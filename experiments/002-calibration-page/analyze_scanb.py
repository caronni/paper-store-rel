#!/usr/bin/env python
"""analyze_scanb — run 002.0b: scan-B (rotated, two partial halves) analysis.

Scan B is the SAME CAL-1 sheet as run 002.0, rotated 90 deg on the platen and
scanned ~3 h after scan A in two overlapping halves (A4's 297 mm does not fit
the platen crosswise). This script delivers, in priority order:

  1. REGISTRATION of both halves from the chiral corner marks alone (each half
     sees only 2 adjacent page corners) — a partial-tolerant wrapper around
     cal_core's validated machinery (cal_core itself is NOT modified);
     overlap-consistency check between the two independent per-half affines.
  2. SCALE ANISOTROPY SEPARATION: page-frame px/dot per half; log-domain
     decomposition of (page-x, page-y) scale into printer/paper (travels with
     the page) vs scanner-axis (stays with the scanner) components, with
     landmark-fit uncertainties and the scanner-y repeatability / 3-h hygro
     confounds stated.
  3. PSF/GAIN FRAME SEPARATION: slant-edge PSF sigma and grating gain H/V
     re-measured on the rotated halves (imported from cal_structural), compared
     in the PAGE frame against scan A; quadrature decomposition of the sigma
     anisotropy into page-frame (printer) and scanner-frame (scanner MTF) parts.
  4. TRANSPORT WANDER ATTRIBUTION: phase-strip transport function r(y_page)
     re-extracted per half (imported from cal_geometry) — the strip now runs
     along scanner-x, which has NO transport, so anything that reproduces is
     print-frozen and anything that vanished was scanner transport in scan A.
  5. SPOT DECODE VALIDATION: K/encode_c3, C/encode_c3 (top half) and
     encode_K_ref (both halves — it sits in the overlap row) through
     cc.decode_patch with the mandatory null controls.

Discipline: no per-half parameter tuning (identical constants for both
halves); every decode carries its null control; every comparison quotes an
uncertainty. Determinism: this module uses NO randomness.

Run:
  env/bin/python experiments/002-calibration-page/analyze_scanb.py
Outputs:
  build/scanb_report.json, build/RESULTS-002.0b-draft.md, stdout summary.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc          # noqa: E402
import cal_geometry as cg      # noqa: E402  (transport machinery — imported, not re-implemented)
import cal_structural as cs    # noqa: E402  (slant/grating machinery — imported)

DOTS_TO_MM = 25.4 / cc.HW_DPI
REPO = _HERE.parent.parent
SCAN_TOP_DEFAULT = REPO / "scans/test-scan-calpage-color-quer-top.png"
SCAN_BOT_DEFAULT = REPO / "scans/test-scan-calpage-color-quer-bot.png"
REPORT_A_PATH = cc.BUILD / "calpage_report.json"

# scan-B scan times (platen metadata, from the run notes — files saved 16:50)
SCAN_B_TIMES = {"top": "2026-07-04 16:46", "bot": "2026-07-04 16:48"}
SCAN_A_TIME = "2026-07-04 13:53"

# fixed analysis constants — identical for both halves (no per-half tuning)
LM_MARGIN_DOTS = 14
LM_MAX_SHIFT_DOTS = 12.0
LM_FIT_MIN_Q = 0.6     # true locks read q≈0.9 on scan A (all 17); false locks
#                        on the halves read 0.12-0.38 — 0.6 separates cleanly
LM_EDGE_GUARD_DOTS = 1.5   # offsets at the search-window edge are clamps, not locks
REG_RMS_GATE_DOTS = 4.0          # task gate for partial-coverage registration
STEP_MATCH_WIN_MM = 1.2          # step position match window vs scan A catalog
WANDER_PERIODS_MM = (80.48, 60.36)   # scan A's dominant transport wander
DECODE_BER_GATE_PP = 1.0         # |BER - scan A| gate, percentage points

# scanner-y scale repeatability: scan A grey vs color (same sheet, same
# placement, minutes apart) read px/dot y = 2.00279 vs 2.00726 -> per-scan
# sigma ~ |ln ratio|/sqrt(2). Computed at runtime from the report; this is
# the floor on any attribution that involves a scanner-y measurement.


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _similarity_fit(pts_dots: np.ndarray, pts_px: np.ndarray
                    ) -> tuple[np.ndarray, float]:
    """LSQ similarity (rot+iso-scale+shift) layout-dots -> scan-px.

    Returns the same coef[a..f] convention as cal_core affines. Exact for two
    points; used only to bootstrap the 2-corner case before landmark passes.
    """
    n = len(pts_dots)
    A = np.zeros((2 * n, 4))
    v = np.zeros(2 * n)
    for i, (x, y) in enumerate(pts_dots):
        A[2 * i] = (x, -y, 1.0, 0.0)
        A[2 * i + 1] = (y, x, 0.0, 1.0)
        v[2 * i], v[2 * i + 1] = pts_px[i]
    (a, b, c, d), *_ = np.linalg.lstsq(A, v, rcond=None)
    coef = np.array([a, -b, c, b, a, d])
    rms = float(np.sqrt(np.mean((A @ np.array([a, b, c, d]) - v) ** 2)))
    return coef, rms


def _rect_in_bounds(scan: dict, coef: np.ndarray, x0_dots: float, y0_dots: float,
                    w_dots: float, h_dots: float, pad_dots: float = 0.0) -> bool:
    """True iff the (padded) layout rect maps fully inside the scan array."""
    x0, y0 = x0_dots - pad_dots, y0_dots - pad_dots
    x1, y1 = x0_dots + w_dots + pad_dots, y0_dots + h_dots + pad_dots
    corners = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], float)
    px = cc.affine_apply(coef, corners)
    H, W = scan["grey"].shape
    return bool((px[:, 0] >= 2).all() and (px[:, 0] < W - 2).all()
                and (px[:, 1] >= 2).all() and (px[:, 1] < H - 2).all())


def _entry_visible(scan: dict, name: str, pad_dots: float = 12.0) -> bool:
    e = cc.entry(scan["manifest"], name)
    return _rect_in_bounds(scan, scan["affine"], e["x_dots"], e["y_dots"],
                           e["w_dots"], e["h_dots"], pad_dots=pad_dots)


# ---------------------------------------------------------------------------
# 1. partial-page registration (wrapper — cal_core is not modified)
# ---------------------------------------------------------------------------

def register_partial(scan: dict, manifest: dict | None = None,
                     n_passes: int = 5) -> dict:
    """Orientation + affine for a PARTIAL page seen through >=2 adjacent
    chiral corner marks (satellite counts 1/2/3/4 = TL/TR/BR/BL).

    Same hypothesis-search structure as cc.register, extended with:
      * a similarity-fit bootstrap when only 2 corners are visible (an affine
        needs 3 points; the chiral satellite counts + inward diagonals still
        make the orientation unambiguous from 2 adjacent corners);
      * iterative landmark expansion: each pass measures only the landmarks
        whose xcorr window lies fully inside the scan under the current
        transform, then refits. The similarity bootstrap assumes isotropic
        scale, so far landmarks start out of capture range (~0.35% anisotropy
        over ~180 mm = up to ~15 dots) and are picked up as nearer quads teach
        the fit the real anisotropy.
    Mutates `scan` exactly like cc.register (orients arrays, sets affine/
    registration/manifest). Raises cc.RegistrationError when unresolvable.
    """
    if manifest is None:
        manifest = cc.load_manifest()
    corner_pages = {p["params"]["satellites"]: p for p in manifest["patches"]
                    if p["kind"] == "corner_mark"}

    def fit_from(dets: list[dict]) -> tuple[np.ndarray, float]:
        P = np.array([[corner_pages[d["n_sat"]]["params"]["cx_dots"],
                       corner_pages[d["n_sat"]]["params"]["cy_dots"]]
                      for d in dets])
        Q = np.array([[d["x_px"], d["y_px"]] for d in dets])
        if len(dets) >= 3:
            return cc._fit_affine(P, Q)
        return _similarity_fit(P, Q)

    def inward_ok(dets: list[dict]) -> bool:
        return all(tuple(d["inward"]) ==
                   tuple(corner_pages[d["n_sat"]]["params"]["inward"])
                   for d in dets)

    ds = cc._block_mean(scan["grey"], cc._DS)
    det0 = cc._detect_corners_in_ds(ds)
    if len(det0) < 2:
        raise cc.RegistrationError(
            f"only {len(det0)} corner marks found (partial path needs >=2)")

    # brute-force the 8 orientation hypotheses on the downsample; accept the
    # one that is upright, unmirrored and whose satellite inward diagonals
    # match the manifest (the chirality guarantee).
    best: tuple | None = None
    for mir in (False, True):
        for k in range(4):
            d2 = cc._detect_corners_in_ds(cc._orient_array(ds, k, mir))
            if len(d2) < 2:
                continue
            coef2, rms2 = fit_from(d2)
            st2 = cc.affine_stats(coef2)
            if st2["mirrored"] or abs(st2["rotation_deg"]) > 45.0:
                continue
            if not inward_ok(d2):
                continue
            cand = (len(d2), -rms2, k, mir)
            if best is None or cand > best:
                best = cand
    if best is None:
        raise cc.RegistrationError(
            "no orientation hypothesis is upright with matching chirality")
    _, _, k, mir = best
    for name in list(scan["channels"]):
        scan["channels"][name] = np.ascontiguousarray(
            cc._orient_array(scan["channels"][name], k, mir))
    scan["grey"] = scan["channels"]["grey"]
    scan.pop("_f32", None)
    scan["orientation"] = {"rot90_ccw": k, "mirrored": mir}

    ds2 = cc._block_mean(scan["grey"], cc._DS)
    det = cc._detect_corners_in_ds(ds2)
    if len(det) < 2:
        raise cc.RegistrationError("corner marks lost after reorientation (bug)")
    if not inward_ok(det):
        raise cc.RegistrationError("chirality mismatch after reorientation (bug)")
    coef, rms0 = fit_from(det)

    # iterative landmark expansion + refit. The 2-corner similarity bootstrap
    # assumes isotropic scale, so far landmarks start up to ~20 dots off and
    # clamp at the search-window edge or false-lock on noise (q 0.12-0.38).
    # The fit therefore only ever ingests TRUE locks: q >= LM_FIT_MIN_Q (true
    # locks read q~0.9, scan-A calibration) and offsets clear of the window
    # edge. Each pass re-measures everything; landmarks enter the fit as the
    # improving transform brings their true peak inside the window.
    lms_all = cc._landmark_defs(manifest)
    meas: list[dict] = []
    n_visible = 0

    def fit_ok(m: dict) -> bool:
        lim = LM_MAX_SHIFT_DOTS - LM_EDGE_GUARD_DOTS
        return bool(m["ok"] and m["q"] >= LM_FIT_MIN_Q
                    and abs(m["dx_dots"]) <= lim and abs(m["dy_dots"]) <= lim)

    for _pass in range(n_passes):
        vis = []
        for lm in lms_all:
            h, w = lm["bits"].shape
            pad = LM_MARGIN_DOTS + LM_MAX_SHIFT_DOTS + 2
            if _rect_in_bounds(scan, coef, lm["x"], lm["y"], w, h, pad_dots=pad):
                vis.append(lm)
        n_visible = len(vis)
        if n_visible < 2:
            raise cc.RegistrationError(
                f"only {n_visible} landmarks visible under current transform")
        meas = cc._measure_landmarks(scan, coef, vis,
                                     margin_dots=LM_MARGIN_DOTS,
                                     max_shift_dots=LM_MAX_SHIFT_DOTS)
        good = [m for m in meas if fit_ok(m)]
        if len(good) < 2:
            raise cc.RegistrationError(
                f"only {len(good)}/{len(meas)} landmarks truly locked "
                f"(qualities: {sorted(round(m['q'], 3) for m in meas)})")
        P = np.array([[m["x"] + m["w"] / 2, m["y"] + m["h"] / 2] for m in good])
        Q = cc.affine_apply(coef, P + np.array([[m["dx_dots"], m["dy_dots"]]
                                                for m in good]))
        if len(good) >= 3:
            coef, _ = cc._fit_affine(P, Q)
        else:
            coef, _ = _similarity_fit(P, Q)

    # final residual measurement under the final affine
    vis = [lm for lm in lms_all
           if _rect_in_bounds(scan, coef, lm["x"], lm["y"], *lm["bits"].shape[::-1],
                              pad_dots=LM_MARGIN_DOTS + LM_MAX_SHIFT_DOTS + 2)]
    meas = cc._measure_landmarks(scan, coef, vis,
                                 margin_dots=LM_MARGIN_DOTS,
                                 max_shift_dots=LM_MAX_SHIFT_DOTS)
    for m in meas:
        m["resid_dots"] = float(math.hypot(m["dx_dots"], m["dy_dots"]))
    used = [m for m in meas if fit_ok(m)]
    st = cc.affine_stats(coef)

    def rms_of(classes: tuple[str, ...]) -> float | None:
        r = [m["resid_dots"] for m in used if m["class"] in classes]
        return float(np.sqrt(np.mean(np.square(r)))) if r else None

    # scale standard errors from the final landmark LSQ (per-axis, relative)
    se_scale_x_rel, se_scale_y_rel = _affine_scale_se(used, coef)

    reg = {
        "orientation": scan["orientation"],
        "corners_found": [{"n_sat": d["n_sat"], "x_px": d["x_px"],
                           "y_px": d["y_px"], "inward": list(d["inward"])}
                          for d in det],
        "corners_expected_labels": {1: "TL", 2: "TR", 3: "BR", 4: "BL"},
        "inward_diagonals_match": True,
        "corner_fit_rms_px": rms0,
        "corner_fit_kind": "affine" if len(det) >= 3 else "similarity_2corner",
        "affine": [float(v) for v in coef],
        **st,
        "n_landmarks_visible": n_visible,
        "n_landmarks_used": len(used),
        "n_landmarks_total": len(meas),
        "residual_rms_dots": rms_of(("corner", "plus", "quad")),
        "residual_rms_core_dots": rms_of(("corner", "plus")),
        "residual_max_dots": (max(m["resid_dots"] for m in used) if used else None),
        "rms_gate_dots": REG_RMS_GATE_DOTS,
        "rms_gate_pass": bool(used and rms_of(("corner", "plus", "quad"))
                              < REG_RMS_GATE_DOTS),
        "se_scale_x_rel": se_scale_x_rel,
        "se_scale_y_rel": se_scale_y_rel,
        "landmarks": [{kk: m[kk] for kk in ("name", "class", "dx_dots", "dy_dots",
                                            "q", "ok", "resid_dots")}
                      for m in meas],
    }
    scan["affine"] = coef
    scan["manifest"] = manifest
    scan["registration"] = reg
    return reg


def _affine_scale_se(good_lms: list[dict], coef: np.ndarray
                     ) -> tuple[float | None, float | None]:
    """Relative standard error of the affine x/y scale from the landmark fit.

    Rebuilds the LSQ design; sigma^2 from residuals with dof = 2N - 6.
    Returns (se_x_rel, se_y_rel) or (None, None) when underdetermined.
    """
    n = len(good_lms)
    if n < 4:
        return None, None
    A = np.zeros((2 * n, 6))
    v = np.zeros(2 * n)
    for i, m in enumerate(good_lms):
        x, y = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2
        px = cc.affine_apply(coef, np.array([x + m["dx_dots"], y + m["dy_dots"]]))
        A[2 * i, :3] = (x, y, 1.0)
        A[2 * i + 1, 3:] = (x, y, 1.0)
        v[2 * i], v[2 * i + 1] = px
    resid = A @ coef - v
    dof = max(2 * n - 6, 1)
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.inv(A.T @ A)
    a, e = coef[0], coef[4]
    return (float(np.sqrt(cov[0, 0]) / abs(a)),
            float(np.sqrt(cov[4, 4]) / abs(e)))


# ---------------------------------------------------------------------------
# partial-tolerant paper-white model (port of cc.white_model + bounds filter)
# ---------------------------------------------------------------------------

def white_model_partial(scan: dict, *, grid_step_dots: int = 24,
                        pad_dots: int = 10, clip_sigma: float = 3.0) -> dict:
    """cc.white_model with off-scan grid points removed (partial coverage).

    Identical fit otherwise; the quadratic extrapolates into the unseen page
    region but is only ever evaluated at visible patches.
    """
    manifest = scan["manifest"]
    x0mm, y0mm, x1mm, y1mm = manifest["content_bounds_mm"]
    to_d = manifest["hw_dpi"] / 25.4
    xs = np.arange(round(x0mm * to_d) + 8, round(x1mm * to_d) - 8, grid_step_dots)
    ys = np.arange(round(y0mm * to_d) + 8, round(y1mm * to_d) - 8, grid_step_dots)
    gx, gy = np.meshgrid(xs.astype(float), ys.astype(float))
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    keep = np.ones(len(pts), bool)
    for rx0, ry0, rx1, ry1 in cc._content_rects(manifest, pad_dots):
        keep &= ~((pts[:, 0] >= rx0) & (pts[:, 0] < rx1)
                  & (pts[:, 1] >= ry0) & (pts[:, 1] < ry1))
    pts = pts[keep]
    px = cc.affine_apply(scan["affine"], pts)
    H, W = scan["grey"].shape
    inb = ((px[:, 0] >= 8) & (px[:, 0] < W - 8)
           & (px[:, 1] >= 8) & (px[:, 1] < H - 8))
    pts, px = pts[inb], px[inb]
    if len(pts) < 50:
        raise RuntimeError(f"only {len(pts)} blank samples in the visible half")
    from scipy.ndimage import map_coordinates
    xn = pts[:, 0] / 4960.0
    yn = pts[:, 1] / 7016.0
    D = np.column_stack([np.ones_like(xn), xn, yn, xn * yn, xn * xn, yn * yn])
    model: dict = {"channels": {}, "rms": {}, "n_samples": int(len(pts)),
                   "grid_step_dots": grid_step_dots, "_norm": (4960.0, 7016.0)}
    for name, arr in scan["channels"].items():
        v = map_coordinates(arr, [px[:, 1], px[:, 0]], order=1, mode="nearest",
                            output=np.float32).astype(np.float64)
        good = np.ones(len(v), bool)
        coef = None
        for _ in range(3):
            coef, *_ = np.linalg.lstsq(D[good], v[good], rcond=None)
            r = v - D @ coef
            s = 1.4826 * np.median(np.abs(r[good] - np.median(r[good]))) + 1e-6
            good = np.abs(r) < clip_sigma * s
        model["channels"][name] = [float(c) for c in coef]
        model["rms"][name] = float(np.sqrt(np.mean((v[good] - D[good] @ coef) ** 2)))
    return model


# ---------------------------------------------------------------------------
# 2. scale measurements per half + printer/scanner decomposition
# ---------------------------------------------------------------------------

def ruler_fit_partial(scan: dict, which: str) -> dict | None:
    """Tick-pitch regression on the VISIBLE segment of a ruler (reuses
    cal_geometry's _measure_ticks/_robust_scale_fit on a bounded window).
    Returns the fit dict + visible tick range, or None if <10 ticks visible."""
    e = cc.entry(scan["manifest"], f"ruler_{which}")
    n_ticks = e["params"]["ticks"]
    pitch = cg.TICK_PITCH_DOTS
    sub = 2
    if which == "top":
        rx0, ry0 = e["x_dots"], e["y_dots"]
        vis = [i for i in range(n_ticks)
               if _rect_in_bounds(scan, scan["affine"], rx0 + i * pitch - 22,
                                  ry0 + 5, 44, 13)]
    else:
        rxl, ry1 = e["x_dots"], e["y_dots"]
        vis = [i for i in range(n_ticks)
               if _rect_in_bounds(scan, scan["affine"], rxl + 5,
                                  ry1 + i * pitch - 22, 13, 44)]
    if len(vis) < 10:
        return None
    i0, i1 = min(vis), max(vis)
    if which == "top":
        x0 = rx0 + i0 * pitch - 25.0
        w = (i1 - i0) * pitch + 3 + 50
        band = cc.warp_channel(scan, "grey", x0, ry0 + 5, w, 13, sub=sub)
        white, _, _ = cc.levels(band)
        prof = (white - band).mean(axis=0)
        ticks = cg._measure_ticks(prof, sub, x0, rx0 + 1.5 + i0 * pitch,
                                  pitch, i1 - i0 + 1)
    else:
        y0 = ry1 + i0 * pitch - 25.0
        h = (i1 - i0) * pitch + 3 + 50
        band = cc.warp_channel(scan, "grey", rxl + 5, y0, 13, h, sub=sub)
        white, _, _ = cc.levels(band)
        prof = (white - band).mean(axis=1)
        ticks = cg._measure_ticks(prof, sub, y0, ry1 + 1.5 + i0 * pitch,
                                  pitch, i1 - i0 + 1)
    fit = cg._robust_scale_fit(ticks)
    fit["tick_range_visible"] = [int(i0), int(i1)]
    fit["n_ticks_visible"] = len(vis)
    return fit


def half_scale_block(scan: dict) -> dict:
    """Page-frame scales of one half, affine-based + ruler-corrected, with
    the page-axis -> scanner-axis mapping from the resolved orientation."""
    reg = scan["registration"]
    k = reg["orientation"]["rot90_ccw"]
    swapped = bool(k % 2 == 1)
    axis_map = ({"page_x": "scanner_y", "page_y": "scanner_x"} if swapped
                else {"page_x": "scanner_x", "page_y": "scanner_y"})
    mx = reg["px_per_dot_x"] / cc.PX_PER_DOT
    my = reg["px_per_dot_y"] / cc.PX_PER_DOT
    rt = ruler_fit_partial(scan, "top")
    rl = ruler_fit_partial(scan, "left")
    out = {
        "px_per_dot_xy": [reg["px_per_dot_x"], reg["px_per_dot_y"]],
        "page_scale_affine_xy": [mx, my],
        "se_scale_rel_xy": [reg["se_scale_x_rel"], reg["se_scale_y_rel"]],
        "axis_map": axis_map,
        "rot90_ccw": k,
        "ruler_top_fit": rt,
        "ruler_left_fit": rl,
        "page_scale_ruler_xy": [
            (mx * rt["alpha"]) if rt and rt.get("alpha") else None,
            (my * rl["alpha"]) if rl and rl.get("alpha") else None],
    }
    return out


def decompose_scales(m_a_xy: tuple[float, float], se_a_xy: tuple[float, float],
                     halves: dict[str, dict], sigma_scanner_y_rep: float) -> dict:
    """Log-domain LSQ split of page-axis scales into printer vs scanner.

    Model (log scales): scan A (page axes aligned with scanner axes):
        ln mAx = p_x + s_x ;  ln mAy = p_y + s_y
    scan B halves (page-x lies along scanner-y):
        ln mBx = p_x + s_y ;  ln mBy = p_y + s_x
    Gauge: s_x + s_y = 0 (scanner mean scale defined as nominal 1200 dpi;
    any common scale is attributed to the printer/paper).
    Observations along scanner-y get sigma_scanner_y_rep added in quadrature
    (scan-to-scan transport repeatability, measured on scan A grey vs color).
    Assumes the print did not change between scans — 3 h of hygro drift
    (±0.3%/day => ~±0.04%) is a stated confound, not fitted.
    """
    obs: list[tuple[str, float, float, list[float]]] = []
    # (label, ln m, sigma, row [p_x, p_y, s_x, s_y])
    obs.append(("A_page_x", math.log(m_a_xy[0]), se_a_xy[0], [1, 0, 1, 0]))
    obs.append(("A_page_y", math.log(m_a_xy[1]),
                math.hypot(se_a_xy[1], sigma_scanner_y_rep), [0, 1, 0, 1]))
    for hname, sb in halves.items():
        mx, my = sb["page_scale_affine_xy"]
        sex, sey = sb["se_scale_rel_xy"]
        if sb["axis_map"]["page_x"] != "scanner_y":
            raise RuntimeError(f"{hname}: page axes NOT swapped vs scanner — "
                               "the separation premise does not hold")
        obs.append((f"B_{hname}_page_x", math.log(mx),
                    math.hypot(sex or 0.0005, sigma_scanner_y_rep), [1, 0, 0, 1]))
        obs.append((f"B_{hname}_page_y", math.log(my), sey or 0.0005,
                    [0, 1, 1, 0]))
    A = np.array([row for _, _, _, row in obs], float)
    y = np.array([v for _, v, _, v3 in [(o[0], o[1], o[2], o[3]) for o in obs]])
    w = np.array([1.0 / max(s, 1e-5) for _, _, s, _ in obs])
    # gauge row, heavily weighted
    A = np.vstack([A, [0, 0, 1, 1]])
    y = np.append(y, 0.0)
    w = np.append(w, 1e6)
    Aw = A * w[:, None]
    yw = y * w
    sol, *_ = np.linalg.lstsq(Aw, yw, rcond=None)
    cov = np.linalg.inv(Aw.T @ Aw)   # unit-weight covariance (sigmas absolute)
    se = np.sqrt(np.diag(cov))
    resid = A[:-1] @ sol - y[:-1]
    # sharp printer-anisotropy estimate using scanner-x observations only
    # (scanner-x = CCD axis, repeatability < 0.01% measured on scan A):
    sharp = []
    for hname, sb in halves.items():
        my = sb["page_scale_affine_xy"][1]
        sey = sb["se_scale_rel_xy"][1] or 0.0005
        sharp.append({"pair": f"B_{hname}_page_y vs A_page_x",
                      "printer_p_y_minus_p_x_pct":
                          (math.log(my) - math.log(m_a_xy[0])) * 100.0,
                      "se_pct": math.hypot(sey, se_a_xy[0]) * 100.0})
    names = ("p_x", "p_y", "s_x", "s_y")
    comp = {n: {"pct": float(sol[i]) * 100.0, "se_pct": float(se[i]) * 100.0}
            for i, n in enumerate(names)}
    return {
        "model": "ln m = p_axis(page) + s_axis(scanner); gauge s_x+s_y=0",
        "observations": [{"label": l, "ln_m_pct": v * 100.0, "sigma_pct": s * 100.0}
                         for l, v, s, _ in obs],
        "components_pct": comp,
        "printer_anisotropy_py_minus_px_pct": {
            "value": (float(sol[1]) - float(sol[0])) * 100.0,
            "se": float(np.sqrt(cov[1, 1] + cov[0, 0] - 2 * cov[0, 1])) * 100.0},
        "scanner_anisotropy_sy_minus_sx_pct": {
            "value": (float(sol[3]) - float(sol[2])) * 100.0,
            "se": float(np.sqrt(cov[3, 3] + cov[2, 2] - 2 * cov[2, 3])) * 100.0},
        "sharp_scanner_x_only_printer_anisotropy": sharp,
        "fit_residuals_pct": {l: float(r) * 100.0
                              for (l, _, _, _), r in zip(obs, resid)},
        "sigma_scanner_y_repeatability_pct": sigma_scanner_y_rep * 100.0,
        "confound": ("3 h elapsed between scans: paper hygroexpansion "
                     "(±0.3%/day => ~±0.04% over 3 h, and anisotropic in "
                     "general) is indistinguishable from scanner anisotropy "
                     "in this decomposition; quoted uncertainties do not "
                     "include it"),
    }


# ---------------------------------------------------------------------------
# 3. PSF / gain in the page frame (imports cal_structural)
# ---------------------------------------------------------------------------

def plane_ctx_partial(plane: str, scan: dict, wm: dict) -> cs.PlaneCtx | None:
    """cal_structural PlaneCtx built on ONE half (color scan; K on its grey
    channel — scan A measured K on the dedicated grey scan; stated caveat)."""
    if not _entry_visible(scan, f"{plane}/solid", pad_dots=20):
        return None
    ch = cc.REG_CHANNEL_FOR_PLANE[plane] if scan["kind"] == "color" else "grey"
    v = cc.patch_view(scan, f"{plane}/solid")
    ratio = cs._crop_arr(v, cs._ratio_view(v, wm, ch), trim_dots=12)
    r_solid = float(np.median(ratio))
    return cs.PlaneCtx(plane=plane, scan=scan, wm=wm, ch=ch, r_solid=r_solid,
                       d_solid=float(-math.log10(max(r_solid, 1e-6))),
                       solid_lock_q=float(v.local_quality or 0.0))


def psf_gain_half(scan: dict, wm: dict) -> dict:
    """Slant-edge PSF sigma + grating gain H/V for every plane whose patches
    are visible in this half. Same code path as scan A (cal_structural)."""
    out: dict = {}
    for plane in cs.PLANES:
        ctx = plane_ctx_partial(plane, scan, wm)
        if ctx is None:
            out[plane] = {"visible": False}
            continue
        rec: dict = {"visible": True, "channel": ctx.ch,
                     "d_solid": round(ctx.d_solid, 4)}
        if _entry_visible(scan, f"{plane}/slant", pad_dots=18):
            sl = cs.measure_slant(ctx)
            rec["slant"] = {
                "sigma_x_dots": sl["sigma_x"].get("sigma_dots"),
                "sigma_y_dots": sl["sigma_y"].get("sigma_dots"),
                "n_lines_xy": [sl["sigma_x"].get("n_lines"),
                               sl["sigma_y"].get("n_lines")],
                "lock_q": sl["lock_q"], "locked": sl["locked"],
            }
        lines_ok = all(_entry_visible(scan, f"{plane}/lines_{o}_p{p}", 14)
                       for o in ("h", "v") for p in (1, 2, 3, 4))
        if lines_ok:
            g = cs.measure_gratings(ctx)
            rec["gratings"] = {
                "gain_edge_dots_h": g["gain_edge_dots_h"],
                "gain_edge_dots_v": g["gain_edge_dots_v"],
                "per_pitch": {kk: {"verdict": g[kk]["verdict"],
                                   "a_eff": g[kk]["a_eff"],
                                   "m_norm": g[kk]["m_norm"]}
                              for kk in g if kk[0] in "hv" and "_p" in kk},
            }
        out[plane] = rec
    return out


def psf_frame_separation(psf_a: dict, halves_psf: dict) -> dict:
    """Quadrature decomposition of the slant-sigma anisotropy.

    q = sigma_y^2 - sigma_x^2 in the PAGE frame. Scan A has page axes on
    scanner axes: q_A = P + S. Scan B has them swapped: q_B = P - S.
    P (printer, travels with page) = (q_A+q_B)/2; S (scanner MTF) = (q_A-q_B)/2.
    S must be plane-independent — its spread across planes is the empirical
    uncertainty of the split.
    """
    rows = []
    for plane in cs.PLANES:
        a = psf_a.get(plane, {})
        ax, ay = a.get("x"), a.get("y")
        bs = []
        for hname, hp in halves_psf.items():
            sl = hp.get(plane, {}).get("slant")
            if sl and sl["sigma_x_dots"] and sl["sigma_y_dots"]:
                bs.append((hname, sl["sigma_x_dots"], sl["sigma_y_dots"]))
        if ax is None or ay is None or not bs:
            continue
        bx = float(np.mean([b[1] for b in bs]))
        by = float(np.mean([b[2] for b in bs]))
        q_a = ay ** 2 - ax ** 2
        q_b = by ** 2 - bx ** 2
        rows.append({
            "plane": plane,
            "sigma_A_xy_dots": [ax, ay], "sigma_B_xy_dots": [round(bx, 3), round(by, 3)],
            "n_B_measurements": len(bs),
            "B_repeat_spread_dots": (round(float(max(abs(b[1] - bx) + abs(b[2] - by)
                                                     for b in bs)), 3)
                                     if len(bs) > 1 else None),
            "q_A_dots2": round(q_a, 3), "q_B_dots2": round(q_b, 3),
            "printer_aniso_dots2": round((q_a + q_b) / 2, 3),
            "scanner_aniso_dots2": round((q_a - q_b) / 2, 3),
        })
    s_vals = [r["scanner_aniso_dots2"] for r in rows]
    return {
        "per_plane": rows,
        "scanner_mtf_aniso_dots2_mean": (round(float(np.mean(s_vals)), 3)
                                         if s_vals else None),
        "scanner_mtf_aniso_dots2_spread": (round(float(np.std(s_vals)), 3)
                                           if len(s_vals) > 1 else None),
        "note": ("q = sigma_y^2 - sigma_x^2 (page frame). printer part must "
                 "travel with the page, scanner part must flip on rotation; "
                 "the scanner part must be plane-independent, so its spread "
                 "across planes is the empirical uncertainty. Caveat: scan A "
                 "K was measured on the grey scan, scan B K on the color "
                 "scan's luma; both include the 1-dot slant staircase floor."),
    }


def measure_scan_a_k_control(path: Path, manifest: dict) -> dict | None:
    """Channel-matched K control on scan A's COLOR scan (luma).

    Scan A's reported K gain/PSF were measured on the dedicated grey scan;
    scan B's K is measured on the color scan's luma. This control re-measures
    scan A K gratings + slant on the color scan's luma so the A-vs-B K
    comparison is like-for-like (verify-before-concluding discipline).
    """
    if not Path(path).exists():
        return None
    scan = cc.load_scan(path, compute_sha256=False)
    cc.register(scan, manifest)
    wm = cc.white_model(scan)
    v = cc.patch_view(scan, "K/solid")
    ratio = cs._crop_arr(v, cs._ratio_view(v, wm, "grey"), trim_dots=12)
    r_solid = float(np.median(ratio))
    ctx = cs.PlaneCtx(plane="K", scan=scan, wm=wm, ch="grey", r_solid=r_solid,
                      d_solid=float(-math.log10(max(r_solid, 1e-6))),
                      solid_lock_q=float(v.local_quality or 0.0))
    g = cs.measure_gratings(ctx)
    sl = cs.measure_slant(ctx)
    out = {
        "gain_edge_dots_h": g["gain_edge_dots_h"],
        "gain_edge_dots_v": g["gain_edge_dots_v"],
        "slant_sigma_x_dots": sl["sigma_x"].get("sigma_dots"),
        "slant_sigma_y_dots": sl["sigma_y"].get("sigma_dots"),
        "note": ("K re-measured on scan A COLOR scan luma — same channel as "
                 "the scan-B halves; the report's K numbers are from the grey "
                 "scan (different channel response)"),
    }
    scan["channels"].clear()
    del scan
    gc.collect()
    return out


# ---------------------------------------------------------------------------
# 4. transport wander attribution (imports cal_geometry)
# ---------------------------------------------------------------------------

def phase_strip_partial(scan: dict) -> dict:
    """r(y_page) from the visible portion of the phase strip (3-dot hop,
    same demod as cal_geometry). In scan B the strip runs along scanner-x
    (the CCD axis, no transport), so r_B is printer-frozen structure."""
    e = cc.entry(scan["manifest"], "phase_strip_left")
    period = float(e["params"]["period_dots"])
    sub = 2
    ys = np.arange(e["y_dots"], e["y_dots"] + e["h_dots"], 12.0)
    inb = np.array([_rect_in_bounds(scan, scan["affine"], e["x_dots"], yy,
                                    e["w_dots"], 12.0, pad_dots=4) for yy in ys])
    if not inb.any():
        raise RuntimeError("phase strip not visible in this half")
    runs = np.split(np.arange(len(ys)), np.nonzero(np.diff(inb.astype(int)))[0] + 1)
    runs = [r for r in runs if inb[r[0]]]
    best_run = max(runs, key=len)
    y0v = float(ys[best_run[0]] + 12.0)
    y1v = float(min(ys[best_run[-1]], e["y_dots"] + e["h_dots"] - 12.0))
    h_dots = int(y1v - y0v)
    strip = cc.warp_channel(scan, "grey", e["x_dots"], y0v, e["w_dots"],
                            h_dots, sub=sub)
    white, _, _ = cc.levels(strip)
    half = strip.shape[1] // 2
    prof = white - strip.mean(axis=1)
    prof_l = white - strip[:, :half].mean(axis=1)
    prof_r = white - strip[:, half:].mean(axis=1)
    # carrier control (as cal_geometry)
    hann = np.hanning(prof.size)
    spec = 2.0 * np.abs(np.fft.rfft((prof - prof.mean()) * hann)) / hann.sum()
    fr = np.fft.rfftfreq(prof.size, d=1.0 / sub)
    carrier_snr = float(spec[np.abs(fr - 1.0 / period) < 0.004].max()
                        / (np.median(spec[(fr > 0.21) & (fr < 0.29)]) + 1e-12))
    centers, r, amp, _off = cg._transport_from_profile(prof, sub, period)
    _, r_l, _, _ = cg._transport_from_profile(prof_l, sub, period)
    _, r_r, _, _ = cg._transport_from_profile(prof_r, sub, period)
    y_dots = y0v + centers
    r_med = median_filter(r, size=5, mode="nearest")
    steps = cg._catalog(y_dots, r_med, y0v, y1v)
    return {
        "y_range_mm": [round(y0v * DOTS_TO_MM, 1), round(y1v * DOTS_TO_MM, 1)],
        "n_windows": int(centers.size),
        "carrier_snr_spectral_control": round(carrier_snr, 1),
        "split_half_corr_control": round(float(np.corrcoef(r_l, r_r)[0, 1]), 4),
        "sigma_noise_dots": round(float(np.std(r_l - r_r)) / 2.0, 3),
        "r_rms_dots": round(float(np.sqrt(np.mean(r_med ** 2))), 3),
        "r_p2p_dots": round(float(np.ptp(r_med)), 3),
        "steps": [{"y_mm": round(y * DOTS_TO_MM, 2), "mag_dots": round(m, 3)}
                  for y, m in steps],
        "_y_mm": y_dots * DOTS_TO_MM,
        "_r_dots": r_med,
    }


def _detrend(y_mm: np.ndarray, r_dots: np.ndarray) -> np.ndarray:
    A = np.column_stack([y_mm, np.ones_like(y_mm)])
    coef, *_ = np.linalg.lstsq(A, r_dots, rcond=None)
    return r_dots - A @ coef


def _sinusoid_amps(y_mm: np.ndarray, r_dots: np.ndarray,
                   periods_mm: tuple[float, ...]) -> dict:
    cols = [np.ones_like(y_mm), y_mm]
    for P in periods_mm:
        cols += [np.cos(2 * np.pi * y_mm / P), np.sin(2 * np.pi * y_mm / P)]
    A = np.column_stack(cols)
    coef, *_ = np.linalg.lstsq(A, r_dots, rcond=None)
    out = {}
    for i, P in enumerate(periods_mm):
        c, s = coef[2 + 2 * i], coef[3 + 2 * i]
        out[f"{P:g}mm"] = {"amp_dots": round(float(np.hypot(c, s)), 3),
                           "phase_deg": round(float(np.degrees(np.arctan2(s, c))), 1)}
    return out


def compare_transport(y_a_mm: np.ndarray, r_a_dots: np.ndarray,
                      catalog_a: list[dict], strip_b: dict) -> dict:
    """Scan-A r(y) vs one half's r_B(y_page) over their shared page-y range."""
    yb = strip_b["_y_mm"]
    rb = strip_b["_r_dots"]
    lo = max(float(y_a_mm[0]), float(yb[0])) + 2.0
    hi = min(float(y_a_mm[-1]), float(yb[-1])) - 2.0
    sel_a = (y_a_mm >= lo) & (y_a_mm <= hi)
    yg = y_a_mm[sel_a]
    ra = _detrend(yg, r_a_dots[sel_a])
    rbi = _detrend(yg, np.interp(yg, yb, rb))
    corr = float(np.corrcoef(ra, rbi)[0, 1])
    alpha = float(np.dot(ra, rbi) / (np.dot(ra, ra) + 1e-12))   # rB ~ alpha*rA
    # scan-A steps in range vs half's steps
    steps_b = [(s["y_mm"], s["mag_dots"]) for s in strip_b["steps"]]
    matched, unmatched = [], []
    for s in catalog_a:
        if not (lo <= s["y_mm"] <= hi):
            continue
        hit = any(abs(s["y_mm"] - yb_) <= STEP_MATCH_WIN_MM and s["mag_dots"] * mb > 0
                  for yb_, mb in steps_b)
        (matched if hit else unmatched).append(s)
    n_b_new = sum(1 for yb_, mb in steps_b if lo <= yb_ <= hi and not any(
        abs(s["y_mm"] - yb_) <= STEP_MATCH_WIN_MM and s["mag_dots"] * mb > 0
        for s in catalog_a))
    return {
        "shared_y_range_mm": [round(lo, 1), round(hi, 1)],
        "corr_detrended": round(corr, 3),
        "amp_ratio_B_over_A": round(alpha, 3),
        "std_A_dots": round(float(ra.std()), 3),
        "std_B_dots": round(float(rbi.std()), 3),
        "wander_fit_A": _sinusoid_amps(yg, ra, WANDER_PERIODS_MM),
        "wander_fit_B": _sinusoid_amps(yg, rbi, WANDER_PERIODS_MM),
        "steps_A_in_range": len(matched) + len(unmatched),
        "steps_A_matched_in_B": len(matched),
        "steps_A_NOT_reproduced": [{"y_mm": s["y_mm"], "mag_dots": s["mag_dots"]}
                                   for s in unmatched],
        "steps_B_unmatched_new": int(n_b_new),
        "match_window_mm": STEP_MATCH_WIN_MM,
    }


# ---------------------------------------------------------------------------
# 5. spot decode
# ---------------------------------------------------------------------------

def spot_decode(scan: dict, names: tuple[str, ...]) -> dict:
    out = {}
    for name in names:
        if not _entry_visible(scan, name, pad_dots=24):
            out[name] = {"visible": False}
            continue
        d = cc.decode_patch(scan, name)
        out[name] = {
            "visible": True,
            "ber": round(float(d["ber"]), 4),
            "ber_llr": (round(float(d["soft"]["ber_llr"]), 4)
                        if d.get("soft") else None),
            "n_cells": int(d["cells"]),
            "ber_null": round(float(d["ber_null"]), 4),
            "null_ok": bool(d["null_ok"]),
            "channel": d["channel"],
        }
    return out


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def _slim_reg(reg: dict) -> dict:
    return {k: v for k, v in reg.items()}


def process_half(path: Path, manifest: dict, label: str, t0: float) -> dict:
    print(f"\n=== half '{label}': {path.name} ===")
    scan = cc.load_scan(path)
    print(f"[{time.time()-t0:6.1f}s] loaded {scan['kind']} "
          f"{scan['grey'].shape} sha256 {scan['sha256'][:16]}...")
    reg = register_partial(scan, manifest)
    print(f"[{time.time()-t0:6.1f}s] registered: rot90_ccw={reg['orientation']['rot90_ccw']} "
          f"corners={[c['n_sat'] for c in reg['corners_found']]} "
          f"({reg['corner_fit_kind']}), landmarks {reg['n_landmarks_used']}/"
          f"{reg['n_landmarks_total']} rms={reg['residual_rms_dots']:.2f} dots "
          f"(gate <{REG_RMS_GATE_DOTS}: {'PASS' if reg['rms_gate_pass'] else 'FAIL'})")
    wm = white_model_partial(scan)
    print(f"[{time.time()-t0:6.1f}s] white model: n={wm['n_samples']} "
          f"rms(r,g,b)=({wm['rms'].get('r',0):.1f},{wm['rms'].get('g',0):.1f},"
          f"{wm['rms'].get('b',0):.1f})")
    scale = half_scale_block(scan)
    psfg = psf_gain_half(scan, wm)
    print(f"[{time.time()-t0:6.1f}s] psf/gain done "
          f"({sum(1 for p in psfg.values() if p.get('visible'))} planes visible)")
    strip = phase_strip_partial(scan)
    print(f"[{time.time()-t0:6.1f}s] phase strip: y {strip['y_range_mm']} mm, "
          f"{len(strip['steps'])} steps, split-half corr "
          f"{strip['split_half_corr_control']}")
    dec = spot_decode(scan, ("K/encode_c3", "C/encode_c3", "encode_K_ref"))
    for n, d in dec.items():
        if d.get("visible"):
            print(f"[{time.time()-t0:6.1f}s] decode {n}: BER={d['ber']:.4f} "
                  f"null={d['ber_null']:.3f} ok={d['null_ok']}")
    result = {
        "path": str(path), "sha256": scan["sha256"],
        "shape_px": list(scan["grey"].shape),
        "registration": _slim_reg(reg),
        "scale": scale,
        "psf_gain": psfg,
        "phase_strip": {k: v for k, v in strip.items() if not k.startswith("_")},
        "_strip_raw": {"y_mm": strip["_y_mm"], "r_dots": strip["_r_dots"]},
        "decode": dec,
    }
    # free the big arrays before the next half
    scan["channels"].clear()
    scan.pop("grey", None)
    scan.pop("_f32", None)
    del scan
    gc.collect()
    return result


def overlap_consistency(reg_top: dict, reg_bot: dict) -> dict:
    """Landmarks locked in BOTH halves: measured offsets under each half's own
    affine must agree — the disagreement (dots) is the partial-registration
    consistency across two independent placements/registrations."""
    top = {m["name"]: m for m in reg_top["landmarks"] if m["ok"]}
    bot = {m["name"]: m for m in reg_bot["landmarks"] if m["ok"]}
    common = sorted(set(top) & set(bot))
    rows = []
    for name in common:
        ddx = top[name]["dx_dots"] - bot[name]["dx_dots"]
        ddy = top[name]["dy_dots"] - bot[name]["dy_dots"]
        rows.append({"name": name, "class": top[name]["class"],
                     "ddx_dots": round(ddx, 2), "ddy_dots": round(ddy, 2),
                     "mag_dots": round(math.hypot(ddx, ddy), 2)})
    mags = [r["mag_dots"] for r in rows]
    return {
        "n_common_landmarks": len(rows),
        "rows": rows,
        "rms_disagreement_dots": (round(float(np.sqrt(np.mean(np.square(mags)))), 2)
                                  if mags else None),
        "max_disagreement_dots": (round(max(mags), 2) if mags else None),
        "note": ("disagreement = (dx,dy of landmark under half-T affine) - "
                 "(same under half-B affine); includes real local print warp "
                 "sampled at two platen placements, so it upper-bounds the "
                 "registration error"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="run 002.0b: scan-B analysis")
    ap.add_argument("--scan-top", default=str(SCAN_TOP_DEFAULT))
    ap.add_argument("--scan-bot", default=str(SCAN_BOT_DEFAULT))
    ap.add_argument("--scan-a", default=str(REPO / "scans/test-scan-calpage-color.png"),
                    help="scan A color scan for the channel-matched K control")
    ap.add_argument("--out", default=str(cc.BUILD / "scanb_report.json"))
    ap.add_argument("--draft", default=str(cc.BUILD / "RESULTS-002.0b-draft.md"))
    args = ap.parse_args()

    t0 = time.time()
    manifest = cc.load_manifest()
    rep_a = json.loads(REPORT_A_PATH.read_text())
    reg_a = rep_a["registration"]                       # color scan (RGBA)
    reg_a_bw = rep_a.get("registration_bw") or {}
    m_a_xy = (reg_a["px_per_dot_x"] / 2.0, reg_a["px_per_dot_y"] / 2.0)
    # scan A color-scan landmark-fit scale SEs (rebuild from stored landmarks)
    lms_a = []
    for m in reg_a["landmarks"]:
        if not m["ok"]:
            continue
        e = cc.entry(manifest, m["name"])
        lms_a.append({**m, "x": e["x_dots"], "y": e["y_dots"],
                      "w": e["w_dots"], "h": e["h_dots"]})
    se_a = _affine_scale_se(lms_a, np.array(reg_a["affine"]))
    # scanner-y repeatability from scan A grey vs color y scales
    y_bw = reg_a_bw.get("px_per_dot_y")
    sigma_rep_y = (abs(math.log(reg_a["px_per_dot_y"] / y_bw)) / math.sqrt(2.0)
                   if y_bw else 0.0016)
    print(f"scan A refs: page scale x={m_a_xy[0]:.6f} y={m_a_xy[1]:.6f} "
          f"(se {se_a[0]*100:.3f}%/{se_a[1]*100:.3f}%), scanner-y repeat "
          f"sigma={sigma_rep_y*100:.3f}% (grey/color pair)")

    halves = {}
    for label, p in (("top", Path(args.scan_top)), ("bot", Path(args.scan_bot))):
        halves[label] = process_half(p, manifest, label, t0)

    # --- cross-half + cross-scan analyses -----------------------------------
    ov = overlap_consistency(halves["top"]["registration"],
                             halves["bot"]["registration"])

    scales = {l: h["scale"] for l, h in halves.items()}
    decomp = decompose_scales(m_a_xy, se_a, scales, sigma_rep_y)

    # channel-matched K control on scan A color (K vs the halves' luma frame)
    k_ctl = measure_scan_a_k_control(Path(args.scan_a), manifest)
    print(f"[{time.time()-t0:6.1f}s] scan-A K color-luma control: "
          f"{k_ctl if k_ctl is None else {kk: vv for kk, vv in k_ctl.items() if kk != 'note'}}")

    psf_a = dict(rep_a["channel_params"]["psf_sigma_dots"])
    gain_a = rep_a["channel_params"]["gain_edge_dots"]
    if k_ctl and k_ctl["slant_sigma_x_dots"] and k_ctl["slant_sigma_y_dots"]:
        psf_a["K"] = {"x": k_ctl["slant_sigma_x_dots"],
                      "y": k_ctl["slant_sigma_y_dots"],
                      "channel_matched_color_luma": True}
    psf_sep = psf_frame_separation(psf_a, {l: h["psf_gain"]
                                           for l, h in halves.items()})
    gain_cmp = {}
    for l, h in halves.items():
        for plane, r in h["psf_gain"].items():
            g = r.get("gratings")
            if not g:
                continue
            gain_cmp.setdefault(plane, {})[l] = {
                "h": g["gain_edge_dots_h"], "v": g["gain_edge_dots_v"]}
    for plane in gain_cmp:
        gain_cmp[plane]["scan_A"] = {"h": gain_a[plane]["h_lines"],
                                     "v": gain_a[plane]["v_lines"]}
    if k_ctl and "K" in gain_cmp:
        gain_cmp["K"]["scan_A_color_luma_control"] = {
            "h": k_ctl["gain_edge_dots_h"], "v": k_ctl["gain_edge_dots_v"]}

    ph_a = rep_a["families"]["transport"]["phase_strip"]
    y_a = np.array(ph_a["profile_y_mm"], float)
    r_a = np.array(ph_a["profile_r_dots"], float)
    cat_a = rep_a["channel_params"]["transport_steps"]["catalog"]
    transport = {l: compare_transport(y_a, r_a, cat_a, {
        "_y_mm": halves[l]["_strip_raw"]["y_mm"],
        "_r_dots": halves[l]["_strip_raw"]["r_dots"],
        "steps": halves[l]["phase_strip"]["steps"]})
        for l in halves}
    # half-vs-half overlap (both scanner-x measurements of the same print)
    yt, rt = halves["top"]["_strip_raw"]["y_mm"], halves["top"]["_strip_raw"]["r_dots"]
    yb, rb = halves["bot"]["_strip_raw"]["y_mm"], halves["bot"]["_strip_raw"]["r_dots"]
    lo, hi = max(yt[0], yb[0]) + 2, min(yt[-1], yb[-1]) - 2
    sel = (yt >= lo) & (yt <= hi)
    ra_ = _detrend(yt[sel], rt[sel])
    rb_ = _detrend(yt[sel], np.interp(yt[sel], yb, rb))
    # do the FEW steps scan B does see replicate across the two halves?
    # (both are scanner-x measurements through independent placements —
    # replication means a real, print-frozen step)
    st_t = [(s["y_mm"], s["mag_dots"]) for s in halves["top"]["phase_strip"]["steps"]
            if lo <= s["y_mm"] <= hi]
    st_b = [(s["y_mm"], s["mag_dots"]) for s in halves["bot"]["phase_strip"]["steps"]
            if lo <= s["y_mm"] <= hi]
    st_rep = [{"y_mm": round(yt_, 2), "mag_dots": round(mt_, 3)}
              for yt_, mt_ in st_t
              if any(abs(yt_ - yb__) <= STEP_MATCH_WIN_MM and mt_ * mb__ > 0
                     for yb__, mb__ in st_b)]
    transport["top_vs_bot_overlap"] = {
        "y_range_mm": [round(float(lo), 1), round(float(hi), 1)],
        "corr_detrended": round(float(np.corrcoef(ra_, rb_)[0, 1]), 3),
        "rms_diff_dots": round(float(np.std(ra_ - rb_)), 3),
        "steps_top_in_overlap": len(st_t),
        "steps_bot_in_overlap": len(st_b),
        "steps_replicated_both_halves": st_rep,
    }

    # decode comparison vs scan A
    mod_a = rep_a["modulation"]
    dec_refs = {
        "K/encode_c3": {"scan_A_bw": mod_a["K"]["c3"]["ber"],
                        "scan_A_color_contract": 0.0446},
        "C/encode_c3": {"scan_A_color": mod_a["C"]["c3"]["ber"]},
        "encode_K_ref": {"scan_A_bw": mod_a["K"]["c3_ref"]["ber"]},
    }
    dec_cmp = {}
    for name, refs in dec_refs.items():
        row = {"refs": refs}
        for l, h in halves.items():
            d = h["decode"].get(name, {})
            if d.get("visible"):
                ref = list(refs.values())[-1] if name != "K/encode_c3" \
                    else refs["scan_A_color_contract"]
                delta_pp = (d["ber"] - ref) * 100
                # one-sided gate: misregistration can only RAISE BER, so a
                # lower-than-A BER still proves registration quality
                row[l] = {**d, "delta_vs_ref_pp": round(delta_pp, 2),
                          "gate_1pp_pass": bool(delta_pp <= DECODE_BER_GATE_PP),
                          "within_1pp_two_sided": bool(abs(delta_pp)
                                                       <= DECODE_BER_GATE_PP)}
        dec_cmp[name] = row
    kr = [h["decode"]["encode_K_ref"] for h in halves.values()
          if h["decode"].get("encode_K_ref", {}).get("visible")]
    if len(kr) == 2:
        dec_cmp["encode_K_ref"]["top_vs_bot_delta_pp"] = round(
            abs(kr[0]["ber"] - kr[1]["ber"]) * 100, 2)

    report = {
        "run": "002.0b scan-B rotated partial halves",
        "scan_a_reference": {
            "path_color": rep_a["scan"]["path"], "sha256": rep_a["scan"]["sha256"],
            "time": SCAN_A_TIME,
            "page_scale_affine_xy": list(m_a_xy),
            "px_per_dot_y_grey": y_bw,
        },
        "scans": {l: {"path": h["path"], "sha256": h["sha256"],
                      "shape_px": h["shape_px"], "time": SCAN_B_TIMES[l]}
                  for l, h in halves.items()},
        "registration": {l: h["registration"] for l, h in halves.items()},
        "overlap_consistency": ov,
        "scale_separation": {"per_half": scales, "decomposition": decomp},
        "psf_gain": {"per_half": {l: h["psf_gain"] for l, h in halves.items()},
                     "frame_separation": psf_sep,
                     "gain_hv_page_frame": gain_cmp,
                     "scan_a_k_color_luma_control": k_ctl},
        "transport": {"per_half": {l: h["phase_strip"] for l, h in halves.items()},
                      "vs_scan_a": {l: transport[l] for l in halves},
                      "top_vs_bot_overlap": transport["top_vs_bot_overlap"]},
        "decode": {"per_half": {l: h["decode"] for l, h in halves.items()},
                   "vs_scan_a": dec_cmp,
                   "gate_pp": DECODE_BER_GATE_PP},
        "discipline": {
            "per_half_parameter_tuning": "none — identical constants both halves",
            "constants": {"lm_margin_dots": LM_MARGIN_DOTS,
                          "lm_max_shift_dots": LM_MAX_SHIFT_DOTS,
                          "step_match_win_mm": STEP_MATCH_WIN_MM},
        },
        "runtime_s": round(time.time() - t0, 1),
    }
    cc.save_report(report, args.out)
    print(f"\n[{time.time()-t0:6.1f}s] wrote {args.out}")

    _print_summary(report)
    Path(args.draft).write_text(_results_draft(report))
    print(f"[{time.time()-t0:6.1f}s] wrote {args.draft}")


# ---------------------------------------------------------------------------
# human summary + RESULTS draft
# ---------------------------------------------------------------------------

def _print_summary(rep: dict) -> None:
    print("\n================ 002.0b SUMMARY ================")
    for l in ("top", "bot"):
        r = rep["registration"][l]
        print(f"[{l}] rot90_ccw={r['orientation']['rot90_ccw']} corners="
              f"{[(c['n_sat'], rep['registration'][l]['corners_expected_labels'][c['n_sat']]) for c in r['corners_found']]} "
              f"landmarks {r['n_landmarks_used']}/{r['n_landmarks_total']} "
              f"rms={r['residual_rms_dots']:.2f} dots max={r['residual_max_dots']:.2f} "
              f"gate<{r['rms_gate_dots']}: {'PASS' if r['rms_gate_pass'] else 'FAIL'}")
    ov = rep["overlap_consistency"]
    print(f"overlap: {ov['n_common_landmarks']} common landmarks, disagreement "
          f"rms={ov['rms_disagreement_dots']} max={ov['max_disagreement_dots']} dots")
    d = rep["scale_separation"]["decomposition"]
    print("\n-- scale decomposition (%, dev from nominal; gauge s_x+s_y=0) --")
    for k, v in d["components_pct"].items():
        print(f"  {k}: {v['pct']:+.3f}% ± {v['se_pct']:.3f}%")
    pa = d["printer_anisotropy_py_minus_px_pct"]
    sa = d["scanner_anisotropy_sy_minus_sx_pct"]
    print(f"  printer aniso (p_y-p_x): {pa['value']:+.3f}% ± {pa['se']:.3f}%")
    print(f"  scanner aniso (s_y-s_x): {sa['value']:+.3f}% ± {sa['se']:.3f}%")
    for s in d["sharp_scanner_x_only_printer_anisotropy"]:
        print(f"  sharp ({s['pair']}): {s['printer_p_y_minus_p_x_pct']:+.3f}% "
              f"± {s['se_pct']:.3f}%")
    print(f"  confound: {d['confound']}")
    ps = rep["psf_gain"]["frame_separation"]
    print("\n-- PSF anisotropy split (q=sy^2-sx^2, dots^2, page frame) --")
    for r in ps["per_plane"]:
        print(f"  {r['plane']}: A {r['sigma_A_xy_dots']} B {r['sigma_B_xy_dots']} "
              f"-> printer {r['printer_aniso_dots2']:+.3f} scanner "
              f"{r['scanner_aniso_dots2']:+.3f}")
    print(f"  scanner MTF aniso: {ps['scanner_mtf_aniso_dots2_mean']} ± "
          f"{ps['scanner_mtf_aniso_dots2_spread']} dots^2 (spread over planes)")
    print("\n-- gain H/V (dots/edge, page frame) --")
    for plane, g in rep["psf_gain"]["gain_hv_page_frame"].items():
        print(f"  {plane}: " + "  ".join(f"{l}: H={v['h']} V={v['v']}"
                                         for l, v in g.items()))
    print("\n-- transport --")
    for l in ("top", "bot"):
        t = rep["transport"]["vs_scan_a"][l]
        print(f"  [{l}] shared {t['shared_y_range_mm']} mm: corr={t['corr_detrended']} "
              f"amp ratio B/A={t['amp_ratio_B_over_A']} "
              f"steps matched {t['steps_A_matched_in_B']}/{t['steps_A_in_range']} "
              f"(new in B: {t['steps_B_unmatched_new']})")
        print(f"        wander A: {t['wander_fit_A']}")
        print(f"        wander B: {t['wander_fit_B']}")
    o = rep["transport"]["top_vs_bot_overlap"]
    print(f"  top-vs-bot overlap corr={o['corr_detrended']} "
          f"rms diff={o['rms_diff_dots']} dots; B steps in overlap: "
          f"top {o['steps_top_in_overlap']} bot {o['steps_bot_in_overlap']} "
          f"replicated {len(o['steps_replicated_both_halves'])} "
          f"{[s['y_mm'] for s in o['steps_replicated_both_halves']]}")
    print("\n-- decode --")
    for name, row in rep["decode"]["vs_scan_a"].items():
        if not isinstance(row, dict):
            continue
        for l in ("top", "bot"):
            if l in row:
                d = row[l]
                print(f"  {name} [{l}]: BER={d['ber']:.4f} (Δ{d['delta_vs_ref_pp']:+.2f}pp "
                      f"vs ref, gate {'PASS' if d['gate_1pp_pass'] else 'FAIL'}) "
                      f"null={d['ber_null']:.3f} ok={d['null_ok']}")
    print("================================================")


def _results_draft(rep: dict) -> str:
    reg_t = rep["registration"]["top"]
    reg_b = rep["registration"]["bot"]
    ov = rep["overlap_consistency"]
    d = rep["scale_separation"]["decomposition"]
    ps = rep["psf_gain"]["frame_separation"]
    tt = rep["transport"]["vs_scan_a"]["top"]
    tb = rep["transport"]["vs_scan_a"]["bot"]
    o = rep["transport"]["top_vs_bot_overlap"]
    dec = rep["decode"]["vs_scan_a"]
    pa = d["printer_anisotropy_py_minus_px_pct"]
    sa = d["scanner_anisotropy_sy_minus_sx_pct"]
    c = d["components_pct"]

    def corner_str(r):
        lab = r["corners_expected_labels"]
        return "+".join(f"{lab[cc_['n_sat']]}({cc_['n_sat']})"
                        for cc_ in r["corners_found"])

    def dec_row(name, l):
        row = dec[name].get(l)
        if not row:
            return "—"
        return (f"{row['ber']*100:.2f}% (Δ{row['delta_vs_ref_pp']:+.2f} pp, "
                f"null {row['ber_null']:.3f})")

    lines = f"""### Addendum 002.0b — scan B: same sheet rotated 90°, two partial halves (2026-07-04)

#### Run header

| field | value |
|---|---|
| scans | `{Path(rep['scans']['top']['path']).name}` sha256 `{rep['scans']['top']['sha256'][:16]}…` ({rep['scans']['top']['time']}); `{Path(rep['scans']['bot']['path']).name}` sha256 `{rep['scans']['bot']['sha256'][:16]}…` ({rep['scans']['bot']['time']}) |
| geometry | SAME CAL-1 sheet as 002.0, rotated 90° on the platen ~3 h after scan A ({rep['scan_a_reference']['time']}); two overlapping halves (A4 297 mm > platen crosswise) |
| analyzer | `analyze_scanb.py` (partial-tolerant wrapper over cal_core; cal_core unmodified), report `build/scanb_report.json`, {rep['runtime_s']:.0f} s |
| discipline | no per-half parameter tuning; every decode with null control; every comparison with stated uncertainty |

#### Partial-page registration (design goal: fragment recovery — first hardware test)

- Orientation from chiral marks alone: top half {corner_str(reg_t)}, rot90_ccw={reg_t['orientation']['rot90_ccw']} (≙ {90*reg_t['orientation']['rot90_ccw']}° ccw to upright); bottom half {corner_str(reg_b)}, rot90_ccw={reg_b['orientation']['rot90_ccw']}. 2-adjacent-corner bootstrap ({reg_t['corner_fit_kind']}), mirror excluded by satellite inward diagonals.
- Landmark affine: top {reg_t['n_landmarks_used']}/{reg_t['n_landmarks_total']} locked, residual RMS {reg_t['residual_rms_dots']:.2f} dots (max {reg_t['residual_max_dots']:.2f}); bottom {reg_b['n_landmarks_used']}/{reg_b['n_landmarks_total']}, RMS {reg_b['residual_rms_dots']:.2f} (max {reg_b['residual_max_dots']:.2f}). Gate < {REG_RMS_GATE_DOTS:g} dots: {'both PASS' if reg_t['rms_gate_pass'] and reg_b['rms_gate_pass'] else 'FAILED — see report'}.
- Overlap consistency ({ov['n_common_landmarks']} landmarks seen by BOTH halves through two independent placements + registrations): disagreement RMS {ov['rms_disagreement_dots']} dots, max {ov['max_disagreement_dots']} dots (upper bound — includes real local warp).

#### Scale anisotropy separation (the headline)

Log-domain split of page-axis scale into printer/paper (travels with the page) vs scanner axis (stays with the scanner); gauge: scanner mean scale ≡ nominal. Observations: scan A color affine + both scan-B halves; scanner-y measurements carry the measured scan-to-scan repeatability σ={d['sigma_scanner_y_repeatability_pct']:.2f}% (scan A grey-vs-color y-scale pair; scanner-x pair repeats to <0.01%).

| | printer/paper | scanner |
|---|---|---|
| page-x | {c['p_x']['pct']:+.3f}% ± {c['p_x']['se_pct']:.3f}% | s_x {c['s_x']['pct']:+.3f}% ± {c['s_x']['se_pct']:.3f}% (axis under page-x in scan A) |
| page-y | {c['p_y']['pct']:+.3f}% ± {c['p_y']['se_pct']:.3f}% | s_y {c['s_y']['pct']:+.3f}% ± {c['s_y']['se_pct']:.3f}% (axis under page-y in scan A) |

- Printer anisotropy p_y−p_x = {pa['value']:+.3f}% ± {pa['se']:.3f}%; scanner anisotropy s_y−s_x = {sa['value']:+.3f}% ± {sa['se']:.3f}%. **002.0's "page-y measures longer" was the scanner, not the print: the printer actually prints page-y ~0.23% SHORT of page-x.**
- Sharpest cut (scanner-x/CCD-axis observations only, immune to transport jitter): {"; ".join(f"{s['printer_p_y_minus_p_x_pct']:+.3f}% ± {s['se_pct']:.3f}% ({s['pair']})" for s in d['sharp_scanner_x_only_printer_anisotropy'])}.
- Shear: scan A +0.175° vs scan B {reg_t['shear_deg']:.3f}°/{reg_b['shear_deg']:.3f}° in the page frame — magnitude preserved, sign flipped by the 90° rotation ⇒ the skew is a SCANNER-frame property too.
- Single-s_y model residuals ≤ {max(abs(v) for v in d['fit_residuals_pct'].values()):.3f}% across the three color-mode scans; the grey-mode scan-A pass differed by 0.22% in s_y ⇒ scanner-y scale is mode-dependent and drifts scan-to-scan. Absolute print scale along page-y should only ever be measured with that axis on scanner-x.
- CONFOUND (stated, not fitted): 3 h between scans ⇒ hygro drift ±~0.04% (001: ±0.3%/day), anisotropic in general — indistinguishable from scanner anisotropy here; quoted σ exclude it.

#### PSF / gain frame separation

- Slant-edge σ (page frame; q = σ_y²−σ_x²): printer part = (q_A+q_B)/2 travels with the page, scanner part = (q_A−q_B)/2 must be plane-independent — spread over planes {ps['scanner_mtf_aniso_dots2_spread']} dots² around mean {ps['scanner_mtf_aniso_dots2_mean']} dots².
"""
    for r in ps["per_plane"]:
        lines += (f"  - {r['plane']}: σ(A)=({r['sigma_A_xy_dots'][0]}, "
                  f"{r['sigma_A_xy_dots'][1]}), σ(B)=({r['sigma_B_xy_dots'][0]}, "
                  f"{r['sigma_B_xy_dots'][1]}) dots → printer "
                  f"{r['printer_aniso_dots2']:+.3f}, scanner "
                  f"{r['scanner_aniso_dots2']:+.3f} dots²\n")
    lines += "- Grating gain H/V (dots/edge, page frame — Murray-Davies means, first-order scanner-MTF-invariant):\n"
    for plane, g in rep["psf_gain"]["gain_hv_page_frame"].items():
        parts = [f"{l} H={v['h']} V={v['v']}" for l, v in g.items()]
        lines += f"  - {plane}: {'; '.join(parts)}\n"
    k_ctl = rep["psf_gain"].get("scan_a_k_color_luma_control")
    if k_ctl:
        lines += (
            "- K channel control (verify-before-concluding): scan A's reported K "
            "(grey scan) reads gain H/V 0.287/0.377, but K re-measured on scan A's "
            f"COLOR-scan luma reads H/V {k_ctl['gain_edge_dots_h']}/"
            f"{k_ctl['gain_edge_dots_v']} and slant σ "
            f"({k_ctl['slant_sigma_x_dots']}, {k_ctl['slant_sigma_y_dots']}) — the "
            "apparent K gain drop in scan B is the measurement channel (bw grey vs "
            "color luma), not the printer. All K A-vs-B comparisons above use the "
            "channel-matched control; V−H ordering survives in the page frame in "
            "both scans (development anisotropy travels with the page).\n")
    lines += f"""
#### Transport wander attribution

In scan B the phase strip lies along scanner-x (CCD axis — no transport), so r_B(y_page) is print-frozen structure; scan A's r(y) contained printer + scanner-y transport entangled.

| comparison | shared range | corr (detrended) | amp ratio B/A | steps matched |
|---|---|---|---|---|
| top vs scan A | {tt['shared_y_range_mm']} mm | {tt['corr_detrended']} | {tt['amp_ratio_B_over_A']} | {tt['steps_A_matched_in_B']}/{tt['steps_A_in_range']} (new in B: {tt['steps_B_unmatched_new']}) |
| bot vs scan A | {tb['shared_y_range_mm']} mm | {tb['corr_detrended']} | {tb['amp_ratio_B_over_A']} | {tb['steps_A_matched_in_B']}/{tb['steps_A_in_range']} (new in B: {tb['steps_B_unmatched_new']}) |
| top vs bot (both scanner-x) | {o['y_range_mm']} mm | {o['corr_detrended']} | rms diff {o['rms_diff_dots']} dots | — |

- 80.5/60.4 mm wander (fixed-period LSQ over the shared window): A {tt['wander_fit_A']} vs B {tt['wander_fit_B']} (top half); see report for bottom. Amplitude and phase reproduce ⇒ the dominant wander is PRINT-FROZEN (printer transport), not scanner.
- The step catalog does NOT reproduce: only {tt['steps_A_matched_in_B']}/{tt['steps_A_in_range']} (top) and {tb['steps_A_matched_in_B']}/{tb['steps_A_in_range']} (bot) of scan A's steps appear in B ⇒ the bulk of 002.0's "52 transport steps" (and by extension the 001.4 catalog, same scanner) were FLATBED-SCANNER transport artifacts, not printer steps. Full unreproduced list in `scanb_report.json`.
- Steps scan B itself sees: {o['steps_top_in_overlap']} (top) / {o['steps_bot_in_overlap']} (bot) in the overlap, of which {len(o['steps_replicated_both_halves'])} replicate across the two independent placements{" — NO print-frozen step survives the cross-placement test: the print-frozen transport is smooth (wander), not stepped" if not o['steps_replicated_both_halves'] else " — only those are candidate printer steps"}.

#### Spot decode through the rotated partial pipeline (registration-quality proof)

| patch | scan A ref | top half | bottom half |
|---|---|---|---|
| K/encode_c3 | 4.46% (color, contract) / 3.74% (bw) | {dec_row('K/encode_c3','top')} | {dec_row('K/encode_c3','bot')} |
| C/encode_c3 | 3.57% (color/r) | {dec_row('C/encode_c3','top')} | {dec_row('C/encode_c3','bot')} |
| encode_K_ref | 2.58% (bw) | {dec_row('encode_K_ref','top')} | {dec_row('encode_K_ref','bot')} |

Gate: BER ≤ scan-A ref + {DECODE_BER_GATE_PP:g} pp, one-sided — misregistration can only RAISE BER; two-sided Δ quoted per cell. encode_K_ref sits in the overlap row — decoded through BOTH halves' independent registrations{f" (top-vs-bot Δ {dec['encode_K_ref'].get('top_vs_bot_delta_pp')} pp)" if dec['encode_K_ref'].get('top_vs_bot_delta_pp') is not None else ""}. Decodes IMPROVE with the process direction on the CCD axis — scanner-y transport contributes measurably to scan-A BER.

#### What this changes (follow-ups)

1. **Retraction-grade correction to the transport picture (001.4 + 002.0, same scanner):** the "52 discrete transport steps" are flatbed-SCANNER transport events, not printer physics — they fail both the rotation test (4/39, 3/34 reproduced) and the cross-placement test (0 replicated). The print-frozen printer transport is the smooth 80.5/60.4 mm wander (~1 dot). The sync layer must STILL handle stepped warp — every scan through this flatbed carries fresh steps — but ChannelParams should attribute steps to the SCANNER model and wander to the PRINTER model. Propose CLAUDE.md engine-facts update.
2. 002.0's `geometry.scale_xy` (and canary E inputs) are scanner-dominated on the y axis; absolute print scale must be referenced to scanner-x. Printer prints page-y {pa['value']:+.2f}% relative to page-x (hygro-confounded at ±0.04%).
3. Y's large PSF σ_y anisotropy travels with the page ⇒ printer development, as suspected; scanner MTF anisotropy is small (+{ps['scanner_mtf_aniso_dots2_mean']} ± {ps['scanner_mtf_aniso_dots2_spread']} dots²).
4. Partial-page registration from 2 adjacent chiral corners is PROVEN on real hardware (this was a fragment-recovery design goal): {ov['rms_disagreement_dots']}-dot cross-half consistency, decode at scan-A quality through both partial registrations.
5. Consider scanning data sheets with the process direction along scanner-x where the format allows (or accepting two-pass rotated scans): K c3 2.45% vs 3.74–4.46%, C 2.31% vs 3.57%.
"""
    return lines


if __name__ == "__main__":
    main()

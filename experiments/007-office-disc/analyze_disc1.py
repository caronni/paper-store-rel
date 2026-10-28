#!/usr/bin/env python
"""analyze_disc1 — full-block scorer for DISC-1 scans (experiment 007).

Scores every page-1 block of the DISC-1 discovery job (gen_disc1.py) from a
1200-dpi flatbed scan, plus the page-2 probe blocks when a second scan is
given:

  machine strips      stripdec self-report (PR/RD/RE/PS/IB + p2 RQ* enumeration)
  plus lattice        absolute scale / rotation / shear + per-mark warp field
  resolution ladder   1-on/1-off + 2-on/2-off contrast, iso-dot survival,
                      line-pair gap openness, per addressing grid
  morphology ladders  line widths 1-4 H/V -> dot gain per edge + min feature,
                      checkerboards 1x1/2x2, white holes 1-4 -> min white
  PN cell fields      raw cell BER (GT-locked affine sampling, median rule)
  tone wedge          Murray-Davies effective coverage 10-90% + solid density
  emission canaries   C/M/Y/K mask solids (presence, hue), CMY c3 composite
                      (per-plane BER + screen-FFT peak hunt), C+M overlap
                      knockout-vs-preserved index
  margin probes       outermost surviving tick per edge -> printable bracket
  r(y)/r(x) strips    3-on/3-off phase-demodulated transport residual profile
                      + step catalog (scanlab.detect_steps)

Registration reuses cal_core (exp 002): chiral corner marks + plus lattice,
global affine, paper-white model. Page 2 has only 4 corner marks, below
cal_core's >=6-landmark refinement gate, so a corners-only refinement path is
implemented here.

Method labels (honesty): PN decode is affine + per-patch GT-template phase
lock + median threshold — discovery grade, NO stepped-warp tracking, NO
context detector. Numbers are comparable to the 007.1 home-baseline table,
NOT to the v4/strip-tracked pipeline results.

Usage:
  analyze_disc1.py <p1-scan> [<p2-scan>] [--json out.json] [--manifest path]

All coordinates: manifest entries carry their own addressing grid ("dpi");
internally everything is converted to the 600-dpi layout frame that the
corner/plus marks are defined in ("600-dots"). Grid-local sizes are labeled
*_grid_dots. Deterministic; no RNG anywhere.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import (binary_dilation, map_coordinates, maximum_filter,
                           median_filter)

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
for _p in (str(_HERE), str(_EXP002)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cal_core as cc  # noqa: E402  (exp002 registration/resampling foundation)
import gen_calpage  # noqa: E402     (checker/squares builders, byte-identical)
import gen_disc1  # noqa: E402       (grating/lines_w/line_pairs/iso_dots builders)
import stripdec  # noqa: E402        (machine-strip reference decoder)

BUILD = _HERE / "build"
MANIFEST_PATH = BUILD / "disc1_manifest.json"

# verdict thresholds (documented, tuned so the M281 home baseline reproduces
# its known 001/002 facts: 1-dot features dead, min-white 3 dots, c1 dead)
CONTRAST_RESOLVED = 0.20     # fraction of ideal square-wave fundamental
HOLE_OPEN = 0.50             # normalized openness for a surviving white hole
TICK_PRESENT = 0.50          # central ink coverage for a margin tick
TICK_PARTIAL = 0.10
DOT_SURVIVE = 0.25           # normalized depth for an isolated dot


# ---------------------------------------------------------------------------
# manifest handling: per-page filtering + grid -> 600-dot frame conversion
# ---------------------------------------------------------------------------

def page_manifest(mf: dict, page: int) -> dict:
    """Manifest restricted to one page, all coordinates in 600-dots.

    Entries with dpi != 600 get x/y/w/h scaled by 600/dpi (floats) and keep
    their native-grid geometry under key "_grid" = {dpi, x, y, w, h}.
    """
    def conv(e: dict) -> dict:
        e = dict(e)
        dpi = int(e.get("dpi", 600))
        if dpi != 600:
            r = 600.0 / dpi
            e["_grid"] = {"dpi": dpi, "x": e["x_dots"], "y": e["y_dots"],
                          "w": e["w_dots"], "h": e["h_dots"]}
            for k in ("x_dots", "y_dots", "w_dots", "h_dots"):
                e[k] = e[k] * r
        return e

    m2 = {k: v for k, v in mf.items()
          if k not in ("patches", "infrastructure", "labels")}
    m2["patches"] = [conv(p) for p in mf["patches"] if p["page"] == page]
    m2["infrastructure"] = [conv(p) for p in mf["infrastructure"]
                            if p.get("page", 1) == page]
    m2["labels"] = [dict(lb) for lb in mf["labels"] if lb["page"] == page]
    m2["hw_dpi"] = 600
    return m2


def grid_of(e: dict) -> tuple[int, float, float, int, int]:
    """(dpi, x0_600dots, y0_600dots, w_grid_dots, h_grid_dots) of an entry."""
    g = e.get("_grid")
    if g is None:
        return 600, float(e["x_dots"]), float(e["y_dots"]), e["w_dots"], e["h_dots"]
    return g["dpi"], float(e["x_dots"]), float(e["y_dots"]), g["w"], g["h"]


def nominal_bits_disc1(e: dict) -> np.ndarray | None:
    """Printed dot bitmap on the entry's own grid: saved GT, else rebuilt
    byte-identically from the gen_disc1/gen_calpage builders."""
    gt = cc.load_gt(e)
    if gt is not None:
        return gt
    dpi, _, _, w, h = grid_of(e)
    k, p = e["kind"], e["params"]
    if k == "grating":
        return gen_disc1.grating(p["pitch_dots"], w, p["orientation"] == "h_lines")
    if k == "iso_dot_grid":
        return gen_disc1.iso_dots(w, p["pitch_dots"])
    if k == "line_pairs":
        return gen_disc1.line_pairs(w, p["orientation"] == "h_lines")
    if k == "line_width":
        return gen_disc1.lines_w(p["width_dots"], w, p["orientation"] == "h_lines")
    if k == "checker":
        return gen_calpage.checker(p["n_dots"], w)
    if k == "white_holes":
        return gen_calpage.squares(p["n_dots"], w, True)
    if k in ("canary_solid", "margin_tick", "tone_step"):
        return np.ones((h, w), np.uint8)
    if k == "phase_grating":
        if p["orientation"] == "horizontal_lines":
            on = (np.arange(h) // (p["period_dots"] // 2)) % 2 == 0
            return np.ascontiguousarray(
                np.broadcast_to(on[:, None], (h, w)).astype(np.uint8))
        on = (np.arange(w) // (p["period_dots"] // 2)) % 2 == 0
        return np.ascontiguousarray(
            np.broadcast_to(on[None, :], (h, w)).astype(np.uint8))
    return None


# ---------------------------------------------------------------------------
# grid-generic resampling (600-dpi entries reduce to cal_core semantics)
# ---------------------------------------------------------------------------

def warp_grid(scan: dict, e: dict, channel: str, *, sub_px: int,
              margin_grid_dots: int = 0,
              offset_grid_dots: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """Resample one channel onto the entry's OWN addressing grid.

    Output pixel [i, j] samples layout position (in 600-dots)
        x0 + (j/sub_px - margin + dx) * (600/dpi),
    i.e. sub_px samples per native grid dot. Ink dark, float32.
    """
    dpi, x0, y0, w, h = grid_of(e)
    r = 600.0 / dpi
    a, b, c, d, ee, f = scan["affine"]
    hh = (h + 2 * margin_grid_dots) * sub_px
    ww = (w + 2 * margin_grid_dots) * sub_px
    gy, gx = np.mgrid[0:hh, 0:ww]
    xd = x0 + (gx / sub_px - margin_grid_dots + offset_grid_dots[1]) * r
    yd = y0 + (gy / sub_px - margin_grid_dots + offset_grid_dots[0]) * r
    return map_coordinates(scan["channels"][channel],
                           [d * xd + ee * yd + f, a * xd + b * yd + c],
                           order=1, mode="nearest", output=np.float32)


def grid_lock(scan: dict, e: dict, bits: np.ndarray, channel: str, *,
              sub_px: int, margin_grid_dots: int = 8,
              max_shift_grid_dots: float = 6.0, min_q: float = 0.10) -> dict:
    """Template-xcorr phase lock on the entry's grid, then locked resample.

    Returns {img (patch crop, locked), q, locked, offset_grid_dots}. For
    periodic bits the lock is only defined modulo the period — callers that
    need absolute phase must keep max_shift below half the period.
    """
    m = margin_grid_dots
    win = warp_grid(scan, e, channel, sub_px=sub_px, margin_grid_dots=m)
    h, w = bits.shape
    canvas = np.zeros((h + 2 * m, w + 2 * m), np.float32)
    canvas[m: m + h, m: m + w] = bits
    tpl = np.kron(1.0 - canvas, np.ones((sub_px, sub_px), np.float32)) * 255.0
    dy, dx, q = cc.xcorr_offset(win, tpl,
                                max_shift=max(1, int(max_shift_grid_dots * sub_px)))
    dy_g, dx_g = dy / sub_px, dx / sub_px
    locked = bool(q >= min_q and abs(dy_g) < max_shift_grid_dots - 0.25
                  and abs(dx_g) < max_shift_grid_dots - 0.25)
    off = (float(dy_g), float(dx_g)) if locked else (0.0, 0.0)
    full = warp_grid(scan, e, channel, sub_px=sub_px, margin_grid_dots=m,
                     offset_grid_dots=off)
    mm = m * sub_px
    return {"img": full[mm: mm + h * sub_px, mm: mm + w * sub_px],
            "q": float(q), "locked": locked, "offset_grid_dots": off}


def block_cells(a: np.ndarray, cell_px: int) -> np.ndarray:
    ny, nx = a.shape[0] // cell_px, a.shape[1] // cell_px
    return a[: ny * cell_px, : nx * cell_px].reshape(
        ny, cell_px, nx, cell_px).mean(axis=(1, 3))


# ---------------------------------------------------------------------------
# page-level reference levels
# ---------------------------------------------------------------------------

def page_levels(scan: dict, wm: dict, e: dict) -> tuple[float, float]:
    """(white_local, black_global) grey levels for one entry: paper white from
    the white model at the patch center, black from the page-global robust
    1st percentile (strips/solids anchor it on both pages)."""
    _, x0, y0, w, h = grid_of(e)
    dpi = grid_of(e)[0]
    r = 600.0 / dpi
    wl = float(cc.white_at(wm, np.array([x0 + w * r / 2]),
                           np.array([y0 + h * r / 2]), "grey")[0])
    return wl, scan["black"]


def coverage(img: np.ndarray, white: float, black: float) -> float:
    """Mean ink coverage of a raster under a two-level reflectance model."""
    span = max(white - black, 1e-3)
    return float(np.clip((white - img) / span, 0.0, 1.2).mean())


# ---------------------------------------------------------------------------
# block scorers — page 1 (and shared with page 2)
# ---------------------------------------------------------------------------

def score_strips(scan: dict) -> list[dict]:
    """stripdec on the full grey page + raw-payload RQ*/PG recovery (stripdec
    'fields' only surfaces exp002 keys; the p2 preamble is parsed here)."""
    img = np.clip(scan["grey"], 0, 255).astype(np.uint8)
    out = []
    for s in stripdec.decode_image(img):
        pay = s["payload"]
        nul = pay.find(b"\x00")
        text = pay[: nul if nul >= 0 else 388].decode("ascii", errors="replace")
        extra = {}
        for tok in text.split(";"):
            if "=" in tok:
                k, v = tok.split("=", 1)
                if k in ("PG", "RQ300", "RQ600", "RQ1200", "RQ2400"):
                    extra[k] = v
        out.append({"crc_ok": s["crc_ok"], "magic_ok": s["magic_ok"],
                    "clock_score": s["clock_score"],
                    "module_px": [float(v) for v in s["module_px"]],
                    "skew_deg": s["skew_deg"], "fields": s["fields"],
                    "preamble": extra, "payload_text": text})
    return out


def score_lattice(reg: dict) -> dict:
    """Absolute scale + warp field from the registration landmark residuals."""
    plus = [m for m in reg["landmarks"] if m["class"] == "plus" and m["ok"]]
    dxs = np.array([m["dx_dots"] for m in plus]) if plus else np.zeros(0)
    dys = np.array([m["dy_dots"] for m in plus]) if plus else np.zeros(0)
    return {
        "px_per_dot_x": reg["px_per_dot_x"], "px_per_dot_y": reg["px_per_dot_y"],
        "scale_err_x_pct": (reg["px_per_dot_x"] / 2.0 - 1.0) * 100.0,
        "scale_err_y_pct": (reg["px_per_dot_y"] / 2.0 - 1.0) * 100.0,
        "scale_note": "print scale x scanner scale, inseparable in one scan; "
                      "home flatbed y-scale is scan-mode dependent (002.0b)",
        "rotation_deg": reg["rotation_deg"], "shear_deg": reg["shear_deg"],
        "n_plus_used": len(plus),
        "residual_rms_dots": reg["residual_rms_dots"],
        "residual_max_dots": reg["residual_max_dots"],
        "plus_dx_range_dots": ([float(dxs.min()), float(dxs.max())]
                               if len(dxs) else None),
        "plus_dy_range_dots": ([float(dys.min()), float(dys.max())]
                               if len(dys) else None),
        "warp_field": [{"name": m["name"], "dx_dots": m["dx_dots"],
                        "dy_dots": m["dy_dots"]} for m in plus],
    }


def _profile_contrast(img: np.ndarray, axis_of_lines: str, period_px: float,
                      white: float, black: float) -> float:
    """Modulation at the grating fundamental, as a fraction of an IDEAL
    full-contrast square wave (whose demod amplitude is (white-black)/pi)."""
    prof = img.mean(axis=1 if axis_of_lines == "h_lines" else 0)
    prof = (white - prof)
    n = len(prof)
    t = np.arange(n)
    amp = np.abs(np.mean((prof - prof.mean())
                         * np.exp(-2j * np.pi * t / period_px)))
    return float(amp / (max(white - black, 1e-3) / np.pi))


def score_grating(scan: dict, e: dict, wm: dict, sub_px: int) -> dict:
    white, black = page_levels(scan, wm, e)
    img = warp_grid(scan, e, "grey", sub_px=sub_px)
    p = e["params"]
    period_px = 2.0 * p["pitch_dots"] * sub_px
    contrast = _profile_contrast(img, p["orientation"], period_px, white, black)
    cov = coverage(img, white, black)
    return {"pitch_dots": p["pitch_dots"], "orientation": p["orientation"],
            "contrast_rel": contrast, "coverage": cov,
            "resolved": bool(contrast >= CONTRAST_RESOLVED),
            "closure": ("ink" if cov > 0.75 else
                        "white" if cov < 0.25 else "open")}


def score_iso_dots(scan: dict, e: dict, wm: dict, sub_px: int) -> dict:
    white, black = page_levels(scan, wm, e)
    bits = nominal_bits_disc1(e)
    pitch = e["params"]["pitch_dots"]
    lk = grid_lock(scan, e, bits, "grey", sub_px=sub_px,
                   max_shift_grid_dots=pitch / 2 - 0.5, min_q=0.02)
    img = lk["img"]
    _, _, _, w, h = grid_of(e)
    span = max(white - black, 1e-3)
    depths = []
    r = max(1, sub_px)  # +-1 grid dot search window around each dot center
    for cy in range(pitch // 2, h - 1, pitch):
        for cx in range(pitch // 2, w - 1, pitch):
            y0, x0 = cy * sub_px, cx * sub_px
            win = img[max(0, y0 - r): y0 + r + 1, max(0, x0 - r): x0 + r + 1]
            depths.append((white - float(win.min())) / span)
    depths = np.array(depths)
    return {"n_dots": int(depths.size), "lock_q": lk["q"], "locked": lk["locked"],
            "median_depth": float(np.median(depths)),
            "survival_frac": float((depths > DOT_SURVIVE).mean()),
            "note": "depth normalized to solid black; threshold "
                    f"{DOT_SURVIVE} = survival"}


def score_line_pairs(scan: dict, e: dict, wm: dict, sub_px: int) -> dict:
    """Fold the profile over the 12-dot pair period: lines at phase 4 and 6,
    gap at 5. Openness 1 = gap fully white, 0 = pair merged."""
    white, black = page_levels(scan, wm, e)
    bits = nominal_bits_disc1(e)
    lk = grid_lock(scan, e, bits, "grey", sub_px=sub_px,
                   max_shift_grid_dots=5.0, min_q=0.02)
    p = e["params"]
    axis = 1 if p["orientation"] == "h_lines" else 0
    prof = lk["img"].mean(axis=axis)
    period = 12 * sub_px
    n = (len(prof) // period) * period
    fold = prof[:n].reshape(-1, period).mean(axis=0)

    def at(phase_dots: float) -> float:
        i = phase_dots * sub_px
        j = int(i) % period
        return float(fold[j])

    v_lines = min(at(4.5), at(6.5))
    v_gap = at(5.5)
    span = max(white - black, 1e-3)
    depth = (white - v_lines) / span
    # denominator floored at 5% of full span: when the lines barely print,
    # openness is meaningless — keep it bounded instead of exploding
    openness = (v_gap - v_lines) / max(white - v_lines, 0.05 * span)
    return {"orientation": p["orientation"], "lock_q": lk["q"],
            "locked": lk["locked"], "line_depth": float(depth),
            "gap_openness": float(openness),
            "pair_resolved": bool(depth > 0.25 and openness > 0.30)}


def score_resolution_row(scan: dict, mf: dict, wm: dict, dpi: int,
                         prefix: str = "") -> dict:
    sub = {300: 4, 600: 2, 1200: 2, 2400: 2}[dpi]
    out: dict = {"grid_dpi": dpi, "px_per_grid_dot_scan": 1200.0 / dpi,
                 "gratings": {}, "iso_dots": None, "line_pairs": {}}
    for nm in ("g1h", "g1v", "g2h", "g2v"):
        e = cc.entry(mf, f"{prefix}res{dpi}/{nm}")
        out["gratings"][nm] = score_grating(scan, e, wm, sub)
    out["iso_dots"] = score_iso_dots(
        scan, cc.entry(mf, f"{prefix}res{dpi}/dots8"), wm, sub)
    for nm in ("lph", "lpv"):
        e = cc.entry(mf, f"{prefix}res{dpi}/{nm}")
        out["line_pairs"][nm] = score_line_pairs(scan, e, wm, sub)
    g = out["gratings"]
    out["verdict_1on1off"] = {o: g[f"g1{o}"]["resolved"] for o in "hv"}
    out["verdict_2on2off"] = {o: g[f"g2{o}"]["resolved"] for o in "hv"}
    if dpi >= 1200:
        out["nyquist_note"] = ("scan gives <=1 px per grid dot at this grid: "
                               "1-on/1-off is at/beyond scan Nyquist — contrast "
                               "is a lower bound, not an MTF")
    return out


def score_line_width(scan: dict, e: dict, wm: dict, sub_px: int) -> dict:
    white, black = page_levels(scan, wm, e)
    img = warp_grid(scan, e, "grey", sub_px=sub_px)
    p = e["params"]
    wd, pitch = p["width_dots"], p["pitch_dots"]
    cov = coverage(img, white, black)
    contrast = _profile_contrast(img, p["orientation"], pitch * sub_px,
                                 white, black)
    apparent = cov * pitch
    return {"width_dots": wd, "orientation": p["orientation"],
            "coverage": cov, "apparent_width_dots": float(apparent),
            "gain_per_edge_dots": float((apparent - wd) / 2.0),
            "contrast_rel": contrast,
            "resolved": bool(contrast >= CONTRAST_RESOLVED and cov < 0.85)}


def score_holes(scan: dict, e: dict, wm: dict, sub_px: int) -> dict:
    white, _ = page_levels(scan, wm, e)
    bits = nominal_bits_disc1(e)          # ink=1, holes are the 0 squares
    n = e["params"]["n_dots"]
    lk = grid_lock(scan, e, bits, "grey", sub_px=sub_px,
                   max_shift_grid_dots=max(1.0, 1.5 * n - 0.5), min_q=0.02)
    img = lk["img"]
    _, _, _, w, h = grid_of(e)
    # solid reference: pixels at least n dots away from any hole
    holes = bits == 0
    far = ~binary_dilation(holes, iterations=max(1, n))
    far_px = np.kron(far, np.ones((sub_px, sub_px), bool))
    v_solid = float(np.median(img[far_px])) if far_px.any() else float(img.min())
    span = max(white - v_solid, 1e-3)
    vals = []
    for y in range(n, h - n, 3 * n):
        for x in range(n, w - n, 3 * n):
            cyx = img[y * sub_px: (y + n) * sub_px, x * sub_px: (x + n) * sub_px]
            vals.append((float(cyx.max()) - v_solid) / span)  # brightest hole px
    vals = np.array(vals)
    return {"n_dots": n, "lock_q": lk["q"], "locked": lk["locked"],
            "n_holes": int(vals.size),
            "median_openness": float(np.median(vals)),
            "open_frac": float((vals > HOLE_OPEN).mean()),
            "open": bool(np.median(vals) > HOLE_OPEN)}


def score_morphology_row(scan: dict, mf: dict, wm: dict, dpi: int,
                         name_fmt: str = "morph{dpi}/{nm}") -> dict:
    sub = 2
    out: dict = {"grid_dpi": dpi, "lines": [], "checkers": [], "holes": []}
    for o in "hv":
        for wd in (1, 2, 3, 4):
            e = cc.entry(mf, name_fmt.format(dpi=dpi, nm=f"lw{wd}{o}"))
            out["lines"].append(score_line_width(scan, e, wm, sub))
    for nn in (1, 2):
        try:
            e = cc.entry(mf, name_fmt.format(dpi=dpi, nm=f"chk{nn}"))
        except KeyError:
            continue
        white, black = page_levels(scan, wm, e)
        img = warp_grid(scan, e, "grey", sub_px=sub)
        cov = coverage(img, white, black)
        # 2-D demod at the checker fundamental (diagonal)
        hpx, wpx = img.shape
        ty, tx = np.mgrid[0:hpx, 0:wpx]
        per = 2 * nn * sub
        z = ((white - img) - (white - img).mean()) \
            * np.exp(-2j * np.pi * (ty / per)) * np.exp(-2j * np.pi * (tx / per))
        amp = float(np.abs(z.mean()) / (max(white - black, 1e-3)))
        out["checkers"].append({"n_dots": nn, "coverage": cov,
                                "closure_delta": float(cov - 0.5),
                                "diag_amp_rel": amp})
    for nn in (1, 2, 3, 4):
        try:
            e = cc.entry(mf, name_fmt.format(dpi=dpi, nm=f"hole{nn}"))
        except KeyError:
            continue
        out["holes"].append(score_holes(scan, e, wm, sub))
    lines_hv = {o: [ln for ln in out["lines"] if ln["orientation"][0] == o]
                for o in "hv"}
    out["summary"] = {
        "min_feature_dots": {
            o: next((ln["width_dots"] for ln in lines_hv[o] if ln["resolved"]),
                    None) for o in "hv"},
        "gain_per_edge_dots_w2to4": {
            o: float(np.mean([ln["gain_per_edge_dots"] for ln in lines_hv[o]
                              if ln["width_dots"] >= 2])) for o in "hv"},
        "min_white_dots": next((hh["n_dots"] for hh in out["holes"]
                                if hh["open"]), None),
    }
    return out


def score_pn_field(scan: dict, e: dict) -> dict:
    """Cell BER of a PN field. 600-grid fields go through the PROVEN v4
    decoder (scanlab.decode_cells: dense warp + stepped y-profile) via
    cc.decode_patch; non-600 grids fall back to affine + GT phase lock +
    median rule (discovery grade — expect ~1-2 pp pessimism at c2/c3 on
    warped sheets; the 007.5 v4-vs-crude arbitration measured the gap)."""
    dpi, _, _, w, h = grid_of(e)
    cell = e["params"]["cell_dots"]
    gt = cc.load_gt(e)
    if dpi == 600 and w == h:
        out = cc.decode_patch(scan, e)
        ber = float(out["ber"])
        rec = {"lock_q": None, "locked": True, "n_cells": int(out["gt_cells"].size),
               "ber_null": out["ber_null"], "null_ok": out["null_ok"],
               "method": "scanlab v4 decode_cells (dense warp + stepped "
                         "y-profile), hard bits"}
    else:
        sub = 2
        lk = grid_lock(scan, e, gt, "grey", sub_px=sub, max_shift_grid_dots=6.0,
                       min_q=0.03)
        m = block_cells(lk["img"], cell * sub)
        gtc = gt[::cell, ::cell][: (m.shape[0]), : (m.shape[1])]
        # threshold at the GT ink-fraction quantile, NOT the median: a median
        # rule forces an exact 50/50 split, so the GT ink-count imbalance
        # becomes a deterministic scan-independent error floor (measured:
        # c4 read exactly 31/4900 = 0.63% on three different prints).
        ink_frac = float(gtc.mean())
        thr = float(np.quantile(m, ink_frac))
        bits = (m < thr).astype(np.uint8)           # ink dark -> 1
        r = cc.ber_with_null(bits, gtc)
        ber = r["ber"]
        rec = {"lock_q": lk["q"], "locked": lk["locked"],
               "n_cells": r["n_cells"], "ber_null": r["ber_null"],
               "null_ok": r["null_ok"],
               "method": "affine + GT phase lock, GT-quantile threshold "
                         "(discovery grade; non-600 grid)"}
    hb = (0.0 if ber in (0.0, 1.0) else
          -ber * math.log2(ber) - (1 - ber) * math.log2(1 - ber))
    cells_per_mm = dpi / cell / 25.4
    return {"grid_dpi": dpi, "cell_dots": cell, "ber": ber,
            "naive_bits_per_cell": float(1.0 - hb),
            "naive_bits_per_mm2": float((1.0 - hb) * cells_per_mm ** 2),
            **rec}


def score_tone(scan: dict, mf: dict, wm: dict) -> dict:
    e_paper = cc.entry(mf, "tone/paper")
    e_solid = cc.entry(mf, "tone/solid")
    v_paper = float(np.median(warp_grid(scan, e_paper, "grey", sub_px=2)))
    v_solid = float(np.median(warp_grid(scan, e_solid, "grey", sub_px=2)))
    span = max(v_paper - v_solid, 1e-3)
    steps = []
    for k in range(1, 10):
        e = cc.entry(mf, f"tone/p{10 * k}")
        gt = cc.load_gt(e)
        lk = grid_lock(scan, e, gt, "grey", sub_px=2, max_shift_grid_dots=6.0,
                       min_q=0.02)
        v = float(lk["img"].mean())
        a_eff = (v_paper - v) / span
        steps.append({"nominal": k / 10.0, "effective_md": float(a_eff),
                      "tvi": float(a_eff - k / 10.0), "lock_q": lk["q"]})
    d_solid = -math.log10(max(v_solid, 1.0) / max(v_paper, 1.0))
    return {"paper_grey": v_paper, "solid_grey": v_solid,
            "solid_density_grey": float(d_solid), "steps": steps,
            "tvi_at_50": steps[4]["tvi"],
            "note": "Murray-Davies effective coverage vs seeded random-dot "
                    "nominal; paper/solid anchors from the wedge itself"}


def _fft_peaks(img: np.ndarray, sub_px: int, dpi: int, *, n_peaks: int = 6,
               lpi_lo: float = 110.0, lpi_hi: float = 320.0,
               exclude_axis_deg: float = 7.0) -> list[dict]:
    """Top OFF-AXIS spectral peaks of a patch in printer units (lpi, deg).

    Bins within exclude_axis_deg of the 0/90 deg axes are masked: the c3 cell
    lattice and its harmonics live on-axis, halftone screens live at rotated
    angles. Band + exclusion validated on the 007.0 home DISC-1 composite:
    the known M281 re-screen reads 164 lpi @ +/-14 deg at ~500-700x the band
    median; scanner-common residual texture (~120-126 lpi) stays <300x."""
    a = img.astype(np.float64)
    a -= a.mean()
    wy = np.hanning(a.shape[0])[:, None]
    wx = np.hanning(a.shape[1])[None, :]
    P = np.abs(np.fft.fftshift(np.fft.fft2(a * wy * wx))) ** 2
    pitch_mm = 25.4 / (dpi * sub_px)
    fy = np.fft.fftshift(np.fft.fftfreq(a.shape[0], d=pitch_mm))
    fx = np.fft.fftshift(np.fft.fftfreq(a.shape[1], d=pitch_mm))
    FX, FY = np.meshgrid(fx, fy)
    R = np.hypot(FX, FY) * 25.4          # lpi
    ang = np.degrees(np.arctan2(FY, FX)) % 90.0
    off_axis = np.minimum(ang, 90.0 - ang) > exclude_axis_deg
    band = (R >= lpi_lo) & (R <= lpi_hi) & (FY >= 0) & off_axis
    loc = (P == maximum_filter(P, size=9)) & band
    idx = np.argsort(P[loc])[::-1][:n_peaks]
    ys, xs = np.nonzero(loc)
    med = float(np.median(P[band])) + 1e-12
    out = []
    for i in idx:
        y, x = ys[i], xs[i]
        out.append({"lpi": float(R[y, x]),
                    "angle_deg": float(math.degrees(math.atan2(FY[y, x],
                                                               FX[y, x]))),
                    "power_rel_median": float(P[y, x] / med)})
    return out


PLANE_CHANNEL = {"C": "r", "M": "g", "Y": "b", "K": "grey"}


def score_canaries(scan: dict, mf: dict, wm: dict) -> dict:
    color = scan["kind"] == "color"
    out: dict = {"scan_kind": scan["kind"], "solids": {}, "cmy_c3": None,
                 "cm_overlap": None}
    chans = ("r", "g", "b") if color else ("grey",)
    for p in "KCMY":
        e = cc.entry(mf, f"canary/solid_{p}")
        dpi, x0, y0, w, h = grid_of(e)
        img = {ch: warp_grid(scan, e, ch, sub_px=2) for ch in chans}
        cx = np.array([x0 + w / 2.0])
        cy = np.array([y0 + h / 2.0])
        dens = {ch: float(-np.log10(
            max(float(np.median(img[ch])), 1.0)
            / max(float(cc.white_at(wm, cx, cy, ch)[0]), 1.0)))
            for ch in chans}
        rec: dict = {"density": dens}
        if color:
            comp = PLANE_CHANNEL[p]
            others = [dens[ch] for ch in ("r", "g", "b")
                      if ch != comp] if p != "K" else []
            rec["present"] = bool((dens[comp] if p != "K"
                                   else min(dens.values())) > 0.15)
            if p != "K":
                rec["purity"] = float(dens[comp]
                                      / max(sum(dens.values()), 1e-6))
            else:
                rec["neutrality_spread"] = float(max(dens.values())
                                                 - min(dens.values()))
        else:
            rec["present"] = bool(list(dens.values())[0] > 0.10)
            rec["note"] = "grey scan: presence only, no hue separation"
        out["solids"][p] = rec

    # CMY c3 composite: per-plane BER in that plane's complementary channel
    comp: dict = {"planes": {}, "screen_peaks": {}}
    for p in "CMY":
        e = cc.entry(mf, f"canary/cmy_c3_{p}")
        gt = cc.load_gt(e)
        ch = PLANE_CHANNEL[p] if color else "grey"
        lk = grid_lock(scan, e, gt, ch, sub_px=2, max_shift_grid_dots=6.0,
                       min_q=0.02)
        m = block_cells(lk["img"], 3 * 2)
        bits = (m < np.median(m)).astype(np.uint8)
        gtc = gt[::3, ::3][: bits.shape[0], : bits.shape[1]]
        r = cc.ber_with_null(bits, gtc)
        comp["planes"][p] = {"channel": ch, "lock_q": lk["q"],
                             "locked": lk["locked"], "ber": r["ber"],
                             "ber_null": r["ber_null"], "null_ok": r["null_ok"]}
        if color:
            comp["screen_peaks"][p] = _fft_peaks(lk["img"], 2, 600)
    if not color:
        e = cc.entry(mf, "canary/cmy_c3_C")
        img = warp_grid(scan, e, "grey", sub_px=2)
        comp["screen_peaks"]["grey"] = _fft_peaks(img, 2, 600)
    comp["note"] = ("per-plane decode in the complementary channel, NO "
                    "crosstalk unmix — BERs are pessimistic bounds; "
                    "screen peaks: content lattice = 200 cpi (c3) + harmonics,"
                    " anything else is the RIP")
    out["cmy_c3"] = comp

    # C+M overlap pair: preserved (overprint) vs knocked out
    ec = cc.entry(mf, "canary/cm_overlap_C")
    em = cc.entry(mf, "canary/cm_overlap_M")
    _, xc, yc, w, h = grid_of(ec)
    _, xm, _, _, _ = grid_of(em)
    ov_w = int(xc + w - xm)              # overlap width in dots (5 mm)
    a, b, c, d, ee, f = scan["affine"]

    def zone_mean(x0: float, wz: float, ch: str) -> float:
        gy, gx = np.mgrid[8: h - 8, 8: int(wz) - 8]
        xd, yd = x0 + gx, yc + gy
        v = map_coordinates(scan["channels"][ch],
                            [d * xd + ee * yd + f, a * xd + b * yd + c],
                            order=1, mode="nearest", output=np.float32)
        return float(np.median(v))

    zones = {"C_only": (xc, xm - xc), "overlap": (xm, ov_w),
             "M_only": (xc + w, xm + w - (xc + w))}
    zr: dict = {"zones": {}}
    for zn, (zx, zw) in zones.items():
        dens = {}
        for ch in chans:
            wl = float(cc.white_at(wm, np.array([zx + zw / 2]),
                                   np.array([yc + h / 2]), ch)[0])
            dens[ch] = float(-math.log10(max(zone_mean(zx, zw, ch), 1.0)
                                         / max(wl, 1.0)))
        zr["zones"][zn] = dens
    if color:
        dr_c = zr["zones"]["C_only"]["r"]
        dr_m = zr["zones"]["M_only"]["r"]
        dr_o = zr["zones"]["overlap"]["r"]
        dg_c = zr["zones"]["C_only"]["g"]
        dg_m = zr["zones"]["M_only"]["g"]
        dg_o = zr["zones"]["overlap"]["g"]
        pres_c = (dr_o - dr_m) / max(dr_c - dr_m, 1e-6)   # C under the overlap?
        pres_m = (dg_o - dg_c) / max(dg_m - dg_c, 1e-6)   # M over the overlap?
        zr["preserve_index_C_under"] = float(pres_c)
        zr["preserve_index_M_over"] = float(pres_m)
        zr["verdict"] = ("overlap_preserved" if pres_c > 0.6 and pres_m > 0.6
                         else "knockout" if pres_c < 0.25 or pres_m < 0.25
                         else "partial")
    else:
        dg_o = zr["zones"]["overlap"]["grey"]
        dg_s = max(zr["zones"]["C_only"]["grey"], zr["zones"]["M_only"]["grey"])
        zr["verdict"] = ("overlap_preserved(grey)" if dg_o > 1.3 * dg_s
                         else "indeterminate(grey)")
    out["cm_overlap"] = zr
    return out


def score_margins(scan: dict, mf: dict) -> dict:
    out: dict = {"edges": {}}
    for edge in ("top", "bottom", "left", "right"):
        ticks = []
        for gap in range(4, 13):
            try:
                e = cc.entry(mf, f"mt_{edge}_{gap}")
            except KeyError:
                continue
            img = warp_grid(scan, e, "grey", sub_px=2, margin_grid_dots=8)
            m = 8 * 2
            core = img[m + 8: -m - 8, m + 8: -m - 8]   # tick minus 4-dot rim
            ring = np.concatenate([img[:m].ravel(), img[-m:].ravel(),
                                   img[:, :m].ravel(), img[:, -m:].ravel()])
            white = float(np.percentile(ring, 85))
            black = scan["black"]
            cov = coverage(core, white, black)
            status = ("present" if cov >= TICK_PRESENT else
                      "partial" if cov >= TICK_PARTIAL else "absent")
            ticks.append({"gap_mm": gap, "coverage": float(cov),
                          "status": status})
        present = [t["gap_mm"] for t in ticks if t["status"] == "present"]
        absent = [t["gap_mm"] for t in ticks if t["status"] == "absent"]
        out["edges"][edge] = {
            "ticks": ticks,
            "min_gap_present_mm": min(present) if present else None,
            "max_gap_absent_mm": max(absent) if absent else None,
        }
    return out


def _demod_residual(sig: np.ndarray, period_px: float, sub_px: int
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(pos_dots, r_dots, amp) — residual displacement of a periodic grating
    vs its nominal grid position, by quadrature demodulation + unwrap."""
    t = np.arange(len(sig))
    z = (sig - sig.mean()) * np.exp(-2j * np.pi * t / period_px)
    k = max(3, int(round(4 * period_px)))
    ker = np.ones(k) / k
    zs = np.convolve(z, ker, mode="same")
    amp = np.abs(zs)
    phase = np.unwrap(np.angle(zs))
    r_px = -phase * period_px / (2 * np.pi)
    trim = k
    sl = slice(trim, len(sig) - trim)
    return (t[sl] / sub_px, (r_px[sl] - np.median(r_px[sl])) / sub_px, amp[sl])


def score_transport_strip(scan: dict, e: dict, axis: str) -> dict:
    """r(y) / r(x) from a 3-on/3-off phase grating (period 6 dots)."""
    sub = 2
    img = warp_grid(scan, e, "grey", sub_px=sub)
    sig = img.mean(axis=1) if axis == "y" else img.mean(axis=0)
    sig = -sig                              # ink positive
    pos, r, amp = _demod_residual(sig, 6.0 * sub, sub)
    good = amp > 0.2 * np.median(amp)
    r = np.interp(pos, pos[good], r[good])
    # decimate to 1 sample per 2 dots for the step detector
    dec = 2 * sub
    nn = (len(r) // dec) * dec
    r2 = r[:nn].reshape(-1, dec).mean(axis=1)
    p2 = pos[:nn].reshape(-1, dec).mean(axis=1)
    r_med = median_filter(r2, size=5, mode="nearest")
    steps = cc.detect_steps(p2, r_med, thresh_dots=0.25)
    slope, icpt = np.polyfit(p2, r2, 1)
    detr = r2 - (slope * p2 + icpt)
    return {"axis": axis, "n_samples": int(len(r2)),
            "span_dots": float(p2[-1] - p2[0]),
            "scale_residual_pct": float(slope * 100.0),
            "p2p_dots_detrended": float(np.ptp(detr)),
            "rms_dots_detrended": float(detr.std()),
            "n_steps": len(steps),
            "steps": [{"pos_dots": s[0], "mag_dots": s[1]} for s in steps],
            "note": "single scan: printer wander and scanner transport are "
                    "entangled; home-flatbed y steps + 18.63 mm CCD comb are "
                    "scanner-side (002.0b)"}


# ---------------------------------------------------------------------------
# page-2 registration (4 corner marks only — below cal_core's 6-landmark gate)
# ---------------------------------------------------------------------------

def register_corners_only(scan: dict, mf_page: dict) -> dict:
    """Orientation from cal_core, then a 4-corner-only affine refinement."""
    reg = cc.register(scan, mf_page, refine=False)
    lms = [lm for lm in cc._landmark_defs(mf_page, use_quads=False)
           if lm["class"] == "corner"]
    coef = scan["affine"]
    meas: list[dict] = []
    for _ in range(2):
        meas = cc._measure_landmarks(scan, coef, lms)
        good = [m for m in meas if m["ok"]]
        if len(good) < 3:
            raise cc.RegistrationError(
                f"only {len(good)} corner landmarks locked on page 2")
        P = np.array([[m["x"] + m["w"] / 2, m["y"] + m["h"] / 2] for m in good])
        Q = cc.affine_apply(coef, P + np.array([[m["dx_dots"], m["dy_dots"]]
                                                for m in good]))
        coef, _ = cc._fit_affine(P, Q)
    scan["affine"] = coef
    meas = cc._measure_landmarks(scan, coef, lms)
    res = [math.hypot(m["dx_dots"], m["dy_dots"]) for m in meas if m["ok"]]
    reg.update(cc.affine_stats(coef))
    reg["affine"] = [float(v) for v in coef]
    reg["n_landmarks_used"] = len(res)
    reg["n_landmarks_total"] = len(meas)
    reg["residual_rms_dots"] = float(np.sqrt(np.mean(np.square(res)))) if res else None
    reg["residual_max_dots"] = float(max(res)) if res else None
    reg["landmarks"] = [{**{k: m[k] for k in ("name", "class", "dx_dots",
                                              "dy_dots", "q", "ok")}}
                        for m in meas]
    reg["note"] = "corners-only refinement (page 2 has no plus lattice)"
    scan["registration"] = reg
    return reg


# ---------------------------------------------------------------------------
# page drivers
# ---------------------------------------------------------------------------

def analyze_page1(scan_path: str, mf_all: dict) -> dict:
    mf = page_manifest(mf_all, 1)
    scan = cc.load_scan(scan_path)
    reg = cc.register(scan, mf)
    wm = cc.white_model(scan)
    rep: dict = {
        "scan": {"path": scan["path"], "sha256": scan["sha256"],
                 "kind": scan["kind"], "shape_px": list(scan["grey"].shape)},
        "registration": {k: reg[k] for k in
                         ("orientation", "px_per_dot_x", "px_per_dot_y",
                          "rotation_deg", "shear_deg", "n_landmarks_used",
                          "n_landmarks_total", "residual_rms_dots",
                          "residual_max_dots")},
        "strips": score_strips(scan),
        "lattice": score_lattice(reg),
        "resolution": {f"res{dpi}": score_resolution_row(scan, mf, wm, dpi)
                       for dpi in (300, 600, 1200)},
        "morphology": {f"morph{dpi}": score_morphology_row(scan, mf, wm, dpi)
                       for dpi in (600, 1200)},
        "pn": {nm: score_pn_field(scan, cc.entry(mf, nm))
               for nm in [f"pn600/c{c}" for c in (1, 2, 3, 4, 5, 6)]
               + ["pn1200/c2", "pn1200/c3"]},
        "tone": score_tone(scan, mf, wm),
        "canaries": score_canaries(scan, mf, wm),
        "margins": score_margins(scan, mf),
        "transport": {
            "r_y": score_transport_strip(scan, cc.entry(mf, "rY_strip_left"), "y"),
            "r_x": score_transport_strip(scan, cc.entry(mf, "rX_strip_bottom"), "x"),
        },
    }
    return rep


def analyze_page2(scan_path: str, mf_all: dict) -> dict:
    mf = page_manifest(mf_all, 2)
    scan = cc.load_scan(scan_path)
    reg = register_corners_only(scan, mf)
    wm = cc.white_model(scan)
    rep: dict = {
        "scan": {"path": scan["path"], "sha256": scan["sha256"],
                 "kind": scan["kind"], "shape_px": list(scan["grey"].shape)},
        "registration": {k: reg.get(k) for k in
                         ("orientation", "px_per_dot_x", "px_per_dot_y",
                          "rotation_deg", "shear_deg", "n_landmarks_used",
                          "residual_rms_dots", "residual_max_dots", "note")},
        "strips": score_strips(scan),
        "resolution": {f"res{dpi}": score_resolution_row(scan, mf, wm, dpi,
                                                         prefix="p2/")
                       for dpi in (1200, 2400)},
        "lw1200": [score_line_width(
            scan, cc.entry(mf, f"p2/lw1200/lw{w}{o}"), wm, 2)
            for o in "hv" for w in (1, 2, 3, 4)],
        "pn": {nm: score_pn_field(scan, cc.entry(mf, nm))
               for nm in ("p2/pn1200/c2", "p2/pn1200/c3", "p2/pn1200/c4",
                          "p2/pn600/c3_ctl")},
    }
    return rep


# ---------------------------------------------------------------------------
# console rendering
# ---------------------------------------------------------------------------

def _fmt_pct(v: float) -> str:
    return f"{100.0 * v:.2f}%"


def print_report(rep: dict, page: int) -> None:
    print(f"\n===== DISC-1 page {page}: {rep['scan']['path']} "
          f"({rep['scan']['kind']}) =====")
    r = rep["registration"]
    print(f"reg: px/dot x={r['px_per_dot_x']:.5f} y={r['px_per_dot_y']:.5f} "
          f"rot={r['rotation_deg']:.3f} deg shear={r['shear_deg']:.3f} deg "
          f"rms={r['residual_rms_dots']:.2f} max={r['residual_max_dots']:.2f} dots")
    for s in rep["strips"]:
        f = s["fields"]
        pre = s.get("preamble") or {}
        print(f"strip: crc={s['crc_ok']} PR={f.get('PR')!r} RD={f.get('RD')} "
              f"RE={f.get('RE')} PS={f.get('PS')} "
              + (f"RQ={[pre.get(k) for k in ('RQ300', 'RQ600', 'RQ1200', 'RQ2400')]} "
                 if pre else ""))
    if "lattice" in rep:
        lt = rep["lattice"]
        print(f"lattice: scale err x={lt['scale_err_x_pct']:+.3f}% "
              f"y={lt['scale_err_y_pct']:+.3f}%  plus dx range "
              f"{lt['plus_dx_range_dots']} dy range {lt['plus_dy_range_dots']} dots")
    for key, row in rep.get("resolution", {}).items():
        g = row["gratings"]
        d = row["iso_dots"]
        lp = row["line_pairs"]
        print(f"{key}: 1on1off h/v contrast {g['g1h']['contrast_rel']:.2f}/"
              f"{g['g1v']['contrast_rel']:.2f} (cov {g['g1h']['coverage']:.2f}/"
              f"{g['g1v']['coverage']:.2f})  2on2off {g['g2h']['contrast_rel']:.2f}/"
              f"{g['g2v']['contrast_rel']:.2f}  iso-dot surv "
              f"{d['survival_frac']:.2f} depth {d['median_depth']:.2f}  "
              f"pair-gap open h/v {lp['lph']['gap_openness']:.2f}/"
              f"{lp['lpv']['gap_openness']:.2f}")
    for key, row in rep.get("morphology", {}).items():
        s = row["summary"]
        ln = {(x["width_dots"], x["orientation"][0]): x for x in row["lines"]}
        gains = " ".join(f"w{w}{o}:{ln[(w, o)]['gain_per_edge_dots']:+.2f}"
                         for o in "hv" for w in (1, 2, 3, 4))
        print(f"{key}: min-feature h/v {s['min_feature_dots']['h']}/"
              f"{s['min_feature_dots']['v']} dots  gain/edge(w2-4) "
              f"h {s['gain_per_edge_dots_w2to4']['h']:+.2f} "
              f"v {s['gain_per_edge_dots_w2to4']['v']:+.2f}  "
              f"min-white {s['min_white_dots']}  [{gains}]")
        for hh in row["holes"]:
            print(f"   hole{hh['n_dots']}: openness {hh['median_openness']:.2f} "
                  f"open_frac {hh['open_frac']:.2f}")
        for ck in row["checkers"]:
            print(f"   chk{ck['n_dots']}: cov {ck['coverage']:.3f} "
                  f"(delta {ck['closure_delta']:+.3f}) amp {ck['diag_amp_rel']:.3f}")
    if "pn" in rep:
        for nm, p in rep["pn"].items():
            meth = "v4" if p["method"].startswith("scanlab v4") else \
                f"crude lock q={p['lock_q']:.2f}"
            print(f"pn {nm}: BER {_fmt_pct(p['ber'])} (null "
                  f"{p['ber_null']:.3f} ok={p['null_ok']}, {meth}) "
                  f"naive {p['naive_bits_per_cell']:.3f} b/cell = "
                  f"{p['naive_bits_per_mm2']:.1f} b/mm2")
    if "lw1200" in rep:
        for x in rep["lw1200"]:
            print(f"p2 lw1200 w{x['width_dots']}{x['orientation'][0]}: cov "
                  f"{x['coverage']:.3f} gain/edge {x['gain_per_edge_dots']:+.2f} "
                  f"contrast {x['contrast_rel']:.2f}")
    if "tone" in rep:
        t = rep["tone"]
        curve = " ".join(f"{s['nominal']:.0%}->{s['effective_md']:.2f}"
                         for s in t["steps"])
        print(f"tone: solid D(grey) {t['solid_density_grey']:.2f}  TVI@50 "
              f"{t['tvi_at_50']:+.3f}  [{curve}]")
    if "canaries" in rep and rep["canaries"]:
        cn = rep["canaries"]
        for p, s in cn["solids"].items():
            print(f"canary solid {p}: present={s['present']} density={ {k: round(v, 3) for k, v in s['density'].items()} }")
        for p, s in cn["cmy_c3"]["planes"].items():
            print(f"canary cmy_c3 {p} ({s['channel']}): BER {_fmt_pct(s['ber'])} "
                  f"null_ok={s['null_ok']} lock q={s['lock_q']:.2f}")
        for p, pk in cn["cmy_c3"]["screen_peaks"].items():
            tops = ", ".join(f"{q['lpi']:.0f}lpi@{q['angle_deg']:.0f}deg "
                             f"x{q['power_rel_median']:.0f}" for q in pk[:3])
            print(f"canary cmy_c3 {p} screen peaks: {tops}")
        ov = cn["cm_overlap"]
        print(f"canary C+M overlap: verdict={ov['verdict']} "
              + (f"preserve C-under={ov['preserve_index_C_under']:.2f} "
                 f"M-over={ov['preserve_index_M_over']:.2f}"
                 if "preserve_index_C_under" in ov else ""))
    if "margins" in rep:
        for edge, ed in rep["margins"]["edges"].items():
            print(f"margin {edge}: min gap present {ed['min_gap_present_mm']} mm "
                  f"(max absent {ed['max_gap_absent_mm']})  "
                  + " ".join(f"{t['gap_mm']}:{t['status'][:4]}"
                             for t in ed["ticks"]))
    if "transport" in rep:
        for ax, tr in rep["transport"].items():
            print(f"{ax}: scale residual {tr['scale_residual_pct']:+.3f}%  "
                  f"p2p {tr['p2p_dots_detrended']:.2f} rms "
                  f"{tr['rms_dots_detrended']:.2f} dots  steps {tr['n_steps']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="DISC-1 full-block analyzer")
    ap.add_argument("p1_scan", help="page-1 scan PNG (1200 dpi)")
    ap.add_argument("p2_scan", nargs="?", default=None,
                    help="optional page-2 scan PNG")
    ap.add_argument("--json", default=None, help="write full report JSON here")
    ap.add_argument("--manifest", default=str(MANIFEST_PATH))
    args = ap.parse_args()

    mf_all = cc.load_manifest(args.manifest)
    report: dict = {"artifact": "disc1", "manifest": args.manifest,
                    "page1": analyze_page1(args.p1_scan, mf_all)}
    print_report(report["page1"], 1)
    if args.p2_scan:
        report["page2"] = analyze_page2(args.p2_scan, mf_all)
        print_report(report["page2"], 2)
    if args.json:
        cc.save_report(report, args.json)
        print(f"\nreport -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

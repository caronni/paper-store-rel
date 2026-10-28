#!/usr/bin/env python
"""cal_geometry — geometry & warp family analyzer for experiment 002 (CAL-1).

Family: TRANSPORT (ANALYZER-CONTRACT.md §8). Owns the curated report keys
`geometry.*` and `channel_params.{banding, transport_steps, warp_rms_dots,
plane_offsets}` plus canary E (rescale). Raw detail goes to
`families.transport`.

Measurements (grey scan primary — K geometry rule; color scan only for the
C/M/Y registration quads and a scanner-axis cross-check):

  (a) rulers       tick-pitch regression -> absolute print scale per axis,
                   skew / anisotropy; machine-readable inch indices -> clip
                   map, printable extent, engine-margin upper bounds
  (b) warp field   corner marks + plus lattice + K reg-quads residual vectors
                   (from the core registration report) -> RMS / max in dots
  (c) phase strip  quadrature demodulation of the left 6-dot grating per
                   12-dot (24-scan-row) Hann window -> unwrapped phase(y) ->
                   transport function r(y), step catalog via
                   scanlab.detect_steps (imported FROM cal_core, per contract)
  (d) banding      K banding strip row-mean density, GT-regressed residual ->
                   FFT -> banding periods/amplitudes 2-120 mm + permutation
                   control

Reuse decision: proven exp-001 primitives (detect_steps, xcorr_offset,
median-filter conventions) are imported FROM cal_core re-exports rather than
copied — single-sourced provenance, exactly the contract's preferred path.

Determinism: the ONLY randomness is the banding permutation control, drawn
from paperholo.modulation.rng(gen_calpage.SEED,
b"exp002/geometry/banding-permctl") per CLAUDE.md.

Controls discipline (001.2 rule): ruler index decode carries a
shifted-position decode control; the phase demod carries an off-carrier
amplitude control; the banding spectrum carries a seeded permutation control;
canary E is emitted via cc.canary_verdict (never a bare boolean).
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402
import gen_calpage  # noqa: E402  (SEED + ruler geometry provenance)
from paperholo.modulation import rng  # noqa: E402

# --- ruler geometry constants (source: gen_calpage.ps_rulers, dot-exact) ----
TICK_PITCH_DOTS = cc.HW_DPI // 10   # /TKX HWX 10 idiv -> 60 dots = 0.1 inch
MODULE_DOTS = 6                     # 6x6-dot index modules at 12-dot pitch
PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
DOTS_TO_MM = 25.4 / cc.HW_DPI

# phase strip demodulation (spec: ~24-scan-row windows = 12 dots = 2 periods)
PHASE_WIN_DOTS = 12.0
PHASE_HOP_DOTS = 3.0     # matches exp-001 residual_y_profile 1-cell-row hop
STEP_DECIMATE = 4        # report-profile decimation (12-dot samples); the
#                          step CATALOG itself runs on 3-dot samples (001.4)

# 001.4 transport-step catalog reference values (task brief) for comparison
REF_001_STEP_RANGE_DOTS = (0.25, 1.5)
REF_001_STEPS_PER_40MM = (3, 7)


# ---------------------------------------------------------------------------
# (a) rulers
# ---------------------------------------------------------------------------

def _measure_ticks(prof: np.ndarray, sub: int, origin_dots: float,
                   first_center_dots: float, pitch_dots: float, n_ticks: int,
                   search_dots: float = 20.0) -> list[dict]:
    """Locate each tick's centroid in a 1-D ink-positive profile.

    prof[i] is at layout position origin_dots + i/sub. Returns per-tick
    dicts: i, nominal_dots, measured_dots, amp, present.
    """
    out = []
    for i in range(n_ticks):
        nom = first_center_dots + i * pitch_dots
        c0 = int(round((nom - origin_dots) * sub))
        lo = max(c0 - int(search_dots * sub), 0)
        hi = min(c0 + int(search_dots * sub) + 1, prof.size)
        w = prof[lo:hi]
        k = int(np.argmax(w))
        floor = float(np.median(np.concatenate([w[:5], w[-5:]])))
        amp = float(w[k] - floor)
        a = max(k - 5 * sub, 0)
        b = min(k + 5 * sub + 1, w.size)
        wgt = np.clip(w[a:b] - floor - 0.3 * amp, 0.0, None)
        cen = float((np.arange(a, b) * wgt).sum() / wgt.sum()) if wgt.sum() > 0 else float(k)
        out.append({"i": i, "nominal_dots": float(nom),
                    "measured_dots": float(origin_dots + (lo + cen) / sub),
                    "amp": amp})
    med_amp = float(np.median([t["amp"] for t in out]))
    for t in out:
        t["present"] = bool(med_amp > 3.0 and t["amp"] > 0.35 * med_amp)
    return out


def _robust_scale_fit(ticks: list[dict]) -> dict:
    """measured = alpha * nominal + beta over present ticks, 3-sigma clipped."""
    pts = [(t["nominal_dots"], t["measured_dots"]) for t in ticks if t["present"]]
    if len(pts) < 8:
        return {"alpha": None, "n_present": len(pts), "error": "too few ticks"}
    n = np.array([p[0] for p in pts])
    m = np.array([p[1] for p in pts])
    keep = np.ones(n.size, bool)
    r = np.zeros(n.size)
    slope, icpt = 1.0, 0.0
    for _ in range(3):
        A = np.column_stack([n[keep], np.ones(int(keep.sum()))])
        (slope, icpt), *_ = np.linalg.lstsq(A, m[keep], rcond=None)
        r = m - (slope * n + icpt)
        s = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep]))) + 1e-9
        keep = np.abs(r - np.median(r[keep])) < 3.0 * s
    return {"alpha": float(slope), "intercept_dots": float(icpt),
            "resid_rms_dots": float(np.sqrt(np.mean(r[keep] ** 2))),
            "n_used": int(keep.sum()), "n_present": int(n.size)}


def _box_mean(scan: dict, x_dots: float, y_dots: float, n_dots: int = MODULE_DOTS) -> float:
    return float(cc.warp_channel(scan, "grey", x_dots, y_dots, n_dots, n_dots,
                                 sub=2).mean())


def _decode_index_block(scan: dict, positions: dict[str, tuple[float, float]],
                        expected: int) -> dict:
    """Decode one 5-module ruler index block (start + 4 bits LSB + parity).

    positions: {'start': (x,y), 'bit0'..'bit3', 'parity'} in layout dots
    (module top-left corners). Even parity over value bits + parity module.
    """
    white = scan["white"]
    black = scan["black"]
    v_start = _box_mean(scan, *positions["start"])
    if v_start > white - 0.35 * (white - black):
        return {"ok": False, "reason": "start module not dark",
                "expected": expected, "value": None, "parity_ok": None}
    thr = 0.5 * (white + v_start)
    value = 0
    for b in range(4):
        if _box_mean(scan, *positions[f"bit{b}"]) < thr:
            value |= 1 << b
    pbit = 1 if _box_mean(scan, *positions["parity"]) < thr else 0
    parity_ok = (bin(value).count("1") + pbit) % 2 == 0
    return {"ok": bool(parity_ok and value == expected), "expected": expected,
            "value": int(value), "parity_ok": bool(parity_ok)}


def analyze_ruler_top(scan: dict, shift_dots: float = 0.0) -> dict:
    """Top ruler (x axis): tick regression + index decode.

    shift_dots != 0 is the DECODE CONTROL: sampling the index blocks at a
    deliberately wrong x must fail (start module lands on blank paper).
    """
    e = cc.entry(scan["manifest"], "ruler_top")
    n_ticks = e["params"]["ticks"]
    rx0, ry0 = e["x_dots"], e["y_dots"]
    sub = 2
    x0 = rx0 - 25.0
    w = (n_ticks - 1) * TICK_PITCH_DOTS + 3 + 50
    # tick-only band: y in [RY0+5, RY0+18] — below the 3-dot baseline, above
    # the index-module row at RY0+54; every tick is >= 20 dots long.
    band = cc.warp_channel(scan, "grey", x0, ry0 + 5, w, 13, sub=sub)
    white, _, _ = cc.levels(band)
    prof = (white - band).mean(axis=0)
    ticks = _measure_ticks(prof, sub, x0, rx0 + 1.5, TICK_PITCH_DOTS, n_ticks)
    fit = _robust_scale_fit(ticks)
    indices = {}
    for i in range(0, n_ticks, 10):
        tx = rx0 + i * TICK_PITCH_DOTS + shift_dots
        ym = ry0 + 54
        pos = {"start": (tx + 6, ym), "parity": (tx + 66, ym),
               **{f"bit{b}": (tx + 18 + 12 * b, ym) for b in range(4)}}
        indices[i // 10] = _decode_index_block(scan, pos, expected=i // 10)
    return {"axis": "x", "ticks": ticks, "fit": fit, "indices": indices,
            "n_present": sum(t["present"] for t in ticks), "n_ticks": n_ticks,
            "missing": [t["i"] for t in ticks if not t["present"]]}


def analyze_ruler_left(scan: dict, shift_dots: float = 0.0) -> dict:
    """Left ruler (y axis): tick regression + index decode (control as top)."""
    e = cc.entry(scan["manifest"], "ruler_left")
    n_ticks = e["params"]["ticks"]
    rxl, ry1 = e["x_dots"], e["y_dots"]
    sub = 2
    y0 = ry1 - 25.0
    h = (n_ticks - 1) * TICK_PITCH_DOTS + 3 + 50
    # tick-only band: x in [RXL+5, RXL+18] — right of the baseline, left of
    # the index-module column at RXL+24.
    band = cc.warp_channel(scan, "grey", rxl + 5, y0, 13, h, sub=sub)
    white, _, _ = cc.levels(band)
    prof = (white - band).mean(axis=1)
    ticks = _measure_ticks(prof, sub, y0, ry1 + 1.5, TICK_PITCH_DOTS, n_ticks)
    fit = _robust_scale_fit(ticks)
    indices = {}
    for i in range(0, n_ticks, 10):
        ty = ry1 + i * TICK_PITCH_DOTS + shift_dots
        xm = rxl + 24
        pos = {"start": (xm, ty + 12), "parity": (xm, ty + 72),
               **{f"bit{b}": (xm, ty + 24 + 12 * b) for b in range(4)}}
        indices[i // 10] = _decode_index_block(scan, pos, expected=i // 10)
    return {"axis": "y", "ticks": ticks, "fit": fit, "indices": indices,
            "n_present": sum(t["present"] for t in ticks), "n_ticks": n_ticks,
            "missing": [t["i"] for t in ticks if not t["present"]]}


def _index_summary(rul: dict) -> dict:
    idx = rul["indices"]
    ok = [k for k, v in idx.items() if v["ok"]]
    return {"n_blocks": len(idx), "n_ok": len(ok), "ok_indices": ok,
            "failed": {k: v for k, v in idx.items() if not v["ok"]} or None}


def clip_map_and_margins(scan: dict, rul_top: dict, rul_left: dict) -> dict:
    """Which ticks/indices survived -> printable extent; engine-margin upper
    bounds from the outermost VERIFIED printed features (corner marks via
    registration, ruler baselines via tick presence)."""
    man = scan["manifest"]
    reg = scan["registration"]
    corners_seen = sorted(c["n_sat"] for c in reg["corners_found"])
    cm = [cc.entry(man, f"corner_{t}") for t in ("tl", "tr", "br", "bl")]
    ink_x0 = min(e["x_dots"] for e in cm)                     # 175 dots
    ink_x1 = max(e["x_dots"] + e["w_dots"] for e in cm)       # 4786 dots
    ink_y0 = min(e["y_dots"] for e in cm)
    ink_y1 = max(e["y_dots"] + e["h_dots"] for e in cm)
    left_baseline_x = cc.entry(man, "ruler_left")["x_dots"]   # 142 dots
    margins = {
        "left": round(min(ink_x0, left_baseline_x) * DOTS_TO_MM, 2),
        "top": round(ink_y0 * DOTS_TO_MM, 2),
        "right": round(PAGE_W_MM - ink_x1 * DOTS_TO_MM, 2),
        "bottom": round(PAGE_H_MM - ink_y1 * DOTS_TO_MM, 2),
    }
    clipped = (rul_top["missing"] or rul_left["missing"]
               or len(corners_seen) < 4)
    kx0, ky0, kx1, ky1 = man["content_bounds_mm"]
    return {
        "corners_found_n_sat": corners_seen,
        "ruler_top_ticks": f"{rul_top['n_present']}/{rul_top['n_ticks']}",
        "ruler_left_ticks": f"{rul_left['n_present']}/{rul_left['n_ticks']}",
        "ruler_top_missing": rul_top["missing"],
        "ruler_left_missing": rul_left["missing"],
        "indices_top": _index_summary(rul_top),
        "indices_left": _index_summary(rul_left),
        "clipping_detected": bool(clipped),
        "printable_extent_verified_mm": {
            "x": [round(min(ink_x0, left_baseline_x) * DOTS_TO_MM, 2),
                  round(ink_x1 * DOTS_TO_MM, 2)],
            "y": [round(ink_y0 * DOTS_TO_MM, 2), round(ink_y1 * DOTS_TO_MM, 2)]},
        "engine_margins_mm_upper_bounds": margins,
        "manifest_keepout_mm": [kx0, ky0, PAGE_W_MM - kx1, PAGE_H_MM - ky1],
        "note": ("margins are UPPER BOUNDS: every requested feature printed, "
                 "so the true engine margin is below the nearest-feature "
                 "distance; nothing was printed closer to the edge than the "
                 "manifest keep-out"),
    }


# ---------------------------------------------------------------------------
# (b) warp field from registration landmarks
# ---------------------------------------------------------------------------

def warp_field_summary(scan: dict) -> dict:
    """Residual warp vectors of all locked landmarks under the final affine."""
    man = scan["manifest"]
    reg = scan["registration"]
    vecs = []
    for lm in reg["landmarks"]:
        e = cc.entry(man, lm["name"])
        vecs.append({
            "name": lm["name"], "class": lm["class"],
            "x_mm": round((e["x_dots"] + e["w_dots"] / 2) * DOTS_TO_MM, 1),
            "y_mm": round((e["y_dots"] + e["h_dots"] / 2) * DOTS_TO_MM, 1),
            "dx_dots": round(lm["dx_dots"], 3), "dy_dots": round(lm["dy_dots"], 3),
            "q": round(lm["q"], 3), "ok": lm["ok"],
            "resid_dots": round(lm.get("resid_dots", float("nan")), 3),
        })
    ok = [v for v in vecs if v["ok"]]
    # coherent-row check: landmarks in the y~177 mm plus row (transport event)
    row = [v for v in ok if 172.0 < v["y_mm"] < 182.0 and v["class"] == "plus"]
    return {
        "n_landmarks": len(vecs), "n_locked": len(ok),
        "rms_dots": reg["residual_rms_dots"],
        "rms_core_dots": reg["residual_rms_core_dots"],
        "max_dots": reg["residual_max_dots"],
        "vectors": vecs,
        "plus_row_177mm": {
            "n": len(row),
            "mean_dy_dots": (round(float(np.mean([v["dy_dots"] for v in row])), 3)
                             if row else None),
            "mean_dx_dots": (round(float(np.mean([v["dx_dots"] for v in row])), 3)
                             if row else None)},
    }


# ---------------------------------------------------------------------------
# (c) phase-grating strip -> transport function + step catalog
# ---------------------------------------------------------------------------

def _demod(prof: np.ndarray, sub: int, period_dots: float,
           win_dots: float = PHASE_WIN_DOTS, hop_dots: float = PHASE_HOP_DOTS
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quadrature demodulation of an ink-positive 1-D profile.

    prof[i] sits at y = i/sub dots (patch-relative). Returns
    (win_center_dots, complex C per window, amp per window). Window = Hann,
    win_dots long (2 grating periods), hop hop_dots.
    """
    n = prof.size
    m = np.arange(n)
    z = (prof - float(prof.mean())) * np.exp(-2j * np.pi * m / (period_dots * sub))
    win = int(round(win_dots * sub))
    hop = int(round(hop_dots * sub))
    h = np.hanning(win)
    C = np.convolve(z, h, mode="valid")[::hop]
    starts = np.arange(0, n - win + 1)[::hop]
    centers = (starts + (win - 1) / 2.0) / sub
    amp = np.abs(C) * 2.0 / h.sum()
    return centers, C, amp


def _phase_to_displacement(C: np.ndarray, period_dots: float,
                           valid: np.ndarray) -> np.ndarray:
    """Unwrapped phase -> grating displacement delta(y) in dots (+y = down).

    Ink half-period center is at period/4 (rows [0, period/2) are ink), so the
    darkness fundamental is cos(2*pi*(y - period/4 - delta)/period) and
    delta = -phase*period/(2*pi) - period/4. Sign verified by _selftest().
    Unwrap runs on valid windows only; invalid ones are interpolated.
    """
    idx = np.arange(C.size, dtype=float)
    phi_v = np.unwrap(np.angle(C[valid]))
    delta_v = -phi_v * period_dots / (2.0 * np.pi) - period_dots / 4.0
    return np.interp(idx, idx[valid], delta_v)


def _transport_from_profile(prof: np.ndarray, sub: int, period: float
                            ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """(win_center_dots, r_dots median-centered, amp, offset_mod_period)."""
    centers, C, amp = _demod(prof, sub, period)
    valid = amp > 0.3 * np.median(amp)
    delta = _phase_to_displacement(C, period, valid)
    delta -= period * round(float(np.median(delta)) / period)
    offset = float(np.median(delta))
    return centers, delta - offset, amp, offset


def _catalog(y_dots: np.ndarray, r_med: np.ndarray, y0: float, y1: float,
             thresh: float = 0.25) -> list[tuple[float, float]]:
    """detect_steps on 3-dot samples (exp-001 convention), ends excluded."""
    return [(float(y), float(m)) for y, m in
            cc.detect_steps(y_dots, r_med, thresh_dots=thresh)
            if y0 + 15 < y < y1 - 15]


def analyze_phase_strip(scan: dict) -> dict:
    """Left phase grating: transport function r(y), step catalog, ripple
    spectrum, split-half noise control, landmark cross-check."""
    e = cc.entry(scan["manifest"], "phase_strip_left")
    period = float(e["params"]["period_dots"])
    sub = 2
    strip = cc.warp_channel(scan, "grey", e["x_dots"], e["y_dots"],
                            e["w_dots"], e["h_dots"], sub=sub)
    white, _, _ = cc.levels(strip)
    half = strip.shape[1] // 2
    prof = white - strip.mean(axis=1)          # ink positive
    prof_l = white - strip[:, :half].mean(axis=1)
    prof_r = white - strip[:, half:].mean(axis=1)

    # carrier control (long-window spectrum): fundamental amplitude vs the
    # off-band floor at 0.21-0.29 cycles/dot — clear of the fundamental
    # (1/6), the duty-distortion 2nd harmonic (1/3) and the 3rd (1/2).
    h = np.hanning(prof.size)
    spec = 2.0 * np.abs(np.fft.rfft((prof - prof.mean()) * h)) / h.sum()
    fr = np.fft.rfftfreq(prof.size, d=1.0 / sub)     # cycles per dot
    near = np.abs(fr - 1.0 / period) < 0.004
    offb = (fr > 0.21) & (fr < 0.29)
    carrier_snr = float(spec[near].max() / (np.median(spec[offb]) + 1e-12))

    centers, r, amp, offset_mod_period = _transport_from_profile(prof, sub, period)
    _, r_l, _, _ = _transport_from_profile(prof_l, sub, period)
    _, r_r, _, _ = _transport_from_profile(prof_r, sub, period)
    y_dots = e["y_dots"] + centers

    # split-half control: the two strip halves share the transport but have
    # independent mottle/noise -> corr quantifies how much of r is real,
    # std(r_l - r_r)/2 is the full-width measurement noise (001.2 discipline).
    half_corr = float(np.corrcoef(r_l, r_r)[0, 1])
    sigma_noise = float(np.std(r_l - r_r)) / 2.0

    # residual scale of the strip vs the global affine
    A = np.column_stack([y_dots, np.ones(y_dots.size)])
    (slope, icpt), *_ = np.linalg.lstsq(A, r, rcond=None)

    r_med = median_filter(r, size=5, mode="nearest")
    y_end = e["y_dots"] + e["h_dots"]
    # 001-compatible catalog: 3-dot-spaced diffs, 0.25-dot threshold — the
    # exact scanlab.detect_steps usage of run 001.4 (blind to slow ripple,
    # which the spectrum below reports instead).
    steps = _catalog(y_dots, r_med, e["y_dots"], y_end)
    steps_l = _catalog(y_dots, median_filter(r_l, size=5, mode="nearest"),
                       e["y_dots"], y_end)
    steps_r = _catalog(y_dots, median_filter(r_r, size=5, mode="nearest"),
                       e["y_dots"], y_end)

    def _matched(s, cat):
        return any(abs(s[0] - t[0]) < 24 and s[1] * t[1] > 0 for t in cat)

    n_rep = sum(1 for s in steps if _matched(s, steps_l) and _matched(s, steps_r))

    # transport ripple spectrum (slow wander detect_steps cannot see)
    rr_det = r_med - (slope * y_dots + icpt)
    hw = np.hanning(rr_det.size)
    ra = 2.0 * np.abs(np.fft.rfft(rr_det * hw)) / hw.sum()
    rf = np.fft.rfftfreq(rr_det.size, d=PHASE_HOP_DOTS)   # cycles/dot
    per_mm = np.where(rf > 0, 1.0 / np.maximum(rf, 1e-12), np.inf) * DOTS_TO_MM
    sel = (per_mm >= 1.0) & (per_mm <= 120.0)
    order = np.argsort(ra[sel])[::-1][:8]
    ripple = [{"period_mm": round(float(per_mm[sel][i]), 2),
               "amp_dots": round(float(ra[sel][i]), 3)} for i in order]

    # cross-check r(y) against the independent 2-D landmark dy offsets
    # (both are relative to the same global affine -> directly comparable)
    man = scan["manifest"]
    xcheck = []
    for lm in scan["registration"]["landmarks"]:
        if not lm["ok"]:
            continue
        le = cc.entry(man, lm["name"])
        yc = le["y_dots"] + le["h_dots"] / 2
        if not (y_dots[0] <= yc <= y_dots[-1]):
            continue
        k = int(np.argmin(np.abs(y_dots - yc)))
        xcheck.append({"name": lm["name"], "class": lm["class"],
                       "x_mm": round((le["x_dots"] + le["w_dots"] / 2) * DOTS_TO_MM, 1),
                       "y_mm": round(yc * DOTS_TO_MM, 1),
                       "landmark_dy_dots": round(lm["dy_dots"], 2),
                       "strip_r_dots": round(float(r_med[k]), 2)})
    plus_row = [x for x in xcheck if x["class"] == "plus" and 175 < x["y_mm"] < 180]
    plus_agree = (round(float(np.mean([x["landmark_dy_dots"] for x in plus_row])
                              - plus_row[0]["strip_r_dots"]), 2)
                  if plus_row else None)

    strip_len_mm = e["h_dots"] * DOTS_TO_MM
    mags = np.array([abs(m) for _, m in steps])
    spacings = (np.diff([y for y, _ in steps]) * DOTS_TO_MM
                if len(steps) > 1 else np.array([]))
    dec = STEP_DECIMATE
    return {
        "period_dots": period, "strip_len_mm": round(strip_len_mm, 1),
        "n_windows": int(centers.size),
        "carrier_snr_spectral_control": round(carrier_snr, 1),
        "split_half_corr_control": round(half_corr, 4),
        "sigma_noise_dots": round(sigma_noise, 3),
        "print_offset_mod_period_dots": round(offset_mod_period, 3),
        "residual_scale_slope_ppm": round(float(slope) * 1e6, 1),
        "r_rms_dots": round(float(np.sqrt(np.mean(r_med ** 2))), 3),
        "r_p2p_dots": round(float(np.ptp(r_med)), 3),
        "steps": {
            "n": len(steps),
            "per_40mm": round(len(steps) * 40.0 / strip_len_mm, 2),
            "size_dots": {"min": round(float(mags.min()), 3) if len(steps) else None,
                          "median": round(float(np.median(mags)), 3) if len(steps) else None,
                          "max": round(float(mags.max()), 3) if len(steps) else None},
            "spacing_mm_median": (round(float(np.median(spacings)), 1)
                                  if spacings.size else None),
            "replicated_in_both_halves": f"{n_rep}/{len(steps)}",
            "threshold_dots": 0.25,
            "catalog": [{"y_mm": round(y * DOTS_TO_MM, 2), "mag_dots": round(m, 3)}
                        for y, m in steps],
        },
        "ripple_spectrum_peaks": ripple,
        "landmark_crosscheck": xcheck,
        "plus_row_177mm": {
            "landmarks_mean_dy_dots": (round(float(np.mean(
                [x["landmark_dy_dots"] for x in plus_row])), 2) if plus_row else None),
            "strip_r_dots": plus_row[0]["strip_r_dots"] if plus_row else None,
            "disagreement_dots": plus_agree},
        "profile_y_mm": [round(float(v), 2) for v in (y_dots[::dec] * DOTS_TO_MM)],
        "profile_r_dots": [round(float(v), 3) for v in r_med[::dec]],
        "caveat": ("r(y) includes flatbed-scanner transport as well as printer "
                   "transport (same entanglement as experiment 001 — the "
                   "comparison with the 001.4 catalog is same-scanner, "
                   "apples-to-apples); right-edge quads disagree with the "
                   "left strip at some rows (x-dependent differential "
                   "transport, see landmark_crosscheck)"),
    }


# ---------------------------------------------------------------------------
# (d) K banding strip
# ---------------------------------------------------------------------------

def _amp_spectrum(x: np.ndarray, pitch_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """Hann-windowed single-sided amplitude spectrum; returns (freq_per_mm, amp)."""
    h = np.hanning(x.size)
    amp = 2.0 * np.abs(np.fft.rfft(x * h)) / h.sum()
    freq = np.fft.rfftfreq(x.size, d=pitch_mm)
    return freq, amp


def _segment_shifts(row_d: np.ndarray, f: np.ndarray, seg: int = 128,
                    max_lag: int = 8) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-segment y-shift of measured rows vs GT rows by 1-D xcorr.

    The rigid patch lock cannot follow the ~4-dot internal warp of the 113-mm
    strip (contract caveat 1); without realignment the GT regression removes
    almost no content noise. Returns (seg_center_rows, shift_dots, corr_q):
    content at measured row y matches GT row y + shift.
    """
    fc = f - f.mean()
    rc = row_d - row_d.mean()
    lags = np.arange(-max_lag, max_lag + 1)
    centers, shifts, quals = [], [], []
    for s0 in range(0, len(f) - seg + 1, seg):
        a = rc[s0: s0 + seg]
        cors = np.full(lags.size, -1.0)
        for j, L in enumerate(lags):
            if 0 <= s0 + L and s0 + L + seg <= len(fc):
                b = fc[s0 + L: s0 + L + seg]
                cors[j] = float(np.dot(a, b) /
                                (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
        k = int(np.argmax(cors))
        kk = float(k)
        if 0 < k < lags.size - 1:
            den = cors[k - 1] - 2 * cors[k] + cors[k + 1]
            if abs(den) > 1e-12:
                kk = k + 0.5 * (cors[k - 1] - cors[k + 1]) / den
        centers.append(s0 + seg / 2.0)
        shifts.append(lags[0] + kk)
        quals.append(float(cors[k]))
    return np.array(centers), np.array(shifts), np.array(quals)


def analyze_banding(scan: dict, white_mod: dict) -> dict:
    """K banding strip: warp-aligned GT-regressed row-density residual -> FFT."""
    e = cc.entry(scan["manifest"], "banding_K")
    v = cc.patch_view(scan, e)                 # GT template lock (rigid)
    D = cc.density(v, white_mod, channels=("grey",))["grey"]
    m = v.margin_dots * v.sub
    D = D[m: m + e["h_dots"] * v.sub, m: m + e["w_dots"] * v.sub]
    row_d = D.reshape(e["h_dots"], v.sub, -1).mean(axis=(1, 2)).astype(np.float64)

    # regress out the 50%-random field's own row-content noise using GT,
    # AFTER realigning GT rows to the measured internal warp (validated:
    # local_offset - shift at stations 3/4 matches the K quad dy there).
    gt = cc.load_gt(e)
    f = gt.mean(axis=1).astype(np.float64)
    seg_c, seg_sh, seg_q = _segment_shifts(row_d, f)
    sh = np.interp(np.arange(len(f), dtype=float), seg_c, seg_sh)
    g = np.interp(np.arange(len(f)) + sh, np.arange(len(f), dtype=float), f)
    A = np.column_stack([np.ones_like(g), g])
    coef, *_ = np.linalg.lstsq(A, row_d, rcond=None)
    resid = row_d - A @ coef
    raw_rms = float(np.std(row_d))
    resid_rms = float(np.std(resid))
    A0 = np.column_stack([np.ones_like(f), f])
    c0, *_ = np.linalg.lstsq(A0, row_d, rcond=None)
    resid_rms_unaligned = float(np.std(row_d - A0 @ c0))

    pitch_mm = DOTS_TO_MM
    freq, amp = _amp_spectrum(resid, pitch_mm)
    strip_len_mm = e["h_dots"] * pitch_mm

    def _local_peaks(a: np.ndarray) -> list[tuple[float, float, float]]:
        """(period_mm, amp, snr_vs_local_median_floor) at local maxima."""
        out = []
        for k in range(2, freq.size - 2):
            per = 1.0 / freq[k] if freq[k] > 0 else np.inf
            if not (2.0 <= per <= 120.0):
                continue
            if not (a[k] >= a[k - 1] and a[k] >= a[k + 1]):
                continue
            lo, hi = max(1, k - 20), min(freq.size, k + 21)
            nbhd = np.concatenate([a[lo: max(lo, k - 2)], a[k + 3: hi]])
            out.append((float(per), float(a[k]),
                        float(a[k] / (np.median(nbhd) + 1e-12))))
        out.sort(key=lambda t: -t[2])
        return out

    cand = _local_peaks(amp)
    # permutation controls (seeded, CLAUDE.md determinism): destroy spectral
    # structure, keep the amplitude distribution -> null distribution of the
    # max peak-SNR statistic (the 001.2 discriminating-control rule).
    ctl_max_snr = []
    amp_ctl = None
    for lbl in (b"", b"/a", b"/b", b"/c"):
        gperm = rng(gen_calpage.SEED, b"exp002/geometry/banding-permctl" + lbl)
        _, a_c = _amp_spectrum(resid[gperm.permutation(resid.size)], pitch_mm)
        if amp_ctl is None:
            amp_ctl = a_c
        pk = _local_peaks(a_c)
        ctl_max_snr.append(round(pk[0][2], 2) if pk else 0.0)
    bar = 4.0
    peaks = [{"period_mm": round(p, 2), "amp_density": round(a, 5),
              "snr_vs_local_floor": round(s, 1),
              "resolved": bool(p <= strip_len_mm / 2.0),
              "drum_fuser_plausible_2_120mm": True}
             for p, a, s in cand if s >= bar]
    peaks.sort(key=lambda p: -p["amp_density"])
    band = (freq > 0) & (1.0 / np.maximum(freq, 1e-9) >= 2.0) \
        & (1.0 / np.maximum(freq, 1e-9) <= strip_len_mm / 2.0)
    max_real = cand[0] if cand else (None, None, None)
    # internal warp of the strip in ABSOLUTE (global-affine) terms: the rigid
    # lock offset minus the segment shift (content at row y = GT row y+sh
    # means the print moved by -sh relative to the locked frame).
    warp_abs = [{"y_mm": round(float((e["y_dots"] + c) * DOTS_TO_MM), 1),
                 "dy_abs_dots": round(float(v.local_offset_dots[0] - s), 2),
                 "xcorr_q": round(float(q), 2)}
                for c, s, q in zip(seg_c, seg_sh, seg_q)]
    return {
        "patch": e["name"], "lock_q": round(v.local_quality, 3),
        "locked": bool(v.local_locked),
        "strip_len_mm": round(strip_len_mm, 1),
        "mean_density_at_50pct": round(float(coef[0] + 0.5 * coef[1]), 3),
        "row_rms_density_raw": round(raw_rms, 4),
        "row_rms_density_gt_regressed": round(resid_rms, 4),
        "row_rms_density_gt_regressed_unaligned": round(resid_rms_unaligned, 4),
        "gt_regression_gain_density_per_ink": round(float(coef[1]), 3),
        "gt_alignment": {"segment_rows": 128,
                         "shift_range_dots": [round(float(seg_sh.min()), 2),
                                              round(float(seg_sh.max()), 2)],
                         "median_xcorr_q": round(float(np.median(seg_q)), 2)},
        "internal_warp_abs_dy": warp_abs,
        "peaks": peaks[:8],
        "no_significant_banding": bool(not peaks),
        "strongest_candidate": {"period_mm": round(max_real[0], 2),
                                "amp_density": round(max_real[1], 5),
                                "snr": round(max_real[2], 2)}
        if max_real[0] is not None else None,
        "control_max_snr_distribution": ctl_max_snr,
        "detection_bar_snr": 4.0,
        "upper_bound_amp_density": (round(max_real[1], 5)
                                    if max_real[0] is not None and not peaks
                                    else None),
        "control_max_amp_in_band": round(float(amp_ctl[band].max()), 5),
        "resolved_period_limit_mm": round(strip_len_mm / 2.0, 1),
        "note": ("periods above the resolved limit have <2 cycles in the "
                 "strip and are reported unresolved; the max-SNR statistic "
                 "is judged against the seeded permutation-control null "
                 "distribution; GT rows are realigned to the strip's "
                 "internal warp before regression (rigid-lock caveat 1)"),
    }


# ---------------------------------------------------------------------------
# plane offsets (color scan, reg quads) — channel_params.plane_offsets
# ---------------------------------------------------------------------------

def analyze_plane_offsets(scan_color: dict) -> dict:
    """C/M/Y engine misregistration vs K at the 5 quad stations.

    The offsets DRIFT along the process direction (tandem-engine behavior the
    panel design anticipated), so the curated result is a linear drift model
    offset(y) = center + slope*(y - 148.5 mm), not a bare median.
    Validated: interpolating the M model to the M/encode_c3 position
    (y ~ 97 mm) reproduces the contract's independently measured +2.49-dot
    M lock offset.
    """
    man = scan_color["manifest"]
    stations = []
    rel: dict[str, list[tuple[float, float, float]]] = {p: [] for p in "CMY"}
    for qi in range(5):
        y_mm = (cc.entry(man, f"quad{qi}_K")["y_dots"] + 16.5) * DOTS_TO_MM
        st: dict = {"station": qi, "y_mm": round(y_mm, 1)}
        for p in "KCMY":
            v = cc.patch_view(scan_color, f"quad{qi}_{p}")
            st[p] = {"dy_dots": round(v.local_offset_dots[0], 3),
                     "dx_dots": round(v.local_offset_dots[1], 3),
                     "q": round(v.local_quality, 3), "locked": v.local_locked,
                     "channel": v.reg_channel}
        stations.append(st)
        if st["K"]["locked"]:
            for p in "CMY":
                if st[p]["locked"]:
                    rel[p].append((y_mm,
                                   st[p]["dy_dots"] - st["K"]["dy_dots"],
                                   st[p]["dx_dots"] - st["K"]["dx_dots"]))
    offsets = {}
    y_mid = 148.5
    for p in "CMY":
        if len(rel[p]) >= 3:
            arr = np.array(rel[p])
            A = np.column_stack([arr[:, 0] - y_mid, np.ones(len(arr))])
            (by, ay), *_ = np.linalg.lstsq(A, arr[:, 1], rcond=None)
            (bx, ax), *_ = np.linalg.lstsq(A, arr[:, 2], rcond=None)
            ry = arr[:, 1] - A @ (by, ay)
            offsets[p] = {
                "dy_center_dots": round(float(ay), 2),
                "dy_slope_dots_per_100mm": round(float(by) * 100, 2),
                "dx_center_dots": round(float(ax), 2),
                "dx_slope_dots_per_100mm": round(float(bx) * 100, 2),
                "dy_range_dots": [round(float(arr[:, 1].min()), 2),
                                  round(float(arr[:, 1].max()), 2)],
                "dy_fit_rms_dots": round(float(np.sqrt(np.mean(ry ** 2))), 2),
                "n_stations": len(rel[p]),
            }
        else:
            offsets[p] = {"n_stations": len(rel[p]),
                          "error": "too few locked stations for drift model"}
    return {"per_station": stations, "offsets_vs_K": offsets,
            "note": ("measured on the color scan; K quads registered on grey, "
                     "C on r, M on g, Y on b (cc.REG_CHANNEL_FOR_PLANE); K "
                     "offsets ~0 by construction (quads are in the affine "
                     "fit); offsets are y-dependent — use the drift model, "
                     "the median would be misleading")}


# ---------------------------------------------------------------------------
# canary E — rescale / fit-to-page
# ---------------------------------------------------------------------------

def rescale_canary(scale_x: float, scale_y: float) -> dict:
    """Panel §8-E: fail iff |scale error| > 1% AND x/y agree within 0.2%
    (uniform shrink = fit-to-page); anisotropic deviations are hygro/fuser."""
    dx_pct = (scale_x - 1.0) * 100.0
    dy_pct = (scale_y - 1.0) * 100.0
    stat = max(abs(dx_pct), abs(dy_pct))
    control = abs(dx_pct - dy_pct)
    if stat <= 0.4:
        status = "pass"
        note = "scale within the healthy +-0.4% hygro envelope"
    elif stat > 1.0 and control < 0.2:
        status = "fail"
        note = "uniform both-axes rescale — fit-to-page class corruption"
    else:
        status = "indeterminate"
        note = ("scale deviation outside +-0.4% but anisotropic or <1% — "
                "hygro/fuser candidate, not rescale-class")
    note += (f" (dx={dx_pct:+.3f}%, dy={dy_pct:+.3f}%; statistic=max axis "
             f"deviation %, control=|dx-dy| uniformity %)")
    return cc.canary_verdict("E_rescale", status, stat, control, note)


# ---------------------------------------------------------------------------
# family entry point
# ---------------------------------------------------------------------------

def run(scan_bw: dict, scan_color: dict, core_ctx: dict | None = None) -> dict:
    """Transport-family payload for cc.report_merge. Scans must be (or will
    be) registered; core_ctx may carry {'white_model_bw': ...} to skip the
    white-model fit."""
    ctx = core_ctx or {}
    _selftest()  # phase-demod sign + step recovery must hold before real data
    for s in (scan_bw, scan_color):
        if s.get("registration") is None:
            cc.register(s)
    reg_bw = scan_bw["registration"]
    reg_c = scan_color["registration"]

    # (a) rulers — grey scan primary (K geometry rule) + decode control
    rul_top = analyze_ruler_top(scan_bw)
    rul_left = analyze_ruler_left(scan_bw)
    ctl_top = analyze_ruler_top(scan_bw, shift_dots=30.0)
    ctl_left = analyze_ruler_left(scan_bw, shift_dots=30.0)
    n_ctl_ok = (sum(v["ok"] for v in ctl_top["indices"].values())
                + sum(v["ok"] for v in ctl_left["indices"].values()))
    # color-scan rulers: scanner-axis cross-check (contract caveat 6)
    rul_top_c = analyze_ruler_top(scan_color)
    rul_left_c = analyze_ruler_left(scan_color)

    def _scales(reg: dict, top: dict, left: dict) -> tuple[float, float]:
        sx = reg["px_per_dot_x"] / cc.PX_PER_DOT * top["fit"]["alpha"]
        sy = reg["px_per_dot_y"] / cc.PX_PER_DOT * left["fit"]["alpha"]
        return float(sx), float(sy)

    scale_x, scale_y = _scales(reg_bw, rul_top, rul_left)
    scale_x_c, scale_y_c = _scales(reg_c, rul_top_c, rul_left_c)

    clip = clip_map_and_margins(scan_bw, rul_top, rul_left)

    # (b) warp field
    warp_bw = warp_field_summary(scan_bw)
    warp_c = warp_field_summary(scan_color)

    # (c) phase strip (grey scan)
    phase = analyze_phase_strip(scan_bw)

    # (d) banding (grey scan; density against the paper-white model)
    wm = ctx.get("white_model_bw") or cc.white_model(scan_bw)
    banding = analyze_banding(scan_bw, wm)

    # plane offsets (color scan)
    quads = analyze_plane_offsets(scan_color)

    canary_e = rescale_canary(scale_x, scale_y)

    steps = phase["steps"]
    n40 = steps["per_40mm"]
    sd = steps["size_dots"]
    sizes_in_ref = (steps["n"] > 0 and sd["min"] is not None
                    and sd["max"] <= 2.0)
    rate_in_ref = REF_001_STEPS_PER_40MM[0] * 0.5 <= n40 <= REF_001_STEPS_PER_40MM[1] * 1.5
    measured = (f"measured {n40}/40mm, sizes {sd['min']}-{sd['max']} dots "
                f"(median {sd['median']})")
    ref = (f"001.4 reference {REF_001_STEPS_PER_40MM[0]}-"
           f"{REF_001_STEPS_PER_40MM[1]}/40mm, "
           f"{REF_001_STEP_RANGE_DOTS[0]}-{REF_001_STEP_RANGE_DOTS[1]} dots")
    consistency = (f"same regime as 001.4: {measured} vs {ref}"
                   if (sizes_in_ref and rate_in_ref)
                   else f"DIFFERS from 001.4: {measured} vs {ref}")

    # banding-strip internal warp vs the grey-scan K quad landmarks at the
    # two stations inside the strip's y range (independent cross-check)
    lm_dy = {lm["name"]: lm["dy_dots"] for lm in reg_bw["landmarks"] if lm["ok"]}
    band_xcheck = []
    for qi in (3, 4):
        name = f"quad{qi}_K"
        if name not in lm_dy:
            continue
        yq = (cc.entry(scan_bw["manifest"], name)["y_dots"] + 16.5) * DOTS_TO_MM
        near = min(banding["internal_warp_abs_dy"],
                   key=lambda wv: abs(wv["y_mm"] - yq))
        band_xcheck.append({"landmark": name, "y_mm": round(yq, 1),
                            "quad_dy_dots": round(lm_dy[name], 2),
                            "banding_strip_dy_dots": near["dy_abs_dots"]})

    geometry = {
        "scale_xy": [round(scale_x, 5), round(scale_y, 5)],
        "skew_deg": round(reg_bw["shear_deg"], 3),
        "rotation_deg": round(reg_bw["rotation_deg"], 3),
        "anisotropy_y_over_x": round(scale_y / scale_x, 5),
        "margins_mm": clip["engine_margins_mm_upper_bounds"],
        "warp_rms_dots": round(warp_bw["rms_dots"], 3),
        "warp_max_dots": round(warp_bw["max_dots"], 3),
    }
    channel_params = {
        "warp_rms_dots": round(warp_bw["rms_dots"], 3),
        "transport_steps": {
            "n": steps["n"], "per_40mm": steps["per_40mm"],
            "size_dots": steps["size_dots"],
            "spacing_mm_median": steps["spacing_mm_median"],
            "threshold_dots": steps["threshold_dots"],
            "replicated_in_both_halves": steps["replicated_in_both_halves"],
            "sigma_noise_dots": phase["sigma_noise_dots"],
            "catalog": steps["catalog"],
            "r_rms_dots": phase["r_rms_dots"],
            "r_p2p_dots": phase["r_p2p_dots"],
            "ripple_spectrum_peaks": phase["ripple_spectrum_peaks"],
            "vs_001_4": consistency,
        },
        "banding": {
            "peaks": banding["peaks"],
            "no_significant_banding": banding["no_significant_banding"],
            "strongest_candidate": banding["strongest_candidate"],
            "control_max_snr_distribution": banding["control_max_snr_distribution"],
            "upper_bound_amp_density": banding["upper_bound_amp_density"],
            "row_rms_density_gt_regressed": banding["row_rms_density_gt_regressed"],
            "resolved_period_limit_mm": banding["resolved_period_limit_mm"],
        },
        "plane_offsets": quads["offsets_vs_K"],
    }
    detail = {
        "rulers": {
            "grey_scan": {
                "top_fit": rul_top["fit"], "left_fit": rul_left["fit"],
                "scale_abs_xy": [round(scale_x, 5), round(scale_y, 5)],
            },
            "color_scan": {
                "top_fit": rul_top_c["fit"], "left_fit": rul_left_c["fit"],
                "scale_abs_xy": [round(scale_x_c, 5), round(scale_y_c, 5)],
                "note": ("y differs from grey scan by scanner transport "
                         "(contract caveat 6) — x should agree"),
            },
            "index_decode_control": {
                "n_ok_at_true_positions": (
                    _index_summary(rul_top)["n_ok"]
                    + _index_summary(rul_left)["n_ok"]),
                "n_ok_at_shift_30dots": n_ctl_ok,
                "expect": "18 vs 0",
            },
            "clip_map": clip,
        },
        "warp_field": {"grey_scan": warp_bw, "color_scan": warp_c},
        "phase_strip": phase,
        "banding": banding,
        "banding_warp_vs_quads": band_xcheck,
        "reg_quads": quads,
        "ruler_check_from_core": {"grey": reg_bw["ruler_check"],
                                  "color": reg_c["ruler_check"]},
    }
    return {
        "geometry": geometry,
        "channel_params": channel_params,
        "canaries": {"E": canary_e},
        "families": {"transport": detail},
    }


# ---------------------------------------------------------------------------
# deterministic self-tests (run before touching real data)
# ---------------------------------------------------------------------------

def _selftest() -> None:
    """Synthetic checks of the phase-demod sign convention and step recovery."""
    sub, period = 2, 6.0
    n = 6000
    y = np.arange(n) / sub
    delta_true = np.where(y < 1500.0, 0.0, 1.0)     # +1 dot step at y=1500
    prof = 0.5 + 0.5 * np.cos(2 * np.pi * (y - period / 4 - delta_true) / period)
    centers, C, amp = _demod(prof, sub, period)
    valid = amp > 0.3 * np.median(amp)
    delta = _phase_to_displacement(C, period, valid)
    delta -= period * round(float(np.median(delta)) / period)
    lo = delta[centers < 1400]
    hi = delta[centers > 1600]
    assert abs(float(np.mean(lo)) - 0.0) < 0.05, f"offset sign wrong: {np.mean(lo)}"
    assert abs(float(np.mean(hi)) - 1.0) < 0.05, f"step sign/size wrong: {np.mean(hi)}"
    r_med = median_filter(delta, size=5, mode="nearest")
    steps = cc.detect_steps(centers[::STEP_DECIMATE], r_med[::STEP_DECIMATE],
                            thresh_dots=0.25)
    assert len(steps) == 1 and abs(steps[0][1] - 1.0) < 0.1, f"steps: {steps}"
    assert abs(steps[0][0] - 1500.0) < 15.0, f"step position: {steps}"
    print("selftest: phase sign, +1.0-dot step magnitude and position OK")


# ---------------------------------------------------------------------------
# smoke run
# ---------------------------------------------------------------------------

def _load_registered(path: str, cache_dir: str | None) -> dict:
    """Dev convenience: pickle-cache a registered scan between iterations."""
    p = Path(path)
    cachef = Path(cache_dir) / (p.name + ".reg.pkl") if cache_dir else None
    if cachef and cachef.exists():
        with open(cachef, "rb") as fh:
            return pickle.load(fh)
    scan = cc.load_scan(p)
    cc.register(scan)
    if cachef:
        scan.pop("_f32", None)
        with open(cachef, "wb") as fh:
            pickle.dump(scan, fh, protocol=5)
    return scan


def _print_summary(payload: dict) -> None:
    g = payload["geometry"]
    ch = payload["channel_params"]
    t = payload["families"]["transport"]
    print("\n== geometry ==")
    print(f"scale_xy={g['scale_xy']}  anisotropy={g['anisotropy_y_over_x']}  "
          f"skew={g['skew_deg']} deg  rot={g['rotation_deg']} deg")
    print(f"margins_mm (upper bounds): {g['margins_mm']}")
    print(f"warp rms={g['warp_rms_dots']} max={g['warp_max_dots']} dots")
    clip = t["rulers"]["clip_map"]
    print(f"clip: top {clip['ruler_top_ticks']} left {clip['ruler_left_ticks']} "
          f"indices top {clip['indices_top']['n_ok']}/8 left "
          f"{clip['indices_left']['n_ok']}/10  clipping={clip['clipping_detected']}")
    print(f"index decode control: {t['rulers']['index_decode_control']}")
    ph = t["phase_strip"]
    print("\n== phase strip ==")
    print(f"carrier spectral SNR={ph['carrier_snr_spectral_control']}  "
          f"split-half corr={ph['split_half_corr_control']}  "
          f"noise sigma={ph['sigma_noise_dots']} dots")
    print(f"offset mod 6 = {ph['print_offset_mod_period_dots']} dots  slope "
          f"{ph['residual_scale_slope_ppm']} ppm")
    s = ch["transport_steps"]
    print(f"r rms={s['r_rms_dots']} p2p={s['r_p2p_dots']} dots; steps n={s['n']} "
          f"({s['per_40mm']}/40mm) sizes {s['size_dots']} "
          f"replicated {s['replicated_in_both_halves']}")
    print(f"vs 001.4: {s['vs_001_4']}")
    print(f"ripple peaks: {s['ripple_spectrum_peaks'][:4]}")
    print(f"plus-row 177mm cross-check: {ph['plus_row_177mm']}")
    b = t["banding"]
    print("\n== banding ==")
    print(f"lock q={b['lock_q']}  D(50%)={b['mean_density_at_50pct']}  row rms "
          f"raw={b['row_rms_density_raw']} regressed="
          f"{b['row_rms_density_gt_regressed']} "
          f"(unaligned {b['row_rms_density_gt_regressed_unaligned']})")
    if b["no_significant_banding"]:
        print(f"  NO significant narrowband banding: strongest candidate "
              f"{b['strongest_candidate']} vs control max-SNR dist "
              f"{b['control_max_snr_distribution']} (bar {b['detection_bar_snr']}); "
              f"amp upper bound {b['upper_bound_amp_density']} D")
    for p in b["peaks"]:
        print(f"  peak {p['period_mm']} mm amp {p['amp_density']} "
              f"snr {p['snr_vs_local_floor']} resolved={p['resolved']}")
    print(f"  perm-control max amp in band: {b['control_max_amp_in_band']}")
    print(f"  strip warp vs quads: {t['banding_warp_vs_quads']}")
    print("\n== plane offsets vs K (drift model, dots) ==")
    for p, o in ch["plane_offsets"].items():
        print(f"  {p}: {o}")
    print(f"\ncanary E: {payload['canaries']['E']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="cal_geometry smoke run")
    ap.add_argument("scan_bw")
    ap.add_argument("scan_color")
    ap.add_argument("--cache-dir", default=None,
                    help="dev only: pickle-cache registered scans")
    args = ap.parse_args()

    _selftest()
    scan_bw = _load_registered(args.scan_bw, args.cache_dir)
    print(f"grey scan registered: rms={scan_bw['registration']['residual_rms_dots']:.3f} dots")
    scan_color = _load_registered(args.scan_color, args.cache_dir)
    print(f"color scan registered: rms={scan_color['registration']['residual_rms_dots']:.3f} dots")
    payload = run(scan_bw, scan_color, None)
    _print_summary(payload)
    rep = cc.report_init(scan_bw)
    cc.report_merge(rep, payload)
    out = cc.BUILD / "cal_geometry_report.json"
    cc.save_report(rep, out)
    print(f"\nwrote {out}")

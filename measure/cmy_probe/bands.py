"""The probe's c2 cell bands: hard cell decisions at per-plane poses against the GT states (CMY-PROBE-M281 §2, §4).

Every band carries the SAME seeded four-state field (npz "states", rows x cols uint8 presence ids C + 2M + 4Y,
so W 0, C 1, M 2, Y 4), printed by a different construct (M-hex, M-a85, I-2, I-8, I-ref).  Per band:

1. the band is tiled into square windows of WINDOW_CELLS cells (36: it divides 216 and 2196; a remainder
   is read by one more window flush with the band's end, its overlap overwriting); per window the
   e041_scale_readout.read_window method (measure/e041_scale_readout.py:244-314), reduced to what a
   four-state single-toner field needs: the window plus SEARCH_MM and the per-plane search on every side
   resampled page-aligned at sub px per dot (e041_probe_readout.sample_rect), registered on the OR-ed ink
   mask against darkness (e041_scale_readout.register), then a pose per plane C, M, Y
   (e041_mixture_readout.plane_poses: own dot mask vs own spectrally unmixed coverage, +/- 3 dots), and per
   cell the mean over a centre box of half the cell with R at C's pose, G at M's, B at Y's
   (e041_mixture_readout.sample_per_plane);
2. one colour table per band: nearest class mean in RGB, the means fitted on every cell of the band with
   its GT label (e041's "band" classifier, e041_mixture_readout.class_means / classify) — the channel a
   receiver with one colour table per band would see;
3. reported: state (cell) error, hard error per plane (the decided state carries the plane vs the true
   one), the 4 x 4 confusion (rows true, columns decided; W, C, M, Y), the per-plane pose offsets of M and
   Y against C in printed dots (median over windows) with |Y - C|, and the in-band lattice score (the bar
   score of measure/cmy_probe/bars.py over the band's interior, all three channels).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from measure.e041_mixture_readout import class_means, classify, plane_poses, plane_search_px, sample_per_plane
from measure.e041_probe_readout import Scan, sample_rect
from measure.e041_scale_readout import REG_MIN_PEAK, SEARCH_MM, register

STATE_NAMES = ("W", "C", "M", "Y")
PRESENCE_IDS = (0, 1, 2, 4)                 # presence id C + 2M + 4Y of each class, in STATE_NAMES order
PLANES_OF_CLASS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], bool)   # class -> (C, M, Y)
WINDOW_CELLS = 36


def state_classes(states: np.ndarray) -> np.ndarray:
    """Presence ids {0, 1, 2, 4} -> class indices 0..3 (W, C, M, Y); refuses any other id."""
    lut = np.full(256, 255, np.uint8)
    for k, pid in enumerate(PRESENCE_IDS):
        lut[pid] = k
    cls = lut[np.asarray(states, np.uint8)]
    if (cls == 255).any():
        bad = sorted(set(np.unique(states).tolist()) - set(PRESENCE_IDS))
        raise SystemExit(f"GT states carry presence ids {bad} outside {PRESENCE_IDS} — contract fork")
    return cls


def dot_planes(cls: np.ndarray, cell_dots: int) -> np.ndarray:
    """(4, H, W) uint8 dot planes C, M, Y, K of a class grid (K empty: the probe carries no K)."""
    blk = np.ones((cell_dots, cell_dots), np.uint8)
    planes = [np.kron((cls == k).astype(np.uint8), blk) for k in (1, 2, 3)]
    return np.stack(planes + [np.zeros_like(planes[0])])


def window_starts(n_cells: int, win: int) -> list[int]:
    """Window starts tiling n_cells with windows of win cells; a remainder gets one window flush with the end."""
    if n_cells < win:
        raise SystemExit(f"band of {n_cells} cells is narrower than one {win}-cell window")
    starts = list(range(0, n_cells - win + 1, win))
    if starts[-1] + win < n_cells:
        starts.append(n_cells - win)
    return starts


def read_window(scan: Scan, A: np.ndarray, xd: int, yd: int, cls_win: np.ndarray, cell_dots: int, dpi: float,
                white: np.ndarray, sub: int) -> dict[str, Any]:
    """One square window whose top-left printed dot is (xd, yd): per-cell features (cells, cells, 3) at the
    per-plane poses, the poses, and the OR-ed registration (e041_scale_readout.read_window's steps)."""
    cells = cls_win.shape[0]
    planes = dot_planes(cls_win, cell_dots)
    n_dots = cells * cell_dots
    dot_mm = 25.4 / dpi
    step = dot_mm / sub
    s_px = int(round(SEARCH_MM / step))
    p_px = plane_search_px(sub)
    m_px = s_px + p_px
    k = np.arange(n_dots * sub + 2 * m_px)
    rect = sample_rect(scan, A, xd * dot_mm + (k - m_px) * step, yd * dot_mm + (k - m_px) * step)
    ink = np.kron(planes.max(axis=0).astype(np.float32), np.ones((sub, sub), np.float32))
    oy, ox, peak, edge = register(rect, ink, s_px, p_px)
    reg_ok = bool(peak >= REG_MIN_PEAK)
    if not reg_ok:
        oy = ox = float(m_px)
    poses = plane_poses(rect, planes, oy, ox, white, p_px, sub)
    vals, _ = sample_per_plane(rect, poses, oy, ox, cells, cell_dots * sub)
    return {"X": vals, "poses": poses, "reg_ok": reg_ok, "reg_edge": bool(edge), "reg_peak": float(peak),
            "reg_dy_px": float(oy - m_px), "reg_dx_px": float(ox - m_px)}


def pose_offsets(windows: list[dict[str, Any]], sub: int) -> dict[str, float]:
    """Median M - C and Y - C pose offsets in printed dots over windows whose planes are both posed
    (flag ok or edge; weak and collinear poses left out), and the median |Y - C|."""
    out: dict[str, float] = {}
    for pl in ("M", "Y"):
        d = [(w["poses"][pl]["oy"] - w["poses"]["C"]["oy"], w["poses"][pl]["ox"] - w["poses"]["C"]["ox"])
             for w in windows if pl in w["poses"] and "C" in w["poses"]
             and w["poses"][pl]["flag"] in ("ok", "edge") and w["poses"]["C"]["flag"] in ("ok", "edge")]
        arr = np.array(d, np.float64).reshape(-1, 2) / sub
        out[f"{pl}_dy_vs_C_dots"] = float(np.median(arr[:, 0])) if len(arr) else float("nan")
        out[f"{pl}_dx_vs_C_dots"] = float(np.median(arr[:, 1])) if len(arr) else float("nan")
        if pl == "Y":
            out["Y_minus_C_abs_dots"] = float(np.median(np.hypot(arr[:, 0], arr[:, 1]))) if len(arr) else float("nan")
    return out


def read_band(scan: Scan, A: np.ndarray, band: dict[str, Any], cls: np.ndarray, dpi: float, white: np.ndarray,
              sub: int) -> dict[str, Any]:
    """Every window of one band -> per-cell features (rows, cols, 3) and the window records."""
    cd = int(band.get("cell_dots", 2))
    rows, cols = cls.shape
    bx, by = int(band["x_dots"]), int(band["y_dots"])
    X = np.full((rows, cols, 3), np.nan, np.float32)
    windows = []
    for r0 in window_starts(rows, WINDOW_CELLS):
        for c0 in window_starts(cols, WINDOW_CELLS):
            win = cls[r0:r0 + WINDOW_CELLS, c0:c0 + WINDOW_CELLS]
            try:
                w = read_window(scan, A, bx + c0 * cd, by + r0 * cd, win, cd, dpi, white, sub)
            except ValueError as exc:                       # outside the scan / no plane present
                print(f"  band {band['name']} window ({r0},{c0}): skipped ({exc})")
                continue
            X[r0:r0 + WINDOW_CELLS, c0:c0 + WINDOW_CELLS] = w.pop("X")
            w.update(r0=r0, c0=c0)
            windows.append(w)
    return {"X": X, "windows": windows}


def classify_band(X: np.ndarray, cls: np.ndarray) -> np.ndarray:
    """One colour table per band (e041's "band" classifier): nearest class mean, means over every read cell
    with its GT label; unread cells come back as -1."""
    ok = np.isfinite(X).all(-1)
    pred = np.full(cls.shape, -1, np.int64)
    Xr, yr = X[ok].astype(np.float64), cls[ok].astype(np.int64)
    if len(yr):
        mu, _ = class_means(Xr, yr, len(STATE_NAMES))
        pred[ok] = classify(Xr, yr, mu, None)
    return pred


def band_metrics(cls: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    """State error, per-plane hard error, the 4 x 4 confusion (rows true, columns decided), per-state error."""
    ok = pred >= 0
    y, p = cls[ok].astype(np.int64), pred[ok]
    S = len(STATE_NAMES)
    conf = np.zeros((S, S), np.int64)
    np.add.at(conf, (y, p), 1)
    th, ph = PLANES_OF_CLASS[y], PLANES_OF_CLASS[p]
    n = max(len(y), 1)
    return {"n_cells": int(cls.size), "n_read": int(ok.sum()), "state_err": float((y != p).sum() / n),
            "plane_err": {pl: float((th[:, i] != ph[:, i]).sum() / n) for i, pl in enumerate("CMY")},
            "per_state_err": {STATE_NAMES[s]: (float(1 - conf[s, s] / conf[s].sum()) if conf[s].sum() else None)
                              for s in range(S)},
            "confusion": conf.tolist()}


def window_errors(cls: np.ndarray, pred: np.ndarray, windows: list[dict[str, Any]]) -> list[float]:
    """State error per window (the band's colour table), in window order."""
    out = []
    for w in windows:
        c = cls[w["r0"]:w["r0"] + WINDOW_CELLS, w["c0"]:w["c0"] + WINDOW_CELLS]
        p = pred[w["r0"]:w["r0"] + WINDOW_CELLS, w["c0"]:w["c0"] + WINDOW_CELLS]
        ok = p >= 0
        out.append(float((c[ok] != p[ok]).mean()) if ok.any() else float("nan"))
    return out


def band_report(scan: Scan, A: np.ndarray, band: dict[str, Any], states: np.ndarray, dpi: float, white: np.ndarray,
                sub: int) -> dict[str, Any]:
    """One band end to end: windows, classification, metrics, pose offsets (lattice score added by the caller)."""
    cls = state_classes(states)
    if cls.shape != (int(band["rows"]), int(band["cols"])):
        raise SystemExit(f"band {band['name']}: GT {cls.shape} vs manifest {band['rows']} x {band['cols']} cells"
                         " — contract fork")
    read = read_band(scan, A, band, cls, dpi, white, sub)
    pred = classify_band(read["X"], cls)
    werr = window_errors(cls, pred, read["windows"])
    ws = read["windows"]
    return {"name": band["name"], "arm": band.get("arm"), **band_metrics(cls, pred), **pose_offsets(ws, sub),
            "n_windows": len(ws), "n_reg_nominal": sum(1 for w in ws if not w["reg_ok"]),
            "n_reg_edge": sum(1 for w in ws if w["reg_edge"]),
            "window_err_max": float(np.nanmax(werr)) if werr else float("nan"),
            "window_err_by_col": _profile(ws, werr, "c0")}


def _profile(ws: list[dict[str, Any]], werr: list[float], key: str) -> dict[str, float]:
    """Mean window state error per window column start (cells), the stripe-crossing profile."""
    acc: dict[int, list[float]] = {}
    for w, e in zip(ws, werr):
        acc.setdefault(int(w[key]), []).append(e)
    return {str(k): float(np.nanmean(v)) for k, v in sorted(acc.items())}

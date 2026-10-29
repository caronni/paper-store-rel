"""e045 — cells at chosen per-plane poses through one box sampler.  MEASUREMENT ONLY (truth is read, nothing is
minted).

The readouts (measure/cmy_probe/bands.read_window, measure/e044_cmy_truth/readout.py) pose every 36-cell window
per plane (C from R, M from G, Y from B) within +/- 3 dots of the window's OR-ed registration, or of the nominal
pose where that registration falls under its bar; on sheet 3's left edge M and Y sit 4-5 dots from the page
affine, so some windows there stop on the search edge.  The pose fields here:

  read   read_window's own poses and X (the e043 readout's band numbers; reproduced, not re-derived);
  win    a second window pass whose prior is the 3 x 3 window-neighbourhood median of the first pass's
         plane-mean offset (5 x 5 where empty, else none; the e044 readout's pass 2);
  finex  per SUB_CELLS-cell sub-window the per-plane pose again (e041_mixture_readout.plane_poses, +/- 3 dots
         around the window's plane-mean pose) CROSS-FITTED by halves: the pose fitted on the sub-window's top
         HALF_ROWS - 1 cell rows reads its bottom half and the pose fitted on its bottom HALF_ROWS - 1 rows reads
         its top half (plane_poses' use_px, laid at the window's pose rounded to a pixel; the row next to the
         split is a guard against the planes' +/- 1-dot spread around that pose), so no cell is read at a pose
         its own pixels chose; a half whose fit is not "ok" falls back to the window's pose.  (A checkerboard
         split is wrong here: its pixel mask sits at the nominal pose while the left edge's cells lie 4-5 dots
         away.)  `fine` is the same sub-window posed on all of its cells, in-sample: finex - fine is the
         in-sample pose's optimism;
  diff   C at its win pose, M and Y at C's pose plus the window differential (M - C, Y - C) smoothed with a
         Gaussian of DIFF_SIGMA_MM over the field's window grid: a receiver with a local common pose and a
         smooth page field (PAGE-FIELD-DESIGN's 5.557 mm length passes a 30 mm wave at ~0.37 and a 100 mm wave
         at 0.965; a Gaussian of 6.7 mm has the same 30 mm transfer — an emulation, not the solve);
  common every plane at C's win pose (no differential at all);
  aff    one affine per plane over every "ok" window offset of the page (the page pose).

sample_field reads every arm the same way: per cell and plane the mean of a (cell_px / 2)^2 scan-px box at the
cell centre, R at C's offset, G at M's, B at Y's, the centre placed as read_window places it (the box's centre
(cell_px - 1) / (2 sub) dots into the cell), one bilinear lookup in the box-filtered scan.  At read_window's
offsets it reproduces read_window's X to within read_window's second interpolation (check_reproduction).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from scipy import ndimage

from measure.cmy_probe.bands import WINDOW_CELLS, dot_planes, read_window, window_starts
from measure.e041_mixture_readout import plane_poses, plane_search_px
from measure.e041_probe_readout import Scan, sample_rect
from measure.e041_scale_readout import SEARCH_MM

DPI = 600.0
DOT_MM = 25.4 / DPI
PLANES = ("C", "M", "Y")
SUB_CELLS = 18                   # sub-window side (cells): 2 x 2 per 36-cell window
HALF_ROWS = SUB_CELLS // 2       # the cross-fit's halves (cell rows)
DIFF_SIGMA_MM = 6.7              # the diff arm's Gaussian (see the module docstring)
ROW_BLOCK = 96                   # cell rows per sampler block (bounds the crop)
Rec = dict[str, Any]


def margin_px(sub: int) -> int:
    """read_window's rect margin (OR-ed search + per-plane search) in rect px."""
    return int(round(SEARCH_MM / (DOT_MM / sub))) + plane_search_px(sub)


def read_windows(scan: Scan, A: np.ndarray, x0d: int, y0d: int, cls: np.ndarray, cd: int, white: np.ndarray,
                 sub: int, workers: int, prior: dict | None = None) -> list[Rec]:
    """Every WINDOW_CELLS window of a cell field whose top-left printed dot is (x0d, y0d): bands.read_window at A
    (shifted by the window's prior (dy, dx) dots when given).  Per window: r0, c0, X, per plane the offset d (dy,
    dx printed dots, prior included) whatever its flag, the flags and peaks, the OR-ed registration."""
    m = margin_px(sub)
    rows, cols = cls.shape

    def one(key: tuple[int, int]) -> Rec:
        r0, c0 = key
        py, px = (prior or {}).get(key, (0.0, 0.0))
        win = cls[r0:r0 + WINDOW_CELLS, c0:c0 + WINDOW_CELLS]
        Ak = A.copy()
        Ak[:, 2] += A[:, :2] @ np.array([px, py]) * DOT_MM
        try:
            w = read_window(scan, Ak, x0d + c0 * cd, y0d + r0 * cd, win, cd, DPI, white, sub)
        except ValueError as exc:
            return {"r0": r0, "c0": c0, "skipped": str(exc)}
        d = {pl: (py + (q["oy"] - m) / sub, px + (q["ox"] - m) / sub) for pl, q in w["poses"].items()}
        return {"r0": r0, "c0": c0, "X": w["X"], "d": d, "flags": {pl: q["flag"] for pl, q in w["poses"].items()},
                "peaks": {pl: q["peak"] for pl, q in w["poses"].items()}, "reg_ok": w["reg_ok"],
                "reg_peak": w["reg_peak"], "reg_edge": w["reg_edge"]}
    keys = [(r, c) for r in window_starts(rows, WINDOW_CELLS) for c in window_starts(cols, WINDOW_CELLS)]
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, keys))


def paint(wins: list[Rec], shape: tuple[int, int], key: str = "d", n: int = WINDOW_CELLS) -> np.ndarray:
    """(3, 2, rows, cols) per-cell offsets from per-window offsets, windows painted in order (NaN = unposed)."""
    off = np.full((3, 2) + shape, np.nan)
    for w in wins:
        for k, pl in enumerate(PLANES):
            if pl in w.get(key, {}):
                off[k, :, w["r0"]:w["r0"] + n, w["c0"]:w["c0"] + n] = np.asarray(w[key][pl])[:, None, None]
    return off


def paint_X(wins: list[Rec], shape: tuple[int, int]) -> np.ndarray:
    X = np.full(shape + (3,), np.nan, np.float32)
    for w in wins:
        if "X" in w:
            X[w["r0"]:w["r0"] + WINDOW_CELLS, w["c0"]:w["c0"] + WINDOW_CELLS] = w["X"]
    return X


def window_centres_dots(w: Rec, x0d: int, y0d: int, cd: int, n: int = WINDOW_CELLS) -> tuple[float, float]:
    """(x, y) printed dots of a window's centre."""
    return x0d + (w["c0"] + n / 2) * cd, y0d + (w["r0"] + n / 2) * cd


def fit_plane_affines(groups: list[tuple[list[Rec], int, int, int]], flags: tuple[str, ...] = ("ok",)) -> Rec:
    """Per plane the affine offset(x, y) = a + b x + c y (dots of offset per printed dot of page position) by least
    squares over every window of every group (wins, x0d, y0d, cd) whose plane flag is in `flags`; its rms."""
    out: Rec = {}
    for pl in PLANES:
        P, D = [], []
        for wins, x0d, y0d, cd in groups:
            for w in wins:
                if w.get("flags", {}).get(pl) in flags:
                    P.append(window_centres_dots(w, x0d, y0d, cd))
                    D.append(w["d"][pl])
        P, D = np.asarray(P, float), np.asarray(D, float)
        M = np.column_stack([np.ones(len(P)), P])
        sol, *_ = np.linalg.lstsq(M, D, rcond=None)
        out[pl] = {"coef_dy": sol[:, 0].tolist(), "coef_dx": sol[:, 1].tolist(), "windows": len(P),
                   "rms_dots": float(np.sqrt(((M @ sol - D) ** 2).sum(1).mean()))}
    return out


def affine_field(aff: Rec, x0d: int, y0d: int, cd: int, shape: tuple[int, int]) -> np.ndarray:
    """(3, 2, rows, cols) offsets of the per-plane affines at every cell centre."""
    rows, cols = shape
    yy, xx = np.meshgrid(y0d + (np.arange(rows) + 0.5) * cd, x0d + (np.arange(cols) + 0.5) * cd, indexing="ij")
    off = np.empty((3, 2) + shape)
    for k, pl in enumerate(PLANES):
        for j, key in enumerate(("coef_dy", "coef_dx")):
            a, b, c = aff[pl][key]
            off[k, j] = a + b * xx + c * yy
    return off


def prior_offsets(wins: list[Rec]) -> dict[tuple[int, int], tuple[float, float]]:
    """Per window (r0, c0) the median plane-mean offset (dy, dx) over its 3 x 3 window neighbourhood among windows
    whose three planes are "ok" (5 x 5 where that is empty; absent where both are)."""
    ok = {(w["r0"], w["c0"]): np.mean([w["d"][pl] for pl in PLANES], 0) for w in wins
          if "skipped" not in w and all(w["flags"].get(pl) == "ok" for pl in PLANES)}
    rs = sorted({w["r0"] for w in wins})
    cs = sorted({w["c0"] for w in wins})
    ri, ci = {r: i for i, r in enumerate(rs)}, {c: j for j, c in enumerate(cs)}
    grid = {(ri[r], ci[c]): v for (r, c), v in ok.items()}
    out = {}
    for w in wins:
        i, j = ri[w["r0"]], ci[w["c0"]]
        for k in (1, 2):
            v = [grid[(i + a, j + b)] for a in range(-k, k + 1) for b in range(-k, k + 1) if (i + a, j + b) in grid]
            if v:
                out[(w["r0"], w["c0"])] = tuple(float(t) for t in np.median(v, 0))
                break
    return out


def refine_subwindows(scan: Scan, A: np.ndarray, x0d: int, y0d: int, cls: np.ndarray, cd: int, white: np.ndarray,
                      sub: int, wins: list[Rec], workers: int) -> list[Rec]:
    """Per window and per SUB_CELLS sub-window: the per-plane poses (plane_poses, +/- 3 dots around the window's
    plane-mean offset) on all of its cells ("d", "flags"), on its top HALF_ROWS - 1 rows ("d0"/"flags0") and on its
    bottom HALF_ROWS - 1 rows ("d1"/"flags1"); r0, c0 in cells."""
    m = margin_px(sub)
    step = DOT_MM / sub
    pp = plane_search_px(sub)
    cp = cd * sub
    n_px = SUB_CELLS * cp

    def one(w: Rec) -> list[Rec]:
        if "skipped" in w or not w.get("d"):
            return []
        base = np.mean([w["d"][pl] for pl in w["d"]], axis=0)
        by, bx = int(round(base[0] * sub)), int(round(base[1] * sub))
        use = {}
        for half, (ra, rb) in (("0", (0, HALF_ROWS - 1)), ("1", (HALF_ROWS + 1, SUB_CELLS))):
            u = np.zeros((n_px + 2 * m,) * 2, bool)
            u[m + by + ra * cp:m + by + rb * cp, m + bx:m + bx + n_px] = True
            use[half] = u
        res = []
        for a in range(0, WINDOW_CELLS, SUB_CELLS):
            for b in range(0, WINDOW_CELLS, SUB_CELLS):
                r0, c0 = w["r0"] + a, w["c0"] + b
                win = cls[r0:r0 + SUB_CELLS, c0:c0 + SUB_CELLS]
                if win.shape != (SUB_CELLS, SUB_CELLS):
                    continue
                planes = dot_planes(win, cd)
                k = np.arange(n_px + 2 * m)
                xd, yd = x0d + c0 * cd, y0d + r0 * cd
                rec: Rec = {"r0": r0, "c0": c0}
                try:
                    rect = sample_rect(scan, A, xd * DOT_MM + (k - m) * step, yd * DOT_MM + (k - m) * step)
                    for tag, u in (("", None), ("0", use["0"]), ("1", use["1"])):
                        poses = plane_poses(rect, planes, m + base[0] * sub, m + base[1] * sub, white, pp, sub, u)
                        rec["d" + tag] = {pl: ((q["oy"] - m) / sub, (q["ox"] - m) / sub) for pl, q in poses.items()}
                        rec["flags" + tag] = {pl: q["flag"] for pl, q in poses.items()}
                except ValueError:
                    continue
                res.append(rec)
        return res
    with ThreadPoolExecutor(workers) as ex:
        return [s for part in ex.map(one, wins) for s in part]


def fine_field(win_off: np.ndarray, subs: list[Rec], crossfit: bool = True) -> np.ndarray:
    """The window offsets with sub-window plane offsets painted over them: cross-fitted (the top HALF_ROWS rows at
    the bottom half's pose and the reverse, where that half-fit is "ok") or, crossfit False, the all-cell fit."""
    off = win_off.copy()
    n = SUB_CELLS
    for s in subs:
        for k, pl in enumerate(PLANES):
            if not crossfit:
                if s["flags"].get(pl) == "ok":
                    sl = (slice(s["r0"], s["r0"] + n), slice(s["c0"], s["c0"] + n))
                    off[(k, slice(None)) + sl] = np.asarray(s["d"][pl])[:, None, None]
                continue
            for rows, src in (((0, HALF_ROWS), "1"), ((HALF_ROWS, n), "0")):
                if s.get(f"flags{src}", {}).get(pl) != "ok":
                    continue
                sl = (slice(s["r0"] + rows[0], s["r0"] + rows[1]), slice(s["c0"], s["c0"] + n))
                off[(k, slice(None)) + sl] = np.asarray(s[f"d{src}"][pl])[:, None, None]
    return off


def diff_field(win_off: np.ndarray, wins: list[Rec], x0d: int, y0d: int, cd: int, sigma_mm: float = DIFF_SIGMA_MM,
               smooth: bool = True) -> np.ndarray:
    """C at its window offset; M and Y at C's plus the window differential (pl - C) smoothed by a Gaussian of
    sigma_mm over the window grid (NaN-aware, "ok" windows only); smooth False: no differential (common)."""
    off = win_off.copy()
    off[1], off[2] = off[0], off[0]
    if not smooth:
        return off
    rs, cs = sorted({w["r0"] for w in wins}), sorted({w["c0"] for w in wins})
    ri, ci = {r: i for i, r in enumerate(rs)}, {c: j for j, c in enumerate(cs)}
    pitch_mm = WINDOW_CELLS * cd * DOT_MM
    for k, pl in ((1, "M"), (2, "Y")):
        G, Wt = np.zeros((2, len(rs), len(cs))), np.zeros((len(rs), len(cs)))
        for w in wins:
            if w.get("flags", {}).get(pl) == "ok" and w["flags"].get("C") == "ok":
                G[:, ri[w["r0"]], ci[w["c0"]]] = np.subtract(w["d"][pl], w["d"]["C"])
                Wt[ri[w["r0"]], ci[w["c0"]]] = 1.0
        s = sigma_mm / pitch_mm
        den = ndimage.gaussian_filter(Wt, s, mode="nearest")
        D = np.stack([ndimage.gaussian_filter(G[j], s, mode="nearest") for j in (0, 1)]) / np.maximum(den, 1e-9)
        for w in wins:
            i, j = ri[w["r0"]], ci[w["c0"]]
            sl = (slice(w["r0"], w["r0"] + WINDOW_CELLS), slice(w["c0"], w["c0"] + WINDOW_CELLS))
            for a in (0, 1):
                off[k, a][sl] = off[0, a][sl] + D[a, i, j]
    return off


def sample_field(scan: Scan, A: np.ndarray, x0d: int, y0d: int, cd: int, sub: int, off: np.ndarray) -> np.ndarray:
    """(rows, cols, 3) per cell: R at C's offset, G at M's, B at Y's (off (3, 2, rows, cols) dy, dx printed dots;
    a NaN offset reads NaN), each the mean of a (cd sub / 2)^2 scan-px box at the cell centre."""
    rows, cols = off.shape[2:]
    cp = cd * sub
    b = cp // 2
    c_in = (cp - 1) / (2.0 * sub)
    X = np.full((rows, cols, 3), np.nan, np.float32)
    jj = np.arange(cols)
    for i0 in range(0, rows, ROW_BLOCK):
        i1 = min(rows, i0 + ROW_BLOCK)
        ii, JJ = np.meshgrid(np.arange(i0, i1), jj, indexing="ij")
        for k in range(3):
            dy, dx = off[k, 0, i0:i1], off[k, 1, i0:i1]
            ok = np.isfinite(dy) & np.isfinite(dx)
            if not ok.any():
                continue
            y = (y0d + ii * cd + c_in + np.where(ok, dy, 0.0)) * DOT_MM
            x = (x0d + JJ * cd + c_in + np.where(ok, dx, 0.0)) * DOT_MM
            col = A[0, 0] * x + A[0, 1] * y + A[0, 2]
            row = A[1, 0] * x + A[1, 1] * y + A[1, 2]
            r0, r1 = int(np.floor(row.min())) - b - 2, int(np.ceil(row.max())) + b + 3
            c0, c1 = int(np.floor(col.min())) - b - 2, int(np.ceil(col.max())) + b + 3
            if r0 < 0 or c0 < 0 or r1 > scan.h or c1 > scan.w:
                raise ValueError("cell field block outside the scan")
            f = ndimage.uniform_filter(scan.crop(r0, r1, c0, c1, ch=k), size=b, mode="nearest")
            v = ndimage.map_coordinates(f, [row - r0 + 0.5, col - c0 + 0.5], order=1, mode="nearest")
            X[i0:i1, :, k] = np.where(ok, v, np.nan)
    return X


def check_reproduction(X_read: np.ndarray, X_direct: np.ndarray) -> Rec:
    """The direct sampler at the window offsets against read_window's X: mean |difference| and its p99 per channel."""
    ok = np.isfinite(X_read).all(-1) & np.isfinite(X_direct).all(-1)
    d = np.abs(X_read[ok].astype(np.float64) - X_direct[ok])
    return {"cells": int(ok.sum()), "mean_abs": d.mean(0).tolist(), "p99_abs": np.percentile(d, 99, 0).tolist()}

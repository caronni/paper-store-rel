"""Strip-based warp tracker — layer-1 legal registration for the E006 pages.

Known sync strips (6-dot-tall c2 rows at 360-dot pitch, format constants of
the printed page) are template-correlated in windows along x: known content
gives processing gain and — unlike self-clocked lattice phase — NO integer
ambiguity, because the strip content is a unique fingerprint. Each strip
yields absolute (dy, dx) at its y, per x window; between strips the offset
field is interpolated (scanner steps between strips are few and bounded;
payload detectors and the optional self-clock DP refinement, anchored at
BOTH neighboring strips, absorb the residual). This also solves the B2
free-form legality problem: dot fields at 2 px/dot cannot self-clock
(Nyquist), but they can ride strip anchors.

Core functions take raw (array, affine, strip GTs) so the same math runs on
real cal_core scans and on simulator output (synthetic validation in
tests/test_strip_tracker.py against paperholo's measured-warp channel).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
for rel in ("002-calibration-page", "001-engine-characterization"):
    p = str(_HERE.parent / rel)
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, str(_HERE.parents[1] / "src"))


def xcorr_offset(win: np.ndarray, tpl: np.ndarray,
                 max_shift: int) -> tuple[float, float, float]:
    """Normalized cross-correlation peak with parabolic sub-pixel refinement.
    Returns (dy_px, dx_px, quality). win must be larger than tpl by at least
    2*max_shift in both axes; tpl is matched inside it."""
    w = win.astype(np.float64) - float(win.mean())
    t = tpl.astype(np.float64) - float(tpl.mean())
    th, tw = t.shape
    n_y = w.shape[0] - th + 1
    n_x = w.shape[1] - tw + 1
    corr = np.empty((n_y, n_x))
    tn = np.sqrt((t * t).sum()) + 1e-9
    for iy in range(n_y):
        for ix in range(n_x):
            patch = w[iy:iy + th, ix:ix + tw]
            corr[iy, ix] = (patch * t).sum() / (
                np.sqrt((patch * patch).sum()) * tn + 1e-9)
    iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)
    q = float(corr[iy, ix])

    def parab(c, i, n):
        if 0 < i < n - 1:
            a, b, cc_ = c[i - 1], c[i], c[i + 1]
            d = a - 2 * b + cc_
            if abs(d) > 1e-12:
                return float(np.clip((a - cc_) / (2 * d), -0.5, 0.5))
        return 0.0

    sy = parab(corr[:, ix], iy, n_y)
    sx = parab(corr[iy, :], ix, n_x)
    cy = (n_y - 1) / 2.0
    cx = (n_x - 1) / 2.0
    return (iy + sy - cy), (ix + sx - cx), q


def track_strips(arr: np.ndarray, coef: np.ndarray,
                 strips: list[dict], *, win_x_dots: int = 192,
                 step_x_dots: int = 96, margin_dots: int = 8,
                 sub: int = 2, min_q: float = 0.10) -> dict:
    """Measure absolute (dy, dx) in dots at every strip, per x window.

    strips: [{"x_dots", "y_dots", "w_dots", "h_dots", "gt" (H x W {0,1})}].
    Returns {"strip_y": (S,), "x_centers": (S, K), "dy": (S, K),
             "dx": (S, K), "q": (S, K)} with NaN where quality < min_q.
    """
    coef = np.asarray(coef, np.float64)
    out_y, out_xc, out_dy, out_dx, out_q = [], [], [], [], []
    for s in strips:
        gt = s["gt"].astype(np.float64)
        h, w = gt.shape
        xcs, dys, dxs, qs = [], [], [], []
        for x0 in range(0, w - win_x_dots + 1, step_x_dots):
            tpl_bits = gt[:, x0:x0 + win_x_dots]
            # sample a window around the affine-predicted position, sub px/dot
            gx0 = s["x_dots"] + x0 - margin_dots
            gy0 = s["y_dots"] - margin_dots
            gw = win_x_dots + 2 * margin_dots
            gh = h + 2 * margin_dots
            yy, xx = np.mgrid[0:gh * sub, 0:gw * sub].astype(np.float64)
            xd = gx0 + xx / sub
            yd = gy0 + yy / sub
            sx = coef[0] * xd + coef[1] * yd + coef[2]
            sy = coef[3] * xd + coef[4] * yd + coef[5]
            win = ndimage.map_coordinates(arr, [sy, sx], order=1,
                                          mode="nearest")
            tpl = np.kron(1.0 - tpl_bits, np.ones((sub, sub))) * 255.0
            dy_px, dx_px, q = xcorr_offset(win, tpl, margin_dots * sub)
            xcs.append(s["x_dots"] + x0 + win_x_dots / 2)
            dys.append(dy_px / sub)
            dxs.append(dx_px / sub)
            qs.append(q)
        out_y.append(s["y_dots"] + h / 2.0)
        out_xc.append(xcs)
        out_dy.append(dys)
        out_dx.append(dxs)
        out_q.append(qs)
    dy = np.asarray(out_dy)
    dx = np.asarray(out_dx)
    q = np.asarray(out_q)
    dy[q < min_q] = np.nan
    dx[q < min_q] = np.nan
    return {"strip_y": np.asarray(out_y), "x_centers": np.asarray(out_xc),
            "dy": dy, "dx": dx, "q": q}


def _fill_nan_1d(v: np.ndarray) -> np.ndarray:
    v = v.copy()
    bad = np.isnan(v)
    if bad.all():
        return np.zeros_like(v)
    idx = np.arange(v.size)
    v[bad] = np.interp(idx[bad], idx[~bad], v[~bad])
    return v


def offset_at(tr: dict, y_dots: np.ndarray, x_dots: np.ndarray
              ) -> tuple[np.ndarray, np.ndarray]:
    """Bilinear offset field between strips: for each requested (y, x),
    interpolate each strip's window profile at x, then interpolate across
    strip rows in y. Inputs are 1-D (grids are formed as outer product)."""
    sy = tr["strip_y"]
    prof_dy = np.stack([_fill_nan_1d(r) for r in tr["dy"]])
    prof_dx = np.stack([_fill_nan_1d(r) for r in tr["dx"]])
    xc = tr["x_centers"][0]
    at_x_dy = np.stack([np.interp(x_dots, xc, p) for p in prof_dy])
    at_x_dx = np.stack([np.interp(x_dots, xc, p) for p in prof_dx])
    dy = np.empty((y_dots.size, x_dots.size))
    dx = np.empty_like(dy)
    for j in range(x_dots.size):
        dy[:, j] = np.interp(y_dots, sy, at_x_dy[:, j])
        dx[:, j] = np.interp(y_dots, sy, at_x_dx[:, j])
    return dy, dx


def strip_cell_means(arr: np.ndarray, coef: np.ndarray, e: dict, cell: int,
                     tr: dict) -> np.ndarray:
    """Cell means for a payload region sampled at affine + strip-tracked
    offsets (2x2 subsamples per cell)."""
    coef = np.asarray(coef, np.float64)
    ny, nx = e["h_dots"] // cell, e["w_dots"] // cell
    yc = e["y_dots"] + (np.arange(ny) + 0.5) * cell
    xc = e["x_dots"] + (np.arange(nx) + 0.5) * cell
    dy, dx = offset_at(tr, yc, xc)
    yy = yc[:, None] + dy
    xx = xc[None, :] + dx
    out = np.zeros((ny, nx))
    for oy in (-0.25, 0.25):
        for ox in (-0.25, 0.25):
            xs = xx + ox * cell
            ys = yy + oy * cell
            sx = coef[0] * xs + coef[1] * ys + coef[2]
            sy_ = coef[3] * xs + coef[4] * ys + coef[5]
            out += ndimage.map_coordinates(arr, [sy_, sx], order=1,
                                           mode="nearest")
    return out / 4.0

# Historical record of e033 (supervised per-plane registration on sheet I, the AltaLink Y sinusoid; PAGE-FIELD B3's
# reference), retired from scratch/xerox-v1-20260818/regmap-gt/ 2026-10-09; inputs in the evidence archive.
# Shared helpers, no output of their own; measure_plane_offsets.py and _anchor.py are the entry points.
"""Subpixel plane-offset estimation.

Integer lock by FFT cross-correlation, subpixel by Lucas-Kanade against a
blurred GT template.  Cells are 2 dots = 8 scan px, so the raw correlation
peak is a broad triangle and parabolic interpolation on it is biased; the
LK step against a smoothed model is unbiased under symmetric blur mismatch.
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates


def lk_shift(model: np.ndarray, tgt: np.ndarray, iters: int = 6,
             border: int = 12, init=(0.0, 0.0)):
    """Find (dy,dx) with tgt(y,x) ~ a*model(y-dy, x-dx) + b.

    Returns (dy, dx, corr) -- dy,dx are the displacement of the target
    content relative to the model, in pixels.
    """
    m = model.astype(np.float64)
    t = tgt.astype(np.float64)
    gy, gx = np.gradient(gaussian_filter(m, 1.0))
    H, W = m.shape
    ys, xs = np.mgrid[border:H - border, border:W - border]
    dy, dx = float(init[0]), float(init[1])
    corr = 0.0
    for _ in range(iters):
        # sample the model at shifted coordinates
        ms = map_coordinates(m, [ys - dy, xs - dx], order=3, mode="nearest")
        gys = map_coordinates(gy, [ys - dy, xs - dx], order=1, mode="nearest")
        gxs = map_coordinates(gx, [ys - dy, xs - dx], order=1, mode="nearest")
        tt = t[border:H - border, border:W - border]
        # amplitude + offset by LS on (ms, 1)
        A = np.stack([ms.ravel(), np.ones(ms.size)], axis=1)
        coef, *_ = np.linalg.lstsq(A, tt.ravel(), rcond=None)
        a, b = coef
        if a <= 0:
            return np.nan, np.nan, 0.0
        resid = tt.ravel() - (a * ms.ravel() + b)
        J = np.stack([-a * gys.ravel(), -a * gxs.ravel()], axis=1)
        try:
            step, *_ = np.linalg.lstsq(J, resid, rcond=None)
        except np.linalg.LinAlgError:
            return np.nan, np.nan, 0.0
        dy += float(step[0])
        dx += float(step[1])
        if abs(step[0]) < 1e-4 and abs(step[1]) < 1e-4:
            break
        if abs(dy) > 30 or abs(dx) > 30:
            return np.nan, np.nan, 0.0
    # final correlation quality
    ms = map_coordinates(m, [ys - dy, xs - dx], order=3, mode="nearest")
    tt = t[border:H - border, border:W - border]
    mm = ms - ms.mean(); tv = tt - tt.mean()
    den = np.sqrt((mm * mm).sum() * (tv * tv).sum())
    corr = float((mm * tv).sum() / den) if den > 0 else 0.0
    return dy, dx, corr


def blur_model(gt_up: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    return gaussian_filter(gt_up.astype(np.float32), sigma)

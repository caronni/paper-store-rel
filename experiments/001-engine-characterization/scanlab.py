"""Scan-side utilities for experiment 001 — registration, warp, cell decode.

Consolidates the decoder progression from runs 001.2/001.3/001.4 (RESULTS log):
v1 global affine -> v2 corner affine -> v3 dense warp field -> v4 stepped warp
+ blind soft output. Alignment, not the channel, dominated early BER readings,
so the load-bearing pieces are:

- fiducial registration with ORIENTATION disambiguation (the 4-corners+center
  cross layout is 180-degree symmetric; the orientation square breaks the tie);
- a dense local warp field per patch (grid of correlation windows -> 2nd-order
  polynomial per axis) PLUS a step-preserving y-residual profile (v4): the
  engine's process-direction transport has discrete steps (~0.3-1.2 dots) that
  no smooth model can follow — per-window-row medians of the poly residuals,
  linearly interpolated, track them (run 001.4 killed v3's error bands);
- a blind soft stage (v4): local percentile level fields -> normalized z ->
  2-component Gaussian EM -> per-cell LLRs. Ground truth is used for
  registration templates and SCORING only; decisions never see it.

These tools are for fiducialed SCRATCH sheets only (DESIGN.md R3 exempts them);
archive decoding uses paperholo.sync (lattice + pilots, no fiducials).
"""
from __future__ import annotations

from itertools import permutations
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates, median_filter, percentile_filter

SCAN_DPI = 1200
HW_DPI = 600
S = SCAN_DPI / HW_DPI  # scan px per printer dot


def levels(scan: np.ndarray) -> tuple[float, float, float]:
    """(white, black, midpoint threshold) from robust percentiles."""
    white = float(np.percentile(scan, 90))
    black = float(np.percentile(scan, 1))
    return white, black, (white + black) / 2


def dark_blobs(scan: np.ndarray, thresh: float, block: int = 8, min_fill: float = 0.15):
    """Connected components of a block-reduced dark mask: (x0, y0, w, h) px."""
    dark = scan < thresh
    hb, wb = scan.shape[0] // block, scan.shape[1] // block
    blk = dark[: hb * block, : wb * block].reshape(hb, block, wb, block).mean(axis=(1, 3))
    cand = blk > min_fill
    lbl = np.zeros_like(cand, dtype=int)
    cur = 0
    out = []
    for i in range(hb):
        for j in range(wb):
            if cand[i, j] and lbl[i, j] == 0:
                cur += 1
                st = [(i, j)]
                cells = []
                while st:
                    y, x = st.pop()
                    if 0 <= y < hb and 0 <= x < wb and cand[y, x] and lbl[y, x] == 0:
                        lbl[y, x] = cur
                        cells.append((y, x))
                        st += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
                ys = [c[0] for c in cells]
                xs = [c[1] for c in cells]
                out.append((min(xs) * block, min(ys) * block,
                            (max(xs) - min(xs) + 1) * block, (max(ys) - min(ys) + 1) * block))
    return out


def register_fiducials(scan: np.ndarray, manifest: dict) -> tuple[np.ndarray, float, float]:
    """Affine print-dots -> scan-px from the 5 crosses; orientation-square tiebreak.

    Returns (coef[a,b,c,d,e,f], white, black) with sx = a*px + b*py + c etc.
    """
    white, black, thr = levels(scan)
    cross_px = 63 * S
    cands = []
    for x0, y0, w, h in dark_blobs(scan, thr):
        if not (0.6 * cross_px < w < 1.8 * cross_px and 0.6 * cross_px < h < 1.8 * cross_px):
            continue
        sub = scan[y0 : y0 + h, x0 : x0 + w] < thr
        if 0.04 < sub.mean() < 0.30:  # cross fill ratio, excludes squares/text
            ys, xs = np.nonzero(sub)
            cands.append((x0 + xs.mean(), y0 + ys.mean()))
    fids = manifest["fiducials"]
    P = np.array([[f["cx_dots"], f["cy_dots"]] for f in fids.values()], float)
    hyps = []
    for cs in permutations(range(len(cands)), len(P)):
        Q = np.array([cands[i] for i in cs], float)
        A = np.zeros((2 * len(P), 6))
        v = np.zeros(2 * len(P))
        for i, (px, py) in enumerate(P):
            A[2 * i, :3] = (px, py, 1)
            A[2 * i + 1, 3:] = (px, py, 1)
            v[2 * i], v[2 * i + 1] = Q[i]
        coef, *_ = np.linalg.lstsq(A, v, rcond=None)
        rms = float(np.sqrt(np.mean((A @ coef - v) ** 2)))
        if rms < 5.0:
            hyps.append((rms, coef))
    if not hyps:
        raise RuntimeError(f"no fiducial hypothesis fit (candidates: {len(cands)})")
    osq = next(p for p in manifest["patches"] if p["kind"] == "orientation")
    best = None
    for rms, coef in hyps:
        img = warp_dots(scan, coef, osq["x_dots"], osq["y_dots"], osq["w_dots"], osq["h_dots"])
        ink = float((img < thr).mean())
        score = ink - rms / 100
        if best is None or score > best[0]:
            best = (score, coef, rms, ink)
    _, coef, rms, ink = best
    if ink < 0.5:
        raise RuntimeError(f"orientation square not found (ink={ink:.2f}) — bad registration")
    return coef, white, black


def warp_dots(scan, coef, x0, y0, w, h, sub: int = 2) -> np.ndarray:
    """Resample the scan onto the print-dot grid [x0,x0+w) x [y0,y0+h), sub px/dot."""
    a, b, c, d, e, f = coef
    gy, gx = np.mgrid[0 : int(h * sub), 0 : int(w * sub)] / sub
    sx = a * (x0 + gx) + b * (y0 + gy) + c
    sy = d * (x0 + gx) + e * (y0 + gy) + f
    return map_coordinates(scan, [sy, sx], order=1, mode="nearest")


def xcorr_offset(a: np.ndarray, b: np.ndarray, max_shift: int = 24):
    """(dy, dx, quality): shift aligning b to a, parabolic subpixel refinement."""
    A = np.fft.rfft2(a - a.mean())
    B = np.fft.rfft2(b - b.mean())
    c = np.fft.fftshift(np.fft.irfft2(A * np.conj(B), s=a.shape))
    cy, cx = np.array(c.shape) // 2
    win = c[cy - max_shift : cy + max_shift + 1, cx - max_shift : cx + max_shift + 1]
    ky, kx = np.unravel_index(np.argmax(win), win.shape)

    def para(v, i):
        if 0 < i < len(v) - 1:
            denom = 2 * (v[i - 1] - 2 * v[i] + v[i + 1])
            if abs(denom) > 1e-12:
                return i + (v[i - 1] - v[i + 1]) / denom
        return float(i)

    q = float(win[ky, kx] / (a.std() * b.std() * a.size + 1e-12))
    return para(win[:, kx], ky) - max_shift, para(win[ky, :], kx) - max_shift, q


def level_fields(m: np.ndarray, size_cells: tuple[int, int] = (11, 51)
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Blind local (white, black) level fields from the sampled cell means.

    80th/20th percentile over a footprint narrow in y, wide in x — tracks the
    y-structured banding/gain ripple without smoothing across it. At ~50% ink
    density both percentiles land robustly inside their class.
    """
    white = percentile_filter(m, 80, size=size_cells, mode="nearest")
    black = percentile_filter(m, 20, size=size_cells, mode="nearest")
    return white, black


def fit_gmm_z(z: np.ndarray, mu_init: tuple[float, float] = (0.1, 0.9),
              max_iters: int = 40, tol: float = 1e-4) -> dict:
    """2-component 1-D Gaussian EM on normalized levels z. Blind, deterministic
    (fixed init mu 0.1/0.9, iterate to tol or max_iters). 0=white, 1=ink.

    Mixture weights are PINNED at 0.5/0.5: the scrambler fixes ink density at
    50% by construction, and freeing pi lets the wide white component swallow
    the c2 gain-bridge mass (EM drifts without settling, measured 001.4).
    """
    zf = z.ravel().astype(np.float64)
    mu = np.array(mu_init, float)
    sig = np.array([0.15, 0.15])
    dmu = np.inf
    n_iters = 0
    for n_iters in range(1, max_iters + 1):
        logp = -0.5 * ((zf[:, None] - mu) / sig) ** 2 - np.log(sig)
        logp -= logp.max(axis=1, keepdims=True)
        r = np.exp(logp)
        r /= r.sum(axis=1, keepdims=True)
        n = r.sum(axis=0)
        mu_new = (r * zf[:, None]).sum(axis=0) / n
        sig = np.sqrt((r * (zf[:, None] - mu_new) ** 2).sum(axis=0) / n)
        sig = np.maximum(sig, 1e-3)
        dmu = float(np.abs(mu_new - mu).max())
        mu = mu_new
        if dmu < tol:
            break
    if mu[0] > mu[1]:  # defensive: keep component 0 = white (low z)
        mu, sig = mu[::-1], sig[::-1]
    return {"pi": [0.5, 0.5], "mu": mu.tolist(), "sigma": sig.tolist(),
            "n_iters": n_iters, "dmu_last_iter": dmu, "converged": dmu < 1e-3}


def llr_field(z: np.ndarray, gmm: dict) -> np.ndarray:
    """Per-cell LLR log p(z|ink) - log p(z|white) from the fitted mixture.

    Flat prior (the scrambled source is 50/50 by construction). Positive = ink.
    """
    (mu0, mu1), (s0, s1) = gmm["mu"], gmm["sigma"]
    return ((-0.5 * ((z - mu1) / s1) ** 2 - np.log(s1))
            - (-0.5 * ((z - mu0) / s0) ** 2 - np.log(s0)))


def context_detect(z: np.ndarray, llr_global: np.ndarray, gmm_global: dict,
                   conf_llr: float = 2.0, min_cells: int = 200,
                   iters: int = 2) -> np.ndarray:
    """Decision-directed 16-context detector (ICM): per-4-neighbour-pattern
    class statistics re-estimated from cells whose neighbours are all confident.

    Blind: contexts come from the detector's own decisions, never GT. Attacks
    the measured development nonlinearities — white cells in inky contexts
    close partially (shifted dark), lone ink cells in white contexts
    under-develop (shifted bright) — that a single global mixture cannot model.
    Contexts with <min_cells usable cells or unseparated classes fall back to
    the global LLR. Returns the context-conditional LLR field.
    """
    llr = llr_global
    for _ in range(iters):
        bits = llr > 0
        conf = np.abs(llr) > conf_llr
        nb = np.pad(bits, 1, mode="edge")
        cf = np.pad(conf, 1, mode="constant")  # border nbrs never confident
        ctx = (8 * nb[:-2, 1:-1] + 4 * nb[2:, 1:-1]
               + 2 * nb[1:-1, 2:] + nb[1:-1, :-2])
        usable = cf[:-2, 1:-1] & cf[2:, 1:-1] & cf[1:-1, 2:] & cf[1:-1, :-2]
        llr_new = np.array(llr_global)
        for c in range(16):
            sel = (ctx == c) & usable
            if sel.sum() < min_cells:
                continue
            g = fit_gmm_z(z[sel], mu_init=tuple(gmm_global["mu"]))
            (mu0, mu1), (s0, s1) = g["mu"], g["sigma"]
            if mu1 - mu0 < (s0 + s1) / 2:  # classes not separated: fall back
                continue
            csel = ctx == c
            llr_new[csel] = llr_field(z[csel], g)
        llr = llr_new
    return llr


def residual_y_profile(scan: np.ndarray, coef: np.ndarray, patch: dict,
                       gt_dots: np.ndarray, cell: int,
                       cx_: np.ndarray, cy_: np.ndarray,
                       band_cell_rows: int = 2, max_shift_px: int = 4,
                       sub: int = 2) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Diagnostic r(y): residual y-offset AFTER affine+poly2, at 1-cell-row
    resolution, via full-width row-band 1-D correlation against the GT template.

    All averaging is spent along x (where the warp is smooth, already removed);
    y-resolution stays at one cell row, so ~1-dot transport steps are 50-sigma
    events instead of being blurred over a window. NOT in the correction path —
    feeds the transport-step catalog (ChannelParams) and eyeball checks of step
    positions vs error-map bands.

    Returns (y_centers_dots, r_dots, r_median_dots, quality).
    """
    gt = gt_dots.astype(np.float32)
    h, w = gt.shape
    gy, gx = (np.mgrid[0 : h * sub, 0 : w * sub] / sub).astype(np.float32)
    xn, yn = gx / w, gy / h

    def poly(c: np.ndarray) -> np.ndarray:
        return c[0] + c[1] * xn + c[2] * yn + c[3] * xn * yn + c[4] * xn * xn + c[5] * yn * yn

    a, b, c0, d, e, f = coef
    px = patch["x_dots"] + gx + poly(cx_)
    py = patch["y_dots"] + gy + poly(cy_)
    A = map_coordinates(scan, [d * px + e * py + f, a * px + b * py + c0],
                        order=1, mode="nearest").astype(np.float32)
    del gy, gx, xn, yn, px, py
    T = np.kron(1 - gt, np.ones((sub, sub), np.float32)) * 255

    H = h * sub
    bh = band_cell_rows * cell * sub
    n_bands = h // cell - band_cell_rows + 1  # stepped by 1 cell row
    starts = np.arange(n_bands) * cell * sub
    npx = float(bh * T.shape[1])

    def winsum(rowv: np.ndarray) -> np.ndarray:
        cs = np.concatenate([[0.0], np.cumsum(rowv, dtype=np.float64)])
        return cs[starts + bh] - cs[starts]

    s_t = winsum(T.sum(axis=1))
    var_t = winsum((T * T).sum(axis=1)) - s_t * s_t / npx
    Ap = np.pad(A, ((max_shift_px, max_shift_px), (0, 0)), mode="edge")
    shifts = np.arange(-max_shift_px, max_shift_px + 1)
    Q = np.zeros((len(shifts), n_bands))
    for i, s in enumerate(shifts):
        As = Ap[max_shift_px + s : max_shift_px + s + H]
        s_a = winsum(As.sum(axis=1))
        cov = winsum((As * T).sum(axis=1)) - s_a * s_t / npx
        var_a = winsum((As * As).sum(axis=1)) - s_a * s_a / npx
        Q[i] = cov / np.sqrt(np.maximum(var_a * var_t, 1e-9))

    k = Q.argmax(axis=0)
    qual = Q.max(axis=0)
    r_px = np.empty(n_bands)
    for bnd in range(n_bands):
        ki = int(k[bnd])
        v = Q[:, bnd]
        r_px[bnd] = ki
        if 0 < ki < len(shifts) - 1:
            denom = 2 * (v[ki - 1] - 2 * v[ki] + v[ki + 1])
            if abs(denom) > 1e-12:
                r_px[bnd] = ki + (v[ki - 1] - v[ki + 1]) / denom
    r_dots = (r_px - max_shift_px) / sub
    valid = (k > 0) & (k < len(shifts) - 1) & (qual > np.percentile(qual, 5))
    idx = np.arange(n_bands, dtype=float)
    r_dots = np.interp(idx, idx[valid], r_dots[valid])  # nearest-ish fill of rejects
    r_med = median_filter(r_dots, size=5, mode="nearest")
    y_centers_dots = (np.arange(n_bands) + band_cell_rows / 2) * cell
    return y_centers_dots, r_dots, r_med, qual


def detect_steps(y_centers_dots: np.ndarray, r_med_dots: np.ndarray,
                 thresh_dots: float = 0.25) -> list[tuple[float, float]]:
    """Transport-step catalog: |diff of median-filtered r| > thresh_dots.

    Consecutive detections merge into one step (net magnitude, |d|-weighted
    position). Returns [(y_dots, magnitude_dots), ...].
    """
    d = np.diff(r_med_dots)
    mid = (y_centers_dots[:-1] + y_centers_dots[1:]) / 2
    idx = np.nonzero(np.abs(d) > thresh_dots)[0]
    runs: list[list[int]] = []
    for i in idx:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(int(i))
        else:
            runs.append([int(i)])
    out = []
    for run in runs:
        wgt = np.abs(d[run])
        y = float(np.average(mid[run], weights=wgt))
        mag = float(r_med_dots[run[-1] + 1] - r_med_dots[run[0]])
        out.append((y, mag))
    return out


def decode_cells(scan, coef, patch: dict, gt_dots: np.ndarray, cell: int,
                 win_x: int = 128, win_y: int = 64,
                 step_x: int = 64, step_y: int = 32,
                 min_quality: float = 0.02,
                 edge_windows: bool = True, y_profile: bool = True,
                 soft: bool = True, diagnostics: bool = True) -> dict:
    """v4 decode: dense warp field (poly2 + step-preserving y-residual profile)
    -> box-sample cells -> hard bits (local median) + blind soft LLRs.

    v3 behaviour (regression tables) = decode_cells(..., win_y=128, step_y=64,
    edge_windows=False, y_profile=False, soft=False, diagnostics=False).

    Ground truth is used for registration templates and SCORING only (ber_llr,
    mi_bits, conf_curve); every decision statistic — median threshold, level
    fields, GMM — is estimated blind from the scan.
    """
    gt = gt_dots.astype(np.float32)
    h, w = gt.shape
    nc = h // cell
    gt_cells = gt[::cell, ::cell][:nc, :nc].astype(np.uint8)

    ys = list(range(win_y // 2, h - win_y // 2 + 1, step_y))
    xs = list(range(win_x // 2, w - win_x // 2 + 1, step_x))
    if edge_windows:  # no cell outside measurement support (kills extrapolation)
        if ys[-1] != h - win_y // 2:
            ys.append(h - win_y // 2)
        if xs[-1] != w - win_x // 2:
            xs.append(w - win_x // 2)

    pts, offs = [], []
    for wy in ys:
        for wx in xs:
            sw = warp_dots(scan, coef, patch["x_dots"] + wx - win_x // 2,
                           patch["y_dots"] + wy - win_y // 2, win_x, win_y)
            tpl = np.kron(1 - gt[wy - win_y // 2 : wy + win_y // 2,
                                 wx - win_x // 2 : wx + win_x // 2],
                          np.ones((2, 2), np.float32)) * 255
            dy, dx, q = xcorr_offset(sw, tpl)
            if q > min_quality:
                pts.append((wx, wy))
                offs.append((dx / 2, dy / 2))  # scan px -> dots
    pts, offs = np.array(pts, float), np.array(offs, float)

    def design(xy):
        x, y = xy[:, 0] / w, xy[:, 1] / h
        return np.column_stack([np.ones_like(x), x, y, x * y, x * x, y * y])

    keep = np.ones(len(pts), bool)
    cx_ = cy_ = None
    for _ in range(2):
        D = design(pts[keep])
        cx_, *_ = np.linalg.lstsq(D, offs[keep, 0], rcond=None)
        cy_, *_ = np.linalg.lstsq(D, offs[keep, 1], rcond=None)
        rx = offs[:, 0] - design(pts) @ cx_
        ry = offs[:, 1] - design(pts) @ cy_
        keep = np.hypot(rx, ry) < max(1.5, np.percentile(np.hypot(rx, ry)[keep], 90))

    # step-preserving y-residual profile: per-window-row median of the poly2
    # y-residuals, linearly interpolated across cell centres. dx stays poly2
    # (no vertical bands observed — the fast-scan axis has no transport steps).
    ry_all = offs[:, 1] - design(pts) @ cy_
    prof_wy = np.array(sorted(set(pts[keep][:, 1])))
    prof_v = np.array([np.median(ry_all[keep & (pts[:, 1] == wy)]) for wy in prof_wy])

    gy, gx = np.mgrid[0:nc, 0:nc].astype(np.float64)
    ccx = gx * cell + cell / 2
    ccy = gy * cell + cell / 2
    Dc = design(np.column_stack([ccx.ravel(), ccy.ravel()]))
    wx_ = (Dc @ cx_).reshape(nc, nc)
    wy_ = (Dc @ cy_).reshape(nc, nc)
    if y_profile:
        wy_ = wy_ + np.interp(ccy[:, 0], prof_wy, prof_v)[:, None]
    a, b, c, d, e, f = coef
    acc = np.zeros((nc, nc))
    for oy in (-cell / 4, cell / 4):
        for ox in (-cell / 4, cell / 4):
            px_ = patch["x_dots"] + ccx + wx_ + ox
            py_ = patch["y_dots"] + ccy + wy_ + oy
            sx = a * px_ + b * py_ + c
            sy = d * px_ + e * py_ + f
            acc += map_coordinates(scan, [sy, sx], order=1, mode="nearest")
    m = acc / 4
    med = median_filter(m, size=31, mode="nearest")
    bits = (m < med).astype(np.uint8)
    err = bits != gt_cells
    nb = np.zeros_like(err, bool)
    nb[1:, :] |= err[:-1, :]
    nb[:-1, :] |= err[1:, :]
    nb[:, 1:] |= err[:, :-1]
    nb[:, :-1] |= err[:, 1:]
    out = {
        "ber": float(err.mean()),
        "errors": int(err.sum()),
        "cells": int(err.size),
        "clustered": float((err & nb).sum() / max(err.sum(), 1)),
        "err_map": err,
        "means": m,
        "gt_cells": gt_cells,
        "warp_windows_used": int(keep.sum()),
        "warp_windows_total": int(len(pts)),
        "warp_y_range_dots": (float(offs[:, 1].min()), float(offs[:, 1].max())) if len(offs) else (0.0, 0.0),
        "poly_resid_rms_dots": float(np.sqrt(np.mean(ry_all[keep] ** 2))),
        "yprof_win_dots": (prof_wy, prof_v),
    }

    if soft:
        white_f, black_f = level_fields(m)
        z = (white_f - m) / np.maximum(white_f - black_f, 1e-3)  # ~0 white, ~1 ink
        gmm = fit_gmm_z(z)
        llr = llr_field(z, gmm)
        llr_ctx = context_detect(z, llr, gmm)
        # --- scoring only below this line (GT allowed) ---
        gtb = gt_cells.astype(bool)
        sgn = 2.0 * gt_cells - 1.0  # +1 ink, -1 white; llr positive = ink

        def score(lv: np.ndarray) -> dict:
            e = (lv > 0) != gtb
            mi = 1.0 - float(np.mean(np.logaddexp(0.0, -sgn * lv))) / np.log(2.0)
            u_grid = np.linspace(0.0, 0.5, 26)
            t_grid = np.quantile(np.abs(lv), u_grid)
            curve = [(float(u), float(t), float(e[np.abs(lv) >= t].mean()))
                     for u, t in zip(u_grid, t_grid)]
            qe = np.quantile(np.abs(lv), np.linspace(0, 1, 11))
            rel = []
            for lo, hi in zip(qe[:-1], qe[1:]):
                sel = (np.abs(lv) >= lo) & (np.abs(lv) < hi if hi < qe[-1] else np.abs(lv) <= hi)
                if sel.sum():
                    rel.append({"llr_lo": float(lo), "llr_hi": float(hi), "n": int(sel.sum()),
                                "pred_err": float(np.mean(1 / (1 + np.exp(np.abs(lv[sel]))))),
                                "emp_err": float(e[sel].mean())})
            return {"ber": float(e.mean()), "mi_bits": mi,
                    "conf_curve": curve,  # (uncertain_frac, llr_thresh, ber_confident)
                    "reliability": rel}

        sc, sc_ctx = score(llr), score(llr_ctx)
        out["soft"] = {
            "gmm": gmm, "llr": llr, "llr_ctx": llr_ctx, "z": z,
            "ber_llr": sc["ber"], "mi_bits": sc["mi_bits"],
            "conf_curve": sc["conf_curve"], "reliability": sc["reliability"],
            "ber_llr_ctx": sc_ctx["ber"], "mi_bits_ctx": sc_ctx["mi_bits"],
            "conf_curve_ctx": sc_ctx["conf_curve"],
            "reliability_ctx": sc_ctx["reliability"],
        }

    if diagnostics:
        y_c, r_raw, r_med, qual = residual_y_profile(scan, coef, patch, gt, cell, cx_, cy_)
        out["diag_yprof"] = {"y_dots": y_c, "r_dots": r_raw, "r_med_dots": r_med,
                             "quality": qual}
        out["steps"] = detect_steps(y_c, r_med)
    return out

"""Between-strip warp refinement — the stage 006.1 reserved.

The strip tracker (strip_tracker.py) gives ABSOLUTE (dy, dx) at every 360-dot
sync strip, then LINEARLY interpolates the offset field between adjacent
strips. 006.1 + 007.6 measured the cost of that straight line: the true warp
BOWS between strips (a smooth sub-strip wander of up to ~2 dots at mid-gap),
so B1 c2-K ctx BER roughly doubles 108-168 dots from a strip. Strip-vs-genie
gap: home +5.82 pp, office +3.37 pp.

This module recovers the mid-gap bow WITHOUT ground truth, then resamples the
payload at the refined field. It is a REFINEMENT on top of the strip-tracked
sampling in analyze_e006bw.py (strip_tracker.offset_at / strip_cell_means):

  1. Self-clock the payload's own c2 lattice: the gradient-magnitude field of
     the band, DFT'd at the cell frequency in inverse-affine dot coordinates,
     in y-sub-bands (off_y(y)) — the dd_warp §5.1 phase estimator, applied per
     band (attribution: dd_warp.selfclock_*). Y-ONLY: the mid-gap residual is
     a y(y) transport wander; the x-axis comb is already carried by the strip
     tracker's per-x-window dx (an x-bow from the c2 payload was measured
     harmful — see refined_offset_field).
  2. Resolve the integer-cell branch AND the phase estimator's arbitrary
     reference using the TWO bracketing strip anchors: the strips pin both
     endpoints, so between them only the SHAPE of the bow is unknown. Fit a
     low-order (quadratic) quality-weighted curve to (phase - strip-line) in
     normalized band coordinates, force it to zero at both anchors, shrink by
     a frozen factor, and add it to the strip line.
  3. Resample cell means at affine + refined offsets (2x2 subsamples/cell).

Legal: inputs are the marks affine, the known strip content (format
constant), and the scan's own lattice. No ground truth enters. The caller
scores externally exactly as with strip_cell_means.

Frozen constants (calibrated once against the home s2 genie warp, then held
as code constants — NOT per-sheet parameters): BOW_DEG=2, BOW_SHRINK=0.75,
PHASE_BAND_DOTS=24. Units are in names throughout.

MEASURED (2026-07-07, e006bw B1 c2-K, this module vs strip_cell_means):
  HOME M281 grey scans (3): mean B1 ctx +1.6 pp (s2 +1.05 / s3 +2.40 /
    s4 +1.33 at shrink 0.75); the mid-gap BER-vs-distance gradient FLATTENS
    (the 120-168-dot-from-strip bin, worst under linear interp, improves the
    most every scan). Multi-scan combining stabilizes the occasional
    self-clock branch miss (per-scan losses land on different bands).
    Closes ~28% of the +5.82 pp strip-vs-genie gap; short of the ~3 pp
    aspiration — the self-clock phase at c2 is genuinely noisy (payload is a
    50%-random lattice, weak DFT signal).
  OFFICE AltaLink scan: HARMFUL (-4.5 pp at shrink 0.75). That print's
    <5-dot feature erosion (007.6) weakens the c2 lattice; the self-clock
    picks wrong bows where strip-alone is already near-genie. The bow gain
    is ENGINE/SCAN-CONDITIONAL and needs a legal go/no-go gate (self-clock
    quality alone does not separate the two engines cleanly — future work).
    Do NOT apply blindly on AltaLink-class prints.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
for rel in ("../002-calibration-page", "../001-engine-characterization"):
    p = str((_HERE / rel).resolve())
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, str(_HERE))

import cal_core as cc          # noqa: E402
import strip_tracker as st     # noqa: E402

# --- frozen geometric constants (calibrated once vs home-s2 genie warp) ---
BOW_DEG = 2               # a mid-gap bow is a low-order wander, not per-band phase
BOW_SHRINK = 0.75         # the noisy self-clock overshoots; trust 3/4 of it
PHASE_BAND_DOTS = 24      # sub-band height/width for the lattice DFT (>=12 cells)
ANCHOR_TOL_DOTS = 6       # a strip counts as "bracketing" within this of the edge


def _band_gradient_lattice(
    arr: np.ndarray, coef: np.ndarray, e: dict
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Gradient-magnitude map of the band in scan pixels, plus the
    inverse-affine dot coordinates of every pixel. (dd_warp convention.)"""
    coef = np.asarray(coef, np.float64)
    inv = cc.affine_invert(coef)
    cs = np.array([[e["x_dots"], e["y_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"] + e["h_dots"]]],
                  np.float64)
    sx = coef[0] * cs[:, 0] + coef[1] * cs[:, 1] + coef[2]
    sy = coef[3] * cs[:, 0] + coef[4] * cs[:, 1] + coef[5]
    x0, x1 = int(min(sx)) + 2, int(max(sx)) - 2
    y0, y1 = int(min(sy)) + 2, int(max(sy)) - 2
    g = arr[y0:y1, x0:x1]
    gy, gx = np.gradient(g)
    g = np.hypot(gy, gx)
    g = g - g.mean()
    yyy, xxx = np.mgrid[0:g.shape[0], 0:g.shape[1]].astype(np.float64)
    xd = inv[0] * (xxx + x0) + inv[1] * (yyy + y0) + inv[2]
    yd = inv[3] * (xxx + x0) + inv[4] * (yyy + y0) + inv[5]
    return g, yd, xd, x0, y0


def selfclock_axis_phase(
    arr: np.ndarray, coef: np.ndarray, e: dict, cell_dots: int, axis: int,
    band_px_dots: int = PHASE_BAND_DOTS,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wrapped self-clock offset profile along one axis for one band.

    axis=0 -> off_y(y) from full-width y-sub-bands; axis=1 -> off_x(x) from
    full-height x-sub-bands. Phase measured at the cell frequency in
    inverse-affine dot coordinates. Returns (coord_dots, wrapped_off_dots,
    quality), each length n_subbands. No GT, no template.
    """
    g, yd, xd, _, _ = _band_gradient_lattice(arr, coef, e)
    dcoord = yd if axis == 0 else xd
    w = np.exp(-2j * np.pi * dcoord / cell_dots)
    band_px = int(round(band_px_dots * 2))  # ~2 scan-px/dot
    n = g.shape[axis] // band_px
    offs = np.zeros(n)
    quals = np.zeros(n)
    cents = np.zeros(n)
    for i in range(n):
        sl = slice(i * band_px, (i + 1) * band_px)
        band = g[sl] if axis == 0 else g[:, sl]
        ww = w[sl] if axis == 0 else w[:, sl]
        dc = dcoord[sl] if axis == 0 else dcoord[:, sl]
        F = np.sum(band * ww)
        offs[i] = (-np.angle(F) / (2 * np.pi)) * cell_dots
        quals[i] = abs(F) / max(np.abs(band).sum(), 1e-9)
        cents[i] = float(dc.mean())
    return cents, offs, quals


def _anchored_bow(
    coord: np.ndarray, wrapped: np.ndarray, qual: np.ndarray, cell_dots: int,
    a0: float, a1: float, v0: float, v1: float,
    deg: int = BOW_DEG, shrink: float = BOW_SHRINK,
) -> np.ndarray:
    """Bow(coord): the sub-strip warp shape, zero at both strip anchors.

    The two anchors (coord a0/a1, offset v0/v1) define the strip line. The
    self-clock wrapped phase is branch-resolved to that line, its deviation
    (phase - line) is fit by a quality-weighted deg-poly, the endpoint line of
    that fit is removed (so the bow vanishes at both anchors), and the whole
    is shrunk. Returns the bow evaluated at `coord`.
    """
    line = np.interp(coord, [a0, a1], [v0, v1])
    k = np.round((line - wrapped) / cell_dots)
    res = (wrapped + k * cell_dots) - line
    good = np.isfinite(res) & (qual > 0)
    if good.sum() < deg + 1:
        return np.zeros_like(coord)
    # normalize the coordinate to [-1, 1] over the band before polyfit:
    # raw inverse-affine dot y runs to ~6000, and a deg-2 fit on un-centered
    # large abscissae is ill-conditioned (coeffs blow up down the page).
    c0 = 0.5 * (a0 + a1)
    span = max(abs(a1 - a0), 1.0)
    u = 2.0 * (coord - c0) / span
    p = np.poly1d(np.polyfit(u[good], res[good], deg, w=qual[good]))
    ua = 2.0 * (a0 - c0) / span
    ub = 2.0 * (a1 - c0) / span
    end = np.interp(u, [ua, ub], [float(p(ua)), float(p(ub))])
    return shrink * (p(u) - end)


def bracketing_anchors(
    tr: dict, e: dict, tol_dots: float = ANCHOR_TOL_DOTS,
) -> tuple[float, float, float, float] | None:
    """The two strips that bracket band `e` in y, with x-averaged dy anchors.

    Returns (y_top, y_bot, dy_top, dy_bot) or None if a bracket is missing.
    dy at each strip is the mean over its lock-quality-good x windows.
    """
    syc = np.asarray(tr["strip_y"], np.float64)
    sdy = np.array([np.nanmean(r) for r in tr["dy"]])
    ytop = e["y_dots"]
    ybot = e["y_dots"] + e["h_dots"]
    it = int(np.argmin(np.abs(syc - ytop)))
    ib = int(np.argmin(np.abs(syc - ybot)))
    if it == ib or not np.isfinite(sdy[it]) or not np.isfinite(sdy[ib]):
        return None
    # a valid bracket has a strip within tol_dots of each band edge (edges sit
    # ~3 dots from their strip center by layout); reject payloads that are not
    # strip-bracketed on both sides.
    if abs(syc[it] - ytop) > tol_dots or abs(syc[ib] - ybot) > tol_dots:
        return None
    return float(syc[it]), float(syc[ib]), float(sdy[it]), float(sdy[ib])


def refined_offset_field(
    arr: np.ndarray, coef: np.ndarray, e: dict, cell_dots: int, tr: dict,
    yc_dots: np.ndarray, xc_dots: np.ndarray,
    deg: int = BOW_DEG, shrink: float = BOW_SHRINK,
    band_px_dots: int = PHASE_BAND_DOTS,
) -> tuple[np.ndarray, np.ndarray]:
    """Refined (dy, dx) offset field at cell centers (yc_dots x xc_dots).

    Base = strip_tracker.offset_at (strip linear interp). Refinement = a
    self-clock anchored Y-BOW added to dy (function of y, broadcast over x).

    Y-ONLY by design (measured, 2026-07-07): the mid-gap residual is a smooth
    y(y) transport wander (scanner steps + printer y-wander) between the two
    360-dot strips; the x-axis (CCD comb + x-wander) is a full-column feature
    already carried by the strip tracker's PER-X-WINDOW dx measurement at each
    strip row (offset_at interpolates that in x). An x-bow from the payload's
    own c2 lattice was tried and REJECTED: the narrow full-height x-sub-band of
    a 50%-random c2 field has almost no lattice signal, the bow it invents
    doubles-to-triples BER on the lower bands. dx is left as the strip field.

    Falls back to the pure strip field on any band without a strip bracket.
    """
    dy, dx = st.offset_at(tr, yc_dots, xc_dots)     # (ny, nx) base field
    br = bracketing_anchors(tr, e)
    if br is None:
        return dy, dx
    y_top, y_bot, dy_top, dy_bot = br

    # y-bow: the sub-strip mid-gap wander, anchored at the two bracketing strips
    ys_c, y_wr, y_q = selfclock_axis_phase(arr, coef, e, cell_dots, 0,
                                           band_px_dots)
    y_bow = _anchored_bow(ys_c, y_wr, y_q, cell_dots,
                          y_top, y_bot, dy_top, dy_bot, deg, shrink)
    dy = dy + np.interp(yc_dots, ys_c, y_bow)[:, None]
    return dy, dx


def refined_cell_means(
    arr: np.ndarray, coef: np.ndarray, e: dict, cell_dots: int, tr: dict,
    *, deg: int = BOW_DEG, shrink: float = BOW_SHRINK,
    band_px_dots: int = PHASE_BAND_DOTS,
) -> np.ndarray:
    """strip_tracker.strip_cell_means with the between-strip bow refinement.

    Drop-in replacement for st.strip_cell_means(arr, coef, e, cell, tr):
    same 2x2-subsample cell-mean estimator, refined offset field.
    """
    coef = np.asarray(coef, np.float64)
    ny, nx = e["h_dots"] // cell_dots, e["w_dots"] // cell_dots
    yc = e["y_dots"] + (np.arange(ny) + 0.5) * cell_dots
    xc = e["x_dots"] + (np.arange(nx) + 0.5) * cell_dots
    dy, dx = refined_offset_field(arr, coef, e, cell_dots, tr, yc, xc,
                                  deg=deg, shrink=shrink,
                                  band_px_dots=band_px_dots)
    yy = yc[:, None] + dy
    xx = xc[None, :] + dx
    out = np.zeros((ny, nx))
    for oy in (-0.25, 0.25):
        for ox in (-0.25, 0.25):
            xs = xx + ox * cell_dots
            ys = yy + oy * cell_dots
            sx = coef[0] * xs + coef[1] * ys + coef[2]
            sy = coef[3] * xs + coef[4] * ys + coef[5]
            out += ndimage.map_coordinates(arr, [sy, sx], order=1,
                                           mode="nearest")
    return out / 4.0

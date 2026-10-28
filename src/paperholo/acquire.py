"""Layer 2 decoder axis, Stage 0 — blind cell-grid acquisition (DESIGN.md §5.1).

Locks the printed cell lattice on a scan fragment with no fiducials and no GT.
Pipeline (each stage's design was forced by a measured failure of the simpler
contract-suggested alternative; see the per-function docstrings):
1. global pitch/angle from the gradient-magnitude FFT (paperholo.sync idiom),
   refined per axis from the median circular band-to-band phase difference
   (the global FFT line is warp-smeared and its in-smear peak is noise);
2. SEPARABLE band-phase profiles phi_v(v)/phi_u(u) from lattice-DFT phasors
   on non-overlapping strips coherently integrated over the full cross axis
   (dd_warp convention: offset = -angle(F)/(2pi)*cell on the gradient map;
   separable matches the measured channel — steps/wander/y-scale are y(y),
   the CCD comb x(x), 002.0b attribution; a 2-D per-window phase field fails
   the lock budget: per-window x-phase sigma ~0.6 px measured);
3. branch unwrap by good-band assembly (quality + seam + lone-outlier gates)
   with median-based jump re-resolution (_assemble_profile);
4. a decision-directed absolute NCC pass against the fragment's own decoded
   content (_dd_refine, dd_decode idiom) that tightens the profiles to
   ~0.02 dots RMS on the geometry=False footing.
Phasor (complex) averaging before taking angles is essential: arithmetic means
of wrapped phases are biased and noisy; the phasor sum measures -0.98/-1.03 px
against a -1.0 px truth on the geometry=False sim (unbiased, no calibration
constant needed).

Known limitation of Stage 0 (page-edge regime): a real warp excursion faster
than half a cell pitch per band (measured on sim seed 314: ~+9 px over 2
bands at the page bottom — fast wander + a step cluster) aliases for ANY
local phase method, and the decision-directed pass is self-consistent with
the resulting one-cell slip; such a region decodes at ~50% while the interior
stays clean (~1.5%). This mirrors dd_warp's measured page-edge failure
(004.0a). REPAIRED at Stage A (Wave 2, this module): once the pilot address
is accepted, _pilot_slip_profiles votes every visible pilot site's expected
bit under +-1-cell shifts and folds the integer slip-step profile into the
grid (measured: sim seed 7 blind payload BER 20.96% -> 4.34%, seed 314
12.65% -> 3.75%). Template-NCC anchors CANNOT do this repair: in a full-cell
slip the detected halo cells are confidently wrong and drag the correlation
peak to zero (see measure_pilot_anchors); anchors remain the sub-cell stage.

Cell-center convention (derived empirically on the frozen simulator, see
tests/test_acquire_grid.py::test_center_convention_geometry_false): at
oversample 2 and cell_dots=3 with geometry=False, cell k's center sits at px
6*k + 2 (dot d maps to px 2*d; the 3-dot cell's central dot is 3k+1), i.e. the
edge phase is -1 px. lock_grid measures that phase blindly — nothing here
hard-codes the -1.

Pilot anchors: known-content template NCC (strip_tracker architecture — known
content gives processing gain and NO integer-cell ambiguity), separable
quality-weighted (dy(y), dx(x)) aggregation; dx is NEVER self-clocked (x-bow
measured catastrophic, 006/between_strip).

Provenance of lifted code (experiment modules are sys.path-wired, not a
package — M1 ports lift, they do not import across experiments/):
- _fit_gmm_z / _llr_field lifted from
  experiments/001-engine-characterization/scanlab.py (fit_gmm_z, llr_field;
  run 001.4 — mixture weights PINNED 0.5/0.5, freeing pi drifts).
- _xcorr_offset_ncc lifted from experiments/006-loop-pages/strip_tracker.py
  (xcorr_offset: sliding normalized cross-correlation + parabolic subpixel).
- cell_bits_blind quantile z-normalization follows
  experiments/006-loop-pages/analyze_e006bw.py blind_ctx_llr.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np
from scipy import ndimage, stats
from scipy.special import logsumexp

from paperholo import bch, compose
from paperholo.dust import dust_positions_tile, dust_states_tile
from paperholo.pilots import (
    PilotLayout,
    code_for_layout,
    decode_word,
    expected_word_bits,
    site_positions_tile,
    t_acq_for_layout,
    value_keystream_tile,
)
from paperholo.sync import estimate_lattice

WIN_PX_DEFAULT = 96
STEP_PX_DEFAULT = 48
WORD_BITS = 100                  # pilot word length (BCH(100,*) both layouts)
CELL_DOTS = 3                    # DEFAULT cell size (kcell-c3). Every geometry
#   helper below takes cell_dots with this default, so all historical callers
#   are bit-identical; acquire_and_decode threads spec.cell_dots (kcell-c2
#   admitted 2026-07-09, the acquire-v2 generalization). The RECTIFIED frame
#   stays 2 px/dot for every cell size (cell_px = 2*cell_dots), which is the
#   scan-native density after scannorm's canonical rescale.
RECT_PX_PER_DOT = 2              # rectified-frame density (px per printer dot)
ANCHOR_MIN_Q = 0.10              # NCC lock gate, strip_tracker convention
ANCHOR_MAX_SHIFT_PX = 5          # +-2.5 dots residual search after grid lock
#   (validated at c3 = 6 px/cell; other cell sizes scale it by cell_px/6 —
#   see acquire_and_decode's anchor loop)
ANCHOR_BIN_CELLS = 24            # 4 pilot block rows (p60b6: 6-cell blocks)
DD_BAND_CELLS = 8                # decision-directed NCC band height (cells)
DD_SEARCH_MAIN_PX = 8            # HISTORICAL (c3): superseded by cell_px+2 in
#   _dd_refine/the anchor loop; kept for reference only
DD_SEARCH_CROSS_PX = 2
DD_MIN_Q = 0.10

# ---- color receiver constants (layout_version 4 / cmy8, IMPL-3) ----------
# plane -> RGB channel (measured convention, scannorm._PLANE_CHANNEL twin:
# C reads best in R, M in G, Y in B — 002.2/007.6 A3 per-channel scoring)
COLOR_PLANE_CHANNEL: dict[str, int] = {"C": 0, "M": 1, "Y": 2}
COLOR_ANCHOR_MIN = 8         # pure-plane anchors needed for a global (dy,dx)
COLOR_SLOPE_MIN = 16         # anchors needed to also fit the linear-in-y term
COLOR_SLOPE_MIN_SPAN = 0.15  # ... and min anchor y-span (fraction of page)
COLOR_ANCHOR_INLIER_DOTS = 0.5   # residual gate around the Theil-Sen line
COLOR_CAL_MIN_LABELS = 300   # per-level PAVA bar (the K-path 300-label bar)
MIN_CAL_LABELS = 60          # K-path PAVA floor (018.4: was 300, and BELOW
#                              the bar raw GMM scores leaked out unbounded —
#                              sigma-floor scores ~5e5 vs calibrated <=6.8.
#                              PAVA's 1/(n+2) clamp makes small-label maps
#                              self-limiting: 60 labels -> |LLR| <= ln 61)
UNCAL_LLR_CAP = 6.0          # no-label windows: rescaled into the
#                              calibrated regime's range, never raw
COLOR_LLR_FLOOR = 2.0        # |LLR| clip on degenerate/collapsed QDA levels
QDA_RIDGE = 1e-6             # x trace(S_pool)/d on every class covariance
QDA_COLLAPSE_DIST = 0.5      # pooled-whitened mean distance = collapsed pair
SITE_FIT_MIN_CELLS = 30      # word-site cells needed before the P1 site fit
#   replaces the whole-window fit (matches Stage B's min_sites bar; below it
#   a pinned 2-GMM has no stable population to fit and the whole-window fit
#   is the only estimator available)


def _normalize_refl(img: np.ndarray) -> np.ndarray:
    """Float64 ink-dark reflectance in [0,1] from sim output or 0-255 grey."""
    arr = np.ascontiguousarray(img, np.float64)
    if arr.size and float(arr.max()) > 1.5:
        arr = arr / 255.0
    return arr


def _wrap(v: np.ndarray | float, period: float) -> np.ndarray | float:
    return (v + period / 2.0) % period - period / 2.0


def _grad_mag(arr: np.ndarray) -> np.ndarray:
    """Mean-removed gradient magnitude — the lattice-line regenerator
    (paperholo.sync: NRZ cells have a spectral NULL at the symbol rate;
    edge detection is the 2-D squaring timing-recovery nonlinearity)."""
    gy, gx = np.gradient(arr)
    g = np.hypot(gy, gx)
    return g - g.mean()


def _zoom_axis_pitch(g: np.ndarray, angle: float, pitch_nominal: float,
                     main_axis: int, *, span_frac: float = 0.04,
                     n_grid: int = 161) -> float:
    """Pass-0 per-axis pitch: fine-grid zoom DFT of the ANGLE-PINNED coherent
    cross-projection of the gradient map.

    Replaces the original global-2-D-FFT peak search (Wave-2 fix of a
    measured Stage-0 failure): that search admitted a |cross| <= 0.25*f0
    noise wedge, and on a 720-px composed fragment the x lattice line
    (F=13.8) lost to in-band noise peaks (~30) — pass-0 landed +4.4% off,
    outside the band-slope capture range (~1.5% at 96-px x bands), and the
    lock never recovered (pitch_u 6.265 vs 6.0 true). Pinning the cross
    frequency to the measured lattice angle (one coherent projection at the
    nominal cross frequency — the pitch-induced cross error over the +-4%
    scan is O(0.04*sin(angle)*W/p), negligible after the pi/4 fold) removes
    that wedge; the fine grid (0.05% step over +-4%) needs no whole-spectrum
    FFT and lands within the slope-pass capture on every measured fragment
    (720-px composed x worst margin peak/median 1.5, argmax exact).
    Scanner/printer scale truth is <1% (001/002.0b); +-4% also covers a
    pass-0 miss of the old kind if content ever carries a near-lattice line.
    """
    h_px, w_px = g.shape
    c_t, s_t = np.cos(angle), np.sin(angle)
    xs = np.arange(w_px, dtype=np.float64)
    ys = np.arange(h_px, dtype=np.float64)
    if main_axis == 0:
        q = g @ np.exp(-2j * np.pi * (-s_t * xs) / pitch_nominal)
        coord = c_t * ys
    else:
        q = np.exp(-2j * np.pi * (s_t * ys) / pitch_nominal) @ g
        coord = c_t * xs
    q = q * np.hanning(q.size)
    pitches = pitch_nominal * (1.0 + np.linspace(-span_frac, span_frac,
                                                 n_grid))
    amp = np.abs(np.exp(-2j * np.pi * np.outer(1.0 / pitches, coord)) @ q)
    if not np.isfinite(amp).all() or float(amp.max()) <= 0.0:
        raise ValueError("no lattice line in the pitch search band")
    return float(pitches[int(np.argmax(amp))])


def _window_phasors(g: np.ndarray, angle: float, pitch_v: float,
                    pitch_u: float, win_px: int, step_px: int
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-window lattice-DFT phasors of the gradient-magnitude map at the
    cell frequency (dd_warp convention), both lattice axes.

    Separable complex-exponential factorization over ABSOLUTE image
    coordinates (exp(-2pi i u/p) = EuX[x]*EuY[y]) so phasors from different
    windows share one phase reference and can be summed coherently.
    Returns (Fu, Fv, quality), each (ny, nx).
    """
    h_px, w_px = g.shape
    c_t, s_t = np.cos(angle), np.sin(angle)
    xs = np.arange(w_px, dtype=np.float64)
    ys = np.arange(h_px, dtype=np.float64)
    eux = np.exp(-2j * np.pi * (c_t * xs) / pitch_u)
    euy = np.exp(-2j * np.pi * (s_t * ys) / pitch_u)
    evx = np.exp(-2j * np.pi * (-s_t * xs) / pitch_v)
    evy = np.exp(-2j * np.pi * (c_t * ys) / pitch_v)
    ny = max(1, (h_px - win_px) // step_px + 1)
    nx = max(1, (w_px - win_px) // step_px + 1)
    hann = np.hanning(win_px)
    w2d = hann[:, None] * hann[None, :]
    Fu = np.zeros((ny, nx), np.complex128)
    Fv = np.zeros((ny, nx), np.complex128)
    qual = np.zeros((ny, nx))
    for iy in range(ny):
        y0 = iy * step_px
        for ix in range(nx):
            x0 = ix * step_px
            wnd = g[y0:y0 + win_px, x0:x0 + win_px]
            wz = (wnd - wnd.mean()) * w2d
            Fu[iy, ix] = euy[y0:y0 + win_px] @ (wz @ eux[x0:x0 + win_px])
            Fv[iy, ix] = evy[y0:y0 + win_px] @ (wz @ evx[x0:x0 + win_px])
            qual[iy, ix] = (min(abs(Fu[iy, ix]), abs(Fv[iy, ix]))
                            / max(np.abs(wz).sum(), 1e-9))
    return Fu, Fv, qual


def _strip_phasors(g: np.ndarray, angle: float, pitch_v: float,
                   pitch_u: float, band_px_v: int, band_px_u: int
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Lattice-DFT phasors on NON-OVERLAPPING band_px strips, coherently
    integrated over the full cross axis (flat weight — the phase is constant
    along it on the measured channel: steps/wander/scale are y(y), the CCD
    comb is x(x)); Hann along the band axis. Non-overlapping bands localize a
    real step or comb seam to exactly ONE band, whose phase (a mix of two
    sub-populations) is then rejectable as a lone outlier — overlapping
    96-px windows smeared the seam into confident garbage across two bands
    (measured on the frozen sim: one antipodal seam phase slipped the
    unwrap by a full cell and killed half the fragment's columns).

    Returns (Fv_bands, Fu_bands, v_centers_px, u_centers_px).
    """
    h_px, w_px = g.shape
    c_t, s_t = np.cos(angle), np.sin(angle)
    xs = np.arange(w_px, dtype=np.float64)
    ys = np.arange(h_px, dtype=np.float64)
    eux = np.exp(-2j * np.pi * (c_t * xs) / pitch_u)
    euy = np.exp(-2j * np.pi * (s_t * ys) / pitch_u)
    evx = np.exp(-2j * np.pi * (-s_t * xs) / pitch_v)
    evy = np.exp(-2j * np.pi * (c_t * ys) / pitch_v)
    hann_v = np.hanning(band_px_v)
    hann_u = np.hanning(band_px_u)
    n_v = h_px // band_px_v
    n_u = w_px // band_px_u
    Fv = np.zeros(n_v, np.complex128)
    Fu = np.zeros(n_u, np.complex128)
    for iy in range(n_v):
        y0 = iy * band_px_v
        strip = g[y0:y0 + band_px_v, :]
        strip = strip - strip.mean()
        Fv[iy] = (hann_v * evy[y0:y0 + band_px_v]) @ (strip @ evx)
    for ix in range(n_u):
        x0 = ix * band_px_u
        strip = g[:, x0:x0 + band_px_u]
        strip = strip - strip.mean()
        Fu[ix] = euy @ (strip @ (hann_u * eux[x0:x0 + band_px_u]))
    row_y = np.arange(n_v) * band_px_v + band_px_v / 2.0
    col_x = np.arange(n_u) * band_px_u + band_px_u / 2.0
    v_centers = c_t * row_y - s_t * float(xs.mean())
    u_centers = c_t * col_x + s_t * float(ys.mean())
    return Fv, Fu, v_centers, u_centers


def _lone_outliers(phi_wrapped: np.ndarray, period: float, *,
                   agree_px: float = 0.6, differ_px: float = 0.9
                   ) -> np.ndarray:
    """Flag bands whose neighbors agree with each other (circular) while the
    band disagrees with both — the signature of a seam/step band whose
    phasor is a two-population mix with arbitrary phase. A REAL step is NOT
    flagged: there the neighbors disagree with each other."""
    n = phi_wrapped.size
    flag = np.zeros(n, bool)
    for i in range(1, n - 1):
        nb = abs(float(_wrap(phi_wrapped[i + 1] - phi_wrapped[i - 1], period)))
        d0 = abs(float(_wrap(phi_wrapped[i] - phi_wrapped[i - 1], period)))
        d1 = abs(float(_wrap(phi_wrapped[i + 1] - phi_wrapped[i], period)))
        flag[i] = nb < agree_px and min(d0, d1) > differ_px
    return flag


def _assemble_profile(phi_wrapped: np.ndarray, quality: np.ndarray,
                      period: float, seam: np.ndarray, *,
                      weak_frac: float = 0.35, jump_px: float = 2.0,
                      ctx_bands: int = 6) -> np.ndarray:
    """Unwrapped phase profile from the GOOD bands only, with jump-branch
    re-resolution; weak bands are bridged by interpolation.

    Design history (all measured on the frozen sim): greedy nearest-branch
    (the contract's design note) slips at seam bands — a band straddling a
    real step is a phasor mix of two far-apart populations whose phase can
    land antipodal with full amplitude, turning the pairwise branch decision
    into a coin flip (a 1.5-dot scanner step > c3 half-pitch tied it within
    0.02 px and slipped the whole fragment tail by one cell). A dd_warp-style
    quality-weighted DP fails the same way when the garbage band offers a
    cheap staircase to the wrong branch, and post-hoc jump fixing fails
    because weak-band interpolation smears the wrong jump below any trigger.
    Assembling from gated good bands and re-deciding every remaining
    >=jump_px jump against nearby-section MEDIANS decides with measured
    margins of 0.8-2.4 px where the pairwise decisions tied.
    """
    phi = np.asarray(phi_wrapped, np.float64)
    q = np.asarray(quality, np.float64)
    n = phi.size
    if n == 0:
        return phi.copy()
    good = ((q >= weak_frac * float(np.median(q)))
            & ~np.asarray(seam, bool) & ~_lone_outliers(phi, period))
    if good.sum() < 3:
        good = np.ones(n, bool)
    idx = np.where(good)[0]
    vals = phi[idx].copy()
    for j in range(1, vals.size):
        vals[j] += period * np.round((vals[j - 1] - vals[j]) / period)
    # robust within-section slope (px per band index): residual pitch error
    # + wander; section medians sit ~3 bands from a jump, so an uncorrected
    # slope biases the branch metric by ~6*slope px — measured enough to
    # flip a near-half-period decision (rot90 comb seam)
    # NO slope extrapolation in the branch metric: the per-band phase noise
    # (sigma ~0.3 px) makes any locally-estimated slope noise-dominated, and
    # extrapolating it over the median windows measurably FLIPPED a correct
    # decision (rot90 comb seam) while plain position-limited medians decide
    # all measured seam/step cases with 0.8-2.4 px margins.
    ks = np.array([-1.0, 0.0, 1.0])
    pos = idx.astype(np.float64)
    for j in range(1, vals.size):
        if abs(vals[j] - vals[j - 1]) < jump_px:
            continue
        mid = (pos[j - 1] + pos[j]) / 2.0
        # section medians from NEARBY good bands only (position <= 10 bands
        # from the jump) so wander/pitch-residual drift stays sub-margin
        near_pre = np.where((pos < mid) & (pos >= mid - 10.0))[0][-ctx_bands:]
        near_post = np.where((pos > mid) & (pos <= mid + 10.0))[0][:ctx_bands]
        if near_pre.size < 2 or near_post.size < 2:
            continue
        m_pre = float(np.median(vals[near_pre]))
        m_post = float(np.median(vals[near_post]))
        k = float(ks[int(np.argmin(np.abs(m_post + ks * period - m_pre)))])
        if k != 0.0:
            vals[j:] += k * period
    return np.interp(np.arange(n, dtype=np.float64),
                     idx.astype(np.float64), vals)


def _diff_coherence(F_bands: np.ndarray, period: float) -> float:
    """Adjacent-band phase-diff coherence |mean(exp(2pi*i*d/period))| — the
    trackability metric for one axis at one band width. Real profiles have
    small band-to-band diffs (high coherence, 0.62-0.99 measured); an axis
    whose per-band lattice line is below the noise gives uniform phases
    (0.07-0.34 measured) and must not steer the slope/unwrap. Band AMPLITUDE
    cannot discriminate here: a 48-96 px band cannot resolve a 2% pitch
    error, so on/off-lattice band amplitudes are equal (measured ratio ~1.0
    on both trackable and untrackable axes)."""
    phi = _wrap((-np.angle(F_bands) / (2 * np.pi)) * period, period)
    d = np.asarray(_wrap(np.diff(phi), period), np.float64)
    if d.size < 3:
        return 0.0
    return float(np.abs(np.mean(np.exp(2j * np.pi * d / period))))


def _seam_flags(F_half: np.ndarray, period: float, n_bands: int,
                thresh_px: float = 1.0) -> np.ndarray:
    """Flag bands with STRUCTURE INSIDE the band: the circular phase
    difference of the band's two halves exceeds thresh_px (~2 sigma of the
    half-band phase noise). A band straddling a comb seam (~1.8 px) or a
    large scanner step is a phasor mix of two far-apart populations whose
    summed phase is arbitrary — it must not steer the branch unwrap.
    Small steps (median 0.52 dots ~ 1 px) stay below the threshold, which is
    fine: near populations mix to a well-behaved intermediate phase."""
    phi_h = _wrap((-np.angle(F_half) / (2 * np.pi)) * period, period)
    flags = np.zeros(n_bands, bool)
    for i in range(n_bands):
        if 2 * i + 1 < phi_h.size:
            d = abs(float(_wrap(phi_h[2 * i + 1] - phi_h[2 * i], period)))
            flags[i] = d > thresh_px
    return flags


@dataclass
class GridModel:
    """Local cell-lattice lock over a scan window/fragment.

    Maps fragment-local CELL coords (arbitrary origin: the seed band's wrapped
    phase) -> scan px, as a rotated per-axis affine (pitch_v/u, angle) plus
    unwrapped separable phase profiles phi_v(v)/phi_u(u) in scan px,
    linearly interpolated between band centers.
    """
    shape_cells: tuple[int, int]
    pitch_px: float                 # mean of the two axis pitches
    angle_rad: float                # lattice rotation, folded to (-pi/4, pi/4]
    quality: np.ndarray             # (ny, nx) per-window lock quality
    pitch_v_px: float               # cell pitch along scan-y-like lattice axis
    pitch_u_px: float               # cell pitch along scan-x-like lattice axis
    phi_v_px: np.ndarray            # (ny,) unwrapped v-phase profile
    v_centers_px: np.ndarray        # (ny,) band-center v coordinates
    phi_u_px: np.ndarray            # (nx,) unwrapped u-phase profile
    u_centers_px: np.ndarray        # (nx,) band-center u coordinates

    def _centers_uv(self, y_cells: np.ndarray, x_cells: np.ndarray
                    ) -> tuple[np.ndarray, np.ndarray]:
        """Cell centers in lattice (v, u) px coordinates; broadcasts inputs."""
        y = np.asarray(y_cells, np.float64)
        x = np.asarray(x_cells, np.float64)
        v0 = (y + 0.5) * self.pitch_v_px
        u0 = (x + 0.5) * self.pitch_u_px
        # one fixed-point pass: evaluate the phase at the phase-corrected
        # position (the profile drifts ~17 px over a page at +0.6% y-scale;
        # evaluating at the nominal coord alone leaves an O(scale*phi) error).
        # GUARDED against folded one-cell slip steps (finding [0], wave-3):
        # the re-evaluated position of a boundary cell adjacent to a
        # negative-going step crosses to the pre-step side of the per-cell
        # node profile and reads the wrong branch, undoing the fold for that
        # whole row/column (measured: +6.0 px sampling error at exactly the
        # boundary cell; sim seeds 7/314 slip rows at 26-53% BER). Keep the
        # first-pass phase wherever the re-evaluation moves >= half a cell —
        # the smooth-drift correction this pass exists for stays intact
        # (0.0002 px residual vs 0.026 px naive at +0.6% y-scale, measured).
        phv = np.interp(v0.ravel(), self.v_centers_px, self.phi_v_px)
        phv2 = np.interp(v0.ravel() + phv, self.v_centers_px, self.phi_v_px)
        phv = np.where(np.abs(phv2 - phv) < self.pitch_v_px / 2.0, phv2, phv)
        phu = np.interp(u0.ravel(), self.u_centers_px, self.phi_u_px)
        phu2 = np.interp(u0.ravel() + phu, self.u_centers_px, self.phi_u_px)
        phu = np.where(np.abs(phu2 - phu) < self.pitch_u_px / 2.0, phu2, phu)
        return v0 + phv.reshape(v0.shape), u0 + phu.reshape(u0.shape)

    def _uv_to_px(self, v: np.ndarray, u: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray]:
        c, s = np.cos(self.angle_rad), np.sin(self.angle_rad)
        return s * u + c * v, c * u - s * v      # (y_px, x_px)

    def cell_centers_px(self, y_cells: np.ndarray, x_cells: np.ndarray
                        ) -> tuple[np.ndarray, np.ndarray]:
        """(y_px, x_px) scan coordinates of cell centers; elementwise with
        numpy broadcasting between y_cells and x_cells."""
        v, u = self._centers_uv(y_cells, x_cells)
        v, u = np.broadcast_arrays(v, u)
        return self._uv_to_px(v, u)


def lock_grid(img: np.ndarray, *, cell_px_nominal: float = 6.0,
              win_px: int = WIN_PX_DEFAULT,
              step_px: int = STEP_PX_DEFAULT,
              cell_dots: int = CELL_DOTS) -> GridModel:
    """Stage 0: blind lattice lock on a scan fragment.

    Tiled gradient-magnitude lattice DFT per window (dd_warp convention),
    phasor-aggregated into separable unwrapped phase profiles. Fragment cell
    origin is arbitrary (seed band's wrapped phase); absolute addressing is
    Stage A's job (pilot word phase search). cell_px_nominal is the expected
    cell pitch in scan px (2*cell_dots at the canonical 2 px/dot); cell_dots
    sizes the decision-directed pass's rectified frame and slip search.
    """
    arr = _normalize_refl(img)
    if min(arr.shape) < win_px:
        raise ValueError(f"fragment smaller than one {win_px}px window")
    est = estimate_lattice(arr, pitch_px_nominal=cell_px_nominal)
    angle = float(est["angle_rad"])
    if angle > np.pi / 4:
        angle -= np.pi / 2                      # fold to (-pi/4, pi/4]

    g = _grad_mag(arr)
    h_px, w_px = g.shape
    # pass-0 per-axis pitch (zoom DFT, angle-pinned — see _zoom_axis_pitch
    # for why the original global-FFT peak search was replaced). Under full
    # geometry the coherent lattice line is SMEARED by the warp and the peak
    # location is ~0.3-0.9% off — it is only the initializer here; the
    # band-to-band phase slope below measures the true pitch robustly.
    pitch_v = _zoom_axis_pitch(g, angle, cell_px_nominal, main_axis=0)
    pitch_u = _zoom_axis_pitch(g, angle, cell_px_nominal, main_axis=1)

    # band widths per axis, chosen by MEASURED adjacent-band phase-diff
    # coherence (Wave-2 fix of a Stage-0 failure): the fixed y=48/x=96
    # assignment assumed canonical orientation, but on a rotated fragment
    # the weak content axis (printed x: deeper edge-gain amplitude null) can
    # land on the 48-px axis, where band phases are noise (coherence
    # 0.12-0.34 measured on 720-px rot90 composed fragments vs 0.62-0.99 on
    # trackable axes) and the median-slope pass random-walks the pitch out
    # of capture (+1.9% measured => unrecoverable). Each axis takes the more
    # coherent of {48, 96} px; if BOTH are incoherent (< 0.5) the axis is
    # phase-untrackable at any band width — its profile falls back to the
    # FLAT full-fragment coherent phase at the pass-0 pitch, and the DD
    # absolute pass carries the residual structure (the weak axis's only
    # real structure is the CCD comb, ~1.8 px steps, inside DD's +-8 px
    # capture; measured: that path locked 720-px fragments whose 96-px band
    # coherence was 0.07).
    cos_a = float(np.cos(angle))
    F48v, F48u, _, _ = _strip_phasors(g, angle, pitch_v, pitch_u,
                                      step_px, step_px)
    F96v, F96u, _, _ = _strip_phasors(g, angle, pitch_v, pitch_u,
                                      2 * step_px, 2 * step_px)
    c_v48, c_v96 = (_diff_coherence(F48v, pitch_v),
                    _diff_coherence(F96v, pitch_v))
    c_u48, c_u96 = (_diff_coherence(F48u, pitch_u),
                    _diff_coherence(F96u, pitch_u))
    band_px_v = step_px if c_v48 >= c_v96 else 2 * step_px
    band_px_u = step_px if c_u48 >= c_u96 else 2 * step_px
    track_v = max(c_v48, c_v96) >= 0.5
    track_u = max(c_u48, c_u96) >= 0.5
    def _slope_px_per_band(phi_wr: np.ndarray, period: float) -> float:
        # pitch correction from the median circular band-to-band phase
        # difference: d(phi)/d(coord) = p_true/p - 1. Diffs > 1.5 px are
        # real steps (comb ~1.8 px, y-steps <=1.95 dots) or seam-band
        # garbage, not pitch — excluding them matters: on the rot90 sim
        # fragment the raw median landed the pitch 0.35% low and forced
        # spurious wrap crossings across the whole profile.
        d = _wrap(np.diff(phi_wr), period)
        keep = np.abs(d) < 1.5
        if keep.sum() < 4:
            return 0.0
        return float(np.median(d[keep]))

    phi_v_wr = phi_u_wr = None
    Fv_b = Fu_b = v_centers = u_centers = None
    for _pass in range(3):
        Fv_b, Fu_b, v_centers, u_centers = _strip_phasors(
            g, angle, pitch_v, pitch_u, band_px_v, band_px_u)
        phi_v_wr = _wrap((-np.angle(Fv_b) / (2 * np.pi)) * pitch_v, pitch_v)
        phi_u_wr = _wrap((-np.angle(Fu_b) / (2 * np.pi)) * pitch_u, pitch_u)
        if _pass < 2:
            if track_v:
                pitch_v *= 1.0 + (_slope_px_per_band(phi_v_wr, pitch_v)
                                  / (band_px_v * cos_a))
            if track_u:
                pitch_u *= 1.0 + (_slope_px_per_band(phi_u_wr, pitch_u)
                                  / (band_px_u * cos_a))

    # seam detection by half-band phase split, then DP branch unwrap at the
    # corrected pitch (profiles are now nearly drift-free: noise sigma
    # ~0.25 px per band << period/2; only real steps and their seam bands
    # remain — seam bands are bent cheaply and re-interpolated). Untracked
    # axes take the flat full-fragment coherent phase instead (strip phasors
    # share one absolute phase reference, so their sum integrates the whole
    # fragment — the per-band phases are noise but the sum is not).
    Fv_h, Fu_h, _, _ = _strip_phasors(g, angle, pitch_v, pitch_u,
                                      band_px_v // 2, band_px_u // 2)
    if track_v:
        seam_v = _seam_flags(Fv_h, pitch_v, phi_v_wr.size)
        phi_v = _assemble_profile(phi_v_wr, np.abs(Fv_b), pitch_v, seam_v)
    else:
        phi_v = np.full(phi_v_wr.size, float(
            _wrap((-np.angle(Fv_b.sum()) / (2 * np.pi)) * pitch_v, pitch_v)))
    if track_u:
        seam_u = _seam_flags(Fu_h, pitch_u, phi_u_wr.size)
        phi_u = _assemble_profile(phi_u_wr, np.abs(Fu_b), pitch_u, seam_u)
    else:
        phi_u = np.full(phi_u_wr.size, float(
            _wrap((-np.angle(Fu_b.sum()) / (2 * np.pi)) * pitch_u, pitch_u)))

    # per-window quality field at the final pitch (diagnostic + Stage-A gate)
    _, _, qual = _window_phasors(g, angle, pitch_v, pitch_u, win_px, step_px)

    shape_cells = (int(h_px / pitch_v), int(w_px / pitch_u))
    grid = GridModel(shape_cells=shape_cells,
                     pitch_px=float((pitch_v + pitch_u) / 2.0),
                     angle_rad=angle, quality=qual,
                     pitch_v_px=float(pitch_v), pitch_u_px=float(pitch_u),
                     phi_v_px=phi_v, v_centers_px=v_centers,
                     phi_u_px=phi_u, u_centers_px=u_centers)
    # decision-directed absolute pass: repairs any residual branch slips
    # (self-clock is provably ambiguous at steps > pitch/2) and tightens
    # the phase profiles against the fragment's own content fingerprint
    return _dd_refine(arr, grid, cell_dots=cell_dots)


def _rectify(arr: np.ndarray, grid: GridModel,
             cell_dots: int = CELL_DOTS) -> np.ndarray:
    """Resample the fragment onto the locked lattice at 2 px/dot
    (cell_px = 2*cell_dots; 6 px/cell at c3): rectified pixel a along an axis
    samples lattice coordinate
    (a + 0.5)*pitch/cell_px + phi — PIXEL-CENTER convention, so a kron-rendered
    template block (pixels 6i..6i+5 at c3, centroid 6i+2.5) aligns bias-free
    with content cell i (centroid (i+0.5)*pitch + phi -> rectified 6i+2.5).
    An index-as-position convention here costs a measured +0.5 px NCC bias."""
    h_cells, w_cells = grid.shape_cells
    cell_px = RECT_PX_PER_DOT * cell_dots
    ya = (np.arange(h_cells * cell_px, dtype=np.float64) + 0.5) / cell_px - 0.5
    xa = (np.arange(w_cells * cell_px, dtype=np.float64) + 0.5) / cell_px - 0.5
    v, u = grid._centers_uv(ya[:, None], xa[None, :])
    v, u = np.broadcast_arrays(v, u)
    y_px, x_px = grid._uv_to_px(np.array(v), np.array(u))
    return ndimage.map_coordinates(arr, [y_px, x_px], order=1, mode="nearest")


def _band_ncc_offsets(rect: np.ndarray, tmpl: np.ndarray, band_px: int,
                      main_axis: int, search_main: int, search_cross: int
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Per-band NCC displacement of rect vs a known/decision template along
    main_axis (full cross-axis integration per band). Positive offset =
    content displaced + along main_axis relative to the model. Returns
    (offsets_px with NaN below DD_MIN_Q, quality)."""
    R = rect if main_axis == 0 else rect.T
    T = tmpl if main_axis == 0 else tmpl.T
    n_b = T.shape[0] // band_px
    hb = n_b * band_px
    w = T.shape[1]
    T = T[:hb] - T.mean()
    Rp = np.pad(R - R.mean(),
                ((search_main, search_main), (search_cross, search_cross)),
                mode="edge")
    tt = (T * T).reshape(n_b, band_px, w).sum(axis=(1, 2))
    n_m = 2 * search_main + 1
    n_c = 2 * search_cross + 1
    corr = np.zeros((n_b, n_m, n_c))
    for im in range(n_m):
        for ic in range(n_c):
            win = Rp[im:im + hb, ic:ic + w]
            prod = (win * T).reshape(n_b, band_px, w).sum(axis=(1, 2))
            ww = (win * win).reshape(n_b, band_px, w).sum(axis=(1, 2))
            corr[:, im, ic] = prod / np.sqrt(ww * tt + 1e-9)
    off = np.full(n_b, np.nan)
    qual = np.zeros(n_b)
    for b in range(n_b):
        im, ic = np.unravel_index(int(np.argmax(corr[b])), (n_m, n_c))
        q = float(corr[b, im, ic])
        qual[b] = q
        if q < DD_MIN_Q:
            continue
        prof = corr[b, :, ic]
        sub = 0.0
        if 0 < im < n_m - 1:
            a, c0, c1 = prof[im - 1], prof[im], prof[im + 1]
            den = a - 2 * c0 + c1
            if abs(den) > 1e-12:
                sub = float(np.clip((a - c1) / (2 * den), -0.5, 0.5))
        off[b] = im + sub - search_main
    return off, qual


def _dd_refine(arr: np.ndarray, grid: GridModel,
               cell_dots: int = CELL_DOTS) -> GridModel:
    """Decision-directed absolute registration pass (dd_warp.dd_decode
    idiom, 004.0a — legal, GT-free): decode once on the phase-locked grid,
    render the OWN-DECISION bitmap as a template, and measure per-band
    absolute (dy, dx) by NCC. The content fingerprint has NO period
    ambiguity, so this repairs what cell-frequency self-clock provably
    cannot: branch choices at scanner steps > pitch/2 (measured y-steps
    reach 1.95 dots > 1.5 dots = c3 half-cell; one such step slipped a
    whole fragment tail by one cell on the frozen sim). An ~80%-correct
    decision template still correlates decisively (NCC ~ 1 - 2*BER)."""
    cell_px = RECT_PX_PER_DOT * cell_dots
    hard, _ = cell_bits_blind(_cell_means(arr, grid, None,
                                          cell_dots=cell_dots))
    rect = _rectify(arr, grid, cell_dots=cell_dots)
    tmpl = np.kron(1.0 - hard.astype(np.float64),
                   np.ones((cell_px, cell_px)))
    band_px = DD_BAND_CELLS * cell_px
    # search must cover a one-cell branch slip: cell_px + 2 (== the frozen
    # DD_SEARCH_MAIN_PX = 8 at c3)
    search_main = cell_px + 2
    dy_rect, _ = _band_ncc_offsets(rect, tmpl, band_px, 0,
                                   search_main, DD_SEARCH_CROSS_PX)
    dx_rect, _ = _band_ncc_offsets(rect, tmpl, band_px, 1,
                                   search_main, DD_SEARCH_CROSS_PX)

    def _profile(off_rect: np.ndarray, pitch: float, phi_old: np.ndarray,
                 centers_old: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        nodes = (np.arange(off_rect.size) + 0.5) * band_px * pitch / cell_px
        base = np.interp(nodes, centers_old, phi_old)
        vals = base + off_rect * (pitch / cell_px)
        good = np.isfinite(vals)
        if not good.any():
            return phi_old, centers_old
        idx = np.arange(vals.size, dtype=np.float64)
        vals[~good] = np.interp(idx[~good], idx[good], vals[good])
        return vals, nodes

    phi_v, v_centers = _profile(dy_rect, grid.pitch_v_px,
                                grid.phi_v_px, grid.v_centers_px)
    phi_u, u_centers = _profile(dx_rect, grid.pitch_u_px,
                                grid.phi_u_px, grid.u_centers_px)
    return GridModel(shape_cells=grid.shape_cells, pitch_px=grid.pitch_px,
                     angle_rad=grid.angle_rad, quality=grid.quality,
                     pitch_v_px=grid.pitch_v_px, pitch_u_px=grid.pitch_u_px,
                     phi_v_px=phi_v, v_centers_px=v_centers,
                     phi_u_px=phi_u, u_centers_px=u_centers)


def _cell_means(arr: np.ndarray, grid: GridModel,
                warp_field: Callable[[np.ndarray, np.ndarray],
                                     tuple[np.ndarray, np.ndarray]] | None,
                cell_dots: int = CELL_DOTS) -> np.ndarray:
    """4-point cell-mean sampler at center +-0.25*cell each axis (house
    convention: strip_tracker/dd_warp/scanlab all sample the same 4 points),
    bilinear map_coordinates, optional (dy, dx) dot-offset field (cell_dots
    converts the field's DOT units to lattice px)."""
    h_cells, w_cells = grid.shape_cells
    ii = np.arange(h_cells, dtype=np.float64)[:, None]
    jj = np.arange(w_cells, dtype=np.float64)[None, :]
    v, u = grid._centers_uv(ii, jj)
    v, u = np.broadcast_arrays(v, u)
    v = np.array(v)
    u = np.array(u)
    if warp_field is not None:
        iim, jjm = np.broadcast_arrays(ii, jj)
        dy_dots, dx_dots = warp_field(iim, jjm)
        # dots -> lattice px via the per-axis pitch (cell = cell_dots dots)
        v = v + np.asarray(dy_dots) * grid.pitch_v_px / cell_dots
        u = u + np.asarray(dx_dots) * grid.pitch_u_px / cell_dots
    acc = np.zeros(v.shape, np.float64)
    for oy in (-0.25, 0.25):
        for ox in (-0.25, 0.25):
            y_px, x_px = grid._uv_to_px(v + oy * grid.pitch_v_px,
                                        u + ox * grid.pitch_u_px)
            acc += ndimage.map_coordinates(arr, [y_px, x_px], order=1,
                                           mode="nearest")
    return acc / 4.0


def sample_cell_means(img: np.ndarray, grid: GridModel,
                      cell_dots: int = CELL_DOTS) -> np.ndarray:
    """(H_cells, W_cells) float reflectance means on the locked grid."""
    return _cell_means(_normalize_refl(img), grid, None, cell_dots=cell_dots)


def resample_cell_means(img: np.ndarray, grid: GridModel,
                        warp_field: Callable[[np.ndarray, np.ndarray],
                                             tuple[np.ndarray, np.ndarray]],
                        cell_dots: int = CELL_DOTS) -> np.ndarray:
    """Cell means with the anchor-derived (dy, dx) dot-offset field applied."""
    return _cell_means(_normalize_refl(img), grid, warp_field,
                       cell_dots=cell_dots)


# ---------------------------------------------------------------------------
# blind bit detection — lifted from experiments/001-engine-characterization/
# scanlab.py (fit_gmm_z, llr_field; measured 001.4) per the M1 porting rule:
# experiment modules are not a package, code is lifted with provenance.
# ---------------------------------------------------------------------------

def _fit_gmm_z(z: np.ndarray, mu_init: tuple[float, float] = (0.1, 0.9),
               max_iters: int = 40, tol: float = 1e-4) -> dict:
    """2-component 1-D Gaussian EM on normalized levels z (0=white, 1=ink).

    Mixture weights are PINNED at 0.5/0.5: the scrambler fixes ink density at
    50% by construction, and freeing pi lets the wide white component swallow
    the c2 gain-bridge mass (EM drifts without settling, measured 001.4).
    Lifted verbatim from scanlab.fit_gmm_z.
    """
    zf = z.ravel().astype(np.float64)
    mu = np.array(mu_init, float)
    sig = np.array([0.15, 0.15])
    dmu = np.inf
    for _ in range(max_iters):
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
    if mu[0] > mu[1]:                     # defensive: component 0 = white
        mu, sig = mu[::-1], sig[::-1]
    return {"pi": [0.5, 0.5], "mu": mu.tolist(), "sigma": sig.tolist()}


def _llr_field(z: np.ndarray, gmm: dict) -> np.ndarray:
    """Per-cell LLR log p(z|ink) - log p(z|white); flat prior (scrambled
    source is 50/50 by construction). Positive = ink. Lifted from
    scanlab.llr_field."""
    (mu0, mu1), (s0, s1) = gmm["mu"], gmm["sigma"]
    return ((-0.5 * ((z - mu1) / s1) ** 2 - np.log(s1))
            - (-0.5 * ((z - mu0) / s0) ** 2 - np.log(s0)))


def _z_normalize(means: np.ndarray) -> np.ndarray:
    """Robust 2%/98% quantile z-normalization of cell means (~0 white,
    ~1 ink) — the shared front half of cell_bits_blind/cell_bits_ctx."""
    m = np.asarray(means, np.float64)
    lo, hi = np.quantile(m, (0.02, 0.98))
    return (hi - m) / max(hi - lo, 1e-6)


def cell_bits_blind(means: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Blind (hard_bits, llr) from sampled cell means: robust 2%/98% quantile
    z-normalization (~0 white, ~1 ink), pinned 2-GMM, LLR sign — the
    analyze_e006bw.blind_ctx_llr chain without the 16-context stage (context
    gains are field/engine-dependent, 007.2/007.6: not budgeted at Stage 0)."""
    z = _z_normalize(means)
    gmm = _fit_gmm_z(z)
    llr = _llr_field(z, gmm)
    return (llr > 0).astype(np.uint8), np.asarray(llr, np.float64)


def _fit_gmm_z_rows(z: np.ndarray, mu_init: tuple[float, float] = (0.1, 0.9),
                    max_iters: int = 40, tol: float = 1e-4
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Row-vectorized twin of _fit_gmm_z: one pinned-0.5/0.5 2-component EM
    per ROW of z (n_rows, n_cells) — the per-hypothesis engine of the P1
    Stage-A site fit (Stage A visits up to 3600 phase hypotheses per window;
    a Python-loop fit per hypothesis is unaffordable, the vectorized EM on
    (3600, ~100) is one pass of elementwise array ops per iteration).
    Same init/iteration/tol contract as _fit_gmm_z with the convergence test
    taken over ALL rows. Returns (mu (n,2), sigma (n,2)) with component 0 =
    white per row. Degenerate rows (a component starved of responsibility on
    a near-constant population) keep finite parameters via the nk floor —
    their bits are arbitrary-but-finite and the BCH word gate rejects them."""
    zf = np.asarray(z, np.float64)
    n = zf.shape[0]
    mu = np.tile(np.asarray(mu_init, np.float64), (n, 1))
    sig = np.full((n, 2), 0.15)
    for _ in range(max_iters):
        logp = (-0.5 * ((zf[:, :, None] - mu[:, None, :])
                        / sig[:, None, :]) ** 2 - np.log(sig[:, None, :]))
        logp -= logp.max(axis=2, keepdims=True)
        r = np.exp(logp)
        r /= r.sum(axis=2, keepdims=True)
        nk = np.maximum(r.sum(axis=1), 1e-12)
        mu_new = (r * zf[:, :, None]).sum(axis=1) / nk
        sig = np.sqrt((r * (zf[:, :, None] - mu_new[:, None, :]) ** 2
                       ).sum(axis=1) / nk)
        sig = np.maximum(sig, 1e-3)
        dmu = float(np.abs(mu_new - mu).max())
        mu = mu_new
        if dmu < tol:
            break
    swap = mu[:, 0] > mu[:, 1]                # defensive: component 0 = white
    mu[swap] = mu[swap][:, ::-1]
    sig[swap] = sig[swap][:, ::-1]
    return mu, sig


def _site_fit_words(z_words: np.ndarray) -> np.ndarray:
    """Hard word bits from per-hypothesis site z-populations (n_rows, sites):
    the P1 Stage-A rule (COLOR-DESIGN D3 / PILOTS-DESIGN §16.4) — each row's
    pinned 2-GMM is fit on THAT hypothesis's gathered word-site cells (50/50
    white/CM by keystream construction under the true phase; ~uniform page
    cells under a wrong one, whose near-coin-flip bits the BCH gate rejects).
    The whole-window fit on a mostly-ink 8-state page mis-thresholds W-vs-CM
    (P1 measured up to 2x word BER)."""
    mu, sig = _fit_gmm_z_rows(z_words)
    m0, m1 = mu[:, 0:1], mu[:, 1:2]
    s0, s1 = sig[:, 0:1], sig[:, 1:2]
    llr = ((-0.5 * ((z_words - m1) / s1) ** 2 - np.log(s1))
           - (-0.5 * ((z_words - m0) / s0) ** 2 - np.log(s0)))
    return (llr > 0).astype(np.uint8)


def _site_fit_cell_bits(means: np.ndarray, sites_yx: np.ndarray
                        ) -> tuple[np.ndarray, np.ndarray]:
    """cell_bits_blind with the pinned 2-GMM fit on the WORD-SITE population
    only (P1 rule, post-acceptance form: the accepted address makes the true
    site cells known, so ONE fit serves every downstream word-bit consumer —
    slip votes, anchor templates, the post-fold word certification). The LLR
    field is evaluated over the whole grid: the site-population W/CM
    threshold is the correct word-channel discriminator wherever a pilot bit
    is read; payload cells never consume these bits on color pages (QDA
    detection owns the payload, _color_payload_stage)."""
    z = _z_normalize(means)
    gmm = _fit_gmm_z(z[sites_yx[:, 0], sites_yx[:, 1]])
    llr = _llr_field(z, gmm)
    return (llr > 0).astype(np.uint8), np.asarray(llr, np.float64)


def context_llr_field(z: np.ndarray, llr_global: np.ndarray,
                      gmm_global: dict, *, conf_llr: float = 2.0,
                      min_cells: int = 200, iters: int = 2) -> np.ndarray:
    """Decision-directed 16-context detector (ICM): per-4-neighbour-pattern
    class statistics re-estimated from cells whose neighbours are all
    confident. Lifted verbatim from experiments/001-*/scanlab.context_detect
    per the M1 porting rule (provenance: measured 001.4; c2 11.2->5.0%
    day-1 M281; 007.6 measured ~no gain on AltaLink at 2 px/dot — run 014.2
    OVERTURNED that at 16 px/cell: 7.9->2.6% on the AltaLink-printed e014,
    i.e. ctx gains are SAMPLING-dependent, not engine-dependent).

    Blind: contexts come from the detector's own decisions, never GT.
    Attacks the measured development nonlinearities — white cells in inky
    contexts close partially (shifted dark), lone ink cells in white
    contexts under-develop (shifted bright) — that a single global mixture
    cannot model. Contexts with <min_cells usable cells or unseparated
    classes fall back to the global LLR."""
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
            g = _fit_gmm_z(z[sel], mu_init=tuple(gmm_global["mu"]))
            (mu0, mu1), (s0, s1) = g["mu"], g["sigma"]
            if mu1 - mu0 < (s0 + s1) / 2:  # classes not separated: fall back
                continue
            csel = ctx == c
            llr_new[csel] = _llr_field(z[csel], g)
        llr = llr_new
    return llr


def cell_bits_ctx(means: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """cell_bits_blind + the 16-context ICM stage (detector="ctx" path)."""
    z = _z_normalize(means)
    gmm = _fit_gmm_z(z)
    llr = context_llr_field(z, _llr_field(z, gmm), gmm)
    return (llr > 0).astype(np.uint8), np.asarray(llr, np.float64)


def pava_calibrate(scores: np.ndarray, labels: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Isotonic (PAVA) calibration map from detector scores to empirical
    P(bit=1): returns (score_nodes, p_nodes) for np.interp. The F1+PAVA
    design (LAYERS.md LLRs contract: "PAVA-calibrated"): monotonicity is
    the only assumption — no Gaussian confidence is trusted. Labels are
    the KNOWN pilot bits (the on-page labeled set; blind-legal since the
    receiver decoded them). Probabilities are clamped to
    [1/(n+2), 1-1/(n+2)] so calibrated |LLR| stays finite."""
    s = np.asarray(scores, np.float64).ravel()
    y = np.asarray(labels, np.float64).ravel()
    order = np.argsort(s, kind="stable")
    s, y = s[order], y[order]
    # classic stack PAVA (weighted block means, monotone non-decreasing)
    vals: list[float] = []
    wts: list[float] = []
    for v in y:
        vals.append(float(v))
        wts.append(1.0)
        while len(vals) > 1 and vals[-2] >= vals[-1]:
            w = wts[-1] + wts[-2]
            vals[-2] = (vals[-1] * wts[-1] + vals[-2] * wts[-2]) / w
            wts[-2] = w
            vals.pop()
            wts.pop()
    # expand blocks to node arrays (block score = weighted center)
    nodes_s = np.empty(len(vals))
    nodes_p = np.empty(len(vals))
    i0 = 0
    pmin = 1.0 / (s.size + 2.0)
    for k, (v, w) in enumerate(zip(vals, wts)):
        i1 = i0 + int(round(w))
        nodes_s[k] = s[i0:min(i1, s.size)].mean()
        nodes_p[k] = min(max(v, pmin), 1.0 - pmin)
        i0 = i1
    return nodes_s, nodes_p


def apply_calibration(llr: np.ndarray, nodes_s: np.ndarray,
                      nodes_p: np.ndarray) -> np.ndarray:
    """Detector scores -> calibrated LLRs via the PAVA map (house sign)."""
    p = np.interp(np.asarray(llr, np.float64), nodes_s, nodes_p)
    return np.log(p / (1.0 - p))


# ---------------------------------------------------------------------------
# pilot anchors — known-content template NCC (strip_tracker architecture)
# ---------------------------------------------------------------------------

def _xcorr_offset_ncc(win: np.ndarray, tpl: np.ndarray, max_shift: int,
                      weight: np.ndarray | None = None
                      ) -> tuple[float, float, float]:
    """Sliding normalized cross-correlation peak with parabolic sub-pixel
    refinement. Returns (dy_px, dx_px, quality in 0..1). win must exceed tpl
    by 2*max_shift each axis. Lifted from strip_tracker.xcorr_offset (the
    better-conditioned primitive for small known marks: true normalization,
    no circular wrap), extended with an optional per-template-pixel weight
    mask: zero-weight pixels contribute nothing to means, correlation or
    normalization (used to exclude unconfident detected halo cells, which
    are self-consistent with any grid error and drag the peak toward 0)."""
    wgt = np.ones_like(tpl, np.float64) if weight is None \
        else weight.astype(np.float64)
    wsum = float(wgt.sum()) + 1e-9
    t = tpl.astype(np.float64)
    t = t - float((t * wgt).sum()) / wsum
    t_w = t * wgt
    th, tw = t.shape
    w = win.astype(np.float64)
    n_y = w.shape[0] - th + 1
    n_x = w.shape[1] - tw + 1
    corr = np.empty((n_y, n_x))
    tn = np.sqrt((t * t_w).sum()) + 1e-9
    for iy in range(n_y):
        for ix in range(n_x):
            patch = w[iy:iy + th, ix:ix + tw]
            pm = float((patch * wgt).sum()) / wsum
            p = patch - pm
            corr[iy, ix] = (p * t_w).sum() / (
                np.sqrt((p * p * wgt).sum()) * tn + 1e-9)
    iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)
    q = float(corr[iy, ix])

    def parab(c: np.ndarray, i: int, n: int) -> float:
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


def measure_pilot_anchors(img: np.ndarray, grid: GridModel,
                          site_cells_yx: np.ndarray,
                          expected_bits: np.ndarray, *,
                          halo_cells: int = 1,
                          detected_bits: np.ndarray | None = None,
                          detected_llr: np.ndarray | None = None,
                          max_shift_px: int = ANCHOR_MAX_SHIFT_PX,
                          cell_dots: int = CELL_DOTS) -> dict:
    """Per-pilot residual displacement by template NCC against the grid lock.

    Template = the KNOWN pilot cell value plus a +-halo_cells ring of DETECTED
    neighbor cells (known content = processing gain and no integer-cell
    ambiguity, strip_tracker doctrine), rendered at the nominal 2 px/dot and
    matched inside a grid-rectified window around the site. Halo cells with
    |LLR| < 2.0 (the scanlab confidence convention) are DOWN-WEIGHTED to
    0.05 in the NCC (not zero: an all-muted halo leaves a contrast-free
    template): detected bits are self-consistent with whatever error the grid has
    (measured: an injected half-cell offset smears their cell means, and a
    full-weight halo drags the anchor back toward 0 — only the KNOWN center
    cell carries independent registration). Under large grid error one
    measure->warp->resample round only part-corrects; iterate 2-3 rounds
    (see tests/test_acquire_grid.py::test_anchor_warp_recovers_corrupted_grid).

    Sites whose template window leaves the fragment, or whose template is
    featureless, or whose NCC quality < 0.10 get NaN (min_q convention).
    Returns {"site_cells_yx", "dy_dots", "dx_dots", "q"}; offsets are in
    layout dots, positive = content displaced +y/+x relative to the grid.
    detected_bits/detected_llr may be passed to reuse an existing Stage-0
    detection; None recomputes them here. max_shift_px defaults to the
    sub-cell design regime (+-2.5 dots); widen to 8 px when hunting a
    one-cell Stage-0 branch slip (page-edge regime) at the cost of extra
    peak ambiguity.
    """
    arr = _normalize_refl(img)
    sites = np.asarray(site_cells_yx, int)
    exp_bits = np.asarray(expected_bits).astype(np.uint8).ravel()
    if sites.shape[0] != exp_bits.size:
        raise ValueError("site_cells_yx and expected_bits length mismatch")
    if detected_bits is None or detected_llr is None:
        detected_bits, detected_llr = cell_bits_blind(
            sample_cell_means(arr, grid, cell_dots=cell_dots))
    det = np.asarray(detected_bits).astype(np.uint8)
    conf = np.abs(np.asarray(detected_llr, np.float64)) >= 2.0

    cell_px = RECT_PX_PER_DOT * cell_dots      # rectified frame: 2 px/dot
    m_px = int(max_shift_px)
    t_cells = 2 * halo_cells + 1
    t_px = t_cells * cell_px
    w_px = t_px + 2 * m_px
    h_cells, w_cells = grid.shape_cells
    n = sites.shape[0]
    dy_dots = np.full(n, np.nan)
    dx_dots = np.full(n, np.nan)
    qs = np.zeros(n)

    # rectified window sample coordinates, in lattice px, relative to the
    # top-left cell BOUNDARY of the template block (boundary = center - p/2)
    a = np.arange(w_px, dtype=np.float64)
    for i in range(n):
        sy, sx = int(sites[i, 0]), int(sites[i, 1])
        if not (halo_cells <= sy < h_cells - halo_cells
                and halo_cells <= sx < w_cells - halo_cells):
            continue
        bits = det[sy - halo_cells:sy + halo_cells + 1,
                   sx - halo_cells:sx + halo_cells + 1].copy()
        # unconfident halo cells keep a small weight (not zero: an all-muted
        # halo leaves a uniform one-cell template with no edge contrast,
        # which is NCC-degenerate under mean removal)
        w_cell = np.where(conf[sy - halo_cells:sy + halo_cells + 1,
                               sx - halo_cells:sx + halo_cells + 1],
                          1.0, 0.05)
        bits[halo_cells, halo_cells] = exp_bits[i]
        w_cell[halo_cells, halo_cells] = 1.0    # known center always counts
        if bits.min() == bits.max():
            continue                            # featureless template
        v_c, u_c = grid._centers_uv(np.float64(sy - halo_cells),
                                    np.float64(sx - halo_cells))
        v0 = float(v_c) - grid.pitch_v_px / 2.0
        u0 = float(u_c) - grid.pitch_u_px / 2.0
        # pixel-center sampling (+0.5): kron template block centroids align
        # bias-free with content cell centroids (see _rectify)
        vq = v0 + (a[:, None] - m_px + 0.5) * (grid.pitch_v_px / cell_px)
        uq = u0 + (a[None, :] - m_px + 0.5) * (grid.pitch_u_px / cell_px)
        vq, uq = np.broadcast_arrays(vq, uq)
        y_px, x_px = grid._uv_to_px(vq, uq)
        win = ndimage.map_coordinates(arr, [y_px, x_px], order=1,
                                      mode="nearest")
        tpl = np.kron(1.0 - bits.astype(np.float64),
                      np.ones((cell_px, cell_px)))
        w_px_mask = np.kron(w_cell, np.ones((cell_px, cell_px)))
        dy_px, dx_px, q = _xcorr_offset_ncc(win, tpl, m_px, weight=w_px_mask)
        qs[i] = q
        if q >= ANCHOR_MIN_Q:
            dy_dots[i] = dy_px / RECT_PX_PER_DOT   # rectified px -> dots
            dx_dots[i] = dx_px / RECT_PX_PER_DOT
    return {"site_cells_yx": sites, "dy_dots": dy_dots,
            "dx_dots": dx_dots, "q": qs}


def _binned_profile(coord_cells: np.ndarray, val_dots: np.ndarray,
                    weight: np.ndarray, n_cells: int,
                    bin_cells: int) -> tuple[np.ndarray, np.ndarray]:
    """Quality-weighted per-bin means of scattered anchor values along one
    axis; returns (node_coords_cells, node_values_dots) for np.interp."""
    ok = np.isfinite(val_dots) & (weight > 0)
    if not ok.any():
        return np.array([0.0, float(n_cells)]), np.zeros(2)
    coord = coord_cells[ok].astype(np.float64)
    val = val_dots[ok]
    wgt = weight[ok]
    nodes_c, nodes_v = [], []
    for b0 in range(0, n_cells, bin_cells):
        sel = (coord >= b0) & (coord < b0 + bin_cells)
        if not sel.any():
            continue
        wsum = wgt[sel].sum()
        nodes_c.append(float((coord[sel] * wgt[sel]).sum() / wsum))
        nodes_v.append(float((val[sel] * wgt[sel]).sum() / wsum))
    if not nodes_c:
        return np.array([0.0, float(n_cells)]), np.zeros(2)
    return np.asarray(nodes_c), np.asarray(nodes_v)


def anchor_warp_field(anchors: dict, shape_cells: tuple[int, int]
                      ) -> Callable[[np.ndarray, np.ndarray],
                                    tuple[np.ndarray, np.ndarray]]:
    """Scattered pilot anchors -> smooth separable (dy, dx) dot-offset field.

    Quality-weighted SEPARABLE aggregation — dy(y) from anchors binned over
    ~4 pilot block rows (ANCHOR_BIN_CELLS), dx(x) from anchors binned over
    columns — is the measured-physics convention (scanner steps/wander/scale
    are y(y), CCD comb is x(x); dd_warp selfclock_profiles). dx comes from
    anchors ONLY, never self-clocked (x-bow measured catastrophic,
    between_strip 006). Linear interpolation between bin nodes, constant
    extrapolation at the ends (np.interp semantics).
    """
    sites = np.asarray(anchors["site_cells_yx"], np.float64)
    q = np.asarray(anchors["q"], np.float64)
    h_cells, w_cells = shape_cells
    ny_c, ny_v = _binned_profile(sites[:, 0], np.asarray(anchors["dy_dots"]),
                                 q, h_cells, ANCHOR_BIN_CELLS)
    nx_c, nx_v = _binned_profile(sites[:, 1], np.asarray(anchors["dx_dots"]),
                                 q, w_cells, ANCHOR_BIN_CELLS)

    def warp_field(y_cells: np.ndarray, x_cells: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray]:
        y = np.asarray(y_cells, np.float64)
        x = np.asarray(x_cells, np.float64)
        dy = np.interp(y.ravel(), ny_c, ny_v).reshape(y.shape)
        dx = np.interp(x.ravel(), nx_c, nx_v).reshape(x.shape)
        return dy, dx

    return warp_field


# ---------------------------------------------------------------------------
# Stage A/B — blind pilot-word acquisition + full fragment decode (Wave 2).
#
# Phase convention: for an oriented hard-bit grid, the pilot tile grid sits at
# some offset (ry, rx) in fragment-local cell coords, ry/rx in [0, period):
# fragment cell f belongs to tile-local coordinate (f - r) mod period, and the
# tile whose top-left is fragment cell (ry + period*my, rx + period*mx) carries
# the codeword of absolute tile (ptile_y, ptile_x) with
#   cell_origin_abs = ptile * period - (r + period*m)
# (absolute page cell of fragment-local (0,0)). The 3600-hypothesis search IS
# the sweep of (ry, rx); a tile window straddling tile boundaries would mix up
# to 4 distinct codewords (adjacent addresses differ in ~half the parity), so
# Stage A only ever gathers FULL tiles — the searched offsets are exactly the
# tile-origin candidates inside the window.
#
# Under np.rot90 the site pattern does NOT map to itself (in-block offsets are
# seeded per block, word order is raster): a wrongly-oriented grid gathers
# keystream-flavored noise and the BCH gate (false accept ~2.3e-8/hypothesis
# at t_acq=8, measured 0/200k) silently rejects — orientation detection is
# free. All Stage-A/B work happens in the ROTATED bits-grid frame; absolute
# coords only become canonical after the accepting orientation's image is
# physically derotated and re-locked (lock_grid's local origin is arbitrary,
# so the canonical-frame re-lock is followed by a one-orientation re-search:
# clean bookkeeping beats rotation algebra on lock origins).
# ---------------------------------------------------------------------------


@dataclass
class AcquireResult:
    """Blind acquisition outcome. ok=False results keep diagnostics
    ("failed_stage" + timings); fields below diagnostics are then defaults.

    n_tiles_attempted/decoded count the CANONICAL-frame fully-visible tiles
    put through the full-strength word decode (t_full per layout: 10 for
    v2, 13 for v3) after acceptance;
    the Stage-A search-window count lives in diagnostics["n_search_windows"].
    """

    ok: bool
    # canonical frame = np.rot90(scan[:, ::-1] if mirrored else scan,
    # orientation_k): orientation_k is the rot90 count applied AFTER any
    # mirror flip (finding [2], wave-3 — the mirror bit is first-class, not
    # a diagnostics-only flag a consumer can miss).
    orientation_k: int = -1
    mirrored: bool = False
    page: int = -1
    plane: str = ""
    ptile_origin_yx: tuple[int, int] = (-1, -1)  # first fully-visible tile, canonical frame
    cell_origin_abs_yx: tuple[int, int] = (0, 0)  # absolute page cell of fragment-local (0,0)
    n_tiles_attempted: int = 0
    n_tiles_decoded: int = 0
    stage_b_match_rate: float = 0.0
    per_tile_match: dict = field(default_factory=dict)
    n_word_errors_corrected: int = 0
    # POST-fold per-pilot-tile word outcomes on the final grid: absolute
    # (ty, tx) -> corrected errors (-1 = failed). The per-scan quality
    # substrate for PageDecodeState merge weights (acquire-v2); empty on
    # ok=False results.
    tile_words: dict = field(default_factory=dict)
    grid: GridModel | None = None       # canonical-frame lock (anchor-folded)
    anchors: dict | None = None         # last measure_pilot_anchors output
    # K pages: (N,) arrays. COLOR pages (spec.n_levels == 3, IMPL-3):
    # payload_bits/payload_llr are LISTS of 3 per-level (N,) arrays (levels
    # C, M, Y) sharing the ONE payload_cell_index — levels share the index
    # map (compose.payload_index_map is level-independent). EXCEPTION: a
    # color page acquired WITHOUT an rgb window (grey scan) returns EMPTY
    # (0,) ndarrays, not lists — diagnostics["color_payload_pending"] is
    # the discriminator, and the K-shaped empties deliberately trip
    # tilemap's "was the scan RGB?" guard instead of merging silently.
    payload_bits: np.ndarray | list | None = None
    payload_cell_index: np.ndarray | None = None
    # soft payload LLRs aligned with payload_cell_index (house convention:
    # positive = payload bit 1, i.e. payload_bits == (payload_llr > 0) up to
    # exact-0 ties). Detection LLRs sign-flipped by the payload keystream —
    # the Layer-3 (paperholo.ldpc) decoder input.
    payload_llr: np.ndarray | list | None = None
    diagnostics: dict = field(default_factory=dict)


def _word_geo(layout: PilotLayout, page_tiles_yx: tuple[int, int] | None
              ) -> dict:
    """encode_word/decode_word geometry kwargs for a layout: empty for v2;
    v3's flat counter REQUIRES the page tile geometry (tiles_x,
    tiles_per_page) to invert counter -> (page, ptile_y, ptile_x)."""
    if layout.version == 2:
        return {}
    if page_tiles_yx is None:
        raise ValueError(
            "layout version 3 needs page_tiles_yx (the flat counter is "
            "geometry-keyed); pass it from ComposeSpec.page_tiles_yx")
    return {"tiles_x": page_tiles_yx[1],
            "tiles_per_page": page_tiles_yx[0] * page_tiles_yx[1]}


def _tile_windows(shape_cells: tuple[int, int], period_cells: int,
                  max_tiles: int) -> list[tuple[int, int]]:
    """Candidate pilot-tile slot indices (my, mx), most-interior first. Slot m
    hosts a full tile at fragment rows [period*m + ry, +period) for phase
    ry — slot m is usable iff period*(m+1) <= extent (at least phase 0 fits;
    _gather_site_vals masks the phases that do not)."""
    h_cells, w_cells = shape_cells
    p = period_cells
    mys = list(range(max(0, (h_cells - p) // p) + 1)) if h_cells >= p else []
    mxs = list(range(max(0, (w_cells - p) // p) + 1)) if w_cells >= p else []
    wins = [(my, mx) for my in mys for mx in mxs]
    wins.sort(key=lambda m: (abs(p * m[0] + p - h_cells / 2.0)
                             + abs(p * m[1] + p - w_cells / 2.0)))
    return wins[:max_tiles]


def _gather_site_vals(grid: np.ndarray, base_cells_yx: tuple[int, int],
                      pos: np.ndarray, period_cells: int
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Gather the (100,) site values for EVERY tile-origin phase (ry, rx)
    whose full tile fits in the grid, via one broadcast fancy-index. Returns
    (vals (n, sites) of grid dtype, ry (n,), rx (n,)) or None if no phase
    fits."""
    h_cells, w_cells = grid.shape
    by, bx = base_cells_yx
    p = period_cells
    ry_lim = min(p, h_cells - by - p + 1)
    rx_lim = min(p, w_cells - bx - p + 1)
    if ry_lim <= 0 or rx_lim <= 0:
        return None
    ry = np.arange(ry_lim)
    rx = np.arange(rx_lim)
    iy = by + ry[:, None] + pos[None, :, 0]          # (ry_lim, sites)
    ix = bx + rx[:, None] + pos[None, :, 1]          # (rx_lim, sites)
    vals = grid[iy[:, None, :], ix[None, :, :]]      # (ry_lim, rx_lim, sites)
    n = ry_lim * rx_lim
    ry_all = np.repeat(ry, rx_lim)
    rx_all = np.tile(rx, ry_lim)
    return vals.reshape(n, pos.shape[0]), ry_all, rx_all


def _stage_a_window(bits_grid: np.ndarray, window_myx: tuple[int, int],
                    pos: np.ndarray, layout: PilotLayout, seed: bytes,
                    plane: str, max_errors: int, geo: dict,
                    z_grid: np.ndarray | None = None) -> list[dict]:
    """All-phase BCH search of ONE pilot-tile slot; candidates sorted by n_err.
    geo = _word_geo(layout, page_tiles_yx) — v3 counter inversion kwargs.
    z_grid (color pages, P1 rule): normalized cell z-levels on the same grid;
    when given, each phase hypothesis's word bits come from a pinned 2-GMM
    fit on ITS OWN gathered site population (_site_fit_words) instead of the
    whole-window bits_grid thresholds."""
    p = layout.period_cells
    base = (window_myx[0] * p, window_myx[1] * p)
    gathered = _gather_site_vals(
        bits_grid if z_grid is None else z_grid, base, pos, p)
    if gathered is None:
        return []
    vals, ry_all, rx_all = gathered
    words = (vals.astype(np.uint8) if z_grid is None
             else _site_fit_words(vals))
    ksp = value_keystream_tile(layout, seed, plane)
    code = code_for_layout(layout)
    decoded = code.decode_many(np.bitwise_xor(words, ksp), max_errors)
    cands: list[dict] = []
    for i, res in enumerate(decoded):
        if res is None:
            continue
        # revalidate through the single-source message gates (pad bits, and
        # for v2 layout_version/plane_id) — decode_word re-runs one BM on the
        # raw scrambled word, ~0.07 ms, hits only
        info = decode_word(words[i], layout, seed, plane, max_errors, **geo)
        if info is None:
            continue
        cands.append({
            "phase_y": int(ry_all[i]), "phase_x": int(rx_all[i]),
            "tile_window_origin": (base[0] + int(ry_all[i]),
                                   base[1] + int(rx_all[i])),
            "message": info, "n_err": int(info["n_errors"]),
        })
    cands.sort(key=lambda c: c["n_err"])
    return cands


def stage_a(bits_grid: np.ndarray, layout: PilotLayout, seed: bytes,
            plane: str, *, max_errors: int | None = None,
            max_tiles: int = 4,
            page_tiles_yx: tuple[int, int] | None = None,
            z_grid: np.ndarray | None = None) -> list[dict]:
    """Stage A: blind site-phase x address search on an oriented hard-bit
    grid. Up to max_tiles full-tile windows (most-interior first), each swept
    over all fitting tile-origin phases (<= period^2 = 3600) in one
    vectorized gather + BCH decode_many at t_acq=max_errors (default from
    the layout version: 8 for v2, 13 for v3 — single-stage full-strength
    search, k_eff=18 keeps window FA ~5e-5). Returns candidate dicts
    (phase_y/phase_x/tile_window_origin/message/n_err), sorted by n_err
    within each window; acquire_and_decode interleaves this per-window with
    Stage B for early stop. v3 layouts REQUIRE page_tiles_yx (the flat
    counter is geometry-keyed). z_grid (color pages): same-shape normalized
    cell z-levels; switches word-bit extraction to the per-hypothesis P1
    site fit (see _stage_a_window)."""
    if max_errors is None:
        max_errors = t_acq_for_layout(layout)
    geo = _word_geo(layout, page_tiles_yx)
    bits = np.ascontiguousarray(bits_grid).astype(np.uint8)
    z = None
    if z_grid is not None:
        z = np.ascontiguousarray(np.asarray(z_grid, np.float64))
        if z.shape != bits.shape:
            raise ValueError(f"z_grid shape {z.shape} != bits_grid "
                             f"shape {bits.shape}")
    pos = site_positions_tile(layout, seed)
    out: list[dict] = []
    for win in _tile_windows(bits.shape, layout.period_cells, max_tiles):
        out.extend(_stage_a_window(bits, win, pos, layout, seed, plane,
                                   max_errors, geo, z_grid=z))
    return out


def stage_b(candidate: dict, bits_grid: np.ndarray, layout: PilotLayout,
            seed: bytes, plane: str, *, min_sites: int = 30,
            min_match: float = 0.85,
            page_tiles_yx: tuple[int, int] | None = None,
            z_grid: np.ndarray | None = None) -> dict | None:
    """Stage B cross-tile validation: from the candidate address, predict
    expected_word_bits for every tile with sites visible in the fragment
    (partial tiles count — their sites are individually predictable) and
    pool the match rate over all sites OUTSIDE the decoded tile. Tiles with
    match rate < 0.6 are slip diagnostics (a Stage-0 one-cell-slip region
    reads ~50% at every site), recorded, never vetoes — the anchor stage is
    the designed repair. DECLARED DEVIATION from the contract's naive
    all-site pool: the pool keeps only tiles whose OWN rate >= min_match —
    measured on sim seed 7, a slip covering ~30% of one axis puts whole
    tiles at ~0.5 AND cuts through a tile column (0.73-0.76: above any slip
    gate, below min_match), dragging every all-site or slip-gated pool to
    0.83-0.84 and vetoing a correct address the contract says must survive.
    Acceptance = >= min_sites sites in clean tiles (their pool is >=
    min_match by construction; a wrong address has ALL tiles near 0.5 —
    P(a partial tile flukes past 0.85) is percent-level and such tiles are
    small, so min_sites=30 rejects it; the word itself already carries a
    2.3e-8 false-accept gate). v3 layouts REQUIRE page_tiles_yx (the flat
    counter is geometry-keyed; neighbor-tile words follow from the counter
    arithmetic c+1 / c+tiles_x inside encode_word). z_grid (color pages, P1
    rule): the visible site cells are re-thresholded by ONE pinned 2-GMM fit
    on their pooled population under the CANDIDATE address — 50/50 by
    keystream construction if the address is right, ~uniform page cells if
    it is wrong (bits ~coin-flip, per-tile match ~0.5, rejection intact)."""
    geo = _word_geo(layout, page_tiles_yx)
    p = layout.period_cells
    pos = site_positions_tile(layout, seed)
    msg = candidate["message"]
    wy, wx = candidate["tile_window_origin"]
    oy = msg["ptile_y"] * p - wy
    ox = msg["ptile_x"] * p - wx
    h_cells, w_cells = bits_grid.shape
    ty_lo, ty_hi = oy // p, (oy + h_cells - 1) // p
    tx_lo, tx_hi = ox // p, (ox + w_cells - 1) // p
    nt_y, nt_x = page_tiles_yx if page_tiles_yx is not None else (64, 64)
    if z_grid is not None:
        sites_loc, _ = _visible_sites(layout, seed, plane, msg["page"],
                                      (oy, ox), (h_cells, w_cells),
                                      (nt_y, nt_x))
        if sites_loc.shape[0] >= SITE_FIT_MIN_CELLS:
            zs = z_grid[sites_loc[:, 0], sites_loc[:, 1]]
            site_llr = _llr_field(zs, _fit_gmm_z(zs))
            bits_grid = np.array(bits_grid)
            bits_grid[sites_loc[:, 0], sites_loc[:, 1]] = (
                site_llr > 0).astype(np.uint8)
    per_tile: dict = {}
    tile_counts: dict = {}
    for ty in range(max(ty_lo, 0), min(ty_hi, nt_y - 1) + 1):
        for tx in range(max(tx_lo, 0), min(tx_hi, nt_x - 1) + 1):
            ly = ty * p + pos[:, 0] - oy
            lx = tx * p + pos[:, 1] - ox
            vis = (ly >= 0) & (ly < h_cells) & (lx >= 0) & (lx < w_cells)
            if not vis.any():
                continue
            try:
                exp = expected_word_bits(layout, seed, plane, msg["page"],
                                         ty, tx, **geo)
            except ValueError:
                continue  # v3 last-page edge: tile beyond the 2^18 counters
            m = bits_grid[ly[vis], lx[vis]] == exp[vis]
            per_tile[(ty, tx)] = float(m.mean())
            if (ty, tx) == (msg["ptile_y"], msg["ptile_x"]):
                continue
            tile_counts[(ty, tx)] = (int(m.sum()), int(vis.sum()))
    slip_tiles = [t for t, r in per_tile.items() if r < 0.6]
    keep = [t for t in tile_counts if per_tile[t] >= min_match]
    n_match = sum(tile_counts[t][0] for t in keep)
    n_tot = sum(tile_counts[t][1] for t in keep)
    if n_tot < min_sites:
        return None
    pooled = n_match / n_tot
    return {"pooled_match": float(pooled), "n_sites_checked": n_tot,
            "per_tile_match": per_tile, "slip_tiles": slip_tiles,
            "cell_origin_abs_yx": (int(oy), int(ox)), "message": msg}


def _search_oriented_bits(bits_grid: np.ndarray, layout: PilotLayout,
                          seed: bytes, plane: str, max_errors: int,
                          page_tiles_yx: tuple[int, int], max_tiles: int,
                          z_grid: np.ndarray | None = None
                          ) -> tuple[dict | None, dict | None, int, int]:
    """Stage A windows interleaved with Stage B; stop on first acceptance.
    Returns (candidate, acceptance, n_windows_tried, n_candidates).
    z_grid threads the P1 color site fit into both stages."""
    geo = _word_geo(layout, page_tiles_yx)
    pos = site_positions_tile(layout, seed)
    n_win = 0
    n_cand = 0
    for win in _tile_windows(bits_grid.shape, layout.period_cells, max_tiles):
        n_win += 1
        cands = _stage_a_window(bits_grid, win, pos, layout, seed, plane,
                                max_errors, geo, z_grid=z_grid)
        n_cand += len(cands)
        for cand in cands:
            acc = stage_b(cand, bits_grid, layout, seed, plane,
                          page_tiles_yx=page_tiles_yx, z_grid=z_grid)
            if acc is not None:
                return cand, acc, n_win, n_cand
    return None, None, n_win, n_cand


def _visible_sites(layout: PilotLayout, seed: bytes, plane: str, page: int,
                   origin_abs_yx: tuple[int, int],
                   shape_cells: tuple[int, int],
                   page_tiles_yx: tuple[int, int]
                   ) -> tuple[np.ndarray, np.ndarray]:
    """(sites_local (N,2), expected_bits (N,)) for every pilot site visible
    in the fragment, raster-sorted by local coords (subsampling stays
    spatially uniform)."""
    geo = _word_geo(layout, page_tiles_yx)
    p = layout.period_cells
    pos = site_positions_tile(layout, seed)
    oy, ox = origin_abs_yx
    h_cells, w_cells = shape_cells
    sites: list[np.ndarray] = []
    exps: list[np.ndarray] = []
    for ty in range(max(oy // p, 0),
                    min((oy + h_cells - 1) // p, page_tiles_yx[0] - 1) + 1):
        for tx in range(max(ox // p, 0),
                        min((ox + w_cells - 1) // p, page_tiles_yx[1] - 1) + 1):
            ly = ty * p + pos[:, 0] - oy
            lx = tx * p + pos[:, 1] - ox
            vis = (ly >= 0) & (ly < h_cells) & (lx >= 0) & (lx < w_cells)
            if not vis.any():
                continue
            try:
                exp = expected_word_bits(layout, seed, plane, page, ty, tx,
                                         **geo)
            except ValueError:
                continue  # v3 last-page edge: tile beyond the 2^18 counters
            sites.append(np.stack([ly[vis], lx[vis]], axis=1))
            exps.append(exp[vis])
    if not sites:
        return np.zeros((0, 2), np.int64), np.zeros(0, np.uint8)
    s = np.concatenate(sites)
    e = np.concatenate(exps)
    order = np.lexsort((s[:, 1], s[:, 0]))
    return s[order], e[order]


def _fold_warp_into_grid(grid: GridModel, warp_field: Callable,
                         cell_dots: int = CELL_DOTS) -> GridModel:
    """Fold a separable (dy, dx) cell-domain dot-offset field into the grid's
    phase profiles (exact for separable fields; lets the repair loop iterate
    measure -> warp -> re-detect on a corrected grid). Profiles are re-noded
    at per-cell density so SHARP fields (the integer slip-step profiles)
    survive the piecewise-linear representation — folding at the original
    ~8-cell DD nodes would smear a one-cell step over 8 boundary cells."""
    h_cells, w_cells = grid.shape_cells
    y_cells = np.arange(h_cells, dtype=np.float64)
    x_cells = np.arange(w_cells, dtype=np.float64)
    dy_v, _ = warp_field(y_cells, np.zeros_like(y_cells))
    _, dx_u = warp_field(np.zeros_like(x_cells), x_cells)
    v_nodes = (y_cells + 0.5) * grid.pitch_v_px
    u_nodes = (x_cells + 0.5) * grid.pitch_u_px
    phi_v = (np.interp(v_nodes, grid.v_centers_px, grid.phi_v_px)
             + np.asarray(dy_v) * grid.pitch_v_px / cell_dots)
    phi_u = (np.interp(u_nodes, grid.u_centers_px, grid.phi_u_px)
             + np.asarray(dx_u) * grid.pitch_u_px / cell_dots)
    return replace(grid, phi_v_px=phi_v, v_centers_px=v_nodes,
                   phi_u_px=phi_u, u_centers_px=u_nodes)


SLIP_SMOOTH_CELLS = 6                # site-vote window: >= ~2 site columns
SLIP_MIN_VOTES = 8
SLIP_MIN_GAIN = 0.25                 # shifted rate must beat nominal by this
SLIP_MIN_RATE = 0.75                 # and be a real match, not less-bad noise


def _pilot_slip_profiles(bits_grid: np.ndarray, sites_local: np.ndarray,
                         expected_bits: np.ndarray
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Integer-cell slip repair from the pilot WORDS (Wave-2, the designed
    Stage-A repair of the Stage-0 page-edge limitation): a fragment region
    whose Stage-0 lock slipped by one cell reads ~50% at its pilot sites,
    but reads ~clean at the sites SHIFTED by the slip — score every visible
    site's expected bit under axis-aligned +-1-cell shifts and build
    smoothed per-axis integer shift profiles (cells). Pilot values are the
    strongest signal available for this: template-NCC anchors fail in a
    full-cell slip because the detected halo cells are confidently WRONG
    (they cleanly read the neighbor cells) and drag the correlation peak to
    zero — measured: anchors left sim seed 7's slipped band at 50% local
    BER; the word-vote profile repairs it. Measured slips are contiguous
    bands along one axis (scanner transport frame); diagonal slips are out
    of v1 scope. Returns (dy_of_y_cells, dx_of_x_cells) int arrays: sample
    content for cell i at grid cell i + shift(i)."""
    h_cells, w_cells = bits_grid.shape
    exps = np.asarray(expected_bits).astype(np.uint8)

    def _rate_profile(axis: int, shift_cells: int) -> np.ndarray:
        dy = shift_cells if axis == 0 else 0
        dx = shift_cells if axis == 1 else 0
        ly = sites_local[:, 0] + dy
        lx = sites_local[:, 1] + dx
        ok = (ly >= 0) & (ly < h_cells) & (lx >= 0) & (lx < w_cells)
        m = np.zeros(sites_local.shape[0])
        m[ok] = (bits_grid[ly[ok], lx[ok]] == exps[ok]).astype(np.float64)
        n_pos = h_cells if axis == 0 else w_cells
        pos = sites_local[:, axis]
        prof = np.full(n_pos, np.nan)
        for c in range(n_pos):
            sel = ok & (np.abs(pos - c) <= SLIP_SMOOTH_CELLS)
            if int(sel.sum()) >= SLIP_MIN_VOTES:
                prof[c] = float(m[sel].mean())
        return prof

    profiles = []
    for axis in (0, 1):
        n_pos = h_cells if axis == 0 else w_cells
        shift_prof = np.zeros(n_pos, np.int64)
        if sites_local.shape[0]:
            base = _rate_profile(axis, 0)
            base_f = np.where(np.isfinite(base), base, 1.0)
            for s in (-1, 1):
                r = _rate_profile(axis, s)
                better = (np.isfinite(r) & (r > SLIP_MIN_RATE)
                          & (r > base_f + SLIP_MIN_GAIN))
                shift_prof[better] = s
        profiles.append(shift_prof)
    return profiles[0], profiles[1]


def _subsample_sites(sites: np.ndarray, exp: np.ndarray, cap: int
                     ) -> tuple[np.ndarray, np.ndarray]:
    n = sites.shape[0]
    if n <= cap:
        return sites, exp
    keep = np.unique(np.round(np.linspace(0, n - 1, cap)).astype(int))
    return sites[keep], exp[keep]


def _decode_visible_tiles(bits_grid: np.ndarray, layout: PilotLayout,
                          seed: bytes, plane: str, page: int,
                          origin_abs_yx: tuple[int, int],
                          page_tiles_yx: tuple[int, int]
                          ) -> tuple[int, int, int,
                                     dict[tuple[int, int], int]]:
    """Full-strength (t_full: 10 v2 / 13 v3) word decode of every
    fully-visible tile. Returns (n_attempted, n_decoded,
    n_word_errors_corrected, per_tile) where per_tile maps each attempted
    ABSOLUTE pilot-tile (ty, tx) to its corrected-error count (-1 = word
    decode failed or address mismatch) — the per-tile substrate the
    PageDecodeState merge weights consume (acquire-v2). A decoded message
    must match the accepted address grid to count."""
    geo = _word_geo(layout, page_tiles_yx)
    t_full = code_for_layout(layout).t_full
    p = layout.period_cells
    pos = site_positions_tile(layout, seed)
    oy, ox = origin_abs_yx
    h_cells, w_cells = bits_grid.shape
    n_att = n_dec = n_err = 0
    per_tile: dict[tuple[int, int], int] = {}
    for ty in range(max(-(-oy // p), 0),
                    min((oy + h_cells) // p, page_tiles_yx[0])):
        for tx in range(max(-(-ox // p), 0),
                        min((ox + w_cells) // p, page_tiles_yx[1])):
            ly0, lx0 = ty * p - oy, tx * p - ox
            word = bits_grid[ly0 + pos[:, 0], lx0 + pos[:, 1]]
            n_att += 1
            info = decode_word(word, layout, seed, plane, t_full, **geo)
            if (info is not None and info["page"] == page
                    and info["ptile_y"] == ty and info["ptile_x"] == tx):
                n_dec += 1
                n_err += int(info["n_errors"])
                per_tile[(ty, tx)] = int(info["n_errors"])
            else:
                per_tile[(ty, tx)] = -1
    return n_att, n_dec, n_err, per_tile


# ---------------------------------------------------------------------------
# color receiver (layout_version 4 / cmy8, IMPL-3 — COLOR-DESIGN D4/D5).
# Everything here hangs AFTER the hardware-certified luma registration
# (Stage 0/A/B + slip + anchors run code-identical to K pages); the color
# additions consume the FINAL grid + the decoded pilot words and never feed
# back into addressing.
# ---------------------------------------------------------------------------


def fit_qda(features: np.ndarray, labels: np.ndarray, *,
            n_classes: int = 8) -> dict:
    """Full-covariance QDA on labeled feature vectors (D4).

    Shrinkage rule (documented per contract): class k's covariance is
    (1 - a_k) * S_k_ml + a_k * S_pooled with a_k = min(1, (d + 2) / n_k) —
    below ~d+2 samples the ML covariance is singular by construction, so the
    class takes the pooled (within-class) covariance entirely; large classes
    keep their own shape. Every covariance then gets a ridge
    QDA_RIDGE * trace(S_pooled)/d * I (solvability floor).

    Degeneracy guards (contract: a starved plane may collapse two classes —
    never crash, warn + widen instead): a class with ZERO labels takes the
    pooled mean + pooled covariance and flags the model degenerate (all
    levels clipped at COLOR_LLR_FLOOR downstream); class-mean pairs closer
    than QDA_COLLAPSE_DIST + sqrt(d*(1/n_i + 1/n_j)) in pooled-whitened
    distance are collapsed pairs — the levels on which the pair differs are
    clipped, with a warning. The added term is the expected whitened
    distance between the SAMPLE means of truly collapsed classes (noise
    only ever inflates the distance, i.e. a fixed bar errs on the UNclipped
    side; at the ~35-55 labels/class of a page_decode window it misses
    ~12% of true collapses — 2026-07-10 review Monte Carlo).

    Priors at inference are FLAT (payload states are uniform 1/8 by
    keystream construction) regardless of training frequencies (pilot label
    cells only carry the white/RENDER_DARK states and would otherwise skew).

    Returns {"mu" (K,d), "chol" [K lower factors], "logdet" (K,),
    "n_per_class" (K,), "warnings" [str], "clip_levels" set[int],
    "degenerate" bool}.
    """
    x = np.asarray(features, np.float64)
    y = np.asarray(labels, np.int64).ravel()
    if x.ndim != 2 or x.shape[0] != y.size:
        raise ValueError(f"features {x.shape} vs labels {y.shape} mismatch")
    n, d = x.shape
    if n < n_classes:
        raise ValueError(f"{n} labels cannot train {n_classes} classes")
    warnings: list[str] = []
    n_k = np.bincount(y, minlength=n_classes).astype(np.int64)
    mu = np.zeros((n_classes, d))
    mu_pool = x.mean(axis=0)
    for k in range(n_classes):
        sel = y == k
        mu[k] = x[sel].mean(axis=0) if n_k[k] > 0 else mu_pool
    resid = x - mu[y]
    s_pool = (resid.T @ resid) / max(n - n_classes, 1)
    ridge = QDA_RIDGE * max(np.trace(s_pool) / d, 1e-12) * np.eye(d)
    s_pool = s_pool + ridge
    chol: list[np.ndarray] = []
    logdet = np.zeros(n_classes)
    degenerate = False
    for k in range(n_classes):
        if n_k[k] == 0:
            degenerate = True
            warnings.append(f"class {k}: 0 labels — pooled stand-in, "
                            "model degenerate (LLRs clipped)")
            s_k = s_pool
        else:
            if n_k[k] < d + 2:
                warnings.append(f"class {k}: only {int(n_k[k])} labels — "
                                "covariance fully shrunk to pooled")
            r = x[y == k] - mu[k]
            s_ml = (r.T @ r) / n_k[k]
            a = min(1.0, (d + 2) / float(n_k[k]))
            s_k = (1.0 - a) * s_ml + a * s_pool + ridge
        c = np.linalg.cholesky(s_k)
        chol.append(c)
        logdet[k] = 2.0 * float(np.log(np.diag(c)).sum())
    # collapsed-pair scan in pooled-whitened space. QDA_COLLAPSE_DIST is
    # the noise-free floor; the per-pair bar adds the sample-mean noise
    # term (see docstring) so shrinking label counts widen the gate
    # instead of blinding it.
    clip_levels: set[int] = set()
    w = np.linalg.cholesky(s_pool)
    mu_w = np.linalg.solve(w, mu.T).T          # whitened means
    for i in range(n_classes):
        for j in range(i + 1, n_classes):
            if n_k[i] == 0 or n_k[j] == 0:
                continue
            bar = QDA_COLLAPSE_DIST + float(
                np.sqrt(d * (1.0 / n_k[i] + 1.0 / n_k[j])))
            if float(np.linalg.norm(mu_w[i] - mu_w[j])) < bar:
                lv_diff = [lv for lv in range(3) if ((i ^ j) >> lv) & 1]
                clip_levels.update(lv_diff)
                warnings.append(
                    f"classes {i}/{j} collapsed (whitened mean dist < "
                    f"{bar:.2f}) — levels {lv_diff} clipped")
    return {"mu": mu, "chol": chol, "logdet": logdet, "n_per_class": n_k,
            "warnings": warnings, "clip_levels": clip_levels,
            "degenerate": degenerate}


def qda_log_densities(model: dict, features: np.ndarray) -> np.ndarray:
    """(n, K) log N(x; mu_k, S_k) up to the shared -d/2*log(2pi) constant
    (flat prior — it cancels in every level LLR)."""
    x = np.asarray(features, np.float64)
    n_classes = model["mu"].shape[0]
    out = np.empty((x.shape[0], n_classes))
    for k in range(n_classes):
        diff = x - model["mu"][k]
        z = np.linalg.solve(model["chol"][k], diff.T)   # lower-triangular
        out[:, k] = -0.5 * (z * z).sum(axis=0) - 0.5 * model["logdet"][k]
    return out


def qda_level_llrs(model: dict, features: np.ndarray) -> np.ndarray:
    """(3, n) per-level LLRs: log-marginal ratio over the 8 posteriors,
    level l partitioning states by bit l (state = C + 2M + 4Y, D4). House
    sign: positive = level bit 1 (that plane inked). Degenerate models clip
    every level, collapsed pairs clip their differing levels (fit_qda)."""
    logp = qda_log_densities(model, features)
    states = np.arange(model["mu"].shape[0])
    out = np.empty((3, logp.shape[0]))
    for lv in range(3):
        one = (states >> lv) & 1 == 1
        out[lv] = (logsumexp(logp[:, one], axis=1)
                   - logsumexp(logp[:, ~one], axis=1))
        if model["degenerate"] or lv in model["clip_levels"]:
            out[lv] = np.clip(out[lv], -COLOR_LLR_FLOOR, COLOR_LLR_FLOOR)
    return out


def _fit_offset_model(y_frac: np.ndarray, vals: np.ndarray, q: np.ndarray
                      ) -> tuple[float, float, int]:
    """ROBUST fit of one offset component: vals ~ a + b*y_frac (dots;
    y_frac = absolute page y / page height). The D5 v1 model shape (CAL-1
    drift models: a global term + a linear-in-y drift).

    Theil-Sen slope (median of pairwise slopes, deterministic) + median
    intercept, then one plain-LSQ refine on the inliers (|residual| <=
    COLOR_ANCHOR_INLIER_DOTS). Robustness is load-bearing, measured on the
    synthetic e2e build data: a pure-plane anchor whose NCC latches onto a
    NEIGHBOR ink cell reads a clean one-cell outlier, and ~15% such
    outliers tilted a plain weighted LSQ of a constant -0.85-dot offset
    into a fake -0.75 dots/page ramp with a ~0 intercept; medians reject
    them outright. NCC quality q gates validity only (it is near-flat,
    0.90-0.98, on valid anchors — not used as a weight).

    Fallbacks: below COLOR_ANCHOR_MIN valid anchors -> (0, 0, n); below
    COLOR_SLOPE_MIN anchors or COLOR_SLOPE_MIN_SPAN y-span the slope is
    dropped (a small fragment cannot condition it) and the global term is
    the median. Returns (a, b, n_inliers)."""
    ok = np.isfinite(vals) & (q > 0)
    n = int(ok.sum())
    if n < COLOR_ANCHOR_MIN:
        return 0.0, 0.0, n
    yf, v = y_frac[ok], vals[ok]
    if (n < COLOR_SLOPE_MIN
            or float(yf.max() - yf.min()) < COLOR_SLOPE_MIN_SPAN):
        return float(np.median(v)), 0.0, n
    iu, ju = np.triu_indices(n, 1)
    dy = yf[iu] - yf[ju]
    sel = np.abs(dy) > 0.05          # near-equal-y pairs: slope noise only
    if not sel.any():
        return float(np.median(v)), 0.0, n
    b = float(np.median((v[iu][sel] - v[ju][sel]) / dy[sel]))
    a = float(np.median(v - b * yf))
    inl = np.abs(v - (a + b * yf)) <= COLOR_ANCHOR_INLIER_DOTS
    n_in = int(inl.sum())
    if n_in >= COLOR_ANCHOR_MIN:     # efficiency refine at the robust model
        a_mat = np.stack([np.ones(n_in), yf[inl]], axis=1)
        coef, *_ = np.linalg.lstsq(a_mat, v[inl], rcond=None)
        a, b = float(coef[0]), float(coef[1])
        return a, b, n_in
    return a, b, n


def _visible_dust_cells(spec: "compose.ComposeSpec", seed: bytes, page: int,
                        origin_abs_yx: tuple[int, int],
                        shape_cells: tuple[int, int],
                        ok_y: np.ndarray, ok_x: np.ndarray
                        ) -> tuple[np.ndarray, np.ndarray]:
    """(local_yx (N,2) int64, states (N,) uint8) of every dust cell visible
    inside the fragment's coverage masks. Positions are tile-periodic
    (dust_positions_tile), states keyed by (seed, page, absolute tile index)
    — the receiver re-derives the encoder's assignment exactly."""
    assert spec.dust is not None
    p = spec.pilot.period_cells
    tiles_y, tiles_x = spec.page_tiles_yx
    dpos = dust_positions_tile(spec.pilot, spec.dust, seed)
    oy, ox = origin_abs_yx
    h_cells, w_cells = shape_cells
    sites: list[np.ndarray] = []
    states: list[np.ndarray] = []
    for ty in range(max(oy // p, 0),
                    min((oy + h_cells - 1) // p, tiles_y - 1) + 1):
        for tx in range(max(ox // p, 0),
                        min((ox + w_cells - 1) // p, tiles_x - 1) + 1):
            ly = ty * p + dpos[:, 0] - oy
            lx = tx * p + dpos[:, 1] - ox
            vis = (ly >= 0) & (ly < h_cells) & (lx >= 0) & (lx < w_cells)
            if vis.any():
                vis &= ok_y[np.clip(ly, 0, h_cells - 1)] \
                    & ok_x[np.clip(lx, 0, w_cells - 1)]
            if not vis.any():
                continue
            st = dust_states_tile(spec.dust, seed, page, ty * tiles_x + tx)
            sites.append(np.stack([ly[vis], lx[vis]], axis=1))
            states.append(st[vis])
    if not sites:
        return np.zeros((0, 2), np.int64), np.zeros(0, np.uint8)
    return (np.concatenate(sites).astype(np.int64),
            np.concatenate(states).astype(np.uint8))


def _render_dark_state() -> int:
    """The 3-bit state a pilot word bit=1 renders as (compose.RENDER_DARK is
    the format-axis constant; reading it here keeps the receiver correct if
    P1's CM flip lands before the e017 golden freezes)."""
    return sum(1 << lv for lv, pl in enumerate("CMY")
               if pl in compose.RENDER_DARK)


def _color_payload_stage(img_c: np.ndarray, rgb_c: np.ndarray,
                         spec: "compose.ComposeSpec", seed: bytes, page: int,
                         grid: GridModel, origin_abs_yx: tuple[int, int],
                         ok_y: np.ndarray, ok_x: np.ndarray,
                         tile_words: dict, sites_all: np.ndarray,
                         exp_all: np.ndarray, *, calibrate: bool,
                         color_features: str, cell_dots: int, diag: dict
                         ) -> tuple[list, np.ndarray, list]:
    """The cmy8 payload detector (runs on the FINAL luma grid, D4/D5):
    (1) labeled sites = visible dust cells + pilot cells of DECODED words;
    (2) per-plane offset model global(dy,dx) + linear-in-y from pure-plane
        dust anchors measured per RGB channel (measure_pilot_anchors on the
        channel image with that channel's own blind detection as the halo);
    (3) per-cell features = channel cell means at plane-corrected grids
        (+ optional luma feature on the base grid);
    (4) 8-class full-covariance QDA trained on the labeled cells;
    (5) per-level payload LLRs (log-marginal ratios), PAVA-calibrated per
        level on the dust labels when calibrate=True, descrambled with each
        level's plane keystream at absolute coords.
    Returns (payload_bits [3 x (N,)], payload_cell_index (N,), payload_llr
    [3 x (N,)])."""
    cd = cell_dots
    cell_px = RECT_PX_PER_DOT * cd
    oy, ox = origin_abs_yx
    h_cells, w_cells = grid.shape_cells
    page_h = float(spec.page_cells_yx[0])
    cdiag: dict = {"warnings": []}
    diag["color"] = cdiag

    channels = [_normalize_refl(rgb_c[..., COLOR_PLANE_CHANNEL[pl]])
                for pl in "CMY"]

    # (1) labeled sites -----------------------------------------------------
    dust_yx, dust_states = _visible_dust_cells(
        spec, seed, page, (oy, ox), (h_cells, w_cells), ok_y, ok_x)
    sy_l, sx_l = sites_all[:, 0], sites_all[:, 1]
    p_cells = spec.pilot.period_cells
    lab_ok = np.array(
        [tile_words.get((int((oy + sy) // p_cells),
                         int((ox + sx) // p_cells)), -1) >= 0
         for sy, sx in zip(sy_l, sx_l)], bool)
    if lab_ok.any():
        lab_ok &= ok_y[sy_l] & ok_x[sx_l]
    pil_yx = sites_all[lab_ok]
    pil_states = np.where(exp_all[lab_ok] == 1,
                          _render_dark_state(), 0).astype(np.uint8)
    cdiag["n_dust_labels"] = int(dust_yx.shape[0])
    cdiag["n_pilot_labels"] = int(pil_yx.shape[0])

    # (2) per-plane offset models (D5) --------------------------------------
    feats_grids: list[np.ndarray] = []
    offsets: list[dict] = []
    for lv, ch in enumerate(channels):
        means0 = _cell_means(ch, grid, None, cell_dots=cd)
        det_b_l, det_l_l = cell_bits_blind(means0)
        pure = dust_yx[dust_states == (1 << lv)]
        fit = {"dy": (0.0, 0.0), "dx": (0.0, 0.0), "n_anchors": 0}
        if pure.shape[0] >= COLOR_ANCHOR_MIN:
            # SUB-cell search only (scaled ANCHOR_MAX_SHIFT_PX = +-2.5 dots
            # at c3): a +-1-cell search admits the neighbor-cell NCC peak
            # (one cell = 3 dots at c3) and produced measured one-cell
            # outlier anchors on the synthetic build data; P4's plane
            # offsets fit inside the half-cell budget by construction
            anch = measure_pilot_anchors(
                ch, grid, pure, np.ones(pure.shape[0], np.uint8),
                detected_bits=det_b_l, detected_llr=det_l_l,
                max_shift_px=max(2, round(ANCHOR_MAX_SHIFT_PX * cell_px / 6.0)),
                cell_dots=cd)
            y_frac = (pure[:, 0].astype(np.float64) + oy) / page_h
            dy_a, dy_b, n_dy = _fit_offset_model(
                y_frac, np.asarray(anch["dy_dots"]), np.asarray(anch["q"]))
            dx_a, dx_b, n_dx = _fit_offset_model(
                y_frac, np.asarray(anch["dx_dots"]), np.asarray(anch["q"]))
            fit = {"dy": (dy_a, dy_b), "dx": (dx_a, dx_b),
                   "n_anchors": min(n_dy, n_dx)}
        if fit["n_anchors"] < COLOR_ANCHOR_MIN:
            cdiag["warnings"].append(
                f"plane {'CMY'[lv]}: {fit['n_anchors']} valid pure-plane "
                f"anchors < {COLOR_ANCHOR_MIN} — zero offset model")
        offsets.append(fit)
        if fit["dy"] == (0.0, 0.0) and fit["dx"] == (0.0, 0.0):
            feats_grids.append(means0)
            continue

        def _warp(y_cells: np.ndarray, x_cells: np.ndarray, _f: dict = fit
                  ) -> tuple[np.ndarray, np.ndarray]:
            y = np.asarray(y_cells, np.float64)
            yf = (y + oy) / page_h
            dy = _f["dy"][0] + _f["dy"][1] * yf
            dx = _f["dx"][0] + _f["dx"][1] * yf     # dx drifts in y too (D5)
            return dy, np.broadcast_to(dx, np.asarray(x_cells).shape).copy()

        feats_grids.append(_cell_means(ch, grid, _warp, cell_dots=cd))
    cdiag["plane_offsets_dots"] = [
        {"plane": "CMY"[lv], **offsets[lv]} for lv in range(3)]

    # (3) feature stack ------------------------------------------------------
    if color_features not in ("rgb", "rgb+luma"):
        raise ValueError(f"color_features must be 'rgb' or 'rgb+luma', "
                         f"got {color_features!r}")
    if color_features == "rgb+luma":
        feats_grids.append(_cell_means(img_c, grid, None, cell_dots=cd))
    cdiag["features"] = color_features
    feats = np.stack(feats_grids, axis=-1)          # (h, w, d)

    # (4) QDA on the labeled cells -------------------------------------------
    lab_yx = np.concatenate([dust_yx, pil_yx]) if pil_yx.size else dust_yx
    lab_st = np.concatenate([dust_states, pil_states]) if pil_yx.size \
        else dust_states
    if lab_yx.shape[0] < 8 * 3:
        raise ValueError(f"only {lab_yx.shape[0]} labeled color cells "
                         "visible — cannot train the 8-class detector")
    model = fit_qda(feats[lab_yx[:, 0], lab_yx[:, 1]], lab_st)
    cdiag["qda_n_per_class"] = model["n_per_class"].tolist()
    cdiag["warnings"].extend(model["warnings"])
    cdiag["qda_degenerate"] = bool(model["degenerate"])

    # (5) per-level LLR fields + PAVA + descramble ----------------------------
    llr_flat = qda_level_llrs(model, feats.reshape(-1, feats.shape[-1]))
    llr_fields = llr_flat.reshape(3, h_cells, w_cells)

    idx_map = compose.payload_index_map(spec, seed)
    ay = oy + np.arange(h_cells)
    ax = ox + np.arange(w_cells)
    sub_idx = idx_map[np.ix_(ay[ok_y], ax[ok_x])]
    sel = sub_idx >= 0
    payload_cell_index = sub_idx[sel].astype(np.int64)
    ry, rx = np.flatnonzero(ok_y), np.flatnonzero(ok_x)
    payload_bits: list[np.ndarray] = []
    payload_llr: list[np.ndarray] = []
    cdiag["calibrated_levels"] = []
    # PAVA per level on the DUST labels (014.2 pattern; dust spans all 8
    # states ~uniformly, unlike pilot cells' white/dark pair). Scores are
    # the FULL model's own dust-cell LLRs — IN-SAMPLE by design (017.5):
    # the map is only meaningful on the score axis it is APPLIED to. The
    # original 2-fold cross-fit (each dust half scored by a QDA trained on
    # the other half) fed pava_calibrate HALF-model scores and then applied
    # the map to FULL-model payload scores; QDA level-LLR scales are
    # covariance-determined and differ arbitrarily between fits (measured
    # 100-1000x on a clean render), so the interpolated p=0.5 crossing
    # landed outside the payload score cloud and whole levels latched to a
    # constant bit (= keystream = exactly 50% BER; the e017 selftest
    # win@(4829,509) M/Y latch, run 017.5; regression:
    # tests/test_e017.py::test_e017_left_edge_window_pava_sign_safe).
    # Cost of in-sample: the payload QDA is TRAINED on these same dust
    # cells, so the map over-states confidence at the LDPC input (the
    # K-path 014.2 setup measured 0.03-0.06 survivorship optimism; bounded
    # by pava_calibrate's 1/(n+2) probability clamp). Recorded in
    # diagnostics so a hardware campaign can attribute it.
    # Zero-anchor (017.5, second defect in the same block): when the dust
    # scores separate perfectly, PAVA degenerates to TWO nodes and
    # apply_calibration's interpolation puts the p=0.5 crossing at the
    # linear midpoint of the two block MEANS. Level LLRs are 8-state
    # log-marginal ratios whose side clusters have systematically different
    # magnitudes, so that midpoint is displaced from the model's own
    # decision boundary (score 0) and payload cells inside the gap get
    # sign-flipped on a PERFECT channel (measured 12.6% M on the clean
    # left-edge window after the scale fix alone). Insert a (0, 0.5) node
    # when score 0 falls in a node gap and the insertion is monotone —
    # the model-informed boundary; where the empirical map already has
    # resolution around 0 the rule is a no-op and the data speaks.
    def _anchor_zero(nodes_s: np.ndarray, nodes_p: np.ndarray
                     ) -> tuple[np.ndarray, np.ndarray]:
        i = int(np.searchsorted(nodes_s, 0.0))
        if (0 < i < nodes_s.size and nodes_s[i - 1] < 0.0 < nodes_s[i]
                and nodes_p[i - 1] <= 0.5 <= nodes_p[i]):
            return (np.insert(nodes_s, i, 0.0), np.insert(nodes_p, i, 0.5))
        return nodes_s, nodes_p

    do_cal = calibrate and dust_yx.shape[0] >= COLOR_CAL_MIN_LABELS
    if do_cal:
        cdiag["pava_in_sample"] = True   # known direction: over-confident
    for lv in range(3):
        raw = llr_fields[lv][np.ix_(ry, rx)][sel].astype(np.float64)
        if do_cal:
            scores = llr_fields[lv][dust_yx[:, 0], dust_yx[:, 1]]
            lab = ((dust_states >> lv) & 1).astype(np.float64)
            nodes_s, nodes_p = _anchor_zero(*pava_calibrate(scores, lab))
            raw = apply_calibration(raw, nodes_s, nodes_p)
            cdiag["calibrated_levels"].append(lv)
        ks = compose.payload_keystream(spec, seed, page, level=lv)
        sub_ks = ks[np.ix_(ay[ok_y], ax[ok_x])][sel]
        # keystream XOR in LLR domain = sign flip where ks == 1 (house sign)
        llr_lv = np.where(sub_ks == 1, -raw, raw)
        payload_llr.append(llr_lv)
        payload_bits.append((llr_lv > 0).astype(np.uint8))
    return payload_bits, payload_cell_index, payload_llr


def acquire_and_decode(img: np.ndarray, spec: "compose.ComposeSpec",
                       seed: bytes, *, include_mirror: bool = False,
                       max_errors_acq: int | None = None, max_tiles: int = 4,
                       plane_hint: str | None = None,
                       max_anchor_sites: int = 250,
                       anchor_rounds: int = 2,
                       cell_px_nominal: float | None = None,
                       detector: str = "global",
                       calibrate: bool = False,
                       rgb: np.ndarray | None = None,
                       color_features: str = "rgb",
                       cell_mask: np.ndarray | None = None) -> AcquireResult:
    """Full blind pipeline: lock -> detect -> orientation x phase x address
    search (Stage A) -> cross-tile validation (Stage B) -> canonical re-lock
    -> pilot-anchored warp repair -> resample -> payload extraction at
    absolute coords.

    plane_hint overrides spec.plane for the decode hypothesis (negative-
    control hook: a wrong hint changes ks_P and trips the plane_id word gate,
    so acquisition fails cleanly). Anchor loop: round index 0 always hunts
    one-cell Stage-0 branch slips at max_shift_px=8 (the measured page-edge
    failure mode, sim seed 314), later rounds refine at the sub-cell
    default; each round folds the separable warp into the grid and
    re-detects. anchor_rounds=0 SKIPS the anchor stage entirely (diagnostic/
    negative-control hook; the pilot-word integer-slip fold still runs) —
    res.anchors stays None and diagnostics carry no "anchor_lock_rate".
    max_errors_acq defaults from the layout version (8 for v2, 13 for v3 —
    single-stage full-strength search). ok=False results carry
    diagnostics["failed_stage"] + timings. After the final fold the visible
    pilot words are re-decoded at full strength as a certification gate: if
    fewer than half decode (2*n_dec < n_att), the folds broke addressing and
    the result is ok=False with failed_stage="post_fold_words" instead of
    silently returning mis-sampled payload (2026-07-09 forensics hardening;
    a global one-cell mis-fold reads ~50% payload BER while pilots pre-fold
    looked perfect).

    COLOR (spec.n_levels == 3, IMPL-3): pass rgb = the (H, W, 3) channel
    image on the SAME pixel frame as img (scannorm.normalize_to_canonical_rgb
    produces it). Registration/addressing stay luma, with the P1 word-bit
    rule wired (COLOR-DESIGN D3 / PILOTS-DESIGN §16.4): every pilot-word bit
    read — Stage A per phase hypothesis, Stage B validation, slip votes,
    anchors, post-fold certification — comes from a pinned 2-GMM fit on the
    gathered WORD-SITE population (50/50 W/CM by construction), never the
    whole-window fit (measured up to 2x word BER on mostly-ink pages;
    diagnostics["word_detector"]="site_fit" records it, and detector="ctx"
    stays K-only for the same reason). After the post-fold
    gate the payload is detected per level by the dust-trained QDA
    (_color_payload_stage): payload_bits/payload_llr become LISTS of 3
    per-level arrays sharing one payload_cell_index (levels share the index
    map). color_features picks the QDA feature set ("rgb" default,
    "rgb+luma" — the engine-dependent 4th feature, COLOR-DESIGN D4).
    calibrate=True runs PAVA per level on the dust labels. Without rgb a
    color page still acquires (addressing certified on luma) but returns
    empty payload with diagnostics["color_payload_pending"]."""
    t0 = time.perf_counter()
    if color_features not in ("rgb", "rgb+luma"):
        raise ValueError(f"color_features must be 'rgb' or 'rgb+luma', "
                         f"got {color_features!r}")
    if rgb is not None and spec.n_levels != 3:
        raise ValueError("rgb is a color-page (n_levels == 3) input; "
                         f"this spec is {spec.encoding_id!r}")
    if rgb is not None and (rgb.ndim != 3 or rgb.shape[:2] != img.shape[:2]
                            or rgb.shape[2] < 3):
        raise ValueError(f"rgb shape {rgb.shape} does not match the luma "
                         f"frame {img.shape[:2]} + (3,)")
    # v4 (cmy8) pages: the word channel is LUMA, plane "K" by design (D3 /
    # PILOTS-DESIGN §16.4) — Stage 0/A/B run code-identical to K pages on
    # the luma reduction. spec.plane is "CMY" there and is never a word
    # keystream plane.
    default_plane = "K" if spec.n_levels == 3 else spec.plane
    plane = default_plane if plane_hint is None else plane_hint
    layout = spec.pilot
    if max_errors_acq is None:
        max_errors_acq = t_acq_for_layout(layout)
    p = layout.period_cells
    page_tiles = (spec.page_cells_yx[0] // p, spec.page_cells_yx[1] // p)
    # geometry from the format hypothesis (acquire-v2): cell size in dots,
    # the RECTIFIED frame's cell pitch (always 2 px/dot — synthesized
    # through the grid, scan-footing independent), and the SCAN footing's
    # expected cell pitch (defaults to the rect value = the historical
    # behavior; scannorm normalizes c2 scans to 6 px/cell and passes it
    # here). All values are identical to the historical constants at c3.
    cd = int(spec.cell_dots)
    cell_px = RECT_PX_PER_DOT * cd                  # rect frame
    scan_cell_px = (float(cell_px) if cell_px_nominal is None
                    else float(cell_px_nominal))    # lock nominal
    # sub-cell anchor search (RECT px), scaled from the c3-validated 5 px
    anchor_shift_px = max(2, round(ANCHOR_MAX_SHIFT_PX * cell_px / 6.0))
    timings: dict = {}
    diag: dict = {"failed_stage": None, "timings_s": timings,
                  "n_search_windows": 0, "n_candidates": 0,
                  "orientations_tried": [], "mirror": False}

    def _fail(stage: str, **extra: object) -> AcquireResult:
        diag["failed_stage"] = stage
        diag.update(extra)
        timings["total"] = time.perf_counter() - t0
        return AcquireResult(ok=False, plane=plane, diagnostics=diag)

    arr = _normalize_refl(img)
    try:
        grid0 = lock_grid(arr, cell_px_nominal=scan_cell_px, cell_dots=cd)
        means0 = sample_cell_means(arr, grid0, cell_dots=cd)
        hard0, llr0 = cell_bits_blind(means0)
    except Exception as e:  # blank paper / no lattice: fail, do not crash
        return _fail("lock", error=f"{type(e).__name__}: {e}")
    # color pages (P1, COLOR-DESIGN D3): Stage A/B word bits come from
    # per-hypothesis site-population fits on the normalized z levels — the
    # whole-window hard0 stays the lattice/orientation substrate only
    z0 = _z_normalize(means0) if spec.n_levels == 3 else None
    timings["lock_detect"] = time.perf_counter() - t0

    t1 = time.perf_counter()
    accepted: tuple[bool, int, dict, dict] | None = None
    for mirror in ((False, True) if include_mirror else (False,)):
        base_bits = hard0[:, ::-1] if mirror else hard0
        base_z = None if z0 is None else (z0[:, ::-1] if mirror else z0)
        for k in range(4):
            diag["orientations_tried"].append((mirror, k))
            bits_k = np.ascontiguousarray(np.rot90(base_bits, k))
            z_k = (None if base_z is None
                   else np.ascontiguousarray(np.rot90(base_z, k)))
            cand, acc, n_win, n_cand = _search_oriented_bits(
                bits_k, layout, seed, plane, max_errors_acq, page_tiles,
                max_tiles, z_grid=z_k)
            diag["n_search_windows"] += n_win
            diag["n_candidates"] += n_cand
            if acc is not None:
                accepted = (mirror, k, cand, acc)
                break
        if accepted is not None:
            break
    timings["search"] = time.perf_counter() - t1
    if accepted is None:
        return _fail("stage_a" if diag["n_candidates"] == 0 else "stage_b")
    mirror, k_acc, cand, acc = accepted
    diag["mirror"] = mirror

    # §15.6 emission hygiene: a caller (page_decode with a piece mask) may
    # pass cell_mask — a bool in the INPUT-window frame marking piece
    # interior. Ride it through the IDENTICAL canonical transform applied to
    # arr->img_c below, so it stays cell-aligned by construction; the
    # payload block then drops cells whose centre falls on backing/neighbor
    # (a square word window emits its whole rectangle otherwise — measured
    # to dump ~0.50-BER cells onto an adjacent scrap's page territory,
    # 2026-07-12 scan-2 forensics). K path only (color emission is a
    # separate stage). None => byte-identical to before.
    cell_mask_c = None
    if cell_mask is not None and spec.n_levels == 1:
        cm = np.asarray(cell_mask, bool)
        if cm.shape != arr.shape:            # defensive: match the norm frame
            yy = np.clip((np.arange(arr.shape[0]) * cm.shape[0]
                          / arr.shape[0]).astype(int), 0, cm.shape[0] - 1)
            xx = np.clip((np.arange(arr.shape[1]) * cm.shape[1]
                          / arr.shape[1]).astype(int), 0, cm.shape[1] - 1)
            cm = cm[yy][:, xx]
        cell_mask_c = (cm if (k_acc == 0 and not mirror)
                       else np.ascontiguousarray(
                           np.rot90(cm[:, ::-1] if mirror else cm, k_acc)))

    # canonical frame: physically derotate the IMAGE, re-lock, re-detect,
    # re-acquire (one orientation) — lock_grid's local origin is arbitrary,
    # so absolute coords must be re-established against the NEW lock.
    t2 = time.perf_counter()
    if k_acc == 0 and not mirror:
        img_c, grid, hard, llr = arr, grid0, hard0, llr0
        means_c = means0
    else:
        img_c = np.ascontiguousarray(
            np.rot90(arr[:, ::-1] if mirror else arr, k_acc))
        try:
            grid = lock_grid(img_c, cell_px_nominal=scan_cell_px,
                             cell_dots=cd)
            means_c = sample_cell_means(img_c, grid, cell_dots=cd)
            hard, llr = cell_bits_blind(means_c)
        except Exception as e:
            return _fail("relock", error=f"{type(e).__name__}: {e}")
        cand, acc, n_win, n_cand = _search_oriented_bits(
            hard, layout, seed, plane, max_errors_acq, page_tiles, max_tiles,
            z_grid=(_z_normalize(means_c) if spec.n_levels == 3 else None))
        diag["n_search_windows"] += n_win
        diag["n_candidates"] += n_cand
        if acc is None:
            return _fail("relock")
    timings["relock"] = time.perf_counter() - t2
    rgb_c = None
    if rgb is not None:
        # same canonical transform as the luma (mirror flip FIRST, then
        # rot90 — np.rot90 default axes (0, 1) leave the channel axis alone)
        rgb_c = rgb if (k_acc == 0 and not mirror) else np.ascontiguousarray(
            np.rot90(rgb[:, ::-1] if mirror else rgb, k_acc))

    msg = acc["message"]
    page = int(msg["page"])
    if "counter" in msg:                 # v3 flat-counter diagnostics
        diag["counter"] = int(msg["counter"])
    oy, ox = acc["cell_origin_abs_yx"]
    h_cells, w_cells = grid.shape_cells

    # integer slip layer first (pilot-word votes), then sub-cell anchors
    t3 = time.perf_counter()
    sites_all, exp_all = _visible_sites(layout, seed, plane, page, (oy, ox),
                                        (h_cells, w_cells), page_tiles)
    # color pages: the accepted address makes the true site cells known, so
    # every downstream word-bit consumer (slip votes, anchor templates,
    # post-fold word certification) reads the P1 site-population fit — the
    # whole-window fit's mis-threshold would double word BER on mostly-ink
    # pages AND feed the post-fold gate a worse channel than Stage B
    # certified (false-veto hazard). K pages: cell_bits_blind, unchanged.
    site_fit = (spec.n_levels == 3
                and sites_all.shape[0] >= SITE_FIT_MIN_CELLS)

    def _detect(means: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return (_site_fit_cell_bits(means, sites_all) if site_fit
                else cell_bits_blind(means))

    g_cur, det_b, det_l = grid, hard, llr
    if site_fit:
        det_b, det_l = _site_fit_cell_bits(means_c, sites_all)
        diag["word_detector"] = "site_fit"
    slip_dy, slip_dx = _pilot_slip_profiles(det_b, sites_all, exp_all)
    diag["slip_cells_yx"] = (int((slip_dy != 0).sum()),
                             int((slip_dx != 0).sum()))
    if (slip_dy != 0).any() or (slip_dx != 0).any():
        def _slip_warp(y_cells: np.ndarray, x_cells: np.ndarray
                       ) -> tuple[np.ndarray, np.ndarray]:
            y = np.asarray(y_cells, np.float64)
            x = np.asarray(x_cells, np.float64)
            iy = np.clip(np.round(y).astype(int), 0, slip_dy.size - 1)
            ix = np.clip(np.round(x).astype(int), 0, slip_dx.size - 1)
            return ((slip_dy[iy] * cd).astype(np.float64),
                    (slip_dx[ix] * cd).astype(np.float64))

        g_cur = _fold_warp_into_grid(g_cur, _slip_warp, cell_dots=cd)
        det_b, det_l = _detect(sample_cell_means(img_c, g_cur, cell_dots=cd))

    sites, exps = _subsample_sites(sites_all, exp_all, max_anchor_sites)
    diag["n_anchor_sites"] = int(sites.shape[0])
    anchors: dict | None = None
    # anchor_rounds=0 disables the anchor stage (diagnostic hook; see
    # docstring). Round index 0, when run, always uses the wide 8 px
    # one-cell slip hunt; later rounds the sub-cell ANCHOR_MAX_SHIFT_PX.
    if anchor_rounds < 0:
        raise ValueError(f"anchor_rounds must be >= 0, got {anchor_rounds}")
    n_rounds = int(anchor_rounds)
    diag["anchor_rounds_run"] = n_rounds
    for rnd in range(n_rounds):
        # round 0 hunts a one-cell branch slip (cell_px + 2 == the frozen
        # 8 px at c3); later rounds refine sub-cell at the scaled shift
        shift = (cell_px + 2) if rnd == 0 else anchor_shift_px
        anchors = measure_pilot_anchors(img_c, g_cur, sites, exps,
                                        detected_bits=det_b,
                                        detected_llr=det_l,
                                        max_shift_px=shift,
                                        cell_dots=cd)
        g_cur = _fold_warp_into_grid(
            g_cur, anchor_warp_field(anchors, g_cur.shape_cells),
            cell_dots=cd)
        det_b, det_l = _detect(sample_cell_means(img_c, g_cur, cell_dots=cd))
    if anchors is not None:
        diag["anchor_lock_rate"] = float(
            np.isfinite(np.asarray(anchors["dy_dots"])).mean())
    timings["anchors"] = time.perf_counter() - t3

    # final detection stage (acquire-v2 F1): the slip/anchor loop always
    # tracks on the GLOBAL detector (robustness); the 16-context ICM stage
    # applies once, on the settled grid, to the detection that feeds the
    # word decode and payload extraction. Measured (run 014.2, e014 c2 on
    # Canon 4800): 7.9% -> 2.6% window BER; gains are SAMPLING-dependent
    # (007.6's no-gain verdict was a 2 px/dot artifact).
    if detector not in ("global", "ctx"):
        raise ValueError(f"detector must be 'global' or 'ctx', "
                         f"got {detector!r}")
    diag["detector"] = detector
    if detector == "ctx" and spec.n_levels == 3:
        # on color pages the ctx stage would re-fit per-context GMMs on ALL
        # cells and clobber the P1 site fit with exactly the all-cells
        # mis-threshold it replaces (a color ctx analog is a declared D4
        # out-of-v1 upgrade path); color payload detection is QDA-owned and
        # never reads det_b. Diagnostics record what actually RAN — a K
        # campaign idiom (detector="ctx") ported to a color page must not
        # read back as ctx having run.
        diag["detector"] = diag.get("word_detector", "global")
        diag["ctx_skipped_color"] = True
    if detector == "ctx" and spec.n_levels == 1:
        det_b, det_l = cell_bits_ctx(
            sample_cell_means(img_c, g_cur, cell_dots=cd))

    # payload extraction at ABSOLUTE coords via the compose-side bijection
    t4 = time.perf_counter()
    page_h, page_w = spec.page_cells_yx
    ay = oy + np.arange(h_cells)
    ax = ox + np.arange(w_cells)
    ok_y = (ay >= 0) & (ay < page_h)
    ok_x = (ax >= 0) & (ax < page_w)
    # fragment-coverage mask (finding [1], wave-3): only cells whose FULL
    # footprint sits inside the fragment CONTENT may emit payload bits —
    # grid.shape_cells counts a last (and, at odd crop offsets, a first)
    # partial cell line whose missing part map_coordinates edge-clamps into
    # ~30-50% BER bits indistinguishable from good ones downstream
    # (measured: abs row 210 at 31.7% / row 30 at 46.7% on the shipped test
    # geometry). The grid is separable, so the mask is per-row/per-column at
    # the measured phase, bounded by the CONTENT extent per axis. The
    # content edge can sit INSIDE the image (scan y-scale > 0, 002.0b: the
    # scan canvas over-runs the content and mode="nearest" replicates the
    # last content line — measured: abs row 210 read 31-34% BER on all three
    # geometry=True seeds while fully inside the image). A clamp-replica
    # band is constant ALONG the clamped axis, so the DIRECTIONAL gradient
    # profile (|d/dy| row means for v, |d/dx| column means for u) collapses
    # there (0.17x median vs ~1.0x in content, measured) where the isotropic
    # gradient magnitude does not (the replicas keep full cross-axis edges).
    # On a real cropped fragment the image edge IS the content edge and the
    # bound reduces to the image extent. +-1.0 px slack: the last complete
    # cell's sampling halo overhangs the last ink edge by a sub-dot margin
    # (measured 0.6-0.8 px keep margins; exclusion margins 4-5 px).
    frag_h_px, frag_w_px = img_c.shape
    gy_c, gx_c = np.gradient(img_c)

    def _content_lohi(prof: np.ndarray) -> tuple[float, float]:
        # smoothing window must span at least one cell-boundary spacing or
        # clean content's INTERIOR rows read zero gradient and the content
        # mask collapses (measured during acquire-v2: a clean c2 page at
        # 8 px/cell trimmed its whole payload with the frozen size-7
        # window). max(7, cell_px+1) == 7 at the 6 px/cell c3 baseline —
        # bit-identical historically.
        filt = max(7, int(round(scan_cell_px)) + 1)
        sm = ndimage.uniform_filter1d(np.asarray(prof, np.float64), filt,
                                      mode="nearest")
        on = sm > 0.5 * float(np.median(sm))
        lo = hi = prof.size // 2
        while hi + 1 < prof.size and on[hi + 1]:
            hi += 1
        while lo - 1 >= 0 and on[lo - 1]:
            lo -= 1
        return float(lo), float(hi)

    y_lo, y_hi = _content_lohi(np.abs(gy_c).mean(axis=1))
    x_lo, x_hi = _content_lohi(np.abs(gx_c).mean(axis=0))
    yy = np.arange(h_cells, dtype=np.float64)
    xx = np.arange(w_cells, dtype=np.float64)
    v_row = np.asarray(g_cur._centers_uv(yy, np.zeros_like(yy))[0]).ravel()
    u_col = np.asarray(g_cur._centers_uv(np.zeros_like(xx), xx)[1]).ravel()
    hpv, hpu = g_cur.pitch_v_px / 2.0, g_cur.pitch_u_px / 2.0
    ok_y &= ((v_row - hpv >= max(0.0, y_lo) - 1.0)
             & (v_row + hpv <= min(float(frag_h_px), y_hi + 1.0) + 1.0))
    ok_x &= ((u_col - hpu >= max(0.0, x_lo) - 1.0)
             & (u_col + hpu <= min(float(frag_w_px), x_hi + 1.0) + 1.0))
    if spec.n_levels == 3:
        # v4 pages acquire on luma (words certify addressing); the payload
        # is per-plane COLOR detection from the RGB channels (dust-trained
        # QDA, _color_payload_stage) and runs AFTER the post-fold word gate
        # below — the luma detector's bits under any single level keystream
        # would be silently WRONG data. Placeholders until then; without an
        # rgb window they are the final (empty) result.
        payload_bits = np.zeros(0, np.uint8)
        payload_cell_index = np.zeros(0, np.int64)
        payload_llr = np.zeros(0, np.float64)
        if rgb_c is None:
            diag["color_payload_pending"] = True
    else:
        idx_map = compose.payload_index_map(spec, seed)
        ks = compose.payload_keystream(spec, seed, page)
        sub_idx = idx_map[np.ix_(ay[ok_y], ax[ok_x])]
        sub_ks = ks[np.ix_(ay[ok_y], ax[ok_x])]
        sub_bits = det_b[np.ix_(np.flatnonzero(ok_y), np.flatnonzero(ok_x))]
        sub_llr = det_l[np.ix_(np.flatnonzero(ok_y), np.flatnonzero(ok_x))]
        sel = sub_idx >= 0
        if cell_mask_c is not None:
            # keep only cells whose centre (v_row, u_col in the img_c frame)
            # lands on the piece interior — same content-extent geometry as
            # the ok_y/ok_x gate above, now 2-D (tilted pieces leave
            # off-mask CORNERS a 1-D row/col gate can't remove)
            rr = np.clip(np.round(v_row[np.flatnonzero(ok_y)]).astype(int),
                         0, cell_mask_c.shape[0] - 1)
            cc = np.clip(np.round(u_col[np.flatnonzero(ok_x)]).astype(int),
                         0, cell_mask_c.shape[1] - 1)
            sel = sel & cell_mask_c[np.ix_(rr, cc)]
        payload_bits = np.bitwise_xor(sub_bits[sel], sub_ks[sel]).astype(np.uint8)
        payload_cell_index = sub_idx[sel].astype(np.int64)
        # keystream XOR in LLR domain = sign flip where ks == 1 (house
        # convention: positive = bit 1, matching cell_bits_blind)
        flip_sel = sub_ks[sel] == 1
        raw_llr_sel = sub_llr[sel].astype(np.float64)
        payload_llr = np.where(flip_sel, -raw_llr_sel, raw_llr_sel)

    n_att, n_dec, n_werr, tile_words = _decode_visible_tiles(
        det_b, layout, seed, plane, page, (oy, ox), page_tiles)
    timings["payload"] = time.perf_counter() - t4

    # F1+PAVA calibration (acquire-v2): the pilot cells of the tiles whose
    # words DECODED are an on-page labeled set (expected bits known exactly;
    # blind-legal — the receiver decoded them). Fit a monotone isotonic map
    # detector-score -> empirical P(bit=1), apply it to the payload scores:
    # the LDPC decoder downstream gets HONEST confidences instead of the
    # 2-Gaussian assumption's (mis)confidence. Sign flips only where the
    # empirical p crosses 0.5 near score 0 (borderline cells).
    if calibrate and spec.n_levels == 1:   # v4: PAVA per level on dust (IMPL-3)
        p_cells = layout.period_cells
        sy_l, sx_l = sites_all[:, 0], sites_all[:, 1]
        tiles_of = ((oy + sy_l) // p_cells, (ox + sx_l) // p_cells)
        lab_ok = np.array([tile_words.get((int(ty_), int(tx_)), -1) >= 0
                           for ty_, tx_ in zip(*tiles_of)], bool)
        diag["n_cal_labels"] = int(lab_ok.sum())
        if lab_ok.sum() >= MIN_CAL_LABELS:
            scores = det_l[sy_l[lab_ok], sx_l[lab_ok]]
            labels = exp_all[lab_ok].astype(np.float64)
            nodes_s, nodes_p = pava_calibrate(scores, labels)
            cal = apply_calibration(raw_llr_sel, nodes_s, nodes_p)
            payload_llr = np.where(flip_sel, -cal, cal)
            payload_bits = (payload_llr > 0).astype(np.uint8)
            diag["calibrated"] = True
            diag["cal_nodes"] = int(nodes_s.size)
        else:
            # NEVER emit raw ctx-GMM scores as LLRs (018.4 forensics):
            # the GMM sigma floor (1e-3) lets raw scores reach ~5e5 —
            # astronomically dishonest confidence that out-votes every
            # calibrated observation (<= ln(n+1) ~ 6.8) in a session
            # union, and it self-selects for BAD windows (geometry
            # drift -> fewer decoded words -> fewer labels). PAVA's
            # 1/(n+2) clamp already scales confidence honestly with the
            # label count, so calibration runs whenever ANY usable label
            # set exists (MIN_CAL_LABELS); a window below even that gets
            # its scores rescaled into the calibrated regime's range.
            diag["calibrated"] = False
            a99 = float(np.percentile(np.abs(raw_llr_sel), 99.0))
            if a99 > 0:
                s = UNCAL_LLR_CAP / a99
                bounded = np.clip(raw_llr_sel * s,
                                  -UNCAL_LLR_CAP, UNCAL_LLR_CAP)
                payload_llr = np.where(flip_sel, -bounded, bounded)
    # post-fold certification gate (2026-07-09 forensics hardening, made
    # BER-AWARE for blind c2, acquire-v2): the Stage-B acceptance certified
    # addressing on the PRE-fold detection; a bad slip/anchor fold can
    # silently re-address the grid afterwards (payload -> ~50% BER with
    # ok=True). The full-strength word decode above ran on the FINAL grid —
    # the gate fires only when its success rate falls FAR below what the
    # channel itself predicts, so it still catches a fold that broke
    # addressing (words -> garbage, n_dec collapses) WITHOUT false-vetoing a
    # legitimately noisy c2 channel whose words fail at t_full even when
    # addressing is intact. Prediction: the pre-fold pooled pilot match
    # (acc["pooled_match"]) gives the pilot BER p; a correctly-addressed
    # word decodes iff it carries <= t_full errors = binomial tail
    # P(errors <= t_full | WORD_BITS, p). At c3 (match ~0.99) that tail is
    # 1.0 and the bar is exactly the old 0.5*n_att (n_dec=n_att always, so
    # c3 is provably unaffected — this only ever relaxes the old rule).
    # Mis-fold protection survives: Stage-B accepted with pooled_match >=
    # 0.85 (min_match), so exp_success is always meaningfully > 0 and a fold
    # that scrambled addressing (n_dec -> ~0) still trips the bar.
    if n_att > 0:
        p_err = min(0.5, max(0.0, 1.0 - float(acc["pooled_match"])))
        t_full = code_for_layout(layout).t_full
        exp_success = float(stats.binom.cdf(t_full, WORD_BITS, p_err))
        if n_dec < 0.5 * exp_success * n_att:
            return _fail("post_fold_words",
                         post_fold_tiles_attempted=n_att,
                         post_fold_tiles_decoded=n_dec,
                         post_fold_word_errors=n_werr,
                         post_fold_expected_success=exp_success,
                         # keep the Stage-B context a forensics reader needs
                         # — the _fail result fields themselves stay defaults
                         page=page, orientation_k=k_acc,
                         cell_origin_abs_yx=(int(oy), int(ox)))
    if spec.n_levels == 3 and rgb_c is not None:
        # color payload AFTER the gate: addressing is certified on the
        # final grid before any color detection consumes it (IMPL-3)
        t5 = time.perf_counter()
        try:
            payload_bits, payload_cell_index, payload_llr = \
                _color_payload_stage(
                    img_c, rgb_c, spec, seed, page, g_cur, (oy, ox),
                    ok_y, ok_x, tile_words, sites_all, exp_all,
                    calibrate=calibrate, color_features=color_features,
                    cell_dots=cd, diag=diag)
        except (ValueError, np.linalg.LinAlgError) as e:
            # label starvation / pathological QDA on a tiny or damaged
            # window: fail THIS window cleanly (page_decode skips it),
            # never crash the scan loop
            return _fail("color_stage", error=f"{type(e).__name__}: {e}",
                         page=page, orientation_k=k_acc,
                         cell_origin_abs_yx=(int(oy), int(ox)))
        timings["color"] = time.perf_counter() - t5
    timings["total"] = time.perf_counter() - t0

    return AcquireResult(
        ok=True, orientation_k=k_acc, mirrored=mirror, page=page, plane=plane,
        ptile_origin_yx=(-(-oy // p), -(-ox // p)),
        cell_origin_abs_yx=(int(oy), int(ox)),
        n_tiles_attempted=n_att, n_tiles_decoded=n_dec,
        stage_b_match_rate=float(acc["pooled_match"]),
        per_tile_match=acc["per_tile_match"],
        n_word_errors_corrected=n_werr, tile_words=tile_words,
        grid=g_cur, anchors=anchors,
        payload_bits=payload_bits, payload_cell_index=payload_cell_index,
        payload_llr=payload_llr, diagnostics=diag)

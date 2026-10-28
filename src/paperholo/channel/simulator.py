"""Print-scan channel simulator (DESIGN.md §3). Measured Layer 0, v0.4.

Two-stage model with two owners, per the 002.0b attribution:

  print_plane()  — PRINTER, print-frozen (travels with the page): development
                   morphology (min ink run 2, min white run 3), anisotropic
                   fractional edge gain, per-plane PSF, per-plane registration
                   drift, smooth 80.5/60.4 mm process-direction wander,
                   page-y scale short by 0.23%, paper mottle. Seeded once at
                   "print time"; rescanning the same PrintedPlane reproduces
                   all of it.
  scan_plane()   — SCANNER, fresh per scan / fixed in scanner frame:
                   stochastic y-transport steps (8.6 per 40 mm), the
                   deterministic 18.63 mm CCD chip-joint comb, +0.62% y scale
                   (mode-dependent), oversampling, sensor noise. One resample
                   total: printer and scanner displacement fields compose
                   before a single map_coordinates call.

All defaults are MEASURED on the reference engine (HP CLJ M281fdw, 600 dpi
native; its flatbed at 1200 dpi), frozen from the 2026-07-04 CAL-1 run:
experiments/002-calibration-page/build/calpage_report.json `channel_params.*`
and scanb_report.json (002.0b rotation test). Those build files are
git-ignored scan artifacts — the numbers are transcribed here with their
report keys; `params_from_calpage_report()` refreshes the per-plane numbers
from a local report after a new CAL-1 run.

The measured PSF sigmas INCLUDE the scanner PSF (slant-edge fit on 1200 dpi
scans, `includes_scanner_psf_and_staircase`), so ScannerParams.mtf_sigma_px
defaults to 0 — setting both would double-blur.

Composite CMY pages (layout_version 4, IMPL-2 2026-07-10): print_scan_cmy /
print_cmy / scan_cmy — per-plane rescreen (calibrated CMY_RESCREEN_SIGMA_FRAC),
per-plane development + measured registration drift, ONE shared wander/scale
draw and ONE scanner realization for all planes (planes fuse together),
density-domain crosstalk composition to an (H, W, 3) RGB scan. The K-plane
path above is untouched.

TODO(M1+): TRC-based partial-coverage response (channel_params.tvi.*.trc),
Y-plane 224 lpi 26.6° clean-path texture (002.1 finding 2, amplitude not yet
pinned), edge raggedness beyond Gaussian blur, hygroexpansion (±0.3%/day).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy import ndimage

MM_PER_INCH = 25.4


# --------------------------------------------------------------------------
# Parameters (defaults = measured M281 + its flatbed, CAL-1 2026-07-04)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PlaneParams:
    """Per-colorant print physics. Sources: channel_params.psf_sigma_dots,
    .gain_edge_dots, .dev_threshold_dots, .plane_offsets, .dmax, .mottle_sigma."""

    psf_sigma_dots_x: float          # slant-edge erf; includes scanner PSF
    psf_sigma_dots_y: float
    gain_edge_v_lines_dots: float    # growth of vertical-line edges (x growth)
    gain_edge_h_lines_dots: float    # growth of horizontal-line edges (y growth)
    dmax: float                      # solid density above paper
    min_ink_run_dots: int = 2        # isolated 1-dot ink does not develop
    min_white_run_dots: int = 3      # detection threshold (metadata; see below)
    # Morphology actually applied: white runs BELOW this fully close (measured:
    # 1-dot white is erased). Runs in [this, min_white_run) survive with
    # context-dependent attenuation that this model does NOT yet capture —
    # hard-closing them was measured WRONG at cell=2 (fills 31% of a c2 field
    # vs hardware c2 hard BER 11.1%, which the softened model reproduces at
    # ~15%). TODO(M2): context-dependent development from the 003 motif
    # library flux tables.
    white_fill_below_dots: int = 2
    reg_dy_center_dots: float = 0.0  # registration vs K at page center
    reg_dy_slope_dots_per_100mm: float = 0.0
    reg_dx_center_dots: float = 0.0
    reg_dx_slope_dots_per_100mm: float = 0.0
    # Density noise at the 0.508 mm block scale vs local coverage:
    # channel_params.mottle_sigma sigma_D_vs_coverage p10..p100. The
    # coverage-0 point is not in the table; 0.011 is the white-model scan
    # residual (6.5/255 counts) minus the sensor share, in density units.
    mottle_sigma_D_vs_coverage: tuple[float, ...] = (
        0.011, 0.016, 0.022, 0.027, 0.031, 0.033,
        0.036, 0.037, 0.041, 0.039, 0.042)  # coverage 0.0, 0.1, ... 1.0


_MOTTLE_COV_GRID = np.linspace(0.0, 1.0, 11)

# channel_params 2026-07-04; gain anisotropy is V>H for CMK (Y loses ink).
M281_PLANES: dict[str, PlaneParams] = {
    "K": PlaneParams(1.063, 1.016, 0.377, 0.287, 1.526),
    "C": PlaneParams(0.945, 1.017, 0.721, 0.588, 1.153,
                     reg_dy_center_dots=0.37, reg_dy_slope_dots_per_100mm=-0.74,
                     reg_dx_center_dots=-0.53, reg_dx_slope_dots_per_100mm=0.17,
                     mottle_sigma_D_vs_coverage=(
                         0.011, 0.020, 0.032, 0.040, 0.042, 0.044,
                         0.042, 0.038, 0.030, 0.022, 0.007)),
    "M": PlaneParams(1.143, 1.148, 0.251, 0.089, 2.396,
                     reg_dy_center_dots=-0.52, reg_dy_slope_dots_per_100mm=-1.52,
                     reg_dx_center_dots=0.64, reg_dx_slope_dots_per_100mm=0.38,
                     mottle_sigma_D_vs_coverage=(
                         0.011, 0.013, 0.022, 0.031, 0.034, 0.054,
                         0.084, 0.135, 0.189, 0.225, 0.244)),
    "Y": PlaneParams(1.173, 1.384, -0.249, 0.001, 0.772,
                     reg_dy_center_dots=-2.17, reg_dy_slope_dots_per_100mm=-1.91,
                     reg_dx_center_dots=0.50, reg_dx_slope_dots_per_100mm=0.29,
                     mottle_sigma_D_vs_coverage=(
                         0.011, 0.008, 0.016, 0.020, 0.025, 0.030,
                         0.036, 0.039, 0.033, 0.033, 0.035)),
}


@dataclass(frozen=True)
class PrinterParams:
    """Print-frozen engine model. Sources: scanb_report scale_separation
    (y short −0.226% ± 0.03) and transport wander_fit (80.48/60.36 mm,
    ~1.0/1.14 dots, print-frozen: corr 0.88-0.93 across scans);
    channel_params.banding = bounded null (upper bound 0.0027 density)."""

    dpi: int = 600
    wander_components: tuple[tuple[float, float], ...] = (
        (80.48, 0.98), (60.36, 1.14))   # (period_mm, amp_dots); phases per page
    y_scale_error: float = -0.00226      # page-y prints SHORT of page-x
    banding_amp_density: float = 0.0     # measured bounded null (<= 0.0027)
    banding_period_mm: float = 2.36      # strongest non-significant candidate
    paper_reflectance: float = 0.92
    mottle_scale_mm: float = 0.508       # mottle_sigma block size


@dataclass(frozen=True)
class ScannerParams:
    """Flatbed model, scanner frame. Sources: channel_params.transport_steps
    (52 steps, 8.6/40 mm, 0.25-1.95 dots, median 0.52) reattributed to the
    scanner by 002.0b; scanb verify-pass comb (scanner-x = 14.1 + n*18.63 mm,
    ~-0.9 dots each); scale decomposition s_y - s_x = +0.616% (sigma_repeat
    0.158%, MODE-DEPENDENT: never mix grey/color scans for absolute y)."""

    oversample: int = 2                  # scan px per printer dot (1200/600)
    y_step_rate_per_mm: float = 8.6 / 40.0
    y_step_size_dots: tuple[float, float, float] = (0.251, 0.523, 1.954)
    comb_pitch_mm: float = 18.63         # CCD chip-joint fixed pattern (x axis)
    comb_phase_mm: float = 14.1
    comb_step_dots: float = -0.9
    y_scale_error: float = 0.00616       # vs x; fresh sigma 0.00158 per scan
    y_scale_sigma: float = 0.00158
    mtf_sigma_px: float = 0.0            # 0: already inside measured plane PSF
    noise_sigma_refl: float = 0.010      # sensor share of the 6.5/255-count
    #                                      white residual (rest is paper
    #                                      texture, modeled as mottle)


# RIP contone screens, measured 002.0/002.2: C,M = 165 lpi +/-14 deg
# (the +/- assignment between C and M is not individually pinned), Y = 212 lpi
# 45 deg (b-channel attribution). Applies to ANY region-overlapping emission
# (Layer-0 freeze: overlap => screened contone, always; no PS escape hatch).
M281_SCREENS: dict[str, tuple[float, float]] = {
    "C": (165.0, 14.0), "M": (165.0, -14.0), "Y": (212.0, 45.0),
}

# Density-domain crosstalk: D[ch] = sum_p A[ch][p] * ink_p, channels r,g,b x
# planes C,M,Y,K. channel_params.crosstalk_matrix (cond 2.445); linear fit on
# solids+paper — sub-additivity at stacked solids is documented there.
M281_CROSSTALK_A: tuple[tuple[float, ...], ...] = (
    (0.8101, -0.1142, -0.0762, 1.6557),
    (-0.0380, 1.3139, -0.3538, 0.9516),
    (-0.1022, 0.2887, 0.5512, 0.8431),
)
CROSSTALK_PLANES = ("C", "M", "Y", "K")

M281_PRINTER = PrinterParams()
M281_SCANNER = ScannerParams()


@dataclass
class ChannelParams:
    """One plane through print + scan. `geometry=False` disables every
    displacement term (wander, scales, steps, comb) for sync-bypassed tests;
    the development/PSF/noise physics stay on."""

    printer: PrinterParams = M281_PRINTER
    scanner: ScannerParams = M281_SCANNER
    plane: str = "K"
    emission: str = "clean_mask"        # or "screened_composite" (rescreen first)
    seed: int = 0                       # print-frozen randomness
    scan_seed: int | None = None        # per-scan randomness (default seed+1)
    geometry: bool = True

    @property
    def scan_oversample(self) -> int:
        return self.scanner.oversample

    @property
    def plane_params(self) -> PlaneParams:
        return M281_PLANES[self.plane]


# --------------------------------------------------------------------------
# Print stage (everything frozen into the page)
# --------------------------------------------------------------------------

@dataclass
class PrintedPlane:
    """A printed page: reflectance at dot resolution plus the print-frozen
    displacement description that scan_plane() composes into its resample."""

    refl_dots: np.ndarray               # float reflectance, dot resolution
    dpi: int
    wander_dy_of_y: np.ndarray          # 1-D, dots, indexed by page-y dot
    y_scale_error: float
    reg_dy_of_y: np.ndarray             # per-plane registration drift, 1-D
    reg_dx_of_x: np.ndarray


def _develop(bits: np.ndarray, pl: PlaneParams) -> np.ndarray:
    """Electrophotographic development at dot resolution: white gaps below
    white_fill_below_dots close solid, ink features below min_ink_run die,
    then fractional anisotropic edge gain (negative gain = the plane loses
    edge ink, e.g. Y). 2-dot white attenuation is context-dependent and not
    yet modeled (see PlaneParams.white_fill_below_dots)."""
    ink_b = bits.astype(bool)
    w = pl.white_fill_below_dots
    if w > 1:
        ink_b = ndimage.binary_closing(
            ink_b, structure=np.ones((w, w), bool), border_value=0)
    k = pl.min_ink_run_dots
    if k > 1:
        ink_b = ndimage.binary_opening(
            ink_b, structure=np.ones((k, k), bool), border_value=0)
    ink = ink_b.astype(np.float64)

    for gain, size in ((pl.gain_edge_v_lines_dots, (1, 3)),
                       (pl.gain_edge_h_lines_dots, (3, 1))):
        if gain >= 0:
            ink = ink + gain * (ndimage.grey_dilation(ink, size=size) - ink)
        else:
            ink = ink + gain * (ink - ndimage.grey_erosion(ink, size=size))
    return np.clip(ink, 0.0, 1.0)


def _smooth_field(shape: tuple[int, int], cells: int, rng: np.random.Generator) -> np.ndarray:
    """Smooth random field via a coarse control grid, unit std."""
    cells = max(2, cells)
    coarse = rng.standard_normal((cells, cells))
    f = ndimage.zoom(coarse, (shape[0] / cells, shape[1] / cells), order=3)
    f = f[: shape[0], : shape[1]]
    return f / max(f.std(), 1e-9)


def print_plane(plane_bits: np.ndarray, p: ChannelParams) -> PrintedPlane:
    """Print a 1-bit plane: returns dot-resolution reflectance plus the
    print-frozen displacement fields. plane_bits in {0,1}, 1 = ink."""
    rng = np.random.default_rng(p.seed)
    pr, pl = p.printer, p.plane_params
    h, w = plane_bits.shape
    dots_per_mm = pr.dpi / MM_PER_INCH

    ink = _develop(plane_bits, pl)
    ink = ndimage.gaussian_filter(
        ink, (pl.psf_sigma_dots_y, pl.psf_sigma_dots_x))

    # Ink coverage -> density -> reflectance, plus mottle (density-domain,
    # 0.5 mm scale, coverage-dependent sigma per the measured table) and the
    # banding bounded-null hook (default amp 0).
    density = pl.dmax * ink
    mottle_cells = int(h / (pr.mottle_scale_mm * dots_per_mm))
    sigma_d = np.interp(ink, _MOTTLE_COV_GRID,
                        np.asarray(pl.mottle_sigma_D_vs_coverage))
    density = density + sigma_d * _smooth_field((h, w), mottle_cells, rng)
    if pr.banding_amp_density > 0:
        y_mm = np.arange(h)[:, None] / dots_per_mm
        density = density + pr.banding_amp_density * np.sin(
            2 * np.pi * y_mm / pr.banding_period_mm + rng.uniform(0, 2 * np.pi))
    refl = pr.paper_reflectance * np.power(10.0, -np.clip(density, 0.0, None))

    # Print-frozen displacements, sampled per page-y dot. Wander phases are
    # arbitrary per page (printed instance), amplitudes are the measured fit.
    y_dots = np.arange(h, dtype=np.float64)
    y_mm = y_dots / dots_per_mm
    wander = np.zeros(h)
    if p.geometry:
        for period_mm, amp_dots in pr.wander_components:
            wander += amp_dots * np.sin(
                2 * np.pi * y_mm / period_mm + rng.uniform(0, 2 * np.pi))
    # Per-plane registration drift: linear in page position, centered on the
    # field (drift models are page-scale; a small field sees the local slope).
    x_mm = np.arange(w, dtype=np.float64) / dots_per_mm
    reg_dy = pl.reg_dy_center_dots + pl.reg_dy_slope_dots_per_100mm * (
        (y_mm - y_mm.mean()) / 100.0)
    reg_dx = pl.reg_dx_center_dots + pl.reg_dx_slope_dots_per_100mm * (
        (x_mm - x_mm.mean()) / 100.0)
    if not p.geometry:
        reg_dy = np.zeros_like(reg_dy)
        reg_dx = np.zeros_like(reg_dx)

    return PrintedPlane(
        refl_dots=refl, dpi=pr.dpi, wander_dy_of_y=wander,
        y_scale_error=pr.y_scale_error if p.geometry else 0.0,
        reg_dy_of_y=reg_dy, reg_dx_of_x=reg_dx)


# --------------------------------------------------------------------------
# Scan stage (fresh randomness per scan; one resample for the whole chain)
# --------------------------------------------------------------------------

def _scanner_y_steps(n_rows_px: int, sc: ScannerParams, os: int, dpi: int,
                     rng: np.random.Generator) -> np.ndarray:
    """Cumulative y-transport step profile in dots, per scan row. Step
    positions are Poisson at the measured rate; sizes follow the measured
    skewed distribution (min + exponential at the median, truncated at max),
    signs random — net drift is the y-scale term's job, not the steps'."""
    dy = np.zeros(n_rows_px)
    row_mm = np.arange(n_rows_px) / (os * dpi / MM_PER_INCH)
    lo, med, hi = sc.y_step_size_dots
    n_exp = sc.y_step_rate_per_mm * row_mm[-1] if n_rows_px > 1 else 0.0
    n_steps = rng.poisson(n_exp)
    if n_steps == 0:
        return dy
    at_mm = rng.uniform(0, row_mm[-1], n_steps)
    sizes = np.minimum(lo + rng.exponential(med - lo, n_steps), hi)
    signs = rng.choice((-1.0, 1.0), n_steps)
    for a, s, g in zip(at_mm, sizes, signs):
        dy[row_mm >= a] += g * s
    return dy


def _scanner_x_comb(n_cols_px: int, sc: ScannerParams, os: int, dpi: int) -> np.ndarray:
    """Deterministic CCD chip-joint staircase in dots, per scan column —
    fixed in the scanner frame (calibratable once per scanner)."""
    col_mm = np.arange(n_cols_px) / (os * dpi / MM_PER_INCH)
    joints = np.floor((col_mm - sc.comb_phase_mm) / sc.comb_pitch_mm) + 1
    return sc.comb_step_dots * np.clip(joints, 0, None)


def scan_plane(printed: PrintedPlane, p: ChannelParams,
               rotate90: bool = False) -> np.ndarray:
    """Scan a PrintedPlane: fresh scanner randomness (p.scan_seed), composed
    with the print-frozen fields, one bilinear resample, then MTF and noise.

    rotate90=True puts the page's process direction on the CCD axis (the
    002.0b protocol, measured 1.3-2.0 pp better) — the page is rotated on
    the platen, so scanner terms act on swapped page axes.
    """
    sc = p.scanner
    os = sc.oversample
    seed = p.seed + 1 if p.scan_seed is None else p.scan_seed
    rng = np.random.default_rng(seed)

    page = printed.refl_dots if not rotate90 else np.rot90(printed.refl_dots)
    h_px, w_px = page.shape[0] * os, page.shape[1] * os

    # Scanner-frame source coordinates in dot units.
    ys = np.arange(h_px, dtype=np.float64) / os
    xs = np.arange(w_px, dtype=np.float64) / os
    if p.geometry:
        y_scale = sc.y_scale_error + rng.normal(0.0, sc.y_scale_sigma)
        ys = ys * (1.0 + y_scale)
        ys = ys + _scanner_y_steps(h_px, sc, os, printed.dpi, rng)
        xs = xs + _scanner_x_comb(w_px, sc, os, printed.dpi)
    yy = np.repeat(ys[:, None], w_px, axis=1)
    xx = np.repeat(xs[None, :], h_px, axis=0)

    # Compose the print-frozen displacements (page frame; small-displacement
    # linearization: fields are evaluated at the nominal position).
    n_y, n_x = printed.wander_dy_of_y.shape[0], printed.reg_dx_of_x.shape[0]
    if rotate90:
        # np.rot90: original (y, x) -> (row = W-1-x, col = y), so page y runs
        # along scanner x and page x runs along -scanner y.
        iy = np.clip(xx.astype(int), 0, n_y - 1)                 # page y
        ix = np.clip((n_x - 1) - yy.astype(int), 0, n_x - 1)     # page x
        dyp = (printed.wander_dy_of_y[iy] + printed.reg_dy_of_y[iy]
               + xx * printed.y_scale_error * -1.0)  # y short => denser
        xx = xx + dyp                       # page-y displacement, scanner x
        yy = yy - printed.reg_dx_of_x[ix]   # page-x displacement, axis flipped
    else:
        iy = np.clip(yy.astype(int), 0, n_y - 1)
        ix = np.clip(xx.astype(int), 0, n_x - 1)
        dyp = (printed.wander_dy_of_y[iy] + printed.reg_dy_of_y[iy]
               + yy * printed.y_scale_error * -1.0)  # y short => denser
        yy = yy + dyp
        xx = xx + printed.reg_dx_of_x[ix]

    refl = ndimage.map_coordinates(page, [yy, xx], order=1, mode="nearest")
    if sc.mtf_sigma_px > 0:
        refl = ndimage.gaussian_filter(refl, sc.mtf_sigma_px)
    refl = refl + rng.normal(0.0, sc.noise_sigma_refl, refl.shape)
    return np.clip(refl, 0.0, 1.0)


def print_scan(plane_bits: np.ndarray, p: ChannelParams) -> np.ndarray:
    """Print + scan in one call (M0 interface). For split control — e.g.
    scanning one printed page twice — use print_plane() / scan_plane()."""
    if p.emission == "screened_composite":
        lpi, angle = M281_SCREENS.get(p.plane, (165.0, 14.0))
        plane_bits = rescreen_plane(plane_bits, p.printer.dpi, lpi, angle)
    return scan_plane(print_plane(plane_bits, p), p)


# --------------------------------------------------------------------------
# Emission-path and color models
# --------------------------------------------------------------------------

def rescreen_plane(plane_bits: np.ndarray, dpi: int,
                   lpi: float, angle_deg: float,
                   contone_sigma_dots: float | None = None) -> np.ndarray:
    """The RIP's contone re-screen (Layer-0 freeze: any region-overlapping
    emission is screened, always). The plane is treated as contone coverage
    and re-halftoned with a rotated clustered-dot screen — off-lattice at
    cell 3/4/6 by construction. First-order model; calibrate against the
    002.2 screen-tax spectra before trusting fine structure.

    contone_sigma_dots: pre-threshold contone blur. Default None keeps the
    original 0.5 * period (the frozen K screened-path behavior — every
    existing call site is byte-identical). The composite CMY path passes
    CMY_RESCREEN_SIGMA_FRAC * period, calibrated 2026-07-10 (IMPL-2)."""
    period_dots = dpi / lpi
    if contone_sigma_dots is None:
        contone_sigma_dots = 0.5 * period_dots
    contone = ndimage.gaussian_filter(
        plane_bits.astype(np.float64), contone_sigma_dots)
    yy, xx = np.mgrid[0:plane_bits.shape[0], 0:plane_bits.shape[1]].astype(np.float64)
    a = np.deg2rad(angle_deg)
    u = (xx * np.cos(a) + yy * np.sin(a)) / period_dots
    v = (-xx * np.sin(a) + yy * np.cos(a)) / period_dots
    threshold = 0.5 - 0.25 * (np.cos(2 * np.pi * u) + np.cos(2 * np.pi * v))
    return (contone > threshold).astype(np.uint8)


def planes_to_rgb_refl(ink_coverage: dict[str, np.ndarray],
                       paper_reflectance: float = 0.92) -> np.ndarray:
    """Compose per-plane ink coverage into an (H, W, 3) r,g,b reflectance
    stack through the measured density-domain crosstalk matrix (linear model;
    sub-additivity at stacked solids is a documented approximation)."""
    shape = next(iter(ink_coverage.values())).shape
    out = np.empty((*shape, 3))
    for ch in range(3):
        density = np.zeros(shape)
        for pi, plane in enumerate(CROSSTALK_PLANES):
            if plane in ink_coverage:
                density += M281_CROSSTALK_A[ch][pi] * ink_coverage[plane]
        out[..., ch] = paper_reflectance * np.power(10.0, -np.clip(density, 0.0, None))
    return out


# --------------------------------------------------------------------------
# Composite CMY pages (layout_version 4; COLOR-DESIGN D5/D6, IMPL-2)
# --------------------------------------------------------------------------

CMY_PLANE_ORDER = ("C", "M", "Y")   # level order everywhere (compose contract)

# Contone-blur fraction of the screen period for the CMY composite path,
# CALIBRATED 2026-07-10 (IMPL-2) against the measured 8-state c3 composite
# genie anchor. Regenerable in-repo footing (tests/test_color_sim._page +
# _genie_qda_read: 120x120-cell page, cross-half QDA on full-cell-mean
# RGB): sim soft-MI 1.760-1.766 b/cell across 4 seeds vs CAL-1 002.0's
# measured 1.76 — same construction, same engine, genie footing. (The
# original calibration probe read 1.77-1.78 on a scratch-script footing;
# the committed-construction numbers above are the durable anchor.) The
# K screened path keeps its original (uncalibrated) 0.5 default — it was
# never hardware-anchored and existing consumers (msel1 M0 gate) pin its
# behavior. KNOWN RESIDUAL: the sim's per-level reliability ORDER is
# C>M>Y in ERROR (sim Y strongest, hardware Y weakest: measured label-bit
# BER C 6.3 / M 10.2 / Y 15.9%, sim ~19.2 / 16.6 / 12.2 at this sigma) —
# the Y-weakness mechanisms (224 lpi clean-path texture, development
# raggedness) are declared TODOs; take per-LEVEL conclusions from
# hardware, not from this sim.
CMY_RESCREEN_SIGMA_FRAC = 0.30


@dataclass
class PrintedCmyPage:
    """A printed COMPOSITE page: per-plane INK COVERAGE at dot resolution
    (crosstalk composition happens in the scan frame, where it is pointwise)
    plus the print-frozen displacement description.

    All planes fuse onto the paper in one pass, so the process-direction
    wander and the page-y scale are drawn ONCE and shared by every plane;
    only the per-plane registration drift fields differ (the CAL-1 drift
    models: Y -0.5..-4.9 dots linear in y, M -2.6..+1.1, C +-1.1 — frozen
    as M281_PLANES[plane].reg_*)."""

    ink_dots: np.ndarray            # (3, H, W) float coverage, planes C, M, Y
    dpi: int
    wander_dy_of_y: np.ndarray      # shared, 1-D dots, indexed by page-y dot
    y_scale_error: float            # shared
    reg_dy_of_y: np.ndarray         # (3, H) per-plane registration drift
    reg_dx_of_x: np.ndarray         # (3, W)
    paper_reflectance: float


def print_cmy(plane_bits: np.ndarray, p: ChannelParams) -> PrintedCmyPage:
    """Print a 3-plane composite: per-plane development/PSF/mottle physics
    (the K-path _develop pipeline per M281_PLANES), ONE shared wander +
    y-scale draw (planes fuse together), per-plane registration fields.

    plane_bits (3, H, W) uint {0,1}, plane order C, M, Y. RAW planes: the
    RIP re-screen belongs to the emission path — print_scan_cmy applies it
    per p.emission, mirroring the K print_scan/print_plane split.

    Mottle is the measured density-domain table converted to ink units
    (sigma_D / dmax) so the composed density through the crosstalk matrix
    reproduces the K-path density perturbation; super-solid excursions are
    truncated at coverage 1.0 (bounded, <= ~0.04 D)."""
    bits = np.asarray(plane_bits)
    if bits.ndim != 3 or bits.shape[0] != 3:
        raise ValueError(f"plane_bits must be (3, H, W) C,M,Y, got {bits.shape}")
    pr = p.printer
    _, h, w = bits.shape
    dots_per_mm = pr.dpi / MM_PER_INCH
    mottle_cells = int(h / (pr.mottle_scale_mm * dots_per_mm))

    y_mm = np.arange(h, dtype=np.float64) / dots_per_mm
    x_mm = np.arange(w, dtype=np.float64) / dots_per_mm

    ink = np.empty((3, h, w))
    reg_dy = np.zeros((3, h))
    reg_dx = np.zeros((3, w))
    for li, plane in enumerate(CMY_PLANE_ORDER):
        pl = M281_PLANES[plane]
        dev = _develop(bits[li], pl)
        dev = ndimage.gaussian_filter(
            dev, (pl.psf_sigma_dots_y, pl.psf_sigma_dots_x))
        # independent per-plane mottle (separate toner/development stations)
        rng_pl = np.random.default_rng((p.seed, li))
        sigma_ink = np.interp(dev, _MOTTLE_COV_GRID,
                              np.asarray(pl.mottle_sigma_D_vs_coverage)) / pl.dmax
        ink[li] = np.clip(
            dev + sigma_ink * _smooth_field((h, w), mottle_cells, rng_pl),
            0.0, 1.0)
        if p.geometry:
            reg_dy[li] = pl.reg_dy_center_dots + (
                pl.reg_dy_slope_dots_per_100mm * (y_mm - y_mm.mean()) / 100.0)
            reg_dx[li] = pl.reg_dx_center_dots + (
                pl.reg_dx_slope_dots_per_100mm * (x_mm - x_mm.mean()) / 100.0)

    # Shared print-frozen wander: ONE draw for the fused page (K print_plane
    # draws per plane_bits call; here that would fake per-plane wander).
    rng_geom = np.random.default_rng(p.seed)
    wander = np.zeros(h)
    if p.geometry:
        for period_mm, amp_dots in pr.wander_components:
            wander += amp_dots * np.sin(
                2 * np.pi * y_mm / period_mm + rng_geom.uniform(0, 2 * np.pi))

    return PrintedCmyPage(
        ink_dots=ink, dpi=pr.dpi, wander_dy_of_y=wander,
        y_scale_error=pr.y_scale_error if p.geometry else 0.0,
        reg_dy_of_y=reg_dy, reg_dx_of_x=reg_dx,
        paper_reflectance=pr.paper_reflectance)


def _scan_cmy_inks(printed: PrintedCmyPage, p: ChannelParams,
                   rotate90: bool) -> np.ndarray:
    """(3, H_px, W_px) per-plane ink coverage in the SCAN frame: each plane
    resampled through the SAME scanner realization (identical scan_seed =>
    identical y-steps/comb/scale draws — scan_plane consumes its rng
    identically for equal shapes) composed with the shared print-frozen
    fields plus that plane's registration drift. Sensor noise is NOT applied
    here (it is per RGB channel, after crosstalk composition)."""
    quiet = replace(p.scanner, noise_sigma_refl=0.0)
    seed = p.seed + 1 if p.scan_seed is None else p.scan_seed
    p_plane = replace(p, scanner=quiet, scan_seed=seed)
    out = []
    for li in range(3):
        pp = PrintedPlane(
            refl_dots=printed.ink_dots[li], dpi=printed.dpi,
            wander_dy_of_y=printed.wander_dy_of_y,
            y_scale_error=printed.y_scale_error,
            reg_dy_of_y=printed.reg_dy_of_y[li],
            reg_dx_of_x=printed.reg_dx_of_x[li])
        out.append(scan_plane(pp, p_plane, rotate90=rotate90))
    return np.stack(out)


def scan_cmy(printed: PrintedCmyPage, p: ChannelParams,
             rotate90: bool = False) -> np.ndarray:
    """Scan a PrintedCmyPage -> (H_px, W_px, 3) r,g,b reflectance: one shared
    scanner realization for all planes (the page is one object), crosstalk
    composition via the measured density-domain matrix, then independent
    per-channel sensor noise (fresh from p.scan_seed, separate stream from
    the geometry draws)."""
    inks = _scan_cmy_inks(printed, p, rotate90)
    rgb = planes_to_rgb_refl(
        {pl: inks[li] for li, pl in enumerate(CMY_PLANE_ORDER)},
        printed.paper_reflectance)
    seed = p.seed + 1 if p.scan_seed is None else p.scan_seed
    # separate stream from scan_plane's default_rng(seed) geometry draws
    rng_noise = np.random.default_rng((seed, 0x60B))
    rgb = rgb + rng_noise.normal(0.0, p.scanner.noise_sigma_refl, rgb.shape)
    return np.clip(rgb, 0.0, 1.0)


def print_scan_cmy(plane_bits: np.ndarray, p: ChannelParams) -> np.ndarray:
    """Print + scan a 3-plane composite page -> (H_px, W_px, 3) RGB scan.

    Emission model (Layer-0 freeze): on the M281, region overlap => screened
    contone ALWAYS — pass emission="screened_composite" for M281 realism
    (each plane re-screened with its measured M281_SCREENS ruling at the
    calibrated CMY_RESCREEN_SIGMA_FRAC before development).
    emission="clean_mask" models the AltaLink-class overlap-preserving
    unscreened path (007.6) — NOT the M281."""
    bits = np.asarray(plane_bits)
    if bits.ndim != 3 or bits.shape[0] != 3:
        raise ValueError(f"plane_bits must be (3, H, W) C,M,Y, got {bits.shape}")
    if p.emission == "screened_composite":
        bits = np.stack([
            rescreen_plane(
                bits[li], p.printer.dpi, *M281_SCREENS[plane],
                contone_sigma_dots=(CMY_RESCREEN_SIGMA_FRAC
                                    * p.printer.dpi / M281_SCREENS[plane][0]))
            for li, plane in enumerate(CMY_PLANE_ORDER)])
    return scan_cmy(print_cmy(bits, p), p)


# --------------------------------------------------------------------------
# Refreshing measured numbers after a new CAL-1 run
# --------------------------------------------------------------------------

def params_from_calpage_report(path: str | Path) -> dict[str, PlaneParams]:
    """Rebuild per-plane params from a calpage_report.json channel_params
    block (build artifacts are git-ignored; module defaults are the frozen
    2026-07-04 values). Printer/scanner geometry comes from scanb_report
    (002.0b) and is not re-fit here."""
    cp = json.loads(Path(path).read_text())["channel_params"]
    planes: dict[str, PlaneParams] = {}
    for name, base in M281_PLANES.items():
        psf, gain = cp["psf_sigma_dots"][name], cp["gain_edge_dots"][name]
        off = cp.get("plane_offsets", {}).get(name)
        table = cp["mottle_sigma"][name]["sigma_D_vs_coverage"]
        sigma_d = (base.mottle_sigma_D_vs_coverage[0],) + tuple(
            table[f"p{i}0"] for i in range(1, 11))
        planes[name] = replace(
            base,
            psf_sigma_dots_x=psf["x"], psf_sigma_dots_y=psf["y"],
            gain_edge_v_lines_dots=gain["v_lines"],
            gain_edge_h_lines_dots=gain["h_lines"],
            dmax=cp["dmax"][name], mottle_sigma_D_vs_coverage=sigma_d,
            **({} if off is None else dict(
                reg_dy_center_dots=off["dy_center_dots"],
                reg_dy_slope_dots_per_100mm=off["dy_slope_dots_per_100mm"],
                reg_dx_center_dots=off["dx_center_dots"],
                reg_dx_slope_dots_per_100mm=off["dx_slope_dots_per_100mm"])))
    return planes

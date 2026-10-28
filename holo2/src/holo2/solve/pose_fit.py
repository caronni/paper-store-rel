"""The E022 pose kernel: prepare, fit, sample, lay out, subdivide.

Ported from ``src/holo/receive/placement/geometry.py`` at 594a465,
refactored per H4-PLAN R4 — the code is holo2's own, the ARITHMETIC is
v1's exactly.  This is W0 sub-wave A2; nothing imports it yet, and W0
changes no behaviour.

The numerical primitives themselves are older than v1: they are E022 v2's
(``paperholo.pilotsearch``) gradient-spectrum fundamentals, zoom-DFT
sub-bin peaks, full affine Jacobian, phase objective, one 0.7-cell box
aperture, and one order-1 read per cell centre.  Window layout,
subdivision and per-window radiometrics keep the measured 200/40 E022
policy, which now arrives as :data:`~holo2.solve.place_model.OR9_FLOORS`
data rather than as literals.  Production uses no characterization
instrument as an algorithmic or numerical dependency.

**THE ONE STRUCTURAL CHANGE (R5 seam prep, ruled).**  v1's fit writes
region-shared MUTABLE state: the first window whose lattice clears every
geometric gate seeds ``RegionContext.lattice_f`` (geometry.py:431-432),
and two later paths read it — an edge window too small for its own
spectrum takes it as its ONLY fit (:422-423), and a full-size window
whose blind fit fails the gates zoom-refits around it (:415-421).  Small
window poses therefore depend on the ORDER windows were fitted in.  Here
the seed is an explicit PARAMETER and an explicit RETURN:
:func:`fit_window_pose` takes ``lattice_seed`` and returns, in
:class:`WindowFit`, the seed it fitted (when it had none) or the seed it
used (when it had one) — beside the pose, and also when the phase
objective refuses, because v1 seeds BEFORE fitting phase on purpose.  No
hidden mutation, no module state, and a fit is a pure function of its
arguments.  W1's provider turns the returned seed into the R5 durable
per-(footing, region) fact, derived from the best-supported window rather
than from whoever fired first — and reads
:attr:`WindowFit.unconditioned_seed` to know WHICH fits are entitled to
propose one (W1 addition; reporting only, no arithmetic moved).  All
three v1 paths — blind fit, seeded
edge-window fit, seeded zoom-refit — keep v1's arithmetic exactly,
including WHICH prior the refit uses (the seed if there is one, else the
declared axis-aligned spec pitch) and the fact that a seeded region never
re-seeds.

R4 freedoms exercised (code only, never arithmetic):

* ``RegionContext`` -> :class:`PreparedRegion`, and its ``crop`` field ->
  ``image``: v1's ``crop`` is not the crop, it is the crop with
  unsupported pixels FILLED to the platen backing (the constructor is
  handed ``filled``, geometry.py:150-154), one letter away from the
  ``filtered`` field beside it.  ``lattice_f`` is gone (above).
* ``prepare_region`` takes the :class:`~holo2.capture.SupportMask`
  instead of a survey region: ``bbox`` and ``rasterize_crop`` were all v1
  read off it, and the mask is what holo2 publishes across the package
  boundary.
* ``_median_radiometrics`` -> :func:`median_radiometrics`, public,
  because the median detector and the bounded-evidence convention are a
  named E022 rule a test may pin directly.
* The subdivision depth cap was the bare literal ``window.depth >= 1``
  (geometry.py:572); it is now the ``subdivision_max_depth`` row of the
  OR-9 table, and this module is that table's first consumer.
  ``min_window_cells`` is read from the table too, as the value
  ``PlacementConfig``'s knob defaults to and the pin that says so.
* :class:`SegmentSample` and :class:`AddressPatch` are frozen (v1's were
  mutable ``slots`` dataclasses that nothing mutated after
  ``__post_init__``), and ``AddressPatch.shape_yx`` returns its two ints
  positionally instead of through a generator.

Arithmetic deliberately NOT touched, idiom for idiom: ``int(round(...))``
everywhere v1 rounds a pixel extent (half-to-even, and never ``np.rint``
or ``int(np.ceil(...))`` — three different functions); bare ``round()``
in the subdivision corner offsets; ``float32`` for the filled image, the
filter output, the gradient and its Hanning windows, and the sampled
means/evidence; ``float64`` for every reciprocal, Jacobian, grid and
phase score; ``complex64`` for the zoom-DFT GEMM AND its left-to-right
association ``(ey @ g) @ ex.T``; the two independent parabola helpers
(the zoom peak's clips its denominator test at 1e-12 and returns a
``float(np.clip(...))``, the phase objective's is the same expression
but guards its neighbours for ``-inf`` at the call site); ``> 0.9``
coverage for the phase objective against ``> 0.85`` for the sample;
``>= 16`` selected points; ``np.median`` for the midpoint and the mean
absolute deviation for the spread, floored at 1e-6; the ``[-8, 8]`` LLR
clip, the ``* 2.0`` before it and the ``-tanh(llr / 2)`` after it; the
globally phased ``[::4, ::4]`` support estimator and its float64
integral image; and the layout sort key
``(-support_estimate, origin_y, origin_x)``.

**THE BATCHED PHASE GRID: BUILT, PROVED, MEASURED, DELETED**
(2026-08-17; H4-PLAN's banked card 2, un-banked and REFUTED).  A twin of
:func:`_fit_phase`'s 8x8 grid — the 128 ``map_coordinates`` stacked into
two — was built behind a switch, proved bit-identical against this arm
(84 real fits, 156 objectives compared at the interpolated planes, the
score matrix, the phase answer and the whole ``WindowFit``; six
injections bite), and then deleted from this module because it does not
pay.  The arm survives as a SOURCE RECONSTRUCTION in
``holo2/measure/fit_phase_equivalence.py``, which is where its evidence,
its faults and the numbers below live.

Measured: kernel 7.27 -> 6.82 ms (1.07x); gen-clean serial 115 s OFF vs
116 s ON, W4 51 vs 48 s, all VERIFIED byte-identical with the anchor's
integers.  **The mechanism is the stride two lines below**: ``stride =
round(max(cells) / 40)`` holds the grid at ~40x40 for ANY window, so
each of the 128 calls carries ~1,600 points — far past where scipy's
per-call setup matters.  Batching pays only at N <= 400 (1.28x) and
N ~ 100 (1.61x), and ``min_window_cells`` is 70 (stride 2, N=1,225), so
that regime is unreachable BY CONSTRUCTION.  Do not re-open this without
changing the stride law first; the share was re-priced at 3.9% of the
serial wall, and 1.07x of it is 0.3 s.

What did not batch, and why it is the durable half of the finding: each
hypothesis scores only the sites its own phase put under
``coverage > 0.9``, so the subsets are variable-length and each needs
its own compressed ``np.mean`` — numpy's pairwise sum blocks by length,
and equal lengths are what make equal answers.  :func:`sample_segment`
next door reads ONE pose, not a grid, so there was never anything to
stack there either.

NOT PORTED from geometry.py:

* ``RegionContext.lattice_f`` — the mutable seed, replaced by the
  explicit parameter/return above (R5).

Nothing else in geometry.py is elided: the module is ported whole.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage

from ..capture import Raster, SupportMask
from .place_model import (AffinePose, PlacementConfig, PoseSegment,
                          PoseWindow, admission_datum)


def _carried_int(name: str) -> int:
    """One carried OR-9 row as an int — the table is the constant's home."""
    datum = admission_datum(name)
    if datum.origin != "carried" or not isinstance(datum.value, int):
        raise TypeError(f"admission datum {name!r} is not a carried integer")
    return int(datum.value)


#: One level of four corner retries, at most once per window
#: (geometry.py:572, a bare literal in v1).
SUBDIVISION_MAX_DEPTH = _carried_int("subdivision_max_depth")
#: The smallest corner retry E022 fits; also ``PlacementConfig``'s default,
#: which is the knob :func:`subdivide_pose_window` actually reads.
MIN_WINDOW_CELLS = _carried_int("min_window_cells")


# ------------------------------------------------------------- the types

@dataclass(frozen=True, slots=True)
class LatticeSeed:
    """A region's fitted reciprocal fundamentals — R5's durable fact.

    Rows are the normalized (vertical, horizontal) cell fundamentals in
    cycles per pixel, flattened row-major, which is exactly the shape v1
    froze into a parked row (``ParkedWindowFacts.lattice_f``, four floats,
    rebuilt with ``np.asarray(seed, np.float64).reshape(2, 2)``).  The
    round trip through Python floats is lossless, so a seeded fit is
    bit-identical whether the seed came from memory or from a record.
    """

    rows: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if len(self.rows) != 4 or not all(
                math.isfinite(float(value)) for value in self.rows):
            raise ValueError("a lattice seed is four finite reciprocal terms")

    @classmethod
    def from_matrix(cls, frequencies: np.ndarray) -> "LatticeSeed":
        rows = np.asarray(frequencies, np.float64).reshape(2, 2)
        return cls((float(rows[0, 0]), float(rows[0, 1]),
                    float(rows[1, 0]), float(rows[1, 1])))

    def matrix(self) -> np.ndarray:
        """The 2x2 reciprocal matrix a fit consumes as a prior."""
        return np.asarray(self.rows, np.float64).reshape(2, 2)


@dataclass(frozen=True, slots=True)
class PreparedRegion:
    """One region's materialized pixels and its single aperture read.

    ``image`` is the region's native-luma crop with every UNSUPPORTED
    pixel filled to the platen backing, and ``filtered`` is that image
    under exactly one box aperture: all phase and payload-site reads
    address ``filtered``, and no rotated or decimated working raster is
    ever built.  ``support`` is the same mask as float32, so the sampler
    can read a coverage fraction through the same interpolator as the
    pixels.  ``y0``/``x0`` place the crop in native capture coordinates.
    """

    region_index: int
    y0: int
    x0: int
    image: np.ndarray
    filtered: np.ndarray
    support: np.ndarray
    backing: float
    pitch_prior: float
    aperture_px: int


@dataclass(frozen=True, slots=True)
class SegmentSample:
    """One window's cell-centre read through one fitted pose."""

    segment: PoseSegment
    means: np.ndarray
    mask: np.ndarray
    bits: np.ndarray
    evidence: np.ndarray
    midpoint: float


@dataclass(frozen=True, slots=True)
class AddressPatch:
    """One E022 address window and its independently fitted pose."""

    sample: SegmentSample
    mask: np.ndarray

    def __post_init__(self) -> None:
        mask = np.asarray(self.mask, bool)
        if mask.shape != self.sample.mask.shape:
            raise ValueError("address mask must match the sampled window")
        object.__setattr__(self, "mask", mask)

    @property
    def region_index(self) -> int:
        return self.sample.segment.window.region_index

    @property
    def shape_yx(self) -> tuple[int, int]:
        shape = self.sample.mask.shape
        return (int(shape[0]), int(shape[1]))

    @property
    def means(self) -> np.ndarray:
        return self.sample.means

    @property
    def bits(self) -> np.ndarray:
        return self.sample.bits

    @property
    def evidence(self) -> np.ndarray:
        return self.sample.evidence

    @property
    def frame_pose(self) -> AffinePose:
        return self.sample.segment.pose

    @property
    def depth(self) -> int:
        return self.sample.segment.window.depth


@dataclass(frozen=True, slots=True)
class WindowFit:
    """What one window's fit produced: a pose or a refusal, and the seed.

    ``lattice_seed`` is the region seed AFTER this fit: the one passed in
    when there was one, the freshly fitted fundamentals when there was
    not, and ``None`` when nothing cleared the geometric gates.  It is
    populated even when ``segment`` is ``None``, because a geometrically
    sound window whose phase objective is inconclusive remains useful to
    a smaller edge window — v1 seeds before fitting phase for exactly
    that reason (geometry.py:427-432).

    ``unconditioned_seed`` is the fundamentals THIS window measured
    without reading the incoming seed — the blind spectral fit, or the
    zoom-refit around the DECLARED axis-aligned pitch when there was no
    seed to refit around.  It is ``None`` exactly when the fit consulted
    the seed (the small-window arm, and the zoom-refit that used the
    seed as its prior), because a seeded fit measures the seed back and
    re-proposing it would be circular.  W1's provider is its consumer:
    R5 ranks unconditioned measurements by their window's support, which
    is what makes the durable seed order-independent (H4-PLAN R5,
    ``solve/lattice_seed.py``).  Nothing about the pose or the returned
    ``lattice_seed`` changes with it — it is a REPORTED fact about which
    arm produced the fit, not a new decision.
    """

    segment: PoseSegment | None
    lattice_seed: LatticeSeed | None
    unconditioned_seed: LatticeSeed | None = None


# ------------------------------------------------------ region materialization

def platen_backing(raster: Raster, border_px: int = 32) -> float:
    """Median native luma at the four platen borders, mmap-safe."""
    height, width = raster.shape
    border = max(1, min(int(border_px), height, width))
    strips = (
        raster.crop_luma(0, border, 0, width).ravel(),
        raster.crop_luma(height - border, height, 0, width).ravel(),
        raster.crop_luma(0, height, 0, border).ravel(),
        raster.crop_luma(0, height, width - border, width).ravel(),
    )
    return float(np.median(np.concatenate(strips)))


def prepare_region(
    raster: Raster,
    support_mask: SupportMask,
    region_index: int,
    pitch_px: float,
    *,
    config: PlacementConfig,
    backing: float,
) -> PreparedRegion | None:
    """Materialize one support bbox and apply its sole box prefilter."""
    if not np.isfinite(pitch_px) or pitch_px <= 0:
        raise ValueError("pitch_px must be finite and positive")
    y0, x0, height, width = support_mask.bbox
    y1 = min(raster.shape[0], y0 + height)
    x1 = min(raster.shape[1], x0 + width)
    if y1 <= y0 or x1 <= x0:
        return None
    crop = raster.crop_luma(y0, y1, x0, x1)
    support = support_mask.rasterize_crop(y0, y1, x0, x1)
    if not support.any():
        return None
    filled = np.where(support, crop, np.float32(backing)).astype(
        np.float32, copy=False
    )
    aperture = max(1, int(round(config.aperture_cells * pitch_px)))
    # Exactly one aperture operation per region.  All phase and payload-site
    # reads below address this array; no rotated/decimated working raster.
    filtered = np.asarray(
        ndimage.uniform_filter(filled, size=aperture, mode="nearest"))
    return PreparedRegion(
        region_index, int(y0), int(x0), filled, filtered,
        support.astype(np.float32), float(backing), float(pitch_px),
        aperture,
    )


# --------------------------------------------------------- the lattice fit

def _zoom_peak(
    gradient: np.ndarray,
    frequency_yx: np.ndarray,
    *,
    span_bins: float = 1.5,
    grid: int = 13,
) -> tuple[np.ndarray, float]:
    """E022-v2 local DTFT peak with parabolic sub-grid refinement."""
    height, width = gradient.shape
    ys = np.arange(height, dtype=np.float64)
    xs = np.arange(width, dtype=np.float64)
    fy = frequency_yx[0] + np.linspace(-span_bins, span_bins, grid) / height
    fx = frequency_yx[1] + np.linspace(-span_bins, span_bins, grid) / width
    ey = np.exp(-2j * np.pi * np.outer(fy, ys)).astype(np.complex64)
    ex = np.exp(-2j * np.pi * np.outer(fx, xs)).astype(np.complex64)
    response = np.abs(ey @ gradient.astype(np.complex64) @ ex.T)
    iy, ix = np.unravel_index(int(np.argmax(response)), response.shape)

    def parabola(before: float, centre: float, after: float) -> float:
        denominator = before - 2.0 * centre + after
        if abs(denominator) < 1e-12:
            return 0.0
        return float(np.clip(
            0.5 * (before - after) / denominator, -0.5, 0.5
        ))

    dy = (
        parabola(response[iy - 1, ix], response[iy, ix], response[iy + 1, ix])
        if 0 < iy < grid - 1 else 0.0
    )
    dx = (
        parabola(response[iy, ix - 1], response[iy, ix], response[iy, ix + 1])
        if 0 < ix < grid - 1 else 0.0
    )
    sy = fy[1] - fy[0] if grid > 1 else 0.0
    sx = fx[1] - fx[0] if grid > 1 else 0.0
    return (
        np.array([fy[iy] + dy * sy, fx[ix] + dx * sx]),
        float(response[iy, ix]),
    )


def _windowed_gradient(image: np.ndarray) -> np.ndarray:
    gradient = np.hypot(*np.gradient(image.astype(np.float32)))
    gradient -= float(gradient.mean())
    wy = np.hanning(gradient.shape[0]).astype(np.float32)[:, None]
    wx = np.hanning(gradient.shape[1]).astype(np.float32)[None, :]
    result: np.ndarray = gradient * wy * wx
    return result


def _normalize_reciprocal(frequencies: np.ndarray) -> np.ndarray:
    """Order vertical/horizontal fundamentals and canonicalize signs."""
    a, b = frequencies
    vertical, horizontal = (a, b) if abs(a[0]) >= abs(a[1]) else (b, a)
    if vertical[0] < 0:
        vertical = -vertical
    if horizontal[1] < 0:
        horizontal = -horizontal
    stacked: np.ndarray = np.stack([vertical, horizontal])
    return stacked


def lattice_reciprocal(
    image: np.ndarray,
    pitch_prior: float,
    *,
    band: float = 0.22,
    prior_f: np.ndarray | None = None,
) -> np.ndarray | None:
    """Return both independently zoomed lattice fundamentals as rows.

    With ``prior_f`` the coarse FFT argmax is skipped and both peaks are
    zoom-refit locally around the given reciprocal rows — the legacy
    cheap/robust arm (paperholo pilotsearch.lattice_reciprocal) that the
    first port dropped. Measured consequence of the drop: on the
    closure-dominated c2 channel the x cell fundamental is ~8-10x weaker
    than y, the blind argmax locks development-texture/speckle decoys,
    the (correct) pitch/shear gate refuses the wrong Jacobian, and the
    refusal blocks every placement route (2026-07-30 root-cause).
    """
    gradient = _windowed_gradient(image)
    if prior_f is not None:
        rows = np.asarray(prior_f, np.float64)
        first, first_contrast = _zoom_peak(gradient, rows[0])
        second, second_contrast = _zoom_peak(gradient, rows[1])
        if first_contrast <= 0 or second_contrast <= 0:
            return None
        return _normalize_reciprocal(np.stack([first, second]))
    magnitude = np.abs(np.fft.rfft2(gradient))
    fy = np.fft.fftfreq(gradient.shape[0])[:, None]
    fx = np.fft.rfftfreq(gradient.shape[1])[None, :]
    radial = np.hypot(fy, fx)
    centre = 1.0 / pitch_prior
    eligible = (
        (radial > centre * (1.0 - band))
        & (radial < centre * (1.0 + band))
    )
    if not eligible.any():
        return None
    first_map = np.where(eligible, magnitude, 0.0)
    iy, ix = np.unravel_index(int(np.argmax(first_map)), first_map.shape)
    if first_map[iy, ix] <= 0:
        return None
    first = np.array([float(fy[iy, 0]), float(fx[0, ix])])
    angles = np.arctan2(fy, fx)
    first_angle = float(np.arctan2(first[0], first[1]))
    distance = np.abs(
        ((angles - first_angle + np.pi / 2.0) % np.pi) - np.pi / 2.0
    )
    second_map = np.where(
        eligible & (distance > np.pi / 2.0 - np.deg2rad(20.0)),
        magnitude,
        0.0,
    )
    jy, jx = np.unravel_index(int(np.argmax(second_map)), second_map.shape)
    if second_map[jy, jx] <= 0:
        return None
    second = np.array([float(fy[jy, 0]), float(fx[0, jx])])
    first, _ = _zoom_peak(gradient, first)
    second, _ = _zoom_peak(gradient, second)
    return _normalize_reciprocal(np.stack([first, second]))


def jacobian_from_reciprocal(frequencies: np.ndarray) -> np.ndarray:
    """Cell-to-pixel Jacobian, including anisotropy and shear."""
    jacobian: np.ndarray = np.linalg.inv(np.asarray(frequencies, np.float64))
    return jacobian


def pose_metrics(jacobian: np.ndarray) -> tuple[float, float, float, float]:
    """Pitch y, pitch x, rotation and orthogonality error of a Jacobian."""
    vertical = jacobian[:, 0]
    horizontal = jacobian[:, 1]
    pitch_y = float(np.hypot(*vertical))
    pitch_x = float(np.hypot(*horizontal))
    angle = float(np.degrees(np.arctan2(horizontal[0], horizontal[1])))
    orthogonal = float(
        np.degrees(np.arctan2(vertical[0], vertical[1])) - 90.0 - angle
    )
    orthogonal = (orthogonal + 180.0) % 360.0 - 180.0
    return pitch_y, pitch_x, angle, orthogonal


def _fit_phase(
    region: PreparedRegion,
    jacobian: np.ndarray,
    window: PoseWindow,
    config: PlacementConfig,
) -> tuple[tuple[float, float], float] | None:
    """Legacy blind cell-centre contrast objective, unchanged numerically."""
    wy, wx = window.origin_yx_px
    cells_y, cells_x = window.shape_yx_cells
    stride = max(1, int(round(max(cells_y, cells_x) / 40.0)))
    gy, gx = np.meshgrid(
        np.arange(0, cells_y, stride),
        np.arange(0, cells_x, stride),
        indexing="ij",
    )
    grid = np.stack([gy.ravel(), gx.ravel()], axis=1).astype(np.float64)
    base = np.array([wy, wx], np.float64)
    py1 = min(region.filtered.shape[0],
              wy + int(round(cells_y * region.pitch_prior)))
    px1 = min(region.filtered.shape[1],
              wx + int(round(cells_x * region.pitch_prior)))
    local = region.filtered[wy:py1:4, wx:px1:4]
    local_mask = region.support[wy:py1:4, wx:px1:4] > 0.5
    if not local_mask.any():
        return None
    midpoint = float(np.median(local[local_mask]))
    offsets = np.arange(0.5, 1.5 - 1e-9, config.phase_step_cells)
    scores = np.full((offsets.size, offsets.size), -np.inf)
    # v1 spells these loop ordinals ``iy, ix`` and then REBINDS the same
    # two names to the argmax below; distinct names, same scan order.
    for row, phase_y in enumerate(offsets):
        for column, phase_x in enumerate(offsets):
            points = (grid + np.array([phase_y, phase_x])) @ jacobian.T + base
            means = ndimage.map_coordinates(
                region.filtered, points.T, order=1, cval=region.backing
            )
            coverage = ndimage.map_coordinates(
                region.support, points.T, order=1, cval=0.0
            )
            selected = coverage > 0.9
            if int(selected.sum()) >= 16:
                scores[row, column] = float(
                    np.abs(means[selected] - midpoint).mean()
                )
    iy, ix = np.unravel_index(int(np.argmax(scores)), scores.shape)
    if not np.isfinite(scores[iy, ix]):
        return None

    def parabola(before: float, centre: float, after: float) -> float:
        denominator = before - 2.0 * centre + after
        return 0.0 if abs(denominator) < 1e-12 else float(np.clip(
            0.5 * (before - after) / denominator, -0.5, 0.5
        ))

    dy = (
        parabola(scores[iy - 1, ix], scores[iy, ix], scores[iy + 1, ix])
        if 0 < iy < offsets.size - 1
        and np.isfinite(scores[iy - 1, ix])
        and np.isfinite(scores[iy + 1, ix]) else 0.0
    )
    dx = (
        parabola(scores[iy, ix - 1], scores[iy, ix], scores[iy, ix + 1])
        if 0 < ix < offsets.size - 1
        and np.isfinite(scores[iy, ix - 1])
        and np.isfinite(scores[iy, ix + 1]) else 0.0
    )
    return (
        (
            float(offsets[iy] + dy * config.phase_step_cells),
            float(offsets[ix] + dx * config.phase_step_cells),
        ),
        float(scores[iy, ix]),
    )


_Gated = tuple[np.ndarray, np.ndarray, float, float, float, float]


def fit_window_pose(
    region: PreparedRegion,
    window: PoseWindow,
    *,
    config: PlacementConfig,
    lattice_seed: LatticeSeed | None = None,
) -> WindowFit:
    """Fit a window's own full affine and sub-cell phase, or refuse.

    ``lattice_seed`` is the region's reciprocal seed, if one has been
    established; the returned :class:`WindowFit` carries the seed this
    fit established or used (see the module docstring's R5 note).
    """
    wy, wx = window.origin_yx_px
    cells_y, cells_x = window.shape_yx_cells
    prior = region.pitch_prior
    py1 = min(region.image.shape[0], wy + int(round(cells_y * prior)))
    px1 = min(region.image.shape[1], wx + int(round(cells_x * prior)))
    image = region.image[wy:py1, wx:px1]
    if min(image.shape, default=0) < 4 * prior:
        return WindowFit(None, lattice_seed)
    cap = int(config.spectral_px)
    cy = (image.shape[0] - min(image.shape[0], cap)) // 2
    cx = (image.shape[1] - min(image.shape[1], cap)) // 2
    spectral = image[cy:cy + cap, cx:cx + cap]
    seed_rows = None if lattice_seed is None else lattice_seed.matrix()

    def gated(frequencies: np.ndarray | None) -> _Gated | None:
        if frequencies is None:
            return None
        jacobian = jacobian_from_reciprocal(frequencies)
        pitch_y, pitch_x, angle, orthogonal = pose_metrics(jacobian)
        if (
            abs(pitch_y / prior - 1.0) > config.pitch_tolerance
            or abs(pitch_x / prior - 1.0) > config.pitch_tolerance
            or abs(orthogonal) > config.shear_tolerance_deg
            or float(np.linalg.det(jacobian)) <= 0.0
        ):
            return None
        return frequencies, jacobian, pitch_y, pitch_x, angle, orthogonal

    fitted: _Gated | None = None
    # Did the fit that survived consult ``lattice_seed``?  (R5 reporting;
    # no arithmetic depends on it — see ``WindowFit.unconditioned_seed``.)
    conditioned = True
    if min(spectral.shape) >= config.min_spectral_periods * prior:
        # A full-size window always measures its own lattice.  Region-level
        # inheritance is reserved for edge windows too small for a stable
        # spectrum, matching E022-v2's fold-safe policy.
        fitted = gated(lattice_reciprocal(spectral, prior))
        conditioned = False
        if fitted is None:
            # Legacy prior_f arm: when the blind strongest-peak fit fails
            # its gates (the weak-fundamental decoy regime), zoom-refit
            # around the best available prior — the region's seeded
            # reciprocal, else the declared axis-aligned spec pitch — and
            # re-apply the IDENTICAL gates. Byte-identical whenever the
            # blind fit succeeds.
            retry_prior = (
                seed_rows if seed_rows is not None
                else np.array(
                    [[1.0 / prior, 0.0], [0.0, 1.0 / prior]], np.float64)
            )
            conditioned = seed_rows is not None
            fitted = gated(lattice_reciprocal(
                spectral, prior, prior_f=retry_prior))
    else:
        fitted = gated(seed_rows)
    if fitted is None:
        return WindowFit(None, lattice_seed)
    frequencies, jacobian, pitch_y, pitch_x, angle, orthogonal = fitted
    measured = (None if conditioned
                else LatticeSeed.from_matrix(frequencies))
    # Establish the seed only after the lattice passes every geometric
    # gate, and BEFORE phase fitting, as in the qualified E022 chain: a
    # geometrically sound window remains useful to a smaller edge window
    # even if its own phase objective is inconclusive.  A region that
    # already has a seed keeps it (v1: first fit wins; R5: best-supported
    # window wins, which is the caller's choice, not this function's).
    seed = (lattice_seed if lattice_seed is not None
            else LatticeSeed.from_matrix(frequencies))
    phase = _fit_phase(region, jacobian, window, config)
    if phase is None:
        return WindowFit(None, seed, measured)
    phase_yx, contrast = phase
    origin = (
        np.array([region.y0 + wy, region.x0 + wx], np.float64)
        + jacobian @ np.asarray(phase_yx)
    )
    pose = AffinePose(
        (float(origin[0]), float(origin[1])),
        (
            (float(jacobian[0, 0]), float(jacobian[0, 1])),
            (float(jacobian[1, 0]), float(jacobian[1, 1])),
        ),
        phase_yx,
        float(0.5 * (pitch_y + pitch_x)),
        angle,
    )
    return WindowFit(
        PoseSegment(window, pose, 0, contrast, (pitch_y, pitch_x), orthogonal),
        seed, measured,
    )


# ---------------------------------------------------------- the cell read

def median_radiometrics(
    means: np.ndarray, mask: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    """Exact E022 median detector and bounded evidence convention."""
    selected = np.asarray(mask, bool)
    midpoint = float(np.median(np.asarray(means)[selected]))
    spread = max(
        float(np.abs(np.asarray(means)[selected] - midpoint).mean()), 1e-6
    )
    llr = np.clip((midpoint - means) / spread, -8.0, 8.0) * 2.0
    evidence = -np.tanh(llr / 2.0).astype(np.float32)
    evidence[~selected] = 0.0
    return midpoint, (means < midpoint).astype(np.uint8), evidence


def sample_segment(
    region: PreparedRegion,
    segment: PoseSegment,
) -> SegmentSample | None:
    """One order-1 cell-centre read through one local affine pose."""
    cells_y, cells_x = segment.window.shape_yx_cells
    gy, gx = np.meshgrid(np.arange(cells_y), np.arange(cells_x), indexing="ij")
    grid = np.stack([gy.ravel(), gx.ravel()], axis=1).astype(np.float64)
    local_origin = (
        np.asarray(segment.pose.origin_yx)
        - np.array([region.y0, region.x0], np.float64)
    )
    points = grid @ segment.pose.matrix().T + local_origin
    means = ndimage.map_coordinates(
        region.filtered, points.T, order=1, cval=region.backing
    ).reshape(cells_y, cells_x)
    coverage = ndimage.map_coordinates(
        region.support, points.T, order=1, cval=0.0
    ).reshape(cells_y, cells_x)
    mask = coverage > 0.85
    if not mask.any():
        return None
    midpoint, bits, evidence = median_radiometrics(means, mask)
    fitted = replace(segment, support_cells=int(mask.sum()))
    return SegmentSample(
        fitted, means.astype(np.float32, copy=False), mask,
        bits, evidence, midpoint,
    )


def make_address_patch(
    sample: SegmentSample,
    mask: np.ndarray | None = None,
) -> AddressPatch:
    """Wrap one sampled E022 window without changing its radiometrics."""
    return AddressPatch(sample, sample.mask if mask is None else mask)


def refresh_address_patch(
    patch: AddressPatch,
    sample: SegmentSample,
    mask: np.ndarray | None = None,
) -> AddressPatch:
    """Replace one refined window sample without altering its identity."""
    if sample.segment.window != patch.sample.segment.window:
        raise ValueError("refreshed patch changed its observation window")
    return make_address_patch(sample, mask)


# ------------------------------------------------------- window geometry
#
# `layout_pose_windows` — v1's pixel-frame window layout — was DELETED
# here (user ruling 2026-08-17). Production's lattice is
# `geometry.window_starts` / `plans.window_plans_for` in the cell frame;
# the carried function's outputs survive as pinned literals in
# `tests/solve/test_geometry.py`, frozen from it before the deletion.

def subdivision_child_extents(
    extent_cells: tuple[int, int, int, int],
    *,
    depth: int,
    config: PlacementConfig,
) -> tuple[tuple[int, int, int, int], ...]:
    """E022's four corner retries as CELL extents — the pixel-free half.

    Split out of :func:`subdivide_pose_window` at W3 so the pull
    scheduler can ask what a window's children WOULD be without holding a
    prepared region: a window is named by its extent in the capture-cell
    frame (``plans.WindowPlan``), the scheduler owns no pixels (DESIGN
    §6.8), and the corner geometry was never pixel arithmetic in the
    first place — v1 computes the offsets in CELLS and multiplies by the
    pitch only to name a pixel origin.

    The arithmetic is unchanged and stays v1's: at most one level
    (:data:`SUBDIVISION_MAX_DEPTH`), a square side of
    ``max(min_window_cells, min(h, w) // 2)``, a refusal when that side
    cannot actually shrink the window, and the four corners in v1's own
    order (top-left, top-right, bottom-left, bottom-right). Children
    OVERLAP in the middle whenever the floor raises the side above the
    half — which is v1's behaviour and not a defect: the floor is the
    smallest window E022 fits, so a corner retry never goes under it.
    """
    if not config.subdivide or depth >= SUBDIVISION_MAX_DEPTH:
        return ()
    cy0, cx0, cy1, cx1 = extent_cells
    height, width = cy1 - cy0, cx1 - cx0
    side = max(config.min_window_cells, min(height, width) // 2)
    if side >= min(height, width):
        return ()
    return tuple(
        (cy0 + offset_y, cx0 + offset_x,
         cy0 + offset_y + side, cx0 + offset_x + side)
        for offset_y, offset_x in (
            (0, 0), (0, width - side),
            (height - side, 0), (height - side, width - side),
        )
    )


def subdivide_pose_window(
    window: PoseWindow,
    region: PreparedRegion,
    *,
    config: PlacementConfig,
    first_window_id: int,
) -> tuple[PoseWindow, ...]:
    """Return E022's four freshly fitted corner retries, at most once."""
    height, width = window.shape_yx_cells
    pitch = region.pitch_prior
    return tuple(
        PoseWindow(
            first_window_id + index,
            window.region_index,
            (
                int(window.origin_yx_px[0] + round(offset_y * pitch)),
                int(window.origin_yx_px[1] + round(offset_x * pitch)),
            ),
            (child_y1 - offset_y, child_x1 - offset_x),
            window.depth + 1,
            0,
        )
        for index, (offset_y, offset_x, child_y1, child_x1)
        in enumerate(subdivision_child_extents(
            (0, 0, height, width), depth=window.depth, config=config))
    )


__all__ = [
    "MIN_WINDOW_CELLS", "SUBDIVISION_MAX_DEPTH", "AddressPatch",
    "LatticeSeed", "PreparedRegion", "SegmentSample", "WindowFit",
    "fit_window_pose", "jacobian_from_reciprocal", "lattice_reciprocal",
    "make_address_patch", "median_radiometrics",
    "platen_backing", "pose_metrics", "prepare_region",
    "refresh_address_patch", "sample_segment", "subdivide_pose_window",
    "subdivision_child_extents",
]

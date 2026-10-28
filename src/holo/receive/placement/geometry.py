"""E022 native affine observation windows.

The numerical primitives are ingested from ``paperholo.pilotsearch`` E022
v2: gradient-spectrum fundamentals, zoom-DFT sub-bin peaks, full affine
Jacobian, phase objective, one 0.7-cell box aperture, and one order-1 read
per cell centre.  Window layout, subdivision, and per-window radiometrics
retain the measured 200/40 E022 policy.  Production uses no characterization
instrument as an algorithmic or numerical dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage

from ..scan import Raster
from ..survey import SurveyRegion
from .model import (
    AffinePose,
    HISTORICAL_MIN_SUPPORT,
    PlacementConfig,
    PoseSegment,
    PoseWindow,
)


@dataclass(slots=True)
class RegionContext:
    region_index: int
    y0: int
    x0: int
    crop: np.ndarray
    filtered: np.ndarray
    support: np.ndarray
    backing: float
    pitch_prior: float
    aperture_px: int
    lattice_f: np.ndarray | None = None


@dataclass(slots=True)
class SegmentSample:
    segment: PoseSegment
    means: np.ndarray
    mask: np.ndarray
    bits: np.ndarray
    evidence: np.ndarray
    midpoint: float


@dataclass(slots=True)
class AddressPatch:
    """One E022 address window and its independently fitted pose."""

    sample: SegmentSample
    mask: np.ndarray

    def __post_init__(self) -> None:
        mask = np.asarray(self.mask, bool)
        if mask.shape != self.sample.mask.shape:
            raise ValueError("address mask must match the sampled window")
        self.mask = mask

    @property
    def region_index(self) -> int:
        return self.sample.segment.window.region_index

    @property
    def shape_yx(self) -> tuple[int, int]:
        return tuple(int(value) for value in self.sample.mask.shape)

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


def _median_radiometrics(
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
    region: SurveyRegion,
    region_index: int,
    pitch_px: float,
    *,
    config: PlacementConfig,
    backing: float,
) -> RegionContext | None:
    """Materialize one support bbox and apply its sole box prefilter."""
    if not np.isfinite(pitch_px) or pitch_px <= 0:
        raise ValueError("pitch_px must be finite and positive")
    y0, x0, height, width = region.bbox
    y1 = min(raster.shape[0], y0 + height)
    x1 = min(raster.shape[1], x0 + width)
    if y1 <= y0 or x1 <= x0:
        return None
    crop = raster.crop_luma(y0, y1, x0, x1)
    support = region.support.rasterize_crop(y0, y1, x0, x1)
    if not support.any():
        return None
    filled = np.where(support, crop, np.float32(backing)).astype(
        np.float32, copy=False
    )
    aperture = max(1, int(round(config.aperture_cells * pitch_px)))
    # Exactly one aperture operation per region.  All phase and payload-site
    # reads below address this array; no rotated/decimated working raster.
    filtered = ndimage.uniform_filter(filled, size=aperture, mode="nearest")
    return RegionContext(
        region_index, int(y0), int(x0), filled, filtered,
        support.astype(np.float32), float(backing), float(pitch_px),
        aperture,
    )


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


def _windowed_gradient(crop: np.ndarray) -> np.ndarray:
    gradient = np.hypot(*np.gradient(crop.astype(np.float32)))
    gradient -= float(gradient.mean())
    wy = np.hanning(gradient.shape[0]).astype(np.float32)[:, None]
    wx = np.hanning(gradient.shape[1]).astype(np.float32)[None, :]
    return gradient * wy * wx


def _normalize_reciprocal(frequencies: np.ndarray) -> np.ndarray:
    """Order vertical/horizontal fundamentals and canonicalize signs."""
    a, b = frequencies
    vertical, horizontal = (a, b) if abs(a[0]) >= abs(a[1]) else (b, a)
    if vertical[0] < 0:
        vertical = -vertical
    if horizontal[1] < 0:
        horizontal = -horizontal
    return np.stack([vertical, horizontal])


def lattice_reciprocal(
    crop: np.ndarray,
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
    gradient = _windowed_gradient(crop)
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
    return np.linalg.inv(np.asarray(frequencies, np.float64))


def pose_metrics(jacobian: np.ndarray) -> tuple[float, float, float, float]:
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
    context: RegionContext,
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
    py1 = min(context.filtered.shape[0], wy + int(round(cells_y * context.pitch_prior)))
    px1 = min(context.filtered.shape[1], wx + int(round(cells_x * context.pitch_prior)))
    local = context.filtered[wy:py1:4, wx:px1:4]
    local_mask = context.support[wy:py1:4, wx:px1:4] > 0.5
    if not local_mask.any():
        return None
    midpoint = float(np.median(local[local_mask]))
    offsets = np.arange(0.5, 1.5 - 1e-9, config.phase_step_cells)
    scores = np.full((offsets.size, offsets.size), -np.inf)
    for iy, phase_y in enumerate(offsets):
        for ix, phase_x in enumerate(offsets):
            points = (grid + np.array([phase_y, phase_x])) @ jacobian.T + base
            means = ndimage.map_coordinates(
                context.filtered, points.T, order=1, cval=context.backing
            )
            coverage = ndimage.map_coordinates(
                context.support, points.T, order=1, cval=0.0
            )
            selected = coverage > 0.9
            if int(selected.sum()) >= 16:
                scores[iy, ix] = float(
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


def fit_window_pose(
    context: RegionContext,
    window: PoseWindow,
    *,
    config: PlacementConfig,
) -> PoseSegment | None:
    """Fit a window's own full affine and sub-cell phase, or refuse."""
    wy, wx = window.origin_yx_px
    cells_y, cells_x = window.shape_yx_cells
    prior = context.pitch_prior
    py1 = min(context.crop.shape[0], wy + int(round(cells_y * prior)))
    px1 = min(context.crop.shape[1], wx + int(round(cells_x * prior)))
    crop = context.crop[wy:py1, wx:px1]
    if min(crop.shape, default=0) < 4 * prior:
        return None
    cap = int(config.spectral_px)
    cy = (crop.shape[0] - min(crop.shape[0], cap)) // 2
    cx = (crop.shape[1] - min(crop.shape[1], cap)) // 2
    spectral = crop[cy:cy + cap, cx:cx + cap]

    def gated(frequencies: np.ndarray | None):
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

    fitted = None
    if min(spectral.shape) >= config.min_spectral_periods * prior:
        # A full-size window always measures its own lattice.  Region-level
        # inheritance is reserved for edge windows too small for a stable
        # spectrum, matching E022-v2's fold-safe policy.
        fitted = gated(lattice_reciprocal(spectral, prior))
        if fitted is None:
            # Legacy prior_f arm: when the blind strongest-peak fit fails
            # its gates (the weak-fundamental decoy regime), zoom-refit
            # around the best available prior — the region's seeded
            # reciprocal, else the declared axis-aligned spec pitch — and
            # re-apply the IDENTICAL gates. Byte-identical whenever the
            # blind fit succeeds.
            retry_prior = (
                context.lattice_f if context.lattice_f is not None
                else np.array(
                    [[1.0 / prior, 0.0], [0.0, 1.0 / prior]], np.float64)
            )
            fitted = gated(lattice_reciprocal(
                spectral, prior, prior_f=retry_prior))
    else:
        fitted = gated(context.lattice_f)
    if fitted is None:
        return None
    frequencies, jacobian, pitch_y, pitch_x, angle, orthogonal = fitted
    # Seed the fallback only after the lattice passes every geometric gate.
    # This deliberately precedes phase fitting, as in the qualified E022
    # chain: a geometrically sound window remains useful to a smaller edge
    # window even if its own phase objective is inconclusive.
    if context.lattice_f is None:
        context.lattice_f = frequencies
    phase = _fit_phase(context, jacobian, window, config)
    if phase is None:
        return None
    phase_yx, contrast = phase
    origin = (
        np.array([context.y0 + wy, context.x0 + wx], np.float64)
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
    return PoseSegment(
        window, pose, 0, contrast,
        (pitch_y, pitch_x), orthogonal,
    )


def sample_segment(
    context: RegionContext,
    segment: PoseSegment,
) -> SegmentSample | None:
    """One order-1 cell-centre read through one local affine pose."""
    cells_y, cells_x = segment.window.shape_yx_cells
    gy, gx = np.meshgrid(np.arange(cells_y), np.arange(cells_x), indexing="ij")
    grid = np.stack([gy.ravel(), gx.ravel()], axis=1).astype(np.float64)
    local_origin = (
        np.asarray(segment.pose.origin_yx)
        - np.array([context.y0, context.x0], np.float64)
    )
    points = grid @ segment.pose.matrix().T + local_origin
    means = ndimage.map_coordinates(
        context.filtered, points.T, order=1, cval=context.backing
    ).reshape(cells_y, cells_x)
    coverage = ndimage.map_coordinates(
        context.support, points.T, order=1, cval=0.0
    ).reshape(cells_y, cells_x)
    mask = coverage > 0.85
    if not mask.any():
        return None
    midpoint, bits, evidence = _median_radiometrics(means, mask)
    fitted = replace(segment, support_cells=int(mask.sum()))
    return SegmentSample(
        fitted, means.astype(np.float32, copy=False), mask,
        bits, evidence, midpoint,
    )


def layout_pose_windows(
    context: RegionContext,
    *,
    config: PlacementConfig,
) -> tuple[PoseWindow, ...]:
    """Lay out the frozen 200-cell E022 windows with 40-cell overlap."""
    pitch = context.pitch_prior
    height_px, width_px = context.crop.shape
    window_px = int(round(config.window_cells * pitch))
    step_px = max(1, int(round(
        (config.window_cells - config.overlap_cells) * pitch
    )))

    def starts(length_px: int) -> list[int]:
        if length_px <= window_px:
            return [0]
        values = list(range(0, length_px - window_px + 1, step_px))
        if values[-1] != length_px - window_px:
            values.append(length_px - window_px)
        return values

    # Estimate support on one globally phased 4x mask.  Window-relative
    # slicing would silently change the sampled phase for edge-aligned
    # windows and is not the E022-v2 estimator.
    sub = 4
    sampled = context.support[::sub, ::sub] > 0.5
    integral = np.pad(
        np.cumsum(np.cumsum(sampled, axis=0), axis=1).astype(np.float64),
        ((1, 0), (1, 0)),
    )

    def support_cells(y0: int, x0: int, y1: int, x1: int) -> int:
        a, b = y0 // sub, x0 // sub
        c = min(sampled.shape[0], y1 // sub)
        d = min(sampled.shape[1], x1 // sub)
        if c <= a or d <= b:
            return 0
        samples = float(
            integral[c, d] - integral[a, d]
            - integral[c, b] + integral[a, b]
        )
        return int(samples * sub * sub / (pitch * pitch))

    windows: list[PoseWindow] = []
    next_id = 0
    for pixel_y in starts(height_px):
        for pixel_x in starts(width_px):
            shape = (
                min(config.window_cells, int((height_px - pixel_y) / pitch)),
                min(config.window_cells, int((width_px - pixel_x) / pitch)),
            )
            if min(shape) < 8:
                continue
            pixel_y1 = min(
                height_px,
                pixel_y + int(round(shape[0] * pitch)),
            )
            pixel_x1 = min(
                width_px,
                pixel_x + int(round(shape[1] * pitch)),
            )
            support_estimate = support_cells(
                pixel_y, pixel_x, pixel_y1, pixel_x1
            )
            if support_estimate < HISTORICAL_MIN_SUPPORT:
                continue
            windows.append(PoseWindow(
                next_id, context.region_index, (pixel_y, pixel_x), shape,
                support_estimate=support_estimate,
            ))
            next_id += 1
    windows.sort(key=lambda row: (
        -row.support_estimate, row.origin_yx_px[0], row.origin_yx_px[1]
    ))
    return tuple(windows)


def subdivide_pose_window(
    window: PoseWindow,
    context: RegionContext,
    *,
    config: PlacementConfig,
    first_window_id: int,
) -> tuple[PoseWindow, ...]:
    """Return E022's four freshly fitted corner retries, at most once."""
    if not config.subdivide or window.depth >= 1:
        return ()
    height, width = window.shape_yx_cells
    side = max(config.min_window_cells, min(height, width) // 2)
    if side >= min(height, width):
        return ()
    pitch = context.pitch_prior
    output: list[PoseWindow] = []
    for index, (offset_y, offset_x) in enumerate((
        (0, 0), (0, width - side),
        (height - side, 0), (height - side, width - side),
    )):
        output.append(PoseWindow(
            first_window_id + index,
            window.region_index,
            (
                int(window.origin_yx_px[0] + round(offset_y * pitch)),
                int(window.origin_yx_px[1] + round(offset_x * pitch)),
            ),
            (side, side),
            window.depth + 1,
            0,
        ))
    return tuple(output)


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

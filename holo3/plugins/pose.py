from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage

from ..lib import geometry
from .words import ReferenceField, ReferencePage

PITCH_TOLERANCE: float = 0.06
SHEAR_TOLERANCE_DEG: float = 3.0
APERTURE_CELLS: float = 0.7
PHASE_STEP_CELLS: float = 0.125
SPECTRAL_PX: int = 2048
MIN_SPECTRAL_PERIODS: int = 12
ERODE_CELLS: int = 2
HALO_CELLS: int = 16
MIN_WINDOW_CELLS: int = 70
SUBDIVISION_MAX_DEPTH: int = 1
REFINE_ANGLE_DEG: float = 0.15
REFINE_ANGLE_STEP_DEG: float = 0.05
REFINE_PHASE_CELLS: float = 0.25
REFINE_PHASE_STEP_CELLS: float = 0.0625
REFINE_MIN_TOTAL_SITES: int = 60
REFINE_MIN_SITES_PER_PARITY: int = 20
REFINE_HELDOUT_DEGRADE: float = 0.005
AUDIT_MIN_SITES: int = 15
AUDIT_BAD: float = 0.35
AUDIT_GOOD: float = 0.20
AUDIT_POST_BAR: float = 0.25
WHOLE_WORD_PARITY: int = 2


@dataclass(frozen=True)
class Pose:
    origin_yx: tuple[float, float]
    jacobian_yx: tuple[tuple[float, float], tuple[float, float]]
    phase_yx: tuple[float, float]
    pitch_px: float
    angle_deg: float

    def matrix(self) -> np.ndarray:
        return np.asarray(self.jacobian_yx, np.float64)


@dataclass(frozen=True)
class PoseSegment:
    pose: Pose
    shape_yx_cells: tuple[int, int]
    support_cells: int
    phase_contrast: float
    pitch_yx_px: tuple[float, float]
    orthogonality_error_deg: float


@dataclass(frozen=True)
class WindowPixels:
    origin_yx: tuple[int, int]
    shape_yx_cells: tuple[int, int]
    filled: np.ndarray
    filtered: np.ndarray
    support: np.ndarray
    backing: float
    pitch_prior: float
    aperture_px: int


@dataclass(frozen=True)
class WindowFit:
    segment: PoseSegment | None
    lattice_seed: np.ndarray | None
    unconditioned_seed: np.ndarray | None = None


@dataclass(frozen=True)
class SegmentSample:
    segment: PoseSegment
    means: np.ndarray
    mask: np.ndarray
    bits: np.ndarray
    evidence: np.ndarray
    midpoint: float


@dataclass(frozen=True)
class RefineOutcome:
    sample: SegmentSample
    delta_angle_deg: float
    delta_phase_yx: tuple[float, float]
    heldout_before: float
    heldout_after: float


@dataclass(frozen=True)
class CandidateScore:
    page: int
    origin_yx: tuple[int, int]
    rot_k: int
    search_mismatch: float
    validation_mismatch: float
    search_errors: int
    validation_errors: int
    search_support: int
    validation_support: int
    soft_z: float
    passes: bool
    route: str


@dataclass(frozen=True)
class SearchOutcome:
    accepted: bool
    best: CandidateScore | None
    runner_ups: tuple[CandidateScore, ...]
    hypotheses: int
    reason: str


def rotation_affine(rot_k: int,
                    shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    height, width = shape
    rot_k = int(rot_k) % 4
    if rot_k == 0:
        return np.eye(2), np.zeros(2)
    if rot_k == 1:
        return (np.array([[0.0, -1.0], [1.0, 0.0]]),
                np.array([width - 1.0, 0.0]))
    if rot_k == 2:
        return -np.eye(2), np.array([height - 1.0, width - 1.0])
    return (np.array([[0.0, 1.0], [-1.0, 0.0]]),
            np.array([0.0, height - 1.0]))


def overlap_slices(
    origin_yx: tuple[int, int],
    fragment_shape: tuple[int, int],
    page_shape: tuple[int, int],
) -> tuple[slice, slice, slice, slice] | None:
    origin_y, origin_x = origin_yx
    height, width = page_shape
    frag_height, frag_width = fragment_shape
    page_y0, page_x0 = max(0, origin_y), max(0, origin_x)
    page_y1 = min(height, origin_y + frag_height)
    page_x1 = min(width, origin_x + frag_width)
    if page_y0 >= page_y1 or page_x0 >= page_x1:
        return None
    return (slice(page_y0, page_y1), slice(page_x0, page_x1),
            slice(page_y0 - origin_y, page_y1 - origin_y),
            slice(page_x0 - origin_x, page_x1 - origin_x))


def parity_mask(shape: tuple[int, int], origin_yx: tuple[int, int],
                parity: int) -> np.ndarray:
    height, width = shape
    y0, x0 = origin_yx
    yy = y0 + np.arange(height, dtype=np.int64)[:, None]
    xx = x0 + np.arange(width, dtype=np.int64)[None, :]
    mask: np.ndarray = geometry.site_parity(yy, xx) == int(parity)
    return mask


def _site_parity(absolute_yx: np.ndarray) -> np.ndarray:
    return geometry.site_parity(
        absolute_yx[:, 0], absolute_yx[:, 1]).astype(bool)


def rival_gate(best_mismatch: float, rival_mismatch: float,
               rival_decoy: float, minimum_gap: float) -> bool:
    return (rival_mismatch > rival_decoy
            and rival_mismatch - best_mismatch >= minimum_gap)


class ScoreMemo:
    def __init__(self, provider: ReferenceField) -> None:
        self.provider = provider
        self._scores: dict[tuple[int, int, int, int, int],
                           tuple[float, int, int, float]] = {}

    def parity_score(
        self,
        evidence: np.ndarray,
        bits: np.ndarray,
        mask: np.ndarray,
        page: int,
        origin_yx: tuple[int, int],
        rot_k: int,
        parity: int,
    ) -> tuple[float, int, int, float]:
        key = (int(page), int(origin_yx[0]), int(origin_yx[1]),
               int(rot_k) % 4, int(parity))
        cached = self._scores.get(key)
        if cached is not None:
            return cached
        reference: ReferencePage = self.provider.page(page)
        observed = np.rot90(np.asarray(evidence, np.float32), rot_k)
        hard = np.rot90(np.asarray(bits, np.uint8), rot_k)
        keep = np.rot90(np.asarray(mask, bool), rot_k)
        slices = overlap_slices(
            origin_yx, observed.shape, reference.values.shape)
        if slices is None:
            result = (1.0, 0, 0, -np.inf)
            self._scores[key] = result
            return result
        page_y, page_x, frag_y, frag_x = slices
        selected = reference.sites[page_y, page_x] & keep[frag_y, frag_x]
        if parity != WHOLE_WORD_PARITY:
            selected &= parity_mask(
                selected.shape,
                (int(page_y.start or 0), int(page_x.start or 0)), parity)
        support = int(selected.sum())
        if support == 0:
            result = (1.0, 0, 0, -np.inf)
            self._scores[key] = result
            return result
        expected_bits = reference.values[page_y, page_x][selected]
        observed_evidence = observed[frag_y, frag_x][selected]
        expected_sign = 1.0 - 2.0 * expected_bits.astype(np.float32)
        weights = np.abs(observed_evidence)
        correlation = float(np.sum(expected_sign * observed_evidence))
        total_weight = float(weights.sum())
        mismatch = ((total_weight - correlation) / (2.0 * total_weight)
                    if total_weight > 0.0 else 1.0)
        observed_bits = hard[frag_y, frag_x][selected]
        errors = int(np.count_nonzero(observed_bits != expected_bits))
        z = correlation / np.sqrt(max(total_weight, 1e-9))
        result = (float(mismatch), errors, support, float(z))
        self._scores[key] = result
        return result

    def candidate(
        self,
        evidence: np.ndarray,
        bits: np.ndarray,
        mask: np.ndarray,
        page: int,
        origin_yx: tuple[int, int],
        rot_k: int,
        min_support: int,
        search_true: float,
        validation_true: float,
        route: str,
    ) -> CandidateScore:
        search = self.parity_score(
            evidence, bits, mask, page, origin_yx, rot_k, 0)
        validation = self.parity_score(
            evidence, bits, mask, page, origin_yx, rot_k, 1)
        passes = (search[2] >= min_support
                  and validation[2] >= min_support
                  and search[0] < search_true
                  and validation[0] < validation_true)
        return CandidateScore(
            int(page), (int(origin_yx[0]), int(origin_yx[1])),
            int(rot_k) % 4,
            search[0], validation[0], search[1], validation[1],
            search[2], validation[2], search[3], passes, route)


def window_pixels(
    luma: np.ndarray,
    support: np.ndarray,
    origin_yx: tuple[int, int],
    shape_yx_cells: tuple[int, int],
    pitch_prior: float,
    backing: float,
) -> WindowPixels | None:
    mask = np.asarray(support, bool)
    if not mask.any():
        return None
    filled = np.where(mask, luma, np.float32(backing)).astype(
        np.float32, copy=False)
    aperture = max(1, int(round(APERTURE_CELLS * pitch_prior)))
    filtered = np.asarray(
        ndimage.uniform_filter(filled, size=aperture, mode="nearest"))
    return WindowPixels(
        (int(origin_yx[0]), int(origin_yx[1])),
        (int(shape_yx_cells[0]), int(shape_yx_cells[1])),
        filled, filtered, mask.astype(np.float32), float(backing),
        float(pitch_prior), aperture)


def _zoom_peak(gradient: np.ndarray, frequency_yx: np.ndarray,
               span_bins: float = 1.5,
               grid: int = 13) -> tuple[np.ndarray, float]:
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
        return float(np.clip(0.5 * (before - after) / denominator, -0.5, 0.5))

    dy = (parabola(response[iy - 1, ix], response[iy, ix],
                   response[iy + 1, ix])
          if 0 < iy < grid - 1 else 0.0)
    dx = (parabola(response[iy, ix - 1], response[iy, ix],
                   response[iy, ix + 1])
          if 0 < ix < grid - 1 else 0.0)
    sy = fy[1] - fy[0] if grid > 1 else 0.0
    sx = fx[1] - fx[0] if grid > 1 else 0.0
    return (np.array([fy[iy] + dy * sy, fx[ix] + dx * sx]),
            float(response[iy, ix]))


def _windowed_gradient(image: np.ndarray) -> np.ndarray:
    gradient = np.hypot(*np.gradient(image.astype(np.float32)))
    gradient -= float(gradient.mean())
    wy = np.hanning(gradient.shape[0]).astype(np.float32)[:, None]
    wx = np.hanning(gradient.shape[1]).astype(np.float32)[None, :]
    result: np.ndarray = gradient * wy * wx
    return result


def _normalize_reciprocal(frequencies: np.ndarray) -> np.ndarray:
    a, b = frequencies
    vertical, horizontal = (a, b) if abs(a[0]) >= abs(a[1]) else (b, a)
    if vertical[0] < 0:
        vertical = -vertical
    if horizontal[1] < 0:
        horizontal = -horizontal
    stacked: np.ndarray = np.stack([vertical, horizontal])
    return stacked


def lattice_reciprocal(image: np.ndarray, pitch_prior: float,
                       band: float = 0.22,
                       prior_f: np.ndarray | None = None,
                       ) -> np.ndarray | None:
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
    eligible = ((radial > centre * (1.0 - band))
                & (radial < centre * (1.0 + band)))
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
        ((angles - first_angle + np.pi / 2.0) % np.pi) - np.pi / 2.0)
    second_map = np.where(
        eligible & (distance > np.pi / 2.0 - np.deg2rad(20.0)),
        magnitude, 0.0)
    jy, jx = np.unravel_index(int(np.argmax(second_map)), second_map.shape)
    if second_map[jy, jx] <= 0:
        return None
    second = np.array([float(fy[jy, 0]), float(fx[0, jx])])
    first, _ = _zoom_peak(gradient, first)
    second, _ = _zoom_peak(gradient, second)
    return _normalize_reciprocal(np.stack([first, second]))


def jacobian_from_reciprocal(frequencies: np.ndarray) -> np.ndarray:
    jacobian: np.ndarray = np.linalg.inv(np.asarray(frequencies, np.float64))
    return jacobian


def pose_metrics(jacobian: np.ndarray) -> tuple[float, float, float, float]:
    vertical = jacobian[:, 0]
    horizontal = jacobian[:, 1]
    pitch_y = float(np.hypot(*vertical))
    pitch_x = float(np.hypot(*horizontal))
    angle = float(np.degrees(np.arctan2(horizontal[0], horizontal[1])))
    orthogonal = float(
        np.degrees(np.arctan2(vertical[0], vertical[1])) - 90.0 - angle)
    orthogonal = (orthogonal + 180.0) % 360.0 - 180.0
    return pitch_y, pitch_x, angle, orthogonal


def _fit_phase(pixels: WindowPixels, jacobian: np.ndarray,
               ) -> tuple[tuple[float, float], float] | None:
    wy, wx = pixels.origin_yx
    cells_y, cells_x = pixels.shape_yx_cells
    stride = max(1, int(round(max(cells_y, cells_x) / 40.0)))
    gy, gx = np.meshgrid(
        np.arange(0, cells_y, stride),
        np.arange(0, cells_x, stride),
        indexing="ij")
    grid = np.stack([gy.ravel(), gx.ravel()], axis=1).astype(np.float64)
    base = np.array([wy, wx], np.float64)
    py1 = min(pixels.filtered.shape[0],
              wy + int(round(cells_y * pixels.pitch_prior)))
    px1 = min(pixels.filtered.shape[1],
              wx + int(round(cells_x * pixels.pitch_prior)))
    local = pixels.filtered[wy:py1:4, wx:px1:4]
    local_mask = pixels.support[wy:py1:4, wx:px1:4] > 0.5
    if not local_mask.any():
        return None
    midpoint = float(np.median(local[local_mask]))
    offsets = np.arange(0.5, 1.5 - 1e-9, PHASE_STEP_CELLS)
    scores = np.full((offsets.size, offsets.size), -np.inf)
    for row, phase_y in enumerate(offsets):
        for column, phase_x in enumerate(offsets):
            points = (grid + np.array([phase_y, phase_x])) @ jacobian.T + base
            means = ndimage.map_coordinates(
                pixels.filtered, points.T, order=1, cval=pixels.backing)
            coverage = ndimage.map_coordinates(
                pixels.support, points.T, order=1, cval=0.0)
            selected = coverage > 0.9
            if int(selected.sum()) >= 16:
                scores[row, column] = float(
                    np.abs(means[selected] - midpoint).mean())
    iy, ix = np.unravel_index(int(np.argmax(scores)), scores.shape)
    if not np.isfinite(scores[iy, ix]):
        return None

    def parabola(before: float, centre: float, after: float) -> float:
        denominator = before - 2.0 * centre + after
        return 0.0 if abs(denominator) < 1e-12 else float(np.clip(
            0.5 * (before - after) / denominator, -0.5, 0.5))

    dy = (parabola(scores[iy - 1, ix], scores[iy, ix], scores[iy + 1, ix])
          if 0 < iy < offsets.size - 1
          and np.isfinite(scores[iy - 1, ix])
          and np.isfinite(scores[iy + 1, ix]) else 0.0)
    dx = (parabola(scores[iy, ix - 1], scores[iy, ix], scores[iy, ix + 1])
          if 0 < ix < offsets.size - 1
          and np.isfinite(scores[iy, ix - 1])
          and np.isfinite(scores[iy, ix + 1]) else 0.0)
    return ((float(offsets[iy] + dy * PHASE_STEP_CELLS),
             float(offsets[ix] + dx * PHASE_STEP_CELLS)),
            float(scores[iy, ix]))


_Gated = tuple[np.ndarray, np.ndarray, float, float, float, float]


def fit_window_pose(pixels: WindowPixels,
                    lattice_seed: np.ndarray | None = None) -> WindowFit:
    wy, wx = pixels.origin_yx
    cells_y, cells_x = pixels.shape_yx_cells
    prior = pixels.pitch_prior
    py1 = min(pixels.filled.shape[0], wy + int(round(cells_y * prior)))
    px1 = min(pixels.filled.shape[1], wx + int(round(cells_x * prior)))
    image = pixels.filled[wy:py1, wx:px1]
    if min(image.shape, default=0) < 4 * prior:
        return WindowFit(None, lattice_seed)
    cap = SPECTRAL_PX
    cy = (image.shape[0] - min(image.shape[0], cap)) // 2
    cx = (image.shape[1] - min(image.shape[1], cap)) // 2
    spectral = image[cy:cy + cap, cx:cx + cap]
    seed_rows = (None if lattice_seed is None
                 else np.asarray(lattice_seed, np.float64).reshape(2, 2))

    def gated(frequencies: np.ndarray | None) -> _Gated | None:
        if frequencies is None:
            return None
        jacobian = jacobian_from_reciprocal(frequencies)
        pitch_y, pitch_x, angle, orthogonal = pose_metrics(jacobian)
        if (abs(pitch_y / prior - 1.0) > PITCH_TOLERANCE
                or abs(pitch_x / prior - 1.0) > PITCH_TOLERANCE
                or abs(orthogonal) > SHEAR_TOLERANCE_DEG
                or float(np.linalg.det(jacobian)) <= 0.0):
            return None
        return frequencies, jacobian, pitch_y, pitch_x, angle, orthogonal

    fitted: _Gated | None = None
    conditioned = True
    if min(spectral.shape) >= MIN_SPECTRAL_PERIODS * prior:
        fitted = gated(lattice_reciprocal(spectral, prior))
        conditioned = False
        if fitted is None:
            retry_prior = (
                seed_rows if seed_rows is not None
                else np.array(
                    [[1.0 / prior, 0.0], [0.0, 1.0 / prior]], np.float64))
            conditioned = seed_rows is not None
            fitted = gated(lattice_reciprocal(
                spectral, prior, prior_f=retry_prior))
    else:
        fitted = gated(seed_rows)
    if fitted is None:
        return WindowFit(None, lattice_seed)
    frequencies, jacobian, pitch_y, pitch_x, angle, orthogonal = fitted
    measured = (None if conditioned
                else np.asarray(frequencies, np.float64).copy())
    seed = (lattice_seed if lattice_seed is not None
            else np.asarray(frequencies, np.float64).copy())
    phase = _fit_phase(pixels, jacobian)
    if phase is None:
        return WindowFit(None, seed, measured)
    phase_yx, contrast = phase
    origin = (np.array([wy, wx], np.float64)
              + jacobian @ np.asarray(phase_yx))
    pose = Pose(
        (float(origin[0]), float(origin[1])),
        ((float(jacobian[0, 0]), float(jacobian[0, 1])),
         (float(jacobian[1, 0]), float(jacobian[1, 1]))),
        phase_yx,
        float(0.5 * (pitch_y + pitch_x)),
        angle)
    return WindowFit(
        PoseSegment(pose, (cells_y, cells_x), 0, contrast,
                    (pitch_y, pitch_x), orthogonal),
        seed, measured)


def median_radiometrics(
    means: np.ndarray, mask: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray]:
    selected = np.asarray(mask, bool)
    midpoint = float(np.median(np.asarray(means)[selected]))
    spread = max(
        float(np.abs(np.asarray(means)[selected] - midpoint).mean()), 1e-6)
    llr = np.clip((midpoint - means) / spread, -8.0, 8.0) * 2.0
    evidence = -np.tanh(llr / 2.0).astype(np.float32)
    evidence[~selected] = 0.0
    return midpoint, (means < midpoint).astype(np.uint8), evidence


def sample_segment(pixels: WindowPixels, segment: PoseSegment,
                   offsets_px: np.ndarray | None = None,
                   ) -> SegmentSample | None:
    cells_y, cells_x = segment.shape_yx_cells
    gy, gx = np.meshgrid(np.arange(cells_y), np.arange(cells_x),
                         indexing="ij")
    grid = np.stack([gy.ravel(), gx.ravel()], axis=1).astype(np.float64)
    points = grid @ segment.pose.matrix().T + np.asarray(
        segment.pose.origin_yx, np.float64)
    if offsets_px is not None:
        points = points + np.asarray(offsets_px, np.float64)
    means = ndimage.map_coordinates(
        pixels.filtered, points.T, order=1, cval=pixels.backing,
    ).reshape(cells_y, cells_x)
    coverage = ndimage.map_coordinates(
        pixels.support, points.T, order=1, cval=0.0,
    ).reshape(cells_y, cells_x)
    mask = coverage > 0.85
    if not mask.any():
        return None
    midpoint, bits, evidence = median_radiometrics(means, mask)
    fitted = replace(segment, support_cells=int(mask.sum()))
    return SegmentSample(
        fitted, means.astype(np.float32, copy=False), mask,
        bits, evidence, midpoint)


def address_core(mask: np.ndarray,
                 erode_cells: int = ERODE_CELLS) -> np.ndarray:
    if erode_cells <= 0:
        return np.asarray(mask, bool)
    eroded = np.asarray(
        ndimage.binary_erosion(mask, iterations=erode_cells))
    return eroded if eroded.any() else np.asarray(mask, bool)


def fragment_reference_sites(
    mask: np.ndarray,
    provider: ReferenceField,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    reference: ReferencePage = provider.page(page)
    rotated_mask = np.rot90(np.asarray(mask, bool), rot_k)
    slices = overlap_slices(
        origin_yx, rotated_mask.shape, reference.values.shape)
    if slices is None:
        empty = np.zeros((0, 2), np.int64)
        return empty, np.zeros(0, np.uint8), empty
    page_y, page_x, frag_y, frag_x = slices
    selected_rotated = np.zeros(rotated_mask.shape, bool)
    selected_rotated[frag_y, frag_x] = (
        reference.sites[page_y, page_x] & rotated_mask[frag_y, frag_x])
    ry, rx = np.nonzero(selected_rotated)
    absolute = np.stack([
        ry + int(origin_yx[0]), rx + int(origin_yx[1])], axis=1)
    expected = reference.values[absolute[:, 0], absolute[:, 1]]
    index = np.full(rotated_mask.shape, -1, np.int64)
    index[ry, rx] = np.arange(ry.size)
    unrotated = np.rot90(index, -rot_k)
    local_y, local_x = np.nonzero(unrotated >= 0)
    order = unrotated[local_y, local_x]
    return (np.stack([local_y, local_x], axis=1),
            expected[order], absolute[order])


def _rotation_2x2(delta_angle_deg: float) -> np.ndarray:
    angle = np.deg2rad(delta_angle_deg)
    return np.array([
        [np.cos(angle), np.sin(angle)],
        [-np.sin(angle), np.cos(angle)]])


def _refine_grids() -> tuple[np.ndarray, np.ndarray]:
    angles = np.arange(
        -REFINE_ANGLE_DEG, REFINE_ANGLE_DEG + 1e-9, REFINE_ANGLE_STEP_DEG)
    phases = np.arange(
        -REFINE_PHASE_CELLS, REFINE_PHASE_CELLS + 1e-9,
        REFINE_PHASE_STEP_CELLS)
    return angles, phases


def _batched_refine_scan(
    pixels: WindowPixels,
    pose: Pose,
    points: np.ndarray,
    midpoint: float,
    train: np.ndarray,
    heldout: np.ndarray,
    expected: np.ndarray,
    expected_sign: np.ndarray,
    angles: np.ndarray,
    phases: np.ndarray,
) -> tuple[float, float, float, float, float]:
    jacobian0 = pose.matrix()
    origin = np.asarray(pose.origin_yx, np.float64)
    local = points.astype(np.float64)
    rotated = np.stack([
        local @ (_rotation_2x2(float(delta_angle)) @ jacobian0).T
        for delta_angle in angles])
    phase_pairs = np.stack(
        np.meshgrid(phases, phases, indexing="ij"), axis=-1).reshape(-1, 2)
    bases = np.stack([
        origin + jacobian0 @ np.array([float(delta_y), float(delta_x)])
        for delta_y, delta_x in phase_pairs])
    scan_points = rotated[:, None, :, :] + bases[None, :, None, :]
    hypotheses = angles.size * phase_pairs.shape[0]
    means = ndimage.map_coordinates(
        pixels.filtered,
        scan_points.reshape(
            hypotheses, local.shape[0], 2).transpose(2, 0, 1),
        order=1, cval=pixels.backing)
    margins = np.mean(
        (midpoint - means[:, train]) * -expected_sign[train], axis=1)
    heldout_mismatches = np.mean(
        (means[:, heldout] < midpoint) != (expected[heldout] > 0), axis=1)
    winner = 0 if np.isnan(margins[0]) else int(np.nanargmax(margins))
    angle_index, phase_index = divmod(winner, phase_pairs.shape[0])
    return (float(margins[winner]),
            float(angles[angle_index]),
            float(phase_pairs[phase_index, 0]),
            float(phase_pairs[phase_index, 1]),
            float(heldout_mismatches[winner]))


def refine_patch_pose(
    pixels: WindowPixels,
    sample: SegmentSample,
    provider: ReferenceField,
    page: int,
    patch_origin_yx: tuple[int, int],
    rot_k: int,
) -> RefineOutcome | None:
    points, expected, absolute = fragment_reference_sites(
        sample.mask, provider, page, patch_origin_yx, rot_k)
    if not expected.size:
        return None
    if expected.size < REFINE_MIN_TOTAL_SITES:
        return None
    parity = _site_parity(absolute)
    train = ~parity
    heldout = parity
    if (int(train.sum()) < REFINE_MIN_SITES_PER_PARITY
            or int(heldout.sum()) < REFINE_MIN_SITES_PER_PARITY):
        return None
    expected_sign = 1.0 - 2.0 * expected.astype(np.float64)
    midpoint = float(np.median(sample.means[sample.mask]))

    def evaluate(delta_angle_deg: float, delta_y: float,
                 delta_x: float) -> tuple[float, float]:
        rotation = _rotation_2x2(delta_angle_deg)
        pose = sample.segment.pose
        jacobian0 = pose.matrix()
        jacobian = rotation @ jacobian0
        base = (np.asarray(pose.origin_yx, np.float64)
                + jacobian0 @ np.array([delta_y, delta_x]))
        scan_points = points.astype(np.float64) @ jacobian.T + base
        means = ndimage.map_coordinates(
            pixels.filtered, scan_points.T, order=1, cval=pixels.backing)
        margin = float(np.mean(
            (midpoint - means[train]) * -expected_sign[train]))
        heldout_mismatch = float(np.mean(
            (means[heldout] < midpoint) != (expected[heldout] > 0)))
        return margin, heldout_mismatch

    _, baseline_heldout = evaluate(0.0, 0.0, 0.0)
    angles, phases = _refine_grids()
    best = _batched_refine_scan(
        pixels, sample.segment.pose, points, midpoint, train, heldout,
        expected, expected_sign, angles, phases)
    _, delta_angle_deg, delta_y, delta_x, heldout_after = best
    if heldout_after > baseline_heldout + REFINE_HELDOUT_DEGRADE:
        return None
    base_pose = sample.segment.pose
    jacobian0 = base_pose.matrix()
    jacobian = _rotation_2x2(delta_angle_deg) @ jacobian0
    origin = (np.asarray(base_pose.origin_yx, np.float64)
              + jacobian0 @ np.array([delta_y, delta_x]))
    pitch_y = float(np.hypot(*jacobian[:, 0]))
    pitch_x = float(np.hypot(*jacobian[:, 1]))
    pose_angle = float(
        np.degrees(np.arctan2(jacobian[0, 1], jacobian[1, 1])))
    pose = Pose(
        (float(origin[0]), float(origin[1])),
        ((float(jacobian[0, 0]), float(jacobian[0, 1])),
         (float(jacobian[1, 0]), float(jacobian[1, 1]))),
        base_pose.phase_yx,
        float(0.5 * (pitch_y + pitch_x)),
        pose_angle)
    refined = sample_segment(
        pixels, replace(sample.segment, pose=pose))
    if refined is None:
        return None
    return RefineOutcome(
        refined, delta_angle_deg, (delta_y, delta_x),
        baseline_heldout, heldout_after)


def _best_change_point(
    coordinates: np.ndarray, errors: np.ndarray, min_sites: int
) -> tuple[float, float, float] | None:
    cumulative = np.concatenate([[0.0], np.cumsum(errors)])
    best: tuple[float, float, float, float] | None = None
    size = coordinates.size
    for split in range(min_sites, size - min_sites):
        if coordinates[split] == coordinates[split - 1]:
            continue
        low = cumulative[split] / split
        high = (cumulative[size] - cumulative[split]) / (size - split)
        impurity = (split * low * (1.0 - low)
                    + (size - split) * high * (1.0 - high))
        if best is None or impurity < best[0]:
            best = (float(impurity), float(low), float(high),
                    float(0.5 * (coordinates[split - 1]
                                 + coordinates[split])))
    if best is None:
        return None
    return best[1], best[2], best[3]


def audit_segment(
    sample: SegmentSample,
    core: np.ndarray,
    provider: ReferenceField,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
    min_support: int,
) -> tuple[np.ndarray, bool, int, float]:
    points, expected, absolute = fragment_reference_sites(
        core, provider, page, origin_yx, rot_k)
    parity = _site_parity(absolute)

    def below_population_floor(selected: np.ndarray) -> bool:
        return (int(np.count_nonzero(selected & ~parity)) < min_support
                or int(np.count_nonzero(selected & parity)) < min_support)

    if points.shape[0] < 2 * AUDIT_MIN_SITES:
        support = int(points.shape[0])
        selected = np.ones(support, bool)
        return (np.asarray(core, bool), below_population_floor(selected),
                support, 0.0)
    wrong = (sample.bits[points[:, 0], points[:, 1]] != expected
             ).astype(np.float64)
    good = np.asarray(core, bool).copy()
    keep = np.ones(points.shape[0], bool)
    for axis in (0, 1, 0, 1):
        active = np.flatnonzero(keep)
        if active.size < 2 * AUDIT_MIN_SITES:
            break
        order = np.argsort(points[active, axis], kind="stable")
        coordinates = points[active, axis][order]
        change_point = _best_change_point(
            coordinates, wrong[active][order], AUDIT_MIN_SITES)
        if change_point is None:
            continue
        low, high, cut = change_point
        bad_low = low > high
        bad_rate, kept_rate = (low, high) if bad_low else (high, low)
        if not (bad_rate > AUDIT_BAD and kept_rate < AUDIT_GOOD):
            continue
        edge = int(np.ceil(cut))
        if axis == 0:
            if bad_low:
                good[:edge, :] = False
            else:
                good[edge:, :] = False
        else:
            if bad_low:
                good[:, :edge] = False
            else:
                good[:, edge:] = False
        keep &= good[points[:, 0], points[:, 1]]
    kept = int(keep.sum())
    residual = float(wrong[keep].mean()) if kept else 1.0
    refused = (below_population_floor(keep)
               or residual > AUDIT_POST_BAR)
    return good, refused, kept, residual


def subdivision_child_extents(
    extent_cells: tuple[int, int, int, int],
    depth: int,
) -> tuple[tuple[int, int, int, int], ...]:
    if depth >= SUBDIVISION_MAX_DEPTH:
        return ()
    cy0, cx0, cy1, cx1 = extent_cells
    height, width = cy1 - cy0, cx1 - cx0
    side = max(MIN_WINDOW_CELLS, min(height, width) // 2)
    if side >= min(height, width):
        return ()
    return tuple(
        (cy0 + offset_y, cx0 + offset_x,
         cy0 + offset_y + side, cx0 + offset_x + side)
        for offset_y, offset_x in (
            (0, 0), (0, width - side),
            (height - side, 0), (height - side, width - side)))

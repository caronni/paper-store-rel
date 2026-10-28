from __future__ import annotations

import math
import time
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy import ndimage

from ..data import (
    Capture,
    CaptureSurvey,
    JobResult,
    PlaneRaster,
    Region,
    RegionMark,
    SurveyDone,
)
from ..descriptor import (
    FactKey,
    Job,
    PluginDescriptor,
    Subject,
)
from ..lib.decimate import plane_mean_luma_f32
from .intake import PLANES_RGB, PLANE_GREY

STAGE_SURVEY: str = "survey"
SURVEY_COST: int = 10
PRICES: tuple[tuple[str, int], ...] = ((STAGE_SURVEY, SURVEY_COST),)

SURVEY_CELL_UM: float = 340.0
DENSITY_MIN: int = 5
MIN_AREA_MM2: float = 9.0
C_SNAP_TOLERANCE: float = 0.04
SUPPORT_HOLE_RADIUS_CELLS: float = 3.0
CANDIDATE_PITCHES_IN: tuple[Fraction, ...] = (
    Fraction(1, 600), Fraction(1, 300), Fraction(1, 200), Fraction(1, 150))

REFINE_BOUNDARY_SURVEY_CELLS: int = 2
REFINE_VALLEY_FRACTION: float = 0.65
REFINE_VALLEY_RUN: int = 3
REFINE_VALLEY_MIN_SPAN_FRACTION: float = 0.25
REFINE_VALLEY_HALO_SURVEY_CELLS: int = 1
REFINE_TILE_CELLS: int = 128
REFINE_TILE_HALO_CELLS: int = 4

PITCH_PROBES_PX: tuple[float, ...] = (
    2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0,
    48.0, 64.0, 96.0, 128.0,
)
CONTRAST_FLOOR: float = 30.0
MEASURE_WINDOW_PX: int = 2048
RATIO_TOLERANCE: float = 0.08
DEDUPE_TOLERANCE: float = 0.02
RADIAL_FLOOR: float = 0.01
SEARCH_OCTAVES: float = 1.0

WORK_CELL_PX: float = 4.0
DERIVATIVE_CELLS: float = 0.22
TENSOR_CELLS: float = 0.30
TENSOR_TILE_CELLS: int = 256


@dataclass(frozen=True)
class NativeView:
    dpi: float
    shape: tuple[int, int]
    planes: tuple[np.ndarray, ...]

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        if len(self.planes) == 1:
            return self.planes[0][r0:r1, c0:c1].astype(np.float32)
        return plane_mean_luma_f32(
            self.planes[0][r0:r1, c0:c1],
            self.planes[1][r0:r1, c0:c1],
            self.planes[2][r0:r1, c0:c1],
        )


@dataclass
class _Component:
    slices: tuple[slice, slice]
    activity: np.ndarray
    scores: np.ndarray
    median_score: float


@dataclass
class _RawRegion:
    origin_yx: tuple[int, int]
    support: np.ndarray
    step_px: int
    extent_px: tuple[int, int]
    score: float


def tensor_geometry(cell_px: float) -> tuple[int, int, int]:
    decimation = max(1, int(round(cell_px / WORK_CELL_PX)))
    work_pitch = max(1, int(round(cell_px / decimation)))
    return decimation, work_pitch, decimation * work_pitch


def _block_mean(image: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return np.asarray(image, np.float32)
    height = image.shape[0] // factor * factor
    width = image.shape[1] // factor * factor
    if height == 0 or width == 0:
        return np.zeros((0, 0), np.float32)
    return np.asarray(image[:height, :width]).reshape(
        height // factor, factor, width // factor, factor
    ).mean(axis=(1, 3), dtype=np.float32)


def _minor_eigen_work(work: np.ndarray, pitch_work_px: float,
                      sample: int) -> np.ndarray:
    image = np.asarray(work, np.float32)
    if min(image.shape, default=0) < 3:
        return np.zeros((0, 0), np.float32)
    derivative_sigma = max(0.6, DERIVATIVE_CELLS * pitch_work_px)
    gx = ndimage.gaussian_filter(
        image, derivative_sigma, order=(0, 1), mode="nearest"
    ) * derivative_sigma
    gy = ndimage.gaussian_filter(
        image, derivative_sigma, order=(1, 0), mode="nearest"
    ) * derivative_sigma
    tensor_sigma = max(1.0, TENSOR_CELLS * pitch_work_px)
    jxx = ndimage.gaussian_filter(gx * gx, tensor_sigma, mode="nearest")
    jyy = ndimage.gaussian_filter(gy * gy, tensor_sigma, mode="nearest")
    jxy = ndimage.gaussian_filter(gx * gy, tensor_sigma, mode="nearest")
    trace = jxx + jyy
    discriminant = np.sqrt(
        np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0)
    )
    minor = np.sqrt(np.maximum(0.5 * (trace - discriminant), 0.0))
    height = minor.shape[0] // sample * sample
    width = minor.shape[1] // sample * sample
    if height == 0 or width == 0:
        return np.zeros((0, 0), np.float32)
    return minor[:height, :width].reshape(
        height // sample, sample, width // sample, sample
    ).mean(axis=(1, 3), dtype=np.float32)


def _minor_eigen_score_array(image: np.ndarray,
                             pitch_px: float) -> tuple[np.ndarray, int]:
    decimation, sample, step = tensor_geometry(pitch_px)
    work = _block_mean(image, decimation)
    if min(work.shape, default=0) < 3:
        return np.zeros((0, 0), np.float32), decimation
    return _minor_eigen_work(work, pitch_px / decimation, sample), step


def _score_crop(view: NativeView, pitch_px: float,
                box: tuple[int, int, int, int]) -> tuple[np.ndarray, int]:
    y0, y1, x0, x1 = box
    return _minor_eigen_score_array(view.crop_luma(y0, y1, x0, x1), pitch_px)


def _tensor_halo_cells(pitch_work_px: float, sample: int) -> int:
    derivative = max(0.6, DERIVATIVE_CELLS * pitch_work_px)
    tensor = max(1.0, TENSOR_CELLS * pitch_work_px)
    work_halo = int(4.0 * derivative + 0.5) + int(4.0 * tensor + 0.5)
    return math.ceil(work_halo / sample)


def _whole_tensor_score(view: NativeView, pitch_px: float,
                        tile_cells: int = TENSOR_TILE_CELLS,
                        ) -> tuple[np.ndarray, int]:
    decimation, sample, step = tensor_geometry(pitch_px)
    rows = view.shape[0] // step
    cols = view.shape[1] // step
    if rows == 0 or cols == 0:
        return np.zeros((0, 0), np.float32), step
    out = np.empty((rows, cols), np.float32)
    halo = _tensor_halo_cells(pitch_px / decimation, sample)
    for row0 in range(0, rows, int(tile_cells)):
        row1 = min(rows, row0 + int(tile_cells))
        ext_row0 = max(0, row0 - halo)
        ext_row1 = min(rows, row1 + halo)
        for col0 in range(0, cols, int(tile_cells)):
            col1 = min(cols, col0 + int(tile_cells))
            ext_col0 = max(0, col0 - halo)
            ext_col1 = min(cols, col1 + halo)
            patch, _ = _score_crop(view, pitch_px, (
                ext_row0 * step,
                (view.shape[0] // decimation * decimation
                 if ext_row1 == rows else ext_row1 * step),
                ext_col0 * step,
                (view.shape[1] // decimation * decimation
                 if ext_col1 == cols else ext_col1 * step),
            ))
            out[row0:row1, col0:col1] = patch[
                row0 - ext_row0:row1 - ext_row0,
                col0 - ext_col0:col1 - ext_col0,
            ]
    return out, step


def _estimate_lattice(image: np.ndarray, pitch_px_nominal: float,
                      ) -> tuple[float, float] | None:
    if min(image.shape, default=0) < 3:
        return None
    f = image.astype(np.float64)
    gy, gx = np.gradient(f)
    magnitude = np.hypot(gy, gx)
    magnitude -= magnitude.mean()
    window_y = np.hanning(magnitude.shape[0])[:, None]
    window_x = np.hanning(magnitude.shape[1])[None, :]
    spectrum = np.abs(np.fft.rfft2(magnitude * window_y * window_x))
    fy = np.fft.fftfreq(magnitude.shape[0])[:, None]
    fx = np.fft.rfftfreq(magnitude.shape[1])[None, :]
    radial = np.hypot(fy, fx)
    centre = 1.0 / pitch_px_nominal
    band = 2.0 ** SEARCH_OCTAVES
    eligible = radial >= RADIAL_FLOOR
    eligible &= (radial >= centre / band) & (radial <= centre * band)
    spectrum[~eligible] = 0.0
    iy, ix = np.unravel_index(int(np.argmax(spectrum)), spectrum.shape)
    peak_fy = float(fy[iy, 0])
    peak_fx = float(fx[0, ix])
    peak_frequency = float(np.hypot(peak_fy, peak_fx))
    if peak_frequency <= 0:
        return None
    in_band = spectrum[spectrum > 0]
    if in_band.size > 65_536:
        stride = in_band.size // 65_536
        in_band = in_band[::stride]
    median = float(np.median(in_band)) if in_band.size else 0.0
    contrast = float(spectrum[iy, ix] / median) if median > 0 else 0.0
    return 1.0 / peak_frequency, float(contrast)


def _measure_cell_pitch(
    crop: np.ndarray,
) -> tuple[float, float, tuple[tuple[float, float], ...]] | None:
    image = np.asarray(crop)
    if min(image.shape, default=0) > MEASURE_WINDOW_PX:
        cy, cx = image.shape[0] // 2, image.shape[1] // 2
        half = MEASURE_WINDOW_PX // 2
        image = np.ascontiguousarray(
            image[cy - half:cy + half, cx - half:cx + half], np.float64)
    raw: list[tuple[float, float]] = []
    for probe in PITCH_PROBES_PX:
        if min(image.shape, default=0) < 8.0 * probe:
            continue
        estimate = _estimate_lattice(image, float(probe))
        if estimate is None:
            continue
        raw.append(estimate)

    strong: list[tuple[float, float]] = []
    for pitch, contrast in raw:
        if contrast < CONTRAST_FLOOR:
            continue
        for index, (prior_pitch, prior_contrast) in enumerate(strong):
            if abs(pitch / prior_pitch - 1.0) < DEDUPE_TOLERANCE:
                if contrast > prior_contrast:
                    strong[index] = (pitch, contrast)
                break
        else:
            strong.append((pitch, contrast))
    if not strong:
        return None

    strong.sort(key=lambda candidate: -candidate[0])
    chosen: tuple[float, float] | None = None
    for pitch, contrast in strong:
        if all(
            abs(pitch / other - max(1.0, round(pitch / other)))
            <= RATIO_TOLERANCE * max(1.0, round(pitch / other))
            for other, _ in strong
        ):
            chosen = (pitch, contrast)
            break
    if chosen is None:
        chosen = max(strong, key=lambda candidate: candidate[1])
    return chosen[0], chosen[1], tuple(strong)


def candidate_pitches(
        declared_pitch_in: Fraction | None) -> tuple[Fraction, ...]:
    if declared_pitch_in is None or declared_pitch_in in CANDIDATE_PITCHES_IN:
        return CANDIDATE_PITCHES_IN
    return tuple(sorted(CANDIDATE_PITCHES_IN + (declared_pitch_in,)))


def _snap_pitch(pitch_px: float, dpi: float,
                pitches: tuple[Fraction, ...]) -> Fraction | None:
    head, *rest = pitches
    best = (abs(pitch_px / (float(head) * dpi) - 1.0), head)
    for candidate in rest:
        error = abs(pitch_px / (float(candidate) * dpi) - 1.0)
        if error < best[0]:
            best = (error, candidate)
    return best[1] if best[0] <= C_SNAP_TOLERANCE else None


def _pitch_vote(crop: np.ndarray, dpi: float, pitches: tuple[Fraction, ...],
                ) -> tuple[Fraction, float] | None:
    measurement = _measure_cell_pitch(crop)
    if measurement is None:
        return None
    pitch_px, contrast, strong = measurement
    candidates = list(strong)
    candidates.append((pitch_px, contrast))
    snapped = [
        (pitch_in, float(pitch))
        for pitch, _ in candidates
        if (pitch_in := _snap_pitch(float(pitch), dpi, pitches)) is not None
    ]
    return max(snapped, key=lambda vote: vote[0]) if snapped else None


def _adaptive_threshold(score: np.ndarray) -> float:
    values = np.log1p(np.asarray(score, np.float64).ravel())
    values = values[np.isfinite(values)]
    if values.size == 0:
        return math.inf
    if float(np.max(values)) <= 0.0:
        return math.inf
    hist, edges = np.histogram(values, bins=256)
    probability = hist.astype(np.float64) / max(int(hist.sum()), 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    weight = np.cumsum(probability)
    mean = np.cumsum(probability * centres)
    variance = (mean[-1] * weight - mean) ** 2 / np.maximum(
        weight * (1.0 - weight), np.finfo(np.float64).eps
    )
    return float(np.expm1(centres[int(np.argmax(variance[:-1]))]))


def _active_mask(score: np.ndarray, threshold: float) -> np.ndarray:
    active = np.asarray(score) > threshold
    neighbours = ndimage.convolve(
        active.astype(np.uint8),
        np.ones((3, 3), np.uint8),
        mode="constant",
        cval=0,
    )
    return active & (neighbours >= DENSITY_MIN)


def _components(score: np.ndarray, threshold: float, step_px: int,
                px_per_mm: float) -> list[_Component]:
    activity = _active_mask(score, threshold)
    labels, _ = ndimage.label(activity)
    cell_area_mm2 = (step_px / px_per_mm) ** 2
    result: list[_Component] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        component = labels[slices] == label_id
        if int(component.sum()) * cell_area_mm2 < MIN_AREA_MM2:
            continue
        local_scores = np.asarray(score[slices], np.float32)
        result.append(_Component(
            slices=slices,
            activity=component,
            scores=local_scores,
            median_score=float(np.median(local_scores[component])),
        ))
    return result


def _component_pitch_crop(view: NativeView, component: _Component,
                          step_px: int) -> np.ndarray | None:
    y0 = component.slices[0].start * step_px
    x0 = component.slices[1].start * step_px
    y1 = min(view.shape[0], component.slices[0].stop * step_px)
    x1 = min(view.shape[1], component.slices[1].stop * step_px)
    if min(y1 - y0, x1 - x0) < 32:
        return None
    if min(y1 - y0, x1 - x0) > MEASURE_WINDOW_PX:
        centre_y = y0 + (y1 - y0) // 2
        centre_x = x0 + (x1 - x0) // 2
        half = MEASURE_WINDOW_PX // 2
        y0, y1 = centre_y - half, centre_y + half
        x0, x1 = centre_x - half, centre_x + half
    return view.crop_luma(y0, y1, x0, x1)


def _global_pitch(view: NativeView, components: list[_Component],
                  step_px: int, pitches: tuple[Fraction, ...],
                  ) -> tuple[Fraction | None, float | None,
                             tuple[tuple[Fraction, float], ...]]:
    votes: list[tuple[Fraction, float]] = []
    for component in sorted(
        components, key=lambda item: int(item.activity.sum()), reverse=True
    ):
        crop = _component_pitch_crop(view, component, step_px)
        if crop is None:
            continue
        vote = _pitch_vote(crop, view.dpi, pitches)
        if vote is not None:
            votes.append(vote)
    if not votes:
        return None, None, ()
    counts: dict[Fraction, int] = {}
    for vote in votes:
        counts[vote[0]] = counts.get(vote[0], 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None, None, tuple(votes)
    chosen = ordered[0][0]
    pitch = float(np.median([value for key, value in votes if key == chosen]))
    return chosen, pitch, tuple(votes)


def support_mask(activity: np.ndarray,
                 max_radius_grid: float = SUPPORT_HOLE_RADIUS_CELLS,
                 ) -> np.ndarray:
    active = np.asarray(activity, bool)
    padded = np.pad(active, 1, constant_values=False)
    enclosed = ndimage.binary_fill_holes(padded)[1:-1, 1:-1] & ~active
    labels, count = ndimage.label(enclosed)
    if count == 0 or max_radius_grid < 1.0:
        return active.copy()
    distance = ndimage.distance_transform_edt(enclosed)
    radii = ndimage.maximum(distance, labels, index=np.arange(1, count + 1))
    fill_ids = np.flatnonzero(radii <= max_radius_grid) + 1
    return active | np.isin(labels, fill_ids)


def _coherent_valleys(component: _Component) -> np.ndarray:
    low = component.activity & (
        component.scores <= REFINE_VALLEY_FRACTION * component.median_score
    )
    run = REFINE_VALLEY_RUN
    structures = (
        np.ones((run, 1), bool),
        np.ones((1, run), bool),
        np.eye(run, dtype=bool),
        np.fliplr(np.eye(run, dtype=bool)),
    )
    coherent = np.zeros(low.shape, bool)
    for structure in structures:
        coherent |= ndimage.binary_opening(low, structure=structure)
    labels, _ = ndimage.label(coherent, structure=np.ones((3, 3), bool))
    min_span = max(
        REFINE_VALLEY_RUN,
        int(math.ceil(
            REFINE_VALLEY_MIN_SPAN_FRACTION * min(component.activity.shape)
        )),
    )
    keep = np.zeros(coherent.shape, bool)
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        height = slices[0].stop - slices[0].start
        width = slices[1].stop - slices[1].start
        if max(height, width) >= min_span:
            keep[slices] |= labels[slices] == label_id
    if keep.any() and REFINE_VALLEY_HALO_SURVEY_CELLS:
        keep = ndimage.binary_dilation(
            keep, iterations=REFINE_VALLEY_HALO_SURVEY_CELLS
        )
    return keep


def _fine_geometry(component: _Component, survey_step_px: int,
                   pitch_px: float, origin_yx: tuple[int, int],
                   extent_px: tuple[int, int],
                   ) -> tuple[np.ndarray, np.ndarray, int]:
    _, _, step = tensor_geometry(pitch_px)
    rows = extent_px[0] // step
    cols = extent_px[1] // step
    if min(rows, cols) < 3:
        return np.zeros((0, 0), bool), np.zeros((0, 0), bool), step

    hole_radius = max(
        1.0, SUPPORT_HOLE_RADIUS_CELLS * pitch_px / survey_step_px
    )
    coarse_support = support_mask(component.activity, hole_radius)
    pad = REFINE_BOUNDARY_SURVEY_CELLS + 1
    padded = np.pad(coarse_support, pad, constant_values=False)
    boundary = (
        ndimage.binary_dilation(
            padded, iterations=REFINE_BOUNDARY_SURVEY_CELLS
        )
        & ~ndimage.binary_erosion(
            padded,
            iterations=REFINE_BOUNDARY_SURVEY_CELLS,
            border_value=0,
        )
    )
    domain_coarse = boundary | np.pad(
        _coherent_valleys(component), pad, constant_values=False
    )

    y0, x0 = origin_yx
    native_y = y0 + np.arange(rows, dtype=np.int64) * step + step // 2
    native_x = x0 + np.arange(cols, dtype=np.int64) * step + step // 2
    coarse_y = native_y // survey_step_px - component.slices[0].start + pad
    coarse_x = native_x // survey_step_px - component.slices[1].start + pad
    valid_y = (coarse_y >= 0) & (coarse_y < padded.shape[0])
    valid_x = (coarse_x >= 0) & (coarse_x < padded.shape[1])
    base = np.zeros((rows, cols), bool)
    domain = np.zeros_like(base)
    if valid_y.any() and valid_x.any():
        target = np.ix_(np.flatnonzero(valid_y), np.flatnonzero(valid_x))
        source = np.ix_(coarse_y[valid_y], coarse_x[valid_x])
        base[target] = padded[source]
        domain[target] = domain_coarse[source]
    return base, domain, step


def _tile_selection(domain: np.ndarray) -> np.ndarray:
    rows = math.ceil(domain.shape[0] / REFINE_TILE_CELLS)
    cols = math.ceil(domain.shape[1] / REFINE_TILE_CELLS)
    selected = np.zeros((rows, cols), bool)
    for row in range(rows):
        y0 = row * REFINE_TILE_CELLS
        y1 = min(domain.shape[0], y0 + REFINE_TILE_CELLS)
        for col in range(cols):
            x0 = col * REFINE_TILE_CELLS
            x1 = min(domain.shape[1], x0 + REFINE_TILE_CELLS)
            selected[row, col] = bool(domain[y0:y1, x0:x1].any())
    if selected.any():
        selected = ndimage.binary_dilation(
            selected, structure=np.ones((3, 3), bool)
        )
    return selected


def _boundary_scores(view: NativeView, origin_yx: tuple[int, int],
                     pitch_px: float, shape: tuple[int, int],
                     selected: np.ndarray, step: int,
                     ) -> tuple[np.ndarray, np.ndarray, int]:
    score = np.zeros(shape, np.float32)
    known = np.zeros(shape, bool)
    tiles = 0
    y_origin, x_origin = origin_yx
    for row, col in np.argwhere(selected):
        fy0 = int(row) * REFINE_TILE_CELLS
        fx0 = int(col) * REFINE_TILE_CELLS
        fy1 = min(shape[0], fy0 + REFINE_TILE_CELLS)
        fx1 = min(shape[1], fx0 + REFINE_TILE_CELLS)
        py0 = max(0, fy0 - REFINE_TILE_HALO_CELLS)
        px0 = max(0, fx0 - REFINE_TILE_HALO_CELLS)
        py1 = min(shape[0], fy1 + REFINE_TILE_HALO_CELLS)
        px1 = min(shape[1], fx1 + REFINE_TILE_HALO_CELLS)
        local, _ = _score_crop(view, pitch_px, (
            y_origin + py0 * step,
            y_origin + py1 * step,
            x_origin + px0 * step,
            x_origin + px1 * step,
        ))
        oy0, ox0 = fy0 - py0, fx0 - px0
        central = local[oy0:oy0 + fy1 - fy0, ox0:ox0 + fx1 - fx0]
        if central.shape != (fy1 - fy0, fx1 - fx0):
            continue
        score[fy0:fy1, fx0:fx1] = central
        known[fy0:fy1, fx0:fx1] = True
        tiles += 1
    return score, known, tiles


def _merge_boundary_refinement(base: np.ndarray, domain: np.ndarray,
                               active: np.ndarray,
                               known: np.ndarray) -> np.ndarray:
    candidate = np.asarray(base, bool) | (
        np.asarray(active, bool) & np.asarray(known, bool)
    )
    replace = np.asarray(domain, bool) & np.asarray(known, bool)
    candidate[replace] = np.asarray(active, bool)[replace]
    enclosed = ndimage.binary_fill_holes(candidate) & ~candidate
    candidate |= enclosed & base
    return candidate


def _refine_component(view: NativeView, component: _Component,
                      survey_step_px: int, pitch_px: float,
                      px_per_mm: float) -> list[_RawRegion]:
    halo = int(round(max(2.0 * pitch_px, px_per_mm)))
    y0 = max(0, component.slices[0].start * survey_step_px - halo)
    x0 = max(0, component.slices[1].start * survey_step_px - halo)
    y1 = min(view.shape[0], component.slices[0].stop * survey_step_px + halo)
    x1 = min(view.shape[1], component.slices[1].stop * survey_step_px + halo)
    extent = (y1 - y0, x1 - x0)
    if min(extent) < 4.0 * pitch_px:
        return []
    base, domain, step = _fine_geometry(
        component, survey_step_px, pitch_px, (y0, x0), extent)
    if not domain.any():
        return []
    selected = _tile_selection(domain)
    score, known, _ = _boundary_scores(
        view, (y0, x0), pitch_px, base.shape, selected, step)
    if not known.any():
        return []
    active = _active_mask(score, _adaptive_threshold(score[known])) & known
    labels, _ = ndimage.label(active)
    touching = np.unique(labels[active & base])
    touching = touching[touching != 0]
    if touching.size == 0:
        return []
    active = np.isin(labels, touching)
    candidate = _merge_boundary_refinement(base, domain, active, known)

    labels, _ = ndimage.label(candidate)
    cell_area_mm2 = (step / px_per_mm) ** 2
    result: list[_RawRegion] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        region = labels[slices] == label_id
        if int(region.sum()) * cell_area_mm2 < MIN_AREA_MM2:
            continue
        support = support_mask(
            region, SUPPORT_HOLE_RADIUS_CELLS * pitch_px / step)
        origin = (y0 + slices[0].start * step, x0 + slices[1].start * step)
        max_height = view.shape[0] - origin[0]
        max_width = view.shape[1] - origin[1]
        region_extent = (
            min(support.shape[0] * step, max_height),
            min(support.shape[1] * step, max_width),
        )
        evidence = region & known[slices] & active[slices]
        median = (float(np.median(score[slices][evidence]))
                  if evidence.any() else component.median_score)
        result.append(
            _RawRegion(origin, support, step, region_extent, median))
    return result


def _support_area_px(cells: np.ndarray, step_px: int,
                     extent_px: tuple[int, int]) -> int:
    height, width = extent_px
    row_heights = np.full(cells.shape[0], step_px, np.int64)
    col_widths = np.full(cells.shape[1], step_px, np.int64)
    row_heights[-1] = height - step_px * (cells.shape[0] - 1)
    col_widths[-1] = width - step_px * (cells.shape[1] - 1)
    return int(np.sum(cells * row_heights[:, None] * col_widths))


def survey_view(view: NativeView, declared_pitch_in: Fraction | None,
                ) -> tuple[tuple[_RawRegion, ...], Fraction | None,
                           float | None, np.ndarray, int]:
    pitches = candidate_pitches(declared_pitch_in)
    px_per_mm = view.dpi / 25.4
    survey_pitch_px = SURVEY_CELL_UM / 1000.0 * px_per_mm
    _, _, expected_step = tensor_geometry(survey_pitch_px)
    if min(view.shape, default=0) < 4.0 * survey_pitch_px:
        return (), None, None, np.zeros((0, 0), np.float32), expected_step

    score, survey_step = _whole_tensor_score(view, survey_pitch_px)
    if min(score.shape, default=0) < 3:
        return (), None, None, score, survey_step
    threshold = _adaptive_threshold(score)
    components = _components(score, threshold, survey_step, px_per_mm)
    voted_pitch, measured_pitch, _ = _global_pitch(
        view, components, survey_step, pitches)
    pitch_px = measured_pitch
    if voted_pitch is not None and pitch_px is None:
        pitch_px = float(voted_pitch) * view.dpi

    raw_regions: list[_RawRegion] = []
    for component in components:
        refined = (
            _refine_component(
                view, component, survey_step, pitch_px, px_per_mm)
            if pitch_px is not None else [])
        if refined:
            raw_regions.extend(refined)
            continue
        y0 = component.slices[0].start * survey_step
        x0 = component.slices[1].start * survey_step
        support = support_mask(
            component.activity,
            max(1.0, SUPPORT_HOLE_RADIUS_CELLS
                * (pitch_px / survey_step if pitch_px is not None else 1.0)),
        )
        raw_regions.append(_RawRegion(
            (y0, x0),
            support,
            survey_step,
            (min(support.shape[0] * survey_step, view.shape[0] - y0),
             min(support.shape[1] * survey_step, view.shape[1] - x0)),
            component.median_score,
        ))
    return tuple(raw_regions), voted_pitch, pitch_px, score, survey_step


def native_view(capture: Capture,
                planes: tuple[PlaneRaster, ...]) -> NativeView:
    level_index = capture.levels[-1].index
    names = PLANES_RGB if capture.channels == 3 else (PLANE_GREY,)
    by_name = {plane.plane: plane for plane in planes
               if plane.level_index == level_index}
    return NativeView(
        dpi=capture.dpi,
        shape=capture.shape_px,
        planes=tuple(by_name[name].open() for name in names),
    )


def survey_capture(capture: Capture, planes: tuple[PlaneRaster, ...],
                   declared_pitch_in: Fraction,
                   ) -> tuple[CaptureSurvey, tuple[object, ...]]:
    view = native_view(capture, planes)
    raw_regions, voted_pitch, pitch_px, score, survey_step = survey_view(
        view, declared_pitch_in)
    if voted_pitch is not None and voted_pitch != declared_pitch_in:
        raise ValueError(
            f"survey of capture {capture.capture_id[:12]} voted printed "
            f"pitch {voted_pitch} in, but the declared format row is "
            f"{declared_pitch_in} in")
    px_per_mm = capture.dpi / 25.4
    measured: list[tuple[float, np.ndarray, _RawRegion]] = []
    for raw in raw_regions:
        cells = np.array(raw.support, dtype=bool, copy=True, order="C")
        cells.flags.writeable = False
        area_px = _support_area_px(cells, raw.step_px, raw.extent_px)
        measured.append((area_px / (px_per_mm * px_per_mm), cells, raw))
    measured.sort(key=lambda item: -item[0])
    regions = tuple(
        Region(
            capture_id=capture.capture_id,
            region_index=region_index,
            origin_yx=raw.origin_yx,
            step_px=raw.step_px,
            cells=cells,
            extent_px=raw.extent_px,
            area_mm2=area_mm2,
            median_tensor_score=raw.score,
        )
        for region_index, (area_mm2, cells, raw) in enumerate(measured)
    )
    survey = CaptureSurvey(
        capture_id=capture.capture_id,
        regions=regions,
        pitch_class=voted_pitch,
        pitch_px=pitch_px,
    )
    return survey, (_survey_event(survey, score, survey_step),)


def _region_mark(region: Region, pitch_px: float | None) -> RegionMark:
    if pitch_px is None:
        shape_cells = (int(region.cells.shape[0]), int(region.cells.shape[1]))
    else:
        shape_cells = (max(1, int(round(region.extent_px[0] / pitch_px))),
                       max(1, int(round(region.extent_px[1] / pitch_px))))
    return RegionMark(
        region_index=region.region_index,
        origin_yx=region.origin_yx,
        shape_cells=shape_cells,
        pitch_px=pitch_px,
        support_cells=int(region.cells.sum()),
        cells=region.cells,
        step_px=region.step_px,
    )


def _survey_event(survey: CaptureSurvey, score: np.ndarray,
                  survey_step: int) -> SurveyDone:
    return SurveyDone(
        capture=survey.capture_id,
        n_regions=len(survey.regions),
        regions=tuple(_region_mark(region, survey.pitch_px)
                      for region in survey.regions),
        pitch_class=(None if survey.pitch_class is None
                     else str(survey.pitch_class)),
        preview=score if score.size else None,
        preview_decim=survey_step,
    )


def prepare_survey(store: object, subject: Subject,
                   stage: str) -> Job | None:
    capture = store.capture(str(subject))
    planes = store.rasters(capture.capture_id)
    pitch_in = store.row.pitch_in

    def job() -> JobResult:
        started = time.thread_time()
        fact, events = survey_capture(capture, planes, pitch_in)
        return JobResult((fact,), tuple(events),
                         time.thread_time() - started)

    return job


def _survey_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    return (fact.capture_id,)


def _survey_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    return ()


def _survey_eligible(store: object, subject: Subject) -> bool:
    return store.survey(subject) is None


def _survey_retire(store: object, subject: Subject) -> bool:
    return store.survey(subject) is not None


def _survey_stage(store: object, subject: Subject) -> str | None:
    return STAGE_SURVEY


def _survey_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    return SURVEY_COST


SURVEY_DESCRIPTOR = PluginDescriptor(
    name="survey",
    subject_kind="capture",
    born_by=(Capture,),
    subjects_of=_survey_subjects,
    reads=_survey_reads,
    eligible=_survey_eligible,
    stage=_survey_stage,
    cost=_survey_cost,
    retire=_survey_retire,
    prepare=prepare_survey,
    produces=(CaptureSurvey,),
    prices=PRICES,
)

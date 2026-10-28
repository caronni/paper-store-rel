"""Physically denominated payload-region survey (E021 production port).

This stage says only where later placement is worth attempting.  It does not
read pilots, mint addresses, or claim that a candidate is valid payload.

The qualified E021 algorithm is retained:

* minor-eigenvalue structure-tensor activity at one 340 um footing;
* log-Otsu plus a 5-of-9 density condition and a 9 mm2 component floor;
* at most one integer-cell-pitch vote per component and one platen-wide vote;
* pitch-scale refinement only at boundaries and coherent separating valleys;
* topology-aware support completion.

Whole-platen filtering uses differentially qualified overlap tiles. Regions
store block-constant support on the detector grid; ``SupportMask`` reproduces
the historical native mask exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy import ndimage

from ._survey_tensor import (
    _feature_luma,
    _score_crop,
    _whole_tensor_score,
    tensor_geometry,
)
from .lattice import MEASURE_WINDOW_PX, measure_cell_pitch
from .scan import Raster
from .types import SurveyRegionRecord


PRINT_DPI = 600.0
SURVEY_CELL_UM = 340.0
DENSITY_MIN = 5
MIN_AREA_MM2 = 9.0
C_SNAP_TOLERANCE = 0.04
MAX_C_DOTS = 12
SUPPORT_HOLE_RADIUS_CELLS = 3.0

REFINE_BOUNDARY_SURVEY_CELLS = 2
REFINE_VALLEY_FRACTION = 0.65
REFINE_VALLEY_RUN = 3
REFINE_VALLEY_MIN_SPAN_FRACTION = 0.25
REFINE_VALLEY_HALO_SURVEY_CELLS = 1
REFINE_TILE_CELLS = 128
REFINE_TILE_HALO_CELLS = 4

PITCH_PROBES_PX = (
    2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0,
    48.0, 64.0, 96.0, 128.0,
)


@dataclass(frozen=True, slots=True)
class SupportMask:
    """Compact search support on an axis-aligned native-pixel grid.

    Cell ``(iy, ix)`` covers the half-open native rectangle beginning at
    ``origin_yx + step_px * (iy, ix)``.  ``extent_px`` clips the final row and
    column at the capture boundary.  The stored array is copied and made
    read-only so a frozen survey cannot be mutated through NumPy aliasing.
    """

    origin_yx: tuple[int, int]
    step_px: int
    cells: np.ndarray
    extent_px: tuple[int, int]

    def __post_init__(self) -> None:
        y0, x0 = self.origin_yx
        height, width = self.extent_px
        if y0 < 0 or x0 < 0:
            raise ValueError("support origin must be non-negative")
        if self.step_px < 1:
            raise ValueError("support step must be positive")
        if height < 1 or width < 1:
            raise ValueError("support extent must be non-empty")
        data = np.array(self.cells, dtype=bool, copy=True, order="C")
        if data.ndim != 2 or min(data.shape, default=0) < 1:
            raise ValueError("support cells must be a non-empty 2-D mask")
        if not ((data.shape[0] - 1) * self.step_px
                < height <= data.shape[0] * self.step_px):
            raise ValueError("support height does not match its grid")
        if not ((data.shape[1] - 1) * self.step_px
                < width <= data.shape[1] * self.step_px):
            raise ValueError("support width does not match its grid")
        if not data.any():
            raise ValueError("support must contain at least one true cell")
        data.flags.writeable = False
        object.__setattr__(self, "cells", data)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        y0, x0 = self.origin_yx
        height, width = self.extent_px
        return y0, x0, height, width

    @property
    def area_px(self) -> int:
        """Exact supported native-pixel area, including clipped edge cells."""
        height, width = self.extent_px
        row_heights = np.full(self.cells.shape[0], self.step_px, np.int64)
        col_widths = np.full(self.cells.shape[1], self.step_px, np.int64)
        row_heights[-1] = height - self.step_px * (self.cells.shape[0] - 1)
        col_widths[-1] = width - self.step_px * (self.cells.shape[1] - 1)
        return int(np.sum(self.cells * row_heights[:, None] * col_widths))

    def rasterize(self) -> np.ndarray:
        """Materialize this bbox-local native mask for diagnostics only."""
        dense = np.repeat(
            np.repeat(self.cells, self.step_px, axis=0),
            self.step_px,
            axis=1,
        )
        height, width = self.extent_px
        return dense[:height, :width]

    def rasterize_crop(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray:
        """Materialize support in an arbitrary native-coordinate crop.

        This is the bounded window-sampling path; unlike :meth:`rasterize`,
        it never allocates in proportion to the complete region.  Pixels
        outside the support bbox are returned false.
        """
        if not (0 <= r0 < r1 and 0 <= c0 < c1):
            raise ValueError("support crop must be a non-empty positive box")
        out = np.zeros((r1 - r0, c1 - c0), bool)
        y0, x0 = self.origin_yx
        height, width = self.extent_px
        iy0, iy1 = max(r0, y0), min(r1, y0 + height)
        ix0, ix1 = max(c0, x0), min(c1, x0 + width)
        if iy0 >= iy1 or ix0 >= ix1:
            return out
        native_y = np.arange(iy0, iy1, dtype=np.int64)
        native_x = np.arange(ix0, ix1, dtype=np.int64)
        grid_y = ((native_y - y0) // self.step_px).astype(np.intp)
        grid_x = ((native_x - x0) // self.step_px).astype(np.intp)
        out[iy0 - r0 : iy1 - r0, ix0 - c0 : ix1 - c0] = self.cells[
            np.ix_(grid_y, grid_x)
        ]
        return out


@dataclass(frozen=True, slots=True)
class SurveyRegion:
    support: SupportMask
    area_mm2: float
    median_tensor_score: float

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return self.support.bbox


def region_from_record(record: SurveyRegionRecord) -> SurveyRegion:
    """Rebuild the transient survey region a durable record froze (v0.33).

    The record's RLE support runs, grid shape, origin, extent, area, and
    tensor score reproduce the frozen ``SupportMask``/``SurveyRegion``
    exactly — the mop-up level's ``prepare_region`` then re-derives the
    same crop and box prefilter the base pass saw.
    """
    rows, columns = record.support_shape_yx
    flat = np.zeros(rows * columns, bool)
    for run in record.support_runs:
        flat[run.start:run.start + run.length] = True
    support = SupportMask(
        origin_yx=tuple(record.origin_yx),
        step_px=int(record.support_step_px),
        cells=flat.reshape(rows, columns),
        extent_px=tuple(record.extent_yx),
    )
    return SurveyRegion(
        support, float(record.area_mm2), float(record.median_tensor_score))


@dataclass(frozen=True, slots=True)
class PitchVote:
    c_dots: int
    pitch_px: float


@dataclass(frozen=True, slots=True)
class SurveyDiagnostics:
    threshold: float | None
    survey_step_px: int
    survey_scale_px: float
    component_count: int
    refinement_tiles: int
    refinement_scored_cells: int
    refinement_grid_cells: int

    @property
    def refinement_fraction(self) -> float:
        return (
            self.refinement_scored_cells / self.refinement_grid_cells
            if self.refinement_grid_cells
            else 0.0
        )


@dataclass(frozen=True, slots=True)
class PayloadSurvey:
    regions: tuple[SurveyRegion, ...]
    c_dots: int | None
    cell_pitch_px: float | None
    pitch_votes: tuple[PitchVote, ...]
    diagnostics: SurveyDiagnostics


@dataclass(slots=True)
class _Component:
    slices: tuple[slice, slice]
    activity: np.ndarray
    scores: np.ndarray
    median_score: float


@dataclass(slots=True)
class _RefinedRegion:
    origin_yx: tuple[int, int]
    support: np.ndarray
    step_px: int
    extent_px: tuple[int, int]
    score: float


@dataclass(slots=True)
class _Refinement:
    regions: list[_RefinedRegion]
    tiles: int
    scored_cells: int
    grid_cells: int


def _adaptive_threshold(score: np.ndarray) -> float:
    """One scan-adaptive log-space Otsu threshold.

    The sole E021 correction: NumPy's arbitrary histogram range for a zero
    plane otherwise creates a negative threshold and mints a flat component.
    """
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


def _components(
    score: np.ndarray,
    threshold: float,
    *,
    step_px: int,
    px_per_mm: float,
) -> list[_Component]:
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
        result.append(
            _Component(
                slices=slices,
                activity=component,
                scores=local_scores,
                median_score=float(np.median(local_scores[component])),
            )
        )
    return result


def _component_pitch_crop(
    raster: Raster, component: _Component, step_px: int
) -> np.ndarray | None:
    """Historical full-bbox pitch input with an equivalent crop pushdown.

    ``measure_cell_pitch`` centrally crops only when BOTH dimensions exceed
    2048.  Applying that exact operation before float32 materialization keeps
    wide ribbons intact while avoiding a page-sized temporary.
    """
    y0 = component.slices[0].start * step_px
    x0 = component.slices[1].start * step_px
    y1 = min(raster.shape[0], component.slices[0].stop * step_px)
    x1 = min(raster.shape[1], component.slices[1].stop * step_px)
    if min(y1 - y0, x1 - x0) < 32:
        return None
    if min(y1 - y0, x1 - x0) > MEASURE_WINDOW_PX:
        centre_y = y0 + (y1 - y0) // 2
        centre_x = x0 + (x1 - x0) // 2
        half = MEASURE_WINDOW_PX // 2
        y0, y1 = centre_y - half, centre_y + half
        x0, x1 = centre_x - half, centre_x + half
    return _feature_luma(raster, y0, y1, x0, x1)


def _snap_c(pitch_px: float, dpi: float) -> int | None:
    value = pitch_px * PRINT_DPI / dpi
    c_dots = int(round(value))
    if not 1 <= c_dots <= MAX_C_DOTS:
        return None
    return (
        c_dots
        if abs(value / c_dots - 1.0) <= C_SNAP_TOLERANCE
        else None
    )


def _pitch_vote(crop: np.ndarray, dpi: float) -> PitchVote | None:
    try:
        measurement = measure_cell_pitch(crop, probes_px=PITCH_PROBES_PX)
    except ValueError:
        return None
    candidates = list(measurement.strong)
    candidates.append((measurement.pitch_px, measurement.contrast))
    snapped = [
        PitchVote(c_dots, float(pitch))
        for pitch, _ in candidates
        if (c_dots := _snap_c(float(pitch), dpi)) is not None
    ]
    return max(snapped, key=lambda vote: vote.c_dots) if snapped else None


def _global_pitch(
    raster: Raster, components: list[_Component], step_px: int
) -> tuple[int | None, float | None, tuple[PitchVote, ...]]:
    votes: list[PitchVote] = []
    for component in sorted(
        components, key=lambda item: int(item.activity.sum()), reverse=True
    ):
        crop = _component_pitch_crop(raster, component, step_px)
        if crop is None:
            continue
        vote = _pitch_vote(crop, raster.dpi)
        if vote is not None:
            votes.append(vote)
    if not votes:
        return None, None, ()
    counts: dict[int, int] = {}
    for vote in votes:
        counts[vote.c_dots] = counts.get(vote.c_dots, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None, None, tuple(votes)
    chosen = ordered[0][0]
    pitch = float(np.median([v.pitch_px for v in votes if v.c_dots == chosen]))
    return chosen, pitch, tuple(votes)


def support_mask(
    activity: np.ndarray,
    max_radius_grid: float = SUPPORT_HOLE_RADIUS_CELLS,
) -> np.ndarray:
    """Fill small enclosed tensor dropouts without changing the exterior."""
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
        int(
            math.ceil(
                REFINE_VALLEY_MIN_SPAN_FRACTION
                * min(component.activity.shape)
            )
        ),
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


def _fine_geometry(
    component: _Component,
    *,
    survey_step_px: int,
    pitch_px: float,
    origin_yx: tuple[int, int],
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
    coarse_y = (
        native_y // survey_step_px - component.slices[0].start + pad
    )
    coarse_x = (
        native_x // survey_step_px - component.slices[1].start + pad
    )
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


def _boundary_scores(
    raster: Raster,
    *,
    origin_yx: tuple[int, int],
    pitch_px: float,
    shape: tuple[int, int],
    selected: np.ndarray,
    step: int,
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
        local, local_step = _score_crop(
            raster,
            pitch_px=pitch_px,
            box=(
                y_origin + py0 * step,
                y_origin + py1 * step,
                x_origin + px0 * step,
                x_origin + px1 * step,
            ),
        )
        if local_step != step:
            raise RuntimeError("pitch-scale tensor grid changed within tile")
        oy0, ox0 = fy0 - py0, fx0 - px0
        central = local[
            oy0 : oy0 + fy1 - fy0, ox0 : ox0 + fx1 - fx0
        ]
        if central.shape != (fy1 - fy0, fx1 - fx0):
            continue
        score[fy0:fy1, fx0:fx1] = central
        known[fy0:fy1, fx0:fx1] = True
        tiles += 1
    return score, known, tiles


def _merge_boundary_refinement(
    base: np.ndarray,
    domain: np.ndarray,
    active: np.ndarray,
    known: np.ndarray,
) -> np.ndarray:
    candidate = np.asarray(base, bool) | (
        np.asarray(active, bool) & np.asarray(known, bool)
    )
    replace = np.asarray(domain, bool) & np.asarray(known, bool)
    candidate[replace] = np.asarray(active, bool)[replace]
    enclosed = ndimage.binary_fill_holes(candidate) & ~candidate
    candidate |= enclosed & base
    return candidate


def _refine_component(
    raster: Raster,
    component: _Component,
    *,
    survey_step_px: int,
    pitch_px: float,
    px_per_mm: float,
) -> _Refinement:
    halo = int(round(max(2.0 * pitch_px, px_per_mm)))
    y0 = max(0, component.slices[0].start * survey_step_px - halo)
    x0 = max(0, component.slices[1].start * survey_step_px - halo)
    y1 = min(
        raster.shape[0], component.slices[0].stop * survey_step_px + halo
    )
    x1 = min(
        raster.shape[1], component.slices[1].stop * survey_step_px + halo
    )
    extent = (y1 - y0, x1 - x0)
    if min(extent) < 4.0 * pitch_px:
        return _Refinement([], 0, 0, 0)
    base, domain, step = _fine_geometry(
        component,
        survey_step_px=survey_step_px,
        pitch_px=pitch_px,
        origin_yx=(y0, x0),
        extent_px=extent,
    )
    if not domain.any():
        return _Refinement([], 0, 0, int(base.size))
    selected = _tile_selection(domain)
    score, known, tiles = _boundary_scores(
        raster,
        origin_yx=(y0, x0),
        pitch_px=pitch_px,
        shape=base.shape,
        selected=selected,
        step=step,
    )
    if not known.any():
        return _Refinement([], tiles, 0, int(base.size))
    active = _active_mask(score, _adaptive_threshold(score[known])) & known
    labels, _ = ndimage.label(active)
    touching = np.unique(labels[active & base])
    touching = touching[touching != 0]
    if touching.size == 0:
        return _Refinement([], tiles, int(known.sum()), int(base.size))
    active = np.isin(labels, touching)
    candidate = _merge_boundary_refinement(base, domain, active, known)

    labels, _ = ndimage.label(candidate)
    cell_area_mm2 = (step / px_per_mm) ** 2
    result: list[_RefinedRegion] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        region = labels[slices] == label_id
        if int(region.sum()) * cell_area_mm2 < MIN_AREA_MM2:
            continue
        support = support_mask(
            region, SUPPORT_HOLE_RADIUS_CELLS * pitch_px / step
        )
        origin = (y0 + slices[0].start * step, x0 + slices[1].start * step)
        max_height = raster.shape[0] - origin[0]
        max_width = raster.shape[1] - origin[1]
        region_extent = (
            min(support.shape[0] * step, max_height),
            min(support.shape[1] * step, max_width),
        )
        evidence = region & known[slices] & active[slices]
        median = (
            float(np.median(score[slices][evidence]))
            if evidence.any()
            else component.median_score
        )
        result.append(
            _RefinedRegion(origin, support, step, region_extent, median)
        )
    return _Refinement(result, tiles, int(known.sum()), int(base.size))


def full_support(raster: Raster) -> SupportMask:
    """The trivial whole-sheet survey support (explicit fast path)."""
    cells = np.ones((1, 1), bool)
    return SupportMask((0, 0), max(raster.shape), cells, raster.shape)


def survey_raster(raster: Raster) -> PayloadSurvey:
    """Return E021 candidate supports and one honest platen-wide pitch."""
    px_per_mm = raster.dpi / 25.4
    survey_pitch_px = SURVEY_CELL_UM / 1000.0 * px_per_mm
    _, _, expected_step = tensor_geometry(survey_pitch_px)
    empty_diagnostics = SurveyDiagnostics(
        threshold=None,
        survey_step_px=expected_step,
        survey_scale_px=survey_pitch_px,
        component_count=0,
        refinement_tiles=0,
        refinement_scored_cells=0,
        refinement_grid_cells=0,
    )
    if min(raster.shape, default=0) < 4.0 * survey_pitch_px:
        return PayloadSurvey((), None, None, (), empty_diagnostics)

    score, survey_step = _whole_tensor_score(raster, survey_pitch_px)
    if min(score.shape, default=0) < 3:
        return PayloadSurvey((), None, None, (), empty_diagnostics)
    threshold = _adaptive_threshold(score)
    components = _components(
        score,
        threshold,
        step_px=survey_step,
        px_per_mm=px_per_mm,
    )
    c_dots, measured_pitch, votes = _global_pitch(
        raster, components, survey_step
    )
    pitch_px = measured_pitch
    if c_dots is not None and pitch_px is None:
        pitch_px = raster.dpi * c_dots / PRINT_DPI

    raw_regions: list[_RefinedRegion] = []
    refine_tiles = 0
    refine_scored = 0
    refine_grid = 0
    for component in components:
        refinement = (
            _refine_component(
                raster,
                component,
                survey_step_px=survey_step,
                pitch_px=pitch_px,
                px_per_mm=px_per_mm,
            )
            if pitch_px is not None
            else _Refinement([], 0, 0, 0)
        )
        refine_tiles += refinement.tiles
        refine_scored += refinement.scored_cells
        refine_grid += refinement.grid_cells
        if refinement.regions:
            raw_regions.extend(refinement.regions)
            continue
        y0 = component.slices[0].start * survey_step
        x0 = component.slices[1].start * survey_step
        support = support_mask(
            component.activity,
            max(
                1.0,
                SUPPORT_HOLE_RADIUS_CELLS
                * (pitch_px / survey_step if pitch_px is not None else 1.0),
            ),
        )
        raw_regions.append(
            _RefinedRegion(
                (y0, x0),
                support,
                survey_step,
                (
                    min(support.shape[0] * survey_step, raster.shape[0] - y0),
                    min(support.shape[1] * survey_step, raster.shape[1] - x0),
                ),
                component.median_score,
            )
        )

    regions: list[SurveyRegion] = []
    for raw in raw_regions:
        support = SupportMask(
            raw.origin_yx, raw.step_px, raw.support, raw.extent_px
        )
        area_mm2 = support.area_px / (px_per_mm * px_per_mm)
        regions.append(SurveyRegion(support, area_mm2, raw.score))
    regions.sort(key=lambda region: -region.area_mm2)
    diagnostics = SurveyDiagnostics(
        threshold=threshold,
        survey_step_px=survey_step,
        survey_scale_px=survey_pitch_px,
        component_count=len(components),
        refinement_tiles=refine_tiles,
        refinement_scored_cells=refine_scored,
        refinement_grid_cells=refine_grid,
    )
    return PayloadSurvey(
        tuple(regions), c_dots, pitch_px, votes, diagnostics
    )

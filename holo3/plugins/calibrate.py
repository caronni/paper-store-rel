from __future__ import annotations

import time
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Sequence

import numpy as np
from scipy import ndimage

from ..data import (
    CalibrateAdopted,
    JobResult,
    OwnedPageEvidence,
    Placement,
    RegionCtx,
    WindowEvidence,
)
from ..data import RegionKey, WindowId
from ..descriptor import (
    FactKey,
    Job,
    KEY_EVIDENCE_FIT,
    KEY_POSE_AFFINE,
    KEY_REGION_PITCH,
    PluginDescriptor,
    Subject,
)
from ..format import keystream, pilots
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib import pava
from ..lib.decimate import luma_f32, plane_mean_luma_f32
from ..lib.geometry import (
    TILE_CELLS,
    compose_from_native,
    rotated_points,
    site_parity,
)
from ..lib.owners import freeze_page_owners
from ..lib.pava import (
    CAL_MIN_HELDOUT,
    CAL_MIN_PER_CLASS,
    CTX_LLR_CLAMP,
    CTX_MIN_SEARCH,
    CTX_MIN_SEARCH_PER_CLASS,
    CTX_MIN_VALIDATION,
    CTX_MIN_VALIDATION_PER_CLASS,
    N_CONTEXT_BINS,
    calibration_llr,
    calibration_probability,
    probability_logloss,
)

APERTURE_CELLS: float = 0.7
SCORE_SPREAD_FLOOR: float = 1e-6
PLANE_TAG_K: str = "K"

STAGE_CALIBRATE: str = "calibrate"
CALIBRATE_COST: int = 15
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_CALIBRATE, CALIBRATE_COST),)


@dataclass(frozen=True)
class SiteLookup:
    kind: np.ndarray
    index: np.ndarray


@dataclass(frozen=True)
class WindowCrop:
    y0: int
    x0: int
    filtered: np.ndarray
    fill: float


@dataclass(frozen=True)
class CalibrationFit:
    accepted: bool
    reason: str
    knots: np.ndarray
    probs: np.ndarray
    n_search: int
    marginal_llr: np.ndarray
    heldout_logloss: float | None


def build_site_lookup(geometry: SiteGeometry) -> SiteLookup:
    kind = np.full((TILE_CELLS, TILE_CELLS), -1, np.int16)
    index = np.full((TILE_CELLS, TILE_CELLS), -1, np.int16)
    word = np.asarray(geometry.word_cells_yx, np.int64)
    kind[word[:, 0], word[:, 1]] = 0
    index[word[:, 0], word[:, 1]] = np.arange(word.shape[0], dtype=np.int16)
    extra = np.asarray(geometry.extra_cells_yx, np.int64)
    if extra.size:
        kind[extra[:, 0], extra[:, 1]] = 1
        index[extra[:, 0], extra[:, 1]] = np.arange(
            extra.shape[0], dtype=np.int16)
    kind.setflags(write=False)
    index.setflags(write=False)
    return SiteLookup(kind, index)


def format_reference_values(row: FormatRow, lookup: SiteLookup, page: int,
                            cells_yx: np.ndarray) -> np.ndarray:
    cells = np.asarray(cells_yx, np.int64)
    values = np.full(cells.shape[0], -1, np.int8)
    if cells.size == 0:
        return values
    local_y = cells[:, 0] % TILE_CELLS
    local_x = cells[:, 1] % TILE_CELLS
    classes = lookup.kind[local_y, local_x]
    word_rows = np.flatnonzero(classes == 0)
    if word_rows.size:
        tile_y = cells[word_rows, 0] // TILE_CELLS
        tile_x = cells[word_rows, 1] // TILE_CELLS
        tile_code = tile_y * row.tiles_yx[1] + tile_x
        for code in np.unique(tile_code):
            selected = word_rows[tile_code == code]
            ty, tx = divmod(int(code), row.tiles_yx[1])
            counter = row.tile_counter(page, ty, tx)
            word = pilots.word_values(
                row.seed, (counter,), pilots.PLANE_K)[0]
            values[selected] = word[lookup.index[
                local_y[selected], local_x[selected]]]
    filler_rows = np.flatnonzero(classes == 1)
    if filler_rows.size:
        values[filler_rows] = keystream.bits(
            row.seed, keystream.DOMAIN_FILLER_VALUES, pilots.PLANE_K, page,
            cells[filler_rows, 0], cells[filler_rows, 1]).astype(np.int8)
    return values


def payload_cell_mask(lookup: SiteLookup, cells_yx: np.ndarray) -> np.ndarray:
    cells = np.asarray(cells_yx, np.int64)
    return lookup.kind[cells[:, 0] % TILE_CELLS,
                       cells[:, 1] % TILE_CELLS] < 0


def region_pitch_px(pitch_values: Sequence[float]) -> float:
    return float(np.median(tuple(float(value) for value in pitch_values)))


def window_page_cells(placement: Placement, window_shape_yx: tuple[int, int],
                      page_shape_yx: tuple[int, int]) -> np.ndarray:
    local = np.asarray(placement.local_cells_yx, np.int64)
    mapped = rotated_points(local, window_shape_yx, placement.rot_k)
    mapped = mapped + np.asarray(placement.page_origin_yx, np.int64)
    height, width = page_shape_yx
    inside = ((mapped[:, 0] >= 0) & (mapped[:, 0] < height)
              & (mapped[:, 1] >= 0) & (mapped[:, 1] < width))
    return mapped[inside]


def scan_points_yx(native_affine: tuple[float, ...], frame: Fraction,
                   page_cells_yx: np.ndarray,
                   offsets_px: np.ndarray | None = None) -> np.ndarray:
    terms = compose_from_native(tuple(native_affine), frame)
    matrix = np.asarray(terms, np.float64).reshape(2, 3)
    cells = np.asarray(page_cells_yx, np.float64) + 0.5
    points: np.ndarray = cells @ matrix[:, :2].T + matrix[:, 2]
    if offsets_px is not None:
        points = points + np.asarray(offsets_px, np.float64)
    return points


def points_inside_raster(points_yx: np.ndarray,
                         raster_shape_yx: tuple[int, int]) -> bool:
    points = np.asarray(points_yx, np.float64)
    if not points.size:
        return True
    return not bool(np.any(points[:, 0] < 0.0) or np.any(points[:, 1] < 0.0)
                    or np.any(points[:, 0] > raster_shape_yx[0] - 1)
                    or np.any(points[:, 1] > raster_shape_yx[1] - 1))


def crop_luma(planes: Sequence[np.ndarray], y0: int, y1: int, x0: int,
              x1: int) -> np.ndarray:
    if len(planes) == 1:
        return luma_f32(planes[0][y0:y1, x0:x1])
    return plane_mean_luma_f32(planes[0][y0:y1, x0:x1],
                               planes[1][y0:y1, x0:x1],
                               planes[2][y0:y1, x0:x1])


def _crop_bounds(points: np.ndarray, raster_shape_yx: tuple[int, int],
                 pitch_px: float) -> tuple[int, int, int, int]:
    halo = int(np.ceil(APERTURE_CELLS * pitch_px)) + 2
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(int(raster_shape_yx[0]), int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(int(raster_shape_yx[1]), int(np.ceil(points[:, 1].max())) + halo)
    return y0, x0, y1, x1


def _aperture_px(pitch_px: float) -> int:
    return max(1, int(round(APERTURE_CELLS * pitch_px)))


def window_crop(planes: Sequence[np.ndarray], points_yx: np.ndarray,
                raster_shape_yx: tuple[int, int],
                pitch_px: float) -> WindowCrop:
    points = np.asarray(points_yx, np.float64)
    y0, x0, y1, x1 = _crop_bounds(points, raster_shape_yx, pitch_px)
    raw = crop_luma(planes, y0, y1, x0, x1)
    filtered = ndimage.uniform_filter(raw, size=_aperture_px(pitch_px),
                                      mode="nearest")
    return WindowCrop(y0, x0, filtered, float(np.median(raw)))


def _lattice_indices(coords: np.ndarray, length: int) -> np.ndarray:
    base = np.floor(coords).astype(np.int64)
    nodes = np.unique(np.concatenate((base, base + np.int64(1))))
    return nodes[(nodes >= 0) & (nodes < length)]


def _filtered_lattice(raw: np.ndarray, size: int, rows: np.ndarray,
                      cols: np.ndarray) -> np.ndarray:
    offsets = np.arange(size, dtype=np.int64) - np.int64(size // 2)
    row_idx = np.clip(rows[:, None] + offsets[None, :], 0, raw.shape[0] - 1)
    pass0 = (raw[row_idx, :].sum(axis=1, dtype=np.float64)
             / np.float64(size)).astype(np.float32)
    col_idx = np.clip(cols[:, None] + offsets[None, :], 0, raw.shape[1] - 1)
    sums = pass0[:, col_idx].sum(axis=2, dtype=np.float64)
    return (sums / np.float64(size)).astype(np.float32)


def sampled_window_means(planes: Sequence[np.ndarray], points_yx: np.ndarray,
                         raster_shape_yx: tuple[int, int],
                         pitch_px: float) -> np.ndarray:
    points = np.asarray(points_yx, np.float64)
    y0, x0, y1, x1 = _crop_bounds(points, raster_shape_yx, pitch_px)
    raw = crop_luma(planes, y0, y1, x0, x1)
    size = _aperture_px(pitch_px)
    local = points - np.asarray((y0, x0), np.float64)
    rows = _lattice_indices(local[:, 0], raw.shape[0])
    cols = _lattice_indices(local[:, 1], raw.shape[1])
    if rows.size * size * (raw.shape[1] + cols.size) >= 2 * raw.size:
        filtered = ndimage.uniform_filter(raw, size=size, mode="nearest")
    else:
        filtered = np.zeros(raw.shape, np.float32)
        filtered[np.ix_(rows, cols)] = _filtered_lattice(raw, size, rows, cols)
    return sample_points(WindowCrop(y0, x0, filtered, 0.0), points)


def sample_points(crop: WindowCrop, points_yx: np.ndarray) -> np.ndarray:
    points = np.asarray(points_yx, np.float64)
    local = points - np.asarray((crop.y0, crop.x0), np.float64)
    means = ndimage.map_coordinates(
        crop.filtered, local.T, order=1, cval=crop.fill)
    return np.asarray(means, np.float32)


def window_scores(raw_means: np.ndarray) -> np.ndarray:
    means = np.asarray(raw_means, np.float32)
    midpoint = np.float32(np.median(means))
    spread = max(np.float32(np.abs(means - midpoint).mean()),
                 np.float32(SCORE_SPREAD_FLOOR))
    return (midpoint - means) / spread


def fit_window_calibration(scores: np.ndarray, reference_values: np.ndarray,
                           page_cells_yx: np.ndarray) -> CalibrationFit:
    cells = np.asarray(page_cells_yx, np.int64)
    labels = np.asarray(reference_values, np.int8)
    known = labels >= 0
    parity = site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    search = known & ~parity
    heldout = known & parity
    search_labels = labels[search]
    n_search_1 = int(search_labels.sum())
    n_search_0 = int(search_labels.size - n_search_1)
    empty_nodes = np.zeros(0, np.float64)
    empty_llr = np.zeros(0, np.float32)
    if min(n_search_0, n_search_1) < CAL_MIN_PER_CLASS:
        return CalibrationFit(False, "search_class_starved", empty_nodes,
                              empty_nodes, 0, empty_llr, None)
    n_heldout = int(np.count_nonzero(heldout))
    if n_heldout < CAL_MIN_HELDOUT:
        return CalibrationFit(False, "heldout_starved", empty_nodes,
                              empty_nodes, 0, empty_llr, None)
    knots, probs = pava._pava_nodes(scores[search], search_labels)
    marginal = np.asarray(calibration_llr(scores, knots, probs), np.float32)
    heldout_probability = calibration_probability(
        scores[heldout], knots, probs)
    loss = probability_logloss(heldout_probability, labels[heldout])
    return CalibrationFit(True, "accepted", knots, probs,
                          int(search_labels.size), marginal, loss)


def window_evidence(placement: Placement, page_cells_yx: np.ndarray,
                    scores: np.ndarray,
                    reference_values: np.ndarray) -> WindowEvidence:
    """Scores plus proven labels -> one window's black-and-white evidence.

    The seam every K-grade read shares: fit the PAVA score-to-probability
    map on the window's own site-parity split, then carry the fit and its
    held-out loss in a `WindowEvidence`.  `_sample_and_fit` reaches it
    with means read off a raster; `plugins/plane_k` reaches it with a
    synthetic plane-isolated channel.  Neither restates the fit.
    """
    fit = fit_window_calibration(scores, reference_values, page_cells_yx)
    return _evidence(placement, page_cells_yx, scores, reference_values, fit)


def _evidence(placement: Placement, page_cells_yx: np.ndarray,
              scores: np.ndarray, reference_values: np.ndarray,
              fit: CalibrationFit) -> WindowEvidence:
    return WindowEvidence(
        window_id=placement.window_id,
        capture_id=placement.capture_id,
        level_index=placement.level_index,
        region_index=placement.region_index,
        patch_ordinal=placement.patch_ordinal,
        page=placement.page,
        page_cells_yx=np.asarray(page_cells_yx, np.int32),
        scores=np.asarray(scores, np.float32),
        reference_values=np.asarray(reference_values, np.int8),
        knots=fit.knots,
        probs=fit.probs,
        n_search=fit.n_search,
        marginal_llr=fit.marginal_llr,
        printed_llr=fit.marginal_llr,
        accepted=fit.accepted,
        refusal_reason="" if fit.accepted else fit.reason,
        heldout_logloss=fit.heldout_logloss,
        ctx_adopted=False)


def _refused_outside(placement: Placement) -> WindowEvidence:
    empty_nodes = np.zeros(0, np.float64)
    empty_llr = np.zeros(0, np.float32)
    fit = CalibrationFit(False, "outside_raster", empty_nodes, empty_nodes,
                         0, empty_llr, None)
    return _evidence(placement, np.zeros((0, 2), np.int64),
                     np.zeros(0, np.float32), np.zeros(0, np.int8), fit)


def calibrate_window(planes: Sequence[np.ndarray], placement: Placement,
                     window_shape_yx: tuple[int, int], row: FormatRow,
                     lookup: SiteLookup, pitch_px: float, frame: Fraction,
                     offsets_px: np.ndarray | None = None) -> WindowEvidence:
    page_cells = window_page_cells(placement, window_shape_yx, row.cells_yx)
    return _sample_and_fit(planes, placement, page_cells, row, lookup,
                           pitch_px, frame, offsets_px, None)


def resample_window(planes: Sequence[np.ndarray], placement: Placement,
                    evidence: WindowEvidence, row: FormatRow,
                    lookup: SiteLookup, pitch_px: float, frame: Fraction,
                    offsets_px: np.ndarray | None = None) -> WindowEvidence:
    page_cells = np.asarray(evidence.page_cells_yx, np.int64)
    return _sample_and_fit(planes, placement, page_cells, row, lookup,
                           pitch_px, frame, offsets_px,
                           evidence.reference_values)


def _sample_and_fit(planes: Sequence[np.ndarray], placement: Placement,
                    page_cells_yx: np.ndarray, row: FormatRow,
                    lookup: SiteLookup, pitch_px: float, frame: Fraction,
                    offsets_px: np.ndarray | None,
                    reference_values: np.ndarray | None) -> WindowEvidence:
    points = scan_points_yx(placement.native_affine, frame, page_cells_yx,
                            offsets_px)
    raster_shape_yx = (int(planes[0].shape[0]), int(planes[0].shape[1]))
    if not points_inside_raster(points, raster_shape_yx):
        return _refused_outside(placement)
    scores = window_scores(sampled_window_means(planes, points,
                                                raster_shape_yx, pitch_px))
    labels = (format_reference_values(row, lookup, placement.page,
                                      page_cells_yx)
              if reference_values is None
              else np.asarray(reference_values, np.int8))
    return window_evidence(placement, page_cells_yx, scores, labels)


def context_neighbour_counts(page_cells_yx: np.ndarray,
                             provisional_ink: np.ndarray,
                             ) -> tuple[np.ndarray, np.ndarray]:
    cells = np.asarray(page_cells_yx, np.int64)
    ink = np.asarray(provisional_ink).ravel().astype(bool)
    if cells.shape[0] == 0:
        return np.zeros(0, np.int8), np.zeros(0, bool)
    if np.unique(cells, axis=0).shape[0] != cells.shape[0]:
        raise ValueError("calibrate: window repeats a page cell")
    lo = cells.min(axis=0)
    local = cells - lo
    shape = tuple((local.max(axis=0) + 1).astype(int))
    present = np.zeros(shape, np.uint8)
    ink_grid = np.zeros(shape, np.uint8)
    present[local[:, 0], local[:, 1]] = 1
    ink_grid[local[:, 0], local[:, 1]] = ink.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    neighbours_present = ndimage.convolve(
        present, kernel, mode="constant", cval=0)
    neighbours_ink = ndimage.convolve(
        ink_grid, kernel, mode="constant", cval=0)
    row_y, row_x = local[:, 0], local[:, 1]
    return (neighbours_ink[row_y, row_x].astype(np.int8),
            neighbours_present[row_y, row_x] == 8)


def apply_context_offsets(llr: np.ndarray, bins: np.ndarray,
                          offsets: np.ndarray) -> np.ndarray:
    out = np.array(llr, dtype=np.float64, copy=True)
    valid = bins >= 0
    out[valid] = np.clip(out[valid] + offsets[bins[valid]],
                         -CTX_LLR_CLAMP, CTX_LLR_CLAMP)
    return out


def physical_cell_ids(rows: Sequence[WindowEvidence]) -> tuple[np.ndarray, ...]:
    pages = np.concatenate([
        np.full(row.page_cells_yx.shape[0], row.page, np.int64)
        for row in rows])
    cells = np.concatenate([
        np.asarray(row.page_cells_yx, np.int64) for row in rows])
    if pages.size == 0:
        return tuple(np.zeros(0, np.int64) for _row in rows)
    page_low = int(pages.min())
    y_low = int(cells[:, 0].min())
    x_low = int(cells[:, 1].min())
    range_y = int(cells[:, 0].max()) - y_low + 1
    range_x = int(cells[:, 1].max()) - x_low + 1
    keys = (((pages - page_low) * range_y + (cells[:, 0] - y_low))
            * range_x + (cells[:, 1] - x_low))
    ids = np.searchsorted(np.unique(keys), keys).astype(np.int64, copy=False)
    stops = np.cumsum([row.page_cells_yx.shape[0] for row in rows])
    starts = np.concatenate((np.asarray([0]), stops[:-1]))
    return tuple(ids[int(start):int(stop)]
                 for start, stop in zip(starts, stops, strict=True))


def site_weights(site_ids: np.ndarray) -> np.ndarray:
    _unique, inverse, multiplicity = np.unique(
        site_ids, return_inverse=True, return_counts=True)
    return 1.0 / multiplicity[inverse].astype(np.float64)


def unique_class_support(labels: np.ndarray,
                         site_ids: np.ndarray) -> tuple[int, int]:
    _unique, first = np.unique(site_ids, return_index=True)
    unique_labels = labels[first]
    n1 = int(unique_labels.sum())
    return int(unique_labels.size - n1), n1


def _check_site_labels(site_ids: np.ndarray, labels: np.ndarray) -> None:
    order = np.argsort(site_ids, kind="stable")
    sorted_ids = site_ids[order]
    sorted_labels = labels[order]
    if np.any((sorted_ids[1:] == sorted_ids[:-1])
              & (sorted_labels[1:] != sorted_labels[:-1])):
        raise ValueError("calibrate: one context site has conflicting labels")


def context_decision(
    search: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    validation: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> tuple[np.ndarray, bool, str, float | None, float | None]:
    search_llr, search_counts, search_labels, search_ids = search
    valid_llr, valid_counts, valid_labels, valid_ids = validation
    _check_site_labels(search_ids, search_labels)
    _check_site_labels(valid_ids, valid_labels)
    n_s0, n_s1 = unique_class_support(search_labels, search_ids)
    n_v0, n_v1 = unique_class_support(valid_labels, valid_ids)
    zeros = np.zeros(N_CONTEXT_BINS, np.float64)
    if n_s0 + n_s1 < CTX_MIN_SEARCH:
        return zeros, False, "insufficient_search_support", None, None
    if min(n_s0, n_s1) < CTX_MIN_SEARCH_PER_CLASS:
        return zeros, False, "search_class_starved", None, None
    if n_v0 + n_v1 < CTX_MIN_VALIDATION:
        return zeros, False, "insufficient_validation_support", None, None
    if min(n_v0, n_v1) < CTX_MIN_VALIDATION_PER_CLASS:
        return zeros, False, "validation_class_starved", None, None
    offsets = pava._ordered_context_offsets(
        search_llr, search_counts, search_labels, site_weights(search_ids))
    valid_weights = site_weights(valid_ids)
    baseline = pava._binary_logloss(valid_llr, valid_labels, valid_weights)
    candidate = pava._binary_logloss(
        valid_llr + offsets[valid_counts], valid_labels, valid_weights)
    adopted = bool(candidate < baseline)
    return (offsets, adopted,
            "adopted" if adopted else "validation_gate_failed",
            baseline, candidate)


def _empty_side() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return (np.zeros(0, np.float64), np.zeros(0, np.int8),
            np.zeros(0, bool), np.zeros(0, np.int64))


def _pool(parts: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not parts:
        return _empty_side()
    return (np.concatenate([np.asarray(part[0], np.float64)
                            for part in parts]),
            np.concatenate([np.asarray(part[1], np.int8) for part in parts]),
            np.concatenate([np.asarray(part[2], np.uint8)
                            for part in parts]).astype(bool),
            np.concatenate([np.asarray(part[3], np.int64) for part in parts]))


def _corrected_row(row: WindowEvidence, marginal: np.ndarray,
                   bins: np.ndarray,
                   offsets: np.ndarray) -> WindowEvidence:
    corrected = apply_context_offsets(marginal, bins, offsets)
    cells = np.asarray(row.page_cells_yx, np.int64)
    heldout = (site_parity(cells[:, 0], cells[:, 1]).astype(bool)
               & (row.reference_values >= 0))
    loss = pava._binary_logloss(corrected[heldout],
                                row.reference_values[heldout])
    return replace(row, printed_llr=np.asarray(corrected, np.float32),
                   heldout_logloss=loss, ctx_adopted=True)


def apply_standing_context(row: WindowEvidence,
                           ctx: RegionCtx) -> WindowEvidence:
    marginal = np.asarray(
        calibration_llr(row.scores, row.knots, row.probs), np.float64)
    counts, valid = context_neighbour_counts(row.page_cells_yx,
                                             marginal > 0.0)
    bins = np.where(valid, counts, -1).astype(np.int8)
    return _corrected_row(row, marginal, bins,
                          np.asarray(ctx.offsets, np.float64))


def apply_region_context(
    rows: Sequence[WindowEvidence],
    label_rows: Sequence[WindowEvidence] = (),
) -> tuple[tuple[WindowEvidence, ...], RegionCtx]:
    base = tuple(rows)
    all_rows = (*base, *tuple(label_rows))
    all_ids = physical_cell_ids(all_rows)
    merged = sorted(
        ((position if position < len(base) else None, all_rows[position],
          all_ids[position]) for position in range(len(all_rows))),
        key=lambda entry: entry[1].patch_ordinal)
    fitted: list[tuple[int, WindowEvidence, np.ndarray, np.ndarray]] = []
    search_parts: list[
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    validation_parts: list[
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    for index, row, ids in merged:
        if not row.accepted:
            continue
        marginal = np.asarray(
            calibration_llr(row.scores, row.knots, row.probs), np.float64)
        counts, valid = context_neighbour_counts(
            row.page_cells_yx, marginal > 0.0)
        cells = np.asarray(row.page_cells_yx, np.int64)
        known = row.reference_values >= 0
        heldout = site_parity(cells[:, 0], cells[:, 1]).astype(bool)
        search = known & ~heldout & valid
        validation = known & heldout & valid
        if search.any():
            search_parts.append((marginal[search], counts[search],
                                 row.reference_values[search], ids[search]))
        if validation.any():
            validation_parts.append(
                (marginal[validation], counts[validation],
                 row.reference_values[validation], ids[validation]))
        if index is not None:
            bins = np.where(valid, counts, -1).astype(np.int8)
            fitted.append((index, row, marginal, bins))
    if not fitted:
        return base, _region_ctx(base[0], np.zeros(N_CONTEXT_BINS, np.float64),
                                 False, "no_accepted_windows")
    offsets, adopted, reason, _baseline, candidate = context_decision(
        _pool(search_parts), _pool(validation_parts))
    ctx = _region_ctx(base[0], offsets, adopted, reason, candidate)
    if not adopted:
        return base, ctx
    out = list(base)
    for index, row, marginal, bins in fitted:
        out[index] = _corrected_row(row, marginal, bins, offsets)
    return tuple(out), ctx


def _region_ctx(row: WindowEvidence, offsets: np.ndarray, adopted: bool,
                reason: str,
                validation_logloss: float | None = None) -> RegionCtx:
    return RegionCtx(row.capture_id, row.level_index, row.region_index,
                     offsets, adopted, reason, validation_logloss)


def freeze_owners(rows: Sequence[WindowEvidence],
                  page_shape_yx: tuple[int, int], lookup: SiteLookup,
                  capture_id: str, level_index: int,
                  plane: str = PLANE_TAG_K) -> tuple[OwnedPageEvidence, ...]:
    candidates: list[
        tuple[int, int, np.ndarray, np.ndarray, np.ndarray]] = []
    order_keys: list[tuple[object, ...]] = []
    for index, row in enumerate(rows):
        if not row.accepted:
            continue
        selected = np.flatnonzero(
            payload_cell_mask(lookup, row.page_cells_yx)).astype(
                np.int32, copy=False)
        if not selected.size:
            continue
        candidates.append((index, row.page, row.page_cells_yx[selected],
                           selected, row.printed_llr[selected]))
        order_keys.append((float(row.heldout_logloss),
                           tuple(int(value) for value in row.window_id[3]),
                           int(row.region_index), plane))
    return tuple(
        OwnedPageEvidence(capture_id, level_index, page, cells,
                          np.asarray(values, np.float32), window_indices)
        for page, cells, values, window_indices, _row_indices
        in freeze_page_owners(candidates, page_shape_yx,
                              order_keys=order_keys))


def window_event(evidence: WindowEvidence) -> CalibrateAdopted:
    return CalibrateAdopted(
        evidence.capture_id,
        f"{evidence.level_index}/{evidence.region_index}"
        f"/patch-{evidence.patch_ordinal}",
        evidence.accepted,
        "accepted" if evidence.accepted else evidence.refusal_reason)


def region_event(ctx: RegionCtx) -> CalibrateAdopted:
    return CalibrateAdopted(
        ctx.capture_id, f"{ctx.level_index}/region-{ctx.region_index}",
        ctx.adopted, ctx.reason)


@dataclass(frozen=True)
class CtxOutcome:
    region_key: RegionKey
    inputs: tuple[WindowEvidence, ...]
    outputs: tuple[WindowEvidence, ...]
    ctx: RegionCtx


def window_job(store: object, wid: WindowId) -> Job | None:
    placement = store.placement(wid)
    if placement is None:
        return None
    pitch_native = store.region_pitch(wid[:3])
    if pitch_native is None:
        return None
    level = store.level(wid[0], wid[1])
    scale = level.scale
    pitch_level = pitch_native / float(scale)
    plane_rasters = store.sampling_planes((wid[0], wid[1]))
    extent = wid[3]
    shape = (extent[2] - extent[0], extent[3] - extent[1])
    row = store.row
    lookup = store.lookup
    standing = store.evidence(wid)

    def job() -> JobResult:
        started = time.thread_time()
        planes = tuple(raster.open() for raster in plane_rasters)
        if standing is not None and standing.page_cells_yx.size:
            evidence = resample_window(
                planes, placement, standing, row, lookup, pitch_level,
                scale)
        else:
            evidence = calibrate_window(
                planes, placement, shape, row, lookup, pitch_level,
                scale)
        return JobResult(
            (evidence,), (window_event(evidence),),
            time.thread_time() - started)

    return job


def prepare_window(store: object, subject: Subject,
                   stage: str) -> Job | None:
    return window_job(store, subject)


def prepare_ctx(store: object, subject: Subject,
                stage: str) -> Job | None:
    key: RegionKey = subject
    rows = tuple(store.evidence(wid) for wid in store.evidences()
                 if wid[:3] == key)
    if not rows:
        return None

    def job() -> JobResult:
        started = time.thread_time()
        outputs, ctx = apply_region_context(rows)
        return JobResult(
            (CtxOutcome(key, rows, outputs, ctx),),
            (region_event(ctx),),
            time.thread_time() - started)

    return job


def _static_stage(name: str) -> "object":
    def stage(store: object, subject: Subject) -> str | None:
        return name

    return stage


def _never(store: object, subject: Subject) -> bool:
    return False


def _window_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if store.row.family is not Family.K:
        return ()
    return (fact.window_id,)


def _window_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    wid: WindowId = subject
    return ((KEY_POSE_AFFINE, wid),
            (KEY_REGION_PITCH, wid[0], wid[1], wid[2]))


def _window_eligible(store: object, subject: Subject) -> bool:
    # the done gate: a window whose whole tile reach is certified in
    # every stream has no cell left to read for anyone
    return (store.placement(subject) is not None
            and not store.window_fully_done(subject))


def _window_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    return CALIBRATE_COST + RUNG_COST * subject[1]


def _ctx_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    return ((fact.capture_id, fact.level_index, fact.region_index),)


def _ctx_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    return tuple((KEY_EVIDENCE_FIT, wid) for wid in store.evidences()
                 if wid[:3] == subject)


def _ctx_eligible(store: object, subject: Subject) -> bool:
    return any(wid[:3] == subject for wid in store.evidences())


def _ctx_cost(store: object, subject: Subject, stage: str,
              attempts: int, last_cost: int) -> int:
    return CALIBRATE_COST + RUNG_COST * subject[1]


CALIBRATE_DESCRIPTOR = PluginDescriptor(
    name="calibrate",
    subject_kind="window",
    born_by=(Placement,),
    subjects_of=_window_subjects,
    reads=_window_reads,
    eligible=_window_eligible,
    stage=_static_stage(STAGE_CALIBRATE),
    cost=_window_cost,
    retire=_never,
    prepare=prepare_window,
    produces=(WindowEvidence,),
    prices=PRICES,
)

CTX_DESCRIPTOR = PluginDescriptor(
    name="ctx",
    subject_kind="region",
    born_by=(WindowEvidence,),
    subjects_of=_ctx_subjects,
    reads=_ctx_reads,
    eligible=_ctx_eligible,
    stage=_static_stage(STAGE_CALIBRATE),
    cost=_ctx_cost,
    retire=_never,
    prepare=prepare_ctx,
    produces=(CtxOutcome,),
    prices=PRICES,
)

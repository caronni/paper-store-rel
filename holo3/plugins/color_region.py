from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Mapping

import numpy as np

from ..data import (
    CalibrateAdopted,
    Certificate,
    ColorCtxPopulation,
    ColorEvidenceRow,
    JobResult,
    Placement,
    PlaneField,
    PlaneRaster,
    PlaneResidual,
    WindowRows,
)
from ..data import WindowId
from ..descriptor import (
    FactKey,
    Job,
    KEY_LANE_POSES,
    KEY_PAGE_CERTS,
    KEY_PLANE_FIELD,
    KEY_POOLED_CTX,
    PluginDescriptor,
    Subject,
)
from ..format import pilots, tile_codec
from ..format.identity import (
    Family,
    FormatRow,
    SiteGeometry,
)
from ..lib import geometry as lib_geometry
from ..lib import plane_field as plane_field_lib
from . import color_model
from . import pose as pose_plugin
from . import color_region_anchor as anchor
from . import color_region_ctx as ctx
from .color_region_head import (
    ColorLaneFit,
    LaneHead,
    OwnerSelection,
    StackConfig,
    evidence_with_divisor,
    fit_region_stack,
    owner_selection,
    window_loss,
)

PLUGIN: str = "color"
STAGE_COLOR: str = "calibrate"
STAGE_COLOR_REFIT: str = "color_refit"
COLOR_COST: int = 15
COLOR_REFIT_COST: int = 160
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_COLOR, COLOR_COST),
                                       (STAGE_COLOR_REFIT, COLOR_REFIT_COST))
TILE: int = pilots.TILE_CELLS
TileKey = tuple[int, int, int, str]
Projection = tuple[np.ndarray, np.ndarray]


@dataclass(frozen=True)
class RegionWindow:
    patch_ordinal: int
    window_id: tuple[str, int, int, tuple[int, int, int, int]]
    page: int
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray
    shape_yx_cells: tuple[int, int]
    affine: anchor.Affine
    pitch_px: float


from .color_sites import (
    cargo_cell_mask,
    cargo_row_indices,
    cargo_site_mask,
    cell_dots_of,
    certified_projection,
    emission_mask,
    suppressed_tile_codes,
)


def build_window_rows(
    row: FormatRow,
    geometry: SiteGeometry,
    window: RegionWindow,
    certificates: Mapping[TileKey, Certificate],
    memo: dict[tuple[int, int, int], Projection | None],
) -> WindowRows:
    cells = np.asarray(window.page_cells_yx, np.int64)
    states, kinds = color_model.reference_states(
        row, geometry, window.page, cells)
    resolved = states.copy()
    bits = np.zeros((resolved.size, 3), np.uint8)
    known = np.zeros((resolved.size, 3), np.bool_)
    furniture = resolved >= 0
    if np.any(furniture):
        bits[furniture] = tile_codec.states_to_planes(
            resolved[furniture])
        known[furniture] = True
    tiles_x = row.tiles_yx[1]
    tile_code = (cells[:, 0] // TILE) * tiles_x + cells[:, 1] // TILE
    for code in np.unique(tile_code):
        ty, tx = divmod(int(code), tiles_x)
        address = (window.page, ty, tx)
        if address not in memo:
            memo[address] = certified_projection(
                row, geometry, window.page, ty, tx, certificates)
        projection = memo[address]
        if projection is None:
            continue
        projected_bits, projected_known = projection
        selected = np.flatnonzero(tile_code == code)
        local_y = cells[selected, 0] % TILE
        local_x = cells[selected, 1] % TILE
        tile_bits = projected_bits[local_y, local_x]
        tile_known = projected_known[local_y, local_x]
        selected_bits = bits[selected]
        selected_bits[tile_known] = tile_bits[tile_known]
        bits[selected] = selected_bits
        known[selected] |= tile_known
    complete = known.all(axis=1)
    if np.any(complete):
        resolved[complete] = tile_codec.planes_to_states(
            bits[complete]).astype(np.int8)
    return WindowRows(
        patch_ordinal=window.patch_ordinal,
        window_id=window.window_id,
        page=window.page,
        local_cells_yx=np.asarray(window.local_cells_yx, np.int64),
        page_cells_yx=cells,
        scan_points_yx=np.asarray(window.scan_points_yx, np.float64),
        states=resolved,
        furniture_kind=kinds,
        known_component_bits=bits,
        known_component_mask=known,
        heldout_logloss=None,
    )


PlaneFields = tuple[PlaneField | None, ...]
# a caller that derives its sampling offsets from cell POSITION is handed
# the rows instead of having to reproduce their order (see row_offsets)
OffsetsOf = Callable[[WindowRows], tuple[np.ndarray | None, ...] | None]


def field_offsets(fields: PlaneFields | None,
                  page_cells_yx: np.ndarray,
                  ) -> tuple[np.ndarray | None, ...] | None:
    """Evaluate a lane-page's standing per-plane fields at these cells.

    Returns the per-plane (N, 2) sampling offsets in dots that
    `features_with_page_fraction` consumes, or None when no plane has a
    standing field — in which case the historical page-fraction residual
    stays in charge, cell for cell.
    """
    if fields is None:
        return None
    entries = tuple(
        None if field is None
        else plane_field_lib.evaluate(field.delta_dots_xy, page_cells_yx,
                                      TILE)
        for field in fields)
    return None if all(entry is None for entry in entries) else entries


def row_offsets(offsets_override: Mapping[
                    int, tuple[np.ndarray | None, ...]] | None,
                fields: PlaneFields | None, rows: WindowRows,
                offsets_of: OffsetsOf | None = None,
                ) -> tuple[np.ndarray | None, ...] | None:
    """The per-plane sampling offsets one window's rows are read at.

    Three tiers, most specific first.  A MAPPING keyed by patch ordinal
    is the historical seam and must align row-for-row with the rows the
    caller knows this window will build.  A CALLABLE is handed the rows
    themselves, so a caller that computes its offsets from cell POSITION
    — an arm fitting a local affine, say — cannot misalign them; it is
    the seam `plugins/swim.py` uses.  With neither, the lane's standing
    plane fields answer, and with no field either the historical
    page-fraction residual stays in charge, cell for cell.
    """
    if offsets_override is not None:
        return offsets_override.get(rows.patch_ordinal)
    if offsets_of is not None:
        return offsets_of(rows)
    return field_offsets(fields, rows.page_cells_yx)


def build_label_rows(
    row: FormatRow,
    geometry: SiteGeometry,
    window: RegionWindow,
) -> WindowRows | None:
    cells = np.asarray(window.page_cells_yx, np.int64)
    states, kinds = color_model.reference_states(
        row, geometry, window.page, cells)
    keep = np.flatnonzero(kinds >= 0)
    if not keep.size:
        return None
    site_states = states[keep]
    return WindowRows(
        patch_ordinal=window.patch_ordinal,
        window_id=window.window_id,
        page=window.page,
        local_cells_yx=np.asarray(
            window.local_cells_yx, np.int64)[keep],
        page_cells_yx=cells[keep],
        scan_points_yx=np.asarray(
            window.scan_points_yx, np.float64)[keep],
        states=site_states,
        furniture_kind=kinds[keep],
        known_component_bits=tile_codec.states_to_planes(site_states),
        known_component_mask=np.ones((keep.size, 3), np.bool_),
        heldout_logloss=None,
    )


def region_job(
    row: FormatRow,
    geometry: SiteGeometry,
    windows: tuple[RegionWindow, ...],
    label_windows: tuple[RegionWindow, ...],
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster],
    certificates: Mapping[TileKey, Certificate],
    config: StackConfig,
    capture_id: str,
    level_index: int,
    offsets_override: Mapping[
        int, tuple[np.ndarray | None, np.ndarray | None,
                   np.ndarray | None]] | None = None,
    pool_rung: str | None = None,
    pooled: ctx.ContextHead | None = None,
    plane_fields: PlaneFields | None = None,
    offsets_of: OffsetsOf | None = None,
) -> JobResult:
    started = time.thread_time()
    covered = tuple(window.patch_ordinal
                    for window in windows + label_windows)
    inputs = build_region_inputs(
        row, geometry, windows, label_windows, planes, certificates,
        capture_id, level_index, offsets_override, plane_fields,
        offsets_of)
    pool_id = inputs.pool_id
    page = inputs.page
    if inputs.fully_certified:
        event = CalibrateAdopted(
            capture=capture_id, pool_id=pool_id, adopted=True,
            reason="fully_certified_pruned")
        pruned = ColorLaneFit(capture_id, level_index, page, covered,
                              False, None)
        return JobResult((pruned,), (event,),
                         time.thread_time() - started)
    payload_rows = inputs.payload_rows
    emission_by_row = inputs.emission_by_row
    stack = fit_region_stack(
        row, inputs.selection, inputs.row_tuple, inputs.base_tuple,
        inputs.corrected, emission_by_row, config, pooled=pooled,
        publish_labels=pool_rung is not None)
    if stack.selected is None:
        event = CalibrateAdopted(
            capture=capture_id, pool_id=pool_id, adopted=False,
            reason=stack.refusal_reason)
        refused = ColorLaneFit(capture_id, level_index, page, covered,
                               True, None)
        return JobResult((refused,), (event,),
                         time.thread_time() - started)
    fit = stack.selected
    facts: list[object] = []
    for ordinal, (rows, emit) in enumerate(
            zip(payload_rows, emission_by_row)):
        if not np.any(emit):
            continue
        features = stack.features[ordinal]
        bins = (
            None if stack.context_bins is None
            else stack.context_bins[ordinal][emit])
        values, _divisor_column = evidence_with_divisor(
            fit, features[emit], bins)
        facts.append(ColorEvidenceRow(
            capture_id=capture_id,
            level_index=level_index,
            patch_ordinal=rows.patch_ordinal,
            page=page,
            page_cells_yx=rows.page_cells_yx[emit],
            values=np.asarray(values, np.float32),
            heldout_logloss=window_loss(
                fit.model, rows, features, fit.heldout_loss),
        ))
    if stack.labels is not None and pool_rung is not None:
        facts.append(ColorCtxPopulation(
            capture_id=capture_id,
            level_index=level_index,
            page=page,
            rung=pool_rung,
            keys_pyx=stack.labels.keys_pyx,
            scores=stack.labels.scores,
            states=stack.labels.states,
            kinds=stack.labels.kinds,
            bins=stack.labels.bins,
            search=stack.labels.search))
    facts.append(ColorLaneFit(
        capture_id, level_index, page, covered, True,
        LaneHead(fit, inputs.pitch_px, inputs.divisor, inputs.residuals,
                 stack.adopted)))
    event = CalibrateAdopted(
        capture=capture_id, pool_id=pool_id, adopted=True,
        reason="pooled_head" if stack.pooled_adopted else "accepted")
    return JobResult(
        tuple(facts), (event,), time.thread_time() - started)


@dataclass(frozen=True)
class RegionInputs:
    pool_id: str
    page: int
    fully_certified: bool
    payload_rows: tuple[WindowRows, ...]
    emission_by_row: tuple[np.ndarray, ...]
    row_tuple: tuple[WindowRows, ...]
    base_tuple: tuple[np.ndarray, ...]
    corrected: tuple[np.ndarray, ...] | None
    selection: OwnerSelection
    # the region frame a fit is made in — what a later window must be
    # read through for the head to mean anything (residuals None on a
    # fully certified gather, which has no frame to report)
    pitch_px: float = 0.0
    divisor: float = 1.0
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual] | None = None


def build_region_inputs(
    row: FormatRow,
    geometry: SiteGeometry,
    windows: tuple[RegionWindow, ...],
    label_windows: tuple[RegionWindow, ...],
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster],
    certificates: Mapping[TileKey, Certificate],
    capture_id: str,
    level_index: int,
    offsets_override: Mapping[
        int, tuple[np.ndarray | None, np.ndarray | None,
                   np.ndarray | None]] | None = None,
    plane_fields: PlaneFields | None = None,
    offsets_of: OffsetsOf | None = None,
) -> RegionInputs:
    page = windows[0].page
    ordered = tuple(sorted(
        windows, key=lambda window: window.patch_ordinal))
    labels_ordered = tuple(sorted(
        label_windows, key=lambda window: window.patch_ordinal))
    pool_id = f"{PLUGIN}/{capture_id[:12]}/l{level_index:02d}/p{page}"
    suppressed = suppressed_tile_codes(row, certificates, page)
    site_mask = cargo_site_mask(geometry)
    emits = tuple(
        emission_mask(row, window.page_cells_yx, suppressed)
        for window in ordered)
    opens = tuple(
        bool(np.any(
            cargo_cell_mask(site_mask, window.page_cells_yx) & emit))
        for window, emit in zip(ordered, emits))
    if not any(opens):
        return RegionInputs(pool_id, page, True, (), (), (), (), None,
                            owner_selection(()))
    memo: dict[tuple[int, int, int], Projection | None] = {}
    payload_rows: list[WindowRows] = []
    payload_windows: list[RegionWindow] = []
    emission_by_row: list[np.ndarray] = []
    label_rows: list[WindowRows] = []
    label_row_windows: list[RegionWindow] = []
    for window, emit, is_open in zip(ordered, emits, opens):
        if not is_open:
            label = build_label_rows(row, geometry, window)
            if label is not None:
                label_rows.append(label)
                label_row_windows.append(window)
            continue
        payload_rows.append(
            build_window_rows(row, geometry, window, certificates, memo))
        payload_windows.append(window)
        emission_by_row.append(emit)
    for window in labels_ordered:
        label = build_label_rows(row, geometry, window)
        if label is not None:
            label_rows.append(label)
            label_row_windows.append(window)
    row_tuple = tuple(payload_rows) + tuple(label_rows)
    row_windows = tuple(payload_windows) + tuple(label_row_windows)
    pitch_px = float(np.median(tuple(
        window.pitch_px for window in ordered + labels_ordered)))
    plane_arrays: anchor.Planes = (
        planes[0].open(), planes[1].open(), planes[2].open())
    halo = anchor.window_halo(pitch_px)
    crop_windows = {
        window.patch_ordinal: window
        for window in ordered + labels_ordered
    }
    divisor = anchor.native_divisor(tuple(
        anchor.crop_maximum(
            plane_arrays,
            anchor.window_points(window.shape_yx_cells, window.affine),
            halo)
        for window in crop_windows.values()))
    base_tuple = tuple(
        anchor.crop_features(
            anchor.native_crop(
                plane_arrays,
                anchor.window_points(
                    crop_windows[rows.patch_ordinal].shape_yx_cells,
                    crop_windows[rows.patch_ordinal].affine),
                halo),
            rows.scan_points_yx, pitch_px, divisor)
        for rows in row_tuple)
    neighbor_tuple = tuple(
        anchor.neighbor_rows(rows.local_cells_yx)
        for rows in payload_rows)
    cell_dots = cell_dots_of(row)
    cells_y = row.cells_yx[0]
    residuals = anchor.fit_registration(
        plane_arrays, tuple(payload_rows), neighbor_tuple,
        tuple(window.affine for window in payload_windows),
        base_tuple[:len(payload_rows)], cell_dots, cells_y)
    corrected_rows = tuple(
        anchor.features_with_page_fraction(
            plane_arrays, rows, window.affine, residuals, cell_dots,
            cells_y, pitch_px, divisor,
            row_offsets(offsets_override, plane_fields, rows, offsets_of))
        for rows, window in zip(row_tuple, row_windows))
    corrected = (
        None
        if any(entry is None for entry in corrected_rows)
        else tuple(entry for entry in corrected_rows if entry is not None)
    )
    return RegionInputs(
        pool_id=pool_id,
        page=page,
        fully_certified=False,
        payload_rows=tuple(payload_rows),
        emission_by_row=tuple(emission_by_row),
        row_tuple=row_tuple,
        base_tuple=base_tuple,
        corrected=corrected,
        selection=owner_selection(row_tuple),
        pitch_px=pitch_px,
        divisor=divisor,
        residuals=residuals,
    )


def head_features(head: LaneHead, planes: anchor.Planes,
                  rows: WindowRows, window: RegionWindow,
                  cell_dots: int, cells_y: int,
                  plane_fields: PlaneFields | None) -> np.ndarray | None:
    """Sample one window the way the standing head was fitted.

    The frame is the head's; the plane fields are read fresh, because a
    lane's standing field is fire-time truth like its certificates are.
    """
    if head.corrected:
        return anchor.features_with_page_fraction(
            planes, rows, window.affine, head.residuals, cell_dots,
            cells_y, head.pitch_px, head.divisor,
            row_offsets(None, plane_fields, rows))
    return anchor.crop_features(
        anchor.native_crop(
            planes,
            anchor.window_points(window.shape_yx_cells, window.affine),
            anchor.window_halo(head.pitch_px)),
        rows.scan_points_yx, head.pitch_px, head.divisor)


def assembly_job(
    row: FormatRow,
    geometry: SiteGeometry,
    head: LaneHead,
    windows: tuple[RegionWindow, ...],
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster],
    certificates: Mapping[TileKey, Certificate],
    capture_id: str,
    level_index: int,
    plane_fields: PlaneFields | None = None,
) -> JobResult:
    """First evidence for windows the lane has never assembled.

    The standing head is APPLIED, never re-fitted, and the region frame
    rides with it, so these windows are read in the feature space the
    fit was made in. Only the debt windows are sampled — that is what
    makes this the lane's cheap stage. Context bins are counted over
    the debt windows alone, so a cell whose eight neighbours are not
    all in this batch reads with no context offset; the next genuine
    re-fit sees the whole lane and replaces every row written here.

    A fire that fits nothing has no context population to publish and
    no pooled head to weigh: both belong to the fit, and every fit
    still does them.
    """
    started = time.thread_time()
    page = windows[0].page
    ordered = tuple(sorted(
        windows, key=lambda window: window.patch_ordinal))
    pool_id = f"{PLUGIN}/{capture_id[:12]}/l{level_index:02d}/p{page}"
    lane_fit = ColorLaneFit(
        capture_id, level_index, page,
        tuple(window.patch_ordinal for window in ordered), False, None)
    suppressed = suppressed_tile_codes(row, certificates, page)
    site_mask = cargo_site_mask(geometry)
    memo: dict[tuple[int, int, int], Projection | None] = {}
    open_rows: list[WindowRows] = []
    open_windows: list[RegionWindow] = []
    open_emits: list[np.ndarray] = []
    for window in ordered:
        emit = emission_mask(row, window.page_cells_yx, suppressed)
        if not np.any(
                cargo_cell_mask(site_mask, window.page_cells_yx) & emit):
            continue
        open_rows.append(
            build_window_rows(row, geometry, window, certificates, memo))
        open_windows.append(window)
        open_emits.append(emit)
    if not open_rows:
        event = CalibrateAdopted(
            capture=capture_id, pool_id=pool_id, adopted=True,
            reason="assembled_fully_certified")
        return JobResult((lane_fit,), (event,),
                         time.thread_time() - started)
    plane_arrays: anchor.Planes = (
        planes[0].open(), planes[1].open(), planes[2].open())
    cell_dots = cell_dots_of(row)
    cells_y = row.cells_yx[0]
    features = tuple(
        head_features(head, plane_arrays, rows, window, cell_dots, cells_y,
                      plane_fields)
        for rows, window in zip(open_rows, open_windows))
    fit = head.fit
    context_bins: tuple[np.ndarray, ...] | None = None
    if fit.context is not None and all(
            entry is not None for entry in features):
        context_bins = ctx.region_context_bins(
            tuple(open_rows),
            lambda ordinal: evidence_with_divisor(
                fit, features[ordinal], None)[0],
            fit.detector is not None)
    facts: list[object] = []
    for ordinal, (rows, emit) in enumerate(zip(open_rows, open_emits)):
        sampled = features[ordinal]
        if sampled is None or not np.any(emit):
            continue
        bins = (None if context_bins is None
                else context_bins[ordinal][emit])
        values, _divisor_column = evidence_with_divisor(
            fit, sampled[emit], bins)
        facts.append(ColorEvidenceRow(
            capture_id=capture_id,
            level_index=level_index,
            patch_ordinal=rows.patch_ordinal,
            page=page,
            page_cells_yx=rows.page_cells_yx[emit],
            values=np.asarray(values, np.float32),
            heldout_logloss=window_loss(
                fit.model, rows, sampled, fit.heldout_loss),
        ))
    facts.append(lane_fit)
    event = CalibrateAdopted(
        capture=capture_id, pool_id=pool_id, adopted=True,
        reason="assembled")
    return JobResult(
        tuple(facts), (event,), time.thread_time() - started)


def region_window(store: object, wid: WindowId) -> RegionWindow:
    placement = store.placement(wid)
    extent = wid[3]
    shape = (extent[2] - extent[0], extent[3] - extent[1])
    local = np.asarray(placement.local_cells_yx, np.int64)
    mapped = lib_geometry.rotated_points(local, shape, placement.rot_k) \
        + np.asarray(placement.page_origin_yx, np.int64)
    height, width = store.row.cells_yx
    inside = ((mapped[:, 0] >= 0) & (mapped[:, 0] < height)
              & (mapped[:, 1] >= 0) & (mapped[:, 1] < width))
    page_cells = mapped[inside]
    local_cells = local[inside]
    scale = store.level(wid[0], wid[1]).scale
    level_terms = np.asarray(lib_geometry.compose_from_native(
        tuple(placement.native_affine), scale), np.float64).reshape(2, 3)
    rotation, translation = pose_plugin.rotation_affine(
        placement.rot_k, shape)
    linear = level_terms[:, :2] @ rotation
    offset = (level_terms[:, :2]
              @ (translation
                 + np.asarray(placement.page_origin_yx, np.float64)
                 + 0.5)
              + level_terms[:, 2])
    centre = (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
              float(linear[1, 0]), float(linear[1, 1]), float(offset[1]))
    points = anchor.pose_points(centre, local_cells)
    return RegionWindow(
        patch_ordinal=placement.patch_ordinal,
        window_id=wid,
        page=placement.page,
        local_cells_yx=local_cells,
        page_cells_yx=page_cells,
        scan_points_yx=points,
        shape_yx_cells=shape,
        affine=centre,
        pitch_px=placement.pitch_px / float(scale))


def pooled_head_of(store: object,
                   subject: Subject) -> ctx.ContextHead | None:
    cell = store.pooled_color_ctx(pooled_key(store, subject))
    if cell is None or not cell.adopted:
        return None
    return ctx.ContextHead(np.asarray(cell.offsets, np.float64),
                           np.asarray(cell.applied, np.bool_))


def pools_this_lane(store: object) -> bool:
    """A lane publishes its context population, and consults the pooled
    head, only where a second capture could ever pair with it."""
    return store.pooled_ctx_enabled() and len(store.captures()) > 1


def pooled_key(store: object, subject: Subject) -> tuple[int, str]:
    capture_id, level_index, page = subject
    return store.pooled_ctx_key(capture_id, level_index, page)


def prepare_color(store: object, subject: Subject,
                  stage: str) -> Job | None:
    capture_id, level_index, page = subject
    lane = (capture_id, level_index, page)
    wids = store.lane_page_windows(capture_id, level_index, page)
    if not wids:
        return None
    plane_rasters = store.rgb_planes((capture_id, level_index))
    certificates = store.certificates()
    row = store.row
    site_geometry = store.geometry
    fields = store.lane_plane_fields(capture_id, level_index, page)
    head = store.color_lane_head(lane)
    debt = store.color_lane_debt(lane) if stage == STAGE_COLOR else ()
    if head is not None and debt:
        owed = tuple(region_window(store, wid) for wid in debt)

        def assemble() -> JobResult:
            return assembly_job(
                row, site_geometry, head, owed, plane_rasters,
                certificates, capture_id, level_index,
                plane_fields=fields)

        return assemble
    windows = tuple(region_window(store, wid) for wid in wids)
    config = StackConfig()
    pools = pools_this_lane(store)
    pool_rung = pooled_key(store, subject)[1] if pools else None
    pooled = pooled_head_of(store, subject) if pools else None

    def job() -> JobResult:
        return region_job(
            row, site_geometry, windows, (), plane_rasters,
            certificates, config, capture_id, level_index,
            pool_rung=pool_rung, pooled=pooled,
            plane_fields=fields)

    return job


def _color_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if store.row.family is Family.K:
        return ()
    return ((fact.capture_id, fact.level_index, fact.page),)


def _color_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    keys: tuple[FactKey, ...] = ((KEY_LANE_POSES,) + tuple(subject),
                                 (KEY_PAGE_CERTS, subject[2]))
    keys = keys + tuple(
        (KEY_PLANE_FIELD,) + tuple(subject) + (plane,)
        for plane in range(3))
    if not store.pooled_ctx_enabled():
        return keys
    return keys + ((KEY_POOLED_CTX,) + pooled_key(store, subject),)


def _color_eligible(store: object, subject: Subject) -> bool:
    capture_id, level_index, page = subject
    return bool(store.lane_page_windows(capture_id, level_index, page))


def _color_never_retire(store: object, subject: Subject) -> bool:
    return False


def _color_stage(store: object, subject: Subject) -> str | None:
    """Assembly debt is the cheap stage; a settled lane re-fits.

    A window the lane has never assembled is FIRST work, not a re-fit:
    it prices at the assembly rung so it lands ahead of cold placement
    instead of behind it. Only once every placed window is covered does
    a wake mean what the re-fit price is for — fitting the head again,
    over the whole lane, because its evidence, its certificates, its
    plane fields or its pooled head moved.
    """
    if store.color_lane_debt(tuple(subject)):
        return STAGE_COLOR
    return STAGE_COLOR_REFIT


def _color_cost(store: object, subject: Subject, stage: str,
                attempts: int, last_cost: int) -> int:
    """The re-fit ordinal counts head fits, never fires.

    ``attempts`` is the bookmark's fire count, and assembly fires are
    fires — pricing off it would let cheap assembly work escalate the
    price of the fit it never performed. The lane's own count of head
    fits is the ordinal instead, and a lane that has never fitted still
    pays a full first re-fit.
    """
    if stage != STAGE_COLOR_REFIT:
        return COLOR_COST + RUNG_COST * subject[1]
    fits = max(1, store.color_lane_head_fits(tuple(subject)))
    return COLOR_REFIT_COST * fits + RUNG_COST * subject[1]


COLOR_DESCRIPTOR = PluginDescriptor(
    name="color",
    subject_kind="lane",
    born_by=(Placement,),
    subjects_of=_color_subjects,
    reads=_color_reads,
    eligible=_color_eligible,
    stage=_color_stage,
    cost=_color_cost,
    retire=_color_never_retire,
    prepare=prepare_color,
    produces=(ColorEvidenceRow, ColorCtxPopulation, ColorLaneFit),
    prices=PRICES,
)

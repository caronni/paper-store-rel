"""``tiles.uplift`` — the supplemental residue row (arms A3 and A4b).

RECEIVE-DESIGN §6.2a, THE SUPPLEMENTAL-LANE LAW.  v1 scheduled A3 and A4b
as extra LANES appended to the scale plan, bound to the finest ordinary
rung and ranked below every refinement lane.  holo3 has no lane plan, so
the same law lands as one priced, subscribed row: born from a failed
tile, priced above refinement (200) so it drains last, and re-fired by
the ordinary declared reads as poses move and the certified frontier
grows.

MONOTONE BY CONSTRUCTION, structurally and for the same reason v1 was:
this row only ever attempts (address, stream) pairs that carry no
certificate, so it can only ADD certificates.  There is no adoption gate
and no applicability floor; the zero-wrong-certificate audit is the only
bar, and it is the unchanged codec that enforces it — every attempt goes
through ``tiles.attempt_tile`` and every certificate through the same
LDPC syndrome + CRC + format-known re-encode check as an ordinary one.

THE CORRECTION IS TRANSIENT.  The row re-derives the region's colour
evidence under the arm, in memory, uses it for the decoder input, and
throws it away.  It writes no ``ColorEvidenceRow``, mutates no standing
cell, and emits only ``AttemptFact`` and ``Certificate`` — so the
ordinary colour head, the ordinary tile rows and the close are untouched
whatever the arm decides.

ELIGIBILITY.  A3 needs only committed poses and an uncertified residue —
the v0.54 zero-frontier fix: v1's "inherits the R leaf's pre-gates
verbatim" was WRONG for A3, whose reachable set is the residue, not the
frontier.  A4b additionally needs a certified frontier and a multi-stream
coding: it conditions a plane's marginal on its certified SIBLING planes,
so a single-stream coding has nothing to condition on, and a tile with no
certified sibling is a bit-exact no-op.  Both conditions are enforced
per tile inside the fire, so the row attempts exactly the tiles the arm
can move.

GRANULARITY (deviation from the per-tile shape, recorded).  The subject
is the LANE-PAGE, not the tile.  Both arms fit at REGION scale — A3's
maps are fitted toward the region QDA's class means, A4b's strata are
fitted on the region's own calibration population — and neither fit
depends on which tile is being attempted.  A per-tile subject would pay
one full region derivation (raster crop, feature build, QDA fit) per
residue tile for an identical result; on a sheet with hundreds of open
tiles that is a several-hundred-fold cost with no yield.  The row is
still BORN from a failed tile: ``subjects_of`` maps the AttemptFact's own
lanes to lane-page subjects, and the per-tile eligibility the charter
names is applied inside the fire.

PRICING.  The row prices itself, as the engine owns no pricing: A3 at
210 and A4b at 220 (late residue work, after refinement at 200), each
multiplied by its own fire ordinal so a row woken again and again by a
growing frontier drifts behind cheaper work instead of thrashing — the
escalation door, exactly as the colour re-fit uses it.  Nothing caps the
row: it may re-fire as often as new evidence justifies.

NO TUNING SURFACE.  Every constant is the v1 policy value fixed in code
(``color_photometry`` and ``color_conditioning`` carry the provenance).
There is no flag, no environment read and no configuration hatch: the
arm is named by the subject, which is the whole reachability test.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..data import AttemptFact, Certificate, JobResult, PlaneRaster
from ..descriptor import (
    FactKey,
    Job,
    KEY_LANE_POSES,
    KEY_PAGE_CERTS,
    PluginDescriptor,
    Subject,
)
from ..format.identity import FormatRow, SiteGeometry
from ..lib.geometry import TILE_CELLS
from ..lib.owners import freeze_page_owners
from . import color_arms, color_region, tiles
from . import color_region_head

PLUGIN: str = "tiles.uplift"

STAGE_A3: str = tiles.STAGE_UPLIFT_A3
STAGE_A4B: str = tiles.STAGE_UPLIFT_A4B
STAGE_OF_ARM: dict[str, str] = {
    color_arms.UPLIFT_ARM_A3: STAGE_A3,
    color_arms.UPLIFT_ARM_A4B: STAGE_A4B,
}

A3_COST: int = 210
A4B_COST: int = 220
RUNG_COST: int = 2
PRICES: tuple[tuple[str, int], ...] = ((STAGE_A3, A3_COST),
                                       (STAGE_A4B, A4B_COST))


@dataclass(frozen=True)
class LaneWindow:
    window: color_region.RegionWindow
    extent: tuple[int, int, int, int]
    region_index: int


@dataclass(frozen=True)
class UpliftPlan:
    arm: str
    page: int
    capture_id: str
    level_index: int
    lane_windows: tuple[LaneWindow, ...]
    planes: tuple[PlaneRaster, PlaneRaster, PlaneRaster]
    certificates: dict
    targets: tuple[tuple[int, int, tuple[str, ...]], ...]


def _certified_streams(store: object, page: int, ty: int,
                       tx: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    certified: list[str] = []
    pending: list[str] = []
    for stream in store.row.streams:
        if store.has_certificate((page, ty, tx, stream.stream_id)):
            certified.append(stream.stream_id)
        else:
            pending.append(stream.stream_id)
    return tuple(certified), tuple(pending)


def lane_targets(store: object, arm: str, capture_id: str,
                 level_index: int, page: int,
                 wids: tuple) -> tuple[tuple[int, int, tuple[str, ...]], ...]:
    seen: set[tuple[int, int]] = set()
    for wid in wids:
        for cover in store.window_cover_tiles(wid):
            if cover[0] != page:
                continue
            seen.add((cover[1], cover[2]))
    targets: list[tuple[int, int, tuple[str, ...]]] = []
    for ty, tx in sorted(seen):
        certified, pending = _certified_streams(store, page, ty, tx)
        if not pending:
            continue
        if arm == color_arms.UPLIFT_ARM_A4B and not certified:
            continue
        targets.append((ty, tx, pending))
    return tuple(targets)


def _transient_rows(inputs: color_region.RegionInputs,
                    stack: color_region_head.StackResult,
                    ) -> tuple[tuple[int, np.ndarray, np.ndarray, float], ...]:
    fit = stack.selected
    rows: list[tuple[int, np.ndarray, np.ndarray, float]] = []
    for ordinal, (window_rows, emit) in enumerate(
            zip(inputs.payload_rows, inputs.emission_by_row)):
        if not np.any(emit):
            continue
        features = stack.features[ordinal]
        bins = (
            None if stack.context_bins is None
            else stack.context_bins[ordinal][emit])
        certified = (
            np.asarray(window_rows.known_component_mask, np.bool_)
            & (np.asarray(window_rows.furniture_kind, np.int8) < 0)[:, None]
        )[emit]
        values, _divisor = color_region_head.evidence_with_divisor(
            fit, features[emit], bins, certified,
            np.asarray(window_rows.known_component_bits, np.uint8)[emit])
        rows.append((
            int(window_rows.patch_ordinal),
            np.asarray(window_rows.page_cells_yx, np.int64)[emit],
            np.asarray(values, np.float32),
            color_region_head.window_loss(
                fit.model, window_rows, features, fit.heldout_loss),
        ))
    return tuple(rows)


def uplift_cut(row: FormatRow, geometry: SiteGeometry,
               order_of: dict[int, tuple[tuple[int, int, int, int], int]],
               transient: tuple[tuple[int, np.ndarray, np.ndarray, float],
                                ...],
               capture_id: str, level_index: int, page: int, ty: int,
               tx: int) -> tiles.TileCut | None:
    arity = tiles.evidence_arity(row)
    y0 = ty * TILE_CELLS
    x0 = tx * TILE_CELLS
    candidates: list[tuple[int, int, np.ndarray, np.ndarray,
                           np.ndarray]] = []
    order_keys: list[tuple[object, ...]] = []
    index = 0
    for patch_ordinal, page_cells, values, loss in transient:
        indices = color_region.cargo_row_indices(geometry, page_cells)
        cells = page_cells[indices]
        cell_values = values[indices]
        inside = ((cells[:, 0] >= y0) & (cells[:, 0] < y0 + TILE_CELLS)
                  & (cells[:, 1] >= x0) & (cells[:, 1] < x0 + TILE_CELLS))
        if not np.any(inside):
            index += 1
            continue
        candidates.append((index, page, cells[inside],
                           np.flatnonzero(inside),
                           cell_values[inside].reshape(-1, arity)))
        extent, region_index = order_of[patch_ordinal]
        order_keys.append((loss, extent, region_index, 0))
        index += 1
    if not candidates:
        return None
    owned = freeze_page_owners(candidates, row.cells_yx, order_keys)
    if not owned:
        return None
    _page, cells, values, _windows, _rows = owned[0]
    cell_y = cells[:, 0].astype(np.int64)
    cell_x = cells[:, 1].astype(np.int64)
    flat = ((cell_y % TILE_CELLS) * TILE_CELLS
            + (cell_x % TILE_CELLS)).astype(np.uint16)
    return tiles.TileCut(capture_id, level_index, page, ty, tx,
                         np.asarray(values, np.float32), flat)


def uplift_job(row: FormatRow, geometry: SiteGeometry,
               plan: UpliftPlan) -> JobResult:
    started = time.thread_time()
    stage = STAGE_OF_ARM[plan.arm]
    windows = tuple(entry.window for entry in plan.lane_windows)
    order_of = {
        int(entry.window.patch_ordinal): (entry.extent, entry.region_index)
        for entry in plan.lane_windows}
    inputs = color_region.build_region_inputs(
        row, geometry, windows, (), plan.planes, plan.certificates,
        plan.capture_id, plan.level_index)
    if inputs.fully_certified:
        return JobResult((), (), time.thread_time() - started)
    stack, _verdict = color_arms.fit_region_stack_arm(
        row, inputs, color_region_head.StackConfig(), plan.arm)
    if stack.selected is None:
        return JobResult((), (), time.thread_time() - started)
    transient = _transient_rows(inputs, stack)
    facts: list[object] = []
    events: list[object] = []
    for ty, tx, pending in plan.targets:
        cut = uplift_cut(row, geometry, order_of, transient,
                         plan.capture_id, plan.level_index, plan.page, ty,
                         tx)
        if cut is None:
            continue
        for stream_id in pending:
            result = tiles.attempt_tile(row, geometry, (cut,), stream_id,
                                        stage)
            facts.append(result.fact)
            if result.certificate is not None:
                facts.append(result.certificate)
            events.append(result.event)
    return JobResult(tuple(facts), tuple(events),
                     time.thread_time() - started)


def prepare_uplift(store: object, subject: Subject,
                   stage: str) -> Job | None:
    capture_id, level_index, page, arm = subject
    wids = store.lane_page_windows(capture_id, level_index, page)
    if not wids:
        return None
    targets = lane_targets(store, arm, capture_id, level_index, page, wids)
    if not targets:
        return None
    lane_windows = tuple(
        LaneWindow(color_region.region_window(store, wid), wid[3],
                   int(store.window(wid).region_index))
        for wid in wids)
    plan = UpliftPlan(
        arm=arm,
        page=page,
        capture_id=capture_id,
        level_index=level_index,
        lane_windows=lane_windows,
        planes=store.rgb_planes((capture_id, level_index)),
        certificates=store.certificates(),
        targets=targets,
    )
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        return uplift_job(row, site_geometry, plan)

    return job


def _uplift_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    arms = color_arms.arms_for_family(store.row.family)
    if not arms or fact.outcome == tiles.OUTCOME_CERTIFIED:
        return ()
    if store.has_certificate(
            (fact.page, fact.ty, fact.tx, fact.stream_id)):
        return ()
    subjects: list[Subject] = []
    for capture_id, level_index in fact.components:
        for arm in arms:
            subjects.append((capture_id, level_index, fact.page, arm))
    return tuple(dict.fromkeys(subjects))


def _uplift_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    capture_id, level_index, page, _arm = subject
    return ((KEY_LANE_POSES, capture_id, level_index, page),
            (KEY_PAGE_CERTS, page))


def _uplift_eligible(store: object, subject: Subject) -> bool:
    capture_id, level_index, page, _arm = subject
    if not store.lane_page_windows(capture_id, level_index, page):
        return False
    return not bool(store.done_grid(page).all())


def _uplift_retire(store: object, subject: Subject) -> bool:
    return not _uplift_eligible(store, subject)


def _uplift_stage(store: object, subject: Subject) -> str | None:
    return STAGE_OF_ARM[subject[3]]


def _uplift_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    if stage == STAGE_A3:
        base = A3_COST * attempts if attempts else A3_COST
    else:
        base = A4B_COST * attempts if attempts else A4B_COST
    return base + RUNG_COST * subject[1]


UPLIFT_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="lane",
    born_by=(AttemptFact,),
    subjects_of=_uplift_subjects,
    reads=_uplift_reads,
    eligible=_uplift_eligible,
    stage=_uplift_stage,
    cost=_uplift_cost,
    retire=_uplift_retire,
    prepare=prepare_uplift,
    produces=(AttemptFact, Certificate),
    prices=PRICES,
)

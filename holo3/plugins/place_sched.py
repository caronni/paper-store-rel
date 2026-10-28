from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .. import data
from ..data import WindowId
from ..descriptor import (
    FactKey,
    Job,
    KEY_LATTICE_SEED,
    KEY_LIVE_PAGES,
    KEY_POSE_AFFINE,
    PluginDescriptor,
    Subject,
)
from . import place, words

WORD_STAGE_OF: dict[str, str] = {
    place.STAGE_WORD_CENTRE: words.STAGE_CENTRE,
    place.STAGE_WORD_REST: words.STAGE_REST,
}

RETIRE_PLACED: str = "placed"
RETIRE_EXHAUSTED: str = "exhausted"
RETIRE_DONE: str = "done_covered"
# not a clause: the name the engine writes if it is ever asked for a
# cause while no clause stands.  It cannot happen on the one production
# path (`engine._fill` retires only where `descriptor.retire` just said
# yes, in the same thread, with no ingest between), and a run that emits
# it is reporting a bug rather than hiding one behind an empty string.
RETIRE_UNKNOWN: str = "unknown"


@dataclass
class WindowState:
    window: data.Window
    tried: set[str] = field(default_factory=set)
    centre_spent: bool = False
    rest_spent: bool = False
    wide_spent: bool = False
    cold_armed: bool = False
    cold_live_spent: bool = False
    cold_rest_spent: bool = False
    subdivided: bool = False
    afterlife_used: bool = False
    dormant_since: int | None = None
    placed: bool = False
    retired: bool = False
    parent: WindowId | None = None
    children: tuple[WindowId, ...] = ()


@dataclass(frozen=True)
class PlaceOutcome:
    window_id: WindowId
    result: place.WindowPassResult


def anchors_of(store: object, wid: WindowId) -> tuple[place.AnchorPose, ...]:
    capture_id, _level, region_index, _extent = wid
    rows: list[place.AnchorPose] = []
    for owid in store.placements():
        if owid[0] != capture_id or owid[2] != region_index:
            continue
        placement = store.placement(owid)
        generation = store.pose_generation(owid)
        ordinal = store.window(owid).ordinal
        rows.append(place.AnchorPose(
            f"pose/{owid[1]}/{ordinal}/g{generation}", owid[3],
            placement.page, tuple(placement.native_affine)))
    rows.sort(key=lambda anchor: anchor.pose_id)
    return tuple(rows)


def untried_consult(store: object, state: WindowState,
                    wide: bool) -> tuple[place.Seed, ...]:
    wid = state.window.window_id
    anchors = anchors_of(store, wid)
    seeds = list(place.consult_seeds(state.window.extent_cells, anchors,
                                     store.page_domain, wide))
    if wide:
        frame = store.frame(wid[:3])
        if frame is not None:
            regional = place.regional_seed(frame, anchors,
                                           store.page_domain)
            if regional is not None:
                seeds.append(regional)
    return tuple(seed for seed in seeds
                 if seed.candidate_id not in state.tried)


def cold_pages_of(store: object, state: WindowState,
                  flavour: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    pages = place.cold_flavour_pages(store.page_domain, flavour,
                                     store.live_pages())
    untried = tuple(page for page in pages
                    if place.cold_tried_id(page, flavour) not in state.tried)
    return pages, untried


def dormant(store: object, state: WindowState, wid: WindowId) -> bool:
    return (state.dormant_since is not None
            and store.worker_version("place", wid) == state.dormant_since)


def ladder_stage(store: object, state: WindowState,
                 wid: WindowId) -> str | None:
    if state.placed or state.retired or dormant(store, state, wid):
        return None
    offered = bool(untried_consult(store, state, wide=False))
    live_all, _live_untried = cold_pages_of(store, state,
                                            place.STAGE_COLD_LIVE)
    rest_all, _rest_untried = cold_pages_of(store, state,
                                            place.STAGE_COLD_REST)
    return place.stage_of(offered, state.centre_spent, state.rest_spent,
                          state.wide_spent, state.cold_armed,
                          bool(live_all), state.cold_live_spent,
                          bool(rest_all), state.cold_rest_spent)


def ring_pass_job(store: object, state: WindowState, stage: str | None,
                  wide: bool, cold_flavour: str | None,
                  cold_pages: tuple[int, ...],
                  seeds: tuple[place.Seed, ...],
                  cold_h_pages: int = 0) -> Job | None:
    wid = state.window.window_id
    frame = store.frame(wid[:3])
    if frame is None:
        return None
    window = state.window
    lattice = store.lattice_seed(wid[:3])
    lattice_rows = (None if lattice is None else tuple(
        float(value) for value in
        np.asarray(lattice.rows, np.float64).ravel()))
    plane_rasters = store.sampling_planes((wid[0], wid[1]))
    row = store.row
    reference = store.reference
    page_domain = store.page_domain
    tried_count = len(state.tried)
    ordinal = window.ordinal

    def job() -> data.JobResult:
        started = time.thread_time()
        planes = tuple(raster.open() for raster in plane_rasters)
        result = place.run_window_pass(place.WindowPass(
            window=window, frame=frame, planes=planes, row=row,
            reference=reference, page_domain=page_domain, stage=stage,
            wide=wide, cold_flavour=cold_flavour, cold_pages=cold_pages,
            seeds=seeds, tried_count=tried_count,
            lattice_seed=lattice_rows, patch_ordinal=ordinal,
            cold_h_pages=cold_h_pages))
        facts: list[object] = []
        if result.placement is not None:
            facts.append(result.placement)
        if result.lattice_seed is not None:
            facts.append(result.lattice_seed)
        facts.append(PlaceOutcome(wid, result))
        return data.JobResult(tuple(facts), result.events,
                              time.thread_time() - started)

    return job


def prepare_place(store: object, subject: Subject, stage: str) -> Job | None:
    wid: WindowId = subject
    state = store.place_stage(wid)
    if state is None or state.placed or state.retired \
            or dormant(store, state, wid):
        return None
    frame = store.frame(wid[:3])
    if frame is None:
        return None
    word_stage = WORD_STAGE_OF.get(stage)
    wide = stage == place.STAGE_WIDE
    seeds: tuple[place.Seed, ...] = ()
    cold_flavour: str | None = None
    cold_pages: tuple[int, ...] = ()
    cold_h_pages = 0
    if stage == place.STAGE_RING:
        seeds = untried_consult(store, state, wide=False)
    elif wide:
        seeds = untried_consult(store, state, wide=True)
    elif stage in place.COLD_STAGES:
        cold_flavour = stage
        all_pages, cold_pages = cold_pages_of(store, state, stage)
        cold_h_pages = len(all_pages)
    return ring_pass_job(store, state, word_stage, wide, cold_flavour,
                         cold_pages, seeds, cold_h_pages)


def worker_stage(store: object, subject: Subject) -> str | None:
    state = store.place_stage(subject)
    if state is None:
        return None
    return ladder_stage(store, state, subject)


def _place_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    return (fact.window_id,)


def _place_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    capture_id, level_index, region_index, extent = subject
    keys: list[FactKey] = [
        (KEY_LATTICE_SEED, capture_id, level_index, region_index),
        (KEY_LIVE_PAGES,)]
    frame = store.frame((capture_id, level_index, region_index))
    if frame is not None:
        neighbours = place.ring_neighbour_extents(frame.shape_cells, extent)
        capture = store.capture(capture_id)
        for level in capture.levels:
            for other in neighbours:
                keys.append((KEY_POSE_AFFINE, (capture_id, level.index,
                                               region_index, other)))
            if level.index != level_index:
                keys.append((KEY_POSE_AFFINE, (capture_id, level.index,
                                               region_index, extent)))
    return tuple(keys)


def _place_eligible(store: object, subject: Subject) -> bool:
    state = store.place_stage(subject)
    return state is not None and not state.placed and not state.retired


def place_retire_cause(store: object, subject: Subject) -> str | None:
    """The clause that retires this place row, or None while it lives.

    THE DONE GATE'S ONLY DOOR.  `engine._fill` consults `retire` before
    `prepare` at every pop, so a window whose supported extent is already
    certified is retired one line before its pass would have been built:
    the pass never sees a done window and carries no second copy of this
    test.  The clause is returned, not just its truth, because the engine
    stamps it on `WindowRetired` — three different reasons leave the
    frontier through this one event, and only the cause separates a
    done-geometry suppression from an accepted pose.

    Order is `_place_retire`'s own: placed, then exhausted, then done.
    """
    state = store.place_stage(subject)
    if state is None:
        return None
    if state.placed:
        return RETIRE_PLACED
    if state.retired:
        return RETIRE_EXHAUSTED
    if store.window_fully_done(subject):
        return RETIRE_DONE
    return None


def _place_retire(store: object, subject: Subject) -> bool:
    return place_retire_cause(store, subject) is not None


def _place_cost(store: object, subject: Subject, stage: str,
                attempts: int, last_cost: int) -> int:
    window = store.window(subject)
    return place.stage_price(stage, window.lane_depth, window.depth)


PLACE_DESCRIPTOR = PluginDescriptor(
    name="place",
    subject_kind="window",
    born_by=(data.Window,),
    subjects_of=_place_subjects,
    reads=_place_reads,
    eligible=_place_eligible,
    stage=worker_stage,
    cost=_place_cost,
    retire=_place_retire,
    prepare=prepare_place,
    produces=(data.Placement, data.LatticeSeed, PlaceOutcome),
    prices=tuple(place.STAGE_COST.items()),
)

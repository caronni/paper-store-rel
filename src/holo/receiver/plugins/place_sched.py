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
    KEY_PLACE_STAGE,
    KEY_POSE_AFFINE,
    KEY_WINDOW_DONE,
    PluginDescriptor,
    Subject,
)
from . import place, place_pass, words

WORD_STAGE_OF: dict[str, str] = {
    place.STAGE_WORD_CENTRE: words.STAGE_CENTRE,
    place.STAGE_WORD_REST: words.STAGE_REST,
}

RETIRE_PLACED: str = "placed"
RETIRE_EXHAUSTED: str = "exhausted"
# `done_covered` was the third cause until 2026-10-03 and is the
# record's spelling for it (e036's idle run, the J run's 44): the done
# gate SUPPRESSES now, through `worker_stage`, because the pose-free
# projection it reads can shrink under a pose revision and a retirement
# cannot be taken back.


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
    #: The two halves of the quartering: ARMED by a refusal that
    #: quarters on the spot, SUBDIVIDED once the rung has run.  The
    #: lazy path arms nothing -- a spent ladder is its own arming.
    subdivide_armed: bool = False
    subdivided: bool = False
    #: A pass found too little paper under this window
    #: (`insufficient_support`): the ladder is spent but for a
    #: quartering a refusal had already ARMED, which this window still
    #: holds (review 2026-10-17, D1).  The afterlife clears it.
    support_refused: bool = False
    afterlife_used: bool = False
    dormant_since: int | None = None
    placed: bool = False
    retired: bool = False
    parent: WindowId | None = None
    children: tuple[WindowId, ...] = ()
    #: THE AFTERLIFE'S OWN INPUTS, written by the STORE when a child
    #: settles (`store_folds._settle_child`) -- this row never reads
    #: its children, and never subscribed to them.
    children_settled: set[WindowId] = field(default_factory=set)
    child_placed: bool = False


@dataclass(frozen=True)
class PlaceOutcome:
    window_id: WindowId
    result: place_pass.WindowPassResult


# ONE STEER PER ANCHOR WINDOW -- its live pose (ruling I3,
# 2026-08-23): offering a revised anchor twice spends two consult
# slots on one neighbour and weights it twice.  The generation rides
# in the pose id, so a revision reads as a candidate not yet tried.
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


# THE AFTERLIFE IS STILL OWED: this window has children that may yet
# re-arm it COLD over its full extent, so its ladder being spent is
# NOT the end of it.  The one clause NOT here is "every child has
# settled", which is the difference between "not yet" and "never" and
# which the STORE answers, in the child's own fold.
#
# IT READS THE PARENT'S STATE AND NOTHING ELSE (2026-09-21): a child
# that settles is routed to this state by `store_folds._settle_child`,
# so neither this predicate nor the place row ever walks the children
# -- a derived relation is the store's, and the store keeps it here.
#
# `place_retire_cause` reads this because the BOOKMARK is what must
# survive: a retired bookmark is unsubscribed and skipped by `_touch`,
# and nothing inside a fold can bring one back.  `state.retired` stays
# latched meanwhile, so `ladder_stage` short-circuits and the waiting
# row costs one predicate per wake and seats nothing.
def afterlife_owed(state: WindowState) -> bool:
    # A child that PLACED cancels the afterlife for good: the quarter
    # that carries the page is the answer the parent's full extent was
    # going to look for.
    return (not state.afterlife_used and not state.placed
            and bool(state.children) and not state.child_placed)


#: A QUARTERING THAT IS STILL POSSIBLE AND NOT YET DONE -- the rung's
#: whole precondition, and the one rung a sleeping window may take
#: (when its own refusal armed it).
def subdivide_ready(state: WindowState) -> bool:
    return not state.subdivided and place.subdividable(state.window)


# Dormancy is a snapshot of the worker's fact version, not a flag: a
# window whose own fit refused sleeps until something it READS
# changes -- a better lattice seed, a neighbour's pose -- which is
# exactly when a retry could answer differently.
#
# A WINDOW THAT OWES A QUARTERING IS NOT ASLEEP.  `pose_refused` arms
# the subdivision and sleeps in the same fold, and the quartering is
# work this window HOLDS, not work it waits for: until 2026-09-21 the
# fold minted the children on the spot, and the rung that replaced it
# has to be reachable through the sleep or the children never come.
def dormant(store: object, state: WindowState, wid: WindowId) -> bool:
    if state.subdivide_armed and subdivide_ready(state):
        return False
    return (state.dormant_since is not None
            and store.worker_version("place", wid) == state.dormant_since)


# Cold readiness asks the whole PARTITION, not the untried
# remainder: a flavour whose page set is empty is skipped costlessly
# and stays unspent (it may fill later), while one that is offered
# and fully deduped comes back cold_refused_* and IS spent.
def ladder_rung(store: object, state: WindowState,
                wid: WindowId) -> str | None:
    """The rung this window would run next, ASLEEP OR NOT.

    The ladder's own answer, which is what "spent" means: a dormant
    window with rungs left is not spent, and `_settle_ladder` reads
    this one rather than `ladder_stage` for exactly that reason.
    """
    offered = bool(untried_consult(store, state, wide=False))
    live_all, _live_untried = cold_pages_of(store, state,
                                            place.STAGE_COLD_LIVE)
    rest_all, _rest_untried = cold_pages_of(store, state,
                                            place.STAGE_COLD_REST)
    return place.stage_of(offered, state.centre_spent, state.rest_spent,
                          state.wide_spent, state.cold_armed,
                          bool(live_all), state.cold_live_spent,
                          bool(rest_all), state.cold_rest_spent,
                          subdivide_armed=state.subdivide_armed,
                          subdivide_ready=subdivide_ready(state),
                          support_refused=state.support_refused)


def ladder_stage(store: object, state: WindowState,
                 wid: WindowId) -> str | None:
    """And the rung it may run NOW."""
    if state.placed or state.retired or dormant(store, state, wid):
        return None
    return ladder_rung(store, state, wid)


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
        result = place_pass.run_window_pass(place_pass.WindowPass(
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


# THE QUARTERING'S JOB, and it reads no pixels: the four children of
# the parent's extent, then the outcome that marks the parent
# subdivided.  It is a JOB and not a fold because a fold may not create
# facts, and a RUNG and not a pass verdict because the decision needs
# the store at POP time -- a pass prepared at t0 cannot know that a
# seed arrived at t1 (the plan's D1 race, answered by the ladder).
#
# The children are microseconds of arithmetic over the frame's support
# mask; the ordinal base is the lane's plan total plus four per parent
# ordinal, which is disjoint by induction and is a store cell written
# once per lane.  A re-fire cannot mint them twice: the store refuses a
# Window it already holds, and `state.subdivided` retires the rung.
def subdivide_job(store: object, state: WindowState) -> Job | None:
    wid = state.window.window_id
    frame = store.frame(wid[:3])
    if frame is None:
        return None
    window = state.window
    first = store.plan_total(wid[:2]) + window.ordinal * 4

    def job() -> data.JobResult:
        started = time.thread_time()
        facts: list[object] = list(place.child_windows(frame, window, first))
        facts.append(PlaceOutcome(wid, place_pass.subdivided_result()))
        return data.JobResult(tuple(facts), (),
                              time.thread_time() - started)

    return job


# The cold floor prices the FLAVOUR'S PARTITION (cold_h_pages) while
# the sweep is only the untried remainder: pricing H on the
# remainder would let a window burn its partition down and then
# accept at a cheaper floor (src/holo/receiver/docs/PAGE-DOMAIN.md §1).
def prepare_place(store: object, subject: Subject, stage: str) -> Job | None:
    wid: WindowId = subject
    state = store.place_stage(wid)
    if state is None or state.placed or state.retired \
            or dormant(store, state, wid):
        return None
    frame = store.frame(wid[:3])
    if frame is None:
        return None
    if stage == place.STAGE_SUBDIVIDE:
        return subdivide_job(store, state)
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
    """The rung this window may run now, or None -- THE DONE GATE.

    A window every supported cell of whose extent already carries a
    certified tile has nothing left to place, so it has no stage: it
    leaves the frontier and waits at the version floor, the way API.md
    §6b says a pose-sensitive row leaves.  It is NOT retired
    (2026-10-03): an unplaced window is judged on the pose-free
    projection through the region's LATEST adopted poses, a revision
    can shrink that projection, and a retired bookmark can never come
    back.  The store remembers the verdict and emits
    `(KEY_WINDOW_DONE, wid)` when a changed affine re-opens the window,
    which this row reads, so the suppression lifts on the fold that
    lifts it.  The same holds a parent owed its afterlife: it is
    suppressed while done and alive when its last child settles.
    """
    state = store.place_stage(subject)
    if state is None or state.placed:
        return None
    if store.window_fully_done(subject):
        return None
    return ladder_stage(store, state, subject)


def _place_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    return (fact.window_id,)


# The wake set, and it is NARROWER than the consult: a window wakes
# on its region's lattice seed, on any page going live, and on the
# eight ring neighbours at every lane -- but it consults every
# placed window of the region.  A key missing here never wakes.
#
# Its OWN place_stage key is the ladder climb, the subdivision AND the
# afterlife: the fold moves the state and emits that key, and this row
# wakes and prices its next rung.  THE PARENT NEVER SUBSCRIBES TO ITS
# CHILDREN (2026-09-21 amendment).  A child that settles is routed by
# the STORE to its parent's own state, and the key the store emits is
# the parent's -- the one this row has read since birth.  A derived
# relation (who is whose child) is the store's business, and a worker's
# declared reads are FIXED AT BIRTH.
#
# Its OWN window_done key is the done gate lifting (2026-10-03): the
# store emits it when a changed affine re-opens a window it last judged
# done, and `worker_stage` -- where the gate lives -- answers a rung
# again.
#
# That also makes this function a constant of its subject once the
# frame exists, which is why no row re-derives its read set any more.
def _place_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    capture_id, level_index, region_index, extent = subject
    keys: list[FactKey] = [
        (KEY_LATTICE_SEED, capture_id, level_index, region_index),
        (KEY_LIVE_PAGES,),
        (KEY_PLACE_STAGE, subject),
        (KEY_WINDOW_DONE, subject)]
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

    Both causes are MONOTONE, which is what a clause consulted at every
    wake has to be: `placed` and the ladder's latch never go back.  The
    done gate is NOT here since 2026-10-03 -- it suppresses through
    `worker_stage` instead, because the projection it reads can shrink
    under a pose revision.  The clause is returned, not just its truth,
    because the engine stamps it on `WorkerRetired`, and only the cause
    separates an accepted pose from a spent ladder in the record.

    Order: placed, then exhausted.

    EXHAUSTED WAITS ON THE AFTERLIFE.  A window whose ladder ran out
    after it subdivided may still get one cold pass over its full
    extent when the last child settles without a pose, and that pass
    is scheduled by waking this bookmark.  `state.retired` is the
    LADDER's latch and is set on both spent paths; whether the ROW
    goes is this clause's business, and `afterlife_owed` is the one
    predicate that says so.
    """
    state = store.place_stage(subject)
    if state is None:
        return None
    if state.placed:
        return RETIRE_PLACED
    if state.retired and not afterlife_owed(state):
        return RETIRE_EXHAUSTED
    return None


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
    retire=place_retire_cause,
    prepare=prepare_place,
    produces=(data.Placement, data.LatticeSeed, PlaceOutcome),
    prices=tuple(place.STAGE_COST.items()),
)

"""The pooled colour context arm.

One printed page observed by several captures is one channel seen several
times.  The per-(state, plane) context matrix each colour lane fits is a
description of that channel, and a lane whose own labelled population is
thin fits it badly or not at all.  This row fits ONE matrix from every
capture's labels for the same page at the same rung and offers it to each
lane as a candidate; the lane adopts it only when it beats the lane's own
head on the lane's own held-out labels (color_region_head.fit_region_stack).
Nothing here mints or bypasses a certificate.

What is deliberately NOT pooled: the ink map.  Bins stay per capture —
INDEPENDENT-PLANES §2.12 (g) measured a three-capture consensus column at
36/57 % of the oracle against one capture's own 44/64 %, "the ink map has
to describe THAT capture's neighbourhood optics".  Labels stay format
truth plus this run's certificates, never ground truth (§2.10's
circularity finding).
"""
#: Decode-scale evidence, the arm-off control, and the two measured
#: reasons no decode-level tile moved -- one of them being that this sim
#: has no marginal-readout regime: measure/pooled_ctx/README.md.

from __future__ import annotations

import time

import numpy as np

from ..data import (
    CalibrateAdopted,
    ColorCtxPopulation,
    JobResult,
    PooledColorCtx,
)
from ..descriptor import (
    FactKey,
    Job,
    KEY_COLOR_POP,
    PluginDescriptor,
    Subject,
)
from ..format.identity import Family
from . import color_region_head
from . import color_region_ctx as ctx

PLUGIN: str = "color.pooled_ctx"
STAGE_POOLED: str = "pooled_ctx"
POOLED_CTX_COST: int = 170
PRICES: tuple[tuple[str, int], ...] = ((STAGE_POOLED, POOLED_CTX_COST),)

MIN_CAPTURES: int = 2
#: Radix packing of (page, cell_y, cell_x) into one int64 physical-cell
#: key.  Injective only while a page's cell coordinates stay under 2**20
#: -- the widest identity in the tree is 3392x2368 cells.  A collision
#: would silently drop a fit row, never raise.
CELL_KEY_MIX: int = 1 << 20
PAGE_KEY_MIX: int = 1 << 40

REASON_SEARCH_STARVED: str = ctx.REASON_SEARCH_STARVED
REASON_VALIDATION_STARVED: str = ctx.REASON_VALIDATION_STARVED

PooledKey = tuple[int, str]


def packed_keys(keys_pyx: np.ndarray) -> np.ndarray:
    cells = np.asarray(keys_pyx, np.int64)
    return (cells[:, 0] * PAGE_KEY_MIX + cells[:, 1] * CELL_KEY_MIX
            + cells[:, 2])


def fit_rows(packed: np.ndarray, search: np.ndarray) -> np.ndarray:
    """The pooled fit side: rows their own lane fits on, minus every
    physical cell any contributing lane holds out.  No pooled curve is
    ever fitted on a row that gates some lane's own adoption."""
    held = np.unique(packed[~search])
    return search & ~np.isin(packed, held)


def stacked(populations: tuple[ColorCtxPopulation, ...],
            ) -> tuple[np.ndarray, ...]:
    return (
        np.concatenate([np.asarray(row.keys_pyx, np.int64)
                        for row in populations]),
        np.concatenate([np.asarray(row.scores, np.float64)
                        for row in populations]),
        np.concatenate([np.asarray(row.states, np.int64)
                        for row in populations]),
        np.concatenate([np.asarray(row.kinds, np.int8)
                        for row in populations]),
        np.concatenate([np.asarray(row.bins, np.int8)
                        for row in populations]),
        np.concatenate([np.asarray(row.search, np.bool_)
                        for row in populations]),
    )


def refused(page: int, rung: str, reason: str, n_lanes: int,
            n_rows: int, width: int) -> PooledColorCtx:
    return PooledColorCtx(
        page=page, rung=rung,
        offsets=np.zeros((width, 3, ctx.N_CONTEXT_BINS), np.float64),
        applied=np.zeros((width, 3), np.bool_), adopted=False,
        reason=reason, n_lanes=n_lanes, n_rows=n_rows,
        validation_logloss=None)


def pooled_cell(populations: tuple[ColorCtxPopulation, ...], page: int,
                rung: str, cmy8: bool, config: ctx.ContextConfig,
                state_ids: tuple[int, ...] | None = None) -> PooledColorCtx:
    keys, scores, states, kinds, bins, search = stacked(populations)
    n_states = int(scores.shape[1])
    width = n_states if cmy8 else n_states - 1
    n_lanes = len(populations)
    fit_side = fit_rows(packed_keys(keys), search)
    gate_side = ~search
    n_rows = int(np.count_nonzero(fit_side))
    if n_rows < config.min_search:
        return refused(page, rung, REASON_SEARCH_STARVED, n_lanes, n_rows,
                       width)
    if int(np.count_nonzero(gate_side)) < config.min_validation:
        return refused(page, rung, REASON_VALIDATION_STARVED, n_lanes,
                       n_rows, width)
    verdict = ctx.context_verdict(
        ctx.population(scores, states, bins, kinds, fit_side),
        ctx.population(scores, states, bins, kinds, gate_side),
        config, cmy8, (True, True, True), None, state_ids)
    if verdict.head is None:
        return refused(page, rung, verdict.reason, n_lanes, n_rows, width)
    return PooledColorCtx(
        page=page, rung=rung, offsets=verdict.head.offsets,
        applied=verdict.head.applied, adopted=True, reason=verdict.reason,
        n_lanes=n_lanes, n_rows=n_rows,
        validation_logloss=verdict.validation_logloss)


def pooled_event(cell: PooledColorCtx) -> CalibrateAdopted:
    return CalibrateAdopted(
        capture=PLUGIN, pool_id=f"page-{cell.page}/ppc-{cell.rung}",
        adopted=cell.adopted,
        reason=f"{cell.reason}:{cell.n_lanes}lanes:{cell.n_rows}rows")


def lane_populations(store: object, subject: Subject,
                     ) -> tuple[ColorCtxPopulation, ...]:
    key: PooledKey = (int(subject[0]), str(subject[1]))
    return tuple(
        population
        for lane in store.pooled_ctx_lanes(key)
        if (population := store.color_ctx_population(lane)) is not None)


def distinct_captures(populations: tuple[ColorCtxPopulation, ...]) -> int:
    return len({population.capture_id for population in populations})


def prepare_pooled(store: object, subject: Subject,
                   stage: str) -> Job | None:
    populations = lane_populations(store, subject)
    if distinct_captures(populations) < MIN_CAPTURES:
        return None
    page, rung = int(subject[0]), str(subject[1])
    cmy8 = store.row.family is Family.CMY8
    config = color_region_head.StackConfig().context
    state_ids = store.row.state_ids

    def job() -> JobResult:
        started = time.thread_time()
        cell = pooled_cell(populations, page, rung, cmy8, config, state_ids)
        return JobResult((cell,), (pooled_event(cell),),
                         time.thread_time() - started)

    return job


def _pooled_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if store.row.family is Family.K or not store.pooled_ctx_enabled():
        return ()
    key: PooledKey = (int(fact.page), str(fact.rung))
    if store.pooled_ctx_captures(key) < MIN_CAPTURES:
        return ()
    return (key,)


def _pooled_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    return ((KEY_COLOR_POP, int(subject[0]), str(subject[1])),)


def _pooled_eligible(store: object, subject: Subject) -> bool:
    return distinct_captures(lane_populations(store, subject)) >= MIN_CAPTURES


def _pooled_stage(store: object, subject: Subject) -> str | None:
    return STAGE_POOLED


def _pooled_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    return POOLED_CTX_COST * attempts


def _pooled_never_retire(store: object, subject: Subject) -> str | None:
    return None


POOLED_CTX_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="page_rung",
    born_by=(ColorCtxPopulation,),
    subjects_of=_pooled_subjects,
    reads=_pooled_reads,
    eligible=_pooled_eligible,
    stage=_pooled_stage,
    cost=_pooled_cost,
    retire=_pooled_never_retire,
    prepare=prepare_pooled,
    produces=(PooledColorCtx,),
    prices=PRICES,
)

"""The pooled colour context arm: provenance, no-leak, ordering, null.

The mechanism's own existence proof lives here at unit scale — a lane too
label-poor to fit a context matrix of its own adopts one fitted from the
captures that share its page.  The decode-scale evidence, and what the
sim cannot ask, is measure/pooled_ctx/README.md.
"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from holo3 import data, engine
from holo3.plugins import color_pooled, color_region
from holo3.plugins import color_region_ctx as ctx
from holo3.plugins import color_region_head as region_head
from holo3.tests import _h3_facts, _h3_support

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
K_FORMAT_REF = "c3-k-r0550@7x7"

CAPTURE_A = "aa" * 32
CAPTURE_B = "bb" * 32

RICH_ROWS = 2400
POOR_ROWS = 120
POOR_SEARCH_ROWS = 40
N_STATES = 8
BLEED_PER_NEIGHBOUR = 0.22
SEPARATION = 1.6
NOISE_SD = 0.9
SEED_RICH = 20260830
SEED_POOR = 20260831


def _engine(format_ref: str = COLOR_FORMAT_REF,
            pooled: bool = True) -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,), format_ref=format_ref,
        max_pages=1, workers=1, complete=False, no_close=False,
        diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-pooled-")),
        pooled_color_context=pooled)
    return engine._Engine(request, [])


def _synthetic_lane(capture_id: str, n_rows: int, seed: int,
                    n_search: int | None = None, page: int = 0,
                    rung: str = "8") -> data.ColorCtxPopulation:
    """A lane whose scores carry a per-bin ink bleed the matrix can undo.

    States and bins are drawn from an explicit seed; the score of the
    true state is pulled down by the neighbour count in every plane the
    state prints, which is exactly the distortion one monotone curve per
    (state, plane) exists to remove.
    """
    rng = np.random.default_rng(seed)
    states = rng.integers(0, N_STATES, n_rows).astype(np.int64)
    bins = rng.integers(0, ctx.N_CONTEXT_BINS, (n_rows, 3)).astype(np.int8)
    scores = rng.normal(0.0, NOISE_SD, (n_rows, N_STATES))
    scores[np.arange(n_rows), states] += SEPARATION
    prints = ctx.state_bits(N_STATES).astype(np.float64)
    scores += BLEED_PER_NEIGHBOUR * (np.asarray(bins, np.float64)
                                     @ prints.T)
    search = np.zeros(n_rows, np.bool_)
    search[:n_rows // 2 if n_search is None else n_search] = True
    keys = np.stack((np.full(n_rows, page, np.int64),
                     np.arange(n_rows, dtype=np.int64) // 64,
                     np.arange(n_rows, dtype=np.int64) % 64), axis=-1)
    return data.ColorCtxPopulation(
        capture_id=capture_id, level_index=0, page=page, rung=rung,
        keys_pyx=keys, scores=scores.astype(np.float32),
        states=states.astype(np.int8),
        kinds=(np.arange(n_rows) % 2).astype(np.int8),
        bins=bins, search=search)


@pytest.fixture(scope="module")
def rich_lane() -> data.ColorCtxPopulation:
    return _synthetic_lane(CAPTURE_A, RICH_ROWS, SEED_RICH)


@pytest.fixture(scope="module")
def poor_lane() -> data.ColorCtxPopulation:
    return _synthetic_lane(CAPTURE_B, POOR_ROWS, SEED_POOR,
                           n_search=POOR_SEARCH_ROWS)


@pytest.fixture(scope="module")
def pooled(rich_lane, poor_lane) -> data.PooledColorCtx:
    """The one pooled fit every gate below reads: fitting it per test
    is what the fast lane's wall budget cannot afford."""
    return color_pooled.pooled_cell((rich_lane, poor_lane), 0, "8", True,
                                    _config())


@pytest.fixture(scope="module")
def pooled_head(pooled) -> ctx.ContextHead:
    return ctx.ContextHead(pooled.offsets, pooled.applied)


@pytest.fixture(scope="module")
def rich_verdict(rich_lane) -> ctx.ContextVerdict:
    return _solo_verdict(rich_lane)


def _config() -> ctx.ContextConfig:
    return region_head.StackConfig().context


def _solo_verdict(lane: data.ColorCtxPopulation) -> ctx.ContextVerdict:
    starved = ctx.label_floor_refusal(lane.search, _config())
    if starved:
        return ctx.ContextVerdict(None, False, starved, 0, 0)
    scores = np.asarray(lane.scores, np.float64)
    return ctx.context_verdict(
        ctx.population(scores, lane.states, lane.bins, lane.kinds,
                       lane.search),
        ctx.population(scores, lane.states, lane.bins, lane.kinds,
                       ~lane.search),
        _config(), True, (True, True, True), None)


def _validation(lane: data.ColorCtxPopulation) -> ctx.Population:
    return ctx.population(np.asarray(lane.scores, np.float64), lane.states,
                          lane.bins, lane.kinds, ~lane.search)


# --- the existence proof, at unit scale ------------------------------


def test_a_lane_too_poor_to_fit_its_own_matrix_refuses_it(poor_lane):
    verdict = _solo_verdict(poor_lane)
    assert verdict.head is None
    assert verdict.reason == ctx.REASON_SEARCH_STARVED, (
        "the poor lane must fail the SEARCH floor and clear the "
        "validation floor: that is the case pooling exists for")
    assert ctx.validation_floor_refusal(poor_lane.search, _config()) == ""


def test_the_pooled_fit_adopts_where_the_poor_lane_could_not(pooled):
    assert pooled.adopted, pooled.reason
    assert pooled.n_lanes == 2
    assert pooled.n_rows > 0
    assert pooled.validation_logloss is not None


def test_the_poor_lane_adopts_the_pooled_head_on_its_own_heldout(
        poor_lane, pooled_head):
    better, loss = ctx.improves_region(None, _validation(poor_lane), None,
                                       pooled_head, True)
    assert better, (
        "the arm's reason to exist: a head the lane could not fit is "
        "strictly better on the lane's own held-out labels")
    assert np.isfinite(loss)


def test_the_pooled_head_beats_the_poor_lane_nothing_by_a_real_margin(
        poor_lane, pooled, pooled_head):
    validation = _validation(poor_lane)
    _better, with_head = ctx.improves_region(None, validation, None,
                                             pooled_head, True)
    _same, without = ctx.improves_region(None, validation, None,
                                         ctx.ContextHead(
                                             np.zeros_like(pooled.offsets),
                                             pooled.applied), True)
    assert with_head < without


# --- monotone by construction ----------------------------------------


def test_a_pooled_head_that_is_not_better_is_a_no_op(rich_lane,
                                                     rich_verdict):
    verdict = rich_verdict
    assert verdict.head is not None
    better, _loss = ctx.improves_region(None, _validation(rich_lane),
                                        verdict.head, verdict.head, True)
    assert not better, "an identical candidate must not displace the head"


def test_a_lane_that_fitted_its_own_matrix_keeps_it(rich_lane, rich_verdict,
                                                    pooled_head):
    """The other half of monotone: the arm helps the starved lane and
    leaves the well-fed one exactly as it was."""
    better, _loss = ctx.improves_region(
        None, _validation(rich_lane), rich_verdict.head, pooled_head, True)
    assert not better


def test_a_zero_pooled_head_never_displaces_a_standing_one(rich_lane,
                                                           rich_verdict):
    verdict = rich_verdict
    zeros = ctx.ContextHead(np.zeros_like(verdict.head.offsets),
                            verdict.head.applied)
    better, _loss = ctx.improves_region(None, _validation(rich_lane),
                                        verdict.head, zeros, True)
    assert not better


def test_the_gate_refuses_a_candidate_that_damages_a_furniture_leg(
        rich_lane, rich_verdict):
    verdict = rich_verdict
    damaged = ctx.ContextHead(verdict.head.offsets * -4.0,
                              verdict.head.applied)
    better, _loss = ctx.improves_region(None, _validation(rich_lane), None,
                                        damaged, True)
    assert not better


# --- no held-out row is ever a pooled fit row ------------------------


def test_no_pooled_fit_row_is_any_lanes_heldout_row(rich_lane, poor_lane):
    keys, _scores, _states, _kinds, _bins, search = color_pooled.stacked(
        (rich_lane, poor_lane))
    packed = color_pooled.packed_keys(keys)
    fit = color_pooled.fit_rows(packed, search)
    assert fit.any()
    assert not np.intersect1d(packed[fit], packed[~search]).size, (
        "a pooled curve fitted on a cell some lane gates on would make "
        "that lane's adoption self-confirming")


def test_the_no_leak_rule_actually_drops_the_shared_cells():
    packed = np.asarray([1, 2, 3, 1, 2, 3], np.int64)
    search = np.asarray([True, True, True, False, True, True])
    fit = color_pooled.fit_rows(packed, search)
    assert list(fit) == [False, True, True, False, True, True]


def test_packed_keys_separate_pages_rows_and_columns():
    keys = np.asarray([[0, 0, 1], [0, 1, 0], [1, 0, 0], [0, 0, 0]],
                      np.int64)
    packed = color_pooled.packed_keys(keys)
    assert len(set(packed.tolist())) == 4
    assert packed[3] == 0


# --- determinism ------------------------------------------------------


def test_the_pooled_fit_is_bit_identical_on_a_repeat(rich_lane, poor_lane,
                                                     pooled):
    second = color_pooled.pooled_cell((rich_lane, poor_lane), 0, "8", True,
                                      _config())
    assert np.array_equal(pooled.offsets, second.offsets)
    assert np.array_equal(pooled.applied, second.applied)
    assert pooled.validation_logloss == second.validation_logloss


def test_the_lane_order_the_scheduler_hands_the_job_is_sorted():
    instance = _engine()
    for lane in (_synthetic_lane(CAPTURE_B, 128, 3),
                 _synthetic_lane(CAPTURE_A, 128, 4)):
        instance._fold(lane)
    lanes = instance.pooled_ctx_lanes((0, "8"))
    assert lanes == tuple(sorted(lanes))
    assert [lane[0] for lane in lanes] == [CAPTURE_A, CAPTURE_B]


# --- the cell schema owns the ordinal ---------------------------------


ORDINAL_CASES = (
    ("adopted beats refused", dict(adopted=True, n_lanes=2, n_rows=100),
     dict(adopted=False, n_lanes=9, n_rows=9000), True),
    ("more lanes beat fewer", dict(adopted=True, n_lanes=3, n_rows=100),
     dict(adopted=True, n_lanes=2, n_rows=100), True),
    ("more rows beat fewer", dict(adopted=True, n_lanes=2, n_rows=200),
     dict(adopted=True, n_lanes=2, n_rows=100), True),
    ("lower loss wins a tie",
     dict(adopted=True, n_lanes=2, n_rows=100, validation_logloss=0.4),
     dict(adopted=True, n_lanes=2, n_rows=100, validation_logloss=0.5),
     True),
    ("a worse loss does not adopt",
     dict(adopted=True, n_lanes=2, n_rows=100, validation_logloss=0.6),
     dict(adopted=True, n_lanes=2, n_rows=100, validation_logloss=0.5),
     False),
    ("an identical cell does not adopt",
     dict(adopted=True, n_lanes=2, n_rows=100, validation_logloss=0.5),
     dict(adopted=True, n_lanes=2, n_rows=100, validation_logloss=0.5),
     False),
)


@pytest.mark.parametrize("label,candidate,standing,adopts",
                         ORDINAL_CASES, ids=[row[0] for row in ORDINAL_CASES])
def test_the_pooled_cell_ordinal_is_quality_then_evidence(
        label, candidate, standing, adopts):
    ordinal = data.pooled_ctx_ordinal
    assert (ordinal(_h3_facts.pooled_color_ctx(**candidate))
            > ordinal(_h3_facts.pooled_color_ctx(**standing))) is adopts


def test_the_store_keeps_the_better_cell_and_wakes_only_on_a_change():
    instance = _engine()
    better = _h3_facts.pooled_color_ctx(validation_logloss=0.4)
    worse = _h3_facts.pooled_color_ctx(validation_logloss=0.9)
    changed, keys, _kind = instance._fold(better)
    assert changed and keys == (("pooled_ctx", 0, "4"),)
    changed, keys, _kind = instance._fold(worse)
    assert not changed and keys == ()
    assert instance.pooled_color_ctx((0, "4")).validation_logloss == 0.4


def test_a_refusal_never_erases_a_standing_pooled_head():
    instance = _engine()
    instance._fold(_h3_facts.pooled_color_ctx(validation_logloss=0.4))
    changed, _keys, _kind = instance._fold(
        _h3_facts.pooled_color_ctx(adopted=False, n_lanes=7, n_rows=99999))
    assert not changed
    assert instance.pooled_color_ctx((0, "4")).adopted


# --- births: the second capture is what arms the row ------------------


def test_one_capture_never_births_the_pooled_row():
    instance = _engine()
    instance._ingest(_synthetic_lane(CAPTURE_A, 128, 5))
    instance._ingest(_synthetic_lane(CAPTURE_A, 128, 6, page=0, rung="4"))
    assert not [key for key in instance._bookmarks
                if key[0] == color_pooled.PLUGIN]


def test_the_second_captures_population_births_the_pooled_row():
    instance = _engine()
    instance._ingest(_synthetic_lane(CAPTURE_A, 128, 7))
    instance._ingest(_synthetic_lane(CAPTURE_B, 128, 8))
    assert [key[1] for key in instance._bookmarks
            if key[0] == color_pooled.PLUGIN] == [(0, "8")]


def test_captures_at_different_rungs_are_not_pooled():
    instance = _engine()
    instance._ingest(_synthetic_lane(CAPTURE_A, 128, 9, rung="8"))
    instance._ingest(_synthetic_lane(CAPTURE_B, 128, 10, rung="4"))
    assert not [key for key in instance._bookmarks
                if key[0] == color_pooled.PLUGIN]


def test_the_dial_off_removes_the_row_and_the_lane_subscription():
    instance = _engine(pooled=False)
    instance._ingest(_synthetic_lane(CAPTURE_A, 128, 11))
    instance._ingest(_synthetic_lane(CAPTURE_B, 128, 12))
    assert not [key for key in instance._bookmarks
                if key[0] == color_pooled.PLUGIN]
    reads = color_region._color_reads(instance, (CAPTURE_A, 0, 0))
    assert not any(key[0] == "pooled_ctx" for key in reads)


def test_a_k_run_never_births_the_pooled_row():
    instance = _engine(format_ref=K_FORMAT_REF)
    instance._ingest(_synthetic_lane(CAPTURE_A, 128, 13))
    instance._ingest(_synthetic_lane(CAPTURE_B, 128, 14))
    assert not [key for key in instance._bookmarks
                if key[0] == color_pooled.PLUGIN]


def test_the_row_declares_the_population_key_it_subscribes_to():
    descriptor = engine.DESCRIPTOR_BY_NAME[color_pooled.PLUGIN]
    assert descriptor.reads(None, (3, "16/3")) == (("color_pop", 3, "16/3"),)


def test_the_row_prices_its_own_re_runs():
    descriptor = engine.DESCRIPTOR_BY_NAME[color_pooled.PLUGIN]
    prices = [descriptor.cost(None, (0, "8"), "pooled_ctx", attempts, 0)
              for attempts in (1, 2, 3)]
    _h3_support.assert_golden("pooled_ctx price ladder", prices,
                              [170, 340, 510])


# --- the pooled head as the lane wears it -----------------------------


def test_an_unsupported_plane_is_zeroed_out_of_the_pooled_head():
    head = ctx.ContextHead(np.full((8, 3, ctx.N_CONTEXT_BINS), 0.5),
                           np.ones((8, 3), np.bool_))
    worn = region_head.pooled_candidate(head, (True, False, True), 8)
    assert worn is not None
    assert np.array_equal(worn.offsets[:, 1], np.zeros((8,
                                                        ctx.N_CONTEXT_BINS)))
    assert not worn.applied[:, 1].any()
    assert worn.applied[:, 0].all() and worn.applied[:, 2].all()
    assert np.array_equal(head.offsets, np.full(head.offsets.shape, 0.5)), (
        "masking must not mutate the standing pooled cell's arrays")


def test_a_pooled_head_of_the_wrong_state_width_is_refused():
    head = ctx.ContextHead(np.full((6, 3, ctx.N_CONTEXT_BINS), 0.5),
                           np.ones((6, 3), np.bool_))
    assert region_head.pooled_candidate(head, (True, True, True), 8) is None
    assert region_head.pooled_candidate(head, (True, True, True),
                                         6) is not None


def test_a_head_with_no_live_plane_is_not_a_candidate():
    head = ctx.ContextHead(np.full((8, 3, ctx.N_CONTEXT_BINS), 0.5),
                           np.ones((8, 3), np.bool_))
    assert region_head.pooled_candidate(head, (False, False, False),
                                         8) is None
    assert region_head.pooled_candidate(None, (True, True, True), 8) is None


# --- label provenance --------------------------------------------------


def test_the_published_population_carries_no_label_the_format_does_not_own(
        cmy8_row, cmy8_geometry):
    from holo3.plugins import color_model

    cells = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    states, kinds = color_model.reference_states(cmy8_row, cmy8_geometry, 0,
                                                 cells)
    labelled = states >= 0
    assert labelled.any()
    assert np.array_equal(labelled, kinds >= 0), (
        "with no certificate in the store every labelled cell is "
        "furniture: a payload label can only come from a certificate")


@pytest.fixture(scope="module")
def cmy8_row() -> object:
    from holo3.format import identity

    return identity.resolve_format_ref(COLOR_FORMAT_REF)


@pytest.fixture(scope="module")
def cmy8_geometry(cmy8_row) -> object:
    from holo3.format import identity

    return identity.build_site_geometry(cmy8_row)


def test_a_stack_result_publishes_nothing_unless_the_lane_was_asked_to():
    result = region_head.StackResult(
        selected=None, features=(), adopted=False, refusal_reason="probe",
        head_reason="", head_saturation=-1.0, ctx_verdict=None,
        context_bins=None)
    assert result.labels is None and result.pooled_adopted is False


def test_a_refit_that_publishes_the_same_population_wakes_nobody():
    instance = _engine()
    lane = _synthetic_lane(CAPTURE_A, 128, 16)
    changed, keys, _kind = instance._fold(lane)
    assert changed and keys == (("color_pop", 0, "8"),)
    changed, keys, _kind = instance._fold(replace(lane))
    assert not changed and keys == (), (
        "an unchanged population must not re-fire the pooled row: that "
        "loop would never settle")
    moved = replace(lane, states=(lane.states + 1) % N_STATES)
    changed, keys, _kind = instance._fold(moved)
    assert changed and keys == (("color_pop", 0, "8"),)

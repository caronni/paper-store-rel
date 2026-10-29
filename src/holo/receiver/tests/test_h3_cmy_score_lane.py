"""cmy on cmy7's score lane, and the stream attempt (CMY-RECEIVER-PLAN A3).

LEDGER 2026-10-12 (A3): the held-out coin trigger `cmy_unsupported_streams` is the
design detail CMY-DESIGN §2.7 left to the build (the erasure must not wait on the
collapse test alone, :680-683): a stream is erased when, for any pair of states that
differ only in that stream's bit, the class-balanced held-out log-loss of the LLRs
clipped to ±DEGENERATE_LLR_CLIP is not below ln 2 (softplus(x) + softplus(−x) ≥ 2 ln 2:
a coin's floor).  Its rates come from a SCRATCH sim of Gaussian noise on solid bars
(no c2 W-confusion, no partly dead plane; scratchpad a3/trigger_sim*.py, not a record):
dead-Y/dead-M detection 0.993–1.000 against 0.93–0.96 for the collapse test alone;
false erasure 0 at σ ≤ 25 counts, 0.7 % at σ 40 (= the collapse test's own), ≤ 0.3 %
with 2–4 W cells reading as solid Y (1.7 % without the clip).  A measured record on
paper is owed (measure/cmy_calibration/, A8); the owner's look is asked for.

LEDGER 2026-10-12 (the cmy implementation review, F3): the context gate scored a
cmy candidate by the four-state loss while emission erases a stream after the
context matrix, so a head could sharpen the discarded stream and reverse the
surviving one and still adopt (the review's constructed head: four-state loss
3.0486 -> 1.3133, emitted hi with lo erased 0 -> 4 sign errors of four patterns).
Now a lane with erased streams hands the gate a `ctx.StreamErasure`, and the gate
scores standing and candidate on the surviving streams' binary log-loss after
`ctx.relative_emission` -- the context, erasure and bound the emission itself
calls; with nothing erased the four-state loss is untouched (the decode records'
null is the proof, the lead's).

cmy's evidence is THREE W-relative state scores (C, M, Y) out of a QDA
over its alphabet W C M Y (presence ids 0, 1, 2, 4, QDA columns 0..3);
a collapsed or unsupported LABEL stream is erased in score space, never
a refusal, and each label stream is demapped from the scores at the
attempt (`tiles.stream_llrs`).  What this module states, on seeded
synthetic features at e043c's solid bars: the four-column fit; a dead
toner erases exactly the label stream it carries (M: hi, Y: lo, C: both)
and the other stream stands; the held-out coin erases a stream the
collapse test kept; the erasure is exactly zero through the demap; the
stream LLRs and the attempt floor.  The generator-encoded tile and the
state error on the stimulus are test_h3_e2e_cmy's (they read the A2
page).  Not re-proved here: the demap itself
(tests/holo/test_channel_mapper.py), the tables, `_combine`.
"""
from __future__ import annotations

import numpy as np
import pytest

from scipy.special import logsumexp

from holo.receiver import data
from holo.receiver.format import identity, tile_codec
from holo.receiver.format.identity import Family
from holo.receiver.lib.pava import class_balanced_weights
from holo.receiver.plugins import color_model, tiles
from holo.receiver.plugins import color_region_ctx as ctx
from holo.receiver.plugins import color_region_head as region_head

CMY_REF = "c3-cmy-r0850@10x10"
CMY8_FOSSIL = "L:c2-cmy8-p120-v0@3328x2304"
STATE_IDS = tile_codec.CMY_STATE_IDS
#: e043c sheet 3's solid bars (`_h3_sims_cmy.e043c_sheet3_bars`) as
#: reflectance, in the alphabet's column order W C M Y.
BARS = np.asarray(((231, 231, 234), (51, 155, 207), (217, 71, 125),
                   (230, 222, 93)), np.float64) / 255.0
SIGMA = 0.02
#: One p120 tile's furniture per state, rounded to the expectation:
#: 50 C words, 25 W and 25 Y words, 20 M dust (the balance law).
TILE_COUNTS = {1: 50, 0: 25, 4: 25, 2: 20}


@pytest.fixture(scope="module")
def cmy_row() -> identity.FormatRow:
    return identity.resolve_format_ref(CMY_REF)


def _furniture(n_tiles: int) -> tuple[np.ndarray, np.ndarray]:
    states = np.concatenate([
        np.full(count, state, np.int64)
        for _tile in range(n_tiles)
        for state, count in TILE_COUNTS.items()])
    return states, np.where(states == 2, 1, 0).astype(np.int8)


def _selection(states: np.ndarray,
               kinds: np.ndarray) -> region_head.OwnerSelection:
    n = states.size
    keys = np.stack((np.zeros(n, np.int64), np.arange(n) // 64,
                     np.arange(n) % 64), axis=1).astype(np.int64)
    return region_head.OwnerSelection(
        np.zeros(n, np.int64), np.arange(n, dtype=np.int64), states, kinds,
        keys, region_head.deterministic_fit_split(states, keys))


def _features(states: np.ndarray, seed: int,
              dead: tuple[int, ...] = ()) -> np.ndarray:
    rng = np.random.default_rng(seed)
    source = region_head.state_columns(STATE_IDS, states)
    source[np.isin(states, dead)] = 0
    return BARS[source] + rng.normal(0.0, SIGMA, (states.size, 3))


def _label_bits(states: np.ndarray) -> np.ndarray:
    return color_model.CMY_COLUMN_LABEL_BITS[
        region_head.state_columns(STATE_IDS, states)]


def test_the_cmy_detector_fits_four_columns_over_presence_ids_0_1_2_4():
    states, kinds = _furniture(4)
    features = _features(states, seed=3)
    fit, reason = region_head.fit_detector(
        Family.CMY, _selection(states, kinds), (features,))
    assert reason == "" and fit is not None and fit.detector is None
    assert fit.model.n_states == 4
    assert np.all(fit.model.class_counts > 0)
    assert np.allclose(fit.model.means, BARS, atol=4 * SIGMA)
    assert fit.model.clipped_planes == () and fit.erased_streams == ()
    assert fit.heldout_scores.shape[1] == 3
    values, _divisor = region_head.evidence_with_divisor(fit, features, None)
    assert values.shape == (states.size, 3)
    read = np.asarray(STATE_IDS)[np.argmax(
        np.concatenate((np.zeros((states.size, 1)), values), axis=1),
        axis=1)]
    assert np.array_equal(read, states)


@pytest.mark.parametrize("dead, erased", [((2,), (0,)), ((4,), (1,)),
                                          ((1,), (0, 1))],
                         ids=["dead-M-clips-hi", "dead-Y-clips-lo",
                              "dead-C-clips-both"])
def test_a_dead_toner_erases_its_label_stream_and_the_other_stands(
        dead, erased):
    states, kinds = _furniture(4)
    features = _features(states, seed=5, dead=dead)
    fit, reason = region_head.fit_detector(
        Family.CMY, _selection(states, kinds), (features,))
    assert reason == "" and fit is not None
    assert fit.model.clipped_planes == erased
    assert fit.erased_streams == erased
    values, _divisor = region_head.evidence_with_divisor(fit, features, None)
    truth = _label_bits(states)
    for stream in range(2):
        llrs = tile_codec.cmy_soft_demap(values, stream)
        if stream in erased:
            assert np.all(llrs == 0.0)
        else:
            assert np.array_equal(llrs > 0.0, truth[:, stream])


def test_the_held_out_coin_erases_a_stream_the_collapse_test_kept():
    # Y prints on the fit side only: its search cells sit 0.1 above W in
    # blue (five sigma, far past the collapse threshold), its held-out
    # cells read as W -- a dead Y the whitened-mean test cannot see.
    states, kinds = _furniture(4)
    selection = _selection(states, kinds)
    features = _features(states, seed=7, dead=(4,))
    printed_on_fit_side = (states == 4) & selection.search
    features[printed_on_fit_side, 2] += 0.1
    fit, reason = region_head.fit_detector(Family.CMY, selection,
                                           (features,))
    assert reason == "" and fit is not None
    assert fit.model.clipped_planes == ()
    assert fit.erased_streams == (1,)


def test_the_erasure_is_exactly_zero_through_the_demap():
    rng = np.random.default_rng(11)
    scores = rng.normal(0.0, 5.0, (200, 3))
    sibling = rng.integers(0, 2, 200).astype(np.uint8)
    marginals = [tile_codec.cmy_soft_demap(scores, stream)
                 for stream in range(2)]
    for erased in ((0,), (1,), (0, 1)):
        projected = color_model.cmy_erase_streams(scores, erased)
        for stream in range(2):
            alone = tile_codec.cmy_soft_demap(projected, stream)
            given = tile_codec.cmy_soft_demap(projected, stream, sibling)
            if stream in erased:
                assert np.all(alone == 0.0) and np.all(given == 0.0)
            else:
                assert np.allclose(alone, marginals[stream],
                                   rtol=1e-12, atol=1e-12)
                assert np.allclose(given, marginals[stream],
                                   rtol=1e-12, atol=1e-12)


def test_stream_llrs_read_a_toner_column_or_demap_a_label_bit(cmy_row):
    rng = np.random.default_rng(13)
    sequential = rng.normal(0.0, 3.0, (64, 3))
    sibling = rng.integers(0, 2, 64).astype(np.uint8)
    cmy8_row = identity.resolve_format_ref(CMY8_FOSSIL)
    for fact in cmy8_row.streams:
        assert np.array_equal(
            tiles.stream_llrs(cmy8_row, fact, sequential),
            sequential[:, fact.plane])
        with pytest.raises(ValueError):
            tiles.stream_llrs(cmy8_row, fact, sequential, sibling)
    for fact in cmy_row.streams:
        assert np.array_equal(
            tiles.stream_llrs(cmy_row, fact, sequential),
            tile_codec.cmy_soft_demap(sequential, fact.label_index))
        assert np.array_equal(
            tiles.stream_llrs(cmy_row, fact, sequential, sibling),
            tile_codec.cmy_soft_demap(sequential, fact.label_index, sibling))


def test_an_erased_label_stream_lands_below_the_attempt_floor(cmy_row):
    geometry = identity.build_site_geometry(cmy_row)
    rng = np.random.default_rng(17)
    scores = color_model.cmy_erase_streams(
        rng.normal(0.0, 3.0, (tile_codec.N_CELLS, 3)), (1,))
    cut = tiles.TileCut(
        capture_id="synthetic", level_index=0, page=0, ty=2, tx=3,
        values=scores.astype(np.float32),
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))
    erased = tiles.attempt_tile(cmy_row, geometry, (cut,), "lo",
                                tiles.STAGE_SCAN)
    standing = tiles.attempt_tile(cmy_row, geometry, (cut,), "hi",
                                  tiles.STAGE_SCAN)
    assert erased.fact.outcome == tiles.OUTCOME_BELOW_FLOOR
    assert erased.certificate is None and erased.fact.n_iters == 0
    assert standing.fact.outcome == tiles.OUTCOME_FAILED
    assert standing.fact.n_iters > 0


# ------------------------------------------ the context gate under erasure


def _erasure_counterexample() -> tuple[ctx.Population, ctx.ContextHead]:
    """The review's F3 construction (probes/context_erasure_gate.py): raw
    scores confuse each state with its lo-flipped twin only; the
    candidate head moves every state onto its hi-flipped twin, sharp on
    lo, reversed on hi.  100 copies of the four patterns, C words and M
    dust (both furniture legs present)."""
    truth = np.arange(4)
    same_hi = (3, 2, 1, 0)
    wrong_hi = (1, 0, 3, 2)
    raw = np.full((4, 4), -13.0)
    candidate = np.full((4, 4), -10.0)
    for state in range(4):
        raw[state, state] = -3.0
        raw[state, same_hi[state]] = 0.0
        candidate[state, state] = 0.0
        candidate[state, wrong_hi[state]] = 1.0
    raw -= raw[:, :1]
    candidate -= candidate[:, :1]
    bins = np.full((4, 3), -1, np.int8)
    bins[:, 0] = np.arange(4)
    offsets = np.zeros((3, 3, ctx.N_CONTEXT_BINS))
    offsets[:, 0, :4] = (candidate[:, 1:] - raw[:, 1:]).T
    head = ctx.ContextHead(offsets, np.ones((3, 3), bool))
    population = ctx.Population(
        np.tile(raw, (100, 1)), np.tile(truth, 100), np.tile(bins, (100, 1)),
        np.tile(np.where(truth == 2, 1, 0), 100))
    return population, head


def test_the_context_gate_scores_the_surviving_stream_under_erasure():
    """F3's regression: with lo erased the decoder reads hi alone, and the
    candidate reverses every hi sign it emits (4 of the four patterns)
    while the four-state loss improves -- so the gate must refuse it,
    and does once it scores the emitted surviving stream."""
    population, head = _erasure_counterexample()
    bound = region_head.CMY7_RELATIVE_SCORE_BOUND
    erasure = ctx.StreamErasure((1,), bound)
    hi = color_model.CMY_COLUMN_LABEL_BITS[:4, 0]
    patterns = population.scores[:4, 1:]
    wrong = []
    for context in (None, head):
        emitted, _divisor = ctx.relative_emission(
            patterns, context, population.bins[:4], (1,), bound)
        wrong.append(int(np.count_nonzero(
            (tile_codec.cmy_soft_demap(emitted, 0) > 0.0) != hi)))
    assert wrong == [0, 4]
    assert ctx.improves_region(None, population, None, head, False)[0], (
        "the four-state gate adopts the reversing head")
    adopted, _loss = ctx.improves_region(None, population, None, head,
                                         False, erasure)
    assert not adopted
    standing = ctx._region_losses(None, population, None, False, erasure)
    proposed = ctx._region_losses(None, population, head, False, erasure)
    assert proposed[0] > standing[0]
    assert ctx._region_losses(None, population, head, False,
                              ctx.StreamErasure((0, 1), bound)) == (
        ctx.CONTEXT_NLL_UNMEASURED,) * 3


def test_with_nothing_erased_the_context_gate_is_the_four_state_loss():
    """The gate's triple without an erasure, recomputed here as it read
    before F3: the head on the W-relative scores, the four-state NLL,
    class-balanced means over all, word and dust rows."""
    population, head = _erasure_counterexample()
    for context in (None, head):
        scores = population.scores
        if context is not None:
            scores = ctx.augment(context.apply_states(scores[:, 1:],
                                                      population.bins))
        normalized = scores - logsumexp(scores, axis=1, keepdims=True)
        nll = -normalized[np.arange(population.states.size),
                          population.states]

        def leg(rows: np.ndarray) -> float:
            weights = class_balanced_weights(population.states[rows])
            return float(np.sum(weights * nll[rows]) / np.sum(weights))

        expected = (leg(np.ones(nll.size, bool)), leg(population.kinds == 0),
                    leg(population.kinds == 1))
        assert ctx._region_losses(None, population, context, False) \
            == expected
        assert ctx._region_losses(None, population, context, False,
                                  None) == expected


def _page_case(format_ref: str, seed: int, dead: tuple[int, ...] = (),
               ) -> tuple[identity.FormatRow, region_head.OwnerSelection,
                          data.WindowRows, np.ndarray]:
    """A whole page as one window: reference states on furniture, the
    payload a seeded draw from the alphabet, features at e043c's bars
    (cmy) or a clean presence ramp (cmy8)."""
    row = identity.resolve_format_ref(format_ref)
    geometry = identity.build_site_geometry(row)
    height, width = row.cells_yx
    cells = np.stack(np.meshgrid(np.arange(height), np.arange(width),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    states, kinds = color_model.reference_states(row, geometry, 0, cells)
    known = states >= 0
    rng = np.random.default_rng(seed)
    printed = np.where(known, states, rng.choice(
        np.asarray(row.state_ids), states.size)).astype(np.int64)
    bits = tile_codec.states_to_planes(
        np.maximum(states, 0).astype(np.uint8))
    rows = data.WindowRows(
        patch_ordinal=0, window_id=("cap", 0, 0, (0, 0) + row.cells_yx),
        page=0, local_cells_yx=cells, page_cells_yx=cells,
        scan_points_yx=cells.astype(np.float64), states=states,
        furniture_kind=kinds, known_component_bits=bits.astype(np.uint8),
        known_component_mask=np.repeat(known[:, None], 3, axis=1),
        heldout_logloss=None)
    if row.family is Family.CMY:
        features = _features(printed, seed, dead)
    else:
        features = 0.9 - 0.6 * tile_codec.states_to_planes(
            printed.astype(np.uint8)).astype(np.float64) + rng.normal(
                0.0, 0.02, (printed.size, 3))
    return row, region_head.owner_selection((rows,)), rows, features


def _gate_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    calls: dict[str, list] = {"verdict": [], "emission": []}
    verdict = ctx.context_verdict
    emission = ctx.relative_emission

    def recording_verdict(*args, **kwargs):
        calls["verdict"].append(args[7] if len(args) > 7
                                else kwargs.get("erasure"))
        return verdict(*args, **kwargs)

    def recording_emission(*args, **kwargs):
        calls["emission"].append(args[3])
        return emission(*args, **kwargs)

    monkeypatch.setattr(ctx, "context_verdict", recording_verdict)
    monkeypatch.setattr(ctx, "relative_emission", recording_emission)
    return calls


def test_a_cmy_lane_hands_its_erasure_to_the_context_gate(monkeypatch):
    row, selection, rows, features = _page_case(CMY_REF, 19, dead=(4,))
    calls = _gate_calls(monkeypatch)
    result = region_head.fit_region_stack(
        row, selection, (rows,), (features,), None,
        (np.ones(features.shape[0], bool),), region_head.StackConfig())
    assert result.selected.erased_streams == (1,)
    assert calls["verdict"] == [ctx.StreamErasure(
        (1,), region_head.CMY7_RELATIVE_SCORE_BOUND)]
    assert calls["emission"] and all(erased == (1,)
                                     for erased in calls["emission"])


def test_the_erasure_helper_is_never_entered_for_a_cmy8_fit(monkeypatch):
    row, selection, rows, features = _page_case("c3-cmy8-r0550@2x2", 23)
    calls = _gate_calls(monkeypatch)
    result = region_head.fit_region_stack(
        row, selection, (rows,), (features,), None,
        (np.ones(features.shape[0], bool),), region_head.StackConfig())
    assert result.selected is not None
    assert result.selected.detector is not None
    assert calls["verdict"] == [None]
    assert calls["emission"] == []
    region_head.evidence_with_divisor(result.selected, features,
                                      result.context_bins)
    assert calls["emission"] == []


@pytest.mark.parametrize("dead, erased", [((4,), (1,)), ((), ())])
def test_the_pooled_head_is_admitted_through_the_lane_erasure(
        monkeypatch, dead, erased):
    """The pooled candidate's admission (`color.pooled_ctx`'s head on
    this lane) is the same region gate, so it sees the lane's erasure --
    and None on a lane that erases nothing."""
    row, selection, rows, features = _page_case(CMY_REF, 19, dead=dead)
    pooled = ctx.ContextHead(np.zeros((3, 3, ctx.N_CONTEXT_BINS)),
                             np.ones((3, 3), bool))
    seen: list[ctx.StreamErasure | None] = []
    gate = ctx.improves_region

    def recording_gate(*args, **kwargs):
        if args[3] is pooled:
            seen.append(args[5] if len(args) > 5 else kwargs.get("erasure"))
        return gate(*args, **kwargs)

    monkeypatch.setattr(ctx, "improves_region", recording_gate)
    result = region_head.fit_region_stack(
        row, selection, (rows,), (features,), None,
        (np.ones(features.shape[0], bool),), region_head.StackConfig(),
        pooled=pooled)
    assert result.selected.erased_streams == erased
    assert seen == [ctx.StreamErasure(
        erased, region_head.CMY7_RELATIVE_SCORE_BOUND) if erased else None]

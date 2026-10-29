"""cmy's calibration chain in the head slot (CMY-RECEIVER-PLAN A8;
CMY-DESIGN §2.7, R11), the state-balanced PAVA entry it fits with, and
`PavaMap`'s logit evaluator.

What this module states, on seeded synthetic score populations: the
weighted `fit_component_pava` under no weights or class-balanced weights
is today's fit bit for bit; `PavaMap` joins its nodes in p unless its
logit field is set, and in logit p when it is; the chain's three maps
fold back so the demap returns each map at its nodes; each map refuses
below its floors and leaves its piece to the raw bounded statistic; the
erasure law composes with the chain (a dead lo reads (L_hi, L_hi, 0), a
dead hi takes no chain); a chain fitted on C-heavy furniture recovers
the payload's prior; and the chain is adopted only through the three-way
gate, whose legs it publishes.  The chain on the cmy sim pages is
test_h3_e2e_cmy's.

LEDGER 2026-10-12 (A8): `pre-A8 fit_component_pava node digest` is the
sha256 of the node bytes `fit_component_pava` returned for `_pava_fits()`
at f8df7b2e, before the weighted entry existed (scratch script, the same
draws); the unweighted path and class-balanced weights reproduce it.
Prototype numbers behind the tests below (the same seeds): the
payload-prior grid's mean |dp| against the balanced reference 0.0059
state-balanced vs 0.0334 class-balanced; the gate on calibrated raw
scores (exact Gaussian log-likelihood ratios) refused at total 0.5692 vs
0.5668, on the same scores x50 adopted at 0.5704 vs 1.2664.
2026-10-12 (A8 refuter): the payload-prior test asserted a bar (<= 0.01
and under a third of class-balanced's); it pins the two measured values
instead, `assert_measured` at four decimals (0.005931 and 0.033363 in
full).
"""
from __future__ import annotations

import dataclasses
import hashlib

import numpy as np
import pytest

from holo.receiver.format import tile_codec
from holo.receiver.lib import pava
from holo.receiver.plugins import color_chain, color_conditioning, color_model
from holo.receiver.plugins import color_region_head as region_head
from holo.receiver.tests import _h3_support

BOUND = region_head.CMY7_RELATIVE_SCORE_BOUND
#: Feature means per QDA column W C M Y: C far from W, M and Y close --
#: the within-class asymmetry the state-balanced weights exist for.
MEANS = np.asarray(((0.0, 0.0, 0.0), (3.2, 2.4, 0.0), (0.0, 1.6, 1.1),
                    (0.0, 0.0, 1.7)), np.float64)
#: One p120 tile's furniture on one side of the `&2` split, rounded to
#: the expectation: 25 C words, 12 W, 13 Y, 10 M dust.
SIDE_TILE = (12, 25, 10, 13)


def _pava_fits(seed: int = 20261012, n_fits: int = 60
               ) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(seed)
    out: list[tuple[np.ndarray, np.ndarray]] = []
    while len(out) < n_fits:
        n = int(rng.integers(4, 600))
        scores = np.round(rng.normal(0.0, 3.0, n), int(rng.integers(0, 3)))
        labels = (rng.random(n) < rng.uniform(0.1, 0.9)).astype(np.int64)
        if labels.min() == labels.max():
            continue
        out.append((scores, labels))
    return out


def _side(counts: tuple[int, ...], seed: int, side: int, offset: int = 0,
          scale: float = 1.0
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """W-relative scores (exact Gaussian log-likelihood ratios, x scale),
    QDA columns, kinds (M dust 1, the rest words 0) and site keys whose
    `&2` bit puts every row on `side` (0 fit, 1 validation)."""
    rng = np.random.default_rng(seed)
    columns = np.concatenate([np.full(count, state, np.int64)
                              for state, count in enumerate(counts)])
    features = MEANS[columns] + rng.normal(0.0, 1.0, (columns.size, 3))
    loglik = -0.5 * ((features[:, None, :] - MEANS[None]) ** 2).sum(axis=-1)
    slot = offset + np.arange(columns.size)
    keys = np.stack((np.zeros_like(slot), np.zeros_like(slot),
                     4 * slot + 2 * side), axis=1)
    return ((loglik[:, 1:] - loglik[:, :1]) * scale, columns,
            np.where(columns == 2, 1, 0).astype(np.int8), keys)


def _population(counts: tuple[int, ...], seed: int, scale: float = 1.0
                ) -> tuple[np.ndarray, ...]:
    fit = _side(counts, seed, 0, scale=scale)
    validation = _side(counts, seed + 1, 1, offset=fit[1].size, scale=scale)
    return tuple(np.concatenate(pair) for pair in zip(fit, validation))


def _digest(maps: list[color_model.PavaMap]) -> str:
    digest = hashlib.sha256()
    for fitted in maps:
        digest.update(fitted.score_nodes.tobytes())
        digest.update(fitted.probability_nodes.tobytes())
        digest.update(str(fitted.n_labels).encode())
    return digest.hexdigest()


def test_unweighted_and_class_balanced_pava_are_todays_fit_bit_for_bit():
    fits = _pava_fits()
    unweighted = [color_model.fit_component_pava(scores, labels)
                  for scores, labels in fits]
    _h3_support.assert_measured(
        "pre-A8 fit_component_pava node digest", _digest(unweighted),
        "d5a52050130633199a7fa5c7f7a59bb1b8b2599a97b02aadcd64cc5a8e7f239c")
    for (scores, labels), reference in zip(fits, unweighted):
        for weights in (pava.class_balanced_weights(labels, 2),
                        np.full(labels.size, 0.37)):
            fitted = color_model.fit_component_pava(scores, labels, weights)
            assert np.array_equal(fitted.score_nodes, reference.score_nodes)
            assert np.array_equal(fitted.probability_nodes,
                                  reference.probability_nodes)
            assert fitted.n_labels == reference.n_labels
            assert not fitted.logit_interpolation


def test_the_pava_map_joins_its_nodes_in_p_unless_its_logit_field_is_set():
    nodes = np.asarray((-3.0, -1.0, 0.0, 2.0, 5.0))
    probabilities = np.asarray((0.05, 0.2, 0.5, 0.7, 0.95))
    linear = color_model.PavaMap(nodes, probabilities, 40)
    logit = dataclasses.replace(linear, logit_interpolation=True)
    grid = np.linspace(-6.0, 8.0, 141)
    p = np.interp(grid, nodes, probabilities)
    assert np.array_equal(linear.llrs(grid), np.log(p / (1.0 - p)))
    node_logits = np.log(probabilities) - np.log1p(-probabilities)
    assert np.array_equal(logit.llrs(nodes), node_logits)
    midpoints = 0.5 * (nodes[1:] + nodes[:-1])
    assert np.allclose(logit.llrs(midpoints),
                       0.5 * (node_logits[1:] + node_logits[:-1]),
                       rtol=0.0, atol=1e-12)
    assert np.all(logit.llrs(np.asarray((-50.0, -3.5))) == node_logits[0])
    assert np.all(logit.llrs(np.asarray((5.5, 50.0))) == node_logits[-1])


def test_fit_fold_demap_returns_each_map_at_its_nodes():
    scores, columns, _kinds, _keys = _population((500, 500, 500, 500), 3)
    maps = [color_chain.fit_chain_map(scores, columns, index)
            for index in range(3)]
    assert all(fitted.logit_interpolation for fitted in maps)
    for index in (1, 2):
        member, labels = color_chain.map_population(columns, index)
        plain = color_model.fit_component_pava(
            color_chain.chain_statistic(scores[member], index),
            labels[member])
        assert np.array_equal(maps[index].probability_nodes,
                              plain.probability_nodes)
    hi, given_w, given_m = np.meshgrid(
        *(fitted.llrs(fitted.score_nodes) for fitted in maps),
        indexing="ij")
    folded = color_chain.fold_hi_first(hi.ravel(), given_w.ravel(),
                                       given_m.ravel())
    zeros = np.zeros(folded.shape[0], np.uint8)
    assert np.allclose(tile_codec.cmy_soft_demap(folded, 0), hi.ravel(),
                       rtol=0.0, atol=1e-9)
    assert np.array_equal(tile_codec.cmy_soft_demap(folded, 1, zeros),
                          given_w.ravel())
    assert np.allclose(tile_codec.cmy_soft_demap(folded, 1, zeros + 1),
                       given_m.ravel(), rtol=0.0, atol=1e-9)
    head = color_chain.CmyChain((maps[0], maps[1], maps[2]), BOUND)
    applied = head.apply(scores)
    for index, (stream, sibling) in enumerate(color_chain.CHAIN_MAPS):
        given = (None if sibling is None
                 else np.full(scores.shape[0], sibling, np.uint8))
        assert np.allclose(
            tile_codec.cmy_soft_demap(applied, stream, given),
            maps[index].llrs(color_chain.chain_statistic(scores, index)),
            rtol=0.0, atol=1e-9)


def _columns(counts: tuple[int, ...]) -> np.ndarray:
    return np.concatenate([np.full(count, state, np.int64)
                           for state, count in enumerate(counts)])


@pytest.mark.parametrize("index, fit_counts, validation_counts, reason", [
    (0, (6, 3, 2, 0), (0, 0, 0, 0), "class_labels:1"),
    (0, (6, 3, 3, 2), (0, 0, 0, 0), "state_diversity:0"),
    (0, (3, 3, 3, 3), (0, 0, 0, 0), None),
    (1, (20, 0, 0, 19), (10, 0, 0, 10), "search_class_starved"),
    (1, (35, 0, 0, 5), (10, 0, 0, 10), "search_class_starved"),
    (1, (20, 0, 0, 20), (10, 0, 0, 9), "heldout_starved"),
    (1, (20, 0, 0, 20), (10, 0, 0, 10), None),
    (2, (0, 34, 6, 0), (0, 10, 10, 0), None),
    (2, (0, 35, 5, 0), (0, 10, 10, 0), "search_class_starved"),
], ids=["hi-class", "hi-diversity", "hi-qualifies", "w-y-labels",
        "w-y-class", "w-y-validation", "w-y-qualifies", "m-c-qualifies",
        "m-c-class"])
def test_each_chain_map_refuses_below_its_floors(index, fit_counts,
                                                 validation_counts, reason):
    _h3_support.assert_measured(
        "cmy chain floors (marginal 6/2/3, conditional 40/6 + 20)",
        (color_model.CMY8_CALIBRATION_MIN_CLASS_LABELS,
         color_model.CMY8_CALIBRATION_MIN_STATES_PER_CLASS,
         color_model.CMY8_CALIBRATION_MIN_LABELS_PER_STATE,
         color_conditioning.CONDITIONED_MIN_LABELS,
         color_conditioning.CONDITIONED_MIN_CLASS_LABELS,
         color_conditioning.CONDITIONED_MIN_VALIDATION),
        (6, 2, 3, 40, 6, 20))
    assert color_chain.map_refusal(_columns(fit_counts),
                                   _columns(validation_counts),
                                   index) == reason


def test_an_unqualified_map_leaves_its_piece_to_the_raw_bounded_statistic():
    scores, columns, kinds, keys = _population(SIDE_TILE, 5)
    fit = color_chain.fit_cmy_chain(scores, columns, kinds, keys, (), BOUND)
    assert fit.map_reasons == ("adopted", "search_class_starved",
                               "search_class_starved")
    raw = 60.0 * scores
    hi_map = color_chain.fit_chain_map(scores, columns, 0)
    head = color_chain.CmyChain((hi_map, None, None), BOUND)
    applied = head.apply(raw)
    bounded = color_chain.bounded(raw, BOUND)
    assert np.max(np.abs(raw)) > BOUND
    zeros = np.zeros(raw.shape[0], np.uint8)
    assert np.allclose(tile_codec.cmy_soft_demap(applied, 0),
                       hi_map.llrs(color_chain.chain_statistic(raw, 0)),
                       rtol=0.0, atol=1e-9)
    assert np.array_equal(tile_codec.cmy_soft_demap(applied, 1, zeros),
                          bounded[:, 2])
    assert np.allclose(tile_codec.cmy_soft_demap(applied, 1, zeros + 1),
                       bounded[:, 0] - bounded[:, 1], rtol=0.0, atol=1e-9)


@pytest.mark.parametrize("erased", [(1,), (0,)], ids=["dead-lo", "dead-hi"])
def test_the_erasure_law_composes_with_the_chain(erased):
    """Through the lane's own emission (`evidence_with_divisor`: head,
    erasure, bound) over a real QDA: a dead lo fits L_hi alone and reads
    (L_hi, L_hi, 0) -- lo exactly 0.0 alone and given either hi; a dead hi
    takes no chain and reads the raw bounded lo statistic, (l, 0, l)."""
    columns = _columns((400, 400, 400, 400))
    features = MEANS[columns] + np.random.default_rng(7).normal(
        0.0, 1.0, (columns.size, 3))
    model = color_model.fit_qda(features, columns, 4,
                                color_model.CMY_COLUMN_LABEL_BITS)
    scores = color_model.cmy7_relative_scores(model, features)
    slot = np.arange(columns.size)
    keys = np.stack((np.zeros_like(slot), np.zeros_like(slot), 2 * slot),
                    axis=1)
    kinds = np.where(columns == 2, 1, 0).astype(np.int8)
    fit = color_chain.fit_cmy_chain(scores, columns, kinds, keys, erased,
                                    BOUND)
    lane = region_head.DetectorFit(
        model=model, detector=None, heldout_loss=0.0,
        word_heldout_loss=0.0, dust_heldout_loss=0.0, heldout_scores=None,
        heldout_states=None, heldout_keys=None, erased_streams=erased)
    zeros = np.zeros(columns.size, np.uint8)
    if erased == (0,):
        assert fit.head is None and fit.reason == "hi_erased"
        assert fit.map_reasons == ("stream_erased",) * 3
        values, _divisor = region_head.evidence_with_divisor(
            dataclasses.replace(lane, head=fit.head), features, None)
        assert np.all(tile_codec.cmy_soft_demap(values, 0) == 0.0)
        assert np.array_equal(values, color_chain.bounded(
            color_model.cmy_erase_streams(scores, erased), BOUND))
        return
    assert fit.map_reasons == ("adopted", "stream_erased", "stream_erased")
    fit_side = color_model.head_sub_split(keys)
    hi_map = color_chain.fit_chain_map(scores[fit_side], columns[fit_side],
                                       0)
    head = color_chain.CmyChain((hi_map, None, None), BOUND)
    values, _divisor = region_head.evidence_with_divisor(
        dataclasses.replace(lane, head=head), features, None)
    for given in (None, zeros, zeros + 1):
        assert np.all(tile_codec.cmy_soft_demap(values, 1, given) == 0.0)
    assert np.allclose(tile_codec.cmy_soft_demap(values, 0),
                       hi_map.llrs(color_chain.chain_statistic(scores, 0)),
                       rtol=0.0, atol=1e-9)


def test_a_chain_fitted_on_c_heavy_furniture_recovers_the_payload_prior():
    """Furniture's hi class is C-heavy (p120: C 50 : M 20 per tile, the
    balance law), the payload's is C : M = 1 : 1.  State-balanced, the
    C-heavy fit lands on the balanced population's map; class-balanced,
    it tilts toward C's statistic."""
    reference_scores, reference_columns, *_ = _side((40000,) * 4, 11, 0)
    tilted_scores, tilted_columns, *_ = _side((25000, 50000, 20000, 25000),
                                              12, 0)
    reference = color_chain.fit_chain_map(reference_scores,
                                          reference_columns, 0)
    balanced = color_chain.fit_chain_map(tilted_scores, tilted_columns, 0)
    _member, labels = color_chain.map_population(tilted_columns, 0)
    class_balanced = color_model.fit_component_pava(
        color_chain.chain_statistic(tilted_scores, 0), labels)
    grid = np.linspace(-6.0, 6.0, 241)

    def probability(fitted: color_model.PavaMap) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-fitted.llrs(grid)))

    state_dp = float(np.mean(np.abs(probability(balanced)
                                    - probability(reference))))
    class_dp = float(np.mean(np.abs(probability(class_balanced)
                                    - probability(reference))))
    _h3_support.assert_measured(
        "payload-prior mean |dp| (state-balanced, class-balanced)",
        (round(state_dp, 4), round(class_dp, 4)), (0.0059, 0.0334))


def test_the_gate_legs_are_the_4_state_nll_per_furniture_kind():
    scores = np.asarray(((2.0, -1.0, 0.5), (-3.0, 1.0, 0.0),
                         (0.0, 0.0, 4.0)))
    columns = np.asarray((1, 2, 3))
    logits = np.concatenate((np.zeros((3, 1)), scores), axis=1)
    nll = (np.log(np.exp(logits).sum(axis=1))
           - logits[np.arange(3), columns])
    total, word, dust = color_chain.gate_losses(
        scores, columns, np.asarray((0, 1, -1), np.int8))
    assert np.allclose((total, word, dust),
                       (nll.mean(), nll[0], nll[1]), rtol=1e-12)
    assert color_chain.gate_losses(
        scores, columns, np.full(3, -1, np.int8))[1:] == (np.inf, np.inf)


@pytest.mark.parametrize("scale, reason", [
    (1.0, "validation_gate_failed"), (50.0, "adopted")],
    ids=["calibrated-raw-kept", "overconfident-raw-replaced"])
def test_the_chain_is_adopted_only_through_the_three_way_gate(scale,
                                                              reason):
    scores, columns, kinds, keys = _population((500, 500, 500, 500), 3,
                                               scale)
    fit = color_chain.fit_cmy_chain(scores, columns, kinds, keys, (), BOUND)
    assert fit.map_reasons == ("adopted",) * 3
    assert fit.reason == reason
    assert (fit.head is not None) is (reason == "adopted")
    assert (fit.n_fit, fit.n_validation) == (2000, 2000)
    assert all(np.isfinite(fit.incumbent_nll))
    assert all(np.isfinite(fit.candidate_nll))
    better = fit.candidate_nll[0] < fit.incumbent_nll[0]
    assert better is (reason == "adopted")

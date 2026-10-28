"""Pure provisional CMY7/CMY8 mapper contracts and numerical oracles."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo.core import channel


# sha256(CMY7_CODEBOOK.tobytes(order="C")); uint8[2048,4].
# This is filled from the independently specified natural-radix convention
# and must change only with a new mapper version.
CMY7_CODEBOOK_SHA256 = (
    "c39e6cc5fd9d4637202aedf2e40db4ad"
    "0487ee3acf493700cea1d175a4dcd229"
)


def _bits_msb(value: int, width: int) -> np.ndarray:
    return ((value >> np.arange(width - 1, -1, -1)) & 1).astype(np.uint8)


def _logsumexp(values: np.ndarray) -> float:
    """Small test-only oracle, intentionally independent of logaddexp."""
    m = float(np.max(values))
    return m + float(np.log(np.exp(values - m).sum()))


def test_canonical_state_and_plane_order_exhaustive():
    expected_names = ("W", "C", "M", "CM", "Y", "CY", "MY", "CMY")
    expected_bits = np.asarray([
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [1, 1, 0],
        [0, 0, 1],
        [1, 0, 1],
        [0, 1, 1],
        [1, 1, 1],
    ], dtype=np.uint8)
    states = np.arange(8, dtype=np.uint8)

    assert channel.PLANE_ORDER == ("C", "M", "Y")
    assert channel.STATE_NAMES == expected_names
    assert tuple(int(s) for s in channel.CMYState) == tuple(range(8))
    assert np.array_equal(channel.states_to_planes(states), expected_bits)
    assert np.array_equal(channel.planes_to_states(expected_bits), states)

    grid = states.reshape(2, 4)
    assert channel.states_to_planes(grid).shape == (2, 4, 3)
    assert np.array_equal(
        channel.planes_to_states(channel.states_to_planes(grid)), grid
    )


def test_cmy8_direct_mapping_and_inverse_exhaustive():
    bits = channel.states_to_planes(np.arange(8, dtype=np.uint8))
    states = channel.cmy8_map(bits)
    assert np.array_equal(states, np.arange(8, dtype=np.uint8))
    assert np.array_equal(channel.cmy8_inverse(states), bits)


def test_cmy8_raw_marginal_llrs_match_brute_force():
    rng = np.random.default_rng(0xC8)
    rel = rng.normal(size=(9, 7))
    got = channel.cmy8_raw_marginal_llrs(rel)
    assert got.shape == (9, 3)

    state_bits = channel.states_to_planes(np.arange(8, dtype=np.uint8))
    want = np.empty_like(got)
    for row in range(rel.shape[0]):
        scores = np.concatenate(([0.0], rel[row]))
        for plane in range(3):
            want[row, plane] = (
                _logsumexp(scores[state_bits[:, plane] == 1])
                - _logsumexp(scores[state_bits[:, plane] == 0])
            )
    assert np.allclose(got, want, rtol=1e-13, atol=1e-13)


def test_cmy8_all_equal_state_scores_are_exact_erasures():
    # This is the raw equal-prior marginalization before historical PAVA.
    got = channel.cmy8_raw_marginal_llrs(
        np.zeros((5, 7), dtype=np.float64))
    assert np.array_equal(got, np.zeros((5, 3), dtype=np.float64))


def test_cmy8_raw_marginal_llr_signs_for_clear_states():
    for state in range(8):
        rel = np.full(7, -30.0)
        if state:
            rel[state - 1] = 30.0
        llr = channel.cmy8_raw_marginal_llrs(rel)
        assert np.array_equal(
            (llr > 0).astype(np.uint8),
            channel.states_to_planes(np.asarray(state)),
        )


def test_cmy7_table_order_digest_and_exhaustive_inverse():
    table = channel.CMY7_CODEBOOK
    assert table.shape == (2048, 4) and table.dtype == np.uint8
    assert not table.flags.writeable
    assert hashlib.sha256(table.tobytes(order="C")).hexdigest() == \
        CMY7_CODEBOOK_SHA256

    # Eleven bits and radix digits are both MSB-first.
    assert np.array_equal(table[0], [0, 0, 0, 0])
    assert np.array_equal(table[1], [0, 0, 0, 1])
    assert np.array_equal(table[7], [0, 0, 1, 0])
    assert np.array_equal(table[343], [1, 0, 0, 0])
    assert np.array_equal(table[2047], [5, 6, 5, 3])

    bits = np.stack([_bits_msb(i, 11) for i in range(2048)])
    assert np.array_equal(channel.cmy7_map(bits), table)
    assert np.array_equal(channel.cmy7_inverse(table), bits)
    assert channel.cmy7_map(bits[17]).shape == (4,)
    assert channel.cmy7_inverse(table[17]).shape == (11,)
    assert np.unique(table, axis=0).shape[0] == 2048
    assert int((channel.CMY7_INVERSE < 0).sum()) == 353


def test_cmy7_inverse_refuses_every_unused_tuple():
    tuples = np.stack(np.unravel_index(
        np.arange(7 ** 4), (7, 7, 7, 7)
    ), axis=-1).astype(np.uint8)
    used = channel.CMY7_INVERSE[tuple(tuples.T)] >= 0
    assert int((~used).sum()) == 353
    for states in tuples[~used]:
        with pytest.raises(ValueError, match="unused"):
            channel.cmy7_inverse(states)


def test_cmy7_soft_demap_matches_brute_force():
    rng = np.random.default_rng(0xC7)
    rel = rng.normal(size=(3, 4, 6))
    got = channel.cmy7_soft_demap(rel)
    assert got.shape == (3, 11)

    candidate_bits = np.stack([_bits_msb(i, 11) for i in range(2048)])
    want = np.empty_like(got)
    for pack in range(rel.shape[0]):
        scores = np.concatenate((np.zeros((4, 1)), rel[pack]), axis=1)
        metric = np.asarray([
            sum(scores[cell, state] for cell, state in enumerate(states))
            for states in channel.CMY7_CODEBOOK
        ])
        for bit in range(11):
            want[pack, bit] = (
                _logsumexp(metric[candidate_bits[:, bit] == 1])
                - _logsumexp(metric[candidate_bits[:, bit] == 0])
            )
    assert np.allclose(got, want, rtol=1e-13, atol=1e-13)


def test_cmy7_all_equal_state_scores_are_exact_erasures():
    got = channel.cmy7_soft_demap(np.zeros((5, 4, 6), dtype=np.float64))
    assert np.array_equal(got, np.zeros((5, 11), dtype=np.float64))


def test_cmy7_soft_demap_clear_codewords_have_correct_signs():
    for word in (0, 1, 7, 343, 1023, 2047):
        states = channel.CMY7_CODEBOOK[word]
        rel = np.full((4, 6), -40.0)
        for cell, state in enumerate(states):
            if state:
                rel[cell, state - 1] = 40.0
        llr = channel.cmy7_soft_demap(rel)
        assert np.array_equal(
            (llr > 0).astype(np.uint8), _bits_msb(word, 11)
        )


def test_cmy7_soft_demap_extreme_finite_scores_keep_log_domain_fallback():
    states = channel.CMY7_CODEBOOK[2047]
    rel = np.full((4, 6), -1000.0)
    for cell, state in enumerate(states):
        rel[cell, state - 1] = 1000.0

    got = channel.cmy7_soft_demap(rel)
    scores = np.concatenate((np.zeros((4, 1)), rel), axis=1)
    metric = np.asarray([
        sum(scores[cell, state] for cell, state in enumerate(candidate))
        for candidate in channel.CMY7_CODEBOOK
    ])
    candidate_bits = np.stack([
        _bits_msb(word, 11) for word in range(2048)])
    want = np.asarray([
        _logsumexp(metric[candidate_bits[:, bit] == 1])
        - _logsumexp(metric[candidate_bits[:, bit] == 0])
        for bit in range(11)
    ])

    assert np.isfinite(got).all()
    assert np.allclose(got, want, rtol=1e-13, atol=1e-13)


def test_cmy7_soft_demap_subnormal_transition_matches_stable_oracle():
    rel = np.random.default_rng(2).normal(
        size=(8, 4, 6)) * 700.0
    with np.errstate(under="raise"):
        got = channel.cmy7_soft_demap(rel)
    candidate_bits = np.stack([
        _bits_msb(word, 11) for word in range(2048)])
    want = np.empty_like(got)
    for pack, pack_scores in enumerate(rel):
        scores = np.concatenate(
            (np.zeros((4, 1)), pack_scores), axis=1)
        metric = np.asarray([
            sum(scores[cell, state]
                for cell, state in enumerate(candidate))
            for candidate in channel.CMY7_CODEBOOK
        ])
        for bit in range(11):
            want[pack, bit] = (
                _logsumexp(metric[candidate_bits[:, bit] == 1])
                - _logsumexp(metric[candidate_bits[:, bit] == 0])
            )

    assert np.isfinite(got).all()
    assert np.allclose(got, want, rtol=1e-13, atol=1e-13)


@pytest.mark.parametrize(
    ("call", "value", "message"),
    [
        (channel.planes_to_states, np.zeros((4, 2)), "final axis 3"),
        (channel.planes_to_states, np.asarray([0, 1, 2]), "only 0/1"),
        (channel.states_to_planes, np.asarray([8]), r"in \[0, 7\]"),
        (channel.cmy7_map, np.zeros((2, 10)), "final axis 11"),
        (channel.cmy7_map, np.asarray([[0] * 10 + [2]]), "only 0/1"),
        (channel.cmy7_inverse, np.zeros((3, 3)), "final axis 4"),
        (channel.cmy7_inverse, np.asarray([0, 0, 0, 7]), r"in \[0, 6\]"),
        (channel.cmy8_raw_marginal_llrs, np.zeros(6),
         r"trailing shape \(7\)"),
        (channel.cmy7_soft_demap, np.zeros((4, 7)),
         r"trailing shape \(4, 6\)"),
        (channel.cmy8_raw_marginal_llrs,
         np.zeros(7, dtype=np.complex128),
         "real numeric"),
        (channel.cmy7_soft_demap, np.zeros((4, 6), dtype=np.complex128),
         "real numeric"),
    ],
)
def test_shape_and_range_refusal(call, value, message):
    with pytest.raises(ValueError, match=message):
        call(value)


def _brute_force_prior_demap(rel, prior):
    """Reference marginalization with an a-priori vector, minus the prior."""
    metric = np.zeros(channel.CMY7_N_CANDIDATES)
    for word in range(channel.CMY7_N_CANDIDATES):
        digits = channel.CMY7_CODEBOOK[word]
        bits = [(word >> shift) & 1
                for shift in range(channel.CMY7_BITS_PER_PACK - 1, -1, -1)]
        total = 0.0
        for cell, state in enumerate(digits):
            if state:
                total += rel[cell, state - 1]
        for index, bit in enumerate(bits):
            if bit:
                total += prior[index]
        metric[word] = total
    out = np.empty(channel.CMY7_BITS_PER_PACK)
    for index in range(channel.CMY7_BITS_PER_PACK):
        mask = np.array(
            [(word >> (channel.CMY7_BITS_PER_PACK - 1 - index)) & 1
             for word in range(channel.CMY7_N_CANDIDATES)], bool)
        out[index] = (
            np.logaddexp.reduce(metric[mask])
            - np.logaddexp.reduce(metric[~mask])
            - prior[index])
    return out


def test_cmy7_soft_demap_prior_matches_brute_force():
    """P3: the prior enters every candidate metric and leaves the output."""
    rng = np.random.default_rng(31415)
    rel = rng.normal(0.0, 3.0, (channel.CMY7_CELLS_PER_PACK, 6))
    prior = rng.normal(0.0, 2.0, channel.CMY7_BITS_PER_PACK)
    got = channel.cmy7_soft_demap(rel, prior)
    assert np.allclose(got, _brute_force_prior_demap(rel, prior), atol=1e-9)


def test_cmy7_soft_demap_zero_prior_is_the_pinned_null():
    """DEMAP_ITERATIONS == 1 must be today's path, byte for byte."""
    rng = np.random.default_rng(2718)
    rel = rng.normal(0.0, 4.0, (17, channel.CMY7_CELLS_PER_PACK, 6))
    reference = channel.cmy7_soft_demap(rel)
    with_zero = channel.cmy7_soft_demap(
        rel, np.zeros(rel.shape[:-2] + (channel.CMY7_BITS_PER_PACK,)))
    assert np.array_equal(reference, with_zero)


def test_cmy7_prior_alone_carries_no_extrinsic():
    """The codebook realizes all 2,048 patterns, so a prior factorizes."""
    rng = np.random.default_rng(1618)
    prior = rng.normal(0.0, 6.0, (5, channel.CMY7_BITS_PER_PACK))
    got = channel.cmy7_soft_demap(
        np.zeros((5, channel.CMY7_CELLS_PER_PACK, 6)), prior)
    assert np.abs(got).max() < 1e-9


def test_state_score_margins_are_top1_minus_top2():
    rel = np.asarray([
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],      # every state ties W
        [5.0, 2.0, 1.0, 0.0, -1.0, -2.0],    # winner state 1 over state 2
        [-4.0, -9.0, -9.0, -9.0, -9.0, -9.0],  # W wins over state 1
    ])
    got = channel.state_score_margins(rel)
    assert np.allclose(got, [0.0, 3.0, 4.0])
    assert (got >= 0.0).all()


def test_prior_shape_and_finiteness_are_refused():
    rel = np.zeros((3, channel.CMY7_CELLS_PER_PACK, 6))
    with pytest.raises(ValueError, match="prior_bit_llrs must have shape"):
        channel.cmy7_soft_demap(rel, np.zeros((3, 10)))
    bad = np.zeros((3, channel.CMY7_BITS_PER_PACK))
    bad[0, 0] = np.inf
    with pytest.raises(ValueError, match="only finite"):
        channel.cmy7_soft_demap(rel, bad)

from __future__ import annotations

import functools
import hashlib

import numpy as np
import pytest

from holo.receiver.lib import bch
from holo.receiver.tests import _h3_support

GF_PRIM_POLY = 0x89
N_FULL = 127
K_FULL = 50
T = 13
D_MIN = 27
SHORTEN_BY = 27
N_WORD = 100
K_MSG = 23
N_PARITY = 77

GENERATOR_POLY_COEFFICIENTS = 78
GENERATOR_POLY_SHA256 = (
    "a0be5064cfef57b2a84aaadbd7bd13b9"
    "772b1259fa041c25af0d7bde4922b684")
GENERATOR_POLY_INT = 0x2C9352AA6CC054468311

# frozen 2026-08-29: CLAUDE.md "true min distance d=27 EXACT (spectrum 27:3,
# 28:8, 31:119, 32:247)", extended to weight 40 by the exhaustive sweep
WEIGHT_SPECTRUM_TO_40 = {
    27: 3, 28: 8, 31: 119, 32: 247,
    35: 1613, 36: 2668, 39: 9551, 40: 13205}
WEIGHT_27_MESSAGES = (39936, 79872, 159744)

COUNTER_BITS = 18
PAD_BITS = 5

ERASURE_BUDGET = 2 * T

CORPUS_FAST = 1200
CORPUS_SWEEP = 20000


def _message_bits(counter: int, pad: int = 0) -> np.ndarray:
    bits = np.zeros(K_MSG, np.uint8)
    for index in range(COUNTER_BITS):
        bits[index] = (counter >> index) & 1
    for index in range(PAD_BITS):
        bits[COUNTER_BITS + index] = (pad >> index) & 1
    return bits


def _counter_from_message(bits: np.ndarray) -> int:
    return sum(int(bits[index]) << index for index in range(COUNTER_BITS))


def _pad_from_message(bits: np.ndarray) -> int:
    return sum(int(bits[COUNTER_BITS + index]) << index
               for index in range(PAD_BITS))


def _corrupt(rng: np.random.Generator, word: np.ndarray,
             n_errors: int) -> np.ndarray:
    bad = word.copy()
    bad[rng.choice(N_WORD, size=n_errors, replace=False)] ^= 1
    return bad


@functools.lru_cache(maxsize=2)
def _corpus(n_rows: int) -> np.ndarray:
    rng = np.random.default_rng(20260829)
    words = np.empty((n_rows, N_WORD), np.uint8)
    half = n_rows // 2
    words[:half] = rng.integers(0, 2, size=(half, N_WORD))
    for row in range(half, n_rows):
        message = rng.integers(0, 2, size=K_MSG).astype(np.uint8)
        words[row] = _corrupt(rng, bch.encode(message),
                              int(rng.integers(0, 16)))
    words[0] = 0
    words.setflags(write=False)
    return words


def _corpus_rows() -> int:
    return CORPUS_SWEEP if _h3_support.oracle_sweeps() else CORPUS_FAST


def _same(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is None and right is None
    left_word, left_errors = left
    right_word, right_errors = right
    return (int(left_errors) == int(right_errors)
            and left_word.dtype == np.uint8
            and np.array_equal(left_word, right_word))


def test_shortened_bch_constants_are_the_frozen_format_law():
    assert (bch.GF_PRIM_POLY, bch.N_FULL, bch.K_FULL) == (
        GF_PRIM_POLY, N_FULL, K_FULL)
    assert (bch.T, bch.D_MIN, bch.SHORTEN_BY) == (T, D_MIN, SHORTEN_BY)
    assert (bch.N_WORD, bch.K_MSG, bch.N_PARITY) == (N_WORD, K_MSG, N_PARITY)
    assert bch.N_WORD == bch.N_FULL - bch.SHORTEN_BY
    assert bch.K_MSG == bch.K_FULL - bch.SHORTEN_BY
    assert bch.K_MSG == COUNTER_BITS + PAD_BITS


def test_generator_polynomial_digest_is_the_format_fork_alarm():
    poly = bch.generator_poly()
    assert poly.dtype == np.uint8
    assert poly.size == GENERATOR_POLY_COEFFICIENTS
    _h3_support.assert_golden(
        "generator_poly sha256",
        hashlib.sha256(poly.tobytes()).hexdigest(), GENERATOR_POLY_SHA256)
    _h3_support.assert_golden(
        "generator_poly integer form",
        sum(int(value) << index for index, value in enumerate(poly)),
        GENERATOR_POLY_INT)
    assert int(poly[0]) == 1 and int(poly[-1]) == 1


def test_generator_poly_hands_back_a_copy_not_the_module_table():
    first = bch.generator_poly()
    first[0] ^= 1
    assert int(bch.generator_poly()[0]) == 1


def test_galois_field_tables_close_the_multiplicative_group():
    assert bch._EXP.size == 127 and bch._LOG.size == 128
    assert int(bch._EXP[0]) == 1
    assert sorted(int(value) for value in bch._EXP) == list(range(1, 128))
    for power in range(127):
        assert int(bch._LOG[bch._EXP[power]]) == power


def _codeword_weight(message_int: int) -> int:
    parity = bch._polymod2(message_int << N_PARITY, bch._GPOLY_INT)
    return parity.bit_count() + message_int.bit_count()


def test_the_fast_weight_route_agrees_with_the_public_encoder():
    rng = np.random.default_rng(20260829)
    for message_int in rng.integers(1, 1 << 18, size=200).tolist():
        bits = np.zeros(K_MSG, np.uint8)
        for index in range(K_MSG):
            bits[index] = (int(message_int) >> index) & 1
        assert _codeword_weight(int(message_int)) == int(
            bch.encode(bits).sum())


def test_exhaustive_sweep_pins_true_minimum_distance_27_and_the_spectrum():
    counts: dict[int, int] = {}
    light: dict[int, list[int]] = {}
    for message_int in range(1, 1 << 18):
        weight = _codeword_weight(message_int)
        counts[weight] = counts.get(weight, 0) + 1
        if weight <= 28:
            light.setdefault(weight, []).append(message_int)
    _h3_support.assert_golden(
        "weight spectrum to 40",
        {weight: n for weight, n in counts.items() if weight <= 40},
        WEIGHT_SPECTRUM_TO_40)
    assert min(counts) == D_MIN == 2 * T + 1
    _h3_support.assert_golden(
        "weight-27 messages", tuple(light[27]), WEIGHT_27_MESSAGES)
    assert sum(counts.values()) == (1 << 18) - 1


def test_encode_is_systematic_with_parity_first_and_message_last():
    rng = np.random.default_rng(20260829)
    for _ in range(64):
        message = rng.integers(0, 2, size=K_MSG).astype(np.uint8)
        word = bch.encode(message)
        assert word.dtype == np.uint8 and word.shape == (N_WORD,)
        assert np.array_equal(word[N_PARITY:], message)
        assert np.array_equal(bch.message_from_word(word), message)
        assert not bch.syndromes(word).any()


def test_address_counter_round_trip_carries_the_five_known_zero_pads():
    rng = np.random.default_rng(20260829)
    ladder = [0, 1, 2, 3, 131071, 262142, (1 << 18) - 1]
    ladder.extend(int(value) for value in
                  rng.integers(0, 1 << 18, size=32).tolist())
    for counter in ladder:
        word = bch.encode(_message_bits(counter))
        recovered = bch.message_from_word(word)
        assert _counter_from_message(recovered) == counter
        assert _pad_from_message(recovered) == 0
        decoded = bch.decode(_corrupt(np.random.default_rng(counter + 1),
                                      word, T))
        assert decoded is not None and decoded[1] == T
        assert _counter_from_message(
            bch.message_from_word(decoded[0])) == counter


@pytest.mark.parametrize("pad, expected_pad", [(0, 0), (1, 1), (16, 16),
                                               (31, 31)])
def test_a_nonzero_pad_is_not_the_bch_layers_business(pad, expected_pad):
    word = bch.encode(_message_bits(4242, pad))
    decoded = bch.decode(word)
    assert decoded is not None and decoded[1] == 0
    recovered = bch.message_from_word(decoded[0])
    assert _counter_from_message(recovered) == 4242
    assert _pad_from_message(recovered) == expected_pad


@pytest.mark.parametrize("n_errors, outcome", [
    (0, "corrected"), (1, "corrected"), (2, "corrected"), (5, "corrected"),
    (12, "corrected"), (13, "corrected"), (14, "refused"), (15, "refused")])
def test_decode_corrects_up_to_t_and_refuses_beyond(n_errors, outcome):
    rng = np.random.default_rng(20260829 + n_errors)
    for _ in range(60):
        message = rng.integers(0, 2, size=K_MSG).astype(np.uint8)
        word = bch.encode(message)
        decoded = bch.decode(_corrupt(rng, word, n_errors))
        if outcome == "refused":
            assert decoded is None
            continue
        assert decoded is not None
        assert np.array_equal(decoded[0], word)
        assert decoded[1] == n_errors


def test_decode_never_claims_more_than_t_corrections():
    words = _corpus(CORPUS_FAST)
    for row in range(words.shape[0]):
        decoded = bch.decode(words[row])
        if decoded is None:
            continue
        assert 0 <= decoded[1] <= T
        assert not bch.syndromes(decoded[0]).any()


def test_erasure_budget_is_two_errors_plus_erasures_at_most_26():
    word = bch.encode(np.ones(K_MSG, dtype=np.uint8))
    zero = np.zeros(N_WORD, dtype=np.uint8)
    assert bch.decode_erasures(zero, np.arange(ERASURE_BUDGET + 1)) is None
    at_budget = word.copy()
    at_budget[:26] ^= 1
    accepted = bch.decode_erasures(at_budget, np.arange(26, dtype=np.int64))
    assert accepted is not None and accepted[1] == 0
    assert np.array_equal(accepted[0], word)
    one_error = word.copy()
    one_error[:24] ^= 1
    one_error[50] ^= 1
    mixed = bch.decode_erasures(one_error, np.arange(24, dtype=np.int64))
    assert mixed is not None and mixed[1] == 1
    assert np.array_equal(mixed[0], word)
    two_errors = word.copy()
    two_errors[:24] ^= 1
    two_errors[[50, 60]] ^= 1
    assert bch.decode_erasures(
        two_errors, np.arange(24, dtype=np.int64)) is None


def test_zero_erasures_delegates_to_the_plain_decoder():
    rng = np.random.default_rng(20260829)
    word = bch.encode(rng.integers(0, 2, size=K_MSG).astype(np.uint8))
    bad = _corrupt(rng, word, 9)
    assert _same(bch.decode_erasures(bad, np.zeros(0, np.int64)),
                 bch.decode(bad))


def test_duplicate_erasure_indices_collapse_before_the_budget_check():
    word = bch.encode(np.ones(K_MSG, dtype=np.uint8))
    doubled = np.concatenate([np.arange(26, dtype=np.int64)] * 2)
    punched = word.copy()
    punched[:26] ^= 1
    accepted = bch.decode_erasures(punched, doubled)
    assert accepted is not None and np.array_equal(accepted[0], word)


def test_syndromes_many_matches_the_scalar_syndrome_row_for_row():
    words = _corpus(CORPUS_FAST)
    batched = bch.syndromes_many(words)
    assert batched.shape == (words.shape[0], 2 * T)
    assert batched.dtype == np.uint8
    for row in range(words.shape[0]):
        assert np.array_equal(batched[row], bch.syndromes(words[row]))
    assert np.array_equal(bch.syndromes(np.zeros(N_WORD, np.uint8)),
                          np.zeros(2 * T, np.uint8))


def test_batch_berlekamp_massey_and_chien_match_the_scalar_derivation():
    words = _corpus(CORPUS_FAST)
    syndrome_rows = bch.syndromes_many(words)
    dirty = np.flatnonzero(syndrome_rows.any(axis=1))
    sigma, trimmed, lengths = bch.berlekamp_massey_many(
        syndrome_rows[dirty])
    checks = _h3_support.Checks("batch bm/chien vs scalar")
    for slot, row in enumerate(dirty.tolist()):
        scalar_sigma, scalar_length = bch._berlekamp_massey(
            [int(value) for value in syndrome_rows[row]])
        checks.equal(f"row {row} lfsr length",
                     int(lengths[slot]), scalar_length)
        checks.equal(f"row {row} sigma",
                     sigma[slot, :int(trimmed[slot])].tolist(), scalar_sigma)
    kept = np.flatnonzero((lengths <= T) & (trimmed - 1 == lengths))
    mask = bch.chien_root_mask(sigma[kept][:, :bch._SIGMA_WIDTH])
    checks.equal("chien mask width", mask.shape[1], N_FULL)
    for slot, keep in enumerate(kept.tolist()):
        expected = np.zeros(N_FULL, bool)
        expected[bch._chien_roots(
            sigma[keep, :int(trimmed[keep])].tolist())] = True
        checks.check(f"chien row {keep}",
                     bool(np.array_equal(mask[slot], expected)))
    assert checks.n_total > 2 * dirty.size
    checks.assert_clean()


def test_decode_many_matches_the_scalar_decoder_including_refusals():
    words = _corpus(_corpus_rows())
    batched = bch.decode_many(words)
    assert len(batched) == words.shape[0]
    n_decoded = 0
    for row in range(words.shape[0]):
        scalar = bch.decode(words[row])
        assert _same(batched[row], scalar), f"row {row}"
        n_decoded += batched[row] is not None
    assert n_decoded > words.shape[0] // 4
    assert batched[0] is not None and batched[0][1] == 0


def test_decode_many_on_an_empty_batch_returns_an_empty_list():
    assert bch.decode_many(np.zeros((0, N_WORD), np.uint8)) == []

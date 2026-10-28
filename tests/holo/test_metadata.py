import numpy as np
import pytest

from holo.format import metadata


def _observations(word, counters):
    counters = np.asarray(counters, dtype=np.int64)
    bits = metadata.tile_bits(word, counters)
    return list(zip(counters.tolist(), bits.tolist()))


def _rank(masks):
    basis = {}
    for value in masks:
        row = int(value)
        while row:
            pivot = (row & -row).bit_length() - 1
            if pivot not in basis:
                basis[pivot] = row
                break
            row ^= basis[pivot]
    return len(basis)


def test_encode_layout_explicit():
    word = metadata.encode_metadata(1, 1)
    assert word.shape == (metadata.METADATA_BITS,)
    assert word.dtype == np.uint8
    assert word[0] == 1
    assert word[18] == 1
    assert word[1:18].sum() == 0
    assert word[19:].sum() == 0
    word = metadata.encode_metadata(0, 1 << (metadata.K_BITS - 1))
    assert word[0] == 0 and word[1] == 1 and word[2:].sum() == 0


def test_encode_validation():
    for version in (-1, 2, 7):
        with pytest.raises(ValueError):
            metadata.encode_metadata(version, 1)
    for k in (0, -3, metadata.MAX_K, metadata.MAX_K + 1):
        with pytest.raises(ValueError):
            metadata.encode_metadata(0, k)
    assert metadata.encode_metadata(
        0, metadata.MAX_K - 1)[1:1 + metadata.K_BITS].all()


def test_lfsr_polynomial_and_coefficient_goldens():
    assert metadata.LFSR_POLYNOMIAL == 0x100001B
    assert metadata.LFSR_INITIAL_STATE == 1
    expected = {
        0: 0x000001, 1: 0x000002, 23: 0x800000, 24: 0x00001B,
        25: 0x000036, 100: 0x110110, 839: 0xB3D0BA,
        840: 0x67A16F, 1871: 0x64260E, 1872: 0xC84C1C,
        262079: 0xEFC994,
    }
    assert {counter: metadata.coefficient_mask(counter)
            for counter in expected} == expected


def test_all_addressable_rows_are_nonzero_and_unique():
    masks = metadata.coefficient_masks(
        np.arange(metadata.MAX_COUNTER, dtype=np.int64))
    assert not np.any(masks == 0)
    assert np.unique(masks).size == metadata.MAX_COUNTER


@pytest.mark.parametrize("start", [0, 1, 23, 24, 839, 840, 1871,
                                    1872, metadata.MAX_COUNTER - 24])
def test_every_24_consecutive_counters_are_a_basis(start):
    counters = np.arange(start, start + metadata.METADATA_BITS)
    assert _rank(metadata.coefficient_masks(counters)) == 24


def test_tile_placement_is_exactly_one_bit_and_vectorized():
    word = metadata.encode_metadata(1, 0x2AAAA)
    counters = np.array([0, 1, 23, 24, 100, 839, 840, 1871, 1872, 262079])
    bits = metadata.tile_bits(word, counters)
    assert bits.shape == counters.shape and bits.dtype == np.uint8
    assert bits.tolist() == [metadata.tile_bit(word, int(counter))
                             for counter in counters]
    assert bits.tolist() == [1, 1, 0, 1, 0, 0, 1, 0, 0, 0]


@pytest.mark.parametrize("version,k", [
    (0, 1), (1, 1), (0, 137), (1, 262143), (0, 0x2AAAA),
])
def test_round_trip_from_addressed_equations(version, k):
    word = metadata.encode_metadata(version, k)
    counters = np.arange(700, 700 + metadata.MIN_METADATA_EQUATIONS)
    res = metadata.decode_metadata(_observations(word, counters))
    assert res.ok and res.reason is None and not res.inconsistent
    assert (res.version, res.k) == (version, k)
    assert res.rank == 24
    assert res.n_unique_counters == metadata.MIN_METADATA_EQUATIONS
    assert res.rank_shortfall == 0 and res.check_shortfall == 0
    assert res.word == tuple(int(bit) for bit in word)


def test_hundreds_of_noncontiguous_tiles_recover():
    word = metadata.encode_metadata(0, 99173)
    counters = np.random.default_rng(73).choice(
        metadata.MAX_COUNTER, size=300, replace=False)
    res = metadata.decode_metadata(_observations(word, counters))
    assert res.ok and (res.version, res.k) == (0, 99173)
    assert res.rank == 24 and res.n_unique_counters == 300


def test_full_rank_below_consistency_floor_is_not_yet_trusted():
    word = metadata.encode_metadata(1, 4242)
    counters = np.arange(metadata.METADATA_BITS)
    res = metadata.decode_metadata(_observations(word, counters))
    assert not res.ok and not res.inconsistent
    assert res.rank == 24 and res.check_shortfall == 24
    assert (res.version, res.k) == (1, 4242)
    assert "48 distinct" in res.reason


def test_rank_deficient_set_is_incomplete():
    word = metadata.encode_metadata(0, 99)
    counters = np.arange(metadata.METADATA_BITS - 1)
    res = metadata.decode_metadata(_observations(word, counters))
    assert not res.ok and not res.inconsistent
    assert res.rank == 23 and res.rank_shortfall == 1
    assert res.version is None and res.k is None


def test_48_distinct_rows_do_not_bypass_rank_requirement():
    word = metadata.encode_metadata(0, 99)
    counters = np.array([
        *range(23), *range(24, 43), 45, *range(48, 53),
    ])
    assert counters.size == metadata.MIN_METADATA_EQUATIONS
    assert _rank(metadata.coefficient_masks(counters)) == 23
    res = metadata.decode_metadata(_observations(word, counters))
    assert not res.ok and not res.inconsistent
    assert res.rank == 23 and res.rank_shortfall == 1
    assert res.check_shortfall == 0


def test_duplicate_same_equation_is_harmless_but_does_not_add_checks():
    word = metadata.encode_metadata(0, 99)
    observations = _observations(word, np.arange(48))
    observations.extend([observations[7]] * 20)
    res = metadata.decode_metadata(observations)
    assert res.ok
    assert res.n_observations == 68 and res.n_unique_counters == 48


def test_opposite_duplicate_is_integrity_failure():
    word = metadata.encode_metadata(1, 4242)
    observations = _observations(word, np.arange(48))
    counter, bit = observations[7]
    observations.append((counter, 1 - bit))
    res = metadata.decode_metadata(observations)
    assert not res.ok and res.inconsistent
    assert "disagree" in res.reason and "7" in res.reason


def test_dependent_equation_contradiction_is_integrity_failure():
    word = metadata.encode_metadata(1, 4242)
    observations = _observations(word, np.arange(48))
    counter, bit = observations[-1]
    observations[-1] = (counter, 1 - bit)
    res = metadata.decode_metadata(observations)
    assert not res.ok and res.inconsistent
    assert "inconsistent" in res.reason


def test_reserved_nonzero_refused():
    word = metadata.encode_metadata(1, 555)
    word[20] = 1
    res = metadata.decode_metadata(_observations(word, np.arange(48)))
    assert not res.ok and not res.inconsistent
    assert "reserved" in res.reason and "20" in res.reason
    assert (res.version, res.k) == (1, 555)


def test_decoded_k_zero_refused():
    word = np.zeros(metadata.METADATA_BITS, dtype=np.uint8)
    res = metadata.decode_metadata(_observations(word, np.arange(48)))
    assert not res.ok and "K = 0" in res.reason


def test_counter_and_observation_validation():
    word = metadata.encode_metadata(0, 1)
    for counter in (-1, metadata.MAX_COUNTER):
        with pytest.raises(ValueError):
            metadata.tile_bit(word, counter)
    with pytest.raises(TypeError):
        metadata.coefficient_mask(1.5)
    with pytest.raises(ValueError):
        metadata.decode_metadata([(0, 2)])
    with pytest.raises(ValueError):
        metadata.decode_metadata([(0, 0, 1)])

from __future__ import annotations

import numpy as np
import pytest

from holo3.format import metadata as md

from holo3.tests import _h3_support

# hand-copied second copy of tests/holo/test_metadata.py
COEFFICIENT_GOLDEN = {
    0: 0x000001, 1: 0x000002, 23: 0x800000, 24: 0x00001B,
    25: 0x000036, 100: 0x110110, 839: 0xB3D0BA,
    840: 0x67A16F, 1871: 0x64260E, 1872: 0xC84C1C,
    262079: 0xEFC994,
}


def _word(version: int, k: int) -> int:
    word = version & 1
    for i in range(md.K_BITS):
        word |= ((k >> (md.K_BITS - 1 - i)) & 1) << (1 + i)
    return word


def _bit(word: int, index: int, max_index: int = md.MAX_COUNTER) -> int:
    mask = int(md.coefficient_table(max_index)[index])
    return (mask & word).bit_count() & 1


def _equations(word: int, indices, max_index: int = md.MAX_COUNTER) -> dict:
    return {int(index): _bit(word, int(index), max_index)
            for index in indices}


def test_frozen_constants():
    assert md.METADATA_BITS == 24
    assert md.VERSION_BITS == 1
    assert md.K_BITS == 18
    assert md.RESERVED_BITS == 5
    assert md.VERSION_BITS + md.K_BITS + md.RESERVED_BITS == md.METADATA_BITS
    assert md.MAX_K == 1 << 18
    assert md.VALID_VERSIONS == (0, 1)
    assert md.SUPPORTED_METADATA_VERSIONS == frozenset({0})
    assert md.COUNTER_BITS == 18
    assert md.MAX_COUNTER == 1 << 18
    assert md.MIN_METADATA_EQUATIONS == 48
    assert md.LFSR_POLYNOMIAL == 0x100001B
    assert md.LFSR_FEEDBACK == 0x00001B
    assert md.LFSR_INITIAL_STATE == 1


def test_coefficient_table_golden_entries():
    table = md.coefficient_table(md.MAX_COUNTER)
    got = {index: int(table[index]) for index in COEFFICIENT_GOLDEN}
    _h3_support.assert_golden("coefficient masks", got, COEFFICIENT_GOLDEN)


def test_coefficient_table_is_a_maximal_length_lfsr_orbit():
    table = md.coefficient_table(md.MAX_COUNTER)
    assert table.dtype == np.uint32
    assert table.shape == (md.MAX_COUNTER,)
    assert not table.flags.writeable
    assert int(table.min()) > 0
    assert np.unique(table).size == md.MAX_COUNTER
    assert int(table.max()) < 1 << md.METADATA_BITS


def test_coefficient_table_recurrence_is_shift_xor_feedback():
    table = md.coefficient_table(md.MAX_COUNTER)
    state = md.LFSR_INITIAL_STATE
    for index in range(64):
        assert int(table[index]) == state
        top = state & (1 << (md.METADATA_BITS - 1))
        state = ((state << 1) & ((1 << md.METADATA_BITS) - 1)) ^ (
            md.LFSR_FEEDBACK if top else 0)


def _rank(masks) -> int:
    basis: dict[int, int] = {}
    for value in masks:
        row = int(value)
        while row:
            pivot = (row & -row).bit_length() - 1
            if pivot not in basis:
                basis[pivot] = row
                break
            row ^= basis[pivot]
    return len(basis)


def test_every_twenty_four_consecutive_indices_span_the_word_space():
    table = md.coefficient_table(md.MAX_COUNTER)
    rng = np.random.default_rng(20260829)
    starts = [0, 1, 23, 1871, md.MAX_COUNTER - 24]
    starts += _h3_support.subsample(
        rng, range(md.MAX_COUNTER - 24), 27)
    for start in starts:
        assert _rank(table[int(start):int(start) + 24]) == 24
    assert _rank(table[0:23]) == 23


@pytest.mark.parametrize("n_streams", [1, 2, 3, 63])
def test_equation_index_is_counter_times_streams_plus_stream(n_streams: int):
    assert md.max_equation_index(n_streams) == n_streams * md.MAX_COUNTER
    for counter in (0, 1, 7, md.MAX_COUNTER - 1):
        for stream in range(min(n_streams, 4)):
            assert md.equation_index(counter, stream, n_streams) == \
                counter * n_streams + stream
    assert md.equation_index(7, 0, 1) == 7


def test_equation_index_space_is_bounded_by_the_lfsr_period():
    with pytest.raises(ValueError, match="nonzero state budget"):
        md.max_equation_index(64)
    assert md.max_equation_index(63) < (1 << md.METADATA_BITS) - 1


def test_full_rank_and_forty_eight_equations_recover_the_word():
    word = _word(0, 1961)
    result = md.decode_metadata(_equations(word, range(60)))
    assert result.ok
    assert result.version == 0
    assert result.k == 1961
    assert result.rank == 24
    assert result.n_unique == 60
    assert not result.inconsistent


def test_scattered_equation_indices_recover_the_word():
    word = _word(0, 99083)
    result = md.decode_metadata(_equations(word, [7 * i + 3
                                                  for i in range(100)]))
    assert result.ok and result.k == 99083 and result.rank == 24


@pytest.mark.parametrize("n_equations,expect_ok,expect_rank,expect_k", [
    (20, False, 20, None),
    (24, False, 24, 1961),
    (47, False, 24, 1961),
    (48, True, 24, 1961),
    (49, True, 24, 1961),
])
def test_the_trust_gate_is_rank_twenty_four_and_forty_eight_equations(
        n_equations: int, expect_ok: bool, expect_rank: int,
        expect_k: int | None):
    word = _word(0, 1961)
    result = md.decode_metadata(_equations(word, range(n_equations)))
    assert result.rank == expect_rank
    assert result.n_unique == n_equations
    assert result.ok is expect_ok
    assert result.k == expect_k


def test_rank_alone_is_not_enough_even_with_many_repeats_of_one_index():
    word = _word(0, 1961)
    equations = _equations(word, range(24))
    result = md.decode_metadata(equations)
    assert result.rank == 24 and result.n_unique == 24 and not result.ok
    assert result.k == 1961


def test_the_equation_state_is_dict_keyed_so_a_duplicate_cannot_be_carried():
    word = _word(0, 1961)
    indices = list(range(60)) * 3
    equations = _equations(word, indices)
    assert len(equations) == 60
    result = md.decode_metadata(equations)
    assert result.ok and result.n_unique == 60


def test_a_contradictory_dependent_equation_is_fatal_not_merely_open():
    word = _word(0, 1961)
    equations = _equations(word, range(60))
    equations[59] ^= 1
    result = md.decode_metadata(equations)
    assert result.inconsistent
    assert not result.ok
    assert result.k is None and result.version is None


def test_an_opposite_bit_at_the_version_pivot_moves_no_k():
    word = _word(0, 1961)
    equations = _equations(word, range(60))
    assert int(md.coefficient_table(md.MAX_COUNTER)[0]) == 1
    equations[0] ^= 1
    result = md.decode_metadata(equations)
    assert result.inconsistent
    assert not result.ok
    assert result.k is None and result.version is None


@pytest.mark.parametrize("k", [1, 2, 1961, 99083, md.MAX_K - 1])
def test_k_round_trips_over_the_whole_declared_range(k: int):
    result = md.decode_metadata(_equations(_word(0, k), range(60)))
    assert result.ok and result.k == k


def test_zero_k_is_refused():
    result = md.decode_metadata(_equations(0, range(60)))
    assert not result.ok and result.k == 0 and result.rank == 24


def test_nonzero_reserved_bits_are_refused():
    word = _word(0, 1234) | (1 << 20)
    result = md.decode_metadata(_equations(word, range(60)))
    assert not result.ok and result.rank == 24 and not result.inconsistent


def test_version_one_is_refused_inside_the_decoder():
    word = _word(1, 5000)
    result = md.decode_metadata(_equations(word, range(60)))
    assert result.version == 1
    assert result.k == 5000
    assert result.rank == 24
    assert not result.inconsistent
    assert not result.ok
    assert 1 not in md.SUPPORTED_METADATA_VERSIONS


def test_empty_equation_set_has_rank_zero():
    result = md.decode_metadata({})
    assert not result.ok and result.rank == 0 and result.n_unique == 0
    assert result.version is None and result.k is None


def test_pooled_rows_carry_one_distinct_equation_per_stream():
    max_index = md.max_equation_index(3)
    word = _word(0, 600)
    healthy = [md.equation_index(c, s, 3)
               for c in range(20) for s in range(3)]
    result = md.decode_metadata(_equations(word, healthy, max_index),
                                max_index)
    assert result.ok and result.k == 600 and result.n_unique == 60


def test_a_dead_plane_still_closes_from_a_punctured_index_set():
    max_index = md.max_equation_index(3)
    word = _word(0, 600)
    dead_y = [md.equation_index(c, s, 3)
              for c in range(40) for s in (0, 1)]
    result = md.decode_metadata(_equations(word, dead_y, max_index),
                                max_index)
    assert result.ok and result.k == 600 and result.n_unique == 80
    starved = md.decode_metadata(
        _equations(word, dead_y[:40], max_index), max_index)
    assert starved.n_unique == 40 and not starved.ok


def test_pooled_and_single_stream_tables_agree_on_the_shared_prefix():
    single = md.coefficient_table(md.MAX_COUNTER)
    pooled = md.coefficient_table(3 * md.MAX_COUNTER)
    assert np.array_equal(pooled[:md.MAX_COUNTER], single)
    assert pooled.shape == (3 * md.MAX_COUNTER,)
    assert int(pooled.min()) > 0

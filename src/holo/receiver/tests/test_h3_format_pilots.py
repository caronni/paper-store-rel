from __future__ import annotations

import hashlib
from collections import Counter

import numpy as np
import pytest

from holo.receiver.format import identity, keystream, pilots
from holo.receiver.lib import bch

from holo.receiver.tests import _h3_support

P100 = b"holo/v1/sites/p100"
P120 = b"holo/v1/sites/p120"
ROW = b"holo/v1/c2-r0550/3328x2304"
OTHER_ROW = b"holo/v1/c3-r0550/2240x1536"

# hand-copied second copy of tests/holo/test_pilots.py
GOLDEN_SITES_P100 = ("bdc8747a748669fe226cda7967c544ee"
                     "4cc7fc62ce69d63f26839fdffd823506")

# hand-copied second copy of tests/holo/test_color_format_profiles.py
P120_SITE_GOLDENS = {
    "word": "cf0d835ffed25402287d2066c71df537"
            "fe227630ced2fe53388eb17dc49f7e08",
    "dust": "cc6f32e5cdfb336e82b1cf0bc050b10"
            "d66dfdb7ff455bb7a81fd26ee7fe41aed",
    "payload": "361489054477d2df0300d1886f84946d"
               "d43ae080cac0f0941711b5ab1c624584",
}

ROW_VALUE_GOLDENS = {
    "c2-cmy7-p120-v0@3328x2304": (
        "9a8b7c9d8ff92a8cc5b141669f7831af"
        "4d3b5992b6b7bfd610431e5805648ba7",
        "f396f407fb9a04518014e839722f2868b"
        "ae99c764c968bb5a26a6d754fec2885",
    ),
    "c2-cmy8-p120-v0@3328x2304": (
        "f4f109aa169b9190c1bdbb3892bdcab1"
        "5c20f20f70003c1202c22fde870550a8",
        "fdbf79ffee96249328ecf9eefe133559a"
        "fff6f1e813c54dfd597c2bad21d082e",
    ),
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_frozen_constants():
    assert pilots.TILE_CELLS == 64
    assert pilots.N_QUOTA == 10
    assert pilots.N_WORD_SITES == 100
    assert pilots.COUNTER_BITS == 18
    assert pilots.PAD_BITS == 5
    assert pilots.MESSAGE_BITS == 23
    assert pilots.PLANE_K == keystream.PLANE_K == 3
    assert pilots.MESSAGE_BITS == bch.K_MSG
    assert pilots.N_WORD_SITES == bch.N_WORD


def test_p100_word_site_pattern_golden():
    cells = pilots.word_site_cells_yx(P100)
    assert cells.shape == (100, 2) and cells.dtype == np.int64
    _h3_support.assert_golden(
        "p100 sites", _sha(cells.astype(np.int64).tobytes()),
        GOLDEN_SITES_P100)
    assert np.array_equal(cells, pilots.word_site_cells_yx(P100))
    assert not np.array_equal(cells, pilots.word_site_cells_yx(P120))


@pytest.mark.parametrize("sites_seed", [P100, P120])
def test_word_sites_are_exactly_one_per_quota_cell(sites_seed: bytes):
    cells = pilots.word_site_cells_yx(sites_seed)
    edges = pilots._QUOTA_EDGES
    occupied: set[tuple[int, int]] = set()
    for q in range(pilots.N_WORD_SITES):
        qi, qj = divmod(q, pilots.N_QUOTA)
        y, x = int(cells[q, 0]), int(cells[q, 1])
        assert edges[qi] <= y < edges[qi + 1]
        assert edges[qj] <= x < edges[qj + 1]
        occupied.add((qi, qj))
    assert len(occupied) == pilots.N_WORD_SITES
    flat = cells[:, 0] * pilots.TILE_CELLS + cells[:, 1]
    assert np.unique(flat).size == pilots.N_WORD_SITES


def test_quota_edges_partition_the_tile_axis():
    edges = pilots._QUOTA_EDGES
    assert edges[0] == 0 and edges[-1] == pilots.TILE_CELLS
    assert np.all(np.diff(edges) > 0)
    assert int(np.diff(edges).sum()) == pilots.TILE_CELLS
    assert set(np.unique(pilots._QUOTA_SPANS).tolist()) == {6, 7}


@pytest.mark.parametrize("n_filler", [0, 1, 20, 28])
def test_filler_sites_are_collision_free_against_the_word_sites(
        n_filler: int):
    word, filler = pilots.site_cells_yx(P100, n_filler)
    assert filler.shape == (n_filler, 2)
    stacked = np.concatenate([word, filler], axis=0)
    flat = stacked[:, 0] * pilots.TILE_CELLS + stacked[:, 1]
    assert np.unique(flat).size == 100 + n_filler
    assert int(flat.min()) >= 0 and int(flat.max()) < 4096
    indices = pilots.site_cell_indices(P100, n_filler)
    assert indices.size == 100 + n_filler
    assert np.all(np.diff(indices) > 0)


def test_p120_site_partition_and_goldens():
    word, dust = pilots.color_site_cells_yx(P120)
    payload = pilots.color_payload_cell_indices(P120)
    assert word.shape == (100, 2)
    assert dust.shape == (20, 2)
    assert payload.shape == (3976,)
    dust_flat = dust[:, 0] * pilots.TILE_CELLS + dust[:, 1]
    assert np.all(np.diff(dust_flat) > 0)
    word_flat = word[:, 0] * pilots.TILE_CELLS + word[:, 1]
    assert np.unique(
        np.concatenate((word_flat, dust_flat, payload))).size == 4096
    _h3_support.assert_golden("p120 word",
                              _sha(word.astype(">u2").tobytes()),
                              P120_SITE_GOLDENS["word"])
    _h3_support.assert_golden("p120 dust",
                              _sha(dust.astype(">u2").tobytes()),
                              P120_SITE_GOLDENS["dust"])
    _h3_support.assert_golden("p120 payload",
                              _sha(payload.astype(">u2").tobytes()),
                              P120_SITE_GOLDENS["payload"])


def test_value_scramble_bits_are_the_pilot_value_keystream_draw():
    scramble = pilots.value_scramble_bits(ROW)
    assert scramble.shape == (100,) and scramble.dtype == np.uint8
    assert np.array_equal(scramble, keystream.bits(
        ROW, keystream.DOMAIN_PILOT_VALUES, keystream.PLANE_K, 0,
        np.arange(100), 0))
    assert not np.array_equal(scramble,
                              pilots.value_scramble_bits(ROW, plane=0))
    assert not np.array_equal(scramble, pilots.value_scramble_bits(OTHER_ROW))


@pytest.mark.parametrize("counter", [0, 1, 1871, 12345, (1 << 18) - 1])
def test_word_values_are_the_bch_word_xor_the_scramble(counter: int):
    message = np.zeros(pilots.MESSAGE_BITS, dtype=np.uint8)
    for i in range(pilots.COUNTER_BITS):
        message[i] = (counter >> (pilots.COUNTER_BITS - 1 - i)) & 1
    expected = bch.encode(message) ^ pilots.value_scramble_bits(ROW)
    got = pilots.word_values(ROW, [counter])[0]
    assert got.shape == (100,) and got.dtype == np.uint8
    assert np.array_equal(got, expected)
    assert np.array_equal(pilots.encode_word(counter), bch.encode(message))
    assert pilots.decode_word(got, ROW) == counter


def test_word_values_are_batched_row_by_row():
    counters = [0, 7, 1871]
    batch = pilots.word_values(ROW, counters)
    assert batch.shape == (3, 100)
    for index, counter in enumerate(counters):
        assert np.array_equal(batch[index],
                              pilots.word_values(ROW, [counter])[0])


def test_thirteen_errors_still_decode():
    rng = np.random.default_rng(20260829)
    for _ in range(16):
        counter = int(rng.integers(0, 1 << 18))
        values = pilots.word_values(ROW, [counter])[0].copy()
        values[rng.choice(100, 13, replace=False)] ^= 1
        assert pilots.decode_word(values, ROW) == counter


def test_fourteen_errors_refuse_rather_than_miscorrect():
    rng = np.random.default_rng(20260829)
    outcomes = []
    for _ in range(32):
        counter = int(rng.integers(0, 1 << 18))
        values = pilots.word_values(ROW, [counter])[0].copy()
        values[rng.choice(100, 14, replace=False)] ^= 1
        outcomes.append(pilots.decode_word(values, ROW))
    assert outcomes == [None] * 32


@pytest.mark.parametrize("n_erasures,expect_decode", [
    (8, True), (20, True), (26, True), (27, False), (28, False)])
def test_erasure_budget_boundary_is_the_minimum_distance(
        n_erasures: int, expect_decode: bool):
    rng = np.random.default_rng(4242)
    for _ in range(8):
        counter = int(rng.integers(0, 1 << 18))
        values = pilots.word_values(ROW, [counter])[0].copy()
        erased = rng.choice(100, n_erasures, replace=False)
        values[erased] = 0
        got = pilots.decode_word(values, ROW, erasure_idx=erased)
        assert (got == counter) is expect_decode
        if not expect_decode:
            assert got is None


def test_a_wrong_row_seed_refuses():
    values = pilots.word_values(ROW, [7])[0]
    assert pilots.decode_word(values, ROW) == 7
    assert pilots.decode_word(values, OTHER_ROW) is None


def test_nonzero_pad_bits_refuse_even_when_the_bch_decode_succeeds():
    message = np.zeros(pilots.MESSAGE_BITS, dtype=np.uint8)
    message[0] = 1
    message[pilots.COUNTER_BITS] = 1
    word = bch.encode(message)
    assert bch.decode(word) is not None
    assert pilots.decode_word(
        word ^ pilots.value_scramble_bits(ROW), ROW) is None
    message[pilots.COUNTER_BITS] = 0
    assert pilots.decode_word(
        bch.encode(message) ^ pilots.value_scramble_bits(ROW), ROW) == 1 << 17


@pytest.mark.parametrize("row_id", sorted(ROW_VALUE_GOLDENS))
def test_colour_word_and_dust_value_goldens(row_id: str):
    row = identity.resolve_format_ref("L:" + row_id)
    words = pilots.color_word_states(row.seed, (0, 1, (1 << 18) - 1), row)
    dust = pilots.dust_state_values(row.seed, (0, 1, 2), row)
    word_golden, dust_golden = ROW_VALUE_GOLDENS[row_id]
    _h3_support.assert_golden(f"{row_id} words", _sha(words.tobytes()),
                              word_golden)
    _h3_support.assert_golden(f"{row_id} dust", _sha(dust.tobytes()),
                              dust_golden)
    assert set(np.unique(words).tolist()) <= {0, 3}
    for counter, states in zip((0, 1, (1 << 18) - 1), words, strict=True):
        assert pilots.decode_color_word(states, row.seed, row) == counter


def test_colour_word_states_are_the_binary_word_scaled_to_zero_and_three():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    values = pilots.word_values(row.seed, [1961], pilots.PLANE_K)[0]
    states = pilots.color_word_states(row.seed, [1961], row)[0]
    assert np.array_equal(states, values * np.uint8(3))
    assert states.dtype == np.uint8


def test_decode_color_word_refuses_off_alphabet_states_and_bad_shapes():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    states = pilots.color_word_states(row.seed, [7], row)[0].copy()
    assert pilots.decode_color_word(states, row.seed, row) == 7
    states[7] = 1
    assert pilots.decode_color_word(states, row.seed, row) is None
    assert pilots.decode_color_word(
        pilots.color_word_states(row.seed, [7], row)[0][:99], row.seed,
        row) is None


def test_cmy7_dust_carries_four_of_each_base_state_and_never_cmy():
    row = identity.resolve_format_ref("L:c2-cmy7-p120-v0@3328x2304")
    dust = pilots.dust_state_values(row.seed, (0, 1, 2), row)
    assert dust.shape == (3, 20)
    assert row.dust_base_cycle == (1, 2, 4, 5, 6)
    for states in dust:
        assert Counter(states.tolist()) == {1: 4, 2: 4, 4: 4, 5: 4, 6: 4}
    assert not np.any(dust == 7)
    assert not np.any(dust == 0)
    assert not np.any(dust == 3)


def test_cmy8_dust_rotates_the_two_extra_states_with_the_counter():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    counters = (0, 1, 2)
    dust = pilots.dust_state_values(row.seed, counters, row)
    missing = (1, 2, 4, 5, 6, 7)
    assert row.dust_base_cycle == missing
    for counter, states in zip(counters, dust, strict=True):
        counts = Counter(states.tolist())
        assert sum(counts.values()) == 20
        assert all(counts[state] >= 3 for state in missing)
        assert counts[missing[(2 * counter) % 6]] >= 4
        assert counts[missing[(2 * counter + 1) % 6]] >= 4


def test_dust_values_ride_the_keyed_dust_permutation():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    first = pilots.dust_state_values(row.seed, [11], row)[0]
    again = pilots.dust_state_values(row.seed, [11], row)[0]
    other = pilots.dust_state_values(row.seed, [14], row)[0]
    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)
    assert Counter(first.tolist()) == Counter(other.tolist())


def test_colour_payload_cells_are_the_complement_of_the_furniture():
    payload = pilots.color_payload_cell_indices(P120)
    word, dust = pilots.color_site_cells_yx(P120)
    furniture = np.concatenate((word, dust), axis=0)
    flat = furniture[:, 0] * pilots.TILE_CELLS + furniture[:, 1]
    assert payload.dtype == np.int64
    assert np.all(np.diff(payload) > 0)
    assert not set(payload.tolist()) & set(flat.tolist())
    assert payload.size + np.unique(flat).size == 4096

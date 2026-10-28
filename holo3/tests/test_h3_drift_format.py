from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pytest

from holo3.format import close as h3_close
from holo3.format import fountain as h3_fountain
from holo3.format import identity as h3_identity
from holo3.format import keystream as h3_ks
from holo3.format import metadata as h3_md
from holo3.format import pilots as h3_pilots
from holo3.format import tile_codec as h3_tc
from holo3.tests import _h3_support

v1_bch = pytest.importorskip("holo.core.bch")
v1_channel = pytest.importorskip("holo.core.channel")
v1_color_tile = pytest.importorskip("holo.core.color_tile")
v1_fountain = pytest.importorskip("holo.core.fountain")
v1_frame = pytest.importorskip("holo.core.ldpc.frame")
v1_ks = pytest.importorskip("holo.core.keystream")
v1_ks_spec = pytest.importorskip("holo.core.keystream_spec")
v1_ldpc_tile = pytest.importorskip("holo.core.ldpc.tile")
v1_envelope = pytest.importorskip("holo.format.envelope")
v1_fossils = pytest.importorskip("holo.format.fossils")
v1_layout = pytest.importorskip("holo.format.layout")
v1_md = pytest.importorskip("holo.format.metadata")
v1_pilots = pytest.importorskip("holo.format.pilots")
v1_resolve = pytest.importorskip("holo.format.resolve")
v1_streamset = pytest.importorskip("holo.format.streamset")

pytestmark = pytest.mark.skipif(
    not _h3_support.slow_lane(),
    reason=f"cross-tree drift equivalence is a full-lane corpus: set "
           f"{_h3_support.SLOW_LANE_ENV}=1")

SEEDS = (
    b"holo/v1/c2-r0550/3328x2304",
    b"holo/v1/c2-r0700/3392x2368",
    b"holo/v2/c2-cmy8-r0700@53x37",
    b"holo/v1/sites/p100",
    b"holo/v1/sites/p120",
)
GOLD_SEED = SEEDS[0]
COLOR_SEED = SEEDS[2]

AUX_BY_DOMAIN = {1: (0, 3), 2: (0, 3), 3: (1, 3), 4: (0,), 5: (0,), 6: (0,),
                 7: (0,), 8: (0,), 9: (0,), 10: (0,), 11: (0,), 12: (0,),
                 13: (1, 2, 3), 14: (0, 1, 2, 3), 15: (0, 1, 2, 3)}

P100 = v1_fossils.FAMILY_SEED_P100
P120 = v1_fossils.FAMILY_SEED_P120

CMY7_BANK = (("r0550", 0), ("r0625", 677), ("r0625", 677))
CMY8_BANKS = {"C": ("r0550", 120), "M": ("r0550", 120), "Y": ("r0547", 120)}

FORMAT_SEED = 20260828


def _n(fast: int, full: int) -> int:
    return full if _h3_support.oracle_sweeps() else fast


def eq_arrays(a: np.ndarray, b: np.ndarray) -> bool:
    a = np.asarray(a)
    b = np.asarray(b)
    return (a.dtype == b.dtype and a.shape == b.shape
            and bool(np.array_equal(a, b)))


@pytest.mark.parametrize("seed", SEEDS)
def test_keystream_kdf_matches_v1_production_and_the_stdlib_reference(seed):
    assert h3_ks.kdf(seed) == v1_ks.kdf(seed) == v1_ks_spec.kdf(seed)


def test_keystream_domain_constants_match_v1():
    for name in ("DOMAIN_PAYLOAD", "DOMAIN_PILOT_VALUES",
                 "DOMAIN_FILLER_VALUES", "DOMAIN_PILOT_SITES",
                 "DOMAIN_FILLER_SITES", "DOMAIN_SLOT_PERM",
                 "DOMAIN_FOUNTAIN_ROW", "DOMAIN_BLOCK_ASSIGN",
                 "DOMAIN_COLOR_DUST_ORDER", "DOMAIN_CMY7_INTERLEAVE",
                 "DOMAIN_CMY7_DITHER", "DOMAIN_COLOR_CELL_ORDER",
                 "DOMAIN_CMY8_DITHER", "DOMAIN_COLOR_FOUNTAIN_ROW",
                 "DOMAIN_COLOR_BLOCK_ASSIGN", "PLANE_K"):
        assert getattr(h3_ks, name) == getattr(v1_ks, name), name


def test_keystream_counters_match_v1_and_refuse_identically_out_of_range():
    rng = np.random.default_rng(FORMAT_SEED)
    major = rng.integers(0, 1 << 24, size=7)
    u = rng.integers(0, 1 << 32, size=7)
    v = rng.integers(0, 1 << 32, size=7)
    assert eq_arrays(h3_ks.counters(9, 2, major, u, v),
                     v1_ks.counters(9, 2, major, u, v))
    assert eq_arrays(h3_ks.counters(1, 3, 2, np.arange(5), 0),
                     v1_ks.counters(1, 3, 2, np.arange(5), 0))
    for bad in ((1, 0, 1 << 24, 0, 0), (1, 0, 0, -1, 0), (1, 0, 0, 0, 1 << 32),
                (300, 0, 0, 0, 0), (1, 256, 0, 0, 0), (-1, 0, 0, 0, 0)):
        with pytest.raises(ValueError):
            h3_ks.counters(*bad)
        with pytest.raises(ValueError):
            v1_ks.counters(*bad)


@pytest.mark.parametrize("domain", sorted(AUX_BY_DOMAIN))
def test_keystream_blocks_and_bits_match_v1_and_the_spec_reference(domain):
    rng = np.random.default_rng(FORMAT_SEED + domain)
    seeds = (GOLD_SEED, COLOR_SEED, SEEDS[4])
    for seed in (seeds if _h3_support.oracle_sweeps() else seeds[:2]):
        for aux in AUX_BY_DOMAIN[domain]:
            major = rng.integers(0, 1 << 24, size=4)
            u = rng.integers(0, 1 << 32, size=4)
            v = rng.integers(0, 1 << 32, size=4)
            mine = h3_ks.blocks(seed, domain, aux, major, u, v)
            assert eq_arrays(mine, v1_ks.blocks(seed, domain, aux, major, u, v))
            assert eq_arrays(h3_ks.bits(seed, domain, aux, major, u, v),
                             v1_ks.bits(seed, domain, aux, major, u, v))
            assert mine[0].tobytes() == v1_ks_spec.block(
                seed, domain, aux, int(major[0]), int(u[0]), int(v[0]))
            assert int(h3_ks.bits(seed, domain, aux, int(major[1]),
                                  int(u[1]), int(v[1]))[0]) == v1_ks_spec.bit(
                seed, domain, aux, int(major[1]), int(u[1]), int(v[1]))


def test_keystream_keys64_and_payload_bits_match_v1():
    tiles = np.array([0, 1, 17, 839, 1871], dtype=np.int64)
    for seed in (GOLD_SEED, SEEDS[1]):
        for page in (0, 139):
            mine = h3_ks.keys64(seed, h3_ks.DOMAIN_BLOCK_ASSIGN, 0, page,
                                tiles, 0)
            assert eq_arrays(mine, v1_ks.keys64(
                seed, v1_ks.DOMAIN_BLOCK_ASSIGN, 0, page, tiles, 0))
            expected = np.array(
                [v1_ks_spec.block_assign_key(seed, page, int(t))
                 for t in tiles], dtype=np.uint64)
            assert np.array_equal(mine, expected)
    for seed, plane, page, shape in ((GOLD_SEED, 3, 0, (64, 128)),
                                     (GOLD_SEED, 0, 1, (7, 1)),
                                     (SEEDS[1], 3, 139, (3, 333)),
                                     (COLOR_SEED, 2, 0, (33, 65))):
        assert eq_arrays(h3_ks.payload_bits(seed, plane, page, shape),
                         v1_ks.payload_bits(seed, plane, page, shape))


def test_keystream_fountain_row_bits_match_v1_and_the_spec_reference():
    rows = np.array([0, 3, 4095], dtype=np.int64)
    for n_cols in (1, 127, 128, 129, 4001):
        mine = h3_ks.fountain_rows_bits(GOLD_SEED, 63, rows, n_cols)
        assert eq_arrays(mine, v1_ks.fountain_rows_bits(
            GOLD_SEED, 63, rows, n_cols))
        for row_index, row in enumerate(rows):
            for col in {0, n_cols - 1, min(130, n_cols - 1)}:
                assert int(mine[row_index, col]) == \
                    v1_ks_spec.fountain_coeff_bit(GOLD_SEED, 63, int(row), col)


def test_keystream_colour_fountain_and_block_assign_match_v1():
    rows = np.array([0, 7], dtype=np.int64)
    aux_of = {"main": 0, "C": 1, "M": 2, "Y": 3}
    for stream in ("main", "C", "M", "Y", 0, 1, 2, 3):
        mine = h3_ks.color_fountain_rows_bits(COLOR_SEED, stream, 5, rows, 300)
        assert eq_arrays(mine, v1_ks.color_fountain_rows_bits(
            COLOR_SEED, stream, 5, rows, 300))
        aux = stream if isinstance(stream, int) else aux_of[stream]
        assert int(mine[1, 299]) == v1_ks_spec.color_fountain_coeff_bit(
            COLOR_SEED, aux, 5, 7, 299)
    tiles = np.array([0, 1, 17, 839, 1871], dtype=np.int64)
    for stream in ("main", "C", "M", "Y"):
        mine = h3_ks.color_block_assign_keys(COLOR_SEED, stream, 3, tiles)
        assert eq_arrays(mine, v1_ks.color_block_assign_keys(
            COLOR_SEED, stream, 3, tiles))
        expected = np.array(
            [v1_ks_spec.color_block_assign_key(COLOR_SEED, aux_of[stream], 3,
                                               int(t)) for t in tiles],
            dtype=np.uint64)
        assert np.array_equal(mine, expected)


def test_keystream_item_permutations_match_v1_and_are_bijections():
    rows = (("dust", h3_ks.color_dust_permutation, v1_ks.color_dust_permutation,
             v1_ks_spec.color_dust_order_key, (20, 5, 1, 0)),
            ("interleave", h3_ks.cmy7_interleave_permutation,
             v1_ks.cmy7_interleave_permutation, v1_ks_spec.cmy7_interleave_key,
             (10934, 33)),
            ("cells", h3_ks.color_cell_permutation,
             v1_ks.color_cell_permutation, v1_ks_spec.color_cell_order_key,
             (3976, 11)))
    for _name, mine_fn, v1_fn, key_fn, sizes in rows:
        for size in sizes:
            for tile_counter in (0, 261143):
                mine = mine_fn(COLOR_SEED, tile_counter, size)
                assert eq_arrays(mine, v1_fn(COLOR_SEED, tile_counter, size))
                assert np.array_equal(np.sort(mine), np.arange(size))
                if 0 < size <= 40:
                    keys = [key_fn(COLOR_SEED, tile_counter, i)
                            for i in range(size)]
                    expected = sorted(range(size), key=lambda i: (keys[i], i))
                    assert list(mine) == expected


def test_keystream_dither_bits_match_v1_and_the_spec_reference():
    for size in (10934, 17):
        for tile_counter in (0, 1871):
            mine = h3_ks.cmy7_dither_bits(COLOR_SEED, tile_counter, size)
            assert eq_arrays(mine, v1_ks.cmy7_dither_bits(
                COLOR_SEED, tile_counter, size))
            assert int(mine[size - 1]) == v1_ks_spec.cmy7_dither_bit(
                COLOR_SEED, tile_counter, size - 1)
    for stream in ("C", "M", "Y", 1, 2, 3):
        mine = h3_ks.cmy8_dither_bits(COLOR_SEED, stream, 7, 3976)
        assert eq_arrays(mine, v1_ks.cmy8_dither_bits(
            COLOR_SEED, stream, 7, 3976))
        aux = stream if isinstance(stream, int) else {"C": 1, "M": 2,
                                                      "Y": 3}[stream]
        assert int(mine[3975]) == v1_ks_spec.cmy8_dither_bit(
            COLOR_SEED, aux, 7, 3975)


def test_keystream_bounded_draws_ladder_matches_v1_and_the_spec_reference():
    us = np.array([0, 1, 42, 99, 100000], dtype=np.int64)
    for bound in (2, 6, 7, 49, 64, 100, 256):
        for domain in (h3_ks.DOMAIN_PILOT_SITES, h3_ks.DOMAIN_FILLER_SITES):
            mine = h3_ks.bounded_draws(GOLD_SEED, domain, us, bound)
            assert eq_arrays(mine, v1_ks.bounded_draws(
                GOLD_SEED, domain, us, bound))
            for i, u in enumerate(us):
                assert int(mine[i]) == v1_ks_spec.bounded_draw(
                    GOLD_SEED, domain, int(u), bound)


def test_keystream_slot_perm_params_match_v1_and_stay_coprime():
    tile_counters = np.array([0, 1, 7, 1871, 261143], dtype=np.int64)
    for n_slots in (3996, 3976, 10, 2):
        a3, b3 = h3_ks.slot_perm_params(GOLD_SEED, tile_counters, n_slots)
        a1, b1 = v1_ks.slot_perm_params(GOLD_SEED, tile_counters, n_slots)
        assert eq_arrays(a3, a1)
        assert eq_arrays(b3, b1)
        for i, tile_counter in enumerate(tile_counters):
            assert v1_ks_spec.slot_perm_param(
                GOLD_SEED, int(tile_counter), n_slots) == (int(a3[i]),
                                                           int(b3[i]))
            assert math.gcd(int(a3[i]), n_slots) == 1


def test_metadata_constants_and_coefficient_tables_match_v1():
    for name in ("METADATA_BITS", "K_BITS", "MAX_K", "VALID_VERSIONS",
                 "COUNTER_BITS", "MAX_COUNTER", "MIN_METADATA_EQUATIONS",
                 "LFSR_POLYNOMIAL", "LFSR_FEEDBACK", "LFSR_INITIAL_STATE"):
        assert getattr(h3_md, name) == getattr(v1_md, name), name
    single = h3_md.coefficient_table(h3_md.MAX_COUNTER)
    assert eq_arrays(single, v1_md._coefficient_table(v1_md.MAX_COUNTER))
    assert not single.flags.writeable
    pooled = h3_md.coefficient_table(3 * h3_md.MAX_COUNTER)
    assert eq_arrays(pooled, v1_md._coefficient_table(3 * v1_md.MAX_COUNTER))


def test_metadata_equation_indexing_matches_v1_including_the_refusal():
    for n_streams in (1, 2, 3, 63):
        assert (h3_md.max_equation_index(n_streams)
                == v1_md.max_equation_index(n_streams))
    with pytest.raises(ValueError):
        h3_md.max_equation_index(64)
    with pytest.raises(ValueError):
        v1_md.max_equation_index(64)
    for n_streams in (1, 2, 3):
        for counter in (0, 1, 7, 262143):
            for stream_index in range(n_streams):
                assert (h3_md.equation_index(counter, stream_index, n_streams)
                        == v1_md.equation_index(counter, stream_index,
                                                n_streams))


def _observations(word: np.ndarray, indices: list[int],
                  max_index: int) -> list[tuple[int, int]]:
    bits = v1_md.tile_bits(word, np.array(indices, dtype=np.int64),
                           max_index=max_index)
    return [(int(index), int(bit)) for index, bit in zip(indices, bits)]


def _metadata_scenarios() -> list[tuple]:
    max_counter = v1_md.MAX_COUNTER
    word_ok = v1_md.encode_metadata(0, 1961)
    word_zero = np.zeros(v1_md.METADATA_BITS, dtype=np.uint8)
    word_reserved = v1_md.encode_metadata(0, 1234).copy()
    word_reserved[20] = 1
    word_v1 = v1_md.encode_metadata(1, 5000)
    word_meta = v1_md.encode_metadata(0, 600)
    max_pooled = v1_md.max_equation_index(3)
    inconsistent = _observations(word_ok, list(range(60)), max_counter)
    inconsistent[-1] = (inconsistent[-1][0], inconsistent[-1][1] ^ 1)
    pooled_healthy = [v1_md.equation_index(c, s, 3)
                      for c in range(20) for s in range(3)]
    pooled_dead_y = [v1_md.equation_index(c, s, 3)
                     for c in range(40) for s in (0, 1)]
    return [
        ("full60", _observations(word_ok, list(range(60)), max_counter),
         max_counter, True, False, 24),
        ("scatter", _observations(word_ok, [7 * i + 3 for i in range(100)],
                                  max_counter), max_counter, True, False, 24),
        ("sub48", _observations(word_ok, list(range(30)), max_counter),
         max_counter, False, False, 24),
        ("rank20", _observations(word_ok, list(range(20)), max_counter),
         max_counter, False, False, 20),
        ("inconsistent", inconsistent, max_counter, False, True, None),
        ("k0", _observations(word_zero, list(range(60)), max_counter),
         max_counter, False, False, 24),
        ("reserved", _observations(word_reserved, list(range(60)),
                                   max_counter), max_counter, False, False,
         24),
        ("version1", _observations(word_v1, list(range(60)), max_counter),
         max_counter, False, False, 24),
        ("pooled_healthy", _observations(word_meta, pooled_healthy,
                                         max_pooled), max_pooled, True, False,
         24),
        ("pooled_dead_y", _observations(word_meta, pooled_dead_y, max_pooled),
         max_pooled, True, False, 24),
        ("replicated",
         _observations(word_ok, list(range(60)), max_counter) * 3,
         max_counter, True, False, 24),
        ("empty", [], max_counter, False, False, 0),
    ]


@pytest.mark.parametrize(
    "label,observations,max_index,expect_ok,expect_inconsistent,expect_rank",
    _metadata_scenarios(), ids=lambda v: v if isinstance(v, str) else "")
def test_metadata_decode_agrees_with_v1_under_the_declared_version_gate(
        label, observations, max_index, expect_ok, expect_inconsistent,
        expect_rank):
    theirs = v1_md.decode_metadata(observations, max_index=max_index)
    mine = h3_md.decode_metadata(dict(observations), max_index)
    assert mine.version == theirs.version
    assert mine.k == theirs.k
    assert mine.rank == theirs.rank
    assert mine.n_unique == theirs.n_unique_counters
    assert mine.inconsistent == theirs.inconsistent
    assert mine.ok == (theirs.ok
                       and theirs.version in h3_md.SUPPORTED_METADATA_VERSIONS)
    assert mine.ok is expect_ok
    assert mine.inconsistent is expect_inconsistent
    if expect_rank is not None:
        assert mine.rank == expect_rank


def test_metadata_version_one_is_the_declared_divergence_not_an_accident():
    max_counter = v1_md.MAX_COUNTER
    observations = _observations(v1_md.encode_metadata(1, 5000),
                                 list(range(60)), max_counter)
    theirs = v1_md.decode_metadata(observations, max_index=max_counter)
    mine = h3_md.decode_metadata(dict(observations), max_counter)
    assert theirs.ok and theirs.version == 1
    assert not mine.ok and mine.version == 1 and mine.k == 5000


@pytest.mark.parametrize("family_seed", (P100, P120))
def test_pilot_site_constructions_match_v1(family_seed):
    assert eq_arrays(h3_pilots.word_site_cells_yx(family_seed),
                     v1_pilots.word_site_cells_yx(family_seed))
    assert eq_arrays(h3_pilots.site_cell_indices(family_seed, 0),
                     v1_pilots.site_cell_indices(family_seed, 0))


def test_pilot_colour_site_constructions_match_v1():
    word_mine = h3_pilots.word_site_cells_yx(P120)
    word_theirs = v1_pilots.word_site_cells_yx(P120)
    assert eq_arrays(h3_pilots.filler_site_cells_yx(P120, 20, word_mine),
                     v1_pilots.filler_site_cells_yx(P120, 20, word_theirs))
    assert eq_arrays(h3_pilots.site_cell_indices(P120, 20),
                     v1_pilots.site_cell_indices(P120, 20))
    assert eq_arrays(h3_pilots.dust_site_cells_yx(P120, 20),
                     v1_pilots.dust_site_cells_yx(P120, 20))
    mine = h3_pilots.color_site_cells_yx(P120)
    theirs = v1_pilots.color_site_cells_yx(P120)
    assert eq_arrays(mine[0], theirs[0])
    assert eq_arrays(mine[1], theirs[1])
    payload = h3_pilots.color_payload_cell_indices(P120)
    assert eq_arrays(payload, v1_pilots.color_payload_cell_indices(P120))
    assert payload.size == 3976


SEED_ROWS = (("c3-r0550@2240x1536", False),
             ("c2-r0700@3392x2368", False),
             ("c2-cmy7-p120-v0@3328x2304", True),
             ("c2-cmy8-p120-v0@3328x2304", True),
             ("c2-cmy8-r0700-p120-x1@3392x2368", True))


@pytest.mark.parametrize("spec_id,is_color", SEED_ROWS)
def test_pilot_word_values_and_decode_match_v1_including_refusals(spec_id,
                                                                  is_color):
    rng = np.random.default_rng(FORMAT_SEED)
    fossil = v1_fossils.FOSSILS[spec_id]
    seed = fossil.seed
    spec = v1_resolve.resolve_format_ref("L:" + spec_id)
    n_tiles = spec.layout.tiles_yx[0] * spec.layout.tiles_yx[1]
    counters = np.concatenate([
        np.array([0, 1, n_tiles - 1], dtype=np.int64),
        rng.integers(0, n_tiles, size=_n(4, 13), dtype=np.int64)])
    for plane in (0, v1_ks.PLANE_K):
        assert eq_arrays(h3_pilots.value_scramble_bits(seed, plane),
                         v1_pilots.value_scramble_bits(seed, plane))
    values = v1_pilots.word_values(seed, counters)
    assert eq_arrays(h3_pilots.word_values(seed, counters), values)
    if is_color:
        assert eq_arrays(h3_pilots.color_word_states(seed, counters),
                         v1_pilots.color_word_states(seed, counters))
        codec = spec.coding.codec
        assert eq_arrays(
            h3_pilots.dust_state_values(seed, counters, codec.dust_base_cycle,
                                        codec.n_dust),
            v1_pilots.dust_state_values(seed, counters, codec))
    for i, counter in enumerate(counters):
        noisy = values[i].copy()
        n_errors = int(rng.integers(0, 14))
        noisy[rng.choice(100, size=n_errors, replace=False)] ^= 1
        assert (h3_pilots.decode_word(noisy, seed)
                == v1_pilots.decode_word(noisy, seed))
        if n_errors <= 13:
            assert h3_pilots.decode_word(noisy, seed) == int(counter)
        erasures = np.unique(rng.choice(100, size=8, replace=False))
        erased = values[i].copy()
        erased[erasures] ^= rng.integers(0, 2, size=erasures.size).astype(
            np.uint8)
        assert (h3_pilots.decode_word(erased, seed, erasure_idx=erasures)
                == v1_pilots.decode_word(erased, seed, erasure_idx=erasures))
    message = np.zeros(23, dtype=np.uint8)
    message[0] = 1
    message[20] = 1
    forged = v1_bch.encode(message) ^ v1_pilots.value_scramble_bits(seed)
    assert h3_pilots.decode_word(forged, seed) is None
    assert v1_pilots.decode_word(forged, seed) is None
    if is_color:
        for i, counter in enumerate(counters):
            states = (values[i] * np.uint8(3)).astype(np.uint8)
            assert (h3_pilots.decode_color_word(states, seed)
                    == v1_pilots.decode_color_word(states, seed)
                    == int(counter))
        bad_states = (values[0] * np.uint8(3)).astype(np.uint8)
        bad_states[7] = 1
        assert h3_pilots.decode_color_word(bad_states, seed) is None


V2_ONLY_IN_HOLO3 = {"c2-cmy8-r0547@53x37"}


def test_fossil_catalogue_key_set_matches_v1_plus_the_v2_row():
    assert len(v1_fossils.FOSSILS) == 14
    assert len(h3_identity._FOSSILS) == 15
    assert set(h3_identity._FOSSILS) == (
        set(v1_fossils.FOSSILS) | V2_ONLY_IN_HOLO3)
    assert not (set(v1_fossils.FOSSILS) & V2_ONLY_IN_HOLO3)
    for spec_id in v1_fossils.FOSSILS:
        assert h3_identity._FOSSILS[spec_id][0].startswith(b"holo/v1/")


@pytest.mark.parametrize("spec_id", sorted(v1_fossils.FOSSILS))
def test_fossil_row_fields_match_v1_resolution(spec_id):
    fossil = v1_fossils.FOSSILS[spec_id]
    spec = v1_resolve.resolve_format_ref("L:" + spec_id)
    row = h3_identity.resolve_format_ref("L:" + spec_id)
    codec = spec.coding.codec
    assert row.seed == fossil.seed
    assert row.row_id == "L:" + spec_id
    assert row.tiles_yx == spec.layout.tiles_yx
    assert row.cells_yx == fossil.cells_yx
    assert row.pooled_fountain == spec.pooled_fountain
    assert row.family.value == codec.family.value
    assert row.n_sites == codec.n_sites
    assert row.n_dust == codec.n_dust
    assert row.dust_base_cycle == tuple(codec.dust_base_cycle)
    assert row.word_states == tuple(codec.word_states)
    assert row.bits_per_mapper_unit == codec.bits_per_mapper_unit
    assert row.cells_per_mapper_unit == codec.cells_per_mapper_unit
    assert row.sites_seed == spec.coding.family_seed
    assert len(row.streams) == len(codec.streams)
    for mine, theirs in zip(row.streams, codec.streams):
        assert mine.stream_id == theirs.stream_id
        assert mine.fountain_aux == theirs.fountain_aux
        assert mine.user_bits == theirs.user_bits
        assert mine.symbol_bits == theirs.symbol_bits
        assert mine.rung_children == tuple(
            (child.code_id, child.shortened_info_tail)
            for child in theirs.fec.children)


V2_IDS = ("c3-k-r0550@7x7", "c3-cmy8-r0550x0550x0547@10x10",
          "c3-k-r0550-p100-v1@7x7", "c3-cmy8-r0550@10x10", "c2-cmy7@52x36",
          "1i200-k-r0550@7x7")


@pytest.mark.parametrize("format_ref", V2_IDS)
def test_v2_grammar_resolution_matches_v1(format_ref):
    spec = v1_resolve.resolve_format_ref(format_ref)
    row = h3_identity.resolve_format_ref(format_ref)
    assert row.row_id == spec.spec_id
    assert row.display_id == spec.display_id
    assert row.seed == spec.seed
    assert row.tiles_yx == spec.layout.tiles_yx
    assert row.n_sites == spec.coding.codec.n_sites
    assert row.pooled_fountain == spec.pooled_fountain
    assert row.sites_seed == spec.coding.family_seed
    for mine, theirs in zip(row.streams, spec.coding.codec.streams):
        assert mine.stream_id == theirs.stream_id
        assert mine.user_bits == theirs.user_bits
        assert mine.symbol_bits == theirs.symbol_bits
        assert mine.rung_children == tuple(
            (child.code_id, child.shortened_info_tail)
            for child in theirs.fec.children)


@pytest.mark.parametrize("media,margin_mm,cell_dots,expected", (
    ((210.0, 297.0), 6.0, 2, (3328, 2304)),
    ((210.0, 297.0), 6.0, 3, (2240, 1536)),
    ((210.0, 297.0), 6.0, 4, (1664, 1152)),
    ((210.0, 297.0), 4.0, 2, (3392, 2368)),
    ((210.0, 297.0), 4.0, 3, (2240, 1536)),
    ((210.0, 297.0), 4.5, 2, (3392, 2368)),
    ((297.0, 420.0), 4.0, 2, (4864, 3392)),
))
def test_derive_field_matches_v1_layout(media, margin_mm, cell_dots, expected):
    mine = h3_identity.derive_field(media, margin_mm, cell_dots)
    theirs = v1_layout.derive_field(media, margin_mm, cell_dots).cells_yx
    assert mine == theirs == expected


def test_tile_addressing_matches_v1_layout_on_the_e029_row():
    rng = np.random.default_rng(FORMAT_SEED + 1)
    row = h3_identity.resolve_format_ref("L:c2-r0700@3392x2368")
    for _ in range(_n(24, 200)):
        page = int(rng.integers(0, row.max_pages))
        ty = int(rng.integers(0, 53))
        tx = int(rng.integers(0, 37))
        counter = row.tile_counter(page, ty, tx)
        assert counter == v1_layout.tile_counter(page, ty, tx, (53, 37))
        assert row.tile_address(counter) == v1_layout.tile_address(counter,
                                                                   (53, 37))


def test_site_geometry_precompute_matches_the_v1_pilot_and_keystream_kernels():
    row = h3_identity.resolve_format_ref("L:c2-r0700@3392x2368")
    geometry = h3_identity.build_site_geometry(row)
    assert eq_arrays(geometry.word_cells_yx, v1_pilots.word_site_cells_yx(P100))
    assert geometry.extra_cells_yx.shape == (0, 2)
    assert eq_arrays(geometry.shorten_flat,
                     v1_pilots.site_cell_indices(P100, 0))
    assert geometry.payload_flat.size == 3996
    n_counters = row.max_pages * row.tiles_per_page
    a1, b1 = v1_ks.slot_perm_params(
        row.seed, np.arange(n_counters, dtype=np.int64), 3996)
    assert eq_arrays(geometry.slot_a, a1)
    assert eq_arrays(geometry.slot_b, b1)
    assert eq_arrays(h3_identity.scramble_plane(row, geometry, 0),
                     v1_ks.payload_bits(row.seed, v1_ks.PLANE_K, 0,
                                        (3392, 2368)))

    sheet_i = h3_identity.resolve_format_ref(
        "L:c2-cmy8-r0700-p120-x1@3392x2368")
    colour = h3_identity.build_site_geometry(sheet_i)
    assert eq_arrays(colour.word_cells_yx, v1_pilots.word_site_cells_yx(P120))
    assert eq_arrays(colour.extra_cells_yx,
                     v1_pilots.dust_site_cells_yx(P120, 20))
    assert eq_arrays(colour.shorten_flat,
                     v1_pilots.site_cell_indices(P120, 20))
    assert eq_arrays(colour.payload_flat,
                     v1_pilots.color_payload_cell_indices(P120))


FOUNTAIN_SEED = b"holo3-verify/assignment"
FOUNTAIN_K = 40000
FOUNTAIN_S = 64
FOUNTAIN_T = 737

FOUNTAIN_VARIANTS = (
    ("K", {}),
    ("main-aux0", {"stream_id": "main", "fountain_aux": 0}),
    ("C", {"stream_id": "C", "fountain_aux": 1}),
    ("M", {"stream_id": "M", "fountain_aux": 2}),
    ("Y", {"stream_id": "Y", "fountain_aux": 3}),
    ("pooled-n3", {"n_streams": 3}),
)


@pytest.mark.parametrize("label,kwargs", FOUNTAIN_VARIANTS,
                         ids=[row[0] for row in FOUNTAIN_VARIANTS])
def test_volume_code_assignment_matches_v1_fountain(label, kwargs):
    mine = h3_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                  FOUNTAIN_T, **kwargs)
    theirs = v1_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                    FOUNTAIN_T, **kwargs)
    assert mine.k_per_block == theirs.k_per_block
    assert mine.block_offsets == theirs.block_offsets
    for page in range(4):
        for stream in range(mine.n_streams):
            assert eq_arrays(mine.quotas(page, stream),
                             theirs.quotas(page, stream))
        blocks_mine, rows_mine = mine.page_assignment(page)
        blocks_theirs, rows_theirs = theirs.page_assignment(page)
        assert eq_arrays(blocks_mine, blocks_theirs)
        assert eq_arrays(rows_mine, rows_theirs)
    for esi in range(0, 4 * mine.symbols_per_page, 7):
        assert mine.block_row_of(esi) == theirs.block_row_of(esi)


def test_pooled_single_stream_is_bit_identical_to_the_k_form_on_both_sides():
    pooled = h3_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                    FOUNTAIN_T, n_streams=1)
    mine = h3_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                  FOUNTAIN_T)
    theirs = v1_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                    FOUNTAIN_T)
    for page in range(4):
        blocks_p, rows_p = pooled.page_assignment(page)
        blocks_k, rows_k = mine.page_assignment(page)
        blocks_o, rows_o = theirs.page_assignment(page)
        assert eq_arrays(blocks_p, blocks_k)
        assert eq_arrays(rows_p, rows_k)
        assert eq_arrays(blocks_p, blocks_o)
        assert eq_arrays(rows_p, rows_o)


def test_colour_fountain_domain_actually_routes_differently_from_k():
    k_code = h3_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                    FOUNTAIN_T)
    main_code = h3_fountain.VolumeCode(FOUNTAIN_K, FOUNTAIN_S, FOUNTAIN_SEED,
                                       FOUNTAIN_T, stream_id="main",
                                       fountain_aux=0)
    assert not np.array_equal(k_code.page_assignment(0)[0],
                              main_code.page_assignment(0)[0])


@pytest.mark.parametrize("label,kwargs", (
    ("K", {}),
    ("main-aux0", {"stream_id": "main", "fountain_aux": 0}),
    ("C", {"stream_id": "C", "fountain_aux": 1}),
    ("pooled-n3", {"n_streams": 3}),
), ids=("K", "main-aux0", "C", "pooled-n3"))
def test_packed_generator_rows_match_v1_generator_row(label, kwargs):
    k_small = 100
    mine = h3_fountain.VolumeCode(k_small, FOUNTAIN_S, FOUNTAIN_SEED,
                                  FOUNTAIN_T, **kwargs)
    theirs = v1_fountain.VolumeCode(k_small, FOUNTAIN_S, FOUNTAIN_SEED,
                                    FOUNTAIN_T, **kwargs)
    esis = list(range(0, 60)) + list(range(150, 190))
    items = sorted((mine.block_row_of(esi)[1], esi, 0, FOUNTAIN_S)
                   for esi in esis)
    decoder = h3_fountain.Decoder(mine)
    got = h3_fountain._unpack_bits_2d(
        decoder._packed_generator_rows(0, items), k_small)
    want = np.stack([theirs.generator_row(esi) for _row, esi, *_ in items])
    assert np.array_equal(got, want)
    assert sum(row >= k_small for row, *_ in items) >= 10


@dataclass(frozen=True)
class _Cert:
    page: int
    ty: int
    tx: int
    stream_id: str
    user_bits: np.ndarray
    source: str


@dataclass(frozen=True)
class _Stream:
    stream_id: str
    symbol_bits: int
    fountain_aux: int | None


@dataclass(frozen=True)
class _Row:
    seed: bytes
    tiles_yx: tuple[int, int]
    streams: tuple[_Stream, ...]
    pooled_fountain: bool


CLOSE_TILES_YX = (8, 8)
CLOSE_TT = 64
CLOSE_SB = 40


def _mk_cert(counter: int, stream_id: str, metadata_bit: int,
             symbol: np.ndarray) -> _Cert:
    page, local = divmod(int(counter), CLOSE_TT)
    ty, tx = divmod(local, CLOSE_TILES_YX[1])
    user_bits = np.concatenate(([metadata_bit], symbol)).astype(np.uint8)
    return _Cert(page, ty, tx, stream_id, user_bits, "test")


def _k_volume() -> tuple:
    rng = np.random.default_rng(7)
    payload = rng.integers(0, 256, 300, dtype=np.uint8).tobytes()
    seed = b"verify/K"
    envelope = v1_envelope.wrap(payload)
    k_total = v1_envelope.source_symbol_count(len(payload), CLOSE_SB)
    source = v1_fountain.pack_source(envelope, k_total, CLOSE_SB)
    code = v1_fountain.VolumeCode(k_total, CLOSE_SB, seed, CLOSE_TT)
    esis = np.arange(2 * CLOSE_TT, dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    bits = v1_md.tile_bits(v1_md.encode_metadata(0, k_total), esis)
    certs = [_mk_cert(int(c), "main", bits[i], symbols[i])
             for i, c in enumerate(esis)]
    row = _Row(seed, CLOSE_TILES_YX, (_Stream("main", CLOSE_SB, None),), False)
    return payload, seed, envelope, k_total, source, code, bits, certs, row


def test_close_of_a_v1_emitted_k_volume_verifies_byte_exact():
    payload, _seed, _env, k_total, _src, _code, _bits, certs, row = _k_volume()
    result = h3_close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k_total
    assert h3_close.close_count_ready(certs, row)
    assert all(block.solved and block.stream_id is None
               for block in result.blocks)


def test_close_of_a_v1_emitted_colour_single_stream_volume_verifies():
    rng = np.random.default_rng(11)
    payload = rng.integers(0, 256, 280, dtype=np.uint8).tobytes()
    seed = b"verify/cmy7"
    envelope = v1_envelope.wrap(payload)
    k_total = v1_envelope.source_symbol_count(len(payload), CLOSE_SB)
    source = v1_fountain.pack_source(envelope, k_total, CLOSE_SB)
    code = v1_fountain.VolumeCode(k_total, CLOSE_SB, seed, CLOSE_TT,
                                  stream_id="main", fountain_aux=0)
    esis = np.arange(2 * CLOSE_TT, dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    bits = v1_md.tile_bits(v1_md.encode_metadata(0, k_total), esis)
    certs = [_mk_cert(int(c), "main", bits[i], symbols[i])
             for i, c in enumerate(esis)]
    row = _Row(seed, CLOSE_TILES_YX, (_Stream("main", CLOSE_SB, 0),), False)
    result = h3_close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert all(block.stream_id == "main" for block in result.blocks)


def test_close_of_a_v1_emitted_cmy8_v0_three_stream_volume_verifies():
    rng = np.random.default_rng(13)
    payload = rng.integers(0, 256, 310, dtype=np.uint8).tobytes()
    seed = b"verify/cmy8-v0"
    stream_set = v1_streamset.StreamSet((("C", CLOSE_SB), ("M", CLOSE_SB),
                                         ("Y", CLOSE_SB)))
    packed = v1_streamset.pack_payload(payload, stream_set)
    counters = np.arange(CLOSE_TT, dtype=np.int64)
    bits = v1_md.tile_bits(v1_md.encode_metadata(0, packed.k_total), counters)
    aux_of = {"C": 1, "M": 2, "Y": 3}
    certs = []
    for stream in packed.streams:
        code = v1_fountain.VolumeCode(packed.k_total, CLOSE_SB, seed, CLOSE_TT,
                                      stream_id=stream.stream_id,
                                      fountain_aux=aux_of[stream.stream_id])
        symbols = code.encode_symbols(stream.rows, counters)
        certs += [_mk_cert(int(c), stream.stream_id, bits[i], symbols[i])
                  for i, c in enumerate(counters)]
    row = _Row(seed, CLOSE_TILES_YX,
               (_Stream("C", CLOSE_SB, 1), _Stream("M", CLOSE_SB, 2),
                _Stream("Y", CLOSE_SB, 3)), False)
    result = h3_close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == packed.k_total
    assert sorted({block.stream_id for block in result.blocks}) == ["C", "M",
                                                                    "Y"]


def _pooled_volume() -> tuple:
    rng = np.random.default_rng(17)
    payload = rng.integers(0, 256, 320, dtype=np.uint8).tobytes()
    seed = b"verify/cmy8-pooled"
    stream_set = v1_streamset.StreamSet((("C", CLOSE_SB), ("M", CLOSE_SB),
                                         ("Y", CLOSE_SB)))
    k_meta, rows = v1_streamset.pooled_pack_payload(payload, stream_set)
    k_total = 3 * k_meta
    code = v1_fountain.VolumeCode(k_total, CLOSE_SB, seed, CLOSE_TT,
                                  n_streams=3)
    esis = np.arange(CLOSE_TT * 3, dtype=np.int64)
    symbols = code.encode_symbols(rows, esis)
    bits = v1_md.tile_bits(v1_md.encode_metadata(0, k_meta), esis,
                           max_index=v1_md.max_equation_index(3))
    stream_of = {0: "C", 1: "M", 2: "Y"}
    certs = []
    for i, esi in enumerate(esis):
        counter, index = divmod(int(esi), 3)
        certs.append(_mk_cert(counter, stream_of[index], bits[i], symbols[i]))
    row = _Row(seed, CLOSE_TILES_YX,
               (_Stream("C", CLOSE_SB, 1), _Stream("M", CLOSE_SB, 2),
                _Stream("Y", CLOSE_SB, 3)), True)
    return payload, k_total, certs, row


def test_close_of_a_v1_emitted_pooled_volume_verifies_healthy_and_dead_plane():
    payload, k_total, certs, row = _pooled_volume()
    result = h3_close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k_total
    assert all(block.stream_id is None for block in result.blocks)
    dead_y = [cert for cert in certs if cert.stream_id != "Y"]
    dead_result = h3_close.close_volume(dead_y, row)
    assert dead_result.status == "verified"
    assert dead_result.payload == payload
    assert h3_close.close_count_ready(dead_y, row)


def test_close_refusals_on_v1_emitted_volumes_report_the_named_outcomes():
    payload, seed, envelope, k_total, source, code, bits, certs, row = \
        _k_volume()

    truncated = certs[:50]
    result = h3_close.close_volume(truncated, row)
    assert result.status == "open"
    assert result.blocks and not result.blocks[0].solved
    assert result.blocks[0].have == 50
    assert result.blocks[0].needed == k_total
    assert not h3_close.close_count_ready(truncated, row)

    starved = certs[:30]
    result = h3_close.close_volume(starved, row)
    assert result.status == "open"
    assert result.reason == "metadata incomplete"
    assert not h3_close.close_count_ready(starved, row)

    corrupted = list(certs[:k_total])
    user_bits = corrupted[5].user_bits.copy()
    user_bits[3] ^= 1
    corrupted[5] = _Cert(corrupted[5].page, corrupted[5].ty, corrupted[5].tx,
                         corrupted[5].stream_id, user_bits, "test")
    result = h3_close.close_volume(corrupted, row)
    assert result.status == "integrity_failure"
    assert "envelope verification failed" in (result.reason or "")

    conflicting = certs[0].user_bits.copy()
    conflicting[7] ^= 1
    duplicate = _Cert(certs[0].page, certs[0].ty, certs[0].tx, "main",
                      conflicting, "test")
    result = h3_close.close_volume(list(certs) + [duplicate], row)
    assert result.status == "integrity_failure"
    assert "certified-symbol integrity failure" in (result.reason or "")

    result = h3_close.close_volume(list(certs) + [certs[0]], row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.symbols_used == len(certs)

    k_noncanonical = k_total + 1
    source_nc = v1_fountain.pack_source(envelope, k_noncanonical, CLOSE_SB)
    code_nc = v1_fountain.VolumeCode(k_noncanonical, CLOSE_SB, seed, CLOSE_TT)
    esis_nc = np.arange(k_noncanonical, dtype=np.int64)
    symbols_nc = code_nc.encode_symbols(source_nc, esis_nc)
    bits_nc = v1_md.tile_bits(v1_md.encode_metadata(0, k_noncanonical),
                              esis_nc)
    certs_nc = [_mk_cert(int(c), "main", bits_nc[i], symbols_nc[i])
                for i, c in enumerate(esis_nc)]
    assert h3_close.close_volume(certs_nc, row).status == "integrity_failure"

    padded = source.copy()
    used_bits = (v1_envelope.OVERHEAD_BYTES + len(payload)) * 8
    row_index, local_bit = divmod(used_bits, CLOSE_SB)
    byte_index, bit_index = divmod(local_bit, 8)
    padded[row_index, byte_index] |= np.uint8(0x80 >> bit_index)
    symbols_pad = code.encode_symbols(padded,
                                      np.arange(k_total, dtype=np.int64))
    certs_pad = [_mk_cert(c, "main", bits[c], symbols_pad[i])
                 for i, c in enumerate(range(k_total))]
    assert h3_close.close_volume(certs_pad, row).status == "integrity_failure"

    symbols_clean = code.encode_symbols(source,
                                        np.arange(k_total, dtype=np.int64))
    certs_clean = [_mk_cert(c, "main", bits[c], symbols_clean[i])
                   for i, c in enumerate(range(k_total))]
    control = h3_close.close_volume(certs_clean, row)
    assert control.status == "verified"
    assert control.payload == payload


def test_close_of_a_v1_emitted_version_one_volume_reports_unsupported():
    payload, _seed, envelope, k_total, source, code, _bits, _certs, row = \
        _k_volume()
    esis = np.arange(2 * CLOSE_TT, dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    v1_bits = v1_md.tile_bits(v1_md.encode_metadata(1, k_total), esis)
    certs = [_mk_cert(int(c), "main", v1_bits[i], symbols[i])
             for i, c in enumerate(esis)]
    result = h3_close.close_volume(certs, row)
    assert result.status == "unsupported"
    assert result.reason == "unsupported metadata version 1"
    assert result.k_total is None
    assert result.payload is None
    theirs = v1_md.decode_metadata(
        [(int(index), int(bit)) for index, bit in zip(esis, v1_bits)])
    assert theirs.ok and theirs.version == 1
    assert payload and envelope


def test_envelope_overhead_and_source_symbol_count_match_v1():
    assert h3_close.OVERHEAD_BYTES == v1_envelope.OVERHEAD_BYTES == 36
    for payload_len in (0, 1, 35, 36, 300, 4096):
        for symbol_bits in (40, 2087, 2747):
            assert (h3_close.source_symbol_count(payload_len, symbol_bits)
                    == v1_envelope.source_symbol_count(payload_len,
                                                       symbol_bits))
    for payload_len in (0, 1, 300):
        payload = bytes(range(256))[:payload_len] if payload_len <= 256 \
            else bytes(payload_len)
        wrapped = v1_envelope.wrap(payload)
        assert h3_close.try_unwrap(wrapped) == payload
        assert h3_close.try_unwrap(wrapped + b"\x00" * 64) == payload


def test_tile_codec_width_arithmetic_matches_v1_frame_and_tile():
    assert h3_tc.tile_capacity("r0550", 100) == v1_ldpc_tile.tile_capacity(
        "r0550", 100) == 2108
    assert h3_tc.tile_capacity("r0700", 100) == v1_ldpc_tile.tile_capacity(
        "r0700", 100) == 2748
    assert h3_tc.bank_transmitted_bits(CMY7_BANK) == 10934
    assert h3_tc.bank_active_bits(CMY7_BANK) == 2240 + 1883 + 1883
    assert h3_tc.bank_user_bits(CMY7_BANK) == 5974
    for stream_id in ("C", "M", "Y"):
        bank = (CMY8_BANKS[stream_id],)
        assert h3_tc.bank_transmitted_bits(bank) == 3976
        assert h3_tc.bank_user_bits(bank) == 2088
    assert h3_tc.bank_transmitted_bits((("r0700", 120),)) == 3976
    assert h3_tc.bank_active_bits((("r0700", 120),)) == 2760
    assert h3_tc.bank_user_bits((("r0700", 120),)) == 2728
    for code_id, tail in (("r0550", 0), ("r0625", 677), ("r0550", 120),
                          ("r0547", 120), ("r0700", 120), ("r0700", 100)):
        assert np.array_equal(
            h3_tc.transmitted_positions(code_id, tail),
            v1_frame.transmitted_positions(
                v1_frame.FecChildProfile(code_id, tail)))


def test_tile_codec_crc32_bits_match_v1():
    rng = np.random.default_rng(FORMAT_SEED + 2)
    for n in (1, 7, 8, 33, 2108, 5974):
        bits = rng.integers(0, 2, n, dtype=np.uint8)
        assert np.array_equal(h3_tc.crc32_bits(bits),
                              v1_ldpc_tile.crc32_bits(bits))


TC_SEED = b"holo3-verify-tile-codec-seed"
TC_FAMILY_SEED = b"holo3-verify-fam"


TC_RATE_IDS = ("r0550", "r0700")


@pytest.mark.parametrize("rate_id", TC_RATE_IDS)
def test_k_tile_encode_and_decode_match_v1_including_failures(rate_id):
    rng = np.random.default_rng(
        FORMAT_SEED + 3 + TC_RATE_IDS.index(rate_id))
    site_flat = v1_pilots.site_cell_indices(TC_FAMILY_SEED, 0)
    assert site_flat.size == 100
    n_slots = 4096 - site_flat.size
    capacity = h3_tc.tile_capacity(rate_id, 100)
    assert np.array_equal(h3_tc.cell_map(site_flat, 7, 11),
                          v1_ldpc_tile.cell_map(site_flat, 7, 11))
    outcomes = {True: 0, False: 0}
    for trial in range(_n(2, 12)):
        counter = trial + (0 if rate_id == "r0550" else 500)
        a_arr, b_arr = v1_ks.slot_perm_params(TC_SEED, counter, n_slots)
        a, b = int(a_arr[0]), int(b_arr[0])
        user = rng.integers(0, 2, capacity, dtype=np.uint8)
        mine_cells = h3_tc.encode_tile(user, rate_id, site_flat, a, b)
        v1_cells = v1_ldpc_tile.encode_tile(user, rate_id, site_flat, a, b)
        assert mine_cells.dtype == np.uint8
        assert np.array_equal(mine_cells, v1_cells)
        p_flip = (0.0, 0.02, 0.05, 0.09)[trial % 4]
        llr = (2.0 * v1_cells.astype(np.float64) - 1.0) * rng.uniform(
            0.8, 6.0, 4096)
        llr[rng.random(4096) < p_flip] *= -1.0
        llr[rng.random(4096) < 0.03] = 0.0
        llr[site_flat] = 0.0
        for max_iters in (60, 150):
            mine = h3_tc.decode_tile(llr, rate_id, site_flat, a, b, max_iters,
                                     0.8)
            theirs = v1_ldpc_tile.decode_tile(llr, rate_id, site_flat, a, b,
                                              max_iters=max_iters, alpha=0.8)
            assert mine[0] == theirs.ok
            assert mine[2] == theirs.n_iters
            assert mine[3] == theirs.syndrome_ok
            assert mine[4] == theirs.crc_ok
            if theirs.ok:
                assert mine[1] is not None
                assert np.array_equal(mine[1], theirs.user_bits)
                assert np.array_equal(mine[1], user)
            else:
                assert mine[1] is None
            outcomes[bool(theirs.ok)] += 1
    assert outcomes[True] > 0


def _v1_cmy7_bank():
    return v1_frame.FecBankProfile(
        "cmy7-p120-v0",
        tuple(v1_frame.FecChildProfile(code_id, tail)
              for code_id, tail in CMY7_BANK))


def _v1_cmy8_banks():
    return {stream_id: v1_frame.FecBankProfile(
        f"cmy8-{stream_id}-p120-v0",
        (v1_frame.FecChildProfile(*CMY8_BANKS[stream_id]),))
        for stream_id in ("C", "M", "Y")}


def _same_frame_outcome(mine, theirs, check_extrinsic: bool) -> None:
    ok, children, invoked, crc_ok, user_bits, soft = mine
    assert (ok, children, invoked, crc_ok) == (
        bool(theirs.ok),
        tuple((child.n_iters, child.syndrome_ok) for child in theirs.children),
        bool(theirs.crc_invoked), theirs.crc_ok)
    if theirs.certified_user_bits is None:
        assert user_bits is None
    else:
        assert user_bits is not None
        assert np.array_equal(user_bits, theirs.certified_user_bits)
    if not check_extrinsic:
        return
    if theirs.extrinsic_llrs is None:
        assert soft is None
    else:
        assert soft is not None
        assert soft.dtype == theirs.extrinsic_llrs.dtype
        assert np.array_equal(soft, theirs.extrinsic_llrs)


@pytest.mark.parametrize("label", ("cmy7", "cmy8-C", "cmy8-M", "cmy8-Y"))
def test_frame_encode_and_decode_match_v1(label):
    rng = np.random.default_rng(FORMAT_SEED + 4 + len(label))
    if label == "cmy7":
        mine_bank, v1_bank = CMY7_BANK, _v1_cmy7_bank()
    else:
        stream_id = label.split("-")[1]
        mine_bank = (CMY8_BANKS[stream_id],)
        v1_bank = _v1_cmy8_banks()[stream_id]
    n_code = h3_tc.bank_transmitted_bits(mine_bank)
    assert n_code == v1_bank.transmitted_bits
    assert h3_tc.bank_user_bits(mine_bank) == v1_bank.user_bits
    for trial in range(_n(2, 8)):
        user = rng.integers(0, 2, v1_bank.user_bits, dtype=np.uint8)
        code_bits = v1_frame.encode_frame(user, v1_bank)
        assert np.array_equal(h3_tc.encode_frame(user, mine_bank), code_bits)
        p_flip = (0.0, 0.03, 0.06, 0.10)[trial % 4]
        llr = (2.0 * code_bits.astype(np.float64) - 1.0) * rng.uniform(
            0.8, 6.0, n_code)
        llr[rng.random(n_code) < p_flip] *= -1.0
        llr[rng.random(n_code) < 0.02] = 0.0
        for want_extrinsic in (False, True):
            mine = h3_tc.decode_frame(llr, mine_bank, 60, 0.8,
                                      want_extrinsic=want_extrinsic)
            theirs = v1_frame.decode_frame(llr, v1_bank, max_iters=60,
                                           alpha=0.8,
                                           want_extrinsic=want_extrinsic)
            _same_frame_outcome(mine, theirs, check_extrinsic=True)


def test_cmy7_soft_demap_matches_v1_channel_including_the_log_fallback():
    rng = np.random.default_rng(FORMAT_SEED + 5)
    for trial in range(_n(9, 30)):
        n_packs = int(rng.integers(1, 40))
        scale = (3.0, 40.0, 800.0)[trial % 3]
        relative = rng.uniform(-scale, scale, (n_packs, 4, 6))
        prior = (None if trial % 2 == 0
                 else rng.uniform(-20.0, 20.0, (n_packs, 11)))
        assert np.array_equal(h3_tc.cmy7_soft_demap(relative, prior),
                              v1_channel.cmy7_soft_demap(relative, prior))
    underflow = np.zeros((2, 4, 6))
    underflow[0, :, 0] = -750.0
    assert np.array_equal(h3_tc.cmy7_soft_demap(underflow),
                          v1_channel.cmy7_soft_demap(underflow))


def test_cmy7_codebook_and_state_plane_maps_match_v1_channel():
    rng = np.random.default_rng(FORMAT_SEED + 6)
    assert np.array_equal(h3_tc.CMY7_CODEBOOK, v1_channel.CMY7_CODEBOOK)
    bits11 = rng.integers(0, 2, (17, 11), dtype=np.uint8)
    assert np.array_equal(h3_tc.cmy7_map(bits11), v1_channel.cmy7_map(bits11))
    states = rng.integers(0, 8, 23, dtype=np.uint8)
    assert np.array_equal(h3_tc.planes_to_states(h3_tc.states_to_planes(
        states)), states)
    assert np.array_equal(h3_tc.states_to_planes(states),
                          v1_channel.states_to_planes(states))


def test_cmy7_payload_demap_and_iterated_decode_match_v1_color_tile():
    rng = np.random.default_rng(FORMAT_SEED + 7)
    v1_bank = _v1_cmy7_bank()
    n_code = 10934
    n_cells = 3976
    outcomes = {"pass1": 0, "iterated": 0, "failed": 0}
    for counter in range(_n(2, 104)):
        interleave = v1_ks.cmy7_interleave_permutation(TC_SEED, counter,
                                                       n_code)
        dither = v1_ks.cmy7_dither_bits(TC_SEED, counter, n_code)
        user = rng.integers(0, 2, 5974, dtype=np.uint8)
        states = v1_color_tile.cmy7_encode_payload(user, v1_bank, interleave,
                                                   dither)
        assert np.array_equal(
            h3_tc.cmy7_encode_payload(user, CMY7_BANK, interleave, dither),
            states)
        magnitude = 7.0
        sigma = (2.5, 2.75, 3.1)[counter % 3]
        scores = rng.normal(0.0, sigma, (n_cells, 6))
        inked = states > 0
        scores[np.flatnonzero(inked),
               states[inked].astype(np.int64) - 1] += magnitude
        scores[~inked] -= magnitude
        observed = np.ones(n_cells, dtype=bool)
        if counter % 4 == 1:
            observed[rng.integers(0, n_cells, 30)] = False
        mine_llr = h3_tc.cmy7_demap_payload(scores, observed, CMY7_BANK,
                                            interleave, dither)
        v1_llr = v1_color_tile.cmy7_demap_payload(scores, observed, v1_bank,
                                                  interleave, dither)
        assert np.array_equal(mine_llr, v1_llr)
        mine = h3_tc.cmy7_iterated_decode(mine_llr, scores, observed,
                                          CMY7_BANK, interleave, dither, 60,
                                          0.8, 3)
        theirs = v1_color_tile.cmy7_iterated_decode(
            v1_llr, scores, observed, v1_bank, interleave, dither,
            max_iters=60, alpha=0.8, demap_iterations=3)
        _same_frame_outcome(mine, theirs, check_extrinsic=False)
        assert mine[5] is None
        single = h3_tc.cmy7_iterated_decode(mine_llr, scores, observed,
                                            CMY7_BANK, interleave, dither, 60,
                                            0.8, 1)
        first = v1_frame.decode_frame(v1_llr, v1_bank, max_iters=60,
                                      alpha=0.8)
        _same_frame_outcome(single, first, check_extrinsic=False)
        if theirs.ok:
            assert np.array_equal(theirs.certified_user_bits, user)
            outcomes["pass1" if first.ok else "iterated"] += 1
        else:
            outcomes["failed"] += 1
    assert sum(outcomes.values()) == _n(2, 104)
    assert outcomes["pass1"] + outcomes["iterated"] > 0


def test_cmy8_encode_and_per_stream_decode_match_v1_color_tile():
    rng = np.random.default_rng(FORMAT_SEED + 8)
    v1_banks = _v1_cmy8_banks()
    outcomes = {True: 0, False: 0}
    for counter in range(_n(3, 35)):
        users = {stream_id: rng.integers(0, 2, 2088, dtype=np.uint8)
                 for stream_id in ("C", "M", "Y")}
        dithers = {stream_id: v1_ks.cmy8_dither_bits(TC_SEED, stream_id,
                                                     counter, 3976)
                   for stream_id in ("C", "M", "Y")}
        v1_states = v1_color_tile.cmy8_encode_payload(users, v1_banks, dithers)
        mine_states = h3_tc.cmy8_encode_payload(
            tuple(users[s] for s in ("C", "M", "Y")),
            tuple((CMY8_BANKS[s],) for s in ("C", "M", "Y")),
            tuple(dithers[s] for s in ("C", "M", "Y")))
        assert np.array_equal(mine_states, v1_states)
        for stream_id in ("C", "M", "Y"):
            wire = v1_frame.encode_frame(users[stream_id],
                                         v1_banks[stream_id]) \
                ^ dithers[stream_id]
            p_flip = (0.0, 0.04, 0.08)[counter % 3]
            llr = (2.0 * wire.astype(np.float64) - 1.0) * rng.uniform(
                0.8, 6.0, 3976)
            llr[rng.random(3976) < p_flip] *= -1.0
            llr[rng.random(3976) < 0.02] = 0.0
            mine = h3_tc.cmy8_decode_stream(llr, (CMY8_BANKS[stream_id],),
                                            dithers[stream_id], 60, 0.8)
            theirs = v1_color_tile.cmy8_decode_stream(
                llr, v1_banks[stream_id], dithers[stream_id], max_iters=60,
                alpha=0.8)
            _same_frame_outcome(mine, theirs, check_extrinsic=True)
            if theirs.ok:
                assert np.array_equal(theirs.certified_user_bits,
                                      users[stream_id])
            outcomes[bool(theirs.ok)] += 1
    assert outcomes[True] > 0

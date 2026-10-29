"""Column-group pools (docs/CMY8-COLUMN-GROUPS.md; rulings 2026-09-04):
uneven cmy8 rung triplets under ONE pooled fountain.

Five families:

* the (Z, bounds, carried) LAW — the rational partition, the ruled
  argmin over Z <= 32, the one-group case at equal widths, the ladder
  table the design doc quotes;
* the SLOT MAP — every source chunk of every block in exactly one slot,
  repair rows consecutive from K_b, the straddling tile's zero tail,
  key-order fill for uneven rows against the frozen ascending order for
  uniform ones, per-segment group balance;
* the ENCODER against a slot-by-slot oracle (the one-group path is the
  fork guard pinned in test_pooled_fountain / test_holo_fountain);
* the weighted CAPACITY tiers, the reserve rule and the planner;
* the manifest block and the frozen EMISSION GOLDENS of the two ruled
  rows — r0700x0700x0547 (the INDEPENDENT-PLANES §H Y lever) and
  r0850x0850x0775 — at 10x10, plus the lever at sheet J's 53x37
  geometry.  Movement = format fork.
"""
from __future__ import annotations

import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

import holo.core.fountain as fnt
from holo.core import capacity
from holo.core import column_groups as groups_law
from holo.core.keystream import DOMAIN_BLOCK_ASSIGN, keys64
from holo.format.lattice import parse_format_id
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes, plan_volume

SEED = b"column-groups-test-seed"
WIDTHS = (40, 40, 30)          # Z=4, groups of 10, the narrow stream 3
TPP = 64


# ------------------------------------------------------------------- law

def _ladder_widths(*rungs: str) -> tuple[int, ...]:
    ladder = {"r0547": 2240, "r0550": 2240, "r0625": 2560, "r0700": 2880,
              "r0775": 3200, "r0850": 3520}
    return tuple(ladder[r] - 120 - 32 - 1 for r in rungs)


@pytest.mark.parametrize("rungs,z,carried,spare", [
    (("r0850", "r0850", "r0775"), 21, (21, 21, 19), Fraction(2, 3)),
    (("r0700", "r0700", "r0547"), 17, (17, 17, 13), Fraction(28, 17)),
    (("r0700", "r0700", "r0625"), 17, (17, 17, 15), Fraction(14, 17)),
    (("r0850", "r0850", "r0700"), 21, (21, 21, 17), Fraction(4, 3)),
    (("r0850", "r0850", "r0625"), 7, (7, 7, 5), Fraction(2)),
])
def test_ladder_triplets_land_on_the_ruled_groupings(rungs, z, carried,
                                                     spare):
    widths = _ladder_widths(*rungs)
    g = groups_law.column_groups(widths)
    assert (g.n_groups, g.carried, g.spare_bits_per_site) == (
        z, carried, spare)
    assert g.symbol_bits == max(widths) and g.bounds[0] == 0
    group_widths = {g.width(i) for i in range(z)}
    assert max(group_widths) - min(group_widths) <= 1
    assert g.bounds == tuple((i * max(widths)) // z for i in range(z + 1))
    assert not g.uniform


def test_equal_widths_are_one_group_carrying_the_whole_symbol():
    g = groups_law.column_groups((2087, 2087, 2087))
    assert g.uniform and g.bounds == (0, 2087) and g.carried == (1, 1, 1)
    assert g.spare_bits_per_site == 0
    assert g.any_plane_ceiling == Fraction(2, 3)
    assert groups_law.column_groups((2727,)).carried == (1,)


def test_the_argmin_is_over_the_mean_spare_and_ties_go_to_the_smaller_z():
    g = groups_law.column_groups(WIDTHS)
    assert (g.n_groups, g.carried) == (4, (4, 4, 3))
    assert g.spare_bits_per_site == 0          # Z=8 ties at 0; 4 is smaller
    # no other Z does better, checked against the rule written out by
    # hand (floor partition, widest cyclic window); a 31-bit stream in
    # place of the 30-bit one is the same rule landing on Z=31
    assert groups_law.column_groups((40, 40, 31)).n_groups == 31
    for z in range(2, groups_law.MAX_COLUMN_GROUPS + 1):
        bounds = [(i * 40) // z for i in range(z + 1)]
        widths = tuple(bounds[i + 1] - bounds[i] for i in range(z))
        doubled = widths + widths
        carried = []
        for w in WIDTHS:
            n = max((n for n in range(z + 1)
                     if max(sum(doubled[i:i + n]) for i in range(z)) <= w),
                    default=0)
            carried.append(n)
        if min(carried) < 1:
            continue
        spare = sum(Fraction(w * z - c * 40, z)
                    for w, c in zip(WIDTHS, carried))
        assert spare > g.spare_bits_per_site or (
            spare == g.spare_bits_per_site and z >= g.n_groups)


def test_carried_groups_is_the_widest_cyclic_window_law():
    assert groups_law._carried_groups((10, 10, 10, 10), 31) == 3
    assert groups_law._carried_groups((10, 10, 10, 10), 30) == 3
    assert groups_law._carried_groups((10, 10, 10, 10), 29) == 2
    assert groups_law._carried_groups((4, 5, 4, 5), 9) == 2     # the 5+4 window
    assert groups_law._carried_groups((4, 5, 4, 5), 8) == 1
    assert groups_law._carried_groups((4, 5, 4, 5), 3) == 0


def test_a_stream_too_narrow_for_one_group_at_every_z_refuses():
    with pytest.raises(ValueError, match="no column grouping"):
        groups_law.column_groups((3000, 50))
    with pytest.raises(ValueError, match="positive"):
        groups_law.column_groups((40, 0))


def test_plane_tier_ceilings_follow_the_carried_weights():
    lever = groups_law.column_groups(_ladder_widths("r0700", "r0700", "r0547"))
    assert lever.chunks_per_site == 47
    assert lever.plane_tier_ceiling(2) == Fraction(34, 47)
    assert lever.plane_tier_ceiling(0) == Fraction(30, 47)
    assert lever.any_plane_ceiling == Fraction(30, 47)
    top = groups_law.column_groups(_ladder_widths("r0850", "r0850", "r0775"))
    assert top.any_plane_ceiling == Fraction(40, 61)
    assert top.plane_tier_ceiling(2) == Fraction(42, 61)


# The cmy pairs (docs/CMY-DESIGN.md §3.2) pool through the same law at
# n = 2.  p120 and p300 are pinned from the design text by
# test_cmy_vectors; these are the densities between, where Z is not
# monotone in p (the furniture axis's FORMAT-SPACE §18 finding).
@pytest.mark.parametrize("pair,p,widths,z,carried,any_one,reserve", [
    ("r0775x0700", 101, (3066, 2746), 19, (19, 17), Fraction(17, 36), 21),
    ("r0775x0700", 150, (3017, 2697), 28, (28, 25), Fraction(25, 53), 21),
    ("r0775x0700", 200, (2967, 2647), 9, (9, 8), Fraction(8, 17), 20),
    ("r0700x0625", 101, (2746, 2426), 17, (17, 15), Fraction(15, 32), 21),
    ("r0700x0625", 150, (2697, 2377), 25, (25, 22), Fraction(22, 47), 21),
    ("r0700x0625", 200, (2647, 2327), 8, (8, 7), Fraction(7, 15), 19),
    ("r0850x0700", 101, (3386, 2746), 21, (21, 17), Fraction(17, 38), 21),
    ("r0850x0700", 150, (3337, 2697), 26, (26, 21), Fraction(21, 47), 21),
    ("r0850x0700", 200, (3287, 2647), 5, (5, 4), Fraction(4, 9), 19),
])
def test_cmy_pairs_group_by_the_same_law_at_every_furniture_density(
        pair, p, widths, z, carried, any_one, reserve):
    spec = parse_format_id(f"c2-cmy-{pair}-p{p}@10x10")
    assert spec.stream_symbol_bits == widths
    g = spec.column_groups
    assert (g.n_groups, g.carried) == (z, carried)
    assert g.any_plane_ceiling == g.plane_tier_ceiling(0) == any_one
    assert g.plane_tier_ceiling(1) == Fraction(z, z + carried[1])
    assert capacity.rank_reserve_for(1, solves_per_block=z) == reserve


# -------------------------------------------------------------- slot map

def _mixed_code(k_meta: int = 43, seed: bytes = SEED) -> fnt.VolumeCode:
    """widths (40, 40, 30) -> Z=4, carried (4, 4, 3); K = 3*k_meta.  At
    k_meta = 43 the 516 source chunks of the one block run past page
    0's 256 C and 256 M chunks into the Y segment: Y tile 0 holds three
    source chunks, Y tile 1 straddles (one source chunk, then zeros),
    every later Y tile is a repair tile."""
    return fnt.VolumeCode(3 * k_meta, 40, seed, tiles_per_page=TPP,
                          n_streams=3, groups=groups_law.column_groups(WIDTHS))


def _slots_over(code: fnt.VolumeCode, n_pages: int):
    return [(esi, code.tile_slots(esi))
            for esi in range(n_pages * code.symbols_per_page)]


def test_every_source_chunk_sits_in_exactly_one_slot_and_repair_rows_are_dense():
    code = _mixed_code()
    kb, z = code.k_per_block[0], code.groups.n_groups
    seen: dict[tuple[int, int], int] = {}
    repair_rows = []
    for esi, tile in _slots_over(code, 2):
        assert tile.block == 0
        if tile.repair_row is None:
            for g, r in zip(tile.groups, tile.source_rows):
                assert r >= 0
                assert (r, g) not in seen
                seen[(r, g)] = esi
        else:
            assert tile.repair_row >= kb
            assert all(r == -1 for r in tile.source_rows)
            repair_rows.append(tile.repair_row)
    assert len(seen) == kb * z
    assert sorted(repair_rows) == list(range(kb, kb + len(repair_rows)))
    assert code.systematic_positions(0) == 128 + 2      # C, M, two Y tiles


def test_the_straddling_tile_keeps_its_source_chunks_and_a_zero_tail():
    code = _mixed_code()
    y_tiles = [tile for esi, tile in _slots_over(code, 1) if esi % 3 == 2]
    systematic = [t for t in y_tiles if t.repair_row is None]
    first, straddler = sorted(systematic, key=lambda t: -len(t.groups))
    assert first.groups == (0, 1, 2) and first.source_rows == (128,) * 3
    assert first.edges == (0, 10, 20, 30)
    assert straddler.groups == (3,) and straddler.source_rows == (128,)
    assert straddler.edges == (0, 10)          # 20 zero bits follow
    # the Y tile after them in FILL order is the block's first repair
    # tile; the residue rotation runs on through the straddler's two
    # zero chunks (516, 517), so it starts at chunk 518 = group 2
    nxt = next(t for t in y_tiles if t.repair_row == code.k_per_block[0])
    assert nxt.groups == (2, 3, 0) and nxt.source_rows == (-1, -1, -1)


def test_slot_widths_are_the_group_widths_and_never_exceed_the_stream():
    code = _mixed_code()
    for esi, tile in _slots_over(code, 2):
        widths = tuple(hi - lo for lo, hi in zip(tile.edges,
                                                  tile.edges[1:]))
        assert widths == tuple(code.groups.width(g) for g in tile.groups)
        assert tile.edges[-1] <= code.groups.widths[esi % 3]
        # consecutive residues mod Z
        for a, b in zip(tile.groups, tile.groups[1:]):
            assert b == (a + 1) % code.groups.n_groups


def test_a_narrow_stream_misses_every_group_equally_often_per_segment():
    code = _mixed_code(k_meta=10)          # all of page 0's Y is repair
    z = code.groups.n_groups
    for page in range(3):
        counts = [0] * z
        for local in range(TPP):
            tile = code.tile_slots(page * code.symbols_per_page + local * 3 + 2)
            for g in tile.groups:
                counts[g] += 1
        share = Fraction(TPP * code.groups.carried[2], z)
        assert all(share - 1 < c < share + 1 for c in counts), counts


def test_uneven_rows_fill_in_key_order_and_uniform_rows_in_the_frozen_order():
    mixed = _mixed_code()
    uniform = fnt.VolumeCode(3 * 43, 40, SEED, tiles_per_page=TPP,
                             n_streams=3)
    assert uniform.groups.uniform and not mixed.groups.uniform
    for page in range(2):
        _, rows_mixed = mixed.page_assignment(page)
        _, rows_uniform = uniform.page_assignment(page)
        for stream in range(3):
            keys = keys64(SEED, DOMAIN_BLOCK_ASSIGN, 0, page,
                          np.arange(TPP, dtype=np.int64) * 3 + stream, 0)
            order = np.argsort(keys, kind="stable")
            by_key = rows_mixed[stream::3][order]
            assert np.array_equal(by_key, np.sort(by_key))       # key order
            ascending = rows_uniform[stream::3]
            assert np.array_equal(ascending, np.sort(ascending))  # frozen
            assert not np.array_equal(rows_mixed[stream::3], ascending)
        assert np.array_equal(mixed.page_assignment(page)[0],
                              uniform.page_assignment(page)[0])  # blocks


def test_the_one_group_row_helpers_refuse_a_column_group_pool():
    code = _mixed_code()
    with pytest.raises(ValueError, match="tile_slots"):
        code.source_row_of(0)
    with pytest.raises(ValueError, match="tile_slots"):
        code.generator_row(0)
    uniform = fnt.VolumeCode(3 * 43, 40, SEED, tiles_per_page=TPP,
                             n_streams=3)
    assert uniform.source_row_of(0) == 0
    tile = uniform.tile_slots(0)
    assert tile == groups_law.TileSlots(0, (0,), (0,), None, (0, 40))


def test_the_core_decoder_refuses_a_column_group_code():
    with pytest.raises(ValueError, match="decoded by holo3"):
        fnt.Decoder(_mixed_code())
    uniform = fnt.VolumeCode(3 * 43, 40, SEED, tiles_per_page=TPP,
                             n_streams=3)
    assert fnt.Decoder(uniform).code is uniform


def test_column_groups_must_agree_with_the_code():
    with pytest.raises(ValueError, match="disagree"):
        fnt.VolumeCode(30, 40, SEED, tiles_per_page=TPP, n_streams=2,
                       groups=groups_law.column_groups(WIDTHS))
    with pytest.raises(ValueError, match="disagree"):
        fnt.VolumeCode(30, 39, SEED, tiles_per_page=TPP, n_streams=3,
                       groups=groups_law.column_groups(WIDTHS))


# --------------------------------------------------------------- encoder

def test_encode_symbols_fills_every_slot_from_its_row_and_zeroes_the_tail():
    code = _mixed_code()
    k = code.k_total
    rng = np.random.default_rng(20260904)
    src = fnt.pack_source(rng.bytes(k * 40 // 8), k, 40)
    full = fnt.unpack_rows(src, 40)
    esis = np.arange(2 * code.symbols_per_page, dtype=np.int64)
    out = code.encode_symbols(src, esis)
    assert out.shape == (esis.size, 40)
    n_straddle = n_repair = 0
    for esi in esis:
        tile = code.tile_slots(int(esi))
        if tile.repair_row is None:
            rows = {r: full[r] for r in tile.source_rows}
            n_straddle += tile.edges[-1] < 30 and esi % 3 == 2
        else:
            coeff = fnt.fountain_rows_bits(SEED, 0, [tile.repair_row], k)[0]
            sel = np.flatnonzero(coeff)
            rows = {-1: (np.bitwise_xor.reduce(full[sel], axis=0)
                         if sel.size else np.zeros(40, np.uint8))}
            n_repair += 1
        for g, r, lo, hi in zip(tile.groups, tile.source_rows,
                                tile.edges, tile.edges[1:]):
            expected = rows[r][code.groups.bounds[g]:
                               code.groups.bounds[g + 1]]
            np.testing.assert_array_equal(out[esi, lo:hi], expected)
        assert not out[esi, tile.edges[-1]:].any()
    assert n_straddle == 1 and n_repair > 0


# -------------------------------------------------------------- capacity

def test_one_group_weights_are_the_uniform_pooled_arithmetic():
    uniform = groups_law.column_groups((2087, 2087, 2087))
    for k in (1, 30, 3000, 16_384, 16_385, 40_000):
        for tpp, pages, q in ((1872, 1, 0.5), (840, 3, 0.35),
                              (1961, 2, 0.66), (100, 8, 0.9)):
            for tier in (True, False):
                assert capacity.pooled_page_capacity_sufficient(
                    k, tpp, pages, q, n_streams=3,
                    enforce_plane_tier=tier, groups=uniform) == \
                    capacity.pooled_page_capacity_sufficient(
                        k, tpp, pages, q, n_streams=3,
                        enforce_plane_tier=tier)
            assert capacity.pooled_max_k_for_pages(
                tpp, pages, q, n_streams=3, groups=uniform) == \
                capacity.pooled_max_k_for_pages(tpp, pages, q, n_streams=3)


def test_weighted_tiers_by_hand_on_one_page():
    """T=64, B=1, P=1, q=0.5, Z=4, carried (4, 4, 3): per stream a page
    gives every group 64, 64 and 48 rows; the reserve is 16 + 2; the
    fragment budget floor(0.5 * 64 * 11 / 4) = 88 binds: K <= 70, and
    the canonical-K law floors that to a multiple of three."""
    g = groups_law.column_groups(WIDTHS)
    assert capacity.rank_reserve_for(1, solves_per_block=g.n_groups) == 18
    assert capacity.pooled_max_k_for_pages(64, 1, 0.5, n_streams=3,
                                      groups=g) == 69
    assert capacity.pooled_page_capacity_sufficient(69, 64, 1, 0.5, n_streams=3,
                                               groups=g)
    assert capacity.pooled_page_capacity_sufficient(70, 64, 1, 0.5, n_streams=3,
                                               groups=g)
    assert not capacity.pooled_page_capacity_sufficient(
        71, 64, 1, 0.5, n_streams=3, groups=g)
    # the dead-plane tier binds on the HEAVIEST stream: at q = 0.9 the
    # budget allows 158 but any dead C or M leaves 176 - 64 = 112 rows
    assert capacity.pooled_max_k_for_pages(64, 1, 0.9, n_streams=3, groups=g,
                                      enforce_plane_tier=False) == 138
    assert capacity.pooled_max_k_for_pages(64, 1, 0.9, n_streams=3,
                                      groups=g) == 93


@pytest.mark.parametrize("tpp,pages,q", [
    (64, 1, 0.5), (100, 3, 0.35), (1961, 1, 0.66), (840, 4, 0.9)])
def test_max_k_is_the_largest_multiple_of_three_the_weighted_tiers_admit(
        tpp, pages, q):
    g = groups_law.column_groups(_ladder_widths("r0700", "r0700", "r0547"))
    for tier in (True, False):
        k = capacity.pooled_max_k_for_pages(tpp, pages, q, n_streams=3,
                                       enforce_plane_tier=tier, groups=g)
        assert k % 3 == 0
        assert capacity.pooled_page_capacity_sufficient(
            k, tpp, pages, q, n_streams=3, enforce_plane_tier=tier,
            groups=g)
        assert not capacity.pooled_page_capacity_sufficient(
            k + 3, tpp, pages, q, n_streams=3, enforce_plane_tier=tier,
            groups=g)


def test_the_reserve_covers_every_group_solve():
    assert capacity.rank_reserve_for(1, solves_per_block=17) == 21
    assert capacity.rank_reserve_for(2, solves_per_block=21) == 22
    assert capacity.rank_reserve_for(1, solves_per_block=1) == 16


# ---------------------------------------------------------------- planner

LEVER_10 = "c3-cmy8-r0700x0700x0547@10x10"
TOP_10 = "c3-cmy8-r0850x0850x0775@10x10"
LEVER_53 = "c2-cmy8-r0700x0700x0547@53x37"


def test_the_planner_prices_an_uneven_row_by_its_groups():
    spec = parse_format_id(LEVER_10)
    g = groups_law.column_groups(spec.stream_symbol_bits)
    plan = plan_volume(spec, 20_000, 0.35)
    assert (plan.k_meta, plan.k_total, plan.n_pages) == (20, 60, 1)
    assert plan.n_symbols_total == 300
    assert plan.plane_tier == "guaranteed"
    code = fnt.VolumeCode(plan.k_total, spec.symbol_bits, spec.seed,
                          tiles_per_page=100, n_streams=3, groups=g)
    assert plan.n_repair == 300 - code.systematic_positions(0) == 240
    assert plan.effective_k_over_n == pytest.approx(
        60 * 17 * 3 / (300 * 47))
    assert plan_volume(spec, 1_000, 0.63).plane_tier == "guaranteed"
    assert plan_volume(spec, 1_000, 0.64).plane_tier == \
        "not-at-this-dial (needs q <= 30/47)"
    cap = max_payload_bytes(spec, 0.35, 1)
    assert cap == 25_529
    assert plan_volume(spec, cap, 0.35).n_pages == 1
    assert plan_volume(spec, cap + 4_000, 0.35).n_pages == 2


def test_the_manifest_names_the_groups_only_on_an_uneven_row(tmp_path):
    spec = parse_format_id(LEVER_10)
    payload = bytes(i % 251 for i in range(20_000))
    emit_volume(spec, payload, 0.5, tmp_path / "vol")
    manifest = json.loads((tmp_path / "vol" / "manifest.json").read_text())
    assert manifest["pooled_fountain"]["column_groups"] == {
        "n_groups": 17,
        "symbol_bits": 2727,
        "carried_per_tile": {"C": 17, "M": 17, "Y": 13},
        "spare_bits_per_site": "28/17",
        "dead_plane_ceiling": {"C": "30/47", "M": "30/47", "Y": "34/47"},
    }
    assert manifest["volume"]["symbol_bits"] == 2727
    assert manifest["volume"]["stream_symbol_bits"] == [2727, 2727, 2087]
    assert manifest["volume"]["aggregate_symbol_bits"] == 3 * 2727


# ----------------------------------------------------------------- goldens

# Frozen 2026-09-04 (payload = bytes(i % 251), q = 0.5, page 0; the 53x37
# lever on the A4-4mm bundle, sheet J's paper).  Movement = format fork.
EMIT_GOLDENS = {
    LEVER_10: {
        "payload_bytes": 20_000, "k_meta": 20, "paper": None,
        "ps_sha256":
            "fd78a100ef6a2cdb51b970891052a994fc63f975493f883e968d322f3d4fde95",
        "gt_sha256":
            "09535b4b50a5a46e094a0932111aa5eb42ce36c2a0403690046b915ce6c68fc8",
        "gt_plane_sha256": (
            "c52a87dc58accb6b4d4415a575bc7f86eb54221910245a4f5165f866ef4225dd",
            "b498929d5b4af3b6fc2fd5987d5f33695b87907c777b3c2705d60c68334c2be6",
            "aa76b7d1e7dcdb417f20670adf483f3e426ff0660ecdc53fe0d3e1a1e5342065",
        ),
    },
    TOP_10: {
        "payload_bytes": 20_000, "k_meta": 16, "paper": None,
        "ps_sha256":
            "8b39c26651a17d8f7164e9a04d6301cd57e3f14e0904411e3a39b2bf63967a6d",
        "gt_sha256":
            "1fc4af9ad78fd6304b6e72dd1aaa32d6d86eb29ac361d4cf21e9d0257b3c0d8e",
        "gt_plane_sha256": (
            "61ae5a31cc6da6789262b40e8c4a93454421ce5c8296c6595506421405d7d536",
            "e4441131b9cd0976a2168f16834e9657274cf5ed24fbc2e5b254957deb87cb86",
            "9c41ea6506b9c190c14acb2660e5ed29f3158d86d391fae7dd3ee594c76503a5",
        ),
    },
    LEVER_53: {
        "payload_bytes": 400_000, "k_meta": 392, "paper": "A4-4mm",
        "ps_sha256":
            "2f7ba3a1d81297aa24ccc9f8e0ac9ee8f9154b76dd6525e030287a9575ea6683",
        "gt_sha256":
            "e1595193ce31aba606b2c7710a99d04c3e0093a1ec9cd6106bfdc2a4c1cbabcc",
        "gt_plane_sha256": (
            "3a838296819dd167220035a239699f8db41437e1d636b7fffe06d4e3ab9ca290",
            "e9da120654995403355764750c0890f7d83f5408db139065214bfbbd207e70e1",
            "d273f8069764745564c9e18379194d44d44bf7407dce6d9c6df35520e14f773d",
        ),
    },
}


# The 53x37 lever is a whole printed-size emission — a fork guard on a
# separate identity, not per-commit feedback, so it rides the slow lane
# while the two 10x10 rows stay in every commit's reach (2026-09-20).
@pytest.mark.parametrize("ref", [
    pytest.param(
        ref,
        marks=pytest.mark.skipif(
            os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
            reason=("set HOLO_RUN_SLOW_TESTS=1 for the printed-size "
                    "emission goldens"),
        ) if ref == LEVER_53 else (),
    )
    for ref in sorted(EMIT_GOLDENS)
])
def test_uneven_row_emission_goldens(ref: str, tmp_path: Path):
    spec = parse_format_id(ref)
    golden = EMIT_GOLDENS[ref]
    payload = bytes(i % 251 for i in range(golden["payload_bytes"]))
    kwargs = {} if golden["paper"] is None else {"paper": golden["paper"]}
    vol = emit_volume(spec, payload, 0.5, tmp_path / "vol", **kwargs)
    assert vol.plan.k_meta == golden["k_meta"]
    assert vol.plan.k_total == 3 * golden["k_meta"]
    assert vol.plan.n_pages == 1
    page = vol.pages[0]
    assert page.ps_sha256 == golden["ps_sha256"]
    assert page.gt_sha256 == golden["gt_sha256"]
    assert page.gt_plane_sha256 == golden["gt_plane_sha256"]
    packed = np.load(tmp_path / "vol" / "page000_gt.npy")
    assert hashlib.sha256(
        packed.tobytes(order="C")).hexdigest() == golden["gt_sha256"]

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from holo3.format import close, fountain, identity, keystream, metadata
from holo3.tests.test_h3_format_close import (
    TILES_PER_PAGE, TILES_YX, Row, Stream, _bit, _cert, _source_rows, _word)
from holo3.tests.test_h3_format_fountain import _naive_ge, _source

# hand-copied second copy of tests/holo/test_column_groups.py's law table
SEED = b"h3/column-groups"
WIDTHS = (40, 40, 30)
LADDER_TABLE = [
    ((3367, 3367, 3047), 21, (21, 21, 19), Fraction(2, 3)),
    ((2727, 2727, 2087), 17, (17, 17, 13), Fraction(28, 17)),
    ((2727, 2727, 2407), 17, (17, 17, 15), Fraction(14, 17)),
    ((3367, 3367, 2727), 21, (21, 21, 17), Fraction(4, 3)),
    ((3367, 3367, 2407), 7, (7, 7, 5), Fraction(2)),
]


def _mixed_code(k_meta: int = 43, seed: bytes = SEED) -> fountain.VolumeCode:
    return fountain.VolumeCode(3 * k_meta, 40, seed, TILES_PER_PAGE,
                               n_streams=3,
                               groups=fountain.column_groups(WIDTHS))


def _tile_bits(code: fountain.VolumeCode, source: np.ndarray,
               esi: int) -> np.ndarray:
    tile = code.tile_slots(esi)
    offset = code.block_offsets[tile.block]
    k_block = code.k_per_block[tile.block]
    if tile.repair_row is None:
        rows = {r: source[offset + r] for r in tile.source_rows}
    else:
        coefficients = keystream.fountain_rows_bits(
            code.seed, tile.block, [tile.repair_row], k_block)[0]
        picked = source[offset:offset + k_block][coefficients.astype(bool)]
        rows = {-1: (np.bitwise_xor.reduce(picked, axis=0)
                     if picked.size else np.zeros(code.s_bits, np.uint8))}
    out = np.zeros(code.groups.widths[esi % code.n_streams], np.uint8)
    for g, r, lo, hi in zip(tile.groups, tile.source_rows, tile.edges,
                            tile.edges[1:]):
        out[lo:hi] = rows[r][code.groups.bounds[g]:code.groups.bounds[g + 1]]
    return out


@pytest.mark.parametrize("widths,z,carried,spare", LADDER_TABLE)
def test_ladder_triplets_land_on_the_ruled_groupings(widths, z, carried,
                                                     spare):
    g = fountain.column_groups(widths)
    assert (g.n_groups, g.carried, g.spare_bits_per_site) == (
        z, carried, spare)
    assert g.bounds == tuple((i * max(widths)) // z for i in range(z + 1))


def test_equal_widths_are_one_group():
    g = fountain.column_groups((2087, 2087, 2087))
    assert g.uniform and g.bounds == (0, 2087) and g.carried == (1, 1, 1)


def test_the_law_and_the_slot_map_agree_with_src_holo():
    v1 = pytest.importorskip("holo.core.fountain")
    v1_law = pytest.importorskip("holo.core.column_groups")
    for widths, *_rest in LADDER_TABLE + [(WIDTHS,)]:
        ours, theirs = (fountain.column_groups(widths),
                        v1_law.column_groups(widths))
        assert (ours.bounds, ours.carried) == (theirs.bounds, theirs.carried)
    ours = _mixed_code()
    theirs = v1.VolumeCode(ours.k_total, 40, SEED, tiles_per_page=TILES_PER_PAGE,
                           n_streams=3, groups=v1_law.column_groups(WIDTHS))
    for page in range(3):
        for a, b in zip(ours.page_assignment(page),
                        theirs.page_assignment(page)):
            np.testing.assert_array_equal(a, b)
    for esi in range(3 * ours.symbols_per_page):
        a, b = ours.tile_slots(esi), theirs.tile_slots(esi)
        assert (a.block, a.groups, a.source_rows, a.repair_row, a.edges) \
            == (b.block, b.groups, b.source_rows, b.repair_row, b.edges)
    assert ours.systematic_positions(0) == theirs.systematic_positions(0)


def test_src_holo_encodes_what_the_decoder_solves():
    v1 = pytest.importorskip("holo.core.fountain")
    v1_law = pytest.importorskip("holo.core.column_groups")
    code = _mixed_code()
    k = code.k_total
    rng = np.random.default_rng(20260904)
    packed = v1.pack_source(rng.bytes(k * 40 // 8), k, 40)
    source = v1.unpack_rows(packed, 40)
    theirs = v1.VolumeCode(k, 40, SEED, tiles_per_page=TILES_PER_PAGE,
                           n_streams=3, groups=v1_law.column_groups(WIDTHS))
    esis = np.arange(2 * code.symbols_per_page, dtype=np.int64)
    symbols = theirs.encode_symbols(packed, esis)
    decoder = fountain.Decoder(code)
    for esi in esis:
        width = WIDTHS[int(esi) % 3]
        np.testing.assert_array_equal(symbols[esi, :width],
                                      _tile_bits(code, source, int(esi)))
        assert not symbols[esi, width:].any()
        decoder.add_symbol(int(esi), symbols[esi, :width])
    solved = decoder.try_solve()
    assert solved is not None and np.array_equal(solved, source)


def test_an_uneven_triplet_resolves_with_its_widths():
    row = identity.resolve_format_ref("c3-cmy8-r0700x0700x0547@10x10")
    assert row.row_id == "1i200-cmy8-r0700x0700x0547-p120-v1@10x10"
    assert row.pooled_fountain
    assert tuple(s.symbol_bits for s in row.streams) == (2727, 2727, 2087)
    assert tuple(s.rung_children[0][0] for s in row.streams) == (
        "r0700", "r0700", "r0547")


@pytest.mark.parametrize("dropped_every", [0, 7, 3])
def test_a_mixed_pool_solves_per_group_and_agrees_with_a_naive_oracle(
        dropped_every: int):
    code = _mixed_code()
    k = code.k_total
    source = _source(k, 40, 20260904)
    esis = [esi for esi in range(2 * code.symbols_per_page)
            if not dropped_every or esi % dropped_every]
    decoder = fountain.Decoder(code)
    for esi in esis:
        assert decoder.add_symbol(esi, _tile_bits(code, source, esi))
    solved = decoder.try_solve()
    assert solved is not None and np.array_equal(solved, source)
    z = code.groups.n_groups
    for group in range(z):
        rows, values = [], []
        for esi in esis:
            tile = code.tile_slots(esi)
            for g, r, lo, hi in zip(tile.groups, tile.source_rows,
                                    tile.edges, tile.edges[1:]):
                if g != group:
                    continue
                row_index = r if r >= 0 else tile.repair_row
                if row_index < k:
                    row = np.zeros(k, np.uint8)
                    row[row_index] = 1
                else:
                    row = keystream.fountain_rows_bits(
                        SEED, 0, [row_index], k)[0]
                rows.append(row)
                values.append(_tile_bits(code, source, esi)[lo:hi])
        rank, oracle = _naive_ge(rows, values, k)
        assert rank == k
        lo, hi = code.groups.bounds[group], code.groups.bounds[group + 1]
        assert np.array_equal(oracle, source[:, lo:hi])
    assert decoder.block_status() == (
        fountain.BlockStatus(0, k, len(esis), k, k, True, 0, z, k),)


def test_a_dead_narrow_stream_still_solves_and_the_shortfall_is_per_group():
    code = _mixed_code()
    k = code.k_total
    source = _source(k, 40, 77)
    alive = [esi for esi in range(2 * code.symbols_per_page) if esi % 3 != 2]
    decoder = fountain.Decoder(code)
    for esi in alive:
        decoder.add_symbol(esi, _tile_bits(code, source, esi))
    solved = decoder.try_solve()
    assert solved is not None and np.array_equal(solved, source)
    starved = fountain.Decoder(code)
    for esi in alive[:k - 5]:
        starved.add_symbol(esi, _tile_bits(code, source, esi))
    assert starved.try_solve() is None
    (status,) = starved.block_status()
    assert (status.block, status.needed, status.have, status.solved) == (
        0, k, k - 5, False)
    assert status.rows == k - 5 and status.rank is None
    assert status.short == 5 and status.groups_open == status.n_groups == 4


def test_the_straddling_tile_carries_zero_bits_after_its_source_chunks():
    code = _mixed_code()
    source = _source(code.k_total, 40, 5)
    straddler = next(esi for esi in range(code.symbols_per_page)
                     if esi % 3 == 2 and code.tile_slots(esi).repair_row is None
                     and code.tile_slots(esi).edges[-1] < 30)
    bits = _tile_bits(code, source, straddler)
    assert bits.size == 30 and not bits[10:].any()
    assert np.array_equal(bits[:10], source[128][30:40])


def test_a_uniform_pool_is_the_one_group_case_of_the_general_decoder():
    code = fountain.VolumeCode(129, 40, SEED, TILES_PER_PAGE, n_streams=3)
    assert code.groups.uniform
    source = _source(129, 40, 9)
    decoder = fountain.Decoder(code)
    for esi in range(2 * code.symbols_per_page):
        tile = code.tile_slots(esi)
        block, row = code.block_row_of(esi)
        assert tile.edges == (0, 40) and tile.groups == (0,)
        assert (tile.source_rows, tile.repair_row) == (
            ((row,), None) if row < 129 else ((-1,), row))
        decoder.add_symbol(esi, _tile_bits(code, source, esi))
    solved = decoder.try_solve()
    assert solved is not None and np.array_equal(solved, source)


# ----------------------------------------------------------------- close

def _mixed_volume(payload: bytes, seed: bytes = b"h3/close/groups",
                  n_pages: int = 3):
    k_meta = close.source_symbol_count(len(payload), 3 * 40)
    k_total = 3 * k_meta
    rows = _source_rows(payload, k_total, 40)
    code = fountain.VolumeCode(k_total, 40, seed, TILES_PER_PAGE, n_streams=3,
                               groups=fountain.column_groups(WIDTHS))
    word = _word(0, k_meta)
    max_index = metadata.max_equation_index(3)
    stream_of = {0: "C", 1: "M", 2: "Y"}
    certs = []
    for esi in range(n_pages * code.symbols_per_page):
        counter, index = divmod(esi, 3)
        certs.append(_cert(counter, stream_of[index],
                           _bit(word, esi, max_index),
                           _tile_bits(code, rows, esi)))
    row_fact = Row(seed, TILES_YX,
                   (Stream("C", 40, 1), Stream("M", 40, 2),
                    Stream("Y", 30, 3)), True)
    return k_meta, k_total, code, certs, row_fact


def test_a_mixed_volume_closes_verified_from_its_own_widths():
    payload = np.random.default_rng(31).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    k_meta, k_total, code, certs, row = _mixed_volume(payload)
    assert code.k_total > 2 * TILES_PER_PAGE          # Y holds source chunks
    assert {c.user_bits.size for c in certs} == {41, 31}
    result = close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k_total == 3 * k_meta
    assert close.close_count_ready(certs, row)


def test_a_mixed_volume_survives_its_narrow_plane_dying():
    payload = np.random.default_rng(32).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    _k_meta, k_total, _code, certs, row = _mixed_volume(payload)
    alive = [cert for cert in certs if cert.stream_id != "Y"]
    result = close.close_volume(alive, row)
    assert result.status == "verified" and result.payload == payload
    assert close.close_count_ready(alive, row)
    heavy_dead = [cert for cert in certs if cert.stream_id != "C"]
    assert close.close_volume(heavy_dead, row).status == "verified"


def test_the_count_gate_counts_the_binding_group():
    payload = np.random.default_rng(33).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    _k_meta, k_total, code, certs, row = _mixed_volume(payload, n_pages=1)
    # the first 40 sites: C and M give every group 40 rows, Y 30 — no
    # group reaches K = 129, so the gate says not ready and the close
    # stays open with the binding group's shortfall
    partial = certs[:120]
    ready, counts = close.close_count_status(partial, row)
    assert not ready
    y_groups = [code.tile_slots(esi).groups for esi in range(2, 120, 3)]
    per_group = [sum(g in groups for groups in y_groups) for g in range(4)]
    binding = 80 + min(per_group)
    assert counts == {("pooled", 0): binding} and binding < k_total
    result = close.close_volume(partial, row)
    assert result.status == "open"
    assert result.blocks[0].have == 120 and result.blocks[0].rank is None
    assert result.blocks[0].short == k_total - binding
    progress = close.CloseProgress(row)
    progress.absorb({(c.page, c.ty, c.tx, c.stream_id): c for c in partial})
    assert progress.metadata_rank == metadata.METADATA_BITS
    assert not progress.count_ready
    _ready, needed, rows = progress.count_progress()
    assert needed == k_total and rows[0].have == 120
    assert rows[0].short == k_total - binding
    # the whole page: every group has 64 + 64 + 48 rows, the gate opens
    # and the close verifies
    assert close.close_count_ready(certs, row)
    assert close.close_volume(certs, row).status == "verified"


def test_a_conflicting_narrow_tile_is_fatal_never_voted():
    payload = np.random.default_rng(34).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    _k_meta, _k_total, _code, certs, row = _mixed_volume(payload)
    twisted = next(c for c in certs if c.stream_id == "Y")
    bits = twisted.user_bits.copy()
    bits[5] ^= 1
    from dataclasses import replace
    result = close.close_volume(certs + [replace(twisted, user_bits=bits)],
                                row)
    assert result.status == "integrity_failure"
    assert "conflicting" in (result.reason or "")


def test_page_scale_source_chunks_reach_the_narrow_plane_and_straddle():
    v1 = pytest.importorskip("holo.core.fountain")
    row = identity.resolve_format_ref("c3-cmy8-r0700x0700x0547@10x10")
    widths = tuple(s.symbol_bits for s in row.streams)
    groups = fountain.column_groups(widths)
    k_total, tpp = 3 * 79, row.tiles_per_page          # 80 KB at 10x10
    code = fountain.VolumeCode(k_total, max(widths), row.seed, tpp,
                               n_streams=3, groups=groups)
    systematic = [0, 0, 0]
    straddlers = []
    for esi in range(code.symbols_per_page):
        tile = code.tile_slots(esi)
        if tile.repair_row is None:
            systematic[esi % 3] += 1
            if len(tile.groups) < groups.carried[esi % 3]:
                straddlers.append(tile)
    assert systematic == [100, 100, 49] and len(straddlers) == 1
    assert straddlers[0].edges[-1] < widths[2]
    assert code.systematic_positions(0) == 249
    rng = np.random.default_rng(20260905)
    packed = v1.pack_source(rng.bytes(k_total * max(widths) // 8),
                            k_total, max(widths))
    theirs = v1.VolumeCode(k_total, max(widths), row.seed, tiles_per_page=tpp,
                           n_streams=3, groups=groups)
    esis = np.arange(2 * code.symbols_per_page, dtype=np.int64)
    symbols = theirs.encode_symbols(packed, esis)
    decoder = fountain.Decoder(code)
    for esi in esis:
        decoder.add_symbol(int(esi), symbols[esi, :widths[int(esi) % 3]])
    solved = decoder.try_solve()
    assert solved is not None
    assert np.array_equal(solved, v1.unpack_rows(packed, max(widths)))


def test_the_progress_object_solves_incrementally_and_names_the_shortness(
        monkeypatch):
    payload = np.random.default_rng(35).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    _k_meta, k_total, code, certs, row = _mixed_volume(payload, n_pages=2)
    # page 0's first C row is withheld throughout: those eight source
    # symbols must come from repair rows, so the close has to eliminate
    keyed = {(c.page, c.ty, c.tx, c.stream_id): c for c in certs
             if not (c.stream_id == "C" and c.page == 0 and c.ty == 0)}
    first = dict(list(keyed.items())[:120])
    progress = close.CloseProgress(row)
    progress.absorb(first)
    assert progress.k_total == k_total and not progress.count_ready
    ready, needed, rows = progress.count_progress()
    assert not ready and needed == k_total
    (block,) = rows
    assert block.rank is None and block.short > 0
    assert block.groups_open == block.n_groups == 4
    assert progress.close_is_new()
    result = progress.close()
    assert result.status == "open"
    assert f"scarcest groups short {block.short} rows; 4 of 4 groups open" \
        in result.reason
    assert not progress.close_is_new()          # nothing new since
    progress.absorb(keyed)
    assert progress.count_ready and progress.close_is_new()
    eliminations = []
    real = fountain._ge_solve_gf2
    monkeypatch.setattr(fountain, "_ge_solve_gf2",
                        lambda *a: eliminations.append(1) or real(*a))
    result = progress.close()
    assert result.status == "verified" and result.payload == payload
    (block,) = result.blocks
    assert block.solved and block.short == 0 and block.groups_open == 0
    assert block.n_groups == 4 and block.rank == k_total
    assert len(eliminations) == 4              # one per group
    del eliminations[:]
    assert progress.close().status == "verified"
    assert eliminations == []                  # solved groups persist


def test_status_names_the_scarcest_group_and_forgets_a_stale_rank(
        monkeypatch):
    code = _mixed_code()
    k = code.k_total
    source = _source(k, 40, 11)
    decoder = fountain.Decoder(code)
    # every C and M tile of two pages, no Y at all: groups 0..3 each hold
    # 256 rows, all reach K, and the shortcut cannot fire for the eight
    # source symbols withheld below
    withheld = {esi for esi in range(code.symbols_per_page)
                if esi % 3 == 0 and code.tile_slots(esi).repair_row is None
                and code.tile_slots(esi).source_rows[0] < 8}
    for esi in range(2 * code.symbols_per_page):
        if esi % 3 != 2 and esi not in withheld:
            decoder.add_symbol(esi, _tile_bits(code, source, esi))
    assert decoder.try_solve() is not None
    # a fresh decoder where group 3 is starved: page 0's C tiles minus
    # the eight withheld ones (56 rows in every group) plus, from two
    # pages, only the Y tiles whose window misses group 3 (32 tiles,
    # rows in groups 0..2 only)
    starved = fountain.Decoder(code)
    for esi in range(2 * code.symbols_per_page):
        tile = code.tile_slots(esi)
        page0_c = esi < code.symbols_per_page and esi % 3 == 0
        if esi in withheld:
            continue
        if page0_c or (esi % 3 == 2 and 3 not in tile.groups):
            starved.add_symbol(esi, _tile_bits(code, source, esi))
    assert starved.try_solve() is None
    (status,) = starved.block_status()
    assert status.rows == 56 and status.rank is None
    assert status.short == k - 56 and status.groups_open == 4
    # page 0's M tiles bring every group 64 rows: groups 0..2 now hold
    # 152 with eight unit rows missing, so each eliminates once and
    # solves on its dense rows; group 3 holds 120 < 129 and stays open.
    # A second attempt with nothing new must not re-run anything.
    for esi in range(1, code.symbols_per_page, 3):
        starved.add_symbol(esi, _tile_bits(code, source, esi))
    eliminations = []
    real = fountain._ge_solve_gf2
    monkeypatch.setattr(fountain, "_ge_solve_gf2",
                        lambda *a: eliminations.append(1) or real(*a))
    assert starved.try_solve() is None
    assert len(eliminations) == 3
    assert starved.try_solve() is None
    assert len(eliminations) == 3
    (status,) = starved.block_status()
    assert status.rows == 120 and status.rank is None   # group 3 binds
    assert status.short == 9 and status.groups_open == 1


def test_an_eliminated_group_reports_its_rank_until_new_rows_arrive():
    code = _mixed_code()
    k = code.k_total
    source = _source(k, 40, 12)
    decoder = fountain.Decoder(code)
    # C and M tiles of page 0 (64 rows per group each) plus every Y
    # tile of page 0 for groups 0..2 only: those groups reach K with
    # dependent rows (page 0 alone spans 129 source symbols only
    # through Y's 65th source symbol), group 3 stays short
    for esi in range(code.symbols_per_page):
        tile = code.tile_slots(esi)
        if esi % 3 != 2 or 3 not in tile.groups:
            decoder.add_symbol(esi, _tile_bits(code, source, esi))
    assert decoder.try_solve() is None
    (status,) = decoder.block_status()
    assert status.rank is None or status.rank <= k
    assert status.short >= 1
    # the group with the largest deficit is the one reported, and a new
    # row in a rank-deficient group clears its stale rank
    eliminated = [key for key in decoder._rank]
    for key in eliminated:
        assert decoder._rank[key] < k
    y_missing_3 = next(esi for esi in range(code.symbols_per_page,
                                            2 * code.symbols_per_page)
                       if esi % 3 == 2
                       and 3 not in code.tile_slots(esi).groups)
    decoder.add_symbol(y_missing_3, _tile_bits(code, source, y_missing_3))
    touched = set(code.tile_slots(y_missing_3).groups)
    assert all((0, g) not in decoder._rank for g in touched)


def test_a_symbol_of_the_wrong_width_is_an_integrity_failure():
    code = _mixed_code()
    decoder = fountain.Decoder(code)
    with pytest.raises(fountain.FountainIntegrityError, match="30"):
        decoder.add_symbol(2, np.zeros(20, np.uint8))
    payload = np.random.default_rng(36).integers(
        0, 256, 600, dtype=np.uint8).tobytes()
    _k_meta, _k_total, _code, certs, row = _mixed_volume(payload)
    from dataclasses import replace
    narrow = replace(certs[2], user_bits=certs[2].user_bits[:21])
    result = close.close_volume(certs + [narrow], row)
    assert result.status == "integrity_failure"
    assert "certified-symbol integrity failure" in (result.reason or "")


def test_the_count_gate_reads_the_fewest_rows_not_the_scarcest_by_deficit(
        monkeypatch):
    """After a failed elimination, a group with K rows and rank K-1 ties on
    deficit with a group holding K-1 rows; the status may name either, the
    gate must read the fewest rows (second review pass, design doc §10)."""
    code = _mixed_code()
    k = code.k_total
    source = _source(k, 40, 3)
    decoder = fountain.Decoder(code)
    withheld = {esi for esi in range(code.symbols_per_page)
                if esi % 3 == 0 and code.tile_slots(esi).source_rows[0] < 8}
    for esi in range(code.symbols_per_page):
        if esi % 3 != 2 and esi not in withheld:
            decoder.add_symbol(esi, _tile_bits(code, source, esi))
    for esi in range(2, 2 * code.symbols_per_page, 3):
        if len(decoder._items[(0, 0)]) >= k:
            break
        if 0 in code.tile_slots(esi).groups:
            decoder.add_symbol(esi, _tile_bits(code, source, esi))
    for esi in range(2, 2 * code.symbols_per_page, 3):
        if len(decoder._items[(0, 3)]) >= k - 1:
            break
        if (esi not in decoder._symbols
                and code.tile_slots(esi).groups == (1, 2, 3)):
            decoder.add_symbol(esi, _tile_bits(code, source, esi))
    rows = {g: len(decoder._items[(0, g)]) for g in range(4)}
    assert rows[0] >= k and rows[3] == k - 1
    monkeypatch.setattr(fountain, "_ge_solve_gf2",
                        lambda _rows, _vals, kb: (kb - 1, None))
    assert decoder.try_solve() is None
    (status,) = decoder.block_status()
    assert status.short == 1 and status.groups_open == 4
    assert status.min_rows == k - 1 < status.needed
    assert status.rows >= status.min_rows
    if status.rank is not None:
        assert status.rows >= k and status.rank == k - 1

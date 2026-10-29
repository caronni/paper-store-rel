"""The grouped round trip (R22; docs/CMY-DESIGN.md §11 G1,
docs/CMY-GENERATOR-PLAN.md W2a, W3) for every ruled cmy row at 10x10.

emit -> plane GT -> presence states -> label bits -> one hard-label LDPC
decode per stream -> certificates -> close -> the payload, byte-exact.
Uniform pairs also close through ``core.fountain.Decoder``; every row,
uneven pairs included, closes through holo3's grouped decoder
(``holo.receiver.format.close.close_volume``) over the receiver's OWN row
(``identity.resolve_format_ref``, its StreamFacts).  The core decoder
refuses a column-group code by design, which is why the print-edge row
needs holo3.  Where the two trees' rows agree field by field is the drift
lane's (test_h3_drift_format's grammar test over every ruled row).

Each row is emitted once, at its own dial — the largest percent at or
below the pair's any-one-stream ceiling, where the planner promises the
stream tier — with the payload filling the one page, so the dead-stream
twin (G2–G4) withholds a stream from a full page.

Plus the n = 2 slot map against the encoder (the n = 3 pattern of
test_column_groups): every source chunk of a pair's block in exactly one
slot, repair rows dense, every slot filled from its row.
"""
from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest

import holo.core.fountain as fnt
from holo.core import channel, color_tile, keystream
from holo.format import metadata, streamset
from holo.format.descriptor import FormatSpec
from holo.format.lattice import parse_format_id
from holo.gen.color_compose import _color_geometry
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes
from holo.receiver.data import Certificate
from holo.receiver.format.close import close_volume
from holo.receiver.format.identity import FormatRow

from _receive_free import certificate, gt_cell_states, holo3_row

RULED_ROWS = (
    "c3-cmy-r0850@10x10",
    "c2-cmy-r0700@10x10",
    "c2-cmy-r0700x0625@10x10",
    "c2-cmy-r0775x0700@10x10",
    "c2-cmy-r0850x0700@10x10",
    "c2-cmy-r0700-p300@10x10",
)
UNIFORM_ROWS = tuple(r for r in RULED_ROWS
                     if parse_format_id(r).column_groups.uniform)
# Design §2.2's death map: a dead toner merges its state into W and kills
# every label stream its state sets — Y (01) lo, M (10) hi, C (11) both.
DEAD_TONER_WITHHOLDS = {"Y": ("lo",), "M": ("hi",), "C": ("hi", "lo")}


def _ceiling(ref: str) -> Fraction:
    """The pair's any-one-stream ceiling, the number
    ``plan.pooled_plane_tier`` reads: 1/2 for a uniform pair, below it for
    an uneven one, whose heavy stream binds (design §3.2)."""
    return parse_format_id(ref).column_groups.any_plane_ceiling


def _dial(ref: str) -> float:
    """The row's own dial: the largest percent at or below its ceiling."""
    return math.floor(_ceiling(ref) * 100) / 100


def _payload(n_bytes: int) -> bytes:
    return bytes(i % 251 for i in range(n_bytes))


def _tile_user_bits(spec: FormatSpec, field: np.ndarray, counter: int
                    ) -> list[np.ndarray]:
    """One tile's states -> labels -> each stream's certified user bits."""
    page, ty, tx = spec.tile_address(counter)
    tile = field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64].reshape(-1)
    placed = tile[_color_geometry(spec)[0]]
    order = keystream.color_cell_permutation(
        spec.seed, counter, spec.payload_cells)
    sequential = np.empty_like(placed)
    sequential[order] = placed
    user_bits = []
    for aux, (stream, labels) in enumerate(
            zip(spec.stream_profiles, channel.cmy_state_labels(sequential),
                strict=True), start=1):
        outcome = color_tile.cmy8_decode_stream(
            np.where(labels == 1, 24.0, -24.0), stream.fec,
            keystream.cmy8_dither_bits(
                spec.seed, aux, counter, stream.fec.transmitted_bits))
        assert outcome.ok, (spec.display_id, counter, stream.stream_id)
        user_bits.append(outcome.certified_user_bits.astype(np.uint8))
    return user_bits


def _certificates(row: FormatRow, tiles: dict[int, list[np.ndarray]],
                  withheld: tuple[str, ...] = ()) -> list[Certificate]:
    """The generator's decoded tiles as certificates of the receiver's
    row, one per tile per StreamFact, none from the ``withheld`` streams."""
    return [certificate(row, counter, fact.stream_id, bits[0], bits[1:])
            for counter, by_stream in tiles.items()
            for fact, bits in zip(row.streams, by_stream, strict=True)
            if fact.stream_id not in withheld]


@pytest.fixture(scope="module")
def decoded(tmp_path_factory) -> dict[str, tuple]:
    """Per row, emitted once at its own dial with the payload filling the
    page: the plan, the payload and every tile's decoded user bits, by
    counter."""
    out = {}
    base = tmp_path_factory.mktemp("cmy-round-trip")
    for ref in RULED_ROWS:
        spec = parse_format_id(ref)
        q = _dial(ref)
        payload = _payload(max_payload_bytes(spec, q, 1))
        vol = emit_volume(spec, payload, q, base / ref, paper="A4-4mm")
        assert vol.plan.n_pages == 1
        field = gt_cell_states(vol.pages[0].gt_path, spec)
        out[ref] = (vol.plan, payload, {
            counter: _tile_user_bits(spec, field, counter)
            for counter in range(spec.tiles_per_page)})
    return out


@pytest.mark.parametrize("ref", RULED_ROWS)
def test_every_ruled_row_closes_through_holo3s_own_row(
        ref: str, decoded) -> None:
    plan, payload, tiles = decoded[ref]
    row = holo3_row(ref)
    certs = _certificates(row, tiles)
    assert len(certs) == 2 * row.tiles_per_page
    result = close_volume(certs, row)
    assert (result.status, result.reason) == ("verified", None)
    assert result.payload == payload
    assert result.k_total == plan.k_total == 2 * plan.k_meta


@pytest.mark.parametrize(
    "ref", RULED_ROWS,
    ids=lambda ref: f"{ref}-q{_dial(ref)}-ceiling{_ceiling(ref)}")
def test_a_dead_y_or_m_closes_and_a_dead_c_stays_open(
        ref: str, decoded) -> None:
    """G2–G4 (design §2.2, §2.6) at the row's own dial, every page
    present: a dead Y leaves only hi certificates, a dead M only lo, and
    each closes byte-exact; a dead C takes both streams (and the words'
    '1'), so nothing reaches the close and it stays open."""
    plan, payload, tiles = decoded[ref]
    assert plan.plane_tier == "guaranteed"
    row = holo3_row(ref)
    for toner, withheld in DEAD_TONER_WITHHOLDS.items():
        certs = _certificates(row, tiles, withheld)
        assert len(certs) == (2 - len(withheld)) * row.tiles_per_page
        result = close_volume(certs, row)
        if toner == "C":
            assert (result.status, result.reason, result.payload) == (
                "open", "metadata incomplete", None)
        else:
            assert (result.status, result.reason) == ("verified", None), toner
            assert result.payload == payload, toner
            assert result.k_total == plan.k_total


@pytest.mark.parametrize("ref", RULED_ROWS)
def test_a_corrupted_certificate_set_does_not_verify(ref: str, decoded) -> None:
    """The negative arm (the W2a refuter): a set with every tile's first user bit flipped cannot pass as
    verified, whichever tiles the pooled fountain makes systematic.  That bit is the METADATA bit, so the
    metadata gate rejects the set first ("inconsistent at equation index 24", the W3 refuter's reading);
    a set that passes the gate still meets the envelope sha as the close's final verdict."""
    _, payload, tiles = decoded[ref]
    row = holo3_row(ref)
    certs = []
    for counter, by_stream in tiles.items():
        for fact, bits in zip(row.streams, by_stream, strict=True):
            bad = bits.copy()
            bad[0] ^= 1
            certs.append(certificate(row, counter, fact.stream_id, bad[0], bad[1:]))
    result = close_volume(certs, row)
    assert result.status != "verified"
    assert result.payload != payload


@pytest.mark.parametrize("ref", RULED_ROWS)
def test_the_decoded_symbols_are_the_pooled_fountains_own(
        ref: str, decoded) -> None:
    """The page carried exactly what the one fountain encodes at
    esi = counter * 2 + stream, each stream cut to its width, behind the
    stream's own metadata equation."""
    spec = parse_format_id(ref)
    plan, payload, tiles = decoded[ref]
    layout = streamset.StreamSet(tuple(
        (s.stream_id, s.symbol_bits) for s in spec.stream_profiles))
    k_meta, source = streamset.pooled_pack_payload(payload, layout)
    assert k_meta == plan.k_meta
    code = fnt.VolumeCode(plan.k_total, spec.symbol_bits, spec.seed,
                          tiles_per_page=spec.tiles_per_page, n_streams=2,
                          groups=spec.column_groups)
    counters = np.arange(spec.tiles_per_page, dtype=np.int64)
    word = metadata.encode_metadata(0, k_meta)
    for index, stream in enumerate(spec.stream_profiles):
        esis = counters * 2 + index
        symbols = code.encode_symbols(source, esis)[:, :stream.symbol_bits]
        for counter, esi, symbol in zip(counters, esis, symbols):
            bits = tiles[int(counter)][index]
            assert bits[0] == metadata.tile_bit(
                word, int(esi), max_index=metadata.max_equation_index(2))
            np.testing.assert_array_equal(bits[1:], symbol)


@pytest.mark.parametrize("ref", UNIFORM_ROWS)
def test_uniform_rows_close_through_the_core_decoder(ref: str,
                                                     decoded) -> None:
    spec = parse_format_id(ref)
    plan, payload, tiles = decoded[ref]
    received = [(metadata.equation_index(counter, index, 2), bits)
                for counter, by_stream in tiles.items()
                for index, bits in enumerate(by_stream)]
    meta = metadata.decode_metadata(
        [(esi, int(bits[0])) for esi, bits in received],
        max_index=metadata.max_equation_index(2))
    assert meta.ok and meta.k == plan.k_meta
    decoder = fnt.Decoder(fnt.VolumeCode(
        2 * meta.k, spec.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page, n_streams=2,
        groups=spec.column_groups))
    for esi, bits in received:
        decoder.add_symbol(esi, bits[1:])
    solved = decoder.try_solve()
    assert solved is not None
    layout = streamset.StreamSet(tuple(
        (s.stream_id, s.symbol_bits) for s in spec.stream_profiles))
    assert streamset.pooled_unwrap_solved(solved, layout, meta.k) == payload


@pytest.mark.parametrize("ref", sorted(set(RULED_ROWS) - set(UNIFORM_ROWS)))
def test_the_core_decoder_refuses_an_uneven_pair(ref: str) -> None:
    spec = parse_format_id(ref)
    code = fnt.VolumeCode(2 * 30, spec.symbol_bits, spec.seed,
                          tiles_per_page=spec.tiles_per_page, n_streams=2,
                          groups=spec.column_groups)
    with pytest.raises(ValueError, match="decoded by holo3"):
        fnt.Decoder(code)


# ------------------------------------------------- the n = 2 slot oracle

# k_meta 60 at 100 tiles/page: the one block's 120 * Z source chunks run
# past page 0's hi tiles into its lo tiles, so both streams hold
# systematic and repair tiles (and an uneven pair's lo a straddler).
ORACLE_K_META = 60


def _oracle_code(ref: str) -> fnt.VolumeCode:
    spec = parse_format_id(ref)
    return fnt.VolumeCode(2 * ORACLE_K_META, spec.symbol_bits, spec.seed,
                          tiles_per_page=spec.tiles_per_page, n_streams=2,
                          groups=spec.column_groups)


@pytest.mark.parametrize("ref", RULED_ROWS)
def test_every_source_chunk_of_a_pair_sits_in_exactly_one_slot(
        ref: str) -> None:
    code = _oracle_code(ref)
    groups = code.groups
    kb, z = code.k_per_block[0], groups.n_groups
    assert code.n_blocks == 1
    seen: dict[tuple[int, int], int] = {}
    repair_rows = []
    lo_systematic = straddlers = 0
    for esi in range(2 * code.symbols_per_page):
        tile = code.tile_slots(esi)
        widths = tuple(hi - lo for lo, hi in zip(tile.edges, tile.edges[1:]))
        assert widths == tuple(groups.width(g) for g in tile.groups)
        assert tile.edges[-1] <= groups.widths[esi % 2]
        if tile.repair_row is None:
            for g, r in zip(tile.groups, tile.source_rows):
                assert r >= 0 and (r, g) not in seen
                seen[(r, g)] = esi
            lo_systematic += esi % 2
            straddlers += len(tile.groups) < groups.carried[esi % 2]
        else:
            assert all(r == -1 for r in tile.source_rows)
            repair_rows.append(tile.repair_row)
    assert len(seen) == kb * z
    assert sorted(repair_rows) == list(range(kb, kb + len(repair_rows)))
    assert lo_systematic > 0
    assert straddlers == (0 if groups.uniform else 1)


@pytest.mark.parametrize("ref", RULED_ROWS)
def test_encode_symbols_fills_every_pair_slot_from_its_row(ref: str) -> None:
    code = _oracle_code(ref)
    spec = parse_format_id(ref)
    k, s = code.k_total, code.s_bits
    source = fnt.pack_source(
        np.random.default_rng(20261011).bytes(k * s // 8), k, s)
    full = fnt.unpack_rows(source, s)
    esis = np.arange(2 * code.symbols_per_page, dtype=np.int64)
    out = code.encode_symbols(source, esis)
    n_repair = 0
    for esi in esis:
        tile = code.tile_slots(int(esi))
        if tile.repair_row is None:
            rows = {r: full[r] for r in tile.source_rows}
        else:
            coeff = fnt.fountain_rows_bits(spec.seed, 0, [tile.repair_row],
                                           k)[0]
            selected = np.flatnonzero(coeff)
            rows = {-1: (np.bitwise_xor.reduce(full[selected], axis=0)
                         if selected.size else np.zeros(s, np.uint8))}
            n_repair += 1
        for g, r, lo, hi in zip(tile.groups, tile.source_rows,
                                tile.edges, tile.edges[1:]):
            np.testing.assert_array_equal(
                out[esi, lo:hi],
                rows[r][code.groups.bounds[g]:code.groups.bounds[g + 1]])
        assert not out[esi, tile.edges[-1]:].any()
    assert n_repair > 0

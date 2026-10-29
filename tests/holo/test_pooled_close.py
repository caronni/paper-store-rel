"""P4 pins for the pooled -v1 close (CMY8-POOLING-PLAN).

Gate E re-home: the vehicle is `holo.receiver.format.close` — the production
close — fed certificates minted by `holo.format.streamset` and
`holo.core.fountain`, so the generator and the close are cross-checked
without a receiver anywhere.

One stream-mixed decoder at esi = counter*n + stream, per-stream
metadata equations at close, pooled block space (stream_id=None rows;
counts keyed ("pooled", block)), the canonical unwrap, conflict
fatality — and the close-level dead-plane companion on the REAL row,
with the -v0 per-stream negative control staying OPEN on stream Y.
The compose-level end-to-end dead-plane GATE is
test_pooled_dead_plane_gate, on the slow lane since 2026-09-20 — so
the companion below is what every commit gets.
"""
from __future__ import annotations

import numpy as np

from holo.core import fountain
from holo.format import metadata, streamset
from holo.format.resolve import resolve_format_ref
from holo.receiver.format import close

from _receive_free import certificate, holo3_row

V1_REF = "L:c3-cmy8-p120-v1@2240x1536"
V0_REF = "L:c3-cmy8-p120-v0@2240x1536"
PAYLOAD = bytes((7 * i + 3) % 251 for i in range(22_000))


def _layout(spec) -> streamset.StreamSet:
    return streamset.StreamSet(tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in spec.stream_profiles))


def _pooled_certs(ref, payload, counters, streams=(0, 1, 2)):
    """Generator-side pooled certificates for the given tiles/streams."""
    spec = resolve_format_ref(ref)
    row = holo3_row(ref)
    k_meta, source = streamset.pooled_pack_payload(payload, _layout(spec))
    code = fountain.VolumeCode(
        3 * k_meta, spec.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page, n_streams=3)
    word = metadata.encode_metadata(0, k_meta)
    bound = metadata.max_equation_index(3)
    esis = np.asarray([
        3 * counter + stream
        for counter in counters for stream in streams], dtype=np.int64)
    symbols = code.encode_symbols(source, esis)
    certs = []
    for index, esi in enumerate(esis):
        counter, stream = divmod(int(esi), 3)
        certs.append(certificate(
            row, counter, spec.stream_ids[stream],
            metadata.tile_bit(
                word, metadata.equation_index(counter, stream, 3),
                max_index=bound),
            symbols[index]))
    return k_meta, certs


def _v0_certs(ref, payload, counters, stream_ids=("C", "M", "Y")):
    """-v0 per-stream certificates (the negative-control generator)."""
    spec = resolve_format_ref(ref)
    row = holo3_row(ref)
    packed = streamset.pack_payload(payload, _layout(spec))
    sources = {stream.stream_id: stream.rows for stream in packed.streams}
    word = metadata.encode_metadata(0, packed.k_total)
    certs = []
    counters = np.asarray(sorted(counters), dtype=np.int64)
    bits = metadata.tile_bits(word, counters)
    for profile in spec.stream_profiles:
        if profile.stream_id not in stream_ids:
            continue
        code = fountain.VolumeCode(
            packed.k_total, profile.symbol_bits, spec.seed,
            tiles_per_page=spec.tiles_per_page,
            stream_id=profile.stream_id,
            fountain_aux=profile.fountain_aux)
        symbols = code.encode_symbols(sources[profile.stream_id], counters)
        for index, counter in enumerate(counters):
            certs.append(certificate(row, int(counter), profile.stream_id,
                                     int(bits[index]), symbols[index]))
    return packed.k_total, certs


def test_pooled_close_verified_byte_exact():
    row = holo3_row(V1_REF)
    k_meta, certs = _pooled_certs(V1_REF, PAYLOAD, range(40))
    assert k_meta == 29                       # 3*29 = 87 source symbols
    result = close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == PAYLOAD
    assert result.k_total == 3 * k_meta
    assert result.metadata_version == 0
    assert result.symbols_used == 120
    assert all(block.stream_id is None for block in result.blocks)


def test_pooled_dead_plane_closes_and_v0_control_stays_open():
    """The close-level dead-plane companion (design §1): Y erased
    everywhere. Pooled at ~q0.5 fill closes byte-exact; the -v0
    per-stream construction over the SAME payload and tiles stays OPEN
    with stream Y named."""
    tiles = range(60)                          # 120 C/M symbols vs K=87
    k_meta, certs = _pooled_certs(V1_REF, PAYLOAD, tiles, streams=(0, 1))
    assert all(cert.stream_id in ("C", "M") for cert in certs)
    result = close.close_volume(certs, holo3_row(V1_REF))
    assert result.status == "verified"
    assert result.payload == PAYLOAD

    k_common, control = _v0_certs(V0_REF, PAYLOAD, tiles,
                                  stream_ids=("C", "M"))
    assert k_common == k_meta                  # identical canonical K
    open_result = close.close_volume(control, holo3_row(V0_REF))
    assert open_result.status == "open"
    assert "('Y',)" in (open_result.reason or "")


def test_pooled_count_status_and_metadata_progress():
    row = holo3_row(V1_REF)
    k_meta, certs = _pooled_certs(V1_REF, PAYLOAD, range(40))
    ready, counts = close.close_count_status(certs, row)
    assert ready and counts == {("pooled", 0): 120}
    short_ready, short_counts = close.close_count_status(certs[:80], row)
    assert not short_ready                     # 80 < K_b = 87
    assert short_counts == {("pooled", 0): 80}
    _ready, k_total, blocks = close.close_count_progress(certs, row)
    assert k_total == 3 * k_meta
    assert len(blocks) == 1
    block = blocks[0]
    assert (block.stream_id, block.needed, block.have) == (None, 87, 120)


def test_pooled_count_gate_skips_the_decoder_build():
    """D8 on a pooled row: an unchanged-count re-consult provably
    cannot gain rank, so the close must know it has nothing new to try.
    The snapshot therefore has to key the ONE pooled block space the
    counts themselves use — a per-stream key never intersects, and the
    skip is dead."""
    row = holo3_row(V1_REF)
    # 20 tiles: 60 pooled symbols < K_b 87, but 60 equations >= 48
    _k_meta, certs = _pooled_certs(V1_REF, PAYLOAD, range(20))
    progress = close.CloseProgress(row)
    progress.absorb(dict(enumerate(certs)))
    assert progress.close_is_new()
    first = progress.close()
    assert first.status == "open"
    assert not progress.close_is_new()         # unchanged counts: skipped
    progress.absorb(dict(enumerate(certs)))    # the same certificates again
    assert not progress.close_is_new()


def test_pooled_conflicting_symbol_is_integrity_fatal():
    row = holo3_row(V1_REF)
    _k_meta, certs = _pooled_certs(V1_REF, PAYLOAD, range(40))
    twin = certs[5]
    flipped = np.asarray(twin.user_bits).copy()
    flipped[1] ^= 1
    certs.append(certificate(
        row, twin.page * row.tiles_per_page
        + twin.ty * row.tiles_yx[1] + twin.tx,
        twin.stream_id, int(flipped[0]), flipped[1:]))
    result = close.close_volume(certs, row)
    assert result.status == "integrity_failure"
    assert "conflicting certified values" in (result.reason or "")


def test_pooled_metadata_short_of_trust_floor_stays_open():
    row = holo3_row(V1_REF)
    _k_meta, certs = _pooled_certs(V1_REF, PAYLOAD, range(15))  # 45 < 48
    result = close.close_volume(certs, row)
    assert result.status == "open"
    assert result.k_total is None
    assert "metadata incomplete" in (result.reason or "")


def test_pooled_fragment_crop_at_the_promise_boundary():
    """Probabilistic-tier sanity (plan P5): one seeded contiguous
    counter-band crop of a three-page pooled volume closes just above
    the boundary and stays open well below it."""
    row = holo3_row(V1_REF)
    payload = bytes((11 * i + 5) % 251 for i in range(500_000))
    tiles_per_page = row.tiles_per_page
    n_tiles = 3 * tiles_per_page
    k_meta, certs = _pooled_certs(V1_REF, payload, range(n_tiles))
    assert 3 * k_meta == 1_917                  # multi-symbol, one block

    def band(width: int) -> list:
        start = 371                             # seeded, arbitrary interior
        keep = {counter % n_tiles
                for counter in range(start, start + width)}
        return [cert for cert in certs
                if (cert.page * tiles_per_page + cert.ty * row.tiles_yx[1]
                    + cert.tx) in keep]

    # contiguous band keeping fraction f of the volume's tiles
    result = close.close_volume(band(int(0.32 * n_tiles)), row)
    assert result.status == "verified"          # f*3N ~ 2419 > K + r
    assert result.payload == payload
    starved = close.close_volume(band(int(0.20 * n_tiles)), row)
    assert starved.status == "open"             # f*3N ~ 1512 < K

"""P4 pins for the pooled -v1 close (CMY8-POOLING-PLAN).

One stream-mixed decoder at esi = counter*n + stream, per-stream
metadata equations at close, pooled block space (stream_id=None rows;
counts keyed ("pooled", block)), the canonical unwrap, conflict
fatality — and the close-level dead-plane companion on the REAL row,
with the -v0 per-stream negative control staying OPEN on stream Y.
The compose-level end-to-end dead-plane GATE is P5.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo.core import fountain
from holo.format import metadata, streamset
from holo.format.registry import get_format_row
from holo.receive import production_close
from holo.receive.close_progress import CloseBlockProgress
from holo.receive.fountain_close import (
    CertifiedStreamSymbol,
    CloseResult,
    close_count_status,
    close_volume,
    metadata_progress,
)
from holo.receive.records import certificate_record_from_user_bits
from holo.receive.runtime import CloseContext
from holo.receive.types import CloseRecord

V1_ROW = "c3-cmy8-p120-v1@2240x1536"
V0_ROW = "c3-cmy8-p120-v0@2240x1536"
PAYLOAD = bytes((7 * i + 3) % 251 for i in range(22_000))


def _layout(spec) -> streamset.StreamSet:
    return streamset.StreamSet(tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in spec.stream_profiles))


def _pooled_certs(spec, payload, counters, streams=(0, 1, 2)):
    """Generator-side pooled certificates for the given tiles/streams."""
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
    for row, esi in enumerate(esis):
        counter, stream = divmod(int(esi), 3)
        page, ty, tx = spec.tile_address(counter)
        certs.append(CertifiedStreamSymbol(
            counter, page, ty, tx, spec.stream_ids[stream],
            symbols[row],
            metadata.tile_bit(
                word,
                metadata.equation_index(counter, stream, 3),
                max_index=bound),
        ))
    return k_meta, certs


def _v0_certs(spec, payload, counters, stream_ids=("C", "M", "Y")):
    """-v0 per-stream certificates (the negative-control generator)."""
    packed = streamset.pack_payload(payload, _layout(spec))
    sources = {row.stream_id: row.rows for row in packed.streams}
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
        symbols = code.encode_symbols(
            sources[profile.stream_id], counters)
        for row, counter in enumerate(counters):
            page, ty, tx = spec.tile_address(int(counter))
            certs.append(CertifiedStreamSymbol(
                int(counter), page, ty, tx, profile.stream_id,
                symbols[row], int(bits[row])))
    return packed.k_total, certs


def test_pooled_close_verified_byte_exact():
    spec = get_format_row(V1_ROW)
    k_meta, certs = _pooled_certs(spec, PAYLOAD, range(40))
    assert k_meta == 29                       # 3*29 = 87 source symbols
    result = close_volume(certs, spec)
    assert result.status == "verified"
    assert result.payload == PAYLOAD
    assert result.k_total == 3 * k_meta
    assert result.metadata_version == 0
    assert result.symbols_used == 120
    assert result.surplus_inconsistencies == ()
    assert all(block.stream_id is None for block in result.blocks)
    assert result.diagnostics["decoded_k_meta"] == k_meta
    assert result.diagnostics["decoded_k"] == k_meta   # the 18-bit field


def test_pooled_dead_plane_closes_and_v0_control_stays_open():
    """The close-level dead-plane companion (design §1): Y erased
    everywhere. Pooled at ~q0.5 fill closes byte-exact; the -v0
    per-stream construction over the SAME payload and tiles stays OPEN
    with stream Y named."""
    spec_v1 = get_format_row(V1_ROW)
    tiles = range(60)                          # 120 C/M symbols vs K=87
    k_meta, certs = _pooled_certs(
        spec_v1, PAYLOAD, tiles, streams=(0, 1))
    assert all(cert.stream_id in ("C", "M") for cert in certs)
    result = close_volume(certs, spec_v1)
    assert result.status == "verified"
    assert result.payload == PAYLOAD

    spec_v0 = get_format_row(V0_ROW)
    k_common, control = _v0_certs(
        spec_v0, PAYLOAD, tiles, stream_ids=("C", "M"))
    assert k_common == k_meta                  # identical canonical K
    open_result = close_volume(control, spec_v0)
    assert open_result.status == "open"
    assert "('Y',)" in (open_result.reason or "")


def test_pooled_count_status_and_metadata_progress():
    spec = get_format_row(V1_ROW)
    k_meta, certs = _pooled_certs(spec, PAYLOAD, range(40))
    ready, counts = close_count_status(certs, spec)
    assert ready and counts == {("pooled", 0): 120}
    short_ready, short_counts = close_count_status(certs[:80], spec)
    assert not short_ready                     # 80 < K_b = 87
    assert short_counts == {("pooled", 0): 80}
    progress = metadata_progress(certs, spec)
    assert progress.count_only
    assert progress.k_total == 3 * k_meta
    assert len(progress.blocks) == 1
    block = progress.blocks[0]
    assert (block.stream_id, block.needed, block.have) == (None, 87, 120)


def test_pooled_count_gate_skips_the_decoder_build(monkeypatch):
    """D8 on a pooled row: an unchanged-count re-consult provably
    cannot gain rank, so it must NOT rebuild the decoder.  The count
    baseline therefore has to key the ONE pooled block space the counts
    themselves use ("pooled", block) — a per-stream key never
    intersects, and the skip is dead."""
    spec = get_format_row(V1_ROW)
    k_meta, certs = _pooled_certs(spec, PAYLOAD, range(40))
    records = tuple(
        certificate_record_from_user_bits(
            spec, page=cert.page, tile_yx=(cert.ty, cert.tx),
            stream_id=cert.stream_id,
            user_bits=np.concatenate((
                [cert.metadata_bit],
                np.asarray(cert.symbol, dtype=np.uint8))),
            origin_attempt_id=f"pooled-d8/{cert.counter}/{cert.stream_id}",
        )
        for cert in certs)
    state = SimpleNamespace(certificates=records, close=CloseRecord())
    # count-ready (120 distinct pooled ESIs >= K_b = 87) but rank-open
    stub = CloseResult(
        status="open", payload=None, k_total=3 * k_meta,
        blocks=(CloseBlockProgress(0, 3 * k_meta, 120, 80, False),),
        symbols_used=120, reason="stub open",
        diagnostics={"metadata_rank": 24, "metadata_rank_shortfall": 0,
                     "metadata_check_shortfall": 0,
                     "metadata_inconsistent": False,
                     "n_unique_metadata_counters": 120})
    builds = []

    def counting_close(close_certs, close_spec):
        builds.append(len(tuple(close_certs)))
        return stub

    monkeypatch.setattr(production_close, "close_volume", counting_close)
    close = production_close.ProductionClose()
    first = close.process(CloseContext(spec, state))
    assert first.record == CloseRecord()
    assert builds == [120]                     # first consult builds
    skipped = close.process(CloseContext(spec, state))
    assert builds == [120]                     # unchanged counts: skipped
    assert skipped.payload is None
    assert skipped.diagnostic_progress().count_only is True


def test_pooled_conflicting_symbol_is_integrity_fatal():
    spec = get_format_row(V1_ROW)
    _k_meta, certs = _pooled_certs(spec, PAYLOAD, range(40))
    twin = certs[5]
    flipped = np.asarray(twin.symbol).copy()
    flipped[0] ^= 1
    certs.append(CertifiedStreamSymbol(
        twin.counter, twin.page, twin.ty, twin.tx, twin.stream_id,
        flipped, twin.metadata_bit))
    result = close_volume(certs, spec)
    assert result.status == "integrity_failure"
    assert "conflicting certified values" in (result.reason or "")


def test_pooled_metadata_short_of_trust_floor_stays_open():
    spec = get_format_row(V1_ROW)
    _k_meta, certs = _pooled_certs(spec, PAYLOAD, range(15))  # 45 < 48
    result = close_volume(certs, spec)
    assert result.status == "open"
    assert result.k_total is None
    assert "metadata incomplete" in (result.reason or "")


def test_pooled_fragment_crop_at_the_promise_boundary():
    """Probabilistic-tier sanity (plan P5): one seeded contiguous
    counter-band crop of a three-page pooled volume closes just above
    the boundary and stays open well below it."""
    spec = get_format_row(V1_ROW)
    payload = bytes((11 * i + 5) % 251 for i in range(500_000))
    tiles_per_page = spec.tiles_per_page
    n_tiles = 3 * tiles_per_page
    k_meta, certs = _pooled_certs(spec, payload, range(n_tiles))
    k_total = 3 * k_meta
    assert k_total == 1_917                     # multi-symbol, one block
    # contiguous band keeping fraction f of the volume's tiles
    keep = int(0.32 * n_tiles)                  # f*3N symbols ~ 2419 > K+r
    start = 371                                 # seeded, arbitrary interior
    band = {
        counter % n_tiles
        for counter in range(start, start + keep)}
    kept = [cert for cert in certs if cert.counter in band]
    result = close_volume(kept, spec)
    assert result.status == "verified"
    assert result.payload == payload
    thin = int(0.20 * n_tiles)                  # f*3N ~ 1512 < K
    starved = {
        counter % n_tiles
        for counter in range(start, start + thin)}
    open_result = close_volume(
        [cert for cert in certs if cert.counter in starved], spec)
    assert open_result.status == "open"

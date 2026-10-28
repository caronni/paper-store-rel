"""The carried verified close, inside the firewall (H2b).

Equivalence with ``src/holo`` is pinned by the oracles in repo-root
``tests/holo2_oracles/test_oracle_close.py``; these tests own the holo2-side
behaviour that must hold with no holo import in sight: DESIGN L9's
verified stop (canonical envelope + SHA-256 + minimal K + zero padding,
total or nothing), L5's fatal certificate conflicts, and the count gate's
"advice, never a stop" contract.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo2.format import envelope, fountain, metadata, streamset
from holo2.format.close_spec import CloseSpec, CloseStreamProfile
from holo2.format.family import Family
from holo2.format.fountain_close import (CertifiedStreamSymbol,
                                         MetadataIntegrityError,
                                         close_count_ready, close_count_status,
                                         close_record_from_result,
                                         close_volume,
                                         metadata_from_certificates)
from holo2.core.records import CloseStatus

# The c3-r0550 K row at its default geometry, stated as data (holo2 has no
# format registry: H2c supplies this from the session's format row).
SEED = b"holo/v1/c3-r0550/2240x1536"
TILES_YX = (35, 24)
SYMBOL_BITS = 2107
K_SPEC = CloseSpec(
    codec_id="k-v1", seed=SEED, tiles_yx=TILES_YX,
    stream_profiles=(CloseStreamProfile("main", SYMBOL_BITS),),
    spec_id="c3-r0550@2240x1536")

# The CMY8 row's three INDEPENDENT streams (same geometry family) —
# i.e. the UNPOOLED -v0 outer code. C2 (2026-08-22, RULINGS G8) drops
# the two cmy8-v0 identities from holo2's legacy catalogue, so this
# fixture deliberately names a sheet holo2 can no longer resolve: what
# it exercises is the carried close's unpooled multi-stream path, which
# is still live code, and hand-building the spec is how a unit fixture
# reaches a path no identity leads to any more.
CMY8_SEED = b"holo/v1/c2-cmy8-p120-v0/3328x2304"
CMY8_SPEC = CloseSpec(
    codec_id="cmy8-presence-p120-v0", seed=CMY8_SEED, tiles_yx=(52, 36),
    stream_profiles=(
        CloseStreamProfile("C", 2087, 1),
        CloseStreamProfile("M", 2087, 2),
        CloseStreamProfile("Y", 2087, 3),
    ),
    spec_id="c2-cmy8-p120-v0@3328x2304",
    codec_family=Family.CMY8)

N_CERTS = 100


def _payload(tag: bytes, blocks: int) -> bytes:
    return hashlib.sha256(tag).digest() * blocks


def _certificates(spec: CloseSpec, stream_symbols, k_total: int,
                  n: int = N_CERTS) -> tuple[CertifiedStreamSymbol, ...]:
    """One certified equation per (counter, stream) from encoder truth."""
    _tiles_y, tiles_x = spec.tiles_yx
    counters = np.arange(n, dtype=np.int64)
    bits = metadata.tile_bits(
        metadata.encode_metadata(0, k_total), counters)
    out = []
    for stream_id, symbols in stream_symbols:
        for index, counter in enumerate(counters):
            page, rem = divmod(int(counter), spec.tiles_per_page)
            ty, tx = divmod(rem, tiles_x)
            out.append(CertifiedStreamSymbol(
                counter=int(counter), page=page, ty=ty, tx=tx,
                stream_id=stream_id, symbol=symbols[index],
                metadata_bit=int(bits[index])))
    return tuple(out)


@pytest.fixture(scope="module")
def k_volume():
    payload = _payload(b"holo2-close-k", 500)
    k_total = envelope.source_symbol_count(len(payload), SYMBOL_BITS)
    assert k_total == 61
    source = fountain.pack_source(
        envelope.wrap(payload), k_total, SYMBOL_BITS)
    code = fountain.VolumeCode(
        k_total, SYMBOL_BITS, SEED, tiles_per_page=K_SPEC.tiles_per_page)
    symbols = code.encode_symbols(
        source, np.arange(N_CERTS, dtype=np.int64))
    certs = _certificates(K_SPEC, (("main", symbols),), k_total)
    return payload, k_total, symbols, certs


@pytest.fixture(scope="module")
def cmy8_volume():
    payload = _payload(b"holo2-close-cmy8", 900)
    layout = streamset.StreamSet(tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in CMY8_SPEC.stream_profiles))
    packed = streamset.pack_payload(payload, layout)
    counters = np.arange(N_CERTS, dtype=np.int64)
    stream_symbols = []
    for source in packed.streams:
        profile = CMY8_SPEC.stream_profile(source.stream_id)
        code = fountain.VolumeCode(
            packed.k_total, profile.symbol_bits, CMY8_SEED,
            tiles_per_page=CMY8_SPEC.tiles_per_page,
            stream_id=profile.stream_id,
            fountain_aux=profile.fountain_aux)
        stream_symbols.append(
            (source.stream_id, code.encode_symbols(source.rows, counters)))
    certs = _certificates(CMY8_SPEC, stream_symbols, packed.k_total)
    return payload, packed.k_total, certs


def test_verified_stop_recovers_the_payload_byte_exact(k_volume) -> None:
    payload, k_total, _symbols, certs = k_volume
    result = close_volume(certs, K_SPEC)
    assert result.verified and result.payload == payload
    assert result.k_total == k_total and result.symbols_used == N_CERTS
    assert [row.rank_shortfall for row in result.blocks] == [0]
    assert result.surplus_inconsistencies == ()


def test_repair_rows_carry_the_volume(k_volume) -> None:
    """Dropping the first 20 systematic ESIs forces the GE path."""
    payload, _k, _symbols, certs = k_volume
    result = close_volume(certs[20:], K_SPEC)
    assert result.verified and result.payload == payload


def test_metadata_refuses_below_the_48_counter_floor(k_volume) -> None:
    _payload_bytes, k_total, _symbols, certs = k_volume
    version, k, diag = metadata_from_certificates(certs[:47], K_SPEC)
    assert version is None and k is None
    assert diag["metadata_rank"] == metadata.METADATA_BITS
    assert diag["metadata_check_shortfall"] == 1
    assert diag["state"] == "incomplete"
    assert metadata_from_certificates(certs[:48], K_SPEC)[1] == k_total


def test_rank_shortfall_is_open_not_partial(k_volume) -> None:
    _payload_bytes, k_total, _symbols, certs = k_volume
    result = close_volume(certs[:55], K_SPEC)
    assert result.status == "open" and result.payload is None
    assert result.k_total == k_total
    assert result.blocks[0].rank == 55 and result.blocks[0].needed == 61
    assert "6 additional symbols" in (result.reason or "")


def test_wrong_bits_fail_the_digest_totally(k_volume) -> None:
    """A flipped systematic symbol: integrity failure, no bytes handed on."""
    _payload_bytes, _k, symbols, certs = k_volume
    broken = symbols[0].copy()
    broken[0] ^= np.uint8(1)
    tampered = CertifiedStreamSymbol(
        counter=0, page=0, ty=0, tx=0, stream_id="main", symbol=broken,
        metadata_bit=certs[0].metadata_bit)
    result = close_volume((tampered,) + certs[1:61], K_SPEC)
    assert result.status == "integrity_failure"
    assert result.payload is None and not result.verified
    assert "SHA-256" in (result.reason or "")


def test_conflicting_certified_values_are_fatal(k_volume) -> None:
    _payload_bytes, _k, symbols, certs = k_volume
    conflicting = CertifiedStreamSymbol(
        counter=0, page=0, ty=0, tx=0, stream_id="main",
        symbol=symbols[0] ^ np.uint8(1),
        metadata_bit=certs[0].metadata_bit)
    result = close_volume(certs + (conflicting,), K_SPEC)
    assert result.status == "integrity_failure"
    assert result.diagnostics["phase"] == "fountain"


def test_disagreeing_metadata_bits_are_fatal(k_volume) -> None:
    _payload_bytes, _k, _symbols, certs = k_volume
    twin = CertifiedStreamSymbol(
        counter=0, page=0, ty=0, tx=0, stream_id="main",
        symbol=certs[0].symbol, metadata_bit=1 - certs[0].metadata_bit)
    with pytest.raises(MetadataIntegrityError):
        metadata_from_certificates(certs + (twin,), K_SPEC)
    assert close_volume(certs + (twin,), K_SPEC).status \
        == "integrity_failure"


def test_unsupported_metadata_version_is_terminal(k_volume) -> None:
    _payload_bytes, k_total, symbols, _certs = k_volume
    counters = np.arange(N_CERTS, dtype=np.int64)
    bits = metadata.tile_bits(metadata.encode_metadata(1, k_total), counters)
    _tiles_y, tiles_x = TILES_YX
    certs = tuple(
        CertifiedStreamSymbol(
            counter=int(counter), page=0,
            ty=int(counter) // tiles_x, tx=int(counter) % tiles_x,
            stream_id="main", symbol=symbols[index],
            metadata_bit=int(bits[index]))
        for index, counter in enumerate(counters))
    result = close_volume(certs, K_SPEC)
    assert result.status == "unsupported" and result.metadata_version == 1
    assert result.payload is None


def test_count_gate_is_advice_not_a_stop(k_volume) -> None:
    _payload_bytes, k_total, _symbols, certs = k_volume
    assert close_count_ready(certs[:47], K_SPEC) is False   # incomplete
    ready, counts = close_count_status(certs[:60], K_SPEC)
    assert ready is False and counts == {("main", 0): 60}
    ready, counts = close_count_status(certs[:61], K_SPEC)
    assert ready is True and counts == {("main", 0): 61}
    # Ready by count says nothing about rank: a duplicate-heavy set can be
    # count-ready and still fail to solve, so the close stays the authority.
    assert close_volume(certs[:61], K_SPEC).verified
    assert k_total == 61


def test_close_records_carry_the_durable_status(k_volume) -> None:
    payload, _k, _symbols, certs = k_volume
    verified = close_record_from_result(close_volume(certs, K_SPEC))
    assert verified.status is CloseStatus.VERIFIED and verified.is_terminal
    assert verified.payload_sha256 == hashlib.sha256(payload).hexdigest()
    opened = close_record_from_result(close_volume(certs[:10], K_SPEC))
    assert opened.status is CloseStatus.OPEN and not opened.is_terminal
    assert opened.payload_sha256 is None


def test_cmy8_streams_close_as_one_envelope(cmy8_volume) -> None:
    payload, k_total, certs = cmy8_volume
    result = close_volume(certs, CMY8_SPEC)
    assert result.verified and result.payload == payload
    assert result.k_total == k_total
    assert {row.stream_id for row in result.blocks} == {"C", "M", "Y"}
    assert result.diagnostics["n_certificates_by_stream"] == {
        "C": N_CERTS, "M": N_CERTS, "Y": N_CERTS}


def test_cmy8_starved_stream_leaves_the_volume_open(cmy8_volume) -> None:
    _payload_bytes, _k, certs = cmy8_volume
    kept = tuple(cert for cert in certs if cert.stream_id != "Y")
    result = close_volume(kept, CMY8_SPEC)
    assert result.status == "open" and result.payload is None
    assert result.diagnostics["unsolved_streams"] == ("Y",)


def test_close_spec_refuses_a_foreign_stream() -> None:
    with pytest.raises(ValueError):
        K_SPEC.stream_profile("C")
    with pytest.raises(ValueError):
        CloseStreamProfile("C", 2087, 2)    # wrong frozen auxiliary

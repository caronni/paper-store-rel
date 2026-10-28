"""Focused stream-coordinate and multistream close tests.

The numerical detector is intentionally faked here.  These tests exercise
the durable/scheduler/close authority without making receiver-state tests
depend on printer photometry.
"""
from __future__ import annotations

import dataclasses
import hashlib

import numpy as np
import pytest

from holo.core import fountain
from holo.devices.profiles import make_spec
from holo.format import metadata, streamset
from holo.receive.evidence import (
    AttemptStage,
    AttemptState,
    TileAttemptRecord,
    TileCertificateRecord,
    certificate_work_index,
)
from holo.receive.fountain_close import (
    CertifiedStreamSymbol,
    close_count_ready,
    close_volume,
    metadata_from_certificates,
)
from holo.receive.records import (
    certificate_for_close,
    certificate_record_from_user_bits,
    stream_attempt_identity,
    validate_certificate_record,
)
from holo.receive.session import SessionIndex, SessionState
from holo.receive.session_validation import validate_attempt
from holo.receive.state_codec import decode_typed, encode_typed


def _stream_certificates(spec, payload: bytes, n_symbols: int = 64):
    layout = streamset.StreamSet(tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in spec.stream_profiles
    ))
    packed = streamset.pack_payload(payload, layout)
    counters = np.arange(n_symbols, dtype=np.int64)
    metadata_bits = metadata.tile_bits(
        metadata.encode_metadata(0, packed.k_total), counters)
    rows = []
    for source, profile in zip(
            packed.streams, spec.stream_profiles, strict=True):
        code = fountain.VolumeCode(
            packed.k_total,
            profile.symbol_bits,
            spec.seed,
            spec.tiles_per_page,
            stream_id=profile.stream_id,
            fountain_aux=profile.fountain_aux,
        )
        symbols = code.encode_symbols(source.rows, counters)
        rows.extend(
            CertifiedStreamSymbol(
                counter=int(counter),
                page=0,
                ty=int(counter) // spec.layout.tiles_yx[1],
                tx=int(counter) % spec.layout.tiles_yx[1],
                stream_id=profile.stream_id,
                symbol=symbol,
                metadata_bit=int(metadata_bit),
            )
            for counter, symbol, metadata_bit in zip(
                counters, symbols, metadata_bits, strict=True)
        )
    return packed.k_total, tuple(rows)


@pytest.mark.parametrize(
    "coding_id",
    (
        "c2-cmy7-p120-v0",
        "c3-cmy7-p120-v0",
        "c2-cmy8-p120-v0",
        "c3-cmy8-p120-v0",
    ),
)
def test_color_close_recovers_one_verified_envelope(coding_id: str) -> None:
    spec = make_spec(coding_id)
    payload = hashlib.sha256(coding_id.encode()).digest() * 250
    k_total, certificates = _stream_certificates(spec, payload)

    result = close_volume(certificates, spec)

    assert result.verified and result.payload == payload
    assert result.k_total == k_total
    assert {row.stream_id for row in result.blocks} == set(spec.stream_ids)
    assert result.symbols_used == len(certificates)


def test_cmy8_partial_stream_progress_is_independent() -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    payload = b"partial CMY8 stream progress" * 300
    k_total, certificates = _stream_certificates(spec, payload)
    partial = tuple(
        row for row in certificates if row.stream_id != "Y")

    result = close_volume(partial, spec)

    assert result.status == "open"
    assert result.k_total == k_total
    assert result.payload is None
    assert result.diagnostics["unsolved_streams"] == ("Y",)
    assert all(row.solved for row in result.blocks
               if row.stream_id in ("C", "M"))
    assert all(not row.solved for row in result.blocks
               if row.stream_id == "Y")


def test_close_count_gate_requires_k_in_every_independent_stream() -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    k_total, certificates = _stream_certificates(
        spec, b"count gate independent streams" * 500)
    assert k_total < 64
    assert close_count_ready(certificates, spec)
    assert not close_count_ready(tuple(
        row for row in certificates if row.stream_id != "Y"), spec)


def test_close_count_gate_checks_every_fountain_block(
    monkeypatch,
) -> None:
    monkeypatch.setattr(fountain, "BLOCK_K_MAX", 2)
    spec = make_spec("c2-cmy7-p120-v0")
    profile = spec.stream_profiles[0]
    k_total = 3
    code = fountain.VolumeCode(
        k_total,
        profile.symbol_bits,
        spec.seed,
        spec.tiles_per_page,
        stream_id=profile.stream_id,
        fountain_aux=profile.fountain_aux,
    )
    by_block = {block: [] for block in range(code.n_blocks)}
    for counter in range(spec.max_tiles_addressable):
        block, _row = code.block_row_of(counter)
        by_block[block].append(counter)
        if len(by_block[0]) >= 48 and len(by_block[1]) >= 1:
            break
    selected = by_block[0][:48]
    metadata_word = metadata.encode_metadata(0, k_total)

    def certificate(counter: int) -> CertifiedStreamSymbol:
        page, ty, tx = spec.tile_address(counter)
        return CertifiedStreamSymbol(
            counter,
            page,
            ty,
            tx,
            profile.stream_id,
            np.zeros(profile.symbol_bits, np.uint8),
            metadata.tile_bit(metadata_word, counter),
        )

    starved = tuple(certificate(counter) for counter in selected)
    assert not close_count_ready(starved, spec)
    balanced = (*starved, certificate(by_block[1][0]))
    assert close_count_ready(balanced, spec)


def test_metadata_copies_do_not_create_rank_and_disagreement_is_fatal() -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    _k_total, certificates = _stream_certificates(
        spec, b"metadata copies" * 500, n_symbols=48)

    version, _k, diagnostics = metadata_from_certificates(
        certificates, spec)
    assert version == 0
    assert diagnostics["n_certificates"] == 3 * 48
    assert diagnostics["n_unique_metadata_counters"] == 48
    assert diagnostics["metadata_rank"] == 24

    first = certificates[0]
    target = next(
        row for row in certificates
        if row.counter == first.counter and row.stream_id == "M")
    contradiction = dataclasses.replace(
        target,
        metadata_bit=1 - first.metadata_bit,
    )
    mixed = tuple(
        contradiction if row is target else row
        for row in certificates
    )
    result = close_volume(mixed, spec)
    assert result.status == "integrity_failure"
    assert result.diagnostics["phase"] == "metadata"
    assert close_count_ready(mixed, spec)


def test_same_stream_symbol_conflict_is_fatal_but_siblings_are_not() -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    _k_total, certificates = _stream_certificates(
        spec, b"same-stream conflict" * 500)
    c = next(row for row in certificates
             if row.counter == 0 and row.stream_id == "C")
    altered = np.array(c.symbol, copy=True)
    altered[0] ^= np.uint8(1)
    conflicting = dataclasses.replace(c, symbol=altered)

    result = close_volume((*certificates, conflicting), spec)
    assert result.status == "integrity_failure"
    assert result.diagnostics["phase"] == "fountain"

    # The unmodified C/M/Y certificates already share every physical
    # counter and carry different stream symbols; that set closes normally.
    assert close_volume(certificates, spec).verified


def test_record_identity_and_selective_work_use_stream_coordinate() -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    block_id = hashlib.sha256(b"one physical evidence block").hexdigest()
    address = (0, 0, 0)
    source = "a" * 64
    attempts = tuple(
        TileAttemptRecord(
            attempt_id=stream_attempt_identity(
                spec, address, stream_id, AttemptStage.SCAN, (block_id,)),
            source_sha256=source,
            lane_id="lane-0",
            page=0,
            tile_yx=(0, 0),
            stage=AttemptStage.SCAN,
            state=AttemptState.ATTEMPTED_FAILED,
            n_informative=1,
            n_iters=1,
            syndrome_ok=False,
            crc_ok=None,
            component_block_ids=(block_id,),
            dependency_certificate_ids=(),
            stream_id=stream_id,
            child_outcomes=((1, False),),
        )
        for stream_id in spec.stream_ids
    )
    assert len({row.attempt_id for row in attempts}) == 3
    assert {row.work_key for row in attempts} == {
        (0, 0, 0, "C"), (0, 0, 0, "M"), (0, 0, 0, "Y")}

    profile = spec.stream_profiles[0]
    user = np.zeros(profile.user_bits, dtype=np.uint8)
    c_cert = certificate_record_from_user_bits(
        spec,
        page=0,
        tile_yx=(0, 0),
        stream_id="C",
        user_bits=user,
        origin_attempt_id=attempts[0].attempt_id,
    )
    validate_certificate_record(c_cert, spec)
    close_input = certificate_for_close(c_cert, spec)
    assert close_input.stream_id == "C"
    assert close_input.symbol.shape == (profile.symbol_bits,)
    encoded = encode_typed(c_cert)
    assert encoded["stream_id"] == "C"
    assert decode_typed(
        encoded, TileCertificateRecord) == c_cert

    # A sibling certificate is legal; a different value at C is not.
    m_cert = certificate_record_from_user_bits(
        spec,
        page=0,
        tile_yx=(0, 0),
        stream_id="M",
        user_bits=user,
        origin_attempt_id=attempts[1].attempt_id,
    )
    assert len(certificate_work_index((c_cert, m_cert))) == 2
    with pytest.raises(ValueError, match="tile stream"):
        certificate_work_index((
            c_cert,
            dataclasses.replace(c_cert, certificate_id="f" * 64),
        ))

    retry_m = TileAttemptRecord(
        attempt_id=stream_attempt_identity(
            spec, address, "M", AttemptStage.RETRY150, (block_id,)),
        source_sha256=source,
        lane_id="lane-0",
        page=0,
        tile_yx=(0, 0),
        stage=AttemptStage.RETRY150,
        state=AttemptState.ATTEMPTED_FAILED,
        n_informative=1,
        n_iters=1,
        syndrome_ok=False,
        crc_ok=None,
        component_block_ids=(block_id,),
        dependency_certificate_ids=(),
        stream_id="M",
        child_outcomes=((1, False),),
    )
    with pytest.raises(ValueError, match="no baseline"):
        validate_attempt(
            retry_m, {}, {}, None, (attempts[0],),
            require_components=False)
    validate_attempt(
        retry_m, {}, {}, None, (attempts[1],),
        require_components=False)


def test_partial_cmy8_session_index_does_not_suppress_siblings() -> None:
    spec = make_spec("c2-cmy8-p120-v0")
    user = np.zeros(spec.stream_profiles[0].user_bits, dtype=np.uint8)
    certificate = certificate_record_from_user_bits(
        spec,
        page=0,
        tile_yx=(0, 0),
        stream_id="C",
        user_bits=user,
        origin_attempt_id="fake-detector-attempt",
    )
    state = dataclasses.replace(
        SessionState.create(spec.spec_id, "test/stream-state-v1", (0,)),
        certificates=(certificate,),
    )
    index = SessionIndex(state, validate=False)

    assert index.certificate_tiles == {
        (0, 0, 0, "C"): certificate.certificate_id}


def test_cmy7_record_padding_is_part_of_certificate_integrity() -> None:
    spec = make_spec("c2-cmy7-p120-v0")
    user = np.zeros(spec.stream_profiles[0].user_bits, dtype=np.uint8)
    record = certificate_record_from_user_bits(
        spec,
        page=0,
        tile_yx=(0, 0),
        stream_id="main",
        user_bits=user,
        origin_attempt_id="fake-detector-attempt",
    )
    corrupted = bytearray(record.packed_user_bits)
    corrupted[-1] |= 0x80
    with pytest.raises(ValueError, match="padding"):
        validate_certificate_record(
            dataclasses.replace(record, packed_user_bits=bytes(corrupted)),
            spec,
        )

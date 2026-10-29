"""The addressed one-bit metadata channel, and what a close makes of it.

Gate E re-home: the vehicle is `holo.format.metadata` (the algebra) plus
`holo.receiver.format.close` over generator-minted certificates — the retired v1
`receive.fountain_close` was a wrapper around exactly those two.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo.core import fountain
from holo.format import envelope, metadata
from holo.format.resolve import resolve_format_ref
from holo.receiver.data import IntegrityError
from holo.receiver.format import close

from _receive_free import certificate, holo3_row

FORMAT_REF = "c3-k-r0550@7x7"
SPEC = resolve_format_ref(FORMAT_REF)
ROW = holo3_row(FORMAT_REF)


def _certificates(word, counters, symbols=None):
    """Certificates carrying the metadata bit the printed tile would."""
    counters = np.asarray(counters, dtype=np.int64)
    bits = metadata.tile_bits(word, counters)
    zero = np.zeros(SPEC.symbol_bits, np.uint8)
    return [certificate(ROW, int(counter), "main", int(bit),
                        zero if symbols is None else symbols[index])
            for index, (counter, bit) in enumerate(zip(counters, bits))]


def _counter_of(cert) -> int:
    return (cert.page * ROW.tiles_per_page
            + cert.ty * ROW.tiles_yx[1] + cert.tx)


def _decode(certs):
    """The metadata algebra alone, read back off the same certificates."""
    return metadata.decode_metadata(
        (_counter_of(cert), int(cert.user_bits[0])) for cert in certs)


def _flip_metadata_bit(certs, index: int) -> None:
    cert = certs[index]
    certs[index] = certificate(
        ROW, _counter_of(cert), "main", int(cert.user_bits[0]) ^ 1,
        np.asarray(cert.user_bits[1:], np.uint8))


def test_close_adapter_recovers_from_hundreds_of_addressed_bits():
    word = metadata.encode_metadata(0, 99_083)
    counters = np.random.default_rng(9).choice(
        metadata.MAX_COUNTER, size=300, replace=False)
    certs = _certificates(word, counters)
    assert close.metadata_from_certificates(certs, ROW) == (0, 99_083,
                                                            "ready")
    decoded = _decode(certs)
    assert decoded.ok is True
    assert decoded.rank == 24
    assert decoded.n_unique_counters == 300


def test_close_adapter_refuses_unsupported_version_without_more_captures():
    word = metadata.encode_metadata(1, 99_083)
    certs = _certificates(word, np.arange(48))
    assert close.metadata_from_certificates(certs, ROW) == (1, None,
                                                            "unsupported")

    result = close.close_volume(certs, ROW)
    assert result.payload is None
    assert result.status == "unsupported"
    assert result.reason == "unsupported metadata version 1"


def test_close_adapter_refuses_nonzero_canonical_padding():
    """One bit set past the envelope is the whole refusal — no monkeypatch.

    The v1 test stubbed the receiver's decoder build; the pinned law is
    the padding gate, so mint the offending source and let the real close
    reach it through the fountain.
    """
    payload = b"canonical padding"
    k_total = envelope.source_symbol_count(len(payload), SPEC.symbol_bits)
    envelope_bits = np.unpackbits(np.frombuffer(
        envelope.wrap(payload), dtype=np.uint8))
    source = np.zeros(k_total * SPEC.symbol_bits, dtype=np.uint8)
    source[:envelope_bits.size] = envelope_bits
    source[envelope_bits.size] = 1
    source = source.reshape(k_total, SPEC.symbol_bits)

    counters = np.arange(48)
    code = fountain.VolumeCode(k_total, SPEC.symbol_bits, SPEC.seed,
                               tiles_per_page=SPEC.tiles_per_page)
    packed = np.packbits(source, axis=1)
    certs = _certificates(
        metadata.encode_metadata(0, k_total), counters,
        code.encode_symbols(packed, counters.astype(np.int64)))
    result = close.close_volume(certs, ROW)
    assert result.status == "integrity_failure"
    assert result.payload is None
    assert "nonzero padding" in (result.reason or "")


def test_close_adapter_rejects_an_inconsistent_certified_system():
    word = metadata.encode_metadata(0, 99_083)
    certs = _certificates(word, np.arange(48))
    _flip_metadata_bit(certs, -1)
    with pytest.raises(IntegrityError, match="inconsistent"):
        close.metadata_from_certificates(certs, ROW)


def test_metadata_progress_publishes_k_without_a_fountain_solve():
    """`decode --complete` still knows K — it is the metadata word."""
    word = metadata.encode_metadata(0, 99_083)
    certs = _certificates(word, np.arange(64))
    ready, k_total, blocks = close.close_count_progress(certs, ROW)
    assert not ready
    assert k_total is not None
    decoded = _decode(certs)
    assert decoded.k == 99_083
    assert (decoded.rank, decoded.rank_shortfall) == (24, 0)
    assert decoded.check_shortfall == 0
    assert decoded.inconsistent is False
    # The count path publishes K and the per-block ESI counts without
    # solving.  holo3 reports the decoder's real rank here, so the v1
    # count-only "rank stays 0" projection has no counterpart — the
    # surviving law is that K arrives from the word, unsolved.
    assert blocks and sum(row.have for row in blocks) == 64
    assert all(row.solved is False for row in blocks)
    assert all(row.needed > 0 for row in blocks)


def test_metadata_progress_reports_shortfall_and_never_raises():
    """An observer path must not raise: integrity failure is a fact to show."""
    word = metadata.encode_metadata(0, 99_083)
    early = _certificates(word, np.arange(10))
    assert close.close_count_progress(early, ROW) == (False, None, ())
    assert _decode(early).rank_shortfall == 14
    assert _decode(early).check_shortfall == 38

    certs = _certificates(word, np.arange(48))
    _flip_metadata_bit(certs, -1)
    assert close.close_count_progress(certs, ROW) == (True, None, ())
    assert _decode(certs).inconsistent is True

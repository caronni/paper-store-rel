"""Receiver adapter tests for the addressed one-bit metadata channel.

These use certificate-shaped records because Track 3 owns certificate
construction and is being rewritten independently; the close adapter's only
metadata inputs are the certified counter and bit.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.format import envelope, metadata
from holo.receive import fountain_close


SPEC = make_spec("c3-r0550")


def _certificates(word, counters):
    counters = np.asarray(counters, dtype=np.int64)
    bits = metadata.tile_bits(word, counters)
    return [SimpleNamespace(counter=int(counter), metadata_bit=int(bit),
                            stream_id="main")
            for counter, bit in zip(counters, bits)]


def test_close_adapter_recovers_from_hundreds_of_addressed_bits():
    word = metadata.encode_metadata(0, 99_083)
    counters = np.random.default_rng(9).choice(
        metadata.MAX_COUNTER, size=300, replace=False)
    version, k_total, diagnostics = \
        fountain_close.metadata_from_certificates(
            _certificates(word, counters), SPEC)
    assert (version, k_total) == (0, 99_083)
    assert diagnostics["ok"] is True
    assert diagnostics["metadata_rank"] == 24
    assert diagnostics["n_unique_metadata_counters"] == 300


def test_close_adapter_reports_rank_and_check_shortfalls():
    word = metadata.encode_metadata(0, 99_083)
    version, k_total, diagnostics = \
        fountain_close.metadata_from_certificates(
            _certificates(word, np.arange(10)), SPEC)
    assert version is None and k_total is None
    assert diagnostics["state"] == "incomplete"
    assert diagnostics["metadata_rank_shortfall"] == 14
    assert diagnostics["metadata_check_shortfall"] == 38


def test_close_adapter_refuses_unsupported_version_without_more_captures():
    word = metadata.encode_metadata(1, 99_083)
    certs = _certificates(word, np.arange(48))
    version, k_total, diagnostics = \
        fountain_close.metadata_from_certificates(certs, SPEC)
    assert version is None and k_total is None
    assert diagnostics["state"] == "unsupported"
    assert diagnostics["decoded_version"] == 1

    result = fountain_close.close_volume(certs, SPEC)
    assert not result.verified and result.payload is None
    assert result.status != "open"
    assert result.diagnostics["state"] == "unsupported"
    assert result.reason.startswith("metadata unsupported:")


def test_close_adapter_refuses_nonzero_canonical_padding(monkeypatch):
    payload = b"canonical padding"
    k_total = envelope.source_symbol_count(len(payload), SPEC.symbol_bits)
    certs = _certificates(metadata.encode_metadata(0, k_total), np.arange(48))
    envelope_bits = np.unpackbits(np.frombuffer(
        envelope.wrap(payload), dtype=np.uint8))
    source = np.zeros(k_total * SPEC.symbol_bits, dtype=np.uint8)
    source[:envelope_bits.size] = envelope_bits
    source[envelope_bits.size] = 1
    source = source.reshape(k_total, SPEC.symbol_bits)

    class _SolvedDecoder:
        def try_solve(self):
            return source

        def rank_status(self):
            return [{"block": 0, "needed": k_total,
                     "have": k_total + 16, "rank": k_total,
                     "solved": True}]

    monkeypatch.setattr(
        fountain_close, "_build_decoder",
        lambda certificates, spec, k: (_SolvedDecoder(), len(certs)))
    result = fountain_close.close_volume(certs, SPEC)
    assert not result.verified and result.payload is None
    assert result.reason == "nonzero bits in canonical envelope padding"
    assert result.diagnostics["padding_nonzero"] is True


def test_close_adapter_rejects_an_inconsistent_certified_system():
    word = metadata.encode_metadata(0, 99_083)
    certs = _certificates(word, np.arange(48))
    certs[-1].metadata_bit ^= 1
    with pytest.raises(fountain_close.MetadataIntegrityError) as excinfo:
        fountain_close.metadata_from_certificates(certs, SPEC)
    assert excinfo.value.diagnostics["metadata_inconsistent"] is True


def test_metadata_progress_publishes_k_without_a_fountain_solve():
    """v0.32: `decode --complete` still knows K — it is the metadata word."""
    word = metadata.encode_metadata(0, 99_083)
    certs = _certificates(word, np.arange(64))
    progress = fountain_close.metadata_progress(certs, SPEC)
    assert progress.k_total == 99_083
    assert progress.metadata.rank == 24
    assert progress.metadata.rank_shortfall == 0
    assert progress.metadata.check_shortfall == 0
    assert progress.metadata.inconsistent is False
    # §10.4 count-only projection: distinct ESIs per block, and NOTHING that
    # needs a decoder — rank and solved stay deferred, never faked as zero.
    assert progress.symbols_used == 64
    assert progress.blocks and sum(row.have for row in progress.blocks) == 64
    assert all(row.rank == 0 and row.solved is False
               for row in progress.blocks)
    assert all(row.needed > 0 for row in progress.blocks)


def test_metadata_progress_reports_shortfall_and_never_raises():
    """An observer path must not raise: integrity failure is a fact to show."""
    word = metadata.encode_metadata(0, 99_083)
    early = fountain_close.metadata_progress(
        _certificates(word, np.arange(10)), SPEC)
    assert early.k_total is None
    assert early.metadata.rank_shortfall == 14
    assert early.metadata.check_shortfall == 38

    certs = _certificates(word, np.arange(48))
    certs[-1].metadata_bit ^= 1
    broken = fountain_close.metadata_progress(certs, SPEC)
    assert broken.k_total is None
    assert broken.metadata.inconsistent is True

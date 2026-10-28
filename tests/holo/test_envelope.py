import sys; from pathlib import Path

import hashlib

import pytest

from holo.format.envelope import (
    LEN_BYTES, MAX_PAYLOAD_BYTES, OVERHEAD_BYTES, EnvelopeError,
    source_symbol_count, try_unwrap, unwrap, wrap,
)

PAYLOADS = [b"", b"x", b"hello holo", bytes(range(256)) * 41]


def test_overhead_constant():
    assert OVERHEAD_BYTES == 36
    for data in PAYLOADS:
        assert len(wrap(data)) == OVERHEAD_BYTES + len(data)


def test_canonical_source_symbol_count():
    assert source_symbol_count(0, 2107) == 1
    assert source_symbol_count(5120, 2107) == 20
    assert source_symbol_count(99_083, 1) == (99_083 + 36) * 8
    with pytest.raises(ValueError):
        source_symbol_count(-1, 2107)
    with pytest.raises(ValueError):
        source_symbol_count(1, 0)
    with pytest.raises(TypeError):
        source_symbol_count(1.5, 2107)


def test_wire_layout():
    data = b"holo format v1 envelope"
    stream = wrap(data)
    assert stream[:32] == hashlib.sha256(data).digest()
    assert stream[32:36] == len(data).to_bytes(4, "big")
    assert stream[36:] == data


def test_oversize_payload_refused():
    # the guard fires on the length, so fake the length without 4 GiB
    class _Huge(bytes):
        def __len__(self):
            return MAX_PAYLOAD_BYTES + 1
    with pytest.raises(ValueError, match="length field"):
        wrap(_Huge())


@pytest.mark.parametrize("data", PAYLOADS)
def test_round_trip(data):
    assert unwrap(wrap(data)) == data
    assert try_unwrap(wrap(data)) == data


@pytest.mark.parametrize("pad", [1, 7, 4096])
def test_trailing_zero_padding_ignored(pad):
    data = b"padded payload"
    stream = wrap(data) + bytes(pad)
    assert unwrap(stream) == data
    assert try_unwrap(stream) == data


def test_sha_mismatch_refused():
    stream = bytearray(wrap(b"some payload bytes"))
    stream[41] ^= 0x01               # flip one data bit
    with pytest.raises(EnvelopeError):
        unwrap(bytes(stream))
    assert try_unwrap(bytes(stream)) is None


def test_sha_field_corruption_refused():
    stream = bytearray(wrap(b"some payload bytes"))
    stream[0] ^= 0x80                # corrupt the digest itself
    with pytest.raises(EnvelopeError):
        unwrap(bytes(stream))
    assert try_unwrap(bytes(stream)) is None


def test_short_stream_refused():
    for stream in (b"", b"short", wrap(b"abc")[:35]):
        with pytest.raises(EnvelopeError):
            unwrap(stream)
        assert try_unwrap(stream) is None


def test_declared_length_beyond_stream_refused():
    data = b"0123456789"
    stream = bytearray(wrap(data))
    stream[32:36] = (len(data) + 1).to_bytes(4, "big")
    with pytest.raises(EnvelopeError):
        unwrap(bytes(stream))
    assert try_unwrap(bytes(stream)) is None
    # absurd length (the receiver sees zero-padded K*S streams, len sane)
    stream[32:36] = MAX_PAYLOAD_BYTES.to_bytes(4, "big")
    with pytest.raises(EnvelopeError):
        unwrap(bytes(stream))


def test_length_shorter_than_trailing_data_is_authoritative():
    # declared len selects the payload; extra bytes are padding, and the
    # sha binds exactly data[0:len]
    inner = b"abcdef"
    stream = (hashlib.sha256(inner).digest()
              + len(inner).to_bytes(4, "big") + inner + bytes(10))
    assert unwrap(stream) == inner

"""holo format-v1 payload envelope: {sha256:32B}{len:4B BE}{data}.

FORMAT-AXIS (HOLO-DESIGN §7.1, decision F7; amended §13.12). The
fountain source stream is the wrapped payload, zero-padded to K*S bits.
The verified stop is fully in-band: fountain rank complete -> solve ->
unwrap/SHA-256 over data[0:len] -> volume-close canonical-K/zero-tail gate ->
done. A wrong SHA is fatal, never partial success; rank/symbol counts are
never a stop condition.

The length is an unsigned 32-bit big-endian integer — the format-wide
integer rule (all multi-byte fields BE). u32 is already generous: the
metadata word's K:18 field caps a volume at 262,143 source symbols
(~69 MB at the largest coding symbol), so lengths beyond 2^27 are
unreachable by any legal generator; wrap() refuses payloads that do
not fit the field.

The envelope parser ignores trailing bytes beyond the declared length because
they are outside the payload digest. Volume closure separately enforces the
format's canonical minimal K and zero-valued tail bits; parsing alone does not.
"""
from __future__ import annotations

import hashlib
import operator

SHA_BYTES = 32
LEN_BYTES = 4
OVERHEAD_BYTES = SHA_BYTES + LEN_BYTES  # 36
MAX_PAYLOAD_BYTES = (1 << (8 * LEN_BYTES)) - 1


class EnvelopeError(ValueError):
    """The stream is not a valid v1 payload envelope."""


def source_symbol_count(payload_len_bytes: int, symbol_bits: int) -> int:
    """Canonical minimal K for an envelope and a source-symbol width."""
    if isinstance(payload_len_bytes, bool) or isinstance(symbol_bits, bool):
        raise TypeError("payload length and symbol width must be integers")
    try:
        payload_len_bytes = operator.index(payload_len_bytes)
        symbol_bits = operator.index(symbol_bits)
    except TypeError as exc:
        raise TypeError(
            "payload length and symbol width must be integers") from exc
    if payload_len_bytes < 0:
        raise ValueError("payload length must be >= 0")
    if symbol_bits <= 0:
        raise ValueError("symbol width must be >= 1")
    envelope_bits = (OVERHEAD_BYTES + payload_len_bytes) * 8
    return -(-envelope_bits // symbol_bits)


def wrap(data: bytes) -> bytes:
    """sha256(data) || len(data) as 4-byte big-endian || data."""
    if len(data) > MAX_PAYLOAD_BYTES:   # before the copy: refuse, don't buffer
        raise ValueError(f"payload of {len(data)} bytes exceeds the "
                         f"{LEN_BYTES}-byte length field "
                         f"(max {MAX_PAYLOAD_BYTES})")
    data = bytes(data)
    return (hashlib.sha256(data).digest()
            + len(data).to_bytes(LEN_BYTES, "big")
            + data)


def _parse(stream: bytes) -> tuple[bytes | None, str | None]:
    stream = bytes(stream)
    if len(stream) < OVERHEAD_BYTES:
        return None, (f"stream of {len(stream)} bytes shorter than the "
                      f"{OVERHEAD_BYTES}-byte envelope header")
    declared_len = int.from_bytes(stream[SHA_BYTES:OVERHEAD_BYTES], "big")
    if declared_len > len(stream) - OVERHEAD_BYTES:
        return None, (f"declared length {declared_len} exceeds the "
                      f"{len(stream) - OVERHEAD_BYTES} bytes present")
    data = stream[OVERHEAD_BYTES:OVERHEAD_BYTES + declared_len]
    if hashlib.sha256(data).digest() != stream[:SHA_BYTES]:
        return None, "payload SHA-256 mismatch"
    return data, None


def unwrap(stream: bytes) -> bytes:
    """Verified payload bytes, or EnvelopeError."""
    data, err = _parse(stream)
    if err is not None:
        raise EnvelopeError(err)
    assert data is not None
    return data


def try_unwrap(stream: bytes) -> bytes | None:
    """Receiver-side unwrap: verified payload bytes, or None."""
    data, _err = _parse(stream)
    return data

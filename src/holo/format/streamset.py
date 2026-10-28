"""Exact common-K, stream-major source mapping for CMY8.

CMY8 carries one envelope through several independent fountain streams.  For
an ordered stream set ``[(id_0, S_0), ..., (id_n, S_n)]`` the format mapping
is:

* ``K = ceil(envelope_bits / sum(S_i))``;
* zero-pad the envelope to exactly ``K * sum(S_i)`` bits;
* give stream ``i`` its contiguous ``K * S_i``-bit slice; and
* split that slice into ``K`` rows of ``S_i`` bits.

The stream boundaries are bit boundaries.  They are never rounded to bytes.
Each returned source matrix is row-packed by the same
``holo.core.fountain.pack_bit_slice`` that backs ``fountain.pack_source``
(shared by construction, not by parallel implementation) and can be passed
directly to a ``fountain.VolumeCode`` with the corresponding ``S_i``.

Packing and reassembly use bounded bit chunks.  They allocate the required
packed source/result storage, but never a payload-sized unpacked bit vector.
"""
from __future__ import annotations

from dataclasses import dataclass
import operator
from typing import Iterable

import numpy as np

from ..core import fountain
from ..core.channel import PLANE_ORDER
from . import envelope


CMY8_STREAM_ORDER: tuple[str, ...] = PLANE_ORDER

# The reassembly walkers share the packer's temporary-memory footing (the
# packing itself now delegates to fountain.pack_bit_slice directly).
_CHUNK_BITS = fountain.CHUNK_BITS


class StreamSetIntegrityError(ValueError):
    """Solved streams do not form one canonical, verified envelope."""


@dataclass(frozen=True, slots=True)
class StreamSet:
    """An ordered, non-empty set of unique ``(stream_id, symbol_bits)``.

    ``stream_id`` is deliberately opaque here.  A format row owns the
    permitted identifiers and their order; this value object only freezes
    and validates that order.
    """

    streams: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        try:
            raw = tuple(self.streams)
        except TypeError as exc:
            raise TypeError(
                "streams must be an iterable of (id, width)"
            ) from exc
        if not raw:
            raise ValueError("stream set must not be empty")

        normalized: list[tuple[str, int]] = []
        seen: set[str] = set()
        for position, item in enumerate(raw):
            if (not isinstance(item, (tuple, list))
                    or len(item) != 2):
                raise TypeError(
                    f"stream {position} must be an (id, width) pair"
                )
            stream_id, width = item
            if not isinstance(stream_id, str) or not stream_id:
                raise ValueError("stream IDs must be non-empty strings")
            if stream_id in seen:
                raise ValueError(f"duplicate stream ID {stream_id!r}")
            if isinstance(width, (bool, np.bool_)):
                raise TypeError("stream widths must be integers")
            try:
                width = operator.index(width)
            except TypeError as exc:
                raise TypeError("stream widths must be integers") from exc
            if width <= 0:
                raise ValueError("stream widths must be positive")
            normalized.append((stream_id, int(width)))
            seen.add(stream_id)

        object.__setattr__(self, "streams", tuple(normalized))

    @property
    def stream_ids(self) -> tuple[str, ...]:
        return tuple(stream_id for stream_id, _width in self.streams)

    @property
    def symbol_widths(self) -> tuple[int, ...]:
        return tuple(width for _stream_id, width in self.streams)

    @property
    def total_symbol_bits(self) -> int:
        return sum(self.symbol_widths)


@dataclass(frozen=True, slots=True)
class PackedSource:
    """One stream's row-packed source matrix."""

    stream_id: str
    symbol_bits: int
    rows: np.ndarray


@dataclass(frozen=True, slots=True)
class PackedSourceSet:
    """Canonical common ``K`` and its ordered packed source matrices."""

    k_total: int
    streams: tuple[PackedSource, ...]


def source_symbol_count(payload_len_bytes: int,
                        stream_set: StreamSet) -> int:
    """Canonical common ``K`` for a payload and this stream set."""
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    return envelope.source_symbol_count(
        payload_len_bytes, stream_set.total_symbol_bits
    )


def _canonical_k_for_wrapped(wrapped: bytes, stream_set: StreamSet) -> int:
    if not wrapped:
        # A real wrapped envelope is at least its 36-byte header.  Keeping
        # K >= 1 makes every returned matrix usable by fountain.VolumeCode.
        raise ValueError("wrapped envelope must not be empty")
    return -(-(len(wrapped) * 8) // stream_set.total_symbol_bits)


def pack_source(wrapped_envelope: bytes,
                stream_set: StreamSet) -> PackedSourceSet:
    """Map one wrapped envelope to canonical stream-major source matrices.

    ``wrapped_envelope`` is not reparsed here; generation normally supplies
    ``envelope.wrap(payload)``.  Integrity and canonical-padding checks live
    in :func:`unwrap_solved`, at the inverse boundary.
    """
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    if not isinstance(wrapped_envelope, (bytes, bytearray, memoryview)):
        raise TypeError("wrapped_envelope must be bytes-like")
    wrapped = bytes(wrapped_envelope)
    k_total = _canonical_k_for_wrapped(wrapped, stream_set)
    data = np.frombuffer(wrapped, dtype=np.uint8)
    content_bits = len(wrapped) * 8

    packed: list[PackedSource] = []
    bit_start = 0
    for stream_id, symbol_bits in stream_set.streams:
        rows = fountain.pack_bit_slice(
            data, content_bits, bit_start, k_total, symbol_bits
        )
        packed.append(PackedSource(stream_id, symbol_bits, rows))
        bit_start += k_total * symbol_bits
    assert bit_start == k_total * stream_set.total_symbol_bits
    return PackedSourceSet(k_total, tuple(packed))


def pack_payload(payload: bytes, stream_set: StreamSet) -> PackedSourceSet:
    """Wrap a payload, then apply :func:`pack_source`."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    return pack_source(envelope.wrap(bytes(payload)), stream_set)


# ------------------------------------------------- pooled source mapping
#
# The -v1 pooled rows (docs/CMY8-POOLED-FOUNTAIN.md §2.1) run ONE fountain
# over row-major S-bit source rows: k_total = n_streams * k_meta, source
# row j carries envelope bits [j*S, (j+1)*S), and S is the pool's one
# symbol width — the widest stream's. At equal widths (every -v0 and
# uniform -v1 row) k_meta is the stream-major mapping's canonical common
# K by identical arithmetic and the flat padded bit stream is
# byte-identical between the two mappings, only the row indexing
# differing. An uneven cmy8 triplet's narrower streams carry column
# groups of S (docs/CMY8-COLUMN-GROUPS.md §3.4): its envelope is
# n_streams * S bits per k_meta unit, wider than the stream widths' sum,
# and no -v0 mapping ever carries such a triplet.


def pooled_symbol_bits(stream_set: StreamSet) -> int:
    """The pool's one symbol width: the widest stream's."""
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    return max(stream_set.symbol_widths)


def pooled_envelope_bits(stream_set: StreamSet) -> int:
    """Envelope bits per ``k_meta`` unit of a pooled row: ``n_streams``
    symbols of the one width (the pooled canonical-K law)."""
    return len(stream_set.streams) * pooled_symbol_bits(stream_set)


def pooled_source_symbol_count(payload_len_bytes: int,
                               stream_set: StreamSet) -> int:
    """Canonical ``k_meta`` of a pooled row for a payload length."""
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    return envelope.source_symbol_count(
        payload_len_bytes, pooled_envelope_bits(stream_set))


def pooled_pack_source(wrapped_envelope: bytes,
                       stream_set: StreamSet) -> tuple[int, np.ndarray]:
    """One wrapped envelope -> (k_meta, row-packed pooled source rows).

    The returned matrix has ``n_streams * k_meta`` rows of the pool's
    symbol width S (the widest stream's), row-packed exactly like
    ``fountain.pack_source``.
    """
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    if not isinstance(wrapped_envelope, (bytes, bytearray, memoryview)):
        raise TypeError("wrapped_envelope must be bytes-like")
    wrapped = bytes(wrapped_envelope)
    if not wrapped:
        raise ValueError("wrapped envelope must not be empty")
    s_bits = pooled_symbol_bits(stream_set)
    k_meta = -(-(len(wrapped) * 8) // pooled_envelope_bits(stream_set))
    k_total = len(stream_set.streams) * k_meta
    rows = fountain.pack_bit_slice(
        np.frombuffer(wrapped, dtype=np.uint8),
        len(wrapped) * 8, 0, k_total, s_bits,
    )
    return k_meta, rows


def pooled_pack_payload(payload: bytes,
                        stream_set: StreamSet) -> tuple[int, np.ndarray]:
    """Wrap a payload, then apply :func:`pooled_pack_source`."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")
    return pooled_pack_source(envelope.wrap(bytes(payload)), stream_set)


def pooled_unwrap_solved(solved_rows: np.ndarray, stream_set: StreamSet,
                         k_meta: int) -> bytes:
    """Reassemble and verify one canonical pooled envelope.

    ``solved_rows`` is the fountain's solved ``(n_streams * k_meta, S)``
    0/1 matrix. The three gates mirror :func:`unwrap_solved`: envelope
    length/SHA, canonical minimal ``k_meta`` for the decoded length, and
    zero padding through the exact bit capacity.
    """
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    k_meta = _validated_k(k_meta)
    s_bits = pooled_symbol_bits(stream_set)
    k_total = len(stream_set.streams) * k_meta
    rows = np.asarray(solved_rows)
    if rows.shape != (k_total, s_bits):
        raise ValueError(
            f"pooled solved rows shape {rows.shape} != "
            f"{(k_total, s_bits)}")
    _validate_bit_values(rows, s_bits)

    total_bits = k_total * s_bits
    out = np.zeros(-(-total_bits // 8), dtype=np.uint8)
    bit_offset = 0
    chunk_rows = max(1, _CHUNK_BITS // s_bits)
    for row0 in range(0, k_total, chunk_rows):
        chunk = np.asarray(
            rows[row0:row0 + chunk_rows], dtype=np.uint8
        ).reshape(-1)
        _write_bits(out, bit_offset, chunk)
        bit_offset += int(chunk.size)
    assert bit_offset == total_bits
    packed = out.tobytes()

    try:
        payload = envelope.unwrap(packed)
    except envelope.EnvelopeError as exc:
        raise StreamSetIntegrityError(
            "pooled envelope verification failed"
        ) from exc
    used_bits = (envelope.OVERHEAD_BYTES + len(payload)) * 8
    if used_bits > total_bits:
        raise StreamSetIntegrityError(
            "envelope extends beyond the exact pooled bit capacity"
        )
    canonical_k_meta = pooled_source_symbol_count(len(payload), stream_set)
    if canonical_k_meta != k_meta:
        raise StreamSetIntegrityError(
            f"pooled K {k_meta} is noncanonical for envelope "
            f"(expected {canonical_k_meta})"
        )
    if _nonzero_bits(packed, used_bits, total_bits):
        raise StreamSetIntegrityError(
            "nonzero bits in canonical pooled envelope padding"
        )
    return payload


def _validated_k(k_total: int) -> int:
    if isinstance(k_total, (bool, np.bool_)):
        raise TypeError("k_total must be an integer")
    try:
        k_total = operator.index(k_total)
    except TypeError as exc:
        raise TypeError("k_total must be an integer") from exc
    if k_total < 1:
        raise ValueError("k_total must be >= 1")
    return int(k_total)


def _validate_bit_values(rows: np.ndarray, symbol_bits: int) -> None:
    if rows.dtype.kind not in "buif":
        raise ValueError("solved source rows must be real 0/1 values")
    chunk_rows = max(1, _CHUNK_BITS // symbol_bits)
    for row0 in range(0, rows.shape[0], chunk_rows):
        chunk = rows[row0:row0 + chunk_rows]
        if rows.dtype.kind == "f" and not np.isfinite(chunk).all():
            raise ValueError("solved source rows must be finite 0/1 values")
        if np.any((chunk != 0) & (chunk != 1)):
            raise ValueError("solved source rows must contain only 0/1")


def _validate_solved(
    solved_streams: Iterable[tuple[str, np.ndarray]],
    stream_set: StreamSet,
    k_total: int,
) -> tuple[np.ndarray, ...]:
    try:
        supplied = tuple(solved_streams)
    except TypeError as exc:
        raise TypeError(
            "solved_streams must be ordered (stream_id, rows) pairs"
        ) from exc
    if len(supplied) != len(stream_set.streams):
        raise ValueError(
            f"got {len(supplied)} solved streams, "
            f"expected {len(stream_set.streams)}"
        )

    arrays: list[np.ndarray] = []
    for position, (expected_id, symbol_bits) in enumerate(
            stream_set.streams):
        item = supplied[position]
        if (not isinstance(item, (tuple, list))
                or len(item) != 2):
            raise TypeError(
                f"solved stream {position} must be an (id, rows) pair"
            )
        stream_id, values = item
        if stream_id != expected_id:
            raise ValueError(
                f"solved stream {position} is {stream_id!r}; "
                f"expected {expected_id!r}"
            )
        rows = np.asarray(values)
        expected_shape = (k_total, symbol_bits)
        if rows.shape != expected_shape:
            raise ValueError(
                f"solved stream {stream_id!r} shape {rows.shape} != "
                f"{expected_shape}"
            )
        _validate_bit_values(rows, symbol_bits)
        arrays.append(rows)
    return tuple(arrays)


def _write_bits(out: np.ndarray, bit_offset: int,
                source_bits: np.ndarray) -> None:
    """OR one 0/1 chunk into a big-endian packed destination."""
    n_bits = int(source_bits.size)
    if n_bits == 0:
        return
    packed = np.packbits(source_bits, bitorder="big")
    byte_offset, shift = divmod(bit_offset, 8)
    if shift == 0:
        out[byte_offset:byte_offset + packed.size] |= packed
        return

    first_count = min(packed.size, out.size - byte_offset)
    if first_count:
        out[byte_offset:byte_offset + first_count] |= (
            packed[:first_count] >> shift
        )
    next_offset = byte_offset + 1
    second_count = min(packed.size, out.size - next_offset)
    if second_count:
        out[next_offset:next_offset + second_count] |= (
            packed[:second_count] << (8 - shift)
        )


def reassemble_solved(
    solved_streams: Iterable[tuple[str, np.ndarray]],
    stream_set: StreamSet,
    k_total: int,
) -> bytes:
    """Concatenate solved ``(K, S_i)`` matrices in exact stream order.

    The return value contains ``ceil(K*sum(S_i)/8)`` bytes.  When the exact
    source capacity is not byte-aligned, unused low bits of the final byte
    are zero and are not part of the source bit string.
    """
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    k_total = _validated_k(k_total)
    arrays = _validate_solved(solved_streams, stream_set, k_total)
    total_bits = k_total * stream_set.total_symbol_bits
    out = np.zeros(-(-total_bits // 8), dtype=np.uint8)

    bit_offset = 0
    for rows, (_stream_id, symbol_bits) in zip(
            arrays, stream_set.streams, strict=True):
        chunk_rows = max(1, _CHUNK_BITS // symbol_bits)
        for row0 in range(0, k_total, chunk_rows):
            chunk = np.asarray(
                rows[row0:row0 + chunk_rows], dtype=np.uint8
            ).reshape(-1)
            _write_bits(out, bit_offset, chunk)
            bit_offset += int(chunk.size)
    assert bit_offset == total_bits
    return out.tobytes()


def _nonzero_bits(data: bytes, bit_start: int, bit_end: int) -> bool:
    """Whether the MSB-first half-open bit range contains a one."""
    if not 0 <= bit_start <= bit_end <= len(data) * 8:
        raise ValueError("invalid packed-bit range")
    view = memoryview(data)
    pos = bit_start
    while pos < bit_end and pos & 7:
        if view[pos >> 3] & (1 << (7 - (pos & 7))):
            return True
        pos += 1
    if pos == bit_end:
        return False
    whole_end = bit_end - (bit_end & 7)
    if pos < whole_end and any(view[pos >> 3:whole_end >> 3]):
        return True
    pos = max(pos, whole_end)
    while pos < bit_end:
        if view[pos >> 3] & (1 << (7 - (pos & 7))):
            return True
        pos += 1
    return False


def unwrap_solved(
    solved_streams: Iterable[tuple[str, np.ndarray]],
    stream_set: StreamSet,
    k_total: int,
) -> bytes:
    """Reassemble and verify one canonical stream-set envelope.

    Verification has three separate gates:

    1. the ordinary envelope length and SHA-256 check;
    2. metadata ``K`` must be the canonical minimum for the decoded length;
    3. every encoded bit after the envelope must be zero.

    The second and third checks are independent.  The envelope parser alone
    intentionally ignores trailing data and therefore cannot enforce them.
    """
    if type(stream_set) is not StreamSet:
        raise TypeError("stream_set must be a StreamSet")
    k_total = _validated_k(k_total)
    packed = reassemble_solved(solved_streams, stream_set, k_total)
    try:
        payload = envelope.unwrap(packed)
    except envelope.EnvelopeError as exc:
        raise StreamSetIntegrityError(
            "stream-set envelope verification failed"
        ) from exc

    used_bits = (envelope.OVERHEAD_BYTES + len(payload)) * 8
    capacity_bits = k_total * stream_set.total_symbol_bits
    if used_bits > capacity_bits:
        # The final packed byte contains up to seven storage-only zero bits;
        # they may never masquerade as encoded envelope bits.
        raise StreamSetIntegrityError(
            "envelope extends beyond the exact stream-set bit capacity"
        )

    canonical_k = source_symbol_count(len(payload), stream_set)
    if canonical_k != k_total:
        raise StreamSetIntegrityError(
            f"K {k_total} is noncanonical for envelope "
            f"(expected {canonical_k})"
        )
    if _nonzero_bits(packed, used_bits, capacity_bits):
        raise StreamSetIntegrityError(
            "nonzero bits in canonical stream-set envelope padding"
        )
    return payload

"""The append-only, content-addressed blob sidecar (DESIGN §5.6).

Bulk values (LLR blocks, support masks, calibration params, recovered
payload bytes) are written **once** at their commit and never rewritten,
so commit cost is independent of history size. Reads are mmap-backed and
zero-copy; numpy arrays are stored as raw C-contiguous bytes with dtype
and shape carried in the ``BlobRef``.

File layout (all offsets 8-byte aligned so ``np.frombuffer`` views are
aligned)::

    magic  = b"HOLO2BLB"                       (8 bytes, file header)
    frame  = header_len : uint64 big-endian    (8 bytes)
             header_json padded with spaces to a multiple of 8
             payload bytes
             zero padding to a multiple of 8
    header_json = {"length_bytes": int, "sha256": hex}

Contracts:

- ``put`` is content-addressed and idempotent: appending bytes already
  present returns the existing ref and writes nothing.
- The index is rebuilt by scanning frames at open; a **torn tail** (a
  frame whose header or payload is short — a crash mid-append) is
  discarded by truncating the file to the last intact frame boundary.
  This is legal because a torn tail can never have been referenced by a
  committed envelope: blobs are appended strictly before the commit that
  references them.
- A blob appended by a commit that never became durable is an inert
  orphan: it is indexed, nothing references it, and re-running the work
  re-derives the same bytes and dedups onto it.
- Payload sha is verified on read only when asked (``verify=True``);
  bulk verification is the sampled trace auditor's job, not the read
  path's. **F-13 as re-scoped (2026-08-13)**: under journal-authoritative
  persistence this file is CACHE — the content addresses ARE the hashes,
  the deep audit is delete-and-re-fold, and the recovered payload carries
  its own end-to-end sha at the close. So verify-on-read is not a
  subsystem, it is a per-site decision made where bytes become a DURABLE
  fact; where they only feed transient compute, replay is the audit.
- A read of an address this file does not hold is a refusal about an
  INCOMPLETE state, not a corrupt one: nothing was damaged, a value that
  should have been derivable is simply not here, and the remedy for a
  cache is re-derivation rather than repair. The record that NAMES a
  missing address is reported by the store's open path, where the
  records are in hand and the naming is free.

**Staging (R1/M6).** A worker no longer appends: it *stages*. Because a
ref is a pure function of the bytes (plus dtype/shape), the ref a record
carries can be computed without touching the sidecar, so a worker's
proposal can reference a blob that does not exist yet and the commit
authority materialises it — for accepted proposals only. A discarded
proposal therefore leaves no orphan, and the one genuinely mutating
thing a proposing thread used to touch is gone from the worker side
entirely.
"""
from __future__ import annotations

import mmap
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .codec import canonical_json_bytes, parse_json_bytes, sha256_hex
from .records import BlobRef

MAGIC = b"HOLO2BLB"
_ALIGN = 8
_LEN_FIELD_BYTES = 8


class BlobError(RuntimeError):
    """Sidecar corruption, or a reference to a blob that is not present."""


@dataclass(frozen=True)
class StagedBlob:
    """A bulk value a proposal carries, with the ref its records use.

    ``ref`` is exactly what :meth:`BlobSidecar.put` would return for
    ``payload`` — content-addressed, so staging and materialising cannot
    disagree, and two workers that computed the same array stage one
    blob.
    """

    ref: BlobRef
    payload: bytes

    def __post_init__(self) -> None:
        if self.ref.length_bytes != len(self.payload):
            raise BlobError(
                f"staged blob {self.ref.sha256}: ref says "
                f"{self.ref.length_bytes} bytes, payload holds "
                f"{len(self.payload)}")


def stage_bytes(payload: bytes) -> StagedBlob:
    """Stage opaque bytes; the ref is their content address."""
    return StagedBlob(
        BlobRef(sha256=sha256_hex(payload), length_bytes=len(payload)),
        payload)


def stage_array(array: np.ndarray) -> StagedBlob:
    """Stage a numpy array exactly as ``put_array`` would store it."""
    contiguous = np.ascontiguousarray(array)
    payload = contiguous.tobytes()
    return StagedBlob(
        BlobRef(sha256=sha256_hex(payload), length_bytes=len(payload),
                dtype=contiguous.dtype.str,
                shape=tuple(int(dim) for dim in contiguous.shape)),
        payload)


def _pad_to_align(length: int) -> int:
    remainder = length % _ALIGN
    return 0 if remainder == 0 else _ALIGN - remainder


class BlobSidecar:
    """Append-only content-addressed store over one file."""

    def __init__(self, path: Path, *, fsync: bool = True) -> None:
        self._path = path
        self._fsync = fsync
        self._index: dict[str, tuple[int, int]] = {}   # sha -> (offset, length)
        self._mmap: mmap.mmap | None = None
        self._stale_maps: list[mmap.mmap] = []
        self._mapped_bytes = 0
        self._end = 0

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def open(cls, path: Path, *, fsync: bool = True) -> "BlobSidecar":
        """Open (creating if absent), rebuilding the index by scanning."""
        sidecar = cls(path, fsync=fsync)
        if not path.exists():
            with open(path, "wb") as handle:
                handle.write(MAGIC)
                handle.flush()
                if fsync:
                    os.fsync(handle.fileno())
            sidecar._end = len(MAGIC)
            return sidecar
        sidecar._scan()
        return sidecar

    def close(self) -> None:
        """Release mappings. Live views keep their own mapping alive."""
        for mapping in (*self._stale_maps, self._mmap):
            if mapping is None:
                continue
            try:
                mapping.close()
            except BufferError:      # a caller still holds a view
                pass
        self._stale_maps.clear()
        self._mmap = None
        self._mapped_bytes = 0

    def __enter__(self) -> "BlobSidecar":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- reads -------------------------------------------------------------

    def contains(self, sha256: str) -> bool:
        return sha256 in self._index

    def read(self, ref: BlobRef, *, verify: bool = False) -> memoryview:
        """A read-only, mmap-backed view of the referenced bytes."""
        located = self._index.get(ref.sha256)
        if located is None:
            raise BlobError(
                f"blob {ref.sha256} is not in {self._path}: this state is "
                "INCOMPLETE, not corrupt — the sidecar is a cache, so the "
                "remedy is re-derivation (decode again from the scans), "
                "never repair. A record naming a missing address is named "
                "by the store's open check")
        offset, length = located
        if length != ref.length_bytes:
            raise BlobError(
                f"blob {ref.sha256}: ref says {ref.length_bytes} bytes, "
                f"sidecar holds {length}")
        view = self._view(offset, length)
        if verify and sha256_hex(bytes(view)) != ref.sha256:
            raise BlobError(f"blob {ref.sha256}: content does not match address")
        return view

    def read_array(self, ref: BlobRef, *, verify: bool = False) -> np.ndarray:
        """A read-only numpy view of an array blob."""
        if ref.dtype is None or ref.shape is None:
            raise BlobError(f"blob {ref.sha256} is opaque bytes, not an array")
        view = self.read(ref, verify=verify)
        array = np.frombuffer(view, dtype=np.dtype(ref.dtype))
        return array.reshape(ref.shape)

    # -- appends -----------------------------------------------------------

    def put(self, payload: bytes, *, dtype: str | None = None,
            shape: tuple[int, ...] | None = None) -> BlobRef:
        """Append ``payload`` unless already present; return its ref."""
        sha256 = sha256_hex(payload)
        ref = BlobRef(sha256=sha256, length_bytes=len(payload),
                      dtype=dtype, shape=shape)
        if sha256 in self._index:
            return ref
        header = canonical_json_bytes(
            {"sha256": sha256, "length_bytes": len(payload)})
        header_padded = header + b" " * _pad_to_align(len(header))
        frame = (
            len(header_padded).to_bytes(_LEN_FIELD_BYTES, "big")
            + header_padded + payload + b"\x00" * _pad_to_align(len(payload))
        )
        payload_offset = self._end + _LEN_FIELD_BYTES + len(header_padded)
        with open(self._path, "r+b") as handle:
            handle.seek(self._end)
            handle.write(frame)
            handle.flush()
            if self._fsync:
                os.fsync(handle.fileno())
        self._end += len(frame)
        self._index[sha256] = (payload_offset, len(payload))
        return ref

    def put_array(self, array: np.ndarray) -> BlobRef:
        """Append a numpy array as raw C-contiguous bytes."""
        contiguous = np.ascontiguousarray(array)
        return self.put(contiguous.tobytes(), dtype=contiguous.dtype.str,
                        shape=tuple(int(dim) for dim in contiguous.shape))

    # -- internals ---------------------------------------------------------

    def _view(self, offset: int, length: int) -> memoryview:
        if length == 0:
            return memoryview(b"")
        if self._mmap is None or self._mapped_bytes < offset + length:
            self._remap()
        assert self._mmap is not None
        if self._mapped_bytes < offset + length:
            raise BlobError(f"{self._path}: blob range beyond end of file")
        return memoryview(self._mmap)[offset:offset + length].toreadonly()

    def _remap(self) -> None:
        if self._mmap is not None:
            self._stale_maps.append(self._mmap)   # views may still reference it
            self._mmap = None
        size = self._path.stat().st_size
        if size == 0:
            raise BlobError(f"{self._path}: empty sidecar")
        with open(self._path, "rb") as handle:
            self._mmap = mmap.mmap(handle.fileno(), size, access=mmap.ACCESS_READ)
        self._mapped_bytes = size

    def _scan(self) -> None:
        """Rebuild the index; truncate a torn tail to the last good frame.

        Headers are read in place and payloads seeked over, so scan cost
        is O(frames), not O(bytes).
        """
        total = self._path.stat().st_size
        offset = len(MAGIC)
        with open(self._path, "rb") as handle:
            if handle.read(len(MAGIC)) != MAGIC:
                raise BlobError(f"{self._path}: not a holo2 blob sidecar")
            while offset < total:
                raw_len = handle.read(_LEN_FIELD_BYTES)
                if len(raw_len) < _LEN_FIELD_BYTES:
                    break
                header_len = int.from_bytes(raw_len, "big")
                header_start = offset + _LEN_FIELD_BYTES
                header_end = header_start + header_len
                if header_len <= 0 or header_len % _ALIGN != 0 or header_end > total:
                    break
                header = parse_json_bytes(handle.read(header_len).rstrip(b" "))
                if (not isinstance(header, dict)
                        or set(header) != {"sha256", "length_bytes"}):
                    raise BlobError(
                        f"{self._path}: malformed frame header at {offset}")
                length = header["length_bytes"]
                frame_end = header_end + length + _pad_to_align(length)
                if frame_end > total:
                    break
                self._index[header["sha256"]] = (header_end, length)
                handle.seek(frame_end)
                offset = frame_end
        if offset != total:
            with open(self._path, "r+b") as handle:
                handle.truncate(offset)
                handle.flush()
                if self._fsync:
                    os.fsync(handle.fileno())
        self._end = offset

"""Compact, lossless Track-3 persistence for payload evidence.

The durable unit is one ``(source SHA-256, lane, page, tile)`` block. It
stores only the observed payload-slot bitmap, exact little-endian float32
evidence, and uint16 references into a tile-local origin table. K stores one
LLR per observed cell; CMY7 stores six W-relative state scores; CMY8 stores
three marginal LLRs in C/M/Y order. A tile has at most 4096 cells, so a
referenced origin table can never contain more than 4096 entries; uint16 is
therefore lossless rather than a resource policy.

This module contains no decoder policy. Within one physical acquisition,
overlapping E022 windows have already selected one owner by
``(heldout_logloss, patch_id)``. Distinct acquisitions remain distinct
content-addressed components, so they can be scanned separately before a
legal same-lane sum.
"""
from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

import numpy as np

if TYPE_CHECKING:
    from .payload_model import CaptureEvidence, WindowEvidence


_MAGIC = b"holo/e023b/evidence-block/v4\x00"
_COLOR_MAGICS = {
    "cmy7": b"holo/e023b/evidence-block/cmy7-v1\x00",
    "cmy8": b"holo/e023b/evidence-block/cmy8-v1\x00",
}
_MAGICS = {"k": _MAGIC, **_COLOR_MAGICS}
_ARITIES = {"k": 1, "cmy7": 6, "cmy8": 3}
_BITMAP_BYTES = 4096 // 8
_SHA256_BYTES = 32

EvidenceKind = Literal["k", "cmy7", "cmy8"]


def evidence_arity(kind: str) -> int:
    """Return the fixed values-per-cell width of one evidence kind."""
    if not isinstance(kind, str) or kind not in _ARITIES:
        raise ValueError(
            "evidence block: kind must be one of k, cmy7, or cmy8")
    return _ARITIES[kind]


def _identity(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"evidence block: {label} must be non-empty")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"evidence block: {label} contains control characters")
    return value


def _nonnegative(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(
            f"evidence block: {label} must be a non-negative integer")
    return value


def _sha256(value: str, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError(f"evidence block: {label} must be a lowercase SHA-256")
    return value


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _pack_natural(value: int) -> bytes:
    """Canonical unbounded non-negative integer encoding."""
    _nonnegative(value, "natural number")
    size = max(1, (value.bit_length() + 7) // 8)
    return struct.pack("<Q", size) + value.to_bytes(size, "little")


@dataclass(frozen=True, slots=True)
class EvidenceOrigin:
    """Provenance shared by one or more owner cells inside a tile.

    Source, lane, page, and tile axes belong to the enclosing block.
    ``patch_id`` is the historical numeric owner ordinal; ``placement_id``
    remains identity and provenance. Held-out loss and patch ordinal retain
    the qualified within-acquisition winner ordering.
    """

    placement_id: str
    patch_id: int
    heldout_logloss: float
    dependency_certificate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identity(self.placement_id, "origin placement id")
        patch_id = _nonnegative(self.patch_id, "patch id")
        loss = float(self.heldout_logloss)
        if not math.isfinite(loss) or loss < 0.0:
            raise ValueError(
                "evidence block: held-out loss must be finite and non-negative")
        dependencies = tuple(self.dependency_certificate_ids)
        if dependencies != tuple(sorted(set(dependencies))):
            raise ValueError(
                "evidence block: dependency ids must be sorted and unique")
        for identity in dependencies:
            _sha256(identity, "dependency id")
        object.__setattr__(self, "heldout_logloss", loss)
        object.__setattr__(self, "patch_id", patch_id)
        object.__setattr__(self, "dependency_certificate_ids", dependencies)

    @property
    def canonical_key(
        self,
    ) -> tuple[float, int, str, tuple[str, ...]]:
        return (self.heldout_logloss, self.patch_id, self.placement_id,
                self.dependency_certificate_ids)


def _origin_bytes(origin: EvidenceOrigin) -> bytes:
    output = bytearray()
    output.extend(_pack_text(origin.placement_id))
    output.extend(_pack_natural(origin.patch_id))
    output.extend(struct.pack("<d", origin.heldout_logloss))
    output.extend(struct.pack("<Q", len(origin.dependency_certificate_ids)))
    for identity in origin.dependency_certificate_ids:
        output.extend(bytes.fromhex(identity))
    return bytes(output)


def _body_bytes(
    source_sha256: str,
    lane_id: str,
    page: int,
    tile_yx: tuple[int, int],
    observed_bitmap: bytes,
    printed_llr_f32: bytes,
    origin_indices_u16: bytes,
    origins: tuple[EvidenceOrigin, ...],
    kind: str = "k",
) -> bytes:
    evidence_arity(kind)
    output = bytearray(_MAGICS[kind])
    output.extend(bytes.fromhex(source_sha256))
    output.extend(_pack_text(lane_id))
    output.extend(struct.pack("<QQQ", page, *tile_yx))
    output.extend(observed_bitmap)
    output.extend(struct.pack("<H", len(origins)))
    for origin in origins:
        output.extend(_origin_bytes(origin))
    output.extend(printed_llr_f32)
    output.extend(origin_indices_u16)
    return bytes(output)


def _flats(bitmap: bytes) -> np.ndarray:
    bits = np.unpackbits(np.frombuffer(bitmap, np.uint8), bitorder="little")
    return np.flatnonzero(bits).astype(np.uint16)


@dataclass(frozen=True, slots=True)
class EvidenceBlock:
    """One immutable, content-addressed tile evidence block."""

    source_sha256: str
    lane_id: str
    page: int
    tile_yx: tuple[int, int]
    observed_bitmap: bytes
    printed_llr_f32: bytes
    origin_indices_u16: bytes
    origins: tuple[EvidenceOrigin, ...]
    content_sha256: bytes
    kind: EvidenceKind = "k"

    def __post_init__(self) -> None:
        arity = evidence_arity(self.kind)
        _sha256(self.source_sha256, "source SHA-256")
        _identity(self.lane_id, "lane id")
        page = _nonnegative(self.page, "page")
        if (not isinstance(self.tile_yx, tuple) or len(self.tile_yx) != 2):
            raise ValueError("evidence block: tile coordinate must have two axes")
        tile_yx = tuple(
            _nonnegative(value, "tile coordinate") for value in self.tile_yx)
        if (not isinstance(self.observed_bitmap, bytes)
                or len(self.observed_bitmap) != _BITMAP_BYTES):
            raise ValueError("evidence block: bitmap must contain 4096 bits")
        n_observed = sum(byte.bit_count() for byte in self.observed_bitmap)
        if n_observed == 0:
            raise ValueError("evidence block: an empty tile is not persisted")
        if (not isinstance(self.printed_llr_f32, bytes)
                or len(self.printed_llr_f32) != n_observed * arity * 4):
            raise ValueError(
                "evidence block: float32 cell tensor length disagrees")
        llr = np.frombuffer(self.printed_llr_f32, dtype="<f4")
        if not np.isfinite(llr).all():
            raise ValueError("evidence block: LLRs must be finite")
        if (not isinstance(self.origin_indices_u16, bytes)
                or len(self.origin_indices_u16) != n_observed * 2):
            raise ValueError("evidence block: origin-index vector disagrees")
        origins = tuple(self.origins)
        if (not origins or len(origins) > n_observed
                or len(origins) > 4096):
            raise ValueError("evidence block: origin table is not tile-local")
        if any(not isinstance(row, EvidenceOrigin) for row in origins):
            raise TypeError("evidence block: origin table contains foreign data")
        if tuple(sorted(origins, key=lambda row: row.canonical_key)) != origins:
            raise ValueError("evidence block: origin table is not canonical")
        if len(set(origins)) != len(origins):
            raise ValueError("evidence block: origin table repeats an origin")
        placements = tuple(row.placement_id for row in origins)
        if len(placements) != len(set(placements)):
            raise ValueError(
                "evidence block: one placement has conflicting provenance")
        indices = np.frombuffer(self.origin_indices_u16, dtype="<u2")
        if int(indices.max(initial=0)) >= len(origins):
            raise ValueError("evidence block: origin index is out of range")
        if set(indices.tolist()) != set(range(len(origins))):
            raise ValueError("evidence block: origin table contains an unused row")
        if (not isinstance(self.content_sha256, bytes)
                or len(self.content_sha256) != _SHA256_BYTES):
            raise ValueError("evidence block: content SHA-256 must be 32 bytes")
        # Mint-once (rework Phase 3.1): the digest is computed exactly once
        # at the authoritative construction sites — ``_block_from_encoded_
        # rows`` hashes the body it just serialized, and the durable-boundary
        # ``from_bytes`` verifies body-vs-trailer before parsing.  Interior
        # reconstruction paths pass the minted digest through trusted.
        object.__setattr__(self, "page", page)
        object.__setattr__(self, "tile_yx", tile_yx)
        object.__setattr__(self, "origins", origins)

    @property
    def address(self) -> tuple[int, int, int]:
        return self.page, *self.tile_yx

    @property
    def block_id(self) -> str:
        """Lowercase content address used by durable manifests."""
        return self.content_sha256.hex()

    @property
    def key(self) -> tuple[str, str, int, int, int]:
        return self.source_sha256, self.lane_id, *self.address

    @property
    def n_observed(self) -> int:
        return sum(byte.bit_count() for byte in self.observed_bitmap)

    @property
    def arity(self) -> int:
        """Number of stored float32 evidence values per observed cell."""
        return evidence_arity(self.kind)

    def observed_flat(self) -> np.ndarray:
        """Sorted local flat slots, as a small immutable uint16 vector."""
        values = _flats(self.observed_bitmap)
        return np.frombuffer(values.tobytes(), dtype="<u2")

    def printed_llr(self) -> np.ndarray:
        values = np.frombuffer(self.printed_llr_f32, dtype="<f4")
        if self.arity == 1:
            return values
        return values.reshape(self.n_observed, self.arity)

    def observed_cells(self) -> np.ndarray:
        """Immutable ``(64,64)`` mask independent of evidence magnitudes."""
        values = np.unpackbits(
            np.frombuffer(self.observed_bitmap, np.uint8), bitorder="little",
        ).astype(np.bool_)
        return np.frombuffer(values.tobytes(), dtype=np.bool_).reshape(64, 64)

    def dependency_certificate_ids(self) -> tuple[str, ...]:
        return tuple(sorted({
            identity for origin in self.origins
            for identity in origin.dependency_certificate_ids
        }))

    def cell_tensor(self) -> np.ndarray:
        """Materialize this tile only as ``(64,64[,arity])`` float32."""
        if self.arity == 1:
            cells = np.zeros(4096, np.float32)
            cells[self.observed_flat()] = self.printed_llr()
            shape = (64, 64)
        else:
            cells = np.zeros((4096, self.arity), np.float32)
            cells[self.observed_flat(), :] = self.printed_llr()
            shape = (64, 64, self.arity)
        return np.frombuffer(cells.tobytes(), dtype="<f4").reshape(shape)

    def to_bytes(self) -> bytes:
        body = _body_bytes(
            self.source_sha256, self.lane_id, self.page, self.tile_yx,
            self.observed_bitmap, self.printed_llr_f32,
            self.origin_indices_u16, self.origins, self.kind)
        return body + self.content_sha256

    @classmethod
    def from_bytes(cls, data: bytes) -> "EvidenceBlock":
        if (not isinstance(data, bytes)
                or len(data) < min(map(len, _MAGICS.values())) + 32):
            raise ValueError("evidence block: truncated binary record")
        body, content_sha256 = data[:-_SHA256_BYTES], data[-_SHA256_BYTES:]
        if hashlib.sha256(body).digest() != content_sha256:
            raise ValueError("evidence block: content SHA-256 mismatch")
        kinds = tuple(
            kind for kind, magic in _MAGICS.items() if body.startswith(magic))
        if len(kinds) != 1:
            raise ValueError("evidence block: unknown binary format")
        kind = kinds[0]
        magic = _MAGICS[kind]
        reader = _Reader(body)
        if reader.read(len(magic)) != magic:
            raise AssertionError("evidence block: internal magic mismatch")
        source_sha256 = reader.read(_SHA256_BYTES).hex()
        lane_id = reader.text()
        page, tile_y, tile_x = reader.unpack("<QQQ")
        bitmap = reader.read(_BITMAP_BYTES)
        n_observed = sum(byte.bit_count() for byte in bitmap)
        (n_origins,) = reader.unpack("<H")
        origins: list[EvidenceOrigin] = []
        for _ in range(n_origins):
            placement_id = reader.text()
            patch_id = reader.natural()
            (loss,) = reader.unpack("<d")
            (n_dependencies,) = reader.unpack("<Q")
            dependencies = tuple(
                reader.read(_SHA256_BYTES).hex()
                for _ in range(n_dependencies))
            origins.append(EvidenceOrigin(
                placement_id, patch_id, loss, dependencies))
        llr = reader.read(n_observed * evidence_arity(kind) * 4)
        indices = reader.read(n_observed * 2)
        reader.finish()
        return cls(
            source_sha256, lane_id, int(page),
            (int(tile_y), int(tile_x)), bitmap, llr, indices,
            tuple(origins), content_sha256, kind)


class _Reader:
    """Bounds-checked parser; lengths are constrained only by input size."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, size: int) -> bytes:
        if size < 0 or size > len(self.data) - self.offset:
            raise ValueError("evidence block: truncated binary field")
        output = self.data[self.offset:self.offset + size]
        self.offset += size
        return output

    def unpack(self, code: str) -> tuple[int | float, ...]:
        return struct.unpack(code, self.read(struct.calcsize(code)))

    def text(self) -> str:
        (size,) = self.unpack("<Q")
        try:
            return self.read(int(size)).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("evidence block: invalid UTF-8 identity") from exc

    def natural(self) -> int:
        (size,) = self.unpack("<Q")
        encoded = self.read(int(size))
        if not encoded or (len(encoded) > 1 and encoded[-1] == 0):
            raise ValueError("evidence block: non-canonical natural number")
        return int.from_bytes(encoded, "little")

    def finish(self) -> None:
        if self.offset != len(self.data):
            raise ValueError("evidence block: trailing binary data")


def _block_from_rows(
    source_sha256: str,
    lane_id: str,
    page: int,
    tile_yx: tuple[int, int],
    rows: Iterable[tuple[int, bytes, EvidenceOrigin]],
) -> EvidenceBlock:
    return _block_from_encoded_rows(
        source_sha256, lane_id, page, tile_yx, rows, kind="k")


def block_from_rows(
    source_sha256: str,
    lane_id: str,
    page: int,
    tile_yx: tuple[int, int],
    rows: Iterable[tuple[int, object, EvidenceOrigin]],
    *,
    kind: EvidenceKind,
) -> EvidenceBlock:
    """Build one block from owned cell vectors.

    Each row is ``(local_flat, values, origin)``. ``values`` must have the
    exact fixed shape ``(arity,)`` for ``kind``. The public builder converts
    finite real values once to canonical little-endian float32. The private
    K builder remains raw-byte based so its established serialized form is
    unchanged.
    """
    arity = evidence_arity(kind)
    encoded: list[tuple[int, bytes, EvidenceOrigin]] = []
    for flat, values, origin in rows:
        array = np.asarray(values)
        if array.shape != (arity,) or array.dtype.kind not in "buif":
            raise ValueError(
                f"evidence block: {kind} row values must have real shape "
                f"({arity},)")
        with np.errstate(over="ignore", invalid="ignore"):
            canonical = array.astype("<f4", copy=False)
        if not np.isfinite(canonical).all():
            raise ValueError(
                "evidence block: row values must be finite float32")
        encoded.append((flat, canonical.tobytes(), origin))
    return _block_from_encoded_rows(
        source_sha256, lane_id, page, tile_yx, encoded, kind=kind)


def _block_from_encoded_rows(
    source_sha256: str,
    lane_id: str,
    page: int,
    tile_yx: tuple[int, int],
    rows: Iterable[tuple[int, bytes, EvidenceOrigin]],
    *,
    kind: EvidenceKind,
) -> EvidenceBlock:
    """Private common constructor after exact per-row encoding."""
    arity = evidence_arity(kind)
    _sha256(source_sha256, "source SHA-256")
    _identity(lane_id, "lane id")
    selected = tuple(sorted(rows, key=lambda row: row[0]))
    if (not selected or any(type(flat) is not int or not 0 <= flat < 4096
                            for flat, _llr, _origin in selected)
            or any(right[0] == left[0]
                   for left, right in zip(selected, selected[1:]))):
        raise ValueError("evidence block: rows need unique local tile slots")
    for _flat, llr, origin in selected:
        if not isinstance(llr, bytes) or len(llr) != arity * 4:
            raise ValueError(
                "evidence block: one cell vector has the wrong byte width")
        if not np.isfinite(np.frombuffer(llr, dtype="<f4")).all():
            raise ValueError("evidence block: one cell vector is not finite")
        if not isinstance(origin, EvidenceOrigin):
            raise TypeError("evidence block: row origin is invalid")
    origins = tuple(sorted(
        {row[2] for row in selected}, key=lambda row: row.canonical_key))
    origin_index = {origin: index for index, origin in enumerate(origins)}
    bitmap = bytearray(_BITMAP_BYTES)
    for flat, _llr, _origin in selected:
        bitmap[flat // 8] |= 1 << (flat % 8)
    values = b"".join(row[1] for row in selected)
    indices = b"".join(
        struct.pack("<H", origin_index[row[2]]) for row in selected)
    body = _body_bytes(
        source_sha256, lane_id, page, tile_yx, bytes(bitmap), values,
        indices, origins, kind)
    return EvidenceBlock(
        source_sha256, lane_id, page, tile_yx, bytes(bitmap), values,
        indices, origins, hashlib.sha256(body).digest(), kind)


def validate_block_supersession(old: EvidenceBlock, new: EvidenceBlock) -> None:
    """Refuse anything but a v0.33 extension-only mop-up supersession.

    A mop-up level may replace a live block at its evidence-lane key only
    when the replacement observes a strict superset of the committed cells
    and agrees exactly — float32 evidence values and full origin rows — on
    every cell the old block observed.  Committed cells are never revised.
    """
    if old.key != new.key or old.kind != new.kind:
        raise ValueError(
            "block supersession must keep the evidence key and kind")
    old_flat = old.observed_flat()
    new_flat = new.observed_flat()
    if len(new_flat) <= len(old_flat):
        raise ValueError(
            "superseding block must extend the committed cell set")
    positions = np.searchsorted(new_flat, old_flat)
    if (int(positions.max(initial=0)) >= len(new_flat)
            or not np.array_equal(new_flat[positions], old_flat)):
        raise ValueError(
            "superseding block does not observe every committed cell")
    arity = old.arity
    old_llr = np.frombuffer(old.printed_llr_f32, "<f4").reshape(-1, arity)
    new_llr = np.frombuffer(new.printed_llr_f32, "<f4").reshape(-1, arity)
    if not np.array_equal(new_llr[positions], old_llr):
        raise ValueError(
            "superseding block revises committed evidence values")
    old_rows = np.frombuffer(old.origin_indices_u16, "<u2").tolist()
    new_rows = np.frombuffer(new.origin_indices_u16, "<u2")[positions].tolist()
    for old_row, new_row in zip(old_rows, new_rows, strict=True):
        if old.origins[old_row] != new.origins[new_row]:
            raise ValueError(
                "superseding block revises committed provenance")


class SupersessionDrops(NamedTuple):
    """D5 mop-up drop tally (ruling 2026-08-02, replacing the v0.36
    byte-inequality canary; docs/CANARY-D5-DISAGREEMENTS.md).

    ``dropped`` counts EVERY fresh mop-up observation at a committed
    cell (the extension-only supersession discards them all; expected
    geometry, not an alarm).  ``winner_flips`` counts the dropped cells
    whose implied cell decision differs from the committed owner's —
    the two-view consistency canary (:func:`winner_codes`).  Advice
    only, never a gate, never durable per-cell data.
    """

    dropped: int
    winner_flips: int

    def add(self, other: "SupersessionDrops") -> "SupersessionDrops":
        return SupersessionDrops(
            self.dropped + other.dropped,
            self.winner_flips + other.winner_flips)


def winner_codes(kind: EvidenceKind, values: np.ndarray) -> np.ndarray:
    """The implied per-cell decision behind one evidence vector.

    One int64 code per row of the ``(n, arity)`` float32 matrix; two
    observations of the same printed cell "agree" exactly when their
    codes are equal:

    - ``k`` (arity 1): the LLR sign category (-1/0/+1) — the implied
      bit decision.
    - ``cmy8`` (arity 3): the per-plane sign-category pattern packed
      base-3 — the implied (C, M, Y) bit triple.
    - ``cmy7`` (arity 6): the implied 7-state winner under the
      W-relative convention (``color_tile.cmy7_demap_payload``: six
      scores relative to state W) — 0 when no score is positive
      (W wins), else ``argmax + 1``.
    """
    arity = evidence_arity(kind)
    matrix = np.asarray(values, np.float32).reshape(-1, arity)
    if kind == "k":
        return np.sign(matrix[:, 0]).astype(np.int64)
    if kind == "cmy8":
        digits = (np.sign(matrix) + 1).astype(np.int64)
        return digits @ (3 ** np.arange(arity, dtype=np.int64))
    best = matrix.max(axis=1)
    return np.where(
        best <= 0.0, 0, matrix.argmax(axis=1).astype(np.int64) + 1)


def supersede_with_committed(
    new_block: EvidenceBlock, committed: EvidenceBlock,
) -> tuple[EvidenceBlock | None, SupersessionDrops]:
    """Materialize the v0.33 D5 superset for one colliding evidence key.

    Committed cells carry over verbatim — bytes, values, and origin rows
    untouched (committed evidence is never revised; base owners win any
    cell collision) — and the new block contributes only its strictly
    novel cells.  The block is None when nothing novel remains, in which
    case the caller must keep the committed block and emit nothing.

    The second value tallies the dropped fresh observations at committed
    cells and, among them, the WINNER FLIPS — cells where the mop-up
    window's implied decision differs from the committed owner's
    (:class:`SupersessionDrops`).  Dropping is expected geometry (a
    mop-up window is never the committed owner, so byte-level agreement
    is structurally impossible — the finding record); the flip rate is
    the misplaced-window / physical-damage canary.
    """
    if new_block.key != committed.key or new_block.kind != committed.kind:
        raise ValueError("supersession merge must keep key and kind")
    arity = committed.arity
    stride = arity * 4
    rows: list[tuple[int, bytes, EvidenceOrigin]] = []
    committed_positions: dict[int, int] = {}
    committed_idx = np.frombuffer(committed.origin_indices_u16, "<u2")
    committed_codes = winner_codes(
        committed.kind,
        np.frombuffer(committed.printed_llr_f32, "<f4"))
    for position, flat in enumerate(committed.observed_flat().tolist()):
        value = committed.printed_llr_f32[
            position * stride:(position + 1) * stride]
        origin = committed.origins[int(committed_idx[position])]
        rows.append((int(flat), value, origin))
        committed_positions[int(flat)] = position
    new_idx = np.frombuffer(new_block.origin_indices_u16, "<u2")
    new_codes = winner_codes(
        new_block.kind, np.frombuffer(new_block.printed_llr_f32, "<f4"))
    novel = 0
    dropped = 0
    winner_flips = 0
    for position, flat in enumerate(new_block.observed_flat().tolist()):
        prior = committed_positions.get(int(flat))
        if prior is not None:
            dropped += 1
            if int(new_codes[position]) != int(committed_codes[prior]):
                winner_flips += 1
            continue
        value = new_block.printed_llr_f32[
            position * stride:(position + 1) * stride]
        origin = new_block.origins[int(new_idx[position])]
        rows.append((int(flat), value, origin))
        novel += 1
    drops = SupersessionDrops(dropped, winner_flips)
    if not novel:
        return None, drops
    return _block_from_encoded_rows(
        committed.source_sha256, committed.lane_id, committed.page,
        committed.tile_yx, rows,
        kind=committed.kind), drops


def apply_mopup_supersession(
    new_blocks: Iterable[EvidenceBlock],
    committed: Iterable[EvidenceBlock],
) -> tuple[tuple[EvidenceBlock, ...], SupersessionDrops]:
    """Rewrite an M-level's fresh blocks into legal D5 supersessions.

    A fresh block whose key collides with a committed one becomes the
    committed-verbatim-plus-novel superset (or vanishes when nothing is
    novel); non-colliding blocks pass through untouched.  The second
    value aggregates the per-collision drop tallies
    (see :func:`supersede_with_committed`).
    """
    committed_by_key = {row.key: row for row in committed}
    out: list[EvidenceBlock] = []
    drops = SupersessionDrops(0, 0)
    for block in new_blocks:
        prior = committed_by_key.get(block.key)
        if prior is None:
            out.append(block)
            continue
        merged, block_drops = supersede_with_committed(block, prior)
        drops = drops.add(block_drops)
        if merged is not None:
            out.append(merged)
    return tuple(out), drops


def merge_block_sets(*sets: Iterable[EvidenceBlock]) -> tuple[EvidenceBlock, ...]:
    """Union distinct source blocks and reject one key with two contents."""
    blocks: dict[tuple[str, str, int, int, int], EvidenceBlock] = {}
    for values in sets:
        for block in values:
            if not isinstance(block, EvidenceBlock):
                raise TypeError("evidence block set contains foreign data")
            previous = blocks.setdefault(block.key, block)
            if previous != block:
                raise ValueError(
                    "evidence block: one source key has conflicting contents")
    return tuple(blocks[key] for key in sorted(blocks))


def blocks_by_address(
    blocks: Iterable[EvidenceBlock],
    *,
    lane_id: str | None = None,
) -> dict[tuple[int, int, int], tuple[EvidenceBlock, ...]]:
    """Index tile components once while preserving source iteration order.

    The returned tuples reject duplicate (source, lane) components per tile.
    Callers which visit many addresses can build this index once instead of
    rescanning a lane frontier for every tile.
    """
    if lane_id is not None:
        _identity(lane_id, "lane id")
    grouped: dict[tuple[int, int, int], list[EvidenceBlock]] = {}
    source_keys: dict[tuple[int, int, int], set[tuple[str, str]]] = {}
    for row in blocks:
        if not isinstance(row, EvidenceBlock):
            raise TypeError(
                "evidence block: address index contains foreign data")
        if lane_id is not None and row.lane_id != lane_id:
            continue
        source_key = (row.source_sha256, row.lane_id)
        seen = source_keys.setdefault(row.address, set())
        if source_key in seen:
            raise ValueError(
                "evidence block: duplicate source component for tile")
        seen.add(source_key)
        grouped.setdefault(row.address, []).append(row)
    return {
        address: tuple(rows)
        for address, rows in grouped.items()
    }


@dataclass(frozen=True, slots=True)
class TileAttemptView:
    """Exact transient block provenance and vector for one tile attempt."""

    components: tuple[EvidenceBlock, ...]
    llr_cells_f64: np.ndarray

    def __post_init__(self) -> None:
        components = tuple(self.components)
        if not components:
            raise ValueError("evidence block: a tile attempt needs evidence")
        if any(not isinstance(row, EvidenceBlock) for row in components):
            raise TypeError("evidence block: tile attempt contains foreign data")
        canonical = tuple(sorted(
            components, key=lambda row: (row.source_sha256, row.block_id)))
        if components != canonical:
            raise ValueError("evidence block: tile components are not canonical")
        address = components[0].address
        lane_id = components[0].lane_id
        if any(row.address != address or row.lane_id != lane_id
               for row in components):
            raise ValueError("evidence block: tile components disagree on axes")
        kind = components[0].kind
        if any(row.kind != kind for row in components):
            raise ValueError("evidence block: tile components mix evidence kinds")
        sources = tuple(row.source_sha256 for row in components)
        if len(sources) != len(set(sources)):
            raise ValueError("evidence block: duplicate source components")
        llr = np.asarray(self.llr_cells_f64, np.float64)
        expected_shape = (
            (64, 64) if components[0].arity == 1
            else (64, 64, components[0].arity)
        )
        if llr.shape != expected_shape or not np.isfinite(llr).all():
            raise ValueError(
                "evidence block: tile attempt tensor has wrong shape or "
                "non-finite values")
        # Mint-once (rework Phase 3.1): the component sum is computed once
        # by :func:`tile_attempt_view`, the authoritative construction site,
        # and passed through trusted; no interior re-summation.
        object.__setattr__(self, "components", components)
        object.__setattr__(
            self, "llr_cells_f64",
            np.frombuffer(llr.tobytes(), dtype="<f8").reshape(expected_shape))

    @property
    def address(self) -> tuple[int, int, int]:
        return self.components[0].address

    @property
    def lane_id(self) -> str:
        return self.components[0].lane_id

    @property
    def kind(self) -> EvidenceKind:
        return self.components[0].kind

    @property
    def arity(self) -> int:
        return self.components[0].arity

    def observed_cells(self) -> np.ndarray:
        """Immutable union of component observation masks."""
        observed = np.zeros((64, 64), np.bool_)
        for row in self.components:
            observed |= row.observed_cells()
        return np.frombuffer(
            observed.tobytes(), dtype=np.bool_).reshape(64, 64)

    @property
    def component_block_ids(self) -> tuple[str, ...]:
        return tuple(row.block_id for row in self.components)

    @property
    def source_sha256s(self) -> tuple[str, ...]:
        return tuple(row.source_sha256 for row in self.components)

    @property
    def dependency_certificate_ids(self) -> tuple[str, ...]:
        return tuple(sorted({
            identity for row in self.components
            for identity in row.dependency_certificate_ids()
        }))


def tile_attempt_view(components: Iterable[EvidenceBlock]) -> TileAttemptView:
    """Build one canonical scan/union view without page materialization."""
    rows = tuple(sorted(
        components, key=lambda row: (
            row.source_sha256, row.block_id)
        if isinstance(row, EvidenceBlock) else ("", "")))
    if not rows:
        raise ValueError("evidence block: a tile attempt needs evidence")
    if any(not isinstance(row, EvidenceBlock) for row in rows):
        raise TypeError("evidence block: tile attempt contains foreign data")
    address = rows[0].address
    lane_id = rows[0].lane_id
    if any(row.address != address or row.lane_id != lane_id for row in rows):
        raise ValueError("evidence block: tile components disagree on axes")
    kind = rows[0].kind
    if any(row.kind != kind for row in rows):
        raise ValueError("evidence block: tile components mix evidence kinds")
    sources = tuple(row.source_sha256 for row in rows)
    if len(sources) != len(set(sources)):
        raise ValueError("evidence block: duplicate source components")
    shape = (64, 64) if rows[0].arity == 1 else (64, 64, rows[0].arity)
    combined = np.zeros(shape, np.float64)
    for row in rows:
        combined += row.cell_tensor()
    return TileAttemptView(rows, combined)


def _origin_for_window(window: WindowEvidence,
                       dependencies: Mapping[str, tuple[str, ...]]
                       ) -> EvidenceOrigin:
    if window.heldout_logloss is None:
        raise ValueError("evidence block: owner window has no held-out loss")
    return EvidenceOrigin(
        window.placement_id, int(window.patch_id),
        float(window.heldout_logloss),
        tuple(sorted(set(dependencies.get(window.placement_id, ())))))


class OwnedPageRows(NamedTuple):
    """One owned page's aligned cell rows for block conversion."""

    page: int
    cells_yx: np.ndarray        # (N, 2) integer page cells
    values: np.ndarray          # (N, arity) float32 evidence values
    window_indices: np.ndarray  # (N,) indices into the origins tuple


def blocks_from_owner_pages(
    source_sha256: str,
    lane_id: str,
    pages: Iterable[OwnedPageRows],
    origins: tuple[EvidenceOrigin | None, ...],
    *,
    kind: EvidenceKind,
) -> tuple[EvidenceBlock, ...]:
    """Stream-generic frontier→block conversion over owned page rows.

    ``origins`` aligns with each row's window indices; slots that no owner
    row references may be ``None`` (refused-window bookkeeping).  The
    complete page value tensor is encoded once as canonical little-endian
    float32 and sliced per row — byte-identical to the historical
    per-element ``astype('<f4').tobytes()`` encodings of both codecs.
    Owner provenance is validated where the frontier is constructed
    (mint-once); this converter only serializes it.
    """
    arity = evidence_arity(kind)
    output: list[EvidenceBlock] = []
    for page, cells_yx, values, window_indices in pages:
        cells = np.asarray(cells_yx, np.int64)
        if cells.shape[0] == 0:
            continue
        value_rows = np.ascontiguousarray(values, dtype="<f4")
        if value_rows.shape != (cells.shape[0], arity):
            raise ValueError(
                "evidence block: owned value tensor shape disagrees")
        encoded = value_rows.tobytes()
        stride = arity * 4
        flats = (cells[:, 0] % 64) * 64 + cells[:, 1] % 64
        tile_y = cells[:, 0] // 64
        tile_x = cells[:, 1] // 64
        page_tiles_x = int(tile_x.max()) + 1
        tile_codes = tile_y * page_tiles_x + tile_x
        order = np.argsort(tile_codes, kind="stable")
        ordered_codes = tile_codes[order]
        starts = np.flatnonzero(np.concatenate((
            np.asarray((True,)),
            ordered_codes[1:] != ordered_codes[:-1],
        )))
        stops = np.concatenate(
            (starts[1:], np.asarray((order.size,))))
        for start, stop in zip(starts, stops, strict=True):
            positions = order[start:stop]
            ty = int(tile_y[positions[0]])
            tx = int(tile_x[positions[0]])
            output.append(_block_from_encoded_rows(
                source_sha256,
                lane_id,
                int(page),
                (ty, tx),
                (
                    (
                        int(flats[position]),
                        encoded[position * stride:(position + 1) * stride],
                        origins[int(window_indices[position])],
                    )
                    for position in positions
                ),
                kind=kind,
            ))
    return tuple(output)


def blocks_from_frontier(
    frontier: CaptureEvidence,
    dependency_certificate_ids: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[EvidenceBlock, ...]:
    """Convert one frozen physical acquisition into exact tile components."""
    dependencies = ({} if dependency_certificate_ids is None
                    else dependency_certificate_ids)
    # The frozen ledger legally retains refused windows (accepted=False,
    # no held-out loss) alongside the owners; CaptureEvidence pins that
    # owner rows reference accepted windows only.  Mint origins for
    # referenced owners alone — an unreferenced ledger row is refusal
    # bookkeeping, not provenance, and building its origin crashed the
    # first real capture that retained a starved-window refusal
    # (2026-08-02).
    referenced = np.zeros(len(frontier.windows), np.bool_)
    for page in frontier.pages:
        if page.window_indices.size:
            referenced[page.window_indices.astype(np.int64)] = True
    origins = tuple(
        _origin_for_window(window, dependencies)
        if referenced[index] else None
        for index, window in enumerate(frontier.windows)
    )
    return blocks_from_owner_pages(
        frontier.source.source_sha256,
        frontier.lane_id,
        (
            OwnedPageRows(
                page.page,
                page.cells_yx,
                page.printed_llr.reshape(-1, 1),
                page.window_indices,
            )
            for page in frontier.pages
        ),
        origins,
        kind="k",
    )


__all__ = [
    "EvidenceBlock", "EvidenceKind", "EvidenceOrigin",
    "OwnedPageRows",
    "TileAttemptView", "block_from_rows", "blocks_by_address",
    "blocks_from_frontier", "blocks_from_owner_pages", "evidence_arity",
    "merge_block_sets",
    "tile_attempt_view",
]

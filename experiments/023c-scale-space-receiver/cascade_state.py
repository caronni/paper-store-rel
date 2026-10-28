"""Persistent state contract for the E023c coarse-to-fine receiver.

This module deliberately contains no orchestration code and imports neither
the E023c runner nor an E021/E022/E023b implementation.  The runner may attach
those implementations' immutable products to ``artifacts`` and complete
per-lane decoder sessions to ``lane_sessions``.  The state layer treats such
objects as opaque, but hashes their semantic Python state recursively.

The central boundary is intentionally strict:

* levels and their checkpoints are ordered barriers;
* views of one capture live in independent decoder lanes;
* only CRC-certified payloads enter ``certificate_union``;
* every attempt records its numerical evidence and certificate dependencies;
* early stopping is explicit -- unvisited levels are marked
  ``skipped_volume_verified`` rather than silently omitted;
* semantic digests exclude only observer diagnostics and wall-clock timing.

The schema is a clean E023c v1.  It is not compatible with the former
four-lane E023c experiment or with an E023b state pickle.
"""
from __future__ import annotations

import hashlib
import math
import os
import pickle
import re
import struct
import tempfile
from dataclasses import dataclass, field, fields, is_dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Mapping

import numpy as np


STATE_MAGIC = "paperholo/e023c-cascade-state"
STATE_VERSION = 1
ALGORITHM_ID = "e023c-scale-space-cascade-v1"
EVIDENCE_POLICY = (
    "independent-capture/correlated-scale-lanes/level-barrier/"
    "certificate-union-v1"
)

TileKey = tuple[int, int, int]
PilotTileKey = tuple[int, int, int]

LEVEL_STATUSES = frozenset({
    "pending", "in_progress", "complete", "skipped_volume_verified",
    "failed",
})
CAPTURE_STATUSES = frozenset({
    "pending", "in_progress", "exhausted", "early_stopped",
    "skipped_volume_verified", "failed",
})
SESSION_STATUSES = frozenset({"open", "early_stopped", "exhausted", "failed"})
COMPLETION_STATUSES = frozenset({
    "not_configured", "insufficient", "volume_verified", "hash_mismatch",
})
ATTEMPT_STATES = frozenset({
    "unobserved", "below_attempt_floor", "attempted_failed", "certified",
    "degenerate",
})
CHECKPOINT_STAGES = (
    "level_open",
    "e021_complete",
    "e022_complete",
    "pilot_level_final",
    "payload_owner_frozen",
    "ldpc_complete",
    "level_complete",
    "fountain_check",
)
_CHECKPOINT_RANK = {name: index for index, name in enumerate(CHECKPOINT_STAGES)}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")


def _hash_parts(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def _is_nonsemantic_name(name: object) -> bool:
    """Names reserved for observer-only or timing data.

    Counts and quality statistics remain semantic.  Only actual clock data and
    diagnostic rendering state are ignored.
    """
    value = str(name).lower()
    # ``diagnostics`` is deliberately *not* excluded by name.  E021/E022 use
    # that field for replay substrate (notably SearchResult.window_audit,
    # which supplies the bounded runner-up poses consumed by the next scale).
    # Observer-only diagnostics in this schema are explicitly marked with
    # dataclass metadata ``semantic=False`` instead.
    if value in {
        "timing", "timings", "diag", "observer", "observers",
        "observer_state",
    }:
        return True
    if value.startswith(("diag_", "observer_", "timing_")):
        return True
    return bool(re.search(
        r"(?:^|_)(?:elapsed|wall|cpu|duration|runtime)(?:_s|_seconds)?$",
        value,
    ))


def _sort_token(value: object) -> tuple[str, str]:
    return type(value).__qualname__, repr(value)


def _canonical_update(digest, value: object, *, _seen: set[int] | None = None
                      ) -> None:
    """Hash an exact, type-tagged semantic representation.

    The generic ``__dict__`` branch is what permits the cascade to retain an
    E023b ``ReceiverSession`` without importing its class.  Cycles are refused
    rather than assigned process-dependent identities.
    """
    if _seen is None:
        _seen = set()
    if value is None:
        digest.update(b"N")
    elif isinstance(value, (bool, np.bool_)):
        digest.update(b"B1" if bool(value) else b"B0")
    elif isinstance(value, (int, np.integer)):
        payload = str(int(value)).encode("ascii")
        digest.update(b"I" + len(payload).to_bytes(8, "big") + payload)
    elif isinstance(value, (float, np.floating)):
        digest.update(b"F" + struct.pack(">d", float(value)))
    elif isinstance(value, bytes):
        digest.update(b"Y" + len(value).to_bytes(8, "big") + value)
    elif isinstance(value, (str, Path)):
        payload = str(value).encode("utf-8")
        digest.update(b"S" + len(payload).to_bytes(8, "big") + payload)
    elif isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        _canonical_update(
            digest, (array.dtype.str, tuple(array.shape)), _seen=_seen)
        digest.update(b"A" + array.nbytes.to_bytes(8, "big"))
        digest.update(memoryview(array).cast("B"))
    elif isinstance(value, np.generic):
        _canonical_update(digest, value.item(), _seen=_seen)
    elif is_dataclass(value):
        identity = id(value)
        if identity in _seen:
            raise TypeError("cyclic dataclass in authoritative state")
        _seen.add(identity)
        try:
            digest.update(b"D")
            _canonical_update(
                digest,
                f"{type(value).__module__}.{type(value).__qualname__}",
                _seen=_seen,
            )
            selected = [
                row for row in fields(value)
                if row.metadata.get("semantic", True)
                and not _is_nonsemantic_name(row.name)
            ]
            _canonical_update(digest, len(selected), _seen=_seen)
            for row in selected:
                _canonical_update(digest, row.name, _seen=_seen)
                _canonical_update(digest, getattr(value, row.name), _seen=_seen)
        finally:
            _seen.remove(identity)
    elif isinstance(value, Mapping):
        identity = id(value)
        if identity in _seen:
            raise TypeError("cyclic mapping in authoritative state")
        _seen.add(identity)
        try:
            selected = [
                (key, row) for key, row in value.items()
                if not _is_nonsemantic_name(key)
            ]
            selected.sort(key=lambda item: _sort_token(item[0]))
            digest.update(b"M")
            _canonical_update(digest, len(selected), _seen=_seen)
            for key, row in selected:
                _canonical_update(digest, key, _seen=_seen)
                _canonical_update(digest, row, _seen=_seen)
        finally:
            _seen.remove(identity)
    elif isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in _seen:
            raise TypeError("cyclic sequence in authoritative state")
        _seen.add(identity)
        try:
            digest.update(b"L" if isinstance(value, list) else b"T")
            _canonical_update(digest, len(value), _seen=_seen)
            for row in value:
                _canonical_update(digest, row, _seen=_seen)
        finally:
            _seen.remove(identity)
    elif isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in _seen:
            raise TypeError("cyclic set in authoritative state")
        _seen.add(identity)
        try:
            digest.update(b"E")
            ordered = sorted(value, key=_sort_token)
            _canonical_update(digest, len(ordered), _seen=_seen)
            for row in ordered:
                _canonical_update(digest, row, _seen=_seen)
        finally:
            _seen.remove(identity)
    elif hasattr(value, "__dict__"):
        identity = id(value)
        if identity in _seen:
            raise TypeError("cyclic object in authoritative state")
        _seen.add(identity)
        try:
            digest.update(b"O")
            _canonical_update(
                digest,
                f"{type(value).__module__}.{type(value).__qualname__}",
                _seen=_seen,
            )
            state = {
                key: row for key, row in vars(value).items()
                if key not in {"_masks", "_cache", "_caches"}
                and not _is_nonsemantic_name(key)
            }
            _canonical_update(digest, state, _seen=_seen)
        finally:
            _seen.remove(identity)
    else:
        raise TypeError(
            "unsupported authoritative state type: "
            f"{type(value).__module__}.{type(value).__qualname__}")


def semantic_digest(value: object) -> str:
    """Return the timing/diagnostics-independent SHA-256 of ``value``."""
    digest = hashlib.sha256()
    _canonical_update(digest, value)
    return digest.hexdigest()


def _require_hex(name: str, value: str | None, *, optional: bool = False
                 ) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _require_token(name: str, value: str) -> None:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise ValueError(f"{name} is not a stable state token: {value!r}")


@dataclass(frozen=True)
class ScaleSpec:
    """One native-derived view, ordered from coarse to fine.

    ``native_per_view_yx`` is an exact positive rational scale for each axis,
    represented as ``((y_num, y_den), (x_num, x_den))``.  For example, a
    600-dpi C3 scan viewed at 400 dpi stores ``((3, 2), (3, 2))``.
    """

    level_id: str
    ordinal: int
    target_ppc: float
    effective_dpi: float
    native_per_view_yx: tuple[tuple[int, int], tuple[int, int]]
    resampler_id: str

    @property
    def scale_yx(self) -> tuple[Fraction, Fraction]:
        y_scale, x_scale = self.native_per_view_yx
        return Fraction(*y_scale), Fraction(*x_scale)


@dataclass(frozen=True)
class CascadeEnvelope:
    algorithm_id: str
    format_id: str
    seed: bytes
    cell_dots: int
    page_cells_yx: tuple[int, int]
    pages: tuple[int, ...]
    native_dpi: float
    rate_id: str
    detector_profile: str
    search_config_sha256: str
    scale_plan: tuple[ScaleSpec, ...]
    implementation_sha256: tuple[tuple[str, str], ...]
    manifest_sha256: str | None = None
    evidence_policy: str = EVIDENCE_POLICY


def envelope_digest(envelope: CascadeEnvelope) -> str:
    return semantic_digest(envelope)


@dataclass(frozen=True)
class SourceIdentity:
    source_id: str
    capture_id: str
    source_path: str
    source_sha256: str
    source_size: int
    image_shape: tuple[int, int]
    image_dtype: str
    native_dpi: float


def source_identity(
    *,
    source_sha256: str,
    source_size: int,
    image_shape: tuple[int, int],
    image_dtype: str,
    native_dpi: float,
) -> str:
    return _hash_parts(
        b"e023c/source/v1",
        source_sha256.encode("ascii"),
        str(int(source_size)).encode("ascii"),
        repr(tuple(int(v) for v in image_shape)).encode("ascii"),
        str(image_dtype).encode("utf-8"),
        struct.pack(">d", float(native_dpi)),
    )


@dataclass(frozen=True)
class PilotPageSummary:
    page: int
    total: int
    unseen: int
    addressed: int
    bch_solved: int
    conflicted: int = 0


@dataclass(frozen=True)
class PilotKnowledgeSummary:
    """Compact account of the canonical pilot sheet after a barrier.

    ``knowledge_sha256`` identifies the full retained pilot/pose substrate,
    normally stored in a level artifact.  The counters are observer-friendly
    but remain semantic and are checked for an exact partition.
    """

    pages: tuple[PilotPageSummary, ...]
    knowledge_sha256: str
    contributing_level_ids: tuple[str, ...] = ()


def empty_pilot_knowledge(pages: tuple[int, ...]) -> PilotKnowledgeSummary:
    rows = tuple(
        PilotPageSummary(int(page), 0, 0, 0, 0, 0) for page in pages)
    return PilotKnowledgeSummary(rows, semantic_digest({}), ())


@dataclass(frozen=True)
class CompletionCheck:
    status: str
    certificate_union_sha256: str
    manifest_sha256: str | None
    block_rank: tuple[tuple[str, int, int], ...] = ()
    shortfall: int | None = None
    volume_sha256: str | None = None
    expected_volume_sha256: str | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LevelCheckpoint:
    checkpoint_id: str
    ordinal: int
    stage: str
    input_certificate_sha256: str
    output_certificate_sha256: str
    pilot_knowledge_sha256: str
    artifacts_sha256: str
    attempt_ids: tuple[str, ...] = ()
    new_certificate_ids: tuple[str, ...] = ()
    statistics: dict = field(default_factory=dict)
    timings: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})
    diagnostics: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})


def checkpoint_identity(checkpoint: LevelCheckpoint) -> str:
    return semantic_digest(replace(checkpoint, checkpoint_id=""))


def make_checkpoint(
    *,
    ordinal: int,
    stage: str,
    input_certificate_sha256: str,
    output_certificate_sha256: str,
    pilot_knowledge_sha256: str,
    artifacts_sha256: str,
    attempt_ids: tuple[str, ...] = (),
    new_certificate_ids: tuple[str, ...] = (),
    statistics: Mapping | None = None,
    timings: Mapping | None = None,
    diagnostics: Mapping | None = None,
) -> LevelCheckpoint:
    row = LevelCheckpoint(
        checkpoint_id="", ordinal=int(ordinal), stage=str(stage),
        input_certificate_sha256=str(input_certificate_sha256),
        output_certificate_sha256=str(output_certificate_sha256),
        pilot_knowledge_sha256=str(pilot_knowledge_sha256),
        artifacts_sha256=str(artifacts_sha256),
        attempt_ids=tuple(attempt_ids),
        new_certificate_ids=tuple(new_certificate_ids),
        statistics=dict(statistics or {}), timings=dict(timings or {}),
        diagnostics=dict(diagnostics or {}),
    )
    return replace(row, checkpoint_id=checkpoint_identity(row))


@dataclass(frozen=True)
class LevelRecord:
    level_id: str
    ordinal: int
    status: str
    view_sha256: str | None
    view_shape: tuple[int, int] | None
    view_dtype: str | None
    input_certificate_sha256: str | None
    output_certificate_sha256: str | None
    checkpoints: tuple[LevelCheckpoint, ...]
    pilot_knowledge: PilotKnowledgeSummary | None
    attempt_ids: tuple[str, ...]
    new_certificate_ids: tuple[str, ...]
    completion: CompletionCheck | None
    artifacts: dict[str, object] = field(default_factory=dict)
    artifacts_sha256: str = field(default_factory=lambda: semantic_digest({}))
    skip_reason: str | None = None
    timings: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})
    diagnostics: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})


def pending_level(spec: ScaleSpec) -> LevelRecord:
    return LevelRecord(
        level_id=spec.level_id, ordinal=spec.ordinal, status="pending",
        view_sha256=None, view_shape=None, view_dtype=None,
        input_certificate_sha256=None, output_certificate_sha256=None,
        checkpoints=(), pilot_knowledge=None, attempt_ids=(),
        new_certificate_ids=(), completion=None,
    )


def with_level_artifacts(
    level: LevelRecord, artifacts: Mapping[str, object]
) -> LevelRecord:
    frozen = dict(artifacts)
    return replace(
        level, artifacts=frozen, artifacts_sha256=semantic_digest(frozen))


@dataclass(frozen=True)
class CaptureRecord:
    source: SourceIdentity
    status: str
    levels: tuple[LevelRecord, ...]
    first_verified_level_id: str | None = None
    exhaustive_requested: bool = False
    artifacts: dict[str, object] = field(default_factory=dict)
    artifacts_sha256: str = field(default_factory=lambda: semantic_digest({}))
    failure: str | None = None
    timings: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})
    diagnostics: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})


def pending_capture(
    envelope: CascadeEnvelope, source: SourceIdentity
) -> CaptureRecord:
    return CaptureRecord(
        source=source, status="pending",
        levels=tuple(pending_level(row) for row in envelope.scale_plan),
    )


def with_capture_artifacts(
    capture: CaptureRecord, artifacts: Mapping[str, object]
) -> CaptureRecord:
    frozen = dict(artifacts)
    return replace(
        capture, artifacts=frozen, artifacts_sha256=semantic_digest(frozen))


@dataclass(frozen=True)
class DependencySet:
    dependency_set_id: str
    certificate_ids: tuple[str, ...]
    tile_keys: tuple[TileKey, ...]


def dependency_identity(certificate_ids: tuple[str, ...]) -> str:
    ids = tuple(sorted(set(str(row) for row in certificate_ids)))
    return _hash_parts(
        b"e023c/dependency-set/v1",
        *[row.encode("ascii") for row in ids],
    )


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    tile_key: TileKey
    capture_id: str
    level_id: str
    lane_id: str
    stage: str
    source: str
    decoder_profile: str
    numeric_evidence_sha256: str
    component_sha256: tuple[tuple[str, str], ...]
    dependency_set_id: str
    state: str
    decoder_invoked: bool
    k_eff: int
    n_nonshort: int
    n_informative: int
    coverage: float
    n_iters: int
    syndrome_ok: bool | None
    crc_ok: bool | None
    n_erased: int
    certified_new: bool
    output_certificate_id: str | None = None
    metrics: dict = field(default_factory=dict)
    timings: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})


def attempt_identity(
    tile_key: TileKey,
    capture_id: str,
    level_id: str,
    lane_id: str,
    stage: str,
    decoder_profile: str,
    numeric_evidence_sha256: str,
    dependency_set_id: str,
) -> str:
    return _hash_parts(
        b"e023c/tile-attempt/v1",
        repr(tuple(int(v) for v in tile_key)).encode("ascii"),
        capture_id.encode("utf-8"), level_id.encode("utf-8"),
        lane_id.encode("ascii"), stage.encode("utf-8"),
        decoder_profile.encode("utf-8"),
        numeric_evidence_sha256.encode("ascii"),
        dependency_set_id.encode("ascii"),
    )


@dataclass(frozen=True)
class PayloadCertificate:
    certificate_id: str
    tile_key: TileKey
    rate_id: str
    n_user_bits: int
    packed_user_bits: bytes
    user_bits_sha256: str
    origin_attempt_id: str
    born_capture_id: str
    born_level_id: str
    born_lane_id: str
    dependency_set_id: str
    provenance: dict = field(default_factory=dict)

    def user_bits(self) -> np.ndarray:
        return np.unpackbits(
            np.frombuffer(self.packed_user_bits, dtype=np.uint8),
            bitorder="little",
        )[:self.n_user_bits].copy()


def certificate_identity(
    format_id: str,
    seed: bytes,
    tile_key: TileKey,
    rate_id: str,
    user_bits: np.ndarray,
) -> tuple[str, str, bytes]:
    bits = np.asarray(user_bits, np.uint8).ravel()
    if np.any((bits != 0) & (bits != 1)):
        raise ValueError("certificate user bits must be binary")
    packed = np.packbits(bits, bitorder="little").tobytes()
    bits_sha256 = hashlib.sha256(packed).hexdigest()
    identity = _hash_parts(
        b"e023c/certificate/v1", format_id.encode("utf-8"), bytes(seed),
        repr(tuple(int(v) for v in tile_key)).encode("ascii"),
        rate_id.encode("utf-8"), str(bits.size).encode("ascii"), packed,
    )
    return identity, bits_sha256, packed


@dataclass(frozen=True)
class DecoderLane:
    lane_id: str
    level_id: str
    lane_kind: str
    parent_lane_id: str | None
    session_sha256: str


def lane_identity(
    level_id: str,
    lane_kind: str,
    parent_lane_id: str | None = None,
) -> str:
    return _hash_parts(
        b"e023c/decoder-lane/v1", level_id.encode("utf-8"),
        lane_kind.encode("utf-8"),
        (parent_lane_id or "").encode("ascii"),
    )


@dataclass
class CascadeSession:
    envelope: CascadeEnvelope
    captures: list[CaptureRecord]
    pilot_knowledge: PilotKnowledgeSummary
    decoder_lanes: dict[str, DecoderLane] = field(default_factory=dict)
    lane_sessions: dict[str, object] = field(default_factory=dict)
    dependency_sets: dict[str, DependencySet] = field(default_factory=dict)
    certificate_union: dict[TileKey, PayloadCertificate] = field(
        default_factory=dict)
    attempts: list[AttemptRecord] = field(default_factory=list)
    attempt_ids: set[str] = field(default_factory=set)
    status: str = "open"
    first_verified_at: tuple[str, str] | None = None
    fatal: list[str] = field(default_factory=list)
    observer_state: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})
    timings: dict = field(
        default_factory=dict, compare=False, metadata={"semantic": False})

    @property
    def source_hashes(self) -> set[str]:
        return {row.source.source_sha256 for row in self.captures}

    @property
    def capture_ids(self) -> tuple[str, ...]:
        return tuple(row.source.capture_id for row in self.captures)

    @property
    def certified_count(self) -> int:
        return len(self.certificate_union)

    def validate_invariants(self) -> None:
        validate_session(self)


def create_session(
    envelope: CascadeEnvelope,
    sources: tuple[SourceIdentity, ...] = (),
    *,
    pilot_knowledge: PilotKnowledgeSummary | None = None,
) -> CascadeSession:
    session = CascadeSession(
        envelope=envelope,
        captures=[pending_capture(envelope, row) for row in sources],
        pilot_knowledge=(pilot_knowledge or empty_pilot_knowledge(
            envelope.pages)),
    )
    empty_id = dependency_identity(())
    session.dependency_sets[empty_id] = DependencySet(empty_id, (), ())
    validate_session(session)
    return session


def attach_lane_session(
    session: CascadeSession,
    *,
    level_id: str,
    lane_kind: str,
    lane_session: object,
    parent_lane_id: str | None = None,
) -> str:
    """Attach one scale lane whose receiver accumulates independent captures.

    Correlated scale views never share a lane.  Independent physical captures
    at this same scale are appended inside the opaque lane session.
    """
    identity = lane_identity(level_id, lane_kind, parent_lane_id)
    digest = semantic_digest(lane_session)
    row = DecoderLane(
        identity, level_id, lane_kind, parent_lane_id, digest)
    old = session.decoder_lanes.get(identity)
    if (old is not None
            and (old.level_id, old.lane_kind, old.parent_lane_id)
            != (row.level_id, row.lane_kind, row.parent_lane_id)):
        raise ValueError("decoder-lane identity collision")
    # Appending another independent physical capture changes the opaque E023b
    # session and therefore its digest, but not the stable scale-lane identity.
    session.decoder_lanes[identity] = row
    session.lane_sessions[identity] = lane_session
    return identity


def intern_dependency_set(
    session: CascadeSession, certificate_ids
) -> str:
    ids = tuple(sorted(set(str(row) for row in certificate_ids)))
    by_id = {
        row.certificate_id: key
        for key, row in session.certificate_union.items()
    }
    missing = [row for row in ids if row not in by_id]
    if missing:
        raise ValueError(
            f"dependency set refers to unknown certificates: {missing[:4]}")
    identity = dependency_identity(ids)
    row = DependencySet(
        identity, ids, tuple(sorted(by_id[value] for value in ids)))
    old = session.dependency_sets.get(identity)
    if old is not None and old != row:
        raise ValueError("dependency-set identity collision")
    session.dependency_sets[identity] = row
    return identity


def certificate_union_digest(
    certificates: Mapping[TileKey, PayloadCertificate]
) -> str:
    return semantic_digest({
        tuple(key): row.certificate_id
        for key, row in certificates.items()
    })


def _validate_scale_plan(envelope: CascadeEnvelope) -> None:
    if envelope.algorithm_id != ALGORITHM_ID:
        raise ValueError("unknown E023c algorithm id")
    if envelope.evidence_policy != EVIDENCE_POLICY:
        raise ValueError("unknown E023c evidence policy")
    _require_token("format_id", envelope.format_id)
    _require_token("rate_id", envelope.rate_id)
    _require_token("detector_profile", envelope.detector_profile)
    _require_hex("search_config_sha256", envelope.search_config_sha256)
    _require_hex("manifest_sha256", envelope.manifest_sha256, optional=True)
    if not isinstance(envelope.seed, bytes) or not envelope.seed:
        raise ValueError("E023c seed must be non-empty bytes")
    if int(envelope.cell_dots) <= 0:
        raise ValueError("cell_dots must be positive")
    if (len(envelope.page_cells_yx) != 2
            or any(int(value) <= 0 for value in envelope.page_cells_yx)):
        raise ValueError("page_cells_yx must contain two positive integers")
    if (not envelope.pages
            or len(set(envelope.pages)) != len(envelope.pages)
            or any(int(page) < 0 for page in envelope.pages)):
        raise ValueError("pages must be a non-empty unique sequence")
    if not math.isfinite(envelope.native_dpi) or envelope.native_dpi <= 0:
        raise ValueError("native_dpi must be finite and positive")
    if not envelope.scale_plan:
        raise ValueError("scale plan must not be empty")
    if not envelope.implementation_sha256:
        raise ValueError("implementation fingerprints must not be empty")
    names = set()
    previous_ppc = -math.inf
    previous_dpi = -math.inf
    for expected_ordinal, row in enumerate(envelope.scale_plan):
        _require_token("level_id", row.level_id)
        _require_token("resampler_id", row.resampler_id)
        if row.level_id in names:
            raise ValueError("scale plan has duplicate level ids")
        names.add(row.level_id)
        if row.ordinal != expected_ordinal:
            raise ValueError("scale plan ordinals must be contiguous")
        if (not math.isfinite(row.target_ppc) or row.target_ppc <= 0
                or row.target_ppc <= previous_ppc):
            raise ValueError("scale plan pixels/cell must increase strictly")
        if (not math.isfinite(row.effective_dpi) or row.effective_dpi <= 0
                or row.effective_dpi <= previous_dpi):
            raise ValueError("scale plan DPI must increase strictly")
        previous_ppc = row.target_ppc
        previous_dpi = row.effective_dpi
        if len(row.native_per_view_yx) != 2:
            raise ValueError("scale transform must have two axes")
        scales = []
        for numerator, denominator in row.native_per_view_yx:
            if numerator <= 0 or denominator <= 0:
                raise ValueError("scale rationals must be positive")
            if math.gcd(numerator, denominator) != 1:
                raise ValueError("scale rationals must be reduced")
            scales.append(Fraction(numerator, denominator))
        if scales[0] != scales[1]:
            raise ValueError("E023c currently requires isotropic scale views")
        derived_dpi = envelope.native_dpi / float(scales[0])
        if not math.isclose(
                row.effective_dpi, derived_dpi, rel_tol=1e-10, abs_tol=1e-9):
            raise ValueError("effective DPI disagrees with exact scale")
        derived_ppc = envelope.cell_dots * row.effective_dpi / 600.0
        if not math.isclose(
                row.target_ppc, derived_ppc, rel_tol=1e-10, abs_tol=1e-9):
            raise ValueError("pixels/cell disagrees with cell dots and DPI")
    last = envelope.scale_plan[-1]
    if last.native_per_view_yx != ((1, 1), (1, 1)):
        raise ValueError("the final E023c scale must be the native raster")
    if not math.isclose(last.effective_dpi, envelope.native_dpi):
        raise ValueError("the final E023c DPI must be native DPI")
    fingerprint_names = [name for name, _digest in envelope.implementation_sha256]
    if len(set(fingerprint_names)) != len(fingerprint_names):
        raise ValueError("implementation fingerprint names must be unique")
    for name, digest in envelope.implementation_sha256:
        if not name:
            raise ValueError("implementation fingerprint name is empty")
        _require_hex("implementation fingerprint", digest)


def _validate_source(source: SourceIdentity, envelope: CascadeEnvelope) -> None:
    _require_hex("source_id", source.source_id)
    _require_token("capture_id", source.capture_id)
    _require_hex("source_sha256", source.source_sha256)
    if source.source_size <= 0:
        raise ValueError("source size must be positive")
    if (len(source.image_shape) != 2
            or any(int(value) <= 0 for value in source.image_shape)):
        raise ValueError("source image shape must be two positive integers")
    if not source.image_dtype:
        raise ValueError("source image dtype is empty")
    if not math.isclose(source.native_dpi, envelope.native_dpi):
        raise ValueError("source native DPI disagrees with the envelope")
    expected = source_identity(
        source_sha256=source.source_sha256,
        source_size=source.source_size,
        image_shape=source.image_shape,
        image_dtype=source.image_dtype,
        native_dpi=source.native_dpi,
    )
    if source.source_id != expected:
        raise ValueError("source identity digest mismatch")


def _validate_pilot_summary(
    summary: PilotKnowledgeSummary, envelope: CascadeEnvelope
) -> None:
    _require_hex("pilot knowledge digest", summary.knowledge_sha256)
    if tuple(row.page for row in summary.pages) != envelope.pages:
        raise ValueError("pilot summary pages disagree with envelope pages")
    known_levels = {row.level_id for row in envelope.scale_plan}
    if (len(set(summary.contributing_level_ids))
            != len(summary.contributing_level_ids)
            or any(row not in known_levels
                   for row in summary.contributing_level_ids)):
        raise ValueError("pilot summary has invalid contributing levels")
    for row in summary.pages:
        counts = (
            row.total, row.unseen, row.addressed, row.bch_solved,
            row.conflicted,
        )
        if any(int(value) < 0 for value in counts):
            raise ValueError("pilot summary has a negative count")
        if row.unseen + row.addressed + row.bch_solved + row.conflicted != row.total:
            raise ValueError("pilot summary does not partition total tiles")


def _validate_completion(
    row: CompletionCheck, envelope: CascadeEnvelope
) -> None:
    if row.status not in COMPLETION_STATUSES:
        raise ValueError("unknown E023c completion status")
    _require_hex("completion certificate digest", row.certificate_union_sha256)
    _require_hex("completion manifest", row.manifest_sha256, optional=True)
    _require_hex("completion volume", row.volume_sha256, optional=True)
    _require_hex(
        "completion expected volume", row.expected_volume_sha256,
        optional=True,
    )
    if row.manifest_sha256 != envelope.manifest_sha256:
        raise ValueError("completion check used a different manifest")
    if row.shortfall is not None and row.shortfall < 0:
        raise ValueError("completion shortfall must be non-negative")
    for block_id, rank, required in row.block_rank:
        if not block_id or rank < 0 or required < 0 or rank > required:
            raise ValueError("invalid completion block rank")
    if row.status == "not_configured":
        if envelope.manifest_sha256 is not None:
            raise ValueError("configured manifest cannot be not_configured")
    elif envelope.manifest_sha256 is None:
        raise ValueError("fountain completion requires a manifest")
    if row.status == "volume_verified":
        if (row.shortfall != 0 or row.volume_sha256 is None
                or row.expected_volume_sha256 is None
                or row.volume_sha256 != row.expected_volume_sha256):
            raise ValueError("volume_verified lacks rank-zero SHA proof")
    if row.status == "hash_mismatch":
        if (row.volume_sha256 is None or row.expected_volume_sha256 is None
                or row.volume_sha256 == row.expected_volume_sha256):
            raise ValueError("hash_mismatch lacks unequal SHA values")


def _validate_checkpoint(
    checkpoint: LevelCheckpoint,
    level: LevelRecord,
    previous_rank: int,
) -> int:
    if checkpoint.ordinal < 0:
        raise ValueError("checkpoint ordinal must be non-negative")
    if checkpoint.stage not in _CHECKPOINT_RANK:
        raise ValueError("unknown E023c checkpoint stage")
    rank = _CHECKPOINT_RANK[checkpoint.stage]
    if rank <= previous_rank:
        raise ValueError("level checkpoints are not in stage order")
    for name, digest in (
        ("checkpoint_id", checkpoint.checkpoint_id),
        ("checkpoint input", checkpoint.input_certificate_sha256),
        ("checkpoint output", checkpoint.output_certificate_sha256),
        ("checkpoint pilot", checkpoint.pilot_knowledge_sha256),
        ("checkpoint artifacts", checkpoint.artifacts_sha256),
    ):
        _require_hex(name, digest)
    if checkpoint.checkpoint_id != checkpoint_identity(checkpoint):
        raise ValueError("checkpoint identity mismatch")
    if len(set(checkpoint.attempt_ids)) != len(checkpoint.attempt_ids):
        raise ValueError("checkpoint has duplicate attempts")
    if len(set(checkpoint.new_certificate_ids)) != len(
            checkpoint.new_certificate_ids):
        raise ValueError("checkpoint has duplicate certificates")
    if not set(checkpoint.attempt_ids).issubset(level.attempt_ids):
        raise ValueError("checkpoint refers outside its level attempts")
    if not set(checkpoint.new_certificate_ids).issubset(
            level.new_certificate_ids):
        raise ValueError("checkpoint refers outside its level certificates")
    return rank


def _validate_level(
    level: LevelRecord,
    spec: ScaleSpec,
    envelope: CascadeEnvelope,
) -> None:
    if (level.level_id, level.ordinal) != (spec.level_id, spec.ordinal):
        raise ValueError("capture level order disagrees with scale plan")
    if level.status not in LEVEL_STATUSES:
        raise ValueError("unknown E023c level status")
    if semantic_digest(level.artifacts) != level.artifacts_sha256:
        raise ValueError("level artifacts digest mismatch")
    if len(set(level.attempt_ids)) != len(level.attempt_ids):
        raise ValueError("level has duplicate attempts")
    if len(set(level.new_certificate_ids)) != len(level.new_certificate_ids):
        raise ValueError("level has duplicate certificates")
    for digest in (level.input_certificate_sha256,
                   level.output_certificate_sha256, level.view_sha256):
        _require_hex("level digest", digest, optional=True)
    if level.pilot_knowledge is not None:
        _validate_pilot_summary(level.pilot_knowledge, envelope)
    if level.completion is not None:
        _validate_completion(level.completion, envelope)
    previous_rank = -1
    for ordinal, checkpoint in enumerate(level.checkpoints):
        if checkpoint.ordinal != ordinal:
            raise ValueError("checkpoint ordinals must be contiguous")
        previous_rank = _validate_checkpoint(checkpoint, level, previous_rank)
    if level.status == "pending":
        if (level.view_sha256 is not None or level.view_shape is not None
                or level.view_dtype is not None or level.checkpoints
                or level.input_certificate_sha256 is not None
                or level.output_certificate_sha256 is not None
                or level.pilot_knowledge is not None or level.attempt_ids
                or level.new_certificate_ids or level.completion is not None
                or level.artifacts or level.skip_reason is not None):
            raise ValueError("pending level already carries work")
    elif level.status == "skipped_volume_verified":
        if (level.checkpoints or level.view_sha256 is not None
                or level.attempt_ids or level.new_certificate_ids
                or level.completion is not None or level.artifacts
                or not level.skip_reason):
            raise ValueError("skipped level must contain only its reason")
    elif level.status == "complete":
        if (level.view_sha256 is None or level.view_shape is None
                or level.view_dtype is None
                or level.input_certificate_sha256 is None
                or level.output_certificate_sha256 is None
                or level.pilot_knowledge is None
                or not level.checkpoints
                or not any(row.stage == "level_complete"
                           for row in level.checkpoints)
                or level.checkpoints[-1].stage not in {
                    "level_complete", "fountain_check"}):
            raise ValueError("complete level lacks its final barrier")
        final = level.checkpoints[-1]
        if (final.output_certificate_sha256
                != level.output_certificate_sha256
                or final.pilot_knowledge_sha256
                != level.pilot_knowledge.knowledge_sha256
                or final.artifacts_sha256 != level.artifacts_sha256
                or final.attempt_ids != level.attempt_ids
                or final.new_certificate_ids != level.new_certificate_ids):
            raise ValueError("complete level disagrees with final checkpoint")
    elif level.status == "in_progress":
        if (not level.checkpoints
                or level.checkpoints[-1].stage in {
                    "level_complete", "fountain_check"}):
            raise ValueError("in-progress level has no open checkpoint")
    elif level.status == "failed" and not level.skip_reason:
        raise ValueError("failed level lacks a reason")


def _validate_capture(
    capture: CaptureRecord, envelope: CascadeEnvelope
) -> None:
    _validate_source(capture.source, envelope)
    if capture.status not in CAPTURE_STATUSES:
        raise ValueError("unknown E023c capture status")
    if len(capture.levels) != len(envelope.scale_plan):
        raise ValueError("capture does not contain the complete scale plan")
    if semantic_digest(capture.artifacts) != capture.artifacts_sha256:
        raise ValueError("capture artifacts digest mismatch")
    for level, spec in zip(capture.levels, envelope.scale_plan):
        _validate_level(level, spec, envelope)
    statuses = [row.status for row in capture.levels]
    active = [index for index, status in enumerate(statuses)
              if status in {"in_progress", "failed"}]
    if len(active) > 1:
        raise ValueError("capture has multiple active levels")
    # Once a level is pending or skipped, no later level may be completed.
    frontier_seen = False
    for status in statuses:
        if status in {"pending", "skipped_volume_verified"}:
            frontier_seen = True
        elif frontier_seen and status in {"complete", "in_progress", "failed"}:
            raise ValueError("capture levels are not a coarse-to-fine prefix")
    verified = [
        row.level_id for row in capture.levels
        if row.completion is not None
        and row.completion.status == "volume_verified"
    ]
    expected_first = verified[0] if verified else None
    if capture.first_verified_level_id != expected_first:
        raise ValueError("capture first-verified level is inconsistent")
    if capture.status == "pending" and any(row != "pending" for row in statuses):
        raise ValueError("pending capture already has level work")
    if capture.status == "in_progress":
        if not any(row in {"in_progress", "complete"} for row in statuses):
            raise ValueError("in-progress capture has no work")
        if all(row == "complete" for row in statuses):
            raise ValueError("fully processed capture is still in-progress")
    if capture.status == "exhausted" and any(row != "complete" for row in statuses):
        raise ValueError("exhausted capture has unfinished levels")
    if capture.status == "early_stopped":
        if capture.exhaustive_requested or expected_first is None:
            raise ValueError("early-stopped capture lacks verified completion")
        index = next(
            row.ordinal for row in capture.levels
            if row.level_id == expected_first)
        if any(row.status != "skipped_volume_verified"
               for row in capture.levels[index + 1:]):
            raise ValueError("post-verification levels are not marked skipped")
    if capture.status == "skipped_volume_verified":
        if (capture.first_verified_level_id is not None
                or any(row != "skipped_volume_verified" for row in statuses)):
            raise ValueError("globally skipped capture contains work")
    if capture.status == "failed" and not capture.failure:
        raise ValueError("failed capture lacks a reason")


def _certificate_by_id(
    session: CascadeSession,
) -> dict[str, PayloadCertificate]:
    out: dict[str, PayloadCertificate] = {}
    for key, row in session.certificate_union.items():
        if tuple(key) != tuple(row.tile_key):
            raise ValueError("certificate-union key mismatch")
        old = out.get(row.certificate_id)
        if old is not None and old != row:
            raise ValueError("certificate identity collision")
        out[row.certificate_id] = row
    return out


def _validate_dependencies(
    session: CascadeSession,
    certificates: dict[str, PayloadCertificate],
) -> None:
    for identity, row in session.dependency_sets.items():
        if identity != row.dependency_set_id:
            raise ValueError("dependency-set key mismatch")
        if tuple(sorted(set(row.certificate_ids))) != row.certificate_ids:
            raise ValueError("dependency certificates are not canonical")
        if dependency_identity(row.certificate_ids) != identity:
            raise ValueError("dependency-set identity mismatch")
        missing = [value for value in row.certificate_ids
                   if value not in certificates]
        if missing:
            raise ValueError("dependency set refers to unknown certificates")
        expected_tiles = tuple(sorted(
            certificates[value].tile_key for value in row.certificate_ids))
        if row.tile_keys != expected_tiles:
            raise ValueError("dependency tile index mismatch")
    empty_id = dependency_identity(())
    if session.dependency_sets.get(empty_id) != DependencySet(empty_id, (), ()):
        raise ValueError("canonical empty dependency set is missing")


def _validate_certificate(
    row: PayloadCertificate,
    session: CascadeSession,
) -> None:
    _require_hex("certificate_id", row.certificate_id)
    _require_hex("certificate user bits", row.user_bits_sha256)
    if row.rate_id != session.envelope.rate_id:
        raise ValueError("certificate rate disagrees with envelope")
    if row.n_user_bits <= 0:
        raise ValueError("certificate bit count must be positive")
    if len(row.packed_user_bits) != (row.n_user_bits + 7) // 8:
        raise ValueError("certificate packed length mismatch")
    bits = row.user_bits()
    identity, bits_sha, packed = certificate_identity(
        session.envelope.format_id, session.envelope.seed,
        row.tile_key, row.rate_id, bits,
    )
    if (identity != row.certificate_id or bits_sha != row.user_bits_sha256
            or packed != row.packed_user_bits):
        raise ValueError("certificate identity or packed bits mismatch")
    if row.dependency_set_id not in session.dependency_sets:
        raise ValueError("certificate has unknown dependencies")


def _validate_attempts(
    session: CascadeSession,
    certificates: dict[str, PayloadCertificate],
) -> None:
    if session.attempt_ids != {row.attempt_id for row in session.attempts}:
        raise ValueError("attempt index is corrupt")
    if len(session.attempts) != len(session.attempt_ids):
        raise ValueError("attempt ledger contains duplicates")
    capture_levels = {
        (capture.source.capture_id, level.level_id)
        for capture in session.captures for level in capture.levels
    }
    by_id = {row.attempt_id: row for row in session.attempts}
    capture_ordinal = {
        row.source.capture_id: ordinal
        for ordinal, row in enumerate(session.captures)
    }
    level_ordinal = {
        row.level_id: row.ordinal for row in session.envelope.scale_plan
    }
    for row in session.attempts:
        _require_hex("attempt_id", row.attempt_id)
        _require_hex("attempt evidence", row.numeric_evidence_sha256)
        if (row.capture_id, row.level_id) not in capture_levels:
            raise ValueError("attempt belongs to unknown capture/level")
        if row.lane_id not in session.decoder_lanes:
            raise ValueError("attempt belongs to unknown decoder lane")
        lane = session.decoder_lanes[row.lane_id]
        if lane.level_id != row.level_id:
            raise ValueError("attempt and decoder lane level disagree")
        if row.dependency_set_id not in session.dependency_sets:
            raise ValueError("attempt has unknown dependency set")
        expected = attempt_identity(
            row.tile_key, row.capture_id, row.level_id, row.lane_id,
            row.stage, row.decoder_profile, row.numeric_evidence_sha256,
            row.dependency_set_id,
        )
        if row.attempt_id != expected:
            raise ValueError("attempt identity mismatch")
        if row.state not in ATTEMPT_STATES:
            raise ValueError("unknown attempt state")
        if (row.k_eff < 0 or row.n_nonshort < 0 or row.n_informative < 0
                or row.n_erased < 0 or row.n_iters < 0
                or row.n_informative > row.n_nonshort
                or not math.isfinite(row.coverage)
                or not 0.0 <= row.coverage <= 1.0):
            raise ValueError("attempt carries invalid decoder counts")
        if row.decoder_invoked != (row.state in {
                "attempted_failed", "certified"}):
            raise ValueError("attempt decoder-invoked flag is inconsistent")
        if row.state == "certified":
            if (row.syndrome_ok is not True or row.crc_ok is not True
                    or row.output_certificate_id not in certificates):
                raise ValueError("certified attempt lacks CRC certificate")
        elif row.output_certificate_id is not None or row.certified_new:
            raise ValueError("non-certified attempt exposes a certificate")
        if row.certified_new:
            certificate = certificates[row.output_certificate_id]  # type: ignore[index]
            if certificate.origin_attempt_id != row.attempt_id:
                raise ValueError("new certificate origin attempt mismatch")
        dependencies = session.dependency_sets[row.dependency_set_id]
        if row.tile_key in dependencies.tile_keys:
            raise ValueError("attempt depends on its target tile")
        attempt_order = (
            capture_ordinal[row.capture_id], level_ordinal[row.level_id])
        for dependency_id in dependencies.certificate_ids:
            dependency = certificates[dependency_id]
            if (dependency.born_capture_id not in capture_ordinal
                    or dependency.born_level_id not in level_ordinal):
                raise ValueError(
                    "dependency certificate has unknown birth barrier")
            dependency_order = (
                capture_ordinal[dependency.born_capture_id],
                level_ordinal[dependency.born_level_id],
            )
            if dependency_order >= attempt_order:
                raise ValueError(
                    "attempt dependency was not born at an earlier barrier")
    for row in certificates.values():
        if row.origin_attempt_id not in by_id:
            raise ValueError("certificate origin attempt is missing")
        attempt = by_id[row.origin_attempt_id]
        if (attempt.tile_key != row.tile_key or not attempt.certified_new
                or attempt.output_certificate_id != row.certificate_id):
            raise ValueError("certificate origin attempt is inconsistent")
        if (row.born_capture_id, row.born_level_id, row.born_lane_id) != (
                attempt.capture_id, attempt.level_id, attempt.lane_id):
            raise ValueError("certificate birth provenance disagrees")
        if row.dependency_set_id != attempt.dependency_set_id:
            raise ValueError("certificate dependencies disagree with attempt")

    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(certificate_id: str) -> None:
        if certificate_id in complete:
            return
        if certificate_id in visiting:
            raise ValueError("certificate dependency cycle")
        visiting.add(certificate_id)
        certificate = certificates[certificate_id]
        dependencies = session.dependency_sets[certificate.dependency_set_id]
        for dependency_id in dependencies.certificate_ids:
            visit(dependency_id)
        visiting.remove(certificate_id)
        complete.add(certificate_id)

    for certificate_id in certificates:
        visit(certificate_id)


def _validate_lane_state(session: CascadeSession) -> None:
    if set(session.decoder_lanes) != set(session.lane_sessions):
        raise ValueError("decoder-lane index and sessions disagree")
    level_ids = {row.level_id for row in session.envelope.scale_plan}
    capture_ordinal = {
        row.source.capture_id: ordinal
        for ordinal, row in enumerate(session.captures)
    }
    level_ordinal = {
        row.level_id: row.ordinal for row in session.envelope.scale_plan
    }
    certificate_order: dict[TileKey, tuple[int, int]] = {}
    for key, certificate in session.certificate_union.items():
        if (certificate.born_capture_id not in capture_ordinal
                or certificate.born_level_id not in level_ordinal):
            raise ValueError("certificate has unknown birth barrier")
        certificate_order[key] = (
            capture_ordinal[certificate.born_capture_id],
            level_ordinal[certificate.born_level_id],
        )
    for identity, row in session.decoder_lanes.items():
        if identity != row.lane_id:
            raise ValueError("decoder-lane key mismatch")
        if row.level_id not in level_ids:
            raise ValueError("decoder lane belongs to unknown level")
        if row.parent_lane_id is not None:
            if row.parent_lane_id not in session.decoder_lanes:
                raise ValueError("decoder lane has unknown parent")
            if row.parent_lane_id == identity:
                raise ValueError("decoder lane cannot parent itself")
        expected = lane_identity(
            row.level_id, row.lane_kind, row.parent_lane_id)
        if identity != expected:
            raise ValueError("decoder-lane identity mismatch")
        lane_session = session.lane_sessions[identity]
        actual = semantic_digest(lane_session)
        if actual != row.session_sha256:
            raise ValueError("decoder-lane session digest mismatch")
        for scan in getattr(lane_session, "scans", ()):
            marker = getattr(scan, "decode_skip_tiles", None)
            if marker is None:
                continue
            if type(marker) is not tuple:
                raise ValueError(
                    "lane decode skip marker must be a canonical tuple")
            if not marker:
                continue
            capture_id = getattr(scan, "capture_id", None)
            if capture_id not in capture_ordinal:
                raise ValueError(
                    "lane decode skip marker belongs to an unknown capture")
            barrier = (capture_ordinal[capture_id], level_ordinal[row.level_id])
            for key in marker:
                if (type(key) is not tuple or len(key) != 3
                        or any(not isinstance(value, (int, np.integer))
                               or isinstance(value, (bool, np.bool_))
                               for value in key)):
                    raise ValueError(
                        "lane decode skip marker contains a malformed tile key")
                canonical = tuple(int(value) for value in key)
                if (canonical not in certificate_order
                        or certificate_order[canonical] >= barrier):
                    raise ValueError(
                        "lane decode skip marker is not authorized by the "
                        "strictly-earlier global certificate frontier")
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(identity: str) -> None:
        if identity in complete:
            return
        if identity in visiting:
            raise ValueError("decoder-lane parent cycle")
        visiting.add(identity)
        parent = session.decoder_lanes[identity].parent_lane_id
        if parent is not None:
            visit(parent)
        visiting.remove(identity)
        complete.add(identity)

    for identity in session.decoder_lanes:
        visit(identity)


def _validate_level_ledgers(session: CascadeSession) -> None:
    attempts_by_level: dict[tuple[str, str], list[str]] = {}
    certificates_by_level: dict[tuple[str, str], list[str]] = {}
    for row in session.attempts:
        attempts_by_level.setdefault(
            (row.capture_id, row.level_id), []).append(row.attempt_id)
        if row.certified_new:
            certificates_by_level.setdefault(
                (row.capture_id, row.level_id), []).append(
                    row.output_certificate_id)  # type: ignore[arg-type]
    for capture in session.captures:
        for level in capture.levels:
            key = (capture.source.capture_id, level.level_id)
            if level.attempt_ids != tuple(attempts_by_level.get(key, ())):
                raise ValueError("level attempt ledger disagrees with session")
            if level.new_certificate_ids != tuple(
                    certificates_by_level.get(key, ())):
                raise ValueError("level certificate ledger disagrees with session")

    capture_ordinal = {
        row.source.capture_id: ordinal
        for ordinal, row in enumerate(session.captures)
    }
    level_ordinal = {
        row.level_id: row.ordinal for row in session.envelope.scale_plan
    }
    certificate_order = {
        key: (
            capture_ordinal[row.born_capture_id],
            level_ordinal[row.born_level_id],
        )
        for key, row in session.certificate_union.items()
    }
    for capture in session.captures:
        for level in capture.levels:
            order = (
                capture_ordinal[capture.source.capture_id], level.ordinal)
            before = {
                key: row for key, row in session.certificate_union.items()
                if certificate_order[key] < order
            }
            through = {
                key: row for key, row in session.certificate_union.items()
                if certificate_order[key] <= order
            }
            if (level.input_certificate_sha256 is not None
                    and level.input_certificate_sha256
                    != certificate_union_digest(before)):
                raise ValueError("level input certificate digest mismatch")
            if (level.output_certificate_sha256 is not None
                    and level.output_certificate_sha256
                    != certificate_union_digest(through)):
                raise ValueError("level output certificate digest mismatch")
            if (level.completion is not None
                    and level.completion.certificate_union_sha256
                    != level.output_certificate_sha256):
                raise ValueError(
                    "completion used a different certificate frontier")


def validate_session(session: CascadeSession) -> None:
    """Fail closed on schema, ordering, evidence, or lineage corruption."""
    if not isinstance(session, CascadeSession):
        raise ValueError("object is not an E023c cascade session")
    _validate_scale_plan(session.envelope)
    if session.status not in SESSION_STATUSES:
        raise ValueError("unknown E023c session status")
    if not session.captures:
        raise ValueError("cascade session has no captures")
    capture_ids = [row.source.capture_id for row in session.captures]
    source_ids = [row.source.source_id for row in session.captures]
    source_hashes = [row.source.source_sha256 for row in session.captures]
    if len(set(capture_ids)) != len(capture_ids):
        raise ValueError("capture ids must be unique")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("source identities must be unique")
    if len(set(source_hashes)) != len(source_hashes):
        raise ValueError("duplicate source bytes are an authoritative no-op")
    for capture in session.captures:
        _validate_capture(capture, session.envelope)
    _validate_pilot_summary(session.pilot_knowledge, session.envelope)
    completed_pilot = [
        level.pilot_knowledge
        for capture in session.captures for level in capture.levels
        if level.status == "complete" and level.pilot_knowledge is not None
    ]
    if (completed_pilot
            and session.pilot_knowledge != completed_pilot[-1]):
        raise ValueError(
            "global pilot knowledge is not the last committed barrier")
    _validate_lane_state(session)
    certificates = _certificate_by_id(session)
    _validate_dependencies(session, certificates)
    for row in certificates.values():
        _validate_certificate(row, session)
    _validate_attempts(session, certificates)
    _validate_level_ledgers(session)
    verified = [
        (capture.source.capture_id, level.level_id)
        for capture in session.captures for level in capture.levels
        if level.completion is not None
        and level.completion.status == "volume_verified"
    ]
    expected_first = verified[0] if verified else None
    if session.first_verified_at != expected_first:
        raise ValueError("session first-verified checkpoint is inconsistent")
    if session.status == "early_stopped":
        if expected_first is None:
            raise ValueError("early-stopped session lacks verified volume")
        found = False
        for capture in session.captures:
            if not found and capture.source.capture_id != expected_first[0]:
                if capture.status != "exhausted":
                    raise ValueError(
                        "capture before early stop was not exhausted")
            if found and capture.status != "skipped_volume_verified":
                raise ValueError("capture after early stop was not skipped")
            if capture.source.capture_id == expected_first[0]:
                found = True
                if capture.status != "early_stopped":
                    raise ValueError("verifying capture is not early-stopped")
    if session.status == "exhausted":
        if any(row.status != "exhausted" for row in session.captures):
            raise ValueError("exhausted session has unfinished captures")
    if (session.status == "open"
            and all(row.status == "exhausted" for row in session.captures)):
        raise ValueError("fully exhausted cascade is still open")
    if session.status == "failed" and not session.fatal:
        raise ValueError("failed session lacks a fatal record")
    if session.status != "failed" and session.fatal:
        raise ValueError("non-failed session carries fatal records")


def authoritative_digest(session: CascadeSession) -> str:
    """Hash all authoritative cascade state, excluding timing/diagnostics."""
    return semantic_digest(session)


def save_session(path: Path | str, session: CascadeSession) -> None:
    """Validate and atomically replace one E023c state artifact."""
    validate_session(session)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "magic": STATE_MAGIC,
        "version": STATE_VERSION,
        "semantic_sha256": authoritative_digest(session),
        "session": session,
    }
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def load_session(path: Path | str) -> CascadeSession:
    """Load, type-check, validate, and authenticate one E023c state."""
    source = Path(path)
    with source.open("rb") as stream:
        unpickler = pickle.Unpickler(stream)
        payload = unpickler.load()
        if stream.read(1):
            raise ValueError(f"{source} has trailing bytes")
    if not isinstance(payload, dict) or payload.get("magic") != STATE_MAGIC:
        raise ValueError(f"{source} is not an E023c cascade state")
    if payload.get("version") != STATE_VERSION:
        raise ValueError(
            f"E023c state version {payload.get('version')} != {STATE_VERSION}")
    session = payload.get("session")
    if not isinstance(session, CascadeSession):
        raise ValueError(f"{source} has an invalid E023c session payload")
    validate_session(session)
    stored = payload.get("semantic_sha256")
    _require_hex("stored semantic digest", stored)
    if authoritative_digest(session) != stored:
        raise ValueError(f"{source} has a semantic digest mismatch")
    return session


__all__ = [
    "ALGORITHM_ID", "ATTEMPT_STATES", "CAPTURE_STATUSES",
    "CHECKPOINT_STAGES", "COMPLETION_STATUSES", "EVIDENCE_POLICY",
    "LEVEL_STATUSES", "SESSION_STATUSES", "STATE_MAGIC", "STATE_VERSION",
    "AttemptRecord", "CascadeEnvelope", "CascadeSession", "CaptureRecord",
    "CompletionCheck", "DecoderLane", "DependencySet", "LevelCheckpoint",
    "LevelRecord", "PayloadCertificate", "PilotKnowledgeSummary",
    "PilotPageSummary", "ScaleSpec", "SourceIdentity", "TileKey",
    "attach_lane_session", "attempt_identity", "authoritative_digest",
    "certificate_identity", "certificate_union_digest", "checkpoint_identity",
    "create_session", "dependency_identity", "empty_pilot_knowledge",
    "envelope_digest", "intern_dependency_set", "lane_identity",
    "load_session", "make_checkpoint", "pending_capture", "pending_level",
    "save_session", "semantic_digest", "source_identity", "validate_session",
    "with_capture_artifacts", "with_level_artifacts",
]

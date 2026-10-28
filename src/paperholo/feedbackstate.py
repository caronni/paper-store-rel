"""Persistent state for the E024 certified-feedback receiver.

E024 is an append-only overlay over an immutable E023b receiver state.  The
large E023b artifact remains external and is bound by complete-file and
semantic hashes.  Nothing in this module changes or upgrades E023b in place.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import pickle
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from . import compose, ldpc, payloaddec, receiver
from .pilotsearch import AffinePose


STATE_MAGIC = "e024-feedback-session-v1"
STATE_VERSION = 1
ALGORITHM_ID = "e024.0-certified-feedback-v1"
EVIDENCE_POLICY = "target-safe/supersede-per-capture/v1"

PROFILE_CONTROL = "control"
PROFILE_RECAL = "recal"
PROFILE_REFINE = "refine"
PROFILE_COMBINED = "combined"
FEEDBACK_PROFILES = frozenset((
    PROFILE_CONTROL, PROFILE_RECAL, PROFILE_REFINE, PROFILE_COMBINED,
))

TileKey = tuple[int, int, int]
WindowKey = tuple[str, int]


def _hash_parts(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def _json_digest(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def stream_sha256(path: Path | str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


@dataclass(frozen=True)
class FeedbackConfig:
    """Registered numerical and scheduling constants for E024.0."""

    block_cells: int = 16
    validation_modulus: int = 4
    min_payload_train: int = 64
    min_payload_validation: int = 32
    min_train_per_class: int = 20
    min_validation_per_class: int = 10
    min_label_blocks: int = 4
    min_improvement: float = 1e-4
    confidence_cap: float = 8.0
    context_clip: float = 8.0
    pose_angle_deg: float = 0.15
    pose_angle_coarse_step_deg: float = 0.15
    pose_angle_fine_step_deg: float = 0.05
    pose_phase_cells: float = 0.25
    pose_phase_coarse_step_cells: float = 0.25
    pose_phase_fine_step_cells: float = 0.0625
    pose_site_cap_train: int = 2048
    pose_site_cap_validation: int = 1024
    pilot_mismatch_slack: float = 0.005
    baseline_bp_max_iters: int = 60
    retry_bp_max_iters: int = 150
    bp_alpha: float = 0.8
    max_generations: int = 6

    @property
    def digest(self) -> str:
        return _json_digest(asdict(self))


@dataclass(frozen=True)
class BaselineReference:
    path: str
    file_sha256: str
    file_size: int
    authoritative_sha256: str
    format_id: str
    seed: bytes
    cell_dots: int
    pages: tuple[int, ...]
    page_cells_yx: tuple[int, int]
    rate_id: str
    ordered_capture_ids: tuple[str, ...]


@dataclass(frozen=True)
class E024Envelope:
    algorithm_id: str
    profile: str
    config: FeedbackConfig
    config_sha256: str
    evidence_policy: str
    implementation_sha256: tuple[tuple[str, str], ...]
    certificate_seed_sha256: str | None = None
    certificate_seed_payload: bytes | None = None


@dataclass(frozen=True)
class DependencySet:
    dependency_set_id: str
    certificate_ids: tuple[str, ...]
    tile_keys: tuple[TileKey, ...]


@dataclass(frozen=True)
class CertificateRecord:
    certificate_id: str
    tile_key: TileKey
    rate_id: str
    user_bits: np.ndarray
    user_bits_sha256: str
    source: str
    origin_attempt_id: str
    born_generation: int
    dependency_set_id: str
    provenance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LabelUse:
    certificate_id: str
    role: str
    n_sites: int
    payload_indices_sha256: str


@dataclass(frozen=True)
class EvidenceRevision:
    revision_id: str
    scan_id: str
    capture_id: str
    placement_ordinal: int
    placement_id: str
    generation: int
    arm: str
    parent_revision_id: str | None
    dependency_set_id: str
    label_uses: tuple[LabelUse, ...]
    pose: AffinePose
    emission: payloaddec.WindowEmission | None
    accepted: bool
    refuse_reason: str
    metrics: dict


@dataclass(frozen=True)
class CellPatch:
    patch_id: str
    generation: int
    scan_id: str
    capture_id: str
    page: int
    payload_indices: np.ndarray
    previous_owner: np.ndarray
    new_owner: np.ndarray
    previous_projection_sha256: str
    new_projection_sha256: str


@dataclass(frozen=True)
class FeedbackAttempt:
    attempt_id: str
    generation: int
    tile_key: TileKey
    stage: str
    source: str
    decoder_profile: str
    numeric_evidence_sha256: str
    component_sha256: tuple[tuple[str, str], ...]
    input_revision_ids: tuple[str, ...]
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


@dataclass(frozen=True)
class FeedbackTileState:
    state: str
    latest_attempt_id: str | None = None
    n_informative_best: int = 0
    decoder_attempts: int = 0


@dataclass(frozen=True)
class GenerationRecord:
    generation_id: str
    ordinal: int
    parent_generation_id: str | None
    label_frontier_ids: tuple[str, ...]
    label_frontier_sha256: str
    active_revisions: tuple[tuple[str, int, str], ...]
    accepted_revision_ids: tuple[str, ...]
    refused_revision_ids: tuple[str, ...]
    patch_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    new_certificate_ids: tuple[str, ...]
    active_projection_sha256: str
    fixed_point: bool
    statistics: dict


@dataclass
class E024Session:
    envelope: E024Envelope
    baseline: BaselineReference
    generations: list[GenerationRecord]
    revisions: dict[str, EvidenceRevision]
    patches: dict[str, CellPatch]
    dependency_sets: dict[str, DependencySet]
    certificates: dict[TileKey, CertificateRecord]
    attempts: list[FeedbackAttempt]
    attempt_ids: set[str]
    tiles: dict[TileKey, FeedbackTileState]

    @property
    def head(self) -> GenerationRecord:
        return self.generations[-1]

    @property
    def active_revision_map(self) -> dict[WindowKey, str]:
        return {
            (scan_id, int(ordinal)): revision_id
            for scan_id, ordinal, revision_id in self.head.active_revisions
        }

    @property
    def certified_count(self) -> int:
        return len(self.certificates)

    @property
    def crc_calls(self) -> int:
        return sum(int(row.decoder_invoked) for row in self.attempts)

    def summary(self) -> dict:
        states: dict[str, int] = {}
        for row in self.tiles.values():
            states[row.state] = states.get(row.state, 0) + 1
        return {
            "generation": self.head.ordinal,
            "profile": self.envelope.profile,
            "certified": self.certified_count,
            "feedback_crc_calls": self.crc_calls,
            "revisions": len(self.revisions),
            "accepted_revisions": sum(
                int(row.accepted) for row in self.revisions.values()),
            "patches": len(self.patches),
            "attempt_records": len(self.attempts),
            "tile_states": states,
            "fixed_point": bool(self.head.fixed_point),
        }


def implementation_fingerprints() -> tuple[tuple[str, str], ...]:
    """Bind an E024 state to its overlay and complete E023b substrate."""
    rows = list(receiver.implementation_fingerprints())
    modules = [importlib.import_module("paperholo.feedbackstate")]
    try:
        modules.append(importlib.import_module("paperholo.feedback"))
    except ImportError:
        pass
    for module in modules:
        path = Path(module.__file__).resolve()
        rows.append((
            module.__name__, hashlib.sha256(path.read_bytes()).hexdigest()))
    runner = (Path(__file__).resolve().parents[2]
              / "experiments/024-feedback-receiver/run_e024.py")
    if runner.is_file():
        rows.append((
            "production:e024-entrypoint",
            hashlib.sha256(runner.read_bytes()).hexdigest()))
    return tuple(rows)


def baseline_reference(
    path: Path | str,
    baseline: receiver.ReceiverSession,
) -> BaselineReference:
    source = Path(path).expanduser().resolve()
    file_sha256, file_size = stream_sha256(source)
    return BaselineReference(
        path=str(source), file_sha256=file_sha256, file_size=file_size,
        authoritative_sha256=receiver.authoritative_digest(baseline),
        format_id=baseline.envelope.format_id,
        seed=bytes(baseline.envelope.seed),
        cell_dots=int(baseline.envelope.cell_dots),
        pages=tuple(baseline.envelope.pages),
        page_cells_yx=tuple(baseline.envelope.page_cells_yx),
        rate_id=baseline.envelope.rate_id,
        ordered_capture_ids=tuple(
            scan.capture_id for scan in baseline.scans),
    )


def dependency_identity(certificate_ids: tuple[str, ...]) -> str:
    return _hash_parts(
        b"e024/dependency-set/v1",
        *[value.encode("ascii") for value in certificate_ids])


def intern_dependency_set(
    session: E024Session,
    certificate_ids,
) -> str:
    ids = tuple(sorted(set(str(value) for value in certificate_ids)))
    tile_by_id = {
        row.certificate_id: key for key, row in session.certificates.items()
    }
    missing = [value for value in ids if value not in tile_by_id]
    if missing:
        raise ValueError(
            f"dependency set refers to unknown certificates: {missing[:4]}")
    identity = dependency_identity(ids)
    tiles = tuple(sorted(tile_by_id[value] for value in ids))
    record = DependencySet(identity, ids, tiles)
    old = session.dependency_sets.get(identity)
    if old is not None and old != record:
        raise ValueError("dependency-set identity collision")
    session.dependency_sets[identity] = record
    return identity


def certificate_identity(
    format_id: str,
    seed: bytes,
    tile_key: TileKey,
    rate_id: str,
    user_bits: np.ndarray,
) -> tuple[str, str]:
    bits = np.asarray(user_bits, np.uint8).ravel()
    packed = np.packbits(bits, bitorder="little").tobytes()
    bits_sha = hashlib.sha256(packed).hexdigest()
    identity = _hash_parts(
        b"e024/certificate/v1", format_id.encode(), bytes(seed),
        repr(tuple(tile_key)).encode("ascii"), rate_id.encode(),
        str(bits.size).encode("ascii"), packed)
    return identity, bits_sha


def revision_identity(
    scan_id: str,
    placement_id: str,
    generation: int,
    arm: str,
    parent_revision_id: str | None,
    dependency_set_id: str,
    label_uses: tuple[LabelUse, ...],
    pose: AffinePose,
    emission: payloaddec.WindowEmission | None,
    accepted: bool,
    refuse_reason: str,
    metrics: dict,
) -> str:
    digest = hashlib.sha256()
    receiver._canonical_update(digest, {
        "kind": "e024/window-revision/v1",
        "scan_id": scan_id,
        "placement_id": placement_id,
        "generation": generation,
        "arm": arm,
        "parent": parent_revision_id,
        "dependencies": dependency_set_id,
        "label_uses": label_uses,
        "pose": pose,
        "emission": emission,
        "accepted": accepted,
        "refuse_reason": refuse_reason,
        "metrics": metrics,
    })
    return digest.hexdigest()


def attempt_identity(
    tile_key: TileKey,
    decoder_profile: str,
    numeric_evidence_sha256: str,
) -> str:
    return _hash_parts(
        b"e024/tile-attempt/v1", repr(tuple(tile_key)).encode("ascii"),
        decoder_profile.encode("ascii"),
        numeric_evidence_sha256.encode("ascii"))


def patch_identity(
    generation: int,
    scan_id: str,
    capture_id: str,
    page: int,
    payload_indices: np.ndarray,
    previous_owner: np.ndarray,
    new_owner: np.ndarray,
    previous_projection_sha256: str,
    new_projection_sha256: str,
) -> str:
    digest = hashlib.sha256()
    receiver._canonical_update(digest, {
        "kind": "e024/cell-patch/v1",
        "generation": generation,
        "scan": scan_id,
        "capture": capture_id,
        "page": page,
        "indices": payload_indices,
        "previous_owner": previous_owner,
        "new_owner": new_owner,
        "previous_projection": previous_projection_sha256,
        "new_projection": new_projection_sha256,
    })
    return digest.hexdigest()


def generation_identity(
    ordinal: int,
    parent_generation_id: str | None,
    label_frontier_sha256: str,
    active_revisions: tuple[tuple[str, int, str], ...],
    accepted_revision_ids: tuple[str, ...],
    refused_revision_ids: tuple[str, ...],
    patch_ids: tuple[str, ...],
    attempt_ids: tuple[str, ...],
    new_certificate_ids: tuple[str, ...],
    active_projection_sha256: str,
    fixed_point: bool,
    statistics: dict,
) -> str:
    digest = hashlib.sha256()
    receiver._canonical_update(digest, {
        "kind": "e024/generation/v1",
        "ordinal": ordinal,
        "parent": parent_generation_id,
        "label_frontier": label_frontier_sha256,
        "active_revisions": active_revisions,
        "accepted": accepted_revision_ids,
        "refused": refused_revision_ids,
        "patches": patch_ids,
        "attempts": attempt_ids,
        "new_certificates": new_certificate_ids,
        "active_projection": active_projection_sha256,
        "fixed_point": fixed_point,
        "statistics": statistics,
    })
    return digest.hexdigest()


def authoritative_digest(session: E024Session) -> str:
    digest = hashlib.sha256()
    receiver._canonical_update(digest, {
        "envelope": session.envelope,
        "baseline": session.baseline,
        "generations": session.generations,
        "revisions": session.revisions,
        "patches": session.patches,
        "dependency_sets": session.dependency_sets,
        "certificates": session.certificates,
        "attempts": session.attempts,
        "tiles": session.tiles,
    })
    return digest.hexdigest()


def _baseline_matches(
    reference: BaselineReference,
    baseline: receiver.ReceiverSession,
    path: Path,
) -> None:
    sha256, size = stream_sha256(path)
    actual = (
        sha256, size,
        receiver.authoritative_digest(baseline),
        baseline.envelope.format_id, bytes(baseline.envelope.seed),
        int(baseline.envelope.cell_dots),
        tuple(baseline.envelope.pages),
        tuple(baseline.envelope.page_cells_yx),
        baseline.envelope.rate_id,
        tuple(scan.capture_id for scan in baseline.scans),
    )
    expected = (
        reference.file_sha256, reference.file_size,
        reference.authoritative_sha256, reference.format_id,
        bytes(reference.seed), int(reference.cell_dots),
        tuple(reference.pages),
        tuple(reference.page_cells_yx), reference.rate_id,
        tuple(reference.ordered_capture_ids),
    )
    if actual != expected:
        raise ValueError("E024 generation-0 E023b artifact changed")


def validate_session(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    baseline_path: Path | str | None = None,
    require_current_implementation: bool = True,
    check_baseline_artifact: bool = True,
    validate_baseline: bool = True,
    replay_projections: bool = True,
    replay_attempts: bool = True,
    replay_decisions: bool = True,
) -> None:
    """Fail closed on state, lineage, dependency, or evidence corruption."""
    if session.envelope.algorithm_id != ALGORITHM_ID:
        raise ValueError("unknown E024 algorithm id")
    if session.envelope.profile not in FEEDBACK_PROFILES:
        raise ValueError("unknown E024 feedback profile")
    if session.envelope.config_sha256 != session.envelope.config.digest:
        raise ValueError("E024 configuration digest mismatch")
    config = session.envelope.config
    positive_integers = (
        config.block_cells, config.validation_modulus,
        config.min_payload_train, config.min_payload_validation,
        config.min_train_per_class, config.min_validation_per_class,
        config.min_label_blocks, config.pose_site_cap_train,
        config.pose_site_cap_validation, config.baseline_bp_max_iters,
        config.retry_bp_max_iters)
    if any(int(value) <= 0 for value in positive_integers):
        raise ValueError("E024 configuration has a non-positive count")
    positive_floats = (
        config.min_improvement, config.confidence_cap,
        config.context_clip, config.pose_angle_coarse_step_deg,
        config.pose_angle_fine_step_deg,
        config.pose_phase_coarse_step_cells,
        config.pose_phase_fine_step_cells)
    if any(not np.isfinite(value) or value <= 0.0
           for value in positive_floats):
        raise ValueError("E024 configuration has an invalid scale")
    if (config.pose_angle_deg < 0.0
            or config.pose_phase_cells < 0.0
            or config.pilot_mismatch_slack < 0.0
            or not 0.0 < config.bp_alpha <= 1.0
            or config.retry_bp_max_iters
            < config.baseline_bp_max_iters
            or config.max_generations < 0):
        raise ValueError("E024 configuration bounds are invalid")
    search_config = baseline.envelope.search_config
    if (session.envelope.profile in (PROFILE_REFINE, PROFILE_COMBINED)
            and not search_config.refine):
        raise ValueError(
            "E024 pose profile requires admitted E022 refinement")
    if (config.pose_angle_deg
            > search_config.refine_angle_deg + 1e-12
            or config.pose_phase_cells
            > search_config.refine_phase_cells + 1e-12):
        raise ValueError(
            "E024 pose box exceeds the admitted E022 refinement box")
    if session.envelope.evidence_policy != EVIDENCE_POLICY:
        raise ValueError("E024 evidence policy mismatch")
    seed_sha256 = session.envelope.certificate_seed_sha256
    seed_payload = session.envelope.certificate_seed_payload
    if (seed_sha256 is None) != (seed_payload is None):
        raise ValueError(
            "E024 certificate-union root is incomplete")
    if seed_payload is not None:
        if (not isinstance(seed_payload, bytes)
                or not isinstance(seed_sha256, str)
                or len(seed_sha256) != 64
                or hashlib.sha256(seed_payload).hexdigest()
                != seed_sha256):
            raise ValueError(
                "E024 certificate-union payload/hash mismatch")
    if (require_current_implementation
            and session.envelope.implementation_sha256
            != implementation_fingerprints()):
        raise ValueError(
            "E024 implementation changed since this state was created")

    if check_baseline_artifact:
        path = Path(
            baseline_path or session.baseline.path).expanduser().resolve()
        _baseline_matches(session.baseline, baseline, path)
    if validate_baseline:
        baseline.validate_invariants()
    if baseline.decode.fatal:
        raise ValueError("E024 baseline carries fatal integrity records")

    if not session.generations or session.generations[0].ordinal != 0:
        raise ValueError("E024 state lacks generation zero")
    for index, generation in enumerate(session.generations):
        if generation.ordinal != index:
            raise ValueError("E024 generation ordinals are not contiguous")
        expected_parent = (
            None if index == 0
            else session.generations[index - 1].generation_id)
        if generation.parent_generation_id != expected_parent:
            raise ValueError("E024 generation graph branches or skips")
        if index < len(session.generations) - 1 and generation.fixed_point:
            raise ValueError(
                "E024 generation follows a persisted fixed point")
    max_generation = len(session.generations) - 1
    if (session.envelope.profile != PROFILE_CONTROL
            and session.generations[0].fixed_point):
        raise ValueError(
            "non-control E024 generation zero cannot be a fixed point")

    cert_by_id: dict[str, CertificateRecord] = {}
    for key, certificate in session.certificates.items():
        if tuple(key) != tuple(certificate.tile_key):
            raise ValueError("E024 certificate key mismatch")
        if tuple(key) not in session.tiles:
            raise ValueError(
                "E024 certificate lies outside the tile universe")
        bits = np.asarray(certificate.user_bits)
        if (bits.ndim != 1 or bits.size == 0
                or not np.all((bits == 0) | (bits == 1))):
            raise ValueError("E024 certificate bits are malformed")
        identity, bits_sha = certificate_identity(
            session.baseline.format_id, session.baseline.seed,
            tuple(key), certificate.rate_id, bits)
        if (identity != certificate.certificate_id
                or bits_sha != certificate.user_bits_sha256):
            raise ValueError("E024 certificate identity mismatch")
        if certificate.rate_id != session.baseline.rate_id:
            raise ValueError("E024 certificate rate mismatch")
        if not 0 <= int(certificate.born_generation) <= max_generation:
            raise ValueError("E024 certificate birth generation is invalid")
        mask = ldpc.tile_shorten_mask(
            tuple(key[1:]), baseline.decode.spec, baseline.decode.seed)
        expected_bits = ldpc.tile_user_capacity(
            mask, baseline.decode.ldpc_spec)
        if bits.size != expected_bits:
            raise ValueError("E024 certificate payload length mismatch")
        if certificate.certificate_id in cert_by_id:
            raise ValueError("duplicate E024 certificate identity")
        cert_by_id[certificate.certificate_id] = certificate

    for dep_id, dependency in session.dependency_sets.items():
        if dep_id != dependency.dependency_set_id:
            raise ValueError("E024 dependency index mismatch")
        ids = tuple(sorted(set(dependency.certificate_ids)))
        if ids != dependency.certificate_ids:
            raise ValueError("E024 dependency set is not canonical")
        if dependency_identity(ids) != dep_id:
            raise ValueError("E024 dependency identity mismatch")
        try:
            tiles = tuple(sorted(
                cert_by_id[value].tile_key for value in ids))
        except KeyError as exc:
            raise ValueError(
                "E024 dependency references an unknown certificate") from exc
        if tiles != dependency.tile_keys:
            raise ValueError("E024 dependency tile index mismatch")

    empty_dependency = dependency_identity(())
    if empty_dependency not in session.dependency_sets:
        raise ValueError("E024 state lacks the empty dependency set")
    for certificate in session.certificates.values():
        if certificate.dependency_set_id not in session.dependency_sets:
            raise ValueError("E024 certificate dependency set unavailable")
    for dependency in session.dependency_sets.values():
        closure = set(dependency.certificate_ids)
        inherited = {
            inherited_id
            for certificate_id in dependency.certificate_ids
            for inherited_id in session.dependency_sets[
                cert_by_id[certificate_id].dependency_set_id
            ].certificate_ids
        }
        if not inherited <= closure:
            raise ValueError(
                "E024 dependency closure is not transitively closed")
    for certificate in session.certificates.values():
        dependency = session.dependency_sets[
            certificate.dependency_set_id]
        if certificate.tile_key in dependency.tile_keys:
            raise ValueError("E024 certificate depends on itself")
        if (certificate.born_generation == 0
                and dependency.certificate_ids):
            raise ValueError(
                "E024 generation-zero certificate has dependencies")
        if any(
                cert_by_id[value].born_generation
                >= certificate.born_generation
                for value in dependency.certificate_ids):
            raise ValueError(
                "E024 certificate dependency cycle or "
                "generation-barrier violation")

    baseline_certifying: dict[TileKey, str] = {}
    for attempt in baseline.attempts:
        if not attempt.certified_new:
            continue
        key = (
            int(attempt.page), int(attempt.tile_yx[0]),
            int(attempt.tile_yx[1]))
        if key in baseline_certifying:
            raise ValueError(
                "E023b baseline has duplicate certifying provenance")
        baseline_certifying[key] = attempt.attempt_id
    baseline_certificate_keys = {
        tuple(map(int, key))
        for key, outcome in baseline.decode.tiles.items()
        if outcome.state == "certified"
    }
    for key in baseline_certificate_keys:
        outcome = baseline.decode.tiles[key]
        certificate = session.certificates.get(key)
        if (outcome.user_bits is None or certificate is None
                or not np.array_equal(
                    certificate.user_bits, outcome.user_bits)
                or certificate.source != "e023b-generation0"
                or certificate.born_generation != 0
                or certificate.origin_attempt_id
                != baseline_certifying.get(key)
                or certificate.dependency_set_id != empty_dependency):
            raise ValueError(
                "E024 generation-zero certificate differs from E023b")
    external_generation_zero = {
        key: certificate
        for key, certificate in session.certificates.items()
        if (certificate.born_generation == 0
            and key not in baseline_certificate_keys)
    }
    if seed_payload is None:
        if external_generation_zero:
            raise ValueError(
                "E024 external generation-zero certificate "
                "lacks union provenance")
    else:
        union_module = importlib.import_module("paperholo.feedback")
        union_root = union_module.certificate_union_seed_records(
            seed_payload)
        if union_root["sha256"] != seed_sha256:
            raise ValueError(
                "E024 embedded certificate-union digest mismatch")
        selected_sources = [
            row for row in union_root["sources"]
            if (
                row["authoritative_sha256"]
                == session.baseline.authoritative_sha256
                and row["state_file_sha256"]
                == session.baseline.file_sha256
                and int(row["state_file_size"])
                == session.baseline.file_size)
        ]
        if len(selected_sources) != 1:
            raise ValueError(
                "E024 baseline is not an exact source artifact "
                "in the embedded union")
        union_records = union_root["records"]
        if not baseline_certificate_keys <= set(union_records):
            raise ValueError(
                "E024 embedded union omits a selected-branch certificate")
        for key in baseline_certificate_keys:
            outcome = baseline.decode.tiles[key]
            if (outcome.user_bits is None
                    or not np.array_equal(
                        union_records[key]["bits"],
                        outcome.user_bits)):
                raise ValueError(
                    "E024 embedded union conflicts with generation zero")
        expected_external = (
            set(union_records) - baseline_certificate_keys)
        if set(external_generation_zero) != expected_external:
            raise ValueError(
                "E024 external generation-zero ledger differs from "
                "the embedded union")
        for key, certificate in external_generation_zero.items():
            expected_provenance = {
                "union_sha256": seed_sha256,
                "sources": union_records[key]["sources"],
            }
            if (not np.array_equal(
                        certificate.user_bits,
                        union_records[key]["bits"])
                    or certificate.source != "certificate-union"
                    or certificate.origin_attempt_id
                    != "external:" + seed_sha256
                    or certificate.dependency_set_id != empty_dependency
                    or receiver._canonical_digest(
                        certificate.provenance)
                    != receiver._canonical_digest(
                        expected_provenance)):
                raise ValueError(
                    "E024 external generation-zero certificate "
                    "differs from the embedded union")

    scans = {scan.scan_id: scan for scan in baseline.scans}
    feedback_replay = (
        importlib.import_module("paperholo.feedback")
        if (
            replay_decisions or session.revisions
            or (replay_attempts and session.attempts))
        else None)
    payload_index_map = (
        compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed)
        if session.revisions else None)
    keystream_pages = (
        {
            int(page): compose.payload_keystream(
                baseline.decode.spec, baseline.decode.seed, int(page))
            for page in session.baseline.pages
        } if session.revisions else {})
    if replay_decisions:
        assert feedback_replay is not None
        for scan in baseline.scans:
            for emission in scan.window_evidence:
                if (emission.refused
                        or emission.calibration_score_nodes.size == 0):
                    continue
                replayed_scores, replayed_logits = (
                    feedback_replay._generation0_detector_logits(
                        emission, emission.page_cells_yx,
                        emission.raw_means))
                stored_logits = feedback_replay._physical_logits(emission)
                if (stored_logits is None
                        or not np.array_equal(
                            replayed_scores,
                            np.asarray(emission.scores, np.float32))
                        or not np.array_equal(
                            replayed_logits, stored_logits)):
                    raise ValueError(
                        "E023b generation-zero detector replay mismatch")

    revision_decisions: set[tuple[int, str, int]] = set()
    for revision_id, revision in session.revisions.items():
        if revision_id != revision.revision_id:
            raise ValueError("E024 revision index mismatch")
        scan = scans.get(revision.scan_id)
        if scan is None:
            raise ValueError("E024 revision names an unknown scan")
        ordinal = int(revision.placement_ordinal)
        if not 0 <= ordinal < len(scan.result.placements):
            raise ValueError("E024 revision placement ordinal is invalid")
        if (revision.capture_id != scan.capture_id
                or revision.placement_id != scan.placement_ids[ordinal]):
            raise ValueError("E024 revision lineage mismatch")
        if not 1 <= int(revision.generation) <= max_generation:
            raise ValueError("E024 revision generation is invalid")
        decision_key = (
            int(revision.generation), revision.scan_id, ordinal)
        if decision_key in revision_decisions:
            raise ValueError(
                "E024 generation has multiple decisions for one window")
        revision_decisions.add(decision_key)
        if revision.arm != session.envelope.profile:
            raise ValueError("E024 revision arm/profile mismatch")
        dependency = session.dependency_sets.get(
            revision.dependency_set_id)
        if dependency is None:
            raise ValueError("E024 revision dependency set is unavailable")
        if any(
                cert_by_id[value].born_generation >= revision.generation
                for value in dependency.certificate_ids):
            raise ValueError(
                "E024 revision crosses the generation label barrier")
        if revision.parent_revision_id is not None:
            parent = session.revisions.get(revision.parent_revision_id)
            if (parent is None or not parent.accepted
                    or parent.generation >= revision.generation):
                raise ValueError("E024 revision parent is not earlier")
            if (parent.scan_id != revision.scan_id
                    or parent.placement_ordinal
                    != revision.placement_ordinal):
                raise ValueError(
                    "E024 revision parent crosses a window lineage")
            parent_dependencies = session.dependency_sets[
                parent.dependency_set_id].certificate_ids
            if not set(parent_dependencies) <= set(
                    dependency.certificate_ids):
                raise ValueError(
                    "E024 revision drops inherited dependencies")
        label_ids = tuple(
            row.certificate_id for row in revision.label_uses)
        if len(label_ids) != len(set(label_ids)):
            raise ValueError("E024 revision duplicates a label use")
        for label_use in revision.label_uses:
            if (label_use.certificate_id not in cert_by_id
                    or label_use.certificate_id
                    not in dependency.certificate_ids
                    or int(label_use.n_sites) <= 0
                    or len(label_use.payload_indices_sha256) != 64):
                raise ValueError("E024 revision label use is malformed")
        if revision.accepted != (revision.emission is not None):
            raise ValueError("E024 revision acceptance/emission mismatch")
        if revision.emission is not None:
            emission = revision.emission
            placement = scan.result.placements[ordinal]
            if (emission.placement_ordinal != ordinal
                    or emission.page != placement.page
                    or not np.array_equal(
                        emission.page_cells_yx, placement.page_cells_yx)
                    or emission.raw_means.size
                    != emission.page_cells_yx.shape[0]
                    or emission.payload_index.size
                    != emission.payload_llr.size
                    or not np.isfinite(emission.payload_llr).all()):
                raise ValueError("E024 revision emission is inconsistent")
            assert feedback_replay is not None
            assert payload_index_map is not None
            mid = float(emission.diagnostics.get("mid", np.nan))
            spread = float(emission.diagnostics.get("spread", np.nan))
            generation0 = scan.window_evidence[ordinal]
            if emission.detector_profile == (
                    feedback_replay.FIXED_DETECTOR_PROFILE):
                expected_scores, _expected_logits = (
                    feedback_replay._generation0_detector_logits(
                        generation0, emission.page_cells_yx,
                        emission.raw_means))
            else:
                expected_scores = np.asarray(
                    (
                        mid
                        - np.asarray(emission.raw_means, np.float64))
                    / spread,
                    np.float32)
            if (not np.isfinite(mid) or not np.isfinite(spread)
                    or spread <= 0.0
                    or not np.array_equal(
                        np.asarray(emission.scores, np.float32),
                        expected_scores)):
                raise ValueError(
                    "E024 revision score replay mismatch")
            physical_logits = feedback_replay._physical_logits(emission)
            if physical_logits is None:
                raise ValueError(
                    "E024 accepted revision lacks detector replay")
            page_yx = np.asarray(emission.page_cells_yx, np.int64)
            pidx = payload_index_map[
                page_yx[:, 0], page_yx[:, 1]]
            selected = pidx >= 0
            expected_payload_index = pidx[selected].astype(np.int64)
            keystream = keystream_pages[int(emission.page)]
            expected_payload_llr = (
                physical_logits[selected]
                * (1.0 - 2.0 * keystream[
                    page_yx[selected, 0],
                    page_yx[selected, 1]].astype(np.float64))
            ).astype(np.float32)
            if (not np.array_equal(
                    emission.payload_index, expected_payload_index)
                    or not np.array_equal(
                        emission.payload_llr, expected_payload_llr)):
                raise ValueError(
                    "E024 revision payload replay mismatch "
                    f"for {revision_id}")
            if emission.diagnostics.get(
                    "feedback_owner_policy"
            ) != "fixed-pilot-validation-v1":
                raise ValueError(
                    "E024 revision owner-ranking policy mismatch")
            site_pos, expected, validation = (
                payloaddec._window_pilot_observations(
                    placement, baseline.decode.spec,
                    baseline.decode.seed))
            if not validation.any():
                raise ValueError(
                    "E024 revision owner rank lacks validation")
            owner_loss = payloaddec._logistic_logloss(
                physical_logits[site_pos[validation]],
                expected[validation])
            if owner_loss != emission.heldout_logloss:
                raise ValueError(
                    "E024 revision owner-rank replay mismatch")
            if revision.arm == PROFILE_RECAL:
                expected_profiles = {
                    feedback_replay.DETECTOR_PROFILE}
            elif revision.arm == PROFILE_REFINE:
                expected_profiles = {
                    feedback_replay.FIXED_DETECTOR_PROFILE}
            else:
                expected_profiles = {
                    feedback_replay.DETECTOR_PROFILE,
                    feedback_replay.FIXED_DETECTOR_PROFILE}
            if emission.detector_profile not in expected_profiles:
                raise ValueError(
                    "E024 revision detector/profile mismatch")
            if emission.detector_profile == (
                    feedback_replay.FIXED_DETECTOR_PROFILE):
                expected_mid = float(generation0.diagnostics.get(
                    "mid", np.median(generation0.raw_means)))
                expected_spread = float(generation0.diagnostics.get(
                    "spread", max(np.abs(
                        generation0.raw_means - expected_mid).mean(), 1e-6)))
                expected_context = (
                    generation0.context_fit
                    if (generation0.context_fit is not None
                        and generation0.context_fit.adopted)
                    else None)
                forbidden = {
                    "feedback_base_clip", "feedback_context_tau",
                    "feedback_context_clip",
                    "feedback_context_adopted",
                    "feedback_pava_validation_logloss",
                }
                if (not np.array_equal(
                            emission.calibration_score_nodes,
                            generation0.calibration_score_nodes)
                        or not np.array_equal(
                            emission.calibration_probability_nodes,
                            generation0.calibration_probability_nodes)
                        or mid != expected_mid
                        or spread != expected_spread
                        or receiver._canonical_digest(
                            emission.context_fit)
                        != receiver._canonical_digest(expected_context)
                        or forbidden & set(emission.diagnostics)):
                    raise ValueError(
                        "E024 fixed detector differs from generation zero")
        placement = scan.result.placements[ordinal]
        base_pose = placement.pose
        if session.envelope.profile == PROFILE_RECAL:
            if revision.pose != base_pose:
                raise ValueError(
                    "E024 recalibration revision changed pose")
        else:
            jac0 = base_pose.matrix()
            jac = revision.pose.matrix()
            origin = np.asarray(revision.pose.origin_yx, np.float64)
            phase_yx = np.asarray(revision.pose.phase_yx, np.float64)
            if (not np.isfinite(jac0).all()
                    or not np.isfinite(jac).all()
                    or not np.isfinite(origin).all()
                    or not np.isfinite(phase_yx).all()
                    or not np.isfinite(revision.pose.angle_deg)
                    or not np.isfinite(revision.pose.pitch_px)
                    or revision.pose.pitch_px <= 0.0):
                raise ValueError("E024 revision pose is non-finite")
            relative = jac @ np.linalg.inv(jac0)
            dtheta = float(np.degrees(np.arctan2(
                relative[0, 1], relative[0, 0])))
            angle = np.deg2rad(dtheta)
            expected_relative = np.array([
                [np.cos(angle), np.sin(angle)],
                [-np.sin(angle), np.cos(angle)]],
                np.float64)
            phase = np.linalg.solve(
                jac0,
                origin
                - np.asarray(base_pose.origin_yx, np.float64))
            actual_angle = float(np.degrees(np.arctan2(
                jac[0, 1], jac[1, 1])))
            actual_pitch = 0.5 * (
                float(np.hypot(*jac[:, 0]))
                + float(np.hypot(*jac[:, 1])))
            if (not np.allclose(
                        relative, expected_relative,
                        rtol=0.0, atol=1e-10)
                    or abs(dtheta)
                    > config.pose_angle_deg + 1e-10
                    or np.max(np.abs(phase))
                    > config.pose_phase_cells + 1e-10
                    or revision.pose.phase_yx != base_pose.phase_yx
                    or revision.pose.footing_factor
                    != base_pose.footing_factor
                    or not np.isclose(
                        revision.pose.angle_deg, actual_angle,
                        rtol=0.0, atol=1e-10)
                    or not np.isclose(
                        revision.pose.pitch_px, actual_pitch,
                        rtol=0.0, atol=1e-10)):
                raise ValueError(
                    "E024 revision pose exceeds the registered rigid box")
            if (revision.accepted and revision.pose != base_pose
                    and revision.emission is not None):
                generation0 = scan.window_evidence[ordinal]
                pilot_pos, expected, validation = (
                    payloaddec._window_pilot_observations(
                        placement, baseline.decode.spec,
                        baseline.decode.seed))
                if (int(validation.sum()) < search_config.min_support
                        or int((~validation).sum())
                        < search_config.min_support):
                    raise ValueError(
                        "E024 pose revision lacks pilot gate support")
                mid = float(generation0.diagnostics.get(
                    "mid", np.median(generation0.raw_means)))
                baseline_mismatch = float(np.mean(
                    (np.asarray(
                        generation0.raw_means)[pilot_pos[validation]] < mid)
                    != (expected[validation] > 0)))
                candidate_mismatch = float(np.mean(
                    (np.asarray(
                        revision.emission.raw_means)[
                            pilot_pos[validation]] < mid)
                    != (expected[validation] > 0)))
                if (candidate_mismatch
                        > baseline_mismatch
                        + config.pilot_mismatch_slack + 1e-12):
                    raise ValueError(
                        "E024 pose revision violates the E022 pilot gate")
        expected_id = revision_identity(
            revision.scan_id, revision.placement_id,
            revision.generation, revision.arm,
            revision.parent_revision_id, revision.dependency_set_id,
            revision.label_uses, revision.pose, revision.emission,
            revision.accepted, revision.refuse_reason, revision.metrics)
        if expected_id != revision_id:
            raise ValueError("E024 revision identity mismatch")

    if session.attempt_ids != {row.attempt_id for row in session.attempts}:
        raise ValueError("E024 attempt index mismatch")
    if len(session.attempt_ids) != len(session.attempts):
        raise ValueError("duplicate E024 attempt identity")
    if any(
            left.generation > right.generation
            for left, right in zip(
                session.attempts, session.attempts[1:], strict=False)):
        raise ValueError("E024 attempt ledger is not generation ordered")
    attempt_by_id: dict[str, FeedbackAttempt] = {}
    latest_max60: dict[
        tuple[int, TileKey, str], FeedbackAttempt] = {}
    baseline_profile = (
        f"{session.baseline.rate_id}/decode_tile-max"
        f"{config.baseline_bp_max_iters}-alpha{config.bp_alpha:g}")
    retry_profile = (
        f"{session.baseline.rate_id}/decode_tile-max"
        f"{config.retry_bp_max_iters}-alpha{config.bp_alpha:g}")
    for attempt in session.attempts:
        if attempt.attempt_id != attempt_identity(
                attempt.tile_key, attempt.decoder_profile,
                attempt.numeric_evidence_sha256):
            raise ValueError("E024 attempt identity mismatch")
        dependency = session.dependency_sets.get(
            attempt.dependency_set_id)
        if dependency is None:
            raise ValueError("E024 attempt dependency set is unavailable")
        if tuple(attempt.tile_key) in dependency.tile_keys:
            raise ValueError("E024 attempt depends on its target tile")
        if not 1 <= int(attempt.generation) <= max_generation:
            raise ValueError("E024 attempt generation is invalid")
        if tuple(attempt.tile_key) not in session.tiles:
            raise ValueError("E024 attempt names an unknown tile")
        if tuple(attempt.input_revision_ids) != tuple(sorted(set(
                attempt.input_revision_ids))):
            raise ValueError(
                "E024 attempt input revisions are not canonical")
        inherited: set[str] = set()
        for value in attempt.input_revision_ids:
            revision = session.revisions.get(value)
            if (revision is None or not revision.accepted
                    or revision.generation > attempt.generation):
                raise ValueError(
                    "E024 attempt names an invalid input revision")
            inherited.update(session.dependency_sets[
                revision.dependency_set_id].certificate_ids)
        if not inherited <= set(dependency.certificate_ids):
            raise ValueError(
                "E024 attempt drops revision dependencies")
        if any(
                cert_by_id[value].born_generation >= attempt.generation
                for value in dependency.certificate_ids):
            raise ValueError(
                "E024 attempt crosses the generation label barrier")
        component_ids = tuple(
            value for value, _digest in attempt.component_sha256)
        if (len(component_ids) != len(set(component_ids))
                or len(attempt.numeric_evidence_sha256) != 64
                or any(len(digest) != 64
                       for _value, digest in attempt.component_sha256)):
            raise ValueError("E024 attempt component ledger is malformed")
        if attempt.stage == "feedback-scan60":
            if (attempt.decoder_profile != baseline_profile
                    or attempt.source not in scans
                    or component_ids
                    != (scans[attempt.source].capture_id,)):
                raise ValueError(
                    "E024 scan attempt provenance is inconsistent")
            latest_max60[(
                int(attempt.generation), tuple(attempt.tile_key),
                attempt.numeric_evidence_sha256)] = attempt
        elif attempt.stage == "feedback-union60":
            if (attempt.decoder_profile != baseline_profile
                    or attempt.source != "union"):
                raise ValueError(
                    "E024 union attempt provenance is inconsistent")
            latest_max60[(
                int(attempt.generation), tuple(attempt.tile_key),
                attempt.numeric_evidence_sha256)] = attempt
        elif attempt.stage == "feedback-retry150":
            parent = latest_max60.get((
                int(attempt.generation), tuple(attempt.tile_key),
                attempt.numeric_evidence_sha256))
            single_component_scan_parent = (
                parent is not None
                and parent.stage == "feedback-scan60"
                and len(attempt.component_sha256) == 1
                and parent.component_sha256
                == attempt.component_sha256)
            if (attempt.decoder_profile != retry_profile
                    or attempt.source != "union"
                    or parent is None
                    or (
                        parent.stage != "feedback-union60"
                        and not single_component_scan_parent)
                    or parent.state != "attempted_failed"
                    or not parent.decoder_invoked
                    or parent.component_sha256
                    != attempt.component_sha256
                    or parent.input_revision_ids
                    != attempt.input_revision_ids
                    or parent.dependency_set_id
                    != attempt.dependency_set_id):
                raise ValueError(
                    "E024 retry lacks its failed max-60 evidence parent")
        else:
            raise ValueError("E024 attempt has an unknown stage")

        mask = baseline.decode.shorten_mask(attempt.tile_key[1:])
        expected_nonshort = int((~mask).sum())
        expected_k = max(
            baseline.decode.ldpc_spec.k_bits - int(mask.sum()), 0)
        degenerate = (
            ldpc.tile_user_capacity(
                mask, baseline.decode.ldpc_spec) == 0)
        if (attempt.n_nonshort != expected_nonshort
                or attempt.k_eff != expected_k
                or not np.isfinite(attempt.coverage)
                or not 0.0 <= attempt.coverage <= 1.0
                or not 0 <= attempt.n_informative
                <= attempt.n_nonshort
                or attempt.n_iters < 0
                or (not degenerate and attempt.n_erased
                    != attempt.n_nonshort
                    - attempt.n_informative)):
            raise ValueError("E024 attempt accounting is inconsistent")
        if attempt.state == "degenerate":
            valid_state = (
                not attempt.decoder_invoked and degenerate
                and attempt.n_informative == 0
                and attempt.n_erased == 0
                and attempt.n_iters == 0
                and attempt.syndrome_ok is None
                and attempt.crc_ok is None)
        elif attempt.state == "below_attempt_floor":
            valid_state = (
                not attempt.decoder_invoked and not degenerate
                and attempt.n_informative < attempt.k_eff
                and attempt.n_iters == 0
                and attempt.syndrome_ok is None
                and attempt.crc_ok is None)
        elif attempt.state == "attempted_failed":
            valid_state = (
                attempt.decoder_invoked and not degenerate
                and attempt.n_informative >= attempt.k_eff
                and isinstance(
                    attempt.syndrome_ok, (bool, np.bool_))
                and isinstance(attempt.crc_ok, (bool, np.bool_))
                and not (
                    bool(attempt.syndrome_ok)
                    and bool(attempt.crc_ok)))
        elif attempt.state == "certified":
            valid_state = (
                attempt.decoder_invoked and not degenerate
                and attempt.n_informative >= attempt.k_eff
                and attempt.syndrome_ok is True
                and attempt.crc_ok is True)
        else:
            valid_state = False
        if (not valid_state
                or attempt.certified_new
                != (attempt.state == "certified")):
            raise ValueError(
                "E024 attempt state semantics are inconsistent")
        attempt_by_id[attempt.attempt_id] = attempt

    for certificate in session.certificates.values():
        if certificate.born_generation == 0:
            continue
        attempt = attempt_by_id.get(certificate.origin_attempt_id)
        if (attempt is None or not attempt.certified_new
                or attempt.generation != certificate.born_generation
                or tuple(attempt.tile_key) != certificate.tile_key
                or attempt.dependency_set_id
                != certificate.dependency_set_id):
            raise ValueError("E024 feedback certificate lacks its attempt")
    for attempt in session.attempts:
        if not attempt.certified_new:
            continue
        certificate = session.certificates.get(tuple(attempt.tile_key))
        if (certificate is None
                or certificate.origin_attempt_id != attempt.attempt_id):
            raise ValueError(
                "E024 certifying attempt lacks its certificate")

    for patch_id, patch in session.patches.items():
        if patch_id != patch.patch_id:
            raise ValueError("E024 patch index mismatch")
        scan = scans.get(patch.scan_id)
        if scan is None:
            raise ValueError("E024 patch names an unknown scan")
        if patch.capture_id != scan.capture_id:
            raise ValueError("E024 patch crosses a capture boundary")
        if (not 1 <= int(patch.generation) <= max_generation
                or int(patch.page) not in session.baseline.pages):
            raise ValueError("E024 patch generation/page is invalid")
        arrays = (
            np.asarray(patch.payload_indices),
            np.asarray(patch.previous_owner),
            np.asarray(patch.new_owner),
        )
        if not (arrays[0].ndim == arrays[1].ndim == arrays[2].ndim == 1
                and arrays[0].size == arrays[1].size == arrays[2].size
                and arrays[0].size > 0
                and np.issubdtype(arrays[0].dtype, np.integer)
                and (arrays[0].size < 2
                     or np.all(arrays[0][1:] > arrays[0][:-1]))):
            raise ValueError("E024 cell patch is malformed")
        expected_patch_id = patch_identity(
            patch.generation, patch.scan_id, patch.capture_id, patch.page,
            arrays[0], arrays[1], arrays[2],
            patch.previous_projection_sha256,
            patch.new_projection_sha256)
        if patch_id != expected_patch_id:
            raise ValueError("E024 patch identity mismatch")

    feedback_module = (
        importlib.import_module("paperholo.feedback")
        if (
            replay_decisions or replay_projections
            or (replay_attempts and session.attempts))
        else None)
    previous_active: dict[WindowKey, str] = {}
    active_by_generation: dict[int, dict[WindowKey, str]] = {}
    for generation in session.generations:
        ordinal = generation.ordinal
        frontier = tuple(generation.label_frontier_ids)
        if frontier != tuple(sorted(set(frontier))):
            raise ValueError(
                "E024 generation label frontier is not canonical")
        expected_frontier = tuple(sorted(
            certificate.certificate_id
            for certificate in session.certificates.values()
            if (certificate.born_generation == 0 if ordinal == 0
                else certificate.born_generation < ordinal)))
        if frontier != expected_frontier:
            raise ValueError(
                "E024 generation label frontier violates the barrier")
        frontier_sha = _hash_parts(
            b"e024/label-frontier/v1",
            *[value.encode("ascii") for value in frontier])
        if frontier_sha != generation.label_frontier_sha256:
            raise ValueError("E024 label frontier digest mismatch")

        accepted = tuple(sorted(
            revision.revision_id
            for revision in session.revisions.values()
            if revision.generation == ordinal and revision.accepted))
        refused = tuple(sorted(
            revision.revision_id
            for revision in session.revisions.values()
            if revision.generation == ordinal and not revision.accepted))
        for revision_id in (*accepted, *refused):
            revision = session.revisions[revision_id]
            expected_revision_parent = previous_active.get((
                revision.scan_id, revision.placement_ordinal))
            if revision.parent_revision_id != expected_revision_parent:
                raise ValueError(
                    "E024 revision branches from a stale window parent")
        patch_ids = tuple(sorted(
            patch.patch_id for patch in session.patches.values()
            if patch.generation == ordinal))
        attempt_ids = tuple(
            attempt.attempt_id for attempt in session.attempts
            if attempt.generation == ordinal)
        new_certificate_ids = (
            () if ordinal == 0 else tuple(sorted(
                certificate.certificate_id
                for certificate in session.certificates.values()
                if certificate.born_generation == ordinal)))
        if generation.accepted_revision_ids != accepted:
            raise ValueError(
                "E024 generation accepted-revision ledger mismatch")
        if generation.refused_revision_ids != refused:
            raise ValueError(
                "E024 generation refused-revision ledger mismatch")
        if generation.patch_ids != patch_ids:
            raise ValueError("E024 generation patch ledger mismatch")
        if generation.attempt_ids != attempt_ids:
            raise ValueError("E024 generation attempt ledger mismatch")
        if generation.new_certificate_ids != new_certificate_ids:
            raise ValueError(
                "E024 generation certificate ledger mismatch")

        expected_active = dict(previous_active)
        for revision_id in accepted:
            revision = session.revisions[revision_id]
            expected_active[(
                revision.scan_id,
                revision.placement_ordinal)] = revision_id
        active_rows = tuple(sorted(
            (scan_id, int(placement_ordinal), revision_id)
            for (scan_id, placement_ordinal), revision_id
            in expected_active.items()))
        if generation.active_revisions != active_rows:
            raise ValueError(
                "E024 generation active-revision projection mismatch")
        active = {
            (scan_id, int(placement_ordinal)): revision_id
            for scan_id, placement_ordinal, revision_id in active_rows
        }
        active_by_generation[int(ordinal)] = active

        if ordinal > 0:
            reason = generation.statistics.get("reason")
            terminal_reasons = {
                "no_reachable_windows", "no_new_certificates",
                "no_reachable_windows_after_certificates"}
            if (generation.fixed_point
                    != (reason in terminal_reasons)
                    or (reason == "new_feedback_frontier"
                        and generation.fixed_point)
                    or reason not in (
                        *terminal_reasons, "new_feedback_frontier")):
                raise ValueError(
                    "E024 fixed-point flag/reason mismatch")

        if replay_projections:
            assert feedback_module is not None
            active_sha = feedback_module._active_projection_digest(
                baseline, active, session if active else None)
            if active_sha != generation.active_projection_sha256:
                raise ValueError(
                    "E024 active projection digest mismatch")
            replayed_patches = feedback_module._build_patches(
                session, baseline, previous_active, active, ordinal)
            replayed_ids = tuple(sorted(
                patch.patch_id for patch in replayed_patches))
            if replayed_ids != patch_ids:
                raise ValueError("E024 cell-patch replay mismatch")

        expected_id = generation_identity(
            ordinal, generation.parent_generation_id,
            generation.label_frontier_sha256,
            generation.active_revisions,
            generation.accepted_revision_ids,
            generation.refused_revision_ids,
            generation.patch_ids, generation.attempt_ids,
            generation.new_certificate_ids,
            generation.active_projection_sha256,
            generation.fixed_point, generation.statistics)
        if expected_id != generation.generation_id:
            raise ValueError("E024 generation identity mismatch")
        previous_active = active

    if replay_attempts and session.attempts:
        assert feedback_module is not None
        for position, attempt in enumerate(session.attempts):
            active = active_by_generation[int(attempt.generation)]
            evidence = feedback_module.resolve_target_evidence(
                session, baseline, tuple(attempt.tile_key), active)
            if evidence is None:
                raise ValueError(
                    "E024 attempt has no replayable target evidence")
            if attempt.stage == "feedback-scan60":
                rows = [
                    row for row in evidence.components
                    if row.scan_id == attempt.source]
                if len(rows) != 1:
                    raise ValueError(
                        "E024 scan attempt source is not replayable")
                component = rows[0]
                index = component.index
                llr_values = component.llr
                numeric_sha256 = component.numeric_sha256
                component_sha256 = ((
                    component.capture_id,
                    component.numeric_sha256),)
                revision_ids = component.revision_ids
                dependency_ids = component.dependency_ids
                max_iters = config.baseline_bp_max_iters
            else:
                index = evidence.union_index
                llr_values = evidence.union_llr
                numeric_sha256 = evidence.union_numeric_sha256
                component_sha256 = tuple(
                    (row.capture_id, row.numeric_sha256)
                    for row in evidence.components)
                revision_ids = evidence.revision_ids
                dependency_ids = evidence.dependency_ids
                max_iters = (
                    config.retry_bp_max_iters
                    if attempt.stage == "feedback-retry150"
                    else config.baseline_bp_max_iters)
            dependency = session.dependency_sets[
                attempt.dependency_set_id]
            if (attempt.numeric_evidence_sha256 != numeric_sha256
                    or attempt.component_sha256 != component_sha256
                    or attempt.input_revision_ids
                    != tuple(sorted(set(revision_ids)))
                    or dependency.certificate_ids
                    != tuple(sorted(set(dependency_ids)))):
                raise ValueError(
                    "E024 attempt evidence replay mismatch")
            evaluation = payloaddec.evaluate_tile(
                llr_values, index, baseline.decode.spec,
                baseline.decode.seed, attempt.tile_key[1:],
                baseline.decode.ldpc_spec, max_iters=max_iters,
                alpha=config.bp_alpha)
            replayed = (
                evaluation.state, bool(evaluation.decoder_invoked),
                int(evaluation.k_eff), int(evaluation.n_nonshort),
                int(evaluation.n_informative), float(evaluation.coverage),
                int(evaluation.n_iters), evaluation.syndrome_ok,
                evaluation.crc_ok, int(evaluation.n_erased))
            stored = (
                attempt.state, bool(attempt.decoder_invoked),
                int(attempt.k_eff), int(attempt.n_nonshort),
                int(attempt.n_informative), float(attempt.coverage),
                int(attempt.n_iters), attempt.syndrome_ok,
                attempt.crc_ok, int(attempt.n_erased))
            if replayed != stored:
                raise ValueError(
                    "E024 attempt numerical replay mismatch")
            if attempt.certified_new:
                certificate = session.certificates.get(
                    tuple(attempt.tile_key))
                if (evaluation.user_bits is None
                        or certificate is None
                        or certificate.origin_attempt_id
                        != attempt.attempt_id
                        or not np.array_equal(
                            certificate.user_bits,
                            evaluation.user_bits)):
                    raise ValueError(
                        "E024 certificate bits fail decoder replay")

            if position > 0 and session.attempts[position - 1].generation > (
                    attempt.generation):
                raise ValueError(
                    "E024 attempt replay chronology is inconsistent")

    baseline_states = payloaddec.full_tile_states(baseline.decode)
    if set(session.tiles) != set(baseline_states):
        raise ValueError("E024 tile universe differs from generation zero")
    attempts_by_tile: dict[TileKey, list[FeedbackAttempt]] = {}
    for attempt in session.attempts:
        attempts_by_tile.setdefault(
            tuple(attempt.tile_key), []).append(attempt)
    for key, tile in session.tiles.items():
        rows = attempts_by_tile.get(tuple(key), [])
        baseline_outcome = baseline.decode.tiles.get(key)
        baseline_attempts = (
            0 if baseline_outcome is None else baseline_outcome.attempts)
        baseline_best = (
            0 if baseline_outcome is None
            else baseline_outcome.n_informative_best)
        expected_attempts = baseline_attempts + sum(
            int(row.decoder_invoked) for row in rows)
        expected_best = max(
            [baseline_best, *[row.n_informative for row in rows]])
        expected_latest = rows[-1].attempt_id if rows else None
        expected_state = (
            "certified" if key in session.certificates
            else rows[-1].state if rows else baseline_states[key])
        if (tile.state != expected_state
                or tile.latest_attempt_id != expected_latest
                or tile.decoder_attempts != expected_attempts
                or tile.n_informative_best != expected_best):
            raise ValueError("E024 tile ledger mismatch")
        if (baseline_states[key] == "certified"
                and key not in session.certificates):
            raise ValueError("E024 lost a generation-zero certificate")

    if replay_decisions:
        assert feedback_module is not None
        generation_zero_certificates = {
            key: copy.deepcopy(certificate)
            for key, certificate in session.certificates.items()
            if certificate.born_generation == 0
        }
        generation_zero_tiles = initial_tile_states(baseline)
        for key in generation_zero_certificates:
            generation_zero_tiles[key] = replace(
                generation_zero_tiles[key], state="certified")
        replayed_session = E024Session(
            envelope=copy.deepcopy(session.envelope),
            baseline=copy.deepcopy(session.baseline),
            generations=[copy.deepcopy(session.generations[0])],
            revisions={},
            patches={},
            dependency_sets={
                empty_dependency: copy.deepcopy(
                    session.dependency_sets[empty_dependency])},
            certificates=generation_zero_certificates,
            attempts=[],
            attempt_ids=set(),
            tiles=generation_zero_tiles,
        )
        for stored_generation in session.generations[1:]:
            advanced, _report = (
                feedback_module._run_feedback_generation_unvalidated(
                    replayed_session, baseline))
            if advanced is replayed_session:
                raise ValueError(
                    "E024 persisted generation is unreachable in replay")
            if advanced.head != stored_generation:
                raise ValueError(
                    "E024 generation decision replay mismatch at "
                    f"generation {stored_generation.ordinal}")
            replayed_session = advanced
        if authoritative_digest(replayed_session) != authoritative_digest(
                session):
            raise ValueError(
                "E024 sequential production replay differs from state")

    if session.envelope.profile == PROFILE_CONTROL:
        if (len(session.generations) != 1
                or not session.generations[0].fixed_point
                or session.revisions or session.patches
                or session.attempts):
            raise ValueError(
                "E024 control profile is not an exact generation-zero no-op")


def save_session(
    path: Path | str,
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    baseline_path: Path | str | None = None,
) -> None:
    validate_session(
        session, baseline, baseline_path=baseline_path,
        validate_baseline=False)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    payload = {
        "magic": STATE_MAGIC,
        "version": STATE_VERSION,
        "session": session,
    }
    tmp.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, target)


def load_session(
    path: Path | str,
    *,
    baseline_path: Path | str | None = None,
) -> tuple[E024Session, receiver.ReceiverSession]:
    payload = pickle.loads(Path(path).read_bytes())
    if not isinstance(payload, dict) or payload.get("magic") != STATE_MAGIC:
        raise ValueError(f"{path} is not an E024 state")
    if int(payload.get("version", -1)) != STATE_VERSION:
        raise ValueError(
            f"E024 state version {payload.get('version')} != {STATE_VERSION}")
    session = payload.get("session")
    if not isinstance(session, E024Session):
        raise ValueError(f"{path} carries an invalid E024 payload")
    source = Path(baseline_path or session.baseline.path)
    baseline = receiver.load_session(source)
    validate_session(
        session, baseline, baseline_path=source,
        validate_baseline=False)
    return session, baseline


def initial_tile_states(
    baseline: receiver.ReceiverSession,
) -> dict[TileKey, FeedbackTileState]:
    states = payloaddec.full_tile_states(baseline.decode)
    out = {}
    for key, state in states.items():
        source = baseline.decode.tiles.get(key)
        out[tuple(key)] = FeedbackTileState(
            state=state,
            n_informative_best=(
                0 if source is None else int(source.n_informative_best)),
            decoder_attempts=(
                0 if source is None else int(source.attempts)),
        )
    return out


def projection_digest(
    pages: dict[int, dict[str, np.ndarray]],
) -> str:
    digest = hashlib.sha256()
    receiver._canonical_update(digest, pages)
    return digest.hexdigest()

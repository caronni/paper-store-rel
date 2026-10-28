"""E024 certified-label feedback over an immutable E023b receiver state.

The implementation is deliberately an overlay.  It imports generation zero,
reconstructs exact printed labels from CRC-certified tiles, proposes bounded
detector and pose revisions, resolves one interpretation per physical
capture, and retries only unresolved tiles whose legal evidence changed.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pickle
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from scipy import ndimage

from . import compose, ldpc, payloaddec, receiver
from .acquire import apply_calibration
from .feedbackstate import (
    ALGORITHM_ID,
    EVIDENCE_POLICY,
    FEEDBACK_PROFILES,
    PROFILE_COMBINED,
    PROFILE_CONTROL,
    PROFILE_RECAL,
    PROFILE_REFINE,
    CellPatch,
    CertificateRecord,
    DependencySet,
    E024Envelope,
    E024Session,
    EvidenceRevision,
    FeedbackAttempt,
    FeedbackConfig,
    FeedbackTileState,
    GenerationRecord,
    LabelUse,
    TileKey,
    WindowKey,
    attempt_identity,
    authoritative_digest,
    baseline_reference,
    certificate_identity,
    dependency_identity,
    generation_identity,
    implementation_fingerprints,
    initial_tile_states,
    intern_dependency_set,
    patch_identity,
    projection_digest,
    revision_identity,
    stream_sha256,
    validate_session,
)
from .pilotsearch import AffinePose, PlacedWindow, SearchConfig


UNION_MAGIC = "e023b-certificate-union-v1"
UNION_VERSION = 1
UNION_ALGORITHM = "certificate-only/correlated-views/v1"
DETECTOR_PROFILE = "e024-dense-pava-context-v1"
FIXED_DETECTOR_PROFILE = "e024-fixed-generation0-detector-v1"

_TRUSTED_UNION_PROOFS: set[tuple[str, str, str]] = set()
_UNION_MERGER_MODULES: dict[str, object] = {}


def _hash_parts(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def _array_digest(value: np.ndarray, dtype=None) -> str:
    array = np.ascontiguousarray(
        np.asarray(value) if dtype is None else np.asarray(value, dtype))
    return _hash_parts(
        array.dtype.str.encode("ascii"),
        repr(tuple(array.shape)).encode("ascii"),
        memoryview(array).cast("B"))


def _descriptor_view(baseline: receiver.ReceiverSession):
    class DescriptorView:
        format_id = baseline.envelope.format_id
        seed = baseline.envelope.seed
        ldpc_rate = baseline.envelope.rate_id
        cell_dots = baseline.envelope.cell_dots

        @staticmethod
        def spec():
            return baseline.decode.spec

    return DescriptorView()


def _empty_dependency(session: E024Session) -> str:
    identity = dependency_identity(())
    if identity not in session.dependency_sets:
        session.dependency_sets[identity] = DependencySet(
            identity, (), ())
    return identity


def _certificate_attempts(
    baseline: receiver.ReceiverSession,
) -> dict[TileKey, str]:
    out = {}
    for attempt in baseline.attempts:
        if not attempt.certified_new:
            continue
        key = (int(attempt.page), *map(int, attempt.tile_yx))
        if key in out:
            raise ValueError(
                f"E023b has duplicate certifying attempts for {key}")
        out[key] = attempt.attempt_id
    return out


def _add_certificate(
    session: E024Session,
    *,
    key: TileKey,
    user_bits: np.ndarray,
    source: str,
    origin_attempt_id: str,
    born_generation: int,
    dependency_set_id: str,
    provenance: dict | None = None,
) -> CertificateRecord:
    bits = np.asarray(user_bits, np.uint8).ravel().copy()
    identity, bits_sha = certificate_identity(
        session.baseline.format_id, session.baseline.seed, key,
        session.baseline.rate_id, bits)
    old = session.certificates.get(key)
    if old is not None:
        if old.certificate_id != identity:
            raise payloaddec.FatalIntegrityError(
                f"conflicting E024 certificates for tile {key}")
        return old
    record = CertificateRecord(
        certificate_id=identity, tile_key=key,
        rate_id=session.baseline.rate_id, user_bits=bits,
        user_bits_sha256=bits_sha, source=str(source),
        origin_attempt_id=str(origin_attempt_id),
        born_generation=int(born_generation),
        dependency_set_id=dependency_set_id,
        provenance={} if provenance is None else copy.deepcopy(provenance),
    )
    session.certificates[key] = record
    return record


def _canonical_json_bytes(value) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "certificate union contains non-canonical JSON values") from exc


def _parse_certificate_union(
    raw: bytes,
    source: Path | str,
) -> dict:
    try:
        payload = json.loads(raw)
    except (
            UnicodeDecodeError, json.JSONDecodeError,
            TypeError, ValueError) as exc:
        raise ValueError(
            f"{source} is not valid certificate-union JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"{source} certificate-union root is not an object")
    version = payload.get("version")
    if (payload.get("magic") != UNION_MAGIC
            or type(version) is not int
            or version != UNION_VERSION):
        raise ValueError(f"{source} is not an E023b certificate union")
    if payload.get("algorithm") != UNION_ALGORITHM:
        raise ValueError("certificate union algorithm is not registered")
    _canonical_json_bytes(payload)
    return payload


def _load_certificate_union(
    path: Path | str,
    session: E024Session,
) -> None:
    source = Path(path).expanduser().resolve()
    raw = source.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    if session.envelope.certificate_seed_sha256 != sha256:
        raise ValueError("certificate-union SHA-256 changed")
    if session.envelope.certificate_seed_payload != raw:
        raise ValueError(
            "certificate-union payload differs from its durable root")
    payload = _parse_certificate_union(raw, source)
    implementation = payload.get("implementation", {})
    merge_script = (
        Path(__file__).resolve().parents[2]
        / "experiments/023b-integrated-receiver/merge_e023b.py")
    expected_implementation = {
        "merge_script_sha256": hashlib.sha256(
            merge_script.read_bytes()).hexdigest(),
        "receiver_sha256": hashlib.sha256(
            Path(receiver.__file__).read_bytes()).hexdigest(),
    }
    if _canonical_json_bytes(implementation) != (
            _canonical_json_bytes(expected_implementation)):
        raise ValueError(
            "certificate union implementation fingerprint mismatch")
    compatibility = payload.get("compatibility", {})
    if not isinstance(compatibility, dict):
        raise ValueError(
            "certificate union compatibility is malformed")
    expected = {
        "format_id": session.baseline.format_id,
        "seed_hex": session.baseline.seed.hex(),
        "cell_dots": session.baseline.cell_dots,
        "page_cells_yx": list(session.baseline.page_cells_yx),
        "pages": list(session.baseline.pages),
        "rate_id": session.baseline.rate_id,
        "ordered_capture_ids": list(
            session.baseline.ordered_capture_ids),
    }
    for name in (
            "format_id", "seed_hex", "cell_dots", "page_cells_yx", "pages",
            "rate_id", "ordered_capture_ids"):
        if compatibility.get(name) != expected[name]:
            raise ValueError(
                f"certificate union compatibility mismatch in {name}")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(
            "certificate union provenance is malformed")
    sources = provenance.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError(
            "certificate union requires at least two source branches")
    source_by_label = {}
    authoritative_ids = set()
    for row in sources:
        if not isinstance(row, dict):
            raise ValueError(
                "certificate union source provenance is malformed")
        label = row.get("label")
        authoritative = row.get("authoritative_sha256")
        if (not isinstance(label, str) or not label
                or label in source_by_label
                or not isinstance(authoritative, str)
                or len(authoritative) != 64
                or authoritative in authoritative_ids
                or not isinstance(row.get("state_file_sha256"), str)
                or len(row["state_file_sha256"]) != 64
                or type(row.get("state_file_size")) is not int
                or row["state_file_size"] <= 0):
            raise ValueError(
                "certificate union source provenance is malformed")
        source_by_label[label] = row
        authoritative_ids.add(authoritative)
    selected_sources = [
        row for row in sources
        if row.get("authoritative_sha256")
        == session.baseline.authoritative_sha256]
    if len(selected_sources) != 1:
        raise ValueError(
            "certificate union is not bound to the selected E023b branch")
    selected = selected_sources[0]
    if (selected.get("state_file_sha256")
            != session.baseline.file_sha256
            or selected.get("state_file_size")
            != session.baseline.file_size):
        raise ValueError(
            "certificate union selected-branch artifact mismatch")

    rows = payload.get("certificates", [])
    if not isinstance(rows, list):
        raise ValueError("certificate union certificate ledger is malformed")
    imported: list[tuple[TileKey, np.ndarray, list[dict]]] = []
    seen_keys: set[TileKey] = set()
    for position, row in enumerate(rows):
        try:
            key = (
                int(row["page"]), int(row["tile_yx"][0]),
                int(row["tile_yx"][1]))
            size = int(row["n_user_bits"])
            packed = bytes.fromhex(row["user_bits_packed_hex"])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ValueError(
                f"certificate union row {position} is malformed") from exc
        if key not in session.tiles:
            raise ValueError(
                f"certificate union tile {key} is outside the page")
        if key in seen_keys:
            raise ValueError(
                f"certificate union duplicates tile {key}")
        seen_keys.add(key)
        if row.get("pack_bitorder") != "little":
            raise ValueError("unsupported certificate-union bit order")
        if size <= 0 or size > 8 * len(packed):
            raise ValueError(
                f"certificate union row {position} has invalid bit length")
        row_sources = row.get("sources")
        if not isinstance(row_sources, list) or not row_sources:
            raise ValueError(
                f"certificate union row {position} lacks provenance")
        seen_labels = set()
        for source_row in row_sources:
            if not isinstance(source_row, dict):
                raise ValueError(
                    f"certificate union row {position} has malformed "
                    "source provenance")
            label = source_row.get("label")
            attempt = source_row.get("attempt")
            if (label not in source_by_label or label in seen_labels
                    or not isinstance(source_row.get("certified_by"), str)
                    or not isinstance(attempt, dict)
                    or attempt.get("decoder_invoked") is not True
                    or attempt.get("syndrome_ok") is not True
                    or attempt.get("crc_ok") is not True
                    or attempt.get("certified_new") is not True
                    or not isinstance(attempt.get("attempt_id"), str)
                    or len(attempt["attempt_id"]) != 64
                    or not isinstance(
                        attempt.get("evidence_digest"), str)
                    or len(attempt["evidence_digest"]) != 64):
                raise ValueError(
                    f"certificate union row {position} has unproven "
                    "certifying provenance")
            expected_profile = (
                f"{session.baseline.rate_id}/decode_tile-max"
                f"{150 if attempt.get('stage') == 'retry150' else 60}"
                "-alpha0.8")
            if (attempt.get("stage")
                    not in ("scan", "union", "retry150")
                    or attempt.get("decoder_profile")
                    != expected_profile):
                raise ValueError(
                    f"certificate union row {position} has an "
                    "unregistered certifying attempt")
            seen_labels.add(label)
        bits = np.unpackbits(
            np.frombuffer(packed, np.uint8),
            bitorder="little")[:size].astype(np.uint8, copy=False)
        imported.append((
            key, bits.copy(), copy.deepcopy(row_sources)))

    _prove_certificate_union(
        source, payload, sha256, merge_script,
        expected_implementation)

    empty = _empty_dependency(session)
    for key, bits, row_sources in imported:
        _add_certificate(
            session, key=key, user_bits=bits, source="certificate-union",
            origin_attempt_id="external:" + sha256,
            born_generation=0, dependency_set_id=empty,
            provenance={"union_sha256": sha256,
                        "sources": row_sources})
        session.tiles[key] = replace(
            session.tiles[key], state="certified")


def _prove_certificate_union(
    source: Path | str,
    payload: dict,
    union_sha256: str,
    merge_script: Path,
    implementation: dict,
) -> None:
    """Replay the fingerprinted E023b merger before trusting its output."""
    proof_key = (
        union_sha256,
        implementation["merge_script_sha256"],
        implementation["receiver_sha256"],
    )
    if proof_key in _TRUSTED_UNION_PROOFS:
        return

    module = _UNION_MERGER_MODULES.get(
        implementation["merge_script_sha256"])
    if module is None:
        module_name = (
            "_paperholo_e024_union_"
            + implementation["merge_script_sha256"][:16])
        spec = importlib.util.spec_from_file_location(
            module_name, merge_script)
        if spec is None or spec.loader is None:
            raise ValueError(
                "certificate union merger cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        _UNION_MERGER_MODULES[
            implementation["merge_script_sha256"]] = module

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(
            "certificate union provenance is malformed")
    source_rows = provenance.get("sources")
    if not isinstance(source_rows, list):
        raise ValueError(
            "certificate union source provenance is malformed")
    try:
        specs = [
            module.SourceSpec(
                str(row["label"]),
                Path(row["state_path"]).expanduser().resolve())
            for row in source_rows
        ]
    except (
            KeyError, TypeError, ValueError,
            AttributeError, IndexError) as exc:
        raise ValueError(
            "certificate union source paths are malformed") from exc
    if any(
            str(spec.path) != str(row.get("state_path"))
            for spec, row in zip(specs, source_rows, strict=True)):
        raise ValueError(
            "certificate union source paths are not canonical")
    try:
        rebuilt = module.build_union(module.load_sources(specs))
    except (
            OSError, ValueError, TypeError, AttributeError,
            pickle.UnpicklingError, EOFError) as exc:
        raise ValueError(
            f"certificate union source replay failed: {exc}") from exc
    if _canonical_json_bytes(rebuilt) != _canonical_json_bytes(payload):
        raise ValueError(
            f"{source} differs from a replay of its certified sources")
    _TRUSTED_UNION_PROOFS.add(proof_key)


def validate_certificate_union(path: Path | str) -> dict:
    """Open and prove an E023b certificate union without loading a footing."""
    source = Path(path).expanduser().resolve()
    raw = source.read_bytes()
    union_sha256 = hashlib.sha256(raw).hexdigest()
    payload = _parse_certificate_union(raw, source)
    merge_script = (
        Path(__file__).resolve().parents[2]
        / "experiments/023b-integrated-receiver/merge_e023b.py")
    expected_implementation = {
        "merge_script_sha256": hashlib.sha256(
            merge_script.read_bytes()).hexdigest(),
        "receiver_sha256": hashlib.sha256(
            Path(receiver.__file__).read_bytes()).hexdigest(),
    }
    if _canonical_json_bytes(payload.get("implementation")) != (
            _canonical_json_bytes(expected_implementation)):
        raise ValueError(
            "certificate union implementation fingerprint mismatch")
    _prove_certificate_union(
        source, payload, union_sha256, merge_script,
        expected_implementation)
    return {
        "path": str(source),
        "sha256": union_sha256,
        "size": len(raw),
        "source_count": len(
            payload.get("provenance", {}).get("sources", [])),
        "certificate_count": len(payload.get("certificates", [])),
        "sources": [
            {
                "label": row["label"],
                "state_file_sha256": row["state_file_sha256"],
                "state_file_size": int(row["state_file_size"]),
                "authoritative_sha256": row["authoritative_sha256"],
            }
            for row in payload["provenance"]["sources"]
        ],
    }


def certificate_union_seed_records(raw: bytes) -> dict:
    """Re-prove an embedded union root and return its exact certificate rows."""
    payload = _parse_certificate_union(
        raw, "<embedded E024 certificate union>")
    merge_script = (
        Path(__file__).resolve().parents[2]
        / "experiments/023b-integrated-receiver/merge_e023b.py")
    implementation = {
        "merge_script_sha256": hashlib.sha256(
            merge_script.read_bytes()).hexdigest(),
        "receiver_sha256": hashlib.sha256(
            Path(receiver.__file__).read_bytes()).hexdigest(),
    }
    if _canonical_json_bytes(payload.get("implementation")) != (
            _canonical_json_bytes(implementation)):
        raise ValueError(
            "embedded certificate union implementation mismatch")
    sha256 = hashlib.sha256(raw).hexdigest()
    _prove_certificate_union(
        "<embedded E024 certificate union>", payload, sha256,
        merge_script, implementation)
    records = {}
    for row in payload["certificates"]:
        key = (
            int(row["page"]), int(row["tile_yx"][0]),
            int(row["tile_yx"][1]))
        size = int(row["n_user_bits"])
        packed = bytes.fromhex(row["user_bits_packed_hex"])
        bits = np.unpackbits(
            np.frombuffer(packed, np.uint8),
            bitorder="little")[:size].astype(np.uint8, copy=False)
        records[key] = {
            "bits": bits.copy(),
            "sources": copy.deepcopy(row["sources"]),
        }
    return {
        "sha256": sha256,
        "records": records,
        "sources": [
            {
                "label": row["label"],
                "state_file_sha256": row["state_file_sha256"],
                "state_file_size": int(row["state_file_size"]),
                "authoritative_sha256": row["authoritative_sha256"],
            }
            for row in payload["provenance"]["sources"]
        ],
    }


def create_session(
    baseline_path: Path | str,
    baseline: receiver.ReceiverSession,
    *,
    profile: str,
    config: FeedbackConfig = FeedbackConfig(),
    certificate_union: Path | str | None = None,
) -> E024Session:
    """Create an immutable-generation-zero E024 overlay."""
    if profile not in FEEDBACK_PROFILES:
        raise ValueError(f"unknown E024 profile {profile!r}")
    baseline.validate_invariants()
    reference = baseline_reference(baseline_path, baseline)
    seed_sha = None
    seed_payload = None
    if certificate_union is not None:
        seed_payload = Path(
            certificate_union).expanduser().resolve().read_bytes()
        seed_sha = hashlib.sha256(seed_payload).hexdigest()
    envelope = E024Envelope(
        algorithm_id=ALGORITHM_ID, profile=profile, config=config,
        config_sha256=config.digest, evidence_policy=EVIDENCE_POLICY,
        implementation_sha256=implementation_fingerprints(),
        certificate_seed_sha256=seed_sha,
        certificate_seed_payload=seed_payload)
    session = E024Session(
        envelope=envelope, baseline=reference, generations=[],
        revisions={}, patches={}, dependency_sets={}, certificates={},
        attempts=[], attempt_ids=set(),
        tiles=initial_tile_states(baseline))
    empty = _empty_dependency(session)
    certifying = _certificate_attempts(baseline)
    for raw_key, outcome in sorted(baseline.decode.tiles.items()):
        key = tuple(map(int, raw_key))
        if outcome.state != "certified":
            continue
        if outcome.user_bits is None or key not in certifying:
            raise ValueError(
                f"E023b certificate {key} lacks complete provenance")
        _add_certificate(
            session, key=key, user_bits=outcome.user_bits,
            source="e023b-generation0",
            origin_attempt_id=certifying[key], born_generation=0,
            dependency_set_id=empty,
            provenance={"certified_by": outcome.certified_by})
    if certificate_union is not None:
        _load_certificate_union(certificate_union, session)

    frontier = tuple(sorted(
        row.certificate_id for row in session.certificates.values()))
    frontier_sha = _hash_parts(
        b"e024/label-frontier/v1",
        *[value.encode("ascii") for value in frontier])
    active_projection_sha = _active_projection_digest(
        baseline, {})
    statistics = {
        "imported_e023b_certificates": sum(
            row.source == "e023b-generation0"
            for row in session.certificates.values()),
        "external_seed_certificates": sum(
            row.source == "certificate-union"
            for row in session.certificates.values()),
    }
    fixed_point = profile == PROFILE_CONTROL
    generation_id = generation_identity(
        0, None, frontier_sha, (), (), (), (), (), (),
        active_projection_sha, fixed_point, statistics)
    session.generations.append(GenerationRecord(
        generation_id=generation_id, ordinal=0,
        parent_generation_id=None,
        label_frontier_ids=frontier,
        label_frontier_sha256=frontier_sha,
        active_revisions=(), accepted_revision_ids=(),
        refused_revision_ids=(), patch_ids=(), attempt_ids=(),
        new_certificate_ids=(),
        active_projection_sha256=active_projection_sha,
        fixed_point=fixed_point, statistics=statistics))
    validate_session(
        session, baseline, baseline_path=baseline_path,
        validate_baseline=False)
    return session


@dataclass(frozen=True)
class LabelField:
    values: dict[int, np.ndarray]
    certificate_ids: dict[TileKey, str]
    payload_indices: dict[TileKey, np.ndarray]
    payload_index_map: np.ndarray | None = None
    keystream_pages: dict[int, np.ndarray] | None = None


def export_certified_labels(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    certificate_ids: Iterable[str] | None = None,
) -> LabelField:
    """Regenerate exact physical printed-cell values from certificates."""
    selected = (
        {str(value) for value in certificate_ids}
        if certificate_ids is not None else
        {row.certificate_id for row in session.certificates.values()})
    by_id = {
        row.certificate_id: row for row in session.certificates.values()
    }
    missing = selected - set(by_id)
    if missing:
        raise ValueError(
            f"label frontier contains unknown certificates: "
            f"{sorted(missing)[:4]}")
    shape = tuple(baseline.decode.spec.page_cells_yx)
    values = {
        int(page): np.full(shape, -1, np.int8)
        for page in baseline.envelope.pages
    }
    inverse = payloaddec._payload_inverse(
        baseline.decode.spec, baseline.decode.seed)
    keystream = {
        int(page): compose.payload_keystream(
            baseline.decode.spec, baseline.decode.seed, int(page))
        for page in baseline.envelope.pages
    }
    pidx_by_tile = {}
    cert_by_tile = {}
    for certificate_id in sorted(selected):
        certificate = by_id[certificate_id]
        key = certificate.tile_key
        mask = baseline.decode.shorten_mask(key[1:])
        _codeword, tx_bits = ldpc.encode_tile(
            certificate.user_bits, mask, baseline.decode.ldpc_spec)
        pidx = ldpc._tile_payload_indices(
            key[1:], baseline.decode.spec, baseline.decode.seed, mask)
        cells = inverse[pidx]
        printed = (
            np.asarray(tx_bits, np.uint8)
            ^ keystream[key[0]][cells[:, 0], cells[:, 1]])
        current = values[key[0]][cells[:, 0], cells[:, 1]]
        if np.any((current >= 0) & (current != printed)):
            raise payloaddec.FatalIntegrityError(
                f"conflicting printed labels while exporting {key}")
        values[key[0]][cells[:, 0], cells[:, 1]] = printed.astype(np.int8)
        pidx_by_tile[key] = np.asarray(pidx, np.int64)
        cert_by_tile[key] = certificate_id
    return LabelField(
        values, cert_by_tile, pidx_by_tile,
        payload_index_map=compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed),
        keystream_pages=keystream)


@dataclass(frozen=True)
class WindowLabels:
    row_positions: np.ndarray
    values: np.ndarray
    validation: np.ndarray
    weights: np.ndarray
    is_pilot: np.ndarray
    block_ids: np.ndarray
    payload_indices: np.ndarray
    certificate_ids: tuple[str | None, ...]
    tile_keys: tuple[TileKey | None, ...]

    @property
    def train(self) -> np.ndarray:
        return ~self.validation


def _validation_block(
    page: int,
    page_yx: np.ndarray,
    config: FeedbackConfig,
) -> np.ndarray:
    block = np.asarray(page_yx, np.int64) // int(config.block_cells)
    token = (
        int(page) * 104729
        + block[:, 0] * 1009
        + block[:, 1] * 9176)
    return (token % int(config.validation_modulus)) == 0


def _block_weights(block_ids: np.ndarray) -> np.ndarray:
    ids = np.asarray(block_ids, np.int64).ravel()
    if ids.size == 0:
        return np.zeros(0, np.float64)
    _unique, inverse, count = np.unique(
        ids, return_inverse=True, return_counts=True)
    return 1.0 / count[inverse].astype(np.float64)


def collect_window_labels(
    placed: PlacedWindow,
    label_field: LabelField,
    baseline: receiver.ReceiverSession,
    config: FeedbackConfig,
) -> WindowLabels:
    """Join pilot and certified printed labels to one authoritative core."""
    page_yx = np.asarray(placed.page_cells_yx, np.int64)
    pilot_pos, pilot_value, pilot_validation = (
        payloaddec._window_pilot_observations(
            placed, baseline.decode.spec, baseline.decode.seed))
    pilot_page = page_yx[pilot_pos]
    page_values = label_field.values[int(placed.page)]
    payload_sel = page_values[page_yx[:, 0], page_yx[:, 1]] >= 0
    payload_pos = np.flatnonzero(payload_sel)
    payload_value = page_values[
        page_yx[payload_pos, 0], page_yx[payload_pos, 1]].astype(np.uint8)
    payload_validation = _validation_block(
        int(placed.page), page_yx[payload_pos], config)

    positions = np.concatenate((pilot_pos, payload_pos)).astype(np.int64)
    values = np.concatenate((pilot_value, payload_value)).astype(np.uint8)
    validation = np.concatenate(
        (pilot_validation, payload_validation)).astype(bool)
    is_pilot = np.concatenate((
        np.ones(pilot_pos.size, bool),
        np.zeros(payload_pos.size, bool)))
    coords = page_yx[positions]
    by = coords[:, 0] // int(config.block_cells)
    bx = coords[:, 1] // int(config.block_cells)
    # Pilot and payload blocks are distinct confidence groups even when they
    # share the same page-space block.
    block_ids = (
        is_pilot.astype(np.int64) * 10**12
        + int(placed.page) * 10**9 + by * 10**4 + bx)
    weights = np.zeros(positions.size, np.float64)
    weights[~validation] = _block_weights(block_ids[~validation])
    weights[validation] = _block_weights(block_ids[validation])

    cert_ids: list[str | None] = [None] * pilot_pos.size
    tile_keys: list[TileKey | None] = [None] * pilot_pos.size
    payload_indices = np.full(positions.size, -1, np.int64)
    pim = (
        label_field.payload_index_map
        if label_field.payload_index_map is not None
        else compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed))
    payload_indices[pilot_pos.size:] = pim[
        page_yx[payload_pos, 0], page_yx[payload_pos, 1]]
    for coord in page_yx[payload_pos]:
        key = (
            int(placed.page), int(coord[0]) // ldpc.TILE_CELLS,
            int(coord[1]) // ldpc.TILE_CELLS)
        if key not in label_field.certificate_ids:
            raise ValueError("printed label lacks its certificate identity")
        cert_ids.append(label_field.certificate_ids[key])
        tile_keys.append(key)
    return WindowLabels(
        positions, values, validation, weights, is_pilot,
        block_ids.astype(np.int64), payload_indices,
        tuple(cert_ids), tuple(tile_keys))


def weighted_pava_calibrate(
    scores: np.ndarray,
    labels: np.ndarray,
    weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Weighted monotone calibration with a finite Beta(1,1) block prior."""
    score = np.asarray(scores, np.float64).ravel()
    label = np.asarray(labels, np.float64).ravel()
    weight = np.asarray(weights, np.float64).ravel()
    if not (score.size == label.size == weight.size) or score.size == 0:
        raise ValueError("weighted PAVA arrays must be equally non-empty")
    if (not np.isfinite(score).all() or not np.isfinite(weight).all()
            or np.any(weight <= 0.0)
            or not np.all((label == 0.0) | (label == 1.0))):
        raise ValueError("weighted PAVA inputs are invalid")
    order = np.argsort(score, kind="stable")
    score, label, weight = score[order], label[order], weight[order]
    unique, first = np.unique(score, return_index=True)
    total_weight = np.add.reduceat(weight, first)
    one_weight = np.add.reduceat(weight * label, first)
    blocks = []
    for index, value in enumerate(unique):
        blocks.append({
            "lo": index, "hi": index + 1,
            "weight": float(total_weight[index]),
            "ones": float(one_weight[index]),
            "score_weight": float(value * total_weight[index]),
        })
        while len(blocks) >= 2:
            left, right = blocks[-2], blocks[-1]
            p_left = (left["ones"] + 1.0) / (left["weight"] + 2.0)
            p_right = (right["ones"] + 1.0) / (right["weight"] + 2.0)
            if p_left < p_right:
                break
            blocks[-2:] = [{
                "lo": left["lo"], "hi": right["hi"],
                "weight": left["weight"] + right["weight"],
                "ones": left["ones"] + right["ones"],
                "score_weight": (
                    left["score_weight"] + right["score_weight"]),
            }]
    nodes_s = np.asarray([
        row["score_weight"] / row["weight"] for row in blocks
    ], np.float64)
    nodes_p = np.asarray([
        (row["ones"] + 1.0) / (row["weight"] + 2.0)
        for row in blocks
    ], np.float64)
    return nodes_s, nodes_p


def _weighted_logloss(
    logits: np.ndarray,
    labels: np.ndarray,
    weights: np.ndarray,
) -> float:
    logit = np.asarray(logits, np.float64).ravel()
    label = np.asarray(labels, np.float64).ravel()
    weight = np.asarray(weights, np.float64).ravel()
    if logit.size == 0 or not (
            logit.size == label.size == weight.size):
        raise ValueError("logloss inputs must be equally non-empty")
    loss = np.logaddexp(0.0, logit) - label * logit
    return float(np.sum(weight * loss) / np.sum(weight))


def _physical_logits(emission: payloaddec.WindowEmission) -> np.ndarray | None:
    if (emission.refused or emission.scores.size == 0
            or emission.calibration_score_nodes.size == 0):
        return None
    logits = apply_calibration(
        emission.scores, emission.calibration_score_nodes,
        emission.calibration_probability_nodes)
    diagnostics = emission.diagnostics
    base_clip = diagnostics.get("feedback_base_clip")
    if base_clip is not None:
        logits = np.clip(logits, -float(base_clip), float(base_clip))
    tau = diagnostics.get("feedback_context_tau")
    if tau is not None:
        count, valid = payloaddec.context_neighbor_counts(
            emission.page_cells_yx, logits > 0.0)
        corrected = logits.copy()
        tau_array = np.asarray(tau, np.float64)
        corrected[valid] = np.clip(
            corrected[valid] + tau_array[count[valid]],
            -float(diagnostics.get("feedback_context_clip", 8.0)),
            float(diagnostics.get("feedback_context_clip", 8.0)))
        return corrected
    fit = getattr(emission, "context_fit", None)
    if fit is not None and fit.adopted:
        count, valid = payloaddec.context_neighbor_counts(
            emission.page_cells_yx, logits > 0.0)
        corrected = logits.copy()
        corrected[valid] = np.clip(
            corrected[valid] + fit.tau[count[valid]],
            -payloaddec.CTX_LLR_CLIP, payloaddec.CTX_LLR_CLIP)
        return corrected
    return logits


def _generation0_detector_logits(
    generation0: payloaddec.WindowEmission,
    page_cells_yx: np.ndarray,
    means: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Replay the frozen E023b detector exactly on newly sampled means."""
    if (generation0.refused
            or generation0.calibration_score_nodes.size == 0):
        raise ValueError("generation-zero detector is unavailable")
    mid = float(generation0.diagnostics.get(
        "mid", np.median(generation0.raw_means)))
    spread = float(generation0.diagnostics.get(
        "spread",
        max(np.abs(generation0.raw_means - mid).mean(), 1e-6)))
    raw = np.asarray(means, np.float32)
    same_generation_zero_sample = (
        np.array_equal(
            np.asarray(page_cells_yx, np.int64),
            np.asarray(generation0.page_cells_yx, np.int64))
        and np.array_equal(
            raw, np.asarray(generation0.raw_means, np.float32)))
    if same_generation_zero_sample:
        # E023b scored the pre-quantized sample and then persisted both
        # float32 raw means and float32 scores.  The original higher-precision
        # sample cannot be recovered from raw_means, so exact replay of the
        # immutable generation-zero point must use its retained score vector.
        scores = np.asarray(
            generation0.scores, np.float32).copy()
    else:
        # Newly sampled pose candidates are already frozen at float32.  Keep
        # the arithmetic in that dtype so durable E024 fixed-detector
        # revisions replay byte-for-byte.
        scores = (
            (np.float32(mid) - raw)
            / np.float32(max(spread, 1e-6))).astype(
                np.float32, copy=False)
    logits = apply_calibration(
        scores, generation0.calibration_score_nodes,
        generation0.calibration_probability_nodes)
    fit = getattr(generation0, "context_fit", None)
    if fit is not None and fit.adopted:
        count, valid = payloaddec.context_neighbor_counts(
            page_cells_yx, logits > 0.0)
        corrected = logits.copy()
        corrected[valid] = np.clip(
            corrected[valid] + fit.tau[count[valid]],
            -payloaddec.CTX_LLR_CLIP, payloaddec.CTX_LLR_CLIP)
        logits = corrected
    return scores, np.asarray(logits, np.float64)


def _scores_from_means(means: np.ndarray) -> tuple[np.ndarray, float, float]:
    raw = np.asarray(means, np.float64).ravel()
    mid = float(np.median(raw))
    spread = max(float(np.abs(raw - mid).mean()), 1e-6)
    return (mid - raw) / spread, mid, spread


def _support_ok(
    labels: WindowLabels,
    config: FeedbackConfig,
) -> tuple[bool, str]:
    payload = ~labels.is_pilot
    train_payload = payload & labels.train
    valid_payload = payload & labels.validation
    if int(train_payload.sum()) < config.min_payload_train:
        return False, "insufficient_payload_train"
    if int(valid_payload.sum()) < config.min_payload_validation:
        return False, "insufficient_payload_validation"
    train_values = labels.values[labels.train]
    valid_values = labels.values[labels.validation]
    if min(int((train_values == 0).sum()),
           int((train_values == 1).sum())) < config.min_train_per_class:
        return False, "train_class_starved"
    if min(int((valid_values == 0).sum()),
           int((valid_values == 1).sum())) < config.min_validation_per_class:
        return False, "validation_class_starved"
    blocks = np.unique(labels.block_ids[payload])
    if blocks.size < config.min_label_blocks:
        return False, "insufficient_label_blocks"
    return True, ""


def _expanded_dependencies(
    session: E024Session,
    certificate_ids: Iterable[str],
    *,
    parent_revision_id: str | None = None,
) -> tuple[str, ...]:
    by_id = {
        row.certificate_id: row for row in session.certificates.values()
    }
    out: set[str] = set()
    for identity in certificate_ids:
        certificate = by_id[str(identity)]
        out.add(certificate.certificate_id)
        out.update(session.dependency_sets[
            certificate.dependency_set_id].certificate_ids)
    if parent_revision_id is not None:
        parent = session.revisions[parent_revision_id]
        out.update(session.dependency_sets[
            parent.dependency_set_id].certificate_ids)
    return tuple(sorted(out))


def _label_uses(
    labels: WindowLabels,
    label_field: LabelField,
) -> tuple[LabelUse, ...]:
    del label_field
    grouped: dict[str, list[int]] = {}
    for identity, payload_index in zip(
            labels.certificate_ids, labels.payload_indices, strict=True):
        if identity is None:
            continue
        if int(payload_index) < 0:
            raise ValueError("certified label lacks a payload index")
        grouped.setdefault(identity, []).append(int(payload_index))
    return tuple(LabelUse(
        certificate_id=identity, role="detector-and-gate",
        n_sites=sum(value == identity
                    for value in labels.certificate_ids),
        payload_indices_sha256=_array_digest(
            np.unique(grouped[identity]), "<i8"))
        for identity in sorted(grouped))


def fit_detector_revision(
    placed: PlacedWindow,
    parent: payloaddec.WindowEmission,
    means: np.ndarray,
    labels: WindowLabels,
    label_field: LabelField,
    baseline: receiver.ReceiverSession,
    config: FeedbackConfig,
) -> tuple[payloaddec.WindowEmission | None, dict, tuple[LabelUse, ...]]:
    """Fit and held-out-gate one dense PAVA + ordered-context revision."""
    eligible, reason = _support_ok(labels, config)
    if not eligible:
        return None, {"eligible": False, "reason": reason}, ()
    scores64, mid, spread = _scores_from_means(means)
    # The persisted emission stores float32 scores.  Quantize once before
    # fitting or gating so the acceptance decision is exactly replayable
    # from the durable representation.
    scores = np.asarray(scores64, np.float32)
    train = labels.train
    valid = labels.validation
    nodes_s, nodes_p = weighted_pava_calibrate(
        scores[labels.row_positions[train]], labels.values[train],
        labels.weights[train])
    value_logits = np.clip(
        apply_calibration(scores, nodes_s, nodes_p),
        -config.confidence_cap, config.confidence_cap)
    pava_valid_loss = _weighted_logloss(
        value_logits[labels.row_positions[valid]],
        labels.values[valid], labels.weights[valid])

    count, context_valid = payloaddec.context_neighbor_counts(
        placed.page_cells_yx, value_logits > 0.0)
    train_context = train & context_valid[labels.row_positions]
    valid_context = valid & context_valid[labels.row_positions]
    tau = np.zeros(9, np.float64)
    context_adopted = False
    context_valid_loss = pava_valid_loss
    if (int(train_context.sum()) >= config.min_payload_train
            and int(valid_context.sum()) >= config.min_payload_validation
            and min(
                int((labels.values[train_context] == 0).sum()),
                int((labels.values[train_context] == 1).sum()))
            >= config.min_train_per_class):
        tau = payloaddec.fit_ordered_context_offsets(
            value_logits[labels.row_positions[train_context]],
            count[labels.row_positions[train_context]],
            labels.values[train_context],
            labels.weights[train_context])
        corrected = value_logits.copy()
        corrected[context_valid] = np.clip(
            corrected[context_valid] + tau[count[context_valid]],
            -config.context_clip, config.context_clip)
        candidate_loss = _weighted_logloss(
            corrected[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid])
        if candidate_loss + config.min_improvement < pava_valid_loss:
            value_logits = corrected
            context_valid_loss = candidate_loss
            context_adopted = True

    parent_logits = _physical_logits(parent)
    parent_loss = (
        float("inf") if parent_logits is None else
        _weighted_logloss(
            parent_logits[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid]))
    candidate_loss = context_valid_loss
    adopted = candidate_loss + config.min_improvement < parent_loss
    metrics = {
        "eligible": True,
        "adopted": adopted,
        "reason": "adopted" if adopted else "heldout_gate_failed",
        "parent_validation_logloss": parent_loss,
        "pava_validation_logloss": pava_valid_loss,
        "candidate_validation_logloss": candidate_loss,
        "context_adopted": context_adopted,
        "n_train": int(train.sum()),
        "n_validation": int(valid.sum()),
        "n_payload_train": int((train & ~labels.is_pilot).sum()),
        "n_payload_validation": int(
            (valid & ~labels.is_pilot).sum()),
        "n_label_blocks": int(np.unique(
            labels.block_ids[~labels.is_pilot]).size),
        "n_certificate_tiles": len({
            key for key in labels.tile_keys if key is not None}),
        "mid": mid, "spread": spread,
    }
    uses = _label_uses(labels, label_field)
    if not adopted:
        return None, metrics, uses

    page_yx = np.asarray(placed.page_cells_yx, np.int64)
    pim = (
        label_field.payload_index_map
        if label_field.payload_index_map is not None
        else compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed))
    pidx = pim[page_yx[:, 0], page_yx[:, 1]]
    selected = pidx >= 0
    ks = (
        label_field.keystream_pages[int(placed.page)]
        if label_field.keystream_pages is not None
        else compose.payload_keystream(
            baseline.decode.spec, baseline.decode.seed, int(placed.page)))
    payload_llr = (
        value_logits[selected]
        * (1.0 - 2.0 * ks[
            page_yx[selected, 0], page_yx[selected, 1]].astype(np.float64))
    ).astype(np.float32)
    diagnostics = {
        "detector_profile": DETECTOR_PROFILE,
        "feedback_base_clip": float(config.confidence_cap),
        "feedback_context_tau": tuple(float(value) for value in (
            tau if context_adopted else np.zeros(9))),
        "feedback_context_clip": float(config.context_clip),
        "feedback_context_adopted": bool(context_adopted),
        "feedback_parent_validation_logloss": float(parent_loss),
        "feedback_pava_validation_logloss": float(pava_valid_loss),
        "feedback_candidate_validation_logloss": float(candidate_loss),
        "feedback_n_label_blocks": metrics["n_label_blocks"],
        "feedback_n_certificate_tiles": metrics["n_certificate_tiles"],
        "mid": mid, "spread": spread,
        "n_cal_nodes": int(nodes_s.size),
    }
    emission = payloaddec.WindowEmission(
        placement_ordinal=int(parent.placement_ordinal),
        page=int(placed.page),
        payload_index=pidx[selected].astype(np.int64),
        payload_llr=payload_llr,
        heldout_logloss=float(candidate_loss),
        n_train_labels=int(train.sum()),
        n_heldout=int(valid.sum()),
        refused=False, refuse_reason="", diagnostics=diagnostics,
        region_index=int(placed.region_index),
        page_cells_yx=page_yx.astype(np.int32, copy=True),
        raw_means=np.asarray(means, np.float32).copy(),
        scores=np.asarray(scores, np.float32),
        calibration_score_nodes=nodes_s,
        calibration_probability_nodes=nodes_p,
        detector_profile=DETECTOR_PROFILE,
        context_fit=None)
    replayed_logits = _physical_logits(emission)
    if replayed_logits is None:
        raise ValueError("accepted feedback detector did not replay")
    emission = replace(
        emission,
        payload_llr=(
            replayed_logits[selected]
            * (1.0 - 2.0 * ks[
                page_yx[selected, 0],
                page_yx[selected, 1]].astype(np.float64))
        ).astype(np.float32))
    return emission, metrics, uses


def _deterministic_cap(
    positions: np.ndarray,
    page_yx: np.ndarray,
    cap: int,
) -> np.ndarray:
    positions = np.asarray(positions, np.int64)
    if positions.size <= cap:
        return positions
    coords = np.asarray(page_yx, np.int64)[positions]
    token = (
        coords[:, 0].astype(np.uint64) * np.uint64(11400714819323198485)
        ^ coords[:, 1].astype(np.uint64) * np.uint64(14029467366897019727))
    order = np.argsort(token, kind="stable")
    return positions[order[:cap]]


def _sample_pose_sites(
    crop: payloaddec.RegionCrop,
    pose: AffinePose,
    local_cells: np.ndarray,
) -> np.ndarray:
    points = pose.points(np.asarray(local_cells, np.float64))
    points -= np.array([crop.y0, crop.x0], np.float64)
    return ndimage.map_coordinates(
        crop.filt, points.T, order=1, cval=crop.fill)


def _pose_candidate(
    base: AffinePose,
    dtheta_deg: float,
    du_cells: float,
    dv_cells: float,
) -> AffinePose:
    angle = np.deg2rad(float(dtheta_deg))
    rotation = np.array([
        [np.cos(angle), np.sin(angle)],
        [-np.sin(angle), np.cos(angle)],
    ], np.float64)
    jac0 = base.matrix()
    jac = rotation @ jac0
    origin = (
        np.asarray(base.origin_yx, np.float64)
        + jac0 @ np.array([du_cells, dv_cells], np.float64))
    pitch_v = float(np.hypot(*jac[:, 0]))
    pitch_u = float(np.hypot(*jac[:, 1]))
    angle_deg = float(np.degrees(np.arctan2(jac[0, 1], jac[1, 1])))
    return AffinePose(
        origin_yx=(float(origin[0]), float(origin[1])),
        jacobian_yx=(
            (float(jac[0, 0]), float(jac[0, 1])),
            (float(jac[1, 0]), float(jac[1, 1]))),
        angle_deg=angle_deg,
        pitch_px=0.5 * (pitch_v + pitch_u),
        phase_yx=base.phase_yx,
        footing_factor=base.footing_factor)


def _pose_objective(
    means: np.ndarray,
    values: np.ndarray,
    weights: np.ndarray,
) -> float:
    raw = np.asarray(means, np.float64)
    labels = np.asarray(values, np.uint8)
    weight = np.asarray(weights, np.float64)
    paper = labels == 0
    ink = labels == 1
    if not paper.any() or not ink.any():
        return -np.inf
    mean_paper = float(np.sum(weight[paper] * raw[paper])
                       / np.sum(weight[paper]))
    mean_ink = float(np.sum(weight[ink] * raw[ink])
                     / np.sum(weight[ink]))
    center = float(np.sum(weight * raw) / np.sum(weight))
    spread = max(float(np.sum(weight * np.abs(raw - center))
                       / np.sum(weight)), 1e-6)
    return (mean_paper - mean_ink) / spread


def refine_pose_on_labels(
    crop: payloaddec.RegionCrop,
    placed: PlacedWindow,
    generation0: payloaddec.WindowEmission,
    labels: WindowLabels,
    config: FeedbackConfig,
    *,
    current_pose: AffinePose | None = None,
    current_means: np.ndarray | None = None,
    search_config: SearchConfig | None = None,
) -> tuple[AffinePose | None, np.ndarray | None, dict]:
    """Bounded coarse-to-fine pose search using only training labels."""
    eligible, reason = _support_ok(labels, config)
    if not eligible:
        return None, None, {"eligible": False, "reason": reason}
    local = payloaddec.local_core_cells(placed)
    replayed = payloaddec.sample_window_means(crop, placed, local)
    if not np.array_equal(
            np.asarray(replayed, np.float32),
            np.asarray(generation0.raw_means, np.float32)):
        raise payloaddec.FatalIntegrityError(
            "generation-zero pose no longer reproduces retained raw means")
    active_pose = placed.pose if current_pose is None else current_pose
    active_means = (
        np.asarray(generation0.raw_means, np.float32)
        if current_means is None else
        np.asarray(current_means, np.float32))
    active_placed = replace(placed, pose=active_pose)
    replayed_active = payloaddec.sample_window_means(
        crop, active_placed, local)
    if not np.array_equal(
            np.asarray(replayed_active, np.float32), active_means):
        raise payloaddec.FatalIntegrityError(
            "active E024 pose no longer reproduces retained raw means")

    label_by_row = np.full(local.shape[0], -1, np.int8)
    weight_by_row = np.zeros(local.shape[0], np.float64)
    pilot_by_row = np.zeros(local.shape[0], bool)
    for position, value, weight, pilot in zip(
            labels.row_positions, labels.values, labels.weights,
            labels.is_pilot, strict=True):
        label_by_row[position] = int(value)
        weight_by_row[position] = float(weight)
        pilot_by_row[position] = bool(pilot)

    def retain_all_pilots(mask: np.ndarray, cap: int) -> np.ndarray:
        rows = labels.row_positions[mask]
        pilots = rows[pilot_by_row[rows]]
        payload = rows[~pilot_by_row[rows]]
        payload_cap = max(int(cap) - int(pilots.size), 0)
        payload = _deterministic_cap(
            payload, placed.page_cells_yx, payload_cap)
        return np.sort(np.concatenate((pilots, payload))).astype(
            np.int64, copy=False)

    train_rows = retain_all_pilots(
        labels.train, config.pose_site_cap_train)
    valid_rows = retain_all_pilots(
        labels.validation, config.pose_site_cap_validation)
    train_values = label_by_row[train_rows].astype(np.uint8)
    train_weights = weight_by_row[train_rows]
    valid_values = label_by_row[valid_rows].astype(np.uint8)
    valid_weights = weight_by_row[valid_rows]

    _base_scores, base_logits = _generation0_detector_logits(
        generation0, placed.page_cells_yx, active_means)
    base_loss = _weighted_logloss(
        base_logits[valid_rows], valid_values, valid_weights)
    train_pilot = train_rows[pilot_by_row[train_rows]]
    base_pilot = valid_rows[pilot_by_row[valid_rows]]
    minimum_pilot_validation = int(
        20 if search_config is None else search_config.min_support)
    if (train_pilot.size < minimum_pilot_validation
            or base_pilot.size < minimum_pilot_validation):
        return None, None, {
            "eligible": False,
            "reason": "insufficient_pose_pilot_validation",
            "n_pose_pilot_train": int(train_pilot.size),
            "n_pose_pilot_validation": int(base_pilot.size),
            "min_pose_pilot_validation": minimum_pilot_validation,
        }
    base_pilot_mismatch = float(np.mean(
        (base_logits[base_pilot] > 0.0)
        != (label_by_row[base_pilot] > 0)))
    generation0_mid = float(generation0.diagnostics.get(
        "mid", np.median(generation0.raw_means)))
    generation0_pilot_mismatch = float(np.mean(
        (np.asarray(generation0.raw_means)[base_pilot] < generation0_mid)
        != (label_by_row[base_pilot] > 0)))

    coarse_angles = np.arange(
        -config.pose_angle_deg,
        config.pose_angle_deg + 1e-12,
        config.pose_angle_coarse_step_deg)
    coarse_phase = np.arange(
        -config.pose_phase_cells,
        config.pose_phase_cells + 1e-12,
        config.pose_phase_coarse_step_cells)
    if generation0.calibration_score_nodes.size == 0:
        return None, None, {
            "eligible": False,
            "reason": "generation0_detector_unavailable",
        }
    detector_mid = float(generation0.diagnostics.get(
        "mid", np.median(generation0.raw_means)))
    detector_spread = float(generation0.diagnostics.get(
        "spread",
        max(np.abs(generation0.raw_means - detector_mid).mean(), 1e-6)))
    candidates: dict[
        tuple[float, float, float], tuple[float, float]
    ] = {}

    def score_candidate(dtheta: float, du: float, dv: float) -> None:
        key = (round(float(dtheta), 12), round(float(du), 12),
               round(float(dv), 12))
        if key in candidates:
            return
        pose = _pose_candidate(placed.pose, *key)
        means = _sample_pose_sites(crop, pose, local[train_rows])
        contrast = _pose_objective(
            means, train_values, train_weights)
        scores = (detector_mid - means) / max(detector_spread, 1e-6)
        logits = apply_calibration(
            scores, generation0.calibration_score_nodes,
            generation0.calibration_probability_nodes)
        train_loss = _weighted_logloss(
            logits, train_values, train_weights)
        candidates[key] = (contrast, train_loss)

    def select_best(
        keys: Iterable[tuple[float, float, float]],
    ) -> tuple[float, float, float]:
        rows = tuple(keys)
        maximum_contrast = max(candidates[key][0] for key in rows)
        # Sampling a mostly flat cell interior often yields a contrast plateau.
        # Treat machine-epsilon-scale contrast differences as ties and use the
        # frozen generation-zero detector on training sites to choose the
        # phase.  Validation labels remain reserved for the independent gate.
        near = [
            key for key in rows
            if maximum_contrast - candidates[key][0] <= 1e-9
        ]
        return min(
            near,
            key=lambda key: (
                candidates[key][1],
                sum(value * value for value in key),
                tuple(abs(value) for value in key),
                key))

    for dtheta in coarse_angles:
        for du in coarse_phase:
            for dv in coarse_phase:
                score_candidate(float(dtheta), float(du), float(dv))
    best_coarse = select_best(candidates)
    fine_angles = np.arange(
        best_coarse[0] - config.pose_angle_coarse_step_deg,
        best_coarse[0] + config.pose_angle_coarse_step_deg + 1e-12,
        config.pose_angle_fine_step_deg)
    fine_du = np.arange(
        best_coarse[1] - config.pose_phase_coarse_step_cells,
        best_coarse[1] + config.pose_phase_coarse_step_cells + 1e-12,
        config.pose_phase_fine_step_cells)
    fine_dv = np.arange(
        best_coarse[2] - config.pose_phase_coarse_step_cells,
        best_coarse[2] + config.pose_phase_coarse_step_cells + 1e-12,
        config.pose_phase_fine_step_cells)
    for dtheta in fine_angles:
        if abs(dtheta) > config.pose_angle_deg + 1e-12:
            continue
        for du in fine_du:
            if abs(du) > config.pose_phase_cells + 1e-12:
                continue
            for dv in fine_dv:
                if abs(dv) > config.pose_phase_cells + 1e-12:
                    continue
                score_candidate(float(dtheta), float(du), float(dv))
    best = select_best(candidates)
    pose = _pose_candidate(placed.pose, *best)
    if pose == active_pose:
        return None, None, {
            "eligible": True, "adopted": False,
            "reason": "active_pose_selected",
            "candidates": len(candidates),
            "baseline_validation_logloss": base_loss}

    revised = replace(placed, pose=pose)
    means = np.asarray(
        payloaddec.sample_window_means(crop, revised, local), np.float32)
    _candidate_scores, candidate_logits = _generation0_detector_logits(
        generation0, placed.page_cells_yx, means)
    candidate_loss = _weighted_logloss(
        candidate_logits[valid_rows], valid_values, valid_weights)
    pilot_rows = valid_rows[pilot_by_row[valid_rows]]
    pilot_mismatch = float(np.mean(
        (candidate_logits[pilot_rows] > 0.0)
        != (label_by_row[pilot_rows] > 0)))
    e022_pilot_mismatch = float(np.mean(
        (means[pilot_rows] < generation0_mid)
        != (label_by_row[pilot_rows] > 0)))
    adopted = (
        candidate_loss + config.min_improvement < base_loss
        and pilot_mismatch
        <= base_pilot_mismatch + config.pilot_mismatch_slack
        # Replay E022's hard pilot-mismatch rule on the authoritative-core
        # pilot population against the immutable generation-zero threshold.
        # The original E022 page/address/orientation, BCH, rival and placement
        # admission remains frozen because E024 does not alter that discrete
        # hypothesis.
        and e022_pilot_mismatch
        <= generation0_pilot_mismatch + config.pilot_mismatch_slack)
    metrics = {
        "eligible": True, "adopted": adopted,
        "reason": "adopted" if adopted else "pose_gate_failed",
        "candidates": len(candidates),
        "dtheta_deg": float(best[0]),
        "du_cells": float(best[1]),
        "dv_cells": float(best[2]),
        "objective": float(candidates[best][0]),
        "training_detector_logloss": float(candidates[best][1]),
        "baseline_validation_logloss": float(base_loss),
        "candidate_validation_logloss": float(candidate_loss),
        "baseline_pilot_mismatch": float(base_pilot_mismatch),
        "candidate_pilot_mismatch": float(pilot_mismatch),
        "generation0_e022_pilot_mismatch": float(
            generation0_pilot_mismatch),
        "candidate_e022_pilot_mismatch": float(
            e022_pilot_mismatch),
        "e022_pilot_mismatch_slack": float(
            config.pilot_mismatch_slack),
        "n_pose_pilot_train": int(train_pilot.size),
        "n_pose_pilot_validation": int(pilot_rows.size),
        "inherited_discrete_gates_frozen": True,
        "inherited_discrete_page": int(placed.page),
        "inherited_discrete_origin_yx": tuple(placed.origin_yx),
        "inherited_discrete_rot_k": int(placed.rot_k),
        "inherited_address_method": placed.method,
        "inherited_placement_mismatch": float(placed.mismatch),
        "inherited_placement_validation_mismatch": float(
            placed.validation_mismatch),
        "inherited_rival_mismatch": placed.rival_mismatch,
        "inherited_support": int(placed.support),
        "inherited_bch_errors": placed.bch_errors,
        "n_pose_train": int(train_rows.size),
        "n_pose_validation": int(valid_rows.size),
    }
    if not adopted:
        return None, None, metrics
    return pose, means, metrics


def _fixed_detector_revision(
    placed: PlacedWindow,
    generation0: payloaddec.WindowEmission,
    parent: payloaddec.WindowEmission,
    means: np.ndarray,
    labels: WindowLabels,
    label_field: LabelField,
    baseline: receiver.ReceiverSession,
    config: FeedbackConfig,
) -> tuple[payloaddec.WindowEmission | None, dict]:
    """Apply generation-zero detector parameters to pose-revised means."""
    if (generation0.refused
            or generation0.calibration_score_nodes.size == 0):
        return None, {
            "eligible": False,
            "reason": "generation0_detector_unavailable"}
    mid = float(generation0.diagnostics.get(
        "mid", np.median(generation0.raw_means)))
    spread = float(generation0.diagnostics.get(
        "spread",
        max(np.abs(generation0.raw_means - mid).mean(), 1e-6)))
    scores, value_logits = _generation0_detector_logits(
        generation0, placed.page_cells_yx, means)
    fit = getattr(generation0, "context_fit", None)
    valid = labels.validation
    candidate_loss = _weighted_logloss(
        value_logits[labels.row_positions[valid]],
        labels.values[valid], labels.weights[valid])
    parent_logits = _physical_logits(parent)
    parent_loss = (
        float("inf") if parent_logits is None else _weighted_logloss(
            parent_logits[labels.row_positions[valid]],
            labels.values[valid], labels.weights[valid]))
    if candidate_loss + config.min_improvement >= parent_loss:
        return None, {
            "eligible": True, "adopted": False,
            "reason": "fixed_detector_heldout_gate_failed",
            "parent_validation_logloss": parent_loss,
            "candidate_validation_logloss": candidate_loss}

    page_yx = np.asarray(placed.page_cells_yx, np.int64)
    pim = (
        label_field.payload_index_map
        if label_field.payload_index_map is not None
        else compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed))
    pidx = pim[page_yx[:, 0], page_yx[:, 1]]
    selected = pidx >= 0
    ks = (
        label_field.keystream_pages[int(placed.page)]
        if label_field.keystream_pages is not None
        else compose.payload_keystream(
            baseline.decode.spec, baseline.decode.seed, int(placed.page)))
    payload_llr = (
        value_logits[selected]
        * (1.0 - 2.0 * ks[
            page_yx[selected, 0], page_yx[selected, 1]].astype(np.float64))
    ).astype(np.float32)
    diagnostics = {
        "detector_profile": FIXED_DETECTOR_PROFILE,
        "feedback_parent_validation_logloss": float(parent_loss),
        "feedback_candidate_validation_logloss": float(candidate_loss),
        "generation0_detector_profile": generation0.detector_profile,
        "mid": mid, "spread": spread,
    }
    emission = payloaddec.WindowEmission(
        placement_ordinal=generation0.placement_ordinal,
        page=placed.page, payload_index=pidx[selected].astype(np.int64),
        payload_llr=payload_llr,
        heldout_logloss=float(candidate_loss),
        n_train_labels=int(labels.train.sum()),
        n_heldout=int(valid.sum()), refused=False,
        diagnostics=diagnostics, region_index=placed.region_index,
        page_cells_yx=page_yx.astype(np.int32, copy=True),
        raw_means=np.asarray(means, np.float32).copy(),
        scores=np.asarray(scores, np.float32),
        calibration_score_nodes=np.asarray(
            generation0.calibration_score_nodes, np.float64).copy(),
        calibration_probability_nodes=np.asarray(
            generation0.calibration_probability_nodes, np.float64).copy(),
        detector_profile=FIXED_DETECTOR_PROFILE,
        context_fit=fit if fit is not None and fit.adopted else None)
    replayed_logits = _physical_logits(emission)
    if replayed_logits is None:
        raise ValueError("accepted fixed detector did not replay")
    emission = replace(
        emission,
        payload_llr=(
            replayed_logits[selected]
            * (1.0 - 2.0 * ks[
                page_yx[selected, 0],
                page_yx[selected, 1]].astype(np.float64))
        ).astype(np.float32))
    return emission, {
        "eligible": True, "adopted": True, "reason": "adopted",
        "parent_validation_logloss": parent_loss,
        "candidate_validation_logloss": candidate_loss}


def _set_comparable_owner_rank(
    emission: payloaddec.WindowEmission,
    placed: PlacedWindow,
    baseline: receiver.ReceiverSession,
) -> payloaddec.WindowEmission:
    """Rank all generations on the same fixed pilot-validation sites."""
    logits = _physical_logits(emission)
    if logits is None:
        raise ValueError("accepted feedback emission lacks physical logits")
    site_pos, expected, validation = (
        payloaddec._window_pilot_observations(
            placed, baseline.decode.spec, baseline.decode.seed))
    if not validation.any():
        raise ValueError(
            "feedback owner rank lacks pilot validation support")
    owner_loss = payloaddec._logistic_logloss(
        logits[site_pos[validation]], expected[validation])
    diagnostics = dict(emission.diagnostics)
    diagnostics.update({
        "feedback_dense_heldout_logloss": float(
            emission.heldout_logloss),
        "feedback_owner_policy": "fixed-pilot-validation-v1",
        "feedback_owner_rank_logloss": float(owner_loss),
    })
    return replace(
        emission, heldout_logloss=float(owner_loss),
        diagnostics=diagnostics)


def _candidate_windows(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    label_field: LabelField,
) -> tuple[dict[WindowKey, set[TileKey]], dict[WindowKey, WindowLabels]]:
    unresolved = {
        key for key, state in session.tiles.items()
        if state.state not in ("certified", "degenerate")
    }
    targets: dict[WindowKey, set[TileKey]] = {}
    # Labels are intentionally streamed later in _build_revisions.  Keeping
    # every dense window label array resident scales poorly on full sheets.
    labels: dict[WindowKey, WindowLabels] = {}
    pim = (
        label_field.payload_index_map
        if label_field.payload_index_map is not None
        else compose.payload_index_map(
            baseline.decode.spec, baseline.decode.seed))
    tile_codes = receiver._payload_tile_codes(
        baseline.decode.spec, baseline.decode.seed)
    tiles_x = int(np.ceil(
        baseline.decode.spec.page_cells_yx[1] / ldpc.TILE_CELLS))
    for scan in baseline.scans:
        for ordinal, placed in enumerate(scan.result.placements):
            page_yx = np.asarray(placed.page_cells_yx, np.int64)
            pidx = pim[page_yx[:, 0], page_yx[:, 1]]
            pidx = pidx[pidx >= 0]
            covered = {
                (int(placed.page), *divmod(int(code), tiles_x))
                for code in np.unique(tile_codes[pidx])
            } & unresolved
            if not covered:
                continue
            page_values = label_field.values[int(placed.page)]
            if not np.any(
                    page_values[page_yx[:, 0], page_yx[:, 1]] >= 0):
                continue
            key = (scan.scan_id, ordinal)
            targets[key] = covered
    return targets, labels


def _active_row(
    session: E024Session,
    baseline_scan: receiver.ScanRecord,
    ordinal: int,
) -> tuple[payloaddec.WindowEmission, str | None]:
    revision_id = session.active_revision_map.get(
        (baseline_scan.scan_id, ordinal))
    if revision_id is None:
        return baseline_scan.window_evidence[ordinal], None
    emission = session.revisions[revision_id].emission
    if emission is None:
        raise ValueError("active E024 revision carries no emission")
    return emission, revision_id


def _build_revisions(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    label_field: LabelField,
    targets: dict[WindowKey, set[TileKey]],
    labels_by_window: dict[WindowKey, WindowLabels],
    generation: int,
) -> tuple[list[EvidenceRevision], list[EvidenceRevision], dict]:
    profile = session.envelope.profile
    config = session.envelope.config
    accepted: list[EvidenceRevision] = []
    refused: list[EvidenceRevision] = []
    statistics = Counter()
    scans = {scan.scan_id: scan for scan in baseline.scans}
    image_cache: dict[str, np.ndarray] = {}
    crop_cache: dict[tuple[str, int], payloaddec.RegionCrop] = {}

    for key in sorted(targets):
        scan_id, ordinal = key
        scan = scans[scan_id]
        placed = scan.result.placements[ordinal]
        generation0 = scan.window_evidence[ordinal]
        parent, parent_revision_id = _active_row(
            session, scan, ordinal)
        labels = labels_by_window.get(key)
        if labels is None:
            labels = collect_window_labels(
                placed, label_field, baseline, config)
        label_uses = _label_uses(labels, label_field)
        direct_ids = [
            row.certificate_id for row in label_uses]
        expanded = _expanded_dependencies(
            session, direct_ids,
            parent_revision_id=parent_revision_id)
        dep_id = intern_dependency_set(session, expanded)
        parent_pose = (
            session.revisions[parent_revision_id].pose
            if parent_revision_id is not None else placed.pose)
        pose = parent_pose
        candidate = None
        metrics: dict = {
            "target_tiles": tuple(sorted(targets[key])),
            "n_label_uses": len(label_uses)}

        try:
            if profile == PROFILE_RECAL:
                candidate, detector_metrics, label_uses = (
                    fit_detector_revision(
                        placed, parent, generation0.raw_means, labels,
                        label_field, baseline, config))
                metrics["detector"] = detector_metrics
            else:
                if scan_id not in image_cache:
                    path = Path(scan.source_path)
                    sha, size = receiver.file_identity(path)
                    if (sha, size) != (
                            scan.source_sha256, scan.source_size):
                        raise payloaddec.FatalIntegrityError(
                            f"source TIFF changed for scan {scan_id}")
                    image = receiver.load_image(path)
                    if (tuple(image.shape[:2]) != scan.image_shape
                            or str(np.asarray(image).dtype)
                            != scan.image_dtype):
                        raise payloaddec.FatalIntegrityError(
                            f"source TIFF metadata changed for scan {scan_id}")
                    image_cache[scan_id] = image
                crop_key = (scan_id, int(placed.region_index))
                if crop_key not in crop_cache:
                    group = [
                        row for row in scan.result.placements
                        if int(row.region_index)
                        == int(placed.region_index)]
                    crop_cache[crop_key] = payloaddec.region_extent_crop(
                        image_cache[scan_id], group)
                pose_candidate, means, pose_metrics = refine_pose_on_labels(
                    crop_cache[crop_key], placed, generation0, labels,
                    config, current_pose=parent_pose,
                    current_means=parent.raw_means,
                    search_config=baseline.envelope.search_config)
                metrics["pose"] = pose_metrics
                chosen_means = np.asarray(parent.raw_means, np.float32)
                if pose_candidate is not None and means is not None:
                    pose = pose_candidate
                    chosen_means = means
                revised_placed = replace(placed, pose=pose)
                if profile == PROFILE_REFINE:
                    if pose_candidate is not None:
                        candidate, detector_metrics = (
                            _fixed_detector_revision(
                                revised_placed, generation0, parent,
                                chosen_means, labels, label_field,
                                baseline, config))
                        metrics["detector"] = detector_metrics
                else:
                    candidate, detector_metrics, label_uses = (
                        fit_detector_revision(
                            revised_placed, parent, chosen_means, labels,
                            label_field, baseline, config))
                    metrics["detector"] = detector_metrics
                    if candidate is None and pose_candidate is not None:
                        candidate, fallback_metrics = (
                            _fixed_detector_revision(
                                revised_placed, generation0, parent,
                                chosen_means, labels, label_field,
                                baseline, config))
                        metrics["fixed_detector_fallback"] = (
                            fallback_metrics)
            if candidate is not None:
                candidate = _set_comparable_owner_rank(
                    candidate, replace(placed, pose=pose), baseline)
                if (pose == parent_pose
                        and np.array_equal(
                            candidate.payload_index,
                            parent.payload_index)
                        and np.array_equal(
                            candidate.payload_llr,
                            parent.payload_llr)):
                    candidate = None
                    metrics["reason"] = "numeric_noop"
        except (ValueError, FloatingPointError) as exc:
            raise payloaddec.FatalIntegrityError(
                "E024 candidate construction failed for "
                f"{scan_id}/w{ordinal}: {exc}") from exc

        accepted_flag = candidate is not None
        reason = (
            "" if accepted_flag else str(
                metrics.get("reason")
                or metrics.get("detector", {}).get("reason")
                or metrics.get("pose", {}).get("reason")
                or "refused"))
        revision_id = revision_identity(
            scan_id, scan.placement_ids[ordinal], generation, profile,
            parent_revision_id, dep_id, label_uses, pose, candidate,
            accepted_flag, reason, metrics)
        record = EvidenceRevision(
            revision_id=revision_id, scan_id=scan_id,
            capture_id=scan.capture_id, placement_ordinal=ordinal,
            placement_id=scan.placement_ids[ordinal],
            generation=generation, arm=profile,
            parent_revision_id=parent_revision_id,
            dependency_set_id=dep_id, label_uses=label_uses,
            pose=pose, emission=candidate, accepted=accepted_flag,
            refuse_reason=reason, metrics=metrics)
        if accepted_flag:
            accepted.append(record)
            statistics["accepted"] += 1
        else:
            refused.append(record)
            statistics[f"refused:{reason}"] += 1

    # Prove files did not change while pose work was in flight.
    for scan_id in image_cache:
        scan = scans[scan_id]
        if receiver.file_identity(scan.source_path) != (
                scan.source_sha256, scan.source_size):
            raise payloaddec.FatalIntegrityError(
                f"source TIFF changed during E024 scan {scan_id}")
    statistics["candidate_windows"] = len(targets)
    statistics["source_tiff_reads"] = len(image_cache)
    return accepted, refused, dict(statistics)


def _revision_for_target(
    session: E024Session,
    baseline_scan: receiver.ScanRecord,
    ordinal: int,
    target: TileKey | None,
    active_map: dict[WindowKey, str],
) -> tuple[payloaddec.WindowEmission, str | None]:
    revision_id = active_map.get((baseline_scan.scan_id, int(ordinal)))
    while revision_id is not None:
        revision = session.revisions[revision_id]
        dependency = session.dependency_sets[revision.dependency_set_id]
        if target is None or target not in dependency.tile_keys:
            assert revision.emission is not None
            return revision.emission, revision_id
        revision_id = revision.parent_revision_id
    return baseline_scan.window_evidence[ordinal], None


def _scan_projection_bound(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    baseline_scan: receiver.ScanRecord,
    active_map: dict[WindowKey, str],
    *,
    target: TileKey | None = None,
) -> tuple[payloaddec.ScanEmission, dict[int, str | None]]:
    rows = []
    selected = {}
    for ordinal in range(len(baseline_scan.result.placements)):
        row, revision_id = _revision_for_target(
            session, baseline_scan, ordinal, target, active_map)
        rows.append(row)
        selected[ordinal] = revision_id
    scan = payloaddec.E022Scan(
        baseline_scan.scan_id, baseline_scan.source_path,
        baseline_scan.source_sha256, baseline_scan.dpi,
        baseline_scan.result)
    return (
        payloaddec.freeze_scan_emission(
            scan, rows, baseline.decode.spec),
        selected)


def _active_projection_digest(
    baseline: receiver.ReceiverSession,
    active_map: dict[WindowKey, str],
    session: E024Session | None = None,
) -> str:
    if not active_map:
        payload = {
            scan.scan_id: scan.emission.pages for scan in baseline.scans}
    else:
        if session is None:
            raise ValueError("active revisions require an E024 session")
        payload = {
            scan.scan_id: _scan_projection_bound(
                session, baseline, scan, active_map)[0].pages
            for scan in baseline.scans
        }
    digest = hashlib.sha256()
    receiver._canonical_update(digest, payload)
    return digest.hexdigest()


def _projection_vectors(
    emission: payloaddec.ScanEmission,
    page: int,
) -> dict[int, tuple[float, int]]:
    vector = emission.pages.get(page)
    if vector is None:
        return {}
    return {
        int(index): (float(llr), int(owner))
        for index, llr, owner in zip(
            vector["index"], vector["llr"], vector["owner"], strict=True)
    }


def _build_patches(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    old_active: dict[WindowKey, str],
    new_active: dict[WindowKey, str],
    generation: int,
) -> list[CellPatch]:
    patches = []
    for scan in baseline.scans:
        old = _scan_projection_bound(
            session, baseline, scan, old_active)[0]
        new = _scan_projection_bound(
            session, baseline, scan, new_active)[0]
        for page in sorted(set(old.pages) | set(new.pages)):
            before = _projection_vectors(old, page)
            after = _projection_vectors(new, page)
            indices = sorted(set(before) | set(after))
            changed = [
                index for index in indices
                if before.get(index) != after.get(index)
            ]
            if not changed:
                continue
            payload_indices = np.asarray(changed, np.int64)
            previous_owner = np.asarray([
                before.get(index, (0.0, -1))[1] for index in changed
            ], np.int32)
            new_owner = np.asarray([
                after.get(index, (0.0, -1))[1] for index in changed
            ], np.int32)
            previous_sha = projection_digest(
                {} if page not in old.pages else {page: old.pages[page]})
            new_sha = projection_digest(
                {} if page not in new.pages else {page: new.pages[page]})
            patches.append(CellPatch(
                patch_id=patch_identity(
                    generation, scan.scan_id, scan.capture_id, int(page),
                    payload_indices, previous_owner, new_owner,
                    previous_sha, new_sha),
                generation=generation,
                scan_id=scan.scan_id, capture_id=scan.capture_id,
                page=int(page), payload_indices=payload_indices,
                previous_owner=previous_owner, new_owner=new_owner,
                previous_projection_sha256=previous_sha,
                new_projection_sha256=new_sha))
    return patches


@dataclass(frozen=True)
class ResolvedComponent:
    scan_id: str
    capture_id: str
    index: np.ndarray
    llr: np.ndarray
    numeric_sha256: str
    revision_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedTileEvidence:
    tile_key: TileKey
    components: tuple[ResolvedComponent, ...]
    union_index: np.ndarray
    union_llr: np.ndarray
    union_numeric_sha256: str
    revision_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...]


def _tile_numeric_digest(
    index: np.ndarray,
    llr_values: np.ndarray,
    baseline: receiver.ReceiverSession,
    key: TileKey,
) -> str:
    gathered, mask, _coverage = ldpc.gather_tile_llrs(
        llr_values, index, baseline.decode.spec, baseline.decode.seed,
        key[1:])
    return _hash_parts(
        b"e024/numeric-tile-evidence/v1",
        repr(tuple(key)).encode("ascii"),
        np.ascontiguousarray(gathered, dtype="<f8").tobytes(),
        np.packbits(mask, bitorder="little").tobytes())


def _resolved_component(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    scan: receiver.ScanRecord,
    target: TileKey,
    active_map: dict[WindowKey, str],
    projection: tuple[
        payloaddec.ScanEmission, dict[int, str | None]
    ] | None = None,
) -> ResolvedComponent | None:
    if projection is not None:
        # A generic scan projection is reusable only when none of this
        # scan's active revisions depends on the target.  Otherwise the
        # documented predecessor walk must be performed for this tile.
        for (scan_id, _ordinal), revision_id in active_map.items():
            if scan_id != scan.scan_id:
                continue
            dependency = session.dependency_sets[
                session.revisions[revision_id].dependency_set_id]
            if target in dependency.tile_keys:
                projection = None
                break
    emission, selected = (
        _scan_projection_bound(
            session, baseline, scan, active_map, target=target)
        if projection is None else projection)
    vector = emission.pages.get(target[0])
    if vector is None:
        return None
    codes = receiver._payload_tile_codes(
        baseline.decode.spec, baseline.decode.seed)[
            np.asarray(vector["index"], np.int64)]
    tiles_x = int(np.ceil(
        baseline.decode.spec.page_cells_yx[1] / ldpc.TILE_CELLS))
    target_code = int(target[1] * tiles_x + target[2])
    in_tile = codes == target_code
    if not in_tile.any():
        return None
    # Conservative provenance: ownership is a competition, so every active
    # revision in this scan can influence which window wins an overlap.
    revision_ids = tuple(sorted({
        revision_id for revision_id in selected.values()
        if revision_id is not None
    }))
    dependencies: set[str] = set()
    for revision_id in revision_ids:
        dependencies.update(session.dependency_sets[
            session.revisions[revision_id].dependency_set_id].certificate_ids)
    index = np.asarray(vector["index"])[in_tile]
    llr_values = np.asarray(vector["llr"])[in_tile]
    numeric = _tile_numeric_digest(
        index, llr_values, baseline, target)
    return ResolvedComponent(
        scan_id=scan.scan_id, capture_id=scan.capture_id,
        index=index, llr=llr_values, numeric_sha256=numeric,
        revision_ids=revision_ids,
        dependency_ids=tuple(sorted(dependencies)))


def resolve_target_evidence(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    target: TileKey,
    active_map: dict[WindowKey, str] | None = None,
    projection_cache: dict[
        str, tuple[payloaddec.ScanEmission, dict[int, str | None]]
    ] | None = None,
) -> ResolvedTileEvidence | None:
    """Resolve a leave-target-out field and sum only independent captures."""
    active = (
        session.active_revision_map if active_map is None else active_map)
    components = tuple(
        row for row in (
            _resolved_component(
                session, baseline, scan, target, active,
                None if projection_cache is None
                else projection_cache.get(scan.scan_id))
            for scan in baseline.scans)
        if row is not None)
    if not components:
        return None
    capture_ids = [row.capture_id for row in components]
    if len(capture_ids) != len(set(capture_ids)):
        raise payloaddec.FatalIntegrityError(
            "E024 target resolver would sum one capture twice")
    concatenated_index = np.concatenate([
        np.asarray(component.index, np.int64)
        for component in components])
    concatenated_llr = np.concatenate([
        np.asarray(component.llr, np.float64)
        for component in components])
    index, inverse = np.unique(
        concatenated_index, return_inverse=True)
    llr_values = np.zeros(index.size, np.float64)
    np.add.at(llr_values, inverse, concatenated_llr)
    numeric = _tile_numeric_digest(
        index, llr_values, baseline, target)
    revisions = tuple(sorted({
        value for row in components for value in row.revision_ids
    }))
    dependencies = tuple(sorted({
        value for row in components for value in row.dependency_ids
    }))
    by_id = {
        row.certificate_id: row.tile_key
        for row in session.certificates.values()
    }
    if target in {by_id[value] for value in dependencies}:
        raise payloaddec.FatalIntegrityError(
            f"E024 target {target} survived leave-target-out resolution")
    return ResolvedTileEvidence(
        tile_key=target, components=components,
        union_index=index, union_llr=llr_values,
        union_numeric_sha256=numeric,
        revision_ids=revisions, dependency_ids=dependencies)


def _decoder_profile(
    baseline: receiver.ReceiverSession,
    max_iters: int,
    alpha: float,
) -> str:
    return (
        f"{baseline.envelope.rate_id}/decode_tile-max{int(max_iters)}-"
        f"alpha{float(alpha):g}")


def _apply_attempt(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    generation: int,
    target: TileKey,
    stage: str,
    source: str,
    index: np.ndarray,
    llr_values: np.ndarray,
    numeric_sha256: str,
    component_sha256: tuple[tuple[str, str], ...],
    revision_ids: tuple[str, ...],
    dependency_ids: tuple[str, ...],
    max_iters: int,
) -> tuple[FeedbackAttempt, CertificateRecord | None, bool]:
    profile = _decoder_profile(
        baseline, max_iters, session.envelope.config.bp_alpha)
    identity = attempt_identity(target, profile, numeric_sha256)
    if identity in session.attempt_ids:
        row = next(
            attempt for attempt in session.attempts
            if attempt.attempt_id == identity)
        return row, session.certificates.get(target), False
    dep_id = intern_dependency_set(session, dependency_ids)
    if target in session.dependency_sets[dep_id].tile_keys:
        raise payloaddec.FatalIntegrityError(
            f"E024 attempt for {target} depends on its target")
    evaluation = payloaddec.evaluate_tile(
        llr_values, index, baseline.decode.spec, baseline.decode.seed,
        target[1:], baseline.decode.ldpc_spec, max_iters=max_iters,
        alpha=session.envelope.config.bp_alpha)
    certificate = None
    certified_new = False
    if evaluation.state == "certified":
        assert evaluation.user_bits is not None
        certificate = _add_certificate(
            session, key=target, user_bits=evaluation.user_bits,
            source=f"e024:{stage}:{source}",
            origin_attempt_id=identity, born_generation=generation,
            dependency_set_id=dep_id,
            provenance={
                "numeric_evidence_sha256": numeric_sha256,
                "input_revision_ids": list(revision_ids)})
        certified_new = certificate.born_generation == generation
    old_state = session.tiles[target]
    state = (
        "certified" if target in session.certificates
        else evaluation.state)
    session.tiles[target] = FeedbackTileState(
        state=state, latest_attempt_id=identity,
        n_informative_best=max(
            old_state.n_informative_best, evaluation.n_informative),
        decoder_attempts=(
            old_state.decoder_attempts + int(evaluation.decoder_invoked)))
    attempt = FeedbackAttempt(
        attempt_id=identity, generation=generation, tile_key=target,
        stage=stage, source=source, decoder_profile=profile,
        numeric_evidence_sha256=numeric_sha256,
        component_sha256=component_sha256,
        input_revision_ids=tuple(sorted(set(revision_ids))),
        dependency_set_id=dep_id, state=evaluation.state,
        decoder_invoked=evaluation.decoder_invoked,
        k_eff=evaluation.k_eff, n_nonshort=evaluation.n_nonshort,
        n_informative=evaluation.n_informative,
        coverage=evaluation.coverage, n_iters=evaluation.n_iters,
        syndrome_ok=evaluation.syndrome_ok, crc_ok=evaluation.crc_ok,
        n_erased=evaluation.n_erased, certified_new=certified_new)
    session.attempts.append(attempt)
    session.attempt_ids.add(identity)
    return attempt, certificate, True


def _decode_changed_targets(
    session: E024Session,
    previous: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    generation: int,
    targets: Iterable[TileKey],
    new_active: dict[WindowKey, str],
    on_attempt: Callable[[
        E024Session, FeedbackAttempt, dict[WindowKey, str]
    ], None] | None = None,
) -> tuple[list[FeedbackAttempt], list[CertificateRecord], dict]:
    attempts: list[FeedbackAttempt] = []
    certificates: list[CertificateRecord] = []
    counts = Counter()
    old_active = previous.active_revision_map
    config = session.envelope.config
    old_projection_cache = {
        scan.scan_id: _scan_projection_bound(
            previous, baseline, scan, old_active)
        for scan in baseline.scans
    }
    new_projection_cache = {
        scan.scan_id: _scan_projection_bound(
            session, baseline, scan, new_active)
        for scan in baseline.scans
    }

    for target in sorted(set(targets)):
        if target in session.certificates:
            continue
        old = resolve_target_evidence(
            previous, baseline, target, old_active,
            projection_cache=old_projection_cache)
        new = resolve_target_evidence(
            session, baseline, target, new_active,
            projection_cache=new_projection_cache)
        if new is None:
            continue
        if old is not None and (
                old.union_numeric_sha256 == new.union_numeric_sha256):
            continue
        counts["changed_targets"] += 1

        old_components = (
            {} if old is None else
            {row.scan_id: row for row in old.components})
        certified = False
        for component in new.components:
            previous_component = old_components.get(component.scan_id)
            if (previous_component is not None
                    and previous_component.numeric_sha256
                    == component.numeric_sha256):
                continue
            row, certificate, created = _apply_attempt(
                session, baseline, generation=generation, target=target,
                stage="feedback-scan60", source=component.scan_id,
                index=component.index, llr_values=component.llr,
                numeric_sha256=component.numeric_sha256,
                component_sha256=((component.capture_id,
                                   component.numeric_sha256),),
                revision_ids=component.revision_ids,
                dependency_ids=component.dependency_ids,
                max_iters=config.baseline_bp_max_iters)
            if created:
                attempts.append(row)
                counts["scan60_records"] += 1
                counts["crc_calls"] += int(row.decoder_invoked)
                if on_attempt is not None:
                    on_attempt(session, row, new_active)
            if certificate is not None:
                if row.certified_new:
                    certificates.append(certificate)
                certified = True
                break
        if certified:
            continue

        component_rows = tuple(
            (row.capture_id, row.numeric_sha256)
            for row in new.components)
        union_row, certificate, created = _apply_attempt(
            session, baseline, generation=generation, target=target,
            stage="feedback-union60", source="union",
            index=new.union_index, llr_values=new.union_llr,
            numeric_sha256=new.union_numeric_sha256,
            component_sha256=component_rows,
            revision_ids=new.revision_ids,
            dependency_ids=new.dependency_ids,
            max_iters=config.baseline_bp_max_iters)
        if created:
            attempts.append(union_row)
            counts["union60_records"] += 1
            counts["crc_calls"] += int(union_row.decoder_invoked)
            if on_attempt is not None:
                on_attempt(session, union_row, new_active)
        if certificate is not None:
            if union_row.certified_new:
                certificates.append(certificate)
            continue
        if union_row.state != "attempted_failed":
            continue

        retry_row, certificate, created = _apply_attempt(
            session, baseline, generation=generation, target=target,
            stage="feedback-retry150", source="union",
            index=new.union_index, llr_values=new.union_llr,
            numeric_sha256=new.union_numeric_sha256,
            component_sha256=component_rows,
            revision_ids=new.revision_ids,
            dependency_ids=new.dependency_ids,
            max_iters=config.retry_bp_max_iters)
        if created:
            attempts.append(retry_row)
            counts["retry150_records"] += 1
            counts["crc_calls"] += int(retry_row.decoder_invoked)
            if on_attempt is not None:
                on_attempt(session, retry_row, new_active)
        if certificate is not None and retry_row.certified_new:
            certificates.append(certificate)
    counts["new_certificates"] = len({
        row.certificate_id for row in certificates})
    return attempts, certificates, dict(counts)


def _run_feedback_generation_unvalidated(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    on_attempt: Callable[[
        E024Session, FeedbackAttempt, dict[WindowKey, str]
    ], None] | None = None,
) -> tuple[E024Session, dict]:
    """Production generation transition without recursive state validation."""
    if session.envelope.profile == PROFILE_CONTROL:
        return session, {
            "noop": True, "reason": "control_profile",
            "generation": session.head.ordinal}
    if session.head.fixed_point:
        return session, {
            "noop": True, "reason": "fixed_point",
            "generation": session.head.ordinal}

    generation = session.head.ordinal + 1
    frontier = tuple(sorted(
        row.certificate_id for row in session.certificates.values()))
    frontier_sha = _hash_parts(
        b"e024/label-frontier/v1",
        *[value.encode("ascii") for value in frontier])
    label_field = export_certified_labels(
        session, baseline, certificate_ids=frontier)
    targets, labels = _candidate_windows(
        session, baseline, label_field)
    if not targets:
        working = copy.deepcopy(session)
        statistics = {
            "reason": "no_reachable_windows",
            "revision": {},
            "decode": {},
            "patches": 0,
            "changed_cells": 0,
            "certified_before": len(session.certificates),
            "certified_after": len(session.certificates),
            "new_certificates": 0,
            "target_windows": 0,
            "target_tiles": 0,
        }
        generation_id = generation_identity(
            generation, session.head.generation_id, frontier_sha,
            session.head.active_revisions, (), (), (), (), (),
            session.head.active_projection_sha256, True, statistics)
        working.generations.append(GenerationRecord(
            generation_id=generation_id, ordinal=generation,
            parent_generation_id=session.head.generation_id,
            label_frontier_ids=frontier,
            label_frontier_sha256=frontier_sha,
            active_revisions=session.head.active_revisions,
            accepted_revision_ids=(), refused_revision_ids=(),
            patch_ids=(), attempt_ids=(), new_certificate_ids=(),
            active_projection_sha256=(
                session.head.active_projection_sha256),
            fixed_point=True, statistics=statistics))
        return working, {
            "noop": False, "terminal_noop": True,
            "generation": generation, "fixed_point": True,
            **statistics}

    working = copy.deepcopy(session)
    accepted, refused, revision_stats = _build_revisions(
        working, baseline, label_field, targets, labels, generation)
    for revision in [*accepted, *refused]:
        old = working.revisions.get(revision.revision_id)
        if old is not None and old != revision:
            raise ValueError("E024 revision identity collision")
        working.revisions[revision.revision_id] = revision

    old_active = session.active_revision_map
    new_active = dict(old_active)
    for revision in accepted:
        new_active[(revision.scan_id,
                    revision.placement_ordinal)] = revision.revision_id
    patches = _build_patches(
        working, baseline, old_active, new_active, generation)
    target_tiles = {
        tile for rows in targets.values() for tile in rows}
    attempt_start = len(working.attempts)
    _attempts, certificates, decode_stats = _decode_changed_targets(
        working, session, baseline, generation=generation,
        targets=target_tiles, new_active=new_active,
        on_attempt=on_attempt)
    new_certificates = {
        row.certificate_id: row for row in certificates}

    for patch in patches:
        old = working.patches.get(patch.patch_id)
        if old is not None and old != patch:
            raise ValueError("E024 patch identity collision")
        working.patches[patch.patch_id] = patch

    active_rows = tuple(sorted(
        (scan_id, int(ordinal), revision_id)
        for (scan_id, ordinal), revision_id in new_active.items()))
    accepted_ids = tuple(sorted(
        revision.revision_id for revision in accepted))
    refused_ids = tuple(sorted(
        revision.revision_id for revision in refused))
    patch_ids = tuple(sorted(patch.patch_id for patch in patches))
    attempt_ids = tuple(
        row.attempt_id for row in working.attempts[attempt_start:])
    new_certificate_ids = tuple(sorted(new_certificates))
    active_sha = _active_projection_digest(
        baseline, new_active, working)
    if not new_certificate_ids:
        fixed_point = True
    else:
        next_frontier = tuple(sorted(
            row.certificate_id for row in working.certificates.values()))
        next_labels = export_certified_labels(
            working, baseline, certificate_ids=next_frontier)
        next_targets, _next_window_labels = _candidate_windows(
            working, baseline, next_labels)
        fixed_point = not next_targets
    statistics = {
        "revision": revision_stats,
        "decode": decode_stats,
        "patches": len(patches),
        "changed_cells": sum(
            int(patch.payload_indices.size) for patch in patches),
        "certified_before": len(session.certificates),
        "certified_after": len(working.certificates),
        "new_certificates": len(new_certificate_ids),
        "target_windows": len(targets),
        "target_tiles": len(target_tiles),
        "reason": (
            "no_new_certificates" if not new_certificate_ids
            else "no_reachable_windows_after_certificates"
            if fixed_point else "new_feedback_frontier"),
    }
    generation_id = generation_identity(
        generation, session.head.generation_id, frontier_sha,
        active_rows, accepted_ids, refused_ids, patch_ids, attempt_ids,
        new_certificate_ids, active_sha, fixed_point, statistics)
    working.generations.append(GenerationRecord(
        generation_id=generation_id, ordinal=generation,
        parent_generation_id=session.head.generation_id,
        label_frontier_ids=frontier,
        label_frontier_sha256=frontier_sha,
        active_revisions=active_rows,
        accepted_revision_ids=accepted_ids,
        refused_revision_ids=refused_ids,
        patch_ids=patch_ids, attempt_ids=attempt_ids,
        new_certificate_ids=new_certificate_ids,
        active_projection_sha256=active_sha,
        fixed_point=fixed_point, statistics=statistics))
    return working, {
        "noop": False, "generation": generation,
        "fixed_point": fixed_point, **statistics}


def run_feedback_generation(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    baseline_path: Path | str | None = None,
    on_attempt: Callable[[
        E024Session, FeedbackAttempt, dict[WindowKey, str]
    ], None] | None = None,
) -> tuple[E024Session, dict]:
    """Run and validate one synchronous generation on a private fork."""
    validate_session(
        session, baseline, baseline_path=baseline_path,
        check_baseline_artifact=False, validate_baseline=False,
        replay_projections=False, replay_attempts=False,
        replay_decisions=False)
    working, report = _run_feedback_generation_unvalidated(
        session, baseline, on_attempt=on_attempt)
    if working is not session:
        validate_session(
            working, baseline, baseline_path=baseline_path,
            check_baseline_artifact=False, validate_baseline=False,
            replay_projections=False, replay_attempts=False,
            replay_decisions=False)
    return working, report


def run_feedback(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    baseline_path: Path | str | None = None,
    max_generations: int | None = None,
    on_attempt: Callable[[
        E024Session, FeedbackAttempt, dict[WindowKey, str]
    ], None] | None = None,
    on_generation: Callable[[E024Session, dict], None] | None = None,
) -> tuple[E024Session, dict]:
    """Run automatic synchronous generations until a local fixed point."""
    limit = (
        session.envelope.config.max_generations
        if max_generations is None else int(max_generations))
    if limit < 0:
        raise ValueError("max_generations must be non-negative")
    current = session
    reports = []
    for _ in range(limit):
        advanced, report = run_feedback_generation(
            current, baseline, baseline_path=baseline_path,
            on_attempt=on_attempt)
        reports.append(report)
        if advanced is current:
            break
        current = advanced
        if on_generation is not None:
            on_generation(current, report)
        if current.head.fixed_point:
            break
    return current, {
        "noop": current is session,
        "generations_run": sum(not row.get("noop", False)
                               for row in reports),
        "reports": reports,
        "fixed_point": current.head.fixed_point,
        "certified": len(current.certificates),
        "authoritative_sha256": authoritative_digest(current),
    }


def active_scan_emissions(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    active_map: dict[WindowKey, str] | None = None,
) -> dict[str, payloaddec.ScanEmission]:
    """Observer/qualification view of the non-target-specific active field."""
    active = (
        session.active_revision_map if active_map is None else active_map)
    return {
        scan.scan_id: _scan_projection_bound(
            session, baseline, scan, active)[0]
        for scan in baseline.scans
    }


def materialize_receiver_view(
    session: E024Session,
    baseline: receiver.ReceiverSession,
    *,
    active_map: dict[WindowKey, str] | None = None,
) -> receiver.ReceiverSession:
    """Build an observer-only ReceiverSession-like view for diagnostics."""
    view = baseline.fork()
    emissions = active_scan_emissions(
        session, baseline, active_map=active_map)
    view.scans = [
        replace(scan, emission=emissions[scan.scan_id])
        for scan in baseline.scans
    ]
    view.decode.scans = [
        emissions[scan.scan_id] for scan in baseline.scans]
    for key, certificate in session.certificates.items():
        outcome = view.decode.outcome(key[0], key[1:])
        outcome.state = "certified"
        outcome.user_bits = certificate.user_bits.copy()
        outcome.certified_by = certificate.source
    for key, state in session.tiles.items():
        if key in session.certificates:
            continue
        outcome = view.decode.outcome(key[0], key[1:])
        outcome.state = state.state
        outcome.n_informative_best = state.n_informative_best
    # This is intentionally not a valid E023b transaction state: E024
    # attempts and emissions have their own ledger.  It is never saved.
    return view


def report_dict(
    session: E024Session,
    baseline: receiver.ReceiverSession,
) -> dict:
    return {
        "algorithm_id": session.envelope.algorithm_id,
        "state_version": 1,
        "profile": session.envelope.profile,
        "config": session.envelope.config.__dict__,
        "config_sha256": session.envelope.config_sha256,
        "evidence_policy": session.envelope.evidence_policy,
        "implementation_sha256": [
            {"component": name, "sha256": sha256}
            for name, sha256
            in session.envelope.implementation_sha256
        ],
        "certificate_seed_sha256": (
            session.envelope.certificate_seed_sha256),
        "authoritative_sha256": authoritative_digest(session),
        "baseline": {
            "path": session.baseline.path,
            "file_sha256": session.baseline.file_sha256,
            "file_size": session.baseline.file_size,
            "authoritative_sha256": (
                session.baseline.authoritative_sha256),
            "format_id": session.baseline.format_id,
            "cell_dots": session.baseline.cell_dots,
            "rate_id": session.baseline.rate_id,
            "captures": list(session.baseline.ordered_capture_ids),
            "pages": list(session.baseline.pages),
            "page_cells_yx": list(
                session.baseline.page_cells_yx),
            "scans": [{
                "scan_id": scan.scan_id,
                "capture_id": scan.capture_id,
                "source_path": scan.source_path,
                "source_sha256": scan.source_sha256,
                "source_size": scan.source_size,
                "dpi": scan.dpi,
                "image_shape": list(scan.image_shape),
                "image_dtype": scan.image_dtype,
            } for scan in baseline.scans],
        },
        "summary": session.summary(),
        "generations": [{
            "ordinal": row.ordinal,
            "generation_id": row.generation_id,
            "parent_generation_id": row.parent_generation_id,
            "label_frontier_sha256": row.label_frontier_sha256,
            "label_count": len(row.label_frontier_ids),
            "accepted_revisions": len(row.accepted_revision_ids),
            "refused_revisions": len(row.refused_revision_ids),
            "patches": len(row.patch_ids),
            "attempts": len(row.attempt_ids),
            "new_certificates": len(row.new_certificate_ids),
            "fixed_point": row.fixed_point,
            "statistics": row.statistics,
            "label_frontier_ids": list(row.label_frontier_ids),
            "active_revisions": [
                {
                    "scan_id": scan_id,
                    "placement_ordinal": ordinal,
                    "revision_id": revision_id,
                }
                for scan_id, ordinal, revision_id
                in row.active_revisions
            ],
            "accepted_revision_ids": list(
                row.accepted_revision_ids),
            "refused_revision_ids": list(
                row.refused_revision_ids),
            "patch_ids": list(row.patch_ids),
            "attempt_ids": list(row.attempt_ids),
            "new_certificate_ids": list(
                row.new_certificate_ids),
        } for row in session.generations],
        "revisions": [{
            "revision_id": row.revision_id,
            "generation": row.generation,
            "arm": row.arm,
            "accepted": row.accepted,
            "refuse_reason": row.refuse_reason,
            "scan_id": row.scan_id,
            "capture_id": row.capture_id,
            "placement_ordinal": row.placement_ordinal,
            "placement_id": row.placement_id,
            "parent_revision_id": row.parent_revision_id,
            "dependency_set_id": row.dependency_set_id,
            "label_uses": [{
                "certificate_id": use.certificate_id,
                "role": use.role,
                "n_sites": use.n_sites,
                "payload_indices_sha256": (
                    use.payload_indices_sha256),
            } for use in row.label_uses],
            "pose": {
                "origin_yx": list(row.pose.origin_yx),
                "jacobian_yx": [
                    list(value) for value
                    in row.pose.jacobian_yx],
                "angle_deg": row.pose.angle_deg,
                "pitch_px": row.pose.pitch_px,
                "phase_yx": list(row.pose.phase_yx),
                "footing_factor": row.pose.footing_factor,
            },
            "emission": (
                None if row.emission is None else {
                    "detector_profile": (
                        row.emission.detector_profile),
                    "page": row.emission.page,
                    "region_index": row.emission.region_index,
                    "n_core_cells": int(
                        row.emission.page_cells_yx.shape[0]),
                    "n_payload_cells": int(
                        row.emission.payload_index.size),
                    "owner_rank_logloss": (
                        row.emission.heldout_logloss),
                    "dense_heldout_logloss": (
                        row.emission.diagnostics.get(
                            "feedback_dense_heldout_logloss")),
                    "n_train_labels": row.emission.n_train_labels,
                    "n_heldout": row.emission.n_heldout,
                    "payload_index_sha256": _array_digest(
                        row.emission.payload_index, "<i8"),
                    "payload_llr_sha256": _array_digest(
                        row.emission.payload_llr, "<f4"),
                    "raw_means_sha256": _array_digest(
                        row.emission.raw_means, "<f4"),
                    "diagnostics": row.emission.diagnostics,
                }),
            "metrics": row.metrics,
        } for row in sorted(
            session.revisions.values(),
            key=lambda value: (
                value.generation, value.scan_id,
                value.placement_ordinal))],
        "patches": [{
            "patch_id": row.patch_id,
            "generation": row.generation,
            "scan_id": row.scan_id,
            "capture_id": row.capture_id,
            "page": row.page,
            "changed_cells": int(row.payload_indices.size),
            "payload_indices_sha256": _array_digest(
                row.payload_indices, "<i8"),
            "previous_owner_sha256": _array_digest(
                row.previous_owner, "<i4"),
            "new_owner_sha256": _array_digest(
                row.new_owner, "<i4"),
            "owner_changes": int(np.sum(
                row.previous_owner != row.new_owner)),
            "previous_projection_sha256": (
                row.previous_projection_sha256),
            "new_projection_sha256": row.new_projection_sha256,
        } for row in sorted(
            session.patches.values(),
            key=lambda value: (
                value.generation, value.scan_id, value.page))],
        "dependency_sets": [{
            "dependency_set_id": row.dependency_set_id,
            "certificate_ids": list(row.certificate_ids),
            "tile_keys": [list(value) for value in row.tile_keys],
            "size": len(row.certificate_ids),
        } for row in sorted(
            session.dependency_sets.values(),
            key=lambda value: value.dependency_set_id)],
        "attempts": [{
            "attempt_id": row.attempt_id,
            "generation": row.generation,
            "tile_key": list(row.tile_key),
            "stage": row.stage, "source": row.source,
            "decoder_profile": row.decoder_profile,
            "numeric_evidence_sha256": row.numeric_evidence_sha256,
            "component_sha256": [list(value)
                                 for value in row.component_sha256],
            "input_revision_ids": list(row.input_revision_ids),
            "dependency_set_id": row.dependency_set_id,
            "state": row.state,
            "decoder_invoked": row.decoder_invoked,
            "k_eff": row.k_eff,
            "n_nonshort": row.n_nonshort,
            "n_informative": row.n_informative,
            "coverage": row.coverage,
            "n_iters": row.n_iters,
            "syndrome_ok": row.syndrome_ok,
            "crc_ok": row.crc_ok,
            "n_erased": row.n_erased,
            "certified_new": row.certified_new,
        } for row in session.attempts],
        "certificates": [{
            "tile_key": list(key),
            "certificate_id": row.certificate_id,
            "source": row.source,
            "born_generation": row.born_generation,
            "dependency_set_id": row.dependency_set_id,
            "user_bits_sha256": row.user_bits_sha256,
            "origin_attempt_id": row.origin_attempt_id,
            "provenance": row.provenance,
        } for key, row in sorted(session.certificates.items())],
        "tiles": [{
            "tile_key": list(key),
            "state": row.state,
            "latest_attempt_id": row.latest_attempt_id,
            "n_informative_best": row.n_informative_best,
            "decoder_attempts": row.decoder_attempts,
            "certificate_id": (
                None if key not in session.certificates else
                session.certificates[key].certificate_id),
        } for key, row in sorted(session.tiles.items())],
        "baseline_certified": sum(
            out.state == "certified"
            for out in baseline.decode.tiles.values()),
        "feedback_certified": sum(
            row.born_generation > 0
            for row in session.certificates.values()),
        "external_seed_certified": sum(
            row.source == "certificate-union"
            for row in session.certificates.values()),
    }

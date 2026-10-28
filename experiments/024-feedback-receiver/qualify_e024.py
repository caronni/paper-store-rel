#!/usr/bin/env python
"""Blind-first numerical qualification for the E024 feedback profiles.

Every selected current-schema E023b baseline is run through the complete
control/recal/refine/combined factorial before the E018 printed ground-truth
array is opened.  The blind boundary retains only compact certificate bytes
and ordinary accounting reports; ground truth is used solely to check
certificate correctness after all detector/decoder decisions are frozen.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E023B_HERE = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(E023B_HERE))

from paperholo import feedback, feedbackstate, payloaddec, receiver  # noqa: E402
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402

# Qualification-only reuse of the exact E018 GT construction and certificate
# comparison used for E023b.  Importing this module does not open ground truth;
# _load_ground_truth is called only after the blind barrier below.
import qualify_e023b_arms as e023b_qual  # noqa: E402


BUILD = HERE / "build"
PROFILE_ORDER = (
    feedbackstate.PROFILE_CONTROL,
    feedbackstate.PROFILE_RECAL,
    feedbackstate.PROFILE_REFINE,
    feedbackstate.PROFILE_COMBINED,
)


def _stream_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(
        report, indent=2, sort_keys=True, default=_json_default) + "\n")
    os.replace(tmp, path)


def _descriptor(format_id: str):
    rows = [
        descriptor for descriptor in FORMAT_REGISTRY
        if descriptor.format_id == format_id]
    if len(rows) != 1:
        raise ValueError(
            f"format registry has {len(rows)} entries for {format_id!r}")
    return rows[0]


def _parse_baselines(values: list[str]) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    labels: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(
                f"--baseline {value!r} must have the form LABEL=PATH")
        label, raw_path = value.split("=", 1)
        label = label.strip()
        if not label or not raw_path:
            raise ValueError(
                f"--baseline {value!r} must have a non-empty label and path")
        if label in labels:
            raise ValueError(f"duplicate baseline label {label!r}")
        labels.add(label)
        rows.append((label, Path(raw_path).expanduser().resolve()))
    if len(rows) < 2:
        raise ValueError(
            "E024 qualification requires at least two distinct footings")
    paths = [path for _label, path in rows]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate baseline state path")
    return rows


def _pack_bits(bits: np.ndarray) -> tuple[int, bytes]:
    array = np.asarray(bits, np.uint8)
    if (array.ndim != 1
            or not np.all((array == 0) | (array == 1))):
        raise ValueError("certificate bits are malformed")
    return int(array.size), np.packbits(array).tobytes()


def _e023b_certificates(
    session: receiver.ReceiverSession,
) -> dict[tuple[int, int, int], tuple[int, bytes]]:
    return {
        tuple(map(int, key)): _pack_bits(outcome.user_bits)
        for key, outcome in session.decode.tiles.items()
        if (outcome.state == "certified"
            and outcome.user_bits is not None)
    }


def _e024_certificates(
    session: feedbackstate.E024Session,
) -> dict[tuple[int, int, int], tuple[int, bytes]]:
    return {
        tuple(map(int, key)): _pack_bits(certificate.user_bits)
        for key, certificate in session.certificates.items()
    }


def _certificate_summary(certs: dict) -> dict:
    return {
        "count": len(certs),
        "tiles": [list(key) for key in sorted(certs)],
        "set_sha256": e023b_qual._certificate_set_digest(certs),
        "bits_sha256": e023b_qual._certificate_bits_digest(certs),
    }


def _changed_certificates(a: dict, b: dict) -> set:
    return e023b_qual._changed_certificates(a, b)


def _effect(before: dict, after: dict) -> dict:
    gained = set(after) - set(before)
    lost = set(before) - set(after)
    changed = _changed_certificates(before, after)
    return {
        "gained": [list(key) for key in sorted(gained)],
        "gained_count": len(gained),
        "lost": [list(key) for key in sorted(lost)],
        "lost_count": len(lost),
        "changed": [list(key) for key in sorted(changed)],
        "changed_count": len(changed),
        "yield_delta": len(after) - len(before),
    }


def _implementation_digest(rows) -> str:
    normalized = tuple((str(name), str(value)) for name, value in rows)
    payload = json.dumps(
        normalized, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _footing_compatibility(
    baseline: receiver.ReceiverSession,
) -> dict:
    envelope = baseline.envelope
    return {
        "algorithm_id": envelope.algorithm_id,
        "format_id": envelope.format_id,
        "seed_hex": bytes(envelope.seed).hex(),
        "cell_dots": int(envelope.cell_dots),
        "page_cells_yx": [
            int(value) for value in envelope.page_cells_yx],
        "pages": [int(page) for page in envelope.pages],
        "rate_id": envelope.rate_id,
        "evidence_policy": envelope.evidence_policy,
        "detector_profile": envelope.detector_profile,
        "search_config_sha256": envelope.search_config_sha256,
        "ordered_capture_ids": [
            scan.capture_id for scan in baseline.scans],
    }


def _validate_footing_compatibility(
    rows: list[tuple[str, dict]],
) -> dict:
    if not rows:
        raise ValueError("E024 qualification has no footings")
    reference_label, reference = rows[0]
    if not reference["ordered_capture_ids"]:
        raise ValueError(
            f"{reference_label}: footing contains no captures")
    for label, candidate in rows[1:]:
        differences = [
            name for name in reference
            if candidate.get(name) != reference[name]]
        if differences:
            raise ValueError(
                f"{label}: E024 footing is not comparable with "
                f"{reference_label}; differing fields: "
                f"{', '.join(differences)}")
    return {
        "compatible": True,
        "reference_label": reference_label,
        "compared_labels": [label for label, _row in rows],
        "identity": reference,
        "excluded_raster_fields": [
            "dpi", "source paths/hashes/sizes", "image metadata",
            "placements", "scan IDs", "user footing labels"],
    }


def _validate_distinct_footing_identities(
    rows: list[tuple[str, dict]],
) -> dict:
    if len(rows) < 2:
        raise ValueError(
            "E024 qualification requires at least two distinct footings")
    file_identities = [
        (row["file_sha256"], int(row["file_size"]))
        for _label, row in rows]
    if len(file_identities) != len(set(file_identities)):
        raise ValueError(
            "E024 qualification footings reuse one baseline artifact")
    authoritative = [
        row["authoritative_sha256"] for _label, row in rows]
    if len(authoritative) != len(set(authoritative)):
        raise ValueError(
            "E024 qualification footings reuse one authoritative state")
    return {
        "distinct": True,
        "labels": [label for label, _row in rows],
        "file_identities": [
            {
                "label": label,
                "file_sha256": row["file_sha256"],
                "file_size": int(row["file_size"]),
                "authoritative_sha256": row["authoritative_sha256"],
            }
            for label, row in rows
        ],
    }


def _preflight_baselines(
    rows: list[tuple[str, Path]],
) -> dict:
    """Validate every footing before any factorial profile is allowed."""
    identities = []
    compatibility = []
    for label, path in rows:
        file_sha256, file_size = _stream_sha256(path)
        baseline = receiver.load_session(path)
        if baseline.decode.fatal:
            raise ValueError(
                f"{label}: E023b footing carries fatal integrity records")
        identity = {
            "file_sha256": file_sha256,
            "file_size": file_size,
            "authoritative_sha256":
                receiver.authoritative_digest(baseline),
        }
        identities.append((label, identity))
        compatibility.append(
            (label, _footing_compatibility(baseline)))
        del baseline
        gc.collect()
    return {
        "identities": _validate_distinct_footing_identities(
            identities),
        "compatibility": _validate_footing_compatibility(
            compatibility),
    }


def _validate_union_footing_bindings(
    union_proof: dict,
    preflight: dict,
) -> dict:
    sources = union_proof.get("sources")
    if not isinstance(sources, list):
        raise ValueError(
            "certificate union proof lacks source identities")
    source_identities = {
        (
            row["state_file_sha256"],
            int(row["state_file_size"]),
            row["authoritative_sha256"],
        ): row["label"]
        for row in sources
    }
    bindings = []
    for footing in preflight["identities"]["file_identities"]:
        identity = (
            footing["file_sha256"],
            int(footing["file_size"]),
            footing["authoritative_sha256"],
        )
        source_label = source_identities.get(identity)
        if source_label is None:
            raise ValueError(
                f"{footing['label']}: footing is not an exact source "
                "artifact in the certificate union")
        bindings.append({
            "footing": footing["label"],
            "union_source": source_label,
        })
    return {
        "all_footings_bound": True,
        "bindings": bindings,
    }


def _revision_audit_metrics(
    session: feedbackstate.E024Session,
    baseline: receiver.ReceiverSession,
) -> dict:
    reason_counts: dict[str, int] = {}
    detector_rows = []
    pose_rows = []
    fallback_rows = []
    owner_policies: dict[str, int] = {}
    accepted_detector_profiles: dict[str, int] = {}
    actual_pose_deltas = []
    accepted_pose_gates = []
    scans = {scan.scan_id: scan for scan in baseline.scans}
    for revision in session.revisions.values():
        reason = (
            "accepted" if revision.accepted
            else revision.refuse_reason or "refused")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        detector = revision.metrics.get("detector")
        if isinstance(detector, dict):
            detector_rows.append(detector)
        pose = revision.metrics.get("pose")
        if isinstance(pose, dict):
            pose_rows.append(pose)
        fallback = revision.metrics.get("fixed_detector_fallback")
        if isinstance(fallback, dict):
            fallback_rows.append(fallback)
        if revision.emission is not None:
            policy = revision.emission.diagnostics.get(
                "feedback_owner_policy", "missing")
            owner_policies[str(policy)] = (
                owner_policies.get(str(policy), 0) + 1)
            detector_profile = str(revision.emission.detector_profile)
            accepted_detector_profiles[detector_profile] = (
                accepted_detector_profiles.get(detector_profile, 0) + 1)
        placed = scans[revision.scan_id].result.placements[
            revision.placement_ordinal]
        jac0 = placed.pose.matrix()
        relative = revision.pose.matrix() @ np.linalg.inv(jac0)
        phase = np.linalg.solve(
            jac0,
            np.asarray(revision.pose.origin_yx, np.float64)
            - np.asarray(placed.pose.origin_yx, np.float64))
        actual_pose_deltas.append({
            "revision_id": revision.revision_id,
            "accepted": bool(revision.accepted),
            "dtheta_deg": float(np.degrees(np.arctan2(
                relative[0, 1], relative[0, 0]))),
            "du_cells": float(phase[0]),
            "dv_cells": float(phase[1]),
        })
        if (revision.accepted and revision.emission is not None
                and revision.pose != placed.pose):
            generation0 = scans[
                revision.scan_id].window_evidence[
                    revision.placement_ordinal]
            pilot_pos, expected, validation = (
                payloaddec._window_pilot_observations(
                    placed, baseline.decode.spec,
                    baseline.decode.seed))
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
            accepted_pose_gates.append({
                "revision_id": revision.revision_id,
                "n_validation": int(validation.sum()),
                "baseline_mismatch": baseline_mismatch,
                "candidate_mismatch": candidate_mismatch,
                "delta": candidate_mismatch - baseline_mismatch,
                "slack": float(
                    session.envelope.config.pilot_mismatch_slack),
                "passed": bool(
                    candidate_mismatch
                    <= baseline_mismatch
                    + session.envelope.config.pilot_mismatch_slack
                    + 1e-12),
            })

    cert_by_id = {
        row.certificate_id: row
        for row in session.certificates.values()
    }
    depth_cache: dict[str, int] = {}

    def certificate_depth(certificate_id: str) -> int:
        if certificate_id in depth_cache:
            return depth_cache[certificate_id]
        certificate = cert_by_id[certificate_id]
        dependencies = session.dependency_sets[
            certificate.dependency_set_id].certificate_ids
        depth = (
            0 if not dependencies else
            1 + max(certificate_depth(value) for value in dependencies))
        depth_cache[certificate_id] = depth
        return depth

    for certificate_id in cert_by_id:
        certificate_depth(certificate_id)
    dependency_sizes = [
        len(row.certificate_ids)
        for row in session.dependency_sets.values()
    ]

    def finite_deltas(rows: list[dict]) -> list[float]:
        values = []
        for row in rows:
            parent = row.get("parent_validation_logloss")
            candidate = row.get("candidate_validation_logloss")
            if (parent is not None and candidate is not None
                    and np.isfinite(parent) and np.isfinite(candidate)):
                values.append(float(parent) - float(candidate))
        return values

    detector_deltas = finite_deltas(detector_rows)
    pose_deltas = [
        float(row["baseline_validation_logloss"])
        - float(row["candidate_validation_logloss"])
        for row in pose_rows
        if (row.get("baseline_validation_logloss") is not None
            and row.get("candidate_validation_logloss") is not None
            and np.isfinite(row["baseline_validation_logloss"])
            and np.isfinite(row["candidate_validation_logloss"]))
    ]
    return {
        "revision_reason_counts": {
            key: reason_counts[key] for key in sorted(reason_counts)},
        "candidate_error_count": int(
            reason_counts.get("candidate_error", 0)),
        "detector": {
            "evaluated": len(detector_rows),
            "gate_passed": sum(bool(row.get("adopted"))
                               for row in detector_rows),
            "context_candidate_selected": sum(
                bool(row.get("context_adopted"))
                for row in detector_rows),
            "heldout_improvement_sum": float(sum(detector_deltas)),
            "heldout_improvement_max": (
                None if not detector_deltas
                else float(max(detector_deltas))),
            "accepted_profiles": {
                key: accepted_detector_profiles[key]
                for key in sorted(accepted_detector_profiles)},
            "committed_context_revisions": sum(
                bool(revision.emission is not None
                     and revision.emission.diagnostics.get(
                         "feedback_context_adopted"))
                for revision in session.revisions.values()
                if revision.accepted),
            "fixed_detector_fallback_evaluated": len(fallback_rows),
            "fixed_detector_fallback_candidate_selected": sum(
                bool(row.get("adopted")) for row in fallback_rows),
            "support": {
                name: {
                    "min": min(values),
                    "max": max(values),
                }
                for name in (
                    "n_train", "n_validation",
                    "n_payload_train", "n_payload_validation",
                    "n_label_blocks", "n_certificate_tiles")
                if (values := [
                    int(row[name]) for row in detector_rows
                    if row.get(name) is not None])
            },
        },
        "pose": {
            "evaluated": len(pose_rows),
            "candidate_selected": sum(bool(row.get("adopted"))
                                      for row in pose_rows),
            "committed_changed_pose_revisions": len(
                accepted_pose_gates),
            "heldout_improvement_sum": float(sum(pose_deltas)),
            "heldout_improvement_max": (
                None if not pose_deltas else float(max(pose_deltas))),
            "max_abs_angle_deg": max(
                [abs(row["dtheta_deg"])
                 for row in actual_pose_deltas],
                default=0.0),
            "max_abs_phase_cells": max(
                [abs(row[axis])
                 for row in actual_pose_deltas
                 for axis in ("du_cells", "dv_cells")],
                default=0.0),
            "actual_delta_records": actual_pose_deltas,
            "accepted_changed_pose_gate_records": accepted_pose_gates,
            "accepted_changed_pose_gate_violations": sum(
                not row["passed"] for row in accepted_pose_gates),
            "max_e022_pilot_mismatch_delta": (
                None if not accepted_pose_gates else
                max(row["delta"] for row in accepted_pose_gates)),
        },
        "owner_policies": {
            key: owner_policies[key] for key in sorted(owner_policies)},
        "dependencies": {
            "sets": len(session.dependency_sets),
            "max_set_size": max(dependency_sizes, default=0),
            "mean_set_size": (
                0.0 if not dependency_sizes
                else float(np.mean(dependency_sizes))),
            "max_certificate_depth": max(
                depth_cache.values(), default=0),
            "attempts_with_dependencies": sum(
                bool(session.dependency_sets[
                    row.dependency_set_id].certificate_ids)
                for row in session.attempts),
        },
    }


def _generation_metrics(
    session: feedbackstate.E024Session,
    run_report: dict,
    baseline: receiver.ReceiverSession,
) -> dict:
    feedback_generations = session.generations[1:]
    source_reads = []
    changed_cells = []
    for generation in feedback_generations:
        statistics = generation.statistics
        revision = statistics.get("revision", {})
        source_reads.append({
            "generation": int(generation.ordinal),
            "reads": int(revision.get("source_tiff_reads", 0)),
        })
        changed_cells.append({
            "generation": int(generation.ordinal),
            "cells": int(statistics.get("changed_cells", 0)),
        })
    evaluations = []
    for ordinal, row in enumerate(run_report.get("reports", ())):
        revision = row.get("revision", {})
        decode = row.get("decode", {})
        refused = sum(
            int(value) for key, value in revision.items()
            if str(key).startswith("refused:"))
        evaluations.append({
            "evaluation": ordinal,
            "reported_generation": int(row.get(
                "generation", session.head.ordinal)),
            "noop": bool(row.get("noop", False)),
            "reason": row.get("reason"),
            "candidate_windows": int(
                revision.get("candidate_windows", 0)),
            "accepted_revision_decisions": int(
                revision.get("accepted", 0)),
            "refused_revision_decisions": refused,
            "source_tiff_image_reads": int(
                revision.get("source_tiff_reads", 0)),
            "patches": int(row.get("patches", 0)),
            "changed_cells": int(row.get("changed_cells", 0)),
            "crc_calls": int(decode.get("crc_calls", 0)),
            "new_certificates": int(row.get(
                "new_certificates", 0)),
        })
    execution_crc_calls = sum(row["crc_calls"] for row in evaluations)
    if execution_crc_calls != session.crc_calls:
        raise ValueError(
            "E024 run report CRC accounting differs from the state ledger")
    last_reason = (
        None if not evaluations else evaluations[-1]["reason"])
    terminal_reasons = {
        "no_reachable_windows", "no_new_certificates",
        "no_reachable_windows_after_certificates"}
    frontier_exhausted = (
        (
            session.envelope.profile
            == feedbackstate.PROFILE_CONTROL
            and bool(session.head.fixed_point)
            and last_reason == "control_profile"
        )
        or (
            session.envelope.profile
            != feedbackstate.PROFILE_CONTROL
            and bool(session.head.fixed_point)
            and last_reason in terminal_reasons
        )
    )
    return {
        "generation_evaluations": len(evaluations),
        "generation_evaluation_details": evaluations,
        "generation_zero_plus_feedback": len(session.generations),
        "feedback_generations": len(feedback_generations),
        "head_ordinal": int(session.head.ordinal),
        "fixed_point": bool(session.head.fixed_point),
        "frontier_exhausted": frontier_exhausted,
        "terminal_reason": last_reason,
        "committed_accepted_revisions": sum(
            len(row.accepted_revision_ids)
            for row in feedback_generations),
        "committed_refused_revisions": sum(
            len(row.refused_revision_ids)
            for row in feedback_generations),
        "accepted_revision_decisions": sum(
            row["accepted_revision_decisions"] for row in evaluations),
        "refused_revision_decisions": sum(
            row["refused_revision_decisions"] for row in evaluations),
        "candidate_windows_evaluated": sum(
            row["candidate_windows"] for row in evaluations),
        "revision_records": len(session.revisions),
        "patches": len(session.patches),
        "changed_cells": sum(
            int(np.asarray(row.payload_indices).size)
            for row in session.patches.values()),
        "owner_changes": sum(
            int(np.sum(
                np.asarray(row.previous_owner)
                != np.asarray(row.new_owner)))
            for row in session.patches.values()),
        "attempt_records": len(session.attempts),
        "crc_calls": int(session.crc_calls),
        "bp_iterations": sum(
            int(row.n_iters) for row in session.attempts),
        "crc_false_accept_budget": (
            int(session.crc_calls) * payloaddec.CRC_FALSE_ACCEPT),
        "source_tiff_image_reads": sum(
            row["source_tiff_image_reads"] for row in evaluations),
        "committed_source_tiff_image_reads_by_generation": source_reads,
        "committed_changed_cells_by_generation": changed_cells,
        "new_certificates_by_generation": {
            str(generation): sum(
                row.born_generation == generation
                for row in session.certificates.values())
            for generation in sorted({
                row.born_generation
                for row in session.certificates.values()
                if row.born_generation > 0
            })
        },
        "revision_audit": _revision_audit_metrics(session, baseline),
    }


@dataclass
class ProfileCompact:
    report: dict
    certs: dict[tuple[int, int, int], tuple[int, bytes]]
    generation_zero_certs: dict[
        tuple[int, int, int], tuple[int, bytes]]


@dataclass
class FootingCompact:
    report: dict
    baseline_certs: dict[tuple[int, int, int], tuple[int, bytes]]
    profiles: dict[str, ProfileCompact]
    format_id: str
    rate_id: str
    compatibility: dict


def _run_profile(
    profile: str,
    baseline_path: Path,
    baseline: receiver.ReceiverSession,
    *,
    certificate_union: Path | None,
    max_generations: int | None,
    implementation_fingerprints: tuple[tuple[str, str], ...],
) -> ProfileCompact:
    if feedbackstate.implementation_fingerprints() != (
            implementation_fingerprints):
        raise ValueError(
            "E024 implementation changed before a profile run")
    total_start = time.perf_counter()
    create_start = time.perf_counter()
    generation_zero = feedback.create_session(
        baseline_path, baseline, profile=profile,
        certificate_union=certificate_union)
    create_seconds = time.perf_counter() - create_start
    generation_zero_certs = _e024_certificates(generation_zero)

    feedback_start = time.perf_counter()
    result, run_report = feedback.run_feedback(
        generation_zero, baseline, baseline_path=baseline_path,
        max_generations=max_generations)
    feedback_seconds = time.perf_counter() - feedback_start
    if (result.envelope.implementation_sha256
            != implementation_fingerprints
            or feedbackstate.implementation_fingerprints()
            != implementation_fingerprints):
        raise ValueError(
            "E024 implementation changed during a profile run")
    feedbackstate.validate_session(
        result, baseline, baseline_path=baseline_path,
        validate_baseline=False)
    certs = _e024_certificates(result)
    generation_zero_effect = _effect(generation_zero_certs, certs)
    source_counts: dict[str, int] = {}
    for certificate in result.certificates.values():
        source_counts[certificate.source] = (
            source_counts.get(certificate.source, 0) + 1)
    state_transitions: dict[str, int] = {}
    for key, before in generation_zero.tiles.items():
        after = result.tiles[key]
        transition = f"{before.state}->{after.state}"
        state_transitions[transition] = (
            state_transitions.get(transition, 0) + 1)
    new_by_initial_state: dict[str, int] = {}
    for key, certificate in result.certificates.items():
        if certificate.born_generation <= 0:
            continue
        state = generation_zero.tiles[key].state
        new_by_initial_state[state] = (
            new_by_initial_state.get(state, 0) + 1)
    report = {
        "profile": profile,
        "authoritative_sha256": feedbackstate.authoritative_digest(result),
        "config_sha256": result.envelope.config_sha256,
        "config": result.envelope.config.__dict__,
        "implementation_sha256": _implementation_digest(
            result.envelope.implementation_sha256),
        "certificate_seed_sha256": (
            result.envelope.certificate_seed_sha256),
        "runtime_seconds": {
            "create": create_seconds,
            "feedback": feedback_seconds,
            "total": time.perf_counter() - total_start,
        },
        "state_summary": result.summary(),
        "generation_zero_state_summary": generation_zero.summary(),
        "tile_state_transitions": {
            key: state_transitions[key]
            for key in sorted(state_transitions)},
        "run": run_report,
        "accounting": _generation_metrics(
            result, run_report, baseline),
        "durable_state_replay_validated": True,
        "certificate_sources": {
            key: source_counts[key] for key in sorted(source_counts)},
        "generation_zero_certificates": _certificate_summary(
            generation_zero_certs),
        "certificates": _certificate_summary(certs),
        "change_from_generation_zero": generation_zero_effect,
        "feedback_new_tiles": [
            list(key) for key, row in sorted(result.certificates.items())
            if row.born_generation > 0],
        "feedback_new_tiles_by_generation_zero_state": {
            key: new_by_initial_state[key]
            for key in sorted(new_by_initial_state)},
        "external_seed_tiles": [
            list(key) for key, row in sorted(result.certificates.items())
            if row.source == "certificate-union"],
    }
    return ProfileCompact(
        report=report, certs=certs,
        generation_zero_certs=generation_zero_certs)


def _run_blind_footing(
    label: str,
    path: Path,
    *,
    certificate_union: Path | None,
    max_generations: int | None,
    implementation_fingerprints: tuple[tuple[str, str], ...],
) -> FootingCompact:
    print(f"\n=== {label}: current-schema E023b -> E024 2x2 ===",
          flush=True)
    state_sha256, state_size = _stream_sha256(path)
    load_start = time.perf_counter()
    baseline = receiver.load_session(path)
    load_seconds = time.perf_counter() - load_start
    if baseline.decode.fatal:
        raise ValueError(
            f"{label}: E023b footing carries fatal integrity records")
    if tuple(baseline.envelope.pages) != (0,):
        raise ValueError(
            f"{label}: frozen E018 GT qualification is page-0-only")
    descriptor = _descriptor(baseline.envelope.format_id)
    if tuple(descriptor.spec().page_cells_yx) != tuple(
            baseline.envelope.page_cells_yx):
        raise ValueError(f"{label}: descriptor/state geometry mismatch")
    baseline_certs = _e023b_certificates(baseline)
    baseline_authoritative = receiver.authoritative_digest(baseline)
    compatibility = _footing_compatibility(baseline)
    report = {
        "reference": {
            "path": str(path),
            "file_sha256": state_sha256,
            "file_size": state_size,
            "authoritative_sha256": baseline_authoritative,
            "algorithm_id": baseline.envelope.algorithm_id,
            "format_id": baseline.envelope.format_id,
            "rate_id": baseline.envelope.rate_id,
            "pages": list(baseline.envelope.pages),
            "dpi": baseline.envelope.dpi,
            "cell_dots": baseline.envelope.cell_dots,
            "detector_profile": baseline.envelope.detector_profile,
            "scan_count": len(baseline.scans),
            "capture_ids": [
                scan.capture_id for scan in baseline.scans],
            "load_seconds": load_seconds,
            "comparison_identity": compatibility,
        },
        "e023b_certificates": _certificate_summary(baseline_certs),
        "e023b_summary": baseline.summary(),
        "e023b_attempt_records": len(baseline.attempts),
        "e023b_crc_calls": sum(
            int(row.decoder_invoked) for row in baseline.attempts),
        "profiles": {},
    }
    profiles = {}
    for profile in PROFILE_ORDER:
        if receiver.authoritative_digest(baseline) != baseline_authoritative:
            raise ValueError(
                f"{label}: in-memory E023b footing changed before "
                f"profile {profile}")
        print(f"  {profile}", flush=True)
        compact = _run_profile(
            profile, path, baseline,
            certificate_union=certificate_union,
            max_generations=max_generations,
            implementation_fingerprints=implementation_fingerprints)
        profiles[profile] = compact
        report["profiles"][profile] = compact.report
        if receiver.authoritative_digest(baseline) != baseline_authoritative:
            raise ValueError(
                f"{label}: E024 profile {profile} mutated the in-memory "
                "E023b footing")
        metrics = compact.report["accounting"]
        print(
            f"    cert={len(compact.certs)} "
            f"gen={metrics['feedback_generations']} "
            f"rev={metrics['accepted_revision_decisions']}/"
            f"{metrics['refused_revision_decisions']} "
            f"patch={metrics['patches']} "
            f"calls={metrics['crc_calls']} "
            f"tiff={metrics['source_tiff_image_reads']} "
            f"runtime={compact.report['runtime_seconds']['total']:.2f}s",
            flush=True)
        gc.collect()
    final_sha256, final_size = _stream_sha256(path)
    if (final_sha256, final_size) != (state_sha256, state_size):
        raise ValueError(
            f"{label}: E023b state changed during blind qualification")
    return FootingCompact(
        report=report, baseline_certs=baseline_certs,
        profiles=profiles, format_id=baseline.envelope.format_id,
        rate_id=baseline.envelope.rate_id,
        compatibility=compatibility)


def _factorial(profiles: dict[str, ProfileCompact]) -> dict:
    control = profiles[feedbackstate.PROFILE_CONTROL].certs
    recal = profiles[feedbackstate.PROFILE_RECAL].certs
    refine = profiles[feedbackstate.PROFILE_REFINE].certs
    combined = profiles[feedbackstate.PROFILE_COMBINED].certs
    recal_gain = set(recal) - set(control)
    refine_gain = set(refine) - set(control)
    combined_gain = set(combined) - set(control)
    independent = recal_gain | refine_gain
    return {
        "factors": {
            "recalibration": ["off", "on"],
            "pose_refinement": ["off", "on"],
        },
        "cells": {
            "control": {
                "recalibration": "off", "pose_refinement": "off"},
            "recal": {
                "recalibration": "on", "pose_refinement": "off"},
            "refine": {
                "recalibration": "off", "pose_refinement": "on"},
            "combined": {
                "recalibration": "on", "pose_refinement": "on"},
        },
        "effects": {
            "recalibration_without_pose": _effect(control, recal),
            "pose_without_recalibration": _effect(control, refine),
            "recalibration_with_pose": _effect(refine, combined),
            "pose_with_recalibration": _effect(recal, combined),
            "combined_from_control": _effect(control, combined),
        },
        "independent_gain_overlap": [
            list(key) for key in sorted(recal_gain & refine_gain)],
        "recalibration_only_independent_gain": [
            list(key) for key in sorted(recal_gain - refine_gain)],
        "refinement_only_independent_gain": [
            list(key) for key in sorted(refine_gain - recal_gain)],
        "independent_gain_union": [
            list(key) for key in sorted(independent)],
        "combined_only_synergy": [
            list(key) for key in sorted(combined_gain - independent)],
        "independent_gains_absent_from_combined": [
            list(key) for key in sorted(independent - combined_gain)],
        "yield_interaction_difference_in_differences": (
            (len(combined) - len(refine))
            - (len(recal) - len(control))),
        "changed_certificate_pairs": {
            "control_to_recal": [
                list(key) for key in sorted(
                    _changed_certificates(control, recal))],
            "control_to_refine": [
                list(key) for key in sorted(
                    _changed_certificates(control, refine))],
            "recal_to_combined": [
                list(key) for key in sorted(
                    _changed_certificates(recal, combined))],
            "refine_to_combined": [
                list(key) for key in sorted(
                    _changed_certificates(refine, combined))],
        },
    }


def _certificate_portfolio(named: dict[str, dict]) -> dict:
    labels = list(named)
    all_keys = sorted({
        key for rows in named.values() for key in rows})
    conflicts = [
        key for key in all_keys
        if len({
            named[label][key] for label in labels
            if key in named[label]}) > 1]
    merged = {}
    if not conflicts:
        for key in all_keys:
            merged[key] = next(
                named[label][key] for label in labels
                if key in named[label])
    support = {
        key: [label for label in labels if key in named[label]]
        for key in all_keys}
    pairwise = []
    for left_index, left in enumerate(labels):
        left_keys = set(named[left])
        for right in labels[left_index + 1:]:
            right_keys = set(named[right])
            pairwise.append({
                "left": left,
                "right": right,
                "intersection": len(left_keys & right_keys),
                "left_only": len(left_keys - right_keys),
                "right_only": len(right_keys - left_keys),
                "union": len(left_keys | right_keys),
                "changed_values": len(_changed_certificates(
                    named[left], named[right])),
            })
    return {
        "labels": labels,
        "conflict_free": not conflicts,
        "conflicts": [list(key) for key in conflicts],
        "conflict_count": len(conflicts),
        "union": (
            None if conflicts else _certificate_summary(merged)),
        "intersection_count": sum(
            len(value) == len(labels) for value in support.values()),
        "exclusive_count": sum(
            len(value) == 1 for value in support.values()),
        "exclusive_by_label": {
            label: [
                list(key) for key in all_keys
                if support[key] == [label]]
            for label in labels
        },
        "support_histogram": {
            str(count): sum(
                len(value) == count for value in support.values())
            for count in range(1, len(labels) + 1)
        },
        "pairwise": pairwise,
    }


def _cross_footing_portfolios(
    footings: dict[str, FootingCompact],
) -> dict:
    baseline = _certificate_portfolio({
        label: row.baseline_certs
        for label, row in footings.items()})
    profiles = {}
    for profile in PROFILE_ORDER:
        final = {
            label: row.profiles[profile].certs
            for label, row in footings.items()}
        generation_zero = {
            label: row.profiles[profile].generation_zero_certs
            for label, row in footings.items()}
        feedback_new = {
            label: {
                key: value for key, value in final[label].items()
                if key not in generation_zero[label]}
            for label in footings
        }
        final_portfolio = _certificate_portfolio(final)
        generation_zero_portfolio = _certificate_portfolio(
            generation_zero)
        feedback_portfolio = _certificate_portfolio(feedback_new)
        final_union_count = (
            None if final_portfolio["union"] is None
            else final_portfolio["union"]["count"])
        generation_zero_union_count = (
            None if generation_zero_portfolio["union"] is None
            else generation_zero_portfolio["union"]["count"])
        baseline_union_count = (
            None if baseline["union"] is None
            else baseline["union"]["count"])
        profiles[profile] = {
            "generation_zero": generation_zero_portfolio,
            "feedback_new": feedback_portfolio,
            "final": final_portfolio,
            "final_union_gain_vs_e023b_union": (
                None if (final_union_count is None
                         or baseline_union_count is None)
                else final_union_count - baseline_union_count),
            "final_union_gain_vs_generation_zero_union": (
                None if (final_union_count is None
                         or generation_zero_union_count is None)
                else final_union_count - generation_zero_union_count),
        }
    conflict_free = (
        baseline["conflict_free"]
        and all(
            row["generation_zero"]["conflict_free"]
            and row["feedback_new"]["conflict_free"]
            and row["final"]["conflict_free"]
            for row in profiles.values()))
    return {
        "e023b_generation_zero": baseline,
        "profiles": profiles,
        "all_certificate_values_conflict_free": conflict_free,
    }


def _attach_ground_truth(
    footing: FootingCompact,
    descriptor,
    gt_bits: np.ndarray,
) -> None:
    baseline_wrong = e023b_qual._wrong_certificates(
        footing.baseline_certs, descriptor, gt_bits, footing.rate_id)
    footing.report["e023b_certificates"].update({
        "wrong": [list(key) for key in baseline_wrong],
        "wrong_count": len(baseline_wrong),
    })
    control = footing.profiles[feedbackstate.PROFILE_CONTROL].certs
    for profile in PROFILE_ORDER:
        compact = footing.profiles[profile]
        current = compact.certs
        wrong = e023b_qual._wrong_certificates(
            current, descriptor, gt_bits, footing.rate_id)
        new_control = set(current) - set(control)
        lost_control = set(control) - set(current)
        changed_control = _changed_certificates(control, current)
        new_e023b = set(current) - set(footing.baseline_certs)
        lost_e023b = set(footing.baseline_certs) - set(current)
        changed_e023b = _changed_certificates(
            footing.baseline_certs, current)
        compact.report["certificates"].update({
            "wrong": [list(key) for key in wrong],
            "wrong_count": len(wrong),
            "new_from_control": [
                list(key) for key in sorted(new_control)],
            "new_from_control_count": len(new_control),
            "lost_from_control": [
                list(key) for key in sorted(lost_control)],
            "lost_from_control_count": len(lost_control),
            "changed_from_control": [
                list(key) for key in sorted(changed_control)],
            "changed_from_control_count": len(changed_control),
            "new_from_e023b": [
                list(key) for key in sorted(new_e023b)],
            "new_from_e023b_count": len(new_e023b),
            "lost_from_e023b": [
                list(key) for key in sorted(lost_e023b)],
            "lost_from_e023b_count": len(lost_e023b),
            "changed_from_e023b": [
                list(key) for key in sorted(changed_e023b)],
            "changed_from_e023b_count": len(changed_e023b),
        })
    footing.report["factorial"] = _factorial(footing.profiles)

    control_report = footing.profiles[
        feedbackstate.PROFILE_CONTROL].report
    control_accounting = control_report["accounting"]
    safety_gates = {
        "current_schema_e023b_loaded": True,
        "e023b_fatal_ledger_empty": True,
        "e023b_certificates_gt_correct": not baseline_wrong,
        "control_exact_noop": (
            bool(control_report["run"]["noop"])
            and control_accounting["head_ordinal"] == 0
            and control_accounting["revision_records"] == 0
            and control_accounting["patches"] == 0
            and control_accounting["attempt_records"] == 0),
        "no_control_loss_from_e023b": not (
            set(footing.baseline_certs) - set(control)),
        "no_control_value_change_from_e023b": not _changed_certificates(
            footing.baseline_certs, control),
        "all_profile_certificates_gt_correct": all(
            not footing.profiles[name].report[
                "certificates"]["wrong"]
            for name in PROFILE_ORDER),
        "all_profiles_exhausted_feedback_frontier": all(
            footing.profiles[name].report[
                "accounting"]["frontier_exhausted"]
            for name in PROFILE_ORDER),
        "no_profile_certificate_lost_from_control": all(
            not (set(control) - set(footing.profiles[name].certs))
            for name in PROFILE_ORDER),
        "no_control_certificate_value_changed": all(
            not _changed_certificates(
                control, footing.profiles[name].certs)
            for name in PROFILE_ORDER),
    }
    execution_gates = {
        "all_profiles_pass_durable_state_replay": all(
            footing.profiles[name].report[
                "durable_state_replay_validated"] is True
            for name in PROFILE_ORDER),
        "all_accepted_revisions_pass_replayed_heldout_gates": all(
            footing.profiles[name].report[
                "durable_state_replay_validated"] is True
            for name in PROFILE_ORDER),
        "fixed_detector_arms_replay_generation_zero_exactly": all(
            footing.profiles[name].report[
                "durable_state_replay_validated"] is True
            for name in (
                feedbackstate.PROFILE_REFINE,
                feedbackstate.PROFILE_COMBINED)),
        "all_profiles_candidate_error_free": all(
            footing.profiles[name].report["accounting"][
                "revision_audit"]["candidate_error_count"] == 0
            for name in PROFILE_ORDER),
        "pose_arms_read_sources_when_they_have_candidates": all(
            (
                footing.profiles[name].report["accounting"][
                    "candidate_windows_evaluated"] == 0
                or footing.profiles[name].report["accounting"][
                    "source_tiff_image_reads"] > 0
            )
            for name in (
                feedbackstate.PROFILE_REFINE,
                feedbackstate.PROFILE_COMBINED)),
        "accepted_feedback_uses_comparable_owner_rank": all(
            set(footing.profiles[name].report["accounting"][
                "revision_audit"]["owner_policies"])
            <= {"fixed-pilot-validation-v1"}
            for name in PROFILE_ORDER),
        "pose_search_stayed_inside_registered_bounds": all(
            (
                footing.profiles[name].report["accounting"][
                    "revision_audit"]["pose"]["max_abs_angle_deg"]
                <= footing.profiles[name].report["config"][
                    "pose_angle_deg"] + 1e-12
                and footing.profiles[name].report["accounting"][
                    "revision_audit"]["pose"]["max_abs_phase_cells"]
                <= footing.profiles[name].report["config"][
                    "pose_phase_cells"] + 1e-12
            )
            for name in PROFILE_ORDER),
        "accepted_changed_poses_pass_e022_pilot_gate": all(
            footing.profiles[name].report["accounting"][
                "revision_audit"]["pose"][
                    "accepted_changed_pose_gate_violations"] == 0
            for name in PROFILE_ORDER),
    }
    efficacy = {
        name: {
            "certificate_gain_vs_control": (
                len(footing.profiles[name].certs) - len(control)),
            "accepted_revisions": footing.profiles[name].report[
                "accounting"]["committed_accepted_revisions"],
            "changed_cells": footing.profiles[name].report[
                "accounting"]["changed_cells"],
            "crc_calls": footing.profiles[name].report[
                "accounting"]["crc_calls"],
            "applicable": footing.profiles[name].report["accounting"][
                "candidate_windows_evaluated"] > 0,
            "operative": (
                footing.profiles[name].report["accounting"][
                    "committed_accepted_revisions"] > 0
                and footing.profiles[name].report["accounting"][
                    "changed_cells"] > 0
            ),
            "yield_positive": (
                len(footing.profiles[name].certs) > len(control)),
        }
        for name in PROFILE_ORDER
    }
    footing.report["safety_gates"] = safety_gates
    footing.report["execution_gates"] = execution_gates
    footing.report["efficacy"] = efficacy
    footing.report["numerical_gates"] = {
        **safety_gates, **execution_gates}
    footing.report["numerical_gates_ok"] = all(
        value is True
        for value in footing.report["numerical_gates"].values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", action="append", required=True, metavar="LABEL=PATH",
        help="current-schema E023b state; repeat for multiple footings")
    parser.add_argument(
        "--certificate-union", type=Path, default=None,
        help="optional conflict-checked E023b merge bundle for generation zero")
    parser.add_argument(
        "--max-generations", type=int, default=None,
        help="feedback generation limit; default is the registered E024 limit")
    parser.add_argument(
        "--out", type=Path,
        default=BUILD / "qualify_e024_report.json")
    args = parser.parse_args()

    try:
        baselines = _parse_baselines(args.baseline)
    except ValueError as exc:
        parser.error(str(exc))
    if args.max_generations is not None and args.max_generations < 0:
        parser.error("--max-generations must be non-negative")
    certificate_union = (
        None if args.certificate_union is None else
        args.certificate_union.expanduser().resolve())
    union_reference = None
    union_proof = None
    if certificate_union is not None:
        try:
            union_sha256, union_size = _stream_sha256(certificate_union)
            union_proof = feedback.validate_certificate_union(
                certificate_union)
        except OSError as exc:
            parser.error(str(exc))
        except ValueError as exc:
            parser.error(str(exc))
        if (union_proof["sha256"], union_proof["size"]) != (
                union_sha256, union_size):
            parser.error(
                "certificate union changed during trust-root replay")
        union_reference = {
            "path": str(certificate_union),
            "sha256": union_sha256,
            "size": union_size,
            "source_count": union_proof["source_count"],
            "certificate_count": union_proof["certificate_count"],
            "source_replay_validated": True,
            "sources": union_proof["sources"],
        }
    try:
        preflight = _preflight_baselines(baselines)
    except (
            OSError, ValueError, TypeError, AttributeError,
            pickle.UnpicklingError, EOFError) as exc:
        parser.error(str(exc))
    union_footing_bindings = None
    if union_proof is not None:
        try:
            union_footing_bindings = _validate_union_footing_bindings(
                union_proof, preflight)
        except ValueError as exc:
            parser.error(str(exc))

    harness_sha256, _ = _stream_sha256(Path(__file__).resolve())
    helper_sha256, _ = _stream_sha256(
        Path(e023b_qual.__file__).resolve())
    implementation_fingerprints = (
        feedbackstate.implementation_fingerprints())
    report = {
        "experiment": "024-feedback-receiver",
        "algorithm_id": feedbackstate.ALGORITHM_ID,
        "boundary": "LDPC and below; no fountain/rank/stop condition",
        "profiles": list(PROFILE_ORDER),
        "factorial": {
            "recalibration": ["off", "on"],
            "pose_refinement": ["off", "on"],
        },
        "certificate_union": union_reference,
        "certificate_union_footing_bindings": (
            union_footing_bindings),
        "preflight": preflight,
        "max_generations": args.max_generations,
        "blind_ground_truth_policy": {
            "ground_truth_opened": False,
            "all_profile_outputs_compacted_first": False,
            "compact_blind_output": (
                "certificate tile keys, packed certificate bits, and "
                "non-GT accounting only"),
            "ground_truth_use": "post-hoc certificate correctness only",
        },
        "implementation": {
            "qualification_harness_sha256": harness_sha256,
            "e023b_gt_helper_path": str(
                Path(e023b_qual.__file__).resolve()),
            "e023b_gt_helper_sha256": helper_sha256,
            "feedback_sha256": _stream_sha256(
                Path(feedback.__file__).resolve())[0],
            "feedbackstate_sha256": _stream_sha256(
                Path(feedbackstate.__file__).resolve())[0],
            "production_entrypoint_sha256": _stream_sha256(
                HERE / "run_e024.py")[0],
            "authoritative_fingerprint_sha256": (
                _implementation_digest(implementation_fingerprints)),
            "authoritative_fingerprint_rows": len(
                implementation_fingerprints),
        },
        "baselines": {},
    }

    qualification_start = time.perf_counter()
    compact: dict[str, FootingCompact] = {}
    try:
        # Blind phase.  Do not call the imported GT loader anywhere above
        # this barrier.
        for label, path in baselines:
            compact[label] = _run_blind_footing(
                label, path, certificate_union=certificate_union,
                max_generations=args.max_generations,
                implementation_fingerprints=implementation_fingerprints)
            report["baselines"][label] = compact[label].report
            gc.collect()

        if feedbackstate.implementation_fingerprints() != (
                implementation_fingerprints):
            raise ValueError(
                "E024 implementation changed across profile runs")
        if _stream_sha256(Path(__file__).resolve())[0] != harness_sha256:
            raise ValueError(
                "E024 qualification harness changed during blind runs")
        if _stream_sha256(Path(e023b_qual.__file__).resolve())[0] != (
                helper_sha256):
            raise ValueError(
                "E023b ground-truth helper changed during blind runs")
        if certificate_union is not None:
            union_final = _stream_sha256(certificate_union)
            if union_final != (union_reference["sha256"],
                               union_reference["size"]):
                raise ValueError(
                    "certificate union changed during blind qualification")
        report["cross_footing_compatibility"] = (
            _validate_footing_compatibility([
                (label, row.compatibility)
                for label, row in compact.items()]))
        report["cross_footing_portfolios"] = (
            _cross_footing_portfolios(compact))
        if not report["cross_footing_portfolios"][
                "all_certificate_values_conflict_free"]:
            raise ValueError(
                "E024 cross-footing certificate portfolio conflicts")
        format_ids = {row.format_id for row in compact.values()}
        report["blind_ground_truth_policy"][
            "all_profile_outputs_compacted_first"] = True
        blind_seconds = time.perf_counter() - qualification_start
        print(
            "\nAll blind profile outputs are compact; opening frozen E018 "
            "ground truth.", flush=True)

        descriptor = _descriptor(next(iter(format_ids)))
        gt_start = time.perf_counter()
        _field, gt_bits, _neighbors, gt_reference = (
            e023b_qual._load_ground_truth(descriptor))
        report["blind_ground_truth_policy"]["ground_truth_opened"] = True
        report["ground_truth"] = {
            **gt_reference,
            "helper_path": str(Path(e023b_qual.__file__).resolve()),
            "helper_sha256": helper_sha256,
        }
        for label, footing in compact.items():
            _attach_ground_truth(footing, descriptor, gt_bits)
            report["baselines"][label] = footing.report
            status = (
                "PASS" if footing.report["numerical_gates_ok"] else "FAIL")
            counts = {
                name: len(footing.profiles[name].certs)
                for name in PROFILE_ORDER}
            print(
                f"  {label}: control={counts['control']} "
                f"recal={counts['recal']} refine={counts['refine']} "
                f"combined={counts['combined']} {status}",
                flush=True)

        report["runtime_seconds"] = {
            "blind_profiles": blind_seconds,
            "ground_truth_evaluation": time.perf_counter() - gt_start,
            "total": time.perf_counter() - qualification_start,
        }
        report["cross_footing_numerical_gates"] = {
            "compatible_receiver_and_capture_identity": (
                report["cross_footing_compatibility"][
                    "compatible"] is True),
            "certificate_values_conflict_free": (
                report["cross_footing_portfolios"][
                    "all_certificate_values_conflict_free"] is True),
        }
        report["numerical_gates_ok"] = (
            all(
                row.report["numerical_gates_ok"]
                for row in compact.values())
            and all(
                value is True for value in report[
                    "cross_footing_numerical_gates"].values()))
        report["status"] = (
            "numerical_pass"
            if report["numerical_gates_ok"] else "numerical_fail")
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["runtime_seconds"] = {
            "total": time.perf_counter() - qualification_start}
        report["numerical_gates_ok"] = False
        report["status"] = "numerical_fail"
        _write_report(args.out, report)
        print(
            f"\nE024 NUMERICAL FAIL: {report['error']} -> {args.out}",
            file=sys.stderr)
        return 1

    _write_report(args.out, report)
    print(
        f"\nE024 NUMERICAL "
        f"{'PASS' if report['numerical_gates_ok'] else 'FAIL'} "
        f"-> {args.out}")
    return 0 if report["numerical_gates_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

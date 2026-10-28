#!/usr/bin/env python
"""Qualify one completed E023c cascade state against frozen truth/baseline.

The receiver itself remains blind.  This observer loads ground truth only
after the persistent state and every lane certificate already exist.  It
audits every certificate, compares the scale list and an optional historical
E023b baseline, reruns the real fountain+SHA completion check, and writes a
compact deterministic report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import cascade  # noqa: E402
import cascade_state  # noqa: E402
import completion  # noqa: E402
import run_e023c  # noqa: E402
from paperholo import compose, payloaddec, receiver  # noqa: E402
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402


MAGIC = "e023c-cascade-qualification-v1"
VERSION = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _descriptor(format_id: str):
    return next(row for row in FORMAT_REGISTRY if row.format_id == format_id)


def _qualification_scope(session, manifest) -> str:
    """Describe only the capture/format facts carried by the inputs."""
    return (
        f"single {session.envelope.native_dpi:g}-dpi physical capture for "
        f"profile {manifest.profile} / format {session.envelope.format_id}; "
        "architectural and numerical qualification, not cross-scanner "
        "generalization"
    )


def _cert_digest(certs: dict) -> tuple[str, str]:
    set_digest = hashlib.sha256()
    bit_digest = hashlib.sha256()
    for key, bits in sorted(certs.items()):
        token = repr(tuple(key)).encode("ascii")
        packed = np.packbits(np.asarray(bits, np.uint8), bitorder="big").tobytes()
        set_digest.update(len(token).to_bytes(4, "big") + token)
        bit_digest.update(len(token).to_bytes(4, "big") + token)
        bit_digest.update(len(packed).to_bytes(8, "big") + packed)
    return set_digest.hexdigest(), bit_digest.hexdigest()


def _lane_certificates(lane) -> dict:
    return {
        tuple(key): np.asarray(out.user_bits, np.uint8).copy()
        for key, out in lane.decode.tiles.items()
        if out.state == "certified"
    }


def _load_historical_e023b(path: Path):
    """Load a local comparator while recording, not waiving, code drift."""
    raw = path.read_bytes()
    payload = pickle.loads(raw)
    if (not isinstance(payload, dict)
            or payload.get("magic") != receiver.STATE_MAGIC
            or int(payload.get("version", -1)) != receiver.STATE_VERSION):
        raise ValueError(f"{path} is not an E023b state")
    session = payload.get("session")
    if not isinstance(session, receiver.ReceiverSession):
        raise ValueError("historical E023b payload has the wrong type")
    session.validate_invariants()
    return session, {
        "path": str(path.resolve()), "file_sha256": hashlib.sha256(raw).hexdigest(),
        "file_size": len(raw),
        "implementation_matches_current": (
            session.envelope.implementation_sha256
            == receiver.implementation_fingerprints()),
        "authoritative_sha256": receiver.authoritative_digest(session),
    }


def _ground_truth_bits(path: Path, expected_sha: str, descriptor):
    actual = _sha256(path)
    if actual != expected_sha:
        raise ValueError(f"ground truth SHA mismatch: {actual} != {expected_sha}")
    dots = np.load(path)
    spec = descriptor.spec()
    field = dots[::spec.cell_dots, ::spec.cell_dots].astype(np.uint8)
    if field.shape != tuple(spec.page_cells_yx):
        raise ValueError("ground truth geometry differs from format")
    pim = compose.payload_index_map(spec, descriptor.seed)
    cells = np.argwhere(pim >= 0)
    order = np.argsort(pim[cells[:, 0], cells[:, 1]], kind="stable")
    cells = cells[order]
    keystream = compose.payload_keystream(spec, descriptor.seed, 0)
    bits = (field[cells[:, 0], cells[:, 1]]
            ^ keystream[cells[:, 0], cells[:, 1]]).astype(np.uint8)
    return bits, {"path": str(path.resolve()), "sha256": actual}


def _wrong(certs: dict, descriptor, rate_id: str, gt_bits: np.ndarray):
    decode = payloaddec.DecodeState(descriptor, rate_id, (0,), ())
    wrong = []
    for key, bits in sorted(certs.items()):
        if key[0] != 0:
            raise ValueError("the frozen E018 ground truth is page-0-only")
        out = payloaddec.TileOutcome(
            page=key[0], tile_yx=key[1:], state="certified",
            user_bits=np.asarray(bits, np.uint8))
        indices, transmitted = decode.certified_payload_indices(out)
        if not np.array_equal(transmitted, gt_bits[indices]):
            wrong.append(key)
    return wrong


def _compare(left: dict, right: dict) -> dict:
    common = set(left) & set(right)
    conflicts = sorted(
        key for key in common if not np.array_equal(left[key], right[key]))
    return {
        "left": len(left), "right": len(right),
        "intersection": len(common),
        "left_only": [list(key) for key in sorted(set(left) - set(right))],
        "right_only": [list(key) for key in sorted(set(right) - set(left))],
        "conflicts": [list(key) for key in conflicts],
    }


def _write(path: Path, payload: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--control-state", type=Path, default=None,
                        help="optional current-code two-level schedule control")
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--ground-truth-sha256", required=True)
    parser.add_argument("--diag", type=Path, default=None)
    parser.add_argument("--label", default="e023c-cascade")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    state_sha = _sha256(args.state)
    session = cascade_state.load_session(args.state)
    stored_implementation = dict(session.envelope.implementation_sha256)
    current_implementation = dict(run_e023c.implementation_fingerprints())
    registered_policy = stored_implementation.pop("run_policy", None)
    implementation_matches = stored_implementation == current_implementation
    policy_registered = registered_policy is not None
    descriptor = _descriptor(session.envelope.format_id)
    manifest = completion.load_manifest(args.manifest)
    if session.envelope.manifest_sha256 != manifest.file_sha256:
        raise ValueError(
            "qualification manifest is not the manifest registered in state")
    if (
        manifest.descriptor.format_id != descriptor.format_id
        or manifest.descriptor.seed != descriptor.seed
        or manifest.descriptor.spec() != descriptor.spec()
        or manifest.descriptor.ldpc_rate != session.envelope.rate_id
    ):
        raise ValueError("qualification manifest differs from state format")
    gt_bits, gt_reference = _ground_truth_bits(
        args.ground_truth, args.ground_truth_sha256, descriptor)

    lanes = {}
    lane_certs = {}
    for lane_id, meta in sorted(session.decoder_lanes.items(),
                                key=lambda item: item[1].level_id):
        lane = session.lane_sessions[lane_id]
        certs = _lane_certificates(lane)
        lane_certs[meta.level_id] = certs
        methods = Counter(
            placed.method for scan in lane.scans
            for placed in scan.result.placements)
        before_retry = sum(
            row.certified_new and row.stage != "retry150"
            for row in lane.attempts)
        retry_gain = sum(
            row.certified_new and row.stage == "retry150"
            for row in lane.attempts)
        set_sha, bits_sha = _cert_digest(certs)
        level = next(
            level for capture in session.captures for level in capture.levels
            if level.level_id == meta.level_id)
        lanes[meta.level_id] = {
            "lane_id": lane_id,
            "ppc": next(row.target_ppc for row in session.envelope.scale_plan
                        if row.level_id == meta.level_id),
            "placements": sum(len(scan.result.placements) for scan in lane.scans),
            "placement_methods": dict(sorted(methods.items())),
            "certified_before_retry": before_retry,
            "retry_gain": retry_gain,
            "certified_after_retry": len(certs),
            "certificate_set_sha256": set_sha,
            "certificate_bits_sha256": bits_sha,
            "crc_calls": int(lane.decode.n_attempts),
            "bp_iterations": sum(int(row.n_iters) for row in lane.attempts),
            "attempt_records": len(lane.attempts),
            "feedback_eligible": level.artifacts.get("feedback", {}).get(
                "eligible", 0),
            "feedback_adopted": level.artifacts.get("feedback", {}).get(
                "adopted", 0),
            "wrong_certificates": [list(key) for key in _wrong(
                certs, descriptor, session.envelope.rate_id, gt_bits)],
        }

    portfolio = {
        tuple(key): row.user_bits()
        for key, row in session.certificate_union.items()
    }
    set_sha, bits_sha = _cert_digest(portfolio)
    portfolio_wrong = _wrong(
        portfolio, descriptor, session.envelope.rate_id, gt_bits)
    completion_report = completion.completion_report(portfolio, manifest)
    ordered_levels = [row.level_id for row in session.envelope.scale_plan]
    scale_comparison = _compare(
        lane_certs[ordered_levels[0]], lane_certs[ordered_levels[-1]])
    pairwise_scale_comparisons = {}
    for left_index, left_level in enumerate(ordered_levels):
        for right_level in ordered_levels[left_index + 1:]:
            pairwise_scale_comparisons[
                f"{left_level}__{right_level}"] = _compare(
                    lane_certs[left_level], lane_certs[right_level])

    baseline_report = None
    baseline_certs = None
    if args.baseline is not None:
        baseline, baseline_reference = _load_historical_e023b(args.baseline)
        if baseline.envelope.format_id != session.envelope.format_id:
            raise ValueError("historical baseline format differs")
        baseline_source_hashes = sorted({
            scan.source_sha256 for scan in baseline.scans
        })
        primary_source_hashes = sorted({
            capture.source.source_sha256 for capture in session.captures
        })
        baseline_source_matches = (
            baseline_source_hashes == primary_source_hashes
            and baseline.envelope.dpi == session.envelope.native_dpi
        )
        baseline_certs = _lane_certificates(baseline)
        baseline_wrong = _wrong(
            baseline_certs, descriptor, session.envelope.rate_id, gt_bits)
        baseline_methods = Counter(
            placed.method for scan in baseline.scans
            for placed in scan.result.placements)
        baseline_before_retry = sum(
            row.certified_new and row.stage != "retry150"
            for row in baseline.attempts)
        baseline_retry_gain = sum(
            row.certified_new and row.stage == "retry150"
            for row in baseline.attempts)
        baseline_report = {
            **baseline_reference,
            "source_sha256": baseline_source_hashes,
            "source_matches": baseline_source_matches,
            "dpi": baseline.envelope.dpi,
            "placements": sum(len(scan.result.placements)
                              for scan in baseline.scans),
            "placement_methods": dict(sorted(baseline_methods.items())),
            "certified_before_retry": baseline_before_retry,
            "retry_gain": baseline_retry_gain,
            "certified": len(baseline_certs),
            "crc_calls": int(baseline.decode.n_attempts),
            "bp_iterations": sum(int(row.n_iters) for row in baseline.attempts),
            "wrong_certificates": [list(key) for key in baseline_wrong],
            "vs_native_lane": _compare(
                baseline_certs, lane_certs[ordered_levels[-1]]),
            "vs_portfolio": _compare(baseline_certs, portfolio),
        }
        del baseline

    control_report = None
    control_certs = None
    control_gates = {}
    if args.control_state is not None:
        control_state_sha = _sha256(args.control_state)
        control = cascade_state.load_session(args.control_state)
        control_implementation = dict(
            control.envelope.implementation_sha256)
        control_policy = control_implementation.pop("run_policy", None)
        control_source = control.captures[0].source if (
            len(control.captures) == 1) else None
        primary_source = session.captures[0].source
        source_matches = bool(
            control_source is not None
            and replace(
                control_source,
                capture_id=primary_source.capture_id,
                source_path=primary_source.source_path,
            ) == primary_source)
        envelope_matches_except_scales = (
            replace(
                control.envelope,
                scale_plan=session.envelope.scale_plan,
            ) == session.envelope)
        control_ppc = [row.target_ppc
                       for row in control.envelope.scale_plan]
        primary_ppc = [row.target_ppc
                       for row in session.envelope.scale_plan]
        schedule_is_endpoint_control = (
            len(primary_ppc) > 2
            and control_ppc == [primary_ppc[0], primary_ppc[-1]])
        control_lanes = {}
        control_lane_certs = {}
        for lane_id, meta in sorted(
                control.decoder_lanes.items(),
                key=lambda item: item[1].level_id):
            lane = control.lane_sessions[lane_id]
            certs = _lane_certificates(lane)
            control_lane_certs[meta.level_id] = certs
            control_lanes[meta.level_id] = {
                "certified": len(certs),
                "crc_calls": int(lane.decode.n_attempts),
                "bp_iterations": sum(
                    int(row.n_iters) for row in lane.attempts),
                "attempt_records": len(lane.attempts),
                "wrong_certificates": [list(key) for key in _wrong(
                    certs, descriptor, session.envelope.rate_id, gt_bits)],
            }
        control_certs = {
            tuple(key): row.user_bits()
            for key, row in control.certificate_union.items()
        }
        control_wrong = _wrong(
            control_certs, descriptor, session.envelope.rate_id, gt_bits)
        control_completion = completion.completion_report(
            control_certs, manifest)
        comparison = _compare(control_certs, portfolio)
        auto_cost = {
            "crc_calls": sum(row["crc_calls"] for row in lanes.values()),
            "bp_iterations": sum(
                row["bp_iterations"] for row in lanes.values()),
            "attempt_records": sum(
                row["attempt_records"] for row in lanes.values()),
        }
        control_cost = {
            "crc_calls": sum(
                row["crc_calls"] for row in control_lanes.values()),
            "bp_iterations": sum(
                row["bp_iterations"] for row in control_lanes.values()),
            "attempt_records": sum(
                row["attempt_records"] for row in control_lanes.values()),
        }
        first_control_level = control.envelope.scale_plan[0].level_id
        control_report = {
            "path": str(args.control_state.resolve()),
            "file_sha256": control_state_sha,
            "authoritative_sha256": cascade_state.authoritative_digest(
                control),
            "status": control.status,
            "ppc": control_ppc,
            "implementation_matches_current": (
                control_implementation == current_implementation),
            "run_policy_sha256": control_policy,
            "lanes": control_lanes,
            "portfolio": {
                "certified": len(control_certs),
                "wrong_certificates": [
                    list(key) for key in control_wrong],
                "certificate_set_sha256": _cert_digest(
                    control_certs)[0],
                "certificate_bits_sha256": _cert_digest(
                    control_certs)[1],
            },
            "completion": control_completion,
            "vs_automatic": comparison,
            "cost": control_cost,
            "automatic_cost": auto_cost,
            "automatic_cost_delta": {
                name: auto_cost[name] - control_cost[name]
                for name in auto_cost
            },
        }
        control_gates = {
            "control_exhaustively_completed": (
                control.status == "exhausted"
                and len(control.captures) == 1
                and control.captures[0].status == "exhausted"),
            "control_source_matches": source_matches,
            "control_envelope_matches_except_scales": (
                envelope_matches_except_scales),
            "control_is_endpoint_schedule": schedule_is_endpoint_control,
            "control_implementation_matches_current": (
                control_implementation == current_implementation),
            "control_run_policy_matches": control_policy == registered_policy,
            "control_certificates_ground_truth_correct": not control_wrong,
            "control_fountain_payload_sha_verified": bool(
                control_completion["payload"]["verified"]),
            "coarse_anchor_identical_to_control": (
                _compare(
                    control_lane_certs[first_control_level],
                    lane_certs[ordered_levels[0]])["left_only"] == []
                and _compare(
                    control_lane_certs[first_control_level],
                    lane_certs[ordered_levels[0]])["right_only"] == []
                and _compare(
                    control_lane_certs[first_control_level],
                    lane_certs[ordered_levels[0]])["conflicts"] == []),
            "automatic_is_strict_superset_of_control": (
                not comparison["left_only"]
                and not comparison["conflicts"]
                and bool(comparison["right_only"])),
        }
        del control

    diag_gate = None
    if args.diag is not None:
        sidecars = sorted(args.diag.glob("frame_*.json"))
        final_meta = (
            None if not sidecars else json.loads(sidecars[-1].read_text()))
        frame = None if final_meta is None else int(final_meta["frame"])
        expected_pages = list(session.envelope.pages)
        page_pngs = ([] if frame is None else [
            args.diag / f"frame_{frame:05d}_p{page:04d}.png"
            for page in expected_pages])
        authoritative = cascade_state.authoritative_digest(session)
        diag_gate = {
            "frames": len(sidecars),
            "final_event": (
                None if final_meta is None else final_meta.get("event")),
            "final_frame": frame,
            "page_pngs": [str(path.resolve()) for path in page_pngs],
            "page_pngs_present": bool(page_pngs) and all(
                path.is_file() and path.stat().st_size > 0
                for path in page_pngs),
            "metadata_matches_state": bool(
                final_meta is not None
                and final_meta.get("event") == "session_complete"
                and final_meta.get("pages") == expected_pages
                and final_meta.get("certified") == len(portfolio)
                and final_meta.get("attempts") == len(session.attempts)
                and final_meta.get("authoritative_sha256") == authoritative
                and final_meta.get("levels_total")
                == len(session.envelope.scale_plan)),
            "files_present": bool(sidecars),
        }
        diag_gate["qualified"] = bool(
            diag_gate["files_present"]
            and diag_gate["page_pngs_present"]
            and diag_gate["metadata_matches_state"])

    gates = {
        "state_validated": True,
        "session_exhaustively_completed": (
            session.status == "exhausted"
            and all(row.status == "exhausted" for row in session.captures)),
        "exactly_one_capture": len(session.captures) == 1,
        "multiple_scale_levels_completed": (
            len(session.envelope.scale_plan) >= 2
            and all(level.status == "complete"
                    for level in session.captures[0].levels)
            if len(session.captures) == 1 else False),
        "state_file_sha256_recorded": bool(state_sha),
        "current_implementation_matches_state": implementation_matches,
        "run_policy_registered": policy_registered,
        "all_lane_certificates_ground_truth_correct": all(
            not row["wrong_certificates"] for row in lanes.values()),
        "portfolio_certificates_ground_truth_correct": not portfolio_wrong,
        "cross_scale_certificates_conflict_free": all(
            not row["conflicts"]
            for row in pairwise_scale_comparisons.values()),
        "every_scale_level_contributes": all(
            lane_certs[level] for level in ordered_levels),
        "scale_portfolio_adds_certificates": (
            len(portfolio) > len(lane_certs[ordered_levels[-1]])),
        "fountain_payload_sha_verified": bool(
            completion_report["payload"]["verified"]),
        "diagnostic_frames_present": (
            True if diag_gate is None else diag_gate["qualified"]),
    }
    if baseline_report is not None:
        gates["historical_baseline_source_matches"] = (
            baseline_report["source_matches"])
        gates["historical_baseline_certificates_correct"] = not (
            baseline_report["wrong_certificates"])
        gates["portfolio_does_not_lose_baseline_certificates"] = not (
            baseline_report["vs_portfolio"]["left_only"])
        gates["portfolio_agrees_with_historical_baseline"] = not (
            baseline_report["vs_portfolio"]["conflicts"])
        gates["portfolio_strictly_improves_historical_baseline"] = (
            len(portfolio) > len(baseline_certs))
    gates.update(control_gates)

    report = {
        "magic": MAGIC, "version": VERSION,
        "status": ("QUALIFIED_SINGLE_CAPTURE" if all(gates.values())
                   else "FAILED"),
        "scope": _qualification_scope(session, manifest),
        "label": args.label,
        "qualifier": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "implementation": {
            "stored": dict(sorted(stored_implementation.items())),
            "current": dict(sorted(current_implementation.items())),
            "matches": implementation_matches,
        },
        "state": {
            "path": str(args.state.resolve()), "file_sha256": state_sha,
            "authoritative_sha256": cascade_state.authoritative_digest(session),
            "captures": len(session.captures),
            "attempt_records": len(session.attempts),
            "implementation_matches_current": implementation_matches,
            "run_policy_sha256": registered_policy,
        },
        "ground_truth": gt_reference,
        "lanes": lanes,
        "scale_comparison": scale_comparison,
        "pairwise_scale_comparisons": pairwise_scale_comparisons,
        "ordered_marginal_contributions": {
            level: len(lane_certs[level]) for level in ordered_levels},
        "portfolio": {
            "certified": len(portfolio),
            "certificate_set_sha256": set_sha,
            "certificate_bits_sha256": bits_sha,
            "wrong_certificates": [list(key) for key in portfolio_wrong],
        },
        "completion": completion_report,
        "historical_baseline": baseline_report,
        "schedule_control": control_report,
        "diagnostics": diag_gate,
        "gates": gates,
        "gates_ok": all(gates.values()),
    }
    _write(args.out, report)
    print(
        f"{report['status']}: "
        + " ".join(
            f"{level}={lanes[level]['certified_after_retry']}"
            for level in ordered_levels)
        + f" portfolio={len(portfolio)} "
        + f"wrong={len(portfolio_wrong)} "
        + f"verified={completion_report['payload']['verified']}")
    print(f"  report {args.out}")
    return 0 if report["gates_ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

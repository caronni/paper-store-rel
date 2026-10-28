#!/usr/bin/env python
"""Export E023c's E023b lanes and audit E024 results across those lanes.

This is deliberately an experiment helper, not a receiver entry point.  It
never changes a receiver state.  ``export`` writes byte-complete current E023b
states from an authenticated E023c cascade.  ``audit`` loads completed E024
states through the production loader, checks their optional observer reports,
conflict-checks their certificate portfolio, and only then opens frozen ground
truth for a post-hoc correctness audit.

The input pickles are trusted local experiment artifacts.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "src/paperholo/receiver.py").is_file():
            return candidate
    raise RuntimeError("cannot locate the paper repository root")


ROOT = _repo_root()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/023c-scale-space-receiver"))
sys.path.insert(0, str(ROOT / "experiments/023b-integrated-receiver"))

import cascade_state  # noqa: E402
import run_e023c  # noqa: E402
import score_e023b  # noqa: E402
from paperholo import compose, feedbackstate, fountain, payloaddec, receiver  # noqa: E402
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402


EXPORT_MAGIC = "e023c-e024-lane-export-v1"
AUDIT_MAGIC = "e023c-e024-portfolio-audit-v1"
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _file_identity(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        signature = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
        after = os.fstat(stream.fileno())
        if signature != (
                after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError(f"{path} changed while hashing")
    current = path.stat()
    if signature != (
            current.st_dev, current.st_ino, current.st_size,
            current.st_mtime_ns, current.st_ctime_ns):
        raise ValueError(f"{path} was replaced while hashing")
    if size != int(current.st_size):
        raise ValueError(f"{path} size changed while hashing")
    return digest.hexdigest(), size


def _atomic_json(path: Path, payload: dict) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _named(values: list[str], flag: str) -> dict[str, Path]:
    rows: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{flag} expects LABEL=PATH, got {value!r}")
        label, raw = value.split("=", 1)
        if _LABEL.fullmatch(label) is None or not raw:
            raise ValueError(f"invalid {flag} value {value!r}")
        if label in rows:
            raise ValueError(f"duplicate {flag} label {label!r}")
        rows[label] = Path(raw).expanduser().resolve()
    return rows


def _key_list(keys) -> list[list[int]]:
    return [list(map(int, key)) for key in sorted(keys)]


def _pack(bits: np.ndarray) -> tuple[int, bytes]:
    values = np.asarray(bits, np.uint8).ravel()
    if values.size == 0 or np.any((values != 0) & (values != 1)):
        raise ValueError("certificate bits must be a non-empty binary vector")
    return int(values.size), np.packbits(values, bitorder="little").tobytes()


def _unpack(value: tuple[int, bytes]) -> np.ndarray:
    size, packed = value
    return np.unpackbits(
        np.frombuffer(packed, np.uint8), bitorder="little"
    )[:size].astype(np.uint8, copy=False)


def _certificate_digest(certs: dict[tuple[int, int, int], tuple[int, bytes]]) -> dict:
    set_digest = hashlib.sha256()
    bits_digest = hashlib.sha256()
    for key, (size, packed) in sorted(certs.items()):
        token = repr(tuple(map(int, key))).encode("ascii")
        set_digest.update(len(token).to_bytes(4, "big") + token)
        bits_digest.update(len(token).to_bytes(4, "big") + token)
        bits_digest.update(int(size).to_bytes(8, "big"))
        bits_digest.update(len(packed).to_bytes(8, "big") + packed)
    return {
        "count": len(certs),
        "set_sha256": set_digest.hexdigest(),
        "bits_sha256": bits_digest.hexdigest(),
    }


def _e024_certificates(session, *, generation_zero: bool = False):
    return {
        tuple(map(int, key)): _pack(row.user_bits)
        for key, row in session.certificates.items()
        if not generation_zero or int(row.born_generation) == 0
    }


def _portfolio(named: dict[str, dict]) -> tuple[dict, dict | None]:
    labels = list(named)
    keys = sorted({key for certs in named.values() for key in certs})
    support = {
        key: [label for label in labels if key in named[label]]
        for key in keys
    }
    conflicts = []
    for key in keys:
        values: dict[tuple[int, bytes], list[str]] = {}
        for label in support[key]:
            values.setdefault(named[label][key], []).append(label)
        if len(values) > 1:
            conflicts.append({
                "tile": list(key),
                "values": [{
                    "labels": grouped,
                    "n_bits": value[0],
                    "packed_sha256": hashlib.sha256(value[1]).hexdigest(),
                } for value, grouped in values.items()],
            })
    merged = None
    if not conflicts:
        merged = {
            key: named[support[key][0]][key]
            for key in keys
        }
    pairwise = []
    for index, left in enumerate(labels):
        left_keys = set(named[left])
        for right in labels[index + 1:]:
            right_keys = set(named[right])
            common = left_keys & right_keys
            pairwise.append({
                "left": left,
                "right": right,
                "intersection": len(common),
                "left_only": len(left_keys - right_keys),
                "right_only": len(right_keys - left_keys),
                "union": len(left_keys | right_keys),
                "changed_values": sum(
                    named[left][key] != named[right][key] for key in common),
            })
    report = {
        "labels": labels,
        "conflict_free": not conflicts,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "union": None if merged is None else {
            **_certificate_digest(merged),
            "keys": _key_list(merged),
        },
        "intersection_count": sum(
            len(rows) == len(labels) for rows in support.values()),
        "exclusive_count": sum(len(rows) == 1 for rows in support.values()),
        "exclusive_by_label": {
            label: _key_list(
                key for key, rows in support.items() if rows == [label])
            for label in labels
        },
        "support_histogram": {
            str(count): sum(len(rows) == count for rows in support.values())
            for count in range(1, len(labels) + 1)
        },
        "pairwise": pairwise,
    }
    return report, merged


def _effect(before: dict, after: dict) -> dict:
    common = set(before) & set(after)
    changed = {key for key in common if before[key] != after[key]}
    return {
        "gained_count": len(set(after) - set(before)),
        "gained": _key_list(set(after) - set(before)),
        "lost_count": len(set(before) - set(after)),
        "lost": _key_list(set(before) - set(after)),
        "changed_count": len(changed),
        "changed": _key_list(changed),
        "yield_delta": len(after) - len(before),
    }


def _descriptor(format_id: str):
    rows = [row for row in FORMAT_REGISTRY if row.format_id == format_id]
    if len(rows) != 1:
        raise ValueError(f"format registry has {len(rows)} entries for {format_id!r}")
    return rows[0]


def _ground_truth(path: Path, expected_sha: str | None, descriptor):
    actual, size = _file_identity(path)
    if expected_sha is not None and actual != expected_sha:
        raise ValueError(f"ground-truth SHA-256 {actual} != {expected_sha}")
    dots = np.load(path)
    spec = descriptor.spec()
    field = dots[::spec.cell_dots, ::spec.cell_dots].astype(np.uint8)
    if field.shape != tuple(spec.page_cells_yx):
        raise ValueError("ground-truth raster does not match format geometry")
    pim = compose.payload_index_map(spec, descriptor.seed)
    cells = np.argwhere(pim >= 0)
    cells = cells[np.argsort(
        pim[cells[:, 0], cells[:, 1]], kind="stable")]
    keystream = compose.payload_keystream(spec, descriptor.seed, 0)
    bits = (field[cells[:, 0], cells[:, 1]]
            ^ keystream[cells[:, 0], cells[:, 1]]).astype(np.uint8)
    return bits, {"path": str(path), "sha256": actual, "file_size": size}


def _wrong(certs: dict, descriptor, rate_id: str, gt_bits: np.ndarray):
    decode = payloaddec.DecodeState(descriptor, rate_id, (0,), ())
    wrong = []
    for key, packed in sorted(certs.items()):
        if key[0] != 0:
            raise ValueError("this helper's single .npy ground truth is page-0-only")
        out = payloaddec.TileOutcome(
            page=key[0], tile_yx=key[1:], state="certified",
            user_bits=_unpack(packed))
        indices, transmitted = decode.certified_payload_indices(out)
        if not np.array_equal(transmitted, gt_bits[indices]):
            wrong.append(key)
    return wrong


def _symbol_counts(certs: dict, manifest) -> dict:
    useful = []
    inert = []
    seen = set()
    for key, packed in sorted(certs.items()):
        page, ty, tx = key
        esi = fountain.esi_of_tile(manifest.volume, page, (ty, tx))
        if esi is None:
            inert.append(key)
            continue
        if esi in seen:
            raise ValueError(f"duplicate fountain symbol {esi} at {key}")
        if packed[0] < manifest.volume.symbol_bits:
            raise ValueError(f"certificate {key} is too short for one symbol")
        seen.add(esi)
        useful.append(key)
    return {
        "useful_count": len(useful),
        "inert_count": len(inert),
        "useful_keys": _key_list(useful),
        "inert_keys": _key_list(inert),
    }


def _report_audit(
    path: Path | None,
    session,
    baseline,
    *,
    frozen_identity: tuple[str, int] | None = None,
) -> dict:
    if path is None:
        return {"provided": False, "ok": True}
    raw = json.loads(path.read_text())
    sha256, size = _file_identity(path)
    expected_summary = session.summary()
    checks = {
        "authoritative_sha256": raw.get("authoritative_sha256")
        == feedbackstate.authoritative_digest(session),
        "profile": raw.get("profile") == session.envelope.profile,
        "config_sha256": raw.get("config_sha256")
        == session.envelope.config_sha256,
        "baseline_file_sha256": raw.get("baseline", {}).get("file_sha256")
        == session.baseline.file_sha256,
        "summary": raw.get("summary") == expected_summary,
        "baseline_authoritative_sha256": (
            receiver.authoritative_digest(baseline)
            == session.baseline.authoritative_sha256),
        "unchanged_since_blind_freeze": (
            frozen_identity is None or frozen_identity == (sha256, size)),
    }
    return {
        "provided": True,
        "path": str(path),
        "sha256": sha256,
        "file_size": size,
        "checks": checks,
        "ok": all(checks.values()),
    }


def command_export(args) -> int:
    source = args.cascade.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    manifest_path = (args.manifest_out.expanduser().resolve()
                     if args.manifest_out else out_dir / "lanes.json")
    session = cascade_state.load_session(source)
    session.validate_invariants()
    stored_implementation = dict(session.envelope.implementation_sha256)
    run_policy_sha256 = stored_implementation.pop("run_policy", None)
    if run_policy_sha256 is None:
        raise ValueError("cascade state has no registered run-policy fingerprint")
    if stored_implementation != dict(run_e023c.implementation_fingerprints()):
        raise ValueError(
            "cascade state was created by a different E023c implementation")
    scale_by_level = {
        row.level_id: row for row in session.envelope.scale_plan
    }
    ordered = sorted(
        session.decoder_lanes.items(),
        key=lambda item: (
            scale_by_level[item[1].level_id].ordinal,
            item[1].lane_kind, item[1].lane_id),
    )
    targets = []
    for lane_id, meta in ordered:
        scale = scale_by_level[meta.level_id]
        safe_level = re.sub(r"[^A-Za-z0-9_.-]+", "-", meta.level_id)
        target = out_dir / f"lane-{scale.ordinal:02d}-{safe_level}.pkl"
        label = f"l{scale.ordinal:02d}-{safe_level}"
        targets.append((lane_id, meta, scale, label, target))
    existing = [path for *_, path in targets if path.exists()]
    if manifest_path.exists():
        existing.append(manifest_path)
    if existing:
        raise ValueError(
            "export refuses to overwrite existing artifacts: "
            + ", ".join(map(str, existing)))
    out_dir.mkdir(parents=True, exist_ok=True)
    lane_rows = []
    for lane_id, meta, scale, label, target in targets:
        lane = session.lane_sessions[lane_id]
        if not isinstance(lane, receiver.ReceiverSession):
            raise ValueError(f"lane {lane_id} is not a current E023b session")
        if (lane.envelope.implementation_sha256
                != receiver.implementation_fingerprints()):
            raise ValueError(
                f"lane {lane_id} was created by a different E023b implementation")
        receiver.save_session(target, lane)
        file_sha, file_size = _file_identity(target)
        states = Counter(payloaddec.full_tile_states(lane.decode).values())
        lane_rows.append({
            "label": label,
            "path": str(target),
            "merge_source": f"{label}={target}",
            "lane_id": lane_id,
            "level_id": meta.level_id,
            "lane_kind": meta.lane_kind,
            "ordinal": int(scale.ordinal),
            "ppc": float(scale.target_ppc),
            "dpi": float(scale.effective_dpi),
            "capture_ids": [scan.capture_id for scan in lane.scans],
            "certified": int(states.get("certified", 0)),
            "tile_states": dict(sorted(states.items())),
            "attempt_records": len(lane.attempts),
            "crc_calls": int(lane.decode.n_attempts),
            "bp_iterations": sum(int(row.n_iters) for row in lane.attempts),
            "cascade_lane_semantic_sha256": meta.session_sha256,
            "receiver_authoritative_sha256": receiver.authoritative_digest(lane),
            "state_file_sha256": file_sha,
            "state_file_size": file_size,
        })
    source_sha, source_size = _file_identity(source)
    cascade_certs = {
        tuple(map(int, key)): _pack(row.user_bits())
        for key, row in session.certificate_union.items()
    }
    tool_sha, _ = _file_identity(Path(__file__).resolve())
    payload = {
        "magic": EXPORT_MAGIC,
        "version": 1,
        "tool_sha256": tool_sha,
        "cascade": {
            "path": str(source),
            "file_sha256": source_sha,
            "file_size": source_size,
            "authoritative_sha256": cascade_state.authoritative_digest(session),
            "format_id": session.envelope.format_id,
            "pages": list(session.envelope.pages),
            "capture_ids": list(session.capture_ids),
            "status": session.status,
            "run_policy_sha256": run_policy_sha256,
            "certificate_union": _certificate_digest(cascade_certs),
        },
        "lanes": lane_rows,
    }
    _atomic_json(manifest_path, payload)
    print(f"exported {len(lane_rows)} lanes to {out_dir}")
    print(f"manifest {manifest_path}")
    return 0


def command_audit(args) -> int:
    states = _named(args.run, "--run")
    reports = _named(args.report, "--report")
    baselines = _named(args.baseline, "--baseline")
    unknown = (set(reports) | set(baselines)) - set(states)
    if unknown:
        raise ValueError(f"observer label has no --run: {sorted(unknown)}")
    if not states:
        raise ValueError("audit needs at least one --run")
    output = args.out.expanduser().resolve()
    protected = {
        *states.values(), *reports.values(), *baselines.values(),
        args.ground_truth.expanduser().resolve(),
    }
    if args.manifest is not None:
        protected.add(args.manifest.expanduser().resolve())
    if output in protected:
        raise ValueError("--out must not overwrite an input artifact")
    # Freeze all result artifacts by bytes before ground truth is opened.  The
    # production loader is then run against these same files, and identities
    # are checked again after each potentially expensive replay.
    frozen_states = {
        label: _file_identity(path) for label, path in states.items()
    }
    frozen_reports = {
        label: _file_identity(path) for label, path in reports.items()
    }
    reference_label = next(iter(states))
    first_session, first_baseline = feedbackstate.load_session(
        states[reference_label], baseline_path=baselines.get(reference_label))
    reference = (
        first_session.baseline.format_id, bytes(first_session.baseline.seed),
        int(first_session.baseline.cell_dots),
        tuple(first_session.baseline.pages),
        tuple(first_session.baseline.page_cells_yx),
        first_session.baseline.rate_id,
        tuple(first_session.baseline.ordered_capture_ids),
    )
    format_id, _seed, cell_dots, pages, page_cells, rate_id, captures = reference
    if pages != (0,):
        raise ValueError("the supplied single ground-truth .npy requires pages=(0,)")
    descriptor = _descriptor(format_id)
    if (bytes(descriptor.seed) != _seed
            or descriptor.cell_dots != cell_dots
            or tuple(descriptor.spec().page_cells_yx) != page_cells
            or descriptor.ldpc_rate != rate_id):
        raise ValueError("format registry differs from E024 baseline geometry")
    gt_bits, gt_reference = _ground_truth(
        args.ground_truth.expanduser().resolve(),
        args.ground_truth_sha256, descriptor)
    manifest = None
    manifest_reference = None
    if args.manifest is not None:
        manifest = score_e023b.load_manifest(args.manifest)
        if (manifest.descriptor.format_id != format_id
                or manifest.descriptor.seed != descriptor.seed
                or manifest.descriptor.spec() != descriptor.spec()
                or manifest.volume.ldpc_spec.rate_id != rate_id
                or tuple(range(manifest.volume.n_pages)) != pages):
            raise ValueError("manifest differs from the E024 lane format")
        manifest_reference = {
            "path": str(manifest.path),
            "sha256": manifest.file_sha256,
            "symbol_bits": int(manifest.volume.symbol_bits),
            "symbols_total": int(manifest.volume.n_symbols_total),
        }
    start_by_lane = {}
    final_by_lane = {}
    lane_reports = {}
    reports_ok = True
    all_wrong = []
    lane_losses = False
    lane_changes = False
    for label, state_path in states.items():
        if label == reference_label:
            session, baseline = first_session, first_baseline
            first_session = None
            first_baseline = None
        else:
            session, baseline = feedbackstate.load_session(
                state_path, baseline_path=baselines.get(label))
            signature = (
                session.baseline.format_id, bytes(session.baseline.seed),
                int(session.baseline.cell_dots),
                tuple(session.baseline.pages),
                tuple(session.baseline.page_cells_yx),
                session.baseline.rate_id,
                tuple(session.baseline.ordered_capture_ids),
            )
            if signature != reference:
                raise ValueError(f"E024 lane state {label!r} is incompatible")
        start = _e024_certificates(session, generation_zero=True)
        final = _e024_certificates(session)
        start_by_lane[label] = start
        final_by_lane[label] = final
        effect = _effect(start, final)
        lane_losses |= bool(effect["lost_count"])
        lane_changes |= bool(effect["changed_count"])
        wrong_final = _wrong(final, descriptor, rate_id, gt_bits)
        wrong_new = _wrong(
            {key: final[key] for key in set(final) - set(start)},
            descriptor, rate_id, gt_bits)
        all_wrong.extend((label, key) for key in wrong_final)
        report_audit = _report_audit(
            reports.get(label), session, baseline,
            frozen_identity=frozen_reports.get(label))
        reports_ok &= bool(report_audit["ok"])
        state_sha, state_size = _file_identity(state_path)
        if frozen_states[label] != (state_sha, state_size):
            raise ValueError(f"E024 state {label!r} changed during audit")
        source_counts = Counter(row.source for row in session.certificates.values())
        row = {
            "state": {
                "path": str(state_path), "sha256": state_sha,
                "file_size": state_size,
                "authoritative_sha256": feedbackstate.authoritative_digest(session),
            },
            "baseline": {
                "path": session.baseline.path,
                "file_sha256": session.baseline.file_sha256,
                "authoritative_sha256": session.baseline.authoritative_sha256,
                "dpi": float(baseline.envelope.dpi),
            },
            "profile": session.envelope.profile,
            "fixed_point": bool(session.head.fixed_point),
            "generation": int(session.head.ordinal),
            "generation_zero": {
                **_certificate_digest(start), "keys": _key_list(start)},
            "final": {
                **_certificate_digest(final), "keys": _key_list(final)},
            "effect": effect,
            "new_keys": effect["gained"],
            "certificate_sources": dict(sorted(source_counts.items())),
            "ground_truth": {
                "audited_count": len(final),
                "wrong_count": len(wrong_final),
                "wrong": _key_list(wrong_final),
                "new_audited_count": effect["gained_count"],
                "new_wrong_count": len(wrong_new),
                "new_wrong": _key_list(wrong_new),
            },
            "work": {
                "generations_after_zero": len(session.generations) - 1,
                "accepted_revisions": sum(
                    int(row.accepted) for row in session.revisions.values()),
                "refused_revisions": sum(
                    not row.accepted for row in session.revisions.values()),
                "patches": len(session.patches),
                "changed_cells": sum(
                    int(row.payload_indices.size) for row in session.patches.values()),
                "owner_changes": sum(int(np.sum(
                    row.previous_owner != row.new_owner))
                    for row in session.patches.values()),
                "feedback_attempt_records": len(session.attempts),
                "feedback_crc_calls": int(session.crc_calls),
                "feedback_bp_iterations": sum(
                    int(row.n_iters) for row in session.attempts),
                "new_by_generation": dict(sorted(Counter(
                    str(row.born_generation)
                    for row in session.certificates.values()
                    if row.born_generation > 0).items())),
            },
            "observer_report": report_audit,
        }
        if manifest is not None:
            row["symbols"] = {
                "generation_zero": _symbol_counts(start, manifest),
                "final": _symbol_counts(final, manifest),
                "new": _symbol_counts(
                    {key: final[key] for key in set(final) - set(start)},
                    manifest),
            }
        lane_reports[label] = row
        del session, baseline
        gc.collect()
    del first_session, first_baseline
    start_report, start_union = _portfolio(start_by_lane)
    final_report, final_union = _portfolio(final_by_lane)
    delta = None
    global_wrong = None
    global_symbols = None
    if start_union is not None and final_union is not None:
        delta = _effect(start_union, final_union)
        wrong = _wrong(final_union, descriptor, rate_id, gt_bits)
        global_wrong = {
            "audited_count": len(final_union),
            "wrong_count": len(wrong),
            "wrong": _key_list(wrong),
        }
        if manifest is not None:
            global_symbols = {
                "generation_zero": _symbol_counts(start_union, manifest),
                "final": _symbol_counts(final_union, manifest),
                "new": _symbol_counts(
                    {key: final_union[key]
                     for key in set(final_union) - set(start_union)}, manifest),
            }
    gates = {
        "compatible_lane_states": True,
        "observer_reports_match_states": reports_ok,
        "generation_zero_conflict_free": start_report["conflict_free"],
        "final_conflict_free": final_report["conflict_free"],
        "no_lane_certificate_loss": not lane_losses,
        "no_lane_generation_zero_value_change": not lane_changes,
        "all_lane_certificates_match_ground_truth": not all_wrong,
        "global_union_matches_ground_truth": (
            global_wrong is not None and global_wrong["wrong_count"] == 0),
    }
    tool_sha, _ = _file_identity(Path(__file__).resolve())
    payload = {
        "magic": AUDIT_MAGIC,
        "version": 1,
        "tool_sha256": tool_sha,
        "blind_boundary": {
            "all_state_and_report_bytes_frozen_before_ground_truth": True,
            "ground_truth_use": "post-hoc certificate correctness only",
        },
        "compatibility": {
            "format_id": format_id,
            "cell_dots": cell_dots,
            "pages": list(pages),
            "page_cells_yx": list(page_cells),
            "rate_id": rate_id,
            "capture_ids": list(captures),
        },
        "ground_truth": gt_reference,
        "manifest": manifest_reference,
        "runs": lane_reports,
        "generation_zero_portfolio": start_report,
        "final_portfolio": final_report,
        "global_effect": delta,
        "global_ground_truth": global_wrong,
        "global_symbols": global_symbols,
        "gates": gates,
        "gates_ok": all(gates.values()),
    }
    _atomic_json(output, payload)
    print(f"audit report {output}")
    if final_report["union"] is not None:
        print(
            f"final union {final_report['union']['count']}; "
            f"gain {0 if delta is None else delta['gained_count']}; "
            f"conflicts {final_report['conflict_count']}; "
            f"wrong {None if global_wrong is None else global_wrong['wrong_count']}")
    return 0 if payload["gates_ok"] else 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="export embedded E023b lanes")
    export.add_argument("cascade", type=Path)
    export.add_argument("--out-dir", type=Path, required=True)
    export.add_argument("--manifest-out", type=Path)
    export.set_defaults(func=command_export)
    audit = sub.add_parser("audit", help="audit completed per-lane E024 states")
    audit.add_argument(
        "--run", action="append", default=[], metavar="LABEL=STATE", required=True)
    audit.add_argument(
        "--report", action="append", default=[], metavar="LABEL=JSON")
    audit.add_argument(
        "--baseline", action="append", default=[], metavar="LABEL=E023B",
        help="optional relocated immutable baseline for one E024 state")
    audit.add_argument("--ground-truth", type=Path, required=True)
    audit.add_argument("--ground-truth-sha256")
    audit.add_argument("--manifest", type=Path)
    audit.add_argument("--out", type=Path, required=True)
    audit.set_defaults(func=command_audit)
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        return args.func(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

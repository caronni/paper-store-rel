#!/usr/bin/env python
"""Export E023c's E023b lanes and audit E024 results across those lanes.

This is deliberately an experiment helper, not a receiver entry point.  It
never changes a receiver state.  ``export`` writes byte-complete current E023b
states from an authenticated E023c cascade.  ``adopt-v1`` writes only a v2
manifest after binding replayed, byte-frozen v1 lane files to that cascade.  A
bound ``audit`` proves that one completed E024 state and observer report
correspond to every exported lane and that every generation-zero certificate
equals the replay-proven official E023b union.  An explicitly unbound audit
remains available for observer work.  In both modes every non-truth input is
replayed and frozen before ground truth is opened for the post-hoc correctness
audit.

The input pickles are trusted local experiment artifacts.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import io
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
from paperholo import (compose, feedback, feedbackstate, fountain,  # noqa: E402
                       payloaddec, receiver)
from paperholo.formats import FORMAT_REGISTRY  # noqa: E402


EXPORT_MAGIC = "e023c-e024-lane-export-v2"
AUDIT_MAGIC = "e023c-e024-portfolio-audit-v2"
VERSION = 2
LEGACY_EXPORT_MAGIC = "e023c-e024-lane-export-v1"
LEGACY_EXPORT_VERSION = 1
LEGACY_BRIDGE_SHA256 = (
    "ecb60174fc5afca9afe45d25fd704cb6bb822e2ba3be6bc6b354de90405b0980"
)
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_HEX64 = re.compile(r"[0-9a-f]{64}")


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


def _stable_bytes(path: Path) -> tuple[bytes, tuple[str, int]]:
    """Read one small artifact while rejecting replacement or mutation."""
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        signature = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        raw = stream.read()
        after = os.fstat(stream.fileno())
        if signature != (
                after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError(f"{path} changed while reading")
    current = path.stat()
    if signature != (
            current.st_dev, current.st_ino, current.st_size,
            current.st_mtime_ns, current.st_ctime_ns):
        raise ValueError(f"{path} was replaced while reading")
    if len(raw) != int(current.st_size):
        raise ValueError(f"{path} size changed while reading")
    return raw, (hashlib.sha256(raw).hexdigest(), len(raw))


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
    raw, (actual, size) = _stable_bytes(path)
    if expected_sha is not None and actual != expected_sha:
        raise ValueError(f"ground-truth SHA-256 {actual} != {expected_sha}")
    dots = np.load(io.BytesIO(raw), allow_pickle=False)
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


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-")
    if not token:
        raise ValueError("lane identity cannot be represented in a filename")
    return token


def _lane_export_tokens(meta, scale) -> tuple[str, str]:
    """Return a stable label and filename that include full lane identity."""
    level = _safe_token(meta.level_id)
    kind = _safe_token(meta.lane_kind)
    identity = _safe_token(meta.lane_id)
    stem = f"{scale.ordinal:02d}-{level}-{kind}-{identity}"
    return f"l{stem}", f"lane-{stem}.pkl"


def _legacy_export_manifest(
    path: Path,
    raw: bytes,
    expected_tool_sha256: str,
) -> tuple[dict, dict[str, dict]]:
    """Parse only the exact manifest schema emitted by the frozen v1 bridge."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} is not valid legacy export JSON") from exc
    if (not isinstance(payload, dict)
            or payload.get("magic") != LEGACY_EXPORT_MAGIC
            or payload.get("version") != LEGACY_EXPORT_VERSION):
        raise ValueError(f"{path} is not a frozen-v1 export manifest")
    if payload.get("tool_sha256") != expected_tool_sha256:
        raise ValueError(
            "legacy export manifest was not created by the preserved v1 bridge")
    cascade = payload.get("cascade")
    if not isinstance(cascade, dict):
        raise ValueError("legacy export manifest has no cascade identity")
    rows = payload.get("lanes")
    if not isinstance(rows, list) or not rows:
        raise ValueError("legacy export manifest contains no lanes")
    by_lane: dict[str, dict] = {}
    labels: set[str] = set()
    paths: set[Path] = set()
    artifacts: set[tuple[str, int, str]] = set()
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"legacy export lane {position} is malformed")
        label = row.get("label")
        raw_path = row.get("path")
        lane_id = row.get("lane_id")
        file_sha = row.get("state_file_sha256")
        file_size = row.get("state_file_size")
        semantic = row.get("cascade_lane_semantic_sha256")
        authoritative = row.get("receiver_authoritative_sha256")
        if (_LABEL.fullmatch(label or "") is None
                or not isinstance(raw_path, str)
                or not isinstance(lane_id, str) or not lane_id
                or _HEX64.fullmatch(str(file_sha)) is None
                or type(file_size) is not int or file_size <= 0
                or _HEX64.fullmatch(str(semantic)) is None
                or _HEX64.fullmatch(str(authoritative)) is None
                or not isinstance(row.get("level_id"), str)
                or not isinstance(row.get("lane_kind"), str)
                or type(row.get("ordinal")) is not int):
            raise ValueError(f"legacy export lane {position} identity is malformed")
        lane_path = Path(raw_path).expanduser().resolve()
        if str(lane_path) != raw_path:
            raise ValueError(f"legacy export lane {label!r} path is not canonical")
        artifact = (file_sha, file_size, authoritative)
        if (lane_id in by_lane or label in labels or lane_path in paths
                or artifact in artifacts):
            raise ValueError("legacy export manifest contains duplicate lane identity")
        if row.get("merge_source") != f"{label}={lane_path}":
            raise ValueError(
                f"legacy export lane {label!r} merge source is malformed")
        by_lane[lane_id] = row
        labels.add(label)
        paths.add(lane_path)
        artifacts.add(artifact)
    return payload, by_lane


def _export_manifest(
    path: Path,
    raw: bytes,
    identity: tuple[str, int],
) -> tuple[dict, dict[str, dict]]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} is not valid export-manifest JSON") from exc
    if (not isinstance(payload, dict)
            or payload.get("magic") != EXPORT_MAGIC
            or payload.get("version") != VERSION):
        raise ValueError(f"{path} is not a current E023c lane export manifest")
    current_tool_sha, _ = _file_identity(Path(__file__).resolve())
    if payload.get("tool_sha256") != current_tool_sha:
        raise ValueError("export manifest was created by a different bridge")
    rows = payload.get("lanes")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("bound E023c audit requires at least two exported lanes")
    by_label: dict[str, dict] = {}
    paths: set[Path] = set()
    lane_ids: set[str] = set()
    identities: set[tuple[str, int, str]] = set()
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"export lane {position} is malformed")
        label = row.get("label")
        raw_path = row.get("path")
        file_sha = row.get("state_file_sha256")
        file_size = row.get("state_file_size")
        authoritative = row.get("receiver_authoritative_sha256")
        lane_id = row.get("lane_id")
        if (_LABEL.fullmatch(label or "") is None
                or not isinstance(raw_path, str)
                or not isinstance(file_sha, str)
                or _HEX64.fullmatch(file_sha) is None
                or type(file_size) is not int or file_size <= 0
                or not isinstance(authoritative, str)
                or _HEX64.fullmatch(authoritative) is None
                or not isinstance(lane_id, str) or not lane_id):
            raise ValueError(f"export lane {position} identity is malformed")
        lane_path = Path(raw_path).expanduser().resolve()
        if str(lane_path) != raw_path:
            raise ValueError(f"export lane {label!r} path is not canonical")
        artifact = (file_sha, file_size, authoritative)
        if (label in by_label or lane_path in paths or lane_id in lane_ids
                or artifact in identities):
            raise ValueError("export manifest contains duplicate lane identity")
        if row.get("merge_source") != f"{label}={lane_path}":
            raise ValueError(f"export lane {label!r} merge source is malformed")
        by_label[label] = row
        paths.add(lane_path)
        lane_ids.add(lane_id)
        identities.add(artifact)
    cascade = payload.get("cascade")
    certs = cascade.get("certificate_union") if isinstance(cascade, dict) else None
    if (not isinstance(certs, dict)
            or type(certs.get("count")) is not int
            or certs["count"] < 0
            or _HEX64.fullmatch(str(certs.get("set_sha256"))) is None
            or _HEX64.fullmatch(str(certs.get("bits_sha256"))) is None):
        raise ValueError("export manifest cascade certificate identity is malformed")
    payload["_identity"] = {
        "path": str(path), "sha256": identity[0], "file_size": identity[1]}
    return payload, by_label


def _assert_frozen(
    rows: dict[str, tuple[Path, tuple[str, int]]],
    kind: str,
) -> None:
    for label, (path, expected) in rows.items():
        if _file_identity(path) != expected:
            raise ValueError(f"{kind} {label!r} changed after its initial freeze")


def _replay_export_cascade(
    payload: dict,
    exported_lanes: dict[str, dict],
) -> tuple[dict, tuple[Path, tuple[str, int]], tuple[tuple[str, str], ...]]:
    """Replay the manifest's cascade and prove every declared lane identity."""
    declared = payload.get("cascade")
    if not isinstance(declared, dict):
        raise ValueError("export manifest has no cascade identity")
    raw_path = declared.get("path")
    if not isinstance(raw_path, str):
        raise ValueError("export manifest cascade path is malformed")
    source = Path(raw_path).expanduser().resolve()
    if str(source) != raw_path:
        raise ValueError("export manifest cascade path is not canonical")
    source_identity = _file_identity(source)
    if source_identity != (
            declared.get("file_sha256"), declared.get("file_size")):
        raise ValueError("export manifest cascade file identity changed")

    session = cascade_state.load_session(source)
    try:
        session.validate_invariants()
        if _file_identity(source) != source_identity:
            raise ValueError("export manifest cascade changed during replay")
        if session.status not in ("early_stopped", "exhausted"):
            raise ValueError(
                f"export manifest cascade is incomplete: {session.status!r}")

        stored_implementation = dict(session.envelope.implementation_sha256)
        run_policy_sha256 = stored_implementation.pop("run_policy", None)
        if run_policy_sha256 is None:
            raise ValueError(
                "export manifest cascade has no run-policy fingerprint")
        current_fingerprints = tuple(run_e023c.implementation_fingerprints())
        current_implementation = dict(current_fingerprints)
        if stored_implementation != current_implementation:
            raise ValueError(
                "export manifest cascade was created by a different "
                "E023c source closure")

        cascade_certificates = {
            tuple(map(int, key)): _pack(row.user_bits())
            for key, row in session.certificate_union.items()
        }
        cascade_certificate_identity = _certificate_digest(
            cascade_certificates)
        cascade_authoritative = cascade_state.authoritative_digest(session)
        expected_cascade = {
            "path": str(source),
            "file_sha256": source_identity[0],
            "file_size": source_identity[1],
            "authoritative_sha256": cascade_authoritative,
            "format_id": session.envelope.format_id,
            "pages": list(session.envelope.pages),
            "capture_ids": list(session.capture_ids),
            "status": session.status,
            "run_policy_sha256": run_policy_sha256,
            "certificate_union": cascade_certificate_identity,
        }
        if any(declared.get(key) != value
               for key, value in expected_cascade.items()):
            raise ValueError(
                "export manifest cascade metadata differs from replay")

        scale_by_level = {
            row.level_id: row for row in session.envelope.scale_plan
        }
        ordered = sorted(
            session.decoder_lanes.items(),
            key=lambda item: (
                scale_by_level[item[1].level_id].ordinal,
                item[1].lane_kind, item[1].lane_id),
        )
        declared_rows = payload["lanes"]
        if [row.get("lane_id") for row in declared_rows] != [
                lane_id for lane_id, _meta in ordered]:
            raise ValueError(
                "export manifest lane order or lane-ID coverage differs "
                "from cascade")

        lane_proofs = {}
        for declared_lane, (lane_id, meta) in zip(
                declared_rows, ordered, strict=True):
            scale = scale_by_level[meta.level_id]
            label, _filename = _lane_export_tokens(meta, scale)
            if exported_lanes.get(label) is not declared_lane:
                raise ValueError(
                    "export manifest lane label differs from cascade order")
            lane = session.lane_sessions[lane_id]
            if not isinstance(lane, receiver.ReceiverSession):
                raise ValueError(
                    f"cascade lane {lane_id!r} is not an E023b session")
            if (lane.envelope.implementation_sha256
                    != receiver.implementation_fingerprints()):
                raise ValueError(
                    f"cascade lane {lane_id!r} uses a different receiver")
            semantic = cascade_state.semantic_digest(lane)
            authoritative = receiver.authoritative_digest(lane)
            states = Counter(payloaddec.full_tile_states(
                lane.decode).values())
            expected_lane = {
                "label": label,
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
                "bp_iterations": sum(
                    int(row.n_iters) for row in lane.attempts),
                "cascade_lane_semantic_sha256": semantic,
                "receiver_authoritative_sha256": authoritative,
            }
            if (meta.session_sha256 != semantic
                    or any(declared_lane.get(key) != value
                           for key, value in expected_lane.items())):
                raise ValueError(
                    f"export manifest lane {lane_id!r} differs from cascade")
            lane_proofs[label] = {
                "lane_id": lane_id,
                "level_id": meta.level_id,
                "lane_kind": meta.lane_kind,
                "ordinal": int(scale.ordinal),
                "cascade_lane_semantic_sha256": semantic,
                "receiver_authoritative_sha256": authoritative,
                "state_file_sha256": declared_lane["state_file_sha256"],
                "state_file_size": declared_lane["state_file_size"],
            }

        proof = {
            **expected_cascade,
            "source_closure": {
                "stored": dict(sorted(stored_implementation.items())),
                "current": dict(sorted(current_implementation.items())),
                "matches": True,
            },
            "lane_count": len(lane_proofs),
            "lanes": lane_proofs,
        }
        result = proof, (source, source_identity), current_fingerprints
    finally:
        del session
        gc.collect()
    return result


def command_export(args) -> int:
    source = args.cascade.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    manifest_path = (args.manifest_out.expanduser().resolve()
                     if args.manifest_out else out_dir / "lanes.json")
    source_identity = _file_identity(source)
    session = cascade_state.load_session(source)
    session.validate_invariants()
    if _file_identity(source) != source_identity:
        raise ValueError("cascade state changed while it was loaded")
    if session.status not in ("early_stopped", "exhausted"):
        raise ValueError(
            f"cascade must be completed before export, got {session.status!r}")
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
        label, filename = _lane_export_tokens(meta, scale)
        target = out_dir / filename
        targets.append((lane_id, meta, scale, label, target))
    if not targets:
        raise ValueError("cascade contains no decoder lanes")
    labels = [label for *_, label, _path in targets]
    paths = [path for *_, path in targets]
    if len(labels) != len(set(labels)) or len(paths) != len(set(paths)):
        raise ValueError("export lane labels or paths collide")
    if manifest_path in set(paths):
        raise ValueError("export manifest path collides with a lane state")
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
    source_sha, source_size = source_identity
    cascade_certs = {
        tuple(map(int, key)): _pack(row.user_bits())
        for key, row in session.certificate_union.items()
    }
    tool_sha, _ = _file_identity(Path(__file__).resolve())
    payload = {
        "magic": EXPORT_MAGIC,
        "version": VERSION,
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


def command_adopt_v1(args) -> int:
    """Adopt exact v1 lane files into a current, bound-auditable manifest."""
    source = args.cascade.expanduser().resolve()
    legacy_path = args.legacy_manifest.expanduser().resolve()
    output = args.manifest_out.expanduser().resolve()
    legacy_bridge = Path(__file__).resolve().with_name(
        "e023c_e024_bridge_v1.py")
    if output in {source, legacy_path, legacy_bridge}:
        raise ValueError("--manifest-out must not overwrite an input artifact")
    if output.exists():
        raise ValueError(f"adoption refuses to overwrite {output}")

    source_identity = _file_identity(source)
    session = cascade_state.load_session(source)
    session.validate_invariants()
    if _file_identity(source) != source_identity:
        raise ValueError("cascade state changed while it was loaded")
    if session.status not in ("early_stopped", "exhausted"):
        raise ValueError(
            f"cascade must be completed before adoption, got {session.status!r}")
    stored_implementation = dict(session.envelope.implementation_sha256)
    run_policy_sha256 = stored_implementation.pop("run_policy", None)
    if run_policy_sha256 is None:
        raise ValueError("cascade state has no registered run-policy fingerprint")
    if stored_implementation != dict(run_e023c.implementation_fingerprints()):
        raise ValueError(
            "cascade state was created by a different E023c implementation")

    _legacy_bridge_raw, legacy_bridge_identity = _stable_bytes(legacy_bridge)
    if legacy_bridge_identity[0] != LEGACY_BRIDGE_SHA256:
        raise ValueError("preserved v1 bridge no longer has its frozen identity")
    legacy_raw, legacy_identity = _stable_bytes(legacy_path)
    legacy, legacy_by_lane = _legacy_export_manifest(
        legacy_path, legacy_raw, legacy_bridge_identity[0])
    if set(legacy_by_lane) != set(session.decoder_lanes):
        raise ValueError(
            "legacy manifest lane IDs do not exactly cover current cascade")
    if len(legacy_by_lane) < 2:
        raise ValueError("bound v2 adoption requires at least two lanes")

    cascade_certs = {
        tuple(map(int, key)): _pack(row.user_bits())
        for key, row in session.certificate_union.items()
    }
    cascade_certificate_identity = _certificate_digest(cascade_certs)
    cascade_authoritative = cascade_state.authoritative_digest(session)
    legacy_cascade = legacy["cascade"]
    if (_HEX64.fullmatch(str(legacy_cascade.get("file_sha256"))) is None
            or type(legacy_cascade.get("file_size")) is not int
            or legacy_cascade["file_size"] <= 0
            or legacy_cascade.get("authoritative_sha256")
            != cascade_authoritative
            or legacy_cascade.get("format_id") != session.envelope.format_id
            or legacy_cascade.get("pages") != list(session.envelope.pages)
            or legacy_cascade.get("capture_ids") != list(session.capture_ids)
            or legacy_cascade.get("status") != session.status
            or legacy_cascade.get("run_policy_sha256") != run_policy_sha256
            or legacy_cascade.get("certificate_union")
            != cascade_certificate_identity):
        raise ValueError(
            "legacy manifest does not describe the current cascade semantics")

    scale_by_level = {
        row.level_id: row for row in session.envelope.scale_plan
    }
    ordered = sorted(
        session.decoder_lanes.items(),
        key=lambda item: (
            scale_by_level[item[1].level_id].ordinal,
            item[1].lane_kind, item[1].lane_id),
    )
    lane_rows = []
    labels: set[str] = set()
    frozen_lanes: dict[str, tuple[Path, tuple[str, int]]] = {}
    for lane_id, meta in ordered:
        scale = scale_by_level[meta.level_id]
        legacy_row = legacy_by_lane[lane_id]
        legacy_lane_path = Path(legacy_row["path"])
        expected_v1_level = re.sub(
            r"[^A-Za-z0-9_.-]+", "-", meta.level_id)
        expected_v1_label = f"l{scale.ordinal:02d}-{expected_v1_level}"
        expected_v1_name = f"lane-{scale.ordinal:02d}-{expected_v1_level}.pkl"
        if (legacy_row["label"] != expected_v1_label
                or legacy_lane_path.name != expected_v1_name
                or legacy_row["level_id"] != meta.level_id
                or legacy_row["lane_kind"] != meta.lane_kind
                or legacy_row["ordinal"] != int(scale.ordinal)
                or legacy_row.get("ppc") != float(scale.target_ppc)
                or legacy_row.get("dpi") != float(scale.effective_dpi)):
            raise ValueError(
                f"legacy lane {lane_id!r} metadata differs from current cascade")

        current_lane = session.lane_sessions[lane_id]
        if not isinstance(current_lane, receiver.ReceiverSession):
            raise ValueError(f"cascade lane {lane_id!r} is not an E023b session")
        if (current_lane.envelope.implementation_sha256
                != receiver.implementation_fingerprints()):
            raise ValueError(
                f"cascade lane {lane_id!r} uses a different receiver")
        current_semantic = cascade_state.semantic_digest(current_lane)
        current_authoritative = receiver.authoritative_digest(current_lane)
        if (meta.session_sha256 != current_semantic
                or legacy_row["cascade_lane_semantic_sha256"]
                != current_semantic
                or legacy_row["receiver_authoritative_sha256"]
                != current_authoritative):
            raise ValueError(
                f"legacy lane {lane_id!r} semantic identity differs from cascade")

        lane_identity = _file_identity(legacy_lane_path)
        if lane_identity != (
                legacy_row["state_file_sha256"],
                legacy_row["state_file_size"]):
            raise ValueError(
                f"legacy lane {lane_id!r} file identity changed")
        legacy_lane = receiver.load_session(legacy_lane_path)
        if _file_identity(legacy_lane_path) != lane_identity:
            raise ValueError(
                f"legacy lane {lane_id!r} changed while it was replayed")
        legacy_semantic = cascade_state.semantic_digest(legacy_lane)
        legacy_authoritative = receiver.authoritative_digest(legacy_lane)
        if (legacy_semantic != current_semantic
                or legacy_authoritative != current_authoritative):
            raise ValueError(
                f"legacy lane {lane_id!r} replay differs from current cascade")

        states = Counter(payloaddec.full_tile_states(
            legacy_lane.decode).values())
        capture_ids = [scan.capture_id for scan in legacy_lane.scans]
        measured = {
            "capture_ids": capture_ids,
            "certified": int(states.get("certified", 0)),
            "tile_states": dict(sorted(states.items())),
            "attempt_records": len(legacy_lane.attempts),
            "crc_calls": int(legacy_lane.decode.n_attempts),
            "bp_iterations": sum(
                int(row.n_iters) for row in legacy_lane.attempts),
        }
        if any(legacy_row.get(key) != value
               for key, value in measured.items()):
            raise ValueError(
                f"legacy lane {lane_id!r} measurements are inconsistent")
        label, _unused_filename = _lane_export_tokens(meta, scale)
        if label in labels:
            raise ValueError("adopted v2 lane labels collide")
        labels.add(label)
        lane_rows.append({
            "label": label,
            "path": str(legacy_lane_path),
            "merge_source": f"{label}={legacy_lane_path}",
            "lane_id": lane_id,
            "level_id": meta.level_id,
            "lane_kind": meta.lane_kind,
            "ordinal": int(scale.ordinal),
            "ppc": float(scale.target_ppc),
            "dpi": float(scale.effective_dpi),
            **measured,
            "cascade_lane_semantic_sha256": current_semantic,
            "receiver_authoritative_sha256": current_authoritative,
            "state_file_sha256": lane_identity[0],
            "state_file_size": lane_identity[1],
        })
        frozen_lanes[label] = (legacy_lane_path, lane_identity)
        del legacy_lane
        gc.collect()

    if output in {path for path, _identity in frozen_lanes.values()}:
        raise ValueError("--manifest-out must not overwrite a legacy lane")
    source_sha, source_size = source_identity
    current_bridge = Path(__file__).resolve()
    tool_identity = _file_identity(current_bridge)
    payload = {
        "magic": EXPORT_MAGIC,
        "version": VERSION,
        "tool_sha256": tool_identity[0],
        "adoption": {
            "mode": "frozen_v1_exact_artifact_adoption",
            "legacy_manifest": {
                "path": str(legacy_path),
                "sha256": legacy_identity[0],
                "file_size": legacy_identity[1],
            },
            "legacy_bridge": {
                "path": str(legacy_bridge),
                "sha256": legacy_bridge_identity[0],
                "file_size": legacy_bridge_identity[1],
            },
            "state_files_rewritten": False,
        },
        "cascade": {
            "path": str(source),
            "file_sha256": source_sha,
            "file_size": source_size,
            "authoritative_sha256": cascade_authoritative,
            "format_id": session.envelope.format_id,
            "pages": list(session.envelope.pages),
            "capture_ids": list(session.capture_ids),
            "status": session.status,
            "run_policy_sha256": run_policy_sha256,
            "certificate_union": cascade_certificate_identity,
        },
        "lanes": lane_rows,
    }

    # No receiver state is written.  Recheck every adopted input immediately
    # before atomically creating the new JSON manifest.
    _assert_frozen({"cascade": (source, source_identity)}, "adoption input")
    _assert_frozen(
        {"legacy manifest": (legacy_path, legacy_identity)},
        "adoption input")
    _assert_frozen(
        {"legacy bridge": (legacy_bridge, legacy_bridge_identity)},
        "adoption input")
    _assert_frozen(
        {"current bridge": (current_bridge, tool_identity)},
        "adoption input")
    _assert_frozen(frozen_lanes, "legacy lane")
    if cascade_state.authoritative_digest(session) != cascade_authoritative:
        raise ValueError("cascade semantics changed during adoption")
    _atomic_json(output, payload)
    print(f"adopted {len(lane_rows)} exact v1 lane artifacts")
    print(f"manifest {output}")
    return 0


def command_audit(args) -> int:
    states = _named(args.run, "--run")
    reports = _named(args.report, "--report")
    baselines = _named(args.baseline, "--baseline")
    export_path = (None if args.export_manifest is None else
                   args.export_manifest.expanduser().resolve())
    union_path = (None if args.certificate_union is None else
                  args.certificate_union.expanduser().resolve())
    bound = export_path is not None or union_path is not None
    if (export_path is None) != (union_path is None):
        raise ValueError(
            "bound audit requires both --export-manifest and "
            "--certificate-union")
    unknown = (set(reports) | set(baselines)) - set(states)
    if unknown:
        raise ValueError(f"observer label has no --run: {sorted(unknown)}")
    if not states:
        raise ValueError("audit needs at least one --run")
    if len(set(states.values())) != len(states):
        raise ValueError("audit state paths must be unique")
    if bound and set(reports) != set(states):
        missing = sorted(set(states) - set(reports))
        raise ValueError(
            "bound audit requires one observer report per run; "
            f"missing labels: {missing}")
    if (bound
            and (not isinstance(args.ground_truth_sha256, str)
                 or _HEX64.fullmatch(args.ground_truth_sha256) is None)):
        raise ValueError(
            "bound audit requires a valid 64-hex --ground-truth-sha256")
    output = args.out.expanduser().resolve()
    protected = {
        *states.values(), *reports.values(), *baselines.values(),
        args.ground_truth.expanduser().resolve(),
    }
    if args.manifest is not None:
        protected.add(args.manifest.expanduser().resolve())
    if export_path is not None:
        protected.add(export_path)
    if union_path is not None:
        protected.add(union_path)
    if output in protected:
        raise ValueError("--out must not overwrite an input artifact")

    # Freeze result artifacts before any replay.  They and every baseline,
    # manifest, and official-union input are checked again immediately before
    # ground truth is opened.
    frozen_states = {
        label: _file_identity(path) for label, path in states.items()
    }
    frozen_reports = {
        label: _file_identity(path) for label, path in reports.items()
    }

    export_payload = None
    exported_lanes: dict[str, dict] = {}
    export_identity = None
    union_identity = None
    union_proof = None
    union_certificates = None
    cascade_proof = None
    frozen_cascade = None
    frozen_source_closure = None
    frozen_export_lanes: dict[str, tuple[Path, tuple[str, int]]] = {}
    if bound:
        export_raw, export_identity = _stable_bytes(export_path)
        export_payload, exported_lanes = _export_manifest(
            export_path, export_raw, export_identity)
        if set(states) != set(exported_lanes):
            raise ValueError(
                "bound audit run labels must exactly cover exported lanes")
        (cascade_proof, frozen_cascade,
         frozen_source_closure) = _replay_export_cascade(
             export_payload, exported_lanes)
        if output == frozen_cascade[0]:
            raise ValueError("--out must not overwrite the exported cascade")
        for label, lane in exported_lanes.items():
            lane_path = Path(lane["path"])
            identity = _file_identity(lane_path)
            if identity != (
                    lane["state_file_sha256"], lane["state_file_size"]):
                raise ValueError(f"exported lane {label!r} file identity changed")
            frozen_export_lanes[label] = (lane_path, identity)

        union_raw, union_identity = _stable_bytes(union_path)
        union_proof = feedback.validate_certificate_union(union_path)
        if (union_proof["sha256"], union_proof["size"]) != union_identity:
            raise ValueError("official certificate union changed during proof")
        proof_sources = {
            row["label"]: row for row in union_proof["sources"]}
        if (len(proof_sources) != len(union_proof["sources"])
                or set(proof_sources) != set(exported_lanes)):
            raise ValueError(
                "official certificate union does not exactly cover exports")
        for label, lane in exported_lanes.items():
            source = proof_sources[label]
            expected = {
                "label": label,
                "state_file_sha256": lane["state_file_sha256"],
                "state_file_size": lane["state_file_size"],
                "authoritative_sha256": lane[
                    "receiver_authoritative_sha256"],
            }
            if source != expected:
                raise ValueError(
                    f"official union source {label!r} differs from export")
        seeded = feedback.certificate_union_seed_records(union_raw)
        if seeded["sha256"] != union_identity[0]:
            raise ValueError("official union embedded proof identity changed")
        union_certificates = {
            tuple(map(int, key)): _pack(row["bits"])
            for key, row in seeded["records"].items()
        }
        union_digest = _certificate_digest(union_certificates)
        if union_digest != export_payload["cascade"]["certificate_union"]:
            raise ValueError(
                "official union certificates differ from cascade portfolio")

    reference = None
    descriptor = None
    frozen_baselines: dict[str, tuple[Path, tuple[str, int]]] = {}
    start_by_lane = {}
    final_by_lane = {}
    lane_reports = {}
    reports_ok = True
    lane_losses = False
    lane_changes = False
    all_fixed_point = True
    for label, state_path in states.items():
        session, baseline = feedbackstate.load_session(
            state_path, baseline_path=baselines.get(label))
        all_fixed_point &= bool(session.head.fixed_point)
        signature = (
            session.baseline.format_id, bytes(session.baseline.seed),
            int(session.baseline.cell_dots),
            tuple(session.baseline.pages),
            tuple(session.baseline.page_cells_yx),
            session.baseline.rate_id,
            tuple(session.baseline.ordered_capture_ids),
        )
        if reference is None:
            reference = signature
            format_id, seed, cell_dots, pages, page_cells, rate_id, captures = (
                reference)
            if pages != (0,):
                raise ValueError(
                    "the supplied single ground-truth .npy requires pages=(0,)")
            descriptor = _descriptor(format_id)
            if (bytes(descriptor.seed) != seed
                    or descriptor.cell_dots != cell_dots
                    or tuple(descriptor.spec().page_cells_yx) != page_cells
                    or descriptor.ldpc_rate != rate_id):
                raise ValueError(
                    "format registry differs from E024 baseline geometry")
        elif signature != reference:
            raise ValueError(f"E024 lane state {label!r} is incompatible")

        baseline_path = Path(
            baselines.get(label) or session.baseline.path).expanduser().resolve()
        if output == baseline_path:
            raise ValueError("--out must not overwrite an implicit baseline")
        baseline_identity = _file_identity(baseline_path)
        if baseline_identity != (
                session.baseline.file_sha256, session.baseline.file_size):
            raise ValueError(f"E024 baseline {label!r} changed after replay")
        frozen_baselines[label] = (baseline_path, baseline_identity)
        if bound:
            lane = exported_lanes[label]
            if (
                session.baseline.file_sha256,
                session.baseline.file_size,
                session.baseline.authoritative_sha256,
            ) != (
                lane["state_file_sha256"],
                lane["state_file_size"],
                lane["receiver_authoritative_sha256"],
            ):
                raise ValueError(
                    f"E024 baseline {label!r} is not its exact exported lane")
        start = _e024_certificates(session, generation_zero=True)
        final = _e024_certificates(session)
        if bound and start != union_certificates:
            raise ValueError(
                f"E024 generation zero {label!r} differs from official union")
        start_by_lane[label] = start
        final_by_lane[label] = final
        effect = _effect(start, final)
        lane_losses |= bool(effect["lost_count"])
        lane_changes |= bool(effect["changed_count"])
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
            "work": {
                "generations_after_zero": len(session.generations) - 1,
                "accepted_revisions": sum(
                    int(revision.accepted)
                    for revision in session.revisions.values()),
                "refused_revisions": sum(
                    not revision.accepted
                    for revision in session.revisions.values()),
                "patches": len(session.patches),
                "changed_cells": sum(
                    int(patch.payload_indices.size)
                    for patch in session.patches.values()),
                "owner_changes": sum(int(np.sum(
                    patch.previous_owner != patch.new_owner))
                    for patch in session.patches.values()),
                "feedback_attempt_records": len(session.attempts),
                "feedback_crc_calls": int(session.crc_calls),
                "feedback_bp_iterations": sum(
                    int(attempt.n_iters) for attempt in session.attempts),
                "new_by_generation": dict(sorted(Counter(
                    str(certificate.born_generation)
                    for certificate in session.certificates.values()
                    if certificate.born_generation > 0).items())),
            },
            "observer_report": report_audit,
        }
        lane_reports[label] = row
        del session, baseline
        gc.collect()

    assert reference is not None and descriptor is not None
    format_id, _seed, cell_dots, pages, page_cells, rate_id, captures = reference
    manifest = None
    manifest_reference = None
    frozen_manifest = None
    if args.manifest is not None:
        manifest_path = args.manifest.expanduser().resolve()
        manifest_identity = _file_identity(manifest_path)
        manifest = score_e023b.load_manifest(manifest_path)
        if _file_identity(manifest_path) != manifest_identity:
            raise ValueError("fountain manifest changed while it was loaded")
        frozen_manifest = {
            "fountain": (manifest_path, manifest_identity)}
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
        for label in states:
            start = start_by_lane[label]
            final = final_by_lane[label]
            lane_reports[label]["symbols"] = {
                "generation_zero": _symbol_counts(start, manifest),
                "final": _symbol_counts(final, manifest),
                "new": _symbol_counts(
                    {key: final[key] for key in set(final) - set(start)},
                    manifest),
            }

    start_report, start_union = _portfolio(start_by_lane)
    final_report, final_union = _portfolio(final_by_lane)
    delta = (_effect(start_union, final_union)
             if start_union is not None and final_union is not None else None)
    global_symbols = None
    if (start_union is not None and final_union is not None
            and manifest is not None):
        global_symbols = {
            "generation_zero": _symbol_counts(start_union, manifest),
            "final": _symbol_counts(final_union, manifest),
            "new": _symbol_counts(
                {key: final_union[key]
                 for key in set(final_union) - set(start_union)}, manifest),
        }

    # All non-truth inputs have now been replayed.  Re-hash every one before
    # opening the ground-truth file, including early lanes whose replay may
    # have taken long enough for a concurrent replacement to matter.
    _assert_frozen({
        label: (path, frozen_states[label])
        for label, path in states.items()}, "E024 state")
    _assert_frozen({
        label: (path, frozen_reports[label])
        for label, path in reports.items()}, "observer report")
    _assert_frozen(frozen_baselines, "E023b baseline")
    if bound:
        assert frozen_cascade is not None
        assert frozen_source_closure is not None
        _assert_frozen(frozen_export_lanes, "exported lane")
        _assert_frozen({
            "cascade": frozen_cascade,
            "manifest": (export_path, export_identity),
            "union": (union_path, union_identity),
        }, "binding artifact")
        if tuple(run_e023c.implementation_fingerprints()) != (
                frozen_source_closure):
            raise ValueError(
                "E023c source closure changed after cascade replay")
    if frozen_manifest is not None:
        _assert_frozen(frozen_manifest, "fountain manifest")

    gt_bits, gt_reference = _ground_truth(
        args.ground_truth.expanduser().resolve(),
        args.ground_truth_sha256, descriptor)
    all_wrong = []
    for label in states:
        start = start_by_lane[label]
        final = final_by_lane[label]
        wrong_final = _wrong(final, descriptor, rate_id, gt_bits)
        wrong_new = _wrong(
            {key: final[key] for key in set(final) - set(start)},
            descriptor, rate_id, gt_bits)
        all_wrong.extend((label, key) for key in wrong_final)
        lane_reports[label]["ground_truth"] = {
            "audited_count": len(final),
            "wrong_count": len(wrong_final),
            "wrong": _key_list(wrong_final),
            "new_audited_count": len(set(final) - set(start)),
            "new_wrong_count": len(wrong_new),
            "new_wrong": _key_list(wrong_new),
        }
    global_wrong = None
    if final_union is not None:
        wrong = _wrong(final_union, descriptor, rate_id, gt_bits)
        global_wrong = {
            "audited_count": len(final_union),
            "wrong_count": len(wrong),
            "wrong": _key_list(wrong),
        }

    gates = {
        "compatible_lane_states": True,
        "supplied_observer_reports_match_states": reports_ok,
        "generation_zero_conflict_free": start_report["conflict_free"],
        "final_conflict_free": final_report["conflict_free"],
        "no_lane_certificate_loss": not lane_losses,
        "no_lane_generation_zero_value_change": not lane_changes,
        "all_lane_certificates_match_ground_truth": not all_wrong,
        "global_union_matches_ground_truth": (
            global_wrong is not None and global_wrong["wrong_count"] == 0),
    }
    if bound:
        gates.update({
            "manifest_referenced_cascade_replayed_and_matches": True,
            "e023c_source_closure_matches_and_remained_frozen": True,
            "all_runs_reached_fixed_point": all_fixed_point,
            "every_exported_lane_has_exactly_one_run": True,
            "every_bound_observer_report_is_present": True,
            "every_baseline_matches_its_exported_lane": True,
            "official_union_exactly_covers_exported_lanes": True,
            "official_union_matches_cascade_portfolio": True,
            "every_generation_zero_equals_official_union": True,
        })
    tool_sha, _ = _file_identity(Path(__file__).resolve())
    gates_ok = all(gates.values())
    status = (
        "QUALIFIED_BOUND" if bound and gates_ok else
        "FAILED_BOUND" if bound else
        "OBSERVED_UNBOUND" if gates_ok else
        "FAILED_UNBOUND"
    )
    binding = ({
        "mode": "bound_e023c_composition",
        "qualified": gates_ok,
        "cascade": cascade_proof,
        "export_manifest": export_payload["_identity"],
        "certificate_union": {
            "path": str(union_path),
            "sha256": union_identity[0],
            "file_size": union_identity[1],
            "source_count": union_proof["source_count"],
            "certificate_count": union_proof["certificate_count"],
            "certificate_identity": _certificate_digest(
                union_certificates),
        },
    } if bound else {
        "mode": "unbound_observer",
        "qualified": False,
        "reason": (
            "No export manifest or official E023b union was supplied; "
            "this report audits only the explicitly supplied E024 states."),
    })
    payload = {
        "magic": AUDIT_MAGIC,
        "version": VERSION,
        "status": status,
        "tool_sha256": tool_sha,
        "blind_boundary": {
            "all_non_truth_inputs_replayed_and_frozen_before_ground_truth": True,
            "ground_truth_use": "post-hoc certificate correctness only",
        },
        "binding": binding,
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
        "gates_ok": gates_ok,
    }
    _atomic_json(output, payload)
    print(f"audit report {output}")
    if final_report["union"] is not None:
        print(
            f"final union {final_report['union']['count']}; "
            f"gain {0 if delta is None else delta['gained_count']}; "
            f"conflicts {final_report['conflict_count']}; "
            f"wrong {None if global_wrong is None else global_wrong['wrong_count']}")
    return 0 if gates_ok else 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="export embedded E023b lanes")
    export.add_argument("cascade", type=Path)
    export.add_argument("--out-dir", type=Path, required=True)
    export.add_argument("--manifest-out", type=Path)
    export.set_defaults(func=command_export)
    adopt = sub.add_parser(
        "adopt-v1",
        help="bind exact frozen-v1 lane files into a v2 manifest")
    adopt.add_argument("cascade", type=Path)
    adopt.add_argument("--legacy-manifest", type=Path, required=True)
    adopt.add_argument("--manifest-out", type=Path, required=True)
    adopt.set_defaults(func=command_adopt_v1)
    audit = sub.add_parser("audit", help="audit completed per-lane E024 states")
    audit.add_argument(
        "--run", action="append", default=[], metavar="LABEL=STATE", required=True)
    audit.add_argument(
        "--report", action="append", default=[], metavar="LABEL=JSON",
        help=("observer report; optional in unbound mode, exactly one per "
              "run in bound mode"))
    audit.add_argument(
        "--baseline", action="append", default=[], metavar="LABEL=E023B",
        help="optional relocated immutable baseline for one E024 state")
    audit.add_argument("--ground-truth", type=Path, required=True)
    audit.add_argument(
        "--ground-truth-sha256",
        help=("expected frozen truth digest; a 64-hex value is required in "
              "bound mode"))
    audit.add_argument(
        "--export-manifest", type=Path,
        help="v2 lanes.json; requires --certificate-union")
    audit.add_argument(
        "--certificate-union", type=Path,
        help="official replayable E023b union; requires --export-manifest")
    audit.add_argument(
        "--manifest", type=Path,
        help="optional fountain manifest for useful/inert classification")
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

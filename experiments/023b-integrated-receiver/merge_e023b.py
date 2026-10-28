#!/usr/bin/env python
"""Union CRC-certified E023b tiles from correlated receiver views.

This is a certificate-boundary merge, not an evidence merge.  Each input is
loaded and validated as a current production E023b state.  Native, decimated,
or otherwise correlated views must name the same physical captures in the
same order; their LLRs and decode attempts are never summed.  Only identical
CRC-certified user bits are pooled, and any overlapping disagreement is
fatal.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import pickle
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import ldpc, payloaddec, receiver  # noqa: E402


UNION_MAGIC = "e023b-certificate-union-v1"
UNION_VERSION = 1
UNION_ALGORITHM = "certificate-only/correlated-views/v1"
PACK_BITORDER = "little"
_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class SourceSpec:
    label: str
    path: Path


@dataclass(frozen=True)
class Certificate:
    n_user_bits: int
    user_bits_packed: bytes
    certified_by: str
    attempt: dict


@dataclass(frozen=True)
class LoadedSource:
    """Validated, compact source state with no retained receiver session."""

    label: str
    path: Path
    file_sha256: str
    file_size: int
    authoritative_sha256: str
    compatibility_key: tuple
    compatibility: dict
    ordered_capture_ids: tuple[str, ...]
    certificates: dict[tuple[int, int, int], Certificate]
    tile_keys: frozenset[tuple[int, int, int]]
    degenerate_keys: frozenset[tuple[int, int, int]]
    crc_calls: int
    bp_iterations: int
    provenance: dict


def parse_source(value: str) -> SourceSpec:
    """Parse one ``LABEL=STATE`` argument without ambiguity."""
    if "=" not in value:
        raise ValueError(
            f"invalid --source {value!r}; expected LABEL=STATE")
    label, raw_path = value.split("=", 1)
    if not _LABEL_RE.fullmatch(label):
        raise ValueError(
            f"invalid source label {label!r}; use letters, digits, '.', "
            "'_', or '-'")
    if not raw_path:
        raise ValueError(f"source {label!r} has an empty state path")
    return SourceSpec(label, Path(raw_path).expanduser().resolve())


def _stream_sha256(stream: BinaryIO) -> str:
    """Hash an open file without retaining its bytes."""
    stream.seek(0)
    digest = hashlib.sha256()
    while True:
        block = stream.read(1024 * 1024)
        if not block:
            return digest.hexdigest()
        digest.update(block)


def _stat_signature(stat: os.stat_result) -> tuple[int, ...]:
    """Fields that expose replacement or in-place content changes."""
    return (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )


def _raise_changed(path: Path) -> None:
    raise ValueError(f"{path} changed while reading")


def _compatibility_key(envelope: receiver.SessionEnvelope) -> tuple:
    return (
        envelope.format_id,
        bytes(envelope.seed),
        int(envelope.cell_dots),
        tuple(int(value) for value in envelope.page_cells_yx),
        tuple(int(page) for page in envelope.pages),
        envelope.rate_id,
    )


def _compatibility_payload(envelope: receiver.SessionEnvelope) -> dict:
    return {
        "format_id": envelope.format_id,
        "seed_hex": bytes(envelope.seed).hex(),
        "cell_dots": int(envelope.cell_dots),
        "page_cells_yx": [
            int(value) for value in envelope.page_cells_yx],
        "pages": [int(page) for page in envelope.pages],
        "rate_id": envelope.rate_id,
    }


def _attempt_provenance(attempt: receiver.TileAttempt) -> dict:
    return {
        "attempt_id": attempt.attempt_id,
        "evidence_digest": attempt.evidence_digest,
        "stage": attempt.stage,
        "source": attempt.source,
        "scan_ids": list(attempt.scan_ids),
        "capture_ids": list(attempt.capture_ids),
        "decoder_profile": attempt.decoder_profile,
        "decoder_invoked": bool(attempt.decoder_invoked),
        "k_eff": int(attempt.k_eff),
        "n_nonshort": int(attempt.n_nonshort),
        "n_informative": int(attempt.n_informative),
        "coverage": float(attempt.coverage),
        "n_iters": int(attempt.n_iters),
        "syndrome_ok": (None if attempt.syndrome_ok is None
                        else bool(attempt.syndrome_ok)),
        "crc_ok": (None if attempt.crc_ok is None
                   else bool(attempt.crc_ok)),
        "n_erased": int(attempt.n_erased),
        "certified_new": bool(attempt.certified_new),
    }


def _certificates(
    session: receiver.ReceiverSession,
    label: str,
) -> dict[tuple[int, int, int], tuple[int, bytes, str]]:
    rows = {}
    for raw_key, outcome in session.decode.tiles.items():
        if outcome.state != "certified":
            continue
        if outcome.user_bits is None:
            raise ValueError(
                f"source {label!r} has a certificate without user bits")
        key = tuple(int(value) for value in raw_key)
        bits = np.asarray(outcome.user_bits)
        if (bits.ndim != 1 or bits.size == 0
                or not np.all((bits == 0) | (bits == 1))):
            raise ValueError(
                f"source {label!r} has malformed certified bits at {key}")
        expected_bits = ldpc.tile_user_capacity(
            session.decode.shorten_mask(key[1:]),
            session.decode.ldpc_spec)
        if bits.size != expected_bits:
            raise ValueError(
                f"source {label!r} has {bits.size} certified bits at "
                f"{key}; expected {expected_bits}")
        rows[key] = (
            int(bits.size),
            np.packbits(
                bits.astype(np.uint8, copy=False),
                bitorder=PACK_BITORDER).tobytes(),
            str(outcome.certified_by),
        )
    return rows


def _certificate_attempts(
    session: receiver.ReceiverSession,
    label: str,
) -> dict[tuple[int, int, int], dict]:
    rows = {}
    for attempt in session.attempts:
        if not attempt.certified_new:
            continue
        key = (int(attempt.page), int(attempt.tile_yx[0]),
               int(attempt.tile_yx[1]))
        if key in rows:
            raise ValueError(
                f"source {label!r} has duplicate certificate "
                f"attempts at {key}")
        rows[key] = _attempt_provenance(attempt)
    return rows


def _compact_source(
    source: SourceSpec,
    session: receiver.ReceiverSession,
    *,
    file_sha256: str,
    file_size: int,
) -> LoadedSource:
    """Validate one full session, then retain only merge-required records."""
    if (session.envelope.implementation_sha256
            != receiver.implementation_fingerprints()):
        raise ValueError(
            f"{source.path} was created by a different receiver "
            "implementation")
    if session.attempt_ids != {
            row.attempt_id for row in session.attempts}:
        raise ValueError(f"{source.path} has a corrupt attempt index")
    session.validate_invariants()
    if session.decode.fatal:
        raise ValueError(
            f"source {source.label!r} carries fatal integrity records")

    authoritative = receiver.authoritative_digest(session)
    raw_certificates = _certificates(session, source.label)
    attempts = _certificate_attempts(session, source.label)
    if set(attempts) != set(raw_certificates):
        raise ValueError(
            f"source {source.label!r} has incomplete certificate-attempt "
            "provenance")
    certificates = {
        key: Certificate(
            n_user_bits=n_user_bits,
            user_bits_packed=packed,
            certified_by=certified_by,
            attempt=attempts[key],
        )
        for key, (n_user_bits, packed, certified_by)
        in raw_certificates.items()
    }

    states = payloaddec.full_tile_states(session.decode)
    tile_keys = frozenset(
        tuple(int(value) for value in key) for key in states)
    degenerate_keys = frozenset(
        tuple(int(value) for value in key)
        for key, state in states.items() if state == "degenerate")
    certified_keys = {
        tuple(int(value) for value in key)
        for key, state in states.items() if state == "certified"}
    if certified_keys != set(certificates):
        raise ValueError(
            f"source {source.label!r} has inconsistent full-tile "
            "certificate accounting")
    if certified_keys & degenerate_keys:
        raise ValueError(
            f"source {source.label!r} certifies a degenerate tile")

    crc_calls = int(session.decode.n_attempts)
    bp_iterations = sum(int(row.n_iters) for row in session.attempts)
    envelope = session.envelope
    ordered_capture_ids = tuple(scan.capture_id for scan in session.scans)
    provenance = {
        "label": source.label,
        "state_path": str(source.path),
        "state_file_sha256": file_sha256,
        "state_file_size": file_size,
        "authoritative_sha256": authoritative,
        "state_version": receiver.STATE_VERSION,
        "algorithm_id": envelope.algorithm_id,
        "format_id": envelope.format_id,
        "dpi": envelope.dpi,
        "rate_id": envelope.rate_id,
        "detector_profile": envelope.detector_profile,
        "search_config_sha256": envelope.search_config_sha256,
        "evidence_policy": envelope.evidence_policy,
        "implementation_sha256": dict(
            envelope.implementation_sha256),
        "certified_tiles": len(certificates),
        "crc_calls": crc_calls,
        "bp_iterations": bp_iterations,
        "crc_false_accept_bound": min(
            1.0, crc_calls * payloaddec.CRC_FALSE_ACCEPT),
        "scans": [{
            "scan_id": scan.scan_id,
            "capture_id": scan.capture_id,
            "source_path": scan.source_path,
            "source_sha256": scan.source_sha256,
            "source_size": scan.source_size,
        } for scan in session.scans],
    }
    return LoadedSource(
        label=source.label,
        path=source.path,
        file_sha256=file_sha256,
        file_size=file_size,
        authoritative_sha256=authoritative,
        compatibility_key=_compatibility_key(envelope),
        compatibility=_compatibility_payload(envelope),
        ordered_capture_ids=ordered_capture_ids,
        certificates=certificates,
        tile_keys=tile_keys,
        degenerate_keys=degenerate_keys,
        crc_calls=crc_calls,
        bp_iterations=bp_iterations,
        provenance=provenance,
    )


def _load_source(source: SourceSpec) -> LoadedSource:
    """Hash, deserialize, validate, and compact one stable open file."""
    with source.path.open("rb") as stream:
        initial = os.fstat(stream.fileno())
        signature = _stat_signature(initial)
        file_sha256 = _stream_sha256(stream)
        if _stat_signature(os.fstat(stream.fileno())) != signature:
            _raise_changed(source.path)

        stream.seek(0)
        payload = pickle.load(stream)
        if _stat_signature(os.fstat(stream.fileno())) != signature:
            _raise_changed(source.path)
        if (not isinstance(payload, dict)
                or payload.get("magic") != receiver.STATE_MAGIC):
            raise ValueError(f"{source.path} is not an e023b session")
        if int(payload.get("version", -1)) != receiver.STATE_VERSION:
            raise ValueError(
                f"e023b state version {payload.get('version')} != "
                f"{receiver.STATE_VERSION}")
        session = payload.get("session")
        if not isinstance(session, receiver.ReceiverSession):
            raise ValueError(f"{source.path} has an invalid e023b payload")

        compact = _compact_source(
            source, session,
            file_sha256=file_sha256, file_size=int(initial.st_size))
        del session
        del payload

        repeated_sha256 = _stream_sha256(stream)
        if (_stat_signature(os.fstat(stream.fileno())) != signature
                or repeated_sha256 != file_sha256):
            _raise_changed(source.path)
        try:
            path_signature = _stat_signature(source.path.stat())
        except OSError as exc:
            raise ValueError(f"{source.path} changed while reading") from exc
        if path_signature != signature:
            _raise_changed(source.path)
    return compact


def load_sources(specs: list[SourceSpec]) -> list[LoadedSource]:
    """Load and compact states one at a time; reject duplicate identities."""
    if len(specs) < 2:
        raise ValueError("certificate union requires at least two --source states")
    labels = [source.label for source in specs]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate source label")
    paths = [source.path for source in specs]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate source state path")

    loaded: list[LoadedSource] = []
    seen_authoritative: dict[str, str] = {}
    for index, source in enumerate(specs):
        compact = _load_source(source)
        previous = seen_authoritative.get(compact.authoritative_sha256)
        if previous is not None:
            raise ValueError(
                f"duplicate source state: {source.label!r} and {previous!r} "
                "have the same authoritative digest")
        seen_authoritative[compact.authoritative_sha256] = source.label
        loaded.append(compact)
        if index + 1 < len(specs):
            # Receiver states may contain large cyclic object graphs.  Ensure
            # an unreachable graph cannot survive into the next source load.
            gc.collect()
    return loaded


def validate_compatible(sources: list[LoadedSource]) -> None:
    """Require a common code geometry and aligned physical captures."""
    if len(sources) < 2:
        raise ValueError("certificate union requires at least two sources")
    labels = [source.label for source in sources]
    if len(labels) != len(set(labels)):
        raise ValueError("duplicate source label")
    reference = sources[0]
    expected = reference.compatibility_key
    expected_captures = reference.ordered_capture_ids
    if not expected_captures:
        raise ValueError(f"source {reference.label!r} contains no scans")
    for source in sources[1:]:
        if source.compatibility_key != expected:
            raise ValueError(
                f"source {source.label!r} is incompatible with "
                f"{reference.label!r}: format/seed/geometry/pages/rate differ")
        if source.ordered_capture_ids != expected_captures:
            raise ValueError(
                f"source {source.label!r} does not have the same ordered "
                f"capture IDs as {reference.label!r}")


def _tile_statistics(
    sources: list[LoadedSource],
) -> tuple[dict, dict[str, dict]]:
    """Validate the common tile universe and count each source's frontier."""
    reference_keys: set[tuple[int, int, int]] | None = None
    reference_degenerate: set[tuple[int, int, int]] | None = None
    per_source = {}
    for source in sources:
        keys = set(source.tile_keys)
        degenerate = set(source.degenerate_keys)
        certified = set(source.certificates)
        if reference_keys is None:
            reference_keys = keys
            reference_degenerate = degenerate
        elif keys != reference_keys:
            raise ValueError(
                f"source {source.label!r} has a different tile universe")
        elif degenerate != reference_degenerate:
            raise ValueError(
                f"source {source.label!r} has a different degenerate-tile "
                "classification")
        nondegenerate = keys - degenerate
        if not certified <= nondegenerate:
            raise ValueError(
                f"source {source.label!r} certifies a degenerate tile")
        per_source[source.label] = {
            "total": len(keys),
            "degenerate": len(degenerate),
            "nondegenerate": len(nondegenerate),
            "unresolved_nondegenerate": len(nondegenerate - certified),
        }

    assert reference_keys is not None and reference_degenerate is not None
    nondegenerate = reference_keys - reference_degenerate
    return ({
        "total": len(reference_keys),
        "degenerate": len(reference_degenerate),
        "nondegenerate": len(nondegenerate),
    }, per_source)


def _source_provenance(source: LoadedSource, certified: int) -> dict:
    if certified != len(source.certificates):
        raise ValueError(
            f"source {source.label!r} has inconsistent compact certificate "
            "accounting")
    return dict(source.provenance)


def build_union(sources: list[LoadedSource]) -> dict:
    """Build a deterministic, JSON-ready certificate-union payload."""
    validate_compatible(sources)
    source_certificates = {
        source.label: source.certificates for source in sources}
    tile_universe, source_tile_statistics = _tile_statistics(sources)
    labels = [source.label for source in sources]
    all_keys = sorted({
        key for rows in source_certificates.values() for key in rows})

    certificates = []
    support_by_key: dict[tuple[int, int, int], tuple[str, ...]] = {}
    for key in all_keys:
        support = tuple(label for label in labels
                        if key in source_certificates[label])
        reference_label = support[0]
        reference = source_certificates[reference_label][key]
        for label in support[1:]:
            candidate = source_certificates[label][key]
            if (candidate.n_user_bits != reference.n_user_bits
                    or candidate.user_bits_packed
                    != reference.user_bits_packed):
                raise ValueError(
                    f"conflicting certified user bits at {key}: "
                    f"{reference_label!r} vs {label!r}")
        support_by_key[key] = support
        certificates.append({
            "page": key[0],
            "tile_yx": [key[1], key[2]],
            "n_user_bits": reference.n_user_bits,
            "user_bits_packed_hex": reference.user_bits_packed.hex(),
            "pack_bitorder": PACK_BITORDER,
            "sources": [{
                "label": label,
                "certified_by": (
                    source_certificates[label][key].certified_by),
                "attempt": source_certificates[label][key].attempt,
            } for label in support],
        })

    support_histogram = {
        str(count): sum(len(support) == count
                        for support in support_by_key.values())
        for count in range(1, len(sources) + 1)
    }
    per_source = {}
    source_by_label = {source.label: source for source in sources}
    for label in labels:
        owned = [key for key, support in support_by_key.items()
                 if label in support]
        per_source[label] = {
            "certified": len(owned),
            "shared": sum(len(support_by_key[key]) > 1 for key in owned),
            "exclusive": sum(len(support_by_key[key]) == 1 for key in owned),
            "certified_user_bits": sum(
                source_certificates[label][key].n_user_bits
                for key in owned),
            "bp_iterations": source_by_label[label].bp_iterations,
            "tiles": source_tile_statistics[label],
        }

    pairwise = []
    for left_index, left in enumerate(labels):
        left_keys = set(source_certificates[left])
        for right in labels[left_index + 1:]:
            right_keys = set(source_certificates[right])
            pairwise.append({
                "left": left,
                "right": right,
                "intersection": len(left_keys & right_keys),
                "left_only": len(left_keys - right_keys),
                "right_only": len(right_keys - left_keys),
                "union": len(left_keys | right_keys),
            })

    reference = sources[0].compatibility
    total_crc_calls = sum(source.crc_calls for source in sources)
    total_bp_iterations = sum(source.bp_iterations for source in sources)
    merged_keys = set(all_keys)
    merged_tile_statistics = {
        **tile_universe,
        "unresolved_nondegenerate": (
            tile_universe["nondegenerate"] - len(merged_keys)),
    }
    return {
        "magic": UNION_MAGIC,
        "version": UNION_VERSION,
        "algorithm": UNION_ALGORITHM,
        "implementation": {
            "merge_script_sha256": hashlib.sha256(
                Path(__file__).read_bytes()).hexdigest(),
            "receiver_sha256": hashlib.sha256(
                Path(receiver.__file__).read_bytes()).hexdigest(),
        },
        "compatibility": {
            **reference,
            "ordered_capture_ids": list(
                sources[0].ordered_capture_ids),
        },
        "provenance": {
            "sources": [
                _source_provenance(
                    source, len(source_certificates[source.label]))
                for source in sources],
        },
        "statistics": {
            "source_count": len(sources),
            "merged_certificates": len(certificates),
            "merged_user_bits": sum(
                int(row["n_user_bits"]) for row in certificates),
            "shared_certificates": sum(
                len(support) > 1 for support in support_by_key.values()),
            "exclusive_certificates": sum(
                len(support) == 1 for support in support_by_key.values()),
            "all_sources_certificates": sum(
                len(support) == len(sources)
                for support in support_by_key.values()),
            "support_histogram": support_histogram,
            "per_source": per_source,
            "pairwise": pairwise,
            "tiles": merged_tile_statistics,
            "total_crc_calls": total_crc_calls,
            "total_bp_iterations": total_bp_iterations,
            "crc_false_accept_per_call": payloaddec.CRC_FALSE_ACCEPT,
            "conservative_crc_false_accept_bound": min(
                1.0, total_crc_calls * payloaddec.CRC_FALSE_ACCEPT),
            "crc_bound_rule": "min(1, total_crc_calls * 2^-32)",
        },
        "certificates": certificates,
    }


def write_json_atomic(path: Path, payload: dict,
                      *, source_paths: tuple[Path, ...] = ()) -> None:
    """Write canonical JSON with atomic replacement of any prior output."""
    target = path.expanduser().resolve()
    if target in source_paths:
        raise ValueError("output path must not overwrite a source state")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    try:
        descriptor, raw_tmp = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        tmp = Path(raw_tmp)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if "tmp" in locals():
            tmp.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", action="append", required=True, metavar="LABEL=STATE",
        help="labeled current E023b state; repeat for each correlated view")
    parser.add_argument("--out", required=True, type=Path,
                        help="atomic JSON certificate-union output")
    args = parser.parse_args()
    try:
        specs = [parse_source(value) for value in args.source]
        sources = load_sources(specs)
        payload = build_union(sources)
        write_json_atomic(
            args.out, payload,
            source_paths=tuple(source.path for source in sources))
    except (OSError, ValueError, pickle.UnpicklingError, EOFError) as exc:
        parser.error(str(exc))

    stats = payload["statistics"]
    print(
        f"merged={stats['merged_certificates']} "
        f"shared={stats['shared_certificates']} "
        f"exclusive={stats['exclusive_certificates']} "
        f"unresolved={stats['tiles']['unresolved_nondegenerate']} "
        f"crc_calls={stats['total_crc_calls']} "
        f"bp_iterations={stats['total_bp_iterations']} "
        f"crc_bound={stats['conservative_crc_false_accept_bound']:.6g} "
        f"out={args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

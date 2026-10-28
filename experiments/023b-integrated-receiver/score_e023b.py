#!/usr/bin/env python
"""Score an E023b state against a fountain-volume manifest.

E023b itself deliberately stops at syndrome+CRC-certified LDPC tiles.  This
tool performs the read-only volume handoff needed to evaluate an encoded
sheet:

1. validate that the state and manifest describe the same complete format;
2. separate fountain-bearing interior certificates from inert edge tiles;
3. run the declared fountain-v1 rank solve;
4. verify recovered length and SHA-256 when the volume closes.

An under-ranked state is a valid, successful score with ``recovered=false``.
A solved payload whose SHA-256 disagrees with the manifest is an integrity
failure and exits nonzero after writing the requested forensic report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import fountain, ldpc, receiver  # noqa: E402
from paperholo.formats import FormatDescriptor  # noqa: E402


SCORE_MAGIC = "e023b-volume-score-v1"
SCORE_VERSION = 1
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ManifestSpec:
    """Validated manifest facts needed by the volume scorer."""

    path: Path
    file_sha256: str
    raw: dict
    profile: str
    descriptor: FormatDescriptor
    volume: fountain.VolumeSpec
    expected_data_sha256: str


def _mapping(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be a JSON object")
    return value


def _integer(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{where} must be an integer")
    return int(value)


def _text(value, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where} must be a non-empty string")
    return value


def _expect_equal(actual, expected, where: str) -> None:
    if actual != expected:
        raise ValueError(
            f"{where} mismatch: expected {expected!r}, got {actual!r}")


def load_manifest(path: Path | str) -> ManifestSpec:
    """Load and fully validate one E018b-style volume manifest."""
    source = Path(path).expanduser().resolve()
    raw_bytes = source.read_bytes()
    try:
        payload = _mapping(json.loads(raw_bytes), "manifest")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source}: invalid JSON: {exc}") from exc

    format_row = _mapping(payload.get("format"), "manifest.format")
    volume_row = _mapping(payload.get("volume"), "manifest.volume")
    payload_row = _mapping(payload.get("payload"), "manifest.payload")

    format_id = _text(
        format_row.get("format_id"), "manifest.format.format_id")
    seed_text = _text(format_row.get("seed"), "manifest.format.seed")
    try:
        seed = seed_text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("manifest.format.seed must be ASCII") from exc
    top_seed = payload.get("seed")
    if top_seed is not None:
        _expect_equal(
            _text(top_seed, "manifest.seed"), seed_text, "manifest.seed")

    page_cells = format_row.get("page_cells_yx")
    if (not isinstance(page_cells, list) or len(page_cells) != 2):
        raise ValueError(
            "manifest.format.page_cells_yx must contain [rows, columns]")
    page_cells_yx = tuple(
        _integer(value, f"manifest.format.page_cells_yx[{index}]")
        for index, value in enumerate(page_cells)
    )
    if min(page_cells_yx) < 1:
        raise ValueError("manifest.format.page_cells_yx must be positive")

    rate_id = _text(
        volume_row.get("ldpc_rate_id"), "manifest.volume.ldpc_rate_id")
    _expect_equal(
        _text(
            format_row.get("ldpc_rate_id"),
            "manifest.format.ldpc_rate_id"),
        rate_id,
        "manifest.format.ldpc_rate_id",
    )
    descriptor = FormatDescriptor(
        format_id=format_id,
        seed=seed,
        layout_version=_integer(
            format_row.get("layout_version"),
            "manifest.format.layout_version"),
        encoding_id=_text(
            format_row.get("encoding_id"),
            "manifest.format.encoding_id"),
        page_cells_yx=page_cells_yx,
        plane=_text(format_row.get("plane"), "manifest.format.plane"),
        notes="manifest-derived E023b scoring descriptor",
        ldpc_rate=rate_id,
    )

    if _text(
            volume_row.get("fountain_version"),
            "manifest.volume.fountain_version") != fountain.FOUNTAIN_VERSION:
        raise ValueError(
            "manifest fountain version is unsupported by this scorer")
    n_pages = _integer(
        volume_row.get("n_pages"), "manifest.volume.n_pages")
    data_len = _integer(
        volume_row.get("data_len_bytes"),
        "manifest.volume.data_len_bytes")
    expected_sha = _text(
        volume_row.get("data_sha256"),
        "manifest.volume.data_sha256")
    if not _SHA256_RE.fullmatch(expected_sha):
        raise ValueError(
            "manifest.volume.data_sha256 must be 64 lowercase hex digits")
    _expect_equal(
        _integer(
            payload_row.get("data_len_bytes"),
            "manifest.payload.data_len_bytes"),
        data_len,
        "manifest.payload.data_len_bytes",
    )
    _expect_equal(
        _text(
            payload_row.get("data_sha256"),
            "manifest.payload.data_sha256"),
        expected_sha,
        "manifest.payload.data_sha256",
    )

    vspec = fountain.VolumeSpec(
        n_pages=n_pages,
        data_len_bytes=data_len,
        seed=seed,
        ldpc_rate_id=rate_id,
        compose_spec=descriptor.spec(),
    )
    fountain.volume_geometry(vspec)
    for key, derived in (
        ("k_total", vspec.k_total),
        ("n_symbols_total", vspec.n_symbols_total),
        ("symbol_bits", vspec.symbol_bits),
    ):
        _expect_equal(
            _integer(volume_row.get(key), f"manifest.volume.{key}"),
            derived,
            f"manifest.volume.{key}",
        )

    profile = str(payload.get("profile") or format_id)
    return ManifestSpec(
        path=source,
        file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        raw=payload,
        profile=profile,
        descriptor=descriptor,
        volume=vspec,
        expected_data_sha256=expected_sha,
    )


def _validate_session(session, manifest: ManifestSpec) -> None:
    envelope = session.envelope
    descriptor = manifest.descriptor
    expected_pages = tuple(range(manifest.volume.n_pages))
    expected = (
        descriptor.format_id,
        descriptor.seed,
        descriptor.cell_dots,
        tuple(descriptor.page_cells_yx),
        expected_pages,
        manifest.volume.ldpc_rate_id,
    )
    actual = (
        envelope.format_id,
        bytes(envelope.seed),
        int(envelope.cell_dots),
        tuple(int(value) for value in envelope.page_cells_yx),
        tuple(int(page) for page in envelope.pages),
        envelope.rate_id,
    )
    if actual != expected:
        raise ValueError(
            "state/manifest format mismatch: format id, seed, cell size, "
            "page geometry, legal pages, or LDPC rate differs")
    fatal = list(getattr(session.decode, "fatal", ()))
    if fatal:
        raise ValueError(
            f"state carries fatal integrity records: {fatal[:4]}")


def _full_state_counts(session, manifest: ManifestSpec) -> dict[str, int]:
    """Classify the complete legal tile universe without mutating state."""
    counts: dict[str, int] = {}
    spec = manifest.descriptor.spec()
    ldpc_spec = manifest.volume.ldpc_spec
    for page in range(manifest.volume.n_pages):
        for tile_yx in ldpc.tile_grid(spec.page_cells_yx):
            key = (page, *tile_yx)
            outcome = session.decode.tiles.get(key)
            if outcome is not None and outcome.state != "unobserved":
                state = str(outcome.state)
            else:
                mask = ldpc.tile_shorten_mask(
                    tile_yx, spec, manifest.descriptor.seed)
                state = (
                    "degenerate"
                    if ldpc.tile_user_capacity(mask, ldpc_spec) == 0
                    else "unobserved"
                )
            counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _certified_symbols(session, manifest: ManifestSpec
                       ) -> tuple[dict, int, int]:
    """Return certified fountain symbols and LDPC/inert certificate counts."""
    symbols: dict[tuple[int, int], np.ndarray] = {}
    certified_ldpc = 0
    certified_inert = 0
    vspec = manifest.volume
    spec = manifest.descriptor.spec()

    for raw_key, outcome in sorted(session.decode.tiles.items()):
        if outcome.state != "certified":
            continue
        certified_ldpc += 1
        key = tuple(int(value) for value in raw_key)
        if len(key) != 3:
            raise ValueError(f"malformed certified tile key {raw_key!r}")
        page, ty, tx = key
        if not 0 <= page < vspec.n_pages:
            raise ValueError(f"certified tile {key} lies outside the volume")
        bits = np.asarray(outcome.user_bits)
        if (bits.ndim != 1 or bits.size == 0
                or not np.all((bits == 0) | (bits == 1))):
            raise ValueError(f"certified tile {key} has malformed user bits")
        mask = ldpc.tile_shorten_mask(
            (ty, tx), spec, manifest.descriptor.seed)
        expected_size = ldpc.tile_user_capacity(mask, vspec.ldpc_spec)
        if bits.size != expected_size:
            raise ValueError(
                f"certified tile {key} has {bits.size} user bits; "
                f"expected {expected_size}")
        esi = fountain.esi_of_tile(vspec, page, (ty, tx))
        if esi is None:
            certified_inert += 1
            continue
        if esi in symbols:
            raise ValueError(f"duplicate certified fountain symbol {esi}")
        if bits.size < vspec.symbol_bits:
            raise ValueError(
                f"certified tile {key} carries {bits.size} bits, below "
                f"fountain symbol size {vspec.symbol_bits}")
        symbols[esi] = bits[:vspec.symbol_bits].astype(
            np.uint8, copy=True)
    return symbols, certified_ldpc, certified_inert


def score_session(
    session,
    manifest: ManifestSpec,
    *,
    state_path: Path | str,
    label: str,
) -> tuple[dict, bytes | None]:
    """Score one already-loaded E023b session without changing it."""
    _validate_session(session, manifest)
    symbols, certified_ldpc, certified_inert = _certified_symbols(
        session, manifest)
    recovered, diag = fountain.volume_decode(symbols, manifest.volume)
    blocks = [dict(row) for row in diag["blocks"]]
    rank = sum(int(row["rank"]) for row in blocks)
    rank_shortfall = sum(
        max(0, int(row["needed"]) - int(row["rank"])) for row in blocks)
    expected_len = manifest.volume.data_len_bytes
    actual_sha = (
        None if recovered is None else hashlib.sha256(recovered).hexdigest())
    sha_matches = (
        None if actual_sha is None
        else actual_sha == manifest.expected_data_sha256)
    length_matches = (
        None if recovered is None else len(recovered) == expected_len)
    state_source = Path(state_path).expanduser().resolve()
    state_size = state_source.stat().st_size
    state_counts = _full_state_counts(session, manifest)
    attempts = list(getattr(session, "attempts", ()))
    scans = list(getattr(session, "scans", ()))

    report = {
        "magic": SCORE_MAGIC,
        "version": SCORE_VERSION,
        "label": label,
        "state": {
            "path": str(state_source),
            "file_size": state_size,
            "format_id": session.envelope.format_id,
            "dpi": float(session.envelope.dpi),
            "detector_profile": session.envelope.detector_profile,
            "rate_id": session.envelope.rate_id,
            "crc_calls": int(session.decode.n_attempts),
            "bp_iterations": sum(int(row.n_iters) for row in attempts),
            "scans": [{
                "scan_id": scan.scan_id,
                "capture_id": scan.capture_id,
                "source_path": scan.source_path,
                "source_sha256": scan.source_sha256,
                "source_size": int(scan.source_size),
            } for scan in scans],
        },
        "manifest": {
            "path": str(manifest.path),
            "file_sha256": manifest.file_sha256,
            "profile": manifest.profile,
            "expected_data_len_bytes": expected_len,
            "expected_data_sha256": manifest.expected_data_sha256,
        },
        "tiles": {
            "states": state_counts,
            "total": sum(state_counts.values()),
            "nondegenerate": (
                sum(state_counts.values()) - state_counts.get("degenerate", 0)
            ),
            "certified_ldpc": certified_ldpc,
            "certified_fountain": len(symbols),
            "certified_fountain_inert": certified_inert,
        },
        "fountain": {
            "version": fountain.FOUNTAIN_VERSION,
            "symbols_received": len(symbols),
            "symbols_total": manifest.volume.n_symbols_total,
            "symbol_yield": (
                len(symbols) / manifest.volume.n_symbols_total
            ),
            "source_symbols_needed": manifest.volume.k_total,
            "rank": rank,
            "rank_fraction": rank / manifest.volume.k_total,
            "rank_shortfall": rank_shortfall,
            "solved_all": bool(diag["solved_all"]),
            "blocks": blocks,
        },
        "payload": {
            "recovered": recovered is not None,
            "verified": bool(
                recovered is not None and length_matches and sha_matches),
            "actual_len_bytes": (
                None if recovered is None else len(recovered)),
            "actual_sha256": actual_sha,
            "length_matches": length_matches,
            "sha256_matches": sha_matches,
        },
    }
    return report, recovered


def write_json_atomic(path: Path | str, payload: dict) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, target)


def write_bytes_atomic(path: Path | str, payload: bytes) -> None:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, target)


def validate_output_paths(
    state: Path | str,
    manifest: Path | str,
    *,
    report: Path | str | None,
    recovered: Path | str | None,
) -> None:
    """Refuse output aliases that could destroy an authoritative input."""
    inputs = {
        Path(state).expanduser().resolve(),
        Path(manifest).expanduser().resolve(),
    }
    outputs = [
        Path(value).expanduser().resolve()
        for value in (report, recovered) if value is not None
    ]
    if any(path in inputs for path in outputs):
        raise ValueError(
            "score outputs must not overwrite the state or manifest")
    if len(outputs) != len(set(outputs)):
        raise ValueError(
            "--out and --recovered-out must name different files")


def _print_summary(report: dict) -> None:
    tiles = report["tiles"]
    fountain_row = report["fountain"]
    payload = report["payload"]
    if payload["verified"]:
        verdict = "RECOVERED + SHA PASS"
    elif payload["recovered"]:
        verdict = "RECOVERED + SHA FAIL"
    else:
        verdict = "OPEN"
    print(
        f"{report['label']}: {verdict}; "
        f"LDPC {tiles['certified_ldpc']}/{tiles['nondegenerate']}, "
        f"symbols {fountain_row['symbols_received']}/"
        f"{fountain_row['symbols_total']}, "
        f"rank {fountain_row['rank']}/"
        f"{fountain_row['source_symbols_needed']} "
        f"(shortfall {fountain_row['rank_shortfall']})"
    )
    print(
        f"  dpi={report['state']['dpi']:g} "
        f"detector={report['state']['detector_profile']} "
        f"crc_calls={report['state']['crc_calls']} "
        f"bp_iterations={report['state']['bp_iterations']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="current E023b state pickle")
    parser.add_argument("manifest", type=Path,
                        help="matching emitted-sheet manifest JSON")
    parser.add_argument("--label", default=None,
                        help="report label; defaults to the state stem")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the complete score as JSON")
    parser.add_argument(
        "--recovered-out", type=Path, default=None,
        help="atomically write payload bytes only if the volume closes")
    parser.add_argument(
        "--require-recovered", action="store_true",
        help="exit 4 when the state is valid but still under-ranked")
    args = parser.parse_args()

    try:
        validate_output_paths(
            args.state, args.manifest,
            report=args.out, recovered=args.recovered_out)
        manifest = load_manifest(args.manifest)
        session = receiver.load_session(args.state)
        report, recovered = score_session(
            session,
            manifest,
            state_path=args.state,
            label=args.label or args.state.stem,
        )
        if args.out is not None:
            write_json_atomic(args.out, report)
        if args.recovered_out is not None:
            if recovered is None:
                print(
                    f"  payload open; {args.recovered_out} left untouched")
            elif report["payload"]["verified"]:
                write_bytes_atomic(args.recovered_out, recovered)
                print(f"  recovered payload {args.recovered_out}")
    except (OSError, ValueError, pickle.UnpicklingError, EOFError) as exc:
        parser.error(str(exc))

    _print_summary(report)
    if args.out is not None:
        print(f"  score {args.out}")
    if report["payload"]["recovered"] and not report["payload"]["verified"]:
        return 3
    if args.require_recovered and not report["payload"]["recovered"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

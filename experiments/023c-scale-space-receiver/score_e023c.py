#!/usr/bin/env python
"""Read-only fountain scorer for an E023c certificate portfolio.

Unlike the receiver's optional completion policy, this audit may attach a
matching manifest after acquisition.  It never resumes captures or writes
receiver state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import cascade_state  # noqa: E402
import completion  # noqa: E402


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _validate_outputs(args: argparse.Namespace) -> None:
    inputs = {args.state.resolve(), args.manifest.resolve()}
    outputs = [
        path.resolve()
        for path in (args.out, args.recovered_out)
        if path is not None
    ]
    if any(path in inputs for path in outputs):
        raise ValueError("score outputs must not overwrite state or manifest")
    if len(outputs) != len(set(outputs)):
        raise ValueError("--out and --recovered-out must differ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--recovered-out", type=Path)
    args = parser.parse_args()

    try:
        _validate_outputs(args)
        session = cascade_state.load_session(args.state)
        manifest = completion.load_manifest(args.manifest)
        if manifest.descriptor.format_id != session.envelope.format_id:
            raise ValueError("manifest format differs from E023c state")
        if manifest.descriptor.ldpc_rate != session.envelope.rate_id:
            raise ValueError("manifest LDPC rate differs from E023c state")
        if manifest.volume.n_pages != len(session.envelope.pages):
            raise ValueError("manifest page count differs from E023c state")
        if tuple(session.envelope.pages) != tuple(range(manifest.volume.n_pages)):
            raise ValueError("state pages do not match manifest logical pages")

        certificates = {
            tuple(key): row.user_bits()
            for key, row in session.certificate_union.items()
        }
        report, recovered = completion.evaluate(certificates, manifest)
        report["state"] = {
            "path": str(args.state.resolve()),
            "status": session.status,
            "captures": len(session.captures),
            "authoritative_sha256": cascade_state.authoritative_digest(session),
        }
        if args.out is not None:
            _write_atomic(
                args.out,
                (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(),
            )
        if args.recovered_out is not None and recovered is not None:
            _write_atomic(args.recovered_out, recovered)

        cert = report["certificates"]
        fountain = report["fountain"]
        payload = report["payload"]
        verdict = (
            "RECOVERED + SHA PASS" if payload["verified"]
            else "RECOVERED + SHA FAIL" if payload["recovered"]
            else "OPEN"
        )
        print(
            f"E023c: {verdict}; LDPC {cert['certified_ldpc']}, "
            f"symbols {fountain['symbols_received']}/{fountain['symbols_total']}, "
            f"rank {fountain['rank']}/{fountain['source_symbols_needed']} "
            f"(shortfall {fountain['rank_shortfall']})"
        )
        return 0 if payload["verified"] else 4 if not payload["recovered"] else 3
    except Exception as exc:
        print(f"E023c score failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

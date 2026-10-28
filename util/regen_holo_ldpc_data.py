#!/usr/bin/env python
"""The paperholo -> holo LDPC provenance bridge.

Regenerates src/holo/core/ldpc/data/<rate>.json — the six frozen e-IRA
mother codes of holo format v1 — by running paperholo's LIVE seeded
construction (src/paperholo/ldpc.py build_code: the normative record,
incl. the falsification history in its docstring) and writing the
winning block descriptions as transparent, diffable JSON.

This is the documented answer to "how were the holo LDPC matrices made,
and can we still make them?": run this script. It verifies the live
construction against paperholo's golden anchors (tests/test_ldpc.py
H_SHA) before writing, and its output is byte-deterministic — rerunning
on an unchanged world reproduces the committed files exactly. holo's own
format pin is INDEPENDENT of this script: golden edge digests over the
expanded matrices live in tests/holo/test_holo_ldpc.py (bump-don't-edit;
a mismatch there is a format fork).

Run from the repo root:  env/bin/python util/regen_holo_ldpc_data.py
(read-verify only: --check)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from paperholo import ldpc  # noqa: E402
import test_ldpc as anchors  # noqa: E402  (paperholo golden H shas)

DATA_DIR = ROOT / "src" / "holo" / "core" / "ldpc" / "data"


def code_document(rid: str, code) -> dict:
    spec = code.spec
    return {
        "comment": ("frozen e-IRA mother code — holo format v1 (F5). "
                    "PROVENANCE: paperholo ldpc.py seeded construction "
                    "(normative docstring incl. the measured "
                    "falsification history), built exp 013 2026-07-08; "
                    "regenerate/verify with util/regen_holo_ldpc_data.py; "
                    "format pin = tests/holo/test_holo_ldpc.py goldens"),
        "rate_id": rid,
        "n_bits": spec.n_bits,
        "z": spec.z,
        "k_bits": spec.k_bits,
        "gap_min": spec.gap_min,
        "heavy_deg": spec.heavy_deg,
        "restart": int(code.restart),
        "pi": code.pi.tolist(),
        "heavy_rows": code.heavy_rows.tolist(),
        "heavy_shifts": code.heavy_shifts.tolist(),
        "light_rows": code.light_rows.tolist(),
        "light_shifts": code.light_shifts.tolist(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="verify committed files match a fresh "
                         "regeneration; write nothing")
    args = ap.parse_args(argv)
    fail = 0
    for rid, spec in ldpc.LDPC_LADDER.items():
        code = ldpc.build_code(spec)          # the live seeded search
        h = hashlib.sha256(code.edge_chk.tobytes()
                           + code.edge_var.tobytes()).hexdigest()
        if h != anchors.H_SHA[rid]:
            print(f"{rid}: LIVE CONSTRUCTION DIVERGED from the paperholo "
                  f"golden ({h[:16]}… != {anchors.H_SHA[rid][:16]}…) — "
                  f"refusing to write")
            fail += 1
            continue
        text = json.dumps(code_document(rid, code), indent=1,
                          sort_keys=True) + "\n"
        path = DATA_DIR / f"{rid}.json"
        if args.check:
            ok = path.exists() and path.read_text() == text
            print(f"{rid}: construction MATCHES golden; file "
                  f"{'MATCHES' if ok else 'DIFFERS/MISSING'}")
            fail += 0 if ok else 1
        else:
            path.write_text(text)
            print(f"{rid}: verified vs golden, wrote {path.name} "
                  f"({len(text):,} bytes)")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

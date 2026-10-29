# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/codes.py
"""Register every code (existing six + candidates + variants) into holo's
construct.LADDER / _CODE_CACHE at import time, so the PRODUCTION decoder
(holo.core.ldpc.decode) serves all of them.  Harness-only; the repo is
untouched.  Every worker process imports this module."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from holo.core.ldpc import construct  # noqa: E402

N = construct.N_BITS
EXISTING = ["r0547", "r0550", "r0625", "r0700", "r0775", "r0850"]
CANDIDATES = ["r0250", "r0297", "r0313", "r0391", "r0406", "r0469"]
VARIANTS = ["r0313-h14", "r0313-f50", "r0391-h14", "r0391-f50"]
ALL = EXISTING + CANDIDATES + VARIANTS


def register() -> None:
    for rid in CANDIDATES + VARIANTS:
        if rid in construct._CODE_CACHE:
            continue
        d = json.loads((WORK / "data" / f"{rid}.json").read_text())
        construct.LADDER[rid] = construct.LdpcSpec(rid, int(d["k_bits"]), heavy_deg=int(d["heavy_deg"]))
        construct._CODE_CACHE[rid] = construct.load_code(rid, data_dir=WORK / "data")
    for rid in EXISTING:
        construct.load_code(rid)          # warm the cache from the package data


register()


def spec(rid: str) -> construct.LdpcSpec:
    return construct.LADDER[rid]


def code(rid: str) -> construct.Code:
    return construct.load_code(rid)

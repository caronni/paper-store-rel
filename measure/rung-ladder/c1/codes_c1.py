# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/codes_c1.py
"""Register the c1 codes (c1/data) plus the previous run's continuity codes
(r0250, r0313, r0313-f50 from ../data, via the old harness codes module) into
holo's construct.LADDER / _CODE_CACHE at import time, exactly as harness/codes.py
does.  Every worker imports this module (run_task below is what the pool pickles)."""
from __future__ import annotations
import json, sys
from pathlib import Path
C1 = Path(__file__).resolve().parent
sys.path.insert(0, str(C1.parent / "harness"))
import codes  # noqa: E402  (registers existing + previous candidates/variants)
import channels as ch  # noqa: E402
from holo.core.ldpc import construct  # noqa: E402

CANDIDATES = ["r0203", "r0219", "r0234", "r0281"]
VARIANTS = ["r0203-f50", "r0234-f50", "r0250-f50", "r0281-f50", "r0203-f70", "r0250-f70"]
NEW = CANDIDATES + VARIANTS
CONTINUITY = ["r0250", "r0313", "r0313-f50"]          # results reused from ../results.json


def register() -> None:
    for rid in NEW:
        if rid in construct._CODE_CACHE:
            continue
        d = json.loads((C1 / "data" / f"{rid}.json").read_text())
        construct.LADDER[rid] = construct.LdpcSpec(rid, int(d["k_bits"]), heavy_deg=int(d["heavy_deg"]))
        construct._CODE_CACHE[rid] = construct.load_code(rid, data_dir=C1 / "data")


register()


def run_task(rid, channel, params, t0, n):
    return ch.run_task(rid, channel, params, t0, n)

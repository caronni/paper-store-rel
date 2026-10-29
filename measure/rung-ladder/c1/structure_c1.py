# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/structure_c1.py
"""Structural stats for the c1 codes via the old harness's structure.stats (unchanged)
-> c1/structure-c1.json.  Continuity rows come from ../structure.json."""
from __future__ import annotations
import json, sys
from pathlib import Path
C1 = Path(__file__).resolve().parent
sys.path.insert(0, str(C1))
import codes_c1  # noqa: E402  registers
import structure  # noqa: E402  (../harness/structure.py)

if __name__ == "__main__":
    out = {}
    for rid in codes_c1.NEW:
        s = structure.stats(rid); out[rid] = s
        print(rid, {kk: s[kk] for kk in ("n_edges", "chk_deg_min", "chk_deg_max", "n_chk_no_info_edge", "girth_gt4", "min_w1", "min_w2", "n_w2_le8", "pair_seconds")}, flush=True)
    (C1 / "structure-c1.json").write_text(json.dumps(out, indent=1) + "\n")

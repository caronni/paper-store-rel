# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/build_c1.py
"""Build the sub-r0300 c1 candidates with paperholo's FROZEN recipe (build.build_one,
imported from ../harness, unchanged) -> c1/data/<rid>.json + c1/build_log.json.
Recipe: HEAVY_FRAC 0.30, heavy_deg 10. VARIANTS (not the recipe): -f50 = HEAVY_FRAC 0.5,
-f70 = HEAVY_FRAC 0.7, heavy_deg 10 throughout."""
from __future__ import annotations
import json, sys
from pathlib import Path
C1 = Path(__file__).resolve().parent
sys.path.insert(0, str(C1.parent / "harness"))
import build  # noqa: E402  (old harness, reused as-is)

CANDIDATES = [("r0203", 832), ("r0219", 896), ("r0234", 960), ("r0281", 1152)]
VARIANTS = [("r0203-f50", 832, 10, 0.50), ("r0234-f50", 960, 10, 0.50), ("r0250-f50", 1024, 10, 0.50),
            ("r0281-f50", 1152, 10, 0.50), ("r0203-f70", 832, 10, 0.70), ("r0250-f70", 1024, 10, 0.70)]

if __name__ == "__main__":
    out = C1 / "data"; log: list = []
    for rid, k in CANDIDATES:
        build.build_one(rid, k, 10, 0.30, out, log)
    for rid, k, hd, hf in VARIANTS:
        build.build_one(rid, k, hd, hf, out, log)
    (C1 / "build_log.json").write_text(json.dumps(log, indent=1) + "\n")

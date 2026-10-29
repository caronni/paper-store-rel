# Historical record of e017 (017.4, the Canon 4800 re-anchoring), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/probe17_out/canon-p5-verbatim.json with:
#   PYTHONPATH=src:. env/bin/python experiments/017-color-channel/probes/probe17_canon_p5_verbatim.py   (after probe17_canon_prep.py)
"""017.4 helper: the EXACT probe17_level_rates.analyze_scan construction
(quarter-point sampling, own dense warp on the full scan, global affine) on
the 4x-decimated Canon PNG = the flatbed-anchor footing through the Canon.
Writes experiments/017-color-channel/build/probe17_out/canon-p5-verbatim.json (does not touch the
durable probes/ report)."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for rel in ("experiments/004-finalists-checkerboard",
            "experiments/002-calibration-page",
            "experiments/003-modulation-probes",
            "experiments/001-engine-characterization",
            "experiments/017-color-channel/probes", "src"):
    p = str(REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import probe17_level_rates as p5  # noqa: E402

report = {"probe": "P5-verbatim-on-canon-dec1200", "date": "2026-07-10",
          "footing": "e004 A3 7-state c3, cross-tile QDA, genie warp, "
                     "Canon 4800 box-decimated x4 to 2 px/dot "
                     "(anchor construction verbatim)",
          "scans": [p5.analyze_scan(
              str(REPO / "experiments/017-color-channel/build" / "probe17_canon_dec1200.png"))]}
out = REPO / "experiments/017-color-channel/build" / "probe17_out" / "canon-p5-verbatim.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=1))
print(f"wrote {out}", flush=True)

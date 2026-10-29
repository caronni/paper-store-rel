#!/usr/bin/env python
# Historical record of e016, retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates build/campaign_e016.json (the 016 scan A/B/C table) with:
#   PYTHONPATH=src:. env/bin/python experiments/016-arch3-c2-volume/campaign_e016.py --evidence-root DIR [--quick]
"""e016 M281 c2 characterization campaign (014.2-style): 3 Canon-4800
scans of the ONE M281-printed e016 sheet, 15 position-balanced 25.4 mm
blind windows each, global vs ctx detector — two full blind acquires per
window (the wired-path idiom that produced 014.2's A 2.58 / B 2.42 /
C 2.20% AltaLink numbers). Payload-domain BER vs gen-module GT.
-> the M281 twin of the 014.2 AltaLink ladder.

Usage: env/bin/python experiments/016-arch3-c2-volume/campaign_e016.py --evidence-root DIR [--quick]
Output: <--out>/campaign_e016.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import argparse  # noqa: E402
from measure import _evidence  # noqa: E402
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
_AP.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "build")
ARGS, _ = _AP.parse_known_args()
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool="campaign_e016")
ARGS.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/016-arch3-c2-volume"))

from paperholo import formats, fountain  # noqa: E402
import gen_e016  # noqa: E402
import decode_e016 as d16  # noqa: E402  (loader + FMT + GOLD sha)

QUICK = "--quick" in sys.argv
SCANS = {
    "A": EVIDENCE / "paper-store-evidence-paperholo-era/016-arch3-c2-volume/c2/captures/c2-canon-4800grey-a.tiff",
    "B": EVIDENCE / "paper-store-evidence-paperholo-era/016-arch3-c2-volume/c2/captures/c2-canon-4800grey-b-displaced.tiff",
    "C": EVIDENCE / "paper-store-evidence-paperholo-era/016-arch3-c2-volume/c2/captures/c2-canon-4800grey-c-displaced.tiff",
}
POS = [(fy, fx) for fy in (0.3, 0.5, 0.7)
       for fx in (0.2, 0.35, 0.5, 0.65, 0.8)]
if QUICK:
    SCANS = {"A": SCANS["A"]}
    POS = POS[6:8]
_evidence.need(*SCANS.values(), tool="campaign_e016")
WIN_PX = 300 * 8              # 25.4 mm at the 8 px/cell footing

t0 = time.time()
vspec = gen_e016.make_vspec()
framed = fountain.encode_volume_pages(gen_e016.make_data(vspec), vspec)[0]
GT = np.asarray(framed["payload_bits"], np.uint8)


def win_read(win: np.ndarray, detector: str, calibrate: bool) -> dict | None:
    r = formats.acquire_scan(win, candidates=[d16.FMT], scan_dpi=2400.0,
                             detector=detector, calibrate=calibrate)
    if not r.ok:
        return None
    res = r.result
    m = res.payload_llr != 0.0
    hard = (res.payload_llr > 0).astype(np.uint8)
    return {"ber": float(np.mean(hard[m] != GT[res.payload_cell_index[m]])),
            "n_cells": int(m.sum()),
            "erase_frac": float(np.mean(~m)),
            "words_ok": sum(1 for v in res.tile_words.values() if v >= 0),
            "n_words": len(res.tile_words)}


out: dict = {"win_mm": 25.4, "positions": POS, "scans": {}}
for name, path in SCANS.items():
    img, dpi = d16.load_scan_2400(path)
    h, w = img.shape
    print(f"[{time.time()-t0:6.1f}s] scan {name}: {img.shape}")
    rows = []
    for fy, fx in POS:
        y0 = int(fy * h) - WIN_PX // 2
        x0 = int(fx * w) - WIN_PX // 2
        win = np.ascontiguousarray(img[y0:y0 + WIN_PX, x0:x0 + WIN_PX])
        rec: dict = {"pos": (fy, fx)}
        for det, cal in (("global", False), ("ctx", True)):
            rec[det] = win_read(win, det, cal)
        rows.append(rec)
        g, c = rec["global"], rec["ctx"]
        print(f"  ({fy:.2f},{fx:.2f}) "
              f"global {100*g['ber']:.2f}% " if g else
              f"  ({fy:.2f},{fx:.2f}) global FAIL ",
              end="")
        print(f"ctx {100*c['ber']:.2f}% ({c['words_ok']}/{c['n_words']} w)"
              if c else "ctx FAIL")
    out["scans"][name] = {"path": str(path), "windows": rows}
    for det in ("global", "ctx"):
        bers = [r[det]["ber"] for r in rows if r[det]]
        if bers:
            print(f"  {name} {det}: n={len(bers)}/{len(rows)} "
                  f"median {100*float(np.median(bers)):.2f}% "
                  f"mean {100*float(np.mean(bers)):.2f}% "
                  f"max {100*float(np.max(bers)):.2f}%")

(ARGS.out / "campaign_e016.json").write_text(json.dumps(out, indent=2))
print(f"[{time.time()-t0:6.1f}s] -> {ARGS.out / 'campaign_e016.json'}")

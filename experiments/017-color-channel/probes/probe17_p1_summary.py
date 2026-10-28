#!/usr/bin/env python
"""P1-stagea-luma-margin cross-dataset summary table (reads probe17_out/*.json
written by probe17_stagea_luma.py)."""
import json
from pathlib import Path

import numpy as np
from scipy.stats import binom

OUT = Path("scratch/probe17_out")
DATASETS = [
    ("calpage_home", "CAL-1 state8 M281 home (day-1, genie, 2px/dot)"),
    ("calpage_xerox", "CAL-1 state8 AltaLink print (genie, 2px/dot)"),
    ("e004_home", "e004 A3 x16 M281 home (day-2, genie, 2px/dot)"),
    ("e004_xerox", "e004 A3 x16 AltaLink print (genie, 2px/dot)"),
    ("e006c_s2", "e006c x16 bands M281 STARVED-Y (strip-legal)"),
    ("e006c_s3", "e006c scan-3 replicate (strip-legal)"),
]
CANDS = ["triple_CMY", "CM", "2ink_mix", "anyink_mix", "MY", "CY"]


def wf(p):
    return float(binom.sf(13, 100, p))


def main() -> None:
    for tag, desc in DATASETS:
        f = OUT / f"{tag}.json"
        if not f.exists():
            continue
        wins = json.loads(f.read_text())["run"]["windows"]
        print(f"\n== {desc} [{len(wins)} window(s)] ==")
        print(f"{'dark':<11} {'oracle':>7} {'gmm-all':>8} {'worst-win':>9} "
              f"{'gmm-sites':>9} {'wf(med)':>9} {'wf(worst)':>9}")
        for c in CANDS:
            vals = [w[c] for w in wins.values() if c in w]
            if not vals:
                continue
            om = float(np.median([v["ber_oracle"] for v in vals]))
            gm = float(np.median([v["ber_gmm_all"] for v in vals]))
            gw = float(max(v["worst_gmm_all"] for v in vals))
            sm = float(np.median([v["ber_gmm_sites"] for v in vals
                                  if "ber_gmm_sites" in v]))
            print(f"{c:<11} {om:7.4f} {gm:8.4f} {gw:9.4f} {sm:9.4f} "
                  f"{wf(gm):9.2e} {wf(gw):9.2e}")
        anyw = next(iter(wins.values()))
        lum = anyw["state_mean_luma"]
        order = sorted(lum.items(), key=lambda kv: kv[1])
        print("  luma (first window): "
              + "  ".join(f"{s}:{v:.0f}" for s, v in order))


if __name__ == "__main__":
    main()

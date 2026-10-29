#!/usr/bin/env python
# Historical record of e016, retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates the per-scan alone-certification table (stdout) from build/e016_state.pkl with:
#   PYTHONPATH=src:. env/bin/python experiments/016-arch3-c2-volume/alone_certify_e016.py   (after decode_e016.py)
"""Per-scan-ALONE LDPC certification + fountain verdict (e016): fresh
PageDecodeState per scan (only that scan's evidence), full r0550 pass,
interior-symbol count, volume_decode verdict — does ONE scan recover the
volume? Plus the print-frozen test: pairwise intersections of the
per-scan failed-tile sets in ABSOLUTE tile coordinates.
"""
from __future__ import annotations

import hashlib
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/016-arch3-c2-volume"))

from paperholo import fountain, tilemap  # noqa: E402
import gen_e016  # noqa: E402
import decode_e016 as d16  # noqa: E402

state = pickle.loads(
    (ROOT / "experiments/016-arch3-c2-volume/build/e016_state.pkl")
    .read_bytes())
vspec = gen_e016.make_vspec()

fails: dict[str, set] = {}
t0 = time.time()
for sid, obs in state.scans.items():
    st = tilemap.PageDecodeState(state.spec, state.seed, page=state.page)
    st.scans[sid] = obs
    counts = st.decode_tiles("r0550", policy="best_scan")
    syms = fountain.tiles_to_symbols(st.certified_results(), vspec)
    data, diag = fountain.volume_decode(syms, vspec)
    ok = (data is not None
          and hashlib.sha256(data).hexdigest() == d16.GOLD_DATA_SHA)
    b = diag["blocks"][0]
    fails[sid] = {t for t, ts in st.tiles.items() if ts.status == "failed"}
    print(f"[{time.time()-t0:5.1f}s] {sid}:")
    print(f"  certified {counts['certified']} "
          f"(failed {counts['failed']}, low_cov {counts['low_coverage']}); "
          f"interior symbols {len(syms)}/{vspec.n_symbols_total} "
          f"(need {vspec.k_total})")
    print(f"  volume alone: "
          f"{'BYTE-EXACT' if ok else 'NOT decoded'} "
          f"(rank {b['rank']}/{b['needed']}, "
          f"{'systematic' if b['systematic'] else 'GE'})")

sids = list(fails)
print("\nprint-frozen test (failed-tile sets, absolute coords):")
for s in sids:
    print(f"  {s}: {len(fails[s])} failed")
for i in range(len(sids)):
    for j in range(i + 1, len(sids)):
        a, b_ = fails[sids[i]], fails[sids[j]]
        inter = len(a & b_)
        print(f"  {sids[i][-12:]} ∩ {sids[j][-12:]}: {inter} "
              f"(jaccard {inter / max(len(a | b_), 1):.2f})")
common = set.intersection(*fails.values())
print(f"  failed in ALL three: {len(common)}")
rows = sorted({t[0] for t in common})
print(f"  common-fail tile rows: {rows[:40]}{'…' if len(rows) > 40 else ''}")

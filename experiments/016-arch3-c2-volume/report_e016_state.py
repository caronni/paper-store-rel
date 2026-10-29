#!/usr/bin/env python
# Historical record of e016, retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates the e016 layer-1 + coverage report (stdout) from build/e016_state.pkl with:
#   PYTHONPATH=src:. env/bin/python experiments/016-arch3-c2-volume/report_e016_state.py   (after decode_e016.py)
"""e016 layer-1 + coverage report from the accumulated PageDecodeState:
per-scan full-page ctx BER (dedup per-cell mean LLR), word-tile (pilot)
counts, tile coverage sets (>=50% of a tile's payload cells observed),
disjoint + incremental tile contributions in fold order, 3-scan
equal-sum combined BER (the 014.2 F1-then-F6 composition), and the LDPC
certification table. Run AFTER decode_e016.py has folded the scans in.

Usage: env/bin/python experiments/016-arch3-c2-volume/report_e016_state.py
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/016-arch3-c2-volume"))

from paperholo import compose, fountain  # noqa: E402
import gen_e016  # noqa: E402

STATE = ROOT / "experiments/016-arch3-c2-volume/build/e016_state.pkl"
TILE = 64

state = pickle.loads(STATE.read_bytes())
vspec = gen_e016.make_vspec()
framed = fountain.encode_volume_pages(gen_e016.make_data(vspec), vspec)[0]
GT = np.asarray(framed["payload_bits"], np.uint8)

# payload index -> (cell y, cell x) -> tile
spec = state.spec
idx_map = compose.payload_index_map(spec, state.seed)
ys, xs = np.nonzero(idx_map >= 0)
vals = idx_map[idx_map >= 0]
cy = np.empty(vals.size, np.int64)
cx = np.empty(vals.size, np.int64)
cy[vals] = ys
cx[vals] = xs
cap = vals.size
# payload cells per tile (denominator for coverage fractions)
tile_key = (cy // TILE) * 10_000 + (cx // TILE)
tkeys, tcounts = np.unique(tile_key, return_counts=True)
tile_ncells = dict(zip(tkeys.tolist(), tcounts.tolist()))
interior = set(fountain.interior_tiles(spec))


def dense_mean(obs) -> tuple[np.ndarray, np.ndarray]:
    """Dedup window overlap: per-cell MEAN LLR (idx, mean_llr)."""
    s = np.zeros(cap, np.float64)
    n = np.zeros(cap, np.int32)
    np.add.at(s, obs.payload_cell_index, obs.payload_llr)
    np.add.at(n, obs.payload_cell_index, 1)
    idx = np.flatnonzero(n > 0)
    return idx, s[idx] / n[idx]


def ber_of(idx: np.ndarray, llr: np.ndarray) -> tuple[float, float]:
    m = llr != 0.0
    hard = (llr[m] > 0).astype(np.uint8)
    return float(np.mean(hard != GT[idx[m]])), float(np.mean(~m))


def covered_tiles(idx: np.ndarray, min_frac: float = 0.5) -> set:
    k = (cy[idx] // TILE) * 10_000 + (cx[idx] // TILE)
    kk, cc = np.unique(k, return_counts=True)
    return {(int(q) // 10_000, int(q) % 10_000)
            for q, c in zip(kk, cc)
            if c >= min_frac * tile_ncells[int(q)]}


order = list(state.scans)          # fold order
per_scan: dict[str, dict] = {}
for sid in order:
    obs = state.scans[sid]
    idx, llr = dense_mean(obs)
    ber, er = ber_of(idx, llr)
    words = {t for t, ne in obs.tile_words.items() if ne >= 0}
    per_scan[sid] = {"idx": idx, "llr": llr, "tiles": covered_tiles(idx),
                     "words": words}
    print(f"{sid}:")
    print(f"  ctx BER {100*ber:.2f}% on {idx.size} cells "
          f"(erasures {100*er:.2f}%), {obs.n_windows} windows, "
          f"pilot_ber_est {100*obs.pilot_ber_est:.2f}%")
    print(f"  word (pilot) tiles decoded: {len(words)}; "
          f"tiles covered >=50%: {len(per_scan[sid]['tiles'])}")

# disjoint + incremental (fold order)
all_tiles = [per_scan[s]["tiles"] for s in order]
union: set = set()
for i, sid in enumerate(order):
    others = set().union(*(t for j, t in enumerate(all_tiles) if j != i))
    only = all_tiles[i] - others
    gain = all_tiles[i] - union
    union |= all_tiles[i]
    print(f"{sid}: +{len(gain)} new tiles when folded "
          f"(union now {len(union)}); exclusive-to-this-scan "
          f"{len(only)}")
words_union = set().union(*(per_scan[s]["words"] for s in order))
print(f"union: {len(union)} tiles covered >=50% "
      f"({sum(1 for t in union if t in interior)}/{len(interior)} "
      f"interior); word tiles union {len(words_union)}")

# 3-scan equal-sum combined (per-scan mean LLRs summed equally)
dense = np.zeros(cap, np.float64)
seen = np.zeros(cap, bool)
for sid in order:
    dense[per_scan[sid]["idx"]] += per_scan[sid]["llr"]
    seen[per_scan[sid]["idx"]] = True
idx_c = np.flatnonzero(seen)
ber_c, er_c = ber_of(idx_c, dense[idx_c])
print(f"combined equal-sum ({len(order)} scans): BER {100*ber_c:.2f}% "
      f"on {idx_c.size} cells (erasures {100*er_c:.2f}%)")
for sid in order:
    b, e = ber_of(per_scan[sid]["idx"], per_scan[sid]["llr"])
    print(f"  vs {sid} alone {100*b:.2f}%")

# LDPC certification table
s = state.summary()
print(f"\nLDPC map: {s['tiles']} — certified bits {s['certified_bits']}")
prov: dict[str, int] = {}
cov_fail = []
for t, st in state.tiles.items():
    if st.status == "certified" and st.scan_id:
        prov[st.scan_id] = prov.get(st.scan_id, 0) + 1
    if st.status in ("failed", "low_coverage"):
        cov_fail.append((t, st.status, round(st.coverage, 3), st.n_iters))
print(f"certified-tile provenance (best_per_tile winner): {prov}")
if cov_fail:
    print(f"non-certified tiles ({len(cov_fail)}): {cov_fail[:20]}"
          f"{'…' if len(cov_fail) > 20 else ''}")

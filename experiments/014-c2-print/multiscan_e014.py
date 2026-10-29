#!/usr/bin/env python
# Historical record of e014 (014.2), retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates the 014.2 multi-scan table (stdout) + build/multiscan_e014_cache.npz with:
#   PYTHONPATH=src:. env/bin/python experiments/014-c2-print/multiscan_e014.py --evidence-root DIR
"""Multi-scan e014: fold both Canon scans (original + displaced re-placement)
into ONE PageDecodeState-style evidence pool and measure what combining buys
— overall and specifically at the fold band. Policies per the measured
doctrine: per-scan baselines, equal LLR sum (the measured-negative control),
pilot-weighted sum, per-cell max-|LLR|, and per-pilot-tile best scan."""
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
import argparse
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
_AP.add_argument('--out', type=Path, default=Path(__file__).resolve().parent / 'build')
ARGS, _ = _AP.parse_known_args()
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool='multiscan_e014')
ARGS.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'experiments/014-c2-print'))
import tifffile
from paperholo import compose, formats, tilemap
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CD = 2
payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(payload_gt, spec, SEED, 0)
idx_map = compose.payload_index_map(spec, SEED)
# absolute row per payload index (for the fold-band split)
ys, xs = np.nonzero(idx_map >= 0)
row_of = np.empty(int(idx_map.max()) + 1, np.int32)
row_of[idx_map[idx_map >= 0]] = ys

SCANS = [("A", EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-a.tiff'),
         ("B", EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-b-displaced.tiff')]
_evidence.need(*(path for _sid, path in SCANS), tool='multiscan_e014')
cpm = 600 / 25.4 / CD

pds = tilemap.PageDecodeState(spec, SEED, page=0)
for sid, path in SCANS:
    arr = tifffile.TiffFile(str(path)).pages[0].asarray(out='memmap')
    Hs, Ws = arr.shape
    n_ok = 0
    for fy in (0.3, 0.5, 0.7):
        for fx in (0.2, 0.35, 0.5, 0.65, 0.8):
            src = int(25 * cpm * CD * 8)
            y0 = int(Hs * fy) - src // 2
            x0 = int(Ws * fx) - src // 2
            if y0 < 0 or x0 < 0 or y0 + src > Hs or x0 + src > Ws:
                continue
            win = np.asarray(arr[y0:y0 + src, x0:x0 + src], np.float32)
            r = formats.acquire_scan(win, scan_dpi=4800.0)
            if r.ok:
                pds.add_acquire_result(sid, r.result)
                n_ok += 1
    obs = pds.scans.get(sid)
    print(f"scan {sid}: {n_ok} windows ok, "
          f"{obs.payload_cell_index.size if obs else 0} payload cells, "
          f"pilot BER est {obs.pilot_ber_est:.4f}" if obs else
          f"scan {sid}: NO windows", flush=True)

A, B = pds.scans.get("A"), pds.scans.get("B")
assert A is not None and B is not None
common = np.intersect1d(A.payload_cell_index, B.payload_cell_index)
print(f"\ncommon coverage: {common.size} payload cells", flush=True)


def at(obs, idx):
    pos = np.searchsorted(obs.payload_cell_index, idx)
    return obs.payload_llr[pos]


la, lb = at(A, common), at(B, common)
gt = payload_gt[common]
wa = (1 - 2 * A.pilot_ber_est) ** 2
wb = (1 - 2 * B.pilot_ber_est) ** 2
policies = {
    "scan A alone": la,
    "scan B alone": lb,
    "equal LLR sum": la + lb,
    "pilot-weighted sum": wa * la + wb * lb,
    "per-cell max|LLR|": np.where(np.abs(la) >= np.abs(lb), la, lb),
}
rows = row_of[common]
np.savez(str(ARGS.out / 'multiscan_e014_cache.npz'), common=common,
         la=la, lb=lb, gt=gt, rows=rows)
fold = np.abs(rows - 1673) <= 4           # the MEASURED crease rows
print(f"fold-band cells in common set: {int(fold.sum())}")
print(f"\n{'policy':22s} {'BER all':>8s} {'BER fold-band':>14s} {'BER rest':>9s}")
for name, llr in policies.items():
    bits = (llr > 0).astype(np.uint8)
    e = bits != gt
    print(f"{name:22s} {100*e.mean():7.2f}% {100*e[fold].mean():13.2f}% "
          f"{100*e[~fold].mean():8.2f}%", flush=True)

# per-pilot-tile best-scan (tile-level union, the 013/015 doctrine)
P = 60
tile_of = (row_of[common] // P) * 100000 + \
          (np.nonzero(idx_map >= 0)[1][common] // P)
bits_bt = np.empty(common.size, np.uint8)
for t in np.unique(tile_of):
    m = tile_of == t
    ty, tx = int(t // 100000), int(t % 100000)
    qa = A.tile_words.get((ty, tx), -1)
    qb = B.tile_words.get((ty, tx), -1)
    ka = qa if qa >= 0 else 999
    kb = qb if qb >= 0 else 999
    src_llr = la if ka <= kb else lb
    bits_bt[m] = (src_llr[m] > 0)
e = bits_bt != gt
print(f"{'per-tile best scan':22s} {100*e.mean():7.2f}% "
      f"{100*e[fold].mean():13.2f}% {100*e[~fold].mean():8.2f}%", flush=True)

# rescue: cells covered by exactly one scan (fold/veto holes)
only_a = np.setdiff1d(A.payload_cell_index, B.payload_cell_index)
only_b = np.setdiff1d(B.payload_cell_index, A.payload_cell_index)
print(f"\nunion coverage: A-only {only_a.size} + B-only {only_b.size} + "
      f"common {common.size} = "
      f"{only_a.size + only_b.size + common.size} cells "
      f"(single scan A covered {A.payload_cell_index.size})", flush=True)

print("\nper-row error profile across the crease (rows 1660..1690):")
ea, eb = ((la > 0) != gt), ((lb > 0) != gt)
em = ((np.where(np.abs(la) >= np.abs(lb), la, lb) > 0) != gt)
for r0 in range(1660, 1691, 2):
    m = (rows >= r0) & (rows < r0 + 2)
    if m.sum() < 50:
        continue
    print(f"  rows {r0}-{r0+1}: A {100*ea[m].mean():5.1f}%  "
          f"B {100*eb[m].mean():5.1f}%  max|LLR| {100*em[m].mean():5.1f}%  "
          f"(n={int(m.sum())})", flush=True)

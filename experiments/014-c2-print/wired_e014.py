#!/usr/bin/env python
# Historical record of e014 (014.2), retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates the 014.2 wired-path numbers (stdout) with:
#   PYTHONPATH=src:. env/bin/python experiments/014-c2-print/wired_e014.py --evidence-root DIR
"""014.2 wired-path measurement: the ctx detector + PAVA calibration now
INSIDE acquire (detector="ctx", calibrate=True), on the three e014 Canon
scans, plus the F6 adaptive scan-request loop live on real data."""
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
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool='wired_e014')
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
ys_all, _ = np.nonzero(compose.payload_index_map(spec, SEED) >= 0)

SCANS = [
    ("A", EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-a.tiff'),
    ("B", EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-b-displaced.tiff'),
    ("C", EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-c-flattened.tiff'),
]
_evidence.need(*(path for _sid, path in SCANS), tool='wired_e014')
POS = [(fy, fx) for fy in (0.3, 0.5, 0.7) for fx in (0.2, 0.35, 0.5, 0.65, 0.8)]
cpm = 600 / 25.4 / CD
SRC = int(25 * cpm * CD * 8)

pds = tilemap.PageDecodeState(spec, SEED, page=0)
for sid, path in SCANS:
    arr = tifffile.TiffFile(str(path)).pages[0].asarray(out='memmap')
    Hs, Ws = arr.shape
    ncal = nok = 0
    for fy, fx in POS:
        y0, x0 = int(Hs * fy) - SRC // 2, int(Ws * fx) - SRC // 2
        if y0 < 0 or x0 < 0 or y0 + SRC > Hs or x0 + SRC > Ws:
            continue
        win = np.asarray(arr[y0:y0 + SRC, x0:x0 + SRC], np.float32)
        r = formats.acquire_scan(win, scan_dpi=4800.0,
                                 detector="ctx", calibrate=True)
        if r.ok:
            pds.add_acquire_result(sid, r.result)
            nok += 1
            ncal += int(bool(r.result.diagnostics.get("calibrated")))
    snap = pds.note_scan_added()
    obs = pds.scans[sid]
    i, l = obs.payload_cell_index, obs.payload_llr
    ber = float(np.mean((l > 0).astype(np.uint8) != payload_gt[i]))
    ok, why = pds.more_scans_useful()
    print(f"scan {sid}: {nok} windows ({ncal} calibrated), wired-ctx BER "
          f"{100*ber:.2f}% on {i.size} cells; weak_frac "
          f"{snap['weak_frac']:.4f}", flush=True)
    print(f"  controller -> more scans useful? {ok}: {why}", flush=True)

# duplicate scan: fold C in again under a new id (same windows) — the
# controller must flip to diminishing returns
sid, path = SCANS[2]
arr = tifffile.TiffFile(str(path)).pages[0].asarray(out='memmap')
Hs, Ws = arr.shape
for fy, fx in POS:
    y0, x0 = int(Hs * fy) - SRC // 2, int(Ws * fx) - SRC // 2
    if y0 < 0 or x0 < 0 or y0 + SRC > Hs or x0 + SRC > Ws:
        continue
    win = np.asarray(arr[y0:y0 + SRC, x0:x0 + SRC], np.float32)
    r = formats.acquire_scan(win, scan_dpi=4800.0, detector="ctx",
                             calibrate=True)
    if r.ok:
        pds.add_acquire_result("C-dup", r.result)
pds.note_scan_added()
ok, why = pds.more_scans_useful()
print(f"after DUPLICATE of C: more scans useful? {ok}: {why}", flush=True)

# combined calibrated evidence (equal LLR sum = Bayesian-correct on
# calibrated inputs), overall / crease / rest + reliability bins
acc = np.zeros(payload_gt.size)
seen = np.zeros(payload_gt.size, bool)
for sid in ("A", "B", "C"):
    o = pds.scans[sid]
    np.add.at(acc, o.payload_cell_index, o.payload_llr)
    seen[o.payload_cell_index] = True
u = np.flatnonzero(seen)
llr, gt = acc[u], payload_gt[u]
err = (llr > 0).astype(np.uint8) != gt
fold = np.abs(ys_all[u] - 1673) <= 4
print(f"\ncombined A+B+C (wired ctx+cal, equal sum): "
      f"BER {100*err.mean():.2f}% | crease {100*err[fold].mean():.2f}% | "
      f"rest {100*err[~fold].mean():.2f}% | {u.size} cells", flush=True)
print("reliability of combined |LLR| (predicted vs empirical P(correct)):")
for lo, hi in ((0, 2), (2, 4), (4, 8), (8, 16)):
    m = (np.abs(llr) >= lo) & (np.abs(llr) < hi)
    if m.sum() < 500:
        continue
    p_pred = float(np.mean(1 / (1 + np.exp(-np.abs(llr[m])))))
    p_emp = float(np.mean(~err[m]))
    print(f"  |LLR| {lo:2d}-{hi:<2d}: predicted {p_pred:.3f} empirical "
          f"{p_emp:.3f}  (n={int(m.sum())})", flush=True)
print("done", flush=True)

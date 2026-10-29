#!/usr/bin/env python
# Historical record of e014 (014.2), retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates build/campaign_e014.npz (the 014.2 ladder) with:
#   PYTHONPATH=src:. env/bin/python experiments/014-c2-print/campaign_e014.py --evidence-root DIR [--quick]
"""e014 c2 measurement campaign over the 3 Canon scans:
  A = original placement, B = displaced, C = displaced + heavy book (flat).
Everything in isolation and combination:
  - detector: global GMM (baseline) vs 16-context ICM (scanlab.context_detect)
  - scans: A, B, C alone; AB, AC, BC, ABC combined
  - combining: best-single (page pilot quality), equal LLR sum, max|LLR|,
    3-scan hard majority (ABC only)
  - splits: overall / crease band (rows |1673+-4|) / rest; coverage; fold-row
    profile per scan; per-window sharpness (focus check C vs A/B).
Usage: campaign_e014.py [--quick]   (--quick: scan A, 2 windows)
Cache: <--out>/campaign_e014.npz
"""
from __future__ import annotations
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
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool='campaign_e014')
ARGS.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'experiments/014-c2-print'))
sys.path.insert(0, str(ROOT / 'experiments/001-engine-characterization'))
import tifffile
from scipy import ndimage
from paperholo import compose, formats, acquire
from paperholo.modulation import rng
import gen_e014
import scanlab                                    # context_detect (001.4)

QUICK = "--quick" in sys.argv
SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CD = 2
payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
idx_map = compose.payload_index_map(spec, SEED)
ks = compose.payload_keystream(spec, SEED, 0)
ys_all, xs_all = np.nonzero(idx_map >= 0)         # raster order == index order
FOLD_ROW = 1673

SCANS = {
    "A": EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-a.tiff',
    "B": EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-b-displaced.tiff',
    "C": EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-c-flattened.tiff',
}
if QUICK:
    SCANS = {"A": SCANS["A"]}
_evidence.need(*SCANS.values(), tool='campaign_e014')
POS = [(fy, fx) for fy in (0.3, 0.5, 0.7) for fx in (0.2, 0.35, 0.5, 0.65, 0.8)]
if QUICK:
    POS = POS[6:8]
cpm = 600 / 25.4 / CD
SRC = int(25 * cpm * CD * 8)


def window_evidence(win: np.ndarray):
    """Blind acquire one window; return dict with payload indices + BOTH
    detectors' payload LLRs on the SAME registration, plus quality/sharpness."""
    r = formats.acquire_scan(win, scan_dpi=4800.0)
    if not r.ok:
        return None
    res = r.result
    img_c = np.ascontiguousarray(np.rot90(
        r.norm.img[:, ::-1] if res.mirrored else r.norm.img,
        res.orientation_k))
    means = acquire.sample_cell_means(acquire._normalize_refl(img_c),
                                      res.grid, cell_dots=CD)
    # exact cell_bits_blind chain, kept open for the ctx stage
    m = np.asarray(means, np.float64)
    lo, hi = np.quantile(m, (0.02, 0.98))
    z = (hi - m) / max(hi - lo, 1e-6)
    gmm = acquire._fit_gmm_z(z)
    llr_g = acquire._llr_field(z, gmm)
    llr_c = scanlab.context_detect(z, llr_g, gmm)
    oy, ox = res.cell_origin_abs_yx
    idx = res.payload_cell_index
    ly = ys_all[idx] - oy
    lx = xs_all[idx] - ox
    ok = (ly >= 0) & (ly < llr_g.shape[0]) & (lx >= 0) & (lx < llr_g.shape[1])
    idx, ly, lx = idx[ok], ly[ok], lx[ok]
    flip = ks[ys_all[idx], xs_all[idx]] == 1
    pg_ = np.where(flip, -llr_g[ly, lx], llr_g[ly, lx])
    pc_ = np.where(flip, -llr_c[ly, lx], llr_c[ly, lx])
    # sanity: global path must reproduce acquire's own payload bits closely
    rep = float(np.mean((pg_ > 0) == (res.payload_llr[ok] > 0)))
    # sharpness on the raw crop center
    c = win[win.shape[0] // 2 - 750:win.shape[0] // 2 + 750,
            win.shape[1] // 2 - 750:win.shape[1] // 2 + 750] / 255.0
    sharp = float(ndimage.laplace(c).var() / (c.var() + 1e-9))
    q = res.n_word_errors_corrected / max(res.n_tiles_decoded, 1) / 100.0
    return {"idx": idx, "llr_g": pg_, "llr_c": pc_, "repro": rep,
            "sharp": sharp, "pilot_q": q,
            "tiles": (res.n_tiles_decoded, res.n_tiles_attempted)}


def extend(store, idx, llr):
    i0, l0 = store
    ia = np.concatenate([i0, idx]); la = np.concatenate([l0, llr])
    order = np.lexsort((-np.abs(la), ia))
    ia, la = ia[order], la[order]
    keep = np.ones(ia.size, bool); keep[1:] = ia[1:] != ia[:-1]
    return ia[keep], la[keep]


evidence = {}
for sid, path in SCANS.items():
    arr = tifffile.TiffFile(str(path)).pages[0].asarray(out='memmap')
    Hs, Ws = arr.shape
    g = (np.empty(0, np.int64), np.empty(0, np.float64))
    cx = (np.empty(0, np.int64), np.empty(0, np.float64))
    sharps, quals, nok = [], [], 0
    for fy, fx in POS:
        y0, x0 = int(Hs * fy) - SRC // 2, int(Ws * fx) - SRC // 2
        if y0 < 0 or x0 < 0 or y0 + SRC > Hs or x0 + SRC > Ws:
            continue
        win = np.asarray(arr[y0:y0 + SRC, x0:x0 + SRC], np.float32)
        ev = window_evidence(win)
        if ev is None:
            print(f"  {sid} ({fy},{fx}): FAIL", flush=True)
            continue
        nok += 1
        g = extend(g, ev["idx"], ev["llr_g"])
        cx = extend(cx, ev["idx"], ev["llr_c"])
        sharps.append(ev["sharp"]); quals.append(ev["pilot_q"])
        print(f"  {sid} ({fy},{fx}): ok repro {ev['repro']:.3f} "
              f"tiles {ev['tiles'][0]}/{ev['tiles'][1]} "
              f"sharp {ev['sharp']:.4f}", flush=True)
    evidence[sid] = {"g": g, "c": cx, "sharp": float(np.mean(sharps)),
                     "q": float(np.mean(quals)), "nwin": nok}
    print(f"scan {sid}: {nok} windows, {g[0].size} cells, "
          f"mean sharpness {evidence[sid]['sharp']:.4f}, "
          f"pilot BER est {evidence[sid]['q']:.4f}", flush=True)

np.savez(str(ARGS.out / 'campaign_e014.npz'),
         **{f"{s}_{d}_idx": evidence[s][d][0] for s in evidence
            for d in ("g", "c")},
         **{f"{s}_{d}_llr": evidence[s][d][1] for s in evidence
            for d in ("g", "c")})


def ber_split(idx, llr):
    gt = payload_gt[idx]
    e = (llr > 0).astype(np.uint8) != gt
    rows = ys_all[idx]
    fold = np.abs(rows - FOLD_ROW) <= 4
    return (100 * e.mean(),
            100 * e[fold].mean() if fold.any() else float('nan'),
            100 * e[~fold].mean())


print(f"\n{'config':34s} {'BER all':>8s} {'crease':>8s} {'rest':>8s} "
      f"{'cells':>9s}")
for sid in evidence:
    for d, name in (("g", "global"), ("c", "ctx")):
        i, l = evidence[sid][d]
        a, f, r_ = ber_split(i, l)
        print(f"{sid+' alone, '+name:34s} {a:7.2f}% {f:7.2f}% {r_:7.2f}% "
              f"{i.size:9d}", flush=True)

import itertools
for combo in [c for n in (2, 3) for c in
              itertools.combinations(evidence, n)]:
    for d, name in (("g", "global"), ("c", "ctx")):
        stores = [evidence[s][d] for s in combo]
        common = stores[0][0]
        for i2, _ in stores[1:]:
            common = np.intersect1d(common, i2)
        if common.size == 0:
            continue
        L = [s_llr[np.searchsorted(s_idx, common)]
             for s_idx, s_llr in stores]
        L = np.stack(L)
        best_s = min(combo, key=lambda s: evidence[s]["q"])
        bi, bl = evidence[best_s][d]
        lbest = bl[np.searchsorted(bi, common)]
        policies = {"best-single(" + best_s + ")": lbest,
                    "equal-sum": L.sum(0),
                    "max|LLR|": L[np.abs(L).argmax(0),
                                  np.arange(common.size)]}
        if len(combo) == 3:
            policies["majority"] = (L > 0).sum(0) - 1.5
        for pname, llr in policies.items():
            a, f, r_ = ber_split(common, llr)
            print(f"{'+'.join(combo)+' '+name+' '+pname:34s} {a:7.2f}% "
                  f"{f:7.2f}% {r_:7.2f}% {common.size:9d}", flush=True)

# fold-row profile per scan (global detector)
print("\ncrease profile per scan (global det, rows 1664..1684):")
for sid in evidence:
    i, l = evidence[sid]["g"]
    gt = payload_gt[i]; e = (l > 0).astype(np.uint8) != gt
    rows = ys_all[i]
    prof = []
    for r0 in range(1664, 1685, 4):
        m = (rows >= r0) & (rows < r0 + 4)
        prof.append(f"{100*e[m].mean():4.1f}%" if m.sum() > 100 else "  --")
    print(f"  {sid}: {' '.join(prof)}", flush=True)
print("done", flush=True)

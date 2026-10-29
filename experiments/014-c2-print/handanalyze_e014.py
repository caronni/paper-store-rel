#!/usr/bin/env python
# Historical record of e014 (014.2), retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates the 014.2 by-hand attribution (stdout) with:
#   PYTHONPATH=src:. env/bin/python experiments/014-c2-print/handanalyze_e014.py --evidence-root DIR
"""By-hand error attribution on a decoded e014 c2 window: is the ~8% BER
SELF-SYNC residual (sub-cell misregistration -> boundary-straddle errors,
fixable by better tracking) or PHYSICAL CHANNEL (the mark is genuinely
wrong, no sync helps)?

Discriminators:
1. blind BER (self-synced grid) vs GENIE-best global sub-cell offset BER —
   if genie << blind, the blind phase is off (sync problem).
2. PER-CELL offset robustness: a cell wrong at the grid point but right at
   some |offset| <= 1/3 cell = sync-recoverable; wrong at ALL offsets in
   that neighborhood = channel error.
3. ink asymmetry: miss (GT ink -> read white = dropout/closure) vs false
   alarm (GT white -> read ink = bleed/gain) — c2's documented failure is
   the 2-dot-white closure.
4. spatial structure + a few actual pixel patches at 16 px/cell.
"""
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
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool='handanalyze_e014')
ARGS.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'experiments/014-c2-print'))
import tifffile
from paperholo import compose, scannorm, acquire
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CD = 2
payload_gt = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(payload_gt, spec, SEED, page=0)
GT, PM = cp.cell_values, cp.pilot_mask

SCAN = EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-a.tiff'
_evidence.need(SCAN, tool='handanalyze_e014')
arr = tifffile.TiffFile(str(SCAN)
                        ).pages[0].asarray(out='memmap')
Hs, Ws = arr.shape

# 25 mm center window (decoded clean at 7.96%)
cpm = 600 / 25.4 / CD
src = int(25 * cpm * CD * 8)
y0, x0 = int(Hs * 0.5) - src // 2, int(Ws * 0.5) - src // 2
win = np.asarray(arr[y0:y0 + src, x0:x0 + src], dtype=np.float32)

norm = scannorm.normalize_to_canonical(scannorm.reduce_plane(win, 'K'),
                                       scannorm.measure_cell_pitch(
                                           scannorm.reduce_plane(win, 'K')
                                       ).pitch_px, CD)
res = acquire.acquire_and_decode(norm.img, spec, SEED,
                                 cell_px_nominal=norm.cell_px_est)
assert res.ok
grid = res.grid
oy, ox = res.cell_origin_abs_yx
img_c = np.ascontiguousarray(np.rot90(
    norm.img[:, ::-1] if res.mirrored else norm.img, res.orientation_k))
img_r = acquire._normalize_refl(img_c)
hh, ww = grid.shape_cells
hh = min(hh, GT.shape[0] - oy)
ww = min(ww, GT.shape[1] - ox)
gtw = GT[oy:oy + hh, ox:ox + ww]
pmw = PM[oy:oy + hh, ox:ox + ww]
print(f"window {hh}x{ww} cells @ origin ({oy},{ox}); footing "
      f"{norm.cell_px_est:.3f} px/cell; grid pitch "
      f"{float(np.mean(grid.pitch_v_px)):.3f}/"
      f"{float(np.mean(grid.pitch_u_px)):.3f}")


def cellmeans_at(dy_dot, dx_dot):
    """Full-frame cell reflectance means with a CONSTANT (dy,dx) dot offset."""
    wf = lambda y, x: (np.full(np.broadcast(y, x).shape, dy_dot),
                       np.full(np.broadcast(y, x).shape, dx_dot))
    return acquire.resample_cell_means(img_c, grid, wf, cell_dots=CD)


def hard_at(dy_dot, dx_dot):
    """EXACTLY the decoder's detection (cell_bits_blind) at a global offset —
    ink=1, its own quantile-z + pinned-50% GMM + LLR sign."""
    hard, _ = acquire.cell_bits_blind(cellmeans_at(dy_dot, dx_dot))
    return hard[:hh, :ww]


means0 = cellmeans_at(0.0, 0.0)[:hh, :ww]
hard0 = hard_at(0.0, 0.0)
blind_ber = float(np.mean(hard0 != gtw))
print(f"\n[1] BLIND BER (self-synced grid, offset 0): {100*blind_ber:.2f}%")

# --- global sub-cell offset sweep: best-registration BER ------------------
offs = np.linspace(-0.9, 0.9, 19)      # dots (cell = 2 dots => +-0.45 cell)
best = (blind_ber, 0.0, 0.0)
grid_ber = np.zeros((offs.size, offs.size))
for i, dy in enumerate(offs):
    for j, dx in enumerate(offs):
        b = float(np.mean(hard_at(dy, dx) != gtw))
        grid_ber[i, j] = b
        if b < best[0]:
            best = (b, dy, dx)
print(f"[1] GENIE-best global offset BER: {100*best[0]:.2f}% at "
      f"(dy={best[1]:+.2f}, dx={best[2]:+.2f}) dots "
      f"[{best[1]/CD:+.2f},{best[2]/CD:+.2f}] cells")
print(f"    -> self-sync leaves {100*(blind_ber-best[0]):.2f} pp on the "
      f"table vs the best single global offset")

# --- per-cell offset robustness: wrong at 0, right somewhere within 1/3 cell
nbr = [(-2/3*CD, 0), (2/3*CD, 0), (0, -2/3*CD), (0, 2/3*CD),
       (-2/3*CD, -2/3*CD), (2/3*CD, 2/3*CD), (-2/3*CD, 2/3*CD),
       (2/3*CD, -2/3*CD)]
hard_nbr = np.stack([hard_at(dy, dx) for dy, dx in nbr])   # (8,hh,ww)
err0 = hard0 != gtw
# a cell is "sync-recoverable" if wrong at 0 but the correct value appears
# at some small neighbor offset
right_somewhere = np.any(hard_nbr == gtw[None], axis=0)
sync_recoverable = err0 & right_somewhere
channel_hard = err0 & ~right_somewhere
n_err = int(err0.sum())
print(f"\n[2] of {n_err} errant cells: "
      f"{int(sync_recoverable.sum())} ({100*sync_recoverable.sum()/n_err:.0f}%) "
      f"read CORRECTLY at some |offset|<=1/3 cell (SYNC-recoverable), "
      f"{int(channel_hard.sum())} ({100*channel_hard.sum()/n_err:.0f}%) "
      f"wrong at EVERY nearby offset (CHANNEL)")

# --- ink asymmetry --------------------------------------------------------
miss = int(((gtw == 1) & (hard0 == 0)).sum())      # ink expected, read white
fa = int(((gtw == 0) & (hard0 == 1)).sum())        # white expected, read ink
n1, n0 = int((gtw == 1).sum()), int((gtw == 0).sum())
print(f"\n[3] asymmetry: MISS (ink->white) {miss}/{n1} = "
      f"{100*miss/n1:.2f}% | FALSE-ALARM (white->ink) {fa}/{n0} = "
      f"{100*fa/n0:.2f}%  (c2 doc: 2-dot-white closure => FA-heavy)")

# channel-hard errors by direction
ch_miss = int(((gtw == 1) & (hard0 == 0) & channel_hard).sum())
ch_fa = int(((gtw == 0) & (hard0 == 1) & channel_hard).sum())
print(f"    channel-hard split: miss {ch_miss} / FA {ch_fa}")

# --- spatial structure: error autocorrelation lag-1 & clustering ----------
ef = err0.astype(float) - err0.mean()
ac_y = float(np.mean(ef[1:] * ef[:-1]) / (ef.var() + 1e-9))
ac_x = float(np.mean(ef[:, 1:] * ef[:, :-1]) / (ef.var() + 1e-9))
# banding: row-mean error profile peak/mean
row_err = err0.mean(1)
print(f"\n[4] error autocorr lag-1: y {ac_y:.3f} x {ac_x:.3f} "
      f"(>0 = clustered); row-error range "
      f"{100*row_err.min():.1f}-{100*row_err.max():.1f}% "
      f"(banding if wide)")

# --- pixel patches: 3 channel-hard cells, show 3x3-cell neighborhoods -----
cell_px = norm.cell_px_est
ys, xs = np.where(channel_hard)
print(f"\n[5] sample CHANNEL-hard cells (GT vs scan ink; each cell "
      f"~{cell_px:.1f}px):")
rng_pick = rng(SEED, b"pick")
sel = rng_pick.choice(ys.size, size=min(4, ys.size), replace=False)
for k in sel:
    cy, cx = int(ys[k]), int(xs[k])
    # local mean reflectance of the cell (lower = more ink)
    yc = grid._centers_uv(np.float64(cy), np.float64(cx))
    print(f"    cell ({cy:3d},{cx:3d}): GT={gtw[cy,cx]} read={hard0[cy,cx]} "
          f"cellmean_refl={means0[cy,cx]:.3f} "
          f"(GT1 median {np.median(means0[gtw==1]):.3f}, "
          f"GT0 median {np.median(means0[gtw==0]):.3f}) "
          f"{'PILOT' if pmw[cy,cx] else 'payload'}")

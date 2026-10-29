#!/usr/bin/env python
# Historical record of e014 (014.2), retired from scratch/ 2026-10-09; inputs in the evidence archive.
# Regenerates build/e014_error_patches.png with:
#   PYTHONPATH=src:. env/bin/python experiments/014-c2-print/patches_e014.py --evidence-root DIR
"""Visual error samples from the e014 c2 scan: for each errant cell, show
the REAL SCAN neighborhood (16 px/cell native) next to the GROUND-TRUTH
cell pattern, center cell boxed. Categories: white-closure FA, ink-erosion
miss, fold-band, borderline. Output: <--out>/e014_error_patches.png"""
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
EVIDENCE = _evidence.resolve(ARGS.evidence_root, tool='patches_e014')
ARGS.out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'experiments/014-c2-print'))
import tifffile
from PIL import Image, ImageDraw
from scipy.ndimage import convolve
from paperholo import compose, scannorm, acquire
from paperholo.modulation import rng
import gen_e014

SEED = gen_e014.SEED
spec = gen_e014.make_spec()
CD = 2
pg = rng(SEED, b"e014/payload").integers(
    0, 2, compose.payload_capacity(spec), dtype=np.uint8)
cp = compose.compose_page(pg, spec, SEED, 0)
GT = cp.cell_values

SCAN = EVIDENCE / 'paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-a.tiff'
_evidence.need(SCAN, tool='patches_e014')
arr = tifffile.TiffFile(str(SCAN)
                        ).pages[0].asarray(out='memmap')
Hs, Ws = arr.shape
cpm = 600 / 25.4 / CD
src = int(25 * cpm * CD * 8)
y0, x0 = int(Hs * 0.5) - src // 2, int(Ws * 0.5) - src // 2
win = np.asarray(arr[y0:y0 + src, x0:x0 + src], dtype=np.float32)

red = scannorm.reduce_plane(win, 'K')
norm = scannorm.normalize_to_canonical(
    red, scannorm.measure_cell_pitch(red).pitch_px, CD)
res = acquire.acquire_and_decode(norm.img, spec, SEED,
                                 cell_px_nominal=norm.cell_px_est)
assert res.ok and res.orientation_k == 2 and not res.mirrored
grid = res.grid
oy, ox = res.cell_origin_abs_yx
img_c = np.ascontiguousarray(np.rot90(norm.img, 2))
win_c = np.ascontiguousarray(np.rot90(red, 2))          # full-res canonical
means = acquire.sample_cell_means(acquire._normalize_refl(img_c), grid,
                                  cell_dots=CD)
hard, llr = acquire.cell_bits_blind(means)
hh = min(hard.shape[0], GT.shape[0] - oy)
ww = min(hard.shape[1], GT.shape[1] - ox)
h, g = hard[:hh, :ww], GT[oy:oy + hh, ox:ox + ww]
L, M = llr[:hh, :ww], means[:hh, :ww]
err = h != g
k8 = np.ones((3, 3), int); k8[1, 1] = 0
inknbr = convolve((g == 1).astype(int), k8, mode='constant')
fa = (g == 0) & (h == 1)
miss = (g == 1) & (h == 0)
band = np.zeros_like(err); band[161:167] = True         # the fold rows

cats = [
    ("closure FA", fa & (inknbr >= 6) & ~band, "-inknbr"),
    ("closure FA", fa & (inknbr >= 6) & ~band, "-inknbr2"),
    ("erosion miss", miss & (inknbr <= 3) & ~band, "-white"),
    ("erosion miss", miss & (inknbr <= 3) & ~band, "-white2"),
    ("FOLD band", err & band, "-fold"),
    ("FOLD band", err & band, "-fold2"),
    ("borderline", err & (np.abs(L) < 1.0) & ~band, "-bl"),
    ("correct ref", ~err & (g == 0) & (inknbr >= 6), "-ok"),  # surrounded white that SURVIVED
]

N = 3            # neighborhood half-size in cells -> 7x7
CELLPX = 16      # full-res px/cell (approx; use grid mapping x2)
SCALE = 4
tile_w = (2 * N + 1) * CELLPX * SCALE // 2   # display: scan at x2 scale of 8px/cell => equivalent
panels = []
picker = rng(SEED, b"patchpick")

used = set()
for label, mask, tag in cats:
    ys, xs = np.where(mask)
    if ys.size == 0:
        continue
    # deterministic distinct pick, away from window edges
    order = picker.permutation(ys.size)
    pick = None
    for oidx in order:
        cy, cx = int(ys[oidx]), int(xs[oidx])
        if (cy, cx) in used or cy < N + 2 or cx < N + 2 \
                or cy >= hh - N - 2 or cx >= ww - N - 2:
            continue
        pick = (cy, cx)
        break
    if pick is None:
        continue
    used.add(pick)
    cy, cx = pick
    # px center in img_c (8 px/cell) -> full-res win_c is x2
    v, u = grid._centers_uv(np.float64(cy), np.float64(cx))
    ypx, xpx = grid._uv_to_px(np.array(v), np.array(u))
    yf, xf = float(ypx) * 2, float(xpx) * 2
    half = int((N + 0.5) * norm.cell_px_est * 2)
    y0p, x0p = int(round(yf)) - half, int(round(xf)) - half
    patch = win_c[y0p:y0p + 2 * half, x0p:x0p + 2 * half]
    pm = (np.clip(patch, 0, 1) * 255).astype(np.uint8)
    im = Image.fromarray(pm).resize((2 * half * 2, 2 * half * 2),
                                    Image.NEAREST)
    d = ImageDraw.Draw(im)
    cpx = norm.cell_px_est * 2 * 2                       # display px/cell
    c0 = im.size[0] / 2 - cpx / 2
    d.rectangle([c0, c0, c0 + cpx, c0 + cpx], outline=200, width=3)
    # GT panel
    gtp = g[cy - N:cy + N + 1, cx - N:cx + N + 1]
    gtimg = Image.fromarray(((1 - gtp) * 255).astype(np.uint8)) \
        .resize(im.size, Image.NEAREST)
    dg = ImageDraw.Draw(gtimg)
    gc = im.size[0] / 2 - im.size[0] / (2 * N + 1) / 2
    gcell = im.size[0] / (2 * N + 1)
    dg.rectangle([gc, gc, gc + gcell, gc + gcell], outline=128, width=3)
    # header strip
    wpair = im.size[0] * 2 + 8
    head = 26
    pair = Image.new('L', (wpair, im.size[1] + head), 255)
    pair.paste(im, (0, head))
    pair.paste(gtimg, (im.size[0] + 8, head))
    dp = ImageDraw.Draw(pair)
    dp.text((4, 4), f"{label}  abs({oy+cy},{ox+cx})  GT={g[cy,cx]} "
            f"read={h[cy,cx]}  refl={M[cy,cx]:.2f}  LLR={L[cy,cx]:+.1f}  "
            f"inkNbrs={inknbr[cy,cx]}", fill=0)
    panels.append(pair)

# montage: 2 columns
cols = 2
rows = (len(panels) + cols - 1) // cols
pw, ph = panels[0].size
mont = Image.new('L', (cols * pw + (cols - 1) * 12,
                       rows * ph + (rows - 1) * 12), 255)
for i, p in enumerate(panels):
    r, c = divmod(i, cols)
    mont.paste(p, (c * (pw + 12), r * (ph + 12)))
out = ARGS.out / 'e014_error_patches.png'
mont.save(out)
print(f"saved {out} ({mont.size[0]}x{mont.size[1]}) — left=SCAN (center "
      f"cell boxed), right=GROUND TRUTH; ink=dark", flush=True)

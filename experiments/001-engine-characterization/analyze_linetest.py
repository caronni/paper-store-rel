#!/usr/bin/env python
"""Run 001.1 analysis: register a linetest scan and measure each patch.

This sheet predates the fiducial crosses, so registration is translation
voting over patch-sized blobs (no orientation ambiguity arose in practice —
if in doubt, prefer gridtest sheets, which carry fiducials + orientation mark).

Usage: python analyze_linetest.py [scan.png]   (default ../../scans/test-scan-2.png)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
SCAN_DPI = 1200
PRINT_DPI = 600
S = SCAN_DPI / PRINT_DPI  # scan px per printer dot

root = Path(__file__).parent / "build"
scan_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "../../scans/test-scan-2.png"
scan = np.asarray(Image.open(scan_path).convert("L")).astype(np.float32)
man = json.load(open(root / "linetest_manifest.json"))
patches = man["patches"]

# --- 1. registration: find patch squares by thresholding ---------------------
# Patches are 12 mm squares of substantial ink coverage; labels are thin text.
dark = scan < 128
# erode-ish via block reduce to kill text, keep 12mm blobs
b = 32
H, W = dark.shape
hb, wb = H // b, W // b
blocks = dark[: hb * b, : wb * b].reshape(hb, b, wb, b).mean(axis=(1, 3))
cand = blocks > 0.25  # block is >25% dark -> inside a patch

# connected components (4-neighbour) on the small grid
lbl = np.zeros_like(cand, dtype=int)
cur = 0
for i in range(hb):
    for j in range(wb):
        if cand[i, j] and lbl[i, j] == 0:
            cur += 1
            stack = [(i, j)]
            while stack:
                y, x = stack.pop()
                if 0 <= y < hb and 0 <= x < wb and cand[y, x] and lbl[y, x] == 0:
                    lbl[y, x] = cur
                    stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]

found = []
exp_px = 12 / 25.4 * SCAN_DPI  # expected patch side in scan px (~567)
for k in range(1, cur + 1):
    ys, xs = np.nonzero(lbl == k)
    h = (ys.max() - ys.min() + 1) * b
    w = (xs.max() - xs.min() + 1) * b
    if 0.6 * exp_px < h < 1.5 * exp_px and 0.6 * exp_px < w < 1.5 * exp_px:
        found.append((xs.min() * b, ys.min() * b, w, h))
print(f"found {len(found)} patch-sized blobs (expect near 22)")

# --- 2. fit scan = a * print + t  (scale + translation, no rotation term) ----
# translation voting: every (blob, patch) pair proposes t; most inliers wins
mx = np.array([p["x_dots"] for p in patches], float)
my = np.array([p["y_dots"] for p in patches], float)
best, best_t = -1, (0.0, 0.0)
for f in found:
    for k in range(len(patches)):
        t = (f[0] - S * mx[k], f[1] - S * my[k])
        n = 0
        for g in found:
            d = (S * mx + t[0] - g[0]) ** 2 + (S * my + t[1] - g[1]) ** 2
            if d.min() < (0.2 * exp_px) ** 2:
                n += 1
        if n > best:
            best, best_t = n, t
t0x, t0y = best_t
pairs = []
for f in found:
    d = (S * mx + t0x - f[0]) ** 2 + (S * my + t0y - f[1]) ** 2
    k = int(np.argmin(d))
    if d[k] < (0.2 * exp_px) ** 2:
        pairs.append((k, f))
print(f"matched {len(pairs)}/{len(found)} blobs (voting: {best} inliers)")
A = np.array([[S * patches[k]["x_dots"], 1] for k, f in pairs])
bx = np.array([f[0] for k, f in pairs])
Ay = np.array([[S * patches[k]["y_dots"], 1] for k, f in pairs])
by = np.array([f[1] for k, f in pairs])
sx, ox = np.linalg.lstsq(A, bx, rcond=None)[0]
sy, oy = np.linalg.lstsq(Ay, by, rcond=None)[0]
print(f"scale err x={sx:+.4%} y={sy:+.4%}  offset=({ox:.0f},{oy:.0f}) scan px")

def crop(p, pad_dots=6):
    x = (S * (p["x_dots"] - pad_dots)) * sx + ox
    y = (S * (p["y_dots"] - pad_dots)) * sy + oy
    w = S * (p["w_dots"] + 2 * pad_dots) * sx
    h = S * (p["h_dots"] + 2 * pad_dots) * sy
    return scan[int(y) : int(y + h), int(x) : int(x + w)]

# --- 3. measurements ----------------------------------------------------------
def fft_orientation(img):
    """dominant stripe orientation (deg) + period (printer dots) via FFT peak"""
    g = img - img.mean()
    win = np.outer(np.hanning(g.shape[0]), np.hanning(g.shape[1]))
    F = np.abs(np.fft.rfft2(g * win))
    F[0, :3] = 0; F[:3, 0] = 0  # kill DC + lowest bins (illumination)
    ky, kx = np.unravel_index(np.argmax(F), F.shape)
    if ky > g.shape[0] // 2: ky -= g.shape[0]
    fr = np.hypot(kx / g.shape[1], ky / g.shape[0])  # cycles / scan px
    ang = np.degrees(np.arctan2(ky / g.shape[0], kx / g.shape[1]))
    period_dots = (1 / fr) / S if fr > 0 else np.inf
    return ang % 180, period_dots

results = {}
for p in patches:
    img = crop(p)
    name = p["name"]
    ink = (img < 128).mean()
    mean = img.mean()
    ang, per = fft_orientation(img)
    results[name] = dict(ink_frac=round(float(ink), 3), mean=round(float(mean), 1),
                         fft_deg=round(float(ang), 1), fft_period_dots=round(float(per), 2))
    print(f"{name:14} ink={ink:.3f} mean={mean:5.1f} fft: {ang:6.1f} deg  period {per:6.2f} dots  | {p['note']}")

json.dump(results, open(root / "linetest_measurements.json", "w"), indent=1)

# --- 4. save 1:1 crops of the interesting patches for eyeballing -------------
for name in ["bow_dot1", "wob_hole1", "bow_1dot_0", "bow_1dot_45", "bow_1dot_90",
             "bow_1dot_135", "wob_1dot_0", "wob_1dot_135", "bow_nyq_H", "bow_nyq_V",
             "wob_nyq_H", "wob_nyq_V", "bow_ladV_1", "wob_ladV_1", "bow_ladV_3", "wob_ladV_3"]:
    p = next(q for q in patches if q["name"] == name)
    img = crop(p, pad_dots=2)
    c = img[: 400, : 400]  # 200x200 printer dots
    Image.fromarray(c.astype(np.uint8)).resize((800, 800), Image.NEAREST).save(root / f"linetest_zoom_{name}.png")
print("zoom crops written: build/linetest_zoom_*.png (200x200 dots, 4x zoom)")


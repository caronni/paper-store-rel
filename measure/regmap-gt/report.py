#!/usr/bin/env python
# Historical record of e033 (supervised per-plane registration on sheet I, the AltaLink Y sinusoid; PAGE-FIELD B3's
# reference), retired from scratch/xerox-v1-20260818/regmap-gt/ 2026-10-09; inputs in the evidence archive.
# Regenerates build/regmap-gt/{per-column.json,plane-offsets.png} with: PYTHONPATH=src:. env/bin/python measure/regmap-gt/report.py   (after measure_plane_offsets.py)
"""Aggregate plane-offsets.json into the per-column table + figure."""
from __future__ import annotations
import json
import os

import numpy as np

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "build", "regmap-gt")      # the outputs, beside plane-offsets.json
D = json.load(open(os.path.join(HERE, "plane-offsets.json")))
P = D["patches"]
RES = np.array(D["residue"])
DEAD = {8, 16, 28, 9, 10, 11, 15, 17, 18, 19, 27, 29}
CLEAN = {4, 5, 6, 12, 13, 14, 21, 22, 23, 31, 33, 34, 35}


def col(tx, key):
    return np.array([p[key] for p in P if p["tile_x"] == tx and key in p])


def mad(a):
    return float(np.median(np.abs(a - np.median(a))) * 1.4826)


rows = []
for tx in range(37):
    r = {"tx": tx, "residue": int(RES[tx]), "n": len(col(tx, "dY_rel_x"))}
    for k in ("dY_rel_x", "dY_rel_y", "dCM_x", "dCM_y",
              "dC_x", "dM_x", "dY_x"):
        v = col(tx, k)
        r[k] = float(np.median(v))
        r[k + "_sd"] = mad(v)
    for k in ("C_corr", "M_corr", "Y_corr"):
        r[k] = float(np.median(col(tx, k)))
    rows.append(r)

cls = {tx: ("DEAD " if tx in DEAD else "clean" if tx in CLEAN else "  -  ")
       for tx in range(37)}

print("per-column medians over %d tile rows  (scan px; 4 px = 1 printer dot)"
      % len(D["rows"]))
print("tx cls   res | dY_rel_x   dot | rowMAD | dY_rel_y   dot | "
      "dCM_x  dCM_y |  corr C/M/Y")
print("-" * 96)
for r in rows:
    print("%2d %s %4d | %8.2f %5.2f | %6.2f | %8.2f %5.2f | %6.2f %6.2f | "
          "%.2f/%.2f/%.2f" % (
              r["tx"], cls[r["tx"]], r["residue"],
              r["dY_rel_x"], r["dY_rel_x"] / 4, r["dY_rel_x_sd"],
              r["dY_rel_y"], r["dY_rel_y"] / 4,
              r["dCM_x"], r["dCM_y"], r["C_corr"], r["M_corr"], r["Y_corr"]))

dead = np.array([r["dY_rel_x"] for r in rows if r["tx"] in DEAD])
clean = np.array([r["dY_rel_x"] for r in rows if r["tx"] in CLEAN])
deady = np.array([r["dY_rel_y"] for r in rows if r["tx"] in DEAD])
cleany = np.array([r["dY_rel_y"] for r in rows if r["tx"] in CLEAN])
cmd = np.array([r["dCM_x"] for r in rows if r["tx"] in DEAD])
cmc = np.array([r["dCM_x"] for r in rows if r["tx"] in CLEAN])
print("\n            |dY_rel_x| mean   |dY_rel_y| mean   |dCM_x| mean")
print("DEAD  (%2d)  %14.3f %17.3f %16.3f"
      % (len(dead), np.abs(dead).mean(), np.abs(deady).mean(),
         np.abs(cmd).mean()))
print("CLEAN (%2d)  %14.3f %17.3f %16.3f"
      % (len(clean), np.abs(clean).mean(), np.abs(cleany).mean(),
         np.abs(cmc).mean()))

ax = np.abs([r["dY_rel_x"] for r in rows])
ay = np.abs([r["dY_rel_y"] for r in rows])
acm = np.abs([r["dCM_x"] for r in rows])
print("\nSpearman/Pearson vs residue over all 37 columns:")
from scipy.stats import spearmanr, pearsonr                      # noqa: E402
for name, v in (("|dY_rel_x|", ax), ("|dY_rel_y|", ay),
                ("|dCM_x|", acm)):
    s = spearmanr(v, RES)
    p = pearsonr(v, RES)
    print("  %-11s  spearman r=%+.3f p=%.2g | pearson r=%+.3f p=%.2g"
          % (name, s.statistic, s.pvalue, p.statistic, p.pvalue))

# within-patch precision: MAD of per-row scatter, pooled
allsd = np.array([r["dY_rel_x_sd"] for r in rows])
print("\nrow-to-row MAD of dY_rel_x: median %.2f px, max %.2f px"
      % (np.median(allsd), allsd.max()))

# --- scanner-lens discriminator -------------------------------------------
# Lateral chromatic aberration is necessarily ODD about the scanner optical
# axis (zero on axis, opposite sign either side).  An EVEN component cannot
# come from the scan lens.
from scipy.interpolate import interp1d                           # noqa: E402
AX = D["affine_x"]
xs = np.array([AX[0] * 3392 + AX[1] * (t * 128 + 64) + AX[2] for t in range(37)])
tx_axis = float(np.interp(20416 / 2.0, xs, np.arange(37)))
u = np.arange(37) - tx_axis


def evenodd(v):
    m = interp1d(u, v, bounds_error=False, fill_value=np.nan)(-u)
    ok = np.isfinite(m)
    e = np.full(37, np.nan); o = np.full(37, np.nan)
    e[ok] = 0.5 * (v[ok] + m[ok]); o[ok] = 0.5 * (v[ok] - m[ok])
    return e, o


vY = np.array([r["dY_rel_x"] for r in rows])
vCM = np.array([r["dCM_x"] for r in rows])
eY, oY = evenodd(vY)
eC, oC = evenodd(vCM)
print("\nsymmetry about the scanner optical axis (tile_x %.2f):" % tx_axis)
print("  dY_rel_x : even rms %.2f px | odd rms %.2f px  -> EVEN-dominated,"
      " cannot be scan-lens lateral CA" % (np.sqrt(np.nanmean(eY ** 2)),
                                           np.sqrt(np.nanmean(oY ** 2))))
print("  dCM_x    : even rms %.2f px | odd rms %.2f px  -> odd-dominated,"
      " consistent with R-G lateral CA" % (np.sqrt(np.nanmean(eC ** 2)),
                                           np.sqrt(np.nanmean(oC ** 2))))
z = vY - vY.mean()
F = np.abs(np.fft.rfft(z * np.hanning(37)))
k = int(np.argmax(F[1:]) + 1)
print("  dY_rel_x dominant period %.1f tiles = %.0f mm across the field"
      % (37 / k, 37 / k * 128 / 600 * 25.4))
print("\ndeviation from the plane-common (C/M-mean) pose, x:")
print("  C and M: +/- %.2f px = %.2f dot = %.2f cell (peak)"
      % (np.abs(vCM).max() / 2, np.abs(vCM).max() / 8, np.abs(vCM).max() / 16))
print("  Y      : +/- %.2f px = %.2f dot = %.2f cell (peak)"
      % (np.abs(vY).max(), np.abs(vY).max() / 4, np.abs(vY).max() / 8))

json.dump(rows, open(os.path.join(HERE, "per-column.json"), "w"), indent=1)


# ---------------- figure (PIL) --------------------------------------------
from PIL import Image, ImageDraw                                 # noqa: E402

W, H = 1500, 900
img = Image.new("RGB", (W, H), "white")
dr = ImageDraw.Draw(img)
L, R = 80, W - 30
n = 37
bw = (R - L) / n


def xpos(tx):
    return L + bw * (tx + 0.5)


# --- panel 1: residue bars ---
t0, t1 = 40, 240
dr.text((10, t0 - 22), "decoder Y-certificate residue (failed tiles / 53)",
        fill="black")
for tx in range(n):
    h = (t1 - t0) * RES[tx] / 53.0
    c = (200, 60, 60) if tx in DEAD else (
        (70, 150, 90) if tx in CLEAN else (150, 150, 150))
    dr.rectangle([xpos(tx) - bw * 0.4, t1 - h, xpos(tx) + bw * 0.4, t1],
                 fill=c)
dr.line([L, t1, R, t1], fill="black")
for tx in range(0, n, 2):
    dr.text((xpos(tx) - 6, t1 + 4), str(tx), fill="black")

# --- panel 2: dY_rel_x with per-row points ---
p0, p1 = 300, 620
lim = 5.0
dr.text((10, p0 - 22),
        "dY - (dC+dM)/2 , x component   [scan px; 4 px = 1 printer dot]",
        fill="black")
mid = (p0 + p1) / 2


def ypos(v, lo=p0, hi=p1, lim=lim):
    m = (lo + hi) / 2
    return m - (hi - lo) / 2 * (v / lim)


for g in (-4, -2, 0, 2, 4):
    y = ypos(g)
    dr.line([L, y, R, y], fill=(220, 220, 220) if g else (0, 0, 0))
    dr.text((L - 40, y - 6), "%+.0f" % g, fill="black")
dr.text((L - 70, ypos(4) - 20), "px", fill="black")
for tx in range(n):
    v = [p["dY_rel_x"] for p in P if p["tile_x"] == tx]
    for u in v:
        dr.ellipse([xpos(tx) - 2, ypos(np.clip(u, -lim, lim)) - 2,
                    xpos(tx) + 2, ypos(np.clip(u, -lim, lim)) + 2],
                   fill=(160, 160, 220))

for tx in range(n):
    med = rows[tx]["dY_rel_x"]
    c = (200, 60, 60) if tx in DEAD else (
        (70, 150, 90) if tx in CLEAN else (90, 90, 90))
    y = ypos(np.clip(med, -lim, lim))
    dr.rectangle([xpos(tx) - bw * 0.35, y - 3, xpos(tx) + bw * 0.35, y + 3],
                 fill=c)
    if tx:
        pm = ypos(np.clip(rows[tx - 1]["dY_rel_x"], -lim, lim))
        dr.line([xpos(tx - 1), pm, xpos(tx), y], fill=(60, 60, 60))
# half-cell reference (1 dot = 4 px)
dr.text((L + 8, p0 + 4), "+-4 px = +-1 printer dot = +-0.5 cell", fill=(150, 60, 60))

# --- panel 3: controls dCM_x and dY_rel_y ---
q0, q1 = 680, 860
dr.text((10, q0 - 22),
        "controls:  dC-dM x (blue)   |   dY-(dC+dM)/2 y (orange)", fill="black")
for g in (-4, -2, 0, 2, 4):
    y = ypos(g, q0, q1)
    dr.line([L, y, R, y], fill=(220, 220, 220) if g else (0, 0, 0))
    dr.text((L - 40, y - 6), "%+.0f" % g, fill="black")
for tx in range(n):
    y = ypos(np.clip(rows[tx]["dCM_x"], -lim, lim), q0, q1)
    dr.ellipse([xpos(tx) - 4, y - 4, xpos(tx) + 4, y + 4], fill=(40, 80, 200))
    if tx:
        pm = ypos(np.clip(rows[tx - 1]["dCM_x"], -lim, lim), q0, q1)
        dr.line([xpos(tx - 1), pm, xpos(tx), y], fill=(40, 80, 200))
    y2 = ypos(np.clip(rows[tx]["dY_rel_y"], -lim, lim), q0, q1)
    dr.ellipse([xpos(tx) - 3, y2 - 3, xpos(tx) + 3, y2 + 3],
               fill=(230, 140, 20))
    if tx:
        pm = ypos(np.clip(rows[tx - 1]["dY_rel_y"], -lim, lim), q0, q1)
        dr.line([xpos(tx - 1), pm, xpos(tx), y2], fill=(230, 140, 20))
dr.text((L, q1 + 12), "tile column (tile_x)  --  red = DEAD, green = CLEAN",
        fill="black")
img.save(os.path.join(HERE, "plane-offsets.png"))
print("wrote plane-offsets.png")

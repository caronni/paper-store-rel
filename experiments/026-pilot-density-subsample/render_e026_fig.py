#!/usr/bin/env python
"""e026 figure: grain-vs-density curves + pooled sites-threshold collapse.
PIL-only (no matplotlib in env). Output: this experiment's
build/e026-grain-vs-density[-c3].png
Run from repo root: env/bin/python experiments/026-pilot-density-subsample/render_e026_fig.py \\
    --report <probe_e026.py's e026_report[_c3].json> [--c3]
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ARM = "_c3" if "--c3" in sys.argv else ""
if "--report" not in sys.argv[:-1]:
    sys.exit(__doc__)
rep = json.loads(Path(sys.argv[sys.argv.index("--report") + 1]).read_text())
OUT = HERE / "build" / f"e026-grain-vs-density{ARM.replace('_', '-')}.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

W, H = 1040, 470
PAD_L, PAD_B, PAD_T = 64, 52, 40
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
try:
    F = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
    FS = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 11)
except OSError:
    F = FS = ImageFont.load_default()

COLORS = {1.00: (20, 20, 20), 0.80: (0, 90, 200), 0.64: (0, 150, 70),
          0.44: (220, 130, 0), 0.36: (200, 30, 30)}


def axes(x0, y0, x1, y1, title):
    d.rectangle([x0, y0, x1, y1], outline=(160, 160, 160))
    d.text((x0, y0 - 22), title, fill="black", font=F)


# ---- panel 1: correct+frozen-gate rate vs size, per density ----
p1 = (PAD_L, PAD_T, 490, H - PAD_B)
axes(*p1, "placement yield vs fragment size (real "
     + ("e012/c3" if ARM else "e014/c2") + " Canon scans)")
sizes = sorted({s["mm"] for s in rep["summary"]})
xmap = {mm: p1[0] + 30 + i * (p1[2] - p1[0] - 60) / (len(sizes) - 1)
        for i, mm in enumerate(sizes)}


def ymap1(v):
    return p1[3] - v * (p1[3] - p1[1] - 14)


for mm in sizes:
    d.text((xmap[mm] - 8, p1[3] + 6), f"{mm}", fill="black", font=F)
d.text(((p1[0] + p1[2]) // 2 - 60, p1[3] + 24), "fragment size (mm)",
       fill="black", font=F)
for v in (0, 0.5, 1.0):
    d.text((p1[0] - 34, ymap1(v) - 7), f"{v:.1f}", fill="black", font=FS)
    d.line([p1[0], ymap1(v), p1[2], ymap1(v)], fill=(235, 235, 235))
for f in sorted({s["f"] for s in rep["summary"]}, reverse=True):
    pts = []
    for mm in sizes:
        row = next(s for s in rep["summary"]
                   if s["f"] == f and s["mm"] == mm)
        pts.append((xmap[mm], ymap1(row["gate_pass"] / row["n"])))
    col = COLORS[f]
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=col, width=2)
    for x, y in pts:
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
    peq = next(s["p_equiv"] for s in rep["summary"] if s["f"] == f)
    dlt = 2.78 * f
    d.text((p1[2] - 168, p1[1] + 8 + 16 * list(
        sorted({s['f'] for s in rep['summary']}, reverse=True)).index(f)),
        f"P~{peq:3d}  d={dlt:.2f}%", fill=col, font=FS)

# ---- panel 2: pooled collapse — admission vs sites-in-window ----
p2 = (560, PAD_T, W - 30, H - PAD_B)
axes(*p2, "pooled: correct+gated vs pilot sites in fragment")
recs = rep["records"]
smax = max(r["sites"] for r in recs)
BINW = 25
bins: dict[int, list] = {}
for r in recs:
    bins.setdefault(r["sites"] // BINW, []).append(
        int(r["exact"] and r["gate"]))


def xmap2(s):
    return p2[0] + 20 + s / (smax + 20) * (p2[2] - p2[0] - 40)


def ymap2(v):
    return p2[3] - v * (p2[3] - p2[1] - 14)


for s in range(0, smax + 1, 100):
    d.text((xmap2(s) - 12, p2[3] + 6), f"{s}", fill="black", font=FS)
d.text(((p2[0] + p2[2]) // 2 - 90, p2[3] + 24),
       "thinned pilot sites in window", fill="black", font=F)
# the pre-registered 140-150 site band
d.rectangle([xmap2(140), p2[1] + 1, xmap2(150), p2[3] - 1],
            fill=(255, 238, 238))
d.text((xmap2(140) - 30, p2[1] + 4), "140-150 pre-reg", fill=(200, 30, 30),
       font=FS)
for v in (0, 0.5, 1.0):
    d.line([p2[0], ymap2(v), p2[2], ymap2(v)], fill=(235, 235, 235))
pts = sorted((k * BINW + BINW / 2, sum(v) / len(v), len(v))
             for k, v in bins.items())
for a, b in zip(pts, pts[1:]):
    d.line([xmap2(a[0]), ymap2(a[1]), xmap2(b[0]), ymap2(b[1])],
           fill=(60, 60, 60), width=2)
for s, v, n in pts:
    d.ellipse([xmap2(s) - 3, ymap2(v) - 3, xmap2(s) + 3, ymap2(v) + 3],
              fill=(60, 60, 60))
    d.text((xmap2(s) - 6, ymap2(v) - 18), f"{n}", fill=(150, 150, 150),
           font=FS)
d.text((p2[0] + 8, p2[3] - 20),
       "small grey n = windows/bin", fill=(120, 120, 120), font=FS)

img.save(OUT)
print(f"figure -> {OUT}")

# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# build/mic-blue-deficit.png with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/diag_mic.py --evidence-root DIR
"""Hunt the AltaLink's yellow machine-identification dots on the COLOR sheet (read-only).
Repo record 007.7/007.8: ~24x24-dot cell, ~0.24 dots/mm^2, on every sheet with COLOR
content; K-only pages clean.  Yellow toner absorbs BLUE, so it lives in the B channel."""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="diag_mic")
XEROX_COLOR = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-color-canon-4800rgb.tiff"
_evidence.need(XEROX_COLOR, tool="diag_mic")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import numpy as np, tifffile
from PIL import Image
DPI = 4800.0
def mm(v): return int(v / 25.4 * DPI)

A = tifffile.memmap(str(XEROX_COLOR))
print("shape", A.shape)

# find a genuinely blank tile: high mean in ALL channels
best = None
for y in range(mm(20), mm(280), mm(10)):
    for x in range(mm(15), mm(195), mm(10)):
        t = np.asarray(A[y:y+mm(6):8, x:x+mm(6):8], np.float32)
        m = t.reshape(-1, 3).mean(axis=0); s = t.reshape(-1,3).std(axis=0)
        score = m.min() - s.max()
        if best is None or score > best[0]:
            best = (score, y, x, m, s)
_, by, bx, bm, bs = best
print(f"blankest 6mm tile at y={by/DPI*25.4:.1f}mm x={bx/DPI*25.4:.1f}mm  RGB mean {bm.round(1)} std {bs.round(1)}")

# full-res patch, per channel
P = np.asarray(A[by:by+mm(8), bx:bx+mm(8)], np.float32)
R, G, B = P[:,:,0], P[:,:,1], P[:,:,2]
print(f"patch RGB medians: R {np.median(R):.1f}  G {np.median(G):.1f}  B {np.median(B):.1f}")
# yellow signature: B depressed relative to R and G
d = (R + G) / 2.0 - B
print(f"(R+G)/2 - B : median {np.median(d):.2f}  p99 {np.percentile(d,99):.2f}  "
      f"p99.9 {np.percentile(d,99.9):.2f}  max {d.max():.2f}")

# count candidate yellow dots: blobs where the blue deficit exceeds a robust threshold
from scipy import ndimage
thr = np.median(d) + 8.0 * (np.percentile(d,75) - np.percentile(d,25) + 1e-6)
mask = d > max(thr, np.median(d) + 6.0)
lab, n = ndimage.label(mask)
sizes = ndimage.sum(mask, lab, range(1, n+1))
keep = [i for i, s in enumerate(sizes, 1) if s >= 20]      # >= ~20 px at 4800dpi
area_mm2 = (P.shape[0]/DPI*25.4) * (P.shape[1]/DPI*25.4)
print(f"blue-deficit threshold {max(thr, np.median(d)+6.0):.2f}; {n} raw blobs, {len(keep)} with area>=20px")
print(f"patch area {area_mm2:.1f} mm^2  ->  {len(keep)/area_mm2:.3f} dots/mm^2 "
      f"(repo record for this engine: ~0.24 dots/mm^2)")
if keep:
    cs = ndimage.center_of_mass(mask, lab, keep)
    ys = np.array([c[0] for c in cs]); xs = np.array([c[1] for c in cs])
    px = np.sort(xs); py = np.sort(ys)
    print(f"  blob px area median {np.median([sizes[i-1] for i in keep]):.0f}")
    if len(keep) > 3:
        print(f"  x spacing (mm) between sorted neighbours: {np.round(np.diff(px)/DPI*25.4,3)[:12]}")
        print(f"  y spacing (mm) between sorted neighbours: {np.round(np.diff(py)/DPI*25.4,3)[:12]}")
Image.fromarray(np.clip((d - np.median(d)) * 12 + 128, 0, 255).astype(np.uint8)[::4,::4]).save(
    str(OUT / "mic-blue-deficit.png"))
print(f"wrote {OUT / 'mic-blue-deficit.png'} (blue-deficit map, x12 gain)")

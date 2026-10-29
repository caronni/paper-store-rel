# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# the MIC density + lattice pitch (stdout) with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/diag_mic2.py --evidence-root DIR
"""MIC yellow-dot density + lattice pitch over a larger blank area (read-only)."""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="diag_mic2")
XEROX_COLOR = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-color-canon-4800rgb.tiff"
_evidence.need(XEROX_COLOR, tool="diag_mic2")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import numpy as np, tifffile
from scipy import ndimage
DPI=4800.0
def mm(v): return int(v/25.4*DPI)
A = tifffile.memmap(str(XEROX_COLOR))

# stitch several blank margin strips (right margin band, clear of printed fields)
patches=[]
for y in range(mm(30), mm(270), mm(24)):
    P=np.asarray(A[y:y+mm(18), mm(191):mm(203)], np.float32)
    if P[:,:,1].mean() > 225:              # keep only genuinely blank
        patches.append(P)
print(f"{len(patches)} blank strips kept")
tot_area=0.0; tot_dots=0; sizes_all=[]; xs_all=[]; ys_all=[]
for P in patches:
    R,G,B = P[:,:,0],P[:,:,1],P[:,:,2]
    d=(R+G)/2.0-B
    thr=np.median(d)+6.0
    m=d>thr
    lab,n=ndimage.label(m)
    sz=ndimage.sum(m,lab,range(1,n+1))
    keep=[i for i,s in enumerate(sz,1) if 20<=s<=6000]
    if keep:
        cs=ndimage.center_of_mass(m,lab,keep)
        ys_all += [c[0] for c in cs]; xs_all += [c[1] for c in cs]
        sizes_all += [sz[i-1] for i in keep]
    tot_dots += len(keep)
    tot_area += (P.shape[0]/DPI*25.4)*(P.shape[1]/DPI*25.4)
print(f"total blank area {tot_area:.1f} mm^2, {tot_dots} yellow-signature dots")
print(f"density = {tot_dots/tot_area:.3f} dots/mm^2   (repo record 007.7/007.8: ~0.24 dots/mm^2)")
s=np.array(sizes_all)
print(f"dot area: median {np.median(s):.0f} px -> equivalent diameter {2*np.sqrt(np.median(s)/np.pi)/DPI*25.4*1000:.0f} um")
# lattice pitch: histogram of nearest-neighbour x separations within rows
xs=np.array(xs_all); ys=np.array(ys_all)
d=[]
for i in range(len(xs)):
    same=np.abs(ys-ys[i])<mm(0.15)
    dx=xs[same]-xs[i]; dx=dx[dx>mm(0.3)]
    if len(dx): d.append(dx.min())
d=np.array(d)/DPI*25.4
if len(d):
    print(f"in-row nearest-neighbour x pitch: median {np.median(d):.3f} mm  "
          f"(24 dots @600dpi = {24/600*25.4:.3f} mm)  n={len(d)}")

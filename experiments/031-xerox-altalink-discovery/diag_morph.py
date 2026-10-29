# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# build/morph.pkl (+ build/morph-cells.npy) with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/diag_morph.py --evidence-root DIR
"""Isolated black dots and white holes: fold each probe over its period (read-only).

Samples on the LAYOUT grid through the fitted affine, so rotation/scale do not
smear the fold.  Output = the average rendered dot / hole, plus core vs
background reflectance.
"""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="diag_morph")
XEROX_BW = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-bw-canon-4800grey.tiff"
M281_BW = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/captures/discovery-bw-canon-4800grey.tiff"
XEROX_BW_REPORT = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/reports/harness/hcal-report-discovery-bw-copy0000-f1e31d2b3944bf66.json"
M281_BW_REPORT = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/reports/hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json"
_evidence.need(XEROX_BW, M281_BW, XEROX_BW_REPORT, M281_BW_REPORT, tool="diag_morph")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import json
import numpy as np, tifffile
sys.path.insert(0, str(REPO / "src"))
from holo.characterize.layout import build_page

OS = 8                      # samples per layout dot (= 4800 dpi in layout space)
SHEETS = {
 "XEROX AltaLink": (str(XEROX_BW),
   str(XEROX_BW_REPORT), False),
 "HP M281":        (str(M281_BW),
   str(M281_BW_REPORT), False),
}
page = build_page(stage="discovery", kind="bw", copy_index=0, request_code=0)
P = {q["probe_id"]: q for q in page["probes"]}
WANT = [("morph/isolated_dots/8", 1, 8, "black"), ("morph/isolated_dots/10", 2, 12, "black"),
        ("morph/isolated_dots/12", 3, 16, "black"), ("morph/isolated_dots/14", 4, 20, "black"),
        ("morph/white_holes/9", 1, 8, "white"),  ("morph/white_holes/11", 2, 12, "white"),
        ("morph/white_holes/13", 3, 16, "white"), ("morph/white_holes/15", 4, 20, "white")]

def sample(A, coef, x0, y0, w, h):
    """Bilinear-sample the scan on the layout grid, OS samples per layout dot."""
    xs = x0 + np.arange(w*OS)/OS
    ys = y0 + np.arange(h*OS)/OS
    LX, LY = np.meshgrid(xs, ys)
    sx = coef[0][0]*LX + coef[0][1]*LY + coef[0][2]
    sy = coef[1][0]*LX + coef[1][1]*LY + coef[1][2]
    x_i = np.clip(sx.astype(np.int64), 0, A.shape[1]-2)
    y_i = np.clip(sy.astype(np.int64), 0, A.shape[0]-2)
    fx = (sx - x_i)[...,None] if False else (sx - x_i)
    fy = (sy - y_i)
    y0i, y1i = y_i.min(), y_i.max()+2
    x0i, x1i = x_i.min(), x_i.max()+2
    blk = np.asarray(A[y0i:y1i, x0i:x1i], np.float32)
    yy, xx = y_i-y0i, x_i-x0i
    v = (blk[yy,xx]*(1-fx)*(1-fy) + blk[yy,xx+1]*fx*(1-fy)
         + blk[yy+1,xx]*(1-fx)*fy + blk[yy+1,xx+1]*fx*fy)
    return v

out = {}
cells = {}
for name,(scan, rep, _c) in SHEETS.items():
    A = tifffile.memmap(scan)
    coef = json.load(open(rep))["geometry"]["affine_layout_to_scan"]
    print(f"\n================ {name} ================")
    print(f"{'probe':<26}{'size':<7}{'pitch':<7}{'core refl':>11}{'bg refl':>10}{'contrast':>11}{'ink Ø µm':>11}")
    for pid, size, pitch, kind in WANT:
        q = P[pid]
        w = int(q["w_layout_dots"]//pitch*pitch); h = int(q["h_layout_dots"]//pitch*pitch)
        v = sample(A, coef, q["x_layout_dots"], q["y_layout_dots"], w, h)
        per = pitch*OS
        ny, nx = h//pitch, w//pitch
        cell = v[:ny*per, :nx*per].reshape(ny, per, nx, per).mean(axis=(0,2))
        white = float(np.percentile(v, 99.5))
        cell_n = cell/white
        cells[(name,pid)] = cell_n
        if kind=="black":
            core = float(cell_n.min()); bg = float(np.percentile(cell_n, 90))
            ink = (cell_n < (bg+core)/2).sum()
        else:
            core = float(cell_n.max()); bg = float(np.percentile(cell_n, 10))
            ink = (cell_n > (bg+core)/2).sum()
        dia = 2*np.sqrt(max(ink,1)/np.pi)/OS/600*25400
        out[(name,pid)] = (core,bg,abs(core-bg),dia)
        print(f"{pid:<26}{f'{size}x{size}':<7}{pitch:<7}{core:11.4f}{bg:10.4f}{abs(core-bg):11.4f}{dia:11.0f}")
np.save(str(OUT / "morph-cells.npy"), np.array([1]))
import pickle
pickle.dump({"cells":cells,"stats":out}, open(str(OUT / "morph.pkl"),"wb"))
print("\ncore = darkest (black dots) / brightest (white holes) point of the period-averaged cell,")
print("normalised to the probe's own paper white; bg = the surrounding field.")

# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# build/stroke-continuity.json (robust centring) with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/diag_strokes2.py --evidence-root DIR
"""3-dot K stroke rendering, ROBUSTLY centred on each cross (read-only)."""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="diag_strokes2")
XEROX_COLOR = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-color-canon-4800rgb.tiff"
XEROX_BW = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-bw-canon-4800grey.tiff"
M281_BW = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/captures/discovery-bw-canon-4800grey.tiff"
XEROX_COLOR_REPORT = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/reports/production/hcal-report-discovery-color-copy0000-82abef068de7c651.json"
M281_BW_REPORT = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/reports/hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json"
CORNER_FIT = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/records/corner_fit.npy"
_evidence.need(XEROX_COLOR, XEROX_BW, M281_BW, XEROX_COLOR_REPORT, M281_BW_REPORT, CORNER_FIT, tool="diag_strokes2")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import json
import numpy as np, tifffile

LAYOUT_DPI, DPI = 600.0, 4800.0
D = DPI / LAYOUT_DPI
ARM = int(55 * D)          # sample 55 layout dots either side of centre (cross half = 61)
SEARCH = 300               # px: robust centring search radius
CENTRES = {1: (15.0, 15.0, "TL"), 2: (195.0, 15.0, "TR"),
           3: (195.0, 282.0, "BR"), 4: (15.0, 282.0, "BL")}

def centre_px(coef, mx, my):
    lx, ly = mx * LAYOUT_DPI / 25.4, my * LAYOUT_DPI / 25.4
    return (coef[0][0]*lx + coef[0][1]*ly + coef[0][2],
            coef[1][0]*lx + coef[1][1]*ly + coef[1][2])

def measure(path, coef, label, color=False):
    A = tifffile.memmap(path)
    print(f"\n===== {label} =====")
    print(f"{'cnr':>6} {'paper':>5} {'recentre(px)':>13} | "
          f"{'H: dark  med   w_px  gap%':>28} | {'V: dark  med   w_px  gap%':>28}")
    out = {}
    for k, (mx, my, nm) in CENTRES.items():
        cx, cy = centre_px(coef, mx, my)
        x, y = int(round(cx)), int(round(cy))
        W = ARM + SEARCH + 60
        blk = np.asarray(A[y-W:y+W, x-W:x+W], dtype=np.float32)
        if color: blk = blk.mean(axis=2)
        paper = float(np.percentile(blk, 95))
        c = W
        # robust centring: the cross arms are the darkest full-length row/column
        colm = blk[c-ARM:c+ARM, c-SEARCH:c+SEARCH].mean(axis=0)
        rowm = blk[c-SEARCH:c+SEARCH, c-ARM:c+ARM].mean(axis=1)
        vx = c - SEARCH + int(np.argmin(colm))
        hy = c - SEARCH + int(np.argmin(rowm))
        dx_px, dy_px = vx - c, hy - c
        res = {}
        for name, band in (("H", blk[hy-14:hy+15, vx-ARM:vx+ARM]),
                           ("V", blk[hy-ARM:hy+ARM, vx-14:vx+15].T)):
            prof = band.min(axis=0) / max(paper, 1.0)
            # effective stroke width: px per along-arm sample below 70% paper
            width = float((band / max(paper, 1.0) < 0.70).sum(axis=0).mean())
            res[name] = (float(prof.min()), float(np.median(prof)), width,
                         float((prof > 0.60).mean()) * 100.0)
        out[nm] = res
        print(f"{k} {nm:>3} {paper:5.0f} {dx_px:+6d}{dy_px:+6d}  | "
              f"{res['H'][0]:8.3f}{res['H'][1]:6.3f}{res['H'][2]:6.1f}{res['H'][3]:6.1f}%  | "
              f"{res['V'][0]:8.3f}{res['V'][1]:6.3f}{res['V'][2]:6.1f}{res['V'][3]:6.1f}%")
    return out

fit = np.load(str(CORNER_FIT)); R, t = fit[:2], fit[2]
xcoef = [[R[0,0], R[0,1], t[0]], [R[1,0], R[1,1], t[1]]]
C = json.load(open(str(XEROX_COLOR_REPORT)))
M = json.load(open(str(M281_BW_REPORT)))

r = {}
r["xerox_bw"]    = measure(str(XEROX_BW), xcoef,
                           "XEROX AltaLink -- B/W sheet (refused at registration)")
r["xerox_color"] = measure(str(XEROX_COLOR),
                           C["geometry"]["affine_layout_to_scan"],
                           "XEROX AltaLink -- COLOR sheet (analyzed OK)", color=True)
r["m281_bw"]     = measure(str(M281_BW),
                           M["geometry"]["affine_layout_to_scan"],
                           "HP M281 -- B/W sheet e028 (healthy K toner)")
json.dump(r, open(str(OUT / "stroke-continuity.json"), "w"), indent=1)
print("\nw_px = mean stroke width in scan px below 70% paper (nominal 3 layout dots = 24 px)")
print("gap% = along-arm samples whose darkest pixel never reaches 60% of paper white")

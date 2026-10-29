# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# build/stroke-continuity.json with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/diag_strokes.py --evidence-root DIR
"""3-dot K stroke continuity at the four corner crosses, three sheets (read-only)."""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="diag_strokes")
XEROX_COLOR = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-color-canon-4800rgb.tiff"
XEROX_BW = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-bw-canon-4800grey.tiff"
M281_BW = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/captures/discovery-bw-canon-4800grey.tiff"
XEROX_COLOR_REPORT = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/reports/production/hcal-report-discovery-color-copy0000-82abef068de7c651.json"
M281_BW_REPORT = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/reports/hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json"
CORNER_FIT = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/records/corner_fit.npy"
_evidence.need(XEROX_COLOR, XEROX_BW, M281_BW, XEROX_COLOR_REPORT, M281_BW_REPORT, CORNER_FIT, tool="diag_strokes")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import json
import numpy as np, tifffile

LAYOUT_DPI, DPI = 600.0, 4800.0
D = DPI / LAYOUT_DPI                      # 8 scan px per layout dot
ARM = int(61 * D)                         # half cross span, px (~488)
HALF = 40                                 # +- px across the stroke
CENTRES = {1: (15.0, 15.0, "TL"), 2: (195.0, 15.0, "TR"),
           3: (195.0, 282.0, "BR"), 4: (15.0, 282.0, "BL")}

def load(path, color=False):
    a = tifffile.memmap(path)
    return a

def centre_px(coef, mx, my):
    lx, ly = mx * LAYOUT_DPI / 25.4, my * LAYOUT_DPI / 25.4
    x = coef[0][0]*lx + coef[0][1]*ly + coef[0][2]
    y = coef[1][0]*lx + coef[1][1]*ly + coef[1][2]
    return x, y

def measure(A, coef, label, color=False):
    print(f"\n===== {label} =====")
    print(f"{'corner':>7} {'paper':>6} | {'HORIZONTAL arm':>28} | {'VERTICAL arm':>28}")
    print(f"{'':>7} {'':>6} | {'darkest':>8}{'median':>9}{'gap%':>7}{'':>4} | {'darkest':>8}{'median':>9}{'gap%':>7}")
    out = {}
    for k, (mx, my, nm) in CENTRES.items():
        cx, cy = centre_px(coef, mx, my)
        x, y = int(round(cx)), int(round(cy))
        W = ARM + 120
        blk = np.asarray(A[y-W:y+W, x-W:x+W], dtype=np.float32)
        if color: blk = blk.mean(axis=2)
        paper = float(np.percentile(blk, 95))
        c = W  # local centre
        # refine: vertical stroke x = argmin of column means; horizontal y = argmin row means
        colm = blk[c-ARM:c+ARM, c-HALF:c+HALF].mean(axis=0)
        rowm = blk[c-HALF:c+HALF, c-ARM:c+ARM].mean(axis=1)
        vx = c - HALF + int(np.argmin(colm))
        hy = c - HALF + int(np.argmin(rowm))
        res = {}
        for name, prof in (
            ("H", blk[hy-12:hy+13, c-ARM:c+ARM].min(axis=0)),
            ("V", blk[c-ARM:c+ARM, vx-12:vx+13].min(axis=1)),
        ):
            p = prof / max(paper, 1.0)
            # "gap" = along-arm samples that never get below 60% of paper white
            res[name] = (float(p.min()), float(np.median(p)), float((p > 0.60).mean()) * 100.0)
        out[nm] = res
        print(f"{k} {nm:>4} {paper:6.0f} | {res['H'][0]:8.3f}{res['H'][1]:9.3f}{res['H'][2]:7.1f}%    "
              f"| {res['V'][0]:8.3f}{res['V'][1]:9.3f}{res['V'][2]:7.1f}%")
    return out

# 1. Xerox B/W -- similarity fit recovered from corners 3+4
fit = np.load(str(CORNER_FIT))
R, t = fit[:2], fit[2]
xcoef = [[R[0,0], R[0,1], t[0]], [R[1,0], R[1,1], t[1]]]
xb = measure(load(str(XEROX_BW)), xcoef,
             "XEROX AltaLink C8245 -- B/W discovery sheet (REFUSED at registration)")

# 2. Xerox color -- report affine
C = json.load(open(str(XEROX_COLOR_REPORT)))
xc = measure(load(str(XEROX_COLOR)),
             C["geometry"]["affine_layout_to_scan"],
             "XEROX AltaLink C8245 -- COLOR discovery sheet (analyzed OK)", color=True)

# 3. M281 B/W -- report affine
M = json.load(open(str(M281_BW_REPORT)))
mb = measure(load(str(M281_BW)),
             M["geometry"]["affine_layout_to_scan"],
             "HP M281fdw -- B/W discovery sheet e028 (analyzed OK, healthy K toner)")

json.dump({"xerox_bw": xb, "xerox_color": xc, "m281_bw": mb},
          open(str(OUT / "stroke-continuity.json"), "w"), indent=1)
print("\n(gap% = fraction of the 3-dot arm whose darkest pixel never reaches 60% of paper white)")

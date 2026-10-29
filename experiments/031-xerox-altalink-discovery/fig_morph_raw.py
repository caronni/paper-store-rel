# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# build/e031-single-dot-raw.png with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/fig_morph_raw.py --evidence-root DIR
"""Raw, unaveraged crops of the 1-dot and 2-dot morphology probes."""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="fig_morph_raw")
XEROX_BW = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-bw-canon-4800grey.tiff"
M281_BW = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/captures/discovery-bw-canon-4800grey.tiff"
XEROX_BW_REPORT = EV / "paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/reports/harness/hcal-report-discovery-bw-copy0000-f1e31d2b3944bf66.json"
M281_BW_REPORT = EV / "paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/reports/hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json"
_evidence.need(XEROX_BW, M281_BW, XEROX_BW_REPORT, M281_BW_REPORT, tool="fig_morph_raw")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import json
import numpy as np, tifffile
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(REPO / "src"))
from holo.characterize.layout import build_page
def F(s):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf","/System/Library/Fonts/Helvetica.ttc"):
        try: return ImageFont.truetype(p,s)
        except Exception: pass
    return ImageFont.load_default()
f9,f11,f13,f20 = F(14),F(16),F(20),F(29)

page=build_page(stage="discovery",kind="bw",copy_index=0,request_code=0)
P={q["probe_id"]:q for q in page["probes"]}
SH={"XEROX AltaLink":(str(XEROX_BW),
      str(XEROX_BW_REPORT)),
    "HP M281":(str(M281_BW),
      str(M281_BW_REPORT))}
COLS=[("morph/isolated_dots/8","1x1 BLACK dot, pitch 8"),
      ("morph/isolated_dots/10","2x2 BLACK dot, pitch 12"),
      ("morph/white_holes/9","1x1 WHITE hole, pitch 8"),
      ("morph/white_holes/11","2x2 WHITE hole, pitch 12")]
MM=1.30
SIDE=int(MM/25.4*4800)      # 246 px at 4800 dpi
ZOOM=2
TS=SIDE*ZOOM
GAP=34; LEFT=200; TOP=140
W=LEFT+4*(TS+GAP)+GAP; H=TOP+2*(TS+82)+70
im=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(im)
d.text((28,20),"Raw scan, no averaging — 1-dot vs 2-dot, both polarities",font=f20,fill=(15,15,15))
d.text((28,58),f"each tile is {MM} mm square of the actual sheet, Canon 4800 dpi, shown at 2x (1 displayed px = 2.6 µm). "
               "600-dpi dot pitch = 42.3 µm.",font=f11,fill=(95,95,95))
d.text((28,80),"the 1-dot lattices carry a dot every 8 layout dots = every 0.34 mm, so ~15 sites are visible per tile.",font=f11,fill=(95,95,95))

for r,(eng,(scan,rep)) in enumerate(SH.items()):
    A=tifffile.memmap(scan)
    co=json.load(open(rep))["geometry"]["affine_layout_to_scan"]
    y=TOP+r*(TS+82)
    d.text((28,y+TS//2-16),eng,font=f13,fill=(20,20,20))
    for c,(pid,lab) in enumerate(COLS):
        q=P[pid]
        lx=q["x_layout_dots"]+q["w_layout_dots"]/2
        ly=q["y_layout_dots"]+q["h_layout_dots"]/2
        sx=co[0][0]*lx+co[0][1]*ly+co[0][2]; sy=co[1][0]*lx+co[1][1]*ly+co[1][2]
        x0,y0=int(sx-SIDE//2),int(sy-SIDE//2)
        t=np.asarray(A[y0:y0+SIDE, x0:x0+SIDE])
        img=Image.fromarray(t).resize((TS,TS),Image.NEAREST)
        X=LEFT+c*(TS+GAP)
        im.paste(img,(X,y))
        d.rectangle([X-1,y-1,X+TS,y+TS],outline=(140,140,140))
        if r==0: d.text((X,y-30),lab,font=f11,fill=(40,40,40))
im.save(str(OUT / "e031-single-dot-raw.png"))
print("wrote", im.size)

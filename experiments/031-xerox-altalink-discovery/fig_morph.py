# Historical record of e031 (AltaLink discovery: MIC dots, cell=1 morphology, stroke continuity), retired from
# scratch/e031/ 2026-10-09; inputs (captures, reports, corner_fit.npy) in the evidence archive. Regenerates
# build/e031-single-dot.png (after diag_morph.py) with: PYTHONPATH=src:. env/bin/python experiments/031-xerox-altalink-discovery/fig_morph.py --evidence-root DIR
"""Single black dot / single white hole at 600 dpi — period-averaged and raw."""
import argparse
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from measure import _evidence
_AP = argparse.ArgumentParser()
_evidence.add_argument(_AP)
EV = _evidence.resolve(_AP.parse_args().evidence_root, tool="fig_morph")
OUT = REPO / "experiments/031-xerox-altalink-discovery/build"
OUT.mkdir(parents=True, exist_ok=True)
import pickle
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(REPO / "src"))
from holo.characterize.layout import build_page
def F(s):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf","/System/Library/Fonts/Helvetica.ttc"):
        try: return ImageFont.truetype(p,s)
        except Exception: pass
    return ImageFont.load_default()
f9,f11,f13,f16,f20 = F(14),F(16),F(19),F(23),F(29)

D=pickle.load(open(str(OUT / "morph.pkl"),"rb")); cells=D["cells"]; stats=D["stats"]
page=build_page(stage="discovery",kind="bw",copy_index=0,request_code=0)
P={q["probe_id"]:q for q in page["probes"]}
BLACK=[("morph/isolated_dots/8",1,8),("morph/isolated_dots/10",2,12),
       ("morph/isolated_dots/12",3,16),("morph/isolated_dots/14",4,20)]
WHITE=[("morph/white_holes/9",1,8),("morph/white_holes/11",2,12),
       ("morph/white_holes/13",3,16),("morph/white_holes/15",4,20)]
ENG=["XEROX AltaLink","HP M281"]
SC=3.2                       # display magnification of the averaged cell
CW=int(20*8*SC)              # widest cell (pitch 20) sets the column width
GAP=30; LEFT=210; TOP=150
W=LEFT+4*(CW+GAP)+GAP; H=TOP+4*(CW+118)+250
im=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(im)
d.text((28,20),"Isolated 1-dot performance at 600 dpi — period-averaged cell from the real scan",font=f20,fill=(15,15,15))
d.text((28,56),"Each panel is the probe folded over its own lattice period (≈1000 periods averaged), sampled on the layout grid through the fitted affine.",font=f11,fill=(95,95,95))
d.text((28,76),"Panels are at TRUE relative scale: the 1-dot cell is 0.34 mm across, the 4-dot cell 0.85 mm. Contrast is normalised to each probe's own paper white.",font=f11,fill=(95,95,95))
d.text((28,96),"CAVEAT: this ladder varies feature size AND lattice pitch together (1@8, 2@12, 3@16, 4@20 dots) — they are not separated.",font=f11,fill=(150,90,20))

def draw_row(ridx, eng, items, kind):
    y=TOP+ridx*(CW+118)
    d.text((28,y+CW//2-30),eng,font=f13,fill=(20,20,20))
    d.text((28,y+CW//2-8),("black dots on paper" if kind=="black" else "white holes in solid"),
           font=f9,fill=(110,110,110))
    d.text((28,y+CW//2+10),"(ink present)" if kind=="black" else "(ink absent)",font=f9,fill=(150,150,150))
    for i,(pid,size,pitch) in enumerate(items):
        c=cells[(eng,pid)]
        side=int(pitch*8*SC)
        img=Image.fromarray(np.clip(c*255,0,255).astype(np.uint8)).resize((side,side),Image.NEAREST)
        X=LEFT+i*(CW+GAP)+(CW-side)//2
        im.paste(img,(X,y+(CW-side)//2))
        d.rectangle([X-1,y+(CW-side)//2-1,X+side,y+(CW-side)//2+side],outline=(150,150,150))
        core,bg,con,dia=stats[(eng,pid)]
        cx=LEFT+i*(CW+GAP)
        dead = con < 0.10
        d.text((cx,y+CW+8),f"{size}x{size} dot, pitch {pitch}",font=f11,fill=(40,40,40))
        d.text((cx,y+CW+30),f"contrast {con:.3f}",font=f16,fill=(190,30,30) if dead else (25,110,60))
        d.text((cx,y+CW+58),f"core {core:.3f}   field {bg:.3f}",font=f9,fill=(110,110,110))
        if dead: d.text((cx,y+CW+76),"→ does not resolve",font=f9,fill=(190,30,30))

draw_row(0,"XEROX AltaLink",BLACK,"black")
draw_row(1,"HP M281",BLACK,"black")
draw_row(2,"XEROX AltaLink",WHITE,"white")
draw_row(3,"HP M281",WHITE,"white")

yb=TOP+4*(CW+118)+16
d.line([28,yb,W-28,yb],fill=(200,200,200),width=1)
d.text((28,yb+14),"The 600-dpi single-dot verdict, both polarities:",font=f13,fill=(15,15,15))
lines=[
 ("single BLACK dot", "AltaLink 0.060 contrast   •   M281 0.013", "both far below usable; the AltaLink lays ~4.6x more ink for one dot but it is still not a cell"),
 ("single WHITE hole","AltaLink 0.044 contrast   •   M281 0.068", "the hole never opens on either engine — solid closes over a 1-dot void"),
 ("the 2x2 step",      "black 0.286/0.362   white 0.467/0.531",   "5-10x jump in both polarities: this is where 'cell=1 dead' actually bites"),
]
for i,(a,b,c) in enumerate(lines):
    yy=yb+42+i*30
    d.text((44,yy),a,font=f11,fill=(40,40,40))
    d.text((240,yy),b,font=f11,fill=(20,20,20))
    d.text((560,yy),c,font=f9,fill=(110,110,110))
im.save(str(OUT / "e031-single-dot.png"))
print("wrote", OUT / "e031-single-dot.png", im.size)

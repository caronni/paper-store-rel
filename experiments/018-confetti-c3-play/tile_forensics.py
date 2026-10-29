#!/usr/bin/env python
"""e018 failed-tile forensics (018.7 instrument): why is this tile orange?

Reconstructs EXACTLY what the LDPC decoder saw (weighted_sum combined LLR
via gather_tile_llrs) and compares against the PRINTED truth from
build/e018_gt/ (source-independent — gen_e018.make_data() re-tars the
LIVE source and drifts on any CORE edit; measured trap, 018.7). Per
interior tile: raw pre-LDPC cell BER, 64x64 error map, |LLR| confidence
map. Renders the certified-vs-failed cliff histogram + representative
MARGINAL / MID / BROKEN tiles.

Truth-domain notes that cost an afternoon (do not re-derive): the slot
raster of gather_tile_llrs pairs with ldpc._tile_payload_indices — NOT
encode_tile's codeword order; the honest per-tile BER =
mean(sign(llr[slots]) != truth[pidx]) over OBSERVED slots only.

  env/bin/python experiments/018-confetti-c3-play/tile_forensics.py \
      --state <evidence>/e018/try_2/e018-session_state.pkl \
      [--e018-gt DIR] [--out PNG]
"""
import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
from paperholo import ldpc, compose                       # noqa: E402
from paperholo.compose import _payload_keystream          # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--state", type=Path, required=True)
_ap.add_argument("--e018-gt", type=Path,
                 default=_ROOT / "experiments/018-confetti-c3-play/build/e018_gt")
_ap.add_argument("--out", type=Path,
                 default=_ROOT / "experiments/018-confetti-c3-play/build/e018_failed_tiles.png")
_args = _ap.parse_args()
OUT = _args.out.parent
OUT.mkdir(parents=True, exist_ok=True)
pds, done = pickle.loads(_args.state.read_bytes())
spec, seed = pds.spec, pds.seed
H, W = spec.page_cells_yx
gt = np.load(str(_args.e018_gt / "K__e018_field.npy"))
gt = gt.reshape(H, 3, W, 3)[:, 0, :, 0].astype(np.uint8)   # dots -> cells
ks = _payload_keystream(spec, seed, 0).astype(np.uint8)
true_cell = gt ^ ks
pim = compose.payload_index_map(spec, seed)
N = int(pim.max()) + 1
truthN = np.zeros(N, np.uint8)
ys, xs = np.nonzero(pim >= 0); truthN[pim[ys, xs]] = true_cell[ys, xs]
idx_p, llr_p, _ = pds.combined_llrs("weighted_sum")


def tile(t):
    llr4096, short, cov = ldpc.gather_tile_llrs(llr_p, idx_p, spec, seed, t)
    slots = np.flatnonzero(~short.astype(bool))
    pidx = ldpc._tile_payload_indices(t, spec, seed, short)
    lv = llr4096[slots]
    truth = truthN[pidx]
    hard = (lv > 0).astype(np.uint8)
    obs = lv != 0.0
    err = hard != truth
    ber = float(err[obs].mean()) if obs.any() else float("nan")
    sy, sx = np.divmod(slots, 64)
    E = np.zeros((64, 64), np.int8); E[sy, sx] = np.where(err, 1, -1) * obs
    L = np.full((64, 64), np.nan); L[sy, sx] = np.where(obs, np.abs(lv), np.nan)
    return dict(t=t, cov=float(cov), ber=ber, nobs=int(obs.sum()),
                nerr=int(err[obs].sum()), E=E, L=L,
                lv=lv[obs], err=err[obs])


rows = []
for t, st in pds.tiles.items():
    if st.status == "degenerate":
        continue
    r = tile(t); r["status"] = st.status
    rows.append(r)
cert = np.array([r["ber"] for r in rows if r["status"] == "certified"])
assert cert.mean() < 0.09, f"truth still wrong: cert BER {cert.mean()}"
fcov = [r for r in rows if r["status"] == "failed" and r["cov"] >= 0.9]
fb = np.array([r["ber"] for r in fcov])
cliff = cert.max()
print(f"certified BER: mean {cert.mean():.3f} p95 {np.percentile(cert,95):.3f} max {cliff:.3f}")
print(f"failed(>=.9) : n={len(fb)} mean {fb.mean():.3f} min {fb.min():.3f} "
      f"p25 {np.percentile(fb,25):.3f} p50 {np.median(fb):.3f} p75 "
      f"{np.percentile(fb,75):.3f} max {fb.max():.3f}")
print(f"MARGINAL (BER<=cliff {cliff:.3f}): {(fb<=cliff).sum()}/{len(fb)}   "
      f"NEAR (<=2x cliff): {(fb<=2*cliff).sum()}   BROKEN (>0.25): {(fb>0.25).sum()}")
lw = np.concatenate([r["lv"][r["err"]] for r in fcov])
lr = np.concatenate([r["lv"][~r["err"]] for r in fcov])
print(f"failed |LLR|: wrong {np.abs(lw).mean():.2f}  right {np.abs(lr).mean():.2f}  "
      f"(errors are {'CONFIDENT' if np.abs(lw).mean()>0.5*np.abs(lr).mean() else 'low-conf'})")

# ---- render ----
def font(s):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", s)
    except Exception:
        return ImageFont.load_default()
f22, f15, f12 = font(23), font(15), font(12)
fcov.sort(key=lambda r: r["ber"])
picks = [("MARGINAL (just over cliff)", fcov[0]),
         ("MID", min(fcov, key=lambda r: abs(r["ber"]-0.16))),
         ("BROKEN", fcov[-1])]
CELL = 7; PW = 64 * CELL


def err_img(r):
    im = np.full((64, 64, 3), 234, np.uint8)
    im[r["E"] == -1] = (223, 236, 223)
    im[r["E"] == 1] = (214, 39, 40)
    return Image.fromarray(im).resize((PW, PW), Image.NEAREST)


def conf_img(r):
    a = r["L"]; fin = np.isfinite(a)
    hi = np.nanpercentile(a, 95) if fin.any() else 1
    v = np.clip(np.nan_to_num(a) / (hi + 1e-9), 0, 1)
    im = np.stack([np.where(fin, 250-205*v, 234),
                   np.where(fin, 70+150*v, 234),
                   np.where(fin, 55, 234)], -1).astype(np.uint8)
    return Image.fromarray(im).resize((PW, PW), Image.NEAREST)


Wc = 48 + 2 * PW + 30
Hc = 250 + len(picks) * (PW + 46)
c = Image.new("RGB", (Wc, Hc), (255, 255, 255)); dr = ImageDraw.Draw(c)
dr.text((24, 16), "e018 failed-tile forensics (printed-GT truth)", fill=(0, 0, 0), font=f22)
dr.text((24, 48), f"r0550 cliff = {cliff*100:.0f}% (max certified). "
        f"marginal failed (BER<=cliff): {(fb<=cliff).sum()}/{len(fb)} · "
        f"broken (>25%): {(fb>0.25).sum()}", fill=(90, 90, 90), font=f15)
# histogram
hy, hh = 78, 150
bins = np.linspace(0, 0.5, 26)
ch, _ = np.histogram(cert, bins); fh, _ = np.histogram(fb, bins)
mx = max(ch.max(), fh.max(), 1); base = hy + hh - 20
for i in range(25):
    x0 = 30 + i * (Wc - 70) // 25; wb = (Wc - 70) // 25 - 1
    d1 = ch[i]*(hh-30)//mx; d2 = fh[i]*(hh-30)//mx
    dr.rectangle([x0, base-d1, x0+wb//2, base], fill=(44, 160, 44))
    dr.rectangle([x0+wb//2, base-d2, x0+wb, base], fill=(255, 127, 14))
cx = 30 + int(cliff/0.5*(Wc-70))
dr.line([cx, hy, cx, base], fill=(0, 0, 0), width=2)
dr.text((cx+4, hy), f"cliff {cliff*100:.0f}%", fill=(0, 0, 0), font=f12)
dr.text((30, hy-4), "raw cell BER  ·  green=certified  orange=failed",
        fill=(90, 90, 90), font=f12)
dr.text((26, base+4), "0%", fill=(120, 120, 120), font=f12)
dr.text((Wc-64, base+4), "50%", fill=(120, 120, 120), font=f12)
y = base + 40
dr.text((24, y), "LEFT error map: red=wrong pale=right grey=unobserved   "
        "RIGHT confidence |LLR|: green=sure yellow=unsure", fill=(60, 60, 60), font=f12)
y += 22
for label, r in picks:
    dr.text((24, y), f"{label} · tile {r['t']} · BER {r['ber']*100:.1f}% · "
            f"cov {r['cov']*100:.0f}% · {r['nerr']} errors of {r['nobs']}",
            fill=(0, 0, 0), font=f15)
    c.paste(err_img(r), (24, y+24)); c.paste(conf_img(r), (24+PW+30, y+24))
    y += PW + 46
c.save(_args.out)
print("wrote", _args.out)

#!/usr/bin/env python
"""exp-019 comparison: the payload lattices exp-019 acquires
(segment.find_lattice_candidates — MODULATION) vs the patches the 018
receiver's segmenter finds (segment.segment_pieces — |mean-backing|), on the
same scan at the same footing. Only the detector differs.

Emits a red/blue overlay PNG + a printed diff: counts, deviation-only patches
with their per-mask modulation std (proof they carry no data), matched-patch
area ratio. Native by default; --decimate N for a fast look.

  env/bin/python compare_texture_vs_deviation.py <scan> --dpi 4800 [--decimate N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/019-platen-segment"))

from paperholo import segment                       # noqa: E402
import analyze_e019 as A                             # noqa: E402
import decimate_scan                                 # noqa: E402

Image.MAX_IMAGE_PIXELS = None
DEV_COL = (220, 40, 40)      # red  = deviation (018 receiver segmenter)
TEX_COL = (60, 130, 255)     # blue = modulation (019 lattice candidates)


def _bb(p):
    return p.bbox_glass if hasattr(p, "bbox_glass") else p.bbox      # y0,x0,h,w


def _mask(p):
    return p.mask_glass if hasattr(p, "mask_glass") else p.mask


def _rect(p):
    y0, x0, h, w = _bb(p)
    return y0, x0, y0 + h, x0 + w


def _overlaps(a, b) -> bool:
    ay0, ax0, ay1, ax1 = _rect(a)
    by0, bx0, by1, bx1 = _rect(b)
    return not (ay1 <= by0 or by1 <= ay0 or ax1 <= bx0 or bx1 <= ax0)


def _mod_std(im, p, d):
    """Mean per-cell std inside a patch mask — the modulation it carries."""
    y0, x0, h, w = _bb(p)
    sub = im[y0:y0 + h, x0:x0 + w]
    m = ndimage_uniform(sub, d)
    v = ndimage_uniform(sub * sub, d) - m * m
    std = np.sqrt(np.clip(v, 0, None))[d // 2::d, d // 2::d]
    mk = _mask(p)[d // 2::d, d // 2::d]
    ny, nx = min(std.shape[0], mk.shape[0]), min(std.shape[1], mk.shape[1])
    std, mk = std[:ny, :nx], mk[:ny, :nx]
    return float(std[mk].mean()) if mk.any() else 0.0


def ndimage_uniform(a, d):
    from scipy import ndimage
    return ndimage.uniform_filter(a, d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--dpi", type=float, required=True)
    ap.add_argument("--decimate", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--target-w", type=int, default=2200)
    args = ap.parse_args()

    src = A.load_img(args.image)
    f = max(1, args.decimate)
    work = np.asarray(src) if f == 1 else decimate_scan.decimate(src, f)
    wd = args.dpi / f
    cell_px = wd / 600.0 * 3.0
    d = max(2, int(round(cell_px)))
    im = np.asarray(work, np.float32)

    dev = segment.segment_pieces(im, cell_px=cell_px, dpi=wd)          # 018
    tex = segment.find_lattice_candidates(im, cell_px=cell_px, dpi=wd)  # 019

    dev_only = [p for p in dev if not any(_overlaps(p, t) for t in tex)]
    tex_only = [t for t in tex if not any(_overlaps(t, p) for p in dev)]
    print(f"{args.image.name} @ {wd:.0f} dpi (cell_px={cell_px:.0f}):")
    print(f"  deviation (018): {len(dev)} patches   modulation (019): "
          f"{len(tex)} candidates")
    print(f"  deviation-ONLY (018 finds, 019 rejects): {len(dev_only)}")
    for p in sorted(dev_only, key=lambda q: -q.area_mm2):
        y0, x0, h, w = _bb(p)
        s = _mod_std(im, p, d)
        mn = float(im[y0:y0 + h, x0:x0 + w][_mask(p)].mean())
        print(f"     area {p.area_mm2:7.0f} mm²  mean {mn:5.0f}  mod-std "
              f"{s:4.1f}  (< {segment.STD_LO:.0f} => carries no data)")
    print(f"  modulation-ONLY (019 finds, 018 misses): {len(tex_only)}")
    ratios = []
    for t in tex:
        cand = [p for p in dev if _overlaps(p, t)]
        if cand:
            dp = max(cand, key=lambda p: p.area_mm2)
            ratios.append(dp.area_mm2 / max(t.area_mm2, 1e-6))
    if ratios:
        print(f"  matched dev/019 area ratio: median {np.median(ratios):.2f} "
              f"(>1 = deviation includes paper margin/edge the field excludes)")

    dn = 4
    pv = im[::dn, ::dn]
    pv = np.clip((pv - pv.min()) / (np.ptp(pv) + 1e-6) * 255,
                 0, 255).astype(np.uint8)
    img = Image.fromarray(pv).convert("RGB")
    scale = args.target_w / img.width
    img = img.resize((args.target_w, max(1, int(img.height * scale))))
    dr = ImageDraw.Draw(img)
    ss = scale / dn
    for p in dev:
        y0, x0, y1, x1 = _rect(p)
        dr.rectangle([x0 * ss, y0 * ss, x1 * ss, y1 * ss],
                     outline=DEV_COL, width=3)
    for t in tex:
        y0, x0, y1, x1 = _rect(t)
        dr.rectangle([x0 * ss, y0 * ss, x1 * ss, y1 * ss],
                     outline=TEX_COL, width=2)
    dr.text((6, 6), f"{args.image.name}  RED=deviation(018) {len(dev)}   "
            f"BLUE=modulation(019) {len(tex)}   dev-only(rejected) "
            f"{len(dev_only)}", fill=(255, 255, 255), font=A._font(15),
            stroke_width=2, stroke_fill=(0, 0, 0))
    out = args.out or (ROOT / "experiments/019-platen-segment/build"
                       / f"compare_{args.image.stem}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

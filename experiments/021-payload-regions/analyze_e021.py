#!/usr/bin/env python
"""e021 driver: platen scan -> candidate regions/global c -> annotated PNG.

Input config = scan dpi. Every returned region is a candidate; validity is
e022's pilot/BCH job. The PNG draws orange bboxes and pale-blue
(150,200,235) candidate-mask contours. The title carries the platen-wide c
and measured scan pitch; labels carry area and an optional angle hint.

  env/bin/python analyze_e021.py <scan> --dpi 4800 [--out PNG]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import platen                    # noqa: E402

Image.MAX_IMAGE_PIXELS = None

MASK_COL = (150, 200, 235)      # pale blue: tight payload-region boundary
REGION_COL = (255, 165, 0)      # orange: survey candidate


def _font(sz: int):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def load_img(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        arr = tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
        if arr.ndim == 3:                       # RGB scan -> luma
            return arr[..., :3].mean(2, dtype=np.float32)
        return arr
    return np.asarray(Image.open(path).convert("L"))


def _label(i: int, r) -> str:
    parts = [f"{i}", f"{r.area_mm2:.0f}mm²"]
    if r.angle_hint_deg is not None:
        parts.append(f"angle≈{r.angle_hint_deg:+.1f}°")
    return "  ".join(parts)


def annotate(src: np.ndarray, regions, *, target_w: int = 2200,
             preview_down: int = 4, title: str = "") -> Image.Image:
    d = preview_down
    pv = np.asarray(src[::d, ::d], np.float32)
    pv = np.clip((pv - pv.min()) / (np.ptp(pv) + 1e-6) * 255,
                 0, 255).astype(np.uint8)
    im = Image.fromarray(pv).convert("RGB")
    scale = target_w / im.width
    im = im.resize((target_w, max(1, int(im.height * scale))))
    dr = ImageDraw.Draw(im)
    s = scale / d
    for i, r in enumerate(regions):
        y0, x0, h, w = r.bbox
        mg = r.mask
        if mg is not None and mg.any():          # per-pixel tight contour
            st = max(1, int(round(1.0 / s / 2)))
            ms = mg[::st, ::st]
            edge = (ms ^ np.roll(ms, 1, 0)) | (ms ^ np.roll(ms, 1, 1))
            edge[0, :] = False                   # no roll wraparound
            edge[:, 0] = False
            ys, xs = np.nonzero(edge)
            gs = st * s
            pts = [(x0 * s + xx * gs, y0 * s + yy * gs)
                   for yy, xx in zip(ys, xs)]
            if pts:
                dr.point(pts, fill=MASK_COL)
        dr.rectangle([x0 * s, y0 * s, (x0 + w) * s, (y0 + h) * s],
                     outline=REGION_COL, width=2)
        dr.text((x0 * s + 2, y0 * s - 14), _label(i, r), fill=REGION_COL,
                font=_font(12), stroke_width=2, stroke_fill=(0, 0, 0))
    if title:
        dr.text((6, 6), title, fill=(255, 255, 255), font=_font(15),
                stroke_width=2, stroke_fill=(0, 0, 0))
    return im


def analyze(image: Path, dpi: float, *, out: Path | None = None,
            target_w: int = 2200):
    src = load_img(image)
    t0 = time.perf_counter()
    survey = platen.detect_payload_regions(np.asarray(src), dpi=dpi)
    dt = time.perf_counter() - t0
    regions = survey.regions
    pitch = (f"{survey.cell_pitch_px:.2f}px"
             if survey.cell_pitch_px is not None else "unknown")
    c_text = f"c{survey.c_dots}" if survey.c_dots is not None else "c?"
    print(f"{image.name}: {tuple(src.shape)} @ {dpi:.0f} dpi -> "
          f"{len(regions)} candidate regions, {c_text}, pitch {pitch} "
          f"in {dt:.1f}s")
    for i, r in enumerate(regions):
        y0, x0, h, w = r.bbox
        angle = (f"{r.angle_hint_deg:+.1f}°"
                 if r.angle_hint_deg is not None else "-")
        print(f"   [{i:2d}] area {r.area_mm2:8.1f} mm²  "
              f"angle hint {angle:>7s}  bbox y{y0} x{x0} h{h} w{w}")
    if out is None:
        out = (ROOT / "experiments/021-payload-regions/build"
               / f"{image.stem}_regions.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    im = annotate(src, regions, target_w=target_w,
                  title=f"e021  {image.name} — {len(regions)} candidates, "
                        f"{c_text}, pitch {pitch}")
    im.save(out)
    print(f"  wrote {out}")
    return survey, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--dpi", type=float, required=True,
                    help="TRUE dpi of the scan — the only required config.")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--target-w", type=int, default=2200)
    args = ap.parse_args()
    analyze(args.image, args.dpi, out=args.out, target_w=args.target_w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

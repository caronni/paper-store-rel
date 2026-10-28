#!/usr/bin/env python
"""exp-019 driver: ingest a platen scan -> acquire candidate payload lattices
-> annotated PNG. The FRONT stage of the fragment receiver, standalone
(angle, pitch, pilots and BCH are all downstream, not done here).

Pipeline: load TIFF/PNG (memmap) -> segment.find_lattice_candidates at the
NATIVE footing (cell-scale MODULATION detection + hysteresis growth, no angle
correction). No decimation by default (--decimate N is an explicit opt-in for
memory); no `backing` anywhere (the detector keys on modulation, not
brightness, so it is backing-independent).

The PNG overlays, per candidate: a labeled bounding box (ORANGE = self-
placeable; GREY = sub-grain, below the ~6 mm correlation floor -> needs
optical jigsaw) plus the per-pixel pale-blue (150,200,235) contour of the
candidate mask (the payload-field boundary; blank white margins are excluded
because they carry no modulation).

  env/bin/python analyze_e019.py build/platen.tiff --dpi 4800
  env/bin/python analyze_e019.py <scan> --dpi 4800 [--decimate N] [--out PNG]
      [--win-cells 2] [--std-lo 8] [--std-hi 22]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/018-confetti-c3-play"))

from paperholo import segment                       # noqa: E402
import decimate_scan                                 # noqa: E402  (box-decimate)

Image.MAX_IMAGE_PIXELS = None

MASK_COL = (150, 200, 235)     # pale blue: payload-field boundary (candidate mask)
FULL_COL = (255, 165, 0)       # orange: self-placeable candidate
SUB_COL = (150, 150, 150)      # grey:   sub-grain (needs jigsaw)


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
        if arr.ndim == 3:                       # RGB(A) scan -> luma (the
            return arr[..., :3].mean(2, dtype=np.float32)   # detector is grey)
        return arr
    return np.asarray(Image.open(path).convert("L"))


def annotate(work: np.ndarray, cands, *, target_w: int = 2200,
             preview_down: int = 4, title: str = "") -> Image.Image:
    """Downsampled grey base + per-candidate bbox and pale-blue mask contour.
    A work-frame pixel X maps to output X * (scale/preview_down)."""
    d = preview_down
    pv = work[::d, ::d].astype(np.float32)
    pv = np.clip((pv - pv.min()) / (np.ptp(pv) + 1e-6) * 255,
                 0, 255).astype(np.uint8)
    im = Image.fromarray(pv).convert("RGB")
    scale = target_w / im.width
    im = im.resize((target_w, max(1, int(im.height * scale))))
    dr = ImageDraw.Draw(im)
    s = scale / d
    for i, c in enumerate(cands):
        y0, x0, h, w = c.bbox
        col = SUB_COL if c.sub_grain else FULL_COL
        mg = c.mask
        if mg is not None and mg.any():          # per-pixel mask contour
            st = max(1, int(round(1.0 / s / 2)))
            ms = mg[::st, ::st]
            edge = (ms ^ np.roll(ms, 1, 0)) | (ms ^ np.roll(ms, 1, 1))
            edge[0, :] = False                   # no np.roll wraparound at
            edge[:, 0] = False                   # the crop borders
            ys2, xs2 = np.nonzero(edge)
            gs = st * s
            pts = [(x0 * s + xx * gs, y0 * s + yy * gs)
                   for yy, xx in zip(ys2, xs2)]
            if pts:
                dr.point(pts, fill=MASK_COL)
        dr.rectangle([x0 * s, y0 * s, (x0 + w) * s, (y0 + h) * s],
                     outline=col, width=2)
        lab = f"{i}  {c.area_mm2:.0f} mm²" + ("  sub-grain" if c.sub_grain
                                              else "")
        dr.text((x0 * s + 2, y0 * s - 14), lab, fill=col, font=_font(12),
                stroke_width=2, stroke_fill=(0, 0, 0))
    if title:
        dr.text((6, 6), title, fill=(255, 255, 255), font=_font(15),
                stroke_width=2, stroke_fill=(0, 0, 0))
    return im


def analyze(image: Path, dpi: float, *, decimate: int = 1,
            dots_per_cell: float = 3.0,
            out: Path | None = None, target_w: int = 2200):
    src = load_img(image)
    f = max(1, decimate)
    # NATIVE by default (f==1): the detector sees the true footing (24 px/cell
    # at 4800, c3). A real A4 4800 grey scan is 2.3 Gpx -> ~9 GB float + the
    # uniform_filter temps peak ~45-55 GB (tight on a 64 GB box; --decimate 3
    # -> 1600 gives headroom).
    work = np.asarray(src) if f == 1 else decimate_scan.decimate(src, f)
    wd = dpi / f
    cell_px = wd / 600.0 * dots_per_cell        # dots_per_cell = 3 (c3) / 2 (c2)
    workf = np.asarray(work, np.float32)
    del work
    diag: dict = {}
    cands = segment.find_lattice_candidates(workf, cell_px=cell_px, dpi=wd,
                                            diagnostics=diag)
    nsub = sum(c.sub_grain for c in cands)
    print(f"{image.name}: {tuple(src.shape)} @ {dpi:.0f} dpi -> "
          f"{'native ' if f == 1 else f'/{f} -> '}{wd:.0f} dpi, "
          f"cell_px={cell_px:.1f} ({dots_per_cell:.0f} dots/cell)")
    dropped = diag.get("dropped_below_med_std", 0)
    print(f"  {len(cands)} lattice candidates ({nsub} sub-grain"
          f"{f'; {dropped} sized blobs below the med_std gate' if dropped else ''}):")
    for i, c in enumerate(cands):
        y0, x0, h, w = c.bbox
        print(f"   [{i:2d}] area {c.area_mm2:8.1f} mm²  mod-std {c.med_std:4.0f}"
              f"{'  SUB-GRAIN' if c.sub_grain else '          '}  bbox y{y0} x{x0}")
    if out is None:
        out = (ROOT / "experiments/019-platen-segment/build"
               / f"{image.stem}_seg.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    im = annotate(workf, cands, target_w=target_w,
                  title=f"exp-019  {image.name}  —  {len(cands)} lattice "
                        f"candidates ({nsub} sub-grain)")
    im.save(out)
    print(f"  wrote {out}")
    return cands, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--dpi", type=float, required=True,
                    help="TRUE dpi of the input scan (authoritative).")
    ap.add_argument("--decimate", type=int, default=1,
                    help="integer decimation factor (default 1 = NATIVE). "
                         "Opt-in only, e.g. 3 (4800->1600) if memory is tight.")
    ap.add_argument("--dots-per-cell", type=float, default=3.0,
                    help="print dots per cell: 3 = c3 (default), 2 = c2. Sets "
                         "the footing; the std thresholds are calibrated for "
                         "the win_cells=2 default and are NOT CLI knobs (change "
                         "them at the segment.find_lattice_candidates API).")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--target-w", type=int, default=2200)
    args = ap.parse_args()
    analyze(args.image, args.dpi, decimate=args.decimate,
            dots_per_cell=args.dots_per_cell, out=args.out,
            target_w=args.target_w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

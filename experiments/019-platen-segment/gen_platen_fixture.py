#!/usr/bin/env python
"""exp-019 synthetic platen fixture: BLACK backing + WHITE-MARGIN c3 confetti.

Nothing on hand produces the scenario exp-019 targets (understand-phase
data probe, 2026-07-13): every real e018 scan is white-lid (margins
invisible white-on-white), and 016/gen_confetti_* carve pieces edge-to-edge
from a full field (no blank-paper margin ring). So this makes it directly.

DETERMINISTIC (seeded np.random.Generator — this is a test FIXTURE, not a
codec path, so it does NOT flow from paperholo.keystream). Real-scan-matched
grey palette (Canon grey, 016/018): backing dark ~40, paper ~225, ink ~70.
Each confetti scrap = a centered c3 printed field (3 dots/cell, ~50% ink)
inside a WHITE paper margin (varied per piece; several full-bleed controls),
randomly rotated so its corners fall to backing, then a light print/scan PSF
(gaussian blur + noise). Grey uint8 TIFF.

  env/bin/python gen_platen_fixture.py --out build/platen.tiff [--dpi 4800]
  env/bin/python gen_platen_fixture.py --small --out build/platen_small.tiff
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

BACKING_DARK = 40.0        # realistic black backing (016 'dark'); 0 = stress
PAPER = 225.0
INK = 70.0

# (scrap_mm, margin_mm) — margin 0 == full-bleed control (edge-to-edge field)
DEFAULT_SCHEDULE = [
    (20, 3), (16, 0), (12, 2), (8, 4),
    (18, 1), (14, 0), (20, 2), (10, 3),
    (16, 0), (12, 4), (8, 2),
]
SMALL_SCHEDULE = [(18, 3), (12, 0), (8, 2)]


def _render_field(rng: np.random.Generator, fcy: int, fcx: int,
                  dot_px: int) -> np.ndarray:
    """c3 printed field, SOLID cells: 1 bit/cell = the whole 3x3-dot block one
    colour, matching the real kcell codec (modulation.cells_to_dots = kron of
    per-cell bits). NOT per-dot random — the modulation lives BETWEEN cells,
    so a cell-sized texture window reads it via boundary straddle + PSF
    (verified: real e018 field std median 30 at native 24 px/cell)."""
    cell_bits = rng.random((fcy, fcx)) < 0.5
    cell_px = 3 * dot_px
    return np.where(np.kron(cell_bits, np.ones((cell_px, cell_px), bool)),
                    INK, PAPER).astype(np.float32)


def _make_piece(rng: np.random.Generator, size_mm: float, margin_mm: float,
                dpi: float, backing: float):
    """(rotated float img, bool piece mask, angle_deg, true scrap side mm)."""
    px_per_mm = dpi / 25.4
    dot_px = max(1, int(round(dpi / 600)))     # 8 at 4800 dpi
    cell_px = 3 * dot_px
    field_mm = max(size_mm - 2 * margin_mm, size_mm * 0.4)
    fc = max(2, int(round(field_mm * px_per_mm / cell_px)))
    field = _render_field(rng, fc, fc, dot_px)
    margin_px = int(round(margin_mm * px_per_mm))
    side = field.shape[0] + 2 * margin_px
    scrap = np.full((side, side), PAPER, np.float32)
    scrap[margin_px:margin_px + field.shape[0],
          margin_px:margin_px + field.shape[1]] = field
    ang = float(rng.uniform(0.0, 360.0))
    rot = ndimage.rotate(scrap, ang, reshape=True, order=1,
                         cval=backing, mode="constant").astype(np.float32)
    msk = ndimage.rotate(np.ones_like(scrap), ang, reshape=True,
                         order=0, cval=0.0, mode="constant") > 0.5
    return rot, msk, ang, side / px_per_mm


def build(*, dpi: float, width_mm: float, backing: float, seed: int,
          blur: float, noise: float, schedule, gap_mm: float,
          border_mm: float):
    rng = np.random.default_rng(seed)
    px_per_mm = dpi / 25.4
    gap = int(round(gap_mm * px_per_mm))
    border = int(round(border_mm * px_per_mm))
    W = int(round(width_mm * px_per_mm))
    rendered = [(*_make_piece(rng, s, m, dpi, backing), s, m)
                for (s, m) in schedule]
    # a rotated piece's bbox can exceed the requested width; grow the canvas
    # so the widest piece + borders always fits (else the fixed-W row slice
    # would clip a piece and the boolean-mask assignment mismatches — review).
    W = max(W, max(r[0].shape[1] for r in rendered) + 2 * border)
    # shelf-pack left-to-right, wrap by width, rows grow downward
    placements, gt = [], []
    x = y = border
    row_h = 0
    for (img, msk, ang, scrap_mm, size_mm, margin_mm) in rendered:
        h, w = img.shape
        if x + w + border > W and x > border:
            y += row_h + gap
            x = border
            row_h = 0
        placements.append((y, x, img, msk))
        gt.append({"y": y, "x": x, "h": int(h), "w": int(w),
                   "size_mm": size_mm, "margin_mm": margin_mm,
                   "angle_deg": round(ang, 2),
                   "scrap_mm": round(scrap_mm, 2)})
        x += w + gap
        row_h = max(row_h, h)
    H = y + row_h + border
    canvas = np.full((H, W), backing, np.float32)
    for (py, px, img, msk) in placements:
        h, w = img.shape
        region = canvas[py:py + h, px:px + w]
        region[msk] = img[msk]                 # backing shows through corners
    if blur > 0:
        canvas = ndimage.gaussian_filter(canvas, blur)
    if noise > 0:
        canvas = canvas + rng.normal(0.0, noise, canvas.shape)
    canvas = np.clip(canvas, 0, 255).astype(np.uint8)
    return canvas, gt


def _backing_value(s: str) -> float:
    named = {"black": 0.0, "dark": BACKING_DARK, "white": 250.0}
    return named[s.lower()] if s.lower() in named else float(s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=float, default=4800.0)
    ap.add_argument("--width-mm", type=float, default=110.0)
    ap.add_argument("--backing", default="dark",
                    help="dark(=40, default) / black(=0) / white(=250) / int")
    ap.add_argument("--seed", type=int, default=19)
    ap.add_argument("--blur", type=float, default=-1.0,
                    help="PSF gaussian sigma px (default auto = dpi/800)")
    ap.add_argument("--noise", type=float, default=7.0)
    ap.add_argument("--gap-mm", type=float, default=5.0)
    ap.add_argument("--border-mm", type=float, default=4.0)
    ap.add_argument("--small", action="store_true",
                    help="fast test preset (1600 dpi, 45 mm, 3 pieces)")
    args = ap.parse_args()

    dpi = 1600.0 if args.small else args.dpi
    width_mm = 45.0 if args.small else args.width_mm
    schedule = SMALL_SCHEDULE if args.small else DEFAULT_SCHEDULE
    backing = _backing_value(args.backing)
    blur = args.blur if args.blur >= 0 else dpi / 800.0

    canvas, gt = build(dpi=dpi, width_mm=width_mm, backing=backing,
                       seed=args.seed, blur=blur, noise=args.noise,
                       schedule=schedule, gap_mm=args.gap_mm,
                       border_mm=args.border_mm)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(args.out), canvas,
                     resolution=(dpi, dpi), resolutionunit=2)
    meta = {"dpi": dpi, "shape": list(canvas.shape), "backing": backing,
            "seed": args.seed, "blur": blur, "noise": args.noise,
            "n_pieces": len(gt), "pieces": gt}
    args.out.with_suffix(".gt.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {args.out} {canvas.shape} @ {dpi:.0f} dpi, "
          f"backing={backing:.0f}, {len(gt)} pieces "
          f"({sum(1 for g in gt if g['margin_mm'] == 0)} full-bleed) "
          f"+ {args.out.with_suffix('.gt.json').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

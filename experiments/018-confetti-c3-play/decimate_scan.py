#!/usr/bin/env python
"""Integer box-average decimation for confetti scans.

Canon 4800 dpi grey -> 3x -> 1600 dpi = 8 px/cell at c3 = the measured-best
footing (012.3/acquire-v2: 4800-sourced 8 px/cell 0.57% BER beat native
1200 6 px/cell 0.85%; the win is 4800-SOURCED, so scan high and decimate).
Also sidesteps the whole-canvas float materialization a raw-4800 decode
would pay in the segmenter.

  env/bin/python decimate_scan.py in.tiff out.tiff [--factor 3]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
import tifffile

Image.MAX_IMAGE_PIXELS = None


def load(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        return tifffile.TiffFile(str(path)).pages[0].asarray()
    return np.asarray(Image.open(path).convert("L"))


def decimate(img: np.ndarray, f: int) -> np.ndarray:
    if img.ndim == 3:                       # reduce RGB to luma first
        img = img[..., :3].mean(2)
    H, W = img.shape[:2]
    Hc, Wc = H - H % f, W - W % f
    return (img[:Hc, :Wc].astype(np.float32)
            .reshape(Hc // f, f, Wc // f, f).mean((1, 3))
            .round().clip(0, 255).astype(np.uint8))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inp", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--factor", type=int, default=3,
                    help="4800->1600 = 3 (default). 2400->1600 is not "
                         "integer; the record says do NOT route c3 through "
                         "2400 (worst of the three footings measured).")
    args = ap.parse_args()
    src = load(args.inp)
    out = decimate(src, args.factor)
    if args.out.suffix.lower() in (".tif", ".tiff"):
        tifffile.imwrite(str(args.out), out)
    else:
        Image.fromarray(out).save(args.out)
    print(f"{args.inp.name} {src.shape} -> {args.out.name} {out.shape} "
          f"(/{args.factor}); feed with --dpi "
          f"{4800 // args.factor if args.factor in (2, 3, 4) else '<orig/factor>'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

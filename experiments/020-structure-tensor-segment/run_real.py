#!/usr/bin/env python
"""Compare e019 and e020 on one real platen scan at the same footing."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import tifffile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import segment  # noqa: E402
import detector as tensor_detector  # noqa: E402


def _overlap(a, b):
    ay, ax, ah, aw = a
    by, bx, bh, bw = b
    return not (ay + ah <= by or by + bh <= ay or
                ax + aw <= bx or bx + bw <= ax)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", type=Path,
                        default=ROOT / "scratch/e018/decimated-1_1600.tiff")
    parser.add_argument("--dpi", type=float, default=1600.0)
    parser.add_argument("--work-cell-px", type=float, default=2.0)
    parser.add_argument("--out", type=Path,
                        default=HERE / "build/real_decimated-1.png")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    source = tifffile.memmap(args.image)
    cell_px = args.dpi / 600.0 * 3.0
    t0 = time.perf_counter()
    e020 = tensor_detector.detect(source, cell_px=cell_px, dpi=args.dpi,
                                  work_cell_px=args.work_cell_px)
    t020 = time.perf_counter() - t0

    factor = e020.work_decimation
    work = tensor_detector._block_mean(source, factor)
    work_dpi = args.dpi / factor
    work_cell = cell_px / factor
    t0 = time.perf_counter()
    e019 = segment.find_lattice_candidates(work, cell_px=work_cell,
                                            dpi=work_dpi)
    t019 = time.perf_counter() - t0

    boxes020 = [c.bbox for c in e020.candidates]
    boxes019 = [(y * factor, x * factor, h * factor, w * factor)
                for c in e019 for y, x, h, w in [c.bbox]]
    only020 = [b for b in boxes020 if not any(_overlap(b, a)
                                               for a in boxes019)]
    only019 = [b for b in boxes019 if not any(_overlap(b, a)
                                               for a in boxes020)]
    print(f"{args.image.name}: {source.shape}, input {args.dpi:.0f} dpi, "
          f"comparison {work_dpi:.0f} dpi ({work_cell:.1f} px/cell)")
    print(f"e019: {len(e019)} candidates in {t019:.2f}s")
    print(f"e020: {len(e020.candidates)} candidates in {t020:.2f}s, "
          f"adaptive threshold={e020.threshold:.3f}")
    print(f"bbox unmatched: e019-only={len(only019)}, e020-only={len(only020)}")

    stride = max(1, int(round(work.shape[1] / 2200)))
    preview = work[::stride, ::stride]
    lo, hi = np.percentile(preview, [0.2, 99.8])
    preview = np.clip((preview - lo) / max(hi - lo, 1e-6) * 255,
                      0, 255).astype(np.uint8)
    image = Image.fromarray(preview).convert("RGB")
    draw = ImageDraw.Draw(image)
    scale = 1.0 / (factor * stride)
    for y, x, h, w in boxes019:
        draw.rectangle((x * scale, y * scale, (x + w) * scale,
                        (y + h) * scale), outline=(50, 130, 255), width=2)
    for y, x, h, w in boxes020:
        draw.rectangle((x * scale, y * scale, (x + w) * scale,
                        (y + h) * scale), outline=(245, 90, 45), width=2)
    draw.text((6, 6), f"BLUE=e019 {len(e019)}  ORANGE=e020 "
             f"{len(e020.candidates)}", fill=(255, 255, 255),
             stroke_width=2, stroke_fill=(0, 0, 0))
    image.save(args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

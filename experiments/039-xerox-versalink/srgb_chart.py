#!/usr/bin/env python3
"""e039 — the sRGB FIXED-POINT CHART: an Apple raster SRGB24 page (the one
colour type this printer advertises) of labelled patches — the six saturated
sRGB primaries, black, and a neighbourhood around cyan, magenta and yellow —
each patch a solid block, a random 2x2-cell field of that colour on white,
and isolated single dots.  The W8 raster printed bit-faithfully because 0 and
255 are fixed points of every tone curve; this chart asks whether ANY sRGB
triple is mapped to a single toner (and pure two-toner overprints), which
would give the CMY8 alphabet a URF route.  Undocumented; measured by loupe.

    env/bin/python experiments/039-xerox-versalink/srgb_chart.py out.urf [--quality 4|5]

The file is decoded back and compared before being kept.  Nothing prints.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from urf_raster import HW_DPI, urf_decode_pixels, urf_encode_pixels  # noqa: E402

PAGE_W, PAGE_H = 5100, 8400
PATCH = 560                      # dots (~24 mm) per patch cell incl. its label band
BLOCK = 240

PATCHES: list[tuple[str, tuple[int, int, int]]] = [
    ("C", (0, 255, 255)), ("M", (255, 0, 255)), ("Y", (255, 255, 0)),
    ("R=M+Y", (255, 0, 0)), ("G=C+Y", (0, 255, 0)), ("B=C+M", (0, 0, 255)), ("K", (0, 0, 0)),
]
for base, name in (((0, 255, 255), "C"), ((255, 0, 255), "M"), ((255, 255, 0), "Y")):
    for k, (dr, dg, db) in enumerate(((0, -15, 0), (0, 0, -15), (-15, 0, 0), (0, -30, 0), (0, 0, -30), (-30, 0, 0))):
        r, g, b = base
        # push the ZERO channel(s) up and the 255 channels down by the offsets that apply
        rgb = tuple(int(min(255, max(0, v + d if v == 255 else v - d))) for v, d in zip((r, g, b), (dr, dg, db)))
        PATCHES.append((f"{name}~{k + 1}", rgb))


def chart(seed: int = 39) -> tuple[np.ndarray, list[tuple[str, tuple[int, int, int], int, int]]]:
    rng = np.random.default_rng(seed)
    img = np.full((PAGE_H, PAGE_W, 3), 255, np.uint8)
    placed = []
    cols = 8
    x0, y0 = 300, 900
    for n, (name, rgb) in enumerate(PATCHES):
        x = x0 + (n % cols) * PATCH
        y = y0 + (n // cols) * PATCH
        img[y:y + BLOCK, x:x + BLOCK] = rgb                                           # solid
        cells = rng.integers(0, 2, (BLOCK // 4, BLOCK // 2)).astype(bool)
        field = np.kron(cells, np.ones((2, 2), bool))
        sub = img[y:y + BLOCK // 2, x + BLOCK + 16:x + BLOCK + 16 + BLOCK]
        sub[field] = rgb                                                               # random 2x2 cells
        d = np.zeros((BLOCK // 2, BLOCK), bool); d[4::8, 4::8] = True
        sub2 = img[y + BLOCK // 2 + 8:y + BLOCK + 8, x + BLOCK + 16:x + BLOCK + 16 + BLOCK]
        sub2[d] = rgb                                                                  # single dots
        placed.append((name, rgb, x, y))
    return img, placed


def label(img: np.ndarray, placed, variant: str) -> None:
    from PIL import Image, ImageDraw, ImageFont
    lab = Image.fromarray(img)
    d = ImageDraw.Draw(lab)
    try:
        big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 150)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except Exception:
        big = small = ImageFont.load_default()
    d.text((300, 150), "e039 sRGB FIXED-POINT CHART  -  Apple raster SRGB24", fill=(0, 0, 0), font=big)
    d.text((300, 330), "sent with: " + variant + "   Loupe: which patch is ONE toner, solid, unscreened?", fill=(0, 0, 0), font=small)
    for name, rgb, x, y in placed:
        d.text((x, y + BLOCK + 20), f"{name} {rgb}", fill=(0, 0, 0), font=small)
    img[:] = np.asarray(lab)


def urf_srgb(img: np.ndarray, quality: int) -> bytes:
    h, w = img.shape[:2]
    return (b"UNIRAST\x00" + struct.pack(">I", 1)
            + struct.pack(">BBBBIIIIIII", 24, 1, 1, quality, 0, 0, w, h, HW_DPI, 0, 0)
            + urf_encode_pixels(img, 3))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--quality", type=int, choices=(4, 5), default=4)
    ap.add_argument("--variant", default="quality NORMAL")
    ap.add_argument("--preview", type=Path, default=None)
    args = ap.parse_args()
    img, placed = chart()
    label(img, placed, args.variant)
    data = urf_srgb(img, args.quality)
    dec, used = urf_decode_pixels(data[44:], PAGE_W, PAGE_H, 3)
    if used != len(data) - 44 or not np.array_equal(dec, img):
        raise SystemExit("round-trip FAILED")
    args.out.write_bytes(data)
    if args.preview:
        from PIL import Image
        Image.fromarray(img[::4, ::4]).save(args.preview, optimize=True)
    print(f"{args.out}: SRGB24 {PAGE_W}x{PAGE_H} @600, {len(PATCHES)} patches, {len(data):,} B, "
          f"sha256 {hashlib.sha256(data).hexdigest()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

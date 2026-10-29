#!/usr/bin/env python3
"""bullseye_profiles.py -- what the comb will face: the centre-row and
centre-column run-length profiles of a bullseye block, per bullseye kind
(record, v1, v2, v3) and ring rendering (coarse, dot), from the page sets
gen_variant.py wrote (build/format-round/pages/<kind>-<rings>/page_p0.pbm).

Per block (default the page's bullseyes (2, 2), bi + bj even, and (8, 5),
odd: the timing line at dx = +8 is white / ink) and axis (row = along x
through the centre, col = along y):
  600dpi   the page raster itself: the dot row (column) just below (right
           of) the centre point (the centre of module (0,0) falls on a dot
           boundary at 12 dots per module, so this line is 1/24 module off
           it), runs in modules (dots / 12);
  sS bB pP camera.py UNCHANGED (simulate_frame on a one-block crop, the
           nominal preset with --spm S --blur B and persp 0, rotate 0,
           illum 0, noise 0: optics and sampling only), the frame cut so
           that the centre point sits at phase P of a pixel (0 = on a pixel
           centre, 0.5 = on a pixel edge); the pixel row (column) through
           (P 0) or just below (P 0.5) the centre point, thresholded at the
           mid reflectance (paper 0.80 + ink 0.10) / 2 x 255 = 114.75 (the
           reader's (min + max) // 2 on an evenly lit page), runs in
           modules (pixels / S).
A run is printed K (ink) or W (white), its length in modules, and in [] its
extreme grey value (the darkest pixel of a K run, the brightest of a W run:
the margin to the threshold); '*' marks the run holding the centre point,
'<' '>' runs cut by the window edge (+-12.5 modules).

Usage: bullseye_profiles.py [--pages DIR] [--kinds record v1 v2 v3]
                            [--rings coarse dot] [--blocks 2,2 8,5]
                            [--out FILE]   (default build/format-round/profiles.txt)
                            [--threshold G] (default 114.75)
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(BOOT, "r2"))
import camera  # noqa: E402  (bootstrap/r2, unchanged)

PAGES = os.path.join(BOOT, "build", "format-round", "pages")
OUT = os.path.join(BOOT, "build", "format-round", "profiles.txt")
HALF_SPAN_MODULES = 12.5
THRESHOLD = (0.80 + 0.10) / 2 * 255
THR = [THRESHOLD]
CAMERAS = [(2.0, 0.30, 0.0), (2.0, 0.30, 0.5), (2.0, 0.45, 0.0),
           (2.0, 0.45, 0.5), (7.0, 0.30, 0.0), (7.0, 0.45, 0.0)]


def runs(ink, grey, centre_idx, unit):
    """ink: bool array along the line; grey: values (or None); centre_idx:
    the index holding the centre point; unit: samples per module."""
    out = []
    i, n = 0, len(ink)
    while i < n:
        j = i
        while j < n and ink[j] == ink[i]:
            j += 1
        k = "K" if ink[i] else "W"
        s = f"{k}{(j - i) / unit:.2f}".rstrip("0").rstrip(".")
        if grey is not None:
            seg = grey[i:j]
            s += f"[{int(seg.min() if ink[i] else seg.max())}]"
        if i <= centre_idx < j:
            s += "*"
        if i == 0:
            s = "<" + s
        if j == n:
            s += ">"
        out.append(s)
        i = j
    return " ".join(out)


def raster_lines(page, cx, cy, md):
    """600-dpi runs along the dot row / column next to the centre point
    (cx, cy integers: the centre lies on a dot corner)."""
    h = int(round(HALF_SPAN_MODULES * md))
    row = page[cy, cx - h:cx + h].astype(bool)
    col = page[cy - h:cy + h, cx].astype(bool)
    return (runs(row, None, h, md), runs(col, None, h, md))


def camera_lines(page, cx, cy, md, spm, blur, phase):
    p = dict(camera.PRESETS["nominal"])
    p.update(spm=spm, blur=blur, persp=0.0, rotate=0.0, illum=0.0,
             noise=0.0)
    pix = md / spm                                  # dots per pixel
    N = int(math.ceil(HALF_SPAN_MODULES * spm))
    off = (N + 0.5 - phase) * pix                   # centre at pixel N + .5 - phase
    side = (2 * N + 1) * pix
    img, _ = camera.simulate_frame(page, md, p, 1,
                                   (cx - off, cy - off, side, side))
    g = img.astype(np.int32)
    row, col = g[N, :], g[:, N]
    return (runs(row < THR[0], row, N, spm),
            runs(col < THR[0], col, N, spm))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pages", default=PAGES)
    ap.add_argument("--kinds", nargs="+", default=["record", "v1", "v2", "v3"])
    ap.add_argument("--rings", nargs="+", default=["coarse", "dot"])
    ap.add_argument("--blocks", nargs="+", default=["2,2", "8,5"])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--threshold", type=float, default=THRESHOLD,
                    help="grey level below which a pixel is ink "
                         "(default the mid reflectance, 114.75)")
    a = ap.parse_args(argv)
    THR[0] = a.threshold
    lines = []
    for kind in a.kinds:
        for rings in a.rings:
            d = os.path.join(a.pages, f"{kind}-{rings}")
            side = json.load(open(os.path.join(d, "page_p0.json")))
            page = camera.load_page(os.path.join(d, "page_p0.pbm"))
            md, x0, y0 = side["module_dots"], side["x0_dots"], side["y0_dots"]
            for b in a.blocks:
                bi, bj = map(int, b.split(","))
                cx = x0 + md * (17 * bj + 9) + md // 2
                cy = y0 + md * (17 * bi + 9) + md // 2
                lines.append(f"== {kind}-{rings} bullseye ({bi},{bj}) "
                             f"(bi+bj {'even' if (bi + bj) % 2 == 0 else 'odd'}),"
                             f" centre dots ({cx}, {cy})")
                r, c = raster_lines(page, cx, cy, md)
                lines.append(f"  600dpi       row: {r}")
                lines.append(f"  600dpi       col: {c}")
                for spm, blur, ph in CAMERAS:
                    r, c = camera_lines(page, cx, cy, md, spm, blur, ph)
                    tag = f"s{spm:g} b{blur:.2f} p{ph:g}"
                    lines.append(f"  {tag:12s} row: {r}")
                    lines.append(f"  {tag:12s} col: {c}")
            print("\n".join(lines[-(len(a.blocks) * (3 + 2 * len(CAMERAS))):]),
                  flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(f"# bullseye_profiles.py, pages {a.pages}, threshold "
                f"{THR[0]:.2f}\n" + "\n".join(lines) + "\n")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())

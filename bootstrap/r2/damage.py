#!/usr/bin/env python3
"""R2 damage operations for the camera simulator (R2-FORMAT.md v1, "What the
camera simulator must reproduce": blacked or torn bullseyes, blots,
scratches, a missing corner; plus the 10-19 build's coffee rings and 10 %
crops).  Ported from bootstrap/build.py (damage_page, crop; 2026-10-19) and
record-2026-10-18/refute-r2/damage.py, with the corner bullseyes of v0
replaced by the 15 bullseye blocks of v1.

Page-space damage works on the page as float32 "ink fraction" (1 = ink,
0 = paper; the camera maps it to reflectance paper - (paper - ink) * v, so a
stain multiplying reflectance by m is v' = (paper - m (paper - (paper - ink)
v)) / (paper - ink), and "no paper here" is v = (paper - background) /
(paper - ink)).  paper/ink/background are the capture's own (v0's build
used the nominal preset's for every capture).  Image-space damage (crop-*)
cuts the rendered capture and moves the homography with it.

KINDS (camera.py --damage KIND, repeatable; bullseye K = index 0..14 into the
sidecar's bullseye list = block raster order (2,2) (2,8) (2,14) (8,5) (8,11)
(8,17) (14,2) (14,8) (14,14) (20,5) (20,11) (20,17) (26,2) (26,8) (26,14);
LIST = K, K+K+..., or 'all'):
  be:LIST            bullseye blocks blacked out (16 x 16 interior inked)
  bt:LIST            bullseye blocks torn out (16 x 16 interior shows the
                     background: a hole in the page)
  blot:C[:R_MM]      ink disc, radius R_MM (default 4 mm), centred on the
                     grid's outer corner C (0 TL, 1 TR, 2 BL, 3 BR) [v0]
  blot-at:X:Y[:R_MM] ink disc centred at grid module (X, Y) (column, row)
  ring-centre        20 mm coffee ring at grid (W/2, 0.15 H) [v0]
  ring-bullseye[:K]  20 mm coffee ring centred on bullseye K (default 0)
  scratch-O-T[:W_MM] a W_MM wide (default 5 mm) scratch, O = h (at grid
                     row 0.25 H), v (at grid column W/2), d (the page
                     diagonal TL -> BR) or e (the anti-diagonal TR -> BL),
                     T = white (paper) or dark (ink) [v0: h-white, d-dark,
                     d-white, v-*]
  torn:C[:L_MM]      page corner C (0 TL, 1 TR, 2 BL, 3 BR) missing: the
                     triangle with legs L_MM (default 60 mm) along the two
                     page edges shows the background
  crop-E[:FRAC]      the rendered capture cut at the page's FRAC (default
                     0.10) line from edge E in T, B, L, R (v0's crop: the cut
                     lies wholly inside the page, so slightly more than FRAC
                     goes); whole-page captures only

Each page-space kind reports the grid blocks (bi, bj) whose 16 x 16 interior
it touches (any dot), so a truth evaluation can tell damaged blocks apart.
"""
import math

import numpy as np

DPM = 600 / 25.4                    # dots per mm
EDGES = ("T", "B", "L", "R")


def _bullseyes(side):
    return [tuple(b["block"]) for b in side["bullseyes"]]


def _list(spec, n):
    if spec == "all":
        return list(range(n))
    out = [int(x) for x in spec.split("+")]
    for k in out:
        if not 0 <= k < n:
            raise SystemExit(f"bullseye index {k} not in 0..{n - 1}")
    return out


def _grid(side):
    return (side["module_dots"], side["x0_dots"], side["y0_dots"],
            side["W"], side["H"])


def blocks_touched(mask, side):
    """Grid blocks whose 16 x 16 interior intersects the dot mask."""
    md, x0, y0, W, H = _grid(side)
    m = mask[y0:y0 + H * md, x0:x0 + W * md]
    mod = m.reshape(H, md, W, md).any(axis=(1, 3))
    out = []
    for bi in range((H - 1) // 17):
        for bj in range((W - 1) // 17):
            if mod[17 * bi + 1:17 * bi + 17, 17 * bj + 1:17 * bj + 17].any():
                out.append([bi, bj])
    return out


def is_cut(kind):
    return kind.startswith("crop-")


def apply(pg, side, kind, paper, ink, background):
    """Page-space damage.  pg: float32 ink fraction (modified and returned).
    -> (pg, record)."""
    hd, wd = pg.shape
    md, x0, y0, W, H = _grid(side)
    no_paper = np.float32((paper - background) / (paper - ink))
    rec = dict(kind=kind)
    if kind.startswith(("be:", "bt:")):
        be = _bullseyes(side)
        ks = _list(kind[3:], len(be))
        mask = np.zeros((hd, wd), dtype=bool)
        for k in ks:
            bi, bj = be[k]
            c0, r0 = 17 * bj + 1, 17 * bi + 1
            mask[y0 + md * r0:y0 + md * (r0 + 16),
                 x0 + md * c0:x0 + md * (c0 + 16)] = True
        pg[mask] = 1.0 if kind.startswith("be:") else no_paper
        rec.update(bullseyes=[list(be[k]) for k in ks],
                   what="blacked out" if kind.startswith("be:")
                   else "torn out (background)")
    elif kind.startswith(("blot:", "blot-at:")):
        parts = kind.split(":")
        if parts[0] == "blot":
            c = int(parts[1])
            cx, cy = x0 + md * W * (c & 1), y0 + md * H * (c >> 1)
            rmm = float(parts[2]) if len(parts) > 2 else 4.0
        else:
            cx = x0 + md * (float(parts[1]) + 0.5)
            cy = y0 + md * (float(parts[2]) + 0.5)
            rmm = float(parts[3]) if len(parts) > 3 else 4.0
        yy, xx = np.ogrid[0:hd, 0:wd]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 < (rmm * DPM) ** 2
        pg[mask] = 1.0
        rec.update(centre_dots_xy=[cx, cy], radius_mm=rmm)
    elif kind.startswith("ring"):
        if kind == "ring-centre":
            cx, cy = x0 + md * W / 2, y0 + md * H * 0.15
        elif kind.startswith("ring-bullseye"):
            k = int(kind.split(":")[1]) if ":" in kind else 0
            cx, cy = side["bullseyes"][k]["centre_dots_xy"]
            rec.update(bullseye=side["bullseyes"][k]["block"])
        else:
            raise SystemExit(f"unknown damage {kind}")
        R, w = 10 * DPM, 1.2 * DPM
        yy, xx = np.ogrid[0:hd, 0:wd]
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        m = np.ones_like(r, dtype=np.float32)
        m[r < R] = 0.90
        rim = np.exp(-0.5 * ((r - (R - w / 2)) / (w / 2.5)) ** 2)
        m = m * (1 - 0.45 * rim).astype(np.float32)
        m[r > R + w] = 1.0
        mask = r <= R + w
        pg = ((paper - m * (paper - (paper - ink) * pg))
              / (paper - ink)).astype(np.float32)
        rec.update(centre_dots_xy=[float(cx), float(cy)], radius_mm=10.0,
                   rim_mm=1.2, inside_gain=0.90, rim_depth=0.45)
    elif kind.startswith("scratch-"):
        try:
            name, _, wmm = kind.partition(":")
            _, o, t = name.split("-")
            assert o in "hvde" and len(o) == 1 and t in ("white", "dark")
            wmm = float(wmm) if wmm else 5.0
        except (ValueError, AssertionError):
            raise SystemExit(f"unknown damage {kind}")
        yy, xx = np.ogrid[0:hd, 0:wd]
        half = wmm / 2 * DPM
        if o == "h":
            ly = y0 + md * H * 0.25
            mask = np.broadcast_to(np.abs(yy - ly) < half, (hd, wd))
            rec.update(line="y = %.1f dots" % ly)
        elif o == "v":
            lx = x0 + md * W / 2
            mask = np.broadcast_to(np.abs(xx - lx) < half, (hd, wd))
            rec.update(line="x = %.1f dots" % lx)
        elif o == "d":
            nx, ny = hd, -wd
            mask = np.abs(xx * nx + yy * ny) / math.hypot(nx, ny) < half
            rec.update(line="page diagonal (0, 0) -> (%d, %d)" % (wd, hd))
        else:
            nx, ny = hd, wd
            mask = np.abs(xx * nx + yy * ny - wd * hd) / math.hypot(nx, ny) \
                < half
            rec.update(line="page anti-diagonal (%d, 0) -> (0, %d)"
                       % (wd, hd))
        pg[mask] = 0.0 if t == "white" else 1.0
        rec.update(width_mm=wmm)
    elif kind.startswith("torn:"):
        parts = kind.split(":")
        c = int(parts[1])
        lmm = float(parts[2]) if len(parts) > 2 else 60.0
        ld = lmm * DPM
        yy, xx = np.ogrid[0:hd, 0:wd]
        dx = xx if c in (0, 2) else (wd - xx)
        dy = yy if c in (0, 1) else (hd - yy)
        mask = (dx / ld + dy / ld) < 1.0
        pg[mask] = no_paper
        rec.update(corner=["TL", "TR", "BL", "BR"][c], legs_mm=lmm)
    else:
        raise SystemExit(f"unknown damage {kind}")
    rec["blocks_touched"] = blocks_touched(np.broadcast_to(mask, (hd, wd)),
                                           side)
    return pg, rec


def cut(img, hm, kind, wd, hd):
    """crop-E[:FRAC]: cut the rendered capture at the page's FRAC line from
    edge E (v0's build.py crop).  -> (img, homography, record)."""
    parts = kind.split(":")
    edge = parts[0][len("crop-"):]
    frac = float(parts[1]) if len(parts) > 1 else 0.10
    if edge not in EDGES:
        raise SystemExit(f"unknown crop edge {edge}")
    hm = np.asarray(hm, dtype=np.float64)

    def m(x, y):
        v = hm @ [x, y, 1]
        return v[0] / v[2], v[1] / v[2]
    c0 = r0 = 0
    if edge == "T":
        a, b = m(0, frac * hd), m(wd, frac * hd)
        r0 = int(math.ceil(max(a[1], b[1])))
        img = img[r0:, :]
    elif edge == "B":
        a, b = m(0, (1 - frac) * hd), m(wd, (1 - frac) * hd)
        img = img[:int(min(a[1], b[1])), :]
    elif edge == "L":
        a, b = m(frac * wd, 0), m(frac * wd, hd)
        c0 = int(math.ceil(max(a[0], b[0])))
        img = img[:, c0:]
    else:
        a, b = m((1 - frac) * wd, 0), m((1 - frac) * wd, hd)
        img = img[:, :int(min(a[0], b[0]))]
    t = np.array([[1, 0, -c0], [0, 1, -r0], [0, 0, 1]], dtype=np.float64)
    rec = dict(kind=kind, edge=edge, frac=frac, offset_px=[c0, r0],
               size_px=[img.shape[1], img.shape[0]])
    return np.ascontiguousarray(img), t @ hm, rec

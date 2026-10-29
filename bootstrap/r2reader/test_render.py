"""test_render.py v1 -- an independent R2-FORMAT v1 renderer and camera
simulator (2026-10-20; never typed; numpy).

Written from bootstrap/R2-FORMAT.md v1 alone, without bootstrap/r2/gen.py or
bootstrap/r2/camera.py: it is the cross-check of those (a second builder
upgrades them from the same spec).  v0 of this file is in git history.

What it makes
  pages(data, ring, seed)   the printed pages of one payload: module grid
                            (H x W, ink = 1) + sidecar (header, slot -> chunk)
  frame(page, ...)          one camera frame of a page: whole page or a
                            partial view (any module rectangle), at a given
                            samples-per-module, perspective relative to the
                            frame, small rotation, quarter turns, Gaussian
                            blur (sigma in modules), illumination gradient,
                            additive noise, damage stamps; returns the 8-bit
                            image and a truth dict (module -> pixel
                            homography, bullseye centres in the reader's
                            pixel convention, local pitch, orientation)
  loupe_grid(page, flips)   the 0/1 module grid as text, with seeded flips
  ring='square'             the v0 13 x 13 square rings in the v1 layout
                            (header modules white): for the detector A/B only

Pixel convention of the truth: pixel (i, j) covers [j, j+1) x [i, i+1) of
the continuous image plane; the reader puts pixel j's value AT coordinate j,
so truth points are reported as (continuous - 0.5).

CLI
  python test_render.py page DATA OUTDIR [--ring square] [--seed S]
      writes page<p>.grid.txt + page<p>.json per page
  python test_render.py frame DATA OUT.pgm [key=value ...]
      e.g. spm=2 sigma=0.3 persp=0.02 view=whole|tl|tr|bl|br turns=1
      rot=4 seed=3 page=0; writes OUT.pgm and OUT.json
"""
import json
import math
import os
import sys
import zlib

import numpy as np

# ---- the format (R2-FORMAT v1) ---------------------------------------------
W, H = 358, 511                  # modules; W = 17*BW + 1, H = 17*BH + 1
BW, BH = 21, 30
CHUNK = 26                       # data bytes per block
PER_PAGE = 204                   # chunks per page
BULLS = ([(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)]
         + [(bi, bj) for bi in (8, 20) for bj in (5, 11, 17)])
MODULE_MM = 12 * 25.4 / 600      # 0.508 mm
INK_Q = (0, 4, 5, 13, 16, 17, 18, 20, 32, 34, 36, 37, 40, 41)   # spec's list


def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def ring_value(dx, dy):
    """Bullseye block module at (dx, dy) from the centre: 1 ink, 0 white,
    None = header module (q >= 57)."""
    q = dx * dx + dy * dy
    if q <= 42:
        return int(math.floor(math.sqrt(q) + 0.5) % 2 == 0)
    if q <= 56:
        return 0
    return None


def square_value(dx, dy):
    """The v0 square rings (13 x 13, ink iff Chebyshev ring even), quiet
    ring 7, everything else white (no header in the square variant)."""
    m = max(abs(dx), abs(dy))
    return int(m % 2 == 0) if m <= 6 else 0


# self-check: the ring formula reproduces the spec's list of ink q
_QS = sorted({dx * dx + dy * dy for dx in range(-8, 8) for dy in range(-8, 8)})
assert tuple(q for q in _QS if q <= 42
             and math.floor(math.sqrt(q) + 0.5) % 2 == 0) == INK_Q

# header modules: block-local raster order, q >= 57
HEAD_RC = [(r, c) for r in range(16) for c in range(16)
           if (c - 8) ** 2 + (r - 8) ** 2 >= 57]
assert len(HEAD_RC) == 79


def header_bits(data):
    """68 bits: 2-byte length, CRC-32 of the data, 20-bit check."""
    h6 = len(data).to_bytes(2, 'big') + crc32(data).to_bytes(4, 'big')
    v = (int.from_bytes(h6, 'big') << 20) | (crc32(h6) % (1 << 20))
    return [(v >> (67 - i)) & 1 for i in range(68)]


class Page:
    def __init__(self, grid, sidecar):
        self.grid, self.sidecar = grid, sidecar


def pages(data, ring='circle', seed=0):
    """All printed pages of one payload."""
    L = len(data)
    assert 0 < L < 65536
    N = -(-L // CHUNK)
    body = data + bytes(N * CHUNK - L)
    chunks = [body[CHUNK * i:CHUNK * i + CHUNK] for i in range(N)]
    hb = header_bits(data)
    out = []
    for p in range(-(-N // PER_PAGE)):
        ids = list(range(PER_PAGE * p, min(N, PER_PAGE * p + PER_PAGE)))
        out.append(_page(ids, chunks, hb, ring, seed * 1000 + p, p, L))
    return out


def _page(ids, chunks, hb, ring, seed, p, L):
    g = np.zeros((H, W), np.uint8)
    r, c = np.mgrid[0:H, 0:W]
    tim = (r % 17 == 0) | (c % 17 == 0)
    g[tim] = ((r + c) % 2)[tim]
    val = ring_value if ring == 'circle' else square_value
    for bi, bj in BULLS:
        k = 0
        for rr in range(16):
            for cc in range(16):
                v = val(cc - 8, rr - 8)
                if v is None:              # header module (circle only)
                    v = hb[k] if k < 68 else 0
                    k += 1
                g[17 * bi + 1 + rr, 17 * bj + 1 + cc] = v
    # placement: band k (block rows 10k..10k+9) x column third t
    n = len(ids)
    rng = np.random.default_rng(seed)
    slot_chunk = {}
    left = []
    for k in range(3):
        for t in range(3):
            slots = [(bi, bj) for bi in range(10 * k, 10 * k + 10)
                     for bj in range(7 * t, 7 * t + 7) if (bi, bj) not in BULLS]
            mine = [i for i in range(n) if (i + k) % 3 == t]
            mine = [mine[j] for j in rng.permutation(len(mine))]
            assert len(mine) <= len(slots)
            for s, i in zip(slots, mine):
                slot_chunk[s] = (i, k)
            left += slots[len(mine):]
    for j, s in enumerate(left):          # fourth copies, index order
        if j < n:
            slot_chunk[s] = (j, 3)
    for (bi, bj), (i, copy) in slot_chunk.items():
        gi = ids[i]
        blk = gi.to_bytes(2, 'big') + chunks[gi]
        blk += crc32(blk).to_bytes(4, 'big')
        bits = np.unpackbits(np.frombuffer(blk, np.uint8)).reshape(16, 16)
        g[17 * bi + 1:17 * bi + 17, 17 * bj + 1:17 * bj + 17] = bits
    side = dict(page=p, ring=ring, length=L, chunks=[ids[0], ids[-1]] if ids else [],
                header=''.join(map(str, hb)),
                slots=[[bi, bj, ids[i], copy] for (bi, bj), (i, copy)
                       in sorted(slot_chunk.items())],
                bullseyes=[[bi, bj, 17 * bj + 9, 17 * bi + 9] for bi, bj in BULLS])
    return Page(g, side)


# ---- the sheet: the grid on A4 ---------------------------------------------
# Usable area 182 x 277 mm (10 mm margins, 18 mm gutter, bound edge left);
# the grid is centred in it.  Paper edges in module units, grid at (0, 0).
GRID_W_MM, GRID_H_MM = W * MODULE_MM, H * MODULE_MM
PAPER_L = -(18 + (182 - GRID_W_MM) / 2) / MODULE_MM
PAPER_R = W + (10 + (182 - GRID_W_MM) / 2) / MODULE_MM
PAPER_T = -(10 + (277 - GRID_H_MM) / 2) / MODULE_MM
PAPER_B = H + (10 + (277 - GRID_H_MM) / 2) / MODULE_MM
INK, PAPER, TABLE = 30.0, 235.0, 70.0


def glyph_line(seed=5):
    """The leaf's overt header in type below the grid: 5 x 7 random glyphs,
    one module per glyph pixel, 7 modules below the grid (no reader reads
    it; it is clutter for the bullseye search)."""
    rng = np.random.default_rng(seed)
    cells = []
    x = 20
    for _ in range(48):
        if rng.random() < 0.15:
            x += 6
            continue
        cells.append((x, rng.random((7, 5)) < 0.45))
        x += 6
    return [(x, H + 7, m) for x, m in cells]


def hires(page, box, R, stamps=(), background=TABLE):
    """Reflectance image of the sheet over module box (c0, r0, c1, r1) at R
    px/module, before blur.  Stamps (module coordinates):
      ('ink', c0, r0, c1, r1)            rectangle of ink
      ('disc', c, r, radius)             ink blot
      ('line', c0, r0, c1, r1, width, v) scratch: v = 1 ink, 0 paper
      ('torn', corner, size)             page corner missing (shows table);
                                         corner in tl/tr/bl/br, size modules
    """
    c0, r0, c1, r1 = box
    nx, ny = int(round((c1 - c0) * R)), int(round((r1 - r0) * R))
    xs = c0 + (np.arange(nx) + 0.5) / R
    ys = r0 + (np.arange(ny) + 0.5) / R
    X, Y = np.meshgrid(xs, ys)
    ci, ri = np.floor(X).astype(np.int64), np.floor(Y).astype(np.int64)
    ink = np.zeros((ny, nx), bool)
    ing = (ci >= 0) & (ci < W) & (ri >= 0) & (ri < H)
    ink[ing] = page.grid[ri[ing], ci[ing]] == 1
    for gx, gy, m in glyph_line():
        sel = (ci >= gx) & (ci < gx + 5) & (ri >= gy) & (ri < gy + 7)
        ink[sel] = m[ri[sel] - gy, ci[sel] - gx]
    paper = (X >= PAPER_L) & (X < PAPER_R) & (Y >= PAPER_T) & (Y < PAPER_B)
    for st in stamps:
        kind = st[0]
        if kind == 'ink':
            _, a, b, c, d = st
            ink |= (X >= a) & (X < c) & (Y >= b) & (Y < d)
        elif kind == 'disc':
            _, a, b, rad = st
            ink |= (X - a) ** 2 + (Y - b) ** 2 < rad ** 2
        elif kind == 'line':
            _, a, b, c, d, wd, v = st
            dx, dy = c - a, d - b
            ln = math.hypot(dx, dy)
            t = ((X - a) * dx + (Y - b) * dy) / ln
            dist = np.abs((X - a) * dy - (Y - b) * dx) / ln
            sel = (dist < wd / 2) & (t >= 0) & (t <= ln)
            ink[sel] = bool(v)
        elif kind == 'torn':
            _, corner, size = st
            u = (X - PAPER_L) if corner[1] == 'l' else (PAPER_R - X)
            v = (Y - PAPER_T) if corner[0] == 't' else (PAPER_B - Y)
            paper &= ~(u + v < size)
    img = np.where(ink, INK, PAPER).astype(np.float32)
    img[~paper] = background
    return img


def gblur(img, sig):
    if sig <= 0:
        return img
    for ax in (0, 1):
        n = img.shape[ax]
        pad = int(4 * sig) + 2
        widths = [(0, 0), (0, 0)]
        widths[ax] = (pad, pad)
        a = np.pad(img, widths, mode='edge')
        m = a.shape[ax]
        f = np.fft.rfftfreq(m)
        kern = np.exp(-2 * (np.pi * f * sig) ** 2)
        shape = [1, 1]
        shape[ax] = -1
        a = np.fft.irfft(np.fft.rfft(a, axis=ax) * kern.reshape(shape), n=m, axis=ax)
        img = (a[pad:pad + n] if ax == 0 else a[:, pad:pad + n]).astype(np.float32)
    return img


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(A, float))
    return vt[-1].reshape(3, 3) / vt[-1, -1]


def apply(Hm, x, y):
    d = Hm[2, 0] * x + Hm[2, 1] * y + Hm[2, 2]
    return (Hm[0, 0] * x + Hm[0, 1] * y + Hm[0, 2]) / d, (Hm[1, 0] * x + Hm[1, 1] * y + Hm[1, 2]) / d


VIEWS = {   # module rectangles (c0, r0, c1, r1); quarters overlap by 8 modules
    'whole': None,
    'tl': (-8, -8, W / 2 + 8, H / 2 + 8),
    'tr': (W / 2 - 8, -8, W + 8, H / 2 + 8),
    'bl': (-8, H / 2 - 8, W / 2 + 8, H + 8),
    'br': (W / 2 - 8, H / 2 - 8, W + 8, H + 8),
}


def frame(page, view='whole', spm=2.0, persp=0.02, sigma=0.3, rot=0.0, turns=0,
          illum=0.2, noise=10.0, seed=0, stamps=(), background=TABLE, R=None, ss=3,
          rect=None):
    """One camera frame.  view: a VIEWS key or rect=(c0, r0, c1, r1) modules.
    The whole view is the paper plus 3 % of background on each side.
    persp: each frame corner displaced by up to persp x frame diagonal (at
    least half of it), random direction.  rot: degrees, about the frame
    centre.  turns: quarter turns (counter-clockwise, numpy rot90)."""
    rng = np.random.default_rng(seed)
    if rect is None and VIEWS.get(view) is None:
        pw, ph = PAPER_R - PAPER_L, PAPER_B - PAPER_T
        rect = (PAPER_L - 0.03 * pw, PAPER_T - 0.03 * ph, PAPER_R + 0.03 * pw, PAPER_B + 0.03 * ph)
    elif rect is None:
        rect = VIEWS[view]
    c0, r0, c1, r1 = rect
    fw, fh = int(round((c1 - c0) * spm)), int(round((r1 - r0) * spm))
    diag = math.hypot(fw, fh)
    th = math.radians(rot)
    cx, cy = fw / 2, fh / 2
    src = [(c0, r0), (c1, r0), (c0, r1), (c1, r1)]
    dst = []
    for (u, v) in [(0, 0), (fw, 0), (0, fh), (fw, fh)]:
        u, v = u - cx, v - cy
        u, v = u * math.cos(th) - v * math.sin(th), u * math.sin(th) + v * math.cos(th)
        a = rng.uniform(0, 2 * math.pi)
        rr = persp * diag * math.sqrt(rng.uniform(0.25, 1))
        dst.append((u + cx + rr * math.cos(a), v + cy + rr * math.sin(a)))
    Hf = homography(src, dst)                 # module -> continuous px
    Hi = np.linalg.inv(Hf)
    # module box seen by the frame, plus the blur support
    corners = [apply(Hi, u, v) for u, v in [(0, 0), (fw, 0), (0, fh), (fw, fh)]]
    m = 4 * sigma + 2
    box = (math.floor(min(p[0] for p in corners) - m), math.floor(min(p[1] for p in corners) - m),
           math.ceil(max(p[0] for p in corners) + m), math.ceil(max(p[1] for p in corners) + m))
    if R is None:
        R = max(6, int(math.ceil(2 * spm)))
    hi = gblur(hires(page, box, R, stamps, background), sigma * R)
    img = np.zeros((fh, fw), np.float64)
    hb, wb = hi.shape
    for i0 in range(0, fh, 256):              # row chunks bound the memory
        i1 = min(fh, i0 + 256)
        yy, xx = np.mgrid[i0:i1, 0:fw].astype(np.float64)
        acc = np.zeros((i1 - i0, fw))
        for sy in range(ss):
            for sx in range(ss):
                mc, mr = apply(Hi, xx + (sx + 0.5) / ss, yy + (sy + 0.5) / ss)
                hx = (mc - box[0]) * R - 0.5
                hy = (mr - box[1]) * R - 0.5
                hx = np.clip(hx, 0, wb - 1.001)
                hy = np.clip(hy, 0, hb - 1.001)
                ii, jj = hy.astype(np.int64), hx.astype(np.int64)
                fy, fx = hy - ii, hx - jj
                acc += (hi[ii, jj] * (1 - fx) * (1 - fy) + hi[ii, jj + 1] * fx * (1 - fy)
                        + hi[ii + 1, jj] * (1 - fx) * fy + hi[ii + 1, jj + 1] * fx * fy)
        img[i0:i1] = acc / ss ** 2
    a = rng.uniform(0, 2 * math.pi)
    yy, xx = np.mgrid[0:fh, 0:fw].astype(np.float64)
    gx = (xx - cx) * math.cos(a) + (yy - cy) * math.sin(a)
    gx = gx / max(1e-9, np.abs(gx).max())
    img = img * (1 + illum * gx) + rng.normal(0, noise, img.shape)
    img = np.clip(np.round(img), 0, 255).astype(np.uint8)
    # quarter turns, and the truth homography with them
    T = np.eye(3)
    w_, h_ = fw, fh
    for _ in range(turns % 4):
        T = np.array([[0, 1, 0], [-1, 0, w_], [0, 0, 1]], float) @ T   # (x, y) -> (y, w - x)
        w_, h_ = h_, w_
    img = np.rot90(img, turns % 4).copy()
    Hfull = T @ Hf
    truth = dict(view=view, rect=list(rect),
                 spm=spm, persp=persp, sigma=sigma, rot=rot, turns=turns % 4,
                 illum=illum, noise=noise, seed=seed, size=[img.shape[1], img.shape[0]],
                 H=Hfull.tolist(), page=page.sidecar['page'], stamps=[list(s) for s in stamps],
                 bullseyes=[])
    for bi, bj in BULLS:
        cc, rc = 17 * bj + 9.5, 17 * bi + 9.5        # centre of the centre module
        x, y = apply(Hfull, cc, rc)
        ex = apply(Hfull, cc + 1, rc)
        ey = apply(Hfull, cc, rc + 1)
        pitch = (math.hypot(ex[0] - x, ex[1] - y) + math.hypot(ey[0] - x, ey[1] - y)) / 2
        foot = [apply(Hfull, cc + dx, rc + dy) for dx in (-8, 8) for dy in (-8, 8)]
        inside = all(1 <= fx_ <= img.shape[1] - 2 and 1 <= fy_ <= img.shape[0] - 2
                     for fx_, fy_ in foot)
        truth['bullseyes'].append(dict(bi=bi, bj=bj, x=x - 0.5, y=y - 0.5, pitch=pitch,
                                       inside=bool(inside)))
    return img, truth


def write_pgm(path, img):
    h, w = img.shape
    with open(path, 'wb') as f:
        f.write(b'P5 %d %d 255\n' % (w, h) + img.tobytes())


def loupe_grid(page, flips=0.0, seed=7):
    """The module grid as text (H lines of W '0'/'1'), each module flipped
    with probability `flips` (seeded)."""
    g = page.grid.copy()
    if flips:
        fl = np.random.default_rng(seed).random(g.shape) < flips
        g[fl] ^= 1
    return ''.join(''.join('01'[v] for v in row) + '\n' for row in g)


# ---- stamps used by the measurements ---------------------------------------
def bull_black(i):
    bi, bj = BULLS[i]
    return ('ink', 17 * bj + 1, 17 * bi + 1, 17 * bj + 17, 17 * bi + 17)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == 'page':
        data = open(a[1], 'rb').read()
        ring = a[a.index('--ring') + 1] if '--ring' in a else 'circle'
        seed = int(a[a.index('--seed') + 1]) if '--seed' in a else 0
        os.makedirs(a[2], exist_ok=True)
        for pg in pages(data, ring, seed):
            p = pg.sidecar['page']
            open(os.path.join(a[2], f'page{p}.grid.txt'), 'w').write(loupe_grid(pg))
            json.dump(pg.sidecar, open(os.path.join(a[2], f'page{p}.json'), 'w'))
        return
    if a[0] == 'frame':
        data = open(a[1], 'rb').read()
        kw = {}
        for kv in a[3:]:
            k, v = kv.split('=')
            kw[k] = v if k == 'view' else float(v) if '.' in v else int(v)
        pg = pages(data, kw.pop('ring', 'circle'), kw.pop('pseed', 0))[kw.pop('page', 0)]
        img, truth = frame(pg, **kw)
        write_pgm(a[2], img)
        json.dump(truth, open(os.path.splitext(a[2])[0] + '.json', 'w'), indent=1)
        return
    raise SystemExit(__doc__)


if __name__ == '__main__':
    main()

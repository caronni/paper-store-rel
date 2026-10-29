#!/usr/bin/env python3
"""verify_variant.py -- bootstrap/r2/verify_grid.py with the format round's
bullseye variants (bootstrap/format-round/README.md), re-derived here from
the README's text, independent of gen_variant.py (stdlib only):

  --bullseye record|v1|v2|v3  the ring rule and header order to check
      against: record / v3 ink rings {0, 2, 4, 6} (cross-checked with the
      spec's q table), v1 {0, 2, 4, 5, 6}, v2 {1, 3, 5}; v3's two axis
      modules, block-local (r, c) = (8, 0) and (0, 8), must be white and
      carry no bit (68 bits on the other 77 header modules, 9 white);
      module counts per block: record / v3 85 ink, 92 white, 79 header
      (v3: 77 + 2 axis), v1 113 / 64 / 79, v2 52 / 125 / 79;
  --rings coarse|dot  with --pbm: coarse = the grid placed module-solid
      (verify_grid.py's check); dot = every dot of a bullseye RING module
      (q <= 42) must equal the circle rule (ink iff floor(rho + 0.5) is an
      ink ring, rho = the distance in modules from the dot's centre to the
      centre of the block's module (0,0), float arithmetic here), every
      other dot the grid placed module-solid; and the grid is the pattern
      at module centres (the circle rule at each ring module's centre point
      == its grid value).  Reported, not gated: per ring module the share
      of its dots equal to its grid value and of its central 2 x 2 dots.
  The sidecar's "variant" entry must be absent for record / coarse and
  name the kind and rings otherwise.

----- verify_grid.py's docstring, unchanged: -----
R2 format self-check, R2-FORMAT v1 (bootstrap/R2-FORMAT.md, 2026-10-20;
amended 2026-10-20 night: the copies of a chunk across pages).

Independent of any reader and of gen.py (shares no code with it; stdlib
only).  Reads module grids as text (H lines of W '0'/'1') and re-derives
everything from the spec:
  - shape 358 x 511; every timing module ((r + c) % 2 on r % 17 == 0 or
    c % 17 == 0);
  - the 15 bullseye blocks: ring modules by the spec's q table (and the
    round(sqrt q) rule, cross-checked), the quiet ring 43..56 white, the 79
    header modules (85 ink / 92 white / 79 header per block), the 68 header
    bits and the 11 white tail, the 20-bit check, all 15 headers identical
    (and identical across the pages given); length 0 refused; ORIENTATION:
    each bullseye's header read from the grid itself as a reader would from
    the page turned 90, 180 and 270 degrees (timing lines included) must
    fail the 20-bit check;
  - every one of the 615 data slots: white (all 256 modules 0) or a block
    whose bytes 28-31 equal the CRC-32 over the six header bytes (length
    BE16, data CRC-32 BE32, as read from the bullseyes) followed by bytes
    0-27, whose index belongs to a group this page carries and whose 26
    bytes are chunk i of the payload (with --payload), zero-padded at the
    end;
  - placement: the DESIGNED placement (R2-FORMAT, 2026-10-20; tables
    D_PI1, D_PI2, D_SKIP, D_OVERFLOW typed from the spec and derived here
    independently of gen.py) slot by slot, with the pages of the amendment
    of 2026-10-20 night: chunk j = index i = j mod 204 of group g = j //
    204, P = ceil(N / 204), d = max(1, (P + 1) // 3); band k of page q
    holds copy k of every chunk of group (q - k d) mod P: copy 0 of index i
    at band-0 slot i, copies 1 and 2 at the same rank of free rows in
    columns PI1[c], PI2[c], the band-2 crossings and the overflow; the
    leftover slots in raster order the fourth copies of group (q + s) mod
    P (s the smallest s >= 1 not congruent to -d or -2d mod P; for P <= 3
    group q), indices 0, 1, ..., the rest white;
  - the GUARANTEES, from the grids themselves: on every page each chunk of
    a band's group once in that band (plus its fourth copy for the
    fourth-copy group, indices 0 .. m-1, in block raster order by index,
    every white slot after them); over the OVERLAY of the pages given (a
    chunk's placed copies wherever they sit), for every chunk whose three
    placed copies are among them: for P >= 3 the three on three different
    pages, and (1) one in each band (block rows 0-9, 10-19, 20-29), (2)
    block columns pairwise >= 5 apart, (3) the narrowest straight strip (any
    angle; exact) touching all three block interiors >= 91 modules (46.2 mm
    at 12 dots), (4) r2 - r0 >= 19 block rows, (5) the smallest disc
    touching all three >= 79.9 mm radius (certified lower bound, branch and
    bound), (6) no line through two copies within 7.36 block columns of the
    third at its row (exact minimum of the design 140/19 = 7.368).  Which
    copy of a 4-copy chunk is the
    fourth: the design's when the grid matches it, else the sidecar's when
    it matches the grid, else the earliest choice the guarantees allow;
  - with a sidecar (PREFIX.json beside PREFIX.grid.txt, used when present):
    its placement tables equal the spec's, the design replayed from the
    sidecar's own tables equals its slot_chunk / slot_copy; slot_block, the
    bullseye list, the header, data length / CRC / SHA-256 and the files'
    SHA-256;
  - with --pbm: module_dots, x0, y0 re-derived from the spec (12 dots; the
    grid centred in the 182 x 277 mm usable area at 18 / 10 mm: 426, 441),
    the sidecar's values must equal them; PREFIX.pbm is exactly the grid
    there on a 4960 x 7016 page, nothing inked elsewhere;
  - when the pages given hold every chunk (for P = 3 a single page can):
    the chunks assemble to the header's length and CRC-32; when every page
    is given they must.

Usage: verify_grid.py GRID.txt [GRID.txt ...] [--payload FILE] [--pbm]
                      [--no-sidecar]
       (verify_variant.py: also [--bullseye K] [--rings R])
Exit status 0 iff every check passes; every deviation is printed as FAIL.
"""
import argparse
import hashlib
import heapq
import json
import math
import os
import sys
import zlib

W_SPEC, H_SPEC, BW_SPEC, BH_SPEC = 358, 511, 21, 30
PER_PAGE, CHUNK = 204, 26
MIN_SPREAD = 5                      # guarantee: block columns pairwise apart
INK_Q = {0, 4, 5, 13, 16, 17, 18, 20, 32, 34, 36, 37, 40, 41}
BULL = [(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)] + \
       [(bi, bj) for bi in (8, 20) for bj in (5, 11, 17)]
BULL_RASTER = sorted(BULL)


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


V_INK = {"record": {0, 2, 4, 6}, "v3": {0, 2, 4, 6},
         "v1": {0, 2, 4, 5, 6}, "v2": {1, 3, 5}}
V_AXIS = {"v3": {(8, 0), (0, 8)}}
V_COUNTS = {"record": (85, 92, 79), "v3": (85, 92, 79),
            "v1": (113, 64, 79), "v2": (52, 125, 79)}
VK = {"kind": "record", "rings": "coarse"}


def local_kind(r, c, kind="record"):
    """Block-local (r, c) -> 'ink' / 'white' / 'header' / 'axis' by the
    README's text."""
    q = (c - 8) ** 2 + (r - 8) ** 2
    if q >= 57:
        return "axis" if (r, c) in V_AXIS.get(kind, ()) else "header"
    if q >= 43:
        return "white"
    d = int(round(math.sqrt(q)))     # no ties: sqrt q is never k + 1/2
    by_rule = "ink" if d in V_INK[kind] else "white"
    if kind in ("record", "v3"):
        by_table = "ink" if q in INK_Q else "white"
        assert by_rule == by_table, (q, by_rule, by_table)
    return by_rule


KIND = []
HDR_POS = []


def set_kind(kind, rings):
    VK.update(kind=kind, rings=rings)
    KIND[:] = [[local_kind(r, c, kind) for c in range(16)] for r in range(16)]
    HDR_POS[:] = [(r, c) for r in range(16) for c in range(16)
                  if KIND[r][c] == "header"]


set_kind("record", "coarse")


def bits_to_bytes(bits):
    return bytes(int("".join(map(str, bits[8 * k:8 * k + 8])), 2)
                 for k in range(len(bits) // 8))


class Page:
    pass


def check_page(path, a, errs):
    """Structural checks of one grid; returns a Page or None."""
    def fail(msg):
        errs.append(f"{os.path.basename(path)}: {msg}")
    pg = Page()
    pg.path = path
    with open(path, "rb") as f:
        raw = f.read()
    lines = raw.decode("ascii").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    pg.H, pg.W = len(lines), len(lines[0]) if lines else 0
    if (pg.W, pg.H) != (W_SPEC, H_SPEC):
        fail(f"grid {pg.W}x{pg.H}, spec {W_SPEC}x{H_SPEC}")
        return None
    for r, ln in enumerate(lines):
        if len(ln) != W_SPEC or set(ln) - {"0", "1"}:
            fail(f"row {r}: bad length or characters")
            return None
    g = [[ord(ch) - 48 for ch in ln] for ln in lines]
    pg.g = g
    # timing lattice
    pg.bad_timing = sum(1 for r in range(H_SPEC) for c in range(W_SPEC)
                        if (r % 17 == 0 or c % 17 == 0)
                        and g[r][c] != (r + c) % 2)
    if pg.bad_timing:
        fail(f"timing lattice: {pg.bad_timing} wrong modules")
    # bullseyes
    kinds_count = {k: sum(row.count(k) for row in KIND)
                   for k in ("ink", "white", "header", "axis")}
    ni, nw, nh = V_COUNTS[VK["kind"]]
    na = len(V_AXIS.get(VK["kind"], ()))
    want_counts = {"ink": ni, "white": nw, "header": nh - na, "axis": na}
    if kinds_count != want_counts:
        fail(f"bullseye module counts {kinds_count} != {want_counts}")
    pg.headers = []
    pg.bad_ring = 0
    for bi, bj in BULL:
        blk = [g[17 * bi + 1 + r][17 * bj + 1:17 * bj + 17] for r in range(16)]
        for r in range(16):
            for c in range(16):
                k = KIND[r][c]
                if k != "header" and blk[r][c] != (k == "ink"):
                    pg.bad_ring += 1
        pg.headers.append([blk[r][c] for r, c in HDR_POS])
    if pg.bad_ring:
        fail(f"bullseye rings: {pg.bad_ring} wrong modules")
    if any(h != pg.headers[0] for h in pg.headers):
        fail("the 15 bullseye headers differ")
    hb = pg.headers[0]
    if any(hb[68:]):
        fail(f"header: the last {len(hb) - 68} header modules are not white")
    six = bits_to_bytes(hb[:48])
    chk = int("".join(map(str, hb[48:68])), 2)
    if crc(six) % (1 << 20) != chk:
        fail(f"header check 0x{chk:05x} != CRC-32 of the six bytes mod 2^20 "
             f"0x{crc(six) % (1 << 20):05x}")
    pg.hbits = hb[:68]
    pg.six = six
    pg.length = int.from_bytes(six[:2], "big")
    pg.dcrc = int.from_bytes(six[2:], "big")
    if pg.length == 0:
        fail("header length 0: the spec refuses an empty payload")
    # orientation: read each bullseye's header as a reader would from the
    # page turned 90, 180, 270 degrees (the grid's own modules, timing lines
    # included); none may pass the 20-bit check
    pg.turned = []
    for bi, bj in BULL:
        cr, cc = 17 * bi + 9, 17 * bj + 9
        for m in (1, 2, 3):
            bits = []
            for r, c in HDR_POS[:68]:
                dy, dx = r - 8, c - 8
                for _ in range(m):
                    dy, dx = -dx, dy
                bits.append(g[cr + dy][cc + dx])
            s6 = bits_to_bytes(bits[:48])
            if crc(s6) % (1 << 20) == int("".join(map(str, bits[48:])), 2):
                pg.turned.append((bi, bj, m))
    if pg.turned:
        fail(f"orientation: the header also passes its check read turned "
             f"{sorted({90 * m for _, _, m in pg.turned})} degrees at "
             f"bullseye blocks {[t[:2] for t in pg.turned][:6]} (the spec "
             "refuses such a payload)")
    # data slots
    be = set(BULL)
    pg.slots = [(bi, bj) for bi in range(BH_SPEC) for bj in range(BW_SPEC)
                if (bi, bj) not in be]
    if len(pg.slots) != 615:
        fail(f"{len(pg.slots)} data slots, spec 615")
    pg.content = []                 # per slot: None (white) or (index, 26 B)
    pg.bad_crc = 0
    for s, (bi, bj) in enumerate(pg.slots):
        bits = []
        for r in range(16):
            bits.extend(g[17 * bi + 1 + r][17 * bj + 1:17 * bj + 17])
        if not any(bits):
            pg.content.append(None)
            continue
        blk = bits_to_bytes(bits)
        # bytes 28-31: CRC-32 of the six header bytes + bytes 0-27
        if crc(six + blk[:28]) != int.from_bytes(blk[28:], "big"):
            pg.bad_crc += 1
            pg.content.append(("BAD", None))
            continue
        pg.content.append((int.from_bytes(blk[:2], "big"), blk[2:28]))
    if pg.bad_crc:
        fail(f"{pg.bad_crc} non-white data slots fail CRC-32 (over the six "
             "header bytes + block bytes 0-27)")
    pg.side = None
    sp = path[:-len(".grid.txt")] + ".json" if path.endswith(".grid.txt") \
        else None
    if not a.no_sidecar and sp and os.path.exists(sp):
        with open(sp) as f:
            pg.side = json.load(f)
        pg.side_path = sp
    return pg


def strip_modules(pts, s=8.0):
    """Narrowest straight strip meeting every axis-aligned square of half-side
    s centred at pts (x, y), exact (modules; 0 if one line meets them all):
    min over directions of the projections' spread minus 2 s (|cos| + |sin|),
    a piecewise sinusoid, evaluated at every breakpoint (a pair of centres
    level, an axis) and at any trough inside a piece."""
    angles = {0.0, math.pi / 2}
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            angles.add((math.atan2(pts[i][1] - pts[j][1],
                                   pts[i][0] - pts[j][0]) + math.pi / 2)
                       % math.pi)
    angles = sorted(angles) + [math.pi]

    def width(t):
        u, v = math.cos(t), math.sin(t)
        pr = [u * x + v * y for x, y in pts]
        return max(pr) - min(pr) - 2 * s * (abs(u) + abs(v))
    low = math.inf
    for t0, t1 in zip(angles, angles[1:]):
        low = min(low, width(t0), width(t1))
        if t1 - t0 < 1e-12:
            continue
        u, v = math.cos((t0 + t1) / 2), math.sin((t0 + t1) / 2)
        pr = [u * x + v * y for x, y in pts]
        hi, lo = pr.index(max(pr)), pr.index(min(pr))
        wx = pts[hi][0] - pts[lo][0] - 2 * s * (1 if u > 0 else -1)
        wy = pts[hi][1] - pts[lo][1] - 2 * s
        trough = math.atan2(wy, wx) + math.pi
        if any(t0 < trough + 2 * math.pi * k < t1 for k in (-1, 0, 1)):
            low = min(low, -math.hypot(wx, wy))
    return max(0.0, low)


def blot_modules(pts, s=8.0, eps=1e-4):
    """Certified LOWER BOUND (modules, within eps of the exact value) on the
    radius of the smallest disc touching every axis-aligned square of
    half-side s centred at pts.  F(p) = max_j dist(p, square_j) is convex and
    1-Lipschitz, its minimiser lies in the squares' bounding box, and a cell
    of side h centred at q has F >= F(q) - h / sqrt(2): branch and bound
    until the best cell's bound is within eps of the best value seen."""
    def F(x, y):
        return max(math.hypot(max(abs(x - cx) - s, 0.0),
                              max(abs(y - cy) - s, 0.0)) for cx, cy in pts)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    side = max(max(xs) - min(xs), max(ys) - min(ys)) + 2 * s
    x, y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    k = 0.7072                                   # > sqrt(2) / 2
    ub = F(x, y)
    heap = [(ub - side * k, x, y, side)]
    while heap:
        lb, x, y, sz = heapq.heappop(heap)
        if lb >= ub - eps:
            return lb
        h = sz / 2
        for dx in (-h / 2, h / 2):
            for dy in (-h / 2, h / 2):
                v = F(x + dx, y + dy)
                ub = min(ub, v)
                heapq.heappush(heap, (v - h * k, x + dx, y + dy, h))
    return ub


def copy_report(cp):
    """cp = [(r, c)] block row/column of the placed copies (bands 0, 1, 2)
    -> the six guarantee quantities: one copy per band (rows), the min
    pairwise column spread, the strip (modules) touching all three block
    interiors, r2 - r0, the blot radius lower bound (modules), and the min
    horizontal distance of a copy from the line through the other two at
    its row (block columns)."""
    spread = min(abs(cp[0][1] - cp[1][1]), abs(cp[0][1] - cp[2][1]),
                 abs(cp[1][1] - cp[2][1]))
    centres = [(17 * c + 9, 17 * r + 9) for r, c in cp]
    off = math.inf
    for t in range(3):
        (ra, ca), (rb, cb) = [cp[x] for x in range(3) if x != t]
        rt, ct = cp[t]
        off = min(off, abs((ct - ca) * (rb - ra) - (cb - ca) * (rt - ra))
                  / abs(rb - ra))
    return dict(bands=sorted(r // 10 for r, _ in cp), spread=spread,
                strip=strip_modules(centres), rows=cp[2][0] - cp[0][0],
                blot=blot_modules(centres), off=off)


def guarantee_failures(rep):
    """The guarantees (R2-FORMAT, designed placement) a copy report breaks."""
    out = []
    if rep["bands"] != [0, 1, 2]:
        out.append(f"placed copies in bands {rep['bands']} (guarantee: one "
                   "in each of bands 0, 1, 2)")
    if rep["spread"] < MIN_SPREAD:
        out.append(f"columns only {rep['spread']} apart (guarantee: >= "
                   f"{MIN_SPREAD})")
    if rep["strip"] < STRIP_BOUND:
        out.append(f"a straight strip {rep['strip']:.1f} modules wide "
                   f"touches all three (guarantee: >= {STRIP_BOUND:g})")
    if rep["rows"] < MIN_ROWS_0_2:
        out.append(f"copies 0 and 2 only {rep['rows']} block rows apart "
                   f"(guarantee: >= {MIN_ROWS_0_2})")
    if rep["blot"] < BLOT_BOUND:
        out.append(f"a disc of radius {rep['blot'] * MODULE_MM:.2f} mm "
                   f"touches all three (guarantee: >= {BLOT_BOUND_MM} mm)")
    if rep["off"] < OFFLINE_BOUND:
        out.append(f"a line through two copies passes {rep['off']:.3f} "
                   f"columns from the third (guarantee: >= {OFFLINE_BOUND})")
    return out


# The designed placement (R2-FORMAT, 2026-10-20), typed from the spec:
D_PI1 = [11, 13, 15, 16, 20, 10, 12, 1, 14, 17, 18, 19, 0, 6, 8, 9, 3, 2, 4,
         7, 5]
D_PI2 = [6, 7, 8, 9, 15, 0, 1, 16, 2, 3, 4, 5, 17, 18, 19, 20, 10, 11, 12,
         13, 14]
D_SKIP = {5: 9, 12: 9, 14: 9, 20: 0}
D_OVERFLOW = {12: (29, 19), 20: (29, 0)}
# The guarantees (R2-FORMAT): one copy per band, MIN_SPREAD and these four.
MODULE_MM = 12 * 25.4 / 600            # the spec's module, 0.508 mm
STRIP_BOUND = 91.0                     # modules (46.2 mm)
MIN_ROWS_0_2 = 19                      # block rows, copy 0 to copy 2
BLOT_BOUND_MM = 79.9
BLOT_BOUND = BLOT_BOUND_MM / MODULE_MM  # modules
OFFLINE_BOUND = 7.36                   # block columns (exact min 140/19)


def design_map(n, pi1=D_PI1, pi2=D_PI2, skip=D_SKIP, overflow=D_OVERFLOW):
    """The designed placement for n chunks on one page -> {slot: (local
    chunk, copy)}.  Copy 0 at band-0 slot i; copies 1 and 2 at the same rank
    of free rows in columns pi1[c], pi2[c]; a band-2 column changing between
    10 and 9 free rows skips rank skip[c] (the dropped chunk's copy 2 at
    overflow[c]); fourth copies of chunks 0, 1, ... in the leftovers."""
    be = set(BULL)
    slots = [(bi, bj) for bi in range(BH_SPEC) for bj in range(BW_SPEC)
             if (bi, bj) not in be]
    at = {b: s for s, b in enumerate(slots)}

    def rows(k, col):
        return [r for r in range(10 * k, 10 * k + 10) if (r, col) not in be]
    band0 = [b for b in slots if b[0] < 10]
    res = {}
    for i in range(n):
        r0, c = band0[i]
        k = rows(0, c).index(r0)
        r2s, n0 = rows(2, pi2[c]), len(rows(0, c))
        if len(r2s) == n0:
            m = k
        elif n0 > len(r2s):
            m = None if k == skip[c] else (k if k < skip[c] else k - 1)
        else:
            m = k if k < skip[c] else k + 1
        b2 = tuple(overflow[c]) if m is None else (r2s[m], pi2[c])
        for copy, b in enumerate([(r0, c), (rows(1, pi1[c])[k], pi1[c]),
                                  b2]):
            if at[b] in res:
                raise SystemExit(f"design: slot {b} taken twice")
            res[at[b]] = (i, copy)
    left = sorted(s for s in range(len(slots)) if s not in res)
    for s, i in zip(left, range(n)):
        res[s] = (i, 3)
    return res


def page_step(P):
    """d = max(1, (P + 1) // 3): copy k of group g on page (g + k d) mod P."""
    return max(1, (P + 1) // 3)


def band_group(q, k, P):
    return (q - k * page_step(P)) % P


def fourth_group(q, P):
    d = page_step(P)
    for s in range(1, P):
        if s % P not in (0, -d % P, -2 * d % P):
            return (q + s) % P
    return q


def gsize(g, N):
    return max(0, min(PER_PAGE, N - PER_PAGE * g))


def page_map(q, N, P, pi1=D_PI1, pi2=D_PI2, skip=D_SKIP,
             overflow=D_OVERFLOW):
    """Page q of a payload of N chunks on P pages -> {slot: (global chunk,
    copy)}: band k carries copy k of group band_group(q, k) at the design's
    slots of its page-local indices; the leftovers, in raster order, the
    fourth copies of group fourth_group(q), indices 0, 1, ..."""
    full = design_map(PER_PAGE, pi1, pi2, skip, overflow)
    at = {(i, k): s for s, (i, k) in full.items() if k < 3}
    res = {}
    for k in range(3):
        g = band_group(q, k, P)
        for i in range(gsize(g, N)):
            if at[i, k] in res:
                raise SystemExit(f"design: slot {at[i, k]} taken twice")
            res[at[i, k]] = (PER_PAGE * g + i, k)
    f = fourth_group(q, P)
    left = sorted(s for s in range(615) if s not in res)
    for s, i in zip(left, range(gsize(f, N))):
        res[s] = (PER_PAGE * f + i, 3)
    return res


def check_placement(pg, p, N, P, payload, errs):
    def fail(msg):
        errs.append(f"{os.path.basename(pg.path)}: {msg}")
    groups = [band_group(p, k, P) for k in range(3)]
    F = fourth_group(p, P)
    on_page = sorted(set(groups) | {F})
    pg.p, pg.n, pg.groups, pg.F = p, gsize(p, N), groups, F
    bad = 0
    # payload / index checks
    where = {}
    for s, c in enumerate(pg.content):
        if c is None or c[0] == "BAD":
            continue
        i, body = c
        if i >= N or i // PER_PAGE not in on_page:
            bad += 1
            fail(f"slot {s}: index {i} not on page {p} (its groups "
                 f"{on_page} of {P}: bands {groups}, fourth copies {F})")
            continue
        if payload is not None:
            want = payload[CHUNK * i:CHUNK * (i + 1)].ljust(CHUNK, b"\0")
            if body != want:
                bad += 1
                fail(f"slot {s}: chunk {i} bytes differ from the payload")
        if i == N - 1 and pg.length % CHUNK and \
                any(body[pg.length - CHUNK * (N - 1):]):
            bad += 1
            fail(f"slot {s}: last chunk padding not zero")
        where.setdefault(i, []).append(s)
    # copy counts: one per band of the chunk's group, and one fourth copy
    # for chunks 0 .. m-1 of the fourth-copy group
    odd, four = [], []
    for g in on_page:
        base = groups.count(g)
        for il in range(gsize(g, N)):
            c = PER_PAGE * g + il
            cnt = len(where.get(c, []))
            if cnt == base + 1 and g == F:
                four.append(il)
            elif cnt != base:
                odd.append((c, cnt, base))
    m = len(four)
    if odd:
        bad += 1
        fail(f"chunks with the wrong number of copies on this page: "
             f"{[c for c, _, _ in odd[:8]]} (copies {[n for _, n, _ in odd[:8]]}"
             f", the design {[b for _, _, b in odd[:8]]} + a fourth copy for "
             f"group {F})")
    if four != list(range(m)):
        bad += 1
        fail(f"fourth copies must go to chunks {PER_PAGE * F} .. of group {F}"
             f" in index order; 4-copy chunks "
             f"{[PER_PAGE * F + i for i in four[:8]]}")
    whites = [s for s, c in enumerate(pg.content) if c is None]
    if whites and m != gsize(F, N):
        bad += 1
        fail(f"{len(whites)} white slots but only {m} of {gsize(F, N)} "
             f"chunks of group {F} have a fourth copy (leftovers take "
             "fourth copies before white)")
    # the designed placement, slot by slot (the spec's tables and pages)
    exp = page_map(p, N, P)
    mis = []
    for s, c in enumerate(pg.content):
        e = exp.get(s)
        got = None if c is None else (None if c[0] == "BAD" else c[0])
        if (e is None) != (c is None) or (e is not None and got != e[0]):
            mis.append(s)
    if mis:
        bad += 1
        fail(f"{len(mis)} slots differ from the designed placement (first: "
             f"slot {mis[0]} {pg.slots[mis[0]]}, designed "
             f"{exp.get(mis[0])}, grid "
             f"{None if pg.content[mis[0]] is None else pg.content[mis[0]][0]})")
    pg.design_ok = not mis
    # which copy is the fourth: the design's when the grid matches it, else
    # the sidecar's when it matches the grid, else from the grid: a copy in
    # a band that is not its group's, or, of two copies in one band, the
    # earliest choice the guarantees allow (fourth copies in raster order)
    fourth = {}
    got_chunk = [None if c is None or c[0] == "BAD" else c[0]
                 for c in pg.content]
    if not mis:
        fourth = {i: s for s, (i, k) in exp.items() if k == 3}
        pg.fourth_from = "design"
    elif pg.side is not None and pg.side.get("slot_chunk") == got_chunk:
        for s, cp in enumerate(pg.side.get("slot_copy", [])):
            if cp == 3 and got_chunk[s] is not None:
                fourth[got_chunk[s]] = s
        pg.fourth_from = "sidecar"
    else:
        prev = -1
        for il in four:
            c = PER_PAGE * F + il
            ss = where[c]
            mine = [k for k in range(3) if groups[k] == F]
            out = [s for s in ss if pg.slots[s][0] // 10 not in mine]
            if len(out) == 1:
                cand = out
            else:
                byband = {}
                for s in ss:
                    byband.setdefault(pg.slots[s][0] // 10, []).append(s)
                dbl = [b for b, v in byband.items() if len(v) == 2]
                if out or len(dbl) != 1:
                    break                              # reported below
                cand = []
                for s in byband[dbl[0]]:
                    rest = sorted((x for x in ss if x != s),
                                  key=lambda x: pg.slots[x][0])
                    if len(rest) < 3 or not guarantee_failures(
                            copy_report([pg.slots[x] for x in rest])):
                        cand.append(s)
            ok = [s for s in cand if s > prev]
            if not ok:
                break
            fourth[c] = prev = min(ok)
        pg.fourth_from = "grid"
    fs = [fourth.get(PER_PAGE * F + il) for il in range(m)]
    if None in fs or fs != sorted(fs) or len(set(fs)) != m:
        bad += 1
        fail("fourth copies are not in block raster order by chunk index "
             f"(slots {fs[:8]}...)")
    elif whites and fs and min(whites) < fs[-1]:
        bad += 1
        fail(f"white slot {min(whites)} {pg.slots[min(whites)]} precedes "
             f"fourth copy slot {fs[-1]} (leftovers in raster order take "
             "fourth copies first)")
    # the placed copies: on this page one in each band of the chunk's group
    pg.placed = {}
    for g in on_page:
        want = [k for k in range(3) if groups[k] == g]
        for il in range(gsize(g, N)):
            i = PER_PAGE * g + il
            ss = [s for s in where.get(i, []) if fourth.get(i) != s]
            bands = sorted(pg.slots[s][0] // 10 for s in ss)
            if bands != want:
                bad += 1
                fail(f"chunk {i}: placed copies in bands {bands} (spec: one "
                     f"in each of bands {want} on page {p})")
                continue
            pg.placed[i] = {pg.slots[s][0] // 10: pg.slots[s] for s in ss}
    pg.where, pg.fourth, pg.bad_place = where, fourth, bad
    pg.n_fourth = len(fourth)
    pg.n_white = len(whites)


def check_overlay(pages, N, P, errs):
    """The guarantees over the overlay of the pages given: every chunk whose
    three placed copies are among them (P >= 3: on three pages)."""
    have = {}
    for pg in pages:
        for c, kb in getattr(pg, "placed", {}).items():
            for k, b in kb.items():
                have.setdefault(c, {})[k] = (pg, b)
    reps, n = [], 0
    for c in sorted(have):
        kb = have[c]
        if sorted(kb) != [0, 1, 2]:
            continue
        n += 1
        on = [kb[k][0].p for k in range(3)]
        if P >= 3 and len(set(on)) != 3:
            errs.append(f"chunk {c}: placed copies on pages {on} (spec: "
                        "three different pages for P >= 3)")
        cp = [kb[k][1] for k in range(3)]
        rep = copy_report(cp)
        reps.append(rep)
        for msg in guarantee_failures(rep):
            errs.append(f"{os.path.basename(kb[0][0].path)}: chunk {c}: "
                        f"copies at blocks {cp} (pages {on}): {msg}")

    def low(key):
        return min(r[key] for r in reps) if reps else None
    return dict(chunks=n, spread=low("spread"), rows=low("rows"),
                strip_mm=round(low("strip") * MODULE_MM, 2) if reps else None,
                blot_mm=round(low("blot") * MODULE_MM, 3) if reps else None,
                off=round(low("off"), 4) if reps else None)


def check_sidecar(pg, a, N, P, errs):
    def fail(msg):
        errs.append(f"{os.path.basename(pg.side_path)}: {msg}")
    sd = pg.side
    first = PER_PAGE * pg.p
    bands = [dict(band=k, copy=k, group=g, chunk_first=PER_PAGE * g,
                  chunk_count=gsize(g, N)) for k, g in enumerate(pg.groups)]
    var = sd.get("variant")
    if (VK["kind"], VK["rings"]) == ("record", "coarse"):
        if var is not None:
            fail(f"variant entry {var.get('kind')}/{var.get('rings')} on a "
                 "record / coarse page")
    elif var is None or (var.get("kind"), var.get("rings")) != \
            (VK["kind"], VK["rings"]):
        fail(f"sidecar variant {var and (var.get('kind'), var.get('rings'))}"
             f" != {(VK['kind'], VK['rings'])}")
    elif sorted(var.get("ink_rings", [])) != sorted(V_INK[VK["kind"]]) or \
            var.get("header_bit_modules") != len(HDR_POS):
        fail("sidecar variant ink_rings / header_bit_modules differ")
    for key, val in (("W", W_SPEC), ("H", H_SPEC), ("BW", BW_SPEC),
                     ("BH", BH_SPEC), ("page", pg.p), ("pages", P),
                     ("page_step", page_step(P)), ("chunk_first", first),
                     ("chunk_count", pg.n), ("band_groups", bands),
                     ("fourth_group", pg.F), ("data_len", pg.length),
                     ("data_crc32", pg.dcrc), ("format", "R2v1")):
        if sd.get(key) != val:
            fail(f"{key} = {sd.get(key)!r}, grid/spec says {val!r}")
    if [tuple(b) for b in sd.get("slot_block", [])] != pg.slots:
        fail("slot_block differs from the block raster order")
    got_chunk = [None if c is None or c[0] == "BAD" else c[0]
                 for c in pg.content]
    if sd.get("slot_chunk") != got_chunk:
        n = sum(1 for x, y in zip(sd.get("slot_chunk", []), got_chunk)
                if x != y)
        fail(f"slot_chunk differs from the grid in {n} slots")
    want_copy = []
    for s, c in enumerate(got_chunk):
        if c is None:
            want_copy.append(None)
        elif pg.fourth.get(c) == s:
            want_copy.append(3)
        else:
            want_copy.append(pg.slots[s][0] // 10)
    if sd.get("slot_copy") != want_copy:
        fail("slot_copy differs from the copies observed on the grid")
    hd = sd.get("header", {})
    if hd.get("bits") != "".join(map(str, pg.hbits)):
        fail("header bits differ from the bullseye blocks")
    if hd.get("length") != pg.length or hd.get("crc32") != pg.dcrc:
        fail("header length/crc32 differ from the bullseye blocks")
    bl = sd.get("bullseyes", [])
    if [tuple(b["block"]) for b in bl] != BULL_RASTER:
        fail("bullseye list differs from the spec's 15 blocks (raster order)")
    md, x0, y0 = sd.get("module_dots"), sd.get("x0_dots"), sd.get("y0_dots")
    for b in bl:
        bi, bj = b["block"]
        if (b["centre_col"], b["centre_row"]) != (17 * bj + 9, 17 * bi + 9):
            fail(f"bullseye {b['block']}: centre module "
                 f"({b['centre_col']}, {b['centre_row']}) != "
                 f"({17 * bj + 9}, {17 * bi + 9})")
        if b["centre_dots_xy"] != [x0 + md * (17 * bj + 9) + md / 2,
                                   y0 + md * (17 * bi + 9) + md / 2]:
            fail(f"bullseye {b['block']}: centre dots wrong")
    pl = sd.get("placement", {})
    spec = dict(PI1=D_PI1, PI2=D_PI2,
                SKIP={str(c): v for c, v in D_SKIP.items()},
                OVERFLOW={str(c): list(v) for c, v in D_OVERFLOW.items()})
    for key, val in spec.items():
        if pl.get(key) != val:
            fail(f"placement {key} differs from the spec's table")
    try:            # replay the design from the sidecar's own tables
        rep = page_map(pg.p, N, P, pl["PI1"], pl["PI2"],
                       {int(c): v for c, v in pl["SKIP"].items()},
                       {int(c): v for c, v in pl["OVERFLOW"].items()})
        want = [None] * len(pg.slots)
        for s, (i, k) in rep.items():
            want[s] = (i, k)
        got = [None if c is None else (c, k)
               for c, k in zip(sd.get("slot_chunk", []),
                               sd.get("slot_copy", []))]
        mis = sum(1 for x, y in zip(want, got) if x != y)
        if mis:
            fail(f"{mis} slots of slot_chunk/slot_copy differ from the design "
                 "replayed from the sidecar's tables")
    except (KeyError, TypeError, IndexError, ValueError) as e:
        fail(f"placement tables unreadable: {e!r}")
    if a.payload_bytes is not None:
        pl = a.payload_bytes
        if sd.get("data_sha256") != hashlib.sha256(pl).hexdigest():
            fail("data_sha256 != the payload's")
    stem = pg.path[:-len(".grid.txt")]
    for ext, h in sd.get("files", {}).items():
        if os.path.exists(stem + ext):
            with open(stem + ext, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() != h:
                    fail(f"files[{ext}] sha256 differs from {stem + ext}")
        else:
            fail(f"files[{ext}]: {stem + ext} missing")


def spec_origin():
    """(module_dots, x0, y0) from the spec: 12-dot modules, the 358 x 511
    grid centred in the usable area 182 x 277 mm at 18 / 10 mm from the left
    / top edge of an A4 page at 600 dpi: round(offset) + (int(usable) -
    grid) // 2 dots, = (12, 426, 441)."""
    dpm = 600 / 25.4
    md = 12
    x0 = round(18.0 * dpm) + (int(182.0 * dpm) - W_SPEC * md) // 2
    y0 = round(10.0 * dpm) + (int(277.0 * dpm) - H_SPEC * md) // 2
    return md, x0, y0


def check_pbm(pg, errs):
    def fail(msg):
        errs.append(f"{os.path.basename(pg.path)} (pbm): {msg}")
    md, x0, y0 = spec_origin()
    if (md, x0, y0) != (12, 426, 441):
        fail(f"spec origin re-derived as {(md, x0, y0)}, the spec states "
             "(12, 426, 441)")
    sd = pg.side
    if sd is not None:
        got = (sd.get("module_dots"), sd.get("x0_dots"), sd.get("y0_dots"))
        if got != (md, x0, y0):
            fail(f"sidecar (module_dots, x0, y0) = {got}, the spec gives "
                 f"{(md, x0, y0)}")
    path = pg.path[:-len(".grid.txt")] + ".pbm"
    with open(path, "rb") as f:
        raw = f.read()
    parts = raw.split(b"\n", 2)
    if parts[0] != b"P4":
        fail("not P4")
        return
    pw, ph = map(int, parts[1].split())
    if (pw, ph) != (4960, 7016):
        fail(f"page {pw}x{ph} dots, A4 at 600 dpi is 4960x7016")
    stride = (pw + 7) // 8
    body = parts[2]
    if len(body) != stride * ph:
        fail(f"body {len(body)} bytes, expected {stride * ph}")
        return
    blank = bytes(stride)               # md, x0, y0: the spec's, above
    bad_rows = 0
    rows = {}
    strs = {}
    for r in range(H_SPEC):
        s = "0" * x0 + "".join(ch * md for ch in map(str, pg.g[r]))
        s = s.ljust(stride * 8, "0")
        strs[r] = s
        rows[r] = int(s, 2).to_bytes(stride, "big")
    dotrows = {}
    if VK["rings"] == "dot":
        ink = V_INK[VK["kind"]]
        pg.dot_changed = 0
        pg.area_agree = []
        pg.centre_agree = []
        pg.bad_centre_rule = 0
        for bi, bj in BULL:
            cx = x0 + md * (17 * bj + 9) + md / 2
            cy = y0 + md * (17 * bi + 9) + md / 2
            for rr in range(16):
                for cc in range(16):
                    if (cc - 8) ** 2 + (rr - 8) ** 2 > 42:
                        continue                # quiet / header: solid
                    gv = pg.g[17 * bi + 1 + rr][17 * bj + 1 + cc]
                    mx = x0 + md * (17 * bj + 1 + cc)
                    my = y0 + md * (17 * bi + 1 + rr)
                    rho_c = math.hypot(mx + md / 2 - cx, my + md / 2 - cy) / md
                    n = int(math.floor(rho_c + 0.5))
                    if int(n in ink and n <= 6) != gv:
                        pg.bad_centre_rule += 1
                    agree = 0
                    cagree = 0
                    for y in range(my, my + md):
                        line = dotrows.get(y)
                        if line is None:
                            line = dotrows[y] = list(strs[(y - y0) // md])
                        for x in range(mx, mx + md):
                            rho = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / md
                            n = int(math.floor(rho + 0.5))
                            v = "1" if (n in ink and n <= 6) else "0"
                            if v != line[x]:
                                pg.dot_changed += 1
                            line[x] = v
                            agree += (v == str(gv))
                            if (y - my) in (md // 2 - 1, md // 2) and \
                                    (x - mx) in (md // 2 - 1, md // 2):
                                cagree += (v == str(gv))
                    pg.area_agree.append(agree / (md * md))
                    pg.centre_agree.append(cagree)
        if pg.bad_centre_rule:
            fail(f"{pg.bad_centre_rule} ring modules whose grid value is not "
                 "the circle rule at the module centre")
        dotrows = {y: int("".join(v), 2).to_bytes(stride, "big")
                   for y, v in dotrows.items()}
    for y in range(ph):
        got = body[y * stride:(y + 1) * stride]
        r = (y - y0) // md
        if y in dotrows:
            want = dotrows[y]
        else:
            want = rows[r] if y0 <= y < y0 + md * H_SPEC else blank
        if got != want:
            bad_rows += 1
    if bad_rows:
        fail(f"{bad_rows} dot rows differ from the grid placed at "
             f"({x0}, {y0}) x {md}"
             f"{' with the dot-rendered rings' if dotrows else ''}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("grids", nargs="+")
    ap.add_argument("--payload")
    ap.add_argument("--pbm", action="store_true")
    ap.add_argument("--no-sidecar", action="store_true")
    ap.add_argument("--bullseye", choices=("record", "v1", "v2", "v3"),
                    default="record")
    ap.add_argument("--rings", choices=("coarse", "dot"), default="coarse")
    a = ap.parse_args(argv)
    set_kind(a.bullseye, a.rings)
    errs = []
    a.payload_bytes = None
    if a.payload:
        with open(a.payload, "rb") as f:
            a.payload_bytes = f.read()
    pages = [check_page(p, a, errs) for p in a.grids]
    pages = [p for p in pages if p is not None]
    if not pages:
        print("\n".join("FAIL: " + e for e in errs) + "\nFAILED")
        return 1
    h0 = pages[0]
    for pg in pages[1:]:
        if pg.hbits != h0.hbits:
            errs.append(f"{os.path.basename(pg.path)}: header differs from "
                        f"{os.path.basename(h0.path)}'s")
    L, C = h0.length, h0.dcrc
    N = -(-L // CHUNK)
    npages = max(1, -(-N // PER_PAGE))
    pl = a.payload_bytes
    if pl is not None:
        if len(pl) != L:
            errs.append(f"header length {L} != payload {len(pl)} B")
        if crc(pl) != C:
            errs.append(f"header CRC 0x{C:08x} != payload CRC "
                        f"0x{crc(pl):08x}")
    seen = set()
    maps = {}
    for pg in pages:
        if pg.side is not None and "page" in pg.side:
            p, how = pg.side["page"], "sidecar"
        else:                              # no sidecar: the page whose rule
            score = []                     # matches the most data slots
            for q in range(npages):
                if q not in maps:
                    maps[q] = page_map(q, N, npages)
                m = maps[q]
                score.append((sum(c is not None and c[0] != "BAD" and
                                  s in m and m[s][0] == c[0]
                                  for s, c in enumerate(pg.content)), -q))
            best, q = max(score)
            p, how = -q, f"best match, {best} of 615 slots"
            if sum(x[0] == best for x in score) > 1:
                errs.append(f"{os.path.basename(pg.path)}: page ambiguous "
                            f"({best} slots match more than one page)")
        if p in seen:
            errs.append(f"{os.path.basename(pg.path)}: page {p} given twice")
        seen.add(p)
        if not 0 <= p < npages:
            errs.append(f"{os.path.basename(pg.path)}: page {p} beyond the "
                        f"payload's {npages} pages")
            continue
        check_placement(pg, p, N, npages, pl, errs)
        if pg.side is not None:
            check_sidecar(pg, a, N, npages, errs)
        if a.pbm:
            check_pbm(pg, errs)
        bands = ", ".join(f"band {k} group {g} ({gsize(g, N)})"
                          for k, g in enumerate(pg.groups))
        print(f"{pg.path}: page {p} of {npages} (d = {page_step(npages)}): "
              f"{bands}, fourth copies {pg.n_fourth} of group {pg.F}; data "
              f"slots ok {615 - pg.bad_crc}/615, white {pg.n_white}; timing "
              f"bad {pg.bad_timing}, ring bad {pg.bad_ring}, placement bad "
              f"{pg.bad_place}; turned header reads passing {len(pg.turned)}"
              f"{', designed placement' if pg.design_ok else ''}"
              f"{', sidecar checked' if pg.side else ', no sidecar'}"
              f"; page from the {how}"
              f"{', pbm checked' if a.pbm else ''}")
        if a.pbm and VK["rings"] == "dot" and hasattr(pg, "area_agree"):
            print(f"  dot rings ({VK['kind']}): {pg.dot_changed} dots differ "
                  f"from module-solid over 15 blocks; ring modules' dots equal "
                  f"to the grid value: min {min(pg.area_agree):.3f}, mean "
                  f"{sum(pg.area_agree) / len(pg.area_agree):.3f}; central "
                  f"2 x 2 dots equal: min {min(pg.centre_agree)} of 4 "
                  f"({sum(1 for c in pg.centre_agree if c < 4)} modules < 4); "
                  f"circle rule at module centres == grid in every ring "
                  f"module: {'yes' if not pg.bad_centre_rule else 'NO'}")
    ov = check_overlay([pg for pg in pages if hasattr(pg, "placed")], N,
                       npages, errs)
    print(f"guarantees over the overlay of the pages given ({ov['chunks']} of "
          f"{N} chunks with all three placed copies among them): spread "
          f"{ov['spread']}, strip {ov['strip_mm']} mm, rows {ov['rows']}, "
          f"blot {ov['blot_mm']} mm, off-line {ov['off']} columns")
    # assemble when the pages given hold every chunk
    per = {}
    for pg in pages:
        for c in pg.content:
            if c is not None and c[0] != "BAD":
                per.setdefault(c[0], set()).add(c[1])
    split = [i for i, v in per.items() if len(v) != 1]
    if split:
        errs.append(f"copies disagree for chunks {split[:10]}")
    missing = [i for i in range(N) if i not in per]
    if not missing:
        data = b"".join(min(per[i]) for i in range(N))[:L]
        if crc(data) != C:
            errs.append("assembled data CRC-32 != header")
        if pl is not None and data != pl:
            errs.append("assembled data != --payload")
        print(f"assembled {N} chunks from page(s) {sorted(seen)} of "
              f"{npages}: {L} B, crc 0x{crc(data):08x} "
              f"{'== header' if crc(data) == C else '!= header'}")
    elif seen == set(range(npages)):
        errs.append(f"chunks never present: {missing[:10]}")
    else:
        print(f"pages given {sorted(seen)} of {npages}: {len(missing)} chunks "
              "absent, no assembly")
    print(f"header: length {L}, crc 0x{C:08x}, identical in "
          f"{15 * len(pages)} bullseye blocks")
    for e in errs:
        print("FAIL:", e)
    print("PASS" if not errs else f"FAILED ({len(errs)} deviations)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())

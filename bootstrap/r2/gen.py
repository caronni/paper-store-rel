#!/usr/bin/env python3
"""R2 page generator, R2-FORMAT v1 (bootstrap/R2-FORMAT.md, 2026-10-20;
amended 2026-10-20 night: the copies of a chunk across pages).

payload bytes -> R2 pages.  Each page is written as a 600-dpi A4 bitmap
(PBM P4 and PNG, ink = 1), the module grid as text (H lines of W '0'/'1',
the loupe path's input) and a JSON sidecar.  Generator side only: numpy/PIL
allowed here, never in typed code.

The page, per the spec:
  - grid W x H = 358 x 511 modules (BW 21 x BH 30 blocks of 16 x 16), 12 dots
    per module, centred in the A4 usable area (182 x 277 mm at 18 / 10 mm
    from the left / top edge: 10 mm margins, 18 mm gutter; the bound edge
    is the LEFT edge of every page): grid origin x0 = 426, y0 = 441 dots
    (round(18 mm) + (int(182 mm) - 358 x 12) // 2 and the same in y, at 600
    dpi; exact centring would give 426.8 / 441.9, the spec fixes 426 /
    441); nothing is inked outside the grid: the leaf's overt header
    (volume, rung, leaf n of m) is drawn by the leaf composer, outside this
    bitmap;
  - timing lattice: rows/columns r % 17 == 0, c % 17 == 0, value (r + c) % 2;
  - 15 bullseye blocks at (bi, bj) in {2,14,26} x {2,8,14} and
    {8,20} x {5,11,17}; ring rule by q = dx^2 + dy^2 (dx = c - 8, dy = r - 8
    block-local): q <= 42 ink iff round(sqrt q) even, 43..56 white, q >= 57
    one of the 79 header modules, which carry the 68 header bits in block
    raster order MSB first, the last 11 white;
  - header = length (2 B BE) + CRC-32 of the data (4 B BE) + 20-bit check =
    CRC-32 of those 6 bytes mod 2^20; identical in every bullseye block of
    every page;
  - the 615 other blocks are data slots: 2-byte GLOBAL chunk index + 26 data
    bytes + CRC-32 over the six header bytes (length BE16, data CRC-32 BE32:
    the bytes whose 20-bit check is in the bullseye blocks) followed by the
    block's bytes 0-27, stored BE32 in bytes 28-31; so a block validates
    only against its own payload's header and frames of two payloads cannot
    mix; bits row-major MSB first; empty slots white;
  - groups: chunk j is page-local index i = j mod 204 of group g = j // 204;
    P = ceil(N / 204) pages.  Every chunk has three placed copies, copy k in
    row band k (block rows 0-9, 10-19, 20-29).  The PAGE of copy k of group
    g is (g + k d) mod P, d = max(1, (P + 1) // 3) (= round(P / 3) for
    P = 2 .. 13; amendment of 2026-10-20 night): band k of page q holds
    the copies k of group (q - k d) mod P.  For P >= 3 the three copies of a
    chunk are on three different pages (P = 3: g, g+1, g+2; P = 7: g, g+2,
    g+4; P = 13: g, g+4, g+8); P = 2: copies 0 and 2 on page g, copy 1 on
    the other; P = 1: the one page as before, byte-identical.  The SLOT of
    copy k of index i in its band is the DESIGNED PLACEMENT (2026-10-20,
    second amendment; it replaced the column thirds, then the seeded
    shuffle + repair), the same for every group and page:
      copy 0 of page-local chunk i at band-0 data slot i (block raster
      order), block (r0, c); copy 1 in band 1, column PI1[c]; copy 2 in
      band 2, column PI2[c]; each at the free (non-bullseye) row of the same
      RANK in its column as r0 has in band 0's column c.  Bands 0 and 2 have
      9 free rows in columns 2, 5, 8, 11, 14, 17, band 1 in 2, 8, 14, every
      other column 10; PI1 maps no 10-row column onto a 9-row one, so band
      1 fits rank for rank (its 3 unreached slots stay leftovers); in band
      2 four columns CROSS: columns 12 and 20 (10 rows) map onto 9-row
      columns and drop band-0 rank SKIP[c] (12: rank 9 = row 9, 20: rank 0 =
      row 0), the dropped chunk's copy 2 going to OVERFLOW[c] (12: block
      (29, 19); 20: block (29, 0)); columns 5 and 14 (9 rows) map onto
      10-row columns and leave target rank SKIP[c] = 9 (row 29) unreached:
      exactly those two OVERFLOW blocks;
      PI1 = 11 13 15 16 20 10 12  1 14 17 18 19  0  6  8  9  3  2  4  7  5
      PI2 =  6  7  8  9 15  0  1 16  2  3  4  5 17 18 19 20 10 11 12 13 14
    GUARANTEES of the slot geometry, for damage at the same place on every
    sheet (the overlay of all pages is the single-page design; a short
    group uses a subset of a full group's triangles): one placed copy per
    band; block columns pairwise
    >= 5 apart; the narrowest straight strip, any angle, touching all three
    copies' 16 x 16 interiors >= 91 modules = 46.2 mm (exact minimum 46.30
    mm, design_placement.py, the optimum of this family); r2 - r0 >= 19
    block rows; the smallest disc touching all three >= 79.9 mm radius
    (exact 79.92); no straight line through two copies within 7.36 block
    columns of the third at its row (exact minimum 140/19 = 7.368).  Of
    the pages: for P >= 3 a lost sheet costs each chunk at most one placed
    copy; any one page may be lost for P >= 2, any two for P >= 3; for
    P >= 3 the fatal three-page losses are exactly {g, g+d, g+2d} mod P
    (placement_stats.py --page-loss, every subset);
  - leftover slots of page q, pooled page-wide in block raster order, carry
    fourth copies of group f(q) = (q + s) mod P, s the smallest s >= 1 not
    congruent to -d or -2d mod P (a group with no copy on page q: its
    fourth copy lands on a fourth page; such s exists for P >= 4), else
    (P <= 3) group q, the group whose copy 0 is on page q: its indices 0,
    1, 2, ... (one each, index order, as many as fit; exempt from the
    guarantees); the rest are white.  For P = 1 that is the single-page
    rule (chunks 0, 1, 2, ... of the page).
  - Slot s = the s-th non-bullseye block in block raster order (bi, then bj).

Refused payloads (nothing is written; message on stderr; exit status):
  3  ORIENTATION: the header (68 bits) also passes its 20-bit check when read
     from a bullseye block of the page turned 90, 180 or 270 degrees, for
     either block parity (bi + bj even / odd: the timing lines a turned read
     samples alternate with it; a 180 / 270 degree read takes the length
     field from a timing line, 0x5555 / 0xAAAA).  About 6 payloads in 2^20.
     CONTRACT with build.py: on status 3, append a newline to the bundle,
     compress again and call gen.py again (repeat until accepted);
  4  EMPTY: length 0 (the spec prints no page without data);
  5  TOO LONG: more than 65,535 bytes (the 2-byte length field).
  In-process callers get gen.PayloadRefused (.code = that status) from
  header_of / build_grid / write_page; turned_reads_passing(bits) lists the
  (turn, parity) pairs that pass.

Usage:
  gen.py capacity
  gen.py page  PAYLOAD OUTPREFIX [--page P] [--module-dots 12]
               [--offset O] [--length N]
      writes OUTPREFIX.{pbm,png,grid.txt,json} for page P (default 0)
  gen.py pages PAYLOAD OUTPREFIX [--module-dots 12] [--offset O] [--length N]
      writes OUTPREFIX_p{P}.{pbm,png,grid.txt,json} for every page
--offset/--length slice the payload file before encoding (as in v0).
--module-dots changes only the physical module size (BW/BH, bullseyes and
placement stay the spec's 21 x 30); the spec and the default are 12.
--copies is accepted for v0 callers and must be 3.
Deterministic: a re-run writes byte-identical files.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import zlib

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import placement_stats  # noqa: E402

FORMAT = "R2v1"
SPEC = "bootstrap/R2-FORMAT.md v1 (2026-10-20, amended 2026-10-20 night)"
DPI = 600
MM = DPI / 25.4                      # dots per mm
PAGE_W_DOTS = 4960                   # A4 210 mm at 600 dpi
PAGE_H_DOTS = 7016                   # A4 297 mm at 600 dpi
# Usable area 182 x 277 mm: 10 mm margins, 18 mm gutter on the bound edge.
# ASSUMED (spec question, as v0): the bound edge is the left edge, every page.
USABLE_X0_MM, USABLE_Y0_MM = 18.0, 10.0
USABLE_W_MM, USABLE_H_MM = 182.0, 277.0
MODULE_DOTS = 12
BW, BH = 21, 30
W, H = 17 * BW + 1, 17 * BH + 1      # 358 x 511 modules
BLOCK = 16                           # block side, modules
CHUNK_BYTES = 26
BLOCK_BYTES = 32
CHUNKS_PER_PAGE = 204
COPIES = 3
BAND_ROWS = 10                       # block rows per band
MAX_LENGTH = 0xFFFF                  # the 2-byte length field
BULLSEYES = sorted([(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)]
                   + [(bi, bj) for bi in (8, 20) for bj in (5, 11, 17)])
INK_Q = (0, 4, 5, 13, 16, 17, 18, 20, 32, 34, 36, 37, 40, 41)  # spec table

# ---- the designed placement (tables from design_placement.py) --------------
PI1 = [11, 13, 15, 16, 20, 10, 12, 1, 14, 17, 18, 19, 0, 6, 8, 9, 3, 2, 4, 7,
       5]
PI2 = [6, 7, 8, 9, 15, 0, 1, 16, 2, 3, 4, 5, 17, 18, 19, 20, 10, 11, 12, 13,
       14]
SKIP = {5: 9, 12: 9, 14: 9, 20: 0}
OVERFLOW = {12: (29, 19), 20: (29, 0)}
MIN_COL_SPREAD = 5                   # guarantee, block columns
STRIP_BOUND_MODULES = 91             # guarantee: 91 x 0.508 = 46.2 mm
DESIGN_RECORD = dict(
    rule="copy 0 of page-local chunk i at band-0 data slot i (block raster "
         "order), block (r0, c); copy 1 in band 1, column PI1[c]; copy 2 in "
         "band 2, column PI2[c]; each at the free (non-bullseye) row of the "
         "same rank in its column as r0 has in band 0's column c; in band 2 "
         "a column c crossing from 10 to 9 free rows drops band-0 rank "
         "SKIP[c] (that chunk's copy 2 goes to block OVERFLOW[c]) and a "
         "column crossing from 9 to 10 leaves target rank SKIP[c] unreached "
         "(the ranks after a skipped one move up by one); fourth copies: "
         "the slots left empty, pooled page-wide in block raster order, "
         "receive chunks 0, 1, 2, ... (one each, as many as fit) of the "
         "page's fourth-copy group; the rest are white",
    pages="chunk j = index i = j mod 204 of group g = j // 204; copy k of "
          "group g on page (g + k d) mod P, d = max(1, (P + 1) // 3); the "
          "fourth copies of page q are group (q + s) mod P, s the smallest "
          "s >= 1 not congruent to -d or -2d mod P, else (P <= 3) group q",
    PI1=PI1, PI2=PI2, SKIP={str(c): v for c, v in SKIP.items()},
    OVERFLOW={str(c): list(v) for c, v in OVERFLOW.items()},
    guarantees=dict(one_placed_copy_per_band=True,
                    min_column_spread=MIN_COL_SPREAD,
                    min_strip_modules=STRIP_BOUND_MODULES,
                    min_strip_mm=round(STRIP_BOUND_MODULES * 0.508, 3),
                    full_page_exact_min_strip_mm=46.30,
                    min_rows_copy0_to_copy2=19, min_blot_radius_mm=79.9,
                    min_offline_columns=7.36,
                    full_page_exact_min_offline_columns="140/19"),
    source="bootstrap/r2/design_placement.py (max-min strip, MILP)")


# ---- the bullseye block ----------------------------------------------------
def ring_class(r, c):
    """Block-local module (r, c), 0..15 -> 'ink' | 'white' | 'header'."""
    dx, dy = c - 8, r - 8
    q = dx * dx + dy * dy
    if q >= 57:
        return "header"
    if q >= 43:
        return "white"                       # ring 7, the quiet ring
    d = math.isqrt(q)
    if q - d * d > d:                        # q > d^2 + d  <=>  sqrt q > d + 1/2
        d += 1
    return "ink" if d % 2 == 0 else "white"


RING = [[ring_class(r, c) for c in range(BLOCK)] for r in range(BLOCK)]
HEADER_MODULES = [(r, c) for r in range(BLOCK) for c in range(BLOCK)
                  if RING[r][c] == "header"]
assert len(HEADER_MODULES) == 79
assert sorted({(r - 8) ** 2 + (c - 8) ** 2 for r in range(BLOCK)
               for c in range(BLOCK) if RING[r][c] == "ink"}) == list(INK_Q)


def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF


class PayloadRefused(Exception):
    """A payload the spec does not print; .code is gen.py's exit status."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


EXIT_ORIENTATION, EXIT_EMPTY, EXIT_TOO_LONG = 3, 4, 5
TURNS = {1: "90 degrees clockwise", 2: "180 degrees",
         3: "270 degrees clockwise"}


def _turn(m, dy, dx):
    """Page offset under an image offset (dy, dx) when the page is turned m
    quarter turns clockwise in the image."""
    for _ in range(m):
        dy, dx = -dx, dy
    return dy, dx


def _module_near_bullseye(hbits79, par, dy, dx):
    """The page module at offset (dy, dx), each -8..8, from the centre of a
    bullseye block (bi, bj) with par = (bi + bj) % 2: inside the block its
    ring or header module, +8 the timing line below / right of the block,
    value (row + column) % 2 = (par + dy + dx) % 2 (17 is odd)."""
    if dy == 8 or dx == 8:
        return (par + dy + dx) % 2
    kind = RING[dy + 8][dx + 8]
    if kind == "header":
        return hbits79[HEADER_MODULES.index((dy + 8, dx + 8))]
    return 1 if kind == "ink" else 0


def turned_reads_passing(hbits79):
    """The (turn, parity) pairs whose wrong-orientation header read passes
    the 20-bit check: a reader assuming the page upright samples the 68
    header positions of a bullseye block of the page turned m = 1, 2, 3
    quarter turns, for both block parities (the timing lines around the
    block alternate with (bi + bj) % 2)."""
    hits = []
    for m in (1, 2, 3):
        for par in (0, 1):
            b = [_module_near_bullseye(hbits79, par, *_turn(m, r - 8, c - 8))
                 for r, c in HEADER_MODULES[:68]]
            six = int("".join(map(str, b[:48])), 2).to_bytes(6, "big")
            if crc32(six) % (1 << 20) == int("".join(map(str, b[48:])), 2):
                hits.append((m, par))
    return hits


def header_of(data):
    """-> (6 header bytes, 20-bit check, 79 module bits), or PayloadRefused:
    length 0 (EXIT_EMPTY), > 65,535 B (EXIT_TOO_LONG), or a header that also
    passes its check read in a wrong orientation (EXIT_ORIENTATION)."""
    if len(data) == 0:
        raise PayloadRefused(EXIT_EMPTY, "REFUSED: empty payload (length "
                             "0); the spec prints no page without data")
    if len(data) > MAX_LENGTH:
        raise PayloadRefused(EXIT_TOO_LONG, f"REFUSED: payload {len(data)} B "
                             f"> {MAX_LENGTH} B (2-byte length field)")
    six = len(data).to_bytes(2, "big") + crc32(data).to_bytes(4, "big")
    check = crc32(six) % (1 << 20)
    bits = [int(b) for b in format(int.from_bytes(six, "big"), "048b")]
    bits += [int(b) for b in format(check, "020b")]
    assert len(bits) == 68
    bits += [0] * (len(HEADER_MODULES) - 68)
    hits = turned_reads_passing(bits)
    if hits:
        where = "; ".join(f"turned {TURNS[m]} at a bullseye block with "
                          f"bi + bj {'even' if p == 0 else 'odd'}"
                          for m, p in hits)
        raise PayloadRefused(EXIT_ORIENTATION, (
            f"REFUSED: the header of this payload (length {len(data)}, "
            f"CRC-32 0x{crc32(data):08x}) also passes its 20-bit check when "
            f"read {where}; a reader could take the page for turned.  Change "
            "the payload and retry (build.py appends a newline to the bundle "
            "before compression)."))
    return six, check, bits


# ---- geometry and placement ------------------------------------------------
def geometry(module_dots=MODULE_DOTS, copies=COPIES):
    if copies != COPIES:
        raise SystemExit("R2-FORMAT v1 is three copies (plus fourth copies "
                         "in the leftover slots); --copies must be 3")
    uw = int(USABLE_W_MM * MM)
    uh = int(USABLE_H_MM * MM)
    if W * module_dots > uw or H * module_dots > uh:
        raise SystemExit(f"grid {W}x{H} @ {module_dots} dots exceeds the "
                         f"usable area {uw}x{uh} dots")
    x0 = round(USABLE_X0_MM * MM) + (uw - W * module_dots) // 2
    y0 = round(USABLE_Y0_MM * MM) + (uh - H * module_dots) // 2
    s = BW * BH - len(BULLSEYES)
    return dict(module_dots=module_dots, copies=COPIES, BW=BW, BH=BH, W=W,
                H=H, S=s, x0_dots=x0, y0_dots=y0, page_w_dots=PAGE_W_DOTS,
                page_h_dots=PAGE_H_DOTS, dpi=DPI,
                capacity_chunks=CHUNKS_PER_PAGE,
                capacity_bytes=CHUNKS_PER_PAGE * CHUNK_BYTES,
                band_slots=[len(band_slots(k)) for k in range(3)])


def slot_blocks():
    """Data slot s -> (bi, bj): block raster order, bullseyes skipped."""
    be = set(BULLSEYES)
    return [(bi, bj) for bi in range(BH) for bj in range(BW)
            if (bi, bj) not in be]


def band_of(bi):
    return bi // BAND_ROWS


def band_slots(k):
    return [s for s, (bi, bj) in enumerate(slot_blocks()) if band_of(bi) == k]


def n_chunks(length):
    return -(-length // CHUNK_BYTES)


def n_pages(length):
    return max(1, -(-n_chunks(length) // CHUNKS_PER_PAGE))


def free_rows(k, col):
    """Band k's free (non-bullseye) block rows in column col, top down."""
    be = set(BULLSEYES)
    return [r for r in range(BAND_ROWS * k, BAND_ROWS * k + BAND_ROWS)
            if (r, col) not in be]


def band2_rank(c, k):
    """Band-2 target rank of band-0 rank k of column c, or None (overflow)."""
    n0, n2 = len(free_rows(0, c)), len(free_rows(2, PI2[c]))
    if n0 == n2:
        return k
    if n0 > n2:                                   # crossing 10 -> 9 rows
        if k == SKIP[c]:
            return None
        return k - (k > SKIP[c])
    return k + (k >= SKIP[c])                     # crossing 9 -> 10 rows


def placement(n):
    """n chunks on ONE page (0..204) -> (slot_local, slot_copy): the
    designed placement of a single-page payload (module docstring; for
    P = 1 page_placement gives exactly this).  slot_local[s] = page-local chunk
    or None (white); slot_copy[s] = 0, 1, 2 (the placed copy of that band),
    3 (a fourth copy) or None."""
    assert 0 <= n <= CHUNKS_PER_PAGE
    sb = slot_blocks()
    where = {b: s for s, b in enumerate(sb)}
    band0 = [s for s, (bi, _) in enumerate(sb) if band_of(bi) == 0]
    slot_local = [None] * len(sb)
    slot_copy = [None] * len(sb)
    for i in range(n):
        r0, c = sb[band0[i]]
        k = free_rows(0, c).index(r0)
        r1 = free_rows(1, PI1[c])[k]
        m = band2_rank(c, k)
        b2 = OVERFLOW[c] if m is None else (free_rows(2, PI2[c])[m], PI2[c])
        for copy, blk in enumerate(((r0, c), (r1, PI1[c]), b2)):
            s = where[blk]
            if slot_local[s] is not None:
                raise AssertionError(f"slot {blk} taken twice")
            slot_local[s], slot_copy[s] = i, copy
    left = [s for s in range(len(sb)) if slot_local[s] is None]
    for s, i in zip(left, range(n)):
        slot_local[s], slot_copy[s] = i, 3
    return slot_local, slot_copy


def page_step(pages):
    """d: copy k of group g goes to page (g + k d) mod P (three distinct
    pages for P >= 3, asserted)."""
    d = max(1, (pages + 1) // 3)
    assert pages < 3 or len({0, d % pages, 2 * d % pages}) == 3, pages
    return d


def copy_page(g, k, pages):
    """The page of copy k (0, 1, 2) of group g."""
    return (g + k * page_step(pages)) % pages


def band_group(q, k, pages):
    """The group whose copies k fill band k of page q."""
    return (q - k * page_step(pages)) % pages


def fourth_group(q, pages):
    """The group whose fourth copies fill page q's leftover slots: (q + s)
    mod P, s the smallest s >= 1 with s not congruent to -d or -2d mod P
    (that group has no placed copy on page q); for P <= 3 there is none and
    it is group q (copy 0 on page q)."""
    d = page_step(pages)
    held = {0, -d % pages, -2 * d % pages}
    for s in range(1, pages):
        if s not in held:
            return (q + s) % pages
    return q


def group_size(g, N):
    """Chunks of group g of a payload of N chunks."""
    return max(0, min(CHUNKS_PER_PAGE, N - CHUNKS_PER_PAGE * g))


_DESIGN_SLOTS = []


def design_slots():
    """(page-local index i, copy k) -> data slot: the designed placement of
    a full group (placement(204)); a shorter group uses the same slots."""
    if not _DESIGN_SLOTS:
        sl, sc = placement(CHUNKS_PER_PAGE)
        _DESIGN_SLOTS.append({(i, k): s for s, (i, k) in enumerate(zip(sl, sc))
                              if k in (0, 1, 2)})
    return _DESIGN_SLOTS[0]


def page_placement(q, N):
    """Page q of a payload of N chunks -> (slot_chunk, slot_copy):
    slot_chunk[s] = global chunk index or None (white), slot_copy[s] = 0, 1,
    2 (the placed copy of that band), 3 (a fourth copy) or None.  Band k
    holds copies k of group band_group(q, k), each at the designed slot of
    its page-local index; the leftover slots, in block raster order, the
    fourth copies of group fourth_group(q), indices 0, 1, 2, ..."""
    pages = max(1, -(-N // CHUNKS_PER_PAGE))
    assert 0 <= q < pages
    ds = design_slots()
    slot_chunk = [None] * (BW * BH - len(BULLSEYES))
    slot_copy = [None] * len(slot_chunk)
    for k in range(COPIES):
        g = band_group(q, k, pages)
        for i in range(group_size(g, N)):
            s = ds[i, k]
            if slot_chunk[s] is not None:
                raise AssertionError(f"slot {s} taken twice")
            slot_chunk[s], slot_copy[s] = CHUNKS_PER_PAGE * g + i, k
    f = fourth_group(q, pages)
    left = [s for s in range(len(slot_chunk)) if slot_chunk[s] is None]
    for s, i in zip(left, range(group_size(f, N))):
        slot_chunk[s], slot_copy[s] = CHUNKS_PER_PAGE * f + i, 3
    return slot_chunk, slot_copy


def block_bytes(index, chunk26, six):
    """32 block bytes: index (BE16), the chunk, and CRC-32 over the six
    header bytes (length BE16, data CRC-32 BE32) followed by bytes 0-27, so
    a block validates only against its own payload's header."""
    body = index.to_bytes(2, "big") + chunk26
    return body + crc32(six + body).to_bytes(4, "big")


def chunk(data, i):
    return data[CHUNK_BYTES * i:CHUNK_BYTES * (i + 1)].ljust(CHUNK_BYTES,
                                                             b"\0")


def build_grid(data, p):
    """-> (grid uint8 H x W, record dict) for page p of data."""
    N = n_chunks(len(data))
    pages = n_pages(len(data))
    if not 0 <= p < pages:
        raise SystemExit(f"page {p} out of range: payload {len(data)} B is "
                         f"{pages} page(s)")
    first = CHUNKS_PER_PAGE * p
    n = group_size(p, N)
    six, check, hbits = header_of(data)
    grid = np.zeros((H, W), dtype=np.uint8)
    rr, cc = np.mgrid[0:H, 0:W]
    timing = (rr % 17 == 0) | (cc % 17 == 0)
    grid[timing] = ((rr + cc) % 2)[timing]
    ring = np.array([[1 if v == "ink" else 0 for v in row] for row in RING],
                    dtype=np.uint8)
    for (r, c), b in zip(HEADER_MODULES, hbits):
        ring[r, c] = b
    for bi, bj in BULLSEYES:
        grid[17 * bi + 1:17 * bi + 17, 17 * bj + 1:17 * bj + 17] = ring
    slot_chunk, slot_copy = page_placement(p, N)
    sb = slot_blocks()
    for s, (bi, bj) in enumerate(sb):
        g = slot_chunk[s]
        if g is None:
            continue                                   # white slot
        bits = np.unpackbits(np.frombuffer(block_bytes(g, chunk(data, g),
                                                       six), dtype=np.uint8))
        grid[17 * bi + 1:17 * bi + 17, 17 * bj + 1:17 * bj + 17] = \
            bits.reshape(BLOCK, BLOCK)
    bands = []
    for k in range(COPIES):
        g = band_group(p, k, pages)
        bands.append(dict(band=k, copy=k, group=g,
                          chunk_first=CHUNKS_PER_PAGE * g,
                          chunk_count=group_size(g, N)))
    f = fourth_group(p, pages)
    rec = dict(page=p, pages=pages, page_step=page_step(pages),
               chunk_first=first, chunk_count=n,
               chunk_first_count_are="group p, the group whose copy 0 is on "
                                     "this page (band 0)",
               band_groups=bands, fourth_group=f,
               chunks_on_page=len({c for c in slot_chunk if c is not None}),
               slot_block=[list(b) for b in sb], slot_chunk=slot_chunk,
               slot_copy=slot_copy,
               fourth_copies=sum(1 for c in slot_copy if c == 3),
               white_slots=sum(1 for c in slot_chunk if c is None),
               placement=dict(DESIGN_RECORD),
               header=dict(bytes_hex=six.hex(), length=len(data),
                           crc32=crc32(data), check20=check,
                           bits="".join(map(str, hbits[:68])),
                           white_tail_modules=len(HEADER_MODULES) - 68,
                           modules_block_local_rc=[list(m) for m in
                                                   HEADER_MODULES]))
    return grid, rec


_OVERLAY = {}


def overlay_stats(N, module_dots=MODULE_DOTS):
    """placement_stats over the OVERLAY of all P pages of a payload of N
    chunks (every page's slots, each chunk's three placed copies and its
    fourth at their block positions): the guarantees for damage at the same
    place on every sheet.  For P = 1, the page's own stats."""
    key = (N, module_dots)
    if key not in _OVERLAY:
        pages = max(1, -(-N // CHUNKS_PER_PAGE))
        sb = [list(b) for b in slot_blocks()]
        ov = dict(module_dots=module_dots, slot_block=[], slot_chunk=[],
                  slot_copy=[])
        for q in range(pages):
            sc, sk = page_placement(q, N)
            ov["slot_block"] += sb
            ov["slot_chunk"] += sc
            ov["slot_copy"] += sk
        _OVERLAY[key] = dict(placement_stats.stats(ov),
                             over="the overlay of all %d page(s)" % pages)
    return dict(_OVERLAY[key])


def bullseye_record(g):
    md, x0, y0 = g["module_dots"], g["x0_dots"], g["y0_dots"]
    out = []
    for k, (bi, bj) in enumerate(BULLSEYES):
        c, r = 17 * bj + 9, 17 * bi + 9
        out.append(dict(index=k, block=[bi, bj], centre_col=c, centre_row=r,
                        centre_dots_xy=[x0 + md * c + md / 2,
                                        y0 + md * r + md / 2]))
    return out


# ---- output ----------------------------------------------------------------
def render(grid, g):
    md = g["module_dots"]
    page = np.zeros((g["page_h_dots"], g["page_w_dots"]), dtype=np.uint8)
    big = np.kron(grid, np.ones((md, md), dtype=np.uint8))
    y0, x0 = g["y0_dots"], g["x0_dots"]
    page[y0:y0 + big.shape[0], x0:x0 + big.shape[1]] = big
    return page


def write_pbm(path, page):
    h, w = page.shape
    with open(path, "wb") as f:
        f.write(b"P4\n%d %d\n" % (w, h))
        f.write(np.packbits(page, axis=1).tobytes())


def write_png(path, page):
    Image.fromarray(((1 - page) * 255).astype(np.uint8)).convert("1").save(
        path, dpi=(DPI, DPI))


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_page(data, p, out, module_dots=MODULE_DOTS):
    g = geometry(module_dots)
    grid, rec = build_grid(data, p)
    page = render(grid, g)
    with open(out + ".grid.txt", "w", newline="\n") as f:
        for row in grid:
            f.write("".join("01"[v] for v in row) + "\n")
    write_pbm(out + ".pbm", page)
    write_png(out + ".png", page)
    side = dict(format=FORMAT, spec=SPEC, **g, ink=1,
                data_len=len(data), data_crc32=crc32(data),
                data_sha256=hashlib.sha256(data).hexdigest(),
                data_chunks=n_chunks(len(data)),
                bullseyes=bullseye_record(g), **rec)
    side["placement"]["stats"] = overlay_stats(n_chunks(len(data)),
                                                g["module_dots"])
    side["files"] = {ext: sha256_file(out + ext)
                     for ext in (".grid.txt", ".pbm", ".png")}
    with open(out + ".json", "w") as f:
        json.dump(side, f, indent=1)
    st = side["placement"]["stats"]
    bands = "; ".join(
        f"band {b['band']}: group {b['group']} "
        f"({b['chunk_first']}..{b['chunk_first'] + b['chunk_count'] - 1})"
        for b in rec["band_groups"])
    print(f"{out}: page {p + 1} of {rec['pages']} (d = {rec['page_step']}),"
          f" {bands}; fourth copies {rec['fourth_copies']} of group "
          f"{rec['fourth_group']}, white slots {rec['white_slots']}; data "
          f"{len(data)} B crc 0x{crc32(data):08x}")
    if st.get("chunks"):
        print(f"  placement (designed, overlay of all pages): strip min {st['min_strip_mm']} / p5 "
              f"{st['p5_strip_mm']} / median {st['median_strip_mm']} mm; "
              f"min column spread {st['min_column_spread']}; min r2 - r0 "
              f"{st['min_vertical_0_2']}; min blot {st['min_blot_mm']} mm")
    for ext, h in side["files"].items():
        print(f"  {ext:10s} {h}")
    return side


def read_payload(a):
    with open(a.payload, "rb") as f:
        data = f.read()[a.offset:]
    if a.length is not None:
        data = data[:a.length]
    return data


def cmd_capacity(_a):
    g = geometry()
    print(f"grid {g['W']}x{g['H']} modules ({g['BW']}x{g['BH']} blocks) at "
          f"{g['module_dots']} dots = {g['W'] * g['module_dots'] / MM:.1f} x "
          f"{g['H'] * g['module_dots'] / MM:.1f} mm, origin "
          f"({g['x0_dots']}, {g['y0_dots']}) dots")
    print(f"blocks {BW * BH}: bullseyes {len(BULLSEYES)}, data slots "
          f"{g['S']}; band slots {g['band_slots']}")
    print(f"chunks/page {g['capacity_chunks']} x {COPIES} copies; "
          f"bytes/page {g['capacity_bytes']}; fourth copies on a full page "
          f"{g['S'] - COPIES * g['capacity_chunks']}")
    print(f"max payload {MAX_LENGTH} B = {n_chunks(MAX_LENGTH)} chunks = "
          f"{n_pages(MAX_LENGTH)} pages")


def cmd_page(a):
    data = read_payload(a)
    write_page(data, a.page, a.outprefix, a.module_dots)
    if n_pages(len(data)) > 1:
        print(f"note: the payload spans {n_pages(len(data))} pages; "
              "use 'pages' or --page P for the others")


def cmd_pages(a):
    data = read_payload(a)
    for p in range(n_pages(len(data))):
        write_page(data, p, f"{a.outprefix}_p{p}", a.module_dots)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("capacity").set_defaults(fn=cmd_capacity)
    for name, fn in (("page", cmd_page), ("pages", cmd_pages)):
        q = sp.add_parser(name)
        q.add_argument("payload")
        q.add_argument("outprefix")
        if name == "page":
            q.add_argument("--page", type=int, default=0)
        q.add_argument("--module-dots", type=int, default=MODULE_DOTS)
        q.add_argument("--copies", type=int, default=COPIES, choices=(3,))
        q.add_argument("--offset", type=int, default=0)
        q.add_argument("--length", type=int)
        q.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except PayloadRefused as e:
        print(f"gen.py: {e}", file=sys.stderr)
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())

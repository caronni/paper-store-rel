#!/usr/bin/env python3
"""Tests for the R2-FORMAT v1 generator, verifier and camera (plain script).

  env/bin/python bootstrap/r2/test_gen_v1.py

Work goes to bootstrap/build/w1/test/ (gitignored; R2_TEST_OUT=DIR moves
it).  Checks:
  capacity     204 chunks / 5,304 B / 615 data slots / bands 204+207+204,
               13 pages at 65,535 B, 65,536 B refused
  design       the designed placement for every page size n = 0 .. 204:
               slots distinct, copy k in band k, block columns pairwise
               >= 5 apart, the narrowest straight strip touching all three
               copies >= gen.STRIP_BOUND_MODULES (91 modules = 46.2 mm,
               exact), the middle copy >= 3 columns off the line through
               the other two and no straight line through two copies within
               3 columns of the third (all three pairs, exact rational
               arithmetic), fourth copies in raster order by index; every
               page's placed copies a subset of the full page's
  identity     P = 1 (the amendment of 2026-10-20 night): the 1 B, 4,747 B
               and 5,304 B pages byte-identical (grid and page bitmap) to
               the generator before it (sha256 recorded from that
               generator), and the design table placement(204) too
  pages        every P = 1 .. 13 (the shortest and the fullest payload of
               P pages, and 65,535 B): every chunk's copy k in band k at
               the designed slot of its page-local index, on page
               (g + k d) mod P, d = max(1, (P + 1) // 3); the three pages
               distinct for P >= 3; every slot used once; the fourth
               copies of page q = group (q + s) mod P (s the smallest s >= 1
               not = -d, -2d mod P; P <= 3: group q), indices 0, 1, ... in
               block raster order, white after them, and for P >= 4 on a
               fourth page
  page loss    placement_stats.page_loss, every subset of lost pages: any
               one page losable for P >= 2, any two for P >= 3, the minimal
               fatal sets exactly {g, g+d, g+2d} mod P (placed copies), no
               minimal fatal set under 3 pages with fourth copies counted,
               at most one placed copy of a chunk per sheet for P >= 3
  constraint   the same checks read back from the generated grids of whole
               payloads (block positions decoded from the grid; the sidecar
               only says which copy of a chunk is the fourth): one copy per
               band, the pages, the guarantees over the overlay
  bullseye     85 ink / 92 white / 79 header modules per block, on the rule
               and on every generated bullseye block; the 68 header bits
               against an independent encoding, the 11-module white tail
  refusals     gen.py refuses an empty payload (exit 4) and the refuter's
               forged payload build/refute-format/payload_orient_180.bin
               (header passes upright and turned 180 degrees at odd-parity
               bullseyes; exit 3, page and pages, nothing written); the
               orientation model names (180, odd); verify_grid, reading the
               turned header from the bypassed grid itself, flags exactly
               the six odd-parity bullseyes
  verify       verify_grid.py PASS (with --payload --pbm) on: the 4,747 B
               page, a full 5,304 B page, the 9,000 B pair, a 5,305 B pair
               (one chunk on page 2), a 1-byte page, the last page of a
               65,535 B payload
  determinism  gen twice -> byte-identical files; camera twice ->
               byte-identical PGM and truth
  multi-page   the 9,000 B pair (P = 2, d = 1): page 0 bands 0 and 2 group
               0, band 1 group 1; page 1 the reverse; either page alone
               holds every chunk; the header identical in all 30 bullseye
               blocks
  negatives    verify_grid FAILS on a flipped data bit, timing module, ring
               module, header bit (one block / all blocks), an in-band swap
               that breaks the guarantees, a swap across bands, an in-band
               swap that keeps every guarantee but is not the design (caught
               by the design replay alone, with or without the sidecar), a
               blanked slot, a block in a white slot, a tampered sidecar, a
               flipped PBM dot, a wrong payload, a block from another
               payload's page (block CRC bound to the header), a sidecar
               x0 off by one (--pbm re-derives the origin from the spec)
  camera       v0 regression (the 10-19 nominal-b030 render, if present), a
               replay of build/r2's recorded captures from their truth
               sidecars (where the page is unchanged), rot90 = exact quarter turns of the frame with the homography
               composed, the truth genie at 0 module errors through crop +
               rot90 and a crop-T cut, damage block records
Exit status 0 iff every check passes.
"""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import zlib
from fractions import Fraction

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.environ.get("R2_TEST_OUT") or os.path.join(ROOT, "build", "w1",
                                                     "test")
PY = sys.executable
GEN = os.path.join(HERE, "gen.py")
VER = os.path.join(HERE, "verify_grid.py")
CAM = os.path.join(HERE, "camera.py")
sys.path.insert(0, HERE)
import gen  # noqa: E402
import genie  # noqa: E402
import placement_stats as ps  # noqa: E402

RESULTS = []


def first_fail(out):
    ls = [ln for ln in out.split("\n") if ln.startswith("FAIL")]
    return ls[0][:150] if ls else out.strip().split("\n")[-1][:150]


def check(name, ok, detail=""):
    detail = str(detail).replace("\n", " | ")
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  -- ' + detail if detail else ''}")


def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_grid(prefix):
    with open(prefix + ".grid.txt") as f:
        return [[int(ch) for ch in ln.strip()] for ln in f]


def six_of(data):
    """The six header bytes of a payload: length BE16 + CRC-32 BE32."""
    return len(data).to_bytes(2, "big") + \
        (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "big")


def decode_blocks(g, six):
    """Independent decode: {(bi, bj): None (white) | (index, 26 B, crc ok)};
    a block's CRC-32 runs over the payload's six header bytes + bytes 0-27."""
    out = {}
    for bi in range(30):
        for bj in range(21):
            bits = [g[17 * bi + 1 + r][17 * bj + 1 + c]
                    for r in range(16) for c in range(16)]
            if not any(bits):
                out[(bi, bj)] = None
                continue
            b = bytes(int("".join(map(str, bits[8 * k:8 * k + 8])), 2)
                      for k in range(32))
            out[(bi, bj)] = (int.from_bytes(b[:2], "big"), b[2:28],
                             zlib.crc32(six + b[:28])
                             == int.from_bytes(b[28:], "big"))
    return out


BULL = sorted([(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)]
              + [(bi, bj) for bi in (8, 20) for bj in (5, 11, 17)])
SLOTS = [(bi, bj) for bi in range(30) for bj in range(21)
         if (bi, bj) not in set(BULL)]


def line_gap(pts):
    """pts = [(r, c)] of copies 0, 1, 2.  -> (column spread, (b) holds, the
    smallest horizontal distance, exact, of a copy from the straight line
    through the other two, at its row)."""
    (r0, c0), (r1, c1), (r2, c2) = pts
    spread = min(abs(c0 - c1), abs(c0 - c2), abs(c1 - c2))
    b = abs((c1 - c0) * (r2 - r0) - (c2 - c0) * (r1 - r0)) >= 3 * (r2 - r0)
    gap = None
    for t in range(3):
        (ra, ca), (rb, cb) = [pts[x] for x in range(3) if x != t]
        rt, ct = pts[t]
        x_line = ca + Fraction(cb - ca, 1) * Fraction(rt - ra, rb - ra)
        d = abs(ct - x_line)
        gap = d if gap is None else min(gap, d)
    return spread, b, gap


def placement_check(slot_chunk, slot_copy, n, first=0):
    """Rule checks on a slot map -> list of problems (empty = ok), stats."""
    probs = []
    placed, fourth = {}, {}
    for s, (c, k) in enumerate(zip(slot_chunk, slot_copy)):
        if c is None:
            continue
        if k == 3:
            fourth[c - first] = s
        else:
            if SLOTS[s][0] // 10 != k:
                probs.append(f"chunk {c} copy {k} in band {SLOTS[s][0] // 10}")
            placed.setdefault(c - first, {})[k] = s
    spreads, gaps, strips = [], [], []
    for i in range(n):
        if sorted(placed.get(i, {})) != [0, 1, 2]:
            probs.append(f"chunk {first + i}: copies {placed.get(i)}")
            continue
        pts = [SLOTS[placed[i][k]] for k in range(3)]
        sp, b, gap = line_gap(pts)
        strip = ps.strip_exact([ps.centre(r, c) for r, c in pts])
        spreads.append(sp)
        gaps.append(gap)
        strips.append(strip)
        if sp < 5 or not b or gap < 3 or strip < gen.STRIP_BOUND_MODULES:
            probs.append(f"chunk {first + i} at {pts}: spread {sp}, (b) {b}, "
                         f"gap {float(gap):.2f}, strip {strip:.1f} modules")
    fs = [fourth.get(i) for i in range(len(fourth))]
    if None in fs or fs != sorted(fs):
        probs.append("fourth copies not chunks 0.. in raster order")
    whites = [s for s, c in enumerate(slot_chunk) if c is None]
    if whites and (len(fourth) != n or (fs and min(whites) < fs[-1])):
        probs.append("white slot before a fourth copy")
    return probs, dict(min_spread=min(spreads) if spreads else None,
                       min_gap=float(min(gaps)) if gaps else None,
                       min_strip_mm=round(min(strips) * 0.508, 2)
                       if strips else None)


def gen_pages(payload_path, prefix):
    rc, out = run([PY, GEN, "pages", payload_path, prefix])
    assert rc == 0, out
    n = gen.n_pages(os.path.getsize(payload_path))
    return [f"{prefix}_p{p}" for p in range(n)]


def verify(prefixes, payload=None, extra=()):
    argv = [PY, VER] + [p + ".grid.txt" for p in prefixes] + list(extra)
    if payload:
        argv += ["--payload", payload]
    return run(argv)


# ---------------------------------------------------------------------------
def t_capacity():
    g = gen.geometry()
    check("capacity: 204 chunks/page", g["capacity_chunks"] == 204,
          str(g["capacity_chunks"]))
    check("capacity: 5,304 B/page", g["capacity_bytes"] == 5304,
          str(g["capacity_bytes"]))
    check("capacity: 615 data slots", g["S"] == 615 and
          len(gen.slot_blocks()) == 615, str(g["S"]))
    check("capacity: band slots 204+207+204",
          g["band_slots"] == [204, 207, 204], str(g["band_slots"]))
    check("capacity: 15 bullseyes, none at a page corner",
          len(gen.BULLSEYES) == 15 and not {(0, 0), (0, 20), (29, 0),
                                            (29, 20)} & set(gen.BULLSEYES))
    check("capacity: 65,535 B = 13 pages", gen.n_pages(65535) == 13)
    rc, out = run([PY, GEN, "capacity"])
    check("capacity CLI", rc == 0 and "bytes/page 5304" in out
          and "data slots 615" in out and "[204, 207, 204]" in out
          and "13 pages" in out, out.strip().replace("\n", " | "))
    big = os.path.join(OUT, "p65536.bin")
    open(big, "wb").write(bytes(65536))
    rc, out = run([PY, GEN, "page", big, os.path.join(OUT, "refused")])
    check("65,536 B payload refused", rc != 0 and "2-byte length" in out,
          out.strip()[-80:])


def t_design_all_n():
    full_l, full_c = gen.placement(204)
    full = {(i, k): s for s, (i, k) in enumerate(zip(full_l, full_c))
            if k in (0, 1, 2)}
    probs, worst_sp, worst_gap, worst_strip = [], 99, 99.0, 1e9
    for n in range(0, 205):
        try:
            sl, sc = gen.placement(n)
        except AssertionError as e:
            probs.append(f"n={n}: {e}")
            continue
        p, st = placement_check(sl, sc, n)
        probs += [f"n={n}: {x}" for x in p]
        sub = {(i, k): s for s, (i, k) in enumerate(zip(sl, sc))
               if k in (0, 1, 2)}
        if any(full[key] != s for key, s in sub.items()):
            probs.append(f"n={n}: placed copies differ from the full page's")
        if st["min_spread"] is not None:
            worst_sp = min(worst_sp, st["min_spread"])
            worst_gap = min(worst_gap, st["min_gap"])
            worst_strip = min(worst_strip, st["min_strip_mm"])
    check("design: valid for every n = 0 .. 204 (one copy per band, spread "
          f">= 5, strip >= {gen.STRIP_BOUND_MODULES} modules, no line "
          "through two copies within 3 columns of the third), each page's "
          "placed copies a subset of the full page's", not probs,
          probs[0] if probs else
          f"min column spread {worst_sp}, min line gap {worst_gap}, min "
          f"strip {worst_strip} mm")


def d_of(P):
    """d, typed from the amendment: max(1, (P + 1) // 3)."""
    return max(1, (P + 1) // 3)


def f_of(q, P):
    """The fourth-copy group of page q, typed from the amendment."""
    d = d_of(P)
    for s in range(1, P):
        if s % P not in (0, (-d) % P, (-2 * d) % P):
            return (q + s) % P
    return q


def pages_check(P, N, pages):
    """pages = [(slot_chunk, slot_copy)] of every page of a payload of N
    chunks -> problems (empty = ok): each chunk's copy k in band k at the
    design slot of its index, on page (g + k d) mod P, pages distinct for
    P >= 3, each slot used once, the fourth-copy rule."""
    probs = []
    d = d_of(P)
    full_l, full_c = gen.placement(204)
    design = {(i, k): s for s, (i, k) in enumerate(zip(full_l, full_c))
              if k in (0, 1, 2)}
    placed, fourth = {}, {}
    for q, (sc, sk) in enumerate(pages):
        if len(sc) != 615:
            probs.append(f"page {q}: {len(sc)} slots")
        fq = []
        for s, (c, k) in enumerate(zip(sc, sk)):
            if c is None:
                continue
            if k == 3:
                if c in fourth:
                    probs.append(f"chunk {c}: two fourth copies")
                fourth[c] = (q, s)
                fq.append((s, c))
                continue
            if SLOTS[s][0] // 10 != k:
                probs.append(f"chunk {c} copy {k} in band {SLOTS[s][0] // 10}")
            if placed.setdefault(c, {}).get(k) is not None:
                probs.append(f"chunk {c} copy {k} twice")
            placed[c][k] = (q, s)
        f = f_of(q, P)
        ns = len([c for c in sc if c is None]) + len(fq)
        m = min(ns, max(0, min(204, N - 204 * f)))
        if [c for _, c in sorted(fq)] != [204 * f + i for i in range(m)]:
            probs.append(f"page {q}: fourth copies not group {f}'s 0.."
                         f"{m - 1} in raster order")
        whites = [s for s in range(615) if sc[s] is None]
        if whites and fq and min(whites) < max(fq)[0]:
            probs.append(f"page {q}: a white slot before a fourth copy")
    if sorted(placed) != list(range(N)):
        probs.append("not every chunk placed")
    for c, cp in placed.items():
        g, i = divmod(c, 204)
        if sorted(cp) != [0, 1, 2]:
            probs.append(f"chunk {c}: copies {sorted(cp)}")
            continue
        for k in range(3):
            q, s = cp[k]
            if q != (g + k * d) % P or s != design[i, k]:
                probs.append(f"chunk {c} copy {k} at page {q} slot {s}, rule "
                             f"page {(g + k * d) % P} slot {design[i, k]}")
        on = {cp[k][0] for k in range(3)}
        if P >= 3 and len(on) != 3:
            probs.append(f"chunk {c}: placed copies on pages {sorted(on)}")
        if P >= 4 and c in fourth and fourth[c][0] in on:
            probs.append(f"chunk {c}: fourth copy on a page with a placed "
                         "copy")
    return probs


def t_identity_p1():
    """P = 1: byte-identical to the generator before the amendment of
    2026-10-20 night (sha256 recorded from that generator, bootstrap/r2/
    gen.py at 3450f87f, in-process: grid bytes and the 4960 x 7016 page)."""
    sl, sc = gen.placement(204)
    check("identity: placement(204), the design table, unchanged",
          hashlib.sha256(json.dumps([sl, sc]).encode()).hexdigest()
          == "0b8e4d9ae712d383e0dabe67a413e6ab67cb536d01e812be0331ae3ef3ea7984")
    want = {1: ("9377622710d999ad283ab5812c142eb7fe025e2361aff59bacf2dbb934761e02",
                "50096089540bc6d6d11c5d14fe4a1b060c3436c816f510c0097786e87aab5e02"),
            4747: ("3befbf9c82dfae909c73c53597163451a8f745abb7dfe9f70d26dabe08ae85c3",
                   "6eba0481edabab80188b3fae0a76ec99bba7b1d2a3584d3f83d3bc0e56651d83"),
            5304: ("65c356c3b2ac76df3312ccfc839ea0464be0266e1133091abc3921276e6fa9f4",
                   "f6f8ce3a2c7005ee4e3e9bba2179eafe240efbb29aa0fb739a17186af49482d1")}
    for n, (wg, wp) in want.items():
        g, _ = gen.build_grid(random.Random(n).randbytes(n), 0)
        page = gen.render(g, gen.geometry())
        check(f"identity: P = 1, the {n:,} B page byte-identical to the "
              "generator before the amendment (grid and page bitmap)",
              hashlib.sha256(g.tobytes()).hexdigest() == wg
              and hashlib.sha256(page.tobytes()).hexdigest() == wp)
    for n in range(0, 205):
        sl, sc = gen.placement(n)
        pc, pk = gen.page_placement(0, n)
        if [None if c is None else c for c in sl] != pc or sc != pk:
            check("identity: page_placement(0, n) == placement(n)", False,
                  f"n = {n}")
            return
    check("identity: page_placement(0, n) == placement(n) for n = 0 .. 204",
          True)


def t_pages_every_P():
    probs, rows = [], []
    for P in range(1, 14):
        d = d_of(P)
        if d != gen.page_step(P) or (P > 1 and d != round(P / 3)):
            probs.append(f"P {P}: d {gen.page_step(P)}")
        cp = [(0 + k * d) % P for k in range(3)]
        if P >= 3 and len(set(cp)) != 3:
            probs.append(f"P {P}: pages {cp} not distinct")
        for N in sorted({204 * (P - 1) + 1, min(204 * P, 2521)}):
            pages = []
            for q in range(P):
                try:
                    pages.append(gen.page_placement(q, N))
                except AssertionError as e:
                    probs.append(f"P {P} N {N} page {q}: {e}")
                    pages.append(([None] * 615, [None] * 615))
            probs += [f"P {P} N {N}: {x}" for x in pages_check(P, N, pages)]
            if P >= 4:
                for q in range(P):
                    if gen.fourth_group(q, P) in {(q - k * d) % P
                                                  for k in range(3)}:
                        probs.append(f"P {P}: page {q}'s fourth group has a "
                                     "placed copy there")
        rows.append(f"{P}:{d}:{'/'.join(map(str, cp))}")
    check("pages: every P = 1 .. 13 (shortest, fullest, 65,535 B): copy k "
          "in band k at the designed slot, on page (g + k d) mod P, d = "
          "max(1, (P + 1) // 3) = round(P / 3), three pages for P >= 3, "
          "every slot once, the fourth-copy rule", not probs,
          probs[0] if probs else "P:d:pages of group 0 " + " ".join(rows))


def t_page_loss():
    probs, rows = [], []
    for r in ps.page_loss_table():
        P, d, a, b = r["P"], r["d"], r["placed"], r["with_fourth"]
        tag = f"P {P} N {r['N']}"
        if r["n_problems"]:
            probs.append(f"{tag}: overlay {r['problems']}")
        if P == 1 and a["minimal_fatal"] != [[0]]:
            probs.append(f"{tag}: minimal {a['minimal_fatal']}")
        if P == 2 and (a["minimal_fatal"] != [[0, 1]]
                       or b["minimal_fatal"] != [[0, 1]]):
            probs.append(f"{tag}: minimal {a['minimal_fatal']}")
        if P >= 3:
            want = sorted({tuple(sorted({g % P, (g + d) % P,
                                         (g + 2 * d) % P}))
                           for g in range(P)})
            if sorted(map(tuple, a["minimal_fatal"])) != want:
                probs.append(f"{tag}: minimal {a['minimal_fatal']} != {want}")
            if a["fatal_by_size"][1] or a["fatal_by_size"][2] \
                    or b["fatal_by_size"][1] or b["fatal_by_size"][2]:
                probs.append(f"{tag}: a fatal set under three pages")
            if r["max_placed_copies_on_one_sheet"] != 1:
                probs.append(f"{tag}: two placed copies on one sheet")
        rows.append(f"{P}:{a['fatal_by_size'][3]}")
    check("page loss (exact, every subset): one page losable for P >= 2, "
          "two for P >= 3, minimal fatal sets {g, g+d, g+2d} mod P, one "
          "placed copy per sheet, the overlay the design", not probs,
          probs[0] if probs else "P:fatal 3-sets " + " ".join(rows))


def t_constraints(sets):
    for name, prefixes in sets:
        allp, pages, side0 = [], [], None
        for pre in prefixes:
            sd = json.load(open(pre + ".json"))
            side0 = side0 or sd
            blocks = decode_blocks(read_grid(pre),
                                   bytes.fromhex(sd["header"]["bytes_hex"]))
            got = [None if blocks[tuple(b)] is None else blocks[tuple(b)][0]
                   for b in sd["slot_block"]]
            if got != sd["slot_chunk"]:
                allp.append(f"{pre}: grid and sidecar slot_chunk differ")
                continue
            pages.append((sd["page"], got, sd["slot_copy"]))
        P = side0["pages"]
        N = gen.n_chunks(side0["data_len"])
        if [q for q, _, _ in pages] != list(range(P)):
            allp.append("not every page")
        else:
            allp += pages_check(P, N, [(g, k) for _, g, k in pages])
        # the guarantees over the overlay, from the grid's block positions
        where = {}
        for q, got, cp in pages:
            for s, (c, k) in enumerate(zip(got, cp)):
                if c is not None and k in (0, 1, 2):
                    where.setdefault(c, {})[k] = s
        sp_, gp_, st_ = 99, None, 1e9
        for c, kk in where.items():
            if sorted(kk) != [0, 1, 2]:
                continue
            pts = [SLOTS[kk[k]] for k in range(3)]
            sp, b, gap = line_gap(pts)
            strip = ps.strip_exact([ps.centre(r, cc) for r, cc in pts])
            sp_, st_ = min(sp_, sp), min(st_, strip)
            gp_ = gap if gp_ is None else min(gp_, gap)
            if sp < 5 or not b or gap < 3 or strip < gen.STRIP_BOUND_MODULES:
                allp.append(f"chunk {c} at {pts}: spread {sp}, gap "
                            f"{float(gap):.2f}, strip {strip:.1f} modules")
        check(f"constraint on the grids: {name} (P = {P})", not allp,
              allp[0] if allp else
              f"overlay: spread >= {sp_}, gap >= {float(gp_):.3f}, strip >= "
              f"{round(st_ * 0.508, 2)} mm")


FORGED = os.path.join(ROOT, "build", "refute-format",
                      "payload_orient_180.bin")


def t_refusals(payload0):
    pre = os.path.join(OUT, "refused_empty")
    rc, out = run([PY, GEN, "page", payload0, pre])
    check("refusal: empty payload (length 0) -> exit 4, nothing written",
          rc == gen.EXIT_EMPTY and "empty payload" in out
          and not os.path.exists(pre + ".pbm"), out.strip()[-90:])
    try:
        gen.header_of(b"")
        ok = False
    except gen.PayloadRefused as e:
        ok = e.code == gen.EXIT_EMPTY
    check("refusal: in-process gen.PayloadRefused(code 4) for b''", ok)
    if not os.path.exists(FORGED):
        check("refusal: forged payload (skipped: build/refute-format "
              "absent)", True)
        return
    for cmd in ("page", "pages"):
        pre = os.path.join(OUT, f"refused_forged_{cmd}")
        rc, out = run([PY, GEN, cmd, FORGED, pre])
        check(f"refusal: the refuter's forged payload (passes upright and "
              f"turned 180 degrees) -> gen.py {cmd} exit 3, nothing written",
              rc == gen.EXIT_ORIENTATION and "180 degrees" in out
              and "odd" in out and not any(os.path.exists(pre + x) for x in
                                           (".pbm", "_p0.pbm")),
              out.strip().replace("gen.py: ", "")[:170])
    data = open(FORGED, "rb").read()
    gen.turned_reads_passing, model = (lambda b: []), gen.turned_reads_passing
    try:
        grid, _ = gen.build_grid(data, 0)          # the refusal bypassed
        bits = gen.header_of(data)[2]
    finally:
        gen.turned_reads_passing = model
    check("orientation model: the forged header passes turned 180 degrees "
          "at odd parity only", model(bits) == [(2, 1)], str(model(bits)))
    pre = os.path.join(OUT, "forged_bypassed")
    with open(pre + ".grid.txt", "w", newline="\n") as f:
        for row in grid:
            f.write("".join("01"[v] for v in row) + "\n")
    rc, out = verify([pre], None, ["--no-sidecar"])
    hit = [ln for ln in out.split("\n") if "orientation" in ln
           and ln.startswith("FAIL")]
    check("verify_grid: the forged header, read turned from the grid itself, "
          "FAILS at the six odd-parity bullseyes (180 degrees)",
          rc == 1 and hit and "[180]" in hit[0]
          and "(8, 5), (8, 11), (8, 17), (20, 5), (20, 11), (20, 17)"
          in hit[0], hit[0][:170] if hit else first_fail(out))


def t_bullseye(prefix, payload):
    kinds = [v for row in gen.RING for v in row]
    check("bullseye rule: 85 ink / 92 white / 79 header",
          (kinds.count("ink"), kinds.count("white"), kinds.count("header"))
          == (85, 92, 79))
    g = read_grid(prefix)
    hdr = set(gen.HEADER_MODULES)
    bad = 0
    heads = []
    for bi, bj in BULL:
        blk = [g[17 * bi + 1 + r][17 * bj + 1:17 * bj + 17] for r in range(16)]
        ink = sum(blk[r][c] for r in range(16) for c in range(16)
                  if (r, c) not in hdr)
        white = sum(1 - blk[r][c] for r in range(16) for c in range(16)
                    if (r, c) not in hdr)
        bad += (ink, white, len(hdr)) != (85, 92, 79)
        heads.append([blk[r][c] for r, c in gen.HEADER_MODULES])
    check("bullseye blocks on the page: 85 ink / 92 white / 79 header each",
          bad == 0, f"{bad} blocks off")
    hm = gen.HEADER_MODULES
    check("header modules: row 0 then column 0/corners, last 11 in row 15",
          hm[:16] == [(0, c) for c in range(16)]
          and all(r == 15 for r, _ in hm[-11:]), str(hm[-11:]))
    data = open(payload, "rb").read()
    six = len(data).to_bytes(2, "big") + \
        (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "big")
    chk = (zlib.crc32(six) & 0xFFFFFFFF) & 0xFFFFF
    want = [int(b) for b in format(int.from_bytes(six, "big"), "048b")
            + format(chk, "020b")] + [0] * 11
    check("header: length + CRC-32 + 20-bit check, 11 white, all 15 equal",
          all(h == want for h in heads))


def t_verify_sets(sets):
    for name, prefixes, payload in sets:
        rc, out = verify(prefixes, payload, ["--pbm"])
        tail = [ln for ln in out.split("\n") if ln.startswith(("assembled",
                                                               "FAIL"))]
        check(f"verify_grid PASS: {name}", rc == 0 and out.strip()
              .endswith("PASS"), "; ".join(tail)[:200])


def t_determinism(payload, payload9):
    a, b = os.path.join(OUT, "det1"), os.path.join(OUT, "det2")
    for d in (a, b):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        run([PY, GEN, "page", payload, os.path.join(d, "one")])
        gen_pages(payload9, os.path.join(d, "two"))
    files = sorted(os.listdir(a))
    same = files == sorted(os.listdir(b)) and all(
        open(os.path.join(a, f), "rb").read()
        == open(os.path.join(b, f), "rb").read() for f in files)
    check(f"determinism: gen twice, {len(files)} files byte-identical", same)
    outs = []
    for d in (a, b):
        pgm = os.path.join(d, "cap.pgm")
        rc, out = run([PY, CAM, os.path.join(d, "one.pbm"), pgm, "--sidecar",
                       os.path.join(d, "one.json"), "--frame", "br",
                       "--spm", "3", "--blur", "0.4", "--rot90", "3",
                       "--damage", "torn:3", "--damage", "be:14",
                       "--seed", "7"])
        tr = json.load(open(os.path.join(d, "cap.json")))
        for k in ("out", "page", "page_sidecar"):
            tr.pop(k)
        outs.append((open(pgm, "rb").read(), json.dumps(tr, sort_keys=True)))
    check("determinism: camera twice (frame + rot90 + damage) identical",
          outs[0] == outs[1])


def t_multipage(prefixes, payload9):
    data = open(payload9, "rb").read()
    idx, heads = [], []
    for p in prefixes:
        g = read_grid(p)
        blocks = decode_blocks(g, six_of(data))
        idx.append(sorted({v[0] for k, v in blocks.items()
                           if v is not None and k not in BULL and v[2]}))
        for bi, bj in BULL:
            heads.append([g[17 * bi + 1 + r][17 * bj + 1 + c]
                          for r, c in gen.HEADER_MODULES])
    check("multi-page: either page of the 9,000 B pair holds every chunk "
          "(347; P = 2: copies 0 and 2 on the home page, copy 1 on the other)",
          idx[0] == list(range(347)) and idx[1] == list(range(347)),
          f"{len(idx[0])} / {len(idx[1])}")
    check("multi-page: header identical in all 30 bullseye blocks",
          all(h == heads[0] for h in heads) and len(heads) == 30)
    s = [json.load(open(p + ".json")) for p in prefixes]
    check("multi-page: sidecars agree (pages 2, d 1, home group 0/1 of "
          "204/143, band groups [0, 1, 0] / [1, 0, 1], fourth group 0/1)",
          [(x["page"], x["pages"], x["page_step"], x["chunk_first"],
            x["chunk_count"], [b["group"] for b in x["band_groups"]],
            x["fourth_group"]) for x in s]
          == [(0, 2, 1, 0, 204, [0, 1, 0], 0),
              (1, 2, 1, 204, 143, [1, 0, 1], 1)])
    per = {}
    for p in prefixes:
        for v in decode_blocks(read_grid(p), six_of(data)).values():
            if v is not None and v[2]:
                per[v[0]] = v[1]
    got = b"".join(per[i] for i in range(347))[:len(data)]
    check("multi-page: chunks of both pages assemble to the payload",
          got == data)


def mutate(src_prefix, dst_prefix, fn, fix_sidecar=True):
    for ext in (".grid.txt", ".json", ".pbm", ".png"):
        shutil.copyfile(src_prefix + ext, dst_prefix + ext)
    g = read_grid(dst_prefix)
    side = json.load(open(dst_prefix + ".json"))
    fn(g, side)
    with open(dst_prefix + ".grid.txt", "w", newline="\n") as f:
        for row in g:
            f.write("".join(map(str, row)) + "\n")
    if fix_sidecar:
        side["files"][".grid.txt"] = sha(dst_prefix + ".grid.txt")
    with open(dst_prefix + ".json", "w") as f:
        json.dump(side, f, indent=1)


def block_get(g, b):
    bi, bj = b
    return [g[17 * bi + 1 + r][17 * bj + 1:17 * bj + 17] for r in range(16)]


def block_put(g, b, rows):
    bi, bj = b
    for r in range(16):
        g[17 * bi + 1 + r][17 * bj + 1:17 * bj + 17] = rows[r]


def in_band_pairs(side):
    """First band-0 pair of placed copies whose swap keeps both chunks
    within the rule, and the first whose swap breaks it."""
    sc, cp = side["slot_chunk"], side["slot_copy"]
    place = {}
    for s, (c, k) in enumerate(zip(sc, cp)):
        if k in (0, 1, 2):
            place.setdefault(c, {})[k] = s

    def ok_with(c, k, s):
        pos = dict(place[c])
        pos[k] = s
        pts = [SLOTS[pos[q]] for q in range(3)]
        sp, b, gap = line_gap(pts)
        return sp >= 5 and ps.strip_exact([ps.centre(r, cc) for r, cc in pts
                                           ]) >= gen.STRIP_BOUND_MODULES
    has4 = {sc[s] for s in range(615) if cp[s] == 3}
    band0 = [s for s in range(615) if cp[s] == 0 and sc[s] not in has4]
    keep = brk = None              # chunks without a fourth copy: no other
    for x in band0:
        for y in band0:
            if y <= x:
                continue
            both = ok_with(sc[x], 0, y) and ok_with(sc[y], 0, x)
            if both and keep is None:
                keep = (x, y)
            if not both and brk is None:
                brk = (x, y)
        if keep and brk:
            break
    cross = (band0[0], next(s for s in range(615) if cp[s] == 1
                            and sc[s] != sc[band0[0]]))
    return keep, brk, cross


def t_negatives(one, two_p1, payload):
    neg = os.path.join(OUT, "neg")
    shutil.rmtree(neg, ignore_errors=True)
    os.makedirs(neg)
    side = json.load(open(one + ".json"))
    sb = [tuple(b) for b in side["slot_block"]]
    keep, brk, cross = in_band_pairs(side)
    has4 = {side["slot_chunk"][s] for s in range(615)
            if side["slot_copy"][s] == 3}
    placed0 = next(s for s in range(615) if side["slot_copy"][s] == 0
                   and side["slot_chunk"][s] not in has4)

    def flip(r, c):
        def f(g, _s):
            g[r][c] ^= 1
        return f

    def swap(x, y, fix_map=False):
        def f(g, s):
            a, b = block_get(g, sb[x]), block_get(g, sb[y])
            block_put(g, sb[x], b)
            block_put(g, sb[y], a)
            if fix_map:
                s["slot_chunk"][x], s["slot_chunk"][y] = \
                    s["slot_chunk"][y], s["slot_chunk"][x]
        return f

    def flip_header(all_blocks):
        def f(g, _s):
            r, c = gen.HEADER_MODULES[5]
            for bi, bj in (BULL if all_blocks else BULL[:1]):
                g[17 * bi + 1 + r][17 * bj + 1 + c] ^= 1
        return f

    cases = [
        ("flipped data bit", flip(17 * 0 + 1 + 3, 17 * 0 + 1 + 5),
         ["fail CRC-32"], False),
        ("flipped timing module", flip(17 * 5, 40), ["timing lattice"],
         False),
        ("flipped ring module", flip(17 * 2 + 1 + 8, 17 * 2 + 1 + 8),
         ["bullseye rings"], False),
        ("header bit flipped in one bullseye",
         flip_header(False), ["headers differ"], False),
        ("header bit flipped in all bullseyes", flip_header(True),
         ["header check"], False),
        ("in-band swap breaking the guarantees", swap(*brk),
         ["(guarantee:"], False),
        ("swap across bands", swap(*cross), ["one in each of bands"], False),
        ("in-band swap keeping the guarantees (not the design)",
         swap(*keep, fix_map=True), ["differ from the designed placement"],
         False),
        ("blanked data slot", lambda g, s: block_put(
            g, sb[placed0], [[0] * 16 for _ in range(16)]),
         ["wrong number of copies"], False),
        ("sidecar data_crc32 tampered",
         lambda g, s: s.__setitem__("data_crc32", s["data_crc32"] ^ 1),
         ["data_crc32"], True),
    ]
    for name, fn, needles, use_side in cases:
        pre = os.path.join(neg, name.replace(" ", "_").replace("(", "")
                           .replace(")", ""))
        mutate(one, pre, fn)
        extra = [] if use_side else ["--no-sidecar"]
        rc, out = verify([pre], payload, extra)
        hit = [n for n in needles if n in out]
        lines = [ln for ln in out.split("\n")
                 if ln.startswith("FAIL") and any(n in ln for n in needles)]
        check(f"negative: {name} -> FAIL", rc == 1 and hit,
              lines[0][:150] if lines else first_fail(out))
        if name.startswith("in-band swap keeping"):
            gl = [ln for ln in out.split("\n")
                  if ln.startswith("FAIL") and "(guarantee:" in ln]
            check("negative control: that swap breaks no guarantee (only the "
                  "design replay catches it)", not gl,
                  gl[0][:150] if gl else "no guarantee FAIL lines")
    # a valid block written into a white slot of page 2 of the 5,305 B pair
    s2 = json.load(open(two_p1 + ".json"))
    sb2 = [tuple(b) for b in s2["slot_block"]]
    w = next(s for s in range(615) if s2["slot_chunk"][s] is None)
    full = next(s for s in range(615) if s2["slot_chunk"][s] is not None)
    pre = os.path.join(neg, "block_in_white_slot")
    mutate(two_p1, pre, lambda g, s: block_put(g, sb2[w], block_get(
        g, sb2[full])))
    rc, out = verify([pre], os.path.join(OUT, "p5305.bin"), ["--no-sidecar"])
    check("negative: block in a white slot -> FAIL",
          rc == 1 and "wrong number of copies" in out, first_fail(out))
    # PBM dot flipped (grid untouched)
    pre = os.path.join(neg, "pbm_dot")
    mutate(one, pre, lambda g, s: None)
    raw = bytearray(open(pre + ".pbm", "rb").read())
    raw[-620 * 3000] ^= 0x10
    open(pre + ".pbm", "wb").write(raw)
    rc, out = verify([pre], payload, ["--pbm"])
    check("negative: flipped PBM dot -> FAIL", rc == 1 and "(pbm)" in out,
          [ln for ln in out.split("\n") if "(pbm)" in ln][0][:150]
          if "(pbm)" in out else first_fail(out))
    # wrong payload
    bad = os.path.join(neg, "wrong_payload.bin")
    d = bytearray(open(payload, "rb").read())
    d[100] ^= 1
    open(bad, "wb").write(d)
    rc, out = verify([one], bad)
    check("negative: wrong payload -> FAIL", rc == 1 and "payload" in out,
          first_fail(out))
    # a block of another payload's page in the same slot: its CRC runs over
    # the other header, so it does not validate here
    g2 = read_grid(two_p1)
    s_mix = next(s for s in range(615) if s2["slot_chunk"][s] is not None
                 and side["slot_chunk"][s] is not None)
    pre = os.path.join(neg, "block_from_other_payload")
    mutate(one, pre, lambda g, s: block_put(g, sb[s_mix],
                                            block_get(g2, sb[s_mix])))
    rc, out = verify([pre], payload, ["--no-sidecar"])
    check("negative: a block from another payload's page -> FAIL CRC-32 "
          "(frames of two payloads cannot mix)",
          rc == 1 and "fail CRC-32" in out, first_fail(out))
    # sidecar origin off by one dot: --pbm re-derives it from the spec
    pre = os.path.join(neg, "sidecar_origin")
    mutate(one, pre, lambda g, s: s.__setitem__("x0_dots", s["x0_dots"] + 1))
    rc, out = verify([pre], payload, ["--pbm"])
    check("negative: sidecar x0 off by one -> FAIL against the spec origin",
          rc == 1 and "the spec gives (12, 426, 441)" in out,
          [ln for ln in out.split("\n") if "spec gives" in ln][0][:150]
          if "spec gives" in out else first_fail(out))


def t_camera(one):
    cam_dir = os.path.join(OUT, "cam")
    os.makedirs(cam_dir, exist_ok=True)
    v0 = os.path.join(ROOT, "build", "r2", "page_12x3")
    rec0 = v0 + ".nominal-b030.json"
    if os.path.exists(rec0) and os.path.exists(v0 + ".pbm"):
        want = json.load(open(rec0))["out_sha256"]
        pgm = os.path.join(cam_dir, "v0reg.pgm")
        run([PY, CAM, v0 + ".pbm", pgm, "--sidecar", v0 + ".json", "--seed",
             "1", "--preset", "nominal", "--blur", "0.30"])
        check("camera v0 regression: the build's nominal-b030 render "
              "byte-identical", sha(pgm) == want, want[:16])
    else:
        check("camera v0 regression (skipped: no 10-19 build)", True)
    # replay: the build's recorded captures, re-rendered from their truth
    # sidecars, must come out byte-identical (where the page is unchanged)
    r2b = os.path.join(ROOT, "build", "r2")
    names = ("page_p0.nominal-b030", "page_p0.q-tl", "page_p0.rot90-1",
             "page_p1.centre")
    done = 0
    for nm in names:
        tp = os.path.join(r2b, nm + ".json")
        if not os.path.exists(tp):
            continue
        tr = json.load(open(tp))
        page = os.path.join(r2b, tr["page"])        # absolute stays absolute
        if not (os.path.exists(page) and sha(page) == tr["page_sha256"]):
            continue
        argv = [PY, CAM, page, os.path.join(cam_dir, nm + ".pgm"),
                "--preset", tr["preset"], "--seed", str(tr["seed"]),
                "--rot90", str(tr["rot90"])]
        if tr.get("page_sidecar"):
            argv += ["--sidecar", os.path.join(r2b, tr["page_sidecar"])]
        for k in ("spm", "persp", "blur", "illum", "noise", "rotate",
                  "paper", "ink", "background"):
            argv += [f"--{k}", repr(tr["params"][k])]
        if tr["frame"]:
            argv += ["--frame", tr["frame"]]
        elif tr["crop_frac"]:
            argv += ["--crop"] + [repr(x) for x in tr["crop_frac"]]
        for d in tr["damage"] + tr["cuts"]:
            argv += ["--damage", d["kind"]]
        rc, out = run(argv)
        check(f"camera replay: build/r2/{nm} re-rendered byte-identical",
              rc == 0 and sha(os.path.join(cam_dir, nm + ".pgm"))
              == tr["out_sha256"], tr["out_sha256"][:16])
        done += 1
    if not done:
        check("camera replay (skipped: no build/r2 captures with their page)",
              True)
    imgs, hms = [], []
    for k in (0, 1, 2, 3):
        pgm = os.path.join(cam_dir, f"tl_r{k}.pgm")
        rc, out = run([PY, CAM, one + ".pbm", pgm, "--sidecar",
                       one + ".json", "--frame", "tl", "--spm", "3",
                       "--blur", "0.2", "--rot90", str(k), "--seed", "3"])
        assert rc == 0, out
        imgs.append(genie.load_pgm(pgm))
        hms.append(np.array(json.load(open(pgm[:-4] + ".json"))
                            ["homography_page_dots_to_px"]))
        st = genie.read(pgm, one)
        check(f"camera: tl frame rot90 {k}: truth genie 0 module errors, all "
              f"in-frame data blocks CRC ok", st["module_errors"] == 0
              and st["data_crc_ok"] == st["data_in_frame"] > 100,
              f"{st['module_errors']}/{st['modules']}, "
              f"{st['data_crc_ok']}/{st['data_in_frame']}")
    check("camera: rot90 k = k clockwise quarter turns of the frame",
          all(np.array_equal(imgs[k], np.rot90(imgs[0], -k))
              for k in (1, 2, 3)))
    x, y = 1234.5, 2345.5
    pts = []
    for k in range(4):
        v = hms[k] @ [x, y, 1]
        pts.append((v[0] / v[2], v[1] / v[2]))
    h0, w0 = imgs[0].shape
    u, v = pts[0]
    want = [(u, v), (h0 - v, u), (w0 - u, h0 - v), (v, w0 - u)]
    check("camera: rot90 homographies compose (page point -> rotated px)",
          all(abs(a - c) < 1e-6 and abs(b - d) < 1e-6
              for (a, b), (c, d) in zip(pts, want)))
    pgm = os.path.join(cam_dir, "cropT.pgm")
    run([PY, CAM, one + ".pbm", pgm, "--sidecar", one + ".json",
         "--blur", "0.2", "--damage", "crop-T", "--seed", "5"])
    st = genie.read(pgm, one)
    tr = json.load(open(pgm[:-4] + ".json"))
    check("camera: crop-T cut moves the homography (genie 0 errors)",
          st["module_errors"] == 0 and tr["cuts"][0]["offset_px"][1] > 0
          and st["blocks_in_frame"] < 630,
          f"blocks {st['blocks_in_frame']}, offset {tr['cuts'][0]['offset_px']}")
    pgm = os.path.join(cam_dir, "torn.pgm")
    run([PY, CAM, one + ".pbm", pgm, "--sidecar", one + ".json",
         "--blur", "0.2", "--damage", "torn:3", "--damage", "be:0",
         "--seed", "5"])
    tr = json.load(open(pgm[:-4] + ".json"))
    st = genie.read(pgm, one)
    torn = {tuple(b) for b in tr["damage"][0]["blocks_touched"]}
    check("camera: torn:3 touches the BR corner blocks, be:0 bullseye 0",
          (29, 20) in torn and (0, 0) not in torn
          and tr["damage"][1]["blocks_touched"] == [[2, 2]],
          f"{len(torn)} blocks torn")
    check("camera: damage confined to the touched blocks (undamaged all ok)",
          st["undamaged_data_crc_ok"] == st["undamaged_data_in_frame"],
          f"{st['undamaged_data_crc_ok']}/{st['undamaged_data_in_frame']}")


def main():
    os.makedirs(OUT, exist_ok=True)
    p1 = os.path.join(OUT, "p4747.bin")
    open(p1, "wb").write(random.Random(4747).randbytes(4747))
    payloads = {}
    for n in (0, 1, 5304, 5305, 9000, 65535):
        p = os.path.join(OUT, f"p{n}.bin")
        open(p, "wb").write(random.Random(n).randbytes(n))
        payloads[n] = p
    t_capacity()
    t_design_all_n()
    t_identity_p1()
    t_pages_every_P()
    t_page_loss()
    one = os.path.join(OUT, "one")
    rc, out = run([PY, GEN, "page", p1, one])
    check("gen page (4,747 B)", rc == 0, out.split("\n")[0][-90:])
    full = gen_pages(payloads[5304], os.path.join(OUT, "full"))
    two = gen_pages(payloads[9000], os.path.join(OUT, "two"))
    edge = gen_pages(payloads[5305], os.path.join(OUT, "edge"))
    tiny = gen_pages(payloads[1], os.path.join(OUT, "tiny"))
    t_refusals(payloads[0])
    last = os.path.join(OUT, "max_p12")
    rc, out = run([PY, GEN, "page", payloads[65535], last, "--page", "12"])
    check("gen page --page 12 of 65,535 B", rc == 0, out.split("\n")[0][-90:])
    maxp = gen_pages(payloads[65535], os.path.join(OUT, "max"))
    check("gen page --page 12 == pages' page 12 (byte-identical grid)",
          open(last + ".grid.txt").read() == open(maxp[12] + ".grid.txt")
          .read())
    t_bullseye(one, p1)
    sf = json.load(open(full[0] + ".json"))
    check("full page: 204 chunks, 3 fourth copies, 0 white",
          (sf["chunk_count"], sf["fourth_copies"], sf["white_slots"])
          == (204, 3, 0))
    se = [json.load(open(e + ".json")) for e in edge]
    check("5,305 B (P = 2, group 1 = chunk 204 alone): page 1 holds copies "
          "0 and 2 of chunk 204 and its fourth, copy 1 of group 0; page 0 "
          "copies 0 and 2 of group 0, its 204 fourth copies, copy 1 of "
          "chunk 204; white 2 / 408",
          [(x["chunk_first"], x["chunk_count"], x["fourth_group"],
            x["fourth_copies"], x["white_slots"], x["chunks_on_page"])
           for x in se] == [(0, 204, 0, 204, 2, 205),
                            (204, 1, 1, 1, 408, 205)],
          str([(x["fourth_copies"], x["white_slots"]) for x in se]))
    sm = json.load(open(last + ".json"))
    check("65,535 B page 12: chunks 2448..2520 (73)",
          (sm["chunk_first"], sm["chunk_count"], sm["pages"])
          == (2448, 73, 13))
    t_constraints([("4,747 B page", [one]), ("full 5,304 B page", full),
                   ("9,000 B pair", two), ("5,305 B pair", edge),
                   ("1 B page", tiny), ("65,535 B, 13 pages", maxp)])
    t_verify_sets([("4,747 B page", [one], p1),
                   ("full 5,304 B page", full, payloads[5304]),
                   ("9,000 B, both pages", two, payloads[9000]),
                   ("5,305 B, both pages", edge, payloads[5305]),
                   ("1 B page", tiny, payloads[1]),
                   ("65,535 B, page 12 alone", [last], payloads[65535]),
                   ("65,535 B, all 13 pages", maxp, payloads[65535])]
                  + [(f"9,000 B, page {q} alone (closes alone, P = 2)",
                      [two[q]], payloads[9000]) for q in (0, 1)])
    t_determinism(p1, payloads[9000])
    t_multipage(two, payloads[9000])
    t_negatives(one, edge[1], p1)
    t_camera(one)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS)} checks, {len(RESULTS) - len(bad)} passed, "
          f"{len(bad)} failed")
    for r in bad:
        print("FAILED:", r[0], r[2])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

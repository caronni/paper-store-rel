#!/usr/bin/env python3
"""R2 placement statistics (qualification instrument): how far apart the
copies of each chunk sit, from a gen.py page sidecar (slot_block,
slot_chunk, slot_copy; copies 0..2 = the placed copies, 3 = a fourth copy).
Geometry in modules: block (bi, bj) has its 16 x 16-module interior centred
at (17 bj + 9, 17 bi + 9), half-side 8; mm = modules * module_dots / 600 in.

Per page, over every chunk (placed copies unless "_all_copies"):
  strip        the narrowest straight strip, any angle, that touches the
               interior of all three copies = min over directions of
               (spread of the centres' projections - 2 x the square's
               half-extent), EXACT (strip_exact: evaluated at every
               breakpoint of the piecewise-sinusoidal function, troughs
               included); a straight scratch at least this wide can take
               all three; reported as min / 5th percentile (nearest rank) /
               median, mm, and the count under 5 mm (damage.py's scratch)
  blot         the smallest disc (any centre) that touches all three
               interiors: min over p of max_j dist(p, square_j), mm (a blot
               of that radius can take all three); min and 5th percentile
  min_column_spread    min pairwise |c_a - c_b| (block columns)
  min_vertical_0_2     min r2 - r0, copies of bands 0 and 2 (block rows)
  min_offline_columns  min over the three copies of the horizontal distance,
                       at its row, of the line through the other two
  min_altitude_blocks  min perpendicular distance of a copy's centre from
                       the line through the other two (block pitches)

A sidecar may be an OVERLAY of several pages (gen.overlay_stats: the
slot lists of every page concatenated): a chunk's copies are then counted
wherever they sit, which is the geometry damage at the same place on every
sheet meets.

PAGE LOSS (--page-loss; the amendment of 2026-10-20 night, copies across
pages): for a payload of N chunks on P pages (gen.page_placement), every
subset of lost pages (2^P) is enumerated EXACTLY; a subset is fatal when a
chunk has every placed copy (and, in the second count, its fourth copy too)
on lost pages.  Reported per (P, N): d, the minimal fatal subsets, the
number of fatal subsets of size 1, 2, 3, whether the minimal fatal 3-sets
are exactly {g, g+d, g+2d} mod P, whether one of them holds two
physically adjacent pages (q, q+1; and cyclically, P-1 with 0), the most
placed copies of one chunk on one sheet, and the overlay check: every
placed copy k of index i at the designed slot of (i, k).  N per P: the
fullest (204 P), the shortest (204 (P - 1) + 1), and 557 (the stand-in,
P = 3), 2,521 (65,535 B, P = 13).

Usage: placement_stats.py PAGE.json [PAGE.json ...] [--json]
       placement_stats.py --page-loss [--json]
"""
import json
import math
import sys

import numpy as np

HALF = 8.0                     # interior half-side, modules


def centre(bi, bj):
    return (17 * bj + 9.0, 17 * bi + 9.0)


def strip_exact(pts, s=HALF):
    """Narrowest straight strip meeting every axis-aligned square of
    half-side s centred at pts (x, y): exact, modules (0 if a line does)."""
    bps = {0.0, math.pi / 2}
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dx, dy = pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]
            bps.add((math.atan2(dy, dx) + math.pi / 2) % math.pi)
    bps = sorted(bps) + [math.pi]

    def proj(t):
        c, sn = math.cos(t), math.sin(t)
        return c, sn, [c * x + sn * y for x, y in pts]

    def g(t):
        c, sn, pr = proj(t)
        return max(pr) - min(pr) - 2 * s * (abs(c) + abs(sn))
    best = math.inf
    for t0, t1 in zip(bps, bps[1:]):
        best = min(best, g(t0), g(t1))
        if t1 - t0 < 1e-12:
            continue
        c, sn, pr = proj((t0 + t1) / 2)
        hi, lo = pr.index(max(pr)), pr.index(min(pr))
        sx = 1.0 if c > 0 else -1.0
        wx = pts[hi][0] - pts[lo][0] - 2 * s * sx
        wy = pts[hi][1] - pts[lo][1] - 2 * s
        trough = math.atan2(wy, wx) + math.pi        # g = |w| cos(t - phi)
        for k in (-1, 0, 1):
            if t0 < trough + 2 * math.pi * k < t1:
                best = min(best, -math.hypot(wx, wy))
    return max(0.0, best)


def blot_radius(pts, s=HALF):
    """Smallest R such that one disc of radius R touches every square
    (min over the centre p of the max distance to a square), modules."""
    P = np.array(pts, dtype=np.float64)
    lo, hi = P.min(axis=0), P.max(axis=0)
    cx, cy = (lo + hi) / 2
    half = max(hi - lo) / 2 + 1.0
    best = None
    for _ in range(12):
        g = np.linspace(-half, half, 41)
        X, Y = np.meshgrid(cx + g, cy + g)
        dx = np.maximum(np.abs(X[..., None] - P[:, 0]) - s, 0)
        dy = np.maximum(np.abs(Y[..., None] - P[:, 1]) - s, 0)
        F = np.sqrt(dx * dx + dy * dy).max(axis=-1)
        k = np.unravel_index(np.argmin(F), F.shape)
        best = float(F[k])
        cx, cy = X[k], Y[k]
        half = 2 * (g[1] - g[0])
    return best


def chunk_copies(side):
    """-> {chunk: {'placed': [(bi, bj, k)], 'all': [(bi, bj)]}}."""
    out = {}
    for b, c, k in zip(side["slot_block"], side["slot_chunk"],
                       side["slot_copy"]):
        if c is None:
            continue
        d = out.setdefault(c, {"placed": [], "all": []})
        d["all"].append(tuple(b))
        if k in (0, 1, 2):
            d["placed"].append((b[0], b[1], k))
    return out


def offline_and_altitude(placed):
    pts = [(r, c) for r, c, _ in sorted(placed, key=lambda t: t[2])]
    off, alt = math.inf, math.inf
    for t in range(3):
        a, b = [pts[x] for x in range(3) if x != t]
        (ra, ca), (rb, cb), (rt, ct) = a, b, pts[t]
        cross = abs((ct - ca) * (rb - ra) - (cb - ca) * (rt - ra))
        if rb != ra:
            off = min(off, cross / abs(rb - ra))
        alt = min(alt, cross / math.hypot(rb - ra, cb - ca))
    return off, alt


def pct(v, p):
    v = sorted(v)
    return v[max(0, math.ceil(p * len(v)) - 1)]


def stats(side, blots=True):
    mm = side["module_dots"] * 25.4 / 600.0
    cc = chunk_copies(side)
    if not cc:
        return dict(chunks=0)
    spread, vert, off, alt, strip, strip_all, blot = [], [], [], [], [], [], []
    for c, d in sorted(cc.items()):
        pl = sorted(d["placed"], key=lambda t: t[2])
        if len(pl) != 3:
            raise SystemExit(f"chunk {c}: {len(pl)} placed copies")
        cols = [x[1] for x in pl]
        spread.append(min(abs(cols[0] - cols[1]), abs(cols[0] - cols[2]),
                          abs(cols[1] - cols[2])))
        vert.append(pl[2][0] - pl[0][0])
        o, a = offline_and_altitude(pl)
        off.append(o)
        alt.append(a)
        pts = [centre(r, c2) for r, c2, _ in pl]
        strip.append(strip_exact(pts) * mm)
        strip_all.append(strip_exact([centre(*b) for b in d["all"]]) * mm)
        if blots:
            blot.append(blot_radius(pts) * mm)
    keys = sorted(cc)
    worst = keys[int(np.argmin(strip))]
    out = dict(
        chunks=len(cc), min_column_spread=min(spread),
        min_vertical_0_2=min(vert),
        min_offline_columns=round(min(off), 3),
        min_altitude_blocks=round(min(alt), 3),
        min_strip_mm=round(min(strip), 2), p5_strip_mm=round(pct(strip, .05), 2),
        median_strip_mm=round(pct(strip, .5), 2),
        worst_chunk=worst,
        worst_chunk_blocks=[list(x[:2]) for x in
                            sorted(cc[worst]["placed"], key=lambda t: t[2])],
        chunks_strip_lt_5mm=sum(s < 5.0 for s in strip),
        chunks_strip_lt_15mm=sum(s < 15.0 for s in strip),
        min_strip_mm_all_copies=round(min(strip_all), 2),
        chunks_strip_lt_5mm_all_copies=sum(s < 5.0 for s in strip_all),
        chunks_offline_lt_3=sum(o < 3 for o in off),
        chunks_spread_lt_5=sum(s < 5 for s in spread))
    if blots:
        out.update(min_blot_mm=round(min(blot), 2),
                   p5_blot_mm=round(pct(blot, .05), 2))
    return out


def page_copies(N):
    """-> (P, {chunk: {copy k: (page, slot)}}, {chunk: (page, slot) of its
    fourth copy}) from gen.page_placement over every page."""
    import gen
    P = max(1, -(-N // gen.CHUNKS_PER_PAGE))
    placed, fourth = {}, {}
    for q in range(P):
        sc, sk = gen.page_placement(q, N)
        used = [s for s in range(len(sc)) if sc[s] is not None]
        assert len(used) == len(set(used))
        for s, (c, k) in enumerate(zip(sc, sk)):
            if c is None:
                continue
            if k == 3:
                assert c not in fourth, f"chunk {c}: two fourth copies"
                fourth[c] = (q, s)
            else:
                d = placed.setdefault(c, {})
                assert k not in d, f"chunk {c}: copy {k} twice"
                d[k] = (q, s)
    return P, placed, fourth


def _fatal_analysis(P, masks):
    """masks: the distinct page masks of the chunks (a chunk is lost iff
    its mask lies inside the lost set) -> fatal counts and minimal sets."""
    masks = sorted(set(masks))
    fatal = [any(m & ~L == 0 for m in masks) for L in range(1 << P)]
    minimal = [L for L in range(1 << P) if fatal[L] and
               not any(fatal[L & ~(1 << q)] for q in range(P) if L >> q & 1)]
    by = {}
    for L in range(1 << P):
        if fatal[L]:
            n = bin(L).count("1")
            by[n] = by.get(n, 0) + 1
    sets = [[q for q in range(P) if L >> q & 1] for L in minimal]
    return dict(fatal_by_size={k: by.get(k, 0) for k in (1, 2, 3)},
                fatal_total=sum(fatal), minimal_fatal=sets,
                min_fatal_size=min((len(s) for s in sets), default=None))


def page_loss(N):
    """The exact page-loss table of a payload of N chunks (module doc)."""
    import gen
    P, placed, fourth = page_copies(N)
    d = gen.page_step(P)
    ds = gen.design_slots()
    probs = []
    if sorted(placed) != list(range(N)):
        probs.append("chunks missing")
    worst_sheet = 0
    for c, cp in placed.items():
        g, i = divmod(c, gen.CHUNKS_PER_PAGE)
        if sorted(cp) != [0, 1, 2]:
            probs.append(f"chunk {c}: copies {sorted(cp)}")
            continue
        for k, (q, s) in cp.items():
            if q != (g + k * d) % P:
                probs.append(f"chunk {c} copy {k} on page {q}")
            if s != ds[i, k]:
                probs.append(f"chunk {c} copy {k} at slot {s}, design "
                             f"{ds[i, k]}")
        pages = [q for q, _ in cp.values()]
        worst_sheet = max(worst_sheet, max(pages.count(q) for q in pages))
        if c in fourth and fourth[c][0] in pages and P >= 4:
            probs.append(f"chunk {c}: fourth copy on a page with a placed "
                         "copy")
    pm = {c: sum(1 << q for q in {q for q, _ in cp.values()})
          for c, cp in placed.items()}
    am = {c: m | (1 << fourth[c][0] if c in fourth else 0)
          for c, m in pm.items()}
    out = dict(P=P, N=N, d=d, problems=probs[:5], n_problems=len(probs),
               fourth_copies=len(fourth),
               max_placed_copies_on_one_sheet=worst_sheet,
               placed=_fatal_analysis(P, pm.values()),
               with_fourth=_fatal_analysis(P, am.values()))
    want = sorted(sorted({g % P, (g + d) % P, (g + 2 * d) % P})
                  for g in range(P)) if P >= 3 else None
    for key in ("placed", "with_fourth"):
        a = out[key]
        three = sorted(s for s in a["minimal_fatal"] if len(s) == 3)
        a["minimal_3sets_are_g_gd_g2d"] = (
            None if want is None else
            three == sorted(map(list, {tuple(w) for w in want}))
            and all(len(s) == 3 for s in a["minimal_fatal"]))
        a["adjacent_in_a_minimal_set"] = any(
            any(q + 1 in s for q in s) for s in a["minimal_fatal"]
            if len(s) >= 2)
        a["adjacent_cyclic_in_a_minimal_set"] = any(
            any((q + 1) % P in s for q in s) for s in a["minimal_fatal"]
            if len(s) >= 2 and P >= 3)
    return out


def page_loss_table():
    rows = []
    for P in range(1, 14):
        Ns = sorted({204 * (P - 1) + 1, min(204 * P, 2521)}   # 2,521 =
                    | ({557} if P == 3 else set()))              # 65,535 B
        rows += [page_loss(N) for N in Ns]
    return rows


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv
    if "--page-loss" in argv:
        rows = page_loss_table()
        if as_json:
            print(json.dumps(rows, indent=1))
            return 0
        for r in rows:
            a, b = r["placed"], r["with_fourth"]
            print(f"P {r['P']:2d} N {r['N']:4d} d {r['d']}: placed copies: "
                  f"fatal 1/2/3-sets {a['fatal_by_size'][1]}/"
                  f"{a['fatal_by_size'][2]}/{a['fatal_by_size'][3]}, "
                  f"minimal {a['minimal_fatal']}, = {{g, g+d, g+2d}} "
                  f"{a['minimal_3sets_are_g_gd_g2d']}, adjacent pages in "
                  f"one {a['adjacent_in_a_minimal_set']} (cyclic "
                  f"{a['adjacent_cyclic_in_a_minimal_set']}); with fourth "
                  f"copies ({r['fourth_copies']}): fatal 1/2/3-sets "
                  f"{b['fatal_by_size'][1]}/{b['fatal_by_size'][2]}/"
                  f"{b['fatal_by_size'][3]}, minimal "
                  f"{b['minimal_fatal'] if b['minimal_fatal'] != a['minimal_fatal'] else 'the same'}"
                  f"; most placed copies on one sheet "
                  f"{r['max_placed_copies_on_one_sheet']}; overlay "
                  f"{'= the design' if not r['n_problems'] else r['problems']}")
        return 0
    for p in [a for a in argv if a != "--json"]:
        st = stats(json.load(open(p)))
        print(json.dumps(dict(page=p, **st)) if as_json else
              f"{p}: " + ", ".join(f"{k} {v}" for k, v in st.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

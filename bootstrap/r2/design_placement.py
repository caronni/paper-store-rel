#!/usr/bin/env python3
"""Design search for the R2 copy placement (provenance of gen.py's PI1, PI2,
SKIP and OVERFLOW tables; generator side, scipy allowed; never typed).

The family (structured, the same rule on every page):
  copy 0 of page-local chunk i at band-0 data slot i (block raster order),
  block (r0, c); copy 1 in band 1, column PI1[c]; copy 2 in band 2, column
  PI2[c]; the row of copy k = the free (non-bullseye) row of the same RANK in
  its column as r0 has in column c of band 0 (rows top to bottom).  So
  r1 - r0 and r2 - r1 are 10 +- 1 (bullseye rows shift a rank) and r2 - r0
  is about 20: as large as the bands allow for every chunk at once (any
  bijection of band-0 rows onto band-2 rows has mean r2 - r0 = 20).
Column sizes: bands 0 and 2 have 9 free rows in columns S = {2, 5, 8, 11,
14, 17}, band 1 in B1 = {2, 8, 14}; every other column 10.  Band 1 fits
exactly (PI1 maps no 10-row column into B1; its 3 unreached slots stay
leftovers).  In band 2 a few columns CROSS: a 10-row column c with PI2[c] in
S has one chunk too many, the one at band-0 rank SKIP[c] (0 or 9), the
others keep their order; a 9-row column c' with PI2[c'] outside S leaves one
row of its target unreached, rank SKIP[c'] (0 or 9), the others keep their
order.  OVERFLOW pairs every overflowing chunk with one unreached slot: its
copy 2 goes there.  (Measured: with no crossing no assignment keeps every
chunk's strip above 0.)
Constraints: PI1, PI2 bijections of the 21 columns; the three columns of
every chunk pairwise >= 5 apart (the overflow chunks' too).
Objective, over the full page (every shorter page is a subset of its
triangles): strip = the narrowest straight strip touching the interiors of
all three copies (placement_stats.strip_exact, exact).  Stage 1: the largest
T such that every chunk's strip >= T (binary search over the candidate
values; each step a mixed-integer feasibility program over the column
triples with their SKIP variants and the overflow pairings).  Stage 2: at
T, maximise the sum of log strips over the columns' minima and the overflow
chunks (geometric mean; lifts the low tail).  Crossings: the smallest limit
that reaches the best T.  scipy.optimize.milp (HiGHS).

Usage: design_placement.py [--json OUT.json]
Prints the tables and the per-column strips (mm).
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import placement_stats as ps  # noqa: E402

BULL = {(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)} | \
       {(bi, bj) for bi in (8, 20) for bj in (5, 11, 17)}
COLS = 21
MIN_SPREAD = 5
MM = 12 * 25.4 / 600.0
SKIPS = (0, 9)


def free_rows(k, col):
    return [r for r in range(10 * k, 10 * k + 10) if (r, col) not in BULL]


ROWS = [[free_rows(k, c) for c in range(COLS)] for k in range(3)]
S = {c for c in range(COLS) if len(ROWS[0][c]) == 9}
B1 = {c for c in range(COLS) if len(ROWS[1][c]) == 9}


def spread_ok(*cols):
    return all(abs(x - y) >= MIN_SPREAD for i, x in enumerate(cols)
               for y in cols[i + 1:])


def kind(c, b):
    if (c in S) == (b in S):
        return "fit"
    return "over" if b in S else "spare"


def rank_pairs(c, b, skip):
    """Band-2 (source rank, target rank) pairs of column c into column b."""
    n0, n2 = len(ROWS[0][c]), len(ROWS[2][b])
    if n0 == n2:
        return [(k, k) for k in range(n0)]
    if n0 > n2:                                   # over: source skip leaves
        return list(zip([k for k in range(n0) if k != skip], range(n2)))
    return list(zip(range(n0), [m for m in range(n2) if m != skip]))


def column_strip(c, a, b, skip):
    """Min strip over the column's chunks (modules), or None."""
    if not spread_ok(c, a, b) or len(ROWS[0][c]) > len(ROWS[1][a]):
        return None
    return min(ps.strip_exact([ps.centre(ROWS[0][c][k], c),
                               ps.centre(ROWS[1][a][k], a),
                               ps.centre(ROWS[2][b][m], b)])
               for k, m in rank_pairs(c, b, skip))


def overflow_strip(c, a, rho, b, sigma):
    """Overflow chunk: band-0 rank rho of column c, copy 1 at rank rho of
    column a, copy 2 at the unreached rank sigma of column b."""
    if not spread_ok(c, a, b):
        return 0.0
    return ps.strip_exact([ps.centre(ROWS[0][c][rho], c),
                           ps.centre(ROWS[1][a][rho], a),
                           ps.centre(ROWS[2][b][sigma], b)])


def model(J, f, OV, T, objective, max_cross):
    """At threshold T: x per column variant (c, a, b, skip) with f >= T; y
    per (over variant, spare slot (b, sigma)) with the overflow strip >= T.
    -> (variants, {overflow column: (b, sigma)}) or None."""
    idx = [j for j in range(len(J)) if f[j] >= T]
    K = [J[j] for j in idx]
    Y = [(k, b, sg) for k, t in enumerate(K) if kind(t[0], t[2]) == "over"
         for b in range(COLS) if b not in S for sg in SKIPS
         if OV[(t[0], t[1], t[3], b, sg)] >= T]
    nx, nv = len(K), len(K) + len(Y)
    if nx == 0:
        return None
    rows, lb, ub = [], [], []

    def add(coef, lo, hi):
        r = np.zeros(nv)
        for j, v in coef:
            r[j] += v
        rows.append(r)
        lb.append(lo)
        ub.append(hi)
    for pos in range(3):                                   # bijections
        for v in range(COLS):
            add([(k, 1) for k, t in enumerate(K) if t[pos] == v], 1, 1)
    for k, t in enumerate(K):                   # a chosen crossing is paired
        if kind(t[0], t[2]) == "over":
            add([(nx + m, 1) for m, y in enumerate(Y) if y[0] == k]
                + [(k, -1)], 0, 0)
    for b in range(COLS):                  # a spare slot takes one overflow
        if b in S:
            continue
        for sg in SKIPS:
            add([(nx + m, 1) for m, y in enumerate(Y) if y[1:] == (b, sg)]
                + [(k, -1) for k, t in enumerate(K)
                   if kind(t[0], t[2]) == "spare" and t[2] == b
                   and t[3] == sg], 0, 0)
    add([(k, 1) for k, t in enumerate(K) if kind(t[0], t[2]) == "over"],
        0, max_cross)
    obj = [objective(t) for t in K] + \
        [objective(("ov", K[k][0], K[k][1], K[k][3], b, sg))
         for k, b, sg in Y]
    res = milp(c=-np.asarray(obj, dtype=float),
               constraints=LinearConstraint(np.array(rows), lb, ub),
               integrality=np.ones(nv), bounds=Bounds(np.zeros(nv),
                                                      np.ones(nv)))
    if not res.success:
        return None
    pick = [K[k] for k in range(nx) if res.x[k] > 0.5]
    pair = {K[k][0]: (b, sg) for m, (k, b, sg) in enumerate(Y)
            if res.x[nx + m] > 0.5}
    return pick, pair


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    J, f = [], []
    for c in range(COLS):
        for x in range(COLS):
            for y in range(COLS):
                for sk in ((None,) if kind(c, y) == "fit" else SKIPS):
                    v = column_strip(c, x, y, sk)
                    if v is not None:
                        J.append((c, x, y, sk))
                        f.append(v)
    OV = {(c, x, rho, b, sg): overflow_strip(c, x, rho, b, sg)
          for c in range(COLS) if c not in S
          for x in range(COLS) if x not in B1
          for rho in SKIPS for b in range(COLS) if b not in S
          for sg in SKIPS}
    fmap = dict(zip(J, f))
    cand = sorted(set(f) | set(OV.values()))     # the bottleneck is either

    def zero(t):
        return 0.0

    def logobj(t):
        return math.log(max(1e-9, OV[t[1:]] if t[0] == "ov" else fmap[t]))
    results = {}
    for mc in (1, 2, 3, 6):
        lo, hi, best = 0, len(cand) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if model(J, f, OV, cand[mid], zero, mc) is not None:
                best, lo = cand[mid], mid + 1
            else:
                hi = mid - 1
        results[mc] = best
        print(f"crossings <= {mc}: max-min strip {best * MM:.2f} mm")
    top = max(results.values())
    mc = min(m for m, v in results.items() if v == top)  # shortest table
    pick, pair = model(J, f, OV, top, logobj, mc)
    p1, p2, skip = [None] * COLS, [None] * COLS, {}
    for c, u, v, sk in pick:
        p1[c], p2[c] = u, v
        if sk is not None:
            skip[c] = sk
    assert sorted(p1) == list(range(COLS)) == sorted(p2)
    ovs = {c: OV[(c, p1[c], skip[c]) + pair[c]] * MM for c in pair}
    per_col = [round(column_strip(c, p1[c], p2[c], skip.get(c)) * MM, 2)
               for c in range(COLS)]
    zmin = min(min(per_col), min(ovs.values()))
    print(f"adopted: crossings <= {mc}; max-min strip {zmin:.2f} mm")
    print("PI1 =", p1)
    print("PI2 =", p2)
    print("SKIP =", dict(sorted(skip.items())))
    for c in sorted(pair):
        b, sg = pair[c]
        print(f"overflow: column {c} -> {p2[c]}: the chunk at band-0 rank "
              f"{skip[c]} takes copy-2 slot ({ROWS[2][b][sg]}, {b}); strip "
              f"{ovs[c]:.2f} mm")
    print("per-column min strip (mm):", per_col)
    print("sorted:", sorted(per_col))
    if a.json:
        json.dump(dict(PI1=p1, PI2=p2,
                       SKIP={str(c): v for c, v in sorted(skip.items())},
                       OVERFLOW={str(c): [ROWS[2][b][sg], b]
                                 for c, (b, sg) in sorted(pair.items())},
                       max_min_strip_mm=round(zmin, 3),
                       overflow_strip_mm={str(c): round(v, 3)
                                          for c, v in sorted(ovs.items())},
                       by_max_crossings_mm={str(m): round(v * MM, 3)
                                            for m, v in results.items()},
                       per_column_strip_mm=per_col), open(a.json, "w"),
                  indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

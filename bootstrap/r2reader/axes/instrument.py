#!/usr/bin/env python3
"""Instrumented run of the typed stage-2 reader (reader_lite_v1.py) against
the truth of a capture (2026-10-22, the up-left question).

The reader's own functions are exec'd from reader_lite_v1.py (the region
between BEGIN READER and its main loop), so ld, v, be, fm, ft, f, a, rb, sp
are the reader's code, untouched.  Only wk is re-stated here, statement for
statement with the same integer operations, with logging beside it; every
ft call is re-done by ft_trace (all nine scores of every stage, ties counted)
and asserted equal to the reader's ft.  The accepted-block count is compared
with the plain reader's progress line by the caller (see DIAG-2026-10-22.md).

Truth per capture kind:
  render   camera.py sidecar: homography page dots -> px (pixel u spans
           [u, u+1)); grid modules -> px through x0, y0, module_dots;
  raster   the 600-dpi .pbm itself: identity at module_dots px per module;
  grid     the 0/1 text grid as ld reads it: 3 px per module, 4 modules pad;
  photo    no recorded warp: a homography from the 15 bullseyes (matched
           through the reader's own CRC-closed reads) seeds a per-block
           genie fit (6-parameter local affine of the block's 18 x 18
           modules against the blurred truth grid, gain/offset projected
           out); validated on a render whose warp is known (--genie).
Reader coordinates are 1/16 px with pixel i's centre at 16 i, so a
continuous pixel position U (pixel u spanning [u, u+1)) is 16 (U - 0.5).

Usage:
  instrument.py run CAPTURE --page PAGE.json --grid GRID.txt --kind KIND
                [--sidecar CAM.json] [--name NAME] [--out DIR] [--genie]
  instrument.py table DIR/*.json      (the central table, markdown)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from typing import Any

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
READER_PATH = os.path.join(os.path.dirname(HERE), "reader_lite_v1.py")
CORNERS = ((-8, -8), (7, -8), (-8, 7), (7, 7))
DIAG = {(-1, -1): "up-left", (-1, 1): "up-right", (1, -1): "down-left",
        (1, 1): "down-right"}
CLASSES = ("up-left", "up-right", "down-left", "down-right", "axial",
           "other")


def load_reader() -> dict[str, Any]:
    """The reader's definitions, exec'd from its own source (no main loop)."""
    src = open(READER_PATH).read()
    body = src.split("# BEGIN READER", 1)[1]
    body = body.split("\nc,e,i,n={},b'',0,'?'", 1)[0]
    ns: dict[str, Any] = {}
    exec(compile(body, READER_PATH, "exec"), ns)
    return ns


def ft_trace(R: dict[str, Any], s: list, p: int, rule: str = "reader"
             ) -> tuple[int, int, list]:
    """The reader's ft, statement for statement, keeping every stage's
    scores; returns (m, n, stages) with stages = [(step, best, n_tied,
    tied_offsets)].  rule "reader" = the reader's max over (score, r, q),
    which breaks a tie toward the larger r, then the larger q; rule
    "centre" (a COUNTERFACTUAL, not the reader) moves to the centre of the
    tied candidates' bounding box instead."""
    v, sp, fr = R["v"], R["sp"], R["fr"]
    c = [(sp(s, x, y), 1 - 2 * (k ^ s[4])) for x, y, k in fr]
    m = n = 0
    stages = []
    for y in (p // 32, p // 64, p // 128, p // 256):
        cand = [(sum(v(x + r, y_ + q) * t for (x, y_), t in c), r, q)
                for r in (m - y, m, m + y) for q in (n - y, n, n + y)]
        k, m2, n2 = max(cand)
        tied = [(r, q) for sc, r, q in cand if sc == k]
        if rule == "centre" and len(tied) > 1:
            rs, qs = [e[0] for e in tied], [e[1] for e in tied]
            m2, n2 = (min(rs) + max(rs)) // 2, (min(qs) + max(qs)) // 2
        m, n = m2, n2
        stages.append((y, k, len(tied), tied))
    return m, n, stages


def fm_logged(R: dict[str, Any], rule: str = "reader"
              ) -> tuple[tuple[int, list], bytes, list]:
    """The reader's fm, statement for statement, keeping the rotation
    scores.  rule "reader" = max over (score, r, t): a tie goes to the
    larger r; rule "r0" (a COUNTERFACTUAL) takes the tied r of least |r|."""
    z, be, w, ax, f, a = R["z"], R["be"], R["w"], R["ax"], R["f"], R["a"]
    hd, e = R["hd"], R["e"]
    c = be(z.translate(bytes(x < t for t in [(min(z[::97]) + max(z[::97]))
                                             // 2] for x in range(256))))
    cand = [(sum(abs(w(ax(x, y, p, r, t))) for k, x, y, p in c), r, t)
            for r in range(-640, 641, 64) for t in range(4)]
    k, m, n = max(cand)
    if rule == "r0":
        tied = [e_ for e_ in cand if e_[0] == k]
        k, m, n = min(tied, key=lambda e_: (abs(e_[1]), -e_[1], -e_[2]))
    r = []
    for k, x, y, p in c:
        s = ax(x, y, p, m, n)
        r += [s + [int(w(s) < 0), (len(r), 0, 0)]]
    t = e
    for s in r:
        t = t or a(*f(s), hd, 20)
    return (c[0][3] if c else 0, r), t or e, cand


def hard_bits(R: dict[str, Any], s: list) -> tuple[list[int], int, int]:
    """The 256 bits a() starts from (before CRC/flips), rb's dark count."""
    c, t = R["f"](s)
    bits = [1 if t - c[i, k] + (c[i - 1, k] + c[i + 1, k] + c[i, k - 1]
                                + c[i, k + 1] - 4 * c[i, k] >> 1) > 0 else 0
            for i, k in R["m"]]
    dark = sum(c[x, y] < t for x, y in R["m"])
    return bits, t, dark


def wk_logged(R: dict[str, Any], p: int, t: list, log: list,
              rule: str = "reader") -> list:
    """The reader's wk, same statements, with a record per queue entry.
    Queue entries carry a 7th element (the parent's key and direction),
    which no reader statement reads."""
    sp, ft, v, rb, fr = R["sp"], R["ft"], R["v"], R["rb"], R["fr"]
    h, j = R["h"], R["j"]
    w, f, i, c = {}, {}, [], 5 * p >> 4
    for s in t:
        rec: dict[str, Any] = dict(
            key=list(s[5]), parent=s[6] if len(s) > 6 else None,
            pred=[s[0], s[1]], inh=[list(s[2]), list(s[3])], flip=s[4])
        log.append(rec)
        x, y = s[0] // c, s[1] // c
        if (x, y) in w:
            rec["skip"] = "dup"
            q, a, b = s[5]
            if a or b:
                s2 = [s[0], s[1], s[2], s[3], s[4], s[5]]
                m2, n2, _ = ft_trace(R, s2, p, rule)
                rec["dup_refined"] = [s[0] + m2, s[1] + n2]
            continue
        w[x, y] = 1
        if [1 for x, n in [sp(s, r, t) for r in (-10, 9) for t in (-10, 9)]
                if min(x, n) < 0 or x > 16 * h - 32 or n > 16 * j - 32]:
            rec["skip"] = "edge"
            continue
        q, a, b = s[5]
        rec["learned"] = [None, None]
        if a or b:
            m, n, stages = ft_trace(R, s, p, rule)
            if rule == "reader":
                assert (m, n) == ft(s, p), "ft_trace diverged from the reader"
            rec["ft"] = [[st[0], st[1], st[2], st[3]] for st in stages]
            s[0], s[1] = s[0] + m, s[1] + n
            for k, z in ((2, b), (3, a)):
                u = (z > 0) - (z < 0)
                g = f.get((q, a - u * (k > 2), b - u * (k < 3)))
                if g and u:
                    s[k] = [u * (s[0] - g[0]), u * (s[1] - g[1])]
                    rec["learned"][k - 2] = [q, a - u * (k > 2),
                                             b - u * (k < 3)]
        rec["refined"] = [s[0], s[1]]
        rec["axes"] = [list(s[2]), list(s[3])]
        r = [(v(*sp(s, x, y)), 1 - 2 * (k ^ s[4])) for x, y, k in fr]
        g = sum(a for a, b in r) // 68
        rec["read"] = None
        if a or b:
            bits, thr, dark = hard_bits(R, s)
            rec["bits"] = "".join(map(str, bits))
            rec["thr"], rec["dark"] = thr, dark
            x = rb(s)
            if x:
                i += [x]
                rec["read"] = int.from_bytes(x[:2], "big")
                rec["payload"] = x.hex()
            else:
                rec["read"] = -1
        sc1, sc2 = 5 * sum(a * b for a, b in r), 3 * sum(abs(a - g)
                                                         for a, b in r)
        rec["sound"] = sc1 >= sc2
        rec["sound_margin"] = sc1 - sc2
        if sc1 >= sc2:
            f[q, a, b] = s
            t += [[s[0] + t * s[2 + x // 2][0], s[1] + t * s[2 + x // 2][1],
                   s[2], s[3], 1 - s[4], (q, a + t * (x > 1), b + t * (x < 2)),
                   [q, a, b, x]]
                  for x in range(4) for t in [1 - 2 * (x % 2)]]
    return i


# ---------------------------------------------------------------- truth --

class Truth:
    """Page module (continuous grid-module coordinates, module (c, r)
    spanning [c, c+1)) -> reader units (1/16 px, pixel centre at 16 i)."""

    def __init__(self, page: dict[str, Any], grid: list[str]) -> None:
        self.page = page
        self.grid = grid
        self.H: np.ndarray | None = None
        self.blocks: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
        self.resid: dict[tuple[int, int], float] = {}
        self.dropped: set[tuple[int, int]] = set()

    def set_h(self, H_px: np.ndarray) -> None:
        """H_px maps grid modules -> continuous px (pixel u = [u, u+1))."""
        self.H = H_px / H_px[2, 2]

    def h_point(self, cm: float, rm: float) -> np.ndarray:
        assert self.H is not None
        q = self.H @ np.array([cm, rm, 1.0])
        return 16.0 * (q[:2] / q[2] - 0.5)

    def h_jac(self, cm: float, rm: float) -> np.ndarray:
        e = 1e-3
        dx = (self.h_point(cm + e, rm) - self.h_point(cm - e, rm)) / (2 * e)
        dy = (self.h_point(cm, rm + e) - self.h_point(cm, rm - e)) / (2 * e)
        return np.stack([dx, dy], axis=1)

    @staticmethod
    def centre_cm(R: int, C: int) -> tuple[float, float]:
        return 17 * C + 9 + 0.5, 17 * R + 9 + 0.5

    def frame(self, R: int, C: int) -> tuple[np.ndarray, np.ndarray] | None:
        """(centre, J) of block (R, C) in reader units; J per module."""
        if (R, C) in self.dropped:
            return None
        if (R, C) in self.blocks:
            return self.blocks[R, C]
        if self.H is None:
            return None
        cm, rm = self.centre_cm(R, C)
        return self.h_point(cm, rm), self.h_jac(cm, rm)

    def point(self, R: int, C: int, x: float, y: float) -> np.ndarray | None:
        """Reader-unit position of the centre of local module (x, y)."""
        if (R, C) in self.blocks:
            c0, J = self.blocks[R, C]
            return c0 + J @ np.array([x, y], dtype=float)
        if self.H is None:
            return None
        cm, rm = self.centre_cm(R, C)
        return self.h_point(cm + x, rm + y)

    def bits(self, R: int, C: int) -> str:
        return "".join(self.grid[17 * R + 9 + y][17 * C + 9 + x]
                       for y in range(-8, 8) for x in range(-8, 8))


def dlt(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(A, dtype=float))
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def genie_fit(truth: Truth, img: np.ndarray, sigma_mod: float = 0.4,
              step: float = 0.25) -> dict[str, Any]:
    """Per-block local affine against the blurred truth grid, seeded by
    truth.H.  Fills truth.blocks; returns fit statistics."""
    from scipy import ndimage, optimize
    up = 8
    G = np.array([[1.0 if ch == "1" else 0.0 for ch in row]
                  for row in truth.grid], dtype=np.float32)
    T = np.kron(G, np.ones((up, up), dtype=np.float32))
    T = ndimage.gaussian_filter(T, sigma_mod * up)
    I = img.astype(np.float32)
    hh, ww = I.shape
    loc = np.arange(-9.5, 8.5 + 1e-9, step)
    lx, ly = np.meshgrid(loc, loc)
    lx, ly = lx.ravel(), ly.ravel()
    stats = dict(fitted=0, skipped=0, shift_px=[], cost=[])
    BH, BW = truth.page["BH"], truth.page["BW"]
    # breadth-first from the bullseye blocks (seeded by truth.H), every
    # other block seeded by its already-fitted neighbour's affine: a
    # homography from 15 points misses a phone frame by up to ~2 modules
    queue: list[tuple[int, int, tuple[int, int] | None]] = [
        (bz["block"][0], bz["block"][1], None)
        for bz in truth.page["bullseyes"]]
    seen: set[tuple[int, int]] = set()
    while queue:
        R, C, par = queue.pop(0)
        if (R, C) in seen or not (0 <= R < BH and 0 <= C < BW):
            continue
        seen.add((R, C))
        cm, rm = truth.centre_cm(R, C)
        tv = ndimage.map_coordinates(
            T, [(rm + ly) * up - 0.5, (cm + lx) * up - 0.5], order=1)
        ch = truth.h_point(cm, rm) / 16.0 + 0.5   # continuous px, from H
        if par is None:
            c0 = ch
            J = truth.h_jac(cm, rm) / 16.0
        else:
            pc, pJ = truth.blocks[par]
            pc, pJ = pc / 16.0 + 0.5, pJ / 16.0
            c0 = pc + pJ @ np.array([17.0 * (C - par[1]),
                                     17.0 * (R - par[0])])
            J = pJ
        pts = c0[:, None] + J @ np.stack([lx, ly])
        if (pts[0].min() < 2 or pts[1].min() < 2
                or pts[0].max() > ww - 3 or pts[1].max() > hh - 3):
            stats["skipped"] += 1
            continue
        M = np.stack([np.ones_like(tv), tv], axis=1)

        def res(prm: np.ndarray) -> np.ndarray:
            cc = prm[:2]
            JJ = prm[2:].reshape(2, 2)
            pp = cc[:, None] + JJ @ np.stack([lx, ly])
            iv = ndimage.map_coordinates(I, [pp[1] - 0.5, pp[0] - 0.5],
                                         order=1, mode="nearest")
            coef, *_ = np.linalg.lstsq(M, iv, rcond=None)
            return iv - M @ coef
        x0 = np.concatenate([c0, J.ravel()])
        sol = optimize.least_squares(res, x0, method="lm",
                                     x_scale=np.array([1, 1] + [0.1] * 4))
        cc, JJ = sol.x[:2], sol.x[2:].reshape(2, 2)
        truth.blocks[R, C] = (16.0 * (cc - 0.5), 16.0 * JJ)
        stats["fitted"] += 1
        stats["shift_px"].append(float(np.hypot(*(cc - ch))))
        r0 = res(sol.x)
        stats["cost"].append(float(np.sqrt(np.mean(r0 ** 2))))
        truth.resid[R, C] = stats["cost"][-1]
        for dR, dC in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            queue.append((R + dR, C + dC, (R, C)))
    cs = stats.pop("cost")
    # a fit whose residual is over twice the frame's median is not trusted
    # (measured on photo 1: seven such blocks sat 0.8-1.2 modules off the
    # reader's CRC-closed poses); their geometric truth is withheld
    if cs:
        med = float(np.median(cs))
        truth.dropped = {k for k, r in truth.resid.items() if r > 2 * med}
        stats["dropped"] = sorted([list(k) for k in truth.dropped])
    stats["rms_resid_median"] = float(np.median(cs)) if cs else None
    stats["rms_resid_max"] = float(np.max(cs)) if cs else None
    sh = stats.pop("shift_px")
    stats["shift_from_H_px_median"] = float(np.median(sh)) if sh else None
    stats["shift_from_H_px_max"] = float(np.max(sh)) if sh else None
    return stats


# ------------------------------------------------------------- analysis --

def classify(a: int, b: int) -> str:
    if (a, b) in DIAG:
        return DIAG[a, b]
    if abs(a) + abs(b) == 1:
        return "axial"
    return "other"


def seed_blocks(page: dict[str, Any], log: list,
                slot_of_chunk: dict[int, list[tuple[int, int]]],
                n_seeds: int) -> dict[int, tuple[int, int]]:
    """Seed q -> page bullseye block, voted from CRC-closed reads: a read
    chunk sits in one of its copies' blocks (R, C); the seed's block is
    (R - a, C - b) for the copy that lands on a bullseye block."""
    bull = {tuple(bz["block"]) for bz in page["bullseyes"]}
    votes: dict[int, dict[tuple[int, int], int]] = {}
    for rec in log:
        if rec.get("read") is None or rec["read"] < 0:
            continue
        q, a, b = rec["key"]
        for (R, C) in slot_of_chunk.get(rec["read"], []):
            sb = (R - a, C - b)
            if sb in bull:
                votes.setdefault(q, {}).setdefault(sb, 0)
                votes[q][sb] += 1
    return {q: max(vs, key=vs.get) for q, vs in votes.items()}


def analyse(truth: Truth, R_: dict[str, Any], log: list,
            seeds_block: dict[int, tuple[int, int]],
            chunk_at: dict[tuple[int, int], int]) -> None:
    """Truth fields onto every processed record."""
    sp = R_["sp"]
    for rec in log:
        q, a, b = rec["key"]
        if q not in seeds_block:
            rec["truth"] = None
            continue
        R, C = seeds_block[q][0] + a, seeds_block[q][1] + b
        if not (0 <= R < truth.page["BH"] and 0 <= C < truth.page["BW"]):
            rec["offpage"] = [R, C]
            continue
        rec["block"] = [R, C]
        if "refined" not in rec:
            if "dup_refined" in rec:
                fr_ = truth.frame(R, C)
                if fr_ is not None:
                    Ji = np.linalg.inv(fr_[1])
                    rec["dup_err_mod"] = (Ji @ (np.array(rec["dup_refined"],
                                                         float) - fr_[0])
                                          ).tolist()
            continue
        if (a or b) and "bits" in rec:
            tb = truth.bits(R, C)
            mis = [k for k in range(256) if rec["bits"][k] != tb[k]]
            rec["misread"] = len(mis)
            rec["misread_cells"] = [[k % 16 - 8, k // 16 - 8] for k in mis]
            rec["true_chunk"] = chunk_at.get((R, C))
            if rec["read"] is not None and rec["read"] >= 0:
                rec["read_correct"] = rec["read"] == rec["true_chunk"]
        fr_ = truth.frame(R, C)
        if fr_ is None:
            rec["truth"] = None
            continue
        c0, J = fr_
        if (R, C) in truth.resid:
            rec["truth_resid"] = truth.resid[R, C]
        Ji = np.linalg.inv(J)
        At, Bt = 17 * J[:, 0], 17 * J[:, 1]
        rec["true_centre"] = c0.tolist()
        rec["true_axes"] = [At.tolist(), Bt.tolist()]
        rec["pred_err_mod"] = (Ji @ (np.array(rec["pred"], float) - c0)
                               ).tolist()
        rec["ctr_err_mod"] = (Ji @ (np.array(rec["refined"], float) - c0)
                              ).tolist()
        for nm, ax in (("inh", rec["inh"]), ("fin", rec["axes"])):
            rec[nm + "_axis_err"] = [
                float(np.linalg.norm(np.array(ax[0]) - At)
                      / np.linalg.norm(At)),
                float(np.linalg.norm(np.array(ax[1]) - Bt)
                      / np.linalg.norm(Bt))]
        s = [rec["refined"][0], rec["refined"][1], rec["axes"][0],
             rec["axes"][1]]
        disp = []
        for (x, y) in CORNERS:
            tp = truth.point(R, C, x, y)
            d = Ji @ (np.array(sp(s, x, y), float) - tp)
            disp.append([x, y, float(d[0]), float(d[1]),
                         float(np.hypot(*d))])
        rec["corner_disp_mod"] = disp
        far = max(disp, key=lambda e: (17 * b + e[0]) ** 2
                  + (17 * a + e[1]) ** 2)
        rec["far_corner"] = far


def summarize(log: list, bull: set) -> dict[str, Any]:
    """Per page block: its first processed visit decides class and
    metrics; read if any processed visit read it."""
    first: dict[tuple[int, int], dict] = {}
    anyread: dict[tuple[int, int], bool] = {}
    nvis: dict[tuple[int, int], int] = {}
    for rec in log:
        if "refined" not in rec or "block" not in rec:
            continue
        a, b = rec["key"][1:]
        if not (a or b):
            continue
        k = tuple(rec["block"])
        if k in bull or ("bits" in rec and rec.get("true_chunk") is None):
            continue    # bullseye blocks and white (chunk-less) slots
        nvis[k] = nvis.get(k, 0) + 1
        if k not in first:
            first[k] = rec
        anyread[k] = anyread.get(k, False) or (rec["read"] is not None
                                               and rec["read"] >= 0)
    rows: dict[str, dict[str, Any]] = {}
    for cl in CLASSES + ("ALL",):
        rows[cl] = dict(blocks=0, read=0, unread_sound=0, unread=0,
                        mis=[], far=[], axA=[], axB=[], inhA=[], inhB=[],
                        unread_mis=[], unread_far=[], ctr=[])
    for k, rec in first.items():
        cl = classify(*rec["key"][1:])
        for row in (rows[cl], rows["ALL"]):
            row["blocks"] += 1
            if anyread[k]:
                row["read"] += 1
            else:
                row["unread"] += 1
                if rec["sound"]:
                    row["unread_sound"] += 1
                if "misread" in rec:
                    row["unread_mis"].append(rec["misread"])
                if "far_corner" in rec:
                    row["unread_far"].append(rec["far_corner"][4])
            if "misread" in rec:
                row["mis"].append(rec["misread"])
            if "far_corner" in rec:
                row["far"].append(rec["far_corner"][4])
                row["axA"].append(rec["fin_axis_err"][0])
                row["axB"].append(rec["fin_axis_err"][1])
                row["inhA"].append(rec["inh_axis_err"][0])
                row["inhB"].append(rec["inh_axis_err"][1])
                row["ctr"].append(float(np.hypot(*rec["ctr_err_mod"])))
    out = {}
    for cl, row in rows.items():
        o = {k: row[k] for k in ("blocks", "read", "unread_sound", "unread")}
        for nm in ("mis", "far", "axA", "axB", "inhA", "inhB", "unread_mis",
                   "unread_far", "ctr"):
            xs = row[nm]
            o[nm + "_mean"] = float(np.mean(xs)) if xs else None
            o[nm + "_max"] = float(np.max(xs)) if xs else None
        out[cl] = o
    out["_visits_per_block_max"] = max(nvis.values()) if nvis else 0
    out["_white_slots_visited"] = len({tuple(r["block"]) for r in log
                                       if "bits" in r and "block" in r
                                       and r.get("true_chunk") is None})
    return out


def img_diag_summary(log: list, bull: set) -> dict[str, list[int]]:
    """Diagonal keys classed by their IMAGE direction: [blocks, unread]."""
    first: dict[tuple[int, int], dict] = {}
    anyread: dict[tuple[int, int], bool] = {}
    for rec in log:
        if "refined" not in rec or "block" not in rec:
            continue
        if not any(rec["key"][1:]):
            continue
        k = tuple(rec["block"])
        if "bits" in rec and rec.get("true_chunk") is None:
            continue
        first.setdefault(k, rec)
        anyread[k] = anyread.get(k, False) or (rec["read"] is not None
                                               and rec["read"] >= 0)
    res: dict[str, list[int]] = {}
    for k, rec in first.items():
        if k in bull or "img_dir" not in rec:
            continue
        r = res.setdefault(rec["img_dir"], [0, 0])
        r[0] += 1
        r[1] += 0 if anyread[k] else 1
    return res


def page_neighbour_summary(log: list, bull: set) -> dict[str, Any]:
    """The same blocks classed by their PAGE relation to the nearest
    bullseye (Chebyshev distance 1), whichever seed's walk reached them."""
    first: dict[tuple[int, int], dict] = {}
    anyread: dict[tuple[int, int], bool] = {}
    for rec in log:
        if "refined" not in rec or "block" not in rec:
            continue
        if not any(rec["key"][1:]):
            continue
        k = tuple(rec["block"])
        if "bits" in rec and rec.get("true_chunk") is None:
            continue
        first.setdefault(k, rec)
        anyread[k] = anyread.get(k, False) or (rec["read"] is not None
                                               and rec["read"] >= 0)
    res: dict[str, list[int]] = {}
    for (R, C), rec in first.items():
        if (R, C) in bull:
            continue
        cl = "far"
        for (bR, bC) in bull:
            d = (R - bR, C - bC)
            if max(abs(d[0]), abs(d[1])) == 1:
                cl = DIAG.get(d, "axial")
        r = res.setdefault(cl, [0, 0])
        r[0] += 1
        r[1] += 0 if anyread[R, C] else 1
    return res


# ------------------------------------------------------------------ run --

def load_capture(R_: dict[str, Any], path: str, kind: str
                 ) -> tuple[np.ndarray | None, str]:
    """Sets R_['h'], R_['j'], R_['z'] exactly as ld would; a .pbm is
    converted to the P5 bytes a P5 file of it would carry (ink 0, paper
    255) and that P5 written beside the outputs for the plain reader."""
    if path.endswith(".pbm"):
        raw = open(path, "rb").read()
        parts = raw.split(b"\n", 2)
        w, h = map(int, parts[1].split())
        bits = np.unpackbits(np.frombuffer(parts[2], dtype=np.uint8))
        bits = bits.reshape(h, -1)[:, :w]
        img = np.where(bits == 1, 0, 255).astype(np.uint8)
        R_["h"], R_["j"], R_["z"] = w, h, img.tobytes()
        return img, "pbm->P5"
    R_["h"], R_["j"], R_["z"] = R_["ld"](path)
    if kind == "grid":
        return None, "grid"
    img = np.frombuffer(R_["z"], dtype=np.uint8).reshape(R_["j"], R_["h"])
    return img, "P5"


def main_run(a: argparse.Namespace) -> None:
    R_ = load_reader()
    page = json.load(open(a.page))
    grid = open(a.grid).read().split()
    truth = Truth(page, grid)
    t0 = time.time()
    img, fmt = load_capture(R_, a.capture, a.kind)
    rot = np.eye(3)
    if a.rot90:
        # quarter turns clockwise of the frame the reader sees (camera.py's
        # rot90_cw: pixel (u, v) -> (h - v, u) per turn); truth composes it
        im = np.frombuffer(R_["z"], dtype=np.uint8).reshape(R_["j"], R_["h"])
        for _ in range(a.rot90 % 4):
            hh = im.shape[0]
            rot = np.array([[0, -1, hh], [1, 0, 0], [0, 0, 1]], float) @ rot
            im = np.rot90(im, -1)
        im = np.ascontiguousarray(im)
        R_["h"], R_["j"], R_["z"] = im.shape[1], im.shape[0], im.tobytes()
        img = im
    t_load = time.time() - t0
    t1 = time.time()
    R_["e"] = b""
    o, e, fm_cand = fm_logged(R_, a.fm_rule)
    if a.fm_rule == "reader" and a.ft_rule == "reader":
        R_["e"] = b""
        assert (o, e) == R_["fm"](), "fm_logged diverged from the reader"
    R_["e"] = e
    t_fm = time.time() - t1
    seeds = [list(s) for s in o[1]]
    log: list = []
    t2 = time.time()
    chunks = (wk_logged(R_, o[0], [list(s) for s in o[1]], log, a.ft_rule)
              if e else [])
    t_wk = time.time() - t2
    md = page["module_dots"]
    if a.kind == "render":
        cam = json.load(open(a.sidecar))
        Hd = np.array(cam["homography_page_dots_to_px"], float)
        g2d = np.array([[md, 0, page["x0_dots"]], [0, md, page["y0_dots"]],
                        [0, 0, 1]], float)
        truth.set_h(rot @ Hd @ g2d)
    elif a.kind == "raster":
        truth.set_h(rot @ np.array([[md, 0, page["x0_dots"]],
                                    [0, md, page["y0_dots"]], [0, 0, 1]],
                                   float))
    elif a.kind == "grid":
        truth.set_h(rot @ np.array([[3, 0, 12], [0, 3, 12], [0, 0, 1]],
                                   float))
    # image-frame direction of every diagonal key, from its seed's axes
    for rec in log:
        q, ka, kb = rec["key"]
        if (ka, kb) in DIAG:
            A, B = seeds[q][2], seeds[q][3]
            dx, dy = kb * A[0] + ka * B[0], kb * A[1] + ka * B[1]
            rec["img_dir"] = (("up" if dy < 0 else "down") + "-"
                              + ("left" if dx < 0 else "right"))
    slot_of_chunk: dict[int, list[tuple[int, int]]] = {}
    chunk_at: dict[tuple[int, int], int] = {}
    for blk, ch in zip(page["slot_block"], page["slot_chunk"]):
        if ch is None or ch < 0:
            continue
        slot_of_chunk.setdefault(ch, []).append(tuple(blk))
        chunk_at[tuple(blk)] = ch
    sb = seed_blocks(page, log, slot_of_chunk, len(seeds))
    genie_stats = None
    genie_check = None
    if a.kind == "photo" or a.genie:
        bpos = {tuple(bz["block"]): bz for bz in page["bullseyes"]}
        src, dst = [], []
        for q, blk in sb.items():
            src.append(truth.centre_cm(*blk))
            dst.append([seeds[q][0] / 16.0 + 0.5, seeds[q][1] / 16.0 + 0.5])
        Hb = dlt(np.array(src), np.array(dst))
        if a.kind == "photo":
            truth.set_h(Hb)
            genie_stats = genie_fit(truth, img)
        else:
            # validation: genie on a render, seeded by the bullseye
            # homography, compared with the recorded warp
            gt = Truth(page, grid)
            gt.set_h(Hb)
            genie_stats = genie_fit(gt, img)
            ce, ae = [], []
            for (Rr, Cc), (c0, J) in gt.blocks.items():
                tc, tJ = truth.frame(Rr, Cc)
                ce.append(float(np.hypot(*(np.linalg.inv(tJ) @ (c0 - tc)))))
                ae.append(float(max(np.linalg.norm(J[:, k] - tJ[:, k])
                                    / np.linalg.norm(tJ[:, k])
                                    for k in (0, 1))))
            genie_check = dict(blocks=len(ce),
                               centre_err_mod_median=float(np.median(ce)),
                               centre_err_mod_max=float(np.max(ce)),
                               axis_err_median=float(np.median(ae)),
                               axis_err_max=float(np.max(ae)))
    analyse(truth, R_, log, sb, chunk_at)
    bull = {tuple(bz["block"]) for bz in page["bullseyes"]}
    summ = summarize(log, bull)
    pn = page_neighbour_summary(log, bull)
    px_mod = None
    js = [np.sqrt(abs(np.linalg.det(fr_[1]))) / 16.0
          for fr_ in (truth.frame(Rr, Cc) for Rr in range(page["BH"])
                      for Cc in range(page["BW"])) if fr_ is not None]
    if js:
        px_mod = [float(np.min(js)), float(np.median(js)), float(np.max(js))]
    visited = {tuple(r["block"]) for r in log
               if "refined" in r and "block" in r}
    out = dict(capture=a.capture, name=a.name, kind=a.kind, fmt=fmt,
               size=[R_["h"], R_["j"]], bullseyes=len(seeds),
               pitch_p=o[0], header=e.hex() if e else None,
               accepted_blocks=len(chunks),
               chunks_distinct=len({int.from_bytes(x[:2], "big")
                                    for x in chunks}),
               seeds_block={str(k): v for k, v in sb.items()},
               seeds=[[s[0], s[1], s[2], s[3], s[4]] for s in seeds],
               px_per_module_min_med_max=px_mod,
               walls_s=dict(load=t_load, fm=t_fm, wk_logged=t_wk),
               rot90=a.rot90, ft_rule=a.ft_rule, fm_rule=a.fm_rule,
               fm_scores=sorted(fm_cand, reverse=True)[:12],
               img_diag=img_diag_summary(log, bull),
               genie=genie_stats, genie_check=genie_check,
               page_blocks_not_visited=sorted(
                   [list(k) for k in ((Rr, Cc) for Rr in range(page["BH"])
                                      for Cc in range(page["BW"]))
                    if k not in visited and k not in bull]),
               summary=summ, page_neighbour=pn, log=log)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, a.name + ".json")
    with open(fn, "w") as fo:
        json.dump(out, fo, default=lambda x: x if not isinstance(
            x, np.generic) else x.item())
    print(f"{a.name}: {len(seeds)} bullseyes, {len(chunks)} blocks accepted,"
          f" chunks {out['chunks_distinct']}; seeds placed {len(sb)};"
          f" px/module {px_mod}; walls fm {t_fm:.1f}s wk {t_wk:.1f}s"
          f" -> {fn}")


def fmt(x: float | None, nd: int = 2) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.2f}"


def tie_stats(log: list) -> tuple[int, int, int]:
    """(ft calls, calls with a tie at any stage, calls with a tie at the
    last stage) over processed non-seed visits."""
    n = t_any = t_last = 0
    for rec in log:
        if "ft" not in rec:
            continue
        n += 1
        t_any += any(st[2] > 1 for st in rec["ft"])
        t_last += rec["ft"][-1][2] > 1
    return n, t_any, t_last


def main_table(a: argparse.Namespace) -> None:
    print("| capture | class | blocks | read | unread, sound | unread |"
          " misread cells mean / max | misread of unread mean / max |"
          " far corner mean / max (mod) | learned A err mean / max (%) |"
          " learned B err mean / max (%) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for fn in a.files:
        d = json.load(open(fn))
        for cl in CLASSES + ("ALL",):
            r = d["summary"][cl]
            if not r["blocks"]:
                continue
            print(f"| {d['name']} | {cl} | {r['blocks']} | {r['read']} |"
                  f" {r['unread_sound']} | {r['unread']} |"
                  f" {fmt(r['mis_mean'])} / {fmt(r['mis_max'], 0)} |"
                  f" {fmt(r['unread_mis_mean'])} /"
                  f" {fmt(r['unread_mis_max'], 0)} |"
                  f" {fmt(r['far_mean'])} / {fmt(r['far_max'])} |"
                  f" {pct(r['axA_mean'])} / {pct(r['axA_max'])} |"
                  f" {pct(r['axB_mean'])} / {pct(r['axB_max'])} |")
    print()
    print("| capture | accepted | chunks | unread diagonals by walk key"
          " UL/UR/DL/DR | by page relation UL/UR/DL/DR | by image direction"
          " UL/UR/DL/DR | fm rotation r (ties) | ft calls tied any / last"
          " stage | not visited |")
    print("|---|---|---|---|---|---|---|---|---|")
    order = ("up-left", "up-right", "down-left", "down-right")
    for fn in a.files:
        d = json.load(open(fn))
        S = d["summary"]
        key = "/".join(str(S[c]["unread"]) for c in order)
        pg = "/".join(str(d["page_neighbour"].get(c, [0, 0])[1])
                      for c in order)
        im = "/".join(str(d["img_diag"].get(c, [0, 0])[1]) for c in order)
        top = d["fm_scores"][0]
        nt = sum(1 for x in d["fm_scores"] if x[0] == top[0])
        n, ta, tl = tie_stats(d["log"])
        print(f"| {d['name']} | {d['accepted_blocks']} |"
              f" {d['chunks_distinct']} | {key} | {pg} | {im} |"
              f" {top[1]} ({nt}) | {ta} / {tl} of {n} |"
              f" {len(d['page_blocks_not_visited'])} |")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("capture")
    r.add_argument("--page", required=True)
    r.add_argument("--grid", required=True)
    r.add_argument("--kind", required=True,
                   choices=("render", "raster", "grid", "photo"))
    r.add_argument("--sidecar")
    r.add_argument("--name", required=True)
    r.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(HERE)), "build", "axes", "diag"))
    r.add_argument("--rot90", type=int, default=0,
                   help="turn the frame K quarter turns clockwise first")
    r.add_argument("--ft-rule", default="reader", choices=("reader", "centre"),
                   help="COUNTERFACTUAL tie rule in ft (default: the reader)")
    r.add_argument("--fm-rule", default="reader", choices=("reader", "r0"),
                   help="COUNTERFACTUAL tie rule in fm (default: the reader)")
    r.add_argument("--genie", action="store_true",
                   help="on a render: also fit the photo truth and compare")
    t = sub.add_parser("table")
    t.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        main_run(a)
    else:
        main_table(a)


if __name__ == "__main__":
    main()

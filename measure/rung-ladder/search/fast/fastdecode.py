# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/fastdecode.py
"""Batched, bit-exact re-implementation of the production hybrid LDPC decode
(src/holo/core/ldpc/decode.py: _run / _bp_loop) for the rung-ladder search.

    decode_batch(llrs (B, n) float64, code: construct.Code,
                 max_iters=60, alpha=0.8, return_extrinsic=False)
        -> ok (B,) bool, hard (B, n) uint8, n_iters (B,) int64
           [, extrinsic (B, n) float64 == production decode_soft's 4th output]

Same numerics, same schedule, B trials at once:
  * channel LLRs clipped to +-20, +-inf -> +-1e9, negated (internal: + = bit 0);
  * normalized min-sum (alpha) flooding loop, early exit on zero syndrome,
    hard = Ltot < 0, n_iters = the iteration index at which the loop broke
    (0 when the channel hard decisions already satisfy every check,
    max_iters when the budget ran out) -- production's break rule;
  * rows whose min-sum pass failed get ONE exact sum-product pass from the
    channel LLRs (skipped when max_iters == 0, as production), n_iters summed.

Per-row early exit: a row whose syndrome is zero is RECORDED at that
iteration (hard, n_iters, beliefs) and DROPPED from the active set (row
compaction); the batch keeps iterating on the remaining rows only.

Two kernels, both verified bit for bit against production (ok, hard,
n_iters AND the extrinsic array's bytes) by test_fastdecode.py:
  decode_batch         the fast one: edge-major, degree-grouped slot layout
                       (see the "dense kernel" comment below);
  decode_batch_simple  the straight transcription (reduceat on production's
                       edge order along axis=1 of (rows, E)); kept as the
                       second witness.  Its two value-identical rewrites:
                       x[chk] gathers of per-check values -> np.repeat
                       (edge_chk is sorted), n_neg & 1 -> bitwise_xor.reduceat
                       of the uint8 sign mask.

Thread safety: reads only the (frozen, never mutated) Code arrays; every
work buffer is local to the call; the per-code derived layouts live in a
small lock-guarded cache (at most _CACHE_MAX codes per process -- the search
registers many codes per worker).  No RNG.
"""
from __future__ import annotations

import threading

import numpy as np

from holo.core.ldpc.construct import Code

_CACHE_MAX = 8                 # derived per-code layouts kept per process
_CACHE_LOCK = threading.Lock()


def _cached(cache: dict, code: Code, build):
    """Bounded per-process cache keyed by id(code), guarded against id reuse
    (the entry holds the code) and against concurrent mutation (lock; the
    build itself runs outside it -- two threads may build the same value,
    which is harmless)."""
    v = cache.get(id(code))
    if v is not None and v[0] is code:
        return v[1]
    val = build(code)
    with _CACHE_LOCK:
        while len(cache) >= _CACHE_MAX:
            cache.pop(next(iter(cache)))
        cache[id(code)] = (code, val)
    return val

LLR_KNOWN = 1e9
LLR_CLIP = 20.0

_GEOM: dict[int, tuple] = {}
_LAYOUTS: dict[int, tuple] = {}


def _build_geom(code: Code) -> tuple:
    chk = code.edge_chk
    E = int(chk.size)
    m = int(code.chk_starts.size)
    chk_counts = np.diff(np.r_[code.chk_starts, E]).astype(np.int64)
    return (code, np.ascontiguousarray(code.edge_var.astype(np.intp)),
            code.chk_starts, chk_counts, code.var_order.astype(np.intp),
            code.var_starts, E, m, np.arange(E, dtype=np.int64))


def _geom(code: Code) -> tuple:
    """Per-code derived index arrays for the simple kernel (Code is frozen)."""
    return _cached(_GEOM, code, _build_geom)


def _channel(llrs: np.ndarray, n: int) -> np.ndarray:
    x = np.asarray(llrs, np.float64)
    if x.ndim == 1:
        x = x[None, :]
    if x.ndim != 2 or x.shape[1] != n:
        raise ValueError(f"llrs must be (B, {n}), got {x.shape}")
    L = np.clip(x, -LLR_CLIP, LLR_CLIP)
    L[np.isposinf(x)] = LLR_KNOWN
    L[np.isneginf(x)] = -LLR_KNOWN
    return -L


def _loop(L: np.ndarray, code: Code, max_iters: int, alpha: float,
          sum_product: bool, want_tot: bool):
    """Batched _bp_loop.  L: (B, n) internal convention.  Returns
    (ok (B,) bool, hard (B, n) uint8, n_iters (B,) int64, Ltot (B, n)|None)."""
    _, var, cs, cc, vo, vs, E, m, epos = _geom(code)
    B, n = L.shape
    ok = np.zeros(B, bool)
    hard_out = np.empty((B, n), np.uint8)
    nit = np.zeros(B, np.int64)
    tot_out = np.empty((B, n)) if want_tot else None
    act = np.arange(B)
    Lc = L                      # channel LLRs of the active rows
    Ltot = L.copy()
    c2v = np.zeros((B, E))
    for it in range(max_iters + 1):
        neg = Ltot < 0
        hard = neg.view(np.uint8)
        syn = np.bitwise_xor.reduceat(hard.take(var, axis=1), cs, axis=1)
        done = ~syn.any(axis=1)
        last = it == max_iters
        if done.any() or last:
            fin = np.ones_like(done) if last else done
            rows = act[fin]
            ok[rows] = done[fin]
            hard_out[rows] = hard[fin]
            nit[rows] = it
            if want_tot:
                tot_out[rows] = Ltot[fin]
            if last:
                break
            keep = ~done
            if not keep.any():
                break
            act = act[keep]
            Lc = Lc[keep]
            Ltot = Ltot[keep]
            c2v = c2v[keep]
        v2c = Ltot.take(var, axis=1) - c2v
        vneg = v2c < 0
        par = np.bitwise_xor.reduceat(vneg.view(np.uint8), cs, axis=1)
        par_sign = 1.0 - 2.0 * par.astype(np.int64)
        sgn = np.where(vneg, -1.0, 1.0)
        ps_e = np.repeat(par_sign, cc, axis=1)
        if sum_product:
            t = np.abs(np.tanh(np.clip(v2c, -40.0, 40.0) / 2.0))
            lt = np.log(np.clip(t, 1e-300, 1.0))
            lsum = np.add.reduceat(lt, cs, axis=1)
            ext = np.exp(np.clip(np.repeat(lsum, cc, axis=1) - lt,
                                 -700.0, -1e-16))
            c2v = 2.0 * np.arctanh(np.clip(ps_e * sgn * ext,
                                           -0.999_999_999_999,
                                           0.999_999_999_999))
        else:
            mag = np.abs(v2c)
            min1 = np.minimum.reduceat(mag, cs, axis=1)
            min1_e = np.repeat(min1, cc, axis=1)
            pos_m = np.where(mag == min1_e, epos, E)
            first = np.minimum.reduceat(pos_m, cs, axis=1)
            mag2 = mag           # mag is dead after this point: reuse
            np.put_along_axis(mag2, first, np.inf, axis=1)
            min2 = np.minimum.reduceat(mag2, cs, axis=1)
            is_first = epos == np.repeat(first, cc, axis=1)
            ext = np.where(is_first, np.repeat(min2, cc, axis=1), min1_e)
            c2v = alpha * ps_e * sgn * ext
        Ltot = Lc + np.add.reduceat(c2v.take(vo, axis=1), vs, axis=1)
    return ok, hard_out, nit, tot_out


def decode_batch_simple(llrs: np.ndarray, code: Code, max_iters: int = 60,
                 alpha: float = 0.8, return_extrinsic: bool = False):
    """Batched production decode, straight transcription (reduceat on the
    production edge order).  Kept as the second witness for the dense
    kernel; see the module docstring."""
    n = int(code.spec.n_bits)
    L = _channel(llrs, n)
    ok, hard, nit, tot = _loop(L, code, max_iters, alpha, False,
                               return_extrinsic)
    fail = np.flatnonzero(~ok)
    if fail.size and max_iters > 0:
        ok2, hard2, n2, tot2 = _loop(L[fail], code, max_iters, alpha, True,
                                     return_extrinsic)
        ok[fail] = ok2
        hard[fail] = hard2
        nit[fail] += n2
        if return_extrinsic:
            tot[fail] = tot2
    if return_extrinsic:
        return ok, hard, nit, L - tot
    return ok, hard, nit


# ============================================================== dense kernel
# The same arithmetic on a DEGREE-GROUPED SLOT LAYOUT: checks of equal degree
# d form a block (rows, d, m_d) whose slot j holds each check's j-th edge in
# production order; variables likewise by degree.  Per-check / per-variable
# reductions become d elementwise vector ops over contiguous slot vectors
# instead of one reduceat inner-loop call per segment.  Exactness:
#   * min / first-argmin / min-excluding-first / XOR parity are exact in any
#     order (min-sum: streaming top-2 per check, strict < keeps the FIRST
#     minimum position as production's pos_m/first does; min2 = min over
#     the others = production's mag2[first] = inf trick);
#   * the two FLOAT sums (sum-product log-sum per check, belief sum per
#     variable) reproduce numpy's reduceat order exactly: out = x0 +
#     pairwise_sum(x1..x_{d-1}), where pairwise_sum of c < 8 terms is the
#     sequential sum from -0.0 and of 8 <= c <= 128 terms is numpy's
#     8-accumulator block ((r0+r1)+(r2+r3))+((r4+r5)+(r6+r7)) + tail
#     (_seg_sum; the model is checked against np.add.reduceat itself in
#     test_fastdecode.py, bit for bit, signed zeros included -- this is a
#     property of numpy's add loop, re-run the test on any numpy upgrade);
#   * every elementwise expression is production's, in production's operand
#     order.


class _Layout:
    __slots__ = ("code", "E", "n", "cgroups", "vgroups", "g1", "g2", "qpos")

    def __init__(self, code: Code) -> None:
        E = int(code.edge_chk.size)
        n = int(code.var_starts.size)
        cs = code.chk_starts.astype(np.intp)
        cc = np.diff(np.r_[cs, E])
        cl_edge = np.empty(E, np.intp)
        cgroups = []
        off = 0
        for d in np.unique(cc):
            d = int(d)
            C = np.flatnonzero(cc == d)
            md = int(C.size)
            for j in range(d):
                cl_edge[off + j * md: off + (j + 1) * md] = cs[C] + j
            cgroups.append((d, off, md))
            off += d * md
        vs = code.var_starts.astype(np.intp)
        vo = code.var_order.astype(np.intp)
        vc = np.diff(np.r_[vs, E])
        vl_edge = np.empty(E, np.intp)
        vgroups, perm = [], []
        voff = qoff = 0
        for d in np.unique(vc):
            d = int(d)
            V = np.flatnonzero(vc == d)
            nd = int(V.size)
            for j in range(d):
                vl_edge[voff + j * nd: voff + (j + 1) * nd] = vo[vs[V] + j]
            vgroups.append((d, voff, nd, qoff))
            perm.append(V)
            voff += d * nd
            qoff += nd
        vperm = np.concatenate(perm)
        qpos = np.empty(n, np.intp)
        qpos[vperm] = np.arange(n)
        inv_cl = np.empty(E, np.intp)
        inv_cl[cl_edge] = np.arange(E)
        self.code, self.E, self.n = code, E, n
        self.cgroups, self.vgroups = cgroups, vgroups
        self.g1 = qpos[code.edge_var.astype(np.intp)[cl_edge]]
        self.g2 = inv_cl[vl_edge]
        self.qpos = qpos


def _layout(code: Code) -> _Layout:
    return _cached(_LAYOUTS, code, _Layout)


# Storage is EDGE-MAJOR: arrays are (E, rows) / (n, rows), so a group block
# is a contiguous (d, w, rows) array, every gather copies contiguous
# row-vectors (np.take along axis 0: ~0.5 ns/elem vs ~2.5 ns for a
# (rows, E) take along axis 1), and per-slot ops run over contiguous
# (w, rows) planes.  (A row-major variant of the same slot kernel measured
# 1.2-1.4x over production against this layout's 1.6-1.9x; not kept.)


def _seg_sum(X: np.ndarray, d: int) -> np.ndarray:
    """numpy reduceat's float-add order over the LEADING slot axis of
    X (d, w, rows): x0 + pairwise_sum(x1..x_{d-1})."""
    if d == 1:
        return X[0].copy()
    c = d - 1
    if c < 8:
        acc = X[1].copy()
        for j in range(2, d):
            acc += X[j]
    else:
        r = [X[1 + j].copy() for j in range(8)]
        i = 8
        while i < c - (c % 8):
            for j in range(8):
                r[j] += X[1 + i + j]
            i += 8
        acc = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
        while i < c:
            acc += X[1 + i]
            i += 1
    return X[0] + acc


class _Work:
    """Flat scratch buffers; buf(name, rows) is a C-contiguous (E, rows)
    view of the first E*rows elements, valid for any rows <= capacity."""

    def __init__(self, E: int, B: int) -> None:
        self.E, self.B = E, B
        self.f = {k: np.empty(E * B) for k in ("le", "v", "sg", "a", "b", "cl", "c2v", "c2w")}
        self.ng = np.empty(E * B, bool)

    def buf(self, name: str, rows: int) -> np.ndarray:
        return self.f[name][: self.E * rows].reshape(self.E, rows)


def _loop_dense(L: np.ndarray, lay: _Layout, max_iters: int, alpha: float,
                sum_product: bool, want_tot: bool):
    E, n, qpos = lay.E, lay.n, lay.qpos
    g1, g2 = lay.g1, lay.g2
    cg = [(d, slice(off, off + d * md), md, np.arange(d, dtype=np.int8)[:, None, None])
          for d, off, md in lay.cgroups]
    vg = [(d, slice(voff, voff + d * nd), nd, slice(qoff, qoff + nd))
          for d, voff, nd, qoff in lay.vgroups]
    B = L.shape[0]
    ok = np.zeros(B, bool)
    hard_out = np.empty((B, n), np.uint8)
    nit = np.zeros(B, np.int64)
    tot_out = np.empty((B, n)) if want_tot else None
    act = np.arange(B)
    W = _Work(E, B)
    Lp = np.ascontiguousarray(L[:, np.argsort(qpos)].T)   # (n, B) permuted
    Ltot = Lp.copy()
    c2v = W.buf("c2v", B)
    c2v[:] = 0.0
    spare = "c2w"
    for it in range(max_iters + 1):
        Ba = act.size
        le = np.take(Ltot, g1, axis=0, out=W.buf("le", Ba))  # (E, Ba)
        ng = W.ng[: E * Ba].reshape(E, Ba)
        np.less(le, 0.0, out=ng)
        bad = np.zeros(Ba, bool)
        for d, sl, md, _ in cg:
            bad |= np.bitwise_xor.reduce(ng[sl].reshape(d, md, Ba), axis=0).any(axis=0)
        done = ~bad
        last = it == max_iters
        if done.any() or last:
            fin = np.ones_like(done) if last else done
            rows = act[fin]
            tp = Ltot[:, fin][qpos].T
            ok[rows] = done[fin]
            hard_out[rows] = tp < 0
            nit[rows] = it
            if want_tot:
                tot_out[rows] = tp
            if last:
                break
            keep = np.flatnonzero(~done)
            if keep.size == 0:
                break
            act = act[keep]
            Ba = act.size
            Lp = np.ascontiguousarray(Lp[:, keep])
            Ltot = np.ascontiguousarray(Ltot[:, keep])
            nc = W.buf(spare, Ba)
            np.take(c2v, keep, axis=1, out=nc)
            spare = "c2v" if spare == "c2w" else "c2w"
            c2v = nc
            le = np.take(Ltot, g1, axis=0, out=W.buf("le", Ba))
            ng = W.ng[: E * Ba].reshape(E, Ba)
        vc = np.subtract(le, c2v, out=W.buf("v", Ba))
        np.less(vc, 0.0, out=ng)
        sgn = W.buf("sg", Ba)                     # == np.where(ng, -1.0, 1.0)
        sgn.fill(1.0)
        np.copyto(sgn, -1.0, where=ng)
        if sum_product:
            T = W.buf("a", Ba)                    # t, then lt
            np.clip(vc, -40.0, 40.0, out=T)
            np.divide(T, 2.0, out=T)
            np.tanh(T, out=T)
            np.abs(T, out=T)
            np.clip(T, 1e-300, 1.0, out=T)
            np.log(T, out=T)
            X = W.buf("b", Ba)                    # lsum[chk] - lt, then ext
            PS = W.buf("cl", Ba)                  # par_sign[chk]
            for d, sl, md, _ in cg:
                LT = T[sl].reshape(d, md, Ba)
                lsum = _seg_sum(LT, d)
                np.subtract(lsum[None], LT, out=X[sl].reshape(d, md, Ba))
                par = np.bitwise_xor.reduce(ng[sl].reshape(d, md, Ba), axis=0)
                PS[sl].reshape(d, md, Ba)[:] = (1.0 - 2.0 * par.astype(np.int64))[None]
            np.clip(X, -700.0, -1e-16, out=X)
            np.exp(X, out=X)
            np.multiply(PS, sgn, out=PS)
            np.multiply(PS, X, out=PS)
            np.clip(PS, -0.999_999_999_999, 0.999_999_999_999, out=PS)
            np.arctanh(PS, out=PS)
            np.multiply(2.0, PS, out=c2v)
        else:
            mag = np.abs(vc, out=W.buf("a", Ba))
            for d, sl, md, jj in cg:
                M = mag[sl].reshape(d, md, Ba)
                m1 = M[0].copy()
                m2 = np.full_like(m1, np.inf)
                idx = np.zeros(m1.shape, np.int8)
                for j in range(1, d):
                    x = M[j]
                    np.minimum(m2, np.maximum(m1, x), out=m2)
                    np.copyto(idx, jj[j, 0, 0], where=x < m1)
                    np.minimum(m1, x, out=m1)
                par = np.bitwise_xor.reduce(ng[sl].reshape(d, md, Ba), axis=0)
                a = alpha * (1.0 - 2.0 * par.astype(np.int64))
                ext = np.where(idx[None] == jj, m2[None], m1[None])
                C = c2v[sl].reshape(d, md, Ba)
                np.multiply(a[None], sgn[sl].reshape(d, md, Ba), out=C)
                np.multiply(C, ext, out=C)
        cl = np.take(c2v, g2, axis=0, out=W.buf("cl", Ba))
        for d, sl, nd, qs in vg:
            s = _seg_sum(cl[sl].reshape(d, nd, Ba), d)
            np.add(Lp[qs], s, out=Ltot[qs])
    return ok, hard_out, nit, tot_out


def decode_batch(llrs: np.ndarray, code: Code, max_iters: int = 60,
                 alpha: float = 0.8, return_extrinsic: bool = False):
    """Batched production decode (edge-major dense slot kernel).  llrs in the
    HOUSE convention (positive = bit 1; 0.0 = erasure; +-inf = known),
    shape (B, n) or (n,).  Returns ok (B,) bool, hard (B, n) uint8,
    n_iters (B,) int64 [, extrinsic (B, n) float64 == decode_soft's]."""
    lay = _layout(code)
    L = _channel(llrs, lay.n)
    ok, hard, nit, tot = _loop_dense(L, lay, max_iters, alpha, False,
                                 return_extrinsic)
    fail = np.flatnonzero(~ok)
    if fail.size and max_iters > 0:
        ok2, hard2, n2, tot2 = _loop_dense(L[fail], lay, max_iters, alpha,
                                       True, return_extrinsic)
        ok[fail] = ok2
        hard[fail] = hard2
        nit[fail] += n2
        if return_extrinsic:
            tot[fail] = tot2
    if return_extrinsic:
        return ok, hard, nit, L - tot
    return ok, hard, nit


def selfcheck(rid: str, n: int = 24, seed: int = 0) -> bool:
    """Cheap start-up guard for a driver: n BIAWGN trials near threshold
    (mixed min-sum / sum-product / converged outcomes) decoded by production
    decode() and by decode_batch; True iff (ok, hard, n_iters) all agree.
    Not a substitute for test_fastdecode.py after a numpy change."""
    from holo.core.ldpc import construct
    from holo.core.ldpc.decode import decode, encode
    code = construct.load_code(rid)
    k, N = code.spec.k_bits, code.spec.n_bits
    g = np.random.default_rng(seed)
    X = np.empty((n, N))
    for i in range(n):
        s = (0.75, 0.9, 1.05)[i % 3] * (1.0 if k >= 2000 else 1.12)
        cw = encode(g.integers(0, 2, k).astype(np.uint8), rid)
        X[i] = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
    ok, hard, nit = decode_batch(X, code)
    for i in range(n):
        r_ok, r_hard, r_n = decode(X[i], rid)
        if bool(ok[i]) != r_ok or int(nit[i]) != r_n or not np.array_equal(hard[i], r_hard):
            return False
    return True

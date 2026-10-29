# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/variants.py
"""Tier B2: inner-code constructions BEYOND the plain e-IRA (scratch; nothing here is a format row).

Every construction below keeps n_TRANSMITTED = 4096 (one 64x64 tile), Z = 64 QC blocks in the
information part, a linear-time encoder (back-substitutions only), girth > 4 on the WHOLE decoding
graph, and is decoded by the PRODUCTION decoder (holo.core.ldpc.decode: normalized min-sum 0.8,
60 iterations, one sum-product retry) after registering it as a construct.Code.  The OUTER draw is
Tier A's generalized e-IRA draw (common.draw / common.expand) for a common.Cfg `outer` — the SAME
seed label b"search/<outer.tag>/<seed>" and restart stream, so a variant built on a Tier-A config
and seed has, restart for restart, the IDENTICAL outer graph as the plain e-IRA code of that name:
every variant-vs-plain comparison is PAIRED on the outer draw (common random numbers on top).

Notation (as paperholo.ldpc's docstring): k info bits u, kb = k/Z info block-columns, m = 4096 - k
transmitted parity bits, mb = m/Z block rows, pi = the outer draw's IRA row interleaver, H_d the
outer QC info part (block-column c: d_c distinct block rows r, each an I(s); edge (pi[r*Z + a],
c*Z + (a + s) mod Z)); circulant convention I(s)[a, b] = 1 iff b == (a + s) mod Z.

-----------------------------------------------------------------------------------------------
(i) ARA — PRECODED e-IRA (accumulate-repeat-accumulate), variant "ara", knobs (pre_frac, pre_sel)

  P = round(pre_frac * kb) info block-columns are PRECODED: pre_sel = "heavy" takes columns
  0..P-1 (the recipe puts heavy columns FIRST), "light" takes columns kb-P..kb-1.  Their KP = 64*P
  bits, in ascending bit order sel[0] < sel[1] < ... < sel[KP-1], form ONE accumulator chain:
      v_0 = u_sel[0],   v_i = v_{i-1} XOR u_sel[i]            (rate-1 1/(1+D) precoder)
  The outer code H_d sees v in place of u on the precoded columns (unprecoded columns: u itself).
  The TRANSMITTED systematic bits are the ORIGINAL u; v is PUNCTURED (never transmitted).

  Mother graph, n = 4096 + KP variables, 4096 - k + KP checks:
      variables  0 .. k-1          u   (transmitted; a precoded u has degree 1)
                 k .. 4095         parity p (transmitted; the recipe's bit-serial accumulator)
                 4096 .. 4096+KP-1 v   (PUNCTURED: channel LLR 0 at the decoder)
      checks     0 .. m-1          outer checks = the plain e-IRA's checks with every H_d edge of a
                                   precoded bit sel[i] moved from u_sel[i] to v_i
                 m + i, 0<=i<KP    precoder check  u_sel[i] + v_i + v_{i-1}   (i = 0: u_sel[0] + v_0)
  Encoder (linear time): v = cumulative XOR of u[sel]; u' = u with u'[sel] = v; s = pi(H_d) @ u';
  p = cumulative XOR of s; codeword (mother) = [u | p | v]; transmitted = its first 4096 bits.
  Build: outer restart R as Tier A (rule (e) info-free-block-row restarts included), then the
  mother graph is assembled deterministically; girth <= 4 on the mother graph -> next restart.

(ii) IRAA — DOUBLY-ACCUMULATED parity, variant "iraa", knob iraa_frac

  m2b = round(iraa_frac * mb) block rows' worth of parity become SECOND-accumulator outputs q;
  m1 = m - 64*m2b first-accumulator outputs p.  Check split in NATURAL (chain) order:
  C1 = checks 0..m1-1, C2 = checks m1..m-1.  H_d's taps (through pi) land on all m checks as in
  the plain draw (so rule (e)/balanced placement still covers every pi-block row).
      C1 check j:        taps_j + p_j + p_{j-1}                    (j = 0: taps_0 + p_0)
      C2 check m1+i:     taps_{m1+i} + q_i + q_{i-1} + sum{ p_j : link(j) = i }   (i = 0: no q_{-1})
  The link L (every p bit feeds exactly ONE C2 check -> p has degree 3, q degree 2) is block-QC
  under a second interleaver pi2 (a permutation of the m2 C2 checks):
      p block b (bits b*Z + a, b < m1/Z) -> C2 local check pi2[r_b*Z + (a + s_b) mod Z],
      r_b = the b-th entry of a Fisher-Yates-shuffled list [b mod m2b for b in 0..m1/Z-1]
      (balanced: every C2 block row receives floor/ceil(m1b/m2b) p blocks), s_b uniform in [0, Z).
  L draws from g = modulation.rng(outer seed label, b"iraa-L/restart<R>/try<T>"), in order:
  pi2 = Fisher-Yates(g, m2), the shuffle of the r list, then shifts = g.integers(0, Z, m1b);
  tries T = 0..63 until the mother graph has girth > 4, then the next outer restart.
  iraa_links = "one" (suffix x1): only m2b p blocks are linked, block floor(i*m1b/m2b) for
  i = 0..m2b-1, so each C2 block row receives exactly one p block (unlinked p keep degree 2);
  "all" = every p block linked (at iraa_frac 0.5 the two coincide up to the r shuffle).
  Variables: u 0..k-1, p k..k+m1-1, q k+m1..4095 — all transmitted (n = 4096, no puncturing).
  Encoder (two back-substitutions): s = pi(H_d) @ u; p = cumulative XOR of s[:m1];
  t = s[m1:] XOR L p; q = cumulative XOR of t.

  NOTE: the outer draw's rule (b) (tap-gap weight floor) is computed, as in Tier A, over ONE chain
  of length m; for IRAA it is only the draw's proxy.  The screen-0 audit measures the TRUE minimum
  single- and two-info-bit transmitted weights of every built code from its own encoder.
-----------------------------------------------------------------------------------------------

Audit adapted to punctured nodes (screen0_v): girth on the mother graph (H H^T off-diagonal <= 1);
encoder verified (H c == 0 on 4 random info vectors; the batch unit-vector encoder equals the
per-vector encoder on sampled columns); a noiseless decode (punctured LLR 0) recovers the codeword;
min single-bit and two-info-bit weights counted on TRANSMITTED bits only; check-degree histogram
of the mother graph; outer checks without an H_d edge; variable degrees split transmitted /
punctured; punctured-node recoverability: the fraction of punctured nodes that are 1-step
recoverable (some check whose other neighbours are all transmitted) and the number of peeling
rounds for the erasure decoder to recover every punctured node from the transmitted bits.

Channels (run_chan_v): exactly common.run_chan's generator consumption per trial (info bits, then
the 4096-bit channel draw) on the TRANSMITTED bits, so trial t sees the same info bits and noise as
every plain code (common random numbers); punctured LLRs are 0; success = syndrome-valid AND the
transmitted bits (hence u, hence the whole mother word) equal the codeword.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import N, Z, BuildFail, Cfg  # noqa: E402
from paperholo import ldpc as pldpc  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from holo.core.ldpc import construct  # noqa: E402

VARIANTS = ("ara", "iraa")


# ---------------------------------------------------------------- config
@dataclass(frozen=True)
class VCfg:
    outer: Cfg
    variant: str                 # "ara" | "iraa"
    pre_frac: float = 0.0        # ara: fraction of info block-columns precoded
    pre_sel: str = "heavy"       # ara: heavy = first P columns, light = last P
    iraa_frac: float = 0.0       # iraa: fraction of parity block rows that are second-accumulator outputs
    iraa_links: str = "all"      # iraa: "all" p blocks feed C2, or "one" = exactly one p block per C2 block row
    max_tries: int = 64          # iraa: link draws per outer restart

    @property
    def k(self) -> int:
        return self.outer.k

    @property
    def seed(self) -> int:
        return self.outer.seed

    @property
    def baseline(self) -> bool:
        return False

    @property
    def placement(self) -> str:
        return self.outer.placement

    @property
    def suffix(self) -> str:
        if self.variant == "ara":
            return f"ara-p{self.pre_frac:g}{self.pre_sel[0]}" if self.pre_frac < 1 else "ara-p1"
        return f"iraa-q{self.iraa_frac:g}" + ("" if self.iraa_links == "all" else "x1")

    @property
    def tag(self) -> str:
        return f"{self.outer.tag}+{self.suffix}"

    @property
    def name(self) -> str:
        return f"{self.tag}-s{self.seed}"

    def to_dict(self) -> dict:
        return {"variant": self.variant, "outer": self.outer.to_dict(), "pre_frac": self.pre_frac,
                "pre_sel": self.pre_sel, "iraa_frac": self.iraa_frac, "iraa_links": self.iraa_links, "max_tries": self.max_tries,
                "k": self.k, "tag": self.tag, "seed": self.seed, "rid": self.name, "baseline": False,
                "placement": self.placement, "meta": [], "degs": list(self.outer.degs),
                "outer_meta": [list(x) for x in self.outer.meta]}

    @staticmethod
    def from_dict(d: dict) -> "VCfg":
        return VCfg(outer=Cfg.from_dict(d["outer"]), variant=d["variant"], pre_frac=d["pre_frac"],
                    pre_sel=d["pre_sel"], iraa_frac=d["iraa_frac"],
                    iraa_links=d.get("iraa_links", "all"), max_tries=d.get("max_tries", 64))


def is_variant(d: dict) -> bool:
    return "variant" in d


# ---------------------------------------------------------------- mother graph
@dataclass
class Mother:
    rid: str
    variant: str
    k: int
    n: int                       # mother variables
    chk: np.ndarray              # edges (int64), unsorted
    var: np.ndarray
    enc_info_col: np.ndarray     # outer H_d edges in u-coordinates, sorted by check
    enc_rows: np.ndarray
    enc_row_starts: np.ndarray
    sel: np.ndarray | None = None      # ara: precoded info bit indices in chain order
    m1: int = 0                        # iraa
    link: np.ndarray | None = None     # iraa: C2-local check index per LINKED p bit
    lbits: np.ndarray | None = None    # iraa: the linked p bit indices (0..m1-1)
    n_outer_chk: int = 0

    @property
    def n_chk(self) -> int:
        return self.n - self.k

    def encode(self, info: np.ndarray) -> np.ndarray:
        k, m = self.k, N - self.k
        u = np.asarray(info, np.uint8)
        u2 = u
        if self.variant == "ara":
            v = np.bitwise_xor.accumulate(u[self.sel])
            u2 = u.copy()
            u2[self.sel] = v
        s = np.zeros(m, np.uint8)
        s[self.enc_rows] = np.bitwise_xor.reduceat(u2[self.enc_info_col], self.enc_row_starts)
        if self.variant == "ara":
            return np.concatenate([u, np.bitwise_xor.accumulate(s), v])
        m1 = self.m1
        p = np.bitwise_xor.accumulate(s[:m1])
        t = s[m1:].copy()
        np.bitwise_xor.at(t, self.link, p[self.lbits])
        return np.concatenate([u, p, np.bitwise_xor.accumulate(t)])

    def unit_parity(self) -> np.ndarray:
        """(m, k) uint8: transmitted parity of every unit info vector e_i (batch encoder)."""
        k, m = self.k, N - self.k
        S = np.zeros((m, k), np.uint8)
        rows = np.repeat(self.enc_rows, np.diff(np.append(self.enc_row_starts, self.enc_info_col.size)))
        S[rows, self.enc_info_col] ^= 1
        if self.variant == "ara":
            # e_i at chain position c flips v_c .. v_{KP-1}: its outer syndrome is the reverse XOR-suffix
            sub = S[:, self.sel]
            S[:, self.sel] = np.bitwise_xor.accumulate(sub[:, ::-1], axis=1)[:, ::-1]
            return np.bitwise_xor.accumulate(S, axis=0)
        m1 = self.m1
        P = np.bitwise_xor.accumulate(S[:m1], axis=0)
        T = S[m1:].copy()
        np.bitwise_xor.at(T, self.link, P[self.lbits])
        return np.vstack([P, np.bitwise_xor.accumulate(T, axis=0)])


def _outer_enc(chk, var, k):
    is_info = var < k
    ic, iv = chk[is_info].astype(np.int64), var[is_info].astype(np.int64)
    o = np.argsort(ic, kind="stable")
    ic, iv = ic[o], iv[o]
    rows, first = np.unique(ic, return_index=True)
    return iv, rows, first.astype(np.int64)


def ara_cols(v: VCfg) -> np.ndarray:
    kb = v.k // Z
    P = int(round(v.pre_frac * kb))
    if not 1 <= P <= kb:
        raise ValueError(f"ara: P={P} out of range for kb={kb}")
    return np.arange(P) if v.pre_sel == "heavy" else np.arange(kb - P, kb)


def draw_ara(v: VCfg, restart: int):
    """common.draw + the ANCHOR rule (f) for precoded columns: after pi, the same generator draws
    anchors = Fisher-Yates(g, mb)[:P]; precoded column i MUST use block row anchors[i] and MUST NOT
    use any other precoded column's anchor row (unprecoded columns: unrestricted).  Every punctured
    v then has a check whose other neighbours are all transmitted (1-step recoverable).  Placement
    balanced: least-loaded allowed rows first (as common.draw), the anchor forced in; uniform:
    the d-1 non-anchor rows drawn uniformly from the allowed rows (rule (a) retried)."""
    cfg = v.outer
    k, m = cfg.k, N - cfg.k
    mb, kb = m // Z, k // Z
    degs = cfg.degs
    pcols = ara_cols(v)
    P = pcols.size
    deg_cap = -(-sum(degs) // mb) + cfg.slack
    if P > mb or sum(degs[int(c)] - 1 for c in pcols) > (mb - P) * deg_cap:
        return "anchor_infeasible"       # the precoded columns' non-anchor edges cannot fit under rule (d)
    spec = common._pspec(cfg)
    g = rng(cfg.seed_label, b"eira-H/restart" + str(restart).encode())
    pi = pldpc._fisher_yates(g, m)
    anchors = pldpc._fisher_yates(g, mb)[:P]
    anchor_of = {int(c): int(r) for c, r in zip(pcols, anchors)}
    is_anchor = np.zeros(mb, bool)
    is_anchor[anchors] = True
    used: dict[tuple[int, int], set[int]] = {}
    row_deg = np.zeros(mb, np.int64)
    rows_l, shifts_l = [], []
    balanced = cfg.placement == "balanced"
    for jc, d in enumerate(degs):
        anc = anchor_of.get(jc)
        for att in range(cfg.max_col_attempts):
            if anc is None:
                if balanced:
                    key = g.random(mb)
                    w = 1.0 if att < 256 else 1.0 + (att - 256) / 1024.0
                    rows = np.argsort(row_deg + w * key, kind="stable")[:d].astype(np.int64)
                else:
                    rows = g.integers(0, mb, size=d)
                    if len({int(r) for r in rows}) != d:
                        g.integers(0, Z, size=d)
                        continue
            else:
                allowed = np.flatnonzero(~is_anchor)
                if balanced:
                    key = g.random(allowed.size)
                    w = 1.0 if att < 256 else 1.0 + (att - 256) / 1024.0
                    pick = allowed[np.argsort(row_deg[allowed] + w * key, kind="stable")[:d - 1]]
                else:
                    pick = allowed[g.integers(0, allowed.size, size=d - 1)]
                    if len({int(r) for r in pick}) != d - 1:
                        g.integers(0, Z, size=d)
                        continue
                rows = np.concatenate([[anc], pick]).astype(np.int64)
            shifts = g.integers(0, Z, size=d)
            order = np.argsort(rows)
            rows, shifts = rows[order], shifts[order]
            if (row_deg[rows] + 1 > deg_cap).any():                    # rule (d)
                continue
            bad = False
            for x in range(d):                                         # rule (c)
                for y in range(x + 1, d):
                    if (int(shifts[x]) - int(shifts[y])) % Z in used.get((int(rows[x]), int(rows[y])), ()):
                        bad = True
                        break
                if bad:
                    break
            if bad:
                continue
            if not pldpc._column_tap_weight_ok(pi, rows, shifts, spec):  # rule (b)
                continue
            for x in range(d):
                for y in range(x + 1, d):
                    used.setdefault((int(rows[x]), int(rows[y])), set()).add(
                        (int(shifts[x]) - int(shifts[y])) % Z)
            row_deg[rows] += 1
            rows_l.append(rows)
            shifts_l.append(shifts)
            break
        else:
            return "col_exhausted"
    return pi, rows_l, shifts_l, row_deg


def assemble_ara(v: VCfg, chk, var, rid: str) -> Mother:
    k, m = v.k, N - v.k
    cols = ara_cols(v)
    sel = (cols[:, None] * Z + np.arange(Z)[None, :]).ravel().astype(np.int64)
    KP = sel.size
    pos = np.full(k, -1, np.int64)
    pos[sel] = np.arange(KP)
    iv, rows, first = _outer_enc(chk, var, k)
    chk = chk.astype(np.int64).copy()
    var = var.astype(np.int64).copy()
    moved = (var < k) & (pos[np.minimum(var, k - 1)] >= 0)
    var[moved] = N + pos[var[moved]]
    i = np.arange(KP, dtype=np.int64)
    pc = np.concatenate([m + i, m + i, m + i[1:]])
    pv = np.concatenate([sel, N + i, N + i[:-1]])
    return Mother(rid, "ara", k, N + KP, np.concatenate([chk, pc]), np.concatenate([var, pv]),
                  iv, rows, first, sel=sel, n_outer_chk=m)


def assemble_iraa(v: VCfg, chk, var, rid: str, g) -> Mother | None:
    k, m = v.k, N - v.k
    mb = m // Z
    m2b = int(round(v.iraa_frac * mb))
    if not 1 <= m2b < mb:
        raise ValueError(f"iraa: m2b={m2b} out of range for mb={mb}")
    m1b = mb - m2b
    m1, m2 = m1b * Z, m2b * Z
    iv, rows, first = _outer_enc(chk, var, k)
    chk = chk.astype(np.int64)
    var = var.astype(np.int64)
    drop = (chk == m1) & (var == k + m1 - 1)          # the p-chain -> q-chain step of the single staircase
    assert int(drop.sum()) == 1
    chk, var = chk[~drop], var[~drop]
    # 4-cycle exclusion (rule L): p_j sits in C1 checks j, j+1 (j+1 < m1); an info variable sharing one of
    # them must not also tap the C2 check p_j links to.  F[j, c] = forbidden.
    inf = var < k
    A = sparse.csr_matrix((np.ones(int(inf.sum()), np.int32), (chk[inf], var[inf])), shape=(m, k))
    B = ((A[:m1] @ A[m1:].T) > 0).toarray()
    F = B.copy()
    F[:-1] |= B[1:]
    pi2 = pldpc._fisher_yates(g, m2)
    load = np.zeros(m2b, np.int64)
    a = np.arange(Z, dtype=np.int64)
    if v.iraa_links == "all":
        blocks = list(range(m1b))
    else:                                   # one p block per C2 block row, evenly spread over the p chain
        blocks = sorted({int(i * m1b // m2b) for i in range(m2b)})
    link = np.full(m1, -1, np.int64)
    for b in blocks:
        for att in range(4096):
            key = g.random(m2b)
            r = int(np.argmin(load + (1.0 + att / 16.0) * key))
            s_b = int(g.integers(0, Z))
            tgt = pi2[r * Z + (a + s_b) % Z]
            if F[b * Z + a, tgt].any():
                continue
            if b and int(tgt[0]) == int(link[b * Z - 1]):   # (-1 when block b-1 is unlinked)      # p_{bZ-1}, p_{bZ} share C1 check bZ
                continue
            link[b * Z:(b + 1) * Z] = tgt
            load[r] += 1
            break
        else:
            return None
    lbits = np.flatnonzero(link >= 0).astype(np.int64)
    lc = m1 + link[lbits]
    lv = k + lbits
    return Mother(rid, "iraa", k, N, np.concatenate([chk, lc]), np.concatenate([var, lv]),
                  iv, rows, first, m1=m1, link=link[lbits], lbits=lbits, n_outer_chk=m)


def girth_gt4(M: Mother) -> tuple[bool, int]:
    H = sparse.csr_matrix((np.ones(M.chk.size, np.int64), (M.chk, M.var)), shape=(M.n_chk, M.n))
    HHt = (H @ H.T).tocoo()
    off = HHt.data[HHt.row != HHt.col]
    mx = int(off.max()) if off.size else 0
    return mx <= 1, mx


def to_code(M: Mother, v: VCfg) -> construct.Code:
    n, k = M.n, M.k
    spec = construct.LdpcSpec(M.rid, k, n_bits=n, heavy_deg=max(v.outer.degs), gap_min=v.outer.gap_min)
    chk, var = M.chk, M.var
    order = np.lexsort((var, chk))
    chk, var = chk[order].astype(np.int32), var[order].astype(np.int32)
    cc = np.bincount(chk, minlength=n - k)
    assert cc.min() >= 2, "degree<2 check"
    vc = np.bincount(var, minlength=n)
    assert vc.min() >= 1, "unused variable"
    chk_starts = np.concatenate(([0], np.cumsum(cc)[:-1])).astype(np.int64)
    var_order = np.argsort(var, kind="stable").astype(np.int64)
    var_starts = np.concatenate(([0], np.cumsum(vc)[:-1])).astype(np.int64)
    # enc_* carry the OUTER H_d in u-coordinates (production decode.encode is NOT valid for these
    # codes and is never called on them; Mother.encode is the encoder)
    return construct.Code(spec=spec, edge_chk=chk, edge_var=var, chk_starts=chk_starts,
                          var_order=var_order, var_starts=var_starts, enc_info_col=M.enc_info_col,
                          enc_rows=M.enc_rows, enc_row_starts=M.enc_row_starts)


def build_v(v: VCfg, restart_hint: int | None = None) -> tuple[Mother, dict]:
    outer = v.outer
    m = N - outer.k
    t0 = time.perf_counter()
    reasons = {"col_exhausted": 0, "deg1_check": 0, "info_free_block_row": 0, "girth_variant": 0}
    it = [restart_hint] if restart_hint is not None else range(outer.max_restarts)
    for restart in it:
        if time.perf_counter() - t0 > outer.max_build_s:
            raise BuildFail("build_timeout", {"reasons": reasons, "restarts_tried": restart,
                                              "seconds": time.perf_counter() - t0})
        out = draw_ara(v, restart) if v.variant == "ara" else common.draw(outer, restart)
        if isinstance(out, str):
            reasons[out] = reasons.get(out, 0) + 1
            if out == "anchor_infeasible":
                raise BuildFail("anchor_infeasible", {"reasons": reasons, "seconds": time.perf_counter() - t0})
            continue
        pi, rows_l, shifts_l, row_deg = out
        chk, var = common.expand(outer, pi, rows_l, shifts_l)
        if int(np.bincount(chk, minlength=m).min()) < 2:
            reasons["deg1_check"] += 1
            continue
        n_free = int((row_deg == 0).sum())
        if n_free and outer.info_rows == "restart":
            reasons["info_free_block_row"] += 1
            continue
        tries = [0] if v.variant == "ara" else range(4)
        for T in tries:
            if v.variant == "ara":
                M = assemble_ara(v, chk, var, v.name)
            else:
                g = rng(outer.seed_label, f"iraa-L/restart{restart}/try{T}".encode())
                M = assemble_iraa(v, chk, var, v.name, g)
                if M is None:
                    reasons["link_exhausted"] = reasons.get("link_exhausted", 0) + 1
                    continue
            ok, mx = girth_gt4(M)
            if ok:
                info = {"restart": restart, "try": T, "reasons": reasons,
                        "seconds": round(time.perf_counter() - t0, 3),
                        "block_row_deg_hist": {int(a): int(b) for a, b in zip(*np.unique(row_deg, return_counts=True))},
                        "info_free_block_rows": n_free, "n_edges": int(M.chk.size), "n_mother": M.n,
                        "deg_cap": -(-sum(outer.degs) // (m // Z)) + outer.slack}
                return M, info
            reasons["girth_variant"] += 1
    raise BuildFail("restarts_exhausted" if restart_hint is None else "restart_hint_failed",
                    {"reasons": reasons, "seconds": round(time.perf_counter() - t0, 3)})


_MOTHER: dict[str, Mother] = {}
_BUILT: dict[str, dict] = {}


_CFG: dict[str, VCfg] = {}


def register_v(v: VCfg, restart_hint: int | None = None, sha: str | None = None) -> str:
    rid = v.name
    if not (rid in _MOTHER and rid in construct._CODE_CACHE):
        M, info = build_v(v, restart_hint)
        code = to_code(M, v)
        info["edge_sha"] = common.edge_sha(code)
        construct.LADDER[rid] = code.spec
        construct._CODE_CACHE[rid] = code
        _MOTHER[rid] = M
        _BUILT[rid] = info
        _CFG[rid] = v
    # same guard as common.check_registered, on this module's registry (prep review 2026-09-30)
    if _CFG.get(rid) is not None and _CFG[rid] != v:
        raise RuntimeError(f"registry name collision in worker: {rid} registered for a different variant config")
    if sha is not None and _BUILT[rid].get("edge_sha") != sha:
        raise RuntimeError(f"{rid}: worker rebuild edge digest {_BUILT[rid].get('edge_sha')} != audited {sha}")
    return rid


# ---------------------------------------------------------------- audit
def pair_weights(par: np.ndarray, k: int) -> dict:
    """par (m, k): transmitted parity of e_i.  Weights count TRANSMITTED bits (1 info bit + parity)."""
    packed = np.packbits(np.ascontiguousarray(par.T), axis=1).view(np.uint64)
    w1 = 1 + np.bitwise_count(packed).sum(axis=1).astype(np.int64)
    min2 = None; arg2 = None; n2 = 0
    for i in range(k - 1):
        a = np.bitwise_count(packed[i][None, :] & packed[i + 1:]).sum(axis=1).astype(np.int64)
        w2 = (w1[i] - 1) + (w1[i + 1:] - 1) - 2 * a + 2
        j = int(np.argmin(w2)); mw = int(w2[j])
        if min2 is None or mw < min2:
            min2, arg2 = mw, (i, i + 1 + j)
        n2 += int((w2 <= 8).sum())
    return {"min_w1": int(w1.min()), "argmin_w1": int(np.argmin(w1)), "w1_le8": int((w1 <= 8).sum()),
            "min_w2": min2, "argmin_w2": arg2, "n_w2_le8": n2}


def punct_recovery(M: Mother) -> dict:
    punct = np.zeros(M.n, bool)
    punct[N:] = True
    npu = int(punct.sum())
    if npu == 0:
        return {"n_punct": 0}
    chk, var = M.chk, M.var
    unk = punct.copy()
    cnt = np.bincount(chk, weights=unk[var], minlength=M.n_chk)
    one_sr = np.zeros(M.n, bool)
    one_sr[var[(cnt[chk] == 1) & unk[var]]] = True
    rounds = 0
    while unk.any() and rounds < 20000:
        cnt = np.bincount(chk, weights=unk[var], minlength=M.n_chk)
        e = (cnt[chk] == 1) & unk[var]
        if not e.any():
            break
        unk[var[e]] = False
        rounds += 1
    return {"n_punct": npu, "frac_1sr": float(one_sr[punct].mean()), "peel_rounds": rounds,
            "punct_unrecovered": int(unk.sum())}


def screen0_v(cfgd: dict) -> dict:
    from holo.core.ldpc.decode import decode
    v = VCfg.from_dict(cfgd)
    t = time.process_time()
    rec = {"rid": v.name, "screen": "s0", "k": v.k, "tag": v.tag, "seed": v.seed, "baseline": False,
           "variant": v.variant, "cfg": v.to_dict()}
    try:
        rid = register_v(v)
    except BuildFail as e:
        rec.update(status="reject", reasons=[e.reason], build=e.info, cpu=time.process_time() - t)
        return rec
    M, info = _MOTHER[rid], _BUILT[rid]
    code = construct._CODE_CACHE[rid]
    k, m = M.k, N - M.k
    reasons = []
    # encoder verification: H c == 0 (mother), batch == per-vector, noiseless decode
    g = np.random.default_rng(12345)
    enc_ok = True
    for _ in range(4):
        cw = M.encode(g.integers(0, 2, k).astype(np.uint8))
        syn = np.bitwise_xor.reduceat(cw[code.edge_var], code.chk_starts)
        enc_ok &= not syn.any()
    par = M.unit_parity()
    for i in sorted({0, k // 3, k // 2, k - 1, int(g.integers(0, k))}):
        e = np.zeros(k, np.uint8); e[i] = 1
        enc_ok &= bool(np.array_equal(M.encode(e)[k:N], par[:, i]))
    cw = M.encode(g.integers(0, 2, k).astype(np.uint8))
    llr = np.zeros(M.n)
    llr[:N] = 8.0 * (2.0 * cw[:N] - 1.0)
    ok, hard, _ = decode(llr, rid)
    noiseless_ok = bool(ok and np.array_equal(hard, cw))
    if not enc_ok:
        reasons.append("encoder_mismatch")
    if not noiseless_ok:
        reasons.append("noiseless_decode_failed")
    w = pair_weights(par, k)
    chk_deg = np.bincount(M.chk, minlength=M.n_chk)
    var_deg = np.bincount(M.var, minlength=M.n)
    outer_edge = (M.chk < M.n_outer_chk) & ((M.var < k) | (M.var >= N))
    if M.variant == "ara":
        outer_edge &= True       # every outer-check edge on u or v is an H_d edge (parity lives in k..N-1)
    info_per_chk = np.bincount(M.chk[outer_edge], minlength=M.n_chk)[:M.n_outer_chk]
    _, mx = girth_gt4(M)
    st = {"n_edges": int(M.chk.size), "n_mother": M.n, "n_chk": M.n_chk,
          "chk_deg_hist": {int(a): int(b) for a, b in zip(*np.unique(chk_deg, return_counts=True))},
          "chk_deg_min": int(chk_deg.min()), "chk_deg_max": int(chk_deg.max()), "chk_deg_mean": float(chk_deg.mean()),
          "n_chk_no_info_edge": int((info_per_chk == 0).sum()),
          "var_deg_hist": {int(a): int(b) for a, b in zip(*np.unique(var_deg[:N], return_counts=True))},
          "var_deg_hist_punct": {int(a): int(b) for a, b in zip(*np.unique(var_deg[N:], return_counts=True))},
          "parity_deg2_frac": float((var_deg[k:N] == 2).mean()),
          "girth_gt4": mx <= 1, "HHt_offdiag_max": mx, **w, **punct_recovery(M),
          "encoder_ok": bool(enc_ok), "noiseless_ok": noiseless_ok}
    if not st["girth_gt4"]:
        reasons.append("girth<=4")
    if info["info_free_block_rows"]:
        reasons.append(f"info_free_block_rows={info['info_free_block_rows']}")
    if st["min_w2"] is not None and st["min_w2"] < 10:
        reasons.append(f"min_w2={st['min_w2']}<10")
    rec.update(status="reject" if reasons else "pass", reasons=reasons, build=info, struct=st,
               cpu=time.process_time() - t)
    return rec


def screen0_any(cfgd: dict) -> dict:
    return screen0_v(cfgd) if is_variant(cfgd) else common.screen0(cfgd)


# ---------------------------------------------------------------- channels
def run_chan_v(rid: str, channel: str, params: dict, t0: int, n: int) -> dict:
    """common.run_chan on the TRANSMITTED bits of a mother graph; punctured LLRs 0."""
    from holo.core.ldpc.decode import decode
    M = _MOTHER[rid]
    k, nm = M.k, M.n
    base = common.BASE_ROBUST if channel == "robust" else common.ch.BASE[channel]
    fails = und = iters = iters_ok = n_ok = 0
    und_w = []
    llr_m = np.zeros(nm)
    for t in range(t0, t0 + n):
        g = np.random.default_rng(base + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cwm = M.encode(info)
        cw = cwm[:N]
        if channel == "bsc":
            p = params["p"]
            llr = common.ch.hard_llr(cw ^ (g.random(N) < p), p)
        elif channel == "awgn":
            s = params["sigma"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
        elif channel == "eras":
            p, eps = params["p"], params["eps"]
            llr = common.ch.hard_llr(cw ^ (g.random(N) < p), p)
            llr[g.random(N) < eps] = 0.0
        elif channel == "robust":
            s, f = params["sigma"], params["f"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
            bad = g.random(N) < f
            llr[bad] = 20.0 * (1.0 - 2.0 * cw[bad])
        else:
            raise ValueError(channel)
        llr_m[:N] = llr
        llr_m[N:] = 0.0
        ok, hard, n_it = decode(llr_m, rid)
        good = ok and np.array_equal(hard[:N], cw)
        if not good:
            fails += 1
            if ok:
                und += 1
                e = hard[:N] ^ cw
                und_w.append([t, int(e.sum()), int(e[:k].sum())])
        else:
            iters_ok += n_it
            n_ok += 1
        iters += n_it
    return {"n": n, "fails": fails, "undetected": und, "iters": iters, "iters_ok": iters_ok, "n_ok": n_ok,
            "und_w": und_w}


def run_chan_v_fast(rid: str, channel: str, params: dict, t0: int, n: int, batch: int = 64) -> dict:
    """run_chan_v with the decode batched (fast/fastdecode.decode_batch on the mother graph; punctured
    LLRs 0.0 = erasure, as production).  Same generation code, same counting, same dict
    (fast/test_variants_fast.py checks it against run_chan_v on every channel and family)."""
    common._fast()
    from fastdecode import decode_batch  # noqa: PLC0415
    M = _MOTHER[rid]
    k, nm = M.k, M.n
    base = common.BASE_ROBUST if channel == "robust" else common.ch.BASE[channel]
    L = np.zeros((n, nm))
    C = np.empty((n, N), np.uint8)
    for i, t in enumerate(range(t0, t0 + n)):
        g = np.random.default_rng(base + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cw = M.encode(info)[:N]
        if channel == "bsc":
            p = params["p"]
            llr = common.ch.hard_llr(cw ^ (g.random(N) < p), p)
        elif channel == "awgn":
            s = params["sigma"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
        elif channel == "eras":
            p, eps = params["p"], params["eps"]
            llr = common.ch.hard_llr(cw ^ (g.random(N) < p), p)
            llr[g.random(N) < eps] = 0.0
        elif channel == "robust":
            s, f = params["sigma"], params["f"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
            bad = g.random(N) < f
            llr[bad] = 20.0 * (1.0 - 2.0 * cw[bad])
        else:
            raise ValueError(channel)
        L[i, :N] = llr
        C[i] = cw
    code = construct._CODE_CACHE[rid]
    fails = und = iters = iters_ok = n_ok = 0
    und_w = []
    for s0 in range(0, n, batch):
        ok, hard, nit = decode_batch(L[s0:s0 + batch], code)
        for j in range(ok.size):
            i = s0 + j
            n_it = int(nit[j])
            good = bool(ok[j]) and np.array_equal(hard[j, :N], C[i])
            if not good:
                fails += 1
                if ok[j]:
                    und += 1
                    e = hard[j, :N] ^ C[i]
                    und_w.append([t0 + i, int(e.sum()), int(e[:k].sum())])
            else:
                iters_ok += n_it
                n_ok += 1
            iters += n_it
    return {"n": n, "fails": fails, "undetected": und, "iters": iters, "iters_ok": iters_ok, "n_ok": n_ok,
            "und_w": und_w}


def selfcheck_v_fast(n: int = 24) -> bool:
    """Start-up guard for Tier B2 --decoder fast: run_chan_v_fast == run_chan_v (whole dict) on one ARA
    and one IRAA mother graph at a mixed-outcome awgn point (fast/test_variants_fast.py is the full test)."""
    o = common.recipe_cfg(1664, 8, 0.5, 3, "balanced", 0)
    prm = {"esn0_db": -3.2, "sigma": common.sigma_of(-3.2)}
    for kw in (dict(variant="ara", pre_frac=0.25, pre_sel="heavy"), dict(variant="iraa", iraa_frac=0.25, iraa_links="one")):
        rid = register_v(VCfg(outer=o, **kw))
        t = time.time()
        ok = run_chan_v(rid, "awgn", prm, 0, n) == run_chan_v_fast(rid, "awgn", prm, 0, n, batch=16)
        print(f"[decoder] run_chan_v_fast == run_chan_v on {rid}: {ok} ({time.time() - t:.1f} s)", file=sys.stderr, flush=True)
        if not ok:
            return False
    return True


def task_chan_any(cfgd: dict, restart: int, channel: str, params: dict, t0: int, n: int) -> dict:
    if not is_variant(cfgd):
        return common.task_chan(cfgd, restart, channel, params, t0, n)
    t = time.process_time()
    restart, sha = common.split_hint(restart)
    rid = register_v(VCfg.from_dict(cfgd), restart, sha)
    if common.decoder() == "fast":
        r = run_chan_v_fast(rid, channel, params, t0, n, batch=min(n, 64))
    else:
        r = run_chan_v(rid, channel, params, t0, n)
    return {"n": r["n"], "fails": r["fails"], "und": r["undetected"], "iters": r["iters"],
            "iters_ok": r["iters_ok"], "n_ok": r["n_ok"], "und_w": r["und_w"], "cpu": time.process_time() - t}

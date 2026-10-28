"""Layer 3 — inner FEC: QC-IRA LDPC per 64x64-cell tile (DESIGN.md §6, M2).

Converts the blind receiver's soft payload LLRs (paperholo.acquire) into
CRC-32-certified user bits. Two sub-layers live here:

1. the MOTHER CODE — a binary e-IRA LDPC, n = 4096: QC (Z = 64) info part
   H_d with mixed column weights {heavy, 3} + an interleaved bit-serial
   dual-diagonal accumulator H_a (systematic: info = 0..k-1, parity = k..n-1,
   encoded by one cumulative XOR), one code per rate-ladder entry, derived
   deterministically from its seed label via paperholo.modulation.rng
   (FORMAT-AXIS: golden-anchored, see below);
2. the TILE FRAMING — the page is tiled into 64x64-cell = 4096-slot tiles in
   tile-grid raster order; slots on pilot sites or off-page are SHORTENED
   (known 0); user payload + CRC-32 fill the surviving info positions; the
   transmitted (non-shortened) codeword bits fill compose_page's payload
   bijection exactly (paperholo.compose.payload_index_map).

LLR SIGN CONVENTION (house-wide, matches acquire.cell_bits_blind and
AcquireResult.payload_llr): POSITIVE = bit 1, llr = log P(bit=1)/P(bit=0);
hard bit = (llr > 0). llr == 0.0 is an ERASURE (first-class: the
confetti/fragment path); +-inf marks a KNOWN bit (shortened positions use
-inf = known 0). Internally decode() negates into the textbook
log P(0)/P(1) convention for the min-sum sign algebra.

FORMAT-AXIS DERIVATION of H (layer-3 v1, frozen — precise enough to
reimplement from this docstring; tests/test_ldpc.py pins sha256 anchors):

  DESIGN PROVENANCE (measured, this codebase — the contract's literal
  "H_d weight-3 + block-circulant dual-diagonal H_a" was built FIRST and
  falsified step by step; every claim below was a measured failure of a
  built variant): (i) block-circulant accumulators (I(0)/I(0) and the
  shift-1 spiral) terminate a single info bit's parity runs at BLOCK
  granularity (mb = 19..29), leaving weight-8..10 codewords — 6/200
  UNDETECTED syndrome-valid decodes at p = 0.015 (r0700), a certification
  hazard. (ii) A bit-serial accumulator directly under a QC H_d is worse:
  the circulant structure makes the taps of in-block offsets t and t+1
  ADJACENT along the chain, so every block-column emits weight-(d+2)
  codewords (pairs [t, t+1] -> d unit-length parity runs; extracted and
  verified explicitly) — up to 80/200 undetected. The cure is the
  classical IRA INTERLEAVER, realized as a seeded row permutation Pi
  between H_d and the accumulator, plus a per-column tap-gap weight floor
  (rule (b), exact over all Z offsets). (iii) The uniform-degree-3
  profile waterfalls far below the contract gate at every accumulator
  variant AND as a regular weight-3-everywhere QC code (sum-product 46%
  BLER at the r0700 p=0.035 gate; a (3,6)-regular rate-1/2 control hit
  its textbook threshold, validating the decoder; Monte-Carlo density
  evolution puts the (3,10)-regular class threshold at ~0.037 < the
  gate's need). The frozen v1 profile is the DE-selected e-IRA: 30%
  degree-10 info block-columns (DE threshold ~0.046 at r0700; degree-6
  measured 15% BLER at the gate, degree-10 clears it).

  Geometry per rate: n = 4096, Z = 64, k = spec.k_bits (multiple of Z),
  m = n - k, kb = k/Z info block-columns, mb = m/Z block-rows.
  Circulant convention: I(s) is the Z x Z shifted identity with
  I(s)[a, b] = 1 iff b == (a + s) mod Z (row a connects column (a+s)%Z).

  Structure: H = [Pi @ H_d | H_a].
  H_a (m x m): bit-level dual diagonal — ones at (j, j) and (j, j-1): the
  standard IRA 1/(1+D) accumulator over the whole parity vector
  (p_j = p_{j-1} XOR s_j, s = the permuted H_d @ u).
  Pi: the IRA interleaver, one permutation of the m check rows, drawn
  FIRST from the restart's generator by an explicit Fisher-Yates shuffle
  (integers-only, spelled out so the stream is reproducible):
      pi = arange(m); for i in m-1 .. 1: j = g.integers(0, i+1);
      swap pi[i], pi[j].
  An edge of H_d at (row x, col c) becomes an edge of H at (pi[x], c).
  Pi destroys the circulant tap adjacency of failure (ii) above.

  H_d (m x k): QC. The first nh = round(HEAVY_FRAC * kb) info
  block-columns have weight spec.heavy_deg (10; 6 at r0850, see the
  ladder), the remaining kb - nh have weight 3 — heavy columns FIRST so
  the per-tile payload (which fills
  info positions from the front; shortening consumes the info tail) sits
  on the best-protected variables. Every block-column: d DISTINCT block
  rows, each an I(s). Rows and shifts come from the SAME generator
  g = modulation.rng(spec.seed_label, b"eira-H/restart" + str(R).encode())
  that drew Pi, restart counter R = 0, 1, ... Greedy column-by-column
  draw in column order, attempts up to 65536 per column (heavy columns
  pass rules (a)+(b) at ~5e-4: ~4.7 expected tap adjacencies per draw at
  d = 10, m = 1216); EVERY attempt consumes exactly two draws in this
  order (d = that column's weight):
      rows   = g.integers(0, mb, size=d)
      shifts = g.integers(0, Z, size=d)
  (integers-only on purpose: the .choice stream is less version-stable).
  The attempt is ACCEPTED iff all of:
    (a) the d rows are pairwise distinct (then sorted ascending, shifts
        carried along with their rows);
    (b) TAP-GAP weight floor, exact over all Z in-block offsets t: the
        column's accumulator taps sit at chain positions
        pi[r_i*Z + (t - s_i) mod Z]; sort them per t, require
        (i) no two taps closer than 2 (kills the accumulator 4-cycle) and
        (ii) the column's own parity weight — the alternating gap sum
        g(x0,x1) + g(x2,x3) + ... (+ the tail run m - x_last when d is
        odd) — to be >= spec.gap_min = 24 for EVERY t. This lower-bounds
        every single-info-bit codeword weight by gap_min + 1 directly;
    (c) 4-cycle rule: for every within-column row pair (r, r'),
        delta = (s_r - s_{r'}) mod Z must not repeat a delta previously
        registered on the same (r, r') pair (QC condition: equal shift
        differences on two shared block rows = a 4-cycle, invariant
        under the row permutation Pi);
    (d) row-degree balance: accepting the column must not push any block
        row's info EDGE count above
        ceil((3*(kb-nh) + heavy_deg*nh) / mb) + 1
        (near-concentrated check degrees; the +1 slack is required or the
        greedy endgame stalls — measured).
  After all kb columns are accepted the construction requires min
  bit-level check degree >= 2 over the expanded H (a final row served
  only by the accumulator — possible for row 0 under an unlucky Pi —
  would be a degree-1 check pinning a parity bit). If a column exhausts
  its attempts or the degree check fails, the WHOLE construction restarts
  with R+1 (fresh generator, fresh Pi, fresh label). The first succeeding
  restart index is part of the frozen format (pinned by the golden
  anchors).

  GUARANTEE: girth > 4 (no two columns of H share two rows), info column
  weights {heavy_deg (first nh blocks), 3}, parity weight 2 (last bit 1),
  single-info-bit codeword weight >= gap_min + 1. Multi-column
  conspiracies are interleaver-randomized, NOT bounded: the expected
  residual is O(1) low-weight pairs per code (measured: r0700/r0775/r0850
  batteries show zero undetected decodes; r0625 carries one weight-6
  two-info-bit word that ~0.5-1% of mid-waterfall decodes land on,
  syndrome-valid). That is exactly why certification is CRC-32's job, not
  the syndrome's — decode_tile counts such events as failures.

  ENCODER: codeword = [info u | parity p], s = (Pi H_d) u via edge-array
  XOR segments, p = cumulative XOR of s (accumulator back-substitution).

TILE FRAMING (format-axis, deterministic from (ComposeSpec, seed) alone):

  Tile grid: 64x64-cell tiles in raster order over the page cell grid,
  including partial edge tiles (e012 page 2220x1500 cells -> 35x24 tiles).
  In-tile slot i = sy*64 + sx (raster inside the LDPC tile) sits on absolute page
  cell (ty*64 + sy, tx*64 + sx). A slot is SHORTENED iff it is off-page or
  on a pilot site (compose's v2/v3 site pattern, period 60).

  Slot <-> codeword position (per tile, from the shorten mask alone):
  let n_s = number of shortened slots. Shortened codeword positions are the
  TOP of the info block descending: {k-1, k-2, ..., k-n_s}; if n_s > k they
  overflow into the TOP of the parity block descending: {n-1, ...,
  n-(n_s-k)}. The j-th shortened slot in slot-raster order takes the j-th
  position of that descending sequence. Non-shortened slots in slot-raster
  order take the COMPLEMENT positions in ASCENDING order — so the first
  k_eff = max(k - n_s, 0) non-shortened slots carry info, the rest parity.

  Info content: user payload (cap = max(k_eff - 32, 0) bits) at info
  positions 0..cap-1, then CRC-32 at positions cap..cap+31 (present iff
  k_eff >= 32), zeros elsewhere (including all shortened info positions).
  CRC-32 = zlib.crc32 over the payload packed MSB-first into bytes
  (np.packbits big-bitorder; last byte zero-padded), emitted as a 32-bit
  big-endian MSB-first trailer. CRC pass == F9 certification.
  DEGENERATE tiles (k_eff < 32, includes the n_s > k overflow case) carry
  no payload and no CRC; their info is all zero, hence codeword all zero —
  the overflow parity positions are therefore 0 too, consistent with the
  decoder treating EVERY shortened position as known 0.

  Transmitted bits: each tile's non-shortened codeword positions in
  slot-raster order, scattered to compose's payload bijection at
  payload_index_map[abs cell]; union over tiles = every non-pilot on-page
  cell exactly once = payload_capacity(spec) bits (asserted; 3,237,500 for
  the e012 page).

Decoder: normalized min-sum (alpha = 0.8), fully vectorized over edge
arrays (reduceat segments per check / per variable), early exit on zero
syndrome. decode() never certifies: decode_tile gates ok on
syndrome_ok AND crc_ok (measured false-pass: 0 over the garbage battery,
tests/test_ldpc.py).
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from . import compose
from .modulation import rng

TILE_CELLS = 64
N_BITS = 4096
Z = 64
CRC_BITS = 32
HEAVY_FRAC = 0.30            # fraction of info block-columns that are heavy
LLR_KNOWN = 1e9              # internal finite stand-in for +-inf channel LLRs
_MAX_COL_ATTEMPTS = 65536    # heavy-10 columns pass rules (a)+(b) at ~5e-4
_MAX_RESTARTS = 64


@dataclass(frozen=True)
class LdpcSpec:
    """One rate-ladder entry (format-axis). seed_label defaults to
    b"ldpc-v1/<rate_id>" (set in __post_init__ when left empty)."""

    rate_id: str
    k_bits: int
    n_bits: int = N_BITS
    z: int = Z
    seed_label: bytes = b""
    gap_min: int = 24            # rule (b) single-column parity-weight floor
    heavy_deg: int = 10          # heavy info column weight (needs <= mb - 3
                                 # spare rows; 6 at r0850 where mb = 9)

    def __post_init__(self) -> None:
        if self.n_bits % self.z or self.k_bits % self.z:
            raise ValueError("n_bits and k_bits must be multiples of z")
        if not (0 < self.k_bits < self.n_bits):
            raise ValueError("need 0 < k_bits < n_bits")
        if not self.seed_label:
            object.__setattr__(self, "seed_label",
                               b"ldpc-v1/" + self.rate_id.encode())

    @property
    def m_bits(self) -> int:
        return self.n_bits - self.k_bits

    @property
    def rate(self) -> float:
        return self.k_bits / self.n_bits


LDPC_LADDER: dict[str, LdpcSpec] = {
    # r0547: the COLOR-DESIGN P5 Y-level rung (added 2026-07-10, IMPL-4).
    # k is Z-quantized, so a rung TARGETING 0.547 snaps to the SAME k=2240
    # as r0550 (whose true rate already is 0.5469) — the ladder floor. The
    # distinct rate_id gives it its own seed label => an independent parity
    # structure (no coding-rate gain over r0550; a genuinely lower rung
    # would be k=2176 = 0.531, a frozen-constants-pass decision). Golden-
    # anchored in test_ldpc alongside the frozen five.
    "r0547": LdpcSpec("r0547", 2240),   # 0.547 floor twin (see above)
    "r0550": LdpcSpec("r0550", 2240),   # 0.547 = round(4096*0.55) snapped to Z
    "r0625": LdpcSpec("r0625", 2560),   # 0.625
    "r0700": LdpcSpec("r0700", 2880),   # 0.703
    # heavy_deg shrinks with mb (rules (a)+(b) feasibility: d distinct rows
    # of mb, no tap adjacency over all Z offsets in an m-bit chain)
    "r0775": LdpcSpec("r0775", 3200, heavy_deg=8),   # 0.781 (mb = 14)
    "r0850": LdpcSpec("r0850", 3520, heavy_deg=6),   # 0.859 (mb = 9)
}


@dataclass(frozen=True, eq=False)
class Code:
    """Built mother code: circulant description + edge arrays (decode order:
    lexsorted by (check, variable)) + encode-side info-edge segments."""

    spec: LdpcSpec
    pi: np.ndarray               # (m,) int64 IRA interleaver row permutation
    heavy_rows: np.ndarray       # (nh, heavy_deg) int64 block rows, ascending
    heavy_shifts: np.ndarray     # (nh, heavy_deg) int64 shifts, row-aligned
    light_rows: np.ndarray       # (kb-nh, 3) int64
    light_shifts: np.ndarray     # (kb-nh, 3) int64
    restart: int                 # winning construction restart index
    edge_chk: np.ndarray         # (E,) int32
    edge_var: np.ndarray         # (E,) int32
    chk_starts: np.ndarray       # (m,) int64 reduceat starts (all checks used)
    var_order: np.ndarray        # (E,) int64: edge ids sorted by variable
    var_starts: np.ndarray       # (n,) int64 reduceat starts over var_order
    enc_info_col: np.ndarray     # info edges sorted by row: info col 0..k-1
    enc_rows: np.ndarray         # rows that have >= 1 info edge, ascending
    enc_row_starts: np.ndarray   # reduceat starts into enc_info_col

    @property
    def n_edges(self) -> int:
        return int(self.edge_chk.size)

    def h_sparse(self):
        """scipy.sparse CSR H (test/verification aid)."""
        from scipy import sparse
        m, n = self.spec.m_bits, self.spec.n_bits
        return sparse.csr_matrix(
            (np.ones(self.n_edges, np.int64),
             (self.edge_chk.astype(np.int64), self.edge_var.astype(np.int64))),
            shape=(m, n))


def _n_heavy(spec: LdpcSpec) -> int:
    return round(HEAVY_FRAC * (spec.k_bits // spec.z))


def _fisher_yates(g: np.random.Generator, m: int) -> np.ndarray:
    """Explicit integers-only Fisher-Yates permutation (frozen derivation:
    Generator.permutation's internal stream is not part of numpy's
    compatibility guarantee; this loop is)."""
    pi = np.arange(m, dtype=np.int64)
    for i in range(m - 1, 0, -1):
        j = int(g.integers(0, i + 1))
        pi[i], pi[j] = pi[j], pi[i]
    return pi


def _column_tap_weight_ok(pi: np.ndarray, rows: np.ndarray,
                          shifts: np.ndarray, spec: LdpcSpec) -> bool:
    """Rule (b): exact single-column parity-weight floor over all Z in-block
    offsets t. Taps at chain positions pi[r*Z + (t - s) % Z]; per t the
    column's parity weight is the alternating gap sum of the sorted taps
    (+ tail run to chain end when the count is odd). Also require no two
    taps within distance 2 (accumulator 4-cycle)."""
    z, m = spec.z, spec.m_bits
    t = np.arange(z, dtype=np.int64)[:, None]
    taps = pi[rows[None, :] * z + (t - shifts[None, :]) % z]  # (Z, d)
    taps = np.sort(taps, axis=1)
    gaps = np.diff(taps, axis=1)
    if int(gaps.min()) < 2:
        return False
    d = taps.shape[1]
    if d % 2:
        run_ends = np.concatenate(
            [taps[:, 1:d:2], np.full((z, 1), m, np.int64)], axis=1)
    else:
        run_ends = taps[:, 1:d:2]
    weight = (run_ends - taps[:, 0:d:2]).sum(axis=1)
    return int(weight.min()) >= spec.gap_min


def _draw_h_blocks(spec: LdpcSpec, restart: int) -> tuple[np.ndarray, ...] | None:
    """One restart of the frozen construction draw (see the module docstring
    for the exact rules; this function IS the normative implementation).
    Returns (pi, heavy_rows, heavy_shifts, light_rows, light_shifts) or
    None when the restart fails (column attempts exhausted)."""
    z = spec.z
    mb = spec.m_bits // z
    kb = spec.k_bits // z
    nh = _n_heavy(spec)
    degs = [spec.heavy_deg] * nh + [3] * (kb - nh)
    deg_cap = -(-(3 * (kb - nh) + spec.heavy_deg * nh) // mb) + 1  # rule (d)
    g = rng(spec.seed_label, b"eira-H/restart" + str(restart).encode())
    pi = _fisher_yates(g, spec.m_bits)
    used: dict[tuple[int, int], set[int]] = {}
    row_deg = np.zeros(mb, np.int64)
    cols: list[tuple[np.ndarray, np.ndarray]] = []
    for jc in range(kb):
        d = degs[jc]
        for _attempt in range(_MAX_COL_ATTEMPTS):
            rows = g.integers(0, mb, size=d)
            shifts = g.integers(0, z, size=d)
            if len({int(r) for r in rows}) != d:              # rule (a)
                continue
            order = np.argsort(rows)
            rows = rows[order]
            shifts = shifts[order]
            if (row_deg[rows] + 1 > deg_cap).any():           # rule (d)
                continue
            bad = False
            for a in range(d):                                # rule (c)
                for b in range(a + 1, d):
                    ra, rb = int(rows[a]), int(rows[b])
                    delta = (int(shifts[a]) - int(shifts[b])) % z
                    if delta in used.get((ra, rb), ()):
                        bad = True
                        break
                if bad:
                    break
            if bad:
                continue
            if not _column_tap_weight_ok(pi, rows, shifts, spec):  # rule (b)
                continue
            for a in range(d):
                for b in range(a + 1, d):
                    ra, rb = int(rows[a]), int(rows[b])
                    used.setdefault((ra, rb), set()).add(
                        (int(shifts[a]) - int(shifts[b])) % z)
            row_deg[rows] += 1
            cols.append((rows, shifts))
            break
        else:
            return None
    heavy = cols[:nh]
    light = cols[nh:]
    return (pi,
            np.array([c[0] for c in heavy], np.int64).reshape(nh, spec.heavy_deg),
            np.array([c[1] for c in heavy], np.int64).reshape(nh, spec.heavy_deg),
            np.array([c[0] for c in light], np.int64).reshape(kb - nh, 3),
            np.array([c[1] for c in light], np.int64).reshape(kb - nh, 3))


_CODE_CACHE: dict[bytes, Code] = {}


def _expand_edges(drawn: tuple[np.ndarray, ...], spec: LdpcSpec
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Block description + interleaver + accumulator -> bit-level
    (chk, var) edge arrays."""
    z, k, m = spec.z, spec.k_bits, spec.m_bits
    pi, heavy_rows, heavy_shifts, light_rows, light_shifts = drawn
    a = np.arange(z, dtype=np.int64)
    chk_l: list[np.ndarray] = []
    var_l: list[np.ndarray] = []
    j = 0
    for rows, shifts in ((heavy_rows, heavy_shifts),
                         (light_rows, light_shifts)):
        for c in range(rows.shape[0]):
            for r, s in zip(rows[c], shifts[c]):
                chk_l.append(pi[int(r) * z + a])
                var_l.append(j * z + (a + int(s)) % z)
            j += 1
    # H_a: bit-level dual diagonal — parity bit j sits in checks j and j+1
    jj = np.arange(m, dtype=np.int64)
    chk_l.append(jj)
    var_l.append(k + jj)
    chk_l.append(jj[1:])
    var_l.append(k + jj[:-1])
    return (np.concatenate(chk_l).astype(np.int32),
            np.concatenate(var_l).astype(np.int32))


def build_code(spec: LdpcSpec) -> Code:
    """Build (cached) the mother code for one ladder entry (the winning
    restart index is part of the frozen format)."""
    key = spec.seed_label + (f"/{spec.n_bits}/{spec.z}/{spec.k_bits}"
                             f"/{spec.gap_min}/{spec.heavy_deg}").encode()
    if key in _CODE_CACHE:
        return _CODE_CACHE[key]
    k, m, n = spec.k_bits, spec.m_bits, spec.n_bits
    drawn = chk = var = None
    restart_won = -1
    for restart in range(_MAX_RESTARTS):
        drawn = _draw_h_blocks(spec, restart)
        if drawn is None:
            continue
        chk, var = _expand_edges(drawn, spec)
        if int(np.bincount(chk, minlength=m).min()) >= 2:  # degree check
            restart_won = restart
            break
        drawn = None
    if drawn is None:
        raise RuntimeError(f"H construction failed for {spec.rate_id} "
                           f"after {_MAX_RESTARTS} restarts")
    order = np.lexsort((var, chk))
    chk, var = chk[order], var[order]
    chk_counts = np.bincount(chk, minlength=m)
    chk_starts = np.concatenate(([0], np.cumsum(chk_counts)[:-1]))
    var_order = np.argsort(var, kind="stable")
    var_counts = np.bincount(var, minlength=n)
    assert var_counts.min() >= 1
    var_starts = np.concatenate(([0], np.cumsum(var_counts)[:-1]))
    # encode-side: info edges only (var < k), sorted by row
    is_info = var < k
    ic, iv = chk[is_info].astype(np.int64), var[is_info].astype(np.int64)
    io = np.argsort(ic, kind="stable")
    ic, iv = ic[io], iv[io]
    enc_rows, first = np.unique(ic, return_index=True)
    code = Code(spec=spec, pi=drawn[0],
                heavy_rows=drawn[1], heavy_shifts=drawn[2],
                light_rows=drawn[3], light_shifts=drawn[4],
                restart=restart_won, edge_chk=chk, edge_var=var,
                chk_starts=chk_starts.astype(np.int64),
                var_order=var_order.astype(np.int64),
                var_starts=var_starts.astype(np.int64),
                enc_info_col=iv, enc_rows=enc_rows,
                enc_row_starts=first.astype(np.int64))
    _CODE_CACHE[key] = code
    return code


def encode(info_bits: np.ndarray, spec: LdpcSpec) -> np.ndarray:
    """Systematic encode: codeword = [info u | parity p], parity by the IRA
    accumulator back-substitution p_j = p_{j-1} XOR s_j (s = H_d @ info),
    vectorized as one cumulative XOR over the whole parity vector."""
    code = build_code(spec)
    k, m = spec.k_bits, spec.m_bits
    info = np.asarray(info_bits).astype(np.uint8).ravel()
    if info.size != k:
        raise ValueError(f"info_bits must be ({k},), got {info.shape}")
    if info.size and int(info.max()) > 1:
        raise ValueError("info_bits must be {0,1}")
    s = np.zeros(m, np.uint8)
    seg = np.bitwise_xor.reduceat(info[code.enc_info_col], code.enc_row_starts)
    s[code.enc_rows] = seg
    p = np.bitwise_xor.accumulate(s)
    return np.concatenate([info, p])


def _bp_loop(L: np.ndarray, code: Code, max_iters: int, alpha: float,
             sum_product: bool) -> tuple[np.ndarray, bool, int]:
    """Flooding BP loop over the edge arrays, internal convention
    (positive = bit 0). Check update: normalized min-sum (alpha) or exact
    sum-product (tanh rule). Early exit on zero syndrome."""
    chk, var = code.edge_chk, code.edge_var
    cs, vo, vs = code.chk_starts, code.var_order, code.var_starts
    E = chk.size
    epos = np.arange(E, dtype=np.int64)
    c2v = np.zeros(E)
    Ltot = L.copy()
    n_iters = 0
    syndrome_ok = False
    for it in range(max_iters + 1):
        hard = (Ltot < 0).astype(np.uint8)
        syn = np.bitwise_xor.reduceat(hard[var], cs)
        if not syn.any():
            syndrome_ok = True
            break
        if it == max_iters:
            break
        n_iters = it + 1
        v2c = Ltot[var] - c2v
        n_neg = np.add.reduceat((v2c < 0).astype(np.int64), cs)
        par_sign = 1.0 - 2.0 * (n_neg & 1)
        sgn = np.where(v2c < 0, -1.0, 1.0)
        if sum_product:
            t = np.abs(np.tanh(np.clip(v2c, -40.0, 40.0) / 2.0))
            lt = np.log(np.clip(t, 1e-300, 1.0))
            lsum = np.add.reduceat(lt, cs)
            ext = np.exp(np.clip(lsum[chk] - lt, -700.0, -1e-16))
            c2v = 2.0 * np.arctanh(np.clip(par_sign[chk] * sgn * ext,
                                           -0.999_999_999_999, 0.999_999_999_999))
        else:
            mag = np.abs(v2c)
            min1 = np.minimum.reduceat(mag, cs)
            pos_m = np.where(mag == min1[chk], epos, E)
            first = np.minimum.reduceat(pos_m, cs)
            mag2 = mag.copy()
            mag2[first] = np.inf
            min2 = np.minimum.reduceat(mag2, cs)
            ext = np.where(epos == first[chk], min2[chk], min1[chk])
            c2v = alpha * par_sign[chk] * sgn * ext
        Ltot = L + np.add.reduceat(c2v[vo], vs)
    return (Ltot < 0).astype(np.uint8), bool(syndrome_ok), int(n_iters)


def decode(llr: np.ndarray, spec: LdpcSpec, *, max_iters: int = 60,
           alpha: float = 0.8, llr_clip: float = 20.0,
           sp_retry: bool = True) -> tuple[np.ndarray, bool, int]:
    """Hybrid BP decode, vectorized over edge arrays: normalized min-sum
    (alpha) first; on syndrome failure ONE exact sum-product retry from the
    channel LLRs (measured at the r0700 BSC gate p=0.035, 500 trials:
    min-sum alone 4.0% BLER, sum-product 1.6% — the retry buys the gate
    while clean tiles keep the min-sum fast path and its early exit).

    llr: (n,) float, HOUSE convention (positive = bit 1); 0.0 = erasure,
    +-inf = known bit (mapped to +-1e9 internally so no inf-inf NaNs).
    Finite inputs are clipped to +-llr_clip. Returns (hard_bits (n,) uint8,
    syndrome_ok, n_iters); n_iters = total iterations across both passes,
    0 when the channel hard decisions already satisfy every check.
    syndrome_ok certifies H@c == 0 only — CRC certification is
    decode_tile's job.
    """
    code = build_code(spec)
    n = spec.n_bits
    x = np.asarray(llr, np.float64).ravel()
    if x.size != n:
        raise ValueError(f"llr must be ({n},), got {x.shape}")
    L = np.clip(x, -llr_clip, llr_clip)
    L[np.isposinf(x)] = LLR_KNOWN
    L[np.isneginf(x)] = -LLR_KNOWN
    L = -L                                   # internal: positive = bit 0
    hard, syndrome_ok, n_iters = _bp_loop(L, code, max_iters, alpha, False)
    if not syndrome_ok and sp_retry and max_iters > 0:
        hard, syndrome_ok, n2 = _bp_loop(L, code, max_iters, alpha, True)
        n_iters += n2
    return hard, syndrome_ok, n_iters


# ---------------------------------------------------------------------------
# tile framing
# ---------------------------------------------------------------------------


def tile_grid(page_cells_yx: tuple[int, int], tile_cells: int = TILE_CELLS
              ) -> list[tuple[int, int]]:
    """All (tile_y, tile_x) in tile-grid raster order over the page cell
    grid, including partial edge tiles (e012: 2220x1500 -> 35x24 = 840)."""
    h, w = page_cells_yx
    nty = -(-h // tile_cells)
    ntx = -(-w // tile_cells)
    return [(ty, tx) for ty in range(nty) for tx in range(ntx)]


_PATTERN_CACHE: dict = {}
_IDXMAP_CACHE: dict = {}


def _pilot_pattern(spec: "compose.ComposeSpec", seed: bytes) -> np.ndarray:
    """Periodic (period_cells^2) SHORTEN pattern: pilot sites, plus dust
    sites when spec.dust is set (dust positions are tile-periodic by
    construction — paperholo.dust — so the modulo derivation extends)."""
    key = (spec, seed)
    if key not in _PATTERN_CACHE:
        p = spec.pilot.period_cells
        pos = compose._site_positions_tile(spec.pilot, seed)
        pat = np.zeros((p, p), dtype=bool)
        pat[pos[:, 0], pos[:, 1]] = True
        if spec.dust is not None:
            from .dust import dust_positions_tile
            dpos = dust_positions_tile(spec.pilot, spec.dust, seed)
            pat[dpos[:, 0], dpos[:, 1]] = True
        _PATTERN_CACHE[key] = pat
    return _PATTERN_CACHE[key]


def _index_map(spec: "compose.ComposeSpec", seed: bytes) -> np.ndarray:
    key = (spec, seed)
    if key not in _IDXMAP_CACHE:
        _IDXMAP_CACHE[key] = compose.payload_index_map(spec, seed)
    return _IDXMAP_CACHE[key]


def tile_shorten_mask(tile_yx: tuple[int, int], compose_spec:
                      "compose.ComposeSpec", seed: bytes) -> np.ndarray:
    """(4096,) bool, slot-raster order: True where the slot is SHORTENED
    (off-page, on a pilot site, or — v4 pages — on a dust site).
    Deterministic from (spec, seed, tile); identical for every LEVEL of a
    cmy8 page (all levels share the index map)."""
    ty, tx = tile_yx
    h, w = compose_spec.page_cells_yx
    p = compose_spec.pilot.period_cells
    pat = _pilot_pattern(compose_spec, seed)
    ys = ty * TILE_CELLS + np.arange(TILE_CELLS)
    xs = tx * TILE_CELLS + np.arange(TILE_CELLS)
    off = (ys >= h)[:, None] | (xs >= w)[None, :]
    pilot = pat[(ys % p)[:, None], (xs % p)[None, :]]
    return (off | pilot).ravel()


def _slot_codeword_positions(shorten_mask: np.ndarray, spec: LdpcSpec
                             ) -> np.ndarray:
    """(4096,) int64 codeword position of each slot (the frozen assignment:
    shortened slots take info-top descending, overflow parity-top descending;
    non-shortened slots take the ascending complement)."""
    n, k = spec.n_bits, spec.k_bits
    mask = np.asarray(shorten_mask, bool).ravel()
    if mask.size != n:
        raise ValueError(f"shorten_mask must be ({n},)")
    n_s = int(mask.sum())
    n_info = min(n_s, k)
    short_pos = np.arange(k - 1, k - 1 - n_info, -1, dtype=np.int64)
    if n_s > k:
        short_pos = np.concatenate(
            [short_pos, np.arange(n - 1, n - 1 - (n_s - k), -1, dtype=np.int64)])
    keep = np.ones(n, bool)
    keep[short_pos] = False
    nonshort_pos = np.flatnonzero(keep)          # ascending
    out = np.empty(n, np.int64)
    out[mask] = short_pos
    out[~mask] = nonshort_pos
    return out


def tile_user_capacity(shorten_mask: np.ndarray, spec: LdpcSpec) -> int:
    """Per-tile user capacity = max(k_eff - 32, 0), k_eff = max(k - n_s, 0).
    Tiles with k_eff < 32 are DEGENERATE (no payload, no CRC)."""
    n_s = int(np.asarray(shorten_mask, bool).sum())
    return max(max(spec.k_bits - n_s, 0) - CRC_BITS, 0)


def _crc32_bits(payload_bits: np.ndarray) -> np.ndarray:
    """(32,) uint8, MSB-first big-endian zlib.crc32 over the payload packed
    MSB-first into bytes (np.packbits, last byte zero-padded)."""
    b = np.packbits(np.asarray(payload_bits, np.uint8)).tobytes()
    c = zlib.crc32(b) & 0xFFFFFFFF
    return ((c >> (31 - np.arange(CRC_BITS))) & 1).astype(np.uint8)


def encode_tile(user_bits: np.ndarray, shorten_mask: np.ndarray,
                spec: LdpcSpec) -> tuple[np.ndarray, np.ndarray]:
    """One tile: (codeword (n,), transmitted_bits) — transmitted bits are the
    non-shortened codeword positions in slot-raster order."""
    mask = np.asarray(shorten_mask, bool).ravel()
    cw_pos = _slot_codeword_positions(mask, spec)
    n_s = int(mask.sum())
    k_eff = max(spec.k_bits - n_s, 0)
    cap = max(k_eff - CRC_BITS, 0)
    user = np.asarray(user_bits, np.uint8).ravel()
    if user.size != cap:
        raise ValueError(f"tile takes exactly {cap} user bits, got {user.size}")
    info = np.zeros(spec.k_bits, np.uint8)
    if k_eff >= CRC_BITS:
        info[:cap] = user
        info[cap:cap + CRC_BITS] = _crc32_bits(user)
    cw = encode(info, spec)
    return cw, cw[cw_pos[~mask]]


@dataclass
class TileResult:
    """decode_tile outcome. ok == syndrome_ok AND crc_ok (F9 certification);
    payload_bits is None unless ok. n_erased/n_measured count the
    NON-shortened slots with llr == 0 / != 0."""

    tile_yx: tuple[int, int]
    ok: bool
    crc_ok: bool
    syndrome_ok: bool
    payload_bits: np.ndarray | None
    n_iters: int
    n_erased: int
    n_measured: int


def decode_tile(llr4096: np.ndarray, shorten_mask: np.ndarray,
                ldpc_spec: LdpcSpec, *, tile_yx: tuple[int, int] = (-1, -1),
                max_iters: int = 60, alpha: float = 0.8) -> TileResult:
    """Decode one tile from slot-raster LLRs (house sign convention;
    0.0 = erasure). Shortened slots are pinned to known 0 regardless of the
    passed llr. NEVER returns ok=True with an uncertified payload: syndrome
    AND CRC-32 both gate. Degenerate tiles (k_eff < 32) return an empty
    payload; their crc_ok degrades to 'all non-shortened info decoded 0'."""
    spec = ldpc_spec
    mask = np.asarray(shorten_mask, bool).ravel()
    x = np.asarray(llr4096, np.float64).ravel()
    if x.size != spec.n_bits:
        raise ValueError(f"llr4096 must be ({spec.n_bits},)")
    cw_pos = _slot_codeword_positions(mask, spec)
    llr_cw = np.zeros(spec.n_bits)
    llr_cw[cw_pos] = x
    llr_cw[cw_pos[mask]] = -np.inf           # known 0 (house: negative = 0)
    hard, syn_ok, n_iters = decode(llr_cw, spec, max_iters=max_iters,
                                   alpha=alpha)
    n_s = int(mask.sum())
    k_eff = max(spec.k_bits - n_s, 0)
    cap = max(k_eff - CRC_BITS, 0)
    payload = hard[:cap].astype(np.uint8)
    if k_eff >= CRC_BITS:
        crc_ok = bool(np.array_equal(hard[cap:cap + CRC_BITS],
                                     _crc32_bits(payload)))
    else:
        crc_ok = bool(not hard[:k_eff].any())
    ok = bool(syn_ok and crc_ok)
    meas = x[~mask] != 0.0
    return TileResult(tile_yx=tuple(tile_yx), ok=ok, crc_ok=crc_ok,
                      syndrome_ok=bool(syn_ok),
                      payload_bits=payload if ok else None,
                      n_iters=int(n_iters),
                      n_erased=int((~meas).sum()), n_measured=int(meas.sum()))


def _tile_payload_indices(tile_yx: tuple[int, int],
                          compose_spec: "compose.ComposeSpec", seed: bytes,
                          mask: np.ndarray) -> np.ndarray:
    """Page-payload-bijection indices of the tile's non-shortened slots, in
    slot-raster order (all >= 0: non-shortened slots are exactly the on-page
    non-pilot cells)."""
    ty, tx = tile_yx
    h, w = compose_spec.page_cells_yx
    idx_map = _index_map(compose_spec, seed)
    ys = ty * TILE_CELLS + np.arange(TILE_CELLS)
    xs = tx * TILE_CELLS + np.arange(TILE_CELLS)
    sy, sx = np.divmod(np.flatnonzero(~mask), TILE_CELLS)
    pidx = idx_map[ys[sy], xs[sx]]
    assert (pidx >= 0).all()
    return pidx




# public alias (acquire-v2 tilemap F9 backfill uses the same addressing
# primitive as encode_page/gather_tile_llrs)
tile_payload_indices = _tile_payload_indices

def encode_page(user_bits, compose_spec: "compose.ComposeSpec",
                seed: bytes, ldpc_spec) -> dict:
    """Frame a page: user bits -> per-tile LDPC codewords -> the payload-bit
    vector compose_page consumes. User bits are consumed tile-by-tile in
    tile-grid raster order (each tile takes its own capacity). Returns
    {"payload_bits": (payload_capacity,) uint8, "per_tile": accounting list,
    "user_capacity_bits": int}; asserts the bijection is filled EXACTLY.

    LEVEL-AWARE (cmy8, COLOR-DESIGN D2): when compose_spec.n_levels == 3,
    user_bits is a LIST of 3 per-level user-bit arrays and ldpc_spec a LIST
    of 3 LdpcSpec (per-level rate rungs); each level frames independently
    against the SAME dust-aware shorten masks. The returned dict then holds
    lists in every slot ("payload_bits": [3 x (capacity,)], "per_tile":
    [3 lists], "user_capacity_bits": [3 ints]) ready for compose_page's
    per-level payload. The single-level path is byte-identical to before."""
    if compose_spec.n_levels == 3:
        if (not isinstance(user_bits, (list, tuple))
                or len(user_bits) != 3
                or not isinstance(ldpc_spec, (list, tuple))
                or len(ldpc_spec) != 3):
            raise ValueError("cmy8 page: pass user_bits and ldpc_spec as "
                             "lists of 3 (levels C, M, Y)")
        outs = [_encode_page_single(u, compose_spec, seed, ls)
                for u, ls in zip(user_bits, ldpc_spec)]
        return {"payload_bits": [o["payload_bits"] for o in outs],
                "per_tile": [o["per_tile"] for o in outs],
                "user_capacity_bits": [o["user_capacity_bits"] for o in outs]}
    return _encode_page_single(user_bits, compose_spec, seed, ldpc_spec)


def _encode_page_single(user_bits: np.ndarray,
                        compose_spec: "compose.ComposeSpec", seed: bytes,
                        ldpc_spec: LdpcSpec) -> dict:
    capacity = compose.payload_capacity(compose_spec)
    user = np.asarray(user_bits, np.uint8).ravel()
    if user.size and int(user.max()) > 1:
        raise ValueError("user_bits must be {0,1}")
    payload = np.zeros(capacity, np.uint8)
    filled = np.zeros(capacity, bool)
    per_tile: list[dict] = []
    ptr = 0
    for tile in tile_grid(compose_spec.page_cells_yx):
        mask = tile_shorten_mask(tile, compose_spec, seed)
        cap = tile_user_capacity(mask, ldpc_spec)
        _, tx_bits = encode_tile(user[ptr:ptr + cap], mask, ldpc_spec)
        pidx = _tile_payload_indices(tile, compose_spec, seed, mask)
        if filled[pidx].any():
            raise AssertionError(f"tile {tile}: payload bijection overlap")
        payload[pidx] = tx_bits
        filled[pidx] = True
        per_tile.append({"tile_yx": tile, "n_short": int(mask.sum()),
                         "user_bits": cap, "user_offset": ptr,
                         "n_transmitted": int(tx_bits.size)})
        ptr += cap
    if user.size != ptr:
        raise ValueError(f"user_bits must be exactly {ptr} bits "
                         f"(page user capacity), got {user.size}")
    assert filled.all(), "payload bijection not fully covered"
    return {"payload_bits": payload, "per_tile": per_tile,
            "user_capacity_bits": ptr}


def page_user_capacity(compose_spec: "compose.ComposeSpec", seed: bytes,
                       ldpc_spec: LdpcSpec) -> int:
    """Total user bits one page carries at this rate (sum of tile caps).
    On cmy8 pages this is PER LEVEL at that level's rate (the shorten
    masks are level-independent): call once per level rung."""
    return sum(tile_user_capacity(tile_shorten_mask(t, compose_spec, seed),
                                  ldpc_spec)
               for t in tile_grid(compose_spec.page_cells_yx))


def gather_tile_llrs(payload_llr: np.ndarray, payload_cell_index: np.ndarray,
                     compose_spec: "compose.ComposeSpec", seed: bytes,
                     tile_yx: tuple[int, int]
                     ) -> tuple[np.ndarray, np.ndarray, float]:
    """AcquireResult -> one tile's decoder input: (llr4096 slot-raster with
    0.0 at unobserved/shortened slots, shorten_mask, coverage = observed
    fraction of the tile's non-shortened slots). payload_llr is aligned with
    payload_cell_index (acquire.AcquireResult convention, positive = bit 1)."""
    mask = tile_shorten_mask(tile_yx, compose_spec, seed)
    pidx = _tile_payload_indices(tile_yx, compose_spec, seed, mask)
    pci = np.asarray(payload_cell_index, np.int64).ravel()
    pll = np.asarray(payload_llr, np.float64).ravel()
    if pci.size != pll.size:
        raise ValueError("payload_llr and payload_cell_index length mismatch")
    order = np.argsort(pci, kind="stable")
    sorted_idx = pci[order]
    pos = np.searchsorted(sorted_idx, pidx)
    found = (pos < sorted_idx.size)
    found[found] = sorted_idx[pos[found]] == pidx[found]
    llr = np.zeros(N_BITS)
    slots = np.flatnonzero(~mask)
    llr[slots[found]] = pll[order[pos[found]]]
    n_non = slots.size
    coverage = float(found.sum() / n_non) if n_non else 0.0
    return llr, mask, coverage


def decode_page_tiles(payload_llr, payload_cell_index: np.ndarray,
                      compose_spec: "compose.ComposeSpec", seed: bytes,
                      ldpc_spec, *, min_coverage: float = 0.0,
                      tiles: Sequence[tuple[int, int]] | None = None):
    """Convenience sweep: gather+decode every tile (or the given subset) with
    coverage >= min_coverage. Tiles below the gate are skipped (a tile with
    no observed slots can only decode degenerately).

    LEVEL-AWARE: on a cmy8 spec pass payload_llr as a LIST of 3 per-level
    LLR arrays (all aligned with the ONE payload_cell_index — levels share
    the index map) and ldpc_spec as a LIST of 3; returns a list of 3
    per-level TileResult lists (levels certify independently, D2). The
    single-level signature and behavior are unchanged."""
    if compose_spec.n_levels == 3:
        if (not isinstance(payload_llr, (list, tuple))
                or len(payload_llr) != 3
                or not isinstance(ldpc_spec, (list, tuple))
                or len(ldpc_spec) != 3):
            raise ValueError("cmy8 page: pass payload_llr and ldpc_spec as "
                             "lists of 3 (levels C, M, Y)")
        return [_decode_page_tiles_single(pl, payload_cell_index,
                                          compose_spec, seed, ls,
                                          min_coverage=min_coverage,
                                          tiles=tiles)
                for pl, ls in zip(payload_llr, ldpc_spec)]
    return _decode_page_tiles_single(payload_llr, payload_cell_index,
                                     compose_spec, seed, ldpc_spec,
                                     min_coverage=min_coverage, tiles=tiles)


def _decode_page_tiles_single(payload_llr: np.ndarray,
                              payload_cell_index: np.ndarray,
                              compose_spec: "compose.ComposeSpec",
                              seed: bytes, ldpc_spec: LdpcSpec, *,
                              min_coverage: float = 0.0,
                              tiles: Sequence[tuple[int, int]] | None = None
                              ) -> list[TileResult]:
    out: list[TileResult] = []
    for tile in (tiles if tiles is not None
                 else tile_grid(compose_spec.page_cells_yx)):
        llr, mask, cov = gather_tile_llrs(payload_llr, payload_cell_index,
                                          compose_spec, seed, tile)
        if cov < min_coverage:
            continue
        res = decode_tile(llr, mask, ldpc_spec, tile_yx=tile)
        out.append(res)
    return out

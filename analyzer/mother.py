"""Mother-code framing, BP variants and the certificate gate (PLAN §1.2).

Declared deviation (PLAN §6): this module re-frames what
`tile_codec.decode_frame` assembles inline, calls the private
`holo3.lib.ldpc._bp_loop`, and owns the analyzer's own damped / offset /
layered min-sum loop.  Everything else — the code, the dither, the
transmitted positions, the CRC — is holo3's, called.

Why each piece exists:

- `to_mother` is the ONE un-dither of DESIGN §6 / PLAN §1.3.  Input is the
  as-printed SEQUENTIAL domain (`tiles._sequential_payload`'s contract:
  un-permuted, still dithered).  Production's L0/L1 path un-dithers inside
  `cmy8_decode_stream`; every other rung un-dithers here, exactly once.
- `bp` exists because `ldpc.decode` returns neither the posterior nor the
  syndrome VECTOR nor an unsatisfied-check count, and offers no sum-product-
  only, damped or layered schedule.  Mode "minsum-then-sp" reproduces
  `ldpc.decode` call-for-call so the hard vector is bit-identical to
  production at the same iteration count (tested).
- `gate` is DESIGN §0: syndrome first (never CRC a non-codeword), the CRC
  consult charged to the exposure bound before it is read.

Blindness (DESIGN §0): this module must not import `analyzer.truth` or
`analyzer.oracle`.
"""

from __future__ import annotations

import hashlib

import numpy as np

from holo3.format import keystream, tile_codec
from holo3.format.tile_codec import Bank
from holo3.lib import ldpc
from holo3.lib.ldpc import CODES, LLR_CLIP, LLR_KNOWN, Code
from holo3.plugins.tiles import stream_fact

from .types import EXPOSURE_PER_CONSULT, Exposure, Key, Mother, BpOut

BP_ALPHA = 0.8
LAYERED_GROUP_CHECKS = 64  # = ldpc.Z, one lifted block per layer

MODES = ("minsum-then-sp", "sp", "minsum", "damped", "damped-offset",
         "layered")

_PACKED_H: dict[str, np.ndarray] = {}


def bank_of(row, stream_id: str) -> Bank:
    """The single-child cmy8 bank of one stream (the analyzer is cmy8-only)."""
    bank = stream_fact(row, stream_id).rung_children
    if len(bank) != 1:
        raise ValueError(
            f"mother: cmy8 expects a one-child bank, got {bank!r}")
    return bank


def dither_of(row, key: Key) -> np.ndarray:
    """The as-printed dither of this (tile, stream), length payload_cells."""
    page, ty, tx, stream_id = key
    counter = row.tile_counter(page, ty, tx)
    n_tx = tile_codec.bank_transmitted_bits(bank_of(row, stream_id))
    return keystream.cmy8_dither_bits(row.seed, stream_id, counter, n_tx)


def to_mother(llr_sequential: np.ndarray, row, key: Key, *,
              metadata_bit: int | None = None) -> Mother:
    """As-printed sequential LLRs -> the mother code's n_bits LLR vector.

    Un-dithers ONCE, scatters through `transmitted_positions`, pins the
    shortened window `[active, k)` at -inf, and injects the metadata bit at
    info index 0 at +-inf when it is trusted (positive = bit 1, the
    `tile_codec` convention).
    """
    stream_id = key[3]
    bank = bank_of(row, stream_id)
    code_id, shorten = bank[0]
    code = CODES[code_id]
    active = code.k_bits - shorten
    n_tx = code.n_bits - shorten
    x = np.asarray(llr_sequential, np.float64).ravel()
    if x.size != n_tx:
        raise ValueError(
            f"mother: sequential LLR has {x.size} entries, bank transmits "
            f"{n_tx}")
    dither = dither_of(row, key)
    undithered = x * (1.0 - 2.0 * dither.astype(np.float64))
    positions = tile_codec.transmitted_positions(code_id, shorten)
    llr = np.zeros(code.n_bits, np.float64)
    llr[positions] = undithered
    if shorten:
        llr[active:code.k_bits] = -np.inf
    if metadata_bit is not None:
        llr[0] = np.inf if int(metadata_bit) else -np.inf
    return Mother(key=key, rate_id=code_id, llr=llr, active=active,
                  k_bits=code.k_bits, transmitted=positions, dither=dither,
                  metadata_bit=(None if metadata_bit is None
                                else int(metadata_bit)))


def code_of(mother: Mother) -> Code:
    return CODES[mother.rate_id]


def to_sequential(values_mother: np.ndarray, mother: Mother) -> np.ndarray:
    """A mother-domain LLR-like vector back in the as-printed domain.

    The dither flips the sign of an LLR, so it applies unchanged in both
    directions; use this for posteriors and extrinsics, never for bits.
    """
    values = np.asarray(values_mother, np.float64)
    return values[mother.transmitted] * (
        1.0 - 2.0 * mother.dither.astype(np.float64))


def clipped_external(llr: np.ndarray) -> np.ndarray:
    """`ldpc.decode`'s channel treatment, in the EXTERNAL sign."""
    x = np.asarray(llr, np.float64).ravel()
    out = np.clip(x, -LLR_CLIP, LLR_CLIP)
    out[np.isposinf(x)] = LLR_KNOWN
    out[np.isneginf(x)] = -LLR_KNOWN
    return out


def syndrome(hard: np.ndarray, code: Code) -> np.ndarray:
    h = np.asarray(hard, np.uint8)
    return np.bitwise_xor.reduceat(h[code.edge_var], code.chk_starts)


def pack_h(rate_id: str) -> np.ndarray:
    """H as packed uint64 rows (m x ceil(n/64)), built from the edge lists.

    `ldpc.Code` carries no dense H; OSD (DESIGN §6 L5) and any explicit
    syndrome algebra need one.  Duplicate edges cancel, so the accumulation
    is XOR, not OR.  Cached per rate id.
    """
    cached = _PACKED_H.get(rate_id)
    if cached is not None:
        return cached
    code = CODES[rate_id]
    m = code.n_bits - code.k_bits
    words = (code.n_bits + 63) // 64
    packed = np.zeros((m, words), np.uint64)
    var = code.edge_var.astype(np.int64)
    chk = code.edge_chk.astype(np.int64)
    bit = np.left_shift(np.uint64(1), (var & 63).astype(np.uint64))
    np.bitwise_xor.at(packed, (chk, var >> 6), bit)
    packed.setflags(write=False)
    _PACKED_H[rate_id] = packed
    return packed


def _minsum_c2v(v2c: np.ndarray, chk_local: np.ndarray,
                starts_local: np.ndarray, alpha: float, beta: float
                ) -> np.ndarray:
    """The min-sum check update of `ldpc._bp_loop`, plus an offset term.

    beta > 0 makes it offset-and-normalized min-sum: |c2v| = max(alpha*min -
    beta, 0), clamped at zero.  beta = 0 is production's rule exactly.
    """
    n_edges = v2c.size
    epos = np.arange(n_edges, dtype=np.int64)
    n_neg = np.add.reduceat((v2c < 0).astype(np.int64), starts_local)
    par_sign = 1.0 - 2.0 * (n_neg & 1)
    sgn = np.where(v2c < 0, -1.0, 1.0)
    mag = np.abs(v2c)
    min1 = np.minimum.reduceat(mag, starts_local)
    pos_m = np.where(mag == min1[chk_local], epos, n_edges)
    first = np.minimum.reduceat(pos_m, starts_local)
    mag2 = mag.copy()
    mag2[first] = np.inf
    min2 = np.minimum.reduceat(mag2, starts_local)
    ext = np.where(epos == first[chk_local], min2[chk_local], min1[chk_local])
    mag_out = alpha * ext
    if beta:
        mag_out = np.maximum(mag_out - beta, 0.0)
    return par_sign[chk_local] * sgn * mag_out


def _flooding_loop(L: np.ndarray, code: Code, max_iters: int, alpha: float,
                   lam: float, beta: float
                   ) -> tuple[np.ndarray, bool, int, np.ndarray]:
    """Damped / offset min-sum, flooding schedule (the analyzer's own).

    Same shape as `_bp_loop`'s min-sum branch; the only additions are the
    damping `c2v <- (1-lam)*c2v_old + lam*c2v_minsum` and the offset beta.
    lam = 1, beta = 0 reproduces production's branch exactly.
    """
    chk, var = code.edge_chk, code.edge_var
    cs, vo, vs = code.chk_starts, code.var_order, code.var_starts
    c2v = np.zeros(chk.size, np.float64)
    Ltot = L.copy()
    n_iters = 0
    syndrome_ok = False
    for it in range(max_iters + 1):
        hard = (Ltot < 0).astype(np.uint8)
        if not np.bitwise_xor.reduceat(hard[var], cs).any():
            syndrome_ok = True
            break
        if it == max_iters:
            break
        n_iters = it + 1
        fresh = _minsum_c2v(Ltot[var] - c2v, chk, cs, alpha, beta)
        c2v = (1.0 - lam) * c2v + lam * fresh
        Ltot = L + np.add.reduceat(c2v[vo], vs)
    return ((Ltot < 0).astype(np.uint8), bool(syndrome_ok), int(n_iters),
            Ltot)


def _layered_loop(L: np.ndarray, code: Code, max_iters: int, alpha: float,
                  lam: float, beta: float, group_checks: int
                  ) -> tuple[np.ndarray, bool, int, np.ndarray]:
    """Serial (layered) check-node schedule, simplest correct form.

    Checks are processed in consecutive groups of `group_checks` (one lifted
    block by default); each group's c2v update lands in Ltot before the next
    group reads it.  Edges are sorted by check, so a group is one contiguous
    edge slice.
    """
    chk, var = code.edge_chk, code.edge_var
    cs, vo, vs = code.chk_starts, code.var_order, code.var_starts
    n_checks = cs.size
    n_edges = chk.size
    bounds = list(range(0, n_checks, group_checks)) + [n_checks]
    c2v = np.zeros(n_edges, np.float64)
    Ltot = L.copy()
    n_iters = 0
    syndrome_ok = False
    for it in range(max_iters + 1):
        hard = (Ltot < 0).astype(np.uint8)
        if not np.bitwise_xor.reduceat(hard[var], cs).any():
            syndrome_ok = True
            break
        if it == max_iters:
            break
        n_iters = it + 1
        for c0, c1 in zip(bounds[:-1], bounds[1:]):
            e0 = int(cs[c0])
            e1 = n_edges if c1 >= n_checks else int(cs[c1])
            if e1 <= e0:
                continue
            edge_var = var[e0:e1]
            old = c2v[e0:e1]
            fresh = _minsum_c2v(Ltot[edge_var] - old,
                                chk[e0:e1].astype(np.int64) - c0,
                                cs[c0:c1] - e0, alpha, beta)
            new = (1.0 - lam) * old + lam * fresh
            np.add.at(Ltot, edge_var, new - old)
            c2v[e0:e1] = new
        Ltot = L + np.add.reduceat(c2v[vo], vs)
    return ((Ltot < 0).astype(np.uint8), bool(syndrome_ok), int(n_iters),
            Ltot)


def bp(mother: Mother, code: Code | None = None, iters: int = 60, *,
       mode: str = "minsum-then-sp", alpha: float = BP_ALPHA,
       lam: float | None = None, beta: float | None = None,
       group_checks: int = LAYERED_GROUP_CHECKS) -> BpOut:
    """Belief propagation over the mother code, EXTERNAL sign in and out.

    `ldpc._bp_loop` works in the internal (negated) sign; this is its only
    caller in the analyzer and it negates on the way in and on the way out.
    +-inf becomes +-LLR_KNOWN and finite channel LLRs are clipped at
    LLR_CLIP, exactly as `ldpc.decode` does — the bounded-LLR invariant.

    Posterior identity (DESIGN §6): `posterior == clipped_external(llr) +
    extrinsic` and `(posterior > 0) == hard`.  Reliability is |posterior|.
    """
    if mode not in MODES:
        raise ValueError(f"mother.bp: unknown mode {mode!r}")
    code = code_of(mother) if code is None else code
    external = clipped_external(mother.llr)
    internal = -external
    lam_v = 1.0 if lam is None else float(lam)
    beta_v = 0.0 if beta is None else float(beta)
    passes = 1
    if mode == "minsum-then-sp":
        hard, ok, n_iters, total = ldpc._bp_loop(
            internal, code, iters, alpha, False)
        if not ok and iters > 0:
            hard, ok, n2, total = ldpc._bp_loop(
                internal, code, iters, alpha, True)
            n_iters += n2
            passes = 2
    elif mode in ("sp", "minsum"):
        hard, ok, n_iters, total = ldpc._bp_loop(
            internal, code, iters, alpha, mode == "sp")
    elif mode == "layered":
        hard, ok, n_iters, total = _layered_loop(
            internal, code, iters, alpha, lam_v, beta_v, group_checks)
    else:  # damped, damped-offset
        hard, ok, n_iters, total = _flooding_loop(
            internal, code, iters, alpha, lam_v, beta_v)
    syn = syndrome(hard, code)
    return BpOut(hard=hard.astype(np.uint8), syndrome=syn,
                 unsat=int(np.count_nonzero(syn)), posterior=-total,
                 n_iters=int(n_iters), syndrome_ok=bool(ok), passes=passes,
                 mode=mode)


def posterior_summary(out: BpOut, mother: Mother) -> dict[str, float]:
    """Blind posterior descriptors, over TRANSMITTED positions only."""
    post = np.abs(out.posterior[mother.transmitted])
    finite = post[post < LLR_KNOWN]
    return {
        "mean_abs_posterior": float(finite.mean()) if finite.size else 0.0,
        "fraction_clipped": float(np.mean(post >= LLR_CLIP)),
        "n_transmitted": int(post.size),
    }


def codeword_digest(hard: np.ndarray) -> bytes:
    return hashlib.blake2b(np.packbits(np.asarray(hard, np.uint8)).tobytes(),
                           digest_size=16).digest()


def gate(hard: np.ndarray, mother: Mother, bank: Bank, exposure: Exposure,
         *, notes: dict | None = None) -> tuple[bool, np.ndarray | None]:
    """The certificate gate (DESIGN §0): syndrome, then the priced CRC.

    A non-codeword never reaches the CRC.  Every CRC consultation costs
    2^-32; candidates are de-duplicated by codeword digest and the run
    refuses a consult that would break the exposure bound.

    `notes["consulted_new"]` is 1 when THIS call was the first consult of
    THIS codeword and 0 when the digest had already been paid for; it is
    the rung's own charge and it is a pure function of the rung's own
    proposals.  The RUNNING TOTAL is deliberately NOT written here (W3):
    `exposure.expected_false` at the moment a rung reached the gate is a
    global counter, so on threads it records the interleaving rather than
    anything about the rung.  Exposure is a RUN-LEVEL column
    (`Ledger.header['exposure_expected_false']`).
    """
    reason: str | None = None
    active = mother.active
    if tile_codec.bank_active_bits(bank) != active:
        raise ValueError("mother.gate: bank does not match the mother frame")
    hard = np.asarray(hard, np.uint8)
    syn = syndrome(hard, code_of(mother))
    if syn.any():
        reason = "syndrome_failed"
    elif active < mother.k_bits and hard[active:mother.k_bits].any():
        # A mother codeword whose SHORTENED window is non-zero is not a
        # printed frame at all.  BP can never produce one (the window is
        # pinned at -inf), but a list proposer (OSD, L4/L6) can, and its CRC
        # would be an unpriced false-accept channel.  Refused before the CRC,
        # so it costs no exposure.
        reason = "shortening_violated"
    else:
        digest = codeword_digest(hard)
        n_new = 0 if digest in exposure.consulted else 1
        if exposure.would_exceed(n_new):
            reason = "exposure_exceeded"
        else:
            exposure.consulted.add(digest)
            frame = hard[:active]
            user = frame[:active - tile_codec.CRC_BITS]
            crc_ok = bool(np.array_equal(
                frame[active - tile_codec.CRC_BITS:],
                tile_codec.crc32_bits(user)))
            if crc_ok:
                if notes is not None:
                    notes["consulted_new"] = n_new
                return True, user.astype(np.uint8)
            reason = "crc_failed"
            if notes is not None:
                notes["consulted_new"] = n_new
    if notes is not None:
        notes["refusal"] = reason
    return False, None


def consult_cost(exposure: Exposure) -> float:
    return exposure.distinct * EXPOSURE_PER_CONSULT

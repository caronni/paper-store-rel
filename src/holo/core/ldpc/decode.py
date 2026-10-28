"""holo inner-FEC encoder + BP decoder (HOLO-DESIGN §3 F5).

PROVENANCE: ported from src/paperholo/ldpc.py (encode, _bp_loop, decode);
that module's docstring is the normative record, including the measured
retry rationale: at the r0700 BSC gate p=0.035 (500 trials) min-sum alone
read 4.0% BLER, sum-product 1.6% — so decode() runs normalized min-sum
first (fast path, early exit on zero syndrome) and ONE exact sum-product
retry from the channel LLRs on syndrome failure.

LLR SIGN CONVENTION (house-wide): POSITIVE = bit 1, llr = log P(1)/P(0);
0.0 = erasure (first-class, propagates natively); +-inf = known bit
(mapped to +-1e9 internally so no inf-inf NaNs). Internally the loop
negates into the textbook log P(0)/P(1) convention for the min-sum sign
algebra.

decode() never certifies payload: syndrome_ok gates H@c == 0 only —
CRC certification is tile.decode_tile's job.
"""
from __future__ import annotations

import numpy as np

from .construct import Code, load_code

LLR_KNOWN = 1e9      # internal finite stand-in for +-inf channel LLRs
LLR_CLIP = 20.0      # finite channel LLRs are clipped to +-LLR_CLIP


def encode(info_bits: np.ndarray, rate_id: str) -> np.ndarray:
    """Systematic encode: codeword = [info u | parity p], parity by the IRA
    accumulator back-substitution p_j = p_{j-1} XOR s_j (s = H_d @ info),
    vectorized as one cumulative XOR over the whole parity vector.
    Returns the (n_bits,) uint8 codeword."""
    code = load_code(rate_id)
    spec = code.spec
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
             sum_product: bool) -> tuple[np.ndarray, bool, int, np.ndarray]:
    """Flooding BP loop over the edge arrays, internal convention
    (positive = bit 0). Check update: normalized min-sum (alpha) or exact
    sum-product (tanh rule). Early exit on zero syndrome.

    Returns ``(hard, syndrome_ok, n_iters, Ltot)``; ``Ltot`` is the total
    (a-posteriori) per-variable belief the hard decisions were sliced
    from, still in the internal convention, so ``Ltot - L`` is exactly the
    accumulated check-to-variable extrinsic."""
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
                                           -0.999_999_999_999,
                                           0.999_999_999_999))
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
    return ((Ltot < 0).astype(np.uint8), bool(syndrome_ok), int(n_iters),
            Ltot)


def _run(llr: np.ndarray, rate_id: str, max_iters: int,
         alpha: float) -> tuple[bool, np.ndarray, int, np.ndarray]:
    """The hybrid schedule, returning the last pass's beliefs as well."""
    code = load_code(rate_id)
    n = code.spec.n_bits
    x = np.asarray(llr, np.float64).ravel()
    if x.size != n:
        raise ValueError(f"llr must be ({n},), got {x.shape}")
    L = np.clip(x, -LLR_CLIP, LLR_CLIP)
    L[np.isposinf(x)] = LLR_KNOWN
    L[np.isneginf(x)] = -LLR_KNOWN
    L = -L                                   # internal: positive = bit 0
    hard, syndrome_ok, n_iters, total = _bp_loop(
        L, code, max_iters, alpha, False)
    if not syndrome_ok and max_iters > 0:
        hard, syndrome_ok, n2, total = _bp_loop(
            L, code, max_iters, alpha, True)
        n_iters += n2
    # House convention, and extrinsic of the CLIPPED channel input the loop
    # actually consumed: the caller may not subtract its own unclipped LLR.
    return syndrome_ok, hard, n_iters, L - total


def decode(llr: np.ndarray, rate_id: str, max_iters: int = 60,
           alpha: float = 0.8) -> tuple[bool, np.ndarray, int]:
    """Hybrid BP decode: normalized min-sum first; on syndrome failure ONE
    exact sum-product retry from the channel LLRs (see module docstring).

    llr: (n_bits,) float, HOUSE convention (positive = bit 1); 0.0 =
    erasure, +-inf = known bit. Finite inputs are clipped to +-LLR_CLIP.
    Returns (ok, hard_bits (n,) uint8, n_iters); ok certifies H@c == 0
    only; n_iters = total iterations across both passes, 0 when the
    channel hard decisions already satisfy every check.
    """
    syndrome_ok, hard, n_iters, _extrinsic = _run(
        llr, rate_id, max_iters, alpha)
    return syndrome_ok, hard, n_iters


def decode_soft(llr: np.ndarray, rate_id: str, max_iters: int = 60,
                alpha: float = 0.8
                ) -> tuple[bool, np.ndarray, int, np.ndarray]:
    """:func:`decode` plus the decoder's per-variable EXTRINSIC LLRs.

    The fourth element is ``posterior - channel`` in the house convention
    (positive = bit 1) for the pass whose hard decisions are returned, so
    it carries only what the code graph added.  It is exactly zero
    wherever BP never ran (a channel hard decision that already satisfied
    every check).  Numerics are bit-identical to :func:`decode`; the extra
    array is the only difference, which is what makes an iterative demapper
    a pure addition to the decode path (soft iteration INSIDE one attempt,
    RECEIVE-DESIGN 6.2a).
    """
    return _run(llr, rate_id, max_iters, alpha)

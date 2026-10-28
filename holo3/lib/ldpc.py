from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

N_BITS = 4096
Z = 64
LLR_KNOWN = 1e9
LLR_CLIP = 20.0

_DATA_DIR = Path(__file__).resolve().parent / "ldpc_data"
_RATE_IDS = ("r0547", "r0550", "r0625", "r0700", "r0775", "r0850")


@dataclass(frozen=True, eq=False)
class Code:
    rate_id: str
    k_bits: int
    n_bits: int
    edge_chk: np.ndarray
    edge_var: np.ndarray
    chk_starts: np.ndarray
    var_order: np.ndarray
    var_starts: np.ndarray
    enc_info_col: np.ndarray
    enc_rows: np.ndarray
    enc_row_starts: np.ndarray


def _expand_edges(pi: np.ndarray, heavy_rows: np.ndarray,
                  heavy_shifts: np.ndarray, light_rows: np.ndarray,
                  light_shifts: np.ndarray, z: int, k: int, m: int
                  ) -> tuple[np.ndarray, np.ndarray]:
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
    jj = np.arange(m, dtype=np.int64)
    chk_l.append(jj)
    var_l.append(k + jj)
    chk_l.append(jj[1:])
    var_l.append(k + jj[:-1])
    return (np.concatenate(chk_l).astype(np.int32),
            np.concatenate(var_l).astype(np.int32))


def _load_code(rate_id: str) -> Code:
    d = json.loads((_DATA_DIR / f"{rate_id}.json").read_text())
    n = int(d["n_bits"])
    z = int(d["z"])
    k = int(d["k_bits"])
    m = n - k
    pi = np.asarray(d["pi"], dtype=np.int64)
    heavy_rows = np.asarray(d["heavy_rows"], dtype=np.int64)
    heavy_shifts = np.asarray(d["heavy_shifts"], dtype=np.int64)
    light_rows = np.asarray(d["light_rows"], dtype=np.int64)
    light_shifts = np.asarray(d["light_shifts"], dtype=np.int64)
    chk, var = _expand_edges(pi, heavy_rows, heavy_shifts,
                             light_rows, light_shifts, z, k, m)
    order = np.lexsort((var, chk))
    chk, var = chk[order], var[order]
    chk_counts = np.bincount(chk, minlength=m)
    chk_starts = np.concatenate(([0], np.cumsum(chk_counts)[:-1]))
    var_order = np.argsort(var, kind="stable")
    var_counts = np.bincount(var, minlength=n)
    var_starts = np.concatenate(([0], np.cumsum(var_counts)[:-1]))
    is_info = var < k
    ic, iv = chk[is_info].astype(np.int64), var[is_info].astype(np.int64)
    io = np.argsort(ic, kind="stable")
    ic, iv = ic[io], iv[io]
    enc_rows, first = np.unique(ic, return_index=True)
    arrays = (chk, var, chk_starts.astype(np.int64),
              var_order.astype(np.int64), var_starts.astype(np.int64),
              iv, enc_rows, first.astype(np.int64))
    for arr in arrays:
        arr.setflags(write=False)
    return Code(rate_id, k, n, *arrays)


CODES: dict[str, Code] = {rate_id: _load_code(rate_id)
                          for rate_id in _RATE_IDS}


def encode(info: np.ndarray, code: Code) -> np.ndarray:
    k = code.k_bits
    m = code.n_bits - k
    u = np.asarray(info).astype(np.uint8).ravel()
    s = np.zeros(m, np.uint8)
    seg = np.bitwise_xor.reduceat(u[code.enc_info_col], code.enc_row_starts)
    s[code.enc_rows] = seg
    p = np.bitwise_xor.accumulate(s)
    return np.concatenate([u, p])


def _bp_loop(L: np.ndarray, code: Code, max_iters: int, alpha: float,
             sum_product: bool) -> tuple[np.ndarray, bool, int, np.ndarray]:
    chk, var = code.edge_chk, code.edge_var
    cs, vo, vs = code.chk_starts, code.var_order, code.var_starts
    E = chk.size
    epos = np.arange(E, dtype=np.int64)
    c2v = np.zeros(E, dtype=np.float64)
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


def decode(llr: np.ndarray, code: Code, max_iters: int, alpha: float = 0.8
           ) -> tuple[bool, np.ndarray, int, np.ndarray]:
    x = np.asarray(llr, np.float64).ravel()
    L = np.clip(x, -LLR_CLIP, LLR_CLIP)
    L[np.isposinf(x)] = LLR_KNOWN
    L[np.isneginf(x)] = -LLR_KNOWN
    L = -L
    hard, syndrome_ok, n_iters, total = _bp_loop(
        L, code, max_iters, alpha, False)
    if not syndrome_ok and max_iters > 0:
        hard, syndrome_ok, n2, total = _bp_loop(
            L, code, max_iters, alpha, True)
        n_iters += n2
    return syndrome_ok, hard, n_iters, L - total

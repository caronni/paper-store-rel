# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/channels.py
"""Per-task channel simulation with the PRODUCTION decoder.  A task =
(rate_id, channel, params, trial range) -> counts.  Seeds: trial t uses
np.random.default_rng(BASE[channel] + t); the same t gives the same info
bits and channel draw for every code and point of that channel (common
random numbers).  LLR house convention: POSITIVE = bit 1."""
from __future__ import annotations
import math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codes  # noqa: E402  (registers every code in this process)
from holo.core.ldpc.decode import decode, encode  # noqa: E402

BASE = {"bsc": 100_000, "awgn": 200_000, "eras": 300_000, "accom": 400_000,
        "record": 0}   # "record" replicates tests/test_ldpc.py seeds (50_000/60_000 + t)
N = 4096


def h2(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def bsc_capacity_p(rate: float) -> float:
    """p with 1 - h2(p) = rate (bisection)."""
    lo, hi = 1e-9, 0.5
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - h2(mid) > rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


_GH = np.polynomial.hermite.hermgauss(160)


def biawgn_capacity(sigma: float) -> float:
    """C = 1 - E[log2(1 + e^{-L})], L ~ N(2/s^2, 4/s^2) (Gauss-Hermite)."""
    x, w = _GH
    mu, sd = 2 / sigma**2, 2 / sigma
    L = mu + sd * math.sqrt(2) * x
    val = np.logaddexp(0.0, -L) / math.log(2)
    return 1 - float((w * val).sum() / math.sqrt(math.pi))


def biawgn_shannon_esn0_db(rate: float) -> float:
    lo, hi = 0.05, 5.0     # sigma
    for _ in range(200):
        mid = (lo + hi) / 2
        if biawgn_capacity(mid) > rate:
            lo = mid
        else:
            hi = mid
    s = (lo + hi) / 2
    return 10 * math.log10(1 / (2 * s * s))


def hard_llr(rx: np.ndarray, p: float) -> np.ndarray:
    mag = math.log((1 - p) / p)
    return mag * (2.0 * rx.astype(np.float64) - 1.0)


def run_task(rid: str, channel: str, params: dict, t0: int, n_trials: int) -> dict:
    sp = codes.spec(rid); k = sp.k_bits; m = sp.m_bits
    base = BASE[channel]
    if channel == "record":
        base = int(params["seed_base"])
    fails = und = 0; iters = 0; iters_ok = 0; n_ok = 0
    for t in range(t0, t0 + n_trials):
        g = np.random.default_rng(base + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        known = None
        if channel == "accom" and params["variant"] == "shorten":
            info[k - 120:] = 0
        cw = encode(info, rid)
        if channel == "bsc":
            p = params["p"]
            rx = cw ^ (g.random(N) < p)
            llr = hard_llr(rx, p)
        elif channel == "record":
            p = params["p"]
            rx = cw ^ (g.random(N) < p)
            llr = params["mag"] * (2.0 * rx.astype(np.float64) - 1.0)
        elif channel == "awgn":
            sigma = params["sigma"]
            x = 1.0 - 2.0 * cw
            y = x + sigma * g.standard_normal(N)
            llr = -2.0 * y / (sigma * sigma)
        elif channel == "eras":
            p, eps = params["p"], params["eps"]
            rx = cw ^ (g.random(N) < p)
            llr = hard_llr(rx, p)
            llr[g.random(N) < eps] = 0.0
        elif channel == "accom":
            p = params["p"]
            rx = cw ^ (g.random(N) < p)
            llr = hard_llr(rx, p)
            v = params["variant"]
            if v == "shorten":
                llr[k - 120:k] = -np.inf
            elif v == "punct_last":
                llr[N - 120:] = 0.0
            elif v == "punct_even":
                pos = k + ((np.arange(120) + 0.5) * m / 120).astype(np.int64)
                llr[pos] = 0.0
            elif v == "mother":
                pass
            else:
                raise ValueError(v)
        else:
            raise ValueError(channel)
        ok, hard, n_it = decode(llr, rid)
        good = ok and np.array_equal(hard, cw)
        if not good:
            fails += 1
            if ok:
                und += 1
        else:
            iters_ok += n_it; n_ok += 1
        iters += n_it
    return {"rid": rid, "channel": channel, "params": params, "t0": t0, "n": n_trials,
            "fails": fails, "undetected": und, "iters": iters, "iters_ok": iters_ok, "n_ok": n_ok}


def sanity() -> None:
    """Noiseless checks of every convention before any sweep."""
    for rid in codes.ALL:
        sp = codes.spec(rid); g = np.random.default_rng(1)
        info = g.integers(0, 2, sp.k_bits).astype(np.uint8); cw = encode(info, rid)
        ok, hard, n_it = decode(hard_llr(cw, 0.01), rid)
        assert ok and n_it == 0 and np.array_equal(hard, cw), rid
        ok, hard, n_it = decode(-2.0 * (1.0 - 2.0 * cw) / 0.5**2, rid)   # awgn sign, noiseless
        assert ok and n_it == 0 and np.array_equal(hard, cw), ("awgn sign", rid)
        llr = hard_llr(cw, 0.01); llr[::20] = 0.0   # 5 % erased (1/7 exceeds r0850 erasure capacity)
        ok, hard, _ = decode(llr, rid)
        assert ok and np.array_equal(hard, cw), ("erasure", rid)
    print("sanity OK: hard-LLR, AWGN sign (bit 1 -> y<0 -> llr>0), erasure=0 on all", len(codes.ALL), "codes")


if __name__ == "__main__":
    sanity()

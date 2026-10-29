"""Single-thread throughput: production decode() vs decode_batch at several B.

Regimes (BIAWGN, LLR = -2y/s^2, house convention):
  conv : the frozen recipe's ~10 % BLER point (mixed iteration counts)
  fail : well below threshold (every trial runs 60 min-sum + 60 SP iters)
Run:  PYTHONPATH=src:. OMP_NUM_THREADS=1 env/bin/python .../bench_single.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "harness"))
import codes as hcodes  # noqa: E402,F401
from holo.core.ldpc import construct  # noqa: E402
from holo.core.ldpc.decode import decode, encode  # noqa: E402
from fastdecode import decode_batch, decode_batch_simple  # noqa: E402

N = construct.N_BITS
POINTS = {  # rid: (conv es/n0 dB ~ 10 % BLER from results.json, fail es/n0 dB)
    "r0406": (-3.1, -4.25),   # k = 1664
    "r0550": (-1.35, -2.25),  # k = 2240
}


def llrs(rid: str, esn0_db: float, n: int, seed: int) -> np.ndarray:
    k = construct.LADDER[rid].k_bits
    s = np.sqrt(1 / (2 * 10 ** (esn0_db / 10)))
    out = np.empty((n, N))
    for t in range(n):
        g = np.random.default_rng(seed + t)
        cw = encode(g.integers(0, 2, k).astype(np.uint8), rid)
        out[t] = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
    return out


def run(fn, X, B):
    t0, c0 = time.perf_counter(), time.process_time()
    it = 0
    if B is None:
        for x in X:
            it += fn(x)[2]
    else:
        for s in range(0, len(X), B):
            it += int(fn(X[s:s + B])[2].sum())
    return len(X) / (time.perf_counter() - t0), it / len(X), time.process_time() - c0


def main() -> None:
    n_trials = int(os.environ.get("BENCH_N", "256"))   # conv; fail uses half
    rows = []
    for rid, (es_conv, es_fail) in POINTS.items():
        code = construct.load_code(rid)
        for regime, es in (("conv", es_conv), ("fail", es_fail)):
            nt = n_trials if regime == "conv" else n_trials // 2
            X = llrs(rid, es, nt, 900_000)
            prod, mean_it, _ = run(lambda x: decode(x, rid), X, None)
            rows.append({"rid": rid, "k": code.spec.k_bits, "regime": regime, "es": es,
                         "B": "prod", "dec_s": round(prod, 2), "mean_iters": round(mean_it, 1),
                         "speedup": 1.0})
            for kern, B in ([(decode_batch, b) for b in (1, 8, 32, 64, 128)]
                            + [(decode_batch_simple, 64)]):
                r, mi, _ = run(lambda x: kern(x, code), X, B)
                rows.append({"rid": rid, "k": code.spec.k_bits, "regime": regime, "es": es,
                             "B": B if kern is decode_batch else f"simple-{B}",
                             "dec_s": round(r, 2), "mean_iters": round(mi, 1),
                             "speedup": round(r / prod, 2)})
            for r in rows[-7:]:
                print(r, flush=True)
    (HERE / "bench_single.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()

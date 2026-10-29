# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/verify/verify_bench.py
"""Reviewer's benchmark re-run: one point (r0550, BIAWGN -1.35 dB), same trials in
every arm, warm-up excluded, CPU (thread_time / process_time) and wall reported,
iteration sums compared across arms.  Then pools: W processes vs W threads,
batched kernel and production, CPU per decode from inside the tasks."""
from __future__ import annotations
import os
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(v, "1")
import json, sys, time, multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; FAST = HERE.parent
sys.path.insert(0, str(FAST)); sys.path.insert(0, str(FAST.parents[1] / "harness"))
import codes as hcodes  # noqa
from holo.core.ldpc import construct
from holo.core.ldpc.decode import decode, encode
from fastdecode import decode_batch, _layout

N = construct.N_BITS
RID, ES, SEED = "r0550", -1.35, 7_777_000


def trials(t0, n):
    k = construct.LADDER[RID].k_bits; s = np.sqrt(1 / (2 * 10 ** (ES / 10)))
    X = np.empty((n, N))
    for i in range(n):
        g = np.random.default_rng(SEED + t0 + i)
        cw = encode(g.integers(0, 2, k).astype(np.uint8), RID)
        X[i] = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
    return X


def warm():
    code = construct.load_code(RID); _layout(code)
    X = trials(10**6, 4); decode(X[0], RID); decode_batch(X, code)


def task(kind, t0, n):
    X = trials(t0, n)
    c0 = time.thread_time()
    if kind == "prod":
        r = [decode(x, RID) for x in X]; it = sum(v[2] for v in r); ok = sum(bool(v[0]) for v in r)
    else:
        o, h, nit = decode_batch(X, construct.load_code(RID)); it = int(nit.sum()); ok = int(o.sum())
    return {"cpu": time.thread_time() - c0, "it": it, "ok": ok, "n": n}


def single(n=256, B=64):
    warm()
    X = trials(0, n); code = construct.load_code(RID)
    out = {}
    for arm in ("prod", "batch", "prod", "batch"):   # two alternating reps
        w0, c0 = time.perf_counter(), time.thread_time()
        if arm == "prod":
            r = [decode(x, RID) for x in X]; it = sum(v[2] for v in r); ok = sum(bool(v[0]) for v in r)
        else:
            it = ok = 0
            for s in range(0, n, B):
                o, h, nit = decode_batch(X[s:s + B], code); it += int(nit.sum()); ok += int(o.sum())
        out.setdefault(arm, []).append({"wall_ms_dec": 1e3 * (time.perf_counter() - w0) / n,
                                        "cpu_ms_dec": 1e3 * (time.thread_time() - c0) / n,
                                        "iters": it, "ok": ok})
    return out


def pooled(kind, mode, W, n_dec, chunk):
    jobs = [(kind, 20_000 + s, chunk) for s in range(0, n_dec, chunk)]
    if mode == "proc":
        ex = ProcessPoolExecutor(W, mp_context=mp.get_context("spawn"), initializer=warm)
        list(ex.map(time.sleep, [0.3] * W))            # workers started + warmed
    else:
        warm(); ex = ThreadPoolExecutor(W)
    t0 = time.perf_counter()
    res = list(ex.map(task, *zip(*jobs)))
    wall = time.perf_counter() - t0
    ex.shutdown()
    return {"kind": kind, "mode": mode, "W": W, "chunk": chunk, "n": n_dec, "wall_s": round(wall, 2),
            "dec_s": round(n_dec / wall, 1), "cpu_ms_dec": round(1e3 * sum(r["cpu"] for r in res) / n_dec, 2),
            "iters": sum(r["it"] for r in res), "ok": sum(r["ok"] for r in res)}


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "single":
        print(json.dumps(single(), indent=1))
    else:
        W = int(sys.argv[2]); kind = sys.argv[3]; mode = sys.argv[4]
        print(json.dumps(pooled(kind, mode, W, int(sys.argv[5]), 50)))

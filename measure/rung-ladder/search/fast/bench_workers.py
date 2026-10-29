"""Worker-mode benchmark on the free-threaded interpreter.

Workload: N_DEC decodes of one code at one BIAWGN point (default r0406 = k 1664
at its ~10 % BLER point, -3.1 dB), in tasks of CHUNK trials; each task
regenerates its trials from seeds (default_rng(SEED + t), encode, channel) and
decodes them either one by one with production decode() ("prod") or with
decode_batch in batches of CHUNK ("batch").  Every mode returns the per-trial
(ok, n_iters, hard-bits sha) so the modes are checked against each other.

Modes:  proc  = ProcessPoolExecutor(P, spawn)
        thr   = ThreadPoolExecutor(T) in this process
        hyb   = ProcessPoolExecutor(P2) whose tasks each run T2 threads

Reports wall (from first submit; pool start-up excluded -- workers are warmed
by an initializer), total CPU (self + reaped children), CPU/wall, and peak RSS
per worker process (ru_maxrss).

Run:  PYTHONPATH=src:. env/bin/python .../bench_workers.py [--n 2800] [--chunk 50]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import resource
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # inherited by spawned workers

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "harness"))
import codes as hcodes  # noqa: E402,F401  (registers candidates)
from holo.core.ldpc import construct  # noqa: E402
from holo.core.ldpc.decode import decode, encode  # noqa: E402
from fastdecode import decode_batch, _layout  # noqa: E402

N = construct.N_BITS
SEED = 5_000_000


def _warm(rid: str) -> None:
    _layout(construct.load_code(rid))


def trials(rid: str, esn0_db: float, t0: int, n: int) -> np.ndarray:
    k = construct.LADDER[rid].k_bits
    s = np.sqrt(1 / (2 * 10 ** (esn0_db / 10)))
    X = np.empty((n, N))
    for i, t in enumerate(range(t0, t0 + n)):
        g = np.random.default_rng(SEED + t)
        cw = encode(g.integers(0, 2, k).astype(np.uint8), rid)
        X[i] = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
    return X


def task(kind: str, rid: str, es: float, t0: int, n: int) -> dict:
    c0 = time.thread_time()
    X = trials(rid, es, t0, n)
    if kind == "prod":
        out = [decode(x, rid) for x in X]
        res = [(bool(o), int(i), hashlib.blake2b(h.tobytes(), digest_size=8).hexdigest())
               for o, h, i in out]
    else:
        ok, hard, nit = decode_batch(X, construct.load_code(rid))
        res = [(bool(ok[j]), int(nit[j]),
                hashlib.blake2b(hard[j].tobytes(), digest_size=8).hexdigest())
               for j in range(n)]
    return {"t0": t0, "res": res, "pid": os.getpid(), "cpu": time.thread_time() - c0,
            "maxrss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20}


def task_threads(kind: str, rid: str, es: float, t0: int, n: int, n_thr: int) -> dict:
    """Hybrid-mode task: split the chunk over n_thr threads in this process."""
    step = -(-n // n_thr)
    with ThreadPoolExecutor(n_thr) as ex:
        parts = list(ex.map(lambda s: task(kind, rid, es, t0 + s, min(step, n - s)),
                            range(0, n, step)))
    res = [r for p in parts for r in p["res"]]
    return {"t0": t0, "res": res, "pid": os.getpid(), "cpu": sum(p["cpu"] for p in parts),
            "maxrss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20}


def cpu_now() -> float:
    a = resource.getrusage(resource.RUSAGE_SELF)
    b = resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime + a.ru_stime + b.ru_utime + b.ru_stime


def run_mode(mode: str, kind: str, rid: str, es: float, n_dec: int, chunk: int,
             par: int, thr: int) -> dict:
    ctx = mp.get_context("spawn")
    c0 = cpu_now()
    if mode == "thr":
        _warm(rid)
        ex = ThreadPoolExecutor(par)
        t_start = time.perf_counter()
        futs = [ex.submit(task, kind, rid, es, t0, min(chunk, n_dec - t0))
                for t0 in range(0, n_dec, chunk)]
    else:
        ex = ProcessPoolExecutor(par, mp_context=ctx, initializer=_warm, initargs=(rid,))
        list(ex.map(time.sleep, [0.0] * par))       # force every worker up
        time.sleep(1.0)
        t_start = time.perf_counter()
        if mode == "proc":
            futs = [ex.submit(task, kind, rid, es, t0, min(chunk, n_dec - t0))
                    for t0 in range(0, n_dec, chunk)]
        else:
            big = chunk * thr
            futs = [ex.submit(task_threads, kind, rid, es, t0, min(big, n_dec - t0), thr)
                    for t0 in range(0, n_dec, big)]
    out = [f.result() for f in futs]
    wall = time.perf_counter() - t_start
    ex.shutdown(wait=True)
    cpu = cpu_now() - c0                      # incl. worker start-up/imports
    task_cpu = sum(o["cpu"] for o in out)     # thread CPU inside the tasks
    res = sorted((o["t0"], o["res"]) for o in out)
    flat = [r for _, rr in res for r in rr]
    rss = {}
    for o in out:
        rss[o["pid"]] = max(rss.get(o["pid"], 0.0), o["maxrss_mb"])
    digest = hashlib.blake2b(json.dumps(flat).encode(), digest_size=8).hexdigest()
    return {"mode": mode, "kind": kind, "par": par, "thr": thr, "n": len(flat),
            "chunk": chunk, "wall_s": round(wall, 2), "cpu_s": round(cpu, 1),
            "dec_per_s": round(len(flat) / wall, 1),
            "task_cpu_ms_per_dec": round(1e3 * task_cpu / len(flat), 1),
            "task_cpu_over_wall": round(task_cpu / wall, 2),
            "rss_mb_per_proc": round(float(np.median(list(rss.values()))), 0),
            "n_procs": len(rss), "ok": sum(1 for r in flat if r[0]),
            "mean_iters": round(float(np.mean([r[1] for r in flat])), 1),
            "outcome_digest": digest}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rid", default="r0406")
    ap.add_argument("--es", type=float, default=-3.1)
    ap.add_argument("--n", type=int, default=2800)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--kinds", default="batch,prod")
    ap.add_argument("--modes", default="proc:14:1,thr:14:1,hyb:7:2")
    ap.add_argument("--out", default=str(HERE / "bench_workers.json"))
    a = ap.parse_args()
    rows = []
    for kind in a.kinds.split(","):
        for m in a.modes.split(","):
            mode, par, thr = m.split(":")
            r = run_mode(mode, kind, a.rid, a.es, a.n, a.chunk, int(par), int(thr))
            rows.append(r)
            print(json.dumps(r), flush=True)
            Path(a.out).write_text(json.dumps(rows, indent=1))
    digests = {r["outcome_digest"] for r in rows}
    print("outcome digests identical across every mode and kind:", len(digests) == 1)


if __name__ == "__main__":
    main()

# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/tasks_fast.py
"""Drop-in batched twins of the per-task trial loops:

    run_chan_fast(rid, channel, params, t0, n, batch=64)
        == search/common.run_chan(rid, channel, params, t0, n)   (bsc/awgn/eras/robust,
           incl. the und_w diagnostic of every syndrome-valid wrong decode)
    run_task_fast(rid, channel, params, t0, n_trials, batch=64)
        == harness/channels.run_task(rid, channel, params, t0, n_trials)  (all harness channels)

Same seeds (trial t: np.random.default_rng(BASE[channel] + t)), same draw
order inside each trial, same channel maps, same counting; only the decode
is batched (fastdecode.decode_batch over `batch` trials at a time).  The
returned dicts are equal to the originals' -- test_tasks_fast.py checks it
dict-for-dict on every channel.  The generation code is a COPY of those
loops (neither file is ours to edit); if either changes, re-run
test_tasks_fast.py before trusting this file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parents[1] / "harness"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import channels as ch  # noqa: E402  (imports harness codes: registers codes)
from holo.core.ldpc import construct  # noqa: E402
from holo.core.ldpc.decode import encode  # noqa: E402
from fastdecode import decode_batch  # noqa: E402

N = construct.N_BITS
BASE_ROBUST = 500_000          # == search/common.BASE_ROBUST (checked in the test)


def _gen_task(rid: str, channel: str, params: dict, t: int, k: int, m: int,
              base: int) -> tuple[np.ndarray, np.ndarray]:
    """One trial of channels.run_task's loop body up to (not incl.) decode."""
    g = np.random.default_rng(base + t)
    info = g.integers(0, 2, k).astype(np.uint8)
    if channel == "accom" and params["variant"] == "shorten":
        info[k - 120:] = 0
    cw = encode(info, rid)
    if channel == "bsc":
        p = params["p"]
        rx = cw ^ (g.random(N) < p)
        llr = ch.hard_llr(rx, p)
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
        llr = ch.hard_llr(rx, p)
        llr[g.random(N) < eps] = 0.0
    elif channel == "accom":
        p = params["p"]
        rx = cw ^ (g.random(N) < p)
        llr = ch.hard_llr(rx, p)
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
    return llr, cw


def _count(llrs: np.ndarray, cws: np.ndarray, code, batch: int) -> dict:
    fails = und = iters = iters_ok = n_ok = 0
    for s in range(0, llrs.shape[0], batch):
        ok, hard, nit = decode_batch(llrs[s:s + batch], code)
        for j in range(ok.size):
            n_it = int(nit[j])
            good = bool(ok[j]) and np.array_equal(hard[j], cws[s + j])
            if not good:
                fails += 1
                if ok[j]:
                    und += 1
            else:
                iters_ok += n_it
                n_ok += 1
            iters += n_it
    return {"fails": fails, "undetected": und, "iters": iters,
            "iters_ok": iters_ok, "n_ok": n_ok}


def run_task_fast(rid: str, channel: str, params: dict, t0: int, n_trials: int,
                  batch: int = 64) -> dict:
    sp = construct.LADDER[rid]
    k, m = sp.k_bits, sp.m_bits
    base = int(params["seed_base"]) if channel == "record" else ch.BASE[channel]
    L = np.empty((n_trials, N))
    C = np.empty((n_trials, N), np.uint8)
    for i, t in enumerate(range(t0, t0 + n_trials)):
        L[i], C[i] = _gen_task(rid, channel, params, t, k, m, base)
    c = _count(L, C, construct.load_code(rid), batch)
    return {"rid": rid, "channel": channel, "params": params, "t0": t0, "n": n_trials,
            "fails": c["fails"], "undetected": c["undetected"], "iters": c["iters"],
            "iters_ok": c["iters_ok"], "n_ok": c["n_ok"]}


def run_chan_fast(rid: str, channel: str, params: dict, t0: int, n: int,
                  batch: int = 64) -> dict:
    """search/common.run_chan with the decode batched (same dict, same und_w)."""
    k = construct.LADDER[rid].k_bits
    base = BASE_ROBUST if channel == "robust" else ch.BASE[channel]
    L = np.empty((n, N))
    C = np.empty((n, N), np.uint8)
    for i, t in enumerate(range(t0, t0 + n)):
        g = np.random.default_rng(base + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cw = encode(info, rid)
        if channel == "bsc":
            p = params["p"]
            llr = ch.hard_llr(cw ^ (g.random(N) < p), p)
        elif channel == "awgn":
            s = params["sigma"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
        elif channel == "eras":
            p, eps = params["p"], params["eps"]
            llr = ch.hard_llr(cw ^ (g.random(N) < p), p)
            llr[g.random(N) < eps] = 0.0
        elif channel == "robust":
            s, f = params["sigma"], params["f"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
            bad = g.random(N) < f
            llr[bad] = 20.0 * (1.0 - 2.0 * cw[bad])
        else:
            raise ValueError(channel)
        L[i], C[i] = llr, cw
    code = construct.load_code(rid)
    fails = und = iters = iters_ok = n_ok = 0
    und_w = []
    for s0 in range(0, n, batch):
        ok, hard, nit = decode_batch(L[s0:s0 + batch], code)
        for j in range(ok.size):
            i = s0 + j
            n_it = int(nit[j])
            good = bool(ok[j]) and np.array_equal(hard[j], C[i])
            if not good:
                fails += 1
                if ok[j]:
                    und += 1
                    e = hard[j] ^ C[i]
                    und_w.append([t0 + i, int(e.sum()), int(e[:k].sum())])
            else:
                iters_ok += n_it
                n_ok += 1
            iters += n_it
    return {"n": n, "fails": fails, "undetected": und, "iters": iters, "iters_ok": iters_ok,
            "n_ok": n_ok, "und_w": und_w}

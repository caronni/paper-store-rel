"""(b) gate 3: tiles per second, CPU vs mlx-GPU, and the break-even batch.

Three engines, one workload:

* ``cpu1``  — ``holo.receiver.lib.ldpc.decode``, one tile at a time, one thread.
* ``cpu8``  — the same call under a thread pool.  Meaningful only on the
  free-threaded interpreter (``env/``, the free-threading build); the script records which one
  it is running on so a GIL-bound number is never mistaken for a
  parallel one.
* ``gpu``   — ``bp_mlx.decode_batch`` at a batch size sweep.

COHORTS.  Throughput is not one number, because a tile that closes on
iteration two and a tile that burns 60 min-sum plus 60 sum-product
iterations are different work.  Worse, a GPU batch runs until its LAST
member finishes, so a mixed batch pays the hard tile's price for every
member.  So the sweep runs three cohorts — ``close`` (attempts the CPU
certifies), ``fail`` (attempts it does not), ``mix`` (the corpus as it
comes) — and reports them separately.  Batches are filled by sampling
the cohort with replacement from a fixed seed, since a cohort is
smaller than the largest batch.

BREAK-EVEN.  The GPU timing is split into transfer (host array to
device and the decoded bits back) and the loop itself, and a straight
line is fitted to per-batch wall against batch size.  The intercept is
the per-batch fixed cost; the break-even is the batch at which the GPU's
per-tile wall first drops below ``cpu1``'s.

ENERGY.  Not measured: ``powermetrics`` needs root on this host and this
work does not get to ask for it.

    PYTHONPATH=<worktree> <venv>/bin/python measure/accel/bp_throughput.py \\
        --corpus <dir> --out <dir> --engines cpu1 cpu8 gpu
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import sysconfig
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from holo.receiver.lib import ldpc

SEED = 20260831
ALPHA = 0.8
RATES = ("r0550", "r0700")
BATCH_SIZES = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024)
COHORTS = ("mix", "close", "fail")
REPEATS = 5
WORKLOAD_TILES = 128
CPU_THREADS = 8


def free_threaded() -> bool:
    return sysconfig.get_config_var("Py_GIL_DISABLED") == 1


def load(corpus: Path) -> tuple[np.ndarray, list[dict]]:
    llr = np.load(corpus / "corpus_llr.npy")
    meta = json.loads((corpus / "corpus_meta.json").read_text())["attempts"]
    return llr, meta


def cohorts(llr: np.ndarray, meta: list[dict], rate_id: str,
            max_iters: int) -> dict[str, np.ndarray]:
    code = ldpc.CODES[rate_id]
    rows = [index for index, entry in enumerate(meta)
            if entry["rate_id"] == rate_id]
    closes: list[int] = []
    fails: list[int] = []
    for index in rows:
        syn_ok, _hard, _iters, _extrinsic = ldpc.decode(
            llr[index, :code.n_bits], code, max_iters, ALPHA)
        (closes if syn_ok else fails).append(index)
    return {"mix": np.asarray(rows, np.int64),
            "close": np.asarray(closes, np.int64),
            "fail": np.asarray(fails, np.int64)}


def draw(pool: np.ndarray, size: int,
         rng: np.random.Generator) -> np.ndarray:
    return pool[rng.integers(0, pool.size, size=size)]


def workload(pool: np.ndarray, batch: int,
             rng: np.random.Generator) -> np.ndarray:
    """The tile set one measurement decodes, for a given batch size.

    Every batch size up to WORKLOAD_TILES decodes the SAME tiles, split
    into as many batches as it takes; larger batch sizes extend that
    prefix.  Without this the sweep measures the luck of the draw — one
    tile that closes in two iterations makes B=1 look faster than
    B=1024 — instead of the batching.
    """
    del rng
    return pool[:max(WORKLOAD_TILES, batch)]


def cohort_pool(pool: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A fixed, seeded draw the whole sweep indexes into."""
    return draw(pool, max(WORKLOAD_TILES, max(BATCH_SIZES)), rng)


def time_cpu(llr: np.ndarray, code: ldpc.Code, rows: np.ndarray,
             max_iters: int, workers: int) -> dict:
    block = llr[rows, :code.n_bits]

    def one(index: int) -> bool:
        syn_ok, _hard, _iters, _extra = ldpc.decode(
            block[index], code, max_iters, ALPHA)
        return bool(syn_ok)

    def run() -> None:
        if workers == 1:
            for index in range(block.shape[0]):
                one(index)
            return
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, range(block.shape[0])))

    run()
    samples = []
    cpu_samples = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        cpu_started = time.process_time()
        run()
        samples.append(time.perf_counter() - started)
        cpu_samples.append(time.process_time() - cpu_started)
    samples.sort()
    cpu_samples.sort()
    best = samples[0]
    return {"tiles": int(block.shape[0]), "best_s": best,
            "median_s": samples[len(samples) // 2],
            "best_cpu_s": cpu_samples[0],
            "tiles_per_s": block.shape[0] / best,
            "tiles_per_cpu_s": block.shape[0] / cpu_samples[0]}


def time_gpu(llr: np.ndarray, code: ldpc.Code, rows: np.ndarray,
             max_iters: int, sync_every: int, batch: int) -> dict:
    import mlx.core as mx

    from measure.accel import bp_mlx

    batched = bp_mlx.prepare(code)
    prepared = bp_mlx.prepare_llr(llr[rows, :code.n_bits]).astype(np.float32)
    starts = list(range(0, prepared.shape[0], batch))

    def transfer_only() -> None:
        for start in starts:
            device = mx.array(prepared[start:start + batch])
            mx.eval(device)
            np.asarray(device)

    def one(block: np.ndarray) -> None:
        device = mx.array(block)
        hard, ok, _iters = bp_mlx.bp_batch(
            device, batched, max_iters, ALPHA, False, sync_every)
        hard_np, ok_np = np.asarray(hard), np.asarray(ok)
        failed = np.flatnonzero(~ok_np)
        if failed.size:
            retry = mx.array(block[failed])
            hard2, ok2, _iters2 = bp_mlx.bp_batch(
                retry, batched, max_iters, ALPHA, True, sync_every)
            hard_np[failed] = np.asarray(hard2)
            ok_np[failed] = np.asarray(ok2)

    def full() -> None:
        for start in starts:
            one(prepared[start:start + batch])

    full()
    transfer_only()
    samples = []
    transfers = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        full()
        samples.append(time.perf_counter() - started)
        started = time.perf_counter()
        transfer_only()
        transfers.append(time.perf_counter() - started)
    samples.sort()
    transfers.sort()
    best = samples[0]
    tiles = int(prepared.shape[0])
    return {"tiles": tiles, "batch": int(batch), "batches": len(starts),
            "best_s": best, "median_s": samples[len(samples) // 2],
            "transfer_best_s": transfers[0],
            "per_batch_best_ms": best / len(starts) * 1e3,
            "tiles_per_s": tiles / best}


def fit_line(sizes: list[int], seconds: list[float]) -> dict:
    x = np.asarray(sizes, np.float64)
    y = np.asarray(seconds, np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    return {"per_tile_s": float(slope), "per_batch_fixed_s": float(intercept)}


def run(llr: np.ndarray, meta: list[dict], engines: list[str],
        max_iters: int, sync_every: int) -> dict:
    rng = np.random.default_rng(SEED)
    out: dict = {}
    for rate_id in RATES:
        code = ldpc.CODES[rate_id]
        pools = cohorts(llr, meta, rate_id, max_iters)
        rate_out: dict = {"cohort_sizes": {name: int(pool.size)
                                           for name, pool in pools.items()}}
        for cohort in COHORTS:
            pool = pools[cohort]
            if pool.size == 0:
                continue
            drawn = cohort_pool(pool, rng)
            entry: dict = {"workload_tiles": WORKLOAD_TILES}
            if "cpu1" in engines:
                entry["cpu1"] = time_cpu(
                    llr, code, drawn[:WORKLOAD_TILES], max_iters, 1)
            if "cpu8" in engines:
                entry["cpu8"] = time_cpu(
                    llr, code, drawn[:WORKLOAD_TILES], max_iters,
                    CPU_THREADS)
            if "gpu" in engines:
                sizes = []
                seconds = []
                entry["gpu"] = {}
                for size in BATCH_SIZES:
                    result = time_gpu(llr, code, workload(drawn, size, rng),
                                      max_iters, sync_every, size)
                    entry["gpu"][str(size)] = result
                    sizes.append(size)
                    seconds.append(result["per_batch_best_ms"] / 1e3)
                entry["gpu_fit"] = fit_line(sizes, seconds)
            rate_out[cohort] = entry
        out[rate_id] = rate_out
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--engines", nargs="+",
                        default=["cpu1", "cpu8", "gpu"])
    parser.add_argument("--max-iters", type=int, default=60)
    parser.add_argument("--sync-every", type=int, default=1)
    parser.add_argument("--tag", default="run")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    llr, meta = load(args.corpus)
    report = {
        "interpreter": sys.version,
        "free_threaded": free_threaded(),
        "platform": platform.platform(),
        "loadavg_before": os.getloadavg(),
        "engines": args.engines,
        "max_iters": args.max_iters,
        "sync_every": args.sync_every,
        "workload_tiles": WORKLOAD_TILES,
        "cpu_threads": CPU_THREADS,
        "repeats": REPEATS,
        "energy": "not measured: powermetrics requires root on this host",
        "rates": run(llr, meta, args.engines, args.max_iters,
                     args.sync_every),
    }
    report["loadavg_after"] = os.getloadavg()
    (args.out / f"throughput-{args.tag}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    for rate_id, rate in report["rates"].items():
        print(f"== {rate_id} == cohorts {rate['cohort_sizes']}")
        for cohort in COHORTS:
            if cohort not in rate:
                continue
            entry = rate[cohort]
            for engine in ("cpu1", "cpu8"):
                if engine in entry:
                    print(f"  {cohort:>5} {engine:<5} "
                          f"{entry[engine]['tiles_per_s']:9.2f} tiles/s "
                          f"({entry[engine]['tiles_per_cpu_s']:9.2f} "
                          f"tiles/cpu-s)")
            if "gpu" in entry:
                for size, result in entry["gpu"].items():
                    print(f"  {cohort:>5} gpu B={size:<5} "
                          f"{result['tiles_per_s']:9.2f} tiles/s "
                          f"({result['tiles']:5d} tiles in "
                          f"{result['batches']:4d} batches, "
                          f"{result['per_batch_best_ms']:8.2f} ms/batch)")
                print(f"  {cohort:>5} gpu fit  per-tile "
                      f"{entry['gpu_fit']['per_tile_s'] * 1e3:.4f} ms, "
                      f"fixed {entry['gpu_fit']['per_batch_fixed_s'] * 1e3:.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

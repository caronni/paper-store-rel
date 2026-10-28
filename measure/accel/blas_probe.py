"""(a) part one: what BLAS does this venv's numpy/scipy actually link?

Three layers of evidence, weakest to strongest:

1. Build metadata — ``numpy.__config__`` / ``scipy.show_config()`` say what
   the wheel was BUILT against.
2. Link-time truth — ``otool -L`` on the extension modules that do the
   linear algebra says what the loaded binary actually resolves against.
3. Runtime behaviour — a GEMM sweep.  Accelerate on Apple silicon routes
   large GEMM to the AMX matrix coprocessor; a single-threaded FP64 GEMM
   rate far above the NEON-only ceiling for one core is the observable
   signature that it is doing so.  Below the ceiling would mean plain
   NEON kernels, whatever the build metadata claims.

The NEON ceiling is arithmetic, not a measurement: an M1 Firestorm core
issues 4 x 128-bit NEON FMAs per cycle = 16 FP64 FLOP/cycle (32 FP32),
so at the published 3.228 GHz P-core clock one core tops out near
51.6 GFLOP/s FP64 and 103.3 GFLOP/s FP32.  Treat it as the reference
line it is: published clock, not a measured one.

    <python> measure/accel/blas_probe.py --out <dir>

runs the sweep twice in child processes, once with
``VECLIB_MAXIMUM_THREADS=1`` and once with Accelerate's own threading
left alone, because the env var only bites before numpy is imported.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# Published Firestorm P-core figures; see the module docstring.
P_CORE_GHZ = 3.228
NEON_FP64_FLOP_PER_CYCLE = 16.0
NEON_FP32_FLOP_PER_CYCLE = 32.0
NEON_CEILING_GFLOPS = {
    "float64": P_CORE_GHZ * NEON_FP64_FLOP_PER_CYCLE,
    "float32": P_CORE_GHZ * NEON_FP32_FLOP_PER_CYCLE,
}

GEMM_SIZES = (64, 128, 256, 512, 1024, 2048)
GEMM_REPEATS = 7
THREAD_MODES = ("veclib1", "default")

LINKAGE_TARGETS = (
    "numpy/_core/_multiarray_umath",
    "numpy/linalg/_umath_linalg",
    "scipy/linalg/cython_blas",
    "scipy/linalg/cython_lapack",
    "scipy/linalg/_flapack",
    "scipy/linalg/_fblas",
)


def _shared_objects(prefix: str) -> list[Path]:
    site = Path(__import__("numpy").__file__).resolve().parent.parent
    stem = site / prefix
    return sorted(stem.parent.glob(stem.name + "*.so"))


def linkage() -> dict:
    out: dict[str, list[str]] = {}
    for target in LINKAGE_TARGETS:
        for path in _shared_objects(target):
            try:
                text = subprocess.run(
                    ["otool", "-L", str(path)], check=True,
                    capture_output=True, text=True).stdout
            except (OSError, subprocess.CalledProcessError) as problem:
                out[target] = [f"otool failed: {problem}"]
                continue
            libraries = [line.strip().split(" (")[0]
                         for line in text.splitlines()[1:]]
            out[target] = [lib for lib in libraries
                           if "libSystem" not in lib and "libc++" not in lib]
    return out


def build_config() -> dict:
    import numpy
    import scipy

    numpy_config = numpy.show_config(mode="dicts")
    scipy_config = scipy.show_config(mode="dicts")
    return {
        "numpy_version": numpy.__version__,
        "scipy_version": scipy.__version__,
        "numpy_blas": numpy_config["Build Dependencies"]["blas"],
        "numpy_lapack": numpy_config["Build Dependencies"]["lapack"],
        "scipy_blas": scipy_config["Build Dependencies"]["blas"],
        "scipy_lapack": scipy_config["Build Dependencies"]["lapack"],
    }


def gemm_sweep(dtype_name: str) -> list[dict]:
    import numpy as np

    rng = np.random.default_rng(20260831)
    dtype = np.dtype(dtype_name)
    rows: list[dict] = []
    for n in GEMM_SIZES:
        a = rng.standard_normal((n, n)).astype(dtype)
        b = rng.standard_normal((n, n)).astype(dtype)
        a @ b
        samples = []
        for _ in range(GEMM_REPEATS):
            started = time.perf_counter()
            a @ b
            samples.append(time.perf_counter() - started)
        samples.sort()
        best = samples[0]
        median = samples[len(samples) // 2]
        flop = 2.0 * n ** 3
        rows.append({
            "n": n,
            "dtype": dtype_name,
            "best_s": best,
            "median_s": median,
            "best_gflops": flop / best / 1e9,
            "median_gflops": flop / median / 1e9,
            "neon_ceiling_gflops": NEON_CEILING_GFLOPS[dtype_name],
            "over_one_core_neon": (flop / best / 1e9)
            / NEON_CEILING_GFLOPS[dtype_name],
        })
    return rows


def child_report() -> dict:
    import numpy as np

    from scipy.linalg import cholesky as scipy_cholesky

    rng = np.random.default_rng(20260831)
    matrix = rng.standard_normal((8, 8))
    spd = matrix @ matrix.T + 8.0 * np.eye(8)
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "veclib_maximum_threads": os.environ.get(
            "VECLIB_MAXIMUM_THREADS", "<unset>"),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS", "<unset>"),
        "build_config": build_config(),
        "gemm": {name: gemm_sweep(name)
                 for name in ("float64", "float32")},
        "scipy_cholesky_agrees": bool(np.allclose(
            scipy_cholesky(spd, lower=True), np.linalg.cholesky(spd))),
    }


def run_child(mode: str) -> dict:
    env = dict(os.environ)
    if mode == "veclib1":
        env["VECLIB_MAXIMUM_THREADS"] = "1"
        env["OMP_NUM_THREADS"] = "1"
    else:
        env.pop("VECLIB_MAXIMUM_THREADS", None)
        env.pop("OMP_NUM_THREADS", None)
    finished = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child"],
        check=True, capture_output=True, text=True, env=env)
    return json.loads(finished.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true",
                        help="internal: emit one report as JSON")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(child_report()))
        return 0
    report = {
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "loadavg": os.getloadavg(),
            "cpu_count": os.cpu_count(),
        },
        "linkage": linkage(),
        "modes": {mode: run_child(mode) for mode in THREAD_MODES},
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "blas.json").write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

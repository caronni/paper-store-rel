"""Kernel-level GIL-release measurement for the holo2 receiver's hot leaves.

Measure-only, driver-side: imports the pinned worktree read-only and times
each kernel in 1 thread vs W threads on the SAME total work. Under a GIL,
a kernel that releases it for a fraction f of its time scales as

    S(W) = W / ((1 - f) * W + f)   =>   f = W * (1 - 1/S) / (W - 1)

so the measured speedup inverts directly to the GIL-free fraction. A BLAS
matmul is the positive control (f ~ 1); a pure-python loop is the negative
control (f ~ 0).

usage: gil_kernels.py TREE [WORKERS]
"""
import sys
import threading
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))
W = int(sys.argv[2]) if len(sys.argv) > 2 else 4

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

from holo2.format import bch  # noqa: E402
from holo2.format.ldpc import decode as ldpc_decode  # noqa: E402


def scale(label, fn, reps):
    """Run reps*W units serially, then reps units on each of W threads."""
    fn()                                        # warm caches / lazy tables
    t0 = time.perf_counter()
    for _ in range(reps * W):
        fn()
    serial = time.perf_counter() - t0

    def loop():
        for _ in range(reps):
            fn()

    threads = [threading.Thread(target=loop) for _ in range(W)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    par = time.perf_counter() - t0
    s = serial / par
    f = W * (1 - 1 / s) / (W - 1)
    print(f"{label:46} serial {serial:6.2f}s  {W}-thread {par:6.2f}s  "
          f"speedup {s:4.2f}x  GIL-free f~{max(0.0, min(1.0, f)):.2f}",
          flush=True)


rng = np.random.default_rng(7)

# ---- controls -----------------------------------------------------------
A = rng.standard_normal((512, 512))
scale("CONTROL blas np.dot 512x512 (expect f~1)", lambda: A @ A, 40)


def _pyloop():
    t = 0
    for i in range(200_000):
        t += i
    return t


scale("CONTROL pure-python loop (expect f~0)", _pyloop, 20)

# ---- BCH word sweep (placement's cold word route) -----------------------
for H in (64, 256, 1024):
    words = (rng.random((H, 100)) < 0.5).astype(np.uint8)
    scale(f"bch.decode_many  H={H} random words",
          lambda w=words: bch.decode_many(w), max(2, 512 // H))

sigma = [1, 5, 9, 17, 33, 65, 3, 7, 11, 19, 35, 67, 13, 21]
scale("bch._chien_roots (one locator)",
      lambda: bch._chien_roots(sigma), 2000)

synd = [int(v) for v in rng.integers(1, 128, size=26)]
scale("bch._berlekamp_massey (one word)",
      lambda: bch._berlekamp_massey(synd), 4000)

# ---- scipy map_coordinates (pose refine / phase fit) --------------------
plane = rng.random((4000, 3000)).astype(np.float32)
for N in (256, 1024, 4096, 16384):
    pts = np.ascontiguousarray(
        rng.random((2, N)) * np.array([[3500.0], [2500.0]]))
    scale(f"ndimage.map_coordinates order=1  N={N} pts",
          lambda p=pts: ndimage.map_coordinates(plane, p, order=1, cval=0.0),
          max(2, 8192 // N))

# ---- pose_audit.evaluate's own numpy lines (504/510/513) ----------------
for N in (256, 1024, 4096):
    pts = rng.random((N, 2))
    jac = rng.standard_normal((2, 2))
    base = rng.standard_normal(2)
    means = rng.random(N)
    train = rng.random(N) < 0.5
    sign = np.where(rng.random(N) < 0.5, 1.0, -1.0)

    def _eval_lines(p=pts, j=jac, b=base, m=means, tr=train, sg=sign):
        sp = p.astype(np.float64) @ j.T + b
        margin = float(np.mean((0.5 - m[tr]) * -sg[tr]))
        mis = float(np.mean((m[~tr] < 0.5) != (sg[~tr] > 0)))
        return sp, margin, mis

    scale(f"pose_audit.evaluate numpy lines  N={N}", _eval_lines,
          max(20, 8192 // N))

# ---- LDPC BP (the payload leaf) -----------------------------------------
for rate in ("r0700",):
    try:
        llr = rng.standard_normal(
            ldpc_decode._code(rate).n_bits if hasattr(ldpc_decode, "_code")
            else 4096)
    except Exception:
        llr = rng.standard_normal(4096)
    try:
        ldpc_decode.decode_soft(llr, rate, max_iters=60, alpha=0.8)
        scale(f"ldpc.decode_soft {rate} (random llr)",
              lambda l=llr, r=rate: ldpc_decode.decode_soft(
                  l, r, max_iters=60, alpha=0.8), 4)
    except Exception as exc:            # shape/rate id mismatch: report it
        print(f"ldpc.decode_soft {rate}: skipped ({type(exc).__name__}: "
              f"{exc})", flush=True)

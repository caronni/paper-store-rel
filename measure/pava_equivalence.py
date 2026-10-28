from __future__ import annotations

import sys
import time
from collections import Counter

import numpy as np

from holo.receive import detect as oracle

from holo3.lib import pava

RNG = np.random.default_rng(20260829)

FAILURES: list[str] = []
COUNTS: Counter[str] = Counter()
CASES: Counter[str] = Counter()


def dispatch_labels(scores: np.ndarray, labels: np.ndarray) -> tuple[str, str]:
    raw = np.asarray(scores).ravel()
    sort_path = "argsort"
    if raw.dtype == np.float32 and raw.size < pava.PAVA_INDEX_LIMIT:
        bits = raw.ravel().view(np.uint32)
        negative_zero = bool((bits == np.uint32(pava.F32_SIGN_BIT)).any())
        not_finite = bool(((bits & np.uint32(pava.F32_MAGNITUDE_MASK))
                           > np.uint32(pava.F32_INFINITY_BITS)).any())
        if not negative_zero and not not_finite:
            sort_path = "radix"
    s = np.asarray(scores, np.float64).ravel()
    y = np.asarray(labels, np.float64).ravel()
    if s.size == 0:
        return sort_path, "empty"
    order = np.argsort(s, kind="stable")
    ys = y[order]
    n_runs = int(np.flatnonzero(ys[1:] != ys[:-1]).size) + 1
    pool_path = ("flat" if n_runs * pava.PAVA_RUN_RATIO_DIVISOR > ys.size
                 else "runs")
    return sort_path, pool_path


def compare(tag: str, scores: np.ndarray, labels: np.ndarray) -> None:
    want_s, want_p = oracle._pava_nodes(scores, labels)
    got_s, got_p = pava._pava_nodes(scores, labels)
    sort_path, pool_path = dispatch_labels(scores, labels)
    COUNTS[f"sort:{sort_path}"] += 1
    COUNTS[f"pool:{pool_path}"] += 1
    CASES[tag] += 1
    same = (got_s.shape == want_s.shape and got_p.shape == want_p.shape
            and got_s.dtype == want_s.dtype and got_p.dtype == want_p.dtype
            and got_s.tobytes() == want_s.tobytes()
            and got_p.tobytes() == want_p.tobytes())
    if not same:
        COUNTS["MISMATCH"] += 1
        if len(FAILURES) < 12:
            FAILURES.append(
                f"{tag} n={np.asarray(scores).size} "
                f"sort={sort_path} pool={pool_path}\n"
                f"  scores={np.asarray(scores).ravel()[:24]!r}\n"
                f"  labels={np.asarray(labels).ravel()[:24]!r}\n"
                f"  want_s={want_s[:8]!r} got_s={got_s[:8]!r}\n"
                f"  want_p={want_p[:8]!r} got_p={got_p[:8]!r}")


def binary_labels(n: int, p: float) -> np.ndarray:
    return (RNG.random(n) < p).astype(np.int8)


def population_tiny(trials: int) -> None:
    for _ in range(trials):
        n = int(RNG.integers(0, 9))
        scores = RNG.normal(size=n).astype(np.float32)
        compare("tiny", scores, binary_labels(n, float(RNG.random())))


def population_small(trials: int) -> None:
    for index in range(trials):
        n = int(RNG.integers(1, 65))
        p = (0.0 if index % 17 == 0 else
             1.0 if index % 17 == 1 else float(RNG.random()))
        scores = RNG.normal(size=n).astype(np.float32)
        compare("small", scores, binary_labels(n, p))


def population_ties(trials: int) -> None:
    for index in range(trials):
        n = int(RNG.integers(2, 129))
        levels = int(RNG.integers(1, 6))
        scores = RNG.integers(0, levels, size=n).astype(np.float32)
        if index % 5 == 0:
            scores = np.zeros(n, np.float32)
        compare("ties", scores, binary_labels(n, float(RNG.random())))


def population_bimodal(trials: int) -> None:
    for _ in range(trials):
        n = int(RNG.integers(50, 401))
        bias = float(RNG.uniform(0.05, 3.5))
        labels = binary_labels(n, 0.5)
        truth = np.where(labels > 0, 1.0, -1.0)
        scores = (RNG.normal(0.0, 1.0, size=n)
                  + bias * truth).astype(np.float32)
        compare("bimodal", scores, labels)


def population_adversarial(trials: int) -> None:
    pool = np.array([0.0, -0.0, 1.0, -1.0, np.inf, -np.inf, np.nan,
                     np.float32(1e-45), np.float32(-1e-45), 3.5, -3.5,
                     np.float32(1.1754944e-38), 2.0, -2.0],
                    dtype=np.float32)
    for _ in range(trials):
        n = int(RNG.integers(1, 41))
        scores = RNG.choice(pool, size=n).astype(np.float32)
        compare("adversarial", scores, binary_labels(n, float(RNG.random())))


def population_signed_zero(trials: int) -> None:
    for _ in range(trials):
        n = int(RNG.integers(2, 41))
        scores = np.where(RNG.random(n) < 0.5,
                          np.float32(0.0), np.float32(-0.0)).astype(np.float32)
        mix = RNG.random(n) < 0.3
        scores[mix] = RNG.normal(size=int(mix.sum())).astype(np.float32)
        compare("signed_zero", scores, binary_labels(n, float(RNG.random())))


def population_nonbinary(trials: int) -> None:
    for index in range(trials):
        n = int(RNG.integers(1, 65))
        scores = RNG.normal(size=n).astype(np.float32)
        if index % 3 == 0:
            labels = RNG.integers(0, 4, size=n).astype(np.float64)
        elif index % 3 == 1:
            labels = RNG.random(n)
        else:
            labels = (RNG.integers(-2, 3, size=n)).astype(np.float64)
        compare("nonbinary", scores, labels)


def population_float64_scores(trials: int) -> None:
    for _ in range(trials):
        n = int(RNG.integers(1, 65))
        scores = RNG.normal(size=n)
        compare("float64_scores", scores, binary_labels(n, float(RNG.random())))


def population_monotone(trials: int) -> None:
    for index in range(trials):
        n = int(RNG.integers(2, 129))
        scores = np.arange(n, dtype=np.float32)
        half = n // 2
        if index % 4 == 0:
            labels = np.concatenate((np.zeros(half, np.int8),
                                     np.ones(n - half, np.int8)))
        elif index % 4 == 1:
            labels = np.concatenate((np.ones(half, np.int8),
                                     np.zeros(n - half, np.int8)))
        elif index % 4 == 2:
            labels = (np.arange(n) % 2).astype(np.int8)
        else:
            labels = binary_labels(n, float(RNG.random()))
        if index % 7 == 0:
            scores = scores[::-1].copy()
        compare("monotone", scores, labels)


def population_shaped_2d(trials: int) -> None:
    for _ in range(trials):
        rows = int(RNG.integers(1, 9))
        cols = int(RNG.integers(1, 9))
        scores = RNG.normal(size=(rows, cols)).astype(np.float32)
        labels = binary_labels(rows * cols, 0.5).reshape(rows, cols)
        compare("shaped_2d", scores, labels)


def population_large(trials: int) -> None:
    for _ in range(trials):
        n = int(RNG.integers(2000, 40001))
        bias = float(RNG.uniform(0.1, 3.5))
        labels = binary_labels(n, 0.5)
        truth = np.where(labels > 0, 1.0, -1.0)
        scores = (RNG.normal(0.0, 1.0, size=n)
                  + bias * truth).astype(np.float32)
        compare("large_window", scores, labels)


def population_large_quantized(trials: int) -> None:
    for _ in range(trials):
        n = int(RNG.integers(2000, 40001))
        bias = float(RNG.uniform(0.1, 3.0))
        labels = binary_labels(n, 0.5)
        truth = np.where(labels > 0, 1.0, -1.0)
        raw = RNG.normal(0.0, 1.0, size=n) + bias * truth
        scores = (np.round(raw * 12.0) / 12.0).astype(np.float32)
        scores[scores == 0.0] = np.float32(0.0)
        compare("large_quantized", scores, labels)


PLAN = (
    ("tiny", population_tiny, 220000),
    ("small", population_small, 260000),
    ("ties", population_ties, 200000),
    ("bimodal", population_bimodal, 120000),
    ("adversarial", population_adversarial, 90000),
    ("signed_zero", population_signed_zero, 60000),
    ("nonbinary", population_nonbinary, 90000),
    ("float64_scores", population_float64_scores, 60000),
    ("monotone", population_monotone, 90000),
    ("shaped_2d", population_shaped_2d, 60000),
    ("large_window", population_large, 220),
    ("large_quantized", population_large_quantized, 180),
)

if __name__ == "__main__":
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    started = time.perf_counter()
    for name, fn, trials in PLAN:
        t0 = time.perf_counter()
        fn(max(1, int(trials * scale)))
        print(f"  {name:<16} {CASES[name]:>8} cases  "
              f"{time.perf_counter() - t0:>7.1f}s")
    total = sum(CASES.values())
    print(f"\ntotal cases {total}  elapsed {time.perf_counter() - started:.1f}s")
    print("dispatch coverage:")
    for key in sorted(COUNTS):
        if key != "MISMATCH":
            print(f"  {key:<16} {COUNTS[key]}")
    if FAILURES:
        print(f"\nMISMATCHES {COUNTS['MISMATCH']}")
        for item in FAILURES:
            print(item)
        raise SystemExit(1)
    print(f"\nEQUIVALENCE GREEN: {total} populations, 0 mismatches "
          f"(bitwise, vs holo.receive.detect._pava_nodes)")

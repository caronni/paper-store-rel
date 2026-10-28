from __future__ import annotations

import cProfile
import pstats
import sys
import time

import numpy as np

from holo3.plugins import color_region_ctx as ctx
from ctx_fixture import make_region_fixture


def run_fit(n_labels: int, n_states: int, repeats: int = 1,
            seed: int = 20260829) -> tuple[float, ctx.ContextVerdict]:
    fixture = make_region_fixture(n_labels, n_states, seed=seed)
    verdict = ctx.fit_region_context(
        fixture.model, fixture.detector, None, fixture.known_features,
        fixture.known_bins, fixture.states, fixture.kinds, fixture.search,
        fixture.config)
    start = time.perf_counter()
    for _ in range(repeats):
        verdict = ctx.fit_region_context(
            fixture.model, fixture.detector, None, fixture.known_features,
            fixture.known_bins, fixture.states, fixture.kinds,
            fixture.search, fixture.config)
    elapsed = (time.perf_counter() - start) / max(repeats, 1)
    return elapsed, verdict


def profile(n_labels: int, n_states: int, seed: int = 20260829) -> None:
    fixture = make_region_fixture(n_labels, n_states, seed=seed)
    profiler = cProfile.Profile()
    profiler.enable()
    ctx.fit_region_context(
        fixture.model, fixture.detector, None, fixture.known_features,
        fixture.known_bins, fixture.states, fixture.kinds, fixture.search,
        fixture.config)
    profiler.disable()
    stats = pstats.Stats(profiler, stream=sys.stdout)
    stats.sort_stats("tottime").print_stats(22)


def solve_counts(n_labels: int, n_states: int,
                 seed: int = 20260829) -> tuple[int, int, float]:
    fixture = make_region_fixture(n_labels, n_states, seed=seed)
    calls = [0]
    sizes = [0]
    original = ctx._solve_offset

    def counted(llr: np.ndarray, labels: np.ndarray,
                weights: np.ndarray) -> float:
        calls[0] += 1
        sizes[0] += int(np.asarray(llr).size)
        return original(llr, labels, weights)

    ctx._solve_offset = counted
    start = time.perf_counter()
    ctx.fit_region_context(
        fixture.model, fixture.detector, None, fixture.known_features,
        fixture.known_bins, fixture.states, fixture.kinds, fixture.search,
        fixture.config)
    elapsed = time.perf_counter() - start
    ctx._solve_offset = original
    return calls[0], sizes[0], elapsed


def ab(n_labels: int, n_states: int, rounds: int = 3,
       seed: int = 20260829) -> tuple[float, float]:
    from holo3.lib import pava
    from .ctx_equivalence import _reference_solve_offset

    fixture = make_region_fixture(n_labels, n_states, seed=seed)
    fast = pava._solve_offset

    def once(solver) -> float:
        pava._solve_offset = solver
        ctx._solve_offset = solver
        start = time.perf_counter()
        ctx.fit_region_context(
            fixture.model, fixture.detector, None, fixture.known_features,
            fixture.known_bins, fixture.states, fixture.kinds,
            fixture.search, fixture.config)
        return time.perf_counter() - start

    once(fast)
    best_old = 1e9
    best_new = 1e9
    for _ in range(rounds):
        best_old = min(best_old, once(_reference_solve_offset))
        best_new = min(best_new, once(fast))
    pava._solve_offset = fast
    ctx._solve_offset = fast
    return best_old, best_new


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "sweep"
    if mode == "ab":
        print(f"{'states':>6} {'labels':>7} {'old(s)':>9} {'new(s)':>9} "
              f"{'speedup':>8}")
        for n_states in (7, 8):
            for n_labels in (5_000, 20_000, 40_000, 90_000):
                old, new = ab(n_labels, n_states)
                print(f"{n_states:6d} {n_labels:7d} {old:9.3f} {new:9.3f} "
                      f"{old / new:7.2f}x")
        return 0
    if mode == "profile":
        n_labels = int(argv[2]) if len(argv) > 2 else 20_000
        n_states = int(argv[3]) if len(argv) > 3 else 8
        profile(n_labels, n_states)
        return 0
    if mode == "counts":
        for n_states in (7, 8):
            for n_labels in (10_000, 20_000, 40_000):
                calls, sizes, elapsed = solve_counts(n_labels, n_states)
                print(f"states={n_states} labels={n_labels} "
                      f"solve_calls={calls} solve_elements={sizes} "
                      f"wall={elapsed:.3f}s")
        return 0
    for n_states in (7, 8):
        for n_labels in (5_000, 10_000, 20_000, 40_000, 80_000):
            elapsed, verdict = run_fit(n_labels, n_states)
            print(f"states={n_states} labels={n_labels} "
                  f"wall={elapsed:.3f}s adopted={verdict.adopted} "
                  f"curves={verdict.curves_adopted}/{verdict.curves_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

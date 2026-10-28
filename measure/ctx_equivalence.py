from __future__ import annotations

import sys
import time

import numpy as np

from holo3.lib import pava
from holo3.plugins import color_region_ctx as ctx
from ctx_fixture import make_region_fixture

CHECKS: list[int] = [0]
FAILS: list[str] = []


def _reference_sigmoid(x: np.ndarray) -> np.ndarray:
    probability = np.empty_like(x)
    positive = x >= 0
    probability[positive] = 1.0 / (1.0 + np.exp(-x[positive]))
    ex = np.exp(x[~positive])
    probability[~positive] = ex / (1.0 + ex)
    return probability


def _reference_solve_offset(llr: np.ndarray, labels: np.ndarray,
                            weights: np.ndarray) -> float:
    target = float(np.sum(weights * labels))

    def derivative(offset: float) -> float:
        return float(
            np.sum(weights * _reference_sigmoid(llr + offset)) - target)

    lo, hi = -pava.CTX_OFFSET_LIMIT, pava.CTX_OFFSET_LIMIT
    if derivative(lo) >= 0.0:
        return lo
    if derivative(hi) <= 0.0:
        return hi
    if derivative(0.0) == 0.0:
        return 0.0
    while hi - lo > pava.CTX_ROOT_TOL:
        mid = (lo + hi) * 0.5
        if derivative(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def _bits(value: np.ndarray) -> np.ndarray:
    return np.asarray(value, np.float64).view(np.uint64)


def _same_float(a: float, b: float) -> bool:
    return (np.float64(a).view(np.uint64)
            == np.float64(b).view(np.uint64))


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS[0] += 1
    if not ok:
        FAILS.append(f"{name}: {detail}")
        if len(FAILS) < 20:
            print(f"FAIL {name} {detail}")


def eq_array(name: str, a: np.ndarray, b: np.ndarray) -> None:
    left = np.asarray(a, np.float64)
    right = np.asarray(b, np.float64)
    same = (left.shape == right.shape
            and np.array_equal(_bits(left), _bits(right)))
    detail = ""
    if left.shape == right.shape and left.size and not same:
        detail = f"maxdiff {np.max(np.abs(left - right))}"
    check(name, same, detail)


def _population(rng: np.random.Generator, size: int,
                kind: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if kind == 0:
        llr = rng.normal(0.0, 2.0, size)
    elif kind == 1:
        llr = rng.normal(0.0, 12.0, size)
    elif kind == 2:
        llr = rng.uniform(-0.5, 0.5, size) * 1e-9
    elif kind == 3:
        llr = rng.normal(30.0, 3.0, size)
    elif kind == 4:
        llr = rng.normal(-30.0, 3.0, size)
    elif kind == 5:
        llr = np.zeros(size)
    else:
        llr = rng.normal(0.0, 2.0, size)
        llr[rng.random(size) < 0.1] = 0.0
    if kind == 3:
        labels = np.ones(size, bool)
    elif kind == 4:
        labels = np.zeros(size, bool)
    elif kind == 5:
        labels = np.zeros(size, bool)
        labels[:size // 2] = True
    else:
        labels = rng.random(size) < rng.uniform(0.05, 0.95)
    if kind == 5:
        weights = np.ones(size)
    else:
        weights = rng.uniform(0.0, 3.0, size)
    llr = np.concatenate((llr, np.array([0.0, 0.0])))
    labels = np.concatenate((labels, np.array([False, True])))
    weights = np.concatenate(
        (weights, np.full(2, pava.CTX_BIN_PRIOR, np.float64)))
    return llr, labels, weights


def stage_sigmoid(rng: np.random.Generator) -> None:
    grids = [
        np.linspace(-40.0, 40.0, 1_500_001),
        np.linspace(-4.0, 4.0, 1_000_001),
        np.linspace(-1e-9, 1e-9, 200_001),
        np.array([0.0, -0.0, np.inf, -np.inf, np.nan, 1e-320, -1e-320,
                  709.0, -709.0, 745.0, -745.0, 1e308, -1e308]),
    ]
    for index, grid in enumerate(grids):
        mine = pava.sigmoid(grid.copy())
        oracle = _reference_sigmoid(grid.copy())
        finite = np.isfinite(oracle)
        eq_array(f"sigmoid_grid[{index}]", mine[finite], oracle[finite])
        check(f"sigmoid_nan[{index}]",
              bool(np.array_equal(np.isnan(mine), np.isnan(oracle))))
    for trial in range(200):
        size = int(rng.integers(1, 3000))
        values = rng.normal(0.0, rng.uniform(0.1, 30.0), size)
        eq_array(f"sigmoid_rand[{trial}]", pava.sigmoid(values.copy()),
                 _reference_sigmoid(values.copy()))


def stage_solve(rng: np.random.Generator, populations: int) -> int:
    bad = 0
    for index in range(populations):
        kind = index % 7
        if index % 500 == 0:
            size = int(rng.integers(600, 4000))
        else:
            size = int(rng.integers(0, 60))
        llr, labels, weights = _population(rng, size, kind)
        mine = pava._solve_offset(llr, labels, weights)
        oracle = _reference_solve_offset(llr, labels, weights)
        if not _same_float(mine, oracle):
            bad += 1
            if bad < 10:
                print(f"FAIL solve[{index}] size={size} kind={kind} "
                      f"{mine!r} != {oracle!r}")
    check(f"solve_offset_populations({populations})", bad == 0,
          f"{bad} mismatches")
    return populations


def stage_ordered(rng: np.random.Generator, trials: int) -> int:
    solves = 0
    for trial in range(trials):
        size = int(rng.integers(20, 4000))
        logits = rng.normal(0.0, rng.uniform(0.5, 6.0), size)
        labels = rng.random(size) < rng.uniform(0.1, 0.9)
        weights = rng.uniform(0.0, 3.0, size)
        spread = rng.integers(1, 10)
        bins = rng.integers(0, spread, size).astype(np.int64)
        for direction in (True, False):
            saved = pava._solve_offset
            mine = ctx.ordered_offsets(
                logits, labels, weights, bins, direction)
            pava._solve_offset = _reference_solve_offset
            ctx._solve_offset = _reference_solve_offset
            oracle = ctx.ordered_offsets(
                logits, labels, weights, bins, direction)
            pava._solve_offset = saved
            ctx._solve_offset = saved
            eq_array(f"ordered_offsets[{trial},{direction}]", mine, oracle)
            eq_array(f"anchor_curve[{trial},{direction}]",
                     ctx.anchor_curve(mine, bins, weights),
                     ctx.anchor_curve(oracle, bins, weights))
            solves += 2 * pava.N_CONTEXT_BINS
    return solves


def stage_context_offsets(rng: np.random.Generator, trials: int) -> int:
    solves = 0
    for trial in range(trials):
        size = int(rng.integers(20, 3000))
        llr = rng.normal(0.0, rng.uniform(0.5, 6.0), size)
        counts = rng.integers(0, 9, size).astype(np.int64)
        labels = rng.random(size) < rng.uniform(0.1, 0.9)
        weights = rng.uniform(0.0, 3.0, size)
        mine = pava._ordered_context_offsets(llr, counts, labels, weights)
        saved = pava._solve_offset
        pava._solve_offset = _reference_solve_offset
        oracle = pava._ordered_context_offsets(llr, counts, labels, weights)
        pava._solve_offset = saved
        eq_array(f"ordered_context_offsets[{trial}]", mine, oracle)
        solves += pava.N_CONTEXT_BINS
    return solves


def stage_logits(rng: np.random.Generator, trials: int) -> int:
    rows_compared = 0
    for trial in range(trials):
        size = int(rng.integers(1, 8000))
        n_states = int(rng.choice([7, 8]))
        scores = rng.normal(0.0, rng.uniform(0.5, 8.0), (size, n_states))
        if trial % 5 == 0:
            scores[rng.random((size, n_states)) < 0.05] = -np.inf
        if trial % 7 == 0:
            scores = np.repeat(scores[:1], size, axis=0)
        column = int(rng.integers(0, n_states))
        rows = np.flatnonzero(rng.random(size) < 0.95)
        if rows.size == 0:
            continue
        eq_array(f"hoisted_logits[{trial}]",
                 ctx.one_versus_rest(scores, column)[rows],
                 ctx.one_versus_rest(scores[rows], column))
        rows_compared += int(rows.size)
    return rows_compared


def stage_oracle_matrix(cases: tuple[tuple[int, int], ...]) -> int:
    from holo.receive import color_context as oracle

    curves = 0
    for n_labels, n_states in cases:
        fixture = make_region_fixture(n_labels, n_states,
                                      seed=41_000 + n_labels + n_states)
        search, validation = _make_populations(fixture)
        mine_offsets, mine_records = ctx._fit_matrix_curves(
            search, validation, fixture.config,
            pinned_reference=fixture.detector is None)
        oracle_offsets, oracle_curves = oracle._fit_matrix_curves(
            oracle._Population(search.scores, search.states, search.bins,
                               search.kinds),
            oracle._Population(validation.scores, validation.states,
                               validation.bins, validation.kinds),
            oracle.ContextConfig(max_labels=fixture.config.max_labels,
                                 sweeps=fixture.config.sweeps),
            pinned_reference=fixture.detector is None)
        eq_array(f"oracle_matrix_offsets[{n_labels},{n_states}]",
                 mine_offsets, oracle_offsets)
        mine_adopted = {key for key, reason in mine_records.items()
                        if reason == ctx.REASON_ADOPTED}
        oracle_adopted = {(curve.column, curve.plane)
                          for curve in oracle_curves
                          if curve.reason == ctx.REASON_ADOPTED}
        check(f"oracle_matrix_adopted[{n_labels},{n_states}]",
              mine_adopted == oracle_adopted,
              f"{sorted(mine_adopted)} != {sorted(oracle_adopted)}")
        curves += len(oracle_curves)
    return curves


def _make_populations(fixture) -> tuple[ctx.Population, ctx.Population]:
    from ctx_fixture import make_populations

    return make_populations(fixture)


def _verdict_tuple(verdict: ctx.ContextVerdict) -> tuple:
    head = verdict.head
    return (
        verdict.adopted, verdict.reason, verdict.curves_adopted,
        verdict.curves_total,
        None if head is None else _bits(head.offsets).tobytes(),
        None if head is None else head.applied.tobytes(),
    )


def stage_region(cases: tuple[tuple[int, int], ...]) -> int:
    curves = 0
    for n_labels, n_states in cases:
        fixture = make_region_fixture(n_labels, n_states,
                                      seed=17_000 + n_labels + n_states)
        mine = ctx.fit_region_context(
            fixture.model, fixture.detector, None, fixture.known_features,
            fixture.known_bins, fixture.states, fixture.kinds,
            fixture.search, fixture.config)
        saved = pava._solve_offset
        pava._solve_offset = _reference_solve_offset
        ctx._solve_offset = _reference_solve_offset
        oracle = ctx.fit_region_context(
            fixture.model, fixture.detector, None, fixture.known_features,
            fixture.known_bins, fixture.states, fixture.kinds,
            fixture.search, fixture.config)
        pava._solve_offset = saved
        ctx._solve_offset = saved
        check(f"region[{n_labels},{n_states}]",
              _verdict_tuple(mine) == _verdict_tuple(oracle),
              f"{mine.reason}/{oracle.reason} "
              f"{mine.curves_adopted}/{oracle.curves_adopted}")
        curves += mine.curves_total
    return curves


def main(argv: list[str]) -> int:
    populations = int(argv[1]) if len(argv) > 1 else 100_000
    rng = np.random.default_rng(20260829)
    start = time.perf_counter()
    stage_sigmoid(rng)
    print(f"sigmoid stage done ({time.perf_counter() - start:.1f}s)")
    solves = stage_solve(rng, populations)
    print(f"solve stage done: {solves} populations "
          f"({time.perf_counter() - start:.1f}s)")
    solves += stage_ordered(rng, 300)
    print(f"ordered stage done ({time.perf_counter() - start:.1f}s)")
    solves += stage_context_offsets(rng, 150)
    print(f"context-offsets stage done ({time.perf_counter() - start:.1f}s)")
    cases = (
        (200, 7), (200, 8), (2_000, 7), (2_000, 8), (12_000, 7),
        (12_000, 8), (41_000, 7), (41_000, 8), (90_000, 8), (90_000, 7),
    )
    rows = stage_logits(rng, 250)
    print(f"hoisted-logits stage done: {rows} rows "
          f"({time.perf_counter() - start:.1f}s)")
    curves = stage_region(cases)
    print(f"region stage done: {curves} curve fits "
          f"({time.perf_counter() - start:.1f}s)")
    oracle_curves = stage_oracle_matrix(cases)
    print(f"src/holo oracle stage done: {oracle_curves} oracle curves "
          f"({time.perf_counter() - start:.1f}s)")
    print(f"{CHECKS[0]} checks, {len(FAILS)} failures, "
          f"~{solves} solver populations, {rows} hoisted rows")
    if FAILS:
        print("ctx_equivalence: FAILED")
        return 1
    print("ctx_equivalence: ALL GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

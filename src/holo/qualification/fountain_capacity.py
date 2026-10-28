"""Independent qualification of fountain-v2 whole-page capacity bounds."""
from __future__ import annotations

from dataclasses import dataclass

from ..core import capacity, fountain


@dataclass(frozen=True, slots=True)
class CapacityCase:
    name: str
    detail: str


def _promise_formula_case() -> CapacityCase:
    comparisons = 0
    for tiles in (37, 840, 1_872):
        for pages in (1, 20, 106, 307):
            for q in (0.3, 0.5, 0.7, 1.0):
                budget = capacity.source_budget(tiles * pages, q)
                for k_total in (0, 1, max(1, budget // 2), budget):
                    if k_total == 0:
                        expected = True
                    else:
                        blocks = fountain.n_blocks_for(k_total)
                        reserve = capacity.rank_reserve_for(blocks)
                        retained = capacity.retained_pages(pages, q)
                        expected = (
                            k_total + blocks * reserve <= budget
                            and -(-k_total // blocks) + reserve
                            <= retained * (tiles // blocks)
                        )
                    actual = capacity.page_capacity_sufficient(
                        k_total, tiles, pages, q)
                    if actual != expected:
                        raise AssertionError(
                            f"K={k_total} T={tiles} P={pages} q={q}: "
                            f"actual={actual} expected={expected}")
                    comparisons += 1
    return CapacityCase(
        "frozen-two-tier-promise",
        f"{comparisons} cases equal the Track-1 global/per-block formula")


def _known_boundaries_case() -> CapacityCase:
    checks = (
        (99_083, 1_872, 106, 0.5, False),
        (99_083, 1_872, 107, 0.5, True),
        (157_041, 1_872, 120, 0.7, False),
        (157_041, 1_872, 121, 0.7, True),
        (179_521, 840, 307, 0.7, False),
        (180_225, 840, 307, 0.7, True),
    )
    for k_total, tiles, pages, q, expected in checks:
        if capacity.page_capacity_sufficient(
                k_total, tiles, pages, q) != expected:
            raise AssertionError("frozen capacity boundary moved")
    return CapacityCase(
        "frozen-boundaries",
        "page-loss and block-count discontinuities remain unchanged")


def _global_hole_case() -> CapacityCase:
    k_total, tiles, pages, q = 99_083, 1_872, 106, 0.5
    blocks = fountain.n_blocks_for(k_total)
    reserve = capacity.rank_reserve_for(blocks)
    global_only = (
        k_total + blocks * reserve
        <= capacity.source_budget(tiles * pages, q)
    )
    if not global_only:
        raise AssertionError("global-only counterexample no longer reaches bound")
    if capacity.page_capacity_sufficient(k_total, tiles, pages, q):
        raise AssertionError("global-average block-starvation hole reopened")
    return CapacityCase(
        "global-average-hole",
        "global budget passes while exact worst-block quota correctly refuses")


def _maximality_case() -> CapacityCase:
    cases = (
        (840, 228, 0.7),
        (1_872, 60, 0.7),
        (1_872, 106, 0.5),
        (1_872, 20, 1.0),
    )
    maxima = []
    for tiles, pages, q in cases:
        maximum = capacity.max_k_for_pages(tiles, pages, q)
        if maximum <= 0 or not capacity.page_capacity_sufficient(
                maximum, tiles, pages, q):
            raise AssertionError("reported maximum is not feasible")
        if capacity.page_capacity_sufficient(
                maximum + 1, tiles, pages, q):
            raise AssertionError("reported maximum is not maximal")
        maxima.append(maximum)
    return CapacityCase(
        "max-k-maximality", f"exact maxima={maxima}")


def qualify() -> tuple[CapacityCase, ...]:
    return (
        _promise_formula_case(),
        _known_boundaries_case(),
        _global_hole_case(),
        _maximality_case(),
    )


if __name__ == "__main__":
    for case in qualify():
        print(f"PASS {case.name}: {case.detail}")

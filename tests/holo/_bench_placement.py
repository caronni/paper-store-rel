"""Measured placement benchmark (v0.22/v0.23 work): NOT a pytest module.

Run:  PYTHONPATH=src:tests/holo env/bin/python tests/holo/_bench_placement.py

Two measurements, per the profiling doctrine (dedicated harness, never
timed through pytest):

1. frontier-save — the deferred-cold synthetic case: a two-window fragment
   whose left window's word slots are killed.  Reports cold searches run,
   the sequential-ladder counterfactual (a deferred window later accepted
   by chain would have been one cold search), and wall time.
2. cold-fft — `correlate_patch` new (hoisted rfftn, winner-only second
   peak) vs the verbatim legacy three-convolution form retained in
   test_cold_search_exactness, on the same true-fragment patch, page
   count swept.
"""
from __future__ import annotations

import time

import numpy as np

import _roundtrip_fixture as roundtrip
import test_placement_frontier as frontier
from test_cold_search_exactness import _reference_correlate

from holo.receive.place import _core
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.geometry import (
    fit_window_pose,
    layout_pose_windows,
    make_address_patch,
    platen_backing,
    prepare_region,
    sample_segment,
)
from holo.receive.placement.model import PlacementConfig
from holo.receive.placement.reference import V1ReferenceField
from holo.receive.placement.search import ScoreMemo, correlate_patch
from holo.receive.survey import SurveyRegion


def _time(callable_, repeats: int = 3):
    best = None
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = callable_()
        elapsed = time.perf_counter() - start
        best = elapsed if best is None else min(best, elapsed)
    return best, result


def bench_frontier(fixture) -> None:
    print("== frontier-save (deferred cold) ==")
    for label, damage in (("clean", False), ("word-killed", True)):
        fragment = frontier._fragment(fixture, damage=damage)
        elapsed, result = _time(
            lambda: frontier._place(fixture, fragment))
        colds = sum(
            "correlation" in row.attempted_routes for row in result.attempts)
        saved = sum(
            row.route == "chain" and any(
                attempt.patch_id == row.patch_id
                and "word" in attempt.attempted_routes
                for attempt in result.attempts)
            for row in result.placements)
        accepted = sum(not row.redundant for row in result.placements)
        print(
            f"  {label:12s} accepted={accepted} colds_run={colds} "
            f"colds_saved_vs_sequential={saved} "
            f"hypotheses={result.hypotheses_evaluated:,} "
            f"wall={elapsed*1e3:.0f} ms")


def bench_cold_fft(fixture) -> None:
    print("== cold-fft: new correlate_patch vs legacy 3-convolution ==")
    spec = fixture.spec
    raster, support = frontier._fragment(fixture, damage=False)
    config = PlacementConfig()
    px_per_mm = raster.dpi / 25.4
    region = SurveyRegion(
        support, support.area_px / (px_per_mm * px_per_mm), 1.0)
    context = prepare_region(
        raster, region, 0, 3.0, config=config,
        backing=platen_backing(raster))
    window = min(
        layout_pose_windows(context, config=config),
        key=lambda row: row.origin_yx_px[1])
    segment = fit_window_pose(context, window, config=config)
    sample = sample_segment(context, segment)
    patch = make_address_patch(sample, _core(sample.mask, config.erode_cells))
    provider = V1ReferenceField(spec)
    for n_pages in (4, 16, 64):
        if n_pages > spec.max_pages:
            continue
        pages = tuple(range(n_pages))
        budgets, _ = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
            spec, pages, 0, config)
        provider.page(0)  # warm the reference memo outside the timing
        for page in pages:
            provider.page(page)
        new_time, new_result = _time(lambda: correlate_patch(
            patch, provider, pages, budgets.cold, ScoreMemo(provider),
            sample_key=0, config=config))
        old_time, old_result = _time(lambda: _reference_correlate(
            patch, provider, pages, budgets.cold, ScoreMemo(provider),
            sample_key=0, config=config))
        assert new_result.accepted == old_result.accepted
        assert new_result.best == old_result.best
        assert new_result.runner_ups == old_result.runner_ups
        print(
            f"  P={n_pages:3d}  legacy={old_time*1e3:7.1f} ms  "
            f"new={new_time*1e3:7.1f} ms  speedup={old_time/new_time:5.2f}x  "
            f"(outcomes identical)")


def main() -> None:
    fixture = roundtrip._build_fixture()
    print(f"fixture: {fixture.spec.spec_id} "
          f"cells={fixture.spec.layout.cells_yx} "
          f"max_pages={fixture.spec.max_pages}")
    bench_frontier(fixture)
    bench_cold_fft(fixture)


if __name__ == "__main__":
    main()

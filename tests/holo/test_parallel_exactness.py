"""Worker-count exactness pins for the tier-0/1 parallel execution paths.

EXPERIMENT (holo-parallel-tier1).  The determinism contract: every
parallelized kernel reproduces its sequential output bit-exactly for any
``HOLO_RECEIVE_WORKERS`` value — tasks are pure functions of frozen
inputs and every reduction happens on the caller thread in submission
order.  These pins compare workers=1 against workers=4 directly on each
kernel; ``test_cold_search_exactness`` (which compares against the
verbatim legacy implementation) additionally passes under any worker
count, and the phased bench harness compares full-decode state digests.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo.receive import _parallel
from holo.receive._survey_tensor import _whole_tensor_score
from holo.receive.placement.model import AttemptBudget, PlacementConfig
from holo.receive.placement.search import ScoreMemo, correlate_patch

import test_cold_search_exactness as cold_fixtures


@pytest.fixture
def workers_env(monkeypatch):
    def set_count(count: int) -> None:
        monkeypatch.setenv("HOLO_RECEIVE_WORKERS", str(count))

    return set_count


def test_worker_count_parsing(monkeypatch):
    monkeypatch.delenv("HOLO_RECEIVE_WORKERS", raising=False)
    assert _parallel.worker_count() == 1
    monkeypatch.setenv("HOLO_RECEIVE_WORKERS", "6")
    assert _parallel.worker_count() == 6
    monkeypatch.setenv("HOLO_RECEIVE_WORKERS", "banana")
    assert _parallel.worker_count() == 1
    monkeypatch.setenv("HOLO_RECEIVE_WORKERS", "0")
    assert _parallel.worker_count() == 1


def test_set_worker_count_overrides_environment(monkeypatch):
    monkeypatch.setenv("HOLO_RECEIVE_WORKERS", "6")
    try:
        _parallel.set_worker_count(3)
        assert _parallel.worker_count() == 3
        with pytest.raises(ValueError):
            _parallel.set_worker_count(0)
        assert _parallel.worker_count() == 3
        _parallel.set_worker_count(None)
        assert _parallel.worker_count() == 6
    finally:
        _parallel.set_worker_count(None)


def test_cli_workers_flag_validator():
    from holo.cli import _worker_count
    import argparse

    assert _worker_count("4") == 4
    with pytest.raises(argparse.ArgumentTypeError):
        _worker_count("0")
    with pytest.raises(ValueError):
        _worker_count("many")


def test_ordered_map_matches_sequential_and_error_order(workers_env):
    workers_env(4)

    def square(value: int) -> int:
        if value == 13:
            raise ValueError("thirteen")
        return value * value

    items = list(range(12))
    assert _parallel.ordered_map(square, items) == [
        value * value for value in items]
    with pytest.raises(ValueError, match="thirteen"):
        _parallel.ordered_map(square, [2, 13, 5, 13])


def test_nested_ordered_map_degrades_to_sequential(workers_env):
    workers_env(4)

    def outer(value: int) -> list[int]:
        # Inside a pool task the nested map must not deadlock the pool.
        return _parallel.ordered_map(lambda inner: inner + value, [1, 2, 3])

    assert _parallel.ordered_map(outer, [10, 20]) == [
        [11, 12, 13], [21, 22, 23]]


def _cold_case(seed: int, rot_k: int):
    rng, sites, values = cold_fixtures._make_world(seed=seed, page_count=6)
    provider = cold_fixtures._Provider(values, sites)
    patch = cold_fixtures._true_patch(
        rng, values[1], (4, 8), (16, 16), rot_k, flip_fraction=0.04)
    return patch, provider


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_cold_search_workers_bit_identical(workers_env, monkeypatch, rot_k):
    patch, provider = _cold_case(17 + rot_k, rot_k)
    pages = tuple(range(6))
    config = PlacementConfig()
    budget = AttemptBudget(
        max_hypotheses=100_000_000,
        familywise_false_accept=1e-3,
        max_true_error_rate=0.08,
        qualification_id="parallel-exactness-fixture",
    )
    monkeypatch.delenv("HOLO_RECEIVE_WORKERS", raising=False)
    sequential = correlate_patch(
        patch, provider, pages, budget, ScoreMemo(provider),
        sample_key=11, config=config)
    workers_env(4)
    parallel = correlate_patch(
        patch, provider, pages, budget, ScoreMemo(provider),
        sample_key=11, config=config)
    assert parallel == sequential


def test_cold_search_heartbeat_call_list_identical(workers_env, monkeypatch):
    rng, sites, values = cold_fixtures._make_world(seed=17, page_count=200)
    provider = cold_fixtures._Provider(values, sites)
    patch = cold_fixtures._true_patch(
        rng, values[1], (4, 8), (16, 16), 0, flip_fraction=0.04)
    budget = AttemptBudget(
        max_hypotheses=100_000_000,
        familywise_false_accept=1e-3,
        max_true_error_rate=0.08,
        qualification_id="parallel-exactness-fixture",
    )
    pages = tuple(range(200))

    def sweep() -> tuple[object, list[tuple[int, int]]]:
        calls: list[tuple[int, int]] = []
        outcome = correlate_patch(
            patch, provider, pages, budget, ScoreMemo(provider),
            sample_key=11, config=PlacementConfig(),
            page_progress=lambda ordinal, total: calls.append(
                (ordinal, total)))
        return outcome, calls

    monkeypatch.delenv("HOLO_RECEIVE_WORKERS", raising=False)
    sequential_outcome, sequential_calls = sweep()
    workers_env(4)
    parallel_outcome, parallel_calls = sweep()
    assert parallel_outcome == sequential_outcome
    assert parallel_calls == sequential_calls
    assert len(parallel_calls) <= 64


class _ArrayRaster:
    """Minimal Raster stand-in for the survey tensor (frozen array)."""

    def __init__(self, pixels: np.ndarray) -> None:
        self._pixels = np.asarray(pixels, np.float32)
        self._pixels.setflags(write=False)
        self.shape = self._pixels.shape
        self.luma_max = float(self._pixels.max())

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        crop = np.array(
            self._pixels[r0:r1, c0:c1], np.float32, copy=True, order="C")
        crop.setflags(write=False)
        return crop


def test_survey_tensor_workers_bit_identical(workers_env, monkeypatch):
    rng = np.random.default_rng(29)
    raster = _ArrayRaster(rng.random((1200, 900), np.float32) * 255.0)
    monkeypatch.delenv("HOLO_RECEIVE_WORKERS", raising=False)
    # Small tile size forces a many-tile grid through the pooled path.
    sequential, step_sequential = _whole_tensor_score(
        raster, 12.0, tile_cells=16)
    workers_env(4)
    parallel, step_parallel = _whole_tensor_score(
        raster, 12.0, tile_cells=16)
    assert step_parallel == step_sequential
    assert sequential.dtype == parallel.dtype
    assert np.array_equal(sequential, parallel)

"""Invocation-scoped worker pool for bit-exact intra-stage parallelism.

EXPERIMENT (holo-parallel-tier1): every consumer must satisfy the
determinism contract — the parallel path reproduces the sequential
path's outputs bit-exactly for every worker count, because tasks are
pure functions of frozen inputs and every reduction happens on the
caller thread in submission order.  The knob is invocation-only
execution state (the ``--profile-timing`` family): it never enters
policy ids, schema, or durable records.

Worker count comes from ``HOLO_RECEIVE_WORKERS`` (default 1 =
sequential, the exact pre-experiment code path).  Tasks must not call
back into :func:`ordered_map` — nested calls run sequentially inline,
so a mis-nested consumer degrades to the sequential path instead of
deadlocking the shared pool.
"""
from __future__ import annotations

import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Iterator, Sequence, TypeVar

_ENV = "HOLO_RECEIVE_WORKERS"

_T = TypeVar("_T")
_R = TypeVar("_R")

_LOCK = threading.Lock()
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_SIZE = 0
_IN_WORKER = threading.local()
_OVERRIDE: int | None = None


def set_worker_count(count: int | None) -> None:
    """Process-wide execution override (the CLI ``--workers`` knob).

    ``None`` restores the ``HOLO_RECEIVE_WORKERS`` environment fallback.
    Execution-only state: results are bit-identical for any value.
    """
    global _OVERRIDE
    if count is not None:
        count = int(count)
        if count < 1:
            raise ValueError("worker count must be a positive integer")
    _OVERRIDE = count


def worker_count() -> int:
    """Configured worker count; 1 (sequential) on absent/invalid values."""
    if _OVERRIDE is not None:
        return _OVERRIDE
    raw = os.environ.get(_ENV, "").strip()
    if not raw:
        return 1
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _pool(size: int) -> ThreadPoolExecutor:
    global _EXECUTOR, _EXECUTOR_SIZE
    with _LOCK:
        if _EXECUTOR is None or _EXECUTOR_SIZE != size:
            if _EXECUTOR is not None:
                _EXECUTOR.shutdown(wait=False)
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=size, thread_name_prefix="holo-worker")
            _EXECUTOR_SIZE = size
        return _EXECUTOR


def _run_task(fn: Callable[[_T], _R], item: _T) -> _R:
    _IN_WORKER.active = True
    try:
        return fn(item)
    finally:
        _IN_WORKER.active = False


def parallel_active() -> bool:
    """True when called from inside a pool task (nesting guard)."""
    return bool(getattr(_IN_WORKER, "active", False))


def ordered_map(
    fn: Callable[[_T], _R],
    items: Sequence[_T],
    *,
    workers: int | None = None,
) -> list[_R]:
    """Map ``fn`` over ``items`` preserving order and first-error order.

    Sequential when the effective worker count is 1, when there is at
    most one item, or when already inside a pool task.  The parallel
    branch waits on futures in submission order, so results, first
    raised exception, and every caller-side reduction ordering are
    identical to the sequential branch.
    """
    n = worker_count() if workers is None else max(1, int(workers))
    if n <= 1 or len(items) <= 1 or parallel_active():
        return [fn(item) for item in items]
    pool = _pool(n)
    futures = [pool.submit(_run_task, fn, item) for item in items]
    return [future.result() for future in futures]


def submit_map(
    fn: Callable[[_T], _R],
    items: Sequence[_T],
    *,
    workers: int | None = None,
) -> Iterator[_R] | None:
    """Submission-order streaming variant; ``None`` means run sequential.

    The caller consumes results strictly in submission order (so
    per-item caller-side work, e.g. heartbeat emission or a running
    reduction, keeps the sequential order); items are computed
    concurrently ahead of consumption.
    """
    n = worker_count() if workers is None else max(1, int(workers))
    if n <= 1 or len(items) <= 1 or parallel_active():
        return None
    pool = _pool(n)
    futures: list[Future[_R]] = [
        pool.submit(_run_task, fn, item) for item in items]

    def _consume() -> Iterator[_R]:
        for future in futures:
            yield future.result()

    return _consume()


__all__ = [
    "ordered_map",
    "parallel_active",
    "set_worker_count",
    "submit_map",
    "worker_count",
]

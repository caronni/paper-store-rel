"""The orchestrator's observation half: minting one frozen instant.

Split out of ``orchestrator.py`` at H4 W2 for the file cap, and it is a
clean seam rather than a convenient one: everything here is DERIVED
(L12 — the observer never holds state, and a failure minting an instant
is reported into the surface instead of raised into the scheduler), and
nothing here decides anything. What is left in the control loop is the
loop.

Both functions take the running :class:`~holo2.engine.orchestrator.
Orchestrator` and read its own collections. That is the same contract the
two methods had when they lived on it — **main thread only, at a commit
boundary** — and stating it once here is what makes the reach into those
collections legible instead of merely allowed: the scheduler's ready set,
in-flight book, decline tables and lease book are touched by one thread,
so an instant minted from this thread is consistent by construction and
frozen the moment it is built.
"""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from .consult import close_progress
from .snapshot import QueueView, RunSnapshot, WorkerView, subscription_kinds

if TYPE_CHECKING:                                  # pragma: no cover
    from .orchestrator import Orchestrator


def publish(run: "Orchestrator") -> None:
    """Push one frozen instant at the observer. Never costs the run.

    L12 in the push direction: a failure minting the instant is reported
    into the surface, never raised into the scheduler.
    """
    status = run._status
    if status is None:
        return
    try:
        # Through the PUBLIC method, not the function below it: the
        # orchestrator's ``snapshot()`` is the one derivation entry point
        # in the tree (the CLI reads the terminal instant off it, and the
        # no-viewer throttle is pinned by counting calls to it).
        status.publish(run.snapshot())
    except Exception as exc:                  # observer failure is inert
        status.publish(error=f"{type(exc).__name__}: {exc}")


def snapshot(run: "Orchestrator") -> RunSnapshot:
    """The worker/queue story the diag surface must answer (§10.3).

    MAIN THREAD ONLY, and frozen once minted: it iterates the
    scheduler's live collections, which only this thread touches. Called
    at a commit boundary (and at the run's two ends), so it reads the
    state one commit left behind.
    """
    ctx = run._ctx
    # The second source's ready windows join the same row, under the
    # family it declares: an operator watching the queue is watching the
    # WORK, not the admission shape that carried it.
    source_counts = {} if run._source is None else run._source.counters()
    source_ready = int(source_counts.get("ready", 0))
    by_family = run._queue.by_family(
        run._workers,
        extra=None if run._source is None
        else (run._source.family, source_ready))
    sleeping = run._queue.sleeping(run._workers)
    by_key_kind = subscription_kinds(ctx.store.subscriptions(), sleeping)
    return RunSnapshot(
        recipe=run._recipe.label,
        complete=run._complete,
        mode="replay" if run._replay is not None else "free",
        pool_size=run._pool_size,
        providers=tuple(provider.provider_id for provider in run._providers)
        + ((run._source.source_id,) if run._source is not None else ()),
        queue=QueueView(depth=len(run._queue.ready) + source_ready,
                        by_family=dict(sorted(by_family.items()))),
        workers=WorkerView(
            total=len(run._workers) + int(source_counts.get("windows", 0)),
            running=tuple(str(worker_id) for worker_id in run._running),
            sleeping=len(sleeping),
            retired=len(run._queue.retired)
            + int(source_counts.get("retired", 0)),
            declined=len(run._declined),
            declined_pending=len(run._pending),
            declined_by_reason=dict(sorted(
                Counter(run._declined.values()).items())),
            fires_by_worker=dict(sorted(run._work.fires_by_worker.items()))),
        counters=run._work.counters(run._commits),
        stream=run._commits.stream(),
        leases=run._leases.residency(),
        sleeping_by_subscription_key=dict(sorted(by_key_kind.items())),
        # The plane's summaries are the plane's to compose: derived views
        # the engine does not type.
        plane=ctx.plane.observer_summary(),
        close=close_progress(run._last_close,
                             len(run._view.certified_work_keys())),
    )


__all__ = ["publish", "snapshot"]

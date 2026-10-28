"""The descriptor queue, and what one admission carries.

Split out of ``orchestrator.py`` at H4 W2, when placement work stopped
being descriptors and the orchestrator grew a SECOND admission source.
What lives here is the mechanics of the first one — which minted workers
are queued, in what order they pop, which are in flight and which have
retired — plus the two value types an admission produces
(:class:`Armed`, :class:`Proposal`), which are what BOTH sources hand the
control loop. There is no policy in any of it: eligibility is the
provider's, pricing is the recipe's, and the merge between the two
sources is the orchestrator's.

Three properties this class exists to keep true:

* **the heap is ordered by COST, not by arrival** (H4 W2's global order).
  A recipe entry declares the price of the work it offers, and the queue
  pops the cheapest ready worker; the ordinal beside it is the arrival
  tie-break, which is what stops equal-priced work from starving on
  ``WorkId`` ordering.
* **lazy deletion.** ``push`` may leave a stale entry behind, so ``pop``
  skips anything no longer in the ready set. The retirement re-test that
  used to follow it was dead and stays gone (0 retired ids popped in
  7,029 pops, measured across serial, pool and replay).
* **a wake is deferred, never dropped.** Continuous admission lets a
  commit land while other fires run, so a wake can reach a worker that
  is ALREADY armed; arming it twice would run two fires against one
  identity. :meth:`push` holds that wake and :meth:`release` re-delivers
  it. Under the old barrier the deferral was structural — a round
  disarmed before it refilled.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any, Mapping

from ..core import (AttemptIdentity, CommitBatch, ResourceKey, WorkDescriptor,
                    WorkId, WorkResult, Worker, WorkSource)


@dataclass(frozen=True)
class Armed:
    """One worker bound to what it will propose over.

    ``source`` is the H4 W2 discriminator and the only branch the rest of
    this loop needs. BOTH shapes carry a read-set and the identity taken
    over it — the wall re-derives that identity for every proposal it
    admits, so a job armed without one could never be admitted at all —
    and what a source job does NOT carry is a spend row or a
    subscription: repetition is its source's flag and tried set, not the
    ledger's, and its read-set is the short list of keys whose transition
    laws could refuse its writes (R5's lattice seed) rather than a
    declaration of what wakes it. The source it came from is settled
    after the commit.
    """

    descriptor: WorkDescriptor
    worker: Worker
    keys: tuple[ResourceKey, ...]
    identity: AttemptIdentity
    entry_index: int
    cost: int = 0
    source: WorkSource | None = None

    @property
    def worker_id(self) -> WorkId:
        return self.descriptor.work_id


@dataclass(frozen=True)
class Proposal:
    """What one fire produced: a batch, not a commit.

    Deliberately NO digest: the wall settles merge-declared writes
    against current state, so the committed batch can lawfully differ
    from the proposed one — the only honest batch id is the wall's own,
    over the SETTLED batch (``CommitResult.batch_id``). A proposal-side
    digest rode here until 2026-08-17; production never read it, and
    the profile priced it at 0.32 s/run (write-only work per fire).
    """

    armed: Armed
    result: WorkResult
    units: int
    batch: CommitBatch


class Worklist:
    """One session's queue of minted, priced, spend-once descriptors."""

    def __init__(self) -> None:
        self.ready: set[WorkId] = set()
        #: Cost and recipe-entry ordinal per admitted worker. The cost is
        #: what the heap orders by; the entry is what prices the fire.
        self.cost: dict[WorkId, int] = {}
        self.entry: dict[WorkId, int] = {}
        self.retired: set[WorkId] = set()
        #: Armed or running, by cost: what the ready set alone does not
        #: say about how much cheaper work is still in play.
        self.inflight: dict[WorkId, int] = {}
        self._heap: list[tuple[int, int, WorkId]] = []
        self._rewake: set[WorkId] = set()
        self._ordinal = 0

    # -- membership --------------------------------------------------------

    def admit(self, worker_id: WorkId, *, cost: int, entry: int) -> None:
        """Record what one worker costs and which entry offered it.

        Called at the mint, and AGAIN on every wake since H5's re-work
        aging: a worker is minted once (the orchestrator's ``_workers``
        is monotone) but re-queued many times, and its price is a
        function of how many attempts it has already spent — so the book
        this keeps is "what it costs now", not "what it cost when it was
        new". :meth:`push` reads it at push time, which is what makes a
        re-price take effect on the very next queueing, including the one
        :meth:`release` delivers out of the re-wake set.
        """
        self.cost[worker_id] = cost
        self.entry[worker_id] = entry

    # -- the queue ---------------------------------------------------------

    def push(self, worker_id: WorkId) -> None:
        """Queue one worker, unless its own fire is still in flight."""
        if worker_id in self.retired or worker_id in self.ready:
            return
        if worker_id in self.inflight:
            self._rewake.add(worker_id)
            return
        self.ready.add(worker_id)
        self._ordinal += 1
        heapq.heappush(self._heap, (self.cost.get(worker_id, 0),
                                    self._ordinal, worker_id))

    def head_cost(self) -> int | None:
        """The cheapest ready worker's cost, tombstones dropped."""
        while self._heap:
            if self._heap[0][2] in self.ready:
                return self._heap[0][0]
            heapq.heappop(self._heap)
        return None

    def pop(self) -> WorkId | None:
        """Pop the next ready worker, skipping the heap's tombstones."""
        while self._heap:
            _cost, _ordinal, worker_id = heapq.heappop(self._heap)
            if worker_id in self.ready:
                self.ready.discard(worker_id)
                return worker_id
        return None

    def retire(self, worker_id: WorkId) -> None:
        """Out of the domain for good. The queue no longer holds it.

        No ``ready`` discard: retirement follows the fire of a worker the
        run popped and armed, so it is not queued, and :meth:`push`
        refuses to re-queue it — including the held wake that
        :meth:`release` delivers a moment later.
        """
        self.retired.add(worker_id)

    # -- the in-flight book ------------------------------------------------

    def take(self, worker_id: WorkId) -> None:
        """Book one worker as in flight — and out of the ready set.

        The discard is normally a no-op: the live path takes a worker
        :meth:`pop` just handed it. It is load-bearing for the ONE caller
        that arms by NAME rather than by queue order — replay, which
        launches the pass a start marker names (H4 W2) — where leaving
        the worker ready would have the live phase after a recovery fire
        it a second time.
        """
        self.ready.discard(worker_id)
        self.inflight[worker_id] = self.cost.get(worker_id, 0)

    def release(self, worker_id: WorkId) -> None:
        self.inflight.pop(worker_id, None)
        if worker_id in self._rewake:
            self._rewake.discard(worker_id)
            self.push(worker_id)

    # DELETED 2026-08-17 (the pricing ruling): ``cheapest_in_play`` and
    # its ``ignore``-filtered ``_ready_head`` answered "how much cheaper
    # work is still in play here" for the quiescent gate, and that gate
    # was their only caller. What survives is the pair of books the
    # gated-TIER rule reads directly — ``head_cost`` for the ready half
    # and ``inflight`` for the other, both still exactly F-22.1's two
    # halves.

    def by_family(self, workers: Mapping[WorkId, Any], *,
                  extra: tuple[str, int] | None = None) -> dict[str, int]:
        """Ready work per family, with a second source's own tally folded in."""
        counts: dict[str, int] = {}
        for worker_id in self.ready:
            family = workers[worker_id][0].family
            counts[family] = counts.get(family, 0) + 1
        if extra is not None and extra[1]:
            counts[extra[0]] = counts.get(extra[0], 0) + extra[1]
        return dict(sorted(counts.items()))

    def sleeping(self, workers: Mapping[WorkId, Any]) -> list[WorkId]:
        """Admitted, not ready, not RUNNING, not retired — the observer's.

        The in-flight book is subtracted because the vocabulary the
        observer publishes reads as a partition: a worker whose fire is
        out was otherwise counted twice, once in ``running`` and again in
        ``sleeping`` (and again under its subscription key), which at
        ``--workers N`` is every fire the run has out.
        """
        return sorted(worker_id for worker_id in workers
                      if worker_id not in self.ready
                      and worker_id not in self.inflight
                      and worker_id not in self.retired)


__all__ = ["Armed", "Proposal", "Worklist"]

"""Enumeration: turning durable facts into minted, priced workers (P2/P3).

Split out of ``orchestrator.py`` with the streaming-ingestion build for
the file cap, along the seam the tree already cuts — ``worklist.py`` owns
the QUEUE, ``replay.py`` owns the recorded ordering, ``observe.py`` owns
the published instant, and this owns the FRONTIER: asking each
enumerable recipe entry's sources what
work exists now, minting a worker or recording a decline for each
descriptor that comes back, and skipping the offers whose disposition can
no longer move.

Nothing here is policy of its own. Eligibility is the provider's and
pricing is the recipe's and the source's; what this module holds is the
enumeration MECHANISM and the two optimizations that keep it affordable —
the re-offer skip (F-17) and the entry stamp taken after the
already-handled test. Since the 2026-08-17 pricing ruling it holds no
gate at all: every work entry expands on every refresh, and what used to
be deferred enumeration (finer footings behind a ``quiescent`` gate) is a
price the placement source charges its own finer windows.

Same contract as ``replay.py``'s and ``observe.py``'s: the functions take
the running :class:`~holo2.engine.orchestrator.Orchestrator` and drive its
own machinery, main thread only, and nothing here holds state.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable, TYPE_CHECKING

from ..core import (Decline, ExpansionRequest, ProtocolViolation, Provider,
                    WorkDescriptor, Worker)

if TYPE_CHECKING:                                  # pragma: no cover
    from .orchestrator import Orchestrator


def refresh(run: "Orchestrator") -> None:
    """Ask every enumerable entry's sources to expand the frontier.

    Generic over families: the engine supplies the entry's policy
    (selector, arm, identity) and admits whatever comes back. One already
    admitted, permanently declined or sleeping on a re-offer wake is
    skipped without minting anything.

    The work SOURCE expands from the same place — ``admit`` is its
    ``expand`` — and since 2026-08-17 that is the whole of it: EVERY
    entry is asked at every refresh, finer footings included, so a
    window enters the scheduling set as soon as its geometry exists.
    Coarse-before-fine is not lost, it moved: the source charges a finer
    window's passes the footing premium, and the one global cost order
    does the ordering that a deferred enumeration used to do.
    """
    for index, entry in enumerate(run._work_entries):
        request = ExpansionRequest(entry=entry.label,
                                   selector=entry.footing_selector,
                                   arm=entry.arm)
        source = run._source
        if source is not None and source.family == entry.task_class:
            source.admit(run._view, entry=index,
                         selector=entry.footing_selector)
        for provider in run._by_family.get(entry.task_class, ()):
            offer_expansion(run, provider,
                            provider.expand(run._view, request),
                            index, entry.label)


def offer_expansion(run: "Orchestrator", provider: Provider,
                    descriptors: Iterable[WorkDescriptor],
                    entry_index: int, entry_label: str) -> None:
    """Offer one expansion, skipping what cannot have changed answer.

    An expansion is TOTAL by design — a provider re-yields its whole
    frontier, because emitting only the changed keys would need engine
    state a provider may not hold
    (``payload.RealPayloadProvider.expand``) — so a serial
    gen-clean run offered 1,677,186 descriptors to mint 1,768 workers:
    the other 1.68 M built a ``WorkId`` only to fail the same membership
    test they failed at the previous refresh, 4.95 s cum and 33% of the
    whole commit path once the derived views went incremental (F-17's
    named residual).

    The skip is EXACT, not merely fast, and rests on two facts together.
    The dispositions it skips are MONOTONE — ``_workers`` and
    ``_declined`` are only ever added to, so a work id in either is in it
    forever and the test's answer cannot move — and the descriptor is the
    SAME OBJECT the provider handed back last time, which is what says
    the work id would be the same one. Everything else takes the full
    path and reaches the identical result: a sleeping decline
    (``_absorb`` un-parks it, so its answer DOES move), and any
    descriptor a provider re-derived. Nothing about which descriptors are
    minted, or in what order, changes — this returns earlier for offers
    that already returned.

    The pin holds the descriptor OBJECT, not merely its id (an id is
    unique only among LIVE objects, so holding it is what makes ``is``
    sound), and is REPLACED by each expansion — one expansion's worth of
    references, and a provider that mints fresh descriptors every refresh
    simply never hits it.
    """
    bucket = (entry_index, provider.provider_id)
    pinned = run._offered.get(bucket, {})
    settled: dict[int, WorkDescriptor] = {}
    for descriptor in descriptors:
        marker = id(descriptor)
        if pinned.get(marker) is descriptor:
            settled[marker] = descriptor
        elif offer(run, provider, descriptor, entry_index, entry_label):
            settled[marker] = descriptor
    run._offered[bucket] = settled


def offer(run: "Orchestrator", provider: Provider, descriptor: WorkDescriptor,
          entry_index: int, entry_label: str) -> bool:
    """Mint one descriptor's worker, or record its decline (M2).

    Answers whether the disposition is FINAL — admitted or permanently
    declined, the two the engine records in a collection it never removes
    from — which is what :func:`offer_expansion` is entitled to skip on
    the next refresh.

    The entry stamp lands AFTER the already-handled test, not before it:
    the recipe entry is provenance and is deliberately not part of a work
    id (``WorkDescriptor.work_id``), so stamping it first rebuilt a
    frozen dataclass for every descriptor a re-enumeration offered and
    immediately dropped — 1.68 M per serial run (F-17). What is admitted
    is the identical value it always was.
    """
    work_id = descriptor.work_id
    if work_id in run._workers or work_id in run._declined:
        return True
    if work_id in run._pending:
        return False
    descriptor = replace(descriptor, entry=entry_label)
    minted = provider.worker(run._view, descriptor)
    if isinstance(minted, Decline):
        if minted.permanent:
            run._declined[work_id] = minted.reason
            return True
        run._pending[work_id] = minted.reason
        run._sleep(work_id, tuple(sorted(set(minted.wake_on))))
        return False
    if not isinstance(minted, Worker):
        raise ProtocolViolation(
            f"{provider.provider_id} answered {work_id} with "
            f"{type(minted).__name__}, which is neither a worker nor a "
            "decline")
    admit(run, descriptor, minted, entry_index)
    return True


def admit(run: "Orchestrator", descriptor: WorkDescriptor, worker: Worker,
          entry_index: int) -> None:
    """Enter one minted worker into the queue at its entry's price.

    Plus the descriptor's own LANE TERM (H4-LANES stage 2): pricing is
    still the recipe's — the entry says what this class of work costs —
    and the one thing an entry cannot know is which rung of a capture's
    ladder a particular attempt reads through, which the provider stamps
    on the descriptor. It composes exactly the way the placement source
    composes its own (tier plus lane term), so the two admission paths
    put comparable numbers into one order.

    The composition moved into ``Orchestrator.price`` at H5 so that the
    RE-WORK ORDINAL has one home with the other two terms. Nothing about
    a FIRST admission changed and nothing could: a work id reaches this
    function before it has ever fired, so its ledger row does not exist
    and ``recipe.work_price`` is the identity on entry cost plus premium.
    Where the ordinal actually bites is the wake (``_absorb``), which is
    where a re-attempt is re-queued.
    """
    work_id = descriptor.work_id
    run._workers[work_id] = (descriptor, worker)
    run._queue.admit(work_id, cost=run.price(descriptor, entry_index),
                     entry=entry_index)
    run._queue.push(work_id)


__all__ = ["admit", "offer", "offer_expansion", "refresh"]

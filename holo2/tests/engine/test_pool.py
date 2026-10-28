"""The proposal pool: admission, dispatch, and the N=1 escape.

Unit tests over the same captureless session ``test_orchestrator.py``
uses — no pixels, no survey, no toys — so what is under test is the
pool mechanism itself: what goes in flight, how much, in what order,
the source-job admission/gating rules, preemption of fires still in
flight, and that ``--workers 1`` never builds a pool at all. The commit
wall's OWN conflict resolution when a proposal lands mid-flight —
staleness discard vs the commutative tile merge — moved to the sibling
module ``test_pool_wall.py``, split out 2026-08-17 once this file
crossed 1000 lines, under the line-cap-as-seam-signal ruling (CLAUDE.md
memory: the cap is a split-here signal, never a budget to game by
squeezing prose).

**Two lanes** (H4-PLAN §4/W-S, R9). Since continuous admission the wall
commits in COMPLETION order, so a live parallel run is not a
deterministic function of the state it started from; exact-order and
exact-count pins live on the serial lane, and a parallel run is pinned
on what is schedule-independent — the certificate SET, zero wrong
certificates, and the mechanism counters. Where a parallel test needs a
particular interleaving it MAKES one (an event a fire waits on, released
from the wall) rather than hoping for it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from holo2.engine import orchestrator as orchestrator_module
from holo2.engine.orchestrator import Orchestrator
from holo2.core.commit import CommitBatch, Write
from holo2.core.records import CLOSE_KEY, CloseRecord, CloseStatus
from conftest import FOOTING, REGION, WINDOW, make_window, spy_on_commits
from holo2.solve import TileRecord, tile_key, window_key
from holo2.solve.close import COLLECTION_CERTIFIED

from holo2.engine.recipe import (COST_PAYLOAD, COST_PLACE_ENTRY,
                                 COST_PLACE_WIDE, FOOTING_ALL,
                                 GATE_ALWAYS, GATE_COUNT_READY,
                                 PriceTable, Recipe,
                                 RecipeEntry, TASK_CLOSE, TASK_PAYLOAD,
                                 TASK_PLACE)
from holo2.core.resources import ResourceKey
from holo2.core.work import Lease, SourceJob, WorkResult
from test_orchestrator import (ADDRESSES, CertifyingWorker, Factories, RECIPE,
                               make_orchestrator, make_session,
                               seed_addressed)


# ------------------------------------------------------------ N=1 is N=1

def test_one_worker_never_builds_a_pool(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """``--workers 1`` takes the sequential path verbatim (DESIGN §10.1)."""

    def refuse(*args: object, **kwargs: object):
        raise AssertionError("--workers 1 must not construct a thread pool")

    monkeypatch.setattr(orchestrator_module, "ThreadPoolExecutor", refuse)
    with make_session(tmp_path) as session:
        seed_addressed(session)
        outcome = make_orchestrator(session, RECIPE, Factories(), workers=1).run()
    assert outcome.certified == 4 and outcome.fires == 4


def test_a_pool_needs_at_least_one_worker(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        with pytest.raises(ValueError):
            make_orchestrator(session, RECIPE, Factories(), workers=0)


# --------------------------------------------------- the same answer at N

def test_the_certificate_set_does_not_depend_on_the_pool_size(
        tmp_path: Path) -> None:
    """L10 at the control-plane level: threads change wall time, not facts."""
    certified: dict[int, tuple] = {}
    for size in (1, 2, 8):
        with make_session(tmp_path, f"state-{size}") as session:
            seed_addressed(session)
            outcome = make_orchestrator(session, RECIPE, Factories(),
                                   workers=size).run()
            certified[size] = session.plane.tiles().certified_keys()
        assert outcome.certified == 4
    assert certified[1] == certified[2] == certified[8]


def _commit_order(tmp_path: Path, name: str, *, workers: int) -> list:
    committed: list = []

    class Recording(CertifyingWorker):
        route = "pool-order"

    with make_session(tmp_path, name) as session:
        seed_addressed(session)
        orchestrator = make_orchestrator(session, RECIPE, Factories(Recording),
                                         workers=workers)
        spy_on_commits(orchestrator,
                       lambda proposal: committed.append(
                           proposal.armed.worker_id))
        orchestrator.run()
    return committed


def test_one_worker_commits_in_the_serial_heap_order(tmp_path: Path) -> None:
    """The exact-order oracle, on the lane that still owns it (R9)."""
    committed = _commit_order(tmp_path, "serial", workers=1)
    assert committed == sorted(committed)
    assert len(committed) == len(ADDRESSES)


def test_a_pool_commits_the_same_set_in_completion_order(
        tmp_path: Path) -> None:
    """R9's declared price: order is the pool's, the SET is the fixpoint's.

    Order is asserted only as "every queue member committed exactly
    once"; whether it came out sorted is a scheduling accident this run
    is allowed to have either way.
    """
    committed = _commit_order(tmp_path, "pooled", workers=8)
    assert sorted(committed) == _commit_order(tmp_path, "serial", workers=1)
    assert len(set(committed)) == len(ADDRESSES)


def test_the_whole_ready_set_goes_in_flight_at_once(tmp_path: Path) -> None:
    """A free slot is filled before the wall blocks, so the pool runs wide."""
    with make_session(tmp_path) as session:
        seed_addressed(session)
        orchestrator = make_orchestrator(session, RECIPE, Factories(), workers=8)
        orchestrator.run()
    counters = orchestrator.snapshot().counters
    assert counters.peak_inflight == len(ADDRESSES)
    assert counters.dispatched == len(ADDRESSES)
    assert counters.cancelled == 0


# ------------------------------------- the SECOND source's own staleness

#: A window nothing else in this module builds, so the pull job's fact is
#: unambiguous evidence that its proposal reached the store.
PULL_EXTENT = (240, 0, 248, 128)
PULL_SUBJECT = window_key(FOOTING, REGION, PULL_EXTENT)


class PullWorker:
    """A source job that DECLARES a read-set, the way ``place_job`` does.

    Non-empty on purpose. A pull job subscribes to nothing and spends
    nothing, but it BINDS the one key whose transition law could refuse
    its write (R5's lattice seed), so the wall's re-derivation gives it
    the ordinary stale discard instead of a fatal ``CommitRefusal``. That
    only works if the identity taken at arm time is the identity the wall
    re-derives — which is what this pin exists to hold.
    """

    def __init__(self, leases: tuple[Lease, ...] = ()) -> None:
        self.fires = 0
        #: WHAT THIS FIRE HOLDS WHILE IT RUNS (M5, and W4's pull half).
        #: A push descriptor declares its leases when it is minted; a
        #: source job has no descriptor until the arm synthesises one, so
        #: the worker is the only party that can declare anything — which
        #: is how ``place_cold``'s page transforms reach the book.
        self.leases = leases
        self.residency: list[dict] = []

    def read_keys(self, view):
        return (WINDOW,)

    def run(self, view, identity, progress):
        self.fires += 1
        progress.emit(1, "pull")
        return WorkResult(outcome="accepted", writes=(
            Write(PULL_SUBJECT, make_window(extent_cells=PULL_EXTENT)),))


class OneJobSource:
    """A minimal ``core.WorkSource``: one ready subject, then dry.

    ``passes`` is a hard budget, not a policy: a build in which every
    source proposal is discarded as stale re-arms forever, and a test
    must fail on that rather than hang the suite. ``settle`` is
    idempotent per claim, as ``place_sched``'s is (it pops its claim
    book), because the commit path settles the subject and ``_disarm``
    then settles it again with ``None``.
    """

    source_id = "unit-pull-source"
    family = TASK_PLACE

    def __init__(self, *, passes: int = 4, cost: int = COST_PLACE_ENTRY,
                 gated: bool = False,
                 leases: tuple[Lease, ...] = ()) -> None:
        self.worker = PullWorker(leases)
        self.settled: list = []
        self.budget = passes
        self.cost = cost
        self.gated = gated
        self._ready = False
        self._entered = False
        self._in_flight = False

    def admit(self, view, *, entry: int, selector: str) -> None:
        if not self._entered:
            self._entered = True
            self._ready = True

    def peek(self):
        if not self._ready or self._in_flight or not self.budget:
            return None
        return SourceJob(cost=self.cost, entry=0, subject=PULL_SUBJECT,
                         gated=self.gated)

    def claim(self, view, subject):
        if not self._ready or self._in_flight or not self.budget:
            return None
        self._ready = False
        self._in_flight = True
        self.budget -= 1
        return self.worker

    def settle(self, view, subject, result) -> None:
        if not self._in_flight:
            return                   # already settled: ``_disarm``'s tail
        self._in_flight = False
        self.settled.append(result)
        if result is None:
            self._ready = True       # abandoned: the flag comes back

    def counters(self):
        return {}


PULL_RECIPE = Recipe("recipe-pull-unit", (
    RecipeEntry(TASK_PLACE, FOOTING_ALL, GATE_ALWAYS, COST_PLACE_ENTRY),
    RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
))


def test_a_source_job_binds_the_identity_the_wall_re_derives(
        tmp_path: Path) -> None:
    """H4 W2: the pull job's read-set is taken at ARM time, or nothing commits.

    The wall re-derives every proposal's identity before admitting it
    (§7), source jobs included. A source job armed with an EMPTY identity
    over a worker that names a key can never match that re-derivation, so
    every pull pass would be discarded as stale, re-armed, and discarded
    again — placement making no progress at any pool size while the
    serial lane, which never re-derives, stayed green.
    """
    with make_session(tmp_path) as session:
        source = OneJobSource()
        orchestrator = make_orchestrator(session, PULL_RECIPE, (),
                                         source=source, workers=4)
        orchestrator.run()
        record = session.store.get(PULL_SUBJECT)
    counters = orchestrator.snapshot().counters
    assert record is not None, "the pull job's fact never reached the store"
    assert source.worker.fires == 1, "the job fired more than once"
    assert [result is not None for result in source.settled] == [True]
    assert counters.stale_discards == 0


def test_a_source_worker_declares_residency_the_book_holds_and_releases(
        tmp_path: Path) -> None:
    """M5 ON THE PULL PATH (W4): the cold pair's transforms, end to end.

    The push half has held leases since M5
    (``test_provider_protocol``); the pull half took an empty tuple on
    every fire, because a source job has no descriptor until the arm
    synthesises one and nothing asked the WORKER. The cold pair is the
    first pull worker with residency worth reading, so this pins the
    whole chain on a source double: worker declares -> the synthesised
    descriptor carries -> ``LeaseBook`` holds it for the duration ->
    ``_disarm`` releases it on every path there is.
    """
    resource = ResourceKey("cold-transforms", ("unit", "pull"))
    seen: list[dict] = []
    with make_session(tmp_path) as session:
        source = OneJobSource(leases=(Lease(resource, weight=7),))
        orchestrator = make_orchestrator(session, PULL_RECIPE, (),
                                         source=source, workers=1)
        original = PullWorker.run

        def spy(self, view, identity, progress):
            seen.append(orchestrator.snapshot().leases)
            return original(self, view, identity, progress)

        PullWorker.run = spy
        try:
            orchestrator.run()
        finally:
            PullWorker.run = original
    assert seen == [{str(resource): 7}], (
        "a pull fire's declared residency never reached the book")
    assert orchestrator.snapshot().leases == {}, "a lease outlived its fire"


def test_a_gated_job_waits_for_cheaper_work_ready_or_in_flight(
        tmp_path: Path) -> None:
    """Q3+Q6 at the ENGINE: the expensive tier's own admission rule.

    The source declares ``gated`` (that half is pinned in
    ``test_place_sched``); this is the half that acts on it. A gated job
    is the cheapest thing on offer here — nothing else is even
    enumerable — and it still may not start while a payload fire that
    could DELETE its window is ready or running: *"if we devolve into
    'let's run a cold search on everything remaining' before all payload
    is decoded, we are going to burn ourselves."*

    IN FLIGHT is the half no serial run can exercise (nothing is in
    flight when a serial ``_next`` asks) and the half a dropped
    ``_source_inflight`` extension would silently lose. Dryness is read
    INSTANTANEOUSLY, not finally (ruled with the build): the release of
    the last cheaper fire re-opens the tier in the same breath.
    """
    with make_session(tmp_path) as session:
        source = OneJobSource(cost=COST_PLACE_WIDE, gated=True)
        engine = make_orchestrator(session, PULL_RECIPE, (), source=source)
        engine._refresh()                    # the source admits its subject
        queue = engine._queue
        assert engine._next() == "source", "nothing cheaper exists at all"

        queue.admit("payload", cost=COST_PAYLOAD, entry=0)
        queue.push("payload")
        assert engine._next() == "queue", "cheaper work is READY"
        assert queue.pop() == "payload"
        queue.take("payload")
        assert engine._next() is None, (
            "the gated job started while cheaper work was IN FLIGHT")
        queue.release("payload")
        assert engine._next() == "source", "dryness is instantaneous"

        # THE DISCRIMINATOR: the flag is what defers, not the cost order.
        # An ungated job of the same price is admitted in the same state.
        open_source = OneJobSource(cost=COST_PLACE_WIDE)
        ungated = make_orchestrator(session, PULL_RECIPE, (),
                                    source=open_source)
        ungated._refresh()
        ungated._queue.admit("payload", cost=COST_PAYLOAD, entry=0)
        ungated._queue.take("payload")
        assert ungated._next() == "source"


class GatedPairSource:
    """Two subjects: a cheap one to arm, and a gated dear one behind it.

    ``OneJobSource`` cannot express the second half of the rule — its one
    subject is either offered or in flight — and the source's OWN
    in-flight book is exactly what the engine must also count.
    """

    source_id = "unit-gated-pair"
    family = TASK_PLACE

    CHEAP = window_key(FOOTING, REGION, (0, 0, 8, 8))

    def __init__(self) -> None:
        self.worker = PullWorker()
        self._in_flight: set = set()

    def admit(self, view, *, entry: int, selector: str) -> None:
        return None

    def peek(self):
        offers = [SourceJob(cost=COST_PLACE_ENTRY, entry=0, subject=self.CHEAP),
                  SourceJob(cost=COST_PLACE_WIDE, entry=0,
                            subject=PULL_SUBJECT, gated=True)]
        ready = [job for job in offers if job.subject not in self._in_flight]
        return min(ready, key=lambda job: job.cost) if ready else None

    def claim(self, view, subject):
        self._in_flight.add(subject)
        return self.worker

    def settle(self, view, subject, result) -> None:
        self._in_flight.discard(subject)

    def counters(self) -> dict:
        return {}


def test_a_gated_job_counts_the_sources_own_in_flight_work(
        tmp_path: Path) -> None:
    """The other in-flight book: a cheap PLACEMENT pass, still running.

    ``_next`` reads two in-flight books — the queue's and the source's —
    and the rule is "anything cheaper, anywhere". A gated head that
    consulted only the queue would start a wide pass beside a ring pass
    that may be about to ping the very window it is about to search.
    """
    with make_session(tmp_path) as session:
        source = GatedPairSource()
        engine = make_orchestrator(session, PULL_RECIPE, (), source=source)
        engine._refresh()
        armed = engine._take("source")           # the CHEAP job, in flight
        assert armed is not None
        assert engine._next() is None, (
            "the wide job started while a cheaper pass was in flight AT THE "
            "SOURCE")
        engine._disarm(armed)
        source._in_flight.add(GatedPairSource.CHEAP)   # placed: it is gone
        assert engine._next() == "source"


# --------------------------------------- preemption and quiescence (F-22)

@dataclass(frozen=True)
class _Verdict:
    """A ``CloseVerdict``: three members, all core types or JSON."""

    writes: tuple = ()
    blobs: tuple = ()
    report: dict[str, Any] = field(default_factory=dict)


class ClosingConsult:
    """A terminal consumer that goes terminal at the first certificate.

    The unit fixture's four tiles never satisfy the real close (the L9
    metadata floor is 48), so preemption needs a consumer that decides
    early. It writes an ordinary terminal ``CloseRecord``, which is the
    only thing the orchestrator reads a terminal answer off (B12).
    """

    frontier = COLLECTION_CERTIFIED

    def consult(self, view, *, mode: str) -> _Verdict:
        if not view.certified_work_keys():
            return _Verdict(report={"status": "open"})
        return _Verdict(
            writes=(Write(CLOSE_KEY, CloseRecord(
                status=CloseStatus.UNSUPPORTED,
                reason="unit close: preempt at the first certificate")),),
            report={"status": "unsupported"})


def test_a_terminal_close_cancels_the_fires_in_flight(tmp_path: Path) -> None:
    """F-22.4's other half: preemption is worth nothing if it pays anyway.

    Four workers go in flight together; the first admission closes the
    session, and the other three proposals are dropped unread — counted,
    never committed, so no certificate but the first one exists.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        orchestrator = Orchestrator(session, RECIPE, Factories(),
                                    close=ClosingConsult(), workers=8)
        outcome = orchestrator.run()
        certified = session.plane.tiles().certified_keys()
    counters = orchestrator.snapshot().counters
    assert outcome.status == "unsupported"
    assert counters.peak_inflight == len(ADDRESSES)
    assert counters.cancelled == len(ADDRESSES) - 1
    assert counters.fires == 1
    assert len(certified) == 1, "a straggler's proposal was admitted anyway"
    assert orchestrator.snapshot().workers.running == ()


# DELETED 2026-08-17 with the quiescent gate (pricing ruling): the
# ``Later`` probe provider, ``QUIESCENT_RECIPE``, the ``Rendezvous``
# worker and
# ``test_a_quiescent_entry_waits_for_the_last_in_flight_fire``. That test
# pinned F-22.1 — an ARMED or RUNNING fire is not a quiet queue — through
# the one gate that consumed the answer, and enumeration is now
# unconditional. The SAME definition is still pinned, over the same two
# books, by the gated-tier pair above
# (``test_a_gated_job_waits_for_cheaper_work_ready_or_in_flight`` and
# ``test_a_gated_job_counts_the_sources_own_in_flight_work``), which is
# the surviving instantaneous-dryness rule.


# ------------------------------------------------- the contracts survive

def test_the_fire_count_tripwire_holds_under_a_pool(tmp_path: Path) -> None:
    """The price is charged at ARM time, so a pool cannot outrun it."""
    from test_orchestrator import ChurningWorker
    from holo2.engine.orchestrator import FireCountTripwire

    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        recipe = Recipe("recipe-churn-pool", (
            RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD,
                        PriceTable(max_fires_per_worker=4)),
            RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
        ))
        with pytest.raises(FireCountTripwire):
            make_orchestrator(session, recipe, Factories(ChurningWorker),
                         workers=8).run()


def test_a_silent_stage_is_still_a_failure_under_a_pool(tmp_path: Path) -> None:
    from test_orchestrator import SilentWorker
    from holo2.core.work import SilentStage

    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        with pytest.raises(SilentStage):
            make_orchestrator(session, RECIPE, Factories(SilentWorker),
                         workers=8).run()


def test_a_certificate_conflict_still_ends_the_run(tmp_path: Path) -> None:
    """L5 lives at the commit wall, which the pool never crosses.

    Same terminal fact as the serial path (F-11) and for the same
    structural reason: a round proposes in parallel and commits on the
    main thread, so the conflict is raised — and caught — in exactly one
    place regardless of ``--workers``.
    """
    from holo2.core import CloseStatus
    from test_orchestrator import Rogue

    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        make_orchestrator(session, RECIPE, Factories(bit=1), workers=8).run()
        session.apply(CommitBatch(writes=(
            Write(tile_key(0, 0, 1, "main"),
                  TileRecord()),)))
        outcome = make_orchestrator(session, RECIPE, Rogue(), workers=8).run()
        assert outcome.status == "integrity_failure"
        record = session.close_record()
        assert record is not None
        assert record.status is CloseStatus.INTEGRITY_FAILURE
        assert record.reason == outcome.reason

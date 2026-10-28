"""Orchestrator v0: queue, idleness, wakes, tripwires, stop conditions.

These are unit tests over a captureless session — no pixels, no survey,
no toys — so what is under test is the control loop itself: which worker
runs, when it stops running, what wakes it, and what kills the run.

R1 shape: work arrives through PROVIDERS. The scaffolding below is a
minimal payload provider — which is all the recipe under test queues —
plus the real volume close, handed over as the engine's TERMINAL
CONSUMER rather than as a third provider (worklist B12, ruled
2026-08-12). :func:`make_orchestrator` is the one place that wiring is
written down, exactly as the composition root writes it once.
"""
from __future__ import annotations

from fractions import Fraction

from pathlib import Path

import numpy as np
import pytest

from holo2.diag import status as diag
from holo2.core.commit import (CommitBatch, CommitEngine, CommitResult,
                               StateRegression, Write)
from holo2.format.close_spec import CloseStreamProfile
from holo2.engine.orchestrator import FireCountTripwire, Orchestrator
from holo2.core.blobs import stage_array
from holo2.core.records import CLOSE_KEY, CloseRecord, CloseStatus
from conftest import (FOOTING, POSE, REGION, WINDOW, lattice_seed_key,
                      make_seed, make_window)
from holo2.core import WorkId, WorkScope
from holo2.solve import MintRef, TileRecord, WindowStatus, tile_key

from holo2.core.work import WorkDescriptor, WorkScope
from holo2.engine.recipe import (COST_PAYLOAD, FOOTING_ALL, GATE_ALWAYS,
                                 GATE_COUNT_READY, PriceTable, REWORK_BASE,
                                 REWORK_STEP, Recipe,
                                 RecipeEntry, TASK_CLOSE, TASK_PAYLOAD)
from holo2.engine.worklist import Worklist
from holo2.engine.session import SessionContext
from holo2.format.registry_rows import FormatRowSpec
from holo2.solve.plane import SessionPlane
from holo2.solve.close import VolumeClose
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.core.work import SilentStage, WorkResult
from conftest import registry

ROW = FormatRowSpec(
    row_id="c3-test@128x128", codec_id="k-v1", seed=b"holo/v1/test/128x128",
    tiles_yx=(2, 2), pitch_in=Fraction(1, 200),
    streams=(CloseStreamProfile("main", 8),))

RECIPE = Recipe("recipe-unit", (
    RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD),
    RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
))

ADDRESSES = ((0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1))


# ------------------------------------------------------------- scaffolding

def make_session(tmp_path: Path, name: str = "state",
                 **kwargs) -> SessionContext:
    """A captureless session: the engine's half plus an empty solve plane.

    The plane is the real one over no captures — the control loop under
    test reads work keys through it, and a stub would be a second
    implementation of the thing the spine already exercises.

    ``kwargs`` reach the store: ``snapshot_every`` is what a crash-cut
    fixture needs (``test_replay``), and a cadence is exactly the kind of
    thing a fixture should be able to state without a second builder.
    """
    from conftest import ground, make_session as make_identity

    identity = make_identity(RECIPE)
    store = Store.open_or_create(tmp_path / name, identity, registry(),
                                 fsync=False, **kwargs)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    # The fixture ground, once and idempotently: the certifying workers
    # below mint against ``POSE``, and since F-07's relational half a
    # certificate's witness has to be a fact. A resumed session lays the
    # same ground and commits nothing (see ``conftest.ground``).
    ground(engine, "pose")
    return SessionContext(store, engine, SessionPlane(store, engine, ROW, ()))


def make_orchestrator(session: SessionContext, recipe: Recipe, providers,
                      **kwargs) -> Orchestrator:
    """The wiring under test, written once (B12).

    The close is not on the provider roster any more: it is the terminal
    consumer the composition root hands the engine, so every test that
    schedules the close entry passes one here — a fresh ``VolumeClose``
    per run, because the engine records what IT consulted at, and a
    consumer that carried run state would hide that.
    """
    return Orchestrator(session, recipe, providers, close=VolumeClose(),
                        **kwargs)


def seed_addressed(session: SessionContext, addresses=ADDRESSES) -> None:
    session.apply(CommitBatch(writes=tuple(
        Write(tile_key(page, ty, tx, "main"),
              TileRecord(observed_by=("f:1/1",)))
        for page, ty, tx in addresses)))


ROUTE_CERTIFY = "unit-certify"


def work_id(key, route: str = ROUTE_CERTIFY) -> WorkId:
    """The descriptor name the ledger and the queue use (R1).

    A structure since the identity law: family, subject, route, scope.
    """
    return WorkId("payload", key, route)


class CertifyingWorker:
    """Mints a certificate for one work key, the way a payload worker does."""

    route = ROUTE_CERTIFY

    def __init__(self, key, *, bit: int = 1, quantum: int = 1) -> None:
        self.key = key
        self.worker_id = work_id(key, self.route)
        self._bit = bit
        self._quantum = quantum
        self.fires = 0

    def read_keys(self, view):
        return (self.key,)

    def run(self, view, identity, progress):
        self.fires += 1
        progress.emit(self._quantum, "decode")
        bits = stage_array(np.full(8, self._bit, np.uint8))
        return WorkResult(
            outcome="certified", retire=True, blobs=(bits,),
            writes=(Write(self.key, TileRecord(
                minting=MintRef(POSE, "scan", "fixture-decoder"),
                bits_ref=bits.ref, metadata_bit=self._bit,
                observed_by=("f:1/1",))),))


class SilentWorker(CertifyingWorker):
    """Fires and reports nothing — the defect §10.3 structurally excludes."""

    route = "unit-silent"

    def run(self, view, identity, progress):
        self.fires += 1
        return WorkResult(outcome="silent")


class HugeQuantumWorker(CertifyingWorker):
    route = "unit-huge"

    def run(self, view, identity, progress):
        self.fires += 1
        progress.emit(1 << 20, "one giant call")
        return WorkResult(outcome="huge")


class ChurningWorker(CertifyingWorker):
    """Rewrites a key it reads: a wake graph that cannot converge.

    Its seed gets strictly better-supported every fire, which is what
    keeps the write LAWFUL under R5's transition law while still moving
    the key's version — a churn the wall has no reason to stop.
    """

    route = "unit-churn"

    def run(self, view, identity, progress):
        self.fires += 1
        progress.emit(1, "churn")
        return WorkResult(outcome="churn", writes=(
            Write(lattice_seed_key(FOOTING, REGION),
                  make_seed(self.fires)),))

    def read_keys(self, view):
        return (self.key, lattice_seed_key(FOOTING, REGION))


class Factories:
    """A payload provider over the open work keys. The whole roster."""

    family = TASK_PAYLOAD
    sources = ("tile",)

    def __init__(self, worker_class=CertifyingWorker, **kwargs) -> None:
        self._class = worker_class
        self._kwargs = kwargs
        self._workers: dict = {}
        self.made: dict = {}
        self.provider_id = f"unit-{worker_class.route}"

    def expand(self, view, request):
        return tuple(
            WorkDescriptor(family=self.family, subject=key,
                           route=self._worker_for(key).route,
                           scope=WorkScope(arm=request.arm),
                           entry=request.entry)
            for key in view.open_work_keys())

    def worker(self, view, descriptor):
        worker = self._worker_for(descriptor.subject)
        self.made[worker.worker_id] = worker
        return worker

    def _worker_for(self, key):
        """One worker object per key, so fire counts survive a re-offer."""
        if key not in self._workers:
            self._workers[key] = self._make(key)
        return self._workers[key]

    def _make(self, key):
        return self._class(key, **self._kwargs)

    def __iter__(self):
        """A provider set of exactly one: the close is not a provider (B12)."""
        return iter((self,))


# ------------------------------------------------------------------ tests

def test_exhaustion_leaves_the_session_open_and_resumable(
        tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session)
        outcome = make_orchestrator(session, RECIPE, Factories()).run()
    assert outcome.status == "open"
    assert outcome.exhausted and not outcome.verified
    assert outcome.certified == 4
    assert outcome.fires == 4
    assert session.store.close_record() is None      # OPEN is not a record


def test_a_resumed_run_is_an_exact_no_op(tmp_path: Path) -> None:
    """Batching invariance at the session level (L10)."""
    with make_session(tmp_path) as session:
        seed_addressed(session)
        make_orchestrator(session, RECIPE, Factories()).run()
        envelope = session.store.state_bytes()
        seq = session.store.commit_seq
    with make_session(tmp_path) as resumed:
        outcome = make_orchestrator(resumed, RECIPE, Factories()).run()
        assert outcome.commits == 0 and outcome.fires == 0
        assert resumed.store.commit_seq == seq
        assert resumed.store.state_bytes() == envelope


def test_a_certified_key_is_never_enumerated_again(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = Factories()
        make_orchestrator(session, RECIPE, factories).run()
        second = Factories()
        make_orchestrator(session, RECIPE, second).run()
        assert second.made == {}                     # §6: only open keys arm


def test_workers_fire_in_a_deterministic_order(tmp_path: Path) -> None:
    order: list[str] = []

    class Recording(CertifyingWorker):
        route = "unit-order"

        def run(self, ctx, identity, progress):
            order.append(self.worker_id)
            return super().run(ctx, identity, progress)

    with make_session(tmp_path) as session:
        seed_addressed(session)
        make_orchestrator(session, RECIPE, Factories(Recording)).run()
    assert order == sorted(order)


def test_a_wake_re_arms_a_subscribed_worker(tmp_path: Path) -> None:
    """A commit that changes a read key produces a new identity (§7)."""
    key = tile_key(0, 0, 0, "main")
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        factories = Factories(ChurningWorker)
        recipe = Recipe("recipe-churn", (
            RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD,
                        PriceTable(max_fires_per_worker=4)),
            RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
        ))
        with pytest.raises(FireCountTripwire):
            make_orchestrator(session, recipe, factories).run()
        # The wake fired it again every time it changed its own read key;
        # the tripwire refuses the fire that would exceed the price.
        assert factories.made[work_id(key, ChurningWorker.route)].fires == 4


def test_a_re_attempt_pays_the_re_work_band_and_ages(tmp_path: Path) -> None:
    """H5 re-work aging, END TO END through the schedule (2026-08-19).

    The unit above proves a wake re-arms; this one proves what the wake
    now COSTS. One key, staged through fire -> spend -> re-arm four times
    (the churning worker's read key is one it rewrites, which is the
    cheapest honest way to make a real ledger row grow), and the price
    read off the queue AT FIRE TIME — the book ``Worklist.push`` orders
    by, not a recomputation beside it.

    The shape is the ruling's: the first attempt pays the entry price
    unchanged, and every attempt after it pays the band plus one step per
    prior attempt. It is read off the queue rather than off
    ``recipe.work_price`` on purpose — the arithmetic is pinned in
    ``test_cost_vocabulary``, and what could still go wrong here is the
    wiring: a price computed but never re-admitted, or re-admitted after
    the push that was supposed to carry it.
    """
    key = tile_key(0, 0, 0, "main")
    prices: list[int] = []

    class Aging(ChurningWorker):
        route = "unit-rework"
        queue: Worklist | None = None

        def run(self, view, identity, progress):
            assert Aging.queue is not None
            prices.append(Aging.queue.cost[self.worker_id])
            return super().run(view, identity, progress)

    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        factories = Factories(Aging)
        recipe = Recipe("recipe-rework", (
            RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD,
                        PriceTable(max_fires_per_worker=4)),
            RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY,
                        COST_PAYLOAD),
        ))
        run = make_orchestrator(session, recipe, factories)
        Aging.queue = run._queue
        with pytest.raises(FireCountTripwire):
            run.run()
        assert factories.made[work_id(key, Aging.route)].fires == 4
        # 20, then the band, then one step per prior attempt. The ledger
        # row is what carries the ordinal, so it is DURABLE: the same four
        # numbers whatever lane commits them.
        assert prices == [COST_PAYLOAD, REWORK_BASE,
                          REWORK_BASE + REWORK_STEP,
                          REWORK_BASE + 2 * REWORK_STEP]
        assert session.store.ledger.held(
            work_id(key, Aging.route), Aging.route).attempts == 4


def test_bumps_while_queued_coalesce_into_one_admission() -> None:
    """The property the band relies on: a queued worker is queued ONCE.

    Re-work aging prices an attempt by what it has already SPENT, so it
    is only coherent if a worker that has not fired cannot be queued into
    several attempts by several wakes. It cannot, and this is where that
    is enforced: ``push`` is idempotent while a worker is ready, so N
    bumps between two fires leave one heap entry and one pop. Re-pricing
    such a worker is a no-op by construction — its ordinal has not moved,
    because nothing has spent.

    (The provider-side half of the same property is
    ``frontier.offer``'s already-admitted skip, pinned by
    ``test_a_certified_key_is_never_enumerated_again`` and by the F-17
    re-offer skip: a total re-expansion mints no second descriptor for a
    work id the run already holds.)
    """
    queue = Worklist()
    worker = work_id(tile_key(0, 0, 0, "main"))
    queue.admit(worker, cost=COST_PAYLOAD, entry=0)
    for _bump in range(5):
        queue.push(worker)
    assert queue.pop() == worker
    assert queue.pop() is None, "five bumps admitted five attempts"


def test_a_silent_stage_is_a_failure_not_a_lesson(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        with pytest.raises(SilentStage, match="without reporting"):
            make_orchestrator(session, RECIPE, Factories(SilentWorker)).run()


def test_an_unbounded_work_quantum_is_a_failure(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        with pytest.raises(SilentStage, match="exceeds"):
            make_orchestrator(session, RECIPE, Factories(HugeQuantumWorker)).run()


def _open_a_second_key(session: SessionContext) -> None:
    """Certify one tile, then leave a DIFFERENT work key open to arm on."""
    seed_addressed(session, addresses=((0, 0, 0),))
    make_orchestrator(session, RECIPE, Factories(bit=1)).run()
    session.apply(CommitBatch(writes=(
        Write(tile_key(0, 0, 1, "main"),
              TileRecord()),)))


def test_a_certificate_conflict_ends_the_run_as_a_durable_fact(
        tmp_path: Path) -> None:
    """F-11: the contradiction is DATA, so the run RECORDS it and stops.

    A ~2^-32 CRC false accept and a scissors session that mixed two
    physical sheets are both things LAWFUL code produces, so a
    contradicted certificate may not be a traceback: it is one lawful
    terminal write, and the run ends reporting the record it just made
    (never voted, never advisory).
    """
    with make_session(tmp_path) as session:
        _open_a_second_key(session)
        outcome = make_orchestrator(session, RECIPE, Rogue()).run()
        assert outcome.status == "integrity_failure"
        assert not outcome.resumed_terminal and not outcome.exhausted
        assert "certified content may not change" in (outcome.reason or "")
        assert str(tile_key(0, 0, 0, "main")) in (outcome.reason or "")
        # The operator hears about it through the close dict the snapshot
        # already publishes — no second channel was invented for this.
        assert (outcome.close or {})["status"] == "integrity_failure"
        assert (outcome.close or {})["reason"] == outcome.reason
        record = session.close_record()
        assert isinstance(record, CloseRecord)
        assert record.status is CloseStatus.INTEGRITY_FAILURE
        assert record.reason == outcome.reason
        assert session.terminal


def test_the_integrity_fact_survives_the_session_and_freezes_it(
        tmp_path: Path) -> None:
    """Resume needed no new code: a terminal CloseRecord IS the freeze."""
    with make_session(tmp_path) as session:
        _open_a_second_key(session)
        reason = make_orchestrator(session, RECIPE, Rogue()).run().reason
    with make_session(tmp_path) as resumed:          # the same state directory
        record = resumed.close_record()
        assert isinstance(record, CloseRecord)
        assert record.status is CloseStatus.INTEGRITY_FAILURE
        assert record.reason == reason
        seq = resumed.store.commit_seq
        outcome = make_orchestrator(resumed, RECIPE, Factories()).run()
        assert outcome.resumed_terminal
        assert outcome.status == "integrity_failure"
        assert outcome.commits == 0 and resumed.store.commit_seq == seq


def test_a_state_regression_still_propagates_fatally(tmp_path: Path) -> None:
    """The discriminating half: ONE refusal is data, every other is a bug.

    A monotone fact walking backwards is a defect in the writer (F-08),
    so it keeps killing the run loudly — and it records nothing, because
    there is no integrity fact about the DATA to record. The fixture
    walks a RETIRED window back to ACTIVE, which is the monotone law
    that survived tile family v4 (a tile's mint is immutable, and a
    write that drops it is the certificate conflict above, not this).
    """
    with make_session(tmp_path) as session:
        _open_a_second_key(session)
        session.apply(CommitBatch(writes=(Write(WINDOW, make_window(
            WindowStatus.RETIRED, retired_reason="unit")),)))
        with pytest.raises(StateRegression):
            make_orchestrator(session, RECIPE, Regressing()).run()
        assert session.close_record() is None and not session.terminal


class Rogue(Factories):
    """A worker that contradicts a standing certificate."""

    def _make(self, key):
        return Contradicting(key)


class Regressing(Factories):
    """A worker that walks a standing certificate backwards."""

    def _make(self, key):
        return Regressive(key)


class Regressive(CertifyingWorker):
    route = "unit-regress"

    def run(self, view, identity, progress):
        progress.emit(1, "regress")
        return WorkResult(outcome="rogue", writes=(
            Write(WINDOW, make_window(WindowStatus.ACTIVE)),))


class Contradicting(CertifyingWorker):
    route = "unit-rogue"

    def run(self, view, identity, progress):
        progress.emit(1, "contradict")
        bits = stage_array(np.zeros(8, np.uint8))
        return WorkResult(outcome="rogue", blobs=(bits,), writes=(
            Write(tile_key(0, 0, 0, "main"), TileRecord(
                minting=MintRef(POSE, "scan", "fixture-decoder"),
                bits_ref=bits.ref,
                metadata_bit=0, observed_by=("f:1/1",))),))


def test_a_terminal_session_runs_nothing(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        session.apply(CommitBatch(writes=(Write(CLOSE_KEY, CloseRecord(
            CloseStatus.INTEGRITY_FAILURE, reason="mixed sheets")),)))
        seq = session.store.commit_seq
        outcome = make_orchestrator(session, RECIPE, Factories()).run()
        assert outcome.resumed_terminal and outcome.status == "integrity_failure"
        assert outcome.commits == 0
        assert session.store.commit_seq == seq


def test_a_consult_costs_neither_a_work_id_nor_a_commit(
        tmp_path: Path) -> None:
    """The close leaves no scheduler trace at all (B12).

    It used to bind a descriptor into the queue's own structures — a work
    id in the ledger, an ``_inflight`` entry, a spend row per look, and
    therefore a commit sequence number per look, even for a consult that
    decided nothing. None of that is scheduling, and none of it is left:
    the four fires below are the payload workers', the certified tiles
    are theirs, and the consults are counted under their own name.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        orchestrator = make_orchestrator(session, RECIPE, Factories())
        orchestrator.run()
        snapshot = orchestrator.snapshot()
        assert not [worker for worker in snapshot.workers.fires_by_worker
                    if "close" in worker]
        assert snapshot.workers.total == 4          # the payload workers only
        assert snapshot.counters.consults          # it WAS consulted
        assert not [row for row in session.store.ledger.entries()
                    if row.worker_id.family == TASK_CLOSE]


def test_an_unchanged_frontier_is_consulted_once(tmp_path: Path) -> None:
    """CONSULT IDEMPOTENCE, kept engine-side (B12, ruled 2026-08-12).

    Two consult OPPORTUNITIES — the commit this worker makes, and the
    exhaustion consult after it — with nothing certified in between, so
    the close's input (the certified frontier's version) is the same
    integer at both. Exactly one consult happens. This is the property
    the durable spend row used to buy, and it is now one compare against
    the version the engine recorded.
    """

    class SeedWriter(CertifyingWorker):
        route = "unit-seed"

        def run(self, view, identity, progress):
            self.fires += 1
            progress.emit(1, "seed")
            return WorkResult(outcome="seeded", retire=True, writes=(
                Write(lattice_seed_key(FOOTING, REGION), make_seed()),))

    with make_session(tmp_path) as session:
        seed_addressed(session, addresses=((0, 0, 0),))
        orchestrator = make_orchestrator(session, RECIPE, Factories(SeedWriter))
        orchestrator.run()
    counters = orchestrator.snapshot().counters
    assert counters.fires == 1, "the fixture must commit exactly once"
    assert counters.consults == 1


def test_a_consult_that_decides_nothing_still_reports_its_counting(
        tmp_path: Path) -> None:
    """The observer sees K derivation even before count-ready (B12 residue).

    The first live run after the terminal-consumer reshape showed 700+
    certificates beside "K unknown": the not-ready consult returned an
    empty verdict, and the display keeps only non-empty reports. K
    derivation runs on EVERY consult — the count gate cannot count
    without it — so a deciding-nothing verdict still carries the
    counting report: status open, the metadata rank, K when the word has
    solved, and the certificate count.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        verdict = VolumeClose().consult(session.view(), mode="close")
        assert verdict.writes == () and verdict.blobs == ()
        report = verdict.report
        assert report, "a consult that decides nothing still knows things"
        assert report["status"] == "open" and report["reason"] == "counting"
        assert report["certified"] == 0 and report["k_total"] is None
        assert report["metadata_rank"] == 0


def test_complete_observes_mid_run_and_defers_the_close(
        tmp_path: Path) -> None:
    """``--complete`` suppresses the DECISION, not the OBSERVATION.

    The guard used to skip the mid-run consult entirely (user ruling
    2026-08-13 ended that): the operator watched certificates pile up
    beside "K unknown" for a whole deferred-close run. The mid-run
    consult now runs in ``observe`` — it counts and reports and never
    closes — and the one DECIDING consult is still the deferred final
    one, counted under the name every HEALTH row measured.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        orchestrator = make_orchestrator(session, RECIPE, Factories(),
                                         complete=True)
        outcome = orchestrator.run()
    counters = orchestrator.snapshot().counters
    assert counters.observations == 4     # one per certificate commit
    assert counters.consults == 1         # the deferred final consult
    assert outcome.status == "open"       # 4 equations cannot reach rank 24
    assert outcome.close["certified"] == 4


def test_observe_mode_never_calls_the_carried_close(
        tmp_path: Path, monkeypatch) -> None:
    """``observe`` may not decide, structurally: ``close_volume`` is not
    reached — where ``final`` on the same state is (the discriminating
    half, proving the patch bites)."""
    import holo2.solve.close as close_module

    def refuse(*_args, **_kwargs):
        raise AssertionError("observe consulted the carried close")

    with make_session(tmp_path) as session:
        seed_addressed(session)
        make_orchestrator(session, RECIPE, Factories()).run()  # 4 certs
        monkeypatch.setattr(close_module, "close_volume", refuse)
        consumer = VolumeClose()
        report = consumer.consult(session.view(), mode="observe").report
        assert report["reason"] == "counting" and report["certified"] == 4
        with pytest.raises(AssertionError, match="observe consulted"):
            consumer.consult(session.view(), mode="final")


def test_counting_consults_read_no_symbol_blobs(
        tmp_path: Path, monkeypatch) -> None:
    """P3-1: the gate consumes tile records, never payload blobs.

    Before the incremental state, every consult materialised every
    certified symbol — O(certified) blob reads for a count the records
    already carry. A ``close``-mode consult below the gate now touches
    zero blobs; ``final`` on the same state still reads them (the
    discriminating half, proving the patch bites).
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        make_orchestrator(session, RECIPE, Factories()).run()  # 4 certs
        monkeypatch.setattr(
            type(session.plane), "read_array",
            lambda self, ref: (_ for _ in ()).throw(
                AssertionError("the count gate read a symbol blob")))
        consumer = VolumeClose()
        report = consumer.consult(session.view(), mode="close").report
        assert report["reason"] == "counting" and report["certified"] == 4
        with pytest.raises(AssertionError, match="read a symbol blob"):
            consumer.consult(session.view(), mode="final")


def test_an_unknown_consult_mode_is_refused(tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        with pytest.raises(ValueError, match="unknown consult mode"):
            VolumeClose().consult(session.view(), mode="when-convenient")


# DELETED 2026-08-17 with the quiescent gate (pricing ruling):
# ``test_quiescence_counts_ready_and_in_flight_work`` and
# ``test_work_that_does_not_quiesce_is_projected_out_of_the_gate`` both
# drove ``_cheaper_in_play`` directly, and both are about a gate that no
# longer exists. F-22.1's live half — READY and IN FLIGHT both count —
# is now asserted where the surviving instantaneous-dryness test lives,
# ``test_pool.py``'s gated-tier pins over ``head_cost``/``inflight``.


def test_the_status_snapshot_is_fed_by_the_run(tmp_path: Path) -> None:
    provider = diag.StatusProvider()
    # What ingest commits before the queue exists: parked here, and
    # replayed into the run's ledger the moment it takes over.
    provider.note_commit(CommitResult(commit_seq=0, batch_id="ingest",
                                      changed_keys=(), wakes=()))
    with make_session(tmp_path) as session:
        seed_addressed(session)
        make_orchestrator(session, RECIPE, Factories(), status=provider).run()
        commit_seq = session.store.commit_seq
    status = provider.status()
    stream = status["commit_stream"]
    session_view = status["session"]
    assert session_view["workers"]["total"] == 4
    assert session_view["workers"]["retired"] == 4
    assert session_view["tiles"]["CERTIFIED"] == 4
    assert session_view["counters"]["fires"] == 4
    assert session_view["close"]["status"] in ("not_consulted", "open")
    # ONE OWNER: the run's own commits are the stream's scheduled subset,
    # and the seeding commit this test made outside the run is the only
    # difference between that subset and the session total. Two numbers
    # that used to be two tallies of one word (472 vs 471 on the bench).
    scheduled = session_view["counters"]["commits"]
    assert scheduled > 0
    assert stream["scheduled_commits"] == scheduled
    assert stream["commits"] == scheduled + 1      # + the parked one
    # The two commits this test made OUTSIDE the run are the fixture
    # ground (the pose the mints name) and the addressed seed.
    assert scheduled == commit_seq - 2             # the seed was not the run's
    assert session_view["counters"]["wakes"] == stream["scheduled_wakes"]


def test_a_snapshot_the_run_cannot_mint_does_not_reach_the_run(
        tmp_path: Path, monkeypatch) -> None:
    """L12 in the push direction: an observer failure is text, not a raise."""
    provider = diag.StatusProvider()
    with make_session(tmp_path) as session:
        seed_addressed(session)
        monkeypatch.setattr(
            type(session.plane), "observer_summary",
            lambda self: (_ for _ in ()).throw(RuntimeError("plane exploded")))
        outcome = make_orchestrator(session, RECIPE, Factories(),
                               status=provider).run()
    assert outcome.certified == 4, "the observer cost the run a certificate"
    status = provider.status()
    assert "session" not in status
    assert status["session_error"] == "RuntimeError: plane exploded"


def test_an_unwatched_run_mints_no_snapshot_per_commit(tmp_path: Path) -> None:
    """The wanted flag is the throttle: no viewer, no derivation.

    Two instants only — the one the run publishes when it adopts the
    observer, and the terminal one — no matter how many commits it makes.
    """
    provider = diag.StatusProvider()
    minted: list[int] = []
    with make_session(tmp_path) as session:
        seed_addressed(session)
        orchestrator = make_orchestrator(session, RECIPE, Factories(),
                                    status=provider)
        snapshot = orchestrator.snapshot
        orchestrator.snapshot = lambda: (minted.append(1), snapshot())[1]
        outcome = orchestrator.run()
    assert outcome.fires == 4                       # the run did work
    assert len(minted) == 1                         # + the one at __init__

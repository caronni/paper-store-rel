"""Orchestrator v0: two work sources, the fixpoint, and close preemption.

DESIGN §9 with the §7 mechanism underneath. Everything that could have
been control flow is a fact instead: *what may run* is enumeration over
the recipe's entries (a refusal is a decline naming the keys that would
change its mind, or permanent); *what will run* is the ready set,
refilled by commit wakes through the ordinary resource table (M4);
*what may not run again* is the spend-once test, the read-set bound to
its versions BEING the attempt identity, so idleness is an integer
compare and not a policy; *when to stop* is a verified close, which
preempts everything, or quiescence of every source across every entry —
an honest, resumable OPEN state, never a failure.

**TWO SOURCES SINCE H4 W2** (the pull model). The descriptor path above
is unchanged and serves payload and the close; placement arrives from a
``core.WorkSource`` instead — an in-memory set of windows, each with a
ready flag, priced per tier by the source (``solve.place_sched``) — and
the two interleave by ONE global cost: the cheaper head is admitted (a
tie goes to the queue, deterministically), and a job the source marks
GATED waits until nothing cheaper is ready or in flight ANYWHERE
(Q3+Q6: the dear tiers must not preempt pending payload, whose
certificates delete placement work). A source job takes no identity and
mints no spend row, because it subscribes to nothing: repetition is
bounded by its own flag and tried set, so there is no staleness test for
it and a failed pass leaves nothing durable. What replaces the
subscription is the PING, whose ordering IS the correctness argument:
this loop COMMITS, then settles the source, which is where it pings
(:meth:`_commit`).

The pool (§10.1) admits CONTINUOUSLY (R9, ruled 2026-08-15): up to
``--workers`` fires are in flight, whichever finishes first is admitted
at the wall immediately, and the freed slot is refilled by take-and-arm.
Two properties stay structural — the concurrent phase writes nothing,
and staleness is waste rather than error (a proposal commits only if its
read-set RE-DERIVED still binds the identity it holds, which is what
makes out-of-order completion safe by construction). One is deliberately
given up: commit order is COMPLETION order, so a live parallel run is no
longer a deterministic function of the state it started from. The oracle
moved lanes rather than dying — ``--workers 1`` builds no pool and stays
exactly deterministic, and every run replays exactly from its journal.
Replay (§10.3) follows a recorded ordering instead of the live queue —
the audit AND, since F-16, crash recovery: a run whose journal is ahead
of its cache re-earns that tail first, then runs live.

**The memory model, stated once** (W-S, 2026-08-15). Commits are
main-thread-only (L11) and each fire pins ONE generation of the plane's
derived views, so the only state a pool thread reads live is the store's
own record / version / blob tables. Three facts make that safe together:
records are immutable values, the tables are plain dicts whose lookups
are atomic under the GIL (a reader sees the old value or the new one,
never a half-built one), and §7 RE-DERIVES the identity at admission. A
fire that read newer-than-pinned state therefore yields, at worst, a
proposal whose identity no longer binds — a counted discard, never
corruption. A mutable record would break it; the wall refuses one.

Choices where DESIGN is silent, argued in ``engine/DESIGN.md``: the close
consult is orchestrator-timed, not queue-scheduled; a terminal answer is
read off the store, not off the consumer; re-enumeration is total after
any structural commit; the fire-count tripwire raises and is charged at
arm time; arming and admission are main-thread-only; and a certificate
conflict — alone among commit refusals — ends the run as a durable
terminal fact rather than a traceback (F-11,
:meth:`Orchestrator._integrity_failure`).
"""
from __future__ import annotations

from concurrent.futures import (FIRST_COMPLETED, Future, ThreadPoolExecutor,
                                wait)
from typing import Any, Iterable, Sequence

from ..core import (CLOSE_KEY, CertificateConflict, CloseRecord, CloseStatus,
                    CommitBatch, CommitResult, LeaseBook, ProgressSink,
                    Provider, ReplayCursor, ReplayError, ResourceKey,
                    SpendProposal, Subscription, WorkDescriptor, WorkId,
                    Worker, WorkScope, WorkSource, Write, check_progress,
                    providers_by_family)
from . import frontier, observe, replay
from .consult import (CONSULT_CLOSE, CONSULT_FINAL, CONSULT_OBSERVE,
                      ROUTE_PULL, CloseConsult, CloseVerdict,
                      FireCountTripwire, NoProviderError, RunObserver,
                      RunOutcome)
from .recipe import GATE_COUNT_READY, GATE_EXHAUSTION, Recipe, work_price
from .session import SessionContext
from .snapshot import CommitLedger, RunSnapshot, WorkLedger
from .worklist import Armed, Proposal, Worklist


class Orchestrator:
    """The §9 control loop over one session."""

    def __init__(self, ctx: SessionContext, recipe: Recipe,
                 providers: Iterable[Provider], *, close: CloseConsult,
                 source: WorkSource | None = None,
                 complete: bool = False, no_close: bool = False,
                 status: RunObserver | None = None, workers: int = 1,
                 replay: Sequence[str] | None = None) -> None:
        if workers < 1:
            raise ValueError("a pool has at least one worker")
        self._ctx = ctx
        self._view = ctx.view()
        self._recipe = recipe
        # The queue-scheduled entries, in priority order: a filtered tuple
        # the arm step reads once per armed worker.
        self._work_entries = recipe.work_entries()
        self._providers = tuple(providers)
        self._by_family = providers_by_family(self._providers)
        # The second work source (H4 W2). One today — placement — and the
        # family it serves is its own declaration, not a parameter here.
        self._source = source
        self._close = close
        # The frontier version each gate last consulted at (B12), IN-RUN:
        # a run that resumes a session asks the inherited frontier once,
        # which is honest for a consult whose input may have grown
        # outside this lineage's ledger.
        self._consulted: dict[str, int] = {}
        self._complete = complete
        #: `--no-close` (user ruling 2026-08-22): this run never enters a
        #: DECIDING consult mode, so no closing record is read, attempted
        #: or written and the session ends OPEN with its certificates
        #: accumulated. ``observe`` stays alive deliberately — holo2 ruled
        #: on 2026-08-13 that suppressing the OBSERVATION along with the
        #: decision is a defect, so K, the metadata rank and the per-block
        #: counts stay live on the status view. It implies the deferral
        #: (a greedy per-barrier close attempt would contradict
        #: never-close), which is what makes ``--complete`` alongside
        #: legal and redundant. What it forfeits is close preemption, the
        #: biggest scheduling win there is (3.7x) — by construction, and
        #: the flag's help text says so.
        self._no_close = no_close
        self._status = status
        self._pool_size = int(workers)
        self._replay = None if replay is None else ReplayCursor(replay)
        self._workers: dict[WorkId, tuple[WorkDescriptor, Worker]] = {}
        #: The descriptor queue: ready set, cost heap, in-flight book
        #: (``engine/worklist.py``, split out when the second source
        #: arrived).
        self._queue = Worklist()
        # A permanent decline never comes back; a re-offerable one sleeps
        # on the keys it named and is re-minted when one of them moves.
        self._declined: dict[WorkId, str] = {}
        self._pending: dict[WorkId, str] = {}
        #: Per ``(entry, provider)``, the descriptor OBJECTS of the last
        #: expansion whose disposition is already final, by identity:
        #: the re-offer skip (``engine.frontier.offer_expansion``).
        self._offered: dict[tuple[int, str], dict[int, WorkDescriptor]] = {}
        self._leases = LeaseBook()
        #: Source jobs in flight, by subject and cost: the source's half
        #: of "how much cheaper work is still in play" (:meth:`_next`).
        self._source_inflight: dict[ResourceKey, int] = {}
        #: Passes whose START MARKER this run wrote (H4 W2). A replay
        #: re-running a dispatch whose marker already stands writes none,
        #: so "which fires the store is still waiting on" is a set of
        #: names rather than a count anybody could double-decrement.
        self._marked: set[WorkId] = set()
        # The two ledgers of L12: one owns every commit of this session
        # (ingest's included), the other owns what the queue did. Nothing
        # else counts either quantity.
        self._commits = CommitLedger()
        self._work = WorkLedger()
        self._last_close: dict[str, Any] | None = None
        self._running: tuple[WorkId, ...] = ()
        self._require_providers()
        if status is not None:
            # PUSH, not pull: the observer is handed the commit ledger and
            # the first instant here, and a fresh instant at every commit
            # it asked for. It never calls back into a running scheduler.
            status.adopt_ledger(self._commits)
            self._publish()

    def _require_providers(self) -> None:
        """Every QUEUED recipe entry must have a SOURCE behind it.

        Loud, not silent — and the close entry is not in this test: it
        names no provider family, because it is the terminal consumer
        this orchestrator was handed (B12), carrying timing policy only.
        Since H4 W2 "a source" is a provider family OR the work source,
        which is how ``place`` entries stay legal with no provider bound.
        """
        served = set(self._by_family)
        if self._source is not None:
            served.add(self._source.family)
        missing = sorted({entry.task_class for entry in self._work_entries
                          if entry.task_class not in served})
        if missing:
            raise NoProviderError(
                f"recipe {self._recipe.label} schedules {missing} but no "
                "provider or work source serves those families")

    # -- the run -----------------------------------------------------------

    def run(self) -> RunOutcome:
        """One session run, and the terminal instant the observer keeps.

        The final publish is in a ``finally`` because it is the only one
        an operator is guaranteed to see: the artifacts written after the
        run (and the six rows the CLI prints) are read off the last
        instant.
        """
        try:
            return self._run()
        finally:
            self._publish()

    def _run(self) -> RunOutcome:
        """Dispatch the run, and catch the ONE lawful integrity event.

        ``CertificateConflict`` and nothing else (F-11): every other
        ``CommitRefusal`` is a writer defect and stays fatal. The catch
        sits here because the paths below ARE one commit site — all of
        them commit on this thread (L11).
        """
        if self._ctx.terminal:
            return self._terminal_outcome()
        self._refresh()
        try:
            if self._replay is not None:
                return self._run_replay()
            recovered = self._recover()      # a crash tail is re-earned first
            if recovered is not None:
                return recovered
            return (self._run_pool() if self._pool_size > 1
                    else self._run_serial())
        except CertificateConflict as conflict:
            return self._integrity_failure(conflict)

    def _run_serial(self) -> RunOutcome:
        """One worker at a time: arm, propose and commit, with no pool."""
        while True:
            armed = self._pop_armed()
            if armed is None:
                break
            self._dispatch(armed)
            self._running = (armed.worker_id,)
            try:
                proposal = self._propose(armed)
            finally:
                self._running = ()
            outcome = self._apply(proposal)
            if outcome is not None:
                return outcome
        return self._exhausted()

    # -- the pool (§10.1) --------------------------------------------------

    def _run_pool(self) -> RunOutcome:
        """Continuous admission: keep the slots full, commit at completion.

        No round, no barrier, and no clock: fill every free slot by
        take-and-arm, block until SOMETHING finishes, admit it, fill
        again. A run ends where the serial one does — the queue dry,
        nothing in flight, one re-enumeration that mints nothing.
        """
        inflight: dict[Future[Proposal], Armed] = {}
        with ThreadPoolExecutor(max_workers=self._pool_size,
                                thread_name_prefix="holo2-propose") as pool:
            while True:
                self._fill(pool, inflight)
                if not inflight:
                    self._refresh()
                    self._fill(pool, inflight)
                    if not inflight:
                        break
                outcome = self._admit_completed(inflight)
                if outcome is not None:
                    self._cancel(pool, inflight)
                    return outcome
        return self._exhausted()

    def _fill(self, pool: ThreadPoolExecutor,
              inflight: dict[Future[Proposal], Armed]) -> None:
        """Pop-and-arm into every free slot: the whole scheduling act.

        It takes raw: a refill may not re-enumerate in the middle of
        itself (the drain path above owns that, once), and it is bounded
        by ``--workers``, so a deep queue cannot starve the wall.
        """
        while len(inflight) < self._pool_size:
            kind = self._next()
            if kind is None:
                break
            armed = self._take(kind)
            if armed is None:
                continue
            self._dispatch(armed)
            inflight[pool.submit(self._propose, armed)] = armed
        self._work.peak_inflight = max(self._work.peak_inflight, len(inflight))
        self._running = tuple(item.worker_id for item in inflight.values())

    def _admit_completed(self, inflight: dict[Future[Proposal], Armed],
                         ) -> RunOutcome | None:
        """Commit what finished, at the one wall, in completion order.

        The identity is re-derived HERE, which is the whole reason
        admitting out of arm order is safe (§7): a proposal is checked
        against what it would take NOW, not its dispatch order.
        """
        for future in wait(tuple(inflight), return_when=FIRST_COMPLETED).done:
            armed = inflight.pop(future)
            self._running = tuple(item.worker_id for item in inflight.values())
            proposal = future.result()
            if not self._is_current(armed):
                # Its frontier moved while it was in flight: the identity
                # it holds is not the identity it would spend. Waste, never
                # error — the worker re-arms against what is true now.
                self._work.stale_discards += 1
                self._disarm(armed)
                if armed.source is None:
                    self._queue.push(armed.worker_id)
                continue
            outcome = self._apply(proposal)
            if outcome is not None:
                return outcome
        return None

    def _cancel(self, pool: ThreadPoolExecutor,
                inflight: dict[Future[Proposal], Armed]) -> None:
        """A terminal outcome preempts everything (§9), fires included.

        F-22.4's other half. Close preemption is the biggest scheduling
        win there is (3.7x) and admitting stragglers would spend it back,
        so a queued fire is cancelled, a started one finishes unread.
        Counted: waste a run CHOSE is waste it should report.
        """
        pool.shutdown(wait=True, cancel_futures=True)
        self._work.cancelled += len(inflight)
        for armed in inflight.values():
            self._disarm(armed)
        inflight.clear()
        self._running = ()

    def _is_current(self, armed: Armed) -> bool:
        """§7: is the identity this proposal holds the one it would take now?

        Re-DERIVED, not merely re-checked: a read-set is a query, so a
        commit can add a key the worker would now read without touching
        any key it named. One compare catches both drifts.

        A SOURCE job takes the same test over the much smaller read-set
        it binds at :meth:`_arm_job` — binding it is not optional, since
        the identity of nothing can never match this re-derivation. Its
        other race — a window whose area finishes mid-pass — needs no
        test at all: the evidence merges into tiles already certified.

        WHAT THE TEST NO LONGER ASKS (H4 W2's merge ruling) is whether a
        key the wall JOINS has moved: the commit layer owns that
        projection, because it owns the registry that knows which
        families declared a merge (``CommitEngine.is_current``).
        """
        keys = armed.worker.read_keys(self._view)
        return self._ctx.engine.is_current(keys, armed.identity)

    # -- replay and recovery (§10.3, F-16, H4 W2 markers) ------------------
    # The bodies live in ``engine/replay.py`` (the file-cap seam, taken
    # where the tree already cuts): following a RECORDED ordering is a
    # subsystem of its own, with its own vocabulary — markers, held
    # proposals, stranded dispatches — and nothing in the live control
    # loop below reads any of it. ENUMERATION took the same seam with the
    # streaming-ingestion build (``engine/frontier.py``): expansion,
    # minting, declining and the re-offer skip are one subsystem, and
    # what stays here is the loop that asks for it.

    def _run_replay(self) -> RunOutcome:
        """The ``--replay`` audit: follow a recorded ordering, whole."""
        return replay.audit(self)

    def _recover(self) -> RunOutcome | None:
        """Re-earn the journal tail the cache does not cover, then run live."""
        return replay.recover(self)

    # -- admission: two sources, one cost order ----------------------------

    def _next(self) -> str | None:
        """WHICH source the cheapest admissible work is in — or None.

        The whole of the global order (H4 W2). The two heads are compared
        by cost and the cheaper wins, a tie going to the queue so the
        choice is a function of state and not of iteration order. The one
        extra rule is the gated tier's: a job the source marks GATED may
        not start while anything cheaper is READY OR IN FLIGHT — an
        expensive placement pass must not begin while a payload fire that
        could delete its window is still running.
        """
        queue_cost = self._queue.head_cost()
        job = None if self._source is None else self._source.peek()
        if job is None:
            return None if queue_cost is None else "queue"
        if queue_cost is not None and queue_cost <= job.cost:
            return "queue"
        if job.gated:
            in_play = list(self._queue.inflight.values())
            in_play.extend(self._source_inflight.values())
            if queue_cost is not None:
                in_play.append(queue_cost)
            if in_play and min(in_play) < job.cost:
                return None
        return "source"

    def _pop_armed(self) -> Armed | None:
        """The next admissible item, armed — from either source.

        Serial and replay both want "take until one arms, or everything
        is dry"; the pool's ``_fill`` is deliberately NOT this (see
        there). The re-enumeration on a drained queue is here because a
        drained queue is when a GATED tier becomes admissible — nothing
        cheaper is ready or in flight, which is the one moment a source
        job the last ``_next`` refused can start.
        """
        while True:
            kind = self._next()
            if kind is None:
                self._refresh()
                kind = self._next()
                if kind is None:
                    return None
            armed = self._take(kind)
            if armed is not None:
                return armed

    def _take(self, kind: str) -> Armed | None:
        """Claim one item from the source ``_next`` chose."""
        if kind == "queue":
            worker_id = self._queue.pop()
            return None if worker_id is None else self._arm(worker_id)
        return self._arm_job()

    def _arm_job(self, subject: ResourceKey | None = None) -> Armed | None:
        """Claim a source job — the HEAD, or the subject a marker names.

        Test-and-clear, then bind. No spend-once test and no subscription
        — the source owns "may this run again?" (its flag and its tried
        set), so the ledger holds nothing. The identity IS taken (main
        thread, exactly as :meth:`_bind` takes it) over the one key the
        job may write and the wall may refuse (R5's seed,
        ``place_job.read_keys``): what it buys is the ordinary stale
        discard instead of a fatal ``CommitRefusal``. The descriptor is
        synthesised for the machinery that needs a name (the fire
        counter, the observer's rows, the progress sink); its route says
        how the work was admitted, the honest answer now that a route is
        no longer an identity.

        ``subject`` is replay's (H4 W2): a recorded dispatch names the
        window it launched, and the source's ready ORDER at that instant
        was a live-schedule artifact that no replay should have to
        reproduce. ``WorkSource.job`` answers for a named subject exactly
        as ``peek`` answers for the head, consuming nothing either way.
        """
        source = self._source
        assert source is not None
        job = source.peek() if subject is None else source.job(subject)
        if job is None:
            return None
        worker = source.claim(self._view, job.subject)
        if worker is None:
            return None
        # M5 RESIDENCY ON THE SOURCE PATH TOO (W4). A descriptor declares
        # its leases when it is minted; a source job has no descriptor
        # until this line synthesises one, so the WORKER is the only party
        # that can say what this pass will hold — and it is asked for it
        # here, exactly where the descriptor's other fields are filled in.
        # The book, the take/release pairing and the published residency
        # are all unchanged: what was missing was a way for the pull
        # model's half of the engine to declare anything at all, so every
        # source fire took an empty tuple. Workers that hold nothing still
        # do — ``leases`` is protocol-typed now (W5, ``LeasedWorker``),
        # never ``getattr``-guessed: ``WorkSource.claim`` returns a
        # ``LeasedWorker``, so a worker that misspells the attribute fails
        # ``mypy --strict`` at the perimeter instead of silently declaring
        # nothing. Cold is the first thing on either path whose residency
        # is worth reading.
        descriptor = WorkDescriptor(
            family=source.family, subject=job.subject, route=ROUTE_PULL,
            scope=WorkScope(), entry=self._work_entries[job.entry].label,
            leases=worker.leases)
        keys = worker.read_keys(self._view)
        armed = Armed(descriptor, worker, keys,
                      self._ctx.engine.attempt_identity(keys),
                      job.entry, job.cost, source)
        self._charge(armed)
        self._source_inflight[job.subject] = job.cost
        self._leases.take(descriptor.leases)
        return armed

    # -- enumeration -------------------------------------------------------

    def _refresh(self) -> None:
        """Expand the frontier (``engine/frontier.py``): mint, decline, skip.

        The body moved out with the streaming-ingestion build along the
        seam the tree already cuts — the queue, the recorded ordering and
        the published instant each
        have their own module — and it stays a method because it is
        called from four places in this loop and from the recovery path.
        """
        frontier.refresh(self)

    # DELETED 2026-08-17 with the quiescent gate (pricing ruling):
    # ``_cheaper_in_play`` asked "is anything strictly cheaper still
    # ready, armed or running", and its one caller was that gate's
    # enumeration skip. The gated-TIER rule in :meth:`_next` keeps the
    # same question in its own words and over its own two books — it is
    # the surviving instantaneous-dryness test, and it is unchanged.

    # -- firing ------------------------------------------------------------

    def _arm(self, worker_id: WorkId) -> Armed | None:
        """Bind one queued worker and charge its price.

        The price is charged after the idle test and before dispatch, so a
        pool cannot outrun the tripwire (§7).
        """
        descriptor, worker = self._workers[worker_id]
        entry_index = self._queue.entry[worker_id]
        armed = self._bind(descriptor, worker, entry_index)
        if armed is None:
            return None
        self._charge(armed)
        return armed

    def _charge(self, armed: Armed) -> None:
        """Count this fire against its entry's price (choice 4).

        Both sources are charged the same way and at the same moment —
        after the idle test, before dispatch — so a pull job that keeps
        re-arming raises the same tripwire a churning descriptor would,
        per WINDOW, which is the quantity a non-converging ping graph
        would run away in.
        """
        # The counters are the OBSERVER's, so they key on the rendered
        # id: a display collision costs a tally line, never a spend.
        rendered = str(armed.worker_id)
        fires = self._work.fires_by_worker.get(rendered, 0) + 1
        price = self._work_entries[
            armed.entry_index].prices.max_fires_per_worker
        if fires > price:
            raise FireCountTripwire(
                f"{armed.worker_id}: {fires} fires exceeds the recipe price "
                f"{price} — the wake graph is not converging (§7)")
        self._work.fires_by_worker[rendered] = fires

    def _bind(self, descriptor: WorkDescriptor, worker: Worker,
              entry_index: int) -> Armed | None:
        """Read the keys, take the identity, apply spend-once.

        Main thread only: the identity must be taken against one frozen
        version map, or the staleness test the wall commits on means
        nothing. Arming also takes the descriptor's leases and counts the
        worker as in flight — both released by :meth:`_disarm`.
        """
        ctx = self._ctx
        work_id = descriptor.work_id
        keys = worker.read_keys(self._view)
        identity = ctx.engine.attempt_identity(keys)
        if ctx.store.ledger.is_spent(work_id, descriptor.route, identity):
            self._work.idle_pops += 1
            self._sleep(work_id, keys)
            return None
        self._queue.take(work_id)
        self._leases.take(descriptor.leases)
        return Armed(descriptor, worker, keys, identity, entry_index,
                      self._work_entries[entry_index].cost)

    def _disarm(self, armed: Armed) -> None:
        """Release what arming took, once the proposal lands or is dropped.

        A source job's release is the source's own: ``settle(None)`` is
        the abandoned-fire path (a cancelled pool slot, a replay proposal
        dropped past the tail), and it is a no-op once the commit path
        has settled this subject — which is what makes it safe here.
        """
        self._leases.release(armed.descriptor.leases)
        self._close_dispatch(armed)
        if armed.source is not None:
            self._source_inflight.pop(armed.descriptor.subject, None)
            armed.source.settle(self._view, armed.descriptor.subject, None)
            return
        self._queue.release(armed.worker_id)

    def _dispatch(self, armed: Armed) -> None:
        """Record the START of one pass, then let it go (H4 W2, ruling 2).

        The marker is written HERE — main thread, between commits, before
        the fire reads a single record — because that is what makes its
        POSITION the snapshot prefix. Commit order alone cannot say what
        a pooled fire saw: it was launched at one position and lands,
        possibly, many commits later. With the dispatch recorded, replay
        launches the same worker against the same state and reaps it at
        the same commit.

        Every dispatched pass is marked, committing or not: a pull pass
        that produces nothing still consumed candidates, and the marker
        is how a replay rebuilds the scheduler's tried set, stage memory
        and acceptance floor exactly rather than approximately.
        """
        self._work.dispatched += 1
        self._marked.add(armed.worker_id)
        self._ctx.store.mark_start(armed.worker_id)

    def _close_dispatch(self, armed: Armed) -> None:
        """Tell the store one recorded dispatch is over. Idempotent.

        This run wrote the marker, so this run closes it — and the SET is
        what makes that exact: a replay re-running a dispatch whose
        marker already stands wrote none, and must not close one either.

        WHEN it is called matters, which is why :meth:`_commit` calls it
        BEFORE the wall rather than leaving it to :meth:`_disarm`: the
        store frames the memo only where no dispatch is outstanding (a
        frame is a resume point, ``core.store._frame``), and the frame is
        taken INSIDE the commit. A pass still counted as outstanding at
        its own commit would make a serial run — where it is the only
        pass there is — never frame at all.
        """
        if armed.worker_id in self._marked:
            self._marked.discard(armed.worker_id)
            self._ctx.store.settle_start()

    def _propose(self, armed: Armed) -> Proposal:
        """Run one worker and shape its batch. Commit-free, hence poolable."""
        descriptor = armed.descriptor
        work_id = descriptor.work_id
        progress = ProgressSink(str(work_id))
        result = armed.worker.run(self._view, armed.identity, progress)
        check_progress(str(work_id), result, progress)
        # A SOURCE job spends nothing and subscribes to nothing (H4 W2):
        # its repetition is bounded by the source's flag and tried set,
        # not by the ledger, so a failed pass produces an EMPTY batch
        # that ``_commit`` never commits at all.
        spends: tuple[SpendProposal, ...] = ()
        subscriptions: tuple[Subscription, ...] = ()
        if armed.source is None:
            spends = (SpendProposal(work_id, descriptor.route,
                                    armed.identity, result.outcome,
                                    exposures=1 if result.exposure else 0),)
            subscriptions = self._subscription(work_id, armed.keys)
        batch = CommitBatch(
            writes=self._ctx.changed(result.writes),
            spends=spends,
            subscriptions=subscriptions,
            blobs=result.blobs,
        )
        return Proposal(armed, result, progress.units, batch)

    def _apply(self, proposal: Proposal) -> RunOutcome | None:
        """The serial point: commit one proposal, then consult the close."""
        self._commit(proposal)
        return self._maybe_consult()

    def _commit(self, proposal: Proposal) -> None:
        """Commit one queued proposal and absorb what it woke.

        Every proposal that reaches here is a queue member: the close
        commits its own verdict, counted in :meth:`_consult` (B12).

        **A failed pull pass is not a commit** (H4 W2, Q4): it carries no
        writes, no blobs, no spend and no subscription, so committing it
        would burn a sequence number and journal an event that changed
        nothing. It is counted as the fire it was and settled, and the
        ordering journal stays a record of the work that PRODUCED
        something — which is what makes replay in that order re-derive
        every consult.
        """
        armed = proposal.armed
        self._work.fires += 1
        self._work.work_units += proposal.units
        outcome_name = proposal.result.outcome
        self._work.outcomes[outcome_name] = (
            self._work.outcomes.get(outcome_name, 0) + 1)
        if self._is_noop(proposal):
            self._settle(proposal)
            return
        self._close_dispatch(armed)      # before the wall: see the docstring
        commit = self._ctx.apply(proposal.batch)
        self._note(commit)
        if commit.changed_keys:
            self._work.useful_fires += 1
        if proposal.result.retire and armed.source is None:
            self._queue.retire(armed.worker_id)
        self._absorb(commit)
        self._settle(proposal)

    @staticmethod
    def _is_noop(proposal: Proposal) -> bool:
        """A source pass that produced nothing durable at all."""
        batch = proposal.batch
        return (proposal.armed.source is not None and not batch.writes
                and not batch.blobs and not batch.spends
                and not batch.subscriptions)

    def _settle(self, proposal: Proposal) -> None:
        """Hand the pass back to its source — AFTER the commit — then release.

        The flag protocol's first ordering, on which the whole lost-wake
        argument rests: the pose is durable before its neighbours are
        pinged, so a window this settle wakes consults an index that
        already holds it (``solve.place_sched.settle``).
        """
        armed = proposal.armed
        if armed.source is not None:
            self._source_inflight.pop(armed.descriptor.subject, None)
            armed.source.settle(self._view, armed.descriptor.subject,
                                proposal.result)
        self._disarm(armed)

    def price(self, descriptor: WorkDescriptor, entry_index: int) -> int:
        """What this descriptor costs RIGHT NOW — the one price expression.

        Entry price, plus the descriptor's lane term, plus the RE-WORK
        ORDINAL term (H5, 2026-08-19): ``recipe.work_price`` composes the
        three and this reads the third off the durable spend ledger. The
        row is the descriptor's own ``(work_id, route)`` pair, and the
        ledger keys rows by exactly that — where ``WorkId`` already
        carries family, subject, route and SCOPE — so a tile's scan on
        one footing, its retry on that same footing and its union at a
        ppc each age on their OWN history rather than on a shared per-tile
        tally. That is the ruling's "each route's subject has its own
        spend rows", read where the rows are.

        Called from BOTH places a price is set, and it must stay that
        way: :func:`frontier.admit` at first mint (where the ordinal is
        always 0, because a work id has not fired before it is admitted)
        and :meth:`_absorb` on every wake, which is where a re-attempt is
        actually re-priced. A worker is minted ONCE — ``_workers`` is
        monotone and ``offer`` skips an admitted id — so a re-arm is the
        same descriptor re-pushed, and a price set only at mint could
        never age.

        It is DURABLE state, read on the main thread at a commit
        boundary, so the pooled and serial lanes read the same ordinal for
        the same attempt: the ledger is mutated only by ``apply_committed``
        and only there.
        """
        held = self._ctx.store.ledger.held(descriptor.work_id,
                                           descriptor.route)
        return work_price(self._work_entries[entry_index].cost,
                          descriptor.premium,
                          0 if held is None else held.attempts)

    def _sleep(self, worker_id: WorkId,
               keys: tuple[ResourceKey, ...]) -> None:
        """An idle worker re-declares its read-set only if it changed."""
        subscription = self._subscription(worker_id, keys)
        if subscription:
            self._note(self._ctx.apply(
                CommitBatch(subscriptions=subscription)))

    def _subscription(self, worker_id: WorkId, keys: tuple[ResourceKey, ...],
                      ) -> tuple[Subscription, ...]:
        if self._ctx.store.subscription(worker_id) == keys:
            return ()
        return (Subscription(worker_id, keys),)

    def _note(self, commit: CommitResult) -> None:
        """Count one commit — the run's own — and serve a waiting observer.

        One increment site, one owner (:class:`CommitLedger`, which the
        observer holds the same instance of), so "commits" cannot mean
        two numbers again. The snapshot is minted HERE — main thread,
        commit boundary, only when a viewer asked for one.
        """
        if self._replay is not None:
            # The cursor indexes ENTRIES, dispatches included (H4 W2), so
            # the position to check against is the journal's own — never
            # the commit sequence, which stopped being the same integer.
            self._replay.verify(self._ctx.store.journal_position,
                                commit.batch_id)
        self._commits.note(commit, scheduled=True)
        if self._status is not None and self._status.wants_snapshot():
            self._publish()

    def _absorb(self, commit: CommitResult) -> None:
        """Wake what this commit moved; re-enumerate if the domain grew.

        Every wake comes from the resource table — including the arrival
        of a key no worker could have named, which reaches its
        subscribers as a bump on the collection it joined (M4). A woken
        descriptor *sleeping on a decline* is not a worker yet: it is
        un-parked and the next enumeration re-offers it (M2). The work
        SOURCE is not woken from here at all — its wakes are pings, and
        they ride the settle that follows this call.

        **A WAKE RE-PRICES (H5 re-work aging, 2026-08-19.)** This is the
        one place a re-attempt's price can move, because it is the one
        place a re-attempt enters the queue: minting happens once
        (``_workers`` is monotone, and ``frontier.offer`` skips an
        already-admitted work id), so the descriptor pushed here is the
        object admitted for its FIRST attempt and ``Worklist.push`` reads
        the cost book. Re-admitting it at :meth:`price` folds in the
        ordinal the ledger now holds — the attempt that just spent is
        counted, so the NEXT attempt pays for it. A worker whose own fire
        is still out is deferred by ``push`` into the re-wake set and
        delivered by ``release`` at this same price, because the cost
        book is read at push time either way.
        """
        # Which kinds expand the frontier is the RECORD REGISTRY's
        # declaration (R3), not a list of domain kinds an engine has no
        # business knowing.
        structural_kinds = self._ctx.registry.structural_kinds()
        structural = any(key.kind in structural_kinds
                         for key in commit.changed_keys)
        for worker_id in commit.wakes:
            if worker_id in self._workers:
                entry_index = self._queue.entry[worker_id]
                self._queue.admit(
                    worker_id,
                    cost=self.price(self._workers[worker_id][0], entry_index),
                    entry=entry_index)
                self._queue.push(worker_id)
            elif self._pending.pop(worker_id, None) is not None:
                structural = True
        if structural:
            self._refresh()

    # -- close -------------------------------------------------------------

    def _maybe_consult(self) -> RunOutcome | None:
        if self._recipe.close_entry.gate != GATE_COUNT_READY:
            return None
        # §9 stop-condition form: ``--complete`` defers the DECISION to
        # the end, and only the decision — the mid-run consult runs in
        # ``observe`` (2026-08-13), so K, the metadata rank and the
        # per-block counts stay live while the close waits. `--no-close`
        # rides the same posture and never leaves it (2026-08-22).
        mode = CONSULT_OBSERVE if self._deferred else CONSULT_CLOSE
        return self._consult(selector=GATE_COUNT_READY, mode=mode,
                             exhausted=False)

    @property
    def _deferred(self) -> bool:
        """Is the DECISION deferred past the mid-run consults?

        One property because the two flags answer it the same way and the
        two consult sites both ask: `--complete` defers the decision to
        the exhaustion consult, `--no-close` defers it past the end of
        the run entirely. Naming it once is what makes ``--complete
        --no-close`` legal-and-redundant a fact of the code rather than a
        coincidence of two branches.
        """
        return self._complete or self._no_close

    def _consult(self, *, selector: str, mode: str,
                 exhausted: bool) -> RunOutcome | None:
        """Ask the terminal consumer, out of band (choice 1, worklist B12).

        Out of band = not through the ready queue: a verified close
        preempts everything, so there is no descriptor, no work id, no
        lease, no slot and no spend row. What survives from the provider
        shape is the ELIGIBILITY test (the frontier version must have
        moved since this gate last consulted) and the ordinary commit of
        whatever the verdict carries. ``selector`` and ``exhausted`` were
        one ``final`` flag doing two unrelated jobs — choosing the gate
        AND setting the outcome's flag — which coincided at only one of
        the two call sites; each caller now states both intents. An
        ``observe`` consult may not decide, so it is counted under its
        own name and ``consults`` keeps meaning what the HEALTH rows did.
        """
        version = self._view.version(self._close.frontier)
        if self._consulted.get(selector) == version:
            return None                       # same equations: idle (§7, M11)
        self._consulted[selector] = version
        if mode == CONSULT_OBSERVE:
            self._work.observations += 1
        else:
            self._work.consults += 1
        verdict = self._close.consult(self._view, mode=mode)
        self._last_close = verdict.report or self._last_close
        writes = self._ctx.changed(verdict.writes)
        if writes or verdict.blobs:
            # A consult that decides nothing writes nothing, and a batch
            # of nothing is not a commit: the old spend row made every
            # look cost a commit sequence number (L10).
            self._note(self._ctx.apply(
                CommitBatch(writes=writes, blobs=verdict.blobs)))
        if not self._ctx.terminal:
            return None
        return self._terminal_outcome(resumed=False, exhausted=exhausted)

    def _exhausted(self) -> RunOutcome:
        """Every worker idle across every entry (§9): OPEN and resumable.

        Under `--no-close` the one consult here is an OBSERVATION: the
        counts and the metadata rank are refreshed for the status view
        and the epilogue, and nothing decides, so nothing is written and
        the session stays OPEN (2026-08-22).
        """
        outcome = self._consult(
            selector=GATE_EXHAUSTION if self._deferred else GATE_COUNT_READY,
            mode=(CONSULT_OBSERVE if self._no_close
                  else CONSULT_FINAL if self._complete else CONSULT_CLOSE),
            exhausted=True)
        if outcome is not None:
            return outcome
        certified = len(self._view.certified_work_keys())
        reason = (self._last_close or {}).get("reason")
        return RunOutcome(
            status="open", close=self._last_close,
            commits=self._commits.scheduled_commits, fires=self._work.fires,
            certified=certified, exhausted=True,
            reason=reason or "no worker can contribute; session stays open")

    def _integrity_failure(self, conflict: CertificateConflict) -> RunOutcome:
        """A contradicted certificate becomes a DURABLE terminal fact (F-11).

        B13's shape as executed — deliver what is deliverable, then go
        terminal — and mid-run nothing is deliverable, so the fact IS the
        delivery: one ordinary commit of
        ``CloseRecord(integrity_failure)`` carrying the conflict's own
        message, which already names the key and what differed. The
        argument is in ``engine/DESIGN.md``. This commit cannot recurse
        into the catch: it writes the close key alone, and the only
        refusal a close write can raise is terminality — which the
        conflict itself proves has not happened.
        """
        reason = str(conflict)
        self._last_close = {
            "status": CloseStatus.INTEGRITY_FAILURE.value,
            "reason": reason,
            "certified": len(self._view.certified_work_keys()),
        }
        self._note(self._ctx.apply(CommitBatch(writes=(
            Write(CLOSE_KEY, CloseRecord(status=CloseStatus.INTEGRITY_FAILURE,
                                         reason=reason)),))))
        return self._terminal_outcome(resumed=False, exhausted=False)

    def _terminal_outcome(self, *, resumed: bool = True,
                          exhausted: bool = True) -> RunOutcome:
        """A terminal session is immutable (§5.5) — report what it holds.

        The durable ``CloseRecord`` is the answer, whether this run wrote
        it or a previous one did; the payload comes back through the
        ordinary blob path, re-verified against its ref (F-13), which is
        what lets the engine end a run on a family whose result type it
        cannot name. ``commits``/``fires`` are run-scoped and zero on a
        resume; ``certified`` is a property of the state.
        """
        record = self._ctx.close_record()
        assert isinstance(record, CloseRecord)
        payload = None
        if record.status is CloseStatus.VERIFIED and record.bytes_ref is not None:
            payload = bytes(self._ctx.read_blob(record.bytes_ref, verify=True))
        reason = record.reason or (self._last_close or {}).get("reason")
        return RunOutcome(
            status=record.status.value, payload=payload,
            close=self._last_close,
            commits=0 if resumed else self._commits.scheduled_commits,
            fires=0 if resumed else self._work.fires,
            certified=len(self._view.certified_work_keys()),
            exhausted=exhausted, resumed_terminal=resumed,
            reason=reason or ("session already terminal" if resumed else None))

    # -- observation (L12: derived, never state) ---------------------------
    # Both bodies live in ``engine/observe.py`` (H4 W2, the file cap):
    # they are pure derivation over this object's own collections, and
    # the seam keeps the control loop the control loop. The contract is
    # unchanged and stated there — main thread, commit boundary.

    def _publish(self) -> None:
        observe.publish(self)

    def snapshot(self) -> RunSnapshot:
        """The frozen instant the diag surface reads (§10.3)."""
        return observe.snapshot(self)

__all__ = ["CONSULT_CLOSE", "CONSULT_FINAL", "CONSULT_OBSERVE",
           "CloseConsult", "CloseVerdict", "FireCountTripwire",
           "NoProviderError", "Orchestrator", "ReplayError", "RunObserver",
           "RunOutcome"]

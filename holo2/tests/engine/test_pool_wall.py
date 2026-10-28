"""The commit wall's own conflict resolution: staleness discard vs the join.

Unit tests over the same captureless session ``test_orchestrator.py``
uses — no pixels, no survey, no toys — so what is under test is what
the wall does when a commit lands MID-FLIGHT against another proposal:
a proposal whose read-set moved under it is a STALE DISCARD (a lattice
seed, compare-and-swap semantics), while a proposal that only touches a
JOINED key (a tile, the commutative carry) is not stale at all — the
wall merges the two writes instead of choosing one. Companion to
``test_pool.py`` (the pool's own admission/dispatch mechanics, and the
source-job/preemption/contract pins that used to sit alongside these);
split out of that file 2026-08-17 once it crossed 1000 lines, under the
line-cap-as-seam-signal ruling (CLAUDE.md memory: the cap is a
split-here signal, never a budget to game by squeezing prose).

**Two lanes** (H4-PLAN §4/W-S, R9): every interleaving pinned below is
FORCED, not hoped for — an event or barrier a fire waits on, released
from inside the wall via ``spy_on_commits`` (``conftest.py``) — because
continuous admission commits in completion order, so a live parallel
run is not a deterministic function of the state it started from.
"""
from __future__ import annotations

import threading
from pathlib import Path

from holo2.core.commit import CommitBatch, Subscription, Write
from conftest import (FOOTING, REGION, lattice_seed_key, make_seed,
                      spy_on_commits)
from holo2.solve import tile_key
from holo2.solve.records import carry_tile
from holo2.core.work import WorkResult
from test_orchestrator import (ADDRESSES, CertifyingWorker, Factories, RECIPE,
                               make_orchestrator, make_session,
                               seed_addressed, work_id)

#: Never wait forever: a broken loop must fail the suite, not hang it.
WAIT_S = 20.0


def _meddle_seed(worker_id):
    """A record key private to one worker: a name nobody else builds.

    R5's seed is keyed ``(footing, region)``, so the FOOTING is what
    distinguishes one worker's probe from another's, and the victim's own
    work key picks it deterministically — no shared name, no digest. (It
    was a window-keyed hint state until H4 W2's clean-slate sweep deleted
    that family; the probe moved to the tree's other improve-only record
    and the fixture's shape is unchanged.)
    """
    page, ty, tx, _stream = worker_id.subject.parts
    offset = (int(page) * 16 + int(ty) * 4 + int(tx)) * 8
    return lattice_seed_key(f"{FOOTING}/probe-{offset}", REGION)


# ------------------------------------------------------------- staleness

class Meddling(CertifyingWorker):
    """Certifies its own key AND bumps a key its round-mate reads.

    The round-mate's proposal is therefore in flight against a frontier
    that moved: §10.1 says discard it and re-arm, never commit it.
    """

    route = "pool-meddle"

    def __init__(self, key, *, victim=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self._victim = victim

    def run(self, view, identity, progress):
        result = super().run(view, identity, progress)
        if self._victim is None:
            return result
        key = _meddle_seed(self._victim)
        return WorkResult(
            outcome=result.outcome, blobs=result.blobs,
            writes=result.writes + (
                Write(key, make_seed(self.fires, footing_id=key.parts[0])),),
            retire=result.retire)


class Subscribing(CertifyingWorker):
    """Reads a probe key as well as its own, so a meddler can move it.

    Its first fire BLOCKS until the wall says a meddler's write landed:
    continuous admission commits while other fires run, so the test can
    stage that interleaving instead of hoping the scheduler produces it.
    """

    route = "pool-subscribed"

    def __init__(self, key, *, released=None, witness=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self.released = released if released is not None else threading.Event()
        self._witness = witness if witness is not None else (lambda: 0)
        #: Commits the wall had made when this fire started, and when it
        #: stopped waiting: the interleaving, observed from inside a fire.
        self.window: list[int] = []

    def read_keys(self, view):
        return tuple(sorted((self.key,
                             _meddle_seed(self.worker_id))))

    def run(self, view, identity, progress):
        self.window.append(self._witness())
        assert self.released.wait(WAIT_S), "nothing ever committed"
        self.window.append(self._witness())
        return super().run(view, identity, progress)


class MeddlingFactories(Factories):
    """Worker A meddles with worker B's read-set WHILE B is still in flight.

    The event is what makes that interleaving certain instead of likely:
    B's fire blocks until the wall has admitted somebody, and since B is
    the only blocker, the somebody is a meddler.
    """

    identity = "pool-meddle-workers"

    def __init__(self) -> None:
        super().__init__()
        self.released = threading.Event()
        self.committed: list = []

    def _make(self, key):
        victim = work_id(tile_key(0, 1, 1, "main"), Subscribing.route)
        if key == tile_key(0, 1, 1, "main"):
            return Subscribing(key, released=self.released,
                               witness=lambda: len(self.committed))
        return Meddling(key, victim=victim)

    def watch(self, orchestrator):
        """Wire the wall: count admissions, release the victim at the first."""
        def note(proposal) -> None:
            self.committed.append(proposal.armed.worker_id)
            self.released.set()

        spy_on_commits(orchestrator, note)
        return orchestrator

    @property
    def victim(self) -> Subscribing:
        return self.made[work_id(tile_key(0, 1, 1, "main"),
                                 Subscribing.route)]


def test_a_commit_lands_while_another_fire_is_still_running(
        tmp_path: Path) -> None:
    """The whole point of continuous admission (R9), observed from a fire.

    Under the round barrier this window was empty by construction: the
    wall committed nothing until every future in the round had returned.

    **KNOWN FLAKE UNDER CPU STARVATION** (measured and ruled, H4 W6,
    2026-08-18 — the one test in this file whose interleaving is HOPED
    FOR rather than forced, against the file docstring's own two-lane
    rule). ``start == 0`` says the victim's fire began before the wall
    admitted anybody, which is a statement about THREAD SCHEDULING, not
    about the model: nothing holds the meddlers back, so a victim thread
    that does not get the CPU until three sibling fires have completed
    and been absorbed reads a non-zero window and the assertion fails
    (observed value 2). ISOLATION EVIDENCE: 0/6 failures at ``-n 4`` and
    ``-n 8`` on an idle machine and 0/1 for the whole suite at ``-n 16``;
    4/6 consecutive failures at ``-n 8`` while a sibling worktree and an
    echo run had the cores, and a clean reproduction at ``-n 8`` under 12
    synthetic spinners — ALWAYS this test, ALWAYS this line, never
    another assertion in this file and never a ``WAIT_S`` timeout.
    There is no timing MARGIN to widen (this is an order, not a
    duration), and the honest fix is to force the order the way every
    other fixture here does — an event the victim sets on entry and the
    meddlers wait on — which is a fixture change three other tests and
    the replay recordings ride on. Recorded for the lead rather than
    taken inside a relocation wave.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = MeddlingFactories()
        factories.watch(make_orchestrator(session, RECIPE, factories,
                                          workers=8)).run()
    start, released = factories.victim.window[:2]
    assert start == 0
    assert released >= 1, "the wall waited for every fire after all"


def test_an_in_flight_proposal_whose_frontier_moved_is_discarded(
        tmp_path: Path) -> None:
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = MeddlingFactories()
        orchestrator = factories.watch(
            make_orchestrator(session, RECIPE, factories, workers=8))
        outcome = orchestrator.run()
        certified = session.plane.tiles().certified_keys()
    counters = orchestrator.snapshot().counters
    assert counters.stale_discards >= 1, "the meddled proposal stood"
    assert counters.stale_discard_ratio > 0.0
    # Waste, never error: the victim re-armed and certified anyway.
    assert outcome.certified == len(ADDRESSES) == len(certified)
    assert factories.victim.fires >= 2


class Querying(CertifyingWorker):
    """Its read-set is a QUERY: it names a key only once that key exists.

    This is the shape every real read-set has (``the observation pieces on
    this tile``), and it is the case a version-by-version staleness check
    misses: nothing the worker named moved, and yet its identity is stale
    because a key it would now read has arrived.
    """

    route = "pool-query"

    def __init__(self, key, *, released=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self.released = released if released is not None else threading.Event()

    def read_keys(self, view):
        probe = lattice_seed_key(FOOTING, REGION)
        keys = [self.key]
        if view.record(probe) is not None:
            keys.append(probe)
        return tuple(sorted(keys))

    def run(self, view, identity, progress):
        assert self.released.wait(WAIT_S), "the probe key never arrived"
        return super().run(view, identity, progress)


class Arriving(CertifyingWorker):
    """Certifies its own key and makes the probe key exist."""

    route = "pool-arrive"

    def run(self, view, identity, progress):
        result = super().run(view, identity, progress)
        return WorkResult(
            outcome=result.outcome, retire=result.retire, blobs=result.blobs,
            writes=result.writes + (
                Write(lattice_seed_key(FOOTING, REGION),
                      make_seed()),))


class QueryFactories(Factories):
    """One worker makes the probe key exist; the queriers wait for it.

    Which of them the wall admits first is the pool's business now, so
    the queriers hold their fires until the arrival has COMMITTED — the
    probe then lands mid-flight for every one of them, by construction.
    """

    identity = "pool-query-workers"

    def __init__(self) -> None:
        super().__init__()
        self.released = threading.Event()

    def _make(self, key):
        first = tile_key(0, 0, 0, "main")
        return (Arriving(key) if key == first
                else Querying(key, released=self.released))

    def watch(self, orchestrator):
        spy_on_commits(orchestrator, lambda _proposal: self.released.set())
        return orchestrator


def test_a_read_set_that_grew_in_flight_is_stale(tmp_path: Path) -> None:
    """Membership drift is staleness too, not only version drift."""
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = QueryFactories()
        orchestrator = factories.watch(
            make_orchestrator(session, RECIPE, factories, workers=8))
        outcome = orchestrator.run()
    counters = orchestrator.snapshot().counters
    assert counters.stale_discards >= 1, (
        "a proposal whose read-set gained a key was committed anyway")
    assert outcome.certified == len(ADDRESSES)
    # And the re-armed workers minted under the identity they actually read.
    for worker_id, worker in factories.made.items():
        if isinstance(worker, Querying):
            assert worker.fires >= 2, worker_id


# ------------------------------- the commutative tile merge (H4 W2, R1)

#: The tile every racing fire in this section also writes. It is one of
#: the four seeded addresses, so it has a certifying worker of its own.
SHARED = tile_key(0, 0, 0, "main")

#: One footing per racing fire, so "whose gain survived" is readable off
#: the record instead of inferred from a count.
RACE_FOOTINGS = {tile_key(0, 0, 1, "main"): "r:2/1",
                 tile_key(0, 1, 0, "main"): "r:4/1",
                 tile_key(0, 1, 1, "main"): "r:8/1"}


class Racing(CertifyingWorker):
    """Certifies its own key AND writes a tile it never bound.

    A placement fire's exact shape: which tiles a pose covers is search
    OUTPUT, learned by running, so those keys cannot be in a read-set and
    NO staleness test can protect them. This double snapshots the shared
    tile the instant it starts, rendezvouses so that every fire is
    provably holding a pre-commit snapshot, waits for the wall to commit
    somebody, and then proposes the carry it computed against a snapshot
    that is now stale by construction.
    """

    route = "pool-race"

    def __init__(self, key, *, gate=None, released=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self._gate = gate
        self.released = released if released is not None else threading.Event()
        self.footing = RACE_FOOTINGS[key]

    def run(self, view, identity, progress):
        snapshot = view.record(SHARED)              # pre-race, by design
        gate, self._gate = self._gate, None         # one rendezvous, not two
        if gate is not None:
            gate.wait(WAIT_S)
        assert self.released.wait(WAIT_S), "nothing ever committed"
        result = super().run(view, identity, progress)
        return WorkResult(
            outcome=result.outcome, retire=result.retire, blobs=result.blobs,
            writes=result.writes + (Write(SHARED, carry_tile(
                snapshot, (self.footing,), baseline=self.footing)),))


class Certifying(CertifyingWorker):
    """The shared tile's own worker: rendezvous, then certify it."""

    route = "pool-race"

    def __init__(self, key, *, gate=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self._gate = gate

    def run(self, view, identity, progress):
        gate, self._gate = self._gate, None
        if gate is not None:
            gate.wait(WAIT_S)
        return super().run(view, identity, progress)


class RacingFactories(Factories):
    """One certifier for the shared tile, three stale observers behind it.

    The barrier makes every snapshot provably pre-commit; the event makes
    the certifier provably first, since it is the only fire not waiting
    on one.
    """

    identity = "pool-race-workers"

    def __init__(self) -> None:
        super().__init__()
        self.released = threading.Event()
        self.gate = threading.Barrier(len(ADDRESSES))

    def _make(self, key):
        if key == SHARED:
            return Certifying(key, gate=self.gate)
        return Racing(key, gate=self.gate, released=self.released)

    def watch(self, orchestrator):
        spy_on_commits(orchestrator, lambda _proposal: self.released.set())
        return orchestrator


def _race(tmp_path: Path, name: str):
    with make_session(tmp_path, name) as session:
        seed_addressed(session)
        factories = RacingFactories()
        orchestrator = factories.watch(
            make_orchestrator(session, RECIPE, factories, workers=8))
        outcome = orchestrator.run()
        record = session.store.get(SHARED)
    return outcome, record, orchestrator.snapshot().counters


def test_a_stale_write_onto_a_certified_tile_no_longer_kills_the_run(
        tmp_path: Path) -> None:
    """THE previously-fatal race, run through the real pool and wall.

    Before the tile family declared its join, the first of these three
    proposals reached ``_tile_transition`` holding a bare observation
    where a certificate now stands, raised ``certified content may not
    change``, and the orchestrator wrote ``CloseRecord(integrity_failure)``
    — a terminal, unresumable session, from three fires that each did
    exactly what they were supposed to do. The wall joins now: the
    certificate stands untouched and the observations land on top of it.
    """
    outcome, record, _counters = _race(tmp_path, "race")
    assert outcome.status == "open", outcome.reason
    assert record is not None and record.certified
    assert record.bits_ref is not None and record.metadata_bit == 1


def test_every_racing_gain_survives_the_race(tmp_path: Path) -> None:
    """The lost-gains sibling: three concurrent gains, three survivors.

    Each fire joined its own footing onto the SAME snapshot, so under
    last-write-wins exactly one of them would stand and the other two
    would vanish silently — no refusal, no counter, no trace. Both
    monotone sets are checked, because ``baselined`` is the one a retry
    route later derives from and losing it costs a decode.
    """
    _outcome, record, counters = _race(tmp_path, "gains")
    assert record is not None
    expected = tuple(sorted(RACE_FOOTINGS.values()))
    assert record.baselined == expected
    assert set(expected) <= set(record.observed_by)
    assert "f:1/1" in record.observed_by, "the seeded observation was dropped"
    assert counters.stale_discards == 0


class TileMeddling(CertifyingWorker):
    """Adds an observation to a tile its ROUND-MATE reads and binds.

    The sibling of :class:`Meddling`, one key kind over: that one moves a
    lattice seed (compare-and-swap, still) and this one moves a tile
    (joined at the wall). Same interleaving, opposite verdict.
    """

    route = "pool-tile-meddle"

    def __init__(self, key, *, victim=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self._victim = victim

    def run(self, view, identity, progress):
        result = super().run(view, identity, progress)
        if self._victim is None:
            return result
        return WorkResult(
            outcome=result.outcome, blobs=result.blobs, retire=result.retire,
            writes=result.writes + (Write(self._victim, carry_tile(
                view.record(self._victim), ("r:9/1",))),))


class TileMeddlingFactories(MeddlingFactories):
    """``MeddlingFactories``' shape, meddling with a JOINED key instead."""

    identity = "pool-tile-meddle-workers"

    VICTIM = tile_key(0, 1, 1, "main")

    def _make(self, key):
        if key == self.VICTIM:
            return Subscribing(key, released=self.released,
                               witness=lambda: len(self.committed))
        return TileMeddling(key, victim=self.VICTIM)

    @property
    def victim(self) -> Subscribing:
        return self.made[work_id(self.VICTIM, Subscribing.route)]


def test_a_moved_JOINED_key_does_not_discard_a_proposal(
        tmp_path: Path) -> None:
    """The staleness projection, end to end.

    ``Subscribing`` binds the key it is about to write, and its
    round-mates move that key while its fire is out. On a lattice seed
    that is a stale discard and a second fire — pinned two tests up, in
    ``test_an_in_flight_proposal_whose_frontier_moved_is_discarded``. On
    a TILE it is not staleness at all: the wall will join, so there is
    nothing for the fire to be stale about, its proposal commits, and
    both the certificate and the meddled observation stand.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = TileMeddlingFactories()
        orchestrator = factories.watch(
            make_orchestrator(session, RECIPE, factories, workers=8))
        outcome = orchestrator.run()
        record = session.store.get(TileMeddlingFactories.VICTIM)
    counters = orchestrator.snapshot().counters
    assert counters.stale_discards == 0, "a joined key discarded a proposal"
    assert factories.victim.fires == 1, "the victim re-armed for nothing"
    assert outcome.certified == len(ADDRESSES)
    assert record is not None and record.certified
    assert "r:9/1" in record.observed_by


class Ghosted(CertifyingWorker):
    """Subscribed to a key it no longer READS, and blocking on the wall.

    A stale-broad read-set is what turns a mid-flight wake into a DOUBLE
    ARM rather than a stale discard: the wake arrives while the fire
    runs, but the identity that fire holds never moved, so its proposal
    is perfectly current and commits.
    """

    route = "pool-ghosted"

    def __init__(self, key, *, released=None, **kwargs) -> None:
        super().__init__(key, **kwargs)
        self.released = released if released is not None else threading.Event()

    def run(self, view, identity, progress):
        assert self.released.wait(WAIT_S), "nothing ever committed"
        return super().run(view, identity, progress)


class GhostFactories(Factories):
    identity = "pool-ghost-workers"

    def __init__(self) -> None:
        super().__init__()
        self.released = threading.Event()

    @property
    def victim_id(self):
        return work_id(tile_key(0, 1, 1, "main"), Ghosted.route)

    def _make(self, key):
        if key == tile_key(0, 1, 1, "main"):
            return Ghosted(key, released=self.released)
        return Meddling(key, victim=self.victim_id)

    def watch(self, orchestrator):
        spy_on_commits(orchestrator, lambda _proposal: self.released.set())
        return orchestrator


def test_a_wake_never_arms_a_worker_whose_fire_is_in_flight(
        tmp_path: Path) -> None:
    """One worker, one fire at a time — the invariant the barrier gave free.

    A commit landing mid-flight can wake a worker whose own fire is STILL
    RUNNING, because its durable subscription names the key that moved.
    Arming it again runs two fires against one identity — measured with
    the deferral removed: this shape fires the victim twice, and the same
    fault on the real spine e2e reaches the wall and dies there
    (``SpendConflict: identity already spent``). The wake is held instead
    and re-delivered when the fire lands.
    """
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = GhostFactories()
        # The read-set a PREVIOUS fire left behind, one key wider than
        # what this worker reads now: the subscription is what wakes, the
        # identity is what decides staleness, and here they disagree.
        session.apply(CommitBatch(subscriptions=(
            Subscription(factories.victim_id,
                         tuple(sorted((tile_key(0, 1, 1, "main"),
                                       _meddle_seed(
                                           factories.victim_id))))),)))
        orchestrator = factories.watch(
            make_orchestrator(session, RECIPE, factories, workers=8))
        outcome = orchestrator.run()
        spends = session.store.ledger.spends_for(factories.victim_id,
                                                 Ghosted.route)
    assert outcome.certified == len(ADDRESSES)
    assert len(spends) == 1, "the victim spent one identity, once"
    assert factories.made[factories.victim_id].fires == 1


def test_a_stale_discard_spends_nothing(tmp_path: Path) -> None:
    """A discarded proposal never reached the ledger (§7: spend ⇔ outcome)."""
    with make_session(tmp_path) as session:
        seed_addressed(session)
        factories = MeddlingFactories()
        factories.watch(make_orchestrator(session, RECIPE, factories,
                                          workers=8)).run()
        victim = work_id(tile_key(0, 1, 1, "main"), Subscribing.route)
        spends = session.store.ledger.spends_for(victim, Subscribing.route)
    assert len(spends) == 1, "only the surviving attempt is durable"

"""Start markers: what makes a POOLED ordering replayable at all.

H4 W2's second concurrency ruling. The journal pins commit order, but a
fire's inputs are pinned by its DISPATCH — it reads the store as of the
moment it was launched and lands, possibly, several commits later. That
position was unrecorded, so a replay had to re-derive the dispatch order
from a queue whose order had been the pool's, and the shape it could not
reproduce is the one this file constructs on purpose: **a fire dispatched
BEFORE a neighbouring commit and committing AFTER it.**

The fixtures are ``test_pool``'s doubles, because the interleaving has to
be MADE rather than hoped for: a fire that blocks until the wall has
admitted somebody is dispatched before that commit by construction.

Fault injection is the same ordering with its markers stripped — which is
exactly the pre-marker journal — and it must fail loudly.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from holo2.core import is_marker, marker_work_id
from holo2.core.cache import CACHE_NAME
from holo2.core.commit import CommitBatch, Write
from holo2.core.journal import (JOURNAL_NAME, JournalError, ReplayError,
                                commit_count, read_journal)
from holo2.core.store import SCHEMA_VERSION, Store, StoreError
from holo2.engine.session import SessionContext
from holo2.solve import TileRecord, tile_key
from holo2.solve.tilemap import StoreIndex
from conftest import WINDOW, make_pose, registry
from test_orchestrator import (ADDRESSES, CertifyingWorker, Factories, RECIPE,
                               make_orchestrator, make_session, seed_addressed)
from test_pool_wall import MeddlingFactories, TileMeddlingFactories


def _recorded(tmp_path: Path, name: str, factories, *, workers: int,
              **kwargs) -> tuple[tuple[str, ...], bytes]:
    """Run once and hand back its recorded ordering and its state."""
    with make_session(tmp_path, name, **kwargs) as session:
        seed_addressed(session)
        if hasattr(factories, "watch"):
            factories.watch(make_orchestrator(
                session, RECIPE, factories, workers=workers)).run()
        else:
            make_orchestrator(session, RECIPE, factories,
                              workers=workers).run()
        return session.store.ordering(), session.store.state_bytes()


def _replay(tmp_path: Path, name: str, ordering, factories=None) -> bytes:
    """Re-fold a recorded ordering into a fresh state directory.

    The SAME provider roster the recording used — a replay re-runs the
    recorded work, so the workers have to be the ones the markers name.
    What it does not need is the recording's staged interleaving: the
    order is the record's now, so the fixture's gate opens up front.
    """
    with make_session(tmp_path, name) as session:
        seed_addressed(session)               # the same starting ground
        make_orchestrator(session, RECIPE, factories or Factories(),
                          replay=tuple(ordering)).run()
        return session.store.state_bytes()


def _released(factories: MeddlingFactories) -> MeddlingFactories:
    """The staged fixture with its rendezvous already open.

    Typed on the base class so both meddlers pass: the tile variant IS a
    ``MeddlingFactories``, and what this touches is the event they share.
    """
    factories.released.set()
    return factories


# ------------------------------------------------------- the entry shapes

def test_every_dispatched_pass_leaves_a_marker(tmp_path: Path) -> None:
    """Committing or not, one marker per dispatch — and it names the work."""
    ordering, _state = _recorded(tmp_path, "marked", Factories(), workers=1)
    markers = [entry for entry in ordering if is_marker(entry)]
    assert len(markers) == len(ADDRESSES)
    # The identity round-trips as a STRUCTURE — family, subject key,
    # route, scope — which is what a replay needs and what the lossy
    # display rendering ``WorkId.__str__`` produces is not.
    named = [marker_work_id(entry) for entry in markers]
    assert {work.family for work in named} == {"payload"}
    assert {work.route for work in named} == {"unit-certify"}
    assert sorted(work.subject for work in named) == sorted(
        tile_key(page, ty, tx, "main") for page, ty, tx in ADDRESSES)
    assert commit_count(ordering) == len(ordering) - len(markers)


def test_a_marker_folds_to_nothing(tmp_path: Path) -> None:
    """Ordering, not facts: no record moves and no sequence number burns."""
    with make_session(tmp_path) as session:
        seed_addressed(session)
        store = session.store
        before_seq, before_state = store.commit_seq, store.state_bytes()
        position = store.journal_position
        from holo2.core import WorkId
        from holo2.solve import tile_key
        store.mark_start(WorkId("payload", tile_key(0, 9, 9, "main"), "probe"))
        assert store.commit_seq == before_seq
        assert store.state_bytes() == before_state
        assert store.journal_position == position + 1


# ---------------------------------------------- the interleaving, replayed

def _staged_pool(tmp_path: Path, name: str) -> tuple[tuple[str, ...], bytes]:
    """The shape commit order cannot express, MADE rather than hoped for.

    ``TileMeddlingFactories``' victim blocks until the wall has committed
    somebody, so its dispatch provably precedes that commit while its own
    commit follows it. Its round-mates move a key it BINDS — a tile,
    joined at the wall since ruling 1 — so it is not discarded either: it
    really does commit, out of dispatch order.
    """
    return _recorded(tmp_path, name, TileMeddlingFactories(), workers=8)


def test_the_recording_really_holds_an_out_of_order_pass(
        tmp_path: Path) -> None:
    """The premise, asserted before the pin that rests on it.

    Several passes are dispatched before ANY of them commits, so all but
    one of them commits after a commit that landed under it. That is the
    shape commit order cannot express — where each fire's snapshot sits
    is unrecoverable from the commits alone — and it is why every one of
    those passes has to be re-launched at its own recorded position.
    """
    ordering, _state = _staged_pool(tmp_path, "staged")
    first_commit = next(index for index, entry in enumerate(ordering[2:], 2)
                        if not is_marker(entry))
    dispatched_first = sum(1 for entry in ordering[2:first_commit]
                           if is_marker(entry))
    assert dispatched_first > 1, (
        f"only {dispatched_first} pass was in flight when the wall "
        "committed; the interleaving this file exists for did not happen")


def test_a_pooled_ordering_replays_exactly(tmp_path: Path) -> None:
    """THE pin. Markers make the pooled fold reproducible, byte for byte.

    Same journal, same durable state — the strong form, which is what
    "auditing a state directory is re-folding its journal" has to mean if
    it is to mean anything for a run that used more than one thread.
    """
    ordering, state = _staged_pool(tmp_path, "staged")
    replayed = _replay(tmp_path, "replayed", ordering,
                       _released(TileMeddlingFactories()))
    assert replayed == state
    _header, entries = read_journal(tmp_path / "replayed" / JOURNAL_NAME)
    assert entries == ordering       # the journal itself, entry for entry


def test_the_walk_re_makes_the_stale_discard_the_recording_made(
        tmp_path: Path) -> None:
    """The other settle site, exercised: a held pass dropped mid-walk.

    ``_drop_stale`` is the walk's own copy of the wall's §7 test, and
    until now no fixture had ever reached the branch INSIDE it (measured
    2026-08-18, H4 W6: 37 calls, zero drops, across the whole engine
    suite) — the tile meddler above moves a JOINED key, which is by
    design not staleness at all.  ``MeddlingFactories`` is the one that
    moves a lattice seed, so the recording really does hold a
    dispatched-but-never-committed pass mid-ordering, and the walk must
    drop it at the same point rather than carry it to the end: a window
    the recording discarded and re-dispatched would otherwise meet a slot
    this walk is still holding, and the re-dispatch would arm nothing.

    What it pins is that the walk's judgement is the RECORDING's — same
    state, entry for entry — plus the settle that rides the drop, which
    is the half a leak would silently cost (the cadence pin below).
    """
    ordering, state = _recorded(tmp_path, "staleness", MeddlingFactories(),
                                workers=8)
    with make_session(tmp_path, "re-staleness") as session:
        seed_addressed(session)
        run = make_orchestrator(session, RECIPE, _released(MeddlingFactories()),
                                replay=tuple(ordering))
        run.run()
        replayed = session.store.state_bytes()
        outstanding = session.store.outstanding_dispatches
    assert run.snapshot().counters.stale_discards >= 1, (
        "the walk committed a pass the recording discarded")
    assert replayed == state
    assert outstanding == 0, "a dropped pass left its dispatch mark behind"


def test_the_same_ordering_without_markers_cannot_be_replayed(
        tmp_path: Path) -> None:
    """Fault injection: the pre-marker journal is the ordering minus them.

    It must fail LOUDLY — a ``ReplayError`` from the cursor, or the
    journal's own tail refusal when the re-derived fold writes an entry
    where a different one stands. Both are the pre-marker behaviour this
    ruling replaced, and a silent pass would mean the pin above was
    proving nothing.
    """
    ordering, _state = _staged_pool(tmp_path, "staged")
    commits_only = tuple(entry for entry in ordering if not is_marker(entry))
    assert len(commits_only) < len(ordering)
    with pytest.raises((ReplayError, JournalError)):
        _replay(tmp_path, "unmarked", commits_only,
                _released(TileMeddlingFactories()))


def test_a_serial_ordering_still_replays_exactly(tmp_path: Path) -> None:
    """The regression: markers cost the deterministic lane nothing."""
    ordering, state = _recorded(tmp_path, "serial", Factories(), workers=1)
    assert _replay(tmp_path, "serial-replayed", ordering) == state


# ------------------------------------------------------ crash and recovery

def cut_last_frame(state_dir: Path) -> int:
    """Drop the cache's last delta frame; leave the journal whole.

    Precisely what a process killed between two frames leaves behind, and
    reproducible, which a kill is not (the verdicts' own staging, in
    miniature — ``measure/verdicts/test_durability.py``).
    """
    raw = (state_dir / CACHE_NAME).read_bytes()
    ends, offset = [0], 0
    while offset < len(raw):
        offset += 8 + int.from_bytes(raw[offset:offset + 8], "big")
        ends.append(offset)
    assert len(ends) >= 3, "the run wrote one frame; cutting it leaves nothing"
    (state_dir / CACHE_NAME).write_bytes(raw[:ends[-2]])
    return len(ends) - 1


def frame_count(state_dir: Path) -> int:
    """Delta frames the cache holds, its header frame excluded.

    The cadence, made observable from outside: the writer flushes every
    frame as it appends it, so this reads the same mid-session as it does
    after a close.
    """
    raw = (state_dir / CACHE_NAME).read_bytes()
    frames, offset = -1, 0
    while offset < len(raw):
        offset += 8 + int.from_bytes(raw[offset:offset + 8], "big")
        frames += 1
    return frames


def _scratch_commit(session: SessionContext, index: int) -> None:
    """One ordinary commit, so the cadence has something to count."""
    session.apply(CommitBatch(writes=(
        Write(tile_key(1, 0, index, "main"),
              TileRecord(observed_by=("f:1/1",))),)))


def test_a_pooled_crash_cut_re_earns_its_tail(tmp_path: Path) -> None:
    """Pooled recovery, which markers made exact rather than lucky.

    The cache frames every other commit, the last frame is cut, and the
    reopened session re-earns the journal tail — dispatches included, at
    the positions they were dispatched from — and lands on the state the
    uncrashed run left.
    """
    ordering, state = _recorded(tmp_path, "crashed", TileMeddlingFactories(),
                                workers=8, snapshot_every=2)
    cut_last_frame(tmp_path / "crashed")

    with make_session(tmp_path, "crashed") as session:
        assert session.store.journal_position < len(ordering), (
            "the cut removed no entries at all")
        outcome = make_orchestrator(session, RECIPE,
                                    _released(TileMeddlingFactories()),
                                    workers=8).run()
        recovered = session.store.state_bytes()
        assert session.store.ordering() == ordering
        # The other half of a re-earned tail, checked where the run
        # already is: every mark the walk wrote is settled again.
        assert session.store.outstanding_dispatches == 0
    assert outcome.status == "open"
    assert recovered == state


#: A second pose of the fixture window whose KEY sorts BEFORE the ground
#: pose's — so "last committed" and "last by id" disagree, which is the
#: only way a test can tell the live-pose derivation from a sorted walk.
REVISED_POSE = make_pose(native_affine=(1.0, 0.0, 0.5, 0.0, 1.0, -2.5))


class PosingWorker(CertifyingWorker):
    """Certifies its tile AND, on the LAST address, revises the pose.

    The roster has no pose-minting family, and recovery re-earns a tail by
    RE-RUNNING work — so a revision can only reach the crash-cut tail
    through a worker. Writing it from the last-firing key alone is what
    puts it past the memo's final frame.
    """

    route = "unit-posing"
    LAST = tile_key(*ADDRESSES[-1], "main")

    def run(self, view, identity, progress):
        result = super().run(view, identity, progress)
        if self.key != self.LAST:
            return result
        return dataclasses.replace(result, writes=result.writes + (
            Write(REVISED_POSE.resource_key(), REVISED_POSE),))


def test_a_re_earned_tail_keeps_the_write_order_the_live_pose_is_read_from(
        tmp_path: Path) -> None:
    """Recovery, pinned on ORDER — added by the W3 review (2026-08-23).

    THE FORK: W3 made record order load-bearing for the first time
    (``StoreIndex.live_poses`` IS the store's write order), and pinned it
    only for the in-process memo round trip. Every durability and replay
    gate compares ``state_bytes()``, which materialises ``sorted(...)``
    and is therefore order-BLIND — so a re-earned tail that commits an
    extent's poses in a different order would produce byte-identical
    state and a DIFFERENT live pose with nothing failing. The three
    verdict durability arms cannot see it either: they run ``run_channel``,
    which the same gate proves carries no revision at all.

    So: two poses of one extent, committed in an order their keys do not
    have, with the second committed in the frame the cut removes. The
    staging is asserted rather than assumed — the reopened store must be
    MISSING the revision before recovery runs.
    """
    factories = Factories(worker_class=PosingWorker)
    with make_session(tmp_path, "ordered", snapshot_every=2) as session:
        seed_addressed(session)
        make_orchestrator(session, RECIPE, factories, workers=1).run()
        before = tuple(session.store.records())
        live = StoreIndex.build(session.store).live_pose(WINDOW)
    assert live == REVISED_POSE.resource_key(), (
        "the revision must be the extent's last committed pose")
    assert before != tuple(sorted(before)), (
        "the fixture must write in an order its keys do not have, or it "
        "cannot tell a sorted walk from a write-order one")

    cut_last_frame(tmp_path / "ordered")
    with make_session(tmp_path, "ordered", snapshot_every=2) as session:
        assert session.store.get(REVISED_POSE.resource_key()) is None, (
            "the cut left the revision in the memo: the staging is stale "
            "and this test would pin the memo path a second time")
        make_orchestrator(session, RECIPE,
                          Factories(worker_class=PosingWorker),
                          workers=1).run()
        assert tuple(session.store.records()) == before, (
            "recovery handed the records back in a different order")
        assert StoreIndex.build(session.store).live_pose(WINDOW) == live


def test_a_tail_marker_with_no_commit_replays_as_a_non_committing_pass(
        tmp_path: Path) -> None:
    """The crashed tail's own shape, and the ruling for it (2026-08-16).

    A crash between a dispatch and its commit leaves a marker with
    nothing after it. That is a NON-COMMITTING pass — the same thing a
    failed pull pass is mid-ordering — replayed for its in-memory
    effects and no more: recovery never invents a commit the ordering
    did not record, and whatever work is genuinely still open re-arms
    live afterwards. Staged by appending the marker a crash would have
    left, which is exact where killing a process is not.
    """
    ordering, state = _recorded(tmp_path, "torn", Factories(), workers=1)
    marker = next(entry for entry in ordering if is_marker(entry))
    with open(tmp_path / "torn" / JOURNAL_NAME, "ab") as handle:
        handle.write(marker.encode() + b"\n")

    with make_session(tmp_path, "torn") as session:
        before = session.store.commit_seq
        outcome = make_orchestrator(session, RECIPE, Factories(),
                                    workers=1).run()
        # The pass it names has nothing to contribute — its tile was
        # certified by the very commit before the crash — so it arms
        # nothing, commits nothing, and is not an error.
        assert session.store.commit_seq == before
        assert session.store.state_bytes() == state
        assert session.store.journal_position == len(ordering) + 1
        # A marker that armed NOTHING still settles: no proposal will
        # ever hold it, so the walk pays it where it is met.
        assert session.store.outstanding_dispatches == 0
    assert outcome.status == "open"


def test_a_recovered_state_re_opens_as_an_exact_no_op(tmp_path: Path) -> None:
    """Once re-earned, the memo covers the record again and stays there."""
    _ordering, _state = _recorded(tmp_path, "settled", Factories(), workers=1,
                                  snapshot_every=2)
    cut_last_frame(tmp_path / "settled")
    with make_session(tmp_path, "settled") as session:
        make_orchestrator(session, RECIPE, Factories(), workers=1).run()
    with make_session(tmp_path, "settled") as session:
        assert session.store.journal_position == len(session.store.ordering())
        outcome = make_orchestrator(session, RECIPE, Factories(),
                                    workers=1).run()
    assert outcome.commits == 0 and outcome.fires == 0


def test_recovery_settles_every_mark_it_replays(tmp_path: Path) -> None:
    """A re-earned tail leaves the store waiting on NOTHING.

    Recovery re-marks each dispatch it replays — it must, because the
    marker's position IS the snapshot prefix the fire read, so the walk
    has to reproduce the same outstanding-accounting the recording had
    at each position. What it also owes is the other half: settling the
    marks it wrote as each replayed pass is reaped. Without it the count
    only rises, and it is never read again as anything but "a dispatch
    is in flight" — see the cadence pin below for what that costs.
    """
    ordering, _state = _recorded(tmp_path, "settled-marks", Factories(),
                                 workers=1, snapshot_every=2)
    cut_last_frame(tmp_path / "settled-marks")
    with make_session(tmp_path, "settled-marks", snapshot_every=2) as session:
        assert len(ordering) - session.store.journal_position > 0, (
            "the cut removed no entries at all")
        make_orchestrator(session, RECIPE, Factories(), workers=1).run()
        assert session.store.outstanding_dispatches == 0, (
            "recovery left dispatch marks unsettled")


def test_the_frame_cadence_survives_a_recovery(tmp_path: Path) -> None:
    """What the leak COSTS: the memo, for the rest of the run.

    A frame is taken only at a clean cut through the dispatches
    (``core.store._frame``), so one unsettled mark disables the cadence
    outright — and a second crash then re-earns the entire session tail
    rather than the one cadence window the store promises
    (``DEFAULT_SNAPSHOT_EVERY``). Waste, never wrongness, which is
    exactly why nothing else would ever notice.
    """
    _ordering, _state = _recorded(tmp_path, "cadence", Factories(),
                                  workers=1, snapshot_every=2)
    cut_last_frame(tmp_path / "cadence")
    framed = frame_count(tmp_path / "cadence")
    with make_session(tmp_path, "cadence", snapshot_every=2) as session:
        make_orchestrator(session, RECIPE, Factories(), workers=1).run()
        for index in range(6):
            _scratch_commit(session, index)
        # Six commits at a cadence of two: three frames, and the close
        # has not run yet — so this counts the CADENCE and not the flush.
        assert frame_count(tmp_path / "cadence") - framed >= 3, (
            "no cache frame was taken after the recovery: the cadence is off")


# --------------------------------------------------- the pre-marker refusal

def test_a_pre_marker_state_refuses_at_the_schema_gate(
        tmp_path: Path) -> None:
    """R3-lawful: no migration, no dual-mode reader, and it says why.

    A pre-marker journal speaks a different ordering vocabulary, and a
    pooled one cannot be replayed exactly at ALL — reading it under this
    build would be claiming a guarantee the file cannot support.
    """
    _recorded(tmp_path, "old", Factories(), workers=1)
    path = tmp_path / "old" / JOURNAL_NAME
    lines = path.read_bytes().split(b"\n")
    lines[0] = lines[0].replace(f'"schema_version":{SCHEMA_VERSION}'.encode(),
                                b'"schema_version":6')
    path.write_bytes(b"\n".join(lines))
    with pytest.raises(StoreError, match="schema version 6"):
        Store.open(tmp_path / "old", registry())

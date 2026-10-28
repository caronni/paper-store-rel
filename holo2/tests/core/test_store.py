"""Store durability under journal-authoritative persistence (F-16).

These are the H1 gate properties (WORKPLAN H1), restated against the
layout that replaced the rewritten envelope: the durable STATE may not
depend on how work was grouped into runs, and a crash at any point leaves
either the previous durable state or the new one — never a torn mixture,
and never work that was not committed.

What moved with F-16:

* the comparison oracle is ``Store.state_bytes()``, the state as a VALUE.
  The cache is append-only frames, so two runs that reach the same state
  legitimately hold different bytes on disk; "the same state" is what the
  gates ever meant.
* the JOURNAL is the durable record — one batch id per commit, fsynced at
  the commit — so a crash leaves it ahead of the cache, and the tail is
  re-earned (by the engine, ``test_crash_recovery_e2e``) or, if a re-fold
  produces a different batch there, truncated.
* the load path validates nothing it reads (rider r1). The strict-load
  battery that used to live here is down to the GATE: schema version,
  family manifest, session identity by value, and cache-vs-journal
  position sanity.
"""
from __future__ import annotations

import itertools
import os
from inspect import signature
from pathlib import Path
from typing import Callable

import numpy as np
import pytest

from holo2.core.cache import CACHE_NAME
from holo2.core.commit import CommitBatch, CommitEngine, SpendProposal, Write
from holo2.core.journal import JournalError, JOURNAL_NAME, read_journal
from holo2.core.records import BlobRef
from holo2.core.cache import CacheReader
from holo2.core.store import (DEFAULT_SNAPSHOT_EVERY, LEGACY_ENVELOPE_NAME,
                              Store, StoreError)
from conftest import (crash, CAPTURE_SHA, MOVED_POLICIES, POSE, REGION, WINDOW,
                      MintRef, PoseRecord, RegionRecord,
                      TileRecord, WindowRecord, WindowStatus,
                      capture_key, ground, ground_batch, make_pose,
                      make_session, make_window,
                      registry, subscribe, tile_key, wid)

_TILE = tile_key(0, 0, 0, "K")
_IDENTITY = ((_TILE, 1),)


def toy_batches(store: Store) -> tuple[CommitBatch, ...]:
    """A scripted workload: blobs, records, a spend, a subscription.

    Deterministic and store-independent in content: blob refs are content
    addresses, so the same payloads produce the same batches in any run.

    Its first batch is the fixture GROUND (capture, region, window):
    since F-07's relational half a region names its capture and a pose
    names its window, so the workload lays the same chain a real run does.
    """
    bits_ref = store.put_array(np.arange(6, dtype=np.uint8))
    base = ground_batch("window")
    return (
        CommitBatch(
            writes=base.writes, blobs=base.blobs,
            subscriptions=(subscribe("w-tile", _TILE),),
        ),
        CommitBatch(
            writes=(
                Write(_TILE, TileRecord(observed_by=("cap:8/1",))),
                Write(POSE, make_pose()),
            ),
            spends=(SpendProposal(wid("win-1"), "chain", _IDENTITY,
                                  "accepted"),),
        ),
        CommitBatch(
            writes=(Write(_TILE, TileRecord(
                minting=MintRef(POSE, "scan", "fixture-decoder"),
                bits_ref=bits_ref, metadata_bit=1,
                observed_by=("cap:8/1",))),),
        ),
    )


def _run_all(state_dir: Path) -> None:
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        for batch in toy_batches(store):
            engine.apply(batch)


def _run_stepwise(state_dir: Path) -> None:
    Store.create(state_dir, make_session(), registry()).close()
    for index in range(3):
        with Store.open(state_dir, registry()) as store:
            CommitEngine(store).apply(toy_batches(store)[index])


def _durable(state_dir: Path) -> tuple[bytes, dict, bytes]:
    with Store.open(state_dir, registry()) as store:
        return (store.state_bytes(),
                {str(key): version for key, version in store.versions().items()},
                (state_dir / "blobs.bin").read_bytes())


def test_batching_invariance_one_run_vs_reopen_per_commit(tmp_path: Path) -> None:
    _run_all(tmp_path / "single")
    _run_stepwise(tmp_path / "stepped")
    single_state, single_versions, single_blobs = _durable(tmp_path / "single")
    stepped_state, stepped_versions, stepped_blobs = _durable(tmp_path / "stepped")
    assert single_state == stepped_state
    assert single_versions == stepped_versions == {
        str(capture_key(CAPTURE_SHA)): 1, str(REGION): 1, str(WINDOW): 1,
        str(_TILE): 2, str(POSE): 1}
    assert single_blobs == stepped_blobs
    # And the ORDERING is the same fold either way: batch ids are content
    # names, so the journal — not just the state — is byte-identical.
    assert ((tmp_path / "single" / JOURNAL_NAME).read_bytes()
            == (tmp_path / "stepped" / JOURNAL_NAME).read_bytes())


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_disjoint_batches_commute(tmp_path: Path, order: tuple[int, ...]) -> None:
    """Independent work items may be committed in any order (L10)."""
    batches = []
    for index in range(3):
        # Three DIFFERENT windows: the extent is what distinguishes them,
        # because the extent is part of what a window IS.
        record = make_window(WindowStatus.ACTIVE,
                             extent_cells=(index * 160, 0, index * 160 + 160,
                                           160))
        batches.append(CommitBatch(
            writes=(Write(record.resource_key(), record),)))
    state_dir = tmp_path / f"order-{''.join(str(i) for i in order)}"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "region")          # the region three windows stand on
        for index in order:
            engine.apply(batches[index])
        state = store.state_bytes()
    reference = tmp_path / "reference"
    with Store.create(reference, make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "region")
        for batch in batches:
            engine.apply(batch)
        assert state == store.state_bytes()


def test_crash_between_blob_append_and_the_commit(tmp_path: Path) -> None:
    """The blob is an inert orphan; the re-armed work dedups onto it."""
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry())
    ref = store.put_array(np.arange(6, dtype=np.uint8))
    del store                                   # crash before any commit
    crash(state_dir)

    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 0
        assert reopened.keys() == ()
        assert reopened.blobs.contains(ref.sha256)     # orphan, referenced by nobody
        engine = CommitEngine(reopened)
        for batch in toy_batches(reopened):            # the work re-arms
            engine.apply(batch)
        assert reopened.blobs.contains(ref.sha256)     # re-used, not re-appended

    clean = tmp_path / "clean"
    _run_all(clean)
    assert _durable(state_dir)[0] == _durable(clean)[0]
    # Deduped, not duplicated: the re-armed work re-derived the orphan's
    # own content address, so the crashed lineage's sidecar carries exactly
    # the blobs a clean run carries — the same frames in a different order.
    assert len(_durable(state_dir)[2]) == len(_durable(clean)[2])


def test_a_crash_leaves_the_journal_ahead_of_the_memo(tmp_path: Path) -> None:
    """The commits are RECORDED and not yet memoised — F-16's whole shape.

    The old envelope lost them outright. Now the journal holds every one,
    fsynced at its commit, and what the reopened store has is a memo that
    covers none of them: the state to re-earn, and the exact ordering to
    re-earn it in.
    """
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(),
                         snapshot_every=100)
    engine = CommitEngine(store)
    recorded = [engine.apply(batch).batch_id for batch in toy_batches(store)]
    assert store.commit_seq == 3                 # in memory
    del store                                    # crash before the cache frame
    crash(state_dir)

    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 0          # the memo covers nothing
        assert reopened.keys() == ()             # unframed work is invisible
        assert list(reopened.ordering()) == recorded      # the record stands
        # Re-earning it is the engine's (the e2e); at this layer the
        # re-derived batches AGREE with the record, so the journal is not
        # written twice and the state lands where it landed before.
        engine = CommitEngine(reopened)
        for batch in toy_batches(reopened):
            engine.apply(batch)
        assert list(reopened.ordering()) == recorded

    clean = tmp_path / "clean"
    _run_all(clean)
    assert _durable(state_dir)[0] == _durable(clean)[0]
    assert ((state_dir / JOURNAL_NAME).read_bytes()
            == (clean / JOURNAL_NAME).read_bytes())


def test_a_divergent_re_fold_is_refused_the_journal_stands(
        tmp_path: Path) -> None:
    """Integrator ruling 2026-08-14: the journal is NEVER rewritten.

    The first cut truncated the unearned tail silently ("a different
    fold owns it"). Overruled: the journal is the AUTHORITATIVE history
    — quietly erasing the record that three commits happened, because
    this run's inputs re-derive differently, is a history rewrite. A
    divergent fold refuses loudly, naming both batch ids and the
    remedy; the recorded tail stands byte-for-byte, and truncation is
    only ever the operator's explicit `rm` of the state directory.
    """
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(),
                         snapshot_every=100)
    engine = CommitEngine(store)
    for batch in toy_batches(store):
        engine.apply(batch)
    del store
    crash(state_dir)

    with Store.open(state_dir, registry()) as reopened:
        assert len(reopened.ordering()) == 3
        with pytest.raises(JournalError,
                           match="cannot reproduce the recorded tail"):
            CommitEngine(reopened).apply(ground_batch("region"))
    _header, ordering = read_journal(state_dir / JOURNAL_NAME)
    assert len(ordering) == 3, "the recorded history stands byte-for-byte"


def _memo_position(state_dir: Path) -> int:
    """The durable MEMO's covered commit position, read off the file.

    The mid-run peek the cadence tests need is a READ of the memo, not a
    second writer: post-F-19 a live state dir has ONE Store, so the peek
    goes straight to the cache file through the same reader `open` uses.
    """
    header, _ordering = read_journal(state_dir / JOURNAL_NAME)
    return CacheReader.load(state_dir / CACHE_NAME, header,
                            registry()).position


def test_the_default_cadence_is_the_ruled_512_spelled_once(
        tmp_path: Path) -> None:
    """OR-6, RULED 2026-08-12 (W-B/B11): 512 commits per cache frame, fsync on.

    Both halves are pinned as VALUES, and the relays are pinned as the
    same value: the ruling's "no second spelling" is exactly the property
    that a literal reappearing in the session or the CLI would break, and
    it cannot be seen from any one of those files alone. ``512`` costs no
    decode result (M-3.4 measured every cadence to identical certificates,
    payload and counters); under F-16 what it buys is a bounded re-earn
    window, since the journal — not the frame — is what makes a commit
    durable.
    """
    from holo2 import cli

    assert DEFAULT_SNAPSHOT_EVERY == 512
    # The engine's ``open_session`` relay is not named here — a core test
    # may not import engine (``test_layering``) — but it is the same
    # imported constant, and the CLI defaults below are what an operator
    # actually gets.
    relays = [signature(Store.create), signature(Store.open),
              signature(Store.open_or_create), signature(Store.__init__),
              signature(cli.open_receiver), signature(cli.decode)]
    for relay in relays:
        assert relay.parameters["snapshot_every"].default == (
            DEFAULT_SNAPSHOT_EVERY)
        assert relay.parameters["fsync"].default is True

    # And the cadence is a cadence: the MEMO lags, the record does not.
    store = Store.create(tmp_path / "state", make_session(), registry())
    CommitEngine(store).apply(toy_batches(store)[0])
    assert _memo_position(tmp_path / "state") == 0
    assert len(read_journal(tmp_path / "state" / JOURNAL_NAME)[1]) == 1
    store.close()                                  # a clean exit is memoised
    with Store.open(tmp_path / "state", registry()) as reopened:
        assert reopened.commit_seq == 1


def test_the_cadence_frames_the_memo(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(), snapshot_every=2)
    engine = CommitEngine(store)
    batches = toy_batches(store)
    engine.apply(batches[0])
    assert _memo_position(state_dir) == 0             # below the cadence
    engine.apply(batches[1])
    assert _memo_position(state_dir) == 2             # a frame landed
    engine.apply(batches[2])
    store.close()                                     # close frames the tail
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 3


def test_frames_are_appended_never_rewritten(tmp_path: Path) -> None:
    """Whole-file rewrite is ABOLISHED: every frame is a suffix (F-16).

    The measured motivation, on one real sheet: a 476 MB envelope rewritten
    every 512 commits, of which 6.6 MB was facts.
    """
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(), snapshot_every=1)
    engine = CommitEngine(store)
    sizes = [(state_dir / CACHE_NAME).stat().st_size]
    prefixes = [(state_dir / CACHE_NAME).read_bytes()]
    for batch in toy_batches(store):
        engine.apply(batch)
        sizes.append((state_dir / CACHE_NAME).stat().st_size)
        prefixes.append((state_dir / CACHE_NAME).read_bytes())
    store.close()
    assert sizes == sorted(sizes) and len(set(sizes)) == len(sizes)
    for earlier, later in zip(prefixes, prefixes[1:]):
        assert later.startswith(earlier)          # append-only, byte for byte


def test_subscriptions_are_derived_from_the_spend_rows(tmp_path: Path) -> None:
    """Not stored: a read-set IS its spend identity's keys (F-16 rider).

    The two were 143 MB of the old envelope — the same keys, written once
    per spend row and once per subscription. The declaration a commit
    carries and the identity it spends come from one read of one worker's
    keys, so the load rebuilds the table instead of storing it.
    """
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "window")
        engine.apply(CommitBatch(
            writes=(Write(_TILE, TileRecord()),),
            spends=(SpendProposal(wid("win-1"), "chain", _IDENTITY,
                                  "accepted"),),
            subscriptions=(subscribe("win-1", _TILE),)))
        declared = store.subscriptions()
    assert declared == {wid("win-1"): (_TILE,)}
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.subscriptions() == declared
        assert CACHE_NAME and b"subscription" not in (
            state_dir / CACHE_NAME).read_bytes()


def test_subscription_reads_one_workers_row(tmp_path: Path) -> None:
    """The per-worker accessor (H4-PLAN W-S audit wart) vs the whole copy.

    ``store.subscription(worker_id)`` replaces ``orchestrator._propose``'s
    whole-table dict copy per fire (the wart named at ``store.py:368-369``
    / ``orchestrator.py:737-742``) with a single-row read. It must return
    exactly the row ``subscriptions()`` would hand back under that key —
    an unknown worker reads as the empty read-set, the same "absent"
    convention ``get``/``version`` already use — and ``subscriptions()``
    itself keeps copying the whole table, unaffected by the accessor
    standing beside it.
    """
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "window")
        engine.apply(CommitBatch(
            writes=(Write(_TILE, TileRecord()),),
            spends=(SpendProposal(wid("win-1"), "chain", _IDENTITY,
                                  "accepted"),),
            subscriptions=(subscribe("win-1", _TILE),)))
        whole = store.subscriptions()
        assert store.subscription(wid("win-1")) == (_TILE,) == whole[wid("win-1")]
        assert store.subscription(wid("nobody")) == ()      # unknown -> empty
        # The whole-table copy is a copy: mutating it cannot move the
        # store's own state, so the accessor still sees the real row.
        whole.pop(wid("win-1"))
        assert store.subscription(wid("win-1")) == (_TILE,)
        assert store.subscriptions() == {wid("win-1"): (_TILE,)}
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.subscription(wid("win-1")) == (_TILE,)
        assert reopened.subscription(wid("nobody")) == ()


def test_a_clean_close_flushes_the_tail_zero_reearn(tmp_path: Path) -> None:
    """Cache rider (H4-PLAN W-S, user 2026-08-15): every CLEAN close flushes
    the tail, not only terminal close — the <=512-commit resume tail
    becomes a CRASH-ONLY artifact.

    Three commits at cadence 2: a periodic frame lands at position 2, one
    commit stays uncached past it, then the store closes cleanly (the
    same path ``SessionContext.close()`` reaches from the CLI's
    ``finally`` on every graceful exit — an operator interrupt or a
    ``--complete`` deferral included, since both let ``orchestrator.run``
    return or raise normally through it; only a hard crash skips this
    method). The memo's recorded position must equal the journal's
    length right after close — zero tail — unlike an actual crash at the
    same point (``test_a_crash_leaves_the_journal_ahead_of_the_memo``),
    where the memo stays behind until replay re-earns it.
    """
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(),
                         snapshot_every=2)
    engine = CommitEngine(store)
    for batch in toy_batches(store):
        engine.apply(batch)
    journal_length = len(read_journal(state_dir / JOURNAL_NAME)[1])
    assert journal_length == 3
    assert _memo_position(state_dir) == 2              # the periodic frame only
    store.close()                                        # the clean-shutdown path
    assert _memo_position(state_dir) == journal_length    # zero tail to re-earn
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == journal_length
        assert len(reopened.ordering()) == journal_length
        # Nothing left to re-earn: an open right after a clean close is
        # already at the journal's tail, with no replay in between.
        assert reopened.commit_seq == len(reopened.ordering())


def test_the_ledger_is_taken_back_unfolded(tmp_path: Path) -> None:
    """A durable row is the fold's RESULT: reloading may not re-count it."""
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "window")
        for version in (1, 2):
            engine.apply(CommitBatch(
                writes=(Write(_TILE, TileRecord(
                    observed_by=("cap:8/1",) if version == 1
                    else ("cap:8/1", "cap:9/1"))),),
                spends=(SpendProposal(wid("win-1"), "chain",
                                      ((_TILE, version),), "accepted",
                                      exposures=1),)))
        held = store.ledger.held(wid("win-1"), "chain")
    assert held is not None and held.attempts == 2 and held.exposures == 2
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.ledger.held(wid("win-1"), "chain") == held


def test_failed_frame_leaves_the_previous_cache_intact(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cadence 1 is named: what fails here is the per-commit cache frame."""
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    batches = toy_batches(store)
    engine.apply(batches[0])
    before = (state_dir / CACHE_NAME).read_bytes()

    def exploding_write(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash while framing")

    monkeypatch.setattr(store._cache, "_append", exploding_write)
    with pytest.raises(OSError):
        engine.apply(batches[1])
    monkeypatch.undo()
    del store
    crash(state_dir)

    assert (state_dir / CACHE_NAME).read_bytes() == before
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 1
        assert reopened.get(_TILE) is None
        # The commit the frame could not memoise is still RECORDED: the
        # journal is the durable half, and the tail is what replay earns.
        assert len(reopened.ordering()) == 2


def test_a_torn_frame_is_truncated_and_the_prefix_stands(tmp_path: Path) -> None:
    """A crash mid-append leaves a valid prefix; the cache is not repaired."""
    state_dir = tmp_path / "state"
    store = Store.create(state_dir, make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    batches = toy_batches(store)
    engine.apply(batches[0])
    whole = (state_dir / CACHE_NAME).read_bytes()
    engine.apply(batches[1])
    torn = (state_dir / CACHE_NAME).read_bytes()
    del store
    crash(state_dir)
    with open(state_dir / CACHE_NAME, "wb") as handle:
        handle.write(torn[:len(torn) - 8])           # the last frame, cut short

    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 1
        assert reopened.get(POSE) is None
    assert (state_dir / CACHE_NAME).read_bytes()[:len(whole)] == whole


def test_a_record_and_its_version_are_one_row(tmp_path: Path) -> None:
    """One table, not two dicts with a keyset invariant nobody enforced.

    The reads are projections of the same entry, so a record cannot exist
    without its version or vice versa, and ``keys()`` keeps its sorted
    ordering guarantee.
    """
    with Store.create(tmp_path / "state", make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "window")          # the window the pose stands on
        engine.apply(CommitBatch(writes=(
            Write(_TILE, TileRecord()),
            Write(POSE, make_pose()))))

        assert set(store.keys()) >= {_TILE, POSE}
        assert store.keys() == tuple(sorted(store.keys()))
        assert set(store.records()) == set(store.versions()) == set(store.keys())
        assert store.records()[_TILE] == store.get(_TILE)
        assert store.versions()[_TILE] == store.version(_TILE) == 1
        # An absent key has no record and reads as version 0 (ABSENT).
        absent = tile_key(9, 9, 9, "K")
        assert store.get(absent) is None and store.version(absent) == 0
        assert absent not in store.records() and absent not in store.versions()
        # The projections are copies: mutating one cannot move the table.
        store.records().pop(_TILE)
        assert store.get(_TILE) is not None


def test_create_refuses_to_overwrite_a_session(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()
    with pytest.raises(StoreError, match="already holds"):
        Store.create(state_dir, make_session(), registry())


def test_a_pre_f16_state_directory_refuses_by_name(tmp_path: Path) -> None:
    """Freshness doctrine: the old layout is not read, and never quietly."""
    state_dir = tmp_path / "old"
    state_dir.mkdir()
    (state_dir / LEGACY_ENVELOPE_NAME).write_text('{"magic":"holo2-state"}')
    for call in (lambda: Store.open(state_dir, registry()),
                 lambda: Store.create(state_dir, make_session(), registry()),
                 lambda: Store.open_or_create(state_dir, make_session(),
                                              registry())):
        with pytest.raises(StoreError, match="pre-F-16 state.json") as caught:
            call()
        assert "no migration decoders" in str(caught.value)


def test_open_refuses_a_directory_that_is_not_a_session(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StoreError, match="no journal"):
        Store.open(empty, registry())


def test_the_identity_can_be_read_before_the_state_is_owned(
        tmp_path: Path) -> None:
    """C5 (RULINGS G6): the read-first surface, and what it does NOT take.

    Prevents the fork where a resume has to be TOLD what it already
    holds: without this, ``format_row_id`` was reachable only from
    inside :meth:`Store.open`, which needs the identity to open — so
    ``--format`` could never become optional and the persisted string
    stayed decoration.

    The two properties the CLI leans on are asserted here rather than
    inferred: the answer is the identity the state was created with, and
    the read takes NO LOCK — so it works while a session is live, which
    is exactly when an operator asks it. (``Store.open`` holds the lock
    for the length of the ``with``; a peek that acquired one would
    refuse there, and the test would fail.)
    """
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as live:
        assert Store.peek_identity(state_dir, registry()) == live.session
    assert Store.peek_identity(state_dir, registry()) == make_session()


def test_a_peek_refuses_what_an_open_would_refuse(tmp_path: Path) -> None:
    """The same GATE, so an operator meets one refusal and not two.

    Prevents a read-first surface that is LAXER than the open it
    precedes — which would resolve a format out of a state this build
    cannot open, and act on it. The three classes: not a session at all,
    a torn starting point (a crash inside ``create``), and a header this
    build refuses (here: a moved schema version).
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StoreError, match="no journal"):
        Store.peek_identity(empty, registry())

    torn = tmp_path / "torn"
    torn.mkdir()
    (torn / JOURNAL_NAME).write_bytes(b'{"magic":"holo2-journal"')
    with pytest.raises(StoreError, match="no starting point"):
        Store.peek_identity(torn, registry())

    state_dir = tmp_path / "state"
    _run_all(state_dir)
    _corrupt_header(state_dir, lambda h: h.__setitem__("schema_version", 99))
    with pytest.raises(StoreError, match="schema version"):
        Store.peek_identity(state_dir, registry())


@pytest.mark.parametrize("index", range(len(MOVED_POLICIES)))
def test_open_refuses_a_moved_policy_by_value(tmp_path: Path,
                                              index: int) -> None:
    """The executable policy binds BY VALUE (the identity law).

    A moved gate, a moved price, a different provider binding and a
    RE-ORDERED one (order is arbitration) each fork the lineage —
    ``conftest.MOVED_POLICIES`` is those four.
    """
    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()
    with pytest.raises(StoreError, match="session identity differs"):
        Store.open(state_dir, registry(),
                   expect_session=MOVED_POLICIES[index])


def test_open_accepts_the_same_policy_restated(tmp_path: Path) -> None:
    """Equality is by value: an equal policy is the same lineage."""
    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()
    Store.open(state_dir, registry(), expect_session=make_session()).close()


def _corrupt_header(state_dir: Path, mutate: Callable[[dict], None]) -> None:
    import json
    lines = (state_dir / JOURNAL_NAME).read_bytes().split(b"\n")
    header = json.loads(lines[0])
    mutate(header)
    lines[0] = json.dumps(header).encode()
    (state_dir / JOURNAL_NAME).write_bytes(b"\n".join(lines))


@pytest.mark.parametrize("mutate,message", [
    (lambda h: h.__setitem__("magic", "something-else"), "not a holo2 journal"),
    (lambda h: h.__setitem__("schema_version", 99), "schema version"),
    (lambda h: h.__setitem__("schema_version", "1"), "must be an integer"),
    (lambda h: h.__setitem__("invented_field", 1), "unknown starting-point"),
    (lambda h: h.pop("families"), "missing starting-point"),
    # R3: the schema identity is the registry MANIFEST, and a mismatch
    # names the family that moved.
    (lambda h: h.__setitem__("families", [["RegionRecord", 1]]),
     "RegionRecord: state v1 != build v4"),
    (lambda h: h["families"].append(["Invented", 1]),
     "Invented v1: this build registers no such family"),
    (lambda h: h.__setitem__("session_type", "OtherIdentity"),
     "this build's is 'SessionIdentity'"),
    (lambda h: h["session"].__setitem__("invented", 1), "unknown field"),
])
def test_the_gate_refuses_a_starting_point_that_is_not_this_builds(
        tmp_path: Path, mutate: Callable[[dict], None], message: str) -> None:
    """The whole of the open-path audit: what the fold STARTED as (rider r1)."""
    state_dir = tmp_path / "state"
    _run_all(state_dir)
    _corrupt_header(state_dir, mutate)
    with pytest.raises(StoreError, match=message):
        Store.open(state_dir, registry())


def test_a_deleted_cache_is_an_empty_memo_and_the_journal_stands(
        tmp_path: Path) -> None:
    """Every refusal in the store offers this remedy; it has to be true.

    "Delete the cache and the fold re-derives" means a missing memo is a
    memo of NOTHING — position zero, whole journal a tail — never an
    error. Re-earning that tail is the engine's (the crash-recovery e2e).
    """
    state_dir = tmp_path / "state"
    _run_all(state_dir)
    recorded = read_journal(state_dir / JOURNAL_NAME)[1]
    (state_dir / CACHE_NAME).unlink()
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 0 and reopened.keys() == ()
        assert reopened.ordering() == recorded
        engine = CommitEngine(reopened)
        for batch in toy_batches(reopened):        # the fold re-derives
            engine.apply(batch)
        assert reopened.ordering() == recorded
    clean = tmp_path / "clean"
    _run_all(clean)
    assert _durable(state_dir)[0] == _durable(clean)[0]


def test_a_cache_from_another_session_is_refused(tmp_path: Path) -> None:
    """The cache gate: a memo must be a memo OF this fold."""
    _run_all(tmp_path / "one")
    with Store.create(tmp_path / "two", make_session(providers=("other-v0",)),
                      registry()) as other:
        pass
    (tmp_path / "one" / CACHE_NAME).write_bytes(
        (tmp_path / "two" / CACHE_NAME).read_bytes())
    with pytest.raises(StoreError, match="memoises a different session"):
        Store.open(tmp_path / "one", registry())


def test_a_cache_claiming_more_commits_than_the_journal_is_refused(
        tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _run_all(state_dir)
    journal = (state_dir / JOURNAL_NAME).read_bytes()
    (state_dir / JOURNAL_NAME).write_bytes(
        b"\n".join(journal.split(b"\n")[:2]) + b"\n")     # one commit recorded
    with pytest.raises(StoreError, match="the memo cannot know more"):
        Store.open(state_dir, registry())


def test_load_refuses_when_a_referenced_blob_is_missing(tmp_path: Path) -> None:
    """And says WHOSE record named it, and that this is INCOMPLETE (F-13).

    The one open-path check rider r1 keeps, because it is a statement
    about the SIDECAR rather than the store auditing its own memo: the
    verdict is the cache doctrine's — incomplete, not corrupt, remedy =
    re-derive.
    """
    state_dir = tmp_path / "state"
    _run_all(state_dir)
    (state_dir / "blobs.bin").unlink()
    with pytest.raises(StoreError, match="absent from the sidecar") as caught:
        Store.open(state_dir, registry())
    message = str(caught.value)
    named = message.split("named by ")[1].split(")")[0]
    assert named in (str(REGION), str(_TILE))
    assert "INCOMPLETE, not corrupt" in message
    assert "decode again from the scans" in message


def test_records_may_not_be_stored_under_a_foreign_kind(tmp_path: Path) -> None:
    with Store.create(tmp_path / "state", make_session(), registry()) as store:
        with pytest.raises(Exception, match="may not be stored under kind"):
            CommitEngine(store).apply(CommitBatch(writes=(
                Write(REGION, TileRecord()),)))


def test_blob_ref_equality_is_content_equality(tmp_path: Path) -> None:
    with Store.create(tmp_path / "state", make_session(), registry()) as store:
        first = store.put_array(np.arange(4, dtype=np.uint8))
        second = store.put_array(np.arange(4, dtype=np.uint8))
        assert first == second
        assert first != BlobRef(first.sha256, first.length_bytes)


def test_the_state_directory_holds_exactly_the_four_files(
        tmp_path: Path) -> None:
    """Journal, cache, sidecar — and the trace only if sampling asked."""
    state_dir = tmp_path / "state"
    _run_all(state_dir)
    assert sorted(path.name for path in state_dir.iterdir()) == [
        "blobs.bin", CACHE_NAME, JOURNAL_NAME]
    assert not (state_dir / "state.json").exists()
    assert os.path.getsize(state_dir / JOURNAL_NAME) < os.path.getsize(
        state_dir / CACHE_NAME)


def test_first_write_order_survives_the_memo(tmp_path: Path) -> None:
    """The frame's rows are FIRST-WRITE order, so a resume seeds the same.

    THE FORK (W3, RULING I3, 2026-08-23): ``_frame`` used to write
    ``sorted(self._dirty)``. Inside one frame — up to ``snapshot_every``
    commits wide — that replaced write order with key order, so a store
    reopened from the memo handed its records back in a DIFFERENT order
    than the run that wrote them. Nothing consumed that order until
    ``solve.tilemap.StoreIndex.live_poses`` did: "the latest committed
    pose for that extent wins" is read off exactly this, and under the
    sorted frame a resume could promote a pose the run had superseded.

    The three poses below share one window and are committed in an order
    their KEYS do not have (the affine's third term descends, and the key
    carries the affine), so a sorted frame is observably not this one.
    All three land in a single frame: the default cadence is 512.
    """
    poses = [make_pose(native_affine=(6.0, 0.0, term, 0.0, 6.0, 2.0))
             for term in (30.0, 20.0, 10.0)]
    written = [pose.resource_key() for pose in poses]
    assert written != sorted(written), (
        "the fixture must commit in an order the keys do not have, or it "
        "cannot tell the two framings apart")

    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        ground(engine, "window")
        for pose in poses:
            engine.apply(CommitBatch(
                writes=(Write(pose.resource_key(), pose),)))
        live = [key for key in store.records() if key.kind == "pose"]
    assert live == written

    with Store.open(state_dir, registry()) as reopened:
        resumed = [key for key in reopened.records() if key.kind == "pose"]
    assert resumed == written, (
        "the memo handed the poses back in a different order than they "
        "were committed in")

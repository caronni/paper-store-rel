"""The publication-order law (DESIGN §6, user ruling 2026-08-11).

A commit derives and validates its COMPLETE delta — records, key↔record
agreement, collection membership, blob references — before mutating
anything; store and resource table then publish from that one delta; no
fallible callback runs after durable publication.

The probe carried here is the review's own (HARDENING-SYSTEMIC-REVIEW,
"P0 — Commit publication is not atomic"): a structurally valid
``EvidenceObservation`` under ``ResourceKey("evidence", ("bad",))``. It
used to be REFUSED by the API and DURABLE in the state (``state.json``
back then; a cache frame now) — the
collection callback parsed the key after ``Store.apply_committed`` — and
the malformed fact then poisoned the lineage permanently: ``Store.open``
accepted it and every ``CommitEngine`` built on it raised while rebuilding
the resource table.

The restart tests are the review's second requirement: fail at each point
a commit can fail — validation, blob materialisation, the cache frame —
abandon the process, and reopen. The durable state must be the pre-commit
state, the session must be usable, and the refused work must re-arm.

The battery's at-LOAD half went with F-16 rider r1: the load path
validates no record it reads, because a disposable cache is trusted or
re-folded and there is no third state. The wall below is where a
malformed key is caught, and it is the only place it needs to be.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from holo2.core.blobs import stage_bytes
from holo2.core.commit import (CommitBatch, CommitEngine, CommitRefusal,
                               SpendProposal, Write)
from holo2.core.identity import ABSENT_VERSION
from holo2.core.keys import ResourceKey
from holo2.core.cache import CACHE_NAME
from holo2.core.journal import JOURNAL_NAME
from holo2.core.store import Store
from conftest import (crash, CALIBRATION, COLLECTION_CERTIFIED, FOOTING,
                      POSE, REGION,
                      EvidenceObservation, MintRef, TileRecord,
                      evidence_collection_key, evidence_key, ground_batch,
                      make_session, region_evidence_collection_key, registry,
                      tile_key, tile_write, wid)

_LLR = stage_bytes(b"calibrated llrs")
_MASK = stage_bytes(b"observed cells")
_BITS = stage_bytes(b"certified bits")

#: The review's probe key: right kind, a shape no minting worker can make.
_BAD_KEY = ResourceKey("evidence", ("bad",))
_TILE = tile_key(0, 1, 2, "K")


def _evidence(footing: str = "cap:8/1") -> EvidenceObservation:
    return EvidenceObservation(
        footing_id=footing, page=0, ty=1, tx=2, stream="K", pose_id=POSE,
        llr_ref=_LLR.ref, observed_ref=_MASK.ref,
        calibration_id=CALIBRATION)


def _evidence_batch(key: ResourceKey,
                    record: EvidenceObservation | None = None) -> CommitBatch:
    piece = _evidence() if record is None else record
    return CommitBatch(writes=(Write(key, piece),), blobs=(_LLR, _MASK))


def _materialised(store: Store) -> tuple[str, ...]:
    """Which of this module's staged bulk values reached the sidecar.

    The sidecar's blob COUNT retired with the W-B/B3 shrink; what these
    tests actually mean is named here instead — a refused commit
    materialises none of its batch's staged blobs, and a re-armed one
    materialises exactly the addresses it staged.
    """
    return tuple(blob.ref.sha256 for blob in (_LLR, _MASK, _BITS)
                 if store.blobs.contains(blob.ref.sha256))


def _started(state_dir: Path) -> tuple[Store, CommitEngine]:
    """A session with one ordinary DURABLE commit behind it.

    ``snapshot_every=1`` is named rather than inherited: these tests
    abandon the process without a clean exit, so the pre-commit state they
    compare against has to be on disk. The production cadence (512, W-B/B11)
    is a crash-window policy and would make "the pre-commit envelope" mean
    the empty one — a different test.
    """
    store = Store.create(state_dir, make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    # ONE commit, and it carries the fixture GROUND: since F-07's
    # relational half a piece of evidence names a pose and a calibration
    # that must already be facts, so the history commit lays them (a real
    # placement fire lays exactly this chain in exactly one batch).
    base = ground_batch()
    engine.apply(CommitBatch(writes=base.writes + (tile_write(0, 3, 4),),
                             blobs=base.blobs))
    return store, engine


def _boom(*args: Any, **kwargs: Any) -> None:
    raise OSError("simulated failure")


# ----------------------------------------------------------- the probe

def test_the_review_probe_is_refused_and_leaves_nothing_durable(
        tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store, engine = _started(state_dir)
    with pytest.raises(CommitRefusal, match="not an evidence key"):
        engine.apply(_evidence_batch(_BAD_KEY))

    assert store.commit_seq == 1                    # only the history commit
    assert store.get(_BAD_KEY) is None
    assert engine.table.version(_BAD_KEY) == ABSENT_VERSION
    assert _materialised(store) == ()               # not even the staged bulk
    store.close()

    crash(state_dir)
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 1
        assert reopened.get(_BAD_KEY) is None
        resumed = CommitEngine(reopened)            # this used to raise forever
        key = _evidence().resource_key()
        # A piece joins TWO collections since the F2a review
        # (2026-08-23): its work key's, and its (footing, region)'s —
        # the second is how a region ctx fit learns that a re-read added
        # pieces without adding a pose.
        assert resumed.apply(_evidence_batch(key)).changed_keys == (
            key, evidence_collection_key(_TILE),
            region_evidence_collection_key(FOOTING, REGION))


def test_a_record_may_not_be_stored_under_another_legal_key(
        tmp_path: Path) -> None:
    """Key-aware validation is agreement, not merely parseability."""
    store, engine = _started(tmp_path / "state")
    foreign = evidence_key("cap:2/1", 0, 1, 2, "K", POSE)
    with pytest.raises(CommitRefusal, match="record identifies"):
        engine.apply(_evidence_batch(foreign))
    assert store.get(foreign) is None


def test_a_refused_write_does_not_publish_its_batch_mates(
        tmp_path: Path) -> None:
    """One delta: the legal half of a refused batch lands nowhere either."""
    store, engine = _started(tmp_path / "state")
    certified = TileRecord(MintRef(POSE, "scan",
                                          "fixture-decoder"),
                           _BITS.ref, 1, ("cap:8/1",))
    with pytest.raises(CommitRefusal, match="not an evidence key"):
        engine.apply(CommitBatch(
            writes=(Write(_TILE, certified), Write(_BAD_KEY, _evidence())),
            blobs=(_LLR, _MASK, _BITS)))

    assert store.get(_TILE) is None
    assert engine.table.version(_TILE) == ABSENT_VERSION
    assert engine.table.version(COLLECTION_CERTIFIED) == ABSENT_VERSION
    assert store.commit_seq == 1


def test_a_dangling_bulk_reference_refuses_before_the_sidecar_moves(
        tmp_path: Path) -> None:
    """References resolve against staged + stored while the delta is derived."""
    store, engine = _started(tmp_path / "state")
    key = _evidence().resource_key()
    with pytest.raises(CommitRefusal, match="neither staged nor already stored"):
        engine.apply(CommitBatch(writes=(Write(key, _evidence()),)))  # no blobs
    assert _materialised(store) == ()
    assert store.get(key) is None


# ------------------------------------------- restart at every failure point

def test_restart_after_a_validation_failure(tmp_path: Path) -> None:
    _assert_restart_resumes_pre_commit_state(
        tmp_path, _evidence_batch(_BAD_KEY), CommitRefusal, inject=None)


def test_restart_after_a_blob_materialisation_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The first blob lands, the second refuses: an orphan is not a fact."""
    materialised: list[object] = []
    honest = Store.put_staged

    def failing_put_staged(self: Store, blob: object) -> object:
        if materialised:
            raise OSError("simulated failure mid-materialisation")
        materialised.append(blob)
        return honest(self, blob)                        # type: ignore[arg-type]

    key = _evidence().resource_key()
    state_dir = _assert_restart_resumes_pre_commit_state(
        tmp_path, _evidence_batch(key), OSError,
        inject=lambda: monkeypatch.setattr(Store, "put_staged",
                                           failing_put_staged),
        undo=monkeypatch.undo)
    crash(state_dir)
    with Store.open(state_dir, registry()) as reopened:
        # The re-arm deduped onto the orphan: the two staged addresses
        # the batch declared are the two the sidecar holds.
        assert _materialised(reopened) == (_LLR.ref.sha256, _MASK.ref.sha256)


def test_restart_after_a_cache_frame_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The third failure point, and the only one F-16 moved.

    A frame that cannot be written is DURABILITY, not semantics: the
    commit is already RECORDED — the journal took it, fsynced, before the
    memo was asked for anything — so the reopened session stands at the
    previous commit with the failed one waiting in the tail, to be
    re-earned rather than lost. That is the whole difference between the
    record and the memo, in one test.
    """
    state_dir = tmp_path / "state"
    store, engine = _started(state_dir)
    key = _evidence().resource_key()
    cached = (state_dir / CACHE_NAME).read_bytes()
    monkeypatch.setattr(store._cache, "_append", _boom)
    with pytest.raises(OSError):
        engine.apply(_evidence_batch(key))
    monkeypatch.undo()
    del engine, store                            # the process dies uncleanly

    assert (state_dir / CACHE_NAME).read_bytes() == cached
    crash(state_dir)
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 1          # the memo stands at one
        assert reopened.get(key) is None
        assert len(reopened.ordering()) == 2     # the record stands at two
        resumed = CommitEngine(reopened)
        assert resumed.table.version(key) == ABSENT_VERSION
        assert resumed.apply(_evidence_batch(key)).changed_keys[0] == key


def _assert_restart_resumes_pre_commit_state(
        tmp_path: Path, batch: CommitBatch, refusal: type[BaseException],
        inject: Any = None, undo: Any = None) -> Path:
    """Fail one commit, abandon the process, reopen: nothing moved.

    The durable files must be the pre-commit ones — the JOURNAL first,
    since a refused commit is a commit that never happened and the
    ordering is what says so — the reopened session must build a resource
    table, and the refused work must re-arm and commit cleanly, which is
    what "a refused commit leaves no durable trace" means once the process
    is gone.
    """
    state_dir = tmp_path / "state"
    store, engine = _started(state_dir)
    before = tuple((state_dir / name).read_bytes()
                   for name in (JOURNAL_NAME, CACHE_NAME))

    if inject is not None:
        inject()
    with pytest.raises(refusal):
        engine.apply(batch)
    if undo is not None:
        undo()
    del engine, store                            # the process dies uncleanly

    assert tuple((state_dir / name).read_bytes()
                 for name in (JOURNAL_NAME, CACHE_NAME)) == before
    key = _evidence().resource_key()
    crash(state_dir)
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.commit_seq == 1
        assert reopened.get(key) is None
        assert reopened.get(_BAD_KEY) is None
        resumed = CommitEngine(reopened)
        assert resumed.table.version(key) == ABSENT_VERSION
        assert resumed.apply(_evidence_batch(key)).changed_keys[0] == key
    return state_dir


# ---------------------------------------------- the two halves cannot part

def test_the_table_cannot_disagree_with_the_store_on_a_failed_frame(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """F-18, resolved structurally: one delta, table first, memo last.

    A failing cache frame is durability, not semantics: the two in-memory
    halves have both moved, so they agree, and the durable state is still
    the previous commit — exactly the ``snapshot_every > 1`` position the
    store already documents.
    """
    state_dir = tmp_path / "state"
    store, engine = _started(state_dir)
    key = _evidence().resource_key()
    monkeypatch.setattr(store._cache, "_append", _boom)
    with pytest.raises(OSError):
        engine.apply(_evidence_batch(key))
    monkeypatch.undo()

    assert store.version(key) == engine.table.version(key) == 1
    assert engine.table.value(key) == store.get(key) == _evidence()
    assert engine.table.version(evidence_collection_key(_TILE)) == 1
    crash(state_dir)
    with Store.open(state_dir, registry()) as durable:
        assert durable.commit_seq == 1           # the commit is not durable
        assert durable.get(key) is None


def test_a_spend_refusal_still_refuses_the_whole_delta(
        tmp_path: Path) -> None:
    """Publication is all-or-nothing over writes, spends and collections."""
    store, engine = _started(tmp_path / "state")
    spend = SpendProposal(wid("w-1"), "chain", ((_TILE, 1),), "accepted")
    engine.apply(CommitBatch(spends=(spend,)))
    key = _evidence().resource_key()
    with pytest.raises(Exception, match="already spent"):
        engine.apply(CommitBatch(writes=(Write(key, _evidence()),),
                                 spends=(spend,), blobs=(_LLR, _MASK)))
    assert store.get(key) is None
    assert engine.table.version(evidence_collection_key(_TILE)) == ABSENT_VERSION
    assert _materialised(store) == ()

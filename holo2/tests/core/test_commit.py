"""The commit layer's laws (DESIGN §7, §10.1, §11.3–§11.4).

Version bumps iff content changed; a spend is durable iff its outcome is;
monotone facts stay monotone; a terminal session is immutable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo2.core.commit import (CertificateConflict, CommitBatch, CommitEngine,
                               DuplicateWrite, SpendProposal, Subscription,
                               TerminalSessionError, Write, batch_id)
from holo2.core.identity import SpendConflict
from holo2.core.records import CLOSE_KEY, CloseRecord, CloseStatus
from holo2.core.store import Store
from conftest import (POSE, REGION, MintRef, PoseRecord, RegionRecord,
                      TileRecord, ground, make_pose, make_region,
                      make_session, registry, subscribe, tile_key, tile_write,
                      wid)

_TILE = tile_key(0, 3, 4, "K")
_IDENTITY = ((_TILE, 1),)


def test_equal_content_bumps_nothing_and_wakes_nobody(
        engine: CommitEngine) -> None:
    engine.apply(CommitBatch(subscriptions=(subscribe("w1", _TILE),)))
    first = engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),)))
    assert first.changed_keys == (_TILE,)
    assert first.wakes == (wid("w1"),)
    assert engine.store.version(_TILE) == 1

    again = engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),)))
    assert again.changed_keys == ()
    assert again.wakes == ()
    assert engine.store.version(_TILE) == 1


def test_changed_content_bumps_exactly_once(engine: CommitEngine) -> None:
    engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),)))
    result = engine.apply(CommitBatch(writes=(
        tile_write(0, 3, 4, observed_by=("cap:8/1",)),)))
    assert result.changed_keys == (_TILE,)
    assert engine.store.version(_TILE) == 2


def test_reordered_set_field_is_not_a_change(engine: CommitEngine) -> None:
    """Set-shaped tuples are canonical, so equality is content equality."""
    record = TileRecord(observed_by=("a", "b"))
    engine.apply(CommitBatch(writes=(Write(_TILE, record),)))
    same = TileRecord(observed_by=tuple(sorted(("b", "a"))))
    assert engine.apply(CommitBatch(writes=(Write(_TILE, same),))).changed_keys == ()


def test_equality_is_decisive_no_flag_can_move_it(
        engine: CommitEngine) -> None:
    """F-26's residue closed by DELETION (H3.5 sweep, 2026-08-14).

    Blob refs are content addresses, so record equality IS content
    equality for every family — the ``content_changed`` escape that let
    a producer force a bump for equal content was a test-only wart on
    the one law that keeps wakes honest, and it is gone: equal content
    never bumps, changed content always does, and Write carries no knob
    that could say otherwise.
    """
    engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),)))
    equal = engine.apply(CommitBatch(writes=(Write(_TILE, TileRecord()),)))
    assert equal.changed_keys == ()
    changed = engine.apply(CommitBatch(writes=(
        Write(_TILE, TileRecord(observed_by=("cap:8/1",))),)))
    assert changed.changed_keys == (_TILE,)
    assert not hasattr(Write(_TILE, TileRecord()), "content_changed")


def test_batch_may_not_write_one_key_twice(engine: CommitEngine) -> None:
    with pytest.raises(DuplicateWrite):
        engine.apply(CommitBatch(writes=(
            tile_write(0, 3, 4),
            tile_write(0, 3, 4, observed_by=("cap:8/1",)))))
    assert engine.store.get(_TILE) is None


def test_a_key_holds_one_record_type(engine: CommitEngine) -> None:
    ground(engine, "capture")           # the capture this region stands on
    engine.apply(CommitBatch(writes=(Write(
        REGION, make_region(engine.store.blobs.put(b"mask"))),)))
    with pytest.raises(Exception, match="may not be stored under kind"):
        engine.apply(CommitBatch(writes=(Write(REGION, TileRecord()),)))


def test_wakes_are_computed_after_subscriptions_apply(
        engine: CommitEngine) -> None:
    """A worker sleeping in the commit that changes its key is not lost."""
    result = engine.apply(CommitBatch(
        writes=(tile_write(0, 3, 4),),
        subscriptions=(subscribe("w1", _TILE),)))
    assert result.wakes == (wid("w1"),)


def test_unsubscribe_stops_wakes(engine: CommitEngine) -> None:
    engine.apply(CommitBatch(subscriptions=(subscribe("w1", _TILE),)))
    engine.apply(CommitBatch(subscriptions=(Subscription(wid("w1"), ()),)))
    assert engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),))).wakes == ()


def test_spend_and_outcome_are_one_transaction(engine: CommitEngine) -> None:
    engine.apply(CommitBatch(
        writes=(tile_write(0, 3, 4),),
        spends=(SpendProposal(wid("win-1"), "chain", _IDENTITY, "accepted"),)))
    assert engine.store.ledger.is_spent(wid("win-1"), "chain", _IDENTITY)
    assert engine.store.get(_TILE) is not None


def test_a_refused_spend_refuses_the_whole_batch(engine: CommitEngine) -> None:
    spend = SpendProposal(wid("win-1"), "chain", _IDENTITY, "accepted")
    engine.apply(CommitBatch(spends=(spend,)))
    with pytest.raises(SpendConflict):
        engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),), spends=(spend,)))
    assert engine.store.get(_TILE) is None          # the write did not land
    assert engine.store.version(_TILE) == 0


def test_one_batch_may_not_spend_the_same_identity_twice(
        engine: CommitEngine) -> None:
    spend = SpendProposal(wid("win-1"), "chain", _IDENTITY, "accepted")
    with pytest.raises(SpendConflict, match="twice in one batch"):
        engine.apply(CommitBatch(spends=(spend, spend)))


def _certify(engine: CommitEngine, bits: bytes = b"certified bits",
             metadata_bit: int = 1,
             observed_by: tuple[str, ...] = ("cap:8/1",)) -> TileRecord:
    if engine.store.get(POSE) is None:
        ground(engine, "pose")          # the pose the certificate names
    ref = engine.store.blobs.put(bits)
    record = TileRecord(MintRef(POSE, "scan", "fixture-decoder"), ref,
                        metadata_bit, observed_by)
    engine.apply(CommitBatch(writes=(Write(_TILE, record),)))
    return record


def test_certified_content_may_not_change(engine: CommitEngine) -> None:
    _certify(engine)
    with pytest.raises(CertificateConflict):
        _certify(engine, bits=b"different bits")
    with pytest.raises(CertificateConflict):
        _certify(engine, metadata_bit=0)


def test_certified_tile_may_gain_observing_footings(engine: CommitEngine) -> None:
    first = _certify(engine)
    grown = TileRecord(first.minting, first.bits_ref,
                       first.metadata_bit, ("cap:2/1", "cap:8/1"))
    result = engine.apply(CommitBatch(writes=(Write(_TILE, grown),)))
    assert result.changed_keys == (_TILE,)          # done-projection needs both


def test_a_certified_tile_can_no_longer_LOSE_observing_footings(
        engine: CommitEngine) -> None:
    """The same law (§6), by construction now rather than by refusal.

    A proposal naming fewer footings used to be REFUSED — fatal, over a
    race nothing was semantically wrong about. Since the tile family
    declared its join (H4 W2) the wall UNIONS it back to the full set
    instead, so the loss is unrepresentable rather than merely illegal,
    and the fire that raced keeps the observation it did contribute.
    """
    _certify(engine, observed_by=("cap:2/1", "cap:8/1"))
    result = _certify(engine, observed_by=("cap:8/1",))
    assert result.observed_by == ("cap:8/1",)          # what was PROPOSED
    stored = engine.store.get(_TILE)
    assert isinstance(stored, TileRecord)
    assert stored.observed_by == ("cap:2/1", "cap:8/1")     # what stands


def test_terminal_close_freezes_the_session(engine: CommitEngine) -> None:
    engine.apply(CommitBatch(writes=(Write(
        CLOSE_KEY, CloseRecord(CloseStatus.OPEN)),)))
    engine.apply(CommitBatch(writes=(tile_write(0, 3, 4),)))
    engine.apply(CommitBatch(writes=(Write(CLOSE_KEY, CloseRecord(
        CloseStatus.VERIFIED, payload_sha256="ff" * 32)),)))
    assert engine.store.is_terminal()

    for batch in (CommitBatch(writes=(tile_write(0, 3, 5),)),
                  CommitBatch(spends=(SpendProposal(wid("w"), "chain", (), "ok"),)),
                  CommitBatch(subscriptions=(subscribe("w2", _TILE),)),
                  CommitBatch(writes=(Write(CLOSE_KEY,
                                            CloseRecord(CloseStatus.OPEN)),))):
        with pytest.raises(TerminalSessionError):
            engine.apply(batch)
    assert engine.store.get(tile_key(0, 3, 5, "K")) is None


def test_terminal_close_survives_reopen(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        CommitEngine(store).apply(CommitBatch(writes=(Write(
            CLOSE_KEY,
            CloseRecord(CloseStatus.INTEGRITY_FAILURE,
                        reason="conflicting certified bits")),)))
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.is_terminal()
        with pytest.raises(TerminalSessionError):
            CommitEngine(reopened).apply(
                CommitBatch(writes=(tile_write(0, 3, 4),)))


def test_batch_id_is_content_derived_and_order_free() -> None:
    """§10.2: ids are content-derived, so batch order within a batch is not id."""
    writes = (tile_write(0, 3, 4), Write(POSE, make_pose()))
    assert batch_id(CommitBatch(writes=writes)) == batch_id(
        CommitBatch(writes=tuple(reversed(writes))))
    assert batch_id(CommitBatch(writes=writes)) != batch_id(
        CommitBatch(writes=(tile_write(0, 3, 5),)))


def test_bulk_values_ride_content_addresses(engine: CommitEngine) -> None:
    """Equal arrays produce equal refs, so an unchanged blob bumps nothing."""
    ground(engine, "pose")              # the pose the certificate names
    ref = engine.store.put_array(np.arange(5, dtype=np.uint8))
    record = TileRecord(MintRef(POSE, "scan", "fixture-decoder"), ref, 0)
    engine.apply(CommitBatch(writes=(Write(_TILE, record),)))
    same_ref = engine.store.put_array(np.arange(5, dtype=np.uint8))
    repeat = TileRecord(MintRef(POSE, "scan", "fixture-decoder"), same_ref, 0)
    assert engine.apply(CommitBatch(writes=(Write(_TILE, repeat),))).changed_keys == ()

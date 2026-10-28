"""The resource table is rebuildable and carries no authority (§5.6, §10.1).

The gate property: after a reopen, the table rebuilt from the store plus
the sleeping workers' declared read-sets equals the table the running
process had. Nothing in H1 is transient-only, so the equality is exact.

A subscription is durable through the same fact its worker's SPEND is
(F-16: read-sets are derived from the spend ledger's identities, never
stored twice), so the workloads here declare the pair a real worker
declares — one read of one worker's keys, spent and subscribed in the
same commit (``orchestrator._propose``).

The equality is spelled out here as :func:`_picture` — versions,
read-sets, and the subscriber set of every key the table holds — because
the W-B/B3 ruling (2026-08-12) deleted the table's own comparison sugar
(``snapshot()``/``__eq__``/``__len__``, production-dead) and kept the
property: what the gate asserts is now visible in the test rather than
hidden behind an operator.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


from holo2.core.commit import CommitBatch, CommitEngine, SpendProposal, Write
from holo2.core.identity import ABSENT_VERSION
from holo2.core.records import KIND_COLLECTION
from holo2.core.resources import ResourceTable
from holo2.core.store import Store
from conftest import (COLLECTION_CERTIFIED, MintRef, RegionRecord,
                      POSE, TileRecord, ground,
                      make_session, registry, subscribe,
                      tile_key, wid, tile_write)

_TILE = tile_key(1, 2, 3, "K")
_OTHER = tile_key(1, 2, 4, "K")


def _picture(table: ResourceTable) -> tuple[Any, Any, Any]:
    """The whole wake/idle behaviour of a table, as comparable values.

    Versions carry the durable ones AND the derived collection counts;
    ``keys()`` adds the subscribed-but-absent keys, so a table that woke a
    different set of workers cannot compare equal to this one.
    """
    return (table.versions(), table.read_sets(),
            {key: table.subscribers(key) for key in table.keys()})


def _populate(engine: CommitEngine) -> None:
    # The ground first (F-07): the region names its capture and the
    # certificate below names a pose, so both have to be facts already.
    ground(engine, "pose")
    engine.apply(CommitBatch(
        subscriptions=(subscribe("w-tile", _TILE, _OTHER),
                       subscribe("w-pose", POSE)),
        spends=(SpendProposal(wid("w-tile"), "route",
                              ((_TILE, 0), (_OTHER, 0)), "accepted"),
                SpendProposal(wid("w-pose"), "route", ((POSE, 0),),
                              "accepted"))))
    engine.apply(CommitBatch(
        writes=(tile_write(1, 2, 3),),
        spends=(SpendProposal(wid("w-tile"), "chain", ((_TILE, 0),),
                              "refused"),)))
    engine.apply(CommitBatch(writes=(Write(_TILE, TileRecord(
        MintRef(POSE, "scan", "fixture-decoder"),
        engine.store.blobs.put(b"bits"), 1, ("cap:8/1",))),)))


def test_rebuild_after_reopen_reproduces_the_table(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        _populate(engine)
        live = _picture(engine.table)

    with Store.open(state_dir, registry()) as reopened:
        rebuilt = ResourceTable.rebuild(reopened.records(),
                                        reopened.versions(),
                                        reopened.subscriptions(), registry())
        assert _picture(rebuilt) == live
        # The values are the store's, never the table's (L13).
        assert rebuilt.value(_TILE) == reopened.get(_TILE)


def test_rebuild_is_total_over_subscribed_but_absent_keys(
        tmp_path: Path) -> None:
    """A worker may sleep on a key that does not exist yet."""
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        CommitEngine(store).apply(CommitBatch(
            subscriptions=(subscribe("w-cold", _OTHER),),
            spends=(SpendProposal(wid("w-cold"), "route", ((_OTHER, 0),),
                                  "declined"),)))
    with Store.open(state_dir, registry()) as reopened:
        rebuilt = ResourceTable.rebuild(reopened.records(),
                                        reopened.versions(),
                                        reopened.subscriptions(), registry())
    entry = rebuilt.entry(_OTHER)
    assert entry.version == ABSENT_VERSION
    assert entry.value is None
    assert entry.subscribers == (wid("w-cold"),)
    assert rebuilt.wakes_for([_OTHER]) == (wid("w-cold"),)


def test_resubscribing_drops_the_stale_subscription(
        engine: CommitEngine) -> None:
    engine.apply(CommitBatch(subscriptions=(subscribe("w1", _TILE, _OTHER),)))
    engine.apply(CommitBatch(subscriptions=(subscribe("w1", _OTHER),)))
    assert engine.table.subscribers(_TILE) == ()
    assert engine.table.subscribers(_OTHER) == (wid("w1"),)
    assert engine.apply(
        CommitBatch(writes=(tile_write(1, 2, 3),))).wakes == ()


def test_subscribers_are_deterministically_ordered(
        engine: CommitEngine) -> None:
    for worker_id in ("w3", "w1", "w2"):
        engine.apply(CommitBatch(subscriptions=(subscribe(worker_id, _TILE),)))
    assert engine.table.subscribers(_TILE) == (wid("w1"), wid("w2"),
                                               wid("w3"))
    assert engine.apply(
        CommitBatch(writes=(tile_write(1, 2, 3),))).wakes == (
            wid("w1"), wid("w2"), wid("w3"))


def test_table_versions_track_the_store(engine: CommitEngine) -> None:
    """Every durable key at its durable version, plus derived collections.

    A collection (M4) has no record and no durable version: the table
    counts its members, which is why it can be rebuilt at open and why a
    resumed session takes the same identities as the run that left it.
    """
    _populate(engine)
    versions = engine.table.versions()
    for key, version in engine.store.versions().items():
        assert versions[key] == version
    derived = {key for key in versions if key.kind == KIND_COLLECTION}
    # The ground joins its own collections (a capture joins `captures`, a
    # pose joins its window's `poses`); what this test is about is that
    # the certified frontier is derived at all.
    assert COLLECTION_CERTIFIED in derived
    assert versions[COLLECTION_CERTIFIED] == 1
    assert engine.table.value(COLLECTION_CERTIFIED) is None
    assert engine.table.value(_TILE) == engine.store.get(_TILE)


def test_tables_of_different_states_differ(tmp_path: Path) -> None:
    with Store.create(tmp_path / "a", make_session(), registry()) as store_a:
        engine_a = CommitEngine(store_a)
        _populate(engine_a)
        with Store.create(tmp_path / "b", make_session(), registry()) as store_b:
            engine_b = CommitEngine(store_b)
            assert _picture(engine_a.table) != _picture(engine_b.table)
            _populate(engine_b)
            assert _picture(engine_a.table) == _picture(engine_b.table)

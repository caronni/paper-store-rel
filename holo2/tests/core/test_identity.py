"""Read-sets, attempt identity, spend-once, idleness (DESIGN §7).

The whole mechanism is integer compares over (key, version) pairs: a
spent identity is idle, and a bump on ANY read key re-arms the worker.

Since the D1 fold the ledger keeps ONE row per ``(worker, route)`` — the
latest identity plus an attempt count — so the tests below pin both
halves: the fold itself, and the monotonicity it rests on (a read-set
that shrinks refuses instead of re-arming forever).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo2.core import codec, identity as ident
from holo2.core.commit import CommitBatch, CommitEngine, SpendProposal, Write
from holo2.core.identity import (ABSENT_VERSION, SpendConflict, SpendLedger,
                                 SpendRecord, attempt_identity, is_idle,
                                 read_set)
from holo2.core.keys import ResourceKey, WorkId, WorkScope
from conftest import POSE, TileRecord, registry, tile_key, wid
from holo2.core.store import Store
from conftest import make_session, tile_write

_A = tile_key(0, 0, 0, "K")
_B = tile_key(0, 0, 1, "K")
_C = POSE


def test_read_set_is_sorted_and_deduplicated() -> None:
    assert read_set([_B, _A, _B]) == (_A, _B)
    assert read_set([_A, _B]) == read_set([_B, _A])


def test_identity_is_order_free_and_absent_keys_read_as_zero() -> None:
    versions = {_A: 3}
    assert attempt_identity([_B, _A], versions) == ((_A, 3), (_B, ABSENT_VERSION))
    assert attempt_identity([_A, _B], versions) == attempt_identity([_B, _A],
                                                                    versions)


def test_the_spend_wire_shape_is_the_generic_codec_and_is_golden() -> None:
    """The envelope's spend row, pinned as bytes (the codec is the wire).

    ``SpendRecord`` used to carry a hand-written ``to_json``/``from_json``
    pair that re-spelled what ``encode_dataclass``/``decode_dataclass``
    already do. Deleting it was allowed to change nothing on disk, so the
    exact encoded dict is frozen here: a field renamed, a key nested, a
    ``WorkId`` rendered differently is a state-format fork and shows up as
    this test, not as an unreadable envelope. It fired for exactly that
    reason on 2026-08-12: deleting the never-written ``WorkScope.incumbent``
    (W-B/B2) narrowed the scope triple to a pair, which is a state-format
    fork taken deliberately and pre-freeze — no work id VALUE moved (the
    field was empty at every site), only the wire's arity.
    """
    worker = WorkId("payload", ResourceKey("tile", ("0", "12", "40", "K")),
                    "scan", WorkScope(arm="a1", profile="p7"))
    identity = ((ResourceKey("pose", ("w1", "0")), 3),
                (ResourceKey("tile", ("0", "12", "40", "K")), 0),
                (ResourceKey("window", ("f", "r", "0")), 17))
    spend = SpendRecord(worker, "scan", identity, "certified",
                        attempts=4, exposures=2)
    encoded = codec.encode_dataclass(spend)

    assert encoded == {
        "worker_id": ["payload", ["tile", "0", "12", "40", "K"], "scan",
                      ["a1", "p7"]],
        "route": "scan",
        "identity": [[["pose", "w1", "0"], 3],
                     [["tile", "0", "12", "40", "K"], 0],
                     [["window", "f", "r", "0"], 17]],
        "outcome": "certified",
        "attempts": 4,
        "exposures": 2,
    }
    assert codec.decode_dataclass(SpendRecord, encoded) == spend


def test_a_decoded_spend_is_validated_by_the_record_it_becomes() -> None:
    """The wall is ``__post_init__``, not a second deserialiser."""
    spend = SpendRecord(wid("win-1"), "chain", ((_A, 1), (_B, 2)), "refused")
    scrambled = codec.encode_dataclass(spend)
    scrambled["identity"] = list(reversed(scrambled["identity"]))
    with pytest.raises(ValueError, match="sorted by key and unique"):
        codec.decode_dataclass(SpendRecord, scrambled)

    truncated = codec.encode_dataclass(spend)
    del truncated["exposures"]
    with pytest.raises(ValueError, match="missing field"):
        codec.decode_dataclass(SpendRecord, truncated)


def test_an_identity_is_named_by_its_values_not_by_a_digest() -> None:
    """The hash-free law, at the ledger: no ``identity_digest`` exists.

    It had exactly two callers, both writing ``MintRef.attempt_digest``,
    and both died with that field (tile family v3). What names an attempt
    is the row the values already key — ``(worker, route)`` plus the
    read-set identity itself, compared as integers.
    """
    assert not hasattr(ident, "identity_digest")
    assert not hasattr(ident, "identity_to_json")
    assert attempt_identity([_A, _C], {_A: 2, _C: 7}) == attempt_identity(
        [_C, _A], {_C: 7, _A: 2})


def test_a_non_canonical_identity_may_not_be_spent() -> None:
    """Equality is the whole mechanism, so identities must be canonical."""
    with pytest.raises(ValueError, match="sorted by key and unique"):
        SpendProposal(wid("win-1"), "chain", ((_B, 1), (_A, 1)), "refused")
    with pytest.raises(ValueError, match="sorted by key and unique"):
        SpendRecord(wid("win-1"), "chain", ((_A, 1), (_A, 2)), "refused")


def test_ledger_refuses_a_repeated_identity() -> None:
    ledger = SpendLedger()
    spend = SpendRecord(wid("win-1"), "chain", ((_A, 1),), "refused")
    ledger.record(spend)
    with pytest.raises(SpendConflict):
        ledger.record(spend)
    assert len(ledger) == 1


def test_the_ledger_folds_to_the_latest_identity_and_counts_attempts() -> None:
    """D1: versions are monotone, so only the newest identity is reachable."""
    ledger = SpendLedger()
    ledger.record(SpendRecord(wid("win-1"), "chain", ((_A, 1),), "refused"))
    ledger.record(SpendRecord(wid("win-1"), "chain", ((_A, 2),), "refused"))
    ledger.record(SpendRecord(wid("win-1"), "chain", ((_A, 5),), "accepted"))

    assert len(ledger) == 1                       # one row per (worker, route)
    held, = ledger.spends_for(wid("win-1"), "chain")
    assert held.identity == ((_A, 5),)
    assert held.outcome == "accepted"
    assert held.attempts == 3
    assert ledger.is_spent(wid("win-1"), "chain", ((_A, 5),))
    assert not ledger.is_spent(wid("win-1"), "chain", ((_A, 1),))


def test_a_shrunk_read_set_is_refused_rather_than_silently_re_arming() -> None:
    """The fold is sound only while identities advance, so it is checked."""
    ledger = SpendLedger()
    ledger.record(SpendRecord(wid("win-1"), "chain", ((_C, 1), (_A, 2)), "refused"))

    with pytest.raises(SpendConflict, match="not newer"):
        ledger.record(SpendRecord(wid("win-1"), "chain", ((_A, 2),), "refused"))
    with pytest.raises(SpendConflict, match="not newer"):
        ledger.record(SpendRecord(wid("win-1"), "chain", ((_C, 1), (_A, 1)),
                                  "refused"))

    held, = ledger.spends_for(wid("win-1"), "chain")
    assert held.identity == ((_C, 1), (_A, 2)) and held.attempts == 1
    # A read-set that GROWS onto a key that now exists is newer, not shrunk.
    ledger.record(SpendRecord(wid("win-1"), "chain", ((_C, 1), (_A, 2), (_B, 1)),
                              "accepted"))
    assert ledger.spends_for(wid("win-1"), "chain")[0].attempts == 2


def test_ledger_separates_workers_and_routes() -> None:
    ledger = SpendLedger()
    identity = ((_A, 1),)
    ledger.record(SpendRecord(wid("win-1"), "chain", identity, "refused"))
    ledger.record(SpendRecord(wid("win-1"), "word", identity, "accepted"))
    ledger.record(SpendRecord(wid("win-2"), "chain", identity, "refused"))
    assert ledger.is_spent(wid("win-1"), "chain", identity)
    assert not ledger.is_spent(wid("win-3"), "chain", identity)
    assert len(ledger) == 3
    assert ledger.entries() == tuple(sorted(ledger.entries(),
                                            key=SpendRecord.sort_key))


def test_spent_identity_is_idle_and_a_bump_re_arms(engine: CommitEngine) -> None:
    keys = [_A, _C]
    engine.apply(CommitBatch(writes=(tile_write(0, 0, 0),)))
    identity = engine.attempt_identity(keys)
    assert not engine.is_idle(wid("win-1"), "chain", keys)

    engine.apply(CommitBatch(spends=(
        SpendProposal(wid("win-1"), "chain", identity, "refused"),)))
    assert engine.is_idle(wid("win-1"), "chain", keys)          # spend-once holds

    engine.apply(CommitBatch(writes=(
        tile_write(0, 0, 0, observed_by=("cap:8/1",)),)))
    assert not engine.is_idle(wid("win-1"), "chain", keys)       # a read key bumped
    assert engine.is_idle(wid("win-1"), "chain", [_A]) is False


def test_arrival_of_an_absent_read_key_re_arms(engine: CommitEngine) -> None:
    keys = [_A, _C]
    identity = engine.attempt_identity(keys)
    assert identity == ((_C, 0), (_A, 0))       # sorted by key: pose < tile
    engine.apply(CommitBatch(spends=(
        SpendProposal(wid("win-1"), "cold", identity, "refused"),)))
    assert engine.is_idle(wid("win-1"), "cold", keys)
    engine.apply(CommitBatch(writes=(tile_write(0, 0, 0),)))
    assert not engine.is_idle(wid("win-1"), "cold", keys)


def test_an_unrelated_bump_does_not_re_arm(engine: CommitEngine) -> None:
    keys = [_A]
    identity = engine.attempt_identity(keys)
    engine.apply(CommitBatch(spends=(
        SpendProposal(wid("win-1"), "chain", identity, "refused"),)))
    engine.apply(CommitBatch(writes=(tile_write(0, 0, 1),)))   # a different key
    assert engine.is_idle(wid("win-1"), "chain", keys)


def test_spends_are_durable_across_resume(tmp_path: Path) -> None:
    """One folded row per (worker, route), attempt count and all (D1)."""
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        engine.apply(CommitBatch(writes=(Write(_A, TileRecord()),)))
        first = engine.attempt_identity([_A])
        engine.apply(CommitBatch(spends=(
            SpendProposal(wid("win-1"), "word", first, "refused"),)))
        engine.apply(CommitBatch(writes=(Write(_A, TileRecord(
            observed_by=("cap:8/1",))),)))
        identity = engine.attempt_identity([_A])
        engine.apply(CommitBatch(spends=(
            SpendProposal(wid("win-1"), "word", identity, "accepted"),)))
        assert len(store.ledger) == 1              # the first identity folded

    with Store.open(state_dir, registry()) as reopened:
        resumed = CommitEngine(reopened)
        assert resumed.attempt_identity([_A]) == identity
        assert resumed.is_idle(wid("win-1"), "word", [_A])
        assert is_idle(reopened.ledger, wid("win-1"), "word", [_A],
                       reopened.versions())
        held, = reopened.ledger.spends_for(wid("win-1"), "word")
        assert held.identity == identity and held.attempts == 2
        with pytest.raises(SpendConflict):
            resumed.apply(CommitBatch(spends=(
                SpendProposal(wid("win-1"), "word", identity, "accepted"),)))
        # A resumed superseded identity is unreachable, not re-spendable.
        with pytest.raises(SpendConflict, match="not newer"):
            resumed.apply(CommitBatch(spends=(
                SpendProposal(wid("win-1"), "word", first, "accepted"),)))

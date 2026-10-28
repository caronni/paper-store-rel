"""The fourth registry hook: a declared commutative merge at the wall.

H4 W2's first concurrency ruling. The wall used to guard every family
with one rule — compare-and-swap on the attempt identity, refuse or
discard anything whose key moved underneath — and for a record whose
algebra is a JOIN that manufactures conflicts nothing is semantically
wrong about. A family may now declare ``merge``, and the wall re-applies
the proposal against the record it CURRENTLY holds, inside the serial
section it already had.

Two kinds of test live here. The toy-family ones state the MECHANISM,
because a registry is data and a wrong (or deliberately broken) one is
three lines — which is the only way a post-condition that a correct
merge can never trip gets fault-injected at all. The production ones use
the real tile family, because the ruling's point is a law that a real
writer's race walks into.

The ALGEBRA itself is pinned in ``tests/solve/test_records.py``
(``join_tiles``); what is pinned here is what the WALL does with it —
what is joined, what is identified and journaled, and what the staleness
test stops asking.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import pytest

from holo2.core import (KeyField, KeySpec, RecordFamily, RecordRegistry,
                        RegistryError, build_key, compose)
from holo2.core.commit import (CertificateConflict, CommitBatch, CommitEngine,
                               CommitRefusal, Write, batch_id)
from holo2.core.identity import drop_kinds
from holo2.core.journal import JOURNAL_NAME, read_journal
from holo2.core.records import RECORD_FAMILIES
from holo2.core.store import Store
from conftest import (FOOTING, POSE, REGION, MintRef, TileRecord, ground,
                      lattice_seed_key, make_seed, registry, tile_key)

_TILE = tile_key(0, 3, 4, "K")
_SEED = lattice_seed_key(FOOTING, REGION)


# ----------------------------------------------------------- a toy family

@dataclass(frozen=True)
class _Header:
    """A session identity of this file's own (see ``test_registry``)."""

    name: str


@dataclass(frozen=True)
class _Bag:
    """A record whose content is a growing set: a join by nature."""

    members: tuple[str, ...] = ()
    sealed: str | None = None


@dataclass(frozen=True)
class _Plain:
    """The same shape with no merge declared: compare-and-swap, as before."""

    members: tuple[str, ...] = ()


class _Sealed(RuntimeError):
    """The toy family's own contradiction — deliberately not a core type."""


_BAG_SPEC = KeySpec("bag", (KeyField("name"),))
_PLAIN_SPEC = KeySpec("plain", (KeyField("name"),))


def _bag_key(name: str = "one"):
    return build_key(_BAG_SPEC, name=name)


def _plain_key(name: str = "one"):
    return build_key(_PLAIN_SPEC, name=name)


def _join_bags(key, current: _Bag, proposed: _Bag) -> _Bag:
    if (current.sealed is not None and proposed.sealed is not None
            and current.sealed != proposed.sealed):
        raise _Sealed(f"{key}: {current.sealed} != {proposed.sealed}")
    return _Bag(tuple(sorted(set(current.members + proposed.members))),
                current.sealed if current.sealed is not None
                else proposed.sealed)


def _bag_never_shrinks(key, current: _Bag, proposed: _Bag) -> None:
    """The post-condition the toy family's transition hook states."""
    if not set(current.members) <= set(proposed.members):
        raise CertificateConflict(f"{key}: a bag may not lose members")


def toy_registry(*, merge: Callable[..., Any] | None = _join_bags,
                 transition: Callable[..., Any] | None = _bag_never_shrinks,
                 ) -> RecordRegistry:
    """core's own families, a session identity, and the two toys."""
    return compose(RECORD_FAMILIES, (
        RecordFamily(_Header, None),
        RecordFamily(_Bag, "bag", merge=merge, transition=transition),
        RecordFamily(_Plain, "plain"),
    ))


def toy_engine(directory: Path, **kwargs: Any) -> CommitEngine:
    return CommitEngine(Store.create(directory, _Header("toy"),
                                     toy_registry(**kwargs)))


@pytest.fixture
def toy(tmp_path: Path) -> CommitEngine:
    return toy_engine(tmp_path / "toy")


# ------------------------------------------------------- the declaration

def test_only_a_declaring_family_names_a_merge_kind() -> None:
    assert toy_registry().merge_kinds() == frozenset({"bag"})
    assert registry().merge_kinds() == frozenset({"tile"})


def test_the_session_identity_may_not_declare_a_merge() -> None:
    """It is not stored at a key, so nothing could ever stand to join."""
    with pytest.raises(RegistryError, match="not stored at a key"):
        RecordFamily(_Bag, None, merge=_join_bags)


def test_a_family_without_the_hook_is_the_compare_and_swap_default(
        toy: CommitEngine) -> None:
    """The absence of a declaration IS the old behaviour: last write wins."""
    toy.apply(CommitBatch(writes=(Write(_plain_key(), _Plain(("a",))),)))
    toy.apply(CommitBatch(writes=(Write(_plain_key(), _Plain(("b",))),)))
    assert toy.store.get(_plain_key()) == _Plain(("b",))


# ------------------------------------------------ the wall applies it

def test_the_wall_joins_onto_what_it_HOLDS_not_onto_the_snapshot(
        toy: CommitEngine) -> None:
    """The whole ruling in one commit: state read at COMMIT time.

    Both proposals are computed against the SAME snapshot — the empty
    record — which is exactly what two fires dispatched together hold.
    The second lands on a store that has moved underneath it, and both
    gains survive.
    """
    snapshot = _Bag()
    toy.apply(CommitBatch(writes=(
        Write(_bag_key(), replace(snapshot, members=("a",))),)))
    toy.apply(CommitBatch(writes=(
        Write(_bag_key(), replace(snapshot, members=("b",))),)))
    assert toy.store.get(_bag_key()) == _Bag(("a", "b"))


def test_a_join_that_changes_nothing_is_still_a_no_op(
        toy: CommitEngine) -> None:
    """Version-bumps-iff-changed is asked of the MERGED record."""
    toy.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("a", "b"))),)))
    result = toy.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("a",))),)))
    assert result.changed_keys == ()
    assert toy.store.version(_bag_key()) == 1


def test_the_transition_audits_the_MERGED_record(tmp_path: Path) -> None:
    """Composition, stated: merge first, then the family's ordinary laws.

    A correct join can never trip its post-condition, so the only way to
    show the audit is live rather than decorative is to BREAK the join.
    This one returns the proposal verbatim — the exact defect a
    hand-written merge would have — and the transition catches it by
    name, at the wall, before anything is durable.
    """
    broken = toy_engine(tmp_path / "broken",
                        merge=lambda key, current, proposed: proposed)
    broken.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("a",))),)))
    with pytest.raises(CertificateConflict, match="may not lose members"):
        broken.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("b",))),)))
    assert broken.store.get(_bag_key()) == _Bag(("a",))


def test_a_merge_that_returns_a_stranger_is_refused(tmp_path: Path) -> None:
    engine = toy_engine(tmp_path / "stranger",
                        merge=lambda key, current, proposed: _Plain(("x",)))
    engine.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("a",))),)))
    with pytest.raises(CommitRefusal, match="merge returned _Plain"):
        engine.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("b",))),)))


def test_the_familys_own_contradiction_passes_through(
        toy: CommitEngine) -> None:
    """A join that CANNOT join raises the owner's type, unwrapped.

    The tile map's is ``CertificateConflict``, which the orchestrator
    turns into a durable terminal fact (F-11); re-wrapping it here as an
    ordinary refusal would send a lawful data event down the crash path.
    """
    toy.apply(CommitBatch(writes=(Write(_bag_key(), _Bag((), "left")),)))
    with pytest.raises(_Sealed):
        toy.apply(CommitBatch(writes=(Write(_bag_key(), _Bag((), "right")),)))
    assert toy.store.get(_bag_key()) == _Bag((), "left")   # nothing landed


def test_a_wrong_kind_still_refuses_with_its_own_message(
        toy: CommitEngine) -> None:
    """The merge pass SUBSTITUTES a record; it never takes over a refusal."""
    with pytest.raises(CommitRefusal, match="may not be stored under kind"):
        toy.apply(CommitBatch(writes=(Write(_plain_key(), _Bag(("a",))),)))


# ------------------------------------------- what is identified and journaled

def test_the_journal_records_the_POST_MERGE_batch(tmp_path: Path) -> None:
    """State transfer, not operation transfer (the ruling's second half).

    The batch id is derived from the record as MERGED, so re-applying
    the recorded result reproduces the state without re-deriving a join
    against a store the replay has moved past. It differs from the id
    the proposing fire computed exactly when the join changed something
    — which is exactly when a race happened.
    """
    state_dir = tmp_path / "journalled"
    engine = toy_engine(state_dir)
    engine.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("a",))),)))
    proposed = CommitBatch(writes=(Write(_bag_key(), _Bag(("b",))),))
    result = engine.apply(proposed)
    engine.store.close()

    merged = CommitBatch(writes=(Write(_bag_key(), _Bag(("a", "b"))),))
    assert result.batch_id == batch_id(merged)
    assert result.batch_id != batch_id(proposed)
    _header, ordering = read_journal(state_dir / JOURNAL_NAME)
    assert ordering[-1] == batch_id(merged)


def test_an_unraced_batch_is_identified_exactly_as_it_was_proposed(
        tmp_path: Path) -> None:
    """Serial invariance: no race, no substitution, no moved id.

    A fire joins its gain onto the snapshot it read, so with nothing
    committing in between the store still HOLDS that snapshot and
    ``current ⊔ proposal`` IS the proposal. That is why the ruling is a
    no-op on the serial lane — the wall fixtures' batch ids do not move
    — and why replay by id keeps working there.
    """
    engine = toy_engine(tmp_path / "serial")
    engine.apply(CommitBatch(writes=(Write(_bag_key(), _Bag(("a",))),)))
    snapshot = engine.store.get(_bag_key())
    assert isinstance(snapshot, _Bag)
    proposed = CommitBatch(writes=(Write(_bag_key(), _join_bags(
        _bag_key(), snapshot, _Bag(("b",)))),))
    assert engine.apply(proposed).batch_id == batch_id(proposed)


# ------------------------------------------------ the staleness projection

def test_a_merge_declared_key_is_not_a_staleness_input(
        engine: CommitEngine) -> None:
    """The other half of "instead of version-validating that key".

    The identity a fire holds is re-derived at the wall and compared; a
    key the wall JOINS is projected out of both sides, because there is
    nothing for a fire to be stale ABOUT. Everything else still decides
    the discard — same engine, same shape, one key of each kind.
    """
    ground(engine, "region")
    keys = (_TILE, _SEED)
    identity = engine.attempt_identity(keys)
    assert engine.is_current(keys, identity)

    engine.apply(CommitBatch(writes=(
        Write(_TILE, TileRecord(observed_by=(FOOTING,))),)))
    assert engine.is_current(keys, identity), (
        "a joined key made a proposal stale")

    engine.apply(CommitBatch(writes=(Write(_SEED, make_seed(1)),)))
    assert not engine.is_current(keys, identity), (
        "an ordinary key stopped deciding the discard")


def test_the_projection_is_never_what_is_SPENT(engine: CommitEngine) -> None:
    """The durable identity keeps every key the worker read.

    Only the admit-or-discard decision moves: what a worker read is what
    it spent, so a later gain on a joined key still re-arms it through
    the ordinary idle test.
    """
    keys = (_TILE, _SEED)
    identity = engine.attempt_identity(keys)
    assert [key for key, _version in identity] == sorted(keys)
    assert [key for key, _version in drop_kinds(
        identity, frozenset({"tile"}))] == [_SEED]


# ------------------------------------------ the production family's laws

def _certify(engine: CommitEngine, *, bits: bytes = b"the certified bits",
             metadata_bit: int = 1, route: str = "scan",
             observed_by: tuple[str, ...] = ("cap:8/1",)) -> TileRecord:
    ground(engine, "pose")
    ref = engine.store.blobs.put(bits)
    record = TileRecord(MintRef(POSE, route, "fixture-decoder"), ref,
                        metadata_bit, observed_by)
    engine.apply(CommitBatch(writes=(Write(_TILE, record),)))
    return record


def test_a_stale_observation_no_longer_kills_a_certified_tile(
        engine: CommitEngine) -> None:
    """THE previously-fatal race, at the wall.

    A placement fire never binds the tiles it writes — they are search
    OUTPUT, unbindable pre-fire — so nothing discarded its proposal when
    a certificate landed underneath it, and its bare observation walked
    into ``certified content may not change``: lawful concurrency,
    fatal outcome. Now it joins. (The same race end-to-end, through the
    real pool, is ``tests/engine/test_pool.py``'s.)
    """
    certified = _certify(engine, observed_by=("cap:8/1",))
    engine.apply(CommitBatch(writes=(
        Write(_TILE, TileRecord(observed_by=("cap:2/1",))),)))
    stored = engine.store.get(_TILE)
    assert isinstance(stored, TileRecord)
    assert stored.minting == certified.minting
    assert stored.bits_ref == certified.bits_ref
    assert stored.observed_by == ("cap:2/1", "cap:8/1")


def test_two_certified_contents_for_one_tile_stay_fatal(
        engine: CommitEngine) -> None:
    """L5 is not relaxed by the join — a certificate is never voted on."""
    _certify(engine)
    with pytest.raises(CertificateConflict, match="disagree"):
        _certify(engine, bits=b"other bits")
    with pytest.raises(CertificateConflict, match="disagree"):
        _certify(engine, metadata_bit=0)


def test_two_AGREEING_certificates_corroborate(engine: CommitEngine) -> None:
    """Concurrency made this reachable, and it is not a contradiction.

    Two routes on one work key can both decode and both certify the same
    bits — before the pool the loser was discarded on the tile key's
    version, which is the compare-and-swap the hook replaces. The
    standing mint keeps the provenance and the loser's observation lands.
    """
    first = _certify(engine, route="scan", observed_by=("cap:8/1",))
    _certify(engine, route="union", observed_by=("cap:2/1",))
    stored = engine.store.get(_TILE)
    assert isinstance(stored, TileRecord)
    assert stored.minting == first.minting               # first names it
    assert stored.observed_by == ("cap:2/1", "cap:8/1")  # both observed

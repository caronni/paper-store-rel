"""The record registry: composition refusals and the schema manifest (R3).

core stores facts it does not know the shape of. What it must still get
right is the bookkeeping around that: one family per name and per key
kind, exactly one session identity, a manifest that IS the store's schema
identity, and a refusal that names the family when a state was written
under a different one.

The families used here are the composed production set (``conftest``),
plus locally declared toy families where the point is a composition
mistake — a registry is data, so a wrong one is buildable in three lines.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import pytest

from holo2.core import RecordFamily, RecordRegistry, RegistryError, compose
from holo2.core.records import CLOSE_KEY, CloseRecord, CloseStatus
from holo2.core.registry import UnknownRecordError
from holo2.core.journal import JOURNAL_NAME
from holo2.core.store import SCHEMA_VERSION, Store, StoreError
from conftest import make_session, registry


@dataclass(frozen=True)
class _Toy:
    value: int


@dataclass(frozen=True)
class _OtherToy:
    value: int


@dataclass(frozen=True)
class _Header:
    name: str


def _session_family() -> RecordFamily:
    return RecordFamily(_Header, None)


# ------------------------------------------------------------ composition

def test_a_registry_needs_exactly_one_session_identity() -> None:
    with pytest.raises(RegistryError, match="no session-identity family"):
        RecordRegistry([RecordFamily(_Toy, "toy")])
    with pytest.raises(RegistryError, match="both claim to be"):
        RecordRegistry([_session_family(), RecordFamily(_OtherToy, None)])


def test_one_family_per_name_and_per_kind() -> None:
    with pytest.raises(RegistryError, match="registered twice"):
        RecordRegistry([_session_family(), RecordFamily(_Toy, "toy"),
                        RecordFamily(_Toy, "other")])
    with pytest.raises(RegistryError, match="claimed by both"):
        RecordRegistry([_session_family(), RecordFamily(_Toy, "toy"),
                        RecordFamily(_OtherToy, "toy")])


def test_a_family_version_starts_at_one() -> None:
    with pytest.raises(RegistryError, match="version must be >= 1"):
        RecordFamily(_Toy, "toy", version=0)


def test_an_unregistered_record_is_refused_by_name() -> None:
    composed = RecordRegistry([_session_family(), RecordFamily(_Toy, "toy")])
    with pytest.raises(UnknownRecordError, match="_OtherToy"):
        composed.kind_of(_OtherToy(1))
    assert composed.kind_of(_Toy(1)) == "toy"
    assert composed.family_named("nope") is None


def test_compose_is_the_union_of_the_packages_declarations() -> None:
    manifest = dict(registry().manifest())
    # one family per package, spot-checked; every bump below the first is
    # the hash-free identity law (a record's key IS its defining values)
    assert manifest["SubjectSpec"] == 1            # core
    # capture: OR-12, then the identity law, then C3's pitch vote
    assert manifest["RegionRecord"] == 4
    assert manifest["PoseRecord"] == 5             # solve (W5's marking)
    assert manifest["EvidenceObservation"] == 4    # solve (W5's marking)
    assert manifest["TileRecord"] == 4              # solve (state deleted)
    assert manifest["WindowRecord"] == 5           # solve (outcome-only, W2)
    # THE HINT KIND IS GONE (H4 W2's clean-slate sweep, 2026-08-16). The
    # pull model ruled a hint a scheduling annotation and not a fact: a
    # window consults the committed poses around it at fire time, so
    # nothing about a steer crosses the wall and there is no family left
    # to register. A state written before the sweep names a family this
    # build does not have and therefore REFUSES AT OPEN — R3-lawful, and
    # the pre-freeze rule working exactly as designed (DESIGN §8). The
    # alternative — registering a dead family so old states still load —
    # would keep a vocabulary alive for records nothing can produce.
    assert "HintState" not in manifest
    assert manifest["CalibrationRecord"] == 2      # solve (ids)
    assert manifest["SessionIdentity"] == 2        # engine (policy by value)
    assert list(manifest) == sorted(manifest), "the manifest is sorted"


def test_the_session_family_is_the_one_without_a_kind() -> None:
    composed = registry()
    assert composed.session_family.kind is None
    assert composed.session_type.__name__ == "SessionIdentity"
    with pytest.raises(UnknownRecordError, match="not stored at a key"):
        composed.kind_of(make_session())


def test_structural_kinds_come_from_the_families() -> None:
    """Scheduling asks the registry, not a list it keeps itself.

    ``hint`` was in this set from H4 W2 package 2 until the clean-slate
    sweep deleted the family: the flag meant "a window's CHAIN descriptor
    exists only where a hint state does", and with the descriptor routes
    gone there is no expansion left for a hint to grow.
    """
    assert registry().structural_kinds() == frozenset(
        {"capture", "region", "window", "pose", "tile", "subject", "seed",
         "contradiction"})


# ---------------------------------------------------------- the manifest

def _starting_point(state_dir: Path) -> dict:
    """Line 1 of the journal: the fold's left endpoint (F-16)."""
    with open(state_dir / JOURNAL_NAME, "rb") as handle:
        return json.loads(handle.readline())


def test_the_starting_point_carries_the_manifest(
        new_store: Callable[..., Store]) -> None:
    store = new_store()
    store.close()
    header = _starting_point(store.state_dir)
    assert header["schema_version"] == SCHEMA_VERSION
    assert header["session_type"] == "SessionIdentity"
    assert [tuple(row) for row in header["families"]] == list(
        registry().manifest())


def test_a_manifest_mismatch_refuses_and_names_the_family(
        tmp_path: Path) -> None:
    """The R3 gate: a bumped family refuses the states written before it."""
    state_dir = tmp_path / "state"
    Store.create(state_dir, make_session(), registry()).close()

    # ``replace``, not a field-by-field copy: a family that grows a rule
    # (F-07's ``references`` did) must not silently lose it here.
    bumped = [
        family if family.name != "TileRecord"
        else replace(family, version=family.version + 1)
        for family in registry().families()
    ]
    # The bump is relative, so this gate does not move when a family's
    # real version does (the tile family is at v2 since the per-route
    # split put the route in ``MintRef``).
    with pytest.raises(StoreError, match=r"TileRecord: state v\d+ != build"):
        Store.open(state_dir, RecordRegistry(bumped))


def test_a_state_holding_an_unregistered_family_refuses(
        tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    with Store.create(state_dir, make_session(), registry()) as store:
        pass
    slim = RecordRegistry([family for family in registry().families()
                           if family.name != "LabelPool"])
    with pytest.raises(StoreError, match="LabelPool v1: this build registers "
                                         "no such family"):
        Store.open(state_dir, slim)


def test_a_store_refuses_a_session_of_the_wrong_type(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="not this build's session identity"):
        Store.create(tmp_path / "state", _Header("nope"), registry())


def test_the_registry_travels_with_the_store(
        new_store: Callable[..., Store]) -> None:
    store = new_store()
    assert store.registry.manifest() == registry().manifest()
    assert store.get(CLOSE_KEY) is None
    store.close()


def test_collections_are_declared_by_the_owning_family() -> None:
    """core asks the family; it does not dispatch on a kind it knows."""
    composed = registry()
    assert composed.collections_for(CLOSE_KEY, CloseRecord(CloseStatus.OPEN)) == ()
    assert composed.collections_for(CLOSE_KEY, None) == ()

"""F-07's relational half: a record may not name a record nobody committed.

The cheap half proved a record IS what its key says (``test_key_identity``);
this proves what it STANDS ON is there. One battery per DECLARING family,
each pinning the pair the ruling asks for:

* a write citing a missing reference refuses, naming BOTH keys — the
  referrer and the reference it could not find;
* the same write passes when the referee rides the SAME batch, which is
  the shape every real writer already has (a placement fire writes the
  window, the pose, the fit and the pieces in one transaction).

Plus the F-08-style meta-test: every family either declares references or
is listed here with the reason it has none, so an abstention stays a
ruling and never becomes an omission.

The refusal is an ordinary ``CommitRefusal`` and deliberately NOT a
``CertificateConflict``: a dangling reference is a WRONG WRITER, and the
terminal-fact path is for data that contradicts itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from holo2.core.blobs import stage_bytes
from holo2.core.commit import (CertificateConflict, CommitBatch, CommitEngine,
                               CommitRefusal, Write)
from holo2.core.keys import ResourceKey
from holo2.core.store import Store
from conftest import (CALIBRATION, CAPTURE_SHA, FOOTING, GROUND_ORDER,
                      GROUND_PARAMS, POSE, REGION, WINDOW, CalibrationRecord,
                      EvidenceObservation, HeldoutGate, LatticeSeedRecord,
                      MintRef, TileRecord, WordContradiction, capture_key,
                      contradiction_key, ground_batch,
                      lattice_seed_key, make_pose,
                      make_region, make_session, make_window, registry,
                      tile_key)

_LLR = stage_bytes(b"calibrated llrs")
_MASK = stage_bytes(b"observed cells")
_BITS = stage_bytes(b"certified bits")
_TILE = tile_key(0, 1, 2, "K")
_EVIDENCE = EvidenceObservation(
    footing_id=FOOTING, page=0, ty=1, tx=2, stream="K", pose_id=POSE,
    llr_ref=_LLR.ref, observed_ref=_MASK.ref, calibration_id=CALIBRATION)


def _certificate() -> TileRecord:
    return TileRecord(
                      minting=MintRef(POSE, "scan", "fixture-decoder"),
                      bits_ref=_BITS.ref, metadata_bit=1,
                      observed_by=(FOOTING,))


#: ``(family, key, record, the ground it stands on, the key it misses
#: when that ground is one stage short, the blobs the write needs)``.
#: The MISSING key is always the last link of the chain, so each case
#: proves its own declaration rather than an ancestor's.
CASES: tuple[tuple[str, ResourceKey, Any, str, ResourceKey, tuple], ...] = (
    ("RegionRecord", REGION, make_region(GROUND_PARAMS.ref), "capture",
     capture_key(CAPTURE_SHA), (GROUND_PARAMS,)),
    ("WindowRecord", WINDOW, make_window(), "region", REGION, ()),
    ("PoseRecord", POSE, make_pose(), "window", WINDOW, ()),
    ("EvidenceObservation", _EVIDENCE.resource_key(), _EVIDENCE,
     "calibration", CALIBRATION, (_LLR, _MASK)),
    ("CalibrationRecord", CALIBRATION, CalibrationRecord(
        scope=WINDOW, algorithm="pava-v1", params_ref=GROUND_PARAMS.ref,
        heldout=HeldoutGate(adopted=True, logloss_delta=-0.031)),
     "window", WINDOW, (GROUND_PARAMS,)),
    ("TileRecord", _TILE, _certificate(), "pose", POSE, (_BITS,)),
    # H4 W1/R5: the lattice seed stands on the surveyed REGION it is the
    # lattice of, and deliberately not on its source window — the fit
    # that measures a seed may be the one that then refuses its own
    # phase objective and writes no window record at all.
    ("LatticeSeedRecord", lattice_seed_key(FOOTING, REGION),
     LatticeSeedRecord(footing_id=FOOTING, region_id=REGION,
                       rows=(0.25, 0.0, 0.0, 0.25), source_window_id=WINDOW,
                       source_support_cells=40_000),
     "region", REGION, ()),
    # H4 W5: the contradiction stands on BOTH sides' poses — a quarantine
    # whose contributors nobody committed would condemn nothing and audit
    # nothing (``solve/contradiction.py``).
    ("WordContradiction", contradiction_key(FOOTING, 0, 1, 2),
     WordContradiction(footing_id=FOOTING, page=0, ty=1, tx=2,
                       expected_counter=66, decoded_counter=67, errors=3,
                       erasures=0, decoded_contributors=(POSE,)),
     "pose", POSE, ()),
)

_IDS = [case[0] for case in CASES]


def _short(stage: str) -> str:
    """The ground one stage SHORT of ``stage`` — where the reference dies."""
    return GROUND_ORDER[GROUND_ORDER.index(stage) - 1] if stage != "capture" \
        else "capture"


@pytest.mark.parametrize("family,key,record,stage,missing,blobs", CASES,
                         ids=_IDS)
def test_a_write_citing_a_missing_reference_refuses_naming_both_keys(
        tmp_path: Path, family: str, key: ResourceKey, record: Any,
        stage: str, missing: ResourceKey, blobs: tuple) -> None:
    store = Store.create(tmp_path / "state", make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    if stage != "capture":                       # everything but the miss
        engine.apply(ground_batch(_short(stage)))
    with pytest.raises(CommitRefusal) as caught:
        engine.apply(CommitBatch(writes=(Write(key, record),), blobs=blobs))
    message = str(caught.value)
    assert str(key) in message and str(missing) in message
    # A wrong writer, not a contradiction: never the terminal-fact path.
    assert not isinstance(caught.value, CertificateConflict)
    assert store.get(key) is None
    store.close()


@pytest.mark.parametrize("family,key,record,stage,missing,blobs", CASES,
                         ids=_IDS)
def test_a_referee_in_the_same_batch_satisfies_the_reference(
        tmp_path: Path, family: str, key: ResourceKey, record: Any,
        stage: str, missing: ResourceKey, blobs: tuple) -> None:
    """Batch inclusion is lawful — the shape every real writer has."""
    store = Store.create(tmp_path / "state", make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    base = ground_batch(stage)
    engine.apply(CommitBatch(writes=base.writes + (Write(key, record),),
                             blobs=base.blobs + tuple(blobs)))
    assert store.get(key) == record
    assert store.get(missing) is not None
    store.close()


def test_the_store_satisfies_a_reference_committed_earlier(
        tmp_path: Path) -> None:
    """The other half of the resolution: batch OR store, never neither."""
    store = Store.create(tmp_path / "state", make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    engine.apply(ground_batch("pose"))              # an earlier commit
    engine.apply(CommitBatch(writes=(Write(_TILE, _certificate()),),
                             blobs=(_BITS,)))
    assert store.get(_TILE) == _certificate()
    store.close()


def test_a_union_certificate_needs_every_contributor(tmp_path: Path) -> None:
    """M10: the mint's full provenance set is checked, not only the witness."""
    store = Store.create(tmp_path / "state", make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    engine.apply(ground_batch("pose"))
    stranger = make_pose(native_affine=(1.0, 0.0, 9.5, 0.0, 1.0, -2.5))
    union = TileRecord(
        minting=MintRef(POSE, "union", "fixture-decoder",
                        contributors=tuple(sorted(
                            (POSE, stranger.resource_key())))),
        bits_ref=_BITS.ref, metadata_bit=1, observed_by=(FOOTING,))
    with pytest.raises(CommitRefusal, match="no committed record stands at"):
        engine.apply(CommitBatch(writes=(Write(_TILE, union),),
                                 blobs=(_BITS,)))
    # With the contributor committed, the same certificate stands.
    engine.apply(CommitBatch(
        writes=(Write(stranger.resource_key(), stranger),
                Write(_TILE, union)), blobs=(_BITS,)))
    assert store.get(_TILE) == union
    store.close()


def test_an_uncertified_tile_declares_nothing(tmp_path: Path) -> None:
    """The state gate is exact: only a certificate carries a mint."""
    store = Store.create(tmp_path / "state", make_session(), registry(),
                         snapshot_every=1)
    engine = CommitEngine(store)
    engine.apply(CommitBatch(writes=(
        Write(_TILE, TileRecord(
                                observed_by=(FOOTING,))),)))
    assert store.get(_TILE) is not None            # no pose, no reference
    store.close()


# ------------------------------------------------------- the meta-test

#: Families that declare NO references, each with the reason it has none
#: (the F-08 pinned-non-law pattern). A new family must land in one list
#: or the other; silence is what this test forbids.
PINNED_ABSTENTIONS: dict[str, str] = {
    "CaptureRecord": "an acquisition is a ROOT fact (L1) — it stands on the "
                     "authenticated bytes, and its footings name itself",
    "LabelPool": "no writer exists yet (B8/CA1–CA7): a reference law "
                 "constrains a writer's batch shape, and its members are "
                 "window KEYS, which are plans long before they are records",
    "SubjectSpec": "its parent is an opaque provider string, not a key",
    "CloseRecord": "it names a payload by CONTENT ADDRESS — bulk, which "
                   "the wall checks separately — and no keyed record",
    "SessionIdentity": "the envelope header is not stored at a key and "
                       "binds its lineage by value",
}


def test_every_family_declares_references_or_a_pinned_reason() -> None:
    declaring = {family.name for family in registry().families()
                 if family.references is not None}
    abstaining = {family.name for family in registry().families()
                  if family.references is None}
    assert declaring == set(_IDS)
    assert abstaining == set(PINNED_ABSTENTIONS)
    assert all(reason for reason in PINNED_ABSTENTIONS.values())


def test_a_declaration_is_a_pure_function_of_key_and_record() -> None:
    """It may READ nothing: no store, no batch — the wall resolves."""
    composed = registry()
    for _family, key, record, _stage, _missing, _blobs in CASES:
        first = composed.references_of(key, record)
        assert first == composed.references_of(key, record)
        assert all(isinstance(reference, ResourceKey) for reference in first)

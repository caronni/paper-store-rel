"""F-07's relational half, at solve's own declarations.

The wall's mechanics are pinned in ``tests/core/test_references.py``;
what is pinned HERE is what each of solve's families says it stands on —
at the callable and at the registration, so a refactor that drops a
``references=`` fails here rather than in a decode three sheets later.

The laws: a certificate names its minting pose and every contributor, and
only when CERTIFIED; a pose names its window; a window names its region;
a piece of evidence names its pose AND its calibration; a fit names its
scope; and a lattice seed names the region it is the lattice of. The ONE
abstention left, ``pool``, is pinned with its reason, the F-08
pinned-non-law pattern.
"""
from __future__ import annotations

from holo2.capture import region_key
from holo2.core.records import BlobRef
from holo2.solve.families import record_families
from holo2.solve.records import (CalibrationRecord, EvidenceObservation,
                                 HeldoutGate, LabelPool, MintRef,
                                 PoseRecord, TileRecord,
                                 WindowRecord, WindowStatus, calibration_key,
                                 pose_key,
                                 tile_key, window_key)

FOOTING = "cap:8/1"
REGION = region_key("ab" * 32, (0, 0), 8, (128, 128))
WINDOW = window_key(FOOTING, REGION, (0, 0, 64, 64))
AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
POSE = pose_key(WINDOW, 0, AFFINE)
BLOB = BlobRef("cd" * 32, 8)
CALIBRATION = calibration_key(WINDOW, "pava-v1", BLOB.sha256)


def _family(kind: str):
    return {family.kind: family for family in record_families((0,))}[kind]


def _references(kind: str, key, record):
    return _family(kind).references(key, record)


def test_a_certificate_names_its_pose_and_every_contributor() -> None:
    key = tile_key(0, 1, 2, "K")
    other = pose_key(WINDOW, 0, (1.0, 0.0, 4.0, 0.0, 1.0, 0.0))
    record = TileRecord(
        minting=MintRef(POSE, "union", "bp-60",
                        contributors=tuple(sorted((POSE, other)))),
        bits_ref=BLOB, metadata_bit=1)
    assert _references("tile", key, record) == (POSE, *sorted((POSE, other)))


def test_a_tile_below_certified_names_nothing() -> None:
    """Footing ids are not keys, and only a certifying write has a mint."""
    key = tile_key(0, 1, 2, "K")
    assert _references("tile", key, TileRecord(
        observed_by=(FOOTING,), baselined=(FOOTING,))) == ()


def test_geometry_names_the_record_it_hangs_off() -> None:
    pose = PoseRecord(window_id=WINDOW, footing_id=FOOTING, page=0,
                      native_affine=AFFINE)
    assert _references("pose", POSE, pose) == (WINDOW,)
    window = WindowRecord(FOOTING, REGION, (0, 0, 64, 64),
                          WindowStatus.ACTIVE)
    assert _references("window", WINDOW, window) == (REGION,)


def test_a_piece_names_its_pose_and_its_calibration() -> None:
    record = EvidenceObservation(
        footing_id=FOOTING, page=0, ty=1, tx=2, stream="K", pose_id=POSE,
        llr_ref=BLOB, observed_ref=BLOB, calibration_id=CALIBRATION)
    assert _references("evidence", record.resource_key(), record) == (
        POSE, CALIBRATION)


def test_a_fit_names_its_scope() -> None:
    record = CalibrationRecord(
        scope=WINDOW, algorithm="pava-v1", params_ref=BLOB,
        heldout=HeldoutGate(adopted=True, logloss_delta=-0.1))
    assert _references("calibration", record.resource_key(), record) == (
        WINDOW,)


def test_the_one_abstention_is_declared_not_forgotten() -> None:
    """A label pool has no writer yet, so it can have no reference law.

    The reason is a RULING recorded at the registration
    (``solve/records.py``): a pool's members are window keys, which are
    plans long before they are records — a claim about a writer
    B8/CA1–CA7 has not built.
    """
    assert _family("pool").references is None
    # And it still holds its own laws, so this is an abstention from ONE
    # rule rather than a family nobody constrained.
    assert _family("pool").transition is not None
    pool = LabelPool("pool-1", (WINDOW,))
    assert pool.member_window_ids == (WINDOW,)

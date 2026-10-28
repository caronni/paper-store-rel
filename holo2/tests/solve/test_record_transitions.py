"""F-08: solve's transition laws — what may follow what under one key.

The commit wall runs a family's ``transition`` on every write over a
standing record (``registry.check_transition``); these tests pin each
rule at the callable, plus the registration (a refactor that drops a
``transition=`` must fail HERE, not in a decode three sheets later).

The laws under test, one per family: windows move freely among their
scheduling states and RETIRED is terminal; evidence and calibration are
frozen (equal passes — the wall sees equal writes before its no-change
skip — different refuses, naming what moved); pools only grow; poses
need no rule (every field is identity). The hint family had a retention
law of its own until H4 W2's clean-slate sweep deleted the family; the
tree's other improve-only law, R5's lattice seed, is pinned with the
record it belongs to (``tests/solve/test_placement.py``).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from holo2.core import CommitRefusal, StateRegression
from holo2.solve.families import record_families
from holo2.solve.records import (CalibrationRecord, EvidenceObservation,
                                 HeldoutGate, LabelPool, PoseRecord,
                                 WindowRecord, WindowStatus,
                                 calibration_key, evidence_key,
                                 pool_key, window_key)
from holo2.core.records import BlobRef

FOOTING = "f:abcdef123456/2"
REGION_PARTS = ("region", "a" * 64, 0, 0, 16, 128, 128)


def _family(kind: str):
    families = {family.kind: family for family in record_families((0,))}
    return families[kind]


def _region_key():
    from holo2.capture import region_key
    return region_key("a" * 64, (0, 0), 16, (128, 128))


def _window(status: WindowStatus, reason: str | None = None) -> WindowRecord:
    return WindowRecord(footing_id=FOOTING, region_id=_region_key(),
                        extent_cells=(0, 0, 64, 64), status=status,
                        retired_reason=reason)


def _blob(tag: str) -> BlobRef:
    return BlobRef(sha256=tag * 64, length_bytes=64)


def _evidence(llr: str = "a", observed: str = "b",
              calibration: str = "c" * 64) -> EvidenceObservation:
    window = window_key(FOOTING, _region_key(), (0, 0, 64, 64))
    from holo2.solve.records import pose_key
    pose = pose_key(window, 0, (1.0, 0.0, 0.0, 0.0, 1.0, 0.0))
    return EvidenceObservation(
        footing_id=FOOTING, page=0, ty=1, tx=2, stream="main", pose_id=pose,
        llr_ref=_blob(llr), observed_ref=_blob(observed),
        calibration_id=calibration_key(window, "pava", calibration))


def _calibration(adopted: bool = True) -> CalibrationRecord:
    window = window_key(FOOTING, _region_key(), (0, 0, 64, 64))
    return CalibrationRecord(
        scope=window, algorithm="pava", params_ref=_blob("d"),
        heldout=HeldoutGate(adopted=adopted, logloss_delta=0.25,
                            refusal_reason=None if adopted else "unit"),
    )


# ------------------------------------------------------------------ window

def test_the_two_outcomes_move_in_the_one_lawful_direction() -> None:
    """Window v5 (H4 W2): the vocabulary is OUTCOMES, so this is short.

    ``PENDING`` and ``SLEEPING`` were scheduling states, and the law had
    to permit them moving in every direction; with the pull model's
    memory in the scheduler, the only move a record can make is placed ->
    retired, and even that is not reached in practice (a placed window
    leaves the set). The law is stated for the fact, not the writer.
    """
    transition = _family("window").transition
    key = window_key(FOOTING, _region_key(), (0, 0, 64, 64))
    assert [status.name for status in WindowStatus] == ["ACTIVE", "RETIRED"]
    transition(key, _window(WindowStatus.ACTIVE),
               _window(WindowStatus.RETIRED, "unit"))
    transition(key, _window(WindowStatus.ACTIVE),
               _window(WindowStatus.ACTIVE))


def test_a_retired_window_is_terminal() -> None:
    transition = _family("window").transition
    key = window_key(FOOTING, _region_key(), (0, 0, 64, 64))
    retired = _window(WindowStatus.RETIRED, "done_covered")
    transition(key, retired, retired)          # equal rewrite is a no-op
    with pytest.raises(StateRegression, match="terminal"):
        transition(key, retired, _window(WindowStatus.ACTIVE))
    with pytest.raises(StateRegression, match="terminal"):
        transition(key, retired,
                   _window(WindowStatus.RETIRED, "another reason"))


def test_the_reason_rides_exactly_the_retired_status() -> None:
    """F-08's illegal-sum-state half, at construction (commit AND load)."""
    with pytest.raises(ValueError, match="rides exactly the RETIRED"):
        _window(WindowStatus.ACTIVE, "why is a live window explaining")
    with pytest.raises(ValueError, match="rides exactly the RETIRED"):
        _window(WindowStatus.RETIRED, None)


# ---------------------------------------------------------------- evidence

def test_evidence_is_frozen_and_names_what_moved() -> None:
    transition = _family("evidence").transition
    piece = _evidence()
    key = piece.resource_key()
    transition(key, piece, _evidence())        # equal rewrite is a no-op
    with pytest.raises(CommitRefusal, match="llr_ref"):
        transition(key, piece, _evidence(llr="e"))
    with pytest.raises(CommitRefusal, match="calibration_id"):
        transition(key, piece, _evidence(calibration="f" * 64))


# ------------------------------------------------------------- calibration

def test_a_calibration_verdict_never_flips() -> None:
    transition = _family("calibration").transition
    fit = _calibration(adopted=True)
    key = fit.resource_key()
    transition(key, fit, _calibration(adopted=True))     # equal: no-op
    with pytest.raises(CommitRefusal, match="held-out verdict"):
        transition(key, fit, _calibration(adopted=False))


# ------------------------------------------------------------------- pool

def test_a_label_pool_only_grows() -> None:
    transition = _family("pool").transition
    key = pool_key("unit-pool")
    windows = tuple(sorted(
        window_key(FOOTING, _region_key(), (0, x, 64, 64))
        for x in (0, 64)))
    small = LabelPool("unit-pool", windows[:1],
                      label_site_count_by_kind=(("k", 3),))
    grown = LabelPool("unit-pool", windows,
                      label_site_count_by_kind=(("k", 5), ("w", 1)))
    transition(key, small, grown)
    transition(key, grown, grown)              # equal rewrite is a no-op
    with pytest.raises(CommitRefusal, match="drops member windows"):
        transition(key, grown, small)
    with pytest.raises(CommitRefusal, match="shrinks label counts for k"):
        transition(key, small,
                   LabelPool("unit-pool", windows,
                             label_site_count_by_kind=(("k", 2),)))
    with pytest.raises(CommitRefusal, match="shrinks label counts for k"):
        transition(key, small, LabelPool("unit-pool", windows))


# ------------------------------------------------- declared non-rules

def test_a_pose_moves_only_by_the_declared_quarantine_marking() -> None:
    """W5 ended the one deliberate absence, and it ended it LOUDLY.

    Through v4 the pose family declared no transition because every
    field was identity. W5 gave it one non-identity field, so the law
    is now written: ``quarantined`` may go ``False -> True``, once, and
    nothing else about committed geometry may move under its name.
    """
    check = _family("pose").transition
    assert check is not None
    affine = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    window = window_key(FOOTING, _region_key(), (0, 0, 64, 64))
    standing = PoseRecord(window, FOOTING, 0, affine)
    key = standing.resource_key()
    condemned = replace(standing, quarantined=True)
    check(key, standing, standing)                     # a no-op is lawful
    check(key, standing, condemned)                    # the declared move
    with pytest.raises(CommitRefusal, match="one direction"):
        check(key, condemned, standing)                # never rehabilitated
    with pytest.raises(CommitRefusal, match="frozen"):
        check(key, standing, replace(condemned, footing_id="other:2/1"))


def test_every_family_that_owes_a_transition_declares_one() -> None:
    """The registration pin: dropping a ``transition=`` fails here."""
    owed = {"tile", "window", "evidence", "pool", "calibration", "seed",
            "pose", "contradiction"}
    declared = {family.kind for family in record_families((0,))
                if family.transition is not None}
    assert owed <= declared

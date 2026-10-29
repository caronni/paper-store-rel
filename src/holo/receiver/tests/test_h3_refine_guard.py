"""The already-stood guard, and the certificate invariant it protects.

RULINGS.md D4 (Germano, 2026-09-03): holo3 keeps the refinement chain
and the single evidence namespace, and gains holo2's guard — a revision
whose geometry the window has already stood at is refused before any
pixel is read through it.  What the single namespace risks is a re-read
that supersedes the read it was meant to improve on, so the tripwire
here is the brief's own bar: on a stimulus whose refinement lane
actually adopts, the certificate set before an adoption survives it.

The composed-drift census that the same ruling ordered, over the
archived event streams, is `measure/refine_chains/`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction

import numpy as np

from holo.receiver import data
from holo.receiver.plugins import color_refine, refine
from holo.receiver.tests import _h3_facts, _h3_support

# a pose with a real rotation and a real pitch, so a walked-back
# revision has something to lose in the recomposition
BASE_AFFINE = (7.0, 0.02, 60.0, -0.03, 7.05, 50.0)
BASE_CELLS = np.stack(
    np.meshgrid(np.arange(8), np.arange(8), indexing="ij"),
    axis=-1).reshape(-1, 2)

REFINEMENT_LANES = ("refine", "refine.color")

# (label, one fine grid step, does the walk-back recompose bit-exactly)
# — measured 2026-09-04 on this arithmetic: a pure translation does,
# because the origin shift is the same product subtracted again; a
# rotation does not, and it is the case the quantum exists for.
WALK_BACKS = ((0.0, refine.PHASE_FINE_STEP_CELLS, 0.0, True),
              (refine.ANGLE_FINE_STEP_DEG, 0.0, 0.0, False))


def _pose():
    return refine.local_segment(BASE_AFFINE, Fraction(1), BASE_CELLS)[0]


def _native(pose) -> tuple[float, ...]:
    return refine.native_terms(pose, BASE_CELLS, Fraction(1))


def _walked_back(dtheta_deg: float, du: float, dv: float):
    there = refine.pose_candidate(_pose(), dtheta_deg, du, dv)
    return refine.pose_candidate(there, -dtheta_deg, -du, -dv)


def _spread(one: tuple[float, ...], other: tuple[float, ...]) -> float:
    return float(np.max(np.abs(np.asarray(one) - np.asarray(other))))


def test_the_pose_quantum_collapses_a_walked_back_fit_and_nothing_else():
    """Why POSE_TERM_DECIMALS is 6, measured on holo3's own arithmetic.

    A search that walks away and back does not return the affine it
    started from: the rotation and the origin are recomposed in floats.
    The quantum has to be coarse enough to collapse that residual and
    fine enough to keep one fine-grid step apart.
    """
    quantum = 10.0 ** -refine.POSE_TERM_DECIMALS
    base = _native(_pose())
    checks = _h3_support.Checks("pose quantum")
    for dtheta, du, dv, exact in WALK_BACKS:
        label = "rotation" if dtheta else "translation"
        back = _native(_walked_back(dtheta, du, dv))
        step = _native(refine.pose_candidate(_pose(), dtheta, du, dv))
        residual, moved = _spread(base, back), _spread(base, step)
        checks.equal(f"{label} walk-back recomposes bit-exactly",
                     back == base, exact)
        checks.check(f"{label} walk-back residual {residual:.3e} px is a "
                     f"hundredth of the quantum", residual < quantum / 100.0)
        checks.check(f"{label} fine step {moved:.3e} px is a hundred "
                     f"quanta", moved > quantum * 100.0)
        checks.equal(f"{label} walk-back is one pose with the base",
                     refine.pose_key(back), refine.pose_key(base))
        checks.check(f"{label} fine step is a different pose",
                     refine.pose_key(step) != refine.pose_key(base))
    checks.assert_clean()


def test_pose_key_normalises_the_sign_of_a_rounded_zero():
    assert refine.pose_key((-1e-9,)) == (0.0,)
    assert repr(refine.pose_key((-1e-9,))) == repr((0.0,))


def test_a_window_stands_at_its_own_pose_and_at_every_revision_it_took():
    placement = _h3_facts.placement()
    assert refine.stood_poses(placement) == {
        refine.pose_key(placement.native_affine)}
    older = refine.pose_key((1.0, 0.0, 2.0, 0.0, 1.0, 3.0))
    chained = replace(placement, stood_affines=(older,))
    assert refine.stood_poses(chained) == {
        older, refine.pose_key(placement.native_affine)}


def test_a_candidate_inside_the_quantum_of_a_stood_pose_is_that_pose():
    placement = _h3_facts.placement()
    stood = refine.stood_poses(placement)
    near = tuple(term + 1e-9 for term in placement.native_affine)
    far = tuple(term + 1e-3 for term in placement.native_affine)
    assert refine.pose_key(near) in stood, (
        "a sub-quantum re-proposal is the geometry it started from")
    assert refine.pose_key(far) not in stood, (
        "a genuinely new geometry is not refused")


def test_both_refinement_lanes_refuse_through_the_one_predicate():
    """The colour lane owns no copy of the guard (the cell-class law)."""
    assert color_refine.pose_key is refine.pose_key
    assert color_refine.stood_poses is refine.stood_poses
    assert color_refine.OUTCOME_ALREADY_STOOD is refine.OUTCOME_ALREADY_STOOD
    for module in (refine, color_refine):
        source = (_h3_support.HOLO3_ROOT
                  / f"plugins/{module.__name__.rsplit('.', 1)[1]}.py"
                  ).read_text()
        assert "pose_key(affine) in stood_poses(placement)" in source, (
            f"{module.__name__} does not consult the pose history before "
            f"it adopts")


def test_an_adopted_revision_carries_the_geometry_it_leaves_behind():
    placement = _h3_facts.placement()
    revised_affine = tuple(term + 0.5 for term in placement.native_affine)
    revised = refine.revised_placement(
        placement,
        refine.Revision(True, refine.OUTCOME_ADOPTED, revised_affine,
                        basis=((0, 1, 1),)))
    assert revised.stood_affines == (
        refine.pose_key(placement.native_affine),)
    assert refine.stood_poses(revised) == {
        refine.pose_key(placement.native_affine),
        refine.pose_key(revised_affine)}, (
        "what a second revision is guarded against is the original "
        "accepted placement plus every adopted revision, this one included")


def _revised(placement: data.Placement) -> data.Placement:
    return refine.revised_placement(
        placement,
        refine.Revision(True, refine.OUTCOME_ADOPTED,
                        tuple(term + 0.5
                              for term in placement.native_affine)))


def test_the_pose_history_survives_the_snapshot_a_resume_folds_back(
        tmp_path):
    """Resume is where the guard's memory would otherwise be lost.

    The chain runs across runs — sheet I took four, sheet J five — and
    the snapshot carries the standing placement, not the fact stream, so
    the history has to ride on the placement to survive at all.
    """
    from holo.receiver import snapshot

    revised = _revised(_h3_facts.placement())
    path = tmp_path / snapshot.NAME
    snapshot.write(path, (revised,))
    back = snapshot.read(path)[0]
    assert back.stood_affines == revised.stood_affines
    assert refine.stood_poses(back) == refine.stood_poses(revised)


def test_a_snapshot_written_before_the_field_existed_still_resumes(
        tmp_path):
    from holo.receiver import snapshot

    written = tmp_path / snapshot.NAME
    snapshot.write(written, (_revised(_h3_facts.placement()),))
    with np.load(written) as handle:
        spine = json.loads(bytes(handle["meta"]).decode())
        blob = handle["blob"]
    node = spine["facts"][0]
    node[2] = [row for row in node[2] if row[0] != "stood_affines"]
    older = tmp_path / "older.npz"
    with open(older, "wb") as stream:
        np.savez_compressed(
            stream, blob=blob,
            meta=np.frombuffer(json.dumps(spine).encode(), np.uint8))
    back = snapshot.read(older)[0]
    assert back.stood_affines == (), (
        "an archived state predates the field and must fold back with an "
        "empty history rather than refuse")


def test_the_placement_ordinal_still_cannot_see_the_pose_history():
    placement = _h3_facts.placement()
    chained = replace(placement, stood_affines=(
        refine.pose_key((1.0, 0.0, 2.0, 0.0, 1.0, 3.0)),))
    assert (data.placement_ordinal(chained)
            == data.placement_ordinal(placement)), (
        "the history is evidence for the guard, never a rank: two "
        "placements that differ only in where they have been must adopt "
        "against each other exactly as before")


def _adoption_snapshots(record: object, lane: str) -> tuple[tuple, ...]:
    """The certified set as each adoption of `lane` folded, in order."""
    standing: set[tuple] = set()
    snapshots: list[tuple] = []
    for event in record.events:
        if isinstance(event, data.TileOutcome):
            if event.result == "certified":
                standing.add((event.page, event.ty, event.tx,
                              event.stream_id))
        elif (isinstance(event, data.JobDone) and event.plugin == lane
                and event.n_poses):
            snapshots.append(tuple(sorted(standing)))
    return tuple(snapshots)


def _assert_no_certificate_is_lost(record: object, lane: str) -> None:
    snapshots = _adoption_snapshots(record, lane)
    assert snapshots, (
        f"{lane} adopted nothing on this stimulus, so the tripwire is "
        f"vacuous — re-measure the stimulus before trusting it")
    final = set(record.certificates)
    assert set(snapshots[-1]) <= final
    for ordinal, standing in enumerate(snapshots):
        lost = sorted(set(standing) - final)
        assert not lost, (
            f"{lane} adoption {ordinal + 1} of {len(snapshots)} on "
            f"{record.label}: {len(lost)} certificate(s) standing before "
            f"the adoption are not in the run's final set, first {lost[0]} "
            f"— an adopted revision must never cost a read that was "
            f"already terminal (RULINGS.md D4)")


def test_no_certificate_is_lost_across_a_colour_refinement_adoption(
        decode_color_w1):
    #: The stimulus the ruling names — the colour sim under `--complete`,
    #: `SCHEDULE.md` "Evidence so far".  That fixture is the widened
    #: matrix, not the slow lane, so the K twin below is the one the
    #: ordinary lane runs; measured here 2026-09-04: 33 fires, 5
    #: adoptions (SCHEDULE.md's 14/2 is an older tree).
    _assert_no_certificate_is_lost(decode_color_w1, "refine.color")


def test_no_certificate_is_lost_across_a_k_refinement_adoption(
        decode_k_degraded_w1):
    _assert_no_certificate_is_lost(decode_k_degraded_w1, "refine")


def test_the_lanes_the_tripwire_watches_are_the_scheduled_ones():
    from holo.receiver import engine

    names = {descriptor.name for descriptor in engine.DESCRIPTORS}
    assert set(REFINEMENT_LANES) <= names

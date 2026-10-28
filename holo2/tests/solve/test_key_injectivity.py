"""Record keys are their defining values, and no two values share a key.

The identity law's other half (core's is
``tests/core/test_identity_law.py``): a region, a window, a pose, a
lattice seed and a calibration are named by what they ARE, so the
adversarial question is whether two different things can land on one
name.

They cannot, and not by luck of the alphabet: **every kind has a fixed
arity**, so an embedded id occupies a known slice of its container's
parts and a concatenation cannot be re-cut. The tests below take pairs
whose flat renderings coincide — adjacent integers, a delimiter inside a
field, a footing spelled like a capture — and pin that the keys differ.
"""
from __future__ import annotations

import pytest

from holo2.capture import (REGION_KEY_PARTS, parse_region_key, region_key)
from holo2.core import MalformedKeyError, ResourceKey, key_parts
from holo2.solve import (calibration_key, evidence_key,
                         parse_evidence_key, parse_tile_key, parse_window_key,
                         pose_key, tile_key, window_key)
from holo2.solve.records import (EVIDENCE_KEY_PARTS, EVIDENCE_SPEC,
                                 POSE_KEY_PARTS, POSE_SPEC, WINDOW_KEY_PARTS,
                                 WINDOW_SPEC)

CAPTURE = "ab" * 32
FOOTING = "abcdefabcdef:8/1"
REGION = region_key(CAPTURE, (64, 96), 8, (320, 480))
WINDOW = window_key(FOOTING, REGION, (0, 0, 160, 160))
AFFINE = (1.0, 0.0, 3.5, 0.0, 1.0, -2.5)


def test_the_arities_are_fixed_and_composed() -> None:
    """Each kind is "the embedded id, plus this kind's own values"."""
    assert len(REGION.parts) == REGION_KEY_PARTS
    assert len(WINDOW.parts) == WINDOW_KEY_PARTS == 1 + REGION_KEY_PARTS + 4
    pose = pose_key(WINDOW, 0, AFFINE)
    assert len(pose.parts) == POSE_KEY_PARTS == WINDOW_KEY_PARTS + 7
    assert len(evidence_key(FOOTING, 0, 1, 2, "K", pose).parts) == (
        EVIDENCE_KEY_PARTS)


def test_the_region_key_cannot_be_re_cut() -> None:
    """Adjacent integers that CONCATENATE alike stay two regions."""
    first = region_key(CAPTURE, (1, 23), 4, (5, 6))
    second = region_key(CAPTURE, (12, 3), 4, (5, 6))
    assert "".join(first.parts) == "".join(second.parts)
    assert first != second
    assert parse_region_key(first) == (CAPTURE, (1, 23), 4, (5, 6))


def test_the_region_key_separates_captures_and_geometry() -> None:
    base = region_key(CAPTURE, (1, 2), 3, (4, 5))
    assert base != region_key("cd" * 32, (1, 2), 3, (4, 5))
    assert base != region_key(CAPTURE, (1, 2), 3, (4, 50))
    assert base != region_key(CAPTURE, (1, 2), 30, (4, 5))


def test_the_window_key_cannot_be_re_cut() -> None:
    """The region occupies a fixed slice; nothing shifts into or out of it."""
    left = window_key(FOOTING, region_key(CAPTURE, (1, 2), 3, (4, 5)),
                      (6, 7, 8, 9))
    right = window_key(FOOTING, region_key(CAPTURE, (1, 2), 3, (4, 5)),
                       (6, 7, 8, 90))
    shifted = window_key(FOOTING, region_key(CAPTURE, (1, 2), 3, (4, 56)),
                         (7, 8, 9, 0))
    assert left != right != shifted and left != shifted
    assert parse_window_key(left) == (
        FOOTING, region_key(CAPTURE, (1, 2), 3, (4, 5)), (6, 7, 8, 9))


def test_the_footing_and_the_capture_are_two_positions() -> None:
    """Part 0 is the footing, part 1 the capture — positionally, always."""
    swapped = window_key(CAPTURE, region_key(CAPTURE, (1, 2), 3, (4, 5)),
                         (6, 7, 8, 9))
    assert swapped != window_key(FOOTING,
                                 region_key(CAPTURE, (1, 2), 3, (4, 5)),
                                 (6, 7, 8, 9))


def test_the_pose_key_carries_its_parameters_exactly() -> None:
    """A pose IS its window and its fit — to the last float bit."""
    nudged = (1.0, 0.0, 3.5, 0.0, 1.0, -2.5 - 1e-15)
    assert pose_key(WINDOW, 0, AFFINE) == pose_key(WINDOW, 0, AFFINE)
    assert pose_key(WINDOW, 0, AFFINE) != pose_key(WINDOW, 0, nudged)
    assert pose_key(WINDOW, 0, AFFINE) != pose_key(WINDOW, 1, AFFINE)
    recovered = tuple(float(part)
                      for part in pose_key(WINDOW, 0, AFFINE).parts[-6:])
    assert recovered == AFFINE                         # repr round-trips


def test_composites_of_a_window_stay_separable() -> None:
    """A pose embeds its window's parts and cannot be confused with it.

    (The hint key was the sharp case here — its parts were the window's
    EXACTLY, so the kind was the whole discriminator — until H4 W2's
    clean-slate sweep deleted that family. The claim survives it: an
    embedded id occupies a known slice, and the kind is never part of the
    flat rendering.)
    """
    pose = pose_key(WINDOW, 0, AFFINE)
    assert pose.kind != WINDOW.kind
    assert pose.parts[:WINDOW_KEY_PARTS] == WINDOW.parts
    assert pose.parts != WINDOW.parts


def test_the_evidence_key_recovers_its_pose() -> None:
    pose = pose_key(WINDOW, 0, AFFINE)
    key = evidence_key(FOOTING, 0, 1, 2, "K", pose)
    assert parse_evidence_key(key) == (FOOTING, 0, 1, 2, "K", pose)
    assert key != evidence_key(FOOTING, 0, 1, 2, "K",
                               pose_key(WINDOW, 1, AFFINE))
    assert key != evidence_key(FOOTING, 0, 12, 2, "K", pose)


def test_the_calibration_key_separates_two_fits_of_one_window() -> None:
    """Same scope, same algorithm, different numbers: two calibrations."""
    first = calibration_key(WINDOW, "pava-v1", "ab" * 32)
    assert first == calibration_key(WINDOW, "pava-v1", "ab" * 32)
    assert first != calibration_key(WINDOW, "pava-v1", "cd" * 32)
    assert first != calibration_key(WINDOW, "pava-v2", "ab" * 32)
    # The scope's KIND leads, so a pool scope and a window scope with the
    # same parts are still two scopes.
    assert first != calibration_key(ResourceKey("pool", WINDOW.parts),
                                    "pava-v1", "ab" * 32)


def test_the_declarative_builders_render_the_hand_written_spelling() -> None:
    """The gate for moving the builders onto ``KeySpec``: same bytes.

    A printed layout keys on these, so the only acceptable evidence that a
    declarative builder replaced a hand-written one is that every existing
    spelling comes out identical. The right-hand sides below are the
    pre-``KeySpec`` bodies, written out inline: ``key_parts`` over the
    kind's own values with an embedded id's parts spliced in at the
    position that kind puts them.
    """
    assert region_key(CAPTURE, (64, 96), 8, (320, 480)) == ResourceKey(
        "region", key_parts(CAPTURE, 64, 96, 8, 320, 480))

    window = window_key(FOOTING, REGION, (0, 0, 160, 160))
    assert window == ResourceKey(
        "window", key_parts(FOOTING, *REGION.parts, *(0, 0, 160, 160)))

    pose = pose_key(window, 2, AFFINE)
    assert pose == ResourceKey(
        "pose", key_parts(*window.parts, 2, *AFFINE))

    assert tile_key(3, 12, 40, "C") == ResourceKey(
        "tile", (*key_parts(3, 12, 40), "C"))

    assert evidence_key(FOOTING, 3, 12, 40, "C", pose) == ResourceKey(
        "evidence",
        (FOOTING, *key_parts(3, 12, 40), "C", *pose.parts))

    # ... and the parsers still hand back exactly what went in.
    assert parse_region_key(REGION) == (CAPTURE, (64, 96), 8, (320, 480))
    assert parse_tile_key(tile_key(3, 12, 40, "C")) == (3, 12, 40, "C")
    assert parse_window_key(window) == (FOOTING, REGION, (0, 0, 160, 160))
    assert parse_evidence_key(evidence_key(FOOTING, 3, 12, 40, "C", pose)) == (
        FOOTING, 3, 12, 40, "C", pose)


def test_the_arities_are_derived_from_the_specs_not_restated() -> None:
    """One source of truth: a spec's slots ARE its part count."""
    assert WINDOW_KEY_PARTS == WINDOW_SPEC.arity
    assert POSE_KEY_PARTS == POSE_SPEC.arity
    assert EVIDENCE_KEY_PARTS == EVIDENCE_SPEC.arity


def test_a_malformed_embedded_id_is_refused_not_absorbed() -> None:
    with pytest.raises(MalformedKeyError):
        window_key(FOOTING, ResourceKey("region", ("short",)), (0, 0, 1, 1))
    with pytest.raises(MalformedKeyError):
        pose_key(REGION, 0, AFFINE)                    # not a window
    with pytest.raises(MalformedKeyError):
        pose_key(WINDOW, 0, (1.0, 0.0, 0.0))           # not six terms
    with pytest.raises(MalformedKeyError):
        evidence_key(FOOTING, 0, 1, 2, "K", WINDOW)    # not a pose
    with pytest.raises(MalformedKeyError):
        parse_window_key(REGION)
    with pytest.raises(MalformedKeyError):
        parse_evidence_key(ResourceKey("evidence", ("bad",)))

"""Pins the PURE logic in ``holo2/measure/crop_harness.py`` and its GT
half ``crop_harness_gt.py`` (HANDOFF-CROP Deliverable B) — no decode, no
state on disk, no crop files.

Lives here and not under ``holo2/tests`` for the same reason
``test_oracle_parity_k.py`` does: both modules import ``holo`` at module
level (``crop_harness_gt``'s GT reconstruction rides src/holo's
generation path directly; ``crop_harness`` reaches it for
``resolve_format_ref``/``load_session``), and only
``tests/holo2_oracles/`` and ``measure/verdicts/test_v1_parity.py`` may
reach v1 (RULINGS §F). The fixture pattern is forked from
``test_oracle_parity_k.py`` (synthetic inputs against the harness's own
pure functions, the mutant's answer stated on the page) — named per the
handoff's "name the fork of every borrowed fixture pattern" rule.

THE FORKS THESE PIN, each silent on the real corpus:

1. **The adoption predicate keyed on the repo HEAD instead of the SIDE'S
   receiver tree.** Both spellings adopt correctly in a single-commit
   session; the HEAD-keyed mutant re-decodes EVERY v1 crop after every
   holo2 commit, which kills the seconds-to-minutes inner loop the
   handoff exists for ("v1 (frozen tree) decodes each case once EVER").
   The predicate below compares exactly ``crop_sha256``,
   ``receiver_tree`` and ``receiver_dirty_sha`` — ``repo_head`` is
   recorded but MUST NOT participate.
2. **A GT gate that reports instead of refusing.** ``validate_gt_bits``
   must RAISE on any mismatch (the handoff: "refuse loudly"), naming the
   tile — a gate that returns a count with a warning would let every
   downstream comparison run against a wrong truth.
3. **Rank vocabulary guessed instead of refused.** ``full_sheet.h2``
   arrives from a manifest another worker generates; an unknown spelling
   must raise, not default to "uncertified" (memory: no invented
   defaults).
4. **Uplift flagged on the wrong classes.** UPLIFT_H2 is a crop-h2
   certificate on a ``still_missing_v2`` or ``neither`` target ONLY —
   flagging a ``flipped`` target (which holo2 already certifies at full
   sheet) would manufacture uplift out of ordinary agreement.
5. **Control tallies collapsed from three values to two.** A side whose
   crop decode is unavailable makes NO statement about its controls;
   counting its flips as 0 (or n) would gate-by-accident the one thing
   the lead ruled is reported, never gated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_ROOT / "src", _ROOT / "holo2" / "src",
              _ROOT / "holo2" / "measure"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import crop_harness                                                 # noqa: E402
import crop_harness_gt                                              # noqa: E402


# --------------------------------------------------------------------
# fork 1 — the sidecar adoption predicate
# --------------------------------------------------------------------

_CURRENT = {"crop_sha256": "aa" * 32, "receiver_tree": "t1" * 20,
            "receiver_dirty_sha": "", "repo_head": "h1" * 20}


def test_adoption_matches_on_the_three_keys_only() -> None:
    saved = dict(_CURRENT)
    saved["repo_head"] = "h2" * 20           # a later commit moved HEAD…
    ok, reason = crop_harness.adoption_verdict(saved, _CURRENT, fresh=False)
    assert ok, reason                        # …and the sidecar still adopts


@pytest.mark.parametrize("key", crop_harness.ADOPTION_KEYS)
def test_adoption_refuses_when_any_predicate_key_moves(key: str) -> None:
    saved = dict(_CURRENT)
    saved[key] = "ff" * 20
    ok, reason = crop_harness.adoption_verdict(saved, _CURRENT, fresh=False)
    assert not ok
    assert key in reason                     # the mismatch is named


def test_adoption_predicate_key_set_is_pinned() -> None:
    """The predicate's keys ARE the contract (fork 1's exact spelling)."""
    assert crop_harness.ADOPTION_KEYS == (
        "crop_sha256", "receiver_tree", "receiver_dirty_sha")
    assert "repo_head" not in crop_harness.ADOPTION_KEYS


def test_adoption_refuses_without_a_sidecar_and_under_fresh() -> None:
    ok, reason = crop_harness.adoption_verdict(None, _CURRENT, fresh=False)
    assert not ok and "no sidecar" in reason
    ok, reason = crop_harness.adoption_verdict(
        dict(_CURRENT), _CURRENT, fresh=True)
    assert not ok and "--fresh" in reason


def test_the_receiver_tree_paths_are_the_two_receivers() -> None:
    """v1 adopts across holo2 edits because its tree component is src/."""
    assert crop_harness.RECEIVER_TREE_PATHS == {"v1": "src",
                                                "h2": "holo2/src"}


# --------------------------------------------------------------------
# fork 2 — the GT-validation refusal path
# --------------------------------------------------------------------


def _bits(*values: int) -> np.ndarray:
    return np.asarray(values, dtype=np.uint8)


def test_gt_validation_passes_and_counts_on_exact_match() -> None:
    gt = {(0, 0, 0): _bits(1, 0, 1), (0, 0, 1): _bits(0, 0, 0)}
    observed = {(0, 0, 0): _bits(1, 0, 1)}
    assert crop_harness_gt.validate_gt_bits(gt, observed, "fixture") == 1


def test_gt_validation_refuses_on_one_flipped_bit_naming_the_tile() -> None:
    gt = {(0, 0, 0): _bits(1, 0, 1)}
    observed = {(0, 0, 0): _bits(1, 1, 1)}
    with pytest.raises(crop_harness_gt.GTValidationError) as caught:
        crop_harness_gt.validate_gt_bits(gt, observed, "fixture")
    message = str(caught.value)
    assert "(0, 0, 0)" in message and "1 bit(s)" in message
    assert "refusing to report" in message


def test_gt_validation_refuses_outside_the_domain_and_on_shape() -> None:
    gt = {(0, 0, 0): _bits(1, 0, 1)}
    with pytest.raises(crop_harness_gt.GTValidationError):
        crop_harness_gt.validate_gt_bits(
            gt, {(0, 9, 9): _bits(1, 0, 1)}, "fixture")
    with pytest.raises(crop_harness_gt.GTValidationError):
        crop_harness_gt.validate_gt_bits(
            gt, {(0, 0, 0): _bits(1, 0)}, "fixture")


def test_gt_reconstruction_covers_the_whole_tile_domain() -> None:
    """The reconstruction is the a2_probe route EXTENDED to every tile
    (the ``neither`` targets need truth too), on a synthetic payload so
    this test touches no corpus file. Determinism is byte-for-byte: the
    generation path draws only from the identity's seed."""
    payload = bytes(range(256)) * 4
    gt = crop_harness_gt.reconstruct_gt("L:c2-r0700@3392x2368", payload)
    assert gt.tiles_yx == (53, 37)
    assert len(gt.user_bits) == 53 * 37
    assert all(bits.shape == (gt.tile_user_bits,)
               for bits in gt.user_bits.values())
    again = crop_harness_gt.reconstruct_gt("L:c2-r0700@3392x2368", payload)
    for key, bits in gt.user_bits.items():
        assert np.array_equal(bits, again.user_bits[key])


# --------------------------------------------------------------------
# fork 3 — the rank vocabulary refuses the unknown
# --------------------------------------------------------------------


@pytest.mark.parametrize("rank,expected", [
    ("certified", True), ("CERTIFIED", True),
    ("attempted_failed", False), ("ATTEMPTED-FAILED", False),
    ("attempted", False),                    # TileState's own spelling
    ("never_addressed", False), ("UNKNOWN", False),
    ("addressed_not_attempted", False), ("ADDRESSED", False),
])
def test_h2_rank_vocabulary_covers_all_recorded_spellings(
        rank: str, expected: bool) -> None:
    assert crop_harness.h2_rank_certified(rank) is expected


def test_h2_rank_vocabulary_refuses_the_unknown() -> None:
    with pytest.raises(ValueError):
        crop_harness.h2_rank_certified("probably_fine")


def test_v1_verdict_vocabulary() -> None:
    assert crop_harness.v1_verdict_certified("certified") is True
    assert crop_harness.v1_verdict_certified("uncertified") is False
    with pytest.raises(ValueError):
        crop_harness.v1_verdict_certified("open")


# --------------------------------------------------------------------
# fork 4 — uplift fires on exactly the ruled classes
# --------------------------------------------------------------------


@pytest.mark.parametrize("classes,h2_cert,expect_h2_uplift", [
    (["still_missing_v2"], True, True),
    (["neither"], True, True),
    (["flipped"], True, False),              # full-sheet h2 already has it
    (["v1_missing"], True, False),           # ditto
    (["still_missing_v2"], False, False),    # no certificate, no uplift
    (["still_missing_v2"], None, False),     # side unavailable: no claim
])
def test_uplift_h2_fires_on_the_ruled_classes_only(
        classes: list[str], h2_cert: bool | None,
        expect_h2_uplift: bool) -> None:
    flags = crop_harness.target_flags(classes, None, h2_cert)
    assert ("UPLIFT_H2" in flags) is expect_h2_uplift


def test_uplift_v1_is_the_symmetric_observation() -> None:
    assert crop_harness.target_flags(["v1_missing"], True, None) == [
        "UPLIFT_V1"]
    assert crop_harness.target_flags(["flipped"], True, None) == []
    assert crop_harness.target_flags(["neither"], True, True) == [
        "UPLIFT_H2", "UPLIFT_V1"]


# --------------------------------------------------------------------
# fork 5 — control tallies stay three-valued
# --------------------------------------------------------------------


def test_control_agreement_counts_flips_and_names_them() -> None:
    tally = crop_harness.control_agreement(
        [(0, 1, 1), (0, 2, 2), (0, 3, 3)], {(0, 1, 1), (0, 3, 3)})
    assert tally == {"n": 3, "reproduced": 2, "flipped": 1,
                     "flipped_tiles": [[0, 2, 2]]}


def test_control_agreement_of_an_unavailable_side_makes_no_claim() -> None:
    tally = crop_harness.control_agreement([(0, 1, 1)], None)
    assert tally["n"] == 1
    assert tally["reproduced"] is None and tally["flipped"] is None
    # The collapse's answer, stated: 0 flips would read as a clean
    # reproduction of controls nobody decoded.
    assert tally["flipped"] != 0


# --------------------------------------------------------------------
# manifest tile convention + the exit contract
# --------------------------------------------------------------------


def test_manifest_tiles_carry_page_zero_unless_spelled() -> None:
    assert crop_harness._manifest_tile([4, 7]) == (0, 4, 7)
    assert crop_harness._manifest_tile([1, 4, 7]) == (1, 4, 7)
    with pytest.raises(ValueError):
        crop_harness._manifest_tile([1, 2, 3, 4])


def test_the_two_nonzero_exits_are_distinct_and_nonzero() -> None:
    codes = {crop_harness.EXIT_OK, crop_harness.EXIT_WRONG_CERTIFICATE,
             crop_harness.EXIT_GT_VALIDATION}
    assert len(codes) == 3
    assert crop_harness.EXIT_OK == 0

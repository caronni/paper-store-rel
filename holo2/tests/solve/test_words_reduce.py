"""W5's reduce: ``words.known_position_words``, carried whole.

The reconciliation half of ruling 2, pinned where its arithmetic is —
the CONSUMER half (what a contradiction condemns) is
``test_quarantine.py``.

The construction is v1's own, from
``tests/holo/test_receive_bch_quarantine.py::
test_selected_same_scan_observations_own_conflict_quarantine``: print
one tile's word for the WRONG counter, hand the reduce every site of it
from several placements of one capture, and the reduce must decode the
wrong counter, call it a conflict against the position's expected one,
and name exactly the placements whose reads it SELECTED.

Numbers here are hand-derived from the published rule, never "whatever
the code returns" — the same discipline ``test_words_kernel.py``
carries for Stage A.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.capture import region_key
from holo2.core import ResourceKey
from holo2.format import pilots
from holo2.solve import words
from holo2.solve.keys import pose_key, window_key
from holo2.format.format_v1 import tile_format

# The 8x8 grid the other solve unit tests use (``test_words_kernel``).
SPEC = tile_format("c2-k-r0550", (8, 8))

CAPTURE_SHA = "cd" * 32
FOOTING = "cap:8/1"
REGION = region_key(CAPTURE_SHA, (0, 0), 8, (512, 512))


def _pose(ordinal: int) -> ResourceKey:
    """A distinct committed-pose key, ORDERED by its extent's origin.

    The extent's first part is the ordinal, and a window key renders its
    extent before anything a pose adds, so ``_pose(1) < _pose(2)`` as
    resource keys. The reduce's declared tie-break is a value — the pose
    key — so the test has to be able to say which value wins.
    """
    window = window_key(FOOTING, REGION,
                        (ordinal, 0, ordinal + 64, 64))
    return pose_key(window, 0, (1.0, 0.0, float(ordinal), 0.0, 1.0, 0.0))


POSE_1, POSE_2, POSE_3, POSE_4 = (_pose(n) for n in (1, 2, 3, 4))


def _printed(counter: int) -> np.ndarray:
    """The 100 printed values of one tile's word at ``counter``."""
    return pilots.word_values(SPEC.seed, (counter,), SPEC.plane)[0]


def _reads(values: np.ndarray, *, pose: ResourceKey, evidence: float,
           capture: str = "scan-a",
           page: int = 0, tile_yx: tuple[int, int] = (0, 0)
           ) -> list[words.PilotObservation]:
    """One placement's read of every site of one word position."""
    return [
        words.PilotObservation(page, tile_yx, site, int(values[site]),
                               evidence, capture, pose)
        for site in range(pilots.N_WORD_SITES)]


# --------------------------------------------------------- v1's construction

def test_a_wrong_counter_at_a_known_position_is_a_conflict() -> None:
    """v1's own fixture: the ink says a tile the geometry does not.

    Every site of tile (0, 0) is printed with the counter ONE ABOVE the
    one that position expects, so the decode is legal (it is a genuine
    codeword with clean pads) and its counter is wrong — which is
    exactly the event L8 contains.
    """
    expected = SPEC.tile_counter(0, 0, 0)
    decoded = expected + 1
    values = _printed(decoded)
    observations = _reads(values, pose=POSE_1, evidence=2.0)
    # A second placement touches every site and never wins the vote.
    observations += _reads(values, pose=POSE_2, evidence=1.0)

    word, = words.known_position_words(tuple(observations), SPEC)

    assert word.conflict and not word.certified
    assert word.expected_counter == expected
    assert word.decoded_counter == decoded
    assert word.errors == 0                       # a clean printed codeword
    assert word.erasures == 0                     # all 100 sites observed
    # ONE strongest read per capture per site: the weaker placement never
    # entered the vote, so it is not a contributor.
    assert word.contributors == (POSE_1,)


def test_the_selected_set_is_what_the_contributor_list_names() -> None:
    """v1's four-patch case: strength selects, and a tie breaks by VALUE.

    v1 keeps the FIRST-SEEN read at equal ``|evidence|`` (a strict
    ``>``), which is arrival order. R7(b)'s fix makes the winner the
    minimum of a total order on values, so the tie at site 8 goes to the
    smaller pose key however the harvest arrived.
    """
    expected = SPEC.tile_counter(0, 0, 0)
    values = _printed(expected + 1)
    observations = _reads(values, pose=POSE_1, evidence=2.0)
    observations += _reads(values, pose=POSE_2, evidence=1.0)
    # A stronger read at ONE site makes POSE_3 a real contributor.
    observations.append(words.PilotObservation(
        0, (0, 0), 7, int(values[7]), 3.0, "scan-a", POSE_3))
    # An EQUAL read at another site must lose to POSE_1 on the tie-break.
    observations.append(words.PilotObservation(
        0, (0, 0), 8, int(values[8]), 2.0, "scan-a", POSE_4))

    word, = words.known_position_words(tuple(observations), SPEC)

    assert word.contributors == (POSE_1, POSE_3)
    assert POSE_1 < POSE_4                        # the tie-break, stated


def test_a_matching_word_is_a_pass_and_not_a_conflict() -> None:
    """The quiet path: the position's OWN counter certifies the read."""
    expected = SPEC.tile_counter(3, 1, 2)
    word, = words.known_position_words(
        tuple(_reads(_printed(expected), pose=POSE_1, evidence=1.5,
                     page=3, tile_yx=(1, 2))), SPEC)
    assert word.certified and not word.conflict
    assert word.decoded_counter == expected


def test_unobserved_sites_become_erasures_and_a_failure_is_silence() -> None:
    """v1's "failures never veto placement", in both of its halves."""
    values = _printed(SPEC.tile_counter(0, 0, 0) + 1)
    partial = [row for row in _reads(values, pose=POSE_1, evidence=1.0)
               if row.site_index >= 10]
    word, = words.known_position_words(tuple(partial), SPEC)
    assert word.erasures == 10 and word.observed_sites == 90
    assert word.conflict                          # 10 <= 2T, still decodable

    # Past the erasure budget the reduce refuses to decode at all, and a
    # refusal is neither a pass nor a conflict.
    starved = [row for row in _reads(values, pose=POSE_1, evidence=1.0)
               if row.site_index >= 2 * 13 + 1]
    silent, = words.known_position_words(tuple(starved), SPEC)
    assert silent.decoded_counter is None and silent.errors is None
    assert not silent.certified and not silent.conflict


def test_noise_that_decodes_to_nothing_lawful_is_silence() -> None:
    """A word whose pads are wrong is REFUSED, never reported as a read."""
    values = _printed(SPEC.tile_counter(0, 0, 0))
    broken = values.copy()
    broken[:40] ^= 1                              # far outside the BCH radius
    word, = words.known_position_words(
        tuple(_reads(broken, pose=POSE_1, evidence=1.0)), SPEC)
    assert word.decoded_counter is None and not word.conflict


# ------------------------------------------------------------ R7(b)'s fix

def _mixed_capture_reads(values: np.ndarray) -> list[words.PilotObservation]:
    """Three captures reading one position at UNEQUAL strengths.

    The vote is a float sum over the selected reads, so it is only
    order-independent because the port sums them in a declared order.
    Evidence magnitudes are chosen wide apart so that a differently
    ordered sum is a genuinely different float, not a rounding
    coincidence.
    """
    rows: list[words.PilotObservation] = []
    for index, (capture, pose, weight) in enumerate((
            ("scan-a", POSE_1, 1e-1),
            ("scan-b", POSE_2, 1e8),
            ("scan-c", POSE_3, 1e-8))):
        for site in range(pilots.N_WORD_SITES):
            bit = int(values[site]) if index != 2 else 1 - int(values[site])
            rows.append(words.PilotObservation(
                0, (0, 0), site, bit, weight, capture, pose))
    return rows


@pytest.mark.parametrize("rotation", [0, 1, 7, 97, 149])
def test_the_reduce_is_the_same_word_however_the_harvest_arrived(
        rotation: int) -> None:
    """R7(b): the sort is DATA, so arrival order cannot move a bit.

    v1 sums votes in PLACEMENT order across captures and selects the
    first-seen read at an evidence tie — both are arrival order, and
    float addition is not associative. The port's declared order makes
    every rotation of the same harvest one answer.
    """
    values = _printed(SPEC.tile_counter(0, 0, 0) + 1)
    rows = _mixed_capture_reads(values)
    rotated = tuple(rows[rotation:] + rows[:rotation])
    assert words.known_position_words(rotated, SPEC) == (
        words.known_position_words(tuple(rows), SPEC))


def test_the_reduce_is_scoped_to_what_its_caller_hands_it() -> None:
    """Ruling 4: one (capture, footing) pass, and no other comparison.

    Two positions reduce independently — the function groups by
    position and knows nothing about any lane but the one whose
    observations it was given.
    """
    first = _printed(SPEC.tile_counter(0, 0, 0) + 1)
    second = _printed(SPEC.tile_counter(0, 1, 1))
    rows = (_reads(first, pose=POSE_1, evidence=1.0)
            + _reads(second, pose=POSE_2, evidence=1.0, tile_yx=(1, 1)))
    conflict, clean = words.known_position_words(tuple(rows), SPEC)
    assert conflict.tile_yx == (0, 0) and conflict.conflict
    assert clean.tile_yx == (1, 1) and clean.certified

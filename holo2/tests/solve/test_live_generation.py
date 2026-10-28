"""F2a's read rule: a superseded generation stops owning cells.

Ruling J2-3, "we implement v1" (2026-08-23). v1 keeps a revised
window's two readings in two LANES and refuses evidence from another
lane outright (``payload_engine.py:181-182``); holo2 has no lanes, so
the same separation is made at the READ — per (tile, window) only the
pieces of the newest pose that HAS pieces are read
(``solve.generation.live_generation``, applied in
``payload.route_evidence_keys`` and ``calibration._pieces_by_pose``).

Each test names the fork it prevents:

* **``index.live_pose`` used as the rule.** It is the obvious spelling
  and it is wrong: on the archived e029 and Xerox states 4,392 / 4,117
  pieces hang on a pose that is NOT its extent's live one, because every
  revision there was committed with nothing to re-sample through it
  (DIVERGENCE-LEDGER row 7). That spelling deletes all of them and the
  two sheets lose most of their evidence. The rule must be the IDENTITY
  until something has actually re-sampled;
* **two generations meeting in one freeze.** The moment the re-read
  emits, a stale geometry's piece would compete under F1's quality
  ranking and could win cells it no longer describes — and the pool
  would weigh one physical label site twice, at half weight each;
* **the reduction reaching windows it was not asked about.** It is per
  (tile, window): a revision on ONE window may not drop another
  window's pieces from the same tile.
"""
from __future__ import annotations

from holo2.core import FootingId, ResourceKey
from holo2.capture import region_key
from holo2.solve.generation import (live_generation, pose_of_evidence,
                                    window_of_evidence)
from holo2.solve.records import PoseRecord, evidence_key, window_key

CAPTURE = "ef" * 32
FOOTING = FootingId("cap:1/1")
REGION = region_key(CAPTURE, (0, 0), 8, (256, 256))
WINDOW_A = window_key(FOOTING, REGION, (0, 0, 128, 128))
WINDOW_B = window_key(FOOTING, REGION, (0, 0, 192, 192))
PARENT_AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
REVISED_AFFINE = (1.0, 0.0, 0.25, 0.0, 1.0, 0.25)


def _pose(window: ResourceKey, affine: tuple[float, ...]) -> ResourceKey:
    return PoseRecord(window, FOOTING, 0, affine).resource_key()


def _piece(pose: ResourceKey, ty: int = 0, tx: int = 0) -> ResourceKey:
    return evidence_key(FOOTING, 0, ty, tx, "main", pose)


PARENT_A = _pose(WINDOW_A, PARENT_AFFINE)
REVISED_A = _pose(WINDOW_A, REVISED_AFFINE)
PARENT_B = _pose(WINDOW_B, PARENT_AFFINE)


def test_a_revision_with_no_pieces_changes_nothing() -> None:
    """THE archived-state case, and the reason the rule is not live_pose.

    Every revision on the two real sheets is exactly this shape: the
    record is committed, ``live_pose`` answers with it, and no pass has
    ever sampled through it. Reducing to the live pose here would return
    an EMPTY read-set and the tile would decode nothing at all.
    """
    pieces = (_piece(PARENT_A), _piece(PARENT_B))
    live = {WINDOW_A: REVISED_A, WINDOW_B: PARENT_B}
    assert live_generation(live, pieces) == pieces


def test_the_live_pose_wins_once_it_has_pieces() -> None:
    """The re-read has spoken: the parent's reading stops owning cells."""
    parent, revised = _piece(PARENT_A), _piece(REVISED_A)
    live = {WINDOW_A: REVISED_A}
    assert live_generation(live, (parent, revised)) == (revised,)
    # ...and order is preserved rather than re-sorted: the read-set IS
    # the attempt's identity (§7), so its order is part of it.
    assert live_generation(live, (revised, parent)) == (revised,)


def test_the_reduction_is_per_window() -> None:
    """One revised window may not silence an unrevised neighbour.

    Both windows cover this tile; only A was revised and re-read. B's
    single generation is its live one and stays whole.
    """
    kept = live_generation(
        {WINDOW_A: REVISED_A, WINDOW_B: PARENT_B},
        (_piece(PARENT_A), _piece(REVISED_A), _piece(PARENT_B)))
    assert kept == (_piece(REVISED_A), _piece(PARENT_B))


def test_an_unposed_or_unparseable_key_is_never_dropped() -> None:
    """The function reduces GENERATIONS and adjudicates nothing else.

    A window nobody has posed (no entry in ``live_poses``) and a key of
    a shape this arithmetic cannot read both survive untouched — the
    readers that refuse a malformed key do so on their own terms, and a
    silent drop here would be an evidence loss with no record of it.
    """
    junk = ResourceKey("evidence", ("nonsense",))
    assert window_of_evidence(junk) is None
    assert pose_of_evidence(junk) is None
    assert live_generation({}, (_piece(PARENT_A), junk)) == (
        _piece(PARENT_A), junk)


def test_the_key_arithmetic_answers_the_two_questions_one_way() -> None:
    """``window_of_evidence`` and ``pose_of_evidence`` are one derivation.

    The fork: a second spelling of "which pose/window is this piece's"
    drifting from the first. F1's supersede wake, the live-generation
    reduction and the re-read's own harvest all read these two, and the
    keys they slice are the keys ``evidence_key`` builds.
    """
    piece = _piece(REVISED_A, ty=3, tx=5)
    assert pose_of_evidence(piece) == REVISED_A
    assert window_of_evidence(piece) == WINDOW_A
    assert window_of_evidence(piece) == ResourceKey(
        "window", REVISED_A.parts[:len(WINDOW_A.parts)])

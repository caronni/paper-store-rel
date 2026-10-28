"""F2a's scheduling door: when a placed window comes back, and at what price.

Ruling J2-3 / RULING I3, "we implement v1" (2026-08-23). Through F1 the
placement source's ``"placed"`` exit was permanent, and an adopted pose
revision therefore bought nothing at all: A2 measured 269/272 revised
windows on the two real sheets, every one of them with ZERO evidence on
its live pose. This module pins the door that lets such a window back in.

Each test names the fork it prevents:

* **a permanent ``placed`` exit** — the ruling's own sentence is "when a
  better pose comes in, the old one goes out the door and the tile/window
  wakes up again", and without the door there is no wake at all;
* **a door that opens for any bare pose** — a re-read replaces a
  GENERATION, so a window whose only pose has not been read yet is the
  emission's business (or a test double), not this one. Opening for it
  would buy a pass that refuses ``nothing_superseded``;
* **a door that reopens on every refresh** — a re-read retires whether it
  emitted or refused, so without the answered-geometry memory a refusal
  would be re-offered forever and the set would stop being bounded;
* **a re-read priced as a placement pass** — it would preempt the ladder
  the revision itself waited behind (RULING I2's top price);
* **a re-read that still climbs the placement ladder** — a placed
  window's address is committed; a consult, a word sweep or a cold
  correlation on it is work with nothing to buy.

The fake plane is ``test_placement``'s, with its F2a ``read_poses`` arm:
"which poses own evidence", the arrow ``StoreIndex.evidence_by_pose``
maintains on the live path.

Two more forks were added at this package's review (2026-08-23):

* **a re-read that resurrects a CONDEMNED generation** — W5 reaches
  poses only through their pieces, so a revision committed before a
  contradiction is never marked and stands as the extent's live pose
  above a condemned parent. Re-reading there would emit fresh,
  unquarantined pieces over the cells W5 condemned;
* **a re-read that overwrites the window's exit reason** — the door is a
  clause ON the placed exit, and ``place_subdivide.child_verdict`` reads
  that reason to decide whether a corner child SERVED its area.
"""
from __future__ import annotations

from dataclasses import replace

from holo2.core import WorkResult
from holo2.solve.place_sched import (EXIT_PLACED, EXIT_SERVED,
                                     PLACEMENT_TIERS, TIER_PRICE,
                                     TIER_RESAMPLE)
from holo2.solve.records import PoseRecord, pose_key
from conftest import FOOTING
from test_placement import WINDOW_A, WINDOW_B, _Plane
from place_sched_support import AFFINE, FINE_LANE_TERM, _pose, _scheduler

#: A revision of :data:`AFFINE`, a quarter of a cell away — the shape RF1
#: actually commits (A2 measured 82-88% of revisions saturating the
#: +-0.25-cell bound in both axes on the two real sheets).
REVISED = (AFFINE[0], AFFINE[1], AFFINE[2] + 0.25,
           AFFINE[3], AFFINE[4], AFFINE[5] + 0.25)

PARENT_KEY = pose_key(WINDOW_A, 0, AFFINE)
REVISED_KEY = pose_key(WINDOW_A, 0, REVISED)


def _revised(*, read: tuple = (PARENT_KEY,), quarantined: bool = False,
             done: bool = False, condemned_parent: bool = False) -> _Plane:
    """WINDOW_A placed, then revised; ``read`` owns the evidence.

    ``condemned_parent`` is the W5 shape the door has to refuse: the
    generation that OWNS the pieces is marked and the live revision is
    clean, which is what a contradiction leaves behind when the revision
    was committed before it.
    """
    revision = PoseRecord(window_id=WINDOW_A, footing_id=FOOTING, page=0,
                          native_affine=REVISED, quarantined=quarantined)
    parent = _pose(WINDOW_A)
    if condemned_parent:
        parent = replace(parent, quarantined=True)
    return _Plane(records={PARENT_KEY: parent, REVISED_KEY: revision},
                  poses={WINDOW_A: (PARENT_KEY, REVISED_KEY)},
                  read_poses=read, done=done)


def test_a_revised_window_re_enters_as_a_re_read() -> None:
    """The door itself: placed, revised, unread — so it comes back.

    And it comes back as a RE-READ and not as a placement candidate: the
    tier it offers is the re-read tier, which is the only one a slot
    carrying that bit will ever answer with.
    """
    scheduler = _scheduler(_revised())
    assert WINDOW_A in scheduler._slots, "a revised window owes a re-read"
    assert WINDOW_A not in scheduler._exited
    slot = scheduler._slots[WINDOW_A]
    assert slot.resample and slot.tier() == TIER_RESAMPLE
    job = scheduler.job(WINDOW_A)
    assert job is not None and job.cost == (
        TIER_PRICE[TIER_RESAMPLE].cost + FINE_LANE_TERM)


def test_the_re_read_outranks_nothing_and_is_outranked_by_the_ladder(
) -> None:
    """RULING I2's price, seen from the queue: it goes LAST.

    WINDOW_B is an ordinary unplaced window at the cheapest tier, so the
    scheduler's own head is B's ring/word pass and not A's re-read —
    "after the ladder" as an emergent property of one cost order, with
    no phase and no barrier arranging it.
    """
    scheduler = _scheduler(_revised())
    head = scheduler.peek()
    assert head is not None and head.subject == WINDOW_B
    assert head.cost < TIER_PRICE[TIER_RESAMPLE].cost


def test_a_window_whose_only_pose_is_unread_owes_no_re_read() -> None:
    """The second half of the door: there must be a GENERATION to replace.

    ``read_poses`` empty means no pose of this window owns evidence, so
    there is nothing for a re-read to supersede and the fire would refuse
    ``nothing_superseded`` after paying for a pass. Eligibility is
    expansion (§3a), so the door asks it.
    """
    scheduler = _scheduler(_revised(read=()))
    assert scheduler._exited[WINDOW_A] == "placed"
    assert WINDOW_A not in scheduler._slots


def test_a_condemned_live_pose_is_never_re_read() -> None:
    """W5's never-return, asked at the fifth reader of one predicate."""
    scheduler = _scheduler(_revised(quarantined=True))
    assert scheduler._exited[WINDOW_A] == "placed"


def test_a_re_read_never_resurrects_a_condemned_generation() -> None:
    """The other side of W5, and the reachable one (review fix).

    ``quarantine._geometry_side`` reaches poses ONLY through their
    pieces, so a revision committed before a contradiction owns nothing,
    is never condemned, and stays live above a parent that IS. The door
    asked the predicate of the live pose alone, so this window opened
    it — and the fire would then read the condemned cells back and emit
    FRESH, unquarantined pieces at the live pose, which is a
    rehabilitation of exactly the material W5 declares beyond recovery
    (*"the transition is one-way and recovery is fresh-evidence-only"*).
    """
    plane = _revised(condemned_parent=True)
    scheduler = _scheduler(plane)
    assert WINDOW_A not in scheduler._slots, (
        "a condemned generation is never re-read")
    assert scheduler._exited[WINDOW_A] == "placed"


def test_a_fully_done_window_is_never_re_read() -> None:
    """Nothing to buy: every tile under it is certified and retired.

    It leaves under the reason it had before F2a — the door is a clause
    ON the placed exit and not a new one beside it, so a window that was
    permanently placed for a second reason stays placed for it. What is
    pinned is that it does not come back.
    """
    scheduler = _scheduler(_revised(done=True))
    assert scheduler._exited[WINDOW_A] == "placed"
    assert WINDOW_A not in scheduler._slots


def test_one_re_read_per_live_pose_however_it_ended() -> None:
    """The anti-spin memory, on the path that would spin: a REFUSAL.

    A re-read retires either way, so the scheduler records the geometry
    it answered for. Re-admitting the same plane — which is what every
    subsequent refresh does — must not offer it again.

    AND IT LEAVES UNDER THE EXIT IT ALREADY HELD (review fix,
    2026-08-23). The fork: writing the fire's own outcome into
    ``_exited``, which is read as a verdict ABOUT THE RECTANGLE by
    ``place_subdivide.child_verdict`` (``EXIT_SERVED``) and by the
    verdicts exit census — so a corner child that PLACED would flip to
    "failed" for having been re-read, and four such children would
    cold-park and arm a parent whose whole area was served. The fire's
    outcome lives in the spend row and in the ``resampled`` counter.
    """
    plane = _revised()
    scheduler = _scheduler(plane)
    assert scheduler.claim(plane, WINDOW_A) is not None
    scheduler.settle(plane, WINDOW_A,
                     WorkResult(outcome="resample_refused_no_pixels",
                                retire=True))
    assert scheduler._exited[WINDOW_A] == EXIT_PLACED
    assert scheduler._exited[WINDOW_A] in EXIT_SERVED, (
        "a re-read must leave a placed child's verdict unchanged")
    assert scheduler.counters()["resampled"] == 1

    scheduler.admit(plane, entry=0, selector="all")
    assert WINDOW_A not in scheduler._slots, "one re-read per live pose"
    assert scheduler._placed_pose[WINDOW_A] == REVISED_KEY


def test_the_review_is_skipped_while_the_pose_count_has_not_moved() -> None:
    """The cost clause of RULING I4, as the memo that makes it O(1).

    A live pose can only move when a pose COMMITS, so an unchanged pose
    count means an unchanged answer for every window — the same
    exactness argument the cold offer and the done projection memoise
    under. Staged by mutating the scheduler's own answered-geometry map
    behind a refresh that must not look: with the memo the window stays
    out, without it the stale entry would let it back in.
    """
    plane = _revised()
    scheduler = _scheduler(plane)
    scheduler._exit(WINDOW_A, "placed")
    scheduler._placed_pose[WINDOW_A] = PARENT_KEY      # "not yet answered"
    scheduler.admit(plane, entry=0, selector="all")
    assert WINDOW_A not in scheduler._slots, "the review did not re-run"

    scheduler._reviewed.clear()                        # a pose committed
    scheduler.admit(plane, entry=0, selector="all")
    assert scheduler._slots[WINDOW_A].resample


def test_the_row_this_module_prices_is_the_one_the_scheduler_offers(
) -> None:
    """The tier is reachable through the scheduler's own table.

    The fork: ``RESAMPLE_TIER`` living beside ``PLACEMENT_TIERS`` and
    never being wired into ``TIER_PRICE``, which would make
    ``Slot.price`` raise on the first re-read instead of failing here.
    It is NOT a member of the ladder table, which is what keeps every
    property asserted over that table about ways of PLACING a window.
    """
    assert TIER_PRICE[TIER_RESAMPLE].tier == TIER_RESAMPLE
    assert TIER_RESAMPLE not in {row.tier for row in PLACEMENT_TIERS}

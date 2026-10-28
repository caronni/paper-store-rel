"""The pull model's queue: admission, the flag protocol, pricing and pings.

Split out of ``test_place_sched.py`` on 2026-08-17 under the cap-as-seam-
signal ruling (1000 lines marks a split-here point, never a budget to
squeeze prose against); the job's own scoring, consult and the ladder that
drives it moved to ``test_place_job.py``. This half keeps
``PlacementScheduler``'s own state machine (the JOB's arithmetic is the
carried kernel and is gated end to end by the decode batteries —
``holo2/measure/``, the wall among them — what is pinned here is the
queue machinery the 2026-08-16 pull-model redesign introduced, because a
page-level gate cannot say which of these moved):

* **membership**, including the resume rebuild (three refusals at
  admission — placed, retired, covered — with empty tried sets, which is
  why none of that has to be durable) and the admission-side covered
  refusal; the OTHER exit, the lazy fire-time covered retirement, is
  pinned in ``test_place_job.py``;
* **the flag protocol**, under adversarial interleavings — lost-wake
  impossibility, single ownership, and the ping-after-commit ordering the
  first two rest on;
* **donor ping targeting** — same-footing ring vs. downhill cross-footing
  donor, and a ping at a window that already left the set;
* **the tier order and its tie-break** (rulings Q3+Q6, R-A), including
  the gated tier's own flag and the 2026-08-17 footing-premium pricing
  ruling (a price now, not a gate: the finer window enters immediately
  and every tier it runs costs a tad more);
* **subdivision** (W3/PL5) — the one thing that makes the set GROW: the
  eligible-refusal set transcribed from v1, the four corner members it
  adds, the child premium as schedule rather than as arithmetic, the
  two facts termination rests on, the parent's cold park, and the
  resume that persists nothing and lands on the same names anyway.

The fake plane is ``test_placement``'s. The admitted-plane builders
(``_scheduler``, ``_pose``, ``_placed``, ``_priced``) and the
sparse/confetti gapped lattice (``_gapped``) are shared with
``test_place_job.py`` and live in ``place_sched_support.py`` so neither
test module restates them.
"""
from __future__ import annotations

from holo2.core import WorkResult, Write
from holo2.solve import place_job, place_sched
from holo2.solve.lattice_seed import LatticeSeedRecord, lattice_seed_key
from holo2.solve.place_shared import READING_FINEST
from holo2.solve.place_sched import (CHILD_PREMIUM, EXIT_OUTSIDE_READING_SET,
                                     LANE_COST_PER_RUNG, PLACEMENT_TIERS,
                                     TIER_PRICE, TIER_RING, TIER_WIDE,
                                     TIER_WORD_CENTRE, TIER_WORD_REST,
                                     PlacementScheduler)
from holo2.solve.records import (WindowRecord, WindowStatus, pose_key,
                                 window_key)
from conftest import FOOTING, REGION
from test_placement import (COARSE, PLAN_A, ROW, WINDOW_A, WINDOW_B,
                            _Plane, _plan)
from place_sched_support import (AFFINE, CHILDREN_A, FAR_C, FAR_D,
                                 GAPPED_CELLS, PLAN_C, PLAN_D, _gapped,
                                 _placed, _pose, _priced, _refuse, _scheduler)

# ------------------------------------------------------------ membership

def test_every_planned_window_enters_ready() -> None:
    """The set is plans minus placed minus covered; entry is READY."""
    scheduler = _scheduler(_Plane())
    counts = scheduler.counters()
    assert counts["windows"] == counts["ready"] == 2
    assert counts["entered"] == 2 and counts["in_flight"] == 0


def test_a_placed_or_retired_or_covered_window_never_enters() -> None:
    """The resume rebuild, stated as three refusals at admission.

    This IS the resume: a fresh scheduler over a store that already holds
    poses and retirements enters exactly the windows that still have a
    question, all ready, with empty tried sets — which is why none of
    that has to be durable.
    """
    placed = _scheduler(_placed({}, WINDOW_A))
    assert {slot for slot in placed._slots} == {WINDOW_B}

    retired = _scheduler(_Plane(records={WINDOW_A: WindowRecord(
        footing_id=FOOTING, region_id=REGION, extent_cells=(0, 0, 200, 200),
        status=WindowStatus.RETIRED, retired_reason="no_labels")}))
    assert {slot for slot in retired._slots} == {WINDOW_B}
    assert retired._exited[WINDOW_A] == "no_labels"

    covered = _scheduler(_Plane(done=True))
    assert not covered._slots and covered.peek() is None


def test_a_detached_capture_enters_nothing_and_is_not_remembered() -> None:
    """M12 as admission: no verdict without pixels, and no exit either."""
    plane = _Plane(raster=None)
    scheduler = _scheduler(plane)
    assert not scheduler._slots and not scheduler._exited
    scheduler.admit(_Plane(), entry=0, selector="all")     # attached now
    assert scheduler.counters()["windows"] == 2


def test_surviving_prepared_planes_are_pixels_enough_to_admit() -> None:
    """The second pixel source (2026-08-17): no raster, planes on disk.

    A crash-cut resume declares no scan, so every raster is ``None`` — and
    every placement fire reads the region's PREPARED plane, never a
    raster (W1a). The gate therefore admits on either source, which is
    what lets such a resume re-earn its recorded placement tail. The
    raster is asked first, so a session that has the file is untouched.
    """
    scheduler = _scheduler(_Plane(raster=None, prepared=object()))
    assert set(scheduler._slots) == {WINDOW_A, WINDOW_B}
    assert not scheduler._exited


def test_a_window_on_a_lane_this_run_does_not_read_exits() -> None:
    """The exit survived stage 2; what moved is when it fires and its name.

    The default reading set is the whole ladder now, so a coarse window
    ENTERS — the first half below. The exit is what a run that declared
    ``finest`` still gets, and the reason names the policy that excluded
    the window rather than a "working footing" that no longer exists.
    """
    plane = _Plane(plans=(_plan(window_key(COARSE, REGION, (0, 0, 200, 200)),
                                (0, 0, 200, 200), footing=COARSE),))
    cascade = _scheduler(plane, selector="coarsest")
    assert set(cascade._slots) and not cascade._exited

    finest = PlacementScheduler(ROW, reading_set=READING_FINEST)
    finest.admit(plane, entry=0, selector="coarsest")
    assert not finest._slots
    assert set(finest._exited.values()) == {EXIT_OUTSIDE_READING_SET}


def test_membership_only_shrinks() -> None:
    """Monotone by construction: an exited window cannot be re-admitted."""
    plane = _Plane()
    scheduler = _scheduler(plane)
    scheduler._exit(WINDOW_A, "placed")
    scheduler.admit(plane, entry=0, selector="all")
    assert set(scheduler._slots) == {WINDOW_B}


# ------------------------------------------------------- the flag protocol

def test_a_claim_clears_the_flag_before_the_job_exists() -> None:
    """Test-and-CLEAR: the second half of the lost-wake argument."""
    scheduler = _scheduler(_Plane())
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert isinstance(job, place_job.WindowJob)
    slot = scheduler._slots[WINDOW_A]
    assert not slot.ready and slot.in_flight


def test_one_window_has_at_most_one_owner() -> None:
    """Single ownership, under every interleaving a ping can produce."""
    scheduler = _scheduler(_Plane())
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    assert scheduler.claim(_Plane(), WINDOW_A) is None, "already claimed"
    # a ping lands mid-flight and sets the bit — it still may not be claimed
    scheduler._wake(scheduler._slots[WINDOW_A], 1.0)
    assert scheduler._slots[WINDOW_A].ready
    assert scheduler.claim(_Plane(), WINDOW_A) is None, "in flight"
    assert scheduler.peek() is None or scheduler.peek().subject != WINDOW_A


def test_a_ping_that_lands_mid_flight_is_re_enqueued_not_lost() -> None:
    """The one interleaving where a lost wake would live.

    A pose commits while this window's own pass is running: the ping sets
    the bit under the fire, and the settle that follows must hand it back
    to the queue even though the pass itself learned nothing.
    """
    scheduler = _scheduler(_Plane())
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None
    scheduler._wake(scheduler._slots[WINDOW_A], 0.0)          # the ping
    scheduler.settle(_Plane(), WINDOW_A, WorkResult(outcome="pose_refused"))
    head = scheduler.peek()
    assert head is not None and head.subject == WINDOW_A
    assert head.cost == _priced(TIER_RING), (
        "the ping's offered seed is what prices it at the ring tier")


def test_a_pass_that_learned_nothing_goes_dormant() -> None:
    """The other side of the same rule: no treadmill on a refused fit.

    A window whose own fit refused tested no hypothesis, so re-arming it
    against the identical pixels would spin. It sleeps until something
    changes — a ping, or R5's seed improving under it.
    """
    scheduler = _scheduler(_Plane())
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_Plane(), WINDOW_A, WorkResult(outcome="pose_refused"))
    slot = scheduler._slots[WINDOW_A]
    assert not slot.ready and not slot.in_flight
    assert {job.subject for job in [scheduler.peek()]} == {WINDOW_B}


def test_a_pass_with_nothing_to_try_falls_to_its_next_tier() -> None:
    """It spent the PING, not a tier — so it may not sleep on a tombstone.

    A window with both word stages behind it sits enqueued at the wide
    tier; a ping reprices it to the ring tier (killing that entry), and
    the pass it buys finds every offered seed already tried. Nothing was
    learned, but nothing was SPENT either: the wide pass is still owed,
    and going dormant here would strand it behind a heap entry the ping
    already invalidated. It cannot spin — the tier it falls to charges
    itself once and then sleeps.
    """
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    slot.centre_spent = slot.rest_spent = True
    scheduler._wake(slot, 1.0)
    assert scheduler.peek().cost == _priced(TIER_RING)
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_Plane(), WINDOW_A,
                     WorkResult(outcome=place_job.NOTHING_TO_TRY))
    assert slot.ready and slot.tier() == TIER_WIDE
    scheduler._exit(WINDOW_B, "placed")          # so the head is A's
    head = scheduler.peek()
    assert head is not None and head.subject == WINDOW_A, (
        "the wide pass was swallowed with its queue entry tombstoned")
    assert head.cost == _priced(TIER_WIDE)


def test_an_accepted_pass_that_supersedes_the_seed_wakes_the_region() -> None:
    """R5 rides the WRITES, not the outcome — acceptances carry them too.

    The pass that first fits a region is its likeliest seed superseder
    (the seed is ranked by the support its source measured) and it is
    also the pass that LEAVES the set, pinging only its ring on the way
    out. A window a gap away whose own fit refused is dormant and outside
    that ring: the improved seed under it is the one thing that changes
    its answer, and the accepted branch used to return before asking.
    """
    plane = _gapped()
    scheduler = _scheduler(plane)
    assert scheduler.claim(plane, FAR_D) is not None
    scheduler.settle(plane, FAR_D, WorkResult(outcome="pose_refused"))
    assert not scheduler._slots[FAR_D].ready, "a refused fit sleeps"

    assert scheduler.claim(plane, WINDOW_A) is not None
    seed = LatticeSeedRecord(footing_id=FOOTING, region_id=REGION,
                             rows=(0.25, 0.0, 0.0, 0.25),
                             source_window_id=WINDOW_A,
                             source_support_cells=40_000)
    scheduler.settle(_gapped(WINDOW_A), WINDOW_A, WorkResult(
        outcome="accepted",
        writes=(Write(lattice_seed_key(FOOTING, REGION), seed),)))
    assert scheduler._exited[WINDOW_A] == "placed"
    assert scheduler._slots[FAR_D].ready, (
        "the seed improved under a dormant window and the acceptance that "
        "wrote it never woke the region")


def test_a_better_lattice_seed_wakes_the_region() -> None:
    """R5's order-independence, carried without a subscription.

    A window whose fit refused is dormant; the one thing that changes its
    answer is the region's lattice seed improving, which used to reach it
    as a version bump on a key in its read-set.
    """
    scheduler = _scheduler(_Plane())
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_Plane(), WINDOW_A, WorkResult(outcome="pose_refused"))
    assert not scheduler._slots[WINDOW_A].ready
    seed = LatticeSeedRecord(footing_id=FOOTING, region_id=REGION,
                             rows=(0.25, 0.0, 0.0, 0.25),
                             source_window_id=WINDOW_B,
                             source_support_cells=900)
    assert scheduler.claim(_Plane(), WINDOW_B) is not None
    scheduler.settle(_Plane(), WINDOW_B, WorkResult(
        outcome="insufficient_support",
        writes=(Write(lattice_seed_key(FOOTING, REGION), seed),)))
    assert scheduler._slots[WINDOW_A].ready, "the region re-arms on a seed"


def test_an_abandoned_fire_gives_the_window_back_unchanged() -> None:
    """``settle(None)``: a cancelled slot charges nothing and re-arms."""
    scheduler = _scheduler(_Plane())
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None
    job.tried_now = ("pretend",)
    scheduler.settle(_Plane(), WINDOW_A, None)
    slot = scheduler._slots[WINDOW_A]
    assert slot.ready and not slot.in_flight and not slot.tried
    assert scheduler.counters()["abandoned"] == 1


def test_settling_a_window_twice_is_a_no_op() -> None:
    """The disarm path calls it again; nothing may be charged twice."""
    scheduler = _scheduler(_Plane())
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_Plane(), WINDOW_A, WorkResult(outcome="consult_refused"))
    before = scheduler.counters()
    scheduler.settle(_Plane(), WINDOW_A, None)
    assert scheduler.counters() == before


# --------------------------------------------------------------- the pings

def test_an_acceptance_pings_its_ring_with_the_ratified_distance() -> None:
    """Commit, THEN ping — and the offered distance is the sort key."""
    scheduler = _scheduler(_Plane())
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_placed({}, WINDOW_A), WINDOW_A,
                     WorkResult(outcome="accepted"))
    assert WINDOW_A not in scheduler._slots, "placed windows leave the set"
    assert scheduler._exited[WINDOW_A] == "placed"
    slot = scheduler._slots[WINDOW_B]
    assert slot.ready and slot.offered == 1.0, (
        "one window stride away scores exactly 1.0")
    assert scheduler.counters()["pings"] == 1


def test_the_ping_targets_the_ring_and_the_covered_finer_windows() -> None:
    """Donor targeting: a coarse pose steers the fine lane it covers.

    ``ring_targets`` is same-footing and ``donor_targets`` is downhill in
    ppc, so a pose committed on the coarse lane pings the fine windows its
    extent contains and nothing else.
    """
    fine = _plan(window_key(FOOTING, REGION, (0, 0, 200, 200)),
                 (0, 0, 200, 200))
    coarse_id = window_key(COARSE, REGION, (0, 0, 200, 200))
    coarse = _plan(coarse_id, (0, 0, 200, 200), footing=COARSE)
    plane = _Plane(plans=(fine, coarse))
    scheduler = PlacementScheduler(ROW)
    # both lanes in the set: admission's working-footing gate is not what
    # is under test here, so the slots are placed directly.
    for plan in (fine, coarse):
        scheduler._ordinal += 1
        scheduler._slots[plan.window_id] = place_sched.Slot(
            plan, 0, scheduler._ordinal)
    scheduler._ping(plane, coarse)
    assert scheduler._slots[fine.window_id].offered == 0.0, (
        "a colocated donor is the strongest steer there is")


def test_a_ping_at_a_window_that_left_is_dropped() -> None:
    scheduler = _scheduler(_Plane())
    scheduler._exit(WINDOW_B, "placed")
    scheduler._ping(_Plane(), PLAN_A)
    assert scheduler.counters()["pings"] == 0


# ------------------------------------------------------ tiers and priority

def test_the_cost_table_is_ordered_and_carries_its_gate() -> None:
    """Q3+Q6 as data: ring < word centre < word rest < wide < cold pair."""
    costs = [row.cost for row in PLACEMENT_TIERS]
    assert costs == sorted(costs) and len(set(costs)) == len(costs)
    assert [row.tier for row in PLACEMENT_TIERS][:3] == [
        TIER_RING, TIER_WORD_CENTRE, TIER_WORD_REST]
    gated = {row.tier for row in PLACEMENT_TIERS if row.gated}
    assert gated == {TIER_WIDE, place_sched.TIER_COLD_LIVE,
                     place_sched.TIER_COLD_REST}
    assert all(row.provenance for row in PLACEMENT_TIERS)


def test_a_window_climbs_its_tiers_and_stops() -> None:
    """The ladder as PRICES: each pass advances, and the last is dormant."""
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    assert slot.tier() == TIER_WORD_CENTRE
    slot.centre_spent = True
    assert slot.tier() == TIER_WORD_REST
    slot.rest_spent = True
    assert slot.tier() == TIER_WIDE
    slot.wide_spent = True
    assert slot.tier() is None, "cold is offered only to an ARMED window"
    slot.offered = 2.0
    assert slot.tier() == TIER_RING, "a ping revives a spent window"


class _OneLane(_Plane):
    """A capture with a single footing: its only lane IS its coarsest."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.footings = tuple(footing for footing in self.footings
                              if footing.footing_id == FOOTING)

    def footing_ids(self, selector: str) -> tuple[str, ...]:
        return (FOOTING,)


def test_a_finer_footing_window_pays_the_lane_term_and_a_coarse_one_does_not(
) -> None:
    """The 2026-08-17 pricing ruling, at the door where it is resolved.

    Footing progression used to be a GATE: the finer entry was not
    enumerated at all while anything cheaper was in play. It is a PRICE
    now — the window enters immediately and every tier it runs costs a
    little more — and the term is read off the plane's own LADDER DEPTH
    at admission (H4-LANES stage 2, which replaced the flat premium of 1
    with ``2`` per rung), not off the selector that reached it and not
    off a branch at fire time.

    The bound that makes it a tie-break rather than a tier of its own is
    pinned in ``tests/engine/test_cost_vocabulary.py``; what this shows
    is the consequence on the real table: a finer window's RING pass
    still outranks any window's word-centre pass.
    """
    fine = _scheduler(_Plane())
    assert {slot.lane_depth for slot in fine._slots.values()} == {1}, (
        "the fine lane sits one rung above the coarsest")
    assert fine.peek().cost == _priced(TIER_WORD_CENTRE)

    coarse = _scheduler(_OneLane())
    assert {slot.lane_depth for slot in coarse._slots.values()} == {0}
    assert coarse.peek().cost == TIER_PRICE[TIER_WORD_CENTRE].cost

    fine._wake(fine._slots[WINDOW_A], 1.0)
    assert fine.peek().cost < TIER_PRICE[TIER_WORD_CENTRE].cost, (
        "a lane term that can carry a window past the next tier is a tier")


def test_the_wide_tier_declares_itself_gated() -> None:
    scheduler = _scheduler(_Plane())
    for window in (WINDOW_A, WINDOW_B):
        slot = scheduler._slots[window]
        slot.centre_spent = slot.rest_spent = True
        scheduler._enqueue(slot)
    job = scheduler.peek()
    assert job is not None and job.cost == _priced(TIER_WIDE)
    assert job.gated, "wide waits for everything cheaper, payload included"


def test_priority_is_distance_first_then_round_robin() -> None:
    """R-A: the frontier grows along its most confident edges.

    Two ready windows at one tier: the one whose ping offered the shorter
    distance goes first, and equal distances fall back to the arrival
    ordinal, which is what kills starvation.
    """
    scheduler = _scheduler(_Plane())
    scheduler._wake(scheduler._slots[WINDOW_B], 0.5)
    scheduler._wake(scheduler._slots[WINDOW_A], 2.0)
    assert scheduler.peek().subject == WINDOW_B
    scheduler._wake(scheduler._slots[WINDOW_A], 0.25)
    assert scheduler.peek().subject == WINDOW_A, "a better ping raises it"
    # Equal offers: the ORDINAL breaks the tie, and a window that has just
    # had a pass goes to the BACK of it — which is the round robin.
    fresh = _scheduler(_Plane())
    assert fresh.peek().subject == WINDOW_A, "admission order, to begin with"
    assert fresh.claim(_Plane(), WINDOW_A) is not None
    fresh.settle(_Plane(), WINDOW_A, WorkResult(outcome="consult_refused",
                                                writes=()))
    fresh._wake(fresh._slots[WINDOW_A], 1.0)
    fresh._wake(fresh._slots[WINDOW_B], 1.0)
    assert fresh.peek().subject == WINDOW_B, "nothing starves behind a re-arm"


def test_admission_offers_what_a_ping_would_have_offered() -> None:
    """R-A at the door: the resume and the late entry order by distance too.

    Pings are not the only way a seed becomes available. A resume
    rebuilds the whole set beside poses that already stand, and a
    quiescence-gated entry admits into a page others have been placing —
    and a window that entered blind priced at the WORD tier in arrival
    order, behind windows with nothing to steer them. Here the window
    with a colocated donor enters SECOND, and it goes first anyway.
    """
    coarse_id = window_key(COARSE, REGION, (0, 0, 200, 200))
    coarse = _plan(coarse_id, (0, 0, 200, 200), footing=COARSE)
    poses = {coarse_id: (pose_key(coarse_id, 0, AFFINE),),
             FAR_D: (pose_key(FAR_D, 0, AFFINE),)}
    plane = _Plane(plans=(PLAN_C, PLAN_A, PLAN_D, coarse),
                   shape_cells=GAPPED_CELLS,
                   records={keys[0]: _pose(window)
                            for window, keys in poses.items()},
                   poses=poses)
    scheduler = _scheduler(plane)
    assert scheduler._slots[WINDOW_A].offered == 0.0, (
        "a colocated coarse donor is the strongest steer there is")
    assert scheduler._slots[FAR_C].offered == 1.0, "its placed ring neighbour"
    assert {scheduler._slots[window].tier() for window in (WINDOW_A, FAR_C)} \
        == {TIER_RING}, "an available seed prices at the ring tier"
    head = scheduler.peek()
    assert head is not None and head.subject == WINDOW_A, (
        "the donor-steered window entered second and still goes first")


def test_a_window_with_nothing_standing_near_it_still_enters_at_the_word_tier(
) -> None:
    """The other half of the same rule: no offer, no ring price."""
    scheduler = _scheduler(_Plane())
    assert scheduler._slots[WINDOW_A].offered is None
    assert scheduler.peek().cost == _priced(TIER_WORD_CENTRE)


def test_a_stale_heap_entry_is_dropped_not_served() -> None:
    """Lazy deletion, and the property that makes it safe."""
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    scheduler._wake(slot, 1.0)              # a second entry, better key
    scheduler._wake(slot, 0.5)              # a third
    entries = [entry for entry in scheduler._heap if entry[3] == WINDOW_A]
    assert len(entries) == 3, "two of these are already tombstones"
    head = scheduler.peek()
    assert head is not None and head.subject == WINDOW_A
    # Served off the SLOT's CURRENT key: the two older entries price this
    # window at the word tier and at 1.0, and the head carries neither.
    assert slot.sort_key() == (_priced(TIER_RING), 0.5, slot.ordinal)
    assert head.cost == _priced(TIER_RING)
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    assert scheduler.peek() is None or scheduler.peek().subject != WINDOW_A


# ----------------------------------------------- subdivision (W3, PL5)
#
# WINDOW_A is (0, 0, 200, 200), so its corner children are the four
# 100-cell squares below — ``max(min_window_cells, 200 // 2)`` is 100,
# and 100 is above the 70-cell floor, so they tile the parent exactly.

def test_an_exhausted_window_adds_its_four_corners_to_the_set() -> None:
    """PL5 in the pull model: not a new record family, four new MEMBERS.

    The children are ordinary windows — named by ``window_key`` from
    their own extents, on the parent's footing and region, entering
    through the same admission door — which is the whole translation the
    descriptor-era census row needed.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    slot = scheduler._slots[WINDOW_A]
    assert slot.children == CHILDREN_A
    assert set(CHILDREN_A) <= set(scheduler._slots)
    for child in CHILDREN_A:
        entered = scheduler._slots[child]
        assert entered.depth == 1 and entered.ready
        assert entered.plan.footing_id == slot.plan.footing_id
        assert entered.plan.region_id == slot.plan.region_id
    assert scheduler.counters()["subdivided"] == 1


def test_a_child_pays_the_premium_and_waits_behind_every_whole_window(
) -> None:
    """The ruling as schedule: exhaust the sheet before specializing.

    WINDOW_B is a whole window with nothing steering it, so it prices at
    the word-centre tier — DEARER than a child's ring tier by class. It
    still goes first, because a child at the same rung carries
    :data:`CHILD_PREMIUM` on top of a price that has to clear the tier
    gap before it can outrank anything.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    child = scheduler._slots[CHILDREN_A[0]]
    parent = scheduler._slots[WINDOW_A]
    assert child.lane_depth == parent.lane_depth and child.depth == 1
    assert child.price(TIER_RING) == parent.price(TIER_RING) + CHILD_PREMIUM
    assert child.price(TIER_RING) == _priced(TIER_RING) + CHILD_PREMIUM
    head = scheduler.peek()
    assert head is not None and head.subject == WINDOW_B, (
        "a child outran the last unworked whole window on the sheet")


def test_the_refusal_v1_declines_to_subdivide_on_subdivides_nothing() -> None:
    """The eligibility set is v1's, and its exclusion is load-bearing.

    ``insufficient_support`` is the one refusal v1 reaches and does NOT
    send to subdivision (``src/holo/receive/place.py:1259-1271``): too
    little paper under the rectangle is not a reason to ask for a
    quarter of it. A window refused that way goes dormant with no
    children at all.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "insufficient_support")
    slot = scheduler._slots[WINDOW_A]
    assert not slot.ready and not slot.subdivided and slot.children == ()
    assert set(scheduler._slots) == {WINDOW_A, WINDOW_B}
    assert scheduler.counters()["subdivided"] == 0


def test_a_window_subdivides_at_most_once_and_children_never_do() -> None:
    """The termination argument, as two facts rather than one hope.

    A ping can re-arm a dormant parent, and its next refusal must not
    mint a second brood; a child that exhausts its own ladder must not
    mint one at all, because the depth cap is 1. Together those bound
    the growth at one generation and four members per window.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    before = set(scheduler._slots)
    scheduler._wake(scheduler._slots[WINDOW_A], 1.0)
    _refuse(scheduler, WINDOW_A, "straddle_audit_refused")
    assert set(scheduler._slots) == before, "a second brood was minted"

    child = CHILDREN_A[0]
    _refuse(scheduler, child, "pose_refused")
    assert scheduler._slots[child].children == ()
    assert set(scheduler._slots) == before, "a child subdivided"


def test_a_parent_whose_children_all_failed_parks_at_the_cold_tier() -> None:
    """The ruled afterlife: park when the last corner has failed.

    This parent's own fit refused, so it has no patch to correlate and
    :meth:`_arm_cold` bars it (``test_place_cold`` pins the two families
    where the escalation does and does not arm). What the park is here
    is the bit and the counter an observer reads, and the parent offers
    no job — which is what "goes dormant there" means.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    parent = scheduler._slots[WINDOW_A]
    for index, child in enumerate(CHILDREN_A):
        assert not parent.cold_parked, (
            f"parked with {4 - index} children still working")
        _refuse(scheduler, child, "pose_refused")
    assert parent.cold_parked
    assert scheduler.job(WINDOW_A) is None, "a parked parent offers no work"
    assert scheduler.counters()["cold_parked"] == 1
    # The park is about the ESCALATION, not about the window: a later
    # ping still buys this parent an ordinary whole-window pass, which is
    # the cheap answer and must never be closed off by a dear one.
    scheduler._wake(parent, 1.0)
    assert scheduler.job(WINDOW_A) is not None


def test_a_parent_whose_child_placed_never_escalates() -> None:
    """The other half: a corner that served the area ends the escalation."""
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    parent = scheduler._slots[WINDOW_A]
    for child in CHILDREN_A[:3]:
        _refuse(scheduler, child, "pose_refused")
    assert scheduler.claim(_Plane(), CHILDREN_A[3]) is not None
    scheduler.settle(_Plane(), CHILDREN_A[3], WorkResult(outcome="accepted"))
    assert scheduler._exited[CHILDREN_A[3]] == "placed"
    assert not parent.cold_parked
    assert scheduler.counters()["cold_parked"] == 0


def test_a_resume_re_subdivides_to_the_same_children() -> None:
    """RESUME PERSISTS NOTHING (ruling 5), and that is enough.

    Nothing durable says a window was ever subdivided: a resumed parent
    re-runs its ladder, re-subdivides, and the kernel is a pure function
    of the parent's extent — so the SAME four names come back. A child
    that placed before the crash is found by the record it left and is
    refused at admission like any placed window; an unfired one simply
    re-enters. Waste at worst, and the final state is the same one.
    """
    first = _scheduler(_Plane())
    _refuse(first, WINDOW_A, "pose_refused")

    placed_child = CHILDREN_A[1]
    resumed = _scheduler(_placed({}, placed_child))
    _refuse(resumed, WINDOW_A, "pose_refused", plane=_placed({}, placed_child))
    assert resumed._slots[WINDOW_A].children == first._slots[WINDOW_A].children
    assert resumed._exited[placed_child] == "placed", (
        "the fired child was found by its own extent-named record")
    assert set(CHILDREN_A) - {placed_child} <= set(resumed._slots)
    assert not resumed._slots[WINDOW_A].cold_parked, (
        "a placed child is a served area, resume or not")


# ------------------------------------------ park verification (W3, PL6)
#
# H4-W3-PLAN section 3's ruling: the expected outcome here is
# VERIFICATION, not construction. The pull model already holds both
# halves of PL6 as scheduling state (a ladder-exhausted window goes
# dormant; wakes ride pings); what follows pins that a dormant window
# re-enters on exactly the ruled wakes and nothing else, and that
# quiescence composes with the orchestrator's close gate.

def test_a_dormant_window_does_not_wake_on_an_unrelated_acceptance() -> None:
    """The ONLY push channel is the ping, and a ping targets a GEOMETRY.

    ``FAR_D`` is neither ``WINDOW_A``'s ring neighbour (its own ring slot
    is empty by construction — ``_gapped``'s whole point) nor its donor
    (one footing here, no coarser lane admitted). Accepting ``FAR_D``
    without superseding a lattice seed exercises ``_ping`` alone: it
    pings ITS ring and donor targets, neither of which is ``WINDOW_A``,
    so an acceptance with no geometric relation to a dormant window must
    not move it — the negative half of
    ``test_an_accepted_pass_that_supersedes_the_seed_wakes_the_region``,
    isolated from the seed channel that test is actually about.
    """
    plane = _gapped()
    scheduler = _scheduler(plane)
    assert scheduler.claim(plane, WINDOW_A) is not None
    scheduler.settle(plane, WINDOW_A,
                     WorkResult(outcome="insufficient_support"))
    assert not scheduler._slots[WINDOW_A].ready, "a refused fit sleeps"

    assert scheduler.claim(plane, FAR_D) is not None
    scheduler.settle(_gapped(FAR_D), FAR_D, WorkResult(outcome="accepted"))
    assert scheduler._exited[FAR_D] == "placed"
    assert not scheduler._slots[WINDOW_A].ready, (
        "an acceptance with no ring/donor/seed relation to this window "
        "must not wake it")


def test_coverage_is_an_exit_not_a_wake() -> None:
    """The done gate is CONSULTED at the job's fire, never PUSHED here.

    Nothing in the scheduler ever asks ``window_is_done`` — that gate is
    ``WindowJob.run``'s own first check (pinned in
    ``test_place_job.py``'s covered-exit), asked only once a claim has
    actually fired. A dormant window's coverage growing in the meantime
    changes nothing about its READY bit; the window sits inert until an
    ordinary ping revives it, and only THEN does the fired job's own
    lazy gate retire it — which is what ``retire=True`` names here. The
    two are different operations: a WAKE sets ``ready`` and leaves the
    window a member of ``_slots``; an EXIT (``done_covered``, exactly
    like ``placed`` or any other retirement) removes it for good.
    """
    scheduler = _scheduler(_Plane())
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_Plane(), WINDOW_A,
                     WorkResult(outcome="insufficient_support"))
    slot = scheduler._slots[WINDOW_A]
    assert not slot.ready, "a refused fit sleeps; still a MEMBER"
    assert WINDOW_A not in scheduler._exited, "dormant, not exited"

    # An ordinary ping is what makes it claimable again (any channel —
    # here a synthetic ring-style wake, as in the acceptance tests above).
    scheduler._wake(slot, 1.0)
    assert scheduler.claim(_Plane(), WINDOW_A) is not None
    scheduler.settle(_Plane(), WINDOW_A,
                     WorkResult(outcome="done_covered", retire=True))
    assert WINDOW_A not in scheduler._slots, "an exit, not a wake"
    assert scheduler._exited[WINDOW_A] == "done_covered"


def test_repeated_admission_and_peeking_never_wakes_a_dormant_window(
) -> None:
    """"Time" is not a wake channel: the model has no clock and no sweep.

    v1's mop-up was a periodic RE-PASS over the parked inventory; the
    pull model has none — a dormant window is inert until a ping names
    it, so calling ``admit`` again (the orchestrator's ordinary
    re-enumeration on every refresh) or ``peek`` any number of times
    must be free of side effects on readiness.
    """
    plane = _Plane()
    scheduler = _scheduler(plane)
    assert scheduler.claim(plane, WINDOW_A) is not None
    scheduler.settle(plane, WINDOW_A,
                     WorkResult(outcome="insufficient_support"))
    slot = scheduler._slots[WINDOW_A]
    assert not slot.ready

    for _ in range(5):
        scheduler.peek()
    scheduler.admit(plane, entry=0, selector="all")
    assert not slot.ready, "neither iteration nor re-enumeration wakes it"


def test_a_childs_exit_updates_the_parents_cold_park_bit_not_its_ready_bit(
) -> None:
    """WHAT "a child's exit pings the parent" ACTUALLY MEANS, precisely.

    ``_review_parents`` is bookkeeping only: it reads ``_child_verdict``
    off each child's own exit or dormancy and, once every child has
    failed, sets ``cold_parked``. It never calls ``_wake``. The parent's
    own ready bit is untouched by anything a child does — it went
    dormant the moment ITS OWN ladder exhausted, before subdivision even
    fired, and stays that way through every child's outcome. There is no
    fourth push channel here beside ring, donor and seed.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    parent = scheduler._slots[WINDOW_A]
    assert not parent.ready, "dormant since its own ladder exhausted"
    for child in CHILDREN_A:
        assert not parent.cold_parked
        assert not parent.ready, "no child's outcome has touched this bit"
        _refuse(scheduler, child, "pose_refused")
    assert parent.cold_parked
    assert not parent.ready, (
        "the escalation is a bit and a counter; it is not a ping")


def test_a_revived_cold_parked_parent_offers_an_ordinary_whole_pass() -> None:
    """The park's OTHER half: revival is an external ping, and it is WHOLE.

    Extends
    ``test_a_parent_whose_children_all_failed_parks_at_the_cold_tier``
    (which shows the job exists once woken) and
    ``test_a_window_subdivides_at_most_once_and_children_never_do``
    (which shows a re-refused parent mints no second brood, but not from
    a COLD-PARKED start): together, a cold-parked parent revived by a
    ping claims at the RING tier over its own FULL extent — not
    ``wide`` and not a child's slice — and a second refusal still may
    not mint a second brood, because ``subdivided`` already stands.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    parent = scheduler._slots[WINDOW_A]
    for child in CHILDREN_A:
        _refuse(scheduler, child, "pose_refused")
    assert parent.cold_parked

    scheduler._wake(parent, 1.0)
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None
    assert not job.wide and job.plan.extent_cells == PLAN_A.extent_cells

    before = set(scheduler._slots)
    scheduler.settle(_Plane(), WINDOW_A,
                     WorkResult(outcome="consult_refused"))
    assert set(scheduler._slots) == before, "a second brood was minted"


def test_a_fully_quiesced_subdivision_tree_offers_nothing() -> None:
    """Quiescence composes: parent, four children, nothing ready anywhere.

    This is the slice the orchestrator's exhaustion path depends on
    (``engine.orchestrator._pop_armed``/``_exhausted``, generic over any
    ``WorkSource`` and pinned end to end for the descriptor path by
    ``test_exhaustion_leaves_the_session_open_and_resumable``,
    ``holo2/tests/engine/test_orchestrator.py``): once every member of a
    subdivision tree is dormant, ``peek``/``job`` must honestly report
    nothing offerable, or the orchestrator's "worklist empty" test would
    be lying to the close gate.
    """
    plane = _Plane(plans=(PLAN_A,))
    scheduler = _scheduler(plane)
    _refuse(scheduler, WINDOW_A, "pose_refused", plane=plane)
    for child in CHILDREN_A:
        _refuse(scheduler, child, "insufficient_support", plane=plane)
    assert scheduler._slots[WINDOW_A].cold_parked

    assert scheduler.peek() is None
    for window in (WINDOW_A, *CHILDREN_A):
        assert scheduler.job(window) is None

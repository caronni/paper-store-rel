"""The cold pair: its page sets, its arming, and its dedup (H4 W4).

What is pinned here is everything about cold that is DECISION rather than
arithmetic. The correlation itself is the carried kernel's and is pinned
bit-for-bit in ``test_cold.py``; the verdicts run a real page through the
tier end to end. This module holds the three rulings that shaped the
tier and would otherwise be invisible until a decode drifted:

* **the two page sets** — live is the pages with a committed pose, rest
  is the declared domain minus those, and they PARTITION the domain;
* **skip-if-empty is costless and never terminal** (ruling 2) — an
  empty flavour is simply not offered, nothing is marked, and it offers
  itself again the moment its set fills;
* **the ladder position and the premium** — cold arms only where every
  cheaper way of placing the rectangle whole has failed, children
  included since the 2026-08-18 reversal, and a child pays the premium
  for it.
"""
from __future__ import annotations

from holo2.core import ProgressSink, WorkResult
from holo2.solve import place_cold
from holo2.solve.place_job import COLD_REFUSED
from holo2.solve.place_sched import (CHILD_PREMIUM, PlacementScheduler,
                                     TIER_COLD_LIVE, TIER_COLD_REST,
                                     TIER_PRICE, TIER_WIDE)
from holo2.solve.reference import V1ReferenceField
from holo2.format.registry_rows import tile_format_for
from holo2.format.registry_rows import format_row
from test_placement import PLAN_A, ROW, WINDOW_A, WINDOW_B, _Plane
from place_sched_support import (CHILDREN_A, _placed, _refuse, _scheduler,
                                 FINE_LANE_TERM)

#: A TWO-PAGE row, so ``rest`` has something to be. The suite's default
#: row declares one page, which is the degenerate case ruled about
#: (``rest`` empties after the first pose) and is pinned as such below.
ROW_TWO_PAGES = format_row("c2-k-r0700", (2, 2), 2)


def _cold_price(tier: str, *, child: bool = False) -> int:
    """What these fixtures' windows pay for one cold flavour."""
    row = TIER_PRICE[tier]
    return (row.cost + row.rung_cost * 1
            + (CHILD_PREMIUM if child else 0))


# ----------------------------------------------------------- the page sets

def test_live_is_the_pages_a_committed_pose_stands_on() -> None:
    """Ask what the producer knows: a pose IS the page-anchored fact."""
    assert place_cold.live_pages(_Plane()) == frozenset()
    assert place_cold.live_pages(_placed({}, WINDOW_A)) == frozenset({0})


def test_the_two_flavours_partition_the_declared_domain() -> None:
    """Every page in exactly one set, so the pair sweeps each one once."""
    for live in (frozenset(), frozenset({0}), frozenset({0, 1})):
        pages = {
            flavor: place_cold.cold_pages(ROW_TWO_PAGES, flavor, live)
            for flavor in (place_cold.FLAVOR_LIVE, place_cold.FLAVOR_REST)}
        both = pages[place_cold.FLAVOR_LIVE] + pages[place_cold.FLAVOR_REST]
        assert sorted(both) == list(ROW_TWO_PAGES.page_domain)
        assert len(set(both)) == len(both), "a page is in both sets"
        assert set(pages[place_cold.FLAVOR_LIVE]) == live & set(
            ROW_TWO_PAGES.page_domain)


def test_a_pose_outside_the_declared_domain_steers_nothing() -> None:
    """This run may only address the pages its row declares."""
    single = format_row("c2-k-r0700", (2, 2), 1)
    assert place_cold.cold_pages(
        single, place_cold.FLAVOR_LIVE, frozenset({5})) == ()
    assert place_cold.cold_pages(
        single, place_cold.FLAVOR_REST, frozenset({5})) == (0,)


def test_a_single_page_domains_rest_flavour_empties_after_the_first_pose(
) -> None:
    """The e029 observation as a DERIVED fact, not an operator flag.

    "--page 0 for single-sheet volumes would collapse the 133-page cold
    domain" — on a one-page volume the live set becomes the whole domain
    the moment anything places, so the full sweep degenerates to an empty
    one and is never scheduled at all. Before that first pose the sets
    are the other way round, which is what makes a blank session's cold
    sweep the page it does have rather than nothing.
    """
    scheduler = PlacementScheduler(ROW)
    assert ROW.page_domain == (0,)

    blank = _Plane()
    scheduler.admit(blank, entry=0, selector="all")
    assert scheduler._cold_offer.flavors == (TIER_COLD_REST,), (
        "with nothing placed, the REST flavour is the one with pages")

    scheduler.admit(_placed({}, WINDOW_A), entry=0, selector="all")
    assert scheduler._cold_offer.flavors == (TIER_COLD_LIVE,), (
        "once the one page is live, rest has nothing to sweep")


# ------------------------------------------- skip-if-empty (ruling 2)

def test_an_empty_flavour_is_skipped_costlessly_and_re_offers_later(
) -> None:
    """"It might fill later" — no state, no re-arm machinery.

    A flavour with an empty page set is not offered, and NOTHING records
    that: no spend bit moves, no counter, no tombstone. When the set
    fills, the next derivation offers the tier again by itself. Read here
    as the live flavour going from unoffered to offered across one pose,
    on a window that is already armed.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    child = CHILDREN_A[0]
    _exhaust(scheduler, child)
    slot = scheduler._slots[child]
    assert slot.cold_armed and not slot.cold_live_spent

    assert slot.tier() == TIER_COLD_REST, (
        "nothing is placed, so only the rest flavour has pages")
    scheduler._refresh_cold_offer(_placed({}, WINDOW_B))
    assert slot.tier() == TIER_COLD_LIVE, (
        "a pose landed: the live flavour re-offers itself, unmarked")
    assert not slot.cold_live_spent and not slot.cold_rest_spent, (
        "being skipped is not being spent")


def test_the_offer_change_re_enqueues_every_armed_window() -> None:
    """The tombstone hazard the derivation has to answer for.

    ``peek`` validates the heap head against the slot's CURRENT sort key
    and DROPS a mismatch, which is safe only because every path that
    leaves a window ready re-enqueues it. A flavour appearing changes
    exactly that key — cold rest at 150 becomes cold live at 140 — so
    the refresh has to re-enqueue, or an armed window would be ready and
    invisible for the rest of the run.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    for child in CHILDREN_A:
        _exhaust(scheduler, child)
    scheduler._refresh_cold_offer(_placed({}, WINDOW_B))
    for child in CHILDREN_A:
        offer = scheduler.job(child)
        assert offer is not None, (
            f"{child} is armed and ready but offers nothing after its "
            "flavour moved")
        assert offer.cost == _cold_price(TIER_COLD_LIVE, child=True)
    # The heap is the half that would silently rot: ``peek`` drops a head
    # whose key no longer matches, so every armed slot needs a LIVE entry.
    queued = {entry[3] for entry in scheduler._heap
              if entry[:3] == scheduler._slots[entry[3]].sort_key()}
    assert set(CHILDREN_A) <= queued, (
        "an armed window has no queue entry matching its current price")


# ------------------------------------------------ the ladder and the premium

def test_cold_is_the_last_tier_and_arms_only_when_wide_has_gone() -> None:
    """Above everything else current, and behind the whole cheap ladder."""
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    slot.centre_spent = slot.rest_spent = True
    assert slot.tier() == TIER_WIDE
    assert not slot.cold_armed, "cold armed before the wide consult ran"
    _exhaust(scheduler, WINDOW_A)
    assert slot.cold_armed and slot.tier() == TIER_COLD_REST


def test_a_window_correlates_before_it_is_quartered() -> None:
    """v1'S OWN ORDER, RESTORED (W4).

    v1 reaches ``subdivide_into_pending`` from ``run_cold`` ->
    ``refuse_unplaced`` (``place.py:1495`` -> :1126): a window that
    exhausts the cheap ladder is DEFERRED to the correlation, and only
    the correlation's refusal quarters it. W3 wired the trigger at the
    wide refusal because cold did not exist; this is the restoration,
    read as the two facts that distinguish the orders — no children
    while the pair is unspent, four the moment it refuses.
    """
    scheduler = _scheduler(_Plane())
    _exhaust(scheduler, WINDOW_A)
    slot = scheduler._slots[WINDOW_A]
    assert slot.cold_armed and slot.children == (), (
        "the wide refusal quartered the window instead of arming its cold")
    assert scheduler.counters()["subdivided"] == 0

    _refuse_cold(scheduler, WINDOW_A, TIER_COLD_REST)
    assert slot.children == CHILDREN_A, (
        "the cold refusal is v1's subdivision trigger and did not fire")
    assert slot.cold_rest_spent and slot.tier() is None, (
        "the pair is spent and this row has one page: nothing left to sweep")


def test_a_cold_flavour_with_every_page_swept_refuses_rather_than_stalls(
) -> None:
    """The one cold pass that does no correlation still ANSWERS.

    A flavour whose pages this window has already swept has nothing to
    do — but it was OFFERED, so it may not answer ``nothing_to_try`` and
    leave the window dormant with its subdivision untriggered. It
    refuses with its own word, which is v1's :1495 outcome, and the
    window is quartered exactly as a fruitless sweep would have
    quartered it.
    """
    scheduler = _scheduler(_Plane())
    _exhaust(scheduler, WINDOW_A)
    slot = scheduler._slots[WINDOW_A]
    slot.tried.add(place_cold.cold_tried_id(0))
    job = _claim_cold(scheduler, WINDOW_A, TIER_COLD_REST)
    result = job.run(_Plane(), (), ProgressSink("unit"))
    assert result.outcome == f"{COLD_REFUSED}_{TIER_COLD_REST}"
    assert job.cold_spent == TIER_COLD_REST
    scheduler.settle(_Plane(), WINDOW_A, result)
    assert slot.children == CHILDREN_A


def test_the_ordinary_parent_has_already_correlated_when_its_family_fails(
) -> None:
    """What v1's order does to the W3 afterlife: it makes it a COUNTER.

    A parent is quartered by its own cold refusal, so by the time its
    corners report it is already armed and already spent. The park bit
    and its counter still record that the family failed — that is what
    an observer reads — but the escalation has nothing left to arm, and
    saying so is more honest than pretending the parent's correlation
    waits for its children.
    """
    scheduler = _scheduler(_Plane())
    parent = _exhaust_family(scheduler, WINDOW_A)
    assert parent.cold_parked and scheduler.counters()["cold_parked"] == 1
    assert parent.cold_armed and parent.cold_rest_spent
    assert scheduler.counters()["cold_armed"] == 5, (
        "the parent and its four corners each armed exactly once")


def test_the_audit_refused_parent_is_the_afterlife_that_still_bites() -> None:
    """The one family whose correlation really does wait for its corners.

    v1's :1173 site quarters a window whose straddle audit refused an
    address the search had already accepted — the window spent its
    address, never reached a cold tier, and is quartered on the spot. If
    all four corners then fail, :meth:`_review_parents` is what finally
    hands the parent its full-extent correlation, which is the W3
    afterlife doing real work rather than restating a bit.
    """
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    slot.centre_spent = slot.rest_spent = True
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None and job.wide
    job.wide_spent = True
    scheduler.settle(_Plane(), WINDOW_A,
                     WorkResult(outcome="straddle_audit_refused"))
    assert slot.children == CHILDREN_A and not slot.cold_armed, (
        "an audit-refused window correlated instead of being quartered")

    for child in CHILDREN_A:
        _exhaust(scheduler, child)
        child_slot = scheduler._slots[child]
        child_slot.cold_live_spent = child_slot.cold_rest_spent = True
        child_slot.ready = False
    scheduler._review_parents()
    assert slot.cold_parked and slot.cold_armed, (
        "the parent's full-extent correlation never armed")
    assert slot.tier() == TIER_COLD_REST


def test_a_fit_refused_window_never_arms() -> None:
    """No patch, no correlation — the bar that is not mere bookkeeping.

    Every tier opens with the same ``sample_window`` call, so a window
    whose own fit refused has nothing for the kernel to correlate and
    arming it would buy a fire that refuses at the identical line. It
    stays dormant until a better lattice seed re-arms it.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    slot = scheduler._slots[WINDOW_A]
    assert not slot.wide_spent and not slot.cold_armed
    assert scheduler.job(WINDOW_A) is None or slot.tier() != TIER_COLD_REST


def test_a_child_runs_cold_too_and_pays_the_premium() -> None:
    """THE 2026-08-18 REVERSAL, as the schedule it produces.

    "children get the cold treatment as well — we implement src/holo,
    algorithmically; the thing we change is scheduling and
    orchestration." v1's children reached the cold route in the main
    pass, so holo2's do: a child that exhausts its own ladder arms the
    same pair a whole window does, one premium dearer, and its price
    stays INSIDE its rung's pair rather than crossing into the next.
    """
    scheduler = _scheduler(_Plane())
    _refuse(scheduler, WINDOW_A, "pose_refused")
    _exhaust(scheduler, CHILDREN_A[0])
    child = scheduler._slots[CHILDREN_A[0]]
    assert child.depth == 1 and child.cold_armed, (
        "a child exhausted its ladder and did not reach cold")
    assert child.price(TIER_COLD_REST) == _cold_price(
        TIER_COLD_REST, child=True)
    assert (_cold_price(TIER_COLD_LIVE)
            < _cold_price(TIER_COLD_LIVE, child=True)
            < _cold_price(TIER_COLD_REST)
            < _cold_price(TIER_COLD_REST, child=True))


# ------------------------------------------------------------ the dedup

def test_a_swept_page_is_not_swept_twice() -> None:
    """PAGE granularity, which is the ruled dedup and is enough.

    The flavours partition the domain at any INSTANT, but live grows, so
    a page swept under rest can turn up in a later live set. The tried
    set is what keeps a window from paying for the same page twice, and
    it is honest for the reason the seed tried-set is: fires are
    deterministic, so re-sweeping a page with the same patch is the same
    trial and not a new one.
    """
    assert place_cold.cold_tried_id(3) != place_cold.cold_tried_id(4)
    scheduler = PlacementScheduler(ROW_TWO_PAGES)
    scheduler.admit(_Plane(), entry=0, selector="all")
    slot = scheduler._slots[WINDOW_A]
    slot.tried.add(place_cold.cold_tried_id(0))
    job = _claim_cold(scheduler, WINDOW_A, TIER_COLD_REST)
    assert job._cold_pages(_Plane()) == (1,), (
        "page 0 was already swept by this window and was swept again")


# ------------------------------------------------------------- the key

def test_the_transform_key_is_widened_and_footing_free() -> None:
    """The page-invariance question, as the key it produced.

    WIDENED by the reference field's printed interpretation, because the
    carried ``np.array_equal`` invariant is scoped to ONE sweep and
    cannot name a store two sweeps might share. NOT widened by the
    footing: this kernel correlates in the page's CELL lattice, which a
    region shares across every footing of its capture, so the transforms
    are rung-invariant and a footing term would fragment one shareable
    store into one per lane.
    """
    pages, shape = (0, 1), (200, 200)
    here = V1ReferenceField(tile_format_for(ROW))
    one = place_cold.cold_transform_key(here, pages, shape)
    bigger = V1ReferenceField(tile_format_for(format_row("c2-k-r0700", (8, 8))))
    assert one != place_cold.cold_transform_key(bigger, pages, shape), (
        "two reference fields with different printed pages share one store")
    assert one != place_cold.cold_transform_key(here, (0,), shape), (
        "two page domains share one store")
    assert one != place_cold.cold_transform_key(here, pages, (100, 100)), (
        "two patch size classes share one store")
    assert "cap:" not in str(one), (
        "the key names a footing, which would fragment a store that is "
        "provably shareable across every rung of a capture")


# ---------------------------------------------------------------- helpers

def _exhaust(scheduler: PlacementScheduler, window) -> None:
    """Run one window's cheap ladder out: both word stages, then wide.

    What happens NEXT is the same for every depth since W4 restored v1's
    order: the window arms its cold pair. Nothing is quartered here.
    """
    slot = scheduler._slots[window]
    slot.centre_spent = slot.rest_spent = True
    job = scheduler.claim(_Plane(), window)
    assert job is not None and job.wide
    job.wide_spent = True
    scheduler.settle(_Plane(), window, WorkResult(outcome="wide_refused"))


def _refuse_cold(scheduler: PlacementScheduler, window, flavor: str) -> None:
    """One whole cold pass at ``flavor``, refused: v1's :1495 outcome."""
    job = _claim_cold(scheduler, window, flavor)
    job.cold_spent = flavor
    scheduler.settle(_Plane(), window,
                     WorkResult(outcome=f"{COLD_REFUSED}_{flavor}"))


def _exhaust_family(scheduler: PlacementScheduler, window):
    """Drive a whole window's ladder, its colds AND its corners out.

    v1's order end to end (W4): the parent runs out of cheap ladder, arms
    its cold pair, sweeps it, is quartered by the COLD refusal, and each
    corner then runs out of its own ladder — cold pair included, since
    the 2026-08-18 reversal. Returns the parent's slot, parked.
    """
    _exhaust(scheduler, window)
    parent = scheduler._slots[window]
    assert parent.cold_armed and not parent.children, (
        "a whole window was quartered before it correlated")
    _refuse_cold(scheduler, window, TIER_COLD_REST)
    assert parent.children, "the cold refusal did not quarter the window"
    for child in parent.children:
        _exhaust(scheduler, child)
        child_slot = scheduler._slots[child]
        assert child_slot.cold_armed, "a child did not reach its cold pair"
        child_slot.cold_live_spent = child_slot.cold_rest_spent = True
        child_slot.ready = False
    scheduler._review_parents()
    return parent


def _claim_cold(scheduler: PlacementScheduler, window, flavor: str):
    """Claim one window at a named cold flavour."""
    slot = scheduler._slots[window]
    slot.centre_spent = slot.rest_spent = slot.wide_spent = True
    slot.cold_armed = True
    slot.ready, slot.in_flight = True, False
    assert slot.tier() == flavor, (slot.tier(), flavor)
    job = scheduler.claim(_Plane(), window)
    assert job is not None and job.cold == flavor
    return job

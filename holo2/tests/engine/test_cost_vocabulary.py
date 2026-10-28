"""The ONE cost order, pinned equal from both sides of the wall.

The engine owns the scale (scheduling is its business) and ``solve``
declares the placement half of it again — ``place_sched.PLACEMENT_TIERS``,
with each row's provenance — because neither package may import the
other. That is the same structural seam as the consult modes and the
footing selectors, and it gets the same remedy (WP-4/16): a data pin
asserting the two spellings are one table.

What the pin protects is the user's ruling (Q3+Q6), which is an ORDER and
not a set of numbers: a tier opens only when everything cheaper GLOBALLY
is dry, and "cheaper" includes pending payload, whose certificates delete
placement work outright. The engine compares source-job costs (priced
from solve's table) against queue costs (priced from recipe entries), so
a reprice on ONE side silently inverts that interleave — the wide tier
starting before the payload it was ruled to wait for — with every
behavioural test in the tree still green. Both sides are PROVISIONAL:
these are orders ratified by the ruling, and a number that moves must
move in both spellings, here, in one edit.
"""
from __future__ import annotations

from pathlib import Path

from holo2.engine import recipe
from holo2.solve import place_job, place_sched, place_slot, place_tiers
from holo2.solve.place_tiers import MAX_LANE_DEPTH


def _lane(depth: int) -> int:
    """What a window at ``depth`` adds to every ORDINARY tier it runs."""
    return place_sched.LANE_COST_PER_RUNG * depth


#: The two tier families, split by which RUNG TERM they carry: the
#: ordinary tiers pay the small lane tie-break, the cold pair pays a real
#: per-rung price. EVERY window runs both families, children included
#: (the 2026-08-18 reversal), so this split is about arithmetic and not
#: about eligibility.
COLD_TIERS = tuple(row for row in place_sched.PLACEMENT_TIERS
                   if row.tier in place_tiers.COLD_TIERS)
ORDINARY_TIERS = tuple(row for row in place_sched.PLACEMENT_TIERS
                       if row.tier not in place_tiers.COLD_TIERS)


def test_the_two_spellings_of_the_placement_scale_are_one_table() -> None:
    assert {row.tier: row.cost for row in place_sched.PLACEMENT_TIERS} == {
        place_sched.TIER_RING: recipe.COST_PLACE_RING,
        place_sched.TIER_WORD_CENTRE: recipe.COST_PLACE_WORD_CENTRE,
        place_sched.TIER_WORD_REST: recipe.COST_PLACE_WORD_REST,
        place_sched.TIER_WIDE: recipe.COST_PLACE_WIDE,
        place_sched.TIER_COLD_LIVE: recipe.COST_PLACE_COLD_LIVE,
        place_sched.TIER_COLD_REST: recipe.COST_PLACE_COLD_REST,
    }
    assert (place_tiers.COLD_COST_PER_RUNG == recipe.COLD_COST_PER_RUNG), (
        "cold's rung term is a price and not a tie-break, so it too has "
        "two spellings that must agree")


def test_payload_undercuts_every_placement_rung() -> None:
    """Q3+Q6 as an order, AMENDED 2026-08-17.

    Payload used to interleave between word rest and wide. MEASURED on a
    real nine-platen run: 2,529 ready workers with 1,287 armed payload,
    and after 431 fires ZERO tiles attempted and zero certified —
    placement on a domain that size never dries, so payload above it
    never runs, and with no certificate there is no close preemption and
    no done coverage either. Both feedback loops were dormant. The ruled
    order is ingest, then the cheapest payload recovery, then placement,
    with the two dear tiers still gated behind global dryness.

    ONE constant by ruling: more payload types will declare their own
    prices beside this one, and none exists today.
    """
    assert (recipe.COST_INGEST
            < recipe.COST_PAYLOAD
            < recipe.COST_PLACE_RING
            < recipe.COST_PLACE_WORD_CENTRE
            < recipe.COST_PLACE_WORD_REST
            < recipe.COST_PLACE_WIDE
            < recipe.COST_PLACE_COLD_LIVE
            < recipe.COST_PLACE_COLD_REST), (
        "payload runs before placement: a certificate deletes placement "
        "work outright, so the work that mints one may not queue behind it")
    dear = {row.tier for row in place_sched.PLACEMENT_TIERS if row.gated}
    assert dear == {place_sched.TIER_WIDE, place_sched.TIER_COLD_LIVE,
                    place_sched.TIER_COLD_REST}, (
        "exactly the dearest tiers declare themselves gated")


# ------------------------------------------------ the lane term (H4-LANES)

def test_payload_at_any_realistic_depth_undercuts_every_placement_tier(
) -> None:
    """The lane term's first bar, and the anti-starvation one.

    Payload carries the SAME lane term as placement (``20 + 2*d``), so
    the question is not whether the base undercuts — it is whether the
    DEEPEST payload attempt still undercuts the CHEAPEST placement pass,
    which is the coarsest lane's ring at depth 0. If it ever stopped
    doing so, the 2026-08-17 starvation would come back on exactly the
    ladders the lanes exist for.
    """
    deepest_payload = recipe.COST_PAYLOAD + _lane(MAX_LANE_DEPTH)
    cheapest_placement = min(row.cost for row in place_sched.PLACEMENT_TIERS)
    assert deepest_payload < cheapest_placement, (
        f"payload at depth {MAX_LANE_DEPTH} costs {deepest_payload}, which "
        f"does not undercut a coarse ring pass at {cheapest_placement}")


def test_within_every_rung_coarse_precedes_fine() -> None:
    """The cascade, as an arithmetic property of one order.

    v1 ran the lanes as a barrier-separated sequence; holo2 runs them in
    one priority order and lets coarse-before-fine EMERGE. That only
    works if the term is strictly monotone in depth at every tier — which
    is what makes a coarse pass of any class beat the same class one rung
    finer, sheet-wide, with nothing arranging it. Asked off each row's
    OWN rung term, so it covers cold's larger one too.
    """
    for row in place_sched.PLACEMENT_TIERS:
        costs = [row.cost + row.rung_cost * depth
                 for depth in range(MAX_LANE_DEPTH + 1)]
        assert costs == sorted(costs) and len(set(costs)) == len(costs), (
            f"{row.tier}: the rung term does not order the rungs: {costs}")


def test_the_lane_term_never_crosses_an_ordinary_inter_tier_gap() -> None:
    """The bar that keeps the term a tie-break instead of a tier.

    A finer word-centre pass has to keep outranking a coarse wide pass,
    or the lanes have quietly become a class of their own. So the whole
    stack a window can ever carry — the lane term at the deepest
    realistic ladder PLUS the child premium — must sit under the smallest
    gap between adjacent tiers. The child premium went LIVE at W3
    (subdivision), so this stack is now a real window's price rather than
    the constraint W3 was asked to build against.

    SCOPED TO THE ORDINARY TIERS AT W4, and the scoping is the ruling
    rather than a weakening. The cold pair sits 10 apart — narrower than
    this stack — and nothing can carry the stack INTO that gap: a child
    never runs cold (ruling 1), and cold's own rung term is not this one.
    Cold's equivalent properties are pinned below, on cold's own terms.
    """
    tiers = sorted(row.cost for row in ORDINARY_TIERS)
    gaps = [b - a for a, b in zip(tiers, tiers[1:])]
    stack = _lane(MAX_LANE_DEPTH) + place_sched.CHILD_PREMIUM
    assert 0 < place_sched.LANE_COST_PER_RUNG
    assert stack < min(gaps), (
        f"lane term {_lane(MAX_LANE_DEPTH)} + child premium "
        f"{place_sched.CHILD_PREMIUM} = {stack} reaches across the "
        f"smallest inter-tier gap {min(gaps)}")
    for cheaper, dearer in zip(tiers, tiers[1:]):
        assert cheaper + stack < dearer


# ------------------------------------------------- the re-read's pin (F2a)

def test_the_re_read_takes_rf1s_own_price_and_sits_above_the_ladder(
) -> None:
    """F2a (ruling J2-3, 2026-08-23): the two spellings of ONE number.

    The re-read (``resample.resample_window``) is RF1's other half — it
    exists only where a revision was adopted, and it re-reads a window
    the ladder already placed. So it takes RF1's own entry price rather
    than a constant of its own: charging it LESS would let it preempt
    the ladder the revision itself waited behind (RULING I2's "after the
    ladder, emergent"), and charging it MORE would put the two halves of
    one mechanism at different places in the one global order.

    THE FORK: ``recipe.COST_REFINE`` moving on the engine's side while
    ``place_tiers.RESAMPLE_TIER`` stays where it is. Every source-job
    cost is priced from ``solve``'s table and every queue cost from a
    recipe entry, so the two would silently interleave the wrong way
    round with the whole suite still green — the same failure this file
    exists for, one tier further up.

    It is deliberately NOT a member of ``PLACEMENT_TIERS``: that table is
    the LADDER, every property asserted over it is about ways of PLACING
    an unplaced window, and this is a re-read of a placed one. The two
    relations that DO bind it are asserted here instead.
    """
    assert place_tiers.RESAMPLE_TIER.cost == recipe.COST_REFINE
    assert place_tiers.RESAMPLE_TIER.tier == place_tiers.TIER_RESAMPLE
    assert place_tiers.RESAMPLE_TIER not in place_sched.PLACEMENT_TIERS
    assert (place_tiers.TIER_PRICE[place_tiers.TIER_RESAMPLE]
            is place_tiers.RESAMPLE_TIER), (
        "the scheduler prices every tier it can offer out of one table")
    dearest_ordinary = max(
        row.cost + _lane(MAX_LANE_DEPTH) + place_sched.CHILD_PREMIUM
        for row in ORDINARY_TIERS)
    assert dearest_ordinary < place_tiers.RESAMPLE_TIER.cost, (
        f"the dearest ordinary pass costs {dearest_ordinary} and the "
        f"re-read {place_tiers.RESAMPLE_TIER.cost}: the re-read is not "
        "above the ladder it re-reads")
    # AND IT INHERITS RF1'S OWN INVERSION, which is recorded rather than
    # asserted away: at the deepest rungs a cold sweep costs MORE than
    # this (``cold_rest`` from rung 3, ``cold_live`` from rung 4 — the
    # arithmetic ``solve/refine.py`` states for ``COST_REFINE``), so a
    # re-read preempts a cold pass that is still ready. Both halves of
    # one mechanism carry one price, so they carry one open question;
    # the price is PROVISIONAL and moves in both spellings at once.
    deepest_cold = max(row.cost + row.rung_cost * MAX_LANE_DEPTH
                       for row in COLD_TIERS)
    assert deepest_cold > place_tiers.RESAMPLE_TIER.cost == recipe.COST_REFINE
    assert not place_tiers.RESAMPLE_TIER.gated, (
        "priced, not gated (RULING I2) — the same standing RF1's own "
        "GATE_ALWAYS recipe entry has")
    assert (place_tiers.RESAMPLE_TIER.rung_cost
            == place_tiers.LANE_COST_PER_RUNG), (
        "a re-read does the same work whatever lane it reads, so its "
        "rung term is the ordinary tie-break and not cold's price")


# ------------------------------------------------------- cold's own pins (W4)

def test_every_cold_clears_the_dearest_ordinary_pass() -> None:
    """"Both flavours sit above everything else current" (ruled).

    Not "above wide's base" — above wide at the DEEPEST realistic lane,
    which is the dearest ordinary pass a real capture can produce, child
    premium included. Otherwise a coarse cold could outrank a fine wide
    consult, and the cheap questions would stop being exhausted first.
    """
    dearest_ordinary = max(
        row.cost + _lane(MAX_LANE_DEPTH) + place_sched.CHILD_PREMIUM
        for row in ORDINARY_TIERS)
    cheapest_cold = min(row.cost for row in COLD_TIERS)
    assert dearest_ordinary < cheapest_cold, (
        f"the dearest ordinary pass costs {dearest_ordinary} and the "
        f"cheapest cold {cheapest_cold}: cold is not above everything else")


def test_a_rungs_four_cold_prices_ascend_and_never_cross_the_next_rung(
) -> None:
    """The ruled ORDER, with the children back in it (2026-08-18).

    A rung offers FOUR cold passes once children run the tier too: a
    whole window's live and rest, and a child's live and rest at the
    premium. The property is that those four ascend in the ruled sense
    and stay INSIDE their rung —

        live(d) < child-live(d) < rest(d) < child-rest(d) < live(d+1)

    — which is the "exhaust before specializing" reading applied to a
    pair rather than to a gap: a child's live still comes after every
    whole window's live at that rung, a child's rest after every whole
    window's rest, and nothing at rung d reaches past the first question
    of rung d+1. It is what cold's larger rung term buys: a term smaller
    than the pair's own 10-point gap would let rungs interleave.
    """
    live, rest = COLD_TIERS
    assert (live.tier, rest.tier) == (place_sched.TIER_COLD_LIVE,
                                      place_sched.TIER_COLD_REST)
    premium = place_sched.CHILD_PREMIUM
    prices: list[tuple[int, str]] = []
    for depth in range(MAX_LANE_DEPTH + 1):
        rung = [(row.cost + row.rung_cost * depth + child * premium,
                 f"{row.tier}{'/child' if child else ''}@{depth}")
                for row in COLD_TIERS for child in (0, 1)]
        rung.sort()
        assert [name for _cost, name in rung] == [
            f"{live.tier}@{depth}", f"{live.tier}/child@{depth}",
            f"{rest.tier}@{depth}", f"{rest.tier}/child@{depth}"], rung
        prices.extend(rung)
    assert prices == sorted(prices), (
        f"a rung's cold passes cross into the next rung: {prices}")
    assert len({cost for cost, _name in prices}) == len(prices), (
        "two distinct cold passes share a price")


def test_the_child_premium_is_the_only_thing_depth_adds() -> None:
    """One premium, one place, and it reaches every tier (2026-08-18).

    The reversal made the price expression UNIFORM — tier cost, plus that
    tier's rung term times the window's rung, plus the premium if it is a
    child — so a child runs the same ladder a whole window does and
    merely pays a little more for each rung of it. Pinned on the source
    because the failure this file exists to catch is a schedule and a
    gate that disagree: the premium reaching the heap key but not the
    cost the engine gates on, or one tier family quietly missing it.
    """
    # The price expression moved to ``place_slot`` at F2a
    # (2026-08-23), when the re-read tier took ``place_sched``
    # past its cap and the ladder became a subject of its own.
    # The pin follows the code, not the file it used to sit in.
    source = Path(place_slot.__file__).read_text()
    priced = source.split("def price(", 1)[1].split("def sort_key", 1)[0]
    assert "CHILD_PREMIUM if self.depth" in priced, (
        "the premium must be added in `price`, where BOTH the heap key "
        "and the engine's gate read it")
    assert "row.rung_cost * self.lane_depth" in priced, (
        "each tier family's own rung term must be the one applied")
    assert source.count("CHILD_PREMIUM if self.depth") == 1, (
        "the premium is added in exactly one expression; a second place "
        "adding it is a schedule and a gate that disagree")


def test_the_child_premium_stacks_on_the_lane_term() -> None:
    """W3's ruling as arithmetic: EXHAUST THE SHEET BEFORE SPECIALIZING.

    The user's words (2026-08-17): "work on subdivided windows is just a
    tad more expensive than work on normal windows — the point is to
    exhaust the sheet before specializing". Under one global cost order
    that is a property to prove, not to hope for, and it has two halves.

    FIRST, the stack: a child pays its rung term AND the child premium,
    so the two ADD. Its price at any ordinary tier is that tier plus at
    most ``_lane(MAX_LANE_DEPTH) + CHILD_PREMIUM``, which the pin above
    keeps under one inter-tier gap — so a child still cannot outrank a
    whole window one tier cheaper. (Cold's own version of the property
    is a pair rather than a gap, and has its own pin above.)

    SECOND, the ordering the ruling is actually about: AT THE SAME RUNG,
    every whole window is cheaper than every child, at every tier —
    EVERY tier, since the 2026-08-18 reversal put children back on the
    cold pair too. Same rung is the honest comparison and not a
    weakening: a child is admitted on its parent's footing, so parent and
    child are always on one lane, and the term they share cancels.

    WHAT IS DELIBERATELY NOT CLAIMED: a coarse child (40 + 0 + 5 = 45)
    does outrank a fine whole window (40 + 8 = 48), because the lane
    span is wider than the premium. That is the cascade's own law, not a
    leak — the coarse lane is the cheaper reading of the same ink
    everywhere on this scale, and the premium was ruled "just a tad",
    not "a rung".
    """
    assert place_sched.CHILD_PREMIUM > 0
    for row in place_sched.PLACEMENT_TIERS:          # children run them all
        for depth in range(MAX_LANE_DEPTH + 1):
            whole = row.cost + row.rung_cost * depth
            child = whole + place_sched.CHILD_PREMIUM
            assert whole < child, (
                f"{row.tier} at rung {depth}: a child ({child}) does not "
                f"pay more than the whole window ({whole})")
    assert "CHILD_PREMIUM" not in Path(place_job.__file__).read_text(), (
        "the job prices nothing: what a pass costs is the scheduler's")


def test_ingest_is_admitted_ahead_of_everything() -> None:
    """H4 streaming ingestion: where ingest sits in the one order.

    PRICE: below the cheapest placement tier, because it is the work that
    CREATES all other work — no capture, no regions; no regions, no
    windows.

    The ``quiesces`` half of this pin is GONE with the quiescent gate
    (2026-08-17): ingest needed an exemption from a gate that no longer
    exists, and there is nothing left for a work class to be off the
    axis OF.
    """
    assert recipe.COST_INGEST < min(row.cost
                                    for row in place_sched.PLACEMENT_TIERS)
    ingest = recipe.RECIPE_V1.entries[0]
    assert ingest.task_class == recipe.TASK_INGEST
    assert ingest.gate == recipe.GATE_ALWAYS
    assert ingest.cost == recipe.COST_INGEST
    assert all(entry.gate == recipe.GATE_ALWAYS
               for entry in recipe.RECIPE_V1.work_entries()), (
        "no work entry defers: footing progression is priced")


def test_calibration_sits_between_ingest_and_payload() -> None:
    """H5 P1: the region ctx fit's place in the one order.

    The plan's own number: 15, between ingest (10) and payload (20+2d),
    so a pool that clears its floors is fitted BEFORE its tiles are
    decoded and a region's tiles decode CALIBRATED the first time — at
    every rung, since the fit carries the same lane term the attempts it
    serves do. Refits take no special casing: the fit descriptor spends
    at the wall like payload's, so ``work_price`` lifts every re-fit into
    the re-work band (90+) and a refit follows a BATCH of new labels.
    """
    assert (recipe.COST_INGEST < recipe.COST_CALIBRATION
            < recipe.COST_PAYLOAD)
    for depth in range(MAX_LANE_DEPTH + 1):
        assert (recipe.COST_CALIBRATION + _lane(depth)
                < recipe.COST_PAYLOAD + _lane(depth))
    entry = next(entry for entry in recipe.RECIPE_V1.entries
                 if entry.task_class == recipe.TASK_CALIBRATION)
    assert entry.cost == recipe.COST_CALIBRATION
    assert entry.gate == recipe.GATE_ALWAYS
    # A refit ages into the band exactly as a payload re-attempt does —
    # dearer than every word pass, cheaper than the wide consult — which
    # is what "a region refit follows a BATCH of new labels" is made of.
    refit = recipe.work_price(recipe.COST_CALIBRATION, 0, 1)
    assert recipe.COST_PLACE_WORD_REST < refit < recipe.COST_PLACE_WIDE
    assert refit == recipe.REWORK_BASE


def _placement_price(row, depth: int, child: bool = False) -> int:
    """What a PLACEMENT descriptor really costs — the tier's OWN rung term.

    ``place_sched.WindowPlan.price``, restated on the engine's side of the
    wall. It is not ``_lane(depth)``: an ordinary tier's rung term is the
    small lane tie-break, and a cold tier's is ``COLD_COST_PER_RUNG`` = 20,
    ten times bigger. Reading cold's price through ``_lane`` is what made
    the first W3 pin vacuous (W3 review, 2026-08-23).
    """
    return (row.cost + row.rung_cost * depth
            + (place_sched.CHILD_PREMIUM if child else 0))


def test_pose_refinement_prices_above_every_other_tier() -> None:
    """RE-PINNED W3 (RULING I2, the user's ruling of 2026-08-23), then
    CORRECTED by the W3 review (2026-08-23).

    OLD: ``COST_REFINE == REWORK_BASE == 90``, "born in the re-work band"
    — dearer than every word pass, CHEAPER than the wide consult (120)
    and than both cold tiers. NEW: **200, above ``COST_PLACE_COLD_REST``
    (150), the dearest tier any other family DECLARES.**

    WHY IT MOVED, and it is not a tuning. "After the ladder" is what
    refinement wants; v1 got it from a BARRIER and holo2 has none by
    design. The ruling refuses to invent a phase and prices instead: at
    200 a revision fires only when nothing cheaper is ready, so the
    ordering is an emergent property of the pull model rather than a rule
    to enforce. At 90 it fired "as soon as the word bands drain", which
    is measurably not the same thing — the wide consult and both cold
    tiers still had work.

    THE FORK THIS PIN NOW NAMES, and it is the one the first version of
    it walked into: comparing refine against ``work_price(COLD_REST,
    _lane(depth), 0)``. A cold descriptor never carries ``_lane`` — it
    carries its own 20-per-rung term — so that comparison reduces to
    200 + 2d > 150 + 2d and can never fail. Priced honestly, the two
    ladders CROSS, and the crossover depths are asserted below rather
    than hidden: refine outranks every declared tier cost, every ordinary
    pass at every depth, and cold through rung 2; ``cold_rest`` overtakes
    it from rung 3 and ``cold_live`` from rung 4. Both are reachable —
    ``MAX_LANE_DEPTH`` is 4 and a 4800-dpi c2 capture lays five rungs —
    so on the two deepest cold rungs the ruled property inverts. Whether
    that stands or the entry moves to 240 is OPEN for the user; either
    way a reprice must come through this test.

    The ageing term: ``work_price`` lifts a re-attempt to
    ``max(base, 90 + 5*(n-1))``, which reaches 200 exactly at the 23rd
    re-fire and first EXCEEDS it at the 24th. So the entry sits past
    every other family's FIRST-ATTEMPT price unconditionally, and an aged
    re-attempt does cross it — the band grows without bound by design.

    Calibration's 15 is still the mirror and the comparison is still the
    point: a ctx fit must run BEFORE the decodes it improves; a pose
    revision is worth asking for only after everything cheaper has
    drained.
    """
    assert recipe.COST_REFINE == 200
    entry = next(entry for entry in recipe.RECIPE_V1.entries
                 if entry.task_class == recipe.TASK_REFINE)
    assert entry.cost == recipe.COST_REFINE
    assert entry.gate == recipe.GATE_ALWAYS
    assert recipe.COST_CALIBRATION < recipe.COST_REFINE

    # Above every tier's DECLARED cost — the claim the prose makes.
    assert recipe.COST_REFINE > max(
        row.cost for row in place_sched.PLACEMENT_TIERS)
    # Above every ORDINARY pass a real capture can produce, child
    # premium and deepest lane included.
    dearest_ordinary = max(_placement_price(row, MAX_LANE_DEPTH, child=True)
                           for row in ORDINARY_TIERS)
    assert recipe.work_price(
        recipe.COST_REFINE, _lane(0), 0) > dearest_ordinary

    # And NOT above every cold pass: the crossover, pinned by depth.
    live, rest = COLD_TIERS
    crossings = {}
    for row in COLD_TIERS:
        for depth in range(MAX_LANE_DEPTH + 1):
            refine_here = recipe.work_price(
                recipe.COST_REFINE, _lane(depth), 0)
            if _placement_price(row, depth) > refine_here:
                crossings[row.tier] = depth
                break
    assert crossings == {rest.tier: 3, live.tier: 4}, (
        "the measured crossover moved: refine outranks cold_rest through "
        "rung 2 and cold_live through rung 3, and is overtaken after "
        f"that — got {crossings}")
    # What it would take to make the ruled property unconditional, so a
    # future reprice has the number in front of it.
    assert max(_placement_price(row, MAX_LANE_DEPTH, child=True)
               for row in place_sched.PLACEMENT_TIERS) == 235

    for depth in range(MAX_LANE_DEPTH + 1):
        first = recipe.work_price(recipe.COST_REFINE, _lane(depth), 0)
        # The ordinal cannot lift a re-fire past the entry until the band
        # itself passes 200: 90 + 5*22 = 200 exactly at the 23rd, so the
        # 24th is the first re-fire that costs more than the first one.
        assert first == recipe.work_price(recipe.COST_REFINE, _lane(depth), 23)
        assert recipe.work_price(recipe.COST_REFINE, _lane(depth), 24) \
            == first + recipe.REWORK_STEP


def test_a_placement_entry_declares_the_cheapest_placement_tier() -> None:
    """Both of them, since the entry price now reaches nothing the pull
    schedules.

    Placement work is priced per TIER by the source that owns it, so an
    entry's own cost is only what a DESCRIPTOR on this family would carry
    — and the finer entry's old ``COST_PLACE_WIDE`` (how "later" was
    spelled for the quiescent gate) would misprice one.
    """
    assert recipe.COST_PLACE_ENTRY == recipe.COST_PLACE_RING == min(
        row.cost for row in place_sched.PLACEMENT_TIERS)
    assert {entry.cost for entry in recipe.RECIPE_V1.entries
            if entry.task_class == recipe.TASK_PLACE} == {
        recipe.COST_PLACE_ENTRY}


# ------------------------------------------- the re-work band (H5 aging)

def _rework(ordinal: int, depth: int = 0) -> int:
    """What a payload attempt costs at its ``ordinal``-th prior attempt."""
    return recipe.work_price(recipe.COST_PAYLOAD, _lane(depth), ordinal)


def test_a_first_attempt_is_priced_exactly_as_it_was() -> None:
    """The ruling's own precondition: payload-first stands.

    "A key's FIRST attempt prices as today (payload 20+2d — payload-first
    stands; the starvation lesson is not relitigated)." So the price
    function must be the IDENTITY on entry cost plus lane term at ordinal
    zero, at every rung and for every entry price in the scale — which is
    what makes "first-attempt behaviour did not change anywhere" a
    property of the arithmetic instead of a claim about call sites.
    """
    for depth in range(MAX_LANE_DEPTH + 1):
        assert _rework(0, depth) == recipe.COST_PAYLOAD + _lane(depth)
    for base in (recipe.COST_INGEST, recipe.COST_PAYLOAD,
                 recipe.COST_PLACE_RING, recipe.COST_PLACE_COLD_REST):
        for premium in (0, 1, _lane(MAX_LANE_DEPTH)):
            assert recipe.work_price(base, premium, 0) == base + premium


def test_a_first_re_attempt_lands_between_word_rest_and_wide() -> None:
    """"RE-attempts price into a re-work band BELOW WIDE" (ruled).

    The strong reading, deliberately: below wide's BASE, not merely below
    wide at some rung — so a re-decode outranks the dear consult on every
    lane a real capture can produce. Above word rest, because that is
    what "the cheaper bands have drained first" means: the whole ordinary
    word ladder is asked before a tile is decoded a second time, which is
    what buys maximal accumulated evidence per attempt.
    """
    for depth in range(MAX_LANE_DEPTH + 1):
        price = _rework(1, depth)
        assert recipe.COST_PLACE_WORD_REST < price < recipe.COST_PLACE_WIDE, (
            f"a first re-attempt at rung {depth} costs {price}, outside the "
            "band the ruling put below wide and above the word passes")
    assert _rework(1) == recipe.REWORK_BASE


def test_the_band_is_strictly_ordered_in_the_ordinal() -> None:
    """Generations through cost: every re-attempt is dearer than the last.

    At a FIXED rung, which is the honest comparison and the same one the
    child premium's pin makes: ``REWORK_STEP`` (5) is smaller than the
    lane span (8), so a deep first re-attempt does outrank a shallow
    second one. That is deliberately NOT claimed — the coarse lane is the
    cheaper reading of the same ink everywhere on this scale, and the
    step was ruled "a small per-ordinal step", not a rung.
    """
    assert recipe.REWORK_STEP > 0
    for depth in range(MAX_LANE_DEPTH + 1):
        prices = [_rework(ordinal, depth) for ordinal in range(1, 40)]
        assert prices == sorted(prices) and len(set(prices)) == len(prices)
        assert prices[0] > _rework(0, depth), (
            "a re-attempt is never cheaper than the first attempt was")
    assert recipe.REWORK_STEP < _lane(MAX_LANE_DEPTH), (
        "the ordinal step reorders within the band; a step that dominated "
        "the lane span would make an ordinal a tier of its own")


def test_the_ordinal_prices_past_wide_then_past_cold() -> None:
    """THE HORIZON — the rejected cap, re-emerging as a price.

    "The per-ordinal step eventually prices a hopeless key's re-attempts
    past cold, where the dryness gate holds them to the very end — the
    cap re-emerges as a HORIZON, not a wall; nothing is ever refused."
    Asserted as arithmetic, which is the only way an UNBOUNDED term can
    be pinned: there is an ordinal past every price this scale declares,
    including the dearest pass any window can ever run (cold rest, at the
    deepest realistic rung, at the child premium).
    """
    def first_past(bar: int) -> int:
        return next(n for n in range(1, 10_000) if _rework(n) > bar)

    # The 7th re-attempt costs exactly wide and the 11th exactly cold's
    # live flavour, so the first STRICTLY dearer ordinals are 8 and 12.
    assert _rework(7) == recipe.COST_PLACE_WIDE
    assert _rework(11) == recipe.COST_PLACE_COLD_LIVE
    assert first_past(recipe.COST_PLACE_WIDE) == 8
    assert first_past(recipe.COST_PLACE_COLD_LIVE) == 12
    dearest = max(row.cost + row.rung_cost * MAX_LANE_DEPTH
                  for row in place_sched.PLACEMENT_TIERS) + (
                      place_sched.CHILD_PREMIUM)
    assert _rework(first_past(dearest)) > dearest, (
        "no ordinal outprices the dearest scheduled pass: the horizon is "
        "a wall after all")


def test_the_re_work_term_never_discounts_and_never_refuses() -> None:
    """L7 as arithmetic: a price may reorder work, never narrow a domain.

    Two halves. The term is a ``max``, so it can only make work DEARER —
    a family whose own class already prices above the band keeps its own
    price, and no descriptor is ever cheapened by having failed. And it
    is a finite integer at every ordinal, so there is no ordinal at which
    a descriptor stops being schedulable: it goes to the back of one
    order, which is where the ruling put it.
    """
    for ordinal in range(0, 200):
        assert _rework(ordinal) >= _rework(0)
        assert recipe.work_price(recipe.COST_PLACE_COLD_REST, 0,
                                 ordinal) >= recipe.COST_PLACE_COLD_REST
    assert recipe.work_price(recipe.COST_PLACE_COLD_REST, 0, 1) == (
        recipe.COST_PLACE_COLD_REST), (
        "the band lifts a cheap class into it; it does not pull a dear "
        "class down to it")


def test_ingest_is_under_payload_is_under_everything() -> None:
    """The order the whole table exists to state, end to end.

    Read as one sentence over the real numbers, at the deepest realistic
    lane, so a re-spacing that got one row wrong cannot hide behind the
    per-property tests above.
    """
    payload = [recipe.COST_PAYLOAD + _lane(depth)
               for depth in range(MAX_LANE_DEPTH + 1)]
    placement = [row.cost + row.rung_cost * depth
                 for row in place_sched.PLACEMENT_TIERS
                 for depth in range(MAX_LANE_DEPTH + 1)]
    assert recipe.COST_INGEST < min(payload) <= max(payload) < min(placement)


# NOTE (H4-LANES stage 2): the coarse-SELECTOR wall-crossing pin that
# stood here is retired with its subject. ``place_sched`` used to resolve
# each window's premium by asking the plane which footings were
# ``"coarsest"``, and a drift in that literal would have priced every
# window at the coarse rate; it asks ``PlaneView.footing_depth`` now,
# which is a number and not a word, so there is no spelling left to
# drift. The selector vocabulary itself is still validated where it is
# consumed (``Recipe.__post_init__``, ``SessionPlane.footing_ids``).

"""The placement cost table: what a pass costs, and why it sits there.

Carved out of ``place_sched`` at W4, when the cold pair took the table
past that file's cap. The seam is real rather than arithmetic: THIS is
policy DATA — six priced classes, two rung terms and a premium, each row
carrying its own provenance — while ``place_sched`` is the mechanism that
reads it (a monotone set, a flag each, a heap). Nothing here imports
anything of holo2's, which is the test that the split was along a joint.

TIERS ARE PRICES, NOT LADDERS (Q3+Q6)
--------------------------------------
:data:`PLACEMENT_TIERS` is declared as data the way
``place_model.OR9_FLOORS`` declares the placement constants. The order is
**payload** < ring consult < word centre < word rest < wide consult <
cold live < cold rest: payload's descriptors compete in the SAME global
order because their certificates DELETE placement work outright (a
covered window never poses again), and the expensive tiers are GATED —
admissible only when nothing cheaper is ready or in flight anywhere. That
is the user's ruling verbatim: "if we devolve into 'let's run a cold
search on everything remaining' before all payload is decoded, we are
going to burn ourselves." AMENDED 2026-08-17: payload used to interleave
BETWEEN word rest and wide; a real nine-platen run measured it starving
there — 1,287 armed payload workers, zero tiles attempted after 431
fires, because placement on a domain that size never dries — so it moved
below every placement rung (``engine.recipe.COST_PAYLOAD``). Nothing
about the gating changed.

The numbers live on the engine's side too (``engine.recipe``'s cost
scale) because neither package may import the other, and a data test pins
the two spellings equal (``tests/engine/test_cost_vocabulary.py``) —
the same wall-crossing discipline the close-consult modes use.
PROVISIONAL, all of it: these are ORDERS ratified by the ruling, not
measured costs, and a number that moves moves here and in ``recipe`` in
one edit.

TWO RUNG TERMS, AND THE DIFFERENCE IS WHAT W4 ADDED
----------------------------------------------------
Every ordinary tier does the same 49-hypothesis work whatever lane it
reads, so :data:`LANE_COST_PER_RUNG` is a TIE-BREAK: small enough to
reorder within a tier and never across one, which is what makes
coarse-before-fine emerge from one priority order instead of a barrier.
A cold pass IS its transform, so :data:`COLD_COST_PER_RUNG` is a real
price — ten times the lane term, and big enough that a rung's two
flavours are both asked before the next rung's first one.

THE RE-WORK BAND SITS IN THIS SCALE, AND ITS HOME IS THE ENGINE
----------------------------------------------------------------
H5's re-work aging (user rulings 2026-08-19, H5-PLAN "RE-WORK AGING")
adds one term to the price function: a DESCRIPTOR's re-attempt prices at
``REWORK_BASE + REWORK_STEP*(n-1)``, plus its own lane term, where ``n``
is the attempt count its durable spend row already holds. The band is
declared with the rest of the scale in ``engine.recipe`` — one home,
because it is the PRICE FUNCTION's third term and neither half of a
placement tier — but it is spelled out here because the ruling is stated
against THIS table and every property it has to keep is a relation to a
row of it:

* the first re-attempt (90, +2 per rung) lands strictly between
  :data:`TIER_WORD_REST` and :data:`TIER_WIDE` — "BELOW WIDE" is the
  ruling verbatim — so a failed tile's re-decode fires once the word
  passes have drained and still ahead of the dear consult;
* the ordinal is UNBOUNDED, so it crosses wide at the 7th re-attempt
  and cold at the 11th: the cap the user rejected re-emerges as a
  HORIZON, never a wall, and nothing is ever refused;
* PLACEMENT takes no term, which is why nothing in this module reads
  one. That is structural rather than a carve-out: this table prices a
  work SOURCE, whose repetition is bounded by the ready bit and the
  tried set and which spends nothing at the wall — and the ordinal is a
  spend-ledger quantity.

All of it is pinned across the wall in
``tests/engine/test_cost_vocabulary.py``, beside the pins that hold the
two spellings of this table equal.
"""
from __future__ import annotations

from dataclasses import dataclass

TIER_RING = "ring_consult"
TIER_WORD_CENTRE = "word_centre"
TIER_WORD_REST = "word_rest"
TIER_WIDE = "wide_consult"
#: COLD, IN TWO FLAVOURS (W4). The names are the tier vocabulary and the
#: flavour vocabulary at once — a fire is told which one it is running and
#: derives that flavour's page set itself, at fire time.
TIER_COLD_LIVE = "cold_live"
TIER_COLD_REST = "cold_rest"
COLD_TIERS: tuple[str, ...] = (TIER_COLD_LIVE, TIER_COLD_REST)

#: THE RE-READ (F2a, ruling J2-3, 2026-08-23). Not a rung of the
#: placement LADDER and deliberately not a member of
#: :data:`PLACEMENT_TIERS`: every property that table declares — payload
#: undercuts it, coarse precedes fine within it, cold clears all of it —
#: is about ways of PLACING an unplaced window, and this is a re-read of
#: a window that is already placed. It has one member, one price and one
#: eligibility (``place_slot.Slot.resample``), and it is above
#: everything in that table by construction.
TIER_RESAMPLE = "resample"



#: THE LANE TERM (H4-LANES stage 2). A window runs every tier at that
#: tier's cost PLUS this per RUNG DEPTH — 0 on the coarsest lane of its
#: capture, 2 on the next, and so on. It replaces the flat premium of 1
#: that the 2026-08-17 pricing ruling landed with, and the difference is
#: the wave: a flat offset can only say "finer", while a depth term says
#: which rung, which is what makes coarse-before-fine hold sheet-wide
#: across a ladder of five instead of only between two classes.
#:
#: WHY 2, on a scale where the tiers are 20 apart. The term must reorder
#: only WITHIN a rung — a finer word-centre pass has to keep outranking a
#: coarse wide pass, or this stops being a tie-break and becomes a tier of
#: its own. The deepest realistic ladder is five rungs (c3 at 4800 dpi:
#: 2/4/8/12/24), so the term spans 8, and 8 plus the child premium
#: reserved below is 13 — under the smallest gap between two ORDINARY
#: tiers, 20, with room to spare. The second bar is the payload
#: interleave: payload at the same depth (20 + 2d, at most 28) must
#: undercut even the cheapest placement rung at depth 0 (40). Both are
#: pinned in ``tests/engine/test_cost_vocabulary.py``.
LANE_COST_PER_RUNG = 2

#: COLD'S OWN RUNG TERM (W4), ten times the lane term, and the reason is
#: that cold's rung is a PRICE rather than a tie-break. Every other tier
#: does the same 49-hypothesis work whatever lane it reads, so its rung
#: term exists only to order coarse before fine. A cold fire transforms
#: the page's whole cell lattice and pays an inverse transform per page:
#: the same arithmetic at a finer rung buys a strictly worse deal for it,
#: and the flavour pair's own 10-point gap has to fit INSIDE one rung
#: step or the pairs would interleave. At 20 they do not —
#: ``rest(d) = 150 + 20d < 160 + 20d = live(d+1)`` — so every rung's two
#: cheap questions are exhausted before the next rung's are asked.
#: Spelled again on the engine's side (``engine.recipe``).
COLD_COST_PER_RUNG = 20


@dataclass(frozen=True)
class TierPrice:
    """One cost class, declared with what it is and why it sits there."""

    tier: str
    cost: int
    gated: bool
    provenance: str
    #: WHAT ONE RUNG OF DEPTH ADDS to this tier. The lane term for every
    #: ordinary tier; cold's own, much larger term for the cold pair.
    rung_cost: int = LANE_COST_PER_RUNG


#: The cost table (Q3+Q6). PROVISIONAL, like everything else the receiver
#: schedules on: these are ORDERS, ratified by the ruling, not measured
#: costs — the wave's measurement battery runs at its end, and a number
#: that moves moves in this table and nowhere else.
PLACEMENT_TIERS: tuple[TierPrice, ...] = (
    TierPrice(TIER_RING, 40, False,
              "the cheap route: one fit plus <=8 seeded 49-hypothesis "
              "searches, and v1 reaches all but one window of a page by it"),
    TierPrice(TIER_WORD_CENTRE, 60, False,
              "one fit plus Stage A over the historical most-interior slot "
              "of each orientation — how a page is seeded from nothing"),
    TierPrice(TIER_WORD_REST, 80, False,
              "the remaining slots: the same fit, a much wider Stage-A "
              "sweep, and only worth it where the centre found nothing"),
    TierPrice(TIER_WIDE, 120, True,
              "nearest-K anchors at any distance plus the regional-affine "
              "fit (R-B); GATED — dear enough that pending payload, whose "
              "certificates delete placement work, must drain first"),
    TierPrice(TIER_COLD_LIVE, 140, True,
              "the correlation sweep over the pages this session already "
              "has a committed pose on — the cheaper flavour, because the "
              "producer already knows those pages reached the platen",
              rung_cost=COLD_COST_PER_RUNG),
    TierPrice(TIER_COLD_REST, 150, True,
              "the same sweep over the declared page domain MINUS the live "
              "pages: the full-sweep flavour, priced above its rung's live "
              "one, and an empty set on a single-sheet volume",
              rung_cost=COLD_COST_PER_RUNG),
)

#: WHAT A RE-READ COSTS, AND WHY IT IS RF1'S OWN NUMBER (F2a). The
#: re-sample exists only because a revision was adopted, and a revision
#: is priced at the TOP of the whole scale — ``engine.recipe.COST_REFINE``
#: = 200, above ``TIER_COLD_REST`` (150), the dearest tier this table
#: declares — so that it fires only when nothing cheaper is ready
#: (RULING I2, "after the ladder as an emergent property"). Its
#: consequence takes the same number rather than a new constant: charging
#: the re-read LESS would let it preempt the ladder the revision itself
#: waited behind, and charging it MORE would say the two halves of one
#: mechanism belong at different places in the order. It carries the
#: ordinary lane term, like every non-cold tier, and it is NOT gated:
#: the price does the ordering, exactly as it does for RF1 (whose recipe
#: entry is ``GATE_ALWAYS``). The two spellings of the 200 are pinned
#: equal in ``tests/engine/test_cost_vocabulary.py``.
RESAMPLE_TIER = TierPrice(
    TIER_RESAMPLE, 200, False,
    "the re-read of a placed window through its LIVE pose after RF1 "
    "revised it (ruling J2-3); RF1's own price, because it is RF1's "
    "other half and fires only where a revision was adopted")

#: Every priced class the scheduler can offer: the placement ladder plus
#: the re-read. ``PLACEMENT_TIERS`` stays the LADDER, which is what the
#: cost-vocabulary pins reason over.
TIER_PRICE: dict[str, TierPrice] = {
    row.tier: row for row in (*PLACEMENT_TIERS, RESAMPLE_TIER)}

#: THE DEEPEST LANE a real capture's ladder produces, 0-based, and the
#: depth every bound around this table is stated at. ``auto_ppc_levels``
#: lays c3 at 4800 dpi as 2/4/8/12/24 — five rungs, so the finest sits
#: four above the coarsest — and 4800 is where the ladder stops because
#: the scanner of record stops there (CLAUDE.md channel facts: a Canon
#: 4800x4800 flatbed, decimated to 1600 by doctrine). It is a datum with
#: a source, not a guess: ``tests/solve/test_reading_set.py`` pins it
#: against the generator itself, on the solve side of the wall where a
#: test may name ``capture``.
MAX_LANE_DEPTH = 4

#: THE CHILD PREMIUM, LIVE since W3 (user ruling, 2026-08-17: "work on
#: subdivided windows is just a tad more expensive than work on normal
#: windows — the point is to exhaust the sheet before specializing"). A
#: child pays this ON TOP of its rung term, so the two STACK, and the
#: stack (8 + 5 = 13) fits inside one ordinary inter-tier gap (20) —
#: which is what makes the exhaust-first property PROVABLE rather than
#: hoped: under one global cost order, any ready whole-window pass
#: anywhere on the sheet outranks any child's pass at the same rung, and
#: a child still cannot outrank a whole window one tier cheaper.
#:
#: IT REACHES THE COLD PAIR TOO (W4, the 2026-08-18 reversal — "children
#: get the cold treatment as well; we implement src/holo algorithmically,
#: the thing we change is scheduling and orchestration"). A child's colds
#: are 145 + 20d and 155 + 20d, and the stacking property holds in the
#: shape that matters for a pair rather than for a gap: a child's live
#: sits under its rung's rest (145 < 150) and a child's rest sits under
#: the NEXT rung's live (155 + 20d < 160 + 20d), so the four prices of a
#: rung ascend and never cross into the rung above. That is the same
#: "exhaust before specializing" reading applied inside a pair instead of
#: across a gap.
#:
#: The ladder's entry side governs when children are BORN (only after
#: the wide consult refuses); this governs how they COMPETE once alive.
#: All of it is pinned in ``tests/engine/test_cost_vocabulary.py``.
CHILD_PREMIUM = 5


__all__ = [
    "CHILD_PREMIUM", "COLD_COST_PER_RUNG", "COLD_TIERS",
    "LANE_COST_PER_RUNG", "MAX_LANE_DEPTH", "PLACEMENT_TIERS",
    "RESAMPLE_TIER", "TIER_COLD_LIVE",
    "TIER_COLD_REST", "TIER_PRICE", "TIER_RESAMPLE", "TIER_RING", "TIER_WIDE",
    "TIER_WORD_CENTRE", "TIER_WORD_REST", "TierPrice",
]

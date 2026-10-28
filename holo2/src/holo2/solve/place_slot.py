"""ONE WINDOW IN THE SCHEDULING SET: its flag, its ladder, its price.

Carved out of ``place_sched`` at F2a (2026-08-23), when the re-read tier
took that file past its cap — and the seam is the one W4 already found
on the other side of the same joint. ``place_tiers`` is the cost TABLE
(policy data), ``place_sched`` is the SET, the FLAG PROTOCOL and the
HEAP, and THIS is what the table is read THROUGH: one window's ready bit,
its stage memory, its tried set, its cold arming and the one expression
that turns all of that into a price and a heap key.

WHY IT MOVED, given that W4 said it would not. ``place_sched``'s W6 note
recorded that ``_Slot`` deliberately did NOT travel with the subdivision
half, "because it is what the heap, the ladder and the price are written
over" — and that reason was about GROWTH, which genuinely belongs with
the set. F2a adds a tier that is not a rung of the placement ladder at
all (the re-read of an already-placed window), and with it the ladder
became a subject with its own vocabulary — ``tier()``'s ordering, the
two rung terms, the child premium, the cold pair's offer test — none of
which the flag protocol or the heap reads. The scheduler still owns
every DECISION; this owns the answer to "what does this one window
offer, and what does it cost".

Nothing here reads the store. A slot is derived, never durable: a resume
rebuilds the set from the committed facts and re-tries at worst (the
argument is in ``place_sched``'s header, where the set lives).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..core import ResourceKey
from .place_tiers import (CHILD_PREMIUM, TIER_COLD_LIVE, TIER_COLD_REST,
                          TIER_PRICE, TIER_RESAMPLE, TIER_RING, TIER_WIDE,
                          TIER_WORD_CENTRE, TIER_WORD_REST)
from .placement import STAGE_CENTRE, STAGE_REST
from .plans import WindowPlan
from .words import SlotStage


@dataclass
class ColdOffer:
    """WHICH COLD FLAVOURS HAVE A NON-EMPTY PAGE SET RIGHT NOW (W4).

    ONE object for the whole scheduler, because the two page sets are
    session-global: "the pages with a committed pose" and "the declared
    domain minus those" are the same two answers for every window, so a
    per-slot copy would be the same tuple N times.

    IT IS A DERIVATION, NOT STATE (ruling 2). The scheduler recomputes it
    from the view at every door it holds one — admit, claim, settle — and
    a flavour whose set is empty is simply not offered, costlessly and
    NEVER terminally: nothing is marked, nothing is remembered, and the
    next recomputation offers it again the moment its set fills. That is
    the whole of "it might fill later", with no re-arm machinery.

    The recomputation is cheap AND rare in its effects: ``live`` only
    grows (a pose is identity-frozen), so this tuple can change at most
    twice in a run — once when the first pose lands and live stops being
    empty, once if live ever swallows the whole declared domain and rest
    stops being offerable.
    """

    flavors: tuple[str, ...] = ()


@dataclass
class Slot:
    """One window in the scheduling set: its flag and everything derived.

    Not a record and never durable — this is the whole of what the pull
    model replaced ``WindowRecord``'s scheduling statuses and the hint
    family with.
    """

    plan: WindowPlan
    entry: int
    ordinal: int
    #: THIS WINDOW'S RUNG, 0-based from the coarsest lane of its capture.
    #: Resolved ONCE, at admission, off the plane's own ladder — a
    #: window's footing cannot change, so nothing at fire time asks which
    #: lane it is on. It is the RUNG and no longer a pre-multiplied
    #: premium, because the two tier families multiply it by different
    #: terms (:meth:`price`, and ``place_tiers.TierPrice.rung_cost``).
    lane_depth: int = 0
    #: SUBDIVISION depth: 0 for a laid-out window, 1 for a corner child.
    #: In memory and nowhere else (the no-lineage ruling) — a resumed
    #: parent re-subdivides and the kernel hands back the same extents,
    #: so nothing durable has to remember which windows were children.
    depth: int = 0
    ready: bool = True
    in_flight: bool = False
    #: The best seed distance OFFERED since the last claim — by a ping, or
    #: by the admission peek for a window that entered beside poses that
    #: already stand. ``None`` means "nothing steers this window", which is
    #: what prices it at a word tier instead of the ring tier.
    offered: float | None = None
    tried: set[str] = field(default_factory=set)
    centre_spent: bool = False
    rest_spent: bool = False
    wide_spent: bool = False
    #: THE REFERENCE ONLY EVER POINTS DOWN (the parent-afterlife ruling):
    #: the window ids this slot's subdivision produced, kept as stage
    #: memory because the parent is the one that computed them. A child
    #: never names its parent, and neither does any record.
    children: tuple[ResourceKey, ...] = ()
    subdivided: bool = False
    #: ESCALATED TO COLD and parked there. Set when every child has
    #: exited and none of them placed or was covered — the ruled
    #: afterlife of a parent whose corners did no better than it did.
    #: Cold runs on the parent's FULL extent (correlation wants area).
    #: SINCE W4 this bit is one of the two ways :attr:`cold_armed` gets
    #: set, rather than the place such a window stops.
    cold_parked: bool = False
    #: THE COLD PAIR IS OPEN TO THIS WINDOW (W4). Set by the scheduler at
    #: the ONE place a window's ladder runs out, and never inferred from
    #: the spend bits — because the ordering matters and it is v1's:
    #: a dormant window correlates BEFORE it is quartered, so this bit
    #: goes up first and subdivision waits for the pair to refuse. Depth
    #: is not a condition (the 2026-08-18 reversal): a child arms like
    #: anything else and pays the premium for it.
    cold_armed: bool = False
    cold_live_spent: bool = False
    cold_rest_spent: bool = False
    #: THIS SLOT IS A RE-READ, not a placement (F2a, ruling J2-3). The
    #: window is already placed; what re-admitted it is a pose revision
    #: whose geometry nothing has sampled through yet
    #: (:meth:`PlacementScheduler._needs_resample`). Such a slot offers
    #: the re-read tier and NOTHING else — no consult, no word, no wide,
    #: no cold — because every one of those is a way of ADDRESSING an
    #: unaddressed window and this window's address is committed.
    resample: bool = False
    #: The scheduler's ONE :class:`ColdOffer`, shared by every slot.
    cold_offer: ColdOffer = field(default_factory=ColdOffer)

    @property
    def window_id(self) -> ResourceKey:
        return self.plan.window_id

    @property
    def words_spent(self) -> int:
        return int(self.centre_spent) + int(self.rest_spent)

    @property
    def stage(self) -> SlotStage | None:
        """The cheapest word stage this window has not spent."""
        if not self.centre_spent:
            return STAGE_CENTRE
        if not self.rest_spent:
            return STAGE_REST
        return None

    def tier(self) -> str | None:
        """This window's cheapest available tier, or None when spent.

        An offered seed prices at the ring tier (a ping IS one, and so is
        the admission peek); a window with none prices at its next unspent
        word stage; a window with neither prices at the wide tier, once;
        and an ARMED window then prices at its unspent cold flavours, live
        before rest. ``None`` is dormancy — not an exit, since a later
        ping revives it, and a cold flavour skipped for an empty page set
        is revived by the set filling.

        THE COLD PAIR IS OFFERED ONLY WHERE IT CAN WORK, and both halves
        of that are checked here rather than at the fire: the window must
        be ARMED (:meth:`PlacementScheduler._arm_cold` — its ladder ran
        out and no family of its own will answer for it), and the
        flavour's page set must be non-empty right now. Offering a
        flavour with nothing to sweep would cost a claim, a pass and a
        decision about whether to mark it spent — and marking it would
        make the skip terminal, which is exactly what ruling 2 forbids.
        Depth is NOT a condition: a child climbs this ladder like any
        other member, and pays the premium for it (:meth:`price`).
        """
        if self.resample:
            # ONE OFFER, ONCE. The pass answers for one (window, live
            # pose) and retires either way, so there is no second tier
            # to fall to; a LATER revision re-admits the window as a
            # fresh slot rather than reviving this one.
            return TIER_RESAMPLE
        if self.offered is not None:
            return TIER_RING
        if not self.centre_spent:
            return TIER_WORD_CENTRE
        if not self.rest_spent:
            return TIER_WORD_REST
        if not self.wide_spent:
            return TIER_WIDE
        if self.cold_armed:
            offered = self.cold_offer.flavors
            if not self.cold_live_spent and TIER_COLD_LIVE in offered:
                return TIER_COLD_LIVE
            if not self.cold_rest_spent and TIER_COLD_REST in offered:
                return TIER_COLD_REST
        return None

    def price(self, tier: str) -> int:
        """What one tier costs THIS window: the tier, its rung, its depth.

        THE ONE PLACE ANY TERM IS ADDED, so the heap key and the cost the
        engine gates on cannot disagree about what a pass costs. One
        expression covers both tier families and both windows:

            tier cost + (that tier's rung term x this window's rung)
                      + the child premium, if this is a child

        TWO RUNG TERMS, because there are two kinds of tier. An ordinary
        tier does the same 49-hypothesis work on every lane, so its term
        is a small tie-break that reorders within a tier and never across
        one. A cold pass IS its transform, so its term is a real price —
        big enough that a rung's flavours are both asked before the next
        rung's first one. ONE CHILD PREMIUM either way (the 2026-08-18
        reversal): a child runs the same ladder a whole window does, cold
        included, and merely pays a little more for every rung of it.
        """
        row = TIER_PRICE[tier]
        return (row.cost + row.rung_cost * self.lane_depth
                + (CHILD_PREMIUM if self.depth else 0))

    def sort_key(self) -> tuple[int, float, int]:
        """The heap key: cost class, offered distance, arrival ordinal."""
        tier = self.tier()
        assert tier is not None
        distance = math.inf if self.offered is None else self.offered
        return (self.price(tier), distance, self.ordinal)


__all__ = ["ColdOffer", "Slot"]

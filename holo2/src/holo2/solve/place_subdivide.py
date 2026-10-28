"""The scheduling set's GROWTH half: subdivision and a parent's afterlife.

Split out of ``place_sched.py`` at H4 W6, at the seam W4 named when that
file landed on exactly 1000 lines ("the growth-half seam,
``_subdivide``/``_review_parents``/``_child_verdict``"). The cap is a
seam signal, never a budget to squeeze, and the seam here is the tree's
own: everything in ``place_sched`` shrinks the set — a window leaves by
being placed, covered or retired — and everything in THIS file is the one
way it grows. The vocabulary is a growth vocabulary too (children,
parents, a corner's verdict, the afterlife of a window whose corners did
no better than it did) and none of it appears in the pull model's flag
protocol, its tiers or its heap.

THE SHAPE IS ``engine/replay.py``'s (the house precedent for exactly this
situation, and the reason no class was invented). These are FUNCTIONS
over the running :class:`~holo2.solve.place_sched.PlacementScheduler`,
driving its own machinery — its slot table, its exit ledger, its counters
and its admission door are all its, applied here rather than reimplemented
— and, like that module, nothing here holds state of its own. The
scheduler keeps the three entry points as one-line methods so its own call
sites (and their pins) read exactly as they did.

RELOCATION ONLY (H4 W6): every line below arrived from ``place_sched`` in
its original order with its docstring intact; ``Slot`` did NOT move with
it, because it is what the heap, the tier ladder and the price are written
over and belongs with the mechanism that reads them. The only thing that
moved beside the three functions is :data:`EXIT_SERVED`, which exists for
:func:`child_verdict` and for nothing else.

THE SAFETY ARGUMENT (termination) lives with the set it is about, in
``place_sched``'s "MONOTONE-GROWTH AMENDMENT" — the growth is one
generation deep, a window subdivides at most once, the kernel refuses to
halve below the 70-cell floor, and every member still leaves only by
being placed or covered. This file is the mechanism that argument
constrains; read it there.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..core import ResourceKey
from .place_job import SUBDIVISION_REFUSALS
from .plans import child_window_plans
from .view import PlaneView

if TYPE_CHECKING:                                  # pragma: no cover
    from .place_sched import PlacementScheduler
    from .place_slot import Slot

#: THE EXITS THAT MEAN THE AREA WAS SERVED, as :func:`child_verdict`
#: reads them: this window carries a pose now, or its whole supported
#: extent certified through someone else's. Every other exit reason is a
#: refusal about the rectangle, which is what a parent's escalation
#: waits for all four of.
EXIT_SERVED = frozenset({"placed", "done_covered", "settled_placed"})


def subdivide(sched: "PlacementScheduler", view: PlaneView, slot: "Slot",
              outcome: str) -> None:
    """The ladder's last escalation: four corner windows, no spend.

    THE ACTION SPENDS NOTHING (R6-Q3): no pass, no budget, no durable
    write. It adds MEMBERS — the corner extents the carried kernel
    computes (``plans.child_window_plans``), admitted through the same
    door every window comes through, so a child is subject to the
    same three permanent refusals (no pixels, already placed, already
    done-covered) and gets the same admission peek at the poses
    standing around it.

    THE PREMIUM (2026-08-17 ruling): a child pays its parent's rung
    term PLUS ``place_tiers.CHILD_PREMIUM`` on every tier it will ever
    run — the cold pair included since the 2026-08-18 reversal — which
    under one global cost order is the exhaust-first property: no child's
    pass outranks a whole window's pass at the same rung and tier,
    anywhere on the sheet.

    AT MOST ONCE, even if a ping re-arms this window and its ladder
    refuses again: ``subdivided`` is what makes the growth one
    generation deep rather than merely usually so. An empty child
    list (the kernel refusing to halve below the 70-cell floor) still
    marks the slot, because the answer cannot change.

    WHEN IT FIRES IS v1'S ORDER (W4). A window that ran its ladder
    out is quartered by its COLD refusal, not by its wide one —
    v1's ``run_cold`` -> ``refuse_unplaced`` -> subdivide, restored
    now that cold exists (``PlacementScheduler.settle`` holds the
    branch). The two refusals that quarter a window on the spot are v1's
    other two call sites: a fit that never posed (``place.py:1244``,
    before any route runs) and an audit that refused an address the
    search had accepted (:1173). Neither of those windows has a
    correlation left to run — one has no patch, the other spent its
    address — so "everything cheaper has failed" is true of all three.

    A better lattice seed can still revive such a parent and place it
    whole; its children merely wait behind every whole window on the
    sheet, which is what the premium is for.
    """
    if slot.subdivided or outcome not in SUBDIVISION_REFUSALS:
        return
    slot.subdivided = True
    children = child_window_plans(
        slot.plan, view.region(slot.plan.region_id),
        depth=slot.depth, config=sched.config)
    if not children:
        return
    slot.children = tuple(plan.window_id for plan in children)
    sched._parents.append(slot.window_id)
    sched._counts["subdivided"] += 1
    for plan in children:
        if plan.window_id in sched._slots or plan.window_id in sched._exited:
            continue
        sched._consider(view, plan, slot.entry, slot.depth + 1,
                        lane_depth=slot.lane_depth)


def review_parents(sched: "PlacementScheduler") -> None:
    """What a child's exit means to the window that computed it.

    The ping and the parent's next pass, collapsed into one read. The
    ruled shape is: a child's exit (placed, covered, exhausted) pings
    the parent, the parent's pass checks its children's outcomes BY
    THEIR EXTENT-NAMED RECORDS, and when they have all failed the
    parent escalates itself to COLD — which runs on the parent's full
    extent, since correlation wants area.

    SINCE W4 THAT ESCALATION IS REAL, and RARE — which is what v1's
    restored order does to it. A window that exhausts its ladder
    correlates BEFORE it subdivides, so the ordinary parent is
    already armed (and usually already spent) by the time its
    children report, and this call finds nothing to do. What is left
    to it is the parent quartered by v1's :1173 site — an address
    accepted at the wide tier and refused by the straddle audit,
    which never reached a cold tier — and that parent gets its
    full-extent correlation here, after its corners have failed.
    Children now carry cold pairs of their own (the 2026-08-18
    reversal), so "all children failed" includes their colds.

    Outcomes are read here rather than pushed from below because the
    reference only ever points down: ``_parents`` is a list of
    windows that subdivided, and nothing anywhere names a parent.
    Normal runs subdivide nothing, so this loop is empty and free.
    """
    for parent_id in sched._parents:
        slot = sched._slots.get(parent_id)
        if slot is None or slot.cold_parked:
            continue              # gone (placed or covered): nothing to park
        verdicts = [child_verdict(sched, child) for child in slot.children]
        if any(verdict is None for verdict in verdicts):
            continue              # a child is still working
        if any(verdicts):
            continue              # a child served this area; the parent rests
        slot.cold_parked = True
        sched._counts["cold_parked"] += 1
        sched._arm_cold(slot)


def child_verdict(sched: "PlacementScheduler",
                  child_id: ResourceKey) -> bool | None:
    """Did this child SERVE its area — ``None`` while it is still trying.

    Three states, and the middle one is why DORMANCY counts as an
    exit here: a child that is neither ready nor in flight has
    finished as surely as one that retired — waiting for a set
    membership it will never give up would park no parent at all.
    Dormancy is the readiness bit and not the tier list: a child
    whose own fit refused sleeps with word tiers unspent, which is
    the commonest way a corner retry ends.

    A ping can still revive such a child, and if it then places, the
    parent is already parked at a tier that does nothing — waste,
    never wrongness.
    """
    reason = sched._exited.get(child_id)
    if reason is not None:
        return reason in EXIT_SERVED
    slot = sched._slots.get(child_id)
    if slot is None:
        return False              # never admissible: no pixels under it
    if slot.in_flight or slot.ready:
        return None
    return False


__all__ = ["EXIT_SERVED", "child_verdict", "review_parents", "subdivide"]

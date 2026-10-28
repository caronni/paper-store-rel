"""Supplemental-lane (u-lane) identity vocabulary — PK4.3.

RECEIVE-DESIGN §6.2a: an arm that cannot prove universal non-regression
is not gated — it is SCHEDULED, as its own lane after the standard
ladder, where the per-address retirement law (§6.3) makes it monotone by
construction.  The override such a lane runs is part of its IDENTITY and
of nothing else: it is spelled into the lane id, so a durable plan, a
resumed state, an event row and a diagnostics pane all read the same
fact from the same string, and no ambient flag can ever claim an
override the plan did not schedule.

This module is that vocabulary and its ONE parse.  It lives beside
``types`` rather than inside it for two reasons: the ≤1000-line rule,
and the fact that a lane id's grammar is worth its own documented home.
Nothing here imports anything: a lane identity is text, and every
consumer reads it through :class:`~holo.receive.types.LaneSpec`'s
derived ``uplift_of`` / ``arm_override`` accessors, never by parsing.

Lane id grammar::

    u<NN>-<arm>-<ppc>ppc-<dpi>dpi

``<NN>`` is the BASE ladder lane's own two-digit index, so the base lane
id is exactly the same string with ``l`` for ``u`` and the arm segment
removed — the plan needs no extra persisted field to say which ordinary
lane a supplemental lane serves, which is what keeps the durable state
shape (and therefore every archived state) unchanged.
"""
from __future__ import annotations

from typing import Final

UPLIFT_LANE_PREFIX: Final = "u"

#: The registered arm overrides, IN PLAN ORDER.  ``off`` = every
#: campaign arm disabled, i.e. the PRE-CAMPAIGN evidence path — the
#: supplemental BASELINE lane (PK5 lead ruling); ``a3`` = per-window
#: photometric maps; ``a4b`` = KnownField-conditioned marginalization
#: with its region comparison measured but not consulted; ``field`` =
#: the PLANE-FIELDS W3 arm (docs/PLANE-FIELDS.md §6.2, the lane the
#: workplan calls ``uF``) — the ordinary evidence ladder re-read over
#: committed poses with the per-plane delta field FORCED ON.  Since
#: PK-CLEAN these names are the ONLY way A3 and A4b run at all, and
#: since W3 ``field`` is the only way the plane-field dial reaches a
#: production decode: the standard ladder has no branch that reaches
#: any of them.  Adding a name here is a FORMAT-AXIS change: it changes
#: the durable plan of every color capture, so it needs a policy-token
#: bump, not just a code review.
#:
#: NOT every coding schedules every name.  A4b conditions a plane's
#: marginal on its certified SIBLING planes, so a single-stream coding
#: has nothing to condition on and its ``a4b`` lane is a measured
#: guaranteed zero (70 s wall / 144 s CPU on xerox c3-cmy7 for 0
#: certificates and not one ``color.conditioning.*`` key,
#: COLOR-UPLIFT-MEASUREMENTS §10.7).  ``field`` is dimensioned by
#: PLANES, not streams, so every colour coding schedules it — cmy7's
#: three planes ride one stream and its joint codec is the one a
#: desynced plane hurts most (PLANE-FIELDS §3c).  The per-coding filter
#: lives with the plan builder that applies it:
#: ``cascade.uplift_arms_for_codec``.
#:
#: ORDER IS LOAD-BEARING, twice.  ``off`` runs FIRST so the OLD
#: configuration's reachable set is completed before any forced arm
#: reads the residue: a ladder-configuration change re-times cascades
#: and can strand tiles the old path certified, and the old path's own
#: tail is schedulable by exactly the law that schedules an arm —
#: monotone under §6.3's per-address retirement, no gate and no floor.
#: The arm lanes then see the true residue rather than one the baseline
#: could still have taken.  ``field`` runs LAST because it CONSUMES what
#: the others mint: its strongest evidence tier is the certified-tile
#: probe (PLANE-FIELDS §3 tier (i)), so every certificate an earlier
#: lane or arm added is one more measurement in the field it builds —
#: the R2 round reading the accumulated frontier.
UPLIFT_ARMS: Final = ("off", "a3", "a4b", "field")


def uplift_lane_id(base_lane_id: str, arm: str) -> str:
    """The supplemental lane id serving ``base_lane_id`` with ``arm``."""
    if arm not in UPLIFT_ARMS:
        raise ValueError(f"unregistered uplift arm {arm!r}")
    if (not base_lane_id.startswith("l")
            or not base_lane_id[1:3].isdigit()
            or base_lane_id[3:4] != "-"):
        raise ValueError(
            "an uplift lane serves an ordinary ladder lane 'lNN-...'")
    return f"{UPLIFT_LANE_PREFIX}{base_lane_id[1:3]}-{arm}-{base_lane_id[4:]}"


def parse_uplift_lane_id(lane_id: str) -> tuple[str, str] | None:
    """``(base lane id, arm)`` for a u-lane id, else ``None``.

    Strict by construction: anything that is not exactly the minted
    shape is an ordinary lane id, so no historical, synthetic or test
    lane can acquire an arm override by accident.
    """
    if not lane_id.startswith(UPLIFT_LANE_PREFIX):
        return None
    body = lane_id[len(UPLIFT_LANE_PREFIX):]
    if len(body) < 3 or not body[:2].isdigit() or body[2] != "-":
        return None
    index, rest = body[:2], body[3:]
    for arm in UPLIFT_ARMS:
        if rest.startswith(f"{arm}-"):
            tail = rest[len(arm) + 1:]
            return (f"l{index}-{tail}", arm) if tail else None
    return None


__all__ = [
    "UPLIFT_ARMS", "UPLIFT_LANE_PREFIX",
    "parse_uplift_lane_id", "uplift_lane_id",
]

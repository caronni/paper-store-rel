"""The LIVE GENERATION of a window's evidence (F2a, ruling J2-3).

One rule, one derivation, two readers. When RF1 revises a window's pose
and the re-sample emits evidence at the revised geometry
(:mod:`holo2.solve.resample`), that window's tile carries TWO generations
of pieces: the parent pose's, sampled at the geometry the revision says
is wrong, and the live pose's, sampled at the one it proposes. This
module answers which of them a reader may use.

WHY THE RULE IS "NEWEST THAT HAS PIECES" AND NOT ``index.live_pose``
--------------------------------------------------------------------
v1's answer is lane separation: the R-level mints under its own lane id,
``payload_engine.py:181-182`` REFUSES evidence from another lane, and the
base lane's committed evidence on the superseded pose stands untouched in
its own namespace forever (``production_refine.py:29-36``). holo2 has no
lanes, so the same property is reproduced at the READ:

* a payload attempt freezes only pieces of the newest pose that HAS
  pieces, per (tile, window) — so a superseded read and a live read never
  meet in one freeze, and a stale geometry can never win a cell it no
  longer describes under F1's quality ranking;
* a ctx pool harvests the same reduction, so one physical label site is
  never pooled twice with two different marginals at half weight each.

``index.live_pose`` alone is the WRONG spelling and the ledger says so
(DIVERGENCE-LEDGER row 7, 2026-08-23): on the archived e029 and Xerox
states 4,392 / 4,117 pieces hang on a pose that is not its extent's live
one, because every revision there was committed with nothing to re-sample
through it. Reducing to the live pose would DELETE all of them. Reducing
to the newest pose that HAS pieces keeps them — it is the IDENTITY
wherever nothing has re-sampled — and starts biting on the exact commit
where the re-sample writes its first piece.

WHAT KEEPS "NEWEST" ANSWERABLE FROM ``live_poses`` ALONE
---------------------------------------------------------
An extent carries at most TWO generations, and that is enforced rather
than hoped: RF1 refuses to revise a pose that is itself a revision
(``refine.Reach.eligible``, the same 2026-08-23 package), so the poses of
a window are the placement's and at most one revision of it. With two
generations "the newest that has pieces" is exactly "the live pose if it
has pieces, else the other one", which :func:`live_generation` reads off
``StoreIndex.live_poses`` and the piece keys themselves — no commit
ordinal, no new durable field, no record-family version.

A THIRD generation would make this rule under-determined (a live pose
with no pieces sitting above a second generation that has some), which is
why the bar on chaining is stated HERE as well as at the guard: the two
are one design, and a future package that lifts the bar owes this module
a pose ordinal.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from ..core import ResourceKey
from .keys import (EVIDENCE_KEY_PARTS, KIND_EVIDENCE, KIND_POSE,
                   KIND_WINDOW, POSE_KEY_PARTS, WINDOW_KEY_PARTS)


def pose_of_evidence(key: ResourceKey) -> ResourceKey | None:
    """The POSE a piece was read through, or ``None`` — key arithmetic.

    §5.4 embeds the pose in the evidence key, so this is a slice. The
    shape guard is the one ``calibration.pool_of_evidence`` and
    :func:`window_of_evidence` make: a malformed key answers ``None``
    rather than minting a junk pose key nobody wrote.
    """
    if key.kind != KIND_EVIDENCE or len(key.parts) != EVIDENCE_KEY_PARTS:
        return None
    return ResourceKey(KIND_POSE,
                       key.parts[EVIDENCE_KEY_PARTS - POSE_KEY_PARTS:])


def window_of_evidence(key: ResourceKey) -> ResourceKey | None:
    """The WINDOW a piece's pose belongs to, or ``None`` — pure key
    arithmetic (§5.4 embeds the pose, the pose embeds the window). F1's
    supersede wake names each covering window's pose collection, and that
    is the only thing it needs to name it by.

    THE SHAPE GUARD MIRRORS ``calibration.pool_of_evidence`` (review fix,
    2026-08-23): the two functions read the SAME keys from the same
    source and must agree on what a well-formed one is. Slicing blind
    would mint a junk window key into the read-set — a subscription to a
    key nobody writes — where the sibling returns None and the caller
    skips.

    Moved here from ``payload`` at F2a (2026-08-23) so that the live
    generation and the wake read one derivation of "which window is this
    piece's"; ``payload.evidence_window`` is this name.
    """
    if key.kind != KIND_EVIDENCE or len(key.parts) != EVIDENCE_KEY_PARTS:
        return None
    return ResourceKey(KIND_WINDOW, key.parts[
        EVIDENCE_KEY_PARTS - POSE_KEY_PARTS:
        EVIDENCE_KEY_PARTS - POSE_KEY_PARTS + WINDOW_KEY_PARTS])


def window_of_pose(pose_id: ResourceKey) -> ResourceKey | None:
    """The WINDOW a pose key names, or ``None`` — pure key arithmetic.

    The pose-side sibling of :func:`window_of_evidence`, with the same
    shape guard and for the same reason: a caller that slices blind
    mints a window key nobody wrote. Added at the F2a review
    (2026-08-23) for ``ctx_apply.window_loss``, which has to reach an
    extent's OTHER generation from one piece's pose.
    """
    if key_is_pose(pose_id):
        return ResourceKey(KIND_WINDOW, pose_id.parts[:WINDOW_KEY_PARTS])
    return None


def key_is_pose(key: object) -> bool:
    """Is this a well-formed pose key? (a test double's string id is not.)"""
    return (isinstance(key, ResourceKey) and key.kind == KIND_POSE
            and len(key.parts) == POSE_KEY_PARTS)


def live_generation(live_poses: Mapping[ResourceKey, ResourceKey],
                    keys: Iterable[ResourceKey]
                    ) -> tuple[ResourceKey, ...]:
    """Drop every piece of a SUPERSEDED generation, order preserved.

    ``live_poses`` is ``StoreIndex.live_poses`` (window -> latest
    committed pose). For each window represented among ``keys``: if the
    window's live pose holds at least one of them, keep only that pose's;
    otherwise keep all of them, which is what nothing-has-re-sampled
    looks like and is the identity on every state written before F2a.

    Keys of an unparseable shape are kept untouched — this function
    reduces generations and adjudicates nothing else, and the readers
    that refuse a malformed key already do so on their own terms.
    """
    ordered = tuple(keys)
    winners: dict[ResourceKey, ResourceKey] = {}
    for key in ordered:
        window = window_of_evidence(key)
        if window is None:
            continue
        live = live_poses.get(window)
        if live is not None and pose_of_evidence(key) == live:
            winners[window] = live
    if not winners:
        return ordered
    keep: list[ResourceKey] = []
    for key in ordered:
        window = window_of_evidence(key)
        live = None if window is None else winners.get(window)
        if live is None or pose_of_evidence(key) == live:
            keep.append(key)
    return tuple(keep)


__all__ = ["key_is_pose", "live_generation", "pose_of_evidence",
           "window_of_evidence", "window_of_pose"]

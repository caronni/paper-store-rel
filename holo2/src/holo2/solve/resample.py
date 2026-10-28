"""THE RE-READ: one window's residue, re-sampled through its LIVE pose.

F2a, ruling J2-3 ("we implement v1", 2026-08-23). This is the half RF1
was missing. Through F1 an adopted pose revision changed NOTHING: the
record was committed, ``StoreIndex.live_pose`` started answering with it,
and every payload attempt went on decoding evidence sampled at the
geometry the revision says is wrong. A2 measured the consequence on both
real sheets — 269 / 272 windows carrying two poses, and for all of them
the count of evidence on the LIVE pose was exactly ZERO. ``refine.py``
said it in as many words: *"chaining a revision onto a revision would
need re-sampled evidence, and nothing in the tree emits any today."*
This module is what emits it.

WHAT v1 DOES, AND WHAT OF IT LIVES HERE
----------------------------------------
v1's R-level (``production_refine.py:187-330``) re-derives the base
lane's committed poses as payload-capable placements
(``place._committed_patch:714`` — *"acceptance already happened at the
base barrier, so no route re-scoring runs"*), re-samples the affected
regions at the refined poses
(``_payload_reuse.sample_refined_reusing_generation:112-330``), and runs
the full ordinary schedule over the delta in the R lane's own namespace.

Three of those four things are carried here, and the fourth is the pull
model's:

1. **No route re-scoring.** The pass does not consult, does not search,
   does not word-decode and does not refine. The live pose IS the
   address; the fire samples through it and nothing re-litigates it.
   The revision is a PROPOSAL and what proves or discards it is the
   ordinary payload rerun that follows (RULING I3), never this fire.
2. **Frozen geometry, moving pose.** v1 asserts that region, page,
   rot_k, page origin, window and the local and page CELL SETS are all
   unchanged and only the POSE may move (``_payload_reuse:225-247``).
   Here that is not asserted but CONSTRUCTED: the cell set is read back
   off the superseded generation's own pieces, so the re-read covers
   exactly the cells the parent covered, and the only thing that differs
   is the geometry they are read at.
3. **A fresh calibration, AND A REPLAYED REGION FIT.** v1 re-calibrates
   the re-sampled window (``_payload_reuse:311-322``); so does this, by
   handing the re-sampled placement to the ordinary
   ``place_shared.emit_placement``, which fits the window's PAVA on its
   format-known sites exactly as generation zero did. v1 then re-runs
   the region-coupled ctx arm over the full population
   (``_payload_reuse:322-328``, C4 §3.3(5)) — and so does this, through
   the pull model's own idiom rather than a call: the pieces this fire
   commits bump ``keys.region_evidence_collection_key``, which the ctx
   fit names in its read-set, so the pool refits over the LIVE
   generation at its own price. That key was ADDED AT THIS PACKAGE'S
   REVIEW (2026-08-23) and the omission was measured, not theoretical:
   0 of 4 pools on either real sheet had a fit that had seen a re-read's
   pieces, so the live pose published no held-out loss and F1's
   ownership key (ruling J2-1) fell back to pose-id order on exactly the
   windows this fire makes decode-authoritative.
4. **The schedule.** v1 runs scan -> union -> preclose -> retry150 over
   the delta itself. holo2 does not: the new pieces are NEW KEYS, so
   they move the payload attempt's read-set, the standing attempt goes
   stale at the wall's existing check, and the tile acts again at its
   turn — scan first, then that footing's BP-150 retry over the new
   baseline, priced like any other payload attempt. That is J1(a)'s
   pull-model idiom reproducing v1's EFFECT, and it is strictly tighter
   than v1's region granularity because the wake reaches tiles rather
   than regions.

WHAT THE OLD EVIDENCE DOES — v1'S ANSWER, REPRODUCED WITHOUT LANES
-------------------------------------------------------------------
Nothing is retracted, marked or deleted: the parent's pieces stay
committed at their own keys forever, exactly as v1's base lane keeps
them in its own namespace. What changes is who READS them —
:func:`holo2.solve.generation.live_generation`, applied in the payload
read-set and in the ctx pool, keeps per (tile, window) only the newest
pose that HAS pieces. So a superseded read and a live read never meet in
one freeze, and a stale geometry can never win a cell it no longer
describes under F1's quality ranking. THE ONE PLACE THIS IS NOT v1: v1's
two lanes both remain decodable and a certificate may still be minted
from the base lane's reading, where holo2 reads the live generation only.
That is the ledger's own ruled expression of J2-3 (DIVERGENCE-LEDGER
row 7; C4 §3.3(3)) and it is what the acceptance measures — a revision
that reads WORSE costs the tiles the parent's reading would have won,
which is why "zero regressions" is the bar and not a hope.

WHY IT IS A PLACEMENT TIER AND NOT A PROVIDER
----------------------------------------------
The subject is a WINDOW and the work is a window pass — sample, address,
emit — which is the placement source's whole vocabulary. A provider
family would need its own recipe entry, and a recipe entry rides
``SessionIdentity`` BY VALUE, so it would fork every archived state's
lineage and put the measurement out of reach. A tier costs nothing of
the sort: prices live in ``place_tiers`` and no state names them.

THE PRICE IS RF1'S OWN (``place_tiers.RESAMPLE_TIER``, 200). This fire
is RF1's other half — it exists only because a revision was adopted, and
a revision is priced at the top so it fires when nothing cheaper is
ready (RULING I2). Charging its consequence less would let a re-read
preempt the ladder that the revision itself waited for.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core import ProgressSink, ResourceKey, WorkResult
from ..format import TILE_CELLS, FormatRowSpec
from .keys import parse_window_key
from .place_model import PlacementConfig
from .place_shared import AcceptedPlacement, emit_placement
from .plans import WindowPlan
from .quarantine import is_quarantined
from .records import EvidenceObservation, unpack_observed_cells
from .refine_fit import local_segment, sample_at
from .reference import ReferenceFieldProvider
from .view import PlaneView

#: The pass's own outcome vocabulary. ``retire=True`` rides every one of
#: them: a re-read answers for ONE (window, live pose) and the scheduler
#: must not offer it again for the same geometry, whether it emitted or
#: refused. A LATER revision re-admits the window on its own merits
#: (``place_sched.PlacementScheduler.admit``).
OUTCOME_RESAMPLED = "resampled"
OUTCOME_PREFIX = "resample_refused_"


@dataclass(frozen=True)
class Superseded:
    """The generation this re-read replaces: its pose and its cells.

    ``cells`` are ABSOLUTE page cells in the sorted piece order, the same
    reconstruction ``refine.PoseRefineWorker._observed`` and
    ``calibration._member_cells`` make and for the same reason: pieces
    are per (tile, pose) and tiles are disjoint, so the union is
    duplicate-free.
    """

    pose_id: ResourceKey
    cells: np.ndarray


def superseded_generation(view: PlaneView, window_id: ResourceKey,
                          live: ResourceKey) -> Superseded | None:
    """The window's evidence-owning generation, off the index's own arrow.

    A pose does not index its pieces in the RECORDS (§5.4: the arrow runs
    the other way), but the index does — ``StoreIndex.evidence_by_pose``,
    widened from F2a's membership-only ``posed_evidence`` at this
    package's review (2026-08-23). So the grouping reaches the pieces of
    this window's own poses (``poses_by_window``, two of them at most)
    instead of walking the whole evidence index once per fire: on e029
    that walk was ~25,010 keys x 239 fires, and the door beside it was
    already O(1) on the same index.

    A CONDEMNED GENERATION IS NEVER RE-READ (the same review). W5's law
    is one-way — *"never rehabilitated: the transition is one-way and
    recovery is fresh-evidence-only (L8)"* — and a re-read of condemned
    pieces would launder them: it takes the cells the condemned pose
    addressed and emits FRESH, unquarantined pieces over them at the
    live pose. The filter is asked on both the pose and the piece
    because ``quarantine.quarantine_writes`` marks both, and this fire
    must not depend on which of the two a future writer marks first.

    ``None`` when the live pose already owns pieces (there is nothing to
    replace), when no generation owns any (a window whose emission
    refused), or when every generation that does is condemned. All three
    are ordinary, and all three make the fire a refusal rather than an
    error.
    """
    index = view.index()
    grouped: dict[ResourceKey, list[ResourceKey]] = {}
    for pose in index.poses_by_window.get(window_id, ()):
        if pose == live or is_quarantined(index.poses.get(pose)):
            continue
        keys = index.evidence_by_pose.get(pose, ())
        if keys:
            grouped[pose] = list(keys)
    if live in index.evidence_by_pose or not grouped:
        return None
    # At most two generations stand on an extent (``refine.Reach.revised``
    # bars a third), and the live one holds nothing here — so exactly one
    # candidate remains. Picking the largest rather than the only one is
    # the total spelling of that, not a policy.
    pose_id = max(grouped, key=lambda key: (len(grouped[key]), key))
    rows: list[np.ndarray] = []
    for key in sorted(grouped[pose_id]):
        observation = view.record(key)
        if not isinstance(observation, EvidenceObservation):
            continue
        if is_quarantined(observation):
            continue
        observed = unpack_observed_cells(
            view.read_array(observation.observed_ref),
            (TILE_CELLS, TILE_CELLS))
        ys, xs = np.nonzero(observed)
        rows.append(np.stack((ys + observation.ty * TILE_CELLS,
                              xs + observation.tx * TILE_CELLS),
                             axis=1).astype(np.int64))
    if not rows:
        return None
    return Superseded(pose_id, np.concatenate(rows))


def resample_window(view: PlaneView, *, plan: WindowPlan,
                    row: FormatRowSpec, reference: ReferenceFieldProvider,
                    config: PlacementConfig,
                    progress: ProgressSink) -> WorkResult:
    """Re-read one placed window's cells through its LIVE pose.

    The whole pass, and every refusal it can make, in the order the
    inputs are needed. Nothing here decides geometry; the live pose is
    read, sampled through, and handed to the ordinary emission block.
    """
    index = view.index()
    live_id = index.live_pose(plan.window_id)
    live = None if live_id is None else index.poses.get(live_id)
    if live_id is None or live is None:
        return WorkResult(outcome=OUTCOME_PREFIX + "no_live_pose",
                          retire=True)
    if is_quarantined(live):
        # W5's never-return, in this fire's voice: a condemned geometry
        # is never sampled through, ever again.
        return WorkResult(outcome=OUTCOME_PREFIX + "quarantined",
                          retire=True)
    progress.emit(1, "resample-arm")
    old = superseded_generation(view, plan.window_id, live_id)
    if old is None:
        return WorkResult(outcome=OUTCOME_PREFIX + "nothing_superseded",
                          retire=True)
    footing_id, region_id, _extent = parse_window_key(plan.window_id)
    if not view.has_region(region_id) or not view.has_footing_pixels(
            footing_id):
        return WorkResult(outcome=OUTCOME_PREFIX + "no_pixels", retire=True)
    prepared = view.prepared_region(view.region(region_id), config=config,
                                    footing_id=footing_id)
    frame = view.footing_frame(footing_id)
    if prepared is None or frame is None:
        return WorkResult(outcome=OUTCOME_PREFIX + "no_pixels", retire=True)
    # THE ONE ARITHMETIC. ``local_segment`` restates the durable
    # native-frame affine in the rung's own pixels and re-origins it at
    # the cell set's corner; ``sample_at`` is the SAME order-1 read
    # through the SAME single box aperture that generation zero's
    # ``pose_fit.sample_segment`` made. So the only difference between
    # these means and the committed ones is the geometry — which is the
    # experiment.
    segment, local = local_segment(live.native_affine, frame, old.cells)
    means = sample_at(prepared.filtered, (prepared.y0, prepared.x0),
                      prepared.backing, segment.pose, local)
    progress.emit(1, "resample-sampled")
    placement = _page_placement(live.page, tuple(live.native_affine),
                                old.cells, means)
    emission = emit_placement(view, row=row, plan=plan, pose=live,
                              placement=placement, provider=reference,
                              progress=progress)
    if not emission.accepted:
        return WorkResult(outcome=OUTCOME_PREFIX + emission.outcome,
                          retire=True)
    # THE POSE WRITE IS DROPPED, and only that one. ``emit_placement``
    # appends its pose unconditionally because its ordinary caller is
    # committing a NEW geometry; here the record already stands, byte
    # for byte, and re-proposing it would bump the key's version and the
    # window's pose collection — waking every reader of both for a write
    # that says nothing. F-07 is satisfied by the store (the pieces'
    # pose is committed), and the transition law would have accepted the
    # no-op anyway; this keeps the wake graph honest.
    writes = tuple(write for write in emission.writes
                   if write.key != live_id)
    return WorkResult(outcome=OUTCOME_RESAMPLED, retire=True,
                      writes=writes, blobs=emission.blobs)


def _page_placement(page: int, affine: tuple[float, ...],
                    cells: np.ndarray,
                    means: np.ndarray) -> AcceptedPlacement:
    """The re-sample, in the shape the emission block already reads.

    ``rot_k`` is 0 AND THAT IS EXACT, not a simplification. The emission
    block takes a placement in the SAMPLER's frame plus the rotation that
    lays it on the sheet, and immediately composes the two
    (``np.rot90(scores, rot_k)``, ``fragment_reference_sites(..., rot_k)``)
    — every downstream read is of the composition. This fire has the
    composition already: its cells ARE absolute page cells, because they
    were read back from pieces that are keyed by page tile. Declaring the
    identity rotation over page-oriented arrays hands the block exactly
    the arrays it would have computed, with no second convention to keep
    in step.

    The array spans the observed cells' bounding box rather than the
    window's full extent. That is not a narrowing: every cell outside it
    is unobserved, and both the tile slicing and the F1 halo read an
    unobserved cell and an out-of-array cell identically (absent), so
    the pieces and their context rings come out the same either way.

    ``sample=None`` is v1's rule, not a shortcut: *"committed poses never
    re-enter the firewall word pool"* (``place._committed_patch``). The
    W5 known-position reduce is a judgement about a placement being
    ACCEPTED, and this fire accepts nothing — it re-reads a geometry the
    tree already committed. The emission block reads that as an empty
    verdict (``quarantine.word_verdict``).
    """
    origin = cells.min(axis=0)
    shape = tuple(int(value) for value in (cells.max(axis=0) - origin + 1))
    local = cells - origin
    scores = np.zeros(shape, np.float64)
    observed = np.zeros(shape, bool)
    # Negated luma: larger means more ink, the polarity the monotone PAVA
    # map and the tile chain both require (``place_shared``'s own).
    scores[local[:, 0], local[:, 1]] = -np.asarray(means, np.float64)
    observed[local[:, 0], local[:, 1]] = True
    return AcceptedPlacement(
        page=page, rot_k=0,
        page_origin_yx=(int(origin[0]), int(origin[1])),
        scores=scores, observed=observed, affine=affine, sample=None)

__all__ = [
    "OUTCOME_PREFIX", "OUTCOME_RESAMPLED", "Superseded",
    "resample_window", "superseded_generation",
]

"""HOW A DECODE READS AN ADOPTED CTX FIT, AND APPLIES IT.

Carved out of ``calibration`` at F2a (2026-08-23), along the joint F1's
own hand-off named when that file reached 992 lines: *"the label harvest
+ the fit worker on one side, the assembly readers on the other"*. The
two sides answer different questions and are read by different families.
``calibration`` is the pool — who its members are, what labels they
publish, which fit is adopted and what a fit RECORDS. This module is what
a PAYLOAD decode does with one: find the adopted fit of a pool, read the
offsets and the per-window losses out of its params blob, bin a tile's
cells in their OWNER's window, and add the correction.

The dependency runs ONE WAY, this module on ``calibration`` and never
back — the same test the ``keys``/``families``/``place_tiers`` seams
passed. There is deliberately NO re-export: a caller names the module
whose question it is asking, which is what keeps the joint visible.

Nothing here writes. The correction is applied at DECODE ASSEMBLY and
never to the stored evidence, which is H5 P1's load-bearing design
sentence and the reason a piece's durable LLR is always the MARGINAL one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..core import ResourceKey
from . import detect
from .calibration import (CTX_BINS, PARAM_LENGTH, ctx_pool_key,
                          member_digest, pose_pool_scope, published_losses)
from .generation import window_of_pose
from .records import CalibrationRecord
from .view import PlaneView


@dataclass(frozen=True)
class AdoptedContextFit:
    """One pool's current adopted fit: its offsets and its window losses.

    Both halves of what a payload decode asks a pool for, read in ONE
    pass over ``context_fits`` — the offsets its component takes and, per
    member window, the held-out loss v1's ownership freeze ranks that
    window by (F1, ruling J2-1). They must come from the SAME record:
    ranking on one fit's losses while correcting with another's offsets
    would be neither tree's rule.
    """

    key: ResourceKey
    offsets: np.ndarray
    window_losses: dict[float, float]

    def loss_of(self, pose_id: ResourceKey) -> float | None:
        """This fit's held-out loss for one member window, if published."""
        return self.window_losses.get(member_digest(pose_id))


def adopted_context_fit(plane: PlaneView, pool: ResourceKey
                        ) -> AdoptedContextFit | None:
    """The CURRENT adopted fit of one pool.

    THE LIVE FIT WINS (F2a review fix, 2026-08-23; C4 §3.3(5): *"v1's
    answer is unambiguous — the CURRENT fit is the one just fitted"*).
    ``StoreIndex.live_context_fits`` is that fit, derived from COMMIT
    ORDER exactly as ``live_poses`` is; every other adopted fit of the
    pool ranks behind it under the older rule (largest search
    population, ties on the params content address).

    The older rule alone was not v1's and, after a re-read, was not even
    deterministic in effect: the live generation replaces a window's
    pieces ONE FOR ONE over the same cells, so the pre-re-read and
    post-re-read fits tie EXACTLY on search population and the winner
    was the higher content address. MEASURED on ``real/f2/e029``, pool
    ``d9c4e932b904:2/1``: two fits both at 69,828, one with 0 re-read
    members and one with 9, separated by nothing but a sha. Adopting the
    stale one publishes no window loss for the live pose, which is what
    F1's ownership key ranks by.

    The rank is a TUPLE and not a lookup so the reader stays total: a
    live fit whose params blob is malformed falls through to the same
    skip every other candidate takes, and the pool answers with the best
    of the rest rather than with nothing.

    TOTAL OVER WHATEVER THE STORE HOLDS (review fix, 2026-08-23). This is
    a decode-path reader, and before F1 it SKIPPED any params blob whose
    shape it did not expect. F1 made the blob self-describing by LENGTH,
    which is exactly the layer where a future writer change can go wrong,
    so a malformed tail is skipped here rather than raised through a
    decode. The refusal stays where it belongs — on the WRITE side, in
    ``_member_loss_params``, which already refuses a digest collision.
    """
    best: tuple[tuple[bool, float, str], AdoptedContextFit] | None = None
    index = plane.index()
    live = index.live_context_fits.get(pool)
    for key in index.context_fits.get(pool, ()):
        record = plane.record(key)
        if not isinstance(record, CalibrationRecord):
            continue
        params = np.asarray(plane.read_array(record.params_ref),
                            np.float64).ravel()
        if params.size < PARAM_LENGTH:
            continue
        try:
            losses = published_losses(params)
        except ValueError:
            continue
        rank = (key == live,
                float(params[CTX_BINS] + params[CTX_BINS + 1]),
                record.params_ref.sha256)
        if best is None or rank > best[0]:
            best = (rank, AdoptedContextFit(
                key, params[:CTX_BINS].copy(), losses))
    return None if best is None else best[1]


def window_loss(plane: PlaneView, fit: AdoptedContextFit | None,
                pose_id: ResourceKey) -> float | None:
    """The held-out loss F1 ranks this piece's window by — v1's statistic
    even on the turn a re-read has just taken (F2a review fix,
    2026-08-23).

    ``fit.loss_of(pose_id)`` is the answer whenever the pool has fitted
    over the generation that owns this piece. A re-read makes that
    momentarily untrue: it commits pieces at the LIVE pose, and the
    pool's re-fit — which the region evidence collection now arms
    (``keys.region_evidence_collection_key``) — is a separate fire at a
    separate price, so between the two commits the live pose has no
    published loss. ``payload._pieces`` reads a missing loss as
    ``inf``, and ``_freeze_with_owners`` sorts on it, so that window
    would lose EVERY contested cell to any published sibling: F1's
    ownership key (ruling J2-1) undone on exactly the windows the
    re-read makes decode-authoritative. MEASURED before the fix on a
    fresh both-pools-publishing decode: 0 of 6 re-read windows had a
    loss for their live pose, 6 of 6 had one for the parent.

    So a pose with no published loss falls back to the published loss of
    its EXTENT'S other generation. That is the same window, the same
    label population and the same 200x200 pixels — v1 re-fits before it
    decodes and never has to answer this, and the parent's loss is the
    statistic v1's answer converges to. Sorted and minimised over the
    siblings so the answer does not depend on ``poses_by_window``'s
    order; ``None`` (hence ``inf``) when no generation of the window
    published one, which is the pre-F1 behaviour whole.

    A pool that publishes NOTHING short-circuits on the first line: that
    is a refused fit or a pre-F1 state, where every piece takes ``inf``
    together and the pre-F1 pose-id order stands.
    """
    if fit is None or not fit.window_losses:
        return None
    own = fit.loss_of(pose_id)
    if own is not None:
        return own
    window = window_of_pose(pose_id)
    if window is None:
        return None
    siblings: list[float] = []
    for other in plane.index().poses_by_window.get(window, ()):
        if other == pose_id:
            continue
        loss = fit.loss_of(other)
        if loss is not None:
            siblings.append(loss)
    return min(siblings) if siblings else None


def adopted_context_offsets(plane: PlaneView, pool: ResourceKey
                            ) -> tuple[ResourceKey, np.ndarray] | None:
    """:func:`adopted_context_fit`'s offsets half, for callers with no
    ranking question to ask."""
    found = adopted_context_fit(plane, pool)
    return None if found is None else (found.key, found.offsets)


def window_context_bins(llr: np.ndarray, observed: np.ndarray,
                        halo: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """One piece's ctx bins at v1's WINDOW scope (ruling J2-2).

    ``halo`` is the piece's durable one-cell frame
    (``records.unpack_piece_halo``): presence and provisional ink for the
    ring just outside the tile, as the piece's own pose saw them. The
    tile's interior comes from the piece itself — its mask and
    ``marginal > 0`` — so the frame handed to the CARRIED kernel is
    exactly the neighbourhood v1's window-wide computation has at these
    cells, and the tile's border ring stops being structurally bin -1.

    A ring cell the pose never covered stays absent, so a cell at the
    WINDOW's own edge is still bin -1 — which is v1's answer too.
    """
    present, ink = halo
    frame_present = np.array(present, bool, copy=True)
    frame_ink = np.array(ink, bool, copy=True)
    frame_present[1:-1, 1:-1] = observed
    frame_ink[1:-1, 1:-1] = observed & (np.asarray(llr) > 0.0)
    ys, xs = np.nonzero(frame_present)
    cells = np.stack((ys, xs), axis=1).astype(np.int64)
    counts, valid = detect.context_neighbour_counts(
        cells, frame_ink[ys, xs])
    frame_bins = np.full(frame_present.shape, -1, np.int8)
    frame_bins[ys, xs] = detect.context_bins(counts, valid=valid)
    return np.where(observed, frame_bins[1:-1, 1:-1], np.int8(-1)
                    ).astype(np.int8)


def apply_component_context(
    llr: np.ndarray,
    observed: np.ndarray,
    corrections: Iterable[tuple[np.ndarray, np.ndarray]],
    bins: np.ndarray | None = None,
) -> np.ndarray:
    """The additive-logit correction on ONE assembled component tensor.

    ``corrections`` pairs a cell mask (which cells this fit governs — the
    cells owned by poses of the fit's own region) with the fit's nine
    offsets. The kernel is the carried
    ``detect.apply_context_offsets``, clamps and all, and a cell at bin
    −1 or outside every mask keeps its marginal LLR.

    WHERE THE BINS COME FROM (F1, ruling J2-2 "we implement v1"). v1
    corrects each 200x200 WINDOW before the ownership freeze, so a
    payload cell is binned in its own pose's window
    (``_payload_context.py:284-291``). ``bins`` is that array, assembled
    cell-by-cell from the OWNER's halo by
    ``payload.RealPayloadWorker._freeze_with_owners``. Passing ``None``
    falls back to deriving them from the assembled component, which is
    what holo2 did before F1 and what a piece written before F1 (no
    durable halo) still gets: correct, but with the tile's border ring
    structurally bin −1 — MEASURED 6.15% of cells against v1's 1.56%.

    With NO corrections the INPUT IS RETURNED UNCHANGED — the same
    object, no arithmetic — which is the null-correction identity the
    refused path's bit-for-bit claim rests on.
    """
    items = [(np.asarray(mask, bool), np.asarray(offsets, np.float64))
             for mask, offsets in corrections]
    if not items:
        return llr
    if bins is None:
        ys, xs = np.nonzero(observed)
        cells = np.stack((ys, xs), axis=1).astype(np.int64)
        counts, valid = detect.context_neighbour_counts(
            cells, llr[observed] > 0.0)
        bins = np.full(llr.shape, -1, np.int8)
        bins[observed] = detect.context_bins(counts, valid=valid)
    out = np.asarray(llr, np.float64)
    for mask, offsets in items:
        gated = np.where(mask, bins, np.int8(-1)).astype(np.int8)
        out = detect.apply_context_offsets(out, gated, offsets)
    return out


def component_corrections(
    plane: PlaneView, owners: dict[ResourceKey, np.ndarray],
    fits: dict[ResourceKey, AdoptedContextFit | None] | None = None,
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    """Each owner region's adopted correction over the cells it owns.

    ``owners`` maps a pose id to the cells that pose owns in the frozen
    component (``payload.RealPayloadWorker``'s freeze). Poses are grouped
    by their (footing, region) pool — the correction is footing-scoped,
    and a component's cells may be owned by poses of different regions
    (two scraps of one sheet addressing one tile) — and each pool with an
    adopted fit contributes one (mask, offsets) pair. Pools without one
    contribute nothing, so a component over refused-fit regions takes the
    empty tuple and :func:`apply_component_context` returns it untouched.

    ``fits`` is the caller's already-read pool -> fit map (F1: the freeze
    reads the same fits to rank owners, and a fit's params blob is now
    the pool's window losses as well as its offsets — reading it twice
    per attempt would be two blob passes for one answer). Omitting it
    reads them here, which is what every caller outside the payload
    worker does.
    """
    by_pool: dict[ResourceKey, np.ndarray] = {}
    for pose_id, mask in owners.items():
        scope = pose_pool_scope(pose_id)
        if scope is None:
            continue
        pool = ctx_pool_key(*scope)
        held = by_pool.get(pool)
        by_pool[pool] = mask if held is None else (held | mask)
    corrections: list[tuple[np.ndarray, np.ndarray]] = []
    for pool in sorted(by_pool):
        found = (adopted_context_fit(plane, pool) if fits is None
                 else fits.get(pool))
        if found is not None:
            corrections.append((by_pool[pool], found.offsets))
    return tuple(corrections)


__all__ = [
    "AdoptedContextFit", "adopted_context_fit",
    "adopted_context_offsets", "apply_component_context",
    "component_corrections", "window_context_bins", "window_loss",
]

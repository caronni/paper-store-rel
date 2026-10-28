"""The colour neighbourhood leaf: what a cell's neighbours ARE.

P2 / PK5's other half (RECEIVE-DESIGN §6.2a, arm A5).  ``color_context``
owns the ARM — which correction to fit, whether to adopt it, how to apply
it.  This module owns the two things that arm reads and that a later
channel model would keep verbatim when it replaces the arm:

* THE NEIGHBOURHOOD.  A cell's provisional per-plane ink, its
  8-neighbourhood counts across the whole region (cross-window correct,
  which K's per-window form is not), and K's nine ordered bins.
* THE MONOTONE PRIMITIVE.  K's generalized ordered-logit PAVA, taking a
  caller's weights and a direction, over K's own block solver
  (``detect._solve_offset``) — so this module defines no sigmoid either.

Separated because the boundary is real (a PSF/spread model would replace
the bins and keep the corrector, or replace the corrector and keep the
bins), and because the two together do not fit one ≤1000-line module —
the PK10 precedent for an arm's module set gaining a member, recorded.
"""
from __future__ import annotations

import numpy as np
from scipy.special import logsumexp

from ..core import channel
from .color_anchoring import _Rows
from .detect import (
    CTX_BIN_PRIOR,
    N_CONTEXT_BINS,
    _solve_offset,
    context_bins,
    context_neighbour_counts,
)


class NeighbourhoodError(ValueError):
    """A shape the neighbourhood leaf refuses to work with."""


# ---------------------------------------------------------------------
# Neighbourhood geometry: provisional ink -> per-plane 9-bin indices.
# ---------------------------------------------------------------------

def provisional_ink(evidence: np.ndarray, *, cmy8: bool) -> np.ndarray:
    """``(N, 3)`` provisional per-plane ink from one row's EMITTED evidence.

    K's rule (``_payload_context``: ``marginal > 0``) in the colour
    alphabet.  A cmy8 row already emits component LLRs; a cmy7 row emits
    six W-relative state logits, whose per-plane marginal is the
    equal-prior log ratio over the states that print that plane.  Neither
    is a decision — it is a neighbourhood descriptor, and the exact bits
    the KnownField knows overwrite it wherever it exists.
    """
    values = np.asarray(evidence, np.float64)
    if cmy8:
        if values.ndim != 2 or values.shape[1] != 3:
            raise NeighbourhoodError(
                "color neighbourhood: cmy8 evidence must be (N, 3)")
        return values > 0.0
    if values.ndim != 2 or values.shape[1] != 6:
        raise NeighbourhoodError(
            "color neighbourhood: cmy7 evidence must be (N, 6)")
    return plane_marginals(augment(values)) > 0.0


def augment(relative: np.ndarray) -> np.ndarray:
    """Prepend W's pinned zero logit to ``(N, S-1)`` relative scores."""
    return np.concatenate(
        (np.zeros((relative.shape[0], 1), np.float64), relative), axis=1)


def state_bits(n_states: int) -> np.ndarray:
    """``(S, 3)`` bool plane bits — cmy7 is cmy8 without the CMY state."""
    return channel.states_to_planes(
        np.arange(n_states, dtype=np.uint8)).astype(bool)


def plane_marginals(scores: np.ndarray) -> np.ndarray:
    """``(N, 3)`` equal-prior plane marginals from ``(N, S)`` state scores."""
    bits = state_bits(scores.shape[1])
    out = np.empty((scores.shape[0], 3), np.float64)
    for plane in range(3):
        one = bits[:, plane]
        out[:, plane] = (
            logsumexp(scores[:, one], axis=1)
            - logsumexp(scores[:, ~one], axis=1))
    return out


def region_context_bins(
    row_tuple: tuple[_Rows, ...],
    evidence_of,
    *,
    cmy8: bool,
) -> tuple[np.ndarray, ...]:
    """Per-row ``(N, 3)`` int8 context bins for one whole region.

    CROSS-WINDOW CORRECT, which K's per-window form is not: the ink map is
    built over the region's DEDUPLICATED page cells, so a cell on a window
    boundary counts the neighbours that live in the adjacent window
    instead of losing them to a crop edge.  Deduplication uses ownership's
    own canonical order (ascending patch id, first window wins), so the
    ink a shared cell contributes can never depend on iteration order.

    ``evidence_of(ordinal) -> (N, 3|6)`` is called once per row and its
    result is dropped immediately: a full-page region carries millions of
    cells and the float evidence for all of them at once is the largest
    array the colour path would ever hold.

    Cells whose 8-neighbourhood is not wholly present in the region are
    ``-1`` — K's "no valid context" code — and are never corrected.
    """
    cells: list[np.ndarray] = []
    ink: list[np.ndarray] = []
    order = sorted(range(len(row_tuple)),
                   key=lambda index: int(row_tuple[index].patch.patch_id))
    for ordinal in order:
        window = row_tuple[ordinal]
        page_cells = np.asarray(window.page_cells_yx, np.int64)
        values = provisional_ink(evidence_of(ordinal), cmy8=cmy8)
        if values.shape[0] != page_cells.shape[0]:
            raise NeighbourhoodError(
                "color neighbourhood: evidence rows do not match the window")
        known = np.asarray(window.known_component_mask, np.bool_)
        bits = np.asarray(window.known_component_bits, np.uint8) > 0
        # THE EXACT BITS WIN.  A known cell's plane ink is a fact
        # (furniture by format, payload by prior-barrier certificate), so
        # the detector's provisional reading of it is never used.
        cells.append(page_cells)
        ink.append(np.where(known, bits, values))
    stacked = np.concatenate(cells)
    stacked_ink = np.concatenate(ink)
    width = int(stacked[:, 1].max()) + 1
    keys = stacked[:, 0] * np.int64(width) + stacked[:, 1]
    unique, first, inverse = np.unique(
        keys, return_index=True, return_inverse=True)
    unique_cells = stacked[first]
    unique_ink = stacked_ink[first]
    bins = np.empty((unique.size, 3), np.int8)
    for plane in range(3):
        counts, valid = context_neighbour_counts(
            unique_cells, unique_ink[:, plane])
        bins[:, plane] = context_bins(counts, valid=valid)
    scattered = bins[inverse]
    out: list[np.ndarray] = []
    start = 0
    sizes = {ordinal: int(row_tuple[ordinal].page_cells_yx.shape[0])
             for ordinal in order}
    parts: dict[int, np.ndarray] = {}
    for ordinal in order:
        stop = start + sizes[ordinal]
        parts[ordinal] = np.ascontiguousarray(scattered[start:stop])
        start = stop
    for ordinal in range(len(row_tuple)):
        out.append(parts[ordinal])
    return tuple(out)


def stride_select(count: int, limit: int) -> np.ndarray:
    """Deterministic every-k-th selector; the identity below ``limit``."""
    if count <= limit:
        return np.arange(count)
    return np.linspace(0, count - 1, limit).astype(np.int64)


def one_versus_rest(scores: np.ndarray, column: int) -> np.ndarray:
    """``score_s - logsumexp(score_j != s)`` — the exact binary reduction.

    Shifting one softmax logit by δ changes that state's probability by
    exactly ``sigmoid(l + δ)``, so K's binary block solver is not an
    analogy here: it is the multinomial stationarity condition for δ,
    written in the variable it is linear in.
    """
    keep = np.ones(scores.shape[1], np.float64)
    keep[column] = 0.0
    return scores[:, column] - logsumexp(scores, b=keep, axis=1)


def ordered_offsets(
    logits: np.ndarray,
    labels: np.ndarray,
    weights: np.ndarray,
    bins: np.ndarray,
    *, non_increasing: bool,
) -> np.ndarray:
    """K's generalized ordered-logit PAVA, with weights and a direction.

    Structurally ``detect._ordered_context_offsets``: one clipped block
    optimum per bin (``detect._solve_offset``, the canonical sigmoid), and
    adjacent blocks pooled whenever the monotone constraint is violated.
    Two differences, both forced and both stated: the weights are the
    caller's (class-balanced, PK3's law) rather than K's site
    multiplicities, and the DIRECTION is a parameter, because a state
    without plane-k ink is under-evidenced by exactly the bleed that
    over-evidences one with it.  A non-decreasing curve is fitted by
    walking the bins in reverse — the same primitive, no second
    implementation.
    """
    order = (range(N_CONTEXT_BINS) if non_increasing
             else range(N_CONTEXT_BINS - 1, -1, -1))
    blocks: list[dict[str, object]] = []
    for bin_index in order:
        select = bins == bin_index
        block_logits = np.concatenate(
            (logits[select], np.array([0.0, 0.0])))
        block_labels = np.concatenate(
            (labels[select], np.array([False, True])))
        block_weights = np.concatenate(
            (weights[select], np.full(2, CTX_BIN_PRIOR, np.float64)))
        blocks.append({
            "bins": [bin_index], "llr": block_logits,
            "labels": block_labels, "weights": block_weights,
            "offset": _solve_offset(
                block_logits, block_labels, block_weights),
        })
        while (len(blocks) >= 2
               and float(blocks[-2]["offset"]) < float(blocks[-1]["offset"])):
            right = blocks.pop()
            left = blocks.pop()
            merged_logits = np.concatenate((left["llr"], right["llr"]))  # type: ignore[arg-type]
            merged_labels = np.concatenate(
                (left["labels"], right["labels"]))  # type: ignore[arg-type]
            merged_weights = np.concatenate(
                (left["weights"], right["weights"]))  # type: ignore[arg-type]
            blocks.append({
                "bins": list(left["bins"]) + list(right["bins"]),  # type: ignore[arg-type]
                "llr": merged_logits, "labels": merged_labels,
                "weights": merged_weights,
                "offset": _solve_offset(
                    merged_logits, merged_labels, merged_weights),
            })
    offsets = np.zeros(N_CONTEXT_BINS, np.float64)
    for block in blocks:
        offsets[np.asarray(block["bins"], np.int64)] = float(block["offset"])
    return offsets


def anchor_curve(
    offsets: np.ndarray,
    bins: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    """Subtract the curve's own weighted mean over its fit population.

    The identification condition: a curve carries SHAPE, never a level.
    Monotonicity survives a constant shift exactly.
    """
    total = float(np.sum(weights))
    if total <= 0.0:
        return offsets
    mean = float(np.sum(weights * offsets[bins]) / total)
    return offsets - mean


__all__ = [
    "NeighbourhoodError", "anchor_curve", "augment", "one_versus_rest",
    "ordered_offsets", "plane_marginals", "provisional_ink",
    "region_context_bins", "state_bits", "stride_select",
]

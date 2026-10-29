from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import ndimage
from scipy.special import logsumexp

from ..data import WindowRows
from ..format.tile_codec import cmy_soft_demap, states_to_planes
from ..lib.pava import (
    CTX_BIN_PRIOR,
    CTX_MIN_SEARCH,
    CTX_MIN_SEARCH_PER_CLASS,
    CTX_MIN_VALIDATION,
    CTX_MIN_VALIDATION_PER_CLASS,
    N_CONTEXT_BINS,
    _solve_offset,
    class_balanced_weights,
)
from .color_chain import CmyChain
from .color_model import (
    CMY_COLUMN_LABEL_BITS,
    DEGENERATE_LLR_CLIP,
    HEAD_GATE_SLACK,
    Cmy7Head,
    Cmy8Detector,
    QdaModel,
    cmy8_marginal_llrs,
    cmy_erase_streams,
    qda_log_scores,
)

#: Coordinate ascent, not one pass: shifting one state's logit
#: renormalizes every other state's probability, so the steps interact
#: and a single sweep lands short of the family's own optimum
#: (measured).  11-colour-planes-ctx.md:340-341.
CONTEXT_SWEEPS: int = 3
#: A loss that was never measured: negative, never NaN, so a skipped
#: leg can never read as a very good 0.0 and can never refuse an
#: adoption.  11-colour-planes-ctx.md:254-255.
CONTEXT_NLL_UNMEASURED: float = -1.0

#: The shipped variant is the per-(state, plane) MATRIX.  The per-plane
#: form K uses was measured head-to-head and RETIRED: one curve per
#: plane spends itself on the 83-84% word population and adopted in 0
#: of 17 lanes.  11-colour-planes-ctx.md:430-433.
CONTEXT_VARIANT_MATRIX: str = "matrix"
CONTEXT_VARIANT_OFF: str = "off"

REASON_ADOPTED: str = "adopted"
REASON_SEARCH_STARVED: str = "insufficient_search_support"
REASON_SEARCH_CLASS: str = "search_class_starved"
REASON_VALIDATION_STARVED: str = "insufficient_validation_support"
REASON_VALIDATION_CLASS: str = "validation_class_starved"
REASON_GATE_FAILED: str = "validation_gate_failed"
REASON_REGION_GATE: str = "region_gate_failed"
REASON_NO_CURVE: str = "no_curve_adopted"
REASON_NO_CELLS: str = "no_context_cells"


@dataclass(frozen=True)
class ContextConfig:
    variant: str = CONTEXT_VARIANT_MATRIX
    min_search: int = CTX_MIN_SEARCH
    min_search_per_class: int = CTX_MIN_SEARCH_PER_CLASS
    min_validation: int = CTX_MIN_VALIDATION
    min_validation_per_class: int = CTX_MIN_VALIDATION_PER_CLASS
    sweeps: int = CONTEXT_SWEEPS

    @property
    def enabled(self) -> bool:
        return self.variant != CONTEXT_VARIANT_OFF


@dataclass(frozen=True)
class ContextHead:
    offsets: np.ndarray
    applied: np.ndarray

    #: The padded tenth column is how bin -1 receives EXACTLY zero: a cell
    #: whose 8-neighbourhood is incomplete keeps uncorrected evidence.
    #: Reach is a property of the capture, never something to interpolate.
    #: 11-colour-planes-ctx.md:342-343.
    def apply_states(self, scores: np.ndarray,
                     bins: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, np.float64)
        index = np.asarray(bins).astype(np.int64)
        index = np.where(index < 0, N_CONTEXT_BINS, index)
        padded = np.concatenate(
            (self.offsets, np.zeros((*self.offsets.shape[:-1], 1))),
            axis=-1)
        delta = (padded[:, 0, index[:, 0]]
                 + padded[:, 1, index[:, 1]]
                 + padded[:, 2, index[:, 2]])
        return values + delta.T


@dataclass(frozen=True)
class ContextVerdict:
    head: ContextHead | None
    adopted: bool
    reason: str
    curves_adopted: int
    curves_total: int
    validation_logloss: float | None = None


#: A cmy lane's erased label streams and the L-infinity bound its
#: emission divides by -- what the context gate scores through.
@dataclass(frozen=True)
class StreamErasure:
    streams: tuple[int, ...]
    bound: float


@dataclass(frozen=True)
class Population:
    scores: np.ndarray
    states: np.ndarray
    bins: np.ndarray
    kinds: np.ndarray


#: Each score column's presence bits.  `states` is the alphabet the
#: columns stand for (a row's `state_ids`: cmy's W C M Y = 0, 1, 2, 4),
#: or a count for an alphabet 0..n-1 (cmy7, cmy8).
def state_bits(states: int | tuple[int, ...]) -> np.ndarray:
    if isinstance(states, int):
        return states_to_planes(
            np.arange(states, dtype=np.uint8)).astype(bool)
    return states_to_planes(np.asarray(states, np.uint8)).astype(bool)


def augment(relative: np.ndarray) -> np.ndarray:
    return np.concatenate(
        (np.zeros((relative.shape[0], 1), np.float64), relative), axis=1)


def plane_marginals(scores: np.ndarray,
                    state_ids: tuple[int, ...] | None = None) -> np.ndarray:
    bits = state_bits(scores.shape[1] if state_ids is None else state_ids)
    out = np.empty((scores.shape[0], 3), np.float64)
    for plane in range(3):
        one = bits[:, plane]
        out[:, plane] = (
            logsumexp(scores[:, one], axis=1)
            - logsumexp(scores[:, ~one], axis=1))
    return out


def provisional_ink(evidence: np.ndarray, cmy8: bool,
                    state_ids: tuple[int, ...] | None = None) -> np.ndarray:
    values = np.asarray(evidence, np.float64)
    if cmy8:
        return values > 0.0
    return plane_marginals(augment(values), state_ids) > 0.0


def context_neighbour_counts(
    page_cells_yx: np.ndarray,
    ink: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    cells = np.asarray(page_cells_yx, np.int64)
    if cells.shape[0] == 0:
        return np.zeros(0, np.int8), np.zeros(0, bool)
    lo = cells.min(axis=0)
    local = cells - lo
    shape = tuple((local.max(axis=0) + 1).astype(int))
    present = np.zeros(shape, np.uint8)
    ink_grid = np.zeros(shape, np.uint8)
    present[local[:, 0], local[:, 1]] = 1
    ink_grid[local[:, 0], local[:, 1]] = np.asarray(ink).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    neighbours_present = ndimage.convolve(
        present, kernel, mode="constant", cval=0)
    neighbours_ink = ndimage.convolve(
        ink_grid, kernel, mode="constant", cval=0)
    row_y, row_x = local[:, 0], local[:, 1]
    return (neighbours_ink[row_y, row_x].astype(np.int8),
            neighbours_present[row_y, row_x] == 8)


#: EXACT BITS WIN: where a cell is known (format furniture, or a
#: prior-barrier certificate) its ink comes from the known bits, never
#: from the detector.  Cells are deduplicated region-wide in ascending
#: patch order, so bins never depend on window iteration order.
def region_context_bins(
    rows: tuple[WindowRows, ...],
    evidence_of: Callable[[int], np.ndarray],
    cmy8: bool,
    state_ids: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, ...]:
    cells_list: list[np.ndarray] = []
    ink_list: list[np.ndarray] = []
    order = sorted(range(len(rows)),
                   key=lambda index: int(rows[index].patch_ordinal))
    for ordinal in order:
        window = rows[ordinal]
        page_cells = np.asarray(window.page_cells_yx, np.int64)
        values = provisional_ink(evidence_of(ordinal), cmy8, state_ids)
        known = np.asarray(window.known_component_mask, np.bool_)
        bits = np.asarray(window.known_component_bits, np.uint8) > 0
        cells_list.append(page_cells)
        ink_list.append(np.where(known, bits, values))
    stacked = np.concatenate(cells_list)
    stacked_ink = np.concatenate(ink_list)
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
        bins[:, plane] = np.where(valid, counts, np.int8(-1))
    scattered = bins[inverse]
    parts: dict[int, np.ndarray] = {}
    start = 0
    for ordinal in order:
        stop = start + int(rows[ordinal].page_cells_yx.shape[0])
        parts[ordinal] = np.ascontiguousarray(scattered[start:stop])
        start = stop
    return tuple(parts[ordinal] for ordinal in range(len(rows)))


def one_versus_rest(scores: np.ndarray, column: int) -> np.ndarray:
    keep = np.ones(scores.shape[1], np.float64)
    keep[column] = 0.0
    return scores[:, column] - logsumexp(scores, b=keep, axis=1)


#: Direction is a PARAMETER read off the state's plane bit, never
#: fitted: a state without plane-k ink is under-evidenced by exactly
#: the bleed that over-evidences one with it.  Non-decreasing is fitted
#: by walking the bins in reverse -- one primitive, not two.
def ordered_offsets(
    logits: np.ndarray,
    labels: np.ndarray,
    weights: np.ndarray,
    bins: np.ndarray,
    non_increasing: bool,
) -> np.ndarray:
    order = (range(N_CONTEXT_BINS) if non_increasing
             else range(N_CONTEXT_BINS - 1, -1, -1))
    blocks: list[tuple[list[int], np.ndarray, np.ndarray, np.ndarray,
                       float]] = []
    for bin_index in order:
        select = bins == bin_index
        block_logits = np.concatenate(
            (logits[select], np.array([0.0, 0.0])))
        block_labels = np.concatenate(
            (labels[select], np.array([False, True])))
        block_weights = np.concatenate(
            (weights[select], np.full(2, CTX_BIN_PRIOR, np.float64)))
        blocks.append((
            [bin_index], block_logits, block_labels, block_weights,
            _solve_offset(block_logits, block_labels, block_weights)))
        while len(blocks) >= 2 and blocks[-2][4] < blocks[-1][4]:
            right = blocks.pop()
            left = blocks.pop()
            merged_logits = np.concatenate((left[1], right[1]))
            merged_labels = np.concatenate((left[2], right[2]))
            merged_weights = np.concatenate((left[3], right[3]))
            blocks.append((
                left[0] + right[0], merged_logits, merged_labels,
                merged_weights,
                _solve_offset(merged_logits, merged_labels,
                              merged_weights)))
    offsets = np.zeros(N_CONTEXT_BINS, np.float64)
    for block in blocks:
        offsets[np.asarray(block[0], np.int64)] = float(block[4])
    return offsets


#: The identification condition: a curve carries SHAPE, never a level.
#: An unanchored curve re-priors the detector, which is the head's job;
#: a constant shift preserves monotonicity exactly.
def anchor_curve(
    offsets: np.ndarray,
    bins: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    total = float(np.sum(weights))
    if total <= 0.0:
        return offsets
    mean = float(np.sum(weights * offsets[bins]) / total)
    return offsets - mean


def validation_floor_refusal(search: np.ndarray,
                             config: ContextConfig) -> str:
    if int(np.count_nonzero(~np.asarray(search, np.bool_))) < (
            config.min_validation):
        return REASON_VALIDATION_STARVED
    return ""


def label_floor_refusal(search: np.ndarray, config: ContextConfig) -> str:
    if int(np.count_nonzero(search)) < config.min_search:
        return REASON_SEARCH_STARVED
    return validation_floor_refusal(search, config)


def _binary_nll(llrs: np.ndarray, labels: np.ndarray) -> np.ndarray:
    sign = np.where(np.asarray(labels, np.int64) > 0, 1.0, -1.0)
    return np.logaddexp(0.0, -sign * np.asarray(llrs, np.float64))


def _multinomial_nll(scores: np.ndarray, states: np.ndarray) -> np.ndarray:
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    return -normalized[np.arange(states.size), states]


def _balanced_mean(losses: np.ndarray, labels: np.ndarray) -> float:
    if losses.size == 0:
        return CONTEXT_NLL_UNMEASURED
    weights = class_balanced_weights(np.asarray(labels, np.int64))
    return float(np.sum(weights * losses) / np.sum(weights))


def _not_worse(candidate: float, incumbent: float) -> bool:
    if (candidate == CONTEXT_NLL_UNMEASURED
            or incumbent == CONTEXT_NLL_UNMEASURED):
        return True
    return candidate <= incumbent + HEAD_GATE_SLACK


#: cmy8's emission path reached from context-corrected STATE scores:
#: marginal, degenerate clip, erasure, per-plane PAVA -- the same steps
#: the detector takes, so nothing is re-derived from features the
#: correction has already left behind.
def emitted_llrs(detector: Cmy8Detector, scores: np.ndarray) -> np.ndarray:
    raw = cmy8_marginal_llrs(scores)
    supported = detector.supported_planes
    out = np.empty_like(raw)
    for plane in range(3):
        if not supported[plane]:
            out[:, plane] = 0.0
            continue
        values = raw[:, plane]
        if detector.qda.degenerate or plane in detector.qda.clipped_planes:
            values = np.clip(
                values, -DEGENERATE_LLR_CLIP, DEGENERATE_LLR_CLIP)
        out[:, plane] = detector.calibrations[plane].llrs(values)
    return out


#: cmy7's and cmy's emission from post-head W-relative scores, in the
#: order `color_region_head.evidence_with_divisor` is law for: the
#: context matrix, the stream erasure, the L-infinity bound LAST.  The
#: emission and the context gate under erasure both call it, so the gate
#: scores what the decoder receives (the 2026-10-12 implementation
#: review, F3).
def relative_emission(
    scores: np.ndarray,
    context: ContextHead | None,
    bins: np.ndarray | None,
    erased: tuple[int, ...],
    bound: float,
) -> tuple[np.ndarray, np.ndarray]:
    if context is not None and bins is not None:
        scores = context.apply_states(scores, bins)
    if erased:
        scores = cmy_erase_streams(scores, erased)
    divisor = np.maximum(
        1.0, np.max(np.abs(scores), axis=1, keepdims=True) / bound)
    return scores / divisor, divisor


#: Under erasure the decoder never sees the erased stream, so standing
#: evidence and candidate are scored on the SURVIVING streams' binary
#: log-loss of the emitted scores: a four-state loss there can reward a
#: head that sharpens the discarded stream while reversing the surviving
#: one (F3).  Both streams erased: nothing is measured, nothing adopts.
def _surviving_losses(
    population: Population,
    head: ContextHead | None,
    erasure: StreamErasure,
) -> tuple[float, float, float]:
    emitted, _divisor = relative_emission(
        population.scores[:, 1:], head, population.bins, erasure.streams,
        erasure.bound)
    bits = CMY_COLUMN_LABEL_BITS[population.states]
    surviving = [stream for stream in range(bits.shape[1])
                 if stream not in erasure.streams]
    if not surviving:
        return (CONTEXT_NLL_UNMEASURED,) * 3
    loss = np.concatenate([
        _binary_nll(cmy_soft_demap(emitted, stream), bits[:, stream])
        for stream in surviving])
    truth = np.concatenate([bits[:, stream] for stream in surviving])
    kind = np.tile(population.kinds, len(surviving))
    return (
        _balanced_mean(loss, truth),
        _balanced_mean(loss[kind == 0], truth[kind == 0]),
        _balanced_mean(loss[kind == 1], truth[kind == 1]),
    )


def _region_losses(
    detector: Cmy8Detector | None,
    population: Population,
    head: ContextHead | None,
    cmy8: bool,
    erasure: StreamErasure | None = None,
) -> tuple[float, float, float]:
    if erasure is not None and not cmy8:
        return _surviving_losses(population, head, erasure)
    scores = population.scores
    kinds = population.kinds
    if head is not None:
        scores = (
            augment(head.apply_states(scores[:, 1:], population.bins))
            if not cmy8
            else head.apply_states(scores, population.bins))
    if cmy8 and detector is not None:
        values = emitted_llrs(detector, scores)
        bits = state_bits(8)[population.states].astype(np.uint8)
        supported = detector.supported_planes
        losses: list[np.ndarray] = []
        truths: list[np.ndarray] = []
        legs: list[np.ndarray] = []
        for plane in range(3):
            if not supported[plane]:
                continue
            losses.append(_binary_nll(values[:, plane], bits[:, plane]))
            truths.append(bits[:, plane])
            legs.append(kinds)
        if not losses:
            return (CONTEXT_NLL_UNMEASURED,) * 3
        loss = np.concatenate(losses)
        truth = np.concatenate(truths)
        kind = np.concatenate(legs)
        return (
            _balanced_mean(loss, truth),
            _balanced_mean(loss[kind == 0], truth[kind == 0]),
            _balanced_mean(loss[kind == 1], truth[kind == 1]),
        )
    loss = _multinomial_nll(scores, population.states)
    return (
        _balanced_mean(loss, population.states),
        _balanced_mean(loss[kinds == 0], population.states[kinds == 0]),
        _balanced_mean(loss[kinds == 1], population.states[kinds == 1]),
    )


def _fit_one_curve(
    running_search: np.ndarray,
    running_validation: np.ndarray,
    logit_cache: list[np.ndarray | None],
    search: Population,
    validation: Population,
    search_weights: np.ndarray,
    validation_weights: np.ndarray,
    state: int,
    plane: int,
    prints_plane: bool,
    config: ContextConfig,
) -> tuple[np.ndarray | None, str]:
    rows = np.flatnonzero(search.bins[:, plane] >= 0)
    validation_rows = np.flatnonzero(validation.bins[:, plane] >= 0)
    positives = int(np.count_nonzero(search.states[rows] == state))
    validation_positives = int(
        np.count_nonzero(validation.states[validation_rows] == state))
    if rows.size < config.min_search:
        return None, REASON_SEARCH_STARVED
    if min(positives, int(rows.size) - positives) < (
            config.min_search_per_class):
        return None, REASON_SEARCH_CLASS
    if validation_rows.size < config.min_validation:
        return None, REASON_VALIDATION_STARVED
    if min(validation_positives,
           int(validation_rows.size) - validation_positives) < (
               config.min_validation_per_class):
        return None, REASON_VALIDATION_CLASS
    labels = search.states[rows] == state
    if logit_cache[0] is None:
        logit_cache[0] = one_versus_rest(running_search, state)
    logits = logit_cache[0][rows]
    weights = search_weights[rows]
    bins = search.bins[rows, plane].astype(np.int64)
    curve = anchor_curve(
        ordered_offsets(logits, labels, weights, bins, prints_plane),
        bins, weights)
    if logit_cache[1] is None:
        logit_cache[1] = one_versus_rest(running_validation, state)
    gate_logits = logit_cache[1][validation_rows]
    gate_labels = validation.states[validation_rows] == state
    gate_bins = validation.bins[validation_rows, plane].astype(np.int64)
    gate_weights = validation_weights[validation_rows]
    incumbent = float(np.sum(
        gate_weights * _binary_nll(gate_logits, gate_labels))
        / np.sum(gate_weights))
    candidate = float(np.sum(
        gate_weights * _binary_nll(gate_logits + curve[gate_bins],
                                   gate_labels))
        / np.sum(gate_weights))
    if not candidate + HEAD_GATE_SLACK < incumbent:
        return None, REASON_GATE_FAILED
    return curve, REASON_ADOPTED


def _fit_matrix_curves(
    search: Population,
    validation: Population,
    config: ContextConfig,
    pinned_reference: bool,
    state_ids: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, dict[tuple[int, int], str]]:
    n_states = search.scores.shape[1]
    bits = state_bits(n_states if state_ids is None else state_ids)
    columns = range(1, n_states) if pinned_reference else range(n_states)
    width = n_states - 1 if pinned_reference else n_states
    offsets = np.zeros((width, 3, N_CONTEXT_BINS), np.float64)
    running_search = np.array(search.scores, np.float64, copy=True)
    running_validation = np.array(validation.scores, np.float64, copy=True)
    search_weights = class_balanced_weights(search.states)
    validation_weights = class_balanced_weights(validation.states)
    records: dict[tuple[int, int], str] = {}
    for _sweep in range(config.sweeps):
        moved = False
        for state in columns:
            target = state - 1 if pinned_reference else state
            logit_cache: list[np.ndarray | None] = [None, None]
            for plane in range(3):
                curve, reason = _fit_one_curve(
                    running_search, running_validation, logit_cache,
                    search, validation, search_weights, validation_weights,
                    state, plane, bool(bits[state, plane]), config)
                if curve is None:
                    # setdefault, not assignment: a later sweep may refuse a
                    # curve an earlier sweep adopted, and the adopted offsets
                    # stay in the head.  Only a curve that never adopted
                    # records a refusal.
                    records.setdefault((state, plane), reason)
                    continue
                records[(state, plane)] = reason
                moved = True
                offsets[target, plane] += curve
                valid_search = search.bins[:, plane] >= 0
                valid_validation = validation.bins[:, plane] >= 0
                running_search[valid_search, state] += curve[
                    search.bins[valid_search, plane]]
                running_validation[valid_validation, state] += curve[
                    validation.bins[valid_validation, plane]]
                logit_cache[0] = None
                logit_cache[1] = None
        if not moved:
            break
    return offsets, records


def locus_scores(model: QdaModel, head: Cmy7Head | CmyChain | None,
                 known_features: np.ndarray, cmy8: bool) -> np.ndarray:
    """The score locus the context matrix corrects: cmy8 state scores,
    cmy7's and cmy's W-relative scores through the head slot (cmy7's
    affine head, cmy's chain), W pinned at 0."""
    scores = qda_log_scores(model, known_features)
    if cmy8:
        return scores
    relative = scores[:, 1:] - scores[:, :1]
    return augment(relative if head is None else head.apply(relative))


def population(scores: np.ndarray, states: np.ndarray, bins: np.ndarray,
               kinds: np.ndarray, rows: np.ndarray) -> Population:
    return Population(np.asarray(scores, np.float64)[rows],
                      np.asarray(states, np.int64)[rows],
                      np.asarray(bins, np.int8)[rows],
                      np.asarray(kinds, np.int8)[rows])


def improves_region(detector: Cmy8Detector | None,
                    validation: Population,
                    incumbent: ContextHead | None,
                    candidate: ContextHead,
                    cmy8: bool,
                    erasure: StreamErasure | None = None,
                    ) -> tuple[bool, float]:
    """The three-way region gate: total strictly better, neither
    furniture leg worse. Returns the verdict and the candidate total."""
    standing = _region_losses(detector, validation, incumbent, cmy8,
                              erasure)
    proposed = _region_losses(detector, validation, candidate, cmy8,
                              erasure)
    passed = (
        proposed[0] + HEAD_GATE_SLACK < standing[0]
        and _not_worse(proposed[1], standing[1])
        and _not_worse(proposed[2], standing[2])
    )
    return passed, proposed[0]


def mask_unsupported(head: ContextHead,
                     supported: tuple[bool, bool, bool]) -> ContextHead:
    if all(supported):
        return head
    offsets = np.array(head.offsets, np.float64, copy=True)
    applied = np.array(head.applied, np.bool_, copy=True)
    for plane in range(3):
        if supported[plane]:
            continue
        offsets[:, plane] = 0.0
        applied[:, plane] = False
    return ContextHead(offsets, applied)


def context_verdict(
    search_population: Population,
    validation_population: Population,
    config: ContextConfig,
    cmy8: bool,
    supported: tuple[bool, bool, bool],
    detector: Cmy8Detector | None,
    state_ids: tuple[int, ...] | None = None,
    erasure: StreamErasure | None = None,
) -> ContextVerdict:
    pinned = not cmy8
    offsets, records = _fit_matrix_curves(
        search_population, validation_population, config,
        pinned_reference=pinned, state_ids=state_ids)
    head_applied = np.zeros(offsets.shape[:2], np.bool_)
    for (state, plane), reason in records.items():
        if reason != REASON_ADOPTED:
            continue
        target = state - 1 if pinned else state
        head_applied[target, plane] = True
    if cmy8:
        for plane in range(3):
            if supported[plane]:
                continue
            offsets[:, plane] = 0.0
            head_applied[:, plane] = False
    if not np.any(head_applied):
        return ContextVerdict(None, False, REASON_NO_CURVE, 0,
                              len(records))
    head_candidate = ContextHead(offsets, head_applied)
    passed, candidate_loss = improves_region(
        detector, validation_population, None, head_candidate, cmy8,
        erasure)
    n_adopted = int(np.count_nonzero(head_applied))
    if not passed:
        return ContextVerdict(None, False, REASON_REGION_GATE, n_adopted,
                              len(records), candidate_loss)
    return ContextVerdict(head_candidate, True, REASON_ADOPTED, n_adopted,
                          len(records), candidate_loss)


def fit_region_context(
    model: QdaModel,
    detector: Cmy8Detector | None,
    head: Cmy7Head | CmyChain | None,
    known_features: np.ndarray,
    known_bins: np.ndarray,
    states: np.ndarray,
    kinds: np.ndarray,
    search: np.ndarray,
    config: ContextConfig,
    state_ids: tuple[int, ...] | None = None,
) -> ContextVerdict:
    cmy8 = detector is not None
    starved = label_floor_refusal(search, config)
    if starved:
        return ContextVerdict(None, False, starved, 0, 0)
    if not np.any(np.asarray(known_bins) >= 0):
        return ContextVerdict(None, False, REASON_NO_CELLS, 0, 0)
    scores = locus_scores(model, head, known_features, cmy8)
    supported = (
        detector.supported_planes if detector is not None
        else (True, True, True))
    return context_verdict(
        population(scores, states, known_bins, kinds, search),
        population(scores, states, known_bins, kinds, ~search),
        config, cmy8, supported, detector, state_ids)

"""E023b per-region context fitting over calibrated payload windows.

This private module owns ``apply_region_context`` and its decision
records: the region-coupled 16-context arm, its held-out adoption gate,
the physical-cell id pooling, and the exact sidecar accounting for
partial/empty populations.  Split from ``_payload_windows.py`` in the
Phase 4 hammer batch (RECEIVE-DESIGN v0.38) together with
:mod:`_payload_sampling` and :mod:`_payload_reuse`.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import numpy as np

from . import detect
from .tiles import sha256_parts_le
from .payload_model import (
    CONTEXT_PROFILE,
    ContextDecision,
    WindowEvidence,
)


def _array_bytes(value: np.ndarray, dtype: str) -> bytes:
    return np.ascontiguousarray(value, dtype=np.dtype(dtype)).tobytes()


def _empty_context_decision(region_id: str, reason: str) -> ContextDecision:
    identity = sha256_parts_le(
        b"e023b/context-decision/v1", region_id.encode("utf-8"),
        reason.encode("utf-8"))
    zeros_f = np.zeros(detect.N_CONTEXT_BINS, np.float64)
    zeros_i = np.zeros(detect.N_CONTEXT_BINS, np.int64)
    return ContextDecision(
        identity, region_id, False, False, reason, zeros_f,
        zeros_f, zeros_f, zeros_i, zeros_i,
        0, 0, 0, 0, 0, 0, 0, 0, None, None)


def _context_record(region_id: str, fit: detect.ContextFit) -> ContextDecision:
    identity = sha256_parts_le(
        b"e023b/context-decision/v1", region_id.encode("utf-8"),
        fit.reason.encode("utf-8"), _array_bytes(fit.offsets, "<f8"),
        repr((fit.baseline_validation_logloss,
              fit.candidate_validation_logloss)).encode("ascii"))
    return ContextDecision(
        identity, region_id, fit.eligible, fit.adopted, fit.reason,
        fit.offsets, fit.search_support_by_bin,
        fit.validation_support_by_bin, fit.search_observations_by_bin,
        fit.validation_observations_by_bin, fit.n_search,
        fit.n_search_0, fit.n_search_1, fit.n_search_observations,
        fit.n_validation, fit.n_validation_0, fit.n_validation_1,
        fit.n_validation_observations, fit.baseline_validation_logloss,
        fit.candidate_validation_logloss)


def _binary_logloss(llr: np.ndarray, labels: np.ndarray,
                    weights: np.ndarray | None = None) -> float:
    x = np.asarray(llr, np.float64)
    y = np.asarray(labels, np.float64)
    losses = np.logaddexp(0.0, x) - y * x
    if weights is None:
        return float(np.mean(losses))
    w = np.asarray(weights, np.float64)
    return float(np.sum(w * losses) / np.sum(w))


def _partial_context_decision(
    region_id: str,
    search_parts: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    validation_parts: list[
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
) -> ContextDecision:
    """Exact sidecar accounting when one context population is empty."""
    def side(parts: list[tuple[np.ndarray, np.ndarray, np.ndarray,
                               np.ndarray]]) -> tuple[np.ndarray, np.ndarray,
                                                      int, int, int]:
        if not parts:
            return (np.zeros(detect.N_CONTEXT_BINS, np.float64),
                    np.zeros(detect.N_CONTEXT_BINS, np.int64), 0, 0, 0)
        counts = np.concatenate([np.asarray(row[1], np.int64) for row in parts])
        labels = np.concatenate([np.asarray(row[2], np.uint8) for row in parts])
        ids = np.concatenate([np.asarray(row[3], np.int64) for row in parts])
        unique, first, inverse, multiplicity = np.unique(
            ids, return_index=True, return_inverse=True, return_counts=True)
        del unique
        unique_labels = labels[first]
        n1 = int(unique_labels.sum())
        weights = 1.0 / multiplicity[inverse].astype(np.float64)
        support = np.bincount(
            counts, weights=weights, minlength=detect.N_CONTEXT_BINS
        )[:detect.N_CONTEXT_BINS]
        observations = np.bincount(
            counts, minlength=detect.N_CONTEXT_BINS
        )[:detect.N_CONTEXT_BINS]
        return support, observations, int(first.size - n1), n1, int(labels.size)

    ss, so, s0, s1, sn = side(search_parts)
    vs, vo, v0, v1, vn = side(validation_parts)
    if s0 + s1 < detect.CTX_MIN_SEARCH:
        reason = "insufficient_search_support"
    elif min(s0, s1) < detect.CTX_MIN_SEARCH_PER_CLASS:
        reason = "search_class_starved"
    elif v0 + v1 < detect.CTX_MIN_VALIDATION:
        reason = "insufficient_validation_support"
    else:
        reason = "validation_class_starved"
    identity = sha256_parts_le(
        b"e023b/context-decision/v1", region_id.encode("utf-8"),
        reason.encode("utf-8"))
    return ContextDecision(
        identity, region_id, False, False, reason,
        np.zeros(detect.N_CONTEXT_BINS), ss, vs, so, vo,
        s0 + s1, s0, s1, sn, v0 + v1, v0, v1, vn, None, None)


def _physical_cell_ids(
    rows: tuple[WindowEvidence, ...],
) -> tuple[np.ndarray, ...]:
    """Dense lexicographic ``(page, y, x)`` ids for one region's rows.

    Exact ``np.unique``/``searchsorted`` replacement for the historical
    per-cell tuple/dict enumeration (payload-windows:05): strided int64
    keys order exactly like lexicographic tuples once each axis is offset
    to zero; the tuple enumeration survives as the overflow fallback.
    """
    if not rows:
        return ()
    pages = np.concatenate([
        np.full(row.page_cells_yx.shape[0], row.page, np.int64)
        for row in rows])
    cells = np.concatenate([
        np.asarray(row.page_cells_yx, np.int64) for row in rows])
    if pages.size == 0:
        return tuple(np.zeros(0, np.int64) for _row in rows)
    page_low = int(pages.min())
    y_low = int(cells[:, 0].min())
    x_low = int(cells[:, 1].min())
    range_y = int(cells[:, 0].max()) - y_low + 1
    range_x = int(cells[:, 1].max()) - x_low + 1
    if ((int(pages.max()) - page_low + 1) * range_y * range_x
            <= np.iinfo(np.int64).max):
        keys = (
            ((pages - page_low) * range_y + (cells[:, 0] - y_low))
            * range_x + (cells[:, 1] - x_low)
        )
        ids = np.searchsorted(np.unique(keys), keys).astype(
            np.int64, copy=False)
    else:  # pragma: no cover — beyond any addressable page geometry
        lookup = {key: value for value, key in enumerate(sorted({
            (int(page), int(cell[0]), int(cell[1]))
            for page, cell in zip(pages.tolist(), cells)}))}
        ids = np.asarray([
            lookup[(int(page), int(cell[0]), int(cell[1]))]
            for page, cell in zip(pages.tolist(), cells)], np.int64)
    stops = np.cumsum([row.page_cells_yx.shape[0] for row in rows])
    starts = np.concatenate((np.asarray([0]), stops[:-1]))
    return tuple(
        ids[int(start):int(stop)]
        for start, stop in zip(starts, stops, strict=True))


def apply_region_context(
    windows: Iterable[WindowEvidence],
    label_windows: Iterable[WindowEvidence] = (),
) -> tuple[tuple[WindowEvidence, ...], tuple[ContextDecision, ...]]:
    """Apply/gate the exact E023b context arm independently per region.

    v0.33 D7: ``label_windows`` join their region's FIT populations (the
    pooled search/validation calibration evidence) but are never profiled,
    returned, or owner-eligible — they restore the single-pass pooled
    label population for a region whose windows split across a phase-1
    pass and its mop-up level.
    """
    baseline = tuple(windows)
    label_rows_all = tuple(label_windows)
    by_region: dict[str, list[int]] = {}
    for index, row in enumerate(baseline):
        by_region.setdefault(row.region_id, []).append(index)
    labels_by_region: dict[str, list[WindowEvidence]] = {}
    for row in label_rows_all:
        labels_by_region.setdefault(row.region_id, []).append(row)
    selected = list(baseline)
    decisions: list[ContextDecision] = []
    for region_id in sorted(by_region):
        indices = by_region[region_id]
        region_labels = tuple(labels_by_region.get(region_id, ()))
        region_rows = tuple(baseline[index] for index in indices)
        all_rows = (*region_rows, *region_labels)
        all_ids = _physical_cell_ids(all_rows)
        rows: list[tuple[
            int, WindowEvidence, np.ndarray, np.ndarray, np.ndarray
        ]] = []
        search_parts: list[tuple[np.ndarray, np.ndarray, np.ndarray,
                                 np.ndarray]] = []
        validation_parts: list[tuple[np.ndarray, np.ndarray, np.ndarray,
                                     np.ndarray]] = []
        # One pass over the union in ascending patch-ordinal order — the
        # exact order a single pooled pass would have used (labels carry
        # base-pass ordinals that interleave with the mop-up's).
        merged: list[tuple[int | None, WindowEvidence, np.ndarray]] = [
            (
                indices[position] if position < len(indices) else None,
                all_rows[position],
                all_ids[position],
            )
            for position in range(len(all_rows))
        ]
        merged.sort(key=lambda entry: entry[1].patch_id)
        for index, row, ids in merged:
            if not row.accepted:
                continue
            calibration = detect.Calibration(
                row.placement_id, row.calibration_score_nodes,
                row.calibration_probability_nodes, row.n_search)
            marginal = np.asarray(calibration.llr(row.scores), np.float64)
            counts, valid = detect.context_neighbour_counts(
                row.page_cells_yx, marginal > 0.0)
            known = row.reference_values >= 0
            heldout = ((131 * row.page_cells_yx[:, 0]
                        + 17 * row.page_cells_yx[:, 1]) & 1).astype(bool)
            search = known & ~heldout & valid
            validation = known & heldout & valid
            if search.any():
                search_parts.append((marginal[search],
                                     counts[search],
                                     row.reference_values[search], ids[search]))
            if validation.any():
                validation_parts.append((marginal[validation],
                                         counts[validation],
                                         row.reference_values[validation],
                                         ids[validation]))
            if index is not None:
                bins = np.where(valid, counts, -1).astype(np.int8)
                rows.append((index, row, marginal, counts, bins))
        if not rows:
            decisions.append(_empty_context_decision(
                region_id, "no_accepted_windows"))
            continue
        if not search_parts or not validation_parts:
            decisions.append(_partial_context_decision(
                region_id, search_parts, validation_parts))
            continue

        def pool(parts: list[tuple[np.ndarray, np.ndarray, np.ndarray,
                                   np.ndarray]], position: int,
                 dtype: np.dtype | type) -> np.ndarray:
            return np.concatenate(
                [np.asarray(part[position], dtype=dtype) for part in parts])

        search = detect.ContextObservations(
            region_id, pool(search_parts, 0, np.float64),
            pool(search_parts, 1, np.int8), pool(search_parts, 2, np.uint8),
            pool(search_parts, 3, np.int64))
        validation = detect.ContextObservations(
            region_id, pool(validation_parts, 0, np.float64),
            pool(validation_parts, 1, np.int8),
            pool(validation_parts, 2, np.uint8),
            pool(validation_parts, 3, np.int64))
        fit = detect.fit_context(search, validation)
        if fit.eligible:
            baseline_loss = _binary_logloss(
                validation.baseline_llr, validation.labels,
                validation.weights)
            candidate_loss = _binary_logloss(
                validation.baseline_llr
                + fit.offsets[validation.neighbour_count],
                validation.labels, validation.weights)
            adopted = candidate_loss < baseline_loss
            fit = replace(
                fit,
                adopted=adopted,
                reason=("adopted" if adopted
                        else "validation_gate_failed"),
                baseline_validation_logloss=baseline_loss,
                candidate_validation_logloss=candidate_loss,
            )
        decision = _context_record(region_id, fit)
        decisions.append(decision)
        if not fit.adopted:
            continue                       # exact baseline objects survive
        for index, row, marginal, _counts, bins in rows:
            corrected = detect.apply_context_offsets(
                marginal, bins, fit.offsets)
            heldout = (((131 * row.page_cells_yx[:, 0]
                         + 17 * row.page_cells_yx[:, 1]) & 1).astype(bool)
                       & (row.reference_values >= 0))
            loss = _binary_logloss(
                corrected[heldout], row.reference_values[heldout])
            selected[index] = replace(
                row, printed_llr=np.asarray(corrected, np.float32),
                heldout_logloss=loss, detector_profile=CONTEXT_PROFILE,
                context_decision_id=decision.decision_id)
    return tuple(selected), tuple(decisions)

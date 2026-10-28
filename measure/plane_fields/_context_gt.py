"""E4 leaves: A5's ink map rebuilt with GROUND-TRUTH columns.

docs/INDEPENDENT-PLANES §3(2) names the next discriminator for the dead
bands' 2.15 pp unattributed residue: **the Y-context circularity**.  A5
(``color_neighbourhood.region_context_bins``) builds each cell's
neighbourhood bin from the region's PROVISIONAL per-plane ink — the
detector's own ``marginal > 0`` reading wherever no exact bit is known —
and in a dead band Y's provisional reading is precisely the broken
quantity.  A wrong ink map gives a wrong bin gives a wrong correction.

The test replaces one or more columns of that ink map with the printed
truth and re-measures.  Four configurations:

===  ==========================================================
 a   baseline: the fit's own bins (production)
 b   Y's ink column = GT, C and M unchanged  <- the hypothesis
 c   C and M = GT, Y unchanged               <- the method control
 d   all three = GT                          <- the ceiling
===  ==========================================================

(c) calibrates the method: C and M are certified on these tiles, so their
provisional ink is already almost exactly right and (c) must move almost
nothing.  A (c) that moves as much as (b) would mean the instrument, not
the circularity, is doing the work.

Two arms per configuration, because "replace the bins" is ambiguous about
the CURVE fitted on them:

* ``bins`` — swap the bins, keep the incumbent A5 head.  This isolates
  the cost of a wrong BIN at a fixed correction.
* ``bins+head`` — swap the bins and refit the head on them
  (``color_context.fit_region_context``, the ladder's own leaf, the
  ladder's own gates).  The head is fitted on known cells whose bins also
  move, so it is contaminated by the same circularity; this is the full
  counterfactual.

Nothing here changes ``src/holo``: the bins are rebuilt by calling the
production leaf with a different evidence function, and the result is
carried on a ``replace``d copy of the harness's own :class:`RegionFit`.
The null proof is exact — configuration (a) rebuilt through this path
must be BIT-IDENTICAL to the bins the ladder itself produced.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from holo.receive.color_context import ContextConfig, label_floor_refusal
from holo.receive.color_neighbourhood import provisional_ink, region_context_bins
from holo.receive.color_stack import _binned_fraction

from . import _swim_region
from ._affine_fit import TILE_CELLS
from ._state_tables import features_tuple, selection_of

#: configuration id -> the ink-map columns replaced by ground truth.
CONFIGS: dict[str, tuple[int, ...]] = {
    "a": (), "b": (2,), "c": (0, 1), "d": (0, 1, 2)}
CONFIG_NAMES = {
    "a": "baseline (provisional ink)",
    "b": "Y column = GT",
    "c": "C,M columns = GT (method control)",
    "d": "all three = GT"}
PLANE_NAMES = ("C", "M", "Y")


def row_gt_bits(fit, ordinal: int, truth_bits: np.ndarray) -> np.ndarray:
    """``(N, 3)`` printed presence for one window's page cells."""
    cells = np.asarray(fit.rows[ordinal].page_cells_yx, np.int64)
    return truth_bits[cells[:, 0], cells[:, 1], :].astype(np.uint8)


def region_evidence(fit) -> tuple[np.ndarray, ...]:
    """The selected fit's per-row emitted evidence — A5's ink-map input.

    Computed ONCE and handed to every configuration: the four GT columns
    differ only by which column is overwritten, and re-scoring five
    million cells four times would be the whole cost of E4.  This is
    exactly the callable ``fit_region_stack`` hands ``region_context_bins``
    (``lambda o: selected_fit.evidence(selected_features[o])``), evaluated
    eagerly.
    """
    features = features_tuple(fit)
    return tuple(np.asarray(fit.selected_fit.evidence(row), np.float64)
                 for row in features)


def build_bins(fit, truth_bits: np.ndarray, planes: tuple[int, ...],
               evidence: tuple[np.ndarray, ...] | None = None
               ) -> tuple[np.ndarray, ...]:
    """The region's context bins with ``planes``' ink taken from GT.

    ``planes = ()`` is the ladder's own call, expression for expression:
    ``region_context_bins(row_tuple, lambda o: fit.evidence(features[o]),
    cmy8=True)``.  A GT column is injected as a hard ``+/-1`` evidence
    value, which ``provisional_ink``'s ``> 0`` reading turns into exactly
    the printed bit; the known-bit overwrite inside the leaf then runs
    unchanged (and is a no-op on a GT column, since GT and the exact bits
    agree — :func:`known_bit_agreement` measures that rather than
    assuming it).
    """
    values_by_row = region_evidence(fit) if evidence is None else evidence

    def evidence_of(ordinal: int) -> np.ndarray:
        values = values_by_row[ordinal]
        if not planes:
            return values
        out = np.array(values, np.float64)
        gt = row_gt_bits(fit, ordinal, truth_bits)
        for plane in planes:
            out[:, plane] = np.where(gt[:, plane] > 0, 1.0, -1.0)
        return out

    return region_context_bins(fit.rows, evidence_of, cmy8=True)


def known_bit_agreement(fit, truth_bits: np.ndarray) -> dict:
    """Do the exact bits the receiver holds equal the printed truth?

    The truth field is validated against certificates upstream; this is
    the same question asked of every KNOWN cell in the region (format
    furniture plus prior-barrier certificates), which is the population
    the ink map overwrites.  A nonzero mismatch would void E4.
    """
    checked = 0
    mismatched = 0
    for ordinal in range(len(fit.rows)):
        row = fit.rows[ordinal]
        known = np.asarray(row.known_component_mask, np.bool_)
        bits = np.asarray(row.known_component_bits, np.uint8) > 0
        gt = row_gt_bits(fit, ordinal, truth_bits) > 0
        checked += int(known.sum())
        mismatched += int(np.count_nonzero((bits != gt) & known))
    return {"known_cells": checked, "mismatched": mismatched,
            "exact": bool(checked > 0 and mismatched == 0)}


def ink_disagreement(fit, truth_bits: np.ndarray, address=None,
                     evidence: tuple[np.ndarray, ...] | None = None) -> dict:
    """Where the PROVISIONAL ink map disagrees with the printed field.

    Region-wide and, when ``address`` is given, on that tile's cells
    alone — the quantity E4 is about (in a dead band Y's provisional ink
    is wrong far more often than C's or M's, and that is what feeds every
    neighbour's bin).
    """
    values_by_row = region_evidence(fit) if evidence is None else evidence
    totals = np.zeros(3, np.int64)
    wrong = np.zeros(3, np.int64)
    tile_totals = np.zeros(3, np.int64)
    tile_wrong = np.zeros(3, np.int64)
    for ordinal in range(len(fit.rows)):
        row = fit.rows[ordinal]
        ink = provisional_ink(values_by_row[ordinal], cmy8=True)
        known = np.asarray(row.known_component_mask, np.bool_)
        bits = np.asarray(row.known_component_bits, np.uint8) > 0
        effective = np.where(known, bits, ink)
        gt = row_gt_bits(fit, ordinal, truth_bits) > 0
        totals += effective.shape[0]
        wrong += np.count_nonzero(effective != gt, axis=0)
        if address is not None:
            cells = np.asarray(row.page_cells_yx, np.int64)
            select = ((cells[:, 0] // TILE_CELLS == address[1])
                      & (cells[:, 1] // TILE_CELLS == address[2]))
            if select.any():
                tile_totals += int(select.sum())
                tile_wrong += np.count_nonzero(
                    effective[select] != gt[select], axis=0)
    out = {
        "region": {
            PLANE_NAMES[plane]: {
                "cells": int(totals[plane]), "wrong": int(wrong[plane]),
                "fraction": (None if not totals[plane]
                             else float(wrong[plane] / totals[plane]))}
            for plane in range(3)}}
    if address is not None:
        out["tile"] = {
            PLANE_NAMES[plane]: {
                "cells": int(tile_totals[plane]),
                "wrong": int(tile_wrong[plane]),
                "fraction": (None if not tile_totals[plane]
                             else float(tile_wrong[plane]
                                        / tile_totals[plane]))}
            for plane in range(3)}
    return out


def bin_change(baseline: tuple[np.ndarray, ...],
               candidate: tuple[np.ndarray, ...],
               fit, address=None) -> dict:
    """Did the override actually reach the bins, and where?

    Reported per plane, region-wide and on the target tile, plus the
    COLUMN INVARIANCE check every configuration must pass: a column whose
    ink was not overridden and whose neighbours' ink was not either must
    come back bit-identical.
    """
    total = np.zeros(3, np.int64)
    changed = np.zeros(3, np.int64)
    tile_total = np.zeros(3, np.int64)
    tile_changed = np.zeros(3, np.int64)
    for ordinal, (left, right) in enumerate(
            zip(baseline, candidate, strict=True)):
        difference = np.asarray(left) != np.asarray(right)
        total += difference.shape[0]
        changed += np.count_nonzero(difference, axis=0)
        if address is not None:
            cells = np.asarray(fit.rows[ordinal].page_cells_yx, np.int64)
            select = ((cells[:, 0] // TILE_CELLS == address[1])
                      & (cells[:, 1] // TILE_CELLS == address[2]))
            if select.any():
                tile_total += int(select.sum())
                tile_changed += np.count_nonzero(difference[select], axis=0)
    out = {
        "region": {
            PLANE_NAMES[plane]: {
                "cells": int(total[plane]), "changed": int(changed[plane]),
                "fraction": (None if not total[plane]
                             else float(changed[plane] / total[plane]))}
            for plane in range(3)},
        "identical_planes": [PLANE_NAMES[plane] for plane in range(3)
                             if changed[plane] == 0]}
    if address is not None:
        out["tile"] = {
            PLANE_NAMES[plane]: {
                "cells": int(tile_total[plane]),
                "changed": int(tile_changed[plane]),
                "fraction": (None if not tile_total[plane]
                             else float(tile_changed[plane]
                                        / tile_total[plane]))}
            for plane in range(3)}
    return out


def refit_context_head(fit, bins: tuple[np.ndarray, ...], *, config=None):
    """Refit A5's curves on ``bins`` through the ladder's own leaf.

    Mirrors ``color_stack.fit_region_stack``'s A5 block: the same
    population (the ownership's known cells), the same floors, the same
    two gates.  Returns ``(detector_fit, record)`` where ``detector_fit``
    is the incumbent with its context head replaced, or the incumbent
    unchanged when the refit refuses (which is the ladder's exact null).
    """
    from holo.receive.color_context import fit_region_context, summarize_context

    context_cfg = ContextConfig() if config is None else config
    detector_fit = fit.selected_fit
    selection = selection_of(fit)
    search = np.asarray(selection.search, np.bool_)
    starved = label_floor_refusal(search, context_cfg)
    if starved:
        return detector_fit, {"reason": starved, "adopted": False}
    result = fit_region_context(
        detector_fit.model, detector_fit.detector, detector_fit.cmy7_head,
        selection.gather(features_tuple(fit)),
        selection.gather(bins, dtype=np.int8),
        np.asarray(selection.states, np.int64),
        np.asarray(selection.kinds, np.int8), search, context_cfg,
        binned_fraction=_binned_fraction(bins, fit.emission_by_row))
    summary = summarize_context(result)
    record = {
        "reason": str(summary.reason), "adopted": bool(summary.adopted),
        "variant": str(summary.variant),
        "curves_adopted": int(summary.curves_adopted),
        "curves_total": int(summary.curves_total),
        "curve_reasons": {name: int(count)
                          for name, count in summary.curve_reasons},
        "incumbent_nll": float(summary.incumbent_nll),
        "candidate_nll": float(summary.candidate_nll),
        "word_incumbent_nll": float(summary.word_incumbent_nll),
        "word_candidate_nll": float(summary.word_candidate_nll),
        "dust_incumbent_nll": float(summary.dust_incumbent_nll),
        "dust_candidate_nll": float(summary.dust_candidate_nll),
        "binned_fraction": float(summary.binned_fraction),
    }
    if result.head is None:
        return detector_fit, record
    return (replace(detector_fit, context=result.head,
                    context_reason=result.reason), record)


def with_context(fit, bins: tuple[np.ndarray, ...], detector_fit=None):
    """A copy of the region fit reading ``bins`` (and optionally a head)."""
    return replace(
        fit, context_bins=tuple(bins),
        selected_fit=fit.selected_fit if detector_fit is None else detector_fit)


def tile_blocks(fit, spec, address) -> tuple:
    """This fit's durable blocks for one tile, from its retained features."""
    windows = []
    for ordinal in fit.tile_rows.get(address, ()):
        features = fit.features0.get(ordinal)
        if features is None:
            continue
        windows.append(_swim_region.window_evidence(fit, ordinal, features))
    if not windows:
        return ()
    return tuple(row for row in _swim_region.capture_blocks(fit, spec, windows)
                 if row.address == address)


__all__ = [
    "CONFIGS", "CONFIG_NAMES", "PLANE_NAMES", "bin_change", "build_bins",
    "ink_disagreement", "known_bit_agreement", "refit_context_head",
    "region_evidence", "row_gt_bits", "tile_blocks", "with_context",
]

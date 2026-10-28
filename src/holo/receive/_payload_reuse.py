"""E023b refined-generation sampling that reuses exact generation-zero work.

This private module owns ``sample_refined_reusing_generation`` and its
reconciliation helpers: proving a generation-zero row against its baseline
placement, recovering the marginal PAVA form of a context-profiled window,
and the pool-law (L5) region replay bookkeeping.  Split from
``_payload_windows.py`` in the Phase 4 hammer batch (RECEIVE-DESIGN
v0.38) together with :mod:`_payload_sampling` and :mod:`_payload_context`.
Since v0.42 its one production consumer is the R-level delta collector
(:func:`payload.collect_refined_region_delta`): the region-recompute
logic re-homed from the retired inline refined generation.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import numpy as np

from ..format.descriptor import FormatSpec
from . import detect
from ._payload_sampling import (
    _WindowRows,
    _calibrate,
    _filter_signature,
    _region_pitch,
    _sample_window,
    _window_label_only,
    _window_rows,
    format_reference_values,
)
from .payload_model import (
    CONTEXT_PROFILE,
    PAVA_PROFILE,
    EvidenceSource,
    RawLumaRaster,
    WindowEvidence,
)
from .placement.model import AddressResult, PlacedPatch


def _marginal_window(window: WindowEvidence) -> WindowEvidence:
    """Recover the exact pre-context PAVA record from a profiled window.

    Generation zero retains the marginal calibration and LLR arrays even
    when the region context arm is adopted.  Recomputing only its diagnostic
    held-out loss lets a changed region replay context without touching the
    unchanged window's pixels or calibration.
    """
    if window.detector_profile == PAVA_PROFILE:
        return window
    if window.detector_profile != CONTEXT_PROFILE or not window.accepted:
        raise ValueError("payload: malformed context-profiled window")
    known = window.reference_values >= 0
    heldout = (
        ((131 * window.page_cells_yx[:, 0]
          + 17 * window.page_cells_yx[:, 1]) & 1).astype(bool)
        & known
    )
    calibration = detect.Calibration(
        window.placement_id,
        window.calibration_score_nodes,
        window.calibration_probability_nodes,
        window.n_search,
    )
    probability = calibration.probability(window.scores[heldout])
    labels = window.reference_values[heldout].astype(np.float64)
    loss = float(-np.mean(
        labels * np.log(probability)
        + (1.0 - labels) * np.log(1.0 - probability)))
    return replace(
        window,
        printed_llr=window.baseline_printed_llr,
        heldout_logloss=loss,
        detector_profile=PAVA_PROFILE,
        context_decision_id=None,
    )


def _validate_reused_window(
    source: EvidenceSource,
    patch: PlacedPatch,
    window: WindowEvidence,
    spec: FormatSpec,
) -> _WindowRows:
    """Prove that a generation-zero row belongs to the baseline placement."""
    rows = _window_rows(patch, spec)
    placement_id = (
        f"{source.source_sha256}/{source.lane_id}/"
        f"patch-{int(patch.patch_id)}")
    region_id = (
        f"{source.source_sha256}/{source.lane_id}/region-"
        f"{int(patch.region_index)}")
    if (
        window.source != source
        or window.placement_id != placement_id
        or window.patch_id != int(patch.patch_id)
        or window.region_id != region_id
        or window.page != int(patch.candidate.page)
        or window.redundant != bool(patch.redundant)
        or window.segment_id != rows.segment_id
        or not np.array_equal(
            window.segment_local_cells_yx, rows.local_cells_yx)
        or not np.array_equal(window.page_cells_yx, rows.page_cells_yx)
        or not np.array_equal(window.scan_points_yx, rows.scan_points_yx)
    ):
        raise ValueError(
            "payload: generation zero does not replay its baseline placement")
    return rows


def sample_refined_reusing_generation(
    raster: RawLumaRaster,
    source: EvidenceSource,
    baseline_address: AddressResult,
    refined_address: AddressResult,
    generation_windows: Iterable[WindowEvidence],
    spec: FormatSpec,
    *,
    changed_patch_ids: Iterable[int],
    included_patch_ids: frozenset[int] | None = None,
    terminal_addresses: frozenset[tuple[int, int, int]] = frozenset(),
) -> tuple[
    tuple[WindowEvidence, ...],
    frozenset[str],
    frozenset[int],
    tuple[WindowEvidence, ...],
]:
    """Prepare a refined generation while reusing exact unchanged work.

    Rows in unchanged regions remain fully profiled generation-zero objects.
    Rows in regions containing a revised pose are returned in their marginal
    PAVA form so the caller can replay that region's coupled context fit.
    Only revised patches are resampled unless the pose revision changes the
    integer crop/filter policy, in which case that region is conservatively
    resampled in full.

    Pool law (v0.35): the pitch/filter-signature pool of every region is
    generation zero's pool — placements UNION all label rows, including
    label-only (certified-complete/zero-payload) windows — and an affected
    region re-derives ALL of its label rows with no terminal gate, so both
    passes fit the identical region population.
    """
    # Interior seam: typed inputs are trusted (kiss validation-boundary
    # ruling); only cross-object domain invariants are checked below.
    changed = frozenset(int(value) for value in changed_patch_ids)
    included = included_patch_ids

    baseline_all = {
        int(row.patch_id): row
        for row in baseline_address.payload_placements
    }
    refined_all = {
        int(row.patch_id): row
        for row in refined_address.payload_placements
    }
    if (
        len(baseline_all) != len(baseline_address.payload_placements)
        or len(refined_all) != len(refined_address.payload_placements)
        or set(baseline_all) != set(refined_all)
    ):
        raise ValueError(
            "payload: refinement changed the promoted placement domain")
    selected_patch_ids = (
        frozenset(baseline_all) if included is None else included)
    if not selected_patch_ids.issubset(baseline_all):
        raise ValueError(
            "payload: included patch ids name no promoted placement")
    if not changed.issubset(selected_patch_ids):
        raise ValueError(
            "payload: changed patch ids fall outside the included domain")
    baseline_patches = {
        patch_id: baseline_all[patch_id]
        for patch_id in sorted(selected_patch_ids)
    }
    refined_patches = {
        patch_id: refined_all[patch_id]
        for patch_id in sorted(selected_patch_ids)
    }
    windows = tuple(generation_windows)
    by_patch = {int(row.patch_id): row for row in windows}
    if len(by_patch) != len(windows) or not set(by_patch) <= set(
            baseline_patches):
        raise ValueError(
            "payload: generation zero and promoted placements disagree")
    # Windows absent from generation zero must be exactly the label-only
    # (certified-complete or zero-payload) windows the sampler routed to
    # the label channel; anything else is genuine domain drift and fails
    # closed.  Pool law L5: they LEAVE the payload domain but STAY in the
    # region pitch/filter pools and re-derive as label rows for affected
    # regions — their poses are frozen (labels never refine).
    label_only_by_region: dict[int, list[PlacedPatch]] = {}
    for patch_id in sorted(set(baseline_patches) - set(by_patch)):
        skipped = baseline_patches[patch_id]
        rows = _window_rows(skipped, spec)
        labels = format_reference_values(
            spec, int(skipped.candidate.page), rows.page_cells_yx)
        if not _window_label_only(
                rows, labels, int(skipped.candidate.page), spec,
                terminal_addresses):
            raise ValueError(
                "payload: generation zero and promoted placements disagree")
        twin = refined_patches[patch_id]
        if (patch_id in changed
                or skipped.region_index != twin.region_index
                or skipped.segment.segment.pose
                != twin.segment.segment.pose):
            raise ValueError(
                "payload: refinement changed a label-only window")
        label_only_by_region.setdefault(
            int(skipped.region_index), []).append(skipped)
        del baseline_patches[patch_id]
        del refined_patches[patch_id]

    actual_changed: set[int] = set()
    baseline_regions: dict[int, list[PlacedPatch]] = {}
    refined_regions: dict[int, list[PlacedPatch]] = {}
    refined_rows_by_patch: dict[int, _WindowRows] = {}
    for patch_id in sorted(baseline_patches):
        baseline = baseline_patches[patch_id]
        refined = refined_patches[patch_id]
        baseline_rows = _validate_reused_window(
            source, baseline, by_patch[patch_id], spec)
        refined_rows = _window_rows(refined, spec)
        refined_rows_by_patch[patch_id] = refined_rows
        if (
            baseline.region_index != refined.region_index
            or baseline.candidate.page != refined.candidate.page
            or baseline.candidate.rot_k != refined.candidate.rot_k
            or baseline.redundant != refined.redundant
            or baseline.segment.page_origin_yx
            != refined.segment.page_origin_yx
            or baseline.segment.rot_k != refined.segment.rot_k
            or baseline.segment.segment.window
            != refined.segment.segment.window
            or not np.array_equal(
                baseline_rows.local_cells_yx, refined_rows.local_cells_yx)
            or not np.array_equal(
                baseline_rows.page_cells_yx, refined_rows.page_cells_yx)
        ):
            raise ValueError(
                "payload: refinement changed frozen placement geometry")
        if baseline.segment.segment.pose != refined.segment.segment.pose:
            actual_changed.add(patch_id)
        elif not np.array_equal(
                baseline_rows.scan_points_yx, refined_rows.scan_points_yx):
            raise ValueError(
                "payload: unchanged pose changed its sampled coordinates")
        baseline_regions.setdefault(
            int(baseline.region_index), []).append(baseline)
        refined_regions.setdefault(
            int(refined.region_index), []).append(refined)
    if actual_changed != set(changed):
        raise ValueError(
            "payload: changed patch ids do not name the revised poses")
    if set(baseline_regions) != set(refined_regions):
        raise ValueError("payload: refinement changed the region domain")

    # One label set per address, identical in both passes (labels are
    # base-pass poses and never refine); the refined address's labels are
    # the ones sampled, with the baseline's validated against them.
    baseline_labels = {
        int(row.patch_id): row for row in baseline_address.label_placements}
    refined_labels = {
        int(row.patch_id): row for row in refined_address.label_placements}
    if set(baseline_labels) != set(refined_labels) or any(
            baseline_labels[patch_id].region_index
            != refined_labels[patch_id].region_index
            or baseline_labels[patch_id].segment.segment.pose
            != refined_labels[patch_id].segment.segment.pose
            for patch_id in baseline_labels):
        raise ValueError(
            "payload: refinement changed the label placements")
    label_patches_by_region: dict[int, list[PlacedPatch]] = {}
    for patch in refined_address.label_placements:
        label_patches_by_region.setdefault(
            int(patch.region_index), []).append(patch)
    output: list[WindowEvidence] = []
    affected_regions: set[str] = set()
    resampled_patch_ids: set[int] = set()
    label_rows_out: list[WindowEvidence] = []
    for region_index in sorted(refined_regions):
        baseline_group = tuple(sorted(
            baseline_regions[region_index], key=lambda row: int(row.patch_id)))
        refined_group = tuple(sorted(
            refined_regions[region_index], key=lambda row: int(row.patch_id)))
        # Pool law L5: the pitch/filter-signature pool is placements UNION
        # all label rows — D7 labels AND label-only (certified-complete or
        # zero-payload) windows — exactly generation zero's pool.  Labels
        # re-derive for affected regions so the replayed context fit keeps
        # its pooled population; labels never refine (frozen poses).
        label_group = tuple(sorted(
            (*label_patches_by_region.get(region_index, ()),
             *label_only_by_region.get(region_index, ())),
            key=lambda row: int(row.patch_id)))
        region_changed = {
            int(row.patch_id) for row in refined_group
            if int(row.patch_id) in changed}
        if not region_changed:
            output.extend(by_patch[int(row.patch_id)]
                          for row in refined_group)
            continue
        region_id = by_patch[int(refined_group[0].patch_id)].region_id
        affected_regions.add(region_id)
        resample = set(region_changed)
        if (_filter_signature(baseline_group + label_group)
                != _filter_signature(refined_group + label_group)):
            resample.update(int(row.patch_id) for row in refined_group)
        pitch_px = _region_pitch(refined_group + label_group)
        for patch in refined_group:
            patch_id = int(patch.patch_id)
            if patch_id not in resample:
                output.append(_marginal_window(by_patch[patch_id]))
                continue
            rows = refined_rows_by_patch[patch_id]
            means = _sample_window(raster, patch, rows, pitch_px)
            labels = format_reference_values(
                spec, int(patch.candidate.page), rows.page_cells_yx)
            output.append(_calibrate(
                source, patch, rows, means, labels, spec))
            resampled_patch_ids.add(patch_id)
        for patch in label_group:
            rows = _window_rows(patch, spec)
            labels = format_reference_values(
                spec, int(patch.candidate.page), rows.page_cells_yx)
            means = _sample_window(raster, patch, rows, pitch_px)
            label_rows_out.append(_calibrate(
                source, patch, rows, means, labels, spec))
    return (
        tuple(output),
        frozenset(affected_regions),
        frozenset(resampled_patch_ids),
        tuple(label_rows_out),
    )

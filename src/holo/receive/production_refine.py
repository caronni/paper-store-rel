"""Production K refinement level R(Lk) leaf (RECEIVE-DESIGN v0.42, clause B).

Certified pose refinement moved out of the inline K payload schedule into
dedicated refinement levels: one ``R(Lk)`` plan entry per ordinary ladder
lane, after all M-levels, run only under ``--refine``.  This module is the
K leaf behind :meth:`ProductionPayload.process`'s ``refine_of`` route:

* INVENTORY — the base lane Lk's committed poses (accepted AND redundant;
  quarantined placements excluded upstream) re-derive deterministically as
  payload-capable placements on Lk's exact raster
  (:func:`place.place_committed`; the R-level binds the base transform via
  ``LaneSpec.base_lane_id``).
* NEEDMAP — the full accumulated certificate frontier prunes certified
  addresses: a pixel-free bounding-box pre-gate skips the level entirely
  when every committed window's page span is certified (the lazy raster
  stand-in never materializes), then the exact
  :func:`payload.unresolved_region_patch_ids` law prunes at region
  granularity.
* REFINEMENT — one generation-zero collection over the needed domain, then
  the one qualified forward proposal per eligible window
  (:func:`certified_cascade.refine_address_once`, mint-once printed-field
  cache), against the full frontier.  ``pose_refine.window_progress``
  events publish here now (moved from the inline stage).
* DELTA — adopted windows re-home the ``_payload_reuse`` region-recompute:
  fresh sampling at refined poses, region context over each affected
  region with the pool law's full population, and the one-owner freeze
  WITHIN the delta (:func:`payload.collect_refined_region_delta`).
  Unaffected regions contribute NOTHING; their Lk evidence stands.  No
  adoptions => empty delta, cheap barrier.
* EVIDENCE NAMESPACE — blocks/attempts/certificates mint under the R
  lane's OWN lane id (``evidence_lane_id`` is the R lane itself); only
  certificates cross lanes, so there is no supersession of base blocks
  and no new evidence law.  Adopted refined poses mint as durable
  PoseRecords under the R lane id via the replacement-address seam; block
  dependency lineage is the base pose lineage unioned with the adopted
  frontier dependencies.

The decode schedule over the delta is the ordinary shared engine
(scan -> union -> advisory preclose -> selective retry150), reusing
``ProductionPayload``'s freeze/blocks/decode/retry/complete methods.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import _diagnostic_snapshots as diagnostic_snapshots
from . import _production_diagnostics as production_diagnostics
from . import payload
from .certified_cascade import ForwardRefinement, refine_address_once
from .payload_model import CONTEXT_PROFILE, EvidenceSource
from .place import place_committed
from .production import (
    _page_to_view_affine,
    empty_refine_payload,
)
from .runtime import LaneContext, LaneStageOutput
from .types import (
    AddressArtifact,
    AddressProduct,
    Detail,
    PoseRecord,
    RefineAddressPlan,
    SurveyProduct,
)

if TYPE_CHECKING:  # circular at runtime: production_payload routes here
    from .production_payload import ProductionPayload


def _pose_span_tiles(
    row: object, page_shape_cells: tuple[int, int],
) -> frozenset[tuple[int, int]]:
    """Conservative tile cover of one committed pose's page-cell span.

    The window's rotated shape at its integer cell origin encloses every
    audited cell, so the returned tile set is a SUPERSET of the tiles the
    window's payload cells can touch.  Used only by the pixel-free
    pre-gate: a fully-certified superset proves the exact NeedMap would
    prune the window too, so skipping is exact, never just cheap.
    """
    height, width = (int(value) for value in row.window_shape_yx_cells)
    if int(row.rot90) % 2:
        height, width = width, height
    y0, x0 = (int(value) for value in row.cell_origin_yx)
    y1 = min(int(page_shape_cells[0]), y0 + height)
    x1 = min(int(page_shape_cells[1]), x0 + width)
    y0 = max(0, y0)
    x0 = max(0, x0)
    if y1 <= y0 or x1 <= x0:
        return frozenset()
    return frozenset(
        (tile_y, tile_x)
        for tile_y in range(y0 // 64, (y1 - 1) // 64 + 1)
        for tile_x in range(x0 // 64, (x1 - 1) // 64 + 1))


def _every_span_certified(
    plan: RefineAddressPlan,
    page_shape_cells: tuple[int, int],
    certified_addresses: frozenset[tuple[int, int, int]],
) -> bool:
    """True when no committed window can cover an uncertified tile."""
    for row in plan.poses:
        page = int(row.page)
        if any((page, tile_y, tile_x) not in certified_addresses
               for tile_y, tile_x in _pose_span_tiles(
                   row, page_shape_cells)):
            return False
    return True


def _mint_refined_address(
    context: LaneContext,
    survey_product: SurveyProduct,
    plan: RefineAddressPlan,
    refinement: ForwardRefinement,
) -> AddressProduct:
    """Mint ONLY the adopted refined poses, under the R lane's own ids.

    The durable rows mirror :func:`production._address_product`'s pose
    minting for the revised segments: base-lane region ids (regions are a
    global durable namespace), the R lane id and pose-id prefix, and
    dependency lineage = base pose lineage UNION the adopted frontier
    certificates.  No proposals, no losers, no parked rows — an R-level
    feeds no hint channel and never parks.
    """
    prefix = f"{context.capture.source_sha256}/{context.lane.lane_id}"
    base_rows = {int(row.patch_id): row for row in plan.poses}
    adopted_deps = {
        int(patch_id): tuple(deps)
        for patch_id, deps in refinement.patch_dependencies}
    by_patch = {
        int(row.patch_id): row
        for row in refinement.address.payload_placements}
    poses: list[PoseRecord] = []
    for patch_id in sorted(adopted_deps):
        patch = by_patch[patch_id]
        base = base_rows[patch_id]
        segment = patch.segment
        fitted = segment.segment
        deps = tuple(sorted(
            set(base.dependency_certificate_ids)
            | set(adopted_deps[patch_id])))
        native = context.lane_to_native_affine(_page_to_view_affine(segment))
        poses.append(PoseRecord(
            pose_id=f"{prefix}/patch-{patch_id}/pose",
            capture_id=context.capture.source_sha256,
            lane_id=context.lane.lane_id,
            region_id=base.region_id,
            patch_id=patch_id,
            placement_outcome=(
                "redundant" if patch.redundant else "accepted"),
            page=int(patch.candidate.page),
            cell_origin_yx=tuple(
                int(value) for value in segment.page_origin_yx),
            native_affine=tuple(float(value) for value in native.ravel()),
            rot90=int(segment.rot_k),
            quality=1.0 - float(patch.candidate.validation_mismatch),
            window_id=int(fitted.window.window_id),
            window_origin_yx_px=tuple(
                int(value) for value in fitted.window.origin_yx_px),
            window_shape_yx_cells=tuple(
                int(value) for value in fitted.window.shape_yx_cells),
            window_depth=int(fitted.window.depth),
            lane_pose_origin_yx=tuple(
                float(value) for value in fitted.pose.origin_yx),
            lane_pose_jacobian=tuple(
                float(value) for row in fitted.pose.jacobian_yx
                for value in row),
            lane_pose_phase_yx=tuple(
                float(value) for value in fitted.pose.phase_yx),
            lane_pose_pitch_px=float(fitted.pose.pitch_px),
            lane_pose_angle_deg=float(fitted.pose.angle_deg),
            segment_support_cells=int(fitted.support_cells),
            segment_phase_contrast=float(fitted.phase_contrast),
            segment_pitch_yx_px=tuple(
                float(value) for value in fitted.pitch_yx_px),
            segment_orthogonality_error_deg=float(
                fitted.orthogonality_error_deg),
            dependency_certificate_ids=deps,
        ))
    artifact = AddressArtifact(
        f"{prefix}/address", survey_product.artifact.survey_id,
        tuple(row.pose_id for row in poses))
    return AddressProduct(
        artifact, tuple(poses), transient=refinement.address)


def process_refine_level(
    engine: "ProductionPayload",
    context: LaneContext,
    survey_product: SurveyProduct,
    address_product: AddressProduct,
) -> LaneStageOutput:
    """Run one R(Lk) K refinement level to its payload product."""
    plan = address_product.transient
    if not isinstance(plan, RefineAddressPlan):
        raise TypeError("refinement payload stage needs RefineAddressPlan")
    from .production_payload import (
        _PayloadPlan,
        _certified_k_addresses,
    )

    certified_addresses = _certified_k_addresses(plan.certificates)
    page_shape_cells = context.spec.layout.cells_yx
    # Pixel-free pre-gates: with no frontier there is nothing to refine
    # against, with no committed poses nothing to refine, and with every
    # window span certified the exact NeedMap prunes everything — in all
    # three cases the lazy raster stand-in never materializes.
    if (not plan.poses or not plan.certificates
            or _every_span_certified(
                plan, page_shape_cells, certified_addresses)):
        return empty_refine_payload(context, address_product)
    base_address = place_committed(
        context.raster, context.spec,
        poses=plan.poses, regions=plan.regions)
    promoted_patch_ids = frozenset(
        int(row.patch_id) for row in base_address.payload_placements)
    included = (
        payload.unresolved_region_patch_ids(
            base_address, context.spec, certified_addresses)
        if promoted_patch_ids else frozenset())
    if not included:
        return empty_refine_payload(context, address_product)
    pruned_patch_ids = promoted_patch_ids - included
    pruned_region_indices = frozenset(
        int(row.region_index)
        for row in base_address.payload_placements
        if int(row.patch_id) in pruned_patch_ids)
    k_plan = _PayloadPlan(
        certified_addresses, included,
        pruned_patch_ids, pruned_region_indices)
    context.progress(
        "payload.plan",
        details=(Detail("payload.placements", len(promoted_patch_ids)),
                 Detail("payload.placements_quarantined", 0),
                 Detail("payload.prior_certificates",
                        len(plan.certificates)),
                 Detail("payload.prior_certified_addresses",
                        len(certified_addresses)),
                 Detail("payload.needed_patches", len(included)),
                 Detail("payload.pruned_terminal_patches",
                        len(pruned_patch_ids)),
                 Detail("payload.pruned_terminal_regions",
                        len(pruned_region_indices)),
                 Detail("payload.detector_profile", CONTEXT_PROFILE),
                 Detail("payload.refine_of", plan.base_lane_id)),
    )
    source = EvidenceSource(
        context.capture.source_sha256, context.lane.evidence_lane_id)
    generation0 = payload.collect_capture_evidence(
        context.raster, source, base_address, context.spec,
        detector_profile=CONTEXT_PROFILE,
        included_patch_ids=included,
        terminal_addresses=certified_addresses,
        region_progress=production_diagnostics.install_adapter(
            context, "payload.region.adapter.install",
            lambda: production_diagnostics.payload_region_callback(
                context, 0)))
    refinement = refine_address_once(
        context.raster, base_address, generation0,
        context.spec, plan.certificates,
        # Refine over the SAMPLED payload domain: label-only windows carry
        # no payload evidence to refine.  The aperture pool spans the full
        # sampled region population (placements UNION labels, pool law
        # L5) so replay reproduces generation zero exactly.
        included_patch_ids=frozenset(
            int(row.patch_id) for row in generation0.windows),
        pool_patch_ids=included)
    if context.observer_enabled:
        for row in refinement.summaries:
            context.observe(
                "pose_refine.window_progress.adapter",
                lambda row=row: context.progress(
                    "pose_refine.window_progress",
                    details=production_diagnostics.refinement_details(row),
                    snapshot_factory=lambda:
                        diagnostic_snapshots.refinement(row),
                ))
            if not context.observer_enabled:
                break
    if not refinement.adopted:
        # No adoptions => the delta is empty by definition and the
        # barrier commits cheaply; every region's Lk evidence stands.
        return empty_refine_payload(context, address_product)
    active_address = _mint_refined_address(
        context, survey_product, plan, refinement)
    context.progress(
        "address.final",
        details=(Detail("address.refined", True),
                 Detail("address.placements",
                        len(refinement.address.placements))),
        snapshot_factory=lambda: diagnostic_snapshots.address(
            active_address),
    )
    delta = payload.collect_refined_region_delta(
        context.raster, source, base_address,
        refinement.address, generation0, context.spec,
        changed_patch_ids=tuple(
            row.patch_id for row in refinement.summaries
            if row.metrics.adopted),
        included_patch_ids=included,
        terminal_addresses=certified_addresses,
        detector_profile=CONTEXT_PROFILE,
        region_progress=production_diagnostics.install_adapter(
            context, "payload.region.adapter.install",
            lambda: production_diagnostics.payload_region_callback(
                context, 1)))
    unresolved_delta = engine._freeze(context, delta, k_plan)
    base_deps = {
        int(row.patch_id): tuple(row.dependency_certificate_ids)
        for row in plan.poses}
    adopted_deps = dict(refinement.patch_dependencies)
    dependencies = {
        window.placement_id: tuple(sorted(
            set(base_deps.get(int(window.patch_id), ()))
            | set(adopted_deps.get(int(window.patch_id), ()))))
        for window in delta.windows}
    new_blocks, frontier_blocks, mopup_drops = (
        engine._blocks(context, dependencies, unresolved_delta,
                       certified_addresses))
    store, leaf, engine_run, preclose_attempted = engine._decode(
        context, new_blocks, frontier_blocks)
    durable_attempts, durable_certificates, retry_rows = engine._retry(
        context, store, leaf, engine_run)
    return engine._complete(
        context,
        active_address=active_address,
        replacement_address=active_address,
        refinement_eligible=refinement.eligible,
        refinement_adopted=refinement.adopted,
        new_blocks=new_blocks,
        frontier_blocks=frontier_blocks,
        store=store,
        leaf=leaf,
        engine_run=engine_run,
        durable_attempts=durable_attempts,
        durable_certificates=durable_certificates,
        retry_rows=retry_rows,
        preclose_attempted=preclose_attempted,
        mopup_drops=mopup_drops,
    )


__all__ = ["process_refine_level"]

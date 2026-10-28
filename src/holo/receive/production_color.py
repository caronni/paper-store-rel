"""Production orchestration for provisional CMY7 and CMY8 receive rows.

The numerical leaves remain deliberately separate:

* :mod:`color_payload` turns BCH-promoted E022 placements and aligned RGB
  into one compact physical evidence block per source/lane/tile;
* :mod:`color_refine` owns the v0.42 refinement level R(Lk): committed
  base-lane poses reconstruct through the shared
  :func:`place.place_committed` audited re-derivation (K parity), each
  eligible window gets the §7 certified forward pose proposal against the
  full accumulated certificate frontier, and adopted windows trigger the
  affected-region payload delta in the R lane's OWN evidence namespace;
* :mod:`color_attempts` attempts one logical stream from an exact scan or
  same-lane union view; and
* the ordinary receive ledger retains BP150 as a distinct, automatic retry
  stage.

Since RECEIVE-DESIGN v0.42 (stage C) the ordinary/mop-up color payload
barrier is generation-zero only — inline refinement moved into the R(Lk)
level, run under the invocation-only ``--refine`` flag.  This module only
schedules those leaves and materialises the existing typed E023b/E023c
barrier records.  K continues through ``ProductionPayload``.

Since v0.51 (PK4.3) there is a fourth leaf: the SUPPLEMENTAL level
``U(Lk, arm)`` (:meth:`ProductionColorPayload._uplift_level`), the
scheduled — not gated — form of an arm that cannot prove universal
non-regression.  It is the R leaf minus pose refinement plus one forced
arm override, and the per-address retirement law makes it monotone by
construction.  PLANE-FIELDS W3 registers a fourth such arm, ``field``
(the workplan's ``uF``): the same leaf, no stack override at all, and
the per-plane delta field FORCED ON for its collection — the R2 round,
reading the residue through every certificate the earlier lanes and
arms minted.

This module schedules and decides; it does not format.  The colour
Detail builders (``color_region_details``, ``plane_field_details``) sit
with the other observer adapters in :mod:`_production_diagnostics`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .color_attempts import attempt_color_tile
from . import _diagnostic_snapshots as diagnostic_snapshots
from . import _production_diagnostics as production_diagnostics
from .records import certificate_divergence, restore_store
from .color_payload import (
    COLOR_PAYLOAD_POLICY_ID,
    ColorCaptureEvidence,
    ColorRegionSummary,
    color_blocks_from_frontier,
    collect_color_evidence,
)
from .color_field import (
    UPLIFT_ARM_FIELD,
    PlaneFieldConfig,
    PlaneFieldReport,
)
from .color_pool import fully_certified_color_addresses
from .color_refine import (
    ColorForwardRefinement,
    affected_color_patch_ids,
    refine_color_address_once,
)
from .color_stack import UPLIFT_ARM_A4B, StackConfig, force_null_enabled
from .evidence import (
    AttemptStage,
    PayloadArtifact,
    PayloadProduct,
    TileAttemptRecord,
)
from .evidence_blocks import (
    SupersessionDrops,
    TileAttemptView,
    apply_mopup_supersession,
    merge_block_sets,
)
from .fountain_close import close_count_ready, close_volume
from .payload_engine import RecordingLeaf, run_attempts
from .payload_model import EvidenceSource
from .place import place_committed
from .placement.model import AddressResult
from .production import (
    _address_product,
    empty_refine_payload,
)
from .production_refine import _every_span_certified
from .runtime import LaneContext, LaneStageOutput
from .records import certificate_for_close
from .types import (
    AddressProduct,
    Detail,
    Disposition,
    RefineAddressPlan,
    Stage,
    StageDecision,
    SurveyArtifact,
    SurveyProduct,
)


def _window_dependencies(
    result: AddressResult,
    product: AddressProduct,
    windows: tuple[object, ...],
) -> dict[str, tuple[str, ...]]:
    """Carry exact prior-barrier pose lineage into owned color cells."""
    if len(result.placements) != len(product.poses):
        raise ValueError(
            "color payload: address pose count disagrees with placements")
    by_patch = {
        int(patch.patch_id): tuple(sorted(
            set(pose.dependency_certificate_ids)))
        for patch, pose in zip(result.placements, product.poses, strict=True)
    }
    if len(by_patch) != len(result.placements):
        raise ValueError("color payload: address repeats a patch identity")
    try:
        output = {
            window.placement_id:
            tuple(sorted(set(
                by_patch[int(window.patch_id)]
            ).union(window.dependency_certificate_ids)))
            for window in windows
        }
    except KeyError as exc:
        raise ValueError(
            "color payload: window has no placed-patch lineage") from exc
    if len(output) != len(windows):
        raise ValueError(
            "color payload: windows repeat a placement identity")
    return output


def _refine_window_dependencies(
    plan: RefineAddressPlan,
    refinement: ColorForwardRefinement,
    windows: tuple[object, ...],
) -> dict[str, tuple[str, ...]]:
    """v0.42 R-delta lineage: base pose deps UNION adopted refinement deps.

    An R level mints no poses for unadopted placements (they are
    references to durable base-lane records), so window lineage joins the
    base record's committed dependencies, the adopted refinement label
    dependencies, and the delta window's own region lineage.
    """
    base_dependencies = {
        int(row.patch_id): tuple(row.dependency_certificate_ids)
        for row in plan.poses
    }
    refine_dependencies = {
        int(patch_id): dependencies
        for patch_id, dependencies in refinement.patch_dependencies
    }
    output = {
        window.placement_id: tuple(sorted(
            set(base_dependencies.get(int(window.patch_id), ()))
            .union(refine_dependencies.get(int(window.patch_id), ()))
            .union(window.dependency_certificate_ids)
        ))
        for window in windows
    }
    if len(output) != len(windows):
        raise ValueError(
            "color payload: windows repeat a placement identity")
    return output


def _uplift_window_dependencies(
    plan: RefineAddressPlan,
    windows: tuple[object, ...],
) -> dict[str, tuple[str, ...]]:
    """PK4.3 lineage: base pose deps UNION the window's own region deps.

    A supplemental level mints no pose at all (it refines nothing), so
    every placement is a reference to a durable base-lane record and the
    lineage is exactly the refinement case minus the adopted-refinement
    term.
    """
    base_dependencies = {
        int(row.patch_id): tuple(row.dependency_certificate_ids)
        for row in plan.poses
    }
    output = {
        window.placement_id: tuple(sorted(
            set(base_dependencies.get(int(window.patch_id), ()))
            .union(window.dependency_certificate_ids)
        ))
        for window in windows
    }
    if len(output) != len(windows):
        raise ValueError(
            "color payload: windows repeat a placement identity")
    return output


def _emit_refinement_summaries(
    context: LaneContext, refinement: ColorForwardRefinement,
) -> None:
    """Observer-gated per-window §7 refinement audit rows."""
    if not context.observer_enabled:
        return
    for row in refinement.summaries:
        context.observe(
            "pose_refine.window_progress.adapter",
            lambda row=row: context.progress(
                "pose_refine.window_progress",
                details=production_diagnostics
                .color_refinement_details(row),
                snapshot_factory=lambda:
                    diagnostic_snapshots.refinement(row),
            ))
        if not context.observer_enabled:
            break


def _synthetic_base_survey(
    survey_product: SurveyProduct, plan: RefineAddressPlan,
) -> SurveyProduct:
    """Index-ordered base-lane regions behind the R level's survey id.

    ``_address_product`` resolves ``regions[patch.region_index]``
    positionally and stamps ``survey.artifact.survey_id`` into the minted
    address artifact.  The R level's own durable survey is empty (stage
    A), so adopted-pose minting borrows the base lane's durable region
    records — poses cite base regions exactly as mop-up poses do (D7:
    region validation is global) — under the R survey's identity.  Never
    persisted: only the minted address product is.
    """
    indexed = {
        int(row.region_id.rsplit("region-", 1)[1]): row
        for row in plan.regions
    }
    ordered = tuple(indexed[index] for index in range(len(indexed)))
    return SurveyProduct(
        SurveyArtifact(
            survey_product.artifact.survey_id,
            tuple(row.region_id for row in ordered)),
        ordered)


@dataclass(frozen=True, slots=True)
class ProductionColorPayload:
    """Complete color E023b/E023c barrier with automatic selective BP150.

    Ordinary and mop-up levels run generation zero only (v0.42: inline
    refinement removed).  A refinement level R(Lk) runs the color codec
    refinement leaf over the base lane's committed poses and contributes
    an affected-region delta in its own evidence namespace — or nothing.
    A supplemental level U(Lk, arm) (PK4.3) runs the same committed-pose
    domain with one campaign arm FORCED and no pose refinement, bounded
    to the uncertified residue by the per-address retirement law.
    """

    policy_id: ClassVar[str] = COLOR_PAYLOAD_POLICY_ID
    stage: Stage = Stage.PAYLOAD
    # PK-CLEAN: the campaign harness's explicit sweep record, threaded
    # from ITS entry point instead of read from the environment by the
    # arms (``color_stack.StackConfig``).  The production runtime
    # constructs this processor with no argument, so a production decode
    # runs the frozen constants the policy id names — there is no
    # ambient state that could move them.
    stack_config: StackConfig | None = None
    # PLANE-FIELDS W2/W4 (docs/PLANE-FIELDS.md §6.2): the per-plane
    # delta-field dial, threaded exactly like ``stack_config`` above and
    # DEFAULT OFF.  The production runtime constructs this processor with
    # no argument, so an ordinary decode never builds a field, never
    # probes, and never leaves the historical ``PlaneResidual`` seam.
    plane_fields: PlaneFieldConfig | None = None

    def _arm_plane_fields(
        self, arm: str | None,
    ) -> PlaneFieldConfig | None:
        """The plane-field dial THIS lane collects under (W3).

        The supplemental ``field`` arm IS the opt-in: its lane forces the
        dial on for its own collection whatever the global default says,
        because a lane that exists to read the residue through the
        per-plane field would otherwise be an ordinary re-read.  An
        explicitly configured global dial still wins the CONSTANTS — a
        harness that swept them sweeps this lane too — so the arm forces
        only the default when there is nothing to inherit.  Every other
        lane class (ordinary, mop-up, refinement, and the three campaign
        arms) reads the global dial unchanged, which is default OFF and
        therefore the historical ``PlaneResidual`` seam bit for bit.
        """
        if arm == UPLIFT_ARM_FIELD:
            return self.plane_fields or PlaneFieldConfig()
        return self.plane_fields

    def _plane_field_reporter(
        self, context: LaneContext, config: PlaneFieldConfig | None,
    ):
        """The W5 analytics seam, or ``None`` while the dial is off."""
        if config is None:
            return None

        def report(row: PlaneFieldReport) -> None:
            context.progress(
                "payload.plane_fields",
                details=production_diagnostics.plane_field_details(row),
                snapshot_factory=lambda: diagnostic_snapshots.plane_fields(
                    row),
            )

        return report

    def process(
        self,
        context: LaneContext,
        survey_product: SurveyProduct,
        address_product: AddressProduct,
    ) -> LaneStageOutput:
        if context.lane.arm_override is not None:
            return self._uplift_level(context, address_product)
        if context.lane.refine_of is not None:
            return self._refine_level(
                context, survey_product, address_product)
        return self._base_level(context, survey_product, address_product)

    def _uplift_level(
        self,
        context: LaneContext,
        address_product: AddressProduct,
    ) -> LaneStageOutput:
        """PK4.3 supplemental level ``U(Lk, arm)`` — RECEIVE-DESIGN §6.2a.

        An arm that cannot prove universal non-regression is SCHEDULED
        rather than gated.  This leaf is the R level minus pose
        refinement plus one forced arm: it reconstructs the base lane's
        committed poses through the same audited
        :func:`place.place_committed` seam, re-runs the ordinary
        ``collect_color_evidence`` over that domain with
        ``arm_override`` set, and decodes through the ordinary shared
        engine in its OWN evidence namespace.

        THE W3 ``field`` ARM (PLANE-FIELDS §6.2) rides this leaf without
        touching the stack: ``fit_region_stack`` recognizes only
        ``off``/``a3``/``a4b``, so the ladder runs its standing
        configuration and the ONLY difference from an ordinary read is
        the registration seam — ``_arm_plane_fields`` forces the
        per-plane delta field on for this lane's collection.  It is
        scheduled LAST among the arms because it consumes what they
        mint: the field's strongest evidence tier is the certified-tile
        probe, so every certificate an earlier lane added is another
        measurement in the field this one builds.

        WHY IT NEEDS NO GATE.  The per-address retirement law
        (RECEIVE-DESIGN §6.3) is the whole safety argument: the store is
        restored from the accumulated frontier, so
        ``unresolved_streams`` never offers a certified (address,
        stream) to the leaf and a u-lane cannot re-attempt — let alone
        overturn — anything already certified.  Its reachable set is
        exactly the uncertified residue, so its certificate delta is
        non-negative BY CONSTRUCTION.  The pool law does the pruning for
        free: wholly certified regions never do image work (L1) and
        certified-complete windows demote to label rows (L2), so the
        "residue only" domain needs no new law here.

        FORCE-NULL SKIPS IT ENTIRELY.  ``--force-null`` must mean "the
        pre-campaign receiver, exactly"; a supplemental lane exists only
        to run a campaign arm, so with the arms off it has no reason to
        run at all — and running it with the arms off would not be a
        null, it would be an extra committed-pose decode pass the
        pre-campaign receiver never made.  The hatch is read here, ahead
        of every other gate, and the lane commits the empty barrier.
        """
        plan = address_product.transient
        if not isinstance(plan, RefineAddressPlan):
            raise TypeError(
                "production color uplift stage needs RefineAddressPlan")
        arm = context.lane.arm_override
        if arm is None:
            raise ValueError("an uplift level needs an arm override")
        if force_null_enabled():
            return empty_refine_payload(context, address_product)
        # The R leaf's pixel-free pre-gates, SPLIT BY ARM (§6.2a v0.54).
        # Every u-lane needs committed poses and an uncertified residue;
        # only U(a4b) needs a certified FRONTIER, since it conditions on
        # certified SIBLING planes.  U(off)/U(a3) fit from committed
        # furniture, so a capture whose ladder certified NOTHING is the
        # stranding case U(off) is for — v3 refused it, silently.
        # PLANE-FIELDS W3: the ``field`` arm's own dial, forced on here
        # and nowhere else.  There is no CHEAPER pre-gate for it than the
        # three below: whether the field has anything to say is a
        # measurement (anchors and certified-tile probes are both read
        # off pixels), so "no plane would be adopted" cannot be decided
        # pixel-free.  The margin therefore lives where it IS decidable —
        # per region and per plane inside the builder, falling back to
        # the historical ``PlaneResidual`` seam plane by plane
        # (``PlaneFieldBuilder.region_offsets``).
        plane_fields = self._arm_plane_fields(arm)
        needs_frontier = arm == UPLIFT_ARM_A4B
        if (not plan.poses
                or (needs_frontier and not plan.certificates)
                or _every_span_certified(
                    plan, context.spec.layout.cells_yx,
                    fully_certified_color_addresses(
                        plan.certificates, context.spec))):
            return empty_refine_payload(context, address_product)
        base_address = place_committed(
            context.raster, context.spec,
            poses=plan.poses, regions=plan.regions)
        if not base_address.payload_placements:
            return empty_refine_payload(context, address_product)
        context.progress(
            "payload.plan",
            details=(
                Detail("color.codec", context.spec.codec_id),
                Detail("color.streams",
                       ",".join(context.spec.stream_ids)),
                Detail("color.uplift_of", plan.base_lane_id),
                Detail("color.uplift_arm", arm),
                # W3: the lane states its own registration model, so a
                # reader never has to know which arm names imply a field.
                Detail("color.plane_fields", plane_fields is not None),
                Detail("color.committed_poses", len(plan.poses)),
                Detail("color.placements",
                       len(base_address.payload_placements)),
                Detail("color.prior_certificates",
                       len(plan.certificates)),
            ),
        )

        def report_region(row: ColorRegionSummary) -> None:
            context.progress(
                "payload.region",
                details=production_diagnostics.color_region_details(row))

        source = EvidenceSource(
            context.capture.source_sha256,
            context.lane.evidence_lane_id)
        current = collect_color_evidence(
            context.raster,
            source,
            base_address,
            context.spec,
            certificates=plan.certificates,
            region_progress=report_region,
            arm_override=arm,
            stack_config=self.stack_config,
            plane_fields=plane_fields,
            plane_field_progress=self._plane_field_reporter(
                context, plane_fields),
        )
        dependencies = _uplift_window_dependencies(plan, current.windows)
        return self._finish(
            context, current, dependencies,
            address_id=address_product.artifact.address_id,
            extra_details=(Detail("color.uplift_arm", arm),),
        )

    def _base_level(
        self,
        context: LaneContext,
        survey_product: SurveyProduct,
        address_product: AddressProduct,
    ) -> LaneStageOutput:
        del survey_product
        if not isinstance(address_product.transient, AddressResult):
            raise TypeError(
                "production color payload stage needs AddressResult")
        result = address_product.transient
        source = EvidenceSource(
            context.capture.source_sha256,
            context.lane.evidence_lane_id)
        context.progress(
            "payload.plan",
            details=(
                Detail("color.codec", context.spec.codec_id),
                Detail("color.streams",
                       ",".join(context.spec.stream_ids)),
                Detail("color.placements",
                       len(result.payload_placements)),
                Detail("color.placements_quarantined",
                       len(result.quarantined_patch_ids)),
                Detail("color.prior_certificates",
                       len(context.evidence.certificates)),
            ),
        )

        def report_region(row: ColorRegionSummary) -> None:
            context.progress(
                "payload.region",
                details=production_diagnostics.color_region_details(row),
            )

        generation0 = collect_color_evidence(
            context.raster,
            source,
            result,
            context.spec,
            certificates=context.evidence.certificates,
            region_progress=report_region,
            stack_config=self.stack_config,
            plane_fields=self.plane_fields,
            plane_field_progress=self._plane_field_reporter(
                context, self.plane_fields),
        )
        dependencies = _window_dependencies(
            result, address_product, generation0.windows)
        return self._finish(
            context, generation0, dependencies,
            address_id=address_product.artifact.address_id,
        )

    def _refine_level(
        self,
        context: LaneContext,
        survey_product: SurveyProduct,
        address_product: AddressProduct,
    ) -> LaneStageOutput:
        """v0.42 R(Lk) color codec leaf (stage C).

        The committed-pose domain is the SHARED ``place.place_committed``
        reconstruction (K parity): every committed base pose re-samples
        and re-audits deterministically on the re-derived base aperture,
        so the window inventory is the base lane's audited cell set —
        never a window-rectangle superset, whose off-support cells
        crashed the R delta's ``collect_color_evidence`` sampling on
        partial-coverage scrap material.  Pixel-free pre-gates run first
        (mirroring the K leaf): with no committed poses, no certificate
        frontier, or every committed window span fully certified, the
        lazy raster stand-in never materializes.  Adopted windows re-fit
        exactly their affected (region, page) groups through the ordinary
        ``collect_color_evidence`` seam — the R delta — and the adopted
        refined poses are minted under the R lane's own id namespace via
        the payload replacement-address barrier.  No adoptions: empty
        delta, cheap barrier.
        """
        plan = address_product.transient
        if not isinstance(plan, RefineAddressPlan):
            raise TypeError(
                "production color refinement stage needs RefineAddressPlan")
        if (not plan.poses or not plan.certificates
                or _every_span_certified(
                    plan, context.spec.layout.cells_yx,
                    fully_certified_color_addresses(
                        plan.certificates, context.spec))):
            # Pixel-free (the K leaf's exact-superset argument): nothing
            # to refine, nothing to label from, or nothing left to gain —
            # the stage-A silent empty delta.
            return empty_refine_payload(context, address_product)
        base_address = place_committed(
            context.raster, context.spec,
            poses=plan.poses, regions=plan.regions)
        if not base_address.payload_placements:
            return empty_refine_payload(context, address_product)
        context.progress(
            "payload.plan",
            details=(
                Detail("color.codec", context.spec.codec_id),
                Detail("color.streams",
                       ",".join(context.spec.stream_ids)),
                Detail("color.refine_of", plan.base_lane_id),
                Detail("color.committed_poses", len(plan.poses)),
                Detail("color.placements",
                       len(base_address.payload_placements)),
                Detail("color.prior_certificates",
                       len(plan.certificates)),
            ),
        )
        refinement = refine_color_address_once(
            context.raster, base_address, None, context.spec,
            plan.certificates)
        _emit_refinement_summaries(context, refinement)
        refinement_details = (
            Detail("color.refinement_eligible", refinement.eligible),
            Detail("color.refinement_adopted", refinement.adopted),
        )
        if not refinement.adopted:
            # No adoptions => empty delta, cheap barrier: unaffected
            # windows contribute NOTHING here — their base-lane evidence
            # stands (own namespaces; only certificates cross lanes).
            context.progress(
                "payload.complete",
                details=(
                    Detail("color.blocks", 0),
                    Detail("color.blocks_persisted", 0),
                    Detail("color.certificates", 0),
                ) + refinement_details,
            )
            return empty_refine_payload(context, address_product)
        adopted_ids = tuple(
            row.patch_id for row in refinement.summaries
            if row.metrics.adopted)
        included = affected_color_patch_ids(refinement.address, adopted_ids)
        adopted = frozenset(int(value) for value in adopted_ids)
        minted_result = AddressResult(
            tuple(
                patch for patch in refinement.address.payload_placements
                if int(patch.patch_id) in adopted),
            (), (),
            refinement.address.region_states, 0)
        replacement = _address_product(
            context, _synthetic_base_survey(survey_product, plan),
            minted_result,
            patch_dependency_overrides=refinement.patch_dependencies,
        )
        context.progress(
            "address.final",
            details=(Detail("address.refined", True),
                     Detail("address.placements",
                            len(minted_result.placements))),
            snapshot_factory=lambda: diagnostic_snapshots.address(
                replacement),
        )
        source = EvidenceSource(
            context.capture.source_sha256,
            context.lane.evidence_lane_id)

        def report_region(row: ColorRegionSummary) -> None:
            context.progress(
                "payload.region",
                details=production_diagnostics.color_region_details(row),
            )

        delta = collect_color_evidence(
            context.raster,
            source,
            refinement.address,
            context.spec,
            certificates=plan.certificates,
            region_progress=report_region,
            included_patch_ids=included,
            stack_config=self.stack_config,
            plane_fields=self.plane_fields,
            plane_field_progress=self._plane_field_reporter(
                context, self.plane_fields),
        )
        dependencies = _refine_window_dependencies(
            plan, refinement, delta.windows)
        return self._finish(
            context, delta, dependencies,
            address_id=replacement.artifact.address_id,
            replacement=replacement,
            extra_details=refinement_details,
        )

    def _finish(
        self,
        context: LaneContext,
        current: ColorCaptureEvidence,
        dependencies: dict[str, tuple[str, ...]],
        *,
        address_id: str,
        replacement: AddressProduct | None = None,
        extra_details: tuple[Detail, ...] = (),
    ) -> LaneStageOutput:
        """Shared barrier tail: owner freeze report, blocks, attempts,
        selective BP150 retry, divergence audit, and the typed product."""
        store = restore_store(context.spec, context.evidence.certificates)
        fully_certified_addresses = frozenset(
            address for address in {
                (row.page, *row.tile_yx)
                for row in context.evidence.certificates}
            if address in store
        )
        owner_cells = sum(
            page.cells_yx.shape[0] for page in current.pages)
        context.progress(
            "payload.owner_frozen",
            details=(
                Detail("color.evidence_kind", current.evidence_kind),
                Detail("color.pages", len(current.pages)),
                Detail("color.owner_cells", owner_cells),
                Detail("color.needed_owner_cells", owner_cells),
                Detail("color.windows", len(current.windows)),
                Detail("color.pruned_certified_addresses",
                       len(fully_certified_addresses)),
            ),
            snapshot_factory=lambda: diagnostic_snapshots.payload(
                current, context.spec),
        )
        new_blocks = color_blocks_from_frontier(current, dependencies)
        mopup_drops = SupersessionDrops(0, 0)
        if (context.lane.mopup_of is not None
                and context.evidence.own_committed_blocks):
            # v0.33 D5: a colliding key becomes the committed-
            # verbatim-plus-novel superset; base owners win cells.  The
            # drop tally (dropped re-observations + winner flips) is the
            # two-view consistency canary (2026-08-02 ruling): counted
            # and surfaced, never gated.
            new_blocks, mopup_drops = (
                apply_mopup_supersession(
                    new_blocks, context.evidence.own_committed_blocks))
        frontier_blocks = merge_block_sets(
            context.evidence.prior_capture_blocks, new_blocks)
        if any(row.lane_id != context.lane.evidence_lane_id
               for row in frontier_blocks):
            raise ValueError(
                "color payload frontier contains another lane")
        if any(row.kind != current.evidence_kind for row in frontier_blocks):
            raise ValueError(
                "color payload frontier contains another evidence kind")

        context.progress(
            "payload.blocks_built",
            details=(
                Detail("color.evidence_kind", current.evidence_kind),
                Detail("color.blocks", len(new_blocks)),
                Detail("color.frontier_blocks", len(frontier_blocks)),
            ),
        )

        # Attempt ledgers are invocation-local (kiss): resumes re-attempt
        # uncertified streams and CRC gates correctness.  The schedule, leaf
        # bookkeeping, and attempt-event emission are all shared with K; the
        # decode closure is the only color-specific piece.
        def color_decode(view, stream_id, stage):
            outcome = attempt_color_tile(
                view, context.spec, stream_id, stage,
                source_sha256=context.capture.source_sha256,
                lane_id=context.lane.evidence_lane_id)
            return outcome.record, outcome.certificate

        def live_attempt_snapshot(
            row: TileAttemptRecord, evidence: TileAttemptView,
        ) -> object:
            return production_diagnostics.attempt_snapshot(
                row, evidence, evidence.components, context.spec)

        attempt_ordinal = [0]
        attempt_progress = production_diagnostics.install_adapter(
            context, "payload.attempt.adapter.install",
            lambda: production_diagnostics.attempt_progress_callback(
                context, "payload.attempt", attempt_ordinal,
                live_attempt_snapshot))
        retry_attempt_progress = production_diagnostics.install_adapter(
            context, "payload.retry_attempt.adapter.install",
            lambda: production_diagnostics.attempt_progress_callback(
                context, "payload.retry_attempt", attempt_ordinal,
                live_attempt_snapshot))
        leaf = RecordingLeaf(
            store, color_decode,
            attempt_progress=attempt_progress,
            retry_attempt_progress=retry_attempt_progress)
        retry_open_progress = production_diagnostics.install_adapter(
            context, "payload.retry_open.adapter.install",
            lambda: production_diagnostics.retry_open_callback(context))
        preclose_attempted = [False]

        def preclose() -> bool:
            """Advisory pre-close (same shape as K, Phase 3.3): the
            emptiness short-circuit runs BEFORE any conversion, so a
            certificate-less consult converts nothing; the engine
            consults at most once per run.  The runtime barrier stays
            the sole authoritative durable close."""
            if not leaf.certificates:
                return False
            close_inputs = tuple(
                certificate_for_close(row, context.spec)
                for row in (*context.evidence.certificates,
                            *leaf.certificates)
            )
            if not close_count_ready(close_inputs, context.spec):
                return False
            preclose_attempted[0] = True
            return close_volume(close_inputs, context.spec).status != "open"

        engine_run = run_attempts(
            new_blocks,
            frontier_blocks,
            lane_id=context.lane.evidence_lane_id,
            leaf=leaf,
            preclose=None if context.defer_fountain_close else preclose,
            retry_open=retry_open_progress,
        )
        attempts = list(leaf.attempts)
        certificates = list(leaf.certificates)
        retry_frontier = engine_run.retry_frontier
        terminal_close = engine_run.terminal_close
        preclose_flag = preclose_attempted[0]
        ordinary = tuple(
            row for row in attempts
            if row.stage is not AttemptStage.RETRY150)
        retries = tuple(
            row for row in attempts
            if row.stage is AttemptStage.RETRY150)
        ordinary_certificates = tuple(
            row for row in certificates
            if row not in leaf.retry_certificates)
        # The max60 -> retry150 boundary is a forced diagnostic milestone
        # (RECEIVE-DESIGN §10.4): every payload lane reports it, mirroring
        # ProductionPayload._retry exactly.  "eligible" is the engine's
        # selected retry frontier; "attempted" counts recorded retry rows.
        retry_report = {
            "noop": not retries,
            "frontier": len(retry_frontier),
            "eligible": len(retry_frontier),
            "attempted": len(retries),
            "certified": len(leaf.retry_certificates),
            "total_certified": len(store),
        }
        if context.observer_enabled:
            context.progress(
                "payload.retry_complete",
                details=production_diagnostics.retry_summary_details(
                    ordinary, ordinary_certificates,
                    retries, leaf.retry_certificates, retry_report),
            )

        # Retention follows the ordinary K/live-frontier rule.  The barrier
        # removes only addresses for which every required stream certified.
        durable_blocks = new_blocks

        # Divergence is observational and never gates certification.  Audit
        # certificates minted by this barrier once against their publication
        # frontier.  Prior certified streams are payload-inert: a later scan
        # does not reopen them merely to create another observational pair.
        if certificates:
            published_frontier = merge_block_sets(
                context.evidence.prior_capture_blocks,
                durable_blocks,
            )
            divergences = certificate_divergence(
                published_frontier,
                certificates,
                context.spec,
            )
        else:
            divergences = ()

        prefix = f"{context.capture.source_sha256}/{context.lane.lane_id}"
        artifact = PayloadArtifact(
            f"{prefix}/payload",
            address_id,
            tuple(row.certificate_id for row in certificates),
            n_blocks=len(durable_blocks),
            n_attempts=len(attempts),
            n_divergences=len(divergences),
        )
        product = PayloadProduct(
            artifact,
            durable_blocks,
            tuple(attempts),
            tuple(certificates),
            divergences,
            mopup_dropped_observations=mopup_drops.dropped,
            mopup_winner_flips=mopup_drops.winner_flips,
        )
        context.progress(
            "payload.complete",
            details=(
                Detail("color.blocks", len(new_blocks)),
                Detail("color.blocks_persisted", len(durable_blocks)),
                Detail("color.scan_union_attempts", len(ordinary)),
                Detail("color.retry150_frontier", len(retry_frontier)),
                Detail("color.retry150_attempts", len(retries)),
                Detail("color.certificates", len(certificates)),
                Detail("color.divergences", len(divergences)),
                Detail("color.preclose_attempted", preclose_flag),
                Detail("color.terminal_close", terminal_close),
                Detail("color.mopup_dropped_observations",
                       mopup_drops.dropped),
                Detail("color.mopup_winner_flips",
                       mopup_drops.winner_flips),
                Detail("color.unresolved_streams", sum(
                    len(leaf.unresolved_streams(block.address))
                    for block in new_blocks)),
            ) + extra_details,
        )
        return LaneStageOutput(
            StageDecision(Stage.PAYLOAD, Disposition.COMPLETE),
            product,
            replacement_address=replacement,
        )


__all__ = ["ProductionColorPayload"]

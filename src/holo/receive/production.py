"""Production E021 -> E022 -> E023b adapters for the E023c runtime.

The numerical stages remain independently callable and independently
qualified.  These adapters do only orchestration and typed barrier
materialisation: complete survey, complete placement, scan-final ownership,
automatic scan/union attempts, mandatory selective evidence-addressed
retry150, and verified fountain close.

This module is the survey/address home and the pipeline composition root;
the K payload driver lives in :mod:`production_payload`, the fountain-close
stage in :mod:`production_close`, and the color driver in
:mod:`production_color` (Phase 4 file split, RECEIVE-DESIGN v0.38).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Callable, ClassVar

import numpy as np

if TYPE_CHECKING:
    from ..format.descriptor import FormatSpec

from ..format.profiles import Family
from . import _diagnostic_snapshots as diagnostic_snapshots
from . import _production_diagnostics as production_diagnostics
from ._bch_quarantine import conflict_records
from .place import (
    FormatHypothesisRejected,
    PlacementConfig,
    _lower_hint_attempt_count,
    mopup_survey,
    place_mopup,
    place_survey,
)
from .placement.model import (
    MAX_LOWER_HINTS,
    AddressResult,
    PlacementHint,
    PlacedSegment,
)
from .placement.defaults import (
    PROVISIONAL_V1_PLACEMENT_POLICY,
    V1_PRODUCTION_QUALIFICATION_NOTES,
)
from .placement.policy import PlacementBudgetPolicy, PlacementDomainEnvelope
from .placement.reference import rotation_affine
from .production_close import ProductionClose
from .session_validation import validate_address_quarantine
from .runtime import (
    LaneAlgorithms, LaneContext, LaneStageOutput,
    ReceivePipeline, ReceiveRequest, ReceiverQualificationStatus,
)
from .survey import PayloadSurvey, SupportMask, survey_raster
from .types import (
    AddressArtifact,
    AddressProduct,
    Detail, Disposition,
    LosingHypothesis,
    ParkedWindowRecord,
    PoseProposal,
    PoseRecord,
    RefineAddressPlan,
    Stage,
    StageDecision,
    SupportRun,
    SurveyArtifact,
    SurveyProduct,
    SurveyRegionRecord,
)


def _survey_preview(raster: object, max_side: int = 512) -> dict[str, object]:
    """Decimated capture luma for pane A's underlay (§10.3.3 preview).

    Block-mean decimation in bounded row strips — never a full-resolution
    materialization.  Built lazily inside the survey snapshot factory, so a
    headless or scalar-only run never pays for it.
    """
    height, width = raster.shape
    decim = max(1, -(-max(height, width) // max_side))
    out_h = max(1, height // decim)
    out_w = max(1, width // decim)
    strip_rows = 64 * decim
    strips: list[np.ndarray] = []
    for y0 in range(0, out_h * decim, strip_rows):
        y1 = min(y0 + strip_rows, out_h * decim)
        block = np.asarray(
            raster.crop_luma(y0, y1, 0, out_w * decim), np.float32)
        rows = (y1 - y0) // decim
        strips.append(block[:rows * decim].reshape(
            rows, decim, out_w, decim).mean(axis=(1, 3), dtype=np.float32))
    pixels = (np.concatenate(strips, axis=0) if strips
              else np.zeros((1, 1), np.float32))
    return {"pixels": pixels, "decimation": int(decim)}


def _runs(mask: SupportMask) -> tuple[SupportRun, ...]:
    flat = np.asarray(mask.cells, bool).ravel()
    padded = np.concatenate((np.asarray([False]), flat, np.asarray([False])))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return tuple(SupportRun(int(start), int(end - start))
                 for start, end in edges.reshape(-1, 2))


@dataclass(frozen=True, slots=True)
class ProductionSurvey:
    policy_id: ClassVar[str] = "holo/e021-survey/paperholo-e021-v1"
    stage: Stage = Stage.SURVEY

    def process(self, context: LaneContext) -> LaneStageOutput:
        if context.lane.mopup_of is not None:
            # v0.33 M-level: no pixel survey.  The address stage consumes
            # durable parked windows whose poses reference the base
            # level's committed regions (region validation is global).
            prefix = (f"{context.capture.source_sha256}/"
                      f"{context.lane.lane_id}")
            artifact = SurveyArtifact(f"{prefix}/survey", ())
            context.progress(
                "survey.complete",
                details=(Detail("survey.regions", 0),
                         Detail("survey.mopup_of", context.lane.mopup_of)))
            return LaneStageOutput(
                StageDecision(Stage.SURVEY, Disposition.COMPLETE),
                SurveyProduct(artifact, ()))
        if (context.lane.refine_of is not None
                or context.lane.uplift_of is not None):
            # v0.42 R-level / v0.51 U-level: empty mint (M precedent).
            # The address stage consumes the base lane's committed
            # poses/regions via the evidence context; no pixel survey, no
            # raster read.  The two `survey.*` details name the class
            # exactly — a supplemental level reports its base AND its
            # forced arm, so no reader has to infer either.
            prefix = (f"{context.capture.source_sha256}/"
                      f"{context.lane.lane_id}")
            artifact = SurveyArtifact(f"{prefix}/survey", ())
            context.progress(
                "survey.complete",
                details=(Detail("survey.regions", 0),
                         Detail("survey.refine_of", context.lane.refine_of),
                         Detail("survey.uplift_of", context.lane.uplift_of),
                         Detail("survey.uplift_arm",
                                context.lane.arm_override)))
            return LaneStageOutput(
                StageDecision(Stage.SURVEY, Disposition.COMPLETE),
                SurveyProduct(artifact, ()))
        survey = survey_raster(context.raster)  # type: ignore[arg-type]
        prefix = f"{context.capture.source_sha256}/{context.lane.lane_id}"
        regions = tuple(
            SurveyRegionRecord(
                region_id=f"{prefix}/region-{index}",
                capture_id=context.capture.source_sha256,
                lane_id=context.lane.lane_id,
                origin_yx=region.support.origin_yx,
                extent_yx=region.support.extent_px,
                support_step_px=region.support.step_px,
                support_shape_yx=tuple(region.support.cells.shape),
                support_runs=_runs(region.support),
                area_mm2=float(region.area_mm2),
                median_tensor_score=float(region.median_tensor_score),
            )
            for index, region in enumerate(survey.regions)
        )
        artifact = SurveyArtifact(
            f"{prefix}/survey", tuple(row.region_id for row in regions))
        context.progress(
            "survey.complete",
            details=(Detail("survey.regions", len(regions)),
                     Detail("survey.c_dots", survey.c_dots)),
            snapshot_factory=lambda: diagnostic_snapshots.survey(
                survey, regions,
                preview=_survey_preview(context.raster)),
        )
        decision = StageDecision(Stage.SURVEY, Disposition.COMPLETE)
        return LaneStageOutput(
            decision, SurveyProduct(artifact, regions, transient=survey))


def _native_hint_box(context: LaneContext,
                     box: tuple[float, float, float, float]
                     ) -> tuple[tuple[int, int], tuple[int, int]]:
    """Conservatively enclose a view-pixel half-open box in native pixels."""
    scale = Fraction(
        context.lane.native_per_view_num,
        context.lane.native_per_view_den)
    y0 = max(0, math.floor(Fraction(str(box[0])) * scale))
    x0 = max(0, math.floor(Fraction(str(box[1])) * scale))
    y1 = min(context.capture.shape_yx[0],
             math.ceil(Fraction(str(box[2])) * scale))
    x1 = min(context.capture.shape_yx[1],
             math.ceil(Fraction(str(box[3])) * scale))
    if y1 <= y0 or x1 <= x0:
        raise ValueError("placement hint does not overlap the native capture")
    return (y0, x0), (y1 - y0, x1 - x0)


def _lane_hint_box(context: LaneContext, origin: tuple[int, int],
                   extent: tuple[int, int]
                   ) -> tuple[float, float, float, float]:
    scale = context.lane.native_per_view_num / context.lane.native_per_view_den
    return (origin[0] / scale, origin[1] / scale,
            (origin[0] + extent[0]) / scale,
            (origin[1] + extent[1]) / scale)


def _lower_hints(context: LaneContext) -> tuple[PlacementHint, ...]:
    rows: list[PlacementHint] = []
    for proposal in context.evidence.proposals:
        affine = context.native_to_lane_affine(
            np.asarray(proposal.native_affine, np.float64).reshape(2, 3))
        rows.append(PlacementHint(
            proposal.proposal_id, proposal.page, proposal.rot90,
            tuple(float(value) for value in affine.ravel()),
            _lane_hint_box(
                context, proposal.native_search_origin_yx,
                proposal.native_search_extent_yx),
            tuple(float(value) for value in context.native_to_lane_points(
                np.asarray([proposal.native_pose_origin_yx], np.float64)
            )[0]),
            kind="accepted"))
    for loser in context.evidence.losers:
        affine = context.native_to_lane_affine(
            np.asarray(loser.native_affine, np.float64).reshape(2, 3))
        rows.append(PlacementHint(
            loser.hypothesis_id, loser.page, loser.rot90,
            tuple(float(value) for value in affine.ravel()),
            _lane_hint_box(
                context, loser.native_search_origin_yx,
                loser.native_search_extent_yx),
            tuple(float(value) for value in context.native_to_lane_points(
                np.asarray([loser.native_pose_origin_yx], np.float64)
            )[0]),
            kind="runner_up",
            search_mismatch=loser.mismatch,
            validation_mismatch=loser.validation))
    return tuple(rows)


def _page_to_view_affine(segment: PlacedSegment) -> np.ndarray:
    rotation, translation = rotation_affine(
        segment.rot_k, segment.segment.window.shape_yx_cells)
    page_jacobian = segment.segment.pose.matrix() @ np.linalg.inv(rotation)
    page_offset = translation + np.asarray(segment.page_origin_yx, np.float64)
    scan_offset = (
        np.asarray(segment.segment.pose.origin_yx, np.float64)
        - page_jacobian @ page_offset)
    return np.column_stack((page_jacobian, scan_offset))


def _address_product(
    context: LaneContext,
    survey: SurveyProduct,
    result: AddressResult,
    *,
    patch_dependency_overrides: tuple[
        tuple[int, tuple[str, ...]], ...
    ] = (),
) -> AddressProduct:
    prefix = f"{context.capture.source_sha256}/{context.lane.lane_id}"
    regions = tuple(row.region_id for row in survey.regions)
    if context.lane.mopup_of is not None and not regions:
        # v0.33 M-level: poses cite the base level's durable regions
        # (region validation is global); rebuild the index-ordered map.
        indexed = {
            int(row.region_id.rsplit("region-", 1)[1]): row.region_id
            for row in context.evidence.regions}
        regions = tuple(
            indexed[index] for index in range(len(indexed)))
    dependencies = {
        row.proposal_id: row.dependency_certificate_ids
        for row in context.evidence.proposals}
    dependencies.update({
        row.hypothesis_id: row.dependency_certificate_ids
        for row in context.evidence.losers})
    inherited_ids = {
        patch.inherited_hint_id
        for patch in result.placements
        if patch.inherited_hint_id is not None
    }
    unknown_inherited_ids = inherited_ids.difference(dependencies)
    if unknown_inherited_ids:
        raise ValueError(
            "placed patch inherits an unknown lower-scale hint: "
            + ", ".join(sorted(unknown_inherited_ids)))
    component_dependencies: dict[tuple[int, int], tuple[str, ...]] = {}
    for patch in result.placements:
        inherited = patch.inherited_hint_id
        if inherited is not None and patch.component >= 0:
            component_dependencies[(patch.region_index, patch.component)] = (
                dependencies[inherited])
    override_dependencies = {
        int(patch_id): tuple(sorted(set(values)))
        for patch_id, values in patch_dependency_overrides
    }
    if len(override_dependencies) != len(patch_dependency_overrides):
        raise ValueError("refinement dependencies repeat a patch")

    poses: list[PoseRecord] = []
    patch_dependencies: dict[int, tuple[str, ...]] = {}
    for patch in result.placements:
        inherited = patch.inherited_hint_id
        deps = () if inherited is None else dependencies[inherited]
        if patch.component >= 0:
            deps = component_dependencies.get(
                (patch.region_index, patch.component), deps)
        deps = tuple(sorted(set(deps).union(
            override_dependencies.get(patch.patch_id, ()))))
        patch_dependencies[patch.patch_id] = deps
        segment = patch.segment
        pose_id = f"{prefix}/patch-{patch.patch_id}/pose"
        native = context.lane_to_native_affine(
            _page_to_view_affine(segment))
        fitted = segment.segment
        poses.append(PoseRecord(
            pose_id=pose_id,
            capture_id=context.capture.source_sha256,
            lane_id=context.lane.lane_id,
            region_id=regions[patch.region_index],
            patch_id=patch.patch_id,
            placement_outcome=(
                "redundant" if patch.redundant else "accepted"),
            page=patch.candidate.page,
            cell_origin_yx=segment.page_origin_yx,
            native_affine=tuple(float(value) for value in native.ravel()),
            rot90=segment.rot_k,
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
                float(value) for value in
                np.asarray(fitted.pose.jacobian_yx, np.float64).ravel()),
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
    proposals: list[PoseProposal] = []
    for hint in result.continuation_hints:
        if hint.kind != "accepted":
            continue
        patch_id = hint.patch_id
        if patch_id is None:
            raise ValueError("accepted continuation hint has no patch identity")
        native = context.lane_to_native_affine(hint.affine())
        origin, extent = _native_hint_box(context, hint.scan_bbox_yxyx)
        proposals.append(PoseProposal(
            proposal_id=hint.hint_id,
            capture_id=context.capture.source_sha256,
            source_lane_id=context.lane.lane_id,
            page=hint.page,
            rot90=hint.rot_k,
            native_search_origin_yx=origin,
            native_search_extent_yx=extent,
            native_pose_origin_yx=tuple(float(value) for value in (
                context.lane_to_native_points(np.asarray(
                    [hint.scan_pose_origin_yx], np.float64))[0]
            )),
            native_affine=tuple(float(value) for value in native.ravel()),
            dependency_certificate_ids=patch_dependencies.get(patch_id, ()),
        ))

    unresolved = {row.patch_id: row for row in result.unresolved}
    losers: list[LosingHypothesis] = []
    for hint in result.continuation_hints:
        if hint.kind != "runner_up":
            continue
        patch_id = hint.patch_id
        if patch_id is None:
            raise ValueError("runner-up continuation hint has no patch identity")
        row = unresolved.get(patch_id)
        if row is None or row.best is None:
            continue
        native = context.lane_to_native_affine(hint.affine())
        origin, extent = _native_hint_box(context, hint.scan_bbox_yxyx)
        losers.append(LosingHypothesis(
            hypothesis_id=hint.hint_id,
            capture_id=context.capture.source_sha256,
            lane_id=context.lane.lane_id,
            region_id=regions[row.region_index],
            page=row.best.page,
            page_origin_yx=row.best.origin_yx,
            rot90=row.best.rot_k,
            native_search_origin_yx=origin,
            native_search_extent_yx=extent,
            native_pose_origin_yx=tuple(float(value) for value in (
                context.lane_to_native_points(np.asarray(
                    [hint.scan_pose_origin_yx], np.float64))[0]
            )),
            native_affine=tuple(float(value) for value in native.ravel()),
            mismatch=row.best.search_mismatch,
            validation=row.best.validation_mismatch,
            search_support=row.best.search_support,
            validation_support=row.best.validation_support,
            dependency_certificate_ids=(),
        ))
    parked_rows: list[ParkedWindowRecord] = []
    for parked in result.parked_windows:
        segment = parked.segment
        pose = segment.pose
        parked_rows.append(ParkedWindowRecord(
            parked_id=f"{prefix}/parked-{parked.patch_id}",
            capture_id=context.capture.source_sha256,
            lane_id=context.lane.lane_id,
            region_id=regions[parked.region_index],
            region_index=int(parked.region_index),
            window_id=int(parked.window.window_id),
            origin_yx_px=tuple(
                int(value) for value in parked.window.origin_yx_px),
            shape_yx_cells=tuple(
                int(value) for value in parked.window.shape_yx_cells),
            depth=int(parked.window.depth),
            support_estimate=float(parked.window.support_estimate),
            pose_origin_yx=tuple(
                float(value) for value in pose.origin_yx),
            pose_jacobian=tuple(
                float(value) for value in
                np.asarray(pose.jacobian_yx, np.float64).ravel()),
            pose_phase_yx=tuple(
                float(value) for value in pose.phase_yx),
            pose_pitch_px=float(pose.pitch_px),
            pose_angle_deg=float(pose.angle_deg),
            support_cells=int(segment.support_cells),
            phase_contrast=float(segment.phase_contrast),
            pitch_yx_px=tuple(
                float(value) for value in segment.pitch_yx_px),
            orthogonality_error_deg=float(
                segment.orthogonality_error_deg),
            patch_ordinal=int(parked.patch_id),
            attempted_routes=parked.attempted_routes,
            cell_pitch_px=float(parked.cell_pitch_px),
            lattice_f=parked.lattice_f,
        ))
    artifact = AddressArtifact(
        f"{prefix}/address", survey.artifact.survey_id,
        tuple(row.pose_id for row in poses),
        tuple(row.proposal_id for row in proposals),
        tuple(row.hypothesis_id for row in losers),
        conflict_records(result.words),
        parked_ids=tuple(row.parked_id for row in parked_rows),
    )
    validate_address_quarantine(artifact, poses)
    return AddressProduct(
        artifact, tuple(poses), tuple(proposals), tuple(losers),
        parked=tuple(parked_rows),
        transient=result)


def empty_refine_payload(
    context: LaneContext, address_product: AddressProduct,
) -> LaneStageOutput:
    """v0.42 R-level payload, stage-A shape: the empty delta.

    Until the codec refinement leaves land (stage B/C), an R-level payload
    contributes NOTHING: no blocks, no attempts, no certificates — the
    barrier commits cheaply and unaffected regions' base evidence stands.
    Deliberately silent (no ``payload.*`` milestones): an empty delta is
    not a payload run, and the mandatory max60->retry150 boundary applies
    only to lanes that attempt.
    """
    from .types import PayloadArtifact, PayloadProduct

    if not isinstance(address_product.transient, RefineAddressPlan):
        raise TypeError("refinement payload stage needs RefineAddressPlan")
    prefix = f"{context.capture.source_sha256}/{context.lane.lane_id}"
    artifact = PayloadArtifact(
        payload_id=f"{prefix}/payload",
        address_id=address_product.artifact.address_id)
    return LaneStageOutput(
        StageDecision(Stage.PAYLOAD, Disposition.COMPLETE),
        PayloadProduct(
            artifact=artifact, blocks=(), attempts=(),
            certificates=(), divergences=()))


def _address_adapter_callbacks(
    context: LaneContext, survey_source: Callable[[], PayloadSurvey],
) -> tuple[Callable[..., None] | None,
           Callable[..., None] | None,
           Callable[..., None] | None]:
    """Install the shared address diagnostic adapters (or a None triple)."""
    callbacks = production_diagnostics.install_adapter(
        context, "address.adapters",
        lambda: production_diagnostics.address_callbacks(
            context, survey_source))
    if callbacks is None:
        callbacks = (None, None, None)
    return callbacks


def _emit_address_final(
    context: LaneContext, result: AddressResult, product: AddressProduct,
) -> None:
    """The one ``address.final`` emission (identical on every branch)."""
    context.progress(
        "address.final",
        details=(Detail("address.placements", len(result.placements)),
                 Detail("address.unresolved", len(result.unresolved)),
                 Detail("address.words", len(result.words)),
                 Detail("address.words_certified",
                        sum(row.certified for row in result.words)),
                 Detail("address.words_conflicting",
                        sum(row.conflict for row in result.words)),
                 Detail("address.placements_quarantined",
                        len(result.quarantined_patch_ids)),
                 Detail("address.placements_promoted",
                        len(result.payload_placements)),
                 Detail("address.hypotheses",
                        result.hypotheses_evaluated)),
        snapshot_factory=lambda: diagnostic_snapshots.address(product),
    )


@dataclass(frozen=True, slots=True)
class ProductionAddress:
    budget_policy: PlacementBudgetPolicy
    page_hypotheses: tuple[int, ...] | None = None
    config: PlacementConfig = PlacementConfig()
    domain_envelope: PlacementDomainEnvelope | None = None
    stage: Stage = Stage.ADDRESS

    def __post_init__(self) -> None:
        if type(self.budget_policy) is not PlacementBudgetPolicy:
            raise TypeError(
                "production address needs a declarative placement policy")
        if type(self.config) is not PlacementConfig:
            raise TypeError("production address needs an exact PlacementConfig")
        if (self.domain_envelope is not None
                and type(self.domain_envelope) is not PlacementDomainEnvelope):
            raise TypeError(
                "production address needs an exact discovery domain envelope")

    @property
    def policy_id(self) -> str:
        """Hand-bumped semantic identity (ground rule G2).

        PlacementConfig fields are tuning data, not identity — the v3 form
        repr-hashed all 27 of them, so a 1e-9 constant edit invalidated
        state while an algorithm rewrite did not. Bump the literal here by
        hand when address SEMANTICS change.
        """
        parts = ["holo/production-address/v6-phased-schedule",
                 self.budget_policy.policy_id]
        if self.domain_envelope is not None:
            parts.append(self.domain_envelope.policy_id)
        return "/".join(parts)

    def route_domain_report(
        self, spec: FormatSpec, pages: tuple[int, ...],
    ) -> dict[str, object]:
        """RECEIVE-DESIGN §5.3 exposure: resolved domains and floors.

        The declared per-window route domains and per-parity support floors
        for this request, resolved exactly as the runtime resolves them
        (lower at the full 8-hint portfolio — the route's maximum declared
        domain).  Numbers only; prose tables are explanation, never the
        source of numerical truth.
        """
        budgets, word = self.budget_policy.resolve(
            spec, pages, _lower_hint_attempt_count(MAX_LOWER_HINTS),
            self.config, domain_envelope=self.domain_envelope)
        routes: dict[str, object] = {}
        for name, budget in (("cold", budgets.cold), ("local", budgets.local),
                             ("lower", budgets.lower)):
            if budget is None:
                continue
            routes[name] = {
                "hypotheses": int(budget.max_hypotheses),
                "min_support_per_parity": int(budget.min_support),
            }
        routes["word"] = {
            "hypotheses": int(word.max_hypotheses),
            "single_word_probability": float(word.single_word_probability),
            "union_bound": float(word.random_union_bound),
            "familywise_false_accept": float(word.familywise_false_accept),
        }
        report: dict[str, object] = {
            "policy_id": self.policy_id,
            "max_true_error_rate": float(
                self.budget_policy.max_true_error_rate),
            "support_margin_sites": int(
                self.budget_policy.support_margin_sites),
            "gate": {
                "search_true": float(self.budget_policy.gate.search_true),
                "validation_true": float(
                    self.budget_policy.gate.validation_true),
                "rival_decoy": float(self.budget_policy.gate.rival_decoy),
                "minimum_gap": float(self.budget_policy.gate.minimum_gap),
                "qualification_id": self.budget_policy.gate.qualification_id,
            },
            "routes": routes,
        }
        if self.domain_envelope is not None:
            report["envelope"] = {
                "row_ids": list(self.domain_envelope.row_ids),
                "cold_hypotheses": int(
                    self.domain_envelope.cold_hypotheses),
                "local_hypotheses": int(
                    self.domain_envelope.local_hypotheses),
                "lower_hypotheses": int(
                    self.domain_envelope.lower_hypotheses),
                "word_hypotheses": int(
                    self.domain_envelope.word_hypotheses),
            }
        return report

    def _resolve_pages(self, context: LaneContext) -> tuple[int, ...]:
        pages = (tuple(range(context.spec.max_pages))
                 if self.page_hypotheses is None else self.page_hypotheses)
        if not pages:
            raise ValueError("page hypothesis set is empty")
        return pages

    def _resolve_budgets(
        self, context: LaneContext, pages: tuple[int, ...],
        lower: tuple[PlacementHint, ...],
    ) -> tuple:
        # E022's measured result policy searches a ranked 8-hint portfolio
        # per patch (including its two-runner reserve).  This is not a memory
        # cap: _rank_lower_hints defines which hypotheses exist on this route.
        # Budget that attempted domain, not the larger retained hint ledger;
        # chain propagation separately covers every accepted anchor.
        return self.budget_policy.resolve(
            context.spec, pages, _lower_hint_attempt_count(len(lower)),
            self.config, domain_envelope=self.domain_envelope,
        )

    def process(self, context: LaneContext,
                survey_product: SurveyProduct) -> LaneStageOutput:
        base_lane_id = (
            context.lane.refine_of
            if context.lane.refine_of is not None
            else context.lane.uplift_of)
        if base_lane_id is not None:
            # v0.42 R-level (stage-A shape): an empty durable product —
            # nothing is minted until the codec refinement leaves land —
            # carrying the typed base-lane references (RefineAddressPlan)
            # to the payload stage.  No pixels are read here, so an
            # ineligible R-level (no certificates, or nothing uncertified)
            # never materializes its raster.
            # v0.51 (PK4.3): a U-level takes exactly this shape and mints
            # even less — a supplemental lane refines no pose, so it never
            # produces a replacement address either.
            prefix = (f"{context.capture.source_sha256}/"
                      f"{context.lane.lane_id}")
            empty = AddressResult((), (), (), (), 0)
            artifact = AddressArtifact(
                f"{prefix}/address", survey_product.artifact.survey_id, ())
            product = AddressProduct(
                artifact, (),
                transient=RefineAddressPlan(
                    base_lane_id=base_lane_id,
                    poses=context.evidence.label_poses,
                    regions=context.evidence.regions,
                    certificates=context.evidence.certificates,
                ))
            _emit_address_final(context, empty, product)
            return LaneStageOutput(
                StageDecision(Stage.ADDRESS, Disposition.COMPLETE), product)
        if context.lane.mopup_of is not None:
            if not context.evidence.parked:
                empty = AddressResult((), (), (), (), 0)
                product = _address_product(context, survey_product, empty)
                _emit_address_final(context, empty, product)
                return LaneStageOutput(
                    StageDecision(Stage.ADDRESS, Disposition.COMPLETE),
                    product)
            # v0.33 M-level drive (PHASED-SCHEDULE D7): the parked
            # inventory re-samples bit-exactly on the re-derived base
            # aperture and runs hint transport, the remaining-slot sweep,
            # and the priced cold ladder with its own per-level firewall.
            pages = self._resolve_pages(context)
            lower = _lower_hints(context)
            budgets, word = self._resolve_budgets(context, pages, lower)
            # Diagnostics geometry = the same synthetic survey the drive
            # places against (lazy: built only under an observer; the
            # M-level survey product is the empty mint, transient None).
            (address_progress, address_phase_progress,
             address_region_progress) = _address_adapter_callbacks(
                context, lambda: mopup_survey(
                    context.evidence.parked, context.evidence.regions))
            result = place_mopup(
                context.raster, context.spec,
                pages=pages, budgets=budgets, word_budget=word,
                parked=context.evidence.parked,
                regions=context.evidence.regions,
                hints=lower,
                label_poses=context.evidence.label_poses,
                config=self.config,
                scan_id=(f"{context.capture.source_sha256}/"
                         f"{context.lane.lane_id}"),
                start_patch_ordinal=(
                    context.evidence.patch_ordinal_watermark),
                progress=lambda name, details: context.progress(
                    name, details=details),
                address_progress=address_progress,
                address_phase_progress=address_phase_progress,
                address_region_progress=address_region_progress,
                address_region_progress_enabled=(
                    lambda: context.snapshots_enabled),
            )  # type: ignore[arg-type]
            product = _address_product(context, survey_product, result)
            _emit_address_final(context, result, product)
            return LaneStageOutput(
                StageDecision(Stage.ADDRESS, Disposition.COMPLETE), product)
        survey = survey_product.transient
        if not isinstance(survey, PayloadSurvey):
            raise TypeError("production address stage needs PayloadSurvey")
        pages = self._resolve_pages(context)
        lower = _lower_hints(context)
        budgets, word = self._resolve_budgets(context, pages, lower)
        (address_progress, address_phase_progress,
         address_region_progress) = _address_adapter_callbacks(
            context, lambda: survey)
        try:
            result = place_survey(
                context.raster, survey, context.spec,
                pages=pages, budgets=budgets, word_budget=word,
                lower_hints=lower, config=self.config,
                scan_id=(f"{context.capture.source_sha256}/"
                         f"{context.lane.lane_id}"),
                park=True,
                progress=lambda name, details: context.progress(
                    name, details=details),
                address_progress=address_progress,
                address_phase_progress=address_phase_progress,
                address_region_progress=address_region_progress,
                address_region_progress_enabled=(
                    lambda: context.snapshots_enabled),
            )  # type: ignore[arg-type]
        except FormatHypothesisRejected as exc:
            return LaneStageOutput(StageDecision(
                Stage.ADDRESS,
                Disposition.REFUSED,
                reason=str(exc),
            ))
        product = _address_product(context, survey_product, result)
        _emit_address_final(context, result, product)
        decision = StageDecision(Stage.ADDRESS, Disposition.COMPLETE)
        return LaneStageOutput(decision, product)


def production_pipeline(
    request: ReceiveRequest,
    *,
    placement_domain_envelope: PlacementDomainEnvelope | None = None,
) -> ReceivePipeline:
    """Build Track 3 with the exact historical provisional placement row.

    No v1 physical/null gate has been frozen yet.  The implicit path uses the
    registered E021--E023c stand-ins and remains visibly provisional at every
    execution.
    """
    from .cascade import PhasedSessionScheduler

    survey = ProductionSurvey()
    address = ProductionAddress(
        PROVISIONAL_V1_PLACEMENT_POLICY, request.page_hypotheses,
        domain_envelope=placement_domain_envelope)
    if request.spec.codec_family is Family.K:
        from .production_payload import ProductionPayload
        payload_processor = ProductionPayload()
    else:
        from .production_color import ProductionColorPayload
        payload_processor = ProductionColorPayload()
    scheduler = PhasedSessionScheduler()
    close = ProductionClose()
    return ReceivePipeline(
        lanes=LaneAlgorithms(survey, address, payload_processor),
        scheduler=scheduler,
        close=close,
        page_hypotheses=request.page_hypotheses,
        qualification_status=ReceiverQualificationStatus.PROVISIONAL,
        qualification_notes=V1_PRODUCTION_QUALIFICATION_NOTES,
    )


__all__ = [
    "ProductionAddress", "ProductionSurvey",
    "production_pipeline",
]

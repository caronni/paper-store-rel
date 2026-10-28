"""Shared synthetic runtime fixtures for the Track-3 receive tests.

Phase 7 (PAYLOAD-REWORK-PLAN 7.2) retired the 16-case ``qualify_runtime``
battery this module used to carry (orphaned from pytest since kiss
e3026f1); its guards live on as fast pins in
``test_trust_boundaries.py``, ``test_payload_nulls.py``,
``test_receive_reauth_memo.py``, and ``test_receive_raster_pool.py``.
What remains here is the shared fixture library those tests (and the
deferred-close family in ``test_receive_qualification.py``) drive: a
qualification :func:`_spec`, deterministic capture images, and the
minimal survey/address/payload lane algorithms with genuine format pilot
labels and a real marginal-PAVA calibration.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

from holo.format.descriptor import FormatSpec, get_coding

from holo.receive import _payload_sampling, detect, payload, tiles
from holo.receive.cascade import PhasedSessionScheduler
from holo.receive.payload_model import (
    CaptureEvidence,
    EvidenceSource,
    OwnedPageEvidence,
    WindowEvidence,
)
from holo.receive.evidence_blocks import (
    blocks_by_address,
    blocks_from_frontier,
    merge_block_sets,
    tile_attempt_view,
)
from holo.receive.runtime import (
    LaneAlgorithms,
    LaneContext,
    LaneStageOutput,
    CloseExecution,
    ReceivePipeline,
    ReceiverQualificationStatus,
)
from holo.receive.session import (  # noqa: F401  (re-exported for tests)
    CaptureStatus,
    load_session,
)
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    AttemptStage,
    AttemptState,
    CaptureInput,
    CloseRecord,
    CloseStatus,
    Disposition,
    LosingHypothesis,
    PayloadArtifact,
    PayloadProduct,
    PoseProposal,
    PoseRecord,
    Stage,
    StageDecision,
    SupportRun,
    SurveyArtifact,
    SurveyProduct,
    SurveyRegionRecord,
    TileAttemptRecord,
)


def _spec() -> FormatSpec:
    return FormatSpec(
        get_coding("c3-r0550"), "qualification", (210.0, 297.0), 10.0)


def _capture(path: Path, *, dpi: float = 1200.0) -> CaptureInput:
    return CaptureInput(path, dpi)


def _write_image(path: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, (30, 36), dtype=np.uint8)
    Image.fromarray(pixels, mode="L").save(path)


def _ids(context: LaneContext) -> tuple[str, str, int]:
    prefix = f"{context.capture.source_sha256}|{context.lane.lane_id}"
    ordinal = int(context.lane.lane_id[1:3])
    return prefix, context.capture.source_sha256, ordinal


def _qualified_window(
    *, spec: FormatSpec, source: EvidenceSource, placement_id: str,
    region_id: str,
    patch_id: int, page: int, cell_origin_yx: tuple[int, int],
) -> WindowEvidence:
    """Dense marginal-PAVA fixture with genuine format pilot labels."""
    yy, xx = np.indices((64, 64), dtype=np.int32)
    local = np.stack((yy.ravel(), xx.ravel()), axis=1)
    cells = local + np.asarray(cell_origin_yx, np.int32)
    labels = payload.format_reference_values(spec, page, cells)
    cargo = (
        (3 * cells[:, 0] + 5 * cells[:, 1]
         + (cells[:, 0] * cells[:, 1]) % 7) % 11 < 5
    ).astype(np.int8)
    printed = np.where(labels >= 0, labels, cargo)
    means = np.where(printed != 0, 36.0, 220.0).astype(np.float32)
    scores = _payload_sampling._scores(means)
    heldout_parity = ((131 * cells[:, 0] + 17 * cells[:, 1]) & 1).astype(bool)
    known = labels >= 0
    identities = np.arange(cells.shape[0], dtype=np.int64)
    search = detect.CalibrationObservations(
        placement_id, scores[known & ~heldout_parity],
        labels[known & ~heldout_parity],
        identities[known & ~heldout_parity])
    heldout = detect.CalibrationObservations(
        placement_id, scores[known & heldout_parity],
        labels[known & heldout_parity],
        identities[known & heldout_parity])
    fit = detect.fit_calibration(search, heldout)
    if not fit.accepted or fit.calibration is None:
        raise AssertionError(f"qualification PAVA refused: {fit.reason}")
    llr = np.asarray(fit.calibration.llr(scores), np.float32)
    return WindowEvidence(
        source=source, placement_id=placement_id, patch_id=patch_id,
        region_id=region_id, page=page, redundant=False,
        segment_id=patch_id,
        segment_local_cells_yx=local, page_cells_yx=cells,
        scan_points_yx=cells.astype(np.float64), raw_means=means,
        scores=scores, reference_values=labels,
        calibration_score_nodes=fit.calibration.knots,
        calibration_probability_nodes=fit.calibration.probabilities,
        baseline_printed_llr=llr, printed_llr=llr, accepted=True,
        refusal_reason="", n_search_0=fit.n_search_0,
        n_search_1=fit.n_search_1, n_heldout=fit.n_heldout,
        heldout_logloss=fit.heldout_logloss)


@dataclass
class _Survey:
    calls: list[str]
    policy_id: str = "qualification/runtime-survey/v1"
    stage: Stage = Stage.SURVEY

    def process(self, context: LaneContext) -> LaneStageOutput:
        prefix, capture, _ = _ids(context)
        self.calls.append(prefix)
        if (context.lane.mopup_of is not None
                or context.lane.refine_of is not None):
            # v0.33 M-level / v0.42 R-level: no pixel survey; nothing is
            # ever parked or refined by this fixture, so the level
            # completes EMPTY (production semantics for an empty
            # inventory).
            return LaneStageOutput(
                StageDecision(Stage.SURVEY, Disposition.COMPLETE),
                SurveyProduct(SurveyArtifact(f"survey|{prefix}", ()), ()))
        height, width = context.raster.shape
        region_id = f"region|{prefix}"
        artifact = SurveyArtifact(f"survey|{prefix}", (region_id,))
        region = SurveyRegionRecord(
            region_id, capture, context.lane.lane_id, (0, 0),
            (height, width), 1, (height, width),
            (SupportRun(0, height * width),), 1.0, 1.0)
        return LaneStageOutput(
            StageDecision(Stage.SURVEY, Disposition.COMPLETE),
            SurveyProduct(artifact, (region,)))


@dataclass
class _Address:
    calls: list[str]
    page: int = 0
    stage: Stage = Stage.ADDRESS

    @property
    def policy_id(self) -> str:
        return f"qualification/runtime-address/v1/page-{self.page}"

    def process(self, context: LaneContext,
                survey: SurveyProduct) -> LaneStageOutput:
        prefix, capture, ordinal = _ids(context)
        self.calls.append(prefix)
        if (context.lane.mopup_of is not None
                or context.lane.refine_of is not None):
            # v0.33 M-level / v0.42 R-level with an empty inventory:
            # zero records.
            artifact = AddressArtifact(
                f"address|{prefix}", survey.artifact.survey_id, (), ())
            return LaneStageOutput(
                StageDecision(Stage.ADDRESS, Disposition.COMPLETE),
                AddressProduct(artifact, ()))
        lane_affine = np.asarray(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), np.float64)
        native_affine = tuple(
            float(value) for value in
            context.lane_to_native_affine(lane_affine).ravel())
        pose_id = f"pose|{prefix}"
        pose = PoseRecord(
            pose_id, capture, context.lane.lane_id,
            survey.regions[0].region_id, ordinal, "accepted",
            self.page, (0, 0),
            native_affine, 0, 1.0,
            0, (0, 0), (64, 64), 0,
            (0.0, 0.0), (1.0, 0.0, 0.0, 1.0), (0.0, 0.0), 1.0, 0.0,
            100, 1.0, (1.0, 1.0), 0.0)
        dependencies = (() if not context.evidence.certificates else
                        (context.evidence.certificates[-1].certificate_id,))
        proposals = (PoseProposal(
            f"proposal|{prefix}", capture, context.lane.lane_id,
            self.page, 0, (0, 0), context.capture.shape_yx,
            (0.0, 0.0), native_affine, dependencies),)
        loser = LosingHypothesis(
            f"loser|{prefix}", capture, context.lane.lane_id,
            survey.regions[0].region_id, self.page, (ordinal, 0), 0,
            (0, 0), context.capture.shape_yx, (0.0, 0.0), native_affine,
            0.5, 0.25, 7, 3)
        artifact = AddressArtifact(
            f"address|{prefix}", survey.artifact.survey_id,
            (pose_id,), tuple(row.proposal_id for row in proposals),
            (loser.hypothesis_id,))
        return LaneStageOutput(
            StageDecision(Stage.ADDRESS, Disposition.COMPLETE),
            AddressProduct(artifact, (pose,), proposals, (loser,)))


@dataclass
class _Payload:
    calls: list[str]
    fail_lane: str | None = None
    fail_once: bool = False
    contexts: list[LaneContext] | None = None
    loss_offsets: dict[str, float] | None = None
    same_tile_across_lanes: bool = False
    stage: Stage = Stage.PAYLOAD

    @property
    def policy_id(self) -> str:
        offsets = () if self.loss_offsets is None else tuple(sorted(
            (key, float(value)) for key, value in self.loss_offsets.items()))
        payload = repr((
            "qualification/runtime-payload/v1",
            offsets,
            self.same_tile_across_lanes,
        )).encode("utf-8")
        return (
            "qualification/runtime-payload/sha256-"
            f"{hashlib.sha256(payload).hexdigest()}"
        )

    def process(self, context: LaneContext, survey: SurveyProduct,
                address: AddressProduct) -> LaneStageOutput:
        prefix, capture, ordinal = _ids(context)
        self.calls.append(prefix)
        if self.contexts is not None:
            self.contexts.append(context)
        if (context.lane.mopup_of is not None
                or context.lane.refine_of is not None):
            # v0.33 M-level / v0.42 R-level with an empty inventory: an
            # empty payload artifact completes the level without evidence.
            artifact = PayloadArtifact(
                payload_id=f"payload|{prefix}",
                address_id=address.artifact.address_id,
                certificate_ids=(),
                n_blocks=0, n_attempts=0, n_divergences=0)
            return LaneStageOutput(
                StageDecision(Stage.PAYLOAD, Disposition.COMPLETE),
                PayloadProduct(
                    artifact=artifact, blocks=(), attempts=(),
                    certificates=(), divergences=()))
        if self.fail_lane == context.lane.lane_id and not self.fail_once:
            self.fail_once = True
            raise RuntimeError("qualification crash between barriers")
        tile_x = 0 if self.same_tile_across_lanes else ordinal
        model = _qualified_window(
            spec=context.spec,
            source=EvidenceSource(
                context.capture.source_sha256, context.lane.lane_id),
            placement_id=f"placement|{prefix}",
            region_id=survey.regions[0].region_id,
            patch_id=ordinal, page=0,
            cell_origin_yx=(0, tile_x * 64))
        if self.loss_offsets is not None:
            adjusted_loss = (float(model.heldout_logloss)
                             + self.loss_offsets.get(capture, 0.0))
            model = replace(
                model,
                heldout_logloss=max(0.0, adjusted_loss))
        payload_rows = np.flatnonzero(model.reference_values == -1)
        if not payload_rows.size:
            raise AssertionError("qualification window has no payload cell")
        row_index = int(payload_rows[0])
        cell = model.page_cells_yx[row_index]
        page = OwnedPageEvidence(
            model.page, cell.reshape(1, 2),
            model.printed_llr[row_index:row_index + 1],
            np.zeros(1, np.int32), np.asarray([row_index], np.int32))
        current = CaptureEvidence(
            model.source, context.spec.spec_id, (model,), (), (page,))
        current_blocks = blocks_from_frontier(current, {model.placement_id: ()})
        new_blocks = current_blocks
        frontier_blocks = merge_block_sets(
            context.evidence.prior_capture_blocks, current_blocks)
        components = tuple(sorted(
            blocks_by_address(
                frontier_blocks, lane_id=context.lane.lane_id,
            ).get((0, 0, tile_x), ()),
            key=lambda row: row.source_sha256))
        current_components = tuple(
            row for row in components if row.source_sha256 == capture)
        if len(current_components) != 1:
            raise AssertionError(
                "qualification capture did not produce one tile component")
        spec = context.spec
        profile = tiles.decoder_profile(spec.rate_id, 60, 0.8)

        def attempt_for(
            selected: tuple,
            stage: AttemptStage,
        ) -> TileAttemptRecord:
            view = tile_attempt_view(selected)
            attempt_id = tiles.attempt_identity(
                (0, 0, tile_x), stage.value, profile,
                view.component_block_ids)
            n_informative = int(np.count_nonzero(view.llr_cells_f64))
            return TileAttemptRecord(
                attempt_id=attempt_id, source_sha256=capture,
                lane_id=context.lane.lane_id, page=0,
                tile_yx=(0, tile_x), stage=stage,
                state=AttemptState.BELOW_ATTEMPT_FLOOR,
                n_informative=n_informative,
                n_iters=0, syndrome_ok=None, crc_ok=None,
                component_block_ids=view.component_block_ids,
                dependency_certificate_ids=(
                    view.dependency_certificate_ids))

        candidates = [attempt_for(current_components, AttemptStage.SCAN)]
        if len(components) >= 2:
            candidates.append(attempt_for(components, AttemptStage.UNION))
        attempts = tuple(candidates)
        artifact = PayloadArtifact(
            payload_id=f"payload|{prefix}",
            address_id=address.artifact.address_id,
            certificate_ids=(),
            n_blocks=len(new_blocks),
            n_attempts=len(attempts),
            n_divergences=0)
        return LaneStageOutput(
            StageDecision(Stage.PAYLOAD, Disposition.COMPLETE),
            PayloadProduct(
                artifact=artifact, blocks=new_blocks, attempts=attempts,
                certificates=(), divergences=()))


class _Scheduler:
    """Explicit qualification adapter around the production scale walk.

    v0.33: the runtime owns rung-major cross-capture iteration; one
    ``process`` call advances exactly one plan level (base or mop-up).
    """

    policy_id = PhasedSessionScheduler.policy_id

    def process(self, context):
        return PhasedSessionScheduler().process(context)


class _OpenClose:
    policy_id = "qualification/runtime-open-close/v1"

    def process(self, _context) -> CloseExecution:
        return CloseExecution(CloseRecord())


class _TerminalClose:
    def __init__(self, failure: bool) -> None:
        self.failure = failure

    @property
    def policy_id(self) -> str:
        outcome = "integrity-failure" if self.failure else "verified"
        return f"qualification/runtime-terminal-close/v1/{outcome}"

    def process(self, context) -> CloseExecution:
        frontier = context.certificate_frontier_sha256
        actual = hashlib.sha256(b"payload").hexdigest()
        record = (
            CloseRecord(
                CloseStatus.INTEGRITY_FAILURE,
                frontier,
                reason="payload SHA mismatch",
            )
            if self.failure
            else CloseRecord(
                CloseStatus.VERIFIED,
                frontier,
                actual,
                len(b"payload"),
            )
        )
        return CloseExecution(record, None if self.failure else b"payload")


def _pipeline(*, crash_lane: str | None = None,
              contexts: list[LaneContext] | None = None,
              loss_offsets: dict[str, float] | None = None,
              page_hypotheses: tuple[int, ...] | None = None,
              address_page: int = 0,
              same_tile_across_lanes: bool = False,
              ) -> tuple[ReceivePipeline, tuple[list[str], list[str], list[str]]]:
    calls: tuple[list[str], list[str], list[str]] = ([], [], [])
    algorithms = LaneAlgorithms(
        _Survey(calls[0]), _Address(calls[1], address_page),
        _Payload(
            calls[2], crash_lane, False, contexts, loss_offsets,
            same_tile_across_lanes))
    return ReceivePipeline(
        algorithms, _Scheduler(), _OpenClose(),
        page_hypotheses=page_hypotheses,
        qualification_status=ReceiverQualificationStatus.QUALIFIED,
    ), calls

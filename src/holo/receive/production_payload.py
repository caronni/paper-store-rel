"""Production K payload stage (E023b leaf driver).

``ProductionPayload`` adapts the K/main numerical payload leaves —
sampling/calibration/context, the one-owner freeze, compact block
materialization, and the shared attempt engine — into the runtime's
typed payload seam.  Split from ``production.py`` in the Phase 4 hammer
batch (RECEIVE-DESIGN v0.38).  ``process`` is decomposed into named
stage methods (plan -> sample -> freeze -> blocks -> decode -> retry ->
complete).

v0.42: certified pose refinement moved OUT of this inline schedule into
the R(Lk) refinement levels (:mod:`production_refine`) — ordinary K
lanes are generation-zero only; an R-level routes through
:func:`production_refine.process_refine_level`, which reuses the
freeze/blocks/decode/retry/complete methods over its affected-region
delta.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Mapping

import numpy as np

from . import _diagnostic_snapshots as diagnostic_snapshots
from . import _production_diagnostics as production_diagnostics
from . import payload
from .evidence import (
    AttemptStage,
    PayloadArtifact,
    PayloadProduct,
    TileAttemptRecord,
    TileCertificateRecord,
    certificate_work_index,
)
from .evidence_blocks import (
    EvidenceBlock,
    SupersessionDrops,
    TileAttemptView,
    apply_mopup_supersession,
    blocks_from_frontier,
    merge_block_sets,
)
from .fountain_close import close_count_ready, close_volume
from .payload_engine import EngineRun, RecordingLeaf, run_attempts
from .payload_model import (
    CONTEXT_PROFILE,
    CaptureEvidence,
    EvidenceSource,
    OwnedPageEvidence,
    WindowEvidence,
)
from .placement.model import AddressResult
from .records import (
    CertificateStore,
    certificate_divergence,
    certificate_for_close,
    restore_store,
)
from .runtime import LaneContext, LaneStageOutput
from .types import (
    AddressProduct,
    Detail,
    Disposition,
    Stage,
    StageDecision,
    SurveyProduct,
)


def _window_dependencies(
    result: AddressResult,
    product: AddressProduct,
    windows: tuple[WindowEvidence, ...],
) -> dict[str, tuple[str, ...]]:
    """Carry exact lower-barrier pose lineage into E023b windows."""
    if len(result.placements) != len(product.poses):
        raise ValueError("address product pose count disagrees with placements")
    by_patch: dict[int, tuple[str, ...]] = {}
    for patch, pose in zip(result.placements, product.poses, strict=True):
        by_patch[int(patch.patch_id)] = tuple(sorted(
            set(pose.dependency_certificate_ids)))
    try:
        output = {
            row.placement_id: by_patch[int(row.patch_id)] for row in windows}
    except KeyError as exc:
        raise ValueError("payload window has no placed-patch lineage") from exc
    if len(output) != len(windows):
        raise ValueError("payload windows repeat a placement identity")
    return output


def _certified_k_addresses(
    certificates: tuple[TileCertificateRecord, ...],
) -> frozenset[tuple[int, int, int]]:
    """Return the terminal physical-tile NeedMap complement for K/main.

    The durable certificate index remains the authority for this decision.
    ProductionPayload is the K leaf, so encountering another stream here is
    a routing fault rather than evidence that may be ignored.
    """
    certified = certificate_work_index(certificates)
    foreign = tuple(
        sorted(work_key for work_key in certified if work_key[3] != "main"))
    if foreign:
        raise ValueError("K payload stage received a non-main certificate")
    return frozenset(work_key[:3] for work_key in certified)


def _prune_certified_k_owners(
    frontier: CaptureEvidence,
    certified_addresses: frozenset[tuple[int, int, int]],
) -> CaptureEvidence:
    """Drop terminal K owner cells before compact block materialization.

    Sampling, marginal/context calibration, overlap ownership, and certified
    pose refinement have already completed when this helper is called.  The
    remaining operation partitions frozen owner cells into tile-local blocks,
    so removing whole certified tile addresses here cannot alter an unresolved
    tile's numerical evidence.  Windows and context decisions are retained to
    preserve the exact provenance indices of every unresolved owner.

    Interior helper: the certified set is minted upstream from the durable
    certificate index (mint-once, kiss validation-boundary ruling).
    """
    if not certified_addresses:
        return frontier

    certified_codes_by_page: dict[int, np.ndarray] = {}
    for certified_page in sorted({address[0]
                                  for address in certified_addresses}):
        certified_codes_by_page[certified_page] = np.asarray(
            sorted(
                (tile_y << 32) | tile_x
                for page, tile_y, tile_x in certified_addresses
                if page == certified_page
            ),
            dtype=np.int64,
        )
    pages: list[OwnedPageEvidence] = []
    changed = False
    for page in frontier.pages:
        certified_codes = certified_codes_by_page.get(page.page)
        if certified_codes is None:
            pages.append(page)
            continue
        cells = np.asarray(page.cells_yx, np.int64)
        tile_codes = (
            (cells[:, 0] // 64) << np.int64(32)
        ) | (cells[:, 1] // 64)
        keep = ~np.isin(
            tile_codes, certified_codes, assume_unique=False)
        if bool(np.all(keep)):
            pages.append(page)
            continue
        changed = True
        if not bool(np.any(keep)):
            continue
        pages.append(OwnedPageEvidence(
            page.page,
            page.cells_yx[keep],
            page.printed_llr[keep],
            page.window_indices[keep],
            page.window_row_indices[keep],
        ))
    if not changed:
        return frontier
    return CaptureEvidence(
        frontier.source,
        frontier.spec_id,
        frontier.windows,
        frontier.context_decisions,
        tuple(pages),
    )


@dataclass(frozen=True, slots=True)
class _PayloadPlan:
    """Typed carrier for the pool-law admission decision (stage: plan)."""
    certified_addresses: frozenset[tuple[int, int, int]]
    included_patch_ids: frozenset[int]
    pruned_patch_ids: frozenset[int]
    pruned_region_indices: frozenset[int]


@dataclass(frozen=True, slots=True)
class ProductionPayload:
    # Hand-bumped identity, spelled literally in full — never derived from
    # a live constant.  v10 wired the advisory preclose (ruling 6.6: K uses
    # the same code as color): a terminal preclose suppresses retry150.
    # v11-f32-scores: ruling 10.2 — the K detection score path is
    # float32-native (`_payload_sampling._scores` drops the float64
    # compute-then-quantize detour); scores/knots/LLRs move by ulps, so
    # every durable K payload product is re-derived under this identity.
    # -stripes-xy: ruling 10.5 — the certified-refinement cargo-holdout
    # stripe assignment mixes x and y (odd coefficients, diagonal stripes);
    # held-out membership changed, so refinement adoption can change.
    # v12-r-lane: RECEIVE-DESIGN v0.42 clause (B) — certified pose
    # refinement moved out of the inline schedule into the R(Lk)
    # refinement levels: ordinary/mop-up K lanes are generation-zero only,
    # and the R-level leaf (production_refine) reconstructs the base
    # lane's committed poses, refines against the full accumulated
    # frontier, and emits an affected-regions-only delta in its OWN
    # evidence namespace.  Same numerical leaves; the SCHEDULE is the
    # semantic change, so every durable K payload product re-derives
    # under this identity.
    policy_id: ClassVar[str] = (
        "holo/e023b-e023c-payload/paperholo-e023b-e023c-v12-r-lane/"
        "needmap-region-prune-label-rows-owner-prune-acquisition-"
        "components-max60-preclose-selective-retry150-unified-cert-identity-"
        "stripes-xy")
    stage: Stage = Stage.PAYLOAD

    def _plan(
        self, context: LaneContext, address_product: AddressProduct,
    ) -> _PayloadPlan:
        """Terminal-tile pool-law admission (L1/L2) + the plan event."""
        certified_addresses = _certified_k_addresses(
            context.evidence.certificates)
        promoted_patch_ids = frozenset(
            int(row.patch_id)
            for row in address_product.transient.payload_placements
        )
        included_patch_ids = (
            promoted_patch_ids
            if not certified_addresses
            else payload.unresolved_region_patch_ids(
                address_product.transient,
                context.spec,
                certified_addresses,
            )
        )
        pruned_patch_ids = promoted_patch_ids - included_patch_ids
        pruned_region_indices = frozenset(
            int(row.region_index)
            for row in address_product.transient.payload_placements
            if int(row.patch_id) in pruned_patch_ids
        )
        # E023c registered one session-wide production detector profile:
        # ctx-pava-v1 at every scale, including the 2-ppc acquisition lane.
        # Context fitting is itself held-out gated and preserves the exact
        # marginal-PAVA baseline whenever it is ineligible or not beneficial;
        # footing is not an additional detector-selection policy.
        context.progress(
            "payload.plan",
            details=(Detail("payload.placements",
                            len(address_product.transient.payload_placements)),
                     Detail(
                         "payload.placements_quarantined",
                         len(address_product.transient.quarantined_patch_ids)),
                     Detail("payload.prior_certificates",
                            len(context.evidence.certificates)),
                     Detail("payload.prior_certified_addresses",
                            len(certified_addresses)),
                     Detail("payload.needed_patches",
                            len(included_patch_ids)),
                     Detail("payload.pruned_terminal_patches",
                            len(pruned_patch_ids)),
                     Detail("payload.pruned_terminal_regions",
                            len(pruned_region_indices)),
                     Detail("payload.detector_profile", CONTEXT_PROFILE)),
        )
        return _PayloadPlan(
            certified_addresses, included_patch_ids,
            pruned_patch_ids, pruned_region_indices)

    def _sample(
        self,
        context: LaneContext,
        address_product: AddressProduct,
        plan: _PayloadPlan,
    ) -> CaptureEvidence:
        """Generation-zero collection (v0.42: ordinary lanes never refine).

        Certified pose refinement lives in the R(Lk) refinement levels
        (:mod:`production_refine`); every ordinary or mop-up K lane emits
        exactly its generation-zero evidence.
        """
        source = EvidenceSource(
            context.capture.source_sha256,
            context.lane.evidence_lane_id)
        return payload.collect_capture_evidence(
            context.raster, source, address_product.transient, context.spec,
            detector_profile=CONTEXT_PROFILE,
            included_patch_ids=plan.included_patch_ids,
            terminal_addresses=plan.certified_addresses,
            region_progress=production_diagnostics.install_adapter(
                context, "payload.region.adapter.install",
                lambda: production_diagnostics.payload_region_callback(
                    context, 0)))

    def _freeze(
        self,
        context: LaneContext,
        current: CaptureEvidence,
        plan: _PayloadPlan,
    ) -> CaptureEvidence:
        """Prune terminal owner cells + the owner-frozen event."""
        unresolved_current = _prune_certified_k_owners(
            current, plan.certified_addresses)
        sampled_owner_cells = sum(
            page.cells_yx.shape[0] for page in current.pages)
        needed_owner_cells = sum(
            page.cells_yx.shape[0] for page in unresolved_current.pages)
        context.progress(
            "payload.owner_frozen",
            details=(
                Detail("payload.pages", len(unresolved_current.pages)),
                Detail("payload.owner_cells", needed_owner_cells),
                Detail("payload.needed_owner_cells", needed_owner_cells),
                Detail("payload.sampled_owner_cells", sampled_owner_cells),
                Detail(
                    "payload.pruned_certified_owner_cells",
                    sampled_owner_cells - needed_owner_cells,
                ),
                Detail("payload.pruned_terminal_patches",
                       len(plan.pruned_patch_ids)),
                Detail("payload.pruned_terminal_regions",
                       len(plan.pruned_region_indices)),
                Detail("payload.windows", len(current.windows)),
            ),
            snapshot_factory=lambda: diagnostic_snapshots.payload(
                unresolved_current, context.spec),
        )
        return unresolved_current

    def _blocks(
        self,
        context: LaneContext,
        dependencies: Mapping[str, tuple[str, ...]],
        unresolved_current: CaptureEvidence,
        certified_addresses: frozenset[tuple[int, int, int]],
    ) -> tuple[
        tuple[EvidenceBlock, ...], tuple[EvidenceBlock, ...],
        SupersessionDrops,
    ]:
        """Compact block materialization + the merged same-lane frontier."""
        new_blocks = blocks_from_frontier(unresolved_current, dependencies)
        mopup_drops = SupersessionDrops(0, 0)
        if (context.lane.mopup_of is not None
                and context.evidence.own_committed_blocks):
            # v0.33 D5: a colliding key becomes the committed-verbatim-
            # plus-novel superset; base owners win cells.  The drop tally
            # (dropped re-observations + winner flips) is the two-view
            # consistency canary (2026-08-02 ruling).
            new_blocks, mopup_drops = (
                apply_mopup_supersession(
                    new_blocks, context.evidence.own_committed_blocks))
        frontier_blocks = merge_block_sets(
            (
                block for block in context.evidence.prior_capture_blocks
                if block.address not in certified_addresses
            ),
            new_blocks,
        )
        if any(block.lane_id != context.lane.evidence_lane_id
               for block in frontier_blocks):
            raise ValueError(
                "payload frontier contains evidence from another lane")
        return new_blocks, frontier_blocks, mopup_drops

    def _decode(
        self,
        context: LaneContext,
        new_blocks: tuple[EvidenceBlock, ...],
        frontier_blocks: tuple[EvidenceBlock, ...],
    ) -> tuple[CertificateStore, RecordingLeaf, EngineRun, bool]:
        """Run the shared scan -> union -> (preclose) -> retry150 engine."""
        def live_attempt_snapshot(
            row: TileAttemptRecord, evidence: TileAttemptView,
        ) -> object:
            if row.component_block_ids != evidence.component_block_ids:
                raise ValueError(
                    "diagnostic attempt provenance changed before observation")
            return production_diagnostics.attempt_snapshot(
                row, evidence, evidence.components, context.spec)

        store = restore_store(context.spec, context.evidence.certificates)
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
        def k_decode(view, stream_id, stage):
            del stream_id  # K has exactly one stream
            return payload.attempt_k_tile(
                view.llr_cells_f64, context.spec, view.address, stage,
                source_sha256=context.capture.source_sha256,
                lane_id=context.lane.evidence_lane_id,
                component_block_ids=view.component_block_ids,
                dependency_certificate_ids=view.dependency_certificate_ids)

        leaf = RecordingLeaf(
            store, k_decode,
            attempt_progress=attempt_progress,
            retry_attempt_progress=retry_attempt_progress)
        retry_open_progress = production_diagnostics.install_adapter(
            context, "payload.retry_open.adapter.install",
            lambda: production_diagnostics.retry_open_callback(context))
        preclose_attempted = [False]

        def preclose() -> bool:
            """Advisory pre-close (same code as color, ruling 6.6): a
            rank/SHA success makes retry150 moot; the runtime barrier
            stays the sole authoritative durable close."""
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

        # v0.27 bug fix: SCAN is this capture's evidence only; the merged
        # frontier feeds the UNION stage.  Passing the frontier as
        # ``new_blocks`` minted scan attempts over prior acquisitions'
        # components, which the barrier correctly refuses ("scan attempt
        # does not use the current acquisition") — any second same-lane
        # K capture crashed at its first payload commit.  The color path
        # (production_color.py) was always the documented contract.
        engine_run = run_attempts(
            new_blocks,
            frontier_blocks,
            lane_id=context.lane.evidence_lane_id,
            leaf=leaf,
            preclose=None if context.defer_fountain_close else preclose,
            retry_open=retry_open_progress,
        )
        return store, leaf, engine_run, preclose_attempted[0]

    def _retry(
        self,
        context: LaneContext,
        store: CertificateStore,
        leaf: RecordingLeaf,
        engine_run: EngineRun,
    ) -> tuple[
        tuple[TileAttemptRecord, ...],
        tuple[TileCertificateRecord, ...],
        tuple[TileAttemptRecord, ...],
    ]:
        """Partition the durable rows + the retry150 report event."""
        durable_attempts = tuple(leaf.attempts)
        durable_certificates = tuple(leaf.certificates)
        retry_rows = tuple(
            row for row in durable_attempts
            if row.stage is AttemptStage.RETRY150)
        ordinary_rows = tuple(
            row for row in durable_attempts
            if row.stage is not AttemptStage.RETRY150)
        ordinary_certificates = tuple(
            row for row in durable_certificates
            if row not in leaf.retry_certificates)
        # "eligible" is the engine's selected retry frontier; "attempted"
        # counts recorded retry rows.  They differ when a terminal advisory
        # preclose suppresses the retry pass or a spent identity no-ops
        # (doc-truth fix 2026-08-02: the report previously conflated the
        # two by deriving both from the attempted rows).
        retry_report = {
            "noop": not retry_rows,
            "frontier": len(engine_run.retry_frontier),
            "eligible": len(engine_run.retry_frontier),
            "attempted": len(retry_rows),
            "certified": len(leaf.retry_certificates),
            "total_certified": len(store),
        }
        if context.observer_enabled:
            context.progress(
                "payload.retry_complete",
                details=production_diagnostics.retry_summary_details(
                    ordinary_rows, ordinary_certificates,
                    retry_rows, leaf.retry_certificates, retry_report),
            )
        return durable_attempts, durable_certificates, retry_rows

    def _complete(
        self,
        context: LaneContext,
        *,
        active_address: AddressProduct,
        replacement_address: AddressProduct | None,
        refinement_eligible: int,
        refinement_adopted: int,
        new_blocks: tuple[EvidenceBlock, ...],
        frontier_blocks: tuple[EvidenceBlock, ...],
        store: CertificateStore,
        leaf: RecordingLeaf,
        engine_run: EngineRun,
        durable_attempts: tuple[TileAttemptRecord, ...],
        durable_certificates: tuple[TileCertificateRecord, ...],
        retry_rows: tuple[TileAttemptRecord, ...],
        preclose_attempted: bool,
        mopup_drops: SupersessionDrops,
    ) -> LaneStageOutput:
        """Divergence audit + the durable product and completion event.

        v0.42: ``refinement_eligible``/``refinement_adopted`` are 0 on
        every ordinary and mop-up lane (refinement lives in the R-levels,
        which pass their real counts and their minted replacement
        address); the event schema is unchanged.
        """
        # One non-gating audit of ALL certified truth (restored + newly
        # minted) against this capture's compact observations; dedup is
        # invocation-local (the persisted ledger is a counter).
        durable_divergences = certificate_divergence(
            frontier_blocks, store.certificates(), context.spec)
        prefix = f"{context.capture.source_sha256}/{context.lane.lane_id}"
        artifact = PayloadArtifact(
            f"{prefix}/payload", active_address.artifact.address_id,
            tuple(row.certificate_id for row in durable_certificates),
            n_blocks=len(new_blocks),
            n_attempts=len(durable_attempts),
            n_divergences=len(durable_divergences),
        )
        product = PayloadProduct(
            artifact, new_blocks, durable_attempts, durable_certificates,
            durable_divergences,
            mopup_dropped_observations=mopup_drops.dropped,
            mopup_winner_flips=mopup_drops.winner_flips)
        context.progress(
            "payload.complete",
            details=(Detail("payload.blocks", len(new_blocks)),
                     Detail("payload.attempts", len(durable_attempts)),
                     Detail("payload.certificates",
                            len(durable_certificates)),
                     Detail("payload.detector_profile", CONTEXT_PROFILE),
                     Detail("payload.refinement_eligible",
                            refinement_eligible),
                     Detail("payload.refinement_adopted",
                            refinement_adopted),
                     Detail("payload.retry150_attempts",
                            len(retry_rows)),
                     Detail("payload.retry150_certificates",
                            len(leaf.retry_certificates)),
                     Detail("payload.preclose_attempted",
                            preclose_attempted),
                     Detail("payload.terminal_close",
                            engine_run.terminal_close),
                     Detail("payload.mopup_dropped_observations",
                            mopup_drops.dropped),
                     Detail("payload.mopup_winner_flips",
                            mopup_drops.winner_flips)),
        )
        decision = StageDecision(Stage.PAYLOAD, Disposition.COMPLETE)
        return LaneStageOutput(
            decision, product,
            replacement_address=replacement_address,
        )

    def process(self, context: LaneContext, survey_product: SurveyProduct,
                address_product: AddressProduct) -> LaneStageOutput:
        if context.lane.arm_override is not None:
            # PK4.3: supplemental lanes are COLOR-ONLY by construction
            # (``cascade._scale_plan`` mints none for ``k-v1``, pinned).
            # Reaching here means a plan was assembled by hand for the
            # wrong codec; refuse loudly rather than decode K evidence
            # under a color-stack arm override.
            raise ValueError(
                f"K schedules no supplemental lane: {context.lane.lane_id}")
        if context.lane.refine_of is not None:
            # v0.42 R(Lk) level: the K refinement leaf (own evidence
            # namespace; delta covers affected regions only).
            from .production_refine import process_refine_level
            return process_refine_level(
                self, context, survey_product, address_product)
        if not isinstance(address_product.transient, AddressResult):
            raise TypeError("production payload stage needs AddressResult")
        plan = self._plan(context, address_product)
        current = self._sample(context, address_product, plan)
        unresolved_current = self._freeze(context, current, plan)
        dependencies = _window_dependencies(
            address_product.transient, address_product, current.windows)
        new_blocks, frontier_blocks, mopup_drops = (
            self._blocks(context, dependencies, unresolved_current,
                         plan.certified_addresses))
        store, leaf, engine_run, preclose_attempted = self._decode(
            context, new_blocks, frontier_blocks)
        durable_attempts, durable_certificates, retry_rows = self._retry(
            context, store, leaf, engine_run)
        return self._complete(
            context,
            active_address=address_product,
            replacement_address=None,
            refinement_eligible=0,
            refinement_adopted=0,
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


__all__ = ["ProductionPayload"]

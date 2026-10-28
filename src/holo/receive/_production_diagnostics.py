"""Observer adapters kept out of the numerical production stage bodies.

Every expensive builder is returned through ``snapshot_factory`` so the
runtime's observer boundary owns failure isolation and lazy construction.
The callbacks contain no receiver decisions and return no value to a stage.

The colour stage's own Detail builders live here too:
:func:`color_region_details` and :func:`plane_field_details`, moved out
of ``production_color`` (2026-08-20) beside the ``color_refinement_details``
that was already here.  Same rule as every other adapter in this module —
they read a finished summary and return scalars.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from math import hypot
from statistics import median
from typing import TypeVar

from ..core.channel import PLANE_ORDER
from ..format.descriptor import FormatSpec
from . import _diagnostic_snapshots as snapshots
from . import tiles
from .certified_cascade import SegmentRefinementSummary
from .color_evidence import ColorRegionSummary
from .color_field import PLANE_NAMES, PlaneFieldReport
from .color_refine import ColorWindowRefinement
from .evidence_blocks import EvidenceBlock, TileAttemptView
from .payload_model import ContextDecision, WindowEvidence
from .placement.model import (
    CandidateScore,
    PlacedPatch,
    PoseSegment,
    PoseWindow,
    WindowAttempt,
)
from .runtime_model import LaneContext
from .survey import PayloadSurvey
from .types import Detail, Scalar, TileAttemptRecord, TileCertificateRecord


_Adapter = TypeVar("_Adapter")


def install_adapter(
    context: LaneContext,
    label: str,
    factory: Callable[[], _Adapter],
) -> _Adapter | None:
    """Build an optional adapter without exposing its code to the receiver."""
    installed: list[_Adapter] = []
    context.observe(label, lambda: installed.append(factory()))
    return installed[0] if installed else None


def address_callbacks(
    context: LaneContext,
    survey_source: Callable[[], PayloadSurvey],
) -> tuple[Callable[..., None], Callable[..., None], Callable[..., None]]:
    """Create E022 terminal, phase, and region observer callbacks.

    ``survey_source`` yields the geometry the placement engine runs
    against — the survey stage's transient on ordinary lanes, the
    ``mopup_survey`` re-derivation on M-levels (whose survey product is
    the empty mint) — so window snapshots always price real pitch and
    region origins.  Evaluated once, behind the observer boundary:
    observer-less runs never build it.
    """
    survey = survey_source()

    def terminal(
        attempt: WindowAttempt,
        placed: PlacedPatch | None,
        ordinal: int,
        queue_total: int,
        anchor_count: int,
    ) -> None:
        context.observe(
            "address.window_progress.adapter",
            lambda: context.progress(
                "address.window_progress",
                details=(
                    Detail("address.region", attempt.region_index),
                    Detail("address.window", attempt.window.window_id),
                    Detail("address.window_ordinal", ordinal),
                    Detail("address.queue_total", queue_total),
                    Detail("address.anchor_count", anchor_count),
                    Detail("address.window_phase", "terminal"),
                    Detail("address.outcome", attempt.outcome),
                    Detail("address.reason", attempt.reason or None),
                    Detail("address.page", None if attempt.candidate is None
                           else attempt.candidate.page),
                ),
                snapshot_factory=lambda: snapshots.window(
                    attempt, placed, pitch_px=survey.cell_pitch_px,
                    region_origin_yx=survey.regions[
                        attempt.region_index].support.origin_yx,
                    ordinal=ordinal, queue_total=queue_total,
                    anchor_count=anchor_count),
            ))

    def phase(
        region_index: int,
        window: PoseWindow,
        phase_name: str,
        segment: PoseSegment | None,
        attempted_routes: tuple[str, ...],
        candidate: CandidateScore | None,
        patch_id: int | None,
        ordinal: int,
        queue_total: int,
        anchor_count: int,
    ) -> None:
        context.observe(
            "address.window_progress.adapter",
            lambda: context.progress(
                "address.window_progress",
                details=(
                    Detail("address.region", region_index),
                    Detail("address.window", window.window_id),
                    Detail("address.window_ordinal", ordinal),
                    Detail("address.queue_total", queue_total),
                    Detail("address.anchor_count", anchor_count),
                    Detail("address.window_phase", phase_name),
                    Detail("address.route_count", len(attempted_routes)),
                    Detail("address.route", None if not attempted_routes
                           else attempted_routes[-1]),
                    Detail("address.patch", patch_id),
                    Detail("address.page", None if candidate is None
                           else candidate.page),
                ),
                snapshot_factory=lambda: snapshots.window_phase(
                    region_index, window, phase_name, segment=segment,
                    attempted_routes=attempted_routes, candidate=candidate,
                    patch_id=patch_id, pitch_px=survey.cell_pitch_px,
                    region_origin_yx=(
                        survey.regions[region_index].support.origin_yx),
                    ordinal=ordinal, queue_total=queue_total,
                    anchor_count=anchor_count),
            ))

    def region(
        region_index: int,
        state: str,
        placements: tuple[PlacedPatch, ...],
        attempts: tuple[WindowAttempt, ...],
        region_states: tuple[tuple[int, str], ...],
        hypotheses_evaluated: int,
    ) -> None:
        context.observe(
            "address.region_complete.adapter",
            lambda: context.progress(
                "address.region_complete",
                details=(Detail("address.region", region_index),
                         Detail("address.state", state),
                         Detail("address.region_placements", len(placements)),
                         Detail("address.hypotheses", hypotheses_evaluated)),
                snapshot_factory=lambda: snapshots.address_progress(
                    placements, attempts, region_states,
                    hypotheses_evaluated),
            ))

    return terminal, phase, region


def payload_region_callback(
    context: LaneContext,
    generation: int,
) -> Callable[
        [str, tuple[WindowEvidence, ...], ContextDecision | None], None]:
    """Publish cumulative coverage without retaining numerical windows."""
    accumulator = (snapshots.payload_progress(context.spec)
                   if context.snapshots_enabled else None)
    completed_regions: set[str] = set()

    def observe(
        region_id: str,
        windows: tuple[WindowEvidence, ...],
        decision: ContextDecision | None,
    ) -> None:
        def publish() -> None:
            nonlocal accumulator
            if decision is not None:
                context.progress(
                    "context.region_complete",
                    details=(Detail("payload.generation", generation),
                             Detail("context.region_id", region_id),
                             Detail("context.eligible", decision.eligible),
                             Detail("context.adopted", decision.adopted),
                             Detail("context.reason", decision.reason)),
                    snapshot_factory=(lambda: snapshots.context(decision))
                    if context.snapshots_enabled else None,
                )
                if not context.observer_enabled:
                    return
            completed_regions.add(region_id)
            if accumulator is not None and not context.snapshots_enabled:
                accumulator = None
            context.progress(
                "payload.region_emitted",
                details=(Detail("payload.generation", generation),
                         Detail("payload.region_id", region_id),
                         Detail("payload.completed_regions",
                                len(completed_regions)),
                         Detail("payload.pages", len({
                             int(row.page) for row in windows})),
                         Detail("payload.windows", len(windows)),
                         Detail("payload.windows_accepted",
                                sum(row.accepted for row in windows))),
                snapshot_factory=(lambda: accumulator.advance(
                    windows, region_id=region_id, generation=generation))
                if accumulator is not None else None,
            )

        context.observe("payload.region.adapter", publish)

    return observe


def attempt_progress_callback(
    context: LaneContext,
    event_name: str,
    ordinal: list[int],
    snapshot_builder: Callable[[TileAttemptRecord, TileAttemptView], object],
) -> Callable[[TileAttemptRecord, TileAttemptView], None]:
    """Publish one attempt at its decoder boundary with lazy fine detail."""
    def observe(row: TileAttemptRecord, evidence: TileAttemptView) -> None:
        def publish() -> None:
            ordinal[0] += 1
            context.progress(
                event_name,
                details=(Detail("payload.attempt_ordinal", ordinal[0]),
                         Detail("payload.attempt_stage", row.stage.value),
                         Detail("payload.stream", row.stream_id),
                         Detail("payload.page", row.page),
                         Detail("payload.tile_y", row.tile_yx[0]),
                         Detail("payload.tile_x", row.tile_yx[1]),
                         Detail("payload.attempt_state", row.state.value),
                         Detail("payload.informative", row.n_informative),
                         Detail("payload.decoder_invoked", row.decoder_invoked),
                         Detail("payload.crc_ok", row.crc_ok),
                         Detail("payload.certificate_is_new",
                                row.certificate_id is not None)),
                snapshot_factory=(lambda: snapshot_builder(row, evidence))
                if context.snapshots_enabled else None,
            )

        context.observe(f"{event_name}.adapter", publish)

    return observe


def retry_open_callback(
    context: LaneContext,
) -> Callable[[tuple[TileAttemptRecord, ...]], None]:
    """Announce the exact retry150 frontier once, at retry open.

    The per-tile snapshot feeds pane D's transient in-flight layer
    (RECEIVE-DESIGN v0.27 §10.3.3); highlights clear on either terminal
    retry outcome.  Aggregate counts are never back-projected into tiles.
    """
    def observe(frontier: tuple[TileAttemptRecord, ...]) -> None:
        tiles_out = tuple(sorted(
            (int(row.work_key[0]), int(row.work_key[1]),
             int(row.work_key[2]), str(row.work_key[3]))
            for row in frontier))

        def publish() -> None:
            context.progress(
                "payload.retry_open",
                details=(Detail("payload.retry_tiles", len(tiles_out)),),
                snapshot_factory=(
                    (lambda: {"kind": "retry_frontier", "tiles": tiles_out})
                    if context.snapshots_enabled else None),
            )

        context.observe("payload.retry_open.adapter", publish)

    return observe


def retry_summary_details(
    ordinary_attempts: Iterable[TileAttemptRecord],
    ordinary_certificates: Iterable[TileCertificateRecord],
    retry_attempts: Iterable[TileAttemptRecord],
    retry_certificates: Iterable[TileCertificateRecord],
    report: Mapping[str, int | bool],
) -> tuple[Detail, ...]:
    """Describe the mandatory max60 -> selective retry150 lane boundary."""
    ordinary = tuple(ordinary_attempts)
    ordinary_certs = tuple(ordinary_certificates)
    retried = tuple(retry_attempts)
    retry_certs = tuple(retry_certificates)
    return (
        Detail("payload.max60_attempts", len(ordinary)),
        Detail("payload.max60_decoder_calls",
               sum(int(row.decoder_invoked) for row in ordinary)),
        Detail("payload.max60_bp_iterations",
               sum(int(row.n_iters) for row in ordinary)),
        Detail("payload.max60_certificates", len(ordinary_certs)),
        Detail("payload.retry150_frontier", report["frontier"]),
        Detail("payload.retry150_eligible", report["eligible"]),
        Detail("payload.retry150_attempts", len(retried)),
        Detail("payload.retry150_decoder_calls",
               sum(int(row.decoder_invoked) for row in retried)),
        Detail("payload.retry150_bp_iterations",
               sum(int(row.n_iters) for row in retried)),
        Detail("payload.retry150_certificates", len(retry_certs)),
        Detail("payload.retry150_noop", report["noop"]),
    )


def refinement_details(row: SegmentRefinementSummary) -> tuple[Detail, ...]:
    """Detach the complete qualified E023c refinement audit as scalars."""
    metrics = row.metrics
    baseline = row.baseline_pose
    adopted = row.adopted_pose
    baseline_matrix = tuple(float(value) for value in baseline.matrix().ravel())
    adopted_matrix = (() if adopted is None else tuple(
        float(value) for value in adopted.matrix().ravel()))
    values: tuple[tuple[str, Scalar], ...] = (
        ("refinement.patch", row.patch_id),
        ("refinement.segment", row.segment_id),
        ("refinement.frontier", row.frontier_id),
        ("refinement.eligible", metrics.eligible),
        ("refinement.adopted", metrics.adopted),
        ("refinement.reason", metrics.reason),
        ("refinement.candidates", metrics.candidates),
        ("refinement.dtheta_deg", metrics.dtheta_deg),
        ("refinement.du_cells", metrics.du_cells),
        ("refinement.dv_cells", metrics.dv_cells),
        ("refinement.baseline_validation_logloss",
         metrics.baseline_validation_logloss),
        ("refinement.candidate_validation_logloss",
         metrics.candidate_validation_logloss),
        ("refinement.baseline_pilot_mismatch",
         metrics.baseline_pilot_mismatch),
        ("refinement.candidate_pilot_mismatch",
         metrics.candidate_pilot_mismatch),
        ("refinement.generation0_e022_pilot_mismatch",
         metrics.generation0_e022_pilot_mismatch),
        ("refinement.candidate_e022_pilot_mismatch",
         metrics.candidate_e022_pilot_mismatch),
        ("refinement.payload_train", metrics.n_payload_train),
        ("refinement.payload_validation", metrics.n_payload_validation),
        ("refinement.certified_blocks", metrics.n_certified_blocks),
        ("refinement.pose_train", metrics.n_pose_train),
        ("refinement.pose_validation", metrics.n_pose_validation),
        ("refinement.pose_pilot_train", metrics.n_pose_pilot_train),
        ("refinement.pose_pilot_validation",
         metrics.n_pose_pilot_validation),
        ("refinement.dependencies", len(row.dependency_certificate_ids)),
        ("refinement.baseline_origin_y", float(baseline.origin_yx[0])),
        ("refinement.baseline_origin_x", float(baseline.origin_yx[1])),
        ("refinement.baseline_j00", baseline_matrix[0]),
        ("refinement.baseline_j01", baseline_matrix[1]),
        ("refinement.baseline_j10", baseline_matrix[2]),
        ("refinement.baseline_j11", baseline_matrix[3]),
        ("refinement.adopted_origin_y",
         None if adopted is None else float(adopted.origin_yx[0])),
        ("refinement.adopted_origin_x",
         None if adopted is None else float(adopted.origin_yx[1])),
        ("refinement.adopted_j00",
         None if not adopted_matrix else adopted_matrix[0]),
        ("refinement.adopted_j01",
         None if not adopted_matrix else adopted_matrix[1]),
        ("refinement.adopted_j10",
         None if not adopted_matrix else adopted_matrix[2]),
        ("refinement.adopted_j11",
         None if not adopted_matrix else adopted_matrix[3]),
    )
    return tuple(Detail(name, value) for name, value in values)


def color_refinement_details(
    row: ColorWindowRefinement,
) -> tuple[Detail, ...]:
    """Detach one color window's §7 refinement audit as scalars.

    The color arm's furniture sites are the pilot analog, so the detail
    vocabulary names them honestly rather than reusing the K pilot keys.
    """
    metrics = row.metrics
    baseline = row.baseline.segment.segment.pose
    adopted = (
        row.refined.segment.segment.pose if metrics.adopted else None)
    baseline_matrix = tuple(
        float(value) for value in baseline.matrix().ravel())
    adopted_matrix = (() if adopted is None else tuple(
        float(value) for value in adopted.matrix().ravel()))
    values: tuple[tuple[str, Scalar], ...] = (
        ("refinement.patch", row.patch_id),
        ("refinement.frontier", row.frontier_id),
        ("refinement.eligible", metrics.eligible),
        ("refinement.adopted", metrics.adopted),
        ("refinement.reason", metrics.reason),
        ("refinement.candidates", metrics.candidates),
        ("refinement.dtheta_deg", metrics.dtheta_deg),
        ("refinement.du_cells", metrics.du_cells),
        ("refinement.dv_cells", metrics.dv_cells),
        ("refinement.baseline_validation_logloss",
         metrics.baseline_validation_logloss),
        ("refinement.candidate_validation_logloss",
         metrics.candidate_validation_logloss),
        ("refinement.baseline_furniture_logloss",
         metrics.baseline_furniture_logloss),
        ("refinement.candidate_furniture_logloss",
         metrics.candidate_furniture_logloss),
        ("refinement.payload_train", metrics.n_payload_train),
        ("refinement.payload_validation", metrics.n_payload_validation),
        ("refinement.certified_blocks", metrics.n_certified_blocks),
        ("refinement.pose_train", metrics.n_pose_train),
        ("refinement.pose_validation", metrics.n_pose_validation),
        ("refinement.furniture_train", metrics.n_furniture_train),
        ("refinement.furniture_validation", metrics.n_furniture_validation),
        ("refinement.dependencies", len(row.dependency_certificate_ids)),
        ("refinement.baseline_origin_y", float(baseline.origin_yx[0])),
        ("refinement.baseline_origin_x", float(baseline.origin_yx[1])),
        ("refinement.baseline_j00", baseline_matrix[0]),
        ("refinement.baseline_j01", baseline_matrix[1]),
        ("refinement.baseline_j10", baseline_matrix[2]),
        ("refinement.baseline_j11", baseline_matrix[3]),
        ("refinement.adopted_origin_y",
         None if adopted is None else float(adopted.origin_yx[0])),
        ("refinement.adopted_origin_x",
         None if adopted is None else float(adopted.origin_yx[1])),
        ("refinement.adopted_j00",
         None if not adopted_matrix else adopted_matrix[0]),
        ("refinement.adopted_j01",
         None if not adopted_matrix else adopted_matrix[1]),
        ("refinement.adopted_j10",
         None if not adopted_matrix else adopted_matrix[2]),
        ("refinement.adopted_j11",
         None if not adopted_matrix else adopted_matrix[3]),
    )
    return tuple(Detail(name, value) for name, value in values)


def attempt_snapshot(
    row: TileAttemptRecord,
    evidence: TileAttemptView,
    components: Iterable[EvidenceBlock],
    spec: FormatSpec,
) -> object:
    """Build a live attempt view exactly matching its durable record fields."""
    del spec
    component_rows = tuple(components)
    component_ids = tuple(block.block_id for block in component_rows)
    if (evidence.address != (row.page, *row.tile_yx)
            or evidence.component_block_ids != row.component_block_ids
            or component_ids != evidence.component_block_ids):
        raise ValueError("attempt provenance changed before observation")
    return snapshots.attempt(
        row, component_block_ids=component_ids,
        dependency_certificate_ids=tuple(sorted({
            identity for block in component_rows
            for identity in block.dependency_certificate_ids()
        })),
        certificate_id=row.certificate_id)


def plane_field_details(row: PlaneFieldReport) -> tuple[Detail, ...]:
    """The PINNED PLANE-FIELDS analytics keys (docs/PLANE-FIELDS.md §6.2).

    NEW key names by ruling (§6.1 pitfall 6): ``color.registration.*``
    is the deployed residual's MEASURED namespace and is never reused,
    so the field mints ``plane_fields.*`` and the two can be read side
    by side on one lane.  The first three keys are the contract W5
    builds against; the rest are this arm's own cost and supply
    accounting, which a scheduled arm owes.

    KEY CASE.  The plane suffix is LOWERCASE (``…rms_dots.c``) because
    ``Detail`` names are validated against ``^[a-z][a-z0-9_.-]*$`` —
    there is no uppercase key anywhere in the event stream.  Plane names
    stay uppercase in VALUES (``plane_fields.adopted`` = ``"C,M"``),
    exactly as ``color.components_supported`` already spells them.
    """
    details: list[Detail] = [
        Detail(f"plane_fields.rms_dots.{name.lower()}", round(value, 4))
        for name, value in zip(PLANE_NAMES, row.rms_dots)
    ]
    details.extend((
        Detail("plane_fields.coverage", round(row.coverage, 4)),
        Detail("plane_fields.adopted", row.adopted_text),
        Detail("plane_fields.regions", row.regions),
        Detail(
            "plane_fields.regions_adopted",
            ",".join(
                f"{name}:{count}"
                for name, count in zip(
                    PLANE_NAMES, row.regions_adopted_by_plane))),
        Detail("plane_fields.samples", row.n_samples),
        Detail(
            "plane_fields.samples_by_source",
            ",".join(
                f"{source}:{count}"
                for source, count in sorted(row.samples_by_source.items()))),
        Detail("plane_fields.probes", row.n_probes),
        Detail("plane_fields.probe_sites", row.n_probe_sites),
        Detail("plane_fields.window_nulls", row.window_nulls),
        Detail("plane_fields.solve_seconds", round(row.solve_seconds, 4)),
        Detail("plane_fields.probe_seconds", round(row.probe_seconds, 4)),
    ))
    # The plane-COMMON residual: MEASURED, never applied (P5 writer work,
    # docs/COMPOSITE-POSE-DESIGN.md §6).  These keys say how large a pose
    # feedback WOULD be, in print dots along each window's own local axes,
    # and how consistent it is across the tiles inside one window.
    magnitudes = row.pose_residual_magnitudes()
    details.append(
        Detail("plane_fields.pose_residual_windows", len(magnitudes)))
    if magnitudes:
        details.extend((
            Detail("plane_fields.pose_residual_median_dots",
                   round(median(magnitudes), 4)),
            Detail("plane_fields.pose_residual_max_dots",
                   round(max(magnitudes), 4)),
            Detail("plane_fields.pose_residual_spread_dots", round(median([
                hypot(entry.spread_dx_dots, entry.spread_dy_dots)
                for entry in row.window_pose_residuals]), 4)),
        ))
    return tuple(details)


def color_region_details(row: ColorRegionSummary) -> tuple[Detail, ...]:
    component_rows = (
        tuple(zip(
            ("C", "M", "Y"),
            row.component_supported,
            row.component_support_reasons,
            strict=True,
        ))
        if row.component_supported else ()
    )
    details: list[Detail] = [
        Detail("color.region", row.region_id),
        Detail("color.page", row.page),
        Detail("color.accepted", row.accepted),
        Detail("color.reason", row.reason),
        Detail("color.patches", row.n_patches),
        Detail("color.train_sites", row.n_train),
        Detail("color.heldout_sites", row.n_heldout),
        Detail("color.class_counts",
               ",".join(str(value) for value in row.class_counts)),
        Detail("color.calibration_labels", row.calibration_labels),
        Detail(
            "color.components_supported",
            ",".join(
                stream_id
                for stream_id, supported, _reason in component_rows
                if supported
            ),
        ),
        Detail(
            "color.component_erasures",
            ",".join(
                f"{stream_id}:{reason}"
                for stream_id, _supported, reason in component_rows
                if reason is not None
            ),
        ),
        Detail("color.registration_adopted", row.registration_adopted),
        Detail("color.dependency_certificates",
               len(row.dependency_certificate_ids)),
    ]
    # PK4/PK4.1 (color-uplift P0, RECEIVE-DESIGN §6.2a A3): the per-window
    # photometric maps.  Emitted whenever the arm RAN — it is
    # kind-agnostic, so a cmy8 region reports these too — and the keys
    # separate verdicts one number would conflate: `.accepted` is how many
    # windows earned a map, `.reason` is the REGION-level verdict,
    # `.adopted` is whether the refitted model was taken.  `.reasons`
    # names every window's disposition in K's refusal vocabulary,
    # `.pooled` counts the windows too starved to fit alone, and
    # `.prior_labels` is the EFFECTIVE shrinkage constant this run fitted
    # with, so a swept run states its own number instead of leaving the
    # policy token to be believed.  The `cert_*` triple is the P6 PREVIEW
    # (report-only, gates nothing): the same region comparison as it would
    # have read on prior-barrier CERTIFIED payload cells.  These keys
    # appear on a `u*-a3` lane and nowhere else: since PK-CLEAN A3 is
    # reachable only from its supplemental lane.
    maps = row.window_photometry
    if maps.accepted or maps.refused:
        details.extend(
            Detail(f"color.window_maps.{key}", value) for key, value in (
                ("accepted", maps.accepted), ("refused", maps.refused),
                ("pooled", maps.pooled),
                ("reasons", ",".join(
                    f"{name}:{count}" for name, count in maps.reasons)),
                ("reason", maps.reason), ("adopted", maps.adopted),
                ("prior_labels", maps.prior_labels),
                ("cert_cells", maps.cert_cells),
                ("cert_incumbent_nll", maps.cert_incumbent_nll),
                ("cert_mapped_nll", maps.cert_mapped_nll)))
    # PK10 (color-uplift P9, RECEIVE-DESIGN §6.2a A4b): the
    # KnownField-conditioned marginals.  A nonempty reason IS the cmy8
    # discriminator — a cmy7 region has no conditioning and emits none of
    # these keys.  `.cells_arity1`/`.cells_arity2` count the emitted
    # per-plane MARGINALS certified siblings narrowed (2-vs-2 and
    # 1-vs-1); `.strata` names every (plane, pattern) stratum's
    # disposition and its material split `cert+masked`, so the
    # two-source provenance law is readable per region; the four NLL
    # pairs are the region gate exactly as it read it.
    conditioning = row.conditioning
    if conditioning.reason:
        details.extend((
            Detail("color.conditioning.reason", conditioning.reason),
            Detail("color.conditioning.adopted", conditioning.adopted),
            Detail("color.conditioning.cells_arity1",
                   conditioning.cells_arity1),
            Detail("color.conditioning.cells_arity2",
                   conditioning.cells_arity2),
        ))
        if conditioning.strata:
            details.extend((
                Detail("color.conditioning.strata_adopted",
                       conditioning.adopted_strata),
                Detail("color.conditioning.cert_cells",
                       conditioning.cert_cells),
                Detail("color.conditioning.masked_cells",
                       conditioning.masked_cells),
                Detail("color.conditioning.validation_cells",
                       conditioning.validation_cells),
                Detail(
                    "color.conditioning.strata",
                    ",".join(
                        f"{PLANE_ORDER[plane]}{pattern}:{reason}"
                        f":{n_cert}+{n_masked}"
                        for plane, pattern, reason, n_cert, n_masked
                        in conditioning.strata)),
                Detail(
                    "color.conditioning.strata_deltas",
                    ",".join(
                        f"{PLANE_ORDER[plane]}{pattern}"
                        f":t{total:+.4f}/w{word:+.4f}/d{dust:+.4f}"
                        for plane, pattern, total, word, dust
                        in conditioning.strata_deltas)),
                Detail("color.conditioning.incumbent_nll",
                       conditioning.incumbent_nll),
                Detail("color.conditioning.candidate_nll",
                       conditioning.candidate_nll),
                Detail("color.conditioning.word_incumbent_nll",
                       conditioning.word_incumbent_nll),
                Detail("color.conditioning.word_candidate_nll",
                       conditioning.word_candidate_nll),
                Detail("color.conditioning.dust_incumbent_nll",
                       conditioning.dust_incumbent_nll),
                Detail("color.conditioning.dust_candidate_nll",
                       conditioning.dust_candidate_nll),
            ))
    # PK5 (color-uplift P2, §6.2a A5): the neighbourhood corrector.
    # `.variant` names WHICH arm ran (the multi-state matrix; the
    # per-plane K port it was measured against is retired, §11.4/§12),
    # `.reason` the region verdict, `.curve_reasons`
    # every curve's disposition in K's vocabulary; `.labels_*` is the
    # two-source label reality (furniture against prior-barrier certified
    # payload cells) and `.binned_fraction` the arm's REACH — the share of
    # EMITTED cells whose 8-neighbourhood lay wholly inside the region.
    context = row.context
    if context.reason:
        details.extend(
            Detail(f"color.context.{key}", value) for key, value in (
                ("variant", context.variant), ("reason", context.reason),
                ("adopted", context.adopted),
                ("curves_adopted", context.curves_adopted),
                ("curves_total", context.curves_total),
                ("curve_reasons", ",".join(
                    f"{name}:{count}"
                    for name, count in context.curve_reasons)),
                ("labels_word", context.labels_word),
                ("labels_dust", context.labels_dust),
                ("labels_cert", context.labels_cert),
                ("search_cells", context.n_search),
                ("validation_cells", context.n_validation),
                ("binned_fraction", context.binned_fraction),
                ("incumbent_nll", context.incumbent_nll),
                ("candidate_nll", context.candidate_nll),
                ("word_incumbent_nll", context.word_incumbent_nll),
                ("word_candidate_nll", context.word_candidate_nll),
                ("dust_incumbent_nll", context.dust_incumbent_nll),
                ("dust_candidate_nll", context.dust_candidate_nll)))
    # P1 (color-uplift, RECEIVE-DESIGN §6.2a A4): the cmy7 head's verdict.
    # A nonempty reason IS the cmy7 discriminator — a cmy8 region has no
    # head and emits none of these keys.  `.temperature` is 1/a (>1 means
    # the head COOLED an overconfident detector); `.saturation_fraction`
    # is the share of emitted cells that hit the L-infinity bound, i.e.
    # the measured 19% pathology this arm exists to move.
    if row.cmy7_head_reason:
        details.extend((
            Detail("color.cmy7_head.adopted", row.cmy7_head_adopted),
            Detail("color.cmy7_head.reason", row.cmy7_head_reason),
            Detail("color.cmy7_head.temperature",
                   row.cmy7_head_temperature),
            Detail("color.cmy7_head.saturation_fraction",
                   row.cmy7_saturation_fraction),
        ))
        # PK3.1: the saturation FLOOR's own input — the same population's
        # PRE-head fraction — reported only where it was measured (a
        # fitted head actually reached the floor).  Where a head is then
        # applied, this is the "before" to `.saturation_fraction`'s
        # "after" WITHIN one run; `saturation_below_floor` in `.reason`
        # means this number fell under color_stack.HEAD_SATURATION_FLOOR.
        if row.cmy7_baseline_saturation_fraction >= 0.0:
            details.extend((
                Detail("color.cmy7_head.baseline_saturation_fraction",
                       row.cmy7_baseline_saturation_fraction),
                # PK4.1: and the EFFECTIVE floor it was judged against,
                # since the joint sweep gave that number a hatch too.
                Detail("color.cmy7_head.saturation_floor",
                       row.cmy7_head_saturation_floor),
            ))
    if row.baseline_heldout_logloss is not None:
        details.append(Detail(
            "color.baseline_heldout_logloss",
            row.baseline_heldout_logloss))
    if row.selected_heldout_logloss is not None:
        details.append(Detail(
            "color.selected_heldout_logloss",
            row.selected_heldout_logloss))
    # P8 (color-uplift): the `color.registration.*` keys report what
    # registration MEASURED — reading them as the applied correction and
    # inferring "no registration" from zeros is exactly the mistake this
    # event once invited.  Adoption is `color.registration_adopted`; the
    # applied correction is these residuals iff that flag is true, and
    # zeros mean registration measured no anchors (or never ran).
    for plane, residual in zip(("C", "M", "Y"), row.residuals, strict=True):
        key_plane = plane.lower()
        details.extend((
            Detail(f"color.registration.{key_plane}.intercept_x_dots",
                   residual.intercept_xy[0]),
            Detail(f"color.registration.{key_plane}.intercept_y_dots",
                   residual.intercept_xy[1]),
            Detail(f"color.registration.{key_plane}.slope_x_dots",
                   residual.slope_xy[0]),
            Detail(f"color.registration.{key_plane}.slope_y_dots",
                   residual.slope_xy[1]),
            Detail(f"color.registration.{key_plane}.anchors",
                   residual.n_anchors),
        ))
    return tuple(details)


__all__ = [
    "address_callbacks", "attempt_progress_callback", "attempt_snapshot",
    "color_refinement_details", "color_region_details", "install_adapter",
    "payload_region_callback", "plane_field_details",
    "refinement_details", "retry_summary_details",
]

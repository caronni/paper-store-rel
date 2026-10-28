"""Typed causal receive runtime with persistence and detached observers."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

from holo.format.descriptor import FormatSpec

from ._runtime_validation import (
    adopt_current_scale_plans as _adopt_current_scale_plans,
    policy_detach,
    validate_attempts as _validate_attempts,
    validate_bch_conflicts_for_spec as _validate_bch_conflicts_for_spec,
    validate_blocks_for_spec as _validate_blocks_for_spec,
    validate_certificates as _validate_certificates,
    validate_lane_request as _validate_lane_request,
    validate_page_domain_records as _validate_page_domain_records,
    validate_state_for_spec as _validate_state_for_spec,
)
from . import _diagnostic_snapshots as diagnostic_snapshots
from .cascade import release_derived_lanes, scale_plan
from .close_progress import CloseBlockProgress, CloseProgress
from .evidence_context import (
    EvidenceContext,
    build_evidence_context,
)
from .fountain_close import metadata_progress
from .records import certificate_for_close
from .observer import (
    EventSink as _EventSink,
    Observer,
    PolicyDetachWarning,
    ProvisionalReceiverWarning,
    ReceiverQualificationStatus,
    event_sink_for_run,
    provisional_warning_message,
)
from .runtime_model import (
    AddressProcessor,
    CaptureRun,
    CloseContext,
    CloseExecution,
    CloseProcessor,
    LaneAlgorithms,
    LaneContext,
    LaneExecution,
    LaneRequest,
    LaneStageOutput,
    MultiresScheduler,
    PayloadProcessor,
    ReceivePipeline,
    ReceiveRequest,
    ReceiveResult,
    ScheduleContext,
    SurveyProcessor,
)
from .scan import Raster, open_capture
from .session import (
    BarrierDelta,
    CaptureConflictError,
    CaptureFacts,
    CaptureRecord,
    CaptureStatus,
    LevelRecord,
    SessionIndex,
    SessionState,
    SessionStatus,
    append_level_barrier,
    apply_close,
    detach_close,
    authoritative_sha256,
    load_session_with_digest,
    save_session_with_digest,
)
from .types import (
    AddressProduct,
    CaptureInput,
    Detail,
    Disposition,
    EventAuthority,
    LaneSpec,
    PayloadProduct,
    Stage,
    StageDecision,
    SurveyProduct,
)


def _request_page_domain(request: ReceiveRequest) -> tuple[int, ...] | None:
    """Canonical durable page domain; ``None`` means the complete range."""
    pages = request.page_hypotheses
    if pages is None:
        return None
    if (len(pages) == request.spec.max_pages
            and all(page == index for index, page in enumerate(pages))):
        return None
    return pages


def _pipeline_page_domain(
    pipeline: ReceivePipeline, spec: FormatSpec,
) -> tuple[int, ...] | None:
    """Canonical executing domain; ``None`` means the complete range."""
    pages = pipeline.page_hypotheses
    if pages is None:
        return None
    if any(page >= spec.max_pages for page in pages):
        raise ValueError("receive pipeline page domain exceeds the format")
    if (len(pages) == spec.max_pages
            and all(page == index for index, page in enumerate(pages))):
        return None
    return pages


def _load_or_create(
    request: ReceiveRequest, pipeline: ReceivePipeline
) -> tuple[SessionState, str, bool]:
    path = Path(request.state_path) if request.state_path is not None else None
    if path is not None and path.exists():
        state, digest = (
            load_session_with_digest(
                path,
                format_row_id=request.spec.spec_id,
                defer_fountain_validation=True,
            )
            if request.defer_fountain_close
            else load_session_with_digest(
                path,
                format_row_id=request.spec.spec_id,
            )
        )
        return state, digest, False
    state = SessionState.create(
        request.spec.spec_id,
        pipeline.policy_id,
        _request_page_domain(request),
    )
    return state, authoritative_sha256(state), True


def _facts(item: CaptureInput, raster: Raster) -> CaptureFacts:
    source = raster.source
    return CaptureFacts(
        source.sha256, float(item.dpi),
        source.dtype, source.shape,
        source.channels)


def _metadata_matches(capture: CaptureRecord, facts: CaptureFacts) -> bool:
    return (
        capture.dpi, capture.dtype, capture.shape_yx, capture.channels,
    ) == (
        facts.dpi, facts.dtype, facts.shape_yx, facts.channels,
    )


def _run_lane(
    request: LaneRequest, evidence: EvidenceContext, *,
    facts: CaptureFacts, spec: FormatSpec,
    algorithms: LaneAlgorithms, events: _EventSink,
    defer_fountain_close: bool = False,
) -> LaneExecution:
    events.emit("lane.open", Stage.SCHEDULE, capture_id=facts.source_sha256,
                details=(Detail("lane.id", request.spec.lane_id),
                         Detail("lane.parent_id",
                                request.spec.parent_lane_id),
                         Detail("lane.ppc_num",
                                request.spec.target_ppc_num),
                         Detail("lane.ppc_den",
                                request.spec.target_ppc_den),
                         Detail("lane.effective_dpi", request.raster.dpi),
                         Detail("lane.native_per_view.num",
                                request.spec.native_per_view_num),
                         Detail("lane.native_per_view.den",
                                request.spec.native_per_view_den)),
                snapshot_factory=lambda: diagnostic_snapshots.lane(
                    request.raster, facts, request.spec, evidence))
    decisions: list[StageDecision] = []
    survey: SurveyProduct | None = None
    address: AddressProduct | None = None
    calls = ((Stage.SURVEY, algorithms.survey),
             (Stage.ADDRESS, algorithms.address), (Stage.PAYLOAD, algorithms.payload))
    for stage, processor in calls:
        context = LaneContext(
            stage, request.spec, spec, request.raster, facts,
            evidence, lambda: events.enabled,
            lambda: events.snapshots_enabled, events.emit,
            lambda name, callback, stage=stage: events.isolate_adapter(
                name, stage, facts.source_sha256, callback),
            defer_fountain_close)
        events.emit("stage.open", stage, capture_id=facts.source_sha256,
                    details=(Detail("lane.id", request.spec.lane_id),))
        timing_mark = events.begin_processor_timing()
        try:
            if stage is Stage.SURVEY:
                output = processor.process(context)  # type: ignore[union-attr]
            elif stage is Stage.ADDRESS:
                assert survey is not None
                output = processor.process(context, survey)  # type: ignore[union-attr]
            else:
                assert survey is not None and address is not None
                output = processor.process(  # type: ignore[union-attr]
                    context, survey, address)
        except BaseException:
            events.emit("stage.failed", stage, capture_id=facts.source_sha256,
                        message="processor failed before its barrier",
                        details=(Detail("lane.id", request.spec.lane_id),)
                        + events.finish_processor_timing(timing_mark))
            raise
        timing_details = events.finish_processor_timing(timing_mark)
        if not isinstance(output, LaneStageOutput):
            raise TypeError(f"{stage.value} processor returned an invalid output")
        decision = output.decision
        if decision.stage is not stage:
            raise ValueError(f"{stage.value} processor returned another stage")
        expected_type = {Stage.SURVEY: SurveyProduct,
                         Stage.ADDRESS: AddressProduct,
                         Stage.PAYLOAD: PayloadProduct}[stage]
        if output.product is not None and not isinstance(output.product, expected_type):
            raise TypeError(f"{stage.value} processor returned the wrong product")
        decisions.append(decision)
        if decision.disposition is not Disposition.COMPLETE:
            events.emit(
                "stage.refused", stage, capture_id=facts.source_sha256,
                message=decision.reason,
                details=(Detail("lane.id", request.spec.lane_id),)
                + timing_details)
            return LaneExecution(
                tuple(decisions), survey, address)
        if stage is Stage.SURVEY:
            survey = output.product  # type: ignore[assignment]
        elif stage is Stage.ADDRESS:
            address = output.product  # type: ignore[assignment]
        elif output.replacement_address is not None:
            # E023c may revise continuous pose geometry from certificates
            # committed before this lane.  The payload processor has already
            # rerun ordinary E023b from the revised current-lane pixels; the
            # same atomic level barrier must therefore retain that geometry,
            # not the generation-zero proposal it superseded.
            address = output.replacement_address
        events.emit("stage.complete", stage, capture_id=facts.source_sha256,
                    details=(Detail("lane.id", request.spec.lane_id),)
                    + timing_details)
    return LaneExecution(
        tuple(decisions), survey, address, output.product)  # type: ignore[arg-type]


def _plan_bound(
    plan: tuple[LaneSpec, ...], *, run_mopup: bool, run_refine: bool,
) -> int:
    """The invocation's flag-bounded plan-prefix length (v0.42).

    Default: the ordinary ladder only (stop before the first M entry);
    ``run_mopup``: through the M-levels (stop before the first R entry);
    ``run_refine``: the whole plan — by the plan-prefix law this includes
    any pending M-levels.  Committed prefixes are always honored: the
    bound limits how far THIS invocation may drive, never what a prior
    invocation committed.

    PK4.3: the color plan's supplemental tail rides ``run_refine`` — it
    is the plan's last family and ``--refine`` means "the whole plan".
    No fifth flag: a u-lane is monotone by construction, so there is
    nothing for an operator to weigh, and a flag would only invite the
    belief that there is.
    """
    if run_refine:
        return len(plan)
    if run_mopup:
        return next(
            (ordinal for ordinal, lane in enumerate(plan)
             if lane.refine_of is not None or lane.uplift_of is not None),
            len(plan))
    return next(
        (ordinal for ordinal, lane in enumerate(plan)
         if lane.mopup_of is not None or lane.refine_of is not None
         or lane.uplift_of is not None),
        len(plan))


@dataclass(slots=True)
class _CaptureSlot:
    """One requested capture held open across the phased session drive.

    v0.33: native rasters stay open for the whole invocation (D10); the
    phase cursor is derived from the capture's prefix length, never stored.
    v0.42: ``bound`` is the invocation's flag-bounded plan-prefix length;
    ``next_lane`` returns nothing at or beyond it.
    """

    position: int
    item: CaptureInput
    raster: Raster
    facts: CaptureFacts
    plan: tuple[LaneSpec, ...]
    bound: int
    barriers_committed: int = 0

    def next_lane(self, state: SessionState) -> LaneSpec | None:
        current = state.capture(self.facts.source_sha256)
        ordinal = 0 if current is None else len(current.levels)
        return self.plan[ordinal] if ordinal < self.bound else None


def _finalize_deferred_close(
    state: SessionState,
    spec: FormatSpec,
    pipeline: ReceivePipeline,
    events: _EventSink,
    state_path: str | Path | None,
    persist_state: Callable[[SessionState], tuple[bool, str]] | None = None,
    close_progress_sink: list[
        Callable[[], CloseProgress | None]] | None = None,
) -> tuple[
    SessionState,
    bytes | None,
    str | None,
    Callable[[], object],
]:
    """Run and retain the invocation's sole deferred fountain close.

    The returned digest is the committed-view base only when the close changed
    durable state.  This lets the terminal diagnostic summary advance the
    observer mirror without inventing another lane barrier.
    """
    if state.status is not SessionStatus.OPEN:
        raise ValueError("deferred close requires an open session")
    base_digest = events.state_sha256
    close = pipeline.close.process(CloseContext(spec, state))
    if not isinstance(close, CloseExecution):
        raise TypeError("close processor returned a non-CloseExecution")
    if close_progress_sink is not None:
        close_progress_sink[:] = [close.diagnostic_progress]
    close_snapshot = diagnostic_snapshots.close_factory(
        state, close.record, close.diagnostic_progress, spec)
    events.emit(
        "close.check",
        Stage.CLOSE,
        details=(
            Detail("close.status", close.record.status.value),
            Detail("close.deferred", True),
            Detail("close.certificates", len(state.certificates)),
        ),
        snapshot_factory=close_snapshot,
    )
    candidate = apply_close(state, close.record)
    if candidate == state:
        return state, close.payload, None, close_snapshot

    digest: str | None = None
    if persist_state is not None:
        _changed, digest = persist_state(candidate)
    elif state_path is not None:
        _changed, digest = save_session_with_digest(
            state_path, candidate, validate=False)
    elif events.enabled:
        digest = authoritative_sha256(candidate)
    if digest is not None:
        events.bind_state(digest)
    return candidate, close.payload, base_digest, close_snapshot


def _replay_deferred_close(
    state: SessionState,
    spec: FormatSpec,
    pipeline: ReceivePipeline,
    events: _EventSink,
    close_progress_sink: list[
        Callable[[], CloseProgress | None]] | None = None,
) -> tuple[bytes | None, Callable[[], object]]:
    """Reproduce one retained close once in the deferred final phase.

    Unlike :func:`_finalize_deferred_close`, this never applies a transition:
    it checks that an existing OPEN or terminal record still reproduces from
    its certified frontier. Terminal state therefore remains immutable.
    The reproduced progress still publishes (a rerun of a terminal state
    prints the same D15/D16 epilogues its first verifying run printed).
    """
    close = pipeline.close.process(CloseContext(spec, state))
    if not isinstance(close, CloseExecution):
        raise TypeError("close processor returned a non-CloseExecution")
    if close.record != state.close:
        raise RuntimeError(
            "deferred final close replay differs from retained state")
    if close_progress_sink is not None:
        close_progress_sink[:] = [close.diagnostic_progress]
    if (
        state.status is SessionStatus.VERIFIED
        and close.payload is None
    ):
        raise RuntimeError(
            "verified deferred close replay omitted payload bytes")
    close_snapshot = diagnostic_snapshots.close_factory(
        state, close.record, close.diagnostic_progress, spec)
    events.emit(
        "close.check",
        Stage.CLOSE,
        details=(
            Detail("close.status", close.record.status.value),
            Detail("close.deferred", True),
            Detail("close.certificates", len(state.certificates)),
        ),
        snapshot_factory=close_snapshot,
    )
    return close.payload, close_snapshot


def _emit_session_complete(
    state: SessionState,
    spec: FormatSpec,
    events: _EventSink,
    *,
    close_base_state_sha256: str | None = None,
    close_snapshot_factory: Callable[[], object] | None = None,
) -> str | None:
    digest = events.state_sha256
    if events.enabled and digest is None:
        digest = authoritative_sha256(state)
        events.bind_state(digest)
    events.emit(
        "session.complete",
        Stage.CLOSE,
        details=(
            Detail("session.status", state.status.value),
            Detail("captures.retained", len(state.captures)),
            Detail("state.sha256", digest),
        ),
        authority=EventAuthority.COMMITTED,
        snapshot_factory=lambda: diagnostic_snapshots.session_summary(
            state,
            spec,
            base_state_sha256=close_base_state_sha256,
            close_value=(
                None
                if close_snapshot_factory is None
                else close_snapshot_factory()
            ),
        ),
    )
    return digest


def _execute_receive(
    request: ReceiveRequest, selected: ReceivePipeline, events: _EventSink, *,
    initial_state: SessionState | None = None, initial_digest: str | None = None,
    persist_state: Callable[[SessionState], tuple[bool, str]] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    finalize_deferred_close: bool = True,
    emit_terminal_summary: bool = True,
) -> ReceiveResult:
    request_domain = _request_page_domain(request)
    if _pipeline_page_domain(selected, request.spec) != request_domain:
        raise ValueError(
            "receive pipeline has a different page domain from the request")
    if initial_state is None:
        state, loaded_digest, session_created = _load_or_create(
            request, selected)
    else:
        state = initial_state
        loaded_digest = (authoritative_sha256(state) if initial_digest is None
                         else initial_digest)
        session_created = False
    if not finalize_deferred_close and state.status is not SessionStatus.OPEN:
        # --no-close on a terminal state DETACHES the close (user ruling
        # 2026-08-19): the run behaves as if no close ever existed — new
        # captures ingest, certificates accumulate, and a later closing
        # run recomputes the close from the full certificate set.  The
        # loaded digest stays the on-disk digest so the first barrier
        # save persists the detached state as a real change.
        state = detach_close(state)
    events.bind_state(loaded_digest)
    if selected.qualification_status is ReceiverQualificationStatus.PROVISIONAL:
        events.emit(
            "receiver.provisional", Stage.INGEST,
            message=provisional_warning_message(
                selected.qualification_notes),
            details=(
                Detail("receiver.qualification_status", "provisional"),
                Detail("receiver.qualification_blockers",
                       len(selected.qualification_notes)),
                Detail("session.created", session_created),
            ),
        )
    _validate_state_for_spec(state, request.spec)
    # The plan-prefix rule (``_runtime_validation.scale_plan_tail``): a
    # capture recorded before a lane family joined the ladder owes today's
    # appended tail, so the record adopts today's plan here — before
    # ``started``, exactly like the ``--no-close`` detach above, so a run
    # that drives no barrier still reports itself unchanged and the loaded
    # digest stays the on-disk one.
    state = _adopt_current_scale_plans(state, request.spec)
    # The policy-detach rule (``_runtime_validation.policy_detach``,
    # RECEIVE-DESIGN §9c): a state minted under an older receiver policy
    # CONTINUES under today's, keeping its certificates and word-validated
    # poses and dropping the intermediates the moved components produced.
    # Same placement as the two repairs above, for the same reason.
    detach = policy_detach(state, selected.policy_id)
    if detach is not None:
        state = detach.state
        warnings.warn(
            detach.message, PolicyDetachWarning, stacklevel=3)
        events.emit(
            "session.policy_detach", Stage.INGEST, message=detach.message,
            details=(
                Detail("receiver.policy_id.previous",
                       detach.previous_policy_id),
                Detail("receiver.policy_id", selected.policy_id),
                Detail("policy.segments_moved",
                       ",".join(detach.segments_moved)),
                Detail("policy.epoch", len(state.policy_lineage) + 1),
                *(Detail(f"policy.kept.{label.replace(' ', '_')}", count)
                  for label, count in detach.kept),
                *(Detail(f"policy.dropped.{label.replace(' ', '_')}", count)
                  for label, count in detach.dropped),
            ),
        )
    started = state
    index = SessionIndex(state, spec=request.spec, validate=False)
    if state.receiver_policy_id != selected.policy_id:
        # Unreachable while ``policy_detach`` is total (it returns a state
        # under ``selected.policy_id`` or raises, naming the reason); kept
        # as the standing invariant this whole block exists to establish.
        raise ValueError("receive state belongs to a different policy")
    if state.page_hypotheses != request_domain:
        raise ValueError("receive state belongs to a different page domain")
    runs: list[CaptureRun] = []
    payload: bytes | None = None
    events.emit("session.open", Stage.INGEST,
                details=(Detail("captures.requested", len(request.captures)),
                         Detail("captures.retained", len(state.captures)),
                         Detail("session.created", session_created),
                         Detail("format.id", request.spec.spec_id),
                         Detail("receiver.policy_id", selected.policy_id),
                         Detail(
                             "receiver.page_domain",
                             "all" if request_domain is None else
                             ",".join(str(page) for page in request_domain))),
                authority=EventAuthority.COMMITTED,
                snapshot_factory=lambda: diagnostic_snapshots.committed(
                    state, request.spec))
    close_progress_sink: list[Callable[[], CloseProgress | None]] = []
    spec = request.spec

    # ---- v0.33 session phase driver -----------------------------------
    # Open every requested capture, then advance all of them rung-major by
    # target ppc, then run the priced mop-up tail (RECEIVE-DESIGN §8,
    # docs/PHASED-SCHEDULE.md D1/D2/D9/D10).
    outcomes: dict[int, CaptureRun] = {}
    repeated: list[tuple[int, str]] = []
    slots: list[_CaptureSlot] = []
    context_sha: str | None = None
    for position, item in enumerate(request.captures):
        if state.status is not SessionStatus.OPEN:
            break
        raster = open_capture(item.source, item.dpi)
        facts = _facts(item, raster)
        context_sha = facts.source_sha256
        events.emit("capture.open", Stage.INGEST,
                    capture_id=facts.source_sha256)
        if (item.expected_sha256 is not None
                and facts.source_sha256 != item.expected_sha256):
            raise CaptureConflictError(
                "capture source SHA differs from manifest")
        by_id = index.captures.get(facts.source_sha256)
        if by_id is not None and not _metadata_matches(by_id, facts):
            raise CaptureConflictError("duplicate source metadata conflicts")
        if by_id is not None and by_id.status is CaptureStatus.COMPLETE:
            events.emit("capture.duplicate", Stage.INGEST,
                        capture_id=facts.source_sha256,
                        details=(Detail("source.sha256",
                                        facts.source_sha256),),
                        authority=EventAuthority.COMMITTED)
            outcomes[position] = CaptureRun(
                facts.source_sha256, CaptureStatus.COMPLETE)
            continue
        if any(slot.facts.source_sha256 == facts.source_sha256
               for slot in slots):
            # A repeated in-request source advances through its first slot;
            # this row resolves to the shared final status below.
            repeated.append((position, facts.source_sha256))
            continue
        events.emit("ingest.complete", Stage.INGEST,
                    capture_id=facts.source_sha256,
                    details=(Detail("source.sha256", facts.source_sha256),
                             Detail("source.height", facts.shape_yx[0]),
                             Detail("source.width", facts.shape_yx[1])))
        plan = scale_plan(
            raster.dpi, spec.cell_dots,
            codec_family=spec.codec_family, n_streams=spec.n_streams)
        slots.append(_CaptureSlot(
            position, item, raster, facts, plan,
            _plan_bound(
                plan,
                run_mopup=request.run_mopup,
                run_refine=request.run_refine)))
    requested_shas = (
        {slot.facts.source_sha256 for slot in slots}
        | {run.source_sha256 for run in outcomes.values()}
        | {sha for _position, sha in repeated})
    if state.status is SessionStatus.OPEN:
        # A terminal session accepts any request: its capture drive no-ops
        # and the close replays below.  Only an OPEN session owes the
        # multi-ACTIVE resume duty (a terminal session legally retains
        # ACTIVE captures that close preemption skipped, v0.33).
        for row in state.captures:
            if (row.status is CaptureStatus.ACTIVE
                    and row.source_sha256 not in requested_shas):
                raise ValueError(
                    "a resume request must include every active capture")

    def slot_context(slot: _CaptureSlot) -> ScheduleContext:
        facts, plan, raster = slot.facts, slot.plan, slot.raster

        def run_lane(lane_request: LaneRequest,
                     evidence: EvidenceContext) -> LaneExecution:
            current = state.capture(facts.source_sha256)
            ordinal = 0 if current is None else len(current.levels)
            if ordinal >= len(plan):
                raise ValueError("lane execution lies beyond the scale plan")
            _validate_lane_request(lane_request, facts, plan[ordinal])
            return _run_lane(
                lane_request, evidence, facts=facts, spec=spec,
                algorithms=selected.lanes, events=events,
                defer_fountain_close=request.defer_fountain_close)

        def evidence_for(lane: LaneSpec) -> EvidenceContext:
            return build_evidence_context(index, facts, lane, plan)

        def commit(level: LevelRecord, delta: BarrierDelta) -> SessionState:
            nonlocal state, payload
            base_digest = events.state_sha256
            assert base_digest is not None
            current = state.capture(facts.source_sha256)
            ordinal = 0 if current is None else len(current.levels)
            if ordinal >= len(plan):
                raise ValueError("level commit lies beyond the scale plan")
            lane = plan[ordinal]
            _validate_page_domain_records(
                delta, state.page_hypotheses, spec)
            _validate_bch_conflicts_for_spec(
                level.address, state.page_hypotheses, spec)
            _validate_blocks_for_spec(delta.blocks, spec)
            _validate_attempts(delta.attempts, spec)
            _validate_certificates(delta.certificates, spec)
            candidate = append_level_barrier(
                state, index, facts, plan, level, delta)
            if request.defer_fountain_close:
                close = None
                # K falls out of the certified LDPC metadata word, not out
                # of the fountain solve, so a deferred close still publishes
                # it (lazily, only when a viewer opted in). Symbol/block
                # counts stay deferred.  metadata_progress consumes
                # CertifiedStreamSymbol rows, so the durable certificate
                # records convert inside the lazy thunk.
                close_snapshot = diagnostic_snapshots.close_factory(
                    candidate, candidate.close,
                    lambda: metadata_progress(
                        tuple(certificate_for_close(row, spec)
                              for row in candidate.certificates),
                        spec), spec)
            else:
                close = selected.close.process(
                    CloseContext(spec, candidate))
                if not isinstance(close, CloseExecution):
                    raise TypeError(
                        "close processor returned a non-CloseExecution")
                close_progress_sink[:] = [close.diagnostic_progress]
                close_snapshot = diagnostic_snapshots.close_factory(
                    candidate, close.record, close.diagnostic_progress,
                    spec)
                events.emit(
                    "close.check", Stage.CLOSE,
                    capture_id=facts.source_sha256,
                    details=(Detail("lane.id", lane.lane_id),
                             Detail("level.ordinal", ordinal),
                             Detail("close.status",
                                    close.record.status.value),
                             Detail("close.new_certificates",
                                    len(delta.certificates))),
                    snapshot_factory=close_snapshot,
                )
                candidate = apply_close(candidate, close.record)
            raster.verify_source_unchanged()
            digest: str | None = None
            if persist_state is not None:
                _changed, digest = persist_state(candidate)
            elif request.state_path is not None:
                _changed, digest = save_session_with_digest(
                    request.state_path, candidate, validate=False)
            elif events.enabled:
                digest = authoritative_sha256(candidate)
            index.accept(candidate, delta)
            state = candidate
            payload = None if close is None else close.payload
            if digest is not None:
                events.bind_state(digest)
            events.emit(
                "barrier.committed", Stage.SCHEDULE,
                capture_id=facts.source_sha256,
                details=(Detail("lane.id", lane.lane_id),
                         Detail("level.ordinal", ordinal),
                         Detail("session.status", candidate.status.value),
                         Detail("state.sha256", digest)),
                authority=EventAuthority.COMMITTED,
                snapshot_factory=lambda: diagnostic_snapshots.barrier(
                    candidate, delta, base_digest, facts.source_sha256,
                    close_snapshot(), spec))
            slot.barriers_committed += 1
            return candidate

        return ScheduleContext(
            spec, raster, facts, state.capture(facts.source_sha256),
            run_lane, evidence_for, commit, events.emit,
            lambda: stop_requested is not None and stop_requested())

    # The stop contract is per-level, checked AFTER each committed barrier
    # (the cascade's historical granularity): a request that arrives
    # stopped still commits exactly one barrier per its first advance.
    stopped = False

    def advance(slot: _CaptureSlot) -> None:
        nonlocal context_sha, stopped
        if context_sha != slot.facts.source_sha256:
            events.emit("capture.resume", Stage.SCHEDULE,
                        capture_id=slot.facts.source_sha256)
            context_sha = slot.facts.source_sha256
        execution = selected.scheduler.process(slot_context(slot))
        if execution is not None:
            raise TypeError("scheduler must not return state or policy")
        if stop_requested is not None and stop_requested():
            stopped = True

    rungs = sorted({
        Fraction(lane.target_ppc_num, lane.target_ppc_den)
        for slot in slots
        for lane in slot.plan
        if lane.mopup_of is None and lane.refine_of is None
        and lane.uplift_of is None})

    def tail_ev(slot: _CaptureSlot) -> tuple[int, int, int]:
        lane = slot.next_lane(state)
        assert lane is not None
        # v0.42: mop-up levels run before any refinement level session-wide
        # (class rank), so every R(Lk) address sees the maximal accumulated
        # certificate frontier.  Within the mop-up class the EV order is
        # unchanged (parked support, descending); refinement levels follow
        # in plan order via the request-position tiebreak.
        # PK4.3: supplemental levels rank BELOW refinement levels for the
        # same reason one class lower — a u-lane reads the residue, so it
        # must run after every lane that could still shrink it.
        lane_class = (
            -1 if lane.uplift_of is not None
            else 0 if lane.refine_of is not None
            else 1)
        weight = sum(
            row.support_cells for row in state.parked
            if row.capture_id == slot.facts.source_sha256
            and row.lane_id == lane.mopup_of)
        return (lane_class, weight, -slot.position)

    try:
        for rung in rungs:
            if state.status is not SessionStatus.OPEN or stopped:
                break
            events.emit(
                "session.phase", Stage.SCHEDULE,
                details=(Detail("phase.kind", "rung"),
                         Detail("phase.ppc", str(rung)),
                         Detail("phase.captures", len(slots))))
            for slot in slots:
                if state.status is not SessionStatus.OPEN or stopped:
                    break
                lane = slot.next_lane(state)
                if (lane is not None and lane.mopup_of is None
                        and lane.refine_of is None
                        and lane.uplift_of is None
                        and Fraction(lane.target_ppc_num,
                                     lane.target_ppc_den) == rung):
                    advance(slot)

        tail_announced = False
        while state.status is SessionStatus.OPEN and not stopped:
            pending = [slot for slot in slots
                       if slot.next_lane(state) is not None]
            if not pending:
                break
            if not tail_announced:
                events.emit(
                    "session.phase", Stage.SCHEDULE,
                    details=(Detail("phase.kind", "tail"),
                             Detail("phase.parked", len(state.parked))))
                tail_announced = True
            advance(max(pending, key=tail_ev))
    finally:
        # v0.37 (plan 3.4): the drive is over — free every derived-lane
        # mmap this invocation pooled.  Native rasters stay open (D10).
        for slot in slots:
            release_derived_lanes(slot.raster)

    for slot in slots:
        current = state.capture(slot.facts.source_sha256)
        if current is None:
            if state.status is SessionStatus.OPEN and not stopped:
                raise RuntimeError(
                    "scheduler completed without committing a capture "
                    "barrier")
            status = CaptureStatus.ACTIVE
        else:
            status = current.status
        events.emit(
            "capture.complete" if status is CaptureStatus.COMPLETE
            else "capture.active",
            Stage.SCHEDULE,
            capture_id=slot.facts.source_sha256,
            details=(Detail("capture.status", status.value),
                     Detail("capture.barriers_committed",
                            slot.barriers_committed)),
            authority=(EventAuthority.COMMITTED
                       if slot.barriers_committed
                       else EventAuthority.TRANSIENT),
        )
        outcomes[slot.position] = CaptureRun(
            slot.facts.source_sha256, status,
            slot.barriers_committed, slot.barriers_committed > 0)
    for position, sha in repeated:
        record = state.capture(sha)
        outcomes[position] = CaptureRun(
            sha,
            CaptureStatus.ACTIVE if record is None else record.status)
    runs = [outcomes[position] for position in sorted(outcomes)]
    close_base_state_sha256: str | None = None
    final_close_snapshot_factory: Callable[[], object] | None = None
    deferred_close_completed = False
    # v0.42 corrected --complete semantics: the one deferred close runs
    # when the work THIS invocation was asked to run is exhausted — every
    # requested capture has committed its flag-bounded plan prefix — not
    # only at full-plan CaptureStatus.COMPLETE.  A --complete run without
    # the lane flags therefore legally ends OPEN (or closes, if the
    # bounded frontier already verifies) with parked lane families, and
    # is resumable.
    bounded_exhausted = (
        not stopped
        and all(slot.next_lane(state) is None for slot in slots))
    if (
        request.defer_fountain_close
        and finalize_deferred_close
        and state.status is SessionStatus.OPEN
        and len(runs) == len(request.captures)
        and bounded_exhausted
    ):
        (
            state,
            payload,
            close_base_state_sha256,
            final_close_snapshot_factory,
        ) = _finalize_deferred_close(
            state,
            request.spec,
            selected,
            events,
            request.state_path,
            persist_state,
            close_progress_sink=close_progress_sink,
        )
        deferred_close_completed = True
    if (
        request.defer_fountain_close
        and finalize_deferred_close
        and not deferred_close_completed
        and state.status is not SessionStatus.OPEN
    ):
        payload, final_close_snapshot_factory = _replay_deferred_close(
            state,
            request.spec,
            selected,
            events,
            close_progress_sink=close_progress_sink,
        )
        deferred_close_completed = True
    elif (
        not request.defer_fountain_close
        and state.status is SessionStatus.VERIFIED
        and payload is None
    ):
        close = selected.close.process(CloseContext(request.spec, state))
        if (not isinstance(close, CloseExecution)
                or close.record != state.close or close.payload is None):
            raise RuntimeError(
                "verified resume requires the installed close processor to "
                "reproduce the payload")
        # A verified reproduction publishes its progress too, so the D16
        # surplus epilogue re-prints on reruns of the terminal state.
        close_progress_sink[:] = [close.diagnostic_progress]
        payload = close.payload
    if emit_terminal_summary:
        digest = _emit_session_complete(
            state,
            request.spec,
            events,
            close_base_state_sha256=close_base_state_sha256,
            close_snapshot_factory=final_close_snapshot_factory,
        )
    else:
        digest = events.state_sha256
        if events.enabled and digest is None:
            digest = authoritative_sha256(state)
            events.bind_state(digest)
    return ReceiveResult(
        state,
        tuple(runs),
        state != started,
        events.failures,
        payload,
        qualification_status=selected.qualification_status,
        qualification_notes=selected.qualification_notes,
        authoritative_digest=(
            digest if (request.state_path is not None or state == started
                       or events.enabled) else None),
        close_progress_factory=(
            close_progress_sink[0] if close_progress_sink else None),
    )


def _safe_exception_text(exc: BaseException) -> str:
    try:
        return str(exc)
    except BaseException:
        return "<exception text unavailable>"


def run_receive(
    request: ReceiveRequest, *, pipeline: ReceivePipeline | None = None,
    observer: Observer | None = None,
    finalize_deferred_close: bool = True) -> ReceiveResult:
    """Run/resume with per-level fsync; the implicit production policy warns
    while physical placement qualification remains outstanding.

    ``finalize_deferred_close=False`` is the --no-close mode (semantics
    table in RECEIVE-DESIGN): the close layer is never entered — no
    closing record is read on replay (deferred fountain validation), no
    close is attempted, none is written, and a terminal state is
    DETACHED back to OPEN so accumulation can continue.  It implies the
    non-greedy deferral (--complete alongside is legal and redundant);
    the caller must set ``request.defer_fountain_close`` accordingly."""
    if not finalize_deferred_close and not request.defer_fountain_close:
        raise ValueError(
            "--no-close mode needs the deferred close: greedy per-barrier "
            "close attempts would contradict never-close; set "
            "request.defer_fountain_close")
    if pipeline is None:
        from .production import production_pipeline
        selected = production_pipeline(request)
    else:
        selected = pipeline
    events = event_sink_for_run(
        observer,
        selected.qualification_status,
        selected.qualification_notes,
        format_id=request.spec.spec_id,
        receiver_policy_id=selected.policy_id,
        page_domain=(tuple(range(request.spec.max_pages))
                     if request.page_hypotheses is None
                     else request.page_hypotheses),
    )
    try:
        return _execute_receive(
            request, selected, events,
            finalize_deferred_close=finalize_deferred_close)
    except BaseException as exc:
        events.emit(
            "run.failed", Stage.CLOSE,
            message=_safe_exception_text(exc),
            details=(Detail("failure.type", type(exc).__name__),),
        )
        raise


__all__ = [
    "AddressProcessor", "CaptureRun", "CloseBlockProgress", "CloseContext",
    "CloseExecution", "CloseProgress", "CloseProcessor",
    "EvidenceContext", "LaneAlgorithms", "LaneContext", "LaneExecution",
    "LaneRequest", "LaneStageOutput", "MultiresScheduler", "Observer",
    "PayloadProcessor", "PolicyDetachWarning", "ProvisionalReceiverWarning",
    "ReceivePipeline",
    "ReceiveRequest", "ReceiveResult", "ReceiverQualificationStatus",
    "ScheduleContext",
    "SurveyProcessor", "run_receive",
]

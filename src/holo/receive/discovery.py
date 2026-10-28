"""Discovery-first, receiver-wide orchestration over exact-row branches."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from typing import Callable
import warnings

from ..format.descriptor import FormatSpec
from ..format.registry import get_format_row, registered_format_rows
from . import _diagnostic_snapshots as diagnostic_snapshots
from .discovery_state import (
    DiscoveryState,
    DiscoveryStatus,
    DiscoverySurvey,
    authoritative_discovery_sha256,
    load_discovery_with_digest,
    save_discovery_with_digest,
)
from .observer import (
    EventSink,
    Observer,
    ProvisionalReceiverWarning,
    ReceiverQualificationStatus,
    event_sink_for_run,
    provisional_warning_message,
)
from .place import PlacementConfig
from .placement.policy import PlacementDomainEnvelope
from .production import production_pipeline
from .runtime import (
    CloseContext,
    CloseExecution,
    ReceivePipeline,
    ReceiveRequest,
    _emit_session_complete,
    _execute_receive,
    _finalize_deferred_close,
    _replay_deferred_close,
)
from .scan import open_capture
from .session import (
    CaptureFacts,
    CaptureStatus,
    SessionState,
    SessionStatus,
    authoritative_sha256 as authoritative_session_sha256,
)
from .survey import survey_raster
from .types import CaptureInput, Detail, EventAuthority, Stage


_DISCOVERY_POLICY_SCHEMA = "holo/discovery-receiver/v6"


@dataclass(frozen=True, slots=True)
class DiscoveryReceiveRequest:
    """Discovery-mode receive invocation.

    ``run_mopup``/``run_refine`` (v0.42) are the same invocation-only
    scheduling flags as :class:`ReceiveRequest`'s: each branch's phased
    drive is flag-bounded identically (default = ordinary ladder only;
    ``run_mopup`` through M-levels; ``run_refine`` through everything).
    """

    captures: tuple[CaptureInput, ...]
    state_path: str | Path | None = None
    candidate_row_ids: tuple[str, ...] | None = None
    page_hypotheses: tuple[int, ...] | None = None
    defer_fountain_close: bool = False
    run_mopup: bool = False
    run_refine: bool = False

    def __post_init__(self) -> None:
        if not self.captures:
            raise ValueError("discovery receive needs at least one capture")
        if type(self.defer_fountain_close) is not bool:
            raise TypeError("defer_fountain_close must be bool")
        if type(self.run_mopup) is not bool:
            raise TypeError("run_mopup must be bool")
        if type(self.run_refine) is not bool:
            raise TypeError("run_refine must be bool")
        if self.candidate_row_ids is not None and (
                not self.candidate_row_ids
                or len(set(self.candidate_row_ids))
                != len(self.candidate_row_ids)):
            raise ValueError(
                "candidate row ids must be unique and non-empty")
        if self.page_hypotheses is not None:
            pages = tuple(dict.fromkeys(self.page_hypotheses))
            if (not pages or any(type(page) is not int or page < 0
                                 for page in pages)
                    or pages != self.page_hypotheses):
                raise ValueError(
                    "page hypotheses must be unique nonnegative integers")


@dataclass(frozen=True, slots=True)
class DiscoveryReceiveResult:
    state: DiscoveryState
    state_changed: bool
    payload: bytes | None = None
    qualification_status: ReceiverQualificationStatus = (
        ReceiverQualificationStatus.PROVISIONAL)
    qualification_notes: tuple[str, ...] = ()
    authoritative_digest: str | None = None
    observer_failures: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.state.status is DiscoveryStatus.VERIFIED

    @property
    def authoritative_sha256(self) -> str:
        return (
            self.authoritative_digest
            if self.authoritative_digest is not None
            else authoritative_discovery_sha256(self.state)
        )


ObserverFactory = Callable[[FormatSpec, ReceivePipeline], Observer | None]


def _page_domain(
    spec: FormatSpec,
    requested: tuple[int, ...] | None,
) -> tuple[tuple[int, ...], tuple[int, ...] | None] | None:
    pages = (
        tuple(range(spec.max_pages))
        if requested is None
        else tuple(page for page in requested if page < spec.max_pages)
    )
    if not pages:
        return None
    durable = (
        None
        if len(pages) == spec.max_pages
        and all(page == index for index, page in enumerate(pages))
        else pages
    )
    return pages, durable


def _candidate_layout(
    request: DiscoveryReceiveRequest,
) -> tuple[
    tuple[tuple[FormatSpec, tuple[int, ...], tuple[int, ...] | None], ...],
    PlacementDomainEnvelope,
    tuple[str, ...],
]:
    rows = registered_format_rows(request.candidate_row_ids)
    domains: list[
        tuple[FormatSpec, tuple[int, ...], tuple[int, ...] | None]
    ] = []
    for spec in rows:
        domain = _page_domain(spec, request.page_hypotheses)
        if domain is not None:
            pages, durable = domain
            domains.append((spec, pages, durable))
    if not domains:
        raise ValueError(
            "no registered format row has a legal requested page")
    config = PlacementConfig()
    envelope = PlacementDomainEnvelope.resolve(
        tuple((spec, pages) for spec, pages, _durable in domains),
        config,
    )
    return (
        tuple(domains),
        envelope,
        tuple(row.spec_id for row in rows),
    )


def _policy_id(
    domains: tuple[
        tuple[FormatSpec, tuple[int, ...], tuple[int, ...] | None], ...
    ],
    envelope: PlacementDomainEnvelope,
    branch_policy_ids: tuple[str, ...],
) -> str:
    payload = "\0".join((
        _DISCOVERY_POLICY_SCHEMA,
        envelope.policy_id,
        *(
            f"{spec.spec_id}:"
            + ",".join(str(page) for page in pages)
            for spec, pages, _durable in domains
        ),
        *branch_policy_ids,
    )).encode("utf-8")
    return (
        "holo/discovery-receiver/"
        f"sha256-{hashlib.sha256(payload).hexdigest()}"
    )


def _bound_request(
    spec: FormatSpec,
    pages: tuple[int, ...] | None,
    captures: tuple[CaptureInput, ...],
    *,
    defer_fountain_close: bool = False,
    run_mopup: bool = False,
    run_refine: bool = False,
) -> ReceiveRequest:
    return ReceiveRequest(
        spec,
        captures,
        state_path=None,
        page_hypotheses=pages,
        defer_fountain_close=defer_fountain_close,
        run_mopup=run_mopup,
        run_refine=run_refine,
    )


def _new_state(
    request: DiscoveryReceiveRequest,
) -> tuple[DiscoveryState, dict[str, ReceivePipeline]]:
    domains, envelope, requested_row_ids = _candidate_layout(request)
    branches: list[SessionState] = []
    pipelines: dict[str, ReceivePipeline] = {}
    for spec, _pages, durable in domains:
        bound = _bound_request(
            spec,
            durable,
            request.captures[:1],
            defer_fountain_close=request.defer_fountain_close,
        )
        pipeline = production_pipeline(
            bound, placement_domain_envelope=envelope)
        pipelines[spec.spec_id] = pipeline
        branches.append(SessionState.create(
            spec.spec_id, pipeline.policy_id, durable))
    policy_id = _policy_id(
        domains,
        envelope,
        tuple(pipelines[row.spec_id].policy_id
              for row, _pages, _durable in domains),
    )
    return DiscoveryState.create(
        policy_id,
        envelope,
        tuple(branches),
        requested_row_ids=requested_row_ids,
    ), pipelines


def _pipelines_for_state(
    request: DiscoveryReceiveRequest,
    state: DiscoveryState,
) -> dict[str, ReceivePipeline]:
    requested = (
        state.requested_row_ids
        if request.candidate_row_ids is None
        else tuple(
            row.spec_id
            for row in registered_format_rows(request.candidate_row_ids)
        )
    )
    if requested != state.requested_row_ids:
        raise ValueError(
            "discovery state belongs to another candidate row set")
    if request.page_hypotheses is not None:
        active = tuple(
            row.spec_id
            for row in registered_format_rows(requested)
            if _page_domain(row, request.page_hypotheses) is not None
        )
        if active != state.candidate_row_ids:
            raise ValueError(
                "discovery state belongs to another active page domain")
    pipelines: dict[str, ReceivePipeline] = {}
    domains: list[
        tuple[FormatSpec, tuple[int, ...], tuple[int, ...] | None]
    ] = []
    for branch in state.branches:
        spec = get_format_row(branch.format_row_id)
        if request.page_hypotheses is None:
            durable = branch.page_hypotheses
            pages = (
                tuple(range(spec.max_pages))
                if durable is None else durable
            )
        else:
            calculated = _page_domain(spec, request.page_hypotheses)
            if calculated is None:
                raise ValueError(
                    "requested pages eliminate an established discovery row")
            pages, durable = calculated
            if durable != branch.page_hypotheses:
                raise ValueError(
                    "discovery state belongs to another page domain")
        bound = _bound_request(
            spec,
            durable,
            request.captures[:1],
            defer_fountain_close=request.defer_fountain_close,
        )
        pipeline = production_pipeline(
            bound, placement_domain_envelope=state.domain_envelope)
        if pipeline.policy_id != branch.receiver_policy_id:
            raise ValueError(
                "discovery branch receiver policy is unavailable")
        pipelines[branch.format_row_id] = pipeline
        domains.append((spec, pages, durable))
    expected_envelope = PlacementDomainEnvelope.resolve(
        tuple((spec, pages) for spec, pages, _durable in domains),
        PlacementConfig(),
    )
    if expected_envelope != state.domain_envelope:
        raise ValueError("discovery receiver-wide domain changed")
    expected_policy = _policy_id(
        tuple(domains),
        state.domain_envelope,
        tuple(pipelines[row_id].policy_id
              for row_id in state.candidate_row_ids),
    )
    if expected_policy != state.discovery_policy_id:
        raise ValueError("discovery policy identity changed")
    return pipelines


def _facts(item: CaptureInput, raster) -> CaptureFacts:
    source_sha256 = raster.source.sha256
    return CaptureFacts(
        source_sha256,
        float(item.dpi),
        raster.source.dtype,
        raster.source.shape,
        raster.source.channels,
    )


def _capture_facts(item: CaptureInput) -> CaptureFacts:
    raster = open_capture(item.source, item.dpi)
    if (item.expected_sha256 is not None
            and raster.source.sha256 != item.expected_sha256):
        raise ValueError("capture source SHA differs from manifest")
    facts = _facts(item, raster)
    raster.verify_source_unchanged()
    return facts


def _survey_capture(item: CaptureInput) -> DiscoverySurvey:
    raster = open_capture(item.source, item.dpi)
    if (item.expected_sha256 is not None
            and raster.source.sha256 != item.expected_sha256):
        raise ValueError("capture source SHA differs from manifest")
    facts = _facts(item, raster)
    survey = survey_raster(raster)
    raster.verify_source_unchanged()
    return DiscoverySurvey(facts, survey.c_dots)


def _replace_branch(
    state: DiscoveryState,
    row_id: str,
    child: SessionState,
) -> DiscoveryState:
    branches = tuple(
        child if row.format_row_id == row_id else row
        for row in state.branches
    )
    return replace(state, branches=branches)


def _flag_bounded_round_complete(
    state: DiscoveryState, *, run_mopup: bool, run_refine: bool,
) -> bool:
    """Invocation-scoped analog of ``DiscoveryState.round_complete`` (v0.42).

    True when every (capture, branch) pair is c-excluded, terminal, or has
    committed at least this invocation's flag-bounded plan prefix.  The
    durable ``round_complete``/status derivations stay full-plan and
    flag-free (they must not depend on invocation flags); this bounded
    notion exists only to decide when a ``--complete`` invocation's single
    deferred close may run — at the end of the invocation's flag-bounded
    work, per the corrected §8.1 semantics.
    """
    from .runtime import _plan_bound

    for survey in state.surveys:
        sha = survey.facts.source_sha256
        for branch in state.branches:
            if state.candidate_complete(sha, branch.format_row_id):
                continue
            capture = branch.capture(sha)
            if capture is None:
                return False
            bound = _plan_bound(
                capture.plan, run_mopup=run_mopup, run_refine=run_refine)
            if len(capture.levels) < bound:
                return False
    return True


def _close_payload(
    state: DiscoveryState,
    pipelines: dict[str, ReceivePipeline],
) -> bytes | None:
    row_id = state.selected_row_id
    if state.status is not DiscoveryStatus.VERIFIED or row_id is None:
        return None
    branch = state.branch(row_id)
    close = pipelines[row_id].close.process(CloseContext(
        get_format_row(row_id), branch))
    if (not isinstance(close, CloseExecution)
            or close.record != branch.close
            or close.payload is None):
        raise RuntimeError(
            "verified discovery resume cannot reproduce the payload")
    return close.payload


def run_discovery_receive(
    request: DiscoveryReceiveRequest,
    *,
    observer_factory: ObserverFactory | None = None,
) -> DiscoveryReceiveResult:
    """Run or resume all registered format rows without caller selection."""
    path = Path(request.state_path) if request.state_path is not None else None
    if path is not None and path.exists():
        state, digest = (
            load_discovery_with_digest(
                path,
                defer_fountain_validation=True,
            )
            if request.defer_fountain_close
            else load_discovery_with_digest(path)
        )
        pipelines = _pipelines_for_state(request, state)
    else:
        state, pipelines = _new_state(request)
        if path is None:
            digest = authoritative_discovery_sha256(
                state,
                defer_fountain_validation=request.defer_fountain_close,
            )
        else:
            _changed, digest = save_discovery_with_digest(
                path,
                state,
                defer_fountain_validation=request.defer_fountain_close,
            )

    started = state
    observer_failures: list[str] = []
    branch_failure_cursors: dict[str, int] = {}
    session_open_rows: set[str] = set()
    deferred_checked_rows: set[str] = set()
    branch_event_sinks: dict[str, EventSink] = {}

    def persist_root(
        candidate: DiscoveryState,
        *,
        validate: bool = True,
    ) -> tuple[bool, str]:
        nonlocal state, digest
        if path is None:
            changed = candidate != state
            root_digest = authoritative_discovery_sha256(
                candidate,
                validate=validate,
                defer_fountain_validation=request.defer_fountain_close,
            )
        else:
            changed, root_digest = save_discovery_with_digest(
                path,
                candidate,
                validate=validate,
                defer_fountain_validation=request.defer_fountain_close,
            )
        state = candidate
        digest = root_digest
        return changed, root_digest

    first_pipeline = pipelines[state.candidate_row_ids[0]]
    if first_pipeline.qualification_status is ReceiverQualificationStatus.PROVISIONAL:
        warnings.warn(
            provisional_warning_message(
                first_pipeline.qualification_notes),
            ProvisionalReceiverWarning,
            stacklevel=2,
        )

    def branch_events(row_id: str):
        retained = branch_event_sinks.get(row_id)
        if retained is not None:
            return retained
        spec = get_format_row(row_id)
        pipeline = pipelines[row_id]
        branch = state.branch(row_id)
        observer = (
            None if observer_factory is None
            else observer_factory(spec, pipeline)
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            sink = event_sink_for_run(
                observer,
                pipeline.qualification_status,
                pipeline.qualification_notes,
                format_id=spec.spec_id,
                receiver_policy_id=pipeline.policy_id,
                page_domain=(
                    tuple(range(spec.max_pages))
                    if branch.page_hypotheses is None
                    else branch.page_hypotheses
                ),
            )
        branch_event_sinks[row_id] = sink
        return sink

    def collect_event_failures(
        row_id: str,
        events: EventSink,
        reported: tuple[str, ...] | None = None,
    ) -> None:
        """Append only failures not already collected from a cached sink."""
        retained = events.failures
        cursor = branch_failure_cursors.get(row_id, 0)
        if cursor > len(retained):
            cursor = 0
        observer_failures.extend(retained[cursor:])
        branch_failure_cursors[row_id] = len(retained)
        # Runtime results report the same cumulative EventSink failures.
        # Preserve synthetic or alternate executor failures that are not
        # represented by the supplied sink.
        if reported is not None and reported != retained:
            represented = Counter(retained)
            for failure in reported:
                if represented[failure]:
                    represented[failure] -= 1
                else:
                    observer_failures.append(failure)

    def ensure_session_open(row_id: str) -> EventSink:
        branch = state.branch(row_id)
        spec = get_format_row(row_id)
        events = branch_events(row_id)
        events.bind_state(authoritative_session_sha256(branch))
        if row_id in session_open_rows:
            return events
        page_domain = branch.page_hypotheses
        events.emit(
            "session.open",
            Stage.INGEST,
            details=(
                Detail("captures.requested", len(request.captures)),
                Detail("captures.retained", len(branch.captures)),
                Detail("session.created", False),
                Detail("format.id", spec.spec_id),
                Detail("receiver.policy_id", branch.receiver_policy_id),
                Detail(
                    "receiver.page_domain",
                    "all" if page_domain is None else ",".join(
                        str(page) for page in page_domain),
                ),
            ),
            authority=EventAuthority.COMMITTED,
            snapshot_factory=lambda: diagnostic_snapshots.committed(
                branch,
                spec,
            ),
        )
        session_open_rows.add(row_id)
        return events

    def finish_deferred_round() -> bytes | None:
        """Run the uniquely recognized row's sole final fountain check."""
        nonlocal state
        selected = state.selected_row_id
        if selected is None or selected in deferred_checked_rows:
            return None
        branch = state.branch(selected)
        spec = get_format_row(selected)
        events = ensure_session_open(selected)

        if (
            state.status is DiscoveryStatus.OPEN
            and branch.status is SessionStatus.OPEN
        ):
            def persist_branch(
                child: SessionState,
            ) -> tuple[bool, str]:
                root = _replace_branch(state, selected, child)
                changed, _root_digest = persist_root(
                    root, validate=False)
                return (
                    changed,
                    authoritative_session_sha256(child),
                )

            (
                branch,
                payload,
                close_base,
                close_snapshot_factory,
            ) = _finalize_deferred_close(
                branch,
                spec,
                pipelines[selected],
                events,
                None,
                persist_branch,
            )
        else:
            payload, close_snapshot_factory = _replay_deferred_close(
                branch,
                spec,
                pipelines[selected],
                events,
            )
            close_base = None

        _emit_session_complete(
            branch,
            spec,
            events,
            close_base_state_sha256=close_base,
            close_snapshot_factory=close_snapshot_factory,
        )
        deferred_checked_rows.add(selected)
        collect_event_failures(selected, events)
        if (
            state.status is DiscoveryStatus.VERIFIED
            and payload is None
        ):
            raise RuntimeError(
                "verified deferred discovery close omitted payload")
        return (
            payload
            if state.status is DiscoveryStatus.VERIFIED
            else None
        )

    def bootstrap_selected_observer(
        terminal: DiscoveryState,
    ) -> bytes | None:
        if observer_factory is None:
            return None
        selected = terminal.selected_row_id
        if selected is None:
            return None
        branch = terminal.branch(selected)
        events = branch_events(selected)
        result = _execute_receive(
            _bound_request(
                get_format_row(selected),
                branch.page_hypotheses,
                request.captures[:1],
                # A bootstrap is a projection of terminal state, never a
                # request to resume its unfinished capture prefix.
                defer_fountain_close=request.defer_fountain_close,
            ),
            pipelines[selected],
            events,
            initial_state=branch,
            initial_digest=authoritative_session_sha256(branch),
        )
        if result.state != branch or result.state_changed:
            raise RuntimeError(
                "terminal diagnostic bootstrap changed branch state")
        collect_event_failures(
            selected, events, result.observer_failures)
        return result.payload

    if state.status is not DiscoveryStatus.OPEN:
        if request.defer_fountain_close:
            payload = finish_deferred_round()
            return DiscoveryReceiveResult(
                state=state,
                state_changed=state != started,
                payload=payload,
                qualification_status=first_pipeline.qualification_status,
                qualification_notes=first_pipeline.qualification_notes,
                authoritative_digest=digest,
                observer_failures=tuple(observer_failures),
            )
        bootstrap_payload: bytes | None = None
        if observer_factory is not None:
            bootstrap_payload = bootstrap_selected_observer(state)
        payload = (
            bootstrap_payload
            if bootstrap_payload is not None
            else _close_payload(state, pipelines)
        )
        return DiscoveryReceiveResult(
            state=state,
            state_changed=False,
            payload=payload,
            qualification_status=first_pipeline.qualification_status,
            qualification_notes=first_pipeline.qualification_notes,
            authoritative_digest=digest,
            observer_failures=tuple(observer_failures),
        )

    authenticated = tuple(
        (item, _capture_facts(item)) for item in request.captures)
    requested_capture_ids = {
        facts.source_sha256 for _item, facts in authenticated}
    for branch in state.branches:
        if branch.status is not SessionStatus.OPEN:
            continue
        active = next((
            row for row in branch.captures
            if row.status is CaptureStatus.ACTIVE
        ), None)
        if (active is not None
                and active.source_sha256 not in requested_capture_ids):
            raise ValueError(
                f"resume active capture {active.source_sha256!r} before "
                f"adding evidence to {branch.format_row_id}")

    # Discovery state exists before this first authenticated raster read.
    for item, facts in authenticated:
        current = state.survey(facts.source_sha256)
        if current is None:
            surveyed = _survey_capture(item)
            if surveyed.facts != facts:
                raise ValueError("capture changed during discovery survey")
            surveys = tuple(sorted(
                (*state.surveys, surveyed),
                key=lambda row: row.facts.source_sha256,
            ))
            candidate = replace(
                state,
                surveys=surveys,
            )
            persist_root(candidate)
        elif current.facts != facts:
            raise ValueError(
                f"capture {facts.source_sha256!r} changed since discovery")

    latest_payload: bytes | None = None
    for row_id in state.candidate_row_ids:
        if state.status is DiscoveryStatus.INTEGRITY_FAILURE:
            break
        branch = state.branch(row_id)
        if branch.status is not SessionStatus.OPEN:
            continue
        spec = get_format_row(row_id)
        # v0.33 (D17): one multi-capture phased call per branch — the
        # session phase driver advances every eligible capture rung-major
        # and runs the priced mop-up tail.  c-excluded captures never
        # enter the branch request; the driver's multi-ACTIVE resume rule
        # replaces the old ACTIVE-first reordering, and an interrupted
        # drive stops everything behind it, so no later evidence passes a
        # deliberately interrupted capture.
        eligible = []
        for item, facts in authenticated:
            survey = state.survey(facts.source_sha256)
            assert survey is not None
            if (survey.c_dots is not None
                    and survey.c_dots != spec.cell_dots):
                continue
            eligible.append(replace(
                item, expected_sha256=survey.facts.source_sha256))
        if not eligible or all(
                state.candidate_complete(item.expected_sha256, row_id)
                for item in eligible):
            continue

        pipeline = pipelines[row_id]
        bound = _bound_request(
            spec,
            branch.page_hypotheses,
            tuple(eligible),
            defer_fountain_close=request.defer_fountain_close,
            run_mopup=request.run_mopup,
            run_refine=request.run_refine,
        )
        events = branch_events(row_id)

        def persist_child(
            child: SessionState,
            *,
            selected_row_id: str = row_id,
        ) -> tuple[bool, str]:
            root = _replace_branch(
                state, selected_row_id, child)
            changed, _root_digest = persist_root(
                root, validate=False)
            return changed, authoritative_session_sha256(child)

        result = _execute_receive(
            bound,
            pipeline,
            events,
            initial_state=branch,
            initial_digest=authoritative_session_sha256(branch),
            persist_state=persist_child,
            stop_requested=lambda: (
                state.status
                is DiscoveryStatus.INTEGRITY_FAILURE),
            finalize_deferred_close=(
                not request.defer_fountain_close),
            emit_terminal_summary=(
                not request.defer_fountain_close),
        )
        # _execute_receive always starts its event lineage with the
        # committed session bootstrap.
        session_open_rows.add(row_id)
        collect_event_failures(
            row_id, events, result.observer_failures)
        if result.state != state.branch(row_id):
            persist_child(result.state)
        if state.status is DiscoveryStatus.INTEGRITY_FAILURE:
            break
        if result.payload is not None:
            latest_payload = result.payload

    if (
        request.defer_fountain_close
        and (
            state.status is not DiscoveryStatus.OPEN
            or state.round_complete
            or _flag_bounded_round_complete(
                state,
                run_mopup=request.run_mopup,
                run_refine=request.run_refine)
        )
    ):
        deferred_payload = finish_deferred_round()
        if deferred_payload is not None:
            latest_payload = deferred_payload

    final = state
    payload = (
        latest_payload
        if final.status is DiscoveryStatus.VERIFIED
        and final.selected_row_id is not None
        and latest_payload is not None
        else (
            None
            if request.defer_fountain_close
            else _close_payload(final, pipelines)
        )
    )
    return DiscoveryReceiveResult(
        state=final,
        state_changed=final != started,
        payload=payload,
        qualification_status=first_pipeline.qualification_status,
        qualification_notes=first_pipeline.qualification_notes,
        authoritative_digest=digest,
        observer_failures=tuple(observer_failures),
    )


__all__ = [
    "DiscoveryReceiveRequest",
    "DiscoveryReceiveResult",
    "run_discovery_receive",
]

"""Discovery persistence, resume, and observer-integrity regressions."""
from __future__ import annotations

from dataclasses import replace
import json
import warnings

import numpy as np
import pytest

from holo.format.registry import DEFAULT_DISCOVERY_ROW_IDS, FORMAT_ROWS
from holo.receive import payload, tiles
from holo.receive.discovery import (
    DiscoveryReceiveRequest,
    _capture_facts,
    run_discovery_receive,
)
from holo.receive.discovery_state import (
    DiscoverySurvey,
    load_discovery,
    save_discovery,
)
from holo.receive.evidence_blocks import EvidenceOrigin, _block_from_rows
from holo.receive.observer import (
    ProvisionalReceiverWarning,
    event_sink_for_run,
)
from holo.receive.place import FormatHypothesisRejected
from holo.receive.runtime import (
    ReceiveRequest,
    ReceiveResult,
    _execute_receive,
    run_receive,
)
from holo.receive.session import (
    BarrierDelta,
    CaptureFacts,
    CaptureRecord,
    CaptureStatus,
    LevelRecord,
    LevelStatus,
    SessionIndex,
    SessionState,
    apply_close,
    append_level_barrier,
    authoritative_sha256 as authoritative_session_sha256,
    certificate_frontier_sha256,
)
from holo.receive.types import (
    AddressArtifact,
    AttemptStage,
    AttemptState,
    CaptureInput,
    CloseRecord,
    CloseStatus,
    Disposition,
    EventAuthority,
    PayloadArtifact,
    Stage,
    SurveyArtifact,
    TileAttemptRecord,
    TileCertificateRecord,
)


def _capture(
    pixels: np.ndarray,
) -> CaptureInput:
    return CaptureInput(pixels, 600.0)


def _run(request: DiscoveryReceiveRequest, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        return run_discovery_receive(request, **kwargs)


def _survey_for(capture: CaptureInput, *, c_dots: int | None) -> DiscoverySurvey:
    return DiscoverySurvey(_capture_facts(capture), c_dots)


def test_level_outcome_is_exactly_derived_from_its_artifact_prefix() -> None:
    survey = SurveyArtifact("survey", ())
    address = AddressArtifact("address", survey.survey_id, ())
    payload = PayloadArtifact("payload", address.address_id)
    levels = (
        LevelRecord(),
        LevelRecord(survey=survey),
        LevelRecord(survey=survey, address=address),
        LevelRecord(survey=survey, address=address, payload=payload),
    )

    assert tuple(level.status for level in levels) == (
        LevelStatus.REFUSED,
        LevelStatus.REFUSED,
        LevelStatus.REFUSED,
        LevelStatus.COMPLETE,
    )
    assert tuple(level.stage_dispositions[-1] for level in levels) == (
        (Stage.SURVEY, Disposition.REFUSED),
        (Stage.ADDRESS, Disposition.REFUSED),
        (Stage.PAYLOAD, Disposition.REFUSED),
        (Stage.PAYLOAD, Disposition.COMPLETE),
    )
    with pytest.raises(ValueError, match="causal prefix"):
        LevelRecord(address=address)
    with pytest.raises(ValueError, match="causal prefix"):
        LevelRecord(survey=survey, payload=payload)


def test_capture_authority_rejects_invalid_scalar_facts() -> None:
    with pytest.raises(ValueError, match="dtype is invalid"):
        CaptureFacts("a" * 64, 600.0, "not-a-dtype", (16, 16), 1)
    with pytest.raises(ValueError, match="dtype is invalid"):
        CaptureRecord(
            "a" * 64, 600.0, "not-a-dtype", (16, 16), 1, (), ())
    with pytest.raises(ValueError, match="channels"):
        CaptureFacts("a" * 64, 600.0, "uint8", (16, 16), True)
    with pytest.raises(ValueError, match="channels"):
        CaptureRecord(
            "a" * 64, 600.0, "uint8", (16, 16), True, (), ())


def test_flat_discovery_decision_persists_and_resumes(tmp_path) -> None:
    """The root retains only authenticated facts and the c decision."""
    state_path = tmp_path / "discovery.json"
    request = DiscoveryReceiveRequest(
        (_capture(np.zeros((128, 128), np.uint8)),),
        state_path=state_path,
    )

    first = _run(request)
    assert first.state.surveys[0].c_dots is None
    assert load_discovery(state_path) == first.state
    # Reject non-standard Infinity/NaN tokens even if an implementation
    # accidentally bypasses the state codec's strict encoder.
    envelope = json.loads(
        state_path.read_text(encoding="utf-8"),
        parse_constant=lambda token: (_ for _ in ()).throw(
            AssertionError(f"non-finite JSON token {token}")),
    )
    assert set(envelope["state"]["surveys"][0]) == {"facts", "c_dots"}

    resumed = _run(request)
    assert resumed.state == first.state
    assert resumed.authoritative_sha256 == first.authoritative_sha256
    assert not resumed.state_changed


def test_discovery_load_rejects_format_derived_branch_corruption(
    tmp_path,
) -> None:
    """Every branch is format-validated before a terminal resume can return."""
    import holo.receive.discovery as discovery
    from holo.receive.cascade import scale_plan

    row_id = "c3-r0550@2240x1536"
    capture = _capture(np.zeros((16, 16), np.uint8))
    root, _pipelines = discovery._new_state(DiscoveryReceiveRequest(
        (capture,), candidate_row_ids=(row_id,)))
    survey = _survey_for(capture, c_dots=3)
    facts = survey.facts
    wrong_capture = CaptureRecord(
        facts.source_sha256,
        facts.dpi,
        facts.dtype,
        facts.shape_yx,
        facts.channels,
        scale_plan(facts.dpi, 2),
        (),
    )
    branch = replace(root.branch(row_id), captures=(wrong_capture,))
    corrupted = replace(
        root,
        branches=(branch,),
        surveys=(survey,),
    )
    path = tmp_path / "corrupt-discovery.json"
    save_discovery(path, corrupted, validate=False)

    with pytest.raises(ValueError, match="scale plan differs"):
        load_discovery(path)


def test_terminal_discovery_bootstraps_selected_observer(
    monkeypatch,
    tmp_path,
) -> None:
    """A verified discovery no-op still exposes its committed exact branch."""
    import holo.receive.discovery as discovery

    capture = _capture(np.zeros((1, 1), np.uint8))
    state_path = tmp_path / "terminal-discovery.json"
    request = DiscoveryReceiveRequest((capture,), state_path=state_path)
    root, _pipelines = discovery._new_state(request)
    selected = root.branches[0]
    certificate = TileCertificateRecord(
        "1" * 64, 0, (0, 0), b"\0", "attempt-0")
    selected = replace(selected, certificates=(certificate,))
    selected = apply_close(selected, CloseRecord(
        CloseStatus.VERIFIED,
        certificate_frontier_sha256(selected.certificates),
        "2" * 64,
        len(b"payload"),
        1,
    ))
    terminal = replace(
        root,
        branches=(selected, *root.branches[1:]),
    )
    assert terminal.status.value == "verified"
    state_path.write_text("fake loader input", encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "load_discovery_with_digest",
        lambda _path: (terminal, "3" * 64),
    )
    monkeypatch.setattr(
        discovery,
        "_close_payload",
        lambda *_args: pytest.fail(
            "observer bootstrap already reproduced verified payload"),
    )
    observed = []
    factories = []

    def observer_factory(spec, pipeline):
        factories.append((spec.spec_id, pipeline.policy_id))
        return observed.append

    def execute(
        exact_request,
        pipeline,
        events,
        *,
        initial_state,
        initial_digest,
        **_kwargs,
    ) -> ReceiveResult:
        assert exact_request.captures == request.captures[:1]
        assert initial_state is selected
        events.bind_state(initial_digest)
        events.emit(
            "session.open",
            Stage.INGEST,
            authority=EventAuthority.COMMITTED,
        )
        return ReceiveResult(
            initial_state,
            (),
            False,
            observer_failures=("fake terminal observer failure",),
            payload=b"payload",
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    monkeypatch.setattr(discovery, "_execute_receive", execute)
    result = _run(request, observer_factory=observer_factory)

    assert factories == [(selected.format_row_id, selected.receiver_policy_id)]
    assert [event.name for event in observed] == ["session.open"]
    assert result.payload == b"payload"
    assert result.observer_failures == ("fake terminal observer failure",)
    assert not result.state_changed


def test_terminal_format_conflict_does_not_run_open_children(
    monkeypatch,
    tmp_path,
) -> None:
    """Diagnostics cannot turn a root integrity result into more reception."""
    import holo.receive.discovery as discovery

    capture = _capture(np.zeros((1, 1), np.uint8))
    state_path = tmp_path / "conflicted-discovery.json"
    request = DiscoveryReceiveRequest((capture,), state_path=state_path)
    root, _pipelines = discovery._new_state(request)
    first = replace(
        root.branches[0],
        certificates=(TileCertificateRecord(
            "1" * 64, 0, (0, 0), b"\0", "attempt-0"),),
    )
    second = replace(
        root.branches[1],
        certificates=(TileCertificateRecord(
            "2" * 64, 0, (0, 0), b"\0", "attempt-1"),),
    )
    terminal = replace(
        root,
        branches=(first, second, *root.branches[2:]),
    )
    assert terminal.status.value == "integrity_failure"
    assert terminal.selected_row_id is None
    state_path.write_text("fake loader input", encoding="utf-8")
    monkeypatch.setattr(
        discovery,
        "load_discovery_with_digest",
        lambda _path: (terminal, "3" * 64),
    )
    monkeypatch.setattr(
        discovery,
        "_execute_receive",
        lambda *_args, **_kwargs: pytest.fail(
            "format-conflicted children must not resume"),
    )

    result = _run(
        request,
        observer_factory=lambda *_args: pytest.fail(
            "format conflict has no selected diagnostic interpretation"),
    )

    assert result.state is terminal
    assert result.payload is None
    assert not result.state_changed


def test_resume_authenticates_facts_without_recomputing_e021(
    monkeypatch, tmp_path,
) -> None:
    """A durable c decision is not a numerical replay obligation."""
    import holo.receive.discovery as discovery

    state_path = tmp_path / "discovery.json"
    capture = _capture(np.zeros((128, 128), np.uint8))
    # v0.42: full-plan completion needs the lane flags.
    request = DiscoveryReceiveRequest(
        (capture,), state_path=state_path, run_refine=True)
    first = _run(request)
    assert all(
        child.capture(first.state.surveys[0].facts.source_sha256) is not None
        and child.capture(
            first.state.surveys[0].facts.source_sha256
        ).status is CaptureStatus.COMPLETE
        for child in first.state.branches
    )

    def forbidden(_item):
        raise AssertionError("resume recomputed the persisted E021 survey")

    monkeypatch.setattr(discovery, "_survey_capture", forbidden)
    monkeypatch.setattr(
        discovery,
        "_execute_receive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resume reran a completed exact-row capture")),
    )
    resumed = _run(request)
    assert resumed.state == first.state


def test_changed_capture_bytes_are_a_distinct_acquisition(tmp_path) -> None:
    pixels = np.zeros((128, 128), np.uint8)
    # v0.42: run the full plan so the first acquisition is COMPLETE and
    # the changed-bytes rerun owes no ACTIVE-capture resume duty.
    request = DiscoveryReceiveRequest(
        (_capture(pixels),),
        state_path=tmp_path / "discovery.json",
        run_refine=True,
    )
    first = _run(request)
    pixels[0, 0] = 1
    second = _run(request)
    assert len(first.state.surveys) == 1
    assert len(second.state.surveys) == 2
    assert len({
        row.facts.source_sha256 for row in second.state.surveys
    }) == 2


def test_page_filtered_explicit_candidate_set_resumes_identically(
    tmp_path,
) -> None:
    """Filtering illegal pages is canonical on both creation and resume."""
    state_path = tmp_path / "discovery.json"
    request = DiscoveryReceiveRequest(
        (_capture(np.zeros((16, 16), np.uint8)),),
        state_path=state_path,
        candidate_row_ids=DEFAULT_DISCOVERY_ROW_IDS,
        page_hypotheses=(200,),
    )

    first = _run(request)
    assert first.state.candidate_row_ids == ("c3-r0550@2240x1536",)
    resumed = _run(request)
    assert resumed.state == first.state
    assert resumed.authoritative_sha256 == first.authoritative_sha256
    assert not resumed.state_changed

    inherited = _run(DiscoveryReceiveRequest(
        request.captures,
        state_path=state_path,
    ))
    assert inherited.state == first.state

    with pytest.raises(ValueError, match="candidate row set"):
        _run(DiscoveryReceiveRequest(
            request.captures,
            state_path=state_path,
            candidate_row_ids=first.state.candidate_row_ids,
        ))


def test_discovery_state_has_no_retry_choice(tmp_path) -> None:
    state_path = tmp_path / "discovery.json"
    capture = _capture(np.zeros((16, 16), np.uint8))
    first = _run(DiscoveryReceiveRequest(
        (capture,), state_path=state_path))
    envelope = json.loads(state_path.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 12
    assert "retry150" not in envelope["state"]
    assert "retry_policy" not in state_path.read_text(encoding="utf-8")

    resumed = _run(DiscoveryReceiveRequest(
        (capture,), state_path=state_path))
    assert resumed.state == first.state


def test_exact_branch_observer_failures_are_exposed(
    monkeypatch, tmp_path,
) -> None:
    """Discovery must not discard failures isolated by an exact-row sink."""
    import holo.receive.discovery as discovery

    capture = _capture(np.zeros((16, 16), np.uint8))
    monkeypatch.setattr(
        discovery,
        "_survey_capture",
        lambda _item: _survey_for(capture, c_dots=3),
    )

    def execute(
        _request, pipeline, _events, *, initial_state, **_kwargs,
    ) -> ReceiveResult:
        return ReceiveResult(
            initial_state,
            (),
            False,
            observer_failures=("exact branch observer failed",),
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    monkeypatch.setattr(discovery, "_execute_receive", execute)
    result = _run(DiscoveryReceiveRequest(
        (capture,), state_path=tmp_path / "discovery.json"))
    assert result.observer_failures == ("exact branch observer failed",)


def test_branch_is_sha_pinned_and_uses_child_diagnostic_lineage(
    monkeypatch, tmp_path,
) -> None:
    """Root persistence must not substitute its digest for child events."""
    import holo.receive.discovery as discovery

    capture = _capture(np.zeros((16, 16), np.uint8))
    survey = _survey_for(capture, c_dots=3)
    monkeypatch.setattr(discovery, "_survey_capture", lambda _item: survey)

    def execute(
        request, pipeline, _events, *, initial_state, initial_digest,
        persist_state, **_kwargs,
    ) -> ReceiveResult:
        assert request.captures[0].expected_sha256 == survey.facts.source_sha256
        child_digest = authoritative_session_sha256(initial_state)
        assert initial_digest == child_digest
        _changed, persisted_digest = persist_state(initial_state)
        assert persisted_digest == child_digest
        return ReceiveResult(
            initial_state,
            (),
            False,
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    monkeypatch.setattr(discovery, "_execute_receive", execute)
    _run(DiscoveryReceiveRequest(
        (capture,), state_path=tmp_path / "discovery.json"))


def test_scale_local_c_mismatch_is_a_durable_refusal(
    monkeypatch, tmp_path,
) -> None:
    """A later E021 c mismatch must not strand an ACTIVE exact branch."""
    import holo.receive.production as production
    from holo.format.registry import registered_format_rows

    def mismatch(*_args, **_kwargs):
        raise FormatHypothesisRejected("scale survey excludes this row")

    monkeypatch.setattr(production, "place_survey", mismatch)
    spec = registered_format_rows()[0]
    request = ReceiveRequest(
        spec,
        (_capture(np.zeros((16, 16), np.uint8)),),
        state_path=tmp_path / "exact.json",
        run_refine=True,
    )
    pipeline = production.production_pipeline(request)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        result = run_receive(request, pipeline=pipeline)
    assert result.captures[0].status is CaptureStatus.COMPLETE
    # v0.33/v0.42 plan shape: ordinary lanes carry the durable address
    # refusal; the appended mop-up and refinement levels have nothing
    # parked/eligible and complete empty.
    record = result.state.captures[0]
    for lane, level in zip(record.plan, record.levels, strict=True):
        if lane.mopup_of is None and lane.refine_of is None:
            assert level.stage_dispositions[-1] == (
                Stage.ADDRESS, Disposition.REFUSED)
        else:
            assert level.payload is not None


def test_nested_stop_request_ends_cascade_after_one_barrier() -> None:
    """A terminal discovery root must be a nested commit boundary."""
    from holo.format.registry import get_format_row
    from holo.receive.production import production_pipeline

    spec = get_format_row("c3-r0550@2240x1536")
    request = ReceiveRequest(
        spec, (_capture(np.zeros((16, 16), np.uint8)),))
    pipeline = production_pipeline(request)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        events = event_sink_for_run(
            None,
            pipeline.qualification_status,
            pipeline.qualification_notes,
            format_id=spec.spec_id,
            receiver_policy_id=pipeline.policy_id,
            page_domain=tuple(range(spec.max_pages)),
        )
    result = _execute_receive(
        request, pipeline, events, stop_requested=lambda: True)
    capture = result.state.captures[0]
    assert capture.status is CaptureStatus.ACTIVE
    assert len(capture.levels) == 1
    assert len(capture.plan) > 1
    assert result.captures[0].barriers_committed == 1


def test_active_capture_is_resumed_before_earlier_request_items(
    tmp_path,
) -> None:
    """Request ordering cannot postpone work behind a durable ACTIVE row."""
    import holo.receive.discovery as discovery

    row_id = "c3-r0550@2240x1536"
    capture_a = _capture(np.zeros((16, 16), np.uint8))
    capture_b = _capture(np.ones((16, 16), np.uint8))
    bootstrap = DiscoveryReceiveRequest(
        (capture_a, capture_b),
        candidate_row_ids=(row_id,),
        page_hypotheses=(0,),
    )
    root, pipelines = discovery._new_state(bootstrap)
    survey_a = discovery._survey_capture(capture_a)
    survey_b = discovery._survey_capture(capture_b)
    branch = root.branch(row_id)
    from holo.format.registry import get_format_row
    exact_spec = get_format_row(row_id)
    exact_request = ReceiveRequest(
        exact_spec,
        (replace(
            capture_a, expected_sha256=survey_a.facts.source_sha256),),
        page_hypotheses=(0,),
    )
    pipeline = pipelines[row_id]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        events = event_sink_for_run(
            None,
            pipeline.qualification_status,
            pipeline.qualification_notes,
            format_id=row_id,
            receiver_policy_id=pipeline.policy_id,
            page_domain=(0,),
        )
    active = _execute_receive(
        exact_request,
        pipeline,
        events,
        initial_state=branch,
        initial_digest=authoritative_session_sha256(branch),
        stop_requested=lambda: True,
    ).state
    assert active.captures[0].status is CaptureStatus.ACTIVE
    root = replace(
        root,
        branches=(active,),
        surveys=tuple(sorted(
            (survey_a, survey_b),
            key=lambda row: row.facts.source_sha256,
        )),
    )
    state_path = tmp_path / "discovery.json"
    save_discovery(state_path, root)

    resumed = _run(DiscoveryReceiveRequest(
        (capture_b, capture_a),
        state_path=state_path,
        run_refine=True,
    ))
    completed = resumed.state.branch(row_id).captures
    assert tuple(row.source_sha256 for row in completed) == (
        survey_a.facts.source_sha256,
        survey_b.facts.source_sha256,
    )
    assert all(row.status is CaptureStatus.COMPLETE for row in completed)


def test_discovery_load_rejects_forged_terminal_branch(tmp_path) -> None:
    """A terminal child must reproduce from its certified frontier."""
    import holo.receive.discovery as discovery

    terminal_row_id = "c3-r0550@2240x1536"
    capture_a = _capture(np.zeros((16, 16), np.uint8))
    capture_b = _capture(np.ones((16, 16), np.uint8))
    bootstrap = DiscoveryReceiveRequest((capture_a, capture_b))
    root, pipelines = discovery._new_state(bootstrap)
    survey_a = discovery._survey_capture(capture_a)
    branch = root.branch(terminal_row_id)

    from holo.format.registry import get_format_row
    spec = get_format_row(terminal_row_id)
    exact_request = ReceiveRequest(
        spec,
        (replace(
            capture_a, expected_sha256=survey_a.facts.source_sha256),),
        page_hypotheses=branch.page_hypotheses,
    )
    pipeline = pipelines[terminal_row_id]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        events = event_sink_for_run(
            None,
            pipeline.qualification_status,
            pipeline.qualification_notes,
            format_id=terminal_row_id,
            receiver_policy_id=pipeline.policy_id,
            page_domain=tuple(range(spec.max_pages)),
        )
    active = _execute_receive(
        exact_request,
        pipeline,
        events,
        initial_state=branch,
        initial_digest=authoritative_session_sha256(branch),
        stop_requested=lambda: True,
    ).state
    assert active.captures[0].status is CaptureStatus.ACTIVE
    terminal = apply_close(active, CloseRecord(
        CloseStatus.INTEGRITY_FAILURE,
        certificate_frontier_sha256(active.certificates),
        reason="test terminal branch",
    ))
    root = replace(
        root,
        branches=tuple(
            terminal if row.format_row_id == terminal_row_id else row
            for row in root.branches
        ),
        surveys=(survey_a,),
    )
    state_path = tmp_path / "discovery.json"
    # This scheduler fixture deliberately forges a terminal outcome without
    # certified evidence; public validation now rejects such close records.
    save_discovery(state_path, root, validate=False)

    with pytest.raises(ValueError, match="close does not reproduce"):
        _run(DiscoveryReceiveRequest((capture_b,), state_path=state_path))

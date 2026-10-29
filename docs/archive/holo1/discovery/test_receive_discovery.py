"""Receiver-wide format discovery, state, and CLI routing."""
from __future__ import annotations

from dataclasses import replace
import json
from types import MappingProxyType

import numpy as np
import pytest

from holo import cli
from holo.format.registry import (
    DEFAULT_DISCOVERY_ROW_IDS,
    FORMAT_ROWS,
    registered_format_rows,
)
from holo.receive.discovery import (
    DiscoveryReceiveRequest,
    DiscoveryReceiveResult,
    _new_state,
    run_discovery_receive,
)
from holo.receive.discovery_state import (
    DiscoveryStatus,
    DiscoverySurvey,
    load_discovery,
    save_discovery,
)
from holo.receive.evidence import TileCertificateRecord
from holo.receive.observer import (
    ProvisionalReceiverWarning,
    ReceiverQualificationStatus,
)
from holo.receive.place import PlacementConfig
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.policy import PlacementDomainEnvelope
from holo.receive.runtime import ReceiveResult
from holo.receive.session import SessionState, save_session
from holo.receive.types import CaptureInput


def _capture() -> CaptureInput:
    return CaptureInput(
        np.zeros((16, 16), np.uint8),
        600.0,
    )


def test_registered_receive_rows_are_complete_and_canonical() -> None:
    rows = registered_format_rows()
    assert isinstance(FORMAT_ROWS, MappingProxyType)
    assert tuple(row.spec_id for row in rows) == DEFAULT_DISCOVERY_ROW_IDS
    assert {row.coding.coding_id for row in rows} == {
        "c3-r0550", "c2-r0550", "c2-r0700",
    }
    with pytest.raises(TypeError):
        FORMAT_ROWS["replacement"] = rows[0]  # type: ignore[index]
    with pytest.raises(ValueError, match="unique"):
        registered_format_rows((rows[0].spec_id, rows[0].spec_id))


def test_deferred_close_request_requires_an_exact_bool() -> None:
    from holo.receive.runtime import ReceiveRequest

    spec = registered_format_rows()[0]
    with pytest.raises(TypeError):
        ReceiveRequest(
            spec, (_capture(),),
            defer_fountain_close=1,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        DiscoveryReceiveRequest(
            (_capture(),),
            defer_fountain_close=1,  # type: ignore[arg-type]
        )


def test_receiver_wide_budget_envelopes_every_row() -> None:
    rows = registered_format_rows()
    config = PlacementConfig()
    pages = tuple(
        (row, tuple(range(row.max_pages))) for row in rows)
    envelope = PlacementDomainEnvelope.resolve(pages, config)
    assert envelope.row_ids == tuple(row.spec_id for row in rows)

    selected = rows[0]
    local_budgets, local_word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        selected,
        tuple(range(selected.max_pages)),
        0,
        config,
    )
    wide_budgets, wide_word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        selected,
        tuple(range(selected.max_pages)),
        0,
        config,
        domain_envelope=envelope,
    )
    assert wide_budgets.cold.max_hypotheses == envelope.cold_hypotheses
    assert wide_budgets.local.max_hypotheses == envelope.local_hypotheses
    assert wide_word.max_hypotheses == envelope.word_hypotheses
    assert wide_budgets.cold.max_hypotheses > (
        local_budgets.cold.max_hypotheses)
    assert wide_word.max_hypotheses > local_word.max_hypotheses


def test_receiver_wide_budget_refuses_foreign_or_undercovered_domains() -> None:
    rows = registered_format_rows()
    config = PlacementConfig()
    selected = rows[0]
    pages = tuple(range(selected.max_pages))
    envelope = PlacementDomainEnvelope.resolve(((selected, pages),), config)

    with pytest.raises(ValueError, match="outside"):
        PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
            rows[1],
            tuple(range(rows[1].max_pages)),
            0,
            config,
            domain_envelope=envelope,
        )

    for field, n_lower in (
        ("cold_hypotheses", 0),
        ("local_hypotheses", 0),
        ("lower_hypotheses", 1),
        ("word_hypotheses", 0),
    ):
        undercovered = replace(envelope, **{field: 1})
        route = field.removesuffix("_hypotheses")
        with pytest.raises(ValueError, match=route):
            PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
                selected,
                pages,
                n_lower,
                config,
                domain_envelope=undercovered,
            )


def test_empty_discovery_state_round_trips(tmp_path) -> None:
    request = DiscoveryReceiveRequest((_capture(),))
    state, _pipelines = _new_state(request)
    path = tmp_path / "discovery.json"
    assert save_discovery(path, state)
    assert load_discovery(path) == state
    wire = json.loads(path.read_text(encoding="utf-8"))
    assert wire["schema_version"] == 12
    assert set(wire["state"]) == {
        "discovery_policy_id",
        "requested_row_ids",
        "domain_envelope",
        "branches",
        "surveys",
    }


def test_only_deferred_discovery_load_suppresses_open_close_replay(
    monkeypatch,
    tmp_path,
) -> None:
    import holo.receive.fountain_close as fountain_close
    from holo.receive.discovery_state import (
        authoritative_discovery_sha256,
        load_discovery,
        save_discovery,
    )

    state, _pipelines = _new_state(
        DiscoveryReceiveRequest((_capture(),)))
    path = tmp_path / "deferred-open-discovery.json"
    assert save_discovery(path, state, validate=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("ordinary discovery load skipped close replay")

    monkeypatch.setattr(fountain_close, "close_volume", forbidden)
    with pytest.raises(AssertionError, match="skipped close replay"):
        load_discovery(path)
    with pytest.raises(AssertionError, match="skipped close replay"):
        authoritative_discovery_sha256(state)
    with pytest.raises(AssertionError, match="skipped close replay"):
        save_discovery(tmp_path / "ordinary-save.json", state)

    assert load_discovery(
        path,
        defer_fountain_validation=True,
    ) == state
    assert len(authoritative_discovery_sha256(
        state,
        defer_fountain_validation=True,
    )) == 64
    assert save_discovery(
        tmp_path / "deferred-save.json",
        state,
        defer_fountain_validation=True,
    )


@pytest.mark.parametrize(
    "terminal_status",
    ("verified", "integrity_failure", "unsupported"),
)
def test_complete_terminal_discovery_resume_replays_selected_once(
    monkeypatch,
    tmp_path,
    terminal_status,
) -> None:
    import hashlib

    import holo.receive.discovery as discovery
    import holo.receive.fountain_close as fountain_close
    from holo.receive.runtime import CloseExecution
    from holo.receive.session import (
        apply_close,
        certificate_frontier_sha256,
    )
    from holo.receive.types import CloseRecord, CloseStatus

    row_ids = tuple(row.spec_id for row in registered_format_rows()[:2])
    row_id = row_ids[0]
    capture = _capture()
    request = DiscoveryReceiveRequest(
        (capture,),
        state_path=tmp_path / f"{terminal_status}-discovery.json",
        candidate_row_ids=row_ids,
        defer_fountain_close=True,
    )
    terminal, pipelines = _new_state(request)
    selected = replace(
        terminal.branches[0],
        certificates=(TileCertificateRecord(
            "1" * 64, 0, (0, 0), b"\0", "attempt-1"),),
    )
    payload = b"payload"
    status = CloseStatus(terminal_status)
    frontier = certificate_frontier_sha256(selected.certificates)
    if status is CloseStatus.VERIFIED:
        close_record = CloseRecord(
            status,
            frontier,
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        )
    elif status is CloseStatus.UNSUPPORTED:
        close_record = CloseRecord(
            status,
            frontier,
            metadata_version=1,
            reason="synthetic unsupported metadata",
        )
    else:
        close_record = CloseRecord(
            status,
            frontier,
            reason="synthetic integrity failure",
        )
    selected = apply_close(selected, close_record)
    terminal = replace(
        terminal,
        branches=(selected, *terminal.branches[1:]),
    )
    assert terminal.status.value == terminal_status
    request.state_path.write_text("fake loader input", encoding="utf-8")

    fountain_calls = 0

    def counted_close_volume(*_args, **_kwargs):
        nonlocal fountain_calls
        fountain_calls += 1
        return object()

    monkeypatch.setattr(
        fountain_close, "close_volume", counted_close_volume)

    class ReproducingClose:
        def __init__(self, policy_id):
            self.policy_id = policy_id

        def process(self, context):
            fountain_close.close_volume((), context.spec)
            return CloseExecution(
                context.state.close,
                (
                    payload
                    if context.state.status.value == "verified"
                    else None
                ),
            )

    for candidate_id, pipeline in tuple(pipelines.items()):
        pipelines[candidate_id] = replace(
            pipeline,
            close=ReproducingClose(pipeline.close.policy_id),
        )

    def load(_path, *, defer_fountain_validation=False):
        assert defer_fountain_validation
        return terminal, "3" * 64

    monkeypatch.setattr(
        discovery, "load_discovery_with_digest", load)
    monkeypatch.setattr(
        discovery, "_pipelines_for_state",
        lambda _request, _state: pipelines,
    )
    monkeypatch.setattr(
        discovery,
        "_capture_facts",
        lambda _capture: pytest.fail(
            "terminal discovery resume acquired a scan"),
    )

    with pytest.warns(ProvisionalReceiverWarning):
        result = run_discovery_receive(request)

    assert result.state is terminal
    assert not result.state_changed
    assert result.payload == (
        payload if terminal_status == "verified" else None)
    assert fountain_calls == 1


def test_complete_discovery_conflict_performs_no_fountain_close(
    monkeypatch,
    tmp_path,
) -> None:
    import holo.receive.discovery as discovery
    import holo.receive.fountain_close as fountain_close
    from holo.receive.runtime import CloseExecution

    row_ids = tuple(row.spec_id for row in registered_format_rows()[:2])
    request = DiscoveryReceiveRequest(
        (_capture(),),
        state_path=tmp_path / "conflict-discovery.json",
        candidate_row_ids=row_ids,
        defer_fountain_close=True,
    )
    terminal, pipelines = _new_state(request)
    terminal = replace(
        terminal,
        branches=tuple(
            replace(
                branch,
                certificates=(TileCertificateRecord(
                    str(index) * 64,
                    0,
                    (0, 0),
                    b"\0",
                    f"attempt-{index}",
                ),),
            )
            for index, branch in enumerate(terminal.branches, 1)
        ),
    )
    assert terminal.status is DiscoveryStatus.INTEGRITY_FAILURE
    assert terminal.selected_row_id is None
    request.state_path.write_text("fake loader input", encoding="utf-8")

    fountain_calls = []
    load_finished = False

    def counted_close_volume(*_args, **_kwargs):
        assert load_finished
        fountain_calls.append(True)
        return object()

    monkeypatch.setattr(
        fountain_close, "close_volume", counted_close_volume)

    class ForbiddenClose:
        def __init__(self, policy_id):
            self.policy_id = policy_id

        def process(self, _context):
            raise AssertionError(
                "format conflict has no selected close interpretation")

    for row_id, pipeline in tuple(pipelines.items()):
        pipelines[row_id] = replace(
            pipeline,
            close=ForbiddenClose(pipeline.close.policy_id),
        )

    def load(_path, *, defer_fountain_validation=False):
        nonlocal load_finished
        assert defer_fountain_validation
        assert fountain_calls == []
        load_finished = True
        return terminal, "3" * 64

    monkeypatch.setattr(
        discovery, "load_discovery_with_digest", load)
    monkeypatch.setattr(
        discovery, "_pipelines_for_state",
        lambda _request, _state: pipelines,
    )
    monkeypatch.setattr(
        discovery,
        "_capture_facts",
        lambda _capture: pytest.fail(
            "terminal discovery conflict acquired a scan"),
    )

    with pytest.warns(ProvisionalReceiverWarning):
        result = run_discovery_receive(request)

    assert result.state is terminal
    assert not result.state_changed
    assert result.payload is None
    assert fountain_calls == []


def test_complete_close_only_resume_bootstraps_real_diagnostic_view(
    monkeypatch,
    tmp_path,
) -> None:
    import hashlib

    import holo.receive.discovery as discovery
    from holo.receive.cascade import scale_plan
    from holo.receive.diag import ReceiveDiagnostics
    from holo.receive.runtime import CloseExecution
    from holo.receive.session import (
        LevelRecord,
        certificate_frontier_sha256,
    )
    from holo.receive.types import CloseRecord, CloseStatus

    capture = _capture()
    row_id = "c3-r0550@2240x1536"
    spec = FORMAT_ROWS[row_id]
    request = DiscoveryReceiveRequest(
        (capture,),
        state_path=tmp_path / "close-only-discovery.json",
        candidate_row_ids=(row_id,),
        page_hypotheses=(0,),
        defer_fountain_close=True,
    )
    resumed, pipelines = _new_state(request)
    survey = DiscoverySurvey(discovery._capture_facts(capture), 3)
    plan = scale_plan(survey.facts.dpi, spec.cell_dots)
    retained = survey.facts.as_record(plan, LevelRecord())
    retained = replace(
        retained,
        levels=tuple(LevelRecord() for _lane in plan),
    )
    certificate = TileCertificateRecord(
        "1" * 64, 0, (0, 0), b"\0", "attempt-1")
    branch = replace(
        resumed.branches[0],
        captures=(retained,),
        certificates=(certificate,),
    )
    resumed = replace(
        resumed,
        branches=(branch,),
        surveys=(survey,),
    )
    assert resumed.status is DiscoveryStatus.OPEN
    assert resumed.round_complete
    assert resumed.selected_row_id == row_id
    request.state_path.write_text("fake loader input", encoding="utf-8")

    payload = b"payload"
    record = CloseRecord(
        CloseStatus.VERIFIED,
        certificate_frontier_sha256(branch.certificates),
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )

    class VerifyingClose:
        def __init__(self, policy_id):
            self.policy_id = policy_id

        def process(self, context):
            assert context.state is branch
            return CloseExecution(record, payload)

    pipeline = pipelines[row_id]
    pipelines[row_id] = replace(
        pipeline,
        close=VerifyingClose(pipeline.close.policy_id),
    )

    def load(_path, *, defer_fountain_validation=False):
        assert defer_fountain_validation
        return resumed, "3" * 64

    monkeypatch.setattr(
        discovery, "load_discovery_with_digest", load)
    monkeypatch.setattr(
        discovery,
        "save_discovery_with_digest",
        lambda _path, _state, **_kwargs: (True, "4" * 64),
    )
    monkeypatch.setattr(
        discovery, "_pipelines_for_state",
        lambda _request, _state: pipelines,
    )
    monkeypatch.setattr(
        discovery, "_capture_facts", lambda _capture: survey.facts)
    monkeypatch.setattr(
        discovery,
        "_execute_receive",
        lambda *_args, **_kwargs: pytest.fail(
            "close-only resume re-entered exact acquisition"),
    )

    diagnostics = []
    diagnostic_dir = tmp_path / "diag"

    def observer_factory(actual_spec, actual_pipeline):
        assert actual_spec is spec
        instance = ReceiveDiagnostics(
            diagnostic_dir,
            actual_spec,
            receiver_policy_id=actual_pipeline.policy_id,
            page_domain=(0,),
            qualification_status=actual_pipeline.qualification_status,
            qualification_notes=actual_pipeline.qualification_notes,
            interval_s=0.0,
            panel_width=112,
        )
        diagnostics.append(instance)
        return instance

    with pytest.warns(ProvisionalReceiverWarning):
        result = run_discovery_receive(
            request,
            observer_factory=observer_factory,
        )

    assert result.payload == payload
    assert result.state.status is DiscoveryStatus.VERIFIED
    assert len(diagnostics) == 1
    # Live-view products are gone with the kiss stub; the compact final
    # report is the remaining observer surface.
    written = diagnostics[0].finalize(result.state)
    names = {path.name for path in written}
    assert {"report.json", "diagnostic-health.json"} <= names
    report = json.loads(
        (diagnostic_dir / "report.json").read_text(encoding="utf-8"))
    assert report["qualification_status"] == "provisional"
    assert diagnostics[0].failures == ()
    event_names = [
        json.loads(line)["name"]
        for line in (diagnostic_dir / "events.jsonl").read_text(
            encoding="utf-8").splitlines()
    ]
    assert event_names == [
        "session.open", "close.check", "session.complete"]
    diagnostics[0].close()


def test_certificate_recognition_selects_and_conflict_refuses() -> None:
    state, _pipelines = _new_state(
        DiscoveryReceiveRequest((_capture(),)))
    certificate = TileCertificateRecord(
        "0" * 64, 0, (0, 0), b"\0", "attempt-0")
    first = state.branches[0]
    first = replace(
        first, certificates=(certificate,))
    recognized = replace(
        state, branches=(first, *state.branches[1:]))
    assert recognized.selected_row_id == first.format_row_id
    assert recognized.status is DiscoveryStatus.OPEN

    second_certificate = replace(certificate, certificate_id="1" * 64)
    second = recognized.branches[1]
    second = replace(
        second,
        certificates=(second_certificate,),
    )
    conflicted = replace(
        recognized,
        branches=(recognized.branches[0], second,
                  *recognized.branches[2:]),
    )
    assert conflicted.selected_row_id is None
    assert conflicted.status is DiscoveryStatus.INTEGRITY_FAILURE


def test_discovery_derives_wrong_c_exclusion_and_runs_remaining_row(
    monkeypatch, tmp_path,
) -> None:
    import holo.receive.discovery as discovery

    capture = _capture()
    survey = DiscoverySurvey(
        discovery._capture_facts(capture),
        3,
    )
    monkeypatch.setattr(discovery, "_survey_capture", lambda _item: survey)
    monkeypatch.setattr(
        discovery, "_capture_facts", lambda _item: survey.facts)

    def execute(
        _request, pipeline, _events, *, initial_state, **_kwargs,
    ):
        return ReceiveResult(
            initial_state,
            (),
            False,
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    monkeypatch.setattr(discovery, "_execute_receive", execute)
    request = DiscoveryReceiveRequest(
        (capture,), state_path=tmp_path / "discovery.json")
    with pytest.warns(ProvisionalReceiverWarning):
        result = run_discovery_receive(request)

    source_sha256 = survey.facts.source_sha256
    assert result.state.candidate_complete(
        source_sha256, "c2-r0550@3328x2304")
    assert result.state.candidate_complete(
        source_sha256, "c2-r0700@3328x2304")
    assert all(
        branch.capture(source_sha256) is None
        for branch in result.state.branches
        if branch.format_row_id.startswith("c2-")
    )
    assert result.state.selected_row_id is None
    assert load_discovery(tmp_path / "discovery.json") == result.state
    with pytest.warns(ProvisionalReceiverWarning):
        resumed = run_discovery_receive(request)
    assert resumed.state == result.state
    assert not resumed.state_changed


@pytest.mark.parametrize("persisted", (False, True))
def test_discovery_defers_all_close_work_through_survey_persistence(
    monkeypatch, tmp_path, persisted,
) -> None:
    import holo.receive.discovery as discovery
    import holo.receive.fountain_close as fountain_close

    capture = _capture()
    survey = DiscoverySurvey(discovery._capture_facts(capture), 3)
    monkeypatch.setattr(discovery, "_survey_capture", lambda _item: survey)
    monkeypatch.setattr(
        discovery, "_capture_facts", lambda _item: survey.facts)

    def forbidden_close(*_args, **_kwargs):
        raise AssertionError(
            "deferred discovery performed hidden fountain work")

    monkeypatch.setattr(
        fountain_close, "close_volume", forbidden_close)
    exact_requests = []

    execution_options = []

    def execute(
        exact_request, pipeline, _events, *, initial_state, **kwargs,
    ):
        exact_requests.append(exact_request)
        execution_options.append(kwargs)
        return ReceiveResult(
            initial_state,
            (),
            False,
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    monkeypatch.setattr(discovery, "_execute_receive", execute)
    request = DiscoveryReceiveRequest(
        (capture,),
        state_path=(
            tmp_path / "discovery.json" if persisted else None),
        candidate_row_ids=("c3-r0550@2240x1536",),
        page_hypotheses=(0,),
        defer_fountain_close=True,
    )
    with pytest.warns(ProvisionalReceiverWarning):
        run_discovery_receive(request)

    assert len(exact_requests) == 1
    assert exact_requests[0].defer_fountain_close
    assert execution_options[0]["finalize_deferred_close"] is False
    assert execution_options[0]["emit_terminal_summary"] is False


def test_discovery_performs_one_final_close_for_recognized_branch(
    monkeypatch,
) -> None:
    import holo.receive.discovery as discovery
    from holo.receive.cascade import scale_plan
    from holo.receive.session import (
        LevelRecord,
        apply_close,
        certificate_frontier_sha256,
    )
    from holo.receive.types import CloseRecord, CloseStatus
    from holo.receive.types import Stage

    capture = _capture()
    row_id = "c3-r0550@2240x1536"
    spec = FORMAT_ROWS[row_id]
    survey = DiscoverySurvey(discovery._capture_facts(capture), 3)
    monkeypatch.setattr(discovery, "_survey_capture", lambda _item: survey)
    monkeypatch.setattr(
        discovery, "_capture_facts", lambda _item: survey.facts)
    ordered = []
    observed = []
    observer_factory_calls = []

    def execute(
        exact_request,
        pipeline,
        _events,
        *,
        initial_state,
        persist_state,
        **kwargs,
    ):
        ordered.append("branch")
        _events.emit(
            "branch.work",
            Stage.INGEST,
            snapshot_factory=lambda: 1 / 0,
        )
        assert exact_request.defer_fountain_close
        assert kwargs["finalize_deferred_close"] is False
        assert kwargs["emit_terminal_summary"] is False
        plan = scale_plan(survey.facts.dpi, spec.cell_dots)
        retained = survey.facts.as_record(plan, LevelRecord())
        retained = replace(
            retained,
            levels=tuple(LevelRecord() for _lane in plan),
        )
        certificate = TileCertificateRecord(
            "0" * 64, 0, (0, 0), b"\0", "attempt-0")
        child = replace(
            initial_state,
            captures=(retained,),
            certificates=(certificate,),
        )
        persist_state(child)
        return ReceiveResult(
            child,
            (),
            True,
            observer_failures=_events.failures,
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    final_calls = []

    def finalize(
        branch,
        selected_spec,
        _pipeline,
        events,
        _state_path,
        persist_state,
    ):
        ordered.append("close")
        final_calls.append(branch)
        events.emit("close.check", Stage.CLOSE)
        assert selected_spec is spec
        record = CloseRecord(
            CloseStatus.VERIFIED,
            certificate_frontier_sha256(branch.certificates),
            "2" * 64,
            len(b"payload"),
        )
        closed = apply_close(branch, record)
        _changed, digest = persist_state(closed)
        events.bind_state(digest)
        return closed, b"payload", None, None

    monkeypatch.setattr(discovery, "_execute_receive", execute)
    monkeypatch.setattr(discovery, "_finalize_deferred_close", finalize)

    def observer_factory(actual_spec, _pipeline):
        observer_factory_calls.append(actual_spec.spec_id)

        def observe(event):
            observed.append(event)

        observe.wants_snapshots = True
        return observe

    request = DiscoveryReceiveRequest(
        (capture,),
        candidate_row_ids=(row_id,),
        page_hypotheses=(0,),
        defer_fountain_close=True,
    )
    with pytest.warns(ProvisionalReceiverWarning):
        result = run_discovery_receive(
            request,
            observer_factory=observer_factory,
        )

    assert ordered == ["branch", "close"]
    assert observer_factory_calls == [row_id]
    assert [event.name for event in observed] == [
        "branch.work", "close.check", "session.complete"]
    assert [event.sequence for event in observed] == [0, 1, 2]
    assert len(final_calls) == 1
    assert result.state.status is DiscoveryStatus.VERIFIED
    assert result.payload == b"payload"
    assert len(result.observer_failures) == 1
    assert "snapshot-builder: ZeroDivisionError" in (
        result.observer_failures[0])


def test_cli_decode_defaults_to_discovery(
    monkeypatch, tmp_path, capsys,
) -> None:
    import holo.receive as receive_api

    state, _pipelines = _new_state(
        DiscoveryReceiveRequest((_capture(),)))
    published = {}

    def run(request, *, observer_factory):
        published["request"] = request
        published["observer_factory"] = observer_factory
        return DiscoveryReceiveResult(
            state,
            False,
            qualification_status=ReceiverQualificationStatus.PROVISIONAL,
            qualification_notes=("qualification pending",),
        )

    monkeypatch.setattr(receive_api, "run_discovery_receive", run)
    status = cli.main([
        "decode",
        str(tmp_path / "unopened.tif"),
        "--scan-dpi", "600",
        "--state", str(tmp_path / "state.json"),
        "--out", str(tmp_path / "payload.bin"),
    ])
    assert status == 2
    assert published["request"].candidate_row_ids is None
    assert not published["request"].defer_fountain_close
    assert published["observer_factory"] is None
    assert "format: unresolved" in capsys.readouterr().out


def test_cli_complete_reaches_discovery_request(
    monkeypatch, tmp_path,
) -> None:
    import holo.receive as receive_api

    state, _pipelines = _new_state(
        DiscoveryReceiveRequest((_capture(),)))
    published = {}

    def run(request, *, observer_factory):
        published["request"] = request
        assert observer_factory is None
        return DiscoveryReceiveResult(
            state,
            False,
            qualification_status=ReceiverQualificationStatus.PROVISIONAL,
            qualification_notes=("qualification pending",),
        )

    monkeypatch.setattr(receive_api, "run_discovery_receive", run)
    assert cli.main([
        "decode",
        str(tmp_path / "unopened.tif"),
        "--scan-dpi", "600",
        "--state", str(tmp_path / "state.json"),
        "--out", str(tmp_path / "payload.bin"),
        "--complete",
    ]) == 2

    assert published["request"].defer_fountain_close


@pytest.mark.parametrize(
    "printer_id",
    ("default", "hp-m281", "xerox-altalink-c8245"),
)
def test_cli_printer_hint_does_not_promote_catalog_only_color_rows(
    monkeypatch, tmp_path, printer_id,
) -> None:
    import holo.receive as receive_api

    state, _pipelines = _new_state(
        DiscoveryReceiveRequest((_capture(),)))
    published = {}

    def run(request, *, observer_factory):
        published["request"] = request
        assert observer_factory is None
        return DiscoveryReceiveResult(
            state,
            False,
            qualification_status=ReceiverQualificationStatus.PROVISIONAL,
            qualification_notes=("qualification pending",),
        )

    monkeypatch.setattr(receive_api, "run_discovery_receive", run)
    assert cli.main([
        "decode",
        str(tmp_path / "unopened.tif"),
        "--scan-dpi", "600",
        "--printer", printer_id,
        "--state", str(tmp_path / "state.json"),
        "--out", str(tmp_path / "payload.bin"),
    ]) == 2

    candidates = published["request"].candidate_row_ids
    assert candidates == DEFAULT_DISCOVERY_ROW_IDS
    assert all("cmy" not in row_id for row_id in candidates)


def test_cli_without_coding_resumes_an_exact_registered_state(
    monkeypatch, tmp_path,
) -> None:
    import holo.receive as receive_api
    from holo.receive.production import production_pipeline
    from holo.receive.runtime import ReceiveRequest

    spec = registered_format_rows()[0]
    bootstrap = ReceiveRequest(spec, (_capture(),))
    policy = production_pipeline(bootstrap)
    state = SessionState.create(spec.spec_id, policy.policy_id, None)
    state_path = tmp_path / "exact.json"
    save_session(state_path, state)
    published = {}

    def run(request, *, pipeline, observer, **kwargs):
        published["request"] = request
        assert observer is None
        return ReceiveResult(
            state,
            (),
            False,
            qualification_status=pipeline.qualification_status,
            qualification_notes=pipeline.qualification_notes,
        )

    monkeypatch.setattr(receive_api, "run_receive", run)
    status = cli.main([
        "decode",
        str(tmp_path / "unopened.tif"),
        "--scan-dpi", "600",
        "--state", str(state_path),
        "--out", str(tmp_path / "payload.bin"),
        "--complete",
    ])
    assert status == 2
    assert published["request"].spec == spec
    assert published["request"].defer_fountain_close


def test_cli_refuses_exact_hint_for_discovery_state(tmp_path) -> None:
    state, _pipelines = _new_state(
        DiscoveryReceiveRequest((_capture(),)))
    state_path = tmp_path / "discovery.json"
    save_discovery(state_path, state)
    with pytest.raises(SystemExit,
                       match="cannot resume with an explicit format"):
        cli.main([
            "decode",
            str(tmp_path / "unopened.tif"),
            "--scan-dpi", "600",
            "--coding", "c3-r0550",
            "--state", str(state_path),
            "--out", str(tmp_path / "payload.bin"),
        ])

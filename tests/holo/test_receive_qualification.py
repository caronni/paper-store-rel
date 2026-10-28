"""Deferred-close (`--complete`) family + qualification-envelope pins.

Driven on the shared synthetic runtime fixtures.  The former slow 4-case
production roundtrip battery hook was retired in Phase 7
(PAYLOAD-REWORK-PLAN 7.2); its guard value lives in the bounded phased
end-to-end (``test_phased_roundtrip_e2e.py``, HOLO_RUN_SLOW_TESTS lane).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from holo import cli
from holo.devices.profiles import make_spec
from holo.receive import tiles
from holo.receive.observer import (
    ReceiverQualificationStatus,
    validate_qualification,
)
from holo.receive.placement.defaults import (
    V1_PRODUCTION_QUALIFICATION_NOTES,
)

def test_complete_defers_one_close_until_all_requested_work(
    tmp_path,
) -> None:
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.cascade import scale_plan
    from holo.receive.runtime import ReceiveRequest, run_receive
    from holo.receive.session import CaptureStatus, SessionStatus

    images = (tmp_path / "capture-a.png", tmp_path / "capture-b.png")
    for seed, image in enumerate(images, 31_000):
        fixtures._write_image(image, seed)
    spec = fixtures._spec()
    plan = scale_plan(1200.0, spec.cell_dots)
    captures = tuple(fixtures._capture(image) for image in images)
    assert len(plan) > 1

    class CountingClose:
        def __init__(self, delegate):
            self.delegate = delegate
            self.calls = 0

        @property
        def policy_id(self):
            return self.delegate.policy_id

        def process(self, context):
            self.calls += 1
            return self.delegate.process(context)

    default_close = CountingClose(fixtures._TerminalClose(False))
    default_pipeline, default_calls = fixtures._pipeline()
    default_pipeline = replace(
        default_pipeline, close=default_close)
    early = run_receive(
        ReceiveRequest(
            spec, captures, tmp_path / "early.json"),
        pipeline=default_pipeline,
    )

    assert early.state.status is SessionStatus.VERIFIED
    assert early.payload == b"payload"
    # v0.33 rung-major driver: every requested capture is opened up front,
    # so the result reports one run row per request even though the close
    # verified at the first barrier; only the capture that committed a
    # barrier is retained in durable state.
    assert len(early.captures) == len(captures) == 2
    assert len(early.state.captures) == 1
    assert early.state.captures[0].status is CaptureStatus.ACTIVE
    assert len(early.state.captures[0].levels) == 1
    assert early.captures[0].status is CaptureStatus.ACTIVE
    assert early.captures[0].barriers_committed == 1
    assert early.captures[1].status is CaptureStatus.ACTIVE
    assert early.captures[1].barriers_committed == 0
    assert not early.captures[1].state_changed
    assert tuple(len(rows) for rows in default_calls) == (1, 1, 1)
    assert default_close.calls == 1

    complete_close = CountingClose(fixtures._TerminalClose(False))
    complete_pipeline, complete_calls = fixtures._pipeline()
    complete_pipeline = replace(
        complete_pipeline, close=complete_close)
    assert complete_pipeline.policy_id == default_pipeline.policy_id
    events = []
    complete = run_receive(
        ReceiveRequest(
            spec,
            captures,
            tmp_path / "complete.json",
            defer_fountain_close=True,
            # v0.42: --complete no longer implies the lane families; the
            # full plan (ladder + M-levels + R-levels) needs --refine,
            # which covers pending M-levels by the plan-prefix law.
            run_refine=True,
        ),
        pipeline=complete_pipeline,
        observer=events.append,
    )

    assert complete.state.status is SessionStatus.VERIFIED
    assert complete.payload == early.payload
    assert len(complete.state.captures) == len(captures)
    assert all(
        capture.status is CaptureStatus.COMPLETE
        and len(capture.levels) == len(plan)
        for capture in complete.state.captures
    )
    assert all(
        run.status is CaptureStatus.COMPLETE
        and run.barriers_committed == len(plan)
        for run in complete.captures
    )
    assert tuple(len(rows) for rows in complete_calls) == (
        2 * len(plan), 2 * len(plan), 2 * len(plan))
    assert complete_close.calls == 1
    close_events = [
        index for index, event in enumerate(events)
        if event.name == "close.check"
    ]
    barrier_events = [
        index for index, event in enumerate(events)
        if event.name == "barrier.committed"
    ]
    assert len(close_events) == 1
    assert len(barrier_events) == 2 * len(plan)
    assert close_events[0] > barrier_events[-1]
    # Rung-major breadth-first (v0.33): during the ladder phase both
    # captures commit their rung-k barrier before any rung-k+1 barrier;
    # the mop-up tail (and, v0.42, the refinement levels behind it) then
    # runs EV-ordered across captures.
    barrier_captures = [
        events[index].capture_id for index in barrier_events]
    n_ladder = sum(
        1 for lane in plan
        if lane.mopup_of is None and lane.refine_of is None)
    assert all(
        set(barrier_captures[2 * rung:2 * rung + 2]) == set(
            run.source_sha256 for run in complete.captures)
        for rung in range(n_ladder)
    )
    # The tail commits every remaining (M + R) level of both captures.
    from collections import Counter
    assert Counter(barrier_captures[2 * n_ladder:]) == Counter({
        run.source_sha256: len(plan) - n_ladder
        for run in complete.captures})


@pytest.mark.parametrize(
    "terminal_status",
    ("open", "verified", "integrity_failure", "unsupported"),
)
def test_complete_terminal_summary_reuses_final_numerical_close(
    tmp_path,
    terminal_status,
) -> None:
    import hashlib

    import _qualify_runtime_fixtures as fixtures
    from holo.receive.close_progress import CloseBlockProgress, CloseProgress
    from holo.receive.runtime import CloseExecution, ReceiveRequest, run_receive
    from holo.receive.types import CloseRecord, CloseStatus

    image = tmp_path / f"final-close-{terminal_status}.png"
    fixtures._write_image(
        image,
        31_500 + (
            "open",
            "verified",
            "integrity_failure",
            "unsupported",
        ).index(terminal_status),
    )
    solved = terminal_status == "verified"
    received = 11 if solved else 9
    rank = 10 if solved else 8

    class NumericalClose:
        def __init__(self):
            self.calls = 0
            self.progress_calls = 0

        @property
        def policy_id(self):
            return (
                "qualification/final-numerical-close/v1/"
                f"{terminal_status}"
            )

        def process(self, context):
            self.calls += 1
            payload = b"payload"
            status = CloseStatus(terminal_status)
            if status is CloseStatus.VERIFIED:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    hashlib.sha256(payload).hexdigest(),
                    len(payload),
                )
            elif status is CloseStatus.INTEGRITY_FAILURE:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    reason="synthetic integrity failure",
                )
            elif status is CloseStatus.UNSUPPORTED:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    metadata_version=1,
                    reason="synthetic unsupported metadata",
                )
            else:
                record = CloseRecord()

            def progress():
                self.progress_calls += 1
                return CloseProgress(
                    10,
                    received,
                    (CloseBlockProgress(
                        0, 10, received, rank, solved),),
                )

            return CloseExecution(
                record, payload if solved else None, progress)

    class FineObserver:
        wants_snapshots = True

        def __init__(self):
            self.events = []

        def __call__(self, event):
            self.events.append(event)

    close = NumericalClose()
    pipeline, _calls = fixtures._pipeline()
    pipeline = replace(pipeline, close=close)
    observer = FineObserver()
    result = run_receive(
        ReceiveRequest(
            fixtures._spec(),
            (fixtures._capture(image),),
            defer_fountain_close=True,
        ),
        pipeline=pipeline,
        observer=observer,
    )

    close_event, = (
        event for event in observer.events if event.name == "close.check")
    summary_event, = (
        event for event in observer.events if event.name == "session.complete")
    assert close.calls == 1
    # Close progress is a lazy observer product: this opted-in observer
    # triggers it once per consuming snapshot (close.check + the terminal
    # summary's close value) while the numerical close still ran exactly once.
    assert close.progress_calls == 2
    assert close_event.snapshot["kind"] == "close"
    assert close_event.snapshot["record"] is not None
    assert close_event.snapshot["progress"].symbols_used == received
    assert summary_event.snapshot["kind"] == "session_summary"
    assert summary_event.snapshot["close"]["kind"] == "close"
    assert result.state.status.value == terminal_status


def test_complete_does_not_reopen_an_existing_verified_session(
    tmp_path,
) -> None:
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.cascade import scale_plan
    from holo.receive.runtime import ReceiveRequest, run_receive
    from holo.receive.session import authoritative_sha256

    image = tmp_path / "capture.png"
    fixtures._write_image(image, 32_000)
    spec = fixtures._spec()
    capture = fixtures._capture(image)
    state_path = tmp_path / "resume.json"

    # v0.42: the deferred close finalizes at the invocation's flag-bounded
    # end; --refine drives the full plan (ladder + M + R levels), so the
    # verified session under test carries a fully processed capture.
    early_pipeline, _calls = fixtures._pipeline()
    early_pipeline = replace(
        early_pipeline, close=fixtures._TerminalClose(False))
    early = run_receive(
        ReceiveRequest(
            spec, (capture,), state_path, defer_fountain_close=True,
            run_refine=True),
        pipeline=early_pipeline,
    )
    assert len(early.state.captures[0].levels) == len(
        scale_plan(1200.0, spec.cell_dots))

    before = authoritative_sha256(early.state)
    resume_pipeline, resume_calls = fixtures._pipeline()
    resume_pipeline = replace(
        resume_pipeline, close=fixtures._TerminalClose(False))
    resumed = run_receive(
        ReceiveRequest(
            spec,
            (capture,),
            state_path,
            defer_fountain_close=True,
        ),
        pipeline=resume_pipeline,
    )

    assert resumed.payload == early.payload
    assert not resumed.state_changed
    assert authoritative_sha256(resumed.state) == before
    assert resumed.captures == ()
    assert tuple(len(rows) for rows in resume_calls) == (0, 0, 0)


@pytest.mark.parametrize(
    "terminal_status",
    ("verified", "integrity_failure", "unsupported"),
)
def test_complete_terminal_resume_runs_one_final_close_with_diagnostics(
    monkeypatch,
    tmp_path,
    terminal_status,
) -> None:
    import hashlib

    import holo.receive.fountain_close as fountain_close
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.close_progress import CloseBlockProgress, CloseProgress
    from holo.receive.runtime import CloseExecution, ReceiveRequest, run_receive
    from holo.receive.types import CloseRecord, CloseStatus

    image = tmp_path / f"{terminal_status}-bootstrap.png"
    fixtures._write_image(image, 32_250)
    spec = fixtures._spec()
    state_path = tmp_path / f"{terminal_status}-resume.json"
    payload = b"payload"
    policy_id = (
        "qualification/deferred-terminal-replay/v1/"
        f"{terminal_status}"
    )

    class InitialTerminalClose:
        def __init__(self):
            self.policy_id = policy_id

        def process(self, context):
            status = CloseStatus(terminal_status)
            if status is CloseStatus.VERIFIED:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    hashlib.sha256(payload).hexdigest(),
                    len(payload),
                )
            elif status is CloseStatus.UNSUPPORTED:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    metadata_version=1,
                    reason="synthetic unsupported metadata",
                )
            else:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    reason="synthetic integrity failure",
                )
            return CloseExecution(
                record,
                payload if status is CloseStatus.VERIFIED else None,
            )

    # v0.42 bootstrap: defer the close and drive the full plan (--refine
    # covers pending M-levels by the plan-prefix law) so the retained
    # terminal state has a fully COMPLETE capture — the shape a
    # `--complete --refine` run produces.
    initial_pipeline, _initial_calls = fixtures._pipeline()
    initial_pipeline = replace(
        initial_pipeline, close=InitialTerminalClose())
    initial = run_receive(
        ReceiveRequest(
            spec,
            (fixtures._capture(image),),
            state_path,
            defer_fountain_close=True,
            run_refine=True,
        ),
        pipeline=initial_pipeline,
    )
    assert initial.state.status.value == terminal_status
    assert all(
        capture.status is fixtures.CaptureStatus.COMPLETE
        for capture in initial.state.captures)

    fountain_calls = 0

    def counted_close_volume(*_args, **_kwargs):
        nonlocal fountain_calls
        fountain_calls += 1
        return object()

    monkeypatch.setattr(
        fountain_close, "close_volume", counted_close_volume)

    class ReproducingClose:
        def __init__(self):
            self.policy_id = policy_id
            self.calls = 0
            self.progress_calls = 0

        def process(self, context):
            self.calls += 1
            fountain_close.close_volume((), context.spec)
            solved = terminal_status == "verified"

            def progress():
                self.progress_calls += 1
                return CloseProgress(
                    10,
                    11,
                    (CloseBlockProgress(
                        0, 10, 11, 10 if solved else 9, solved),),
                )

            return CloseExecution(
                context.state.close,
                payload if solved else None,
                progress,
            )

    class FineObserver:
        wants_snapshots = True

        def __init__(self):
            self.events = []

        def __call__(self, event):
            self.events.append(event)

    close = ReproducingClose()
    resume_pipeline, resume_calls = fixtures._pipeline()
    resume_pipeline = replace(resume_pipeline, close=close)
    observer = FineObserver()
    missing_capture = tmp_path / "must-not-be-acquired.png"
    resumed = run_receive(
        ReceiveRequest(
            spec,
            (fixtures._capture(missing_capture),),
            state_path,
            defer_fountain_close=True,
        ),
        pipeline=resume_pipeline,
        observer=observer,
    )

    close_event, = (
        event for event in observer.events if event.name == "close.check")
    summary_event, = (
        event for event in observer.events if event.name == "session.complete")
    assert close.calls == fountain_calls == 1
    # Close progress is a lazy observer product: this opted-in observer
    # triggers it once per consuming snapshot (close.check + the terminal
    # summary's close value); the numerical close itself still ran once.
    assert close.progress_calls == 2
    assert tuple(len(rows) for rows in resume_calls) == (0, 0, 0)
    assert resumed.captures == ()
    assert not resumed.state_changed
    assert resumed.payload == (
        payload if terminal_status == "verified" else None)
    assert resumed.state.status.value == terminal_status
    assert close_event.snapshot["kind"] == "close"
    assert close_event.snapshot["progress"].symbols_used == 11
    assert summary_event.snapshot["kind"] == "session_summary"
    assert summary_event.snapshot["close"]["kind"] == "close"


def test_complete_interruption_keeps_partial_capture_open_without_close(
    tmp_path,
) -> None:
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.observer import event_sink_for_run
    from holo.receive.runtime import (
        ReceiveRequest,
        _execute_receive,
    )
    from holo.receive.session import CaptureStatus, SessionStatus

    image = tmp_path / "interrupted.png"
    fixtures._write_image(image, 32_500)
    spec = fixtures._spec()
    request = ReceiveRequest(
        spec,
        (fixtures._capture(image),),
        tmp_path / "interrupted.json",
        defer_fountain_close=True,
    )

    class CountingClose:
        policy_id = fixtures._TerminalClose(False).policy_id

        def __init__(self):
            self.calls = 0

        def process(self, context):
            self.calls += 1
            return fixtures._TerminalClose(False).process(context)

    close = CountingClose()
    pipeline, calls = fixtures._pipeline()
    pipeline = replace(pipeline, close=close)
    events = event_sink_for_run(
        None,
        pipeline.qualification_status,
        pipeline.qualification_notes,
        format_id=spec.spec_id,
        receiver_policy_id=pipeline.policy_id,
        page_domain=tuple(range(spec.max_pages)),
    )
    result = _execute_receive(
        request,
        pipeline,
        events,
        stop_requested=lambda: True,
    )

    assert result.state.status is SessionStatus.OPEN
    assert result.state.captures[0].status is CaptureStatus.ACTIVE
    assert len(result.state.captures[0].levels) == 1
    assert close.calls == 0
    assert tuple(len(rows) for rows in calls) == (1, 1, 1)


def test_deferred_discovery_child_emits_no_false_terminal_summary(
    tmp_path,
) -> None:
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.observer import event_sink_for_run
    from holo.receive.runtime import ReceiveRequest, _execute_receive
    from holo.receive.session import CaptureStatus, SessionStatus

    image = tmp_path / "discovery-child.png"
    fixtures._write_image(image, 32_750)
    spec = fixtures._spec()
    request = ReceiveRequest(
        spec,
        (fixtures._capture(image),),
        tmp_path / "discovery-child.json",
        defer_fountain_close=True,
        run_refine=True,
    )

    class ForbiddenClose:
        policy_id = fixtures._TerminalClose(False).policy_id

        def process(self, _context):
            raise AssertionError(
                "deferred discovery child performed a close")

    pipeline, _calls = fixtures._pipeline()
    pipeline = replace(pipeline, close=ForbiddenClose())
    observed = []
    events = event_sink_for_run(
        observed.append,
        pipeline.qualification_status,
        pipeline.qualification_notes,
        format_id=spec.spec_id,
        receiver_policy_id=pipeline.policy_id,
        page_domain=tuple(range(spec.max_pages)),
    )
    result = _execute_receive(
        request,
        pipeline,
        events,
        finalize_deferred_close=False,
        emit_terminal_summary=False,
    )

    assert result.state.status is SessionStatus.OPEN
    assert result.state.captures[0].status is CaptureStatus.COMPLETE
    assert all(event.name != "session.complete" for event in observed)
    assert observed[-1].name == "capture.complete"


def test_complete_resume_closes_an_open_fully_processed_ladder_once(
    tmp_path,
) -> None:
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.cascade import scale_plan
    from holo.receive.runtime import ReceiveRequest, run_receive
    from holo.receive.session import CaptureStatus, SessionStatus

    image = tmp_path / "close-crash.png"
    fixtures._write_image(image, 33_000)
    spec = fixtures._spec()
    capture = fixtures._capture(image)
    state_path = tmp_path / "close-crash.json"
    plan = scale_plan(1200.0, spec.cell_dots)

    class CrashAtClose:
        policy_id = fixtures._TerminalClose(False).policy_id

        def process(self, _context):
            raise RuntimeError("injected final close crash")

    pipeline, first_calls = fixtures._pipeline()
    pipeline = replace(pipeline, close=CrashAtClose())
    with pytest.raises(RuntimeError, match="final close crash"):
        run_receive(
            ReceiveRequest(
                spec,
                (capture,),
                state_path,
                defer_fountain_close=True,
                run_refine=True,
            ),
            pipeline=pipeline,
        )
    retained = fixtures.load_session(state_path)
    assert retained.status is SessionStatus.OPEN
    assert retained.captures[0].status is CaptureStatus.COMPLETE
    assert len(retained.captures[0].levels) == len(plan)
    assert tuple(len(rows) for rows in first_calls) == (
        len(plan), len(plan), len(plan))

    class CountingClose:
        policy_id = fixtures._TerminalClose(False).policy_id

        def __init__(self):
            self.calls = 0

        def process(self, context):
            self.calls += 1
            return fixtures._TerminalClose(False).process(context)

    close = CountingClose()
    resumed_pipeline, resumed_calls = fixtures._pipeline()
    resumed_pipeline = replace(resumed_pipeline, close=close)
    resumed = run_receive(
        ReceiveRequest(
            spec,
            (capture,),
            state_path,
            defer_fountain_close=True,
        ),
        pipeline=resumed_pipeline,
    )

    assert resumed.state.status is SessionStatus.VERIFIED
    assert resumed.payload == b"payload"
    assert close.calls == 1
    assert resumed.captures[0].barriers_committed == 0
    assert tuple(len(rows) for rows in resumed_calls) == (0, 0, 0)


def test_production_pipeline_is_provisional_with_blockers() -> None:
    notes = V1_PRODUCTION_QUALIFICATION_NOTES
    assert len(notes) == 2
    assert "physical/null" in notes[0]
    assert "0.176" in notes[1]
    assert "whole-word rival" in notes[1]
    validate_qualification(ReceiverQualificationStatus.PROVISIONAL, notes)


def test_qualification_envelope_refuses_inconsistent_status() -> None:
    with pytest.raises(ValueError):
        validate_qualification(ReceiverQualificationStatus.PROVISIONAL, ())
    with pytest.raises(ValueError):
        validate_qualification(
            ReceiverQualificationStatus.QUALIFIED, ("blocker",))
    with pytest.raises(TypeError):
        validate_qualification(ReceiverQualificationStatus.PROVISIONAL, ("",))


def test_current_attempt_floor_is_rung_specific() -> None:
    c3 = make_spec("c3-r0550", "default")
    c2 = make_spec("c2-r0700", "default")
    assert tiles.k_eff_bits(c3) == 2240 - c3.n_sites
    assert tiles.k_eff_bits(c2) == 2880 - c2.n_sites
    assert tiles.k_eff_bits(c2) > tiles.k_eff_bits(c3)


def test_decode_help_discloses_provisional_status_and_diag(capsys) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["decode", "--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "provisional historical placement constants" in help_text
    assert "--diag" in help_text and "--diag-dir" in help_text
    assert "--complete" in help_text
    assert "defer fountain close" in help_text
    assert "--detector-profile" not in help_text
    assert "pava-v1" not in help_text


@pytest.mark.parametrize(
    "terminal_status",
    ("verified", "integrity_failure", "unsupported"),
)
def test_cli_complete_terminal_resume_has_one_fountain_call(
    monkeypatch,
    tmp_path,
    terminal_status,
) -> None:
    import hashlib

    import holo.receive.fountain_close as fountain_close
    import holo.receive.production as receive_production
    import _qualify_runtime_fixtures as fixtures
    from holo.format.registry import get_format_row
    from holo.receive.runtime import CloseExecution, ReceiveRequest, run_receive
    from holo.receive.types import CloseRecord, CloseStatus

    spec = get_format_row("c3-r0550@2240x1536")
    image = tmp_path / f"{terminal_status}-cli-bootstrap.png"
    fixtures._write_image(image, 33_250)
    state_path = tmp_path / f"{terminal_status}-cli.json"
    payload = b"payload"
    policy_id = (
        "qualification/deferred-cli-terminal/v1/"
        f"{terminal_status}"
    )

    class InitialTerminalClose:
        def __init__(self):
            self.policy_id = policy_id

        def process(self, context):
            status = CloseStatus(terminal_status)
            if status is CloseStatus.VERIFIED:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    hashlib.sha256(payload).hexdigest(),
                    len(payload),
                )
            elif status is CloseStatus.UNSUPPORTED:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    metadata_version=1,
                    reason="synthetic unsupported metadata",
                )
            else:
                record = CloseRecord(
                    status,
                    context.certificate_frontier_sha256,
                    reason="synthetic integrity failure",
                )
            return CloseExecution(
                record,
                payload if status is CloseStatus.VERIFIED else None,
            )

    # v0.42 bootstrap: defer the close and drive the full plan (ladder,
    # M-levels, R-levels) — the shape the CLI's own `--complete --refine`
    # runs produce and later resume against.
    initial_pipeline, _initial_calls = fixtures._pipeline()
    initial_pipeline = replace(
        initial_pipeline, close=InitialTerminalClose())
    initial = run_receive(
        ReceiveRequest(
            spec,
            (fixtures._capture(image),),
            state_path,
            defer_fountain_close=True,
            run_refine=True,
        ),
        pipeline=initial_pipeline,
    )
    assert initial.state.status.value == terminal_status
    assert all(
        capture.status is fixtures.CaptureStatus.COMPLETE
        for capture in initial.state.captures)

    fountain_calls = 0

    def counted_close_volume(*_args, **_kwargs):
        nonlocal fountain_calls
        fountain_calls += 1
        return object()

    monkeypatch.setattr(
        fountain_close, "close_volume", counted_close_volume)

    class ReproducingClose:
        def __init__(self):
            self.policy_id = policy_id

        def process(self, context):
            fountain_close.close_volume((), context.spec)
            return CloseExecution(
                context.state.close,
                payload if terminal_status == "verified" else None,
            )

    resume_pipeline, resume_calls = fixtures._pipeline()
    resume_pipeline = replace(
        resume_pipeline, close=ReproducingClose())
    monkeypatch.setattr(
        receive_production,
        "production_pipeline",
        lambda _request: resume_pipeline,
    )

    output = tmp_path / f"{terminal_status}-cli.bin"
    status = cli.main([
        "decode",
        str(tmp_path / "must-not-be-acquired.png"),
        "--scan-dpi", "1200",
        "--state", str(state_path),
        "--out", str(output),
        "--complete",
    ])

    assert status == (0 if terminal_status == "verified" else 2)
    if terminal_status == "verified":
        assert output.read_bytes() == payload
    else:
        assert not output.exists()
    assert fountain_calls == 1
    assert tuple(len(rows) for rows in resume_calls) == (0, 0, 0)


def test_cli_rejects_too_small_diagnostic_panes(capsys) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main([
            "decode", "unopened.tif", "--scan-dpi", "600",
            "--coding", "c3-r0550",
            "--state", "state.json", "--out", "payload.bin",
            "--diag", "--diag-panel-width", "79",
        ])
    assert stopped.value.code == 2
    assert "must be at least 80 pixels" in capsys.readouterr().err


def test_cli_diag_report_receives_provisional_result(
    monkeypatch, tmp_path,
) -> None:
    import holo.receive as receive_api
    import holo.receive.diag as receive_diag
    import holo.receive.production as receive_production
    from holo.receive.runtime import (
        ReceiveResult,
        ReceiverQualificationStatus,
    )
    from holo.receive.session import SessionState

    spec = make_spec("c3-r0550", "default")
    notes = ("production qualification remains outstanding",)
    result = ReceiveResult(
        SessionState.create(spec.spec_id, "qualification/cli-diag-v1", None),
        (),
        False,
        qualification_status=ReceiverQualificationStatus.PROVISIONAL,
        qualification_notes=notes,
    )
    published = {}

    class Pipeline:
        policy_id = "qualification/cli-diag-v1"
        qualification_status = ReceiverQualificationStatus.PROVISIONAL
        qualification_notes = notes

    class Diagnostics:
        failures = ()

        def __init__(self, directory, report_spec, **kwargs):
            published["constructor"] = {
                "directory": directory,
                "spec": report_spec,
                **kwargs,
            }

        def __call__(self, event):
            del event

        def finalize(self, state):
            published["finalize"] = {"state": state}
            return (tmp_path / "diag" / "report.json",)

    monkeypatch.setattr(
        receive_api,
        "run_receive",
        lambda request, *, pipeline, observer, **kwargs: result,
    )
    monkeypatch.setattr(
        receive_production,
        "production_pipeline",
        lambda request: Pipeline(),
    )
    monkeypatch.setattr(
        receive_diag,
        "ReceiveDiagnostics",
        Diagnostics,
    )
    status = cli.main([
        "decode", str(tmp_path / "unopened.tif"),
        "--scan-dpi", "600",
        "--coding", "c3-r0550",
        "--state", str(tmp_path / "state.json"),
        "--out", str(tmp_path / "payload.bin"),
        "--diag", "--diag-dir", str(tmp_path / "diag"),
    ])

    assert status == 2
    constructor = dict(published["constructor"])
    assert callable(constructor.pop("on_server"))
    assert constructor == {
        "directory": tmp_path / "diag",
        "spec": spec,
        "receiver_policy_id": "qualification/cli-diag-v1",
        "page_domain": tuple(range(spec.max_pages)),
        "qualification_status": ReceiverQualificationStatus.PROVISIONAL,
        "qualification_notes": notes,
        "interval_s": 3.0,
        "panel_width": 600,
        "port": None,
        "route_domains": None,
    }
    assert published["finalize"] == {
        "state": result.state,
    }

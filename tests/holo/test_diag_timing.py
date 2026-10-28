"""Contract for the doctrine profiling observer (single-decode harness)."""
from __future__ import annotations

import pytest

from holo import cli
from holo.receive.diag.timing import TimingObserver, render_timing_table
from holo.receive.types import Detail, RuntimeEvent, Stage


def _event(sequence: int, name: str, stage: Stage,
           details: tuple[Detail, ...] = (),
           capture_id: str | None = "a" * 64) -> RuntimeEvent:
    return RuntimeEvent(
        sequence, name, stage, capture_id=capture_id, details=details)


def _timed(lane_id: str, wall: float, observer: float) -> tuple[Detail, ...]:
    return (
        Detail("lane.id", lane_id),
        Detail("timing.wall_seconds", wall),
        Detail("timing.observer_seconds", observer),
        Detail("timing.processor_seconds", wall - observer),
    )


def test_timing_observer_accumulates_per_capture_lane_stage() -> None:
    observer = TimingObserver()
    observer(_event(0, "stage.open", Stage.SURVEY,
                    (Detail("lane.id", "l00"),)))
    observer(_event(1, "stage.complete", Stage.SURVEY,
                    _timed("l00", 1.5, 0.5)))
    observer(_event(2, "stage.complete", Stage.ADDRESS,
                    _timed("l00", 4.0, 1.0)))
    observer(_event(3, "stage.refused", Stage.PAYLOAD,
                    _timed("l00", 2.0, 0.0)))
    observer(_event(4, "stage.complete", Stage.SURVEY,
                    _timed("l01", 0.25, 0.0)))
    # A headless emission carries no timing details and must be ignored.
    observer(_event(5, "stage.complete", Stage.ADDRESS,
                    (Detail("lane.id", "l01"),)))
    # A second event for an existing cell accumulates.
    observer(_event(6, "stage.complete", Stage.SURVEY,
                    _timed("l00", 0.5, 0.0)))

    rows = observer.rows
    assert [(row.lane_id, row.stage, row.calls) for row in rows] == [
        ("l00", "survey", 2),
        ("l00", "address", 1),
        ("l00", "payload", 1),
        ("l01", "survey", 1),
    ]
    survey = rows[0]
    assert survey.wall_seconds == pytest.approx(2.0)
    assert survey.observer_seconds == pytest.approx(0.5)
    assert survey.processor_seconds == pytest.approx(1.5)
    assert observer.total_processor_seconds == pytest.approx(
        1.5 + 3.0 + 2.0 + 0.25)

    table = render_timing_table(observer)
    assert "l00" in table and "l01" in table
    assert "survey" in table and "address" in table
    assert "TOTAL processor" in table


def test_timing_observer_renders_a_headless_placeholder() -> None:
    assert "no instrumented stage events" in render_timing_table(
        TimingObserver())


def test_decode_help_discloses_profile_timing(capsys) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["decode", "--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "--profile-timing" in help_text
    assert "per-stage processor" in help_text


def test_profile_timing_refuses_diag(tmp_path) -> None:
    with pytest.raises(SystemExit, match="conflicts with --diag"):
        cli.main([
            "decode", str(tmp_path / "scan.png"),
            "--scan-dpi", "600",
            "--coding", "c3-r0550",
            "--state", str(tmp_path / "state.json"),
            "-o", str(tmp_path / "out.bin"),
            "--profile-timing", "--diag",
        ])

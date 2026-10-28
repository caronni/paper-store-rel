"""EventSink pins for the v0.33 phased-schedule diagnostics (D14).

Two properties the viewer work leans on and that must not drift:

* ``capture.resume`` folds the event context exactly like ``capture.open``
  — the capture/lane envelope resets so later lane events rebuild it —
  while presentation-side capture counting is the VIEWER's duty (the sink
  never counts captures at all);
* a headless sink stays timing-neutral (§10.6): emitting scalar events —
  including the ``address.cold_progress`` heartbeat — performs no clock
  reads and attaches no snapshots.
"""
from __future__ import annotations

from holo.receive.observer import EventSink
from holo.receive.types import Detail, RuntimeEvent, Stage


def _sink(seen: list[RuntimeEvent]) -> EventSink:
    return EventSink(seen.append, "provisional", ("observer pin",))


def test_capture_resume_folds_context_like_capture_open() -> None:
    seen: list[RuntimeEvent] = []
    sink = _sink(seen)
    sink.emit("capture.open", Stage.INGEST, capture_id="a" * 64,
              details=(Detail("source.sha256", "a" * 64),))
    sink.emit("lane.open", Stage.SCHEDULE,
              details=(Detail("lane.id", "l00"),
                       Detail("level.ordinal", 0),
                       Detail("level.total", 4),
                       Detail("level.ppc.num", 2),
                       Detail("level.ppc.den", 1),
                       Detail("level.effective_dpi", 1200.0)))
    context = seen[-1].context
    assert context.source_sha256 == "a" * 64
    assert context.lane_id == "l00"
    assert context.level_ordinal == 0
    assert context.ppc == (2, 1)
    assert context.effective_dpi == 1200.0

    # The v0.33 mid-phase switch resets the capture/lane envelope exactly
    # like capture.open; the resumed capture's identity rides capture_id
    # and the next lane events rebuild the lane fields.
    sink.emit("capture.resume", Stage.SCHEDULE, capture_id="b" * 64)
    event = seen[-1]
    assert event.capture_id == "b" * 64
    assert event.context.source_sha256 is None
    assert event.context.lane_id is None
    assert event.context.level_ordinal is None
    assert event.context.ppc is None
    assert event.context.effective_dpi is None


def test_ordinary_events_leave_capture_context_standing() -> None:
    seen: list[RuntimeEvent] = []
    sink = _sink(seen)
    sink.emit("capture.open", Stage.INGEST,
              details=(Detail("source.sha256", "a" * 64),))
    sink.emit("lane.open", Stage.SCHEDULE,
              details=(Detail("lane.id", "l00"),))
    # Heartbeats and phase announcements are scalar events like any other:
    # they must not disturb the standing envelope.
    sink.emit("session.phase", Stage.SCHEDULE,
              details=(Detail("phase.kind", "rung"),
                       Detail("phase.ppc", "2"),
                       Detail("phase.captures", 2)))
    sink.emit("address.cold_progress", Stage.ADDRESS,
              details=(Detail("address.pages", 312),
                       Detail("address.page_ordinal", 47)))
    context = seen[-1].context
    assert context.source_sha256 == "a" * 64
    assert context.lane_id == "l00"


def test_headless_sink_never_reads_the_clock() -> None:
    """§10.6: without an observer there is not even a clock read."""
    reads: list[int] = []

    def clock() -> float:
        reads.append(1)
        return 0.0

    sink = EventSink(None, clock=clock)
    sink.emit("address.cold_progress", Stage.ADDRESS,
              details=(Detail("address.pages", 312),
                       Detail("address.page_ordinal", 1)))
    sink.emit("session.phase", Stage.SCHEDULE,
              details=(Detail("phase.kind", "tail"),
                       Detail("phase.parked", 3)))
    assert sink.begin_processor_timing() is None
    assert reads == []
    assert sink.failures == ()

"""Per-stage processor-seconds accounting for one instrumented decode.

The profiling doctrine (CLAUDE.md): never profile via generic pytest
runs.  Attach a :class:`TimingObserver` to ONE ``run_receive`` and read
per-stage ``timing.processor_seconds`` from the stage events —
``confetti.py decode --profile-timing`` is the operator entry point.
The runtime's :class:`~holo.receive.observer.EventSink` subtracts
observer time from wall time before emitting, so the processor numbers
stay honest while collection is attached.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..types import RuntimeEvent


_TIMED_EVENTS = frozenset(
    ("stage.complete", "stage.refused", "stage.failed"))


@dataclass(slots=True)
class StageTiming:
    """Accumulated seconds for one (capture, lane, stage) cell."""

    capture_id: str
    lane_id: str
    stage: str
    calls: int = 0
    wall_seconds: float = 0.0
    observer_seconds: float = 0.0
    processor_seconds: float = 0.0


@dataclass(slots=True)
class TimingObserver:
    """Detached observer accumulating per-stage decode timing.

    Insertion order of :attr:`rows` is the causal stage order of the run.
    """

    _rows: dict[tuple[str, str, str], StageTiming] = field(
        default_factory=dict)

    def __call__(self, event: RuntimeEvent) -> None:
        if event.name not in _TIMED_EVENTS:
            return
        details = {row.name: row.value for row in event.details}
        processor = details.get("timing.processor_seconds")
        if processor is None:
            # Headless sinks and clock faults omit timing details.
            return
        key = (
            event.capture_id or "",
            str(details.get("lane.id", "")),
            event.stage.value,
        )
        row = self._rows.get(key)
        if row is None:
            row = StageTiming(*key)
            self._rows[key] = row
        row.calls += 1
        row.wall_seconds += float(details.get("timing.wall_seconds", 0.0))
        row.observer_seconds += float(
            details.get("timing.observer_seconds", 0.0))
        row.processor_seconds += float(processor)

    @property
    def rows(self) -> tuple[StageTiming, ...]:
        return tuple(self._rows.values())

    @property
    def total_processor_seconds(self) -> float:
        return sum(row.processor_seconds for row in self._rows.values())


def render_timing_table(observer: TimingObserver) -> str:
    """Human table for one instrumented decode (stderr, never state)."""
    rows = observer.rows
    if not rows:
        return "timing: no instrumented stage events were observed"
    lines = ["stage timing (processor = wall - observer):"]
    for row in rows:
        capture = row.capture_id[:12] if row.capture_id else "-"
        lines.append(
            f"  {capture:>12} {row.lane_id:<24} {row.stage:<8}"
            f" calls {row.calls:>3}"
            f"  processor {row.processor_seconds:9.3f}s"
            f"  wall {row.wall_seconds:9.3f}s")
    wall = sum(row.wall_seconds for row in rows)
    observer_s = sum(row.observer_seconds for row in rows)
    lines.append(
        f"  TOTAL processor {observer.total_processor_seconds:.3f}s"
        f"  observer {observer_s:.3f}s  wall {wall:.3f}s")
    return "\n".join(lines)


__all__ = ["StageTiming", "TimingObserver", "render_timing_table"]

"""Detached receive observers and visible qualification-status warning."""
from __future__ import annotations

import math
import warnings
from dataclasses import replace
from enum import Enum
from time import perf_counter
from typing import Callable, TypeAlias

from .types import Detail, EventAuthority, EventContext, RuntimeEvent, Stage


Observer: TypeAlias = Callable[[RuntimeEvent], None]
SnapshotFactory: TypeAlias = Callable[[], object]
Clock: TypeAlias = Callable[[], float]
_ProcessorTimingMark: TypeAlias = tuple[float | None, float, int]


class ReceiverQualificationStatus(str, Enum):
    """Evidence status of an installed receiver policy, not its semantics."""

    QUALIFIED = "qualified"
    PROVISIONAL = "provisional"


class ProvisionalReceiverWarning(UserWarning):
    """A run is using historical stand-ins without production qualification."""


class PolicyDetachWarning(UserWarning):
    """A loaded session was continued under a NEWER receiver policy.

    Ruled behaviour, not an anomaly (RECEIVE-DESIGN §9c) — but nobody
    should have to discover it afterwards from a certificate count, so
    the detach announces itself once, on stderr, in the run that does it.
    """


def validate_qualification(
    status: ReceiverQualificationStatus,
    notes: tuple[str, ...],
) -> None:
    if type(status) is not ReceiverQualificationStatus:
        raise TypeError("receiver qualification status must be exact")
    if (type(notes) is not tuple
            or any(not isinstance(note, str) or not note for note in notes)):
        raise TypeError("receiver qualification notes must be non-empty strings")
    if status is ReceiverQualificationStatus.PROVISIONAL and not notes:
        raise ValueError("a provisional receiver must disclose its blockers")
    if status is ReceiverQualificationStatus.QUALIFIED and notes:
        raise ValueError("a qualified receiver cannot carry blocker notes")


def provisional_warning_message(notes: tuple[str, ...]) -> str:
    return (
        "HOLO TRACK-3 RECEIVER IS PROVISIONAL: historical E021-E023c "
        "stand-in constants are active; production qualification is still "
        "required. Outstanding: " + "; ".join(notes)
    )


class EventSink:
    def __init__(
        self,
        observer: Observer | None,
        qualification_status: str | None = None,
        qualification_notes: tuple[str, ...] = (),
        *,
        clock: Clock | None = None,
    ) -> None:
        if clock is not None and not callable(clock):
            raise TypeError("observer clock must be callable")
        self._observer = observer
        self._sequence = 0
        self._failures: list[str] = []
        self._snapshots_failed = False
        self._state_sha256: str | None = None
        self._context = EventContext(
            qualification_status=qualification_status,
            qualification_notes=qualification_notes,
        )
        self._clock = perf_counter if clock is None else clock
        self._observer_timing_depth = 0
        self._observer_timing_started: float | None = None
        self._observer_seconds = 0.0
        self._timing_clock_faults = 0

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(self._failures)

    @property
    def enabled(self) -> bool:
        return self._observer is not None

    @property
    def state_sha256(self) -> str | None:
        return self._state_sha256

    @property
    def snapshots_enabled(self) -> bool:
        """Generic fine-product opt-in for pre-event accumulation."""
        timed = self._observer is not None
        if timed:
            self._begin_observer_work()
        try:
            return self._snapshot_capability(None)
        finally:
            if timed:
                self._end_observer_work()

    def _clock_value(self) -> float | None:
        """Read the optional diagnostics clock without gaining authority."""
        try:
            value = float(self._clock())
        except Exception:
            self._timing_clock_faults += 1
            return None
        if not math.isfinite(value):
            self._timing_clock_faults += 1
            return None
        return value

    def _begin_observer_work(self) -> None:
        """Open one union-of-observer-work interval; nesting is free."""
        if self._observer_timing_depth == 0:
            self._observer_timing_started = self._clock_value()
        self._observer_timing_depth += 1

    def _end_observer_work(self) -> None:
        self._observer_timing_depth -= 1
        if self._observer_timing_depth != 0:
            return
        stopped = self._clock_value()
        started = self._observer_timing_started
        self._observer_timing_started = None
        if started is not None and stopped is not None:
            if stopped < started:
                self._timing_clock_faults += 1
            else:
                self._observer_seconds += stopped - started

    def begin_processor_timing(self) -> _ProcessorTimingMark | None:
        """Start observer-only timing of one numerical stage call.

        A headless sink deliberately avoids even a clock read.  The returned
        marker is detached observer bookkeeping and never enters receiver
        state or a policy identity.
        """
        if self._observer is None:
            return None
        started = self._clock_value()
        return started, self._observer_seconds, self._timing_clock_faults

    def finish_processor_timing(
        self,
        mark: _ProcessorTimingMark | None,
    ) -> tuple[Detail, ...]:
        """Return finite wall/observer/numerical seconds for an event."""
        if mark is None:
            return ()
        started, observer_started, clock_faults = mark
        stopped = self._clock_value()
        if (started is None or stopped is None or stopped < started
                or self._timing_clock_faults != clock_faults):
            return ()
        wall = stopped - started
        observer = self._observer_seconds - observer_started
        if not 0.0 <= observer <= wall:
            return ()
        return (
            Detail("timing.wall_seconds", wall),
            Detail("timing.observer_seconds", observer),
            Detail("timing.processor_seconds", wall - observer),
        )

    def _snapshot_capability(self, event: RuntimeEvent | None) -> bool:
        if self._snapshots_failed:
            return False
        observer = self._observer
        if observer is None:
            return False
        try:
            selector = getattr(observer, "wants_snapshot", None)
            if event is not None and callable(selector):
                return bool(selector(event))
            return bool(getattr(observer, "wants_snapshots", False))
        except Exception as exc:
            failure_event = event or RuntimeEvent(
                self._sequence, "snapshot.capability", Stage.INGEST,
                state_sha256=self._state_sha256, context=self._context)
            self._record_failure(
                failure_event, exc, capability="snapshot-opt-in")
            self._snapshots_failed = True
            return False

    def bind_state(self, state_sha256: str) -> None:
        if (not isinstance(state_sha256, str) or len(state_sha256) != 64
                or any(char not in "0123456789abcdef"
                       for char in state_sha256)):
            raise ValueError("observer state digest must be lowercase SHA-256")
        self._state_sha256 = state_sha256

    def bind_session(
        self,
        format_id: str,
        receiver_policy_id: str,
        page_domain: tuple[int, ...],
    ) -> None:
        self._context = replace(
            self._context,
            format_id=format_id,
            receiver_policy_id=receiver_policy_id,
            page_domain=page_domain,
        )

    def _advance_context(
        self,
        name: str,
        details: tuple[Detail, ...],
    ) -> None:
        values = {row.name: row.value for row in details}
        changes: dict[str, object] = {}
        if name in ("capture.open", "capture.resume"):
            changes.update({
                "source_sha256": None,
                "lane_id": None,
                "parent_lane_id": None,
                "level_ordinal": None,
                "levels_total": None,
                "ppc": None,
                "effective_dpi": None,
                "native_per_view": None,
            })
        source = values.get("source.sha256")
        if isinstance(source, str):
            changes["source_sha256"] = source
        lane = values.get("lane.id")
        if isinstance(lane, str):
            changes["lane_id"] = lane
        if "lane.parent_id" in values:
            parent = values["lane.parent_id"]
            changes["parent_lane_id"] = (
                parent if isinstance(parent, str) else None)
        for detail_name, field_name in (
            ("level.ordinal", "level_ordinal"),
            ("level.total", "levels_total"),
        ):
            value = values.get(detail_name)
            if type(value) is int:
                changes[field_name] = value
        ppc_num = values.get("level.ppc.num", values.get("lane.ppc_num"))
        ppc_den = values.get("level.ppc.den", values.get("lane.ppc_den"))
        if type(ppc_num) is int and type(ppc_den) is int:
            changes["ppc"] = (ppc_num, ppc_den)
        dpi = values.get(
            "level.effective_dpi", values.get("lane.effective_dpi"))
        if isinstance(dpi, (int, float)) and not isinstance(dpi, bool):
            changes["effective_dpi"] = float(dpi)
        npv_num = values.get("lane.native_per_view.num")
        npv_den = values.get("lane.native_per_view.den")
        if type(npv_num) is int and type(npv_den) is int and npv_den:
            changes["native_per_view"] = (npv_num, npv_den)
        if changes:
            self._context = replace(self._context, **changes)

    def _record_failure(
        self,
        event: RuntimeEvent,
        exc: BaseException,
        *,
        capability: str,
    ) -> None:
        try:
            explanation = str(exc)
        except BaseException:
            explanation = "<exception text unavailable>"
        self._failures.append(
            f"event {event.sequence} {event.name}/{event.stage.value} "
            f"{capability}: {type(exc).__name__}: {explanation}")

    def isolate_adapter(
        self,
        name: str,
        stage: Stage,
        capture_id: str | None,
        callback: Callable[[], None],
    ) -> None:
        """Run presentation-only adapter code behind the observer boundary."""
        if self._observer is None:
            return
        self._begin_observer_work()
        try:
            callback()
        except Exception as exc:
            event = RuntimeEvent(
                self._sequence, name, stage, capture_id, "", (),
                EventAuthority.TRANSIENT, self._state_sha256, self._context)
            self._record_failure(event, exc, capability="observer-adapter")
            self._observer = None
        finally:
            self._end_observer_work()

    def emit(self, name: str, stage: Stage, *,
             capture_id: str | None = None, message: str = "",
             details: tuple[Detail, ...] = (),
             authority: EventAuthority = EventAuthority.TRANSIENT,
             snapshot_factory: SnapshotFactory | None = None) -> None:
        timed = self._observer is not None
        if timed:
            self._begin_observer_work()
        try:
            self._advance_context(name, details)
            event = RuntimeEvent(
                self._sequence, name, stage, capture_id, message, details,
                authority, self._state_sha256, self._context)
            self._sequence += 1
            observer = self._observer
            if observer is None:
                return
            if (snapshot_factory is not None
                    and self._snapshot_capability(event)):
                try:
                    event = replace(event, snapshot=snapshot_factory())
                except Exception as exc:
                    # A fine snapshot is an optional observer capability. Keep
                    # the invocation-local scalar stream alive if its builder fails.
                    self._record_failure(
                        event, exc, capability="snapshot-builder")
                    self._snapshots_failed = True
            try:
                observer(event)
            except Exception as exc:
                # Diagnostics are deliberately non-fatal.
                self._record_failure(event, exc, capability="observer")
                self._observer = None
        finally:
            if timed:
                self._end_observer_work()


def event_sink_for_run(
    observer: Observer | None,
    status: ReceiverQualificationStatus,
    notes: tuple[str, ...],
    *,
    format_id: str,
    receiver_policy_id: str,
    page_domain: tuple[int, ...],
) -> EventSink:
    """Warn and create the first detached event before any receiver mutation."""
    validate_qualification(status, notes)
    sink = EventSink(observer, status.value, notes)
    sink.bind_session(format_id, receiver_policy_id, page_domain)
    if status is ReceiverQualificationStatus.PROVISIONAL:
        message = provisional_warning_message(notes)
        warnings.warn(message, ProvisionalReceiverWarning, stacklevel=3)
    return sink


__all__ = [
    "EventSink",
    "Observer",
    "PolicyDetachWarning",
    "ProvisionalReceiverWarning",
    "ReceiverQualificationStatus",
    "SnapshotFactory",
    "event_sink_for_run",
    "provisional_warning_message",
    "validate_qualification",
]

"""Operational receive diagnostics: scalar event log + live view.

- :class:`JsonlDiagnostics` — the invocation-local scalar event log
  (``events.jsonl``), unchanged and always primary.
- :class:`ReceiveDiagnostics` — the CLI observer: the same scalar log plus
  the :mod:`~holo.receive.diag.viewer` live view (one composed frame of four
  A4 panes + six-row status, e023c-style PNG/status.json transport) and a
  compact final ``report.json`` / ``diagnostic-health.json``.

The view is strictly optional: any viewer failure is recorded in
``failures``, drops the view for the rest of the invocation, and leaves the
scalar log and the receiver untouched.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from ..observer import ReceiverQualificationStatus, validate_qualification
from ..types import RuntimeEvent
from .filesystem import atomic_write
from .jsonl import JsonlDiagnostics, _json_bytes
from .viewer import LiveView


class ReceiveDiagnostics(JsonlDiagnostics):
    """Scalar log + live composed-frame view for one receive session."""

    # Generic fine-product opt-in; per-event selection below narrows it to
    # exactly the pass-through snapshots the view consumes.
    wants_snapshots = True

    def __init__(
        self,
        directory: str | Path,
        spec: object,
        *,
        receiver_policy_id: str,
        page_domain: Sequence[int],
        qualification_status: ReceiverQualificationStatus,
        qualification_notes: tuple[str, ...],
        interval_s: float = 3.0,
        panel_width: int = 600,
        port: int | None = None,
        on_server: Callable[[str], None] | None = None,
        route_domains: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(directory)
        validate_qualification(qualification_status, qualification_notes)
        self._spec_id = str(getattr(spec, "spec_id", spec))
        self._policy_id = str(receiver_policy_id)
        self._status = qualification_status
        self._notes = tuple(qualification_notes)
        self._page_domain = tuple(int(page) for page in page_domain)
        self._route_domains = (
            None if route_domains is None else dict(route_domains))
        self._viewer_failures: list[str] = []
        self._viewer: LiveView | None = None
        try:
            self._viewer = LiveView(
                self.directory, spec,
                page_domain=self._page_domain,
                panel_width=panel_width,
                interval_s=interval_s,
                port=port,
                on_server=on_server,
            )
        except Exception as exc:
            self._viewer_failures.append(
                f"viewer unavailable: {type(exc).__name__}: {exc}")
        if self._viewer is not None and self._viewer.server_error:
            self._viewer_failures.append(self._viewer.server_error)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(self._viewer_failures)

    def wants_snapshot(self, event: RuntimeEvent) -> bool:
        viewer = self._viewer
        return viewer is not None and event.name in viewer.SNAPSHOT_EVENTS

    def __call__(self, event: RuntimeEvent) -> None:
        with self._lock:
            self._append(event)
            viewer = self._viewer
            if viewer is None:
                return
            try:
                viewer.feed(event)
            except Exception as exc:
                self._drop_viewer(
                    f"viewer event {event.sequence} {event.name}: "
                    f"{type(exc).__name__}: {exc}")

    def _drop_viewer(self, failure: str) -> None:
        viewer, self._viewer = self._viewer, None
        self._viewer_failures.append(failure)
        if viewer is not None:
            try:
                viewer.close(0.0)
            except Exception:
                pass

    def close(self) -> None:
        viewer = self._viewer
        if viewer is not None:
            try:
                viewer.close()
            except Exception as exc:
                self._viewer_failures.append(
                    f"viewer close: {type(exc).__name__}: {exc}")

    def finalize(self, state: object) -> tuple[Path, ...]:
        """Publish the terminal view and the compact committed summary."""
        written: list[Path] = []
        viewer = self._viewer
        if viewer is not None:
            try:
                written.extend(viewer.finalize(state))
            except Exception as exc:
                self._drop_viewer(
                    f"viewer finalize: {type(exc).__name__}: {exc}")
        identity = self._bind()
        report = {
            "diagnostic_schema": "kiss-viewer-1",
            "format": self._spec_id,
            "receiver_policy_id": self._policy_id,
            "qualification_status": self._status.value,
            "qualification_notes": list(self._notes),
            "page_domain": list(self._page_domain),
            "state": _state_summary(state),
        }
        if self._route_domains is not None:
            # RECEIVE-DESIGN §5.3: the machine-readable report exposes the
            # resolved route domains and per-parity floors.
            report["placement_route_domains"] = self._route_domains
        health = {
            "health_schema": 1,
            "failures": list(self._viewer_failures),
            "capabilities": {
                "event_log": True,
                "report": True,
                "view": self._viewer is not None,
                "server": (self._viewer is not None
                           and self._viewer.serving),
            },
        }
        report_path = self.directory / "report.json"
        health_path = self.directory / "diagnostic-health.json"
        atomic_write(report_path, _json_bytes(report), durable=False,
                     directory_identity=identity)
        atomic_write(health_path, _json_bytes(health), durable=False,
                     directory_identity=identity)
        written.extend((report_path, health_path))
        # Normal finalization waits (bounded) for a connected browser to
        # receive the terminal frame, then releases the loopback server.
        self.close()
        return tuple(written)


def _state_summary(state: object) -> dict[str, object]:
    """Best-effort scalar view of a committed state; never raises."""
    summary: dict[str, object] = {"type": type(state).__name__}
    status = getattr(state, "status", None)
    if status is not None:
        summary["status"] = str(getattr(status, "value", status))
    for name in ("selected_row_id", "decoder_invocations"):
        value = getattr(state, name, None)
        if isinstance(value, (str, int)):
            summary[name] = value
    captures = getattr(state, "captures", None)
    if isinstance(captures, Iterable):
        try:
            summary["captures"] = len(tuple(captures))
        except Exception:
            pass
    return summary


__all__ = ["JsonlDiagnostics", "LiveView", "ReceiveDiagnostics"]

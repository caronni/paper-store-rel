"""W5 measurement observer for the PLANE-FIELDS line (docs/PLANE-FIELDS.md
§6.2): a detached accumulator over the per-plane registration Details, plus
the retained illustration snapshot the diag viewer's field band paints.

THE PRODUCER'S SHAPE -- read off the emission side (``production_color.py::
_plane_field_reporter`` -> ``_production_diagnostics.plane_field_details``
+ ``color_field.PlaneFieldReport.snapshot``), not agreed in advance.  The
W5 build was written against a contract that promised TWO vehicles and the
producer shipped ONE; that mismatch left :meth:`summary` empty on 25 real
field reports (W6 qualification, 2026-08-21) while every synthetic fixture
passed.  Pin contracts from the producer (INDEPENDENT-PLANES §6 P5).

ONE event carries everything, once per field report:

- name ``payload.plane_fields``, stage ``Stage.PAYLOAD``, ``capture_id`` =
  the capture's source sha256;
- Details: ``lane.id`` (prepended by ``LaneContext.progress``),
  ``plane_fields.rms_dots.c`` / ``.m`` / ``.y`` (float, print-dots),
  ``plane_fields.coverage`` (float 0..1), ``plane_fields.adopted`` (str,
  e.g. ``"C,M"`` or ``""``), plus the arm's own cost/supply keys
  (``…regions``, ``…samples``, ``…probes``, ``…solve_seconds``, …) which
  this module ignores;
- snapshot (only while snapshots are enabled) ``{"planes":
  [[plane_index, tile_y, tile_x, dx_dots, dy_dots], ...], "done":
  [[page, tile_y, tile_x], ...], "exaggeration_hint": float}``.

There is NO ``stage.complete`` vehicle: an ordinary payload completion
never carries a ``plane_fields.*`` Detail, so reading one would only ever
match a fixture.  Nothing here imports color_*.py, color_payload.py or
plane_fields.py -- this module consumes RuntimeEvents, synthetic or real.

NAMING NOTE: a ``Detail`` name is validated against ``^[a-z][a-z0-9_.-]*$``
(types.py ``_NAME_RE``) -- uppercase is rejected, so the plane suffix is
lowercase on the wire (``plane_fields.rms_dots.c``) and the producer emits
it that way.  The uppercase C/M/Y spelling is restored only in
human-facing output (:class:`FieldSummaryRow`, the CLI epilogue).

Shape mirrors :class:`~holo.receive.diag.timing.TimingObserver`: a plain
dataclass callable, headless-safe (an event with no plane_fields Details
is a silent no-op), and it never touches receiver state -- dial-off runs
(no plane_fields events at all, the W2 default) leave :meth:`summary`
empty and :meth:`latest_field` ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..types import Detail, RuntimeEvent, Stage

_PLANES = ("C", "M", "Y")
#: The producer's single vehicle (see the module docstring).
FIELD_EVENT = "payload.plane_fields"


@dataclass(slots=True)
class _PlaneAccumulator:
    """Mutable per-(capture, lane) accumulation cell."""

    capture_id: str
    lane_id: str
    calls: int = 0
    last_rms: dict[str, float] = field(default_factory=dict)
    peak_rms: dict[str, float] = field(default_factory=dict)
    coverage: float | None = None
    adopted_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class FieldSummaryRow:
    """Read-only snapshot of one (capture, lane) cell's plane-field stats."""

    capture_id: str
    lane_id: str
    calls: int
    rms_dots: dict[str, float]
    peak_dots: dict[str, float]
    coverage: float | None
    adopted_counts: dict[str, int]


@dataclass(slots=True)
class FieldStats:
    """Detached observer accumulating plane-field Details per (capture,
    lane), and retaining the LAST ``payload.plane_fields`` illustration
    snapshot for pane consumers.

    Two independent products off ONE event (the producer's shape, see the
    module docstring): :meth:`summary` (the scalar Details -- what the CLI
    epilogue prints) and :meth:`latest_field` (the illustration snapshot --
    what the diag viewer's field band paints).  Neither depends on the
    other arriving: snapshots are enabled independently of the scalar log,
    and a jsonl replay carries Details with no snapshot at all.
    """

    _rows: dict[tuple[str, str], _PlaneAccumulator] = field(
        default_factory=dict)
    _latest_field: dict[str, object] | None = field(
        default=None, repr=False)

    def __call__(self, event: RuntimeEvent) -> None:
        if event.name != FIELD_EVENT:
            return
        snapshot = event.snapshot
        if isinstance(snapshot, dict) and "planes" in snapshot:
            self._latest_field = snapshot
        details = {row.name: row.value for row in event.details}
        rms = {
            plane: details[f"plane_fields.rms_dots.{plane.lower()}"]
            for plane in _PLANES
            if f"plane_fields.rms_dots.{plane.lower()}" in details
        }
        coverage = details.get("plane_fields.coverage")
        adopted = details.get("plane_fields.adopted")
        if not rms and coverage is None and adopted is None:
            # A field event carrying none of the three scalar keys (a
            # snapshot-only fixture, or a producer that reported nothing
            # measurable): TimingObserver's "ignore it" rule, ported --
            # the snapshot above is retained either way.
            return
        key = (event.capture_id or "", str(details.get("lane.id", "")))
        row = self._rows.get(key)
        if row is None:
            row = _PlaneAccumulator(*key)
            self._rows[key] = row
        row.calls += 1
        for plane, value in rms.items():
            value = float(value)
            row.last_rms[plane] = value
            row.peak_rms[plane] = max(row.peak_rms.get(plane, value), value)
        if coverage is not None:
            row.coverage = float(coverage)
        if adopted is not None:
            adopted = str(adopted)
            row.adopted_counts[adopted] = row.adopted_counts.get(
                adopted, 0) + 1

    def summary(self) -> tuple[FieldSummaryRow, ...]:
        """Per-(capture, lane) rows, in first-seen order."""
        return tuple(
            FieldSummaryRow(
                capture_id=row.capture_id,
                lane_id=row.lane_id,
                calls=row.calls,
                rms_dots=dict(row.last_rms),
                peak_dots=dict(row.peak_rms),
                coverage=row.coverage,
                adopted_counts=dict(row.adopted_counts),
            )
            for row in self._rows.values()
        )

    def latest_field(self) -> Mapping[str, object] | None:
        """The most recent ``payload.plane_fields`` snapshot, if any."""
        return self._latest_field


def replay_jsonl_row(row: Mapping[str, object]) -> RuntimeEvent:
    """Reconstruct a minimal :class:`RuntimeEvent` from one decoded
    ``events.jsonl`` line (``JsonlDiagnostics``/``RuntimeEvent.to_dict``).

    The scalar log never carries a snapshot (:mod:`.jsonl` records
    ``to_dict()`` only), so a replayed ``payload.plane_fields`` event
    always has ``snapshot=None`` -- exactly what :meth:`FieldStats.summary`
    needs, since it is built from that event's Details alone.  This is the
    CLI epilogue's data path (see
    ``cli.py::cmd_decode``): read the already-written, already-flushed
    diagnostic log back instead of composing a second live observer
    alongside :class:`~holo.receive.diag.ReceiveDiagnostics`.
    """
    stage = Stage(row["stage"])
    details = tuple(
        Detail(name, value)
        for name, value in dict(row.get("details") or {}).items())
    capture_id = row.get("capture_id")
    return RuntimeEvent(
        int(row["sequence"]), str(row["name"]), stage,
        capture_id=capture_id if isinstance(capture_id, str) else None,
        message=str(row.get("message", "") or ""),
        details=details,
    )


__all__ = [
    "FIELD_EVENT",
    "FieldStats",
    "FieldSummaryRow",
    "replay_jsonl_row",
]

"""Phase-0 payload-bucket decomposition harness (PAYLOAD-REWORK-PLAN 0.3).

Standalone instrument, never pytest-collected (profiling doctrine: a small
instrumented single-decode harness, not a pytest run):

    cd <worktree> && PYTHONPATH=src <python> tests/holo/_bench_payload_decomp.py

Runs ONE receive over the SYNTHETIC roundtrip corpus that _bench_phased
builds (one full-field capture plus two re-placed scraps, single page,
c3-r0550) with a synchronous observer, and decomposes the wall-clock spent
inside every payload stage into buckets bounded by the EXISTING payload.*
milestones.  No src/ changes and no new event details: where the stream has
no boundary (per-attempt durations), the bucket is declared inferred, never
faked.  Prints exactly one JSON document to stdout.

Accounting model: the receive is single-threaded, so the wall interval
between two consecutive observed events belongs entirely to the code that
ran between them; every interval is attributed to the lane and bucket of the
event that CLOSES it.  Buckets are therefore exact wherever a milestone pair
brackets one activity, and inferred where several activities share one
interval (see the "accounting" block embedded in the JSON output).
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench_phased as bench_phased

roundtrip = bench_phased.roundtrip

from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput, RuntimeEvent, Stage


_ATTEMPT_EVENTS = frozenset(("payload.attempt", "payload.retry_attempt"))
_SAMPLING_EVENTS = frozenset((
    "payload.region_emitted",     # K per-region emission (gen 0 + refined)
    "payload.region",             # color per-region emission
    "context.region_complete",    # per-region context-fit decision
    "pose_refine.window_progress",  # certified pose refinement summaries
    "address.final",              # refined-address adoption marker
))
_STAGE_BOUNDARY_EVENTS = frozenset(
    ("stage.complete", "stage.refused", "stage.failed"))

_ACCOUNTING = {
    "milestone_bounded_exact": [
        "stage_open_s: previous lane event -> stage.open (runtime pre-stage"
        " bookkeeping before the payload processor is entered)",
        "plan_setup_s: stage.open -> payload.plan (terminal patch/region"
        " pruning + stage setup inside the payload processor)",
        "sampling_calibration_ctx_s: payload.plan -> last region/context/"
        "refine event (gen-0 sampling + calibration + context fits, pose"
        " refinement, refined re-collection)",
        "ownership_freeze_s: last region event -> payload.owner_frozen"
        " (owner competition + certified-owner prune; on refinement-"
        "INELIGIBLE lanes refine_address_once emits no events, so its"
        " eligibility pass also lands here)",
        "block_build_s: -> payload.blocks_built (color lanes only; the K"
        " path has no blocks_built milestone)",
        "retry_frontier_open_s: last ordinary attempt -> payload.retry_open"
        " (retry150 frontier construction)",
        "retry_close_s: last retry attempt -> payload.retry_complete",
        "divergence_audit_finalize_s: payload.retry_complete ->"
        " payload.complete (certificate divergence audit + artifact build)",
        "stage_finalize_s: payload.complete -> stage.complete (runtime"
        " product validation + barrier handoff emit)",
    ],
    "inferred_residual": [
        "block_build_first_attempt_s: payload.owner_frozen (or"
        " payload.blocks_built) -> first attempt event; K block build,"
        " frontier merge, store restore, engine open AND the first"
        " attempt's own BP+CRC are inseparable here — the stream has no"
        " per-attempt duration detail and none was added (Phase-2/3"
        " option)",
        "attempts_scan_s / attempts_union_s / attempts_retry150_s:"
        " inter-attempt event deltas = per-attempt BP+CRC plus per-attempt"
        " engine overhead; each engine run's first attempt is excluded"
        " (it lands in block_build_first_attempt_s); the first attempt"
        " after payload.retry_open additionally carries retry-engine"
        " restart",
        "other_payload_s: payload-stage events with no assigned bucket",
    ],
    "cross_checks": [
        "stage_processor_s (from stage.complete timing details) excludes"
        " observer time; bucket sums include the observer's own per-event"
        " cost, so bucket_sum_minus_stage_wall_s > 0 by roughly the"
        " inter-stage runtime overhead captured in plan_setup_s +"
        " stage_finalize_s",
        "outside_payload_s: wall attributed to all non-payload stages"
        " (ingest/survey/address/schedule/close), exact by the same"
        " event-delta rule",
    ],
}


@dataclass(slots=True)
class _LaneRow:
    capture: str
    lane: str
    lane_class: str
    bucket_seconds: dict[str, float] = field(
        default_factory=lambda: defaultdict(float))
    counts: dict[str, int] = field(
        default_factory=lambda: defaultdict(int))
    stage_wall_s: float | None = None
    stage_processor_s: float | None = None


class _Decomposer:
    """Synchronous observer bucketing wall between payload milestones."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._t_prev: float | None = None
        self._prev_name: str = ""
        self.rows: dict[tuple[str, str], _LaneRow] = {}
        self.outside_payload_s: float = 0.0
        self.events_observed: int = 0

    def observe(self, event: RuntimeEvent) -> None:
        now = self._clock()
        delta_s = 0.0 if self._t_prev is None else now - self._t_prev
        self._t_prev = now
        self.events_observed += 1
        name = event.name
        prev_name = self._prev_name
        self._prev_name = name
        if event.stage is not Stage.PAYLOAD:
            self.outside_payload_s += delta_s
            return
        details = {row.name: row.value for row in event.details}
        lane_id = str(details.get("lane.id")
                      or event.context.lane_id or "?")
        capture_id = (event.capture_id or "?")[:8]
        row = self._lane_row(capture_id, lane_id)
        row.bucket_seconds[self._bucket_for(name, prev_name, details)] \
            += delta_s
        self._count(row, name, details)

    def _lane_row(self, capture_id: str, lane_id: str) -> _LaneRow:
        key = (capture_id, lane_id)
        row = self.rows.get(key)
        if row is None:
            lane_class = "mopup" if lane_id.startswith("m") else "base"
            row = _LaneRow(capture_id, lane_id, lane_class)
            self.rows[key] = row
        return row

    @staticmethod
    def _bucket_for(name: str, prev_name: str,
                    details: dict[str, object]) -> str:
        if name == "stage.open":
            return "stage_open_s"
        if name == "payload.plan":
            return "plan_setup_s"
        if name in _SAMPLING_EVENTS:
            return "sampling_calibration_ctx_s"
        if name == "payload.owner_frozen":
            return "ownership_freeze_s"
        if name == "payload.blocks_built":
            return "block_build_s"
        if name in _ATTEMPT_EVENTS:
            if (prev_name in _ATTEMPT_EVENTS
                    or prev_name == "payload.retry_open"):
                stage_label = str(
                    details.get("payload.attempt_stage", "unknown"))
                return f"attempts_{stage_label}_s"
            return "block_build_first_attempt_s"
        if name == "payload.retry_open":
            return "retry_frontier_open_s"
        if name == "payload.retry_complete":
            return "retry_close_s"
        if name == "payload.complete":
            return "divergence_audit_finalize_s"
        if name in _STAGE_BOUNDARY_EVENTS:
            return "stage_finalize_s"
        return "other_payload_s"

    def _count(self, row: _LaneRow, name: str,
               details: dict[str, object]) -> None:
        counts = row.counts
        counts[f"events.{name}"] += 1
        if name in ("payload.region_emitted", "payload.region"):
            counts["regions_emitted"] += 1
            for detail_name, count_name in (
                ("payload.windows", "windows_emitted"),
                ("payload.windows_accepted", "windows_accepted"),
            ):
                value = details.get(detail_name)
                if type(value) is int:
                    counts[count_name] += value
        elif name == "context.region_complete":
            counts["context_fits"] += 1
            if details.get("context.adopted"):
                counts["context_fits_adopted"] += 1
        elif name == "pose_refine.window_progress":
            counts["refine_windows"] += 1
        elif name in _ATTEMPT_EVENTS:
            stage_label = str(details.get("payload.attempt_stage", "unknown"))
            counts[f"attempts.{stage_label}"] += 1
            if details.get("payload.decoder_invoked"):
                counts[f"bp_crc_calls.{stage_label}"] += 1
            if details.get("payload.crc_ok"):
                counts[f"crc_ok.{stage_label}"] += 1
            if details.get("payload.certificate_is_new"):
                counts[f"certificates_new.{stage_label}"] += 1
        elif name == "payload.retry_open":
            tiles = details.get("payload.retry_tiles")
            if type(tiles) is int:
                counts["retry_tiles"] += tiles
        elif name == "payload.plan":
            for detail_name in ("payload.placements",
                                "payload.needed_patches",
                                "payload.pruned_terminal_patches",
                                "payload.pruned_terminal_regions"):
                value = details.get(detail_name)
                if type(value) is int:
                    counts[detail_name.replace("payload.", "plan.")] += value
        elif name == "payload.owner_frozen":
            for detail_name in ("payload.sampled_owner_cells",
                                "payload.needed_owner_cells",
                                "payload.pruned_certified_owner_cells",
                                "payload.windows"):
                value = details.get(detail_name)
                if type(value) is int:
                    counts[detail_name.replace("payload.", "owner.")] += value
        elif name in _STAGE_BOUNDARY_EVENTS:
            wall = details.get("timing.wall_seconds")
            processor = details.get("timing.processor_seconds")
            if isinstance(wall, (int, float)) and not isinstance(wall, bool):
                row.stage_wall_s = float(wall)
            if (isinstance(processor, (int, float))
                    and not isinstance(processor, bool)):
                row.stage_processor_s = float(processor)
            if name != "stage.complete":
                counts["stage_not_complete"] += 1


def _round_map(values: dict[str, float]) -> dict[str, float]:
    return {name: round(seconds, 4)
            for name, seconds in sorted(values.items())}


def _lane_report(row: _LaneRow) -> dict[str, object]:
    payload_total_s = sum(row.bucket_seconds.values())
    report: dict[str, object] = {
        "capture": row.capture,
        "lane": row.lane,
        "lane_class": row.lane_class,
        "payload_total_s": round(payload_total_s, 4),
        "bucket_seconds": _round_map(row.bucket_seconds),
        "counts": dict(sorted(row.counts.items())),
    }
    if row.stage_wall_s is not None:
        report["stage_wall_s"] = round(row.stage_wall_s, 4)
        report["bucket_sum_minus_stage_wall_s"] = round(
            payload_total_s - row.stage_wall_s, 4)
    if row.stage_processor_s is not None:
        report["stage_processor_s"] = round(row.stage_processor_s, 4)
    return report


def _totals(decomposer: _Decomposer, wall_s: float) -> dict[str, object]:
    bucket_totals: dict[str, float] = defaultdict(float)
    class_totals: dict[str, dict[str, float]] = {}
    count_totals: dict[str, int] = defaultdict(int)
    for row in decomposer.rows.values():
        class_row = class_totals.setdefault(
            row.lane_class, defaultdict(float))
        for bucket, seconds in row.bucket_seconds.items():
            bucket_totals[bucket] += seconds
            class_row[bucket] += seconds
        for count_name, value in row.counts.items():
            if not count_name.startswith("events."):
                count_totals[count_name] += value
    payload_total_s = sum(bucket_totals.values())
    return {
        "wall_s": round(wall_s, 4),
        "payload_total_s": round(payload_total_s, 4),
        "outside_payload_s": round(decomposer.outside_payload_s, 4),
        "payload_bucket_seconds": _round_map(bucket_totals),
        "payload_seconds_by_lane_class": {
            lane_class: _round_map(buckets)
            for lane_class, buckets in sorted(class_totals.items())},
        "counts": dict(sorted(count_totals.items())),
        "events_observed": decomposer.events_observed,
    }


def main() -> None:
    fixture = roundtrip._build_fixture()
    full = np.array(fixture.raster, copy=True)
    full.setflags(write=False)
    captures = (
        CaptureInput(full, roundtrip._DPI),
        CaptureInput(bench_phased._scrap(fixture, 32, 32, 128),
                     roundtrip._DPI),
        CaptureInput(bench_phased._scrap(fixture, 96, 96, 128),
                     roundtrip._DPI),
    )
    decomposer = _Decomposer()
    with TemporaryDirectory() as scratch:
        request = ReceiveRequest(
            fixture.spec, captures,
            state_path=Path(scratch) / "decomp.json",
            page_hypotheses=(0,),
            # v0.42: the full phased drive (M + R levels) is flag-gated.
            run_refine=True)
        start = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            result = run_receive(
                request, pipeline=production_pipeline(request),
                observer=decomposer.observe)
        wall_s = time.perf_counter() - start
    print(json.dumps({
        "corpus": ("synthetic _bench_phased corpus: roundtrip fixture "
                   "full-field capture + two re-placed scraps, "
                   "single page, c3-r0550"),
        "verified": result.verified,
        "certificates": len(result.state.certificates),
        "close_status": result.state.close.status.value,
        "lanes": [_lane_report(row) for row in decomposer.rows.values()],
        "totals": _totals(decomposer, wall_s),
        "accounting": _ACCOUNTING,
    }, indent=1))


if __name__ == "__main__":
    main()

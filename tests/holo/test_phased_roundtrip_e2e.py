"""The ONE bounded phased-native end-to-end roundtrip (Phase 7.3).

Replacement for the retired 4-case pathological production battery
(PAYLOAD-REWORK-PLAN 7.2, lens-coverage:10 — its unique pins never ran at
>20-min walls).  Same guard value, bounded runtime: one multi-capture
phased-native session on the shared 7x7 c3 roundtrip fixture —

* two captures: the full field plus a re-placed, 90-degree-rotated
  128-cell scrap (blind non-native orientation must be recovered);
* the full plan — ladder, M-level mop-up tail, AND the v0.42 R-levels —
  via the ``--complete --refine`` leg, with the mandatory max60 ->
  retry150 boundary event on every attempting payload lane;
* a resume-mid-session leg (stop after the first committed barrier, then
  resume to a verified close);
* a ``--complete --refine`` (deferred fountain close, full drive) leg:
  every level of every capture commits, exactly one close check,
  byte-exact payload;
* a WALL BUDGET tripwire (~3x measured, the kiss timing-tripwire
  precedent): a breach means a mechanism regression, never noise.

Slow lane: HOLO_RUN_SLOW_TESTS=1.
"""
from __future__ import annotations

import os
import time
import warnings
from pathlib import Path

import numpy as np
import pytest

import _roundtrip_fixture as roundtrip
from holo.receive.cascade import scale_plan
from holo.receive.observer import ProvisionalReceiverWarning, event_sink_for_run
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, _execute_receive, run_receive
from holo.receive.session import CaptureStatus, SessionStatus, load_session
from holo.receive.types import CaptureInput, RuntimeEvent


pytestmark = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the bounded phased e2e roundtrip",
)

# Wall-budget tripwire, NOT profiling (the doctrine instrument stays
# `confetti.py decode --profile-timing`).  Measured 2026-08-02 on the
# reference machine: ~61 s for the whole test body (both legs).  ~3x:
_WALL_BUDGET_S = 180.0


def _scrap(fixture, y0_cells: int, x0_cells: int, span_cells: int):
    """One re-placed scrap on a fresh paper canvas (parking material)."""
    spec = fixture.spec
    px = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * px) // 2
    y0 = int(origin_px[0] + y0_cells * px)
    x0 = int(origin_px[1] + x0_cells * px)
    span = span_cells * px
    piece = np.array(fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 4 * 64 * px // 8
    canvas = np.full((span + 2 * margin, span + 2 * margin),
                     float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    # Re-placed AND re-oriented: the receiver gets no orientation hint.
    rotated = np.ascontiguousarray(np.rot90(canvas, 1))
    rotated.setflags(write=False)
    return rotated


def _assert_mandatory_retry_events(events: tuple[RuntimeEvent, ...]) -> None:
    """Every observed payload lane exposes its max60 -> retry150 boundary."""
    payload_events = tuple(
        event for event in events if event.name == "payload.complete")
    retry_events = tuple(
        event for event in events if event.name == "payload.retry_complete")
    assert payload_events, "no payload lane completed"
    assert len(retry_events) == len(payload_events), (
        "production payload lanes did not each publish retry completion")
    for payload_event in payload_events:
        key = (payload_event.capture_id, payload_event.context.lane_id)
        retries = tuple(
            event for event in retry_events
            if (event.capture_id, event.context.lane_id) == key)
        barriers = tuple(
            event for event in events
            if event.name == "barrier.committed"
            and (event.capture_id, event.context.lane_id) == key
            and event.sequence > payload_event.sequence)
        assert (len(retries) == 1 and len(barriers) == 1
                and retries[0].sequence < payload_event.sequence
                < barriers[0].sequence), (
            f"retry150 boundary is misplaced for {key}")
        details = {row.name: row.value for row in retries[0].details}
        assert {
            "payload.max60_attempts",
            "payload.max60_certificates",
            "payload.retry150_frontier",
            "payload.retry150_eligible",
            "payload.retry150_attempts",
            "payload.retry150_noop",
        }.issubset(details)


def test_phased_multicapture_roundtrip_bounded(tmp_path: Path) -> None:
    started = time.perf_counter()
    fixture = roundtrip._build_fixture()
    spec = fixture.spec
    plan = scale_plan(roundtrip._DPI, spec.cell_dots)
    full = np.array(fixture.raster, copy=True)
    full.setflags(write=False)
    captures = (
        CaptureInput(full, roundtrip._DPI),
        CaptureInput(_scrap(fixture, 32, 32, 128), roundtrip._DPI),
    )

    # ---- Leg 1: interrupt after the first committed barrier, resume. ----
    state_path = tmp_path / "resume.json"
    request = ReceiveRequest(
        spec, captures, state_path, page_hypotheses=(0,))
    pipeline = production_pipeline(request)
    committed = [0]

    def stop_after_first() -> bool:
        return committed[0] >= 1

    def count_barriers(event) -> None:
        if event.name == "barrier.committed":
            committed[0] += 1

    events_sink = event_sink_for_run(
        count_barriers,
        pipeline.qualification_status,
        pipeline.qualification_notes,
        format_id=spec.spec_id,
        receiver_policy_id=pipeline.policy_id,
        page_domain=(0,),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        interrupted = _execute_receive(
            request, pipeline, events_sink,
            stop_requested=stop_after_first)
    assert interrupted.state.status is SessionStatus.OPEN
    assert committed[0] == 1
    retained = load_session(state_path, format_row_id=spec.spec_id)
    assert sum(len(row.levels) for row in retained.captures) == 1

    resume_events: list[RuntimeEvent] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        resumed = run_receive(
            request, pipeline=production_pipeline(request),
            observer=resume_events.append)
    assert resumed.verified
    assert resumed.payload == fixture.payload
    assert resumed.state.status is SessionStatus.VERIFIED
    # The committed level was not re-run: the resumed invocation's barrier
    # count excludes it.
    resumed_barriers = sum(
        1 for event in resume_events if event.name == "barrier.committed")
    assert resumed_barriers >= 1
    total_levels = sum(len(row.levels) for row in resumed.state.captures)
    assert total_levels == 1 + resumed_barriers
    _assert_mandatory_retry_events(tuple(resume_events))
    # Certificates certify the whole page exactly once, zero divergences.
    assert len(resumed.state.certificates) == spec.tiles_per_page

    # ---- Leg 2: --complete --refine (deferred close): the FULL plan —
    # ladder, M-level tail, and R-levels — on both captures, one final
    # close, byte-exact payload.  v0.42: --complete alone no longer drives
    # the lane families (it only defers the close to the invocation's
    # flag-bounded end); --refine extends the drive through everything,
    # including pending M-levels, by the plan-prefix law. ----------------
    complete_path = tmp_path / "complete.json"
    complete_request = ReceiveRequest(
        spec, captures, complete_path, page_hypotheses=(0,),
        defer_fountain_close=True, run_refine=True)
    complete_events: list[RuntimeEvent] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        complete = run_receive(
            complete_request,
            pipeline=production_pipeline(complete_request),
            observer=complete_events.append)
    assert complete.verified and complete.payload == fixture.payload
    assert len(complete.state.captures) == len(captures)
    assert all(
        row.status is CaptureStatus.COMPLETE
        and len(row.levels) == len(plan)
        for row in complete.state.captures)
    close_checks = sum(
        1 for event in complete_events if event.name == "close.check")
    assert close_checks == 1
    # Rung-major phasing is observable: the session phase indicator runs.
    assert any(
        event.name == "session.phase" for event in complete_events)
    # The rotated scrap retained a blind non-native pose.
    scrap_sha = complete.state.captures[-1].source_sha256
    scrap_rotations = {
        row.rot90 for row in complete.state.poses
        if row.capture_id == scrap_sha}
    assert scrap_rotations and scrap_rotations != {0}
    _assert_mandatory_retry_events(tuple(complete_events))
    assert load_session(complete_path).status is SessionStatus.VERIFIED

    wall = time.perf_counter() - started
    assert wall < _WALL_BUDGET_S, (
        f"phased e2e wall {wall:.1f}s breached its {_WALL_BUDGET_S:.0f}s "
        "tripwire (~3x measured): a mechanism regression, not noise")

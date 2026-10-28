"""v0.33 phased-session-schedule contracts (docs/PHASED-SCHEDULE.md).

Dedicated pins for the amendment's new machinery: durable parking with
retirement, extension-only block supersession, the count-gated close
schedule, and the rung-major drive's event/interleave law on the real
production pipeline.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from holo.receive.evidence_blocks import (
    EvidenceOrigin,
    block_from_rows,
    validate_block_supersession,
)
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.session import load_session
from holo.receive.session_model import CaptureStatus
from holo.receive.types import CaptureInput

import _roundtrip_fixture as roundtrip


@pytest.fixture(scope="module")
def fixture():
    return roundtrip._build_fixture()


def _scrap_canvas(fixture, y0_cells: int, x0_cells: int, span_cells: int):
    spec = fixture.spec
    px_per_cell = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * px_per_cell) // 2
    y0 = int(origin_px[0] + y0_cells * px_per_cell)
    x0 = int(origin_px[1] + x0_cells * px_per_cell)
    span = span_cells * px_per_cell
    piece = np.array(fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 4 * 64 * px_per_cell // 8
    canvas = np.full(
        (span + 2 * margin, span + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)
    return canvas


def _run(request, *, stop_requested=None, observer=None):
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        if stop_requested is None and observer is None:
            return run_receive(
                request, pipeline=production_pipeline(request))
        from holo.receive.runtime import _execute_receive
        from holo.receive.observer import event_sink_for_run
        pipeline = production_pipeline(request)
        events = event_sink_for_run(
            observer,
            pipeline.qualification_status,
            pipeline.qualification_notes,
            format_id=request.spec.spec_id,
            receiver_policy_id=pipeline.policy_id,
            page_domain=(tuple(range(request.spec.max_pages))
                         if request.page_hypotheses is None
                         else request.page_hypotheses),
        )
        return _execute_receive(
            request, pipeline, events, stop_requested=stop_requested)


def test_parked_windows_persist_across_interrupt_and_retire(
    fixture, tmp_path,
) -> None:
    """D6: parked rows survive an interrupted phase 1 durably, load
    cleanly, and the resumed session's mop-up levels retire them."""
    spec = fixture.spec
    canvas = _scrap_canvas(fixture, 32, 32, 128)
    path = tmp_path / "parked.json"
    # v0.42: the full plan (ladder + M + R levels) needs --refine, which
    # covers pending M-levels by the plan-prefix law.
    request = ReceiveRequest(
        spec, (CaptureInput(canvas, roundtrip._DPI),),
        state_path=path, page_hypotheses=(0,), run_refine=True)

    barriers = [0]

    def stop_after_first_barrier() -> bool:
        return barriers[0] >= 1

    def count_barriers(event) -> None:
        if event.name == "barrier.committed":
            barriers[0] += 1

    interrupted = _run(
        request, stop_requested=stop_after_first_barrier,
        observer=count_barriers)
    record = interrupted.state.captures[0]
    assert record.status is CaptureStatus.ACTIVE
    assert len(record.levels) == 1
    assert interrupted.state.parked, "the scrap corpus must park at l00"
    parked_ids = {row.parked_id for row in interrupted.state.parked}

    loaded = load_session(path, format_row_id=spec.spec_id)
    assert {row.parked_id for row in loaded.parked} == parked_ids

    resumed = _run(request)
    assert not resumed.state.parked, "mop-up levels must retire parked rows"
    resumed_record = resumed.state.captures[0]
    assert resumed_record.status is CaptureStatus.COMPLETE

    # The interrupted+resumed session certifies exactly what one straight
    # run certifies (deterministic pipeline, same corpus).
    straight = _run(ReceiveRequest(
        spec, (CaptureInput(canvas, roundtrip._DPI),),
        state_path=tmp_path / "straight.json", page_hypotheses=(0,),
        run_refine=True))
    assert (
        {row.work_key for row in resumed.state.certificates}
        == {row.work_key for row in straight.state.certificates})


def _block(cells: dict[int, float], *, sha: str = "ab" * 32,
           lane: str = "l00-2ppc-1200dpi"):
    origin = EvidenceOrigin("placement-1", 7, 0.25, ())
    return block_from_rows(
        sha, lane, 0, (0, 0),
        tuple((flat, np.asarray([value], np.float32), origin)
              for flat, value in sorted(cells.items())),
        kind="k")


def test_block_supersession_is_extension_only() -> None:
    """D5: a mop-up block replaces a live one only as a strict-superset
    extension agreeing exactly on every committed cell."""
    base = _block({3: 1.5, 9: -2.0})
    extended = _block({3: 1.5, 9: -2.0, 40: 0.75})
    validate_block_supersession(base, extended)

    with pytest.raises(ValueError, match="extend"):
        validate_block_supersession(base, base)
    with pytest.raises(ValueError, match="observe every committed cell"):
        validate_block_supersession(
            base, _block({3: 1.5, 40: 0.75, 41: 0.5}))
    with pytest.raises(ValueError, match="revises committed evidence"):
        validate_block_supersession(
            base, _block({3: 1.5, 9: -2.5, 40: 0.75}))
    with pytest.raises(ValueError, match="keep the evidence key"):
        validate_block_supersession(
            base, _block({3: 1.5, 9: -2.0, 40: 0.75}, lane="l01-x"))


def test_close_gate_never_consults_a_provably_open_frontier(
    fixture, tmp_path, monkeypatch,
) -> None:
    """D8: a scrap far below metadata trust and block counts commits many
    barriers but never pays a fountain solve; the run still reports its
    NOT-RECOVERED state gracefully.  (The positive direction — verifying
    sessions still verify under the gate — is carried by every green
    verifying test in the suite.)"""
    import holo.receive.production_close as production_close
    import holo.receive.production_payload as production_payload

    calls = [0]
    real = production_close.close_volume

    def counting(*args, **kwargs):
        calls[0] += 1
        return real(*args, **kwargs)

    # Both fountain consult sites: the close gate and the K advisory
    # preclose (one module pre-v0.38, split homes since).
    monkeypatch.setattr(production_close, "close_volume", counting)
    monkeypatch.setattr(production_payload, "close_volume", counting)
    spec = fixture.spec
    canvas = _scrap_canvas(fixture, 32, 32, 128)
    request = ReceiveRequest(
        spec, (CaptureInput(canvas, roundtrip._DPI),),
        state_path=tmp_path / "gate.json", page_hypotheses=(0,),
        run_refine=True)
    result = _run(request)
    assert result.state.captures[0].status is CaptureStatus.COMPLETE
    assert len(result.state.captures[0].levels) >= 2
    assert result.state.certificates, "corpus must certify tiles"
    assert calls[0] == 0, (
        "the count gate must skip every provably-open consult")
    assert result.state.status.value == "open"
    # Phase-2 crash regression (production-drivers:01): the gated skip's
    # progress factory consumes CONVERTED certificates, so with real
    # durable records retained it materializes a count-only projection
    # instead of raising AttributeError.
    progress = result.close_progress()
    assert progress is not None and progress.count_only
    assert progress.metadata is not None


def test_deferred_close_snapshots_publish_count_only_progress(
    fixture, tmp_path,
) -> None:
    """--complete on a count-short scrap with snapshots enabled: every
    deferred barrier close snapshot and the one final gated consult build
    from CONVERTED certificates (Phase-2 crash repair) and carry the
    count-only marking, so the fountain row and the CLI epilogue render
    reach, never a fake rank (fountain-close:05 / lens-doc-v33:03)."""
    from holo.receive.diag.rows import close_row

    spec = fixture.spec
    canvas = _scrap_canvas(fixture, 32, 32, 128)
    seen = []

    class _Observer:
        wants_snapshots = True  # every event; the assertions filter by name

        def __call__(self, event) -> None:
            seen.append(event)

    request = ReceiveRequest(
        spec, (CaptureInput(canvas, roundtrip._DPI),),
        state_path=tmp_path / "deferred.json", page_hypotheses=(0,),
        defer_fountain_close=True)
    result = _run(request, observer=_Observer())
    assert result.state.certificates, "corpus must certify tiles"
    assert result.observer_failures == (), (
        "no snapshot builder may fail (the pre-Phase-2 AttributeError "
        "refused every later pane snapshot)")

    barrier_close = [
        event.snapshot["close"] for event in seen
        if event.name == "barrier.committed" and event.snapshot is not None]
    final_close = [
        event.snapshot for event in seen
        if event.name == "close.check" and event.snapshot is not None]
    assert barrier_close and final_close
    for snapshot in (*barrier_close, *final_close):
        assert snapshot["deferred_counts"] is True
        progress = snapshot["progress"]
        assert progress.count_only is True
        row = close_row(snapshot)
        assert "rank/solve deferred" in row
        # The ranked branch's "rank R/N · blocks S/B" never renders
        # (metadata rank 0/24 is honest — the metadata solve IS exact).
        assert " · blocks " not in row
    # The deferred final consult was count-gated (count-short frontier):
    # correct — it provably cannot verify — and the published progress is
    # the count-only shape, reaching the CLI factory.
    progress = result.close_progress()
    assert progress is not None and progress.count_only


def test_mopup_window_snapshots_build_from_real_geometry(
    fixture, tmp_path,
) -> None:
    """M-level address.window_progress snapshots build from the re-derived
    synthetic survey (mopup_survey: parked-row pitch, base-region origins)
    under an observer granting EVERY snapshot.  Pins the None-transient
    AttributeError whose one poisoned builder refused every later pane
    snapshot for the whole run (--diag went blind at the first M window)."""
    spec = fixture.spec
    canvas = _scrap_canvas(fixture, 32, 32, 128)
    seen = []

    class _Observer:
        wants_snapshots = True  # every event: no per-event filter

        def __call__(self, event) -> None:
            seen.append(event)

    request = ReceiveRequest(
        spec, (CaptureInput(canvas, roundtrip._DPI),),
        state_path=tmp_path / "mopup-diag.json", page_hypotheses=(0,),
        run_mopup=True)
    result = _run(request, observer=_Observer())
    assert result.observer_failures == (), (
        "no snapshot builder may raise (one poisoned builder silences "
        "every later pane snapshot)")

    def lane_of(event) -> str:
        return str({row.name: row.value for row in event.details}["lane.id"])

    mopup_windows = [
        event for event in seen
        if event.name == "address.window_progress"
        and lane_of(event).startswith("m")]
    assert mopup_windows, "the scrap corpus must drive M-level windows"
    for event in mopup_windows:
        snapshot = event.snapshot
        assert snapshot is not None
        assert float(snapshot["pitch_px"]) > 0
        assert snapshot["region_origin_yx"] is not None


def test_rung_major_interleave_and_phase_events(fixture, tmp_path) -> None:
    """D1/D14: two captures advance breadth-first (both l00 barriers
    before any l01), with ascending rung phase events and capture.resume
    context switches."""
    spec = fixture.spec
    captures = (
        CaptureInput(_scrap_canvas(fixture, 32, 32, 128), roundtrip._DPI),
        CaptureInput(_scrap_canvas(fixture, 96, 96, 128), roundtrip._DPI),
    )
    # v0.42: the tail phase needs --mopup (default invocations stop
    # before the first M entry and emit no tail phase).
    request = ReceiveRequest(
        spec, captures,
        state_path=tmp_path / "interleave.json", page_hypotheses=(0,),
        run_mopup=True)
    names: list[tuple[str, object]] = []

    def observe(event) -> None:
        detail = {row.name: row.value for row in event.details}
        if event.name == "session.phase":
            names.append(("phase", detail.get("phase.kind"),
                          detail.get("phase.ppc")))
        elif event.name == "barrier.committed":
            names.append(("barrier", detail.get("lane.id")))
        elif event.name == "capture.resume":
            names.append(("resume",))

    _run(request, observer=observe)
    phases = [row for row in names if row[0] == "phase"]
    assert [row[1] for row in phases[:-1]].count("rung") == len(phases) - 1
    assert phases[-1][1] == "tail"
    assert any(row == ("resume",) for row in names)
    barrier_lanes = [row[1] for row in names if row[0] == "barrier"]
    first_l01 = next(
        (index for index, lane in enumerate(barrier_lanes)
         if lane.startswith("l01")), len(barrier_lanes))
    l00_positions = [
        index for index, lane in enumerate(barrier_lanes)
        if lane.startswith("l00")]
    assert len(l00_positions) == 2
    assert all(index < first_l01 for index in l00_positions)


def test_plan_shape_flag_bounds_and_scheduler_identity() -> None:
    """v0.42 pins: [L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln)] plan shape, the
    flag-bounded prefix law, LaneSpec's one-of-three family invariant, and
    the hand-bumped scheduler identity."""
    from holo.receive.cascade import PhasedSessionScheduler, scale_plan
    from holo.receive.runtime import _plan_bound
    from holo.receive.types import LaneSpec

    plan = scale_plan(1200.0, 3)
    ladder = [row for row in plan
              if row.mopup_of is None and row.refine_of is None]
    n = len(ladder)
    assert n >= 2 and len(plan) == 3 * n
    assert [row.mopup_of for row in plan[n:2 * n]] == [
        row.lane_id for row in ladder]
    assert [row.refine_of for row in plan[2 * n:]] == [
        row.lane_id for row in ladder]
    for refine, base in zip(plan[2 * n:], ladder, strict=True):
        # R(Lk) binds to Lk's exact transform but owns its OWN evidence
        # namespace; the raster binding is the base lane's.
        assert (refine.native_per_view_num, refine.native_per_view_den) == (
            base.native_per_view_num, base.native_per_view_den)
        assert refine.evidence_lane_id == refine.lane_id
        assert refine.base_lane_id == base.lane_id
    # Parent chain stays linear across the whole plan.
    assert [row.parent_lane_id for row in plan[1:]] == [
        row.lane_id for row in plan[:-1]]

    assert _plan_bound(plan, run_mopup=False, run_refine=False) == n
    assert _plan_bound(plan, run_mopup=True, run_refine=False) == 2 * n
    # --refine extends through everything, INCLUDING pending M-levels
    # (the plan-prefix law).
    assert _plan_bound(plan, run_mopup=False, run_refine=True) == 3 * n

    with pytest.raises(ValueError, match="exactly one"):
        LaneSpec("x", 1, 1, 1, 1, mopup_of="a", refine_of="b")
    with pytest.raises(ValueError, match="cannot serve itself"):
        LaneSpec("x", 1, 1, 1, 1, refine_of="x")

    assert (PhasedSessionScheduler.policy_id
            == "holo/phased-session/rung-major-v5-u-lanes-codingaware-field")


def test_flag_bounded_driver_parks_lane_families(tmp_path) -> None:
    """v0.42: default stops before the first M entry, --mopup before the
    first R entry, --refine runs everything; committed prefixes are
    honored and a resume with different flags continues monotonically.
    CaptureStatus stays ACTIVE (a legal end state) until the full plan —
    including R-levels — is committed."""
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.cascade import scale_plan
    from holo.receive.runtime import ReceiveRequest, run_receive
    from holo.receive.session import CaptureStatus

    image = tmp_path / "flags.png"
    fixtures._write_image(image, 42_000)
    spec = fixtures._spec()
    plan = scale_plan(1200.0, spec.cell_dots)
    n = len(plan) // 3
    path = tmp_path / "flags.json"

    def drive(**flags):
        pipeline, _calls = fixtures._pipeline()
        return run_receive(
            ReceiveRequest(
                spec, (fixtures._capture(image),), path, **flags),
            pipeline=pipeline)

    default = drive()
    record = default.state.captures[0]
    assert record.status is CaptureStatus.ACTIVE
    assert len(record.levels) == n

    mopup = drive(run_mopup=True)
    record = mopup.state.captures[0]
    assert record.status is CaptureStatus.ACTIVE
    assert len(record.levels) == 2 * n
    assert mopup.captures[0].barriers_committed == n

    refine = drive(run_refine=True)
    record = refine.state.captures[0]
    assert record.status is CaptureStatus.COMPLETE
    assert len(record.levels) == 3 * n
    assert refine.captures[0].barriers_committed == n
    # The R-levels committed empty artifacts (stage-A shape).
    for level in record.levels[2 * n:]:
        assert level.survey is not None and level.survey.region_ids == ()
        assert level.address is not None and level.address.pose_ids == ()
        assert level.payload is not None
        assert level.payload.certificate_ids == ()


def _pose_row_from_placed(placed_patch):
    """Mint the D7 PoseRecord field surface production persists."""
    from types import SimpleNamespace

    fitted = placed_patch.segment.segment
    return SimpleNamespace(
        patch_id=placed_patch.patch_id,
        page=placed_patch.candidate.page,
        cell_origin_yx=placed_patch.segment.page_origin_yx,
        rot90=placed_patch.segment.rot_k,
        window_id=fitted.window.window_id,
        window_origin_yx_px=fitted.window.origin_yx_px,
        window_shape_yx_cells=fitted.window.shape_yx_cells,
        window_depth=fitted.window.depth,
        lane_pose_origin_yx=fitted.pose.origin_yx,
        lane_pose_jacobian=tuple(
            float(v) for v in np.asarray(
                fitted.pose.jacobian_yx, np.float64).ravel()),
        lane_pose_phase_yx=fitted.pose.phase_yx,
        lane_pose_pitch_px=fitted.pose.pitch_px,
        lane_pose_angle_deg=fitted.pose.angle_deg,
        segment_support_cells=fitted.support_cells,
        segment_phase_contrast=fitted.phase_contrast,
        segment_pitch_yx_px=fitted.pitch_yx_px,
        segment_orthogonality_error_deg=fitted.orthogonality_error_deg,
    )


def test_label_reconstruction_is_bit_exact(fixture) -> None:
    """D7: a base-accepted window reconstructed from its durable pose
    carrier reproduces the identical pose, audited cell set, and page
    footprint — the complete determinants of payload sampling."""
    from holo.receive.place import _core, _label_patch
    from holo.receive.placement.defaults import (
        PROVISIONAL_V1_PLACEMENT_POLICY,
    )
    from holo.receive.placement.geometry import (
        platen_backing,
        prepare_region,
    )
    from holo.receive.placement.model import PlacementConfig
    from holo.receive.placement.reference import V1ReferenceField
    from holo.receive.placement.search import ScoreMemo
    from holo.receive.place import place_survey
    from holo.receive.scan import open_capture
    from holo.receive.survey import (
        PayloadSurvey,
        SupportMask,
        SurveyDiagnostics,
        SurveyRegion,
    )

    spec = fixture.spec
    canvas = _scrap_canvas(fixture, 32, 32, 128)
    raster = open_capture(canvas, roundtrip._DPI)
    ppc = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    margin = 4 * 64 * ppc // 8
    span = 128 * ppc
    support = SupportMask(
        (margin, margin), span, np.ones((1, 1), bool), (span, span))
    px_per_mm = raster.dpi / 25.4
    survey = PayloadSurvey(
        regions=(SurveyRegion(
            support, support.area_px / (px_per_mm * px_per_mm), 1.0),),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )
    config = PlacementConfig()
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, (0,), 0, config)
    result = place_survey(
        raster, survey, spec, pages=(0,), budgets=budgets,
        word_budget=word)
    accepted = [row for row in result.placements if not row.redundant]
    assert accepted
    original = accepted[0]

    context = prepare_region(
        raster, survey.regions[0], 0, float(survey.cell_pitch_px),
        config=config, backing=platen_backing(raster))
    assert context is not None
    provider = V1ReferenceField(spec)
    memo = ScoreMemo(provider)
    label = _label_patch(
        _pose_row_from_placed(original), 0, context, memo, provider,
        budgets.local, config, sample_key=0)
    assert label is not None
    assert label.route == "label" and label.redundant
    assert not label.observations
    lhs, rhs = label.segment, original.segment
    assert lhs.segment.pose == rhs.segment.pose
    assert np.array_equal(lhs.audited_cells_yx, rhs.audited_cells_yx)
    assert np.array_equal(label.page_cells_yx, original.page_cells_yx)
    assert (label.candidate.page, label.candidate.origin_yx,
            label.candidate.rot_k) == (
        original.candidate.page, original.candidate.origin_yx,
        original.candidate.rot_k)


def test_split_region_fit_equals_pooled_oracle(fixture) -> None:
    """D7: fitting a region's context over (mop-up rows + label rows)
    reproduces the single-pass pooled fit exactly, and the profiled
    mop-up rows carry the oracle's own LLR nodes."""
    from holo.receive._payload_context import apply_region_context
    from holo.receive._payload_sampling import sample_and_calibrate
    from holo.receive.payload_model import EvidenceSource
    from holo.receive.placement.defaults import (
        PROVISIONAL_V1_PLACEMENT_POLICY,
    )
    from holo.receive.placement.model import PlacementConfig
    from holo.receive.place import place_survey
    from holo.receive.scan import open_capture
    from holo.receive.survey import (
        PayloadSurvey,
        SupportMask,
        SurveyDiagnostics,
        SurveyRegion,
    )

    spec = fixture.spec
    # A 128x288-cell scrap spans two 200/40 windows (the frontier
    # fragment's geometry), so the region fit pools multiple rows.
    ppc = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * ppc) // 2
    y0 = int(origin_px[0] + 32 * ppc)
    x0 = int(origin_px[1] + 32 * ppc)
    piece = np.array(
        fixture.raster[y0:y0 + 128 * ppc, x0:x0 + 288 * ppc], copy=True)
    margin = 16 * ppc
    canvas = np.full(
        (128 * ppc + 2 * margin, 288 * ppc + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + 128 * ppc, margin:margin + 288 * ppc] = piece
    canvas.setflags(write=False)
    raster = open_capture(canvas, roundtrip._DPI)
    support = SupportMask(
        (margin, margin), 288 * ppc, np.ones((1, 1), bool),
        (128 * ppc, 288 * ppc))
    px_per_mm = raster.dpi / 25.4
    survey = PayloadSurvey(
        regions=(SurveyRegion(
            support, support.area_px / (px_per_mm * px_per_mm), 1.0),),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, (0,), 0, PlacementConfig())
    address = place_survey(
        raster, survey, spec, pages=(0,), budgets=budgets,
        word_budget=word)
    source = EvidenceSource("cd" * 32, "l00-oracle")
    rows = sample_and_calibrate(raster, source, address, spec)
    assert len(rows) >= 2

    oracle_rows, oracle_decisions = apply_region_context(rows)
    half = len(rows) // 2
    base, mop = rows[:half], rows[half:]
    split_rows, split_decisions = apply_region_context(mop, base)

    assert len(oracle_decisions) == len(split_decisions) == 1
    lhs, rhs = split_decisions[0], oracle_decisions[0]
    assert lhs.eligible == rhs.eligible and lhs.adopted == rhs.adopted
    assert lhs.reason == rhs.reason
    assert np.array_equal(lhs.offsets, rhs.offsets)
    assert np.array_equal(
        lhs.search_support_by_bin, rhs.search_support_by_bin)
    assert np.array_equal(
        lhs.validation_support_by_bin, rhs.validation_support_by_bin)
    assert (lhs.n_search, lhs.n_validation) == (
        rhs.n_search, rhs.n_validation)
    oracle_by_id = {row.placement_id: row for row in oracle_rows}
    assert {row.placement_id for row in split_rows} == {
        row.placement_id for row in mop}
    for row in split_rows:
        twin = oracle_by_id[row.placement_id]
        assert np.array_equal(row.printed_llr, twin.printed_llr)
        assert row.detector_profile == twin.detector_profile


def test_winner_flip_rate_separates_misplaced_mopup_window(fixture) -> None:
    """The D5 drop tally's positive control (2026-08-02 ruling,
    docs/CANARY-D5-DISAGREEMENTS.md): overlapping windows at CORRECT
    poses drop many re-observations but flip (almost) no winners, while
    the SAME window with a wrong pose — shifted several cells, the
    misplaced-mop-up-window failure class the canary exists for — flips
    an order of magnitude more.  Dropped counts are pose-independent
    (the claimed page cells do not move)."""
    import dataclasses

    from holo.receive._payload_sampling import sample_and_calibrate
    from holo.receive.evidence_blocks import (
        apply_mopup_supersession,
        blocks_from_frontier,
    )
    from holo.receive.payload import freeze_capture_evidence
    from holo.receive.payload_model import EvidenceSource
    from holo.receive.placement.defaults import (
        PROVISIONAL_V1_PLACEMENT_POLICY,
    )
    from holo.receive.placement.model import (
        AddressResult,
        PlacementConfig,
    )
    from holo.receive.place import place_survey
    from holo.receive.scan import open_capture
    from holo.receive.survey import (
        PayloadSurvey,
        SupportMask,
        SurveyDiagnostics,
        SurveyRegion,
    )

    spec = fixture.spec
    ppc = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * ppc) // 2
    y0 = int(origin_px[0] + 32 * ppc)
    x0 = int(origin_px[1] + 32 * ppc)
    piece = np.array(
        fixture.raster[y0:y0 + 128 * ppc, x0:x0 + 288 * ppc], copy=True)
    margin = 16 * ppc
    canvas = np.full(
        (128 * ppc + 2 * margin, 288 * ppc + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + 128 * ppc, margin:margin + 288 * ppc] = piece
    canvas.setflags(write=False)
    raster = open_capture(canvas, roundtrip._DPI)
    support = SupportMask(
        (margin, margin), 288 * ppc, np.ones((1, 1), bool),
        (128 * ppc, 288 * ppc))
    px_per_mm = raster.dpi / 25.4
    survey = PayloadSurvey(
        regions=(SurveyRegion(
            support, support.area_px / (px_per_mm * px_per_mm), 1.0),),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, (0,), 0, PlacementConfig())
    address = place_survey(
        raster, survey, spec, pages=(0,), budgets=budgets,
        word_budget=word)
    placements = sorted(
        address.payload_placements, key=lambda row: int(row.patch_id))
    assert len(placements) >= 2
    committed_window, fresh_window = placements[0], placements[1]
    source = EvidenceSource("cd" * 32, "l00-flip-canary")

    def blocks_for(patch):
        rows = sample_and_calibrate(
            raster, source,
            AddressResult((patch,), (), (), address.region_states, 0),
            spec)
        return blocks_from_frontier(
            freeze_capture_evidence(source, spec, rows))

    committed_blocks = blocks_for(committed_window)

    def drop_tally(patch):
        _blocks, drops = apply_mopup_supersession(
            blocks_for(patch), committed_blocks)
        return drops

    correct = drop_tally(fresh_window)
    assert correct.dropped > 1000, "arms must overlap substantially"

    placed = fresh_window.segment
    pose_segment = placed.segment
    shifted = dataclasses.replace(
        fresh_window,
        segment=dataclasses.replace(
            placed,
            segment=dataclasses.replace(
                pose_segment,
                pose=dataclasses.replace(
                    pose_segment.pose,
                    origin_yx=(
                        pose_segment.pose.origin_yx[0] + 8 * ppc,
                        pose_segment.pose.origin_yx[1],
                    )))))
    misplaced = drop_tally(shifted)

    # The claimed page cells did not move: identical collision sets.
    assert misplaced.dropped == correct.dropped
    correct_rate = correct.winner_flips / correct.dropped
    misplaced_rate = misplaced.winner_flips / misplaced.dropped
    assert correct_rate <= 0.02, correct_rate
    assert misplaced_rate >= 0.25, misplaced_rate

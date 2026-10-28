"""The plan-prefix rule: an archived plan may be a PREFIX of today's.

A capture recorded before a lane family joined ``cascade.scale_plan``
carries a plan that is a strict prefix of the plan the same format row
schedules today — the PLANE-FIELDS ``u0x-field`` arm is the case that
forced the repair, exactly as the ``off``/``a3``/``a4b`` arms would have.
The phased schedule already treats a capture's completed lanes as a
prefix (its phase cursor IS ``len(levels)``, derived and never stored),
so such a state is a capture with work still owed, not a corrupt record.

These pins fix the whole rule: a prefix loads and resumes into exactly
the appended lanes, a plan that differs INSIDE the prefix is refused with
the offending lane named, a plan LONGER than today's is refused, and an
exact plan is left byte-identical.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import _qualify_runtime_fixtures as fixtures
from holo.format.profiles import Family
from holo.receive._runtime_validation import (
    adopt_current_scale_plans,
    policy_scale_plan,
    scale_plan_tail,
    validate_state_for_spec,
)
from holo.receive.cascade import scale_plan
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.session import (
    CaptureStatus,
    authoritative_bytes,
    load_session,
    save_session,
)
from holo.receive.types import LaneSpec

DPI = 1200.0


def _ladder_state(tmp_path: Path, name: str):
    """One default-bounded run: the ordinary ladder is committed, no more."""
    image = tmp_path / f"{name}.png"
    fixtures._write_image(image, 24_000)
    path = tmp_path / f"{name}.json"
    pipeline, _calls = fixtures._pipeline()
    run_receive(
        ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    return image, path


def _truncate_plan_to_committed_levels(path: Path) -> tuple[int, int]:
    """Rewrite the state as an ARCHIVED one: plan == committed prefix."""
    spec = fixtures._spec()
    state = load_session(path, format_row_id=spec.spec_id)
    capture = state.captures[0]
    archived = replace(capture, plan=capture.plan[:len(capture.levels)])
    assert archived.status is CaptureStatus.COMPLETE
    save_session(path, replace(state, captures=(archived,)), validate=False)
    return len(archived.plan), len(capture.plan)


def test_a_prefix_plan_loads_and_resumes_into_exactly_the_appended_lanes(
    tmp_path,
) -> None:
    image, path = _ladder_state(tmp_path, "prefix")
    stored_lanes, _full = _truncate_plan_to_committed_levels(path)
    spec = fixtures._spec()
    today = scale_plan(DPI, spec.cell_dots)
    appended = tuple(row.lane_id for row in today[stored_lanes:])
    assert appended  # the fixture ladder is a strict prefix of the plan

    # (a) the archived state loads and validates against today's format.
    state = load_session(path, format_row_id=spec.spec_id)
    validate_state_for_spec(state, spec)
    assert len(state.captures[0].plan) == stored_lanes
    assert state.captures[0].status is CaptureStatus.COMPLETE

    # (b) the runtime adopts today's plan, so the capture owes the tail.
    adopted = adopt_current_scale_plans(state, spec)
    assert adopted.captures[0].plan == today
    assert adopted.captures[0].levels == state.captures[0].levels
    assert adopted.captures[0].status is CaptureStatus.ACTIVE

    # (c) the tail stays flag-gated, and an unflagged resume leaves the
    # archived record byte-identical on disk: adoption is in-memory, and
    # only a barrier writes.
    archived_bytes = path.read_bytes()
    unflagged, unflagged_calls = fixtures._pipeline()
    quiet = run_receive(
        ReceiveRequest(spec, (fixtures._capture(image),), path),
        pipeline=unflagged)
    assert tuple(tuple(rows) for rows in unflagged_calls) == ((), (), ())
    assert not quiet.state_changed
    assert path.read_bytes() == archived_bytes

    # (d) under --refine the resume schedules exactly the appended lanes.
    resumed, calls = fixtures._pipeline()
    result = run_receive(
        ReceiveRequest(
            spec, (fixtures._capture(image),), path, run_refine=True),
        pipeline=resumed)
    for stage_calls in calls:
        assert tuple(row.split("|")[-1] for row in stage_calls) == appended
    assert result.captures[0].barriers_committed == len(appended)
    assert result.state.captures[0].plan == today
    assert len(result.state.captures[0].levels) == len(today)
    assert result.state.captures[0].status is CaptureStatus.COMPLETE

    # (e) the retained prefix was never re-run, and the reloaded state is
    # the adopted one: a second resume has nothing left to do.
    again, again_calls = fixtures._pipeline()
    repeat = run_receive(
        ReceiveRequest(
            spec, (fixtures._capture(image),), path, run_refine=True),
        pipeline=again)
    assert tuple(tuple(rows) for rows in again_calls) == ((), (), ())
    assert not repeat.state_changed


def test_a_plan_that_differs_inside_the_prefix_is_refused_by_lane(
    tmp_path,
) -> None:
    image, path = _ladder_state(tmp_path, "moved-ladder")
    spec = fixtures._spec()
    state = load_session(path, format_row_id=spec.spec_id)
    capture = state.captures[0]
    moved = replace(
        capture.plan[1], target_ppc_num=capture.plan[1].target_ppc_num + 1)
    forked = replace(
        capture, plan=(capture.plan[0], moved) + capture.plan[2:])
    corrupted = replace(state, captures=(forked,))
    save_session(path, corrupted, validate=False)

    expected = f"at lane 1: lane {moved.lane_id!r} geometry differs"
    with pytest.raises(ValueError, match=expected):
        validate_state_for_spec(corrupted, spec)
    with pytest.raises(ValueError, match=expected):
        adopt_current_scale_plans(corrupted, spec)
    # The refusal is the RESUME's, not a bookkeeping detail: the run
    # stops before the first lane executes.
    pipeline, calls = fixtures._pipeline()
    with pytest.raises(ValueError, match=expected):
        run_receive(
            ReceiveRequest(
                spec, (fixtures._capture(image),), path, run_refine=True),
            pipeline=pipeline)
    assert tuple(tuple(rows) for rows in calls) == ((), (), ())

    # A renamed lane names both sides instead of the geometry.
    renamed = replace(capture.plan[1], lane_id="l01-elsewhere")
    with pytest.raises(ValueError, match="stored 'l01-elsewhere', policy"):
        scale_plan_tail(
            (capture.plan[0], renamed), policy_scale_plan(DPI, spec))


def test_a_plan_longer_than_todays_policy_is_refused(tmp_path) -> None:
    image, path = _ladder_state(tmp_path, "retired-lane")
    spec = fixtures._spec()
    state = load_session(path, format_row_id=spec.spec_id)
    capture = state.captures[0]
    # A lane RETIRED from the ladder under a live state: the record keeps
    # an ordinary entry today's plan no longer has.
    ghost = LaneSpec(
        lane_id="l99-retired",
        target_ppc_num=capture.plan[-1].target_ppc_num,
        target_ppc_den=capture.plan[-1].target_ppc_den,
        native_per_view_num=capture.plan[-1].native_per_view_num,
        native_per_view_den=capture.plan[-1].native_per_view_den,
        parent_lane_id=capture.plan[-1].lane_id)
    longer = replace(capture, plan=capture.plan + (ghost,))
    corrupted = replace(state, captures=(longer,))
    save_session(path, corrupted, validate=False)

    expected = "longer than format policy: stored lane 'l99-retired'"
    with pytest.raises(ValueError, match=expected):
        validate_state_for_spec(corrupted, spec)
    with pytest.raises(ValueError, match=expected):
        adopt_current_scale_plans(corrupted, spec)
    pipeline, calls = fixtures._pipeline()
    with pytest.raises(ValueError, match=expected):
        run_receive(
            ReceiveRequest(
                spec, (fixtures._capture(image),), path, run_refine=True),
            pipeline=pipeline)
    assert tuple(tuple(rows) for rows in calls) == ((), (), ())


def test_an_exact_plan_keeps_todays_behaviour_byte_for_byte(
    tmp_path,
) -> None:
    _image, path = _ladder_state(tmp_path, "exact")
    spec = fixtures._spec()
    state = load_session(path, format_row_id=spec.spec_id)
    assert state.captures[0].plan == scale_plan(DPI, spec.cell_dots)

    before = authoritative_bytes(state)
    adopted = adopt_current_scale_plans(state, spec)
    assert adopted is state
    assert authoritative_bytes(adopted) == before


def test_the_archive_case_is_the_supplemental_tail_of_a_colour_plan() -> None:
    """The exact shape the repair exists for (e030/PK-FINAL/sheet I)."""
    cmy8 = scale_plan(4800.0, 3, codec_family=Family.CMY8, n_streams=3)
    cmy7 = scale_plan(4800.0, 3, codec_family=Family.CMY7, n_streams=1)
    for plan in (cmy8, cmy7):
        # PK-FINAL states: everything but the PLANE-FIELDS field arm.
        assert plan[-1].arm_override == "field"
        assert scale_plan_tail(plan[:-1], plan) == plan[-1:]
        # Pre-campaign states: no supplemental lane at all.
        ordinary = tuple(row for row in plan if row.uplift_of is None)
        assert scale_plan_tail(ordinary, plan) == plan[len(ordinary):]
        assert all(row.uplift_of is not None
                   for row in scale_plan_tail(ordinary, plan))
        assert scale_plan_tail(plan, plan) == ()
    # K plans never grew a tail, so every K state stays exact — and the
    # colour tail is APPENDED to the identical ladder, which is why the
    # rule can be a plain prefix test.  (Family is bound by the state's
    # own ``format_row_id``, never inferred from the plan: the K plan IS
    # the colour plan's ordinary prefix.)
    k_plan = scale_plan(4800.0, 3)
    assert scale_plan_tail(k_plan, k_plan) == ()
    assert cmy8[:len(k_plan)] == k_plan


def test_lane_spec_equality_covers_every_persisted_field() -> None:
    """The rule compares whole LaneSpecs, not lane ids."""
    lane = scale_plan(DPI, fixtures._spec().cell_dots)[0]
    for field, value in (
        ("target_ppc_num", lane.target_ppc_num + 1),
        ("native_per_view_num", lane.native_per_view_num + 1),
    ):
        assert replace(lane, **{field: value}) != lane
    assert isinstance(lane, LaneSpec)

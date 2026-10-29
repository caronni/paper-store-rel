"""``tiles.swim`` — the per-plane local-affine rescue, pinned.

Three things this file exists to hold still.  THE UNITS: the search
converts dots to cells before it touches the pose, through the same
`lib/page_map` every reader goes through, so the displacement it
recovers is the displacement the head will apply — the
test below injects a known two-dot shift into a synthetic plane and
demands it back.  THE LABELS: every cell in the objective is proven by
the format or by a certificate, and the target tile's own cargo is
never one, which is the whole difference between this row and the
non-oracle loop INDEPENDENT-PLANES section 2.12 measured diverging.
THE NO-OP: a plane the search refuses is read at exactly the offsets
the standing lane would have used, by construction rather than by
convention.
"""

from __future__ import annotations

import dataclasses
import math
from fractions import Fraction

import numpy as np
import pytest
from scipy import ndimage

from holo.receiver import data, engine
from holo.receiver.format import identity
from holo.receiver.lib import evidence, geometry, local_affine
from holo.receiver.lib import page_map
from holo.receiver.lib import plane_field
from holo.receiver.plugins import color_model, color_region, field_tiers
from holo.receiver.plugins import fields_collect, local_ctx
from holo.receiver.plugins import swim, tiles, uplift
from holo.receiver.tests import _h3_facts, _h3_fixture_geometry

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
CAPTURE_ID = _h3_facts.CAPTURE_ID
PPC = Fraction(4)
PAGE = 0
SPAN_CELLS = 2 * geometry.TILE_CELLS
WID = (CAPTURE_ID, 0, 0, (0, 0, SPAN_CELLS, SPAN_CELLS))

ROW = identity.resolve_format_ref(COLOR_FORMAT_REF)
GEOMETRY = _h3_fixture_geometry.memoised_site_geometry(ROW)
CELL_DOTS = 3
#: the printer's scale, which is how design §2.4's two lengths in
#: millimetres reach the solve (`plugins/fields.DOTS_PER_MM`)
DOTS_PER_MM = identity.HW_DPI / identity.MM_PER_INCH
PITCH_PX = 6.0
INJECTED_DOTS = 2.0
BLUR_PX = 1.5
#: the renderer rolls the displaced plane by whole PIXELS, so this is
#: the finest shift this stimulus can express and every injection below
#: is a multiple of it
RENDER_STEP_DOTS = CELL_DOTS / PITCH_PX
#: the licence sweep's three points: the ordinary injection, the swim's
#: own translation bound, and a third past it (2 x bound / 1.5)
BOUND_DOTS = swim.translation_bound_dots(ROW)
REACH_INJECTION_DOTS = 2.0 * BOUND_DOTS / 1.5
INJECTIONS_DOTS = (INJECTED_DOTS, BOUND_DOTS, REACH_INJECTION_DOTS)
#: What the standing field must still be carrying inside its own reach.
#: RE-DERIVED 2026-09-08 at the gain fix (the lead's W8 landing ruling):
#: **0.973** measured where the W8 build measured 0.89, because the
#: smoothing length is now solved from the 100 mm gain bar rather than
#: copied from the retired kernel's bandwidth, and a window's worth of
#: measured tiles on a page nobody else has measured is an ISLAND — the
#: W8 review's M1, whose shrinkage is governed by that same length
#: against the island's extent.  The bar sits below the measurement and
#: well above the half the search would have to carry back, so a prior
#: that gave a tenth of a small island away fails here instead of
#: quietly costing the swim its head start.
FIELD_SHARE_INSIDE_REACH: float = 0.9
#: the rotated-placement pin's point, RE-DERIVED 2026-09-08 at the W8
#: integration: the ordinary injection, because it is the largest of
#: this stimulus's shifts that the page field's own tiers still measure
#: (2.24 dots is where they stop) and therefore the only one that
#: exercises the frame round trip's DOWN leg — the hint through
#: `page_map.local_axes`.  It used to be twice the swim's bound, where
#: W7's parity-half furniture template aliased onto a nearer peak and
#: published 1.124 dots of four; the whole-site template W8 ships
#: refuses that, so at four dots the hint is exactly zero and the down
#: conversion is never exercised.  Measured on this stimulus, all four
#: rotations identical to 1e-4.
#: RE-PINNED 2026-09-08 at the gain fix: 1.783 -> **1.946** of the two
#: dots injected, the island shrinkage the shorter smoothing length no
#: longer takes (0.89 -> 0.97).  The search's own contribution went with
#: it — 0.187 dots before, exactly 0.000 now, because what the hint
#: leaves behind (0.054 dots) is under the search's finest step — so the
#: UP leg is no longer exercised here and is pinned, at all four
#: rotations and unconditionally, by
#: `test_a_refused_plane_carries_the_hint_and_nothing_else`.
FIELD_AT_INJECTION = 1.946
SWUM_AT_INJECTION = 1.946

ARMING_MATRIX = (
    (tiles.STAGE_SCAN, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_UNION, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_RETRY150, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_LOCAL150, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_SWIM150, tiles.OUTCOME_FAILED, False),
    (tiles.STAGE_SCAN, tiles.OUTCOME_CERTIFIED, False),
    (tiles.STAGE_SCAN, tiles.OUTCOME_BELOW_FLOOR, False),
)


# --- the pure search ----------------------------------------------------


def test_unit_coordinates_span_the_window_and_are_x_then_y():
    cells = np.asarray([[0, 0], [199, 199], [0, 199], [199, 0]], np.int64)
    unit = local_affine.unit_coordinates(cells, (200, 200))
    assert unit.shape == (4, 2)
    assert np.allclose(unit[0], (-1.0, -1.0))
    assert np.allclose(unit[1], (1.0, 1.0))
    # third cell is y=0, x=199 -> (x, y) = (+1, -1)
    assert np.allclose(unit[2], (1.0, -1.0))
    assert np.allclose(unit[3], (-1.0, 1.0))


def test_the_linear_terms_read_as_dots_at_the_window_edge():
    affine = local_affine.Affine(
        translation=np.zeros(2, np.float64),
        linear=np.asarray(((0.0, 0.7), (0.0, 0.0)), np.float64))
    unit = local_affine.unit_coordinates(
        np.asarray([[0, 0], [199, 0]], np.int64), (200, 200))
    offsets = affine.offsets_dots_xy(unit)
    assert np.allclose(offsets[:, 0], (-0.7, 0.7)), (
        "an entry of the linear term IS the dots it adds at the window "
        "edge; anything else makes the bound unreadable")


def test_the_step_ladder_halves_from_the_bound_to_the_resolution():
    ladder = local_affine.step_ladder(3.0, 0.125)
    assert ladder == (1.5, 0.75, 0.375, 0.1875)
    assert ladder[0] == 3.0 / local_affine.COARSE_STEPS_PER_SIDE
    assert ladder[-1] >= 0.125 > ladder[-1] * 0.5
    for coarse, fine in zip(ladder, ladder[1:]):
        assert fine == coarse * 0.5


def test_a_resolution_coarser_than_the_bound_still_searches_once():
    assert local_affine.step_ladder(3.0, 99.0) == (1.5,)
    assert local_affine.step_ladder(0.0, 0.1) == ()


def test_the_state_groups_are_the_sorted_partition_of_the_labels():
    states = np.asarray([3, 0, 3, 7, 0, 0], np.int64)
    groups = local_affine.state_groups(states)
    assert groups.n_cells == 6 and groups.n_states == 3
    assert list(states[groups.order]) == [0, 0, 0, 3, 3, 7]
    assert list(groups.boundaries) == [0, 3, 5]
    assert list(groups.counts) == [3.0, 2.0, 1.0]
    empty = local_affine.state_groups(np.zeros(0, np.int64))
    assert empty.n_cells == 0 and empty.n_states == 0


def test_eta_is_one_on_a_level_reading_and_zero_on_a_flat_one():
    states = np.asarray([0, 0, 1, 1, 2, 2], np.int64)
    groups = local_affine.state_groups(states)
    exact = np.asarray([[1.0, 1.0, 4.0, 4.0, 9.0, 9.0]])
    flat = np.full((1, 6), 3.0)
    noise = np.asarray([[1.0, 9.0, 1.0, 9.0, 1.0, 9.0]])
    assert local_affine.correlation_ratios(groups, exact)[0] == \
        pytest.approx(1.0)
    assert local_affine.correlation_ratios(groups, flat)[0] == 0.0
    assert local_affine.correlation_ratios(groups, noise)[0] == 0.0, (
        "identical readings in every group: the states explain nothing")


def test_the_levels_are_refitted_per_candidate_not_frozen_at_the_start():
    """The objective must not be scored against its own starting read."""
    states = np.asarray([0, 0, 1, 1], np.int64)
    groups = local_affine.state_groups(states)
    start = np.asarray([1.0, 1.0, 2.0, 2.0])
    better = np.asarray([0.0, 0.0, 9.0, 9.0])
    scores = local_affine.correlation_ratios(
        groups, np.stack((start, better)))
    assert scores[0] == pytest.approx(scores[1]) == pytest.approx(1.0), (
        "both readings separate the two states perfectly, so both are "
        "maximum-likelihood; a table frozen at `start` would have scored "
        "`better` lower purely for having moved")


def test_the_objective_is_the_profile_gaussian_log_likelihood():
    for correlation, n_cells in ((0.0, 100), (0.5, 100), (0.9, 2048)):
        assert np.isclose(
            local_affine.profile_log_likelihood(correlation, n_cells),
            -0.5 * n_cells * np.log(1.0 - correlation ** 2))
    assert local_affine.profile_log_likelihood(0.0, 100) == 0.0
    assert np.isfinite(local_affine.profile_log_likelihood(1.0, 100))


def _quadratic(peak_xy: tuple[float, float], peak_linear: float = 0.0):
    """A scorer with one maximum, so the descent has a right answer."""
    calls: list[int] = []

    def score(candidates):
        calls.append(len(candidates))
        out = []
        for candidate in candidates:
            error = (np.asarray(candidate.translation, np.float64)
                     - np.asarray(peak_xy, np.float64))
            linear_error = float(candidate.linear[0, 1]) - peak_linear
            out.append(-float(error @ error) - linear_error ** 2)
        return np.asarray(out, np.float64)

    return score, calls


def test_the_search_finds_a_translation_and_repeats_itself_exactly():
    score, _calls = _quadratic((1.7, -0.9))
    first = local_affine.search(score, local_affine.Affine.zero(), 3.0,
                                0.125, 500)
    second = local_affine.search(*(_quadratic((1.7, -0.9))[0],
                                   local_affine.Affine.zero(), 3.0, 0.125,
                                   500))
    assert np.allclose(first.affine.translation, (1.6875, -0.9375),
                       atol=0.2)
    assert np.array_equal(first.affine.as_vector(),
                          second.affine.as_vector()), (
        "the search draws no random numbers and visits candidates in a "
        "fixed order: two runs are one run")
    assert first.correlation == second.correlation


def test_the_search_opens_the_linear_terms_after_the_translation():
    score, _calls = _quadratic((0.0, 0.0), peak_linear=0.5)
    result = local_affine.search(score, local_affine.Affine.zero(), 3.0,
                                 0.125, 500)
    assert abs(float(result.affine.linear[0, 1]) - 0.5) < 0.2
    assert np.allclose(result.affine.translation, (0.0, 0.0), atol=0.2)


def test_no_candidate_the_search_returns_can_leave_its_bound():
    bound = 3.0
    score, _calls = _quadratic((99.0, -99.0))
    result = local_affine.search(score, local_affine.Affine.zero(), bound,
                                 0.125, 500)
    assert np.all(np.abs(result.affine.translation) <= bound + 1e-12)
    linear_bound = bound * local_affine.LINEAR_BOUND_FRACTION
    assert np.all(np.abs(result.affine.linear) <= linear_bound + 1e-12)


def test_the_linear_stage_is_one_sweep_and_the_budget_says_so():
    score, calls = _quadratic((0.0, 0.0))
    local_affine.search(score, local_affine.Affine.zero(), 3.0, 0.125, 500)
    ladder = local_affine.step_ladder(3.0, 0.125)
    linear_ladder = local_affine.step_ladder(
        3.0 * local_affine.LINEAR_BOUND_FRACTION, 0.125)
    side = 2 * local_affine.COARSE_STEPS_PER_SIDE + 1
    expected = ([1, side * side] + [8] * (len(ladder) - 1)
                + [side - 1 if index == 0 else 2
                   for _term in range(local_affine.N_LINEAR_TERMS)
                   for index in range(len(linear_ladder))])
    assert calls == expected, (
        "a second sweep over the linear terms would be a fixed-point "
        "iteration, which is the shape E8 measured diverging")


def test_a_refused_search_leaves_the_hint_untouched():
    zero = local_affine.Affine.zero()
    unit = local_affine.unit_coordinates(
        np.asarray([[3, 4], [7, 9]], np.int64), (64, 64))
    assert np.array_equal(zero.offsets_dots_xy(unit), np.zeros((2, 2)))
    assert zero.magnitude_dots() == 0.0


def test_the_worst_corner_of_a_full_correction_is_reported():
    affine = local_affine.Affine(
        translation=np.asarray((1.0, 0.0), np.float64),
        linear=np.asarray(((0.5, 0.5), (0.0, 0.0)), np.float64))
    assert np.isclose(affine.magnitude_dots(), 2.0)


# --- the bound, the resolution and the support floor, all derived -------


def test_the_translation_bound_is_one_printed_cell():
    assert swim.translation_bound_dots(ROW) == float(CELL_DOTS)


def test_the_bound_is_inside_the_field_s_own_measurement_reach():
    """CORRECTED 2026-09-08 (W7): the claim it replaces was false at c2.

    The claim was that one printed cell "strictly contains the field's
    own measurement reach", and the pin stood on a c3 row where 3.0 dots
    beats the anchor tier's Y reach of 2.24.  On sheet J's own row —
    the FOSSIL `L:c2-cmy8-r0547@53x37`, which is what that sheet was
    printed and decoded under, not the display name the 2026-09-02
    re-key gave to another row — the bound is 2.0 and the reach is the
    same 2.24, so the ordering was already the other way; and with the
    certified tier's radius at 1.25 printed cells the reach is
    1.25*cell - 0.26 on every plane and every row, past one cell
    everywhere.  Both rows are asserted, so a row that put the bound
    back outside the reach fails here.  The two bound different things —
    this one a per-window affine against the addressing question, the
    reach what a correlation could have seen — and what licenses the
    swim is the measured column below, not an ordering.
    """
    c2_row = identity.resolve_format_ref("L:c2-cmy8-r0547@53x37")
    for row, cell_dots in ((ROW, CELL_DOTS), (c2_row, 2)):
        bound = swim.translation_bound_dots(row)
        assert bound == float(cell_dots)
        for plane in range(3):
            assert bound < field_tiers.measurement_reach_dots(plane,
                                                              cell_dots)


def test_the_resolution_is_a_quarter_capture_pixel_in_dots():
    assert swim.resolution_dots(PITCH_PX, CELL_DOTS) == pytest.approx(0.125)
    assert swim.resolution_dots(PITCH_PX * 2, CELL_DOTS) == pytest.approx(
        0.0625), "a finer capture resolves a finer correction"
    assert swim.resolution_dots(0.0, CELL_DOTS) == float(CELL_DOTS)


def test_the_support_floor_is_the_level_table_s_own():
    """RE-POINTED 2026-09-08: the arithmetic was pinning itself.

    `MIN_OBJECTIVE_CELLS == N_STATES * MIN_STATE_CELLS` restates the
    line above it in `swim.py` and holds whatever the table does.  This
    was a cross-module pin until W2 moved the level table into `swim.py`
    beside the floor; the re-point kept the shape and lost the claim.
    The claim is that the objective's floor is the TABLE's, so ask the
    table: at the floor every state is live, one cell short of it that
    state is not, and the objective wants the whole alphabet's worth.
    Since 2026-10-12 the alphabet is the row's (`min_objective_cells`;
    cmy's four states in test_h3_cmy_residue): cmy8's eight, 64 cells.
    """
    states = np.repeat(np.asarray(ROW.state_ids), swim.MIN_STATE_CELLS)
    values = np.zeros((states.size, 3), np.float64)
    _levels, live = swim.state_levels(states, values, ROW.state_ids)
    assert live.all() and states.size == swim.min_objective_cells(ROW) == 64
    _levels, short = swim.state_levels(states[:-1], values[:-1],
                                       ROW.state_ids)
    assert not short[-1] and short[:-1].all(), (
        "one cell under the floor must drop that state and only it")
    assert swim.MIN_LIVE_STATES == 2, (
        "one live state has no separation to correlate against")


# --- a synthetic window: the units, and the displacement recovered ------


def _synthetic_window(rot_k: int = 0
                      ) -> tuple[color_region.RegionWindow, np.ndarray]:
    """The same square window, placed at one of the four rotations.

    The cell set is square and the page origin is the extent origin, so
    every rotation covers the SAME page cells and reads the SAME
    raster; what changes is the frame the window's own pose and search
    space are written in, which is the whole subject of the page map.
    """
    local = _h3_facts.tile_cells(SPAN_CELLS)
    placement = _h3_fixture_geometry.window_placement(
        WID, _h3_fixture_geometry.page_native_affine(PITCH_PX, 0.0), local,
        page=PAGE, rot_k=rot_k)
    window = _h3_fixture_geometry.window_pose(ROW, placement)
    return window, local


#: ONE RENDER PER SHIFT, 2026-09-05: nine call sites ask for four
#: distinct shifts of the same 0.13 s stimulus.  Every caller paints the
#: same `_synthetic_window` cells, which is what makes the shift the whole
#: key; the planes are frozen read-only, being shared now.
_RENDERS: dict[float, tuple[np.ndarray, ...]] = {}


def _rendered_planes(local: np.ndarray,
                     shift_dots: float) -> tuple[np.ndarray, ...]:
    key = float(shift_dots)
    planes = _RENDERS.get(key)
    if planes is None:
        planes = _render_planes(local, key)
        for plane in planes:
            plane.setflags(write=False)
        _RENDERS[key] = planes
    return planes


def _render_planes(local: np.ndarray,
                   shift_dots: float) -> tuple[np.ndarray, ...]:
    """Paint the format's own furniture, one plane displaced in x.

    Ink reads DARK, which is the convention every correlation template
    in the receiver is written against.  The page is then blurred: a hard-edged raster has a FLAT
    optimum a cell wide (the sampling aperture sits entirely inside a
    cell over a whole plateau, so every displacement there reads the
    same), and a channel with no MTF is not a channel.  One dot of
    Gaussian blur is the Canon's own measured order (e028's knife edge:
    glass-level MTF10 near 17 lp/mm), and it makes the objective a peak
    instead of a plateau — which is what lets this test ask for a NUMBER
    back rather than an interval.
    """
    from holo.receiver.format import tile_codec

    states, kinds = color_model.reference_states(ROW, GEOMETRY, PAGE, local)
    bits = np.zeros((states.size, 3), np.uint8)
    known = states >= 0
    bits[known] = tile_codec.states_to_planes(states[known])
    # unproven cargo gets a deterministic pattern so the raster is not
    # blank there; the fit must ignore it, and the test that it does is
    # `test_only_provable_cells_enter_the_objective`
    cargo = ~known
    pattern = ((local[:, 0] * 131 + local[:, 1] * 17) % 8).astype(np.uint8)
    bits[cargo] = np.stack(((pattern[cargo] >> 0) & 1,
                            (pattern[cargo] >> 1) & 1,
                            (pattern[cargo] >> 2) & 1), axis=1)
    size = int(SPAN_CELLS * PITCH_PX)
    planes = []
    for plane in range(3):
        image = np.ones((size, size), np.float32)
        ink = bits[:, plane].astype(np.float32)
        for row, column, value in zip(local[:, 0], local[:, 1], ink):
            y0 = int(row * PITCH_PX)
            x0 = int(column * PITCH_PX)
            image[y0:y0 + int(PITCH_PX), x0:x0 + int(PITCH_PX)] = 1.0 - value
        if plane == 2 and shift_dots:
            step = int(round(shift_dots * PITCH_PX / CELL_DOTS))
            image = np.roll(image, step, axis=1)
        planes.append(ndimage.gaussian_filter(image, BLUR_PX))
    return tuple(planes)


def test_the_search_recovers_a_two_dot_plane_displacement_in_dots():
    window, local = _synthetic_window()
    planes = _rendered_planes(local, INJECTED_DOTS)
    fit = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX, 1.0,
                          (None, None, None))
    assert fit is not None and fit.fitted
    assert fit.n_cells >= swim.min_objective_cells(ROW)
    displaced = fit.affines[2]
    assert displaced is not None
    resolution = swim.resolution_dots(PITCH_PX, CELL_DOTS)
    ladder = local_affine.step_ladder(swim.translation_bound_dots(ROW),
                                      resolution)
    assert abs(float(displaced.translation[0]) - INJECTED_DOTS) \
        <= ladder[-1], (
        "the fit is in printed DOTS and converts to cells before the "
        "pose, exactly as lib/page_map does; the error must be inside "
        "the search's own finest step, not a factor")
    assert abs(float(displaced.translation[1])) < 0.5
    for plane in (0, 1):
        quiet = fit.affines[plane]
        assert quiet is None or np.all(np.abs(quiet.translation) < 0.5), (
            "an in-register plane must not be swum away from its pose")


def test_the_displaced_plane_scores_better_after_the_swim_than_before():
    window, local = _synthetic_window()
    planes = _rendered_planes(local, INJECTED_DOTS)
    fit = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX, 1.0,
                          (None, None, None))
    assert fit.correlations[2] > 0.5
    assert fit.log_likelihoods[2] > 0.0


def test_the_search_is_bit_repeatable_on_the_same_window():
    window, local = _synthetic_window()
    planes = _rendered_planes(local, INJECTED_DOTS)
    first = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX,
                            1.0, (None, None, None))
    second = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX,
                             1.0, (None, None, None))
    for left, right in zip(first.affines, second.affines):
        assert (left is None) == (right is None)
        if left is not None:
            assert np.array_equal(left.as_vector(), right.as_vector())
    assert first.correlations == second.correlations
    assert first.n_evaluations == second.n_evaluations


def _field_step_dots(window, planes) -> float:
    """What the PAGE field's estimator recovers on this evidence.

    The whole production chain for one plane, in printed DOTS: the
    collector's own tiers over this window — already page-axis, because
    they probe through the page map — the gauge, then
    `plane_field.solve` (the smoother and the ridge) and finally the
    per-cell evaluation the read side applies.  Measuring after the
    evaluation is the point: it is the number the sampler would actually
    move by, and the number directly comparable to the swim's
    translation.
    """
    crop = fields_collect.window_crop(window, planes, PITCH_PX, 1.0)
    codes = tuple(sorted(fields_collect.tile_rows(window.page_cells_yx,
                                                  ROW.tiles_yx)))
    fresh = tuple(
        (code, plane, field_tiers.furniture_template(
            ROW, GEOMETRY, PAGE, divmod(code, ROW.tiles_yx[1]), plane))
        for code in codes for plane in range(fields_collect.N_PLANES))
    made = fields_collect.measure_window(
        ROW, window, crop,
        fields_collect.cell_lookup(window.page_cells_yx, ROW.tiles_yx[1]),
        fresh, CELL_DOTS)
    n = len(made)
    rows = evidence.Rows(
        capture=np.zeros(n, np.int64), page=np.full(n, PAGE, np.int64),
        tile_code=np.asarray(made.tile_code, np.int64),
        plane=np.asarray(made.plane, np.int64),
        delta_dots_xy=np.stack(made.delta_dots_xy),
        measured_xy=np.stack(made.measured_xy),
        weight=np.asarray(made.weight, np.float64),
        source=np.asarray(made.source, np.int64),
        window=np.zeros(n, np.int64),
        pose_generation=np.ones(n, np.int64))
    solution = plane_field.solve(
        rows, ROW.tiles_yx, cell_dots=CELL_DOTS,
        prior=plane_field.default_prior(CELL_DOTS,
                                        dots_per_mm=DOTS_PER_MM))
    offsets = plane_field.evaluate(solution.delta_dots_xy[2],
                                   window.page_cells_yx,
                                   geometry.TILE_CELLS)
    return float(np.median(np.abs(offsets[:, 0])))


def test_the_swim_recovers_what_the_standing_field_cannot_express():
    """The row's licence, RE-ARGUED against the PAGE field (2026-09-07).

    It has been re-argued twice before, each time because the field got
    better: the first version pinned the field at 9% of any injection
    and the swim at ~100%, which was mostly a DEFECT (the field fitted
    in cells and published dots); the second was argued against the
    2.0-dot clamp the photometric estimator carried.  Neither exists
    now — no linearised probes, and the page field's own bound IS the
    measurement (I8 as amended at W7: per plane, at that plane's widest
    tier radius less the saturation margin, 3.49 dots on this c3 row).
    This fixture carries no certificate, so the tier that stops first
    here is the anchor one, at 2.24.

    RE-MEASURED 2026-09-08 at the W8 integration, on the one primitive
    and the whole-site furniture template that replaced the parity
    halves and the blind sweep:

        injected   field, as applied   swim (blind)   swim (hinted)
        1.0 dots   0.894  (89%)        0.938  (94%)   1.081
        1.5 dots   1.339  (89%)        1.500 (100%)   1.526
        2.0 dots   1.783  (89%)        2.062 (103%)   1.970
        2.5 dots   0.000   (0%)        2.438  (98%)   2.438
        3.0 dots   0.000   (0%)        3.000 (100%)   3.000
        4.0 dots   0.000   (0%)        3.000  (75%)   3.000
        5.0 dots   0.000   (0%)        3.000  (60%)   3.000

    INSIDE the estimator's reach the field is excellent and this row
    makes no claim against it — the swim is more accurate, not
    necessary.  The licence is the SHAPE of that column past the reach.
    The anchor tier's Y radius is 2.5 dots and a peak within
    `ANCHOR_SATURATION_MARGIN_DOTS` of the wall is a lock rather than a
    displacement, so at 2.24 dots this window's tiers stop and the field
    reads EXACTLY ZERO past it, at every injection.  W7's column read
    1.124 of four dots and 1.699 of five there: those were the
    parity-half template aliasing onto a nearer peak, and the whole-site
    template's sharper null refuses them (W8 R-C, review F2 — the same
    ruling that retired the blind sweep).  So the displacement this row
    exists for is the one past the tiers' reach and inside the swim's
    own bound, which is where the swim carries the whole of it unaided.
    """
    window, local = _synthetic_window()
    anchor_reach = (field_tiers.ANCHOR_RADIUS_DOTS[2]
                    - field_tiers.ANCHOR_SATURATION_MARGIN_DOTS)
    assert anchor_reach < field_tiers.measurement_reach_dots(2, CELL_DOTS)
    inside = _rendered_planes(local, INJECTED_DOTS)
    assert INJECTED_DOTS < anchor_reach
    field_inside = _field_step_dots(window, inside)
    swum_inside = abs(float(swim.fit_window(
        ROW, GEOMETRY, window, {}, inside, PITCH_PX, 1.0,
        (None, None, None)).affines[2].translation[0]))
    assert swum_inside >= field_inside, (
        "inside the estimator's reach the swim need not beat the field "
        "by much, but it may never be worse on the same evidence")

    # the first shift past the tiers' reach this stimulus can express;
    # it sits inside the swim's own bound, which is what makes the
    # recovery below the row's claim rather than the bound's
    beyond = RENDER_STEP_DOTS * math.ceil(anchor_reach / RENDER_STEP_DOTS)
    assert anchor_reach < beyond <= BOUND_DOTS
    planes = _rendered_planes(local, beyond)
    field = _field_step_dots(window, planes)
    hinted, _eta, _evals = _hinted(window, planes, field)
    assert field == 0.0, (
        f"past its own reach the field recovers {field:.3f} of "
        f"{beyond} dots; it is supposed to publish nothing there, and a "
        f"number instead of a zero is a tier reading a displacement it "
        f"cannot see (review F2)")
    assert hinted >= 0.9 * beyond, (
        f"the swim, on evidence the field refused, recovered "
        f"{hinted:.3f} of {beyond} dots")


def _hinted(window, planes, delta_dots: float | None):
    fields_tuple = ((None, None, None) if delta_dots is None
                    else (None, None, _h3_facts.plane_field(
                        plane=2, delta_dots=delta_dots, tiles_yx=(2, 2))))
    fit = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX, 1.0,
                          fields_tuple)
    affine = fit.affines[2]
    start = 0.0 if delta_dots is None else float(delta_dots)
    # a REFUSED plane is the row's no-op law, not a zero correction: the
    # hint already explains the page and the search found nothing worth
    # moving for, so the total is the hint itself
    #
    # the affine is the WINDOW's own frame, the hint and the injection
    # are the PAGE's, so the two meet in page axes and nowhere else
    moved = 0.0 if affine is None else float(page_map.page_axes(
        np.asarray(affine.translation, np.float64), window.rotation)[0])
    return start + moved, fit.correlations[2], fit.n_evaluations


#: One injection per case, 2026-09-05: the three points used to be a
#: loop in one body.  Same three shifts, same stimulus, same four
#: assertions per point — one failure name per point.
@pytest.mark.parametrize("injected", INJECTIONS_DOTS)
def test_the_field_hint_costs_nothing_and_reaches_as_far_as_its_tier(
        injected: float):
    """What the standing field's value at this window is actually worth.

    RE-MEASURED 2026-09-08 at the W8 integration on the PAGE field (the
    one primitive, the joint solve, evaluated per cell), same fixture,
    hint ablated by starting the search from zero instead of from the
    field's own number:

        injected   field   blind total   hinted total   blind/hinted eta
        1.0 dots   0.894   0.938         1.081          0.9986 / 0.9985
        1.5 dots   1.339   1.500         1.526
        2.0 dots   1.783   2.062         1.970          0.9972 / 0.9974
        2.5 dots   0.000   2.438         2.438          0.9913 / 0.9913
        3.0 dots   0.000   3.000 (clip)  3.000          0.9788 / 0.9788
        3.5 dots   0.000   3.000 (clip)  3.000          0.9755 / 0.9755
        4.0 dots   0.000   3.000 (clip)  3.000          0.9477 / 0.9477
        5.0 dots   0.000   3.000 (clip)  3.000          0.4274 / 0.4274

    246 evaluations at every point, hinted and blind alike: the hint
    costs and saves NOTHING in search work — the step ladder is a
    function of the bound and the sampler's resolution, never of where
    the search starts — so it can never hurt.

    THE SHAPE OF THE FIELD COLUMN IS THE ESTIMATOR'S REACH.  The anchor
    tier's Y radius is 2.5 dots and a peak within
    `ANCHOR_SATURATION_MARGIN_DOTS` of the wall is a lock rather than a
    displacement, so past **2.24 dots** the tiers refuse, the page has
    no evidence there and the field reads exactly zero (I6, the honest
    answer) — at every injection, where W7's column had the parity-half
    template aliasing back onto a nearer peak at four and five dots.

    WHAT THAT COSTS, and it is this row's own finding rather than a
    regression: on a window carrying only FURNITURE the field's reach
    (2.24 dots) is inside the swim's own bound (3.0), so the hint can
    never carry the search past that bound and there is no reach left to
    buy — the last two rows of W7's column, 3.936 of four dots and 4.699
    of five, were bought with an aliased hint and are gone with it.  The
    template that could buy it is the CERTIFIED one, whose reach on this
    row is 3.49 dots; this fixture carries no certificate and its
    renderer paints a stand-in pattern over unproven cargo, so a
    certified arm is a stimulus this module does not have.  OWED to the
    lead with the W8 integration report.
    """
    window, local = _synthetic_window()
    reach = (field_tiers.ANCHOR_RADIUS_DOTS[2]
             - field_tiers.ANCHOR_SATURATION_MARGIN_DOTS)
    planes = _rendered_planes(local, injected)
    field_dx = _field_step_dots(window, planes)
    blind, blind_eta, blind_evals = _hinted(window, planes, None)
    hinted, hinted_eta, hinted_evals = _hinted(window, planes, field_dx)
    assert hinted_evals == blind_evals, (
        "the search budget is the ladder's, not the start's: a hint "
        "that changed the cost would be a tuning knob")
    assert hinted_eta >= blind_eta - 1e-3
    if injected > reach:
        assert field_dx == 0.0, (
            f"at {injected} dots, past the tiers' own {reach} of reach, "
            f"the field published {field_dx:.3f}: a displacement it "
            f"cannot see must publish nothing (review F2)")
        assert hinted == pytest.approx(blind), (
            "a zero hint is not a hint: it may not move the answer")
    else:
        assert field_dx >= FIELD_SHARE_INSIDE_REACH * injected, (
            f"inside its own reach the field took {field_dx:.3f} of "
            f"{injected} dots and the search is left carrying a "
            f"displacement the page had already measured")
    assert abs(hinted - injected) <= abs(blind - injected) + 0.25


def test_a_plane_that_never_moves_is_refused_not_zeroed():
    """A zero correction and a refusal are different answers.

    A refusal hands the plane back to the standing lane — its field if
    it has one, its own pose if it has not.  A zero correction would say
    the search HAS an opinion and that the opinion is "do not move",
    which on a plane it never scored is a silent regression against
    whatever the page had already solved there.
    """
    window, local = _synthetic_window()
    planes = _rendered_planes(local, 0.0)
    fit = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX, 1.0,
                          (None, None, None))
    assert fit is not None
    for plane, affine in enumerate(fit.affines):
        assert affine is None or np.any(affine.as_vector()), (
            f"plane {plane} came back as an all-zero correction instead "
            f"of a refusal")
    rows = _rows_for(window)
    got = swim.offsets_builder({0: fit} if fit.fitted else {},
                               {0: window}, (None, None, None))(rows)
    assert got is None or all(
        entry is None or np.any(entry) for entry in got)


def test_only_provable_cells_enter_the_objective():
    window, local = _synthetic_window()
    sites = swim.window_sites(ROW, GEOMETRY, window, {})
    assert sites is not None
    rows = color_region.build_window_rows(ROW, GEOMETRY, window, {}, {})
    complete = np.asarray(rows.known_component_mask, bool).all(axis=1)
    assert np.array_equal(
        sites.page_cells_yx,
        np.asarray(rows.page_cells_yx, np.int64)[complete])
    kinds = np.asarray(rows.furniture_kind, np.int8)
    assert np.all(kinds[complete] >= 0), (
        "with no certificate on the page every provable cell is FORMAT "
        "furniture: no decision of the receiver's is a label here"
    )
    assert int(complete.sum()) >= swim.min_objective_cells(ROW)


def test_a_certified_neighbour_adds_cargo_labels_and_the_target_adds_none():
    window, local = _synthetic_window()
    streams = tuple(fact.stream_id for fact in ROW.streams)
    certificate = data.Certificate(
        page=PAGE, ty=0, tx=1, stream_id=streams[0],
        user_bits=np.zeros(ROW.streams[0].user_bits, np.uint8),
        source="tiles/scan")
    certificates = {(PAGE, 0, 1, streams[0]): certificate}
    bare = swim.window_sites(ROW, GEOMETRY, window, {})
    with_donor = swim.window_sites(ROW, GEOMETRY, window,
                                            certificates)
    assert with_donor.page_cells_yx.shape[0] >= bare.page_cells_yx.shape[0]
    added = {tuple(cell) for cell in with_donor.page_cells_yx} - {
        tuple(cell) for cell in bare.page_cells_yx}
    for cell_y, cell_x in added:
        assert (cell_y // geometry.TILE_CELLS,
                cell_x // geometry.TILE_CELLS) == (0, 1), (
            "only the CERTIFIED tile's cargo becomes a label; the "
            "target's own cargo is what the correction is judged by and "
            "may never be what it is fitted on")


# --- the no-op: a refused plane reads exactly as the lane would ---------


def _rows_for(window: color_region.RegionWindow) -> data.WindowRows:
    return color_region.build_window_rows(ROW, GEOMETRY, window, {}, {})


def test_no_fit_means_the_standing_offsets_verbatim():
    """And a window with nothing to say says it PER PLANE.

    RE-POINTED 2026-09-08 (the W3a review's finding 1).  The seam used
    to answer the page-level `None` here, which `build_region_inputs`
    reads as "this region has no corrected arm" and applies to the WHOLE
    region — so one unfitted window threw away every fitted window's
    correction on a page with no solved field.  The answer is a tuple of
    per-plane Nones: this window is read at its own pose, which is what
    the sentence below always claimed, and the region keeps its arm.
    """
    window, _local = _synthetic_window()
    rows = _rows_for(window)
    builder = swim.offsets_builder({}, {0: window}, (None, None, None))
    assert builder(rows) == (None, None, None), (
        "with no field and no fit there is nothing to correct, and the "
        "window is read at its own pose")
    field = _h3_facts.plane_field(plane=2)
    standing = (None, None, field)
    expected = color_region.field_offsets(standing, rows.page_cells_yx)
    got = swim.offsets_builder({}, {0: window}, standing)(rows)
    assert np.array_equal(got[2], expected[2])


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_a_refused_plane_carries_the_hint_and_nothing_else(rot_k):
    """The composition, both frames, at every rotation.

    The hint is PAGE-axis dots and the affine is the WINDOW's own, so
    what the seam hands back is `hint + page_axes(affine)` — the unit
    `row_offsets` and `anchor.features_at` consume.  At rot 0 the two
    frames agree and the conversion is invisible; at rot 1, 2 and 3 a
    seam that skipped it would move the sampler along the wrong axis,
    which is what the second assertion below refuses to let happen.
    """
    window, _local = _synthetic_window(rot_k=rot_k)
    rows = _rows_for(window)
    field = _h3_facts.plane_field(plane=2)
    standing = (None, None, field)
    local_translation = (1.0, 0.0)
    fit = swim.WindowFit(
        patch_ordinal=0, window=window,
        affines=(None, None, local_affine.Affine(
            translation=np.asarray(local_translation),
            linear=np.zeros((2, 2)))),
        correlations=(0.0, 0.0, 0.9), log_likelihoods=(0.0, 0.0, 1.0),
        n_cells=1000, n_evaluations=100)
    got = swim.offsets_builder({0: fit}, {0: window}, standing)(rows)
    expected = color_region.field_offsets(standing, rows.page_cells_yx)
    assert got[0] is None and got[1] is None, (
        "a plane the search refused must not be moved off the page's own "
        "reading of it")
    in_page = page_map.page_axes(np.asarray(local_translation),
                                 window.rotation)
    assert np.allclose(got[2] - expected[2], in_page)
    if rot_k:
        assert not np.allclose(in_page, local_translation), (
            "a rotation that changed nothing would let an unconverted "
            "seam pass this test")


@pytest.mark.parametrize("rot_k", [0, 2])
def test_the_hint_reaches_the_same_distance_at_a_rotated_placement(rot_k):
    """The search's own frame round trip, measured (bar B1).

    The injection is a PAGE displacement of the printer's and the raster
    is a picture of the page, so the same window placed at rot 0 and at
    rot 2 must recover the same page number.  Everything in between is
    written in the window's own frame — the hint comes down through
    `page_map.local_axes`, the affine is searched there, and the sum
    goes back up — and a missing conversion at either end is a sign flip
    at rot 2.

    The injection is the ordinary one because the field must be nonzero
    for the down conversion to carry anything, and past 2.24 dots the
    tiers refuse and it is exactly zero (`FIELD_AT_INJECTION`'s note).
    Measured here 2026-09-08 at the gain fix: negate the hint and the
    total falls from 1.946 to 1.054, six times this tolerance, so the
    down leg is load-bearing.  The up leg is NOT exercised here any more
    — see `FIELD_AT_INJECTION` — and belongs to
    `test_a_refused_plane_carries_the_hint_and_nothing_else`.
    """
    window, local = _synthetic_window(rot_k=rot_k)
    planes = _rendered_planes(local, INJECTED_DOTS)
    field = _field_step_dots(window, planes)
    total, _eta, _evals = _hinted(window, planes, field)
    assert field == pytest.approx(FIELD_AT_INJECTION, abs=0.05), (
        "the collector reads the page's own displacement whatever "
        "rotation the window was placed at")
    assert total == pytest.approx(SWUM_AT_INJECTION, abs=0.15), (
        f"rot {rot_k} recovered {total:.3f} of "
        f"{INJECTED_DOTS} dots")


def test_every_offset_row_lines_up_with_the_rows_the_head_built():
    window, _local = _synthetic_window()
    rows = _rows_for(window)
    fit = swim.WindowFit(
        patch_ordinal=0, window=window,
        affines=tuple(local_affine.Affine(
            translation=np.asarray((0.5, -0.25)),
            linear=np.zeros((2, 2))) for _ in range(3)),
        correlations=(0.9,) * 3, log_likelihoods=(1.0,) * 3,
        n_cells=1000, n_evaluations=100)
    got = swim.offsets_builder({0: fit}, {0: window},
                               (None, None, None))(rows)
    for entry in got:
        assert entry.shape == (rows.page_cells_yx.shape[0], 2), (
            "the callable seam is handed the head's OWN rows, so an "
            "offset array can never be a row short")


def test_the_seam_prefers_the_callable_over_the_standing_field():
    window, _local = _synthetic_window()
    rows = _rows_for(window)
    field = _h3_facts.plane_field(plane=2)
    marker = (np.zeros((rows.page_cells_yx.shape[0], 2)), None, None)
    assert color_region.row_offsets(
        None, (None, None, field), rows,
        lambda _rows: marker)[0] is marker[0]
    assert color_region.row_offsets(
        {0: marker}, (None, None, field), rows,
        lambda _rows: None) is marker, (
        "the mapping stays the most specific tier: an existing caller "
        "cannot be overtaken by the new one"
    )


# --- the row: eligibility, arming, price, transience --------------------


def _color_engine() -> engine._Engine:
    request = dataclasses.replace(_h3_facts.new_engine()._request,
                                  format_ref=COLOR_FORMAT_REF)
    instance = engine._Engine(request, [])
    instance._ingest(_h3_facts.capture())
    return instance


def _subject(ty: int = 0, tx: int = 0) -> tuple:
    """The tile-LANE (page, ty, tx, ppc) — one subject for C, M and Y."""
    return (PAGE, ty, tx, PPC)


def _arm(store: engine._Engine, stream_index: int = 0) -> None:
    """Fold one failed scan verdict: the arming a real subject is born by."""
    store._ingest(dataclasses.replace(
        _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED),
        stream_id=ROW.streams[stream_index].stream_id))


def _attempt_fact(stage: str, outcome: str) -> data.AttemptFact:
    return data.AttemptFact(
        page=PAGE, ty=0, tx=0, stream_id=ROW.streams[0].stream_id,
        stage=stage, outcome=outcome, n_informative=1000, n_iters=60,
        syndrome_ok=False, crc_ok=False, components=((CAPTURE_ID, 0),))


def test_the_descriptor_produces_only_attempts_and_certificates():
    assert swim.SWIM_DESCRIPTOR.name == "tiles.swim"
    assert swim.SWIM_DESCRIPTOR.subject_kind == "tile"
    assert swim.SWIM_DESCRIPTOR.born_by == (
        data.AttemptFact, data.WindowEvidence, data.ColorEvidenceRow)
    assert swim.SWIM_DESCRIPTOR.produces == (data.AttemptFact,
                                             data.Certificate)
    # transient by construction: no standing evidence row, no standing
    # context cell, no plane field — the equality above says so


def test_the_row_is_the_dearest_in_the_tree_and_escalates():
    assert swim.SWIM_COST > local_ctx.LOCAL_COST
    assert swim.SWIM_COST > uplift.A4B_COST
    store = _color_engine()
    never = swim._swim_cost(store, _subject(), swim.STAGE_SWIM, 0, 0)
    first = swim._swim_cost(store, _subject(), swim.STAGE_SWIM, 1, 0)
    third = swim._swim_cost(store, _subject(), swim.STAGE_SWIM, 3, 0)
    # base + base x earlier fires (2026-10-18): a row pays its base
    # once, then its base again for every earlier fire -- never twice
    # at the base, which the earlier `price * attempts if attempts`
    # shape charged on the first two fires
    assert first == never + swim.SWIM_COST
    assert third == never + 3 * swim.SWIM_COST


@pytest.mark.parametrize("stage,outcome,arms", ARMING_MATRIX)
def test_the_row_arms_on_failed_reads_but_never_on_its_own(stage, outcome,
                                                           arms):
    store = _color_engine()
    subjects = swim._swim_subjects(store, _attempt_fact(stage, outcome))
    assert bool(subjects) is arms
    if arms:
        assert subjects == (_subject(),)


def test_a_k_page_never_arms_prepares_or_qualifies():
    store = _h3_facts.new_engine()
    store._ingest(_h3_facts.capture())
    fact = _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED)
    fact = dataclasses.replace(fact, stream_id=store.row.streams[0].stream_id)
    assert swim._swim_subjects(store, fact) == (), (
        "one plane means any per-plane correction IS a pose correction, "
        "and the pose rows own that")
    subject = (PAGE, 0, 0, PPC)
    assert swim._swim_eligible(store, subject) is False
    assert swim.prepare_swim(store, subject, swim.STAGE_SWIM) is None


def test_a_colour_tile_with_no_placed_window_prepares_nothing():
    store = _color_engine()
    assert swim._swim_eligible(store, _subject()) is False
    assert swim.prepare_swim(store, _subject(), swim.STAGE_SWIM) is None


def test_furniture_alone_admits_the_row_where_tiles_local_refuses():
    store = _color_engine()
    store._ingest(_h3_facts.window(WID, ordinal=0))
    store._ingest(dataclasses.replace(
        _h3_facts.placement(WID),
        local_cells_yx=_h3_facts.tile_cells(SPAN_CELLS)))
    store._ingest(_h3_facts.color_row())
    _arm(store)
    assert local_ctx._local_eligible(store, _subject()) is \
        False, ("tiles.local needs a certified neighbour to have any "
                "label; its subject is the tile LANE since 2026-09-21")
    assert swim._swim_eligible(store, _subject()) is True, (
        "the swim's labels are the format's own furniture, which every "
        "addressed window carries — that is what lets it work in a dead "
        "band where nothing has ever certified")


def test_a_certified_tile_neither_fires_nor_survives():
    store = _color_engine()
    store._ingest(_h3_facts.window(WID, ordinal=0))
    store._ingest(dataclasses.replace(
        _h3_facts.placement(WID),
        local_cells_yx=_h3_facts.tile_cells(SPAN_CELLS)))
    store._ingest(_h3_facts.color_row())
    _arm(store)
    assert swim._swim_retire(store, _subject()) is None
    for index, stream in enumerate(ROW.streams):
        store._ingest(data.Certificate(
            page=PAGE, ty=0, tx=0, stream_id=stream.stream_id,
            user_bits=np.zeros(stream.user_bits, np.uint8),
            source="tiles/scan"))
        if index == 0:
            assert swim._swim_eligible(store, _subject()) is False, (
                "the one armed stream is certified: nothing left to read")
            assert swim.prepare_swim(store, _subject(),
                                     swim.STAGE_SWIM) is None
            assert swim._swim_retire(store, _subject()) is None, (
                "retirement is the tile's, not the stream's: two "
                "streams are still uncertified")
    assert swim._swim_retire(store, _subject()) == "certified"


def test_the_row_subscribes_to_the_fields_it_hints_from():
    store = _color_engine()
    store._ingest(_h3_facts.window(WID, ordinal=0))
    store._ingest(dataclasses.replace(
        _h3_facts.placement(WID),
        local_cells_yx=_h3_facts.tile_cells(SPAN_CELLS)))
    store._ingest(_h3_facts.color_row())
    keys = swim._swim_reads(store, _subject())
    families = {key[0] for key in keys}
    assert "plane_field" in families, (
        "a new field is a better hint: the row must wake for one")
    assert families == {"plane_field", "pose_affine", "attempt", "tile"}
    assert "lane_poses" not in families, (
        "the page-wide lane-pose key took 4.9 M of sheet H's 6.55 M "
        "wakes for 19 fires; `_fold_placement` emits `pose_affine` at "
        "the same site under the same test, so the per-window key is "
        "the SAME wake at four keys instead of 5,880 subscribers")
    assert ("pose_affine", WID) in keys, (
        "the swim samples the raster THROUGH this window's placement")


def test_the_attempt_stage_is_a_heavy_one():
    assert tiles.STAGE_SWIM150 in tiles.HEAVY_STAGES
    assert tiles.max_iters_for(tiles.STAGE_SWIM150) \
        == tiles.RETRY_BP_MAX_ITERS

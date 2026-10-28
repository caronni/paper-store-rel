"""``tiles.swim`` — the per-plane local-affine rescue, pinned.

Three things this file exists to hold still.  THE UNITS: the search
converts dots to cells before it touches the pose, exactly as
`color_region_anchor.features_with_page_fraction` does, so the
displacement it recovers is the displacement the head will apply — the
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
from fractions import Fraction

import numpy as np
import pytest
from scipy import ndimage

from holo3 import data, engine
from holo3.format import identity
from holo3.lib import geometry, local_affine, plane_field
from holo3.plugins import color_model, color_region, field_tiers
from holo3.plugins import fields, local_ctx
from holo3.plugins import color_region_anchor as anchor
from holo3.plugins import swim, tiles, uplift
from holo3.tests import _h3_facts, _h3_fixture_geometry, _h3_support

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
CAPTURE_ID = _h3_facts.CAPTURE_ID
PPC = Fraction(4)
PAGE = 0
SPAN_CELLS = 2 * geometry.TILE_CELLS
WID = (CAPTURE_ID, 0, 0, (0, 0, SPAN_CELLS, SPAN_CELLS))

ROW = identity.resolve_format_ref(COLOR_FORMAT_REF)
GEOMETRY = identity.build_site_geometry(ROW)
CELL_DOTS = 3
PITCH_PX = 6.0
INJECTED_DOTS = 2.0
BLUR_PX = 1.5

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
    _h3_support.assert_golden(
        "swim translation bound", swim.translation_bound_dots(ROW),
        float(identity.build_site_geometry(ROW).cell_dots)
        if hasattr(GEOMETRY, "cell_dots") else float(CELL_DOTS))


def test_the_bound_reaches_past_the_standing_field_s_own_clamp():
    from holo3.lib import plane_field

    assert swim.translation_bound_dots(ROW) > plane_field.MAX_DELTA_DOTS, (
        "the swim exists because the field saturates; a bound inside the "
        "field's clamp could not rescue a displacement the field clipped")


def test_the_resolution_is_a_quarter_capture_pixel_in_dots():
    assert swim.resolution_dots(PITCH_PX, CELL_DOTS) == pytest.approx(0.125)
    assert swim.resolution_dots(PITCH_PX * 2, CELL_DOTS) == pytest.approx(
        0.0625), "a finer capture resolves a finer correction"
    assert swim.resolution_dots(0.0, CELL_DOTS) == float(CELL_DOTS)


def test_the_support_floor_is_the_level_table_s_own():
    assert swim.MIN_OBJECTIVE_CELLS == (fields.N_STATES
                                        * fields.MIN_STATE_CELLS)
    assert swim.MIN_LIVE_STATES == 2, (
        "one live state has no separation to correlate against")


# --- a synthetic window: the units, and the displacement recovered ------


def _synthetic_window() -> tuple[color_region.RegionWindow, np.ndarray]:
    local = _h3_facts.tile_cells(SPAN_CELLS)
    placement = _h3_fixture_geometry.window_placement(
        WID, _h3_fixture_geometry.page_native_affine(PITCH_PX, 0.0), local,
        page=PAGE)
    window = _h3_fixture_geometry.window_pose(ROW, placement)
    return window, local


def _rendered_planes(local: np.ndarray,
                     shift_dots: float) -> tuple[np.ndarray, ...]:
    """Paint the format's own furniture, one plane displaced in x.

    Ink reads DARK, which is the convention `rectified_ncc` templates
    against.  The page is then blurred: a hard-edged raster has a FLAT
    optimum a cell wide (the sampling aperture sits entirely inside a
    cell over a whole plateau, so every displacement there reads the
    same), and a channel with no MTF is not a channel.  One dot of
    Gaussian blur is the Canon's own measured order (e028's knife edge:
    glass-level MTF10 near 17 lp/mm), and it makes the objective a peak
    instead of a plateau — which is what lets this test ask for a NUMBER
    back rather than an interval.
    """
    from holo3.format import tile_codec

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
    assert fit.n_cells >= swim.MIN_OBJECTIVE_CELLS
    displaced = fit.affines[2]
    assert displaced is not None
    resolution = swim.resolution_dots(PITCH_PX, CELL_DOTS)
    ladder = local_affine.step_ladder(swim.translation_bound_dots(ROW),
                                      resolution)
    assert abs(float(displaced.translation[0]) - INJECTED_DOTS) \
        <= ladder[-1], (
        "the fit is in printed DOTS and converts to cells before the "
        "pose, exactly as features_with_page_fraction does; the error "
        "must be inside the search's own finest step, not a factor")
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


def _all_photometric(sites: fields.WindowSites) -> fields.WindowSites:
    """Hand the whole window to the photometric tier.

    `partition_sites` halves furniture by SITE PARITY between the anchor
    and blind tiers and gives photometry the certified payload — so on
    this synthetic window, which has no certificates and therefore no
    payload rows, photometry gets NOTHING and `measure_pass` returns
    None.  That is the production law working correctly on a fixture
    that is not a production page, and the fixture is what has to bend:
    `test_h3_plane_fields`'s own ramp site does exactly this for exactly
    this reason.  What is compared below is the photometric fitter, on
    both sides, so this is the tier the comparison is about.
    """
    n = int(sites.page_cells_yx.shape[0])
    return dataclasses.replace(sites, partition=field_tiers.SitePartition(
        photometric=np.arange(n, dtype=np.int64),
        anchor=np.zeros(0, np.int64), blind=np.zeros(0, np.int64)))


def _field_step_dots(window, planes, tiles_yx=(2, 2)) -> float:
    """What the standing field's estimator recovers on this evidence.

    The whole standing pipeline for one plane, in printed DOTS: the
    photometric pass, then `plane_field.solve`, which is where the
    smoothing, the ridge and the clamp now live.  Measuring after the
    solve rather than before it is the point — it is what the read side
    would actually apply, and it is the number directly comparable to
    the swim's translation.
    """
    sites = _all_photometric(fields.window_sites(ROW, GEOMETRY, window, {}))
    measurement = fields.measure_pass((sites,), planes, PITCH_PX, 1.0,
                                      (None, None, None), tiles_yx,
                                      CELL_DOTS)
    levels, live = fields.state_levels(measurement.states,
                                       measurement.centres)
    equations, _n_sites = fields.plane_step(
        measurement, levels, live, 2, tiles_yx)
    delta, support = plane_field.solve(equations)
    return float(np.median(np.abs(delta[..., 0][support > 0])))


def test_the_swim_recovers_what_the_standing_field_cannot_express():
    """The row's licence, RE-ARGUED against the repaired field.

    The first version of this test pinned the field at 9% of any
    injection and the swim at ~100%.  That gap was mostly a DEFECT — the
    field fitted in cells and published dots — and the 2026-08-31 units
    fix removed it.  The test fired on the repair, exactly as its own
    failure message asked it to, and the licence is re-argued here
    rather than the bound relaxed.

    MEASURED on this fixture after the fix, same evidence, same window:

        injected   field, as applied   swim (blind)   swim (hinted)
        1.0 dots   0.409  (41%)        0.938  (94%)
        2.0 dots   1.213  (61%)        2.062 (103%)   1.963
        2.5 dots   1.998  (80%)        2.438  (98%)
        3.0 dots   1.975  (66%)        3.000 (100%)   3.100
        4.0 dots   1.043  (26%)        3.000  (75%)   4.043 (101%)
        5.0 dots   0.656  (13%)        3.000  (60%)   3.656

    INSIDE its clamp the repaired field is good, and this row makes no
    claim against it there — the swim is more accurate, not necessary.
    The licence is the SHAPE of that column past the clamp.
    `plane_field.MAX_DELTA_DOTS` is 2.0, so 1.998 at a 2.5-dot injection
    is the field hitting the wall its own constant builds; beyond it the
    linearised fit does not even saturate usefully, it DEGRADES — 26% at
    four dots, 13% at five — because a half-dot probe measures the wrong
    slope that far from the truth.  The swim's bound is one printed cell
    measured FROM THE HINT, so with the field's own number under it the
    search reaches four dots and recovers 101% of them.
    """
    window, local = _synthetic_window()
    from holo3.lib import plane_field

    clamp = plane_field.MAX_DELTA_DOTS
    inside = _rendered_planes(local, clamp)
    field_inside = _field_step_dots(window, inside)
    swum_inside = abs(float(swim.fit_window(
        ROW, GEOMETRY, window, {}, inside, PITCH_PX, 1.0,
        (None, None, None)).affines[2].translation[0]))
    assert swum_inside >= field_inside, (
        "inside the clamp the swim need not beat the field by much, but "
        "it may never be worse on the same evidence")

    beyond = 2.0 * clamp
    planes = _rendered_planes(local, beyond)
    field = _field_step_dots(window, planes)
    hinted, _eta, _evals = _hinted(window, planes, field)
    assert field < 0.5 * beyond, (
        f"at twice its own clamp the field recovers {field:.3f} of "
        f"{beyond} dots; if that ever stops being less than half, the "
        f"field has grown past the constant that bounds it and this "
        f"row's licence needs re-arguing rather than this bound relaxing")
    assert hinted >= 0.9 * beyond, (
        f"the swim, hinted by the field's own number, recovered "
        f"{hinted:.3f} of {beyond} dots")


def _hinted(window, planes, delta_dots: float | None):
    fields_tuple = ((None, None, None) if delta_dots is None
                    else (None, None, _h3_facts.plane_field(
                        plane=2, delta_dots=delta_dots, tiles_yx=(2, 2))))
    fit = swim.fit_window(ROW, GEOMETRY, window, {}, planes, PITCH_PX, 1.0,
                          fields_tuple)
    affine = fit.affines[2]
    start = 0.0 if delta_dots is None else float(delta_dots)
    return (start + float(affine.translation[0]), fit.correlations[2],
            fit.n_evaluations)


def test_the_field_hint_buys_reach_and_not_speed():
    """What the standing field's value at this window is actually worth.

    MEASURED on the REPAIRED field (the 2026-08-31 units fix), same
    fixture, hint ablated by starting the search from zero instead of
    from the field's own number:

        injected   blind total      hinted total   blind eta / hinted
        2.0 dots   2.062            1.963          0.9973 / 0.9974
        3.0 dots   3.000 (clipped)  3.100          0.9787 / 0.9781
        3.5 dots   3.000 (clipped)  3.597          0.9751 / 0.9781
        4.0 dots   3.000 (clipped)  4.043          0.9452 / 0.9784
        5.0 dots   3.000 (clipped)  3.656          0.4403 / 0.8396

    The hint costs and saves NOTHING in search work — the step ladder is
    a function of the bound and the sampler's resolution, never of where
    the search starts — so it can never hurt.  What it buys is REACH:
    the bound is measured from the hint, so a plane displaced past one
    cell stays reachable to the extent the field has already taken up
    the distance.

    Before the units fix that effect was marginal, because the field
    only ever delivered 0.1-0.3 dots.  It is now decisive: at four dots
    the blind search clips at its bound and reads eta 0.945, while the
    same search started from the field's own 1.043 recovers 4.043 dots
    at eta 0.978.  Repairing the field did not make this row redundant;
    it made the row's HINT worth something.
    """
    window, local = _synthetic_window()
    bound = swim.translation_bound_dots(ROW)
    for injected in (INJECTED_DOTS, bound, 2.0 * bound / 1.5):
        planes = _rendered_planes(local, injected)
        field_dx = _field_step_dots(window, planes)
        blind, blind_eta, blind_evals = _hinted(window, planes, None)
        hinted, hinted_eta, hinted_evals = _hinted(window, planes, field_dx)
        assert hinted_evals == blind_evals, (
            "the search budget is the ladder's, not the start's: a hint "
            "that changed the cost would be a tuning knob")
        assert hinted_eta >= blind_eta - 1e-3
        if injected >= bound:
            assert hinted > blind, (
                f"at {injected} dots the unhinted search is clipped at "
                f"its bound {bound}; the hint must reach past it")
        assert abs(hinted - injected) <= abs(blind - injected) + 0.25


def test_a_plane_that_never_moves_is_refused_not_zeroed():
    """A zero correction and a refusal are different answers.

    A refusal hands the plane back to the standing lane — its field if
    it has one, its {1, y} page-fraction residual if it has not.  A zero
    correction would REPLACE that residual with nothing, which is a
    silent regression on every plane the search had no opinion about.
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
    sites = fields.window_sites(ROW, GEOMETRY, window, {})
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
    assert int(complete.sum()) >= swim.MIN_OBJECTIVE_CELLS


def test_a_certified_neighbour_adds_cargo_labels_and_the_target_adds_none():
    window, local = _synthetic_window()
    streams = tuple(fact.stream_id for fact in ROW.streams)
    certificate = data.Certificate(
        page=PAGE, ty=0, tx=1, stream_id=streams[0],
        user_bits=np.zeros(ROW.streams[0].user_bits, np.uint8),
        source="tiles/scan")
    certificates = {(PAGE, 0, 1, streams[0]): certificate}
    bare = fields.window_sites(ROW, GEOMETRY, window, {})
    with_donor = fields.window_sites(ROW, GEOMETRY, window, certificates)
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
    window, _local = _synthetic_window()
    rows = _rows_for(window)
    builder = swim.offsets_builder({}, {0: window}, (None, None, None))
    assert builder(rows) is None, (
        "with no field and no fit the historical page-fraction residual "
        "must stay in charge, cell for cell")
    field = _h3_facts.plane_field(plane=2)
    standing = (None, None, field)
    expected = color_region.field_offsets(standing, rows.page_cells_yx)
    got = swim.offsets_builder({}, {0: window}, standing)(rows)
    assert np.array_equal(got[2], expected[2])


def test_a_refused_plane_carries_the_hint_and_nothing_else():
    window, _local = _synthetic_window()
    rows = _rows_for(window)
    field = _h3_facts.plane_field(plane=2)
    standing = (None, None, field)
    fit = swim.WindowFit(
        patch_ordinal=0, window=window,
        affines=(None, None, local_affine.Affine(
            translation=np.asarray((1.0, 0.0)), linear=np.zeros((2, 2)))),
        correlations=(0.0, 0.0, 0.9), log_likelihoods=(0.0, 0.0, 1.0),
        n_cells=1000, n_evaluations=100)
    got = swim.offsets_builder({0: fit}, {0: window}, standing)(rows)
    expected = color_region.field_offsets(standing, rows.page_cells_yx)
    assert got[0] is None and got[1] is None, (
        "a plane the search refused must not be moved off the lane's own "
        "reading of it")
    assert np.allclose(got[2] - expected[2], (1.0, 0.0))


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


def _subject(ty: int = 0, tx: int = 0, stream_id: str = "") -> tuple:
    return (PAGE, ty, tx, stream_id or ROW.streams[0].stream_id, PPC)


def _attempt_fact(stage: str, outcome: str) -> data.AttemptFact:
    return data.AttemptFact(
        page=PAGE, ty=0, tx=0, stream_id=ROW.streams[0].stream_id,
        stage=stage, outcome=outcome, n_informative=1000, n_iters=60,
        syndrome_ok=False, crc_ok=False, components=((CAPTURE_ID, 0),))


def test_the_descriptor_produces_only_attempts_and_certificates():
    assert swim.SWIM_DESCRIPTOR.name == "tiles.swim"
    assert swim.SWIM_DESCRIPTOR.subject_kind == "tile"
    assert swim.SWIM_DESCRIPTOR.born_by == (data.AttemptFact,)
    assert swim.SWIM_DESCRIPTOR.produces == (data.AttemptFact,
                                             data.Certificate)
    assert data.ColorEvidenceRow not in swim.SWIM_DESCRIPTOR.produces, (
        "the correction is transient: no standing evidence row, no "
        "standing context cell, no plane field")
    assert data.PlaneField not in swim.SWIM_DESCRIPTOR.produces


def test_the_row_is_the_dearest_in_the_tree_and_escalates():
    assert swim.SWIM_COST > local_ctx.LOCAL_COST
    assert swim.SWIM_COST > uplift.A4B_COST
    store = _color_engine()
    first = swim._swim_cost(store, _subject(), swim.STAGE_SWIM, 1, 0)
    third = swim._swim_cost(store, _subject(), swim.STAGE_SWIM, 3, 0)
    assert third == 3 * swim.SWIM_COST + (first - swim.SWIM_COST)
    assert swim._swim_cost(store, _subject(), swim.STAGE_SWIM, 0, 0) \
        == first, "a never-fired row is priced once, not at zero"


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
    subject = (PAGE, 0, 0, store.row.streams[0].stream_id, PPC)
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
    assert local_ctx._local_eligible(store, _subject()) is False, (
        "tiles.local needs a certified neighbour to have any label")
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
    assert swim._swim_retire(store, _subject()) is False
    store._ingest(data.Certificate(
        page=PAGE, ty=0, tx=0, stream_id=ROW.streams[0].stream_id,
        user_bits=np.zeros(ROW.streams[0].user_bits, np.uint8),
        source="tiles/scan"))
    assert swim._swim_eligible(store, _subject()) is False
    assert swim._swim_retire(store, _subject()) is True
    assert swim.prepare_swim(store, _subject(), swim.STAGE_SWIM) is None


def test_the_row_subscribes_to_the_fields_it_hints_from():
    store = _color_engine()
    store._ingest(_h3_facts.window(WID, ordinal=0))
    store._ingest(dataclasses.replace(
        _h3_facts.placement(WID),
        local_cells_yx=_h3_facts.tile_cells(SPAN_CELLS)))
    store._ingest(_h3_facts.color_row())
    families = {key[0] for key in swim._swim_reads(store, _subject())}
    assert "plane_field" in families, (
        "a new field is a better hint: the row must wake for one")
    assert families >= {"plane_field", "lane_poses", "color_row", "tile"}


def test_the_attempt_stage_is_a_heavy_one():
    assert tiles.STAGE_SWIM150 in tiles.HEAVY_STAGES
    assert tiles.max_iters_for(tiles.STAGE_SWIM150) \
        == tiles.RETRY_BP_MAX_ITERS

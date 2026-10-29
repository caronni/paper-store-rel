"""Unit pins for `tiles.planek` and the plane-isolation kernel.

Everything here is cheap and sim-free: the kernel's algebra, the row's
birth and eligibility gates, the standing-field consultation order, and
the transience law.  The existence proof — that the row certifies a tile
the ordinary colour path cannot — lives in
`test_h3_planek_existence.py`, which needs a rendered page.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import engine
from holo.receiver.data import (
    AttemptFact,
    Certificate,
    ColorEvidenceRow,
    PlaneField,
    WindowEvidence,
)
from holo.receiver.format import identity, tile_codec
from holo.receiver.lib import spectral
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import (calibrate, color_model, color_region,
                                   field_tiers, plane_k, tiles)
from holo.receiver.tests import _h3_fixture_geometry, _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_the_offset_grid_is_the_measured_one_and_leads_with_nominal`.

K_FORMAT_REF = "L:c2-r0700@3392x2368"
CMY7_FORMAT_REF = "L:c3-cmy7-p120-v0@2240x1536"
CMY8_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"

PPC = Fraction(6)
SUBJECT = (0, 3, 4, "Y", PPC)

SHIFT_GRID_SIZE = 17
MIX_SEED = 20260831
MIX_ROWS = 512


def _row(ref: str):
    return identity.resolve_format_ref(ref)


# --------------------------------------------------------------------
# the kernel
# --------------------------------------------------------------------


def _synthetic(seed: int = MIX_SEED, n_rows: int = MIX_ROWS):
    """A noise-free page of channel means from a known subtractive mix."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, (n_rows, 3)).astype(np.uint8)
    m0 = np.asarray((235.0, 232.0, 228.0))
    # column p is plane p's shift; the OFF-DIAGONALS are the whole
    # problem this row exists for (measured on paper: magenta darkens
    # blue by 60% of what yellow does)
    coef = np.asarray(((-74.0, -24.0, -10.0),
                       (-21.0, -74.0, -17.0),
                       (-14.0, -21.0, -73.0)))
    values = m0 + bits.astype(np.float64) @ coef.T
    return values, bits, coef, m0


def test_the_mixing_model_recovers_the_channel_by_plane_shifts():
    values, bits, coef, m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    assert mix.accepted and mix.reason == spectral.REASON_ACCEPTED
    assert mix.n_full_rows == MIX_ROWS
    assert np.allclose(mix.m0, m0, atol=1e-6)
    assert np.allclose(mix.coef, coef, atol=1e-6)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_subtraction_is_exact_where_the_siblings_are_proven(plane):
    """THE ARM'S SECOND RUNG, as algebra.

    Where a cell's two sibling bits are known, their modelled
    contribution is subtracted and the residual projected on the target
    plane's own shift — so on a noise-free page the readout IS the plane
    bit, whatever the crosstalk.  The measured battery values this rung
    at five times the yield of the projection alone.
    """
    values, bits, _coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    score = spectral.plane_score(mix, values, bits, known, plane,
                                 spectral.MODE_SUBTRACT)
    assert np.allclose(score, bits[:, plane].astype(np.float64), atol=1e-6)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_the_projection_annihilates_both_siblings_in_the_mean(plane):
    values, bits, coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    functional = mix.projections[:, plane]
    for sibling in spectral.siblings_of(plane):
        assert abs(float(functional @ coef[:, sibling])) < 1e-9
    assert float(functional @ coef[:, plane]) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_with_no_sibling_proof_subtract_falls_back_to_the_projection(plane):
    values, bits, _coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    blind = np.zeros_like(bits, bool)
    blind[:, plane] = True
    subtracted = spectral.plane_score(mix, values, bits, blind, plane,
                                      spectral.MODE_SUBTRACT)
    projected = spectral.plane_score(mix, values, bits, blind, plane,
                                     spectral.MODE_PROJECT)
    assert np.array_equal(subtracted, projected)


def test_a_starved_or_thin_population_refuses_rather_than_fitting_noise():
    values, bits, _coef, _m0 = _synthetic(n_rows=64)
    known = np.ones_like(bits, bool)
    assert spectral.fit_plane_mix(values, bits, known).reason == (
        spectral.REASON_FEW_ROWS)
    values, bits, _coef, _m0 = _synthetic()
    bits[:, 2] = 0
    values = np.asarray(values)
    known = np.ones_like(bits, bool)
    assert spectral.fit_plane_mix(values, bits, known).reason == (
        spectral.REASON_STARVED)


def test_an_unknown_readout_mode_is_refused_by_name():
    values, bits, _coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    with pytest.raises(ValueError, match="unknown mode"):
        spectral.plane_score(mix, values, bits, known, 2, "blue")


# --------------------------------------------------------------------
# the offset grid and the standing field
# --------------------------------------------------------------------


def test_the_offset_grid_is_the_measured_one_and_leads_with_nominal():
    grid = plane_k.shift_grid()
    _h3_support.assert_measured("planek offset grid size", len(grid),
                               SHIFT_GRID_SIZE)
    assert grid[0] == 0.0, (
        "nominal must be the first candidate so a tie keeps the pose the "
        "receiver committed rather than a neighbouring offset"
    )
    assert sorted(grid) == [
        round(plane_k.SHIFT_MIN_DOTS + index * plane_k.SHIFT_STEP_DOTS, 6)
        for index in range(SHIFT_GRID_SIZE)]
    assert min(grid) == plane_k.SHIFT_MIN_DOTS
    assert max(grid) == plane_k.SHIFT_MAX_DOTS


def _field(delta_dots: float, supported: bool,
           tiles_yx: tuple[int, int] = (4, 4)) -> PlaneField:
    delta = np.zeros((*tiles_yx, 2), np.float64)
    delta[..., 0] = delta_dots
    support = np.full(tiles_yx, 1.0 if supported else 0.0)
    return PlaneField(page=0, plane=2, delta_dots_xy=delta,
                      support=support,
                      uncertainty_dots=np.zeros(tiles_yx, np.float64),
                      n_observations=int(support.sum()), n_captures=1,
                      ordinal=1)


def _cells_of_tile(ty: int, tx: int) -> np.ndarray:
    ys = np.arange(ty * TILE_CELLS, (ty + 1) * TILE_CELLS)
    xs = np.arange(tx * TILE_CELLS, (tx + 1) * TILE_CELLS)
    grid = np.stack(np.meshgrid(ys, xs, indexing="ij"), axis=-1)
    return grid.reshape(-1, 2)


def test_no_solved_field_reads_exactly_zero_and_the_search_still_runs():
    """I6/I8: the field is always defined, and zero IS the pose.

    Before W3 an absent field returned None and that None was what
    switched the blind sweep on.  Now the sweep always runs and the
    field is only ever the point it is centred on, so an unsolved page
    reads zero and the sweep measures the whole correction itself.
    """
    delta = plane_k.field_delta_dots(None, _cells_of_tile(1, 1))
    assert delta.shape == (TILE_CELLS * TILE_CELLS, 2)
    assert np.all(delta == 0.0)


def test_a_tile_the_solve_left_at_zero_reads_the_pose():
    """I6: an unseen tile is zero, and zero is where the pose points.

    The smoother is what puts zero on a tile no evidence reached
    (`lib/plane_field`), so the reader has nothing to decide: it reads
    the grid, and a zero there means "sample where you were going to".
    """
    field = _field(0.0, supported=True)
    delta = plane_k.field_delta_dots(field, _cells_of_tile(1, 1))
    assert np.all(delta == 0.0)


def test_the_support_grid_no_longer_gates_the_read():
    """The retired rule, inverted (I8).

    The row used to refuse the whole field wherever ANY covered tile
    had zero support, so that its blind estimator stayed in charge over
    exactly the dead bands the estimator exists for.  There is nothing
    left to protect: the sweep is unconditional now, so what the solve
    published is what is read, support or none.
    """
    unsupported = _field(1.75, supported=False)
    assert np.allclose(
        plane_k.field_delta_dots(unsupported, _cells_of_tile(1, 1))[:, 0],
        1.75)
    partly = _field(1.75, supported=True)
    partly.support[1, 1] = 0.0
    assert np.allclose(
        plane_k.field_delta_dots(partly, _cells_of_tile(1, 1))[:, 0], 1.75)


def test_a_supported_field_carries_its_own_delta():
    field = _field(1.75, supported=True)
    delta = plane_k.field_delta_dots(field, _cells_of_tile(1, 1))
    assert delta.shape == (TILE_CELLS * TILE_CELLS, 2)
    assert np.allclose(delta[:, 0], 1.75)
    assert np.allclose(delta[:, 1], 0.0)


# --------------------------------------------------------------------
# the sweep, on a raster whose plane really is displaced
# --------------------------------------------------------------------

SWEEP_FORMAT_REF = "c3-cmy8-r0550@2x2"
#: 12 px per cell against a 3-dot cell puts 4 pixels on a printed dot,
#: so the injected 1.75 dots is exactly 7 pixels and the stimulus needs
#: no interpolation to build.
SWEEP_PPC = 12
SWEEP_MARGIN_PX = 24
SWEEP_SHIFT_DOTS = 1.75
SWEEP_PLANE = 2
SWEEP_PAPER = 240
SWEEP_INK = 60
SWEEP_SEED = 20260907


def _page_states(row, geometry):
    height, width = row.cells_yx
    cells = np.stack(np.meshgrid(np.arange(height), np.arange(width),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    states, _kinds = color_model.reference_states(row, geometry, 0, cells)
    rng = np.random.default_rng(SWEEP_SEED)
    full = np.where(states >= 0, states,
                    rng.integers(0, 8, states.size)).astype(np.uint8)
    return cells, states, full


def _displaced_page(row, full: np.ndarray, shift_dots: float, plane: int):
    """The page as pixels, with ONE plane's ink moved along page +x."""
    height, width = row.cells_yx
    bits = tile_codec.states_to_planes(full).reshape(height, width, 3)
    block = np.kron(bits.astype(np.uint8),
                    np.ones((SWEEP_PPC, SWEEP_PPC, 1), np.uint8))
    side_y = height * SWEEP_PPC + 2 * SWEEP_MARGIN_PX
    side_x = width * SWEEP_PPC + 2 * SWEEP_MARGIN_PX
    px_per_dot = SWEEP_PPC // color_region.cell_dots_of(row)
    planes = []
    for channel in range(3):
        raster = np.full((side_y, side_x), SWEEP_PAPER, np.uint8)
        raster[SWEEP_MARGIN_PX:SWEEP_MARGIN_PX + height * SWEEP_PPC,
               SWEEP_MARGIN_PX:SWEEP_MARGIN_PX + width * SWEEP_PPC] = (
            np.where(block[..., channel] > 0, SWEEP_INK, SWEEP_PAPER))
        if channel == plane:
            raster = np.roll(raster,
                             int(round(shift_dots * px_per_dot)), axis=1)
        planes.append(raster)
    return tuple(planes)


def _furniture_window(row, cells: np.ndarray, states: np.ndarray):
    """The page's own furniture as one window, composed by production.

    The sweep scores a window on the cells it can PROVE, and on a page
    with no certificate those are the format's furniture; handing the
    window exactly those cells is the same population one full-page
    window would score, at a thirtieth of the sampling.
    """
    height, width = row.cells_yx
    known = cells[states >= 0]
    placement = _h3_fixture_geometry.window_placement(
        ("cap", 0, 0, (0, 0, height, width)),
        _h3_fixture_geometry.page_native_affine(SWEEP_PPC,
                                                SWEEP_MARGIN_PX),
        known)
    return placement, _h3_fixture_geometry.window_pose(row, placement)


def _swept(field, row, geometry, window, placement, planes):
    """One window read at `field`, then the scalar sweep around it."""
    cell_dots = color_region.cell_dots_of(row)
    read, delta = plane_k.read_window(
        row, geometry, window, placement, 0, planes, cell_dots, {}, {},
        field, SWEEP_PLANE)
    mix = plane_k.fit_lane_mix((read,))
    assert mix.accepted, mix.reason
    return plane_k.choose_offset(mix, read, planes, cell_dots, delta,
                                 SWEEP_PLANE), delta


def test_the_sweep_is_centred_on_the_field_and_adds_what_it_missed():
    """The rule this phase inverts, on a raster that really is displaced.

    A page whose Y plane is printed 1.75 dots along page +x, read three
    ways.  With the page's own field standing at the truth the sweep
    CONFIRMS it — it runs, and it stays put.  With a field standing at
    1.0 the sweep adds the rest, which is exactly what the retired rule
    forbade: "the standing fit speaks first and this row does NOT
    search".  With no field at all it finds the displacement itself.

    RESOLUTION.  The objective is a held-out log loss over a box
    aperture 0.7 cells wide on a 3-dot cell, so on a noise-free page it
    has a flat basin and the argmin inside that basin is not a
    measurement.  W3a's first build read the argmin anyway and moved a
    field standing at the truth by half a dot; `plane_k.LOSS_TOLERANCE`
    (RULED 2026-09-08) makes that difference a tie, so the confirming
    arm below pins ZERO rather than a bracket.  What the tolerance is
    and is not, in measured numbers, is the next test.
    """
    row = identity.resolve_format_ref(SWEEP_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    cells, states, full = _page_states(row, geometry)
    planes = _displaced_page(row, full, SWEEP_SHIFT_DOTS, SWEEP_PLANE)
    placement, window = _furniture_window(row, cells, states)
    tiles_yx = row.tiles_yx

    standing, delta = _swept(_field(SWEEP_SHIFT_DOTS, True, tiles_yx), row,
                             geometry, window, placement, planes)
    assert np.allclose(delta[:, 0], SWEEP_SHIFT_DOTS)
    assert standing.offset_source == plane_k.SOURCE_FIELD_SEARCH
    assert standing.shift_dots == 0.0, (
        "a correct field must come back whole: nothing inside the "
        "objective's own resolution may displace it")

    short, _delta = _swept(_field(1.0, True, tiles_yx), row, geometry,
                           window, placement, planes)
    assert short.offset_source == plane_k.SOURCE_FIELD_SEARCH
    assert short.shift_dots > 0.0, (
        "a field that is short must be ADDED to, not obeyed")


    blind, zero = _swept(None, row, geometry, window, placement, planes)
    assert np.all(zero == 0.0)
    assert blind.offset_source == plane_k.SOURCE_SEARCH
    assert blind.shift_dots >= 1.0


def _field_xy(delta_x: float, delta_y: float,
              tiles_yx: tuple[int, int]) -> PlaneField:
    delta = np.zeros((*tiles_yx, 2), np.float64)
    delta[..., 0], delta[..., 1] = delta_x, delta_y
    return PlaneField(page=0, plane=2, delta_dots_xy=delta,
                      support=np.ones(tiles_yx),
                      uncertainty_dots=np.zeros(tiles_yx, np.float64),
                      n_observations=1, n_captures=1, ordinal=1)


def test_the_pose_is_a_candidate_beside_the_field_centred_grid():
    """RULED 2026-09-08 (R6): the sweep carries the zero-field candidate.

    The sweep reaches two dots either side of the field, and the field
    itself is bounded at what the tiers could measure — 3.49 dots on a
    c3 Y plane — so a field that is wrong by its whole bound at a tile
    no evidence reached takes the POSE out of the candidate set: every
    candidate on the grid then sits at least 1.49 dots off a page that
    is barely displaced at all.  With the pose scored last, this
    window's own held-out labels can send it back there, and say so in
    the ledger.  A CORRECT field is not displaced by it: the pose is a
    worse reading and loses on the objective, and a tie keeps the field
    because the pose is scored last.
    """
    row = identity.resolve_format_ref(SWEEP_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    cells, states, full = _page_states(row, geometry)
    placement, window = _furniture_window(row, cells, states)
    tiles_yx = row.tiles_yx

    reach = field_tiers.measurement_reach_dots(
        SWEEP_PLANE, color_region.cell_dots_of(row))
    assert reach - plane_k.SHIFT_MAX_DOTS > 0.0, (
        "the case only exists because the sweep is narrower than the "
        "field's own bound")
    registered = _displaced_page(row, full, 0.0, SWEEP_PLANE)
    astray, delta = _swept(_field_xy(reach, 0.0, tiles_yx), row, geometry,
                           window, placement, registered)
    assert np.allclose(delta[:, 0], reach)
    assert astray.offset_source == plane_k.SOURCE_POSE
    assert astray.shift_dots == 0.0

    displaced = _displaced_page(row, full, SWEEP_SHIFT_DOTS, SWEEP_PLANE)
    correct, _delta = _swept(_field(SWEEP_SHIFT_DOTS, True, tiles_yx), row,
                             geometry, window, placement, displaced)
    assert correct.offset_source == plane_k.SOURCE_FIELD_SEARCH


def test_the_parity_instrument_reads_the_rows_own_source_spellings():
    """The retired label, caught 2026-09-08 (W7).

    W3 replaced this row's single `"blind"` label with four constants
    and `measure/planek_parity.py` kept the literal in its report
    filter, so it selected nothing and every lane line of every parity
    report printed "mean blind offset +0.000 dots" as a measurement.
    Reading the constants puts the coupling under the instrument
    attribute-rot gate, which a string literal was invisible to.
    """
    sys.path.insert(0, str(_h3_support.WORKTREE_ROOT / "measure"))
    parity = pytest.importorskip("planek_parity")
    offsets = [{"patch": 0, "source": plane_k.SOURCE_FIELD_SEARCH,
                "shift_dots": 0.5},
               {"patch": 1, "source": plane_k.SOURCE_SEARCH,
                "shift_dots": 1.5},
               {"patch": 2, "source": plane_k.SOURCE_POSE,
                "shift_dots": 0.0},
               {"patch": 3, "source": "blind", "shift_dots": 99.0}]
    report = {"case": "c", "note": "n", "crop_tiles": 1,
              "wall_seconds": 1.0,
              "decode": dict.fromkeys(
                  ("certificates", "gt_exact", "wrong", "adds"), 0),
              "production": {"tiles": 1, "C": 1, "M": 1, "Y": 1},
              "gt_gate": {"tiles": 1, "cells": 1},
              "lanes": [{"capture": "cap", "level_index": 0, "poses": 1,
                         "windows": 1, "mix": {"plane_snr": [1.0]},
                         "offsets": offsets}]}
    line, = [text for text in parity.render([report], "one")
             if text.startswith("* cap")]
    assert "2 searched offsets averaging +1.000 dots" in line, line


#: The held-out log loss the sweep reads, per shift, on the stimulus
#: above — measured 2026-09-08 through `plane_k`'s own helpers.  The
#: numbers are what the RULING is about, and they are two worlds apart:
#: the best rival of a CORRECT field is better by 6.3e-12, and the best
#: rival of a field 0.75 dots short is better by 3.8e-2.  The tolerance
#: sits between them by ten orders of magnitude in both directions,
#: which is the whole claim that it is numerical equality and not a bar.
CORRECT_FIELD_RIVAL_GAIN = 1e-10
SHORT_FIELD_RIVAL_GAIN = 1e-2
#: MEASURED, and against the ruling's expectation: at half a dot short
#: the objective's own argmin is ALREADY the nominal shift, so nothing
#: is refused there and the tolerance is not what holds it.  The box
#: aperture is 0.7 cells = 2.1 dots wide on this format, so the basin is
#: about a dot across rather than the half-dot the review estimated.
#: The sweep's real discrimination on this stimulus lies between 0.5 and
#: 0.75 dots, and it is the OBJECTIVE's limit, not the tolerance's.
BASIN_HALF_WIDTH_DOTS = 0.5


def _loss_curve(field, row, geometry, window, placement, planes):
    """`{shift: held-out loss}` for one standing field, the sweep's own."""
    cell_dots = color_region.cell_dots_of(row)
    read, delta = plane_k.read_window(
        row, geometry, window, placement, 0, planes, cell_dots, {}, {},
        field, SWEEP_PLANE)
    mix = plane_k.fit_lane_mix((read,))
    assert mix.accepted, mix.reason
    extremes = [plane_k.offset_points(window, cell_dots, delta, shift)
                for shift in (plane_k.SHIFT_MIN_DOTS,
                              plane_k.SHIFT_MAX_DOTS, 0.0)]
    crops = plane_k.channel_crops(planes, extremes, window.pitch_px)
    curve: dict[float, float] = {}
    for shift in plane_k.shift_grid():
        points = plane_k.offset_points(window, cell_dots, delta, shift)
        values = plane_k.sample_channels(crops, points)
        loss = plane_k.heldout_loss_at(mix, read, values, SWEEP_PLANE)
        if loss is not None:
            curve[float(shift)] = float(loss)
    return curve


def test_the_tolerance_is_numerical_equality_and_not_a_bar():
    """The two gaps the ruling stands on, read off the objective.

    A tolerance is a bar if some real displacement is refused because of
    it.  Measured here: what the tolerance refuses is 1e-10 of log loss
    and what the sweep still accepts is 1e-2 of it — eight orders of
    magnitude of daylight, so no displacement this objective can resolve
    is being held back by 1e-6.

    What DOES hold half a dot back is the objective itself: with the
    field 0.5 dots short the nominal shift is already the argmin, before
    any tolerance is applied.  That is the aperture's basin and it is a
    limit of the measurement, which is worth having pinned because the
    tempting repair — lowering the tolerance — cannot touch it.
    """
    row = identity.resolve_format_ref(SWEEP_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    cells, states, full = _page_states(row, geometry)
    planes = _displaced_page(row, full, SWEEP_SHIFT_DOTS, SWEEP_PLANE)
    placement, window = _furniture_window(row, cells, states)
    tiles_yx = row.tiles_yx

    def gain(delta_dots: float) -> float:
        curve = _loss_curve(_field(delta_dots, True, tiles_yx), row,
                            geometry, window, placement, planes)
        return curve[0.0] - min(curve.values())

    correct = gain(SWEEP_SHIFT_DOTS)
    assert 0.0 <= correct < CORRECT_FIELD_RIVAL_GAIN < plane_k.LOSS_TOLERANCE
    short = gain(SWEEP_SHIFT_DOTS - 0.75)
    assert short > SHORT_FIELD_RIVAL_GAIN > plane_k.LOSS_TOLERANCE

    basin = _loss_curve(
        _field(SWEEP_SHIFT_DOTS - BASIN_HALF_WIDTH_DOTS, True, tiles_yx),
        row, geometry, window, placement, planes)
    assert min(basin, key=basin.__getitem__) == 0.0, (
        "half a dot short, the objective's own argmin is the nominal "
        "shift: the tolerance refuses nothing here and cannot be blamed "
        "for it")


def test_the_two_offsets_land_on_the_same_points_by_two_routes():
    """field + shift is one displacement, however it is spelled."""
    row = identity.resolve_format_ref(SWEEP_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    cells, states, _full = _page_states(row, geometry)
    _placement, window = _furniture_window(row, cells, states)
    cell_dots = color_region.cell_dots_of(row)
    field = _field(1.0, True, row.tiles_yx)
    delta = plane_k.field_delta_dots(field, window.page_cells_yx)
    both = plane_k.offset_points(window, cell_dots, delta, 0.75)
    whole = plane_k.offset_points(
        window, cell_dots, delta + np.asarray((0.75, 0.0)), 0.0)
    assert np.allclose(both, whole)
    nominal = plane_k.offset_points(
        window, cell_dots, np.zeros_like(delta), 0.0)
    assert np.allclose(nominal, window.scan_points_yx)


# --------------------------------------------------------------------
# admission: the whole declared candidate set
# --------------------------------------------------------------------

#: The edge stimulus, in the sweep's own units — SWEEP_PPC over a 3-dot
#: cell puts 4 pixels on a printed dot.  The page below is cropped FLUSH
#: with the raster, so a pose nudged 1.75 dots left takes its first
#: column off the scan (x from -1.0) and a field standing at twice that
#: less a hundredth carries the last column 1.96 px past the far edge.
#: What is left is the declared grid: -1.75 dots lands the read back on
#: the printed cells, and of the seventeen it is the one that reaches
#: deepest into the scan.
EDGE_NUDGE_DOTS = -1.75
EDGE_FIELD_DOTS = 3.49
EDGE_ADMITTED_DOTS = -1.75
#: The least-margin start of that same declared set: 1.24 dots off the
#: printed cells, and viable, which is the whole reason the order is not
#: the grid's.
EDGE_LEAST_MARGIN_DOTS = -0.5
#: MEASURED 2026-09-09 through this row's own helpers, and the review's
#: own number for its reproduction: the held-out log loss of the window
#: the row used to refuse outright.
EDGE_ADMITTED_LOSS = 0.003883500026397696
#: What the ORDER buys, measured on the pair in the last test: at the
#: deepest-in-the-scan start the healthy neighbour's held-out loss is
#: the one it has alone to thirteen digits; at the least-margin start of
#: the same set the lane mix is fitted through a read 1.24 dots off the
#: cells and that neighbour pays 1.565x.  (The review measured 2.33x on
#: its own construction; the direction is the claim, not the factor.)
#: The margin is a GEOMETRY proxy and on this stimulus it also picks the
#: most accurate start — the confound is named in the test's docstring.
LEAST_MARGIN_LOSS_RATIO = 1.5
#: A field wrong in Y by more than the whole page: the x-only sweep
#: cannot move it, so every declared shift is equally unusable and the
#: margins tie.
TIED_FIELD_Y_DOTS = 10.0


@pytest.fixture(scope="module")
def flush_page():
    """The sweep's registered page, cropped flush with its raster.

    The render margin comes off, so the page's own first and last
    columns are the scan's first and last, and any pose or field that
    points outward leaves it.  One stimulus for every admission case
    below; the window is the whole page, composed by production.
    """
    row = identity.resolve_format_ref(SWEEP_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    cells, _states, full = _page_states(row, geometry)
    margin = SWEEP_MARGIN_PX
    planes = tuple(image[margin:-margin, margin:-margin] for image in
                   _displaced_page(row, full, 0.0, SWEEP_PLANE))
    return SimpleNamespace(
        row=row, geometry=geometry, cells=cells, planes=planes,
        cell_dots=color_region.cell_dots_of(row),
        raster_shape_yx=(planes[0].shape[0], planes[0].shape[1]))


def _nudged_read(page, nudge_dots: float, field, ordinal: int = 0):
    """One whole-page window, its pose moved along page +x, read blind."""
    px_per_dot = SWEEP_PPC / page.cell_dots
    affine = list(_h3_fixture_geometry.page_native_affine(SWEEP_PPC, 0.0))
    affine[5] += nudge_dots * px_per_dot
    placement = _h3_fixture_geometry.window_placement(
        ("cap", 0, 0, (0, 0, *page.row.cells_yx)), tuple(affine), page.cells,
        patch_ordinal=ordinal)
    window = _h3_fixture_geometry.window_pose(page.row, placement)
    return plane_k.read_window(page.row, page.geometry, window, placement, 0,
                               page.planes, page.cell_dots, {}, {}, field,
                               SWEEP_PLANE), window


def _viable_shifts(page, window, delta: np.ndarray) -> list[float]:
    """The declared shifted starts that reach the raster, in order."""
    starts = plane_k.start_candidates(window, page.cell_dots, delta,
                                      page.raster_shape_yx)
    return [shift for _at, shift, _source in starts[2:]
            if calibrate.points_inside_raster(
                plane_k.offset_points(window, page.cell_dots, delta, shift),
                page.raster_shape_yx)]


def test_a_declared_shift_admits_the_window_both_first_choices_lost(
        flush_page):
    """R7 (RULED 2026-09-09): admission is the whole DECLARED set.

    The review's case.  On this flush raster the pose reaches x = -1.0
    and the field reaches 1536.96 of a 1536-wide scan, so neither
    initial choice can be read — and the row refused the window in
    front of its own sweep, whose -1.75 shift spans 5.96..1529.96 and
    fits an accepted mix on it.  Nothing here is a new candidate: the
    grid, the mixing fit and the objective are the ones the sweep was
    always going to use, and the search is now reachable.
    """
    found, _window = _nudged_read(
        flush_page, EDGE_NUDGE_DOTS,
        _field_xy(EDGE_FIELD_DOTS, 0.0, flush_page.row.tiles_yx))
    assert found is not None, (
        "both first choices leave the raster, and the declared shift "
        "that reaches it has to admit the window")
    read, _delta = found
    assert read.offset_source == plane_k.SOURCE_FIELD_SHIFT, (
        "an admission chosen by raster margin is not the sweep's answer "
        "and an operator counts the two apart")
    assert read.shift_dots == EDGE_ADMITTED_DOTS, (
        "the start is recorded as it was taken, never as 0.0")
    mix = plane_k.fit_lane_mix((read,))
    assert mix.accepted, mix.reason
    assert plane_k.heldout_loss_at(mix, read, read.values,
                                  SWEEP_PLANE) == pytest.approx(
        EDGE_ADMITTED_LOSS, rel=1e-9)


def test_the_pose_is_still_the_rescue_when_it_reaches_the_raster(flush_page):
    """R7 keeps W8 R-E's order: the pose is tried before any shift.

    The same field at the pose the composer actually committed.  The
    field carries the last column off the scan and the pose does not, so
    one candidate is spent, the window is kept, and the ledger goes on
    spelling this rescue apart from the sweep's PREFERENCE for the pose.
    """
    found, _window = _nudged_read(
        flush_page, 0.0,
        _field_xy(EDGE_FIELD_DOTS, 0.0, flush_page.row.tiles_yx))
    assert found is not None
    read, _delta = found
    assert read.offset_source == plane_k.SOURCE_POSE_ONLY
    assert read.shift_dots == 0.0


def test_a_field_that_reaches_the_raster_is_where_the_read_starts(flush_page):
    """The ordinary path, unmoved: the field is still the first choice."""
    found, _window = _nudged_read(
        flush_page, 0.0, _field(0.25, True, flush_page.row.tiles_yx))
    assert found is not None
    read, _delta = found
    assert read.offset_source == plane_k.SOURCE_FIELD
    assert read.shift_dots == 0.0


def test_no_declared_candidate_reaching_the_raster_is_still_a_refusal(
        flush_page):
    """The grid reaches two dots and no further.

    A window posed fifty dots off the scan is refused with a field
    standing exactly as it is without one: admission tries the declared
    set, and it does not enlarge it.
    """
    found, _window = _nudged_read(
        flush_page, -50.0,
        _field_xy(EDGE_FIELD_DOTS, 0.0, flush_page.row.tiles_yx))
    assert found is None


def test_with_no_field_standing_an_off_raster_pose_is_refused(flush_page):
    """The scope the lead kept narrow: the shifts are the FIELD's.

    With no field published there is nothing declared but the nominal
    pose, and the off-raster doctrine refuses it — here, one pixel out,
    where the -1.75 shift of the case above would have read the window.
    """
    found, _window = _nudged_read(flush_page, EDGE_NUDGE_DOTS, None)
    assert found is None


def test_the_shifts_are_ordered_by_raster_margin_and_ties_keep_the_grid(
        flush_page):
    """Deepest into the scan first, and deterministic.

    The margin is what one declared shift has over another before
    anything has been sampled, so it is the whole ordering; and the sort
    is stable, so a tie keeps `shift_grid`'s own order.  The margins are
    re-read here through `offset_points`, the route the READ takes, so
    the ordering's broadcast point grid is checked against the geometry
    it is ranking rather than against itself.  The tie is not
    hypothetical: a field wrong in y is a field the x-only sweep cannot
    move, and then every shift is equally unusable.
    """
    field = _field_xy(EDGE_FIELD_DOTS, 0.0, flush_page.row.tiles_yx)
    found, window = _nudged_read(flush_page, EDGE_NUDGE_DOTS, field)
    read, delta = found
    starts = plane_k.start_candidates(window, flush_page.cell_dots, delta,
                                      flush_page.raster_shape_yx)
    assert [source for _at, _shift, source in starts[:2]] == [
        plane_k.SOURCE_FIELD, plane_k.SOURCE_POSE_ONLY]
    shifts = [shift for _at, shift, _source in starts[2:]]
    margins = [plane_k.raster_margin_px(
        plane_k.offset_points(window, flush_page.cell_dots, delta, shift),
        flush_page.raster_shape_yx) for shift in shifts]
    assert margins == sorted(margins, reverse=True)
    assert shifts[0] == read.shift_dots == EDGE_ADMITTED_DOTS
    assert _viable_shifts(flush_page, window, delta)[-1] == (
        EDGE_LEAST_MARGIN_DOTS)

    astray = plane_k.field_delta_dots(
        _field_xy(0.0, -TIED_FIELD_Y_DOTS, flush_page.row.tiles_yx),
        window.page_cells_yx)
    tied = plane_k.start_candidates(window, flush_page.cell_dots, astray,
                                    flush_page.raster_shape_yx)
    assert [shift for _at, shift, _source in tied[2:]] == [
        shift for shift in plane_k.shift_grid() if shift != 0.0]


def test_the_admitted_start_leaves_a_healthy_neighbours_loss_alone(
        flush_page):
    """WHY THE ORDER IS THE MARGIN (R7).

    The mixing model is fitted over the WHOLE LANE from the values each
    window was admitted at, so a read admitted far off the printed cells
    is paid for by every other window on that lane.  Two whole-page
    windows of one capture under one standing field: the neighbour's
    pose is nudged so that the field lands it on the cells, and the
    other is the edge case above.  Admitted deepest into the scan, the
    neighbour's held-out loss is the one it has alone to thirteen
    digits; admitted at the least-margin start of the same declared set,
    it pays 1.565x for a lane-mate it never asked about.

    CONFOUNDED, and this pin says so rather than leaving it to be
    over-read: on this stimulus the deepest-in-the-scan shift is also
    the most ACCURATE one — the pose is nudged -1.75 dots and the field
    stands at +3.49, so the printed cells are a shift of -1.74 away from
    the field and the grid's nearest point to that is the admitted
    -1.75 — while the least-margin viable start sits 1.24 dots off those
    cells.  What is measured here is that an accurate start costs a
    lane-mate nothing and an off-cell one costs it half again as much.
    That the MARGIN is what finds the accurate start is a property of
    this construction, not a general claim: do not cite this test for
    the ordering protecting the mix on a stimulus where the two come
    apart.
    """
    field = _field_xy(EDGE_FIELD_DOTS, 0.0, flush_page.row.tiles_yx)
    (edge, delta), window = _nudged_read(flush_page, EDGE_NUDGE_DOTS, field)
    (healthy, _its_delta), _healthy_window = _nudged_read(
        flush_page, -EDGE_FIELD_DOTS, field, ordinal=1)
    assert healthy.offset_source == plane_k.SOURCE_FIELD, (
        "the neighbour's own pose plus this field is the truth, so it "
        "starts at the field like any ordinary window")
    alone = plane_k.fit_lane_mix((healthy,))
    base = plane_k.heldout_loss_at(alone, healthy, healthy.values,
                                  SWEEP_PLANE)
    admitted = plane_k.fit_lane_mix((healthy, edge))
    assert plane_k.heldout_loss_at(
        admitted, healthy, healthy.values, SWEEP_PLANE) == pytest.approx(
        base, rel=1e-12)

    least = _viable_shifts(flush_page, window, delta)[-1]
    points = plane_k.offset_points(window, flush_page.cell_dots, delta, least)
    crops = plane_k.channel_crops(flush_page.planes, (points,),
                                  window.pitch_px)
    worst = plane_k.fit_lane_mix(
        (healthy, replace(edge, shift_dots=least,
                          values=plane_k.sample_channels(crops, points))))
    assert plane_k.heldout_loss_at(worst, healthy, healthy.values,
                                   SWEEP_PLANE) > (
        LEAST_MARGIN_LOSS_RATIO * base)


# --------------------------------------------------------------------
# the transient decoder input
# --------------------------------------------------------------------


def _evidence(accepted: bool = True, n_cells: int = 8) -> WindowEvidence:
    cells = np.stack((np.zeros(n_cells, np.int64),
                      np.arange(n_cells, dtype=np.int64)), axis=1)
    return WindowEvidence(
        window_id=("cap", 0, 0, (0, 0, 128, 128)), capture_id="cap",
        level_index=0, region_index=0, patch_ordinal=0, page=0,
        page_cells_yx=cells, scores=np.zeros(n_cells, np.float32),
        reference_values=np.zeros(n_cells, np.int8),
        knots=np.zeros(0), probs=np.zeros(0), n_search=0,
        marginal_llr=np.arange(n_cells, dtype=np.float32),
        printed_llr=np.arange(n_cells, dtype=np.float32),
        accepted=accepted, refusal_reason="" if accepted else "starved",
        heldout_logloss=0.25 if accepted else None, ctx_adopted=False)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_only_the_target_plane_column_carries_evidence(plane):
    """0.0 IS the erasure spelling, and `tiles._attempt_stream` reads only
    the stream's own column, so a plane-isolated cut says nothing at all
    about the two planes it did not read."""
    read = SimpleNamespace(window=SimpleNamespace(patch_ordinal=0))
    row = plane_k.transient_row(read, _evidence(), (plane,), 3)
    assert row is not None
    assert np.array_equal(row.values[:, plane],
                          np.arange(8, dtype=np.float32))
    for other in spectral.siblings_of(plane):
        assert not np.any(row.values[:, other])


def test_a_refused_window_contributes_no_transient_row():
    read = SimpleNamespace(window=SimpleNamespace(patch_ordinal=0))
    assert plane_k.transient_row(read, _evidence(accepted=False), (2,),
                                 3) is None


def test_no_cut_means_no_attempt_and_no_fact():
    facts, events = plane_k.attempt_components(
        _row(CMY8_FORMAT_REF), None, (), "Y")
    assert facts == () and events == ()


# --------------------------------------------------------------------
# birth, eligibility, retirement, price
# --------------------------------------------------------------------


def _fact(stage: str = tiles.STAGE_RETRY150,
          outcome: str = tiles.OUTCOME_FAILED) -> AttemptFact:
    return AttemptFact(page=0, ty=3, tx=4, stream_id="Y", stage=stage,
                       outcome=outcome, n_informative=100, n_iters=150,
                       syndrome_ok=False, crc_ok=None,
                       components=(("cap", 0),))


def _store(ref: str, *, certified: frozenset = frozenset(),
           reach: tuple = ((3, 5),), color_rows: tuple = (("cap", 0, 0, 0),),
           ) -> SimpleNamespace:
    row = _row(ref)
    return SimpleNamespace(
        row=row,
        geometry=_h3_fixture_geometry.memoised_site_geometry(row),
        level=lambda capture_id, level_index: SimpleNamespace(ppc=PPC),
        cover_lanes=lambda page, ty, tx, ppc: (("cap", 0),),
        tile_cover=lambda key: ((), color_rows),
        evidence_reach=lambda wid: None,
        color_row_cover_tiles=lambda key: tuple(
            (0, ty, tx, "cap", 0) for ty, tx in reach),
        window_by_ordinal=lambda capture_id, level_index, ordinal: (
            capture_id, level_index, 0, (0, 0, 64, 64)),
        attempt_verdict=lambda *key: None,
        tile_lane_generation=lambda key: 0,
        union_generation=lambda page, ty, tx, ppc: 0,
        has_certificate=lambda key: key in certified,
        union_rung_ordinal=lambda ppc: 0)


@pytest.mark.parametrize("ref", (K_FORMAT_REF, CMY7_FORMAT_REF))
def test_the_row_is_never_born_on_k_or_cmy7(ref):
    """cmy7 has no per-plane codeword to decode — its base-7 packing is a
    JOINT symbol over three planes — and K has no siblings to cancel.
    The gate is at birth, so neither page ever carries a planek subject."""
    store = _store(ref)
    fact = _fact()
    assert plane_k._planek_subjects(store, fact) == ()


def test_a_failed_cmy8_attempt_is_what_gives_the_row_a_subject():
    store = _store(CMY8_FORMAT_REF)
    assert plane_k._planek_subjects(store, _fact()) == (SUBJECT,)


@pytest.mark.parametrize("stage,outcome", (
    (tiles.STAGE_SCAN, tiles.OUTCOME_CERTIFIED),
    (tiles.STAGE_PLANEK150, tiles.OUTCOME_FAILED),
    (tiles.STAGE_LOCAL150, tiles.OUTCOME_FAILED),
))
def test_the_row_does_not_arm_itself_or_follow_a_certificate(stage, outcome):
    store = _store(CMY8_FORMAT_REF)
    assert plane_k._planek_subjects(store, _fact(stage, outcome)) == ()


def test_eligibility_is_the_local_rows_shape():
    store = _store(CMY8_FORMAT_REF,
                   certified=frozenset({(0, 3, 5, "C")}))
    assert plane_k._planek_eligible(store, SUBJECT)
    assert not plane_k._planek_retire(store, SUBJECT)


def test_no_certified_material_in_reach_means_no_fire():
    """A RESIDUE ARM BY CONSTRUCTION, and the ablation says so: with the
    certified neighbours' labels gone the measured battery certifies
    zero on every crop, even though the isolated signal is no worse.  A
    PAVA map fitted on 120 format sites per tile cannot price 3,976
    payload cells."""
    store = _store(CMY8_FORMAT_REF)
    assert not plane_k._planek_eligible(store, SUBJECT)
    assert plane_k.prepare_planek(store, SUBJECT, plane_k.STAGE_PLANEK) \
        is None


def test_no_covering_colour_row_means_no_fire():
    store = _store(CMY8_FORMAT_REF, certified=frozenset({(0, 3, 5, "C")}),
                   color_rows=())
    assert not plane_k._planek_eligible(store, SUBJECT)
    assert plane_k.prepare_planek(store, SUBJECT, plane_k.STAGE_PLANEK) \
        is None


def test_a_certified_target_retires_the_subject_before_any_pixel():
    store = _store(CMY8_FORMAT_REF,
                   certified=frozenset({(0, 3, 4, "Y"), (0, 3, 5, "C")}))
    assert plane_k._planek_retire(store, SUBJECT)
    assert not plane_k._planek_eligible(store, SUBJECT)
    assert plane_k.prepare_planek(store, SUBJECT, plane_k.STAGE_PLANEK) \
        is None


@pytest.mark.parametrize("ref", (K_FORMAT_REF, CMY7_FORMAT_REF))
def test_prepare_refuses_on_k_or_cmy7_even_if_a_subject_is_handed_to_it(ref):
    store = _store(ref, certified=frozenset({(0, 3, 5, "main")}))
    subject = (0, 3, 4, _row(ref).streams[0].stream_id, PPC)
    assert plane_k.prepare_planek(store, subject,
                                  plane_k.STAGE_PLANEK) is None
    assert not plane_k._planek_eligible(store, subject)


def test_the_row_declares_the_reads_that_can_wake_it():
    store = _store(CMY8_FORMAT_REF)
    keys = plane_k._planek_reads(store, SUBJECT)
    kinds = {key[0] for key in keys}
    assert kinds == {"attempt", "pose_affine", "plane_field", "tile"}
    assert ("plane_field", 0, 2) in keys, (
        "the row consults the standing field of its PAGE, so a newly "
        "solved one must wake it")
    assert "color_row" not in kinds, (
        "the colour ROWS are `tiles.scan`'s reads: subscribing to them "
        "was this row routing around its own predecessor's verdict, "
        "and the verdict is a key of its own since 2026-09-21")
    assert {key for key in keys if key[0] == "attempt"} == {
        ("attempt", 0, SUBJECT[1], SUBJECT[2], SUBJECT[3], stage, lane)
        for stage, lane in (("scan", ("cap", 0)), ("union", PPC))}, (
        "the chain head's verdict per lane it could have been read on: "
        "scan is always single-lane, union always summed.  A retry150 "
        "failure ARMS this row but is no read (2026-10-03, S9): it "
        "follows a scan/union failure that already woke it, and its cut "
        "is not the one this row builds")


def test_the_row_prices_itself_above_every_other_residue_row():
    # ...except `tiles.swim` (240) and the two colds (250/260).  Swim
    # pays a whole local colour head fit plus a bounded per-plane
    # raster search; this row re-reads one plane and searches an
    # offset.  Both are last resorts among residue rows; cold is last
    # by price (PAGE-DOMAIN §6), not a residue row.  And except the cmy
    # retry (241, 2026-10-18): priced above swim's first fire on purpose,
    # it is a cmy-only stage of `tiles.retry` and never meets this row
    # on a cmy8 page.
    from holo.receiver.plugins import place, swim, tiles_sched

    store = _store(CMY8_FORMAT_REF)
    excluded = {(tiles_sched.PLUGIN_RETRY, tiles_sched.STAGE_RETRY_CMY)}
    prices = {(descriptor.name, stage): value
              for descriptor in engine.DESCRIPTORS
              for stage, value in descriptor.prices}
    assert plane_k.PLANEK_COST > max(
        price for (name, stage), price in prices.items()
        if name not in (plane_k.PLUGIN, swim.PLUGIN, "place")
        and (name, stage) not in excluded)
    assert swim.SWIM_COST > plane_k.PLANEK_COST
    assert place.STAGE_COST[place.STAGE_COLD_LIVE] > swim.SWIM_COST
    never = plane_k._planek_cost(store, SUBJECT, plane_k.STAGE_PLANEK, 0, 0)
    assert never == plane_k.PLANEK_COST
    third = plane_k._planek_cost(store, SUBJECT, plane_k.STAGE_PLANEK, 3, 0)
    assert third == never + 3 * plane_k.PLANEK_COST, (
        "the escalation door: nothing is capped, the row just drifts "
        "behind cheaper work by its base each time a growing frontier "
        "wakes it (base + base x earlier fires, 2026-10-18)")


def test_the_heavy_budget_is_the_one_the_tile_vocabulary_declares():
    assert plane_k.tiles.STAGE_PLANEK150 in tiles.HEAVY_STAGES
    assert tiles.max_iters_for(tiles.STAGE_PLANEK150) == (
        tiles.RETRY_BP_MAX_ITERS)


def test_the_descriptor_produces_only_transient_facts():
    descriptor = plane_k.PLANEK_DESCRIPTOR
    assert descriptor.produces == (AttemptFact, Certificate), (
        "the fits are built inside the job and dropped: no standing "
        "evidence row, no region context cell, no pose"
    )
    # the verdict, and the two evidence folds that move the cover (the
    # reach repair, 2026-10-03: they only RE-birth an armed subject)
    assert descriptor.born_by == (AttemptFact, WindowEvidence,
                                  ColorEvidenceRow)
    assert descriptor.subject_kind == "tile"

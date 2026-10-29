"""What a measurement of the page field is, and what it is not.

W8 charter §3, items 7-10, written BEFORE the build (R-G).  R-C is the
rule: a row is one measurement of one plane on one tile from one
capture — the displacement against the pose, a flag per axis saying
whether that axis was measured, a weight, a source — and NOTHING is
subtracted from it.  Two template sources remain, the certified pattern
of that plane and that plane's furniture; the blind tier is retired
because it publishes a field from noise (review F2), so a plane with no
template reads unknown rather than zero.

This module also owns `rows`, the builder the gauge and estimator
modules construct their evidence with: the table is the interface those
tests speak, so it has one builder and it lives beside the table.

Seeded from the review's `collector_counterexamples.py`,
`yellow_noise.py` and `estimator_counterexamples.py`.  The collector
fixtures come from `test_h3_plane_fields`, whose collector-internal
tests this suite supersedes; when that module goes its builders move to
`_h3_fixtures_field` and this import follows them.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from holo.receiver.lib import evidence, plane_field
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import color_region_anchor as anchor
from holo.receiver.plugins import field_tiers, fields, fields_collect
from holo.receiver.tests import _h3_fixture_geometry as geom
from holo.receiver.tests import _h3_support, test_h3_plane_fields as fx
from holo.receiver.tests.test_h3_field_lifecycle import (_collect_fact,
                                                         prior)

#: how many independent noise draws item 9 asks for; the fast lane takes
#: a subsample of them and the widened matrix takes all
NOISE_TRIALS = 20
NOISE_TRIALS_FAST = 4
NOISE_SEED = 20260908
NOISE_SIGMA = 0.1
NOISE_BLUR_PX = 2.0


def rows(delta_dots_xy: object, plane: object, *,
         measured_xy: object = None, weight: object = None,
         tile_code: object = 0, window: object = 0, capture: object = 0,
         page: int = 0, source: int = plane_field.SOURCE_ANCHOR,
         pose_generation: int = 1) -> evidence.Rows:
    """An evidence table from the columns a test cares about.

    Everything unstated is the ordinary case: both axes measured, unit
    weight, one window of one capture on page 0.  The columns that do
    vary are spelled at every call site, because they are what the test
    is about.
    """
    delta = np.atleast_2d(np.asarray(delta_dots_xy, np.float64))
    n = delta.shape[0]

    def column(value: object, dtype: object) -> np.ndarray:
        return np.broadcast_to(np.asarray(value, dtype), (n,)).copy()

    return evidence.Rows(
        capture=column(capture, np.int64), page=column(page, np.int64),
        tile_code=column(tile_code, np.int64),
        plane=column(plane, np.int64), delta_dots_xy=delta,
        measured_xy=(np.ones((n, 2), bool) if measured_xy is None
                     else np.atleast_2d(np.asarray(measured_xy, bool))),
        weight=column(1.0 if weight is None else weight, np.float64),
        source=column(source, np.int64), window=column(window, np.int64),
        pose_generation=column(pose_generation, np.int64))


def _certificates_of(*planes: int) -> dict:
    """The tile's certificates for SOME of its planes.

    A CMY8 certificate labels its own plane and no other
    (`plugins/color_sites.py`), so this is an ordinary state of a page
    being read — not a contrived one — and it is the state the field
    matters most in, before the page is finished.
    """
    whole = fx._tile_certificates(0, 0)
    keep = {fx.ROW.streams[plane].stream_id for plane in planes}
    return {key: value for key, value in whole.items()
            if value.stream_id in keep}


def _tile_rows(fact: object, plane: int, code: int = 0) -> np.ndarray:
    return ((np.asarray(fact.plane) == plane)
            & (np.asarray(fact.tile_code) == code))


# --------------------------------------------------------------------
# 7. a certified plane carries its own template
# --------------------------------------------------------------------

@pytest.mark.parametrize("certified", [(0,), (2,), (0, 1)])
def test_a_certified_plane_contributes_its_template_alone(certified):
    """Review F3: 3,976 authoritative cells per plane, discarded.

    The collector kept only the cells known in ALL THREE planes and
    refused the certified tier unless the whole tile had certified, so a
    certified C waited on M and Y before its 4,096 known cells counted —
    exactly backwards, since strong C and M measurements are what
    stabilises the frame Y is measured in.
    """
    fact = fx._collect(certificates=_certificates_of(*certified))
    for plane in certified:
        source = np.asarray(fact.source)[_tile_rows(fact, plane)]
        assert source.size, f"plane {plane} certified and not measured"
        assert (source == plane_field.SOURCE_CERTIFIED).all(), source


def test_the_certified_template_of_one_plane_covers_its_whole_tile():
    """The template builders are per (tile, PLANE), which is what makes
    the tier above reachable: C's certificate exposes every printed cell
    of C's tile, and says nothing at all about M and Y."""
    certificates = _certificates_of(0)
    certified = field_tiers.certified_template(
        fx.ROW, fx.GEOMETRY, fx.PAGE, (0, 0), 0, certificates)
    assert certified is not None
    assert len(certified.page_cells_yx) == TILE_CELLS ** 2
    assert field_tiers.certified_template(
        fx.ROW, fx.GEOMETRY, fx.PAGE, (0, 0), 2, certificates) is None
    furniture = field_tiers.furniture_template(
        fx.ROW, fx.GEOMETRY, fx.PAGE, (0, 0), 2)
    assert furniture is not None and len(furniture.page_cells_yx)


def test_a_tile_pays_once_per_plane_and_says_which_source_paid():
    """Design §2.5's third rule, in its W8 form: TWO sources, attributed
    per row, and never both for one (tile, plane).

    The three-way parity partition retires with the blind tier, and this
    is what survives it.  Measured on this tree, 2026-09-08: with C
    certified, Y publishes EIGHT rows over four tiles — an anchor row and
    a blind row for the same tile — so one tile's photons are counted
    twice and the second count is the tier R-C retires.  C, meanwhile,
    reads from furniture while its own 4,096 certified cells sit unused.
    """
    fact = fx._collect(certificates=_certificates_of(0))
    keys = list(zip(np.asarray(fact.plane).tolist(),
                    np.asarray(fact.tile_code).tolist()))
    assert len(keys) == len(set(keys)), (
        "a (tile, plane) paid twice: " + str(sorted(keys)))
    source = np.asarray(fact.source)
    assert (source[_tile_rows(fact, 0)]
            == plane_field.SOURCE_CERTIFIED).all()
    assert (source[_tile_rows(fact, 2)] == plane_field.SOURCE_ANCHOR).all()


# --------------------------------------------------------------------
# 8. an unmeasured axis
# --------------------------------------------------------------------

def test_a_row_with_one_axis_unmeasured_contributes_nothing_on_that_axis():
    """Review F8: unknown is not zero.

    A tier that swept only x knows nothing about y.  Writing its y as a
    zero with a positive weight makes it a measurement of "no
    displacement", which no tier made — and that fiction then pulls the
    y field toward zero and, before R-A, moved the gauge as well.

    THE WINDOW ALSO MEASURES ITS WORD PLANES, which the stimulus first
    written here did not (repaired at the W8 integration, measured):
    under R-A the window carries a free translation, so a constant seen
    by every window of a page IS that page's windows' pose error and
    item 12 requires it to be absorbed there — a lone Y row's 1.5 dots
    landed on the nuisance and the field read 3.5e-14, which is item 12
    passing, not this item failing.  C and M at zero on the same tile
    pin the translation through the gauge (`F_C = -F_M`, so both at
    zero forces the window's own translation to zero), and the swept x
    then reaches the field where this item can ask for it.  That is also
    the ordinary case on paper: a window that reads Y reads C and M too.
    """
    truth_x = 1.5
    swept = evidence.Rows.concat(
        rows([[truth_x, 9.0]] * 8, plane=2,
             measured_xy=[[True, False]] * 8),
        rows(np.zeros((8, 2)), plane=0), rows(np.zeros((8, 2)), plane=1))
    absent = rows(np.zeros((0, 2)), plane=2, measured_xy=np.zeros((0, 2)))
    at = prior(fx.CELL_DOTS)
    with_row = plane_field.solve(swept, fx.TILES_YX,
                                 cell_dots=fx.CELL_DOTS, prior=at)
    without = plane_field.solve(absent, fx.TILES_YX,
                                cell_dots=fx.CELL_DOTS, prior=at)
    assert np.allclose(with_row.delta_dots_xy[2, ..., 1],
                       without.delta_dots_xy[2, ..., 1])
    assert with_row.delta_dots_xy[2, 0, 0, 0] == pytest.approx(
        truth_x, abs=plane_field.FIELD_NOISE_DOTS)


# --------------------------------------------------------------------
# the primitive's own refusals, and its address
#
# `test_h3_field_tiers.py` was deleted whole with the blind tier (R-G)
# and took the site-count refusal's only pin with it; item 9 below
# exercises the QUALITY floor end to end and `test_h3_plane_fields`
# the saturation one, so this is the third of the three.
# --------------------------------------------------------------------

INK_PERIOD_DOTS = 8.0
TEMPLATE_CELLS = 8
TRUTH_DOTS_XY = (0.5, -0.25)


def _template_cells(side: int) -> np.ndarray:
    down, across = np.meshgrid(np.arange(side), np.arange(side),
                              indexing="ij")
    return np.stack((down.ravel(), across.ravel()), axis=1).astype(np.int64)


def _printed(cells_yx: np.ndarray, cell_dots: int,
             shift_dots_xy: tuple[float, float]) -> np.ndarray:
    """One plane's ink over the template's cells, displaced by a vector.

    Structure on BOTH axes, at a period the search grid resolves: a
    pattern that varied along x alone would leave the y peak flat and
    the primitive would be measured on half of what it does.  Ink is a
    printed bit and not a wave — the page prints what the template
    knows, so a candidate at the truth matches exactly and the peak is
    the primitive's own arithmetic rather than a phase.
    """
    wave = 2.0 * np.pi / INK_PERIOD_DOTS
    down = cells_yx[:, 0] * cell_dots - shift_dots_xy[1]
    across = cells_yx[:, 1] * cell_dots - shift_dots_xy[0]
    return (np.sin(wave * across) + np.sin(wave * down)
            > 0.0).astype(np.float64)


def _sampler(cells_yx: np.ndarray, cell_dots: int,
             truth_dots_xy: tuple[float, float]) -> tuple[object, list]:
    """The page under the template, read at each candidate offset.

    Ink reads dark, so the value is the negated pattern; the list beside
    it counts the calls, which is how a refusal that never scores is
    told from one that scores and rejects.
    """
    calls: list[int] = []

    def sample(offsets: np.ndarray) -> np.ndarray:
        calls.append(int(np.asarray(offsets).shape[0]))
        return -np.stack([
            _printed(cells_yx, cell_dots,
                     (truth_dots_xy[0] - float(offset[0]),
                      truth_dots_xy[1] - float(offset[1])))
            for offset in np.asarray(offsets, np.float64)])

    return sample, calls


def _measure_template(bits: np.ndarray, cells_yx: np.ndarray,
                      cell_dots: int = 2) -> tuple[object, list]:
    template = field_tiers.Template(
        page_cells_yx=cells_yx, bits=bits,
        source=plane_field.SOURCE_ANCHOR,
        radius_dots=field_tiers.ANCHOR_RADIUS_DOTS[2])
    sample, calls = _sampler(cells_yx, cell_dots, TRUTH_DOTS_XY)
    return field_tiers.measure(template, sample), calls


def test_the_primitive_measures_both_axes_of_a_template_it_admits():
    """The control the two refusals below are worth anything against."""
    cells = _template_cells(TEMPLATE_CELLS)
    measured, calls = _measure_template(_printed(cells, 2, (0.0, 0.0)),
                                        cells)
    assert measured is not None and calls
    assert measured.measured_xy.all()
    assert measured.delta_dots_xy == pytest.approx(
        TRUTH_DOTS_XY, abs=field_tiers.ANCHOR_STEP_DOTS)


@pytest.mark.parametrize("case", ["too few sites", "one-sided",
                                  "every cell printed", "no cell printed"])
def test_a_template_that_cannot_localize_never_scores(case):
    """`ANCHOR_MIN_SITES` and `ANCHOR_MIN_PER_CLASS`, which a cut scrap
    reaches routinely: Y carries no word ink on this format, so its
    polarity comes from a tile's dust and two sites of it is a peak, not
    a measurement (a 32-site template with one minority site returns
    0.47 dots of error at HIGHER quality than a balanced one, W7).

    NO refusal may cost a correlation: they are asked of the template
    alone, before the page is ever sampled.  The two CONSTANT templates
    are review R11 — a template with every cell printed or none of them
    has nothing of the other polarity, and `minority_class` said the
    opposite of exactly that one, counting all 64 of a constant
    template's sites as minority sites because its min and its max are
    the same value.  So it passed this gate, paid for a 441-candidate
    sweep, and was refused by the NCC at the far end.  A whole plane of
    a tile printed solid is not exotic (a dead plane, a suppressed
    tile): what it is, is unlocalizable.
    """
    cells = _template_cells(TEMPLATE_CELLS)
    bits = _printed(cells, 2, (0.0, 0.0))
    if case == "too few sites":
        keep = field_tiers.ANCHOR_MIN_SITES - 1
        cells, bits = cells[:keep], bits[:keep]
        assert field_tiers.minority_class(bits) >= \
            field_tiers.ANCHOR_MIN_PER_CLASS
    elif case == "one-sided":
        bits = np.zeros(cells.shape[0], np.float64)
        bits[:field_tiers.ANCHOR_MIN_PER_CLASS - 1] = 1.0
        assert bits.size >= field_tiers.ANCHOR_MIN_SITES
    else:
        bits = np.full(cells.shape[0],
                       float(case == "every cell printed"), np.float64)
        assert bits.size == TEMPLATE_CELLS ** 2 > field_tiers.ANCHOR_MIN_SITES
        assert field_tiers.minority_class(bits) == 0
    measured, calls = _measure_template(bits, cells)
    assert measured is None
    assert not calls, "a template that cannot localize scored anyway"


def test_a_row_is_keyed_to_the_tile_whose_cells_it_measured():
    """The address a measurement carries and the address a reader
    evaluates at are the same one: row-major over the page's tile grid.

    Both directions, on a page that is not square, because the failure
    this refuses is a transposition that reads perfectly consistently on
    a square grid and puts every measurement of a 53x37 page on the
    wrong tile.  The value is not asked of the SOLVE here: a page this
    small is inside the prior's own fade length end to end, so one
    measurement lifts every tile of it (0.80-0.81 dots of an injected
    1.0 measured 2026-09-08), and where the evidence LANDED is the
    support grid's answer, exactly.
    """
    tiles_yx = (5, 7)
    ty, tx = 3, 2
    centre = np.array([[ty * TILE_CELLS + TILE_CELLS // 2,
                        tx * TILE_CELLS + TILE_CELLS // 2]], np.int64)
    code = plane_field.tile_codes(centre, tiles_yx, TILE_CELLS)
    assert code.tolist() == [ty * tiles_yx[1] + tx]

    solution = plane_field.solve(
        rows([[1.0, 0.0]], plane=2, tile_code=code), tiles_yx,
        cell_dots=fx.CELL_DOTS, prior=prior(fx.CELL_DOTS))
    landed = np.asarray(solution.support)[2] > 0.0
    assert list(zip(*np.nonzero(landed))) == [(ty, tx)]

    grid = np.zeros(tiles_yx + (2,), np.float64)
    grid[..., 0] = np.arange(tiles_yx[0] * tiles_yx[1]).reshape(tiles_yx)
    assert plane_field.evaluate(grid, centre, TILE_CELLS)[0, 0] == \
        pytest.approx(float(code[0]))


@pytest.mark.parametrize("code", [-1, 5 * 7])
def test_a_tile_code_outside_the_page_is_refused_where_it_enters(code):
    """A negative code indexes from the far edge and an over-large one
    raises a bare numpy error deep in the fit; either way the page's own
    grid is what says so."""
    with pytest.raises(ValueError):
        plane_field.solve(rows([[1.0, 0.0]], plane=2, tile_code=code),
                          (5, 7), cell_dots=fx.CELL_DOTS,
                          prior=prior(fx.CELL_DOTS))


# --------------------------------------------------------------------
# what a measurement is a function of: the OWNING window, and the
# sampler it reads its plane through
# --------------------------------------------------------------------

OWNER_PITCH_PX = 5.0
#: 0.7 * 5.0 is 3.5 EXACTLY, so an owner at that pitch sits on the
#: aperture's own rounding boundary and the smallest neighbour moves it:
#: the lane median 4.999 rounds the 0.7-cell box down to 3 px where the
#: owner's own pitch keeps 4.  A real operating point, and the case the
#: external review reproduced (R4).
NEIGHBOUR_PITCH_PX = 4.998


def _exact_rows(fact: object) -> dict:
    """Every row of a collection, keyed by (tile, plane), bit for bit.

    `_table`'s nine decimals are for reading; the memo's premise is
    bit-exactness, so the deltas are compared as their own bytes.  Every
    published column of a row is here: what the memo carries is the whole
    row, so a comparison that skipped one could not see it move.
    """
    return {(int(code), int(plane)):
            (int(source), float(weight),
             np.asarray(delta, np.float64).tobytes(),
             tuple(bool(axis) for axis in measured))
            for code, plane, source, weight, delta, measured in zip(
                fact.tile_code, fact.plane, fact.source, fact.weight,
                np.asarray(fact.delta_dots_xy), np.asarray(fact.measured_xy))}


def test_a_neighbour_window_cannot_change_what_the_owner_measures(
        monkeypatch):
    """I9's premise: a row is a function of ONE window's pose, raster and
    template, so re-measuring it must return the number that was carried.

    The collection used to preprocess at the LANE's median pitch.  Every
    input of the owner stands still, a window that owns nothing joins the
    lane at 4.998 px/cell, and the owner's 0.7-cell aperture moves from 4
    px to 3 px — so an incremental collection carried rows measured
    through the old filter beside rows measured through the new one, and
    a fresh collection from identical inputs disagreed with it by up to
    0.67 dots (review R4, 0.181 dots C/M and 0.124 Y after solving).
    Deriving the preprocessing from the owning window makes the two
    agree, and it is the accurate one of the pair here: the certified C
    of tile 0, printed in register, reads (0.0003, -0.0005) dots through
    the owner's own aperture and (-0.291, -0.291) through the lane's.

    The certificate is what makes this a MIXED collection — C's template
    at tile 0 is new work while every other row is carried — which is
    the state the defect needed and the ordinary state of a page being
    read.
    """
    monkeypatch.setattr(fx, "PITCH_PX", OWNER_PITCH_PX)
    monkeypatch.setattr(fx, "_RENDERS", {})
    window = fx._window()
    neighbour = geom.window_pose(fx.ROW, geom.window_placement(
        fx.WID_B, geom.page_native_affine(NEIGHBOUR_PITCH_PX, 0.0),
        window.local_cells_yx))
    pooled_pitch_px = float(np.median((window.pitch_px, neighbour.pitch_px)))
    assert round(anchor.APERTURE_CELLS * window.pitch_px) != round(
        anchor.APERTURE_CELLS * pooled_pitch_px), (
        "the stimulus no longer crosses an aperture rounding boundary")

    certified = _certificates_of(0)
    planes = fx._render(window, 0, (0.0, 1.0), certified)
    alone = fields_collect.LaneWindows(
        level_index=0, ppc=4.0, windows=(window,), window_ids=(fx.WID,),
        pose_generation=(1,), planes=planes)
    joined = dataclasses.replace(
        alone, windows=(window, neighbour),
        window_ids=(fx.WID, fx.WID_B), pose_generation=(1, 0))
    standing = fx._collect(lanes=(alone,), revision=1)
    warm = fx._collect(lanes=(joined,), certificates=certified,
                       standing=standing, revision=2)
    cold = fx._collect(lanes=(joined,), certificates=certified,
                       standing=None, revision=2)

    assert warm.window_ids == cold.window_ids == (fx.WID,), (
        "the neighbour owns a tile, so this no longer tests a non-owner")
    incremental, fresh = _exact_rows(warm), _exact_rows(cold)
    assert incremental and incremental == fresh
    moved = {key for key, row in incremental.items()
             if _exact_rows(standing)[key] != row}
    assert moved == {(0, 0)}, (
        "only the (tile, plane) whose template changed may be re-measured")
    assert incremental[(0, 0)][0] == plane_field.SOURCE_CERTIFIED


def test_the_sampler_reads_one_plane_and_reads_it_whole(monkeypatch):
    """R10: the collection wanted one channel and interpolated three.

    `anchor.sample_plane` is the three-channel sampler's own arithmetic
    on one channel — the same crop-origin subtraction, the same order-1
    nearest-edge interpolation, the same float64 — so this is a cost
    change and not a measurement change, and both ends are pinned: the
    values, at the crop's edges and outside them where `mode="nearest"`
    decides, and the collection those values become.
    """
    rng = np.random.default_rng(20260912)
    filtered = rng.random((40, 50, 3), dtype=np.float32)
    y0, x0 = 7, 11
    inside = rng.uniform((y0, x0), (y0 + 39, x0 + 49), (200, 2))
    outside = np.asarray(
        ((y0, x0), (y0 + 39, x0 + 49), (y0 - 5.5, x0 + 12.25),
         (y0 + 44.5, x0 - 3.75), (y0 + 0.5, x0 + 49.5)), np.float64)
    points = np.concatenate((inside, outside))
    three = anchor.sample_rgb(filtered, y0, x0, points)
    for plane in range(3):
        assert np.array_equal(
            anchor.sample_plane(filtered, y0, x0, points, plane),
            three[:, plane])

    one_channel = _exact_rows(fx._collect())
    monkeypatch.setattr(
        anchor, "sample_plane",
        lambda filtered, y0, x0, points_yx, plane: anchor.sample_rgb(
            filtered, y0, x0, points_yx)[:, plane])
    assert one_channel and one_channel == _exact_rows(fx._collect())


# --------------------------------------------------------------------
# 9. a plane that carries no signal
# --------------------------------------------------------------------

def _noise_raster(trial: int) -> object:
    """One draw of the Y plane, keyed by its own trial number.

    Keyed rather than drawn from a running generator so that the fast
    lane's four rasters are literally four of the widened matrix's
    twenty: a subsample that consumed the same generator would make the
    two lanes exercise different stimuli, and a failure in one would not
    reproduce in the other.
    """
    size = int(fx.SPAN_CELLS * fx.PITCH_PX)
    rng = np.random.default_rng((NOISE_SEED, trial))
    return fx._Raster(0.5 + ndimage.gaussian_filter(
        rng.normal(0, NOISE_SIGMA, (size, size)).astype(np.float32),
        NOISE_BLUR_PX))


def test_a_noise_plane_publishes_no_evidence_and_solves_to_unknown():
    """Review F2, through the production collector and the real solve.

    C and M are printed and registered; only Y is replaced, by a smooth
    random field with no cells in it.  Every anchor call on Y is refused
    — and before R-C the blind tier accepted anyway, in 11 of 20 draws,
    publishing corrections up to 1.875 dots and reaching tiles nobody
    had observed.  A plane with no template has to read UNKNOWN.

    The collector runs BEFORE the prior is built, so the first thing this
    test can fail on is F2 itself and not a name the build has yet to
    write.
    """
    trials = _h3_support.subsample(np.random.default_rng(NOISE_SEED),
                                   range(NOISE_TRIALS), NOISE_TRIALS_FAST)
    for trial in trials:
        store = fx._placed_store({})
        store._planes_by_lane[(fx.CAPTURE_ID, 0)]["b"] = _noise_raster(trial)
        fact = _collect_fact(store)
        assert not np.any(np.asarray(fact.plane) == 2), (
            f"trial {trial}: a plane of pure noise published a measurement")
        assert set(np.asarray(fact.source).tolist()) <= {
            plane_field.SOURCE_CERTIFIED, plane_field.SOURCE_ANCHOR}
        store._fold(fact)
        table, _captures = fields.page_observations(store, fx.PAGE)
        solution = plane_field.solve(table, fx.TILES_YX,
                                     cell_dots=fx.CELL_DOTS,
                                     prior=prior(fx.CELL_DOTS))
        assert not solution.plane_known[2]
        assert not np.any(solution.delta_dots_xy[2])


# --------------------------------------------------------------------
# 10. the identity gate (built at W7b; the charter keeps its pin)
# --------------------------------------------------------------------

def test_the_identity_gate_refuses_a_mismatched_seed_before_any_raster():
    """The harness will not replay a page under a seed it was not
    decoded under, and it decides that from the run's own `RunOpen`
    before it opens anything — the sheet-J incident's gate (design §7).

    Kept as written and re-stated here because this suite is where the
    evidence boundary's rules live; the harness's own self-check
    (`measure/page_field/estimate.self_check`) stays the instrument's.
    """
    from measure.page_field import estimate

    printed = estimate.Archive("extract", Path("sheet-J"),
                               {"format_id": "c2-cmy8-r0547@53x37",
                                "attested_by": "the suite"})
    estimate.check_identity(printed, "L:c2-cmy8-r0547@53x37")
    with pytest.raises(ValueError):
        estimate.check_identity(printed, "c2-cmy8-r0547@53x37")
    with pytest.raises(ValueError):
        estimate.check_identity(
            estimate.Archive("extract", Path("nowhere"), None),
            "L:c2-cmy8-r0547@53x37")


def test_the_whole_harness_refuses_before_it_opens_a_scan(tmp_path):
    """The gate's other half, which is why it is a GATE: `estimate` puts
    it before everything, so a refused replay opens no raster.

    Driven through the whole entry point with a scan path that does not
    exist: if the gate ever moved below the intake, this would raise on
    the missing file instead, and the error would not name the two seeds.
    """
    from measure.page_field import estimate

    scan = tmp_path / "no-such-scan.tiff"
    declared = "L:c2-cmy8-r0700-p120-x1@3392x2368"
    with pytest.raises(ValueError) as refusal:
        estimate.estimate(
            estimate.Declaration(scans=(scan,), dpis=(2400.0,),
                                 format_ref=declared, max_pages=None),
            estimate.Archive("extract", Path("sheet-J"),
                             {"format_id": "c2-cmy8-r0547@53x37",
                              "attested_by": "the suite"}),
            (), tmp_path / "out")
    assert "seed" in str(refusal.value)
    assert not scan.exists() and not (tmp_path / "out").exists()

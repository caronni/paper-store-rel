from __future__ import annotations

from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage

from holo3 import data
from holo3.format.identity import resolve_format_ref
from holo3.lib import geometry
from holo3.plugins import calibrate, color_region, pose, refine
from holo3.tests import _h3_support

CELL_CENTRE_OFFSET = 0.5

BLOCK_PITCH_PX = 6
BLOCK_ORIGIN_YX = (100, 200)
BLOCK_CELLS_YX = (9, 11)
BLOCK_AFFINE = (6.0, 0.0, 100.0, 0.0, 6.0, 200.0)

GOLDEN_CELLS = np.asarray([[0, 0], [1, 2], [7, 5]], np.int64)
GOLDEN_POINTS = np.asarray(
    [[103.0, 203.0], [109.0, 215.0], [145.0, 233.0]], np.float64)

SHEARED_AFFINE = (12.03, 0.021, 5000.0, -0.019, 12.05, 4000.0)
SHEARED_CELLS = np.asarray([[0, 0], [1, 0], [0, 1], [40, 64]], np.int64)

AGREEMENT_TOL_PX = 1e-9
HALF_CELL_SIGNATURE_PX = 6.0

LEVEL_SCALES = (Fraction(1), Fraction(2), Fraction(3), Fraction(4),
                Fraction(7, 3), Fraction(5, 2))
# measured under env314t 2026-08-29: rescale_pixels round-trips through
# Fraction(float(term)), so only the integer rungs are bit-exact; the
# fractional rungs land within 2 ulp and their exactness moves with the
# window corner, so exactness is asserted for the integer rungs alone
ROUND_TRIP_ULP_BAR_PX = 1e-11

COLOR_FOSSIL = "L:c3-cmy7-p120-v0@2240x1536"


def _block_raster() -> tuple[np.ndarray, np.ndarray]:
    cells_y, cells_x = BLOCK_CELLS_YX
    values = (np.arange(cells_y * cells_x, dtype=np.float32) + 1.0).reshape(
        cells_y, cells_x)
    height = BLOCK_ORIGIN_YX[0] + BLOCK_PITCH_PX * (cells_y + 2)
    width = BLOCK_ORIGIN_YX[1] + BLOCK_PITCH_PX * (cells_x + 2)
    raster = np.zeros((height, width), np.float32)
    for cell_y in range(cells_y):
        for cell_x in range(cells_x):
            y0 = BLOCK_ORIGIN_YX[0] + BLOCK_PITCH_PX * cell_y
            x0 = BLOCK_ORIGIN_YX[1] + BLOCK_PITCH_PX * cell_x
            raster[y0:y0 + BLOCK_PITCH_PX,
                   x0:x0 + BLOCK_PITCH_PX] = values[cell_y, cell_x]
    return raster, values


def _all_block_cells() -> np.ndarray:
    cells_y, cells_x = BLOCK_CELLS_YX
    grid = np.stack(np.meshgrid(np.arange(cells_y), np.arange(cells_x),
                                indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def _sample(raster: np.ndarray, points_yx: np.ndarray) -> np.ndarray:
    return np.asarray(ndimage.map_coordinates(
        raster, np.asarray(points_yx, np.float64).T, order=1, cval=0.0))


def _shifted_points(affine: tuple[float, ...], frame: Fraction,
                    cells_yx: np.ndarray, offset: float) -> np.ndarray:
    terms = geometry.compose_from_native(tuple(affine), frame)
    matrix = np.asarray(terms, np.float64).reshape(2, 3)
    cells = np.asarray(cells_yx, np.float64) + offset
    return cells @ matrix[:, :2].T + matrix[:, 2]


def test_scan_points_yx_is_the_cell_centre_convention_golden():
    points = calibrate.scan_points_yx(
        BLOCK_AFFINE, Fraction(1), GOLDEN_CELLS)
    assert points.dtype == np.float64
    _h3_support.assert_golden("scan_points_yx cell-centre golden",
                              points.tolist(), GOLDEN_POINTS.tolist())


def test_scan_points_yx_adds_exactly_half_a_cell_on_a_sheared_affine():
    points = calibrate.scan_points_yx(
        SHEARED_AFFINE, Fraction(1), SHEARED_CELLS)
    expected = _shifted_points(SHEARED_AFFINE, Fraction(1), SHEARED_CELLS,
                               CELL_CENTRE_OFFSET)
    assert np.array_equal(points, expected)


def test_scan_points_yx_reads_every_cells_own_block_value():
    raster, values = _block_raster()
    cells = _all_block_cells()
    points = calibrate.scan_points_yx(BLOCK_AFFINE, Fraction(1), cells)
    read = _sample(raster, points)
    assert np.array_equal(read, values[cells[:, 0], cells[:, 1]])


@pytest.mark.parametrize(
    "offset,cell_shift",
    [(-0.5, -1), (0.5, 0), (1.5, 1)])
def test_a_half_cell_shifted_sampler_reads_the_neighbouring_cell(
        offset, cell_shift):
    raster, values = _block_raster()
    cells_y, cells_x = BLOCK_CELLS_YX
    interior = _all_block_cells()
    interior = interior[(interior[:, 0] + cell_shift >= 0)
                        & (interior[:, 0] + cell_shift < cells_y)
                        & (interior[:, 1] + cell_shift >= 0)
                        & (interior[:, 1] + cell_shift < cells_x)]
    read = _sample(raster, _shifted_points(
        BLOCK_AFFINE, Fraction(1), interior, offset))
    expected = values[interior[:, 0] + cell_shift,
                      interior[:, 1] + cell_shift]
    assert np.array_equal(read, expected)
    own = values[interior[:, 0], interior[:, 1]]
    assert (cell_shift == 0) is bool(np.array_equal(read, own))


def test_scan_points_yx_offsets_px_arm_is_purely_additive():
    rng = np.random.default_rng(20260829)
    cells = _all_block_cells()
    offsets = rng.normal(0.0, 2.0, size=(cells.shape[0], 2))
    base = calibrate.scan_points_yx(SHEARED_AFFINE, Fraction(2), cells)
    with_offsets = calibrate.scan_points_yx(
        SHEARED_AFFINE, Fraction(2), cells, offsets)
    assert np.array_equal(with_offsets, base + offsets)


@pytest.mark.parametrize("scale", LEVEL_SCALES)
def test_local_segment_then_native_terms_returns_the_input_affine(scale):
    cells = _all_block_cells() + np.asarray((37, 91), np.int64)
    local_pose, _local = refine.local_segment(SHEARED_AFFINE, scale, cells)
    recovered = refine.native_terms(local_pose, cells, scale)
    exact = recovered == tuple(float(term) for term in SHEARED_AFFINE)
    if scale.denominator == 1:
        assert exact, recovered
    assert max(abs(a - b) for a, b in zip(recovered, SHEARED_AFFINE,
                                          strict=True)) <= (
        ROUND_TRIP_ULP_BAR_PX)


def test_a_half_cell_shift_survives_the_native_terms_round_trip():
    scale = Fraction(1)
    cells = _all_block_cells() + np.asarray((37, 91), np.int64)
    local_pose, _local = refine.local_segment(SHEARED_AFFINE, scale, cells)
    linear = local_pose.matrix()
    slipped = refine.LocalPose(
        origin_yx=tuple(np.asarray(local_pose.origin_yx, np.float64)
                        + linear @ np.full(2, 0.5)),
        jacobian_yx=local_pose.jacobian_yx,
        phase_yx=local_pose.phase_yx, pitch_px=local_pose.pitch_px,
        angle_deg=local_pose.angle_deg)
    recovered = refine.native_terms(slipped, cells, scale)
    drift = max(abs(a - b) for a, b in zip(recovered, SHEARED_AFFINE,
                                           strict=True))
    assert drift == pytest.approx(HALF_CELL_SIGNATURE_PX, abs=0.05)


@pytest.mark.parametrize("scale", LEVEL_SCALES)
def test_local_pose_points_agree_with_scan_points_yx(scale):
    cells = _all_block_cells() + np.asarray((37, 91), np.int64)
    local_pose, local = refine.local_segment(SHEARED_AFFINE, scale, cells)
    truth = calibrate.scan_points_yx(SHEARED_AFFINE, scale, cells)
    delta = float(np.abs(local_pose.points(local) - truth).max())
    assert delta <= AGREEMENT_TOL_PX, delta


def test_local_pose_points_detect_a_planted_half_cell_slip():
    scale = Fraction(1)
    cells = _all_block_cells() + np.asarray((37, 91), np.int64)
    local_pose, local = refine.local_segment(SHEARED_AFFINE, scale, cells)
    truth = calibrate.scan_points_yx(SHEARED_AFFINE, scale, cells)
    slipped = local_pose.points(local.astype(np.float64) - 0.5)
    delta = float(np.abs(slipped - truth).max())
    assert delta > HALF_CELL_SIGNATURE_PX / 2.0, delta


def _placement(rot_k: int, shape_yx: tuple[int, int],
               n_cells: int = 200) -> data.Placement:
    extent = (100, 200, 100 + shape_yx[0], 200 + shape_yx[1])
    grid = np.stack(np.meshgrid(np.arange(shape_yx[0]),
                                np.arange(shape_yx[1]), indexing="ij"),
                    axis=-1).reshape(-1, 2)
    rng = np.random.default_rng(4242)
    local = grid[rng.choice(grid.shape[0], n_cells, replace=False)]
    return data.Placement(
        window_id=("cap", 3, 0, extent), capture_id="cap", level_index=3,
        region_index=0, patch_ordinal=17, page=0, rot_k=rot_k,
        page_origin_yx=(400, 300), native_affine=SHEARED_AFFINE,
        pitch_px=12.04, route="word",
        local_cells_yx=local.astype(np.int64))


def _region_store(placement: data.Placement, scale: Fraction,
                  row: object) -> object:
    placements = {placement.window_id: placement}
    levels = {("cap", 3): SimpleNamespace(scale=scale)}
    return SimpleNamespace(
        placement=placements.get,
        level=lambda capture_id, level_index: levels[(capture_id,
                                                      level_index)],
        row=row)


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
@pytest.mark.parametrize("scale", (Fraction(1), Fraction(3)))
@pytest.mark.parametrize("shape_yx", ((48, 48), (40, 64)))
def test_region_window_scan_points_match_the_k_convention(
        rot_k, scale, shape_yx):
    row = resolve_format_ref(COLOR_FOSSIL)
    placement = _placement(rot_k, shape_yx)
    store = _region_store(placement, scale, row)
    window = color_region.region_window(store, placement.window_id)
    truth = calibrate.scan_points_yx(
        placement.native_affine, scale, window.page_cells_yx)
    assert window.page_cells_yx.shape[0] == 200
    delta = float(np.abs(window.scan_points_yx - truth).max())
    assert delta <= AGREEMENT_TOL_PX, (rot_k, scale, shape_yx, delta)


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_a_half_cell_slip_in_region_window_would_exceed_the_bar(rot_k):
    row = resolve_format_ref(COLOR_FOSSIL)
    placement = _placement(rot_k, (48, 48))
    store = _region_store(placement, Fraction(1), row)
    window = color_region.region_window(store, placement.window_id)
    truth = calibrate.scan_points_yx(
        placement.native_affine, Fraction(1), window.page_cells_yx)
    linear = np.asarray(SHEARED_AFFINE, np.float64).reshape(2, 3)[:, :2]
    slipped = window.scan_points_yx - linear @ np.full(2, 0.5)
    delta = float(np.abs(slipped - truth).max())
    assert delta > AGREEMENT_TOL_PX
    assert delta == pytest.approx(HALF_CELL_SIGNATURE_PX, abs=0.05)


def test_region_window_keeps_only_cells_inside_the_page():
    row = resolve_format_ref(COLOR_FOSSIL)
    placement = _placement(0, (48, 48))
    store = _region_store(placement, Fraction(1), row)
    window = color_region.region_window(store, placement.window_id)
    height, width = row.cells_yx
    cells = window.page_cells_yx
    assert cells.min() >= 0
    assert int(cells[:, 0].max()) < height
    assert int(cells[:, 1].max()) < width
    assert window.local_cells_yx.shape == cells.shape
    assert window.shape_yx_cells == (48, 48)
    assert window.pitch_px == pytest.approx(12.04)


def _local_pose(pitch: float) -> refine.LocalPose:
    return refine.LocalPose(
        origin_yx=(11.5, 7.25),
        jacobian_yx=((pitch, 0.03), (-0.02, pitch)),
        phase_yx=(0.0, 0.0), pitch_px=pitch, angle_deg=0.0)


def test_refine_sample_at_samples_exactly_pose_points_plus_offsets():
    rng = np.random.default_rng(90210)
    raster = rng.normal(128.0, 20.0, size=(220, 260)).astype(np.float32)
    local_pose = _local_pose(6.0)
    cells = _all_block_cells()
    offsets = rng.normal(0.0, 1.5, size=(cells.shape[0], 2))
    read = refine.sample_at(raster, (0, 0), 0.0, local_pose, cells, offsets)
    expected = _sample(raster, local_pose.points(cells) + offsets)
    assert np.array_equal(read, expected)
    plain = refine.sample_at(raster, (0, 0), 0.0, local_pose, cells)
    assert np.array_equal(plain, _sample(raster, local_pose.points(cells)))
    assert not np.array_equal(read, plain)


def test_refine_sample_at_honours_the_crop_origin():
    rng = np.random.default_rng(4711)
    raster = rng.normal(128.0, 20.0, size=(240, 240)).astype(np.float32)
    local_pose = _local_pose(5.0)
    cells = _all_block_cells()
    crop = (13, 21)
    read = refine.sample_at(raster, crop, 0.0, local_pose, cells)
    expected = _sample(
        raster, local_pose.points(cells) - np.asarray(crop, np.float64))
    assert np.array_equal(read, expected)


def _window_pixels(pitch: float) -> pose.WindowPixels:
    rng = np.random.default_rng(31337)
    luma = rng.normal(140.0, 25.0, size=(200, 200)).astype(np.float32)
    support = np.ones((200, 200), bool)
    return pose.window_pixels(luma, support, (20, 20), (20, 20), pitch,
                              200.0)


def test_pose_sample_segment_offsets_px_arm_is_purely_additive():
    pitch = 6.0
    pixels = _window_pixels(pitch)
    fitted = pose.PoseSegment(
        pose.Pose((25.0, 25.0), ((pitch, 0.0), (0.0, pitch)), (0.5, 0.5),
                  pitch, 0.0),
        (20, 20), 0, 0.0, (pitch, pitch), 0.0)
    shift = np.asarray((0.75, -1.25), np.float64)
    plain = pose.sample_segment(pixels, fitted)
    shifted = pose.sample_segment(pixels, fitted, shift)
    moved = pose.sample_segment(
        pixels, pose.PoseSegment(
            pose.Pose((25.0 + shift[0], 25.0 + shift[1]),
                      fitted.pose.jacobian_yx, fitted.pose.phase_yx, pitch,
                      0.0),
            (20, 20), 0, 0.0, (pitch, pitch), 0.0))
    assert plain is not None and shifted is not None and moved is not None
    assert np.array_equal(shifted.means, moved.means)
    assert not np.array_equal(shifted.means, plain.means)


def test_window_page_cells_and_region_window_select_the_same_page_cells():
    row = resolve_format_ref(COLOR_FOSSIL)
    placement = _placement(2, (48, 48))
    store = _region_store(placement, Fraction(1), row)
    window = color_region.region_window(store, placement.window_id)
    through_k = calibrate.window_page_cells(placement, (48, 48), row.cells_yx)
    assert np.array_equal(window.page_cells_yx, through_k)

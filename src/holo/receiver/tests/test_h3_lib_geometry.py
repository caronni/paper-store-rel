from __future__ import annotations

import hashlib
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver.lib import geometry
from holo.receiver.tests import _h3_support

TILE_CELLS = 64
WINDOW_CELLS = 200
WINDOW_STEP_CELLS = 160
LAYOUT_MIN_WINDOW_CELLS = 8

SITE_HASH_Y_COEFFICIENT = 131
SITE_HASH_X_COEFFICIENT = 17
# frozen 2026-08-29 over the 64x64 cell block in raster order, '<i8' bytes
SITE_HASH_SHA256 = (
    "82b398f01edddddf34fed833093f96cc"
    "76e06c8091c3fe84e6161f2010b0ea6d")
SITE_PARITY_SHA256 = (
    "5341245c407d1835c5f54508aac9cd0e"
    "dc1d47e0ca280e6442f7f5967bad916f")
SITE_HASH_SAMPLES = (
    ((0, 0), 0), ((1, 0), 131), ((0, 1), 17), ((3, 7), 512),
    ((63, 63), 9324))

SINGULAR_REFUSAL = "pose affine is singular; it maps no cells"

POSE_TERMS = (
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    (6.0, 0.0, 12.5, 0.0, 6.0, -3.25),
    (5.9921875, 0.03125, 1201.5, -0.015625, 6.0078125, 903.25),
    (-2.25, 0.5, -48.0, 0.125, 3.5, 17.75),
)

# recorded 2026-08-29 on machine 4's free-threaded 3.14 venv (then named
# env314t), over POSE_TERMS: the dyadic scales survive the float round
# trip exactly, the rest land within one ulp
EXACT_COMPOSE_SCALES = (Fraction(1), Fraction(2), Fraction(4), Fraction(8),
                        Fraction(16))
NEAR_COMPOSE_SCALES = (Fraction(3), Fraction(3, 2), Fraction(8, 3),
                       Fraction(12, 5))
COMPOSE_NEAR_TOLERANCE = 1e-12


def _cell_block(n_cells: int = 64) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.meshgrid(np.arange(n_cells, dtype=np.int64),
                         np.arange(n_cells, dtype=np.int64), indexing="ij")
    return ys.ravel(), xs.ravel()


def test_layout_constants_are_the_frozen_window_lattice():
    assert geometry.TILE_CELLS == TILE_CELLS
    assert geometry.WINDOW_CELLS == WINDOW_CELLS
    assert geometry.WINDOW_STEP_CELLS == WINDOW_STEP_CELLS
    assert geometry.LAYOUT_MIN_WINDOW_CELLS == LAYOUT_MIN_WINDOW_CELLS
    assert WINDOW_CELLS % TILE_CELLS != 0
    assert WINDOW_STEP_CELLS < WINDOW_CELLS


@pytest.mark.parametrize("terms", POSE_TERMS)
def test_affine_matrix_and_terms_round_trip_exactly(terms):
    matrix = geometry.affine_matrix(terms)
    assert matrix.shape == (2, 3) and matrix.dtype == np.float64
    assert geometry.affine_terms(matrix) == terms
    assert geometry.affine_terms(geometry.affine_matrix(
        geometry.affine_terms(matrix))) == terms


@pytest.mark.parametrize("terms", POSE_TERMS)
def test_apply_affine_is_the_literal_two_row_product(terms):
    rng = np.random.default_rng(20260829)
    ys = rng.normal(scale=100.0, size=64)
    xs = rng.normal(scale=100.0, size=64)
    a, b, c, d, e, f = terms
    got_y, got_x = geometry.apply_affine(terms, ys, xs)
    assert np.array_equal(got_y, a * ys + b * xs + c)
    assert np.array_equal(got_x, d * ys + e * xs + f)


@pytest.mark.parametrize("terms", POSE_TERMS)
def test_inverting_a_pose_takes_pixels_back_to_their_cells(terms):
    inverse = geometry.invert_affine(terms)
    rng = np.random.default_rng(20260829)
    ys = rng.normal(scale=100.0, size=64)
    xs = rng.normal(scale=100.0, size=64)
    pixel_y, pixel_x = geometry.apply_affine(terms, ys, xs)
    back_y, back_x = geometry.apply_affine(inverse, pixel_y, pixel_x)
    assert np.allclose(back_y, ys, rtol=0.0, atol=1e-9)
    assert np.allclose(back_x, xs, rtol=0.0, atol=1e-9)
    twice = geometry.invert_affine(inverse)
    assert np.allclose(np.asarray(twice), np.asarray(terms),
                       rtol=1e-12, atol=1e-12)


def test_a_singular_pose_refuses_by_name_instead_of_returning_nonsense():
    with pytest.raises(ValueError) as excinfo:
        geometry.invert_affine((1.0, 2.0, 0.0, 2.0, 4.0, 0.0))
    assert str(excinfo.value) == SINGULAR_REFUSAL


def test_shift_affine_moves_the_pose_by_whole_cells():
    terms = (6.0, 0.0, 12.5, 0.0, 6.0, -3.25)
    ys = np.array([0.0, 1.0, 17.0])
    xs = np.array([0.0, 2.0, 31.0])
    shifted = geometry.apply_affine(
        geometry.shift_affine(terms, 2.0, 3.0), ys, xs)
    direct = geometry.apply_affine(terms, ys + 2.0, xs + 3.0)
    assert np.array_equal(shifted[0], direct[0])
    assert np.array_equal(shifted[1], direct[1])
    assert geometry.shift_affine(terms, 0.0, 0.0) == terms


@pytest.mark.parametrize("scale", EXACT_COMPOSE_SCALES + NEAR_COMPOSE_SCALES)
def test_rescale_pixels_carries_the_half_cell_shift_of_the_scale(scale):
    zero = geometry.rescale_pixels((0.0,) * 6, scale)
    expected_shift = float(Fraction(scale - 1, 2))
    assert zero == (0.0, 0.0, expected_shift, 0.0, 0.0, expected_shift)
    terms = (6.0, 0.5, 12.5, -0.25, 6.0, -3.25)
    scaled = geometry.rescale_pixels(terms, scale)
    for index in (0, 1, 3, 4):
        assert scaled[index] == float(
            Fraction(terms[index]) * scale)
    for index in (2, 5):
        assert scaled[index] == float(
            Fraction(terms[index]) * scale + Fraction(scale - 1, 2))


@pytest.mark.parametrize("terms", POSE_TERMS)
def test_compose_to_and_from_native_are_inverses_at_dyadic_scales(terms):
    for scale in EXACT_COMPOSE_SCALES:
        back = geometry.compose_to_native(
            geometry.compose_from_native(terms, scale), scale)
        assert back == terms, scale
    for scale in NEAR_COMPOSE_SCALES:
        back = geometry.compose_to_native(
            geometry.compose_from_native(terms, scale), scale)
        assert np.allclose(np.asarray(back), np.asarray(terms),
                           rtol=COMPOSE_NEAR_TOLERANCE,
                           atol=COMPOSE_NEAR_TOLERANCE), scale


def test_scale_one_composes_to_the_identical_tuple():
    for terms in POSE_TERMS:
        assert geometry.compose_to_native(terms, Fraction(1)) == terms
        assert geometry.compose_from_native(terms, Fraction(1)) == terms


def test_compose_from_native_is_a_rescale_by_the_reciprocal():
    terms = (6.0, 0.5, 12.5, -0.25, 6.0, -3.25)
    for scale in EXACT_COMPOSE_SCALES + NEAR_COMPOSE_SCALES:
        if scale == 1:
            continue
        assert geometry.compose_from_native(terms, scale) == (
            geometry.rescale_pixels(terms, 1 / scale))
        assert geometry.compose_to_native(terms, scale) == (
            geometry.rescale_pixels(terms, scale))


@pytest.mark.parametrize("n_cells", [8, 100, 200, 201, 360, 361, 520, 2368,
                                     3392])
def test_window_starts_cover_the_axis_with_the_declared_step(n_cells):
    starts = geometry.window_starts(n_cells)
    assert starts[0] == 0
    size = min(WINDOW_CELLS, n_cells)
    assert starts[-1] == n_cells - size
    for previous, current in zip(starts, starts[1:]):
        assert 0 < current - previous <= WINDOW_STEP_CELLS
        assert current <= previous + size
    covered = np.zeros(n_cells, bool)
    for start in starts:
        covered[start:start + size] = True
    assert covered.all()
    assert starts[-1] + size == n_cells


@pytest.mark.parametrize("n_cells", [0, 1, 7])
def test_an_axis_below_the_layout_minimum_yields_no_windows(n_cells):
    assert geometry.window_starts(n_cells) == ()


def test_an_axis_no_wider_than_one_window_yields_exactly_one_start():
    for n_cells in (8, 64, 199, 200):
        assert geometry.window_starts(n_cells) == (0,)


def test_site_hash_is_the_single_home_of_the_131_17_lattice():
    ys, xs = _cell_block()
    values = geometry.site_hash(ys, xs)
    assert values.dtype == np.int64
    assert np.array_equal(
        values, SITE_HASH_Y_COEFFICIENT * ys + SITE_HASH_X_COEFFICIENT * xs)
    _h3_support.assert_golden(
        "site_hash over the 64x64 block",
        hashlib.sha256(values.astype("<i8").tobytes()).hexdigest(),
        SITE_HASH_SHA256)
    for (cell_y, cell_x), expected in SITE_HASH_SAMPLES:
        assert int(geometry.site_hash(np.int64(cell_y),
                                     np.int64(cell_x))) == expected
    swapped = (SITE_HASH_X_COEFFICIENT * ys
               + SITE_HASH_Y_COEFFICIENT * xs)
    assert not np.array_equal(values, swapped)


def test_site_parity_is_the_low_bit_of_the_same_hash():
    ys, xs = _cell_block()
    parity = geometry.site_parity(ys, xs)
    assert np.array_equal(parity, geometry.site_hash(ys, xs) & 1)
    _h3_support.assert_golden(
        "site_parity over the 64x64 block",
        hashlib.sha256(parity.astype("<i8").tobytes()).hexdigest(),
        SITE_PARITY_SHA256)
    assert float(parity.mean()) == 0.5


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_rotating_points_and_rotating_back_is_the_identity(rot_k):
    shape = (7, 11)
    ys, xs = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                         indexing="ij")
    points = np.column_stack((ys.ravel(), xs.ravel())).astype(np.int64)
    rotated = geometry.rotated_points(points, shape, rot_k)
    rotated_shape = shape if rot_k % 2 == 0 else (shape[1], shape[0])
    assert int(rotated[:, 0].max()) == rotated_shape[0] - 1
    assert int(rotated[:, 1].max()) == rotated_shape[1] - 1
    back = geometry.rotated_points(rotated, rotated_shape, (4 - rot_k) % 4)
    assert np.array_equal(back, points)


def test_rotated_points_are_the_literal_corner_map():
    points = np.array([[0, 0], [1, 2]], np.int64)
    shape = (4, 5)
    assert geometry.rotated_points(points, shape, 0).tolist() == [[0, 0],
                                                                  [1, 2]]
    assert geometry.rotated_points(points, shape, 1).tolist() == [[4, 0],
                                                                  [2, 1]]
    assert geometry.rotated_points(points, shape, 2).tolist() == [[3, 4],
                                                                  [2, 2]]
    assert geometry.rotated_points(points, shape, 3).tolist() == [[0, 3],
                                                                  [2, 2]]


def test_tile_of_cell_partitions_the_cell_grid_into_64_cell_tiles():
    ys, xs = _cell_block(n_cells=200)
    tile_y, tile_x = geometry.tile_of_cell(ys, xs)
    assert np.array_equal(tile_y, ys // TILE_CELLS)
    assert np.array_equal(tile_x, xs // TILE_CELLS)
    for cell, tile in ((0, 0), (63, 0), (64, 1), (127, 1), (128, 2),
                       (199, 3)):
        assert int(geometry.tile_of_cell(np.int64(cell), np.int64(0))[0]) == (
            tile)
    counts = np.bincount(tile_y * 4 + tile_x)
    assert int(counts[0]) == TILE_CELLS * TILE_CELLS
    assert int(counts.sum()) == 200 * 200

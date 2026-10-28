from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from holo3.lib import decimate
from holo3.tests import _h3_support

MINIMUM_PPC = Fraction(2)
DEFAULT_CHUNK_ROWS = 128

PITCH_IN = {"c1": Fraction(1, 600), "c2": Fraction(1, 300),
            "c3": Fraction(1, 200), "c4": Fraction(1, 150)}

# frozen 2026-08-29: every dpi x pitch-class ladder, as level strings
LADDER_TABLE = (
    (600, "c1", ("1",)),
    (600, "c2", ("2",)),
    (600, "c3", ("2", "3")),
    (600, "c4", ("2", "4")),
    (1200, "c1", ("2",)),
    (1200, "c2", ("2", "4")),
    (1200, "c3", ("2", "3", "6")),
    (1200, "c4", ("2", "4", "8")),
    (1600, "c1", ("2", "8/3")),
    (1600, "c2", ("2", "8/3", "16/3")),
    (1600, "c3", ("2", "4", "8")),
    (1600, "c4", ("2", "32/9", "16/3", "32/3")),
    (2400, "c1", ("2", "4")),
    (2400, "c2", ("2", "4", "8")),
    (2400, "c3", ("2", "4", "6", "12")),
    (2400, "c4", ("2", "4", "8", "16")),
    (4800, "c1", ("2", "4", "8")),
    (4800, "c2", ("2", "4", "8", "16")),
    (4800, "c3", ("2", "4", "8", "12", "24")),
    (4800, "c4", ("2", "4", "8", "16", "32")),
)

INTEGER_LADDER_DPI = (600, 1200, 2400, 4800)
FRACTIONAL_LADDER_DPI = 1600

BOX_FACTORS = (2, 3, 4, 6, 8, 16)
RATIONAL_SCALES = (Fraction(3, 2), Fraction(8, 3), Fraction(5, 3),
                   Fraction(16, 3), Fraction(12, 5))

EXACT_TRANSFORM_SCALES = (Fraction(1), Fraction(2), Fraction(4),
                          Fraction(8), Fraction(16))
NEAR_TRANSFORM_SCALES = (Fraction(3), Fraction(8, 3), Fraction(12, 5))
TRANSFORM_NEAR_TOLERANCE = 1e-9

PROBE_POINTS = np.array([[0.0, 0.0], [1.0, 2.0], [12.5, 7.25],
                         [4000.0, 3000.0], [-3.0, 11.125]])
PROBE_AFFINE = np.array([[6.0, 0.0, 12.5], [0.0, 6.0, -3.25]])


def _levels(dpi: int, pitch_class: str) -> tuple[Fraction, ...]:
    return decimate.auto_ppc_levels(dpi, PITCH_IN[pitch_class])


def _box_oracle(grey: np.ndarray, factor: int) -> np.ndarray:
    height = grey.shape[0] // factor
    width = grey.shape[1] // factor
    out = np.empty((height, width), np.uint8)
    for row in range(height):
        for column in range(width):
            block = grey[row * factor:(row + 1) * factor,
                         column * factor:(column + 1) * factor]
            total = int(np.asarray(block, np.int64).sum())
            out[row, column] = int(round(Fraction(total, factor * factor)))
    return out


def _overlap_weights(index: int, scale: Fraction) -> list[tuple[int, int]]:
    p, q = scale.numerator, scale.denominator
    start, stop = index * p, (index + 1) * p
    rows = []
    for source_index in range(start // q, (stop + q - 1) // q):
        overlap = (min(stop, (source_index + 1) * q)
                   - max(start, source_index * q))
        if overlap > 0:
            rows.append((source_index, overlap))
    return rows


def _area_oracle(grey: np.ndarray, scale: Fraction) -> np.ndarray:
    # v1's arbitrary-precision fallback (_integer_area_tile_python):
    # exact rational area mean, ties rounded half-to-even
    p = scale.numerator
    out_h = grey.shape[0] * scale.denominator // p
    out_w = grey.shape[1] * scale.denominator // p
    out = np.empty((out_h, out_w), np.uint8)
    for oy in range(out_h):
        ys = _overlap_weights(oy, scale)
        for ox in range(out_w):
            total = 0
            for sy, wy in ys:
                for sx, wx in _overlap_weights(ox, scale):
                    total += int(grey[sy, sx]) * wy * wx
            out[oy, ox] = int(round(Fraction(total, p * p)))
    return out


def test_intake_constants_are_the_integer_only_contract():
    assert decimate.MINIMUM_PPC == MINIMUM_PPC
    assert decimate.DEFAULT_CHUNK_ROWS == DEFAULT_CHUNK_ROWS


def test_as_fraction_takes_the_decimal_reading_of_a_float():
    assert decimate.as_fraction(1200.0) == Fraction(1200)
    assert decimate.as_fraction(0.1) == Fraction(1, 10)
    assert decimate.as_fraction("2400") == Fraction(2400)
    assert decimate.as_fraction(2400) == Fraction(2400)
    assert decimate.as_fraction(Fraction(5, 2)) == Fraction(5, 2)
    assert decimate.as_fraction(np.float64(1200.0)) == Fraction(1200)
    assert decimate.as_fraction(0.1) != Fraction(0.1)


@pytest.mark.parametrize("dpi, pitch_class, expected", LADDER_TABLE)
def test_the_ppc_ladder_is_frozen_for_every_dpi_and_pitch_class(
        dpi, pitch_class, expected):
    levels = _levels(dpi, pitch_class)
    _h3_support.assert_golden(
        f"auto_ppc_levels({dpi}, {pitch_class})",
        tuple(str(level) for level in levels), expected)
    native = decimate.native_pixels_per_cell(dpi, PITCH_IN[pitch_class])
    assert native == Fraction(dpi) * PITCH_IN[pitch_class]
    assert levels[-1] == native
    if native > MINIMUM_PPC:
        assert levels[0] == MINIMUM_PPC
    else:
        assert levels == (native,)
    for lower, upper in zip(levels, levels[1:]):
        assert lower < upper


@pytest.mark.parametrize("dpi", INTEGER_LADDER_DPI)
@pytest.mark.parametrize("pitch_class", sorted(PITCH_IN))
def test_a_600_multiple_scanner_gives_an_integer_only_ladder(dpi,
                                                             pitch_class):
    for level in _levels(dpi, pitch_class):
        assert level.denominator == 1
        assert decimate.AreaPixelTransform(level).is_integer_box


@pytest.mark.parametrize("pitch_class", ["c1", "c2", "c4"])
def test_an_off_grid_scanner_ladder_materialises_its_fractional_scales(
        pitch_class):
    levels = _levels(FRACTIONAL_LADDER_DPI, pitch_class)
    native = levels[-1]
    scales = [native / ppc for ppc in levels[:-1]]
    fractional = [scale for scale in scales if scale.denominator != 1]
    assert fractional
    rng = np.random.default_rng(20260830)
    grey = rng.integers(0, 256, size=(33, 27)).astype(np.uint8)
    for scale in fractional:
        transform = decimate.AreaPixelTransform(scale)
        assert not transform.is_integer_box
        got = decimate.area_decimate(grey, transform)
        assert got.dtype == np.uint8
        assert got.shape == transform.output_shape(grey.shape)
        assert np.array_equal(got, _area_oracle(grey, scale))


@pytest.mark.parametrize("scale", RATIONAL_SCALES)
def test_a_rational_scale_is_the_exact_area_mean_round_half_even(scale):
    rng = np.random.default_rng(20260830 + scale.numerator)
    grey = rng.integers(0, 256, size=(37, 29)).astype(np.uint8)
    transform = decimate.AreaPixelTransform(scale)
    got = decimate.area_decimate(grey, transform)
    assert got.dtype == np.uint8
    assert got.shape == transform.output_shape(grey.shape)
    assert np.array_equal(got, _area_oracle(grey, scale))


@pytest.mark.parametrize("scale", (Fraction(3, 2), Fraction(8, 3)))
def test_rational_row_chunking_never_changes_a_pixel(scale):
    rng = np.random.default_rng(20260830)
    grey = rng.integers(0, 256, size=(48, 40)).astype(np.uint8)
    transform = decimate.AreaPixelTransform(scale)
    reference = decimate.area_decimate(grey, transform)
    for chunk_rows in (1, 2, 7, DEFAULT_CHUNK_ROWS, 4096):
        assert np.array_equal(
            decimate.area_decimate(grey, transform, chunk_rows), reference)


@pytest.mark.parametrize("factor", BOX_FACTORS)
def test_area_decimate_is_the_exact_rational_block_mean(factor):
    rng = np.random.default_rng(20260829 + factor)
    grey = rng.integers(0, 256, size=(3 * factor + 5,
                                      4 * factor + 3)).astype(np.uint8)
    transform = decimate.AreaPixelTransform(Fraction(factor))
    got = decimate.area_decimate(grey, transform)
    assert got.dtype == np.uint8
    assert got.shape == (grey.shape[0] // factor, grey.shape[1] // factor)
    assert np.array_equal(got, _box_oracle(grey, factor))


@pytest.mark.parametrize("factor", BOX_FACTORS)
def test_row_chunking_never_changes_a_pixel(factor):
    rng = np.random.default_rng(20260829 + factor)
    grey = rng.integers(0, 256, size=(6 * factor, 5 * factor)).astype(
        np.uint8)
    transform = decimate.AreaPixelTransform(Fraction(factor))
    reference = decimate.area_decimate(grey, transform)
    for chunk_rows in (1, 2, 7, DEFAULT_CHUNK_ROWS, 4096):
        assert np.array_equal(
            decimate.area_decimate(grey, transform, chunk_rows), reference)


def test_area_decimate_into_writes_the_same_bytes_into_a_caller_buffer():
    rng = np.random.default_rng(20260829)
    grey = rng.integers(0, 256, size=(24, 30)).astype(np.uint8)
    transform = decimate.AreaPixelTransform(Fraction(3))
    reference = decimate.area_decimate(grey, transform)
    buffer = np.zeros(transform.output_shape(grey.shape), np.uint8)
    returned = decimate.area_decimate_into(grey, transform, buffer)
    assert returned is buffer
    assert np.array_equal(buffer, reference)


def test_the_identity_factor_copies_the_source_rather_than_aliasing_it():
    rng = np.random.default_rng(20260829)
    grey = rng.integers(0, 256, size=(9, 7)).astype(np.uint8)
    got = decimate.area_decimate(grey, decimate.AreaPixelTransform(
        Fraction(1)))
    assert np.array_equal(got, grey)
    got[0, 0] ^= 0xFF
    assert got[0, 0] != grey[0, 0]


def test_rgb_decimation_is_the_three_planes_decimated_separately():
    rng = np.random.default_rng(20260829)
    rgb = rng.integers(0, 256, size=(24, 18, 3)).astype(np.uint8)
    transform = decimate.AreaPixelTransform(Fraction(3))
    per_plane = np.stack(
        [decimate.area_decimate(rgb[..., channel], transform)
         for channel in range(3)], axis=2)
    assert np.array_equal(decimate.area_decimate_rgb(rgb, transform),
                          per_plane)
    buffer = np.zeros(transform.output_shape(rgb.shape) + (3,), np.uint8)
    assert decimate.area_decimate_rgb_into(
        rgb, transform, buffer) is buffer
    assert np.array_equal(buffer, per_plane)


def test_the_k_luma_rung_means_the_channels_before_the_box_never_after():
    rng = np.random.default_rng(20260829)
    rgb = rng.integers(0, 256, size=(24, 18, 3)).astype(np.uint8)
    transform = decimate.AreaPixelTransform(Fraction(3))
    mean_then_box = decimate.area_decimate(
        np.asarray(rgb[..., :3].mean(axis=2), np.float32), transform)
    assert np.array_equal(decimate.area_decimate(rgb, transform),
                          mean_then_box)
    box_then_mean = np.asarray(
        decimate.area_decimate_rgb(rgb, transform).mean(axis=2).round(),
        np.uint8)
    assert not np.array_equal(mean_then_box, box_then_mean)


@pytest.mark.parametrize("scale", EXACT_TRANSFORM_SCALES
                         + NEAR_TRANSFORM_SCALES)
def test_area_pixel_transform_reports_its_own_shape_arithmetic(scale):
    transform = decimate.AreaPixelTransform(scale)
    assert transform.is_identity == (scale == 1)
    assert transform.is_integer_box == (scale.denominator == 1)
    for source_length in (0, 1, 7, 100, 4801):
        assert transform.output_length(source_length) == (
            source_length * scale.denominator // scale.numerator)
    assert transform.output_shape((100, 51)) == (
        transform.output_length(100), transform.output_length(51))


@pytest.mark.parametrize("scale", EXACT_TRANSFORM_SCALES
                         + NEAR_TRANSFORM_SCALES)
def test_source_and_view_points_are_the_half_pixel_centre_convention(scale):
    transform = decimate.AreaPixelTransform(scale)
    view = transform.source_to_view_points(PROBE_POINTS)
    if scale == 1:
        assert np.array_equal(view, PROBE_POINTS)
    else:
        assert np.array_equal(
            view, (PROBE_POINTS + 0.5) / float(scale) - 0.5)
    back = transform.view_to_source_points(view)
    if scale in EXACT_TRANSFORM_SCALES:
        assert np.array_equal(back, PROBE_POINTS)
    else:
        assert np.allclose(back, PROBE_POINTS, rtol=0.0,
                           atol=TRANSFORM_NEAR_TOLERANCE)


@pytest.mark.parametrize("scale", EXACT_TRANSFORM_SCALES
                         + NEAR_TRANSFORM_SCALES)
def test_the_affine_transforms_match_the_point_transforms(scale):
    transform = decimate.AreaPixelTransform(scale)
    view = transform.source_to_view_affine(PROBE_AFFINE)
    assert view.shape == (2, 3)
    if scale == 1:
        assert np.array_equal(view, PROBE_AFFINE)
    else:
        assert np.array_equal(view[:, :2], PROBE_AFFINE[:, :2]
                              / float(scale))
        assert np.array_equal(
            view[:, 2], (PROBE_AFFINE[:, 2] + 0.5) / float(scale) - 0.5)
    back = transform.view_to_source_affine(view)
    if scale in EXACT_TRANSFORM_SCALES:
        assert np.array_equal(back, PROBE_AFFINE)
    else:
        assert np.allclose(back, PROBE_AFFINE, rtol=0.0,
                           atol=TRANSFORM_NEAR_TOLERANCE)


def test_transform_outputs_never_alias_their_inputs():
    transform = decimate.AreaPixelTransform(Fraction(1))
    points = transform.source_to_view_points(PROBE_POINTS)
    points[0, 0] = 99.0
    assert float(PROBE_POINTS[0, 0]) == 0.0
    affine = transform.view_to_source_affine(PROBE_AFFINE)
    affine[0, 0] = 99.0
    assert float(PROBE_AFFINE[0, 0]) == 6.0


def test_luma_is_the_plain_channel_mean_in_float32():
    pixels = np.array([[[0, 0, 0], [255, 255, 255], [10, 20, 31]]], np.uint8)
    luma = decimate.luma_f32(pixels)
    assert luma.dtype == np.float32
    assert luma.tolist() == [[0.0, 255.0, float(np.float32(61.0 / 3.0))]]
    assert np.array_equal(
        decimate.plane_mean_luma_f32(pixels[..., 0], pixels[..., 1],
                                     pixels[..., 2]), luma)


def test_luma_of_a_grey_raster_is_a_float32_view_of_the_same_values():
    rng = np.random.default_rng(20260829)
    grey = rng.integers(0, 256, size=(4, 5)).astype(np.uint8)
    luma = decimate.luma_f32(grey)
    assert luma.dtype == np.float32
    assert np.array_equal(luma, grey.astype(np.float32))


def test_a_four_channel_raster_drops_the_alpha_before_the_mean():
    rgba = np.zeros((1, 2, 4), np.uint8)
    rgba[..., :3] = 12
    rgba[..., 3] = 255
    assert decimate.luma_f32(rgba).tolist() == [[12.0, 12.0]]

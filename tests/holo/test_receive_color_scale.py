"""Color-only direct-native scale lanes without K numerical changes."""
from __future__ import annotations

from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from holo.format.registry import get_format_row
from holo.receive.cascade import (
    ColorScaleRaster,
    ScaleRaster,
    _materialize,
    release_derived_lanes,
)
from holo.receive.scan import open_capture
from holo.receive.scale_space import (
    AreaPixelTransform,
    ScaleSchedule,
    area_decimate,
    area_decimate_rgb,
    area_decimate_rgb_into,
)


def test_rgb_decimation_is_three_independent_registered_scalar_transforms():
    rng = np.random.default_rng(0xC017)
    source = rng.integers(0, 65_536, (37, 41, 3), dtype=np.uint16)
    transform = AreaPixelTransform(Fraction(5, 2))

    got = area_decimate_rgb(
        source, transform, chunk_rows=3, chunk_cols=4)
    expected = np.stack(tuple(
        area_decimate(
            source[..., channel], transform,
            chunk_rows=2, chunk_cols=7)
        for channel in range(3)
    ), axis=2)

    assert got.dtype == source.dtype
    assert np.array_equal(got, expected)


def test_rgb_decimation_rejects_grey_wrong_output_and_aliases():
    transform = AreaPixelTransform(Fraction(2))
    grey = np.zeros((8, 10), np.uint8)
    rgb = np.zeros((8, 10, 3), np.uint8)
    with pytest.raises(ValueError, match="exactly RGB"):
        area_decimate_rgb(grey, transform)
    with pytest.raises(ValueError, match="RGB output shape"):
        area_decimate_rgb_into(
            rgb, transform, np.empty((4, 5), np.uint8))
    with pytest.raises(ValueError, match="must not share"):
        area_decimate_rgb_into(
            rgb, AreaPixelTransform(Fraction(1)), rgb)


def _context(source: np.ndarray, row_id: str) -> tuple[object, object]:
    native = open_capture(source, 1200.0)
    return native, SimpleNamespace(
        native=native,
        spec=get_format_row(row_id),
        facts=SimpleNamespace(
            source_sha256=native.source.sha256,
            channels=native.source.channels,
        ),
    )


def test_color_materializer_retains_aligned_rgb_and_derives_lane_luma():
    rng = np.random.default_rng(0xC0A5E)
    source = rng.integers(0, 256, (47, 53, 3), dtype=np.uint8)
    native, context = _context(
        source, "c3-cmy8-p120-v0@2240x1536")
    level = ScaleSchedule.auto(1200, 3).levels[0]
    expected = area_decimate_rgb(source, level.transform)

    raster = _materialize(context, level)
    assert isinstance(raster, ColorScaleRaster)
    height, width = raster.shape
    lane_rgb = raster.crop_native(0, height, 0, width)
    lane_luma = raster.crop_luma(0, height, 0, width)
    assert np.array_equal(lane_rgb, expected)
    np.testing.assert_array_equal(
        lane_luma, expected.mean(axis=2, dtype=np.float32))
    assert not lane_rgb.flags.writeable
    assert not lane_luma.flags.writeable
    assert raster.source_sha256 == native.source.sha256

    # v0.37: the derivation is pooled for the native raster's lifetime and
    # a repeat visit reuses the exact object; explicit release invalidates.
    assert _materialize(context, level) is raster
    release_derived_lanes(native)
    with pytest.raises(RuntimeError, match="released"):
        raster.crop_native(0, 1, 0, 1)


def test_k_materializer_stays_on_registered_grey_leaf():
    rng = np.random.default_rng(0x0B1A)
    source = rng.integers(0, 256, (47, 53, 3), dtype=np.uint8)
    _native, context = _context(source, "c3-r0550@2240x1536")
    level = ScaleSchedule.auto(1200, 3).levels[0]
    expected = area_decimate(source, level.transform)

    raster = _materialize(context, level)
    assert type(raster) is ScaleRaster
    height, width = raster.shape
    assert np.array_equal(
        raster.crop_native(0, height, 0, width), expected)
    release_derived_lanes(_native)


def test_greyscale_color_capture_remains_luma_only_for_addressing():
    source = np.arange(47 * 53, dtype=np.uint16).reshape(47, 53)
    _native, context = _context(
        source, "c2-cmy7-p120-v0@3328x2304")
    level = ScaleSchedule.auto(1200, 2).levels[0]

    raster = _materialize(context, level)
    assert type(raster) is ScaleRaster
    assert raster.crop_native(
        0, raster.shape[0], 0, raster.shape[1]).ndim == 2
    release_derived_lanes(_native)

"""Public contracts of Track-3 native capture ingest."""
from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from holo.receive import open_capture
from holo.receive._runtime_validation import validate_lane_request
from holo.receive.cascade import scale_plan
from holo.receive.runtime import LaneRequest
from holo.receive.session import CaptureFacts


DPI = 1200.0


def _native_lane_fixture():
    raster = open_capture(
        np.arange(48, dtype=np.uint16).reshape(4, 12),
        DPI,
    )
    source = raster.source
    facts = CaptureFacts(
        source.sha256,
        source.dpi,
        source.dtype,
        source.shape,
        source.channels,
    )
    lane = scale_plan(DPI, 3)[-1]
    return raster, facts, lane


def test_array_identity_native_dtype_and_readonly_crops() -> None:
    source = np.arange(48, dtype=np.uint16).reshape(4, 12)
    same = source.copy()
    raster = open_capture(source, DPI)

    assert raster.source.sha256 == open_capture(same, DPI).source.sha256
    assert raster.source.sha256 != open_capture(
        same.reshape(6, 8), DPI
    ).source.sha256
    assert raster.source.dtype == "uint16"
    assert raster.source.shape == (4, 12)
    assert raster.source.channels == 1
    assert raster.source.dpi == DPI

    # Borrowed arrays are detached before they become authenticated input.
    source[0, 0] = np.uint16(999)
    native = raster.crop_native(0, 2, 0, 3)
    luma = raster.crop_luma(0, 2, 0, 3)
    assert native.dtype == np.uint16 and int(native[0, 0]) == 0
    assert luma.dtype == np.float32
    np.testing.assert_array_equal(luma, same[:2, :3].astype(np.float32))
    assert not native.flags.writeable and not luma.flags.writeable
    with pytest.raises(ValueError):
        native[0, 0] = 1
    with pytest.raises(ValueError):
        luma[0, 0] = 1.0
    with pytest.raises(FrozenInstanceError):
        raster.source.sha256 = "0" * 64  # type: ignore[misc]


def test_lane_request_is_bound_to_authenticated_plan_position() -> None:
    raster, facts, lane = _native_lane_fixture()
    request = LaneRequest(lane, raster)

    validate_lane_request(request, facts, lane)

    wrong_lane = scale_plan(DPI, 3)[0]
    with pytest.raises(ValueError, match="scale plan"):
        validate_lane_request(replace(request, spec=wrong_lane), facts, lane)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_sha256", "b" * 64, "another source"),
        ("native_dtype", np.dtype("float64"), "dtype"),
        ("shape", (7, 11), "shape"),
        ("dpi", 13.0, "dpi"),
    ],
)
def test_lane_request_rejects_a_foreign_raster_view(
    field: str,
    value: object,
    message: str,
) -> None:
    raster, facts, lane = _native_lane_fixture()
    view = SimpleNamespace(
        source_sha256=raster.source_sha256,
        native_dtype=raster.native_dtype,
        shape=raster.shape,
        dpi=raster.dpi,
        luma_max=raster.luma_max,
    )
    setattr(view, field, value)
    request = LaneRequest(lane, view)

    with pytest.raises(ValueError, match=message):
        validate_lane_request(request, facts, lane)


def test_path_identity_is_exact_encoded_file_sha(tmp_path) -> None:
    pixels = np.arange(99, dtype=np.uint8).reshape(9, 11)
    path = tmp_path / "capture.png"
    Image.fromarray(pixels, mode="L").save(path)

    raster = open_capture(path, DPI)
    assert raster.source.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert raster.source.shape == pixels.shape
    np.testing.assert_array_equal(
        raster.crop_native(0, 9, 0, 11), pixels
    )
    with pytest.raises(FileNotFoundError):
        open_capture(tmp_path / "missing.png", DPI)


def test_crop_bounds_are_strict_and_accept_numpy_integers() -> None:
    raster = open_capture(np.arange(35, dtype=np.uint8).reshape(5, 7), DPI)
    box = tuple(np.int64(value) for value in (1, 4, 2, 6))
    assert raster.contains(*box)
    assert raster.crop_native(*box).shape == (3, 4)
    assert raster.contains(0, 5, 0, 7)

    invalid = (
        (-1, 2, 0, 2),
        (0, 6, 0, 2),
        (0, 2, 0, 8),
        (2, 2, 0, 2),
        (3, 2, 0, 2),
        (False, 2, 0, 2),
        (0.0, 2, 0, 2),
    )
    for bad in invalid:
        assert not raster.contains(*bad)
        with pytest.raises(ValueError, match="in-bounds"):
            raster.crop_luma(*bad)


def test_rgb_equal_mean_and_singleton_grey_are_raw_luma() -> None:
    rgb = np.array(
        [
            [[3, 12, 30], [40, 10, 70]],
            [[255, 0, 0], [17, 17, 17]],
        ],
        dtype=np.uint8,
    )
    raster = open_capture(rgb, DPI)
    assert raster.source.channels == 3
    np.testing.assert_array_equal(
        raster.crop_luma(0, 2, 0, 2),
        rgb.mean(axis=2, dtype=np.float32),
    )

    grey = np.arange(20, dtype=np.uint16).reshape(4, 5)
    singleton = open_capture(grey[:, :, None], DPI)
    assert singleton.source.channels == 1
    assert singleton.source.shape == grey.shape
    np.testing.assert_array_equal(
        singleton.crop_luma(0, 4, 0, 5), grey.astype(np.float32)
    )


@pytest.mark.parametrize("dpi", [0.0, -1.0, np.nan, np.inf, True])
def test_dpi_must_be_finite_positive_and_not_boolean(dpi) -> None:
    with pytest.raises(ValueError, match="dpi"):
        open_capture(np.zeros((2, 2), dtype=np.uint8), dpi)


@pytest.mark.parametrize(
    "pixels",
    [
        np.zeros(4, dtype=np.uint8),
        np.zeros((2, 2, 2), dtype=np.uint8),
        np.zeros((2, 2, 4), dtype=np.uint8),
        np.zeros((1, 2, 2, 3), dtype=np.uint8),
        np.zeros((2, 2), dtype=np.bool_),
        np.zeros((2, 2), dtype=np.complex64),
    ],
)
def test_rank_channel_and_dtype_refusals(pixels: np.ndarray) -> None:
    with pytest.raises(ValueError):
        open_capture(pixels, DPI)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nonfinite_native_samples_are_refused(bad: float) -> None:
    pixels = np.zeros((3, 4), dtype=np.float32)
    pixels[1, 2] = bad
    with pytest.raises(ValueError, match="non-finite"):
        open_capture(pixels, DPI)

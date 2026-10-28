"""Focused tests for the standalone ``util/scrap_pack.py`` tool.

These tests intentionally use only synthetic rasters and the utility's public
API.  In particular, they do not import the paperholo package or an experiment.
"""
from __future__ import annotations

import binascii
import io
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import util.scrap_pack as scrap_pack
from util.scrap_pack import (Box, Placement, compose_packed, detect_boxes,
                             load_image, pack_boxes, save_lossless)


def _checker(h: int, w: int, dtype: np.dtype, rgb: bool) -> np.ndarray:
    """Strong two-axis texture with identical geometry at either bit depth."""
    dt = np.dtype(dtype)
    peak = np.iinfo(dt).max
    yy, xx = np.indices((h, w))
    bit = ((yy // 2 + xx // 2) & 1).astype(bool)
    mono = np.where(bit, round(0.12 * peak), round(0.86 * peak)).astype(dt)
    if not rgb:
        return mono
    # Keep all channels textured and non-identical so the color path is real.
    inverse = (peak - mono).astype(dt)
    third = np.where(bit, round(0.30 * peak), round(0.70 * peak)).astype(dt)
    return np.stack((mono, inverse, third), axis=-1)


def _scene(dtype: np.dtype, rgb: bool) -> tuple[np.ndarray, list[Box]]:
    dt = np.dtype(dtype)
    peak = np.iinfo(dt).max
    shape = (280, 400, 3) if rgb else (280, 400)
    image = np.full(shape, round(0.94 * peak), dtype=dt)
    truth = [Box(48, 56, 136, 152), Box(160, 240, 248, 352)]
    for box in truth:
        image[box.y0:box.y1, box.x0:box.x1] = _checker(
            box.y1 - box.y0, box.x1 - box.x0, dt, rgb)
    return image, truth


def _contains(box: Box, inner: Box) -> bool:
    return (box.y0 <= inner.y0 and box.x0 <= inner.x0
            and box.y1 >= inner.y1 and box.x1 >= inner.x1)


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
@pytest.mark.parametrize("rgb", [False, True])
def test_detects_gray_and_rgb_at_both_depths_and_expands_in_cells(
        dtype: np.dtype, rgb: bool) -> None:
    image, truth = _scene(dtype, rgb)
    base = sorted(detect_boxes(image, cell_px=8, margin_cells=0,
                               min_blocks=8), key=lambda b: b.x0)
    grown = sorted(detect_boxes(image, cell_px=8, margin_cells=3,
                                min_blocks=8), key=lambda b: b.x0)

    assert len(base) == len(grown) == len(truth)
    assert all(_contains(found, actual)
               for found, actual in zip(base, truth, strict=True))
    for before, after in zip(base, grown, strict=True):
        assert after == Box(max(0, before.y0 - 24),
                            max(0, before.x0 - 24),
                            min(image.shape[0], before.y1 + 24),
                            min(image.shape[1], before.x1 + 24))


def test_cell_expansion_closes_a_small_texture_gap_without_merging_ids() -> None:
    image = np.full((160, 240), 245, dtype=np.uint8)
    left = Box(48, 32, 112, 80)
    # Leave enough room for the coarse detector to keep two components before
    # the explicit two-cell expansion makes their coarse boxes touch.
    right = Box(48, 128, 112, 176)
    for box in (left, right):
        image[box.y0:box.y1, box.x0:box.x1] = _checker(
            box.y1 - box.y0, box.x1 - box.x0, np.uint8, False)

    separate = detect_boxes(image, cell_px=8, margin_cells=0, min_blocks=4)
    grown = detect_boxes(image, cell_px=8, margin_cells=2, min_blocks=4)

    assert len(separate) == 2
    assert len(grown) == 2
    grown = sorted(grown, key=lambda box: box.x0)
    assert grown[0].x1 >= grown[1].x0


def test_flat_raster_has_no_segments() -> None:
    flat = np.full((137, 181, 3), 62000, dtype=np.uint16)
    assert detect_boxes(flat, cell_px=8, margin_cells=4,
                        min_blocks=4) == []


def test_fully_transparent_rgba_texture_is_not_visible_payload() -> None:
    hidden, _truth = _scene(np.uint8, True)
    rgba = np.concatenate(
        (hidden, np.zeros(hidden.shape[:2] + (1,), dtype=np.uint8)), axis=2
    )

    assert detect_boxes(
        rgba, cell_px=8, margin_cells=2, min_blocks=8
    ) == []

    preview = Image.open(io.BytesIO(scrap_pack._preview_png(rgba, [])))
    assert preview.convert("RGB").getpixel((0, 0)) == (255, 255, 255)


def test_noise_gradient_and_single_edge_have_no_segments() -> None:
    rng = np.random.default_rng(2030)
    shape = (800, 1000)
    noise = np.clip(
        128.0 + rng.normal(0.0, 10.0, shape), 0, 255
    ).astype(np.uint8)
    gradient = np.broadcast_to(
        np.linspace(20, 230, shape[1], dtype=np.uint8), shape
    ).copy()
    _yy, xx = np.indices(shape)
    edge = np.where(xx < shape[1] // 2, 40, 220).astype(np.uint8)

    for image in (noise, gradient, edge):
        assert detect_boxes(
            image, cell_px=8, margin_cells=4, min_blocks=8
        ) == []


def _overlap(a: tuple[int, int, int, int],
             b: tuple[int, int, int, int]) -> bool:
    ay0, ax0, ay1, ax1 = a
    by0, bx0, by1, bx1 = b
    return ay0 < by1 and by0 < ay1 and ax0 < bx1 and bx0 < ax1


def test_pack_is_tight_nonoverlapping_and_compose_preserves_samples() -> None:
    # Each crop has unique samples; equality of the complete multisets catches
    # dropped, duplicated, interpolated, or background-substituted pixels.
    source = np.arange(80 * 96, dtype=np.uint16).reshape(80, 96)
    boxes = [Box(4, 5, 12, 13), Box(31, 43, 39, 51)]
    placements, height, width = pack_boxes(boxes)
    packed = compose_packed(source, boxes, placements, height, width)

    total_area = sum((b.y1 - b.y0) * (b.x1 - b.x0) for b in boxes)
    assert height * width == total_area
    assert packed.shape == (height, width)
    assert packed.dtype == source.dtype

    occupied: list[tuple[int, int, int, int]] = []
    for placement in placements:
        box = boxes[placement.source_index]
        bh, bw = box.y1 - box.y0, box.x1 - box.x0
        ph, pw = (bw, bh) if placement.rotated else (bh, bw)
        rect = (placement.y, placement.x,
                placement.y + ph, placement.x + pw)
        assert 0 <= rect[0] < rect[2] <= height
        assert 0 <= rect[1] < rect[3] <= width
        assert not any(_overlap(rect, other) for other in occupied)
        occupied.append(rect)

    wanted = np.concatenate([
        source[b.y0:b.y1, b.x0:b.x1].ravel() for b in boxes
    ])
    np.testing.assert_array_equal(np.sort(packed.ravel()), np.sort(wanted))


def test_compose_rotates_rectangular_crop_without_resampling() -> None:
    source = np.arange(6 * 8, dtype=np.uint16).reshape(6, 8)
    box = Box(1, 2, 3, 7)
    packed = compose_packed(
        source, [box], [Placement(0, 0, 0, True)], box.width, box.height
    )

    np.testing.assert_array_equal(
        packed, np.rot90(source[box.y0:box.y1, box.x0:box.x1])
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return (struct.pack(">I", len(payload)) + body
            + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF))


def _write_rgb16_png(path: Path, array: np.ndarray) -> None:
    """Write a standards-compliant RGB16 PNG without exercising tool code."""
    assert array.dtype == np.uint16 and array.ndim == 3 and array.shape[2] == 3
    h, w, _ = array.shape
    be = array.astype(">u2", copy=False).reshape(h, w * 3)
    scanlines = b"".join(b"\0" + row.tobytes() for row in be)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    path.write_bytes(signature + _png_chunk(b"IHDR", ihdr)
                     + _png_chunk(b"IDAT", zlib.compress(scanlines, 9))
                     + _png_chunk(b"IEND", b""))


def _samples(dtype: np.dtype, rgb: bool) -> np.ndarray:
    dt = np.dtype(dtype)
    peak = np.iinfo(dt).max
    yy, xx = np.indices((19, 23), dtype=np.uint32)
    gray = ((yy * 1777 + xx * 941 + yy * xx * 13) % (peak + 1)).astype(dt)
    if not rgb:
        return gray
    return np.stack((gray, (peak - gray).astype(dt),
                     ((gray.astype(np.uint32) * 17 + 31)
                      % (peak + 1)).astype(dt)), axis=-1)


def test_load_image_preserves_png_and_tiff_sample_types(tmp_path: Path) -> None:
    tifffile = pytest.importorskip("tifffile")
    fixtures: list[tuple[Path, np.ndarray]] = []

    gray8 = _samples(np.uint8, False)
    gray8_path = tmp_path / "gray8.png"
    Image.fromarray(gray8).save(gray8_path)
    fixtures.append((gray8_path, gray8))

    rgb8 = _samples(np.uint8, True)
    rgb8_path = tmp_path / "rgb8.png"
    Image.fromarray(rgb8).save(rgb8_path)
    fixtures.append((rgb8_path, rgb8))

    gray16 = _samples(np.uint16, False)
    gray16_path = tmp_path / "gray16.tiff"
    tifffile.imwrite(gray16_path, gray16)
    fixtures.append((gray16_path, gray16))

    rgb16 = _samples(np.uint16, True)
    rgb16_tiff_path = tmp_path / "rgb16.tiff"
    tifffile.imwrite(rgb16_tiff_path, rgb16, photometric="rgb")
    fixtures.append((rgb16_tiff_path, rgb16))
    rgb16_png_path = tmp_path / "rgb16.png"
    _write_rgb16_png(rgb16_png_path, rgb16)
    fixtures.append((rgb16_png_path, rgb16))

    for path, expected in fixtures:
        loaded = load_image(path)
        assert loaded.path == path
        assert loaded.array.shape == expected.shape, path.name
        assert loaded.array.dtype == expected.dtype, path.name
        np.testing.assert_array_equal(loaded.array, expected,
                                      err_msg=path.name)


def test_tiff_rejects_photometrics_that_would_change_visual_semantics(
        tmp_path: Path) -> None:
    tifffile = pytest.importorskip("tifffile")
    miniswhite = tmp_path / "miniswhite.tiff"
    tifffile.imwrite(
        miniswhite, _samples(np.uint8, False), photometric="miniswhite"
    )
    cmyk = tmp_path / "cmyk.tiff"
    tifffile.imwrite(
        cmyk, np.zeros((13, 17, 4), np.uint8), photometric="separated"
    )
    ycbcr = tmp_path / "ycbcr.tiff"
    tifffile.imwrite(
        ycbcr, np.zeros((13, 17, 3), np.uint8), photometric="ycbcr"
    )

    with pytest.raises(ValueError, match="MINISWHITE"):
        load_image(miniswhite)
    with pytest.raises(ValueError, match="CMYK/Separated"):
        load_image(cmyk)
    with pytest.raises(ValueError, match="YCBCR"):
        load_image(ycbcr)


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_rgba_tiff_requires_and_preserves_unassociated_alpha(
        tmp_path: Path, dtype: np.dtype) -> None:
    tifffile = pytest.importorskip("tifffile")
    rgb = _samples(dtype, True)
    peak = np.iinfo(dtype).max
    alpha = np.arange(rgb.shape[0] * rgb.shape[1], dtype=np.uint32)
    alpha = (alpha.reshape(rgb.shape[:2]) * 257 % (peak + 1)).astype(dtype)
    expected = np.concatenate((rgb, alpha[..., None]), axis=2)
    source = tmp_path / f"rgba-{np.dtype(dtype).itemsize * 8}.tiff"
    tifffile.imwrite(
        source, expected, photometric="rgb", extrasamples="unassalpha"
    )

    loaded = load_image(source).array
    np.testing.assert_array_equal(loaded, expected)
    output = Path(save_lossless(tmp_path / f"rgba-packed-{np.dtype(dtype).itemsize * 8}.tiff", loaded))
    np.testing.assert_array_equal(load_image(output).array, expected)
    with tifffile.TiffFile(output) as tif:
        assert {sample.name for sample in tif.pages[0].extrasamples} == {
            "UNASSALPHA"
        }


def test_big_endian_uint16_tiff_preserves_numeric_samples(tmp_path: Path) -> None:
    tifffile = pytest.importorskip("tifffile")
    expected = _samples(np.uint16, True)
    source = tmp_path / "rgb16-be.tiff"
    tifffile.imwrite(
        source, expected.astype(">u2"), photometric="rgb", byteorder=">"
    )

    loaded = load_image(source).array
    assert loaded.dtype.kind == "u" and loaded.dtype.itemsize == 2
    np.testing.assert_array_equal(loaded, expected)

    output = Path(save_lossless(tmp_path / "rgb16-be-packed.tiff", loaded))
    np.testing.assert_array_equal(load_image(output).array, expected)


@pytest.mark.parametrize(
    ("dtype", "rgb", "suffix"),
    [(np.uint8, False, ".png"),
     (np.uint16, False, ".png"),
     (np.uint8, True, ".png"),
     (np.uint16, True, ".png"),
     (np.uint16, True, ".tiff")],
)
def test_save_lossless_round_trip_keeps_depth_channels_and_values(
        tmp_path: Path, dtype: np.dtype, rgb: bool, suffix: str) -> None:
    expected = _samples(dtype, rgb)
    requested = tmp_path / f"packed{suffix}"
    actual = Path(save_lossless(requested, expected))

    assert actual.is_file()
    loaded = load_image(actual).array
    assert loaded.shape == expected.shape
    assert loaded.dtype == expected.dtype
    np.testing.assert_array_equal(loaded, expected)


def test_pure_headless_pipeline_never_needs_ui(tmp_path: Path) -> None:
    """The callable core is the deliberate approval bypass for automation."""
    source, _ = _scene(np.uint8, True)
    boxes = detect_boxes(source, cell_px=8, margin_cells=2, min_blocks=8)
    placements, height, width = pack_boxes(boxes)
    packed = compose_packed(source, boxes, placements, height, width)
    output = Path(save_lossless(tmp_path / "headless.png", packed))

    assert len(boxes) == 2
    assert output.is_file()
    np.testing.assert_array_equal(load_image(output).array, packed)


def test_preview_is_bounded_in_both_dimensions() -> None:
    tall = np.full((4000, 10), 240, np.uint8)
    preview = Image.open(io.BytesIO(
        scrap_pack._preview_png(tall, [], max_width=100)
    ))

    assert max(preview.size) <= 100


def test_cli_cancel_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    source, _ = _scene(np.uint8, False)
    input_path = tmp_path / "scan.png"
    Image.fromarray(source).save(input_path)
    output = tmp_path / "packed.png"
    monkeypatch.setattr(scrap_pack, "request_approval", lambda *_a, **_k: False)

    result = scrap_pack.main([
        str(input_path), "-o", str(output),
        "--cell-px", "8", "--margin-cells", "2", "--min-blocks", "8",
    ])

    assert result == 1
    assert not output.exists()

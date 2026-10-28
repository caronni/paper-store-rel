"""Oracle: holo2.scan == holo.receive.scan (capture ingest/authentication).

Compares the carried leaf against its source on identity (source SHA-256,
dpi, dtype, shape, channels), photometry (native crops and raw luma
crops, byte-exact), the bounds contract, the stat-memo re-authentication
behaviour, and refusal messages.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import holo2.capture.scan as h2
from holo.receive import scan as h1
from _oracle_fixtures import (  # noqa: F401  (pytest fixtures)
    grey_page, holo_sequential, rgb_page, small_grey)


def _write_png(path: Path, array: np.ndarray) -> Path:
    """PNG: decoded by Pillow (the non-memmap ingest branch)."""
    path = path.with_suffix(".png")
    Image.fromarray(array).save(path)
    return path


def _write_tiff(path: Path, array: np.ndarray) -> Path:
    """TIFF: the ``.tiff`` suffix selects the tifffile memmap branch."""
    path = path.with_suffix(".tiff")
    Image.fromarray(array).save(path, format="TIFF")
    return path


def _facts(raster) -> tuple:
    source = raster.source
    return (
        source.sha256, source.dpi, source.dtype, source.shape,
        source.channels, raster.dpi, raster.shape, raster.luma_max,
        str(raster.native_dtype),
    )


@pytest.mark.parametrize("writer", [_write_png, _write_tiff], ids=["png", "tiff"])
@pytest.mark.parametrize("colour", [False, True], ids=["grey", "rgb"])
def test_path_ingest_facts_and_pixels(
    tmp_path: Path, grey_page: np.ndarray, rgb_page: np.ndarray,
    writer, colour: bool,
) -> None:
    array = rgb_page if colour else grey_page
    path = writer(tmp_path / f"capture-{int(colour)}", array)

    one = h1.open_capture(path, 1200.0)
    two = h2.open_capture(path, 1200.0)

    assert _facts(two) == _facts(one)
    assert two.source_sha256 == one.source_sha256
    # The SHA is of the ENCODED bytes, so it must equal a plain file hash.
    import hashlib
    assert one.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()

    box = (17, 480, 33, 512)
    native_one, native_two = one.crop_native(*box), two.crop_native(*box)
    assert native_two.dtype == native_one.dtype
    np.testing.assert_array_equal(native_two, native_one)
    luma_one, luma_two = one.crop_luma(*box), two.crop_luma(*box)
    assert luma_two.dtype == luma_one.dtype == np.float32
    assert luma_two.tobytes() == luma_one.tobytes()
    assert not luma_two.flags.writeable


def test_uint16_dtype_is_not_coerced(tmp_path: Path, small_grey: np.ndarray) -> None:
    wide = (small_grey.astype(np.uint16) * 256)
    path = _write_tiff(tmp_path / "wide.tiff", wide)
    one, two = h1.open_capture(path, 4800.0), h2.open_capture(path, 4800.0)
    assert _facts(two) == _facts(one)
    assert two.source.dtype == "uint16"
    assert two.luma_max > 512.0  # the E021 16-bit amplitude branch
    np.testing.assert_array_equal(
        two.crop_native(0, 64, 0, 64), one.crop_native(0, 64, 0, 64))


def test_in_memory_array_identity(grey_page: np.ndarray, rgb_page: np.ndarray) -> None:
    for array in (grey_page, rgb_page):
        one, two = h1.open_capture(array, 1200.0), h2.open_capture(array, 1200.0)
        assert _facts(two) == _facts(one)
        # Detached at ingest: mutating the caller's array cannot reach in.
        before = two.crop_native(0, 4, 0, 4).copy()
        scratch = array.copy()
        third = h2.open_capture(scratch, 1200.0)
        scratch[0:4, 0:4] = 0
        np.testing.assert_array_equal(third.crop_native(0, 4, 0, 4), before)


def test_singleton_channel_is_canonicalized(small_grey: np.ndarray) -> None:
    singleton = small_grey[..., None]
    one, two = h1.open_capture(singleton, 600.0), h2.open_capture(singleton, 600.0)
    assert _facts(two) == _facts(one)
    assert two.source.channels == 1


def test_bounds_contract(small_grey: np.ndarray) -> None:
    one, two = h1.open_capture(small_grey, 600.0), h2.open_capture(small_grey, 600.0)
    cases = [
        (0, 1, 0, 1), (0, 600, 0, 600), (5, 5, 0, 10), (-1, 10, 0, 10),
        (0, 601, 0, 10), (0, 10, 0, 601), (0, True, 0, 10), (0.0, 10, 0, 10),
    ]
    for case in cases:
        assert two.contains(*case) is one.contains(*case), case
    with pytest.raises(ValueError) as excinfo_one:
        one.crop_luma(0, 601, 0, 10)
    with pytest.raises(ValueError) as excinfo_two:
        two.crop_luma(0, 601, 0, 10)
    assert str(excinfo_two.value) == str(excinfo_one.value)


def test_stat_memo_and_escalation(tmp_path: Path, small_grey: np.ndarray) -> None:
    """Unchanged path passes; same bytes re-written pass; new bytes refuse."""
    path = _write_png(tmp_path / "memo.png", small_grey)
    payload = path.read_bytes()
    one, two = h1.open_capture(path, 1200.0), h2.open_capture(path, 1200.0)

    # 1. Memo hit: nothing touched the file.
    one.verify_source_unchanged()
    two.verify_source_unchanged()

    # 2. Memo miss, cryptographic escalation passes: identical bytes, new
    #    inode/mtime.  Both leaves must accept and refresh the memo.
    path.unlink()
    path.write_bytes(payload)
    one.verify_source_unchanged()
    two.verify_source_unchanged()
    two.verify_source_unchanged()  # refreshed memo -> hit

    # 3. Escalation refuses: different bytes.
    mutated = bytearray(payload)
    mutated[-1] ^= 0xFF
    path.write_bytes(bytes(mutated))
    with pytest.raises(ValueError) as excinfo_one:
        one.verify_source_unchanged()
    with pytest.raises(ValueError) as excinfo_two:
        two.verify_source_unchanged()
    assert str(excinfo_two.value) == str(excinfo_one.value)

    # 4. Source gone at a retention barrier.
    path.unlink()
    with pytest.raises(ValueError) as excinfo_one:
        one.verify_source_unchanged()
    with pytest.raises(ValueError) as excinfo_two:
        two.verify_source_unchanged()
    assert str(excinfo_two.value) == str(excinfo_one.value)


def test_in_memory_source_needs_no_reauth(small_grey: np.ndarray) -> None:
    two = h2.open_capture(small_grey, 1200.0)
    two.verify_source_unchanged()  # detached at ingest; no path, no re-stream


@pytest.mark.parametrize(
    "case",
    [
        "rgba", "four_d", "bool", "complex", "empty_dim", "nonfinite",
        "dpi_zero", "dpi_nan", "dpi_bool",
    ],
)
def test_refusals_match(case: str, small_grey: np.ndarray) -> None:
    array, dpi = small_grey, 1200.0
    if case == "rgba":
        array = np.dstack([small_grey] * 4)
    elif case == "four_d":
        array = small_grey[None, None]
    elif case == "bool":
        array = small_grey > 128
    elif case == "complex":
        array = small_grey.astype(np.complex64)
    elif case == "empty_dim":
        array = small_grey[:0]
    elif case == "nonfinite":
        array = small_grey.astype(np.float32).copy()
        array[3, 3] = np.nan
    elif case == "dpi_zero":
        dpi = 0.0
    elif case == "dpi_nan":
        dpi = float("nan")
    elif case == "dpi_bool":
        dpi = True

    with pytest.raises(ValueError) as excinfo_one:
        h1.open_capture(array, dpi)
    with pytest.raises(ValueError) as excinfo_two:
        h2.open_capture(array, dpi)
    assert str(excinfo_two.value) == str(excinfo_one.value)


def test_missing_file_refusal(tmp_path: Path) -> None:
    absent = tmp_path / "nope.png"
    with pytest.raises(FileNotFoundError) as excinfo_one:
        h1.open_capture(absent, 1200.0)
    with pytest.raises(FileNotFoundError) as excinfo_two:
        h2.open_capture(absent, 1200.0)
    assert str(excinfo_two.value) == str(excinfo_one.value)


def test_source_id_validation_matches(small_grey: np.ndarray) -> None:
    good = dict(sha256="ab" * 32, dpi=1200.0, dtype="uint8",
                shape=(10, 20), channels=1)
    assert h2.SourceId(**good) == h2.SourceId(**good)
    for field, value in [
        ("sha256", "AB" * 32), ("sha256", "ab" * 31), ("dpi", 0.0),
        ("dpi", float("inf")), ("dtype", "not-a-dtype"), ("shape", (10,)),
        ("shape", (0, 20)), ("channels", 4),
    ]:
        broken = dict(good, **{field: value})
        with pytest.raises(ValueError) as excinfo_one:
            h1.SourceId(**broken)
        with pytest.raises(ValueError) as excinfo_two:
            h2.SourceId(**broken)
        assert str(excinfo_two.value) == str(excinfo_one.value), (field, value)


def test_multipage_tiff_refusal(tmp_path: Path, small_grey: np.ndarray) -> None:
    path = tmp_path / "pages.tiff"
    first = Image.fromarray(small_grey)
    first.save(path, format="TIFF", save_all=True,
               append_images=[Image.fromarray(small_grey[::-1])])
    with pytest.raises(ValueError) as excinfo_one:
        h1.open_capture(path, 1200.0)
    with pytest.raises(ValueError) as excinfo_two:
        h2.open_capture(path, 1200.0)
    assert str(excinfo_two.value) == str(excinfo_one.value)
    assert os.path.exists(path)

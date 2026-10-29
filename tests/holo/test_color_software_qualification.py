"""Historical M281 check and opt-in production emission/receiver gates.

Gate E re-home: the receiver leg is holo3's, addressed by the row's own
frozen ``L:`` fossil id — the same identity the page is emitted from
(R21, 2026-10-12: the fossil is the one legacy door).
The verdict is the CLI's exit code and the bytes it wrote, not a
receiver session file.

Both gates are opt-in behind HOLO_RUN_GS_TESTS=1 with ghostscript on
PATH — the one gs flag in tests/holo since 2026-09-20 (it replaced
HOLO_RUN_GS_COLOR_SEPARATIONS and HOLO_RUN_GS_COLOR_RECEIVER).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import warnings
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

from holo.format.descriptor import FormatSpec
from holo.format.fossils import resolve_fossil_spec
from holo.gen.emit import emit_volume
from holo.gen.ps import HW_DPI
from holo.qualification import color_distort

from _receive_free import decode_with_holo3


_ROOT = Path(__file__).resolve().parents[2]
_COLOR_ROWS = (
    "c2-cmy7-p120-v0",
    "c3-cmy7-p120-v0",
    "c2-cmy8-p120-v0",
    "c3-cmy8-p120-v0",
    # pooled -v1 rows (CMY8-POOLING-PLAN P5): same tile codec and
    # emission machinery, pooled outer code — the PS -> gs -> distortion
    # -> receiver chain must close them exactly like -v0.
    "c2-cmy8-p120-v1",
    "c3-cmy8-p120-v1",
)
# Each row's 6 mm A4 fossil, by pitch.
_FOSSIL_CELLS = {"c2": "3328x2304", "c3": "2240x1536"}
_PLATE_NAMES = ("Cyan", "Magenta", "Yellow", "Black")
_STRIPE_ROWS = 256


def _fossil_spec(coding_id: str) -> FormatSpec:
    return resolve_fossil_spec(
        f"{coding_id}@{_FOSSIL_CELLS[coding_id[:2]]}")


def _qualification_payload(coding_id: str, length: int) -> bytes:
    return hashlib.shake_256(
        b"holo/color-q1/" + coding_id.encode("ascii")
    ).digest(length)


def _separation_path(base: Path, name: str) -> Path:
    return base.with_name(f"{base.stem}({name}){base.suffix}")


def _assert_full_plate(
    path: Path,
    *,
    expected_packed: np.ndarray | None,
    page_size_xy: tuple[int, int],
    field_origin_yx: tuple[int, int],
    field_size_yx: tuple[int, int],
) -> None:
    """Compare one full plate in bounded stripes, including white margins."""
    page_w, page_h = page_size_xy
    field_y, field_x = field_origin_yx
    field_h, field_w = field_size_yx
    with Image.open(path) as source:
        assert source.size == page_size_xy
        for page_y0 in range(0, page_h, _STRIPE_ROWS):
            page_y1 = min(page_y0 + _STRIPE_ROWS, page_h)
            pixels = np.asarray(
                source.crop((0, page_y0, page_w, page_y1)).convert("L"),
                dtype=np.uint8,
            )
            assert np.all((pixels == 0) | (pixels == 255))
            ink = pixels < 128

            overlap_y0 = max(page_y0, field_y)
            overlap_y1 = min(page_y1, field_y + field_h)
            if expected_packed is not None and overlap_y0 < overlap_y1:
                truth_y0 = overlap_y0 - field_y
                truth_y1 = overlap_y1 - field_y
                truth = np.unpackbits(
                    expected_packed[truth_y0:truth_y1],
                    axis=1,
                    bitorder="big",
                )[:, :field_w].astype(bool, copy=False)
                plate_y0 = overlap_y0 - page_y0
                plate_y1 = overlap_y1 - page_y0
                got = ink[plate_y0:plate_y1, field_x:field_x + field_w]
                assert np.array_equal(got, truth)
                ink[plate_y0:plate_y1, field_x:field_x + field_w] = False

            # C/M/Y must be blank outside the authored field. K must be
            # blank over the complete page.
            assert not np.any(ink)


def _assert_full_rgb_composite(
    path: Path,
    *,
    expected_packed: np.ndarray,
    page_size_xy: tuple[int, int],
    field_origin_yx: tuple[int, int],
    field_size_yx: tuple[int, int],
) -> None:
    """Threshold a full RGB render in stripes and retain only its palette."""
    page_w, page_h = page_size_xy
    field_y, field_x = field_origin_yx
    field_h, field_w = field_size_yx
    palette_codes: set[int] = set()

    source = tifffile.memmap(path, mode="r")
    assert source.dtype == np.uint8
    assert source.shape == (page_h, page_w, 3)
    for page_y0 in range(0, page_h, _STRIPE_ROWS):
        page_y1 = min(page_y0 + _STRIPE_ROWS, page_h)
        pixels = np.asarray(source[page_y0:page_y1])
        codes = (
            (pixels[..., 0].astype(np.uint32) << 16)
            | (pixels[..., 1].astype(np.uint32) << 8)
            | pixels[..., 2].astype(np.uint32)
        )
        palette_codes.update(int(value) for value in np.unique(codes))
        assert len(palette_codes) <= 8

        overlap_y0 = max(page_y0, field_y)
        overlap_y1 = min(page_y1, field_y + field_h)
        if overlap_y0 < overlap_y1:
            truth_y0 = overlap_y0 - field_y
            truth_y1 = overlap_y1 - field_y
            plate_y0 = overlap_y0 - page_y0
            plate_y1 = overlap_y1 - page_y0
            for plane in range(3):
                truth = np.unpackbits(
                    expected_packed[plane, truth_y0:truth_y1],
                    axis=1,
                    bitorder="big",
                )[:, :field_w].astype(bool, copy=False)
                got = (
                    pixels[
                        plate_y0:plate_y1,
                        field_x:field_x + field_w,
                        plane,
                    ]
                    < 128
                )
                assert np.array_equal(got, truth)

        nonwhite = np.any(pixels != 255, axis=2)
        if overlap_y0 < overlap_y1:
            nonwhite[
                overlap_y0 - page_y0:overlap_y1 - page_y0,
                field_x:field_x + field_w,
            ] = False
        assert not np.any(nonwhite)

    palette = tuple(
        (code >> 16, (code >> 8) & 255, code & 255)
        for code in sorted(palette_codes)
    )
    assert 1 <= len(palette) <= 8
    assert all(
        not 120 <= channel < 136
        for color in palette
        for channel in color
    )
    signatures = {
        tuple(channel < 128 for channel in color) for color in palette}
    assert len(signatures) == len(palette)


def _render_ghostscript(
    postscript: Path,
    output: Path,
    *,
    device: str,
) -> None:
    subprocess.run(
        [
            "gs",
            "-dSAFER",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            f"-sDEVICE={device}",
            "-dTextAlphaBits=1",
            "-dGraphicsAlphaBits=1",
            f"-r{HW_DPI}",
            f"-sOutputFile={output}",
            str(postscript),
        ],
        check=True,
        capture_output=True,
        timeout=600,
    )


# One flag for every gs-gated slow path (2026-09-20): HOLO_RUN_GS_TESTS,
# the one test_characterize_gs_report already carried, plus which("gs").
@pytest.mark.skipif(
    shutil.which("gs") is None
    or os.environ.get("HOLO_RUN_GS_TESTS") != "1",
    reason=(
        "set HOLO_RUN_GS_TESTS=1 with ghostscript for the all-four-row "
        "full-production-page emission gate"
    ),
)
@pytest.mark.parametrize("coding_id", _COLOR_ROWS)
def test_q1_full_production_page_separations_match_plane_truth(
    tmp_path: Path,
    coding_id: str,
) -> None:
    """Production PS has exact separated and RGB-thresholded C/M/Y content."""
    spec = _fossil_spec(coding_id)
    payload = _qualification_payload(coding_id, 64)
    volume = emit_volume(
        spec,
        payload,
        0.35,
        tmp_path / f"{coding_id}-volume",
    )
    assert len(volume.pages) == 1
    page = volume.pages[0]
    assert page.gt_plane_sha256 is not None

    base = tmp_path / f"{coding_id}-separations.tif"
    _render_ghostscript(page.ps_path, base, device="tiffsep")

    packed = np.load(page.gt_path, allow_pickle=False)
    field_h, field_w = spec.layout.field_dots_yx
    assert packed.shape == (3, field_h, -(-field_w // 8))
    for plane in range(3):
        assert hashlib.sha256(
            packed[plane].tobytes(order="C")
        ).hexdigest() == page.gt_plane_sha256[plane]

    for plane, name in enumerate(_PLATE_NAMES):
        plate_path = _separation_path(base, name)
        assert plate_path.is_file()
        _assert_full_plate(
            plate_path,
            expected_packed=packed[plane] if plane < 3 else None,
            page_size_xy=spec.layout.page_dots_xy,
            field_origin_yx=spec.layout.origin_dots_yx,
            field_size_yx=spec.layout.field_dots_yx,
        )

    composite = tmp_path / f"{coding_id}-composite.tif"
    _render_ghostscript(page.ps_path, composite, device="tiff24nc")
    _assert_full_rgb_composite(
        composite,
        expected_packed=packed,
        page_size_xy=spec.layout.page_dots_xy,
        field_origin_yx=spec.layout.origin_dots_yx,
        field_size_yx=spec.layout.field_dots_yx,
    )


@pytest.mark.skipif(
    shutil.which("gs") is None
    or os.environ.get("HOLO_RUN_GS_TESTS") != "1",
    reason=(
        "set HOLO_RUN_GS_TESTS=1 with ghostscript for the slow "
        "all-four-row production-to-receiver gate"
    ),
)
@pytest.mark.parametrize("coding_id", _COLOR_ROWS)
def test_production_page_closes_through_standalone_tiff_transformer(
    tmp_path: Path,
    coding_id: str,
) -> None:
    """PS -> GS TIFF -> standalone TIFF tool -> receiver -> replayed bytes."""
    payload = _qualification_payload(coding_id, 64)
    spec = _fossil_spec(coding_id)
    volume = emit_volume(
        spec, payload, 0.35, tmp_path / f"{coding_id}-volume")
    assert len(volume.pages) == 1

    clean = tmp_path / f"{coding_id}-gs-600.tif"
    _render_ghostscript(
        volume.pages[0].ps_path, clean, device="tiff24nc")
    scan = tmp_path / f"{coding_id}-nominal-1200.tif"
    assert color_distort.main([
        str(clean),
        str(scan),
        "--profile", "nominal",
        "--seed", "20260727",
        "--output-dpi", "1200",
    ]) == 0

    # The printed identity is the row's own frozen fossil — the same one
    # the page was emitted from, spelled the way holo3 takes it.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        decode = decode_with_holo3(((scan, 1200.0),), "L:" + spec.spec_id,
                                   tmp_path, f"{coding_id}-receive")

    assert decode.exit_code == 0, decode.stdout
    assert decode.payload == payload
    assert decode.status == "verified"
    assert decode.report["run_done"]["n_bytes"] == len(payload)
    assert decode.report["run_done"]["payload_sha256"] == hashlib.sha256(
        payload).hexdigest()

"""Historical M281 check and opt-in production emission/receiver gates."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

from holo import cli
from holo.devices.profiles import make_spec
from holo.gen.emit import emit_volume
from holo.gen.ps import HW_DPI
from holo.qualification import color_distort
from holo.receive.session import load_session


_ROOT = Path(__file__).resolve().parents[2]
_M281_RECORD = _ROOT / "docs" / "COLOR-M281-CAL1-QUALIFICATION.json"
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
_PLATE_NAMES = ("Cyan", "Magenta", "Yellow", "Black")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STRIPE_ROWS = 256


def test_m281_operational_record_preserves_the_negative_result() -> None:
    """The full-page tool check must not be mistaken for receiver success."""
    report = json.loads(_M281_RECORD.read_text(encoding="utf-8"))

    assert report["schema"] == \
        "holo-color-m281-cal1-operational-check-v1"
    assert report["paper_qualification"] is False
    assert report["receiver_success"] is False
    assert _SHA256.fullmatch(report["tool_source_sha256_at_run"])
    assert _SHA256.fullmatch(report["simulator_source_sha256"])
    assert report["transform"]["status"] == "completed"
    assert report["transform"]["source"]["size_xy"] == [4960, 7016]
    assert report["transform"]["output"]["size_xy"] == [9920, 14032]
    receiver = report["receiver"]
    assert receiver["capture_status"] == "complete; committed"
    assert receiver["captures"] == 1
    assert receiver["levels"] == 3
    assert receiver["regions"] == 3
    for field in (
        "poses",
        "proposals",
        "attempts",
        "certificates",
        "evidence_blocks",
    ):
        assert receiver[field] == 0
    assert receiver["close_status"] == "open"
    assert "did not demonstrate acquisition" in report["interpretation"]


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


@pytest.mark.skipif(
    shutil.which("gs") is None
    or os.environ.get("HOLO_RUN_GS_COLOR_SEPARATIONS") != "1",
    reason=(
        "set HOLO_RUN_GS_COLOR_SEPARATIONS=1 for the all-four-row "
        "full-production-page emission gate"
    ),
)
@pytest.mark.parametrize("coding_id", _COLOR_ROWS)
def test_q1_full_production_page_separations_match_plane_truth(
    tmp_path: Path,
    coding_id: str,
) -> None:
    """Production PS has exact separated and RGB-thresholded C/M/Y content."""
    spec = make_spec(coding_id)
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
    or os.environ.get("HOLO_RUN_GS_COLOR_RECEIVER") != "1",
    reason=(
        "set HOLO_RUN_GS_COLOR_RECEIVER=1 for the slow all-four-row "
        "production-to-receiver gate"
    ),
)
@pytest.mark.parametrize("coding_id", _COLOR_ROWS)
def test_production_page_closes_through_standalone_tiff_transformer(
    tmp_path: Path,
    coding_id: str,
) -> None:
    """PS -> GS TIFF -> standalone TIFF tool -> receiver -> replayed bytes."""
    payload = _qualification_payload(coding_id, 64)
    spec = make_spec(coding_id)
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

    state_path = tmp_path / f"{coding_id}.receive.json"
    output_path = tmp_path / f"{coding_id}.payload.bin"
    assert cli.main([
        "decode",
        str(scan),
        "--scan-dpi",
        "1200",
        "--coding",
        coding_id,
        "--state",
        str(state_path),
        "--out",
        str(output_path),
        "--page",
        "0",
    ]) == 0
    assert output_path.read_bytes() == payload

    state = load_session(state_path, format_row_id=spec.spec_id)
    assert state.status.value == "verified"
    assert state.close.status.value == "verified"
    assert state.close.payload_length == len(payload)
    assert state.close.payload_sha256 == hashlib.sha256(payload).hexdigest()

"""analyze_scan's units and its structured refusals — the default lane.

Until 2026-09-20 this module was also the whole-page instrument proofs
and the calibration-report facets, which made it one xdist group of
~47 s and so the wall of both gated lanes.  Those left for
test_characterize_sweeps and test_characterize_reports; the painter
they share is _characterize_pages.  What stays here is what a commit
gets for free: the raster gates, the threshold fit, the role split, and
every structured refusal analyze_scan can return.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from PIL import Image

import holo.characterize.raster as raster_module
from holo.characterize.analyze import analyze_scan
from holo.characterize.emit import EMITTER_VERSION, PAGE_MANIFEST_SCHEMA
from holo.characterize.layout import build_page
from holo.characterize.sampling import _minimum_error_threshold
from holo.characterize.summarize import summarize_dpi_and_cells
from holo.characterize.statistics import split_roles, validate_split
from holo.characterize.raster import RasterSource

from _characterize_pages import (
    _candidate,
    _measure_calibration_candidate,
    _paint_page,
)


def test_binary_phase_threshold_is_fit_from_observed_classes() -> None:
    values = np.asarray([0.0, 0.0, 0.0, 4.0, 4.0, 5.0, 5.0, 5.0, 5.0, 9.0])
    expected_ink = np.asarray(
        [False, False, False, False, False, True, True, True, True, True]
    )

    threshold, error_rate = _minimum_error_threshold(values, expected_ink)

    assert 4.0 < threshold < 5.0
    assert error_rate == 0.0
    median_midpoint = 0.5 * (
        np.median(values[expected_ink])
        + np.median(values[~expected_ink])
    )
    assert np.mean((values > median_midpoint) != expected_ink) == 0.2


@pytest.mark.parametrize("dpi", (float("nan"), float("inf"), 0.0, -1.0))
def test_scan_dpi_must_be_finite_and_positive(dpi: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        analyze_scan(
            np.full((8, 8), 255, np.uint8),
            scan_dpi_x=dpi,
            scan_dpi_y=300.0,
        )


def test_cmyk_file_is_refused_instead_of_treated_as_rgb(
    tmp_path,
) -> None:
    path = tmp_path / "cmyk.tif"
    Image.new("CMYK", (16, 16), (0, 0, 0, 0)).save(path)

    with pytest.raises(ValueError, match="color model"):
        RasterSource(path)


def test_compressed_planar_rgb_tiff_falls_back_without_stale_axes(
    tmp_path,
) -> None:
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "planar-rgb.tif"
    planar = np.full((3, 40, 50), 255, np.uint8)
    tifffile.imwrite(
        path,
        planar,
        photometric="rgb",
        planarconfig="separate",
        compression="deflate",
    )

    source = RasterSource(path)

    assert source.spatial_shape == (40, 50)
    assert source.channels == 3
    assert source.color_model == "RGB"


def test_multipage_tiff_is_refused(
    tmp_path,
) -> None:
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "two-pages.tif"
    with tifffile.TiffWriter(path) as writer:
        writer.write(np.full((20, 30), 255, np.uint8))
        writer.write(np.full((20, 30), 0, np.uint8))

    with pytest.raises(ValueError, match="exactly one TIFF page"):
        RasterSource(path)


def test_large_compressed_tiff_is_refused_before_resident_decode(
    tmp_path,
    monkeypatch,
) -> None:
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "compressed.tif"
    tifffile.imwrite(
        path,
        np.full((40, 50), 255, np.uint8),
        compression="deflate",
    )
    monkeypatch.setattr(
        raster_module, "MAX_RESIDENT_FALLBACK_BYTES", 100
    )

    with pytest.raises(ValueError, match="contiguous uncompressed TIFF"):
        RasterSource(path)



# Two refusal laws read the same ideal bw calibration page, and painting
# a whole A4 is what either one costs; the sentinel arm copies before it
# erases (2026-09-20).
@pytest.fixture(scope="module")
def bw_calibration_page() -> tuple[dict, np.ndarray]:
    code = _candidate("bw", (300, 300), (2, 2))
    page = build_page(
        stage="calibration", kind="bw", copy_index=3,
        request_code=0, candidate_codes=(code,),
    )
    return page, _paint_page(page)


def test_current_manifest_must_match_printed_identity(
    bw_calibration_page: tuple[dict, np.ndarray],
) -> None:
    printed, scan = bw_calibration_page
    different = build_page(
        stage="calibration", kind="bw", copy_index=4,
        request_code=0,
        candidate_codes=tuple(printed["identity"]["candidate_codes"]),
    )
    manifest = {
        "schema": PAGE_MANIFEST_SCHEMA,
        "schema_version": EMITTER_VERSION,
        "emitter_version": EMITTER_VERSION,
        "stimulus_schema": printed["schema"],
        "page": different,
        "postscript": {},
    }

    report = analyze_scan(
        scan,
        scan_dpi_x=300,
        scan_dpi_y=300,
        manifest=manifest,
    )

    assert report["status"] == "refused"
    assert report["refusal"]["code"] == "manifest_identity_mismatch"


def test_non_object_manifest_returns_structured_refusal(
    tmp_path,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    report = analyze_scan(
        np.full((8, 8), 255, np.uint8),
        scan_dpi_x=300,
        scan_dpi_y=300,
        manifest=path,
    )

    assert report["status"] == "refused"
    assert report["refusal"]["code"] == "manifest_invalid"
    assert "JSON object" in report["refusal"]["detail"]


def test_blank_capture_is_a_structured_registration_refusal() -> None:
    scan = np.full((900, 700), 255, np.uint8)

    report = analyze_scan(scan, scan_dpi_x=100, scan_dpi_y=100)

    assert report["status"] == "refused"


def test_missing_end_sentinel_is_a_structured_integrity_refusal(
    bw_calibration_page: tuple[dict, np.ndarray],
) -> None:
    page, painted = bw_calibration_page
    scan = painted.copy()
    end = next(row for row in page["probes"] if row["probe_id"] == "end")
    x0 = round(end["x_source_dots"] * 300 / end["source_dpi"][0])
    y0 = round(end["y_source_dots"] * 300 / end["source_dpi"][1])
    width = round(end["w_source_dots"] * 300 / end["source_dpi"][0])
    height = round(end["h_source_dots"] * 300 / end["source_dpi"][1])
    scan[y0:y0 + height, x0:x0 + width] = 255

    report = analyze_scan(scan, scan_dpi_x=300, scan_dpi_y=300)

    assert report["status"] == "refused"
    assert report["refusal"]["code"] == "page_integrity_unobservable"
    assert "missing" in report["refusal"]["detail"]


def test_color_identity_refuses_grayscale_capture_before_measurement() -> None:
    code = _candidate("color", (300, 300), (2, 2))
    page = build_page(
        stage="calibration", kind="color", copy_index=2,
        request_code=0, candidate_codes=(code,),
    )

    report = analyze_scan(
        _paint_page(page), scan_dpi_x=300, scan_dpi_y=300
    )

    assert report["status"] == "refused"
    assert report["refusal"]["code"] == "color_scan_required"


def test_one_dot_cells_at_300_dpi_do_not_claim_usable_dpi() -> None:
    fine_code = _candidate("bw", (300, 300), (1, 1))
    fine_page = build_page(
        stage="calibration", kind="bw", copy_index=6,
        request_code=0, candidate_codes=(fine_code,),
    )

    rows, candidates, geometry = _measure_calibration_candidate(
        fine_page, fine_code, _paint_page(fine_page)
    )

    assert candidates[0]["provisional_usable"] is False
    assert {row["status"] for row in rows} == {"unmeasurable"}
    # The dpi claim is probe-derived, but an unusable candidate empties the
    # usable list before the rulers are consulted, so the whole-page verdict
    # (None) is reproduced with no rulers at all (2026-09-05).
    assert summarize_dpi_and_cells(candidates, {}, geometry)[
        "highest_useful_authored_grid_dpi"
    ] is None



def test_spatial_role_split_is_reproducible_mixed_and_complete() -> None:
    states = np.arange(128 * 96, dtype=np.uint8).reshape(96, 128) & 1
    first = split_roles(128, 96, field_key=0x123456789ABCDEF0)
    second = split_roles(128, 96, field_key=0x123456789ABCDEF0)

    assert np.array_equal(first, second)
    assert set(np.unique(first)) == {0, 1, 2, 3}
    audit = validate_split(first, states, 2)
    assert audit["complete"] is True
    assert audit["rows_with_all_roles_fraction"] > 0.95
    assert audit["columns_with_all_roles_fraction"] > 0.95
    assert hashlib.sha256(first.tobytes()).hexdigest() == (
        "468be567a842606e8ebe1d0b64a7990831840186fc6f10e197ce13c74167510b"
    )


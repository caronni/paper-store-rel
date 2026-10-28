from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import pytest
from PIL import Image

import holo.characterize.raster as raster_module
from holo.characterize.aggregate import combine_calibration_reports
from holo.characterize.analyze import analyze_scan
from holo.characterize.emit import EMITTER_VERSION, PAGE_MANIFEST_SCHEMA
from holo.characterize.geometry import register_blind
from holo.characterize.layout import build_page
from holo.characterize.sampling import _minimum_error_threshold
from holo.characterize.model import (
    BASE_DPI,
    CANDIDATES_BY_CODE,
    discovery_candidate_codes,
    Identity,
)
from holo.characterize.patterns import (
    expand_state_planes,
    field_states,
    pattern_bits,
)
from holo.characterize.statistics import split_roles, validate_split
from holo.characterize.raster import RasterSource
from holo.characterize.report import (
    DeviceSelfReport,
    encode_report_payload,
    payload_to_modules,
)
from holo.characterize.report_strips import (
    decode_report_strips,
    report_strip_consensus,
)


_SLOW_CHARACTERIZE = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason=(
        "set HOLO_RUN_SLOW_TESTS=1 for full-page synthetic "
        "characterization analysis"
    ),
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


def _candidate(kind: str, grid: tuple[int, int],
               cell: tuple[int, int]) -> int:
    return next(
        code for code, candidate in CANDIDATES_BY_CODE.items()
        if candidate.page_kind == kind
        and candidate.grid_dpi == grid
        and candidate.cell_dots == cell
        and candidate.emission_path == "single-plane-imagemask"
    )


def _paint_page(page: dict, *, dpi: int = 300,
                color: bool = False) -> np.ndarray:
    height = round(297.0 / 25.4 * dpi)
    width = round(210.0 / 25.4 * dpi)
    canvas = np.full(
        (height, width, 3) if color else (height, width), 255, np.uint8
    )

    def paint(bits: np.ndarray, x: int, y: int,
              source_dpi: tuple[int, int],
              planes: tuple[str, ...] = ("K",)) -> None:
        target_width = max(1, round(bits.shape[1] * dpi / source_dpi[0]))
        target_height = max(1, round(bits.shape[0] * dpi / source_dpi[1]))
        scaled = np.asarray(
            Image.fromarray((bits * 255).astype(np.uint8)).resize(
                (target_width, target_height), Image.Resampling.NEAREST
            )
        )
        x0 = round(x * dpi / source_dpi[0])
        y0 = round(y * dpi / source_dpi[1])
        crop = canvas[y0:y0 + target_height, x0:x0 + target_width]
        selected = scaled != 0
        if not color:
            crop[selected] = 0
        else:
            for plane in planes:
                if plane == "K":
                    crop[selected, :] = 0
                else:
                    channel = {"C": 0, "M": 1, "Y": 2}[plane]
                    crop[..., channel][selected] = 0

    identity_record = page["identity"]
    identity = Identity(
        stage=identity_record["stage"],
        kind=identity_record["kind"],
        copy_index=identity_record["copy_index"],
        request_code=identity_record["request_code"],
        candidate_codes=tuple(identity_record["candidate_codes"]),
        layout_digest=identity_record["layout_digest"],
    )
    device = DeviceSelfReport(
        language_level=3,
        default_resolution=(600, 600),
        effective_resolution=(600, 600),
        page_size_points=(595, 842),
        imaging_bbox=(0, 0, 595, 842),
        duplex=False,
        tumble=False,
        process_color_model=("DeviceRGB" if color else "DeviceGray"),
        product="synthetic-printer",
        version="1",
        revision=1,
        serial="synthetic-001",
        print_nonce=identity.copy_index + 1,
    )
    report_modules = payload_to_modules(
        encode_report_payload(identity, device)
    )
    for record in page["infrastructure"]:
        if record["kind"] == "corner_mark":
            bits = pattern_bits({
                "kind": "chiral_corner",
                "w_source_dots": record["w_layout_dots"],
                "h_source_dots": record["h_layout_dots"],
                "params": {
                    "satellites": record["satellites"],
                    "inward": record["inward"],
                    "stroke_dots": 3,
                },
            })
            paint(
                bits, record["x_layout_dots"], record["y_layout_dots"],
                (BASE_DPI, BASE_DPI),
            )
        elif record["kind"] == "geometry_plus":
            bits = pattern_bits({
                "kind": "plus_mark",
                "w_source_dots": record["w_layout_dots"],
                "h_source_dots": record["h_layout_dots"],
                "params": {"stroke_dots": 3},
            })
            paint(
                bits, record["x_layout_dots"], record["y_layout_dots"],
                (BASE_DPI, BASE_DPI),
            )
        elif record["kind"] == "machine_report":
            module = record["module_layout_dots"]
            bits = np.repeat(
                np.repeat(report_modules, module, axis=0), module, axis=1
            )
            paint(
                bits,
                record["x_layout_dots"],
                record["y_layout_dots"],
                (BASE_DPI, BASE_DPI),
            )

    for probe in page["probes"]:
        params = probe.get("params", {})
        paint(
            pattern_bits(probe),
            probe["x_source_dots"],
            probe["y_source_dots"],
            tuple(probe["source_dpi"]),
            tuple(params.get("planes", (probe["plane"],))),
        )
    for field in page["fields"]:
        candidate = CANDIDATES_BY_CODE[field["candidate_code"]]
        planes = expand_state_planes(field_states(field, candidate), candidate)
        for plane, bits in planes.items():
            paint(
                bits,
                field["x_source_dots"],
                field["y_source_dots"],
                candidate.grid_dpi,
                (plane,),
            )
    return canvas


@pytest.mark.parametrize(
    ("kind", "color", "ruler_planes"),
    (
        ("bw", False, {"K"}),
        ("color", True, {"K", "C", "M", "Y"}),
    ),
)
@_SLOW_CHARACTERIZE
def test_full_discovery_pair_is_manifestless_and_measurable(
    kind: str,
    color: bool,
    ruler_planes: set[str],
) -> None:
    page = build_page(
        stage="discovery",
        kind=kind,
        copy_index=2,
        request_code=0,
    )

    report = analyze_scan(
        _paint_page(page, color=color),
        scan_dpi_x=300,
        scan_dpi_y=300,
    )

    assert report["status"] == "ok"
    assert report["page_identity"]["stage"] == "discovery"
    assert len(report["summary"]["candidate_results"]) == len(
        discovery_candidate_codes(kind)
    )
    assert report["summary"]["dpi_and_cells"][
        "highest_useful_authored_grid_dpi"
    ] is not None
    for grid in report["summary"]["dpi_and_cells"]["grids"]:
        assert set(grid["ruler"]["planes"]) == ruler_planes
        assert grid["ruler"]["complete"] is True
        assert all(
            set(plane["diagnostics"]) == {
                "g1-v", "g1-h", "g2-v", "g2-h", "dots", "line-pair"
            }
            for plane in grid["ruler"]["planes"].values()
        )
    diagnostics = report["summary"]["diagnostics"]
    if kind == "bw":
        assert len(diagnostics["morphology"]) == 20
        assert {
            row["kind"] for row in diagnostics["morphology"]
        } >= {
            "line_width",
            "isolated_dots",
            "white_holes",
            "checker",
            "slanted_edge",
            "microtext",
        }
    else:
        assert {
            row["alphabet"]
            for row in report["summary"]["candidate_results"]
        } >= {"CM4", "CMY7", "CMY8", "KCMY4"}
        assert {
            row["plane"] for row in diagnostics["color_selectivity"]
        } == {"C", "M", "Y"}


@_SLOW_CHARACTERIZE
def test_calibration_analysis_is_manifestless_and_held_out() -> None:
    code = _candidate("bw", (300, 300), (2, 2))
    page = build_page(
        stage="calibration", kind="bw", copy_index=3,
        request_code=0, candidate_codes=(code,),
    )
    scan = _paint_page(page)

    report = analyze_scan(scan, scan_dpi_x=300, scan_dpi_y=300)

    assert report["status"] == "ok"
    assert report["page_identity"]["copy_index"] == 3
    assert report["machine_report"]["consensus"]["n_valid"] == 2
    assert report["machine_report"]["identity"]["candidate_codes"] == [code]
    assert report["machine_report"]["device_readback"][
        "default_resolution"
    ] == [600, 600]
    assert report["machine_report"]["device_readback"][
        "effective_resolution"
    ] == [600, 600]
    assert "print_nonce" not in report["device_footing"]["fields"]
    candidate = report["summary"]["candidate_results"][0]
    assert candidate["candidate_code"] == code
    assert candidate["provisional_usable"] is True
    assert candidate["n_fields_expected"] == 6
    assert report["summary"]["dpi_and_cells"][
        "highest_useful_authored_grid_dpi"
    ] == [300, 300]
    ink = report["summary"]["diagnostics"]["physical_ink_extent"]
    physical_edges = ink["edges"]
    assert all(row["complete"] for row in physical_edges.values())
    assert all(len(row["ticks"]) == 13 for row in physical_edges.values())
    # Ideal render: every observable tick registers as fully printed (the
    # gap-0 tick's footprint touches the raster boundary and stays an
    # honest unobservable), so the ladder is safe from the first
    # observable rung and the clip estimate is bounded by that rung.
    assert all(
        tick["classification"] == "full"
        or (tick["gap_mm"] == 0.0
            and tick["classification"] == "unobservable")
        for row in physical_edges.values() for tick in row["ticks"]
    )
    assert all(
        row["safe_gap_mm"] == 0.5 for row in physical_edges.values()
    )
    assert all(
        row["first_partial_gap_mm"] is None
        for row in physical_edges.values()
    )
    assert all(
        value is not None and value < 0.70
        for value in ink["printable_clip_mm"].values()
    )
    payload_edges = report["summary"]["payload_extent"]["edges"]
    assert all(row["complete"] for row in payload_edges.values())
    assert all(len(row["gaps"]) == 8 for row in payload_edges.values())
    # Data-only edge curves (workplan W3): no verdict keys anywhere.
    assert all(
        "passed" not in gap and "exact_references_ok" not in gap
        for row in payload_edges.values() for gap in row["gaps"]
    )
    assert all(
        curve["edge_flat_gap_mm"] == 0.5
        for row in payload_edges.values()
        for curve in row["arm_curves"].values()
    )
    capacity = report["summary"]["capacity_by_margin_mm"]["margins"]
    assert [row["source"] for row in capacity].count(
        "measured-clip-worst-edge"
    ) == 1
    measured = next(
        row for row in capacity
        if row["source"] == "measured-clip-worst-edge"
    )
    assert measured["margin_mm"] <= 0.70
    assert len(measured["candidates"]) == 1
    assert measured["candidates"][0]["empirical_information_bits"] > 0
    rungs = report["summary"]["rung_planning"]["rows"]
    assert len(rungs) == 1 and rungs[0]["candidate_code"] == code
    assert rungs[0]["rungs"]["r0550"]["supported_at"]["p95"] is True
    registration = report["summary"]["registration_map"]
    assert registration["n_observations"] > 30
    assert registration["max_displacement_layout_dots"] <= 2.0
    paper_edges = report["geometry"]["paper_edges"]["edges"]
    assert set(paper_edges) == {"top", "bottom", "left", "right"}
    phase_rails = [
        row for row in report["probe_measurements"]
        if row["group"] == "transport-geometry"
    ]
    assert {row["probe_id"] for row in phase_rails} == {
        "geometry/phase-x", "geometry/phase-y"
    }
    assert all(
        row["status"] == "ok" and row["pattern"]["scorable"]
        for row in phase_rails
    )
    tone = report["summary"]["diagnostics"]["tone_profiles"]
    assert len(tone) == 1
    profile = tone[0]["profile"]
    assert profile["axis"] == "x"
    assert profile["n_bins"] == len(profile["density_bins"])
    assert profile["n_bins"] == len(
        profile["axis_position_page_mm"]
    )
    assert profile["axis_position_page_mm"] == sorted(
        profile["axis_position_page_mm"]
    )
    assert profile["density_rms"] >= 0.0
    assert profile["detrended_rms_density"] >= 0.0


def test_current_manifest_must_match_printed_identity() -> None:
    code = _candidate("bw", (300, 300), (2, 2))
    printed = build_page(
        stage="calibration", kind="bw", copy_index=3,
        request_code=0, candidate_codes=(code,),
    )
    different = build_page(
        stage="calibration", kind="bw", copy_index=4,
        request_code=0, candidate_codes=(code,),
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
        _paint_page(printed),
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
    assert report["refusal"]["code"] == "corner_registration_failed"


def test_missing_end_sentinel_is_a_structured_integrity_refusal() -> None:
    code = _candidate("bw", (300, 300), (2, 2))
    page = build_page(
        stage="calibration", kind="bw", copy_index=12,
        request_code=0, candidate_codes=(code,),
    )
    scan = _paint_page(page)
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


@_SLOW_CHARACTERIZE
def test_low_samples_per_cell_and_scaled_pages_do_not_claim_usable_dpi() -> None:
    fine_code = _candidate("bw", (300, 300), (1, 1))
    fine_page = build_page(
        stage="calibration", kind="bw", copy_index=6,
        request_code=0, candidate_codes=(fine_code,),
    )
    undersampled = analyze_scan(
        _paint_page(fine_page), scan_dpi_x=300, scan_dpi_y=300
    )
    assert undersampled["status"] == "ok"
    assert undersampled["summary"]["candidate_results"][0][
        "provisional_usable"
    ] is False
    assert undersampled["summary"]["dpi_and_cells"][
        "highest_useful_authored_grid_dpi"
    ] is None
    core = [
        row for row in undersampled["field_measurements"]
        if row["family"] == "calibration"
    ]
    assert {row["status"] for row in core} == {"unmeasurable"}

    robust_code = _candidate("bw", (300, 300), (2, 2))
    robust_page = build_page(
        stage="calibration", kind="bw", copy_index=7,
        request_code=0, candidate_codes=(robust_code,),
    )
    nominal = _paint_page(robust_page)
    shrunken = np.asarray(
        Image.fromarray(nominal).resize(
            (
                round(nominal.shape[1] * 0.90),
                round(nominal.shape[0] * 0.90),
            ),
            Image.Resampling.NEAREST,
        )
    )
    scaled_capture = np.full_like(nominal, 255)
    scaled_capture[:shrunken.shape[0], :shrunken.shape[1]] = shrunken
    scaled = analyze_scan(
        scaled_capture, scan_dpi_x=300, scan_dpi_y=300
    )
    assert scaled["status"] == "ok"
    dpi = scaled["summary"]["dpi_and_cells"]
    assert dpi["physical_scale_status"] == "scaled"
    assert dpi["highest_useful_authored_grid_dpi"] is None


@_SLOW_CHARACTERIZE
def test_color_page_measures_planes_registration_and_selectivity() -> None:
    code = _candidate("color", (300, 300), (2, 2))
    page = build_page(
        stage="calibration", kind="color", copy_index=5,
        request_code=0, candidate_codes=(code,),
    )

    report = analyze_scan(
        _paint_page(page, color=True), scan_dpi_x=300, scan_dpi_y=300
    )

    assert report["status"] == "ok"
    assert report["summary"]["candidate_results"][0][
        "provisional_usable"
    ] is True
    diagnostics = report["summary"]["diagnostics"]
    assert diagnostics["plane_registration"]["complete_target_count"] == 1
    assert {
        row["probe_id"] for row in diagnostics["scanner_adequacy"]
    } == {
        "scanner/c3",
        "scanner/c2",
        "scanner/g2/horizontal_lines",
        "scanner/g2/vertical_lines",
        "scanner/entropy",
        "quiet/main",
    }
    scanner = diagnostics["scanner_adequacy_summary"]
    assert scanner["status"] == "complete"
    assert scanner["missing_roles"] == []
    assert scanner["duplicated_roles"] == []
    assert scanner["checks"]["compression"]["verdict"] == "indeterminate"
    solid_verdict = scanner["mode_classes"]["solid_class"]["verdict"]
    c2_verdict = scanner["mode_classes"]["c2_class"]["verdict"]
    assert solid_verdict in {"adequate", "inadequate"}
    if solid_verdict == "inadequate":
        assert scanner["verdict"] == "inadequate"
        assert c2_verdict == "inadequate"
    else:
        assert c2_verdict == "indeterminate"


@_SLOW_CHARACTERIZE
def test_color_phase_threshold_handles_skewed_cmy8_densities() -> None:
    code = next(
        candidate.code for candidate in CANDIDATES_BY_CODE.values()
        if candidate.page_kind == "color"
        and candidate.grid_dpi == (300, 300)
        and candidate.cell_dots == (2, 2)
        and candidate.alphabet == "CMY8"
    )
    page = build_page(
        stage="calibration", kind="color", copy_index=6,
        request_code=0, candidate_codes=(code,),
    )
    scan = _paint_page(page, color=True)
    c_only = (
        (scan[..., 0] == 0)
        & (scan[..., 1] == 255)
        & (scan[..., 2] == 255)
    )
    scan[..., 0][c_only] = 64

    report = analyze_scan(
        scan, scan_dpi_x=300, scan_dpi_y=300
    )

    assert report["status"] == "ok"
    result = report["summary"]["candidate_results"][0]
    assert result["candidate_code"] == code
    assert result["n_fields_measured"] == 6
    fields = [
        row for row in report["field_measurements"]
        if row["candidate_code"] == code and row["family"] == "calibration"
    ]
    assert all(
        window["phase"]["C"]["ok"]
        for row in fields
        for window in row["windows"]
    )


@_SLOW_CHARACTERIZE
def test_nested_multilevel_candidate_retains_multibit_motif_evidence() -> None:
    code = next(
        candidate.code for candidate in CANDIDATES_BY_CODE.values()
        if candidate.page_kind == "bw" and candidate.alphabet == "K4"
    )
    page = build_page(
        stage="calibration", kind="bw", copy_index=8,
        request_code=0, candidate_codes=(code,),
    )

    report = analyze_scan(
        _paint_page(page), scan_dpi_x=300, scan_dpi_y=300
    )

    assert report["status"] == "ok"
    result = report["summary"]["candidate_results"][0]
    assert result["candidate_code"] == code
    assert result["alphabet"] == "K4"
    assert result["n_fields_measured"] >= 2
    assert result["minimum_mutual_information_bits_per_cell"] > 1.2
    assert (
        result["minimum_generalized_mutual_information_bits_per_cell"]
        > 1.2
    )


@_SLOW_CHARACTERIZE
def test_calibration_combination_keeps_worst_copy_and_exact_extent() -> None:
    code = _candidate("bw", (300, 300), (2, 2))
    reports = []
    for copy_index in (30, 31):
        page = build_page(
            stage="calibration", kind="bw", copy_index=copy_index,
            request_code=0, candidate_codes=(code,),
        )
        reports.append(analyze_scan(
            _paint_page(page),
            scan_dpi_x=300,
            scan_dpi_y=300,
            footing={
                "printer": "synthetic",
                "print_path": "synthetic",
                "media": "synthetic",
                "scanner": "synthetic",
                "scan_mode": "synthetic",
                "print_session": f"session-{copy_index}",
            },
        ))

    assert (
        reports[0]["machine_report"]["device_readback"]["print_nonce"]
        != reports[1]["machine_report"]["device_readback"]["print_nonce"]
    )
    assert (
        reports[0]["device_footing"]["semantic_sha256"]
        == reports[1]["device_footing"]["semantic_sha256"]
    )
    combined = combine_calibration_reports(reports)

    assert combined["copy_indices"] == [30, 31]
    assert combined["print_sessions"] == ["session-30", "session-31"]
    assert combined["candidate_results"][0]["calibrated_usable"] is True
    clip = combined["payload_extent"]["printable_clip_mm_worst_copy"]
    assert all(
        clip[edge] is not None and clip[edge] < 0.70
        for edge in ("left", "top", "right", "bottom")
    )
    assert len(combined["payload_extent"]["capacity_at_worst_clip"]) == 1
    assert "K" in combined["cross_copy_diagnostics"]["tone_mid"]


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


def test_manifestless_identity_survives_all_rotations_and_mirrors() -> None:
    code = _candidate("bw", (300, 300), (2, 2))
    page = build_page(
        stage="calibration", kind="bw", copy_index=23,
        request_code=0, candidate_codes=(code,),
    )
    expected = page["identity"]
    upright = _paint_page(page)

    for mirrored in (False, True):
        base = np.fliplr(upright) if mirrored else upright
        for rotations in range(4):
            transformed = np.rot90(base, rotations).copy()
            source = RasterSource(transformed)
            affine, _geometry = register_blind(
                source, 300, 300,
                corner_layout=page["infrastructure"],
            )
            observations = decode_report_strips(
                source, affine, [
                    row for row in page["infrastructure"]
                    if row["kind"] == "machine_report"
                ]
            )
            decoded, diagnostics = report_strip_consensus(observations)
            assert decoded is not None, (mirrored, rotations, diagnostics)
            assert decoded.identity.matches(Identity(
                stage=expected["stage"],
                kind=expected["kind"],
                copy_index=expected["copy_index"],
                request_code=expected["request_code"],
                candidate_codes=tuple(expected["candidate_codes"]),
                layout_digest=expected["layout_digest"],
            ))

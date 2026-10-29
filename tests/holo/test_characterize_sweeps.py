"""The characterize instrument sweep lane: whole-page analyze_scan proofs.

Split out of test_characterize_analyze (2026-09-20): these are the proofs
that paint a whole A4 page and run the instrument's own entry point over
it, and one module is one xdist group, so they parallelize against the
calibration-report facets in test_characterize_reports instead of
serializing behind them.

Whole-page proofs of the import-firewalled discovery instrument, which
have no claim on the curated slow lane (seven-coding payload gate +
measured-channel gates).  Run before any src/holo/characterize change:
HOLO_RUN_CHARACTERIZE_SWEEPS=1.
"""
from __future__ import annotations

import os

import numpy as np
import pytest
from PIL import Image

from holo.characterize.analyze import analyze_scan
from holo.characterize.geometry import register_blind
from holo.characterize.layout import build_page
from holo.characterize.model import (
    discovery_candidate_codes,
    Identity,
)
from holo.characterize.raster import RasterSource
from holo.characterize.report_strips import (
    decode_report_strips,
    report_strip_consensus,
)

from _characterize_pages import _candidate, _paint_page


_CHARACTERIZE_SWEEPS = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_CHARACTERIZE_SWEEPS") != "1",
    reason=(
        "set HOLO_RUN_CHARACTERIZE_SWEEPS=1 for whole-page characterize "
        "instrument sweeps"
    ),
)


@pytest.mark.parametrize(
    ("kind", "color", "ruler_planes"),
    (
        ("bw", False, {"K"}),
        ("color", True, {"K", "C", "M", "Y"}),
    ),
)
@_CHARACTERIZE_SWEEPS
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


@_CHARACTERIZE_SWEEPS
def test_a_shrunken_capture_is_scaled_and_claims_no_usable_dpi() -> None:
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


@_CHARACTERIZE_SWEEPS
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


# Ungated until 2026-09-20 in test_characterize_analyze: 7.8 s of the
# default lane to paint an A4 and read it back in eight orientations.
@_CHARACTERIZE_SWEEPS
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

"""The calibration report read facet by facet, and the two slow arms.

Split out of test_characterize_analyze (2026-09-20): one ideal bw copy
pair is analysed once as a session fixture, and seven narrow readers —
six of one report, one of the pair — pin one facet each.  One module
is one xdist group, so keeping the fixture and its readers together
(and the whole-page proofs in test_characterize_sweeps apart) lets the
two run side by side instead of behind one another.

The readers carry the sweeps flag their own lane gave them
(HOLO_RUN_CHARACTERIZE_SWEEPS=1, before any src/holo/characterize
change); the two composed measurement arms below them stay on the
curated slow lane (HOLO_RUN_SLOW_TESTS=1).
"""
from __future__ import annotations

import os

import pytest

from holo.characterize.aggregate import combine_calibration_reports
from holo.characterize.analyze import analyze_scan
from holo.characterize.layout import build_page
from holo.characterize.model import CANDIDATES_BY_CODE

from _characterize_pages import (
    _candidate,
    _measure_calibration_candidate,
    _paint_page,
)


_SLOW_CHARACTERIZE = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason=(
        "set HOLO_RUN_SLOW_TESTS=1 for full-page synthetic "
        "characterization analysis"
    ),
)

# The characterize instrument sweep lane (2026-09-05): whole-page analyze_scan
# proofs of the import-firewalled discovery instrument, which have no claim on
# the curated slow lane (seven-coding payload gate + measured-channel gates).
# Run before any src/holo/characterize change: HOLO_RUN_CHARACTERIZE_SWEEPS=1.
_CHARACTERIZE_SWEEPS = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_CHARACTERIZE_SWEEPS") != "1",
    reason=(
        "set HOLO_RUN_CHARACTERIZE_SWEEPS=1 for whole-page characterize "
        "instrument sweeps"
    ),
)


# One ideal bw 300x300 cell-2x2 pair, analysed once for both the cross-copy
# combination law and the held-out single-report laws; the render is ideal, so
# every measured verdict is copy-invariant (2026-09-05).
@pytest.fixture(scope="session")
def calibration_bw_reports() -> list[dict]:
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
    return reports



@_CHARACTERIZE_SWEEPS
def test_calibration_analysis_is_manifestless_and_held_out(
    calibration_bw_reports: list[dict],
) -> None:
    code = _candidate("bw", (300, 300), (2, 2))

    report = calibration_bw_reports[0]

    assert report["status"] == "ok"
    assert report["page_identity"]["copy_index"] == 30
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


@_CHARACTERIZE_SWEEPS
def test_physical_ink_extent_ladder_is_complete_and_safe_on_an_ideal_render(
    calibration_bw_reports: list[dict],
) -> None:
    report = calibration_bw_reports[0]

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


@_CHARACTERIZE_SWEEPS
def test_payload_extent_edges_carry_curves_and_no_verdicts(
    calibration_bw_reports: list[dict],
) -> None:
    report = calibration_bw_reports[0]

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


@_CHARACTERIZE_SWEEPS
def test_capacity_and_rung_planning_price_the_measured_worst_edge_clip(
    calibration_bw_reports: list[dict],
) -> None:
    code = _candidate("bw", (300, 300), (2, 2))
    report = calibration_bw_reports[0]

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


@_CHARACTERIZE_SWEEPS
def test_registration_map_and_paper_edges_come_from_the_measured_page(
    calibration_bw_reports: list[dict],
) -> None:
    report = calibration_bw_reports[0]

    registration = report["summary"]["registration_map"]
    assert registration["n_observations"] > 30
    assert registration["max_displacement_layout_dots"] <= 2.0
    paper_edges = report["geometry"]["paper_edges"]["edges"]
    assert set(paper_edges) == {"top", "bottom", "left", "right"}


@_CHARACTERIZE_SWEEPS
def test_phase_rails_and_the_tone_profile_are_scorable_and_monotone(
    calibration_bw_reports: list[dict],
) -> None:
    report = calibration_bw_reports[0]

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

    fields, candidates, _geometry = _measure_calibration_candidate(
        page, code, scan
    )

    result = candidates[0]
    assert result["candidate_code"] == code
    assert result["n_fields_measured"] == 6
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

    _fields, candidates, _geometry = _measure_calibration_candidate(
        page, code, _paint_page(page)
    )

    # All six calibration fields, never the two measurable ones: the pinned
    # numbers are minima over fields, so pre-selecting would freeze them.
    result = candidates[0]
    assert result["candidate_code"] == code
    assert result["alphabet"] == "K4"
    assert result["n_fields_measured"] >= 2
    assert result["minimum_mutual_information_bits_per_cell"] > 1.2
    assert (
        result["minimum_generalized_mutual_information_bits_per_cell"]
        > 1.2
    )



@_CHARACTERIZE_SWEEPS
def test_calibration_combination_keeps_worst_copy_and_exact_extent(
    calibration_bw_reports: list[dict],
) -> None:
    reports = calibration_bw_reports

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


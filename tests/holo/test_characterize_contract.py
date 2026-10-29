from __future__ import annotations

import os

import pytest

from holo.characterize.aggregate import combine_calibration_reports
from holo.characterize.layout import build_page, verify_page
from holo.characterize.model import (
    BASE_DPI,
    CANDIDATES_BY_CODE,
    CANDIDATES_BY_ID,
    REPORT_SCHEMA,
    REQUEST_CODES,
    discovery_candidate_codes,
    semantic_digest,
)
from holo.characterize.shortlist import (
    shortlist_candidate_codes,
    shortlist_details,
)
from holo.characterize.summarize import summarize_grid_rulers
from holo.characterize.summarize_physical import (
    PAYLOAD_CANARY_GAPS,
    PHYSICAL_TICK_GAPS,
)


_SLOW_CONTRACT = pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason=(
        "set HOLO_RUN_SLOW_TESTS=1 for the whole-registry layout proof"
    ),
)


def test_registry_keeps_every_measurement_axis_in_candidate_identity() -> None:
    assert len(CANDIDATES_BY_CODE) == 86
    assert len(discovery_candidate_codes("bw")) == 34
    assert len(discovery_candidate_codes("color")) == 52
    assert len(CANDIDATES_BY_ID) == len(CANDIDATES_BY_CODE)
    identities = {
        candidate.identity_tuple(REQUEST_CODES["default"])
        for candidate in CANDIDATES_BY_CODE.values()
    }
    assert len(identities) == len(CANDIDATES_BY_CODE)
    assert {
        candidate.grid_dpi for candidate in CANDIDATES_BY_CODE.values()
    } == {
        (300, 300), (600, 600), (1200, 1200),
        (2400, 2400), (1200, 2400),
    }
    bw = [
        candidate for candidate in CANDIDATES_BY_CODE.values()
        if candidate.page_kind == "bw"
    ]
    assert {
        candidate.symbol_shape for candidate in bw
        if candidate.grid_dpi == (600, 600)
        and candidate.cell_dots == (2, 2)
    } >= {"solid", "diagonal", "horizontal-half", "vertical-half"}
    assert {
        candidate.cell_dots for candidate in bw
        if candidate.grid_dpi == (600, 600)
    } >= {(2, 3), (3, 2)}

    composite = [
        candidate for candidate in CANDIDATES_BY_CODE.values()
        if candidate.page_kind == "color"
        and candidate.emission_path == "DeviceCMYK-image"
    ]
    for grid in {
        (300, 300), (600, 600), (1200, 1200),
        (2400, 2400), (1200, 2400),
    }:
        for alphabet in {"CM4", "CMY7", "CMY8"}:
            assert {
                candidate.role for candidate in composite
                if candidate.grid_dpi == grid
                and candidate.alphabet == alphabet
            } == {"stress", "channel"}


@pytest.mark.parametrize("kind", ("bw", "color"))
def test_discovery_layout_is_canonical_overlap_free_and_separate(kind: str) -> None:
    page = build_page(
        stage="discovery", kind=kind, copy_index=9,
        request_code=REQUEST_CODES["default"],
    )
    verify_page(page)
    assert page["kind"] == kind
    assert page["request"] == "default"
    assert len(page["candidate_codes"]) == len(
        discovery_candidate_codes(kind)
    )
    assert len(page["infrastructure"]) == 17
    assert sum(
        row["kind"] == "machine_report"
        for row in page["infrastructure"]
    ) == 2
    rulers = [
        row for row in page["probes"]
        if row["group"] == "grid-discovery"
    ]
    assert len(rulers) == (30 if kind == "bw" else 120)


# An instrument-completeness proof over all 86 candidates, not per-commit
# feedback: it builds a page per candidate and verifies each (2026-09-20).
@_SLOW_CONTRACT
def test_every_candidate_has_an_overlap_free_calibration_layout() -> None:
    for code, candidate in CANDIDATES_BY_CODE.items():
        page = build_page(
            stage="calibration",
            kind=candidate.page_kind,
            copy_index=0,
            request_code=0,
            candidate_codes=(code,),
        )
        verify_page(page)
        assert len([
            row for row in page["probes"]
            if row["group"] == "grid-discovery"
        ]) == (30 if candidate.page_kind == "bw" else 120)


@pytest.mark.parametrize(
    ("kind", "planes"),
    (("bw", ("K",)), ("color", ("K", "C", "M", "Y"))),
)
def test_common_diagnostics_are_complete_and_machine_scorable(
    kind: str,
    planes: tuple[str, ...],
) -> None:
    page = build_page(
        stage="discovery", kind=kind, copy_index=0, request_code=0
    )
    probes = page["probes"]

    reports = [
        row for row in page["infrastructure"]
        if row["kind"] == "machine_report"
    ]
    assert len(reports) == 2
    assert {
        (
            row["format"],
            row["payload_bytes"],
            row["module_layout_dots"],
            row["width_modules"],
            row["height_modules"],
        )
        for row in reports
    } == {("HCAL-R1", 160, 6, 380, 10)}
    assert reports[0]["x_layout_dots"] == reports[1]["x_layout_dots"]
    assert reports[0]["y_layout_dots"] != reports[1]["y_layout_dots"]
    total_report_area_mm2 = sum(
        row["w_layout_dots"] * row["h_layout_dots"]
        * (25.4 / BASE_DPI) ** 2
        for row in reports
    )
    assert total_report_area_mm2 < 500.0

    scanner = {
        row["probe_id"]: row for row in probes
        if row["group"] == "scanner-adequacy"
    }
    assert set(scanner) == {
        "scanner/c3",
        "scanner/c2",
        "scanner/g2/horizontal_lines",
        "scanner/g2/vertical_lines",
        "scanner/entropy",
        "quiet/main",
    }
    assert scanner["scanner/c3"]["params"]["cell_dots"] == 3
    assert scanner["scanner/c2"]["params"]["cell_dots"] == 2
    assert scanner["scanner/entropy"]["kind"] == "entropy_field"

    rails = {
        row["params"]["axis"]: row for row in probes
        if row["group"] == "transport-geometry"
    }
    assert set(rails) == {"x", "y"}
    assert {row["kind"] for row in rails.values()} == {"phase_rail"}
    assert rails["x"]["params"]["orientation"] == "vertical_lines"
    assert rails["y"]["params"]["orientation"] == "horizontal_lines"

    physical_by_edge = {
        edge: {
            float(row["params"]["gap_mm"])
            for row in probes
            if row["group"] == "physical-ink-extent"
            and row["params"]["edge"] == edge
        }
        for edge in ("top", "right", "bottom", "left")
    }
    assert all(
        gaps == set(PHYSICAL_TICK_GAPS)
        for gaps in physical_by_edge.values()
    )

    canaries = [
        row for row in page["fields"]
        if row["family"] == "edge-canary"
    ]
    for edge in ("top", "right", "bottom", "left"):
        for gap in PAYLOAD_CANARY_GAPS:
            at_gap = [
                row for row in canaries
                if row["edge"] == edge and row["gap_mm"] == gap
            ]
            assert len(at_gap) == 2
            assert {row["role"] for row in at_gap} == {"edge-canary"}

    expected_grid_diagnostics = {
        "g1-v", "g1-h", "g2-v", "g2-h", "dots", "line-pair"
    }
    rulers = [
        row for row in probes if row["group"] == "grid-discovery"
    ]
    for grid in (
        (300, 300), (600, 600), (1200, 1200),
        (2400, 2400), (1200, 2400),
    ):
        grid_text = f"{grid[0]}x{grid[1]}"
        for plane in planes:
            prefix = f"grid/{grid_text}/{plane}/"
            assert {
                row["probe_id"].removeprefix(prefix)
                for row in rulers
                if row["probe_id"].startswith(prefix)
            } == expected_grid_diagnostics


def test_bw_discovery_restores_morphology_and_numeric_tone_profile() -> None:
    page = build_page(
        stage="discovery", kind="bw", copy_index=0, request_code=0
    )
    morphology = [
        row for row in page["probes"]
        if row["group"] == "morphology"
    ]
    assert len(morphology) == 20
    assert {
        (
            row["params"]["orientation"],
            row["params"]["width_dots"],
        )
        for row in morphology if row["kind"] == "line_width"
    } == {
        (orientation, width)
        for orientation in ("horizontal_lines", "vertical_lines")
        for width in (1, 2, 3, 4)
    }
    assert {
        row["params"]["dot_dots"]
        for row in morphology if row["kind"] == "isolated_dots"
    } == {1, 2, 3, 4}
    assert {
        row["params"]["hole_dots"]
        for row in morphology if row["kind"] == "white_holes"
    } == {1, 2, 3, 4}
    assert {
        row["params"]["n_dots"]
        for row in morphology if row["kind"] == "checker"
    } == {1, 2}
    assert {
        row["kind"] for row in morphology
    } >= {"slanted_edge", "microtext"}

    profiles = [
        row for row in page["probes"]
        if row["kind"] == "profile_tone"
    ]
    assert len(profiles) == 1
    assert profiles[0]["params"] == {
        "coverage": 0.5,
        "axis": "x",
        "mode": "fixed-profile",
    }


def test_copy_index_changes_all_field_ground_truth_and_printed_identity() -> None:
    codes = discovery_candidate_codes("bw")[:2]
    first = build_page(
        stage="calibration", kind="bw", copy_index=1,
        request_code=0, candidate_codes=codes,
    )
    second = build_page(
        stage="calibration", kind="bw", copy_index=2,
        request_code=0, candidate_codes=codes,
    )
    first_by_id = {row["field_id"]: row for row in first["fields"]}
    second_by_id = {row["field_id"]: row for row in second["fields"]}
    assert first_by_id.keys() == second_by_id.keys()
    assert all(
        first_by_id[key]["state_sha256"]
        != second_by_id[key]["state_sha256"]
        for key in first_by_id
    )
    assert (
        first["identity"]["layout_digest"]
        != second["identity"]["layout_digest"]
    )


def test_calibration_budget_refuses_more_than_eight_candidates() -> None:
    with pytest.raises(ValueError, match="one and eight"):
        build_page(
            stage="calibration", kind="bw", copy_index=0,
            request_code=0,
            candidate_codes=discovery_candidate_codes("bw")[:9],
        )
    with pytest.raises(ValueError, match="duplicates"):
        build_page(
            stage="calibration", kind="bw", copy_index=0,
            request_code=0, candidate_codes=(1, 1),
        )
    with pytest.raises(ValueError, match="unknown candidate"):
        build_page(
            stage="calibration", kind="bw", copy_index=0,
            request_code=0, candidate_codes=(999,),
        )


def test_grid_ruler_summary_distinguishes_resolution_from_completeness() -> None:
    def row(orientation: str, correlation: float = 0.9) -> dict:
        return {
            "probe_id": f"grid/600x600/K/{orientation}",
            "group": "grid-discovery",
            "status": "ok",
            "pattern": {
                "scorable": True,
                "correlation": correlation,
                "dot_error_rate": 0.01,
                "density_separation": 0.8,
            },
        }

    probe_ids = ("g1-v", "g1-h", "g2-v", "g2-h", "dots", "line-pair")
    incomplete = summarize_grid_rulers([
        row(orientation) for orientation in probe_ids[:-1]
    ])
    complete = summarize_grid_rulers([
        row(orientation) for orientation in probe_ids
    ])

    assert incomplete["600x600"]["planes"]["K"]["complete"] is False
    assert incomplete["600x600"]["planes"]["K"]["addressable"] is True
    assert incomplete["600x600"]["planes"]["K"][
        "finest_resolved_pattern"
    ] == "1-on/1-off"
    assert complete["600x600"]["planes"]["K"]["complete"] is True
    assert complete["600x600"]["planes"]["K"]["addressable"] is True


def _calibration_report(
    copy_index: int,
    error: float,
    *,
    scan_dpi: tuple[float, float] = (300.0, 300.0),
    window_error: float | None = None,
) -> dict:
    upper = error + 0.01
    local_error = error if window_error is None else window_error
    local_upper = local_error + 0.01
    candidate = CANDIDATES_BY_CODE[1]
    layout_digest = semantic_digest({
        "fixture": "calibration",
        "copy_index": copy_index,
    })
    page_plan_digest = semantic_digest({
        "fixture": "calibration-page-plan",
        "copy_index": copy_index,
    })
    report = {
        "schema": REPORT_SCHEMA,
        "schema_version": 4,
        "analyzer_version": 4,
        "status": "ok",
        "scan_dpi": list(scan_dpi),
        "page_plan_semantic_sha256": page_plan_digest,
        "capture": {
            "native_dtype": "uint8",
            "channels": 1,
            "color_model": "array-grayscale",
            "sha256": semantic_digest({
                "capture": copy_index,
                "error": error,
            }),
        },
        "operator_footing": {
            "printer": "synthetic-printer",
            "print_path": "synthetic-path",
            "media": "synthetic-media",
            "scanner": "synthetic-scanner",
            "scan_mode": "synthetic-mode",
            "print_session": f"session-{copy_index}",
        },
        "machine_report": {
            "identity": {
                "stage": "calibration",
                "kind": "bw",
                "copy_index": copy_index,
                "request_code": 0,
                "candidate_codes": [1],
                "layout_digest_128": layout_digest[:32],
            },
            "device_readback": {
                "product": "synthetic-printer",
                "effective_resolution": [600, 600],
                "print_nonce": copy_index + 1,
            },
            "strip_diagnostics": [],
            "consensus": {"status": "ok"},
        },
        "device_footing": {
            "fields": {
                "product": "synthetic-printer",
                "effective_resolution": [600, 600],
            },
            "semantic_sha256": semantic_digest({
                "product": "synthetic-printer",
                "effective_resolution": [600, 600],
            }),
        },
        "page_identity": {
            "stage": "calibration",
            "kind": "bw",
            "copy_index": copy_index,
            "request_code": 0,
            "candidate_codes": [1],
            "layout_digest": layout_digest,
        },
        "summary": {
            "candidate_results": [{
                "candidate_code": 1,
                "candidate_id": candidate.candidate_id,
                "page_kind": candidate.page_kind,
                "grid_dpi": [300, 300],
                "cell_dots": list(candidate.cell_dots),
                "alphabet": "K2",
                "states": list(candidate.states),
                "state_planes": [
                    list(values) for values in candidate.state_planes
                ],
                "bit_names": list(candidate.bit_names),
                "planes": list(candidate.planes),
                "emission_path": "single-plane-imagemask",
                "symbol_shape": candidate.symbol_shape,
                "role": candidate.role,
                "evidence_complete": True,
                "worst_error_rate": error,
                "worst_error_wilson_upper_95": upper,
                "worst_window_error_rate": local_error,
                "worst_window_wilson_upper_95": local_upper,
                "minimum_empirical_information_bits_per_mm2": 1.0 / error,
                "provisional_usable": (
                    upper < 0.08 and local_upper < 0.08
                ),
            }],
            "dpi_and_cells": {
                "grids": [{
                    "authored_grid_dpi": [300, 300],
                    "status": "usable",
                    "usable_candidate_codes": [1],
                }],
            },
        },
    }
    report["report_semantic_sha256"] = semantic_digest(report)
    return report


def test_shortlist_and_calibration_combination_are_conservative() -> None:
    first = _calibration_report(1, 0.01)
    second = _calibration_report(2, 0.05)

    combined = combine_calibration_reports([first, second])

    assert combined["copy_indices"] == [1, 2]
    assert combined["candidate_results"][0]["worst_copy_error_rate"] == 0.05
    assert (
        combined["candidate_results"][0][
            "worst_copy_window_error_rate"
        ]
        == 0.05
    )
    assert combined["candidate_results"][0]["calibrated_usable"] is True
    assert combined["scan_dpi"] == [300.0, 300.0]
    assert combined["source_evidence"] == [
        {
            "copy_index": report["page_identity"]["copy_index"],
            "report_semantic_sha256": report["report_semantic_sha256"],
            "capture_sha256": report["capture"]["sha256"],
            "layout_digest": report["page_identity"]["layout_digest"],
            "page_plan_semantic_sha256": (
                report["page_plan_semantic_sha256"]
            ),
        }
        for report in (first, second)
    ]
    alternate = combine_calibration_reports([
        _calibration_report(1, 0.02),
        second,
    ])
    assert alternate["candidate_results"] == combined["candidate_results"]
    assert alternate["source_evidence"] != combined["source_evidence"]
    assert semantic_digest(alternate) != semantic_digest(combined)
    assert combine_calibration_reports([second, first]) == combined
    with pytest.raises(ValueError, match="at least two"):
        combine_calibration_reports([first])
    with pytest.raises(ValueError, match="repeat a copy"):
        combine_calibration_reports([first, first])

    local_collapse = _calibration_report(
        6, 0.01, window_error=0.50
    )
    combined_local = combine_calibration_reports([first, local_collapse])
    assert combined_local["candidate_results"][0][
        "worst_copy_window_wilson_upper_95"
    ] == 0.51
    assert combined_local["candidate_results"][0][
        "calibrated_usable"
    ] is False

    different_dpi = _calibration_report(
        3, 0.01, scan_dpi=(600.0, 600.0)
    )
    with pytest.raises(ValueError, match="scanner DPI"):
        combine_calibration_reports([first, different_dpi])

    different_capture = _calibration_report(5, 0.01)
    different_capture["capture"]["native_dtype"] = "uint16"
    payload = dict(different_capture)
    payload.pop("report_semantic_sha256")
    different_capture["report_semantic_sha256"] = semantic_digest(payload)
    with pytest.raises(ValueError, match="dtype/channel/color"):
        combine_calibration_reports([first, different_capture])

    missing_capture_digest = _calibration_report(9, 0.01)
    missing_capture_digest["capture"]["sha256"] = None
    payload = dict(missing_capture_digest)
    payload.pop("report_semantic_sha256")
    missing_capture_digest["report_semantic_sha256"] = semantic_digest(payload)
    with pytest.raises(ValueError, match="capture SHA-256"):
        combine_calibration_reports([first, missing_capture_digest])

    missing_page_plan = _calibration_report(10, 0.01)
    missing_page_plan.pop("page_plan_semantic_sha256")
    payload = dict(missing_page_plan)
    payload.pop("report_semantic_sha256")
    missing_page_plan["report_semantic_sha256"] = semantic_digest(payload)
    with pytest.raises(ValueError, match="page-plan semantic digest"):
        combine_calibration_reports([first, missing_page_plan])

    different_device = _calibration_report(6, 0.01)
    different_device["device_footing"]["fields"][
        "effective_resolution"
    ] = [1200, 1200]
    different_device["machine_report"]["device_readback"][
        "effective_resolution"
    ] = [1200, 1200]
    different_device["device_footing"]["semantic_sha256"] = semantic_digest(
        different_device["device_footing"]["fields"]
    )
    payload = dict(different_device)
    payload.pop("report_semantic_sha256")
    different_device["report_semantic_sha256"] = semantic_digest(payload)
    with pytest.raises(ValueError, match="device self-report"):
        combine_calibration_reports([first, different_device])

    mismatched_identity = _calibration_report(7, 0.01)
    mismatched_identity["machine_report"]["identity"][
        "layout_digest_128"
    ] = "0" * 32
    payload = dict(mismatched_identity)
    payload.pop("report_semantic_sha256")
    mismatched_identity["report_semantic_sha256"] = semantic_digest(payload)
    with pytest.raises(ValueError, match="canonical page identity"):
        combine_calibration_reports([first, mismatched_identity])

    mismatched_footing = _calibration_report(8, 0.01)
    mismatched_footing["device_footing"]["fields"]["product"] = "other"
    mismatched_footing["device_footing"]["semantic_sha256"] = semantic_digest(
        mismatched_footing["device_footing"]["fields"]
    )
    payload = dict(mismatched_footing)
    payload.pop("report_semantic_sha256")
    mismatched_footing["report_semantic_sha256"] = semantic_digest(payload)
    with pytest.raises(ValueError, match="machine self-report readback"):
        combine_calibration_reports([first, mismatched_footing])

    refused = {
        "schema": REPORT_SCHEMA,
        "schema_version": 4,
        "analyzer_version": 4,
        "status": "refused",
        "refusal": {
            "code": "test",
            "stage": "test",
            "detail": "synthetic refusal",
        },
    }
    refused["report_semantic_sha256"] = semantic_digest(refused)
    with pytest.raises(ValueError, match="successful calibration"):
        combine_calibration_reports([refused, second])

    tampered = dict(first)
    tampered["status"] = "refused"
    with pytest.raises(ValueError, match="digest mismatch"):
        shortlist_candidate_codes(tampered)

    calibration = _calibration_report(4, 0.01)
    with pytest.raises(ValueError, match="discovery report"):
        shortlist_candidate_codes(calibration)

    malformed = {
        "schema": REPORT_SCHEMA,
        "schema_version": 4,
        "analyzer_version": 4,
        "status": "ok",
        "machine_report": {
            "identity": {},
            "device_readback": {},
            "strip_diagnostics": [],
            "consensus": {"status": "ok"},
        },
        "device_footing": {
            "fields": {},
            "semantic_sha256": semantic_digest({}),
        },
    }
    malformed["report_semantic_sha256"] = semantic_digest(malformed)
    with pytest.raises(
        ValueError, match="page identity|machine self-report"
    ):
        shortlist_candidate_codes(malformed)


def test_shortlist_preserves_each_usable_authored_grid() -> None:
    chosen = []
    for grid in (
        (300, 300), (600, 600), (1200, 1200),
        (2400, 2400), (1200, 2400),
    ):
        candidate = next(
            row for row in CANDIDATES_BY_CODE.values()
            if row.page_kind == "bw" and row.grid_dpi == grid
            and row.alphabet == "K2"
        )
        chosen.append(candidate)
    all_candidates = [
        CANDIDATES_BY_CODE[code]
        for code in discovery_candidate_codes("bw")
    ]
    layout_digest = semantic_digest({"fixture": "discovery", "kind": "bw"})
    chosen_codes = {candidate.code for candidate in chosen}
    report = {
        "schema": REPORT_SCHEMA,
        "schema_version": 4,
        "analyzer_version": 4,
        "status": "ok",
        "machine_report": {
            "identity": {
                "stage": "discovery",
                "kind": "bw",
                "copy_index": 0,
                "request_code": 0,
                "candidate_codes": [
                    candidate.code for candidate in all_candidates
                ],
                "layout_digest_128": layout_digest[:32],
            },
            "device_readback": {},
            "strip_diagnostics": [],
            "consensus": {"status": "ok"},
        },
        "device_footing": {
            "fields": {},
            "semantic_sha256": semantic_digest({}),
        },
        "page_identity": {
            "stage": "discovery",
            "kind": "bw",
            "copy_index": 0,
            "request_code": 0,
            "candidate_codes": [
                candidate.code for candidate in all_candidates
            ],
            "layout_digest": layout_digest,
        },
        "summary": {
            "candidate_results": [
                {
                    "candidate_code": candidate.code,
                    "candidate_id": candidate.candidate_id,
                    "page_kind": candidate.page_kind,
                    "grid_dpi": list(candidate.grid_dpi),
                    "cell_dots": list(candidate.cell_dots),
                    "cell_pitch_mm": list(candidate.pitch_mm),
                    "alphabet": candidate.alphabet,
                    "states": list(candidate.states),
                    "state_planes": [
                        list(values) for values in candidate.state_planes
                    ],
                    "bit_names": list(candidate.bit_names),
                    "planes": list(candidate.planes),
                    "emission_path": candidate.emission_path,
                    "symbol_shape": candidate.symbol_shape,
                    "role": candidate.role,
                    "evidence_complete": True,
                    "worst_error_rate": (
                        0.01 if candidate.code in chosen_codes else 0.5
                    ),
                    "minimum_empirical_information_bits_per_mm2": float(
                        index + 1
                        if candidate.code in chosen_codes
                        else 0.0
                    ),
                    "worst_error_wilson_upper_95": (
                        0.02 if candidate.code in chosen_codes else 0.6
                    ),
                    "worst_window_error_rate": (
                        0.01 if candidate.code in chosen_codes else 0.5
                    ),
                    "worst_window_wilson_upper_95": (
                        0.02 if candidate.code in chosen_codes else 0.6
                    ),
                    "provisional_usable": candidate.code in chosen_codes,
                }
                for index, candidate in enumerate(all_candidates)
            ],
            "dpi_and_cells": {
                "grids": [
                    {
                        "authored_grid_dpi": list(candidate.grid_dpi),
                        "status": "usable",
                        "usable_candidate_codes": [candidate.code],
                    }
                    for candidate in chosen
                ],
            },
        }
    }
    report["report_semantic_sha256"] = semantic_digest(report)

    codes = shortlist_candidate_codes(report, limit=5)
    details = shortlist_details(report, limit=5)

    # Equal-pitch twins are ONE physical channel (workplan W4a): the five
    # chosen grids collapse to their pitch clubs, each club keeping its
    # lowest-grid representative and recording every collapsed member.
    expected_clubs = {}
    for candidate in chosen:
        key = tuple(
            int(round(value * 1_000_000)) for value in candidate.pitch_mm
        )
        best = expected_clubs.get(key)
        if best is None or (
            candidate.grid_dpi[0] * candidate.grid_dpi[1]
            < best.grid_dpi[0] * best.grid_dpi[1]
        ):
            expected_clubs[key] = candidate
    assert set(codes) == {
        candidate.code for candidate in expected_clubs.values()
    }
    members_by_code = {
        row["candidate_code"]: set(row["club"]["member_codes"])
        for row in details
    }
    for candidate in chosen:
        assert any(
            candidate.code in members for members in members_by_code.values()
        )

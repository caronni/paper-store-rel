"""Conservative aggregation of independently seeded calibration reports."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

from .model import CANDIDATES_BY_CODE, PAGE_MM, SUMMARY_SCHEMA
from .verify import QUALIFICATION_ERROR_UPPER_MAX, verify_analysis_report
from .statistics import extremum, tier_for_error


def _scan_dpi_footing(report: dict[str, Any]) -> tuple[float, float]:
    try:
        values = tuple(float(value) for value in report["scan_dpi"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "calibration report has a missing or invalid scanner DPI footing"
        ) from exc
    if (
        len(values) != 2
        or not all(math.isfinite(value) and value > 0 for value in values)
    ):
        raise ValueError(
            "calibration report has a missing or invalid scanner DPI footing"
        )
    return values


def _capture_footing(report: dict[str, Any]) -> tuple[str, int, str]:
    capture = report.get("capture")
    if not isinstance(capture, dict):
        raise ValueError("calibration report lacks capture footing")
    try:
        dtype = str(capture["native_dtype"]).strip()
        channels = int(capture["channels"])
        color_model = str(capture["color_model"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calibration report lacks capture footing") from exc
    if not dtype or not color_model or channels not in {1, 2, 3, 4}:
        raise ValueError("calibration report lacks capture footing")
    return dtype, channels, color_model


def _extract_device_footing(report: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    footing = report.get("device_footing")
    if not isinstance(footing, dict):
        raise ValueError("calibration report lacks device self-report footing")
    digest = footing.get("semantic_sha256")
    fields = footing.get("fields")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(fields, dict)
    ):
        raise ValueError("calibration report has invalid device self-report footing")
    return digest, fields


def _sha256_field(value: Any, *, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"calibration report lacks valid {name}")
    return value


def _source_evidence(report: dict[str, Any]) -> dict[str, Any]:
    capture = report.get("capture")
    identity = report.get("page_identity")
    if not isinstance(capture, dict) or not isinstance(identity, dict):
        raise ValueError("calibration report lacks source evidence")
    try:
        copy_index = int(identity["copy_index"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calibration report lacks source evidence") from exc
    return {
        "copy_index": copy_index,
        "report_semantic_sha256": _sha256_field(
            report.get("report_semantic_sha256"),
            name="report semantic digest",
        ),
        "capture_sha256": _sha256_field(
            capture.get("sha256"),
            name="capture SHA-256",
        ),
        "layout_digest": _sha256_field(
            identity.get("layout_digest"),
            name="layout digest",
        ),
        "page_plan_semantic_sha256": _sha256_field(
            report.get("page_plan_semantic_sha256"),
            name="page-plan semantic digest",
        ),
    }


def _usable_codes(report: dict[str, Any]) -> set[int]:
    return {
        int(code)
        for grid in report["summary"]["dpi_and_cells"].get("grids", [])
        if grid.get("status") == "usable"
        for code in grid.get("usable_candidate_codes", [])
    }


def _agree(values, extract, message: str):
    """One N-way footing agreement: extract per report, refuse unless the
    set has exactly one member (previously five hand-unrolled copies)."""
    footings = {extract(report) for report in values}
    if len(footings) != 1:
        raise ValueError(message)
    return next(iter(footings))


def combine_calibration_reports(
    reports: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    values = list(reports)
    if len(values) < 2:
        raise ValueError(
            "at least two independently seeded calibration reports are required"
        )
    for report in values:
        verify_analysis_report(report)
    if any(
        report.get("status") != "ok"
        or report.get("page_identity", {}).get("stage") != "calibration"
        for report in values
    ):
        raise ValueError("all inputs must be successful calibration reports")
    kind, request_code, codes = _agree(
        values,
        lambda report: (
            report["page_identity"]["kind"],
            int(report["page_identity"]["request_code"]),
            tuple(report["page_identity"]["candidate_codes"]),
        ),
        "calibration reports have different kind/request/candidate footings",
    )
    copy_indices = [
        int(report["page_identity"]["copy_index"]) for report in values
    ]
    if len(set(copy_indices)) != len(copy_indices):
        raise ValueError("calibration reports repeat a copy index")
    source_evidence = sorted(
        (_source_evidence(report) for report in values),
        key=lambda row: int(row["copy_index"]),
    )

    stable_footing_keys = (
        "printer", "print_path", "media", "scanner", "scan_mode"
    )
    required_footing_keys = stable_footing_keys + ("print_session",)
    if any(
        any(
            not str(report.get("operator_footing", {}).get(key, "")).strip()
            for key in required_footing_keys
        )
        for report in values
    ):
        raise ValueError(
            "calibration reports require complete printer/path/media/scanner/"
            "scan-mode/session footing"
        )
    stable_footing = _agree(
        values,
        lambda report: tuple(
            str(report["operator_footing"][key])
            for key in stable_footing_keys
        ),
        "calibration reports have different printer/path/media/scanner "
        "footings",
    )
    scan_dpi_footing = _agree(
        values, _scan_dpi_footing,
        "calibration reports have different scanner DPI footings",
    )
    dtype, channels, color_model = _agree(
        values, _capture_footing,
        "calibration reports have different dtype/channel/color footings",
    )
    device_digest = _agree(
        values,
        lambda report: _extract_device_footing(report)[0],
        "calibration reports have different device self-report footings",
    )

    usable_by_report = [_usable_codes(report) for report in values]
    by_candidate: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for report in values:
        for row in report["summary"]["candidate_results"]:
            by_candidate[int(row["candidate_code"])].append(row)
    candidates = []
    for code in sorted(by_candidate):
        rows = by_candidate[code]
        complete = len(rows) == len(values) and all(
            row["evidence_complete"] for row in rows
        )
        dpi_evidence_complete = all(
            code in usable_codes for usable_codes in usable_by_report
        )
        n_measured = sum(
            1 for row in rows if row.get("worst_error_rate") is not None
        )
        worst_error = extremum(
            rows, lambda row: row.get("worst_error_rate"), max)
        worst_upper = extremum(
            rows, lambda row: row.get("worst_error_wilson_upper_95"), max)
        worst_window_error = extremum(
            rows, lambda row: row.get("worst_window_error_rate"), max)
        worst_window_upper = extremum(
            rows,
            lambda row: row.get("worst_window_wilson_upper_95"), max)
        minimum_information_density = extremum(
            rows,
            lambda row: row.get(
                "minimum_empirical_information_bits_per_mm2"),
            min)
        candidates.append({
            "candidate_code": code,
            "candidate_id": CANDIDATES_BY_CODE[code].candidate_id,
            "copies": len(rows),
            "n_copies": len(values),
            "n_measured": n_measured,
            "evidence_complete": complete,
            "dpi_evidence_complete": dpi_evidence_complete,
            "worst_copy_error_rate": worst_error,
            "worst_copy_wilson_upper_95": worst_upper,
            "worst_copy_window_error_rate": worst_window_error,
            "worst_copy_window_wilson_upper_95": worst_window_upper,
            "minimum_copy_empirical_information_bits_per_mm2": (
                minimum_information_density
            ),
            "tier": tier_for_error(
                None
                if worst_error is None or worst_window_error is None
                else max(worst_error, worst_window_error)
            ),
            "calibrated_usable": bool(
                complete
                and dpi_evidence_complete
                and worst_upper is not None
                and worst_window_upper is not None
                and worst_upper < QUALIFICATION_ERROR_UPPER_MAX
                and worst_window_upper < QUALIFICATION_ERROR_UPPER_MAX
            ),
        })

    # Worst-copy clip line per edge (the print margin, 028.2 ruling): the
    # conservative combination is the LARGEST measured clip; a copy whose
    # clip is unknowable makes the combined edge unknowable.
    clip_by_edge: dict[str, float | None] = {}
    for edge in ("left", "top", "right", "bottom"):
        copies = [
            report.get("summary", {})
            .get("diagnostics", {})
            .get("physical_ink_extent", {})
            .get("printable_clip_mm", {})
            .get(edge)
            for report in values
        ]
        clip_by_edge[edge] = (
            None if any(value is None for value in copies)
            else max(float(value) for value in copies)
        )

    combined_capacity = []
    clip_values = [value for value in clip_by_edge.values()]
    if all(value is not None for value in clip_values):
        margin = max(float(value) for value in clip_values
                     if value is not None)
        width = PAGE_MM[0] - 2.0 * margin
        height = PAGE_MM[1] - 2.0 * margin
        area = max(0.0, width) * max(0.0, height)
        for row in candidates:
            code = int(row["candidate_code"])
            density_value = row[
                "minimum_copy_empirical_information_bits_per_mm2"
            ]
            if not row["calibrated_usable"] or density_value is None:
                continue
            candidate = CANDIDATES_BY_CODE[code]
            combined_capacity.append({
                "candidate_code": code,
                "candidate_id": candidate.candidate_id,
                "margin_mm": margin,
                "area_mm2": area,
                "raw_alphabet_bits": (
                    candidate.alphabet_bits * candidate.cells_per_mm2 * area
                ),
                "empirical_information_bits": float(density_value) * area,
            })

    tone_mid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    registration_offsets = []
    scale_deviations = []
    physical_edges: dict[str, list[float | None]] = defaultdict(list)
    for report in values:
        summary = report.get("summary", {})
        diagnostics = summary.get("diagnostics", {})
        for row in diagnostics.get("tone_profiles", []):
            if row.get("status") == "ok":
                tone_mid[str(row["plane"])].append({
                    "copy_index": int(
                        report["page_identity"]["copy_index"]
                    ),
                    "density_median": float(row["density_median"]),
                })
        registration = diagnostics.get("plane_registration", {}).get(
            "worst_plane_offset_micrometres"
        )
        if registration is not None:
            registration_offsets.append(float(registration))
        for edge, edge_row in (
            diagnostics.get("physical_ink_extent", {})
            .get("edges", {})
            .items()
        ):
            value = edge_row.get("safe_gap_mm")
            physical_edges[edge].append(
                None if value is None else float(value)
            )
        grids = summary.get("dpi_and_cells", {}).get("grids", [])
        if grids:
            for ratio in grids[0].get("scale_ratio_xy", []):
                scale_deviations.append(abs(float(ratio) - 1.0))

    tone_summary = {}
    for plane, rows in sorted(tone_mid.items()):
        rows = sorted(rows, key=lambda row: int(row["copy_index"]))
        values_for_plane = [row["density_median"] for row in rows]
        tone_summary[plane] = {
            "copies": rows,
            "minimum_density": min(values_for_plane),
            "maximum_density": max(values_for_plane),
            "range": max(values_for_plane) - min(values_for_plane),
        }
    physical_summary = {}
    for edge, margins in physical_edges.items():
        physical_summary[edge] = (
            None if len(margins) != len(values) or any(
                value is None for value in margins
            )
            else max(float(value) for value in margins if value is not None)
        )
    print_sessions = sorted({
        str(report["operator_footing"]["print_session"])
        for report in values
    })
    device_fields = next(
        fields
        for digest, fields in (_extract_device_footing(report) for report in values)
        if digest == device_digest
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "stage": "calibration-combined",
        "kind": kind,
        "request_code": request_code,
        "candidate_codes": list(codes),
        "copy_indices": sorted(copy_indices),
        "source_evidence": source_evidence,
        "operator_footing": dict(zip(
            stable_footing_keys, stable_footing, strict=True
        )),
        "scan_dpi": list(scan_dpi_footing),
        "capture_footing": {
            "native_dtype": dtype,
            "channels": channels,
            "color_model": color_model,
        },
        "device_footing": {
            "semantic_sha256": device_digest,
            "fields": device_fields,
        },
        "print_sessions": print_sessions,
        "session_evidence": {
            "declared_session_count": len(print_sessions),
            "multiple_declared_sessions": len(print_sessions) >= 2,
        },
        "candidate_results": candidates,
        "payload_extent": {
            "printable_clip_mm_worst_copy": clip_by_edge,
            "capacity_at_worst_clip": combined_capacity,
        },
        "cross_copy_diagnostics": {
            "tone_mid": tone_summary,
            "worst_plane_registration_offset_micrometres": (
                max(registration_offsets, default=None)
            ),
            "physical_ink_safe_gap_mm": physical_summary,
            "worst_absolute_scale_deviation": (
                max(scale_deviations, default=None)
            ),
        },
        "independence_note": (
            "Copies establish content/sheet/position variation. They count as "
            "independent print sessions only when the operator records "
            "separate session provenance."
        ),
    }


__all__ = ["combine_calibration_reports"]

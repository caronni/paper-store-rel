"""Bounded calibration shortlists from one successful discovery report.

Equal-pitch twins (same pitch, alphabet, planes, path — e.g. 300-c1 and
600-c2) are ONE physical channel sampled at different page positions;
workplan W4a: the shortlist presents one representative per pitch club,
ranked with the club's conservative tail, and surfaces the club spread as
the position-variance measurement instead of letting twins straddle gates
silently.
"""
from __future__ import annotations

from typing import Any

from .verify import QUALIFICATION_ERROR_UPPER_MAX, verify_analysis_report


def _club_key(row: dict[str, Any]) -> tuple[Any, ...]:
    pitch = row["cell_pitch_mm"]
    return (
        int(round(float(pitch[0]) * 1_000_000)),
        int(round(float(pitch[1]) * 1_000_000)),
        str(row["page_kind"]),
        str(row["alphabet"]),
        tuple(str(value) for value in row["states"]),
        tuple(
            tuple(str(value) for value in state_planes)
            for state_planes in row["state_planes"]
        ),
        tuple(str(value) for value in row["bit_names"]),
        tuple(str(value) for value in row["planes"]),
        str(row["emission_path"]),
        str(row["symbol_shape"]),
        str(row["role"]),
    )


def _grid_area(row: dict[str, Any]) -> int:
    return int(row["grid_dpi"][0]) * int(row["grid_dpi"][1])


def shortlist_details(
    report: dict[str, Any], *, limit: int = 8
) -> list[dict[str, Any]]:
    """Pitch-club-collapsed shortlist with club evidence, rank-ordered."""

    if limit < 1 or limit > 8:
        raise ValueError("calibration shortlist limit must be 1..8")
    verify_analysis_report(report)
    if report.get("status") != "ok":
        raise ValueError("shortlisting requires a successful analysis report")
    if report.get("page_identity", {}).get("stage") != "discovery":
        raise ValueError("shortlisting requires a discovery report")
    summary = report["summary"]
    usable_codes = {
        int(code)
        for row in summary["dpi_and_cells"].get("grids", [])
        if row.get("status") == "usable"
        for code in row.get("usable_candidate_codes", [])
    }
    all_rows = list(summary["candidate_results"])
    clubs: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in all_rows:
        clubs.setdefault(_club_key(row), []).append(row)

    representatives: list[dict[str, Any]] = []
    for key, members in clubs.items():
        eligible = [
            row for row in members
            if (
                row.get("provisional_usable")
                and int(row["candidate_code"]) in usable_codes
            )
        ]
        if not eligible:
            continue
        representative = min(
            eligible,
            key=lambda row: (_grid_area(row), int(row["candidate_code"])),
        )
        measured_errors = [
            float(row["worst_error_rate"]) for row in members
            if row.get("worst_error_rate") is not None
        ]
        measured_uppers = [
            float(row["worst_error_wilson_upper_95"]) for row in members
            if row.get("worst_error_wilson_upper_95") is not None
        ]
        window_uppers = [
            float(row["worst_window_wilson_upper_95"]) for row in members
            if row.get("worst_window_wilson_upper_95") is not None
        ]
        representatives.append({
            "row": representative,
            "club": {
                "member_codes": sorted(
                    int(row["candidate_code"]) for row in members
                ),
                "measured_member_count": len(measured_errors),
                "club_worst_error_rate": (
                    max(measured_errors) if measured_errors else None
                ),
                "club_worst_error_wilson_upper_95": (
                    max(measured_uppers) if measured_uppers else None
                ),
                "club_worst_window_wilson_upper_95": (
                    max(window_uppers) if window_uppers else None
                ),
                "position_variance_worst_error_spread": (
                    max(measured_errors) - min(measured_errors)
                    if len(measured_errors) >= 2 else None
                ),
                "club_straddles_qualification_gate": bool(
                    window_uppers
                    and min(window_uppers)
                    < QUALIFICATION_ERROR_UPPER_MAX
                    <= max(window_uppers)
                ),
            },
        })

    def rank(entry: dict[str, Any]) -> tuple[float, float, int]:
        row = entry["row"]
        club = entry["club"]
        conservative_upper = club["club_worst_error_wilson_upper_95"]
        return (
            -float(row.get(
                "minimum_empirical_information_bits_per_mm2", 0.0
            ) or 0.0),
            float(
                conservative_upper
                if conservative_upper is not None
                else row.get("worst_error_wilson_upper_95", 1.0)
            ),
            int(row["candidate_code"]),
        )

    representatives.sort(key=rank)
    selected: list[dict[str, Any]] = []

    # Preserve the DPI question in calibration: take the best club from
    # every usable authored grid before filling by density.
    grids = {
        tuple(int(value) for value in entry["row"]["grid_dpi"])
        for entry in representatives
    }
    grid_winners = [
        min(
            (
                entry for entry in representatives
                if tuple(
                    int(value) for value in entry["row"]["grid_dpi"]
                ) == grid
            ),
            key=rank,
        )
        for grid in grids
    ]
    grid_winners.sort(key=rank)
    selected.extend(grid_winners[:limit])

    # Distinct alphabets and emission paths are distinct channel claims.
    signatures = {
        (str(entry["row"]["alphabet"]), str(entry["row"]["emission_path"]))
        for entry in representatives
    }
    signature_winners = [
        min(
            (
                entry for entry in representatives
                if (
                    str(entry["row"]["alphabet"]),
                    str(entry["row"]["emission_path"]),
                ) == signature
            ),
            key=rank,
        )
        for signature in signatures
    ]
    signature_winners.sort(key=rank)
    for entry in signature_winners + representatives:
        if len(selected) >= limit:
            break
        if entry not in selected:
            selected.append(entry)
    return [
        {
            "candidate_code": int(entry["row"]["candidate_code"]),
            "candidate_id": entry["row"]["candidate_id"],
            "tier": entry["row"].get("tier"),
            "worst_error_rate": entry["row"].get("worst_error_rate"),
            "worst_error_wilson_upper_95": entry["row"].get(
                "worst_error_wilson_upper_95"
            ),
            "worst_window_wilson_upper_95": entry["row"].get(
                "worst_window_wilson_upper_95"
            ),
            "window_error_quantiles": entry["row"].get(
                "window_error_quantiles"
            ),
            "minimum_empirical_information_bits_per_mm2": entry[
                "row"
            ].get("minimum_empirical_information_bits_per_mm2"),
            "club": entry["club"],
        }
        for entry in selected
    ]


def shortlist_candidate_codes(
    report: dict[str, Any], *, limit: int = 8
) -> tuple[int, ...]:
    return tuple(
        int(row["candidate_code"])
        for row in shortlist_details(report, limit=limit)
    )


__all__ = [
    "shortlist_candidate_codes",
    "shortlist_details",
]

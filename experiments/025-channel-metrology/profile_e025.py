#!/usr/bin/env python
"""Aggregate E025 reports into emitter, sensor, or pipeline profiles.

E025 profiles separate three claims: a printer path observed through one
reference scanner; a scanner compared on the same physical sheet; and an
exact end-to-end pipeline.  The compact FEC coupons are compatibility checks,
not waterfall confidence intervals.  Diversity and raw held-out channel
evidence therefore remain explicit in every recommendation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from paperholo.metrology import CandidateObservation, observations_from_report


@dataclass(frozen=True)
class ProfilePolicy:
    policy_id: str
    min_physical_sheets: int
    max_worst_hard_error: float
    min_mi_fraction_of_alphabet: float
    require_exact_fec_coupon: bool
    min_fec_sheets: int


POLICIES = {
    "survey": ProfilePolicy("survey", 1, 0.03, 0.75, True, 1),
    "production": ProfilePolicy("production", 3, 0.01, 0.90, True, 3),
    "archive": ProfilePolicy("archive", 6, 0.005, 0.95, True, 6),
}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    observations_from_report(document)
    expected = document.get("semantic_sha256")
    payload = dict(document)
    payload.pop("semantic_sha256", None)
    if _digest(payload) != expected:
        raise ValueError(f"{path}: report semantic digest mismatch")
    e025 = document.get("metadata", {}).get("e025", {})
    if e025.get("schema") != "paper-store/e025/analysis/v2":
        raise ValueError(f"{path}: not a forward E025 analysis report")
    return document


def _observation_index(document: dict[str, Any]
                       ) -> dict[str, CandidateObservation]:
    return {
        str(item.diagnostics["field_id"]): item
        for item in observations_from_report(document)
    }


def _validate_roles(kind: str, reports: list[dict[str, Any]]) -> None:
    roles = {item["metadata"].get("role") for item in reports}
    if roles != {kind}:
        raise ValueError(f"profile kind {kind!r}, report roles {sorted(roles)}")


def _validate_independent_prints(reports: list[dict[str, Any]]) -> None:
    seen: set[tuple[str, str]] = set()
    for report in reports:
        sheet = str(report["footing"]["sheet_id"])
        for field_id in _observation_index(report):
            key = sheet, field_id
            if key in seen:
                raise ValueError(
                    "repeated scan of one physical field is not independent "
                    f"printer evidence: {key}"
                )
            seen.add(key)


def _intersection_extent(reports: list[dict[str, Any]]) -> dict[str, Any]:
    margins: dict[str, list[float]] = {edge: [] for edge in
                                      ("top", "bottom", "left", "right")}
    unresolved = []
    for report in reports:
        values = report["metadata"]["e025"]["payload_safe_extent"]["margins_mm"]
        for edge in margins:
            value = values.get(edge)
            if value is None:
                unresolved.append({
                    "sheet_id": report["footing"]["sheet_id"], "edge": edge,
                })
            else:
                margins[edge].append(float(value))
    conservative = {
        edge: max(values) if values else None for edge, values in margins.items()
    }
    rectangle = None
    if all(value is not None for value in conservative.values()):
        width = 210.0 - conservative["left"] - conservative["right"]
        height = 297.0 - conservative["top"] - conservative["bottom"]
        rectangle = {
            "x0_mm": conservative["left"], "y0_mm": conservative["top"],
            "x1_mm": 210.0 - conservative["right"],
            "y1_mm": 297.0 - conservative["bottom"],
            "width_mm": width, "height_mm": height,
            "area_mm2": width * height,
        }
    return {
        "conservative_margins_mm": conservative,
        "intersection_rectangle_mm": rectangle,
        "unresolved": unresolved,
        "rule": "maximum measured payload-safe margin per edge across captures",
    }


def _channel_summaries(reports: list[dict[str, Any]],
                       policy: ProfilePolicy) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[str, CandidateObservation]]] = {}
    for report in reports:
        sheet = str(report["footing"]["sheet_id"])
        for observation in observations_from_report(report):
            family = str(observation.diagnostics.get("family", ""))
            if family != "prnd":
                continue
            grouped.setdefault(observation.candidate.candidate_id, []).append(
                (sheet, observation)
            )
    rows = []
    for candidate_id, items in grouped.items():
        candidate = items[0][1].candidate
        sheets = sorted({sheet for sheet, _ in items})
        worst_ber = max(item.hard_error_rate for _, item in items)
        minimum_mi = min(item.mutual_information_bpc for _, item in items)
        mi_fraction = minimum_mi / candidate.payload_bits_per_cell
        reasons = []
        if len(sheets) < policy.min_physical_sheets:
            reasons.append(
                f"physical sheets {len(sheets)} < {policy.min_physical_sheets}"
            )
        if worst_ber > policy.max_worst_hard_error:
            reasons.append(
                f"worst BER {worst_ber:.5f} > {policy.max_worst_hard_error:.5f}"
            )
        if mi_fraction < policy.min_mi_fraction_of_alphabet:
            reasons.append(
                f"MI fraction {mi_fraction:.4f} < "
                f"{policy.min_mi_fraction_of_alphabet:.4f}"
            )
        if not all(item.scan_adequate for _, item in items):
            reasons.append("one or more scans are detector-inadequate")
        rows.append({
            "candidate_id": candidate_id,
            "physically_qualified": not reasons,
            "reasons": reasons, "physical_sheets": sheets,
            "strata": sorted({item.stratum_id.split("/")[-1] for _, item in items}),
            "field_observations": len(items),
            "validation_cells": sum(item.n_validation_cells for _, item in items),
            "worst_hard_error_rate": worst_ber,
            "minimum_mi_bpc": minimum_mi,
            "minimum_mi_fraction_of_alphabet": mi_fraction,
            "minimum_information_bits_per_mm2": (
                minimum_mi * candidate.grid.cells_per_mm2
            ),
            "minimum_measured_samples_per_cell": [
                min(item.measured_scan_samples_x for _, item in items),
                min(item.measured_scan_samples_y for _, item in items),
            ],
            "candidate": candidate.to_dict(),
        })
    rows.sort(key=lambda row: row["minimum_information_bits_per_mm2"], reverse=True)
    return rows


def _fec_confirmations(reports: list[dict[str, Any]],
                       policy: ProfilePolicy) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[tuple[str, Any]]] = {}
    for report in reports:
        sheet = str(report["footing"]["sheet_id"])
        for observation in observations_from_report(report):
            if observation.diagnostics.get("family") != "fec_coupon":
                continue
            for result in observation.ldpc:
                grouped.setdefault((observation.candidate.candidate_id,
                                    result.level_id, result.rate_id), []).append(
                    (sheet, result)
                )
    rows = []
    for (candidate_id, level_id, rate_id), items in sorted(grouped.items()):
        sheets = sorted({sheet for sheet, _ in items})
        attempted = sum(item.attempted for _, item in items)
        certified = sum(item.certified for _, item in items)
        wrong = sum(item.wrong for _, item in items)
        all_exact = certified == attempted and wrong == 0 and attempted > 0
        rows.append({
            "candidate_id": candidate_id, "level_id": level_id,
            "rate_id": rate_id, "code_rate": items[0][1].code_rate,
            "physical_sheets": sheets, "attempted": attempted,
            "certified_exact": certified, "syndrome_valid_wrong": wrong,
            "all_exact": all_exact,
            "policy_diversity_met": len(sheets) >= policy.min_fec_sheets,
            "confirmation_pass": bool(
                all_exact and len(sheets) >= policy.min_fec_sheets
            ),
            "interpretation": (
                "production-code compatibility coupon; too few words for a "
                "standalone waterfall confidence interval"
            ),
        })
    return rows


def _recommendations(channel: list[dict[str, Any]], fec: list[dict[str, Any]],
                     extent: dict[str, Any], policy: ProfilePolicy
                     ) -> list[dict[str, Any]]:
    fec_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for row in fec:
        fec_by_candidate.setdefault(row["candidate_id"], []).append(row)
    rectangle = extent["intersection_rectangle_mm"]
    out = []
    for summary in channel:
        candidate = summary["candidate"]
        levels = list(candidate["bit_levels"])
        candidate_fec = fec_by_candidate.get(summary["candidate_id"], [])
        rates = sorted({row["rate_id"] for row in candidate_fec})
        if not rates:
            out.append({
                "candidate_id": summary["candidate_id"], "rate_id": None,
                "qualified": False,
                "reasons": ["no exact production-code coupon for candidate"],
                "channel_only": True,
                "minimum_information_bits_per_mm2": summary[
                    "minimum_information_bits_per_mm2"
                ],
                "candidate": candidate,
            })
            continue
        for rate_id in rates:
            per_level = {
                row["level_id"]: row for row in candidate_fec
                if row["rate_id"] == rate_id
            }
            reasons = list(summary["reasons"])
            missing = sorted(set(levels) - set(per_level))
            if missing:
                reasons.append("missing FEC levels " + ",".join(missing))
            if policy.require_exact_fec_coupon and any(
                not per_level[level]["confirmation_pass"]
                for level in levels if level in per_level
            ):
                reasons.append("FEC coupon exactness/diversity policy not met")
            code_rate = next(iter(per_level.values()))["code_rate"] if per_level else 0.0
            source_density = candidate["grid"]["dpi_x"] * candidate["grid"]["dpi_y"]
            source_density /= 25.4**2 * candidate["grid"]["c_x"] * candidate["grid"]["c_y"]
            source_density *= len(levels) * code_rate
            page_bits = None
            if rectangle is None:
                reasons.append("payload-safe printable rectangle unresolved")
            else:
                grid = candidate["grid"]
                pitch_x = 25.4 * grid["c_x"] / grid["dpi_x"]
                pitch_y = 25.4 * grid["c_y"] / grid["dpi_y"]
                cells = int(rectangle["width_mm"] / pitch_x) * int(
                    rectangle["height_mm"] / pitch_y
                )
                page_bits = cells * len(levels) * code_rate
            out.append({
                "candidate_id": summary["candidate_id"], "rate_id": rate_id,
                "qualified": not reasons, "reasons": reasons,
                "channel_only": False,
                "code_rate": code_rate,
                "levels": {level: per_level.get(level) for level in levels},
                "coded_bits_per_mm2_before_furniture": source_density,
                "coded_payload_bits_in_measured_rectangle_before_furniture": page_bits,
                "coded_payload_megabytes_before_furniture": (
                    None if page_bits is None else page_bits / 8e6
                ),
                "minimum_information_bits_per_mm2": summary[
                    "minimum_information_bits_per_mm2"
                ],
                "candidate": candidate,
                "caution": (
                    "feasibility recommendation; production format furniture, "
                    "outer fountain recovery, and payload CRC remain separate"
                ),
            })
    out.sort(key=lambda row: (
        bool(row["qualified"]),
        float(row.get("coded_bits_per_mm2_before_furniture", 0.0)),
    ), reverse=True)
    return out


def _sensor_deltas(targets: list[dict[str, Any]],
                   references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_by_sheet = {str(item["footing"]["sheet_id"]): item
                          for item in references}
    target_sheets = {str(item["footing"]["sheet_id"]) for item in targets}
    if set(reference_by_sheet) != target_sheets:
        raise ValueError("sensor target/reference reports must name the same sheet set")
    rows = []
    for target in targets:
        sheet = str(target["footing"]["sheet_id"])
        reference = reference_by_sheet[sheet]
        if target["metadata"]["stimulus_manifest_semantic_sha256"] != reference[
            "metadata"
        ]["stimulus_manifest_semantic_sha256"]:
            raise ValueError(f"sensor sheet {sheet}: target/reference stimuli differ")
        ti, ri = _observation_index(target), _observation_index(reference)
        if set(ti) != set(ri):
            raise ValueError(f"sensor sheet {sheet}: target/reference field sets differ")
        for field_id in sorted(ti):
            t, r = ti[field_id], ri[field_id]
            rows.append({
                "sheet_id": sheet, "field_id": field_id,
                "candidate_id": t.candidate.candidate_id,
                "hard_error_delta": t.hard_error_rate - r.hard_error_rate,
                "mi_delta_bpc": t.mutual_information_bpc - r.mutual_information_bpc,
                "measured_samples_delta": [
                    t.measured_scan_samples_x - r.measured_scan_samples_x,
                    t.measured_scan_samples_y - r.measured_scan_samples_y,
                ],
            })
    return rows


def build_profile(*, kind: str, policy_id: str,
                  reports: list[dict[str, Any]],
                  references: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        raise ValueError("at least one E025 report is required")
    policy = POLICIES[policy_id]
    _validate_roles(kind, reports)
    if kind != "sensor":
        _validate_independent_prints(reports)
    channel = _channel_summaries(reports, policy)
    fec = _fec_confirmations(reports, policy)
    extent = _intersection_extent(reports)
    recommendations = _recommendations(channel, fec, extent, policy)
    footings = [item["footing"] for item in reports]
    profile: dict[str, Any] = {
        "schema": "paper-store/e025/profile/v2",
        "kind": kind, "policy": asdict(policy),
        "input_report_semantic_sha256": [item["semantic_sha256"] for item in reports],
        "footings": footings,
        "payload_safe_extent": extent,
        "channel_summaries": channel,
        "fec_confirmations": fec,
        "recommendations": recommendations,
        "qualified": [row for row in recommendations if row["qualified"]],
        "device_readback_strips": [
            {
                "sheet_id": report["footing"]["sheet_id"],
                "strips": report["metadata"]["e025"]["device_readback_strips"],
            } for report in reports
        ],
    }
    if kind == "emitter":
        scanner_paths = {
            (item["scanner_id"], item["scan_mode"], item["scan_dpi_x"],
             item["scan_dpi_y"]) for item in footings
        }
        if len(scanner_paths) != 1:
            raise ValueError("emitter profile requires one reference scanner footing")
        profile["reference_scanner"] = dict(zip(
            ("scanner_id", "scan_mode", "scan_dpi_x", "scan_dpi_y"),
            next(iter(scanner_paths)), strict=True,
        ))
    elif kind == "sensor":
        if not references:
            raise ValueError("sensor profile requires same-sheet reference reports")
        profile["reference_report_semantic_sha256"] = [
            item["semantic_sha256"] for item in references
        ]
        profile["scanner_deltas"] = _sensor_deltas(reports, references)
    elif kind == "pipeline":
        paths = {
            (item["printer_id"], item["scanner_id"], item["print_path"],
             item["scan_mode"], item["scan_dpi_x"], item["scan_dpi_y"],
             item["media"], tuple(item["requested_dpi"] or ()))
            for item in footings
        }
        if len(paths) != 1:
            raise ValueError("pipeline profile requires one exact end-to-end footing")
        best = next((row for row in recommendations if row["qualified"]), None)
        if best is not None:
            profile["receiver_hint"] = {
                "advisory_only": True,
                "candidate_id": best["candidate_id"],
                "rate_id": best["rate_id"],
                "payload_safe_margins_mm": extent["conservative_margins_mm"],
                "minimum_measured_samples_per_cell": next(
                    row["minimum_measured_samples_per_cell"] for row in channel
                    if row["candidate_id"] == best["candidate_id"]
                ),
                "may_weaken_receiver_gates": False,
                "interpretation": (
                    "compatibility hint only; placement, bounded LLR, LDPC, "
                    "fountain recovery, and payload CRC remain authoritative"
                ),
            }
            profile["receiver_hint"]["semantic_sha256"] = _digest(
                profile["receiver_hint"]
            )
    profile["semantic_sha256"] = _digest(profile)
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--kind", choices=("emitter", "sensor", "pipeline"),
                        required=True)
    parser.add_argument("--policy", choices=tuple(POLICIES), default="survey")
    parser.add_argument("--reference", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    profile = build_profile(
        kind=args.kind, policy_id=args.policy,
        reports=[_load(path) for path in args.reports],
        references=[_load(path) for path in args.reference],
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")
    print(f"profile {args.out}")
    for row in profile["recommendations"][:12]:
        status = "QUALIFIED" if row["qualified"] else "not-qualified"
        print(f"{status:13} {row['candidate_id']} {row['rate_id'] or '-'} "
              f"info={row['minimum_information_bits_per_mm2']:.2f} b/mm2")


if __name__ == "__main__":
    main()

"""Structural re-validation of one analyzer report at the disk boundary.

Aggregation and shortlisting accept operator-supplied report files; this
gate refuses anything that is not a complete, self-consistent current
report before any number is combined.
"""
from __future__ import annotations

from typing import Any

from .model import (
    CANDIDATES_BY_CODE,
    REPORT_SCHEMA,
    REQUEST_NAMES,
    SUMMARY_SCHEMA,
    discovery_candidate_codes,
    semantic_digest,
)

QUALIFICATION_ERROR_UPPER_MAX = 0.08


def verify_analysis_report(report: dict[str, Any]) -> None:
    if report.get("schema") != REPORT_SCHEMA:
        raise ValueError(
            f"analysis report schema must be exactly {REPORT_SCHEMA!r}"
        )
    if (
        report.get("schema_version") != 4
        or report.get("analyzer_version") != 4
    ):
        raise ValueError("analysis report version is not current")
    expected = report.get("report_semantic_sha256")
    payload = dict(report)
    payload.pop("report_semantic_sha256", None)
    if expected != semantic_digest(payload):
        raise ValueError("analysis report semantic digest mismatch")
    status = report.get("status")
    if status not in {"ok", "refused"}:
        raise ValueError("analysis report has invalid status")
    if status == "refused":
        refusal = report.get("refusal")
        if not isinstance(refusal, dict) or not {
            "code", "stage", "detail"
        } <= set(refusal):
            raise ValueError("refused analysis report lacks refusal detail")
        return
    machine_report = report.get("machine_report")
    if (
        not isinstance(machine_report, dict)
        or not {
            "identity",
            "device_readback",
            "strip_diagnostics",
            "consensus",
        } <= set(machine_report)
        or not isinstance(machine_report["identity"], dict)
        or not isinstance(machine_report["device_readback"], dict)
        or not isinstance(machine_report["strip_diagnostics"], list)
        or not isinstance(machine_report["consensus"], dict)
        or machine_report["consensus"].get("status") != "ok"
    ):
        raise ValueError("successful analysis report lacks machine self-report")
    device_footing = report.get("device_footing")
    if (
        not isinstance(device_footing, dict)
        or not {"fields", "semantic_sha256"} <= set(device_footing)
        or not isinstance(device_footing["fields"], dict)
        or device_footing["semantic_sha256"]
        != semantic_digest(device_footing["fields"])
    ):
        raise ValueError("successful analysis report lacks device footing")
    stable_readback = {
        str(key): value
        for key, value in machine_report["device_readback"].items()
        if key != "print_nonce"
    }
    if device_footing["fields"] != stable_readback:
        raise ValueError(
            "device footing differs from the machine self-report readback"
        )
    identity = report.get("page_identity")
    summary = report.get("summary")
    if not isinstance(identity, dict) or not {
        "stage",
        "kind",
        "copy_index",
        "request_code",
        "candidate_codes",
        "layout_digest",
    } <= set(identity):
        raise ValueError("successful analysis report lacks page identity")
    if identity["stage"] not in {"discovery", "calibration"}:
        raise ValueError("analysis report has invalid page stage")
    if identity["kind"] not in {"bw", "color"}:
        raise ValueError("analysis report has invalid page kind")
    if (
        not isinstance(summary, dict)
        or not isinstance(summary.get("candidate_results"), list)
        or not isinstance(summary.get("dpi_and_cells"), dict)
    ):
        raise ValueError("successful analysis report lacks current summary")
    try:
        copy_index = int(identity["copy_index"])
        request_code = int(identity["request_code"])
        candidate_codes = tuple(
            int(code) for code in identity["candidate_codes"]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("analysis report has malformed page identity") from exc
    if copy_index < 0 or request_code not in REQUEST_NAMES:
        raise ValueError("analysis report has malformed page identity")
    if (
        not candidate_codes
        or len(set(candidate_codes)) != len(candidate_codes)
        or any(code not in CANDIDATES_BY_CODE for code in candidate_codes)
        or any(
            CANDIDATES_BY_CODE[code].page_kind != identity["kind"]
            for code in candidate_codes
        )
    ):
        raise ValueError("analysis report has malformed candidate identity")
    if (
        identity["stage"] == "discovery"
        and candidate_codes != discovery_candidate_codes(identity["kind"])
    ):
        raise ValueError("analysis report has incomplete discovery identity")
    if identity["stage"] == "calibration" and len(candidate_codes) > 8:
        raise ValueError("analysis report has oversized calibration identity")
    machine_identity = machine_report["identity"]
    if not {
        "stage",
        "kind",
        "copy_index",
        "request_code",
        "candidate_codes",
        "layout_digest_128",
    } <= set(machine_identity):
        raise ValueError("machine self-report lacks current page identity")
    try:
        machine_copy_index = int(machine_identity["copy_index"])
        machine_request_code = int(machine_identity["request_code"])
        machine_candidate_codes = tuple(
            int(code) for code in machine_identity["candidate_codes"]
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "machine self-report has malformed page identity"
        ) from exc
    layout_digest = identity["layout_digest"]
    layout_digest_128 = machine_identity["layout_digest_128"]
    if (
        machine_identity["stage"] != identity["stage"]
        or machine_identity["kind"] != identity["kind"]
        or machine_copy_index != copy_index
        or machine_request_code != request_code
        or machine_candidate_codes != candidate_codes
        or not isinstance(layout_digest, str)
        or len(layout_digest) != 64
        or any(character not in "0123456789abcdef" for character in layout_digest)
        or not isinstance(layout_digest_128, str)
        or len(layout_digest_128) != 32
        or any(
            character not in "0123456789abcdef"
            for character in layout_digest_128
        )
        or not layout_digest.startswith(layout_digest_128)
    ):
        raise ValueError(
            "machine self-report identity differs from canonical page identity"
        )

    # The semantic digest above already proves the report's integrity; the
    # boundary checks below bind the summary to the printed identity and the
    # current registry without re-deriving per-row registry fields (that
    # was validating a copy against its own source and amplified every
    # report-shape change into an edit here).
    result_codes = []
    for row in summary["candidate_results"]:
        if not isinstance(row, dict):
            raise ValueError(
                "analysis report has malformed candidate results"
            )
        try:
            code = int(row["candidate_code"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "analysis report has malformed candidate results"
            ) from exc
        if code not in CANDIDATES_BY_CODE:
            raise ValueError("analysis report has unknown candidate result")
        result_codes.append(code)
    if tuple(sorted(result_codes)) != tuple(sorted(candidate_codes)):
        raise ValueError(
            "analysis report candidate results differ from printed identity"
        )

    grids = summary["dpi_and_cells"].get("grids")
    if not isinstance(grids, list):
        raise ValueError("analysis report has malformed DPI/cell summary")
    for grid in grids:
        if (
            not isinstance(grid, dict)
            or not {
                "authored_grid_dpi", "status", "usable_candidate_codes"
            } <= set(grid)
        ):
            raise ValueError("analysis report has malformed DPI/cell summary")
        try:
            usable_codes = {
                int(code) for code in grid["usable_candidate_codes"]
            }
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "analysis report has malformed DPI/cell summary"
            ) from exc
        if not usable_codes <= set(result_codes):
            raise ValueError(
                "DPI/cell summary names a non-result candidate"
            )

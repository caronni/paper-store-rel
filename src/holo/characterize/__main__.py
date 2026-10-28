"""Command-line implementation for the characterization instrument."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .aggregate import combine_calibration_reports
from .analyze import analyze_scan, write_report
from .emit import emit_bundle
from .io import json_bytes, write_new_bytes
from .model import (
    CANDIDATES_BY_CODE,
    CANDIDATES_BY_ID,
    REQUEST_CODES,
    semantic_digest,
    validate_shortlist,
)
from .shortlist import shortlist_candidate_codes, shortlist_details


def _kind_values(value: str) -> tuple[str, ...]:
    return ("bw", "color") if value == "both" else (value,)


def _fmt_pct(value: Any) -> str:
    return "n/a" if value is None else f"{float(value) * 100.0:.2f}%"


def _fmt_mm(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2f}mm"


def _stdout_summary(report: dict[str, Any]) -> list[str]:
    """Operator summary block (workplan W5a): derived, never authoritative.

    The JSON report stays the evidence record; these lines exist so a
    print-day operator does not need to dig a 2 MB report for the facts
    that drive the next decision.
    """

    summary = report.get("summary", {})
    diagnostics = summary.get("diagnostics", {})
    lines = ["", "== operator summary (derived; the JSON is the record) =="]
    device = report.get("machine_report", {}).get("device_readback", {})
    lines.append(
        f"device: {device.get('product')} | languagelevel "
        f"{device.get('language_level')} | effective dpi "
        f"{device.get('effective_resolution')}"
    )
    dpi_cells = summary.get("dpi_and_cells", {})
    lines.append(
        "highest useful authored grid: "
        f"{dpi_cells.get('highest_useful_authored_grid_dpi')} "
        f"(scale {dpi_cells.get('physical_scale_status')})"
    )
    ink = diagnostics.get("physical_ink_extent", {})
    clip = ink.get("printable_clip_mm", {})
    lines.append(
        "print margin (layout-frame clip line): "
        + "  ".join(
            f"{edge} {_fmt_mm(clip.get(edge))}"
            for edge in ("left", "top", "right", "bottom")
        )
    )
    flats = []
    for edge, row in summary.get("payload_extent", {}).get(
        "edges", {}
    ).items():
        for code, curve in row.get("arm_curves", {}).items():
            flats.append((
                str(curve.get("candidate_id")),
                edge,
                curve.get("edge_flat_gap_mm"),
            ))
    by_arm: dict[str, list[Any]] = {}
    for candidate_id, _edge, gap in flats:
        by_arm.setdefault(candidate_id, []).append(gap)
    for candidate_id, gaps in sorted(by_arm.items()):
        worst = (
            None if any(gap is None for gap in gaps)
            else max(float(gap) for gap in gaps)
        )
        lines.append(
            f"payload edge data: {candidate_id} at interior level from "
            f"{_fmt_mm(worst)} (worst edge)"
        )
    adequacy = diagnostics.get("scanner_adequacy_summary", {})
    checks = adequacy.get("checks", {})
    failing = sorted(
        name for name, row in checks.items()
        if isinstance(row, dict)
        and (row.get("status") == "fail" or row.get("verdict") == "fail")
    )
    lines.append(
        "scanner adequacy: "
        + str(adequacy.get("verdict"))
        + (f" (failing: {', '.join(failing)})" if failing else "")
    )
    try:
        details = shortlist_details(report, limit=5)
    except ValueError:
        details = []
    for row in details:
        club = row.get("club", {})
        spread = club.get("position_variance_worst_error_spread")
        quantiles = row.get("window_error_quantiles") or {}
        lines.append(
            f"candidate {row['candidate_id']}: {row.get('tier')}, "
            f"whole {_fmt_pct(row.get('worst_error_rate'))}, "
            f"window p95 {_fmt_pct(quantiles.get('p95'))}, "
            f"{(row.get('minimum_empirical_information_bits_per_mm2') or 0.0):.1f} b/mm2"
            + (
                f", club spread {_fmt_pct(spread)}"
                if spread is not None else ""
            )
        )
    for margin in summary.get("capacity_by_margin_mm", {}).get(
        "margins", []
    ):
        if margin.get("source") != "measured-clip-worst-edge":
            continue
        top = sorted(
            margin.get("candidates", []),
            key=lambda row: -float(row["empirical_information_bits"]),
        )[:2]
        for row in top:
            megabits = float(row["empirical_information_bits"]) / 1e6
            lines.append(
                f"capacity at measured clip "
                f"({_fmt_mm(margin.get('margin_mm'))} margins): "
                f"{row['candidate_id']} ~{megabits:.2f} Mbit info bound"
            )
    registration = summary.get("registration_map", {})
    lines.append(
        "registration: "
        f"{registration.get('n_observations', 0)} observations, max "
        f"{registration.get('max_displacement_layout_dots') or 0.0:.1f} "
        "dots displacement"
    )
    paper = report.get("geometry", {}).get("paper_edges", {})
    visible = [
        f"{edge}:{row.get('status')}"
        for edge, row in paper.get("edges", {}).items()
    ]
    if visible:
        lines.append("paper edges: " + "  ".join(sorted(visible)))
    return lines


def _candidate_code(value: str) -> int:
    if value.isdecimal():
        code = int(value)
        if code in CANDIDATES_BY_CODE:
            return code
    candidate = CANDIDATES_BY_ID.get(value)
    if candidate is None:
        raise argparse.ArgumentTypeError(
            f"unknown current candidate code/id {value!r}"
        )
    return candidate.code


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _scan_dpi(args: argparse.Namespace) -> tuple[float, float]:
    if args.scan_dpi is not None:
        if args.scan_dpi_x is not None or args.scan_dpi_y is not None:
            raise ValueError(
                "use --scan-dpi or the x/y pair, not both forms"
            )
        return float(args.scan_dpi), float(args.scan_dpi)
    if args.scan_dpi_x is None or args.scan_dpi_y is None:
        raise ValueError(
            "true capture resolution is required: use --scan-dpi or both "
            "--scan-dpi-x and --scan-dpi-y"
        )
    return float(args.scan_dpi_x), float(args.scan_dpi_y)


def _emit_discovery(args: argparse.Namespace) -> int:
    bundle = emit_bundle(
        args.output_dir,
        stage="discovery",
        copy_index=args.copy_index,
        request_code=args.request,
        kinds=_kind_values(args.kind),
        max_job_bytes=args.max_job_mib << 20,
    )
    print(json.dumps({
        "bundle_manifest": bundle["bundle_manifest"],
        "pages": [
            {
                "kind": row["kind"],
                "postscript": row["postscript"],
                "page_manifest": row["page_manifest"],
            }
            for row in bundle["pages"]
        ],
    }, indent=2))
    return 0


def _calibration_selection(
    args: argparse.Namespace,
) -> tuple[tuple[str, ...], dict[str, tuple[int, ...]]]:
    codes = set(int(code) for code in args.candidate)
    expected_request = REQUEST_CODES[args.request]
    for report_path in args.from_report:
        report = _read_json(report_path)
        selected = shortlist_candidate_codes(
            report, limit=args.shortlist_limit
        )
        identity = report["page_identity"]
        if int(identity.get("request_code", -1)) != expected_request:
            raise ValueError(
                f"{report_path}: discovery request footing does not match "
                f"--request {args.request}"
            )
        codes.update(selected)
    if not codes:
        raise ValueError(
            "calibration needs --candidate and/or --from-report"
        )
    grouped: dict[str, tuple[int, ...]] = {}
    requested = _kind_values(args.kind)
    for kind in requested:
        selected = tuple(sorted(
            code for code in codes
            if CANDIDATES_BY_CODE[code].page_kind == kind
        ))
        if not selected:
            raise ValueError(
                f"no selected candidate belongs to requested {kind} page"
            )
        grouped[kind] = validate_shortlist(kind, selected)
    return requested, grouped


def _emit_calibration(args: argparse.Namespace) -> int:
    kinds, selection = _calibration_selection(args)
    bundle = emit_bundle(
        args.output_dir,
        stage="calibration",
        copy_index=args.copy_index,
        request_code=args.request,
        candidate_codes=selection,
        kinds=kinds,
        max_job_bytes=args.max_job_mib << 20,
    )
    print(json.dumps({
        "bundle_manifest": bundle["bundle_manifest"],
        "candidate_codes": {
            kind: list(codes) for kind, codes in selection.items()
        },
        "pages": bundle["pages"],
    }, indent=2))
    return 0


def _analyze(args: argparse.Namespace) -> int:
    dpi_x, dpi_y = _scan_dpi(args)
    report = analyze_scan(
        args.scan,
        scan_dpi_x=dpi_x,
        scan_dpi_y=dpi_y,
        manifest=args.manifest,
        footing={
            key: value for key, value in {
                "printer": args.printer,
                "print_path": args.print_path,
                "media": args.media,
                "scanner": args.scanner,
                "scan_mode": args.scan_mode,
                "print_session": args.print_session,
            }.items() if value
        },
    )
    path = write_report(args.output_dir, report)
    print(json.dumps({
        "status": report["status"],
        "report": str(path),
        "refusal": report.get("refusal"),
        "highest_useful_authored_grid_dpi": (
            report.get("summary", {})
            .get("dpi_and_cells", {})
            .get("highest_useful_authored_grid_dpi")
        ),
    }, indent=2))
    if report["status"] == "ok":
        for line in _stdout_summary(report):
            print(line)
    return 0 if report["status"] == "ok" else 2


def _combine(args: argparse.Namespace) -> int:
    summary = combine_calibration_reports(
        _read_json(path) for path in args.reports
    )
    summary["summary_semantic_sha256"] = semantic_digest(summary)
    name = (
        f"hcal-calibration-summary-{summary['kind']}-"
        f"{summary['summary_semantic_sha256'][:16]}.json"
    )
    path = Path(args.output_dir) / name
    write_new_bytes(path, json_bytes(summary))
    print(json.dumps({
        "summary": str(path),
        "candidate_results": summary["candidate_results"],
    }, indent=2))
    return 0


def _list_candidates(args: argparse.Namespace) -> int:
    rows = []
    for code, candidate in CANDIDATES_BY_CODE.items():
        if args.kind != "both" and candidate.page_kind != args.kind:
            continue
        rows.append(candidate.to_dict())
    print(json.dumps(rows, indent=2))
    return 0


def _parser(
    *,
    prog: str = "python -m holo.characterize",
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Emit and analyze standalone printer/scanner discovery and "
            "calibration sheets."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discovery = subparsers.add_parser(
        "emit",
        help="write the default-request B/W and color discovery jobs",
    )
    discovery.add_argument("output_dir")
    discovery.add_argument("--copy-index", type=int, default=0)
    discovery.add_argument(
        "--request", choices=tuple(REQUEST_CODES), default="default"
    )
    discovery.add_argument(
        "--kind", choices=("both", "bw", "color"), default="both"
    )
    discovery.add_argument("--max-job-mib", type=int, default=128)
    discovery.set_defaults(run=_emit_discovery)

    analyze = subparsers.add_parser(
        "analyze", help="blindly identify and analyze one scan"
    )
    analyze.add_argument("scan")
    analyze.add_argument("output_dir")
    analyze.add_argument("--scan-dpi", type=float)
    analyze.add_argument("--scan-dpi-x", type=float)
    analyze.add_argument("--scan-dpi-y", type=float)
    analyze.add_argument("--manifest")
    analyze.add_argument("--printer", required=True)
    analyze.add_argument("--print-path", required=True)
    analyze.add_argument("--media", required=True)
    analyze.add_argument("--scanner", required=True)
    analyze.add_argument("--scan-mode", required=True)
    analyze.add_argument("--print-session", required=True)
    analyze.set_defaults(run=_analyze)

    calibration = subparsers.add_parser(
        "calibrate",
        help="write calibration jobs for an explicit/current shortlist",
    )
    calibration.add_argument("output_dir")
    calibration.add_argument(
        "--candidate", action="append", type=_candidate_code, default=[]
    )
    calibration.add_argument(
        "--from-report", action="append", default=[],
        help="add the report's top provisionally usable candidates",
    )
    calibration.add_argument("--shortlist-limit", type=int, default=8)
    calibration.add_argument("--copy-index", type=int, default=1)
    calibration.add_argument(
        "--request", choices=tuple(REQUEST_CODES), default="default"
    )
    calibration.add_argument(
        "--kind", choices=("both", "bw", "color"), default="both"
    )
    calibration.add_argument("--max-job-mib", type=int, default=128)
    calibration.set_defaults(run=_emit_calibration)

    combine = subparsers.add_parser(
        "combine",
        help="take conservative minima across calibration copies",
    )
    combine.add_argument("output_dir")
    combine.add_argument("reports", nargs="+")
    combine.set_defaults(run=_combine)

    listing = subparsers.add_parser(
        "candidates", help="print the fixed current candidate registry"
    )
    listing.add_argument(
        "--kind", choices=("both", "bw", "color"), default="both"
    )
    listing.set_defaults(run=_list_candidates)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    prog: str = "python -m holo.characterize",
) -> int:
    parser = _parser(prog=prog)
    args = parser.parse_args(argv)
    try:
        return int(args.run(args))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())

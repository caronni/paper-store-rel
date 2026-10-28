"""Arm comparison tables in the docs/PAYLOAD-MEASUREMENTS.md style.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.compare --run A.json --run B.json \
            [--baseline-state xerox-c3-cmy7] [--out table.md]

Rows are captures, columns are arms.  CPU seconds are the primary cost
metric (wall is reported but is load-sensitive — the campaign compares
arms on CPU, COLOR-UPLIFT-PLAN B2).  The wrong-certificate column is
ALWAYS shown: bar B5 is the campaign-stopping hard bar, so its value must
be visible even when it is zero.  A cell reads ``?`` when the number was
not measured — never a guess.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import corpus


def _load_run(path: str) -> dict:
    row = json.loads(Path(path).read_text())
    if row.get("schema") != "color-uplift-run-1":
        raise SystemExit(f"{path}: not a color-uplift run JSON")
    return row


def _arm_label(run: dict) -> str:
    suffix = " (force-null)" if run.get("force_null") else ""
    mode = run["mode"]
    return f"{run['arm']}/{mode}{suffix}"


def _stream_cell(counts: dict | None, streams: list[str]) -> str:
    if not counts:
        return "0"
    if streams == ["main"]:
        return str(counts.get("main", 0))
    return " / ".join(f"{name} {counts.get(name, 0)}" for name in streams)


def _wrong_cell(run: dict, scores: dict) -> str:
    audit = scores.get(run["run_key"], {}).get("certificate_audit")
    if audit is None:
        return "?"
    bad = audit.get("disagreeing_addresses", 0)
    return "0" if not bad else f"**{bad} WRONG**"


def _baseline_row(key: str) -> dict:
    """Archived-baseline summary straight from the frozen provenance."""
    recorded = corpus.provenance_row(key)
    baseline = recorded["baseline"]
    return {
        "certificates": baseline["archived_certificates"],
        "close": baseline["state_status"],
        "flags": baseline["flags"],
        "certificates_by_lane": None,
    }


def build_table(runs: list[dict], scores: dict,
                baselines: list[str]) -> str:
    by_capture: dict[str, dict[str, dict]] = {}
    arms: list[str] = []
    for run in runs:
        label = _arm_label(run)
        if label not in arms:
            arms.append(label)
        by_capture.setdefault(run["capture"], {})[label] = run
    for key in baselines:
        by_capture.setdefault(key, {})

    lines: list[str] = []
    lines.append("### Certificates by stream (cumulative, all lanes)")
    lines.append("")
    header = ["capture", "archived baseline", *arms, "wrong certs"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for capture in sorted(by_capture):
        recorded = corpus.provenance_row(capture)
        streams = recorded["stream_ids"]
        archived_total = recorded["baseline"]["archived_certificates"]
        cells = [capture, f"{archived_total}"]
        wrong = []
        for arm in arms:
            run = by_capture[capture].get(arm)
            if run is None:
                cells.append("—")
                continue
            totals = run.get("totals", {})
            cell = _stream_cell(totals.get("by_stream"), streams)
            total = totals.get("certificates")
            delta = ("" if archived_total is None or total is None
                     else f" ({total - archived_total:+d})")
            cells.append(f"{cell}{delta}")
            wrong.append(_wrong_cell(run, scores))
        cells.append(", ".join(wrong) if wrong else "?")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("### Cost (CPU seconds primary; wall is load-sensitive)")
    lines.append("")
    header = ["capture", "arm", "CPU s", "wall s", "peak RSS MiB",
              "lanes", "blocks", "attempts"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for run in runs:
        totals = run.get("totals", {})
        lanes = run.get("lanes", [])
        lines.append("| " + " | ".join((
            run["capture"], _arm_label(run),
            str(totals.get("cpu_s", "?")),
            str(totals.get("wall_s", "?")),
            str(totals.get("peak_rss_mib", "?")),
            str(len(lanes)),
            str(sum(lane.get("blocks", 0) for lane in lanes)),
            str(sum(lane.get("attempts", 0) for lane in lanes)),
        )) + " |")

    lines.append("")
    lines.append("### Per-lane certificates (replay vs archived barrier)")
    lines.append("")
    header = ["capture", "arm", "lane", "kind", "placements",
              "prior certs", "certs", "archived certs", "CPU s"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for run in runs:
        for lane in run.get("lanes", []):
            archived = lane.get("archived_certificates")
            mark = ("" if archived is None
                    or archived == lane["certificates"] else "  ⚠")
            lines.append("| " + " | ".join((
                run["capture"], _arm_label(run), lane["lane_id"],
                lane["lane_kind"], str(lane["placements"]),
                str(lane["prior_certificates"]),
                f"{lane['certificates']}{mark}",
                "?" if archived is None else str(archived),
                str(lane.get("cpu_s", "?")),
            )) + " |")

    lines.append("")
    lines.append("### Notes")
    for run in runs:
        head = run["worktree"]["head"][:9]
        dirty = " (dirty)" if run["worktree"].get("dirty") else ""
        diff = scores.get(run["run_key"], {}).get(
            "certificate_set_vs_archived", {})
        identity = ("identical" if diff.get("identical")
                    else f"missing {diff.get('missing')} / extra "
                         f"{diff.get('extra')}"
                    if diff.get("comparable") else "not compared")
        lines.append(
            f"- `{run['capture']}` {_arm_label(run)}: head {head}{dirty}, "
            f"policy `{run['color_payload_policy_id'][:60]}…`, "
            f"certificate set vs archived: {identity}"
            + (", diag observer attached"
               if run.get("diagnostics", {}).get("enabled") else ""))
    for key in baselines:
        row = _baseline_row(key)
        lines.append(
            f"- `{key}` ARCHIVED baseline: {row['certificates']} "
            f"certificates, close {row['close']}, flags "
            f"--complete={row['flags']['complete']} "
            f"--refine={row['flags']['refine']} "
            f"--page={row['flags']['page']}")
    lines.append(
        "- Replays are development signal; FULL decodes are the only "
        "qualification numbers (RECEIVE-DESIGN §6.2a).")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.compare", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="append", default=[], required=True)
    parser.add_argument("--score", action="append", default=[],
                        help="gt_score run JSON for the same run (pairs by "
                             "the run path recorded inside)")
    parser.add_argument("--baseline-state", action="append", default=[],
                        help="capture key whose ARCHIVED baseline to list")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    runs = []
    for path in args.run:
        run = _load_run(path)
        run["run_key"] = str(Path(path).resolve())
        runs.append(run)
    scores: dict[str, dict] = {}
    for path in args.score:
        score = json.loads(Path(path).read_text())
        scores[str(Path(score["run"]).resolve())] = score
    table = build_table(runs, scores, list(args.baseline_state))
    if args.out:
        Path(args.out).write_text(table)
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Roll several battery reports into one verdict table + one shift map.

    PYTHONPATH=src:. env/bin/python -m measure.yask.summarize \\
        build/yask/*.json

Two outputs, both read straight out of the reports — nothing is
recomputed and nothing is re-decoded:

* **the verdict table**, one row per (case, arm), with the additive
  count that the pre-registered bar is about;
* **the registration map**, the blind per-window sampling offset the
  A1/A2 arms chose, binned by the window's page-x position. The yellow
  plane's x-registration wanders across the sheet (e033 measured a
  0.83-dot, ~100 mm sinusoid on the AltaLink from the certificate
  residue); this is the same quantity read off the yellow signal
  itself, by a blind estimator, on whatever crops the battery ran.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

CELLS_PER_INCH = 300.0
MM_PER_INCH = 25.4


def load(paths: list[Path]) -> list[dict]:
    reports: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports.extend(payload if isinstance(payload, list) else [payload])
    return reports


def verdict_rows(reports: list[dict]) -> list[str]:
    lines = ["| case | capture | arm | Y certs | GT-exact | WRONG | "
             "**adds** | target d' | target cell err | live d' |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for report in sorted(reports, key=lambda r: (r["case"], r.get("capture", ""))):
        for name, arm in report["arms"].items():
            decode = arm.get("decode")
            if decode is None:
                continue
            target = (arm.get("separation") or {}).get("target") or {}
            live = (arm.get("separation") or {}).get("live") or {}
            lines.append(
                f"| {report['case']} | {report.get('capture', '?')} | {name} "
                f"| {decode['certificates']} | {decode['gt_exact']} "
                f"| {decode['wrong']} | **{decode['adds']}** "
                f"| {_fmt(target.get('dprime'))} "
                f"| {_fmt(target.get('cell_error'), 4)} "
                f"| {_fmt(live.get('dprime'))} |")
    return lines


def registration_rows(reports: list[dict], bin_mm: float = 10.0
                      ) -> list[str]:
    buckets: dict[int, list[float]] = defaultdict(list)
    for report in reports:
        for name, arm in report["arms"].items():
            if arm.get("shift") != "blind":
                continue
            for lane in arm.get("lanes", {}).values():
                for entry in lane.get("shift_table", ()):
                    origin = entry.get("window")
                    if not origin:
                        continue
                    # the window's page-x centre, in mm across the sheet
                    centre_cells = float(origin[1]) + 100.0
                    mm = centre_cells / CELLS_PER_INCH * MM_PER_INCH
                    buckets[int(mm // bin_mm)].append(
                        float(entry["shift_dots"]))
    lines = [f"| page x (mm, {bin_mm:.0f} mm bins) | windows | "
             "mean blind offset (dots) | min | max |",
             "|---|---:|---:|---:|---:|"]
    for key in sorted(buckets):
        values = buckets[key]
        lines.append(
            f"| {key * bin_mm:.0f}-{(key + 1) * bin_mm:.0f} | "
            f"{len(values)} | {sum(values) / len(values):+.3f} | "
            f"{min(values):+.2f} | {max(values):+.2f} |")
    return lines


def totals(reports: list[dict]) -> list[str]:
    per_arm: dict[str, dict[str, int]] = defaultdict(
        lambda: {"certs": 0, "gt": 0, "wrong": 0, "adds": 0, "cases": 0})
    for report in reports:
        for name, arm in report["arms"].items():
            decode = arm.get("decode")
            if decode is None:
                continue
            row = per_arm[name]
            row["certs"] += decode["certificates"]
            row["gt"] += decode["gt_exact"]
            row["wrong"] += decode["wrong"]
            row["adds"] += decode["adds"]
            row["cases"] += 1
    lines = ["| arm | cases | Y certs | GT-exact | WRONG | **adds** |",
             "|---|---:|---:|---:|---:|---:|"]
    for name in sorted(per_arm):
        row = per_arm[name]
        lines.append(f"| {name} | {row['cases']} | {row['certs']} | "
                     f"{row['gt']} | {row['wrong']} | **{row['adds']}** |")
    return lines


def _fmt(value, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--bin-mm", type=float, default=10.0)
    args = parser.parse_args(argv)
    reports = load(args.reports)
    print("## totals by arm\n")
    print("\n".join(totals(reports)))
    print("\n## per case\n")
    print("\n".join(verdict_rows(reports)))
    print("\n## blind sampling offset by page x\n")
    print("\n".join(registration_rows(reports, args.bin_mm)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

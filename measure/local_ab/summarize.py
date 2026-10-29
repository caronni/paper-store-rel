#!/usr/bin/env python
"""Roll several case reports into one verdict table.

    PYTHONPATH=src:. <python> -m measure.local_ab.summarize \\
        build/local-ab/reports/*.json

Reads the JSON each battery writes and prints the union-vs-per-origin
table across every case, plus the pooled zero-wrong audit. Sim reports
(``sim-*.json``) are recognised and listed separately: their arm counts
come from the POSITIVE CONTROL, not from a residue population, so they
must never be added into a residue total.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _case_row(name: str, payload: dict) -> dict:
    summary = payload["summary"]
    classes = summary["classes"]
    cpu = summary["cpu_seconds"]
    return {
        "case": name,
        "population": "residue",
        "subjects": summary["n_subjects"],
        "union": summary["union_adds"],
        "per_origin": summary["per_origin_adds"],
        "both": classes["both"],
        "union_only": classes["union_only"],
        "per_origin_only": classes["per_origin_only"],
        "neither": classes["neither"],
        "null": summary["null_certificates"],
        "build_cpu_s": cpu["component_build_shared"],
        "union_cpu_s": cpu["union_attempts"],
        "per_origin_cpu_s": cpu["per_origin_attempts_exhaustive"],
        "per_origin_stop_cpu_s": cpu["per_origin_attempts_first_cert_stop"],
        "audits": [(a["n_checked"], a["n_wrong"]) for a in payload["audits"]],
    }


def _sim_row(name: str, payload: dict) -> dict:
    control = payload.get("positive_control", [])
    return {
        "case": name,
        "population": "positive control",
        "subjects": len(control),
        "union": sum(1 for row in control if row["union"]),
        "per_origin": sum(1 for row in control if row["per_origin"]),
        "both": sum(1 for row in control
                    if row["union"] and row["per_origin"]),
        "union_only": sum(1 for row in control
                          if row["union"] and not row["per_origin"]),
        "per_origin_only": sum(1 for row in control
                               if row["per_origin"] and not row["union"]),
        "neither": sum(1 for row in control
                       if not row["union"] and not row["per_origin"]),
        "null": payload["null_certificates"],
        "build_cpu_s": payload["cpu_seconds"]["component_build_shared"],
        "union_cpu_s": payload["cpu_seconds"]["union_attempts"],
        "per_origin_cpu_s": payload["cpu_seconds"]["per_origin_attempts"],
        "per_origin_stop_cpu_s": None,
        "audits": [(a["n_checked"], a["n_wrong"]) for a in payload["audits"]],
    }


def rows(paths: list[Path]) -> list[dict]:
    out: list[dict] = []
    for path in sorted(paths):
        payload = json.loads(path.read_text(encoding="utf-8"))
        name = path.stem
        out.append(_sim_row(name, payload) if "summary" not in payload
                   else _case_row(name, payload))
    return out


def render(collected: list[dict]) -> str:
    lines = ["# local_ab — union vs per-origin, all cases", "",
             "| case | population | subjects | union | per-origin | both | "
             "union only | per-origin only | neither | **null** |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in collected:
        lines.append(
            f"| {row['case']} | {row['population']} | {row['subjects']} | "
            f"{row['union']} | {row['per_origin']} | {row['both']} | "
            f"{row['union_only']} | {row['per_origin_only']} | "
            f"{row['neither']} | **{row['null']}** |")
    residue = [row for row in collected if row["population"] == "residue"]
    if residue:
        lines += ["", "Residue totals: union "
                  f"{sum(r['union'] for r in residue)}, per-origin "
                  f"{sum(r['per_origin'] for r in residue)}, per-origin only "
                  f"{sum(r['per_origin_only'] for r in residue)}, union only "
                  f"{sum(r['union_only'] for r in residue)}, over "
                  f"{sum(r['subjects'] for r in residue)} subjects."]
    checked = sum(n for row in collected for n, _ in row["audits"])
    wrong = sum(n for row in collected for _, n in row["audits"])
    lines += ["", f"Ground-truth audit across every case: **{checked}** "
              f"certificates checked against the emitted payload, "
              f"**{wrong}** wrong.", "",
              "| case | component build (shared) | union attempts | "
              "per-origin, all lanes | per-origin, stop at first cert |",
              "|---|---:|---:|---:|---:|"]
    for row in collected:
        stop = ("—" if row["per_origin_stop_cpu_s"] is None
                else f"{row['per_origin_stop_cpu_s']} s")
        lines.append(
            f"| {row['case']} | {row['build_cpu_s']} s | "
            f"{row['union_cpu_s']} s | {row['per_origin_cpu_s']} s | "
            f"{stop} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args(argv)
    missing = [str(path) for path in args.reports if not path.is_file()]
    if missing:
        raise SystemExit("local_ab: no such report(s): " + ", ".join(missing))
    collected = rows(args.reports)
    print(render(collected))
    return 2 if any(n for row in collected
                    for _, n in row["audits"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())

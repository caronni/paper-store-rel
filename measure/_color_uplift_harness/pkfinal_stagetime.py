"""PK-FINAL derivation tool (committed per review disposition 2026-08-10).

Stage timing (bar B2): archived events vs candidate FULL run.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.pkfinal_stagetime --capture xerox-c2-k

`ab_runner full` sums `timing.processor_seconds` off the runtime's own
`stage.complete`/`stage.refused` events into `stage_seconds`.  The
ARCHIVED runs emitted the identical detail into their `events.jsonl`, so
this reads them the same way and puts the two side by side.  Two honest
caveats travel with every number here: the epochs are different machines
under different load (the archived decodes are from the 2026-08 print
days), and a candidate colour plan runs SUPPLEMENTAL u-lanes the archived
plan never scheduled — so the u-lane column is broken out and never
folded into the ladder comparison.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import corpus


def kind_of(lane: str) -> str:
    if lane.startswith("u"):
        return "uplift"
    if lane.startswith("m"):
        return "mopup"
    if lane.startswith("r"):
        return "refine"
    return "base"


def scan(path: Path) -> dict:
    totals: dict[str, float] = {}
    per_lane: dict[str, float] = {}
    with open(path) as handle:
        for line in handle:
            event = json.loads(line)
            if event.get("name") not in ("stage.complete", "stage.refused"):
                continue
            details = event.get("details") or {}
            seconds = details.get("timing.processor_seconds")
            if not isinstance(seconds, (int, float)):
                continue
            lane = str(details.get("lane.id", "?"))
            key = f"{kind_of(lane)}.{event.get('stage')}"
            totals[key] = totals.get(key, 0.0) + float(seconds)
            per_lane[lane] = per_lane.get(lane, 0.0) + float(seconds)
    return {"stage_seconds": {k: round(v, 1) for k, v in sorted(
        totals.items())}, "lane_seconds": {k: round(v, 1) for k, v in
                                           per_lane.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.pkfinal_stagetime", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--arm", default="pkfinal")
    parser.add_argument("--runs", default=None,
                        help="run JSON directory (default <work>/runs)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    row = corpus.capture(args.capture)
    runs = Path(args.runs) if args.runs else corpus.work_dir("runs")
    archived = scan(row.diag_path() / "events.jsonl")
    run = json.loads(
        (runs / f"{args.capture}-full-{args.arm}.json").read_text())
    # NOT run["stage_seconds"] historically: the harness observer used to
    # classify a lane as mop-up/refine by its first letter and folded a
    # `u` lane into "base".  ``run_full`` now breaks u-lanes out itself
    # (review disposition 2026-08-10), but the candidate is still
    # re-scanned from its OWN events so both epochs pass through exactly
    # the same classifier here, and the harness column is kept beside it.
    candidate = scan(runs / f"{args.capture}-full-{args.arm}.diag"
                     / "events.jsonl")
    candidate["harness_stage_seconds"] = run["stage_seconds"]

    keys = sorted(set(archived["stage_seconds"]) | set(
        candidate["stage_seconds"]))
    print(f"# {args.capture}: timing.processor_seconds by stage class")
    print(f"{'stage':22s} {'archived':>10s} {'candidate':>10s} {'delta':>10s}")
    for key in keys:
        a = archived["stage_seconds"].get(key, 0.0)
        c = candidate["stage_seconds"].get(key, 0.0)
        print(f"{key:22s} {a:10.1f} {c:10.1f} {c - a:+10.1f}")
    a_all = sum(archived["stage_seconds"].values())
    c_all = sum(candidate["stage_seconds"].values())
    c_u = sum(value for key, value in candidate["stage_seconds"].items()
              if key.startswith("uplift"))
    print(f"{'TOTAL':22s} {a_all:10.1f} {c_all:10.1f} {c_all - a_all:+10.1f}")
    print(f"{'  of which u-lanes':22s} {0.0:10.1f} {c_u:10.1f}")
    print(f"{'  standard lanes':22s} {a_all:10.1f} {c_all - c_u:10.1f} "
          f"{c_all - c_u - a_all:+10.1f}"
          + (f"  ({(c_all - c_u) / a_all - 1:+.1%})" if a_all else ""))
    document = {"capture": args.capture, "arm": args.arm,
                "archived": archived, "candidate": candidate,
                "archived_total_s": round(a_all, 1),
                "candidate_total_s": round(c_all, 1),
                "candidate_uplift_lane_s": round(c_u, 1),
                "candidate_standard_s": round(c_all - c_u, 1),
                "run_totals": run["totals"]}
    if args.out:
        Path(args.out).write_text(json.dumps(document, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

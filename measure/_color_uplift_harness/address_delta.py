"""Address-level A/B between two harness run JSONs.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.address_delta \
            --baseline runs/xerox-c3-cmy7-replay-pk31.json \
            --candidate runs/xerox-c3-cmy7-replay-pk4.json

Certificate IDs are lane-dependent — the same tile certified at a
different barrier is a different id — so a certificate-count delta cannot
separate "gained a tile" from "certified the same tile one lane later".
The honest unit is the ADDRESS `(page, tile_y, tile_x, stream)`, which is
what COLOR-UPLIFT-MEASUREMENTS §4.5 reports and what
`gt_score run --run` cannot give (it compares against the ARCHIVED state,
not against another arm).

Prints, per stream: gained, lost, net; then per-lane certificate counts
side by side with each lane's window-map diagnostics, so a lane
regression is visible next to the arm decision that produced it.

Read-only: it opens two JSONs and writes nothing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

Address = tuple[int, int, int, str]


def load(path: str) -> dict:
    row = json.loads(Path(path).read_text())
    if row.get("schema") != "color-uplift-run-1":
        raise SystemExit(f"{path}: not a color-uplift run JSON")
    return row


def addresses(run: dict) -> set[Address]:
    return {
        (int(row["page"]), int(row["tile_yx"][0]), int(row["tile_yx"][1]),
         str(row["stream_id"]))
        for row in run["certificates"]
    }


def by_stream(rows: set[Address]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[3]] = counts.get(row[3], 0) + 1
    return dict(sorted(counts.items()))


def uplift_addresses(run: dict) -> dict[str, set[Address]]:
    """PK4.3: the addresses each SUPPLEMENTAL lane minted, per lane.

    Keyed on the lane KIND the run JSON records (``uplift:<arm>``), so a
    u-lane's contribution is read from the run rather than guessed from
    a lane-id spelling.
    """
    uplift_lanes = {
        lane["lane_id"] for lane in run["lanes"]
        if str(lane.get("lane_kind", "")).startswith("uplift")}
    rows: dict[str, set[Address]] = {name: set() for name in uplift_lanes}
    for row in run["certificates"]:
        lane_id = row.get("lane_id")
        if lane_id in rows:
            rows[lane_id].add(
                (int(row["page"]), int(row["tile_yx"][0]),
                 int(row["tile_yx"][1]), str(row["stream_id"])))
    return rows


def report(baseline: dict, candidate: dict) -> dict:
    before, after = addresses(baseline), addresses(candidate)
    gained, lost = after - before, before - after
    lanes = {lane["lane_id"]: lane for lane in baseline["lanes"]}
    rows = []
    for lane in candidate["lanes"]:
        other = lanes.get(lane["lane_id"], {})
        region = lane["details"].get("payload.region", {})
        rows.append({
            "lane_id": lane["lane_id"],
            "candidate": lane["certificates"],
            "baseline": other.get("certificates"),
            "archived": lane["archived_certificates"],
            "by_stream": lane["certificates_by_stream"],
            "window_maps": {
                key.rsplit(".", 1)[-1]: value
                for key, value in sorted(region.items())
                if key.startswith("color.window_maps.")
            },
        })
    return {
        "baseline": {
            "arm": baseline["arm"], "force_null": baseline["force_null"],
            "certificates": baseline["totals"]["certificates"],
            "addresses": len(before), "by_stream": by_stream(before)},
        "candidate": {
            "arm": candidate["arm"], "force_null": candidate["force_null"],
            "certificates": candidate["totals"]["certificates"],
            "addresses": len(after), "by_stream": by_stream(after)},
        "gained": {"n": len(gained), "by_stream": by_stream(gained)},
        "lost": {"n": len(lost), "by_stream": by_stream(lost),
                 "examples": sorted(lost)[:20]},
        "net": len(gained) - len(lost),
        # PK4.3: monotonicity is claimed STRUCTURALLY and verified
        # EMPIRICALLY.  ``superset`` is the claim as a boolean, on the
        # addresses, in every score.
        "superset": not lost,
        "uplift": _uplift_report(candidate, before),
        "lanes": rows,
        "close": candidate.get("close"),
    }


def _uplift_report(candidate: dict, before: set[Address]) -> dict:
    """Per-u-lane adds, and the two facts that make them adds.

    ``new_vs_baseline`` is the honest number — addresses this u-lane
    minted that the baseline arm never certified anywhere.  ``re_timed``
    is the rest: tiles the baseline also got, which a u-lane can only
    produce when the baseline certified them in a LATER lane than this
    run did, and which are yield only once.
    """
    rows = uplift_addresses(candidate)
    if not rows:
        return {"lanes": {}, "total_new": 0}
    detail: dict[str, dict] = {}
    total: set[Address] = set()
    for lane_id, minted in sorted(rows.items()):
        fresh = minted - before
        total |= fresh
        detail[lane_id] = {
            "minted": len(minted),
            "by_stream": by_stream(minted),
            "new_vs_baseline": len(fresh),
            "new_by_stream": by_stream(fresh),
            "re_timed": len(minted & before),
        }
    return {"lanes": detail, "total_new": len(total)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.address_delta", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    result = report(load(args.baseline), load(args.candidate))
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    from _color_uplift_harness import address_delta as _module

    raise SystemExit(_module.main())

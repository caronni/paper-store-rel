#!/usr/bin/env python
"""The two receivers' placement census, side by side.

    PYTHONPATH=. env/bin/python -m measure.angle_residue_census

holo3's side is read from the run dir's own ``events.jsonl`` (the CLI
writes it); holo2's from the ``census.json`` the wrapper in
``measure.angle_residue_h2`` dumps.  Nothing is re-derived from a
receiver's internals here — both sides are read off recorded artifacts.

The window key is level-aware on both sides, which is what the
2026-08-31 angle post-mortem found matters: ``report.json``'s
``live_windows`` drops ``level_index`` and collides lanes.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "angle-residue"

#: holo3 stage names by class, for the cost census.
EXPENSIVE = ("wide", "cold_live", "cold_rest")

#: ``holo3.plugins.place.STAGE_COST`` and its two rung terms, spelled
#: here so a JobDone's recorded ``cost`` can be inverted back to the
#: stage that ran (the event does not carry the stage, and
#: ``WindowScheduled`` is emitted only when (stage, cost) MOVES).
STAGE_COST = {"ring": 40, "word_centre": 60, "word_rest": 80,
              "wide": 120, "cold_live": 140, "cold_rest": 150}
COLD_STAGES = ("cold_live", "cold_rest")


def stage_for_cost(cost: int, lane: int, depth: int) -> str:
    for stage, base in STAGE_COST.items():
        rung = 20 if stage in COLD_STAGES else 2
        if base + rung * lane + (5 if depth else 0) == cost:
            return stage
    return f"?cost{cost}"


def holo3_census(run_dir: Path) -> dict:
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        return {"error": f"no events.jsonl in {run_dir}"}
    scheduled: dict[tuple, dict] = {}
    settled: dict[tuple, str] = {}
    settle_rows: Counter = Counter()
    placed: set[tuple] = set()
    retired: dict[tuple, str] = {}
    fires_by_stage: Counter = Counter()
    cpu_by_stage: dict[str, float] = defaultdict(float)
    fires_by_window: Counter = Counter()
    cpu_by_window: dict = defaultdict(float)
    stage_of_window: dict[tuple, list[str]] = defaultdict(list)
    #: subdivision depth, read off the price parity (a child adds 5 to an
    #: otherwise even price, so an odd cost names a child exactly).
    depth_of: dict[tuple, int] = {}
    place_jobs = 0
    place_cpu = 0.0
    total_cpu = 0.0
    run_done = None
    engine_stat = None
    #: subject -> the stage its most recent WindowScheduled announced,
    #: which is the stage the next place JobDone for it ran.
    pending_stage: dict[tuple, str] = {}
    with events_path.open() as handle:
        for line in handle:
            event = json.loads(line)
            kind = event.get("type")
            if kind == "WindowScheduled":
                key = (event["capture"], event["level_index"],
                       event["region_index"],
                       tuple(event["extent_cells"]))
                scheduled.setdefault(key, dict(event))
                pending_stage[key] = event["stage"]
            elif kind == "WindowSettled":
                key = (event["capture"], event["level_index"],
                       event["region_index"],
                       tuple(event["extent_cells"]))
                settled[key] = event["state"]
                settle_rows[event["state"]] += 1
            elif kind == "PoseCommitted":
                key = (event["capture"], event["level_index"],
                       event["region_index"],
                       tuple(event["extent_cells"]))
                if event.get("accepted", True):
                    placed.add(key)
            elif kind == "WindowRetired":
                key = (event["capture"], event["level_index"],
                       event["region_index"],
                       tuple(event["extent_cells"]))
                retired[key] = event.get("cause", "?")
            elif kind == "JobDone":
                total_cpu += float(event.get("cpu_s", 0.0))
                if event.get("plugin") != "place":
                    continue
                place_jobs += 1
                place_cpu += float(event.get("cpu_s", 0.0))
                subject = event.get("subject")
                key = None
                if isinstance(subject, (list, tuple)) and len(subject) == 4:
                    key = (subject[0], subject[1], subject[2],
                           tuple(subject[3]))
                cost = int(event.get("cost", 0))
                lane = key[1] if key else 0
                # Parent prices are even (tier + even rung term); a child
                # adds 5, so cost parity names the depth exactly.
                stage = stage_for_cost(cost, lane, cost % 2)
                fires_by_stage[stage] += 1
                cpu_by_stage[stage] += float(event.get("cpu_s", 0.0))
                if key is not None:
                    fires_by_window[key] += 1
                    cpu_by_window[key] += float(event.get("cpu_s", 0.0))
                    stage_of_window[key].append(stage)
                    if cost % 2:
                        depth_of[key] = 1
            elif kind == "RunDone":
                run_done = event
            elif kind == "EngineStat":
                engine_stat = event
    live = {key: settled.get(key) for key in scheduled
            if key not in placed and key not in retired}
    by_lane_total: Counter = Counter()
    by_lane_live: Counter = Counter()
    for key in scheduled:
        by_lane_total[key[1]] += 1
    for key in live:
        by_lane_live[key[1]] += 1
    expensive_fires = sum(fires_by_stage[s] for s in EXPENSIVE)
    expensive_cpu = sum(cpu_by_stage[s] for s in EXPENSIVE)
    live_cpu = sum(cpu_by_window[key] for key in live)
    return {
        "scheduled": len(scheduled),
        "placed": len(placed),
        "retired": len(retired),
        "retire_causes": dict(Counter(retired.values())),
        "live_unresolved": len(live),
        "live_causes": dict(Counter(
            v or "no_settle" for v in live.values())),
        "by_lane_total": dict(sorted(by_lane_total.items())),
        "by_lane_live": dict(sorted(by_lane_live.items())),
        "lane_fail_rate": {
            str(lane): round(by_lane_live[lane] / by_lane_total[lane], 4)
            for lane in sorted(by_lane_total)},
        "place_jobs": place_jobs,
        "place_cpu_s": round(place_cpu, 1),
        "total_job_cpu_s": round(total_cpu, 1),
        "fires_by_stage": dict(fires_by_stage),
        "cpu_by_stage_s": {k: round(v, 1)
                           for k, v in sorted(cpu_by_stage.items())},
        "expensive_fires": expensive_fires,
        "expensive_cpu_s": round(expensive_cpu, 1),
        "settle_census": dict(settle_rows.most_common()),
        "fires_on_live_windows": sum(fires_by_window[k] for k in live),
        "cpu_on_live_windows_s": round(live_cpu, 1),
        "cpu_on_live_share": (round(live_cpu / place_cpu, 4)
                              if place_cpu else 0.0),
        "live_by_depth": dict(Counter(
            depth_of.get(key, 0) for key in live)),
        "max_fires_one_window": (max(fires_by_window.values())
                                 if fires_by_window else 0),
        "mean_fires_per_live_window": (
            round(sum(fires_by_window[k] for k in live) / len(live), 2)
            if live else 0.0),
        "run_done": run_done,
        "engine_stat": {k: engine_stat.get(k) for k in
                        ("wakes", "stale_skips", "retired", "retire_causes")}
        if engine_stat else None,
    }


def holo2_census(run_dir: Path) -> dict:
    path = run_dir / "census.json"
    if not path.exists():
        return {"error": f"no census.json in {run_dir}"}
    raw = json.loads(path.read_text())
    settles = raw["settles"]
    fires = raw["fires"]
    exits = raw["exits"]
    slots = raw["slots_end"]
    fires_by_stage: Counter = Counter()
    cpu_by_stage: dict[str, float] = defaultdict(float)
    for row in fires:
        if row["cold"]:
            stage = str(row["cold"])
        elif row["wide"]:
            stage = "wide"
        else:
            stage = row["stage"] or "ring_or_resample"
        fires_by_stage[stage] += 1
        cpu_by_stage[stage] += float(row["cpu_s"])
    tier_fires: Counter = Counter(str(row["tier"]) for row in settles)
    # ONE PASS = ONE ``WindowJob.run``.  ``settle`` is called twice per
    # pass by the orchestrator (once on the abandon path with
    # ``result is None``, once with the result), so the fire ledger — not
    # the settle ledger — is what counts passes.
    fires_by_window: Counter = Counter(row["window"] for row in fires)
    cpu_by_window: dict[str, float] = defaultdict(float)
    for row in fires:
        cpu_by_window[row["window"]] += float(row["cpu_s"])
    lane_of: dict[str, int] = {}
    for row in settles:
        if row["lane_depth"] is not None:
            lane_of[row["window"]] = row["lane_depth"]
    for row in slots:
        lane_of[row["window"]] = row["lane_depth"]
    by_lane_live: Counter = Counter(row["lane_depth"] for row in slots)
    exits_by_reason = Counter(row["reason"] for row in exits)
    total_windows = len(set(lane_of))
    by_lane_total: Counter = Counter(lane_of.values())
    expensive = ("wide_consult", "cold_live", "cold_rest")
    return {
        "entered": raw["counts_end"].get("entered"),
        "placed": raw["counts_end"].get("placed"),
        "retired": raw["counts_end"].get("retired"),
        "subdivided": raw["counts_end"].get("subdivided"),
        "cold_armed": raw["counts_end"].get("cold_armed"),
        "cold_fired": raw["counts_end"].get("cold_fired"),
        "pings": raw["counts_end"].get("pings"),
        "passes": raw["counts_end"].get("passes"),
        "windows_end": raw["counts_end"].get("windows"),
        "ready_end": raw["counts_end"].get("ready"),
        "exit_reasons": dict(exits_by_reason),
        "live_unresolved": len(slots),
        "live_dormant": sum(1 for row in slots if row["tier"] is None),
        "live_with_tier": dict(Counter(
            str(row["tier"]) for row in slots)),
        "by_lane_total": dict(sorted(by_lane_total.items())),
        "by_lane_live": dict(sorted(by_lane_live.items())),
        "lane_fail_rate": {
            str(lane): round(by_lane_live[lane] / by_lane_total[lane], 4)
            for lane in sorted(by_lane_total) if by_lane_total[lane]},
        "total_windows_seen": total_windows,
        "place_jobs": len(fires),
        "place_cpu_s": round(sum(float(r["cpu_s"]) for r in fires), 1),
        "fires_by_stage": dict(fires_by_stage),
        "cpu_by_stage_s": {k: round(v, 1)
                           for k, v in sorted(cpu_by_stage.items())},
        "expensive_fires": sum(tier_fires[t] for t in expensive),
        "tier_claims": dict(tier_fires),
        "settle_census": raw.get("settle_outcomes", {}),
        "fires_on_live_windows": sum(
            fires_by_window[row["window"]] for row in slots),
        "cpu_on_live_windows_s": round(sum(
            cpu_by_window[row["window"]] for row in slots), 1),
        "cpu_on_live_share": (
            round(sum(cpu_by_window[row["window"]] for row in slots)
                  / sum(cpu_by_window.values()), 4)
            if cpu_by_window else 0.0),
        "mean_fires_per_live_window": (
            round(sum(fires_by_window[row["window"]] for row in slots)
                  / len(slots), 2) if slots else 0.0),
        "max_fires_one_window": (max(fires_by_window.values())
                                 if fires_by_window else 0),
        "live_by_depth": dict(Counter(row["depth"] for row in slots)),
        "wall_seconds": round(raw.get("wall_seconds", 0.0), 1),
        "exit_code": raw.get("exit_code"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=OUT / "census-summary.json")
    args = parser.parse_args(argv)
    summary: dict = {}
    for run_dir in sorted(OUT.glob("holo*-a*")):
        if not run_dir.is_dir():
            continue
        side = run_dir.name.split("-a")[0]
        sidecar = run_dir / "sidecar.json"
        meta = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        census = (holo3_census(run_dir) if side == "holo3"
                  else holo2_census(run_dir))
        census["wall_seconds_outer"] = round(
            meta.get("wall_seconds", 0.0), 1)
        census["returncode"] = meta.get("returncode")
        summary[run_dir.name] = census
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --------------------------------------------------------------------------
# Two derived questions the raw census cannot answer, both read off the same
# holo3 event file.  Run with:
#     PYTHONPATH=. env/bin/python -c \
#       "from measure.angle_residue_census import *; reach_report(<run_dir>)"

def _region_shapes(run_dir: Path) -> dict:
    report = json.loads((run_dir / "report.json").read_text())
    shapes = {}
    for capture in report["capture_facts"]:
        for region in capture.get("regions", ()):
            shapes[(capture["capture"][:12], region["region_index"])] = \
                tuple(region["shape_cells"])
    return shapes


def _contains(outer, inner) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def reach_report(run_dir) -> dict:
    """How much of holo3's chain placement holo2's REACH could not have made.

    Replays the pose stream in order and asks, at each accepted chain
    commit, whether an anchor holo2 would have offered existed yet: a
    same-lane ring neighbour (``place_shared.ring_targets``) or a COARSER
    lane whose extent contains this one (``place_shared.donor_sources``).
    An upper bound on the loss — a window denied its anchor at time T may
    still be placed later by a different one — but it is the only census
    the recorded events support.

    Also reports the PLACEMENT-COVERAGE gate's opportunity: unresolved
    windows whose extent another lane of the same capture already posed.
    """
    from holo3.plugins.place import ring_neighbour_extents

    run_dir = Path(run_dir)
    shapes = _region_shapes(run_dir)
    placed_at = defaultdict(set)
    reachable = 0
    unreachable = 0
    by_lane = defaultdict(lambda: [0, 0])
    placed, retired, sched, cpu = set(), set(), {}, defaultdict(float)
    for line in (run_dir / "events.jsonl").open():
        event = json.loads(line)
        kind = event.get("type")
        if kind == "WindowScheduled":
            sched.setdefault((event["capture"], event["level_index"],
                              event["region_index"],
                              tuple(event["extent_cells"])), 1)
        elif kind == "WindowRetired":
            retired.add((event["capture"], event["level_index"],
                         event["region_index"],
                         tuple(event["extent_cells"])))
        elif kind == "JobDone" and event.get("plugin") == "place":
            subject = event["subject"]
            cpu[(subject[0], subject[1], subject[2],
                 tuple(subject[3]))] += float(event["cpu_s"])
        elif kind == "PoseCommitted" and event.get("accepted", True):
            capture, lane = event["capture"], event["level_index"]
            region, extent = event["region_index"], tuple(event["extent_cells"])
            placed.add((capture, lane, region, extent))
            if event["route"] == "chain":
                shape = shapes.get((capture[:12], region))
                have = placed_at[(capture, region)]
                ring = set(ring_neighbour_extents(shape, extent)) if shape \
                    else set()
                ok = any((lane, other) in have for other in ring) or any(
                    other_lane < lane and _contains(other_extent, extent)
                    for other_lane, other_extent in have)
                by_lane[lane][0] += 1
                if ok:
                    reachable += 1
                else:
                    unreachable += 1
                    by_lane[lane][1] += 1
            placed_at[(capture, region)].add((lane, extent))
    live = [key for key in sched if key not in placed and key not in retired]
    by_region = defaultdict(list)
    for capture, lane, region, extent in placed:
        by_region[(capture, region)].append((lane, extent))
    exact = [k for k in live if any(
        lane != k[1] and extent == k[3]
        for lane, extent in by_region.get((k[0], k[2]), ()))]
    covered = [k for k in live if any(
        lane != k[1] and _contains(extent, k[3])
        for lane, extent in by_region.get((k[0], k[2]), ()))]
    out = {
        "chain_poses_reachable_under_holo2_rule": reachable,
        "chain_poses_unreachable_under_holo2_rule": unreachable,
        "by_lane_chain_total_and_unreachable": {
            str(lane): by_lane[lane] for lane in sorted(by_lane)},
        "live_unresolved": len(live),
        "coverage_gate_exact_extent": len(exact),
        "coverage_gate_exact_cpu_s": round(sum(cpu[k] for k in exact), 1),
        "coverage_gate_covered_extent": len(covered),
        "coverage_gate_covered_cpu_s": round(sum(cpu[k] for k in covered), 1),
        "place_cpu_s": round(sum(cpu.values()), 1),
    }
    print(json.dumps(out, indent=2))
    return out

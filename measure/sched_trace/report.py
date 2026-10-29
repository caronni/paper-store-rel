"""Reduce one `sched-trace/` directory to a markdown report.

    PYTHONPATH=src env/bin/python measure/sched_trace/report.py RUN_DIR \
        [--out REPORT.md] [--top 20]

RUN_DIR is either the run directory the decode wrote (the one carrying
`events.jsonl`) or the `sched-trace/` directory inside it.  The reducer
is read-only, stdlib-only and works on a partial trace — a run killed
between dumps still reduces, because every file is either atomic or
append-only and flushed at each dump.

It answers, in order: where the wall went (worker utilisation and the
main thread's exclusive split), who woke whom, what the push and pop
funnels look like, which rows fire for nothing or on an input they have
already decoded, how the place ladder spends itself, and what the
frontier and the inverted index cost.  Every number is a count or a
measured second; nothing here interprets.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SECTION = "\n\n"


def _load_summary(out: Path) -> dict[str, Any]:
    path = out / "summary.json"
    if not path.is_file():
        raise SystemExit(f"no summary.json under {out}")
    return json.loads(path.read_text())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # a torn last line from a kill between flushes
            break
    return rows


def _table(header: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    if not rows:
        return "_(none)_"
    widths = [len(name) for name in header]
    text = [[f"{cell}" for cell in row] for row in rows]
    for row in text:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    out = ["| " + " | ".join(name.ljust(widths[index])
                             for index, name in enumerate(header)) + " |",
           "|" + "|".join("-" * (width + 2) for width in widths) + "|"]
    for row in text:
        out.append("| " + " | ".join(cell.ljust(widths[index])
                                     for index, cell in enumerate(row))
                   + " |")
    return "\n".join(out)


def _pct(part: float, whole: float) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "-"


def _headline(summary: dict[str, Any]) -> str:
    wall = float(summary["wall_s"])
    workers = int(summary["workers"])
    cpu = float(summary["job_cpu_s"])
    main = summary["main_thread_s"]
    busy = float(summary["main_thread_busy_s"])
    heap = summary["heap"]
    # The intake (raster decode of the TIFFs) precedes every worker, so
    # utilisation and the busy share are over the wall AFTER it.
    intake = float(main.get("intake", 0.0))
    wall_work = max(wall - intake, 1e-9)
    lines = [
        "## Headline",
        "",
        _table(("what", "value"), [
            ("wall_s", f"{wall:.1f}"),
            ("intake_s (before any worker)", f"{intake:.1f}"),
            ("workers", workers),
            ("job cpu_s", f"{cpu:.1f}"),
            ("worker utilisation (post-intake wall)",
             _pct(cpu, wall_work * workers)),
            ("main thread busy_s", f"{busy:.1f}"),
            ("main thread busy share of post-intake wall",
             _pct(busy, wall_work)),
            ("main thread blocked in wait_s",
             f"{float(main.get('wait', 0.0)):.1f}"),
            ("fires", summary["fires"]),
            ("wakes", summary["wakes"]),
            ("wakes/s", summary.get("wakes_per_s")),
            ("wakes per fire",
             f"{summary['wakes'] / summary['fires']:.1f}"
             if summary["fires"] else "-"),
            ("bookmarks", summary["bookmarks"]),
            ("frontier_len at dump", heap["frontier_len"]),
            ("max frontier_len", heap["max_frontier_len"]),
            ("index keys", heap["index_keys"]),
            ("index subscriptions", heap["subscriptions"]),
            ("peak rss_mb", heap["rss_mb"]),
            ("digest calls", summary["digest"]["calls"]),
            ("digest cpu_s", summary["digest"]["cpu_s"]),
            ("dumps", summary["dumps"]),
        ])]
    runtime = summary.get("runtime")
    if runtime:
        lines += ["", _table(
            ("interpreter", "value"),
            [(name, runtime[name]) for name in sorted(runtime)])]
    return "\n".join(lines)


def _main_thread(summary: dict[str, Any]) -> str:
    wall = float(summary["wall_s"])
    main = summary["main_thread_s"]
    rows = [(name, f"{value:.3f}", _pct(value, wall))
            for name, value in sorted(main.items(),
                                      key=lambda item: -item[1])]
    rows.append(("TOTAL", f"{sum(main.values()):.3f}",
                 _pct(sum(main.values()), wall)))
    return ("## Main thread, exclusive categories\n\n"
            "Nested regions charge their own bucket, so these sum to the "
            "traced wall.\n\n"
            + _table(("category", "seconds", "share of wall"), rows))


def _callbacks(summary: dict[str, Any]) -> str:
    rows = []
    for plugin, kinds in summary["callbacks"].items():
        for kind, cell in kinds.items():
            calls = int(cell["calls"])
            cpu = float(cell["cpu_s"])
            rows.append((plugin, kind, calls, f"{cpu:.3f}",
                         f"{1e6 * cpu / calls:.1f}" if calls else "-"))
    rows.sort(key=lambda row: -float(row[3]))
    return ("## Descriptor callbacks on the main thread (INCLUSIVE)\n\n"
            "These overlap the exclusive categories above on purpose: a "
            "`stage` call inside `_push_worker` is both.\n\n"
            + _table(("plugin", "callback", "calls", "seconds", "us/call"),
                     rows))


def _fires_by_plugin(summary: dict[str, Any]) -> str:
    by = summary["by_plugin"]
    rows = []
    for plugin, fires in sorted(by["fires"].items(),
                                key=lambda item: -by["fire_cpu_s"].get(
                                    item[0], 0.0)):
        cpu = float(by["fire_cpu_s"].get(plugin, 0.0))
        zero = int(by["zero_yield_fires"].get(plugin, 0))
        zero_cpu = float(by["zero_yield_cpu_s"].get(plugin, 0.0))
        redundant = int(by["redundant_fires"].get(plugin, 0))
        redundant_cpu = float(by["redundant_cpu_s"].get(plugin, 0.0))
        facts = int(by.get("facts", {}).get(plugin, 0))
        refused = int(by.get("facts_refused", {}).get(plugin, 0))
        rows.append((plugin, fires, f"{cpu:.1f}",
                     f"{1000.0 * cpu / fires:.0f}" if fires else "-",
                     f"{zero} ({_pct(zero, fires)})", f"{zero_cpu:.1f}",
                     f"{redundant} ({_pct(redundant, fires)})",
                     f"{redundant_cpu:.1f}", facts,
                     f"{refused} ({_pct(refused, facts)})"))
    out = ["## Fires by plugin\n\n"
           "`redundant` = the fire's decode input digested equal to one "
           "this same subject already fired on; rows with no digest hook "
           "report 0 and must be read with the schema note.  `refused` = "
           "facts the folds discarded on a value compare.\n\n"
           + _table(("plugin", "fires", "cpu_s", "ms/fire",
                     "zero-yield", "zero-yield cpu_s",
                     "redundant", "redundant cpu_s", "facts",
                     "facts refused"), rows)]
    reasons = summary.get("reasons", {})
    if reasons:
        reason_rows = [(plugin, reason, count)
                       for plugin, row in sorted(reasons.items())
                       for reason, count in sorted(row.items(),
                                                   key=lambda i: -i[1])]
        out.append("### What the jobs' own facts said\n\n"
                   "Attempt outcomes, place outcomes and the refinement "
                   "rows' adopt/refuse reason -- which the folds swallow "
                   "and no event carries.\n\n"
                   + _table(("plugin", "reason", "fires"), reason_rows))
    return SECTION.join(out)


def _funnels(summary: dict[str, Any]) -> str:
    out = []
    for name, key in (("Push funnel (`_push_worker` exits)", "pushes"),
                      ("Pop funnel (`_fill` exits)", "pops")):
        kinds: list[str] = []
        for row in summary[key].values():
            for kind in row:
                if kind not in kinds:
                    kinds.append(kind)
        kinds.sort()
        rows = []
        for plugin, row in sorted(summary[key].items()):
            total = sum(row.values())
            rows.append((plugin, total, *[row.get(kind, 0)
                                          for kind in kinds]))
        totals = ["TOTAL", sum(int(row[1]) for row in rows)]
        totals += [sum(int(row[2 + index]) for row in rows)
                   for index in range(len(kinds))]
        rows.append(tuple(totals))
        out.append(f"## {name}\n\n"
                   + _table(("plugin", "total", *kinds), rows))
    return SECTION.join(out)


def _fan_out(summary: dict[str, Any], top: int) -> str:
    cells = [(kind, plugin, count)
             for kind, row in summary["fan_out"].items()
             for plugin, count in row.items()]
    cells.sort(key=lambda cell: -cell[2])
    total = sum(cell[2] for cell in cells)
    rows = [(kind, plugin, count, _pct(count, total))
            for kind, plugin, count in cells[:top]]
    by_kind = defaultdict(int)
    by_plugin = defaultdict(int)
    for kind, plugin, count in cells:
        by_kind[kind] += count
        by_plugin[plugin] += count
    return SECTION.join([
        f"## Wake fan-out, top {top} cells of (key kind) x (woken plugin)"
        f"\n\n" + _table(("key kind", "plugin", "wakes", "share"), rows),
        "### Wakes by key kind\n\n" + _table(
            ("key kind", "wakes", "share"),
            [(kind, count, _pct(count, total))
             for kind, count in sorted(by_kind.items(),
                                       key=lambda item: -item[1])]),
        "### Wakes by woken plugin\n\n" + _table(
            ("plugin", "wakes", "share"),
            [(plugin, count, _pct(count, total))
             for plugin, count in sorted(by_plugin.items(),
                                         key=lambda item: -item[1])]),
    ])


def _census(summary: dict[str, Any]) -> str:
    rows = []
    for plugin, row in summary["census"].items():
        rows.append((plugin, row["bookmarks"], row["fired"],
                     row["never_fired"], row["retired"], row["births"],
                     row["rebirths"], row["wakes"], row["fires"],
                     row["max_seats_one_bookmark"],
                     f"{row['seat_to_first_fire_s']['mean']:.3f}",
                     f"{row['seat_to_first_fire_s']['max']:.1f}"))
    rows.sort(key=lambda row: -int(row[7]))
    out = ["## Bookmark census\n\n" + _table(
        ("plugin", "bookmarks", "fired", "never fired", "retired",
         "births", "re-births", "wakes", "fires", "max seats/bookmark",
         "seat->1st fire mean_s", "max_s"), rows)]
    hist_rows = []
    for plugin, row in summary["census"].items():
        hist_rows.append((plugin, json.dumps(row["fires_hist"]),
                          json.dumps(row["wakes_per_fire_hist"])))
    out.append("### Fires per subject, and wakes per fire\n\n" + _table(
        ("plugin", "fires-per-subject histogram",
         "wakes-per-fire histogram"), hist_rows))
    return SECTION.join(out)


def _subscribers(summary: dict[str, Any]) -> str:
    rows = [(kind, cell["keys"], cell["subscriptions"], cell["max"],
             cell["mean"], cell["p99"])
            for kind, cell in sorted(
                summary["subscribers"]["by_key_kind"].items(),
                key=lambda item: -item[1]["subscriptions"])]
    return ("## Inverted index, by key kind\n\n"
            + _table(("key kind", "keys", "subscriptions",
                      "max subscribers", "mean", "p99"), rows))


def _place_ladder(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "## Place ladder\n\n_(no place rows in this trace)_"
    seats: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fires: dict[str, list[dict[str, Any]]] = defaultdict(list)
    retires: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["kind"] == "seat":
            seats[row["window"]].append(row)
        elif row["kind"] == "fire":
            fires[row["window"]].append(row)
        else:
            retires[row["window"]] = row
    windows = set(seats) | set(fires) | set(retires)
    seat_hist: dict[int, int] = defaultdict(int)
    fire_hist: dict[int, int] = defaultdict(int)
    stage_hist: dict[int, int] = defaultdict(int)
    for window in windows:
        seat_hist[len(seats.get(window, ()))] += 1
        fire_hist[len(fires.get(window, ()))] += 1
        stage_hist[len({row["stage"] for row in seats.get(window, ())})] += 1
    cause_rows: dict[str, list[float]] = defaultdict(list)
    for row in retires.values():
        cause_rows[row["cause"]].append(float(row["wall_s"]))
    worst = sorted(
        windows,
        key=lambda window: -sum(float(row["cpu_s"])
                                for row in fires.get(window, ())))[:20]
    worst_rows = []
    for window in worst:
        rows_for = fires.get(window, ())
        cpu = sum(float(row["cpu_s"]) for row in rows_for)
        poses = sum(int(row["n_poses"]) for row in rows_for)
        worst_rows.append((window[:78], len(seats.get(window, ())),
                           len(rows_for), f"{cpu:.1f}", poses,
                           (retires.get(window) or {}).get("cause", "-")))
    return SECTION.join([
        "## Place ladder\n\n" + _table(
            ("what", "value"),
            [("windows seen", len(windows)),
             ("seat records", sum(len(v) for v in seats.values())),
             ("fire records", sum(len(v) for v in fires.values())),
             ("retire records", len(retires))]),
        "### Seats per window / fires per window / distinct stages seated"
        "\n\n" + _table(
            ("count", "windows with that many seats",
             "windows with that many fires",
             "windows with that many distinct stages"),
            [(n, seat_hist.get(n, 0), fire_hist.get(n, 0),
              stage_hist.get(n, 0))
             for n in sorted(set(seat_hist) | set(fire_hist)
                             | set(stage_hist))]),
        "### Retire causes and when\n\n" + _table(
            ("cause", "windows", "first wall_s", "median wall_s",
             "last wall_s"),
            [(cause, len(walls), f"{min(walls):.1f}",
              f"{sorted(walls)[len(walls) // 2]:.1f}", f"{max(walls):.1f}")
             for cause, walls in sorted(cause_rows.items(),
                                        key=lambda item: -len(item[1]))]),
        "### The twenty costliest windows\n\n" + _table(
            ("window", "seats", "fires", "cpu_s", "poses", "retire"),
            worst_rows),
    ])


def _fire_cadence(fires: list[dict[str, Any]], top: int) -> str:
    if not fires:
        return "## Fire cadence\n\n_(no fires.jsonl)_"
    by_plugin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fires:
        by_plugin[row["plugin"]].append(row)
    rows = []
    for plugin, group in sorted(by_plugin.items(),
                                key=lambda item: -sum(
                                    float(row["cpu_s"])
                                    for row in item[1])):
        subjects = {row["subject"] for row in group}
        cpu = sum(float(row["cpu_s"]) for row in group)
        wall = sum(float(row["wall_s"]) for row in group)
        wakes = sum(int(row["wakes_since_last_fire"]) for row in group)
        rows.append((
            plugin, len(group), len(subjects),
            f"{len(group) / len(subjects):.2f}", f"{cpu:.1f}",
            f"{1000.0 * cpu / len(group):.0f}",
            f"{wall / cpu:.2f}" if cpu else "-",
            f"{wakes / len(group):.1f}",
            f"{min(float(row['wall_started_s']) for row in group):.0f}",
            f"{max(float(row['wall_ended_s']) for row in group):.0f}"))
    out = ["## Fire cadence by plugin\n\n"
           "`wall/cpu` above 1 means the job's own thread stalled (cpu_s "
           "is thread_time).\n\n"
           + _table(("plugin", "fires", "subjects", "fires/subject",
                     "cpu_s", "ms/fire", "wall/cpu",
                     "wakes since last fire", "first fire wall_s",
                     "last fire wall_s"), rows)]
    counts: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in fires:
        counts[(row["plugin"], row["subject"])].append(float(row["cpu_s"]))
    ranked = sorted(counts.items(),
                    key=lambda item: (-len(item[1]), -sum(item[1])))[:top]
    out.append(f"### The {top} most-fired subjects\n\n" + _table(
        ("plugin", "subject", "fires", "cpu_s"),
        [(plugin, subject[:78], len(values), f"{sum(values):.1f}")
         for (plugin, subject), values in ranked]))
    return SECTION.join(out)


def _shared_inputs(fires: list[dict[str, Any]], top: int) -> str:
    """Where the SAME evidence was decoded twice, across rows.

    `input_digest_bare` is the assembled cut without the stage, so a
    `tiles.retry` at 150 iterations and the `tiles.scan` at 60 that
    armed it carry the same bare digest when the cut did not move
    between them.  That pair is the direct measure of TILE-5's claim
    and no per-subject counter can see it.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fires:
        bare = row.get("input_digest_bare")
        if bare:
            groups[bare].append(row)
    repeats = {bare: rows for bare, rows in groups.items()
               if len(rows) > 1}
    if not groups:
        return ("## Evidence decoded more than once\n\n"
                "_(no bare input digests in this trace)_")
    pairs: dict[tuple[str, str], list[float]] = defaultdict(list)
    for rows in repeats.values():
        ordered = sorted(rows, key=lambda row: row["fire"])
        for earlier, later in zip(ordered, ordered[1:]):
            pairs[(f"{earlier['plugin']}/{earlier['stage']}",
                   f"{later['plugin']}/{later['stage']}")].append(
                       float(later["cpu_s"]))
    rows_out = [(f"{first} -> {second}", len(values),
                 f"{sum(values):.1f}")
                for (first, second), values in sorted(
                    pairs.items(), key=lambda item: -sum(item[1]))[:top]]
    return SECTION.join([
        "## Evidence decoded more than once\n\n"
        "Keyed on `input_digest_bare` (the assembled cut alone, no "
        "stage), so a repeat here is the SAME evidence reaching a "
        "decoder twice, whichever row ran it.\n\n"
        + _table(("what", "value"), [
            ("fires carrying a bare digest",
             sum(len(rows) for rows in groups.values())),
            ("distinct inputs", len(groups)),
            ("inputs decoded more than once", len(repeats)),
            ("fires that were a repeat of an earlier one",
             sum(len(rows) - 1 for rows in repeats.values())),
            ("cpu_s in those repeat fires",
             f"{sum(float(row['cpu_s']) for rows in repeats.values() for row in sorted(rows, key=lambda r: r['fire'])[1:]):.1f}")]),
        "### The transitions\n\n" + _table(
            ("earlier -> later", "occurrences", "later cpu_s"), rows_out)])


def _colour_fires(fires: list[dict[str, Any]]) -> str:
    """The colour lane's fires split assembly from re-fit, per lane.

    Only a re-fit re-derives the head, and only a re-fit therefore
    re-emits every ColorEvidenceRow of its lane; an assembly fire
    applies the STANDING head to windows that had none.  The two are
    priced apart (15 + 2*rung against 160 * head fits + 2*rung), so the
    stage column separates them exactly and the cost column shows the
    re-fit ordinal climbing.
    """
    rows = [row for row in fires if row["plugin"] == "color"]
    if not rows:
        return "## Colour lane fires\n\n_(no colour lane in this run)_"
    lanes: dict[str, dict[str, Any]] = {}
    for row in rows:
        cell = lanes.setdefault(row["subject"], {
            "assembly": 0, "refit": 0, "assembly_cpu_s": 0.0,
            "refit_cpu_s": 0.0, "costs": [], "first_s": None,
            "last_s": None})
        refit = row["stage"] == "color_refit"
        cell["refit" if refit else "assembly"] += 1
        cell["refit_cpu_s" if refit else "assembly_cpu_s"] += \
            float(row["cpu_s"])
        if refit:
            cell["costs"].append(int(row["cost"]))
        if cell["first_s"] is None:
            cell["first_s"] = float(row["wall_started_s"])
        cell["last_s"] = float(row["wall_ended_s"])
    table = []
    for subject, cell in sorted(lanes.items()):
        costs = cell["costs"]
        table.append((
            subject, cell["assembly"], cell["refit"],
            f"{cell['assembly_cpu_s']:.1f}", f"{cell['refit_cpu_s']:.1f}",
            (f"{min(costs)}..{max(costs)}" if costs else "-"),
            f"{cell['first_s']:.1f}", f"{cell['last_s']:.1f}"))
    total_refits = sum(cell["refit"] for cell in lanes.values())
    return "\n".join([
        "## Colour lane fires (assembly vs re-fit)",
        "",
        f"{len(rows)} colour fires over {len(lanes)} lane(s); "
        f"{total_refits} re-fits, and each re-fit re-emits every "
        "ColorEvidenceRow of its lane.",
        "",
        _table(("lane", "assembly", "refit", "assembly cpu_s",
                "refit cpu_s", "refit cost range", "first_s", "last_s"),
               table)])


def _timeline(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "## Timeline\n\n_(no timeline.jsonl)_"
    last = float(rows[-1]["wall_s"]) or 1.0
    buckets: dict[int, dict[str, Any]] = {}
    for row in rows:
        bucket = min(19, int(20.0 * float(row["wall_s"]) / last))
        buckets[bucket] = row
    table = []
    previous: dict[str, Any] | None = None
    for bucket in sorted(buckets):
        row = buckets[bucket]
        wall = float(row["wall_s"])
        busy = float(row["main_thread_busy_s"])
        if previous is None:
            wakes_rate = row["wakes"] / wall if wall else 0.0
            busy_share = _pct(busy, wall)
        else:
            span = wall - float(previous["wall_s"])
            wakes_rate = ((row["wakes"] - previous["wakes"]) / span
                          if span else 0.0)
            busy_share = _pct(
                busy - float(previous["main_thread_busy_s"]), span)
        table.append((f"{5 * (bucket + 1)}%", f"{wall:.0f}",
                      row["inflight"], row["frontier_len"],
                      row["certificates"], row["fires"],
                      f"{wakes_rate:.0f}", busy_share, row["rss_mb"]))
        previous = row
    return ("## Timeline by 5% of wall\n\n"
            + _table(("at", "wall_s", "inflight", "frontier", "certs",
                      "fires", "wakes/s", "main-thread busy %",
                      "peak rss_mb"),
                     table))


def reduce_dir(run_dir: Path, top: int = 20) -> str:
    out = run_dir if run_dir.name == "sched-trace" else \
        run_dir / "sched-trace"
    summary = _load_summary(out)
    fires = _load_jsonl(out / "fires.jsonl")
    timeline = _load_jsonl(out / "timeline.jsonl")
    ladder = _load_jsonl(out / "place-ladder.jsonl")
    parts = [
        f"# sched-trace report — {out}",
        "Schema {schema}, {dumps} dump(s).  Measurement only: nothing in "
        "this trace was read by a scheduling decision.".format(
            schema=summary["schema"], dumps=summary["dumps"]),
        _headline(summary),
        _main_thread(summary),
        _callbacks(summary),
        _fires_by_plugin(summary),
        _fire_cadence(fires, top),
        _shared_inputs(fires, top),
        _colour_fires(fires),
        _funnels(summary),
        _fan_out(summary, top),
        _census(summary),
        _subscribers(summary),
        _place_ladder(ladder),
        _timeline(timeline),
        "## Schema notes\n\n" + "\n".join(
            f"* {note}" for note in summary["notes"]),
    ]
    return SECTION.join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sched_trace.report")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)
    text = reduce_dir(args.run_dir, args.top)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} chars)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

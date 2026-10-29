"""What the evidence loss ACTUALLY did over a traced run.

Reads one run dir's ``sched-trace/folds.jsonl`` (the per-fold record of
``ColorEvidenceRow`` and ``WindowEvidence``, written by
``holo.receiver.sched_trace_folds``) beside ``fires.jsonl``,
``timeline.jsonl`` and ``summary.json``, and answers the questions the
last-write-wins fold has never been asked:

* per lane, the sequence of head fits (``color_refit`` fires, priced at
  160 x fits) against the cheap assembly fires, and what each of them
  did to the rows it re-emitted;
* per row, across the run: how often the loss improved, worsened or
  stood; the magnitudes; how many rows EVER got worse; and the
  sign-change count, which is jitter measured rather than asserted;
* the values statistics CONDITIONAL on the loss direction — a row whose
  loss rose while its values barely moved is a different animal from
  one that rose because the head really changed;
* how many key emissions came from a row whose loss did not improve,
  and, through the fold record's own subscriber count, how many
  downstream worker wakes those emissions bought.

STDLIB + NUMPY.  Reads a run dir; writes markdown to stdout or --out.
Nothing here is ever read by a decode.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

SECTION = "\n\n"
#: `color_refit` is the only colour stage that re-derives the head.
REFIT_STAGE = "color_refit"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # a killed run can leave one torn trailing line
            break
    return rows


def _table(header: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    if not rows:
        return "_(none)_"
    text = [[f"{cell}" for cell in row] for row in rows]
    widths = [len(name) for name in header]
    for row in text:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    out = ["| " + " | ".join(name.ljust(widths[i])
                             for i, name in enumerate(header)) + " |",
           "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    for row in text:
        out.append("| " + " | ".join(cell.ljust(widths[i])
                                     for i, cell in enumerate(row)) + " |")
    return "\n".join(out)


def _pct(part: float, whole: float) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "-"


def _q(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, np.float64), q)) \
        if values else float("nan")


# ------------------------------------------------------------- lanes


def _lane_of(record: dict[str, Any]) -> str:
    """A colour row's lane: (capture, level, page), ordinal dropped."""
    key = record["key"]
    return f"({key[0][:8]}…, {key[1]}, {key[2]})"


def _fire_lanes(fires: list[dict[str, Any]]) -> str:
    rows = [row for row in fires if row["plugin"] == "color"]
    if not rows:
        return "## Colour fires\n\n_(no colour lane)_"
    lanes: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"assembly": 0, "refit": 0, "refit_at": [],
                 "assembly_cpu_s": 0.0, "refit_cpu_s": 0.0})
    for row in rows:
        cell = lanes[row["subject"]]
        if row["stage"] == REFIT_STAGE:
            cell["refit"] += 1
            cell["refit_at"].append(round(float(row["wall_ended_s"]), 1))
            cell["refit_cpu_s"] += float(row["cpu_s"])
        else:
            cell["assembly"] += 1
            cell["assembly_cpu_s"] += float(row["cpu_s"])
    table = [(subject, cell["assembly"], cell["refit"],
              f"{cell['assembly_cpu_s']:.1f}", f"{cell['refit_cpu_s']:.1f}",
              ", ".join(str(at) for at in cell["refit_at"]) or "-")
             for subject, cell in sorted(lanes.items())]
    last = max(float(row["wall_ended_s"]) for row in rows)
    return "\n".join([
        "## Colour fires by cost band",
        "",
        f"{len(rows)} colour fires; the lane's LAST fire ended at "
        f"{last:.1f} s.  Only a `{REFIT_STAGE}` re-derives the head; an "
        "assembly fire applies the standing head to windows that had "
        "none.  Both re-emit ColorEvidenceRows.",
        "",
        _table(("lane", "assembly", "refit", "assembly cpu_s",
                "refit cpu_s", "refit ended at (s)"), table)])


# ------------------------------------------------------- the folds


def _fold_overview(folds: list[dict[str, Any]]) -> str:
    if not folds:
        return ("## Fold records\n\n_(no folds.jsonl — the run predates "
                "the fold trace, or HOLO3_SCHED_TRACE was off)_")
    table = []
    for kind in sorted({row["kind"] for row in folds}):
        rows = [row for row in folds if row["kind"] == kind]
        changed = [row for row in rows if row["changed"]]
        directions: dict[str, int] = defaultdict(int)
        for row in rows:
            directions[row["loss_direction"]] += 1
        table.append((
            kind, len(rows), len(changed),
            _pct(len(changed), len(rows)),
            directions.get("first", 0), directions.get("improved", 0),
            directions.get("worsened", 0), directions.get("equal", 0),
            directions.get("unknown", 0)))
    reasons: dict[str, int] = defaultdict(int)
    for row in folds:
        if not row["changed"]:
            reasons[row["reason"]] += 1
    reason_rows = [(reason, count)
                   for reason, count in sorted(reasons.items())]
    return "\n".join([
        "## Fold records",
        "",
        "One row per fold of an evidence cell.  `first` is a row with no "
        "standing predecessor; the other three compare the new loss with "
        "the standing one.",
        "",
        _table(("kind", "folds", "adopted", "adopt %", "first",
                "improved", "worsened", "equal", "unknown"), table),
        "",
        "Refusal reasons:",
        "",
        _table(("reason", "folds"), reason_rows)])


def _repeat_folds(folds: list[dict[str, Any]]) -> str:
    """Only a REPEAT fold can tell us anything: the first is free."""
    repeats = [row for row in folds if row["loss_direction"] != "first"]
    if not repeats:
        return "## Re-emission\n\n_(every fold was a first row)_"
    table = []
    for kind in sorted({row["kind"] for row in repeats}):
        rows = [row for row in repeats if row["kind"] == kind]
        improved = [row for row in rows
                    if row["loss_direction"] == "improved"]
        worsened = [row for row in rows
                    if row["loss_direction"] == "worsened"]
        equal = [row for row in rows if row["loss_direction"] == "equal"]
        up = [abs(row["loss_delta"]) for row in worsened
              if row["loss_delta"] is not None]
        down = [abs(row["loss_delta"]) for row in improved
                if row["loss_delta"] is not None]
        table.append((
            kind, len(rows),
            f"{len(improved)} ({_pct(len(improved), len(rows))})",
            f"{len(worsened)} ({_pct(len(worsened), len(rows))})",
            f"{len(equal)} ({_pct(len(equal), len(rows))})",
            f"{_q(down, 0.5):.5f}", f"{_q(down, 0.9):.5f}",
            f"{_q(up, 0.5):.5f}", f"{_q(up, 0.9):.5f}"))
    return "\n".join([
        "## Re-emissions (folds that met a standing row)",
        "",
        _table(("kind", "repeat folds", "improved", "worsened", "equal",
                "median abs Δ down", "p90 abs Δ down",
                "median abs Δ up", "p90 abs Δ up"), table)])


def _monotonicity(folds: list[dict[str, Any]]) -> str:
    """Per row, over the whole run: did it only ever get better?"""
    series: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in folds:
        series[(row["kind"], tuple(map(str, row["key"])))].append(row)
    table = []
    detail = []
    for kind in sorted({key[0] for key in series}):
        rows = {key: value for key, value in series.items()
                if key[0] == kind}
        multi = {key: value for key, value in rows.items()
                 if sum(1 for one in value
                        if one["loss_direction"] != "first") > 0}
        if not multi:
            continue
        ever_worse = 0
        sign_changes: list[int] = []
        jittered = 0
        net: list[float] = []
        for value in multi.values():
            directions = [one["loss_direction"] for one in value
                          if one["loss_direction"] in
                          ("improved", "worsened")]
            if "worsened" in directions:
                ever_worse += 1
            changes = sum(1 for a, b in zip(directions, directions[1:])
                          if a != b)
            sign_changes.append(changes)
            if changes:
                jittered += 1
            losses = [one["new_loss"] for one in value
                      if one["new_loss"] is not None]
            if len(losses) >= 2:
                net.append(losses[-1] - losses[0])
        table.append((
            kind, len(rows), len(multi),
            f"{ever_worse} ({_pct(ever_worse, len(multi))})",
            f"{jittered} ({_pct(jittered, len(multi))})",
            max(sign_changes) if sign_changes else 0,
            f"{_q(net, 0.5):+.5f}",
            f"{sum(1 for one in net if one < 0)} / {len(net)}"))
        worst = sorted(multi.items(),
                       key=lambda item: -sum(
                           1 for a, b in zip(
                               [one["loss_direction"] for one in item[1]],
                               [one["loss_direction"]
                                for one in item[1]][1:]) if a != b))[:5]
        for key, value in worst:
            losses = [one["new_loss"] for one in value]
            detail.append((kind, key[1][:48],
                           len(value),
                           " → ".join(f"{one:.4f}" if one is not None
                                      else "-" for one in losses[:8])))
    return "\n".join([
        "## Monotonicity and jitter, per row over the whole run",
        "",
        "`ever worse` counts rows whose loss rose at least once; "
        "`jittered` counts rows whose direction CHANGED SIGN at least "
        "once (a row that only ever fell, or only ever rose, is not "
        "jitter).  `net` is last loss minus first.",
        "",
        _table(("kind", "rows", "re-emitted rows", "ever worse",
                "jittered", "max sign changes", "median net Δ",
                "net improved / rows"), table),
        "",
        "The most jittered rows, first eight losses:",
        "",
        _table(("kind", "key", "folds", "loss sequence"), detail)])


def _values_vs_loss(folds: list[dict[str, Any]]) -> str:
    """Did the DECODER INPUT move when the loss did?"""
    table = []
    for kind in sorted({row["kind"] for row in folds}):
        for direction in ("improved", "worsened", "equal"):
            rows = [row for row in folds
                    if row["kind"] == kind
                    and row["loss_direction"] == direction
                    and row["values_changed_fraction"] is not None]
            if not rows:
                continue
            fractions = [row["values_changed_fraction"] for row in rows]
            maxima = [row["values_max_abs_delta"] for row in rows
                      if row["values_max_abs_delta"] is not None]
            means = [row["values_mean_abs_delta"] for row in rows
                     if row["values_mean_abs_delta"] is not None]
            cells = sum(1 for row in rows if row["cells_changed"])
            still = sum(1 for row in rows
                        if row["values_changed_fraction"] == 0.0)
            table.append((
                kind, direction, len(rows),
                f"{_q(fractions, 0.5):.4f}", f"{_q(fractions, 0.9):.4f}",
                f"{_q(maxima, 0.5):.4f}", f"{_q(means, 0.5):.5f}",
                f"{cells} ({_pct(cells, len(rows))})",
                f"{still} ({_pct(still, len(rows))})"))
    return "\n".join([
        "## What the values did, conditional on the loss direction",
        "",
        "`cells moved` = the row's cell SET changed (no adoption rule "
        "may refuse those); `values still` = not one cell's LLR "
        "differed, so the fold adopted on the loss alone.",
        "",
        _table(("kind", "loss", "folds", "median frac changed",
                "p90 frac changed", "median max abs Δ", "median mean abs Δ",
                "cells moved", "values still"), table)])


def _wake_consequence(folds: list[dict[str, Any]],
                      summary: dict[str, Any]) -> str:
    """How much of the wake traffic came from a row that got no better?"""
    adopted = [row for row in folds if row["changed"]]
    if not adopted:
        return "## Wake consequence\n\n_(nothing adopted)_"
    table = []
    for kind in sorted({row["kind"] for row in adopted}):
        rows = [row for row in adopted if row["kind"] == kind]
        emissions = sum(len(row["keys"]) for row in rows)
        subscribers = sum(row["n_subscribers"] or 0 for row in rows)
        not_better = [row for row in rows
                      if row["loss_direction"] in ("worsened", "equal")]
        nb_keys = sum(len(row["keys"]) for row in not_better)
        nb_subs = sum(row["n_subscribers"] or 0 for row in not_better)
        table.append((
            kind, len(rows), emissions, subscribers,
            f"{len(not_better)} ({_pct(len(not_better), len(rows))})",
            nb_keys, f"{nb_subs} ({_pct(nb_subs, subscribers)})"))
    fan = summary.get("fan_out", {})
    rowkeys = {"color_row": "color_row", "evidence": "evidence_read"}
    lines = []
    for kind, key in rowkeys.items():
        row = fan.get(key)
        if row:
            total = sum(row.values())
            top = ", ".join(f"{plugin} {count}" for plugin, count
                            in sorted(row.items(), key=lambda x: -x[1])[:6])
            lines.append(f"* `{key}` woke {total} worker(s): {top}")
    return "\n".join([
        "## Wake consequence",
        "",
        "`not better` = the adopted row's loss was worse than or equal "
        "to the standing one.  Those adoptions are the ones an "
        "improvement-only rule would have refused, and the subscriber "
        "column is the wake traffic they bought.",
        "",
        _table(("kind", "adoptions", "key emissions", "subscribers woken",
                "not better", "their emissions", "their subscribers"),
               table),
        "",
        *lines])


def _ownership(folds: list[dict[str, Any]]) -> str:
    """Only a CONTESTED tile can change its cut when a loss moves.

    `lib/owners.freeze_page_owners` gives each contested payload cell to
    the first writer in `(loss, extent, region, plane)` order, so a tile
    covered by ONE row of a lane reads the same however that row's loss
    moves.  The cover column of each fold record names the tile keys the
    row covers, so the contested set is exact.
    """
    table = []
    for kind in ("color_row", "evidence"):
        rows = [row for row in folds if row["kind"] == kind]
        if not rows:
            continue
        # last cover wins: the record is written in fold order
        cover: dict[tuple, tuple] = {}
        for row in rows:
            cover[tuple(map(str, row["key"]))] = tuple(
                tuple(one) for one in row["cover"])
        writers: dict[tuple, set[tuple]] = defaultdict(set)
        for key, tiles in cover.items():
            for tile in tiles:
                writers[tile].add(key)
        if not writers:
            continue
        contested = {tile: who for tile, who in writers.items()
                     if len(who) >= 2}
        # a lane is the tile key's (capture, level) tail
        per_lane: dict[str, list[int]] = defaultdict(list)
        for tile, who in writers.items():
            per_lane[str(tuple(tile[3:]))].append(len(who))
        moved = sum(1 for row in rows
                    if row["changed"]
                    and row["loss_direction"] in ("improved", "worsened")
                    and any(tuple(one) in contested
                            for one in row["cover"]))
        table.append((
            kind, len(cover), len(writers),
            f"{len(contested)} ({_pct(len(contested), len(writers))})",
            f"{max((len(who) for who in writers.values()), default=0)}",
            moved, len(per_lane)))
    return "\n".join([
        "## Ownership exposure",
        "",
        "`contested` = tiles covered by two or more rows of one lane — "
        "the only tiles whose CUT a loss change can alter.  `loss moves "
        "on a contested tile` counts adopted folds whose loss really "
        "moved and which touch at least one contested tile.",
        "",
        _table(("kind", "rows", "tiles covered", "contested",
                "max writers on a tile", "loss moves on a contested tile",
                "lanes"), table)])


def reduce_dir(run_dir: Path) -> str:
    out = run_dir if run_dir.name == "sched-trace" else \
        run_dir / "sched-trace"
    folds = _load_jsonl(out / "folds.jsonl")
    fires = _load_jsonl(out / "fires.jsonl")
    summary_path = out / "summary.json"
    summary = (json.loads(summary_path.read_text(encoding="utf-8"))
               if summary_path.is_file() else {})
    head = [f"# logloss report — {out}"]
    if summary:
        head.append(
            "wall {wall}s, {workers} workers, {fires} fires, "
            "{wakes} wakes.".format(
                wall=summary.get("wall_s"), workers=summary.get("workers"),
                fires=summary.get("fires"), wakes=summary.get("wakes")))
    head.append("Measurement only: no scheduling decision reads this.")
    parts = ["\n".join(head),
             _fire_lanes(fires),
             _fold_overview(folds),
             _repeat_folds(folds),
             _monotonicity(folds),
             _values_vs_loss(folds),
             _wake_consequence(folds, summary),
             _ownership(folds)]
    return SECTION.join(parts) + "\n"


# --------------------------------------------------------- the A/B


def _run_facts(run_dir: Path) -> dict[str, Any]:
    """Everything the A/B compares, from one run dir."""
    out = run_dir / "sched-trace"
    summary_path = out / "summary.json"
    summary = (json.loads(summary_path.read_text(encoding="utf-8"))
               if summary_path.is_file() else {})
    report_path = run_dir / "report.json"
    report = (json.loads(report_path.read_text(encoding="utf-8"))
              if report_path.is_file() else {})
    folds = _load_jsonl(out / "folds.jsonl")
    fires = _load_jsonl(out / "fires.jsonl")
    timeline = _load_jsonl(out / "timeline.jsonl")
    colour = [row for row in folds if row["kind"] == "color_row"]
    refused = defaultdict(int)
    for row in colour:
        if not row["changed"]:
            refused[row["reason"]] += 1
    decoder = defaultdict(int)
    decoder_cpu: dict[str, float] = defaultdict(float)
    for row in fires:
        if row["plugin"].startswith("tiles."):
            decoder[row["plugin"]] += 1
            decoder_cpu[row["plugin"]] += float(row["cpu_s"])
    planes = {name: count
              for name, count in (report.get("plane_certs") or [])}
    return {
        "run_dir": str(run_dir),
        "wall_s": summary.get("wall_s"),
        "workers": summary.get("workers"),
        "job_cpu_s": summary.get("job_cpu_s"),
        "fires": summary.get("fires"),
        "wakes": summary.get("wakes"),
        "certified": (report.get("close") or {}).get("certified"),
        "planes": planes,
        "colour_folds": len(colour),
        "colour_adopted": sum(1 for row in colour if row["changed"]),
        "colour_refused": dict(refused),
        "decoder_fires": dict(decoder),
        "decoder_cpu_s": {k: round(v, 1)
                          for k, v in decoder_cpu.items()},
        "timeline": [(float(row.get("wall_s", 0.0)),
                      int(row.get("certificates", 0) or 0))
                     for row in timeline if "certificates" in row]}


def _at_wall(timeline: list[tuple[float, int]], wall_s: float) -> int | None:
    """The certificate count at or before a matched wall clock."""
    best = None
    for at, count in timeline:
        if at <= wall_s:
            best = count
    return best


def compare_dirs(run_dirs: list[Path]) -> str:
    facts = [_run_facts(one) for one in run_dirs]
    walls = [one["wall_s"] for one in facts if one["wall_s"]]
    matched = min(walls) if walls else 0.0
    head = [(
        Path(one["run_dir"]).name, one["wall_s"], one["workers"],
        one["job_cpu_s"], one["fires"], one["certified"],
        _at_wall(one["timeline"], matched))
        for one in facts]
    planes = sorted({name for one in facts for name in one["planes"]})
    plane_rows = [tuple([Path(one["run_dir"]).name]
                        + [one["planes"].get(name, "-") for name in planes])
                  for one in facts]
    fold_rows = [(
        Path(one["run_dir"]).name, one["colour_folds"],
        one["colour_adopted"],
        one["colour_folds"] - one["colour_adopted"],
        ", ".join(f"{k}={v}" for k, v in sorted(
            one["colour_refused"].items())) or "-")
        for one in facts]
    plugins = sorted({name for one in facts for name in one["decoder_fires"]})
    decoder_rows = []
    for one in facts:
        decoder_rows.append(tuple(
            [Path(one["run_dir"]).name]
            + [f"{one['decoder_fires'].get(name, 0)} "
               f"/ {one['decoder_cpu_s'].get(name, 0.0)}s"
               for name in plugins]))
    return SECTION.join([
        "# logloss A/B — HOLO3_COLOR_ROW_ADOPT",
        "\n".join([
            "## Headline", "",
            f"Matched wall for the certificate curve: {matched:.1f} s.",
            "",
            _table(("run", "wall_s", "workers", "job cpu_s", "fires",
                    "certified at stop", "certified at matched wall"),
                   head)]),
        "\n".join([
            "## Certificates per plane", "",
            _table(tuple(["run"] + planes), plane_rows)]),
        "\n".join([
            "## Colour row folds", "",
            _table(("run", "folds", "adopted", "refused", "reasons"),
                   fold_rows)]),
        "\n".join([
            "## Tile decoder fires (fires / cpu)", "",
            _table(tuple(["run"] + plugins), decoder_rows)]),
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sched_trace.logloss_report")
    parser.add_argument("run_dir", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--compare", action="store_true",
                        help="A/B several run dirs instead of reducing one")
    args = parser.parse_args(argv)
    if args.compare or len(args.run_dir) > 1:
        text = compare_dirs(list(args.run_dir))
    else:
        text = reduce_dir(args.run_dir[0])
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} chars)", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

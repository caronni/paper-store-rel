"""When could the done gate have bitten?  A read-only walk of one
finished run's event stream.

    PYTHONPATH=src:. env/bin/python measure/donegeo_timeline.py \
        /tmp/I/holo3-I-first-run/events.jsonl

NOT A TEST and not collectable as one (`measure/` standing, alongside
`donegeo_realstate.py`, `donegeo_parity.py`, `donegeo_saturation.py`).
READ-ONLY: it opens no raster, folds no snapshot and writes nothing
outside `--out`.  `.xz` inputs are decompressed on the fly.

WHY.  `store.window_fully_done` is an AND across every stream of the
coding: a tile with C and M certified and Y open is NOT done, and a
window is only suppressible when its whole supported extent is.  So the
gate has a PRECONDITION that is invisible in a per-run total — there
must be certified tiles, in ALL streams, under the ground a window
covers, AT THE MOMENT that window is popped.  On a run that starts cold
the placement lattice is laid down before the first certificate exists,
and no sharpening of the gate could have suppressed a single one of
those jobs.

This walk prices that.  Certificates arrive as `TileOutcome`
(`result == "certified"`), placement work as `JobDone(plugin=...)`, and
both are ordered in the file, so the done-tile count AT EACH FIRE is a
prefix count — no state, no store, no re-derivation.  The report says
how much CPU each plugin spent while the all-stream done set was empty
(the gate's dead zone), and, for contrast, how many tiles were certified
in the single BEST stream over the same stretch: that difference is the
whole of what a per-stream relaxation could reach, and it is a design
ruling, not a measurement.

IT ALSO RECOVERS THE RETIREMENT CAUSE, which the v1 record does not
carry (`WorkerRetired` is emitted for all three clauses of
`place_sched.place_retire_cause` and names none of them).  A window that
leaves the frontier having never been posed and never fired a single
`place` job cannot have been retired as `placed` or as `exhausted`: the
done gate is the only clause left.  That inference needs every placement
to be visible in the file, so it is reported ONLY for runs with no
`SnapshotReplayed` — on a resume the placements arrive silently with the
snapshot and `measure/donegeo_realstate.py` is the instrument that
handles them.
"""

from __future__ import annotations

import argparse
import json
import lzma
from collections import Counter, defaultdict
from pathlib import Path
from typing import IO, Iterator

CERTIFIED = "certified"
#: `revisit` was dissolved 2026-09-21 and no live run emits it; the name
#: stays because this reader's job is ARCHIVED journals, which do.
PLACING_PLUGINS: frozenset[str] = frozenset({"place", "revisit"})
WindowKey = tuple[str, int, int, tuple[int, int, int, int]]


def window_key(event: dict) -> WindowKey:
    return (event["capture"], event["level_index"], event["region_index"],
            tuple(event["extent_cells"]))


def job_window_key(event: dict) -> WindowKey:
    subject = event["subject"]
    return (subject[0], subject[1], subject[2], tuple(subject[3]))


#: The retire event in BOTH spellings: `WorkerRetired` is generic over
#: every row and carries the subject as a JSON list (2026-09-21),
#: `WindowRetired` was place's alone and carried the window flat.  An
#: archived journal -- and the base leg of any A/B -- holds the old one.
RETIRED_TYPES = ("WorkerRetired", "WindowRetired")


def retired_window_key(event: dict) -> WindowKey:
    return (job_window_key(event) if "subject" in event
            else window_key(event))


def events(path: Path) -> Iterator[dict]:
    stream: IO[str]
    if path.suffix == ".xz":
        stream = lzma.open(path, "rt")
    else:
        stream = open(path)
    with stream:
        for line in stream:
            yield json.loads(line)


def walk(path: Path) -> dict:
    """Prefix-count the done set and bill every job against it."""
    streams: tuple[str, ...] = ()
    per_tile: defaultdict[tuple[int, int, int], set[str]] = defaultdict(set)
    per_stream: Counter = Counter()
    done_tiles = 0
    # cpu spent while the all-stream done set was still empty, and after
    cpu_dead: Counter = Counter()
    cpu_live: Counter = Counter()
    jobs_dead: Counter = Counter()
    jobs_live: Counter = Counter()
    # the looser bound: cpu spent before the FIRST certificate of any
    # stream — the ceiling on what any per-stream or per-lane relaxation
    # of the AND could ever reach, since before it nothing is done in
    # any sense at all
    cpu_before_any_cert: Counter = Counter()
    any_cert = False
    best_stream_at_first_done = 0
    first_done_index: int | None = None
    settled: Counter = Counter()
    retired = 0
    n_events = 0
    resumed = False
    posed: set[WindowKey] = set()
    left_frontier: set[WindowKey] = set()
    refused: set[WindowKey] = set()
    fired: Counter = Counter()
    place_cpu: defaultdict[WindowKey, float] = defaultdict(float)
    causes: Counter = Counter()
    cause_cpu: Counter = Counter()
    cause_jobs: Counter = Counter()
    for index, event in enumerate(events(path)):
        n_events = index + 1
        kind = event["type"]
        if kind == "RunOpen":
            streams = tuple(event["stream_ids"])
        elif kind == "SnapshotReplayed":
            resumed = True
        elif kind == "PoseCommitted":
            if event["accepted"]:
                posed.add(window_key(event))
        elif kind == "TileOutcome":
            if event["result"] != CERTIFIED:
                continue
            key = (event["page"], event["ty"], event["tx"])
            held = per_tile[key]
            if event["stream_id"] in held:
                continue
            held.add(event["stream_id"])
            per_stream[event["stream_id"]] += 1
            any_cert = True
            if len(held) == len(streams):
                done_tiles += 1
                if first_done_index is None:
                    first_done_index = index
                    best_stream_at_first_done = (
                        max(per_stream.values()) if per_stream else 0)
        elif kind == "JobDone":
            plugin = event["plugin"]
            if done_tiles:
                cpu_live[plugin] += float(event["cpu_s"])
                jobs_live[plugin] += 1
            else:
                cpu_dead[plugin] += float(event["cpu_s"])
                jobs_dead[plugin] += 1
            if not any_cert:
                cpu_before_any_cert[plugin] += float(event["cpu_s"])
            if plugin in PLACING_PLUGINS:
                # In journals written before 2026-09-21, `revisit`
                # builds the same `place_sched.ring_pass_job` and folds
                # the same PlaceOutcome, so a window it fired for can
                # reach the exhausted clause with no `place` job of its
                # own: both count as "this window was tried".
                key = job_window_key(event)
                fired[key] += 1
                place_cpu[key] += float(event["cpu_s"])
        elif kind == "WindowSettled":
            settled[event["state"]] += 1
            refused.add(window_key(event))
        elif kind in RETIRED_TYPES and event.get("plugin", "place") == "place":
            retired += 1
            key = retired_window_key(event)
            left_frontier.add(key)
            if key in posed:
                cause = "placed"
            elif fired[key]:
                cause = "exhausted"
            else:
                cause = "done_covered"
            causes[cause] += 1
            cause_jobs[cause] += fired[key]
            cause_cpu[cause] += place_cpu[key]
    total = {plugin: cpu_dead[plugin] + cpu_live[plugin]
             for plugin in set(cpu_dead) | set(cpu_live)}
    rows = []
    for plugin in sorted(total, key=lambda name: -total[name]):
        rows.append({
            "plugin": plugin,
            "cpu_s": round(total[plugin], 1),
            "cpu_s_while_nothing_done": round(cpu_dead[plugin], 1),
            "share_while_nothing_done": (
                round(cpu_dead[plugin] / total[plugin], 4)
                if total[plugin] else None),
            "cpu_s_before_first_certificate": round(
                cpu_before_any_cert[plugin], 1),
            "jobs": jobs_dead[plugin] + jobs_live[plugin],
            "jobs_while_nothing_done": jobs_dead[plugin],
        })
    never_posed = {key: value for key, value in place_cpu.items()
                   if key not in posed}
    # the diag pane's "orange": scheduled, refused at least once, never
    # posed, never retired — the residue the angle report priced
    orange = {key: value for key, value in never_posed.items()
              if key in refused and key not in left_frontier}
    return {
        "events": str(path),
        "n_events": n_events,
        "streams": list(streams),
        "tiles_done_all_streams": done_tiles,
        "tiles_certified_per_stream": dict(sorted(per_stream.items())),
        "first_all_stream_done_at_event": first_done_index,
        "best_single_stream_when_first_tile_went_done":
            best_stream_at_first_done,
        "window_settled": dict(settled),
        "window_retired": retired,
        "done_covered_settles": settled.get("done_covered", 0),
        "resumed_from_snapshot": resumed,
        "retire_cause": (
            "not reconstructible from a resume run's events — the "
            "snapshot's placements are silent; use donegeo_realstate.py"
            if resumed else {
                "counts": dict(causes),
                "placing_jobs_before_retirement": dict(cause_jobs),
                "placing_cpu_s_before_retirement": {
                    cause: round(value, 1)
                    for cause, value in cause_cpu.items()},
            }),
        "windows_that_fired_a_placing_job": len(fired),
        "windows_placed": len(posed),
        # A DIFFERENT MECHANISM, priced for the record only: the whole
        # placement bill of windows that never took a pose.  That is the
        # naive ceiling for a placement-COVERAGE gate (suppress a window
        # whose ground this capture already placed at another lane), not
        # for done-geometry, and it is an upper bound in the loosest
        # sense — a suppressed coarse-lane pose may be the seed a
        # neighbour needed.
        "windows_never_posed": len(never_posed),
        "placing_cpu_s_on_windows_never_posed": round(
            sum(never_posed.values()), 1),
        "windows_left_orange": len(orange),
        "placing_cpu_s_on_windows_left_orange": round(
            sum(orange.values()), 1),
        "plugins": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("events", type=Path, nargs="+")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = [walk(path) for path in args.events]
    text = json.dumps(report, indent=2)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n")


if __name__ == "__main__":
    main()

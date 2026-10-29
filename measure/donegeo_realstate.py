"""Did the done gate bite on paper?  A read-only census over one
archived run: its INPUT snapshot plus the events it then produced.

    PYTHONPATH=src:. env/bin/python measure/donegeo_realstate.py \
        --snapshot /tmp/I/holo3-I-resume-run/facts.npz \
        --events   /tmp/I/holo3-I-resume-2-run/events.jsonl \
        --format   L:c2-cmy8-r0700-p120-x1@3392x2368

NOT A TEST and not collectable as one (measure/ standing, alongside
`donegeo_parity.py` and `donegeo_saturation.py`).  READ-ONLY: it folds a
finished run's fact snapshot through the ordinary store merge and asks
`store.window_fully_done` about every window.  No raster is opened, no
scan is decoded, nothing is written outside `--out`.

WHY THIS INSTRUMENT EXISTS, AND WHAT CHANGED UNDER IT.  It was written
when the done gate RETIRED a window, and when the event stream did not
say why a window retired:

* `place.run_window_pass` could settle a window `done_covered` — a
  `WindowSettled` with a distinct state, and UNREACHABLE, because the
  scheduler asked the same predicate first.  That door is gone; the pass
  carries no done test at all.
* `place_sched.place_retire_cause` retired a done window `done_covered`
  beside the ordinary `placed` and `exhausted`, and the old place-only
  `WindowRetired` event carried no cause.

So the split was recovered from OUTSIDE the run: a window that the input
snapshot shows UNPLACED, that this run never fired a `place` job for,
and that this run retired, was retired by the done gate and by nothing
else.  Both premises have since moved:

* `WorkerRetired` carries the retire clause as `cause` (2026-09-21), so
  for a run that records it the census READS `done_covered` instead of
  inferring it (`run_retired_by_cause`, `retired_done_covered`); the
  inference stays for journals that carry no cause.
* Since 56928c45 (2026-10-03) a done window is NOT retired at all: the
  pose-free projection it is judged on can shrink under a pose revision,
  so `place_sched.worker_stage` SUPPRESSES it (no stage) and the store
  re-opens it on `KEY_WINDOW_DONE`.  On such a run neither the cause nor
  the inference sees the gate — a suppressed window simply never fires —
  and `gate_says_done_now` (the replay below) is the only column that
  measures it.  The script prints a one-line note saying so.

The gate columns re-derive the gate's verdict directly from the same
facts, so the record and the replay agree or the disagreement is the
finding.

The re-derivation needs the captures, which a snapshot deliberately does
not hold (the operator re-declares them every run).  They are rebuilt
from the run's own `CaptureOpen` events plus `intake.build_levels`,
which is a pure function of dpi, pitch and shape — the same call the
real intake makes.  `platen_backing` is not recoverable and not read by
the gate; it is set to 0.0 and the frames it feeds are only used here
for `support_cells` and the region lattice.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator

WindowKey = tuple[str, int, int, tuple[int, int, int, int]]


#: The seat and retire events, in BOTH spellings.  `WorkerSeated` /
#: `WorkerRetired` are generic over every row and carry the subject as
#: a JSON list (2026-09-21); `WindowScheduled` / `WindowRetired` were
#: place-only and carried the four window fields flat.  Archived
#: journals hold the old spelling and so does the base leg of any
#: base-vs-branch A/B, so a reader that matches one name silently
#: reports zero windows on half its inputs.
SEATED_TYPES = ("WorkerSeated", "WindowScheduled")
RETIRED_TYPES = ("WorkerRetired", "WindowRetired")


def _is_place(event: dict) -> bool:
    """The old events were place's alone and carry no `plugin` field."""
    return event.get("plugin", "place") == "place"


def _place_window_key(event: dict) -> WindowKey:
    """The window a seat/retire event names, in either spelling."""
    subject = event.get("subject")
    if subject is None:
        return (event["capture"], int(event["level_index"]),
                int(event["region_index"]), tuple(event["extent_cells"]))
    return (subject[0], int(subject[1]), int(subject[2]),
            tuple(subject[3]))


def events(path: Path) -> Iterator[dict]:
    with open(path) as stream:
        for line in stream:
            yield json.loads(line)


#: The place retire clause the done gate used until 56928c45
#: (2026-10-03); `place_sched` keeps the spelling as the record's.
CAUSE_DONE_COVERED = "done_covered"

NOTE_SUPPRESSED = (
    "note: runs after 2026-10-03 (56928c45) do not retire done windows -- "
    "the gate suppresses through the stage, so only gate_says_done_now "
    "measures it there")


def observed(path: Path) -> dict[str, object]:
    """What the run did, counted from its own event stream."""
    retired: set[WindowKey] = set()
    retire_cause: dict[WindowKey, str | None] = {}
    scheduled: set[WindowKey] = set()
    fired: Counter = Counter()
    settled: Counter = Counter()
    place_cpu: defaultdict = defaultdict(float)
    captures: dict[str, dict] = {}
    for event in events(path):
        kind = event["type"]
        if kind == "CaptureOpen":
            captures[event["capture"]] = event
        elif kind in RETIRED_TYPES and _is_place(event):
            window = _place_window_key(event)
            retired.add(window)
            # `WorkerRetired` carries the clause; the old spelling did not
            retire_cause[window] = event.get("cause")
        elif kind in SEATED_TYPES and _is_place(event):
            scheduled.add(_place_window_key(event))
        elif kind == "WindowSettled":
            settled[event["state"]] += 1
        elif kind == "JobDone" and event["plugin"] == "place":
            subject = event["subject"]
            key = (subject[0], subject[1], subject[2], tuple(subject[3]))
            fired[key] += 1
            place_cpu[key] += event["cpu_s"]
    return {"retired": retired, "retire_cause": retire_cause,
            "scheduled": scheduled, "fired": fired,
            "settled": settled, "place_cpu": place_cpu,
            "captures": captures}


def rebuilt_captures(opens: dict[str, dict],
                     pitch_in: object) -> tuple[object, ...]:
    from holo.receiver import data
    from holo.receiver.plugins import intake

    out = []
    for capture_id, event in sorted(opens.items()):
        shape = (int(event["shape_yx"][0]), int(event["shape_yx"][1]))
        out.append(data.Capture(
            capture_id=capture_id, path=Path(f"{capture_id}.tiff"),
            dpi=float(event["dpi"]), shape_px=shape,
            channels=int(event["channels"]), platen_backing=0.0,
            levels=intake.build_levels(float(event["dpi"]), pitch_in,
                                       shape),
            plane_dir=Path(capture_id)))
    return tuple(out)


def replay(snapshot_path: Path, format_ref: str,
           opens: dict[str, dict]) -> object:
    import tempfile

    from holo.receiver import data, engine, snapshot
    from holo.receiver.format import identity

    row = identity.resolve_format_ref(format_ref)
    request = data.DecodeRequest(
        scans=(), dpis=(), format_ref=format_ref, max_pages=1, workers=1,
        complete=True, no_close=True, diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-donegeo-realstate-")))
    instance = engine._Engine(request, [])
    for capture in rebuilt_captures(opens, row.pitch_in):
        instance._ingest(capture)
    for fact in snapshot.read(snapshot_path):
        instance._ingest(fact)
    return instance


def census(instance: object, seen: dict[str, object]) -> dict:
    placed = set(instance.placements())
    windows = set(instance.windows())
    unplaced = windows - placed
    retired = seen["retired"]
    fired = set(seen["fired"])
    gate = {wid: instance.window_fully_done(wid) for wid in unplaced}
    gated = {wid for wid, verdict in gate.items() if verdict}
    causes = seen["retire_cause"]
    # A run either records the clause on every retirement or on none.
    cause_in_record = any(cause is not None for cause in causes.values())
    if cause_in_record:
        suppressed = {wid for wid, cause in causes.items()
                      if cause == CAUSE_DONE_COVERED}
    else:
        suppressed = (unplaced & retired) - fired
    survivors = unplaced & fired
    by_cause = Counter(str(cause) for cause in causes.values())
    return {
        "cause_in_record": cause_in_record,
        "run_retired_by_cause": dict(sorted(by_cause.items())),
        "retired_done_covered": (len(suppressed) if cause_in_record
                                 else None),
        "windows": len(windows),
        "placed_in_snapshot": len(placed),
        "unplaced_in_snapshot": len(unplaced),
        "run_retired": len(retired),
        "run_retired_that_were_placed": len(retired & placed),
        "suppressed_unplaced_never_fired": len(suppressed),
        "survivors_that_fired": len(survivors),
        "survivor_place_jobs": sum(seen["fired"][wid] for wid in survivors),
        "survivor_place_cpu_s": round(
            sum(seen["place_cpu"][wid] for wid in survivors), 1),
        "gate_says_done_now": len(gated),
        "gate_agrees_with_suppressed": len(gated & suppressed),
        "gate_done_but_run_fired": sorted(gated & survivors)[:8],
        "gate_open_but_run_suppressed": sorted(suppressed - gated)[:8],
        "unplaced_neither_fired_nor_retired": len(
            unplaced - retired - fired),
    }


def tile_reasons(instance: object, seen: dict[str, object],
                 limit: int = 12) -> list:
    """For the windows the gate let through: which streams are open on
    the tiles their extent projects to."""
    import numpy as np

    unplaced = set(instance.windows()) - set(instance.placements())
    survivors = sorted(unplaced & set(seen["fired"]))
    rows = []
    grid_done = instance.done_grid(0)
    certs = instance.certificates()
    streams = tuple(stream.stream_id for stream in instance.row.streams)
    open_by_stream: Counter = Counter()
    tiles_y, tiles_x = instance.row.tiles_yx
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            if grid_done[ty, tx]:
                continue
            for stream in streams:
                if (0, ty, tx, stream) not in certs:
                    open_by_stream[stream] += 1
    rows.append({"open_tiles": int((~grid_done).sum()),
                 "open_tile_streams": dict(open_by_stream)})
    for wid in survivors[:limit]:
        done = instance.done_cells(wid[:3])
        frame = instance.frame(wid[:3])
        if done is None or frame is None:
            rows.append({"window": wid, "done_cells": None})
            continue
        cy0, cx0, cy1, cx1 = wid[3]
        support = frame.support_cells[cy0:cy1, cx0:cx1]
        covered = done[cy0:cy1, cx0:cx1][support]
        rows.append({
            "window": wid,
            "supported_cells": int(support.sum()),
            "done_cells_in_extent": int(np.count_nonzero(covered)),
            "open_cells_in_extent": int(covered.size - covered.sum()),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="the facts.npz the run RESUMED FROM")
    parser.add_argument("--events", type=Path, required=True,
                        help="events.jsonl the run then wrote")
    parser.add_argument("--format", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reasons", action="store_true")
    parser.add_argument("--reasons-limit", type=int, default=12)
    args = parser.parse_args()
    seen = observed(args.events)
    print(NOTE_SUPPRESSED, file=sys.stderr)
    instance = replay(args.snapshot, args.format, seen["captures"])
    report = {"snapshot": str(args.snapshot), "events": str(args.events),
              "format": args.format, "census": census(instance, seen),
              "settled": dict(seen["settled"])}
    if args.reasons:
        report["reasons"] = tile_reasons(instance, seen, args.reasons_limit)
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n")


if __name__ == "__main__":
    main()

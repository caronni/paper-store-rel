"""W6/V4 qualification: sheet I decoded FRESH with the plane-fields dial ON.

docs/PLANE-FIELDS.md §4 (V3/V4) and §6.2 W6.  Read-only against every
archived artifact: the three 2026-08-18 Canon 2400 captures are opened for
reading and sha-verified by the receiver itself (``expected_sha256`` on
each :class:`CaptureInput`); the archived ``I-…/receive.state`` is NEVER
opened by this script -- the dial-off baseline it is scored against comes
from the W0 harness's cached ``StateFacts`` (``_inputs.read_state_facts``)
and from experiments/033 §033.4.

Everything this run writes lands under ``scratch/plane-fields/qual/``.

    cd <repo>          # or a plane-fields worktree
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.qualify_sheet_i

THE PRE-REGISTERED BAR (fixed before the run):
  PRIMARY  median Y residue over the twelve dead-band columns
           tile_x in {8,9,10,11,15,16,17,18,19,27,28,29}  <=  5/53
           (aspirational: the <=1.3/53 class of §033.4)
  REPORT   total + per-stream certificates, close status and payload sha
           against 2445b95d…, column 8 alone (baseline 53/53 = zero Y
           evidence, pure extrapolation), the plane_fields Details,
           wall/CPU/RSS, and the W4 probe counts actually fired.

LADDER NOTE (deviation, deliberate, see the report): the baseline is
e033 §033.3 run 2 -- "fresh state, three 2400 captures, ``--refine``" --
so this run declares ``run_refine=True`` too.  The default ordinary-only
ladder stops before the first M level and would not be comparable to the
number it is scored against.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np

from ._inputs import (
    MAIN_SCRATCH,
    SHEET_I_SCANS,
    SHEET_I_STATE,
    read_state_facts,
    receiver_tree_sha256,
    recorded_scan_shas,
    tree_state,
)

# ------------------------------------------------------------------ pins
FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"
CAPTURE_ORDER = (
    "269d81217ec48a5e57ae5736baf091f0afe3f66dd15539c0f39dfc6cffdea30c",
    "a410631d6ff6a8519767a4cdb7c55bd6e5b90b549a7450d017e783064991e8dd",
    "36b90a50f272bb02982286b18657a8630eaa378eb7ac553e3a54461e548d55af",
)
CAPTURE_DPI = 2400.0
BASELINE_CERTS = {"C": 1895, "M": 1958, "Y": 1444}
BASELINE_TOTAL = 5297
BASELINE_PAYLOAD_SHA = (
    "2445b95db5b49bf3e05eb2538e9e247d289a48a4fed2e46eb7ba78ab61e4350b")
#: experiments/033 §033.4, residue/53 by tile_x (the pre-registered table).
BASELINE_RESIDUE_LOG = (
    7, 1, 21, 5, 0, 0, 0, 14, 53, 38, 37, 39, 0, 0, 0, 45, 49, 45, 31, 47,
    2, 0, 0, 0, 4, 3, 5, 43, 50, 24, 12, 0, 2, 0, 0, 0, 4)
DEAD_BANDS = (8, 9, 10, 11, 15, 16, 17, 18, 19, 27, 28, 29)
PRIMARY_BAR = 5.0
ASPIRATIONAL_BAR = 1.3

OUT_DIR = MAIN_SCRATCH / "plane-fields" / "qual"
PLANES = ("C", "M", "Y")


# ------------------------------------------------------------- observer
class QualObserver:
    """Persist every event as JSONL, keep the plane-field rows in memory.

    Never raises: :class:`~holo.receive.observer.EventSink` silently
    DISABLES an observer that throws, which would cost the whole run its
    measurement channel.  ``wants_snapshots`` stays False -- the W5
    quiver snapshot is illustration only and the opt-in would turn on
    fine-product accumulation across every stage for hours.
    """

    wants_snapshots = False

    def __init__(self, events_path: Path, log) -> None:
        self._handle = events_path.open("w", encoding="utf-8")
        self._log = log
        self._t0 = time.time()
        self.field_rows: list[dict] = []
        self.write_failures = 0
        self.events = 0
        from holo.receive.diag.field_stats import FieldStats
        self.field_stats = FieldStats()

    def __call__(self, event) -> None:
        try:
            self.events += 1
            row = event.to_dict()
            self._handle.write(json.dumps(
                row, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False) + "\n")
            name = event.name
            if name == "payload.plane_fields":
                self.field_rows.append(row)
                self._handle.flush()
                details = row.get("details") or {}
                self._say(
                    f"FIELD {(event.capture_id or '')[:8]} "
                    f"{details.get('lane.id', '?')} "
                    f"rms C/M/Y "
                    f"{details.get('plane_fields.rms_dots.c')}/"
                    f"{details.get('plane_fields.rms_dots.m')}/"
                    f"{details.get('plane_fields.rms_dots.y')} "
                    f"cov {details.get('plane_fields.coverage')} "
                    f"adopted '{details.get('plane_fields.adopted')}' "
                    f"probes {details.get('plane_fields.probes')}"
                    f"/{details.get('plane_fields.probe_sites')} sites "
                    f"samples {details.get('plane_fields.samples')} "
                    f"[{details.get('plane_fields.samples_by_source')}] "
                    f"solve {details.get('plane_fields.solve_seconds')}s "
                    f"probe {details.get('plane_fields.probe_seconds')}s")
            elif name in ("session.open", "session.complete", "run.failed",
                          "receiver.provisional") or name.startswith(
                              ("capture.", "close.", "level.", "barrier.")):
                self._say(f"{name} {(event.capture_id or '')[:8]} "
                          f"{event.message[:160]}")
            elif name == "stage.complete":
                details = row.get("details") or {}
                self._say(
                    f"stage.complete {event.stage.value} "
                    f"{(event.capture_id or '')[:8]} "
                    f"lane={details.get('lane.id', '-')} "
                    f"{event.message[:120]}")
            self.field_stats(event)
        except Exception:                                    # noqa: BLE001
            self.write_failures += 1

    def _say(self, text: str) -> None:
        print(f"[{time.time() - self._t0:8.1f}s] {text}", file=self._log,
              flush=True)

    def close(self) -> None:
        try:
            self._handle.close()
        except Exception:                                    # noqa: BLE001
            pass


# -------------------------------------------------------------- scoring
def residue_by_column(certificates, tiles_yx) -> dict[str, list[int]]:
    """Per-stream uncertified tiles per tile_x, out of ``tiles_yx[0]``."""
    rows, columns = tiles_yx
    out: dict[str, list[int]] = {}
    for stream in PLANES:
        have = np.zeros((rows, columns), bool)
        for record in certificates:
            if record.stream_id == stream:
                have[record.tile_yx] = True
        out[stream] = [int(v) for v in (~have).sum(axis=0)]
    return out


def verdict(residue_y: list[int]) -> dict:
    dead = [residue_y[i] for i in DEAD_BANDS]
    median = float(np.median(dead))
    return {
        "dead_band_columns": list(DEAD_BANDS),
        "dead_band_residue": dead,
        "median": median,
        "primary_bar": PRIMARY_BAR,
        "primary_pass": bool(median <= PRIMARY_BAR),
        "aspirational_bar": ASPIRATIONAL_BAR,
        "aspirational_pass": bool(median <= ASPIRATIONAL_BAR),
        "column_8": residue_y[8],
    }


# --------------------------------------------------------------- figure
def draw_comparison(path: Path, baseline: list[int], dial_on: list[int],
                    rows: int, title: str) -> None:
    """Paired residue bars per tile_x, dead-band columns shaded."""
    from PIL import Image, ImageDraw

    columns = len(baseline)
    pad_l, pad_t, pad_r, pad_b = 56, 74, 20, 56
    plot_w, plot_h = 1100, 360
    width = pad_l + plot_w + pad_r
    height = pad_t + plot_h + pad_b
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 8), title, fill="black")
    draw.text((10, 24),
              "Y-stream residue (uncertified tiles) per tile column, out of "
              f"{rows}; grey band = the twelve pre-registered dead-band "
              "columns", fill=(70, 70, 70))
    draw.text((10, 40),
              "dark = dial-OFF baseline (archived sheet-I state)    "
              "orange = dial-ON (this run)", fill=(70, 70, 70))

    step = plot_w / columns
    y0, y1 = pad_t, pad_t + plot_h
    for index in DEAD_BANDS:
        x = pad_l + index * step
        draw.rectangle([x, y0, x + step, y1], fill=(238, 238, 238))
    draw.rectangle([pad_l, y0, pad_l + plot_w, y1], outline=(160, 160, 160))
    for level in (0, rows // 4, rows // 2, 3 * rows // 4, rows):
        y = y1 - plot_h * level / rows
        draw.line([pad_l, y, pad_l + plot_w, y], fill=(220, 220, 220))
        draw.text((8, y - 6), f"{level:>3}", fill=(90, 90, 90))
    bar = step * 0.40
    for index in range(columns):
        x = pad_l + index * step
        for offset, values, color in (
            (0.06, baseline, (40, 40, 90)),
            (0.52, dial_on, (230, 130, 20)),
        ):
            value = values[index]
            if value <= 0:
                continue
            top = y1 - plot_h * value / rows
            draw.rectangle([x + step * offset, top,
                            x + step * offset + bar, y1], fill=color)
        if index % 2 == 0:
            draw.text((x + step * 0.1, y1 + 6), f"{index}",
                      fill=(90, 90, 90))
    draw.text((pad_l, y1 + 26), "tile_x", fill=(90, 90, 90))
    image.save(path)


# ----------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dial", choices=("on", "off"), default="on")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--captures", type=int, default=3)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = sys.stderr

    before = tree_state()
    print(f"tree {before['receiver_tree_sha256'][:16]}… head "
          f"{before['head'][:12]} dirty={before['dirty']}", file=log)

    # ---- inputs, sha-pinned -------------------------------------------
    recorded = recorded_scan_shas()
    by_sha = {sha: path for path, sha in recorded.items()}
    sources = []
    for sha in CAPTURE_ORDER[:args.captures]:
        path = by_sha.get(sha)
        if path is None:
            raise SystemExit(f"scan-shas.txt has no entry for {sha[:12]}…")
        if not Path(path).is_file():
            raise SystemExit(f"missing capture file {path}")
        sources.append((sha, Path(path)))
        print(f"capture {sha[:12]}… -> {Path(path).name} "
              f"({Path(path).stat().st_size} B)", file=log)
    for sha, path in sources:
        if path not in {p for p in SHEET_I_SCANS.values()}:
            raise SystemExit(f"{path} is not a pinned sheet-I scan")

    from holo.format.resolve import resolve_format_ref
    from holo.receive import (
        CaptureInput, ProvisionalReceiverWarning, ReceiveRequest, run_receive)
    from holo.receive import _parallel
    from holo.receive.color_field import PlaneFieldConfig
    from holo.receive.production import production_pipeline
    from holo.receive.production_color import ProductionColorPayload

    spec = resolve_format_ref(FORMAT_REF)
    print(f"format {spec.spec_id} family={spec.codec_family.name} "
          f"tiles={spec._tiles_yx} per_page={spec.tiles_per_page}", file=log)

    _parallel.set_worker_count(args.workers)

    request = ReceiveRequest(
        spec,
        tuple(CaptureInput(source=str(path), dpi=CAPTURE_DPI,
                           expected_sha256=sha)
              for sha, path in sources),
        state_path=out_dir / "receive.state",
        page_hypotheses=(0,),
        defer_fountain_close=True,
        run_refine=True,          # match the e033 §033.3 run-2 ladder
    )
    pipeline = production_pipeline(request)
    config = PlaneFieldConfig() if args.dial == "on" else None
    if config is not None:
        pipeline = replace(pipeline, lanes=replace(
            pipeline.lanes,
            payload=ProductionColorPayload(plane_fields=config)))
    print(f"dial={args.dial} config={config} workers={args.workers} "
          f"run_refine={request.run_refine} "
          f"defer_close={request.defer_fountain_close}", file=log)

    observer = QualObserver(out_dir / "events.jsonl", log)
    wall0 = time.time()
    cpu0 = time.process_time()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("always", ProvisionalReceiverWarning)
            result = run_receive(request, pipeline=pipeline,
                                 observer=observer)
    finally:
        observer.close()
    wall = time.time() - wall0
    cpu = time.process_time() - cpu0
    usage = resource.getrusage(resource.RUSAGE_SELF)

    after = tree_state()
    void = before["receiver_tree_sha256"] != after["receiver_tree_sha256"]

    # ---- score ---------------------------------------------------------
    state = result.state
    counts = {plane: sum(1 for row in state.certificates
                         if row.stream_id == plane) for plane in PLANES}
    residue = residue_by_column(state.certificates, spec._tiles_yx)
    rows, _columns = spec._tiles_yx

    facts = read_state_facts(SHEET_I_STATE, CAPTURE_ORDER[0])
    baseline_residue = residue_by_column(facts.certificates, spec._tiles_yx)

    report = {
        "void": void,
        "tree_before": before,
        "tree_after": after,
        "format": spec.spec_id,
        "captures": [
            {"sha256": sha, "file": str(path), "dpi": CAPTURE_DPI}
            for sha, path in sources],
        "dial": args.dial,
        "workers": args.workers,
        "run_refine": request.run_refine,
        "plane_field_config": (
            None if config is None
            else {name: getattr(config, name)
                  for name in config.__dataclass_fields__}),
        "runtime": {
            "wall_seconds": wall,
            "cpu_process_seconds": cpu,
            "ru_utime": usage.ru_utime,
            "ru_stime": usage.ru_stime,
            "ru_maxrss_bytes": usage.ru_maxrss,
            "events": observer.events,
            "observer_write_failures": observer.write_failures,
            "observer_failures": list(result.observer_failures),
        },
        "result": {
            "status": state.status.value,
            "verified": bool(result.verified),
            "payload_sha256": state.close.payload_sha256,
            "payload_bytes": (None if result.payload is None
                              else len(result.payload)),
            "baseline_payload_sha256": BASELINE_PAYLOAD_SHA,
            "payload_sha_matches_baseline": (
                state.close.payload_sha256 == BASELINE_PAYLOAD_SHA),
            "state_sha256": result.authoritative_sha256,
            "captures": [
                {"sha256": row.source_sha256, "status": row.status.value,
                 "barriers": row.barriers_committed,
                 "changed": row.state_changed}
                for row in result.captures],
        },
        "certificates": {
            "total": len(state.certificates),
            "by_stream": counts,
            "baseline_total": BASELINE_TOTAL,
            "baseline_by_stream": BASELINE_CERTS,
            "delta_total": len(state.certificates) - BASELINE_TOTAL,
            "delta_by_stream": {p: counts[p] - BASELINE_CERTS[p]
                                for p in PLANES},
        },
        "residue": {
            "rows_per_column": rows,
            "dial_on": residue,
            "baseline_archived_state": baseline_residue,
            "baseline_033_4_log": list(BASELINE_RESIDUE_LOG),
        },
        "verdict": {
            "dial_on": verdict(residue["Y"]),
            "baseline_archived_state": verdict(baseline_residue["Y"]),
            "baseline_033_4_log": verdict(list(BASELINE_RESIDUE_LOG)),
        },
        "plane_fields_events": observer.field_rows,
        "field_stats_summary": [
            {"capture_id": row.capture_id, "lane_id": row.lane_id,
             "calls": row.calls, "rms_dots": row.rms_dots,
             "peak_dots": row.peak_dots, "coverage": row.coverage,
             "adopted_counts": row.adopted_counts}
            for row in observer.field_stats.summary()],
    }
    (out_dir / f"qual-{args.dial}.json").write_text(
        json.dumps(report, indent=1, sort_keys=True))

    try:
        draw_comparison(
            out_dir / f"residue-comparison-{args.dial}.png",
            baseline_residue["Y"], residue["Y"], rows,
            f"sheet I — Y residue per column: dial-OFF baseline vs "
            f"plane-fields dial-{args.dial.upper()}  ({spec.spec_id})")
    except Exception as exc:                                 # noqa: BLE001
        print(f"figure failed: {type(exc).__name__}: {exc}", file=log)

    # ---- human summary --------------------------------------------------
    print("", file=log)
    print(f"VOID={void}  wall {wall / 3600:.2f} h  cpu {cpu / 3600:.2f} h  "
          f"maxrss {usage.ru_maxrss / 1e9:.1f} GB  events {observer.events}",
          file=log)
    print(f"status {state.status.value}  payload_sha "
          f"{state.close.payload_sha256}  "
          f"matches_baseline="
          f"{state.close.payload_sha256 == BASELINE_PAYLOAD_SHA}", file=log)
    print(f"certificates {len(state.certificates)} "
          f"(baseline {BASELINE_TOTAL}) {counts}", file=log)
    for label, key in (("dial-on", "dial_on"),
                       ("baseline(state)", "baseline_archived_state"),
                       ("baseline(§033.4)", "baseline_033_4_log")):
        row = report["verdict"][key]
        print(f"{label:>18}: dead-band median {row['median']:.1f}/{rows} "
              f"col8 {row['column_8']}  primary_pass={row['primary_pass']}",
              file=log)
    print(f"wrote {out_dir}", file=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

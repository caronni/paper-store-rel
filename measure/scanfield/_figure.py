"""The offset map: every measurement against the floor, on one scale.

Four panels, all four drawn with the SAME y-axis — plus or minus 0.30
printed dots, so the 0.25-dot publish floor sits just inside the frame
and the reader does not have to do arithmetic to see that the scanner
arms hug zero and the print-inclusive arm does not:

* A — lateral (sensor-axis) offset against platen x.  The chromatic
  aberration question.  Everything is on the centre line.
* B — transport-axis offset against platen x.  Two flat constants, one
  per channel, which is what a CIS line-timing offset looks like.
* C — the same axis as A for the payload sheet's own field boundary,
  which INCLUDES the printer, over the scanner-only marks at the same
  platen positions.  The attribution panel.
* D — capture against capture, per target.  The invariance premise: a
  scanner property must land on the diagonal.

``scanner/_figures.Panel`` is reused rather than re-implemented, so the
two instruments' figures cannot drift apart on axis conventions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from scanner._figures import AXIS, CHANNEL_COLORS, INK, MUTED, Panel

FLOOR_DOTS = 0.25
LIMIT_DOTS = 0.30
FLOOR_COLOR = (198, 64, 64)
CAPTURE_SHAPE = {0: "o", 1: "s"}


def _points(rows: list[dict[str, Any]], arm: str, axis: str, channel: str
            ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Platen x and offset, grouped by capture, for one arm/axis/pair."""
    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        if row["arm"] != arm:
            continue
        if arm == "marks":
            value = row["dx_dots" if axis == "x" else "dy_dots"].get(channel)
        elif arm == "edges-paired":
            if row["axis"] != axis:
                continue
            value = row["displacement_dots"].get(channel)
        elif arm == "margin":
            if row["axis"] != axis:
                continue
            value = row["shift_dots"].get(channel)
        else:
            continue
        if value is None or not np.isfinite(value):
            continue
        grouped.setdefault(row["capture"], []).append((row["x_mm"], value))
    return {key: (np.asarray([p[0] for p in pairs]),
                  np.asarray([p[1] for p in pairs]))
            for key, pairs in grouped.items()}


def _floor_band(panel: Panel) -> None:
    for level in (FLOOR_DOTS, -FLOOR_DOTS):
        panel.hline(level, FLOOR_COLOR, 2)
    panel.hline(0.0, AXIS, 1)


def _scatter(panel: Panel, rows: list[dict[str, Any]], arm: str, axis: str,
             captures: list[str], size: int = 3) -> None:
    for channel in ("R", "B"):
        for capture, (xs, values) in _points(rows, arm, axis,
                                             channel).items():
            shape = CAPTURE_SHAPE.get(captures.index(capture)
                                      if capture in captures else 0, "o")
            for x, value in zip(xs, values):
                # Clamp rather than let an off-scale margin point draw
                # over the panel title: piled on the frame it still reads
                # as "past the floor", which is the whole point of C.
                panel.marker(x, min(max(value, -LIMIT_DOTS), LIMIT_DOTS),
                             CHANNEL_COLORS[channel], size, shape)


def draw_offset_map(path: Path, report: dict[str, Any]) -> None:
    rows = report.get("rows", [])
    if not rows:
        return
    captures = sorted({row["capture"] for row in rows
                       if row["arm"] == "marks"})
    image = Image.new("RGB", (1340, 980), "white")
    draw = ImageDraw.Draw(image)
    # ASCII only in the figure: PIL's built-in bitmap font has no em dash
    # and draws a box where one should be.
    draw.text((28, 20), "measure/scanfield - per-channel offset across the "
                        "platen, against the 0.25-dot publish floor", fill=INK)
    draw.text((28, 36), f"Canon LiDE 400, tone {report.get('tone_curve')}; "
                        f"red = R-G, blue = B-G, red rules = "
                        f"{FLOOR_DOTS} dots "
                        f"(holo3/plugins/fields.py MIN_DELTA_DOTS)",
              fill=MUTED)

    ticks_x = [0, 50, 100, 150, 200]
    ticks_y = [-0.25, -0.125, 0.0, 0.125, 0.25]
    boxes = ((70, 130, 630, 420), (740, 130, 1300, 420),
             (70, 560, 630, 850), (740, 560, 1300, 850))

    panel = Panel(draw, boxes[0], (0, 216), (-LIMIT_DOTS, LIMIT_DOTS),
                  "A  lateral (sensor axis), scanner only",
                  "platen x (mm)", "offset (600-dpi printed dots)")
    panel.grid(ticks_x, ticks_y, yfmt="%+.3f")
    _floor_band(panel)
    _scatter(panel, rows, "marks", "x", captures)
    _scatter(panel, rows, "edges-paired", "x", captures, size=2)
    summary = report.get("summary", {})
    panel.caption("marks (circles) + edges (squares), both captures")
    for channel in ("R", "B"):
        entry = summary.get(f"marks/x/{channel}-G")
        if entry:
            panel.caption(f"marks {channel}-G  mean {entry['mean_dots']:+.4f}"
                          f"  max |.| {entry['max_abs_dots']:.4f} dots",
                          CHANNEL_COLORS[channel])

    panel = Panel(draw, boxes[1], (0, 216), (-LIMIT_DOTS, LIMIT_DOTS),
                  "B  transport axis, scanner only",
                  "platen x (mm)", "offset (600-dpi printed dots)")
    panel.grid(ticks_x, ticks_y, yfmt="%+.3f")
    _floor_band(panel)
    _scatter(panel, rows, "marks", "y", captures)
    _scatter(panel, rows, "edges-paired", "y", captures, size=2)
    for channel in ("R", "B"):
        entry = summary.get(f"marks/y/{channel}-G")
        if entry:
            panel.curve([0, 216], [entry["mean_dots"]] * 2,
                        CHANNEL_COLORS[channel], 1)
            panel.caption(f"marks {channel}-G  constant "
                          f"{entry['mean_dots']:+.4f} dots "
                          f"({entry['mean_dots'] * 42.3333:+.2f} um)",
                          CHANNEL_COLORS[channel])

    panel = Panel(draw, boxes[2], (0, 216), (-LIMIT_DOTS, LIMIT_DOTS),
                  "C  payload boundary (scanner + PRINTER) over marks",
                  "platen x (mm)", "offset (600-dpi printed dots)")
    panel.grid(ticks_x, ticks_y, yfmt="%+.3f")
    _floor_band(panel)
    _scatter(panel, rows, "margin", "x", captures, size=4)
    _scatter(panel, rows, "marks", "x", captures, size=2)
    anti = report.get("antisymmetry", {})
    for arm in ("margin", "marks"):
        entry = anti.get(f"{arm}/x/B-G")
        if entry:
            panel.caption(
                f"{arm:<7} B-G right-minus-left "
                f"{entry['right_minus_left_dots']:+.4f} "
                f"+- {entry['standard_error_dots']:.4f} dots",
                CHANNEL_COLORS["B"])

    panel = Panel(draw, boxes[3], (-LIMIT_DOTS, LIMIT_DOTS),
                  (-LIMIT_DOTS, LIMIT_DOTS),
                  "D  invariance: same target, two captures",
                  f"offset on {captures[0] if captures else 'A'} (dots)",
                  f"offset on {captures[1] if len(captures) > 1 else 'B'}")
    panel.grid(ticks_y, ticks_y, xfmt="%+.2f", yfmt="%+.3f")
    panel.curve([-LIMIT_DOTS, LIMIT_DOTS], [-LIMIT_DOTS, LIMIT_DOTS],
                AXIS, 1)
    if len(captures) == 2:
        index: dict[tuple, dict[str, float]] = {}
        for row in rows:
            if row["arm"] != "marks":
                continue
            for axis in ("x", "y"):
                values = row["dx_dots" if axis == "x" else "dy_dots"]
                for channel in ("R", "B"):
                    value = values.get(channel)
                    if value is None or not np.isfinite(value):
                        continue
                    slot = index.setdefault((row["target"], axis, channel), {})
                    slot[row["capture"]] = value
        for (_, axis, channel), pair in index.items():
            if len(pair) != 2:
                continue
            panel.marker(pair[captures[0]], pair[captures[1]],
                         CHANNEL_COLORS[channel], 3,
                         "o" if axis == "x" else "s")
    block = report.get("reproducibility_marks", {})
    for key in ("y/R-G", "y/B-G"):
        entry = block.get(key)
        if entry:
            panel.caption(f"{key}  median |A-B| "
                          f"{entry['median_abs_difference_dots']:.4f} dots, "
                          f"r {entry['pearson_r']:+.2f}",
                          CHANNEL_COLORS[key[-3]])

    final = report.get("verdict", {})
    if final:
        draw.text((28, 946), f"VERDICT {final.get('verdict')} - worst raw "
                             f"{final.get('worst_raw_offset', {}).get('value', float('nan')):.4f} "
                             f"dots, floor {FLOOR_DOTS}, headroom "
                             f"{final.get('headroom_factor', float('nan')):.1f}x",
                  fill=INK)
    image.save(path)

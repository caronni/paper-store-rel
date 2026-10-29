"""The home flatbed's offset map — the constant, and the three ways it is one.

Same scale and same conventions as ``_figure`` so the two scanners can be
read side by side: four panels, all on plus or minus 0.30 printed dots,
with the 0.25-dot publish floor drawn as a red rule just inside the
frame.  What differs is what the panels have to prove, because this
scanner's answer is not "nothing is there" but "something is there and it
is a constant":

* A — lateral (sensor) axis against platen x.  The chromatic aberration
  question, and the panel that looks like the Canon's.
* B — transport axis against platen x.  Two flat lines well clear of
  zero.  This is the finding.
* C — the placement arm.  Each capture's mean against what a
  PLATEN-locked effect predicts and what a PAGE-locked one predicts.
  The 180-degree and 90-degree captures are what separate a scanner
  property from a printer one, and this panel is that separation.
* D — the comb phase test.  Offsets binned by phase within each named
  comb period, against the band that pure scatter would produce.  Flat
  inside the band means the comb is not carrying the effect.
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
BAND_COLOR = (210, 210, 216)
UM_PER_DOT = 25400.0 / 600.0
SHAPES = ("o", "s", "^", "v", "x")


def _points(rows: list[dict[str, Any]], arm: str, axis: str, channel: str
            ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    grouped: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        if row["arm"] != arm:
            continue
        value = row["dx_dots" if axis == "x" else "dy_dots"].get(channel)
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
            index = captures.index(capture) if capture in captures else 0
            shape = SHAPES[index % len(SHAPES)]
            for x, value in zip(xs, values):
                panel.marker(x, min(max(value, -LIMIT_DOTS), LIMIT_DOTS),
                             CHANNEL_COLORS[channel], size, shape)


def _panel_placement(panel: Panel, report: dict[str, Any]) -> None:
    """Observed capture means against the two competing predictions."""
    tests = report.get("orientation", {}).get("against_flat", {})
    names = sorted(tests)
    if not names:
        panel.caption("no rotated captures in this run")
        return
    # Panel::marker draws a filled circle or a filled rectangle and
    # nothing else, so the three series are told apart by size and
    # colour: a large channel-coloured disc for what was measured, a
    # small dark square on top of it for what a platen-locked effect
    # predicts, and a small red square for what a page-locked one
    # predicts.  When the dark square sits inside the disc, the scanner
    # hypothesis fits; the red square is then somewhere else entirely.
    for slot, name in enumerate(names):
        entry = tests[name]
        for channel in ("R", "B"):
            key = f"y/{channel}-G"
            observed = entry.get(f"{key}/observed")
            platen = entry.get(f"{key}/platen_locked_predicts")
            page = entry.get(f"{key}/page_locked_predicts")
            if observed is None or platen is None:
                continue
            x = slot + (0.18 if channel == "B" else -0.18)
            panel.marker(x, observed, CHANNEL_COLORS[channel], 6, "o")
            panel.marker(x, platen, AXIS, 2, "s")
            if page is not None:
                panel.marker(x, min(max(page, -LIMIT_DOTS), LIMIT_DOTS),
                             FLOOR_COLOR, 3, "s")
    panel.caption("disc = observed, dark square = platen-locked predicted,")
    panel.caption("red square = page-locked (printer-side) predicted")
    panel.caption("0 re-placed  1 displaced  2 rot 90  3 rot 180")


def _panel_comb(panel: Panel, report: dict[str, Any]) -> None:
    """Binned offset against comb phase, with the pure-noise band."""
    comb = report.get("comb_phase", {})
    drawn = 0
    for key in sorted(comb):
        entry = comb[key]
        if not entry.get("tested") or "/y/" not in key:
            continue
        means = np.asarray(entry["bin_means_dots"])
        centred = means - means.mean()
        phases = np.linspace(0.0, 1.0, centred.size, endpoint=False)
        channel = key[-3]
        shape = "o" if key.startswith("ccd") else "s"
        for phase, value in zip(phases, centred):
            panel.marker(phase, value, CHANNEL_COLORS[channel], 4, shape)
        noise = entry["expected_range_from_noise_dots"] / 2.0
        panel.curve([0.0, 1.0], [noise, noise], BAND_COLOR, 1)
        panel.curve([0.0, 1.0], [-noise, -noise], BAND_COLOR, 1)
        drawn += 1
    panel.hline(0.0, AXIS, 1)
    if not drawn:
        panel.caption("comb arm not run")
        return
    panel.caption("circles = 18.63 mm sensor comb, squares = 11.36 px")
    panel.caption("grey = range pure scatter would give; deviation from")
    panel.caption("the platen mean, so a flat line means no comb term")


def draw_hp_offset_map(path: Path, report: dict[str, Any]) -> None:
    rows = report.get("rows", [])
    if not rows:
        return
    captures = sorted({row["capture"] for row in rows
                       if row["arm"] == "marks"})
    summary = report.get("summary", {})
    image = Image.new("RGB", (1340, 980), "white")
    draw = ImageDraw.Draw(image)
    # ASCII only: PIL's built-in bitmap font draws a box for an em dash.
    draw.text((28, 20), "measure/scanfield - home/HP flatbed per-channel "
                        "offset across the platen, against the 0.25-dot "
                        "publish floor", fill=INK)
    draw.text((28, 36), f"HP M281fdw flatbed, 1200 dpi colour, tone "
                        f"{report.get('tone_curve')}; red = R-G, blue = B-G, "
                        f"red rules = {FLOOR_DOTS} dots "
                        f"(src/holo/receiver/plugins/fields.py MIN_DELTA_DOTS)",
              fill=MUTED)

    ticks_x = [0, 50, 100, 150, 200]
    ticks_y = [-0.25, -0.125, 0.0, 0.125, 0.25]
    boxes = ((70, 130, 630, 420), (740, 130, 1300, 420),
             (70, 560, 630, 850), (740, 560, 1300, 850))

    panel = Panel(draw, boxes[0], (0, 216), (-LIMIT_DOTS, LIMIT_DOTS),
                  "A  lateral (sensor axis)", "platen x (mm)",
                  "offset (600-dpi printed dots)")
    panel.grid(ticks_x, ticks_y, yfmt="%+.3f")
    _floor_band(panel)
    _scatter(panel, rows, "marks", "x", captures, size=2)
    for channel in ("R", "B"):
        entry = summary.get(f"marks/x/{channel}-G")
        if entry:
            panel.caption(f"{channel}-G  mean {entry['mean_dots']:+.4f}  "
                          f"max |.| {entry['max_abs_dots']:.4f} dots",
                          CHANNEL_COLORS[channel])

    panel = Panel(draw, boxes[1], (0, 216), (-LIMIT_DOTS, LIMIT_DOTS),
                  "B  transport axis - THE FINDING", "platen x (mm)",
                  "offset (600-dpi printed dots)")
    panel.grid(ticks_x, ticks_y, yfmt="%+.3f")
    _floor_band(panel)
    _scatter(panel, rows, "marks", "y", captures, size=2)
    for channel in ("R", "B"):
        entry = summary.get(f"marks/y/{channel}-G")
        if entry:
            panel.curve([0, 216], [entry["mean_dots"]] * 2,
                        CHANNEL_COLORS[channel], 1)
            panel.caption(f"{channel}-G  constant {entry['mean_dots']:+.4f} "
                          f"dots ({entry['mean_dots'] * UM_PER_DOT:+.2f} um), "
                          f"sd {entry['std_dots']:.4f}",
                          CHANNEL_COLORS[channel])
    separation = report.get("channel_separation", {}).get("y")
    if separation:
        panel.caption(f"R-to-B {separation['R_minus_B_dots']:+.4f} dots "
                      f"({separation['R_minus_B_um']:+.2f} um) - "
                      f"over floor: {separation['over_floor']}", INK)

    panel = Panel(draw, boxes[2], (-0.6, 3.6), (-LIMIT_DOTS, LIMIT_DOTS),
                  "C  placement: platen-locked or page-locked?",
                  "capture (see caption)", "transport offset (dots)")
    panel.grid([0, 1, 2, 3], ticks_y, xfmt="%.0f", yfmt="%+.3f")
    _floor_band(panel)
    _panel_placement(panel, report)

    panel = Panel(draw, boxes[3], (0.0, 1.0), (-0.06, 0.06),
                  "D  comb phase test - is a known comb the answer?",
                  "phase within the comb period",
                  "offset minus platen mean (dots)")
    panel.grid([0.0, 0.25, 0.5, 0.75, 1.0], [-0.05, -0.025, 0.0, 0.025, 0.05],
               xfmt="%.2f", yfmt="%+.3f")
    _panel_comb(panel, report)

    final = report.get("verdict", {})
    field = report.get("field_verdict", {})
    if final:
        draw.text((28, 930),
                  f"PRE-REGISTERED VERDICT {final.get('verdict')} - worst raw "
                  f"{final.get('worst_raw_offset', {}).get('value', float('nan')):.4f}"
                  f" dots, floor {FLOOR_DOTS}, headroom "
                  f"{final.get('headroom_factor', float('nan')):.2f}x",
                  fill=INK)
    if field:
        draw.text((28, 950),
                  f"FIELD VERDICT {field.get('verdict')} - worst median "
                  f"|offset - platen mean| "
                  f"{field.get('worst_median_abs_demeaned_dots', float('nan')):.4f}"
                  f" dots, headroom "
                  f"{field.get('headroom_factor', float('nan')):.1f}x",
                  fill=INK)
    image.save(path)

"""E5/E5b's figure: what each probe density costs and what it buys (PIL).

matplotlib is not in this env (``_figures`` says so and draws with PIL);
this follows the same house style.  Everything is read out of the run
JSON -- nothing is recomputed here, so the illustration can be re-cut
with ``--figure-only`` without re-running a measurement.  Generic over
whatever densities the run selected (``document["modes"]``).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ._swim_inputs import DEAD_BANDS

SHORT = {"block-per-bin": "A  block/bin 5x5",
         "whole-tile": "B  whole-tile 64x64",
         "every-block": "C  every block 5x5",
         "tile-fragment": "F  tile fragment"}
COLOR = {"block-per-bin": (30, 90, 190), "whole-tile": (200, 80, 30),
         "every-block": (90, 90, 90), "tile-fragment": (20, 140, 70)}
GREY = (120, 120, 120)
DARK = (60, 60, 60)


def _bars(draw, box, values, labels, texts, colors, *, title, unit,
          log: bool = False):
    """One bar panel; ``box`` is (left, top, right, bottom) in pixels."""
    left, top, right, bottom = box
    draw.text((left, top - 34), title, fill="black")
    draw.text((left, top - 18), unit, fill=GREY)
    count = max(1, len(values))
    step = (right - left) / count
    finite = [v for v in values if np.isfinite(v) and v > 0]
    if log:
        top_value = np.log10(max(finite) * 10.0) if finite else 1.0
        floor = np.log10(min(finite) / 3.0) if finite else 0.0

        def height(value):
            if not np.isfinite(value) or value <= 0:
                return 0.0
            span = max(1e-9, top_value - floor)
            return (bottom - top) * max(
                0.0, (np.log10(value) - floor) / span)
    else:
        top_value = max(finite) * 1.35 if finite else 1.0

        def height(value):
            if not np.isfinite(value):
                return 0.0
            return (bottom - top) * max(0.0, value / top_value)

    draw.line([left, bottom, right, bottom], fill="black")
    for index, value in enumerate(values):
        x0 = left + step * index + step * 0.18
        x1 = left + step * (index + 1) - step * 0.18
        bar = height(value)
        draw.rectangle([x0, bottom - bar, x1, bottom], fill=colors[index],
                       outline="black")
        for line, text in enumerate(texts[index].split("\n")):
            draw.text((x0, bottom - bar - 16 - 12 * line), text, fill=DARK)
        for line, text in enumerate(labels[index].split("\n")):
            draw.text((x0, bottom + 6 + 12 * line), text, fill="black")


def _profile(draw, box, series, truth, columns, *, title, limit=1.0):
    left, top, right, bottom = box
    draw.text((left, top - 34), title, fill="black")
    draw.text((left, top - 18),
              "shaded = the measured Y dead-band columns; black = regmap-gt "
              "(supervised)", fill=GREY)
    step = (right - left) / max(1, columns)

    def xpos(index):
        return left + step * (index + 0.5)

    def ypos(value):
        middle = (top + bottom) / 2
        return middle - (bottom - top) / 2 * (
            float(np.clip(value, -limit, limit)) / limit)

    for column in DEAD_BANDS:
        if column < columns:
            draw.rectangle([xpos(column) - step / 2, top,
                            xpos(column) + step / 2, bottom],
                           fill=(252, 232, 232))
    for gridline in (-0.5, 0.0, 0.5):
        y = ypos(gridline)
        draw.line([left, y, right, y],
                  fill=(0, 0, 0) if gridline == 0 else (222, 222, 222))
        draw.text((left - 42, y - 6), "%+.2f" % gridline, fill="black")
    draw.text((left - 46, top - 2), "dots", fill=GREY)
    for values, colour, width in series + [(truth, (0, 0, 0), 2)]:
        previous = None
        for index in range(columns):
            value = values[index]
            if value is None or not np.isfinite(value):
                previous = None
                continue
            y = ypos(value)
            if previous is not None:
                draw.line([xpos(index - 1), previous, xpos(index), y],
                          fill=colour, width=width)
            draw.ellipse([xpos(index) - 2, y - 2, xpos(index) + 2, y + 2],
                         fill=colour)
            previous = y
    for column in range(0, columns, 2):
        draw.text((xpos(column) - 6, bottom + 6), str(column), fill="black")
    draw.text((left, bottom + 24), "tile column", fill="black")


def _finite(values):
    return [None if value is None else float(value) for value in values]


def draw(document: dict, path: Path) -> Path:
    full = document["full_sheet"]
    reach = document["reach"]
    per_probe = document.get("per_probe_precision") or {}
    modes = [name for name in document["modes"] if name in full]
    certified = document["counts"]["fully_certified_tiles"]
    columns = int(document["inputs"]["tiles_yx"][1])

    width, height = 1560, 1060
    image = Image.new("RGB", (width, height), "white")
    draw_on = ImageDraw.Draw(image)
    draw_on.text((14, 10),
                 "E5b -- probe density for the certified-probe pass: what "
                 "each density costs and what it buys", fill="black")
    inputs = document["inputs"]
    state_sha = inputs["state_sha256"][:12]
    draw_on.text((14, 26),
                 f"sheet I, W6 qualification state ({state_sha}..., "
                 f"{inputs.get('close_status', '')}), "
                 f"capture {inputs['capture_ordinal']}/3 at "
                 f"{inputs['capture_dpi']:g} dpi, lane {inputs['lane_id']} "
                 f"({inputs['lane_px_per_cell']:g} px/cell); PROBES ONLY, no "
                 f"anchors; truth = regmap-gt supervised", fill=DARK)
    counts = document["counts"]
    draw_on.text((14, 42),
                 f"{counts['windows']} windows of {counts['placements']} "
                 f"placements = {counts['label_only_windows']} label-only + "
                 f"{counts['mixed_windows']} mixed, ALL offered to the pass "
                 f"(--window-kind {document['window_kind']}); {certified} "
                 f"fully-certified tiles of {counts['tiles_total']}; window "
                 f"shape {counts['window_shape_yx_cells']} cells", fill=DARK)

    # -- panel 1: cost over the whole sheet ------------------------------
    _bars(draw_on, (80, 120, 740, 400),
          [full[key]["wall_seconds"] for key in modes],
          [SHORT[key] for key in modes],
          [f"{full[key]['n_probes']:,} probes\n"
           f"{full[key]['ms_per_probe']:.2f} ms each" for key in modes],
          [COLOR[key] for key in modes],
          title="COST of one (capture, lane) pass over the whole sheet",
          unit="wall seconds, log scale", log=True)

    # -- panel 2: reach --------------------------------------------------
    _bars(draw_on, (860, 120, 1520, 400),
          [reach[key]["n_tiles"] for key in modes],
          [SHORT[key] for key in modes],
          [f"{reach[key]['n_sites']:,} sites\n"
           f"{reach[key]['n_tiles'] / certified:.0%} of certified\n"
           f"+{reach[key]['tiles_reached_only_through_mixed_windows']} "
           f"via mixed" for key in modes],
          [COLOR[key] for key in modes],
          title="REACH -- certified tiles a probe can be placed on at all",
          unit=f"tiles, of {certified} fully certified; "
               f"{document['reach_shared_by_every_mode']} reached by every "
               f"density")

    # -- panel 3: quality ------------------------------------------------
    rows = [
        ("field column profile\nSpearman vs regmap-gt\n(higher better)",
         [full[key]["score"]["dY_rel_x"]["spearman"] for key in modes],
         "%.4f"),
        ("field bin coverage\n(higher better)",
         [float(np.mean(list(full[key]["coverage_by_plane"].values())))
          for key in modes], "%.3f"),
        ("per-TILE field residual\nMAD dots (LOWER better)",
         [full[key]["tile_residual_vs_gt"]["mad"] for key in modes], "%.3f"),
    ]
    if per_probe:
        rows.append((
            "per-PROBE residual\nMAD dots (matched tiles, LOWER better)",
            [per_probe.get(key, {}).get(
                "residual_vs_regmap_gt", {}).get("mad", float("nan"))
             for key in modes], "%.3f"))
    left, top, right, bottom = 80, 500, 740, 830
    draw_on.text((left, top - 34),
                 "FIELD QUALITY -- each metric scaled to its own maximum",
                 fill="black")
    draw_on.text((left, top - 18),
                 "read the printed number, not the bar length: the bars only "
                 "compare densities within one metric", fill=GREY)
    lane = (bottom - top) / len(rows)
    for index, (label, values, fmt) in enumerate(rows):
        y = top + lane * index + 6
        span = max([abs(v) for v in values if np.isfinite(v)] + [1e-9])
        for slot, (value, key) in enumerate(zip(values, modes)):
            bar = (right - left - 300) * (
                abs(value) / span if np.isfinite(value) else 0.0)
            y0 = y + 13 * slot
            draw_on.rectangle([left + 290, y0, left + 290 + bar, y0 + 10],
                              fill=COLOR[key], outline="black")
            draw_on.text((left + 296 + bar, y0 - 1), fmt % value, fill=DARK)
        for line, text in enumerate(label.split("\n")):
            draw_on.text((left, y + 12 * line), text, fill="black")

    # -- panel 4: the column profiles ------------------------------------
    _profile(draw_on, (900, 500, 1520, 780),
             [(_finite(full[key]["profile"]["dY_rel_x"]), COLOR[key], 1)
              for key in modes],
             _finite(document["regmap_gt_profile"]["dY_rel_x"]), columns,
             title="the field's dY_rel_x per column ("
                   + ", ".join(f"{SHORT[k].split()[0]}" for k in modes) + ")")

    # -- the summary table -----------------------------------------------
    y = 880
    draw_on.text((80, y),
                 "PER DENSITY -- and the plane-COMMON residual per window "
                 "(MEASURED, never applied: that is P5 writer work)",
                 fill="black")
    header = ("density", "tiles", "sites", "template cells", "wall s",
              "ms/probe", "tile MAD", "Spearman", "pose |d| med/p90")
    columns_x = (80, 260, 340, 430, 570, 650, 750, 850, 960)
    for x, text in zip(columns_x, header):
        draw_on.text((x, y + 22), text, fill=GREY)
    for index, key in enumerate(modes):
        row = full[key]
        pose = row.get("window_pose_residual") or {}
        cells = reach[key]["template_cells"]
        line = y + 40 + 18 * index
        cells_text = (
            f"{cells.get('median', 0):,.0f}"
            if cells.get("n") else "-")
        pose_text = (
            f"{pose['magnitude_dots']['median']:.3f}/"
            f"{pose['magnitude_dots']['p90']:.3f}"
            if pose.get("windows") else "-")
        for x, text in zip(columns_x, (
                SHORT[key], f"{reach[key]['n_tiles']:,}",
                f"{row['n_probe_sites']:,}", cells_text,
                f"{row['wall_seconds']:.1f}", f"{row['ms_per_probe']:.2f}",
                f"{row['tile_residual_vs_gt']['mad']:.3f}",
                f"{row['score']['dY_rel_x']['spearman']:+.4f}", pose_text)):
            draw_on.text((x, line), text, fill=COLOR[key])
    image.save(path)
    return path


__all__ = ["draw"]

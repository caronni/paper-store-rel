"""PIL figures for the W0 instrument (matplotlib is not in this env).

Two artifacts, both to ``scratch/plane-fields/`` (the figures-in-scratch
rule):

* ``plane-fields-<sheet>.png`` — the per-plane translation-delta field
  over tile space, drawn as the exaggerated quiver of
  docs/PLANE-FIELDS.md §6.2 W5 (C cyan / M magenta / Y gold), plus the
  Y-relative panel that is the measured sheet-I mechanism;
* ``comparison-<sheet>.png`` — per-column Y dx, this instrument against
  the supervised regmap-gt profile.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

PLANE_COLORS = {"C": (0, 160, 200), "M": (200, 40, 160),
                "Y": (200, 150, 0), "Yrel": (120, 90, 200)}


def _grid_geometry(width: int, height: int, tiles_yx: tuple[int, int],
                   left: int, top: int, right: int, bottom: int):
    rows, columns = tiles_yx
    cell_w = (width - left - right) / columns
    cell_h = (height - top - bottom) / rows
    return cell_w, cell_h


def draw_field(path, samples, smooth, tiles_yx, *, exaggeration: float,
               threshold_dots: float, title: str) -> None:
    """Four panels: C, M, Y (delta vs committed pose) and Y - (C+M)/2.

    ``smooth`` maps panel key -> (dx, dy) arrays over the tile grid, NaN
    where the smoother has no support.  ``exaggeration`` is in TILE
    WIDTHS PER PRINT DOT: an arrow one tile long means a one-dot delta
    at exaggeration 1.
    """
    rows, columns = tiles_yx
    panels = ("C", "M", "Y", "Yrel")
    pad_l, pad_t, pad_r, pad_b = 46, 104, 24, 56
    panel_w, panel_h = 420, 700
    width = len(panels) * panel_w
    height = panel_h + 10
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 8), title, fill="black")
    draw.text((10, 24),
              "arrow = per-plane translation delta vs the committed pose, in "
              "print dots, drawn at x%.1f tile widths per dot;  shaded tile = "
              "|delta| >= %.2f dot" % (exaggeration, threshold_dots),
              fill=(80, 80, 80))
    draw.text((10, 40),
              "tile space: 53 rows x 37 columns, page down / page right; "
              "field = Gaussian-weighted local mean of the certified-tile "
              "probes", fill=(80, 80, 80))

    cell_w, cell_h = _grid_geometry(panel_w, panel_h, tiles_yx,
                                   pad_l, pad_t, pad_r, pad_b)
    for index, key in enumerate(panels):
        x_origin = index * panel_w
        colour = PLANE_COLORS[key]
        label = ("Y - (C+M)/2  (the plane-differential field)"
                 if key == "Yrel" else f"{key} plane vs committed pose")
        draw.text((x_origin + pad_l, 62), label, fill=colour)
        bar_y = 82
        draw.line([x_origin + pad_l, bar_y,
                   x_origin + pad_l + 0.5 * exaggeration * cell_w, bar_y],
                  fill=colour)
        draw.text((x_origin + pad_l + 0.5 * exaggeration * cell_w + 6,
                   bar_y - 6), "= 0.5 dot", fill=(120, 120, 120))
        dx_field, dy_field = smooth[key]
        for tile_y in range(rows):
            for tile_x in range(columns):
                dx = dx_field[tile_y, tile_x]
                dy = dy_field[tile_y, tile_x]
                if not np.isfinite(dx):
                    continue
                cx = x_origin + pad_l + cell_w * (tile_x + 0.5)
                cy = pad_t + cell_h * (tile_y + 0.5)
                if float(np.hypot(dx, dy)) >= threshold_dots:
                    draw.rectangle([cx - cell_w / 2, cy - cell_h / 2,
                                    cx + cell_w / 2, cy + cell_h / 2],
                                   fill=(250, 226, 226))
        for tile_y in range(rows):
            for tile_x in range(columns):
                dx = dx_field[tile_y, tile_x]
                dy = dy_field[tile_y, tile_x]
                if not np.isfinite(dx):
                    continue
                cx = x_origin + pad_l + cell_w * (tile_x + 0.5)
                cy = pad_t + cell_h * (tile_y + 0.5)
                tip_x = cx + dx * exaggeration * cell_w
                tip_y = cy + dy * exaggeration * cell_h
                draw.line([cx, cy, tip_x, tip_y], fill=colour)
                draw.ellipse([tip_x - 1.2, tip_y - 1.2,
                              tip_x + 1.2, tip_y + 1.2], fill=colour)
        draw.rectangle([x_origin + pad_l, pad_t,
                        x_origin + pad_l + cell_w * columns,
                        pad_t + cell_h * rows], outline=(170, 170, 170))
        # measured sample density, as dots on the bottom axis
        counts = samples.get(key)
        if counts is not None:
            for tile_x in range(columns):
                total = int(counts[:, tile_x].sum())
                if not total:
                    continue
                bar = min(1.0, total / max(1.0, counts.sum() / columns))
                bx = x_origin + pad_l + cell_w * (tile_x + 0.5)
                draw.line([bx, pad_t + cell_h * rows + 4,
                           bx, pad_t + cell_h * rows + 4 + 16 * bar],
                          fill=(150, 150, 150))
        draw.text((x_origin + pad_l, pad_t + cell_h * rows + 26),
                  "tile_x (bars: probes per column; gaps = no certificate "
                  "for this plane)", fill=(120, 120, 120))
    image.save(path)


def draw_comparison(path, columns_axis, instrument, instrument_sd, truth,
                    residue, *, title: str, subtitle: str,
                    limit_dots: float = 1.4) -> None:
    """Per-column Y dx: this instrument (solid) vs regmap-gt (dashed)."""
    width, height = 1500, 760
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), title, fill="black")
    draw.text((12, 24), subtitle, fill=(80, 80, 80))
    left, right = 90, width - 30
    count = len(columns_axis)
    step = (right - left) / count

    def xpos(index: float) -> float:
        return left + step * (index + 0.5)

    top, bottom = 70, 300
    for tile_x in range(count):
        bar = (bottom - top) * float(residue[tile_x]) / 53.0
        draw.rectangle([xpos(tile_x) - step * 0.4, bottom - bar,
                        xpos(tile_x) + step * 0.4, bottom],
                       fill=(210, 150, 150))
    draw.line([left, bottom, right, bottom], fill="black")
    draw.text((12, top - 16), "decoder Y residue (failed tiles / 53)",
              fill=(160, 60, 60))

    plot_top, plot_bottom = 360, 700

    def ypos(value: float) -> float:
        middle = (plot_top + plot_bottom) / 2
        return middle - (plot_bottom - plot_top) / 2 * (value / limit_dots)

    for gridline in (-1.0, -0.5, 0.0, 0.5, 1.0):
        y = ypos(gridline)
        draw.line([left, y, right, y],
                  fill=(0, 0, 0) if gridline == 0 else (225, 225, 225))
        draw.text((left - 48, y - 6), "%+.2f" % gridline, fill="black")
    draw.text((left - 78, ypos(1.0) - 22), "print dots", fill="black")

    previous_i = previous_t = None
    for index, tile_x in enumerate(columns_axis):
        value = instrument[index]
        if np.isfinite(value):
            y = ypos(float(np.clip(value, -limit_dots, limit_dots)))
            spread = instrument_sd[index]
            if np.isfinite(spread):
                draw.line([xpos(index),
                           ypos(float(np.clip(value - spread,
                                              -limit_dots, limit_dots))),
                           xpos(index),
                           ypos(float(np.clip(value + spread,
                                              -limit_dots, limit_dots)))],
                          fill=(200, 200, 235))
            draw.ellipse([xpos(index) - 3, y - 3, xpos(index) + 3, y + 3],
                         fill=(30, 60, 200))
            if previous_i is not None:
                draw.line([xpos(index - 1), previous_i, xpos(index), y],
                          fill=(30, 60, 200), width=2)
            previous_i = y
        else:
            previous_i = None
        truth_value = truth[index]
        if np.isfinite(truth_value):
            y = ypos(float(np.clip(truth_value, -limit_dots, limit_dots)))
            draw.ellipse([xpos(index) - 2, y - 2, xpos(index) + 2, y + 2],
                         fill=(200, 100, 20))
            if previous_t is not None:
                draw.line([xpos(index - 1), previous_t, xpos(index), y],
                          fill=(200, 100, 20))
            previous_t = y
        else:
            previous_t = None
        if tile_x % 2 == 0:
            draw.text((xpos(index) - 6, plot_bottom + 8), str(tile_x),
                      fill="black")
    draw.text((left + 8, plot_top + 6),
              "blue = field_from_certs (certificates + committed poses)   |   "
              "orange = regmap-gt (page GT + fitted global affine)",
              fill=(60, 60, 60))
    draw.text((left, plot_bottom + 26), "tile column (tile_x)", fill="black")
    image.save(path)


__all__ = ["draw_comparison", "draw_field"]

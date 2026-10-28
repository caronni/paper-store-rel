"""PIL figures for the swim pilot (matplotlib is not in this env).

Two artifacts under ``scratch/plane-fields/swim-pilot/``:

* ``offsets-<tag>.png`` — per target, the three independent offset
  estimates for the swum plane against the supervised regmap-gt column
  expectation, with the CERTIFICATION PLATEAU drawn as a band wherever
  the swim found one: an estimator is useful exactly when it lands
  inside that band;
* ``cliff-<tag>.png`` — the money shot: decode outcome versus sampling
  offset.  The certificate gate is the marker fill, the likelihood
  surrogate is the curve, and (where the closed volume gave us truth)
  the ground-truth cell BER rides the same axis.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

BG = (255, 255, 255)
INK = (30, 30, 30)
GREY = (120, 120, 120)
GRID = (222, 222, 222)
BAND = (198, 232, 205)
SERIES = {
    "neighbour": (0, 130, 190),
    "swim": (200, 60, 40),
    "own": (30, 150, 90),
    "regmap": (150, 120, 200),
}
BER = (90, 90, 200)


def _frame(draw, box, xlim, ylim, *, xlabel, ylabel, title, ticks=5):
    left, top, right, bottom = box
    draw.text((left - 46, top - 30), title, fill=INK)
    draw.text((left - 46, top - 17), ylabel, fill=GREY)
    draw.text((left, bottom + 18), xlabel, fill=GREY)
    draw.rectangle((left, top, right, bottom), outline=INK)

    def to_px(x, y):
        fx = (x - xlim[0]) / ((xlim[1] - xlim[0]) or 1.0)
        fy = (y - ylim[0]) / ((ylim[1] - ylim[0]) or 1.0)
        return (left + fx * (right - left), bottom - fy * (bottom - top))

    for value in np.linspace(ylim[0], ylim[1], ticks):
        py = to_px(xlim[0], value)[1]
        draw.line((left, py, right, py), fill=GRID)
        draw.text((left - 44, py - 5), f"{value:+.2f}", fill=GREY)
    return to_px


def _marker(draw, point, colour, *, filled: bool, size: int = 4,
            clipped: bool = False):
    x, y = point
    box = (x - size, y - size, x + size, y + size)
    if clipped:
        draw.polygon([(x, y), (x - size, y + size * (1 if y < 0 else -1)),
                      (x + size, y + size * (1 if y < 0 else -1))],
                     outline=colour)
        return
    if filled:
        draw.ellipse(box, fill=colour, outline=colour)
    else:
        draw.ellipse(box, outline=colour)


def _span(values, floor: float = 0.6) -> float:
    """Robust half-range: outliers are clipped, not allowed to set scale."""
    finite = [abs(float(v)) for v in values
              if v is not None and np.isfinite(v)]
    if not finite:
        return floor
    return max(floor, 1.15 * float(np.percentile(finite, 85)))


def draw_offsets(path, rows, *, title: str) -> None:
    """One column per target; one marker per estimator, in page dots."""
    width = max(820, 66 * len(rows) + 220)
    height = 440
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    keys = ("neighbour_dx", "swim_dx", "own_dx", "regmap_dx")
    span = _span([row.get(key) for row in rows for key in keys])
    box = (86, 62, width - 160, height - 74)
    to_px = _frame(draw, box, (-0.5, len(rows) - 0.5), (-span, span),
                   xlabel="target  tile_y,tile_x / stream",
                   ylabel="dx (print dots, page axis)", title=title)
    for index, row in enumerate(rows):
        px = to_px(index, 0.0)[0]
        plateau = row.get("plateau_dx") or ()
        if plateau:
            low, high = min(plateau), max(plateau)
            y_hi = to_px(index, min(high + 0.0625, span))[1]
            y_lo = to_px(index, max(low - 0.0625, -span))[1]
            draw.rectangle((px - 22, y_hi, px + 22, y_lo), fill=BAND)
    zero_y = to_px(0, 0.0)[1]
    draw.line((box[0], zero_y, box[2], zero_y), fill=INK)
    for index, row in enumerate(rows):
        px = to_px(index, 0.0)[0]
        draw.line((px, box[1], px, box[3]), fill=GRID)
        draw.text((px - 26, box[3] + 4),
                  f"{row['tile_y']},{row['tile_x']}{row['stream']}", fill=INK)
        if row.get("role", "target") != "target":
            draw.text((px - 12, box[3] + 16), "ctrl", fill=GREY)
        for key, series in zip(keys, SERIES):
            value = row.get(key)
            if value is None or not np.isfinite(value):
                continue
            clipped = abs(float(value)) > span
            shown = float(np.clip(value, -span, span))
            _marker(draw, to_px(index, shown), SERIES[series],
                    filled=(series != "regmap"),
                    size=5 if series == "swim" else 4, clipped=clipped)
    legend_x = width - 150
    for offset, (series, colour) in enumerate(SERIES.items()):
        y = 74 + 18 * offset
        _marker(draw, (legend_x + 6, y), colour, filled=(series != "regmap"))
        draw.text((legend_x + 18, y - 6), series, fill=INK)
    draw.rectangle((legend_x, 74 + 18 * len(SERIES) + 4, legend_x + 12,
                    74 + 18 * len(SERIES) + 14), fill=BAND)
    draw.text((legend_x + 18, 74 + 18 * len(SERIES) + 2),
              "certified band", fill=INK)
    draw.text((86, height - 42),
              "filled = estimator, hollow = supervised regmap-gt column "
              "(Y minus the C/M mean, converted to print dots); triangle = "
              "clipped to the axis", fill=GREY)
    draw.text((86, height - 28),
              "green band = the offsets at which the ORDINARY certificate "
              "gate fired; an estimator is useful when it lands inside it",
              fill=GREY)
    image.save(path)


def draw_cliff(path, curves, *, title: str) -> None:
    """Surrogate (and truth BER) versus offset, with the gate as fill."""
    count = max(1, len(curves))
    height = 120 + 210 * count
    width = 900
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.text((30, 14), title, fill=INK)
    draw.text((30, 30),
              "red = mean |LLR| surrogate (left scale); filled+ringed = the "
              "certificate gate FIRED; blue = ground-truth cell BER "
              "(right scale)", fill=GREY)
    for index, curve in enumerate(curves):
        top = 92 + 210 * index
        box = (86, top, width - 96, top + 132)
        offsets = np.asarray(curve["offsets"], np.float64)
        scores = np.asarray(curve["scores"], np.float64)
        finite = scores[np.isfinite(scores)]
        low = float(finite.min()) if finite.size else 0.0
        high = float(finite.max()) if finite.size else 1.0
        pad = 0.10 * ((high - low) or 1.0)
        to_px = _frame(
            draw, box, (offsets.min(), offsets.max()), (low - pad, high + pad),
            xlabel="per-plane sampling offset delta-x  (print dots, page axis)",
            ylabel="mean |LLR|", title=curve["label"])
        for name, key in (("neighbour", "neighbour_dx"),
                          ("own", "own_dx"), ("regmap", "regmap_dx")):
            value = curve.get(key)
            if value is None or not np.isfinite(value):
                continue
            if not offsets.min() <= value <= offsets.max():
                continue
            px = to_px(float(value), low)[0]
            draw.line((px, box[1], px, box[3]), fill=SERIES[name])
            draw.text((px + 2, box[1] + 2), name[:4], fill=SERIES[name])
        points = [to_px(x, y) for x, y in zip(offsets, scores)]
        draw.line(points, fill=SERIES["swim"], width=2)
        for point, certified in zip(points, curve["certified"]):
            _marker(draw, point, SERIES["swim"], filled=bool(certified),
                    size=6 if certified else 3)
            if certified:
                draw.ellipse((point[0] - 9, point[1] - 9,
                              point[0] + 9, point[1] + 9), outline=INK)
        bers = curve.get("bers")
        if bers:
            values = np.asarray([np.nan if v is None else v for v in bers],
                                np.float64)
            good = values[np.isfinite(values)]
            if good.size:
                blo, bhi = float(good.min()), float(good.max())
                bpad = 0.12 * ((bhi - blo) or 1.0)

                def ber_px(x, y):
                    fx = ((x - offsets.min())
                          / ((offsets.max() - offsets.min()) or 1.0))
                    fy = ((y - (blo - bpad))
                          / (((bhi + bpad) - (blo - bpad)) or 1.0))
                    return (box[0] + fx * (box[2] - box[0]),
                            box[3] - fy * (box[3] - box[1]))

                line = [ber_px(x, y) for x, y in zip(offsets, values)
                        if np.isfinite(y)]
                if len(line) > 1:
                    draw.line(line, fill=BER, width=2)
                for value in (blo, bhi):
                    py = ber_px(offsets.min(), value)[1]
                    draw.text((box[2] + 4, py - 5), f"{value:.3f}", fill=BER)
        for value in np.linspace(offsets.min(), offsets.max(), 9):
            px = to_px(value, low)[0]
            draw.text((px - 14, box[3] + 4), f"{value:+.2f}", fill=GREY)
        note = curve.get("note")
        if note:
            draw.text((box[0] + 8, box[1] + 6), note, fill=INK)
    image.save(path)


__all__ = ["draw_cliff", "draw_offsets"]

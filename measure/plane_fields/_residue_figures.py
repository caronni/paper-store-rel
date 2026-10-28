"""PIL figures for the P2 measurements (matplotlib is not in this env).

* ``e1-refit.png`` — per tile, the union cell error of the FROZEN arm
  next to the RECUT-BINS REFIT arm, with the measured decode gate drawn
  as a band and certification called out on the bar.  The question the
  figure has to answer at a glance: does recutting the detector at the
  corrected geometry move the dead band, and does anything cross?
* ``e2-directional.png`` — the four downstream-neighbour strata per
  group, with the UPSTREAM strata drawn hollow beside them.  A real
  anisotropic leakage shows as a downstream/upstream split that the
  controls do not have.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

#: PIL's built-in bitmap font is 6 px wide and cannot render an em dash;
#: a real face is worth the two lines.  Missing faces fall back silently.
_FACES = ("/System/Library/Fonts/Supplemental/Arial.ttf",
          "/System/Library/Fonts/Helvetica.ttc",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _font(size: int):
    for path in _FACES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


BG = (255, 255, 255)
INK = (30, 30, 30)
GREY = (120, 120, 120)
GRID = (226, 226, 226)
GATE = (198, 232, 205)
FROZEN = (110, 130, 200)
REFIT = (205, 95, 55)
UPSTREAM = (170, 170, 170)
STRATUM_COLOUR = {"none": (140, 140, 140), "C": (0, 140, 190),
                  "M": (200, 60, 140), "both": (90, 70, 160)}
GROUP_ORDER = ("dead_band", "reproduction_control", "clear_band",
               "certified_reference")


def _axes(draw, box, ylim, *, title, ylabel, ticks=6, percent=True):
    left, top, right, bottom = box
    draw.text((left - 56, top - 38), title, fill=INK, font=_font(15))
    draw.text((left - 56, top - 20), ylabel, fill=GREY, font=_font(12))
    draw.rectangle((left, top, right, bottom), outline=INK)

    def to_y(value):
        fraction = (value - ylim[0]) / ((ylim[1] - ylim[0]) or 1.0)
        return bottom - fraction * (bottom - top)

    for value in np.linspace(ylim[0], ylim[1], ticks):
        py = to_y(value)
        draw.line((left, py, right, py), fill=GRID)
        draw.text((left - 52, py - 7),
                  f"{100 * value:5.1f}%" if percent else f"{value:5.2f}",
                  fill=GREY, font=_font(11))
    return to_y


def draw_e1(path, rows, *, gate: float) -> None:
    rows = [row for row in rows if "error" not in row
            and row.get("frozen", {}).get("union_ber") is not None]
    if not rows:
        return
    width, height = max(1180, 130 + 118 * len(rows)), 500
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    box = (82, 62, width - 24, height - 106)
    values = [row["frozen"]["union_ber"] for row in rows] + [
        row.get("refit", {}).get("union_ber") for row in rows]
    top = max([v for v in values if v is not None] + [gate]) * 1.18
    to_y = _axes(draw, box, (0.0, top),
                 title=("E1: recut-bins refit vs the frozen detector, at "
                        "the supervised affine + BER polish"),
                 ylabel="union cell error, 3 captures, against printed truth")
    draw.rectangle((box[0] + 1, to_y(gate), box[2] - 1, box[3]), fill=GATE)
    draw.line((box[0], to_y(gate), box[2], to_y(gate)), fill=(110, 160, 120))
    step = (box[2] - box[0]) / len(rows)
    for position, row in enumerate(rows):
        centre = box[0] + step * (position + 0.5)
        for offset, key, colour in ((-0.22, "frozen", FROZEN),
                                    (0.22, "refit", REFIT)):
            value = row.get(key, {}).get("union_ber")
            if value is None:
                continue
            x0 = centre + offset * step - 0.17 * step
            x1 = centre + offset * step + 0.17 * step
            draw.rectangle((x0, to_y(value), x1, box[3]), fill=colour)
            label_y = to_y(value) - 15
            if row[key].get("certified"):
                draw.text((x0, label_y), "CERT", fill=(20, 120, 40),
                          font=_font(11))
                label_y -= 14
            draw.text((x0 - 2, label_y), f"{100 * value:.2f}", fill=INK,
                      font=_font(11))
        draw.text((centre - 18, box[3] + 8),
                  f"{row['tile_y']},{row['tile_x']}", fill=INK, font=_font(13))
        draw.text((centre - 20, box[3] + 25),
                  "dead" if row["band"] == "dead" and row["role"] == "target"
                  else "control", fill=GREY, font=_font(11))
        arms = [value or "?" for value in
                row.get("frozen", {}).get("arm_by_capture", {}).values()]
        # A COUNT, not a sequence: this figure has no capture order to
        # attach the arms to, and the table beside it does.
        draw.text((centre - 34, box[3] + 40),
                  "frozen arms " + " ".join(
                      f"{arms.count(name)}x{name}"
                      for name in sorted(set(arms))), fill=GREY,
                  font=_font(10))
    for offset, colour, text in (
            (0, FROZEN, "frozen detector: one fit at delta = 0, A5 context "
                        "bins cut there"),
            (370, REFIT, "refit: the whole region re-fitted with this tile "
                         "sampled at the correction"),
            (750, GATE, f"measured decode gate {100 * gate:.2f}% "
                        "(the band, not a threshold)")):
        draw.rectangle((box[0] + offset, height - 44,
                        box[0] + offset + 12, height - 33), fill=colour,
                       outline=GREY)
        draw.text((box[0] + offset + 18, height - 45), text, fill=INK,
                  font=_font(11))
    image.save(path)


def draw_e2(path, summary: dict, *, key: str = "ber_global") -> None:
    groups = [name for name in GROUP_ORDER
              if name in summary.get("downstream", {})]
    if not groups:
        return
    names = ("none", "C", "M", "both")
    width, height = 150 + 250 * len(groups), 490
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    box = (82, 62, width - 24, height - 106)
    values = [summary[label][group][name][key]
              for label in ("downstream", "upstream")
              for group in groups for name in names
              if summary[label][group][name][key] is not None]
    if not values:
        return
    to_y = _axes(draw, box, (0.0, max(values) * 1.20),
                 title=("E2: Y cell error under ONE tile-wide threshold, by "
                        "the DOWNSTREAM neighbour's C/M ink "
                        "(hollow bar = the upstream falsifier)"),
                 ylabel="Y cell error at a stratum-blind threshold")

    def show(value, digits=2, plus=True):
        if value is None:
            return "n/a"
        return f"{value:+.{digits}f}" if plus else f"{value:.{digits}f}"

    step = (box[2] - box[0]) / len(groups)
    for position, group in enumerate(groups):
        base = box[0] + step * position
        span = (step - 34) / len(names)
        for index, name in enumerate(names):
            slot = base + 18 + index * span
            down = summary["downstream"][group][name][key]
            up = summary["upstream"][group][name][key]
            if down is not None:
                draw.rectangle((slot, to_y(down), slot + span * 0.44, box[3]),
                               fill=STRATUM_COLOUR[name])
                draw.text((slot - 3, to_y(down) - 15), f"{100 * down:.1f}",
                          fill=INK, font=_font(11))
            if up is not None:
                draw.rectangle(
                    (slot + span * 0.5, to_y(up), slot + span * 0.94, box[3]),
                    outline=STRATUM_COLOUR[name], fill=None)
                draw.text((slot + span * 0.47, to_y(up) - 15),
                          f"{100 * up:.1f}", fill=GREY, font=_font(10))
            draw.text((slot + span * 0.28, box[3] + 8), name, fill=GREY,
                      font=_font(12))
        rows = summary.get("ink_gap_pp", {}).get(group, {})
        draw.text((base + 18, box[3] + 28),
                  f"{group}   {rows.get('n_tiles', '?')} tiles / "
                  f"{rows.get('n_rows', '?')} rows", fill=INK, font=_font(12))
        draw.text((base + 18, box[3] + 45),
                  "ink-gap  downstream "
                  f"{show(rows.get('downstream_ber_global_gap_inked_minus_none'))}"
                  " pp   upstream "
                  f"{show(rows.get('upstream_ber_global_gap_inked_minus_none'))}"
                  " pp", fill=GREY, font=_font(11))
        draw.text((base + 18, box[3] + 60),
                  "error lift   inked "
                  f"{show(rows.get('downstream_lift_inked_mean'), 3, False)}"
                  "   none "
                  f"{show(rows.get('downstream_lift_none'), 3, False)}",
                  fill=GREY, font=_font(11))
        if position:
            draw.line((base, box[1], base, box[3]), fill=GREY)
    image.save(path)


__all__ = ["draw_e1", "draw_e2"]

"""PIL figures for E9 (matplotlib is not in this env).

One artifact, `e9-k-<lane>.png`, four panels:

  A  the page's per-tile cell BER under arm R (the incumbent recipe),
     with the 21 uncertified tiles ringed — this is the banding, drawn
     from the receiver's own evidence rather than from the print;
  B  the same page under the best halo arm MINUS arm R, diverging, so a
     local/global calibration effect that had any spatial structure
     would appear here as structure;
  C  the complete residue: 21 tiles x 5 arms, cell BER, grouped by the
     e029 failure geography (col 0 / col 36 / row 42 / singleton);
  D  every window's fitted decision threshold t50 under arm W minus the
     page-global t50 of arm G, drawn at the window's cell-space centre —
     the toner field as the FIT sees it.
"""
from __future__ import annotations

from ast import literal_eval

import numpy as np
from PIL import Image, ImageDraw

BACKGROUND = (18, 18, 20)
INK = (232, 232, 236)
MUTED = (150, 150, 158)
RING = (255, 214, 64)


def _heat(value: float, lo: float, hi: float) -> tuple[int, int, int]:
    """Sequential dark-blue -> yellow ramp for a rate in [lo, hi]."""
    if not np.isfinite(value):
        return (60, 60, 66)
    t = float(np.clip((value - lo) / max(hi - lo, 1e-9), 0.0, 1.0))
    stops = ((0.0, (16, 32, 84)), (0.35, (36, 120, 140)),
             (0.7, (190, 170, 60)), (1.0, (250, 240, 170)))
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = (t - t0) / max(t1 - t0, 1e-9)
            return tuple(int(round(a + (b - a) * f))
                         for a, b in zip(c0, c1))       # type: ignore
    return stops[-1][1]


def _diverge(value: float, span: float) -> tuple[int, int, int]:
    """Blue (better) / red (worse) around zero."""
    if not np.isfinite(value):
        return (60, 60, 66)
    t = float(np.clip(value / max(span, 1e-9), -1.0, 1.0))
    if t < 0:
        f = -t
        return (int(28 + 20 * (1 - f)), int(60 + 100 * f), int(90 + 150 * f))
    return (int(90 + 160 * t), int(60 + 30 * (1 - t)), int(50 + 20 * (1 - t)))


def _grid(draw: ImageDraw.ImageDraw, values: np.ndarray, x0: int, y0: int,
          cell: int, colour, *, ring: set[tuple[int, int]] = frozenset()):
    rows, columns = values.shape
    for ty in range(rows):
        for tx in range(columns):
            px = x0 + tx * cell
            py = y0 + ty * cell
            draw.rectangle((px, py, px + cell - 1, py + cell - 1),
                           fill=colour(float(values[ty, tx])))
            if (ty, tx) in ring:
                draw.rectangle((px, py, px + cell - 1, py + cell - 1),
                               outline=RING)
    draw.rectangle((x0 - 1, y0 - 1, x0 + columns * cell,
                    y0 + rows * cell), outline=MUTED)


def _colourbar(draw, x0, y0, width, height, colour, lo, hi, label):
    for step in range(width):
        value = lo + (hi - lo) * step / max(width - 1, 1)
        draw.line((x0 + step, y0, x0 + step, y0 + height),
                  fill=colour(value))
    draw.rectangle((x0, y0, x0 + width - 1, y0 + height), outline=MUTED)
    draw.text((x0, y0 + height + 4), f"{lo:g}", fill=MUTED)
    draw.text((x0 + width - 26, y0 + height + 4), f"{hi:g}", fill=MUTED)
    draw.text((x0, y0 - 14), label, fill=INK)


def _page_matrix(page_ber: dict, tiles_yx) -> np.ndarray:
    out = np.full(tuple(tiles_yx), np.nan)
    for key, (observed, wrong) in page_ber.items():
        _page, ty, tx = literal_eval(key)
        out[ty, tx] = 100.0 * wrong / observed if observed else np.nan
    return out


def draw_lane(path, lane_report, residue, tiles_yx, arms, *,
              group_of, halo_arm: str = "H2") -> None:
    tiles_y, tiles_x = tiles_yx
    cell = 12
    left = 46
    top = 96
    gap = 60
    grid_w = tiles_x * cell
    grid_h = tiles_y * cell
    panel_c_w = 470
    width = left + grid_w + gap + grid_w + gap + panel_c_w + 40
    panel_d_top = top + grid_h + 90
    height = panel_d_top + grid_h + 60
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    lane_id = lane_report["lane_id"]
    draw.text((left, 18), "E9 (K instance): LOCAL vs PAGE-GLOBAL calibration, "
                          "additive attempts", fill=INK)
    draw.text((left, 36), f"e029 c2-r0700@3392x2368 / HP M281 / Canon 4800 grey / "
                          f"lane {lane_id} / complete residue "
                          f"({len(residue)} uncertified tiles)", fill=MUTED)

    base = _page_matrix(lane_report["arms"]["R"]["page_ber"], tiles_yx)
    halo = _page_matrix(lane_report["arms"][halo_arm]["page_ber"], tiles_yx)
    ring = {(entry[1], entry[2]) for entry in residue}

    draw.text((left, top - 30), "A - arm R (incumbent) cell BER %", fill=INK)
    _grid(draw, base, left, top, cell,
          lambda v: _heat(v, 0.0, 12.0), ring=ring)
    _colourbar(draw, left, top + grid_h + 26, grid_w, 10,
               lambda v: _heat(v, 0.0, 12.0), 0, 12, "cell BER %")

    x_b = left + grid_w + gap
    draw.text((x_b, top - 30), f"B - arm {halo_arm} minus arm R (pp)",
              fill=INK)
    _grid(draw, halo - base, x_b, top, cell,
          lambda v: _diverge(v, 2.0), ring=ring)
    _colourbar(draw, x_b, top + grid_h + 26, grid_w, 10,
               lambda v: _diverge(v, 2.0), -2, 2, "dBER pp (blue = better)")

    x_c = x_b + grid_w + gap
    draw.text((x_c, top - 30),
              "C - the complete residue, cell BER % by arm", fill=INK)
    row_h = 20
    col_w = 62
    draw.text((x_c, top - 8), "tile", fill=MUTED)
    for index, arm in enumerate(arms):
        draw.text((x_c + 150 + index * col_w, top - 8), arm, fill=MUTED)
    order = sorted(residue, key=lambda e: (group_of(e), e[1], e[2]))
    previous = None
    y = top + 14
    for entry in order:
        group = group_of(entry)
        if group != previous:
            draw.text((x_c, y + 3), group, fill=RING)
            y += row_h
            previous = group
        draw.text((x_c + 12, y + 4), f"({entry[1]},{entry[2]})", fill=INK)
        values = []
        for arm in arms:
            row = lane_report["arms"][arm]["tiles"][str(tuple(entry))]
            values.append(row.get("ber"))
        finite = [v for v in values if v is not None and v == v]
        best = min(finite) if finite else None
        for index, value in enumerate(values):
            px = x_c + 150 + index * col_w
            if value is None or value != value:
                draw.text((px, y + 4), "   -", fill=MUTED)
                continue
            draw.rectangle((px - 3, y, px + col_w - 10, y + row_h - 4),
                           fill=_heat(100 * value, 0.0, 26.0))
            colour = (10, 10, 12) if 100 * value > 14 else INK
            draw.text((px, y + 4), f"{100 * value:5.2f}", fill=colour)
            if best is not None and value == best:
                draw.rectangle((px - 4, y - 1, px + col_w - 9, y + row_h - 3),
                               outline=RING)
        y += row_h
    y += 18
    draw.text((x_c, y), "certificates won, all arms, all tiles: "
              f"{sum(lane_report['arms'][a]['n_certified'] for a in arms)}",
              fill=RING)

    # D — the fitted threshold field.
    y_d = panel_d_top
    draw.text((left, y_d - 20),
              "D - fitted t50 (arm W, window-local) minus t50 (arm G, "
              "page-global), in window score units", fill=INK)
    window_w = np.asarray(
        [[row["centre_yx"][0], row["centre_yx"][1], row["t50"]]
         for row in lane_report["arms"]["W"]["windows"]], np.float64)
    window_g = np.asarray(
        [row["t50"] for row in lane_report["arms"]["G"]["windows"]],
        np.float64)
    delta = window_w[:, 2] - window_g
    span = float(np.nanmax(np.abs(delta))) if delta.size else 1.0
    cells_y = tiles_y * 64
    cells_x = tiles_x * 64
    scale = grid_h / cells_y
    radius = max(3, int(0.22 * scale * 200))
    for (cy, cx, _t), value in zip(window_w, delta):
        px = left + int(cx * grid_w / cells_x)
        py = y_d + int(cy * scale)
        draw.ellipse((px - radius, py - radius, px + radius, py + radius),
                     fill=_diverge(float(value), max(span, 1e-6)))
    draw.text((left, y_d + grid_h + 8),
              f"max |d t50| = {span:.3f}   (red = local threshold above "
              "global, blue = below)", fill=MUTED)
    image.save(path)


__all__ = ["draw_lane"]

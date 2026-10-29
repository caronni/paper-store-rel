"""The FIELD band — DIAG-DESIGN.md §3's reserved slot, now that holo3
has a per-page field producer (`plugins/fields.py`).

Same visual vocabulary as the v1 plane-fields band it is matched to
(user design 2026-08-21, docs/PLANE-FIELDS.md §6.2; the parity record
is src/holo/receiver/docs/conversion_docs/ARMS-2026-08-31.md:69-80): one exaggerated
quiver arrow per plane per block, C/M/Y in the stream hues and staggered
so they never fully overlap, over a mid-grey page body; blocks shaded
where any plane's delta reaches `plane_field.FIELD_NOISE_DOTS` — the
shading IS the dead-band prediction; and a block with no field data
split BY CAUSE, dark green where the tiles are already certified
(nothing left to measure, benign) and black where they are not (the
actionable blind spot).  The exaggeration factor is folded into the
title so the drawn geometry and the printed number are always the same
measurement.

Arrow scale is v1's: a FIXED factor of 50 -- v1's producer published it
as its exaggeration hint (b167b9f:src/holo/receive/color_field.py:209,
`exaggeration_hint`; that receiver was retired 2026-09-05 at 284ae3e)
and docs/PLANE-FIELDS.md §6.2 spells the band's title
as `E FIELD x50` -- clamped by geometry, never lengthened by it —
`min(fixed, cap)`, v1's own expression.  A cap-only
factor normalizes the measurement away: it makes the longest arrow
exactly as long on every sheet whatever the field measures, so the
pane always reads at maximum and two runs cannot be compared by eye.
The clamp is v1's own two blocks per axis (user ruling 2026-08-30, "i
asked for v1 fidelity"): a fidelity port does not get to retune the
constant it ports.  It costs nothing on a real field — the clamp binds
only above ~3.6 dots on sheet-I geometry, where the measured sinusoid
is 0.83 and draws 42 px inside an ~89 px block — because the streaking
this pane used to show came from the SATURATING factor, which normalised
every field to the cap, and not from the cap itself.  The title always
prints the factor that was used.

One thing differs from v1 by construction, not by choice: the
certified-tile overlay is read off the model's own tile states instead
of riding in the event, because holo3's diag model already holds them.

One channel v1 does not have, for the dead-plane sheets this band exists
for (e030, e033): per-plane blindness gets a spatial channel — a block
where one plane has no data while another does is tinted in that plane's
hue across its own third of the block, the payload pane's per-stream
segment vocabulary — because "where is Y blind" is a spatial question
that the all-planes-blind black square cannot answer.

W4 (2026-09-08) gave the band the page field's own two products: the
arrows are one page's field and no lane is named anywhere, and the
per-capture residual energies are a TABLE under the plot, loudest
first, so which footing disagrees with the page is read off the pane.

Split out of `panes.py` for the 1000-line cap, the same reason v1 kept
its field view beside its viewer -- one growing concern should not push
the shared pane module over.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import ImageDraw

from ..data import FieldPlaneRow, FieldSolved
from ..lib import plane_field
from . import panes, readout

TITLE = "FIELD"
BODY_BG = (118, 118, 118)          # mid-grey base (v1 user ruling: amber
                                   # shading read as background and gold
                                   # arrows drowned on anything lighter)
BODY_OUTLINE = (214, 214, 214)     # faint page outline
DIM = (150, 150, 150)              # title colour when there is no field
SHADE = (94, 94, 94)               # at or over the field's noise scale
HOLE = (0, 0, 0)                   # no field data, tiles uncertified
DONE = (26, 62, 44)                # no field data, tiles certified
TITLE_FILL = (238, 240, 243)
TITLE_RULE = (176, 181, 186)
TITLE_TEXT = (35, 40, 45)

#: plane_index 0/1/2 = C/M/Y, the pinned contract; hues are v1's own
#: stream palette so the two viewers read the same.
PLANE_HUE = {"C": (60, 200, 255), "M": (255, 80, 200), "Y": (240, 220, 60)}

STAGGER_PX = 3
#: v1's own fixed exaggeration, 50 (docs/PLANE-FIELDS.md §6.2, `E FIELD
#: x50`).  Arrow length stays proportional to the physical delta, so two
#: runs of two sheets compare by eye; holo3 first shipped without the
#: fixed term and the pane saturated (ARMS-2026-08-31.md:69-73).
FIXED_EXAGGERATION = 50.0
#: The clamp, v1's own two blocks per axis: ruled strict v1 fidelity
#: ('i asked for v1 fidelity', RULINGS-2026-08-31.md:76-82) after a
#: half-block variant was proposed -- restoring v1's value measured
#: byte-identical.  Measured from the block centre; never lengthens.
ARROW_BLOCK_CAP = 2.0
#: a per-plane blind segment, blended this far toward the body grey
BLIND_MIX = 0.72
TITLE_H = 20
TEXT_SIZE = 11
TEXT_STEP = 16
#: The POSE band spells the same 2600 as a literal (`_pose_raster` in
#: panes.py), and the two halves of the bottom row are only flush while
#: they agree: move both or neither.
BAND_MAX_WIDTH = 2600


def draw_arrow(draw: ImageDraw.ImageDraw, origin: tuple[float, float],
               end: tuple[float, float],
               colour: tuple[int, int, int]) -> None:
    """One quiver arrow: a shaft plus a short two-stroke head."""
    x0, y0 = origin
    x1, y1 = end
    draw.line((x0, y0, x1, y1), fill=colour)
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    head = min(4.0, length)
    px, py = -uy, ux
    draw.line((x1, y1, x1 - ux * head + px * head * 0.5,
               y1 - uy * head + py * head * 0.5), fill=colour)
    draw.line((x1, y1, x1 - ux * head - px * head * 0.5,
               y1 - uy * head - py * head * 0.5), fill=colour)


def exaggeration(measured: tuple[tuple[FieldPlaneRow, np.ndarray,
                                       np.ndarray, np.ndarray], ...],
                 block_w: float, block_h: float,
                 fixed: float = FIXED_EXAGGERATION) -> float:
    """The factor every arrow is drawn at: `min(fixed, clamp)`, v1's own
    expression of it.

    The fixed factor is what makes the drawing a MEASUREMENT — the same
    delta draws the same length on every sheet — and the clamp only ever
    shortens it, per axis against that axis' OWN block dimension, so a
    field that is mostly x (the measured registration sinusoid is) is
    shortened by an x outlier rather than by the grid.  Arrows stay
    isotropic in pixels (one factor scales both components), so the drawn
    direction is the measured direction.  Deliberately an illustration:
    there is no dots-per-pixel physical claim.
    """
    widest = tallest = 0.0
    for _row, _blocks, deltas, _magnitudes in measured:
        if deltas.size:
            widest = max(widest, float(np.abs(deltas[:, 0]).max()))
            tallest = max(tallest, float(np.abs(deltas[:, 1]).max()))
    caps = [ARROW_BLOCK_CAP * span / delta
            for span, delta in ((block_w, widest), (block_h, tallest))
            if delta > 0.0]
    return min([fixed] + caps)


def _live_blocks(row: FieldPlaneRow
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """This plane's (block index pairs, deltas, |delta|) where it has data.

    A non-finite delta — a degenerate solve — counts as NO data rather
    than as a delta: it is not something to draw an arrow from, and the
    block is honestly a blind spot.  The magnitude rides along from the
    producer's own pooling, never `hypot` of the pooled vector, which is
    a different statistic.
    """
    grid = np.asarray(row.delta_grid_dots_xy, np.float64)
    live = np.asarray(row.has_data, bool) & np.isfinite(grid).all(axis=-1)
    magnitude = np.asarray(row.magnitude_grid_dots, np.float64)
    ys, xs = np.nonzero(live)
    return (np.stack((ys, xs), axis=1), grid[live], magnitude[live])


def _mix(colour: tuple[int, int, int], toward_body: float
         ) -> tuple[int, int, int]:
    """`colour` blended `toward_body` of the way into the band's grey."""
    share = min(1.0, max(0.0, float(toward_body)))
    return tuple(int(round(c * (1.0 - share) + b * share))
                 for c, b in zip(colour, BODY_BG))


def _blind_blocks(mine: set[tuple[int, int]],
                  covered: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Blocks another plane measured and this one did not.

    Blocks NO plane reached are the band's black holes and stay whole;
    this channel is the per-plane story the union cannot tell — which is
    the dead-plane story (e030's Y, e033's dead bands).
    """
    return covered - mine


def _segment(box_xyxy: tuple[int, int, int, int], index: int,
             total: int) -> tuple[int, int, int, int]:
    """`index`'s vertical slice of one block — the payload pane's own
    per-stream segment vocabulary, so one plane reads the same way in
    both panes."""
    x0, y0, x1, y1 = box_xyxy
    span = x1 - x0 + 1
    sx0 = x0 + round(index * span / max(1, total))
    sx1 = x0 + round((index + 1) * span / max(1, total)) - 1
    return sx0, y0, max(sx0, sx1), y1


def _grid_shape(fit: FieldSolved) -> tuple[int, int] | None:
    if not fit.planes:
        return None
    shape = np.asarray(fit.planes[0].has_data).shape
    return int(shape[0]), int(shape[1])


def _certified_blocks(model: object, fit: FieldSolved,
                      grid_yx: tuple[int, int]) -> set[tuple[int, int]]:
    """Blocks whose every tile is certified in every stream.

    A fully decoded area has nothing left to measure, so it is uncovered
    for a benign reason and must not read as a blind spot.
    """
    # THIS page's states, never the run's: a band painting another page's
    # certified tiles reports 'nothing left to measure' exactly where the
    # operator is hunting a blind spot (v1's 2026-08-22 page-aware fix).
    states = model.tile_states.get(int(fit.page))
    if states is None:
        return set()
    done = np.asarray(states == panes.TILE_CERTIFIED).all(axis=0)
    block_y, block_x = (max(1, int(v)) for v in fit.block_tiles_yx)
    grid_y, grid_x = grid_yx
    found = set()
    for gy in range(grid_y):
        for gx in range(grid_x):
            patch = done[gy * block_y:(gy + 1) * block_y,
                         gx * block_x:(gx + 1) * block_x]
            if patch.size and bool(patch.all()):
                found.add((gy, gx))
    return found


def _plane_line(row: FieldPlaneRow, n_tiles: int | None = None) -> str:
    """One plane's numbers, with the solve's own error bar beside the
    value it belongs to (design §2.4).

    A plane no template could be built for reads UNKNOWN, which is not
    the same statement as a measured zero (I13) and is the state a
    starved Y leaves the page in.  A plane the gauge holds at the pose
    (cmy's C) is zero by name: no median, no support (2026-10-12).
    """
    total = "" if not n_tiles else f"/{n_tiles}"
    if row.held:
        return (f"{row.plane_name}  zero by the gauge — the pose's own ink"
                f" · {row.n_observations} observation(s) fit the window"
                f" nuisances only")
    if not row.known:
        return f"{row.plane_name}  unknown — no template on any tile"
    return (f"{row.plane_name}  median {row.median_delta_dots:.3f}d"
            f" ± {row.median_uncertainty_dots:.3f}d"
            f" · support {row.support_tiles}{total} tiles"
            f" · {row.n_observations} observation(s)"
            f" from {row.n_captures} capture(s)")


def _residual_table(model: object, fit: FieldSolved) -> list[str]:
    """Which footing disagrees with the page and on WHICH PLANE: a
    header and one line per (capture, plane), loudest first.

    Energy against its own noise expectation: a ratio near one is a
    capture the page explains, and a loud one is design §7's question,
    rendered where an operator can read which footing it was.  PER
    PLANE since W8 (R-F, review F11): summing the three first lets two
    healthy word planes bury the Y plane this table exists to expose —
    a Y ratio of 8 reported as 0.040.  A table and not one line, because
    the answer is an ordering over a sheet's whole scan history
    (thirteen captures on sheet H, so thirty-nine rows) and an ordering
    does not survive being packed onto a row.  A tie falls back to the
    event's own order: the labels are ordinals, and sorting those as
    text would put capture 10 ahead of capture 2.
    """
    rows = sorted(
        ((energy / expected if expected > 0.0 else 0.0, order,
          readout.capture_label(model, capture),
          readout.plane_name_of(fit, plane), int(count))
         for order, (capture, plane, energy, expected, count)
         in enumerate(fit.residual_by_capture_plane)),
        key=lambda row: (-row[0], row[1]))
    return ["residual/noise by capture and plane, loudest first"] + [
        f"  {label} {plane_name}  {ratio:.2f}x · {count} observation(s)"
        for ratio, _order, label, plane_name, count in rows]


def _text_lines(model: object, fit: FieldSolved, factor: float,
                grid_yx: tuple[int, int] | None) -> list[tuple[str, tuple]]:
    geometry = ("no block grid" if grid_yx is None else
                f"{grid_yx[0]}x{grid_yx[1]} blocks of"
                f" {fit.block_tiles_yx[0]}x{fit.block_tiles_yx[1]} tiles"
                f" · arrows x{factor:.4g}")
    lines: list[tuple[str, tuple]] = [
        (f"page {fit.page} · rev {fit.revision} · {geometry}", panes.TEXT)]
    n_tiles = int(fit.tiles_yx[0]) * int(fit.tiles_yx[1])
    for row in fit.planes:
        hue = PLANE_HUE.get(row.plane_name, panes.TEXT)
        ink = tuple(int(v * 0.55) for v in hue)
        lines.append((_plane_line(row, n_tiles), ink))
    lines.extend((line, panes.MUTED)
                 for line in _residual_table(model, fit))
    return lines


def band_geometry(model: object, page: int) -> tuple[int, int] | None:
    """(width, body height) of the band's page body, or None when the
    page has no geometry yet.  Page-proportioned at twice the page
    pane's width — the POSE band's own footing, so the two share the
    bottom row cleanly."""
    geometry = panes.page_geometry(model, page)
    if geometry is None:
        return None
    _grid, base_width, base_height = geometry
    width = min(BAND_MAX_WIDTH, base_width * 2)
    return width, max(80, round(base_height * width / base_width))


def raster(model: object, page: int) -> np.ndarray | None:
    """The FIELD band for one page, or None while no fit has landed on
    it — the byte-stability rule: a run without the arm renders exactly
    the panes it always did."""
    fit = readout.page_field(model, page)
    geometry = band_geometry(model, page)
    if fit is None or geometry is None:
        return None
    grid_yx = _grid_shape(fit)
    width, body_h = geometry
    measured = tuple((row,) + _live_blocks(row) for row in fit.planes
                     if not row.held)
    block_w = width / max(1, grid_yx[1]) if grid_yx else float(width)
    block_h = body_h / max(1, grid_yx[0]) if grid_yx else float(body_h)
    factor = exaggeration(measured, block_w, block_h)
    drawn = any(deltas.size
                for _row, _blocks, deltas, _magnitudes in measured)
    lines = _text_lines(model, fit, factor, grid_yx)
    pane = panes.Pane(width, TITLE_H + body_h + 10 + len(lines) * TEXT_STEP)
    pane.rect((0, 0, width - 1, TITLE_H - 1), fill=TITLE_FILL,
              outline=TITLE_RULE)
    title = (f"{TITLE} x{factor:.4g} · arrow = per-plane registration"
             f" delta · shaded = any plane's |delta| >="
             f" {plane_field.FIELD_NOISE_DOTS:.2f} dot · tinted share = that"
             f" plane blind · black = all planes blind · dark green ="
             f" certified"
             if drawn else f"{TITLE} · no plane has evidence here yet")
    pane.text((7, 4), title, TITLE_TEXT if drawn else DIM, TEXT_SIZE)
    pane.rect((0, TITLE_H, width - 1, TITLE_H + body_h - 1), fill=BODY_BG,
              outline=BODY_OUTLINE)
    if grid_yx is not None:
        _paint_body(pane, model, fit, grid_yx, factor, measured,
                    (width, body_h))
    pane.draw.line((0, TITLE_H + body_h, width, TITLE_H + body_h),
                   fill=panes.RULE)
    pane.rows(8, TITLE_H + body_h + 5, lines, size=TEXT_SIZE)
    return pane.array()


def _paint_body(pane: panes.Pane, model: object, fit: FieldSolved,
                grid_yx: tuple[int, int], factor: float,
                measured: tuple[tuple[FieldPlaneRow, np.ndarray,
                                      np.ndarray, np.ndarray], ...],
                size_wh: tuple[int, int]) -> None:
    width, body_h = size_wh
    grid_y, grid_x = grid_yx
    block_w = width / max(1, grid_x)
    block_h = body_h / max(1, grid_y)
    floor = plane_field.FIELD_NOISE_DOTS
    covered: set[tuple[int, int]] = set()
    shaded: set[tuple[int, int]] = set()
    live_by_plane: dict[int, set[tuple[int, int]]] = {}
    for row, blocks, _deltas, magnitudes in measured:
        mine = live_by_plane.setdefault(int(row.plane), set())
        for (gy, gx), magnitude in zip(blocks.tolist(), magnitudes):
            covered.add((gy, gx))
            mine.add((gy, gx))
            if float(magnitude) >= floor:
                shaded.add((gy, gx))

    def box(gy: int, gx: int) -> tuple[int, int, int, int]:
        x0 = round(gx * block_w)
        y0 = TITLE_H + round(gy * block_h)
        return (x0, y0, max(x0, round((gx + 1) * block_w) - 1),
                max(y0, TITLE_H + round((gy + 1) * block_h) - 1))

    for gy, gx in sorted(shaded):
        pane.rect(box(gy, gx), fill=SHADE)
    done = _certified_blocks(model, fit, grid_yx)
    for gy in range(grid_y):
        for gx in range(grid_x):
            if (gy, gx) in covered:
                continue
            pane.rect(box(gy, gx),
                      fill=DONE if (gy, gx) in done else HOLE)
    n_planes = max(1, len(measured))
    for index, (row, _blocks, _deltas, _mag) in enumerate(measured):
        blind = _blind_blocks(live_by_plane.get(int(row.plane), set()),
                              covered)
        if not blind:
            continue
        tint = _mix(PLANE_HUE.get(row.plane_name, panes.TEXT), BLIND_MIX)
        for gy, gx in sorted(blind):
            pane.rect(_segment(box(gy, gx), index, n_planes), fill=tint)
    for row, blocks, deltas, _magnitudes in measured:
        colour = PLANE_HUE.get(row.plane_name, panes.TEXT)
        stagger = (int(row.plane) % 3 - 1) * STAGGER_PX
        for (gy, gx), delta in zip(blocks.tolist(), deltas):
            cx = (gx + 0.5) * block_w
            cy = TITLE_H + (gy + 0.5) * block_h + stagger
            draw_arrow(pane.draw, (cx, cy),
                       (cx + float(delta[0]) * factor,
                        cy + float(delta[1]) * factor), colour)

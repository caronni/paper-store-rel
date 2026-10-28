"""The FIELD band — DIAG-DESIGN.md §3's reserved slot, now that holo3
has a per-plane field producer (`plugins/fields.py`).

Same visual vocabulary as the v1 plane-fields band it is matched to
(`src/holo/receive/diag/presentation.py::PaneRenderer.field_band`, user
design 2026-08-21): one exaggerated quiver arrow per plane per block,
C/M/Y in the stream hues and staggered so they never fully overlap, over
a mid-grey page body; blocks shaded where any plane's delta reaches the
writer's publish floor — the shading IS the dead-band prediction; and a
block with no field data split BY CAUSE, dark green where the tiles are
already certified (nothing left to measure, benign) and black where they
are not (the actionable blind spot).  The exaggeration factor is folded
into the title so the drawn geometry and the printed number are always
the same measurement.

Arrow scale is v1's: a FIXED factor (`src/holo/receive/color_field.py`
carries 50.0 as its `exaggeration_hint`) clamped by geometry, never
lengthened by it — `min(fixed, cap)`, v1's own expression.  A cap-only
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

Two things differ from v1 by construction, not by choice.  holo3's field
is per lane-page (capture, level, page) rather than one page-wide
measurement, so the band draws the lane that fitted this page most
recently and names it; and the certified-tile overlay is read off the
model's own tile states instead of riding in the event, because holo3's
diag model already holds them.

Two channels v1 does not have, both for the dead-plane sheets this band
exists for (e030, e033).  A REFUSED plane's quiver is drawn dimmed: its
field is real and is the point of carrying it, but it is not in effect
on the decode, and the rest of this viewer already spells "not durable"
as a weaker stroke.  And per-plane blindness gets a spatial channel —
a block where one plane has no data while another does is tinted in
that plane's hue across its own third of the block, the payload pane's
per-stream segment vocabulary — because "where is Y blind" is a
spatial question that the all-planes-blind black square cannot answer.

Split out of `panes.py` for the line cap, on v1's own precedent
(`field_view.py` beside `viewer.py`) — one growing concern should not
push the shared pane module over.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import ImageDraw

from ..data import FieldFitted, FieldPlaneFit
from . import panes, readout

TITLE = "FIELD"
BODY_BG = (118, 118, 118)          # mid-grey base (v1 user ruling: amber
                                   # shading read as background and gold
                                   # arrows drowned on anything lighter)
BODY_OUTLINE = (214, 214, 214)     # faint page outline
DIM = (150, 150, 150)              # title colour when there is no field
SHADE = (94, 94, 94)               # at-or-over the publish floor
HOLE = (0, 0, 0)                   # no field data, tiles uncertified
DONE = (26, 62, 44)                # no field data, tiles certified
TITLE_FILL = (238, 240, 243)
TITLE_RULE = (176, 181, 186)
TITLE_TEXT = (35, 40, 45)

#: plane_index 0/1/2 = C/M/Y, the pinned contract; hues are v1's own
#: stream palette so the two viewers read the same.
PLANE_HUE = {"C": (60, 200, 255), "M": (255, 80, 200), "Y": (240, 220, 60)}

STAGGER_PX = 3
#: v1's own fixed exaggeration (`color_field.FieldConfig.exaggeration_hint`
#: = 50.0): arrow length stays proportional to the physical delta, so two
#: runs of two sheets are comparable by eye.
FIXED_EXAGGERATION = 50.0
#: the clamp, v1's own (`presentation.py::field_band`): no drawn arrow
#: reaches beyond this many blocks on its OWN axis, measured from the
#: block centre.  Never lengthens the fixed factor.
ARROW_BLOCK_CAP = 2.0
#: a refused plane's arrow, blended this far toward the body grey
REFUSED_MIX = 0.55
#: a per-plane blind segment, blended this far toward the body grey
BLIND_MIX = 0.72
TITLE_H = 20
TEXT_SIZE = 11
TEXT_STEP = 16
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


def exaggeration(measured: tuple[tuple[FieldPlaneFit, np.ndarray,
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


def _live_blocks(row: FieldPlaneFit
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """This plane's (block index pairs, deltas, |delta|) where it has data.

    A non-finite delta — a degenerate solve — counts as NO data rather
    than as a delta: it is not something to draw an arrow from, and the
    block is honestly a blind spot.  The magnitude rides along from the
    producer's own pooling (never `hypot` of the pooled vector, which is
    a different statistic than the writer's floor).
    """
    if row.delta_grid_dots_xy is None or row.has_data is None:
        return (np.zeros((0, 2), np.int64), np.zeros((0, 2), np.float64),
                np.zeros(0, np.float64))
    grid = np.asarray(row.delta_grid_dots_xy, np.float64)
    live = np.asarray(row.has_data, bool) & np.isfinite(grid).all(axis=-1)
    if row.magnitude_grid_dots is None:
        magnitude = np.hypot(grid[..., 0], grid[..., 1])
    else:
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


def _grid_shape(fit: FieldFitted) -> tuple[int, int] | None:
    for row in fit.planes:
        if row.has_data is not None:
            shape = np.asarray(row.has_data).shape
            return int(shape[0]), int(shape[1])
    return None


def _certified_blocks(model: object, fit: FieldFitted,
                      grid_yx: tuple[int, int]) -> set[tuple[int, int]]:
    """Blocks whose every tile is certified in every stream.

    A fully decoded area has nothing left to measure, so it is uncovered
    for a benign reason and must not read as a blind spot.
    """
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


def _plane_line(row: FieldPlaneFit, n_tiles: int | None = None) -> str:
    if not row.fitted:
        return f"{row.plane_name}  {row.refusal}"
    verdict = "PUBLISHED" if row.published else f"refused: {row.refusal}"
    total = "" if not n_tiles else f"/{n_tiles}"
    return (f"{row.plane_name}  median {row.median_delta_dots:.3f}d"
            f" · sites {row.n_sites}"
            f" · support {row.support_tiles}{total} tiles"
            f" · residual {row.residual:.3f} · {verdict}")


def _text_lines(model: object, fit: FieldFitted, factor: float,
                grid_yx: tuple[int, int] | None) -> list[tuple[str, tuple]]:
    lanes = readout.page_field_lanes(model, fit.page)
    geometry = ("no block grid — no plane fitted" if grid_yx is None else
                f"{grid_yx[0]}x{grid_yx[1]} blocks of"
                f" {fit.block_tiles_yx[0]}x{fit.block_tiles_yx[1]} tiles"
                f" · arrows x{factor:.4g}")
    head = (f"lane {lanes[0] if lanes else '?'} · page {fit.page}"
            f" · {fit.n_certificates} certificates · {geometry}")
    lines: list[tuple[str, tuple]] = [(head, panes.TEXT)]
    n_tiles = int(fit.tiles_yx[0]) * int(fit.tiles_yx[1])
    for row in fit.planes:
        hue = PLANE_HUE.get(row.plane_name, panes.TEXT)
        ink = tuple(int(v * 0.55) for v in hue)
        lines.append((_plane_line(row, n_tiles), ink))
    if len(lanes) > 1:
        lines.append((f"also fitted here: {', '.join(lanes[1:])}"
                      f" (latest shown)", panes.MUTED))
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
    measured = tuple((row,) + _live_blocks(row) for row in fit.planes)
    block_w = width / max(1, grid_yx[1]) if grid_yx else float(width)
    block_h = body_h / max(1, grid_yx[0]) if grid_yx else float(body_h)
    factor = exaggeration(measured, block_w, block_h)
    drawn = any(deltas.size
                for _row, _blocks, deltas, _magnitudes in measured)
    lines = _text_lines(model, fit, factor, grid_yx)
    pane = panes.Pane(width, TITLE_H + body_h + 10 + len(lines) * TEXT_STEP)
    pane.rect((0, 0, width - 1, TITLE_H - 1), fill=TITLE_FILL,
              outline=TITLE_RULE)
    title = (f"{TITLE} x{factor:.4g} · arrow = per-plane registration delta"
             f" (dim = refused) · shaded = any plane's |delta| >="
             f" {fit.publish_floor_dots:.2f} dot · tinted third = that"
             f" plane blind · black = all planes blind · dark green ="
             f" certified"
             if drawn else f"{TITLE} · no plane has a field here yet")
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


def _paint_body(pane: panes.Pane, model: object, fit: FieldFitted,
                grid_yx: tuple[int, int], factor: float,
                measured: tuple[tuple[FieldPlaneFit, np.ndarray,
                                      np.ndarray, np.ndarray], ...],
                size_wh: tuple[int, int]) -> None:
    width, body_h = size_wh
    grid_y, grid_x = grid_yx
    block_w = width / max(1, grid_x)
    block_h = body_h / max(1, grid_y)
    floor = float(fit.publish_floor_dots)
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
        if not row.published:
            colour = _mix(colour, REFUSED_MIX)
        stagger = (int(row.plane) % 3 - 1) * STAGGER_PX
        for (gy, gx), delta in zip(blocks.tolist(), deltas):
            cx = (gx + 0.5) * block_w
            cy = TITLE_H + (gy + 0.5) * block_h + stagger
            draw_arrow(pane.draw, (cx, cy),
                       (cx + float(delta[0]) * factor,
                        cy + float(delta[1]) * factor), colour)

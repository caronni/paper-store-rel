from __future__ import annotations

import io
import math
from functools import lru_cache
from typing import TYPE_CHECKING, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..format import pilots
from . import readout
from .model import (TILE_ADDRESSED, TILE_ATTEMPTED, TILE_CERTIFIED,
                    TILE_FLOOR, TILE_UNKNOWN, DiagModel)

if TYPE_CHECKING:
    from ..data import PoseCommitted

BG = (250, 250, 250)
TEXT = (34, 34, 34)
MUTED = (122, 126, 130)
GREEN = (0, 158, 62)
ORANGE = (238, 106, 0)
BLUE = (0, 94, 224)
PURPLE = (128, 62, 208)
CYAN = (0, 168, 200)
AMBER = (210, 130, 35)
RULE = (176, 181, 186)
CONTRADICTION = (168, 18, 28)

HUES = (
    (96, 165, 250), (52, 211, 153), (251, 191, 36), (248, 113, 113),
    (167, 139, 250), (45, 212, 191), (251, 146, 60), (232, 121, 249),
    (163, 230, 53), (125, 211, 252), (253, 164, 175), (196, 181, 253),
)

CHIP_GREEN = ((118, 196, 130), (25, 120, 55))
CHIP_REACH = ((198, 220, 246), (152, 186, 224))
CHIP_AMBER = ((250, 198, 110), (210, 130, 35))
CHIP_ORANGE = ((247, 166, 106), (205, 92, 15))
CHIP_UNSEEN = ((238, 238, 238), (216, 216, 216))
CHIP_NEUTRAL = ((233, 233, 233), (209, 209, 209))
CHIP_TEXT = (20, 20, 20)

TILE_CHIPS = {
    TILE_UNKNOWN: CHIP_NEUTRAL,
    TILE_ADDRESSED: CHIP_REACH,
    TILE_FLOOR: CHIP_AMBER,
    TILE_ATTEMPTED: CHIP_ORANGE,
    TILE_CERTIFIED: CHIP_GREEN,
}

CAPTURE_PANE_WIDTH = 900
PAGE_PANE_MIN_WIDTH = 700
PAGE_PANE_MAX_WIDTH = 2200
REPLAY_FOOTER_H = 22

POSE_BG = (150, 152, 156)
POSE_TITLE_TEXT = (28, 30, 33)
TICK_GREY = (70, 72, 75)
TICK_BLUE = (20, 80, 220)
TICK_RED = (211, 47, 47)
ROTATION_EXAGGERATION = 40
PITCH_SATURATION_DEV = 0.005
PITCH_DEV_EPSILON = 1e-4
POSE_TITLE = ("POSE x40 · tick = grid rotation vs page"
              " · colour = pitch vs nominal")


@lru_cache(maxsize=None)
def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


@lru_cache(maxsize=4096)
def glyph(size: int, text: str) -> tuple[object, tuple[int, int]]:
    return font(size).getmask2(text)


def blit_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
              fill: tuple[int, int, int], size: int) -> None:
    mask, offset = glyph(size, text)
    ink = draw._getink(fill)[0]
    if ink is not None:
        draw.draw.draw_bitmap((xy[0] + offset[0], xy[1] + offset[1]),
                              mask, ink)


def mask_edge(mask: np.ndarray) -> np.ndarray:
    padded = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), bool)
    padded[1:-1, 1:-1] = mask
    inner = (padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1]
             & padded[1:-1, :-2] & padded[1:-1, 2:])
    return mask & ~inner


def resize_mask(mask: np.ndarray, size_wh: tuple[int, int]) -> np.ndarray:
    source = np.asarray(mask, bool)
    if not source.size:
        return np.zeros((max(1, size_wh[1]), max(1, size_wh[0])), bool)
    image = Image.fromarray(source.astype(np.uint8) * 255)
    return np.asarray(image.resize(size_wh, Image.NEAREST), np.uint8) > 0


def dashed_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                color: tuple[int, int, int], dash: int = 4) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1, 2 * dash):
        draw.line((x, y0, min(x + dash, x1), y0), fill=color)
        draw.line((x, y1, min(x + dash, x1), y1), fill=color)
    for y in range(y0, y1, 2 * dash):
        draw.line((x0, y, x0, min(y + dash, y1)), fill=color)
        draw.line((x1, y, x1, min(y + dash, y1)), fill=color)


class Pane:

    def __init__(self, width: int, height: int,
                 background: tuple[int, int, int] = BG,
                 canvas: np.ndarray | None = None) -> None:
        self.width = int(width)
        self.height = int(height)
        if canvas is not None:
            self.image = Image.fromarray(np.ascontiguousarray(canvas))
        else:
            self.image = Image.new("RGB", (self.width, self.height),
                                   background)
        self.draw = ImageDraw.Draw(self.image)

    def array(self) -> np.ndarray:
        return np.asarray(self.image)

    def clip(self, box: tuple[float, float, float, float]
             ) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        return (max(0, min(x0, self.width - 1)),
                max(0, min(y0, self.height - 1)),
                max(1, min(x1, self.width - 1)),
                max(1, min(y1, self.height - 1)))

    def rect(self, box: tuple[float, float, float, float], *,
             outline: tuple[int, int, int] | None = None,
             fill: tuple[int, int, int] | None = None,
             width: int = 1) -> None:
        self.draw.rectangle(self.clip(box), outline=outline, fill=fill,
                            width=width)

    def dashed(self, box: tuple[float, float, float, float],
               color: tuple[int, int, int], dash: int = 4) -> None:
        dashed_rect(self.draw, self.clip(box), color, dash)

    def text(self, xy: tuple[float, float], value: str,
             fill: tuple[int, int, int] = TEXT, size: int = 11) -> None:
        blit_text(self.draw, (int(xy[0]), int(xy[1])), value, fill, size)

    def rows(self, x: int, y: int,
             lines: Iterable[str | tuple[str, tuple[int, int, int]]], *,
             size: int = 11) -> int:
        step = size + 5
        lines = tuple(lines)
        for index, line in enumerate(lines):
            value, colour = line if isinstance(line, tuple) else (line, TEXT)
            self.text((x, y + index * step), value, colour, size)
        return y + len(lines) * step


class TileGrid:

    def __init__(self, width: int, height: int,
                 tiles_yx: tuple[int, int]) -> None:
        self.width = int(width)
        self.height = int(height)
        self.tiles_yx = (max(1, int(tiles_yx[0])), max(1, int(tiles_yx[1])))

    def box(self, ty: int, tx: int) -> tuple[int, int, int, int]:
        tile_y, tile_x = self.tiles_yx
        x0 = round(tx * self.width / tile_x)
        y0 = round(ty * self.height / tile_y)
        x1 = round((tx + 1) * self.width / tile_x)
        y1 = round((ty + 1) * self.height / tile_y)
        return x0, y0, max(x0 + 1, x1 - 1), max(y0 + 1, y1 - 1)

    def segment(self, box: tuple[int, int, int, int], index: int,
                n_streams: int) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        span = x1 - x0 + 1
        sx0 = x0 + round(index * span / n_streams)
        sx1 = x0 + round((index + 1) * span / n_streams) - 1
        return sx0, y0, max(sx0, sx1), y1

    def count_font(self) -> int | None:
        tile_y, tile_x = self.tiles_yx
        room_x = round(self.width / tile_x) - 4
        room_y = round(self.height / tile_y) - 3
        for size in range(11, 5, -1):
            mask, _offset = glyph(size, "999")
            if mask.size[0] <= room_x and mask.size[1] <= room_y:
                return size
        return None

    def base(self) -> Pane:
        fill, outline = CHIP_UNSEEN
        pane = Pane(self.width, self.height, fill)
        tile_y, tile_x = self.tiles_yx
        for tx in range(tile_x):
            x = self.box(0, tx)[2]
            pane.draw.line((x, 0, x, self.height), fill=outline)
        for ty in range(tile_y):
            y = self.box(ty, 0)[3]
            pane.draw.line((0, y, self.width, y), fill=outline)
        return pane


def encode_png(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(array)).save(stream, "PNG")
    return stream.getvalue()


def region_hue(ordinal: int, region_index: int) -> tuple[int, int, int]:
    return HUES[(int(ordinal) * 5 + int(region_index)) % len(HUES)]


def _darken(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(int(v * 0.55) for v in colour)


def page_pane_width(tiles_x: int) -> int:
    return min(PAGE_PANE_MAX_WIDTH, max(PAGE_PANE_MIN_WIDTH, 16 * tiles_x))


def page_geometry(model: DiagModel,
                  page: int) -> tuple[TileGrid, int, int] | None:
    run = model.run
    if run is None or not 0 <= int(page) < run.pages:
        return None
    ty, tx = (max(1, int(v)) for v in run.tiles_yx)
    width = page_pane_width(tx)
    height = max(120, min(3000, round(width * ty / tx)))
    return TileGrid(width, height, (ty, tx)), width, height


def _ordinal_by_capture(model: DiagModel) -> dict[str, int]:
    return {capture: ordinal for ordinal, capture in model.ordinals.items()}


def _resize_grey(values: np.ndarray, size_wh: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray((values * 255.0).astype(np.uint8))
    return np.asarray(image.resize(size_wh, Image.BILINEAR), np.uint8)


def _underlay_canvas(underlay: tuple[np.ndarray, int] | None,
                     frame: tuple[float, float, float, float], scale: float,
                     width: int, height: int) -> np.ndarray:
    canvas = np.zeros((height, width, 3), np.uint8)
    canvas[:] = BG
    if underlay is None:
        return canvas
    grey, stride = underlay
    y0, x0, y1, x1 = frame
    py0 = max(0, int(y0 / stride))
    px0 = max(0, int(x0 / stride))
    py1 = max(py0 + 1, min(grey.shape[0], int(np.ceil(y1 / stride))))
    px1 = max(px0 + 1, min(grey.shape[1], int(np.ceil(x1 / stride))))
    crop = grey[py0:py1, px0:px1]
    if not crop.size:
        return canvas
    low, high = np.percentile(crop, (1.0, 99.0))
    span = max(float(high) - float(low), 1e-6)
    stretched = 0.55 + 0.45 * np.clip((crop - float(low)) / span, 0.0, 1.0)
    target_h = max(1, min(height, round((py1 - py0) * stride * scale)))
    target_w = max(1, min(width, round((px1 - px0) * stride * scale)))
    resized = np.asarray(_resize_grey(stretched, (target_w, target_h)),
                         np.uint8)
    oy = min(max(0, round((py0 * stride - y0) * scale)),
             height - resized.shape[0])
    ox = min(max(0, round((px0 * stride - x0) * scale)),
             width - resized.shape[1])
    canvas[oy:oy + resized.shape[0], ox:ox + resized.shape[1]] = (
        resized[..., None])
    return canvas


def _blend_mask(canvas: np.ndarray, mask: np.ndarray,
                colour: tuple[int, int, int], alpha: float) -> None:
    hue = np.asarray(colour, np.float32)
    target = canvas[mask]
    canvas[mask] = ((1.0 - alpha) * target.astype(np.float32)
                    + alpha * hue).astype(np.uint8)


def _paint_region_mask(canvas: np.ndarray, mark: object, scale: float,
                       hue: tuple[int, int, int], won: bool) -> None:
    cells = mark.cells
    if cells is None or int(mark.step_px) <= 0:
        return
    cells = np.asarray(cells, bool)
    if not cells.size:
        return
    step = int(mark.step_px)
    oy = int(round(mark.origin_yx[0] * scale))
    ox = int(round(mark.origin_yx[1] * scale))
    h = max(1, int(round(cells.shape[0] * step * scale)))
    w = max(1, int(round(cells.shape[1] * step * scale)))
    resized = resize_mask(cells, (w, h))
    y0, x0 = max(0, oy), max(0, ox)
    y1 = min(canvas.shape[0], oy + resized.shape[0])
    x1 = min(canvas.shape[1], ox + resized.shape[1])
    if y1 <= y0 or x1 <= x0:
        return
    piece = resized[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    target = canvas[y0:y1, x0:x1]
    if won:
        target[piece] = (0.68 * target[piece].astype(np.float32)
                         + 0.32 * np.asarray(GREEN, np.float32)
                         ).astype(np.uint8)
    target[mask_edge(piece)] = hue


def _capture_text(model: DiagModel, capture_id: str
                  ) -> list[tuple[str, tuple[int, int, int]]]:
    lines: list[tuple[str, tuple[int, int, int]]] = []
    replay = readout.replay_line(model)
    if replay is not None:
        lines.append((replay, MUTED))
    causes = model.settle_causes.get(capture_id, {})
    if causes:
        ranked = sorted(causes.items(), key=lambda item: (-item[1], item[0]))
        lines.append(("settled  " + " · ".join(
            f"{cause} {count}" for cause, count in ranked), TEXT))
    else:
        lines.append(("settled  none", MUTED))
    entries = [event for (cid, _pool), event in model.calibrations.items()
               if cid == capture_id]
    if entries:
        adopted = sum(1 for event in entries if event.adopted)
        refusals: dict[str, int] = {}
        for event in entries:
            if not event.adopted:
                refusals[event.reason] = refusals.get(event.reason, 0) + 1
        tail = "" if not refusals else " · " + " · ".join(
            f"{reason} {count}" for reason, count in
            sorted(refusals.items(), key=lambda item: (-item[1], item[0])))
        lines.append((f"calibrate {adopted}/{len(entries)} adopted{tail}",
                      TEXT))
    else:
        lines.append(("calibrate unavailable before calibrate", MUTED))
    return lines


def _capture_poses(model: DiagModel, capture_id: str) -> tuple:
    return tuple(pose for rows in model.poses.values() for pose in rows
                 if pose.capture == capture_id)


def _certified_scrap_boxes(model: DiagModel, pose: PoseCommitted,
                           scale: float
                           ) -> tuple[tuple[int, int, int, int], ...]:
    run = model.run
    states = model.tile_states.get(int(pose.page))
    if run is None or states is None:
        return ()
    height, width = (int(v) for v in pose.shape_yx)
    if height <= 0 or width <= 0:
        return ()
    matrix = np.asarray(pose.native_affine, np.float64).reshape(2, 3)
    if not bool(np.isfinite(matrix).all()) or not bool(
            np.abs(matrix[:, :2]).sum() > 0.0):
        return ()
    rot_h, rot_w = ((width, height) if pose.rot_k % 2
                    else (height, width))
    oy, ox = (int(v) for v in pose.page_origin_yx)
    period = pilots.TILE_CELLS
    tiles_y, tiles_x = (int(v) for v in run.tiles_yx)
    boxes = []
    for ty in range(max(0, oy // period),
                    min(tiles_y, (oy + rot_h - 1) // period + 1)):
        for tx in range(max(0, ox // period),
                        min(tiles_x, (ox + rot_w - 1) // period + 1)):
            if not bool((states[:, ty, tx] == TILE_CERTIFIED).all()):
                continue
            py0 = max(oy, ty * period)
            px0 = max(ox, tx * period)
            py1 = min(oy + rot_h, (ty + 1) * period)
            px1 = min(ox + rot_w, (tx + 1) * period)
            if py1 <= py0 or px1 <= px0:
                continue
            corners = np.array(((py0, px0), (py0, px1), (py1, px0),
                                (py1, px1)), np.float64)
            native = corners @ matrix[:, :2].T + matrix[:, 2]
            boxes.append((
                int(round(float(native[:, 1].min()) * scale)),
                int(round(float(native[:, 0].min()) * scale)),
                int(round(float(native[:, 1].max()) * scale)),
                int(round(float(native[:, 0].max()) * scale))))
    return tuple(boxes)


def _capture_raster(model: DiagModel, ordinal: int) -> np.ndarray | None:
    capture_id = model.ordinals.get(int(ordinal))
    if capture_id is None:
        return None
    opened = model.captures.get(capture_id)
    if opened is None:
        return None
    shape_y, shape_x = (max(1, int(v)) for v in opened.shape_yx)
    width = CAPTURE_PANE_WIDTH
    scale = width / shape_x
    draw_h = max(120, min(2400, round(shape_y * scale)))
    survey = model.surveys.get(capture_id)
    underlay = (None if survey is None or survey.preview is None
                else (survey.preview, max(1, int(survey.preview_decim))))
    canvas = _underlay_canvas(underlay, (0.0, 0.0, float(shape_y),
                                         float(shape_x)),
                              scale, width, draw_h)
    marks = () if survey is None else survey.regions
    for mark in marks:
        hue = region_hue(ordinal, int(mark.region_index))
        _paint_region_mask(canvas, mark, scale, hue, False)
    wash = np.zeros(canvas.shape[:2], bool)
    for pose_event in _capture_poses(model, capture_id):
        for x0, y0, x1, y1 in _certified_scrap_boxes(model, pose_event,
                                                     scale):
            wash[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    if wash.any():
        _blend_mask(canvas, wash, GREEN, 0.35)
    text_lines = _capture_text(model, capture_id)
    text_h = 12 + len(text_lines) * 16
    pane = Pane(width, draw_h + text_h)
    pane.image.paste(Image.fromarray(canvas), (0, 0))
    for mark in marks:
        hue = region_hue(ordinal, int(mark.region_index))
        ly = int(round(mark.origin_yx[0] * scale))
        lx = int(round(mark.origin_yx[1] * scale))
        pane.text((min(width - 34, max(2, lx + 2)),
                   min(draw_h - 14, max(2, ly + 2))),
                  f"{ordinal}.{int(mark.region_index)}", _darken(hue), 12)
    frames = {int(mark.region_index): (mark.origin_yx, mark.pitch_px)
              for mark in marks}
    active = readout.active_place_windows(model)
    for key, rec in model.windows.items():
        if key[0] != capture_id:
            continue
        entry = frames.get(key[1])
        if entry is None or entry[1] is None:
            continue
        (origin_y, origin_x), pitch = entry
        cy0, cx0, cy1, cx1 = key[2]
        x0 = (origin_x + cx0 * pitch) * scale
        y0 = (origin_y + cy0 * pitch) * scale
        x1 = (origin_x + cx1 * pitch) * scale
        y1 = (origin_y + cy1 * pitch) * scale
        if key in active:
            pane.rect((x0, y0, x1, y1), outline=PURPLE, width=2)
            pane.dashed((x0 - 3, y0 - 3, x1 + 3, y1 + 3), PURPLE)
            colour = PURPLE
        elif rec.cause is not None:
            pane.rect((x0, y0, x1, y1), outline=ORANGE, width=1)
            colour = ORANGE
        else:
            pane.rect((x0, y0, x1, y1), outline=PURPLE, width=1)
            colour = PURPLE
        label = f"{rec.stage} {rec.cost}" if rec.stage else (rec.cause or "")
        if label:
            pane.text((x0 + 2, max(0, y0 - 11)), label, colour, 9)
    if underlay is None:
        pane.text((6, draw_h - 15), "preview omitted by the survey",
                  MUTED, 10)
    pane.draw.line((0, draw_h, width, draw_h), fill=RULE)
    pane.rows(8, draw_h + 6, text_lines, size=11)
    return pane.array()


def _pose_boxes(model: DiagModel, page: int, width: int, height: int
                ) -> tuple[tuple[object, tuple[int, int, int, int]], ...]:
    run = model.run
    ty, tx = (max(1, int(v)) for v in run.tiles_yx)
    cell_w = width / (tx * pilots.TILE_CELLS)
    cell_h = height / (ty * pilots.TILE_CELLS)
    boxes = []
    for pose in model.poses.get(int(page), ()):
        h, w = (int(v) for v in pose.shape_yx)
        if pose.rot_k % 2:
            h, w = w, h
        if h <= 0 or w <= 0:
            continue
        oy, ox = (int(v) for v in pose.page_origin_yx)
        boxes.append((pose, (int(round(ox * cell_w)),
                             int(round(oy * cell_h)),
                             int(round((ox + w) * cell_w)),
                             int(round((oy + h) * cell_h)))))
    return tuple(boxes)


def _page_raster(model: DiagModel, page: int) -> np.ndarray | None:
    geometry = page_geometry(model, page)
    if geometry is None:
        return None
    grid, width, height = geometry
    canvas = np.array(grid.base().image)
    ordinal_of = _ordinal_by_capture(model)
    boxes = _pose_boxes(model, page, width, height)
    union: dict[tuple[int, int], np.ndarray] = {}
    for pose, box in boxes:
        ordinal = ordinal_of.get(pose.capture, 0)
        key = (ordinal, int(pose.region_index))
        mask = union.get(key)
        if mask is None:
            mask = np.zeros((height, width), bool)
            union[key] = mask
        x0, y0, x1, y1 = box
        mask[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    for key in sorted(union):
        _blend_mask(canvas, union[key], region_hue(*key), 0.22)
    pane = Pane(width, height, canvas=canvas)
    for key in sorted(union):
        ys, xs = np.nonzero(union[key])
        if not ys.size:
            continue
        pane.text((int(xs.min()) + 3, int(ys.min()) + 2),
                  f"{key[0]}.{key[1]}", _darken(region_hue(*key)), 11)
    bits = model.address_bits.get(int(page))
    solved = model.words_solved.get(int(page))
    counts = (None if bits is None
              else np.unpackbits(bits, axis=-1).sum(axis=-1))
    font_size = grid.count_font()
    tile_y, tile_x = grid.tiles_yx
    for ty in range(tile_y):
        for tx in range(tile_x):
            is_solved = solved is not None and bool(solved[ty, tx])
            count = 0 if counts is None else int(counts[ty, tx])
            if not is_solved and count == 0:
                continue
            box = grid.box(ty, tx)
            outline = GREEN if is_solved else CHIP_REACH[1]
            pane.rect(box, outline=outline, width=1)
            if count and font_size is not None:
                pane.text((box[0] + 2, box[3] - font_size - 2), str(count),
                          CHIP_TEXT, font_size)
    return pane.array()


def _with_replay_footer(canvas: np.ndarray,
                        model: DiagModel) -> np.ndarray:
    """A resumed run's tile map holds only this run's own outcomes; the
    replayed certificates never had a TileOutcome to fold.  An unmarked
    grid would read as an empty run, so a resumed pane says what it is."""
    line = readout.replay_line(model)
    if line is None:
        return canvas
    height, width = canvas.shape[:2]
    pane = Pane(width, height + REPLAY_FOOTER_H)
    pane.image.paste(Image.fromarray(np.ascontiguousarray(canvas)), (0, 0))
    pane.draw.line((0, height, width, height), fill=RULE)
    pane.text((6, height + 6), line, MUTED, 11)
    return pane.array()


def _payload_raster(model: DiagModel, page: int) -> np.ndarray | None:
    geometry = page_geometry(model, page)
    if geometry is None:
        return None
    grid, _width, _height = geometry
    pane = grid.base()
    states = model.tile_states.get(int(page))
    evidence = model.tile_evidence.get(int(page))
    if states is None and evidence is None:
        return _with_replay_footer(pane.array(), model)
    font_size = grid.count_font()
    tiles_x = grid.tiles_yx[1]
    touched = np.zeros(grid.tiles_yx, bool)
    if states is not None:
        touched |= states.max(axis=0) > 0
    if evidence is not None:
        touched |= evidence > 0
    n_streams = 1 if states is None else max(1, states.shape[0])
    for flat in np.flatnonzero(touched.ravel()):
        ty, tx = divmod(int(flat), tiles_x)
        box = grid.box(ty, tx)
        for index in range(n_streams):
            rank = 0 if states is None else int(states[index, ty, tx])
            fill, outline = TILE_CHIPS.get(rank, CHIP_NEUTRAL)
            pane.draw.rectangle(grid.segment(box, index, n_streams),
                                fill=fill, outline=outline)
        fully_certified = (states is not None and bool(
            (states[:, ty, tx] == TILE_CERTIFIED).all()))
        count = 0 if evidence is None else int(evidence[ty, tx])
        if count and font_size is not None and not fully_certified:
            pane.text((box[0] + 2, box[1] + 1), str(min(count, 999)),
                      CHIP_TEXT, font_size)
    return _with_replay_footer(pane.array(), model)


def _rotation_deviation_deg(
        native_affine: tuple[float, ...]) -> float:
    linear = np.asarray(native_affine, np.float64).reshape(2, 3)[:, :2]
    vy, vx = float(linear[0, 1]), float(linear[1, 1])
    if vy == 0.0 and vx == 0.0:
        return 0.0
    return math.remainder(math.degrees(math.atan2(vy, vx)), 90.0)


def _pitch_tick_colour(model: DiagModel,
                       pose: object) -> tuple[int, int, int]:
    run = model.run
    opened = model.captures.get(pose.capture)
    if run is None or opened is None:
        return TICK_GREY
    nominal = float(opened.dpi) * float(run.pitch_in)
    if nominal <= 0.0 or float(pose.pitch_px) <= 0.0:
        return TICK_GREY
    deviation = float(pose.pitch_px) / nominal - 1.0
    if abs(deviation) < PITCH_DEV_EPSILON:
        return TICK_GREY
    target = TICK_RED if deviation > 0.0 else TICK_BLUE
    share = min(1.0, abs(deviation) / PITCH_SATURATION_DEV)
    return tuple(int(round(grey + (hot - grey) * share))
                 for grey, hot in zip(TICK_GREY, target))


def _pose_raster(model: DiagModel, page: int) -> np.ndarray | None:
    geometry = page_geometry(model, page)
    if geometry is None:
        return None
    _grid, base_width, base_height = geometry
    width = min(2600, base_width * 2)
    height = round(base_height * width / base_width)
    pane = Pane(width, height, POSE_BG)
    pane.text((8, 6), POSE_TITLE, POSE_TITLE_TEXT, 12)
    ordinal_of = _ordinal_by_capture(model)
    half = 13.0
    for pose, box in _pose_boxes(model, page, width, height):
        ordinal = ordinal_of.get(pose.capture, 0)
        cx = (box[0] + box[2]) / 2.0 + 3.0 * ordinal
        cy = (box[1] + box[3]) / 2.0
        theta = math.radians(_rotation_deviation_deg(pose.native_affine)
                             * ROTATION_EXAGGERATION)
        colour = _pitch_tick_colour(model, pose)
        dx = math.sin(theta) * half
        dy = -math.cos(theta) * half
        pane.draw.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=colour,
                       width=2)
        pane.draw.ellipse((cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5),
                          fill=colour)
    return pane.array()


def render_pane(model: DiagModel, pane: str, selector: int) -> bytes | None:
    if pane == "capture":
        raster = _capture_raster(model, selector)
    elif pane == "page":
        raster = _page_raster(model, selector)
    elif pane == "payload":
        raster = _payload_raster(model, selector)
    elif pane == "pose":
        raster = _pose_raster(model, selector)
    elif pane == "field":
        from . import fields_pane

        raster = fields_pane.raster(model, selector)
    else:
        return None
    if raster is None:
        return None
    return encode_png(raster)


def pin_panes(model: DiagModel) -> dict[tuple[str, int], bytes]:
    pinned: dict[tuple[str, int], bytes] = {}
    for ordinal in readout.capture_selectors(model):
        try:
            png = render_pane(model, "capture", ordinal)
        except Exception:
            png = None
        if png is not None:
            pinned[("capture", ordinal)] = png
    for page in readout.page_selectors(model):
        for pane in ("page", "payload", "pose"):
            try:
                png = render_pane(model, pane, page)
            except Exception:
                png = None
            if png is not None:
                pinned[(pane, page)] = png
    for page in readout.field_pages(model):
        try:
            png = render_pane(model, "field", page)
        except Exception:
            png = None
        if png is not None:
            pinned[("field", page)] = png
    return pinned

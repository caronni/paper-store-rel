"""Palette, glyphs and canvas primitives for the pane server.

Carried and stripped from the v1 receiver's ``diag/presentation.py``
(RECEIVE-DESIGN §10.3.1 composition, §10.3.4 semantic palette): the
operator palette, the cached-glyph text blitter, the mask-edge and
dashed-rect primitives, the ruled tile grid with its one-pane-wide count
font, and the composed-frame title furniture.

What deliberately did NOT carry: the lane/rung/level vocabulary, the
parked-for-mop-up chip family, the barrier states, and the BCH-word chip
family — holo2 has footings, workers and commits, and its address plane
is the tile map's ``ADDRESSED`` state, not a word-site count.

Observer-side only (DESIGN §10.3, L12). Nothing here reads receiver
state, and nothing here reads a clock: a frame's identity is the store's
commit sequence, which is work-counted by construction.
"""
from __future__ import annotations

import io
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# -- palette (v1 operator primaries-on-white, approved 2026-07-31) ---------

BG = (250, 250, 250)
TEXT = (34, 34, 34)
MUTED = (122, 126, 130)
GREEN = (0, 158, 62)              # certified / verified
ORANGE = (238, 106, 0)            # refused / retired
BLUE = (0, 94, 224)               # evidence / surveyed
PURPLE = (128, 62, 208)           # transient (dashed)
CYAN = (0, 168, 200)              # active / running
AMBER = (210, 130, 35)            # attempted, not certified
PENDING_OUTLINE = (178, 178, 178)  # planned, no committed pose
RULE = (176, 181, 186)

# Region identity hues (pane A tint), v1 table unchanged.
HUES = (
    (96, 165, 250), (52, 211, 153), (251, 191, 36), (248, 113, 113),
    (167, 139, 250), (45, 212, 191), (251, 146, 60), (232, 121, 249),
    (163, 230, 53), (125, 211, 252), (253, 164, 175), (196, 181, 253),
)

# Two-tone chips: soft fill + darker same-hue outline (v1 user declaration
# 2026-07-31). Deep red stays reserved for contradiction and is unused
# here — holo2 makes a conflicting certificate fatal at the commit layer,
# so no pane can be in a position to paint one.
CHIP_GREEN = ((118, 196, 130), (25, 120, 55))     # CERTIFIED
CHIP_BLUE = ((120, 175, 225), (30, 105, 175))     # evidence present
CHIP_REACH = ((198, 220, 246), (152, 186, 224))   # ADDRESSED
CHIP_AMBER = ((250, 198, 110), (210, 130, 35))    # ATTEMPTED
CHIP_UNSEEN = ((238, 238, 238), (216, 216, 216))  # UNKNOWN
CHIP_NEUTRAL = ((233, 233, 233), (209, 209, 209))  # unseen sibling stream
CHIP_TEXT = (20, 20, 20)

TITLE_FILL = (238, 240, 243)
TITLE_TEXT = (35, 40, 45)


@lru_cache(maxsize=None)
def font(size: int):
    """The panel font: DejaVu/Arial truetype where present, else default."""
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:                      # pragma: no cover - old Pillow
        return ImageFont.load_default()


@lru_cache(maxsize=4096)
def glyph(size: int, text: str):
    """Pre-rendered FreeType mask + offset; identical to ``draw.text``."""
    return font(size).getmask2(text)


def blit_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
              fill: tuple[int, int, int], size: int) -> None:
    """Bit-exact ``draw.text`` via the cached mask (v1 measured 30x cheaper)."""
    mask, offset = glyph(size, text)
    ink = draw._getink(fill)[0]
    if ink is not None:
        draw.draw.draw_bitmap((xy[0] + offset[0], xy[1] + offset[1]),
                              mask, ink)


def mask_edge(mask: np.ndarray) -> np.ndarray:
    """4-neighbour boundary of a boolean mask (holes stay outlined)."""
    padded = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), bool)
    padded[1:-1, 1:-1] = mask
    inner = (padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1]
             & padded[1:-1, :-2] & padded[1:-1, 2:])
    return mask & ~inner


def resize_mask(mask: np.ndarray, size_wh: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resample of a boolean mask to ``(w, h)`` pane px."""
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
    """One pane's canvas: fixed size, RGB, drawn through Pillow."""

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

    def clip(self, box: tuple[int, int, int, int]
             ) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        return (max(0, min(x0, self.width - 1)),
                max(0, min(y0, self.height - 1)),
                max(1, min(x1, self.width - 1)),
                max(1, min(y1, self.height - 1)))

    def rect(self, box, *, outline=None, fill=None, width: int = 1) -> None:
        self.draw.rectangle(self.clip(box), outline=outline, fill=fill,
                            width=width)

    def dashed(self, box, color, dash: int = 4) -> None:
        dashed_rect(self.draw, self.clip(box), color, dash)

    def text(self, xy: tuple[int, int], value: str,
             fill: tuple[int, int, int] = TEXT, size: int = 11) -> None:
        blit_text(self.draw, (int(xy[0]), int(xy[1])), value, fill, size)

    def rows(self, x: int, y: int, lines, *, size: int = 11) -> int:
        """Write a block of lines; returns the y below the last one.

        A line may be a plain string or ``(text, colour)``; nothing here
        wraps, because a pane whose text needs wrapping is a pane whose
        content is wrong. ``lines`` is materialised once, so a generator
        argument advances the cursor like a list does.
        """
        step = size + 5
        lines = tuple(lines)
        for index, line in enumerate(lines):
            value, colour = line if isinstance(line, tuple) else (line, TEXT)
            self.text((x, y + index * step), value, colour, size)
        return y + len(lines) * step

    def bar(self, box: tuple[int, int, int, int], fraction: float, *,
            fill: tuple[int, int, int], track=CHIP_UNSEEN[0]) -> None:
        """A horizontal progress bar with a clamped fraction."""
        x0, y0, x1, y1 = self.clip(box)
        self.draw.rectangle((x0, y0, x1, y1), fill=track, outline=RULE)
        share = 0.0 if not np.isfinite(fraction) else min(1.0, max(0.0,
                                                                   fraction))
        if share <= 0.0:
            return
        end = x0 + max(1, int(round((x1 - x0) * share)))
        self.draw.rectangle((x0, y0, min(end, x1), y1), fill=fill)


class TileGrid:
    """Pane geometry for a ``tiles_yx`` chip grid (v1 PaneRenderer, stripped)."""

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
        """One stream's slice of an INCLUSIVE tile box.

        ``box`` already ends on the tile's last pixel, so the span is
        ``x1 - x0 + 1``; the v1 bug of subtracting another pixel from the
        final segment left one background column per tile column.
        """
        x0, y0, x1, y1 = box
        span = x1 - x0 + 1
        sx0 = x0 + round(index * span / n_streams)
        sx1 = x0 + round((index + 1) * span / n_streams) - 1
        return sx0, y0, max(sx0, sx1), y1

    def count_font(self) -> int | None:
        """ONE pane-wide count font (§10.3.3), or None if nothing fits.

        A per-label fallback would print ``100`` smaller than ``42`` in the
        same pane, which is exactly what the rule forbids. The widest label
        a count chip can carry is ``999`` (pane B clamps to it).
        """
        tile_y, tile_x = self.tiles_yx
        room_x = round(self.width / tile_x) - 4
        room_y = round(self.height / tile_y) - 3
        for size in range(11, 5, -1):
            mask, _offset = glyph(size, "999")
            if mask.size[0] <= room_x and mask.size[1] <= room_y:
                return size
        return None

    def base(self) -> Pane:
        """The ruled untouched grid, so a tile pane always shows page shape.

        Ruled lines cost O(tiles_y + tiles_x) calls, not one rectangle per
        tile; each line lands on a tile's own last row/column, so a chip
        drawn later replaces it exactly.
        """
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


def compose(rasters: tuple[np.ndarray, ...], titles: tuple[str, ...],
            *, title_height: int, title_size: int) -> bytes:
    """The §10.3.1 frame: equal panes in one horizontal row under headings.

    Pane bodies arrive as finished rasters, so composition is one paste
    plus the fixed headings — no pane is re-rendered to publish a frame.
    """
    height = max(raster.shape[0] for raster in rasters)
    width = max(raster.shape[1] for raster in rasters)
    canvas = np.empty((title_height + height, len(rasters) * width, 3),
                      np.uint8)
    canvas[:] = BG
    for index, raster in enumerate(rasters):
        x0 = index * width
        canvas[title_height:title_height + raster.shape[0],
               x0:x0 + raster.shape[1]] = raster
    image = Image.fromarray(canvas)
    draw = ImageDraw.Draw(image)
    for index, title in enumerate(titles[:len(rasters)]):
        x0 = index * width
        draw.rectangle((x0, 0, x0 + width - 1, title_height - 1),
                       fill=TITLE_FILL, outline=RULE)
        blit_text(draw, (x0 + 7, max(1, (title_height - title_size) // 2 - 1)),
                  title, TITLE_TEXT, title_size)
    return encode_png(np.asarray(image))


__all__ = [
    "AMBER", "BG", "BLUE", "CHIP_AMBER", "CHIP_BLUE", "CHIP_GREEN",
    "CHIP_NEUTRAL", "CHIP_REACH", "CHIP_TEXT", "CHIP_UNSEEN",
    "CYAN", "GREEN", "HUES", "MUTED", "ORANGE", "PENDING_OUTLINE", "PURPLE",
    "RULE", "TEXT", "TITLE_FILL", "TITLE_TEXT", "Pane",
    "TileGrid", "blit_text", "compose", "dashed_rect", "encode_png", "font",
    "glyph", "mask_edge", "resize_mask",
]

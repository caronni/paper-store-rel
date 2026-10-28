"""holo format-v1 page layout: field derivation, borders, tile counters.

FORMAT-AXIS (HOLO-DESIGN §4.1, decisions F1/F11/F12). A format row's page
geometry is derived here: the largest field of 64x64-cell tiles that fits
inside the media minus the per-edge payload-safe margin, computed on the
printer's 600 dpi dot grid; axis slack is split across the two borders as
evenly as the dot grid allows, with the odd dot going to bottom/right.

Provenance: the A4 page raster (4960 x 7016 dots) matches paperholo
compose.py's frozen ``A4_W_DOTS, A4_H_DOTS`` constants. The general rule
``page_dots_xy`` rounds each axis to the nearest multiple of 8 dots
(byte-aligned rows for the 1-bit PostScript imagemask, F15); it reproduces
those constants exactly. The 6.0 mm default margin is the pre-Phase-C
policy of HOLO-DESIGN §4.1. The flat tile counter
``c = page * tiles_per_page + ty * tiles_x + tx`` is the F3/F12 18-bit
address word message.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

HW_DPI = 600
MM_PER_INCH = 25.4
MM_PER_DOT = MM_PER_INCH / HW_DPI
A4_MM: tuple[float, float] = (210.0, 297.0)
A3_MM: tuple[float, float] = (297.0, 420.0)
MEDIA_MM: dict[str, tuple[float, float]] = {"a4": A4_MM, "a3": A3_MM}
TILE_CELLS = 64                # tile edge, cells (F1)
VALID_CELL_DOTS = (2, 3, 4)    # c2 / c3 / c4 (§4.1; FORMAT-SPACE §4)
COUNTER_BITS = 18              # F12: flat tile counter width
MAX_TILES = 1 << COUNTER_BITS
DEFAULT_MARGIN_MM = 6.0        # pre-Phase-C margin policy (§4.1)


def page_dots_xy(media_mm: tuple[float, float]) -> tuple[int, int]:
    """Page raster size in dots, (x, y): nearest multiple of 8 per axis.

    A4 (210.0, 297.0) -> (4960, 7016), matching paperholo compose.py.
    """
    w_mm, h_mm = media_mm
    if not (w_mm > 0 and h_mm > 0):
        raise ValueError(f"media_mm must be positive, got {media_mm}")

    def axis(mm: float) -> int:
        return 8 * int(math.floor(mm / MM_PER_INCH * HW_DPI / 8 + 0.5))

    return axis(w_mm), axis(h_mm)


def split_slack(slack_dots: int) -> tuple[int, int]:
    """Split one axis' slack across its two borders.

    Returns (top_or_left, bottom_or_right); the odd dot goes to
    bottom/right (§4.1: origin = slack // 2).
    """
    if slack_dots < 0:
        raise ValueError(f"negative slack {slack_dots}")
    before = slack_dots // 2
    return before, slack_dots - before


@dataclass(frozen=True)
class FieldLayout:
    """Derived page geometry for one (media, margin, cell size) row."""
    cell_dots: int
    cells_yx: tuple[int, int]        # field size in cells (rows, cols)
    tiles_yx: tuple[int, int]        # 64-cell tiles (rows, cols)
    origin_dots_yx: tuple[int, int]  # field top-left on the page raster
    field_dots_yx: tuple[int, int]   # field size in dots
    page_dots_xy: tuple[int, int]    # full page raster (x, y)
    border_top_mm: float
    border_bottom_mm: float
    border_left_mm: float
    border_right_mm: float
    tile_pitch_mm: float

    @property
    def tiles_per_page(self) -> int:
        ty, tx = self.tiles_yx
        return ty * tx


def derive_field(media_mm: tuple[float, float] = A4_MM,
                 margin_mm: float = DEFAULT_MARGIN_MM,
                 cell_dots: int = 2) -> FieldLayout:
    """Largest 64-tile-quantized field inside media minus margins (§4.1).

    Per axis, in dots: usable = page - 2*ceil(margin_mm in dots);
    field cells = (usable // cell_dots) // 64 * 64.
    """
    if cell_dots not in VALID_CELL_DOTS:
        raise ValueError(f"cell_dots must be one of {VALID_CELL_DOTS}, "
                         f"got {cell_dots}")
    if not (margin_mm >= 0 and math.isfinite(margin_mm)):
        raise ValueError(f"margin_mm must be finite and >= 0, got {margin_mm}")
    page_x, page_y = page_dots_xy(media_mm)
    margin_dots = math.ceil(margin_mm / MM_PER_INCH * HW_DPI)

    def field_cells(page_axis_dots: int) -> int:
        usable_dots = page_axis_dots - 2 * margin_dots
        if usable_dots < cell_dots * TILE_CELLS:
            raise ValueError(
                f"media {media_mm} mm too small for one {TILE_CELLS}-cell "
                f"tile at cell_dots={cell_dots} inside {margin_mm} mm margins")
        return (usable_dots // cell_dots) // TILE_CELLS * TILE_CELLS

    cells_y = field_cells(page_y)
    cells_x = field_cells(page_x)
    tiles_yx = (cells_y // TILE_CELLS, cells_x // TILE_CELLS)
    if tiles_yx[0] * tiles_yx[1] > MAX_TILES:
        raise ValueError(f"tiles {tiles_yx} exceed the {COUNTER_BITS}-bit "
                         "counter space on a single page")
    field_y = cells_y * cell_dots
    field_x = cells_x * cell_dots
    top, bottom = split_slack(page_y - field_y)
    left, right = split_slack(page_x - field_x)
    return FieldLayout(
        cell_dots=cell_dots,
        cells_yx=(cells_y, cells_x),
        tiles_yx=tiles_yx,
        origin_dots_yx=(top, left),
        field_dots_yx=(field_y, field_x),
        page_dots_xy=(page_x, page_y),
        border_top_mm=top * MM_PER_DOT,
        border_bottom_mm=bottom * MM_PER_DOT,
        border_left_mm=left * MM_PER_DOT,
        border_right_mm=right * MM_PER_DOT,
        tile_pitch_mm=TILE_CELLS * cell_dots * MM_PER_DOT,
    )


def tile_counter(page: int, ty: int, tx: int,
                 tiles_yx: tuple[int, int]) -> int:
    """Flat tile counter c = page*tiles_per_page + ty*tiles_x + tx (§4.3)."""
    tiles_y, tiles_x = tiles_yx
    if tiles_y <= 0 or tiles_x <= 0:
        raise ValueError(f"invalid tiles_yx {tiles_yx}")
    if not (0 <= ty < tiles_y and 0 <= tx < tiles_x):
        raise ValueError(f"tile ({ty},{tx}) outside grid {tiles_yx}")
    if page < 0:
        raise ValueError(f"negative page {page}")
    c = page * (tiles_y * tiles_x) + ty * tiles_x + tx
    if c >= MAX_TILES:
        raise ValueError(f"tile counter {c} exceeds {COUNTER_BITS} bits (F12)")
    return c


def tile_address(counter: int,
                 tiles_yx: tuple[int, int]) -> tuple[int, int, int]:
    """Inverse of tile_counter: counter -> (page, ty, tx)."""
    tiles_y, tiles_x = tiles_yx
    if tiles_y <= 0 or tiles_x <= 0:
        raise ValueError(f"invalid tiles_yx {tiles_yx}")
    if not 0 <= counter < MAX_TILES:
        raise ValueError(f"counter {counter} outside 0..{MAX_TILES - 1}")
    page, rem = divmod(counter, tiles_y * tiles_x)
    ty, tx = divmod(rem, tiles_x)
    return page, ty, tx

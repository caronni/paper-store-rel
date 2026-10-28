import sys; from pathlib import Path

import pytest

from holo.format.layout import (
    A4_MM, DEFAULT_MARGIN_MM, HW_DPI, MAX_TILES, MM_PER_DOT, TILE_CELLS,
    derive_field, page_dots_xy, split_slack, tile_address, tile_counter,
)

MM_TOL = 0.05  # assignment: 0.05 mm tolerance on mm reports


def test_constants():
    assert HW_DPI == 600
    assert A4_MM == (210.0, 297.0)
    assert TILE_CELLS == 64
    assert MAX_TILES == 262144


def test_page_dots_a4_matches_paperholo_convention():
    # paperholo compose.py: A4_W_DOTS, A4_H_DOTS = 4960, 7016
    assert page_dots_xy(A4_MM) == (4960, 7016)


def test_a4_c2_design_row():
    f = derive_field(A4_MM, 6.0, cell_dots=2)
    assert f.cells_yx == (3328, 2304)          # exact per HOLO-DESIGN §4.1
    assert f.tiles_yx == (52, 36)
    assert f.tiles_per_page == 1872
    assert f.field_dots_yx == (3328 * 2, 2304 * 2)
    assert abs(f.border_top_mm - 7.62) <= MM_TOL
    assert abs(f.border_bottom_mm - 7.62) <= MM_TOL
    assert abs(f.border_left_mm - 7.45) <= MM_TOL
    assert abs(f.border_right_mm - 7.45) <= MM_TOL
    assert abs(f.tile_pitch_mm - 5.42) <= MM_TOL


def test_a4_c3_design_row():
    f = derive_field(A4_MM, 6.0, cell_dots=3)
    assert f.cells_yx == (2240, 1536)
    assert f.tiles_yx == (35, 24)
    assert f.tiles_per_page == 840
    assert f.field_dots_yx == (2240 * 3, 1536 * 3)
    assert abs(f.border_top_mm - 6.26) <= MM_TOL
    assert abs(f.border_bottom_mm - 6.26) <= MM_TOL
    assert abs(f.border_left_mm - 7.45) <= MM_TOL
    assert abs(f.border_right_mm - 7.45) <= MM_TOL
    assert abs(f.tile_pitch_mm - 8.13) <= MM_TOL


def test_defaults_are_a4_6mm():
    assert derive_field(cell_dots=2) == derive_field(A4_MM, DEFAULT_MARGIN_MM, 2)


@pytest.mark.parametrize("cell_dots", [2, 3, 4])
def test_field_geometry_consistent(cell_dots):
    f = derive_field(A4_MM, 6.0, cell_dots)
    page_x, page_y = f.page_dots_xy
    oy, ox = f.origin_dots_yx
    fy, fx = f.field_dots_yx
    # cells quantized to whole tiles, dots consistent with cells
    assert all(c % TILE_CELLS == 0 for c in f.cells_yx)
    assert (fy, fx) == (f.cells_yx[0] * cell_dots, f.cells_yx[1] * cell_dots)
    # borders account for the whole page raster, in dots exactly
    assert oy + fy + round(f.border_bottom_mm / MM_PER_DOT) == page_y
    assert ox + fx + round(f.border_right_mm / MM_PER_DOT) == page_x
    assert abs(f.border_top_mm - oy * MM_PER_DOT) < 1e-9
    # field sits inside the requested margins on all four sides
    for b in (f.border_top_mm, f.border_bottom_mm,
              f.border_left_mm, f.border_right_mm):
        assert b >= 6.0 - 1e-9


def test_split_slack_even_and_odd():
    assert split_slack(360) == (180, 180)
    assert split_slack(361) == (180, 181)   # odd dot to bottom/right
    assert split_slack(1) == (0, 1)
    assert split_slack(0) == (0, 0)
    with pytest.raises(ValueError):
        split_slack(-1)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        derive_field(A4_MM, 6.0, cell_dots=1)
    with pytest.raises(ValueError):
        # c4 became lawful with FORMAT-SPACE (e033 sheet A); 5 is not.
        derive_field(A4_MM, 6.0, cell_dots=5)
    with pytest.raises(ValueError):
        derive_field(A4_MM, -1.0, cell_dots=2)
    with pytest.raises(ValueError):
        derive_field((15.0, 15.0), 6.0, cell_dots=2)   # too small for a tile
    with pytest.raises(ValueError):
        derive_field((15.0, 297.0), 6.0, cell_dots=2)  # one axis too small
    with pytest.raises(ValueError):
        page_dots_xy((0.0, 297.0))


def test_counter_formula_and_round_trip():
    tiles_yx = (35, 24)
    tpp = 35 * 24
    assert tile_counter(0, 0, 0, tiles_yx) == 0
    assert tile_counter(0, 0, 1, tiles_yx) == 1
    assert tile_counter(0, 1, 0, tiles_yx) == 24
    assert tile_counter(3, 7, 5, tiles_yx) == 3 * tpp + 7 * 24 + 5
    for c in [0, 1, 23, 24, 839, 840, 12345, MAX_TILES - 1]:
        page, ty, tx = tile_address(c, tiles_yx)
        assert tile_counter(page, ty, tx, tiles_yx) == c
    for page in range(3):
        for ty in (0, 17, 34):
            for tx in (0, 11, 23):
                c = tile_counter(page, ty, tx, tiles_yx)
                assert tile_address(c, tiles_yx) == (page, ty, tx)


def test_counter_range_validation():
    tiles_yx = (52, 36)
    with pytest.raises(ValueError):
        tile_counter(0, 52, 0, tiles_yx)
    with pytest.raises(ValueError):
        tile_counter(0, 0, 36, tiles_yx)
    with pytest.raises(ValueError):
        tile_counter(0, -1, 0, tiles_yx)
    with pytest.raises(ValueError):
        tile_counter(-1, 0, 0, tiles_yx)
    # F12: the counter must fit 18 bits; a4-c2 crosses 2^18 within page 140
    assert tile_counter(140, 1, 27, tiles_yx) == MAX_TILES - 1
    with pytest.raises(ValueError):
        tile_counter(140, 1, 28, tiles_yx)
    with pytest.raises(ValueError):
        tile_address(MAX_TILES, tiles_yx)
    with pytest.raises(ValueError):
        tile_address(-1, tiles_yx)
    with pytest.raises(ValueError):
        tile_counter(0, 0, 0, (0, 36))

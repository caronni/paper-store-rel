"""Cell/pixel geometry conventions (DESIGN §5.3, §6, §8.2).

The affine convention, the pose-free capture-cell lattice, the v1-shaped
window lattice, and the cell-granular run representation §6 requires.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from holo2.solve.geometry import (CellLattice, LAYOUT_MIN_WINDOW_CELLS,
                                  TILE_CELLS, WINDOW_CELLS, WINDOW_STEP_CELLS,
                                  affine_matrix, affine_terms, apply_affine,
                                  contains_rect, invert_affine, runs_of_mask,
                                  scale_translation_affine, tile_cell_rect,
                                  tile_of_cell, window_starts)
AFFINE = scale_translation_affine(3.0, (61.0, 97.0))


def test_affine_convention_is_cells_to_native() -> None:
    """Cell (0,0)'s corner is the page origin; one cell steps ``pitch`` px."""
    y, x = apply_affine(AFFINE, np.array([0.0, 1.0]), np.array([0.0, 2.0]))
    assert list(y) == [61.0, 64.0]
    assert list(x) == [97.0, 103.0]


def test_affine_round_trips_through_its_inverse() -> None:
    inverse = invert_affine(AFFINE)
    cells_y = np.array([0.0, 17.5, 511.0])
    cells_x = np.array([0.0, 3.25, 500.0])
    native_y, native_x = apply_affine(AFFINE, cells_y, cells_x)
    back_y, back_x = apply_affine(inverse, native_y, native_x)
    np.testing.assert_allclose(back_y, cells_y, atol=1e-9)
    np.testing.assert_allclose(back_x, cells_x, atol=1e-9)


def test_rotated_affine_round_trips_too() -> None:
    """The inverse is a real matrix inverse, not a scale/offset shortcut."""
    rotated = (2.9, 0.12, 61.0, -0.09, 3.05, 97.0)
    inverse = invert_affine(rotated)
    y, x = apply_affine(rotated, np.array([7.0]), np.array([11.0]))
    back_y, back_x = apply_affine(inverse, y, x)
    np.testing.assert_allclose([back_y[0], back_x[0]], [7.0, 11.0], atol=1e-9)


def test_singular_affine_is_refused() -> None:
    with pytest.raises(ValueError):
        invert_affine((0.0, 0.0, 1.0, 0.0, 0.0, 2.0))


def test_affine_matrix_round_trip() -> None:
    assert affine_terms(affine_matrix(AFFINE)) == AFFINE
    with pytest.raises(ValueError):
        affine_matrix((1.0, 2.0, 3.0))


def test_lattice_centres_are_cell_centres() -> None:
    lattice = CellLattice.over((59, 94), (1539, 1542), Fraction(3))
    assert lattice.shape_cells == (513, 514)
    assert lattice.centres_y(0, 2).tolist() == [60.5, 63.5]
    assert lattice.centres_x(0, 1).tolist() == [95.5]


def test_lattice_refuses_a_nonpositive_pitch() -> None:
    with pytest.raises(ValueError):
        CellLattice((0, 0), Fraction(0), (4, 4))


def test_window_lattice_shifts_its_last_window_flush() -> None:
    """The alignment ruling: the last start is pulled in, never clipped.

    513 cells at size 256 / step 128: ``range(0, 513-256+1, 128)`` is
    0, 128, 256 and the flush start is 513-256 = 257, which is not 256,
    so it is appended — four windows, every one a full 256, and the last
    two overlap by 255 cells rather than leaving a 1-cell remainder.
    """
    assert window_starts(513, 256, 128) == (0, 128, 256, 257)
    assert all(513 - start >= 256 for start in window_starts(513, 256, 128))
    # the production geometry, on the differential's own region heights:
    # 520 = 320 + 200 lands the flush start ON a step (no extra window),
    # 513 and 451 do not (313 = 513-200, 251 = 451-200).
    assert window_starts(520) == (0, 160, 320)
    assert window_starts(513) == (0, 160, 313)
    assert window_starts(451) == (0, 160, 251)
    assert window_starts(642) == (0, 160, 320, 442)


def test_window_lattice_keeps_a_short_axis_whole_above_the_floor() -> None:
    """An axis shorter than one window is ONE window, down to 8 cells."""
    assert window_starts(300, 256, 128) == (0, 44)      # 300 - 256
    assert window_starts(256, 256, 128) == (0,)
    assert window_starts(32, 256, 128) == (0,)
    # v1's sliver rule, the only floor a flush lattice can reach.
    assert LAYOUT_MIN_WINDOW_CELLS == 8
    assert window_starts(8) == (0,)
    assert window_starts(7) == ()


def test_window_lattice_reproduces_the_carried_layout_function() -> None:
    """The alignment ruling's bar: these starts ARE v1's, in the cell frame.

    The expected origins below were FROZEN from ``layout_pose_windows``
    — v1's pixel-frame layout, deleted by user ruling 2026-08-17 —
    verified equal to this lattice's output on the day of the deletion.
    They remain an INDEPENDENT reference: hand-derivable as v1's
    flush-shifted starts times the pitch, and any drift in
    ``window_starts`` breaks the comparison against values no current
    code produces. The equivalence held only where the region's pixel
    extent is ``pitch * n_cells`` AND ``step * pitch`` is integral —
    ``pitch = 4.0`` satisfies both (``WINDOW_STEP_CELLS * pitch ==
    640``); a non-integral ``step * pitch`` (any real capture's pitch,
    routinely) was never covered by the carried function either — see
    ``geometry.window_starts`` for the divergence that opens then.
    """
    pitch = 4.0
    frozen = {
        (520, 517): [(0, 0), (0, 640), (0, 1268), (640, 0), (640, 640),
                     (640, 1268), (1280, 0), (1280, 640), (1280, 1268)],
        (513, 514): [(0, 0), (0, 640), (0, 1256), (640, 0), (640, 640),
                     (640, 1256), (1252, 0), (1252, 640), (1252, 1256)],
        (451, 642): [(0, 0), (0, 640), (0, 1280), (0, 1768), (640, 0),
                     (640, 640), (640, 1280), (640, 1768), (1004, 0),
                     (1004, 640), (1004, 1280), (1004, 1768)],
        (200, 8): [(0, 0)],
    }
    for (rows, cols), expected in frozen.items():
        mine = [(int(round(cy0 * pitch)), int(round(cx0 * pitch)))
                for cy0 in window_starts(rows, WINDOW_CELLS,
                                         WINDOW_STEP_CELLS)
                for cx0 in window_starts(cols, WINDOW_CELLS,
                                         WINDOW_STEP_CELLS)]
        assert sorted(mine) == expected, (rows, cols)


def test_tile_addressing_helpers() -> None:
    ty, tx = tile_of_cell(np.array([0, 63, 64]), np.array([128, 191, 192]))
    assert ty.tolist() == [0, 0, 1]
    assert tx.tolist() == [2, 2, 3]
    assert tile_cell_rect(1, 2) == (64, 128, 128, 192)
    assert TILE_CELLS == 64


def test_contains_rect_is_half_open() -> None:
    assert contains_rect((-0.5, -0.5, 255.5, 255.5), (0, 0, 64, 64))
    assert not contains_rect((0.5, 0.0, 255.5, 255.5), (0, 0, 64, 64))
    assert not contains_rect((0.0, 0.0, 63.5, 255.5), (0, 0, 64, 64))


def test_runs_of_mask_is_the_cell_granular_representation() -> None:
    mask = np.zeros((3, 8), bool)
    mask[0, 1:4] = True
    mask[0, 6:8] = True
    mask[2, :] = True
    assert runs_of_mask(mask) == ((0, 1, 4), (0, 6, 8), (2, 0, 8))
    assert runs_of_mask(np.zeros((2, 2), bool)) == ()


def test_runs_of_mask_refuses_a_non_2d_mask() -> None:
    with pytest.raises(ValueError):
        runs_of_mask(np.ones(4, bool))

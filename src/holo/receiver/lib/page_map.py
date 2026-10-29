"""The one mapping from a page cell to the pixel a plane is read at.

Page space is where the field lives, the raster is where the evidence
is, and this module is the only thing in the receiver that joins them
(design §2.8, invariant I7).  A window's pose maps its own LOCAL cells
to pixels; the field is a displacement along the PAGE axes, in printed
dots; and a scrap read at rot 1 must say the same thing about the same
page as one read at rot 0.  Every consumer that applies a field —
the colour lane's read, the plane-as-K read, the swim's search, the
pose refinement — comes through here, so the frame algebra is written
once and every reader inherits the same answer.

  page cell --evaluate--> delta in PAGE dots --page_linear--> pixels

`page_linear` is a window's PAGE-cell -> pixel 2x2, which
`color_region.region_window` composes as `level_terms[:, :2]` and
carries on the window; it equals `pose_linear(affine) @ rotation.T`
exactly, and it carries the scrap's orientation, scale and shear in one
step.  `rotation` is the same window's LOCAL-cell -> page-cell
quarter-turn.  A consumer whose search space is the window's own frame
(the swim's local affine, `refine.color`'s candidate poses) converts
with `local_axes` and `page_axes` and nothing else.

THE INVERSE — pixel to page cell — is one Newton step off
`page_linear`'s inverse with the field subtracted at the estimate, and
NOBODY CALLS IT.  It is not built: the consumers of this wave all hold
a page position already.  The cold search is the reader that will want
it, and its door is on the forward side: `plugins/pose.sample_segment`
and `plugins/refine.sample_at` both take an `offsets_px` this module's
`raster_points` would fill from a page hypothesis, and both are unused
today (design §5, PAGE-FIELD-PLAN §3).
"""

from __future__ import annotations

import numpy as np

from . import plane_field
from .geometry import TILE_CELLS


def plane_delta_dots(field, page_cells_yx: np.ndarray) -> np.ndarray:
    """One standing plane field, evaluated per cell, in PAGE-axis dots.

    Bilinear on the tile grid (I11), and per CELL rather than once per
    tile or window: the AltaLink's sinusoid reaches 0.28 dots per tile.
    A tile no evidence ever reached reads exactly zero, which is the
    pose — there is no support gate and no refusal (I6, I8).

    `field` carries no annotation because nothing under `lib/` imports
    the receiver's data model; it is DUCK-TYPED to `.delta_dots_xy` and
    reads nothing else off the fact.  `test_h3_page_map` puts a real
    `PlaneField` through this door so the duck is checked against the
    bird once.
    """
    return plane_field.evaluate(
        np.asarray(field.delta_dots_xy, np.float64), page_cells_yx,
        TILE_CELLS)


def raster_points(scan_points_yx: np.ndarray, page_linear: np.ndarray,
                  delta_dots_xy: np.ndarray,
                  cell_dots: int) -> np.ndarray:
    """`(N, 2)` sample points displaced by a per-cell PAGE-axis delta.

    The delta is `(N, 2)` in printed DOTS, x then y — the unit every
    field, tier and hint speaks.  Dots become page cells through
    `cell_dots` and page cells become pixels through `page_linear`, so
    a one-dot field moves the sampler one dot along the named page axis
    whatever the window's rotation (I2).
    """
    delta = np.asarray(delta_dots_xy, np.float64)[:, ::-1] / float(cell_dots)
    return (np.asarray(scan_points_yx, np.float64)
            + delta @ np.asarray(page_linear, np.float64).T)


def raster_point_grid(scan_points_yx: np.ndarray, page_linear: np.ndarray,
                      offsets_dots_xy: np.ndarray,
                      cell_dots: int) -> np.ndarray:
    """`(S, N, 2)`: N points at each of S UNIFORM page-axis offsets.

    The correlation tiers sweep one offset over a whole template and
    score hundreds of candidates; moving the points once per candidate
    is the same arithmetic `raster_points` does, broadcast instead of
    looped.
    """
    offsets = np.asarray(offsets_dots_xy, np.float64)
    delta = ((offsets[:, ::-1] / float(cell_dots))
             @ np.asarray(page_linear, np.float64).T)
    return np.asarray(scan_points_yx, np.float64)[None, :, :] \
        + delta[:, None, :]


def _in_frame(delta_xy: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    given = np.asarray(delta_xy, np.float64)
    delta = np.atleast_2d(given)
    moved = np.ascontiguousarray(
        (delta[:, ::-1] @ np.asarray(matrix, np.float64).T)[:, ::-1])
    return moved[0] if given.ndim == 1 else moved


def page_axes(delta_local_xy: np.ndarray,
              rotation: np.ndarray) -> np.ndarray:
    """A window-LOCAL-axis delta, expressed along the PAGE axes.

    `rotation` takes local cell coordinates to page cell coordinates,
    so it takes a local displacement to a page one; the reversals are
    the (x, y) delta convention meeting the (y, x) coordinate one.
    """
    return _in_frame(delta_local_xy, rotation)


def local_axes(delta_page_xy: np.ndarray,
               rotation: np.ndarray) -> np.ndarray:
    """A PAGE-axis delta, expressed along one window's LOCAL axes.

    The inverse of `page_axes`, and a quarter-turn is orthogonal, so it
    is the transpose.  A consumer searching in the window's own frame
    converts the standing field down with this, searches, and converts
    the answer back up.
    """
    return _in_frame(delta_page_xy, np.asarray(rotation, np.float64).T)

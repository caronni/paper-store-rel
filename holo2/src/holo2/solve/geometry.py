"""Cell/pixel geometry for the spine (DESIGN §5.3, §6, §8.2).

Pure arithmetic: no store, no records, no policy beyond the two v1-shaped
window constants. That is the whole lattice/affine vocabulary — the
affine convention and its inverse, the pose guesses a search enumerates
(``orientation_linear``, ``anchored_affine``, ``shift_affine``), the
least-squares fits that replace them, the two support anchors, the
window↔page rects, and the tile enumeration those rects define. The
placement KERNEL (fit, sampling, the word decode) is the ported E022
kernel's — ``pose_fit``, ``pose_audit``, ``words`` — and the family that
runs it is ``placement``.

Conventions where DESIGN is silent are listed here so they can be
adjudicated.

1. **The pose affine.** ``PoseRecord.native_affine`` is the row-major 2x3
   matrix ``(a, b, c, d, e, f)`` with
   ``native_y = a*cell_y + b*cell_x + c`` and
   ``native_x = d*cell_y + e*cell_x + f``.  Both sides are *continuous
   edge* coordinates: cell ``(cy, cx)`` names the corner of the cell whose
   interior is ``[cy, cy+1) x [cx, cx+1)``, and native ``(y, x)`` the
   corner of the pixel whose interior is ``[y, y+1) x [x, x+1)``.  The
   cell frame is the PAGE cell lattice — the addressing frame — never a
   capture's own lattice.  A pose is therefore exactly the
   physical→logical correspondence of DESIGN §1.
2. **The capture-cell lattice.** A window has to be named *before* any
   pose exists, so it is defined on a pose-free grid: origin at the
   region's support bbox corner, step = the capture's cell pitch in native
   pixels (``pitch_in_vote * dpi_true``, exact rational).  This grid
   is a property of (capture, region) and is shared by every footing of
   that capture — footings differ in sampling, not in physical cell size.
3. **``WindowRecord.extent_cells``** is ``(cy0, cx0, cy1, cx1)``,
   half-open, in that capture-cell lattice.
4. **Window geometry is the measured E022 lattice** (§8.2): one nominal
   size, one step, and — since the H4 window-alignment ruling — a last
   window SHIFTED FLUSH against the far edge instead of clipped by it,
   which is v1's own layout read in the cell frame
   (:func:`window_starts`).  Since H4 W1 the numbers are the OR-9
   table's, not the H2 spine's stand-ins — see below.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .place_model import (E022_LAYOUT_MIN_WINDOW_CELLS, E022_OVERLAP_CELLS,
                          E022_WINDOW_CELLS)

TILE_CELLS = 64                  # format v1, F1 (carried constant)

# THE WINDOW LATTICE, OR-9 (H4 W1). The three H2 spine stand-ins
# (256 / 128 / one tile) are retired exactly as ``OR9_FLOORS`` says they
# are: the qualified E022 geometry is a 200-cell window with 40 cells of
# overlap — hence a 160-cell step. This is not decoration: the word
# route's declared Stage-A domain is the count for a
# ``PlacementConfig.window_cells`` square (147,456 at 200), so a 256-cell
# window declares 262,144 hypotheses and every one of them refuses on
# ``attempt_budget_exceeded`` — measured, W1. The admission algebra has
# to describe the windows that actually exist.
#
# The layout FLOOR is v1's own sliver rule (8 cells), not the 70-cell
# subdivision retry floor the H2 spine reached for: since the
# window-alignment ruling the last window is shifted flush rather than
# clipped, so no start ever produces a remainder for a floor to judge.
WINDOW_CELLS = E022_WINDOW_CELLS
WINDOW_STEP_CELLS = E022_WINDOW_CELLS - E022_OVERLAP_CELLS
LAYOUT_MIN_WINDOW_CELLS = E022_LAYOUT_MIN_WINDOW_CELLS


@dataclass(frozen=True, slots=True)
class CellLattice:
    """One region's pose-free capture-cell grid (convention 2 above)."""

    origin_yx: tuple[int, int]
    pitch_px: Fraction
    shape_cells: tuple[int, int]

    def __post_init__(self) -> None:
        if self.pitch_px <= 0:
            raise ValueError("cell pitch must be positive")
        if min(self.shape_cells) < 1:
            raise ValueError("a lattice has at least one cell")

    @classmethod
    def over(cls, origin_yx: tuple[int, int], extent_px: tuple[int, int],
             pitch_px: Fraction) -> "CellLattice":
        """The lattice covering ``extent_px`` from ``origin_yx``."""
        rows = int(Fraction(extent_px[0]) / pitch_px)
        cols = int(Fraction(extent_px[1]) / pitch_px)
        return cls(origin_yx, pitch_px, (max(1, rows), max(1, cols)))

    def centres_y(self, cy0: int, cy1: int) -> np.ndarray:
        """Native y of the cell-row centres in ``[cy0, cy1)``."""
        pitch = float(self.pitch_px)
        return self.origin_yx[0] + pitch * (np.arange(cy0, cy1) + 0.5)

    def centres_x(self, cx0: int, cx1: int) -> np.ndarray:
        pitch = float(self.pitch_px)
        return self.origin_yx[1] + pitch * (np.arange(cx0, cx1) + 0.5)


def affine_matrix(terms: tuple[float, ...]) -> np.ndarray:
    """The 2x3 matrix of a 6-term affine (convention 1)."""
    if len(terms) != 6:
        raise ValueError("an affine has 6 terms")
    return np.asarray(terms, np.float64).reshape(2, 3)


def affine_terms(matrix: np.ndarray) -> tuple[float, ...]:
    """The 6-term form of a 2x3 matrix, as a durable record carries it."""
    array = np.asarray(matrix, np.float64)
    if array.shape != (2, 3):
        raise ValueError("an affine matrix has shape (2, 3)")
    return tuple(float(value) for value in array.reshape(6))


def invert_affine(terms: tuple[float, ...]) -> tuple[float, ...]:
    """The inverse map (native px -> page cells) of a pose affine."""
    matrix = affine_matrix(terms)
    linear = matrix[:, :2]
    determinant = float(np.linalg.det(linear))
    if not np.isfinite(determinant) or determinant == 0.0:
        raise ValueError("pose affine is singular; it maps no cells")
    inverse_linear = np.linalg.inv(linear)
    offset = -inverse_linear @ matrix[:, 2]
    return affine_terms(np.column_stack([inverse_linear, offset]))


def apply_affine(terms: tuple[float, ...], ys: np.ndarray, xs: np.ndarray,
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Map coordinate arrays through an affine (broadcasting elementwise)."""
    a, b, c, d, e, f = (float(value) for value in terms)
    return a * ys + b * xs + c, d * ys + e * xs + f


def scale_translation_affine(pitch_px: float, origin_yx: tuple[float, float],
                             ) -> tuple[float, ...]:
    """The axis-aligned affine of a page laid down at ``origin_yx``."""
    return (float(pitch_px), 0.0, float(origin_yx[0]),
            0.0, float(pitch_px), float(origin_yx[1]))


# ------------------------------------------------- pose guesses and fits

_ROT90 = (
    ((1.0, 0.0), (0.0, 1.0)),
    ((0.0, -1.0), (1.0, 0.0)),
    ((-1.0, 0.0), (0.0, -1.0)),
    ((0.0, 1.0), (-1.0, 0.0)),
)


def orientation_linear(pitch_px: float, orientation: int,
                       angle_deg: float) -> np.ndarray:
    """The 2x2 cells->native linear part of one pose guess."""
    angle = math.radians(float(angle_deg))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]], np.float64)
    quarter = np.asarray(_ROT90[orientation % 4], np.float64)
    return float(pitch_px) * (rotation @ quarter)


def bbox_centre_native(bbox_native: tuple[float, float, float, float],
                       ) -> tuple[float, float]:
    """The MIDPOINT of the support bbox — THE seed anchor.

    Deliberately the midpoint of the supported EXTENT and never the
    support mask's mass centroid, and the difference is not academic. On
    a sheet whose ink coverage RAMPS across the page — the e032 counting
    page is exactly that — the survey's support thins on the light side,
    which drags a mass centroid off the field centre while leaving the
    extent, and therefore this midpoint, where it belongs. Measured on
    that capture: mass centroid (-0.6, -3.3) cells off the true field
    centre against a phase grid of R = 2 cells, so every hypothesis
    missed the true phase in x; bbox midpoint (0.1, 0.7) cells off, well
    inside the grid.

    The midpoint is also rotation-exact for a rectangular printed field —
    a rotated rectangle's axis-aligned bbox is still centred on the
    rectangle's centre — so it keeps the property that made a corner
    anchor unusable in the first place.
    """
    return ((bbox_native[0] + bbox_native[2]) / 2.0,
            (bbox_native[1] + bbox_native[3]) / 2.0)


def support_mass_centroid_native(
        lattice: "CellLattice",
        support: np.ndarray) -> tuple[float, float] | None:
    """The support mask's mass centre — the anchor deliberately NOT used.

    Derived only so a refusal can report how far apart the two candidates
    were. A large gap is the coverage-ramp signature, and it is the
    difference between 'this sheet is a foreign format' and 'this sheet
    is fine and something moved the anchor'.
    """
    mask = np.asarray(support, bool)
    if not mask.any():
        return None
    rows, cols = np.nonzero(mask)
    pitch = float(lattice.pitch_px)
    return (lattice.origin_yx[0] + pitch * (float(rows.mean()) + 0.5),
            lattice.origin_yx[1] + pitch * (float(cols.mean()) + 0.5))


def anchored_affine(linear: np.ndarray, cells_yx: tuple[int, int],
                    anchor_yx: tuple[float, float]) -> tuple[float, ...]:
    """Lay the page down so its CENTRE cell sits at ``anchor_yx``."""
    centre_cell = np.array([cells_yx[0] / 2.0, cells_yx[1] / 2.0], np.float64)
    offset = np.asarray(anchor_yx, np.float64) - linear @ centre_cell
    return (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
            float(linear[1, 0]), float(linear[1, 1]), float(offset[1]))


def shift_affine(affine: tuple[float, ...], d_cell_y: float,
                 d_cell_x: float) -> tuple[float, ...]:
    """``shifted(cell) == affine(cell + d)``: move the page origin in cells."""
    a, b, c, d, e, f = (float(term) for term in affine)
    return (a, b, c + a * d_cell_y + b * d_cell_x,
            d, e, f + d * d_cell_y + e * d_cell_x)


def support_bbox_native(lattice: "CellLattice",
                        support: np.ndarray) -> tuple[float, ...] | None:
    """The supported cells' bounding box, in continuous native pixels."""
    mask = np.asarray(support, bool)
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or cols.size == 0:
        return None
    pitch = float(lattice.pitch_px)
    return (lattice.origin_yx[0] + pitch * float(rows[0]),
            lattice.origin_yx[1] + pitch * float(cols[0]),
            lattice.origin_yx[0] + pitch * float(rows[-1] + 1),
            lattice.origin_yx[1] + pitch * float(cols[-1] + 1))


def window_starts(n_cells: int, size: int = WINDOW_CELLS,
                  step: int = WINDOW_STEP_CELLS,
                  minimum: int = LAYOUT_MIN_WINDOW_CELLS) -> tuple[int, ...]:
    """Window start offsets along one axis — v1's FLUSH-SHIFTED lattice.

    THE WINDOW-ALIGNMENT RULING (H4-PLAN R12 addenda, 2026-08-15: "align
    windows to v1 behaviour. it has good reason, and we don't want to
    waste tiles!"). The last window is SHIFTED IN so that it ends flush
    against the far edge — it is a full ``size`` window like every other
    one — instead of being clipped there and then dropped for being too
    short. What the clipped lattice cost is exactly what the ruling
    names — wasted tiles, in two ways. A 451-cell axis laid out 200, 200
    and 131, so the tiles under the short one were addressed by a window
    holding a third less evidence than its siblings — the same fit, the
    same word, a worse-conditioned one of each. A 545-cell axis laid out
    200, 200, 200 and then DROPPED
    its 65-cell remainder under the (misapplied) 70-cell floor, so its
    last 25 cell rows sat in no window at all. Flush-shifted, the same
    axes lay out 200/200/200 from starts 0/160/251 and 0/160/320/345.

    This IS ``pose_fit.layout_pose_windows``' ``starts`` (v1
    ``geometry.py:500-506``), read in the capture-CELL frame instead of
    the region's pixel frame: same size, same step, same flush shift,
    same "one start" answer for an axis shorter than a window. The two
    frames agree exactly only where BOTH hold: ``pitch * n_cells`` is the
    region's pixel extent, AND ``step * pitch`` (the step in pixels) is
    itself integral. v1 quantises the STEP once
    (``round(step_cells * pitch)``) and multiplies by the window index to
    get every interior start; this lattice's starts are exact cell
    multiples that get quantised INDIVIDUALLY wherever a start is later
    converted to native pixels (``round(cy0 * pitch)`` at the call site).
    Those coincide for every index only when ``step * pitch`` is already
    an integer — otherwise interior start k diverges from v1's by
    approximately ``k * |round(step * pitch) - step * pitch|``, growing
    with distance from the origin. Every fixture in this module sits at
    ``pitch = 4.0``, where ``WINDOW_STEP_CELLS * pitch == 640`` exactly,
    so no test here exercises the divergence — but real captures land at
    non-integral pitch routinely, where the two lattices differ BY
    DESIGN, not by a bug to reconcile: a window's durable name is its
    CELL extent (§8.2 convention 3), so a start is a cell index here and
    a pixel there, and the cell lattice is the one that is durable.

    ``minimum`` is v1's sliver rule (``min(shape) < 8``, OR-9
    ``layout_min_window_cells``) and, under the flush shift, it can only
    ever bite on an axis SHORTER than one window: every other start
    yields a full ``size`` span. The 70-cell ``min_window_cells`` this
    parameter used to default to is the SUBDIVISION retry floor and was
    never a layout floor; that stand-in is retired in the OR-9 table.
    """
    if n_cells < minimum:
        return ()
    if n_cells <= size:
        return (0,)
    starts = list(range(0, n_cells - size + 1, step))
    if starts[-1] != n_cells - size:
        starts.append(n_cells - size)
    return tuple(starts)


def tile_of_cell(cell_y: np.ndarray, cell_x: np.ndarray,
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Page cell indices -> the 64-cell tile they belong to."""
    return cell_y // TILE_CELLS, cell_x // TILE_CELLS


def tile_cell_rect(ty: int, tx: int) -> tuple[int, int, int, int]:
    """The half-open page-cell rectangle of one tile."""
    return (ty * TILE_CELLS, tx * TILE_CELLS,
            (ty + 1) * TILE_CELLS, (tx + 1) * TILE_CELLS)


def contains_rect(outer: tuple[float, float, float, float],
                  inner: tuple[int, int, int, int]) -> bool:
    """Whether the half-open ``inner`` cell rect sits inside ``outer``."""
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def runs_of_mask(mask: np.ndarray) -> tuple[tuple[int, int, int], ...]:
    """Row-wise runs ``(row, c0, c1)`` of a boolean cell mask.

    The §6 representation rule: done-ness is carried as cell-granular
    runs, never as a native-resolution bitmap.
    """
    array = np.asarray(mask, bool)
    if array.ndim != 2:
        raise ValueError("a cell mask is 2-D")
    runs: list[tuple[int, int, int]] = []
    for row in range(array.shape[0]):
        line = array[row]
        if not line.any():
            continue
        padded = np.concatenate(([False], line, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        for start, stop in zip(edges[0::2], edges[1::2]):
            runs.append((row, int(start), int(stop)))
    return tuple(runs)


__all__ = [
    "CellLattice", "LAYOUT_MIN_WINDOW_CELLS", "TILE_CELLS",
    "WINDOW_CELLS", "WINDOW_STEP_CELLS", "affine_matrix", "affine_terms",
    "anchored_affine", "apply_affine", "bbox_centre_native",
    "contains_rect", "invert_affine", "orientation_linear",
    "runs_of_mask", "scale_translation_affine", "shift_affine",
    "support_bbox_native", "support_mass_centroid_native", "tile_cell_rect",
    "tile_of_cell", "window_starts",
]

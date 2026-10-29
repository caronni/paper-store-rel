from __future__ import annotations

from fractions import Fraction

import numpy as np

TILE_CELLS: int = 64
#: The qualified E022 lattice: a 200-cell window with 40 cells of
#: overlap.  Not decoration -- Stage A declares one hypothesis per
#: (slot, phase, rotation), 9*4096*4 = 147,456 at 200 against 262,144
#: at 256, where every one refuses on the attempt budget.
WINDOW_CELLS: int = 200
WINDOW_STEP_CELLS: int = 160
LAYOUT_MIN_WINDOW_CELLS: int = 8


def affine_matrix(terms: tuple[float, ...]) -> np.ndarray:
    return np.asarray(terms, np.float64).reshape(2, 3)


def affine_terms(matrix: np.ndarray) -> tuple[float, ...]:
    array = np.asarray(matrix, np.float64)
    return tuple(float(value) for value in array.reshape(6))


def invert_affine(terms: tuple[float, ...]) -> tuple[float, ...]:
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
    a, b, c, d, e, f = (float(value) for value in terms)
    return a * ys + b * xs + c, d * ys + e * xs + f


def shift_affine(affine: tuple[float, ...], d_cell_y: float,
                 d_cell_x: float) -> tuple[float, ...]:
    a, b, c, d, e, f = (float(term) for term in affine)
    return (a, b, c + a * d_cell_y + b * d_cell_x,
            d, e, f + d * d_cell_y + e * d_cell_x)


#: Rational in, rational through, one float out.  A rung pixel j is
#: the area average of native [j*s, (j+1)*s), so its centre sits at
#: s*(j+1/2)-1/2.  Only the PIXEL side moves -- a printed cell measures
#: the same paper at every rung -- and s == 1 is the identity exactly.
def rescale_pixels(terms: tuple[float, ...],
                   scale: Fraction) -> tuple[float, ...]:
    shift = (scale - 1) / 2
    a, b, c, d, e, f = (Fraction(float(term)) for term in terms)
    return (float(a * scale), float(b * scale), float(c * scale + shift),
            float(d * scale), float(e * scale), float(f * scale + shift))


def compose_to_native(terms: tuple[float, ...],
                      source_per_output: Fraction) -> tuple[float, ...]:
    if source_per_output == 1:
        return tuple(float(term) for term in terms)
    return rescale_pixels(terms, source_per_output)


def compose_from_native(terms: tuple[float, ...],
                        source_per_output: Fraction) -> tuple[float, ...]:
    if source_per_output == 1:
        return tuple(float(term) for term in terms)
    return rescale_pixels(terms, 1 / source_per_output)


#: The last window is SHIFTED IN flush against the far edge, never
#: clipped: clipping cost tiles twice over -- a 451-cell axis gave its
#: last tiles a window holding a third less evidence, and a 545-cell
#: axis dropped its 65-cell remainder, leaving 25 cell rows unwindowed.
def window_starts(n_cells: int, size: int = WINDOW_CELLS,
                  step: int = WINDOW_STEP_CELLS,
                  minimum: int = LAYOUT_MIN_WINDOW_CELLS) -> tuple[int, ...]:
    if n_cells < minimum:
        return ()
    if n_cells <= size:
        return (0,)
    starts = list(range(0, n_cells - size + 1, step))
    if starts[-1] != n_cells - size:
        starts.append(n_cells - size)
    return tuple(starts)


#: C-4: `& 1` is the fit split, `& 2` the colour head sub-split, `& 12`
#: the reveal codes.  `& 1` is identically (y+x)&1 -- the other two are
#: NOT, so "simplifying" to (y+x) silently changes them.  The contract
#: wants this literal spelled ONCE, here.  00-contract.md:27-29.
def site_hash(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    return 131 * y + 17 * x


def site_parity(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    return site_hash(y, x) & 1


def rotated_points(points_yx: np.ndarray, shape_yx: tuple[int, int],
                   rot_k: int) -> np.ndarray:
    points = np.asarray(points_yx)
    y, x = points[:, 0], points[:, 1]
    height, width = shape_yx
    if rot_k == 0:
        return np.stack((y, x), axis=1)
    if rot_k == 1:
        return np.stack((width - 1 - x, y), axis=1)
    if rot_k == 2:
        return np.stack((height - 1 - y, width - 1 - x), axis=1)
    return np.stack((x, height - 1 - y), axis=1)


def tile_of_cell(cell_y: np.ndarray, cell_x: np.ndarray,
                 ) -> tuple[np.ndarray, np.ndarray]:
    return cell_y // TILE_CELLS, cell_x // TILE_CELLS

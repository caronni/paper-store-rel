"""Per-plane registration-delta fields in tile space.

The field is a translation-only, per-plane delta expressed in printed
DOTS, relative to the committed (plane-common) window pose: what a
sampler must add to its scan point so that a plane's ink lands where the
format says it should.  The measured record behind this shape is the
plane-fields line (docs/PLANE-FIELDS.md, docs/INDEPENDENT-PLANES.md):
per-plane registration is real, smooth in tile space, and translation is
~95% of what geometry buys — the Jacobian is plane-common and belongs to
the window pose, not here.

The estimator is a locally weighted least-squares solve on photometric
normal equations.  Each evidence cell contributes the linearisation
``v(delta) ~ v0 + g . delta`` of its own sampled value against the value
the format truth predicts, so ``sum g g^T delta = sum g (t - v0)`` per
tile; the per-tile equations are then smoothed over a Gaussian
neighbourhood (unnormalised, peak 1, so information adds) and solved
against a ridge to zero — a tile with no evidence in reach returns
exactly zero delta, which is the honest answer.  One twicing pass
(a Gauss-Newton step on the smoothed objective) buys back the amplitude
a plain local mean attenuates on smooth structure.

Nothing here reads a clock, draws a random number, or touches a raster:
the caller measures, this module fits and evaluates.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclasses_field

import numpy as np
from scipy import ndimage

# a Gaussian half-width of 2 tiles (~11 mm at c2/600 dpi) is the v1
# bandwidth: wide enough to pool a few hundred furniture sites, narrow
# enough to follow a ~100 mm registration sinusoid
BANDWIDTH_TILES: float = 2.0
KERNEL_TRUNCATION: float = 3.5
# ridge to zero: a N(0, PRIOR_SIGMA_DOTS^2) prior on the delta, in the
# normalised units the caller hands over (residuals divided by the
# plane's own contrast range)
PRIOR_SIGMA_DOTS: float = 1.0
TWICING_PASSES: int = 1
MAX_DELTA_DOTS: float = 2.0


@dataclass(frozen=True)
class NormalEquations:
    """Per-tile normal equations, one plane's worth, one tier's worth.

    ``a`` and ``b`` are the quadratic and linear parts of
    ``sum |A delta - y|^2`` binned by tile, so equations from different
    EVIDENCE TIERS add: the sum of two tiers' equations is the joint
    fit's equations, exactly, and ``a`` from a tier that is left out is a
    subtraction.  That is what makes leave-one-tier-out accounting exact
    rather than a re-fit.
    """

    a: np.ndarray
    b: np.ndarray
    mass: np.ndarray
    total_square: float

    @property
    def tiles_yx(self) -> tuple[int, int]:
        return (int(self.mass.shape[0]), int(self.mass.shape[1]))

    def __add__(self, other: "NormalEquations") -> "NormalEquations":
        if self.tiles_yx != other.tiles_yx:
            raise ValueError(
                "plane field: two tiers' equations must be binned on one "
                f"tile grid, got {self.tiles_yx} and {other.tiles_yx}")
        return NormalEquations(
            a=self.a + other.a, b=self.b + other.b,
            mass=self.mass + other.mass,
            total_square=self.total_square + other.total_square)

    @classmethod
    def empty(cls, tiles_yx: tuple[int, int]) -> "NormalEquations":
        shape = (int(tiles_yx[0]), int(tiles_yx[1]))
        return cls(a=np.zeros(shape + (2, 2), np.float64),
                   b=np.zeros(shape + (2,), np.float64),
                   mass=np.zeros(shape, np.float64), total_square=0.0)


def combine(*tiers: NormalEquations) -> NormalEquations:
    """The joint fit's equations: every tier's, added once."""
    if not tiers:
        raise ValueError("plane field: nothing to combine")
    total = tiers[0]
    for tier in tiers[1:]:
        total = total + tier
    return total


@dataclass(frozen=True)
class FieldFit:
    delta_dots_xy: np.ndarray
    support: np.ndarray
    residual: float
    median_delta_dots: float
    n_sites: int
    #: Per-tier accounting: sites, weight mass, and the effect each tier
    #: had on this fit, measured by leaving it out.  Empty for a fit that
    #: had only one tier to begin with.
    tiers: dict = dataclasses_field(default_factory=dict)
    #: Whether a tier declined, and why.
    gain_check: dict = dataclasses_field(default_factory=dict)


def tile_codes(cells_yx: np.ndarray, tiles_yx: tuple[int, int],
               tile_cells: int) -> np.ndarray:
    cells = np.asarray(cells_yx, np.int64)
    return ((cells[:, 0] // tile_cells) * tiles_yx[1]
            + cells[:, 1] // tile_cells)


def accumulate(codes: np.ndarray, gradient_dots_xy: np.ndarray,
               residual: np.ndarray,
               tiles_yx: tuple[int, int]) -> NormalEquations:
    """Bin centred photometric normal equations by tile.

    ``gradient_dots_xy`` is d(sampled value)/d(offset) in units of value
    per dot, x then y; ``residual`` is (predicted value - sampled value).
    Both are centred within their tile before accumulation, which makes
    the fit invariant to a per-tile brightness offset (banding) — only
    the SHAPE of the mismatch inside a tile moves the delta.
    """
    n_tiles = tiles_yx[0] * tiles_yx[1]
    code = np.asarray(codes, np.int64)
    gradient = np.asarray(gradient_dots_xy, np.float64)
    values = np.asarray(residual, np.float64)
    counts = np.bincount(code, minlength=n_tiles).astype(np.float64)
    safe = np.maximum(counts, 1.0)
    centred_r = values - (np.bincount(code, weights=values,
                                      minlength=n_tiles) / safe)[code]
    centred_g = np.empty_like(gradient)
    for axis in (0, 1):
        mean = np.bincount(code, weights=gradient[:, axis],
                           minlength=n_tiles) / safe
        centred_g[:, axis] = gradient[:, axis] - mean[code]
    shape = (tiles_yx[0], tiles_yx[1])
    a = np.empty(shape + (2, 2), np.float64)
    b = np.empty(shape + (2,), np.float64)
    for i in (0, 1):
        b[..., i] = np.bincount(
            code, weights=centred_g[:, i] * centred_r,
            minlength=n_tiles).reshape(shape)
        for j in (0, 1):
            a[..., i, j] = np.bincount(
                code, weights=centred_g[:, i] * centred_g[:, j],
                minlength=n_tiles).reshape(shape)
    return NormalEquations(a=a, b=b, mass=counts.reshape(shape),
                           total_square=float(np.dot(centred_r, centred_r)))


def observe(codes: np.ndarray, delta_dots_xy: np.ndarray,
            weight: np.ndarray, tiles_yx: tuple[int, int],
            ) -> NormalEquations:
    """Bin RANK-2 pseudo-observations of the delta itself, by tile.

    A photometric cell says "the value here is wrong by this much along
    this gradient" -- one rank-1 equation, and only the SHAPE of the
    mismatch inside a tile carries it, which is why
    :func:`accumulate` centres.  An anchor says something else entirely:
    "this plane's ink is HERE, and the format says it should be there".
    That is a direct, isotropic measurement of the delta, informative in
    both axes at once, and it must NOT be tile-centred -- centring would
    subtract the very quantity being measured.

    Each site contributes ``weight * |delta - measured|^2``, so the
    equations are ``a += w I`` and ``b += w * measured``, and they add to
    a photometric tier's exactly as one more term in the same sum.
    """
    n_tiles = int(tiles_yx[0]) * int(tiles_yx[1])
    code = np.asarray(codes, np.int64)
    measured = np.asarray(delta_dots_xy, np.float64)
    w = np.asarray(weight, np.float64)
    if measured.shape[0] != code.shape[0] or w.shape[0] != code.shape[0]:
        raise ValueError(
            "plane field: one weight and one delta per observed site")
    shape = (int(tiles_yx[0]), int(tiles_yx[1]))
    mass = np.bincount(code, weights=w, minlength=n_tiles).reshape(shape)
    a = np.zeros(shape + (2, 2), np.float64)
    a[..., 0, 0] = mass
    a[..., 1, 1] = mass
    b = np.stack([
        np.bincount(code, weights=w * measured[:, axis],
                    minlength=n_tiles).reshape(shape)
        for axis in (0, 1)], axis=-1)
    counts = np.bincount(code, minlength=n_tiles).astype(np.float64)
    return NormalEquations(
        a=a, b=b, mass=counts.reshape(shape),
        total_square=float(np.dot(w, (measured ** 2).sum(axis=1))))


def gaussian_kernel(bandwidth_tiles: float = BANDWIDTH_TILES,
                    truncation: float = KERNEL_TRUNCATION) -> np.ndarray:
    """Unnormalised (peak 1) Gaussian taps: information adds, it never
    averages away."""
    radius = max(1, int(np.ceil(truncation * bandwidth_tiles)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    return np.exp(-0.5 * (offsets / float(bandwidth_tiles)) ** 2)


def smooth(grid: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable correlation over the two tile axes, zero-padded."""
    values = np.asarray(grid, np.float64)
    taps = np.asarray(kernel, np.float64)
    for axis in (0, 1):
        values = ndimage.correlate1d(values, taps, axis=axis,
                                     mode="constant", cval=0.0)
    return values


def _solve_ridge(a: np.ndarray, b: np.ndarray, ridge: float) -> np.ndarray:
    matrix = a + ridge * np.eye(2, dtype=np.float64)
    determinant = (matrix[..., 0, 0] * matrix[..., 1, 1]
                   - matrix[..., 0, 1] * matrix[..., 1, 0])
    inverse = np.empty_like(matrix)
    inverse[..., 0, 0] = matrix[..., 1, 1]
    inverse[..., 1, 1] = matrix[..., 0, 0]
    inverse[..., 0, 1] = -matrix[..., 0, 1]
    inverse[..., 1, 0] = -matrix[..., 1, 0]
    return np.einsum("...ij,...j->...i", inverse, b) / determinant[..., None]


def solve(equations: NormalEquations,
          bandwidth_tiles: float = BANDWIDTH_TILES,
          prior_sigma_dots: float = PRIOR_SIGMA_DOTS,
          passes: int = TWICING_PASSES,
          max_delta_dots: float = MAX_DELTA_DOTS,
          ) -> tuple[np.ndarray, np.ndarray]:
    """Smoothed ridge solve plus ``passes`` twicing steps.

    Returns (delta_dots_xy per tile, smoothed evidence mass per tile).
    """
    kernel = gaussian_kernel(bandwidth_tiles)
    ridge = 1.0 / float(prior_sigma_dots) ** 2
    smoothed_a = smooth(equations.a, kernel)
    support = smooth(equations.mass, kernel)
    delta = _solve_ridge(smoothed_a, smooth(equations.b, kernel), ridge)
    for _ in range(max(0, int(passes))):
        gradient = equations.b - np.einsum("...ij,...j->...i",
                                           equations.a, delta)
        delta = delta + _solve_ridge(smoothed_a, smooth(gradient, kernel),
                                     ridge)
    return clamp(delta, max_delta_dots), support


def clamp(delta_dots_xy: np.ndarray,
          max_delta_dots: float = MAX_DELTA_DOTS) -> np.ndarray:
    delta = np.asarray(delta_dots_xy, np.float64)
    magnitude = np.hypot(delta[..., 0], delta[..., 1])
    scale = np.where(magnitude > max_delta_dots,
                     max_delta_dots / np.maximum(magnitude, 1e-12), 1.0)
    return delta * scale[..., None]


def fit_residual(equations: NormalEquations,
                 delta_dots_xy: np.ndarray) -> float:
    """Relative residual left by the fit: 1.0 explains nothing, 0.0 all.

    Uses the same centred quadratic the normal equations carry, so the
    number is comparable between fits of the same plane on the same page
    and is the quality half of the cell ordinal.
    """
    total_square_residual = float(equations.total_square)
    if total_square_residual <= 0.0:
        return 1.0
    delta = np.asarray(delta_dots_xy, np.float64)
    quadratic = np.einsum("...i,...ij,...j->...", delta, equations.a, delta)
    linear = np.einsum("...i,...i->...", delta, equations.b)
    remaining = total_square_residual - 2.0 * float(linear.sum()) \
        + float(quadratic.sum())
    return float(np.sqrt(max(remaining, 0.0) / total_square_residual))


def evaluate(delta_dots_xy: np.ndarray, cells_yx: np.ndarray,
             tile_cells: int) -> np.ndarray:
    """Bilinear lookup at tile centres, clamped at the page edge."""
    delta = np.asarray(delta_dots_xy, np.float64)
    cells = np.asarray(cells_yx, np.float64)
    if not cells.shape[0]:
        return np.zeros((0, 2), np.float64)
    coordinates = np.stack(
        (np.clip(cells[:, 0] / tile_cells - 0.5, 0.0,
                 delta.shape[0] - 1.0),
         np.clip(cells[:, 1] / tile_cells - 0.5, 0.0,
                 delta.shape[1] - 1.0)), axis=0)
    out = np.empty((cells.shape[0], 2), np.float64)
    for axis in (0, 1):
        out[:, axis] = ndimage.map_coordinates(
            delta[..., axis], coordinates, order=1, mode="nearest")
    return out


def median_magnitude_dots(delta_dots_xy: np.ndarray,
                          support: np.ndarray) -> float:
    """Median |delta| over tiles that actually carry evidence."""
    delta = np.asarray(delta_dots_xy, np.float64)
    live = np.asarray(support, np.float64) > 0.0
    if not np.any(live):
        return 0.0
    magnitude = np.hypot(delta[..., 0], delta[..., 1])
    return float(np.median(magnitude[live]))

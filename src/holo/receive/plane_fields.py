"""Per-plane translation-delta vector fields over tile space (W1 core).

Normative: docs/PLANE-FIELDS.md §3 (representation ruling), §3c
(shared core, item 1 and 3), §6.2 W1.

The primary object is the per-plane translation-delta VECTOR field over
TILE SPACE: sampled ``(dx, dy)`` deltas in PRINT-DOTS relative to the
committed plane-common pose, each with a precision weight.  There is no
absolute truth in it; the natural zero is "this plane sits exactly where
the common pose says".  The field is integrable by construction -- the
local Jacobian delta IS the spatial gradient of the translation field,
never an independent unknown -- so a lookup returns a FULL UNCOUPLED
LOCAL AFFINE per plane (translation delta + 2x2 gradient) plus an
uncertainty, to be composed onto the committed pose by the caller.

Units are in the names: deltas are ``_dots`` (600 dpi print dots),
positions are ``_tiles`` (continuous tile-space coordinate; tile index
``i`` spans ``[i, i+1)``, so ``cell_yx / TILE_CELLS`` is exactly this
coordinate) and Jacobians are ``_dots_per_cell`` (the format's cell is
the natural step for the sampling seam, hence the ``/TILE_CELLS``).

The field is TRANSIENT by design (§3c item 1): it is rebuilt from the
certificate/pose ledger at load and never enters session state.  The
``to_json``/``from_json`` pair here serves the analytics and instrument
path (W0/W5) only -- it carries the accumulated sufficient statistics,
not a state schema.

Estimator (the exact formulas, per plane ``p`` at one grid point, with
Gaussian kernel weights ``k_i`` over TILE distance and sample weights
``w_i`` read as relative precisions)::

    A_p = sum_i k_i w_i                      weight mass
    B_p = sum_i k_i^2 w_i
    tau_p = A_p^2 / B_p                      effective precision mass
    m_p = (sum_i k_i w_i d_i) / A_p          local weighted mean, dots

Each plane is then an INDEPENDENT normal-normal posterior about the
NATURAL ZERO, with per-sample scatter ``sample_sigma_dots`` (ss) and one
prior variance ``V = plane_sigma_dots^2 + prior_sigma_dots^2``
(``sb^2 + s0^2``)::

    P_p   = tau_p / ss^2 + 1 / V
    mu_p  = (tau_p m_p / ss^2) / P_p
    unc_p = 1 / sqrt(P_p)                    dots

THERE IS NO CROSS-PLANE POOLING (law changed 2026-08-22; §6.5.4b,
docs/INDEPENDENT-PLANES.md §2.6 and §6 P1).  The earlier form shrank
every plane toward a SIGNED precision-weighted mean over planes, and
that target is not a common field: the committed pose is fitted from
W/CM words, so it already sits at the C/M mean and C and M carry
+-(C-M)/2 -- an antisymmetric pair that CANCELS in the signed mean.
With three planes the "common" field therefore came out at about Y/3,
and Y -- the plane the field exists for -- was shrunk toward a third of
itself exactly where its own evidence was thinnest, which is also what
pushed its predicted magnitude under the adoption margin.  Planes are
different by construction; the only defensible shared target is zero,
and the spatial kernel plus the ridge do the regularising work.

The two prior sds add in quadrature because this IS the old hierarchy
with its middle level pinned: ``sb`` is one plane's deviation from the
common registration and ``s0`` the ridge on the common itself, so with
the common no longer ESTIMATED the marginal prior about zero is their
sum.  An uncovered plane (``tau_p = 0``) therefore gets the natural zero
at uncertainty ``sqrt(V)``, never another plane's field -- the same
answer :meth:`lookup` gives for a page with no evidence at all.

Equivalently the blend weight on the plane's own evidence is
``tau_p / (tau_p + kappa)`` with an equivalent prior mass
``kappa = ss^2 / V`` (0.083 at the defaults): a plane floats free where
its evidence mass exceeds kappa and decays toward zero where it does
not.  The ridge is deliberately WEAK, because a ridge strong enough to
tame one wild anchor would also suppress the excursion the field exists
to report.  Thin evidence is REFUSED, not absorbed: it shows up as a
large ``uncertainty_dots``, and the caller's adoption gate is what turns
it down (``color_field.PlaneFieldConfig.max_uncertainty_dots``).  The
estimator is honest; the gate decides.

Bias: a locally weighted MEAN attenuates smooth structure by
``exp(-w^2 h^2 / 2)`` -- at the measured AltaLink Y sinusoid (~100 mm =
18.5 tiles at c2) and the default 2.0-tile bandwidth that is ~21% of
amplitude, which is large against the 0.25-dot adoption threshold.
``refine_passes`` (default 1) therefore runs residual add-back passes
("twicing"): smooth, take each bin's residual against the current
estimate, smooth that, add it to the numerator.  One pass takes the
attenuation to ~4% at a modest variance cost; the reported uncertainty
is the un-sharpened posterior sd and is optimistic by that factor.
``refine_passes=0`` is the plain local average.  Inside about one
bandwidth of the evidence hull the local mean is boundary-biased
(kernel truncation); that is reported through the falling weight mass
and uncertainty rather than corrected -- local-LINEAR regression is the
documented upgrade if measurement ever demands it.
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Final

import numpy as np

from ..format.layout import TILE_CELLS

FIELD_JSON_KIND: Final = "plane_delta_field/1"

DEFAULT_BANDWIDTH_TILES: Final = 2.0
DEFAULT_PLANE_SIGMA_DOTS: Final = 0.3
DEFAULT_SAMPLE_SIGMA_DOTS: Final = 0.3
DEFAULT_PRIOR_SIGMA_DOTS: Final = 1.0
DEFAULT_REFINE_PASSES: Final = 1
KERNEL_TRUNCATION: Final = 3.5      # kernel radius, bandwidths

SOURCE_CERTIFIED: Final = "certified"   # tier (i): certified-tile probe
SOURCE_WORD: Final = "word"             # tier (ii): word residual
SOURCE_DUST: Final = "dust"             # D5 ancestry: dust anchors
SOURCE_PROBE: Final = "probe"           # W4 probe pass
KNOWN_SOURCES: Final = (
    SOURCE_CERTIFIED, SOURCE_WORD, SOURCE_DUST, SOURCE_PROBE)


def _pair_floats(values: Any, name: str) -> tuple[float, float]:
    try:
        first, second = values
    except (TypeError, ValueError):
        raise ValueError(
            f"plane fields: {name} must be a pair") from None
    pair = (float(first), float(second))
    if not (math.isfinite(pair[0]) and math.isfinite(pair[1])):
        raise ValueError(f"plane fields: {name} must be finite")
    return pair


def _index(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"plane fields: {name} must be an integer")
    result = int(value)
    if result < 0:
        raise ValueError(f"plane fields: {name} must be nonnegative")
    return result


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    """One observed per-plane translation delta, in print-dots.

    ``tile_yx`` is the continuous tile-space position of the observation
    (fractional positions are kept; they are binned at ``add`` time).
    ``weight`` is the observation's RELATIVE PRECISION: 1.0 is a nominal
    anchor whose scatter is the field's ``sample_sigma_dots``, 0.25 is an
    observation declared twice as noisy, 0.0 is a recorded non-observation.
    ``source`` is a free tag; ``KNOWN_SOURCES`` names the evidence tiers.
    """

    page: int
    tile_yx: tuple[float, float]
    plane_index: int
    offset_dots_xy: tuple[float, float]
    weight: float = 1.0
    source: str = SOURCE_CERTIFIED

    def __post_init__(self) -> None:
        object.__setattr__(self, "page", _index(self.page, "page"))
        object.__setattr__(
            self, "plane_index", _index(self.plane_index, "plane_index"))
        object.__setattr__(
            self, "tile_yx", _pair_floats(self.tile_yx, "tile_yx"))
        object.__setattr__(
            self, "offset_dots_xy",
            _pair_floats(self.offset_dots_xy, "offset_dots_xy"))
        weight = float(self.weight)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError(
                "plane fields: weight must be finite and nonnegative")
        object.__setattr__(self, "weight", weight)
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("plane fields: source must be a nonempty tag")

    @classmethod
    def from_cell_yx(
        cls,
        *,
        page: int,
        cell_yx: tuple[float, float],
        plane_index: int,
        offset_dots_xy: tuple[float, float],
        weight: float = 1.0,
        source: str = SOURCE_CERTIFIED,
    ) -> FieldEvidence:
        """Build from a page-CELL position (cells / TILE_CELLS = tiles)."""
        cells = _pair_floats(cell_yx, "cell_yx")
        return cls(
            page=page,
            tile_yx=(cells[0] / TILE_CELLS, cells[1] / TILE_CELLS),
            plane_index=plane_index,
            offset_dots_xy=offset_dots_xy,
            weight=weight,
            source=source,
        )


@dataclass(frozen=True, slots=True)
class PlaneLocalAffine:
    """One plane's local affine delta at a lookup point.

    ``delta_dots_xy`` is the translation delta in print-dots and
    ``jacobian_dots_per_cell[i][j] = d(delta_axis_i) / d(position_axis_j)``
    with both axes in x/y order -- i.e. the spatial gradient of the
    translation field, expressed per CELL of travel.  Compose onto the
    committed plane-common pose; never use as an absolute pose.
    """

    plane_index: int
    delta_dots_xy: tuple[float, float]
    jacobian_dots_per_cell: tuple[tuple[float, float], tuple[float, float]]
    uncertainty_dots: float
    weight_mass: float
    n_effective: float
    covered: bool

    def delta_dots_at(
        self, offset_cells_xy: tuple[float, float]
    ) -> tuple[float, float]:
        """Evaluate the local affine ``offset_cells_xy`` away, in dots."""
        offset = _pair_floats(offset_cells_xy, "offset_cells_xy")
        jac = self.jacobian_dots_per_cell
        return (
            self.delta_dots_xy[0]
            + jac[0][0] * offset[0] + jac[0][1] * offset[1],
            self.delta_dots_xy[1]
            + jac[1][0] * offset[0] + jac[1][1] * offset[1],
        )


@dataclass(frozen=True, slots=True)
class FieldStats:
    """Per-plane summary of a solved field (W5 reporting shape)."""

    n_planes: int
    pages: tuple[int, ...]
    n_samples: int
    samples_by_source: dict[str, int] = dataclass_field(default_factory=dict)
    samples_by_plane: tuple[int, ...] = ()
    weight_by_plane: tuple[float, ...] = ()
    rms_dots: tuple[float, ...] = ()
    peak_dots: tuple[float, ...] = ()
    coverage_fraction: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class _PageSolution:
    delta_dots: np.ndarray          # (P, ny, nx, 2) x/y
    jacobian: np.ndarray            # (P, ny, nx, 2, 2) dots per cell
    uncertainty_dots: np.ndarray    # (P, ny, nx)
    weight_mass: np.ndarray         # (P, ny, nx)
    n_effective: np.ndarray         # (P, ny, nx)
    covered: np.ndarray             # (P, ny, nx) bool


def _gauss_kernel(sigma_bins: float) -> np.ndarray:
    """Unnormalised Gaussian, peak 1 (all estimators here are ratios)."""
    radius = max(1, int(math.ceil(KERNEL_TRUNCATION * sigma_bins)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    return np.exp(-0.5 * (offsets / sigma_bins) ** 2)


def _convolve_axis(
    grid: np.ndarray, kernel: np.ndarray, axis: int
) -> np.ndarray:
    """Zero-padded 1-D convolution (outside the grid there is no mass)."""
    radius = kernel.size // 2
    pad_width = [(0, 0)] * grid.ndim
    pad_width[axis] = (radius, radius)
    padded = np.pad(grid, pad_width)
    extent = grid.shape[axis]
    out = np.zeros_like(grid)
    for offset, coefficient in enumerate(kernel):
        if coefficient == 0.0:
            continue
        index: list[Any] = [slice(None)] * grid.ndim
        index[axis] = slice(offset, offset + extent)
        out += coefficient * padded[tuple(index)]
    return out


def _smooth(grid: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable smoothing over the (y, x) bin axes 1 and 2."""
    return _convolve_axis(_convolve_axis(grid, kernel, 1), kernel, 2)


def _ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Elementwise ratio, zero where the denominator carries no mass."""
    denom = denominator
    while denom.ndim < numerator.ndim:
        denom = denom[..., None]
    out = np.zeros_like(numerator)
    np.divide(
        numerator, denom, out=out,
        where=np.broadcast_to(denom > 0.0, numerator.shape))
    return out


def _dilate(mask: np.ndarray, radius_bins: float) -> np.ndarray:
    """Disc dilation over the trailing (y, x) axes, radius in bins."""
    if radius_bins <= 0.0:
        return mask.copy()
    radius = int(math.ceil(radius_bins))
    ny, nx = mask.shape[-2], mask.shape[-1]
    out = np.zeros_like(mask)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy * dy + dx * dx > radius_bins * radius_bins:
                continue
            src_y = slice(max(0, dy), ny + min(0, dy))
            src_x = slice(max(0, dx), nx + min(0, dx))
            dst_y = slice(max(0, -dy), ny + min(0, -dy))
            dst_x = slice(max(0, -dx), nx + min(0, -dx))
            out[..., dst_y, dst_x] |= mask[..., src_y, src_x]
    return out


def _bilinear(grid: np.ndarray, bin_y: float, bin_x: float) -> np.ndarray:
    """Interpolate ``(P, ny, nx, ...)`` at fractional bin coordinates."""
    ny, nx = grid.shape[1], grid.shape[2]
    y = min(max(bin_y, 0.0), float(ny - 1))
    x = min(max(bin_x, 0.0), float(nx - 1))
    y0 = int(math.floor(y))
    x0 = int(math.floor(x))
    y1 = min(y0 + 1, ny - 1)
    x1 = min(x0 + 1, nx - 1)
    fy = y - y0
    fx = x - x0
    top = grid[:, y0, x0] * (1.0 - fx) + grid[:, y0, x1] * fx
    bottom = grid[:, y1, x0] * (1.0 - fx) + grid[:, y1, x1] * fx
    return top * (1.0 - fy) + bottom * fy


class PlaneDeltaField:
    """Per-plane translation-delta field over tile space, one page-set.

    Plane-generic by ruling (§3): ``n_planes`` is the family's PHYSICAL
    plane count, and the K instance is ``n_planes=1`` with no special
    case anywhere in this module.
    """

    def __init__(
        self,
        n_planes: int,
        tiles_yx: tuple[int, int],
        *,
        bandwidth_tiles: float = DEFAULT_BANDWIDTH_TILES,
        plane_sigma_dots: float = DEFAULT_PLANE_SIGMA_DOTS,
        sample_sigma_dots: float = DEFAULT_SAMPLE_SIGMA_DOTS,
        prior_sigma_dots: float = DEFAULT_PRIOR_SIGMA_DOTS,
        bins_per_tile: int = 1,
        refine_passes: int = DEFAULT_REFINE_PASSES,
    ) -> None:
        if isinstance(n_planes, bool) or not isinstance(
                n_planes, (int, np.integer)) or int(n_planes) < 1:
            raise ValueError("plane fields: n_planes must be >= 1")
        tiles_y, tiles_x = (_index(v, "tiles_yx") for v in tiles_yx)
        if tiles_y < 1 or tiles_x < 1:
            raise ValueError("plane fields: tiles_yx must be positive")
        if not math.isfinite(bandwidth_tiles) or bandwidth_tiles <= 0.0:
            raise ValueError("plane fields: bandwidth_tiles must be > 0")
        if not math.isfinite(plane_sigma_dots) or plane_sigma_dots < 0.0:
            raise ValueError("plane fields: plane_sigma_dots must be >= 0")
        if not math.isfinite(sample_sigma_dots) or sample_sigma_dots <= 0.0:
            raise ValueError("plane fields: sample_sigma_dots must be > 0")
        if not math.isfinite(prior_sigma_dots) or prior_sigma_dots <= 0.0:
            raise ValueError("plane fields: prior_sigma_dots must be > 0")
        bins_per_tile = _index(bins_per_tile, "bins_per_tile")
        if bins_per_tile < 1:
            raise ValueError("plane fields: bins_per_tile must be >= 1")
        refine_passes = _index(refine_passes, "refine_passes")

        self.n_planes: Final = int(n_planes)
        self.tiles_yx: Final = (tiles_y, tiles_x)
        self.bandwidth_tiles: Final = float(bandwidth_tiles)
        self.plane_sigma_dots: Final = float(plane_sigma_dots)
        self.sample_sigma_dots: Final = float(sample_sigma_dots)
        self.prior_sigma_dots: Final = float(prior_sigma_dots)
        self.bins_per_tile: Final = bins_per_tile
        self.refine_passes: Final = refine_passes
        self._bins_yx: Final = (
            tiles_y * bins_per_tile, tiles_x * bins_per_tile)
        self._grids: dict[int, np.ndarray] = {}
        self._solution: dict[int, _PageSolution] = {}
        self._solved = False
        self._source_counts: dict[tuple[int, str], int] = {}
        self._weight_by_plane = np.zeros(self.n_planes, dtype=np.float64)
        self._n_samples = 0

    @property
    def prior_variance(self) -> float:
        """One plane's prior variance about the natural zero, dots^2.

        ONE definition, read by the solver and by the no-evidence answer,
        so "what the field says where it knows nothing" cannot drift from
        "what it shrinks toward where it knows little".
        """
        return self.plane_sigma_dots ** 2 + self.prior_sigma_dots ** 2

    # -- accumulation ---------------------------------------------------

    def add(self, evidence: Iterable[FieldEvidence]) -> int:
        """Scatter observations into the per-(plane, bin) accumulators.

        Returns the number of observations added.  Any previously solved
        state is discarded: ``solve()`` must be called again.
        """
        rows = list(evidence)
        if not rows:
            return 0
        pages = np.fromiter((r.page for r in rows), np.int64, len(rows))
        planes = np.fromiter(
            (r.plane_index for r in rows), np.int64, len(rows))
        if int(planes.max()) >= self.n_planes:
            raise ValueError(
                f"plane fields: plane_index {int(planes.max())} outside "
                f"n_planes={self.n_planes}")
        tile_y = np.fromiter((r.tile_yx[0] for r in rows), float, len(rows))
        tile_x = np.fromiter((r.tile_yx[1] for r in rows), float, len(rows))
        if (tile_y.min() < 0.0 or tile_x.min() < 0.0
                or tile_y.max() > self.tiles_yx[0]
                or tile_x.max() > self.tiles_yx[1]):
            raise ValueError(
                "plane fields: evidence tile position outside "
                f"tiles_yx={self.tiles_yx}")
        weights = np.fromiter((r.weight for r in rows), float, len(rows))
        delta_x = np.fromiter(
            (r.offset_dots_xy[0] for r in rows), float, len(rows))
        delta_y = np.fromiter(
            (r.offset_dots_xy[1] for r in rows), float, len(rows))

        bin_y = np.clip(
            (tile_y * self.bins_per_tile).astype(np.int64),
            0, self._bins_yx[0] - 1)
        bin_x = np.clip(
            (tile_x * self.bins_per_tile).astype(np.int64),
            0, self._bins_yx[1] - 1)

        for page in np.unique(pages):
            grid = self._grids.get(int(page))
            if grid is None:
                grid = np.zeros(
                    (self.n_planes, self._bins_yx[0], self._bins_yx[1], 4),
                    dtype=np.float64)
                self._grids[int(page)] = grid
            take = pages == page
            cell = (planes[take], bin_y[take], bin_x[take])
            np.add.at(grid, (*cell, 0), weights[take])
            np.add.at(grid, (*cell, 1), weights[take] * delta_x[take])
            np.add.at(grid, (*cell, 2), weights[take] * delta_y[take])
            np.add.at(grid, (*cell, 3), weights[take] ** 2)

        for row in rows:
            key = (row.plane_index, row.source)
            self._source_counts[key] = self._source_counts.get(key, 0) + 1
        np.add.at(self._weight_by_plane, planes, weights)
        self._n_samples += len(rows)
        self._solution.clear()
        self._solved = False
        return len(rows)

    # -- solving --------------------------------------------------------

    def solve(self) -> None:
        """Build the smoothed, shrunk per-plane grids for every page."""
        kernel = _gauss_kernel(self.bandwidth_tiles * self.bins_per_tile)
        kernel_squared = kernel ** 2
        self._solution = {
            page: self._solve_page(grid, kernel, kernel_squared)
            for page, grid in self._grids.items()
        }
        self._solved = True

    def _solve_page(
        self,
        grid: np.ndarray,
        kernel: np.ndarray,
        kernel_squared: np.ndarray,
    ) -> _PageSolution:
        bin_weight = grid[..., 0]
        bin_weighted_delta = grid[..., 1:3]
        bin_weight_squared = grid[..., 3]

        weight_mass = _smooth(bin_weight, kernel)
        precision_denominator = _smooth(bin_weight, kernel_squared)
        count_denominator = _smooth(bin_weight_squared, kernel_squared)
        numerator = _smooth(bin_weighted_delta, kernel)

        bin_mean = _ratio(bin_weighted_delta, bin_weight)
        for _ in range(self.refine_passes):
            estimate = _ratio(numerator, weight_mass)
            residual = bin_mean - estimate
            numerator = numerator + _smooth(
                bin_weight[..., None] * residual, kernel)
        local_mean = _ratio(numerator, weight_mass)

        tau = _ratio(weight_mass ** 2, precision_denominator)
        n_effective = _ratio(weight_mass ** 2, count_denominator)

        # Per plane, independently, about the NATURAL ZERO: no term here
        # reads another plane's evidence (the 2026-08-22 law).
        sample_variance = self.sample_sigma_dots ** 2
        plane_precision = (
            tau / sample_variance + 1.0 / self.prior_variance)
        delta = (
            tau[..., None] * local_mean / sample_variance
            / plane_precision[..., None])
        uncertainty = 1.0 / np.sqrt(plane_precision)

        return _PageSolution(
            delta_dots=delta,
            jacobian=self._jacobian(delta),
            uncertainty_dots=uncertainty,
            weight_mass=weight_mass,
            n_effective=n_effective,
            covered=_dilate(
                bin_weight > 0.0,
                self.bandwidth_tiles * self.bins_per_tile),
        )

    def _jacobian(self, delta: np.ndarray) -> np.ndarray:
        """Finite-difference gradient of the delta field, dots per cell."""
        scale = self.bins_per_tile / TILE_CELLS
        gradient_y = np.zeros_like(delta)
        gradient_x = np.zeros_like(delta)
        if delta.shape[1] > 1:
            gradient_y = np.gradient(delta, axis=1) * scale
        if delta.shape[2] > 1:
            gradient_x = np.gradient(delta, axis=2) * scale
        jacobian = np.empty(delta.shape[:3] + (2, 2), dtype=np.float64)
        jacobian[..., 0, 0] = gradient_x[..., 0]   # d(dx)/dx
        jacobian[..., 0, 1] = gradient_y[..., 0]   # d(dx)/dy
        jacobian[..., 1, 0] = gradient_x[..., 1]   # d(dy)/dx
        jacobian[..., 1, 1] = gradient_y[..., 1]   # d(dy)/dy
        return jacobian

    # -- lookup ---------------------------------------------------------

    @property
    def solved(self) -> bool:
        return self._solved

    def lookup(
        self, page: int, tile_yx: tuple[float, float]
    ) -> tuple[PlaneLocalAffine, ...]:
        """Local affine delta per plane at a tile-space position.

        ``tile_yx`` is continuous; positions outside the grid are clamped
        to its edge, and a page with no evidence returns the natural zero
        at the prior uncertainty.  Use ``lookup_tile_index`` to evaluate
        at the centre of tile ``(ty, tx)``.
        """
        if not self._solved:
            raise RuntimeError("plane fields: solve() before lookup()")
        position = _pair_floats(tile_yx, "tile_yx")
        solution = self._solution.get(_index(page, "page"))
        if solution is None:
            return tuple(
                self._no_evidence(plane) for plane in range(self.n_planes))
        bin_y = position[0] * self.bins_per_tile - 0.5
        bin_x = position[1] * self.bins_per_tile - 0.5
        delta = _bilinear(solution.delta_dots, bin_y, bin_x)
        jacobian = _bilinear(solution.jacobian, bin_y, bin_x)
        uncertainty = _bilinear(
            solution.uncertainty_dots[..., None], bin_y, bin_x)
        weight_mass = _bilinear(
            solution.weight_mass[..., None], bin_y, bin_x)
        n_effective = _bilinear(
            solution.n_effective[..., None], bin_y, bin_x)
        covered = _bilinear(
            solution.covered[..., None].astype(np.float64), bin_y, bin_x)
        return tuple(
            PlaneLocalAffine(
                plane_index=plane,
                delta_dots_xy=(
                    float(delta[plane, 0]), float(delta[plane, 1])),
                jacobian_dots_per_cell=(
                    (float(jacobian[plane, 0, 0]),
                     float(jacobian[plane, 0, 1])),
                    (float(jacobian[plane, 1, 0]),
                     float(jacobian[plane, 1, 1])),
                ),
                uncertainty_dots=float(uncertainty[plane, 0]),
                weight_mass=float(weight_mass[plane, 0]),
                n_effective=float(n_effective[plane, 0]),
                covered=bool(covered[plane, 0] > 0.5),
            )
            for plane in range(self.n_planes)
        )

    def lookup_tile_index(
        self, page: int, tile_y: int, tile_x: int
    ) -> tuple[PlaneLocalAffine, ...]:
        """Lookup at the CENTRE of the tile with index ``(tile_y, tile_x)``."""
        return self.lookup(
            page,
            (_index(tile_y, "tile_y") + 0.5, _index(tile_x, "tile_x") + 0.5),
        )

    def lookup_cells(
        self, page: int, cell_yx: tuple[float, float]
    ) -> tuple[PlaneLocalAffine, ...]:
        """Lookup at a page-CELL position (bilinear between tile samples)."""
        cells = _pair_floats(cell_yx, "cell_yx")
        return self.lookup(
            page, (cells[0] / TILE_CELLS, cells[1] / TILE_CELLS))

    def lookup_plane(
        self, page: int, tile_yx: tuple[float, float], plane_index: int
    ) -> PlaneLocalAffine:
        """One plane's local affine delta; unknown plane index raises."""
        plane = _index(plane_index, "plane_index")
        if plane >= self.n_planes:
            raise ValueError(
                f"plane fields: plane_index {plane} outside "
                f"n_planes={self.n_planes}")
        return self.lookup(page, tile_yx)[plane]

    def _no_evidence(self, plane_index: int) -> PlaneLocalAffine:
        uncertainty = math.sqrt(self.prior_variance)
        return PlaneLocalAffine(
            plane_index=plane_index,
            delta_dots_xy=(0.0, 0.0),
            jacobian_dots_per_cell=((0.0, 0.0), (0.0, 0.0)),
            uncertainty_dots=uncertainty,
            weight_mass=0.0,
            n_effective=0.0,
            covered=False,
        )

    # -- reporting ------------------------------------------------------

    def stats(self) -> FieldStats:
        """Per-plane RMS/peak delta, sample tallies, coverage fraction.

        RMS and peak are magnitudes over the COVERED bins of every page
        (bins within ``bandwidth_tiles`` of at least one sample of that
        plane); coverage is that same set as a fraction of the whole grid.
        """
        if not self._solved:
            raise RuntimeError("plane fields: solve() before stats()")
        by_source: dict[str, int] = {}
        by_plane = [0] * self.n_planes
        for (plane, source), count in self._source_counts.items():
            by_source[source] = by_source.get(source, 0) + count
            by_plane[plane] += count

        rms = [0.0] * self.n_planes
        peak = [0.0] * self.n_planes
        coverage = [0.0] * self.n_planes
        total_bins = self._bins_yx[0] * self._bins_yx[1] * max(
            len(self._solution), 1)
        for plane in range(self.n_planes):
            squares = 0.0
            covered_bins = 0
            for solution in self._solution.values():
                mask = solution.covered[plane]
                covered_bins += int(mask.sum())
                if not mask.any():
                    continue
                magnitude = np.hypot(
                    solution.delta_dots[plane, ..., 0],
                    solution.delta_dots[plane, ..., 1])[mask]
                squares += float((magnitude ** 2).sum())
                peak[plane] = max(peak[plane], float(magnitude.max()))
            if covered_bins:
                rms[plane] = math.sqrt(squares / covered_bins)
            coverage[plane] = covered_bins / total_bins
        return FieldStats(
            n_planes=self.n_planes,
            pages=tuple(sorted(self._grids)),
            n_samples=self._n_samples,
            samples_by_source=by_source,
            samples_by_plane=tuple(by_plane),
            weight_by_plane=tuple(float(w) for w in self._weight_by_plane),
            rms_dots=tuple(rms),
            peak_dots=tuple(peak),
            coverage_fraction=tuple(coverage),
        )

    # -- transient serialisation (analytics / instrument path only) -----

    def to_json(self) -> dict[str, Any]:
        """JSON-ready mapping of config + accumulated sufficient statistics.

        NOT session state (the field is transient by §3c ruling): this
        serves the W0 instrument and the W5 analytics path, and carries
        the bin accumulators rather than the solved grids so that
        ``from_json(...).solve()`` reproduces the solution exactly.
        """
        bins: list[list[float]] = []
        for page in sorted(self._grids):
            grid = self._grids[page]
            planes, ys, xs = np.nonzero(grid[..., 0] != 0.0)
            for plane, y, x in zip(planes, ys, xs):
                sums = grid[plane, y, x]
                bins.append([
                    float(page), float(plane), float(y), float(x),
                    float(sums[0]), float(sums[1]),
                    float(sums[2]), float(sums[3]),
                ])
        return {
            "kind": FIELD_JSON_KIND,
            "n_planes": self.n_planes,
            "tiles_yx": list(self.tiles_yx),
            "bandwidth_tiles": self.bandwidth_tiles,
            "plane_sigma_dots": self.plane_sigma_dots,
            "sample_sigma_dots": self.sample_sigma_dots,
            "prior_sigma_dots": self.prior_sigma_dots,
            "bins_per_tile": self.bins_per_tile,
            "refine_passes": self.refine_passes,
            "n_samples": self._n_samples,
            "sources": [
                [plane, source, count]
                for (plane, source), count in sorted(
                    self._source_counts.items())
            ],
            "weight_by_plane": [
                float(w) for w in self._weight_by_plane],
            "bins": bins,
        }

    @classmethod
    def from_json(
        cls, payload: Mapping[str, Any] | str
    ) -> PlaneDeltaField:
        """Rebuild an UNSOLVED field from ``to_json`` output."""
        data = json.loads(payload) if isinstance(payload, str) else payload
        if data.get("kind") != FIELD_JSON_KIND:
            raise ValueError(
                f"plane fields: expected kind {FIELD_JSON_KIND!r}")
        tiles = data["tiles_yx"]
        field = cls(
            int(data["n_planes"]),
            (int(tiles[0]), int(tiles[1])),
            bandwidth_tiles=float(data["bandwidth_tiles"]),
            plane_sigma_dots=float(data["plane_sigma_dots"]),
            sample_sigma_dots=float(data["sample_sigma_dots"]),
            prior_sigma_dots=float(data["prior_sigma_dots"]),
            bins_per_tile=int(data["bins_per_tile"]),
            refine_passes=int(data["refine_passes"]),
        )
        for row in data["bins"]:
            page = int(row[0])
            grid = field._grids.get(page)
            if grid is None:
                grid = np.zeros(
                    (field.n_planes, field._bins_yx[0], field._bins_yx[1], 4),
                    dtype=np.float64)
                field._grids[page] = grid
            grid[int(row[1]), int(row[2]), int(row[3])] = row[4:8]
        field._source_counts = {
            (int(plane), str(source)): int(count)
            for plane, source, count in data["sources"]
        }
        field._weight_by_plane = np.asarray(
            data["weight_by_plane"], dtype=np.float64)
        field._n_samples = int(data["n_samples"])
        return field

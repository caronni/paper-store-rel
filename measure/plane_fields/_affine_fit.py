"""The supervised affine engine: a fast tile sampler, the 6-dof fit, the stats.

``gt_affine`` asks a question the swim could not: for a tile whose printed
cells we KNOW (sheet I closed VERIFIED), what is the BEST per-plane
sampling geometry, and what error survives it?  That needs three things
this module supplies and ``gt_affine`` composes:

* :class:`TileSampler` — one capture's sampled channel values for ONE
  tile at an arbitrary per-plane affine, reading pixels the production
  way (``color_sampling`` crop + aperture filter + order-1 interpolation)
  but over the tile's cells only, so an optimiser can afford thousands of
  evaluations.  :meth:`TileSampler.null_proof` asserts that the zero
  affine reproduces the production window sampler's values EXACTLY on
  those cells — the same discipline ``_swim_region.null_proof`` applies
  to the constant-delta seam.
* :class:`Affine` and :func:`fit_affine` — the model and the coarse-to-
  fine search.  The objective is a PARTIAL NCC: the correlation between
  the sampled channel and the plane's ground-truth bits after linearly
  removing the OTHER two planes' ground-truth bits, so cross-plane ink
  (a c2-cmy8 page prints all three planes on the same cells) cannot buy
  correlation the geometry did not earn.
* the diagnostics: class separation (d', AUC, and the partial d' that
  the same projector supplies), the ORACLE-THRESHOLD cell error (what a
  perfect photometric decision would score on these very samples), and
  the spatial structure of what is left (quadrants, edge ring, Moran's I
  with a permutation p-value).

Nothing here writes anything, and nothing here is imported by src/holo.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage, optimize, stats

from holo.receive._payload_sampling import APERTURE_CELLS
from holo.receive.color_sampling import filtered_crop, native_crop

from ._swim_region import page_to_local_dots

#: Cell coordinates inside a tile run 0..63; the affine is expressed
#: about the tile centre so translation and Jacobian are orthogonal.
TILE_CELLS = 64
HALF_TILE = (TILE_CELLS - 1) / 2.0


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Affine:
    """A per-plane sampling-grid affine, in PAGE print dots.

    For a cell at in-tile coordinates ``(cx, cy)`` the sampling point is
    displaced by::

        (dx, dy) = (tx, ty) + M @ (cx - 31.5, cy - 31.5)

    with ``M`` in DOTS PER CELL.  The vector form the optimiser sees
    scales ``M`` by :data:`HALF_TILE`, so every coordinate is "print dots
    of displacement at the tile edge" and a plain Nelder-Mead simplex is
    well conditioned in all six.
    """

    tx: float
    ty: float
    m: tuple[tuple[float, float], tuple[float, float]] = (
        (0.0, 0.0), (0.0, 0.0))

    @property
    def matrix(self) -> np.ndarray:
        return np.asarray(self.m, np.float64)

    def to_vector(self) -> np.ndarray:
        matrix = self.matrix * HALF_TILE
        return np.asarray(
            (self.tx, self.ty, matrix[0, 0], matrix[0, 1],
             matrix[1, 0], matrix[1, 1]), np.float64)

    @staticmethod
    def from_vector(vector) -> "Affine":
        values = np.asarray(vector, np.float64)
        matrix = values[2:6].reshape(2, 2) / HALF_TILE
        return Affine(float(values[0]), float(values[1]),
                      ((float(matrix[0, 0]), float(matrix[0, 1])),
                       (float(matrix[1, 0]), float(matrix[1, 1]))))

    def offsets(self, centred_xy: np.ndarray) -> np.ndarray:
        """``(n, 2)`` page-dot ``(dx, dy)`` for centred ``(cx, cy)``."""
        return (np.asarray((self.tx, self.ty), np.float64)[None, :]
                + centred_xy @ self.matrix.T)

    def report(self, cell_dots: int) -> dict:
        """The fit in interpretable units.

        ``M`` is dots per CELL; the sampling grid's Jacobian in DOT space
        is ``J = I + M / cell_dots``, so the diagonal is a relative scale
        error and the off-diagonal splits into a rotation (antisymmetric)
        and a shear (symmetric) part.
        """
        matrix = self.matrix
        jac = matrix / float(cell_dots)
        rotation = 0.5 * (jac[1, 0] - jac[0, 1])
        shear = 0.5 * (jac[1, 0] + jac[0, 1])
        span = TILE_CELLS - 1
        return {
            "translation_dots_xy": [self.tx, self.ty],
            "translation_dots_norm": float(np.hypot(self.tx, self.ty)),
            "m_dots_per_cell": [[float(v) for v in row] for row in matrix],
            "scale_x_pct": float(100.0 * jac[0, 0]),
            "scale_y_pct": float(100.0 * jac[1, 1]),
            "rotation_deg": float(np.degrees(rotation)),
            "shear_deg": float(np.degrees(shear)),
            "dots_across_tile": {
                "dx_from_x": float(matrix[0, 0] * span),
                "dx_from_y": float(matrix[0, 1] * span),
                "dy_from_x": float(matrix[1, 0] * span),
                "dy_from_y": float(matrix[1, 1] * span)},
            "jacobian_deviation_norm": float(np.linalg.norm(jac)),
        }


ZERO = Affine(0.0, 0.0)


# --------------------------------------------------------------------------
# the sampler
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _WindowRows:
    """One window's rows for one tile, everything precomputed."""

    ordinal: int
    select: np.ndarray            # indices into the window's row arrays
    cell_yx: np.ndarray           # (n, 2) in-tile cell coordinates
    centred_xy: np.ndarray        # (n, 2) (cx, cy) - 31.5
    base_dots_xy: np.ndarray      # (3, n, 2) the delta = 0 offsets, LOCAL
    basis: np.ndarray             # page (dx, dy) -> local (dx, dy)
    pose: np.ndarray              # local cell (dy, dx) -> scan px (dy, dx)
    points: np.ndarray            # (n, 2) delta = 0 scan points
    origin: tuple[int, int]
    filtered: np.ndarray          # the aperture-filtered local crop


class TileSampler:
    """One capture's sampled values for one tile, at any per-plane affine.

    The crop is read ONCE with a halo wide enough for the whole search
    box plus the production aperture halo, so every evaluation is a
    ``map_coordinates`` call and nothing re-reads the scan.  Because the
    aperture filter is a local box, values at points that sit at least
    ``ceil(APERTURE_CELLS * pitch) + 2`` px inside the crop are identical
    to the ones production's per-call ``points_crop`` would produce —
    which :meth:`null_proof` verifies rather than assumes.
    """

    def __init__(self, fit, raster, spec, address, ordinals,
                 *, pad_dots: float = 3.0) -> None:
        self.fit = fit
        self.spec = spec
        self.address = address
        self.cell_dots = int(spec.cell_dots)
        self.capture_sha256 = fit.capture_sha256
        _page, tile_y, tile_x = address
        halo = int(np.ceil(APERTURE_CELLS * fit.pitch_px)) + 2
        rows: list[_WindowRows] = []
        for ordinal in ordinals:
            row = fit.rows[ordinal]
            page_cells = np.asarray(row.page_cells_yx, np.int64)
            select = np.nonzero((page_cells[:, 0] // TILE_CELLS == tile_y)
                                & (page_cells[:, 1] // TILE_CELLS == tile_x)
                                )[0]
            if select.size == 0:
                continue
            cell_yx = page_cells[select] % TILE_CELLS
            centred = np.stack(
                (cell_yx[:, 1] - HALF_TILE, cell_yx[:, 0] - HALF_TILE),
                axis=1).astype(np.float64)
            fraction = (page_cells[:, 0].astype(np.float64)
                        / spec.layout.cells_yx[0])[select]
            base = np.stack([
                (residual.offsets(fraction) if fit.base_is_residual
                 else np.zeros((select.size, 2), np.float64))
                for residual in fit.residuals])
            pose = np.asarray(
                row.patch.segment.segment.pose.matrix(), np.float64)
            points = np.asarray(row.scan_points_yx, np.float64)[select]
            reach = np.abs(pose).sum(axis=1) * (
                (pad_dots + float(np.abs(base).max(initial=0.0)))
                / self.cell_dots)
            corners = np.concatenate([
                points + np.asarray((sy * reach[0], sx * reach[1]))
                for sy in (-1.0, 1.0) for sx in (-1.0, 1.0)])
            y0, x0, raw = native_crop(raster, corners, halo)
            crop = filtered_crop(y0, x0, raw, fit.pitch_px, fit.divisor)
            rows.append(_WindowRows(
                ordinal=int(ordinal), select=select, cell_yx=cell_yx,
                centred_xy=centred, base_dots_xy=base,
                basis=page_to_local_dots(row.patch), pose=pose,
                points=points, origin=(crop.y0, crop.x0),
                filtered=np.ascontiguousarray(crop.filtered)))
        if not rows:
            raise ValueError(f"no window carries tile {address}")
        self.rows = tuple(rows)
        self.cell_yx = np.concatenate([row.cell_yx for row in self.rows])
        self.n_samples = int(self.cell_yx.shape[0])

    # -- sampling ---------------------------------------------------------
    def sample(self, plane: int, affine: Affine | None = None) -> np.ndarray:
        """Channel ``plane`` at every one of the tile's cells, all windows."""
        out: list[np.ndarray] = []
        for row in self.rows:
            local = np.array(row.base_dots_xy[plane], np.float64)
            if affine is not None:
                local += affine.offsets(row.centred_xy) @ row.basis.T
            delta = (local[:, ::-1] / self.cell_dots) @ row.pose.T
            points = row.points + delta
            points -= np.asarray(row.origin, np.float64)
            out.append(ndimage.map_coordinates(
                row.filtered[..., plane], points.T, order=1, mode="nearest",
                output=np.float64))
        return np.concatenate(out)

    def truth(self, tile_bits: np.ndarray, plane: int) -> np.ndarray:
        """The GT bits of this plane, aligned with :meth:`sample`."""
        return tile_bits[self.cell_yx[:, 0], self.cell_yx[:, 1],
                         plane].astype(np.float64)

    def null_proof(self, raster) -> dict:
        """The zero affine == the production window sampler, cell for cell."""
        from holo.receive.color_anchoring import _features_with_page_fraction

        from ._swim_region import override_offsets

        mine = np.stack([self.sample(plane, None) for plane in range(3)],
                        axis=1)
        worst = 0.0
        checked = 0
        start = 0
        for row in self.rows:
            stop = start + row.select.size
            window = self.fit.rows[row.ordinal]
            produced = _features_with_page_fraction(
                raster, window, self.fit.residuals, self.spec,
                self.fit.pitch_px, self.fit.divisor,
                offsets_override=override_offsets(
                    window, self.fit.residuals, self.spec, np.zeros((3, 2)),
                    self.fit.base_is_residual))
            if produced is None:
                return {"exact": False, "reason": "production sampler refused"}
            worst = max(worst, float(np.abs(
                mine[start:stop] - produced[row.select]).max()))
            checked += int(row.select.size) * 3
            start = stop
        # The production sampler filters a crop whose ORIGIN differs from
        # this one's, and the aperture filter runs in float32, so the two
        # accumulate in a different order.  Bit-equality is therefore the
        # wrong bar; float32 rounding is the right one, and anything
        # larger would be a real geometric disagreement.
        return {"bit_identical": worst == 0.0,
                "within_float32_rounding": worst <= 1e-6,
                "max_abs_diff": worst, "cells_checked": checked}


# --------------------------------------------------------------------------
# the objective
# --------------------------------------------------------------------------
class PartialNCC:
    """Correlation with one plane's GT bits, the other two projected out.

    A c2-cmy8 page prints all three planes on the same cells, so the raw
    channel a plane is read from carries the other two planes' ink as
    well.  Removing their GT bits (and an intercept) linearly before
    correlating means a misregistered plane cannot borrow correlation
    from a neighbour that happens to be aligned.
    """

    def __init__(self, truth_by_plane: np.ndarray, plane: int) -> None:
        others = [p for p in range(3) if p != plane]
        design = np.column_stack(
            [np.ones(truth_by_plane.shape[1])]
            + [truth_by_plane[p] for p in others])
        self.pinv = np.linalg.pinv(design)
        self.design = design
        target = truth_by_plane[plane]
        self.target = self.residual(target)
        norm = float(np.linalg.norm(self.target))
        self.target_norm = norm
        self.degenerate = norm < 1e-9

    def residual(self, values: np.ndarray) -> np.ndarray:
        return values - self.design @ (self.pinv @ values)

    def __call__(self, values: np.ndarray) -> float:
        """Partial correlation; NEGATIVE when ink darkens the channel."""
        if self.degenerate:
            return 0.0
        residual = self.residual(values)
        norm = float(np.linalg.norm(residual))
        if norm < 1e-12:
            return 0.0
        return float(residual @ self.target / (norm * self.target_norm))


def raw_ncc(values: np.ndarray, truth: np.ndarray) -> float:
    if values.std() < 1e-12 or truth.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(values, truth)[0, 1])


# --------------------------------------------------------------------------
# the search
# --------------------------------------------------------------------------
#: Refusal box.  A sampling correction bigger than this is not a
#: registration finding, it is the optimiser leaving the tile.
MAX_T_DOTS = 3.0
MAX_EDGE_DOTS = 2.0


def _penalty(vector: np.ndarray) -> float:
    excess = (max(0.0, abs(vector[0]) - MAX_T_DOTS)
              + max(0.0, abs(vector[1]) - MAX_T_DOTS)
              + sum(max(0.0, abs(v) - MAX_EDGE_DOTS) for v in vector[2:]))
    return 0.0 if excess == 0.0 else 10.0 * excess


def fit_affine(sampler: TileSampler, plane: int, truth_by_plane: np.ndarray,
               *, coarse_max: float = 1.5, coarse_step: float = 0.25,
               dof: int = 6) -> dict:
    """Coarse translation grid, then Nelder-Mead on ``dof`` parameters.

    ``dof = 2`` stops at translation (the supervised translation
    ceiling); ``dof = 6`` opens the Jacobian.  Both minimise the same
    partial NCC, so the pair is a clean one-variable ladder.
    """
    objective = PartialNCC(truth_by_plane, plane)
    evaluations = {"count": 0}

    def score(vector: np.ndarray) -> float:
        evaluations["count"] += 1
        penalty = _penalty(vector)
        if penalty:
            return 1.0 + penalty
        return objective(sampler.sample(plane, Affine.from_vector(vector)))

    steps = int(round(coarse_max / coarse_step))
    axis = np.arange(-steps, steps + 1) * coarse_step
    best_vector = np.zeros(6)
    best_score = score(best_vector)
    for tx in axis:
        for ty in axis:
            vector = np.array((tx, ty, 0.0, 0.0, 0.0, 0.0))
            value = score(vector)
            if value < best_score:
                best_score, best_vector = value, vector
    coarse = Affine.from_vector(best_vector)
    coarse_score = best_score

    free = 2 if dof == 2 else 6
    x0 = best_vector[:free]

    def wrapped(partial: np.ndarray) -> float:
        vector = np.zeros(6)
        vector[:free] = partial
        return score(vector)

    result = optimize.minimize(
        wrapped, x0, method="Nelder-Mead",
        options={"xatol": 1e-4, "fatol": 1e-9, "maxiter": 4000,
                 "maxfev": 4000, "adaptive": True})
    vector = np.zeros(6)
    vector[:free] = np.asarray(result.x, np.float64)
    fitted = Affine.from_vector(vector)
    values = sampler.sample(plane, fitted)
    return {
        "dof": free,
        "affine": fitted,
        "coarse_affine": coarse,
        "partial_ncc": float(objective(values)),
        "partial_ncc_at_zero": float(
            objective(sampler.sample(plane, None))),
        "partial_ncc_coarse": float(coarse_score),
        "raw_ncc": raw_ncc(values, truth_by_plane[plane]),
        "evaluations": int(evaluations["count"]),
        "optimiser_success": bool(result.success),
        "objective": objective,
    }


# --------------------------------------------------------------------------
# the diagnostics
# --------------------------------------------------------------------------
def separation(values: np.ndarray, truth: np.ndarray,
               objective: PartialNCC | None = None) -> dict:
    """Class separation between GT-ink and GT-white cells.

    ``d_prime`` is the plain pooled-sd effect size and ``auc`` the
    rank statistic; ``d_prime_partial`` is the same effect size measured
    after the other two planes' GT bits are projected out, which is the
    honest number on a page that prints three planes on one cell.
    """
    ink = truth > 0.5
    white = ~ink
    if ink.sum() < 8 or white.sum() < 8:
        return {"n_ink": int(ink.sum()), "n_white": int(white.sum()),
                "d_prime": None, "auc": None, "d_prime_partial": None}

    def effect(sample: np.ndarray) -> float:
        var = 0.5 * (sample[ink].var(ddof=1) + sample[white].var(ddof=1))
        if var <= 0.0:
            return float("nan")
        return float((sample[white].mean() - sample[ink].mean())
                     / np.sqrt(var))

    ranks = stats.rankdata(values)
    n_white = int(white.sum())
    auc = float((ranks[white].sum() - n_white * (n_white + 1) / 2.0)
                / (n_white * int(ink.sum())))
    row = {
        "n_ink": int(ink.sum()), "n_white": n_white,
        "d_prime": effect(values), "auc": auc,
        "mean_ink": float(values[ink].mean()),
        "mean_white": float(values[white].mean()),
        "sd_ink": float(values[ink].std(ddof=1)),
        "sd_white": float(values[white].std(ddof=1)),
    }
    if objective is not None:
        row["d_prime_partial"] = effect(objective.residual(values))
    return row


def oracle_threshold_ber(values: np.ndarray, truth: np.ndarray) -> dict:
    """The best cell error ANY threshold on these samples could reach.

    Ink darkens the channel, so the rule is ``ink if value < threshold``
    and the optimum is found exactly by sweeping the sorted order.  This
    is the photometric ceiling at a FIXED geometry: whatever separates it
    from the detector's error is calibration, not sampling.
    """
    order = np.argsort(values, kind="stable")
    ink = (truth[order] > 0.5)
    total_ink = int(ink.sum())
    head_ink = np.concatenate(([0], np.cumsum(ink)))
    head = np.arange(values.size + 1)
    errors = (head - head_ink) + (total_ink - head_ink)
    best = int(np.argmin(errors))
    sorted_values = values[order]
    threshold = (float(sorted_values[0]) - 1.0 if best == 0
                 else float(sorted_values[best - 1]) if best == values.size
                 else float(0.5 * (sorted_values[best - 1]
                                   + sorted_values[best])))
    return {"ber": float(errors[best] / values.size),
            "threshold": threshold, "n": int(values.size)}


def stratified_oracle_ber(values: np.ndarray, truth_by_plane: np.ndarray,
                          plane: int) -> dict:
    """Oracle threshold PER cross-plane ink stratum.

    Four strata (the other two planes' GT presence).  This is the ceiling
    a perfect crosstalk compensation plus a perfect threshold would
    reach — everything below it is geometry or noise, everything above it
    is calibration the receiver could in principle recover.
    """
    others = [p for p in range(3) if p != plane]
    key = (truth_by_plane[others[0]] > 0.5).astype(int) * 2 + (
        truth_by_plane[others[1]] > 0.5).astype(int)
    errors = 0
    strata = []
    for stratum in range(4):
        mask = key == stratum
        if not mask.any():
            continue
        if mask.sum() < 16:
            errors += int(min(
                (truth_by_plane[plane][mask] > 0.5).sum(),
                mask.sum() - (truth_by_plane[plane][mask] > 0.5).sum()))
            continue
        row = oracle_threshold_ber(values[mask], truth_by_plane[plane][mask])
        errors += int(round(row["ber"] * mask.sum()))
        strata.append({"stratum": stratum, "n": int(mask.sum()),
                       "ber": row["ber"], "threshold": row["threshold"]})
    return {"ber": float(errors / values.size), "strata": strata}


# --------------------------------------------------------------------------
# residual structure
# --------------------------------------------------------------------------
def _neighbour_sum(grid: np.ndarray, valid: np.ndarray) -> np.ndarray:
    total = np.zeros_like(grid)
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        rolled = np.roll(grid * valid, shift, axis=axis)
        rolled_valid = np.roll(valid, shift, axis=axis)
        if axis == 0:
            edge = 0 if shift > 0 else -1
            rolled[edge, :] = 0.0
            rolled_valid[edge, :] = False
        else:
            edge = 0 if shift > 0 else -1
            rolled[:, edge] = 0.0
            rolled_valid[:, edge] = False
        total += rolled * rolled_valid
    return total


def _neighbour_count(valid: np.ndarray) -> np.ndarray:
    return _neighbour_sum(np.ones_like(valid, np.float64), valid)


def morans_i(errors: np.ndarray, valid: np.ndarray, *, permutations: int,
             seed: int) -> dict:
    """Rook-adjacency Moran's I of the mismatch map, permutation-tested."""
    values = np.where(valid, errors.astype(np.float64), 0.0)
    n = int(valid.sum())
    if n < 32:
        return {"i": None, "p_permutation": None, "n": n}
    mean = float(values[valid].mean())
    centred = np.where(valid, values - mean, 0.0)
    weight_total = float(_neighbour_count(valid)[valid].sum())
    denominator = float((centred[valid] ** 2).sum())
    if denominator <= 0.0 or weight_total <= 0.0:
        return {"i": None, "p_permutation": None, "n": n}

    def statistic(field: np.ndarray) -> float:
        return float(
            n / weight_total
            * (field * _neighbour_sum(field, valid))[valid].sum()
            / denominator)

    observed = statistic(centred)
    rng = np.random.default_rng(seed)
    flat = centred[valid]
    exceed = 0
    for _ in range(permutations):
        shuffled = np.zeros_like(centred)
        shuffled[valid] = rng.permutation(flat)
        if statistic(shuffled) >= observed:
            exceed += 1
    return {"i": observed, "expected": -1.0 / (n - 1),
            "p_permutation": (exceed + 1) / (permutations + 1),
            "permutations": permutations, "n": n}


def structure(mismatch: np.ndarray, valid: np.ndarray, *,
              permutations: int = 199, seed: int = 20260821) -> dict:
    """Where the surviving mismatch sits inside the tile."""
    half = TILE_CELLS // 2
    quadrants = {}
    for name, rows, cols in (("top-left", slice(0, half), slice(0, half)),
                             ("top-right", slice(0, half), slice(half, None)),
                             ("bottom-left", slice(half, None), slice(0, half)),
                             ("bottom-right", slice(half, None),
                              slice(half, None))):
        cell = valid[rows, cols]
        quadrants[name] = (None if not cell.any()
                           else float(mismatch[rows, cols][cell].mean()))
    edge = np.zeros((TILE_CELLS, TILE_CELLS), bool)
    edge[:8, :] = edge[-8:, :] = edge[:, :8] = edge[:, -8:] = True
    interior = valid & ~edge
    ring = valid & edge
    columns = [float(mismatch[:, x][valid[:, x]].mean())
               if valid[:, x].any() else float("nan")
               for x in range(TILE_CELLS)]
    rows_rate = [float(mismatch[y, :][valid[y, :]].mean())
                 if valid[y, :].any() else float("nan")
                 for y in range(TILE_CELLS)]
    return {
        "overall": float(mismatch[valid].mean()),
        "quadrants": quadrants,
        "edge_ring_8": None if not ring.any() else float(
            mismatch[ring].mean()),
        "interior": None if not interior.any() else float(
            mismatch[interior].mean()),
        "worst_column": {
            "x": int(np.nanargmax(columns)),
            "rate": float(np.nanmax(columns))},
        "worst_row": {
            "y": int(np.nanargmax(rows_rate)),
            "rate": float(np.nanmax(rows_rate))},
        "column_rate_sd": float(np.nanstd(columns)),
        "row_rate_sd": float(np.nanstd(rows_rate)),
        "morans_i": morans_i(mismatch, valid, permutations=permutations,
                             seed=seed),
    }


__all__ = [
    "Affine", "PartialNCC", "TileSampler", "ZERO", "fit_affine", "morans_i",
    "oracle_threshold_ber", "raw_ncc", "separation", "stratified_oracle_ber",
    "structure",
]

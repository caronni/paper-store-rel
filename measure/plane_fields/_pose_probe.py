"""The plane-COMMON half of the probe pass, and the pose it implies.

INDEPENDENT-PLANES §2.9b measured a :class:`~holo.receive.color_field.
WindowPoseResidual` per window and applied it nowhere; docs/
COMPOSITE-POSE-DESIGN.md §6 names the writer that would apply it (the
plane-common residual belongs to the window POSE, the per-plane part to
the printer field).  This module is the measuring half of the P5-bar
instrument for that writer: it re-runs the production probe pass with the
per-SITE measurements recorded instead of summarised, and turns each
window's sites into a pose correction.

It re-implements NOTHING.  Sites come from
:func:`holo.receive.color_probes.probe_sites_for_window`, templates from
:func:`~holo.receive.color_probes.probe_template`, the correlation from
:func:`holo.receive.color_anchoring._rectified_ncc` -- the same three
production calls in the same order that
:meth:`~holo.receive.color_field.PlaneFieldBuilder.add_certified_probes`
makes (``_density.instrumented_probes`` does the same for the FIELD half;
this one keeps the LOCAL frame, which a pose correction is expressed in,
and the site's local position, which an affine needs).

TWO MODELS PER WINDOW, both plane-common, both in the window's own local
print-dot axes:

* **translation** -- the quality-weighted mean of the window's site
  residuals.  One number per window, and the one a pose writer would
  apply first.
* **local affine** -- translation plus a 2x2 in dots per CELL, fitted by
  weighted least squares with the Jacobian SHRUNK toward identity (a
  ridge whose strength is the ratio of the measured site noise to a
  declared prior on the edge displacement).  Whether it is distinguishable
  from translation-only is decided by LEAVE-ONE-SITE-OUT prediction
  error, never by in-sample fit: six parameters over a median of ~12
  sites will always fit better in sample.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

N_PLANES = 3
PLANES = ("C", "M", "Y")


@dataclass(frozen=True, slots=True)
class SiteMeasurement:
    """One (certified tile, covering window) probe, all three planes."""

    page: int
    tile_y: int
    tile_x: int
    patch_id: int
    window_ordinal: int
    window_kind: str
    rot_k: int
    centre_local_y: float
    centre_local_x: float
    centre_page_y: float
    centre_page_x: float
    template_cells: int
    #: ``(3, 2)`` LOCAL-frame ``(dx, dy)`` print dots, per plane.
    local_offsets_xy: np.ndarray
    quality: np.ndarray                       # (3,)

    @property
    def address(self) -> tuple[int, int, int]:
        return (self.page, self.tile_y, self.tile_x)

    @property
    def common_xy(self) -> np.ndarray:
        """The plane-COMMON part: the mean over the three planes.

        Production's definition, verbatim (``PlaneFieldBuilder.
        add_certified_probes`` records ``np.mean(local_offsets, axis=0)``
        for sites where every plane measured).
        """
        return np.asarray(self.local_offsets_xy, np.float64).mean(axis=0)

    @property
    def weight(self) -> float:
        return float(min(1.0, np.mean(self.quality)))


def collect_site_measurements(
    spec, raster, regions, projection_for, config, kind: str = "all",
) -> list[SiteMeasurement]:
    """Every probe site of every offered window, per-plane and LOCAL.

    The gates are production's: a site with no template, a flat plane, an
    off-raster correlation or a quality below
    ``config.probe_min_quality`` contributes nothing, exactly as it
    contributes nothing to the field.  Only sites where ALL THREE planes
    survived carry a plane-common component -- a mean over a varying
    subset of planes is not a common component.
    """
    from holo.receive.color_anchoring import _rectified_ncc
    from holo.receive.color_probes import (
        probe_sites_for_window,
        probe_template,
        template_is_flat,
    )

    tiles_x = int(spec.layout.tiles_yx[1])
    block_cells = int(config.probe_block_cells)
    rows: list[SiteMeasurement] = []
    for region in regions:
        windows = region.select(kind)
        sites = []
        for ordinal, window in enumerate(windows):
            sites.extend(probe_sites_for_window(
                window, ordinal, config.probe_mode,
                lambda address: projection_for(address) is not None,
                tiles_x, block_cells=block_cells,
                bins_per_tile=int(config.bins_per_tile)))
        sites.sort(key=lambda site: (
            site.page, site.page_y, site.page_x, site.window_ordinal))
        for site in sites:
            window = windows[site.window_ordinal]
            projected = projection_for(site.address)
            if projected is None:
                continue
            template = probe_template(
                window, site, projected, min_edge_cells=block_cells)
            if template is None:
                continue
            bits, weights = template
            inside = weights > 0.0
            offsets = np.full((N_PLANES, 2), np.nan, np.float64)
            quality = np.full(N_PLANES, np.nan, np.float64)
            for plane in range(N_PLANES):
                plane_bits = bits[..., plane]
                if template_is_flat(plane_bits, inside):
                    continue
                measured = _rectified_ncc(
                    raster, window.patch, spec, site.centre_local_yx,
                    plane_bits, weights, plane)
                if measured is None:
                    continue
                offset_dots_xy, value = measured
                if value < config.probe_min_quality:
                    continue
                offsets[plane] = offset_dots_xy
                quality[plane] = float(value)
            if not np.isfinite(offsets).all():
                continue
            centre_local = site.centre_local_yx
            rows.append(SiteMeasurement(
                page=site.page,
                tile_y=site.address[1], tile_x=site.address[2],
                patch_id=int(window.patch.patch_id),
                window_ordinal=int(site.window_ordinal),
                window_kind=region.kind_of(site.window_ordinal, kind),
                rot_k=int(window.patch.segment.rot_k),
                centre_local_y=float(centre_local[0]),
                centre_local_x=float(centre_local[1]),
                centre_page_y=float(site.centre_page_yx[0]),
                centre_page_x=float(site.centre_page_yx[1]),
                template_cells=int(inside.sum()),
                local_offsets_xy=offsets,
                quality=quality,
            ))
    return rows


# --------------------------------------------------------------------------
# the per-window pose correction
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class WindowPose:
    """One window's plane-common correction, translation and affine."""

    page: int
    patch_id: int
    window_kind: str
    n_sites: int
    weight_total: float
    #: The site cloud's weighted centroid in LOCAL cells, ``(cx, cy)`` --
    #: the affine's origin, and part of the correction's definition.
    centroid_xy: tuple[float, float]
    half_extent_cells: float
    #: The correction a translation-only writer would apply, LOCAL dots.
    translation_xy: tuple[float, float]
    #: Production's own summary of the same sites (median, MAD), kept so
    #: the instrument can be checked against ``WindowPoseResidual``.
    median_xy: tuple[float, float]
    spread_xy: tuple[float, float]
    #: Dots per CELL, the affine's shrunk Jacobian deviation.
    jacobian: tuple[tuple[float, float], tuple[float, float]]
    shrinkage: float
    noise_sd_dots: float
    #: Leave-one-site-out prediction error, dots (nan when < 4 sites).
    cv_translation_dots: float
    cv_affine_dots: float
    rms_translation_dots: float
    rms_affine_dots: float

    @property
    def magnitude_dots(self) -> float:
        return float(np.hypot(*self.translation_xy))

    @property
    def median_magnitude_dots(self) -> float:
        return float(np.hypot(*self.median_xy))

    @property
    def spread_dots(self) -> float:
        return float(np.hypot(*self.spread_xy))

    @property
    def consistent(self) -> bool:
        """Production's rule: the sites AGREE when spread < half magnitude."""
        return bool(self.n_sites > 1
                    and self.spread_dots < 0.5 * self.median_magnitude_dots)

    @property
    def affine_edge_dots(self) -> float:
        """Extra displacement the Jacobian produces at the site cloud's edge."""
        matrix = np.asarray(self.jacobian, np.float64)
        return float(np.linalg.norm(matrix, 2) * self.half_extent_cells)

    @property
    def affine_distinguishable(self) -> bool:
        """Does the affine PREDICT a held-out site better than translation?"""
        return bool(np.isfinite(self.cv_affine_dots)
                    and np.isfinite(self.cv_translation_dots)
                    and self.cv_affine_dots < self.cv_translation_dots)

    def offsets(self, local_cells_yx: np.ndarray, *, affine: bool
                ) -> np.ndarray:
        """``(n, 2)`` LOCAL ``(dx, dy)`` dot correction for these cells."""
        cells = np.asarray(local_cells_yx, np.float64)
        out = np.empty((cells.shape[0], 2), np.float64)
        out[:] = np.asarray(self.translation_xy, np.float64)
        if affine:
            delta = np.stack(
                (cells[:, 1] - self.centroid_xy[0],
                 cells[:, 0] - self.centroid_xy[1]), axis=1)
            out += delta @ np.asarray(self.jacobian, np.float64).T
        return out


def _weighted_fit(delta_xy: np.ndarray, values_xy: np.ndarray,
                  weights: np.ndarray, ridge: float
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Ridge-shrunk ``(translation, jacobian)`` for one centred site set.

    ``delta_xy`` is already weight-centred, so the translation is the
    plain weighted mean and the Jacobian solves the shrunk normal
    equations independently -- shrinking M toward ZERO is shrinking the
    sampling grid's Jacobian toward IDENTITY, which is the composite
    design's default (COMPOSITE-POSE-DESIGN §4.1).
    """
    total = float(weights.sum())
    translation = (weights[:, None] * values_xy).sum(axis=0) / total
    residual = values_xy - translation
    gram = (weights[:, None, None] * delta_xy[:, :, None]
            * delta_xy[:, None, :]).sum(axis=0)
    cross = (weights[:, None, None] * residual[:, :, None]
             * delta_xy[:, None, :]).sum(axis=0)
    jacobian = np.linalg.solve(
        gram + ridge * np.eye(2), cross.T).T
    return translation, jacobian


def _cv_errors(delta_xy, values_xy, weights, ridge) -> tuple[float, float]:
    """Leave-one-site-out prediction error for both models, in dots."""
    n = values_xy.shape[0]
    translation_error = np.empty(n)
    affine_error = np.empty(n)
    for index in range(n):
        keep = np.ones(n, bool)
        keep[index] = False
        centre = ((weights[keep, None] * delta_xy[keep]).sum(axis=0)
                  / weights[keep].sum())
        centred = delta_xy[keep] - centre
        translation, jacobian = _weighted_fit(
            centred, values_xy[keep], weights[keep], ridge)
        translation_error[index] = np.hypot(
            *(values_xy[index] - translation))
        predicted = translation + jacobian @ (delta_xy[index] - centre)
        affine_error[index] = np.hypot(*(values_xy[index] - predicted))
    return (float(translation_error.mean()), float(affine_error.mean()))


def fit_window_poses(
    sites: list[SiteMeasurement],
    *,
    prior_edge_dots: float = 0.25,
    noise_floor_dots: float = 0.02,
    min_affine_sites: int = 6,
) -> dict[int, WindowPose]:
    """One :class:`WindowPose` per window that produced any site.

    ``prior_edge_dots`` is the shrinkage prior expressed the only way a
    reader can judge it: how many print dots of EXTRA displacement the
    Jacobian is a priori allowed to produce at the edge of the window's
    site cloud.  0.25 dot is the field's own adoption cliff -- the
    threshold below which INDEPENDENT-PLANES has repeatedly measured a
    correction not to be worth believing.
    """
    grouped: dict[int, list[SiteMeasurement]] = {}
    for site in sites:
        grouped.setdefault(site.patch_id, []).append(site)
    out: dict[int, WindowPose] = {}
    for patch_id, rows in sorted(grouped.items()):
        values = np.asarray([row.common_xy for row in rows], np.float64)
        weights = np.asarray([row.weight for row in rows], np.float64)
        cells = np.asarray(
            [(row.centre_local_x, row.centre_local_y) for row in rows],
            np.float64)
        total = float(weights.sum())
        if total <= 0.0:
            continue
        centroid = (weights[:, None] * cells).sum(axis=0) / total
        delta = cells - centroid
        half_extent = float(np.linalg.norm(delta, axis=1).max())
        median = np.median(values, axis=0)
        spread = np.median(np.abs(values - median), axis=0)
        translation = (weights[:, None] * values).sum(axis=0) / total
        noise = float(np.sqrt(
            (weights * ((values - translation) ** 2).sum(axis=1)).sum()
            / (2.0 * total)))
        noise = max(noise, noise_floor_dots)
        prior_sd = prior_edge_dots / max(half_extent, 1.0)
        ridge = (noise / prior_sd) ** 2
        jacobian = np.zeros((2, 2))
        cv_translation = cv_affine = float("nan")
        rms_affine = rms_translation = float(np.sqrt(
            (weights * ((values - translation) ** 2).sum(axis=1)).sum()
            / total))
        shrinkage = float("nan")
        if len(rows) >= min_affine_sites and half_extent > 0.0:
            _t, jacobian = _weighted_fit(delta, values, weights, ridge)
            gram = (weights[:, None, None] * delta[:, :, None]
                    * delta[:, None, :]).sum(axis=0)
            eigenvalues = np.linalg.eigvalsh(gram)
            shrinkage = float(np.mean(
                eigenvalues / (eigenvalues + ridge)))
            predicted = translation + delta @ jacobian.T
            rms_affine = float(np.sqrt(
                (weights * ((values - predicted) ** 2).sum(axis=1)).sum()
                / total))
            cv_translation, cv_affine = _cv_errors(
                delta, values, weights, ridge)
        out[patch_id] = WindowPose(
            page=rows[0].page,
            patch_id=patch_id,
            window_kind=rows[0].window_kind,
            n_sites=len(rows),
            weight_total=total,
            centroid_xy=(float(centroid[0]), float(centroid[1])),
            half_extent_cells=half_extent,
            translation_xy=(float(translation[0]), float(translation[1])),
            median_xy=(float(median[0]), float(median[1])),
            spread_xy=(float(spread[0]), float(spread[1])),
            jacobian=((float(jacobian[0, 0]), float(jacobian[0, 1])),
                      (float(jacobian[1, 0]), float(jacobian[1, 1]))),
            shrinkage=shrinkage,
            noise_sd_dots=noise,
            cv_translation_dots=cv_translation,
            cv_affine_dots=cv_affine,
            rms_translation_dots=rms_translation,
            rms_affine_dots=rms_affine,
        )
    return out


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def _spread(values: np.ndarray) -> dict:
    finite = np.asarray(values, np.float64)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return {"n": 0}
    return {
        "n": int(finite.size),
        "mean": float(finite.mean()),
        "median": float(np.median(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p90": float(np.percentile(finite, 90)),
        "max": float(finite.max()),
    }


def pose_summary(poses: dict[int, WindowPose], *, dead_columns=()) -> dict:
    """The residual distribution, whole and split by window kind."""
    rows = sorted(poses.values(), key=lambda row: row.patch_id)

    def block(subset: list[WindowPose]) -> dict:
        if not subset:
            return {"windows": 0}
        magnitude = np.asarray([row.magnitude_dots for row in subset])
        spread = np.asarray([row.spread_dots for row in subset])
        sites = np.asarray([row.n_sites for row in subset])
        multi = sites > 1
        affine_rows = [row for row in subset
                       if np.isfinite(row.cv_affine_dots)]
        return {
            "windows": len(subset),
            "sites_total": int(sites.sum()),
            "sites_per_window_median": float(np.median(sites)),
            "magnitude_dots": _spread(magnitude),
            "median_magnitude_dots": _spread(np.asarray(
                [row.median_magnitude_dots for row in subset])),
            "within_window_spread_dots": _spread(spread),
            "dx_dots": _spread(np.asarray(
                [row.translation_xy[0] for row in subset])),
            "dy_dots": _spread(np.asarray(
                [row.translation_xy[1] for row in subset])),
            "windows_with_multiple_sites": int(multi.sum()),
            "fraction_consistent": (
                float(np.mean([row.consistent for row in subset if
                               row.n_sites > 1])) if multi.any()
                else float("nan")),
            "affine": {
                "windows_fitted": len(affine_rows),
                "edge_displacement_dots": _spread(np.asarray(
                    [row.affine_edge_dots for row in affine_rows])),
                "shrinkage": _spread(np.asarray(
                    [row.shrinkage for row in affine_rows])),
                "cv_translation_dots": _spread(np.asarray(
                    [row.cv_translation_dots for row in affine_rows])),
                "cv_affine_dots": _spread(np.asarray(
                    [row.cv_affine_dots for row in affine_rows])),
                "fraction_cv_better_than_translation": (
                    float(np.mean([row.affine_distinguishable
                                   for row in affine_rows]))
                    if affine_rows else float("nan")),
                "rms_translation_dots": _spread(np.asarray(
                    [row.rms_translation_dots for row in affine_rows])),
                "rms_affine_dots": _spread(np.asarray(
                    [row.rms_affine_dots for row in affine_rows])),
            },
        }

    del dead_columns
    return {
        "all_windows": block(rows),
        "label_only_windows": block(
            [row for row in rows if row.window_kind == "label-only"]),
        "mixed_windows": block(
            [row for row in rows if row.window_kind == "mixed"]),
    }


def cross_check_production(poses: dict[int, WindowPose], report) -> dict:
    """This module's medians against ``PlaneFieldReport``'s own.

    The instrument runs the same three production calls the builder runs;
    if it is faithful, the per-window MEDIAN plane-common offset and the
    site count must agree exactly.  Any disagreement means the collector
    drifted from the pass it claims to measure, and the run is not
    reportable.
    """
    mine = {row.patch_id: row for row in poses.values()}
    worst_offset = 0.0
    worst_spread = 0.0
    missing: list[int] = []
    site_mismatch: list[int] = []
    for row in report.window_pose_residuals:
        found = mine.get(int(row.patch_id))
        if found is None:
            missing.append(int(row.patch_id))
            continue
        if found.n_sites != int(row.n_sites):
            site_mismatch.append(int(row.patch_id))
        worst_offset = max(worst_offset, abs(
            found.median_xy[0] - row.median_dx_dots), abs(
            found.median_xy[1] - row.median_dy_dots))
        worst_spread = max(worst_spread, abs(
            found.spread_xy[0] - row.spread_dx_dots), abs(
            found.spread_xy[1] - row.spread_dy_dots))
    return {
        "production_windows": len(report.window_pose_residuals),
        "instrument_windows": len(mine),
        "windows_missing_from_instrument": missing,
        "windows_with_different_site_counts": site_mismatch,
        "max_abs_median_difference_dots": worst_offset,
        "max_abs_spread_difference_dots": worst_spread,
        "exact": bool(not missing and not site_mismatch
                      and worst_offset == 0.0 and worst_spread == 0.0),
    }


__all__ = [
    "N_PLANES", "PLANES", "SiteMeasurement", "WindowPose",
    "collect_site_measurements", "cross_check_production",
    "fit_window_poses", "pose_summary",
]

"""Shared-sheet and per-plane color registration primitives.

This module ports the robust constant-plus-page-Y residual fit from
``paperholo.acquire._fit_offset_model`` (E017/D5).  The Holo adapter retains
one shared page/lane affine and represents C, M, and Y only as residuals on
top of it:

``delta_plane(y) = (dx0 + dx1*y, dy0 + dy1*y)``.

Coordinates exposed here are explicitly ``(x, y)`` and homogeneous affine
matrices follow that order.  ``page_y_fraction`` is supplied separately to
make the residual model's normalized absolute-page coordinate unambiguous.
Anchor extraction/NCC and image resampling remain adapter responsibilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np



COLOR_ANCHOR_MIN: Final = 8
COLOR_SLOPE_MIN: Final = 16
COLOR_SLOPE_MIN_SPAN: Final = 0.15
COLOR_ANCHOR_INLIER: Final = 0.5


def _point_rows(values: np.ndarray, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 2:
        raise ValueError(
            f"color registration: {name} must have shape (N, 2) in x/y order")
    if not np.isfinite(result).all():
        raise ValueError(f"color registration: {name} must be finite")
    return result


def _offset_rows(values: np.ndarray) -> np.ndarray:
    """Anchor offsets; non-finite entries are historical missing values."""
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 2:
        raise ValueError(
            "color registration: observed_offsets_xy must have shape "
            "(N, 2) in x/y order")
    return result


@dataclass(frozen=True, slots=True)
class PlaneResidual:
    """One plane's x/y residual in the coordinate units supplied by caller."""

    intercept_xy: tuple[float, float]
    slope_xy: tuple[float, float]
    n_anchors: int

    def __post_init__(self) -> None:
        intercept = np.asarray(self.intercept_xy, dtype=np.float64)
        slope = np.asarray(self.slope_xy, dtype=np.float64)
        if (intercept.shape != (2,) or slope.shape != (2,)
                or not np.isfinite(intercept).all()
                or not np.isfinite(slope).all()):
            raise ValueError(
                "color registration: residual coefficients must be finite x/y")
        if (isinstance(self.n_anchors, bool)
                or not isinstance(self.n_anchors, (int, np.integer))
                or self.n_anchors < 0):
            raise ValueError(
                "color registration: n_anchors must be nonnegative")
        object.__setattr__(
            self, "intercept_xy",
            (float(intercept[0]), float(intercept[1])),
        )
        object.__setattr__(
            self, "slope_xy", (float(slope[0]), float(slope[1])))
        object.__setattr__(self, "n_anchors", int(self.n_anchors))

    @property
    def supported(self) -> bool:
        return self.n_anchors >= COLOR_ANCHOR_MIN

    def offsets(self, page_y_fraction: np.ndarray) -> np.ndarray:
        y_fraction = np.asarray(page_y_fraction, dtype=np.float64)
        if not np.isfinite(y_fraction).all():
            raise ValueError(
                "color registration: page_y_fraction must be finite")
        return (
            np.asarray(self.intercept_xy)
            + y_fraction[..., None] * np.asarray(self.slope_xy)
        )


def _fit_component(
    page_y_fraction: np.ndarray,
    offsets: np.ndarray,
    quality: np.ndarray,
) -> tuple[float, float, int]:
    """Exact historical Theil–Sen + inlier-LSQ scalar residual fit."""
    valid = np.isfinite(offsets) & (quality > 0.0)
    n_valid = int(valid.sum())
    if n_valid < COLOR_ANCHOR_MIN:
        return 0.0, 0.0, n_valid
    y_fraction = page_y_fraction[valid]
    values = offsets[valid]
    if (
        n_valid < COLOR_SLOPE_MIN
        or float(y_fraction.max() - y_fraction.min())
        < COLOR_SLOPE_MIN_SPAN
    ):
        return float(np.median(values)), 0.0, n_valid

    left, right = np.triu_indices(n_valid, 1)
    delta_y = y_fraction[left] - y_fraction[right]
    usable = np.abs(delta_y) > 0.05
    if not usable.any():
        return float(np.median(values)), 0.0, n_valid
    slope = float(np.median(
        (values[left][usable] - values[right][usable])
        / delta_y[usable]
    ))
    intercept = float(np.median(values - slope * y_fraction))
    inliers = np.abs(
        values - (intercept + slope * y_fraction)
    ) <= COLOR_ANCHOR_INLIER
    n_inliers = int(inliers.sum())
    if n_inliers >= COLOR_ANCHOR_MIN:
        design = np.stack(
            (np.ones(n_inliers), y_fraction[inliers]), axis=1)
        coefficients, *_ = np.linalg.lstsq(
            design, values[inliers], rcond=None)
        return (
            float(coefficients[0]),
            float(coefficients[1]),
            n_inliers,
        )
    return intercept, slope, n_valid


def fit_plane_residual(
    page_y_fraction: np.ndarray,
    observed_offsets_xy: np.ndarray,
    quality: np.ndarray,
) -> PlaneResidual:
    """Fit one plane residual from offsets measured after shared alignment.

    Quality is a validity gate only (strictly positive means usable), exactly
    as in E017; it is not a regression weight.  Below eight valid anchors the
    historical zero model is returned.  Below 16 anchors or 0.15 page span,
    only the median constant is retained.
    """
    y_fraction = np.asarray(page_y_fraction, dtype=np.float64)
    offsets = _offset_rows(observed_offsets_xy)
    q = np.asarray(quality, dtype=np.float64)
    if y_fraction.ndim != 1 or q.ndim != 1:
        raise ValueError(
            "color registration: y fractions and quality must be vectors")
    if y_fraction.size != offsets.shape[0] or q.size != offsets.shape[0]:
        raise ValueError(
            "color registration: residual observation lengths differ")
    if not np.isfinite(y_fraction).all():
        raise ValueError(
            "color registration: page_y_fraction must be finite")
    if np.any(np.isinf(q)):
        raise ValueError("color registration: quality must not be infinite")

    x_intercept, x_slope, n_x = _fit_component(
        y_fraction, offsets[:, 0], q)
    y_intercept, y_slope, n_y = _fit_component(
        y_fraction, offsets[:, 1], q)
    return PlaneResidual(
        intercept_xy=(x_intercept, y_intercept),
        slope_xy=(x_slope, y_slope),
        n_anchors=min(n_x, n_y),
    )

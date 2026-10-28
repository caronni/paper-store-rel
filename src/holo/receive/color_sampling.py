"""The color sampling leaf: crops, aperture filtering, point sampling.

One home for every raster access the color payload path makes.  These are
pure functions of a bounded RGB footprint and a set of scan points — they
know nothing about detectors, certificates, registration, or evidence:

* :func:`native_crop` reads one local RGB footprint (never a multi-window
  union);
* :func:`filtered_crop` applies the aperture box filter and the region
  divisor;
* :func:`window_crop` / :func:`points_crop` compose those two for the two
  footprints the receiver uses (an E022 window, and an exact corrected
  point set);
* :func:`sample` interpolates a filtered image at scan points; and
* :func:`window_raw_crops` / :func:`crop_features` are the region-level
  batch forms (one native read per window, shared by the divisor probe and
  the base features).

Split out of :mod:`holo.receive.color_anchoring` (PK2, RECEIVE-DESIGN
§6.2a "the sampling leaf is a stable contract the pixel rework keeps"):
the same functions with the same numerics, so registration/NCC anchoring
and payload feature extraction draw from ONE implementation.  Crops are
transient and never cross into persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy import ndimage

from . import _parallel
from ._payload_sampling import APERTURE_CELLS
from .payload_model import PlacementModelError
from .placement.model import PlacedPatch


class RawRGBRaster(Protocol):
    """Bounded aligned RGB access supplied by a color scale lane."""

    shape: tuple[int, int]

    def crop_native(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class LocalCrop:
    y0: int
    x0: int
    # Native RGB is retained without a float64 full-page normalization.
    # NCC is affine-intensity invariant; detector means use ``filtered``.
    rgb: np.ndarray
    filtered: np.ndarray


def native_crop(
    raster: RawRGBRaster,
    points_yx: np.ndarray,
    halo: int,
) -> tuple[int, int, np.ndarray]:
    """Read one local RGB footprint, never a multi-window union."""
    points = np.asarray(points_yx, np.float64)
    if (points.ndim != 2 or points.shape[1:] != (2,)
            or points.shape[0] == 0 or not np.isfinite(points).all()):
        raise PlacementModelError(
            "color payload: local crop points are malformed")
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(raster.shape[0], int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(raster.shape[1], int(np.ceil(points[:, 1].max())) + halo)
    if y1 <= y0 or x1 <= x0:
        raise PlacementModelError(
            "color payload: local footprint misses RGB raster")
    raw = np.asarray(raster.crop_native(y0, y1, x0, x1))
    if raw.shape != (y1 - y0, x1 - x0, 3):
        raise ValueError(
            "color payload: color lane did not return aligned RGB")
    return y0, x0, raw


def window_points(
    patch: PlacedPatch,
) -> np.ndarray:
    placed = patch.segment
    height, width = placed.segment.window.shape_yx_cells
    local = np.asarray(
        ((-2, -2), (-2, width + 2),
         (height + 2, -2), (height + 2, width + 2)),
        np.float64,
    )
    return placed.segment.pose.points(local)


def window_halo(pitch_px: float) -> int:
    """Exact halo of the historical probe/base window crops."""
    return int(np.ceil(1.5 * pitch_px)) + 3


def window_crop(
    raster: RawRGBRaster,
    patch: PlacedPatch,
    pitch_px: float,
    divisor: float,
) -> LocalCrop:
    """Build one transient filtered E022-window crop."""
    y0, x0, raw = native_crop(
        raster, window_points(patch), window_halo(pitch_px))
    return filtered_crop(y0, x0, raw, pitch_px, divisor)


def filtered_crop(
    y0: int,
    x0: int,
    raw: np.ndarray,
    pitch_px: float,
    divisor: float,
) -> LocalCrop:
    aperture = max(1, int(round(APERTURE_CELLS * pitch_px)))
    filtered = np.empty(raw.shape, np.float32)
    for channel_index in range(3):
        ndimage.uniform_filter(
            raw[..., channel_index],
            size=aperture,
            output=filtered[..., channel_index],
            mode="nearest",
        )
    if divisor != 1.0:
        filtered /= np.float32(divisor)
    return LocalCrop(y0, x0, raw, filtered)


def points_crop(
    raster: RawRGBRaster,
    points_yx: np.ndarray,
    pitch_px: float,
    divisor: float,
) -> LocalCrop:
    """Filter only the exact corrected-point footprint plus aperture halo."""
    halo = int(np.ceil(APERTURE_CELLS * pitch_px)) + 2
    y0, x0, raw = native_crop(raster, points_yx, halo)
    return filtered_crop(y0, x0, raw, pitch_px, divisor)


def sample(
    image: np.ndarray,
    crop: LocalCrop,
    points_yx: np.ndarray,
) -> np.ndarray:
    local = np.asarray(points_yx, np.float64) - np.asarray(
        (crop.y0, crop.x0), np.float64)
    if local.size and (
        np.any(local[:, 0] < 0.0)
        or np.any(local[:, 1] < 0.0)
        or np.any(local[:, 0] > image.shape[0] - 1)
        or np.any(local[:, 1] > image.shape[1] - 1)
    ):
        raise PlacementModelError(
            "color payload: corrected sample leaves the region crop")
    return np.stack(tuple(
        ndimage.map_coordinates(
            image[..., channel], local.T, order=1, mode="nearest",
            output=np.float64)
        for channel in range(3)
    ), axis=1)


def window_raw_crops(
    raster: RawRGBRaster,
    patches: tuple[PlacedPatch, ...],
    pitch_px: float,
) -> dict[int, tuple[int, int, np.ndarray]]:
    """Read each window's probe/base native RGB footprint exactly once.

    The transient raw crops feed BOTH the region divisor probe and the
    filtered base features (color-upstream:07: previously two identical
    native reads per window); they are released with the region.
    """
    halo = window_halo(pitch_px)
    crops = _parallel.ordered_map(
        lambda patch: native_crop(raster, window_points(patch), halo),
        patches)
    return {int(patch.patch_id): crop
            for patch, crop in zip(patches, crops, strict=True)}


def crop_features(
    crop: tuple[int, int, np.ndarray],
    scan_points_yx: np.ndarray,
    pitch_px: float,
    divisor: float,
) -> np.ndarray:
    """Filter one pre-read window crop and sample its aligned rows."""
    y0, x0, raw = crop
    filtered = filtered_crop(y0, x0, raw, pitch_px, divisor)
    return sample(filtered.filtered, filtered, scan_points_yx)


__all__ = [
    "LocalCrop", "RawRGBRaster", "crop_features", "filtered_crop",
    "native_crop", "points_crop", "sample", "window_crop", "window_halo",
    "window_points", "window_raw_crops",
]

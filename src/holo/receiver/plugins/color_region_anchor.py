from __future__ import annotations

import numpy as np
from scipy import ndimage

from ..data import WindowRows
from ..lib import page_map

#: The sampling box aperture, in cells, carried verbatim from v1's
#: payload sampler.  plugins/pose.py and plugins/calibrate.py declare
#: the same number independently -- it is one channel fact and the
#: three must move together.  09-detect-calibrate-k.md:52.
APERTURE_CELLS: float = 0.7

Planes = tuple[np.ndarray, np.ndarray, np.ndarray]
Affine = tuple[float, float, float, float, float, float]


def pose_points(affine: Affine, local_yx: np.ndarray) -> np.ndarray:
    cells = np.asarray(local_yx, np.float64)
    return cells @ pose_linear(affine).T + np.asarray(
        (affine[2], affine[5]), np.float64)


def pose_linear(affine: Affine) -> np.ndarray:
    a, b, _c, d, e, _f = affine
    return np.asarray(((a, b), (d, e)), np.float64)


def window_halo(pitch_px: float) -> int:
    return int(np.ceil(1.5 * pitch_px)) + 3


def points_halo(pitch_px: float) -> int:
    return int(np.ceil(APERTURE_CELLS * pitch_px)) + 2


def window_points(shape_yx_cells: tuple[int, int],
                  affine: Affine) -> np.ndarray:
    height, width = shape_yx_cells
    local = np.asarray(
        ((-2, -2), (-2, width + 2),
         (height + 2, -2), (height + 2, width + 2)),
        np.float64)
    return pose_points(affine, local)


def native_crop(planes: Planes, points_yx: np.ndarray,
                halo: int) -> tuple[int, int, np.ndarray]:
    points = np.asarray(points_yx, np.float64)
    shape = planes[0].shape
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(shape[0], int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(shape[1], int(np.ceil(points[:, 1].max())) + halo)
    raw = np.stack(
        tuple(np.asarray(plane[y0:y1, x0:x1]) for plane in planes),
        axis=-1)
    return y0, x0, raw


def crop_maximum(planes: Planes, points_yx: np.ndarray,
                 halo: int) -> float:
    _y0, _x0, raw = native_crop(planes, points_yx, halo)
    return float(np.max(raw)) if raw.size else 0.0


def native_divisor(maxima: tuple[float, ...]) -> float:
    return 255.0 if max(maxima) > 1.5 else 1.0


def filtered_rgb(raw: np.ndarray, pitch_px: float,
                 divisor: float) -> np.ndarray:
    aperture = max(1, int(round(APERTURE_CELLS * pitch_px)))
    filtered = np.empty(raw.shape, np.float32)
    for channel in range(3):
        ndimage.uniform_filter(
            raw[..., channel], size=aperture,
            output=filtered[..., channel], mode="nearest")
    if divisor != 1.0:
        filtered /= np.float32(divisor)
    return filtered


def sample_rgb(filtered: np.ndarray, y0: int, x0: int,
               points_yx: np.ndarray) -> np.ndarray:
    local = np.asarray(points_yx, np.float64) - np.asarray(
        (y0, x0), np.float64)
    return np.stack(tuple(
        ndimage.map_coordinates(
            filtered[..., channel], local.T, order=1, mode="nearest",
            output=np.float64)
        for channel in range(3)), axis=1)


def sample_plane(filtered: np.ndarray, y0: int, x0: int,
                 points_yx: np.ndarray, plane: int) -> np.ndarray:
    """One channel of `sample_rgb`, for the price of one channel.

    Bit-identical to `sample_rgb(...)[:, plane]` -- the same crop-origin
    subtraction, the same order-1 nearest-edge interpolation, the same
    float64 output -- and 2.90x cheaper where the caller wants one plane
    (measured 2026-09-12 through the collection's own sampler, 961
    offsets x 4,096 sites: 0.341 s against 0.118 s, values equal).
    """
    local = np.asarray(points_yx, np.float64) - np.asarray(
        (y0, x0), np.float64)
    return ndimage.map_coordinates(filtered[..., plane], local.T, order=1,
                                   mode="nearest", output=np.float64)


def crop_features(crop: tuple[int, int, np.ndarray],
                  scan_points_yx: np.ndarray, pitch_px: float,
                  divisor: float) -> np.ndarray:
    y0, x0, raw = crop
    return sample_rgb(
        filtered_rgb(raw, pitch_px, divisor), y0, x0, scan_points_yx)


def features_at(
    planes: Planes,
    rows: WindowRows,
    page_linear: np.ndarray,
    offsets_dots_xy: tuple[np.ndarray | None, np.ndarray | None,
                           np.ndarray | None],
    cell_dots: int,
    pitch_px: float,
    divisor: float,
) -> np.ndarray | None:
    """One window's three planes, each read at its own page offset.

    `offsets_dots_xy` is per plane, `(N, 2)` in printed dots along the
    PAGE axes, row for row with `rows`; a plane with `None` is read at
    the pose.  Three point sets, ONE crop and ONE filter over their
    union, because the aperture is a property of the region and not of
    the plane.
    """
    shape = planes[0].shape
    points_by_plane: list[np.ndarray] = []
    for offset in offsets_dots_xy:
        points = (
            np.asarray(rows.scan_points_yx, np.float64) if offset is None
            else page_map.raster_points(rows.scan_points_yx, page_linear,
                                        offset, cell_dots))
        # ANY corrected point outside the raster makes the REGION's whole
        # corrected arm ineligible, not just this window's -- one None
        # collapses the tuple.  The shared pose stays usable and the base arm
        # still fits.  11-colour-planes-ctx.md:125-127.
        if points.size and (
            np.any(points[:, 0] < 0.0)
            or np.any(points[:, 1] < 0.0)
            or np.any(points[:, 0] > shape[0] - 1)
            or np.any(points[:, 1] > shape[1] - 1)
        ):
            return None
        points_by_plane.append(points)
    y0, x0, raw = native_crop(
        planes, np.concatenate(points_by_plane), points_halo(pitch_px))
    filtered = filtered_rgb(raw, pitch_px, divisor)
    result = np.empty((rows.page_cells_yx.shape[0], 3), np.float64)
    for plane, points in enumerate(points_by_plane):
        local = points - np.asarray((y0, x0), np.float64)
        result[:, plane] = ndimage.map_coordinates(
            filtered[..., plane], local.T, order=1, mode="nearest")
    return result

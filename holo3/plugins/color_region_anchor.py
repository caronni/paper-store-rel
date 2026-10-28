from __future__ import annotations

import numpy as np
from scipy import ndimage

from ..data import PlaneResidual, WindowRows
from ..lib.geometry import site_parity
from .color_model import BLIND_CONFIDENT_LLR, blind_component_bits

APERTURE_CELLS: float = 0.7
RECTIFIED_PX_PER_DOT: int = 2
ANCHOR_MIN_Q: float = 0.10
ANCHOR_MAX_SHIFT_PX: int = 5
ANCHOR_BUDGET_PER_KIND: int = 512
COLOR_ANCHOR_MIN: int = 8
COLOR_SLOPE_MIN: int = 16
COLOR_SLOPE_MIN_SPAN: float = 0.15
COLOR_ANCHOR_INLIER: float = 0.5

Planes = tuple[np.ndarray, np.ndarray, np.ndarray]
Affine = tuple[float, float, float, float, float, float]


def pose_points(affine: Affine, local_yx: np.ndarray) -> np.ndarray:
    cells = np.asarray(local_yx, np.float64)
    return cells @ pose_linear(affine).T + np.asarray(
        (affine[2], affine[5]), np.float64)


def pose_linear(affine: Affine) -> np.ndarray:
    a, b, _c, d, e, _f = affine
    return np.asarray(((a, b), (d, e)), np.float64)


def shifted_points(points_yx: np.ndarray, linear: np.ndarray,
                   delta_cells_xy: np.ndarray) -> np.ndarray:
    """Move sample points by a per-cell delta expressed in CELLS (x, y).

    `linear` is a window pose's cell->pixel 2x2, so the delta it carries
    is in CELLS.  A caller holding a registration delta in printed DOTS
    divides by the row's `cell_dots` before it gets here, and every call
    site in the colour lane does exactly that.
    """
    delta = np.asarray(delta_cells_xy, np.float64)[:, ::-1]
    return points_yx + delta @ linear.T


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


def crop_features(crop: tuple[int, int, np.ndarray],
                  scan_points_yx: np.ndarray, pitch_px: float,
                  divisor: float) -> np.ndarray:
    y0, x0, raw = crop
    return sample_rgb(
        filtered_rgb(raw, pitch_px, divisor), y0, x0, scan_points_yx)


def neighbor_rows(local_cells_yx: np.ndarray) -> np.ndarray:
    local = np.asarray(local_cells_yx, np.int64)
    output = np.full((local.shape[0], 9), -1, np.int32)
    if not local.shape[0]:
        return output
    lookup = np.full(
        (int(local[:, 0].max()) + 1, int(local[:, 1].max()) + 1),
        -1, np.int32)
    lookup[local[:, 0], local[:, 1]] = np.arange(
        local.shape[0], dtype=np.int32)
    ordinal = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y = local[:, 0] + dy
            x = local[:, 1] + dx
            valid = (
                (y >= 0) & (y < lookup.shape[0])
                & (x >= 0) & (x < lookup.shape[1])
            )
            output[valid, ordinal] = lookup[y[valid], x[valid]]
            ordinal += 1
    return output


def xcorr_offset_ncc(
    window: np.ndarray,
    template: np.ndarray,
    weight: np.ndarray,
) -> tuple[float, float, float]:
    wgt = np.asarray(weight, np.float64)
    wsum = float(wgt.sum()) + 1e-9
    centered_template = np.asarray(template, np.float64)
    centered_template = (
        centered_template
        - float((centered_template * wgt).sum()) / wsum
    )
    weighted_template = centered_template * wgt
    th, tw = template.shape
    n_y = window.shape[0] - th + 1
    n_x = window.shape[1] - tw + 1
    template_norm = np.sqrt(
        (centered_template * weighted_template).sum()) + 1e-9
    patches = np.lib.stride_tricks.sliding_window_view(
        np.asarray(window, np.float64), (th, tw))
    means = np.einsum(
        "ijab,ab->ij", patches, wgt, optimize=True) / wsum
    centered = patches - means[..., None, None]
    numerator = np.einsum(
        "ijab,ab->ij", centered, weighted_template, optimize=True)
    norm = np.sqrt(np.einsum(
        "ijab,ijab,ab->ij", centered, centered, wgt, optimize=True))
    corr = numerator / (norm * template_norm + 1e-9)
    iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)

    def parabola(values: np.ndarray, index: int) -> float:
        if 0 < index < values.size - 1:
            left, center, right = values[index - 1:index + 2]
            denominator = left - 2.0 * center + right
            if abs(float(denominator)) > 1e-12:
                return float(np.clip(
                    (left - right) / (2.0 * denominator), -0.5, 0.5))
        return 0.0

    sy = parabola(corr[:, ix], iy)
    sx = parabola(corr[iy, :], ix)
    return (
        iy + sy - (n_y - 1) / 2.0,
        ix + sx - (n_x - 1) / 2.0,
        float(corr[iy, ix]),
    )


def rectified_ncc(
    planes: Planes,
    affine: Affine,
    cell_dots: int,
    centre_local_yx: tuple[int, int],
    bits: np.ndarray,
    weights: np.ndarray,
    plane: int,
) -> tuple[np.ndarray, float] | None:
    block = int(bits.shape[0])
    cell_px = RECTIFIED_PX_PER_DOT * cell_dots
    max_shift = max(2, round(ANCHOR_MAX_SHIFT_PX * cell_px / 6.0))
    template_size = block * cell_px
    window_size = template_size + 2 * max_shift
    half = block / 2.0
    axis = np.arange(window_size, dtype=np.float64)
    local_y = (
        float(centre_local_yx[0]) - half
        + (axis[:, None] - max_shift + 0.5) / cell_px
    )
    local_x = (
        float(centre_local_yx[1]) - half
        + (axis[None, :] - max_shift + 0.5) / cell_px
    )
    local_y, local_x = np.broadcast_arrays(local_y, local_x)
    local_points = np.stack(
        (local_y.ravel(), local_x.ravel()), axis=1)
    scan = pose_points(affine, local_points)
    y0, x0, rgb = native_crop(planes, scan, 2)
    crop_points = scan - np.asarray((y0, x0), np.float64)
    if (np.any(crop_points[:, 0] < 0.0)
            or np.any(crop_points[:, 1] < 0.0)
            or np.any(crop_points[:, 0] > rgb.shape[0] - 1)
            or np.any(crop_points[:, 1] > rgb.shape[1] - 1)):
        return None
    window = ndimage.map_coordinates(
        rgb[..., plane], crop_points.T,
        order=1, mode="nearest", output=np.float64,
    ).reshape(window_size, window_size)
    template = np.kron(
        1.0 - bits.astype(np.float64),
        np.ones((cell_px, cell_px), np.float64))
    pixel_weights = np.kron(
        weights, np.ones((cell_px, cell_px), np.float64))
    dy, dx, quality = xcorr_offset_ncc(window, template, pixel_weights)
    offset_dots_xy = np.asarray(
        (dx / RECTIFIED_PX_PER_DOT, dy / RECTIFIED_PX_PER_DOT),
        np.float64)
    return offset_dots_xy, quality


def measure_anchor(
    planes: Planes,
    rows: WindowRows,
    neighbor_indices: np.ndarray,
    row_index: int,
    plane: int,
    detected: np.ndarray,
    confident: np.ndarray,
    affine: Affine,
    cell_dots: int,
) -> tuple[np.ndarray, float] | None:
    local = np.asarray(rows.local_cells_yx, np.int64)
    center = local[row_index]
    indices = neighbor_indices[row_index]
    if np.any(indices < 0):
        return None
    bits = detected[indices, plane].reshape(3, 3).copy()
    weights = np.where(
        confident[indices, plane].reshape(3, 3), 1.0, 0.05)
    bits[1, 1] = 1
    weights[1, 1] = 1.0
    if bits.min() == bits.max():
        return None
    measured = rectified_ncc(
        planes, affine, cell_dots,
        (int(center[0]), int(center[1])), bits, weights, plane)
    if measured is None or measured[1] < ANCHOR_MIN_Q:
        return None
    return measured


def _select_candidates(
    candidates: dict[int, dict[tuple[int, int, int], tuple[int, int]]],
) -> tuple[tuple[tuple[int, int, int], int, int, int], ...]:
    selected: list[tuple[tuple[int, int, int], int, int, int]] = []
    for bucket in (0, 1, 2):
        ordered = tuple(sorted(candidates[bucket].items()))
        if len(ordered) > ANCHOR_BUDGET_PER_KIND:
            indices = (
                np.arange(ANCHOR_BUDGET_PER_KIND, dtype=np.int64)
                * len(ordered)
                // ANCHOR_BUDGET_PER_KIND
            )
            ordered = tuple(ordered[int(index)] for index in indices)
        selected.extend(
            (key, window_index, row_index, bucket)
            for key, (window_index, row_index) in ordered)
    return tuple(selected)


def _fit_component(
    page_y_fraction: np.ndarray,
    offsets: np.ndarray,
    quality: np.ndarray,
) -> tuple[float, float, int]:
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
        coefficients, *_rest = np.linalg.lstsq(
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
    y_fraction = np.asarray(page_y_fraction, np.float64)
    offsets = np.asarray(observed_offsets_xy, np.float64)
    q = np.asarray(quality, np.float64)
    x_intercept, x_slope, n_x = _fit_component(
        y_fraction, offsets[:, 0], q)
    y_intercept, y_slope, n_y = _fit_component(
        y_fraction, offsets[:, 1], q)
    return PlaneResidual(
        intercept_xy=(x_intercept, y_intercept),
        slope_xy=(x_slope, y_slope),
        n_anchors=min(n_x, n_y),
    )


def residual_offsets(residual: PlaneResidual,
                     page_y_fraction: np.ndarray) -> np.ndarray:
    return (
        np.asarray(residual.intercept_xy)
        + np.asarray(page_y_fraction, np.float64)[..., None]
        * np.asarray(residual.slope_xy)
    )


def fit_registration(
    planes: Planes,
    rows: tuple[WindowRows, ...],
    neighbor_indices: tuple[np.ndarray, ...],
    affines: tuple[Affine, ...],
    base_features: tuple[np.ndarray, ...],
    cell_dots: int,
    cells_y: int,
) -> tuple[PlaneResidual, PlaneResidual, PlaneResidual]:
    all_features = np.concatenate(base_features)
    blind_bits = np.empty(all_features.shape, np.bool_)
    blind_llr = np.empty(all_features.shape, np.float64)
    for plane in range(3):
        bits, llr = blind_component_bits(all_features[:, plane])
        blind_bits[:, plane] = bits.astype(bool)
        blind_llr[:, plane] = llr
    stops = np.cumsum([row.shape[0] for row in base_features])
    starts = np.concatenate((np.asarray([0]), stops[:-1]))
    prepared: list[tuple[np.ndarray, np.ndarray]] = []
    for window, start, stop in zip(rows, starts, stops):
        detected = blind_bits[int(start):int(stop)].copy()
        confident = (
            np.abs(blind_llr[int(start):int(stop)])
            >= BLIND_CONFIDENT_LLR
        )
        detected[window.known_component_mask] = (
            window.known_component_bits[
                window.known_component_mask].astype(bool))
        confident[window.known_component_mask] = True
        prepared.append((detected, confident))
    residuals: list[PlaneResidual] = []
    for plane in range(3):
        candidates: dict[
            int, dict[tuple[int, int, int], tuple[int, int]]
        ] = {0: {}, 1: {}, 2: {}}
        for window_index, (window, (_detected, _confident)) in enumerate(
                zip(rows, prepared)):
            search = site_parity(
                window.page_cells_yx[:, 0],
                window.page_cells_yx[:, 1]) == 0
            known_ink = (
                window.known_component_mask[:, plane]
                & window.known_component_bits[:, plane].astype(bool)
                & search
            )
            for row_index in np.flatnonzero(known_ink):
                cell = window.page_cells_yx[row_index]
                key = (window.page, int(cell[0]), int(cell[1]))
                furniture_kind = int(window.furniture_kind[row_index])
                bucket = (
                    furniture_kind if furniture_kind in (0, 1) else 2)
                candidates[bucket].setdefault(
                    key, (window_index, int(row_index)))
        anchors: dict[tuple[int, int, int], tuple[np.ndarray, float]] = {}
        for key, window_index, row_index, _bucket in (
                _select_candidates(candidates)):
            window = rows[window_index]
            detected, confident = prepared[window_index]
            measured = measure_anchor(
                planes, window, neighbor_indices[window_index],
                row_index, plane, detected, confident,
                affines[window_index], cell_dots)
            if measured is None:
                continue
            anchors[key] = measured
        if anchors:
            keys = sorted(anchors)
            y_fraction = np.asarray(
                [key[1] / cells_y for key in keys], np.float64)
            offsets = np.asarray(
                [anchors[key][0] for key in keys], np.float64)
            quality = np.asarray(
                [anchors[key][1] for key in keys], np.float64)
        else:
            y_fraction = np.zeros(0, np.float64)
            offsets = np.zeros((0, 2), np.float64)
            quality = np.zeros(0, np.float64)
        residuals.append(
            fit_plane_residual(y_fraction, offsets, quality))
    return residuals[0], residuals[1], residuals[2]


def features_with_page_fraction(
    planes: Planes,
    rows: WindowRows,
    affine: Affine,
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual],
    cell_dots: int,
    cells_y: int,
    pitch_px: float,
    divisor: float,
    offsets_override: tuple[np.ndarray | None, np.ndarray | None,
                            np.ndarray | None] | None = None,
) -> np.ndarray | None:
    page_y_fraction = (
        rows.page_cells_yx[:, 0].astype(np.float64) / cells_y)
    shape = planes[0].shape
    linear = pose_linear(affine)
    points_by_plane: list[np.ndarray] = []
    for plane, residual in enumerate(residuals):
        override = (
            None if offsets_override is None else offsets_override[plane])
        offset_dots_xy = (
            residual_offsets(residual, page_y_fraction)
            if override is None
            else np.asarray(override, np.float64))
        points = shifted_points(rows.scan_points_yx, linear,
                                offset_dots_xy / cell_dots)
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

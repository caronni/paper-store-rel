"""Blind page registration and strict geometry sampling.

This module is intentionally local to :mod:`holo.characterize`.  It uses the
scratch sheet's chiral 1..4-satellite corner marks for an eight-way
rotation/mirror registration, then treats that affine as a *locator*, not as
proof that fine payload geometry is locally solved.

All affine matrices map layout ``(x, y)`` coordinates at 600 source dots per
inch to scan-pixel ``(x, y)`` coordinates.  Sampling refuses any point outside
the captured raster before interpolation; no edge-clamping mode is used.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import ndimage
from scipy.ndimage import map_coordinates

from .diagnostics import density as plane_density
from .raster import RasterSource


LAYOUT_DPI = 600.0
CORNER_MARK_DOTS = 123
CORNER_CENTER_DOT = 61
CORNER_SATELLITE_DOTS = 8
CORNER_SATELLITE_DISTANCES = (18, 30, 42, 54)


class GeometryError(ValueError):
    """Base class for characterization geometry refusals."""


class OutOfRasterError(GeometryError):
    """Raised when any requested evidence point is outside the capture."""


def _component_center(projection: np.ndarray) -> float:
    """Subpixel centre of a flat-topped maximum in index coordinates."""

    values = np.asarray(projection, dtype=np.float64)
    peak = float(np.max(values))
    floor = float(np.percentile(values, 50))
    weight = np.clip(values - floor, 0.0, None)
    strong = values >= floor + 0.80 * max(peak - floor, 0.0)
    weight = np.where(strong, weight, 0.0)
    total = float(weight.sum())
    if total <= 0.0:
        return float(np.argmax(values))
    return float(np.dot(np.arange(values.size), weight) / total)


def detect_chiral_corners(
    grey: np.ndarray,
    *,
    target_dpi: float = 300.0,
    dpi_x: float | None = None,
    dpi_y: float | None = None,
    layout_dpi: float = LAYOUT_DPI,
) -> list[dict[str, Any]]:
    """Blindly find the 1..4-satellite chiral corner marks.

    The returned position is the centre of the long cross in thumbnail pixel
    coordinates.  At most one (the strongest) candidate is returned for each
    satellite count.  No assumed page orientation or corner position enters
    detection.
    """

    image = np.asarray(grey, dtype=np.float32)
    if image.ndim != 2 or image.size == 0:
        raise GeometryError("corner detection requires a nonempty 2-D image")
    dx = float(target_dpi if dpi_x is None else dpi_x)
    dy = float(target_dpi if dpi_y is None else dpi_y)
    if dx <= 0 or dy <= 0 or layout_dpi <= 0:
        raise GeometryError("corner detection DPI must be positive")

    # Use only a bounded stride for threshold estimation.  The threshold is a
    # reflectance separator, not a numerical channel normalization.
    stride_y = max(1, image.shape[0] // 2048)
    stride_x = max(1, image.shape[1] // 2048)
    sample = image[::stride_y, ::stride_x]
    # The furniture occupies far below 0.5% of an otherwise blank synthetic
    # or severely faded page.  A low percentile can therefore equal paper
    # white and make a perfectly valid sparse fixture look contrast-free.
    # The full-plane minimum is a scalar reduction (not a derived raster);
    # isolated dark dust merely creates tiny components rejected below.
    black = float(np.min(image))
    white = float(np.percentile(sample, 90.0))
    span = white - black
    if not math.isfinite(span) or span < 1.0 / 255.0:
        raise GeometryError("scan has insufficient contrast for corner detection")
    threshold = white - 0.42 * span
    labels, n_labels = ndimage.label(image < threshold)
    if n_labels == 0:
        return []
    slices = ndimage.find_objects(labels)

    components: list[dict[str, Any]] = []
    for label_index, sl in enumerate(slices, start=1):
        if sl is None:
            continue
        height = int(sl[0].stop - sl[0].start)
        width = int(sl[1].stop - sl[1].start)
        area = int(np.count_nonzero(labels[sl] == label_index))
        if area == 0:
            continue
        yy, xx = np.nonzero(labels[sl] == label_index)
        components.append(
            {
                "label": label_index,
                "slice": sl,
                "height": height,
                "width": width,
                "area": area,
                "cy": float(sl[0].start + yy.mean()),
                "cx": float(sl[1].start + xx.mean()),
            }
        )

    nominal_h = CORNER_MARK_DOTS * dy / layout_dpi
    nominal_w = CORNER_MARK_DOTS * dx / layout_dpi
    satellite_h = CORNER_SATELLITE_DOTS * dy / layout_dpi
    satellite_w = CORNER_SATELLITE_DOTS * dx / layout_dpi
    small_components = [
        item
        for item in components
        if (
            max(1.0, 0.35 * satellite_h)
            <= item["height"]
            <= max(3.0, 2.25 * satellite_h)
            and max(1.0, 0.35 * satellite_w)
            <= item["width"]
            <= max(3.0, 2.25 * satellite_w)
            and item["area"] >= 2
        )
    ]

    found: dict[int, dict[str, Any]] = {}
    for component in components:
        height, width = component["height"], component["width"]
        if not (
            0.58 * nominal_h <= height <= 1.55 * nominal_h
            and 0.58 * nominal_w <= width <= 1.55 * nominal_w
        ):
            continue
        sl = component["slice"]
        mask = labels[sl] == component["label"]
        fill = float(mask.mean())
        if not 0.012 <= fill <= 0.24:
            continue
        row_projection = mask.sum(axis=1).astype(np.float64)
        col_projection = mask.sum(axis=0).astype(np.float64)
        local_y = _component_center(row_projection)
        local_x = _component_center(col_projection)
        band_y = max(1.5, 4.0 * dy / layout_dpi)
        band_x = max(1.5, 4.0 * dx / layout_dpi)
        yy, xx = np.nonzero(mask)
        crossness = float(
            np.mean(
                (np.abs(yy - local_y) <= band_y)
                | (np.abs(xx - local_x) <= band_x)
            )
        )
        if crossness < 0.58:
            continue
        cy = float(sl[0].start + local_y)
        cx = float(sl[1].start + local_x)
        # The cross itself is an absolute-scale witness.  Use its measured
        # span to seed satellite spacing so corner identity still works on a
        # materially scaled or anisotropically sampled fixture.
        #
        # W8a (e031): seed from the LONGER axis, not per-axis.  The mark is
        # square by construction (CORNER_MARK_DOTS both ways) and nominal_w /
        # nominal_h already carry the per-axis sampling DPI, so a faithful
        # capture yields the same ratio on both axes even when sampling is
        # anisotropic — a per-axis disagreement is therefore truncation, not
        # anisotropy.  Thresholding can only ever SHORTEN a measured arm, so
        # the longer axis is the better estimate of the true span.  Measured
        # on the e031 B/W sheet: a threshold-clipped arm gave width/height
        # 36/60 against a nominal 61.5, collapsing the x scale to 0.585,
        # shrinking the satellite search radius with it and missing the only
        # satellite by 5.24 against a 2.25 tolerance — the corner was dropped
        # from a physically perfect print.  Seeded from max() the same corner
        # matches at 0.15.
        local_scale = max(float(width) / max(nominal_w, 1e-9),
                          float(height) / max(nominal_h, 1e-9))
        local_scale_x = local_scale
        local_scale_y = local_scale

        best_quadrant: tuple[int, int] | None = None
        best_matches: list[tuple[dict[str, Any], float]] = []
        for sign_y in (-1, 1):
            for sign_x in (-1, 1):
                matches: list[tuple[dict[str, Any], float]] = []
                used: set[int] = set()
                for distance in CORNER_SATELLITE_DISTANCES:
                    expected_y = (
                        cy
                        + sign_y
                        * distance
                        * dy
                        / layout_dpi
                        * local_scale_y
                    )
                    expected_x = (
                        cx
                        + sign_x
                        * distance
                        * dx
                        / layout_dpi
                        * local_scale_x
                    )
                    tolerance = max(
                        2.25,
                        0.32
                        * math.hypot(
                            12.0 * dx / layout_dpi * local_scale_x,
                            12.0 * dy / layout_dpi * local_scale_y,
                        ),
                    )
                    options = []
                    for item in small_components:
                        if item["label"] == component["label"]:
                            continue
                        if int(item["label"]) in used:
                            continue
                        error = math.hypot(
                            (item["cx"] - expected_x)
                            / max(dx / target_dpi * local_scale_x, 1e-9),
                            (item["cy"] - expected_y)
                            / max(dy / target_dpi * local_scale_y, 1e-9),
                        )
                        options.append((error, item))
                    if not options:
                        break
                    error, item = min(options, key=lambda pair: pair[0])
                    if error > tolerance:
                        break
                    used.add(int(item["label"]))
                    matches.append((item, float(error)))
                if (
                    len(matches) > len(best_matches)
                    or (
                        len(matches) == len(best_matches)
                        and matches
                        and sum(error for _item, error in matches)
                        < sum(error for _item, error in best_matches)
                    )
                ):
                    best_matches = matches
                    best_quadrant = (sign_y, sign_x)

        satellite_count = len(best_matches)
        if not 1 <= satellite_count <= 4 or best_quadrant is None:
            continue
        y0 = max(0, int(math.floor(cy - band_y)))
        y1 = min(image.shape[0], int(math.ceil(cy + band_y + 1)))
        x0 = max(0, int(math.floor(cx - band_x)))
        x1 = min(image.shape[1], int(math.ceil(cx + band_x + 1)))
        line_mean = float(np.mean(image[y0:y1, x0:x1]))
        local_contrast = max(0.0, white - line_mean)
        satellite_error = sum(error for _item, error in best_matches)
        score = (
            crossness
            + min(local_contrast / max(span, 1e-9), 1.0)
            - 0.01 * satellite_error
        )
        candidate = {
            "satellites": satellite_count,
            "n_sat": satellite_count,
            "x_thumb": cx,
            "y_thumb": cy,
            "crossness": crossness,
            "contrast": local_contrast,
            "score": float(score),
            "inward": [int(best_quadrant[0]), int(best_quadrant[1])],
            "bbox_thumb": [
                int(sl[1].start),
                int(sl[0].start),
                int(width),
                int(height),
            ],
            "satellite_centres_thumb": [
                [float(item["cx"]), float(item["cy"])]
                for item, _error in best_matches
            ],
        }
        previous = found.get(satellite_count)
        if previous is None or candidate["score"] > previous["score"]:
            found[satellite_count] = candidate
    return [found[key] for key in sorted(found)]


def _coerce_affine(coef: Any) -> np.ndarray:
    if hasattr(coef, "coef"):
        coef = getattr(coef, "coef")
    array = np.asarray(coef, dtype=np.float64)
    if array.shape == (6,):
        array = array.reshape(2, 3)
    if array.shape != (2, 3) or not np.all(np.isfinite(array)):
        raise GeometryError("affine must be a finite 2x3 matrix")
    return array


def fit_affine(
    layout_xy: np.ndarray,
    scan_xy: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Least-squares layout-to-scan affine and pointwise RMS residual."""

    layout = np.asarray(layout_xy, dtype=np.float64)
    scan = np.asarray(scan_xy, dtype=np.float64)
    if layout.ndim != 2 or layout.shape[1] != 2 or layout.shape != scan.shape:
        raise GeometryError("layout_xy and scan_xy must be matching (n, 2) arrays")
    if len(layout) < 3 or not np.all(np.isfinite(layout)) or not np.all(
        np.isfinite(scan)
    ):
        raise GeometryError("at least three finite affine correspondences are required")
    design = np.column_stack((layout, np.ones(len(layout), dtype=np.float64)))
    if np.linalg.matrix_rank(design) < 3:
        raise GeometryError("layout affine correspondences are collinear")
    solution, *_ = np.linalg.lstsq(design, scan, rcond=None)
    coef = solution.T
    prediction = design @ solution
    residual = prediction - scan
    rms = float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))
    return coef, rms


def apply_affine(
    coef: Any,
    x: np.ndarray | float,
    y: np.ndarray | float | None = None,
) -> tuple[np.ndarray, np.ndarray] | np.ndarray:
    """Apply a layout-to-scan affine.

    With both ``x`` and ``y``, returns ``(scan_x, scan_y)``.  With ``y=None``,
    ``x`` must be an ``(..., 2)`` point array and the result has the same
    point-array shape.
    """

    matrix = _coerce_affine(coef)
    if y is None:
        points = np.asarray(x, dtype=np.float64)
        if points.shape[-1:] != (2,):
            raise GeometryError("single-argument affine input must end in two")
        flat = points.reshape(-1, 2)
        result = flat @ matrix[:, :2].T + matrix[:, 2]
        return result.reshape(points.shape)
    xx, yy = np.broadcast_arrays(
        np.asarray(x, dtype=np.float64),
        np.asarray(y, dtype=np.float64),
    )
    scan_x = matrix[0, 0] * xx + matrix[0, 1] * yy + matrix[0, 2]
    scan_y = matrix[1, 0] * xx + matrix[1, 1] * yy + matrix[1, 2]
    return scan_x, scan_y


def affine_metrics(
    coef: Any,
    *,
    scan_dpi_x: float,
    scan_dpi_y: float,
    layout_dpi: float = LAYOUT_DPI,
) -> dict[str, Any]:
    """Physical scale, orientation, reflection, and shear of an affine."""

    if scan_dpi_x <= 0 or scan_dpi_y <= 0 or layout_dpi <= 0:
        raise GeometryError("DPI values must be positive")
    matrix = _coerce_affine(coef)
    linear = matrix[:, :2]
    samples_x = float(np.linalg.norm(linear[:, 0]))
    samples_y = float(np.linalg.norm(linear[:, 1]))

    # Express scan displacement in layout-dot physical units before
    # decomposing.  This avoids inventing rotation/shear when scanner x/y DPI
    # differ.
    physical = np.diag(
        [layout_dpi / float(scan_dpi_x), layout_dpi / float(scan_dpi_y)]
    ) @ linear
    column_x, column_y = physical[:, 0], physical[:, 1]
    scale_x = float(np.linalg.norm(column_x))
    scale_y = float(np.linalg.norm(column_y))
    determinant = float(np.linalg.det(physical))
    mirrored = determinant < 0.0
    rotation = math.degrees(math.atan2(column_x[1], column_x[0]))
    quadrant = int(round(rotation / 90.0)) % 4
    dot = float(np.dot(column_x, column_y))
    denom = max(scale_x * scale_y, 1e-15)
    axis_angle = math.degrees(math.acos(float(np.clip(dot / denom, -1.0, 1.0))))
    shear = axis_angle - 90.0
    orientation = f"{'mirror-' if mirrored else ''}r{quadrant * 90}"
    return {
        "px_per_layout_dot_x": samples_x,
        "px_per_layout_dot_y": samples_y,
        "nominal_px_per_layout_dot_x": float(scan_dpi_x) / layout_dpi,
        "nominal_px_per_layout_dot_y": float(scan_dpi_y) / layout_dpi,
        "scale_ratio_x": scale_x,
        "scale_ratio_y": scale_y,
        "rotation_deg": float(rotation),
        "rotation_quadrants": quadrant,
        "rotation_right_angle_deg": quadrant * 90,
        "mirrored": bool(mirrored),
        "orientation": orientation,
        "axis_angle_deg": axis_angle,
        "shear_from_orthogonal_deg": shear,
        "determinant": determinant,
    }


def _layout_corner_centres(
    layout: Sequence[Mapping[str, Any]],
) -> dict[int, tuple[float, float]]:
    """Chiral corner centres from canonical infrastructure records."""
    result: dict[int, tuple[float, float]] = {}
    for record in layout:
        if record["kind"] != "corner_mark":
            continue
        result[int(record["satellites"])] = (
            float(record["cx_layout_dots"]),
            float(record["cy_layout_dots"]),
        )
    if len(result) < 3:
        raise GeometryError(
            f"layout contains only {len(result)} identified chiral corners"
        )
    return result


def register_blind(
    source: RasterSource | str | np.ndarray,
    scan_dpi_x: float,
    scan_dpi_y: float,
    *,
    corner_layout: Any,
    target_dpi: float = 300.0,
    min_corners: int = 3,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Blind corner registration supporting all rotations and mirrors."""

    if not isinstance(source, RasterSource):
        source = RasterSource(source)
    if scan_dpi_x <= 0 or scan_dpi_y <= 0:
        raise GeometryError("true scanner DPI must be positive")
    if min_corners < 3 or min_corners > 4:
        raise GeometryError("min_corners must be 3 or 4")
    grey, factor_x, factor_y = source.thumbnail_grey(
        scan_dpi_x, scan_dpi_y, target_dpi
    )
    effective_x = float(scan_dpi_x) / factor_x
    effective_y = float(scan_dpi_y) / factor_y
    detected_rows = detect_chiral_corners(
        grey,
        target_dpi=target_dpi,
        dpi_x=effective_x,
        dpi_y=effective_y,
    )
    detected = {int(row["satellites"]): row for row in detected_rows}
    expected = _layout_corner_centres(corner_layout)
    common = sorted(set(expected) & set(detected))
    if len(common) < min_corners:
        raise GeometryError(
            f"found chiral corners {sorted(detected)}; "
            f"need at least {min_corners}"
        )
    layout_points = np.asarray([expected[key] for key in common], np.float64)
    scan_points = np.asarray(
        [
            (
                (float(detected[key]["x_thumb"]) + 0.5) * factor_x - 0.5,
                (float(detected[key]["y_thumb"]) + 0.5) * factor_y - 0.5,
            )
            for key in common
        ],
        np.float64,
    )
    coef, rms_px = fit_affine(layout_points, scan_points)
    predicted = np.asarray(apply_affine(coef, layout_points), np.float64)
    residual_scan = predicted - scan_points
    inverse_linear = np.linalg.inv(coef[:, :2])
    residual_layout = residual_scan @ inverse_linear.T
    residual_layout_norm = np.linalg.norm(residual_layout, axis=1)

    corners_found = []
    for index, key in enumerate(common):
        row = dict(detected[key])
        row.update(
            {
                "x_scan": float(scan_points[index, 0]),
                "y_scan": float(scan_points[index, 1]),
                "x_layout_dots": float(layout_points[index, 0]),
                "y_layout_dots": float(layout_points[index, 1]),
                "residual_scan_px": residual_scan[index].tolist(),
                "residual_layout_dots": residual_layout[index].tolist(),
            }
        )
        corners_found.append(row)
    geometry: dict[str, Any] = {
        "corners_found": corners_found,
        "corner_satellite_counts": common,
        "corners_missing": sorted(set(expected) - set(common)),
        "affine_layout_to_scan": coef.tolist(),
        "corner_fit_rms_px": rms_px,
        "corner_fit_rms_layout_dots": float(
            np.sqrt(np.mean(residual_layout_norm**2))
        ),
        "thumbnail": {
            "shape": list(grey.shape),
            "factor_x": factor_x,
            "factor_y": factor_y,
            "effective_dpi_x": effective_x,
            "effective_dpi_y": effective_y,
        },
    }
    geometry.update(
        affine_metrics(
            coef,
            scan_dpi_x=scan_dpi_x,
            scan_dpi_y=scan_dpi_y,
        )
    )
    return coef, geometry


def sample_layout_points(
    source: RasterSource,
    coef: Any,
    x_layout: np.ndarray | float,
    y_layout: np.ndarray | float,
    *,
    max_crop_pixels: int = 3_000_000,
    max_points_per_chunk: int = 65_536,
) -> np.ndarray:
    """Bilinearly sample arbitrary layout points in bounded scan crops.

    Visibility is checked for the entire requested population before the
    first crop is read.  One out-of-frame point refuses the call; it cannot
    acquire a plausible value from an interpolator's nearest edge.
    """

    if max_crop_pixels <= 0 or max_points_per_chunk <= 0:
        raise GeometryError("sampling chunk limits must be positive")
    xx, yy = np.broadcast_arrays(
        np.asarray(x_layout, dtype=np.float64),
        np.asarray(y_layout, dtype=np.float64),
    )
    shape = xx.shape
    if xx.size == 0:
        return np.empty(shape + (3,), dtype=np.float32)
    scan_x, scan_y = apply_affine(coef, xx.ravel(), yy.ravel())
    scan_x = np.asarray(scan_x, dtype=np.float64)
    scan_y = np.asarray(scan_y, dtype=np.float64)
    visible = source.points_visible(scan_x, scan_y)
    if not np.all(visible):
        bad = np.flatnonzero(~visible)
        first = int(bad[0])
        raise OutOfRasterError(
            f"{bad.size} of {visible.size} registered sample points lie "
            f"outside raster {source.spatial_shape}; first is "
            f"({scan_x[first]:.3f}, {scan_y[first]:.3f})"
        )

    limit = min(int(max_crop_pixels), source.max_crop_pixels)
    order = np.lexsort((scan_x, scan_y))
    output = np.empty((scan_x.size, 3), dtype=np.float32)
    cursor = 0
    while cursor < order.size:
        selected = [int(order[cursor])]
        x_min = x_max = float(scan_x[selected[0]])
        y_min = y_max = float(scan_y[selected[0]])
        cursor += 1
        while cursor < order.size and len(selected) < max_points_per_chunk:
            index = int(order[cursor])
            next_x_min = min(x_min, float(scan_x[index]))
            next_x_max = max(x_max, float(scan_x[index]))
            next_y_min = min(y_min, float(scan_y[index]))
            next_y_max = max(y_max, float(scan_y[index]))
            crop_x0 = max(0, int(math.floor(next_x_min)) - 1)
            crop_x1 = min(source.width, int(math.ceil(next_x_max)) + 2)
            crop_y0 = max(0, int(math.floor(next_y_min)) - 1)
            crop_y1 = min(source.height, int(math.ceil(next_y_max)) + 2)
            area = (crop_x1 - crop_x0) * (crop_y1 - crop_y0)
            if area > limit:
                break
            selected.append(index)
            x_min, x_max = next_x_min, next_x_max
            y_min, y_max = next_y_min, next_y_max
            cursor += 1

        indices = np.asarray(selected, dtype=np.int64)
        crop_x0 = max(0, int(math.floor(x_min)) - 1)
        crop_x1 = min(source.width, int(math.ceil(x_max)) + 2)
        crop_y0 = max(0, int(math.floor(y_min)) - 1)
        crop_y1 = min(source.height, int(math.ceil(y_max)) + 2)
        area = (crop_x1 - crop_x0) * (crop_y1 - crop_y0)
        if area > limit:
            # A one-point crop should never reach this branch, but make the
            # bounded-memory contract explicit if limits are pathological.
            raise GeometryError(
                f"minimum sampling crop needs {area} pixels; limit is {limit}"
            )
        crop = source.crop_rgb(
            crop_y0,
            crop_y1,
            crop_x0,
            crop_x1,
            max_pixels=limit,
        )
        coordinates = np.stack(
            (scan_y[indices] - crop_y0, scan_x[indices] - crop_x0)
        )
        for channel in range(3):
            output[indices, channel] = map_coordinates(
                crop[..., channel],
                coordinates,
                order=1,
                mode="constant",
                cval=np.nan,
                prefilter=False,
            )
        if not np.all(np.isfinite(output[indices])):
            raise OutOfRasterError(
                "interpolation touched outside a supposedly visible crop"
            )
    return output.reshape(shape + (3,))


def _rect_from_record(
    record: Mapping[str, Any],
) -> tuple[float, float, float, float]:
    return (
        float(record["x_layout_dots"]),
        float(record["y_layout_dots"]),
        float(record["w_layout_dots"]),
        float(record["h_layout_dots"]),
    )


def layout_footprint_visibility(
    source: RasterSource,
    coef: Any,
    record: Any,
) -> tuple[bool, float]:
    """Visibility of an affine-mapped layout rectangle's full footprint."""

    x0, y0, width, height = _rect_from_record(record)
    if width <= 0 or height <= 0:
        raise GeometryError("layout footprint dimensions must be positive")
    layout_corners = np.asarray(
        [
            [x0, y0],
            [x0 + width, y0],
            [x0 + width, y0 + height],
            [x0, y0 + height],
        ],
        dtype=np.float64,
    )
    scan_corners = np.asarray(apply_affine(coef, layout_corners))
    return source.footprint_visibility(scan_corners)


def _plus_records(
    container: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [row for row in container if row["kind"] == "geometry_plus"]


def plus_residuals(
    source: RasterSource,
    coef: Any,
    plus_geometry: Any,
    *,
    search_layout_dots: float = 12.0,
    step_layout_dots: float = 0.25,
    minimum_density_contrast: float = 0.02,
) -> dict[str, Any]:
    """Measure internal plus-centre residuals after the corner affine."""

    if search_layout_dots <= 0 or step_layout_dots <= 0:
        raise GeometryError("plus search span and step must be positive")
    records = _plus_records(plus_geometry)
    offsets = np.arange(
        -search_layout_dots,
        search_layout_dots + 0.5 * step_layout_dots,
        step_layout_dots,
        dtype=np.float64,
    )
    rows: list[dict[str, Any]] = []
    for sequence, record in enumerate(records):
        x = float(record["cx_layout_dots"])
        y = float(record["cy_layout_dots"])
        grid_x, grid_y = np.meshgrid(x + offsets, y + offsets)
        try:
            rgb = sample_layout_points(source, coef, grid_x, grid_y)
        except OutOfRasterError:
            rows.append(
                {
                    "index": int(record["index"]),
                    "ok": False,
                    "status": "unobservable",
                    "x_layout_dots": x,
                    "y_layout_dots": y,
                }
            )
            continue
        density = plane_density(rgb, "K")
        score_x = density.mean(axis=0)
        score_y = density.mean(axis=1)
        peak_x = int(np.argmax(score_x))
        peak_y = int(np.argmax(score_y))
        contrast_x = float(score_x[peak_x] - np.median(score_x))
        contrast_y = float(score_y[peak_y] - np.median(score_y))
        at_boundary = peak_x in (0, len(offsets) - 1) or peak_y in (
            0,
            len(offsets) - 1,
        )
        ok = (
            not at_boundary
            and contrast_x >= minimum_density_contrast
            and contrast_y >= minimum_density_contrast
        )
        row: dict[str, Any] = {
            "index": int(record["index"]),
            "ok": bool(ok),
            "status": "ok" if ok else "unresolved",
            "x_layout_dots": x,
            "y_layout_dots": y,
            "density_contrast_x": contrast_x,
            "density_contrast_y": contrast_y,
        }
        if ok:
            # A printed three-dot bar has a deliberately flat-topped
            # projection.  Selecting the first argmax biases its centre by
            # roughly half the bar width; use the strong-peak centroid.
            refined_x = _component_center(score_x)
            refined_y = _component_center(score_y)
            dx = -search_layout_dots + refined_x * step_layout_dots
            dy = -search_layout_dots + refined_y * step_layout_dots
            row.update(
                {
                    "dx_layout_dots": float(dx),
                    "dy_layout_dots": float(dy),
                    "residual_layout_dots": float(math.hypot(dx, dy)),
                }
            )
        rows.append(row)
    valid = [row for row in rows if row.get("ok")]
    magnitudes = [float(row["residual_layout_dots"]) for row in valid]
    return {
        "marks": rows,
        "n_expected": len(records),
        "n_ok": len(valid),
        "residual_rms_layout_dots": (
            float(np.sqrt(np.mean(np.square(magnitudes))))
            if magnitudes
            else None
        ),
        "residual_max_layout_dots": max(magnitudes, default=None),
        "search_layout_dots": float(search_layout_dots),
        "step_layout_dots": float(step_layout_dots),
    }


PAPER_EDGE_SEARCH_MM = 3.0
PAPER_EDGE_BANDS = 9
PAPER_EDGE_MIN_PROMINENCE = 0.012


def measure_paper_edges(
    source: RasterSource,
    coef: Any,
    page_size_mm: tuple[float, float],
) -> dict[str, Any]:
    """Locate the PHYSICAL paper edges (shadow lines) around the layout
    frame, where the capture shows background (workplan W2e).

    Separates print-to-paper registration (offset varying along an edge =
    feed skew) from paper-on-platen placement.  Edges outside the raster
    or without background contrast degrade honestly to not-visible.
    Offsets are signed along the outward normal: positive = the paper
    edge lies beyond the layout frame edge.
    """

    dots_per_mm = LAYOUT_DPI / 25.4
    width_dots = float(page_size_mm[0]) * dots_per_mm
    height_dots = float(page_size_mm[1]) * dots_per_mm
    steps_mm = np.arange(
        -PAPER_EDGE_SEARCH_MM, PAPER_EDGE_SEARCH_MM + 0.025, 0.05
    )
    transverse_mm = np.linspace(-0.3, 0.3, 9)
    edges: dict[str, Any] = {}
    for edge in ("top", "bottom", "left", "right"):
        along = (
            width_dots if edge in {"top", "bottom"} else height_dots
        )
        positions = np.linspace(
            0.10 * along, 0.90 * along, PAPER_EDGE_BANDS
        )
        bands = []
        offsets = []
        for position in positions:
            outward = steps_mm * dots_per_mm
            across = transverse_mm * dots_per_mm
            if edge == "top":
                grid_x = position + across[None, :]
                grid_y = -outward[:, None] + 0.0 * across[None, :]
            elif edge == "bottom":
                grid_x = position + across[None, :]
                grid_y = height_dots + outward[:, None] + 0.0 * across
            elif edge == "left":
                grid_x = -outward[:, None] + 0.0 * across[None, :]
                grid_y = position + across[None, :]
            else:
                grid_x = width_dots + outward[:, None] + 0.0 * across
                grid_y = position + across[None, :]
            band: dict[str, Any] = {
                "position_mm": float(position / dots_per_mm),
            }
            mesh_x, mesh_y = np.broadcast_arrays(grid_x, grid_y)
            scan_x, scan_y = apply_affine(coef, mesh_x, mesh_y)
            valid = (
                (scan_x >= 0.0) & (scan_x <= source.width - 1.0)
                & (scan_y >= 0.0) & (scan_y <= source.height - 1.0)
            )
            row_valid = np.all(valid, axis=1)
            if float(np.mean(row_valid)) < 0.35:
                band.update({"visible": False,
                             "reason": "outside-raster"})
                bands.append(band)
                continue
            luma_rows = np.full(mesh_x.shape[0], np.nan, np.float64)
            try:
                rgb = sample_layout_points(
                    source, coef,
                    mesh_x[row_valid], mesh_y[row_valid],
                )
            except (OutOfRasterError, GeometryError, ValueError):
                band.update({"visible": False,
                             "reason": "outside-raster"})
                bands.append(band)
                continue
            luma = (
                0.2126 * rgb[..., 0]
                + 0.7152 * rgb[..., 1]
                + 0.0722 * rgb[..., 2]
            )
            luma_rows[row_valid] = np.mean(luma, axis=1)
            profile = luma_rows
            smooth = np.convolve(
                profile, np.ones(3) / 3.0, mode="same"
            )
            # The paper edge is a falling reflectance STEP along the
            # outward walk (platen background is often darker than the
            # edge's own shadow dip, so a plain minimum saturates at the
            # window boundary).  Score each interior position by the
            # inside-vs-outside mean difference over 1 mm shoulders.
            shoulder = max(2, int(round(1.0 / 0.05)) // 2)
            best_index = None
            best_step = 0.0
            for index in range(shoulder, len(smooth) - shoulder):
                inside = float(np.mean(smooth[index - shoulder:index]))
                outside = float(np.mean(
                    smooth[index + 1:index + 1 + shoulder]
                ))
                step_size = inside - outside
                if step_size > best_step:
                    best_step = step_size
                    best_index = index
            detected = bool(
                best_index is not None
                and best_step >= PAPER_EDGE_MIN_PROMINENCE
            )
            band.update({
                "visible": True,
                "detected": detected,
                "edge_step": best_step,
            })
            if detected:
                # The shoulder comparison is biased early when the dark
                # tail is asymmetric (shadow dip + background); refine to
                # the steepest falling gradient near the coarse position.
                lo = max(1, best_index - shoulder)
                hi = min(len(smooth) - 1, best_index + shoulder + 1)
                gradient = smooth[lo + 1:hi + 1] - smooth[lo - 1:hi - 1]
                finite = np.isfinite(gradient)
                if bool(np.any(finite)):
                    candidates = np.where(finite, gradient, np.inf)
                    edge_index = lo + int(np.argmin(candidates))
                else:
                    edge_index = best_index
                # A paper edge leads to BACKGROUND: everything beyond it
                # must stay darker than paper.  A bright edge-glow line
                # inside a flush-placed page produces a step whose tail
                # returns to paper level — refuse it (e028 bottom-left).
                inside_level = float(np.nanmedian(smooth[:max(
                    2, edge_index - 2
                )]))
                tail = smooth[edge_index + 6:]
                tail = tail[np.isfinite(tail)]
                # 1.5x the prominence floor: gradual frame-end vignette
                # darkens by about one floor and must not qualify.
                if (
                    tail.size < 4
                    or float(np.mean(tail))
                    > inside_level - 1.5 * PAPER_EDGE_MIN_PROMINENCE
                ):
                    band["detected"] = False
                    band["reason"] = "no-sustained-background-beyond-edge"
                    bands.append(band)
                    continue
                offset = float(steps_mm[edge_index])
                band["offset_mm"] = offset
                offsets.append((float(position / dots_per_mm), offset))
            bands.append(band)
        record: dict[str, Any] = {
            "bands": bands,
            "n_detected": len(offsets),
            "status": (
                "detected" if len(offsets) >= 3
                else "not-visible" if not offsets
                else "sparse"
            ),
        }
        if offsets:
            values = np.asarray([row[1] for row in offsets])
            record["offset_mm_mean"] = float(np.mean(values))
            record["offset_mm_span"] = float(np.ptp(values))
            if len(offsets) >= 3:
                along_positions = np.asarray(
                    [row[0] for row in offsets]
                )
                design = np.stack(
                    (np.ones(len(offsets)), along_positions), axis=1
                )
                coefficients, *_ = np.linalg.lstsq(
                    design, values, rcond=None
                )
                record["tilt_deg"] = float(
                    math.degrees(math.atan(coefficients[1]))
                )
        edges[edge] = record
    return {
        "search_mm": PAPER_EDGE_SEARCH_MM,
        "offset_sign": (
            "positive = paper edge beyond the layout frame edge "
            "(outward normal)"
        ),
        "edges": edges,
    }


__all__ = [
    "CORNER_MARK_DOTS",
    "GeometryError",
    "LAYOUT_DPI",
    "OutOfRasterError",
    "affine_metrics",
    "apply_affine",
    "detect_chiral_corners",
    "fit_affine",
    "layout_footprint_visibility",
    "measure_paper_edges",
    "plus_residuals",
    "register_blind",
    "sample_layout_points",
]

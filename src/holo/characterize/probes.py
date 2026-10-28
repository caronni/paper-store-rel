"""Typed probe measurement: tones, geometry, rails, morphology."""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from .diagnostics import (
    luma709,
    blockiness,
    density,
    blockiness_comb,
    highpass_noise,
    level_occupancy,
    pattern_score,
    screen_fingerprint,
    slanted_edge_mtf50,
)
from .geometry import (
    GeometryError,
    OutOfRasterError,
    apply_affine,
    layout_footprint_visibility,
    sample_layout_points,
)
from .model import BASE_DPI
from .patterns import pattern_bits
from .raster import RasterSource
from .sampling import (
    PHASE_RAIL_CORRELATION_MIN,
    PHASE_RAIL_MIN_PERIODS_PER_SEGMENT,
    PHASE_RAIL_MIN_VALID_FRACTION,
    PHASE_RAIL_SEGMENT_TARGET_MM,
)


TICK_PAD_LAYOUT_DOTS = 10.0
TICK_SAMPLES_PER_DOT = 2
TICK_MIN_CONTRAST_DENSITY = 0.20
TICK_FULL_MIN_FRACTION = 0.85
TICK_ABSENT_MAX_FRACTION = 0.10


def _edge_tick_registration(
    source: RasterSource,
    affine: np.ndarray,
    probe: dict[str, Any],
) -> dict[str, Any]:
    """Grade one solid edge tick from its REGISTERED footprint.

    The retired verdict rule (solid_density_p05 vs paper) demanded the
    whole nominal window be ink and therefore measured window alignment,
    not ink (028.2: 1-3 dot print/affine displacement failed 12 of 16
    solidly printed ticks).  Here the 28-dot footprint is searched over a
    bounded translation and graded on registered ink coverage; partially
    printed ticks additionally yield a layout-referenced clip estimate.
    """

    width = float(probe["w_layout_dots"])
    height = float(probe["h_layout_dots"])
    x0 = float(probe["x_layout_dots"])
    y0 = float(probe["y_layout_dots"])
    step = 1.0 / TICK_SAMPLES_PER_DOT
    pads = {side: TICK_PAD_LAYOUT_DOTS
            for side in ("left", "right", "top", "bottom")}
    grid_x = np.arange(
        x0 - pads["left"] + step / 2.0,
        x0 + width + pads["right"],
        step,
    )
    grid_y = np.arange(
        y0 - pads["top"] + step / 2.0,
        y0 + height + pads["bottom"],
        step,
    )
    mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
    scan_x, scan_y = apply_affine(affine, mesh_x, mesh_y)
    valid = (
        (scan_x >= 0.0) & (scan_x <= source.width - 1.0)
        & (scan_y >= 0.0) & (scan_y <= source.height - 1.0)
    )
    if float(np.mean(valid)) < 0.5:
        return {
            "scorable": False,
            "reason": "tick pad is mostly outside the captured raster",
        }
    values = np.full(mesh_x.shape, np.nan, np.float64)
    try:
        rgb = sample_layout_points(
            source, affine, mesh_x[valid], mesh_y[valid]
        )
    except (OutOfRasterError, GeometryError, ValueError) as exc:
        return {"scorable": False, "reason": str(exc)}
    values[valid] = density(rgb, str(probe["plane"]))
    observed = values[valid]
    low = float(np.percentile(observed, 5))
    high = float(np.percentile(observed, 95))
    dot_mm = 25.4 / BASE_DPI
    record: dict[str, Any] = {
        "scorable": True,
        "samples_per_dot": TICK_SAMPLES_PER_DOT,
        "pads_layout_dots": dict(pads),
        "size_mm": [width * dot_mm, height * dot_mm],
        "contrast_density": high - low,
        "full_min_fraction": TICK_FULL_MIN_FRACTION,
        "absent_max_fraction": TICK_ABSENT_MAX_FRACTION,
    }
    if high - low < TICK_MIN_CONTRAST_DENSITY:
        return {
            **record,
            "classification": "absent",
            "ink_fraction_nominal": 0.0,
            "ink_fraction_registered": 0.0,
            "displacement_layout_dots": None,
            "threshold_density": None,
        }
    threshold = 0.5 * (low + high)
    ink = ((values > threshold) & valid).astype(np.float64)
    window_x = max(1, int(round(width * TICK_SAMPLES_PER_DOT)))
    window_y = max(1, int(round(height * TICK_SAMPLES_PER_DOT)))
    if ink.shape[0] < window_y or ink.shape[1] < window_x:
        return {**record, "scorable": False,
                "reason": "tick footprint exceeds the observable pad"}
    integral = np.pad(np.cumsum(np.cumsum(ink, 0), 1), ((1, 0), (1, 0)))
    sums = (
        integral[window_y:, window_x:]
        - integral[:-window_y, window_x:]
        - integral[window_y:, :-window_x]
        + integral[:-window_y, :-window_x]
    )
    fractions = sums / float(window_x * window_y)
    nominal_iy = min(
        int(round(pads["top"] * TICK_SAMPLES_PER_DOT)),
        fractions.shape[0] - 1,
    )
    nominal_ix = min(
        int(round(pads["left"] * TICK_SAMPLES_PER_DOT)),
        fractions.shape[1] - 1,
    )
    best_value = float(np.max(fractions))
    tied = np.argwhere(fractions >= best_value - 1e-9)
    # Plateaus tie under blur; prefer the window nearest the nominal
    # position so an undisplaced tick reports zero displacement.
    nearest = int(np.argmin(
        (tied[:, 0] - nominal_iy) ** 2 + (tied[:, 1] - nominal_ix) ** 2
    ))
    best_iy, best_ix = (int(value) for value in tied[nearest])
    nominal = float(fractions[nominal_iy, nominal_ix])
    best = float(fractions[best_iy, best_ix])
    displacement = [
        (int(best_ix) - nominal_ix) * step,
        (int(best_iy) - nominal_iy) * step,
    ]
    if best <= TICK_ABSENT_MAX_FRACTION:
        classification = "absent"
    elif best >= TICK_FULL_MIN_FRACTION:
        classification = "full"
    else:
        classification = "partial"
    record.update({
        "classification": classification,
        "ink_fraction_nominal": nominal,
        "ink_fraction_registered": best,
        "displacement_layout_dots": displacement,
        "threshold_density": threshold,
    })
    edge = str(probe.get("params", {}).get("edge", ""))
    gap_mm = probe.get("params", {}).get("gap_mm")
    if classification == "partial" and edge and gap_mm is not None:
        footprint = ink[
            best_iy:best_iy + window_y, best_ix:best_ix + window_x
        ]
        if edge in {"left", "right"}:
            profile = footprint.mean(axis=0)
            inward_displacement = float(displacement[0])
        else:
            profile = footprint.mean(axis=1)
            inward_displacement = float(displacement[1])
        if edge in {"right", "bottom"}:
            profile = profile[::-1]
            inward_displacement = -inward_displacement
        crossed = np.flatnonzero(profile >= 0.5)
        if crossed.size:
            onset_dots = float(crossed[0]) * step
            record["clip_mm_estimate"] = (
                float(gap_mm)
                + (onset_dots + inward_displacement) * dot_mm
            )
    return record


def _probe_grid(probe: dict[str, Any], max_points: int = 250_000
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    width = int(probe["w_source_dots"])
    height = int(probe["h_source_dots"])
    stride = max(1, int(math.ceil(math.sqrt(width * height / max_points))))
    yy, xx = np.indices(
        (
            math.ceil(height / stride),
            math.ceil(width / stride),
        ),
        dtype=np.float64,
    )
    source_x = np.minimum(xx * stride + 0.5, width - 0.5)
    source_y = np.minimum(yy * stride + 0.5, height - 0.5)
    dpi_x, dpi_y = (int(value) for value in probe["source_dpi"])
    layout_x = (
        float(probe["x_layout_dots"]) + source_x * BASE_DPI / dpi_x
    )
    layout_y = (
        float(probe["y_layout_dots"]) + source_y * BASE_DPI / dpi_y
    )
    truth = pattern_bits(probe)[::stride, ::stride]
    return layout_x, layout_y, truth, stride


def _native_probe_luma(
    source: RasterSource,
    affine: np.ndarray,
    probe: dict[str, Any],
    *,
    max_pixels: int = 2_000_000,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Read a bounded central probe crop without resampling scan pixels."""

    x0 = float(probe["x_layout_dots"])
    y0 = float(probe["y_layout_dots"])
    width = float(probe["w_layout_dots"])
    height = float(probe["h_layout_dots"])
    # An inset keeps a rotated crop's bounding box away from neighboring ink.
    inset_x, inset_y = 0.12 * width, 0.12 * height
    width -= 2.0 * inset_x
    height -= 2.0 * inset_y
    x0 += inset_x
    y0 += inset_y

    limit = min(max_pixels, source.max_crop_pixels)
    for _attempt in range(8):
        corners = np.asarray([
            [x0, y0],
            [x0 + width, y0],
            [x0 + width, y0 + height],
            [x0, y0 + height],
        ])
        scan = np.asarray(apply_affine(affine, corners), dtype=np.float64)
        crop_x0 = max(0, int(math.floor(float(np.min(scan[:, 0])))))
        crop_x1 = min(
            source.width, int(math.ceil(float(np.max(scan[:, 0])))) + 1
        )
        crop_y0 = max(0, int(math.floor(float(np.min(scan[:, 1])))))
        crop_y1 = min(
            source.height, int(math.ceil(float(np.max(scan[:, 1])))) + 1
        )
        area = (crop_x1 - crop_x0) * (crop_y1 - crop_y0)
        if (
            crop_x1 > crop_x0
            and crop_y1 > crop_y0
            and area <= limit
        ):
            break
        scale = min(0.9, math.sqrt(limit / max(area, 1)) * 0.92)
        center_x, center_y = x0 + width / 2.0, y0 + height / 2.0
        width *= scale
        height *= scale
        x0, y0 = center_x - width / 2.0, center_y - height / 2.0
    else:
        raise ValueError("native scanner-diagnostic crop exceeds limit")

    # Preserve the capture's global 8-pixel phase for JPEG block diagnostics.
    aligned_x0 = max(0, crop_x0 - crop_x0 % 8)
    aligned_y0 = max(0, crop_y0 - crop_y0 % 8)
    aligned_x1 = min(source.width, ((crop_x1 + 7) // 8) * 8)
    aligned_y1 = min(source.height, ((crop_y1 + 7) // 8) * 8)
    if (
        (aligned_x1 - aligned_x0) * (aligned_y1 - aligned_y0)
        <= limit
    ):
        crop_x0, crop_x1 = aligned_x0, aligned_x1
        crop_y0, crop_y1 = aligned_y0, aligned_y1
    luma = source.crop_luma(
        crop_y0,
        crop_y1,
        crop_x0,
        crop_x1,
        max_pixels=limit,
    )
    return luma, {
        "source": "native-scan-pixels",
        "crop_xyxy": [crop_x0, crop_y0, crop_x1, crop_y1],
        "crop_shape_yx": list(luma.shape),
        # The extent ACTUALLY read: the loop above shrinks the requested
        # rectangle until it fits the pixel budget, so the authored probe
        # size is not what came back.  Anything converting crop pixels into
        # a physical frequency must divide by this, not by the authored
        # size (W9: doing the latter understated the scan DPI by ~1.8x and
        # therefore mis-scaled the spectral knee).
        "layout_extent_dots": [float(width), float(height)],
    }

def _profile_trace(
    values: np.ndarray,
    truth: np.ndarray,
    probe: dict[str, Any],
    stride: int,
) -> dict[str, Any]:
    params = dict(probe.get("params", {}))
    axis = str(params.get("axis", ""))
    if axis not in {"x", "y"}:
        raise ValueError(f"profile_tone has invalid axis {axis!r}")
    collapse_axis = 0 if axis == "x" else 1
    density_profile = np.mean(values, axis=collapse_axis)
    authored_profile = np.mean(truth, axis=collapse_axis)
    axis_index = 0 if axis == "x" else 1
    source_dpi = float(probe["source_dpi"][axis_index])
    source_length = int(
        probe["w_source_dots"] if axis == "x"
        else probe["h_source_dots"]
    )
    source_positions = np.minimum(
        np.arange(len(density_profile), dtype=np.float64) * stride + 0.5,
        source_length - 0.5,
    )
    local_mm = source_positions / source_dpi * 25.4
    page_start = (
        float(probe["x_layout_dots"])
        if axis == "x"
        else float(probe["y_layout_dots"])
    ) / BASE_DPI * 25.4
    page_mm = page_start + local_mm

    groups = np.array_split(
        np.arange(len(density_profile)),
        min(192, len(density_profile)),
    )
    density_bins = np.asarray([
        float(np.mean(density_profile[group])) for group in groups
    ])
    authored_bins = np.asarray([
        float(np.mean(authored_profile[group])) for group in groups
    ])
    local_bins = np.asarray([
        float(np.mean(local_mm[group])) for group in groups
    ])
    page_bins = np.asarray([
        float(np.mean(page_mm[group])) for group in groups
    ])
    design = np.stack((np.ones(len(local_bins)), local_bins), axis=1)
    coefficients, *_ = np.linalg.lstsq(
        design, density_bins, rcond=None
    )
    fitted = design @ coefficients
    p05, p95 = np.percentile(density_bins, (5.0, 95.0))
    return {
        "axis": axis,
        "mode": params.get("mode"),
        "nominal_coverage": params.get("coverage"),
        "station": params.get("station"),
        "n_bins": int(len(density_bins)),
        "axis_position_mm_from_probe_start": local_bins.tolist(),
        "axis_position_page_mm": page_bins.tolist(),
        "density_bins": density_bins.tolist(),
        "authored_coverage_bins": authored_bins.tolist(),
        "density_mean": float(np.mean(density_bins)),
        "density_p05_p95": [float(p05), float(p95)],
        "density_rms": float(np.std(density_bins)),
        "linear_slope_density_per_mm": float(coefficients[1]),
        "linear_end_to_end_density_delta": float(
            coefficients[1] * (local_bins[-1] - local_bins[0])
        ),
        "detrended_rms_density": float(np.std(density_bins - fitted)),
    }


def _unavailable_phase_rail(
    probe: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    params = dict(probe.get("params", {}))
    axis = params.get("axis")
    on_dots = int(params.get("on_dots", 0))
    off_dots = int(params.get("off_dots", 0))
    period = on_dots + off_dots
    return {
        "axis": axis,
        "period_source_dots": period if period > 0 else None,
        "valid": False,
        "reason": reason,
        "n_segments": 0,
        "n_valid_segments": 0,
        "valid_fraction": 0.0,
        "trace": [],
        "phase_drift_source_dots": None,
        "phase_span_source_dots": None,
        "phase_drift_mm": None,
        "phase_span_mm": None,
    }


def _phase_rail_trace(
    values: np.ndarray,
    truth: np.ndarray,
    probe: dict[str, Any],
    stride: int,
) -> dict[str, Any]:
    """Measure local periodic phase along one transport-geometry rail."""

    params = dict(probe.get("params", {}))
    axis = str(params.get("axis", ""))
    if axis not in {"x", "y"}:
        return _unavailable_phase_rail(
            probe, f"phase_rail has invalid axis {axis!r}"
        )
    on_dots = int(params.get("on_dots", 0))
    off_dots = int(params.get("off_dots", 0))
    period = on_dots + off_dots
    if on_dots <= 0 or off_dots <= 0:
        return _unavailable_phase_rail(
            probe, "phase_rail requires positive on_dots and off_dots"
        )

    collapse_axis = 0 if axis == "x" else 1
    density_profile = np.mean(values, axis=collapse_axis)
    authored_profile = np.mean(truth, axis=collapse_axis)
    axis_index = 0 if axis == "x" else 1
    source_dpi = float(probe["source_dpi"][axis_index])
    source_length = int(
        probe["w_source_dots"] if axis == "x"
        else probe["h_source_dots"]
    )
    source_positions = np.minimum(
        np.arange(len(density_profile), dtype=np.float64) * stride + 0.5,
        source_length - 0.5,
    )
    min_axis_samples = max(
        12,
        int(math.ceil(
            PHASE_RAIL_MIN_PERIODS_PER_SEGMENT * period / stride
        )),
    )
    if len(source_positions) < min_axis_samples:
        return _unavailable_phase_rail(
            probe, "phase_rail is too short for local phase measurement"
        )

    rail_length_mm = source_length / source_dpi * 25.4
    requested_segments = max(
        1, int(round(rail_length_mm / PHASE_RAIL_SEGMENT_TARGET_MM))
    )
    n_segments = min(
        requested_segments,
        max(1, len(source_positions) // min_axis_samples),
    )
    groups = np.array_split(np.arange(len(source_positions)), n_segments)
    page_start_mm = (
        float(probe["x_layout_dots"])
        if axis == "x"
        else float(probe["y_layout_dots"])
    ) / BASE_DPI * 25.4
    angular_frequency = 2.0 * math.pi / period
    trace: list[dict[str, Any]] = []

    for segment_index, group in enumerate(groups):
        positions = source_positions[group]
        measured = np.asarray(density_profile[group], dtype=np.float64)
        authored = np.asarray(authored_profile[group], dtype=np.float64)
        local_values = (
            values[:, group].ravel()
            if axis == "x"
            else values[group, :].ravel()
        )
        local_mm = float(np.mean(positions) / source_dpi * 25.4)
        point: dict[str, Any] = {
            "segment_index": segment_index,
            "axis_position_mm_from_probe_start": local_mm,
            "axis_position_page_mm": page_start_mm + local_mm,
            "n_axis_samples": int(len(group)),
            "n_density_samples": int(local_values.size),
            "density_mean": float(np.mean(local_values)),
            "density_p05_p95": [
                float(np.percentile(local_values, 5.0)),
                float(np.percentile(local_values, 95.0)),
            ],
            "density_span_p05_p95": float(
                np.percentile(local_values, 95.0)
                - np.percentile(local_values, 5.0)
            ),
            "correlation": None,
            "phase_source_dots_wrapped": None,
            "phase_source_dots_unwrapped": None,
            "phase_mm_unwrapped": None,
            "valid": False,
        }
        if (
            len(group) < min_axis_samples
            or not np.all(np.isfinite(measured))
            or not np.all(np.isfinite(authored))
        ):
            point["reason"] = "insufficient-or-nonfinite-samples"
            trace.append(point)
            continue

        measured_centered = measured - float(np.mean(measured))
        authored_centered = authored - float(np.mean(authored))
        measured_energy = float(np.linalg.norm(measured_centered))
        authored_energy = float(np.linalg.norm(authored_centered))
        density_span = float(np.ptp(measured))
        if (
            measured_energy <= 1e-9
            or authored_energy <= 1e-9
            or density_span <= 1e-9
        ):
            point["reason"] = "no-periodic-density-contrast"
            trace.append(point)
            continue

        carrier = np.exp(-1j * angular_frequency * positions)
        measured_coefficient = np.sum(measured_centered * carrier)
        authored_coefficient = np.sum(authored_centered * carrier)
        if (
            abs(measured_coefficient) <= 1e-12
            or abs(authored_coefficient) <= 1e-12
        ):
            point["reason"] = "no-fundamental-phase-component"
            trace.append(point)
            continue
        phase = (
            -np.angle(measured_coefficient * np.conj(authored_coefficient))
            / angular_frequency
        )
        wrapped_phase = float(
            (phase + period / 2.0) % period - period / 2.0
        )

        basis = np.column_stack((
            np.cos(angular_frequency * positions),
            np.sin(angular_frequency * positions),
        ))
        coefficients, *_ = np.linalg.lstsq(
            basis, measured_centered, rcond=None
        )
        fitted = basis @ coefficients
        fitted_energy = float(np.linalg.norm(fitted))
        correlation = (
            0.0
            if fitted_energy <= 1e-12
            else float(
                np.dot(measured_centered, fitted)
                / (measured_energy * fitted_energy)
            )
        )
        point.update({
            "correlation": correlation,
            "phase_source_dots_wrapped": wrapped_phase,
        })
        if (
            not math.isfinite(correlation)
            or correlation < PHASE_RAIL_CORRELATION_MIN
        ):
            point["reason"] = "periodic-correlation-below-threshold"
            trace.append(point)
            continue
        point["valid"] = True
        trace.append(point)

    valid_points = [point for point in trace if point["valid"]]
    valid_fraction = len(valid_points) / len(trace) if trace else 0.0
    minimum_valid = max(2, int(math.ceil(
        PHASE_RAIL_MIN_VALID_FRACTION * len(trace)
    )))
    valid = len(valid_points) >= minimum_valid
    result = {
        "axis": axis,
        "period_source_dots": period,
        "phase_reference": "authored-rail-period",
        "segment_target_mm": PHASE_RAIL_SEGMENT_TARGET_MM,
        "correlation_minimum": PHASE_RAIL_CORRELATION_MIN,
        "minimum_valid_fraction": PHASE_RAIL_MIN_VALID_FRACTION,
        "valid": valid,
        "n_segments": len(trace),
        "n_valid_segments": len(valid_points),
        "valid_fraction": valid_fraction,
        "trace": trace,
        "phase_drift_source_dots": None,
        "phase_span_source_dots": None,
        "phase_drift_mm": None,
        "phase_span_mm": None,
    }
    if not valid_points:
        result["reason"] = "no-valid-phase-segments"
        return result

    wrapped = np.asarray([
        float(point["phase_source_dots_wrapped"])
        for point in valid_points
    ])
    unwrapped = (
        np.unwrap(wrapped * angular_frequency) / angular_frequency
    )
    for point, phase_value in zip(valid_points, unwrapped, strict=True):
        point["phase_source_dots_unwrapped"] = float(phase_value)
        point["phase_mm_unwrapped"] = float(
            phase_value / source_dpi * 25.4
        )
    drift = float(unwrapped[-1] - unwrapped[0])
    span = float(np.ptp(unwrapped))
    positions_mm = np.asarray([
        float(point["axis_position_mm_from_probe_start"])
        for point in valid_points
    ])
    if len(valid_points) >= 2 and np.ptp(positions_mm) > 0.0:
        design = np.column_stack((np.ones(len(positions_mm)), positions_mm))
        coefficients, *_ = np.linalg.lstsq(design, unwrapped, rcond=None)
        fitted = design @ coefficients
        slope = float(coefficients[1])
        detrended_rms = float(np.std(unwrapped - fitted))
    else:
        slope = None
        detrended_rms = None
    density_means = np.asarray([
        float(point["density_mean"]) for point in valid_points
    ])
    correlations = np.asarray([
        float(point["correlation"]) for point in valid_points
    ])
    result.update({
        "phase_drift_source_dots": drift,
        "phase_span_source_dots": span,
        "phase_drift_mm": drift / source_dpi * 25.4,
        "phase_span_mm": span / source_dpi * 25.4,
        "linear_phase_slope_source_dots_per_mm": slope,
        "detrended_phase_rms_source_dots": detrended_rms,
        "minimum_valid_correlation": float(np.min(correlations)),
        "density_mean_span": float(np.ptp(density_means)),
    })
    if not valid:
        result["reason"] = "valid-phase-segment-fraction-below-threshold"
    return result


def measure_probe(
    source: RasterSource,
    affine: np.ndarray,
    probe: dict[str, Any],
) -> dict[str, Any]:
    """Numerically score one typed physical/scanner probe."""

    visible, fraction = layout_footprint_visibility(source, affine, probe)
    result: dict[str, Any] = {
        "probe_id": probe["probe_id"],
        "kind": probe["kind"],
        "group": probe["group"],
        "plane": probe["plane"],
        "params": dict(probe.get("params", {})),
        "visible": visible,
        "visible_vertex_fraction": fraction,
    }
    kind = str(probe["kind"])
    if not visible:
        unavailable = {**result, "status": "unobservable"}
        if kind == "phase_rail":
            unavailable["phase_rail"] = _unavailable_phase_rail(
                probe, "probe-footprint-unobservable"
            )
        return unavailable
    try:
        x, y, truth, stride = _probe_grid(
            probe,
            max_points=(
                2_000_000
                if probe.get("group") == "grid-discovery"
                else 250_000
            ),
        )
        rgb = sample_layout_points(source, affine, x, y)
    except (OutOfRasterError, GeometryError, ValueError) as exc:
        unavailable = {
            **result, "status": "unobservable", "reason": str(exc)
        }
        if kind == "phase_rail":
            unavailable["phase_rail"] = _unavailable_phase_rail(
                probe, str(exc)
            )
        return unavailable

    plane = str(probe["plane"])
    values = density(rgb, plane)
    luma = luma709(rgb)
    result.update({
        "status": "ok",
        "sample_stride_source_dots": stride,
        "source_dpi": list(probe["source_dpi"]),
        "n_samples": int(values.size),
        "reflectance_median": float(np.median(luma)),
        "reflectance_p05_p95": [
            float(np.percentile(luma, 5)),
            float(np.percentile(luma, 95)),
        ],
        "density_median": float(np.median(values)),
        "channel_density_medians": {
            name: float(np.median(density(rgb, name)))
            for name in "CMYK"
        },
    })
    has_ink = bool(np.any(truth != 0))
    has_paper = bool(np.any(truth == 0))
    if has_ink and has_paper:
        result["pattern"] = pattern_score(
            truth, values, max_shift=max(1, 6 // stride)
        )
    elif np.all(truth):
        result["solid_density_p05"] = float(np.percentile(values, 5))
    else:
        result.update({
            "paper_noise_highpass": highpass_noise(luma),
            "blockiness_8px": blockiness(luma),
            "dark_fraction_below_0_80": float(np.mean(luma < 0.80)),
        })

    if kind == "edge_tick":
        result["tick"] = _edge_tick_registration(source, affine, probe)

    if probe["group"] == "scanner-adequacy":
        try:
            native_luma, native_metadata = _native_probe_luma(
                source, affine, probe
            )
        except (GeometryError, ValueError) as exc:
            result["native_scanner_diagnostics"] = {
                "source": "unavailable",
                "reason": str(exc),
            }
        else:
            native_noise = highpass_noise(native_luma)
            result.update({
                "native_scanner_diagnostics": native_metadata,
                "blockiness_8px": blockiness(native_luma),
            })
            if kind in {"paper", "quiet_zone"}:
                result.update({
                    "paper_noise_highpass": native_noise,
                    "paper_noise_highpass_8bit_counts": (
                        native_noise * 255.0
                    ),
                    "dark_fraction_below_0_80": float(
                        np.mean(native_luma < 0.80)
                    ),
                })
                # W9/W10 (e031): capture forensics on the UNPRINTED quiet
                # region.  blockiness_comb is the phase-invariant seam
                # detector (gates, in summarize); level_occupancy probes
                # posterisation/bit-depth reduction (advisory — it has never
                # fired on real material and is recorded as a null detector
                # so nobody re-derives it as a gate).  The spectral-knee /
                # flatness advisory that briefly lived here was RETIRED:
                # on blank paper the "signal" is paper texture, and every
                # statistic built on it proved patch-unstable (workplan W9
                # second pass / W10).
                comb = blockiness_comb(native_luma)
                if comb is not None:
                    result["blockiness_comb"] = comb
                result["level_occupancy"] = level_occupancy(native_luma)
    if kind == "profile_tone":
        result["profile"] = _profile_trace(
            values, truth, probe, stride
        )
    if kind == "phase_rail":
        result["phase_rail"] = _phase_rail_trace(
            values, truth, probe, stride
        )
    dpi_x, dpi_y = (float(value) / stride for value in probe["source_dpi"])
    if kind == "slanted_edge":
        result["mtf"] = slanted_edge_mtf50(
            values, dpi_x, dpi_y,
            float(probe.get("params", {}).get("angle_deg", 5.0)),
        )
    if probe["group"] == "screen":
        screen = screen_fingerprint(
            values, truth, dpi_x, dpi_y
        )
        params = dict(probe.get("params", {}))
        screen.update({
            "matched_set": params.get("matched_set"),
            "control_role": params.get("control_role"),
            "emission_path": params.get("path"),
            "measurement_feature": params.get("measurement_feature"),
            "authored_pattern_sha256": probe.get(
                "ground_truth_sha256"
            ),
            "authored_shape_yx": [
                int(probe["h_source_dots"]),
                int(probe["w_source_dots"]),
            ],
            "authored_dpi": list(probe["source_dpi"]),
            "authored_planes": list(
                params.get("planes", [probe["plane"]])
            ),
            "physical_extent_mm": [
                float(probe["w_source_dots"])
                / float(probe["source_dpi"][0]) * 25.4,
                float(probe["h_source_dots"])
                / float(probe["source_dpi"][1]) * 25.4,
            ],
        })
        result["screen"] = screen
    if kind == "registration_cross":
        weights = np.clip(values - np.percentile(values, 20), 0.0, None)
        total = float(weights.sum())
        if total > 0:
            yy, xx = np.indices(values.shape, dtype=np.float64)
            result["centroid_source_dots"] = [
                float(np.sum(xx * weights) / total * stride),
                float(np.sum(yy * weights) / total * stride),
            ]
            result["registration_target"] = probe.get(
                "params", {}
            ).get("target")
    return result


def measure_all_probes(
    source: RasterSource,
    affine: np.ndarray,
    probes: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [measure_probe(source, affine, probe) for probe in probes]

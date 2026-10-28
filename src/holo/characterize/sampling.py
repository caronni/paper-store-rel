"""Bounded field sampling primitives and the exact threshold fit."""
from __future__ import annotations

import hashlib
from typing import Any, Iterable

import numpy as np

from .diagnostics import (
    density,
)
from .geometry import (
    sample_layout_points,
)
from .model import BASE_DPI, CANDIDATES_BY_CODE, Candidate
from .patterns import symbol_motif
from .raster import RasterSource


MIN_SAMPLES_PER_CELL = 4.0
PHASE_CERTIFY_ERROR_MAX = 0.20
PHASE_CERTIFY_CORRELATION_MIN = 0.12
WINDOW_TARGET_MM = 4.7
PHASE_WIDE_SPAN_CELLS = 2.6
PHASE_LOCAL_SPAN_CELLS = 0.7
MAX_PHASE_POINTS = 1024
MAX_MODEL_POINTS_PER_ROLE = 20_000
PHASE_RAIL_SEGMENT_TARGET_MM = 8.0
PHASE_RAIL_MIN_PERIODS_PER_SEGMENT = 3.0
PHASE_RAIL_CORRELATION_MIN = 0.20
PHASE_RAIL_MIN_VALID_FRACTION = 0.75


def _field_key(field_id: str) -> int:
    return int.from_bytes(
        hashlib.sha256(field_id.encode("utf-8")).digest()[:8], "big"
    )


def _candidate(code: int) -> Candidate:
    try:
        return CANDIDATES_BY_CODE[int(code)]
    except KeyError as exc:
        raise ValueError(f"unknown candidate code {code}") from exc


def _cell_geometry(
    field: dict[str, Any], candidate: Candidate
) -> tuple[np.ndarray, np.ndarray, float, float]:
    nx, ny = int(field["nx"]), int(field["ny"])
    pitch_x = candidate.cell_dots[0] * BASE_DPI / candidate.grid_dpi[0]
    pitch_y = candidate.cell_dots[1] * BASE_DPI / candidate.grid_dpi[1]
    x0, y0 = float(field["x_layout_dots"]), float(field["y_layout_dots"])
    yy, xx = np.indices((ny, nx), dtype=np.float64)
    return (
        x0 + (xx + 0.5) * pitch_x,
        y0 + (yy + 0.5) * pitch_y,
        float(pitch_x),
        float(pitch_y),
    )


def _samples_per_cell(
    affine: np.ndarray, pitch_x: float, pitch_y: float
) -> dict[str, float]:
    linear = np.asarray(affine, dtype=np.float64)[:, :2]
    samples_x = float(np.linalg.norm(linear[:, 0]) * pitch_x)
    samples_y = float(np.linalg.norm(linear[:, 1]) * pitch_y)
    samples_area = float(
        abs(np.linalg.det(linear)) * pitch_x * pitch_y
    )
    return {
        "x": samples_x,
        "y": samples_y,
        "area": samples_area,
    }


def _take_bounded(indices: np.ndarray, limit: int) -> np.ndarray:
    values = np.asarray(indices, dtype=np.int64)
    if len(values) <= limit:
        return values
    positions = np.linspace(0, len(values) - 1, limit, dtype=np.int64)
    return values[positions]


def _membership(states: np.ndarray, candidate: Candidate,
                plane: str) -> np.ndarray:
    lookup = np.asarray(
        [plane in state_planes for state_planes in candidate.state_planes],
        dtype=bool,
    )
    return lookup[np.asarray(states, dtype=np.int64)]


def _sample_plane(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    *,
    plane: str,
    candidate: Candidate,
    pitch_x: float,
    pitch_y: float,
) -> np.ndarray:
    """Sample one plane, integrating the authored motif when multilevel."""

    if candidate.symbol_shape.startswith("nested-"):
        aperture = np.asarray((-0.375, -0.125, 0.125, 0.375))
        sample_x = (
            np.asarray(x)[..., None, None]
            + aperture[None, None, :] * pitch_x
        )
        sample_y = (
            np.asarray(y)[..., None, None]
            + aperture[None, :, None] * pitch_y
        )
        sample_x, sample_y = np.broadcast_arrays(sample_x, sample_y)
        rgb = sample_layout_points(source, affine, sample_x, sample_y)
        return density(rgb, plane).mean(axis=(-2, -1))
    if candidate.symbol_shape != "solid":
        cell_x, cell_y = candidate.cell_dots
        motif = symbol_motif(candidate.cell_dots, candidate.symbol_shape)
        motif_y, motif_x = np.nonzero(motif)
        offsets_x = (
            (motif_x.astype(np.float64) + 0.5) / cell_x - 0.5
        ) * pitch_x
        offsets_y = (
            (motif_y.astype(np.float64) + 0.5) / cell_y - 0.5
        ) * pitch_y
        sample_x = np.asarray(x)[..., None] + offsets_x
        sample_y = np.asarray(y)[..., None] + offsets_y
        rgb = sample_layout_points(source, affine, sample_x, sample_y)
        return density(rgb, plane).mean(axis=-1)
    return density(
        sample_layout_points(source, affine, x, y), plane
    )


def _correlation(expected: np.ndarray, measured: np.ndarray) -> float:
    left = np.asarray(expected, dtype=np.float64)
    right = np.asarray(measured, dtype=np.float64)
    if len(left) < 4 or np.ptp(left) == 0.0 or np.ptp(right) == 0.0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def _minimum_error_threshold(
    values: np.ndarray,
    expected_ink: np.ndarray,
) -> tuple[float, float]:
    measured = np.asarray(values, dtype=np.float64)
    truth = np.asarray(expected_ink, dtype=bool)
    unique = np.unique(measured)
    if len(unique) == 1:
        thresholds = np.asarray([
            np.nextafter(unique[0], -np.inf),
            np.nextafter(unique[0], np.inf),
        ])
    else:
        thresholds = np.concatenate((
            [np.nextafter(unique[0], -np.inf)],
            0.5 * (unique[:-1] + unique[1:]),
            [np.nextafter(unique[-1], np.inf)],
        ))
    midpoint = 0.5 * (
        float(np.median(measured[truth]))
        + float(np.median(measured[~truth]))
    )
    errors = np.asarray([
        np.count_nonzero((measured > threshold) != truth)
        for threshold in thresholds
    ])
    best_error = int(np.min(errors))
    tied = np.flatnonzero(errors == best_error)
    best = min(
        (int(index) for index in tied),
        key=lambda index: (
            abs(float(thresholds[index]) - midpoint),
            float(thresholds[index]),
        ),
    )
    return float(thresholds[best]), best_error / len(truth)

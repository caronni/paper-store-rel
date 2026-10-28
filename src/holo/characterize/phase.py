"""Local phase search, certification, and the phase/density model."""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

from .geometry import (
    apply_affine,
)
from .model import BASE_DPI, Candidate
from .raster import RasterSource
from .statistics import (
    ROLE_CERTIFY,
    ROLE_FIT,
    bounded_stratified_indices,
)
from .sampling import (
    MAX_PHASE_POINTS,
    PHASE_CERTIFY_CORRELATION_MIN,
    PHASE_CERTIFY_ERROR_MAX,
    PHASE_LOCAL_SPAN_CELLS,
    PHASE_WIDE_SPAN_CELLS,
    _correlation,
    _membership,
    _minimum_error_threshold,
    _sample_plane,
)


def _phase_support(
    expected: np.ndarray,
    candidate: Candidate,
) -> bool:
    values = np.asarray(expected).ravel()
    if len(values) < 24:
        return False
    if candidate.symbol_shape.startswith("nested-"):
        return len(np.unique(values)) == candidate.n_states
    selected = values.astype(bool)
    return min(
        int(np.count_nonzero(selected)),
        int(np.count_nonzero(~selected)),
    ) >= 6


def _phase_score(
    expected: np.ndarray,
    measured: np.ndarray,
    candidate: Candidate,
) -> tuple[float, float, float]:
    if candidate.symbol_shape.startswith("nested-"):
        ink = measured[expected == 1.0]
        paper = measured[expected == 0.0]
    else:
        selected = expected.astype(bool)
        ink, paper = measured[selected], measured[~selected]
    if not len(ink) or not len(paper):
        return float("-inf"), float("nan"), float("nan")
    separation = float(np.median(ink) - np.median(paper))
    correlation = _correlation(expected, measured)
    spread = max(
        0.5 * (float(np.std(ink)) + float(np.std(paper))),
        1e-7,
    )
    return separation / spread, correlation, separation


def _phase_axis(
    center: float,
    span: float,
    step: float,
    lower: float,
    upper: float,
) -> np.ndarray:
    count = max(1, int(math.ceil(2.0 * span / step)))
    values = np.linspace(center - span, center + span, count + 1)
    values = np.concatenate((values, [center]))
    return np.unique(np.round(np.clip(values, lower, upper), 12))


def _best_phase_offsets(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    expected: np.ndarray,
    candidate: Candidate,
    plane: str,
    pitch_x: float,
    pitch_y: float,
    offsets_cells: np.ndarray,
    *,
    tie_origin: tuple[float, float],
    visibility_indices: np.ndarray | None = None,
) -> dict[str, Any] | None:
    offsets = np.asarray(offsets_cells, dtype=np.float64).reshape(-1, 2)
    if not len(offsets):
        return None
    offsets_layout = offsets * np.asarray((pitch_x, pitch_y))[None, :]

    visible_at = indices if visibility_indices is None else visibility_indices
    base_scan = np.asarray(apply_affine(
        affine,
        np.stack((x.ravel()[visible_at], y.ravel()[visible_at]), axis=1),
    ))
    linear = np.asarray(affine, dtype=np.float64)[:, :2]
    scan_delta = offsets_layout @ linear.T
    aperture_margin = np.abs(linear) @ np.asarray(
        (0.5 * pitch_x, 0.5 * pitch_y),
        dtype=np.float64,
    )
    valid = (
        (
            np.min(base_scan[:, 0]) + scan_delta[:, 0]
            >= aperture_margin[0]
        )
        & (
            np.max(base_scan[:, 0]) + scan_delta[:, 0]
            <= source.width - 1.0 - aperture_margin[0]
        )
        & (
            np.min(base_scan[:, 1]) + scan_delta[:, 1]
            >= aperture_margin[1]
        )
        & (
            np.max(base_scan[:, 1]) + scan_delta[:, 1]
            <= source.height - 1.0 - aperture_margin[1]
        )
    )
    valid_indices = np.flatnonzero(valid)
    best: tuple[float, float, float, float, int] | None = None
    for start in range(0, len(valid_indices), 64):
        selected = valid_indices[start:start + 64]
        layout = offsets_layout[selected]
        measured = _sample_plane(
            source,
            affine,
            x.ravel()[indices][None, :] + layout[:, 0, None],
            y.ravel()[indices][None, :] + layout[:, 1, None],
            plane=plane,
            candidate=candidate,
            pitch_x=pitch_x,
            pitch_y=pitch_y,
        )
        for local_index, values in enumerate(measured):
            offset_index = int(selected[local_index])
            score, correlation, separation = _phase_score(
                expected, values, candidate
            )
            if (
                not math.isfinite(score)
                or not math.isfinite(correlation)
                or separation <= 0.0
            ):
                continue
            dx, dy = offsets[offset_index]
            distance = (
                (float(dx) - tie_origin[0]) ** 2
                + (float(dy) - tie_origin[1]) ** 2
            )
            row = score, correlation, separation, -distance, offset_index
            if best is None or row[:4] > best[:4]:
                best = row
    if best is None:
        return None
    index = int(best[4])
    return {
        "offset_cells": offsets[index].tolist(),
        "score": float(best[0]),
        "correlation": float(best[1]),
        "density_separation": float(best[2]),
        "n_candidates": int(len(offsets)),
        "n_visible_candidates": int(np.count_nonzero(valid)),
    }


def _phase_search(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    expected: np.ndarray,
    candidate: Candidate,
    plane: str,
    pitch_x: float,
    pitch_y: float,
    *,
    seed: tuple[float, float] | None,
    visibility_indices: np.ndarray | None = None,
) -> dict[str, Any] | None:
    base = (0.0, 0.0) if seed is None else seed
    span = (
        PHASE_WIDE_SPAN_CELLS
        if seed is None
        else PHASE_LOCAL_SPAN_CELLS
    )
    lower = (base[0] - span, base[1] - span)
    upper = (base[0] + span, base[1] + span)
    searches: list[dict[str, Any]] = []

    def probe(offsets_cells: np.ndarray) -> dict[str, Any] | None:
        # One sampling context, six offset schedules: the context is
        # closed over instead of hand-threaded through every call.
        return _best_phase_offsets(
            source, affine, x, y, indices, expected, candidate, plane,
            pitch_x, pitch_y, offsets_cells,
            tie_origin=base, visibility_indices=visibility_indices,
        )

    if seed is None:
        xs = _phase_axis(base[0], span, 0.4, lower[0], upper[0])
        ys = _phase_axis(base[1], span, 0.4, lower[1], upper[1])
        coarse = np.asarray(
            [(dx, dy) for dy in ys for dx in xs],
            dtype=np.float64,
        )
        best = probe(coarse)
        if best is None:
            return None
        searches.append(best)
        for refine_span, refine_step in ((0.24, 0.08), (0.06, 0.03)):
            dx, dy = (float(value) for value in best["offset_cells"])
            xs = _phase_axis(
                dx, refine_span, refine_step, lower[0], upper[0]
            )
            ys = _phase_axis(
                dy, refine_span, refine_step, lower[1], upper[1]
            )
            refined = probe(np.asarray(
                [(px, py) for py in ys for px in xs],
                dtype=np.float64,
            ))
            if refined is not None:
                best = refined
                searches.append(refined)
    else:
        ys = _phase_axis(base[1], span, 0.1, lower[1], upper[1])
        best = probe(np.asarray([(base[0], py) for py in ys], np.float64))
        if best is None:
            return None
        searches.append(best)
        xs = _phase_axis(base[0], span, 0.1, lower[0], upper[0])
        dy = float(best["offset_cells"][1])
        refined = probe(np.asarray([(px, dy) for px in xs], np.float64))
        if refined is not None:
            best = refined
            searches.append(refined)
        dx = float(best["offset_cells"][0])
        ys = _phase_axis(base[1], span, 0.1, lower[1], upper[1])
        refined = probe(np.asarray([(dx, py) for py in ys], np.float64))
        if refined is not None:
            best = refined
            searches.append(refined)
        dx, dy = (float(value) for value in best["offset_cells"])
        xs = _phase_axis(dx, 0.06, 0.03, lower[0], upper[0])
        ys = _phase_axis(dy, 0.06, 0.03, lower[1], upper[1])
        refined = probe(np.asarray(
                [(px, py) for py in ys for px in xs],
                dtype=np.float64,
            ))
        if refined is not None:
            best = refined
            searches.append(refined)

    dx, dy = (float(value) for value in best["offset_cells"])
    boundary_distance = min(
        dx - lower[0],
        upper[0] - dx,
        dy - lower[1],
        upper[1] - dy,
    )
    return {
        **best,
        "search_kind": "wide" if seed is None else "local",
        "seed_cells": None if seed is None else list(seed),
        "boundary_hit": bool(boundary_distance <= 0.075),
        "search_span_cells": span,
        "n_candidates": int(sum(
            row["n_candidates"] for row in searches
        )),
        "n_visible_candidates": int(sum(
            row["n_visible_candidates"] for row in searches
        )),
    }


def _fit_phase_density_model(
    values: np.ndarray,
    expected: np.ndarray,
    candidate: Candidate,
) -> dict[str, Any]:
    if candidate.symbol_shape.startswith("nested-"):
        levels = np.linspace(0.0, 1.0, candidate.n_states)
        centroids = np.asarray([
            np.median(values[expected == level]) for level in levels
        ])
        return {
            "multilevel": True,
            "levels": levels,
            "centroids": centroids,
            "threshold": None,
        }
    threshold, _error = _minimum_error_threshold(
        values, expected.astype(bool)
    )
    return {
        "multilevel": False,
        "levels": None,
        "centroids": None,
        "threshold": threshold,
    }


def _evaluate_phase_density_model(
    model: dict[str, Any],
    values: np.ndarray,
    expected: np.ndarray,
) -> dict[str, Any]:
    if model["multilevel"]:
        levels = np.asarray(model["levels"])
        centroids = np.asarray(model["centroids"])
        predicted = levels[np.argmin(
            np.abs(values[:, None] - centroids[None, :]), axis=1
        )]
        monotonic = bool(np.all(np.diff(centroids) > 0.0))
        ink = values[expected == 1.0]
        paper = values[expected == 0.0]
    else:
        predicted = values > float(model["threshold"])
        expected = expected.astype(bool)
        monotonic = True
        ink, paper = values[expected], values[~expected]
    error = float(np.mean(predicted != expected))
    correlation = _correlation(expected, values)
    separation = (
        float(np.median(ink) - np.median(paper))
        if len(ink) and len(paper)
        else float("nan")
    )
    ok = bool(
        math.isfinite(correlation)
        and correlation >= PHASE_CERTIFY_CORRELATION_MIN
        and monotonic
        and math.isfinite(separation)
        and separation > 0.0
        and error < PHASE_CERTIFY_ERROR_MAX
    )
    return {
        "ok": ok,
        "error_rate": error,
        "correlation": (
            correlation if math.isfinite(correlation) else None
        ),
        "density_separation": (
            separation if math.isfinite(separation) else None
        ),
        "monotonic_levels": monotonic,
    }


def _sample_phase(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    offset_cells: tuple[float, float],
    *,
    plane: str,
    candidate: Candidate,
    pitch_x: float,
    pitch_y: float,
) -> np.ndarray:
    return _sample_plane(
        source,
        affine,
        x.ravel()[indices] + offset_cells[0] * pitch_x,
        y.ravel()[indices] + offset_cells[1] * pitch_y,
        plane=plane,
        candidate=candidate,
        pitch_x=pitch_x,
        pitch_y=pitch_y,
    )


def _phase_lock(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    search_indices: np.ndarray,
    lock_indices: np.ndarray,
    expected_all: np.ndarray,
    candidate: Candidate,
    plane: str,
    pitch_x: float,
    pitch_y: float,
    offset_cells: tuple[float, float],
) -> dict[str, Any] | None:
    if not len(lock_indices):
        return None
    search_values = _sample_phase(
        source, affine, x, y, search_indices, offset_cells,
        plane=plane, candidate=candidate,
        pitch_x=pitch_x, pitch_y=pitch_y,
    )
    model = _fit_phase_density_model(
        search_values, expected_all[search_indices], candidate
    )
    lock_values = _sample_phase(
        source, affine, x, y, lock_indices, offset_cells,
        plane=plane, candidate=candidate,
        pitch_x=pitch_x, pitch_y=pitch_y,
    )
    return _evaluate_phase_density_model(
        model, lock_values, expected_all[lock_indices]
    )


def _phase_lock_key(
    lock: dict[str, Any] | None,
    search: dict[str, Any],
) -> tuple[float, float, float, float]:
    if lock is None:
        return 0.0, -1.0, -1.0, float(search["score"])
    return (
        1.0 if lock["ok"] else 0.0,
        -float(lock["error_rate"]),
        float(lock["correlation"] or -1.0),
        float(lock["density_separation"] or -1.0),
    )


def _phase_fit(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    states: np.ndarray,
    roles: np.ndarray,
    window: np.ndarray,
    candidate: Candidate,
    plane: str,
    pitch_x: float,
    pitch_y: float,
    *,
    seed_cells: tuple[float, float] | None = None,
) -> dict[str, Any]:
    fit = np.flatnonzero(window.ravel() & (roles.ravel() == ROLE_FIT))
    certify = np.flatnonzero(
        window.ravel() & (roles.ravel() == ROLE_CERTIFY)
    )
    multilevel = candidate.symbol_shape.startswith("nested-")
    expected_all = (
        states.astype(np.float64).ravel() / (candidate.n_states - 1)
        if multilevel
        else _membership(states, candidate, plane).ravel()
    )
    fit = bounded_stratified_indices(
        fit, expected_all[fit], MAX_PHASE_POINTS
    )
    certify = bounded_stratified_indices(
        certify, expected_all[certify], MAX_PHASE_POINTS * 2
    )
    expected_fit = expected_all[fit]
    expected_certify = expected_all[certify]
    if (
        not _phase_support(expected_fit, candidate)
        or not _phase_support(expected_certify, candidate)
    ):
        return {
            "ok": False,
            "status": "insufficient_phase_support",
            "plane": plane,
            "n_fit": int(len(fit)),
            "n_certify": int(len(certify)),
        }

    search_parts: list[np.ndarray] = []
    lock_parts: list[np.ndarray] = []
    for state in np.unique(expected_fit):
        group = fit[expected_fit == state]
        search_parts.append(group[::2])
        lock_parts.append(group[1::2])
    search_indices = np.sort(np.concatenate(search_parts))
    lock_indices = np.sort(np.concatenate(lock_parts))
    if (
        not _phase_support(expected_all[search_indices], candidate)
        or not _phase_support(expected_all[lock_indices], candidate)
    ):
        search_indices = fit
        lock_indices = np.empty(0, dtype=np.int64)

    selected = _phase_search(
        source, affine, x, y, search_indices,
        expected_all[search_indices], candidate, plane,
        pitch_x, pitch_y, seed=seed_cells,
        visibility_indices=np.concatenate((fit, certify)),
    )
    fallback_reason: str | None = None
    search_mode = "wide-initial" if seed_cells is None else "local"
    lock: dict[str, Any] | None = None
    if selected is not None:
        selected_offset = tuple(
            float(value) for value in selected["offset_cells"]
        )
        lock = _phase_lock(
            source, affine, x, y, search_indices, lock_indices,
            expected_all, candidate, plane, pitch_x, pitch_y,
            selected_offset,
        )

    if seed_cells is not None and (
        selected is None
        or selected["boundary_hit"]
        or lock is None
        or not lock["ok"]
    ):
        if selected is None:
            fallback_reason = "local_search_unscorable"
        elif selected["boundary_hit"]:
            fallback_reason = "local_search_boundary_hit"
        elif lock is None:
            fallback_reason = "independent_fit_lock_unavailable"
        else:
            fallback_reason = "independent_fit_lock_failed"
        wide = _phase_search(
            source, affine, x, y, search_indices,
            expected_all[search_indices], candidate, plane,
            pitch_x, pitch_y, seed=None,
            visibility_indices=np.concatenate((fit, certify)),
        )
        wide_lock: dict[str, Any] | None = None
        if wide is not None:
            wide_offset = tuple(
                float(value) for value in wide["offset_cells"]
            )
            wide_lock = _phase_lock(
                source, affine, x, y, search_indices, lock_indices,
                expected_all, candidate, plane, pitch_x, pitch_y,
                wide_offset,
            )
        if wide is not None and (
            selected is None
            or selected["boundary_hit"]
            or _phase_lock_key(wide_lock, wide)
            > _phase_lock_key(lock, selected)
        ):
            selected, lock = wide, wide_lock
            search_mode = "wide-fallback"
        elif selected is not None:
            search_mode = "local-after-wide-check"

    if selected is None:
        return {
            "ok": False,
            "status": "phase_fit_no_positive_separation",
            "plane": plane,
            "seed_cells": (
                None if seed_cells is None else list(seed_cells)
            ),
            "wide_fallback_reason": fallback_reason,
            "n_fit": int(len(fit)),
            "n_certify": int(len(certify)),
        }

    offset_cells = tuple(
        float(value) for value in selected["offset_cells"]
    )
    fit_values = _sample_phase(
        source, affine, x, y, fit, offset_cells,
        plane=plane, candidate=candidate,
        pitch_x=pitch_x, pitch_y=pitch_y,
    )
    density_model = _fit_phase_density_model(
        fit_values, expected_fit, candidate
    )
    fit_metrics = _evaluate_phase_density_model(
        density_model, fit_values, expected_fit
    )
    certify_values = _sample_phase(
        source, affine, x, y, certify, offset_cells,
        plane=plane, candidate=candidate,
        pitch_x=pitch_x, pitch_y=pitch_y,
    )
    certify_metrics = _evaluate_phase_density_model(
        density_model, certify_values, expected_certify
    )
    range_exhausted = bool(
        selected["search_kind"] == "wide" and selected["boundary_hit"]
    )
    ok = bool(certify_metrics["ok"] and not range_exhausted)
    offset_layout = [
        offset_cells[0] * pitch_x,
        offset_cells[1] * pitch_y,
    ]
    centroids = density_model["centroids"]
    threshold = density_model["threshold"]
    return {
        "ok": ok,
        "status": (
            "ok" if ok
            else "phase_search_range_exhausted" if range_exhausted
            else "phase_certification_failed"
        ),
        "plane": plane,
        "offset_cells": list(offset_cells),
        "offset_layout_dots": offset_layout,
        "offset_source_dots": [
            float(offset_layout[0] * candidate.grid_dpi[0] / BASE_DPI),
            float(offset_layout[1] * candidate.grid_dpi[1] / BASE_DPI),
        ],
        "search_mode": search_mode,
        "seed_cells": None if seed_cells is None else list(seed_cells),
        "wide_fallback_reason": fallback_reason,
        "search_range_exhausted": range_exhausted,
        "search_candidate_count": int(selected["n_candidates"]),
        "search_visible_candidate_count": int(
            selected["n_visible_candidates"]
        ),
        "fit_score": float(selected["score"]),
        "fit_correlation": fit_metrics["correlation"],
        "fit_density_separation": fit_metrics["density_separation"],
        "fit_threshold": threshold,
        "fit_threshold_error_rate": (
            None if multilevel else fit_metrics["error_rate"]
        ),
        "fit_linear_intercept": (
            None if centroids is None else float(centroids[0])
        ),
        "fit_linear_slope": (
            None
            if centroids is None
            else float(centroids[-1] - centroids[0])
        ),
        "fit_level_density_centroids": (
            None if centroids is None else centroids.tolist()
        ),
        "fit_lock": lock,
        "certify_error_rate": certify_metrics["error_rate"],
        "certify_correlation": certify_metrics["correlation"],
        "certify_density_separation": certify_metrics[
            "density_separation"
        ],
        "n_fit": int(len(fit)),
        "n_certify": int(len(certify)),
    }

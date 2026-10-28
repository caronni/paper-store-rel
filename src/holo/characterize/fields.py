"""Per-window field measurement over certified local pose."""
from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

import numpy as np

from .geometry import (
    GeometryError,
    OutOfRasterError,
    layout_footprint_visibility,
)
from .model import Candidate
from .patterns import field_states
from .raster import RasterSource
from .statistics import (
    ROLE_CERTIFY,
    ROLE_FIT,
    ROLE_REPORT,
    ROLE_TRAIN,
    confusion_matrix,
    error_interval,
    fit_qda,
    generalized_mutual_information,
    mutual_information,
    overdispersion,
    split_roles,
    tier_for_error,
    validate_split,
)
from .sampling import (
    MAX_MODEL_POINTS_PER_ROLE,
    MIN_SAMPLES_PER_CELL,
    WINDOW_TARGET_MM,
    _candidate,
    _cell_geometry,
    _field_key,
    _membership,
    _sample_plane,
    _samples_per_cell,
    _take_bounded,
)
from .phase import (
    _phase_fit,
    _phase_support,
)


def _partition_edges(length: int, count: int) -> tuple[int, ...]:
    quotient, remainder = divmod(length, count)
    edges = [0]
    for index in range(count):
        edges.append(
            edges[-1] + quotient + (1 if index < remainder else 0)
        )
    return tuple(edges)


def _window_specs(
    nx: int,
    ny: int,
    candidate: Candidate,
    *,
    roles: np.ndarray | None = None,
    states: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    target_x = max(
        1, int(math.floor(WINDOW_TARGET_MM / candidate.pitch_mm[0]))
    )
    target_y = max(
        1, int(math.floor(WINDOW_TARGET_MM / candidate.pitch_mm[1]))
    )
    initial_x = max(1, int(math.ceil(nx / target_x)))
    initial_y = max(1, int(math.ceil(ny / target_y)))

    def bounds_for(
        count_x: int,
        count_y: int,
    ) -> list[tuple[int, int, int, int, int, int]]:
        x_edges = _partition_edges(nx, count_x)
        y_edges = _partition_edges(ny, count_y)
        return [
            (row, col, y0, y1, x0, x1)
            for row, (y0, y1) in enumerate(
                zip(y_edges[:-1], y_edges[1:], strict=True)
            )
            for col, (x0, x1) in enumerate(
                zip(x_edges[:-1], x_edges[1:], strict=True)
            )
        ]

    def supported(
        bounds: list[tuple[int, int, int, int, int, int]],
    ) -> int:
        if roles is None or states is None:
            dimension = max(1, len(candidate.planes))
            required = max(
                96,
                4 * candidate.n_states * (dimension + 3),
            )
            return sum(
                (y1 - y0) * (x1 - x0) < required
                for _row, _col, y0, y1, x0, x1 in bounds
            )
        failures = 0
        for _row, _col, y0, y1, x0, x1 in bounds:
            local_roles = roles[y0:y1, x0:x1]
            local_states = states[y0:y1, x0:x1]
            counts = np.bincount(local_roles.ravel(), minlength=4)
            if (
                counts[ROLE_FIT] < 24
                or counts[ROLE_CERTIFY] < 24
                or counts[ROLE_TRAIN] == 0
                or counts[ROLE_REPORT] == 0
            ):
                failures += 1
                continue
            train_support = np.bincount(
                local_states[local_roles == ROLE_TRAIN].astype(np.int64),
                minlength=candidate.n_states,
            )
            report_support = np.bincount(
                local_states[local_roles == ROLE_REPORT].astype(np.int64),
                minlength=candidate.n_states,
            )
            if (
                np.any(train_support <= len(candidate.planes) + 2)
                or np.any(report_support == 0)
            ):
                failures += 1
                continue
            for plane in candidate.planes:
                if candidate.symbol_shape.startswith("nested-"):
                    fit_expected = (
                        local_states[local_roles == ROLE_FIT].astype(
                            np.float64
                        )
                        / (candidate.n_states - 1)
                    )
                    certify_expected = (
                        local_states[local_roles == ROLE_CERTIFY].astype(
                            np.float64
                        )
                        / (candidate.n_states - 1)
                    )
                else:
                    fit_expected = _membership(
                        local_states[local_roles == ROLE_FIT],
                        candidate,
                        plane,
                    )
                    certify_expected = _membership(
                        local_states[local_roles == ROLE_CERTIFY],
                        candidate,
                        plane,
                    )
                if (
                    not _phase_support(fit_expected, candidate)
                    or not _phase_support(certify_expected, candidate)
                ):
                    failures += 1
                    break
        return failures

    count_x, count_y = initial_x, initial_y
    current = bounds_for(count_x, count_y)
    while supported(current) and (count_x > 1 or count_y > 1):
        alternatives = []
        if count_x > 1:
            candidate_bounds = bounds_for(count_x - 1, count_y)
            alternatives.append((
                supported(candidate_bounds),
                max(
                    (x1 - x0) * candidate.pitch_mm[0]
                    for _r, _c, _y0, _y1, x0, x1 in candidate_bounds
                ),
                0,
                count_x - 1,
                count_y,
                candidate_bounds,
            ))
        if count_y > 1:
            candidate_bounds = bounds_for(count_x, count_y - 1)
            alternatives.append((
                supported(candidate_bounds),
                max(
                    (y1 - y0) * candidate.pitch_mm[1]
                    for _r, _c, y0, y1, _x0, _x1 in candidate_bounds
                ),
                1,
                count_x,
                count_y - 1,
                candidate_bounds,
            ))
        _failures, _span, _axis, count_x, count_y, current = min(
            alternatives,
            key=lambda row: (row[0], row[1], row[2]),
        )

    expanded = count_x < initial_x or count_y < initial_y
    specs = []
    for index, (row, col, y0, y1, x0, x1) in enumerate(current):
        specs.append({
            "index": index,
            "grid_position": [row, col],
            "bounds_yx_cells": [y0, y1, x0, x1],
            "span_mm": [
                (x1 - x0) * candidate.pitch_mm[0],
                (y1 - y0) * candidate.pitch_mm[1],
            ],
            "target_mm": WINDOW_TARGET_MM,
            "expanded_for_support": expanded,
        })
    return specs


def _measure_window(
    source: RasterSource,
    affine: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    states: np.ndarray,
    roles: np.ndarray,
    window: np.ndarray,
    candidate: Candidate,
    pitch_x: float,
    pitch_y: float,
    window_index: int,
    *,
    window_spec: dict[str, Any] | None = None,
    phase_seeds: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    record = {
        "window": window_index,
        **(
            {}
            if window_spec is None
            else {
                "grid_position": window_spec["grid_position"],
                "bounds_yx_cells": window_spec["bounds_yx_cells"],
                "span_mm": window_spec["span_mm"],
                "target_mm": window_spec["target_mm"],
                "expanded_for_support": window_spec[
                    "expanded_for_support"
                ],
            }
        ),
    }
    phases: dict[str, dict[str, Any]] = {}
    try:
        for plane in candidate.planes:
            phases[plane] = _phase_fit(
                source, affine, x, y, states, roles, window, candidate,
                plane, pitch_x, pitch_y,
                seed_cells=(
                    None
                    if phase_seeds is None
                    else phase_seeds.get(plane)
                ),
            )
    except OutOfRasterError as exc:
        return {
            **record,
            "status": "unobservable",
            "reason": str(exc),
        }
    failed = [plane for plane, result in phases.items() if not result["ok"]]
    if failed:
        return {
            **record,
            "status": "geometry_uncertified",
            "failed_planes": failed,
            "phase": phases,
        }

    train = np.flatnonzero(window.ravel() & (roles.ravel() == ROLE_TRAIN))
    report = np.flatnonzero(window.ravel() & (roles.ravel() == ROLE_REPORT))
    train = _take_bounded(train, MAX_MODEL_POINTS_PER_ROLE)
    report = _take_bounded(report, MAX_MODEL_POINTS_PER_ROLE)
    if not len(train) or not len(report):
        return {
            **record,
            "status": "insufficient_model_support",
            "phase": phases,
        }

    def features(indices: np.ndarray) -> np.ndarray:
        columns = []
        for plane in candidate.planes:
            shift_x, shift_y = phases[plane]["offset_layout_dots"]
            columns.append(_sample_plane(
                source, affine,
                x.ravel()[indices] + shift_x,
                y.ravel()[indices] + shift_y,
                plane=plane, candidate=candidate,
                pitch_x=pitch_x, pitch_y=pitch_y,
            ))
        return np.stack(columns, axis=1).astype(np.float32)

    train_labels = states.ravel()[train].astype(np.int64)
    report_labels = states.ravel()[report].astype(np.int64)
    try:
        train_features = features(train)
        model = fit_qda(
            train_features, train_labels, candidate.n_states
        )
        report_features = features(report)
    except (ValueError, GeometryError, np.linalg.LinAlgError) as exc:
        return {
            **record,
            "status": "insufficient_model_support",
            "reason": str(exc),
            "phase": phases,
            "train_state_counts": np.bincount(
                train_labels, minlength=candidate.n_states
            ).tolist(),
        }
    scores = model.scores(report_features)
    predicted = np.argmax(scores, axis=1)
    confusion = confusion_matrix(
        report_labels, predicted, candidate.n_states
    )
    errors = predicted != report_labels
    error_rate = float(np.mean(errors))
    lower, upper = error_interval(int(errors.sum()), len(errors))
    class_errors = []
    for state in range(candidate.n_states):
        selected = report_labels == state
        class_errors.append(
            None if not np.any(selected)
            else float(np.mean(errors[selected]))
        )
    soft_gmi = generalized_mutual_information(
        scores - model.log_priors[None, :],
        report_labels,
    )
    return {
        **record,
        "status": "ok",
        "phase": phases,
        "n_train": int(len(train)),
        "n_report": int(len(report)),
        "errors": int(errors.sum()),
        "train_state_counts": np.bincount(
            train_labels, minlength=candidate.n_states
        ).tolist(),
        "report_state_counts": np.bincount(
            report_labels, minlength=candidate.n_states
        ).tolist(),
        "confusion": confusion.tolist(),
        "class_error_rates": class_errors,
        "error_rate": error_rate,
        "error_wilson_95": [lower, upper],
        "mutual_information_bits_per_cell": mutual_information(confusion),
        "soft_score_gmi": soft_gmi,
        "generalized_mutual_information_bits_per_cell": soft_gmi[
            "bits_per_cell"
        ],
        "tier": tier_for_error(error_rate),
    }


def measure_field(
    source: RasterSource,
    affine: np.ndarray,
    field: dict[str, Any],
) -> dict[str, Any]:
    """Measure one known-state field with four disjoint populations."""

    candidate = _candidate(int(field["candidate_code"]))
    visible, visible_fraction = layout_footprint_visibility(
        source, affine, field
    )
    base: dict[str, Any] = {
        "field_id": field["field_id"],
        "candidate_code": candidate.code,
        "candidate_id": candidate.candidate_id,
        "family": field.get("family"),
        "role": field.get("role"),
        "position": field.get("position"),
        "visible": visible,
        "visible_vertex_fraction": visible_fraction,
    }
    for key in ("edge", "gap_mm", "gap_index"):
        if key in field:
            base[key] = field[key]
    if not visible:
        return {**base, "status": "unobservable"}

    states = field_states(field, candidate)
    expected_hash = hashlib.sha256(states.tobytes()).hexdigest()
    if expected_hash != field.get("state_sha256"):
        return {
            **base,
            "status": "refused",
            "reason": "field ground-truth digest mismatch",
        }
    roles = split_roles(
        int(field["nx"]), int(field["ny"]),
        field_key=_field_key(str(field["field_id"])),
    )
    split = validate_split(roles, states, candidate.n_states)
    x, y, pitch_x, pitch_y = _cell_geometry(field, candidate)
    sampling = _samples_per_cell(affine, pitch_x, pitch_y)
    base.update({
        "grid_dpi": list(candidate.grid_dpi),
        "cell_dots": list(candidate.cell_dots),
        "cell_pitch_mm": list(candidate.pitch_mm),
        "cells_per_mm2": candidate.cells_per_mm2,
        "alphabet": candidate.alphabet,
        "emission_path": candidate.emission_path,
        "samples_per_cell": sampling,
        "statistical_split": split,
    })
    if sampling["area"] < MIN_SAMPLES_PER_CELL:
        return {
            **base,
            "status": "unmeasurable",
            "reason": (
                f"{sampling['area']:.3f} measured pixel samples/cell; "
                f"need {MIN_SAMPLES_PER_CELL:g}"
            ),
            "tier": "unmeasurable",
        }

    specs = _window_specs(
        int(field["nx"]),
        int(field["ny"]),
        candidate,
        roles=roles,
        states=states,
    )
    certified_phase: dict[
        tuple[int, int, str], tuple[float, float]
    ] = {}
    results = []
    for spec in specs:
        row, col = (int(value) for value in spec["grid_position"])
        seeds: dict[str, tuple[float, float]] = {}
        for plane in candidate.planes:
            seed = certified_phase.get((row, col - 1, plane))
            if seed is None:
                seed = certified_phase.get((row - 1, col, plane))
            if seed is not None:
                seeds[plane] = seed
        y0, y1, x0, x1 = (
            int(value) for value in spec["bounds_yx_cells"]
        )
        window = np.zeros(states.shape, dtype=bool)
        window[y0:y1, x0:x1] = True
        result = _measure_window(
            source,
            affine,
            x,
            y,
            states,
            roles,
            window,
            candidate,
            pitch_x,
            pitch_y,
            int(spec["index"]),
            window_spec=spec,
            phase_seeds=seeds,
        )
        results.append(result)
        for plane, phase in result.get("phase", {}).items():
            if phase.get("ok"):
                certified_phase[(row, col, plane)] = tuple(
                    float(value) for value in phase["offset_cells"]
                )
    passed = [row for row in results if row["status"] == "ok"]
    if len(passed) != len(results):
        return {
            **base,
            "status": "geometry_uncertified",
            "n_windows_expected": len(results),
            "n_windows_ok": len(passed),
            "windows": results,
            "tier": "unmeasurable",
        }

    confusion = sum(
        (
            np.asarray(row["confusion"], dtype=np.int64)
            for row in passed
        ),
        start=np.zeros((candidate.n_states, candidate.n_states), np.int64),
    )
    errors = int(confusion.sum() - np.trace(confusion))
    total = int(confusion.sum())
    error_rate = errors / total
    lower, upper = error_interval(errors, total)
    window_errors = np.asarray(
        [row["error_rate"] for row in passed], dtype=np.float64
    )
    window_uppers = np.asarray(
        [row["error_wilson_95"][1] for row in passed],
        dtype=np.float64,
    )
    outcomes = np.concatenate([
        np.concatenate((
            np.ones(int(row["errors"]), dtype=bool),
            np.zeros(
                int(row["n_report"]) - int(row["errors"]), dtype=bool
            ),
        ))
        for row in passed
    ])
    block_ids = np.concatenate([
        np.full(int(row["n_report"]), index, dtype=np.int64)
        for index, row in enumerate(passed)
    ])
    dispersion = {
        **overdispersion(outcomes, block_ids, error_rate),
        "error_rate_stddev": (
            float(np.std(window_errors, ddof=1))
            if len(window_errors) > 1 else 0.0
        ),
        "worst_window_error_rate": float(np.max(window_errors)),
        "worst_window_error_rate_index": int(np.argmax(window_errors)),
        "worst_window_wilson_upper_95": float(np.max(window_uppers)),
        "worst_window_wilson_upper_95_index": int(
            np.argmax(window_uppers)
        ),
    }
    weighted_gmi = sum(
        float(row["generalized_mutual_information_bits_per_cell"])
        * int(row["n_report"])
        for row in passed
    ) / total
    return {
        **base,
        "status": "ok",
        "n_windows_expected": len(results),
        "n_windows_ok": len(passed),
        "windows": results,
        "confusion": confusion.tolist(),
        "n_report": total,
        "errors": errors,
        "error_rate": error_rate,
        "error_wilson_95": [lower, upper],
        "mutual_information_bits_per_cell": mutual_information(confusion),
        "generalized_mutual_information_bits_per_cell": weighted_gmi,
        "minimum_window_generalized_mutual_information_bits_per_cell": min(
            float(row[
                "generalized_mutual_information_bits_per_cell"
            ])
            for row in passed
        ),
        "empirical_information_bits_per_mm2": (
            mutual_information(confusion) * candidate.cells_per_mm2
        ),
        "soft_score_information_bits_per_mm2": (
            weighted_gmi * candidate.cells_per_mm2
        ),
        "raw_alphabet_bits_per_mm2": (
            candidate.alphabet_bits * candidate.cells_per_mm2
        ),
        "tier": tier_for_error(error_rate),
        "window_dispersion": dispersion,
    }


def measure_all_fields(
    source: RasterSource,
    affine: np.ndarray,
    fields: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [measure_field(source, affine, field) for field in fields]

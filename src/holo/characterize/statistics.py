"""Small statistical primitives for held-out channel metrology."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


ROLE_FIT = 0
ROLE_CERTIFY = 1
ROLE_TRAIN = 2
ROLE_REPORT = 3


def extremum(rows, key, fn):
    """One worst/best reduction under the strict unknown-policy.

    With no rows, or any row missing the value, the answer is not
    knowable -> None (user ruling 2026-07-30: unmeasurability correlates
    with badness, so silently dropping a row is anti-conservative; the
    consumer decides what an unknowable worst case refuses).
    """
    values = [key(row) for row in rows]
    if not values or any(value is None for value in values):
        return None
    return fn(float(value) for value in values)


def _mix64(values: np.ndarray) -> np.ndarray:
    """SplitMix64 finalizer, vectorized with intentional uint overflow."""
    out = values.astype(np.uint64, copy=True)
    with np.errstate(over="ignore"):
        out ^= out >> np.uint64(30)
        out *= np.uint64(0xBF58476D1CE4E5B9)
        out ^= out >> np.uint64(27)
        out *= np.uint64(0x94D049BB133111EB)
        out ^= out >> np.uint64(31)
    return out


def split_roles(nx: int, ny: int, *, field_key: int) -> np.ndarray:
    """Return a spatially mixed, exhaustive four-way role assignment.

    Row/column coordinates both affect high and low hash bits. This avoids the
    axis-aligned comb produced by flat-index modulo splits.
    """
    if nx <= 0 or ny <= 0:
        raise ValueError("field dimensions must be positive")
    yy, xx = np.indices((ny, nx), dtype=np.uint64)
    with np.errstate(over="ignore"):
        raw = (
            xx * np.uint64(0x9E3779B185EBCA87)
            ^ yy * np.uint64(0xC2B2AE3D27D4EB4F)
            ^ np.uint64(field_key & ((1 << 64) - 1))
        )
    roles = (_mix64(raw) & np.uint64(3)).astype(np.uint8)
    return roles


def validate_split(roles: np.ndarray, states: np.ndarray,
                   n_states: int) -> dict[str, Any]:
    if roles.shape != states.shape:
        raise ValueError("roles and states must have the same shape")
    counts = np.bincount(roles.ravel(), minlength=4)
    if np.any(counts == 0):
        raise ValueError(f"empty statistical role: {counts.tolist()}")
    support = np.zeros((4, n_states), np.int64)
    for role in range(4):
        support[role] = np.bincount(
            states[roles == role].astype(np.int64), minlength=n_states
        )
    row_roles = np.array([
        len(np.unique(row)) for row in roles
    ])
    col_roles = np.array([
        len(np.unique(column)) for column in roles.T
    ])
    return {
        "counts": counts.tolist(),
        "state_support": support.tolist(),
        "roles_complete": bool(np.all(counts > 0)),
        "state_support_complete": bool(np.all(support > 0)),
        "minimum_state_support_by_role": np.min(
            support, axis=1
        ).tolist(),
        "rows_with_all_roles_fraction": float(np.mean(row_roles == 4)),
        "columns_with_all_roles_fraction": float(np.mean(col_roles == 4)),
        "complete": bool(np.all(counts > 0) and np.all(support > 0)),
    }


def bounded_stratified_indices(
    indices: np.ndarray,
    labels: np.ndarray,
    limit: int,
) -> np.ndarray:
    """Deterministically thin indices while retaining every observed class."""

    values = np.asarray(indices, dtype=np.int64).ravel()
    groups = np.asarray(labels).ravel()
    if values.shape != groups.shape:
        raise ValueError("bounded indices and labels differ")
    if limit <= 0:
        raise ValueError("bounded-index limit must be positive")
    if len(values) <= limit:
        return values
    classes = np.unique(groups)
    if len(classes) > limit:
        raise ValueError("bounded-index limit is smaller than class count")

    selected: list[np.ndarray] = []
    remaining = int(limit)
    pools = [np.flatnonzero(groups == state) for state in classes]
    for ordinal, pool in enumerate(pools):
        classes_left = len(pools) - ordinal
        target = min(
            len(pool),
            max(1, remaining // classes_left),
        )
        positions = np.linspace(
            0, len(pool) - 1, target, dtype=np.int64
        )
        selected.append(pool[positions])
        remaining -= target
    if remaining:
        chosen = np.zeros(len(values), dtype=bool)
        chosen[np.concatenate(selected)] = True
        extra_pool = np.flatnonzero(~chosen)
        extra_positions = np.linspace(
            0, len(extra_pool) - 1, remaining, dtype=np.int64
        )
        selected.append(extra_pool[extra_positions])
    return values[np.sort(np.concatenate(selected))]


def wilson_interval(successes: int, total: int,
                    z: float = 1.959963984540054
                    ) -> tuple[float, float]:
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("invalid binomial counts")
    if total == 0:
        return 0.0, 1.0
    p = successes / total
    den = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / den
    radius = z * math.sqrt(
        p * (1.0 - p) / total + z * z / (4.0 * total * total)
    ) / den
    return max(0.0, center - radius), min(1.0, center + radius)


def error_interval(errors: int, total: int) -> tuple[float, float]:
    return wilson_interval(errors, total)


def confusion_matrix(truth: np.ndarray, predicted: np.ndarray,
                     n_states: int) -> np.ndarray:
    truth = np.asarray(truth, dtype=np.int64).ravel()
    predicted = np.asarray(predicted, dtype=np.int64).ravel()
    if truth.shape != predicted.shape:
        raise ValueError("truth/predicted shape mismatch")
    return np.bincount(
        truth * n_states + predicted,
        minlength=n_states * n_states,
    ).reshape(n_states, n_states)


def mutual_information(confusion: np.ndarray) -> float:
    counts = np.asarray(confusion, dtype=np.float64)
    total = float(counts.sum())
    if total <= 0:
        return 0.0
    joint = counts / total
    px = joint.sum(axis=1, keepdims=True)
    py = joint.sum(axis=0, keepdims=True)
    expected = px @ py
    mask = joint > 0
    return float(np.sum(joint[mask] * np.log2(joint[mask] / expected[mask])))


def generalized_mutual_information(
    log_metrics: np.ndarray,
    truth: np.ndarray,
    *,
    priors: np.ndarray | None = None,
    scales: np.ndarray | None = None,
) -> dict[str, Any]:
    """Estimate soft-score GMI for a possibly mismatched state metric.

    ``log_metrics[i, x]`` is any natural-log decoding metric for observation
    ``i`` and state ``x``.  The metric need not be a calibrated probability.
    GMI optimizes a non-negative temperature ``s`` without changing the hard
    decision.  Including ``s = 0`` makes the estimate conservatively
    non-negative even when the supplied soft scores are actively misleading.
    """

    metrics = np.asarray(log_metrics, dtype=np.float64)
    labels = np.asarray(truth, dtype=np.int64).ravel()
    if metrics.ndim != 2 or len(metrics) != len(labels) or not len(labels):
        raise ValueError("GMI inputs must be nonempty (n,k) and (n,)")
    n_states = int(metrics.shape[1])
    if n_states < 2 or np.any(labels < 0) or np.any(labels >= n_states):
        raise ValueError("GMI labels are outside the score alphabet")
    if not np.all(np.isfinite(metrics)):
        raise ValueError("GMI metrics must be finite")

    if priors is None:
        probabilities = np.bincount(
            labels, minlength=n_states
        ).astype(np.float64)
    else:
        probabilities = np.asarray(priors, dtype=np.float64).ravel()
        if probabilities.shape != (n_states,):
            raise ValueError("GMI priors differ from the score alphabet")
        if not np.all(np.isfinite(probabilities)):
            raise ValueError("GMI priors must be finite")
    if np.any(probabilities < 0.0) or float(probabilities.sum()) <= 0.0:
        raise ValueError("GMI priors must be nonnegative with positive mass")
    probabilities /= float(probabilities.sum())
    if np.any(probabilities[labels] <= 0.0):
        raise ValueError("GMI truth contains a zero-prior state")
    log_priors = np.full(n_states, -np.inf, dtype=np.float64)
    positive = probabilities > 0.0
    log_priors[positive] = np.log(probabilities[positive])

    if scales is None:
        temperatures = np.asarray(
            (
                0.0,
                1.0 / 32.0,
                1.0 / 16.0,
                1.0 / 8.0,
                1.0 / 4.0,
                1.0 / 2.0,
                3.0 / 4.0,
                1.0,
                3.0 / 2.0,
                2.0,
                3.0,
                4.0,
                6.0,
                8.0,
                12.0,
                16.0,
                24.0,
                32.0,
            ),
            dtype=np.float64,
        )
    else:
        temperatures = np.asarray(scales, dtype=np.float64).ravel()
        if (
            not len(temperatures)
            or not np.all(np.isfinite(temperatures))
            or np.any(temperatures < 0.0)
        ):
            raise ValueError("GMI scales must be finite and nonnegative")
        if not np.any(temperatures == 0.0):
            temperatures = np.concatenate(([0.0], temperatures))
    temperatures = np.unique(temperatures)

    selected = metrics[np.arange(len(labels)), labels]
    estimates = []
    for scale in temperatures:
        weighted = scale * metrics + log_priors[None, :]
        maximum = np.max(weighted, axis=1)
        log_denominator = maximum + np.log(
            np.sum(np.exp(weighted - maximum[:, None]), axis=1)
        )
        estimates.append(float(np.mean(
            (scale * selected - log_denominator) / math.log(2.0)
        )))
    best_index = int(np.argmax(estimates))
    entropy = -float(np.sum(
        probabilities[positive] * np.log2(probabilities[positive])
    ))
    return {
        "bits_per_cell": min(
            entropy, max(0.0, float(estimates[best_index]))
        ),
        "scale": float(temperatures[best_index]),
        "input_entropy_bits": entropy,
        "n_observations": int(len(labels)),
        "state_priors": probabilities.tolist(),
    }


@dataclass(frozen=True)
class QDAModel:
    means: np.ndarray
    inverse_covariances: np.ndarray
    log_determinants: np.ndarray
    log_priors: np.ndarray

    def scores(self, features: np.ndarray) -> np.ndarray:
        values = np.asarray(features, dtype=np.float64)
        out = np.empty((len(values), len(self.means)), np.float64)
        for state in range(len(self.means)):
            delta = values - self.means[state]
            out[:, state] = -0.5 * (
                np.einsum(
                    "ij,jk,ik->i",
                    delta,
                    self.inverse_covariances[state],
                    delta,
                )
                + self.log_determinants[state]
            ) + self.log_priors[state]
        return out


def fit_qda(features: np.ndarray, labels: np.ndarray,
            n_states: int) -> QDAModel:
    values = np.asarray(features, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64).ravel()
    if values.ndim != 2 or len(values) != len(labels):
        raise ValueError("QDA inputs must be (n,d) and (n,)")
    dimension = values.shape[1]
    means = np.empty((n_states, dimension), np.float64)
    inverse = np.empty((n_states, dimension, dimension), np.float64)
    logdet = np.empty(n_states, np.float64)
    priors = np.empty(n_states, np.float64)
    for state in range(n_states):
        group = values[labels == state]
        if len(group) <= dimension + 2:
            raise ValueError(
                f"state {state} has {len(group)} training rows; "
                f"need more than {dimension + 2}"
            )
        means[state] = group.mean(axis=0)
        covariance = np.atleast_2d(np.cov(group, rowvar=False))
        if dimension == 1:
            covariance = np.array(
                [[max(float(covariance.ravel()[0]), 1e-7)]],
                dtype=np.float64,
            )
        scale = max(float(np.trace(covariance)) / dimension, 1e-7)
        covariance = covariance + np.eye(dimension) * (2e-3 * scale + 1e-7)
        sign, determinant = np.linalg.slogdet(covariance)
        if sign <= 0:
            raise ValueError(f"state {state} covariance is not positive")
        inverse[state] = np.linalg.inv(covariance)
        logdet[state] = determinant
        priors[state] = math.log(len(group) / len(values))
    return QDAModel(means, inverse, logdet, priors)


def tier_for_error(error_rate: float | None) -> str:
    if error_rate is None or not math.isfinite(error_rate):
        return "unmeasurable"
    if error_rate < 0.01:
        return "solid"
    if error_rate < 0.08:
        return "marginal"
    if error_rate < 0.20:
        return "fragile"
    return "collapsed"


def overdispersion(errors: np.ndarray, block_ids: np.ndarray,
                   expected: float) -> dict[str, Any]:
    """Pearson overdispersion over nonempty blocks."""
    errors = np.asarray(errors, dtype=bool).ravel()
    block_ids = np.asarray(block_ids, dtype=np.int64).ravel()
    if errors.shape != block_ids.shape:
        raise ValueError("errors and block ids differ")
    rows = []
    for block in np.unique(block_ids):
        selected = errors[block_ids == block]
        if len(selected) < 20:
            continue
        variance = max(expected * (1.0 - expected), 1e-9)
        rows.append((float(selected.sum()) - len(selected) * expected) ** 2
                    / (len(selected) * variance))
    dof = max(len(rows) - 1, 0)
    return {
        "n_blocks": len(rows),
        "chi2": float(sum(rows)),
        "dof": dof,
        "chi2_per_dof": (
            None if dof == 0 else float(sum(rows) / dof)
        ),
    }

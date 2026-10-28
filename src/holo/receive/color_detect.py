"""Provisional historical CMY detector numerical leaf.

This is a production-local port of the color detector implemented in
``paperholo.acquire`` for experiment E017.  Production Holo does not import
that historical package at runtime.  The deliberately retained numerical
choices are:

* reflected R/G/B cell means, in R/G/B order;
* full-covariance QDA with class covariance shrinkage toward the pooled
  within-class covariance and a trace-scaled ridge;
* flat state priors, irrespective of furniture-label frequencies;
* pooled-whitened collapsed-class guards;
* CMY8 equal-prior state marginalization followed by an in-sample,
  per-component, tie-pooled and class-balanced stack-PAVA map; and
* the explicit score-zero/probability-one-half PAVA anchor from E017.6.

CMY7 stops before marginalization: it consumes six state log scores, for
states C through MY, relative to W.  CMY8 consumes three calibrated LLRs in
C/M/Y order.  LLR sign is always ``log P(ink) - log P(no ink)``.

The image/grid adapter owns registration and cell sampling.  This module
only transforms finite sampled features and known state labels into
numerical evidence.  It does not know about tiles, addresses, scrambling,
FEC, or receiver state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.special import logsumexp

from ..core.channel import PLANE_ORDER
from .detect import readonly_array


QDA_RIDGE: Final = 1e-6
QDA_COLLAPSE_DIST: Final = 0.5
CMY8_CALIBRATION_MIN_CLASS_LABELS: Final = 6
CMY8_CALIBRATION_MIN_STATES_PER_CLASS: Final = 2
CMY8_CALIBRATION_MIN_LABELS_PER_STATE: Final = 3
DEGENERATE_LLR_CLIP: Final = 2.0
BLIND_CONFIDENT_LLR: Final = 2.0

_CMY8_STATE_BITS: Final = (
    (np.arange(8, dtype=np.uint8)[:, None]
     >> np.arange(3, dtype=np.uint8)[None, :]) & 1
).astype(bool)
_CMY8_STATE_BITS.setflags(write=False)

# Each component's two SIBLING planes, ascending.  P9 conditions a
# component's marginal on these and never on the component itself; the
# ascending order fixes which sibling the conditioning-pattern code's
# low bit names (color_calibration).
CMY8_SIBLINGS: Final = ((1, 2), (0, 2), (0, 1))


def _feature_rows(values: np.ndarray, name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[0] == 0 or result.shape[1] == 0:
        raise ValueError(f"color detect: {name} must have shape (N, D)")
    if not np.isfinite(result).all():
        raise ValueError(f"color detect: {name} must be finite")
    return result


def _states(values: np.ndarray, size: int, n_states: int,
            name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.size != size:
        raise ValueError(
            f"color detect: {name} must have shape ({size},)")
    if not np.issubdtype(raw.dtype, np.number):
        raise ValueError(f"color detect: {name} must be numeric state IDs")
    as_float = raw.astype(np.float64, copy=False)
    if (not np.isfinite(as_float).all()
            or not np.equal(as_float, np.floor(as_float)).all()):
        raise ValueError(
            f"color detect: {name} must be finite integer state IDs")
    if raw.size and (
        float(as_float.min()) < 0.0
        or float(as_float.max()) >= float(n_states)
    ):
        raise ValueError(
            f"color detect: {name} must lie in [0, {n_states - 1}]")
    return as_float.astype(np.int64)


def blind_component_bits(
    reflected_means: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Historical pinned-0.5 two-Gaussian blind component detector.

    This is the exact ``paperholo.acquire.cell_bits_blind`` numerical leaf
    used only to form registration-anchor halo templates.  Returned LLRs
    use the receiver-wide positive-is-ink sign.
    """
    means = np.asarray(reflected_means, np.float64)
    if means.size == 0 or not np.isfinite(means).all():
        raise ValueError(
            "color detect: blind component means must be finite and nonempty")
    lo, hi = np.quantile(means, (0.02, 0.98))
    normalized = (hi - means) / max(float(hi - lo), 1e-6)
    flat = normalized.ravel()
    mu = np.asarray((0.1, 0.9), np.float64)
    sigma = np.asarray((0.15, 0.15), np.float64)
    for _ in range(40):
        logp = (
            -0.5 * ((flat[:, None] - mu) / sigma) ** 2
            - np.log(sigma)
        )
        logp -= logp.max(axis=1, keepdims=True)
        responsibility = np.exp(logp)
        responsibility /= responsibility.sum(axis=1, keepdims=True)
        support = responsibility.sum(axis=0)
        updated = (
            responsibility * flat[:, None]
        ).sum(axis=0) / support
        sigma = np.sqrt((
            responsibility
            * (flat[:, None] - updated) ** 2
        ).sum(axis=0) / support)
        sigma = np.maximum(sigma, 1e-3)
        change = float(np.abs(updated - mu).max())
        mu = updated
        if change < 1e-4:
            break
    if mu[0] > mu[1]:
        mu = mu[::-1]
        sigma = sigma[::-1]
    llr = (
        -0.5 * ((normalized - mu[1]) / sigma[1]) ** 2
        - np.log(sigma[1])
    ) - (
        -0.5 * ((normalized - mu[0]) / sigma[0]) ** 2
        - np.log(sigma[0])
    )
    return (
        readonly_array(llr > 0.0, np.uint8),
        readonly_array(llr, np.float64),
    )


@dataclass(frozen=True, slots=True)
class ColorQDAModel:
    """Immutable equal-prior QDA fit for seven or eight canonical states."""

    means: np.ndarray
    cholesky: tuple[np.ndarray, ...]
    log_determinants: np.ndarray
    class_counts: np.ndarray
    warnings: tuple[str, ...]
    clipped_planes: tuple[int, ...]
    degenerate: bool

    def __post_init__(self) -> None:
        means = np.asarray(self.means, dtype=np.float64)
        if means.ndim != 2 or means.shape[0] not in (7, 8) or means.shape[1] < 1:
            raise ValueError(
                "color detect: QDA means must have shape (7|8, D)")
        if not np.isfinite(means).all():
            raise ValueError("color detect: QDA means must be finite")
        n_states, n_features = means.shape
        if len(self.cholesky) != n_states:
            raise ValueError(
                "color detect: one QDA Cholesky factor is required per state")
        factors: list[np.ndarray] = []
        for factor in self.cholesky:
            array = np.asarray(factor, dtype=np.float64)
            if array.shape != (n_features, n_features):
                raise ValueError(
                    "color detect: QDA Cholesky factor shape mismatch")
            if (not np.isfinite(array).all()
                    or np.any(np.diag(array) <= 0.0)
                    or not np.allclose(
                        array, np.tril(array), rtol=0.0, atol=0.0)):
                raise ValueError(
                    "color detect: invalid QDA Cholesky factor")
            factors.append(readonly_array(array, np.float64))
        logdet = np.asarray(self.log_determinants, dtype=np.float64)
        counts = np.asarray(self.class_counts)
        if logdet.shape != (n_states,) or not np.isfinite(logdet).all():
            raise ValueError(
                "color detect: QDA log determinants have invalid shape/value")
        if (counts.shape != (n_states,)
                or not np.issubdtype(counts.dtype, np.integer)
                or np.any(counts < 0)):
            raise ValueError("color detect: QDA class counts are invalid")
        clipped = tuple(int(value) for value in self.clipped_planes)
        if any(value not in (0, 1, 2) for value in clipped):
            raise ValueError("color detect: invalid clipped plane")
        object.__setattr__(self, "means", readonly_array(means, np.float64))
        object.__setattr__(self, "cholesky", tuple(factors))
        object.__setattr__(
            self, "log_determinants", readonly_array(logdet, np.float64))
        object.__setattr__(
            self, "class_counts", readonly_array(counts, np.int64))
        object.__setattr__(
            self, "warnings", tuple(str(value) for value in self.warnings))
        object.__setattr__(
            self, "clipped_planes", tuple(sorted(set(clipped))))
        object.__setattr__(self, "degenerate", bool(self.degenerate))

    @property
    def n_states(self) -> int:
        return int(self.means.shape[0])

    @property
    def n_features(self) -> int:
        return int(self.means.shape[1])


def fit_equal_prior_qda(
    features: np.ndarray,
    states: np.ndarray,
    *,
    n_states: int,
) -> ColorQDAModel:
    """Fit the exact historical pooled/shrunk full-covariance QDA.

    For state ``k``, with ``D`` features and ``n_k`` observations,

    ``S_k = (1-a_k) S_k,ML + a_k S_pooled + ridge``

    where ``a_k=min(1,(D+2)/n_k)``.  The pooled covariance already contains
    one ridge before it enters this expression; preserving that detail is
    required for differential parity with the E017 implementation.
    """
    if isinstance(n_states, bool) or n_states not in (7, 8):
        raise ValueError("color detect: n_states must be 7 or 8")
    x = _feature_rows(features, "features")
    y = _states(states, x.shape[0], n_states, "states")
    n, n_features = x.shape
    if n < n_states:
        raise ValueError(
            f"color detect: {n} labels cannot train {n_states} states")

    warnings: list[str] = []
    counts = np.bincount(y, minlength=n_states).astype(np.int64)
    means = np.zeros((n_states, n_features), dtype=np.float64)
    pooled_mean = x.mean(axis=0)
    for state in range(n_states):
        selected = y == state
        means[state] = (
            x[selected].mean(axis=0) if counts[state] > 0 else pooled_mean
        )

    residual = x - means[y]
    pooled = (residual.T @ residual) / max(n - n_states, 1)
    ridge = (
        QDA_RIDGE
        * max(float(np.trace(pooled)) / n_features, 1e-12)
        * np.eye(n_features)
    )
    pooled = pooled + ridge

    factors: list[np.ndarray] = []
    log_determinants = np.zeros(n_states, dtype=np.float64)
    degenerate = False
    for state in range(n_states):
        if counts[state] == 0:
            degenerate = True
            warnings.append(
                f"class {state}: 0 labels — pooled stand-in, "
                "model degenerate (LLRs clipped)"
            )
            covariance = pooled
        else:
            if counts[state] < n_features + 2:
                warnings.append(
                    f"class {state}: only {int(counts[state])} labels — "
                    "covariance fully shrunk to pooled"
                )
            centered = x[y == state] - means[state]
            maximum_likelihood = (
                centered.T @ centered
            ) / counts[state]
            shrinkage = min(
                1.0, (n_features + 2) / float(counts[state]))
            covariance = (
                (1.0 - shrinkage) * maximum_likelihood
                + shrinkage * pooled
                + ridge
            )
        factor = np.linalg.cholesky(covariance)
        factors.append(factor)
        log_determinants[state] = (
            2.0 * float(np.log(np.diag(factor)).sum())
        )

    clipped_planes: set[int] = set()
    pooled_factor = np.linalg.cholesky(pooled)
    whitened_means = np.linalg.solve(pooled_factor, means.T).T
    for left in range(n_states):
        for right in range(left + 1, n_states):
            if counts[left] == 0 or counts[right] == 0:
                continue
            threshold = QDA_COLLAPSE_DIST + float(np.sqrt(
                n_features
                * (1.0 / counts[left] + 1.0 / counts[right])
            ))
            distance = float(np.linalg.norm(
                whitened_means[left] - whitened_means[right]))
            if distance < threshold:
                differing = tuple(
                    plane for plane in range(3)
                    if ((left ^ right) >> plane) & 1
                )
                clipped_planes.update(differing)
                warnings.append(
                    f"classes {left}/{right} collapsed "
                    f"(whitened mean dist < {threshold:.2f}) — "
                    f"levels {list(differing)} clipped"
                )

    return ColorQDAModel(
        means=means,
        cholesky=tuple(factors),
        log_determinants=log_determinants,
        class_counts=counts,
        warnings=tuple(warnings),
        clipped_planes=tuple(sorted(clipped_planes)),
        degenerate=degenerate,
    )


def qda_log_scores(
    model: ColorQDAModel,
    features: np.ndarray,
) -> np.ndarray:
    """Return flat-prior state log densities, omitting only the shared term."""
    if not isinstance(model, ColorQDAModel):
        raise TypeError("color detect: model must be ColorQDAModel")
    x = _feature_rows(features, "features")
    if x.shape[1] != model.n_features:
        raise ValueError(
            "color detect: feature width does not match the QDA model")
    result = np.empty((x.shape[0], model.n_states), dtype=np.float64)
    for state in range(model.n_states):
        difference = x - model.means[state]
        whitened = np.linalg.solve(
            model.cholesky[state], difference.T)
        result[:, state] = (
            -0.5 * (whitened * whitened).sum(axis=0)
            - 0.5 * model.log_determinants[state]
        )
    return result


def cmy7_relative_scores(
    model: ColorQDAModel,
    features: np.ndarray,
) -> np.ndarray:
    """Return ``(N, 6)`` C..MY state scores relative to W.

    This is the complete CMY7 detector output.  No marginalization, PAVA,
    or per-plane clipping is applied because the exact pack7 demapper needs
    joint seven-state likelihoods.
    """
    if not isinstance(model, ColorQDAModel) or model.n_states != 7:
        raise ValueError("color detect: CMY7 requires a seven-state QDA")
    scores = qda_log_scores(model, features)
    return scores[:, 1:] - scores[:, :1]


def cmy8_sibling_allowed(
    plane: int,
    known_mask: np.ndarray,
    known_bits: np.ndarray,
) -> np.ndarray:
    """``(N, 8)`` states consistent with ``plane``'s KNOWN SIBLINGS.

    P9 (RECEIVE-DESIGN §6.2a, arm A4b).  A component's marginal may be
    restricted to the states agreeing with whatever the KnownField
    (``(N, 3)`` mask/bits) says about the OTHER two components — never
    about ``plane`` itself, whose own column is ignored here by
    construction, so a caller cannot condition a component on itself.
    No known sibling allows every state (today's 4-vs-4); one leaves
    2-vs-2, both leave 1-vs-1.
    """
    if plane not in (0, 1, 2):
        raise ValueError("color detect: CMY8 plane must be 0, 1 or 2")
    mask = np.asarray(known_mask, np.bool_)
    bits = np.asarray(known_bits)
    if mask.ndim != 2 or mask.shape[1] != 3 or bits.shape != mask.shape:
        raise ValueError(
            "color detect: KnownField arrays must have shape (N, 3)")
    allowed = np.ones((mask.shape[0], 8), np.bool_)
    for sibling in CMY8_SIBLINGS[plane]:
        hit = mask[:, sibling]
        if not np.any(hit):
            continue
        wanted = bits[:, sibling].astype(bool)
        matches = _CMY8_STATE_BITS[None, :, sibling] == wanted[:, None]
        allowed &= matches | ~hit[:, None]
    return allowed


def _masked_logsumexp(scores: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """Row-wise ``logsumexp`` over the allowed columns only."""
    return logsumexp(np.where(allowed, scores, -np.inf), axis=1)


def cmy8_plane_marginal(
    scores: np.ndarray,
    plane: int,
    allowed: np.ndarray | None = None,
) -> np.ndarray:
    """One component's equal-prior marginal LLR from ``(N, 8)`` scores.

    ``allowed is None`` is the historical whole-alphabet form, spelled
    exactly as it always was.  A supplied subset (:func:`
    cmy8_sibling_allowed`) restricts BOTH sides of the ratio; being
    defined by sibling bits alone it always retains an equal, nonzero
    count on each side, so the quotient is always finite.
    """
    one = _CMY8_STATE_BITS[:, plane]
    if allowed is None:
        return (
            logsumexp(scores[:, one], axis=1)
            - logsumexp(scores[:, ~one], axis=1)
        )
    return (
        _masked_logsumexp(scores, allowed & one[None, :])
        - _masked_logsumexp(scores, allowed & ~one[None, :])
    )


def cmy8_marginal_llrs(
    scores: np.ndarray,
    known_mask: np.ndarray | None = None,
    known_bits: np.ndarray | None = None,
) -> np.ndarray:
    """THE generic P9 head: ``(N, 8)`` scores -> ``(N, 3)`` component LLRs.

    Uncalibrated and unclipped — the pure marginalization step, the one
    place the state subset is chosen.  ``known_mask is None`` is the
    arity-0 NORMAL case, spelled as the literal historical expression, so
    an unconditioned call is bit-for-bit what the receiver always
    computed; a KnownField restricts each component's marginal to the
    states its certified siblings allow, per plane and per cell.
    """
    values = np.asarray(scores, np.float64)
    if values.ndim != 2 or values.shape[1] != 8:
        raise ValueError("color detect: CMY8 scores must have shape (N, 8)")
    result = np.empty((values.shape[0], 3), dtype=np.float64)
    for plane in range(3):
        result[:, plane] = cmy8_plane_marginal(values, plane)
    if known_mask is None:
        if known_bits is not None:
            raise ValueError(
                "color detect: KnownField bits without a mask")
        return result
    if known_bits is None:
        raise ValueError("color detect: KnownField mask without bits")
    mask = np.asarray(known_mask, np.bool_)
    if mask.shape[0] != values.shape[0]:
        raise ValueError(
            "color detect: KnownField rows must align with the scores")
    for plane in range(3):
        left, right = CMY8_SIBLINGS[plane]
        conditioned = np.flatnonzero(mask[:, left] | mask[:, right])
        if conditioned.size == 0:
            # Exact null, per row set: an unconditioned plane keeps the
            # array the historical expression just wrote.
            continue
        allowed = cmy8_sibling_allowed(
            plane, mask[conditioned], np.asarray(known_bits)[conditioned])
        result[conditioned, plane] = cmy8_plane_marginal(
            values[conditioned], plane, allowed)
    return result


def _clip_unsupported_planes(
    model: ColorQDAModel,
    values: np.ndarray,
) -> np.ndarray:
    """Apply the degenerate/collapsed-plane clip in place, and return it."""
    for plane in range(3):
        if model.degenerate or plane in model.clipped_planes:
            values[:, plane] = np.clip(
                values[:, plane], -DEGENERATE_LLR_CLIP, DEGENERATE_LLR_CLIP)
    return values


def cmy8_raw_llrs(
    model: ColorQDAModel,
    features: np.ndarray,
) -> np.ndarray:
    """Return historical equal-prior raw component LLRs, shape ``(N, 3)``."""
    if not isinstance(model, ColorQDAModel) or model.n_states != 8:
        raise ValueError("color detect: CMY8 requires an eight-state QDA")
    return _clip_unsupported_planes(
        model, cmy8_marginal_llrs(qda_log_scores(model, features)))


def cmy8_conditioned_llrs(
    model: ColorQDAModel,
    features: np.ndarray,
    known_mask: np.ndarray,
    known_bits: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(unconditioned, conditioned)`` component LLRs, ``(N, 3)``.

    Both from ONE scoring pass: A4b needs the conditioned marginal where
    a stratum's calibration exists and the unconditioned one everywhere
    else (the arity-0 majority, and a starved stratum's exact fallback).
    The first value is ``cmy8_raw_llrs`` bit-for-bit.
    """
    if not isinstance(model, ColorQDAModel) or model.n_states != 8:
        raise ValueError("color detect: CMY8 requires an eight-state QDA")
    scores = qda_log_scores(model, features)
    return (
        _clip_unsupported_planes(model, cmy8_marginal_llrs(scores)),
        _clip_unsupported_planes(
            model, cmy8_marginal_llrs(scores, known_mask, known_bits)),
    )


@dataclass(frozen=True, slots=True)
class ColorPAVAMap:
    """One in-sample, class-balanced component score-to-LLR map."""

    score_nodes: np.ndarray
    probability_nodes: np.ndarray
    n_labels: int

    def __post_init__(self) -> None:
        scores = np.asarray(self.score_nodes, dtype=np.float64)
        probabilities = np.asarray(self.probability_nodes, dtype=np.float64)
        if (scores.ndim != 1 or scores.size == 0
                or probabilities.shape != scores.shape):
            raise ValueError(
                "color detect: PAVA nodes must be equally non-empty")
        if not np.isfinite(scores).all() or not np.isfinite(
                probabilities).all():
            raise ValueError("color detect: PAVA nodes must be finite")
        if scores.size > 1 and np.any(np.diff(scores) <= 0.0):
            raise ValueError(
                "color detect: PAVA score nodes must be strictly increasing")
        if probabilities.size > 1 and np.any(
                np.diff(probabilities) < -1e-12):
            raise ValueError(
                "color detect: PAVA probabilities must be monotone")
        if (isinstance(self.n_labels, bool)
                or not isinstance(self.n_labels, (int, np.integer))
                or int(self.n_labels) < 1):
            raise ValueError(
                "color detect: PAVA n_labels must be a positive integer")
        pmin = 1.0 / (int(self.n_labels) + 2.0)
        if np.any(probabilities < pmin - 1e-15) or np.any(
                probabilities > 1.0 - pmin + 1e-15):
            raise ValueError(
                "color detect: PAVA probability exceeds its finite clamp")
        object.__setattr__(
            self, "score_nodes", readonly_array(scores, np.float64))
        object.__setattr__(
            self, "probability_nodes",
            readonly_array(probabilities, np.float64),
        )
        object.__setattr__(self, "n_labels", int(self.n_labels))

    def llrs(self, scores: np.ndarray) -> np.ndarray:
        """Apply linear-probability interpolation followed by logit."""
        values = np.asarray(scores, dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError(
                "color detect: scores presented to PAVA must be finite")
        probabilities = np.interp(
            values, self.score_nodes, self.probability_nodes)
        return np.log(probabilities / (1.0 - probabilities))


def _pava_map(scores: np.ndarray, labels: np.ndarray) -> ColorPAVAMap:
    """Fit tie-pooled, class-balanced stack-PAVA with a finite clamp.

    Equal raw scores are one indivisible observation: their class-balanced
    empirical probability is formed before isotonic regression.  This makes
    the result independent of label order inside a tie.  The two binary
    classes receive equal total weight, so an uninformative score axis maps
    to probability one half even when the dust schedule contains unequal
    class counts.
    """
    raw_scores = np.asarray(scores, dtype=np.float64).ravel()
    raw_labels = np.asarray(labels, dtype=np.float64).ravel()
    if raw_scores.size == 0 or raw_scores.size != raw_labels.size:
        raise ValueError(
            "color detect: PAVA scores/labels must be equally non-empty")
    if not np.isfinite(raw_scores).all() or not np.isfinite(
            raw_labels).all():
        raise ValueError("color detect: PAVA scores/labels must be finite")
    if not np.isin(raw_labels, (0.0, 1.0)).all():
        raise ValueError("color detect: PAVA labels must contain only 0/1")

    counts = np.bincount(raw_labels.astype(np.int64), minlength=2)
    if np.any(counts == 0):
        raise ValueError(
            "color detect: PAVA calibration requires both binary classes")

    order = np.argsort(raw_scores, kind="stable")
    sorted_scores = raw_scores[order]
    sorted_labels = raw_labels[order]
    unique_scores, starts, group_counts = np.unique(
        sorted_scores, return_index=True, return_counts=True)
    positive_counts = np.add.reduceat(sorted_labels, starts)
    negative_counts = group_counts.astype(np.float64) - positive_counts
    total_weight = float(raw_labels.size)
    positive_weights = (
        positive_counts * total_weight / (2.0 * float(counts[1]))
    )
    negative_weights = (
        negative_counts * total_weight / (2.0 * float(counts[0]))
    )
    group_weights = positive_weights + negative_weights
    group_values = positive_weights / group_weights

    values: list[float] = []
    weights: list[float] = []
    score_sums: list[float] = []
    for score, value, weight in zip(
        unique_scores, group_values, group_weights, strict=True
    ):
        values.append(float(value))
        weights.append(float(weight))
        score_sums.append(float(score) * float(weight))
        while len(values) > 1 and values[-2] >= values[-1]:
            weight = weights[-1] + weights[-2]
            values[-2] = (
                values[-1] * weights[-1]
                + values[-2] * weights[-2]
            ) / weight
            weights[-2] = weight
            score_sums[-2] += score_sums[-1]
            values.pop()
            weights.pop()
            score_sums.pop()

    score_nodes = np.empty(len(values), dtype=np.float64)
    probability_nodes = np.empty(len(values), dtype=np.float64)
    pmin = 1.0 / (sorted_scores.size + 2.0)
    for index, (value, weight, score_sum) in enumerate(zip(
        values, weights, score_sums, strict=True
    )):
        score_nodes[index] = score_sum / weight
        probability_nodes[index] = min(
            max(value, pmin), 1.0 - pmin)

    # E017.6: a two-node perfect fit must retain QDA's exact decision
    # boundary.  Without this node, asymmetric marginal-score magnitudes
    # can move the interpolated p=0.5 crossing away from score zero.
    insertion = int(np.searchsorted(score_nodes, 0.0))
    if (
        0 < insertion < score_nodes.size
        and score_nodes[insertion - 1] < 0.0 < score_nodes[insertion]
        and probability_nodes[insertion - 1] <= 0.5
        <= probability_nodes[insertion]
    ):
        score_nodes = np.insert(score_nodes, insertion, 0.0)
        probability_nodes = np.insert(
            probability_nodes, insertion, 0.5)

    return ColorPAVAMap(
        score_nodes=score_nodes,
        probability_nodes=probability_nodes,
        n_labels=int(sorted_scores.size),
    )


def fit_component_pava(
    scores: np.ndarray,
    labels: np.ndarray,
) -> ColorPAVAMap:
    """The shared component-calibration primitive, exposed for P9.

    ``fit_cmy8_detector`` fits the unconditioned per-plane maps with it;
    A4b's pattern-stratified maps (``color_calibration``) must be fitted
    by the IDENTICAL estimator or the two would not be comparable at the
    gate.  One implementation, two callers — never a second PAVA.
    """
    return _pava_map(scores, labels)


@dataclass(frozen=True, slots=True)
class CMY8ComponentCalibrationSupport:
    """Structural dust support for one binary CMY8 component map.

    Counts alone are not enough: a component needs both binary classes and
    each class must span more than one eight-state QDA population.  The
    latter prevents a nominally balanced but nuisance-color-degenerate dust
    sample from calibrating a marginal score.
    """

    class_counts: tuple[int, int]
    qualified_state_counts: tuple[int, int]
    supported: bool
    reason: str | None

    def __post_init__(self) -> None:
        class_counts = tuple(int(value) for value in self.class_counts)
        state_counts = tuple(
            int(value) for value in self.qualified_state_counts)
        if (
            len(class_counts) != 2
            or len(state_counts) != 2
            or any(value < 0 for value in class_counts + state_counts)
        ):
            raise ValueError(
                "color detect: invalid CMY8 component support counts")
        supported = bool(self.supported)
        reason = None if self.reason is None else str(self.reason)
        if supported != (reason is None):
            raise ValueError(
                "color detect: supported CMY8 component cannot have a reason")
        object.__setattr__(self, "class_counts", class_counts)
        object.__setattr__(self, "qualified_state_counts", state_counts)
        object.__setattr__(self, "supported", supported)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True, slots=True)
class CMY8CalibrationSupport:
    """Auditable structural qualification of one dust-label population."""

    n_labels: int
    state_counts: tuple[int, ...]
    components: tuple[
        CMY8ComponentCalibrationSupport,
        CMY8ComponentCalibrationSupport,
        CMY8ComponentCalibrationSupport,
    ]

    def __post_init__(self) -> None:
        if (
            isinstance(self.n_labels, bool)
            or not isinstance(self.n_labels, (int, np.integer))
            or int(self.n_labels) < 1
        ):
            raise ValueError(
                "color detect: CMY8 support needs a positive label count")
        state_counts = tuple(int(value) for value in self.state_counts)
        if (
            len(state_counts) != 8
            or any(value < 0 for value in state_counts)
            or sum(state_counts) != int(self.n_labels)
        ):
            raise ValueError(
                "color detect: invalid CMY8 calibration state counts")
        if (
            len(self.components) != 3
            or not all(
                isinstance(value, CMY8ComponentCalibrationSupport)
                for value in self.components
            )
        ):
            raise ValueError(
                "color detect: CMY8 support requires C/M/Y components")
        object.__setattr__(self, "n_labels", int(self.n_labels))
        object.__setattr__(self, "state_counts", state_counts)
        object.__setattr__(self, "components", tuple(self.components))

    @property
    def supported_planes(self) -> tuple[bool, bool, bool]:
        return tuple(
            value.supported for value in self.components
        )  # type: ignore[return-value]

    @property
    def unsupported_reasons(
        self,
    ) -> tuple[str | None, str | None, str | None]:
        return tuple(
            value.reason for value in self.components
        )  # type: ignore[return-value]


def qualify_cmy8_calibration_support(
    calibration_states: np.ndarray,
) -> CMY8CalibrationSupport:
    """Qualify dust calibration independently for C, M, and Y.

    This replaces the historical aggregate ``N >= 300`` switch.  A plane is
    supported when each of its binary classes has at least six labels and
    at least two distinct QDA states represented by three or more labels each.
    Those floors match the p120 one-tile dust contract: its 18-row base gives
    three examples of each missing state and at least six examples of both
    binary values for every component.  They are estimator-identifiability
    checks rather than an area proxy.  PAVA's existing ``1/(N+2)`` clamp
    continues to adapt maximum emitted confidence to the actual population.
    """
    raw = np.asarray(calibration_states)
    if raw.ndim != 1 or raw.size == 0:
        raise ValueError(
            "color detect: calibration_states must have shape (N,)")
    states = _states(raw, int(raw.size), 8, "calibration_states")
    counts = np.bincount(states, minlength=8)
    components: list[CMY8ComponentCalibrationSupport] = []
    for plane in range(3):
        bits = ((states >> plane) & 1).astype(np.int64)
        class_counts = np.bincount(bits, minlength=2)
        qualified_states = tuple(
            int(np.count_nonzero(
                counts[
                    _CMY8_STATE_BITS[:, plane] == bool(binary)
                ] >= CMY8_CALIBRATION_MIN_LABELS_PER_STATE
            ))
            for binary in range(2)
        )
        weak_classes = tuple(
            binary for binary in range(2)
            if int(class_counts[binary])
            < CMY8_CALIBRATION_MIN_CLASS_LABELS
        )
        weak_diversity = tuple(
            binary for binary in range(2)
            if qualified_states[binary]
            < CMY8_CALIBRATION_MIN_STATES_PER_CLASS
        )
        if weak_classes:
            reason = (
                "class_labels:"
                + ",".join(str(value) for value in weak_classes)
            )
        elif weak_diversity:
            reason = (
                "state_diversity:"
                + ",".join(str(value) for value in weak_diversity)
            )
        else:
            reason = None
        components.append(CMY8ComponentCalibrationSupport(
            class_counts=(
                int(class_counts[0]), int(class_counts[1])),
            qualified_state_counts=qualified_states,
            supported=reason is None,
            reason=reason,
        ))
    return CMY8CalibrationSupport(
        n_labels=int(states.size),
        state_counts=tuple(int(value) for value in counts),
        components=tuple(components),  # type: ignore[arg-type]
    )


def _neutral_pava_map(n_labels: int) -> ColorPAVAMap:
    """Return the exact-zero map used for an unsupported component."""
    return ColorPAVAMap(
        score_nodes=np.asarray((0.0,), np.float64),
        probability_nodes=np.asarray((0.5,), np.float64),
        n_labels=n_labels,
    )


@dataclass(frozen=True, slots=True)
class CMY8Detector:
    """An eight-state QDA and its same-score-axis C/M/Y PAVA maps."""

    qda: ColorQDAModel
    calibrations: tuple[ColorPAVAMap, ColorPAVAMap, ColorPAVAMap]
    calibration_labels: int
    calibration_support: CMY8CalibrationSupport
    pava_in_sample: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.qda, ColorQDAModel) or self.qda.n_states != 8:
            raise ValueError("color detect: CMY8 detector requires 8-state QDA")
        if len(self.calibrations) != 3 or not all(
            isinstance(value, ColorPAVAMap) for value in self.calibrations
        ):
            raise ValueError(
                "color detect: CMY8 detector requires C/M/Y PAVA maps")
        if (isinstance(self.calibration_labels, bool)
                or int(self.calibration_labels) != self.calibration_labels
                or self.calibration_labels < 1):
            raise ValueError(
                "color detect: CMY8 calibration labels must be positive")
        if any(
            value.n_labels != int(self.calibration_labels)
            for value in self.calibrations
        ):
            raise ValueError(
                "color detect: CMY8 calibration counts disagree")
        if (
            not isinstance(
                self.calibration_support, CMY8CalibrationSupport)
            or self.calibration_support.n_labels
            != int(self.calibration_labels)
        ):
            raise ValueError(
                "color detect: CMY8 calibration support disagrees")
        if self.pava_in_sample is not True:
            raise ValueError(
                "color detect: provisional CMY8 PAVA must be in-sample")
        object.__setattr__(
            self, "calibration_labels", int(self.calibration_labels))

    @property
    def supported_planes(self) -> tuple[bool, bool, bool]:
        """Effective component support after calibration and QDA guards."""
        if self.qda.degenerate:
            return (False, False, False)
        return tuple(
            supported and plane not in self.qda.clipped_planes
            for plane, supported in enumerate(
                self.calibration_support.supported_planes)
        )  # type: ignore[return-value]

    @property
    def unsupported_reasons(
        self,
    ) -> tuple[str | None, str | None, str | None]:
        """Machine-readable reason for every exact-zero component."""
        if self.qda.degenerate:
            return ("qda_degenerate",) * 3
        return tuple(
            (
                f"qda_collapsed:{PLANE_ORDER[plane]}"
                if plane in self.qda.clipped_planes
                else self.calibration_support.unsupported_reasons[plane]
            )
            for plane in range(3)
        )  # type: ignore[return-value]

    def llrs(self, features: np.ndarray) -> np.ndarray:
        """Return final calibrated C/M/Y evidence, shape ``(N, 3)``."""
        raw = cmy8_raw_llrs(self.qda, features)
        result = np.empty_like(raw)
        supported = self.supported_planes
        for plane, calibration in enumerate(self.calibrations):
            # Calibration and QDA failures are component-local erasures.
            # Never let an arbitrary raw marginal cross this boundary.
            # An unsupported plane is exactly zero — its map is never
            # consulted (result-identical: the historical path computed
            # the map and then overwrote the column with zeros).
            if not supported[plane]:
                result[:, plane] = 0.0
                continue
            result[:, plane] = calibration.llrs(raw[:, plane])
        return result


def fit_cmy8_detector(
    training_features: np.ndarray,
    training_states: np.ndarray,
    calibration_features: np.ndarray,
    calibration_states: np.ndarray,
) -> CMY8Detector:
    """Fit CMY8 QDA and in-sample, class-balanced dust PAVA.

    ``training_*`` is the complete trusted furniture population (word and
    dust). ``calibration_*`` is specifically the trusted dust population.
    It is scored by the *full* fitted QDA, and those same scores fit the
    maps.  Binary classes are balanced inside each component map; the wire
    dust schedule is unchanged.  Supplying held-out scores from another QDA
    would recreate the E017.5 scale mismatch and is intentionally impossible
    through this API.
    """
    qda = fit_equal_prior_qda(
        training_features, training_states, n_states=8)
    calibration_x = _feature_rows(
        calibration_features, "calibration_features")
    if calibration_x.shape[1] != qda.n_features:
        raise ValueError(
            "color detect: calibration feature width differs from training")
    calibration_y = _states(
        calibration_states,
        calibration_x.shape[0],
        8,
        "calibration_states",
    )
    support = qualify_cmy8_calibration_support(calibration_y)
    # A plane the QDA guard zeroes (degenerate model or clipped plane)
    # never exposes its map — ``llrs`` erases the component — so fitting
    # PAVA for it is dead work (color-upstream:10); the neutral map is
    # result-identical on every detector output.
    plane_fitted = tuple(
        support.supported_planes[plane]
        and not qda.degenerate
        and plane not in qda.clipped_planes
        for plane in range(3)
    )
    raw = (
        cmy8_raw_llrs(qda, calibration_x)
        if any(plane_fitted) else None
    )
    maps = tuple(
        (
            _pava_map(raw[:, plane], (calibration_y >> plane) & 1)
            if raw is not None and plane_fitted[plane]
            else _neutral_pava_map(int(calibration_y.size))
        )
        for plane in range(3)
    )
    return CMY8Detector(
        qda=qda,
        calibrations=maps,  # type: ignore[arg-type]
        calibration_labels=int(calibration_y.size),
        calibration_support=support,
    )

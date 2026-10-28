from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

from ..format import pilots
from ..format.identity import CMY_PLANE_ORDER, FormatRow, SiteGeometry
from ..lib import geometry, pava

QDA_RIDGE: float = 1e-6
QDA_COLLAPSE_DIST: float = 0.5
CMY8_CALIBRATION_MIN_CLASS_LABELS: int = 6
CMY8_CALIBRATION_MIN_STATES_PER_CLASS: int = 2
CMY8_CALIBRATION_MIN_LABELS_PER_STATE: int = 3
DEGENERATE_LLR_CLIP: float = 2.0
BLIND_CONFIDENT_LLR: float = 2.0

HEAD_N_OFFSETS: int = 6
HEAD_SCALE_MIN: float = 0.01
HEAD_SCALE_MAX: float = 10.0
HEAD_MAX_ITERATIONS: int = 50
HEAD_GRAD_TOL: float = 1e-10
HEAD_DAMPING: float = 1e-12
HEAD_LINE_SEARCH_STEPS: int = 40
HEAD_MIN_SEARCH_PER_STATE: int = 10
HEAD_MIN_VALIDATION: int = 40
HEAD_MIN_VALIDATION_PER_STATE: int = 3
HEAD_GATE_SLACK: float = 1e-9

_CMY8_STATE_BITS: np.ndarray = (
    (np.arange(8, dtype=np.uint8)[:, None]
     >> np.arange(3, dtype=np.uint8)[None, :]) & 1
).astype(bool)


def blind_component_bits(
    reflected_means: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    means = np.asarray(reflected_means, np.float64)
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
    return (llr > 0.0).astype(np.uint8), llr


@dataclass(frozen=True)
class QdaModel:
    means: np.ndarray
    cholesky: tuple[np.ndarray, ...]
    log_determinants: np.ndarray
    class_counts: np.ndarray
    clipped_planes: tuple[int, ...]
    degenerate: bool

    @property
    def n_states(self) -> int:
        return int(self.means.shape[0])

    @property
    def n_features(self) -> int:
        return int(self.means.shape[1])


def fit_qda(features: np.ndarray, states: np.ndarray,
            n_states: int) -> QdaModel:
    x = np.asarray(features, np.float64)
    y = np.asarray(states, np.int64)
    n, n_features = x.shape
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
            covariance = pooled
        else:
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
                clipped_planes.update(
                    plane for plane in range(3)
                    if ((left ^ right) >> plane) & 1
                )
    return QdaModel(
        means=means,
        cholesky=tuple(factors),
        log_determinants=log_determinants,
        class_counts=counts,
        clipped_planes=tuple(sorted(clipped_planes)),
        degenerate=degenerate,
    )


def qda_log_scores(model: QdaModel, features: np.ndarray) -> np.ndarray:
    x = np.asarray(features, np.float64)
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


def cmy7_relative_scores(model: QdaModel,
                         features: np.ndarray) -> np.ndarray:
    scores = qda_log_scores(model, features)
    return scores[:, 1:] - scores[:, :1]


def cmy8_marginal_llrs(scores: np.ndarray) -> np.ndarray:
    values = np.asarray(scores, np.float64)
    result = np.empty((values.shape[0], 3), dtype=np.float64)
    for plane in range(3):
        one = _CMY8_STATE_BITS[:, plane]
        result[:, plane] = (
            logsumexp(values[:, one], axis=1)
            - logsumexp(values[:, ~one], axis=1)
        )
    return result


def clip_unsupported_planes(model: QdaModel,
                            values: np.ndarray) -> np.ndarray:
    for plane in range(3):
        if model.degenerate or plane in model.clipped_planes:
            values[:, plane] = np.clip(
                values[:, plane], -DEGENERATE_LLR_CLIP, DEGENERATE_LLR_CLIP)
    return values


def cmy8_raw_llrs(model: QdaModel, features: np.ndarray) -> np.ndarray:
    return clip_unsupported_planes(
        model, cmy8_marginal_llrs(qda_log_scores(model, features)))


@dataclass(frozen=True)
class PavaMap:
    score_nodes: np.ndarray
    probability_nodes: np.ndarray
    n_labels: int

    def llrs(self, scores: np.ndarray) -> np.ndarray:
        probabilities = np.interp(
            np.asarray(scores, dtype=np.float64),
            self.score_nodes, self.probability_nodes)
        return np.log(probabilities / (1.0 - probabilities))


def fit_component_pava(scores: np.ndarray,
                       labels: np.ndarray) -> PavaMap:
    raw_scores = np.asarray(scores, dtype=np.float64).ravel()
    raw_labels = np.asarray(labels, dtype=np.float64).ravel()
    counts = np.bincount(raw_labels.astype(np.int64), minlength=2)
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
        unique_scores, group_values, group_weights
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
        values, weights, score_sums
    )):
        score_nodes[index] = score_sum / weight
        probability_nodes[index] = min(
            max(value, pmin), 1.0 - pmin)
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
    return PavaMap(
        score_nodes=score_nodes,
        probability_nodes=probability_nodes,
        n_labels=int(sorted_scores.size),
    )


def neutral_pava_map(n_labels: int) -> PavaMap:
    return PavaMap(
        score_nodes=np.asarray((0.0,), np.float64),
        probability_nodes=np.asarray((0.5,), np.float64),
        n_labels=n_labels,
    )


def qualify_cmy8_support(
    calibration_states: np.ndarray,
) -> tuple[tuple[bool, bool, bool],
           tuple[str | None, str | None, str | None]]:
    states = np.asarray(calibration_states, np.int64)
    counts = np.bincount(states, minlength=8)
    supported: list[bool] = []
    reasons: list[str | None] = []
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
            reason: str | None = (
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
        supported.append(reason is None)
        reasons.append(reason)
    return (
        (supported[0], supported[1], supported[2]),
        (reasons[0], reasons[1], reasons[2]),
    )


@dataclass(frozen=True)
class Cmy8Detector:
    qda: QdaModel
    calibrations: tuple[PavaMap, PavaMap, PavaMap]
    calibration_labels: int
    supported_planes: tuple[bool, bool, bool]
    unsupported_reasons: tuple[str | None, str | None, str | None]

    def llrs(self, features: np.ndarray) -> np.ndarray:
        raw = cmy8_raw_llrs(self.qda, features)
        result = np.empty_like(raw)
        for plane, calibration in enumerate(self.calibrations):
            if not self.supported_planes[plane]:
                result[:, plane] = 0.0
                continue
            result[:, plane] = calibration.llrs(raw[:, plane])
        return result


def fit_cmy8_detector(
    training_features: np.ndarray,
    training_states: np.ndarray,
    calibration_features: np.ndarray,
    calibration_states: np.ndarray,
) -> Cmy8Detector:
    qda = fit_qda(training_features, training_states, 8)
    calibration_x = np.asarray(calibration_features, np.float64)
    calibration_y = np.asarray(calibration_states, np.int64)
    support, support_reasons = qualify_cmy8_support(calibration_y)
    plane_fitted = (
        support[0] and not qda.degenerate and 0 not in qda.clipped_planes,
        support[1] and not qda.degenerate and 1 not in qda.clipped_planes,
        support[2] and not qda.degenerate and 2 not in qda.clipped_planes,
    )
    raw = (
        cmy8_raw_llrs(qda, calibration_x)
        if any(plane_fitted) else None
    )
    maps = tuple(
        (
            fit_component_pava(
                raw[:, plane], (calibration_y >> plane) & 1)
            if raw is not None and plane_fitted[plane]
            else neutral_pava_map(int(calibration_y.size))
        )
        for plane in range(3)
    )
    if qda.degenerate:
        reasons: tuple[str | None, str | None, str | None] = (
            "qda_degenerate", "qda_degenerate", "qda_degenerate")
    else:
        detector_reasons = [
            (
                f"qda_collapsed:{CMY_PLANE_ORDER[plane]}"
                if plane in qda.clipped_planes
                else support_reasons[plane]
            )
            for plane in range(3)
        ]
        reasons = (
            detector_reasons[0], detector_reasons[1], detector_reasons[2])
    return Cmy8Detector(
        qda=qda,
        calibrations=(maps[0], maps[1], maps[2]),
        calibration_labels=int(calibration_y.size),
        supported_planes=plane_fitted,
        unsupported_reasons=reasons,
    )


@dataclass(frozen=True)
class Cmy7Head:
    scale: float
    offsets: np.ndarray

    def apply(self, scores: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, np.float64)
        return self.scale * values + self.offsets


def _logits(scores: np.ndarray, scale: float,
            offsets: np.ndarray) -> np.ndarray:
    return scale * scores + offsets


def _log_partition(logits: np.ndarray) -> np.ndarray:
    shift = np.maximum(0.0, np.max(logits, axis=1))
    return shift + np.log(
        np.exp(-shift) + np.sum(np.exp(logits - shift[:, None]), axis=1))


def _mean_nll(scores: np.ndarray, states: np.ndarray, scale: float,
              offsets: np.ndarray, weights: np.ndarray) -> float:
    logits = _logits(scores, scale, offsets)
    rows = np.arange(states.size)
    chosen = np.where(states == 0, 0.0, logits[rows, states - 1])
    row_loss = _log_partition(logits) - chosen
    return float(np.sum(weights * row_loss) / weights.sum())


def _objective(
    scores: np.ndarray, states: np.ndarray, scale: float,
    offsets: np.ndarray, weights: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    total = float(weights.sum())
    logits = _logits(scores, scale, offsets)
    log_z = _log_partition(logits)
    rows = np.arange(states.size)
    chosen = np.where(states == 0, 0.0, logits[rows, states - 1])
    value = float(np.sum(weights * (log_z - chosen)) / total)
    probabilities = np.exp(logits - log_z[:, None])
    residual = probabilities.copy()
    printed = states > 0
    residual[rows[printed], states[printed] - 1] -= 1.0
    residual *= weights[:, None]
    gradient = np.empty(1 + HEAD_N_OFFSETS, np.float64)
    gradient[0] = float(np.sum(residual * scores)) / total
    gradient[1:] = residual.sum(axis=0) / total
    scaled = probabilities * weights[:, None]
    weighted = scaled * scores
    projection = (probabilities * scores).sum(axis=1)
    hessian = np.empty(
        (1 + HEAD_N_OFFSETS, 1 + HEAD_N_OFFSETS), np.float64)
    hessian[0, 0] = float(np.sum(
        np.sum(scaled * scores * scores, axis=1)
        - weights * projection * projection)) / total
    cross = (weighted - projection[:, None] * scaled).sum(axis=0) / total
    hessian[0, 1:] = cross
    hessian[1:, 0] = cross
    hessian[1:, 1:] = (
        np.diag(scaled.sum(axis=0))
        - probabilities.T @ scaled) / total
    return value, gradient, hessian


def _projected_gradient_norm(scale: float, gradient: np.ndarray) -> float:
    active = gradient.copy()
    if scale <= HEAD_SCALE_MIN and active[0] > 0.0:
        active[0] = 0.0
    if scale >= HEAD_SCALE_MAX and active[0] < 0.0:
        active[0] = 0.0
    return float(np.max(np.abs(active)))


def _newton(scores: np.ndarray, states: np.ndarray,
            weights: np.ndarray) -> tuple[float, np.ndarray, int]:
    scale = 1.0
    offsets = np.zeros(HEAD_N_OFFSETS, np.float64)
    value, gradient, hessian = _objective(
        scores, states, scale, offsets, weights)
    iterations = 0
    for _ in range(HEAD_MAX_ITERATIONS):
        if _projected_gradient_norm(scale, gradient) < HEAD_GRAD_TOL:
            break
        damping = HEAD_DAMPING * max(1.0, float(np.trace(hessian)))
        eye = np.eye(1 + HEAD_N_OFFSETS)
        step: np.ndarray | None = None
        for _attempt in range(8):
            try:
                step = np.linalg.solve(hessian + damping * eye, -gradient)
            except np.linalg.LinAlgError:
                step = None
            if step is not None and np.isfinite(step).all():
                break
            damping = max(damping * 1000.0, 1e-8)
        if step is None or not np.isfinite(step).all():
            step = -gradient
        improved = False
        length = 1.0
        for _backtrack in range(HEAD_LINE_SEARCH_STEPS):
            trial_scale = min(max(
                scale + length * float(step[0]),
                HEAD_SCALE_MIN), HEAD_SCALE_MAX)
            trial_offsets = offsets + length * step[1:]
            trial = _mean_nll(
                scores, states, trial_scale, trial_offsets, weights)
            if np.isfinite(trial) and trial < value:
                scale, offsets, value = trial_scale, trial_offsets, trial
                improved = True
                break
            length *= 0.5
        iterations += 1
        if not improved:
            break
        _unused, gradient, hessian = _objective(
            scores, states, scale, offsets, weights)
    return scale, offsets, iterations


def head_sub_split(site_keys: np.ndarray) -> np.ndarray:
    keys = np.asarray(site_keys, np.int64)
    return (geometry.site_hash(keys[:, 1], keys[:, 2]) & 2) == 0


def fit_cmy7_head(
    scores: np.ndarray,
    states: np.ndarray,
    site_keys: np.ndarray,
) -> tuple[Cmy7Head | None, str]:
    values = np.asarray(scores, np.float64)
    labels = np.asarray(states, np.int64)
    fit_side = head_sub_split(site_keys)
    validation_side = ~fit_side
    states_total = HEAD_N_OFFSETS + 1
    search_counts = np.bincount(
        labels[fit_side], minlength=states_total)[:states_total]
    validation_counts = np.bincount(
        labels[validation_side], minlength=states_total)[:states_total]
    if int(search_counts.min()) < HEAD_MIN_SEARCH_PER_STATE:
        return None, "search_class_starved"
    if (int(validation_counts.sum()) < HEAD_MIN_VALIDATION
            or int(validation_counts.min())
            < HEAD_MIN_VALIDATION_PER_STATE):
        return None, "heldout_starved"
    scale, offsets, _iterations = _newton(
        values[fit_side], labels[fit_side],
        pava.class_balanced_weights(labels[fit_side]))
    head = Cmy7Head(scale, offsets)
    validation_scores = values[validation_side]
    validation_states = labels[validation_side]
    validation_weights = pava.class_balanced_weights(validation_states)
    identity = _mean_nll(
        validation_scores, validation_states, 1.0,
        np.zeros(HEAD_N_OFFSETS, np.float64), validation_weights)
    candidate = _mean_nll(
        validation_scores, validation_states, head.scale, head.offsets,
        validation_weights)
    if identity - candidate > HEAD_GATE_SLACK:
        return head, "adopted"
    return None, "validation_gate_failed"


def reference_states(
    row: FormatRow,
    site_geometry: SiteGeometry,
    page: int,
    cells_yx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    cells = np.asarray(cells_yx, np.int64)
    states = np.full(cells.shape[0], -1, np.int8)
    kinds = np.full(cells.shape[0], -1, np.int8)
    if not cells.size:
        return states, kinds
    word = site_geometry.word_cells_yx
    dust = site_geometry.extra_cells_yx
    lookup = np.full(
        (pilots.TILE_CELLS, pilots.TILE_CELLS), -1, np.int16)
    lookup[word[:, 0], word[:, 1]] = np.arange(
        pilots.N_WORD_SITES, dtype=np.int16)
    lookup[dust[:, 0], dust[:, 1]] = (
        pilots.N_WORD_SITES
        + np.arange(dust.shape[0], dtype=np.int16))
    local_y = cells[:, 0] % pilots.TILE_CELLS
    local_x = cells[:, 1] % pilots.TILE_CELLS
    index = lookup[local_y, local_x]
    known = np.flatnonzero(index >= 0)
    if known.size:
        tys = cells[known, 0] // pilots.TILE_CELLS
        txs = cells[known, 1] // pilots.TILE_CELLS
        code = tys * row.tiles_yx[1] + txs
        for tile_code in np.unique(code):
            selected = known[code == tile_code]
            ty, tx = divmod(int(tile_code), row.tiles_yx[1])
            counter = row.tile_counter(page, ty, tx)
            word_states = pilots.color_word_states(
                row.seed, (counter,))[0]
            dust_states = pilots.dust_state_values(
                row.seed, (counter,), row.dust_base_cycle, row.n_dust)[0]
            site = index[selected]
            is_word = site < pilots.N_WORD_SITES
            if np.any(is_word):
                rows = selected[is_word]
                states[rows] = word_states[site[is_word]]
                kinds[rows] = 0
            if np.any(~is_word):
                rows = selected[~is_word]
                states[rows] = dust_states[
                    site[~is_word] - pilots.N_WORD_SITES]
                kinds[rows] = 1
    return states, kinds

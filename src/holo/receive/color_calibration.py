"""P1: the CMY7 kind head — one calibrated scale+offset per region.

RECEIVE-DESIGN §6.2a, arm A4 (cmy7 half).  A4b, the CMY8 half of the
same ladder rung, is :mod:`holo.receive.color_conditioning`; the two are
fitted side by side in ``color_stack`` and neither ever runs for the
other's codec.

The CMY7 leaf emits raw
equal-prior QDA relative scores and nothing calibrates them; measured on
the e030/e032 corpus, 19% of emitted cells saturate the L∞=20 bound and
the WRONG cells sit at median |score| 18.8/20.  That is an OUT-OF-SAMPLE
overconfidence fact: the QDA separates its own training split, and its
confidence is only wrong on cells it never saw.  So the head is fitted on
the region HELD-OUT side of the standing ``(131y+17x)&1`` split, never on
the QDA's own training population.

The model is the smallest correction that can express "the detector is
too sure": one scalar scale ``a`` shared by all six relative logits plus
one offset per logit, with W's logit pinned at 0 (it is the reference the
scores are already relative to).  Seven parameters,

    s' = a * s + b,   P(state) = softmax([0, s'_1 .. s'_6])

Multinomial NLL in ``(a, b)`` is convex, so a hand-rolled damped Newton
with an exact Hessian is both sufficient and deterministic — no scipy
optimizer, no RNG, no random restarts, and the same inputs always give
the same 7 numbers.  ``a`` lives on the closed box [0.01, 10]; the search
is a projected Newton on that box.

The held-out population is split ONCE more by the next unused bit of the
standing site-key hash family (``&1`` = the QDA split, ``&2`` = here,
``&4``/``&8`` = P9's reveal field): ``cal_search`` fits, and the
disjoint ``cal_validation`` decides adoption.  Adoption requires a STRICT
validation-NLL improvement over the identity head — a head that only
reproduces ``a=1, b=0`` is refused, so a clean channel keeps today's exact
numbers.  Every refusal returns NO head, and a region with no head runs
the literal pre-P1 code path (risk R2).

Refusal reasons reuse K's vocabulary verbatim (``detect.fit_calibration``
/ ``detect.fit_context``): ``search_class_starved``, ``heldout_starved``,
``validation_gate_failed``; adoption is ``adopted``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np


# Seven parameters: one scale + six offsets (W's logit is the fixed 0
# reference the relative scores are already measured against).
HEAD_N_OFFSETS: Final = 6
# The scale's closed box.  0.01 = "the detector knows almost nothing";
# 10 = "ten times as sure as it says".  Clipping is a projection, not a
# refusal: a solution on the boundary is still a legal head.
HEAD_SCALE_MIN: Final = 0.01
HEAD_SCALE_MAX: Final = 10.0
# Newton budget.  A 7-parameter convex problem converges in well under
# ten steps; the cap only bounds pathological line searches.
HEAD_MAX_ITERATIONS: Final = 50
HEAD_GRAD_TOL: Final = 1e-10
# Levenberg damping, relative to the Hessian trace: the Hessian is PSD by
# construction but can be singular (a state absent from cal_search, a
# score column that is constant), and a singular solve must degrade to a
# gradient step, never to an exception.
HEAD_DAMPING: Final = 1e-12
HEAD_LINE_SEARCH_STEPS: Final = 40
# Floors.  Per-state search support mirrors K's CAL_MIN_PER_CLASS role;
# the validation floors are the campaign's registered pre-values.
HEAD_MIN_SEARCH_PER_STATE: Final = 10
HEAD_MIN_VALIDATION: Final = 40
HEAD_MIN_VALIDATION_PER_STATE: Final = 3
# The standing 1e-9 strict-improvement convention (color_stack,
# detect.fit_context, the §6.2a three-way gate).
HEAD_GATE_SLACK: Final = 1e-9


class Cmy7HeadError(ValueError):
    """A leak, a shape, or a label the head fitter refuses to fit on."""


@dataclass(frozen=True, slots=True)
class Cmy7Head:
    """A fitted ``s' = a*s + b`` head for one region's CMY7 scores."""

    scale: float
    offsets: np.ndarray

    def __post_init__(self) -> None:
        scale = float(self.scale)
        if not np.isfinite(scale):
            raise Cmy7HeadError("color head: scale must be finite")
        offsets = np.array(self.offsets, np.float64).ravel()
        if offsets.shape != (HEAD_N_OFFSETS,):
            raise Cmy7HeadError(
                f"color head: needs {HEAD_N_OFFSETS} offsets")
        if not np.isfinite(offsets).all():
            raise Cmy7HeadError("color head: offsets must be finite")
        offsets.flags.writeable = False
        object.__setattr__(
            self, "scale", min(max(scale, HEAD_SCALE_MIN), HEAD_SCALE_MAX))
        object.__setattr__(self, "offsets", offsets)

    @property
    def temperature(self) -> float:
        """``1/a`` — how much the raw scores are being cooled."""
        return 1.0 / self.scale

    def apply(self, scores: np.ndarray) -> np.ndarray:
        """Return ``a*scores + b``; pure, shape-preserving ``(N,6)``."""
        values = np.asarray(scores, np.float64)
        if values.ndim != 2 or values.shape[1] != HEAD_N_OFFSETS:
            raise Cmy7HeadError("color head: scores must have shape (N,6)")
        return self.scale * values + self.offsets


@dataclass(frozen=True, slots=True)
class Cmy7HeadFit:
    """One region's head decision with the counts that produced it."""

    head: Cmy7Head | None
    adopted: bool
    reason: str
    n_search: int
    n_validation: int
    search_class_counts: tuple[int, ...]
    validation_class_counts: tuple[int, ...]
    identity_validation_nll: float | None
    candidate_validation_nll: float | None
    iterations: int

    @property
    def temperature(self) -> float:
        return 1.0 if self.head is None else self.head.temperature


def class_balanced_weights(states: np.ndarray) -> np.ndarray:
    """Per-row weights that give every REPRESENTED state equal total mass.

    The CMY7 QDA is fitted equal-prior on purpose
    (``color_detect.fit_equal_prior_qda``): payload symbols are uniform by
    construction, so the detector must not carry a class prior.  The head's
    fit population is the opposite — MEASURED on the synthetic 8x8 cmy7
    field, known furniture is 45% W and 39% one dust state against a
    ~1/7-each payload field.  An unweighted multinomial NLL therefore fits
    the furniture log-prior straight into ``b`` (measured: offsets within
    0.3 of ``log(count_k / count_W)``) and makes payload evidence worse
    even while the head's own held-out loss improves.  Balancing the
    classes is what keeps the head a CALIBRATION of the scores rather than
    a re-priorization of them — the same reason the policy id has carried
    ``classbal`` since the CMY8 PAVA.

    Weights are normalized to mean 1, so a balanced population reproduces
    the unweighted objective exactly and every loss stays comparable.
    """
    labels = np.asarray(states, np.int64)
    counts = np.bincount(labels, minlength=HEAD_N_OFFSETS + 1)
    weights = np.where(counts[labels] > 0, 1.0 / counts[labels], 0.0)
    total = float(weights.sum())
    if total <= 0.0:
        return np.ones(labels.size, np.float64)
    return weights * (labels.size / total)


def _logits(scores: np.ndarray, scale: float,
            offsets: np.ndarray) -> np.ndarray:
    return scale * scores + offsets


def _log_partition(logits: np.ndarray) -> np.ndarray:
    """``log(1 + sum exp(z))`` — W's implicit 0 logit carried exactly."""
    shift = np.maximum(0.0, np.max(logits, axis=1))
    return shift + np.log(
        np.exp(-shift) + np.sum(np.exp(logits - shift[:, None]), axis=1))


def _mean_nll(scores: np.ndarray, states: np.ndarray, scale: float,
              offsets: np.ndarray, weights: np.ndarray) -> float:
    """Class-balanced multinomial NLL of ``softmax([0, a*s+b])``."""
    logits = _logits(scores, scale, offsets)
    rows = np.arange(states.size)
    chosen = np.where(states == 0, 0.0, logits[rows, states - 1])
    row_loss = _log_partition(logits) - chosen
    return float(np.sum(weights * row_loss) / weights.sum())


def _objective(
    scores: np.ndarray, states: np.ndarray, scale: float,
    offsets: np.ndarray, weights: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Weighted NLL with its exact gradient and Hessian in ``(a, b)``.

    The Hessian block algebra: with ``A_n = diag(p_n) - p_n p_n^T`` over
    the six non-W states, ``H_bb = sum w_n A_n``, ``H_ab = sum w_n A_n s_n``
    and ``H_aa = sum w_n s_n' A_n s_n`` — each computed in ``O(N)`` without
    ever materializing a per-row 6x6.  Weights are non-negative, so the
    Hessian stays PSD and the problem stays convex.
    """
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
    """Infinity norm of the box-projected gradient (KKT residual)."""
    active = gradient.copy()
    if scale <= HEAD_SCALE_MIN and active[0] > 0.0:
        active[0] = 0.0
    if scale >= HEAD_SCALE_MAX and active[0] < 0.0:
        active[0] = 0.0
    return float(np.max(np.abs(active)))


def _newton(scores: np.ndarray, states: np.ndarray,
            weights: np.ndarray) -> tuple[float, np.ndarray, int]:
    """Damped projected Newton on the convex box; returns (a, b, steps)."""
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


def _rows_overlap(left: np.ndarray, right: np.ndarray) -> bool:
    """True when two canonical ``(N,3)`` site-key sets share a row."""
    if left.shape[0] == 0 or right.shape[0] == 0:
        return False
    both = np.concatenate(
        (np.unique(left, axis=0), np.unique(right, axis=0)))
    return bool(np.unique(both, axis=0).shape[0] < both.shape[0])


def head_sub_split(site_keys: np.ndarray) -> np.ndarray:
    """The nested ``&2`` sub-split: True = cal_search, False = validation.

    ``&1`` already owns the QDA train/validation split
    (``color_fitting._deterministic_fit_split``) and ``&4``/``&8`` are
    P9's reveal field (``color_conditioning``), so ``&2`` is this arm's
    bit of the standing ``131y + 17x`` family.  Deterministic in the
    printed geometry alone:
    it never looks at a feature, a score, or a label.
    """
    keys = np.asarray(site_keys, np.int64)
    return ((131 * keys[:, 1] + 17 * keys[:, 2]) & 2) == 0


def _refused(reason: str, search_counts: np.ndarray,
             validation_counts: np.ndarray) -> Cmy7HeadFit:
    return Cmy7HeadFit(
        head=None, adopted=False, reason=reason,
        n_search=int(search_counts.sum()),
        n_validation=int(validation_counts.sum()),
        search_class_counts=tuple(int(v) for v in search_counts),
        validation_class_counts=tuple(int(v) for v in validation_counts),
        identity_validation_nll=None, candidate_validation_nll=None,
        iterations=0)


def fit_cmy7_head(
    scores: np.ndarray,
    states: np.ndarray,
    site_keys: np.ndarray,
    *,
    qda_search_site_keys: np.ndarray,
) -> Cmy7HeadFit:
    """Fit and strictly held-out-gate one region's CMY7 head.

    ``scores`` / ``states`` / ``site_keys`` are the region's HELD-OUT
    known-furniture rows under the selected arm's QDA: the six relative
    scores, the 0..6 true state, and the canonical ``(page, y, x)`` site
    key.  ``qda_search_site_keys`` is the QDA's own training population,
    passed so the disjointness the split guarantees is CHECKED rather than
    assumed (K does the same in ``detect.fit_calibration``); it is a
    keyword argument because the leak check is the point, not an option.

    Returns a decision, never raises on starvation.  It DOES raise on a
    leak or a malformed population — those are bugs, not channel facts.
    """
    scores = np.asarray(scores, np.float64)
    labels = np.asarray(states, np.int64)
    keys = np.asarray(site_keys, np.int64)
    search_keys = np.asarray(qda_search_site_keys, np.int64)
    if scores.ndim != 2 or scores.shape[1] != HEAD_N_OFFSETS:
        raise Cmy7HeadError("color head: scores must have shape (N,6)")
    if labels.shape != (scores.shape[0],):
        raise Cmy7HeadError("color head: states must align with scores")
    if keys.ndim != 2 or keys.shape != (scores.shape[0], 3):
        raise Cmy7HeadError("color head: site keys must have shape (N,3)")
    if search_keys.ndim != 2 or search_keys.shape[1:] != (3,):
        raise Cmy7HeadError("color head: QDA site keys must have shape (M,3)")
    if labels.size and (labels.min() < 0 or labels.max() > HEAD_N_OFFSETS):
        raise Cmy7HeadError("color head: states must be seven-state labels")
    if not np.isfinite(scores).all():
        raise Cmy7HeadError("color head: scores must be finite")

    fit_side = head_sub_split(keys)
    validation_side = ~fit_side
    # The sub-split is a pure function of the site key, so a cell cannot
    # land on both sides — UNLESS the population itself repeats a cell,
    # which is the falsifiable form of the same leak (an upstream
    # deduplication failure would double-count one observation and let the
    # fitting side see a row the gate also scores).  Both are checked:
    # uniqueness first because it is the one that can actually fire, then
    # the intersection itself, kept as the literal mirror of K's
    # `detect.fit_calibration` contract.
    if np.unique(keys, axis=0).shape[0] != keys.shape[0]:
        raise Cmy7HeadError("color head: cal site keys repeat a cell")
    if _rows_overlap(keys[fit_side], keys[validation_side]):
        raise Cmy7HeadError(
            "color head: cal SEARCH/VALIDATION site keys overlap")
    if _rows_overlap(keys[fit_side], search_keys):
        raise Cmy7HeadError(
            "color head: cal SEARCH overlaps the QDA search population")
    if _rows_overlap(keys[validation_side], search_keys):
        raise Cmy7HeadError(
            "color head: cal VALIDATION overlaps the QDA search population")

    states_total = HEAD_N_OFFSETS + 1
    search_counts = np.bincount(
        labels[fit_side], minlength=states_total)[:states_total]
    validation_counts = np.bincount(
        labels[validation_side], minlength=states_total)[:states_total]
    if int(search_counts.min()) < HEAD_MIN_SEARCH_PER_STATE:
        return _refused(
            "search_class_starved", search_counts, validation_counts)
    if (int(validation_counts.sum()) < HEAD_MIN_VALIDATION
            or int(validation_counts.min())
            < HEAD_MIN_VALIDATION_PER_STATE):
        return _refused("heldout_starved", search_counts, validation_counts)

    # Both populations are class-balanced: the fit so the head calibrates
    # instead of re-priorizing, the gate so it is judged under the same
    # equal-prior measure the payload field actually has.
    scale, offsets, iterations = _newton(
        scores[fit_side], labels[fit_side],
        class_balanced_weights(labels[fit_side]))
    head = Cmy7Head(scale, offsets)
    validation_scores = scores[validation_side]
    validation_states = labels[validation_side]
    validation_weights = class_balanced_weights(validation_states)
    identity = _mean_nll(
        validation_scores, validation_states, 1.0,
        np.zeros(HEAD_N_OFFSETS, np.float64), validation_weights)
    candidate = _mean_nll(
        validation_scores, validation_states, head.scale, head.offsets,
        validation_weights)
    adopted = bool(identity - candidate > HEAD_GATE_SLACK)
    return Cmy7HeadFit(
        head=head if adopted else None,
        adopted=adopted,
        reason="adopted" if adopted else "validation_gate_failed",
        n_search=int(search_counts.sum()),
        n_validation=int(validation_counts.sum()),
        search_class_counts=tuple(int(v) for v in search_counts),
        validation_class_counts=tuple(int(v) for v in validation_counts),
        identity_validation_nll=identity,
        candidate_validation_nll=candidate,
        iterations=iterations)


__all__ = [
    "HEAD_GATE_SLACK", "HEAD_GRAD_TOL", "HEAD_MAX_ITERATIONS",
    "HEAD_MIN_SEARCH_PER_STATE", "HEAD_MIN_VALIDATION",
    "HEAD_MIN_VALIDATION_PER_STATE", "HEAD_N_OFFSETS", "HEAD_SCALE_MAX",
    "HEAD_SCALE_MIN", "Cmy7Head", "Cmy7HeadError", "Cmy7HeadFit",
    "class_balanced_weights", "fit_cmy7_head", "head_sub_split",
]

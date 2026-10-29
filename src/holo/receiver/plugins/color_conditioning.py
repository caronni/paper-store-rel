"""A4b — KnownField-conditioned marginalization (CMY8 only).

Carries the A4b arm of the v1 receiver plus the sibling-subset kernels
of its colour detector — that receiver was retired 2026-09-05 at
284ae3e, and the arm reads at b167b9f:src/holo/receive/
color_conditioning.py and .../color_detect.py.  Policy token
``knownfield-conditioned-marginals-ulane-only``
(docs/RECEIVE-DESIGN.md section 6.2a, "P9 conditioning ruling", that
receiver's design of record and still the record of this arm;
docs/COLOR-UPLIFT-PLAN.md:391).  Its constants are v1's, bit-for-bit.

Per cell, a component's marginal is taken over the state SUBSET
consistent with what the KnownField already knows about its two SIBLING
components: nothing known leaves the ordinary 4-vs-4 (the NORMAL case,
not a fallback), one sibling leaves 2-vs-2, both leave 1-vs-1.
Conditioning on prior-barrier certified authority fabricates nothing
about the remaining component.

CALIBRATION IS THE SAFETY, NOT POLISH.  A 2-vs-2 log ratio is a DIFFERENT
statistic from a 4-vs-4 one, so feeding it to the map fitted for the
unconditioned axis would sharpen the model's overconfidence exactly where
the receiver was given real knowledge.  Maps are therefore stratified by
(plane, conditioning-pattern) — {none, sib1, sib2, both} per plane,
twelve strata — and M-given-C is deliberately a different stratum from
M-given-Y.

TWO-SOURCE PROVENANCE.  (a) PRIMARY where dense: CERT-CROSS cells, payload
cells whose labelled plane AND at least one sibling are prior-barrier
certified — deployment-exact material, but selection-biased toward clean
tiles (registered compromise R12).  (b) FLOOR everywhere: format
furniture, arity-2 by construction, read through a deterministic MASK,
which is the spatially unbiased mitigation of (a).

THE REVEAL FIELD is two bits, ``(131*y + 17*x) & 12``, whose LOW BIT is
§6.2a's named ``&4`` (it selects sib1 vs sib2 exactly as written) and
whose high bit adds "both".  One bit chooses between two siblings but
cannot also choose the ARITY, and there are three nonempty patterns; with
two bits the four codes PARTITION every furniture cell into exactly one
pattern per plane.  Measured uniform (1024 each over a 64x64 tile) and
exactly independent of the ``&1`` QDA split and the ``&2`` head
sub-split.  Masking is a VIEW, never a mutation: it exists only in this
module's two populations, and every other consumer sees the cell's true
state.  Pattern code 0 is NOT refitted — it IS the incumbent detector's
own map, so an unconditioned cell's evidence stays byte-identical.

Constants and their provenance (COLOR-UPLIFT-MEASUREMENTS §9):

* ``CONDITIONED_MIN_CLASS_LABELS = 6`` — the CMY8 dust vocabulary's
  ``CMY8_CALIBRATION_MIN_CLASS_LABELS``.
* ``CONDITIONED_MIN_LABELS = 40`` — enough total mass that PAVA's
  1/(N+2) clamp is not the whole model.
* ``CONDITIONED_MIN_VALIDATION = 20`` — K's held-out floor name and
  shape; A3 carries the identical structure one arm lower.
* ``CONDITIONED_MAX_LABELS = 100_000`` / ``CONDITIONING_MAX_CERT_CELLS =
  400_000`` — bounded cost, deterministic stride in canonical site order,
  never a draw.  Four strata's worth, so no stratum is starved by the cap.

THE PRE-GATE IS A3'S SHAPE: one strict improvement on the stratum's own
held-out cells.  The three-way variant was built and measured and is NOT
adopted — it keeps 2 strata of 9 and +11 certificates on xerox c2-cmy8
where the single test keeps 8 and +19.  All three legs are measured and
published anyway.  The REGION adoption gate is bypassed by construction
(verdict ``region_gate_forced``): measured, that gate refused on the DUST
leg at all fourteen conditioned lanes while total and word improved by
.015-.023 nats, so it was what made the arm unreachable rather than
unhelpful.  There is no applicability constant, because no statistic
separated the lanes A4b helps from the ones it costs — the harm tracks
the SOURCE of a stratum's material, not any size, spread or ratio of it.

A4b needs a certified SIBLING plane, so a single-stream coding has
nothing to condition on and never schedules the arm.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

from ..lib.pava import class_balanced_weights
from .color_model import (
    DEGENERATE_LLR_CLIP,
    HEAD_GATE_SLACK,
    Cmy8Detector,
    PavaMap,
    QdaModel,
    _CMY8_STATE_BITS,
    clip_unsupported_planes,
    fit_component_pava,
    qda_log_scores,
)

CMY8_SIBLINGS: tuple[tuple[int, int], ...] = ((1, 2), (0, 2), (0, 1))

CONDITIONING_REVEAL_MASK: int = 12
CONDITIONING_REVEAL_SHIFT: int = 2
CONDITIONING_N_PATTERNS: int = 4

CONDITIONED_MIN_CLASS_LABELS: int = 6
CONDITIONED_MIN_LABELS: int = 40
CONDITIONED_MIN_VALIDATION: int = 20
CONDITIONED_MAX_LABELS: int = 100_000
CONDITIONING_MAX_CERT_CELLS: int = 400_000

#: A loss that was never measured -- a starved stratum, an unsupported
#: plane, a region that refused before its gate ran.  Negative, never NaN
#: and never 0.0, so a skipped measurement can neither poison an
#: arithmetic comparison nor be read as a perfect one.
CONDITIONING_NLL_UNMEASURED: float = -1.0

CONDITIONING_REASON_ADOPTED: str = "adopted"
CONDITIONING_REASON_STARVED: str = "search_class_starved"
CONDITIONING_REASON_HELDOUT_STARVED: str = "heldout_starved"
CONDITIONING_REASON_GATE_FAILED: str = "validation_gate_failed"
CONDITIONING_REASON_NO_STRATUM: str = "no_stratum_adopted"
CONDITIONING_REASON_NO_CELLS: str = "no_conditioned_cells"
CONDITIONING_REASON_UNSUPPORTED: str = "plane_unsupported"
CONDITIONING_REASON_REGION_FORCED: str = "region_gate_forced"


class ConditioningError(ValueError):
    pass


def conditioning_pattern_codes(known_mask: np.ndarray) -> np.ndarray:
    mask = np.asarray(known_mask, np.bool_)
    if mask.ndim != 2 or mask.shape[1] != 3:
        raise ConditioningError(
            "color conditioning: known mask must be (N, 3)")
    codes = np.zeros(mask.shape, np.int8)
    for plane in range(3):
        first, second = CMY8_SIBLINGS[plane]
        codes[:, plane] = (
            mask[:, first].astype(np.int8)
            + 2 * mask[:, second].astype(np.int8))
    return codes


def masking_reveal_codes(cells_yx: np.ndarray) -> np.ndarray:
    cells = np.asarray(cells_yx, np.int64)
    if cells.ndim != 2 or cells.shape[1] != 2:
        raise ConditioningError(
            "color conditioning: cells must be (N, 2) y/x")
    hashed = 131 * cells[:, 0] + 17 * cells[:, 1]
    return (
        (hashed & CONDITIONING_REVEAL_MASK) >> CONDITIONING_REVEAL_SHIFT
    ).astype(np.int8)


def pattern_view_mask(plane: int, pattern_codes: np.ndarray) -> np.ndarray:
    codes = np.asarray(pattern_codes, np.int64)
    view = np.zeros((codes.size, 3), np.bool_)
    first, second = CMY8_SIBLINGS[plane]
    view[:, first] = (codes & 1) != 0
    view[:, second] = (codes & 2) != 0
    return view


def cmy8_sibling_allowed(plane: int, known_mask: np.ndarray,
                         known_bits: np.ndarray) -> np.ndarray:
    if plane not in (0, 1, 2):
        raise ConditioningError(
            "color conditioning: CMY8 plane must be 0, 1 or 2")
    mask = np.asarray(known_mask, np.bool_)
    bits = np.asarray(known_bits)
    if mask.ndim != 2 or mask.shape[1] != 3 or bits.shape != mask.shape:
        raise ConditioningError(
            "color conditioning: KnownField arrays must have shape (N, 3)")
    allowed = np.ones((mask.shape[0], 8), np.bool_)
    for sibling in CMY8_SIBLINGS[plane]:
        hit = mask[:, sibling]
        if not np.any(hit):
            continue
        wanted = bits[:, sibling].astype(bool)
        matches = _CMY8_STATE_BITS[None, :, sibling] == wanted[:, None]
        allowed &= matches | ~hit[:, None]
    return allowed


def _masked_logsumexp(scores: np.ndarray,
                      allowed: np.ndarray) -> np.ndarray:
    return logsumexp(np.where(allowed, scores, -np.inf), axis=1)


def cmy8_plane_marginal(scores: np.ndarray, plane: int,
                        allowed: np.ndarray | None = None) -> np.ndarray:
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


def cmy8_conditioned_marginal_llrs(scores: np.ndarray,
                                   known_mask: np.ndarray,
                                   known_bits: np.ndarray) -> np.ndarray:
    values = np.asarray(scores, np.float64)
    if values.ndim != 2 or values.shape[1] != 8:
        raise ConditioningError(
            "color conditioning: CMY8 scores must have shape (N, 8)")
    result = np.empty((values.shape[0], 3), dtype=np.float64)
    for plane in range(3):
        result[:, plane] = cmy8_plane_marginal(values, plane)
    mask = np.asarray(known_mask, np.bool_)
    if mask.shape[0] != values.shape[0]:
        raise ConditioningError(
            "color conditioning: KnownField rows must align with the scores")
    bits = np.asarray(known_bits)
    for plane in range(3):
        left, right = CMY8_SIBLINGS[plane]
        conditioned = np.flatnonzero(mask[:, left] | mask[:, right])
        if conditioned.size == 0:
            continue
        allowed = cmy8_sibling_allowed(
            plane, mask[conditioned], bits[conditioned])
        result[conditioned, plane] = cmy8_plane_marginal(
            values[conditioned], plane, allowed)
    return result


@dataclass(frozen=True)
class ConditioningPopulation:
    scores: np.ndarray
    bits: np.ndarray
    labelled: np.ndarray
    pattern: np.ndarray
    kinds: np.ndarray
    from_certificates: np.ndarray

    def __post_init__(self) -> None:
        rows = np.asarray(self.scores, np.float64)
        if rows.ndim != 2 or rows.shape[1] != 8:
            raise ConditioningError(
                "color conditioning: population scores must be (N, 8)")
        for name, width in (("bits", 3), ("labelled", 3), ("pattern", 3),
                            ("kinds", 0), ("from_certificates", 0)):
            value = np.asarray(getattr(self, name))
            expected = ((rows.shape[0], width) if width
                        else (rows.shape[0],))
            if value.shape != expected:
                raise ConditioningError(
                    f"color conditioning: {name} must have shape {expected}")

    @property
    def n_cells(self) -> int:
        return int(self.scores.shape[0])


@dataclass(frozen=True)
class ConditionedStratum:
    plane: int
    pattern: int
    calibration: PavaMap | None
    reason: str
    n_cert: int
    n_masked: int
    n_fitted: int
    n_validation: int
    incumbent_nll: float
    candidate_nll: float
    word_incumbent_nll: float = CONDITIONING_NLL_UNMEASURED
    word_candidate_nll: float = CONDITIONING_NLL_UNMEASURED
    dust_incumbent_nll: float = CONDITIONING_NLL_UNMEASURED
    dust_candidate_nll: float = CONDITIONING_NLL_UNMEASURED

    @property
    def adopted(self) -> bool:
        return self.calibration is not None


@dataclass(frozen=True)
class Cmy8ConditionedHead:
    strata: tuple[tuple[PavaMap | None, ...], ...]

    def __post_init__(self) -> None:
        if (len(self.strata) != 3
                or any(len(row) != CONDITIONING_N_PATTERNS
                       for row in self.strata)
                or any(row[0] is not None for row in self.strata)):
            raise ConditioningError(
                "color conditioning: strata must be 3 planes x 4 patterns "
                "with an empty pattern-0 slot")

    def llrs_from_scores(self, detector: Cmy8Detector, scores: np.ndarray,
                         known_mask: np.ndarray,
                         known_bits: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, np.float64)
        raw = clip_unsupported_planes(
            detector.qda, _unconditioned_marginals(values))
        conditioned = clip_unsupported_planes(
            detector.qda,
            cmy8_conditioned_marginal_llrs(values, known_mask, known_bits))
        codes = conditioning_pattern_codes(known_mask)
        supported = detector.supported_planes
        result = np.empty_like(raw)
        for plane in range(3):
            if not supported[plane]:
                result[:, plane] = 0.0
                continue
            plane_values = detector.calibrations[plane].llrs(raw[:, plane])
            for pattern in range(1, CONDITIONING_N_PATTERNS):
                stratum = self.strata[plane][pattern]
                if stratum is None:
                    continue
                selected = codes[:, plane] == pattern
                if not np.any(selected):
                    continue
                plane_values[selected] = stratum.llrs(
                    conditioned[selected, plane])
            result[:, plane] = plane_values
        return result

    def llrs(self, detector: Cmy8Detector, features: np.ndarray,
             known_mask: np.ndarray,
             known_bits: np.ndarray) -> np.ndarray:
        return self.llrs_from_scores(
            detector, qda_log_scores(detector.qda, features),
            known_mask, known_bits)


@dataclass(frozen=True)
class Cmy8ConditioningFit:
    head: Cmy8ConditionedHead | None
    adopted: bool
    reason: str
    strata: tuple[ConditionedStratum, ...]
    n_cert_cells: int
    n_masked_cells: int
    n_validation: int
    incumbent_nll: float
    candidate_nll: float
    word_incumbent_nll: float
    word_candidate_nll: float
    dust_incumbent_nll: float
    dust_candidate_nll: float


def _unconditioned_marginals(scores: np.ndarray) -> np.ndarray:
    values = np.asarray(scores, np.float64)
    result = np.empty((values.shape[0], 3), dtype=np.float64)
    for plane in range(3):
        result[:, plane] = cmy8_plane_marginal(values, plane)
    return result


def _binary_nll(llrs: np.ndarray, bits: np.ndarray) -> np.ndarray:
    sign = np.where(np.asarray(bits, np.int64) > 0, 1.0, -1.0)
    return np.logaddexp(0.0, -sign * np.asarray(llrs, np.float64))


def _balanced_mean(losses: np.ndarray, bits: np.ndarray) -> float:
    if losses.size == 0:
        return 0.0
    weights = class_balanced_weights(np.asarray(bits, np.int64))
    return float(np.sum(weights * losses) / np.sum(weights))


def _stride_subsample(count: int, limit: int) -> np.ndarray:
    if count <= limit:
        return np.arange(count)
    return np.linspace(0, count - 1, limit).astype(np.int64)


def _plane_llrs(population: ConditioningPopulation, qda: QdaModel,
                plane: int, rows: np.ndarray, *,
                conditioned: bool) -> np.ndarray:
    scores = population.scores[rows]
    allowed = (
        cmy8_sibling_allowed(
            plane,
            pattern_view_mask(plane, population.pattern[rows, plane]),
            population.bits[rows])
        if conditioned else None
    )
    values = cmy8_plane_marginal(scores, plane, allowed)
    if qda.degenerate or plane in qda.clipped_planes:
        values = np.clip(values, -DEGENERATE_LLR_CLIP, DEGENERATE_LLR_CLIP)
    return values


def _fit_stratum(detector: Cmy8Detector, material: ConditioningPopulation,
                 gate: ConditioningPopulation, plane: int,
                 pattern: int) -> ConditionedStratum:
    chosen = np.flatnonzero(
        material.labelled[:, plane]
        & (material.pattern[:, plane] == pattern))
    n_cert = int(np.count_nonzero(material.from_certificates[chosen]))
    n_masked = int(chosen.size) - n_cert
    validation = np.flatnonzero(
        gate.labelled[:, plane] & (gate.pattern[:, plane] == pattern))

    def refused(reason: str, fitted: int = 0) -> ConditionedStratum:
        return ConditionedStratum(
            plane, pattern, None, reason, n_cert, n_masked, fitted,
            int(validation.size),
            CONDITIONING_NLL_UNMEASURED, CONDITIONING_NLL_UNMEASURED)

    labels = material.bits[chosen, plane].astype(np.int64)
    counts = np.bincount(labels, minlength=2)
    if (chosen.size < CONDITIONED_MIN_LABELS
            or int(counts.min()) < CONDITIONED_MIN_CLASS_LABELS):
        return refused(CONDITIONING_REASON_STARVED)
    if validation.size < CONDITIONED_MIN_VALIDATION:
        return refused(CONDITIONING_REASON_HELDOUT_STARVED)
    fitted_rows = chosen[_stride_subsample(
        chosen.size, CONDITIONED_MAX_LABELS)]
    fitted_labels = material.bits[fitted_rows, plane].astype(np.int64)
    if int(np.bincount(fitted_labels, minlength=2).min()) < 1:
        return refused(CONDITIONING_REASON_STARVED, int(fitted_rows.size))
    calibration = fit_component_pava(
        _plane_llrs(material, detector.qda, plane, fitted_rows,
                    conditioned=True),
        fitted_labels)
    truth = gate.bits[validation, plane]
    kinds = gate.kinds[validation]
    incumbent_loss = _binary_nll(
        detector.calibrations[plane].llrs(
            _plane_llrs(gate, detector.qda, plane, validation,
                        conditioned=False)),
        truth)
    candidate_loss = _binary_nll(
        calibration.llrs(
            _plane_llrs(gate, detector.qda, plane, validation,
                        conditioned=True)),
        truth)

    def legs(loss: np.ndarray) -> tuple[float, float, float]:
        return (
            _balanced_mean(loss, truth),
            _balanced_mean(loss[kinds == 0], truth[kinds == 0]),
            _balanced_mean(loss[kinds == 1], truth[kinds == 1]),
        )

    incumbent = legs(incumbent_loss)
    candidate = legs(candidate_loss)
    passed = candidate[0] + HEAD_GATE_SLACK < incumbent[0]
    return ConditionedStratum(
        plane, pattern, calibration if passed else None,
        CONDITIONING_REASON_ADOPTED if passed
        else CONDITIONING_REASON_GATE_FAILED,
        n_cert, n_masked, int(fitted_rows.size), int(validation.size),
        incumbent[0], candidate[0], incumbent[1], candidate[1],
        incumbent[2], candidate[2])


def _region_losses(detector: Cmy8Detector, gate: ConditioningPopulation,
                   head: Cmy8ConditionedHead | None,
                   ) -> tuple[float, float, float]:
    losses: list[np.ndarray] = []
    truths: list[np.ndarray] = []
    kinds: list[np.ndarray] = []
    supported = detector.supported_planes
    for plane in range(3):
        if not supported[plane]:
            continue
        rows = np.flatnonzero(gate.labelled[:, plane])
        if rows.size == 0:
            continue
        values = detector.calibrations[plane].llrs(
            _plane_llrs(gate, detector.qda, plane, rows, conditioned=False))
        if head is not None:
            for pattern in range(1, CONDITIONING_N_PATTERNS):
                stratum = head.strata[plane][pattern]
                if stratum is None:
                    continue
                selected = gate.pattern[rows, plane] == pattern
                if not np.any(selected):
                    continue
                values[selected] = stratum.llrs(
                    _plane_llrs(gate, detector.qda, plane, rows[selected],
                                conditioned=True))
        truth = gate.bits[rows, plane]
        losses.append(_binary_nll(values, truth))
        truths.append(truth)
        kinds.append(gate.kinds[rows])
    if not losses:
        return 0.0, 0.0, 0.0
    loss = np.concatenate(losses)
    truth = np.concatenate(truths)
    kind = np.concatenate(kinds)
    return (
        _balanced_mean(loss, truth),
        _balanced_mean(loss[kind == 0], truth[kind == 0]),
        _balanced_mean(loss[kind == 1], truth[kind == 1]),
    )


def fit_conditioned_marginals(detector: Cmy8Detector,
                              material: ConditioningPopulation,
                              gate: ConditioningPopulation,
                              ) -> Cmy8ConditioningFit:
    if not isinstance(detector, Cmy8Detector):
        raise ConditioningError(
            "color conditioning: A4b needs a CMY8 detector")
    if not isinstance(material, ConditioningPopulation) or not isinstance(
            gate, ConditioningPopulation):
        raise ConditioningError(
            "color conditioning: populations must be ConditioningPopulation")
    supported = detector.supported_planes
    strata: list[ConditionedStratum] = []
    grid: list[list[PavaMap | None]] = [
        [None] * CONDITIONING_N_PATTERNS for _ in range(3)]
    for plane in range(3):
        for pattern in range(1, CONDITIONING_N_PATTERNS):
            if not supported[plane]:
                strata.append(ConditionedStratum(
                    plane, pattern, None, CONDITIONING_REASON_UNSUPPORTED,
                    0, 0, 0, 0, CONDITIONING_NLL_UNMEASURED,
                    CONDITIONING_NLL_UNMEASURED))
                continue
            stratum = _fit_stratum(detector, material, gate, plane, pattern)
            strata.append(stratum)
            grid[plane][pattern] = stratum.calibration
    n_cert = int(np.count_nonzero(material.from_certificates))
    n_masked = material.n_cells - n_cert
    frozen = tuple(strata)
    if not any(row.adopted for row in frozen):
        return Cmy8ConditioningFit(
            None, False, CONDITIONING_REASON_NO_STRATUM, frozen,
            n_cert, n_masked, gate.n_cells,
            *((CONDITIONING_NLL_UNMEASURED,) * 6))
    head = Cmy8ConditionedHead(tuple(tuple(row) for row in grid))
    incumbent = _region_losses(detector, gate, None)
    candidate = _region_losses(detector, gate, head)
    return Cmy8ConditioningFit(
        head, True, CONDITIONING_REASON_REGION_FORCED,
        frozen, n_cert, n_masked, gate.n_cells,
        incumbent[0], candidate[0], incumbent[1], candidate[1],
        incumbent[2], candidate[2])

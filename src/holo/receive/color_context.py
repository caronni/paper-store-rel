"""P2 / PK5: the neighbourhood corrector (arm A5).

RECEIVE-DESIGN §6.2a, arm A5.  Ink is not laid one cell at a time: a
cell's reading carries its neighbours' ink through the print spread and
the scanner PSF, and the region QDA — fitted on features alone — cannot
see that.  K has priced this since E023b (``ctx-pava-v1``, the c2-K
enabler and the F1∘F6 multi-scan prerequisite); colour had no context
model at all.  This module is that model:

* **the multi-state MATRIX** (``matrix``, the user's respec, SHIPPED) —
  a per-STATE x per-plane isotonic correction of the QDA's own state
  scores, ``score(s) += SUM_k f_{s,k}(count_k)``, with ``count_k`` the
  8-neighbourhood ink count in plane ``k`` and each ``f_{s,k}`` a monotone
  9-bin curve.  ONE correction locus serves both kinds: cmy7's six
  W-relative scores and cmy8's eight state scores, corrected BEFORE
  ``color_detect.cmy8_marginal_llrs`` marginalizes.  It strictly
  GENERALIZES the per-plane form (``f_{s,k} = bit_k(s)·g_k`` is the
  special case), so neighbour ink in one plane can move a specific state
  confusion — M-neighbours against the C/CM boundary — and not only the M
  marginal.

THE PER-PLANE K PORT IS RETIRED (PK-CLEAN; measured PK5, MEASUREMENTS
§11.2/§11.4, retirement note §12).  It was built beside the matrix as the
comparison arm — ``detect.fit_context`` / ``apply_context_offsets``
verbatim, one 3x9 ordered-logit fit per plane on the post-head marginals
— and on the uplift target it adopted in **0 of 17 lanes**, refusing
``region_gate_failed`` every time while costing 8,648 s of CPU.  The
mechanism, in one sentence: ONE CURVE PER PLANE IS SPENT ON THE
POPULATION THAT DOMINATES THE LABELS — 83-84% word — so it improves the
word leg by .09-.19 nats, damages the dust leg by .04-.20, and the
standing three-way gate refuses it, where the matrix's per-STATE
factorization serves word and dust at once.  The ``ContextHead``
interface it shared with the matrix stays; its fitter, its
plane-composition sum and its marginal application locus do not.

The fit produces one :class:`ContextHead`, so ``color_fitting`` has
exactly one thing to apply and ``color_stack`` exactly one arm to gate.
Which variant a tree runs is :data:`CONTEXT_VARIANT`, published per
region and generated into the policy token; a sweep moves it as
lane-scoped configuration (``color_stack.StackConfig``), never through
the environment.

WHY THE CURVES ARE MONOTONE, AND IN WHICH DIRECTION.  K's offsets are
NON-INCREASING in the neighbour count because bleed inflates the evidence
for ink.  The state form has both signs, and the sign is not fitted — it
is READ OFF the state's own plane bit, which keeps the parameter count
honest and the family a strict generalization of the per-plane one: a
state that PRINTS plane k is over-evidenced by plane-k neighbours
(non-increasing, K's direction) and one that does NOT is under-evidenced
by the same bleed (non-decreasing), so their difference is non-increasing
— the per-plane curve — whichever way the population leans.  The pooling
is K's generalized PAVA over ordered blocks with K's block solver
(``detect._solve_offset``: the project-canonical two-branch sigmoid
resolved by bisection — this module defines no sigmoid, per the v0.39
ruling), applied to the one-vs-rest logit.  That reduction is EXACT: for
a softmax, shifting one state's logit by δ moves its probability by
exactly ``sigmoid(l + δ)`` with ``l = score_s - logsumexp(score_j≠s)``,
so the multinomial stationarity condition for δ IS K's binary one
(expected count of s == observed count of s).  Curves are fitted in a
canonical order (state-major, plane-minor) over :data:`CONTEXT_SWEEPS`
coordinate-ascent sweeps: each sees every correction adopted before it.

IDENTIFICATION (why a curve cannot do the head's job).  Every curve is
ZERO-ANCHORED on its own fit population — the class-balanced weighted
mean of ``f(count)`` over the cells it was fitted on is subtracted — so
it carries SHAPE only.  Unanchored, a curve absorbs a constant per-state
offset, which is A4's job and the QDA's; a context arm that quietly
re-priors the detector is measuring something else.  Anchoring preserves
monotonicity exactly.

FLOORS AND EXACT NULLS.  K's ``CTX_*`` floors apply PER CURVE (80 search
labels with 20 per class, 40 validation with 10) in K's refusal
vocabulary; a starved or gate-refused curve is exactly zero, a region
whose curves all refuse produces NO head, and a region without a head
emits the literal pre-P2 arrays (risk R3).  The ±12 clamp kernel runs
only for a plane whose curve was ADOPTED (risk R1).

THE LABEL REALITY, STATED.  Labels are known cells only, from two sources
in one population: format furniture (word + dust) and prior-barrier
CERTIFIED payload cells — ``_owner_selection`` already carries both,
deduplicated, on the standing ``(131y+17x)&1`` split.  Curves fit on the
SEARCH side and are gated on the disjoint HELD-OUT side, which the region
comparison also reads.  Each source's per-lane volume is published
(``color.context.labels_*``): a context fit's whole quality is which
cells it saw.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.special import logsumexp

from . import color_detect
from .color_calibration import (
    HEAD_GATE_SLACK, Cmy7Head, Cmy7HeadError, class_balanced_weights,
)
from .color_detect import CMY8Detector, ColorQDAModel
from .color_neighbourhood import (
    anchor_curve, augment, one_versus_rest, ordered_offsets,
    state_bits, stride_select,
)
from .detect import (
    CTX_MIN_SEARCH, CTX_MIN_SEARCH_PER_CLASS, CTX_MIN_VALIDATION,
    CTX_MIN_VALIDATION_PER_CLASS, N_CONTEXT_BINS,
)


class ContextError(Cmy7HeadError):
    """A shape or a type the A5 fitter refuses to work with."""


# The shipped variant, and the value that is "no arm at all" (which is
# what force-null hands the ladder).
CONTEXT_VARIANT_MATRIX: Final = "matrix"
CONTEXT_VARIANT_OFF: Final = "off"
CONTEXT_VARIANTS: Final = (CONTEXT_VARIANT_MATRIX, CONTEXT_VARIANT_OFF)

# THE SHIPPED VARIANT.  Measured head-to-head against the per-plane K
# port on the three-capture replay set (COLOR-UPLIFT-MEASUREMENTS §11)
# and it won everywhere that mattered; the token carries it, so a
# decode's declared identity always names the arm it ran.
CONTEXT_VARIANT: Final = CONTEXT_VARIANT_MATRIX

# Bounded cost.  Every curve's block solve bisects over its own rows in
# Python (``detect._solve_offset``) and the matrix form fits up to 24
# curves where K fits one, so a late lane's millions of labels would make
# one region's fit the run's CPU peak.  Above this a population is
# subsampled by a deterministic stride — never a draw — and the fitted
# count is published.
CONTEXT_MAX_LABELS: Final = 40_000

# Coordinate-ascent sweeps for the matrix variant.  Swept, published in
# the token, and NOT 1: see :func:`_fit_matrix_curves`.
CONTEXT_SWEEPS: Final = 3

# A loss that was never measured (the campaign's standing convention,
# ``color_conditioning.CONDITIONING_NLL_UNMEASURED``): negative, never
# NaN, so a summary stays ``==``-comparable and a skipped measurement is
# never readable as a very good 0.0.
CONTEXT_NLL_UNMEASURED: Final = -1.0

# Refusal vocabulary — K's verbatim, plus A3/A4b's region verdicts.
CONTEXT_REASON_ADOPTED: Final = "adopted"
CONTEXT_REASON_SEARCH_STARVED: Final = "insufficient_search_support"
CONTEXT_REASON_SEARCH_CLASS: Final = "search_class_starved"
CONTEXT_REASON_VALIDATION_STARVED: Final = "insufficient_validation_support"
CONTEXT_REASON_VALIDATION_CLASS: Final = "validation_class_starved"
CONTEXT_REASON_GATE_FAILED: Final = "validation_gate_failed"
CONTEXT_REASON_REGION_GATE: Final = "region_gate_failed"
CONTEXT_REASON_REGION_FORCED: Final = "region_gate_forced"
CONTEXT_REASON_NO_CURVE: Final = "no_curve_adopted"
CONTEXT_REASON_NO_CELLS: Final = "no_context_cells"
CONTEXT_REASON_UNSUPPORTED: Final = "plane_unsupported"

# The application locus.  A state-locus head is added to the score vector
# the kind emits through (cmy7's six relative logits, cmy8's eight state
# scores, BEFORE marginalization).  It is named rather than assumed
# because a head declares WHERE it applies and ``color_fitting`` reads
# that declaration; the second locus this field once distinguished (K's
# own, on the emitted component LLRs) belonged to the retired per-plane
# port.
LOCUS_STATES: Final = "states"


@dataclass(frozen=True, slots=True)
class ContextConfig:
    """The effective A5 configuration for one run (swept, published)."""

    variant: str = CONTEXT_VARIANT
    min_search: int = CTX_MIN_SEARCH
    min_search_per_class: int = CTX_MIN_SEARCH_PER_CLASS
    min_validation: int = CTX_MIN_VALIDATION
    min_validation_per_class: int = CTX_MIN_VALIDATION_PER_CLASS
    max_labels: int = CONTEXT_MAX_LABELS
    sweeps: int = CONTEXT_SWEEPS

    def __post_init__(self) -> None:
        if self.variant not in CONTEXT_VARIANTS:
            raise ContextError(
                f"color context: unknown variant {self.variant!r}")
        if min(self.min_search, self.min_search_per_class,
               self.min_validation, self.min_validation_per_class) < 1:
            raise ContextError("color context: floors must be positive")
        if self.max_labels < 1:
            raise ContextError("color context: the label cap must be positive")
        if self.sweeps < 1:
            raise ContextError("color context: sweeps must be positive")

    @property
    def enabled(self) -> bool:
        return self.variant != CONTEXT_VARIANT_OFF

    @property
    def policy_token(self) -> str:
        """The GENERATED identity segment — A3's discipline, verbatim.

        A swept run cannot claim numbers it did not use: the variant AND
        the four floors are spelled into the token from the values the
        ladder will actually read.
        """
        if not self.enabled:
            return "ctxoff"
        return (
            f"ctxmatrix-9bin-zeroanchor-sweeps{self.sweeps}"
            f"-floors{self.min_search}-{self.min_search_per_class}"
            f"-{self.min_validation}-{self.min_validation_per_class}")


@dataclass(frozen=True, slots=True)
class ContextHead:
    """A fitted neighbourhood corrector — THE interface the fit lands on.

    ``offsets`` is ``(C, 3, 9)`` at :data:`LOCUS_STATES`: one curve per
    score column and plane.  ``applied`` says which of them a refusal
    left exactly zero — load-bearing because a non-adopted curve must be
    provably inert, not merely small (risk R1).
    """

    locus: str
    variant: str
    offsets: np.ndarray
    applied: np.ndarray

    def __post_init__(self) -> None:
        if self.locus != LOCUS_STATES:
            raise ContextError(f"color context: bad locus {self.locus!r}")
        offsets = np.array(self.offsets, np.float64)
        applied = np.array(self.applied, np.bool_)
        if (offsets.ndim != 3 or offsets.shape[-1] != N_CONTEXT_BINS
                or offsets.shape[-2] != 3):
            raise ContextError(
                "color context: offsets must be (C, 3, 9) at the state "
                "locus")
        if applied.shape != offsets.shape[:-1]:
            raise ContextError(
                "color context: the applied mask must match the curves")
        if not np.isfinite(offsets).all():
            raise ContextError("color context: offsets must be finite")
        if np.any(offsets[~applied] != 0.0):
            raise ContextError(
                "color context: a non-adopted curve must be exactly zero")
        offsets.flags.writeable = False
        applied.flags.writeable = False
        object.__setattr__(self, "offsets", offsets)
        object.__setattr__(self, "applied", applied)

    @property
    def n_applied(self) -> int:
        return int(np.count_nonzero(self.applied))

    def apply_states(self, scores: np.ndarray,
                     bins: np.ndarray) -> np.ndarray:
        """``scores + SUM_k f_{·,k}(count_k)``, fresh ``(N, C)`` float64.

        Cells with an incomplete neighbourhood (bin ``-1``) receive
        exactly zero from every plane — K's rule, spelled here as a tenth
        zero column so the gather stays one vectorized indexing.
        """
        values = np.asarray(scores, np.float64)
        index = _bin_index(bins, values.shape[0])
        padded = np.concatenate(
            (self.offsets, np.zeros((*self.offsets.shape[:-1], 1))), axis=-1)
        if padded.shape[0] != values.shape[1]:
            raise ContextError(
                "color context: head width does not match the scores")
        delta = (padded[:, 0, index[:, 0]]
                 + padded[:, 1, index[:, 1]]
                 + padded[:, 2, index[:, 2]])
        return values + delta.T


def _bin_index(bins: np.ndarray, rows: int) -> np.ndarray:
    """``(N, 3)`` gather index with ``-1`` mapped to the zero slot."""
    values = np.asarray(bins)
    if values.ndim != 2 or values.shape != (rows, 3):
        raise ContextError(
            f"color context: bins must have shape ({rows}, 3)")
    index = values.astype(np.int64)
    if np.any((index < -1) | (index >= N_CONTEXT_BINS)):
        raise ContextError("color context: bins must lie in -1..8")
    return np.where(index < 0, N_CONTEXT_BINS, index)


@dataclass(frozen=True, slots=True)
class ContextCurve:
    """One fitted (state, plane) curve's disposition and counts."""

    column: int
    plane: int
    reason: str
    n_search: int
    n_search_positive: int
    n_validation: int
    n_fitted: int
    incumbent_nll: float = CONTEXT_NLL_UNMEASURED
    candidate_nll: float = CONTEXT_NLL_UNMEASURED

    @property
    def adopted(self) -> bool:
        return self.reason == CONTEXT_REASON_ADOPTED


@dataclass(frozen=True, slots=True)
class ContextFit:
    """One region's A5 verdict with the numbers that produced it."""

    head: ContextHead | None
    adopted: bool
    reason: str
    variant: str
    curves: tuple[ContextCurve, ...]
    n_search: int
    n_validation: int
    labels_word: int
    labels_dust: int
    labels_cert: int
    binned_fraction: float
    # The region three-way gate as it read: total, word leg, dust leg.
    incumbent_nll: float
    candidate_nll: float
    word_incumbent_nll: float
    word_candidate_nll: float
    dust_incumbent_nll: float
    dust_candidate_nll: float


@dataclass(frozen=True, slots=True)
class ContextSummary:
    """The published A5 record for one region (append-only diagnostics).

    The default instance — empty ``reason`` — is what a region reports
    when the arm never ran: force-null, a refused detector fit, or the
    variant switched off.  It is distinguishable from "ran and refused"
    exactly as A4b's is.
    """

    reason: str = ""
    variant: str = ""
    adopted: bool = False
    curves_adopted: int = 0
    curves_total: int = 0
    curve_reasons: tuple[tuple[str, int], ...] = ()
    labels_word: int = 0
    labels_dust: int = 0
    labels_cert: int = 0
    n_search: int = 0
    n_validation: int = 0
    binned_fraction: float = CONTEXT_NLL_UNMEASURED
    incumbent_nll: float = CONTEXT_NLL_UNMEASURED
    candidate_nll: float = CONTEXT_NLL_UNMEASURED
    word_incumbent_nll: float = CONTEXT_NLL_UNMEASURED
    word_candidate_nll: float = CONTEXT_NLL_UNMEASURED
    dust_incumbent_nll: float = CONTEXT_NLL_UNMEASURED
    dust_candidate_nll: float = CONTEXT_NLL_UNMEASURED

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not isinstance(
                self.variant, str):
            raise ContextError("color context: reason/variant not strings")
        if type(self.adopted) is not bool:
            raise ContextError("color context: adoption must be a bool")
        if any(type(value) is not int or value < 0 for value in (
                self.curves_adopted, self.curves_total, self.labels_word,
                self.labels_dust, self.labels_cert, self.n_search,
                self.n_validation)):
            raise ContextError(
                "color context: summary counts must be nonnegative")
        if self.adopted and self.reason not in (
                CONTEXT_REASON_ADOPTED, CONTEXT_REASON_REGION_FORCED):
            raise ContextError(
                "color context: an adopted summary must say so")


def summarize_context(fit: ContextFit) -> ContextSummary:
    """Publish one region's A5 decision, counts and gate numbers."""
    reasons: dict[str, int] = {}
    for curve in fit.curves:
        reasons[curve.reason] = reasons.get(curve.reason, 0) + 1
    return ContextSummary(
        reason=fit.reason,
        variant=fit.variant,
        adopted=fit.adopted,
        curves_adopted=sum(1 for row in fit.curves if row.adopted),
        curves_total=len(fit.curves),
        curve_reasons=tuple(sorted(reasons.items())),
        labels_word=fit.labels_word,
        labels_dust=fit.labels_dust,
        labels_cert=fit.labels_cert,
        n_search=fit.n_search,
        n_validation=fit.n_validation,
        binned_fraction=fit.binned_fraction,
        incumbent_nll=fit.incumbent_nll,
        candidate_nll=fit.candidate_nll,
        word_incumbent_nll=fit.word_incumbent_nll,
        word_candidate_nll=fit.word_candidate_nll,
        dust_incumbent_nll=fit.dust_incumbent_nll,
        dust_candidate_nll=fit.dust_candidate_nll)


# ---------------------------------------------------------------------
# The fits.
# ---------------------------------------------------------------------

def _binary_nll(llrs: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Per-cell logistic loss of an LLR against a 0/1 truth."""
    sign = np.where(np.asarray(labels, np.int64) > 0, 1.0, -1.0)
    return np.logaddexp(0.0, -sign * np.asarray(llrs, np.float64))


def _balanced_mean(losses: np.ndarray, labels: np.ndarray) -> float:
    """Class-balanced mean loss — the measure every colour gate uses.

    PK3's lesson as law (COLOR-UPLIFT-MEASUREMENTS §4.1): a furniture
    population is nothing like the uniform payload field, so an
    unweighted objective fits its log-prior instead of the channel.
    ``class_balanced_weights`` normalizes to mean 1, so a balanced
    population reproduces the plain mean exactly.  Binary printed bits
    and seven/eight-way states are the same call — the labels name their
    own alphabet.
    """
    if losses.size == 0:
        return CONTEXT_NLL_UNMEASURED
    weights = class_balanced_weights(np.asarray(labels, np.int64))
    return float(np.sum(weights * losses) / np.sum(weights))


def _multinomial_nll(scores: np.ndarray, states: np.ndarray) -> np.ndarray:
    """Per-cell ``-log softmax(scores)[state]``."""
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    return -normalized[np.arange(states.size), states]


@dataclass(frozen=True, slots=True)
class _Population:
    """One side of the split, in the shape every A5 fit reads it."""

    scores: np.ndarray          # (N, S) full state scores at the locus
    states: np.ndarray          # (N,)   true state ids
    bins: np.ndarray            # (N, 3) int8 context bins
    kinds: np.ndarray           # (N,)   0 word / 1 dust / -1 certified

    @property
    def n_cells(self) -> int:
        return int(self.scores.shape[0])


def _fit_matrix_curves(
    search: _Population,
    validation: _Population,
    config: ContextConfig,
    *, pinned_reference: bool,
) -> tuple[np.ndarray, tuple[ContextCurve, ...]]:
    """THE multi-state matrix: one monotone curve per (state, plane).

    Coordinate ascent in a canonical order — state-major, plane-minor —
    with the running corrections applied to BOTH populations as they are
    adopted, so every curve is fitted and gated against the model as it
    will actually be emitted.

    :data:`CONTEXT_SWEEPS` passes, not one.  Shifting ONE state's logit
    renormalizes every other state's probability, so the steps interact
    and a single pass leaves the family short of its own optimum
    (MEASURED, §11: one sweep reaches only part of what the per-plane
    special case gets in a single coherent step).  Every later sweep is
    fitted against the running model and passes the SAME per-curve
    held-out gate, so it can only add a correction that pays for itself;
    contributions accumulate (a sum of same-direction monotone curves is
    monotone, and each summand is zero-anchored, so the total still
    carries shape alone) and the published record is a curve's LAST
    verdict.
    """
    n_states = search.scores.shape[1]
    bits = state_bits(n_states)
    columns = range(1, n_states) if pinned_reference else range(n_states)
    width = n_states - 1 if pinned_reference else n_states
    offsets = np.zeros((width, 3, N_CONTEXT_BINS), np.float64)
    running_search = np.array(search.scores, np.float64, copy=True)
    running_validation = np.array(validation.scores, np.float64, copy=True)
    search_weights = class_balanced_weights(search.states)
    validation_weights = class_balanced_weights(validation.states)
    records: dict[tuple[int, int], ContextCurve] = {}
    for sweep in range(config.sweeps):
        moved = False
        for state in columns:
            target = state - 1 if pinned_reference else state
            for plane in range(3):
                curve, record = _fit_one_curve(
                    running_search, running_validation, search, validation,
                    search_weights, validation_weights, state, plane,
                    bool(bits[state, plane]), config)
                if curve is None:
                    # A later sweep must not erase an earlier verdict: a
                    # curve already adopted stays adopted with its offsets.
                    records.setdefault((state, plane), record)
                    continue
                records[(state, plane)] = record
                moved = True
                offsets[target, plane] += curve
                valid_search = search.bins[:, plane] >= 0
                valid_validation = validation.bins[:, plane] >= 0
                running_search[valid_search, state] += curve[
                    search.bins[valid_search, plane]]
                running_validation[valid_validation, state] += curve[
                    validation.bins[valid_validation, plane]]
        if not moved:
            # Nothing in a whole sweep earned its gate: the remaining
            # sweeps would repeat identical arithmetic.
            break
    del sweep
    return offsets, tuple(
        records[key] for key in sorted(records))


def _fit_one_curve(
    running_search: np.ndarray, running_validation: np.ndarray,
    search: _Population, validation: _Population,
    search_weights: np.ndarray, validation_weights: np.ndarray,
    state: int, plane: int, prints_plane: bool, config: ContextConfig,
) -> tuple[np.ndarray | None, ContextCurve]:
    """Fit, anchor and gate ONE ``f_{s,k}``; refuse to exactly zero.

    The weights are the region's STATE-balanced ones (PK3's law in the
    multinomial alphabet): the curve is one coordinate step of the
    class-balanced multinomial NLL, and its block solve is that step's
    exact stationarity condition, so fit and gate share one measure.
    """
    rows = np.flatnonzero(search.bins[:, plane] >= 0)
    validation_rows = np.flatnonzero(validation.bins[:, plane] >= 0)
    positives = int(np.count_nonzero(search.states[rows] == state))
    validation_positives = int(
        np.count_nonzero(validation.states[validation_rows] == state))

    def refused(reason: str, fitted: int = 0) -> tuple[None, ContextCurve]:
        return None, ContextCurve(
            state, plane, reason, int(rows.size), positives,
            int(validation_rows.size), fitted)

    if rows.size < config.min_search:
        return refused(CONTEXT_REASON_SEARCH_STARVED)
    if min(positives, int(rows.size) - positives) < (
            config.min_search_per_class):
        return refused(CONTEXT_REASON_SEARCH_CLASS)
    if validation_rows.size < config.min_validation:
        return refused(CONTEXT_REASON_VALIDATION_STARVED)
    if min(validation_positives,
           int(validation_rows.size) - validation_positives) < (
               config.min_validation_per_class):
        return refused(CONTEXT_REASON_VALIDATION_CLASS)
    fitted_rows = rows[stride_select(int(rows.size), config.max_labels)]
    labels = search.states[fitted_rows] == state
    if min(int(np.count_nonzero(labels)),
           int(labels.size) - int(np.count_nonzero(labels))) < 1:
        return refused(CONTEXT_REASON_SEARCH_CLASS, int(fitted_rows.size))
    logits = one_versus_rest(running_search[fitted_rows], state)
    weights = search_weights[fitted_rows]
    bins = search.bins[fitted_rows, plane].astype(np.int64)
    curve = anchor_curve(
        ordered_offsets(logits, labels, weights, bins,
                         non_increasing=prints_plane),
        bins, weights)
    # THE PER-CURVE GATE, K's shape: one strict improvement on the
    # DISJOINT held-out side, in the same one-vs-rest measure the curve
    # was fitted under, class-balanced.
    gate_rows = validation_rows[
        stride_select(int(validation_rows.size), config.max_labels)]
    gate_logits = one_versus_rest(running_validation[gate_rows], state)
    gate_labels = validation.states[gate_rows] == state
    gate_bins = validation.bins[gate_rows, plane].astype(np.int64)
    gate_weights = validation_weights[gate_rows]
    incumbent = float(np.sum(
        gate_weights * _binary_nll(gate_logits, gate_labels))
        / np.sum(gate_weights))
    candidate = float(np.sum(
        gate_weights * _binary_nll(gate_logits + curve[gate_bins],
                                   gate_labels))
        / np.sum(gate_weights))
    if not candidate + HEAD_GATE_SLACK < incumbent:
        return None, ContextCurve(
            state, plane, CONTEXT_REASON_GATE_FAILED, int(rows.size),
            positives, int(validation_rows.size), int(fitted_rows.size),
            incumbent, candidate)
    return curve, ContextCurve(
        state, plane, CONTEXT_REASON_ADOPTED, int(rows.size), positives,
        int(validation_rows.size), int(fitted_rows.size),
        incumbent, candidate)


# ---------------------------------------------------------------------
# The region entry point.
# ---------------------------------------------------------------------

def label_floor_refusal(search: np.ndarray, config: ContextConfig) -> str:
    """The two COUNT floors, answerable before a single bin exists.

    Hoistable by construction — both are counts over the label split, so a
    starved region refuses WITHOUT the region-wide ink pass the bins need.
    ``color_stack`` asks this first and :func:`fit_region_context` asks
    the same function, so the floors are stated once.
    """
    if int(np.count_nonzero(search)) < config.min_search:
        return CONTEXT_REASON_SEARCH_STARVED
    if int(np.count_nonzero(~np.asarray(search, np.bool_))) < (
            config.min_validation):
        return CONTEXT_REASON_VALIDATION_STARVED
    return ""


def fit_region_context(
    model: ColorQDAModel, detector: CMY8Detector | None,
    head: Cmy7Head | None, known_features: np.ndarray,
    known_bins: np.ndarray, states: np.ndarray, kinds: np.ndarray,
    search: np.ndarray, config: ContextConfig,
    *, binned_fraction: float,
    force_region_adoption: bool = False,
) -> ContextFit:
    """Fit A5 for one region and rule on it.

    Two gates, the ladder's landed shape.  Every curve must first earn
    itself on the disjoint held-out side (the one-vs-rest pre-gate); the
    surviving set then faces the standing THREE-WAY comparison — total
    strictly better by 1e-9, word not worse, dust not worse — measured in
    the space the region actually EMITS (per-plane binary loss for cmy8,
    joint multinomial loss for cmy7), class-balanced.  Either refusal
    returns NO head, and a region with no head emits the literal pre-P2
    arrays.

    ``force_region_adoption`` bypasses the REGION comparison and nothing
    else — a curve that failed its own pre-gate is still exactly zero —
    and reports under ``region_gate_forced``, so a forced adoption can
    never be read as one the comparison granted.
    """
    cmy8 = detector is not None
    pinned = not cmy8
    labels_word = int(np.count_nonzero(kinds == 0))
    labels_dust = int(np.count_nonzero(kinds == 1))
    labels_cert = int(np.count_nonzero(kinds < 0))
    heldout = ~search

    def refused(reason: str, curves: tuple[ContextCurve, ...] = ()
                ) -> ContextFit:
        return ContextFit(
            None, False, reason, config.variant, curves,
            int(np.count_nonzero(search)), int(np.count_nonzero(heldout)),
            labels_word, labels_dust, labels_cert, binned_fraction,
            *((CONTEXT_NLL_UNMEASURED,) * 6))

    starved = label_floor_refusal(search, config)
    if starved:
        return refused(starved)
    if not np.any(np.asarray(known_bins) >= 0):
        return refused(CONTEXT_REASON_NO_CELLS)

    scores = color_detect.qda_log_scores(model, known_features)
    if not cmy8 and head is not None:
        # A5 corrects what the region EMITS, so it reads the post-head
        # scores: the head is A4's calibration of the same six logits and
        # runs one rung earlier in the ladder.
        scores = augment(head.apply(scores[:, 1:] - scores[:, :1]))
    elif not cmy8:
        scores = augment(scores[:, 1:] - scores[:, :1])
    search_population = _Population(
        scores[search], np.asarray(states, np.int64)[search],
        np.asarray(known_bins, np.int8)[search],
        np.asarray(kinds, np.int8)[search])
    validation_population = _Population(
        scores[heldout], np.asarray(states, np.int64)[heldout],
        np.asarray(known_bins, np.int8)[heldout],
        np.asarray(kinds, np.int8)[heldout])
    supported = (
        detector.supported_planes if cmy8 else (True, True, True))

    offsets, curves = _fit_matrix_curves(
        search_population, validation_population, config,
        pinned_reference=pinned)
    head_applied = np.zeros(offsets.shape[:2], np.bool_)
    for curve in curves:
        if not curve.adopted:
            continue
        target = curve.column - 1 if pinned else curve.column
        head_applied[target, curve.plane] = True
    if cmy8:
        # A plane the detector erases to exactly zero can carry no
        # correction; its curves are dropped rather than emitted into
        # a column the calibration overwrites with 0.0 anyway.
        for plane in range(3):
            if supported[plane]:
                continue
            offsets[:, plane] = 0.0
            head_applied[:, plane] = False

    if not np.any(head_applied):
        return refused(CONTEXT_REASON_NO_CURVE, curves)
    head_candidate = ContextHead(
        LOCUS_STATES, config.variant, offsets, head_applied)
    incumbent = _region_losses(
        detector, validation_population, None, cmy8=cmy8)
    candidate = _region_losses(
        detector, validation_population, head_candidate, cmy8=cmy8)
    passed = (
        candidate[0] + HEAD_GATE_SLACK < incumbent[0]
        and _not_worse(candidate[1], incumbent[1])
        and _not_worse(candidate[2], incumbent[2])
    )
    adopted = passed or force_region_adoption
    return ContextFit(
        head_candidate if adopted else None,
        adopted,
        (CONTEXT_REASON_ADOPTED if passed
         else CONTEXT_REASON_REGION_FORCED if adopted
         else CONTEXT_REASON_REGION_GATE),
        config.variant, curves,
        int(np.count_nonzero(search)), int(np.count_nonzero(heldout)),
        labels_word, labels_dust, labels_cert, binned_fraction,
        incumbent[0], candidate[0], incumbent[1], candidate[1],
        incumbent[2], candidate[2])


def _not_worse(candidate: float, incumbent: float) -> bool:
    """A leg that was never measured cannot refuse the arm."""
    if (candidate == CONTEXT_NLL_UNMEASURED
            or incumbent == CONTEXT_NLL_UNMEASURED):
        return True
    return candidate <= incumbent + HEAD_GATE_SLACK


def emitted_llrs(detector: CMY8Detector, scores: np.ndarray) -> np.ndarray:
    """cmy8's EMITTED component LLRs from state scores: marginal + PAVA.

    The A5 seam on the CMY8 leaf, and the same three steps
    ``CMY8Detector.llrs`` takes after scoring — the degenerate-plane clip,
    the component erasure, the dust PAVA — reached from scores the matrix
    variant has already corrected, so nothing is re-derived from features
    the correction has left behind.
    """
    raw = color_detect.cmy8_marginal_llrs(scores)
    supported = detector.supported_planes
    out = np.empty_like(raw)
    for plane in range(3):
        if not supported[plane]:
            out[:, plane] = 0.0
            continue
        values = raw[:, plane]
        if detector.qda.degenerate or plane in detector.qda.clipped_planes:
            values = np.clip(
                values, -color_detect.DEGENERATE_LLR_CLIP,
                color_detect.DEGENERATE_LLR_CLIP)
        out[:, plane] = detector.calibrations[plane].llrs(values)
    return out


def _region_losses(
    detector: CMY8Detector | None, population: _Population,
    head: ContextHead | None, *, cmy8: bool,
) -> tuple[float, float, float]:
    """(total, word, dust) class-balanced loss in the EMITTED space.

    cmy8 emits three component LLRs, so it is judged per plane on the
    printed bits — the same measure A4b's region gate uses.  cmy7 emits a
    joint seven-state logit vector the exact pack7 demapper consumes, so
    it is judged by the multinomial loss of that vector.  Both variants
    are scored under their kind's measure, which is what makes the
    head-to-head a comparison of arms rather than of metrics.
    """
    scores = population.scores
    kinds = population.kinds
    if head is not None:
        scores = augment(head.apply_states(scores[:, 1:], population.bins)) \
            if not cmy8 else head.apply_states(scores, population.bins)
    if cmy8:
        if detector is None:
            raise ContextError("color context: cmy8 losses need a detector")
        values = emitted_llrs(detector, scores)
        bits = state_bits(8)[population.states].astype(np.uint8)
        supported = detector.supported_planes
        losses: list[np.ndarray] = []
        truths: list[np.ndarray] = []
        legs: list[np.ndarray] = []
        for plane in range(3):
            if not supported[plane]:
                continue
            losses.append(_binary_nll(values[:, plane], bits[:, plane]))
            truths.append(bits[:, plane])
            legs.append(kinds)
        if not losses:
            return (CONTEXT_NLL_UNMEASURED,) * 3
        loss = np.concatenate(losses)
        truth = np.concatenate(truths)
        kind = np.concatenate(legs)
        return (
            _balanced_mean(loss, truth),
            _balanced_mean(loss[kind == 0], truth[kind == 0]),
            _balanced_mean(loss[kind == 1], truth[kind == 1]),
        )
    loss = _multinomial_nll(scores, population.states)
    return (
        _balanced_mean(loss, population.states),
        _balanced_mean(loss[kinds == 0], population.states[kinds == 0]),
        _balanced_mean(loss[kinds == 1], population.states[kinds == 1]),
    )


__all__ = [
    "CONTEXT_MAX_LABELS", "CONTEXT_NLL_UNMEASURED", "CONTEXT_SWEEPS",
    "CONTEXT_REASON_ADOPTED", "CONTEXT_REASON_GATE_FAILED",
    "CONTEXT_REASON_NO_CELLS", "CONTEXT_REASON_NO_CURVE",
    "CONTEXT_REASON_REGION_FORCED", "CONTEXT_REASON_REGION_GATE",
    "CONTEXT_REASON_SEARCH_CLASS", "CONTEXT_REASON_SEARCH_STARVED",
    "CONTEXT_REASON_UNSUPPORTED", "CONTEXT_REASON_VALIDATION_CLASS",
    "CONTEXT_REASON_VALIDATION_STARVED", "CONTEXT_VARIANT",
    "CONTEXT_VARIANTS", "CONTEXT_VARIANT_MATRIX",
    "CONTEXT_VARIANT_OFF",
    "LOCUS_STATES", "ContextConfig", "ContextCurve", "ContextError",
    "ContextFit", "ContextHead", "ContextSummary",
    "emitted_llrs", "fit_region_context", "label_floor_refusal",
    "summarize_context",
]

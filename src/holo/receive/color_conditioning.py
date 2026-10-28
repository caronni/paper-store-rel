"""P9 / PK10: KnownField-conditioned marginalization (arm A4b, CMY8).

RECEIVE-DESIGN §6.2a, "P9 conditioning ruling".  Per cell, a component's
marginal is taken over the state SUBSET consistent with whatever the
KnownField already knows about its two SIBLING components: nothing known
leaves today's 4-vs-4 (the NORMAL case — all of lane 0, most early-lane
cells — not a fallback), one sibling leaves 2-vs-2, both leave 1-vs-1.
Conditioning on prior-barrier certified authority fabricates nothing
about the remaining component, and it creates no information where a
plane is physically dead.  The state-subset kernel itself is
``color_detect.cmy8_marginal_llrs``; what lives here is the CALIBRATION
that makes a conditioned score readable, and the gate that decides
whether to trust it.

KIND-NEUTRAL BY OMISSION.  CMY7 and K reach this module never: cmy7's
pack7 demapper consumes joint seven-state logits and no source of
partial cmy7 knowledge exists yet (the pack-codebook restriction would
be the same interface, built when one does), and K does not migrate.
The arm is a correct no-op there, not a disabled one.

WHY CALIBRATION IS THE SAFETY, NOT POLISH (risk R11).  A 2-vs-2 log
ratio is a DIFFERENT statistic from a 4-vs-4 one — different scale,
different tail — so feeding it to the map fitted for the unconditioned
axis would sharpen the model's overconfidence exactly where the receiver
has been given real knowledge.  The maps are therefore stratified by
(plane, conditioning-pattern): {none, sib1, sib2, both} per plane,
twelve strata, and M-given-C is deliberately a different stratum from
M-given-Y (different physical regimes, not one "arity 1").

TWO-SOURCE PROVENANCE (the v1.2 law).  (a) PRIMARY where dense:
CERT-CROSS cells — payload cells whose labelled plane AND at least one
sibling are prior-barrier certified — are deployment-exact material
(measured: hp c3-cmy8 carries C∩M = 31 tiles ≈ 123k cells for M|C;
xerox c2-cmy8 certified Y on 1,755 tiles, so its Y|C and Y|M strata are
dense).  Registered compromise R12: cert-cross tiles certified BECAUSE
they were easy, so the material is selection-biased toward clean cells.
(b) FLOOR everywhere, and the spatially unbiased mitigation of (a):
format furniture, which is arity-2 by construction, read through a
deterministic MASK.

THE SCOPED MASKING LAW (v1.3, pinned three ways).  Masking is a VIEW,
never a mutation.  It exists only in this module's two populations —
stratum fitting and gate evaluation — and is spelled as a PATTERN CODE
carried beside the cell, never as an edited KnownField.  One masked cell
contributes its full state to the QDA (which never sees this module),
its masked pattern to exactly one stratum (the reveal field below
partitions the furniture), and its true bits to context, registration,
ownership and anchoring (which read ``KnownRows`` directly).

THE REVEAL FIELD, and the one bit the spec did not have.  §6.2a names
``(131y + 17x) & 4`` as the reveal bit "selecting which sibling is
revealed for arity-1 strata", extending the &1 QDA split / &2 P1
sub-split family.  One bit chooses between two siblings but cannot also
choose the ARITY, and there are three nonempty patterns; so the field
here is the two-bit ``& 12`` whose LOW BIT IS THE SPEC'S &4 (it selects
sib1 vs sib2 exactly as written) and whose high bit adds "both".  The
four codes partition every furniture cell into exactly one pattern per
plane, which is what makes "exactly one stratum" literally true.  Code 0
means the cell sits out the conditioned fits: the pattern-∅ stratum is
NOT refitted here at all — it IS the incumbent detector's own map,
fitted on its own full population, so an unconditioned cell's evidence
stays byte-identical to today (the exact null this arm is judged
against).

MODULE PLACEMENT (deviation, recorded).  COLOR-UPLIFT-PLAN §3's module
table put this code in ``color_calibration``.  Written there it left that
file at 965 lines against the 1000-line rule with two unrelated heads in
it; the arm ladder's own module set (``color_stack``, ``color_locality``,
``color_fitting``, ``color_calibration``) gains one member instead.  No
seam moved: A4 and A4b are still fitted side by side in ``color_stack``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from . import color_detect
from .color_calibration import (
    HEAD_GATE_SLACK,
    Cmy7HeadError,
    class_balanced_weights,
)
from .color_detect import CMY8_SIBLINGS, CMY8Detector, ColorPAVAMap


class ConditioningError(Cmy7HeadError):
    """A shape or a type the A4b fitter refuses to work with."""


# Two bits of the standing ``131y + 17x`` site-key hash: 4 = the spec's
# named reveal bit (sib1), 8 = its companion (sib2).  Code 0 = the cell
# is not conditioned material; 3 = both siblings revealed.
CONDITIONING_REVEAL_MASK: Final = 12
CONDITIONING_REVEAL_SHIFT: Final = 2
# Patterns per plane: 0 = {}, 1 = {sib1}, 2 = {sib2}, 3 = {sib1, sib2}.
CONDITIONING_N_PATTERNS: Final = 4
# Per-stratum floors, in the CMY8 dust vocabulary
# (``color_detect.CMY8_CALIBRATION_MIN_CLASS_LABELS`` is 6): a stratum
# needs both binary classes represented well enough to fit a monotone
# map, and enough total mass that PAVA's 1/(N+2) clamp is not the whole
# model.  Below either floor the stratum falls back to the unconditioned
# marginal — the exact-null discipline, not an approximation.
CONDITIONED_MIN_CLASS_LABELS: Final = 6
CONDITIONED_MIN_LABELS: Final = 40
# The stratum's own held-out furniture pre-gate needs a population too
# (K's floor name, K's shape: A3 carries the identical structure one arm
# lower — a per-unit pre-gate before the region-level comparison).
CONDITIONED_MIN_VALIDATION: Final = 20
# Bounded cost: PAVA walks its unique scores in Python, and a late colour
# lane can present millions of certified cells.  Above this a stratum is
# subsampled by a deterministic stride in canonical site order — never a
# draw, and published so a run states what it fitted on.
CONDITIONED_MAX_LABELS: Final = 100_000
# The same bound one level up, on the CERT-CROSS material a region
# gathers before it is scored at all: four strata's worth, so no stratum
# is starved by the cap while a late lane's millions of certified cells
# cannot turn one region's fit into the run's memory peak.
CONDITIONING_MAX_CERT_CELLS: Final = 400_000

# A loss that was never measured — a starved stratum, an unsupported
# plane, a region that refused before the gate ran.  Negative, never NaN:
# a summary record must stay comparable by ``==`` (the R-delta identity
# test compares two whole region summaries), and a skipped measurement
# must not be readable as a very good 0.0.  Same convention as
# ``color_stack.HEAD_SATURATION_UNMEASURED`` and
# ``color_locality.NLL_UNMEASURED``.
CONDITIONING_NLL_UNMEASURED: Final = -1.0

# THE OVERRIDE-ONLY ARM (PK-CLEAN, RECEIVE-DESIGN 6.2a).  A4b is built,
# instrumented and measured, and on this corpus it does not earn a place
# in the standard ladder: an exact end-to-end null on the hp c3-cmy8
# uplift target (663 certificates cert-for-cert identical, M = 43, the
# bar unmet, fourteen consecutive region-gate refusals on the DUST leg)
# and net -5 ADDRESSES on the xerox c2-cmy8 non-regression capture, whose
# byte-exact close survives but whose finest lane gives back nine tiles.
# COLOR-UPLIFT-MEASUREMENTS 9 is the record.
#
# WHY THERE IS NO APPLICABILITY CONSTANT HERE.  NO statistic separated
# the lanes A4b helps from the ones it costs -- the harm tracks the
# SOURCE of a stratum's material (cert-cross, whose selection bias
# scales with how selective the certification was) and not any size,
# spread or ratio of it, so on hp the harmful strata are the
# material-RICHEST ones.  A threshold invented from that data would be a
# constant fitted to the very corpus that refused the arm.  PK10 parked
# the arm behind a FLAG instead; PK-CLEAN retired the flag, because a
# flag is still something to flip.  The arm is reachable ONLY from a
# supplemental lane's ``arm_override`` (``color_stack``), so the standard
# ladder has no branch that could engage it and the evidence emitted
# there is the same array objects the arm-never-built path produces.
#
# What a standard-ladder A4b would still wait for is the
# cert-versus-masked BALANCE rule -- how much deployment-exact but
# selection-biased cert-cross material may outvote the spatially
# unbiased masked-furniture floor (registered compromise R12, measured
# for the first time in 9.6).  That rule is NOT sweepable from this
# corpus: two captures, and the statistic that would have to separate
# them is confounded with how much of each page had already certified.

CONDITIONING_REASON_ADOPTED: Final = "adopted"
CONDITIONING_REASON_STARVED: Final = "search_class_starved"
CONDITIONING_REASON_HELDOUT_STARVED: Final = "heldout_starved"
CONDITIONING_REASON_GATE_FAILED: Final = "validation_gate_failed"
CONDITIONING_REASON_NO_STRATUM: Final = "no_stratum_adopted"
CONDITIONING_REASON_NO_CELLS: Final = "no_conditioned_cells"
CONDITIONING_REASON_UNSUPPORTED: Final = "plane_unsupported"
# PK4.3: adopted inside a SUPPLEMENTAL lane, with the region comparison
# measured and published but not consulted.  A distinct reason on purpose
# — ``adopted`` must keep meaning "the region comparison said yes", so a
# forced adoption can never be read as one.  Since PK-CLEAN it is the
# ONLY region-level verdict this arm can report: A4b runs only when a
# u-lane forced it, so ``region_gate_failed`` became unreachable and is
# retired (MEASUREMENTS §12).
CONDITIONING_REASON_REGION_FORCED: Final = "region_gate_forced"


def conditioning_pattern_codes(known_mask: np.ndarray) -> np.ndarray:
    """``(N, 3)`` pattern code per plane from a KnownField mask.

    Code ``(sib1_known) | (sib2_known) << 1`` with the siblings in
    ascending plane order (``color_detect.CMY8_SIBLINGS``).  A plane's own
    column never enters its own code.
    """
    mask = np.asarray(known_mask, np.bool_)
    if mask.ndim != 2 or mask.shape[1] != 3:
        raise ValueError("color conditioning: known mask must be (N, 3)")
    codes = np.zeros(mask.shape, np.int8)
    for plane in range(3):
        first, second = CMY8_SIBLINGS[plane]
        codes[:, plane] = (
            mask[:, first].astype(np.int8)
            + 2 * mask[:, second].astype(np.int8))
    return codes


def masking_reveal_codes(cells_yx: np.ndarray) -> np.ndarray:
    """The masked pattern each FORMAT-KNOWN cell contributes, ``(N,)``.

    Deterministic in the printed geometry alone — it never looks at a
    feature, a score, or a label — and disjoint from the &1 QDA split and
    the &2 P1 sub-split, so a cell's mask is independent of which side of
    either split it fell on.
    """
    cells = np.asarray(cells_yx, np.int64)
    if cells.ndim != 2 or cells.shape[1] != 2:
        raise ValueError("color conditioning: cells must be (N, 2) y/x")
    hashed = 131 * cells[:, 0] + 17 * cells[:, 1]
    return (
        (hashed & CONDITIONING_REVEAL_MASK) >> CONDITIONING_REVEAL_SHIFT
    ).astype(np.int8)


def pattern_view_mask(plane: int, pattern_codes: np.ndarray) -> np.ndarray:
    """``(N, 3)`` sibling-revealed view implied by one plane's patterns.

    This is the masking law's whole mechanism: the VIEW is derived from
    the pattern code, so nothing downstream can mistake it for the cell's
    knowledge.  The revealed sibling's value is always the cell's true
    bit — a revealed sibling is one the KnownField genuinely knows.
    """
    codes = np.asarray(pattern_codes, np.int64)
    view = np.zeros((codes.size, 3), np.bool_)
    first, second = CMY8_SIBLINGS[plane]
    view[:, first] = (codes & 1) != 0
    view[:, second] = (codes & 2) != 0
    return view


@dataclass(frozen=True, slots=True)
class ConditioningPopulation:
    """Labelled cells for A4b, with the masked pattern they are read at.

    One shape serves both populations the arm needs — the stratum fitting
    material and the held-out furniture the gates score — because they
    differ only in membership, never in meaning.  ``pattern`` IS the
    masked view (see :func:`pattern_view_mask`); ``bits`` are always the
    cell's TRUE printed bits, and ``labelled`` says which of them the
    KnownField actually resolved.
    """

    scores: np.ndarray            # (N, 8) float64 QDA log scores
    bits: np.ndarray              # (N, 3) uint8   true printed bits
    labelled: np.ndarray          # (N, 3) bool    which bits are known
    pattern: np.ndarray           # (N, 3) int8    masked pattern per plane
    kinds: np.ndarray             # (N,)   int8    0 word / 1 dust / -1 payload
    from_certificates: np.ndarray  # (N,)  bool    provenance of the label

    def __post_init__(self) -> None:
        rows = np.asarray(self.scores, np.float64)
        if rows.ndim != 2 or rows.shape[1] != 8:
            raise ValueError(
                "color conditioning: population scores must be (N, 8)")
        for name, width in (("bits", 3), ("labelled", 3), ("pattern", 3),
                            ("kinds", 0), ("from_certificates", 0)):
            value = np.asarray(getattr(self, name))
            expected = ((rows.shape[0], width) if width
                        else (rows.shape[0],))
            if value.shape != expected:
                raise ValueError(
                    f"color conditioning: {name} must have shape {expected}")

    @property
    def n_cells(self) -> int:
        return int(self.scores.shape[0])


@dataclass(frozen=True, slots=True)
class ConditionedStratum:
    """One (plane, pattern) stratum's calibration decision and counts.

    The three loss PAIRS are the pre-gate exactly as it read: total,
    word-only and dust-only, over this stratum's own held-out furniture
    cells.  They are published because the region-level refusal this
    packet measured is a DUST refusal, and a region number cannot say
    which stratum spent it.
    """

    plane: int
    pattern: int
    calibration: ColorPAVAMap | None
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


@dataclass(frozen=True, slots=True)
class Cmy8ConditionedHead:
    """The adopted strata, applied at emission.

    ``strata`` is indexed ``[plane][pattern]`` and is ``None`` wherever
    the stratum was starved, refused, or is the pattern-∅ incumbent.
    Applying the head is therefore an OVERWRITE of the conditioned cells
    on top of today's evidence: a cell whose plane has no known sibling,
    or whose stratum did not survive, keeps the byte-identical
    unconditioned value.
    """

    strata: tuple[tuple[ColorPAVAMap | None, ...], ...]

    def __post_init__(self) -> None:
        if (len(self.strata) != 3
                or any(len(row) != CONDITIONING_N_PATTERNS
                       for row in self.strata)
                or any(row[0] is not None for row in self.strata)):
            raise ConditioningError(
                "color conditioning: strata must be 3 planes x 4 patterns "
                "with an empty pattern-0 slot")

    def llrs(
        self,
        detector: CMY8Detector,
        features: np.ndarray,
        known_mask: np.ndarray,
        known_bits: np.ndarray,
    ) -> np.ndarray:
        """Final calibrated C/M/Y evidence under the KnownField."""
        return self._apply(
            detector,
            color_detect.cmy8_conditioned_llrs(
                detector.qda, features, known_mask, known_bits),
            known_mask)

    def llrs_from_scores(
        self,
        detector: CMY8Detector,
        scores: np.ndarray,
        known_mask: np.ndarray,
        known_bits: np.ndarray,
    ) -> np.ndarray:
        """:meth:`llrs` from PRE-COMPUTED state scores — the P2 seam.

        A5's multi-state matrix corrects the state scores upstream of
        this arm, so the two compose by handing the corrected scores down
        rather than by re-scoring features the correction has already
        left behind.  On uncorrected scores it is :meth:`llrs` value for
        value — the pair below is ``cmy8_conditioned_llrs``'s body with
        its one scoring call removed.
        """
        return self._apply(
            detector,
            (_clipped_marginals(detector, scores),
             _clipped_marginals(detector, scores, known_mask, known_bits)),
            known_mask)

    def _apply(
        self,
        detector: CMY8Detector,
        marginals: tuple[np.ndarray, np.ndarray],
        known_mask: np.ndarray,
    ) -> np.ndarray:
        raw, conditioned = marginals
        codes = conditioning_pattern_codes(known_mask)
        supported = detector.supported_planes
        result = np.empty_like(raw)
        for plane in range(3):
            if not supported[plane]:
                # A component-local erasure outranks every calibration:
                # the historical contract is an exact zero here.
                result[:, plane] = 0.0
                continue
            values = detector.calibrations[plane].llrs(raw[:, plane])
            for pattern in range(1, CONDITIONING_N_PATTERNS):
                stratum = self.strata[plane][pattern]
                if stratum is None:
                    continue
                selected = codes[:, plane] == pattern
                if not np.any(selected):
                    continue
                values[selected] = stratum.llrs(
                    conditioned[selected, plane])
            result[:, plane] = values
        return result


@dataclass(frozen=True, slots=True)
class Cmy8ConditioningFit:
    """One region's A4b verdict with the counts that produced it."""

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


@dataclass(frozen=True, slots=True)
class ConditioningSummary:
    """The published A4b record for one region (append-only diagnostics).

    The default instance is what a region reports when the arm never ran
    — force-null, a CMY7 region, a refused detector fit — and is
    distinguishable from "ran and refused" by its empty ``reason``.

    ``cells_arity1``/``cells_arity2`` count (cell, plane) MARGINALS in
    the region's emitted payload population, not cells: one payload cell
    on a C-certified tile contributes two arity-1 marginals (M and Y) and
    leaves C's own marginal unconditioned, and that pair count is what
    the decode actually consumes.
    """

    reason: str = ""
    adopted: bool = False
    cells_arity1: int = 0
    cells_arity2: int = 0
    cert_cells: int = 0
    masked_cells: int = 0
    validation_cells: int = 0
    strata: tuple[tuple[int, int, str, int, int], ...] = ()
    strata_deltas: tuple[tuple[int, int, float, float, float], ...] = ()
    incumbent_nll: float = CONDITIONING_NLL_UNMEASURED
    candidate_nll: float = CONDITIONING_NLL_UNMEASURED
    word_incumbent_nll: float = CONDITIONING_NLL_UNMEASURED
    word_candidate_nll: float = CONDITIONING_NLL_UNMEASURED
    dust_incumbent_nll: float = CONDITIONING_NLL_UNMEASURED
    dust_candidate_nll: float = CONDITIONING_NLL_UNMEASURED

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str):
            raise ConditioningError(
                "color conditioning: summary reason must be a string")
        if type(self.adopted) is not bool:
            raise ConditioningError(
                "color conditioning: summary adoption must be a bool")
        if any(type(value) is not int or value < 0 for value in (
                self.cells_arity1, self.cells_arity2, self.cert_cells,
                self.masked_cells, self.validation_cells)):
            raise ConditioningError(
                "color conditioning: summary counts must be nonnegative")
        if self.adopted and self.reason not in (
                CONDITIONING_REASON_ADOPTED,
                CONDITIONING_REASON_REGION_FORCED):
            raise ConditioningError(
                "color conditioning: an adopted summary must say so")

    @property
    def adopted_strata(self) -> int:
        return sum(1 for row in self.strata
                   if row[2] == CONDITIONING_REASON_ADOPTED)


def summarize_conditioning(
    fit: Cmy8ConditioningFit,
    *,
    cells_arity1: int,
    cells_arity2: int,
) -> ConditioningSummary:
    """Publish one region's A4b decision, counts and gate numbers."""
    return ConditioningSummary(
        reason=fit.reason,
        adopted=fit.adopted,
        cells_arity1=int(cells_arity1),
        cells_arity2=int(cells_arity2),
        cert_cells=fit.n_cert_cells,
        masked_cells=fit.n_masked_cells,
        validation_cells=fit.n_validation,
        strata=tuple(
            (row.plane, row.pattern, row.reason, row.n_cert, row.n_masked)
            for row in fit.strata),
        # candidate MINUS incumbent per leg: negative is better, and the
        # sign pattern names which leg a refusal spent.
        strata_deltas=tuple(
            (row.plane, row.pattern,
             row.candidate_nll - row.incumbent_nll,
             row.word_candidate_nll - row.word_incumbent_nll,
             row.dust_candidate_nll - row.dust_incumbent_nll)
            for row in fit.strata),
        incumbent_nll=fit.incumbent_nll,
        candidate_nll=fit.candidate_nll,
        word_incumbent_nll=fit.word_incumbent_nll,
        word_candidate_nll=fit.word_candidate_nll,
        dust_incumbent_nll=fit.dust_incumbent_nll,
        dust_candidate_nll=fit.dust_candidate_nll)


def _clipped_marginals(
    detector: CMY8Detector,
    scores: np.ndarray,
    known_mask: np.ndarray | None = None,
    known_bits: np.ndarray | None = None,
) -> np.ndarray:
    """The marginal step with the degenerate-plane clip, from scores."""
    return color_detect._clip_unsupported_planes(
        detector.qda,
        color_detect.cmy8_marginal_llrs(scores, known_mask, known_bits))


def _binary_nll(llrs: np.ndarray, bits: np.ndarray) -> np.ndarray:
    """Per-cell logistic loss of a printed-bit LLR against the truth."""
    sign = np.where(np.asarray(bits, np.int64) > 0, 1.0, -1.0)
    return np.logaddexp(0.0, -sign * np.asarray(llrs, np.float64))


def _balanced_mean(losses: np.ndarray, bits: np.ndarray) -> float:
    """Class-balanced mean loss — the measure the maps are fitted under.

    PAVA balances its two binary classes (``color_detect._pava_map``), so
    a gate that did not would judge a calibration under a different
    measure than the one it optimizes.  ``class_balanced_weights``
    normalizes to mean 1, so a balanced population reproduces the plain
    mean exactly.
    """
    if losses.size == 0:
        return 0.0
    weights = class_balanced_weights(np.asarray(bits, np.int64))
    return float(np.sum(weights * losses) / np.sum(weights))


def _stride_subsample(count: int, limit: int) -> np.ndarray:
    """Deterministic every-k-th selector; the identity below ``limit``."""
    if count <= limit:
        return np.arange(count)
    return np.linspace(0, count - 1, limit).astype(np.int64)


def _plane_llrs(
    population: ConditioningPopulation,
    detector: CMY8Detector,
    plane: int,
    rows: np.ndarray,
    *,
    conditioned: bool,
) -> np.ndarray:
    """Unconditioned or pattern-conditioned marginals for selected rows."""
    scores = population.scores[rows]
    allowed = (
        color_detect.cmy8_sibling_allowed(
            plane,
            pattern_view_mask(plane, population.pattern[rows, plane]),
            population.bits[rows])
        if conditioned else None
    )
    values = color_detect.cmy8_plane_marginal(scores, plane, allowed)
    if detector.qda.degenerate or plane in detector.qda.clipped_planes:
        values = np.clip(
            values,
            -color_detect.DEGENERATE_LLR_CLIP,
            color_detect.DEGENERATE_LLR_CLIP)
    return values


def _fit_stratum(
    detector: CMY8Detector,
    material: ConditioningPopulation,
    gate: ConditioningPopulation,
    plane: int,
    pattern: int,
) -> ConditionedStratum:
    """Fit and pre-gate one (plane, pattern) stratum."""
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
        # A stride can only lose a class if one was already vanishing;
        # refuse rather than fit a one-class map.
        return refused(CONDITIONING_REASON_STARVED, int(fitted_rows.size))
    calibration = color_detect.fit_component_pava(
        _plane_llrs(material, detector, plane, fitted_rows,
                    conditioned=True),
        fitted_labels)
    truth = gate.bits[validation, plane]
    kinds = gate.kinds[validation]
    incumbent_loss = _binary_nll(
        detector.calibrations[plane].llrs(
            _plane_llrs(gate, detector, plane, validation,
                        conditioned=False)),
        truth)
    candidate_loss = _binary_nll(
        calibration.llrs(
            _plane_llrs(gate, detector, plane, validation,
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
    # THE PRE-GATE IS A3'S SHAPE: one strict improvement on this
    # stratum's own held-out cells, with the standing THREE-WAY rule
    # reserved for the region comparison that follows
    # (``color_locality``'s per-window pre-gate is the same single test
    # one arm lower).  All three legs are MEASURED and published anyway,
    # because the region refusal this packet met is a DUST refusal and a
    # region number cannot say which stratum spent it.
    #
    # SWEPT, in the only sense that applies to a gate SHAPE (§9): making
    # the pre-gate three-way as well was built and measured on both
    # cmy8 captures.  It is strictly more conservative — it can only
    # drop strata — and measured it drops the ones carrying the largest
    # total and word gains, because on this corpus the DUST cost is
    # concentrated in exactly the cert-cross-fed strata (R12's
    # selection bias, visible per stratum in ``strata_deltas``: hp l01
    # C1 t-0.0364/w-0.0650/d+0.0230, M1 t-0.0042/w-0.0290/d+0.0470).
    # On xerox c2-cmy8 it keeps 2 strata of 9 and +11 certificates
    # where this shape keeps 8 and +19; on hp c3-cmy8 it converts a
    # region refusal into an adoption worth zero certificates.  Larger
    # measured gain, no measured harm on either capture, and the
    # landed precedent — so the single test ships and the three-way
    # variant is recorded, not adopted.
    passed = candidate[0] + HEAD_GATE_SLACK < incumbent[0]
    return ConditionedStratum(
        plane, pattern, calibration if passed else None,
        CONDITIONING_REASON_ADOPTED if passed
        else CONDITIONING_REASON_GATE_FAILED,
        n_cert, n_masked, int(fitted_rows.size), int(validation.size),
        incumbent[0], candidate[0], incumbent[1], candidate[1],
        incumbent[2], candidate[2])


def _region_losses(
    detector: CMY8Detector,
    gate: ConditioningPopulation,
    head: Cmy8ConditionedHead | None,
) -> tuple[float, float, float]:
    """(total, word, dust) class-balanced binary loss over every plane.

    REGIME-MATCHED by construction: the gate population is furniture,
    which is arity-2 in truth, and it is scored at each cell's MASKED
    pattern — so every stratum is judged in the deployment regime it will
    actually be applied in, and a cell masked to pattern ∅ contributes
    exactly the same loss to both arms.
    """
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
            _plane_llrs(gate, detector, plane, rows, conditioned=False))
        if head is not None:
            for pattern in range(1, CONDITIONING_N_PATTERNS):
                stratum = head.strata[plane][pattern]
                if stratum is None:
                    continue
                selected = gate.pattern[rows, plane] == pattern
                if not np.any(selected):
                    continue
                values[selected] = stratum.llrs(
                    _plane_llrs(gate, detector, plane, rows[selected],
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


def fit_conditioned_marginals(
    detector: CMY8Detector,
    material: ConditioningPopulation,
    gate: ConditioningPopulation,
) -> Cmy8ConditioningFit:
    """Fit A4b's pattern-stratified maps and rule on them.

    ONE gate decides, in A3's landed shape: each stratum must earn its
    own map on the held-out furniture cells read at ITS pattern.  A
    region with no surviving stratum returns NO head, and a region with
    no head emits byte-identical evidence to today (risk R3's
    discipline: the exact null is the same arrays, not an identity
    transform).

    The standing three-way REGION comparison — total, word leg, dust leg
    over the whole held-out furniture population — is still measured and
    published on every fit, but it no longer decides: since PK-CLEAN this
    arm runs only inside a supplemental lane, where the per-address
    retirement law already bounds it to the uncertified residue so a
    worse region model can cost no certificate, and where the gate was
    measured to be exactly what made the arm unreachable rather than
    unhelpful (§9.4/§9.8: refused on the DUST leg at all fourteen
    conditioned lanes while total and word improved).  The surviving
    strata are therefore adopted under ``region_gate_forced`` with the
    numbers that would have refused them reported beside the verdict.

    Returns a decision; it never raises on starvation.  A malformed
    population is a bug and does raise.
    """
    if not isinstance(detector, CMY8Detector):
        raise ConditioningError(
            "color conditioning: A4b needs a CMY8 detector")
    if not isinstance(material, ConditioningPopulation) or not isinstance(
            gate, ConditioningPopulation):
        raise ConditioningError(
            "color conditioning: populations must be ConditioningPopulation")
    supported = detector.supported_planes
    strata: list[ConditionedStratum] = []
    grid: list[list[ColorPAVAMap | None]] = [
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
    head = Cmy8ConditionedHead(
        tuple(tuple(row) for row in grid))  # type: ignore[arg-type]
    incumbent = _region_losses(detector, gate, None)
    candidate = _region_losses(detector, gate, head)
    return Cmy8ConditioningFit(
        head, True, CONDITIONING_REASON_REGION_FORCED,
        frozen, n_cert, n_masked, gate.n_cells,
        incumbent[0], candidate[0], incumbent[1], candidate[1],
        incumbent[2], candidate[2])



__all__ = [
    "CONDITIONED_MAX_LABELS", "CONDITIONED_MIN_CLASS_LABELS",
    "CONDITIONED_MIN_LABELS", "CONDITIONED_MIN_VALIDATION",
    "CONDITIONING_N_PATTERNS", "CONDITIONING_REASON_ADOPTED",
    "CONDITIONING_REASON_GATE_FAILED",
    "CONDITIONING_REASON_HELDOUT_STARVED",
    "CONDITIONING_REASON_NO_CELLS", "CONDITIONING_REASON_NO_STRATUM",
    "CONDITIONING_REASON_REGION_FORCED",
    "CONDITIONING_REASON_STARVED",
    "CONDITIONING_REASON_UNSUPPORTED", "CONDITIONING_REVEAL_MASK",
    "CONDITIONING_MAX_CERT_CELLS", "CONDITIONING_NLL_UNMEASURED",
    "CONDITIONING_REVEAL_SHIFT", "Cmy8ConditionedHead",
    "Cmy8ConditioningFit", "ConditionedStratum",
    "ConditioningError", "ConditioningPopulation", "ConditioningSummary",
    "conditioning_pattern_codes", "fit_conditioned_marginals",
    "masking_reveal_codes", "pattern_view_mask", "summarize_conditioning",
]

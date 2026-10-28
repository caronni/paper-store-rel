"""The color evidence stack: one gated arm ladder per region.

RECEIVE-DESIGN §6.2a.  One region's evidence model is chosen by a
sequential, greedily gated ladder of arms; every arm is adopted only
through the standing three-way held-out comparison

    total strictly better by 1e-9  AND  word not worse  AND  dust not worse

and every refusal falls back to a BIT-EXACT predecessor: the same fitted
model and the SAME feature array objects, never an identity transform.

Arms landed so far —

    A0 baseline (window-crop features)          PK2      standard ladder
    A1 region plane-registration correction     PK2      standard ladder
    A3 per-window photometric maps              PK4      u-lane ONLY
    A4 cmy7 kind head (scale + six offsets)     PK3      standard ladder
    A4b cmy8 KnownField-conditioned marginals   PK10     u-lane ONLY
    A5 the neighbourhood corrector              PK5      standard ladder

THE OVERRIDE-ONLY LAW (PK-CLEAN, RECEIVE-DESIGN §6.2a).  Two of these
arms — A3 and A4b — were measured on the whole corpus and could not
prove universal non-regression, and every applicability statistic
proposed for them was measured NOT to separate the lanes they help from
the lanes they tax (three for A3, none even constructible for A4b;
COLOR-UPLIFT-MEASUREMENTS §6/§7/§9, retired at §12).  They are therefore
not gated and not parked behind a flag: they are UNREACHABLE from the
standard ladder and run only inside their own supplemental lane, forced
by that lane's identity.  The reachability test is the ``arm_override``
argument itself — ``if arm_override == UPLIFT_ARM_A3`` — so there is no
constant to flip, no environment hatch, and no branch an ordinary,
mop-up or refinement level could take.  ``test_color_uplift_lanes``
pins it with a spy: a standard-ladder region processes without calling
either arm's fitter.

A4 carries TWO adoption conditions, and both are measured on different
populations by design: the head's own class-balanced validation gate on
held-out FURNITURE (color_calibration), and PK3.1's saturation FLOOR on
the region's own DEPLOYMENT population (:func:`deployment_saturation`).
The furniture gate cannot see the harm the head does to an unsaturated
lane — measured, it adopted in all twelve xerox c3-cmy7 lanes including
the one where the head strictly loses certificates — so the floor asks
the separate question "does this population have the pathology at all?".

A3 keeps its per-window pre-gate (each window's map must strictly
improve the incumbent model's held-out NLL on that window's own labels)
and the standing three-way region comparison on the refitted QDA.  Both
of those measure furniture — that limitation is registered, P6 is its
fix, its preview rides every u-a3 run as ``color.window_maps.cert_*``,
and it is why this arm's evidence is per-lane certificate deltas rather
than fit losses.

MEMORY OWNERSHIP.  The ladder takes its A0/A1 feature tuples inside a
mutable :class:`ArmFeatures` holder and CONSUMES them: the loser of the
A0/A1 choice is dropped as soon as the choice is made, and both are
dropped when A3's mapped tuple wins.  A region's feature tuples are the
largest transient the color path allocates (one ``(N, 3)`` float64 array
per window), so this is the difference between the ladder holding two of
them and holding three.  WHAT IT IS NOT is the peak: PK4's "+34% peak RSS
from holding three" was RETRACTED as a cross-run contention artifact —
measured one lane at a time, force-null 41,097 MiB vs A3-adopting 41,091
MiB, 0.01% apart (COLOR-UPLIFT-MEASUREMENTS §7.7).  The peak is set by
the finest rung's crops and futures, not by this ladder.  The ownership
rule stands on its own terms — do not hold what you have handed over —
and the caller must keep no other reference; the selected tuple comes
back on the result.

A4b is A4's cmy8 counterpart (:mod:`holo.receive.color_conditioning`):
each (plane, conditioning-pattern) stratum must earn its own map on
held-out furniture read at ITS pattern.  Its populations are built here
— the masked dust floor from the ownership selection, the cert-cross
primary material from the rows — because only this module sees both, and
the material is deliberately the INCUMBENT's calibration population
stratified (see the block in :func:`fit_region_stack`: a candidate
fitted on a different population than its rival turns the three-way gate
into a comparison of fitting regimes).  Ahead of the per-stratum gate it
asks the cheapest question first: does this region EMIT a single cell
with a certified sibling?  Where the answer is no (every lane 0) nothing
is gathered, nothing is fitted, and the evidence is byte-identical.  Its
REGION comparison is measured and published on all three legs but no
longer decides anything — the arm reaches this module only when a u-lane
forced it, so the verdict is always ``region_gate_forced`` and an
auditor reads the legs rather than a gate outcome (§9.4/§9.8: that gate,
not the material, is what made the arm unreachable).

One rung is still owed inside this one function (A2 per-window
registration).  The region loop in
:mod:`holo.receive.color_payload` keeps ownership of refusal reporting,
emission, and the region summary; this module owns only the choice.

FORCE-NULL.  ``HOLO_COLOR_STACK_FORCE_NULL`` is the campaign's ONE
remaining environment contract, read from the environment at every
:func:`fit_region_stack` call (never cached — a test or a harness run may
set it per process, and a stale cache would silently lie).  When truthy
the ladder is EXACTLY the PK2 skeleton: A0/A1 only — no window map, no
head, no conditioning and no context is ever fitted — and the selected
fit object is the one A0/A1 produced, untouched.  That is what makes the harness's
``--force-null`` differential mean "the receiver as it was" rather than
"the receiver with its gates closed".  It can only REMOVE behaviour, so
it is a contract rather than a knob; every constant the campaign SWEPT
is threaded instead, as :class:`StackConfig`.

SUPPLEMENTAL LANES (PK4.3, RECEIVE-DESIGN §6.2a).  An arm that cannot
prove UNIVERSAL non-regression is not gated: it is SCHEDULED, as its own
supplemental lane after the standard ladder, where the per-address
retirement law bounds it to the uncertified residue and makes it monotone
by construction.  ``fit_region_stack``'s ``arm_override`` is how that
lane says which arm it forces; it is lane-scoped configuration threaded
from ``LaneSpec.arm_override`` and is the ONLY way A3 or A4b runs at all.
It can never be ambient: there is no environment hatch for it, and an
ordinary lane's plan entry cannot carry one.

PK5 generalizes that law from ARMS to CONFIGURATIONS with a third
override, :data:`UPLIFT_ARM_OFF`: the supplemental BASELINE lane, which
runs the residue on the pre-campaign skeleton so that a configuration
change which RE-TIMES the cascade cannot strand a tile the old path
would have certified.  Same monotonicity, same absence of a gate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Final

import numpy as np

from ..core import channel
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from . import color_detect
from .color_anchoring import _Rows
from .color_calibration import Cmy7Head, Cmy7HeadFit, fit_cmy7_head
from .color_conditioning import (
    CONDITIONING_MAX_CERT_CELLS,
    CONDITIONING_REASON_NO_CELLS,
    ConditioningPopulation,
    ConditioningSummary,
    conditioning_pattern_codes,
    fit_conditioned_marginals,
    masking_reveal_codes,
    summarize_conditioning,
)
from .color_context import (
    CONTEXT_NLL_UNMEASURED,
    CONTEXT_VARIANT_OFF,
    ContextConfig,
    ContextSummary,
    fit_region_context,
    label_floor_refusal,
    summarize_context,
)
from .color_fitting import _DetectorFit, _OwnerSelection, _fit_detector
from .color_neighbourhood import region_context_bins
from .color_locality import (
    NLL_UNMEASURED,
    REASON_ADOPTED,
    REASON_REGION_GATE_FAILED,
    WindowPhotometryConfig,
    WindowPhotometrySummary,
    cert_population_preview,
    fit_window_photometry,
)
from .color_registration import PlaneResidual
from .types import UPLIFT_ARMS


# PK4.3 arm overrides, as the vocabulary this module IMPLEMENTS.  The
# lane vocabulary itself lives in ``lane_uplift`` (a lane id is not a
# color concept); these two names are the ladder's own reading of it,
# and `test_color_uplift_lanes` pins that the two agree.
#
# UPLIFT_ARM_A3 and UPLIFT_ARM_A4B are the ONLY way their arms run at
# all (the override-only law in the module note): there is no constant,
# flag or environment variable that could engage either from an ordinary,
# mop-up or refinement level.  Forcing a lane does NOT force the arm's
# construction — every per-window and per-stratum pre-gate still rules —
# and it touches no other arm and not force-null.  What a forced A4b lane
# additionally does is stop CONSULTING its region comparison (still
# measured, still published, verdict `region_gate_forced`), because that
# gate is what measurement showed made the arm unreachable rather than
# unhelpful.
#
# UPLIFT_ARM_OFF is the ruling that generalizes the supplemental-lane law
# from ARMS to CONFIGURATIONS (PK5).  It disables every campaign arm for
# its lane — the ladder collapses to the pre-campaign A0/A1 skeleton,
# exactly as ``--force-null`` does process-wide — so the lane re-reads the
# residue through the evidence path the receiver had BEFORE the campaign.
# It exists because a ladder-configuration change re-times cascades: when
# an adopted arm moves fifty to a hundred tiles to an earlier barrier, the
# later barriers face a different residue and a handful of tiles the old
# path certified can be stranded (MEASURED at PK5: six across the corpus
# against 255 gained).  Those tiles are not evidence damage and they do
# not need a gate or a floor — the OLD PATH'S OWN TAIL IS SCHEDULABLE, by
# the same per-address retirement law that makes every u-lane monotone.
# It is ordered FIRST among the overrides (``lane_uplift.UPLIFT_ARMS``) so
# the old configuration finishes its reachable set before a forced arm
# reads what is left.
UPLIFT_ARM_A3: Final = "a3"
UPLIFT_ARM_A4B: Final = "a4b"
UPLIFT_ARM_OFF: Final = "off"

# The standing held-out gate's slack.  It absorbs float re-association
# only; it is not a tolerance policy (color_payload's furniture
# non-regression comparison since the v0.31 policy family).
STACK_GATE_SLACK = 1e-9

FORCE_NULL_ENV: Final = "HOLO_COLOR_STACK_FORCE_NULL"
FORCE_NULL_REASON: Final = "force_null"
# Reported when a region has no held-out population to fit a head on
# (a CMY8 region never reaches this code; a CMY7 region without one
# means the detector fit refused before it could carry one).
HEAD_NO_POPULATION_REASON: Final = "no_heldout_population"

# A4's SATURATION FLOOR (PK3.1).  The head is adopted only where the
# DEPLOYMENT population exhibits the pathology it treats: the fraction of
# emitted payload cells whose PRE-head L-infinity divisor exceeds 1 must
# reach this floor.
#
# Why a second condition at all.  The head's own gate is a class-balanced
# validation NLL on known FURNITURE, and MEASURED on xerox c3-cmy7 it
# adopted in all twelve lanes — including the one lane where the head
# strictly LOSES certificates (l00, 2 ppc: 295 live, a strict subset of
# the null arm's 333, with 262 of the 295 survivors paying BP margin,
# sign test p=3.6e-77; COLOR-UPLIFT-MEASUREMENTS §4.5.1).  Furniture NLL
# cannot see that: deflating honest LLRs is free in NLL and expensive in
# BP margin.  What separates the lanes is where the evidence actually
# lives — l00's payload cells saturate 13.1% of the bound while every
# lane the head helps saturates 45-68%.  Where evidence is not clipped,
# there is no bound-induced overconfidence to cure and the head is a pure
# tax; where most of the evidence IS a clipped constant, cooling restores
# its dynamic range.
#
# The value is SWEPT, not chosen (PK3.1, §4.5.2): the twelve measured
# per-lane saturations of xerox c3-cmy7 leave one wide empty band,
# between the coarse lanes (0.117-0.221, which contributed ZERO of the
# head's twelve gained addresses and FOUR of its five lost ones) and the
# fine ones (>=0.455, where every measured gain is).  All four swept
# candidates (0.15/0.20/0.25/0.30) buy the same measured outcome, so the
# choice is margin: 0.30 sits deepest inside the band (0.079 / 0.155),
# so lane-to-lane drift cannot flip a rung, and a higher floor withholds
# the head in the conservative direction.  The second capture agrees from
# below: xerox c2-cmy7's coarse lane measures 0.050 pre-head, and the
# gate accepted a head there.
# RE-SWEPT at PK4.1 (COLOR-UPLIFT-MEASUREMENTS §6.2).  A3 lowers the
# pre-head saturation of every lane it adopts into — better-conditioned
# features produce less extreme QDA scores — so PK3.1's band was measured
# on a distribution the new arm moves, and the two floors had to be swept
# JOINTLY on the post-A3 landscape.
HEAD_SATURATION_FLOOR: Final = 0.30
HEAD_SATURATION_REASON: Final = "saturation_below_floor"
# Reported saturation when no head fit ever needed measuring (force-null,
# cmy8, a starved or gate-refused head): the measurement is skipped, and
# a skipped measurement must not be readable as 0.0.
HEAD_SATURATION_UNMEASURED: Final = -1.0
_FALSEY: Final = frozenset({"", "0", "false", "no", "off"})


def force_null_enabled() -> bool:
    """True when the campaign's escape hatch is set in the environment."""
    return os.environ.get(FORCE_NULL_ENV, "").strip().lower() not in _FALSEY


@dataclass(frozen=True, slots=True)
class StackConfig:
    """Every SWEPT constant the ladder reads, as ONE explicit argument.

    PK-CLEAN's hatch consolidation.  Until now each sweepable constant
    had its own environment variable, read deep inside the arm that used
    it; a production module therefore depended on ambient process state
    that no caller declared.  They are now one frozen record, threaded
    the way ``arm_override`` already was — ``ProductionColorPayload`` →
    ``collect_color_evidence`` → :func:`fit_region_stack` — with the
    default instance holding exactly the constants the policy token
    names.  The production runtime never passes one; only the campaign
    harness does, at its own entry point, and the EFFECTIVE values are
    published per region so a swept run states its own numbers.

    ``HOLO_COLOR_STACK_FORCE_NULL`` is deliberately NOT here: it is a
    contract ("the receiver as it was"), it can only remove behaviour,
    and a harness must be able to assert it process-wide across code
    paths that never see this record.
    """

    window_photometry: WindowPhotometryConfig = field(
        default_factory=WindowPhotometryConfig)
    head_saturation_floor: float = HEAD_SATURATION_FLOOR
    context: ContextConfig = field(default_factory=ContextConfig)

    def __post_init__(self) -> None:
        floor = float(self.head_saturation_floor)
        # A THRESHOLD on a fraction, so nonnegative and finite.  It is not
        # itself bounded by 1: the head adopts on ``saturation >= floor``,
        # so a floor above 1.0 is the one value that refuses EVERY
        # population — which is how the suite reaches the refusal branch
        # on the pathological channel, whose emitted cells saturate 100%.
        if not np.isfinite(floor) or floor < 0.0:
            raise ValueError(
                "color stack: the head saturation floor must be a "
                "nonnegative fraction threshold")
        object.__setattr__(self, "head_saturation_floor", floor)


@dataclass(slots=True)
class ArmFeatures:
    """The A0/A1 feature tuples, handed to the ladder as OWNED memory.

    A region's feature tuples are the largest transient in the color
    path, so the ladder drops each one the moment no arm can still select
    it (see the module note).  A caller passes this holder and keeps no
    other reference; ``None`` means "already consumed".
    """

    base: tuple[np.ndarray, ...] | None
    corrected: tuple[np.ndarray, ...] | None


@dataclass(frozen=True, slots=True)
class RegionStackResult:
    """The arm ladder's outcome for one region/page.

    ``selected_fit`` is ``None`` exactly when no arm produced a usable
    detector; ``refusal_reason`` then carries the fitter's own message
    (empty string when a fit was selected).  ``selected_features`` is the
    feature tuple the selected arm was fitted on — the caller emits from
    it, so a non-adopted arm returns the predecessor's own tuple object.
    """

    selected_fit: _DetectorFit | None
    selected_features: tuple[np.ndarray, ...]
    baseline_fit: _DetectorFit | None
    adopted: bool
    refusal_reason: str
    # P1 (append-only): the A4 cmy7 head's verdict, empty string for a
    # cmy8 region (which has no head) and for a refused detector fit.
    # ``head_temperature`` is what the region EMITS through (1.0 whenever
    # no head is applied, including a head fitted and then refused by the
    # saturation floor); ``head_fit`` still carries the fitted numbers.
    head_reason: str = ""
    head_adopted: bool = False
    head_temperature: float = 1.0
    head_fit: Cmy7HeadFit | None = None
    # PK3.1 (append-only): the deployment-population saturation the floor
    # gated on — the PRE-head fraction of emitted payload cells at the
    # L-infinity bound, or ``HEAD_SATURATION_UNMEASURED`` when no fitted
    # head ever reached the floor.
    head_saturation_fraction: float = HEAD_SATURATION_UNMEASURED
    # PK4.1 (append-only): the EFFECTIVE floor the line above was judged
    # against, published so a swept run states its own number.
    head_saturation_floor: float = HEAD_SATURATION_UNMEASURED
    # PK4 / A3 (append-only): the per-window photometric maps, as one
    # published record (``color_locality.WindowPhotometrySummary``).  Its
    # ``reason`` carries the region-level verdict and its counts carry the
    # per-window ones; the default instance is what force-null reports,
    # where no constant was ever read and no map ever fitted.
    window_photometry: WindowPhotometrySummary = WindowPhotometrySummary()
    # PK10 / A4b (append-only): the KnownField-conditioned marginals, as
    # one published record (``color_conditioning.ConditioningSummary``).
    # The default instance — empty reason — is what a CMY7 region, a
    # force-null run, and a refused detector fit all report.
    conditioning: ConditioningSummary = ConditioningSummary()
    # PK5 / A5 (append-only): the neighbourhood corrector, as one
    # published record (``color_context.ContextSummary``).  Kind-agnostic
    # like A3 — both kinds fit it — so the default instance's empty
    # reason means "the arm never ran", never "this codec has none".
    context: ContextSummary = ContextSummary()
    # PK5 (append-only): the per-row ``(N, 3)`` context bins the emitted
    # cells are corrected through, in the caller's row order, or ``None``
    # whenever no context head was adopted.  They ride the result because
    # the ladder computes them once (one region-wide ink map) and the
    # emission loop must not rebuild them per row.
    context_bins: tuple[np.ndarray, ...] | None = None


def _improves(
    candidate: _DetectorFit,
    selected: _DetectorFit | None,
) -> bool:
    """The standing three-way furniture-non-regression comparison."""
    if selected is None:
        return True
    return (
        candidate.heldout_loss + STACK_GATE_SLACK < selected.heldout_loss
        and candidate.word_heldout_loss
        <= selected.word_heldout_loss + STACK_GATE_SLACK
        and candidate.dust_heldout_loss
        <= selected.dust_heldout_loss + STACK_GATE_SLACK
    )


def deployment_saturation(
    fit: _DetectorFit,
    features: tuple[np.ndarray, ...],
    emission_masks: tuple[np.ndarray, ...],
) -> float:
    """The PRE-head saturated fraction of the cells this region will emit.

    Exactly the population and the divisor the emitted canary uses
    (``color_payload``: payload rows only, emission mask applied,
    ``divisor > 1``), measured before any head is attached — so the floor
    reads the pathology as the pre-P1 receiver saw it, and the two
    numbers in one run are a true before/after pair.

    Returns 0.0 for a region that emits nothing, which the floor then
    refuses: a head with no deployment population has no evidence for its
    own adoption.
    """
    emitted = 0
    saturated = 0
    for row_features, emit in zip(
            features[:len(emission_masks)], emission_masks, strict=True):
        if not np.any(emit):
            continue
        cells, hits = fit.pre_head_saturation_counts(row_features[emit])
        emitted += cells
        saturated += hits
    return 0.0 if not emitted else saturated / emitted


def emitted_conditioning_arities(
    payload_rows: tuple[_Rows, ...],
    emission_masks: tuple[np.ndarray, ...],
) -> tuple[int, int]:
    """``(arity-1, arity-2)`` MARGINALS in the region's emitted cells.

    A4b's deployment-population precondition, and the published counts.
    Only CERTIFIED knowledge conditions: format furniture is excluded
    here even though the KnownField knows it exactly, because a furniture
    cell's evidence is erased by the certification chain before any bit
    of it is used (RECEIVE-DESIGN §6.3 step 3).  Conditioning it would
    move emitted bytes, change every block digest, and buy no decode —
    the wrong side of a wrong-certificate risk trade.
    """
    arity1 = 0
    arity2 = 0
    for row, emit in zip(
            payload_rows[:len(emission_masks)], emission_masks, strict=True):
        if not np.any(emit):
            continue
        mask = np.asarray(row.known_component_mask, np.bool_)[emit]
        certified = mask & (
            np.asarray(row.furniture_kind, np.int8)[emit] < 0)[:, None]
        codes = conditioning_pattern_codes(certified)
        arity1 += int(np.count_nonzero((codes == 1) | (codes == 2)))
        arity2 += int(np.count_nonzero(codes == 3))
    return arity1, arity2


def _furniture_population(
    model: color_detect.ColorQDAModel,
    selection: _OwnerSelection,
    known_features: np.ndarray,
    rows: np.ndarray,
) -> ConditioningPopulation:
    """Format-known cells read at their MASKED pattern.

    Furniture is arity-2 in truth, so its pattern here is the reveal
    field's, never the KnownField's — the scoped masking law's whole
    mechanism, and the reason this population is spatially unbiased where
    the cert-cross material is not (R12).  Two callers with two row sets:
    the stratum material takes the incumbent's own dust population, the
    gate takes the held-out furniture the standing comparison scores.
    """
    states = np.asarray(selection.states, np.int64)[rows]
    bits = channel.states_to_planes(states.astype(np.int8))
    reveal = masking_reveal_codes(selection.keys[rows][:, 1:])
    return ConditioningPopulation(
        scores=color_detect.qda_log_scores(model, known_features[rows]),
        bits=np.asarray(bits, np.uint8),
        labelled=np.ones((rows.size, 3), np.bool_),
        pattern=np.repeat(reveal[:, None], 3, axis=1),
        kinds=np.asarray(selection.kinds, np.int8)[rows],
        from_certificates=np.zeros(rows.size, np.bool_))


def _cert_cross_population(
    model: color_detect.ColorQDAModel,
    row_tuple: tuple[_Rows, ...],
    features: tuple[np.ndarray, ...],
) -> ConditioningPopulation | None:
    """The PRIMARY material: payload cells with >= 2 certified components.

    A cell needs a certified label for the plane being calibrated AND at
    least one certified sibling to sit in a conditioned stratum, so the
    gather is exactly ``two or more known components on a payload cell``
    — the population ``_owner_selection`` cannot supply, because a
    partially certified cell resolves no state and is therefore not an
    owner.  Deduplicated in the SAME canonical order ownership uses
    (ascending patch id, first window wins) so the two populations can
    never disagree about who owns a cell.  Unlike the furniture floor
    these cells keep their TRUE pattern: this is deployment-exact
    material and masking it would throw away the reason it is primary.
    """
    cells: list[np.ndarray] = []
    gathered: list[np.ndarray] = []
    bits: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    for ordinal, window in sorted(
            enumerate(row_tuple),
            key=lambda pair: int(pair[1].patch.patch_id)):
        mask = np.asarray(window.known_component_mask, np.bool_)
        chosen = np.flatnonzero(
            (np.asarray(window.furniture_kind, np.int8) < 0)
            & (mask.sum(axis=1) >= 2))
        if chosen.size == 0:
            continue
        cells.append(np.asarray(window.page_cells_yx, np.int64)[chosen])
        gathered.append(
            np.asarray(features[ordinal], np.float64)[chosen])
        bits.append(
            np.asarray(window.known_component_bits, np.uint8)[chosen])
        masks.append(mask[chosen])
    if not cells:
        return None
    page_cells = np.concatenate(cells)
    # One region is one page, so (y, x) is a complete identity here.
    _unique, first = np.unique(
        page_cells[:, 0] * (int(page_cells[:, 1].max()) + 1)
        + page_cells[:, 1], return_index=True)
    if first.size > CONDITIONING_MAX_CERT_CELLS:
        first = first[np.linspace(
            0, first.size - 1, CONDITIONING_MAX_CERT_CELLS).astype(np.int64)]
    known = np.concatenate(masks)[first]
    return ConditioningPopulation(
        scores=color_detect.qda_log_scores(
            model, np.concatenate(gathered)[first]),
        bits=np.concatenate(bits)[first],
        labelled=known,
        pattern=conditioning_pattern_codes(known),
        kinds=np.full(first.size, -1, np.int8),
        from_certificates=np.ones(first.size, np.bool_))


def _concatenate_populations(
    left: ConditioningPopulation,
    right: ConditioningPopulation | None,
) -> ConditioningPopulation:
    if right is None:
        return left
    return ConditioningPopulation(
        scores=np.concatenate((left.scores, right.scores)),
        bits=np.concatenate((left.bits, right.bits)),
        labelled=np.concatenate((left.labelled, right.labelled)),
        pattern=np.concatenate((left.pattern, right.pattern)),
        kinds=np.concatenate((left.kinds, right.kinds)),
        from_certificates=np.concatenate(
            (left.from_certificates, right.from_certificates)))


def fit_region_stack(
    spec: FormatSpec,
    selection: _OwnerSelection,
    row_tuple: tuple[_Rows, ...],
    arms: ArmFeatures,
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual],
    *,
    emission_masks: tuple[np.ndarray, ...],
    arm_override: str | None = None,
    stack_config: StackConfig | None = None,
) -> RegionStackResult:
    """Run the arm ladder for one region and return the selected arm.

    ``arms`` holds the A0 window-crop features and the A1
    registration-corrected ones (``corrected is None`` when the residual
    proposal left the acquisition and is therefore ineligible), and is
    CONSUMED: the ladder clears each slot as soon as no arm can still
    select it, so the caller must keep no other reference to them (see
    the module's memory-ownership note).  ``row_tuple`` is A3's
    neighbourhood geometry (window bboxes in page cells, rows only);
    ``residuals`` is A2's declared input and is still unread.

    ``emission_masks`` are the per-PAYLOAD-row emission masks in the
    caller's row order (payload rows first, label rows after).  A4's
    saturation floor is a claim about the population the region will
    actually EMIT, so the ladder has to be told what that is; the
    argument is keyword-only and REQUIRED so no caller can quietly
    disable the floor by forgetting it.

    ``arm_override`` (PK4.3) is a SUPPLEMENTAL lane's forced arm, one of
    :data:`UPLIFT_ARMS`, threaded from that lane's own identity — never
    from the environment, and never set on an ordinary, mop-up or
    refinement level.  It is the ONLY thing that makes A3 or A4b run:
    the standard ladder has no branch that reaches either (the
    override-only law in the module note).  :data:`UPLIFT_ARM_OFF` is the
    override that removes rather than forces: it runs this lane on the
    pre-campaign A0/A1 skeleton.

    ``stack_config`` is the campaign harness's explicit sweep record
    (:class:`StackConfig`); ``None`` — every production caller — is the
    frozen constants the policy token names.

    Deterministic and RNG-free: every arm is a pure function of
    canonically ordered inputs.  ONE environment read sits here and
    nowhere else in the color stack: the force-null contract, which can
    only REMOVE behaviour, read per call and never cached.
    """
    del residuals
    if arm_override is not None and arm_override not in UPLIFT_ARMS:
        raise ValueError(f"unregistered uplift arm {arm_override!r}")
    config = StackConfig() if stack_config is None else stack_config
    # The supplemental BASELINE lane is the force-null ladder, lane-scoped:
    # one flag, one meaning, no second skeleton to keep in step.
    force_null = force_null_enabled() or arm_override == UPLIFT_ARM_OFF
    baseline_fit: _DetectorFit | None = None
    selected_fit: _DetectorFit | None = None
    selected_features = arms.base
    adopted = False
    reason = ""
    try:
        baseline_fit = _fit_detector(spec, selection, arms.base)
    except ValueError as exc:
        reason = str(exc)
    try:
        candidate_fit = (
            None if arms.corrected is None
            else _fit_detector(spec, selection, arms.corrected)
        )
    except ValueError:
        candidate_fit = None
    if baseline_fit is not None:
        selected_fit = baseline_fit
    if candidate_fit is not None and _improves(candidate_fit, selected_fit):
        selected_fit = candidate_fit
        selected_features = arms.corrected
        adopted = True
    # The A0/A1 loser can never be selected again: drop it here, before
    # A3 allocates a third tuple against it.
    arms.base, arms.corrected = None, None

    # A3 (P0): per-window photometric maps, fitted against the INCUMBENT
    # arm's own region QDA and applied to the INCUMBENT arm's features —
    # so the region refit below sees exactly one change.  Two gates:
    # color_locality's per-window pre-gate decides which windows carry a
    # map at all, and the standing three-way comparison then decides
    # whether the refitted region model replaces its predecessor.  A
    # region where no window earned a map refuses WITHOUT allocating a
    # mapped tuple — an exact null costs one wasted QDA fit and nothing
    # else.
    #
    # OVERRIDE-ONLY (PK-CLEAN).  The arm runs if and only if a
    # supplemental lane forced it.  It used to run on every lane and then
    # refuse at a parked region dispersion floor; that floor and its
    # normalized successor are RETIRED (measured non-separating on 27
    # lanes of two captures — MEASUREMENTS §6.3/§7.4/§12), so what is left
    # is the arm the campaign measured at floor 0 and the scheduling law
    # that makes it monotone.  The standard ladder therefore does not fit
    # window maps at all: same evidence as before, one fewer QDA pass.
    photometry: WindowPhotometryConfig | None = (
        config.window_photometry
        if not force_null and arm_override == UPLIFT_ARM_A3 else None)
    window_photometry = WindowPhotometrySummary()
    if selected_fit is not None and photometry is not None:
        maps = fit_window_photometry(
            selected_fit.model, selection, row_tuple, selected_features,
            photometry)
        window_reason = maps.arm_reason
        cert_preview = (0, NLL_UNMEASURED, NLL_UNMEASURED)
        if not window_reason:
            try:
                mapped_fit: _DetectorFit | None = _fit_detector(
                    spec, selection, maps.features)
            except ValueError:
                mapped_fit = None
            if mapped_fit is None:
                window_reason = REASON_REGION_GATE_FAILED
            else:
                # P6 preview (report-only): the same comparison the gate
                # below makes, scored on prior-barrier CERTIFIED payload
                # cells instead of held-out furniture.
                cert_preview = cert_population_preview(
                    selected_fit.model, mapped_fit.model, selection,
                    selected_features, maps.features)
                if _improves(mapped_fit, selected_fit):
                    selected_fit = mapped_fit
                    selected_features = maps.features
                    window_reason = REASON_ADOPTED
                else:
                    window_reason = REASON_REGION_GATE_FAILED
        window_photometry = WindowPhotometrySummary(
            accepted=maps.accepted, refused=maps.refused,
            reasons=maps.reasons, reason=window_reason,
            adopted=window_reason == REASON_ADOPTED, pooled=maps.pooled,
            prior_labels=photometry.prior_labels,
            cert_cells=cert_preview[0],
            cert_incumbent_nll=cert_preview[1],
            cert_mapped_nll=cert_preview[2])
        # Whatever A3's verdict, the tuple the region did NOT select is
        # dead the moment the gate rules.
        del maps

    # A4 (P1): the cmy7 head is fitted on the SELECTED arm's held-out
    # scores, so it must run after the arm choice, not inside it.  A head
    # is a pure post-transform of that arm's scores: it changes no
    # feature array, no arm verdict, and no gate above.
    head_fit: Cmy7HeadFit | None = None
    head_reason = ""
    head: Cmy7Head | None = None
    saturation = HEAD_SATURATION_UNMEASURED
    floor = HEAD_SATURATION_UNMEASURED
    if selected_fit is not None and spec.codec_family is Family.CMY7:
        if force_null:
            head_reason = FORCE_NULL_REASON
        elif selected_fit.heldout_population is None:
            head_reason = HEAD_NO_POPULATION_REASON
            selected_fit = replace(selected_fit, head_reason=head_reason)
        else:
            population = selected_fit.heldout_population
            head_fit = fit_cmy7_head(
                population.relative_scores,
                population.states,
                population.site_keys,
                qda_search_site_keys=population.search_site_keys)
            head_reason = head_fit.reason
            head = head_fit.head
            if head is not None:
                # The floor runs LAST, and only on a head the furniture
                # gate already accepted: it is the more expensive of the
                # two conditions (one pre-head scoring pass over the
                # deployment population) and a head refused upstream
                # would pay it for nothing.  Order is cost, not meaning —
                # both conditions must hold to adopt.
                saturation = deployment_saturation(
                    selected_fit, selected_features, emission_masks)
                floor = config.head_saturation_floor
                if saturation < floor:
                    head = None
                    head_reason = HEAD_SATURATION_REASON
            selected_fit = replace(
                selected_fit,
                cmy7_head=head,
                head_reason=head_reason)

    # A4b (P9/PK10): KnownField-conditioned marginalization, cmy8 only.
    # It runs after A4 for the same reason A4 runs after A3 — it is a
    # post-transform of the SELECTED arm's evidence and must see the arm
    # the region actually emits through — and it is a strict no-op on
    # cmy7 (no head is fitted, no population gathered, the reason stays
    # empty so not even a diagnostic key appears).
    # OVERRIDE-ONLY (PK-CLEAN).  The arm runs if and only if a
    # supplemental lane forced it; on every ordinary, mop-up and
    # refinement level it is ABSENT, not gated.  It used to be reachable
    # in the ladder behind a park FLAG; the flag is retired and the
    # reachability test is the override itself, so there is nothing left
    # to flip.  Absent means the summary stays the default instance (not
    # one ``color.conditioning.*`` diagnostic key is emitted) and
    # ``selected_fit`` is never rebound, so emission passes the same
    # array objects the arm-never-built receiver passed.
    #
    # A forced lane also forces the REGION adoption gate, because that
    # gate is precisely what made the arm unreachable rather than
    # unhelpful.  Measured (§9.4/§9.8): even under maximal conditioning
    # the standing three-way comparison refused on the DUST leg at all
    # fourteen conditioned lanes while total and word improved by
    # .015-.023 nats, so PK10's "no certificates" answered a gate, not
    # the question.  The per-stratum pre-gate is NOT bypassed: it is how
    # the arm is CONSTRUCTED (which strata carry a map), not whether the
    # arm is allowed to run.  All three region legs are still measured
    # and published under ``region_gate_forced``, so the adoption is
    # auditable, not silent.
    conditioning = ConditioningSummary()
    if (selected_fit is not None and selected_fit.detector is not None
            and not force_null and arm_override == UPLIFT_ARM_A4B):
        arity1, arity2 = emitted_conditioning_arities(
            row_tuple, emission_masks)
        if arity1 + arity2 == 0:
            # The exact null, for free: with no certified sibling anywhere
            # in the emitted population — every lane 0, and every capture
            # whose siblings never certify — the arm cannot change one
            # byte, so it never gathers a population or fits a map.
            conditioning = ConditioningSummary(
                reason=CONDITIONING_REASON_NO_CELLS)
        else:
            known_features = selection.gather(selected_features)
            kinds = np.asarray(selection.kinds, np.int8)
            search = np.asarray(selection.search, np.bool_)
            furniture = np.flatnonzero(kinds >= 0)
            # THE MATERIAL IS THE INCUMBENT'S OWN CALIBRATION POPULATION,
            # STRATIFIED — dust (both split sides, masked) plus certified
            # payload cells, and NO word.  Symmetry is a requirement, not
            # a preference: `_fit_detector` calibrates the incumbent maps
            # in-sample on exactly this population and keeps word out of
            # it, so a candidate fitted on anything else meets an
            # optimistic rival on the gate's DUST leg and a pessimistic
            # one on its WORD leg, and the three-way comparison stops
            # measuring conditioning.  MEASURED on hp c3-cmy8 l01: with
            # search-side word+dust material the gate read word
            # 0.515 -> 0.454 (better) against dust 0.445 -> 0.468
            # (worse) and refused on an artifact of the two fitting
            # regimes (COLOR-UPLIFT-MEASUREMENTS §9).  The candidate's
            # material is a strict SUPERSET of the incumbent's only where
            # the arm's own primary source adds it: partially certified
            # cells, which resolve no state and so cannot be owners at
            # all.
            fit = fit_conditioned_marginals(
                selected_fit.detector,
                _concatenate_populations(
                    _furniture_population(
                        selected_fit.model, selection, known_features,
                        np.flatnonzero(kinds == 1)),
                    _cert_cross_population(
                        selected_fit.model, row_tuple, selected_features)),
                _furniture_population(
                    selected_fit.model, selection, known_features,
                    furniture[~search[furniture]]))
            del known_features
            conditioning = summarize_conditioning(
                fit, cells_arity1=arity1, cells_arity2=arity2)
            selected_fit = replace(
                selected_fit,
                conditioned=fit.head,
                conditioning_reason=fit.reason)

    # A5 (P2/PK5): the neighbourhood corrector.  LAST in the ladder
    # because it corrects what the region actually emits — it reads the
    # selected arm's features and, on CMY7, A4's calibration: the ink map
    # and the fit population both go through ``selected_fit.evidence``,
    # which applies ``cmy7_head`` before the bins are cut.
    #
    # THE ASYMMETRY, RECORDED (review disposition 2026-08-10).  It does
    # NOT read A4b.  Both the bins and the fit population are scored with
    # ``known_mask=None``, i.e. UNCONDITIONED, and ``fit_region_context``
    # never sees ``selected_fit.conditioned`` — so on a cell with certified
    # siblings the transform actually deployed is conditioned∘A5 over
    # bins cut without conditioning, a composition NO gate here scored
    # (A4b earned itself against the unconditioned incumbent, A5 against
    # the unconditioned marginals).  Its blast radius is bounded by the
    # same override-only law: A4b is reachable ONLY from the u-a4b lane,
    # so the composition exists only there, over the residue, where §6.3
    # makes the lane monotone whatever it emits.  That is why this is
    # RECORDED rather than fixed — it is a limitation of the ladder's
    # ORDER, not a proof of harm.  Reordering (fit A5 per conditioning
    # stratum, or condition before binning) is owed only if u-a4b is ever
    # promoted out of its supplemental lane.
    #
    # THE ONE COST THIS ARM CANNOT AVOID: a context bin is a fact about a
    # cell's NEIGHBOURS, so the ink map has to cover the whole region
    # before any cell can be corrected — one extra evidence pass over
    # every row.  Force-null and a switched-off variant never reach here
    # at all; a region too starved to fit anything still pays the pass
    # before ``fit_region_context`` refuses on its two COUNT floors,
    # which is dead work on scrap-scale material (a specimen patch) and
    # invisible on a capture, where every region clears them by three
    # orders of magnitude.  Hoisting those two counts above the ink map
    # is outcome-identical and owed.
    context = ContextSummary()
    context_bins: tuple[np.ndarray, ...] | None = None
    context_cfg = (
        ContextConfig(variant=CONTEXT_VARIANT_OFF) if force_null
        else config.context)
    search_mask = np.asarray(selection.search, np.bool_)
    if (selected_fit is not None and context_cfg.enabled
            and not label_floor_refusal(search_mask, context_cfg)):
        cmy8 = selected_fit.detector is not None
        bins = region_context_bins(
            row_tuple,
            lambda ordinal: selected_fit.evidence(  # type: ignore[union-attr]
                selected_features[ordinal]),
            cmy8=cmy8)
        known_bins = selection.gather(bins, dtype=np.int8)
        fit = fit_region_context(
            selected_fit.model,
            selected_fit.detector,
            selected_fit.cmy7_head,
            selection.gather(selected_features),
            known_bins,
            np.asarray(selection.states, np.int64),
            np.asarray(selection.kinds, np.int8),
            search_mask,
            context_cfg,
            binned_fraction=_binned_fraction(bins, emission_masks))
        context = summarize_context(fit)
        if fit.head is None:
            # The exact null: no head, no bins retained, and the emission
            # loop is handed ``None`` — so a refused A5 emits the same
            # array objects the arm-never-built receiver emitted.
            del bins
        else:
            selected_fit = replace(
                selected_fit, context=fit.head, context_reason=fit.reason)
            context_bins = bins
    elif selected_fit is not None and context_cfg.enabled:
        # Starved on a COUNT floor: publish the arm's own refusal record
        # without building an ink map for a fit that cannot happen.  The
        # bins stand-in is all-invalid because none was ever computed, and
        # ``binned_fraction`` is UNMEASURED for the same reason — a region
        # that never binned a cell must not report a reach.
        context = summarize_context(fit_region_context(
            selected_fit.model, selected_fit.detector,
            selected_fit.cmy7_head,
            np.zeros((selection.states.size, 0), np.float64),
            np.full((selection.states.size, 3), -1, np.int8),
            np.asarray(selection.states, np.int64),
            np.asarray(selection.kinds, np.int8), search_mask,
            context_cfg,
            binned_fraction=CONTEXT_NLL_UNMEASURED))
    return RegionStackResult(
        selected_fit=selected_fit,
        selected_features=selected_features,
        baseline_fit=baseline_fit,
        adopted=adopted,
        refusal_reason="" if selected_fit is not None else reason,
        head_reason=head_reason,
        head_adopted=head is not None,
        head_temperature=1.0 if head is None else head.temperature,
        head_fit=head_fit,
        head_saturation_fraction=saturation,
        head_saturation_floor=floor,
        window_photometry=window_photometry,
        conditioning=conditioning,
        context=context,
        context_bins=context_bins,
    )


def _binned_fraction(
    bins: tuple[np.ndarray, ...],
    emission_masks: tuple[np.ndarray, ...],
) -> float:
    """Share of the region's EMITTED cells with a complete neighbourhood.

    Published (``color.context.binned_fraction``) because it is the arm's
    reach: a cell whose 8-neighbourhood is not wholly inside the region
    keeps its uncorrected evidence, and how often that happens is a
    property of the capture's coverage, not of the fit.
    """
    emitted = 0
    binned = 0
    for row_bins, emit in zip(bins[:len(emission_masks)], emission_masks,
                              strict=True):
        if not np.any(emit):
            continue
        selected = row_bins[emit]
        emitted += int(selected.shape[0])
        binned += int(np.count_nonzero(np.all(selected >= 0, axis=1)))
    return 0.0 if not emitted else binned / emitted


__all__ = [
    "FORCE_NULL_ENV", "FORCE_NULL_REASON",
    "HEAD_NO_POPULATION_REASON", "HEAD_SATURATION_FLOOR",
    "HEAD_SATURATION_REASON", "HEAD_SATURATION_UNMEASURED",
    "STACK_GATE_SLACK", "UPLIFT_ARMS", "UPLIFT_ARM_A3", "UPLIFT_ARM_A4B",
    "UPLIFT_ARM_OFF",
    "ArmFeatures",
    "ConditioningSummary", "RegionStackResult", "StackConfig",
    "WindowPhotometryConfig",
    "WindowPhotometrySummary", "deployment_saturation",
    "emitted_conditioning_arities", "fit_region_stack",
    "force_null_enabled",
]

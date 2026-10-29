"""The supplemental arm ladder — A3 and A4b, override-only.

RECEIVE-DESIGN §6.2a, THE SUPPLEMENTAL-LANE LAW (v0.51) as amended by the
override-only law (v0.52) and the zero-frontier fix (v0.54).

An arm that cannot prove universal non-regression is not gated — it is
SCHEDULED, on the uncertified residue, where the per-address retirement
law makes it MONOTONE BY CONSTRUCTION: a certified (address, stream) is
never re-attempted, so the arm's reachable set is exactly the residue and
it can only ADD certificates.  No adoption gate, no applicability floor;
the zero-wrong-certificate audit is the only bar.

THE OVERRIDE IS THE WHOLE REACHABILITY TEST.  ``apply_arm`` runs A3 iff
the arm is ``a3`` and A4b iff it is ``a4b``.  There is no constant, no
flag and no environment variable that could engage either arm from the
standard ladder, which therefore does not pay for an arm it was always
going to refuse: ``color_region_head.fit_region_stack`` fits no window maps
and gathers no conditioning population at all.

WHAT EACH ARM STILL OBEYS.  A3 keeps BOTH of its own gates — the
per-window held-out pre-gate that decides which windows carry a map, and
the standing three-way region comparison (total strictly better by 1e-9,
word and dust not worse) that decides whether the refitted region model
replaces its predecessor.  Only the two retired region dispersion floors
are gone, and they are gone from the tree, not bypassed.  A4b keeps its
per-stratum pre-gate — that is how the arm is CONSTRUCTED, not whether it
may run — and forces only the REGION adoption gate, because measured that
gate is what made the arm unreachable rather than unhelpful (refused on
the DUST leg at all fourteen conditioned lanes while total and word
improved by .015-.023 nats).  Its verdict is therefore always
``region_gate_forced``, never ``adopted``, so a forced adoption can never
be read as one the comparison granted, and all three region legs are
still measured.

LADDER POSITION.  v1 runs A0/A1 -> A3 -> A4 -> A4b -> A5.  A4 is the CMY7
head and A4b is CMY8-only, so the two are mutually exclusive by family
and running A4b before the (no-op) head is the same composition.  A5 is
deliberately fitted on UNCONDITIONED bins — the recorded asymmetry: on a
cell with certified siblings the transform deployed is conditioned o A5
over bins cut without conditioning, which no gate scored.  Its blast
radius is bounded by the override-only law: the composition exists only
in the residue row, where the retirement law makes the row monotone
whatever it emits.  Reordering is owed only if A4b is ever promoted out
of its supplemental row.

A4b needs a certified SIBLING plane, so a single-stream coding has
nothing to condition on and never schedules it (v1 measured that lane at
98 blocks / 185 attempts / 0 certificates / 144 s CPU on xerox c3-cmy7).

Deterministic and RNG-free: every arm is a pure function of canonically
ordered inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ..data import WindowRows
from ..format.identity import Family, FormatRow
from ..format.tile_codec import states_to_planes
from . import color_conditioning as conditioning
from . import color_photometry as photometry
from . import color_region
from . import color_region_head
from .color_model import qda_log_scores

UPLIFT_ARM_A3: str = "a3"
UPLIFT_ARM_A4B: str = "a4b"
#: Why these two are override-only (COLOR-UPLIFT-MEASUREMENTS 5.9, 9.10):
#: neither proves universal non-regression on the colour corpus.  A3 won
#: +47 C on hp c3-cmy8 and lost 5 addresses on the xerox c3-cmy7 canary;
#: A4b was an exact null on hp (M = 43) and net -5 on xerox c2-cmy8.
UPLIFT_ARMS: tuple[str, ...] = (UPLIFT_ARM_A3, UPLIFT_ARM_A4B)


@dataclass(frozen=True)
class ArmVerdict:
    arm: str
    reason: str
    adopted: bool
    accepted_maps: int = 0
    refused_maps: int = 0
    pooled_maps: int = 0
    map_reasons: tuple[tuple[str, int], ...] = ()
    strata_adopted: int = 0
    cells_arity1: int = 0
    cells_arity2: int = 0
    cert_cells: int = 0
    masked_cells: int = 0
    # published per stratum because a region refusal is SPENT by particular
    # strata and a region number cannot name them -- the per-stratum legs are
    # what COLOR-UPLIFT-MEASUREMENTS section 9.6 is made of.
    strata: tuple[tuple[int, int, str, int, int], ...] = ()
    strata_deltas: tuple[tuple[int, int, float, float, float], ...] = ()


# The FAMILY is the stream filter v1 spelled as ``n_streams < 2``: an
# identity's stream set follows from its family (cmy8 three, cmy7 one;
# format/identity.py's stream loop) and A4b conditions on a certified SIBLING
# plane.  A one-stream cmy8 family would schedule a guaranteed zero here.
# cmy is never born here: its A4b is `tiles.cond` (CMY-RECEIVER-PLAN O4).
_ARMS_BY_FAMILY: dict[Family, tuple[str, ...]] = {
    Family.K: (), Family.CMY7: (UPLIFT_ARM_A3,), Family.CMY8: UPLIFT_ARMS,
    Family.CMY: ()}


def arms_for_family(family: Family) -> tuple[str, ...]:
    return _ARMS_BY_FAMILY[family]


# These count (cell, plane) MARGINALS, not cells: one payload cell on a
# C-certified tile contributes two arity-1 marginals (M and Y) and leaves
# C's own marginal unconditioned.  That pair count is what the decode
# consumes, so it is the honest measure of the arm's reach.
def emitted_conditioning_arities(
    payload_rows: tuple[WindowRows, ...],
    emission_masks: tuple[np.ndarray, ...],
) -> tuple[int, int]:
    arity1 = 0
    arity2 = 0
    for rows, emit in zip(payload_rows[:len(emission_masks)],
                          emission_masks):
        if not np.any(emit):
            continue
        mask = np.asarray(rows.known_component_mask, np.bool_)[emit]
        certified = mask & (
            np.asarray(rows.furniture_kind, np.int8)[emit] < 0)[:, None]
        codes = conditioning.conditioning_pattern_codes(certified)
        arity1 += int(np.count_nonzero((codes == 1) | (codes == 2)))
        arity2 += int(np.count_nonzero(codes == 3))
    return arity1, arity2


def furniture_population(
    model: object,
    selection: color_region_head.OwnerSelection,
    known_features: np.ndarray,
    rows: np.ndarray,
) -> conditioning.ConditioningPopulation:
    states = np.asarray(selection.states, np.int64)[rows]
    bits = states_to_planes(states.astype(np.int8))
    reveal = conditioning.masking_reveal_codes(selection.keys[rows][:, 1:])
    return conditioning.ConditioningPopulation(
        scores=qda_log_scores(model, known_features[rows]),
        bits=np.asarray(bits, np.uint8),
        labelled=np.ones((rows.size, 3), np.bool_),
        pattern=np.repeat(reveal[:, None], 3, axis=1),
        kinds=np.asarray(selection.kinds, np.int8)[rows],
        from_certificates=np.zeros(rows.size, np.bool_))


def cert_cross_population(
    model: object,
    row_tuple: tuple[WindowRows, ...],
    features: tuple[np.ndarray, ...],
) -> conditioning.ConditioningPopulation | None:
    cells: list[np.ndarray] = []
    gathered: list[np.ndarray] = []
    bits: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    for ordinal, rows in sorted(
            enumerate(row_tuple),
            key=lambda pair: int(pair[1].patch_ordinal)):
        mask = np.asarray(rows.known_component_mask, np.bool_)
        chosen = np.flatnonzero(
            (np.asarray(rows.furniture_kind, np.int8) < 0)
            & (mask.sum(axis=1) >= 2))
        if chosen.size == 0:
            continue
        cells.append(np.asarray(rows.page_cells_yx, np.int64)[chosen])
        gathered.append(np.asarray(features[ordinal], np.float64)[chosen])
        bits.append(np.asarray(rows.known_component_bits, np.uint8)[chosen])
        masks.append(mask[chosen])
    if not cells:
        return None
    page_cells = np.concatenate(cells)
    _unique, first = np.unique(
        page_cells[:, 0] * (int(page_cells[:, 1].max()) + 1)
        + page_cells[:, 1], return_index=True)
    if first.size > conditioning.CONDITIONING_MAX_CERT_CELLS:
        first = first[np.linspace(
            0, first.size - 1,
            conditioning.CONDITIONING_MAX_CERT_CELLS).astype(np.int64)]
    known = np.concatenate(masks)[first]
    return conditioning.ConditioningPopulation(
        scores=qda_log_scores(model, np.concatenate(gathered)[first]),
        bits=np.concatenate(bits)[first],
        labelled=known,
        pattern=conditioning.conditioning_pattern_codes(known),
        kinds=np.full(first.size, -1, np.int8),
        from_certificates=np.ones(first.size, np.bool_))


def concatenate_populations(
    left: conditioning.ConditioningPopulation,
    right: conditioning.ConditioningPopulation | None,
) -> conditioning.ConditioningPopulation:
    if right is None:
        return left
    return conditioning.ConditioningPopulation(
        scores=np.concatenate((left.scores, right.scores)),
        bits=np.concatenate((left.bits, right.bits)),
        labelled=np.concatenate((left.labelled, right.labelled)),
        pattern=np.concatenate((left.pattern, right.pattern)),
        kinds=np.concatenate((left.kinds, right.kinds)),
        from_certificates=np.concatenate(
            (left.from_certificates, right.from_certificates)))


def _apply_a3(
    row: FormatRow,
    selection: color_region_head.OwnerSelection,
    row_tuple: tuple[WindowRows, ...],
    selected: color_region_head.DetectorFit,
    features: tuple[np.ndarray, ...],
    config: photometry.WindowPhotometryConfig,
) -> tuple[color_region_head.DetectorFit, tuple[np.ndarray, ...], ArmVerdict]:
    maps = photometry.fit_window_photometry(
        selected.model, selection, row_tuple, features, config)
    reason = maps.arm_reason
    if not reason:
        mapped, _refusal = color_region_head.fit_detector(
            row.family, selection, maps.features)
        if mapped is None:
            reason = photometry.REASON_REGION_GATE_FAILED
        elif color_region_head.improves(mapped, selected):
            selected = mapped
            features = maps.features
            reason = photometry.REASON_ADOPTED
        else:
            reason = photometry.REASON_REGION_GATE_FAILED
    return selected, features, ArmVerdict(
        arm=UPLIFT_ARM_A3,
        reason=reason,
        adopted=reason == photometry.REASON_ADOPTED,
        accepted_maps=maps.accepted,
        refused_maps=maps.refused,
        pooled_maps=maps.pooled,
        map_reasons=maps.reasons)


def _apply_a4b(
    selection: color_region_head.OwnerSelection,
    row_tuple: tuple[WindowRows, ...],
    payload_rows: tuple[WindowRows, ...],
    emission_masks: tuple[np.ndarray, ...],
    selected: color_region_head.DetectorFit,
    features: tuple[np.ndarray, ...],
) -> tuple[color_region_head.DetectorFit, ArmVerdict]:
    arity1, arity2 = emitted_conditioning_arities(
        payload_rows, emission_masks)
    if arity1 + arity2 == 0:
        return selected, ArmVerdict(
            arm=UPLIFT_ARM_A4B,
            reason=conditioning.CONDITIONING_REASON_NO_CELLS,
            adopted=False)
    known_features = selection.gather(features)
    kinds = np.asarray(selection.kinds, np.int8)
    search = np.asarray(selection.search, np.bool_)
    furniture = np.flatnonzero(kinds >= 0)
    fit = conditioning.fit_conditioned_marginals(
        selected.detector,
        concatenate_populations(
            furniture_population(
                selected.model, selection, known_features,
                np.flatnonzero(kinds == 1)),
            cert_cross_population(selected.model, row_tuple, features)),
        furniture_population(
            selected.model, selection, known_features,
            furniture[~search[furniture]]))
    return replace(selected, conditioned=fit.head), ArmVerdict(
        arm=UPLIFT_ARM_A4B,
        reason=fit.reason,
        adopted=fit.adopted,
        strata_adopted=sum(
            1 for stratum in fit.strata
            if stratum.reason == conditioning.CONDITIONING_REASON_ADOPTED),
        cells_arity1=arity1,
        cells_arity2=arity2,
        cert_cells=fit.n_cert_cells,
        masked_cells=fit.n_masked_cells,
        strata=tuple(
            (row.plane, row.pattern, row.reason, row.n_cert, row.n_masked)
            for row in fit.strata),
        strata_deltas=tuple(
            (row.plane, row.pattern,
             row.candidate_nll - row.incumbent_nll,
             row.word_candidate_nll - row.word_incumbent_nll,
             row.dust_candidate_nll - row.dust_incumbent_nll)
            for row in fit.strata))


def fit_region_stack_arm(
    row: FormatRow,
    inputs: color_region.RegionInputs,
    config: color_region_head.StackConfig,
    arm: str,
) -> tuple[color_region_head.StackResult, ArmVerdict | None]:
    if arm not in UPLIFT_ARMS:
        raise ValueError(f"color arms: unregistered uplift arm {arm!r}")
    selected, features, adopted, reason = (
        color_region_head.select_registration_arm(
            row, inputs.selection, inputs.base_tuple, inputs.corrected))
    verdict: ArmVerdict | None = None
    if selected is not None and arm == UPLIFT_ARM_A3:
        selected, features, verdict = _apply_a3(
            row, inputs.selection, inputs.row_tuple, selected, features,
            config.window_photometry)
    if (selected is not None and arm == UPLIFT_ARM_A4B
            and selected.detector is not None):
        selected, verdict = _apply_a4b(
            inputs.selection, inputs.row_tuple, inputs.payload_rows,
            inputs.emission_by_row, selected, features)
    stack = color_region_head.finish_region_stack(
        row, inputs.selection, inputs.row_tuple, selected, features,
        adopted, reason, inputs.emission_by_row, config)
    return stack, verdict

"""The decoder-feedback rung `L3f` (W8 B4; APPROACHES-2026-09-06 §1g P3).

BP failed on the combined channel.  Its EXTRINSIC still says, cell by
cell, which bits the code is confident about; the measured record (MEAS
§5b) found that handing 25 % of a tile's cells to the patch filter as
labels took the dead band's three-ink error from 0.119 to 0.085 on one
lane and to 0.049 combined.  This rung is the blind twin of that proxy:

  round r   the confident extrinsic bits (|extrinsic| >= `refit_confidence_llr`,
            sequential index 0 excluded when the metadata bit is injected)
            become a typed `PseudoLabels(source="decoder")` at their PAGE
            cells; the rule's chosen lanes are RECOMPUTED with them
            (`arms.evidence_for` with the `pseudo_labels` knob: the patch
            filter refits, the PAVA map refits when `refit_calibration`),
            recombined under the rule with the ROUND-0 label view (ruling
            9: the coefficients cannot move), and BP runs again through
            the gate.  Stops on a certificate, on no unsatisfied-check
            gain, on an empty confident set, or when the per-KEY evidence
            budget (`refit_max_evidence`) cannot cover another round.

The rung is a pure function of its knobs like every other (ruling 2): the
pixels stay behind `knobs["refit"]`, a closure `fixedpoint.blind_key`
binds per rule over the generation's certificate snapshot.  Without it —
the `controls` null arm hands none — the rung refuses `no_refit`.

What the extrinsic is (ladder L3's spelling, `ladder.py` `_rung_ctx_iterate`):
``clip(posterior_seq - clip(channel_seq, ±LLR_CLIP), ±LLR_CLIP)`` in the
SEQUENTIAL domain, against the vector the decoder actually consumed.  A
positive sequential LLR is target-plane ink AS PRINTED, which is
`KnownFrame.bits`' own convention, so the pseudo bit is ``extrinsic > 0``
with no dither re-applied (the sequential domain is still dithered on
both sides of that comparison).

MEASURED while building the fixture (2026-09-06, r0850 synthetic, tau 4):
in the near-codeword regime (unsat <= 12 at exit) the gate names 93-99 %
of the cells with 0-8 of them wrong, and a re-read of those cells at the
truth certifies; far above threshold (unsat >= 100) the extrinsic never
converges — its 99th percentile sits under 4 and the gate names 0-2 % —
so there the rung refuses `no_confident_bits` at the cost of one BP.

Blind (DESIGN §0): imports numpy, `.mother`, `.types`, `.combine`,
`.arms` at module level and `.ladder` inside functions (`ladder` imports
this module function-locally too); never `.truth`, `.oracle`, `.score`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from holo.receiver.lib.ldpc import LLR_CLIP

from . import arms as arms_mod
from . import combine as combine_mod
from . import mother as mother_mod
from .types import (VERDICT_CERTIFIED, VERDICT_REFUSED, Combined, Evidence,
                    Exposure, Key, PseudoLabels, RungResult)

RUNG: str = "L3f"
DEFAULT_ROUNDS: int = 2
DEFAULT_CONFIDENCE_LLR: float = 4.0
DEFAULT_WEIGHT: float = 3.0
DEFAULT_MAX_EVIDENCE: int = 26
PSEUDO_SOURCE_DECODER: str = "decoder"


class RefitError(RuntimeError):
    """The refit closure could not do what it was asked."""


class RefitBudgetExhausted(RefitError):
    """The key's evidence budget cannot cover another full round."""


# ------------------------------------------------------ the pseudo labels

def extrinsic_sequential(current_seq: np.ndarray, posterior_seq: np.ndarray
                         ) -> np.ndarray:
    """L3's extrinsic: ``clip(posterior - clip(channel))``, sequential."""
    current = np.asarray(current_seq, np.float64).ravel()
    posterior = np.asarray(posterior_seq, np.float64).ravel()
    return np.clip(posterior - np.clip(current, -LLR_CLIP, LLR_CLIP),
                   -LLR_CLIP, LLR_CLIP)


def confident_pseudo_labels(current_seq: np.ndarray,
                            posterior_seq: np.ndarray, row: Any, key: Key,
                            *, tau: float, weight: float,
                            metadata_bit: int | None) -> PseudoLabels:
    """The decoder's confident bits, typed, at their PAGE cells.

    `current_seq` is the sequential vector the decoder CONSUMED (the
    mother's channel mapped back, so a temperature-scaled L2 entry is
    read against its own scaled channel); `posterior_seq` its posterior
    in the same domain.  Confident = observed (finite, non-zero) and
    |extrinsic| >= `tau`.  Sequential index 0 is the metadata cell; when
    a bit was injected there its mother posterior is ~+-1e9 and it is
    already known to the frame, so it is left out.  Cells come from
    `ladder._cell_grid` (the blind inverse of `to_sequential`) plus the
    tile origin.
    """
    from . import ladder as ladder_mod
    current = np.asarray(current_seq, np.float64).ravel()
    extrinsic = extrinsic_sequential(current, posterior_seq)
    observed = np.isfinite(current) & (current != 0.0)
    confident = observed & (np.abs(extrinsic) >= float(tau))
    if metadata_bit is not None and confident.size:
        confident[0] = False
    index = np.flatnonzero(confident)
    page, ty, tx, _stream = key
    grid = np.asarray(ladder_mod._cell_grid(row, key), np.int64)[index]
    cells = grid + np.array([int(ty) * 64, int(tx) * 64], np.int64)
    bits = (extrinsic[index] > 0.0).astype(np.uint8)
    weights = np.full(index.size, float(weight), np.float64)
    return PseudoLabels(source=PSEUDO_SOURCE_DECODER, cells_yx=cells,
                        bits=bits, weights=weights)


def extrinsic_quantiles(current_seq: np.ndarray, posterior_seq: np.ndarray
                        ) -> dict[str, float]:
    """|extrinsic| at the 50/90/99th percentiles and its max, for the row.

    Read beside `no_confident_bits`: it says whether the gate was a hair
    too high or the decoder never converged at all.
    """
    current = np.asarray(current_seq, np.float64).ravel()
    magnitude = np.abs(extrinsic_sequential(current, posterior_seq))
    magnitude = magnitude[np.isfinite(current) & (current != 0.0)]
    if not magnitude.size:
        return {"extrinsic_q50": 0.0, "extrinsic_q90": 0.0,
                "extrinsic_q99": 0.0, "extrinsic_max": 0.0}
    q50, q90, q99 = np.quantile(magnitude, (0.5, 0.9, 0.99))
    return {"extrinsic_q50": float(q50), "extrinsic_q90": float(q90),
            "extrinsic_q99": float(q99),
            "extrinsic_max": float(magnitude.max())}


# ------------------------------------------------------------- the refit

def _label_view_for(kept: Sequence[Evidence], label_view: tuple,
                    round0_kept: Sequence[Evidence]) -> tuple | None:
    """The round-0 label view re-ordered onto the lanes that survived.

    KEYED BY THE NEW LIST, in ITS order (review 2026-09-06).  `combine`
    de-duplicates the refitted set for itself, and `deduplicate` keeps
    the FINEST level of each capture — so a capture whose finest lane
    refuses on the refit can come back through a COARSER level that
    round 0 never carried.  Restricting round 0 by "which lanes are
    present" then yields fewer rows than `combine` has lanes, and the
    stack silently misaligns: `best` reads one lane's losses under
    another's name and `platt`/`platt-state` raise inside a worker,
    aborting the pass.  A promoted lane has no round-0 row to stand on,
    so the refit REFUSES the round rather than combining a mismatched
    view; `None` is the refusal, exactly as "no lane survived" is.
    """
    rows, stack, values, *rest = label_view
    stack = np.asarray(stack, np.float64)
    if stack.ndim != 2 or stack.shape[0] != len(round0_kept):
        raise RefitError(
            f"refit: the label view has {stack.shape} rows for "
            f"{len(round0_kept)} round-0 lanes")
    by_lane = {item.lane: index for index, item in enumerate(round0_kept)}
    if any(item.lane not in by_lane for item in kept):
        return None
    take = [by_lane[item.lane] for item in kept]
    return (np.asarray(rows, np.int64), stack[take],
            np.asarray(values, np.uint8), *rest)


def refit_evidence(inputs: Any, certs: Mapping[Key, Any], key: Key,
                   halo: int, knobs_by_lane: Mapping[Any, Mapping[str, Any]],
                   lanes_by_id: Mapping[Any, Any],
                   evidence_set: Sequence[Evidence], rule: str,
                   sibling_state: np.ndarray | None, label_view: tuple,
                   budget: list[int], pseudo: PseudoLabels,
                   ) -> Combined | None:
    """Recompute one evidence set with the pseudo labels and recombine.

    Every item of `evidence_set` is re-run through `arms.evidence_for`
    with the SAME knobs it had plus `pseudo_labels`, against the SAME
    certificate mapping (the generation's snapshot: `frame._projection`'s
    memo hits), and each recomputation is charged to `budget[0]`, the
    per-key bound.  A budget that cannot cover the whole set refuses
    BEFORE spending (`RefitBudgetExhausted`): a half-recomputed set would
    have to be combined under a label view its lanes do not match.

    The recombination uses the ROUND-0 label view (ruling 9): the rule's
    fit is the same deterministic function of the same select-fold view,
    so its coefficients come out identical and no decoder-shaped LLR ever
    reaches a rule fit.  A lane that refuses on the refit is dropped and
    the view is re-ordered onto the survivors; `None` when none survive,
    and `None` too when de-duplication PROMOTED a coarser level of a
    capture whose finer lane refused — that lane has no round-0 label row
    to be combined against (review 2026-09-06).
    """
    if not isinstance(pseudo, PseudoLabels):
        raise RefitError("refit_evidence: pseudo labels must be a typed "
                         "PseudoLabels (ruling 8)")
    needed = len(evidence_set)
    if needed == 0:
        return None
    if int(budget[0]) < needed:
        raise RefitBudgetExhausted(
            f"{int(budget[0])} evidence recomputation(s) left in the key's "
            f"budget, {needed} needed for one round")
    new: list[Evidence] = []
    for item in evidence_set:
        knobs = {**dict(knobs_by_lane[item.lane]), "pseudo_labels": pseudo}
        evidence = arms_mod.evidence_for(
            inputs, certs, key, lanes_by_id[item.lane], item.arm,
            halo_cells=int(halo), knobs=knobs)
        budget[0] -= 1
        if (evidence.blind.get("refusal") is None
                and bool(np.any(evidence.observed))):
            new.append(evidence)
    if not new:
        return None
    round0_kept, _detail = combine_mod.deduplicate(evidence_set)
    kept, _detail = combine_mod.deduplicate(new)
    view = _label_view_for(kept, label_view, round0_kept)
    if view is None:
        return None
    return combine_mod.combine(list(kept), rule, labels=view,
                               sibling_state=sibling_state)


@dataclass
class Refit:
    """What `blind_key` binds as `knobs["refit"]`, one per (rule, set).

    A callable over `PseudoLabels` -> `Combined | None` that carries the
    key's evidence BUDGET (`budget` is one shared one-element list for
    every rule and re-roll set of the key, `limit` its starting value)
    so the rung can say how much of it a round spent.  Everything it
    captures is the generation's own — the certificate snapshot, the
    lanes, their knobs — and the only thing it mutates is the budget.
    """
    inputs: Any = field(repr=False)
    certs: Mapping[Key, Any] = field(repr=False)
    key: Key
    halo: int
    knobs_by_lane: Mapping[Any, Mapping[str, Any]] = field(repr=False)
    lanes_by_id: Mapping[Any, Any] = field(repr=False)
    evidence_set: tuple[Evidence, ...] = field(repr=False)
    rule: str
    sibling_state: np.ndarray | None = field(repr=False)
    label_view: tuple = field(repr=False)
    budget: list[int] = field(repr=False)
    limit: int = DEFAULT_MAX_EVIDENCE

    @property
    def n_evidence(self) -> int:
        return len(self.evidence_set)

    @property
    def remaining(self) -> int:
        return int(self.budget[0])

    @property
    def used(self) -> int:
        return int(self.limit) - int(self.budget[0])

    def __call__(self, pseudo: PseudoLabels) -> Combined | None:
        return refit_evidence(
            self.inputs, self.certs, self.key, self.halo, self.knobs_by_lane,
            self.lanes_by_id, self.evidence_set, self.rule,
            self.sibling_state, self.label_view, self.budget, pseudo)


def bind(inputs: Any, certs: Mapping[Key, Any], key: Key, halo: int,
         knobs_by_lane: Mapping[Any, Mapping[str, Any]],
         lanes_by_id: Mapping[Any, Any], evidence_set: Sequence[Evidence],
         rule: str, sibling_state: np.ndarray | None, budget: list[int],
         limit: int) -> Refit:
    """The closure for one (rule, evidence set), label view taken NOW.

    The view is `combine._label_view` over the DEDUPLICATED set — the
    lanes `combine` itself would fit the rule on — so a refit recombines
    under exactly the rows and lanes round 0 did.
    """
    kept, _detail = combine_mod.deduplicate(evidence_set)
    return Refit(inputs=inputs, certs=certs, key=key, halo=int(halo),
                 knobs_by_lane=knobs_by_lane, lanes_by_id=lanes_by_id,
                 evidence_set=tuple(evidence_set), rule=str(rule),
                 sibling_state=sibling_state,
                 label_view=combine_mod._label_view(kept), budget=budget,
                 limit=int(limit))


# -------------------------------------------------------------- the rung

def _refused(rung: str, reason: str, *, seconds: float = 0.0,
             unsat: int = -1, **extra: Any) -> RungResult:
    from . import ladder as ladder_mod
    return ladder_mod._result(rung, VERDICT_REFUSED, unsat=unsat,
                              seconds=seconds,
                              detail={"reason": reason, **extra})


def rung_feedback(llr_seq: np.ndarray, row: Any, key: Key, bank: Any,
                  exposure: Exposure, knobs: Mapping[str, Any],
                  metadata_bit: int | None, states: Sequence[tuple],
                  ) -> list[RungResult]:
    """L3f: refit the chosen lanes on the decoder's confident bits.

    Entry is `ladder._flip_source(states)` — the fewest-unsat decode this
    rule has produced (L2's variants, else L1's, else L0's) — or, when
    none ran, its own 150-iteration decode.  Each round: pseudo labels
    from the entry's extrinsic -> `knobs["refit"]` -> a new combined
    vector -> `to_mother` -> BP -> the gate (the CRC consult charged
    inside `mother.gate`, like every other rung).  Refusals, each a row
    of its own: `no_refit` (no closure bound), `entry_syndrome_closed`
    (the entry converged to a codeword the CRC refused — its extrinsic
    is a lie of full confidence), `no_confident_bits`,
    `refit_budget_exhausted`, `refit_failed`, and `no_unsat_gain` when a
    round did not lower the unsatisfied-check count.  The gate's own
    `exposure_exceeded` stops the rung as it stops L4.
    """
    from . import ladder as ladder_mod
    started = time.perf_counter()
    refit = knobs.get("refit")
    if refit is None:
        return [_refused(RUNG, "no_refit",
                         seconds=time.perf_counter() - started)]
    rounds = int(knobs.get("refit_rounds", DEFAULT_ROUNDS))
    tau = float(knobs.get("refit_confidence_llr", DEFAULT_CONFIDENCE_LLR))
    weight = float(knobs.get("refit_weight", DEFAULT_WEIGHT))
    iters = int(knobs.get("iters", ladder_mod.PROD_RETRY_ITERS))
    keep_hard = bool(knobs.get("keep_hard", False))
    limit = int(knobs.get("refit_max_evidence", DEFAULT_MAX_EVIDENCE))

    entry = ladder_mod._flip_source(states)
    if entry is None:
        mother = mother_mod.to_mother(np.asarray(llr_seq, np.float64), row,
                                      key, metadata_bit=metadata_bit)
        out = mother_mod.bp(mother, None, iters, mode="minsum-then-sp")
        entry = (f"{RUNG}.entry", out, mother)
    source, out, mother = entry
    entry_unsat = int(out.unsat)
    base_detail = {"source_rung": str(source), "unsat_entry": entry_unsat,
                   "tau": tau, "weight": weight, "refit_rounds": rounds,
                   "refit_max_evidence": limit}
    if entry_unsat == 0:
        return [_refused(RUNG, "entry_syndrome_closed", unsat=0,
                         seconds=time.perf_counter() - started,
                         **base_detail)]
    # what the entry decoder CONSUMED, back in the sequential domain — the
    # channel it was handed, temperature and metadata injection included
    current = mother_mod.to_sequential(mother.llr, mother)
    posterior = mother_mod.to_sequential(out.posterior, mother)
    results: list[RungResult] = []
    previous_unsat = entry_unsat
    for round_index in range(rounds):
        label = f"{RUNG}.r{round_index}"
        pseudo = confident_pseudo_labels(current, posterior, row, key,
                                         tau=tau, weight=weight,
                                         metadata_bit=metadata_bit)
        n_observed = int(np.count_nonzero(np.isfinite(current)
                                          & (current != 0.0)))
        round_detail = {**base_detail, "round": round_index,
                        "n_pseudo": int(pseudo.size),
                        "n_observed": n_observed,
                        **extrinsic_quantiles(current, posterior)}
        if pseudo.size == 0:
            results.append(_refused(label, "no_confident_bits",
                                    unsat=previous_unsat,
                                    seconds=time.perf_counter() - started,
                                    **round_detail))
            break
        try:
            combined = refit(pseudo)
        except RefitBudgetExhausted as error:
            results.append(_refused(
                label, "refit_budget_exhausted", unsat=previous_unsat,
                seconds=time.perf_counter() - started,
                budget_remaining=int(getattr(refit, "remaining", -1)),
                budget_needed=int(getattr(refit, "n_evidence", -1)),
                message=str(error), **round_detail))
            break
        round_detail["refit_evidence_used"] = int(
            getattr(refit, "used", -1))
        round_detail["refit_budget_remaining"] = int(
            getattr(refit, "remaining", -1))
        if combined is None:
            results.append(_refused(label, "refit_failed",
                                    unsat=previous_unsat,
                                    seconds=time.perf_counter() - started,
                                    **round_detail))
            break
        current = ladder_mod._sequential_llr(combined)
        round_detail["refit_lanes"] = tuple(
            (lane[0][:12], int(lane[1]))
            for lane in getattr(combined, "lanes", ()))
        mother = mother_mod.to_mother(current, row, key,
                                      metadata_bit=metadata_bit)
        result, out = ladder_mod._decode_and_gate(
            mother, bank, exposure, label, iters=iters,
            mode="minsum-then-sp", extra=round_detail, keep_hard=keep_hard)
        results.append(result)
        if result.verdict == VERDICT_CERTIFIED:
            break
        if result.detail.get("refusal") == "exposure_exceeded":
            break
        if round_index + 1 == rounds:
            break
        if int(out.unsat) >= previous_unsat:
            results.append(_refused(label, "no_unsat_gain",
                                    unsat=int(out.unsat),
                                    seconds=time.perf_counter() - started,
                                    unsat_previous=previous_unsat))
            break
        previous_unsat = int(out.unsat)
        # the next round reads THIS decode: its channel and its posterior
        current = mother_mod.to_sequential(mother.llr, mother)
        posterior = mother_mod.to_sequential(out.posterior, mother)
    return results

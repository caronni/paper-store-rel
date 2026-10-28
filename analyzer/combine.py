"""Combination across lanes — DESIGN §5.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`.  `platt` and `corr` are FITTED, and every label
they fit on is a `KnownFrame` bit carried in the evidence's own blind
record; the fit sees the SELECT fold only, which no arm's search touched.

THE PHYSICAL-EVIDENCE INVARIANT COMES FIRST (DESIGN §0).  One physical
capture contributes ONE evidence vector to any sum, and decimated levels
of one capture ARE the same capture — the 018 operational rule, the
e023b "one ordinary state freezes one DPI" finding.  :func:`combine`
therefore de-duplicates by capture id BEFORE any rule runs, keeping the
FINEST level of each capture (largest ppc, falling back to the largest
level index when no ppc table is offered), and records which lane each
capture contributed so the choice is auditable rather than incidental.

FIVE RULES, and what each is for:

* `sum` — production's own equal-weight LLR addition, the F1 o F6 law's
  right-hand side.  The baseline every other rule is scored against.
* `best` — the single lane with the lowest select-fold log loss.  The
  control for "the union can lose a tile": when `best` beats `sum`, a
  lane is actively harmful.
* `platt` — per-lane coefficients b_l >= 0 and one temperature, fitted
  by minimising the select-fold log loss.  Refused below the label floor,
  where it falls back to `sum` and says so.  The scale and the weights
  are one convex problem (b_l / T is the only identified quantity), so
  they are fitted jointly and REPORTED split, never fitted twice.
* `corr` — the equal-weight sum divided by (1 + (L-1)rho)^(1/2), rho the
  mean pairwise correlation of per-lane errors at label cells.  This is
  the multi-scan law's correction: errors are print-frozen and therefore
  correlated across captures, so L independent-looking lanes are worth
  fewer than L.
* `normalized` — the mean.  A control: it changes no decision `sum`
  makes (a positive scaling), and it exists so the clipped-cell fraction
  of `sum` can be read against a rule that cannot clip.

WHY LABELS COME OUT OF THE FOOTPRINT, NOT THE SEQUENTIAL VECTOR.  The
sequential vector is the target tile's payload cells alone, and DESIGN
§4.5's run-abort assertion guarantees that NONE of them carries a known
target-plane bit.  There is nothing there to fit on.  The labels live in
the halo and in the tile's own furniture, i.e. in the footprint domain,
so `analyzer.calibrate.calibrate` publishes `label_rows` / `label_llr` /
`label_values` on the select fold and this module fits there.  Footprints
are lane-independent (`frame.tile_footprint` takes no lane), so a row
index means the same cell in every lane of one tile and the pairing is
exact.

TWO AGREEMENTS LIVE HERE, and they are different things.
:func:`lane_agreement` is per-CELL sign agreement inside one
combination — L7a's erasure input.  :func:`independent_agreement` is
per-KEY agreement between finished CERTIFICATES: the fourth leg of the
2026-09-04 correctness ruling, where two certificates resting on
disjoint physical captures and carrying identical user bits corroborate
each other, and two carrying different bits are a contradiction that
refuses the key.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import optimize

from holo3.lib import ldpc, pava

from .calibrate import SELECT_MIN_MINORITY, _minority_count, _per_label_loss
from .types import Combined, Evidence, Folds, LaneId

RULES: tuple[str, ...] = ("sum", "best", "platt", "corr", "normalized")

#: L7a's default disagreement threshold (DESIGN §6 L7a): a cell is
#: disagreeing when ANY voting lane's sign differs from the combination's,
#: i.e. when its agreement fraction is below 1.0.  A caller that wants only
#: the badly split cells lowers it (0.5 = "the minority is at least half").
AGREEMENT_UNANIMOUS: float = 1.0

#: `platt`'s optimiser stops here; the problem is convex and smooth, so
#: this is arithmetic, not a search budget.
PLATT_MAX_ITERATIONS: int = 500


class CombineError(RuntimeError):
    """The lanes cannot be combined as asked."""


# ------------------------------------------------------------ de-duping

def deduplicate(evidence: Sequence[Evidence], *,
                lane_ppc: Mapping[LaneId, Fraction] | None = None,
                ) -> tuple[tuple[Evidence, ...], dict]:
    """One evidence vector per physical capture (DESIGN §0), finest wins."""
    best: dict[str, Evidence] = {}
    dropped: list[tuple[str, int]] = []
    for item in evidence:
        capture, level = item.lane
        held = best.get(capture)
        if held is None:
            best[capture] = item
            continue
        if _finer(item.lane, held.lane, lane_ppc):
            dropped.append((capture, int(held.lane[1])))
            best[capture] = item
        else:
            dropped.append((capture, int(level)))
    kept = tuple(best[capture] for capture in sorted(best))
    return kept, {"n_input": len(evidence), "n_captures": len(kept),
                  "levels_kept": tuple(
                      (item.lane[0][:12], int(item.lane[1]))
                      for item in kept),
                  "levels_dropped": tuple(
                      (capture[:12], level) for capture, level in dropped)}


def _finer(left: LaneId, right: LaneId,
           lane_ppc: Mapping[LaneId, Fraction] | None) -> bool:
    if lane_ppc is not None and left in lane_ppc and right in lane_ppc:
        return lane_ppc[left] > lane_ppc[right]
    return int(left[1]) > int(right[1])


# --------------------------------------------------------- the label view

def _label_view(evidence: Sequence[Evidence],
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-lane select-fold LLRs at the labels EVERY lane priced.

    Returns ``(rows, llr (L, n), values (n,))``; empty when the lanes
    share too few labels for a fit to mean anything.
    """
    rows: np.ndarray | None = None
    for item in evidence:
        mine = np.asarray(item.blind.get("label_rows", ()), np.int64)
        rows = mine if rows is None else np.intersect1d(
            rows, mine, assume_unique=True)
    if rows is None or not rows.size:
        return (np.zeros(0, np.int64), np.zeros((len(evidence), 0)),
                np.zeros(0, np.uint8))
    stack = np.empty((len(evidence), rows.size), np.float64)
    values = np.zeros(rows.size, np.uint8)
    for index, item in enumerate(evidence):
        mine = np.asarray(item.blind.get("label_rows", ()), np.int64)
        take = np.searchsorted(mine, rows)
        stack[index] = np.asarray(
            item.blind.get("label_llr", ()), np.float64)[take]
        values = np.asarray(
            item.blind.get("label_values", ()), np.uint8)[take]
    return rows, stack, values


def _discriminating_minority(evidence: Sequence[Evidence],
                             rows: np.ndarray) -> int:
    item = evidence[0]
    mine = np.asarray(item.blind.get("label_rows", ()), np.int64)
    flags = np.asarray(item.blind.get("label_discriminating", ()), bool)
    values = np.asarray(item.blind.get("label_values", ()), np.uint8)
    if flags.size != mine.size or not rows.size:
        return 0
    take = np.searchsorted(mine, rows)
    return _minority_count(values[take][flags[take]])


# --------------------------------------------------------------- the fits

def _platt_weights(stack: np.ndarray, values: np.ndarray,
                   ) -> tuple[np.ndarray, dict]:
    """Non-negative per-lane weights minimising the select-fold log loss.

    ``llr = sum_l w_l x_l`` with ``w_l >= 0``.  Only ``w`` is identified;
    the reported ``beta`` and ``temperature`` are its normalisation
    (``beta_l = w_l / mean(w)``, ``T = 1 / mean(w)``), so the two numbers
    a reader expects are there without fitting a redundant parameter.
    """
    y = np.asarray(values, np.float64)

    def objective(weights: np.ndarray) -> tuple[float, np.ndarray]:
        z = weights @ stack
        loss = float(np.mean(np.logaddexp(0.0, z) - y * z))
        gradient = (stack @ (pava.sigmoid(z) - y)) / max(1, y.size)
        return loss, gradient

    start = np.full(stack.shape[0], 1.0 / max(1, stack.shape[0]))
    result = optimize.minimize(
        objective, start, jac=True, method="L-BFGS-B",
        bounds=[(0.0, None)] * stack.shape[0],
        options={"maxiter": PLATT_MAX_ITERATIONS})
    weights = np.clip(np.asarray(result.x, np.float64), 0.0, None)
    mean = float(np.mean(weights)) if weights.size else 0.0
    return weights, {
        "platt_weights": tuple(float(value) for value in weights),
        "platt_beta": tuple(float(value / mean) if mean > 0.0 else 0.0
                            for value in weights),
        "platt_temperature": (1.0 / mean) if mean > 0.0 else None,
        "platt_converged": bool(result.success),
        "platt_logloss": float(result.fun)}


def _error_correlation(stack: np.ndarray, values: np.ndarray) -> float:
    """rho: the mean pairwise correlation of per-lane errors at labels.

    CENTRED WITHIN LABEL CLASS.  The raw error ``y - p`` carries the
    label itself (it is near +1 on a missed 1 and near -1 on a missed 0),
    so uncentred it correlates across lanes that share nothing but the
    page — measured here at rho = 0.55 for three provably independent
    lanes.  Removing each class's own mean leaves the lane-specific
    residual, which is what the multi-scan law is about: whether two
    captures fail on the SAME cells because the failure is print-frozen.
    """
    if stack.shape[0] < 2 or stack.shape[1] < 3:
        return 0.0
    y = np.asarray(values, np.float64)
    errors = y[None, :] - pava.sigmoid(stack)
    centred = np.array(errors, copy=True)
    for label in (0.0, 1.0):
        rows = y == label
        if int(np.count_nonzero(rows)) >= 2:
            centred[:, rows] -= centred[:, rows].mean(axis=1, keepdims=True)
    norm = np.sqrt(np.einsum("ln,ln->l", centred, centred))
    live = norm > 0.0
    if int(np.count_nonzero(live)) < 2:
        return 0.0
    unit = centred[live] / norm[live][:, None]
    gram = unit @ unit.T
    upper = gram[np.triu_indices(gram.shape[0], k=1)]
    return float(np.mean(upper))


# ----------------------------------------------------------- the combine

def combine(evidence: Sequence[Evidence], rule: str,
            folds: Folds | None = None, *, labels: Any = None,
            lane_ppc: Mapping[LaneId, Fraction] | None = None,
            agreement_threshold: float = AGREEMENT_UNANIMOUS,
            ) -> Combined:
    """DESIGN §5's rules over one tile-stream's lanes.

    `folds` is accepted for PLAN §1.2's signature and is not consulted:
    the select-fold restriction is already baked into the `label_*`
    arrays `analyzer.calibrate.calibrate` publishes, so a caller cannot
    accidentally fit a rule on a fold an arm searched.  `labels` overrides
    those arrays as ``(rows, llr_stack, values)`` for a test.
    """
    if rule not in RULES:
        raise CombineError(f"unknown rule {rule!r}; known: {RULES}")
    if not evidence:
        raise CombineError("combine: no evidence")
    del folds
    kept, detail = deduplicate(evidence, lane_ppc=lane_ppc)
    key = kept[0].key
    for item in kept:
        if item.key != key:
            raise CombineError(
                f"combine: evidence for {item.key} and {key} in one call")
    n = int(kept[0].llr_sequential.size)
    stack_seq = np.stack([np.asarray(item.llr_sequential, np.float64)
                          for item in kept])
    observed = np.zeros(n, bool)
    for item in kept:
        observed |= np.asarray(item.observed, bool)
    coefficients = np.ones(len(kept), np.float64)
    detail["rule_requested"] = rule
    effective = rule

    if labels is not None:
        rows, label_stack, values = labels
        rows = np.asarray(rows, np.int64)
        label_stack = np.asarray(label_stack, np.float64)
        values = np.asarray(values, np.uint8)
    else:
        rows, label_stack, values = _label_view(kept)
    detail["n_paired_labels"] = int(rows.size)

    if rule == "best":
        losses = [_select_loss(item, label_stack, values, index)
                  for index, item in enumerate(kept)]
        detail["per_lane_select_logloss"] = tuple(
            None if value is None else float(value) for value in losses)
        finite = [(value, index) for index, value in enumerate(losses)
                  if value is not None]
        chosen = min(finite)[1] if finite else 0
        coefficients = np.zeros(len(kept), np.float64)
        coefficients[chosen] = 1.0
        detail["best_lane"] = (kept[chosen].lane[0][:12],
                               int(kept[chosen].lane[1]))
    elif rule == "platt":
        minority = _discriminating_minority(kept, rows)
        detail["n_minority_discriminating"] = int(minority)
        if (label_stack.size == 0 or minority < SELECT_MIN_MINORITY
                or len(kept) < 2):
            detail["platt_refused"] = (
                "below_minority_floor" if minority < SELECT_MIN_MINORITY
                else "too_few_lanes_or_labels")
            effective = "sum"
        else:
            coefficients, platt = _platt_weights(label_stack, values)
            detail.update(platt)
            detail["platt_refused"] = None
    elif rule == "corr":
        rho = _error_correlation(label_stack, values)
        detail["error_correlation"] = float(rho)
        n_lanes = float(len(kept))
        bounded = float(np.clip(rho, 0.0, 1.0))
        scale = 1.0 / float(np.sqrt(1.0 + (n_lanes - 1.0) * bounded))
        coefficients = np.full(len(kept), scale, np.float64)
        detail["corr_scale"] = scale
    elif rule == "normalized":
        coefficients = np.full(len(kept), 1.0 / len(kept), np.float64)

    pooled, ctx_detail = pooled_ctx_offsets(kept, coefficients)
    detail.update(ctx_detail)

    llr = coefficients @ stack_seq
    llr[~observed] = 0.0
    # L7a's disagreement set is read against the sign the ladder decodes,
    # so it is computed from the FINISHED combination (DESIGN §6 L7a).
    if len(kept) < 2:
        disagree = agreement = None
        detail["n_disagreeing"] = 0
        detail["agreement_refused"] = "single_lane"
    else:
        disagree, agreement, agree_detail = lane_agreement(
            kept, stack_seq, llr, threshold=agreement_threshold)
        detail.update(agree_detail)
        disagree.setflags(write=False)
        agreement.setflags(write=False)
    clipped = int(np.count_nonzero(
        np.abs(llr[observed]) >= ldpc.LLR_CLIP)) if np.any(observed) else 0
    detail["rule_effective"] = effective
    detail["n_observed"] = int(np.count_nonzero(observed))
    llr = np.asarray(llr, np.float64)
    llr.setflags(write=False)
    observed.setflags(write=False)
    return Combined(
        key=key, rule=rule,
        lanes=tuple(item.lane for item in kept),
        coefficients=tuple(float(value) for value in coefficients),
        llr_sequential=llr, observed=observed,
        clipped_fraction=float(clipped) / max(1, int(
            np.count_nonzero(observed))),
        ctx_offsets=(None if pooled is None
                     else tuple(float(value) for value in pooled)),
        agreement=agreement, disagree=disagree)


def pooled_ctx_offsets(evidence: Sequence[Evidence],
                       coefficients: np.ndarray) -> tuple[np.ndarray | None,
                                                          dict]:
    """The context offsets a combined vector carries — DESIGN §6 L3.

    THE ONE SOUND FORM (RULED, W3).  Each lane's calibrated LLR already
    carries ITS OWN production-context offsets, and the combined vector is
    ``sum_l c_l * llr_l``; so the correction sitting in the combination is
    the COEFFICIENT-WEIGHTED MEAN of the lanes' offset vectors, and that
    is what L3 shifts between bin assignments.  Only lanes that actually
    ADOPTED a context correction contribute (a lane whose validation gate
    failed carries none), and the weights are renormalised over exactly
    those lanes so the pooled vector is on the LLR scale of the lanes it
    came from.

    Under `best` the coefficients are 0/1, so this collapses to the
    winning lane's own offsets — the "restrict L3 to the best rule's
    lane" reading is the same arithmetic, not a second rule.  When no
    lane adopted, the answer is None and L3 refuses.
    """
    weights: list[float] = []
    vectors: list[np.ndarray] = []
    for index, item in enumerate(evidence):
        if not bool(item.blind.get("ctx_adopted", False)):
            continue
        spec = item.blind.get("ctx_offsets")
        if spec is None:
            continue
        vector = np.asarray(spec, np.float64).ravel()
        weight = abs(float(coefficients[index]))
        if vector.size == 0 or weight == 0.0:
            continue
        weights.append(weight)
        vectors.append(vector)
    detail = {"ctx_lanes_adopted": len(vectors),
              "ctx_lanes": len(evidence)}
    if not vectors:
        return None, detail
    total = float(sum(weights))
    if total <= 0.0:
        return None, detail
    # The combined LLR is sum_l c_l * LLR_l and each lane's LLR already
    # carries its own adopted correction, so the correction PRESENT in the
    # combination is sum_l c_l * offsets_l — the coefficient-weighted SUM,
    # not the mean (W3 review, 2026-09-03: the mean under-shifted `sum`/`corr`
    # by ~1/L; exact for `best`/`normalized` where one lane carries c = 1).
    pooled = np.zeros(vectors[0].size, np.float64)
    for weight, vector in zip(weights, vectors):
        if vector.size != pooled.size:
            detail["ctx_refused"] = "ragged_offset_vectors"
            return None, detail
        pooled += weight * vector
    detail["ctx_offsets"] = tuple(float(value) for value in pooled)
    detail["ctx_weights"] = tuple(float(value) for value in weights)
    detail["ctx_weight_total"] = total
    return pooled, detail


def lane_agreement(evidence: Sequence[Evidence], stack_seq: np.ndarray,
                   llr_combined: np.ndarray, *,
                   threshold: float = AGREEMENT_UNANIMOUS,
                   ) -> tuple[np.ndarray, np.ndarray, dict]:
    """L7a's producer: per-cell sign agreement across the lanes (DESIGN §6).

    A lane VOTES at a sequential position when it observed the cell and
    priced it (a zero LLR is no evidence, so it is not a vote — the same
    rule `combine` uses for `n_observed`).  The agreement fraction is the
    share of voting lanes whose sign matches the COMBINED sign, which is
    the sign the ladder will actually decode; a cell where the lanes split
    is a cell the multi-scan law says one capture read through a defect the
    others did not, and L7a erases those first.

    A position with fewer than two voting lanes can never disagree, so a
    single-lane combination produces an EMPTY index set and L7a refuses
    exactly as it did before this producer existed.  Positions the lanes
    priced with opposite and exactly cancelling weight get combined sign 0
    and agreement 0 — maximal disagreement, which is what they are.

    Returns ``(disagreeing indices, agreement per position, detail)``.
    """
    voting = np.zeros(stack_seq.shape, bool)
    for index, item in enumerate(evidence):
        voting[index] = (np.asarray(item.observed, bool)
                         & (stack_seq[index] != 0.0))
    n_voting = voting.sum(axis=0)
    combined_sign = np.sign(np.asarray(llr_combined, np.float64))
    agrees = (np.sign(stack_seq) == combined_sign[None, :]) & voting
    fraction = np.where(n_voting > 0,
                        agrees.sum(axis=0) / np.maximum(n_voting, 1), 1.0)
    eligible = n_voting >= 2
    index = np.flatnonzero(eligible & (fraction < float(threshold)))
    detail = {"agreement_threshold": float(threshold),
              "n_agreement_eligible": int(np.count_nonzero(eligible)),
              "n_disagreeing": int(index.size),
              "mean_agreement": (float(fraction[eligible].mean())
                                 if np.any(eligible) else None)}
    return index.astype(np.int64), fraction, detail


def _select_loss(item: Evidence, stack: np.ndarray, values: np.ndarray,
                 index: int) -> float | None:
    """One lane's select-fold log loss, from the paired labels if there
    are any and from its own diag otherwise."""
    if stack.size and index < stack.shape[0]:
        return float(np.mean(_per_label_loss(stack[index], values)))
    value = item.blind.get("heldout_logloss_select")
    return None if value is None else float(value)


def combine_detail(result: Combined) -> dict:
    """The ledger-safe summary DESIGN §9 nests under the row."""
    return {"rule": result.rule,
            "lanes": tuple((lane[0][:12], int(lane[1]))
                           for lane in result.lanes),
            "coefficients": result.coefficients,
            "clipped_fraction": result.clipped_fraction,
            "ctx_offsets": result.ctx_offsets,
            # Counts, never the per-cell vectors: the ledger carries one row
            # per tile-stream and a 3,976-entry agreement vector per rule
            # would swamp it (DESIGN §9).
            "n_disagreeing": (None if result.disagree is None
                              else int(result.disagree.size)),
            "mean_agreement": (
                None if result.agreement is None
                else float(np.mean(result.agreement))),
            "n_observed": int(np.count_nonzero(result.observed))}


# --------------------------------------------------------- the re-roll

def reroll_sets(candidates_by_lane: Mapping[LaneId, Sequence[Evidence]],
                selected: Sequence[Evidence],
                ) -> tuple[tuple[str, tuple[Evidence, ...]], ...]:
    """The evidence sets the arm CHOICE did not use — GAPS §7's re-roll.

    The measurement's diagnosis: the C tiles production had to work hardest
    for sit in the BP waterfall at mean R ~= 0.80-0.93, where certification
    is a coin flip and every factor that "recovers" one moves R by a
    hundredth.  Production won them with six tools and hundreds of attempts
    each; the analyzer computes a whole battery of evidence, uses ONE of it
    (the arm the select fold picked) and throws the rest away.  This hands
    the rest back, one set per arm, so the ladder can be re-rolled on
    evidence that is already paid for.

    It is not a second selection and it does not touch the select fold: the
    certificate gate (syndrome + CRC) is the only thing that can accept any
    of these, so a re-roll cannot make a wrong certificate more likely than
    the exposure bound already prices.  The set that the selection already
    ran is skipped by construction; order is the battery's, first
    appearance first, so a re-roll is deterministic.
    """
    chosen_by_lane = {item.lane: item.arm for item in selected}
    order: list[str] = []
    by_arm: dict[str, dict[LaneId, Evidence]] = {}
    for lane in sorted(candidates_by_lane):
        for item in candidates_by_lane[lane]:
            if item.arm not in by_arm:
                by_arm[item.arm] = {}
                order.append(item.arm)
            by_arm[item.arm][lane] = item
    out: list[tuple[str, tuple[Evidence, ...]]] = []
    for arm in order:
        lanes = by_arm[arm]
        if not lanes:
            continue
        if all(chosen_by_lane.get(lane) == arm for lane in lanes) \
                and set(lanes) == set(chosen_by_lane):
            continue                       # the selection already ran this
        out.append((arm, tuple(lanes[lane] for lane in sorted(lanes))))
    return tuple(out)


# ------------------------------------------ independent certificate agreement

@dataclass(frozen=True)
class CertificateClaim:
    """One gate-passing certificate for one key, with its provenance.

    `captures` is the set of PHYSICAL captures the combination that
    produced it actually leaned on — the lanes whose coefficient is
    non-zero, so `best` names one capture and `sum` names all of them.
    """

    label: str
    rung: str
    verdict: str
    captures: frozenset[str]
    user_bits: np.ndarray

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            np.asarray(self.user_bits, np.uint8).tobytes()).hexdigest()


def contributing_captures(detail: Mapping[str, Any]) -> frozenset[str]:
    """The captures a `combine_detail` summary's certificate rests on.

    A zero coefficient contributes nothing to ``sum_l c_l * llr_l``, so
    the lane it names is not evidence for anything the combination
    decided; under `best` that leaves exactly the winning capture.
    """
    lanes = tuple(detail.get("lanes", ()) or ())
    coefficients = tuple(detail.get("coefficients", ()) or ())
    if len(coefficients) != len(lanes):
        return frozenset(str(lane[0]) for lane in lanes)
    return frozenset(str(lane[0])
                     for lane, value in zip(lanes, coefficients)
                     if float(value) != 0.0)


def independent_agreement(claims: Sequence[CertificateClaim]) -> dict:
    """How many MUTUALLY INDEPENDENT certificates for one key agree.

    THE FOURTH LEG of the correctness argument (RULING, 2026-09-04):
    beside the syndrome+CRC gate with its priced exposure, the envelope
    sha at the close and the fountain's over-determination, a key that
    two lanes certify INDEPENDENTLY, bit for bit, is a key whose bits two
    disjoint sets of paper readings agree on.

    INDEPENDENCE IS DISJOINT PHYSICAL CAPTURES, not distinct rules or
    arms.  Two rules over the same lanes read the same pixels through
    the same evidence vectors, and DESIGN §0's physical-evidence
    invariant is exactly the statement that this is ONE observation; a
    re-roll on a different arm is likewise the same paper.  So a claim
    counts as independent of the ones already counted only when its
    capture set is disjoint from all of theirs — which is what makes the
    agreement evidence rather than bookkeeping.

    THE COUNT IS A LOWER BOUND.  Choosing the largest pairwise-disjoint
    subfamily of a set family is NP-hard in general; this takes the
    smallest capture sets first, which is optimal when the sets are
    nested or disjoint (the shapes `best` and `sum` actually produce) and
    a lower bound otherwise.  Cost is O(n^2) in the number of claims,
    which is at most one per (rule, rung) attempted.

    A DISAGREEMENT IS A CONTRADICTION.  Two certificates for one key with
    different bits both passed syndrome and CRC, so at least one of them
    is a false accept and NOTHING here can say which.  `contradiction` is
    then True and the caller must refuse the key — never mint.  This is
    strictly stronger than the independent case on purpose: two claims
    that share a capture and still disagree are the same impossibility.
    """
    claims = tuple(claims)
    out: dict[str, Any] = {
        "n_claims": len(claims),
        "independent_agreement": 0,
        "contradiction": False,
        "n_distinct_bits": 0,
        "claims": [{"label": item.label, "rung": item.rung,
                    "verdict": item.verdict,
                    "captures": sorted(item.captures),
                    "sha256": item.sha256[:16]} for item in claims],
    }
    if not claims:
        return out
    by_digest: dict[str, list[CertificateClaim]] = {}
    for item in claims:
        by_digest.setdefault(item.sha256, []).append(item)
    out["n_distinct_bits"] = len(by_digest)
    if len(by_digest) > 1:
        first = claims[0]
        out["contradiction"] = True
        out["contradicting"] = [
            {"label": item.label, "rung": item.rung,
             "sha256": item.sha256[:16],
             "n_bits_differing_from_first": int(np.count_nonzero(
                 np.asarray(item.user_bits, np.uint8)
                 != np.asarray(first.user_bits, np.uint8)))
             if item.user_bits.shape == first.user_bits.shape else -1}
            for item in claims]
        out["refusal"] = ("two gate-passing certificates for this key "
                          "carry different bits")
        return out
    taken: list[CertificateClaim] = []
    covered: set[str] = set()
    for item in sorted(claims, key=lambda claim: (len(claim.captures),
                                                  claim.label, claim.rung)):
        if not item.captures or (item.captures & covered):
            continue
        taken.append(item)
        covered |= set(item.captures)
    out["independent_agreement"] = len(taken)
    out["independent_claims"] = [
        {"label": item.label, "rung": item.rung,
         "captures": sorted(item.captures)} for item in taken]
    out["sha256"] = claims[0].sha256[:16]
    return out

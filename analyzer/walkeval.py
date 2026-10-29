"""The self-discovery walk's OBJECTIVE — what a knob search is scored on.

BLIND.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`, and nothing here imports
:mod:`analyzer.patch`, :mod:`analyzer.autoknobs`, :mod:`analyzer.arms` or
:mod:`analyzer.unmix` — the first two dispatch INTO this module and the
last two dispatch into them.  :mod:`analyzer.patchfit` is imported inside
:func:`cargo_profile` for exactly that reason: `patchfit` imports
`autoknobs`, which imports this module at its top, so a module-level
import here would close the cycle.  One deferred import, named, with the
cycle written down.

WHY (HALO-CHANNEL-2026-09-07 §2.3-§2.4, §3(b)).  `autoknobs.choose`
compares two candidate filters by their held-out log loss on the halo's
own SEARCH-fold labels.  Those labels are the furniture of the tiles the
footprint touches plus the projected cargo of the neighbours THAT
CERTIFIED — a sample selected on exactly the quantity being measured.
Measured on sheet H's two `auto` ledgers, their own cross-fit error is
0.0356 (halo 16) / 0.0202 (halo 48) on the three-ink state, against the
dead band's three-ink cargo at 0.152-0.171: **the walk optimises a
population four times easier than the cargo it will price**, and two
filters that differ by 4.4 points of cargo cell error and 19 certificates
differ by 0.009 nats there.  This is the same defect the pure path had
ruled on it (APPROACHES §4.0 ruling 15, DESIGN §14.5, fixed in
`583b482`: "the halo's number is a floor, not an estimate"); the walk was
never given the treatment, and this module is that treatment.

THREE MECHANISMS, all on the SEARCH fold (DESIGN §4.8 gives every
within-arm search that fold; the select fold stays untouched, so
`select_arm`, `platt`, `platt-state` and `best` still arbitrate on labels
nothing here minimised):

* **W1, the cargo weighting** (:func:`cargo_profile`,
  :func:`cargo_weights`).  The walk's per-label losses are
  importance-weighted so the halo's histogram over two BLIND covariates —
  the sibling state (a fact of the two SIBLING planes) and a difficulty
  bin from the incumbent box-mean score — matches the target tile's own
  cargo.  Blind because the target tile's cargo carries NO target-plane
  bit by construction (`analyzer.frame`'s run-abort assertion
  ``known[in_tile & cargo, target_plane].sum() == 0``), so the profile
  consumes no fold and no label: it is a histogram of an UNLABELLED
  population's covariates.  The weights multiply losses; they restrict no
  hypothesis and enter no certificate.
* **W2, the franchise**, is `analyzer.patch`'s (a population that cannot
  carry its own vote inherits a DISCOVERY — the pooled walk — and not a
  module constant); this module only prices it.
* **W3, the burden of proof** (:func:`paired_verdict`'s `direction`).
  `red` is literally nested inside `rgb` — the same 144 columns plus 288
  — so on that axis the richer candidate is adopted UNLESS the leaner one
  wins by `calibrate.SELECT_SE_MULTIPLE` standard errors.

DETERMINISM.  No RNG: quantile edges, a histogram, and a bisection with a
fixed iteration count.  Two calls on the same inputs are bit-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from holo.receiver.lib import pava

from . import calibrate as cal

__all__ = [
    "CargoProfile", "DIRECTIONS", "DIRECTION_ADOPT", "DIRECTION_KEEP",
    "ESS_FLOOR_FRACTION", "LOSS_CARGO", "LOSS_HALO", "MAX_BINS",
    "MAX_UNMATCHED_CARGO", "MIN_LABELS_PER_BIN", "WALK_POPULATIONS",
    "cargo_profile", "cargo_weights", "loss_population", "paired_verdict",
    "weighted_mean",
]

#: The ordinary direction: the CANDIDATE has to prove a gain.
DIRECTION_ADOPT: str = "adopt_if_better"
#: W3's direction, for an axis whose candidates NEST: the richer side is
#: adopted unless the leaner one proves a gain.
DIRECTION_KEEP: str = "keep_unless_worse"
DIRECTIONS: tuple[str, ...] = (DIRECTION_ADOPT, DIRECTION_KEEP)

#: Difficulty bins.  DERIVED, not pinned (§4.1): the median block's
#: search fold at halo 16 carries 451 labels over the four sibling states
#: (~110 each) and `calibrate.SELECT_MIN_MINORITY` is 40, so a bin under
#: ~25 labels cannot carry a paired difference; four is where that stops
#: buying resolution on the widest block in the record.
MIN_LABELS_PER_BIN: int = 25
MAX_BINS: int = 4
#: THE COUNT THE BINS ARE AFFORDABLE FOR (2026-09-07 review).  The
#: profile is built ONCE per `patch_score` call and serves both the
#: pooled walk (which sees every walk label) and the PER-STATE walks
#: (which see their own state's share, and are the majority of the
#: walks), so the bin count has to be affordable for the smaller of the
#: two or a per-state walk gets four bins on a quarter of the labels —
#: the regime §4.1's own derivation says cannot carry a paired
#: difference.  The states partition the labels, so the derivation
#: divides by their number: `statecal.sibling_state`'s four (both
#: siblings' presence, 2x2), spelled here because importing `statecal`
#: for one integer would put a second analyzer module in this file's
#: import list.  At the median block (451 labels) this is still 4 bins;
#: it is the SMALL blocks it protects.
WALK_POPULATIONS: int = 4

#: What `autoknobs.choose`'s published losses are the mean OVER — the
#: halo's own search-fold labels, or those labels reweighted onto the
#: target tile's cargo (W1).  A number that does not name its population
#: is the whole defect this module exists for, so the walk publishes it.
LOSS_HALO: str = "halo_search_labels"
LOSS_CARGO: str = "cargo_weighted_halo_search_labels"

#: THE VARIANCE BUDGET, argued not picked (§4.1).  The bar a walk has to
#: clear is 2 SE, and SE is proportional to n^(-1/2); halving the
#: effective count therefore costs sqrt(2) in that bar, which is less
#: than the 2.15 the halo change moves it (§2.3).  So the correction may
#: not spend more than the effect it corrects: the weights are clipped
#: until the Kish effective sample size clears half the raw count.
ESS_FLOOR_FRACTION: float = 0.5
#: Cargo mass in bins that hold NO halo label.  Above this the weighting
#: REFUSES and the walk runs unweighted — a refusal, never a fabricated
#: number.
MAX_UNMATCHED_CARGO: float = 0.5

#: Bisection steps for the clip.  `_ess` is monotone in the clip, the
#: bracket is [1, max weight], and 60 halvings resolve it to the last
#: double it can express.
_CLIP_STEPS: int = 60


@dataclass(frozen=True)
class CargoProfile:
    """The blind covariate histogram of the cells a filter will price.

    `edges` and `bins_by_state` are keyed by SIBLING STATE (including
    `statecal.STATE_UNKNOWN`, which is a real part of a cargo the walk
    will price).  The edges are per state because the quantiles are the
    state's own: a state-3 cargo compressed toward the decision midpoint
    has its own |z| scale, and pooled edges would put nearly all of it in
    one bin and correct nothing inside it.

    `z` is the incumbent box-mean score of EVERY row, standardised by
    `patchfit.fallback_population` — NaN where the lane does not observe
    the cell.  It is carried here so the halo's rows and the cargo's
    share one footing by construction (one call, not two).
    """

    bins_by_state: Mapping[int, np.ndarray]
    edges: Mapping[int, np.ndarray]
    n_cargo_by_state: Mapping[int, int]
    n_bins: int
    centre: float
    scale: float
    centred_on: str
    z: np.ndarray
    refused: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def n_cargo(self) -> int:
        return int(sum(self.n_cargo_by_state.values()))


def cargo_profile(fallback: np.ndarray, *, observed: np.ndarray,
                  in_tile: np.ndarray, cargo: np.ndarray,
                  state: np.ndarray, known_target_fit: np.ndarray,
                  values: np.ndarray, min_per_class: int,
                  n_walk_labels: int) -> CargoProfile:
    """The target tile's own cargo, as (sibling state x difficulty) mass.

    THE DIFFICULTY STATISTIC is ``abs(z)``, where `z` is
    `patchfit.fallback_population`'s standardised `subtract` score — the
    incumbent box-mean read, centred at its own FIT-FOLD class midpoint
    and divided by its fit-fold sd.  Small ``|z|`` is near the decision
    midpoint, which is precisely what the third toner layer does to a C
    cell (MEASUREMENTS-2026-09-06-C-THIRD-LAYER §3).  The call is made
    ONCE over every observed row, so the halo's labels and the tile's
    cargo are measured on one footing rather than two.

    NO LABEL OF THE TARGET PLANE IS READ INSIDE THE TILE.  `values` and
    `known_target_fit` enter only through `fallback_population`'s
    centring, which reads FIT-FOLD labelled rows; the tile's own cargo
    carries no target-plane bit at all (`frame`'s run-abort assertion),
    so the histogram below is a histogram of an unlabelled population.
    """
    observed = np.asarray(observed, bool)
    state = np.asarray(state, np.int8)
    n = int(observed.size)
    rows_observed = np.flatnonzero(observed)
    z = np.full(n, np.nan, np.float64)
    centre, scale, centred_on = 0.0, 1.0, "none"
    if rows_observed.size:
        # DEFERRED (see the module docstring): `patchfit` imports
        # `autoknobs`, which imports this module.
        from . import patchfit
        scores, detail = patchfit.fallback_population(
            np.asarray(fallback, np.float64), rows_observed,
            np.asarray(known_target_fit, bool), np.asarray(values, np.uint8),
            int(min_per_class))
        z[rows_observed] = np.asarray(scores, np.float64)
        centre = float(detail["patch_fallback_centre_value"])
        scale = float(detail["patch_fallback_scale"])
        centred_on = str(detail["patch_fallback_centre"])
    z.setflags(write=False)
    #: `n_walk_labels` is the TILE-WIDE search-fold count; the per-state
    #: walks each see about a `WALK_POPULATIONS`-th of it and the bins
    #: have to be affordable for them too (2026-09-07 review).
    n_bins = int(min(MAX_BINS, max(1, int(n_walk_labels)
                                   // (MIN_LABELS_PER_BIN
                                       * WALK_POPULATIONS))))
    target = (observed & np.asarray(in_tile, bool) & np.asarray(cargo, bool)
              & np.isfinite(z))
    bins_by_state: dict[int, np.ndarray] = {}
    edges_by_state: dict[int, np.ndarray] = {}
    counts_by_state: dict[int, int] = {}
    for value in np.unique(state[target]) if np.any(target) else ():
        mine = np.abs(z[target & (state == value)])
        if not mine.size:
            continue
        edges = _quantile_edges(mine, n_bins)
        counts = np.bincount(_bin_of(mine, edges), minlength=n_bins)
        total = float(counts.sum())
        edges.setflags(write=False)
        share = counts.astype(np.float64) / total
        share.setflags(write=False)
        edges_by_state[int(value)] = edges
        bins_by_state[int(value)] = share
        counts_by_state[int(value)] = int(total)
    refused = None if counts_by_state else "no_observed_cargo_cells"
    return CargoProfile(
        bins_by_state=bins_by_state, edges=edges_by_state,
        n_cargo_by_state=counts_by_state, n_bins=n_bins, centre=centre,
        scale=scale, centred_on=centred_on, z=z, refused=refused,
        detail={"n_walk_labels": int(n_walk_labels),
                "n_cargo": int(sum(counts_by_state.values()))})


def _quantile_edges(values: np.ndarray, n_bins: int) -> np.ndarray:
    """The interior quantile edges of one state's cargo — at most `n_bins-1`.

    DE-DUPLICATED: a cargo with a point mass (an incumbent score that
    saturates, which is exactly what a dead band does) puts several
    quantiles on one value, and repeated edges are empty bins that would
    make the histogram unreadable and the bin index degenerate.  Fewer
    distinct edges is fewer bins, which the shares carry honestly.
    """
    if int(n_bins) <= 1:
        return np.zeros(0, np.float64)
    fractions = np.arange(1, int(n_bins), dtype=np.float64) / float(n_bins)
    edges = np.asarray(np.quantile(np.asarray(values, np.float64),
                                   fractions), np.float64)
    return np.unique(edges)


def _bin_of(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Which bin each `|z|` falls in; a tie with an edge goes BELOW it.

    `side="left"`, so a point mass sitting exactly on its own quantile
    stays in one bin instead of being swept into the bin above it with
    everything else — with a continuous statistic the two conventions
    agree, and with a point mass only this one separates it.
    """
    return np.asarray(np.searchsorted(np.asarray(edges, np.float64),
                                      np.asarray(values, np.float64),
                                      side="left"), np.int64)


def cargo_weights(profile: CargoProfile, *, state_of_row: np.ndarray,
                  z_of_row: np.ndarray, pooled: bool,
                  ) -> tuple[np.ndarray | None, dict]:
    """Importance weights that move the halo's histogram onto the cargo's.

    ``w_i ∝ cargo_share(bin_i[, state_i]) / halo_share(bin_i[, state_i])``,
    mean-normalised.  `pooled=True` — the state-agnostic tier, which pools
    every sibling state — matches the STATE histogram as well; a per-state
    walk already has the state exactly right and matches bins WITHIN its
    own state, so the state mix it was handed is left alone.

    Returns ``(weights, detail)``, and `weights` is None when the
    weighting REFUSES: no cargo at all, a single bin with nothing to
    correct, more than `MAX_UNMATCHED_CARGO` of the cargo's mass in bins
    that hold no halo label, or a variance budget the clip cannot reach.
    A refusal runs the walk unweighted and says so; it never fabricates a
    number.
    """
    state_of_row = np.asarray(state_of_row, np.int8)
    values = np.abs(np.asarray(z_of_row, np.float64))
    n = int(values.size)
    detail: dict[str, Any] = {
        "weighting": "cargo", "pooled": bool(pooled), "n": n,
        "n_bins": int(profile.n_bins), "ess": float(n), "clip": None,
        "unmatched_cargo_fraction": 0.0, "refused": None}
    if profile.refused is not None:
        detail["refused"] = str(profile.refused)
        return None, detail
    if n < pava.CAL_MIN_HELDOUT or not np.all(np.isfinite(values)):
        detail["refused"] = ("too_few_rows" if n < pava.CAL_MIN_HELDOUT
                             else "a_row_has_no_incumbent_score")
        return None, detail
    if profile.n_bins <= 1 and not pooled:
        detail["refused"] = "one_bin"
        return None, detail

    # the halo's own (state, bin) histogram, over the rows handed in
    bins = np.zeros(n, np.int64)
    matched = np.zeros(n, bool)
    for value, edges in profile.edges.items():
        mine = state_of_row == value
        if np.any(mine):
            bins[mine] = _bin_of(values[mine], edges)
            matched[mine] = True
    n_matched = int(np.count_nonzero(matched))
    detail["n_rows_without_cargo_state"] = int(n - n_matched)
    if not n_matched:
        detail["refused"] = "no_row_shares_a_state_with_the_cargo"
        return None, detail
    cells = state_of_row.astype(np.int64) * profile.n_bins + bins
    halo_count: dict[int, int] = {int(cell): int(count) for cell, count
                                  in zip(*np.unique(cells[matched],
                                                    return_counts=True))}
    #: THE TARGET distribution over (state, bin) cells.  Pooled: the
    #: cargo's own joint mass over every state it has.  Per state: the
    #: cargo's bin shares INSIDE each state, carried at the halo's own
    #: state mix — a per-state walk already has the state exactly right,
    #: so nothing about the state covariate is moved.
    target: dict[int, float] = {}
    if pooled:
        cargo_total = float(sum(profile.n_cargo_by_state.values()))
        for value, share in profile.bins_by_state.items():
            weight = float(profile.n_cargo_by_state[value]) / cargo_total
            for index in range(profile.n_bins):
                target[int(value) * profile.n_bins + index] = (
                    float(share[index]) * weight)
    else:
        for value in np.unique(state_of_row[matched]):
            share = profile.bins_by_state[int(value)]
            weight = (float(np.count_nonzero(matched & (state_of_row == value)))
                      / float(n_matched))
            for index in range(profile.n_bins):
                target[int(value) * profile.n_bins + index] = (
                    float(share[index]) * weight)
    mass = float(sum(target.values()))
    if not mass > 0.0:
        detail["refused"] = "no_cargo_mass_for_these_rows"
        return None, detail
    unmatched = sum(value for cell, value in target.items()
                    if cell not in halo_count) / mass
    detail["unmatched_cargo_fraction"] = float(unmatched)
    if unmatched > MAX_UNMATCHED_CARGO:
        detail["refused"] = "cargo_mass_the_halo_cannot_reach"
        return None, detail
    raw = np.zeros(n, np.float64)
    for cell, count in halo_count.items():
        raw[cells == cell] = ((target.get(cell, 0.0) / mass)
                              * (float(n_matched) / float(count)))
    #: a row whose sibling state has no cargo at all: it prices nothing
    #: the pooled walk will meet (weight 0), and for a per-state walk
    #: there is nothing inside it to correct (weight 1, left alone).
    if n_matched < n:
        raw[~matched] = 0.0 if pooled else 1.0
    mean = float(raw.mean())
    if not mean > 0.0:
        detail["refused"] = "every_weight_is_zero"
        return None, detail
    raw = raw / mean
    weights, clip, ess = _clip_to_budget(raw, ESS_FLOOR_FRACTION * n)
    detail["ess"] = float(ess)
    detail["clip"] = None if clip is None else float(clip)
    if weights is None:
        detail["refused"] = "the_variance_budget_is_unreachable"
        return None, detail
    weights.setflags(write=False)
    return weights, detail


def _ess(weights: np.ndarray) -> float:
    """Kish's effective sample size — scale-free, so the clip decides it."""
    total = float(np.sum(weights))
    square = float(np.sum(weights * weights))
    return (total * total / square) if square > 0.0 else 0.0


def _clip_to_budget(raw: np.ndarray, floor: float,
                    ) -> tuple[np.ndarray | None, float | None, float]:
    """The LEAST clipping whose effective sample size still clears `floor`.

    `_ess(min(raw, c))` is monotone NON-INCREASING in `c` — a bigger cap
    lets the extreme weights back in — so the cheapest correction that
    fits the budget is the LARGEST `c`, and the budget binds from above.
    (Read the other way the rule is empty: `c = 1` always fits and
    weights nothing.)  With no clip needed the raw weights come back
    untouched; when even `c = 1` cannot reach the floor the weighting
    refuses rather than pretend.
    """
    top = float(np.max(raw)) if raw.size else 1.0
    if _ess(raw) >= floor:
        return raw, None, _ess(raw)
    if top <= 1.0:
        return None, None, _ess(raw)
    flattest = np.minimum(raw, 1.0)
    if _ess(flattest) < floor:
        return None, None, _ess(flattest)
    low, high = 1.0, top                 # ess(low) >= floor > ess(high)
    for _step in range(_CLIP_STEPS):
        middle = 0.5 * (low + high)
        if _ess(np.minimum(raw, middle)) >= floor:
            low = middle
        else:
            high = middle
    clipped = np.minimum(raw, low)
    mean = float(clipped.mean())
    if mean > 0.0:
        clipped = clipped / mean
    return clipped, low, _ess(clipped)


def loss_population(weights: np.ndarray | None) -> str:
    """Which population a walk's published losses are the mean over."""
    return LOSS_HALO if weights is None else LOSS_CARGO


def weighted_mean(values: np.ndarray, weights: np.ndarray | None) -> float:
    """The decision loss: `np.mean` unweighted, the weighted mean under W1.

    2026-09-07 review.  `autoknobs.choose` minimised the inner ridge and
    published `auto_losses` / `baseline_logloss` on the PLAIN halo mean
    while the outer paired verdict used the weights, so under
    `walk_weighting=cargo` the regulariser was still chosen on exactly
    the population W1 exists to reject and the ledger's loss was not the
    quantity the decision was made on.  One quantity now.  With
    `weights=None` this is `float(np.mean(values))` to the bit.
    """
    values = np.asarray(values, np.float64)
    if weights is None:
        return float(np.mean(values))
    w = np.asarray(weights, np.float64)
    if w.size != values.size:
        return float(np.mean(values))
    total = float(np.sum(w))
    if not total > 0.0:
        return float(np.mean(values))
    return float(np.sum(w * values) / total)


def paired_verdict(base: np.ndarray, candidate: np.ndarray, *,
                   weights: np.ndarray | None = None,
                   direction: str = DIRECTION_ADOPT) -> dict:
    """`select_arm`'s paired test, weighted, in one of two directions.

    `base - candidate` is positive where the CANDIDATE reads better.  The
    mean and the standard error are weighted (Kish): with `weights=None`
    the arithmetic is `autoknobs.paired_verdict`'s to the last bit — the
    reliability-weight variance ``Σw(d-m)²/(Σw - Σw²/Σw)`` collapses to
    `np.std(ddof=1)²` and the effective count to `n`.

    `direction`:

    * `DIRECTION_ADOPT` — adopt when the candidate's mean gain clears
      `calibrate.SELECT_SE_MULTIPLE` standard errors.  Ties lose.
    * `DIRECTION_KEEP` (W3, the NESTED axes) — the candidate is the
      richer model and is adopted unless the LEANER side clears the same
      bar.  Ties go to the richer model.

    A comparison that cannot be made (`pava.CAL_MIN_HELDOUT` on the RAW
    count, or a candidate that refused) adopts NOTHING in either
    direction: a refusal is not evidence, and the population that cannot
    vote is W2's business, not this function's.
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"paired_verdict: direction {direction!r} is not "
                         f"one of {DIRECTIONS}")
    base = np.asarray(base, np.float64)
    candidate = np.asarray(candidate, np.float64)
    n = int(base.size)
    if candidate.size != n or n < pava.CAL_MIN_HELDOUT:
        return {"adopted": False, "mean_difference": 0.0,
                "standard_error": float("inf"), "n": n, "ess": 0.0,
                "reason": "too_few_paired_labels"}
    weighted = weights is not None and int(np.asarray(weights).size) == n
    difference = base - candidate            # positive = candidate better
    if not weighted:
        #: LITERALLY today's three lines, so an unweighted walk is
        #: bit-identical and not merely equal in exact arithmetic
        mean = float(np.mean(difference))
        se = (float(np.std(difference, ddof=1) / np.sqrt(difference.size))
              if difference.size > 1 else float("inf"))
        ess = float(n)
        logloss = float(np.mean(candidate))
    else:
        w = np.asarray(weights, np.float64)
        total = float(np.sum(w))
        if not total > 0.0:
            return {"adopted": False, "mean_difference": 0.0,
                    "standard_error": float("inf"), "n": n, "ess": 0.0,
                    "reason": "no_weight"}
        mean = float(np.sum(w * difference) / total)
        ess = _ess(w)
        logloss = float(np.sum(w * candidate) / total)
        #: the reliability-weight variance ``Σw(d-m)²/(Σw - Σw²/Σw)``;
        #: with unit weights it is `np.var(difference, ddof=1)` exactly
        denominator = total - float(np.sum(w * w)) / total
        if n > 1 and denominator > 0.0 and ess > 0.0:
            variance = float(np.sum(w * (difference - mean) ** 2)
                             / denominator)
            se = float(np.sqrt(variance / ess))
        else:
            se = float("inf")
    bar = cal.SELECT_SE_MULTIPLE * se
    if direction == DIRECTION_ADOPT:
        adopted = bool(mean > bar and se > 0.0)
    else:
        #: THE DEGENERATE CASE, EXPLICITLY (2026-09-07 review).  With a
        #: zero-variance paired difference the bar is 0 and `se > 0.0`
        #: is False, so the leaner side could never clear it and a
        #: richer candidate that is uniformly and DETERMINISTICALLY
        #: worse was adopted.  A constant difference needs no standard
        #: error to be read: its sign is the whole evidence.  Ties still
        #: go to the richer model (`mean == 0.0` is a tie), which is
        #: what the direction is for.
        worse = bool((-mean > bar and se > 0.0)
                     or (se == 0.0 and mean < 0.0))
        adopted = not worse
    return {"adopted": adopted, "mean_difference": mean,
            "standard_error": se, "n": n, "ess": float(ess),
            "select_logloss": logloss, "weighted": bool(weighted),
            "direction": str(direction), "reason": None}

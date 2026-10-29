"""Self-discovery — the knobs a run chooses for itself (W8 B7).

BLIND.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`, and nothing here imports
:mod:`analyzer.patch` (which dispatches into this module).

THE RULING (Germano, 2026-09-06): "even the existing pins / defaults are
not well grounded.  if a run can discover its own truth for the
paper-print-scanner-scan object at hand, it should!"  So no value in the
patch family is a number carried over from a sweep on one sheet.  Every
knob a run can decide for itself takes the value `"auto"`, and `"auto"`
is what the patch and pure profiles ask for; the module constants that
were the defaults stay exactly where they are and become the INHERITED
FALLBACK — what a run uses when its own select fold cannot tell the
candidates apart.

HOW A RUN DECIDES.  DESIGN §4.8 already has the arbitration: a PAIRED
test with a standard-error margin (`calibrate.select_arm`).  This module
is that test applied one level down — to the knobs of one arm instead of
to the arms — and it is run ON THE SEARCH FOLD, because a knob walk is a
within-arm SEARCH and §4.8 reserves the search fold for those ("an offset
chosen here has not seen the fold the arm choice is made on").  The
select fold stays untouched, so `select_arm`, `platt`, `platt-state` and
`best` still arbitrate on labels nothing here minimised (review
2026-09-06; the wave as first built walked the select fold, which made
every auto arm's `label_llr` a minimum over its own candidate set on
precisely the rows the arm choice pairs on):

  * every candidate is fitted on the FIT fold and cross-fitted inside it
    (APPROACHES ruling 7: a fitted score may never be calibrated on its
    own training rows), so every candidate carries out-of-fold scores;
  * those scores fit a PAVA map, the map prices the SEARCH fold's labels,
    and the per-label log losses of two candidates are compared PAIRED
    over the same rows — adopted only when the mean gain clears
    `calibrate.SELECT_SE_MULTIPLE` standard errors, refused below
    `calibrate.SELECT_MIN_MINORITY` minority labels or `pava`'s own
    held-out floor;
  * the walk over the axes is a single COORDINATE pass in a fixed order
    (`AXIS_ORDER`), each axis compared against the choice so far, so the
    work is a sum over the axes rather than a product and the result is
    deterministic: no RNG, ties to the inherited value.

WHAT THE CRITERION LEARNED (HALO-CHANNEL-2026-09-07 §3(b), 2026-09-07).
The test above is scored on the halo's labels, which are 4.3-4.8x EASIER
than the cargo the filter will price, and its bar moves with the label
count while the truth does not.  Three things follow, and the mechanism
of all three lives in :mod:`analyzer.walkeval`; this module only
dispatches.  W1: the per-label losses may be importance-weighted to the
target tile's own cargo (`choose(weights=...)`).  W3: an axis whose
candidates NEST — `channels`, and only `channels` — may be walked with
the burden of proof on the LEANER side (`choose(nested=...)`).  And W4,
which is not optional and not a knob: the REGULARISER left `AXIS_ORDER`
and became an inner minimisation under every candidate
(`choose(inner_axis=...)`), so no candidate is judged at another
candidate's ridge.  W2, the franchise, is `analyzer.patch`'s.

THE TIER RULE (B7 item b).  `patch_min_labels_per_state` was a label
COUNT — the kind of pin the ruling refuses.  Under `"auto"` it is
replaced by a statistical admission on the population's own cross-fit
numbers (:func:`admit`): a fitted tier is used only when its out-of-fold
error is significantly below the population's majority-class rate AND its
optimism (the cross-fit gap `e_oof - e_in`, the two numbers the ledger
already publishes as `patch_fit_error_*`) does not exceed the advantage
it actually bought.  Nothing in either clause comes from a sheet: the
tolerance is the population's own realised gain, and the multiple is the
`select_arm` multiple that already existed.  A tier that fails falls to
the next one, and in the end to the pooled `subtract` population.

WHAT IS NOT AUTO.  A knob that names WHAT IS BEING MEASURED rather than
how well it is measured — the unmix mode, the register arm, the train
scope, the self-training rounds, the fallback mode — is the operator's,
because a select-fold win would make the ledger's arm attribution a
statement about a different question.
"""

from __future__ import annotations

from dataclasses import dataclass, replace as dc_replace
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from holo.receiver.lib import pava, spectral
from holo.receiver.plugins import color_region_anchor as anchor

from . import calibrate as cal
from . import sample as sample_mod
from . import walkeval
from .patchcache import (FeatureBank, Moments, bounding_of, column_subset,
                         inside_mask, moments_of)
from .patchgrid import PatchError
from .types import Crops, Folds, KnownFrame, LaneFootprint, Read

#: The value that says "the run decides".  A knob bag carries it as the
#: string `"auto"` (the CLI's `--knob patch_channels=auto` is not JSON,
#: so it arrives as exactly this string).
AUTO: str = "auto"

#: Every knob name that accepts `AUTO`.  `spec_from_knobs` in
#: :mod:`analyzer.patch` reads them; the CLI needs no list of its own.
AUTO_KNOBS: tuple[str, ...] = (
    "patch_samples_per_cell", "patch_window_cells", "patch_channels",
    "patch_features", "patch_shrinkage", "patch_min_labels_per_state",
    "patch_min_labels_agnostic", "aperture_cells")

#: Samples per cell along each axis.  `patchgrid.grid_shape` caps a
#: candidate at the lane's own native pitch, so 16 IS "the native pitch
#: capped at 16" and collapses onto 8 on a lane that carries 8 px/cell —
#: a candidate that resolves onto another is dropped, never scored twice.
SAMPLES_CANDIDATES: tuple[int, ...] = (8, 16)
WINDOW_CANDIDATES: tuple[float, ...] = (1.0, 1.5, 2.0)
#: `r` and `rgb`, resolved — a candidate is the channel tuple itself so
#: the selector never has to know the knob's spelling.
CHANNEL_CANDIDATES: tuple[tuple[int, ...], ...] = ((0,), (0, 1, 2))
SHRINKAGE_CANDIDATES: tuple[float, ...] = (1e-3, 1e-2, 1e-1)
#: W4 (HALO-CHANNEL §3(a)): the ONE mechanical duty `labels_per_feature`
#: acquires.  The halo does NOT grow to afford a model — at a fixed model
#: the wide halo measured neutral-to-harmful at 4.3x the CPU, the best
#: cell in the matrix runs at 0.77 labels per parameter, and two halo
#: candidates have no common evaluation population to be paired on.  The
#: model is fitted to its budget through the REGULARISER instead, and a
#: candidate whose own `n_fit_rows / n_features` falls below 1.0 gets one
#: more rung upward, because that is the regime where the ridge is doing
#: the work of the missing rows.  No target, no veto: the run still
#: chooses, on its own search fold.
SHRINKAGE_UNDERDETERMINED_RUNG: float = 1.0
FEATURE_CANDIDATES: tuple[str, ...] = ("pixels", "rings")
#: A7's aperture widths, in cells.  0.7 is production's own
#: (`color_region_anchor.APERTURE_CELLS`) and therefore the inherited one.
APERTURE_CANDIDATES: tuple[float, ...] = (0.5, 0.7, 1.0)

#: The order the coordinate pass walks.  Geometry first (it moves the
#: features), then the reduction.  THE REGULARISER LEFT THIS LIST (W4,
#: HALO-CHANNEL §2.5/§3(a)): as the last stop of a coordinate pass the
#: channel axis was always judged at the INHERITED ridge and the ridge
#: was chosen afterwards for the channel set already fixed — and the
#: ledgers say the richer model asks for more ridge (at halo 48, 20 %
#: against 7 % on the three-ink state) only after it has already lost the
#: vote.  It is an INNER minimisation now: every candidate is scored at
#: the argmin over its own shrinkage ladder, so no candidate is judged at
#: another candidate's ridge (:func:`choose`'s `inner_axis`).
AXIS_ORDER: tuple[str, ...] = ("samples_per_cell", "window_cells",
                               "channels", "features")
#: The axis minimised INSIDE every candidate's evaluation.
INNER_AXIS: str = "shrinkage"
#: Every axis a run may hand this module, outer then inner — the
#: membership test for "is this knob walked at all", and the order the
#: ledger reads (`patchspec.walk_geometry`).
WALK_ORDER: tuple[str, ...] = AXIS_ORDER + (INNER_AXIS,)

CANDIDATES: dict[str, tuple] = {
    "samples_per_cell": SAMPLES_CANDIDATES,
    "window_cells": WINDOW_CANDIDATES,
    "channels": CHANNEL_CANDIDATES,
    "features": FEATURE_CANDIDATES,
    "shrinkage": SHRINKAGE_CANDIDATES}

#: Salts the fold seed for the cross-fit halves so they are independent
#: of the fit/search/select split (which uses the seed itself).
CROSSFIT_SALT: int = 0x57383143
#: A cross-fit half must hold at least this many labels of EACH class,
#: or the half's filter has no class-mean midpoint to threshold at.
MIN_PER_CLASS_PER_HALF: int = 2

#: The channel sets a `patch_channels` knob may name.
CHANNEL_SETS: dict[str, tuple[int, ...]] = {"r": (0,), "rgb": (0, 1, 2)}


def is_auto(value: Any) -> bool:
    """True when a knob value asks the run to decide."""
    return isinstance(value, str) and value.strip().lower() == AUTO


# ---------------------------------------------------- the discriminant
#
# Moved here from `analyzer.patch` (W8 B7) so the selector can fit a
# candidate without importing the module that dispatches into it; `patch`
# re-exports every name, so `patch.fit_discriminant`,
# `patch.crossfit_scores`, `patch.Discriminant`, `patch.CROSSFIT_SALT`
# and `patch.MIN_PER_CLASS_PER_HALF` are still the spelling.

DEFAULT_SHRINKAGE: float = 1e-2


@dataclass(frozen=True)
class Discriminant:
    """A standardised shrinkage-LDA: ``score = ((X-mu)/sd) @ w - thr``."""

    mu: np.ndarray
    sd: np.ndarray
    w: np.ndarray
    threshold: float
    n_0: int
    n_1: int
    #: The sd of the population's out-of-fold fit-fold scores (ruling 7 +
    #: the shared scale); 1.0 for a filter that was never cross-fitted.
    scale: float = 1.0


def fit_discriminant(X: np.ndarray, y: np.ndarray,
                     weights: np.ndarray | None = None, *,
                     shrinkage: float = DEFAULT_SHRINKAGE) -> Discriminant:
    """`analyze_selftrain.fit_lda`, verbatim.

    Weighted mean/sd standardisation (``sd + 1e-6``), targets ±1, solve
    ``((Xs*w).T @ Xs + lam*I) v = (Xs*w).T @ t``, threshold at the
    midpoint of the two weighted class-mean scores.
    """
    X = np.asarray(X, np.float64)
    y = np.asarray(y).astype(np.uint8)
    if X.ndim != 2 or X.shape[0] != y.size:
        raise PatchError(f"fit_discriminant: X {X.shape} vs y {y.shape}")
    wt = (np.ones(y.size, np.float64) if weights is None
          else np.asarray(weights, np.float64))
    if wt.size != y.size or np.any(wt < 0.0) or not np.any(wt > 0.0):
        raise PatchError("fit_discriminant: bad weights")
    wt = wt / wt.sum()
    n_1 = int(np.count_nonzero(y == 1))
    n_0 = int(y.size - n_1)
    if n_0 == 0 or n_1 == 0:
        raise PatchError("fit_discriminant: one class is empty")
    mu = (wt[:, None] * X).sum(axis=0)
    Xs = X - mu
    sd = np.sqrt((wt[:, None] * Xs ** 2).sum(axis=0)) + 1e-6
    Xs = Xs / sd
    t = np.where(y == 1, 1.0, -1.0)
    weighted = Xs * wt[:, None]
    A = weighted.T @ Xs + float(shrinkage) * np.eye(X.shape[1])
    w = np.linalg.solve(A, weighted.T @ t)
    s = Xs @ w
    w1 = wt * (y == 1)
    w0 = wt * (y == 0)
    threshold = 0.5 * ((w1 * s).sum() / w1.sum() + (w0 * s).sum() / w0.sum())
    for array in (mu, sd, w):
        array.setflags(write=False)
    return Discriminant(mu=mu, sd=sd, w=w, threshold=float(threshold),
                        n_0=n_0, n_1=n_1, scale=1.0)


def apply_discriminant(X: np.ndarray, d: Discriminant) -> np.ndarray:
    """``(((X - mu) / sd) @ w - threshold) / scale``; high = ink."""
    X = np.asarray(X, np.float64)
    return (((X - d.mu) / d.sd) @ d.w - d.threshold) / float(d.scale)


def crossfit_scores(X: np.ndarray, y: np.ndarray,
                    weights: np.ndarray | None, half: np.ndarray, *,
                    shrinkage: float = DEFAULT_SHRINKAGE,
                    always: np.ndarray | None = None,
                    ) -> tuple[np.ndarray, Discriminant]:
    """Out-of-fold scores on every training row, plus the FULL fit.

    `half` is True for half A, False for half B; the filter fitted on A
    scores B and the one fitted on B scores A.  Rows flagged `always`
    (pseudo labels, B3/B4) join BOTH half fits and the full fit and take
    the full fit's score — they never leave the training set, so they
    have no out-of-fold score to give.  The full fit's `scale` is the sd
    of the out-of-fold scores of the halved rows, and the returned scores
    are already divided by it.  Refuses (`PatchError`) a half that lacks
    `MIN_PER_CLASS_PER_HALF` labels of either class.
    """
    X = np.asarray(X, np.float64)
    y = np.asarray(y).astype(np.uint8)
    half = np.asarray(half, bool)
    always = (np.zeros(y.size, bool) if always is None
              else np.asarray(always, bool))
    wt = (np.ones(y.size, np.float64) if weights is None
          else np.asarray(weights, np.float64))
    part_a = half & ~always
    part_b = ~half & ~always
    for name, part in (("A", part_a), ("B", part_b)):
        labels = y[part]
        n_1 = int(np.count_nonzero(labels == 1))
        n_0 = int(labels.size - n_1)
        if min(n_0, n_1) < MIN_PER_CLASS_PER_HALF:
            raise PatchError(f"crossfit: half {name} holds {n_0}/{n_1} "
                             f"labels per class")
    oof = np.full(y.size, np.nan, np.float64)
    fit_a = fit_discriminant(X[part_a | always], y[part_a | always],
                             wt[part_a | always], shrinkage=shrinkage)
    oof[part_b] = apply_discriminant(X[part_b], fit_a)
    fit_b = fit_discriminant(X[part_b | always], y[part_b | always],
                             wt[part_b | always], shrinkage=shrinkage)
    oof[part_a] = apply_discriminant(X[part_a], fit_b)
    full = fit_discriminant(X, y, wt, shrinkage=shrinkage)
    halved = oof[~always]
    scale = float(np.std(halved)) if halved.size > 1 else 1.0
    if not np.isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    full = dc_replace(full, scale=scale)
    oof[always] = apply_discriminant(X[always], full)
    oof[~always] = halved / scale
    return oof, full


# --------------------------------------------------- the select-fold test

def select_losses(train_scores: np.ndarray, train_labels: np.ndarray,
                  eval_scores: np.ndarray, eval_labels: np.ndarray,
                  ) -> np.ndarray | None:
    """Per-label held-out log losses of one candidate, or None.

    (The name is `select_losses` because this is `select_arm`'s
    arithmetic; the FOLD it is handed is the caller's — every walk in
    this module hands it the SEARCH fold, review 2026-09-06.)

    `calibrate.fold_logloss`'s arithmetic, kept per label instead of
    averaged so two candidates can be compared PAIRED (the mean of a
    candidate's own losses over its own rows is a mean over different
    cells; `select_arm` pairs for the same reason).  `train_scores` must
    be the candidate's OUT-OF-FOLD scores on the fit fold — a PAVA map
    fitted on in-sample scores is a map of the filter's optimism.

    None below `pava.CAL_MIN_PER_CLASS` on the training side or
    `pava.CAL_MIN_HELDOUT` held-out labels: a refusal, never a
    fabricated number.
    """
    train_scores = np.asarray(train_scores, np.float64)
    eval_scores = np.asarray(eval_scores, np.float64)
    train_labels = np.asarray(train_labels, np.float64)
    eval_labels = np.asarray(eval_labels, np.float64)
    good_train = np.isfinite(train_scores)
    good_eval = np.isfinite(eval_scores)
    train_scores, train_labels = (train_scores[good_train],
                                  train_labels[good_train])
    eval_scores, eval_labels = eval_scores[good_eval], eval_labels[good_eval]
    n_1 = int(np.count_nonzero(train_labels == 1.0))
    if min(n_1, int(train_labels.size - n_1)) < pava.CAL_MIN_PER_CLASS:
        return None
    if int(eval_labels.size) < pava.CAL_MIN_HELDOUT:
        return None
    # one standardisation over both sides, exactly as `fold_logloss`
    # standardises the whole score vector before splitting it
    both = cal._standardise(np.concatenate((train_scores, eval_scores)))
    knots, probs = cal._pava_map(both[:train_scores.size], train_labels)
    llr = pava.calibration_llr(np.asarray(both[train_scores.size:],
                                          np.float32), knots, probs)
    return cal._per_label_loss(np.asarray(llr, np.float64), eval_labels)


def crossfit_losses(scores: np.ndarray, labels: np.ndarray,
                    half: np.ndarray) -> np.ndarray | None:
    """Per-label log losses of one score over its OWN labelled rows.

    The rows carry out-of-fold scores (the filter that scored a row was
    not fitted on it), but a PAVA map fitted on all of them and priced on
    all of them would be in-sample for the MAP.  So the map is cross-fit
    on the same halves the filter used: half A's map prices half B and
    vice versa.  Returns one loss per row, or None when either half is
    below `pava`'s floors — a refusal, never a fabricated number.
    """
    scores = np.asarray(scores, np.float64)
    labels = np.asarray(labels, np.float64)
    half = np.asarray(half, bool)
    good = np.isfinite(scores)
    out = np.full(labels.size, np.nan, np.float64)
    for train, evaluate in ((half & good, ~half & good),
                            (~half & good, half & good)):
        got = select_losses(scores[train], labels[train],
                            scores[evaluate], labels[evaluate])
        if got is None or got.size != int(np.count_nonzero(evaluate)):
            return None
        out[evaluate] = got
    return out if np.all(np.isfinite(out[good])) else None


def paired_verdict(base: np.ndarray, candidate: np.ndarray) -> dict:
    """`select_arm`'s paired test, over one population's held-out labels.

    ONE spelling, in :mod:`analyzer.walkeval`, which is the same
    arithmetic with two additions the walk needs — importance weights and
    a direction (HALO-CHANNEL §4.1).  Unweighted and adopt-if-better it
    is bit-identical to what this function computed before, which a test
    pins; every caller that wants the plain test keeps calling it here.
    """
    return walkeval.paired_verdict(base, candidate, weights=None,
                                   direction=walkeval.DIRECTION_ADOPT)


def minority_ok(labels: np.ndarray) -> bool:
    """`SELECT_MIN_MINORITY` on the population's own held-out labels.

    NOT `select_arm`'s discriminating-label count: inside one sibling
    state every discriminating label carries the same target bit (B2's
    finding), so that count is degenerate here.  The honest floor within
    a state is the smaller class of the state's own labels.
    """
    labels = np.asarray(labels, np.uint8)
    ones = int(np.count_nonzero(labels == 1))
    return min(ones, int(labels.size - ones)) >= cal.SELECT_MIN_MINORITY


def axis_label(axis: str, value: Any) -> str:
    """A short, JSON-safe key for one candidate — the ledger reads it."""
    if isinstance(value, float):
        return f"{axis}={value:g}"
    if isinstance(value, (tuple, list)):
        return f"{axis}=" + "".join(str(int(item)) for item in value)
    return f"{axis}={value}"


def choose(inherited: Mapping[str, Any], candidates: Mapping[str, Sequence],
           evaluate: Callable[[dict], np.ndarray | None], *,
           order: Sequence[str] = AXIS_ORDER,
           weights: np.ndarray | None = None,
           verdict: Callable[..., dict] | None = None,
           nested: Mapping[str, Sequence] | None = None,
           inner_axis: str | None = None,
           inner_candidates: Any = None) -> tuple[dict, dict, dict]:
    """One deterministic coordinate pass over the auto axes.

    `evaluate(axes)` returns that candidate's per-label SEARCH-fold
    losses (or None when it refuses).  Returns ``(axes, losses,
    detail)``: the chosen axes (the inherited ones where nothing won),
    a small ``{label: mean loss or None}`` dict for the ledger, and the
    bookkeeping (`baseline_logloss`, `refused`, `n_evaluated`, `adopted`,
    `verdicts`, `inner`).

    Ties lose: a candidate is adopted only when its paired mean gain
    clears `SELECT_SE_MULTIPLE` standard errors, so an undiscriminating
    search fold leaves every axis where it was.

    THREE THINGS THE CALLER MAY ASK FOR (HALO-CHANNEL §4.2).  With none
    of them this function is what it was, to the bit.

    * `weights` — per-label importance weights (W1), passed straight
      through to `verdict`.  They multiply losses; they choose no row and
      restrict no hypothesis.
    * `nested` — axes whose candidates are ordered by RICHNESS and NEST
      (`{"channels": ((0,), (0, 1, 2))}`, and only that one: `red` is
      literally `rgb`'s first 144 columns).  Such an axis is climbed from
      the leanest incumbent upward under
      `walkeval.DIRECTION_KEEP` — the richer rung is taken unless the
      leaner one clears the bar — because the loss here is one-sided:
      under-richness cost 13-19 certificates on the matrix that argues
      for it and over-richness cost 0, and a richer filter cannot mint a
      wrong certificate (the gate decides that).  Every other axis keeps
      ties-to-inherited.
    * `inner_axis` / `inner_candidates` — the axis minimised INSIDE every
      candidate's evaluation (W4, the regulariser).  `inner_candidates`
      is a ladder or a callable taking the candidate's axes, so a
      candidate that is underdetermined at its OWN width can be handed
      one more rung.  The optimism this introduces is equal in COUNT
      across candidates (every one of them is a minimum over the same
      ladder length, or over one rung more exactly when its own
      `n_fit_rows / n_features` says so), it stays on the search fold,
      and the losses the ledger records are the minima.
    """
    verdict_of = walkeval.paired_verdict if verdict is None else verdict
    nested = dict(nested or {})
    current = dict(inherited)
    losses: dict[str, Any] = {}
    detail: dict[str, Any] = {"refused": None, "n_evaluated": 0,
                              "adopted": {}, "verdicts": {}, "inner": {},
                              "loss_population": walkeval.loss_population(
                                  weights)}

    def mean_loss(got: np.ndarray) -> float:
        """THE DECISION LOSS — the population the verdict is taken on.

        2026-09-07 review: this used to be the plain halo mean
        everywhere, so under W1 the inner ridge was minimised, and
        `losses`/`baseline_logloss` were published, on exactly the
        population the weighting exists to reject while the outer paired
        verdict used the weights.  One quantity now, named in
        `detail["loss_population"]`; with `weights=None` it is
        `np.mean` to the bit.
        """
        return walkeval.weighted_mean(got, weights)

    def score(axes: Mapping[str, Any]) -> tuple[np.ndarray | None, Any]:
        """One candidate's losses, at the argmin over its inner ladder."""
        if inner_axis is None:
            got = evaluate(dict(axes))
            detail["n_evaluated"] += 1
            return got, None
        ladder = (inner_candidates(axes) if callable(inner_candidates)
                  else tuple(inner_candidates or ()))
        best_value: Any = None
        best_got: np.ndarray | None = None
        best_mean: float | None = None
        for value in _inner_order(ladder, axes.get(inner_axis)):
            trial = dict(axes)
            trial[inner_axis] = value
            got = evaluate(trial)
            detail["n_evaluated"] += 1
            if got is None:
                continue
            mean = mean_loss(got)
            #: strict, and the incumbent rung goes first: a tie keeps the
            #: ridge the population already had
            if best_mean is None or mean < best_mean:
                best_value, best_got, best_mean = value, got, mean
        return best_got, best_value

    base, inner_value = score(current)
    if base is None:
        detail["refused"] = "no_baseline"
        return current, losses, detail
    if inner_axis is not None and inner_value is not None:
        current[inner_axis] = inner_value
        detail["inner"]["inherited"] = axis_label(inner_axis, inner_value)
    losses["inherited"] = mean_loss(base)
    detail["baseline_logloss"] = mean_loss(base)
    for axis in order:
        if axis in nested:
            base = _climb(axis, tuple(nested[axis]), current, base, score,
                          losses, detail, weights, verdict_of, inner_axis,
                          mean_loss)
            continue
        options = tuple(candidates.get(axis) or ())
        best_value: Any = None
        best_losses: np.ndarray | None = None
        best_inner: Any = None
        best_gain = 0.0
        seen = {_value_key(current[axis])}
        for value in options:
            if _value_key(value) in seen:
                continue
            seen.add(_value_key(value))
            trial = dict(current)
            trial[axis] = value
            got, got_inner = score(trial)
            label = axis_label(axis, value)
            if got is None:
                losses[label] = None
                continue
            losses[label] = mean_loss(got)
            got_verdict = verdict_of(base, got, weights=weights,
                                     direction=walkeval.DIRECTION_ADOPT)
            detail["verdicts"][label] = got_verdict
            if (got_verdict["adopted"]
                    and got_verdict["mean_difference"] > best_gain):
                best_gain = float(got_verdict["mean_difference"])
                best_value, best_losses, best_inner = value, got, got_inner
        if best_value is not None and best_losses is not None:
            current[axis] = best_value
            base = best_losses
            if inner_axis is not None and best_inner is not None:
                current[inner_axis] = best_inner
                detail["inner"][axis_label(axis, best_value)] = axis_label(
                    inner_axis, best_inner)
            detail["adopted"][axis] = axis_label(axis, best_value)
            detail["baseline_logloss"] = mean_loss(base)
    return current, losses, detail


def _climb(axis: str, ladder: Sequence[Any], current: dict,
           base: np.ndarray, score: Callable[[Mapping[str, Any]],
                                             tuple[np.ndarray | None, Any]],
           losses: dict, detail: dict, weights: np.ndarray | None,
           verdict_of: Callable[..., dict], inner_axis: str | None,
           mean_loss: Callable[[np.ndarray], float]) -> np.ndarray:
    """W3: climb a NESTED axis from the incumbent upward, richest last.

    The rung is taken unless the leaner side wins by the margin, and the
    climb stops at the first rung the leaner side holds — the candidates
    nest, so the ladder is ordered and there is nothing above a rung the
    evidence already refused.  `current` is mutated in place and the new
    running baseline is returned.
    """
    keys = [_value_key(value) for value in ladder]
    here = _value_key(current[axis])
    start = keys.index(here) + 1 if here in keys else 0
    for value in tuple(ladder)[start:]:
        trial = dict(current)
        trial[axis] = value
        got, got_inner = score(trial)
        label = axis_label(axis, value)
        if got is None:
            losses[label] = None
            continue
        losses[label] = mean_loss(got)
        got_verdict = verdict_of(base, got, weights=weights,
                                 direction=walkeval.DIRECTION_KEEP)
        detail["verdicts"][label] = got_verdict
        if not got_verdict["adopted"]:
            break
        current[axis] = value
        base = got
        if inner_axis is not None and got_inner is not None:
            current[inner_axis] = got_inner
            detail["inner"][label] = axis_label(inner_axis, got_inner)
        detail["adopted"][axis] = label
        detail["baseline_logloss"] = mean_loss(base)
    return base


def _inner_order(ladder: Sequence[Any], incumbent: Any) -> list[Any]:
    """The inner ladder with the incumbent FIRST, de-duplicated."""
    out: list[Any] = []
    seen: set[Any] = set()
    for value in ([incumbent] if incumbent is not None else []) + list(ladder):
        key = _value_key(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def shrinkage_ladder(n_fit_rows: int, n_features: int, *,
                     candidates: Sequence[float] = SHRINKAGE_CANDIDATES,
                     ) -> tuple[float, ...]:
    """W4's ladder: one rung more when the candidate is underdetermined.

    `labels_per_feature` stays a published DIAGNOSTIC with no target and
    no veto (HALO-CHANNEL §3(a)); this is the one thing it decides.
    """
    ladder = tuple(float(value) for value in candidates)
    if int(n_features) > 0 and (float(n_fit_rows) / float(n_features)) < 1.0:
        ladder = ladder + (float(SHRINKAGE_UNDERDETERMINED_RUNG),)
    return ladder


def _value_key(value: Any) -> Any:
    if isinstance(value, (tuple, list)):
        return tuple(int(item) for item in value)
    if isinstance(value, float):
        return round(float(value), 12)
    return value


# ------------------------------------------------- the admission rule (b)

def admit(insample_wrong: np.ndarray, crossfit_wrong: np.ndarray,
          labels: np.ndarray, *, own_losses: np.ndarray | None = None,
          alternative_losses: np.ndarray | None = None,
          ) -> tuple[bool, dict]:
    """Is a fitted tier worth using?  Its OWN cross-fit numbers decide.

    Three clauses, none of them a number carried in from a sheet:

    * USEFUL — the out-of-fold error must be below the population's own
      majority-class rate by more than `calibrate.SELECT_SE_MULTIPLE`
      binomial standard errors.  A filter that cannot beat "guess the
      commoner class" out of fold is not a filter.
    * GENERALISES — the optimism (`e_oof - e_in`, the cross-fit GAP the
      ledger already publishes as `patch_fit_error_*`) must not exceed
      the advantage the filter actually bought (`p_majority - e_oof`).
      The tolerance is the population's own realised gain, so a tier
      whose fit is mostly memory is refused however many labels it had.
    * DOES NOT READ WORSE THAN WHAT IT DISPLACES — when the caller offers
      the two per-label loss vectors (`own_losses`, `alternative_losses`,
      both from :func:`crossfit_losses` over the same rows), the tier is
      refused if the ALTERNATIVE wins the module's own paired test
      against it.  ADDED 2026-09-06 (review): the two clauses above
      compare a filter to MAJORITY-CLASS GUESSING, which a filter worse
      than the plain `subtract` score can clear — and then it takes those
      cells anyway, because the tier ladder gives a fitted tier its cells
      before the next one ever sees them.  The test runs in THAT
      direction on purpose: the tier is the arm's own mechanism and keeps
      every tie, exactly as `select_arm`'s pinned default does; the
      alternative has to prove HARM (a mean gain over
      `SELECT_SE_MULTIPLE` standard errors), and `select_arm` still
      arbitrates the whole arm against `subtract+offset` afterwards.  The
      comparison is refused, not failed, when either side is below
      `pava`'s floors, and then the two clauses above decide alone.

    Returns ``(admitted, detail)``; the detail is a handful of floats and
    a reason, and it is what the ledger shows for a refused tier.
    """
    insample_wrong = np.asarray(insample_wrong, bool)
    crossfit_wrong = np.asarray(crossfit_wrong, bool)
    labels = np.asarray(labels, np.uint8)
    n = int(labels.size)
    n_1 = int(np.count_nonzero(labels == 1))
    n_0 = n - n_1
    detail: dict[str, Any] = {"n": n, "reason": None}
    if n < pava.CAL_MIN_HELDOUT or min(n_0, n_1) < MIN_PER_CLASS_PER_HALF:
        detail["reason"] = "too_few_crossfit_labels"
        return False, detail
    p_majority = max(n_0, n_1) / n
    e_in = float(np.count_nonzero(insample_wrong)) / n
    e_oof = float(np.count_nonzero(crossfit_wrong)) / n
    # a half-count continuity floor so a perfect out-of-fold filter still
    # has a standard error to be tested against (not a tuning: 0.5/n is
    # the smallest error the sample can express)
    se = max(float(np.sqrt(max(e_oof * (1.0 - e_oof), 0.0) / n)), 0.5 / n)
    gain = p_majority - e_oof
    gap = e_oof - e_in
    detail.update({"error_insample": e_in, "error_crossfit": e_oof,
                   "majority_rate": float(p_majority), "gain": float(gain),
                   "gap": float(gap), "standard_error": float(se)})
    if not gain > cal.SELECT_SE_MULTIPLE * se:
        detail["reason"] = "crossfit_no_better_than_majority"
        return False, detail
    if gap > gain:
        detail["reason"] = "optimism_exceeds_the_gain"
        return False, detail
    if own_losses is None or alternative_losses is None:
        detail["comparison"] = "not_offered"
        detail["reason"] = "admitted"
        return True, detail
    own = np.asarray(own_losses, np.float64)
    other = np.asarray(alternative_losses, np.float64)
    keep = np.isfinite(own) & np.isfinite(other)
    # base = the TIER, candidate = the alternative: `adopted` therefore
    # means "the score these cells would otherwise carry is better than
    # this tier by more than the margin", which is the refusal
    verdict = paired_verdict(own[keep], other[keep])
    detail.update({
        "comparison": "paired_against_the_alternative",
        "comparison_n": int(np.count_nonzero(keep)),
        "alternative_gain": float(verdict["mean_difference"]),
        "alternative_se": float(verdict["standard_error"]),
        "alternative_logloss": verdict.get("select_logloss")})
    if verdict.get("reason") == "too_few_paired_labels":
        detail["comparison"] = "refused:too_few_paired_labels"
        detail["reason"] = "admitted"
        return True, detail
    if verdict["adopted"]:
        detail["reason"] = "worse_than_the_alternative"
        return False, detail
    detail["reason"] = "admitted"
    return True, detail


# ------------------------------------------- the normal-equation fits
#
# W8 B8.  `fit_discriminant` above is the MEASUREMENT's recipe and stays
# the reference (a test pins it line by line against
# `measure/c-third-layer-20260906/analyze_selftrain.py`).  Everything it
# computes is a function of the weighted moments, so the same fit can be
# read off `patchcache.Moments` — which ADD over disjoint row sets and
# SLICE over feature subsets.  That is what makes the self-discovery walk
# affordable: one `gemm` per (population, cross-fit half) at the widest
# candidate geometry prices every window, every channel subset, both
# feature kinds and every shrinkage, and the cross-fit's third fit
# (A u B) is an addition instead of a third build.


def fit_from_moments(moments: Moments, *,
                     shrinkage: float = DEFAULT_SHRINKAGE) -> Discriminant:
    """`fit_discriminant` from sufficient statistics — same fit.

    Exact in exact arithmetic: `mu = S1/S0`, `sd = sqrt(G/S0 - mu mu) +
    1e-6`, the ridge system is `D^-1 (G/S0 - mu mu^T) D^-1 + lam I`, the
    right-hand side is `D^-1 (E[t x] - mu E[t])` with `t = 2y - 1`, and
    the threshold is the midpoint of the two class-mean scores, each of
    which is `((S1_c/S0_c - mu)/sd) . v`.  In floating point the
    difference from the raw-row path is the usual one-digit loss of a
    moment-form variance; the features are pixel values in [0, 1], so a
    test pins the two fits to agree to 1e-8.
    """
    total = float(moments.s0)
    if not total > 0.0:
        raise PatchError("fit_from_moments: no weight")
    n_1 = int(moments.n_1)
    n_0 = int(moments.n) - n_1
    s0_1 = float(moments.s0_1)
    s0_0 = total - s0_1
    if n_0 == 0 or n_1 == 0 or not s0_1 > 0.0 or not s0_0 > 0.0:
        raise PatchError("fit_from_moments: one class is empty")
    mu = np.asarray(moments.s1, np.float64) / total
    second = np.asarray(moments.gram, np.float64) / total
    centred = second - np.outer(mu, mu)
    sd = np.sqrt(np.maximum(np.diag(centred), 0.0)) + 1e-6
    A = centred / sd[:, None] / sd[None, :]
    A[np.diag_indices_from(A)] += float(shrinkage)
    mean_1 = np.asarray(moments.s1_1, np.float64) / s0_1
    mean_0 = (np.asarray(moments.s1, np.float64)
              - np.asarray(moments.s1_1, np.float64)) / s0_0
    # E[t x] - mu E[t] with t = 2y - 1
    rhs = ((2.0 * np.asarray(moments.s1_1, np.float64)
            - np.asarray(moments.s1, np.float64)) / total
           - mu * ((2.0 * s0_1 - total) / total)) / sd
    w = np.linalg.solve(A, rhs)
    threshold = 0.5 * (float(((mean_1 - mu) / sd) @ w)
                       + float(((mean_0 - mu) / sd) @ w))
    mu.setflags(write=False)
    sd.setflags(write=False)
    w.setflags(write=False)
    return Discriminant(mu=mu, sd=sd, w=w, threshold=float(threshold),
                        n_0=n_0, n_1=n_1, scale=1.0)


def crossfit_selection(bank: FeatureBank, axes: Mapping[str, Any],
                       token: Any, positions: np.ndarray,
                       labels: np.ndarray, half: np.ndarray, *,
                       shrinkage: float = DEFAULT_SHRINKAGE,
                       ) -> tuple[np.ndarray, Discriminant]:
    """`crossfit_scores` over a bank's selection block, from moments.

    Same contract, same refusals, same `scale`: the filter fitted on
    half A scores half B and vice versa, the full fit is A + B, and the
    returned scores are divided by the sd of the out-of-fold ones.  What
    differs is the arithmetic path — two cached, sliceable Gram builds
    per (population, half) instead of three per candidate.
    """
    positions = np.asarray(positions, np.int64)
    labels = np.asarray(labels).astype(np.uint8)
    half = np.asarray(half, bool)
    parts = {"A": half, "B": ~half}
    for name, part in parts.items():
        mine = labels[part]
        n_1 = int(np.count_nonzero(mine == 1))
        n_0 = int(mine.size - n_1)
        if min(n_0, n_1) < MIN_PER_CLASS_PER_HALF:
            raise PatchError(f"crossfit: half {name} holds {n_0}/{n_1} "
                             f"labels per class")
    moments = {name: bank.selection_moments(
        axes, (token, name), positions[part], labels[part])
        for name, part in parts.items()}
    fit_a = fit_from_moments(moments["A"], shrinkage=shrinkage)
    fit_b = fit_from_moments(moments["B"], shrinkage=shrinkage)
    full = fit_from_moments(moments["A"] + moments["B"], shrinkage=shrinkage)
    block, _inside = bank.selection(axes)
    oof = np.empty(labels.size, np.float64)
    oof[parts["B"]] = apply_discriminant(
        np.asarray(block[positions[parts["B"]]], np.float64), fit_a)
    oof[parts["A"]] = apply_discriminant(
        np.asarray(block[positions[parts["A"]]], np.float64), fit_b)
    scale = float(np.std(oof)) if oof.size > 1 else 1.0
    if not np.isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    return oof / scale, dc_replace(full, scale=scale)


def bounding_axes(inherited: Mapping[str, Any],
                  auto: Sequence[str]) -> dict:
    """The most restrictive candidate geometry, for ONE `inside` mask.

    Every candidate must be trained and scored on the SAME rows or the
    paired test is not paired, so the row set is fixed by the geometry
    that reaches furthest from the cell centre — the widest window at the
    finest sampling.  With nothing auto this is the inherited geometry
    itself, so a run that names its knobs reads exactly what it read
    before.
    """
    axes = dict(inherited)
    if "window_cells" in auto:
        axes["window_cells"] = max(float(axes["window_cells"]),
                                   max(WINDOW_CANDIDATES))
    if "samples_per_cell" in auto:
        axes["samples_per_cell"] = max(int(axes["samples_per_cell"]),
                                       max(SAMPLES_CANDIDATES))
    return axes


# ------------------------------------------------------- A7, the aperture

def aperture_scores(crops: Crops, lfp: LaneFootprint, read: Read,
                    frame: KnownFrame, plane: int,
                    mix: spectral.PlaneMix, *, aperture_cells: float,
                    fallback_mode: str = spectral.MODE_SUBTRACT,
                    ) -> np.ndarray:
    """The box-mean plane score read through ONE candidate aperture.

    `sample.refiltered_values` re-filters the crop the arm already opened
    and re-reads it at the read's own posed points, so a candidate is
    evaluated on ITS OWN filtered crop and nothing else moves.  The
    `PlaneMix` is the one the arm fitted at the crop's aperture and is
    NOT refitted per candidate: a wider box shifts every channel's level
    together, which `calibrate`'s standardisation removes anyway, and a
    refit would need the whole lane's read again.  Stated, not hidden.
    """
    values = sample_mod.refiltered_values(
        crops, lfp, read, aperture_cells=float(aperture_cells))
    return np.asarray(spectral.plane_score(
        mix, values, frame.bits, frame.known, plane, fallback_mode),
        np.float64)


def choose_aperture(crops: Crops, lfp: LaneFootprint, read: Read,
                    frame: KnownFrame, plane: int, mix: spectral.PlaneMix,
                    folds: Folds, *, usable: np.ndarray,
                    fallback_mode: str = spectral.MODE_SUBTRACT,
                    candidates: Sequence[float] = APERTURE_CANDIDATES,
                    ) -> tuple[float, np.ndarray, dict, dict]:
    """Pick the sampling aperture on the search fold; A7, self-discovered.

    The inherited value is the aperture the crop was OPENED at (production's
    0.7 box unless the operator asked for another), and it wins every tie.
    Returns ``(aperture_cells, values_rgb, losses, detail)`` — the values
    are the read at the CHOSEN aperture, `read.values_rgb` itself when the
    inherited one wins, so the caller never re-derives them.
    """
    inherited = float(crops.aperture_cells)
    values_rgb = np.asarray(read.values_rgb, np.float64)
    labels_all = (np.asarray(frame.known[:, plane], bool)
                  & np.asarray(usable, bool))
    fit_rows = np.flatnonzero(labels_all & np.asarray(folds.fit, bool))
    #: the SEARCH fold, like every other within-arm search (review
    #: 2026-09-06): the select fold is what `select_arm` and the lane
    #: weights are decided on and no walk here may minimise it.
    walk_rows = np.flatnonzero(labels_all & np.asarray(folds.search, bool))
    values = np.asarray(frame.bits[:, plane], np.uint8)
    detail: dict[str, Any] = {"inherited": inherited, "refused": None,
                              "walk_fold": "search"}
    if str(crops.aperture_kind) != "box" or crops.raw_rgb is None:
        detail["refused"] = "aperture_not_a_box_crop"
        return inherited, values_rgb, {}, detail
    if not minority_ok(values[walk_rows]):
        detail["refused"] = "below_minority_floor"
        return inherited, values_rgb, {}, detail

    def evaluate(axes: Mapping[str, Any]) -> np.ndarray | None:
        score = aperture_scores(crops, lfp, read, frame, plane, mix,
                                aperture_cells=float(axes["aperture_cells"]),
                                fallback_mode=fallback_mode)
        return select_losses(score[fit_rows], values[fit_rows],
                             score[walk_rows], values[walk_rows])

    axes, losses, walk = choose({"aperture_cells": inherited},
                                {"aperture_cells": tuple(candidates)},
                                evaluate, order=("aperture_cells",))
    detail.update(walk)
    chosen = float(axes["aperture_cells"])
    if chosen != inherited:
        values_rgb = sample_mod.refiltered_values(crops, lfp, read,
                                                  aperture_cells=chosen)
    return chosen, values_rgb, losses, detail


__all__ = [
    "AUTO", "AUTO_KNOBS", "APERTURE_CANDIDATES", "AXIS_ORDER",
    "CANDIDATES", "CHANNEL_CANDIDATES", "CHANNEL_SETS", "CROSSFIT_SALT",
    "DEFAULT_SHRINKAGE", "Discriminant", "FEATURE_CANDIDATES",
    "FeatureBank", "INNER_AXIS", "MIN_PER_CLASS_PER_HALF", "Moments",
    "SAMPLES_CANDIDATES", "SHRINKAGE_CANDIDATES",
    "SHRINKAGE_UNDERDETERMINED_RUNG", "WALK_ORDER", "WINDOW_CANDIDATES",
    "admit", "apply_discriminant", "aperture_scores", "axis_label",
    "bounding_axes", "bounding_of", "choose", "choose_aperture",
    "column_subset", "crossfit_losses", "crossfit_scores",
    "crossfit_selection",
    "fit_discriminant", "fit_from_moments", "inside_mask", "is_auto",
    "minority_ok", "moments_of", "paired_verdict", "select_losses",
    "shrinkage_ladder",
]

# `anchor` is imported for the production aperture constant the
# candidate set is named against; keeping the reference explicit tells
# the reader where 0.7 comes from.
PRODUCTION_APERTURE_CELLS: float = float(anchor.APERTURE_CELLS)

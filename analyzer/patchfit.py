"""The patch family's POPULATIONS — how a set of cells is priced (W8 B7).

BLIND, and free of every analyzer module but :mod:`analyzer.autoknobs`
(the discriminant) and :mod:`analyzer.patchgrid` (the error type):
`analyzer.patch` grew past DESIGN §0.4's 1000-line cap when the
self-discovery selector landed, so the three things it does to a
POPULATION of cells moved here, UNCHANGED — this file is a move, not a
rewrite, and the tests that pinned them still pin them through
`analyzer.patch`'s re-export —

* :func:`fit_population` — one population's cross-fitted discriminant,
  with P1g's neighbourhood rows, B4's decoder rows and P2's
  self-training, on the shared scale (`analyzer.patch`'s module
  docstring is the contract; this is its implementation);
* :func:`fallback_population` — the `subtract` score, centred and scaled
  so it can share one pooled PAVA map with a fitted tier;
* :func:`mixture_score` — M1's label-free two-Gaussian segmentation.

`analyzer.patch` imports every public name here, so `patch.mixture_score`
stays the spelling for every caller and every test.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from typing import Any

import numpy as np

from .autoknobs import apply_discriminant, crossfit_scores
from .patchgrid import PatchError

__all__ = ["MIXTURE_INIT_PERCENTILES", "MIXTURE_MIN_CELLS", "MIXTURE_STATE",
           "MIXTURE_STEPS", "fallback_population", "fit_population",
           "mixture_score", "sd_or_one"]

#: M1: the two-Gaussian mixture refuses a population under this many
#: cells (a segmentation of 40 points is noise, not a segmentation).
MIXTURE_MIN_CELLS: int = 100
#: M1's deterministic init and step count (MEAS §4's recipe).
MIXTURE_INIT_PERCENTILES: tuple[float, float] = (30.0, 70.0)
MIXTURE_STEPS: int = 20
#: The sibling state the mixture serves: both siblings inked (MEAS §1's
#: 2-4x worse population, the only one it helped).
MIXTURE_STATE: int = 3


# ------------------------------------------------------- M1, the mixture

def mixture_score(values: np.ndarray, *, steps: int = MIXTURE_STEPS,
                  ) -> tuple[np.ndarray, dict]:
    """Two-Gaussian EM on one channel; high = INK, scaled by its own sd.

    NO LABELS (MEAS §4's blind mixture): the population is segmented into
    a dark component and a light one, initialised at the 30th and 70th
    percentiles with the population's own variance, run for `steps`
    fixed EM steps, and the score is the log-ratio ``log p_dark - log
    p_light``.  DARK IS INK — every plane's presence is a deficit in its
    own channel (PLAN §1.3's ink-dark convention), so the low-mean
    component is the inked one and the sign needs no label to fix.
    Deterministic: percentile init, a fixed step count, no RNG.
    """
    values = np.asarray(values, np.float64).reshape(-1)
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        raise PatchError("mixture: fewer than two finite values")
    low, high = np.percentile(finite, list(MIXTURE_INIT_PERCENTILES))
    var = max(float(np.var(finite)), 1e-12)
    mu = np.array((float(low), float(high)), np.float64)
    sigma2 = np.array((var, var), np.float64)
    weight = np.array((0.5, 0.5), np.float64)
    for _ in range(int(steps)):
        density = (weight[None, :]
                   / np.sqrt(2.0 * np.pi * sigma2[None, :])
                   * np.exp(-0.5 * (finite[:, None] - mu[None, :]) ** 2
                            / sigma2[None, :]))
        total = density.sum(axis=1)
        total = np.where(total > 1e-300, total, 1e-300)
        resp = density / total[:, None]
        mass = resp.sum(axis=0)
        mass = np.where(mass > 1e-12, mass, 1e-12)
        mu = (resp * finite[:, None]).sum(axis=0) / mass
        sigma2 = np.maximum(
            (resp * (finite[:, None] - mu[None, :]) ** 2).sum(axis=0) / mass,
            1e-12)
        weight = mass / float(finite.size)
    dark = int(np.argmin(mu))
    light = 1 - dark
    def _log_density(x: np.ndarray, index: int) -> np.ndarray:
        return (np.log(max(weight[index], 1e-12))
                - 0.5 * np.log(2.0 * np.pi * sigma2[index])
                - 0.5 * (x - mu[index]) ** 2 / sigma2[index])
    score = np.full(values.size, np.nan, np.float64)
    ok = np.isfinite(values)
    score[ok] = (_log_density(values[ok], dark)
                 - _log_density(values[ok], light))
    scale = sd_or_one(score)
    detail = {"mixture_mu": (float(mu[dark]), float(mu[light])),
              "mixture_sigma": (float(np.sqrt(sigma2[dark])),
                                float(np.sqrt(sigma2[light]))),
              "mixture_weight_ink": float(weight[dark]),
              "mixture_scale": float(scale)}
    return score / scale, detail


# ------------------------------------------- the fallback population

def sd_or_one(values: np.ndarray) -> float:
    values = np.asarray(values, np.float64)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return 1.0
    sd = float(np.std(values))
    return sd if np.isfinite(sd) and sd > 1e-12 else 1.0


def fallback_population(score: np.ndarray, rows: np.ndarray,
                         labelled_fit: np.ndarray, values: np.ndarray,
                         min_per_class: int) -> tuple[np.ndarray, dict]:
    """The `subtract` population on the shared scale (see the docstring).

    Centred at the midpoint of its own fit-fold class means when both
    classes clear `min_per_class`, else at the population's median (no
    label needed); divided by the sd of its fit-fold labelled scores, or
    left at unit scale when there are too few of them.
    """
    mine = score[rows]
    labelled = np.flatnonzero(labelled_fit[rows])
    label_scores = mine[labelled]
    label_bits = values[rows][labelled]
    n_1 = int(np.count_nonzero(label_bits == 1))
    n_0 = int(label_bits.size - n_1)
    if min(n_0, n_1) >= int(min_per_class):
        centre = 0.5 * (float(np.mean(label_scores[label_bits == 1]))
                        + float(np.mean(label_scores[label_bits == 0])))
        centred_on = "class_midpoint"
    else:
        finite = mine[np.isfinite(mine)]
        centre = float(np.median(finite)) if finite.size else 0.0
        centred_on = "median"
    scale = sd_or_one(label_scores)
    return (mine - centre) / scale, {
        "patch_fallback_centre": centred_on,
        "patch_fallback_centre_value": float(centre),
        "patch_fallback_n_fit_0": n_0, "patch_fallback_n_fit_1": n_1,
        "patch_fallback_scale": float(scale)}


def _stack(parts: list[np.ndarray], dtype) -> np.ndarray:
    kept = [np.asarray(part, dtype) for part in parts if part.size]
    if not kept:
        return np.zeros(0, dtype)
    return np.concatenate(kept)


def fit_population(spec: Any, X_own: np.ndarray, y_own: np.ndarray,
                   half_own: np.ndarray, X_apply: np.ndarray,
                   pool: np.ndarray | None, *,
                   extra: tuple[np.ndarray, np.ndarray, np.ndarray]
                   | None = None,
                   extra_half: np.ndarray | None = None,
                   local: tuple[np.ndarray, np.ndarray, np.ndarray]
                   | None = None,
                   scale_rows: np.ndarray | None = None,
                   shrinkage: float | None = None,
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Cross-fit ONE population's filter and score it; P2 lives here.

    `spec` is a `patch.PatchSpec` — read here for `shrinkage`,
    `selftrain_rounds`, `selftrain_keep` and `selftrain_weight` only, and
    typed `Any` so this module never imports the one that dispatches
    into it.

    THE RIDGE THE WALK CHOSE (2026-09-07 review, blocker).  `shrinkage`
    overrides `spec.shrinkage` and is the value `autoknobs.choose`
    returned for THIS population — under `patch_shrinkage="auto"` the
    walk minimises the regulariser inside every candidate (W4) and
    publishes the winner in `auto_choices`, and until this argument
    existed the fit ran at the spec's inherited constant instead, so the
    ledger named a ridge the filter was never fitted at.  `None` keeps
    the spec's, which is what a run that NAMES its shrinkage has.  The
    value used comes back in `detail["shrinkage_fitted"]`, which is what
    pins the ridge the ledger publishes to the ridge the filter was
    fitted at.

    `X_own`/`y_own`/`half_own` are the footprint's own fit-fold labelled
    rows (the halo), `X_apply` every row this population scores.  `local`
    (P1g) is a second labelled set with its own halves; `extra` (P3, and
    B1's door) are weighted rows that join the fit.  Returns
    ``(oof_own, insample_own, scores_apply, detail)``; `detail` carries
    `extra_oof`, the extra rows' OUT-OF-FOLD scores, when they were
    cross-fitted.

    RULING 7 REACHES THE DECODER'S ROWS TOO (review 2026-09-06).  `extra`
    used to be `always`: in both half fits, in the full fit, and scored
    by the full fit AT ITS OWN CELLS — an in-sample score that
    `calibrate` then took as a PAVA training pair and BP took as channel
    evidence at the map's ceiling.  Given `extra_half` the rows are
    cross-fitted like any other training row (halves by the caller's
    `fold_hash`), so every other cell still gets a filter trained on all
    of them while the pseudo cells themselves carry an out-of-fold score.
    Without `extra_half` the old `always` behaviour stands, for B1's door
    and for the tests that pin it.

    `scale_rows` is a mask over `X_own`'s rows naming the ones this
    population actually OWNS (an earlier tier may already have scored the
    rest): the shared scale of the module docstring is the sd of THEIR
    out-of-fold scores, so the rows that leave on this filter's scale are
    the rows that set it.

    P2 (self-training, MEAS §5b): for `spec.selftrain_rounds` rounds the
    ``spec.selftrain_keep`` most confident rows of `pool` — a subset of
    the applied rows, the caller's business, and never a row the frame
    knows — are re-derived from the CURRENT scores, labelled by their own
    sign at weight `spec.selftrain_weight`, and the filter is refitted
    with them through the same cross-fit.  Re-derived, not accumulated
    (`analyze_selftrain.py`'s loop), and deterministic: a percentile
    threshold, never a draw.
    """
    X_local, y_local, half_local = (
        local if local is not None
        else (np.zeros((0, X_own.shape[1]), np.float32),
              np.zeros(0, np.uint8), np.zeros(0, bool)))
    X_extra, y_extra, w_extra = (
        extra if extra is not None
        else (np.zeros((0, X_own.shape[1]), np.float32),
              np.zeros(0, np.uint8), np.zeros(0, np.float64)))
    n_own = int(y_own.size)
    n_local = int(y_local.size)
    n_extra = int(y_extra.size)
    crossfit_extra = extra_half is not None and n_extra > 0
    half_extra = (np.asarray(extra_half, bool) if crossfit_extra
                  else np.zeros(n_extra, bool))
    if half_extra.size != n_extra:
        raise PatchError(f"fit_population: extra_half has {half_extra.size} "
                         f"entries for {n_extra} extra rows")
    base_X = [X_own, X_local, X_extra]
    base_y = [y_own, y_local, y_extra]
    base_w = [np.ones(n_own, np.float64), np.ones(n_local, np.float64),
              np.asarray(w_extra, np.float64)]
    base_half = [half_own, half_local, half_extra]
    base_always = [np.zeros(n_own, bool), np.zeros(n_local, bool),
                   np.zeros(n_extra, bool) if crossfit_extra
                   else np.ones(n_extra, bool)]
    pool = (np.zeros(0, np.int64) if pool is None
            else np.asarray(pool, np.int64))
    ridge = float(spec.shrinkage if shrinkage is None else shrinkage)
    rounds = max(0, int(spec.selftrain_rounds))
    n_self = 0
    detail: dict[str, Any] = {}
    self_X = np.zeros((0, X_own.shape[1]), np.float32)
    self_y = np.zeros(0, np.uint8)
    for round_index in range(rounds + 1):
        X = np.concatenate([np.asarray(part, np.float64)
                            for part in base_X + [self_X]])
        y = _stack(base_y + [self_y], np.uint8)
        w = _stack(base_w + [np.full(self_y.size, float(spec.selftrain_weight),
                                     np.float64)], np.float64)
        half = _stack(base_half + [np.zeros(self_y.size, bool)], bool)
        always = _stack(base_always + [np.ones(self_y.size, bool)], bool)
        oof, full = crossfit_scores(X, y, w, half, shrinkage=ridge,
                                    always=always)
        scores_apply = apply_discriminant(X_apply, full)
        if round_index >= rounds or not pool.size:
            if scale_rows is not None:
                owned = oof[:n_own][np.asarray(scale_rows, bool)]
                owned = owned[np.isfinite(owned)]
                extra_scale = (float(np.std(owned)) if owned.size > 1
                               else 1.0)
                if not np.isfinite(extra_scale) or extra_scale <= 1e-12:
                    extra_scale = 1.0
                oof = oof / extra_scale
                scores_apply = scores_apply / extra_scale
                full = dc_replace(full, scale=float(full.scale) * extra_scale)
            oof_own = oof[:n_own]
            insample_own = apply_discriminant(X_own, full)
            detail.update({"n_self": int(n_self),
                           "self_rounds": int(round_index),
                           "shrinkage_fitted": float(ridge),
                           "n_extra_crossfit": (int(n_extra)
                                                if crossfit_extra else 0),
                           "scale": float(full.scale)})
            if crossfit_extra:
                detail["extra_oof"] = np.asarray(
                    oof[n_own + n_local:n_own + n_local + n_extra],
                    np.float64)
            return oof_own, insample_own, scores_apply, detail
        confidence = np.abs(scores_apply[pool])
        finite = confidence[np.isfinite(confidence)]
        if finite.size < 2:
            continue
        threshold = float(np.percentile(
            finite, 100.0 * (1.0 - float(spec.selftrain_keep))))
        picked = pool[np.isfinite(confidence) & (confidence >= threshold)]
        if not picked.size:
            continue
        self_X = np.asarray(X_apply[picked], np.float32)
        self_y = (scores_apply[picked] > 0.0).astype(np.uint8)
        n_self = int(picked.size)
    raise PatchError("unreachable: the self-training loop always returns")



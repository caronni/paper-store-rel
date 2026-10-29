"""The PURE path — detector to decoder, with nothing fitted in between.

W8 B6, from the user's ruling of 2026-09-06:

    "sample all MY* cells in the 5x5 tile set and discriminate CMY from
    MY using the certified tiles and the certified planes of the tile
    under observation; we already have every tile addressed, the correct
    page field and mostly correct poses per plane — there is no
    justification for pushing that through PAVA, ctx, Platt; just try it
    out either way."

and W8 F2, from the user's rulings on the first trial (APPROACHES §6.5):

    "cells with unknown sibling state obviously are erasures / ie
    uncounted" — and — "why do we need refit??": the price comes from
    the tile itself.

BLIND.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`, and nothing here imports
:mod:`analyzer.arms` (which dispatches into this module).  Every label
this module reads is a `KnownFrame` bit on the FIT fold — a certified
neighbour's projection, a dust cell, the metadata cell — never the target
tile's own cargo and never a search- or select-fold row.  The tile's own
cargo is read as SCORES ONLY, without a label in sight.

WHAT IT REPLACES.  `calibrate.calibrate` turns a presence score into an
LLR through a PAVA map per branch, then a 9-bin context correction, then
(with `platt`) a per-lane weight fitted on the select fold — three fitted
stages between a discriminant that already separates the classes and a
decoder that only wants a log-odds.  The pure path keeps ONE number per
population, an error rate, and spends it directly: ``llr = sign(score -
threshold) * log((1 - e) / e)``, the log-odds of a binary symmetric
channel whose crossover is `e` — which is what a hard decision from a
discriminant IS.  `pure_soft=True` scales the magnitude by the
standardised score, capped at `SOFT_CLIP` sd; nothing else changes.

WHERE `e` COMES FROM — the tile, floored by the halo.  The first trial
(§6.5) priced eight dead-band tiles at the halo's held-out error, ~3 %,
where the same cells measure ~15 %: a certified neighbour's cells are
EASIER than a dead-band tile's cargo, so the halo's number is a floor on
the tile's error, never an estimate of it.  Per sibling state, then:

* THE SELF PRICE.  The discriminant's scores on the tile's OWN cargo
  cells of that state are two populations, the inked and the blank, in
  the code's own proportion (the keystream whitens the cargo, so the
  prior is 1/2 and 1/2 and is FIXED, not fitted).  A two-component
  Gaussian fit with those equal priors — initialised at the 30th/70th
  percentiles with the population's own variance, as `patch`'s mixture
  is, run for `SELF_STEPS` EM steps, no RNG — gives the error of the
  hard decision at the adopted threshold on exactly the cells being
  decoded: ``e_self = ½·P(score > t | blank) + ½·P(score <= t | ink)``.
  A well-separated tile reads ~0; a tile whose ink has faded into the
  blank population reads the overlap; a filter with nothing in it reads
  a unimodal population and prices itself near chance.

* THE HALO FLOOR.  The fit-fold labelled rows of the state are split
  into the SAME two halves `patch.crossfit_scores` uses
  (`calibrate.fold_hash` under `patch.CROSSFIT_SALT`); the class-mean
  midpoint of one half is the threshold applied to the other and the
  error of that hard decision is counted on rows the threshold never
  saw.  Both directions are published (`error_halves`).  That number is
  the FLOOR: the adopted `e` is ``max(e_self, e_halo)``, clamped into
  [`ERROR_FLOOR`, `ERROR_CEILING`] so a small sample can neither claim
  certainty nor invert the sign.  The threshold is the halo's midpoint —
  the discriminant's own centring, anchored by labels — and the fit's
  own equal-density boundary is published beside it so a shifted tile
  can be read.

* A state whose halo cannot measure a floor (too few labels of a class
  in a half) takes the POOLED halo's threshold and floor, and is listed
  in `pure_fallback_states`; a state with no floor at all is erased.  A
  state with too few cargo cells to fit its own populations takes the
  TILE-POOLED self fit at its own threshold (`_tile_fit`) — smeared, so
  pessimistic, and still the tile's.
  A cell whose sibling state is UNKNOWN is an ERASURE — LLR 0, counted
  in `pure_erased_cells` and `pure_unknown_state_cells` — never priced
  by anything, and never counted into the POOLED halo either (its score
  comes from a different discriminant, on another scale).  There is no
  context stage, no Platt, no map, no refit.

DETERMINISM.  No RNG: the halves are `calibrate.fold_hash`, the fit's
init is a percentile and its step count fixed, every statistic is a
mean or a count, and a repeat call is `np.array_equal`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from holo.receiver.lib import ldpc, pava

from . import calibrate as cal
from . import patch as patch_mod
from . import statecal
from .residue import discriminating_mask
from .types import BRANCH_ALL, Folds, KnownFrame, LaneFootprint, STREAMS


class PureError(Exception):
    """A pure-path calibration that cannot be spelled."""


#: The value of the `calibration` knob that selects this path.
CALIBRATION_PURE: str = "pure"

#: `e` is clamped into this band before it becomes a log-odds: a
#: population that measures 0 errors on a few hundred rows has not proven
#: certainty (the floor caps |llr| at log 99 = 4.60), and one that
#: measures worse than the ceiling has not proven a direction either (the
#: cap leaves |llr| at log(0.55/0.45) = 0.20, a fifth of a bit — what a
#: collapsed filter is worth).
ERROR_FLOOR: float = 0.01
ERROR_CEILING: float = 0.45
#: `pure_soft`: the standardised score is clipped at this many sd before
#: it scales the magnitude, so one wild cell cannot outvote the rest.
SOFT_CLIP: float = 3.0
#: A cross-fit half must hold this many labels of EACH class or it has no
#: class-mean midpoint to hand the other half — `patch`'s own floor, the
#: same number for the same reason.
MIN_PER_CLASS_PER_HALF: int = patch_mod.MIN_PER_CLASS_PER_HALF
#: The pooled halo population, behind a state whose own halo is starved.
POOLED: str = BRANCH_ALL
#: The self fit: `patch`'s mixture recipe (its init and its refusal
#: floor), with the step count raised — measured on synthetic pairs, 20
#: fixed-prior steps leave a 15 % overlap read at 17-19 %; 50 read it at
#: 15.2 % (n 1000-2000), and a 1000-cell population costs nothing.
SELF_INIT_PERCENTILES: tuple[float, float] = patch_mod.MIXTURE_INIT_PERCENTILES
SELF_MIN_CELLS: int = patch_mod.MIXTURE_MIN_CELLS
SELF_STEPS: int = 50
#: How the fit's own boundary is located: the error is scanned on this
#: many points between the two component means.
_BOUNDARY_GRID: int = 201
#: `pure_price_source` per state.
PRICE_SELF: str = "self"          # the tile's own overlap binds
PRICE_FLOOR: str = "floor"        # the halo floor binds (self <= floor)
PRICE_FLOOR_ONLY: str = "floor:"  # + the self refusal: no self estimate
#: What the blind detail carries per state and for the pooled halo.
_POPULATION_KEYS: tuple[str, ...] = (
    "n_labels", "n_0", "n_1", "n_labels_halves", "n_measured", "n_cells",
    "n_cargo", "scale", "error_raw", "error_halves", "reason", "priced_by",
    "own_threshold", "threshold", "floor", "self_error", "self_reason",
    "self_mu", "self_sigma", "self_boundary", "self_error_at_boundary",
    "error", "price_source")
_POOLED_KEYS: tuple[str, ...] = (
    "n_labels", "n_0", "n_1", "n_measured", "error", "error_raw",
    "error_halves", "threshold", "reason")


# ------------------------------------------------------------- the spec

@dataclass(frozen=True)
class PureSpec:
    """Every knob of the pure path, one frozen value."""

    soft: bool = False
    exclude_word_sites: bool = True
    error_floor: float = ERROR_FLOOR
    error_ceiling: float = ERROR_CEILING
    min_per_class_per_half: int = MIN_PER_CLASS_PER_HALF
    self_min_cells: int = SELF_MIN_CELLS
    self_steps: int = SELF_STEPS

    def __post_init__(self) -> None:
        if not 0.0 < self.error_floor < self.error_ceiling < 0.5:
            raise PureError(
                f"pure error band [{self.error_floor}, "
                f"{self.error_ceiling}] must satisfy 0 < floor < ceiling "
                f"< 0.5")
        if int(self.min_per_class_per_half) < 1:
            raise PureError("pure_min_per_class_per_half must be >= 1")
        if int(self.self_min_cells) < 2:
            raise PureError("pure_self_min_cells must be >= 2")
        if int(self.self_steps) < 1:
            raise PureError("pure_self_steps must be >= 1")


def is_pure(knobs: Mapping[str, Any] | None,
            unmix_mode: str | None = None) -> bool:
    """Does this (knob bag, arm) ask for the pure path?

    TWO doors, and the arm's is the finer one.  `calibration="pure"` in
    the knob bag puts the WHOLE battery on the pure path — B6's `pure`
    family, where that is the point.  The `pure` unmix mode (W8 B8) puts
    ONE arm on it: `pure+committed` computes exactly the score
    `patch+committed` computes and differs from it only here, so a
    battery can carry both and the ledger attributes the difference to
    the calibration alone.  That is what makes `patch-then-pure`'s
    re-roll placement a one-variable experiment.
    """
    if unmix_mode is not None and str(unmix_mode) == patch_mod.UNMIX_PURE:
        return True
    return str(dict(knobs or {}).get("calibration", "")) == CALIBRATION_PURE


def spec_from_knobs(knobs: Mapping[str, Any] | None) -> PureSpec:
    """The `pure_*` knobs of a knob bag, defaults where absent."""
    knobs = dict(knobs or {})
    base = PureSpec()
    return PureSpec(
        soft=bool(knobs.get("pure_soft", base.soft)),
        exclude_word_sites=bool(knobs.get("patch_exclude_word_sites",
                                          base.exclude_word_sites)),
        error_floor=float(knobs.get("pure_error_floor", base.error_floor)),
        error_ceiling=float(knobs.get("pure_error_ceiling",
                                      base.error_ceiling)),
        min_per_class_per_half=int(knobs.get("pure_min_per_class_per_half",
                                             base.min_per_class_per_half)),
        self_min_cells=int(knobs.get("pure_self_min_cells",
                                     base.self_min_cells)),
        self_steps=int(knobs.get("pure_self_steps", base.self_steps)))


# ------------------------------------------------ the halo measurement

def _midpoint(score: np.ndarray, values: np.ndarray,
              rows: np.ndarray) -> float | None:
    """The class-mean midpoint of a labelled set; None if a class is empty.

    The threshold `patch.fit_discriminant` puts on its own scores, re-derived
    here so the pure path prices a score nobody centred as readily.
    """
    if not rows.size:
        return None
    ones = rows[values[rows] == 1]
    zeros = rows[values[rows] == 0]
    if not ones.size or not zeros.size:
        return None
    return 0.5 * (float(np.mean(score[ones])) + float(np.mean(score[zeros])))


def measure(score: np.ndarray, values: np.ndarray, rows: np.ndarray,
            half: np.ndarray, spec: PureSpec) -> dict[str, Any]:
    """One population's threshold and HELD-OUT error rate — the floor.

    `rows` are its fit-fold labelled footprint rows and `half` is the
    cross-fit split over the footprint.  Half A's midpoint thresholds
    half B and B's thresholds A, so no row is measured against a
    threshold it set; both rates are returned and `error` pools them.
    """
    ones = int(np.count_nonzero(values[rows] == 1)) if rows.size else 0
    entry: dict[str, Any] = {
        "n_labels": int(rows.size), "n_1": ones,
        "n_0": int(rows.size) - ones,
        "threshold": None, "scale": 1.0,
        "error": None, "error_raw": None, "error_halves": (None, None),
        "n_labels_halves": (0, 0), "n_measured": 0, "reason": "no_labels"}
    if not rows.size:
        return entry
    entry["threshold"] = _midpoint(score, values, rows)
    finite = score[rows][np.isfinite(score[rows])]
    if finite.size > 1:
        spread = float(np.std(finite))
        if np.isfinite(spread) and spread > 1e-12:
            entry["scale"] = spread
    part_a = rows[np.asarray(half, bool)[rows]]
    part_b = rows[~np.asarray(half, bool)[rows]]
    entry["n_labels_halves"] = (int(part_a.size), int(part_b.size))
    wrong = seen = 0
    halves: list[float | None] = [None, None]
    floor = int(spec.min_per_class_per_half)
    for index, (fit_rows, eval_rows) in enumerate(((part_b, part_a),
                                                   (part_a, part_b))):
        if not eval_rows.size:
            continue
        ones_fit = int(np.count_nonzero(values[fit_rows] == 1))
        if min(ones_fit, int(fit_rows.size) - ones_fit) < floor:
            continue
        threshold = _midpoint(score, values, fit_rows)
        if threshold is None:
            continue
        mine = int(np.count_nonzero((score[eval_rows] > threshold)
                                    != (values[eval_rows] == 1)))
        halves[index] = mine / float(eval_rows.size)
        wrong += mine
        seen += int(eval_rows.size)
    entry["error_halves"] = (halves[0], halves[1])
    if not seen or entry["threshold"] is None:
        entry["reason"] = ("half_starved" if entry["threshold"] is not None
                           else "one_class")
        return entry
    raw = wrong / float(seen)
    entry["error_raw"] = float(raw)
    entry["error"] = clamp_error(raw, spec)
    entry["n_measured"] = int(seen)
    entry["reason"] = "measured"
    return entry


def clamp_error(error: float, spec: PureSpec) -> float:
    """`e` into [floor, ceiling] — neither certainty nor an inverted sign."""
    return float(min(max(float(error), spec.error_floor),
                     spec.error_ceiling))


def weight_of(error: float) -> float:
    """``log((1 - e) / e)`` — the log-odds of a hard decision at rate `e`."""
    e = float(error)
    if not 0.0 < e < 1.0:
        raise PureError(f"pure weight wants 0 < e < 1, got {e}")
    return float(np.log((1.0 - e) / e))


# ------------------------------------------------------ the self price

@dataclass(frozen=True)
class SelfFit:
    """Two equal-prior Gaussians on one population; `lo` is the blank."""

    mu_lo: float
    mu_hi: float
    sigma_lo: float
    sigma_hi: float
    n: int


def self_fit(scores: np.ndarray, *, steps: int = SELF_STEPS) -> SelfFit:
    """Two-Gaussian EM with the priors FIXED at 1/2 and 1/2.

    `patch.mixture_score`'s recipe — percentile init with the population's
    own variance, a fixed step count, no RNG — with one change: the
    component weights are never updated, because the population is the
    tile's cargo and the keystream has already made its prior the code's
    own.  (That is also what keeps a half-empty fit honest: a population
    that is really 90/10 is read as two halves and priced worse than it
    is, never better.)  Returns the two components ordered by mean.
    """
    x = np.asarray(scores, np.float64).reshape(-1)
    x = x[np.isfinite(x)]
    if x.size < 2:
        raise PureError("self fit: fewer than two finite scores")
    low, high = np.percentile(x, list(SELF_INIT_PERCENTILES))
    var = max(float(np.var(x)), 1e-12)
    mu = np.array((float(low), float(high)), np.float64)
    sigma2 = np.array((var, var), np.float64)
    for _ in range(int(steps)):
        density = (np.exp(-0.5 * (x[:, None] - mu[None, :]) ** 2
                          / sigma2[None, :])
                   / np.sqrt(2.0 * np.pi * sigma2[None, :]))
        total = density.sum(axis=1)
        resp = density / np.where(total > 1e-300, total, 1e-300)[:, None]
        mass = np.maximum(resp.sum(axis=0), 1e-12)
        mu = (resp * x[:, None]).sum(axis=0) / mass
        sigma2 = np.maximum(
            (resp * (x[:, None] - mu[None, :]) ** 2).sum(axis=0) / mass,
            1e-12)
    lo = int(np.argmin(mu))
    hi = 1 - lo
    return SelfFit(mu_lo=float(mu[lo]), mu_hi=float(mu[hi]),
                   sigma_lo=float(np.sqrt(sigma2[lo])),
                   sigma_hi=float(np.sqrt(sigma2[hi])), n=int(x.size))


def _phi(z: float) -> float:
    """The standard normal CDF."""
    return 0.5 * math.erfc(-float(z) / math.sqrt(2.0))


def error_at(threshold: float, fit: SelfFit) -> float:
    """The error of ``score > threshold => ink`` under the fit, priors 1/2.

    ``½·P(x > t | lo) + ½·P(x <= t | hi)`` — the overlap of the two
    components at `t`; at the equal-density point it is the Bayes error.
    """
    t = float(threshold)
    return float(0.5 * (1.0 - _phi((t - fit.mu_lo) / fit.sigma_lo))
                 + 0.5 * _phi((t - fit.mu_hi) / fit.sigma_hi))


def _own_boundary(fit: SelfFit) -> tuple[float, float]:
    """The fit's own least-error threshold between its means, and that
    error — published so a tile whose halo threshold sits off its own
    boundary can be read; it prices nothing."""
    grid = np.linspace(fit.mu_lo, fit.mu_hi, _BOUNDARY_GRID)
    errors = np.array([error_at(t, fit) for t in grid], np.float64)
    at = int(np.argmin(errors))
    return float(grid[at]), float(errors[at])


def self_price(score: np.ndarray, rows: np.ndarray, threshold: float,
               spec: PureSpec) -> dict[str, Any]:
    """The tile's own error at `threshold`, from its cargo scores alone."""
    finite = score[rows][np.isfinite(score[rows])] if rows.size else \
        np.zeros(0, np.float64)
    entry: dict[str, Any] = {
        "n_cargo": int(finite.size), "self_error": None,
        "self_reason": "below_self_min_cells", "self_mu": None,
        "self_sigma": None, "self_boundary": None,
        "self_error_at_boundary": None}
    if finite.size < int(spec.self_min_cells):
        return entry
    fit = self_fit(finite, steps=int(spec.self_steps))
    boundary, at_boundary = _own_boundary(fit)
    entry.update({
        "self_error": error_at(threshold, fit), "self_reason": "fitted",
        "self_mu": (fit.mu_lo, fit.mu_hi),
        "self_sigma": (fit.sigma_lo, fit.sigma_hi),
        "self_boundary": boundary, "self_error_at_boundary": at_boundary})
    return entry


def _tile_fit(score: np.ndarray, rows: np.ndarray, spec: PureSpec,
              ) -> tuple[SelfFit | None, tuple[float, float] | None]:
    """The WHOLE tile's known-state cargo as one population, and its own
    boundary — the fallback fit for a state with too few cargo cells to
    fit its own (`self_min_cells`).

    Pooling the states smears the two components by their per-state
    offsets, so this reads the overlap PESSIMISTICALLY: it can only raise
    a starved state's price above the halo floor, never lower it.  It is
    still the TILE's own scores — never the halo's optimism, which is
    what §6.5 measured as the defect.
    """
    finite = score[rows][np.isfinite(score[rows])] if rows.size else \
        np.zeros(0, np.float64)
    if finite.size < int(spec.self_min_cells):
        return None, None
    fit = self_fit(finite, steps=int(spec.self_steps))
    return fit, _own_boundary(fit)


def _tile_self(own: dict[str, Any], fit: SelfFit | None,
               boundary: tuple[float, float] | None,
               threshold: float) -> dict[str, Any]:
    """`own`, with the tile-pooled fit standing in for a refused self fit."""
    if fit is None or boundary is None:
        return own
    return {**own, "self_error": error_at(threshold, fit),
            "self_reason": f"tile:{own['self_reason']}",
            "self_mu": (fit.mu_lo, fit.mu_hi),
            "self_sigma": (fit.sigma_lo, fit.sigma_hi),
            "self_boundary": boundary[0],
            "self_error_at_boundary": boundary[1]}


# --------------------------------------------------------- the calibration

def _state_masks(state: np.ndarray, usable: np.ndarray,
                 ) -> dict[str, np.ndarray]:
    """One population per KNOWN sibling state; the unknown are erasures."""
    return {name: usable & (state == index)
            for index, name in enumerate(statecal.STATE_BRANCHES)}


def _priced(halo: dict[str, Any], own: dict[str, Any], pooled: dict[str, Any],
            name: str, spec: PureSpec) -> dict[str, Any]:
    """One state's entry: halo floor (own or pooled), self price, adopted."""
    entry = {**halo, "own_threshold": halo["threshold"], "priced_by": name}
    if entry["error"] is None and pooled["error"] is not None:
        entry.update(threshold=pooled["threshold"], scale=pooled["scale"],
                     error=pooled["error"], error_raw=pooled["error_raw"],
                     reason=f"pooled:{halo['reason']}", priced_by=POOLED)
    entry["floor"] = entry["error"]
    entry.update(own)
    entry["price_source"] = None
    if entry["floor"] is None:
        entry["error"] = None
        entry["priced_by"] = None
        return entry
    floor_raw = float(entry["error_raw"])
    if entry["self_error"] is None:
        entry["price_source"] = PRICE_FLOOR_ONLY + str(entry["self_reason"])
        return entry
    own_error = float(entry["self_error"])
    entry["error"] = clamp_error(max(own_error, floor_raw), spec)
    # "self" means the tile's own price is what BP gets: it is above the
    # floor after the clamp, not merely above the halo's raw count
    entry["price_source"] = (PRICE_SELF if entry["error"] > entry["floor"]
                             else PRICE_FLOOR)
    return entry


def pure_llr(score: np.ndarray, frame: KnownFrame, target_plane: int,
             lfp: LaneFootprint, folds: Folds, *,
             spec: PureSpec | None = None,
             stream_id: str | None = None,
             pseudo_rows: np.ndarray | None = None,
             ) -> tuple[np.ndarray, dict]:
    """Presence scores -> LLR with no fitted stage; the pure path.

    Signature-compatible with `calibrate.calibrate` where it matters:
    same inputs, an LLR over the footprint rows, and a blind detail
    carrying the select-fold label arrays, so `select_arm`, `combine` and
    the ledger read a pure arm as they read any other.  The select-fold
    loss those arbitrations pair on is therefore the pure LLR's own log
    loss on the select-fold labels — the two paths are compared on the
    number the decoder actually consumes.

    Decoder pseudo labels (B4) are NOT read here: in the pure path they
    train the FILTER, there being no map to refit, so the floor stays a
    statement about the frame's own certified labels and the price a
    statement about the tile's own scores.  `pseudo_rows` are the rows
    they trained it ON, and they are SUBTRACTED from the self population
    (ruling R3, follow-up review): a filter measured on the cells that
    trained it reads its own error low — "ruling 7 one stage down", which
    `arms` already refuses for the PAVA map.
    """
    spec = PureSpec() if spec is None else spec
    score = np.asarray(score, np.float64)
    n = int(score.size)
    observed = np.asarray(lfp.observed, bool)
    if observed.size != n:
        raise PureError(f"score has {n} entries, the lane footprint "
                        f"observes {observed.size}")
    usable = observed & np.isfinite(score)
    stream = stream_id or (frame.target[3] if frame.target is not None
                           else STREAMS[target_plane])
    values = np.asarray(frame.bits[:, target_plane], np.uint8)
    labels_all = np.asarray(frame.known[:, target_plane], bool) & usable
    state = statecal.sibling_state(frame, target_plane)
    kind = frame.furniture_kind
    word = (np.asarray(kind, np.int8) == statecal.FURNITURE_WORD
            if kind is not None else np.zeros(n, bool))
    train = labels_all & np.asarray(folds.fit, bool)
    if spec.exclude_word_sites:
        train = train & ~word
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    half = cal.fold_hash(cells, int(folds.seed)
                         ^ patch_mod.CROSSFIT_SALT) < 0.5
    own_cargo = (usable & np.asarray(lfp.tile.in_tile, bool)
                 & np.asarray(lfp.tile.cargo, bool))

    if pseudo_rows is not None and np.asarray(pseudo_rows).size:
        own_cargo = own_cargo.copy()
        own_cargo[np.asarray(pseudo_rows, np.int64)] = False

    known_state = np.asarray(state, np.int8) >= 0
    masks = _state_masks(state, usable)
    # R2, all the way down: a labelled row whose sibling state is UNKNOWN
    # is uncounted HERE too, not only where it is decoded.  It carries a
    # different discriminant's score (`patch.fallback_population`, another
    # scale), and the pooled halo is what prices every starved state — so
    # one such row in the pool moves the threshold every fallback state
    # signs by.  The pool is the known-state rows and nothing else.
    pooled = measure(score, values, np.flatnonzero(train & known_state),
                     half, spec)
    tile_fit, tile_boundary = _tile_fit(
        score, np.flatnonzero(own_cargo & known_state), spec)
    llr = np.zeros(n, np.float64)
    covered = np.zeros(n, bool)
    fallback: list[str] = []
    populations: dict[str, Any] = {}
    for name, mask in masks.items():
        halo = measure(score, values, np.flatnonzero(train & mask), half,
                       spec)
        threshold = halo["threshold"] if halo["error"] is not None \
            else pooled["threshold"]
        own = (self_price(score, np.flatnonzero(mask & own_cargo),
                          float(threshold), spec)
               if threshold is not None else
               self_price(score, np.zeros(0, np.int64), 0.0, spec))
        if own["self_error"] is None and threshold is not None:
            own = _tile_self(own, tile_fit, tile_boundary, float(threshold))
        entry = _priced(halo, own, pooled, name, spec)
        rows = np.flatnonzero(mask)
        entry["n_cells"] = int(rows.size)
        if not rows.size:
            # a state that owns no cell of this tile priced nothing; it is
            # not a pooled fallback and its record says so
            entry["priced_by"] = None
            entry["price_source"] = None
        elif entry["priced_by"] == POOLED and entry["error"] is not None:
            fallback.append(name)
        populations[name] = entry
        if not rows.size or entry["error"] is None:
            continue
        weight = weight_of(float(entry["error"]))
        delta = score[rows] - float(entry["threshold"])
        if spec.soft:
            magnitude = (np.clip(delta / float(entry["scale"]),
                                 -SOFT_CLIP, SOFT_CLIP) / SOFT_CLIP)
        else:
            magnitude = np.sign(delta)
        llr[rows] = np.clip(magnitude * weight,
                            -ldpc.LLR_CLIP, ldpc.LLR_CLIP)
        covered[rows] = True

    detail = _detail(spec, frame, target_plane, lfp, folds, stream, llr,
                     values, labels_all, covered, usable, observed, state,
                     populations, pooled, tuple(fallback))
    detail["pure_self_excluded_cells"] = (
        0 if pseudo_rows is None else int(np.asarray(pseudo_rows).size))
    detail["pure_floor_only_cargo_cells"] = int(sum(
        entry["n_cargo"] for entry in populations.values()
        if str(entry["price_source"] or "").startswith(PRICE_FLOOR_ONLY)))
    llr.setflags(write=False)
    return llr, detail


def _detail(spec: PureSpec, frame: KnownFrame, target_plane: int,
            lfp: LaneFootprint, folds: Folds, stream: str,
            llr: np.ndarray, values: np.ndarray, labels_all: np.ndarray,
            covered: np.ndarray, usable: np.ndarray, observed: np.ndarray,
            state: np.ndarray, populations: dict[str, Any],
            pooled: dict[str, Any], fallback: tuple[str, ...]) -> dict:
    """The blind record: the label arrays every arbitration reads, the
    per-state numbers this path is judged on, and the counts that say
    how much of the tile it refused to price."""
    in_tile = np.asarray(lfp.tile.in_tile, bool)
    cargo = np.asarray(lfp.tile.cargo, bool)
    discriminating = discriminating_mask(frame.bits, frame.known, stream)
    cargo_cells = usable & in_tile & cargo
    labels_cleanable = float(
        np.count_nonzero(labels_all & frame.siblings)
        / max(1, np.count_nonzero(labels_all)))
    detail: dict[str, Any] = {
        "calibration": CALIBRATION_PURE, "pure_soft": bool(spec.soft),
        "pure_error_band": (float(spec.error_floor),
                            float(spec.error_ceiling)),
        "pure_exclude_word_sites": bool(spec.exclude_word_sites),
        "pure_self_steps": int(spec.self_steps),
        "pure_self_min_cells": int(spec.self_min_cells),
        # the ADOPTED price per state, flat, and where it came from
        "pure_error_by_state": {name: entry["error"]
                                for name, entry in populations.items()},
        "pure_price_by_state": {
            name: {"self": entry["self_error"], "floor": entry["floor"],
                   "adopted": entry["error"]}
            for name, entry in populations.items()},
        "pure_price_source": {name: entry["price_source"]
                              for name, entry in populations.items()},
        "pure_n_labels_by_state": {name: entry["n_labels"]
                                   for name, entry in populations.items()},
        "pure_threshold_by_state": {name: entry["threshold"]
                                    for name, entry in populations.items()},
        # ... and everything else about them, including BOTH cross-fit
        # directions and the self fit, under one key
        "pure_populations": {
            name: {key: entry[key] for key in _POPULATION_KEYS}
            for name, entry in populations.items()},
        "pure_pooled": {key: pooled[key] for key in _POOLED_KEYS},
        "pure_fallback_states": tuple(fallback),
        # F2: an unknown sibling state is an ERASURE, priced by nothing
        "pure_unknown_state_cells": int(np.count_nonzero(usable
                                                        & (state < 0))),
        "pure_erased_cells": int(np.count_nonzero(usable & ~covered)),
        "pure_cargo_erased_cells": int(np.count_nonzero(
            cargo_cells & ~covered)),
        # the shape `calibrate` publishes, so a pure row reads like any
        # other row of the ledger
        "ctx_mode": "none", "ctx_adopted": False, "n_ctx_eligible": 0,
        "ctx_state_any_adopted": False,
        "n_observed": int(np.count_nonzero(observed)),
        "n_calibrated": int(np.count_nonzero(covered)),
        "n_labels": int(np.count_nonzero(labels_all)),
        "n_labels_fit": int(np.count_nonzero(labels_all & folds.fit)),
        "n_labels_search": int(np.count_nonzero(labels_all & folds.search)),
        "n_labels_select": int(np.count_nonzero(labels_all & folds.select)),
        "n_discriminating": int(np.count_nonzero(
            discriminating & usable & ~in_tile)),
        "n_discriminating_select": int(np.count_nonzero(
            discriminating & usable & folds.select)),
        "labels_cleanable_fraction": labels_cleanable,
        "cargo_cleanable_fraction": float(
            np.count_nonzero(cargo_cells & frame.siblings)
            / max(1, np.count_nonzero(cargo_cells))),
        "n_cargo_observed": int(np.count_nonzero(cargo_cells)),
    }
    for fold_name in ("search", "select"):
        mask = labels_all & folds.mask(fold_name) & covered
        detail[f"heldout_logloss_{fold_name}"] = (
            float(cal._logloss(llr[mask], values[mask].astype(np.float64)))
            if int(np.count_nonzero(mask)) >= pava.CAL_MIN_HELDOUT else None)
    rows = np.flatnonzero(labels_all & folds.select & covered)
    detail["label_rows"] = rows
    detail["label_values"] = values[rows].astype(np.uint8)
    detail["label_llr"] = llr[rows]
    detail["label_discriminating"] = discriminating[rows]
    detail["label_state"] = np.asarray(state, np.int8)[rows]
    return detail

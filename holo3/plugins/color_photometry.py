"""A3 — per-window photometric gain/offset maps.

Ported from src/holo/receive/color_locality.py (policy token
``winphot-gainoffset-adaptivehalo-shrink20``, RECEIVE-DESIGN §6.2a).
Colour photometry is per-REGION (one QDA per page) while K's has been
per-WINDOW since detect.fit_calibration; the map is the smallest
correction expressing "this window's photometry is offset from the
region's", ``x'_c = g_c * x_c + o_c``, six parameters per window, fitted
by weighted least squares toward the incumbent region QDA's class means.

Constants and their provenance, all from COLOR-UPLIFT-MEASUREMENTS:

* ``WINDOW_PHOT_PRIOR_LABELS = 20.0`` — the shrinkage prior in effective
  labels; best on-grid point of PK4's nine-point halo x prior sweep
  inside the winning halo row (+17 / +15 / +12 addresses for 20 / 40 /
  80, §5.2), re-confirmed on the adaptive-halo landscape (§6.2).
* ``WINDOW_PHOT_HALO_POOL_WEIGHT = 1.0`` — not swept.  PK4.1 measured the
  halo axis monotone against pooling (row means +14.7 / +9.0 / +5.7 for
  weights 0.25 / 0.5 / 1.0, own-window-only +27), so the halo became a
  STARVATION FALLBACK rather than a standing prior: a window that cannot
  see enough of itself has no basis for discounting what it can.
* ``WINDOW_PHOT_MIN_SEARCH_LABELS = 40`` / ``MIN_STATES = 3`` /
  ``MIN_HELDOUT = 20`` — K's refusal vocabulary verbatim
  (detect.fit_calibration).  Three states because six parameters are not
  identifiable from two class means.
* ``WINDOW_PHOT_GATE_SLACK = 1e-9`` — the standing strict-improvement
  convention.
* ``WINDOW_PHOT_MIN_VARIANCE = 1e-12`` — below it a channel carries no
  slope information and the regression takes its exact pure-offset limit.

There is NO region applicability floor.  PK4.1 and PK4.2 built two
(raw map dispersion; its Huber-White variance-ratio successor), measured
both on all 27 lanes of two captures, and neither separates the lanes A3
helps from the lanes it taxes — the requirement is contradictory by 15x
(refusing every harm lane needs > 31.1, keeping every help lane needs
<= 2.09).  Both are RETIRED at v0.52 and SCHEDULING is the applicability
answer: the arm is unreachable from the standard ladder and runs only in
its supplemental residue row, where the per-address retirement law makes
it monotone by construction.

Kind-agnostic: the map transforms RGB features, so cmy7 and cmy8 run the
identical code.  Deterministic and RNG-free.

NOT ported: v1's ``cert_population_preview`` (the P6 report-only preview
of the region gate scored on certified cells).  It gates nothing and
costs two QDA scorings over up to 250k cells per region.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.special import logsumexp

from ..data import WindowRows
from ..lib.pava import class_balanced_weights
from .color_model import QdaModel, qda_log_scores

if TYPE_CHECKING:
    from .color_region import OwnerSelection

WINDOW_PHOT_PRIOR_LABELS: float = 20.0
WINDOW_PHOT_HALO_POOL_WEIGHT: float = 1.0
WINDOW_PHOT_MIN_SEARCH_LABELS: int = 40
WINDOW_PHOT_MIN_STATES: int = 3
WINDOW_PHOT_MIN_HELDOUT: int = 20
WINDOW_PHOT_GATE_SLACK: float = 1e-9
WINDOW_PHOT_MIN_VARIANCE: float = 1e-12

REASON_ADOPTED: str = "adopted"
REASON_SEARCH_STARVED: str = "search_class_starved"
REASON_STATE_SUPPORT: str = "insufficient_search_support"
REASON_HELDOUT_STARVED: str = "heldout_starved"
REASON_GATE_FAILED: str = "validation_gate_failed"
REASON_NO_WINDOW_MAPS: str = "no_window_maps"
REASON_REGION_GATE_FAILED: str = "region_gate_failed"


@dataclass(frozen=True)
class WindowPhotometryConfig:
    prior_labels: float = WINDOW_PHOT_PRIOR_LABELS

    def __post_init__(self) -> None:
        prior = float(self.prior_labels)
        if not np.isfinite(prior) or prior <= 0.0:
            raise ValueError(
                "color window photometry: prior labels must be positive")
        object.__setattr__(self, "prior_labels", prior)


@dataclass(frozen=True)
class WindowMap:
    gains: np.ndarray
    offsets: np.ndarray

    def apply(self, features: np.ndarray) -> np.ndarray:
        values = np.asarray(features, np.float64)
        if values.ndim != 2 or values.shape[1] != self.gains.size:
            raise ValueError(
                "color window photometry: features must have shape (N, C)")
        return values * self.gains + self.offsets


@dataclass(frozen=True)
class WindowMapFit:
    ordinal: int
    window_map: WindowMap | None
    reason: str
    n_own: int
    n_halo: int
    n_states: int
    n_heldout: int
    n_effective: float
    identity_nll: float | None
    candidate_nll: float | None

    @property
    def accepted(self) -> bool:
        return self.window_map is not None

    @property
    def pooled(self) -> bool:
        return self.n_halo > 0


@dataclass(frozen=True)
class WindowPhotometryResult:
    features: tuple[np.ndarray, ...]
    fits: tuple[WindowMapFit, ...]
    accepted: int
    refused: int
    pooled: int
    reasons: tuple[tuple[str, int], ...]
    arm_reason: str


def window_bboxes(row_tuple: tuple[WindowRows, ...]) -> np.ndarray:
    bounds = np.empty((len(row_tuple), 4), np.int64)
    for index, rows in enumerate(row_tuple):
        cells = np.asarray(rows.page_cells_yx, np.int64)
        if cells.size == 0:
            bounds[index] = (0, -1, 0, -1)
            continue
        bounds[index] = (
            cells[:, 0].min(), cells[:, 0].max(),
            cells[:, 1].min(), cells[:, 1].max())
    return bounds


def halo_membership(bounds: np.ndarray) -> np.ndarray:
    empty = bounds[:, 1] < bounds[:, 0]
    height = bounds[:, 1] - bounds[:, 0]
    width = bounds[:, 3] - bounds[:, 2]
    y0 = bounds[:, 0] - height
    y1 = bounds[:, 1] + height
    x0 = bounds[:, 2] - width
    x1 = bounds[:, 3] + width
    overlap = (
        (bounds[None, :, 0] <= y1[:, None])
        & (bounds[None, :, 1] >= y0[:, None])
        & (bounds[None, :, 2] <= x1[:, None])
        & (bounds[None, :, 3] >= x0[:, None])
    )
    overlap &= ~empty[:, None]
    overlap &= ~empty[None, :]
    np.fill_diagonal(overlap, False)
    return overlap


def balanced_base_weights(states: np.ndarray,
                          base: np.ndarray) -> np.ndarray:
    labels = np.asarray(states, np.int64)
    mass = np.bincount(
        labels, weights=np.asarray(base, np.float64),
        minlength=int(labels.max(initial=-1)) + 1)
    per_row = np.where(
        mass[labels] > 0.0, base / np.where(mass[labels] > 0.0,
                                            mass[labels], 1.0), 0.0)
    total = float(per_row.sum())
    if total <= 0.0:
        return np.zeros(labels.size, np.float64)
    return per_row * (float(np.sum(base)) / total)


def weighted_affine(features: np.ndarray, targets: np.ndarray,
                    weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    total = float(np.sum(weights))
    mean_x = (weights @ features) / total
    mean_t = (weights @ targets) / total
    var_x = (weights @ (features * features)) / total - mean_x * mean_x
    cov_xt = (weights @ (features * targets)) / total - mean_x * mean_t
    informative = var_x > WINDOW_PHOT_MIN_VARIANCE
    gains = np.where(
        informative,
        cov_xt / np.where(informative, var_x, 1.0),
        1.0)
    offsets = mean_t - gains * mean_x
    return gains, offsets


def balanced_nll(model: QdaModel, features: np.ndarray,
                 states: np.ndarray, weights: np.ndarray) -> float:
    scores = qda_log_scores(model, features)
    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    chosen = normalized[np.arange(states.size), states]
    return float(-np.sum(weights * chosen) / float(np.sum(weights)))


def _fit_one_window(model: QdaModel, config: WindowPhotometryConfig,
                    ordinal: int, known: np.ndarray, targets: np.ndarray,
                    states: np.ndarray, own_search: np.ndarray,
                    own_heldout: np.ndarray,
                    halo: np.ndarray) -> WindowMapFit:
    n_heldout = int(np.count_nonzero(own_heldout))

    def represented(rows: np.ndarray) -> np.ndarray:
        return np.unique(states[rows])

    def identifiable(present: np.ndarray) -> bool:
        return bool(
            present.size >= WINDOW_PHOT_MIN_STATES
            and np.count_nonzero(present > 0) >= 2
            and np.any(present == 0))

    own_present = represented(own_search)
    n_own = int(np.count_nonzero(own_search))
    if n_own >= WINDOW_PHOT_MIN_SEARCH_LABELS and identifiable(own_present):
        fit_rows, present, n_halo = own_search, own_present, 0
    else:
        fit_rows = own_search | halo
        present = represented(fit_rows)
        n_halo = int(np.count_nonzero(halo))
    n_states = int(present.size)

    def refused(reason: str, n_effective: float = 0.0) -> WindowMapFit:
        return WindowMapFit(
            ordinal=ordinal, window_map=None, reason=reason, n_own=n_own,
            n_halo=n_halo, n_states=n_states, n_heldout=n_heldout,
            n_effective=n_effective, identity_nll=None, candidate_nll=None)

    if n_own + n_halo < WINDOW_PHOT_MIN_SEARCH_LABELS:
        return refused(REASON_SEARCH_STARVED)
    if not identifiable(present):
        return refused(REASON_STATE_SUPPORT)
    if n_heldout < WINDOW_PHOT_MIN_HELDOUT:
        return refused(REASON_HELDOUT_STARVED)

    fit_states = states[fit_rows]
    base = np.where(
        own_search[fit_rows], 1.0, WINDOW_PHOT_HALO_POOL_WEIGHT)
    weights = balanced_base_weights(fit_states, base)
    n_effective = float(np.sum(base))
    gains, offsets = weighted_affine(
        known[fit_rows], targets[fit_rows], weights)
    denominator = n_effective + config.prior_labels
    gains = (n_effective * gains + config.prior_labels) / denominator
    offsets = n_effective * offsets / denominator
    candidate = WindowMap(
        np.ascontiguousarray(gains, np.float64),
        np.ascontiguousarray(offsets, np.float64))

    heldout_states = states[own_heldout]
    heldout_weights = class_balanced_weights(heldout_states)
    heldout_features = known[own_heldout]
    identity_nll = balanced_nll(
        model, heldout_features, heldout_states, heldout_weights)
    candidate_nll = balanced_nll(
        model, candidate.apply(heldout_features), heldout_states,
        heldout_weights)
    accepted = identity_nll - candidate_nll > WINDOW_PHOT_GATE_SLACK
    return WindowMapFit(
        ordinal=ordinal,
        window_map=candidate if accepted else None,
        reason=REASON_ADOPTED if accepted else REASON_GATE_FAILED,
        n_own=n_own, n_halo=n_halo, n_states=n_states,
        n_heldout=n_heldout, n_effective=n_effective,
        identity_nll=identity_nll, candidate_nll=candidate_nll)


def fit_window_photometry(
    model: QdaModel,
    selection: OwnerSelection,
    row_tuple: tuple[WindowRows, ...],
    features: tuple[np.ndarray, ...],
    config: WindowPhotometryConfig,
) -> WindowPhotometryResult:
    if len(features) != len(row_tuple):
        raise ValueError(
            "color window photometry: one feature array per window row")
    means = np.asarray(model.means, np.float64)
    known = selection.gather(features)
    states = np.asarray(selection.states, np.int64)
    ordinals = np.asarray(selection.window_ordinals, np.int64)
    search = np.asarray(selection.search, np.bool_)
    halo_of = halo_membership(window_bboxes(row_tuple))
    targets = means[states]

    own_of = [ordinals == ordinal for ordinal in range(len(row_tuple))]
    fits = [
        _fit_one_window(
            model, config, ordinal, known, targets, states,
            own & search, own & ~search,
            halo_of[ordinal][ordinals] & search & ~own)
        for ordinal, own in enumerate(own_of)
    ]
    accepted = sum(1 for fit in fits if fit.accepted)
    counts: dict[str, int] = {}
    for fit in fits:
        counts[fit.reason] = counts.get(fit.reason, 0) + 1
    arm_reason = "" if accepted else REASON_NO_WINDOW_MAPS
    mapped = features
    if not arm_reason:
        rows = list(features)
        for fit in fits:
            if fit.window_map is not None:
                rows[fit.ordinal] = fit.window_map.apply(
                    features[fit.ordinal])
        mapped = tuple(rows)
    return WindowPhotometryResult(
        features=mapped,
        fits=tuple(fits),
        accepted=accepted,
        refused=len(fits) - accepted,
        pooled=sum(1 for fit in fits if fit.pooled),
        reasons=tuple(sorted(counts.items())),
        arm_reason=arm_reason,
    )

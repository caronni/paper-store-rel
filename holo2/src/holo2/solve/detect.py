"""Qualified E023/E023b photometric calibration.

CARRIED VERBATIM (holo2 firewall: copy-and-adapt, never import) from
``src/holo/receive/detect.py``.  Zero numeric change: every executable
line is the original, pinned character for character by
``tests/holo2_oracles/test_oracle_tiles.py``.  What holo2 changes is the SCOPE
framework around it (DESIGN §8.4) — which label population one fit may
see — never the fit itself; the explicit window/region identity arguments
are exactly the seam that makes those scopes checkable.

This module is the numerical evidence boundary of the receiver.  It owns no
image sampling, placement, page addressing, or payload descrambling.  Its two
algorithms are deliberately small and historically pinned:

* ``pava-v1`` is the exact, unweighted ``paperholo.acquire`` stack-PAVA map,
  fitted on one window's SEARCH-parity labels and evaluated on a disjoint
  HELDOUT-parity population.  A window either has the registered support or
  refuses; raw detector scores never cross this boundary as evidence.
* ``ctx-pava-v1`` is E023b's nine-bin ordered additive-logit correction.  It
  is fitted and held-out gated per region, gives duplicate observations of a
  physical label total weight one, and leaves the marginal evidence exactly
  untouched unless held-out log-loss strictly improves.

The explicit window/region identities are load-bearing.  They prevent an
orchestrator from accidentally pooling marginal labels across windows or
context labels across regions, and make split leakage checkable here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


# Frozen E023 marginal-calibration bars.  The held-out bar is a total count,
# exactly as in payloaddec._emit_window_from_means; the SEARCH bar is per
# class because a one-sided population cannot identify a probability map.
CAL_MIN_PER_CLASS = 10
CAL_MIN_HELDOUT = 10

# Frozen ctx-pava-v1 constants from E023b.1.
N_CONTEXT_BINS = 9
CTX_OFFSET_LIMIT = 4.0
CTX_LLR_CLAMP = 12.0
CTX_BIN_PRIOR = 1.0
CTX_MIN_SEARCH = 80
CTX_MIN_SEARCH_PER_CLASS = 20
CTX_MIN_VALIDATION = 40
CTX_MIN_VALIDATION_PER_CLASS = 10
CTX_ROOT_TOL = 1e-12


def readonly_array(array: np.ndarray, dtype: np.dtype | type) -> np.ndarray:
    """THE owned read-only C-contiguous array copy (one shared idiom)."""
    out = np.array(array, dtype=dtype, copy=True, order="C")
    out.setflags(write=False)
    return out


def _identity(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"detect: {name} must be a non-empty string")
    return value


def _binary(values: np.ndarray, name: str) -> np.ndarray:
    raw = np.asarray(values).ravel()
    try:
        legal = (raw == 0) | (raw == 1)
    except (TypeError, ValueError):
        legal = np.zeros(raw.shape, dtype=bool)
    if not bool(np.all(legal)):
        raise ValueError(f"detect: {name} must contain only 0/1 labels")
    return raw.astype(bool)


def _site_ids(values: np.ndarray, size: int, name: str,
              *, unique: bool) -> np.ndarray:
    raw = np.asarray(values).ravel()
    if not np.issubdtype(raw.dtype, np.integer):
        raise ValueError(f"detect: {name} must be integer identities")
    out = raw.astype(np.int64)
    if out.size != size:
        raise ValueError(f"detect: {name} length mismatch")
    if unique and np.unique(out).size != out.size:
        raise ValueError(f"detect: {name} contains duplicate physical labels")
    return out


@dataclass(frozen=True)
class CalibrationObservations:
    """One population of labels belonging to exactly one detector window.

    Marginal PAVA is intentionally unweighted.  A physical label may occur
    only once in each population, and SEARCH/HELDOUT disjointness is checked
    by :func:`fit_calibration`.
    """

    window_id: str
    scores: np.ndarray
    labels: np.ndarray
    site_ids: np.ndarray

    def __post_init__(self) -> None:
        window_id = _identity(self.window_id, "window_id")
        scores = np.asarray(self.scores, dtype=np.float64).ravel()
        labels = _binary(self.labels, "calibration labels")
        if scores.size != labels.size:
            raise ValueError("detect: calibration scores/labels length mismatch")
        if not np.isfinite(scores).all():
            raise ValueError("detect: calibration scores must be finite")
        ids = _site_ids(self.site_ids, scores.size, "calibration site_ids",
                        unique=True)
        object.__setattr__(self, "window_id", window_id)
        object.__setattr__(self, "scores", readonly_array(scores, np.float64))
        object.__setattr__(self, "labels", readonly_array(labels, np.bool_))
        object.__setattr__(self, "site_ids", readonly_array(ids, np.int64))

    @property
    def class_support(self) -> tuple[int, int]:
        n1 = int(self.labels.sum())
        return int(self.labels.size - n1), n1


def clamp_for(n_search_labels: int) -> float:
    """Natural PAVA bound ``log(n + 1)`` from ``pmin=1/(n+2)``."""
    if (isinstance(n_search_labels, (bool, np.bool_))
            or int(n_search_labels) != n_search_labels
            or n_search_labels < 1):
        raise ValueError("detect: n_search_labels must be a positive integer")
    return float(np.log1p(int(n_search_labels)))


@dataclass(frozen=True)
class Calibration:
    """Immutable exact ``pava-v1`` score -> P(ink) map for one window."""

    window_id: str
    knots: np.ndarray
    probabilities: np.ndarray
    n_search: int

    def __post_init__(self) -> None:
        window_id = _identity(self.window_id, "window_id")
        knots = np.asarray(self.knots, dtype=np.float64).ravel()
        probs = np.asarray(self.probabilities, dtype=np.float64).ravel()
        if knots.size == 0 or knots.size != probs.size:
            raise ValueError("detect: calibration nodes must be equally non-empty")
        if not np.isfinite(knots).all() or not np.isfinite(probs).all():
            raise ValueError("detect: calibration nodes must be finite")
        # Equal knots are possible and meaningful under the historical stable
        # tie order.  np.interp's rightmost equal-knot behaviour is part of
        # the old apply_calibration result and is preserved.
        if knots.size > 1 and np.any(np.diff(knots) < 0):
            raise ValueError("detect: calibration knots must be non-decreasing")
        if probs.size > 1 and np.any(np.diff(probs) < -1e-12):
            raise ValueError("detect: calibration probabilities must be monotone")
        if (isinstance(self.n_search, (bool, np.bool_))
                or int(self.n_search) != self.n_search or self.n_search < 1):
            raise ValueError("detect: n_search must be a positive integer")
        pmin = 1.0 / (int(self.n_search) + 2.0)
        if np.any(probs < pmin - 1e-15) or np.any(probs > 1.0 - pmin + 1e-15):
            raise ValueError("detect: calibration probability exceeds PAVA support")
        object.__setattr__(self, "window_id", window_id)
        object.__setattr__(self, "knots", readonly_array(knots, np.float64))
        object.__setattr__(self, "probabilities", readonly_array(probs, np.float64))

    def probability(self, scores: np.ndarray) -> np.ndarray:
        raw = np.asarray(scores, dtype=np.float64)
        if not np.isfinite(raw).all():
            raise ValueError("detect: scores presented for calibration must be finite")
        return np.interp(raw, self.knots, self.probabilities)

    def llr(self, scores: np.ndarray) -> np.ndarray:
        """Exact historical ``apply_calibration`` interpolation/logit."""
        p = self.probability(scores)
        return np.log(p / (1.0 - p))


@dataclass(frozen=True)
class CalibrationFit:
    """Marginal fit/refusal and its disjoint held-out diagnostic."""

    window_id: str
    calibration: Calibration | None
    accepted: bool
    reason: str
    n_search: int
    n_search_0: int
    n_search_1: int
    n_heldout: int
    heldout_logloss: float | None

    def __post_init__(self) -> None:
        _identity(self.window_id, "window_id")
        if self.accepted != (self.calibration is not None):
            raise ValueError("detect: calibration acceptance is inconsistent")
        if self.calibration is not None and self.calibration.window_id != self.window_id:
            raise ValueError("detect: calibration/window identity mismatch")
        if not self.reason:
            raise ValueError("detect: calibration reason must not be empty")
        if min(self.n_search, self.n_search_0, self.n_search_1,
               self.n_heldout) < 0:
            raise ValueError("detect: calibration counts must be non-negative")
        if self.n_search != self.n_search_0 + self.n_search_1:
            raise ValueError("detect: calibration class counts do not add up")
        loss = (None if self.heldout_logloss is None
                else float(self.heldout_logloss))
        if loss is not None and (not np.isfinite(loss) or loss < 0.0):
            raise ValueError(
                "detect: held-out loss must be finite and non-negative")
        if self.accepted:
            if loss is None:
                raise ValueError("detect: accepted fit needs held-out loss")
        object.__setattr__(self, "heldout_logloss", loss)


def _pava_nodes(scores: np.ndarray,
                labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact ``paperholo.acquire.pava_calibrate`` implementation."""
    s = np.asarray(scores, np.float64).ravel()
    y = np.asarray(labels, np.float64).ravel()
    order = np.argsort(s, kind="stable")
    s, y = s[order], y[order]
    vals: list[float] = []
    wts: list[float] = []
    for value in y:
        vals.append(float(value))
        wts.append(1.0)
        while len(vals) > 1 and vals[-2] >= vals[-1]:
            weight = wts[-1] + wts[-2]
            vals[-2] = (
                vals[-1] * wts[-1] + vals[-2] * wts[-2]) / weight
            wts[-2] = weight
            vals.pop()
            wts.pop()
    nodes_s = np.empty(len(vals))
    nodes_p = np.empty(len(vals))
    start = 0
    pmin = 1.0 / (s.size + 2.0)
    for index, (value, weight) in enumerate(zip(vals, wts)):
        stop = start + int(round(weight))
        nodes_s[index] = s[start:min(stop, s.size)].mean()
        nodes_p[index] = min(max(value, pmin), 1.0 - pmin)
        start = stop
    return nodes_s, nodes_p


def fit_calibration(search: CalibrationObservations,
                    heldout: CalibrationObservations) -> CalibrationFit:
    """Fit exact per-window PAVA or explicitly refuse.

    HELDOUT is never used to fit or gate quality; its registered role is
    ownership/honesty.  It must nevertheless have at least ten labels before
    the marginal evidence is accepted, matching E023.
    """
    if not isinstance(search, CalibrationObservations) or not isinstance(
            heldout, CalibrationObservations):
        raise TypeError("detect: fit_calibration requires window observations")
    if search.window_id != heldout.window_id:
        raise ValueError("detect: calibration populations name different windows")
    if np.intersect1d(search.site_ids, heldout.site_ids).size:
        raise ValueError("detect: calibration SEARCH/HELDOUT site ids overlap")
    n0, n1 = search.class_support
    common = dict(window_id=search.window_id, n_search=search.labels.size,
                  n_search_0=n0, n_search_1=n1,
                  n_heldout=heldout.labels.size)
    if min(n0, n1) < CAL_MIN_PER_CLASS:
        return CalibrationFit(
            calibration=None, accepted=False, reason="search_class_starved",
            heldout_logloss=None, **common)
    if heldout.labels.size < CAL_MIN_HELDOUT:
        return CalibrationFit(
            calibration=None, accepted=False, reason="heldout_starved",
            heldout_logloss=None, **common)
    knots, probabilities = _pava_nodes(search.scores, search.labels)
    calibration = Calibration(search.window_id, knots, probabilities,
                              int(search.labels.size))
    heldout_loss = _logloss(calibration.llr(heldout.scores).astype(np.float64),
                            heldout.labels,
                            np.ones(heldout.labels.size, np.float64))
    return CalibrationFit(
        calibration=calibration, accepted=True, reason="accepted",
        heldout_logloss=heldout_loss, **common)


def context_neighbour_counts(
    page_cells_yx: np.ndarray,
    provisional_ink: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Eight-neighbour ink counts and complete-neighbourhood validity."""
    cells = np.asarray(page_cells_yx)
    if (cells.ndim != 2 or cells.shape[1] != 2
            or not np.issubdtype(cells.dtype, np.integer)):
        raise ValueError("detect: page_cells_yx must have integer shape (N,2)")
    cells = cells.astype(np.int64, copy=False)
    ink = _binary(provisional_ink, "provisional_ink")
    if ink.size != cells.shape[0]:
        raise ValueError("detect: provisional_ink must align with page cells")
    if cells.shape[0] == 0:
        return np.zeros(0, np.int8), np.zeros(0, bool)
    if np.unique(cells, axis=0).shape[0] != cells.shape[0]:
        raise ValueError("detect: page_cells_yx contains duplicate cells")
    # This is the exact E023b dense-grid convolution, not a Python per-cell
    # neighbour walk.  Authoritative cores are dense window patches, making
    # the temporary bounding grid both smaller and materially faster.
    lo = cells.min(axis=0)
    local = cells - lo
    shape = tuple((local.max(axis=0) + 1).astype(int))
    present = np.zeros(shape, np.uint8)
    ink_grid = np.zeros(shape, np.uint8)
    present[local[:, 0], local[:, 1]] = 1
    ink_grid[local[:, 0], local[:, 1]] = ink.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    neighbours_present = ndimage.convolve(
        present, kernel, mode="constant", cval=0)
    neighbours_ink = ndimage.convolve(
        ink_grid, kernel, mode="constant", cval=0)
    row_y, row_x = local[:, 0], local[:, 1]
    return (neighbours_ink[row_y, row_x].astype(np.int8),
            neighbours_present[row_y, row_x] == 8)


def context_bins(counts: np.ndarray, *, valid: np.ndarray | None = None
                 ) -> np.ndarray:
    """Exact E023b indices 0..8; invalid cells are represented by -1."""
    raw = np.asarray(counts)
    if np.issubdtype(raw.dtype, np.floating):
        finite = np.isfinite(raw)
        rounded = np.rint(np.where(finite, raw, -1))
        if np.any(finite & (rounded != raw)):
            raise ValueError("detect: context counts must be integers")
        raw = rounded
    try:
        out = raw.astype(np.int64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("detect: context counts must be integers") from exc
    invalid = out == -1
    if np.any((out < -1) | (out > 8)):
        raise ValueError("detect: context counts must lie in 0..8 or be -1")
    if valid is not None:
        mask = np.asarray(valid, dtype=bool)
        if mask.shape != out.shape:
            raise ValueError("detect: context validity shape mismatch")
        invalid |= ~mask
    return np.where(invalid, -1, out).astype(np.int8)


@dataclass(frozen=True)
class ContextObservations:
    """One side of an explicit E023b region SEARCH/VALIDATION split."""

    region_id: str
    baseline_llr: np.ndarray
    neighbour_count: np.ndarray
    labels: np.ndarray
    site_ids: np.ndarray

    def __post_init__(self) -> None:
        region_id = _identity(self.region_id, "region_id")
        llr = np.asarray(self.baseline_llr, dtype=np.float64).ravel()
        count = context_bins(self.neighbour_count).astype(np.int8)
        labels = _binary(self.labels, "context labels")
        ids = _site_ids(self.site_ids, llr.size, "context site_ids",
                        unique=False)
        if not (llr.size == count.size == labels.size):
            raise ValueError("detect: context observation arrays must align")
        if llr.size == 0:
            raise ValueError("detect: context observations must not be empty")
        if not np.isfinite(llr).all():
            raise ValueError("detect: context baseline LLRs must be finite")
        if np.any(count < 0):
            raise ValueError("detect: context fit observations must be valid")
        order = np.argsort(ids, kind="stable")
        sorted_ids = ids[order]
        starts = np.flatnonzero(np.r_[True, sorted_ids[1:] != sorted_ids[:-1]])
        for start, stop in zip(starts, np.r_[starts[1:], ids.size]):
            if np.any(labels[order[start:stop]] != labels[order[start]]):
                raise ValueError(
                    "detect: one physical context site has conflicting labels")
        object.__setattr__(self, "region_id", region_id)
        object.__setattr__(self, "baseline_llr", readonly_array(llr, np.float64))
        object.__setattr__(self, "neighbour_count", readonly_array(count, np.int8))
        object.__setattr__(self, "labels", readonly_array(labels, np.bool_))
        object.__setattr__(self, "site_ids", readonly_array(ids, np.int64))

    @property
    def weights(self) -> np.ndarray:
        _, inverse, multiplicity = np.unique(
            self.site_ids, return_inverse=True, return_counts=True)
        return 1.0 / multiplicity[inverse].astype(np.float64)

    @property
    def unique_class_support(self) -> tuple[int, int]:
        _, first = np.unique(self.site_ids, return_index=True)
        labels = self.labels[first]
        n1 = int(labels.sum())
        return int(labels.size - n1), n1


def _logloss(llr: np.ndarray, labels: np.ndarray,
             weights: np.ndarray) -> float:
    signed = np.where(labels, -llr, llr)
    losses = np.logaddexp(0.0, signed)
    return float(np.sum(weights * losses) / np.sum(weights))


def _solve_offset(llr: np.ndarray, labels: np.ndarray,
                  weights: np.ndarray) -> float:
    """Clipped additive-logit optimum for one context block.

    The inner two-branch sigmoid (``1/(1+exp(-x))`` for ``x >= 0``,
    ``exp(x)/(1+exp(x))`` otherwise) is the PROJECT-CANONICAL sigmoid
    (v0.39 ruling 10.3, finding detect-k:06). It is NOT bit-identical to
    ``scipy.special.expit``: measured on scipy 1.18.0 / numpy 2.5.1 the
    two agree exactly for all ``x >= 0`` but differ on ~45% of negative
    inputs by 1–3 ulp of the probability (expit routes through a different
    kernel). This does not matter numerically — the offset returned here
    is resolved through a fixed-tolerance bisection (CTX_ROOT_TOL = 1e-12),
    which masks ulp-level probability differences — but it IS a bit-level
    divergence from legacy paperholo, whose ``payloaddec.py`` used scipy
    ``expit`` for the same block solve. The two-branch form is canonical
    by fiat: every receive path, in every encoding, that needs a sigmoid
    must use this form (there is exactly one sigmoid site in ``src/holo``
    — this function; color lanes use QDA/logsumexp, not a sigmoid), and
    no ``scipy.special.expit`` import may appear in ``src/holo``.
    Pinned by ``tests/holo/test_canonical_sigmoid.py``.
    """
    target = float(np.sum(weights * labels))

    def derivative(offset: float) -> float:
        x = llr + offset
        probability = np.empty_like(x)
        positive = x >= 0
        probability[positive] = 1.0 / (1.0 + np.exp(-x[positive]))
        ex = np.exp(x[~positive])
        probability[~positive] = ex / (1.0 + ex)
        return float(np.sum(weights * probability) - target)

    lo, hi = -CTX_OFFSET_LIMIT, CTX_OFFSET_LIMIT
    if derivative(lo) >= 0.0:
        return lo
    if derivative(hi) <= 0.0:
        return hi
    if derivative(0.0) == 0.0:
        return 0.0
    while hi - lo > CTX_ROOT_TOL:
        mid = (lo + hi) * 0.5
        if derivative(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def _ordered_context_offsets(observations: ContextObservations) -> np.ndarray:
    """Exact generalized-PAVA ordered-logit fit from E023b.1."""
    blocks: list[dict[str, object]] = []
    observation_weights = observations.weights
    for bin_index in range(N_CONTEXT_BINS):
        select = observations.neighbour_count == bin_index
        logits = np.concatenate(
            (observations.baseline_llr[select], np.array([0.0, 0.0])))
        labels = np.concatenate(
            (observations.labels[select], np.array([False, True])))
        weights = np.concatenate(
            (observation_weights[select],
             np.full(2, CTX_BIN_PRIOR, dtype=np.float64)))
        blocks.append({
            "bins": [bin_index], "llr": logits, "labels": labels,
            "weights": weights,
            "offset": _solve_offset(logits, labels, weights),
        })
        while (len(blocks) >= 2
               and float(blocks[-2]["offset"]) < float(blocks[-1]["offset"])):
            right = blocks.pop()
            left = blocks.pop()
            logits = np.concatenate((left["llr"], right["llr"]))  # type: ignore[arg-type]
            labels = np.concatenate((left["labels"], right["labels"]))  # type: ignore[arg-type]
            weights = np.concatenate((left["weights"], right["weights"]))  # type: ignore[arg-type]
            blocks.append({
                "bins": list(left["bins"]) + list(right["bins"]),  # type: ignore[arg-type]
                "llr": logits, "labels": labels, "weights": weights,
                "offset": _solve_offset(logits, labels, weights),
            })
    offsets = np.empty(N_CONTEXT_BINS, dtype=np.float64)
    for block in blocks:
        offsets[np.asarray(block["bins"], dtype=np.int64)] = float(
            block["offset"])
    return offsets


@dataclass(frozen=True)
class ContextFit:
    """Eligibility/adoption result for exactly one context region."""

    region_id: str
    eligible: bool
    adopted: bool
    reason: str
    offsets: np.ndarray
    search_support_by_bin: np.ndarray
    validation_support_by_bin: np.ndarray
    search_observations_by_bin: np.ndarray
    validation_observations_by_bin: np.ndarray
    n_search: int
    n_search_0: int
    n_search_1: int
    n_search_observations: int
    n_validation: int
    n_validation_0: int
    n_validation_1: int
    n_validation_observations: int
    baseline_validation_logloss: float | None
    candidate_validation_logloss: float | None

    def __post_init__(self) -> None:
        _identity(self.region_id, "region_id")
        offsets = np.asarray(self.offsets, dtype=np.float64).ravel()
        if offsets.shape != (N_CONTEXT_BINS,) or not np.isfinite(offsets).all():
            raise ValueError("detect: context offsets must be nine finite values")
        if np.max(np.abs(offsets), initial=0.0) > CTX_OFFSET_LIMIT + 1e-10:
            raise ValueError("detect: context offset exceeds registered bound")
        if np.any(np.diff(offsets) > 1e-10):
            raise ValueError("detect: context offsets must be non-increasing")
        for name, dtype in (
            ("search_support_by_bin", np.float64),
            ("validation_support_by_bin", np.float64),
            ("search_observations_by_bin", np.int64),
            ("validation_observations_by_bin", np.int64),
        ):
            value = np.asarray(getattr(self, name), dtype=dtype).ravel()
            if value.shape != (N_CONTEXT_BINS,) or np.any(value < 0):
                raise ValueError(f"detect: {name} must be nine non-negative values")
            object.__setattr__(self, name, readonly_array(value, dtype))
        object.__setattr__(self, "offsets", readonly_array(offsets, np.float64))
        for name in ("baseline_validation_logloss",
                     "candidate_validation_logloss"):
            value = getattr(self, name)
            if value is not None:
                loss = float(value)
                if not np.isfinite(loss) or loss < 0.0:
                    raise ValueError(
                        "detect: context loss must be finite and non-negative")
                object.__setattr__(self, name, loss)
        if self.adopted and not self.eligible:
            raise ValueError("detect: an ineligible context fit cannot be adopted")
        if self.adopted and not (
                self.candidate_validation_logloss
                < self.baseline_validation_logloss):  # type: ignore[operator]
            raise ValueError("detect: adopted context must improve held-out loss")

def apply_context_offsets(
    llr: np.ndarray,
    bins: np.ndarray,
    offsets: np.ndarray,
) -> np.ndarray:
    """Clamped per-bin context correction — the one shared clip kernel.

    ``bins`` uses -1 for cells without a valid context neighbourhood; those
    cells keep their marginal LLR unchanged.  Returns a fresh float64 array.
    """
    out = np.array(llr, dtype=np.float64, copy=True)
    valid = bins >= 0
    out[valid] = np.clip(
        out[valid] + offsets[bins[valid]],
        -CTX_LLR_CLAMP, CTX_LLR_CLAMP)
    return out


def fit_context(search: ContextObservations,
                validation: ContextObservations) -> ContextFit:
    """Fit and strictly held-out-gate the registered ctx-pava-v1 arm."""
    if search.region_id != validation.region_id:
        raise ValueError("detect: context populations name different regions")
    if np.intersect1d(search.site_ids, validation.site_ids).size:
        raise ValueError("detect: context SEARCH/VALIDATION site ids overlap")
    search_w = search.weights
    validation_w = validation.weights
    search_support = np.bincount(
        search.neighbour_count, weights=search_w,
        minlength=N_CONTEXT_BINS)[:N_CONTEXT_BINS]
    validation_support = np.bincount(
        validation.neighbour_count, weights=validation_w,
        minlength=N_CONTEXT_BINS)[:N_CONTEXT_BINS]
    search_observations = np.bincount(
        search.neighbour_count, minlength=N_CONTEXT_BINS)[:N_CONTEXT_BINS]
    validation_observations = np.bincount(
        validation.neighbour_count,
        minlength=N_CONTEXT_BINS)[:N_CONTEXT_BINS]
    n_s0, n_s1 = search.unique_class_support
    n_v0, n_v1 = validation.unique_class_support
    reason: str | None = None
    if n_s0 + n_s1 < CTX_MIN_SEARCH:
        reason = "insufficient_search_support"
    elif min(n_s0, n_s1) < CTX_MIN_SEARCH_PER_CLASS:
        reason = "search_class_starved"
    elif n_v0 + n_v1 < CTX_MIN_VALIDATION:
        reason = "insufficient_validation_support"
    elif min(n_v0, n_v1) < CTX_MIN_VALIDATION_PER_CLASS:
        reason = "validation_class_starved"
    common = dict(
        region_id=search.region_id,
        search_support_by_bin=search_support,
        validation_support_by_bin=validation_support,
        search_observations_by_bin=search_observations,
        validation_observations_by_bin=validation_observations,
        n_search=n_s0 + n_s1, n_search_0=n_s0, n_search_1=n_s1,
        n_search_observations=int(search.labels.size),
        n_validation=n_v0 + n_v1, n_validation_0=n_v0,
        n_validation_1=n_v1,
        n_validation_observations=int(validation.labels.size),
    )
    if reason is not None:
        return ContextFit(
            eligible=False, adopted=False, reason=reason,
            offsets=np.zeros(N_CONTEXT_BINS),
            baseline_validation_logloss=None,
            candidate_validation_logloss=None, **common)
    offsets = _ordered_context_offsets(search)
    baseline_loss = _logloss(
        validation.baseline_llr, validation.labels, validation_w)
    candidate_loss = _logloss(
        validation.baseline_llr + offsets[validation.neighbour_count],
        validation.labels, validation_w)
    adopted = candidate_loss < baseline_loss
    return ContextFit(
        eligible=True, adopted=adopted,
        reason="adopted" if adopted else "validation_gate_failed",
        offsets=offsets,
        baseline_validation_logloss=baseline_loss,
        candidate_validation_logloss=candidate_loss, **common)

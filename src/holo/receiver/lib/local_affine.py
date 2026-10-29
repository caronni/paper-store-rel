"""Per-plane local affine corrections, and the bounded search that finds
one.

The standing plane field (``lib/plane_field``) is a smoothed TRANSLATION
field: one delta per tile, pooled over a two-tile Gaussian, linearised
around the incumbent with half-dot probes and ridged toward zero.  That
shape is right for the smooth part of a plane's registration and wrong
for everything else — it under-recovers a large displacement (it fits a
linear model to a non-linear photometric response), it attenuates
anything sharper than its own bandwidth, and where evidence is thin it
answers exactly zero, which is honest but useless.

This module is the other half: over ONE window and ONE plane, the
correction is a full local affine in dots,

    d(u) = t + M u,     u in [-1, 1]^2, the cell's place in the window

six parameters, found by DIRECT SEARCH on an objective the caller
supplies — no linearisation, no shrinkage, no smoothing.  The search is
deterministic (a fixed candidate order, strict improvement to move, no
random draws), coarse-to-fine, and bounded.

Nothing here reads a clock, draws a random number, or touches a raster:
the caller samples and scores, this module proposes and descends.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# The linear term is bounded at HALF of the translation bound, so the
# worst corner of a window (both a full translation and both linear
# columns at their limit) stays inside one bound of the hint.  Neither
# number is a tuning knob: the caller derives the bound from the printed
# format's own cell (see plugins/swim.py).
LINEAR_BOUND_FRACTION: float = 0.5
# The coarse pass is a full grid over the bound; every later pass is the
# eight neighbours of the incumbent at half the previous step.
COARSE_STEPS_PER_SIDE: int = 2
N_LINEAR_TERMS: int = 4


@dataclass(frozen=True)
class Affine:
    """One plane's correction over one window, in printed dots.

    ``translation`` is (dx, dy); ``linear`` is the 2x2 matrix acting on
    the window's normalised coordinates, so its entries ARE the extra
    displacement in dots at the window edge.
    """

    translation: np.ndarray
    linear: np.ndarray

    @staticmethod
    def zero() -> "Affine":
        return Affine(translation=np.zeros(2, np.float64),
                      linear=np.zeros((2, 2), np.float64))

    def as_vector(self) -> np.ndarray:
        return np.concatenate((np.asarray(self.translation, np.float64),
                               np.asarray(self.linear, np.float64).ravel()))

    def offsets_dots_xy(self, unit_xy: np.ndarray) -> np.ndarray:
        """Evaluate the correction at normalised window coordinates."""
        unit = np.asarray(unit_xy, np.float64)
        if not unit.shape[0]:
            return np.zeros((0, 2), np.float64)
        return (np.asarray(self.translation, np.float64)[None, :]
                + unit @ np.asarray(self.linear, np.float64).T)

    def magnitude_dots(self) -> float:
        """The largest displacement the correction can produce anywhere in
        the window — the corner where every term adds."""
        translation = np.abs(np.asarray(self.translation, np.float64))
        linear = np.abs(np.asarray(self.linear, np.float64)).sum(axis=1)
        return float(np.hypot(*(translation + linear)))


def unit_coordinates(local_cells_yx: np.ndarray,
                     shape_yx_cells: tuple[int, int]) -> np.ndarray:
    """Normalised (x, y) position of each cell within its window.

    Centred and scaled to [-1, 1] so the linear term's entries read
    directly as dots at the window edge, and so the two axes are very
    nearly orthogonal over any window's cell population — which is what
    makes one sweep of coordinate descent over the four linear terms a
    principled fit rather than a truncated iteration.
    """
    cells = np.asarray(local_cells_yx, np.float64)
    if not cells.shape[0]:
        return np.zeros((0, 2), np.float64)
    unit = np.empty((cells.shape[0], 2), np.float64)
    for axis, extent in enumerate(shape_yx_cells):
        span = max(float(extent) - 1.0, 1.0)
        # axis 0 of the cells is y, and the output is (x, y)
        unit[:, 1 - axis] = 2.0 * (cells[:, axis] - 0.5 * span) / span
    return unit


def profile_log_likelihood(correlation: float, n_cells: int) -> float:
    """The Gaussian log-likelihood with the photometry concentrated out.

    The objective is how much of what the capture reads is explained by
    what the format says is printed there.  Under ``v = level(state) +
    N(0, s^2)`` — one level per printed state, plus noise, which is the
    whole photometric model a window has (a gain, an offset, a toner
    density, a band) — the profile log-likelihood over the levels and
    over s is

        l(theta) = -(n / 2) log(1 - eta(theta)^2) + const

    with eta the correlation ratio below.  Maximising eta IS maximum
    likelihood, and the number returned is the log-likelihood itself, in
    nats, for reporting and for comparing one window's fit to another's.
    """
    bounded = min(abs(float(correlation)), 1.0 - 1e-12)
    return -0.5 * float(n_cells) * float(np.log1p(-bounded * bounded))


@dataclass(frozen=True)
class StateGroups:
    """Cells grouped by the printed state the format proves they carry."""

    order: np.ndarray
    boundaries: np.ndarray
    counts: np.ndarray

    @property
    def n_cells(self) -> int:
        return int(self.counts.sum())

    @property
    def n_states(self) -> int:
        return int(self.counts.size)


def state_groups(states: np.ndarray) -> StateGroups:
    """Sort provable cells by state once, for every later candidate.

    Only the grouping is precomputed.  The LEVELS are not: they are
    re-fitted for every candidate inside `correlation_ratios`, which is
    what keeps the objective honest.  A level table fitted once at the
    starting pose is a target the starting pose matches by construction
    — the search would then be scored against its own initial reading
    and would refuse to leave it, which is the same self-reference
    failure, at the photometry instead of at the labels, that
    INDEPENDENT-PLANES section 2.12 measured on the ink column.
    """
    values = np.asarray(states, np.int64)
    if not values.size:
        return StateGroups(order=np.zeros(0, np.int64),
                           boundaries=np.zeros(0, np.int64),
                           counts=np.zeros(0, np.float64))
    order = np.argsort(values, kind="stable").astype(np.int64)
    _states, counts = np.unique(values, return_counts=True)
    boundaries = np.concatenate(
        (np.zeros(1, np.int64), np.cumsum(counts)[:-1])).astype(np.int64)
    return StateGroups(order=order, boundaries=boundaries,
                       counts=counts.astype(np.float64))


def correlation_ratios(groups: StateGroups,
                       sampled: np.ndarray) -> np.ndarray:
    """Per-candidate eta: the share of the reading the states explain.

    ``sampled`` is (K, N) in the caller's cell order.  eta is the square
    root of the one-way variance ratio — between-state variance over
    total — so it is 1 when every state reads its own level exactly and
    0 when the states say nothing about the reading.  A candidate that
    reads a constant scores 0.0 rather than dividing by zero, which is
    the honest answer for a window that has run off the paper.
    """
    values = np.atleast_2d(np.asarray(sampled, np.float64))[:, groups.order]
    n_cells = float(groups.n_cells)
    if n_cells < 2.0 or groups.n_states < 2:
        return np.zeros(values.shape[0], np.float64)
    sums = np.add.reduceat(values, groups.boundaries, axis=1)
    means = sums / groups.counts[None, :]
    grand = values.sum(axis=1) / n_cells
    between = np.einsum(
        "ks,s->k", (means - grand[:, None]) ** 2, groups.counts)
    total = np.einsum("kn,kn->k", values, values) - n_cells * grand ** 2
    out = np.zeros(values.shape[0], np.float64)
    safe = total > 0.0
    out[safe] = np.sqrt(np.clip(between[safe] / total[safe], 0.0, 1.0))
    return out


def step_ladder(bound: float, resolution: float) -> tuple[float, ...]:
    """Halving steps from half the bound down to the resolution.

    The coarsest step is half the bound, so the first pass's full grid
    spans the whole bound; the finest is the last halving still coarser
    than ``resolution``, the displacement below which the caller's
    sampler cannot tell two candidates apart.
    """
    step = abs(float(bound)) / float(COARSE_STEPS_PER_SIDE)
    floor = abs(float(resolution))
    if step <= 0.0:
        return ()
    steps = [step]
    while steps[-1] * 0.5 >= floor:
        steps.append(steps[-1] * 0.5)
    return tuple(steps)


def _clip(values: np.ndarray, bound: float) -> np.ndarray:
    return np.clip(np.asarray(values, np.float64), -bound, bound)


def _grid_offsets(step: float) -> tuple[tuple[float, float], ...]:
    side = tuple(
        float(index) * step
        for index in range(-COARSE_STEPS_PER_SIDE,
                           COARSE_STEPS_PER_SIDE + 1))
    return tuple((dx, dy) for dy in side for dx in side)


_RING: tuple[tuple[float, float], ...] = tuple(
    (float(dx), float(dy))
    for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dx, dy) != (0, 0))


@dataclass(frozen=True)
class SearchResult:
    affine: Affine
    correlation: float
    n_evaluations: int
    n_cells: int

    @property
    def log_likelihood(self) -> float:
        return profile_log_likelihood(self.correlation, self.n_cells)


Score = Callable[[tuple[Affine, ...]], np.ndarray]


def _best(candidates: tuple[Affine, ...], score: Score,
          incumbent: Affine, incumbent_score: float,
          ) -> tuple[Affine, float, int]:
    """Move to the best strictly better candidate, in the given order."""
    if not candidates:
        return incumbent, incumbent_score, 0
    scores = np.asarray(score(candidates), np.float64)
    order = int(np.argmax(scores))
    if float(scores[order]) > incumbent_score:
        return candidates[order], float(scores[order]), len(candidates)
    return incumbent, incumbent_score, len(candidates)


def search_translation(score: Score, start: Affine, bound: float,
                       resolution: float) -> tuple[Affine, float, int]:
    steps = step_ladder(bound, resolution)
    if not steps:
        return start, float(score((start,))[0]), 1
    incumbent = start
    incumbent_score = float(score((start,))[0])
    evaluations = 1
    for index, step in enumerate(steps):
        deltas = (_grid_offsets(step) if index == 0
                  else tuple((dx * step, dy * step) for dx, dy in _RING))
        candidates = tuple(
            Affine(translation=_clip(
                np.asarray(incumbent.translation, np.float64)
                + np.asarray(delta, np.float64), bound),
                linear=incumbent.linear)
            for delta in deltas)
        incumbent, incumbent_score, spent = _best(
            candidates, score, incumbent, incumbent_score)
        evaluations += spent
    return incumbent, incumbent_score, evaluations


def search_linear(score: Score, start: Affine, bound: float,
                  resolution: float, start_score: float,
                  ) -> tuple[Affine, float, int]:
    """One sweep of coordinate descent over the four linear terms.

    ONE sweep on purpose.  The window's normalised coordinates have zero
    mean and are near-orthogonal, so the four terms are very nearly
    separable and a second sweep would be a fixed-point iteration on a
    loopy objective — the shape INDEPENDENT-PLANES section 2.12 measured
    diverging.  A single pass over near-orthogonal coordinates is a fit;
    repeating it is a loop, and this module does not have one.
    """
    steps = step_ladder(bound, resolution)
    incumbent = start
    incumbent_score = start_score
    evaluations = 0
    if not steps:
        return incumbent, incumbent_score, evaluations
    for term in range(N_LINEAR_TERMS):
        row, column = divmod(term, 2)
        for index, step in enumerate(steps):
            deltas = (
                tuple(float(offset) * step
                      for offset in range(-COARSE_STEPS_PER_SIDE,
                                          COARSE_STEPS_PER_SIDE + 1)
                      if offset != 0)
                if index == 0 else (-step, step))
            candidates = []
            for delta in deltas:
                linear = np.asarray(incumbent.linear, np.float64).copy()
                linear[row, column] = float(_clip(
                    np.asarray(linear[row, column] + delta), bound))
                candidates.append(Affine(translation=incumbent.translation,
                                         linear=linear))
            incumbent, incumbent_score, spent = _best(
                tuple(candidates), score, incumbent, incumbent_score)
            evaluations += spent
    return incumbent, incumbent_score, evaluations


def search(score: Score, start: Affine, translation_bound: float,
           resolution: float, n_cells: int) -> SearchResult:
    """Translation first, then the linear terms — the staged search.

    Translation leads because it is the measured dominant term (the
    Xerox Y-registration sinusoid, the C-minus-M offsets, the scanner's
    lateral chromatic aberration are all translations at window scale);
    the linear terms are opened after it, around the translation the
    data chose, and cannot undo it.
    """
    affine, correlation, spent = search_translation(
        score, start, translation_bound, resolution)
    linear_bound = translation_bound * LINEAR_BOUND_FRACTION
    affine, correlation, linear_spent = search_linear(
        score, affine, linear_bound, resolution, correlation)
    return SearchResult(affine=affine, correlation=correlation,
                        n_evaluations=spent + linear_spent,
                        n_cells=int(n_cells))

"""The patch family's ARITHMETIC ECONOMY — one extraction, one Gram (W8 B8).

BLIND, and free of every analyzer module but :mod:`analyzer.patchgrid`
(the geometry) and :mod:`analyzer.types`: this is the layer that makes the
self-discovery walk of W8 B7 affordable without changing a single verdict
it reaches.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`, and nothing here imports
:mod:`analyzer.autoknobs` or :mod:`analyzer.patch` (both dispatch into
this module).

THE RULING (Germano, 2026-09-06): "nothing prevents us from a) numpy
optimizing and parallelizing the pure pass (which is probably a thing),
and b) only run it after the other pass has done its job."  This module
is (a).  (b) is `types.PROFILES`' `patch-then-pure` and the
`reroll_only_arms` placement.

WHAT WAS SLOW, MEASURED ON THIS MACHINE (Accelerate, one BLAS thread):
`scipy.ndimage.map_coordinates` at order 1 reads about 5.6 M points per
second, while a 4096x576 normal-equation build (`dgemm`) takes 25 ms —
so the patch family is BOUND BY THE RESAMPLER, not by the algebra, by
roughly two orders of magnitude per unit of work.  A `patch_score` under
`patch_window_cells="auto"` used to resample

  * every observed cell at the WIDEST window, only to learn which rows
    stay inside the crop  (25,600 x 1024 samples = 26 M points, 4.7 s),
  * every observed cell again at the inherited window  (14.7 M, 2.6 s),
  * and the selection rows once per candidate geometry per population,
    with a four-entry memo that five populations thrash  (up to 160 M).

THREE EXACT MOVES REMOVE MOST OF IT, and none of them changes a number:

1. :func:`inside_mask` — WHICH ROWS FIT IN THE CROP IS ARITHMETIC, NOT
   SAMPLING.  IEEE addition is monotone in the addend, so the minimum
   over a row's samples of ``fl(centre + offset)`` IS ``fl(centre +
   min offset)``: the bounds test `patchgrid.extract` makes per sample is
   reproduced EXACTLY by two comparisons per row and per axis.  The
   bounding-geometry extraction disappears entirely.

2. :class:`FeatureBank` — A NARROWER CANDIDATE IS A SLICE OF A WIDER ONE.
   `patchgrid.grid_cells` puts sample `j` at ``(j + 0.5)/S -
   window/2``; at a fixed `S` the offsets of window `w` are the CENTRED
   sub-square of the offsets of any wider window, and the arithmetic is
   dyadic, so the two grids agree bit for bit (checked at run time, with
   a real extraction as the fallback).  Channels are channel-major
   blocks, so `r` is the leading block of `rgb`; and `rings` is a
   matrix multiply of the pixel block, never a second extraction.  ONE
   extraction of the selection rows at the walk's widest geometry
   therefore serves every candidate of every population.

3. :class:`Moments` — THE NORMAL EQUATIONS ARE ADDITIVE AND SLICEABLE.
   ``(n, sum w, sum w x, sum w x x^T, ...)`` are sufficient for the whole
   of `autoknobs.fit_discriminant` (mean, sd, the ridge system, the
   right-hand side and the class-mean threshold), they SUM over disjoint
   row sets — halves, sibling states, neighbourhood tiles — and the
   moments of a feature SUBSET are the corresponding submatrix.  So one
   Gram per (population, half) at the widest geometry prices every
   candidate window, every channel subset, both feature kinds and every
   shrinkage, and the cross-fit's third fit (A u B) is an addition
   rather than a third build.

DETERMINISM.  No RNG; every cache is keyed by resolved geometry and row
identity, and a cached answer is the answer the direct path gives (the
byte-identical pin is `test_analyzer_patch_walk`'s
`test_the_memoised_and_direct_paths_agree_byte_for_byte`).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .patchgrid import (PatchError, extract, grid_cells, grid_shape,
                        ring_features, ring_matrix)
from .types import Crops, LaneFootprint, Read

__all__ = ["FeatureBank", "Moments", "axes_key", "block_width",
           "column_subset", "derive_block", "inside_mask", "moments_of"]


@dataclass(frozen=True)
class _Grid:
    """What `patchgrid` reads off a spec — nothing else."""

    samples_per_cell: int
    window_cells: float


def _grid_of(axes: Mapping[str, Any]) -> _Grid:
    return _Grid(int(axes["samples_per_cell"]), float(axes["window_cells"]))


# ------------------------------------------------------- 1. the bounds test

def inside_mask(crops: Crops, points_yx: np.ndarray,
                linear_by_owner: Mapping[int, np.ndarray],
                owner_index: np.ndarray, rows: np.ndarray,
                grid: np.ndarray) -> np.ndarray:
    """`patchgrid.extract`'s `inside` predicate, WITHOUT resampling.

    A row is inside iff every one of its samples lands in
    ``[0, h-1] x [0, w-1]`` of the crop.  `extract` tests that sample by
    sample; here the extreme sample per axis is used instead, which is
    the SAME predicate in IEEE arithmetic: floating-point addition is
    monotone in its addend, so for a fixed centre `c` the smallest
    ``fl(c + o_j)`` over the grid is ``fl(c + min_j o_j)`` and likewise
    for the largest.  The cost falls from (rows x samples) to (rows).

    Returns a `(len(rows),)` bool array in `rows` order.  A row whose
    owner has no pose, or whose centre is not finite, is NOT inside —
    exactly as `extract` leaves it NaN.
    """
    rows = np.asarray(rows, np.int64)
    inside = np.zeros(rows.size, bool)
    if not rows.size:
        return inside
    if crops.raw_rgb is None:
        raise PatchError("the crops carry no raw pixels; open them with "
                         "keep_raw=True")
    grid = np.asarray(grid, np.float64)
    height = float(int(crops.raw_rgb.shape[0]) - 1)
    width = float(int(crops.raw_rgb.shape[1]) - 1)
    origin = np.asarray((crops.y0, crops.x0), np.float64)
    owners = np.asarray(owner_index, np.int64)[rows]
    points = np.asarray(points_yx, np.float64)[rows]
    for owner in np.unique(owners).tolist():
        if owner < 0:
            continue
        linear = linear_by_owner.get(int(owner))
        if linear is None:
            continue
        offsets = grid @ np.asarray(linear, np.float64).T   # (samples, 2)
        low = offsets.min(axis=0)
        high = offsets.max(axis=0)
        where = np.flatnonzero(owners == owner)
        centre = points[where] - origin
        with np.errstate(invalid="ignore"):
            ok = (np.isfinite(centre).all(axis=1)
                  & (centre[:, 0] + low[0] >= 0.0)
                  & (centre[:, 0] + high[0] <= height)
                  & (centre[:, 1] + low[1] >= 0.0)
                  & (centre[:, 1] + high[1] <= width))
        inside[where] = ok
    return inside


# --------------------------------------------------- 2. the column subset

def column_subset(base: Mapping[str, Any], axes: Mapping[str, Any],
                  pitch_px: float) -> np.ndarray | None:
    """Columns of `axes`' PIXEL block inside `base`'s, or None.

    None means "not a subset, extract it" — a coarser sampling, a wider
    window, a channel `base` does not carry, or (defensively) a grid that
    does not agree sample for sample.  The agreement is CHECKED, not
    assumed: `np.array_equal` on the two grids' offsets, so a future
    change to `grid_cells` cannot silently make a slice wrong.
    """
    base_samples, base_axis = grid_shape(_grid_of(base), pitch_px)
    samples, per_axis = grid_shape(_grid_of(axes), pitch_px)
    if samples != base_samples or per_axis > base_axis:
        return None
    if (base_axis - per_axis) % 2:
        return None
    base_channels = tuple(int(c) for c in base["channels"])
    channels = tuple(int(c) for c in axes["channels"])
    if any(channel not in base_channels for channel in channels):
        return None
    start = (base_axis - per_axis) // 2
    rows = np.arange(start, start + per_axis)
    flat = (rows[:, None] * base_axis + rows[None, :]).ravel()
    if not np.array_equal(grid_cells(_grid_of(axes), pitch_px),
                          grid_cells(_grid_of(base), pitch_px)[flat]):
        return None
    block = int(base_axis) ** 2
    return np.concatenate([flat + base_channels.index(channel) * block
                           for channel in channels]).astype(np.int64)


def axes_key(axes: Mapping[str, Any], pitch_px: float) -> tuple:
    """The RESOLVED geometry of one axes bag — `grid_shape`'s cap included.

    ONE spelling, shared by `FeatureBank.key` and by every caller that
    has to ask "is this block already the one I want?" (the local5
    harvest, review 2026-09-06).  Two candidates that resolve onto the
    same grid share it: 16 samples per cell on a lane that carries 8
    px/cell IS 8.
    """
    samples, per_axis = grid_shape(_grid_of(axes), pitch_px)
    return (int(samples), int(per_axis),
            tuple(int(c) for c in axes["channels"]),
            str(axes["features"]))


def block_width(axes: Mapping[str, Any], pitch_px: float) -> int:
    """How many features one row of `axes`' block holds."""
    _samples, per_axis = grid_shape(_grid_of(axes), pitch_px)
    channels = len(tuple(axes["channels"]))
    per_channel = (max(1, int(per_axis) // 2)
                   if str(axes["features"]) == "rings"
                   else int(per_axis) ** 2)
    return int(per_channel * channels)


def derive_block(base_axes: Mapping[str, Any], block: np.ndarray,
                 axes: Mapping[str, Any], pitch_px: float,
                 ) -> np.ndarray | None:
    """`axes`' feature block out of `base_axes`' PIXEL block, or None.

    `FeatureBank._derive` without the bank: a caller that holds one wide
    extraction (the 5x5 neighbourhood's rows, harvested once at the
    walk's widest geometry) cuts every narrower candidate out of it.
    None means "not derivable" — a coarser SAMPLING, which moves every
    sample position and is a different grid, or a channel the base does
    not carry.
    """
    if str(base_axes.get("features", "pixels")) != "pixels":
        return None
    block = np.asarray(block)
    if axes_key(base_axes, pitch_px) == axes_key(axes, pitch_px):
        return np.ascontiguousarray(block)
    columns = column_subset(base_axes, axes, pitch_px)
    if columns is None:
        return None
    out = block[:, columns]
    if str(axes["features"]) == "rings":
        out = ring_features(out, ring_matrix(_grid_of(axes), pitch_px),
                            len(tuple(axes["channels"])))
    return np.ascontiguousarray(out)


# ------------------------------------------------------- 3. the moments

@dataclass(frozen=True)
class Moments:
    """Sufficient statistics of a weighted labelled row set.

    ``n`` rows, ``s0 = sum w``, ``s1 = sum w x``, ``gram = sum w x x^T``,
    and the same two sums restricted to the ``y == 1`` rows.  Everything
    `autoknobs.fit_discriminant` computes is a function of these, so they
    ADD over disjoint row sets (the cross-fit halves, the sibling states,
    a neighbourhood's tiles) and a feature subset is a submatrix.
    """

    n: int
    n_1: int
    s0: float
    s0_1: float
    s1: np.ndarray
    s1_1: np.ndarray
    gram: np.ndarray

    def __add__(self, other: "Moments") -> "Moments":
        return Moments(n=self.n + other.n, n_1=self.n_1 + other.n_1,
                       s0=self.s0 + other.s0, s0_1=self.s0_1 + other.s0_1,
                       s1=self.s1 + other.s1, s1_1=self.s1_1 + other.s1_1,
                       gram=self.gram + other.gram)

    def select(self, columns: np.ndarray) -> "Moments":
        """The same moments over a subset of the features."""
        columns = np.asarray(columns, np.int64)
        return Moments(n=self.n, n_1=self.n_1, s0=self.s0, s0_1=self.s0_1,
                       s1=self.s1[columns], s1_1=self.s1_1[columns],
                       gram=self.gram[np.ix_(columns, columns)])

    def reduce(self, matrix: np.ndarray) -> "Moments":
        """The moments of ``x @ matrix`` — `patchgrid.ring_features`."""
        matrix = np.asarray(matrix, np.float64)
        return Moments(n=self.n, n_1=self.n_1, s0=self.s0, s0_1=self.s0_1,
                       s1=self.s1 @ matrix, s1_1=self.s1_1 @ matrix,
                       gram=matrix.T @ self.gram @ matrix)


def moments_of(X: np.ndarray, y: np.ndarray,
               weights: np.ndarray | None = None) -> Moments:
    """The moments of one labelled block; ONE `gemm` and two `gemv`."""
    X = np.asarray(X, np.float64)
    y = np.asarray(y).astype(np.uint8)
    if X.ndim != 2 or X.shape[0] != y.size:
        raise PatchError(f"moments_of: X {X.shape} vs y {y.shape}")
    w = (np.ones(y.size, np.float64) if weights is None
         else np.asarray(weights, np.float64))
    if w.size != y.size or np.any(w < 0.0):
        raise PatchError("moments_of: bad weights")
    ones = y == 1
    weighted = X * w[:, None]
    return Moments(n=int(y.size), n_1=int(np.count_nonzero(ones)),
                   s0=float(w.sum()), s0_1=float(w[ones].sum()),
                   s1=weighted.sum(axis=0),
                   s1_1=weighted[ones].sum(axis=0),
                   gram=weighted.T @ X)


# ------------------------------------------------------- 4. the bank

class FeatureBank:
    """Pose-resampled patch blocks for one (tile, lane, read), by geometry.

    ONE extraction serves the whole self-discovery walk: the selection
    rows — the labelled rows every candidate is trained and scored on —
    are resampled once at the walk's WIDEST geometry (`bounding`), and
    every narrower candidate is :func:`column_subset` of that block, with
    `rings` applied as a matrix multiply.  Full-footprint blocks (the
    rows a population SCORES) are memoised by geometry in a small LRU and
    served by slicing whenever the request is a subset of one held.

    The bank is per `patch_score` call: it dies with the crops.  What it
    memoises across calls is nothing — the cross-target memo the review
    asked for needs a lane and pose identity that `patch_score`'s
    signature does not carry (B8's notes name the seam).
    """

    #: Full-footprint blocks kept at once.  One is (observed rows x F)
    #: float32 — 59 MB at 25,600 x 576, and 314 MB at the 3,072 features
    #: the widest candidate the auto walk may name (window 2.0, 16
    #: samples per cell, rgb) asks for on a 4800-dpi lane.  A population
    #: only ever scores through the geometry it chose, so two is a working
    #: set and not a cache; the BYTE cap is what actually bounds a worker
    #: when the geometry is wide (review 2026-09-06 — the entry count
    #: alone let two entries reach 630 MB, times `--workers`).
    CACHE_ENTRIES: int = 2
    #: Bytes the block memo may hold before it evicts, whatever the entry
    #: count says.  One entry is always kept: it is the block in use.
    CACHE_BYTES: int = 192 * 1024 * 1024

    def __init__(self, crops: Crops, read: Read, lfp: LaneFootprint,
                 selection_rows: np.ndarray | None = None, *,
                 bounding: Mapping[str, Any] | None = None):
        self.crops = crops
        self.read = read
        self.lfp = lfp
        self.pitch_px = float(crops.pitch_px_level)
        self.selection_rows = (np.zeros(0, np.int64)
                               if selection_rows is None
                               else np.asarray(selection_rows, np.int64))
        #: the widest geometry any candidate may ask for; the selection
        #: block is cut here once and sliced thereafter
        self.bounding: dict[str, Any] | None = (dict(bounding)
                                                if bounding else None)
        #: ``(resolved key, features, inside)`` of the selection rows
        self._selection: tuple[tuple, np.ndarray, np.ndarray] | None = None
        #: resolved key -> ``(rows, axes, features, inside)``
        self._blocks: OrderedDict[tuple, tuple] = OrderedDict()
        self._moments: dict[tuple, Moments] = {}
        self.n_extractions = 0

    # -- geometry ---------------------------------------------------------

    def geometry_of(self, axes: Mapping[str, Any]) -> tuple[int, int]:
        """``(samples, per_axis)`` after `grid_shape`'s native cap."""
        return grid_shape(_grid_of(axes), self.pitch_px)

    def key(self, axes: Mapping[str, Any]) -> tuple:
        """The RESOLVED geometry — `grid_shape`'s native cap included.

        Two candidates that resolve onto the same grid (16 samples per
        cell on a lane that carries 8 px/cell is 8) share one extraction
        and therefore score identically, so the paired test finds no
        difference and the inherited value keeps the axis.
        """
        return axes_key(axes, self.pitch_px)

    def inside(self, axes: Mapping[str, Any], rows: np.ndarray) -> np.ndarray:
        """Which of `rows` a patch at `axes` fits inside the crop for.

        :func:`inside_mask`, so it costs one comparison per row and axis
        instead of one resampled point per sample — and it is the same
        predicate `patchgrid.extract` applies, which is what lets the
        widest candidate geometry fix the row set for free.
        """
        return inside_mask(self.crops, self.read.points_yx,
                           self.read.linear_by_owner, self.lfp.owner_index,
                           rows, grid_cells(_grid_of(axes), self.pitch_px))

    def _bounding_for(self, axes: Mapping[str, Any]) -> dict[str, Any]:
        """The geometry a request is cut from: the walk's, or its own."""
        if self.bounding is None:
            return dict(axes)
        return dict(self.bounding)

    # -- extraction -------------------------------------------------------

    def _cut(self, axes: Mapping[str, Any], rows: np.ndarray,
             ) -> tuple[np.ndarray, np.ndarray]:
        """One real extraction, pixels then (if asked) the ring reduction."""
        grid_spec = _grid_of(axes)
        channels = tuple(int(c) for c in axes["channels"])
        self.n_extractions += 1
        features, inside = extract(
            self.crops, self.read.points_yx, self.read.linear_by_owner,
            self.lfp.owner_index, np.asarray(rows, np.int64),
            grid_cells(grid_spec, self.pitch_px), channels)
        if str(axes["features"]) == "rings":
            features = ring_features(
                features, ring_matrix(grid_spec, self.pitch_px),
                len(channels))
        return features, inside

    def _derive(self, base_axes: Mapping[str, Any], base: np.ndarray,
                axes: Mapping[str, Any]) -> np.ndarray | None:
        """`axes`' block out of `base_axes`' pixel block, or None."""
        if str(base_axes["features"]) != "pixels":
            return None
        columns = column_subset(base_axes, axes, self.pitch_px)
        if columns is None:
            return None
        block = base[:, columns]
        if str(axes["features"]) == "rings":
            block = ring_features(
                block, ring_matrix(_grid_of(axes), self.pitch_px),
                len(tuple(axes["channels"])))
        return np.ascontiguousarray(block)

    def block(self, axes: Mapping[str, Any], rows: np.ndarray,
              ) -> tuple[np.ndarray, np.ndarray]:
        """``(features (len(rows), F) float32, inside (len(rows),) bool)``.

        Served from a memoised wider block when the rows are a subset of
        one held and the geometry is a column subset of its own; cut
        otherwise, and the cut is memoised under its own key.

        The `inside` that comes back with a DERIVED block is the wider
        geometry's, which is the conservative one — and the one the
        caller wants: `patch_score` fixes its row set by the bounding
        geometry on purpose, so that every candidate is trained and
        scored on the same rows.
        """
        rows = np.asarray(rows, np.int64)
        for cached_key in list(self._blocks.keys()):
            cached_rows, cached_axes, block, inside = self._blocks[cached_key]
            take = _positions(cached_rows, rows)
            if take is None:
                continue
            derived = (block if cached_key == self.key(axes)
                       else self._derive(cached_axes, block, axes))
            if derived is None:
                continue
            self._blocks.move_to_end(cached_key)
            return np.ascontiguousarray(derived[take]), inside[take]
        features, inside = self._cut(axes, rows)
        self._blocks[self.key(axes)] = (rows, dict(axes), features, inside)
        self._evict()
        return features, inside

    def _evict(self) -> None:
        """Trim the block memo to its entry AND byte caps, oldest first."""
        held = sum(int(np.asarray(entry[2]).nbytes)
                   for entry in self._blocks.values())
        while len(self._blocks) > 1 and (
                len(self._blocks) > int(self.CACHE_ENTRIES)
                or held > int(self.CACHE_BYTES)):
            _key, dropped = self._blocks.popitem(last=False)
            held -= int(np.asarray(dropped[2]).nbytes)

    # -- the selection ----------------------------------------------------

    def use_selection(self, rows: np.ndarray,
                      bounding: Mapping[str, Any] | None = None) -> None:
        """Name the selection rows and (optionally) the walk's widest axes.

        `inside` — which rows the widest candidate can reach at all —
        comes out of :func:`inside_mask`, so the selection set cannot be
        known before the bank exists.  Setting it drops the selection
        memo; the full-block memo is left alone (its rows are unaffected).
        """
        self.selection_rows = np.asarray(rows, np.int64)
        if bounding is not None:
            self.bounding = dict(bounding)
        self._selection = None
        self._moments.clear()

    def selection(self, axes: Mapping[str, Any],
                  ) -> tuple[np.ndarray, np.ndarray]:
        """The selection rows' block — ONE extraction, then slices."""
        base = self._bounding_for(axes)
        base_key = self.key(base)
        if self._selection is None or self._selection[0] != base_key:
            features, inside = self._cut(base, self.selection_rows)
            self._selection = (base_key, features, inside)
        _key, block, inside = self._selection
        if base_key == self.key(axes):
            return block, inside
        derived = self._derive(base, block, axes)
        if derived is None:
            return self._cut(axes, self.selection_rows)
        return derived, inside

    def selection_moments(self, axes: Mapping[str, Any], token: Any,
                          positions: np.ndarray, labels: np.ndarray,
                          ) -> Moments:
        """Cached, sliceable normal equations over selection positions.

        `token` names the row set (a population and a cross-fit half);
        the moments are built ONCE at the walk's widest geometry and
        every narrower candidate is `Moments.select` of them — so a
        coordinate pass over windows, channels, feature kinds and
        shrinkages costs one `gemm`, not one per candidate.
        """
        base = self._bounding_for(axes)
        cache_key = (token, self.key(base))
        wide = self._moments.get(cache_key)
        if wide is None:
            block, _inside = self.selection(base)
            wide = moments_of(np.asarray(block[positions], np.float64),
                              labels)
            self._moments[cache_key] = wide
        if self.key(base) == self.key(axes):
            return wide
        columns = column_subset(base, axes, self.pitch_px)
        if columns is None:
            block, _inside = self.selection(axes)
            return moments_of(np.asarray(block[positions], np.float64),
                              labels)
        narrow = wide.select(columns)
        if str(axes["features"]) == "rings":
            matrix = ring_matrix(_grid_of(axes), self.pitch_px)
            channels = len(tuple(axes["channels"]))
            narrow = narrow.reduce(_block_diagonal(matrix, channels))
        return narrow


def _block_diagonal(matrix: np.ndarray, blocks: int) -> np.ndarray:
    """`ring_features` as ONE matrix: `blocks` copies down the diagonal."""
    rows, cols = matrix.shape
    out = np.zeros((rows * blocks, cols * blocks), np.float64)
    for index in range(int(blocks)):
        out[index * rows:(index + 1) * rows,
            index * cols:(index + 1) * cols] = matrix
    return out


def _positions(have: np.ndarray, want: np.ndarray) -> np.ndarray | None:
    """Where `want` sits inside `have`, or None if it is not contained."""
    have = np.asarray(have, np.int64)
    want = np.asarray(want, np.int64)
    if not have.size:
        return None if want.size else np.zeros(0, np.int64)
    order = np.argsort(have, kind="stable")
    sorted_have = have[order]
    position = np.searchsorted(sorted_have, want)
    if np.any(position >= sorted_have.size):
        return None
    if not np.array_equal(sorted_have[position], want):
        return None
    return order[position]


def bounding_of(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The widest geometry a set of candidate axes asks for.

    Channels are taken as the LONGEST tuple, which is the widest only
    when the candidate sets nest (`autoknobs.CHANNEL_CANDIDATES` is
    `(0,)` inside `(0, 1, 2)`).  A future non-nesting set costs an
    extraction, never a wrong slice: `column_subset` refuses a channel
    the base does not carry and the bank cuts the candidate for itself.
    """
    if not candidates:
        raise PatchError("bounding_of: no candidates")
    out = dict(candidates[0])
    out["features"] = "pixels"
    for axes in candidates[1:]:
        out["samples_per_cell"] = max(int(out["samples_per_cell"]),
                                      int(axes["samples_per_cell"]))
        out["window_cells"] = max(float(out["window_cells"]),
                                  float(axes["window_cells"]))
        if len(tuple(axes["channels"])) > len(tuple(out["channels"])):
            out["channels"] = tuple(int(c) for c in axes["channels"])
    return out

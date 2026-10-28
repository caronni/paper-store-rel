"""E8 leaves: A5's ink map rebuilt from the DECODER'S OWN decisions.

§2.10's E4 replaced Y's column of A5's ink map with the printed truth and
measured the size of the Y-context loop: −2.43 pp on the dead tiles,
−2.45 on the controls, three of six dead tiles flipped to CERTIFIED.  That
is an ORACLE — a receiver cannot know Y's printed bits — so it priced the
loop and licensed nothing.  E8 asks the next question: how much of it can
a receiver take WITHOUT the truth?

Every configuration here is a different non-oracle estimate of the same
column, fed through the same seam E4 used:

===  =====================================================================
 a   baseline: the fit's own bins (production)               [E4's (a)]
 b   Y's ink column = GT                       [E4's (b), reference only]
 c   C and M = GT                              [E4's (c), method control]
 e1  Y's ink column = the baseline pass's FINAL decision (post-context,
     post-calibration emitted LLR sign) — ONE fixed-point iteration
 e2  the same, iterated once more on (e1)'s decision
 f   Y's SELF-column removed: Y's bin counts neighbours carrying C or M
     ink; C and M keep their own.  The non-circular model class.
 g   Y's ink column = the 3-capture CONSENSUS of the baseline decisions
     (summed post-context Y LLRs over the captures that observe the cell)
 h   Y's ink column SOFT: each neighbour contributes its baseline
     posterior P(Y ink) instead of a hard 0/1, and the expected count is
     rounded to A5's own nine bins
===  =====================================================================

**What (h) is NOT.**  The brief's soft column would interpolate A5's
per-bin offsets between integer bins.  ``ContextHead.apply_states`` takes
an ``int8`` bin array, so a fractional bin is a DETECTOR change and this
instrument is forbidden to make one.  What is implemented is the other
half — soft evidence into the neighbourhood COUNT — consumed by the
existing nine-bin machinery through a rounding.  Stated, not silently
substituted.

Nothing here changes ``src/holo``.  The bins are rebuilt by a lattice
that reproduces ``color_neighbourhood.region_context_bins`` expression for
expression (:class:`RegionGrid`), and the null proof is exact:
configuration (a) rebuilt through this path must be BIT-IDENTICAL to the
bins the ladder itself produced.  The lattice exists only because E8 runs
eight configurations against E4's four and the dedup, the dense grid and
the two unchanged planes are shared by all of them — one convolution per
configuration instead of a full rebuild.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from holo.receive.color_neighbourhood import provisional_ink
from holo.receive.detect import context_bins

from ._affine_fit import TILE_CELLS
from ._state_tables import Y_PLANE

PLANE_NAMES = ("C", "M", "Y")
N_PLANES = 3

#: configuration id -> (short label, long description).
CONFIGS: tuple[str, ...] = ("a", "b", "c", "z", "e1", "e2", "f", "g", "h")
CONFIG_NAMES = {
    "a": "baseline (provisional ink)",
    "b": "Y column = GT (oracle, reference)",
    "c": "C,M columns = GT (method control)",
    "z": "Y neighbourhood term OFF (bins = -1)",
    "e1": "Y column = baseline decision (1 iteration)",
    "e2": "Y column = (e1)'s decision (2 iterations)",
    "f": "Y bin from C-or-M ink (self-column removed)",
    "g": "Y column = 3-capture consensus decision",
    "h": "Y column = baseline posterior, expected count",
}
#: The configurations whose Y BIN no longer means "how many neighbours
#: carry Y ink".  For those the incumbent A5 curve is being read at an
#: index it was never fitted on, so ``bins+head`` is the faithful arm and
#: ``bins`` is reported only for continuity with E4's table.
REDEFINED_BIN = frozenset({"f", "h"})
#: Configurations that need the consensus map, i.e. a second pass.
NEEDS_CONSENSUS = frozenset({"g"})

#: ``detect.context_neighbour_counts``' kernel: the eight neighbours, not
#: the cell itself.  Kept in both dtypes so the presence pass stays in
#: integers and the ink pass can carry a posterior.
_KERNEL_U8 = np.ones((3, 3), np.uint8)
_KERNEL_U8[1, 1] = 0
_KERNEL = _KERNEL_U8.astype(np.float64)


# --------------------------------------------------------------------------
# the region's deduplicated cell lattice
# --------------------------------------------------------------------------
class RegionGrid:
    """``region_context_bins``'s own dedup and dense grid, computed once.

    The production leaf rebuilds all of this on every call; E8 calls it
    eight times per (tile, capture, geometry) and only ONE plane's ink
    ever changes, so the lattice is hoisted and a configuration costs one
    convolution.  Every step below is the production expression: the
    ownership-canonical row order (ascending patch id), the row-major
    key, ``np.unique``'s first-wins deduplication, and
    ``detect.context_neighbour_counts``' bounding grid.
    """

    def __init__(self, rows) -> None:
        self.n_rows = len(rows)
        self.order = sorted(range(self.n_rows),
                            key=lambda index: int(rows[index].patch.patch_id))
        self.sizes = {ordinal: int(rows[ordinal].page_cells_yx.shape[0])
                      for ordinal in self.order}
        stacked = np.concatenate(
            [np.asarray(rows[ordinal].page_cells_yx, np.int64)
             for ordinal in self.order])
        self.width = int(stacked[:, 1].max()) + 1
        keys = stacked[:, 0] * np.int64(self.width) + stacked[:, 1]
        unique, first, inverse = np.unique(
            keys, return_index=True, return_inverse=True)
        self.unique_keys = unique
        self._first = first
        self._inverse = np.asarray(inverse).reshape(-1)
        self.unique_cells = stacked[first]
        lo = self.unique_cells.min(axis=0)
        self._local = self.unique_cells - lo
        self._shape = tuple((self._local.max(axis=0) + 1).astype(int))
        present = np.zeros(self._shape, np.uint8)
        present[self._local[:, 0], self._local[:, 1]] = 1
        self.valid = ndimage.convolve(
            present, _KERNEL_U8, mode="constant", cval=0)[
                self._local[:, 0], self._local[:, 1]] == 8

    @property
    def n_unique(self) -> int:
        return int(self.unique_keys.size)

    def unique_of(self, by_row: list[np.ndarray]) -> np.ndarray:
        """Per-row values reduced to the deduplicated lattice, first wins."""
        return np.concatenate(
            [np.asarray(by_row[ordinal]) for ordinal in self.order]
        )[self._first]

    def counts(self, ink_column: np.ndarray) -> np.ndarray:
        """The eight-neighbour ink count, exactly as ``detect`` computes it.

        Float ink is allowed (configuration (h)); with 0/1 ink every sum
        is an exact small integer in float64, so the rounding below is the
        identity and the result is bit-identical to the ``uint8`` path.
        """
        grid = np.zeros(self._shape, np.float64)
        grid[self._local[:, 0], self._local[:, 1]] = np.asarray(
            ink_column, np.float64)
        return ndimage.convolve(grid, _KERNEL, mode="constant", cval=0.0)[
            self._local[:, 0], self._local[:, 1]]

    def bins_for(self, ink_column: np.ndarray) -> np.ndarray:
        """One plane's ``int8`` bins over the lattice (``-1`` = no context)."""
        return context_bins(np.rint(self.counts(ink_column)), valid=self.valid)

    def all_bins(self, ink: np.ndarray) -> np.ndarray:
        """``(U, 3)`` bins from an ``(U, 3)`` lattice ink map."""
        out = np.empty((self.n_unique, N_PLANES), np.int8)
        for plane in range(N_PLANES):
            out[:, plane] = self.bins_for(ink[:, plane])
        return out

    def scatter(self, unique_bins: np.ndarray) -> tuple[np.ndarray, ...]:
        """The lattice's bins back onto the rows, in row order."""
        scattered = unique_bins[self._inverse]
        parts: dict[int, np.ndarray] = {}
        start = 0
        for ordinal in self.order:
            stop = start + self.sizes[ordinal]
            parts[ordinal] = np.ascontiguousarray(scattered[start:stop])
            start = stop
        return tuple(parts[ordinal] for ordinal in range(self.n_rows))


# --------------------------------------------------------------------------
# the ink map, and the decisions that feed it
# --------------------------------------------------------------------------
def production_ink(fit, evidence: tuple[np.ndarray, ...]) -> list[np.ndarray]:
    """Per row, A5's own ``(N, 3)`` ink: provisional, with exact bits winning."""
    out = []
    for ordinal in range(len(fit.rows)):
        row = fit.rows[ordinal]
        known = np.asarray(row.known_component_mask, np.bool_)
        bits = np.asarray(row.known_component_bits, np.uint8) > 0
        ink = provisional_ink(evidence[ordinal], cmy8=True)
        out.append(np.where(known, bits, ink).astype(np.float64))
    return out


def post_context_evidence(fit, bins: tuple[np.ndarray, ...]
                          ) -> tuple[np.ndarray, ...]:
    """Every region cell's FINAL emitted evidence under ``bins``.

    ``_swim_region.window_evidence`` without the emission mask: the same
    call, the same certified/known arguments, over all of a row's cells
    rather than the emitted ones — because the ink map is a region-wide
    object and covers suppressed cells too.  This is what "the baseline
    pass's final decision" means: post-A4, post-A5, post-calibration.
    """
    out = []
    for ordinal in range(len(fit.rows)):
        row = fit.rows[ordinal]
        certified = (np.asarray(row.known_component_mask, np.bool_)
                     & (np.asarray(row.furniture_kind, np.int8) < 0)[:, None])
        values, _divisor = fit.selected_fit.evidence_with_divisor(
            fit.features0[ordinal], certified,
            np.asarray(row.known_component_bits, np.uint8), bins[ordinal])
        out.append(np.asarray(values, np.float64))
    return tuple(out)


def _known(fit, ordinal: int) -> tuple[np.ndarray, np.ndarray]:
    row = fit.rows[ordinal]
    return (np.asarray(row.known_component_mask, np.bool_)[:, Y_PLANE],
            np.asarray(row.known_component_bits, np.uint8)[:, Y_PLANE] > 0)


def decision_column(fit, values: tuple[np.ndarray, ...]) -> list[np.ndarray]:
    """Per row, the hard Y ink a decision-fed map would carry."""
    out = []
    for ordinal in range(len(fit.rows)):
        known, bits = _known(fit, ordinal)
        decision = np.asarray(values[ordinal])[:, Y_PLANE] > 0.0
        out.append(np.where(known, bits, decision).astype(np.float64))
    return out


def posterior_column(fit, values: tuple[np.ndarray, ...]) -> list[np.ndarray]:
    """Per row, the SOFT Y ink: ``sigmoid`` of the emitted Y LLR.

    A known cell is a fact, not a posterior, and keeps its exact bit —
    the same rule the hard map follows.
    """
    from scipy.special import expit

    out = []
    for ordinal in range(len(fit.rows)):
        known, bits = _known(fit, ordinal)
        soft = expit(np.asarray(values[ordinal])[:, Y_PLANE])
        out.append(np.where(known, bits.astype(np.float64), soft))
    return out


def consensus_column(fit, page_sum: np.ndarray) -> list[np.ndarray]:
    """Per row, the Y ink of the 3-capture consensus decision.

    ``page_sum`` is the summed post-context Y LLR per PAGE cell over the
    captures that observe it — the receiver's own way of combining
    independent captures' evidence, applied to the neighbourhood
    descriptor instead of to the decode.
    """
    out = []
    for ordinal in range(len(fit.rows)):
        known, bits = _known(fit, ordinal)
        cells = np.asarray(fit.rows[ordinal].page_cells_yx, np.int64)
        decision = page_sum[cells[:, 0], cells[:, 1]] > 0.0
        out.append(np.where(known, bits, decision).astype(np.float64))
    return out


# --------------------------------------------------------------------------
# the eight configurations, as lattice ink maps
# --------------------------------------------------------------------------
@dataclass
class LatticeState:
    """Everything one (tile, capture, geometry) refit shares across configs."""

    grid: RegionGrid
    evidence: tuple[np.ndarray, ...]
    base_ink: np.ndarray                 # (U, 3) production's own
    base_bins: np.ndarray                # (U, 3)
    gt_ink: np.ndarray                   # (U, 3) the printed field


def build_lattice(fit, truth_bits, evidence) -> LatticeState:
    """The shared lattice, with the (a) null proof already available."""
    grid = RegionGrid(fit.rows)
    base_ink = grid.unique_of(production_ink(fit, evidence))
    cells = grid.unique_cells
    gt_ink = np.asarray(
        truth_bits[cells[:, 0], cells[:, 1], :] > 0, np.float64)
    return LatticeState(
        grid=grid, evidence=evidence, base_ink=base_ink,
        base_bins=grid.all_bins(base_ink), gt_ink=gt_ink)


def config_bins(state: LatticeState, name: str, *, y_column=None
                ) -> np.ndarray:
    """``(U, 3)`` lattice bins for one configuration.

    Only the column a configuration touches is recomputed; every other
    plane's bins are carried from the baseline BY CONSTRUCTION, which is
    also the column-invariance E4 had to assert.
    """
    bins = state.base_bins.copy()
    if name == "a":
        return bins
    if name == "z":
        # A5's correction is additive PER PLANE and a -1 bin contributes
        # exactly zero (``ContextHead.apply_states``), so this switches
        # off the Y-NEIGHBOURHOOD TERM and leaves C's and M's standing.
        # The control the smoke run demanded: if a broken Y term is worse
        # than no Y term, a configuration that merely blunts it is not
        # closing the loop, it is disabling the arm.
        bins[:, Y_PLANE] = -1
        return bins
    if name == "b":
        bins[:, Y_PLANE] = state.grid.bins_for(state.gt_ink[:, Y_PLANE])
        return bins
    if name == "c":
        for plane in (0, 1):
            bins[:, plane] = state.grid.bins_for(state.gt_ink[:, plane])
        return bins
    if name == "f":
        either = np.maximum(state.base_ink[:, 0], state.base_ink[:, 1])
        bins[:, Y_PLANE] = state.grid.bins_for(either)
        return bins
    if y_column is None:
        raise ValueError(f"configuration {name} needs its own Y column")
    bins[:, Y_PLANE] = state.grid.bins_for(y_column)
    return bins


def bin_change(state: LatticeState, bins: np.ndarray, fit, address=None
               ) -> dict:
    """Did the override reach the bins, region-wide and on the target tile?

    Computed on the LATTICE rather than per row: the deduplicated cell is
    the object the ink map is built over, so a per-row count would weigh
    shared boundary cells twice.  The invariance clause is explicit —
    a plane whose column was not overridden must come back identical.
    """
    difference = state.base_bins != bins
    out = {
        "region": {
            PLANE_NAMES[plane]: {
                "cells": int(difference.shape[0]),
                "changed": int(difference[:, plane].sum()),
                "fraction": float(difference[:, plane].mean()),
            } for plane in range(N_PLANES)},
        "identical_planes": [PLANE_NAMES[plane] for plane in range(N_PLANES)
                             if not difference[:, plane].any()],
    }
    if address is not None:
        cells = state.grid.unique_cells
        select = ((cells[:, 0] // TILE_CELLS == address[1])
                  & (cells[:, 1] // TILE_CELLS == address[2]))
        out["tile"] = {
            PLANE_NAMES[plane]: {
                "cells": int(select.sum()),
                "changed": int(difference[select, plane].sum()),
                "fraction": (None if not select.any()
                             else float(difference[select, plane].mean())),
            } for plane in range(N_PLANES)}
        out["tile_y_histogram"] = bin_histogram(bins[select])["Y"]
        out["tile_y_histogram_baseline"] = bin_histogram(
            state.base_bins[select])["Y"]
    del fit
    return out


def bin_histogram(bins: np.ndarray) -> dict:
    """Per plane, occupancy of the ten gather slots (index 0 IS bin ``-1``).

    The discriminator between "a better estimate of the neighbourhood"
    and "an estimate so blunted that A5 stops correcting": a column that
    collapses toward the middle bins, or toward ``-1``, is turning the
    arm off rather than aiming it.
    """
    return {PLANE_NAMES[plane]: [int(value) for value in np.bincount(
        np.asarray(bins[:, plane], np.int64) + 1, minlength=10)]
        for plane in range(N_PLANES)}


def ink_disagreement(state: LatticeState, column: np.ndarray | None = None
                     ) -> dict:
    """Where an ink column disagrees with the printed field, per plane."""
    ink = state.base_ink if column is None else np.column_stack(
        (state.base_ink[:, 0], state.base_ink[:, 1], column))
    wrong = (ink > 0.5) != (state.gt_ink > 0.5)
    return {PLANE_NAMES[plane]: {
        "cells": int(wrong.shape[0]),
        "wrong": int(wrong[:, plane].sum()),
        "fraction": float(wrong[:, plane].mean())} for plane in range(N_PLANES)}


def reference_error(fit, bins, addresses, truth_bits, payload_indices,
                    detector_fit=None) -> dict:
    """Y cell error on certified clean-column tiles, at this fit's own bins.

    A REGRESSION control, not a decode: reference tiles are suppressed by
    the emission mask, so they carry no blocks and can never mint a
    certificate.  What they carry is a Y bit the receiver already knows
    to be right, on cells this same detector reads — so a configuration
    that damages the head shows up here, on a population that was never
    outcome-selected.  The cells are deduplicated by ascending patch id
    (the ink map's own canonical order), and the geometry is the region
    fit's own: these tiles get no per-tile affine of their own, which is
    what makes them a control on the DETECTOR rather than on a pose.
    """
    head = fit.selected_fit if detector_fit is None else detector_fit
    payload = np.zeros(TILE_CELLS * TILE_CELLS, bool)
    payload[np.asarray(payload_indices, np.int64)] = True
    by_tile: dict[str, dict] = {}
    for address in addresses:
        ordinals = fit.tile_rows.get(address, ())
        if not ordinals:
            continue
        seen: set[int] = set()
        cells_seen = 0
        wrong = 0
        for ordinal in sorted(
                ordinals, key=lambda o: int(fit.rows[o].patch.patch_id)):
            features = fit.features0.get(ordinal)
            if features is None:
                continue
            row = fit.rows[ordinal]
            cells = np.asarray(row.page_cells_yx, np.int64)
            select = np.flatnonzero(
                (cells[:, 0] // TILE_CELLS == address[1])
                & (cells[:, 1] // TILE_CELLS == address[2]))
            if select.size == 0:
                continue
            keys = ((cells[select, 0] % TILE_CELLS) * TILE_CELLS
                    + (cells[select, 1] % TILE_CELLS))
            fresh = np.fromiter((int(key) not in seen for key in keys.tolist()),
                                bool, count=keys.size)
            seen.update(int(key) for key in keys[fresh].tolist())
            select = select[fresh & payload[keys]]
            if select.size == 0:
                continue
            certified = (np.asarray(row.known_component_mask, np.bool_)
                         & (np.asarray(row.furniture_kind, np.int8) < 0
                            )[:, None])
            values, _divisor = head.evidence_with_divisor(
                features, certified,
                np.asarray(row.known_component_bits, np.uint8), bins[ordinal])
            decision = np.asarray(values)[select, Y_PLANE] > 0.0
            truth = truth_bits[cells[select, 0], cells[select, 1],
                               Y_PLANE] > 0
            cells_seen += int(select.size)
            wrong += int(np.count_nonzero(decision != truth))
        if cells_seen:
            by_tile[f"{address[1]},{address[2]}"] = {
                "cells": cells_seen, "errors": wrong,
                "ber": float(wrong / cells_seen)}
    cells = sum(row["cells"] for row in by_tile.values())
    errors = sum(row["errors"] for row in by_tile.values())
    return {"cells": int(cells), "errors": int(errors),
            "ber": (None if not cells else float(errors / cells)),
            "by_tile": by_tile}


def known_bit_agreement(fit, truth_bits) -> dict:
    """Do the exact bits the receiver holds equal the printed truth?"""
    checked = 0
    mismatched = 0
    for row in fit.rows:
        cells = np.asarray(row.page_cells_yx, np.int64)
        known = np.asarray(row.known_component_mask, np.bool_)
        bits = np.asarray(row.known_component_bits, np.uint8) > 0
        gt = truth_bits[cells[:, 0], cells[:, 1], :] > 0
        checked += int(known.sum())
        mismatched += int(np.count_nonzero((bits != gt) & known))
    return {"known_cells": checked, "mismatched": mismatched,
            "exact": bool(checked > 0 and mismatched == 0)}


__all__ = [
    "CONFIGS", "CONFIG_NAMES", "NEEDS_CONSENSUS", "N_PLANES", "PLANE_NAMES",
    "REDEFINED_BIN", "LatticeState", "RegionGrid", "bin_change",
    "bin_histogram", "build_lattice", "config_bins", "consensus_column", "decision_column",
    "ink_disagreement", "known_bit_agreement", "post_context_evidence",
    "posterior_column", "production_ink", "reference_error",
]

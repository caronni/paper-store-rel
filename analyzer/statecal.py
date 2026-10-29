"""The SIBLING STATE, and everything the analyzer keys on it — W8 B2.

BLIND.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`; nothing here may import
:mod:`analyzer.calibrate` or :mod:`analyzer.combine` either, because both
of those dispatch INTO this module and the constants they share live in
:mod:`analyzer.types` for exactly that reason (the import-direction
ruling of W8 B2).  `state_platt_weights` therefore takes the pooled Platt
fitter as a CALLABLE instead of importing it.

WHY A STATE AXIS EXISTS AT ALL (MEASUREMENTS-2026-09-06-C-THIRD-LAYER):
on sheet H a C cell whose siblings M and Y are BOTH inked is read 2-4x
worse than any other C cell, sheet-wide — 0.214 in the dead band against
0.05-0.07 elsewhere — because the third toner layer on an M+Y pile has no
dot core (a flat red deficit at ~60% of a single layer's strength).  The
consequence for calibration is not that the score is worse but that it is
a DIFFERENT score: one PAVA map over the union is a map fitted on a
mixture and applied to another mixture, which is DESIGN §4.7's blocker
B12 again, one axis further in.  The measured symptom is a calibration
that is OVER-confident on M+Y cells (|L| 2-4 claims 5.8% error and
measures 15.7%) and UNDER-confident everywhere else (slope ~1.3).

FOUR MECHANISMS, one convention:

* :func:`sibling_state` — ``s = bits[left] + 2*bits[right]`` with
  ``left, right = spectral.siblings_of(plane)`` ASCENDING, and −1 where
  either sibling is unproven.  For C: 0 blank, 1 M, 2 Y, 3 M+Y; state 3
  is "both siblings inked" in every plane.  This is the convention the
  measurement scripts and `oracle` already use; it is written down ONCE,
  here, and every other module calls it.

* :func:`state_branch_masks` / :func:`state_fit_masks` — C1.  One PAVA
  map and one standardisation per state (plus `other`, where the
  siblings are unproven and no state exists).  The SCORING mask and the
  TRAIN mask differ by ruling 11: a word site carries ONE target class
  per sibling state (at a word site C == M and Y == 0), so word rows are
  excluded from a per-state fit and kept in the pooled one; dust and
  certified cargo projections stay.

* :func:`apply_state_context` — C2.  Production's own 9-bin context
  correction, fitted per state with production's solver and production's
  floors, on top of the pooled correction that already ran.

* :func:`state_platt_weights` — D1.  Per-state combination weights,
  gated on the state's OWN minority count.  NOT on the discriminating
  minority: within a fixed sibling state the discriminating flag is
  degenerate (for C, discriminating means C != M, so with M fixed every
  such label carries the same C bit), so that floor reads 0 for every
  state and would refuse the rule everywhere.

WHERE IT CAN FIRE.  Every per-state mechanism needs BOTH siblings
certified at the cell.  On sheet H that is true in the dead band (cargo
cleanable 1.0 on 64 of 100 dead-band C rows) and false on the open
live/marginal C tiles whose Y is open too (cleanable 0.0 on 27 of 33
live rows) — there the `other` branch and the pooled fallback carry
everything, and a measurement that pools the two populations says
nothing about either.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np

from holo.receiver.lib import spectral
from holo.receiver.plugins import calibrate as calibrate_plugin
from holo.receiver.plugins import tiles as tiles_plugin

from .types import (BRANCH_OTHER, Folds, Key, KnownFrame, PLANE_OF,
                    TileFootprint)

#: The four sibling states of a three-plane format.
N_STATES: int = 4
#: What :func:`sibling_state` returns where a sibling bit is unproven.
STATE_UNKNOWN: int = -1

#: `calibrate.branch_masks`'s dispatch value for C1.
BRANCH_STATE: str = "state"
#: The branch names C1 produces, in state order.
STATE_BRANCHES: tuple[str, ...] = tuple(f"s{state}" for state in
                                        range(N_STATES))

#: D1's floor, on the state's OWN select-fold classes (see the module
#: docstring for why it is not the discriminating minority).  Same
#: number as `calibrate.SELECT_MIN_MINORITY`, and deliberately a
#: separate constant: it counts a different thing.
PLATT_STATE_MIN_PER_CLASS: int = 40

#: `frame.furniture_kind` spelling, from `color_model.reference_states`.
FURNITURE_WORD: int = 0
FURNITURE_DUST: int = 1


def sibling_state(frame: KnownFrame, target_plane: int) -> np.ndarray:
    """``bits[left] + 2*bits[right]`` per cell, −1 where unproven.

    The siblings are `spectral.siblings_of(plane)` in ASCENDING plane
    order, so the low bit is always the lower-numbered sibling: for C
    (plane 0) that is M then Y, for M it is C then Y, for Y it is C then
    M.  The target plane's own bit is NEVER read here — that is the
    circularity `unmix`'s head arm refuses (unmix.py:345-354).
    """
    return sibling_state_of(frame.bits, frame.known, int(target_plane))


def sibling_state_of(bits: np.ndarray, known: np.ndarray,
                     target_plane: int) -> np.ndarray:
    """:func:`sibling_state` over the bare ``(bits, known)`` arrays.

    RULING 6 (B2) says there is ONE sibling-state convention and one
    helper for it.  `patchlocal.harvest_tile` holds `unmix._sample_frame`'s
    two arrays rather than a `KnownFrame`, and used to re-implement the
    body inline (review 2026-09-06); this is the seam that lets it call
    instead of copy.
    """
    left, right = spectral.siblings_of(int(target_plane))
    bits = np.asarray(bits, np.uint8)
    known = np.asarray(known, bool)
    proven = known[:, left] & known[:, right]
    state = (bits[:, left].astype(np.int8)
             + 2 * bits[:, right].astype(np.int8))
    return np.where(proven, state, np.int8(STATE_UNKNOWN)).astype(np.int8)


# ------------------------------------------------------- C1: the branches

def state_branch_masks(frame: KnownFrame, target_plane: int,
                       usable: np.ndarray) -> dict[str, np.ndarray]:
    """The SCORING populations of C1 — one per state, plus `other`.

    `other` is every usable cell whose siblings are not both proven; it
    is the same population `branch_masks`'s two-population split calls
    `other`, and on an open-Y tile it is the whole footprint.
    """
    usable = np.asarray(usable, bool)
    state = sibling_state(frame, target_plane)
    masks: dict[str, np.ndarray] = {}
    for index, name in enumerate(STATE_BRANCHES):
        masks[name] = usable & (state == index)
    masks[BRANCH_OTHER] = usable & (state < 0)
    return masks


def state_fit_masks(frame: KnownFrame, target_plane: int,
                    usable: np.ndarray, *, exclude_word_sites: bool = True,
                    ) -> dict[str, np.ndarray]:
    """The TRAIN populations of C1 — ruling 11's word-site exclusion.

    A word site renders one of the two reference states, so within a
    fixed sibling state its target bit is a CONSTANT: at a word site
    C == M and Y == 0, which puts every C word label of sibling state 0
    at C = 0 and every one of state 1 at C = 1.  Fitting a per-state map
    on those rows fits a map on a one-sided population — the exact
    condition `pava`'s own floors exist to refuse — while pretending to
    have hundreds of labels.  So they are dropped from the per-state
    fits (the ~13 dust cells per tile and every certified cargo
    projection stay), and the pooled fits keep them, unchanged.
    """
    masks = state_branch_masks(frame, target_plane, usable)
    kind = frame.furniture_kind
    if not exclude_word_sites or kind is None:
        return masks
    word = np.asarray(kind, np.int8) == FURNITURE_WORD
    return {name: (mask & ~word if name in STATE_BRANCHES else mask)
            for name, mask in masks.items()}


def fit_row_kinds(frame: KnownFrame, rows: np.ndarray) -> dict[str, int]:
    """How a train set splits into word / dust / cargo rows."""
    rows = np.asarray(rows, bool)
    kind = frame.furniture_kind
    total = int(np.count_nonzero(rows))
    if kind is None:
        furniture = np.asarray(frame.furniture, bool) & rows
        n_furniture = int(np.count_nonzero(furniture))
        return {"n_fit_word": 0, "n_fit_dust": n_furniture,
                "n_fit_cargo": total - n_furniture}
    kind = np.asarray(kind, np.int8)
    n_word = int(np.count_nonzero(rows & (kind == FURNITURE_WORD)))
    n_dust = int(np.count_nonzero(rows & (kind == FURNITURE_DUST)))
    return {"n_fit_word": n_word, "n_fit_dust": n_dust,
            "n_fit_cargo": total - n_word - n_dust}


# -------------------------------------------------- C2: state x context

def apply_state_context(llr: np.ndarray, bins: np.ndarray,
                        state: np.ndarray, frame: KnownFrame,
                        target_plane: int, folds: Folds,
                        usable: np.ndarray) -> tuple[np.ndarray, dict]:
    """A per-state 9-bin context residual, on top of the pooled one.

    `llr` has already been through `calibrate`'s pooled context stage, so
    what is fitted here is the RESIDUAL trend the pooled correction left
    on each state: production's variable (`bins`, provisional ink over
    present neighbours), production's solver
    (`pava._ordered_context_offsets` via `context_decision`, offsets
    bounded to ±4 and forced non-increasing in bin index) and
    production's four floors (80 search / 20 per class, 40 validation /
    10 per class), fitted on this footprint's FIT fold and validated on
    its SEARCH fold, once per state.

    A state that refuses keeps the pooled LLR exactly.  The pooled
    9-vector and the pooled verdict are NOT touched — `calibrate`
    publishes them unchanged under `ctx_offsets` / `ctx_adopted`, because
    `combine.pooled_ctx_offsets` and the L3 rung both refuse anything
    that is not one 9-vector.

    ONE DOCUMENTED SIDE EFFECT.  `apply_context_offsets` clamps every
    cell it touches to ±`CTX_LLR_CLAMP` (12), where an uncorrected cell
    sits at `ldpc.LLR_CLIP` (20).  A state adopted HERE where the pooled
    pass refused is therefore newly clamped from 20 to 12 — a real change
    to the cells of that state, and the price of using production's own
    application function rather than a private one.
    """
    llr = np.asarray(llr, np.float64)
    bins = np.asarray(bins, np.int8)
    state = np.asarray(state, np.int8)
    usable = np.asarray(usable, bool)
    labels_all = (np.asarray(frame.known[:, target_plane], bool) & usable
                  & (bins >= 0))
    values = np.asarray(frame.bits[:, target_plane], bool)
    ids = np.arange(bins.size, dtype=np.int64)

    by_state: list[tuple[float, ...] | None] = []
    adopted_flags: list[bool] = []
    reasons: list[str] = []
    fit_labels: list[int] = []
    baselines: list[float | None] = []
    candidates: list[float | None] = []
    n_applied = 0
    for index in range(N_STATES):
        mine = labels_all & (state == index)
        fit = mine & folds.fit
        validation = mine & folds.search
        fit_labels.append(int(np.count_nonzero(fit)))
        offsets, adopted, reason, baseline, candidate = \
            calibrate_plugin.context_decision(
                (llr[fit], bins[fit], values[fit], ids[fit]),
                (llr[validation], bins[validation], values[validation],
                 ids[validation]))
        adopted_flags.append(bool(adopted))
        reasons.append(str(reason))
        baselines.append(None if baseline is None else float(baseline))
        candidates.append(None if candidate is None else float(candidate))
        if not adopted:
            by_state.append(None)
            continue
        by_state.append(tuple(float(value) for value in offsets))
        mask = state == index
        n_applied += int(np.count_nonzero(mask & (bins >= 0)))
        llr = calibrate_plugin.apply_context_offsets(
            llr, np.where(mask, bins, np.int8(-1)).astype(np.int8), offsets)
    detail = {
        "ctx_offsets_by_state": tuple(by_state),
        "ctx_state_adopted": tuple(adopted_flags),
        "ctx_state_reason": tuple(reasons),
        "ctx_state_fit_labels": tuple(fit_labels),
        "ctx_state_baseline_logloss": tuple(baselines),
        "ctx_state_candidate_logloss": tuple(candidates),
        "ctx_state_any_adopted": bool(any(adopted_flags)),
        "ctx_state_cells_corrected": int(n_applied),
    }
    return llr, detail


# --------------------------------------------------- D1: per-state Platt

def state_platt_weights(stack: np.ndarray, values: np.ndarray,
                        state: np.ndarray, *,
                        pooled_fit: Callable[[np.ndarray, np.ndarray],
                                             tuple[np.ndarray, dict]],
                        ) -> tuple[np.ndarray, dict[int, np.ndarray] | None,
                                   dict]:
    """Pooled Platt weights first, then a per-state refit where it pays.

    `pooled_fit` is `combine._platt_weights` handed in as a callable —
    the import-direction ruling: this module is imported BY `combine`.

    The floor is the state's OWN ``min(n0, n1)`` on the select fold.  A
    state under it takes the pooled weights and says why; nothing is ever
    fitted on a one-sided population.
    """
    stack = np.asarray(stack, np.float64)
    values = np.asarray(values, np.uint8)
    state = np.asarray(state, np.int8)
    pooled, detail = pooled_fit(stack, values)
    pooled = np.asarray(pooled, np.float64)
    refused: dict[str, str] = {}
    weights: dict[str, tuple[float, ...]] = {}
    counts: dict[str, tuple[int, int]] = {}
    by_state: dict[int, np.ndarray] = {}
    for index in range(N_STATES):
        rows = state == index
        mine = values[rows]
        n_1 = int(mine.sum())
        n_0 = int(mine.size - n_1)
        counts[str(index)] = (n_0, n_1)
        if min(n_0, n_1) < PLATT_STATE_MIN_PER_CLASS:
            refused[str(index)] = "state_class_starved"
            continue
        fitted, _detail = pooled_fit(stack[:, rows], mine)
        by_state[index] = np.asarray(fitted, np.float64)
        weights[str(index)] = tuple(float(value) for value in fitted)
    detail = dict(detail)
    detail.update({"platt_state_counts": counts,
                   "platt_state_weights": weights,
                   "platt_state_refused": refused,
                   "platt_state_fitted": tuple(sorted(by_state))})
    return pooled, (by_state or None), detail


# ------------------------------------------- the state in the sequential domain

def sequential_state(frame: KnownFrame, fp: TileFootprint, row: Any,
                     geometry: Any, key: Key) -> np.ndarray:
    """The tile's own sibling state, in production's SEQUENTIAL domain.

    LANE-INDEPENDENT by construction: the scatter is over `in_tile`
    alone, never over a lane's `observed`, so one vector serves every
    lane of the key and the driver computes it once.  Un-permuting is
    `tiles._sequential_payload`, CALLED — the same declared deviation
    `calibrate.to_sequential` makes.

    The state is carried as ``state + 1`` through the float scatter (0 is
    "no cell here") and decoded back, so an unobserved or unproven
    position comes out as `STATE_UNKNOWN`.
    """
    page, ty, tx, stream = key
    if (int(fp.page), int(fp.ty), int(fp.tx)) != (int(page), int(ty),
                                                  int(tx)):
        raise ValueError(f"key {key} is not the footprint's tile "
                         f"({fp.page}, {fp.ty}, {fp.tx})")
    plane = PLANE_OF[str(stream)]
    state = sibling_state(frame, plane)
    cells = np.asarray(fp.page_cells_yx, np.int64)
    inside = np.asarray(fp.in_tile, bool)
    flat = ((cells[:, 0] % 64) * 64 + (cells[:, 1] % 64))[inside]
    dense = np.zeros(64 * 64, np.float64)
    dense_observed = np.zeros(64 * 64, bool)
    dense[flat] = state[inside].astype(np.float64) + 1.0
    dense_observed[flat] = True
    counter = row.tile_counter(int(page), int(ty), int(tx))
    sequential, observed = tiles_plugin._sequential_payload(
        row, geometry, counter, dense, dense_observed)
    out = np.where(np.asarray(observed, bool),
                   np.rint(np.asarray(sequential, np.float64)) - 1.0,
                   float(STATE_UNKNOWN)).astype(np.int8)
    out.setflags(write=False)
    return out


def state_summary(state: np.ndarray) -> dict[str, int]:
    """The two counts `blind_key` puts on a row's diag — never the vector."""
    values = np.asarray(state, np.int8)
    return {"n_state3": int(np.count_nonzero(values == 3)),
            "n_state_known": int(np.count_nonzero(values >= 0))}


def state_view(blind: Mapping[str, Any], rows: np.ndarray) -> np.ndarray:
    """`label_state` of one evidence's blind record, at `rows`.

    Returns an all-unknown vector when the arm published no state (an
    evidence from before C1, or a refused calibration), so a caller can
    always index it.
    """
    mine = np.asarray(blind.get("label_rows", ()), np.int64)
    state = np.asarray(blind.get("label_state", ()), np.int8)
    rows = np.asarray(rows, np.int64)
    if state.size != mine.size or not rows.size:
        return np.full(rows.size, np.int8(STATE_UNKNOWN), np.int8)
    return state[np.searchsorted(mine, rows)]

"""Score -> LLR, the fold discipline and the arm choice — DESIGN §4.7,
§4.8, §4.9.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`.  Every label this module fits on is a
`KnownFrame` bit: the format's own word/dust furniture, a certified
neighbour's projection, or the trusted metadata cell.  A test may compare
what comes out to the emitted field; the instrument may not.

FOUR THINGS LIVE HERE.

* :func:`split_folds` — DESIGN §4.8's three-way split.  A cell's fold is
  a hash of ``(seed, y, x)`` and nothing else, so it is the same in every
  footprint, lane, arm and pass the cell appears in; that is what makes
  "the offset search used the search fold and the arm choice used the
  select fold" mean anything across a whole run.

* :func:`calibrate` — PAVA, BRANCH-WISE.  `subtract` and `global` produce
  a score with TWO populations: cells whose siblings are known are
  cleaned exactly, cells whose siblings are unknown fall back to the
  projection (`spectral.plane_score`, src/holo/receiver/lib/spectral.py:173-201).
  One PAVA map over the union is a map fitted on a mixture and applied
  to another mixture — review blocker B12.  So each branch gets its own
  standardisation (`calibrate.window_scores`, one median and one MAD per
  branch) and its own map, each refusing below `pava`'s own floors rather
  than pooling to reach them.  A branch that refuses emits LLR 0 — the
  erasure spelling `tiles._attempt_stream` already understands.

* :func:`select_arm` — the paired test of DESIGN §4.8.  Arms are compared
  on PER-LABEL log losses over the SELECT fold, which no arm's search
  ever touched; a non-default arm is adopted only when the paired mean
  difference clears two standard errors, and the whole comparison is
  refused below 40 minority-class discriminating held-out labels (the
  corrected label arithmetic of DESIGN §1: at a word site C == M and
  Y == 0, so the labels that separate a plane from its confusable
  sibling are the ~13 dust cells per tile, not 120).

* :func:`to_sequential` — the un-permutation, and ONLY the un-permutation.
  Production's sequential domain is un-permuted and STILL DITHERED
  (PLAN §1.3); the single un-dither is `mother.to_mother`'s or
  `tile_codec.cmy8_decode_stream`'s.  This function therefore calls
  `tiles._sequential_payload` itself rather than restating it — the same
  declared deviation `mother.py` makes for `ldpc._bp_loop`: a private
  holo3 function is CALLED, never copied, so a format-side change cannot
  silently fork the analyzer.

DEVIATION RECORDED (PLAN §6, W1d).  DESIGN §4.7 wants production's
context variable fitted at LANE-PAGE scope, over every footprint of a
pass, behind `apply_region_context`'s adoption gate.  That scope is the
driver's (W2) — one footprint cannot see the lane-page.  `ctx_mode
="production"` therefore implements the PER-FOOTPRINT form: production's
kernel (`calibrate.context_neighbour_counts`), production's solver
(`pava._ordered_context_offsets` through `calibrate.context_decision`),
production's adoption gate and clamp (`calibrate.apply_context_offsets`),
fitted on this footprint's fit fold and validated on its search fold.
The scope is the deviation; the arithmetic is not.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from holo.receiver.lib import ldpc, pava
from holo.receiver.plugins import calibrate as calibrate_plugin
from holo.receiver.plugins import tiles as tiles_plugin

from . import statecal
from .residue import discriminating_mask
from .types import (BRANCH_ALL, BRANCH_CLEANABLE, BRANCH_OTHER, Evidence,
                    Folds, Key, KnownFrame, LaneFootprint, PageContext,
                    STREAMS, TileFootprint)

#: DESIGN §4.8's fold proportions.  Fit gets half because the PAVA map is
#: the only thing with enough parameters to want them; search and select
#: are model-comparison folds and split the rest evenly.
FOLD_FRACTIONS: tuple[float, float, float] = (0.5, 0.25, 0.25)

#: DESIGN §4.8: blind selection is refused below this many minority-class
#: discriminating held-out labels, and falls back to the pinned default.
SELECT_MIN_MINORITY: int = 40
#: "adopt a non-default arm only when the paired mean difference exceeds
#: 2 standard errors".
SELECT_SE_MULTIPLE: float = 2.0
#: The pinned default of DESIGN §4.8, as RULED 2026-09-03 from W1d's
#: parity measurement: `subtract+offset` with production's context
#: re-derived C 5/5, M 5/5, Y 5/5 on interior certified sheet-I tiles
#: where `subtract+committed` without context managed C 3/5, M 5/5,
#: Y 0/5.  The blind offset and the context correction are what make the
#: plane read certify at all, so they are the default, not extras.
DEFAULT_ARM: str = "subtract+offset"

#: Every register arm that MINIMISES an objective over the search fold
#: (the offset grids, the affine swim, the word pose): their
#: `heldout_logloss_search` is a minimum, not a held-out number, and
#: `select_arm` refuses to report it as nested CV.  Pinned against
#: `arms.REGISTER_ARMS` by a test (W8 B1).
SEARCHED_REGISTER_ARMS: tuple[str, ...] = (
    "offset", "field+offset", "field2+offset", "affine", "word")

#: DESIGN §4.7: a cleanable-fraction gap this wide between the labels the
#: map was fitted on and the cargo it is applied to is `extrapolating`.
EXTRAPOLATION_GAP: float = 0.2

#: RE-EXPORTED (W8 B2).  The three branch names now live in `types` so
#: that `statecal` — which `calibrate` dispatches into — can name
#: `BRANCH_OTHER` without importing this module.  Every caller that says
#: `calibrate.BRANCH_CLEANABLE` keeps working.
__all_branches__ = (BRANCH_CLEANABLE, BRANCH_OTHER, BRANCH_ALL)

#: `branches="state"` — C1's per-sibling-state calibration (W8 B2,
#: `statecal.state_branch_masks`): one PAVA map and one standardisation
#: per sibling state, plus `other` where the siblings are unproven.
BRANCH_STATE: str = statecal.BRANCH_STATE

#: Modes whose score carries the two populations of DESIGN §4.7/B12.
TWO_POPULATION_MODES: tuple[str, ...] = ("subtract", "global")

#: What `arms.evidence_for` asks for when nobody says otherwise (RULED
#: 2026-09-03 from the gate in `analyzer/GAPS-2026-09-03.md` §8): ONE map
#: over the footprint, which is what `plane_k.calibrated_rows` fits in
#: production.  Measured on sheet H's 60-tile C sample it is +1 certificate
#: over the split with zero regressions, and on sheet I's 20-per-stream
#: parity and sheet H's M/Y parity it moves nothing at all.  The split of
#: §4.7 stays reachable — `branches="subtract"` — and stays the thing the
#: extrapolation flags describe; it is no longer what the instrument fires
#: by default.
DEFAULT_BRANCHES: str = "pooled"

#: DESIGN §4.7 AMENDED (2026-09-03, from the GAPS measurement §3): the
#: two-population split may never ZERO a tile.  A branch that holds cells
#: but cannot fit its own map — no fit labels at all, or labels below
#: `pava`'s floors — is priced by the POOLED map over the footprint's
#: union instead of being erased, and the row records `branch_fallback`.
#: This is not the pooling §4.7 refuses: every branch that CAN fit keeps
#: its own map and its own standardisation, and the fallback only ever
#: replaces an LLR that would have been 0.  Measured: the erasure hit
#: 17 C, 18 M and 7 Y tiles of sheet H page 0 — every C and M one of them
#: production-certified — and one of them read R = 0, AUC = 0.5 on all
#: seven lanes with a perfectly good score.  ON by default.
STARVED_FALLBACK: bool = True

CTX_MODES: tuple[str, ...] = ("none", "ctx-known", "production", "page",
                              "local5")

#: DESIGN §4.7's own scope.  `production` fits the same variable, the same
#: solver and the same gate over ONE footprint (the W1d deviation recorded
#: in the module docstring); `page` fits it once per (lane, page, stream)
#: over a deterministic tile sample, which is `apply_region_context`'s
#: scope.  The fit itself is `arms.page_context` — it needs rasters, and
#: this module reads none.
CTX_PAGE: str = "page"

#: RULING 2026-09-03 (Germano): pose, page field and toner intensity are
#: LOCAL, so a fitted model takes a NEIGHBOURHOOD, not the sheet.  `local5`
#: fits the same 9-bin variable over the 5x5 tiles centred on the target
#: (`arms.local_context`, which reads rasters), SHRINKS it toward this
#: footprint's own fit by label count, and adopts the blend only when it
#: beats the footprint fit on the footprint's own held-out labels under
#: production's support floors.  NOT the default: the GAPS measurement §5
#: found the per-footprint fit 1.6% BETTER than a page-scope pooled one,
#: so borrowing is for LABEL-STARVED footprints, not for every footprint.
CTX_LOCAL: str = "local5"


class CalibrateError(RuntimeError):
    """The calibration cannot be done as asked."""


# ------------------------------------------------------------- the folds

_GOLDEN = np.uint64(0x9E3779B97F4A7C15)
_MIX_A = np.uint64(0xBF58476D1CE4E5B9)
_MIX_B = np.uint64(0x94D049BB133111EB)
_FNV = np.uint64(0x100000001B3)


def _mix64(value: np.ndarray) -> np.ndarray:
    """splitmix64's finaliser — a deterministic avalanche, no RNG."""
    v = (value + _GOLDEN).astype(np.uint64)
    v = ((v ^ (v >> np.uint64(30))) * _MIX_A).astype(np.uint64)
    v = ((v ^ (v >> np.uint64(27))) * _MIX_B).astype(np.uint64)
    return (v ^ (v >> np.uint64(31))).astype(np.uint64)


def fold_hash(page_cells_yx: np.ndarray, seed: int) -> np.ndarray:
    """A uniform [0, 1) draw per cell, a pure function of (seed, y, x)."""
    cells = np.asarray(page_cells_yx, np.int64)
    if not cells.shape[0]:
        return np.zeros(0, np.float64)
    state = _mix64(np.full(cells.shape[0], np.uint64(seed & ((1 << 64) - 1)),
                           np.uint64))
    state = _mix64(state ^ (cells[:, 0].astype(np.uint64) * _FNV))
    state = _mix64(state ^ cells[:, 1].astype(np.uint64))
    return (state >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)


def split_folds(page_cells_yx: np.ndarray, seed: int) -> Folds:
    """DESIGN §4.8's fit / search / select split, cell by cell."""
    draw = fold_hash(page_cells_yx, seed)
    first, second, _third = FOLD_FRACTIONS
    fit = draw < first
    search = (draw >= first) & (draw < first + second)
    select = draw >= first + second
    for array in (fit, search, select):
        array.setflags(write=False)
    return Folds(seed=int(seed), fit=fit, search=search, select=select)


# ------------------------------------------------------------ PAVA seams

def _standardise(score: np.ndarray) -> np.ndarray:
    """Production's one standardisation, on the ink-dark convention.

    `unmix_score` returns PLANE PRESENCE (high = ink); ink is dark, so the
    synthetic luma is its negation and `calibrate.window_scores` removes
    level and scale exactly as it does for a real grey window.  This is
    `plane_k.isolated_scores`'s second line, and a test pins the equality.
    """
    return np.asarray(
        calibrate_plugin.window_scores(np.asarray(-score, np.float32)),
        np.float64)


def _pava_map(scores: np.ndarray, labels: np.ndarray,
              ) -> tuple[np.ndarray, np.ndarray]:
    return pava._pava_nodes(np.asarray(scores, np.float32),
                            np.asarray(labels, np.float64))


def _logloss(llr: np.ndarray, labels: np.ndarray) -> float:
    return pava._binary_logloss(np.asarray(llr, np.float64),
                                np.asarray(labels, np.float64))


def _per_label_loss(llr: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """The per-label log loss `select_arm` pairs on (no mean taken)."""
    x = np.asarray(llr, np.float64)
    y = np.asarray(labels, np.float64)
    return np.logaddexp(0.0, x) - y * x


def fold_logloss(score: np.ndarray, frame: KnownFrame, target_plane: int,
                 folds: Folds, *, usable: np.ndarray | None = None,
                 fit_fold: str = "fit", eval_fold: str = "search",
                 ) -> float | None:
    """Fit a PAVA map on one fold's labels, score it on another's.

    THE OBJECTIVE OF EVERY SEARCH IN `arms.py` (DESIGN §4.8).  It is
    `plane_k.heldout_loss_at`'s shape — one PAVA fit per candidate, one
    held-out log loss — with production's site-parity split replaced by
    the analyzer's own three-way fold, so an offset chosen here has not
    seen the fold the arm choice is made on.  Returns None when either
    side is below `pava`'s floors: a refusal, never a fabricated number.
    """
    labels = np.asarray(frame.known[:, target_plane], bool)
    if usable is not None:
        labels = labels & np.asarray(usable, bool)
    finite = np.isfinite(np.asarray(score, np.float64))
    labels = labels & finite
    values = np.asarray(frame.bits[:, target_plane], np.float64)
    standard = _standardise(np.where(finite, score, 0.0))
    train = labels & folds.mask(fit_fold)
    test = labels & folds.mask(eval_fold)
    n_train_1 = int(values[train].sum())
    n_train_0 = int(np.count_nonzero(train) - n_train_1)
    if min(n_train_0, n_train_1) < pava.CAL_MIN_PER_CLASS:
        return None
    if int(np.count_nonzero(test)) < pava.CAL_MIN_HELDOUT:
        return None
    knots, probs = _pava_map(standard[train], values[train])
    probability = pava.calibration_probability(standard[test], knots, probs)
    return float(pava.probability_logloss(probability, values[test]))


# ----------------------------------------------------------- the context

def _known_neighbour_bins(page_cells_yx: np.ndarray, bits: np.ndarray,
                          known: np.ndarray) -> tuple[np.ndarray, int]:
    """DESIGN §4.7's `ctx-known` variable: 9 bins over KNOWN neighbours.

    Production's variable counts ink over neighbours PRESENT in the
    window, ink being the detector's own provisional decision.  This one
    counts ink over neighbours whose bit is PROVEN, and is eligible only
    where all eight are — a different, stricter variable, so DESIGN gives
    it a name of its own instead of folding it into the production arm.
    """
    counts_ink, present = calibrate_plugin.context_neighbour_counts(
        page_cells_yx, np.asarray(bits, bool) & np.asarray(known, bool))
    counts_known, _present = calibrate_plugin.context_neighbour_counts(
        page_cells_yx, np.asarray(known, bool))
    eligible = present & (counts_known == 8)
    bins = np.where(eligible, counts_ink, np.int8(-1)).astype(np.int8)
    return bins, int(np.count_nonzero(eligible))


def _production_bins(page_cells_yx: np.ndarray, llr: np.ndarray,
                     ) -> tuple[np.ndarray, int]:
    """Production's own variable: provisional ink over neighbours PRESENT."""
    counts, present = calibrate_plugin.context_neighbour_counts(
        page_cells_yx, np.asarray(llr, np.float64) > 0.0)
    bins = np.where(present, counts, np.int8(-1)).astype(np.int8)
    return bins, int(np.count_nonzero(present))


def _apply_context(llr: np.ndarray, bins: np.ndarray, frame: KnownFrame,
                   target_plane: int, folds: Folds,
                   usable: np.ndarray) -> tuple[np.ndarray, dict]:
    """`context_decision` on the fit fold, validated on the search fold."""
    labels = (np.asarray(frame.known[:, target_plane], bool) & usable
              & (bins >= 0))
    values = np.asarray(frame.bits[:, target_plane], bool)
    search = labels & folds.fit
    validation = labels & folds.search
    ids = np.arange(bins.size, dtype=np.int64)   # one footprint, one site
    offsets, adopted, reason, baseline, candidate = \
        calibrate_plugin.context_decision(
            (llr[search], bins[search], values[search], ids[search]),
            (llr[validation], bins[validation], values[validation],
             ids[validation]))
    detail = {
        "ctx_scope": "footprint",
        "ctx_adopted": bool(adopted), "ctx_reason": str(reason),
        "ctx_baseline_logloss": (None if baseline is None
                                 else float(baseline)),
        "ctx_candidate_logloss": (None if candidate is None
                                  else float(candidate)),
        "ctx_offsets": tuple(float(value) for value in offsets),
    }
    if not adopted:
        return llr, detail
    return calibrate_plugin.apply_context_offsets(llr, bins, offsets), detail


def _apply_page_context(llr: np.ndarray, bins: np.ndarray,
                        page_context: PageContext | None,
                        ) -> tuple[np.ndarray, dict]:
    """Apply a LANE-PAGE context correction that was fitted elsewhere.

    Nothing is fitted here: `arms.page_context` pooled the labels of a
    deterministic tile sample, ran `context_decision` once over that pool
    and already made the adoption call — which is what production does per
    region in `apply_region_context`.  A footprint that arrives without a
    page context is left EXACTLY as it was and says so; it is never
    silently re-fitted at footprint scope, because then the arm would not
    be the arm it is named.
    """
    if page_context is None:
        return llr, {"ctx_scope": "page", "ctx_adopted": False,
                     "ctx_reason": "no_page_context", "ctx_offsets": (),
                     "ctx_baseline_logloss": None,
                     "ctx_candidate_logloss": None}
    detail = {
        "ctx_scope": "page",
        "ctx_adopted": bool(page_context.adopted),
        "ctx_reason": str(page_context.reason),
        "ctx_baseline_logloss": page_context.baseline_logloss,
        "ctx_candidate_logloss": page_context.candidate_logloss,
        "ctx_offsets": tuple(float(value) for value in page_context.offsets),
        "ctx_page_tiles": len(page_context.tiles),
        "ctx_page_tiles_read": int(page_context.n_tiles_read),
        "ctx_page_fit_labels": int(page_context.n_fit_labels),
        "ctx_page_validation_labels": int(page_context.n_validation_labels),
    }
    if not page_context.adopted:
        return llr, detail
    offsets = np.asarray(page_context.offsets, np.float64)
    return calibrate_plugin.apply_context_offsets(llr, bins, offsets), detail


def _bin_counts(bins: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """How many labelled cells back each of the 9 context bins."""
    values = np.asarray(bins, np.int64)[np.asarray(mask, bool)]
    values = values[values >= 0]
    return np.bincount(values,
                       minlength=calibrate_plugin.N_CONTEXT_BINS).astype(
                           np.float64)[:calibrate_plugin.N_CONTEXT_BINS]


def _validation_gate(llr: np.ndarray, bins: np.ndarray, values: np.ndarray,
                     ids: np.ndarray, offsets: np.ndarray,
                     ) -> tuple[bool, str, float | None, float | None]:
    """`context_decision`'s validation half, on offsets fitted elsewhere.

    Production adopts a context correction only when it lowers the log
    loss on held-out labels with enough support of BOTH classes; a blended
    correction is not exempt from that just because half of it came from
    the neighbourhood, so it goes through the same floors and the same
    comparison — the only difference is that the offsets were not fitted
    on this footprint alone.
    """
    n_0, n_1 = calibrate_plugin.unique_class_support(values, ids)
    if n_0 + n_1 < calibrate_plugin.CTX_MIN_VALIDATION:
        return False, "insufficient_validation_support", None, None
    if min(n_0, n_1) < calibrate_plugin.CTX_MIN_VALIDATION_PER_CLASS:
        return False, "validation_class_starved", None, None
    weights = calibrate_plugin.site_weights(ids)
    baseline = float(pava._binary_logloss(llr, values, weights))
    candidate = float(pava._binary_logloss(
        llr + offsets[np.asarray(bins, np.int64)], values, weights))
    adopted = bool(candidate < baseline)
    return (adopted, "adopted" if adopted else "validation_gate_failed",
            baseline, candidate)


def _apply_local_context(llr: np.ndarray, bins: np.ndarray,
                         frame: KnownFrame, target_plane: int, folds: Folds,
                         usable: np.ndarray, local: Any,
                         ) -> tuple[np.ndarray, dict]:
    """The neighbourhood context of the 2026-09-03 ruling.

    Two fits meet here: this footprint's own (production's variable, its
    solver, its gate — exactly `_apply_context`) and the 5x5-tile
    neighbourhood's (`arms.local_context`).  The footprint's is the
    ANCHOR; the neighbourhood's is what a label-starved footprint borrows,
    per bin, in proportion to how many labels each side put in that bin:

        w_b = n_local_b / (n_local_b + n_footprint_b)

    so a bin this footprint knows well keeps its own number and a bin it
    has never seen takes the neighbourhood's.  The blend is then gated on
    this footprint's own held-out labels; if it does not win there, the
    footprint's own correction stands, and the mode degenerates EXACTLY
    to `production`.
    """
    labels = (np.asarray(frame.known[:, target_plane], bool) & usable
              & (bins >= 0))
    values = np.asarray(frame.bits[:, target_plane], bool)
    fit = labels & folds.fit
    validation = labels & folds.search
    ids = np.arange(bins.size, dtype=np.int64)
    own, own_adopted, own_reason, own_baseline, own_candidate = \
        calibrate_plugin.context_decision(
            (llr[fit], bins[fit], values[fit], ids[fit]),
            (llr[validation], bins[validation], values[validation],
             ids[validation]))
    detail: dict[str, Any] = {
        "ctx_scope": "local5",
        "ctx_footprint_adopted": bool(own_adopted),
        "ctx_footprint_reason": str(own_reason),
        "ctx_baseline_logloss": (None if own_baseline is None
                                 else float(own_baseline)),
        "ctx_candidate_logloss": (None if own_candidate is None
                                  else float(own_candidate)),
        "ctx_local_adopted": bool(getattr(local, "adopted", False)),
        "ctx_local_reason": str(getattr(local, "reason", "no_local_context")),
        "ctx_local_tiles_read": int(getattr(local, "n_tiles_read", 0)),
        "ctx_local_fit_labels": int(getattr(local, "n_fit_labels", 0)),
    }
    anchor = (np.asarray(own, np.float64) if own_adopted
              else np.zeros(calibrate_plugin.N_CONTEXT_BINS, np.float64))
    if local is None or not bool(getattr(local, "adopted", False)):
        detail["ctx_adopted"] = bool(own_adopted)
        detail["ctx_reason"] = str(own_reason)
        detail["ctx_offsets"] = tuple(float(value) for value in anchor)
        detail["ctx_blend_weights"] = ()
        if not own_adopted:
            return llr, detail
        return calibrate_plugin.apply_context_offsets(llr, bins, own), detail

    n_own = _bin_counts(bins, fit)
    n_local = np.asarray(local.bin_labels, np.float64)
    total = n_own + n_local
    weight = np.divide(n_local, total, out=np.zeros_like(total),
                       where=total > 0)
    blended = weight * np.asarray(local.offsets, np.float64) \
        + (1.0 - weight) * anchor
    adopted, reason, baseline, candidate = _validation_gate(
        llr[validation], bins[validation], values[validation],
        ids[validation], blended)
    detail.update({
        "ctx_blend_weights": tuple(float(value) for value in weight),
        "ctx_blend_baseline_logloss": baseline,
        "ctx_blend_candidate_logloss": candidate,
        "ctx_blend_adopted": bool(adopted),
        "ctx_blend_reason": str(reason),
    })
    if adopted:
        detail["ctx_adopted"] = True
        detail["ctx_reason"] = "local5_blend"
        detail["ctx_offsets"] = tuple(float(value) for value in blended)
        return calibrate_plugin.apply_context_offsets(llr, bins,
                                                      blended), detail
    detail["ctx_adopted"] = bool(own_adopted)
    detail["ctx_reason"] = (f"local5_refused:{reason}" if own_adopted
                            else str(own_reason))
    detail["ctx_offsets"] = tuple(float(value) for value in anchor)
    if not own_adopted:
        return llr, detail
    return calibrate_plugin.apply_context_offsets(llr, bins, own), detail


# --------------------------------------------------------- the main seam

def branch_masks(frame: KnownFrame, target_plane: int, mode: str,
                 usable: np.ndarray) -> dict[str, np.ndarray]:
    """The populations of DESIGN §4.7 (blocker B12), never pooled.

    `mode` is the unmix mode (so `subtract`/`global` get the two
    populations) or the literal `"state"`, which is C1: one population
    per SIBLING STATE plus `other`.  The state test comes FIRST — a
    caller who asked for states asked for states, whatever the unmix
    mode was.  `covered_cells` calls this same function, so extending it
    extends the coverage rebuild for free.
    """
    if mode == BRANCH_STATE:
        return statecal.state_branch_masks(frame, target_plane, usable)
    if mode in TWO_POPULATION_MODES:
        cleanable = np.asarray(frame.siblings, bool) & usable
        return {BRANCH_CLEANABLE: cleanable,
                BRANCH_OTHER: usable & ~cleanable}
    return {BRANCH_ALL: usable}


def _pseudo_arrays(pseudo: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(rows, bits, weights)` as arrays, empty when there is no pseudo."""
    if pseudo is None:
        return (np.zeros(0, np.int64), np.zeros(0, np.float64),
                np.zeros(0, np.float64))
    try:
        rows, bits, weights = pseudo
    except (TypeError, ValueError) as error:
        raise CalibrateError(
            "calibrate: `pseudo` must be the (rows, bits, weights) triple "
            "of `patch.pseudo_rows`") from error
    rows = np.asarray(rows, np.int64).ravel()
    bits = np.asarray(bits, np.float64).ravel()
    weights = np.asarray(weights, np.float64).ravel()
    if bits.size != rows.size or weights.size != rows.size:
        raise CalibrateError(
            f"calibrate: pseudo rows {rows.size}, bits {bits.size}, "
            f"weights {weights.size}")
    return rows, bits, weights


def _pseudo_fit_rows(mask: np.ndarray, labels_all: np.ndarray,
                     rows: np.ndarray, bits: np.ndarray, weights: np.ndarray,
                     ) -> tuple[np.ndarray, np.ndarray, int]:
    """The pseudo rows a branch's PAVA fit takes, replicated by weight.

    Inside `mask` (the branch's own cells) and NOT a label (a label beats
    a pseudo — the door drops those already, this is the second lock).
    Each row is repeated ``round(weight)`` times because `_pava_nodes`
    takes no sample weights.  Returns the repeated rows, their bits as
    values, and the DISTINCT count for the detail.
    """
    if not rows.size:
        return np.zeros(0, np.int64), np.zeros(0, np.float64), 0
    keep = np.asarray(mask, bool)[rows] & ~np.asarray(labels_all, bool)[rows]
    rows, bits, weights = rows[keep], bits[keep], weights[keep]
    repeats = np.maximum(np.rint(weights).astype(np.int64), 0)
    return (np.repeat(rows, repeats), np.repeat(bits, repeats),
            int(rows.size))


def calibrate(score: np.ndarray, frame: KnownFrame, target_plane: int,
              lfp: LaneFootprint, folds: Folds, *,
              branches: str = "auto",
              ctx_mode: str = "none",
              page_context: PageContext | None = None,
              local_context: Any = None,
              starved_fallback: bool = STARVED_FALLBACK,
              stream_id: str | None = None,
              ctx_state: bool = False,
              pseudo: Any = None,
              ) -> tuple[np.ndarray, dict]:
    """Presence scores -> calibrated LLR over the footprint, plus diag.

    `branches` is the unmix MODE (so the two-population rule of §4.7
    fires for `subtract`/`global`), the literal `"pooled"` to force one
    map over everything, or `"state"` for C1's per-sibling-state maps.
    The returned LLR is 0 wherever no accepted branch covers the cell —
    the erasure spelling — and is clipped at `ldpc.LLR_CLIP` everywhere
    else.

    `ctx_mode="page"` applies `page_context` — a correction fitted once
    per (lane, page, stream) by `arms.page_context`, DESIGN §4.7's own
    scope — instead of fitting one on this footprint's labels.

    `ctx_state` (C2) adds a per-state 9-bin residual on top of whatever
    the pooled context stage did, for the production-variable modes only.
    It never changes `ctx_offsets` or `ctx_adopted`: those stay the
    POOLED 9-vector and the pooled verdict, which is what
    `combine.pooled_ctx_offsets` and the L3 rung consume.

    `pseudo` (W8 B4) is the decoder's pseudo labels in FOOTPRINT rows,
    ``(rows, bits, weights)`` from `patch.pseudo_rows` through the typed
    door in `arms.evidence_for`.  They join the PAVA TRAINING SET of the
    branch that holds them, each replicated ``round(weight)`` times
    (`pava._pava_nodes` is unweighted), with the pseudo bit as the value.
    Everything else stays on the halo labels alone: the floors, every
    `n_labels*` count, the context fit, the held-out log losses and the
    select-fold `label_*` arrays (a pseudo row is in-tile cargo, never a
    known cell, so it can never be a label row).  `label_llr` is the
    held-out VIEW of the refitted map and may move with it.
    """
    pseudo_rows, pseudo_bits, pseudo_weights = _pseudo_arrays(pseudo)
    if ctx_mode not in CTX_MODES:
        raise CalibrateError(f"unknown ctx_mode {ctx_mode!r}")
    score = np.asarray(score, np.float64)
    n = score.size
    observed = np.asarray(lfp.observed, bool)
    if observed.size != n:
        raise CalibrateError(
            f"score has {n} entries, the lane footprint observes "
            f"{observed.size}")
    usable = observed & np.isfinite(score)
    stream = stream_id or (frame.target[3] if frame.target is not None
                           else STREAMS[target_plane])
    labels_all = np.asarray(frame.known[:, target_plane], bool) & usable
    values = np.asarray(frame.bits[:, target_plane], np.float64)
    masks = ({BRANCH_ALL: usable} if branches == "pooled"
             else branch_masks(frame, target_plane, str(branches), usable))
    #: RULING 11 (W8 B2): a per-state map is TRAINED on a mask that drops
    #: the word sites, because a word site's target bit is a constant
    #: within a sibling state; every other mode trains on what it scores.
    fit_masks = (statecal.state_fit_masks(frame, target_plane, usable)
                 if str(branches) == BRANCH_STATE else masks)

    llr = np.zeros(n, np.float64)
    covered = np.zeros(n, bool)
    branch_detail: dict[str, Any] = {}
    for name, mask in masks.items():
        rows = np.flatnonzero(mask)
        if not rows.size:
            branch_detail[name] = {"n_cells": 0, "accepted": False,
                                   "reason": "empty_branch"}
            continue
        standard = np.zeros(n, np.float64)
        standard[rows] = _standardise(score[rows])
        train = fit_masks.get(name, mask) & labels_all & folds.fit
        heldout = mask & labels_all & folds.search
        n_train_1 = int(values[train].sum())
        n_train_0 = int(np.count_nonzero(train) - n_train_1)
        n_heldout = int(np.count_nonzero(heldout))
        reason = "accepted"
        if min(n_train_0, n_train_1) < pava.CAL_MIN_PER_CLASS:
            reason = "search_class_starved"
        elif n_heldout < pava.CAL_MIN_HELDOUT:
            reason = "heldout_starved"
        p_rows, p_values, n_pseudo = _pseudo_fit_rows(
            mask, labels_all, pseudo_rows, pseudo_bits, pseudo_weights)
        branch_detail[name] = {
            "n_cells": int(rows.size), "n_fit_0": n_train_0,
            "n_fit_1": n_train_1, "n_heldout": n_heldout,
            "n_pseudo_fit": n_pseudo,
            "accepted": reason == "accepted", "reason": reason,
            **statecal.fit_row_kinds(frame, train)}
        if reason != "accepted":
            continue
        knots, probs = _pava_map(
            np.concatenate((standard[train], standard[p_rows])),
            np.concatenate((values[train], p_values)))
        llr[rows] = np.clip(
            pava.calibration_llr(standard[rows], knots, probs),
            -ldpc.LLR_CLIP, ldpc.LLR_CLIP)
        covered[rows] = True

    # THE STARVED BRANCH (`analyzer/GAPS-2026-09-03.md` §3).  A branch that
    # holds cells but no labels is refused `search_class_starved` and its
    # cells are erased — and when the halo is fully sibling-proven and the
    # target's siblings are not, that branch is the WHOLE TARGET TILE: 17
    # of sheet H's 1,961 C tiles, 18 M and 7 Y, every one of which
    # production certified.  Erasing a tile the score reads perfectly well
    # is not the conservatism §4.7 asked for, so the refused cells are
    # priced by ONE map fitted over the union — the map `branches="pooled"`
    # would have used — and the row says so.  The accepted branches keep
    # their own maps: this only ever fills what would have been zero.
    fallback_detail: dict[str, Any] | None = None
    if starved_fallback:
        missing = usable & ~covered
        starved = any(not entry.get("accepted", False)
                      and int(entry.get("n_cells", 0)) > 0
                      for entry in branch_detail.values())
        if starved and np.any(missing):
            rows = np.flatnonzero(usable)
            standard = np.zeros(n, np.float64)
            standard[rows] = _standardise(score[rows])
            train = usable & labels_all & folds.fit
            heldout = usable & labels_all & folds.search
            n_train_1 = int(values[train].sum())
            n_train_0 = int(np.count_nonzero(train)) - n_train_1
            n_heldout = int(np.count_nonzero(heldout))
            reason = "accepted"
            if min(n_train_0, n_train_1) < pava.CAL_MIN_PER_CLASS:
                reason = "search_class_starved"
            elif n_heldout < pava.CAL_MIN_HELDOUT:
                reason = "heldout_starved"
            p_rows, p_values, n_pseudo = _pseudo_fit_rows(
                usable, labels_all, pseudo_rows, pseudo_bits,
                pseudo_weights)
            fallback_detail = {
                "n_cells": int(np.count_nonzero(missing)),
                "n_fit_0": n_train_0, "n_fit_1": n_train_1,
                "n_heldout": n_heldout, "n_pseudo_fit": n_pseudo,
                "accepted": reason == "accepted", "reason": reason}
            if reason == "accepted":
                fill = np.flatnonzero(missing)
                knots, probs = _pava_map(
                    np.concatenate((standard[train], standard[p_rows])),
                    np.concatenate((values[train], p_values)))
                llr[fill] = np.clip(
                    pava.calibration_llr(standard[fill], knots, probs),
                    -ldpc.LLR_CLIP, ldpc.LLR_CLIP)
                covered[fill] = True

    detail: dict[str, Any] = {"branches": branch_detail,
                              "branch_fallback": fallback_detail,
                              "n_observed": int(np.count_nonzero(observed)),
                              "n_calibrated": int(np.count_nonzero(covered)),
                              "n_pseudo_rows": int(pseudo_rows.size)}

    # the context, on the cells a branch actually priced
    ctx_detail: dict[str, Any] = {"ctx_mode": ctx_mode, "n_ctx_eligible": 0,
                                  "ctx_adopted": False}
    if ctx_mode == "ctx-known":
        bins, eligible = _known_neighbour_bins(
            frame_cells(frame, lfp), frame.bits[:, target_plane],
            frame.known[:, target_plane])
    elif ctx_mode in ("production", CTX_PAGE, CTX_LOCAL):
        bins, eligible = _production_bins(frame_cells(frame, lfp), llr)
    else:
        bins, eligible = None, 0
    if bins is not None:
        bins = np.where(covered, bins, np.int8(-1)).astype(np.int8)
        eligible = int(np.count_nonzero(bins >= 0))
        if ctx_mode == CTX_PAGE:
            llr, applied = _apply_page_context(llr, bins, page_context)
        elif ctx_mode == CTX_LOCAL:
            llr, applied = _apply_local_context(
                llr, bins, frame, target_plane, folds, covered,
                local_context)
        else:
            llr, applied = _apply_context(llr, bins, frame, target_plane,
                                          folds, covered)
        ctx_detail.update(applied)
        ctx_detail["n_ctx_eligible"] = eligible
        # C2 (W8 B2).  A per-state residual on top of the pooled
        # correction, for production's variable only: `ctx-known` is a
        # different variable and `none` has no bins.  `ctx_offsets` and
        # `ctx_adopted` above are LEFT ALONE — they are the pooled
        # 9-vector `combine.pooled_ctx_offsets` sums and L3 shifts.
        if ctx_state and ctx_mode in ("production", CTX_PAGE, CTX_LOCAL):
            llr, state_applied = statecal.apply_state_context(
                llr, bins, statecal.sibling_state(frame, target_plane),
                frame, target_plane, folds, covered)
            ctx_detail.update(state_applied)
    ctx_detail.setdefault("ctx_state_any_adopted", False)
    detail.update(ctx_detail)

    # blind label bookkeeping (DESIGN §4.9)
    in_tile = np.asarray(lfp.tile.in_tile, bool)
    cargo_mask = np.asarray(lfp.tile.cargo, bool)
    discriminating = discriminating_mask(frame.bits, frame.known, stream)
    labels_cleanable = float(np.count_nonzero(
        labels_all & frame.siblings) / max(1, np.count_nonzero(labels_all)))
    cargo_cells = usable & in_tile & cargo_mask
    cargo_cleanable = float(np.count_nonzero(
        cargo_cells & frame.siblings) / max(1, np.count_nonzero(cargo_cells)))
    detail.update({
        "n_labels": int(np.count_nonzero(labels_all)),
        "n_labels_fit": int(np.count_nonzero(labels_all & folds.fit)),
        "n_labels_search": int(np.count_nonzero(labels_all & folds.search)),
        "n_labels_select": int(np.count_nonzero(labels_all & folds.select)),
        "n_discriminating": int(np.count_nonzero(
            discriminating & usable & ~in_tile)),
        "n_discriminating_select": int(np.count_nonzero(
            discriminating & usable & folds.select)),
        "labels_cleanable_fraction": labels_cleanable,
        "cargo_cleanable_fraction": cargo_cleanable,
        "extrapolating": bool(
            abs(labels_cleanable - cargo_cleanable) > EXTRAPOLATION_GAP),
        "n_cargo_observed": int(np.count_nonzero(cargo_cells)),
    })
    for fold_name in ("search", "select"):
        mask = labels_all & folds.mask(fold_name) & covered
        detail[f"heldout_logloss_{fold_name}"] = (
            float(_logloss(llr[mask], values[mask]))
            if int(np.count_nonzero(mask)) >= pava.CAL_MIN_HELDOUT else None)
    rows = np.flatnonzero(labels_all & folds.select & covered)
    detail["label_rows"] = rows
    detail["label_values"] = values[rows].astype(np.uint8)
    detail["label_llr"] = llr[rows]
    detail["label_discriminating"] = discriminating[rows]
    #: W8 B2 (D1): the SIBLING STATE of each select-fold label row, so
    #: `combine`'s `platt-state` can weight per state without recomputing
    #: a frame it does not have.  Lane-independent (the frame is), int8,
    #: −1 where the siblings are unproven — one more small array beside
    #: the four that already ride the row.
    detail["label_state"] = statecal.sibling_state(frame,
                                                   target_plane)[rows]
    llr.setflags(write=False)
    return llr, detail


def covered_cells(frame: KnownFrame, target_plane: int, branches: str,
                  lfp: LaneFootprint, score: np.ndarray,
                  detail: Mapping[str, Any]) -> np.ndarray:
    """Which cells a :func:`calibrate` call actually priced.

    `calibrate` returns the mask only implicitly — LLR 0 is the erasure
    spelling, but a priced cell may legitimately BE 0 — so a caller that
    needs the mask (the page-scope context fit, which must not fit on
    erased cells) rebuilds it from the same branch masks and the
    per-branch acceptance the detail already carries.  No pixels, no
    labels: the arithmetic is the same in both places or the test fails.
    """
    usable = np.asarray(lfp.observed, bool) & np.isfinite(
        np.asarray(score, np.float64))
    masks = ({BRANCH_ALL: usable} if branches == "pooled"
             else branch_masks(frame, target_plane, str(branches), usable))
    covered = np.zeros(usable.size, bool)
    branch_detail = detail.get("branches", {}) or {}
    for name, mask in masks.items():
        if bool((branch_detail.get(name) or {}).get("accepted")):
            covered |= np.asarray(mask, bool)
    if bool((detail.get("branch_fallback") or {}).get("accepted")):
        covered |= usable
    return covered


def frame_cells(frame: KnownFrame, lfp: LaneFootprint) -> np.ndarray:
    """The page cells the frame and the lane footprint share."""
    del frame
    return np.asarray(lfp.tile.page_cells_yx, np.int64)


# ------------------------------------------------------- the arm choice

def select_arm(candidates: Sequence[Evidence], folds: Folds,
               ) -> tuple[Evidence, dict]:
    """DESIGN §4.8's paired test on the SELECT fold.

    Every candidate carries `label_rows` / `label_values` / `label_llr`
    over ITS select fold; the test pairs them by footprint row, so two
    arms are compared on the same labels and nothing else.  The default
    arm wins every tie and every refusal.
    """
    if not candidates:
        raise CalibrateError("select_arm: no candidates")
    del folds                              # the fold is already in the rows
    default = next((item for item in candidates
                    if item.arm == DEFAULT_ARM), candidates[0])
    detail: dict[str, Any] = {
        "n_candidates": len(candidates), "default_arm": default.arm,
        "selection_refused": False, "comparisons": {}}
    base_rows = np.asarray(default.blind.get("label_rows", ()), np.int64)
    base_values = np.asarray(default.blind.get("label_values", ()), np.uint8)
    base_llr = np.asarray(default.blind.get("label_llr", ()), np.float64)
    base_discriminating = np.asarray(
        default.blind.get("label_discriminating", ()), bool)
    minority = _minority_count(base_values[base_discriminating]
                              if base_discriminating.size == base_values.size
                              else base_values)
    detail["n_minority_discriminating_select"] = int(minority)
    if minority < SELECT_MIN_MINORITY:
        detail["selection_refused"] = True
        detail["refusal_reason"] = "below_minority_floor"
        return default, detail

    winner = default
    default_loss = float(np.mean(_per_label_loss(base_llr, base_values))) \
        if base_llr.size else float("inf")
    #: The running best is compared PAIRED — over the labels the two arms
    #: share — because an arm's mean over its own label set is a mean
    #: over a different set of cells, and the easier set would win on
    #: nothing but its cells.  `default_select_logloss` stays the
    #: default's own full-fold number, for the reader.
    winner_loss = float("inf")
    winner_margin = 0.0
    detail["default_select_logloss"] = default_loss
    for candidate in candidates:
        if candidate is default:
            continue
        rows = np.asarray(candidate.blind.get("label_rows", ()), np.int64)
        llr = np.asarray(candidate.blind.get("label_llr", ()), np.float64)
        values = np.asarray(candidate.blind.get("label_values", ()), np.uint8)
        shared, left, right = np.intersect1d(
            base_rows, rows, assume_unique=True, return_indices=True)
        if shared.size < pava.CAL_MIN_HELDOUT:
            detail["comparisons"][candidate.arm] = {
                "n_paired": int(shared.size), "adopted": False,
                "reason": "too_few_paired_labels"}
            continue
        mine = _per_label_loss(llr[right], values[right])
        theirs = _per_label_loss(base_llr[left], base_values[left])
        difference = theirs - mine            # positive = candidate better
        mean = float(np.mean(difference))
        se = float(np.std(difference, ddof=1) / np.sqrt(difference.size)) \
            if difference.size > 1 else float("inf")
        adopted = bool(mean > SELECT_SE_MULTIPLE * se and se > 0.0)
        detail["comparisons"][candidate.arm] = {
            "n_paired": int(shared.size), "mean_difference": mean,
            "standard_error": se, "adopted": adopted,
            "select_logloss": float(np.mean(mine))}
        if adopted and mean > winner_margin:
            winner = candidate
            winner_margin = mean
            winner_loss = float(np.mean(mine))
    detail["winner"] = winner.arm
    detail["winner_select_logloss"] = (default_loss if winner is default
                                       else winner_loss)
    #: DESIGN §4.8 wants a nested loss for the winner, "never the
    #: minimum".  `heldout_logloss_search` is exactly the minimum for an
    #: arm that SEARCHED the search fold, so it is refused there instead
    #: of being reported as if it were held out.  W8 B1 widened the list
    #: from `offset`/`field+offset` to EVERY searching register arm (a
    #: pre-existing gap the patch arms would otherwise inherit); the
    #: review of 2026-09-06 widened it again to every arm that chose its
    #: OWN KNOBS — `autoknobs.choose` walks the search fold too, so an
    #: auto arm's search loss is a minimum over its candidate set exactly
    #: as an offset grid's is over its poses.
    searched_registration = str(winner.blind.get("register_arm", "")) in \
        SEARCHED_REGISTER_ARMS
    searched_knobs = bool(winner.blind.get("auto_choices"))
    detail["nested_cv_logloss"] = (
        None if (searched_registration or searched_knobs)
        else winner.blind.get("heldout_logloss_search"))
    detail["nested_cv_refused"] = (
        "winner_minimised_the_search_fold" if searched_registration else
        "winner_chose_its_own_knobs_on_the_search_fold" if searched_knobs
        else None)
    return winner, detail


def _minority_count(values: np.ndarray) -> int:
    v = np.asarray(values, np.uint8)
    if not v.size:
        return 0
    ones = int(v.sum())
    return min(ones, int(v.size - ones))


# ------------------------------------------------------ the un-permuting

def to_sequential(llr_footprint: np.ndarray, lfp: LaneFootprint, row: Any,
                  geometry: Any, key: Key) -> tuple[np.ndarray, np.ndarray]:
    """Footprint LLRs -> production's SEQUENTIAL domain (PLAN §1.3).

    Un-permutes and NOTHING ELSE: the dither stays, because production's
    sequential domain is the as-printed one and `mother.to_mother` /
    `tile_codec.cmy8_decode_stream` own the single un-dither.  The scatter
    itself is `tiles._sequential_payload`, CALLED — a private holo3
    function, the same declared deviation `mother.py` makes for
    `ldpc._bp_loop`, and the only way this cannot fork.
    """
    page, ty, tx, _stream = key
    tile: TileFootprint = lfp.tile
    if (int(tile.page), int(tile.ty), int(tile.tx)) != (int(page), int(ty),
                                                        int(tx)):
        raise CalibrateError(
            f"key {key} is not the footprint's tile "
            f"({tile.page}, {tile.ty}, {tile.tx})")
    values = np.asarray(llr_footprint, np.float64)
    cells = np.asarray(tile.page_cells_yx, np.int64)
    inside = np.asarray(tile.in_tile, bool) & np.asarray(lfp.observed, bool)
    inside = inside & np.isfinite(values)
    flat = ((cells[:, 0] % 64) * 64 + (cells[:, 1] % 64))[inside]
    dense = np.zeros(64 * 64, np.float64)
    dense_observed = np.zeros(64 * 64, bool)
    dense[flat] = values[inside]
    dense_observed[flat] = True
    counter = row.tile_counter(int(page), int(ty), int(tx))
    sequential, observed = tiles_plugin._sequential_payload(
        row, geometry, counter, dense, dense_observed)
    sequential = np.asarray(sequential, np.float64)
    sequential[~observed] = 0.0
    sequential.setflags(write=False)
    observed = np.asarray(observed, bool)
    observed.setflags(write=False)
    return sequential, observed


def observed_fraction(observed: np.ndarray) -> float:
    values = np.asarray(observed, bool)
    return float(np.count_nonzero(values)) / max(1, values.size)


def blind_summary(detail: Mapping[str, Any]) -> dict:
    """The ledger-safe half of a calibration diag (arrays dropped)."""
    return {name: value for name, value in detail.items()
            if not isinstance(value, np.ndarray)}

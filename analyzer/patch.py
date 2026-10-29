"""The patch family — DESIGN §13's "patch discriminant", BUILT (W8 B1).

BLIND.  Nothing here may import :mod:`analyzer.truth`,
:mod:`analyzer.oracle` or :mod:`analyzer.score`; nothing here imports
:mod:`analyzer.arms` or :mod:`analyzer.unmix` either (both dispatch into
this module).  Every label a fit sees is a `KnownFrame` bit on the FIT
fold: a certified neighbour's projection, a dust cell, the metadata cell
— never the target tile's own cargo, and never a search- or select-fold
row.

WHY (MEASUREMENTS-2026-09-06-C-THIRD-LAYER §3-§5b).  On sheet H a C cell
whose siblings M and Y are both inked has NO dot core: the third toner
layer is a flat red deficit at ~60 % of a single layer's strength, spread
over the cell and its surround.  The 0.7-cell box aperture every existing
arm reads through sees it at 60 % and the band's M+Y cells come out at
0.214 error against 0.05-0.07 for every other state.  A LEARNED linear
discriminant over the raw red patch in cell coordinates — per lane, per
plane, per sibling state — read the same cells at 0.149 in a single lane
(0.119 halo-trained with no label from the tile, 0.062 combined over the
4800 lanes), because the filter's residual errors are capture noise and
average out where the box mean's are print-frozen.  The permutation
control read 0.46.  This module is that filter, blind.

WHAT IT IS.  For each footprint cell a (window_cells x window_cells)
patch of the RAW crop is resampled at the read's pose — the cell's posed
centre plus a pixel-step grid pushed through the owner's own 2x2
cell->pixel map, bilinear (`ndimage.map_coordinates`, order 1), bounds
checked FIRST and never clamped: the arithmetic
`color_region_anchor.rectified_ncc` already uses, a reuse.  Per sibling
state the fit-fold labelled rows train a standardised shrinkage-LDA
(the measurement's `fit_lda`, ported verbatim from
`measure/c-third-layer-20260906/analyze_selftrain.py`), threshold at the
midpoint of the class-mean scores, presence HIGH = INK like every other
unmix mode.

THE FOLD CONTRACT FOR A FITTED SCORE (APPROACHES §4.0 ruling 7).  A
fitted score changes what "the fit fold" means: the PAVA map that
`calibrate` fits on fit-fold labels may not see the discriminant's OWN
training rows scored in-sample, or the calibration is a map of the
filter's overfit.  So every population CROSS-FITS inside the fit fold —
the fit-fold labelled rows are split into halves A and B by
`fold_hash(cells, seed ^ CROSSFIT_SALT) < 0.5`; the filter fitted on A
scores B and the one fitted on B scores A, so every fit-fold labelled
row carries an OUT-OF-FOLD score; the full filter (A ∪ B) scores every
other row (cargo, search, select).  PAVA, the context fit and every
search objective see only those scores.  The in-sample and cross-fit
fit-fold errors are both published so the gap is a ledger column.

ONE SHARED SCALE (DESIGN §4.7's B12 note, restated).  The per-state
filters, and the `subtract` fallback where nothing fits, are DIFFERENT
scores with different units; one pooled PAVA map over their union is a
map fitted on a mixture.  Every population is therefore put on a common
footing before it leaves this module: a fitted state's scores are divided
by the sd of its own out-of-fold fit-fold scores (`Discriminant.scale`),
and the fallback population is centred at the midpoint of its own
fit-fold class means and divided by their sd.  C1's per-state branches
(`calibrate(branches="state")`) are the natural companion; this only
makes the pooled map honest.

THE LADDER per cell: per-state filter where the state is known and the
tier is ADMITTED (below), with both classes ≥ `min_per_class` in every
half → (B3: the state-agnostic filter) →
`spectral.plane_score(MODE_SUBTRACT)` for everything else, including
rows whose patch leaves the crop.  Word sites (`furniture_kind == 0`)
are EXCLUDED from the per-state train sets (ruling 11: a word site
carries one target class per sibling state), dust and cargo projections
stay, and the counts are reported per state.

SELF-DISCOVERY (W8 B7, the user's ruling of 2026-09-06).  None of the
numbers above is a pin a run has to accept.  A knob set to `"auto"`
keeps its module constant as the INHERITED FALLBACK and hands the axis
to `analyzer.autoknobs`, which fits every candidate on the fit fold
(cross-fit, as ruling 7 demands) and chooses on the SEARCH fold by a
paired log-loss test with the `select_arm` standard-error margin — per
(lane, plane, sibling state, tile), one coordinate pass, ties to the
inherited value.  The SEARCH fold and not the select fold (review
2026-09-06): a knob walk is a within-arm search, DESIGN §4.8 gives those
the search fold, and the select fold stays what it is — the fold the ARM
choice and the lane weights are made on, which no search has touched.
`min_labels_per_state` / `min_labels_agnostic` under `"auto"` are not
counts at all: the tier is fitted, and then ADMITTED by `autoknobs.admit`
on its own cross-fit numbers AND against the score its cells would
otherwise carry, or its cells fall to the next tier.  Every choice and
every candidate loss is in the blind detail under `auto_choices` /
`auto_losses`; with nothing auto this module is B1/B3's own code path,
byte for byte.

HOW THAT WALK DECIDES (HALO-CHANNEL-2026-09-07; the mechanism is
`analyzer.walkeval` and `analyzer.patchwalk`, this module dispatches).
The paragraph above describes the arbitration correctly and the
POPULATION it ran on wrongly: the halo's labels are 4.3-4.8x easier than
the dead band's three-ink cargo the filter will price.  Three named
changes, all on the SEARCH fold, all behind operator knobs — the walk's
losses may be weighted to the target tile's own cargo
(`walk_weighting`), a population that cannot carry its own vote may
inherit the POOLED walk's discovery instead of a module constant
(`walk_franchise`), and the nested channel axis may put the burden of
proof on the leaner side (`walk_direction`).  The last two SHIP ON, by a
pre-registered isolation; naming all three restores the walk above
exactly.  One change is not a knob: the REGULARISER is minimised INSIDE
every candidate rather than after all of them, so no candidate is judged
at another candidate's ridge — a run that NAMES `patch_shrinkage` is
unaffected, which the null proof pins.  `auto_source` and
`auto_verdicts` are what make a vote countable apart from an
inheritance.

DETERMINISM.  No RNG anywhere: the halves are `calibrate.fold_hash`, the
folds and the candidate walk are deterministic, the solve is a dense
ridge system, and a repeat call is `np.array_equal`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from holo.receiver.lib import spectral

from . import autoknobs
from . import calibrate as cal
from . import patchcache
from . import patchwalk
from . import statecal
from . import walkeval
# W8 B7: the discriminant moved to `autoknobs` (the selector fits
# candidates and may not import the module that dispatches into it); the
# spelling `patch.fit_discriminant` / `patch.crossfit_scores` /
# `patch.Discriminant` / `patch.CROSSFIT_SALT` /
# `patch.MIN_PER_CLASS_PER_HALF` is preserved by this re-export.
from .autoknobs import (AUTO, CROSSFIT_SALT, Discriminant,
                        MIN_PER_CLASS_PER_HALF, apply_discriminant,
                        crossfit_scores, fit_discriminant, is_auto)
from .patchfit import (MIXTURE_INIT_PERCENTILES, MIXTURE_MIN_CELLS,
                       MIXTURE_STATE, MIXTURE_STEPS, fallback_population,
                       fit_population, mixture_score, sd_or_one)
from .patchgrid import (PatchError, extract, grid_cells, grid_shape,
                        ring_features, ring_matrix)
# W8, review 2026-09-06: the KNOB layer (the spec, what a knob bag means,
# and the walk's bounding geometry) moved to `patchspec` when this file
# went past the 1000-line cap again; every name is re-exported here, so
# `patch.PatchSpec`, `patch.spec_from_knobs`, `patch.pseudo_rows` and
# every constant stay the spelling for every caller and every test.
from .patchspec import (AUTO_AXES, CHANNEL_SETS,
                        DEFAULT_MIN_LABELS_AGNOSTIC,
                        DEFAULT_MIN_LABELS_PER_STATE,
                        DEFAULT_SAMPLES_PER_CELL, DEFAULT_SHRINKAGE,
                        DEFAULT_WINDOW_CELLS, FEATURE_KINDS, LABELS_FROM_BP,
                        LABELS_FROM_HALO, LABELS_FROM_LOCAL5,
                        LABELS_FROM_SELF, PATCH_MODES, PatchSpec,
                        SEARCH_MODES, TRAIN_SCOPES, UNMIX_PURE,
                        WALK_KNOBS, WALK_WEIGHTING_CARGO,
                        feature_kind_of, objective_mode, pseudo_rows,
                        spec_from_knobs, spec_key, walk_geometry)
from .types import Crops, Folds, KnownFrame, LaneFootprint, Read

#: The module's surface.  Most of it is re-exported from `patchgrid`
#: (the geometry), `autoknobs` (the discriminant and the self-discovery
#: sentinel), `patchfit` (the populations) and `patchspec` (the knobs),
#: so that `patch.extract`, `patch.grid_cells`, `patch.fit_discriminant`,
#: `patch.crossfit_scores`, `patch.CROSSFIT_SALT`,
#: `patch.MIN_PER_CLASS_PER_HALF`, `patch.PatchSpec` and
#: `patch.spec_from_knobs` stay the ONE spelling every caller and every
#: test already uses.
__all__ = [
    "AUTO", "CROSSFIT_SALT", "Discriminant", "MIN_PER_CLASS_PER_HALF",
    "PatchError", "apply_discriminant", "crossfit_scores", "extract",
    "fit_discriminant", "grid_cells", "grid_shape", "is_auto",
    "ring_features", "ring_matrix",
    "AUTO_AXES", "CHANNEL_SETS", "DEFAULT_MIN_LABELS_AGNOSTIC",
    "DEFAULT_MIN_LABELS_PER_STATE", "DEFAULT_SAMPLES_PER_CELL",
    "DEFAULT_SHRINKAGE", "DEFAULT_WINDOW_CELLS", "FEATURE_KINDS",
    "PATCH_MODES", "PatchLabels", "PatchSpec", "SEARCH_MODES",
    "TRAIN_SCOPES", "UNMIX_PURE", "WALK_KNOBS", "feature_kind_of",
    "mixture_score",
    "objective_mode", "patch_score", "pseudo_rows", "spec_from_knobs",
    "spec_key", "walk_geometry",
    "MIXTURE_INIT_PERCENTILES", "MIXTURE_MIN_CELLS", "MIXTURE_STATE",
    "MIXTURE_STEPS", "fallback_population", "fit_population", "sd_or_one",
]



@dataclass(frozen=True)
class PatchLabels:
    """Labelled patches from OUTSIDE the target footprint (P1g, local5).

    The 5x5 neighbourhood's own certified cargo, extracted at the WALK'S
    WIDEST geometry — `axes` — so that every candidate a population may
    choose is a column slice of these rows rather than a reason to throw
    them away (review 2026-09-06).  `cells_yx` are the page cells, so the
    cross-fit halves come from `calibrate.fold_hash` here exactly as they
    do for the footprint's own rows, and none of them lies inside the
    target footprint (the loader drops those: they are the target's own
    search- and select-fold cells).

    `axes` empty means "extracted through the caller's own grid", which
    is what a direct test call hands in; then the feature COUNT is the
    only compatibility check, as it was before.
    """

    features: np.ndarray
    bits: np.ndarray
    state: np.ndarray
    cells_yx: np.ndarray
    word: np.ndarray
    n_tiles: int = 0
    axes: Mapping[str, Any] = field(default_factory=dict)
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def n_rows(self) -> int:
        return int(self.bits.size)




def patch_score(spec: PatchSpec, plane: int, frame: KnownFrame,
                mix: spectral.PlaneMix, crops: Crops, read: Read,
                lfp: LaneFootprint, folds: Folds, *, mode: str = "patch",
                extra_labels: tuple[np.ndarray, np.ndarray, np.ndarray]
                | None = None,
                local_labels: PatchLabels | None = None,
                ) -> tuple[np.ndarray, dict]:
    """One plane's presence from the pose-resampled raw patch; high = ink.

    ONE signature, used verbatim by `unmix.unmix_score`, `arms.evidence_for`
    and the tests.  Returns ``(score (n,) float64, detail)`` with NaN where
    the lane does not observe the cell.  The target plane's own bit is
    used ONLY as the label of fit-fold rows (`frame.known[:, plane] &
    lfp.observed & folds.fit`) and never restricts a hypothesis.

    `mode` is the unmix mode this score serves: `"patch"` (pixels),
    `"rings"` (the same filter over radial means, P1c) or `"mixture"`
    (M1's label-free two-Gaussian segmentation of the three-ink
    population, `subtract` everywhere else).

    `extra_labels` = ``(rows, bits, weights)`` in footprint rows joins the
    fit set of the row's state (P3's decoder labels; B1's door);
    `local_labels` (P1g) is the 5x5 neighbourhood's own certified cargo,
    already extracted through this grid.  P2's self-labels are built HERE,
    inside each population, and never leave the fit set.  The detail says
    which of the three a fit saw.
    """
    if mode not in PATCH_MODES:
        raise PatchError(f"patch_score: mode {mode!r} is not one of "
                         f"{PATCH_MODES}")
    if read.refusal is not None:
        raise PatchError(f"patch_score on a refused read: {read.refusal}")
    if read.points_yx is None or read.linear_by_owner is None:
        raise PatchError("patch_score needs a read that carries its pose "
                         "(Read.points_yx / linear_by_owner)")
    if crops.raw_rgb is None:
        raise PatchError("patch_score needs crops opened with keep_raw=True")
    values_rgb = np.asarray(read.values_rgb, np.float64)
    n = int(values_rgb.shape[0])
    fp = lfp.tile
    cells = np.asarray(fp.page_cells_yx, np.int64)
    observed = (np.asarray(lfp.observed, bool)
                & np.isfinite(values_rgb).all(axis=1))
    known_target = np.asarray(frame.known[:, plane], bool)
    values = np.asarray(frame.bits[:, plane], np.uint8)
    state = statecal.sibling_state(frame, plane)
    kind = frame.furniture_kind
    word = (np.asarray(kind, np.int8) == statecal.FURNITURE_WORD
            if kind is not None else np.zeros(n, bool))
    dust = (np.asarray(kind, np.int8) == statecal.FURNITURE_DUST
            if kind is not None else np.zeros(n, bool))
    in_tile = np.asarray(fp.in_tile, bool)
    cargo = np.asarray(fp.cargo, bool)

    #: the five small dicts a walk leaves in the blind detail — the
    #: choices, the candidate losses, the refusals, and (2026-09-07) HOW
    #: each population chose: `auto_source`, the label count, the adopted
    #: map, the chosen ridge, the weighting's ESS, and the paired
    #: verdicts themselves (`patchwalk.AutoLedger`).
    auto = patchwalk.AutoLedger()
    auto_choices = auto.choices
    auto_losses = auto.losses
    auto_refused = auto.refused

    # 0. W8 B7 (A7, self-discovered): the sampling APERTURE the box mean
    #    reads through, chosen once per (tile, lane) on the search fold.
    #    It moves `values_rgb`, so it is settled before anything reads
    #    them — the fallback population, the mixture and the mix's own
    #    residuals all see the chosen aperture.  `observed` was taken from
    #    the read at the crop's aperture and does not move (same points,
    #    same bounds), so every candidate keeps the same row set.
    #
    #    IT IS NOT W1-WEIGHTED, and says so: this walk runs BEFORE the
    #    fallback of step 1, and the fallback is what the cargo profile's
    #    difficulty covariate is read from (HALO-CHANNEL §4.3 builds the
    #    profile after step 1 for exactly that reason).
    if "aperture_cells" in spec.auto:
        aperture, values_rgb, ap_losses, ap_detail = \
            autoknobs.choose_aperture(crops, lfp, read, frame, plane, mix,
                                      folds, usable=observed,
                                      fallback_mode=spec.fallback_mode)
        # every value in `auto_choices` is a dict keyed by axis; the
        # aperture is the (tile, lane)-wide one, the rest are the
        # populations' own — one shape for a ledger reader to walk
        auto_choices["tile"] = {"aperture_cells": float(aperture)}
        if ap_losses:
            auto_losses["tile"] = dict(ap_losses)
        if ap_detail.get("refused"):
            auto_refused["tile"] = str(ap_detail["refused"])

    # 1. the fallback score, everywhere the lane observes
    fallback = np.asarray(spectral.plane_score(
        mix, values_rgb, frame.bits, frame.known, plane, spec.fallback_mode),
        np.float64)
    score = np.full(n, np.nan, np.float64)
    patched = np.zeros(n, bool)

    # 2. M1: the mixture is a segmentation, not a filter — no patch, no
    #    label, no fit fold.  It scores the three-ink cells of this
    #    (tile, lane) and hands everything else to the fallback.
    if mode == "mixture":
        population = np.flatnonzero(observed & (state == MIXTURE_STATE))
        mixture_detail: dict[str, Any] = {
            "mixture_cells": int(population.size), "mixture_refused": None}
        if population.size >= MIXTURE_MIN_CELLS:
            try:
                mixed, fitted = mixture_score(values_rgb[population, 0])
            except PatchError as error:
                mixture_detail["mixture_refused"] = str(error)
            else:
                score[population] = mixed
                patched[population] = True
                mixture_detail.update(fitted)
        else:
            mixture_detail["mixture_refused"] = "below_mixture_min_cells"
        fallback_rows = np.flatnonzero(observed & ~patched)
        fallback_detail: dict[str, Any] = {}
        if fallback_rows.size:
            score[fallback_rows], fallback_detail = fallback_population(
                fallback, fallback_rows, known_target & folds.fit, values,
                int(spec.min_per_class))
        score.setflags(write=False)
        return score, {
            "patch_feature_kind": "mixture",
            "patch_labels_from": "none",
            "patch_states": {},
            "patch_fitted_states": (),
            "patch_agnostic_cells": 0,
            "patch_fallback_cells": int(fallback_rows.size),
            "patch_outside_cells": 0,
            "patch_unknown_state_cells": int(np.count_nonzero(
                observed & (state < 0))),
            "patch_search_mode": str(spec.search_mode),
            "auto_axes": tuple(spec.auto),
            "auto_choices": auto_choices, "auto_losses": auto_losses,
            "auto_refused": auto_refused, "auto_detail": auto.detail,
            "auto_verdicts": auto.verdicts,
            **mixture_detail, **fallback_detail}

    # 3. the patches, at the read's pose.  The ROW SET is fixed by the
    #    BOUNDING geometry — the widest window at the finest sampling any
    #    candidate may ask for — so every candidate is trained and scored
    #    on the same rows and the select-fold test is genuinely paired.
    #    With nothing auto the bounding geometry IS the spec's, and this
    #    is B1's single extraction, byte for byte.
    #: W8 B8: the ONE geometry the walk is cut at — the widest window at
    #: the finest sampling over the widest channel set any candidate can
    #: ask for.  Every narrower candidate is a column slice of it and
    #: `rings` is a matrix multiply, so the coordinate pass resamples
    #: nothing after this.
    inherited_axes, filter_auto, walk_axes, walk_refused = walk_geometry(
        spec, mode)
    #: W4 (HALO-CHANNEL §3(a)): the regulariser is still an axis the run
    #: owns, but it is minimised INSIDE every candidate rather than after
    #: them, so it leaves the coordinate order.  It stays in
    #: `filter_auto` — that tuple is what the ledger publishes.
    inner_axis = (autoknobs.INNER_AXIS
                  if autoknobs.INNER_AXIS in filter_auto else None)
    walk_order = tuple(name for name in filter_auto
                       if name != autoknobs.INNER_AXIS)
    feature_kind = str(inherited_axes["features"])
    auto_refused.update(walk_refused)
    rows_observed = np.flatnonzero(observed)
    pitch_px = float(crops.pitch_px_level)
    bank = autoknobs.FeatureBank(crops, read, lfp)
    samples, per_axis = bank.geometry_of(inherited_axes)
    inside = np.zeros(n, bool)
    #: which rows the widest candidate reaches is ARITHMETIC, not
    #: sampling (W8 B8) — the bounding extraction this used to cost is
    #: gone and the predicate is the one `extract` applies
    inside[rows_observed] = bank.inside(walk_axes, rows_observed)
    feature_row = np.full(n, -1, np.int64)
    feature_row[rows_observed] = np.arange(rows_observed.size)
    # 3a. W1 (HALO-CHANNEL §3(b)): the blind covariate histogram of the
    #     cells this filter will actually price — the target tile's OWN
    #     observed cargo, over (sibling state x incumbent difficulty).
    #     Built ONCE, from the fallback of step 1, so every population's
    #     walk and the tile's cargo sit on one standardisation.  It reads
    #     no target-plane bit inside the tile (there is none: `frame`'s
    #     run-abort assertion), consumes no fold and no label.
    #
    #     NOT the aperture walk's (step 0 runs BEFORE the fallback and
    #     MOVES the values the fallback is computed from, so a profile
    #     for it would have to be built at the pre-aperture read): the
    #     tile-wide aperture walk stays unweighted, and says so.
    #: the walk's own fold, tile-wide — the count `n_bins` is derived
    #: from (§4.1), and the same for every population of this call
    n_walk_labels = int(np.count_nonzero(
        known_target & observed & inside & np.asarray(folds.search, bool)))
    cargo_prof = None
    if filter_auto and spec.walk_weighting == WALK_WEIGHTING_CARGO:
        cargo_prof = walkeval.cargo_profile(
            fallback, observed=observed, in_tile=in_tile, cargo=cargo,
            state=state, known_target_fit=known_target & folds.fit,
            values=values, min_per_class=int(spec.min_per_class),
            n_walk_labels=n_walk_labels)

    #: the rows every candidate is trained and scored on: the labelled
    #: fit and SEARCH rows that the BOUNDING geometry keeps inside the
    #: crop, so no candidate is judged on a row another cannot reach.
    #: The search fold, not the select fold (review 2026-09-06): a knob
    #: walk is a within-arm search and DESIGN §4.8 gives those the search
    #: fold, so `select_arm`, `platt` and `best` still arbitrate on a
    #: fold nothing here minimised.
    selection_rows = np.flatnonzero(
        known_target & observed & inside
        & (np.asarray(folds.fit, bool) | np.asarray(folds.search, bool)))
    bank.use_selection(selection_rows, walk_axes)
    sel_index = np.full(n, -1, np.int64)
    sel_index[selection_rows] = np.arange(selection_rows.size)
    # the INHERITED geometry is what an unchosen population is fitted
    # through, and the only full-footprint block a default run cuts
    _base_block, _ = bank.block(inherited_axes, rows_observed)
    _base_key = bank.key(inherited_axes)
    n_features = int(_base_block.shape[1])

    def _blocks_for(axes: Mapping[str, Any],
                    groups: list[np.ndarray]) -> list[np.ndarray]:
        """Feature blocks for several row groups under ONE geometry.

        The inherited geometry's whole-observed block is already in hand;
        any other geometry is cut once over the union of the groups and
        dropped when the population is done, so a chosen geometry costs
        one extraction and no cache growth.
        """
        if bank.key(axes) == _base_key:
            return [np.asarray(_base_block[feature_row[rows]], np.float64)
                    for rows in groups]
        parts = [rows for rows in groups if rows.size]
        union = (np.unique(np.concatenate(parts)) if parts
                 else np.zeros(0, np.int64))
        got, _ins = bank.block(axes, union)
        index = np.full(n, -1, np.int64)
        index[union] = np.arange(union.size)
        return [np.asarray(got[index[rows]], np.float64) for rows in groups]

    # 4. the labels: fit fold ONLY (ruling 7), word sites out of the
    #    PER-STATE fits (ruling 11) and kept in the agnostic one
    labelled = known_target & observed & inside & np.asarray(folds.fit, bool)
    #: the POOLED walk's training rows — hoisted here from step 6 so W2's
    #: franchise can consult the pooled discovery before the per-state
    #: tiers are fitted (the value is step 6's, unchanged)
    agnostic_rows = np.flatnonzero(labelled)
    train_base = labelled & ~word if spec.exclude_word_sites else labelled
    half = cal.fold_hash(cells, int(folds.seed) ^ CROSSFIT_SALT) < 0.5
    extra_rows = np.zeros(0, np.int64)
    extra_bits = np.zeros(0, np.uint8)
    extra_weights = np.zeros(0, np.float64)
    if extra_labels is not None:
        rows_x, bits_x, weights_x = extra_labels
        rows_x = np.asarray(rows_x, np.int64)
        keep = (observed[rows_x] & inside[rows_x] & ~known_target[rows_x])
        extra_rows = rows_x[keep]
        extra_bits = np.asarray(bits_x, np.uint8)[keep]
        extra_weights = np.asarray(weights_x, np.float64)[keep]
    is_extra = np.zeros(n, bool)
    is_extra[extra_rows] = True

    local_state = np.zeros(0, np.int8)
    local_half = np.zeros(0, bool)
    local_word = np.zeros(0, bool)
    local_detail: dict[str, Any] = {"patch_local_tiles": 0,
                                    "patch_local_rows": 0,
                                    "patch_local_refused": None}
    local_axes = dict(local_labels.axes) if local_labels is not None else {}
    if local_labels is not None:
        got = int(local_labels.features.shape[1])
        want = (patchcache.block_width(local_axes, pitch_px) if local_axes
                else n_features)
        if got != want:
            local_detail["patch_local_refused"] = f"features {got} != {want}"
            local_labels = None
        elif local_axes and patchcache.derive_block(
                local_axes, local_labels.features[:0], inherited_axes,
                pitch_px) is None:
            local_detail["patch_local_refused"] = (
                f"the harvest geometry "
                f"{patchcache.axes_key(local_axes, pitch_px)} cannot serve "
                f"{patchcache.axes_key(inherited_axes, pitch_px)}")
            local_labels = None
        else:
            local_state = np.asarray(local_labels.state, np.int8)
            local_word = np.asarray(local_labels.word, bool)
            local_half = cal.fold_hash(
                np.asarray(local_labels.cells_yx, np.int64),
                int(folds.seed) ^ CROSSFIT_SALT) < 0.5
            local_detail["patch_local_tiles"] = int(local_labels.n_tiles)
            local_detail["patch_local_rows"] = int(local_labels.n_rows)

    walk = patchwalk.WalkContext(
        spec=spec, bank=bank, inherited_axes=inherited_axes,
        axis_names=filter_auto, walk_order=walk_order,
        inner_axis=inner_axis, known_target=known_target, observed=observed,
        inside=inside, word=word, search=np.asarray(folds.search, bool),
        values=values, state=state, half=half, sel_index=sel_index,
        agnostic_rows=agnostic_rows, pitch_px=pitch_px, n=n,
        profile=cargo_prof)

    def _population(mine: np.ndarray, rows_train: np.ndarray,
                    local_pick: np.ndarray, axes: Mapping[str, Any],
                    admit_auto: bool) -> tuple[np.ndarray | None, dict]:
        """Fit one population and, if it is admitted, write its scores.

        Every row of `rows_train` TRAINS the filter; only the ones no
        earlier tier has scored (`~patched`) take its out-of-fold score,
        so the agnostic tier can learn from the whole labelled pool
        while the per-state filters keep the cells they own.

        W8 B7: under `admit_auto` the tier's own cross-fit numbers decide
        whether it is used at all (`autoknobs.admit`), so the fit happens
        BEFORE the commit and a refused tier leaves `score` and `patched`
        exactly as it found them — its cells fall to the next tier.
        """
        apply_mask = observed & inside & mine & ~patched
        apply_mask[rows_train] = False
        apply_rows = np.flatnonzero(apply_mask)
        #: P2's self-training pool: in-tile cargo the frame does not know
        #: AND the decoder has not already labelled (review 2026-09-06 —
        #: a pseudo cell whose own sign came back as a third label would
        #: be the decoder's belief counted twice).
        pool_rows = np.flatnonzero(apply_mask & in_tile & cargo
                                   & ~known_target & ~is_extra)
        pool = np.searchsorted(apply_rows, pool_rows)
        here = (np.flatnonzero(mine[extra_rows]) if extra_rows.size
                else np.zeros(0, np.int64))
        extra_here = extra_rows[here] if here.size else np.zeros(0, np.int64)
        train_block, apply_block, extra_block = _blocks_for(
            axes, [rows_train, apply_rows, extra_here])
        extra = ((extra_block, extra_bits[here], extra_weights[here])
                 if here.size else None)
        #: RULING 7 for the decoder's rows (review 2026-09-06): they are
        #: cross-fitted like any other training row, so the cells they
        #: label do not come back scored by a filter they trained.
        extra_half = half[extra_here] if here.size else None
        local = None
        local_dropped = 0
        if local_labels is not None and np.any(local_pick):
            picked = np.asarray(local_labels.features[local_pick])
            block = (picked if bank.key(axes) == _base_key and not local_axes
                     else patchcache.derive_block(
                         local_axes or inherited_axes, picked, axes,
                         pitch_px))
            if block is not None and int(block.shape[1]) == int(
                    train_block.shape[1]):
                local = (np.asarray(block, np.float64),
                         np.asarray(local_labels.bits, np.uint8)[local_pick],
                         local_half[local_pick])
            else:
                # a chosen SAMPLING moves every sample position, so it is
                # a different grid and not a slice of the harvest; the
                # rows are dropped and the population says so
                local_dropped = int(np.count_nonzero(local_pick))
        train_new = ~patched[rows_train]
        try:
            #: THE RIDGE THIS POPULATION CHOSE (2026-09-07 review,
            #: blocker).  `axes` carries every axis the walk owns,
            #: including the regulariser W4 minimises inside every
            #: candidate — and this call used to read `spec.shrinkage`
            #: instead, so a run published one ridge in `auto_choices`
            #: and fitted at another.  With the axis NAMED the two are
            #: the same float and this is a no-op.
            oof_own, insample_own, scores_apply, pop_detail = fit_population(
                spec, train_block, values[rows_train], half[rows_train],
                apply_block, pool, extra=extra, extra_half=extra_half,
                local=local, scale_rows=train_new,
                shrinkage=float(axes["shrinkage"]) if "shrinkage" in axes
                else None)
        except PatchError as error:
            return None, {"reason": f"crossfit_refused:{error}"}
        # the pseudo cells take their OUT-OF-FOLD score, not the full
        # filter's in-sample one (the rest of the population keeps the
        # full filter, which still saw every pseudo row)
        extra_oof = pop_detail.pop("extra_oof", None)
        n_extra_oof = 0
        if extra_oof is not None and extra_here.size:
            position = np.searchsorted(apply_rows, extra_here)
            found = position < apply_rows.size
            found[found] = apply_rows[position[found]] == extra_here[found]
            scores_apply = np.array(scores_apply, np.float64, copy=True)
            scores_apply[position[found]] = np.asarray(extra_oof,
                                                       np.float64)[found]
            n_extra_oof = int(np.count_nonzero(found))
        every_label = values[rows_train]
        wrong_in_all = (insample_own > 0.0) != (every_label == 1)
        wrong_oof_all = (oof_own > 0.0) != (every_label == 1)
        labels = every_label[train_new]
        wrong_insample = wrong_in_all[train_new]
        wrong_crossfit = wrong_oof_all[train_new]
        pop_detail.update({
            "n_extra": int(here.size),
            "n_extra_out_of_fold": int(n_extra_oof),
            "n_local": 0 if local is None else int(local[1].size),
            "n_local_dropped": int(local_dropped),
            "n_applied": int(apply_rows.size),
            "n_fit_rows": int(rows_train.size),
            "n_features": int(train_block.shape[1]),
            "wrong_insample": int(np.count_nonzero(wrong_insample)),
            "wrong_crossfit": int(np.count_nonzero(wrong_crossfit)),
            "n_fit_scored": int(labels.size),
            "n_half_a": int(np.count_nonzero(half[rows_train])),
            "n_half_b": int(np.count_nonzero(~half[rows_train]))})
        if admit_auto:
            # measured over the WHOLE fit set: how well the filter reads
            # out of fold is a property of the filter, not of which rows
            # an earlier tier happened to leave it.
            #
            # AND AGAINST WHAT IT DISPLACES (review 2026-09-06): the tier
            # ladder hands a fitted tier its cells before the next one
            # sees them, so a filter that only has to beat majority-class
            # guessing can take cells the `subtract` score reads better.
            # The alternative offered here is that score — exactly what
            # the cells would carry for the LAST tier, and the honest
            # floor for an earlier one (the agnostic tier is fitted after
            # the per-state ones and cannot be quoted here).
            # over the rows this tier OWNS (`train_new`, the same set the
            # shared scale is taken from): they are the labelled stand-in
            # for the cells it is about to take, and an earlier tier's
            # rows are not this tier's to argue about
            owned = np.flatnonzero(train_new)
            own_losses = autoknobs.crossfit_losses(
                oof_own[owned], every_label[owned],
                half[rows_train][owned])
            alt_losses = autoknobs.crossfit_losses(
                fallback[rows_train][owned], every_label[owned],
                half[rows_train][owned])
            admitted, admit_detail = autoknobs.admit(
                wrong_in_all, wrong_oof_all, every_label,
                own_losses=own_losses, alternative_losses=alt_losses)
            pop_detail["admission"] = admit_detail
            if not admitted:
                pop_detail.update({"fitted": False,
                                   "reason": f"refused:"
                                             f"{admit_detail['reason']}"})
                return None, pop_detail
        score[rows_train[train_new]] = oof_own[train_new]
        score[apply_rows] = scores_apply
        patched[rows_train[train_new]] = True
        patched[apply_rows] = True
        pop_detail.update({"fitted": True, "reason": "fitted"})
        return oof_own, pop_detail

    # 5. one filter per sibling state, cross-fitted inside the fit fold
    states_detail: dict[int, dict[str, Any]] = {}
    wrong_in = right_in = wrong_oof = right_oof = 0
    n_half_a = n_half_b = 0
    n_self_total = 0
    n_local_total = n_local_dropped_total = 0
    for index in range(statecal.N_STATES):
        mine = state == index
        local_pick = ((local_state == index) & ~local_word
                      if spec.exclude_word_sites else local_state == index)
        rows_train = np.flatnonzero(train_base & mine)
        labels = values[rows_train]
        n_1 = int(np.count_nonzero(labels == 1))
        n_0 = int(labels.size - n_1)
        n_local_here = int(np.count_nonzero(local_pick))
        entry: dict[str, Any] = {
            "n_fit_0": n_0, "n_fit_1": n_1,
            "n_fit_word": int(np.count_nonzero(labelled & mine & word)),
            "n_fit_dust": int(np.count_nonzero(labelled & mine & dust)),
            "n_fit_cargo": int(np.count_nonzero(labelled & mine & ~word
                                                & ~dust)),
            "n_cells": int(np.count_nonzero(observed & mine)),
            "fitted": False, "n_scored": 0,
            "labels_per_feature": (float(labels.size + n_local_here)
                                   / n_features if n_features else 0.0)}
        states_detail[index] = entry
        # W8 B7: under `patch_min_labels_per_state="auto"` the COUNT pin
        # is gone — the tier is fitted and then admitted (or not) on its
        # own cross-fit numbers.  The per-class floor stays: it is what
        # makes a fit possible at all, not a judgement about its quality.
        admit_auto = "min_labels_per_state" in spec.auto
        if (not admit_auto
                and labels.size + n_local_here < int(
                    spec.min_labels_per_state)):
            entry["reason"] = "below_min_labels_per_state"
            continue
        if min(n_0, n_1) < int(spec.min_per_class):
            entry["reason"] = "class_below_min_per_class"
            continue
        axes, axes_losses, axes_detail, axes_source = patchwalk.choose_axes(
            walk, mine, rows_train, tag=f"state{index}",
            exclude_word=bool(spec.exclude_word_sites))
        auto.record(f"state{index}", axes, axes_losses, axes_detail,
                    axes_source, filter_auto)
        oof_own, pop_detail = _population(mine, rows_train, local_pick,
                                          axes, admit_auto)
        entry.update(pop_detail)
        #: THE DENOMINATOR THIS FIELD DIVIDES BY (HALO-CHANNEL §4.3).
        #: `labels_per_feature` above is at the INHERITED width (144)
        #: while the population may have been fitted at 256 or 432 — the
        #: whole data-budget argument is read off this number, so the
        #: geometry it was actually fitted at gets its own field.
        if int(pop_detail.get("n_features", 0)) > 0:
            entry["labels_per_feature_chosen"] = (
                float(pop_detail["n_fit_rows"])
                / float(pop_detail["n_features"]))
        if oof_own is None:
            continue
        wrong_in += int(pop_detail["wrong_insample"])
        right_in += int(pop_detail["n_fit_scored"] - pop_detail[
            "wrong_insample"])
        wrong_oof += int(pop_detail["wrong_crossfit"])
        right_oof += int(pop_detail["n_fit_scored"] - pop_detail[
            "wrong_crossfit"])
        n_half_a += int(pop_detail["n_half_a"])
        n_half_b += int(pop_detail["n_half_b"])
        n_self_total += int(pop_detail["n_self"])
        n_local_total += int(pop_detail["n_local"])
        n_local_dropped_total += int(pop_detail["n_local_dropped"])
        entry["n_scored"] = int(np.count_nonzero(patched & mine))

    # 6. P1d, the state-agnostic tier: one filter over EVERY fit-fold
    #    labelled row (word sites kept — every state is present in that
    #    pool), for the cells whose siblings are unknown and for the
    #    states that refused.  Its own floor, so
    #    `patch_min_labels_per_state=1000000` isolates it.
    agnostic_local = (~local_word if local_labels is not None
                      else np.zeros(0, bool))
    n_local_agnostic = int(np.count_nonzero(agnostic_local))
    agnostic_labels = values[agnostic_rows]
    n_1 = int(np.count_nonzero(agnostic_labels == 1))
    n_0 = int(agnostic_labels.size - n_1)
    agnostic: dict[str, Any] = {
        "n_fit_0": n_0, "n_fit_1": n_1, "fitted": False, "n_scored": 0,
        "n_cells": int(np.count_nonzero(observed & ~patched))}
    before = patched.copy()
    admit_agnostic = "min_labels_agnostic" in spec.auto
    if not np.any(observed & inside & ~patched):
        # every observed cell already has a filter: the tier would fit
        # three more systems to score nothing.  This is the ordinary case
        # on a dead-band tile whose M and Y ARE certified.
        agnostic["reason"] = "no_unscored_cell"
    elif (not admit_agnostic
          and agnostic_labels.size + n_local_agnostic < int(
              spec.min_labels_agnostic)):
        agnostic["reason"] = "below_min_labels_agnostic"
    elif min(n_0, n_1) < int(spec.min_per_class):
        agnostic["reason"] = "class_below_min_per_class"
    else:
        every = np.ones(n, bool)
        axes, axes_losses, axes_detail, axes_source = patchwalk.choose_axes(
            walk, every, agnostic_rows, tag=patchwalk.POOLED_TAG,
            exclude_word=False)
        auto.record(patchwalk.POOLED_TAG, axes, axes_losses, axes_detail,
                    axes_source, filter_auto)
        oof_own, pop_detail = _population(every, agnostic_rows,
                                          agnostic_local, axes,
                                          admit_agnostic)
        agnostic.update(pop_detail)
        if int(pop_detail.get("n_features", 0)) > 0:
            agnostic["labels_per_feature_chosen"] = (
                float(pop_detail["n_fit_rows"])
                / float(pop_detail["n_features"]))
        if oof_own is not None:
            wrong_in += int(pop_detail["wrong_insample"])
            right_in += int(pop_detail["n_fit_scored"]
                            - pop_detail["wrong_insample"])
            wrong_oof += int(pop_detail["wrong_crossfit"])
            right_oof += int(pop_detail["n_fit_scored"]
                             - pop_detail["wrong_crossfit"])
            n_half_a += int(pop_detail["n_half_a"])
            n_half_b += int(pop_detail["n_half_b"])
            n_self_total += int(pop_detail["n_self"])
            n_local_total += int(pop_detail["n_local"])
            n_local_dropped_total += int(pop_detail["n_local_dropped"])
            agnostic["n_scored"] = int(np.count_nonzero(patched & ~before))
    n_agnostic = int(np.count_nonzero(patched & ~before))

    # 7. everything else: the fallback population on the shared scale
    fallback_rows = np.flatnonzero(observed & ~patched)
    fallback_detail = {}
    if fallback_rows.size:
        score[fallback_rows], fallback_detail = fallback_population(
            fallback, fallback_rows, known_target & folds.fit, values,
            int(spec.min_per_class))
    score.setflags(write=False)

    sources = [LABELS_FROM_HALO]
    # `local5` is claimed only when a population actually TRAINED on the
    # neighbourhood's rows (review 2026-09-06 — it used to be claimed
    # whenever the loader returned any, even where every population had
    # dropped them for a geometry it could not slice)
    if n_local_total:
        sources.append(LABELS_FROM_LOCAL5)
    if n_self_total:
        sources.append(LABELS_FROM_SELF)
    if extra_rows.size:
        sources.append(LABELS_FROM_BP)
    n_fit_total = wrong_in + right_in
    detail: dict[str, Any] = {
        #: THE FLAT GEOMETRY FIELDS ARE THE INHERITED ONES.  Under `auto`
        #: a population may have used another width, another channel set
        #: or another feature kind, and what it used is in `auto_choices`
        #: — `patch_geometry_scope` says which to read (review
        #: 2026-09-06; the pair is not spelled out per population here
        #: because that would put five more numbers per population in
        #: every ledger row, and `auto_choices` already carries them).
        "patch_geometry_scope": ("per_population" if spec.auto
                                 else "inherited"),
        "patch_window_cells": float(spec.window_cells),
        "patch_samples_per_cell": int(samples),
        "patch_px": int(per_axis),
        "patch_features": n_features,
        "patch_feature_kind": feature_kind,
        "patch_channels": tuple(int(c) for c in spec.channels),
        "patch_shrinkage": float(spec.shrinkage),
        "patch_fit_fold": "fit",
        "patch_labels_from": "+".join(sources),
        "patch_train_scope": str(spec.train_scope),
        "patch_states": states_detail,
        "patch_fitted_states": tuple(
            index for index, entry in states_detail.items()
            if entry["fitted"]),
        "patch_agnostic": agnostic,
        "patch_agnostic_cells": int(n_agnostic),
        "patch_fallback_cells": int(fallback_rows.size),
        "patch_outside_cells": int(np.count_nonzero(observed & ~inside)),
        "patch_unknown_state_cells": int(np.count_nonzero(
            observed & (state < 0))),
        "patch_search_mode": str(spec.search_mode),
        "patch_exclude_word_sites": bool(spec.exclude_word_sites),
        # W8 B7: what this run decided for itself, and what it cost every
        # candidate on the select fold.  `auto_axes` empty = every knob
        # was named by the operator and nothing was chosen here.
        "auto_axes": tuple(spec.auto),
        #: WHICH FOLD the walk spent (review 2026-09-06).  A knob walk is
        #: a within-arm search, so it is the SEARCH fold's and the select
        #: fold is left to `select_arm` / `platt` / `best`.
        "patch_auto_walk_fold": ("search" if spec.auto else None),
        "auto_choices": auto_choices,
        "auto_losses": auto_losses,
        "auto_refused": auto_refused,
        #: 2026-09-07 — HOW the walk decided, beside WHAT it chose:
        #: `auto_source` (own / pooled / inherited) is what makes a vote
        #: countable apart from an inheritance, and `auto_verdicts` is
        #: the paired test itself.
        "auto_detail": auto.detail,
        "auto_verdicts": auto.verdicts,
        "patch_walk_weighting": str(spec.walk_weighting),
        "patch_walk_franchise": str(spec.walk_franchise),
        "patch_walk_direction": str(spec.walk_direction),
        "patch_walk_inner_axis": inner_axis,
        "patch_walk_cargo_cells": (None if cargo_prof is None
                                   else int(cargo_prof.n_cargo)),
        #: the profile's own bookkeeping, published so the derived bin
        #: count is inspectable from a real run's ledger rather than
        #: only from a re-derivation (2026-09-07 review): `n_walk_labels`
        #: is the TILE-WIDE search-fold count the bins were derived from,
        #: which is not any population's own `n_walk_labels`
        "patch_walk_profile": (None if cargo_prof is None
                               else {**dict(cargo_prof.detail),
                                     "n_bins": int(cargo_prof.n_bins),
                                     "refused": cargo_prof.refused}),
        "patch_fit_error_insample": (wrong_in / n_fit_total
                                     if n_fit_total else None),
        "patch_fit_error_crossfit": (wrong_oof / (wrong_oof + right_oof)
                                     if (wrong_oof + right_oof) else None),
        "patch_crossfit_halves": (int(n_half_a), int(n_half_b)),
        "patch_n_extra_labels": int(extra_rows.size),
        "patch_local_rows_used": int(n_local_total),
        "patch_local_rows_dropped": int(n_local_dropped_total),
        "patch_self_rounds": int(spec.selftrain_rounds),
        "patch_self_cells": int(n_self_total),
        "pseudo_source": LABELS_FROM_SELF if n_self_total else None,
        **local_detail,
        **fallback_detail,
    }
    return score, detail

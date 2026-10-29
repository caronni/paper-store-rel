"""The patch family's KNOBS — what a knob bag means (W8, review 2026-09-06).

BLIND, and free of every analyzer module but :mod:`analyzer.autoknobs`
(the `"auto"` sentinel and the candidate sets the walk's bounding
geometry is taken over) and :mod:`analyzer.patchgrid` (the error type).
Nothing here may import :mod:`analyzer.truth`, :mod:`analyzer.oracle` or
:mod:`analyzer.score`, and nothing here imports :mod:`analyzer.patch`
(which dispatches into this module).

`analyzer.patch` grew past DESIGN §0.4's 1000-line cap again when the
local5 harvest was moved onto the walk's own geometry, so the layer that
turns a knob bag into a frozen `PatchSpec` — and the two small pure
functions that read one — moved here, UNCHANGED except for
:func:`walk_geometry`, which is new.  This file is a move, not a rewrite:
`analyzer.patch` imports every public name, so `patch.PatchSpec`,
`patch.spec_from_knobs`, `patch.spec_key`, `patch.feature_kind_of`,
`patch.objective_mode`, `patch.pseudo_rows`, `patch.PATCH_MODES`,
`patch.AUTO_AXES` and every constant here stay the ONE spelling every
caller and every test already uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from holo.receiver.lib import spectral

from . import autoknobs
from .autoknobs import AUTO, is_auto
from .patchgrid import PatchError
from .types import TileFootprint

__all__ = [
    "AUTO", "AUTO_AXES", "CHANNEL_SETS", "DEFAULT_MIN_LABELS_AGNOSTIC",
    "DEFAULT_MIN_LABELS_PER_STATE", "DEFAULT_SAMPLES_PER_CELL",
    "DEFAULT_SHRINKAGE", "DEFAULT_WINDOW_CELLS", "FEATURE_KINDS",
    "LABELS_FROM_BP", "LABELS_FROM_HALO", "LABELS_FROM_LOCAL5",
    "LABELS_FROM_SELF", "PATCH_MODES", "PatchSpec", "SEARCH_MODES",
    "TRAIN_SCOPES", "UNMIX_PURE", "WALK_DIRECTIONS", "WALK_DIRECTION_NESTED",
    "WALK_DIRECTION_PLAIN", "WALK_FRANCHISES", "WALK_FRANCHISE_INHERIT",
    "WALK_FRANCHISE_POOLED", "WALK_KNOBS", "WALK_WEIGHTINGS",
    "WALK_WEIGHTING_CARGO", "WALK_WEIGHTING_NONE", "feature_kind_of",
    "is_auto", "objective_mode", "pseudo_rows", "spec_from_knobs",
    "spec_key", "walk_geometry",
]


#: The unmix modes this module serves.  `patch` is the pixel filter,
#: `rings` (B3, P1c) the radial-mean variant, `mixture` (B3, M1) the
#: label-free two-Gaussian segmentation of the three-ink population, and
#: `pure` (B8) the pixel filter again — the SAME score as `patch`, named
#: apart so an arm can ask for `analyzer.pure`'s calibration while its
#: neighbours in the battery keep the map.  `patch_score(mode=...)`.
PATCH_MODES: tuple[str, ...] = ("patch", "rings", "mixture", "pure")
#: `pure.is_pure` reads it; `types.PROFILES`' `patch-then-pure` puts the
#: arms it names (`pure+committed`, `pure+field2`) in the RE-ROLL only.
UNMIX_PURE: str = "pure"

DEFAULT_WINDOW_CELLS: float = 1.5
#: Samples per cell along each axis, CAPPED at the lane's native pitch
#: (ruling 4): 8 gives 144 features at 2400/4800 and 36 at 1200; 16
#: reproduces the measured 576-feature filter at 4800.
DEFAULT_SAMPLES_PER_CELL: int = 8
DEFAULT_SHRINKAGE: float = 1e-2
DEFAULT_MIN_LABELS_PER_STATE: int = 200
DEFAULT_MIN_LABELS_AGNOSTIC: int = 200

SEARCH_MODES: tuple[str, ...] = ("subtract", "patch")

#: THE THREE WALK KNOBS (HALO-CHANNEL-2026-09-07 §4.4).  `walk_weighting`
#: turns W1 on (the walk's held-out losses importance-weighted to the
#: target tile's OWN cargo over two blind covariates); `walk_franchise`
#: turns W2 on (a population that cannot carry its own vote inherits the
#: POOLED walk's discovery instead of the module constant);
#: `walk_direction` turns W3 on (on the nested channel axis the richer
#: candidate is adopted unless the leaner one clears the bar).  Which of
#: them SHIPS on is on `PatchSpec`, beside the fields, with the
#: measurement that decided it; naming all three at their first value
#: here restores the pre-change walk exactly.
WALK_WEIGHTING_NONE: str = "none"
WALK_WEIGHTING_CARGO: str = "cargo"
WALK_WEIGHTINGS: tuple[str, ...] = (WALK_WEIGHTING_NONE,
                                    WALK_WEIGHTING_CARGO)
WALK_FRANCHISE_INHERIT: str = "inherit"
WALK_FRANCHISE_POOLED: str = "pooled"
WALK_FRANCHISES: tuple[str, ...] = (WALK_FRANCHISE_INHERIT,
                                    WALK_FRANCHISE_POOLED)
WALK_DIRECTION_PLAIN: str = "adopt-if-better"
WALK_DIRECTION_NESTED: str = "nested-richer"
WALK_DIRECTIONS: tuple[str, ...] = (WALK_DIRECTION_PLAIN,
                                    WALK_DIRECTION_NESTED)
#: The knob names, for the CLI's help and for a reader of the header.
WALK_KNOBS: tuple[str, ...] = ("walk_weighting", "walk_franchise",
                               "walk_direction")
CHANNEL_SETS: dict[str, tuple[int, ...]] = dict(autoknobs.CHANNEL_SETS)
FEATURE_KINDS: tuple[str, ...] = ("pixels", "rings")
TRAIN_SCOPES: tuple[str, ...] = ("footprint", "local5")

LABELS_FROM_HALO: str = "halo"
LABELS_FROM_SELF: str = "self"
LABELS_FROM_LOCAL5: str = "local5"
#: B4's decoder labels, arriving through `extra_labels` from the
#: `pseudo_labels` door in `arms.evidence_for` — `"halo+bp"`, or
#: `"halo+self+bp"` when self-training is on too.
LABELS_FROM_BP: str = "bp"


# ------------------------------------------------------------- the spec

@dataclass(frozen=True)
class PatchSpec:
    """Every knob of the patch family, one frozen value."""

    window_cells: float = DEFAULT_WINDOW_CELLS
    samples_per_cell: int = DEFAULT_SAMPLES_PER_CELL
    channels: tuple[int, ...] = (0,)
    features: str = "pixels"
    shrinkage: float = DEFAULT_SHRINKAGE
    min_labels_per_state: int = DEFAULT_MIN_LABELS_PER_STATE
    min_labels_agnostic: int = DEFAULT_MIN_LABELS_AGNOSTIC
    min_per_class: int = spectral.MIN_PER_CLASS
    fallback_mode: str = spectral.MODE_SUBTRACT
    search_mode: str = "subtract"
    selftrain_rounds: int = 0
    selftrain_keep: float = 0.6
    selftrain_weight: float = 2.0
    train_scope: str = "footprint"
    exclude_word_sites: bool = True
    #: HOW the self-discovery walk decides (HALO-CHANNEL-2026-09-07 §4.4)
    #: — three OPERATOR knobs, none of them `"auto"`-able: they name how
    #: a run decides, not what is measured, and a rule cannot be chosen
    #: by the rule it defines (the carve-out `autoknobs`' docstring
    #: already makes for the unmix mode, the register arm and the train
    #: scope).
    #:
    #: TWO OF THE THREE SHIP ON, by the pre-registered isolation of §4.6
    #: (measured 2026-09-07, HALO-CHANNEL §5, 153 open C tile-streams,
    #: one code state, 606 certificates checked, 0 wrong, 0 false
    #: accepts): the FRANCHISE is NET +4 over the same run without it
    #: (+5/−1, a crossing) and the DIRECTION is NET +6 (+7/−1) — neither
    #: is a containment.  Of the gate's three clauses only clause 1
    #: (zero wrong, zero false) applied to them and it PASSED; clauses 2
    #: and 3 failed on their own terms and are dispositioned in §5.1.
    #: The WEIGHTING did not pass — alone it is −3 and a strict SUBSET —
    #: so it stays off and is recorded as a measured negative; its
    #: apparent +4/−1 "in composition" was re-measured on 2026-09-07 as
    #: exactly 0 gained / 0 lost over the shipped pair (§5.5).  One
    #: sheet, one stream, one print day: this is regression evidence and
    #: promotes nothing (CLAUDE.md), and naming all three restores the
    #: pre-change walk's RULES exactly (W4 lands unconditionally, so the
    #: ridge is still minimised inside every candidate — §5.1 clause 2).
    walk_weighting: str = WALK_WEIGHTING_NONE
    walk_franchise: str = WALK_FRANCHISE_POOLED
    walk_direction: str = WALK_DIRECTION_NESTED
    #: W8 B7: the AXES this run decides for itself, by name — every field
    #: above keeps its INHERITED value here (what a run falls back to when
    #: its own select fold cannot tell the candidates apart), and the
    #: names in this tuple are the ones `patch_score` re-chooses per
    #: (lane, plane, sibling state, tile).  Empty means "the operator
    #: named every knob", and then this module behaves exactly as B1/B3
    #: built it.
    auto: tuple[str, ...] = ()

    @property
    def bounding_window_cells(self) -> float:
        """The widest window a run may choose — the crop must reach it."""
        if "window_cells" not in self.auto:
            return float(self.window_cells)
        return max(float(self.window_cells), max(autoknobs.WINDOW_CANDIDATES))

    def axes(self) -> dict[str, Any]:
        """The inherited value of every auto-able axis, as a plain dict."""
        return {"samples_per_cell": int(self.samples_per_cell),
                "window_cells": float(self.window_cells),
                "channels": tuple(int(c) for c in self.channels),
                "features": str(self.features),
                "shrinkage": float(self.shrinkage)}

    def __post_init__(self) -> None:
        if self.window_cells <= 0.0:
            raise PatchError("patch_window_cells must be positive")
        if int(self.samples_per_cell) < 1:
            raise PatchError("patch_samples_per_cell must be >= 1")
        if self.search_mode not in SEARCH_MODES:
            raise PatchError(f"patch_search_mode {self.search_mode!r} is "
                             f"not one of {SEARCH_MODES}")
        if self.features not in FEATURE_KINDS:
            raise PatchError(f"patch features {self.features!r} is not "
                             f"one of {FEATURE_KINDS}")
        if self.fallback_mode not in spectral.MODES:
            raise PatchError(f"patch fallback {self.fallback_mode!r} is "
                             f"not one of {spectral.MODES}")
        if self.train_scope not in TRAIN_SCOPES:
            raise PatchError(f"patch_train_scope {self.train_scope!r} is "
                             f"not one of {TRAIN_SCOPES}")
        if not self.channels or any(
                int(c) not in (0, 1, 2) for c in self.channels):
            raise PatchError(f"patch channels {self.channels!r}")
        for name in self.auto:
            if name not in AUTO_AXES:
                raise PatchError(f"patch auto axis {name!r} is not one of "
                                 f"{AUTO_AXES}")
        for knob, value, allowed in (
                ("walk_weighting", self.walk_weighting, WALK_WEIGHTINGS),
                ("walk_franchise", self.walk_franchise, WALK_FRANCHISES),
                ("walk_direction", self.walk_direction, WALK_DIRECTIONS)):
            if value not in allowed:
                raise PatchError(f"{knob} {value!r} is not one of {allowed}")


#: The axes `PatchSpec.auto` may name.  `samples_per_cell`,
#: `window_cells`, `channels`, `features` and `shrinkage` are the
#: FILTER's, chosen per population by `autoknobs.choose`;
#: `min_labels_per_state` / `min_labels_agnostic` are the TIER's count
#: pins, replaced under `auto` by `autoknobs.admit`'s statistical rule;
#: `aperture_cells` is A7's sampling aperture, chosen once per (tile,
#: lane).  Every name is the knob's own, minus the `patch_` prefix.
AUTO_AXES: tuple[str, ...] = (
    "samples_per_cell", "window_cells", "channels", "features",
    "shrinkage", "min_labels_per_state", "min_labels_agnostic",
    "aperture_cells")


def _channels(value: Any) -> tuple[int, ...]:
    if isinstance(value, str):
        if value not in CHANNEL_SETS:
            raise PatchError(f"patch_channels {value!r} is not one of "
                             f"{sorted(CHANNEL_SETS)}")
        return CHANNEL_SETS[value]
    return tuple(int(item) for item in value)


def _inherit(knobs: Mapping[str, Any], knob: str, axis: str,
             inherited: Any, cast, auto: list[str]) -> Any:
    """One knob: `"auto"` records the axis and keeps the inherited value.

    W8 B7.  A knob absent from the bag is inherited silently; a knob set
    to `autoknobs.AUTO` is inherited AND named in `PatchSpec.auto`, so
    the value in the field is exactly what the run falls back to when its
    select fold refuses to choose.
    """
    value = knobs.get(knob, inherited)
    if is_auto(value):
        auto.append(axis)
        return inherited
    return cast(value)


def spec_from_knobs(knobs: Mapping[str, Any] | None) -> PatchSpec:
    """The `patch_*` knobs of a knob bag, defaults where absent.

    `"auto"` on any of `AUTO_AXES`' knobs (and on the top-level
    `aperture_cells`) is the user's self-discovery ruling of 2026-09-06:
    the field keeps its inherited value and the axis is handed to the
    run's own select fold.
    """
    knobs = dict(knobs or {})
    base = PatchSpec()
    auto: list[str] = []
    return PatchSpec(
        window_cells=_inherit(knobs, "patch_window_cells", "window_cells",
                              base.window_cells, float, auto),
        samples_per_cell=_inherit(knobs, "patch_samples_per_cell",
                                  "samples_per_cell",
                                  base.samples_per_cell, int, auto),
        channels=_inherit(knobs, "patch_channels", "channels",
                          base.channels, _channels, auto),
        features=_inherit(knobs, "patch_features", "features",
                          base.features, str, auto),
        shrinkage=_inherit(knobs, "patch_shrinkage", "shrinkage",
                           base.shrinkage, float, auto),
        min_labels_per_state=_inherit(
            knobs, "patch_min_labels_per_state", "min_labels_per_state",
            base.min_labels_per_state, int, auto),
        min_labels_agnostic=_inherit(
            knobs, "patch_min_labels_agnostic", "min_labels_agnostic",
            base.min_labels_agnostic, int, auto),
        min_per_class=int(knobs.get("patch_min_per_class",
                                    base.min_per_class)),
        fallback_mode=str(knobs.get("patch_fallback_mode",
                                    base.fallback_mode)),
        search_mode=str(knobs.get("patch_search_mode", base.search_mode)),
        selftrain_rounds=int(knobs.get("patch_selftrain_rounds",
                                       base.selftrain_rounds)),
        selftrain_keep=float(knobs.get("patch_selftrain_keep",
                                       base.selftrain_keep)),
        selftrain_weight=float(knobs.get("patch_selftrain_weight",
                                         base.selftrain_weight)),
        train_scope=str(knobs.get("patch_train_scope", base.train_scope)),
        exclude_word_sites=bool(knobs.get("patch_exclude_word_sites",
                                          base.exclude_word_sites)),
        #: not `_inherit`: these three are the operator's and take no
        #: `"auto"` (see the field comments on `PatchSpec`)
        walk_weighting=str(knobs.get("walk_weighting",
                                     base.walk_weighting)),
        walk_franchise=str(knobs.get("walk_franchise",
                                     base.walk_franchise)),
        walk_direction=str(knobs.get("walk_direction",
                                     base.walk_direction)),
        auto=_auto_axes(knobs, auto))


def _auto_axes(knobs: Mapping[str, Any], auto: list[str]) -> tuple[str, ...]:
    """The auto axes in `AUTO_AXES` order, plus the top-level aperture."""
    names = set(auto)
    if is_auto(knobs.get("aperture_cells")):
        names.add("aperture_cells")
    return tuple(name for name in AUTO_AXES if name in names)


def spec_key(spec: PatchSpec) -> tuple:
    """A hashable identity of the spec, for memo keys."""
    return (float(spec.window_cells), int(spec.samples_per_cell),
            tuple(int(c) for c in spec.channels), str(spec.features),
            float(spec.shrinkage), int(spec.min_labels_per_state),
            int(spec.min_labels_agnostic), int(spec.min_per_class),
            str(spec.fallback_mode), str(spec.search_mode),
            int(spec.selftrain_rounds), float(spec.selftrain_keep),
            float(spec.selftrain_weight), str(spec.train_scope),
            bool(spec.exclude_word_sites), tuple(spec.auto),
            str(spec.walk_weighting), str(spec.walk_franchise),
            str(spec.walk_direction))


def feature_kind_of(unmix_mode: str, spec: PatchSpec | None) -> str:
    """The feature kind an (arm, spec) pair asks for.

    The MODE decides for `rings` (that is what the arm name means); the
    `patch_features` knob decides for `patch`, so `patch+offset` can be
    run over radial means without a second arm name.  One spelling, used
    by `patch_score` and by the local5 loader, which must extract through
    the same grid.
    """
    if str(unmix_mode) == "rings":
        return "rings"
    return "pixels" if spec is None else str(spec.features)


def objective_mode(unmix_mode: str, spec: PatchSpec | None, *,
                   grid: bool) -> str:
    """The unmix mode a registration SEARCH evaluates (ruling 1).

    A patch mode searches the offset GRID under its own objective only
    when the spec says `search_mode="patch"`; the affine swim and the
    word pose ALWAYS search under `subtract`, because their objectives run
    over fit ∪ search rows and would be half in-sample for a fitted
    score.  Every other mode is its own objective.
    """
    if unmix_mode not in PATCH_MODES:
        return str(unmix_mode)
    if grid and spec is not None and spec.search_mode == "patch":
        return str(unmix_mode)
    return spectral.MODE_SUBTRACT


# DESIGN §0.4: this file is at its cap, so the grid/rings/extraction live
# in `patchgrid`, the discriminant and the cross-fit in `autoknobs` (W8
# B7) and the feature/normal-equation economy in `patchcache` (W8 B8).
# All three are imported at the top, so `patch.extract`,
# `patch.grid_cells`, `patch.fit_discriminant`, `patch.crossfit_scores`,
# `patch.CROSSFIT_SALT` and `patch.MIN_PER_CLASS_PER_HALF` stay the
# spelling for every caller and every test.


# ------------------------------------------------- pseudo-label plumbing

def pseudo_rows(fp: TileFootprint, pseudo: Any,
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Page cells of a pseudo-label set -> ``(rows, bits, weights)``.

    `pseudo` carries `cells_yx (m, 2)`, `bits (m,)` and `weights (m,)`
    (B4's `PseudoLabels`).  Cells outside the footprint are dropped; the
    lookup is a `searchsorted` on the flat page key, which is what
    `sample.lane_footprint` relies on the footprint order for.
    """
    cells = np.asarray(fp.page_cells_yx, np.int64)
    width = int(fp.page_shape_cells_yx[1])
    if width <= 0:
        width = int(cells[:, 1].max()) + 1 if cells.shape[0] else 1
    keys = cells[:, 0] * np.int64(width) + cells[:, 1]
    theirs = np.asarray(pseudo.cells_yx, np.int64).reshape(-1, 2)
    want = theirs[:, 0] * np.int64(width) + theirs[:, 1]
    position = np.clip(np.searchsorted(keys, want), 0, max(0, keys.size - 1))
    hit = (keys.size > 0) & (keys[position] == want) if keys.size else \
        np.zeros(want.size, bool)
    rows = position[hit].astype(np.int64)
    bits = np.asarray(pseudo.bits, np.uint8).reshape(-1)[hit]
    weights = np.asarray(pseudo.weights, np.float64).reshape(-1)[hit]
    return rows, bits, weights


# --------------------------------------------------- the walk's geometry

def walk_geometry(spec: PatchSpec, mode: str
                  ) -> tuple[dict[str, Any], tuple[str, ...],
                             dict[str, Any], dict[str, str]]:
    """``(inherited axes, auto axis names, the walk's widest axes, refusals)``.

    ONE spelling of B8's bounding geometry, because two callers need it:
    `patch_score`, which cuts every candidate out of it, and
    `patchlocal.local_patch_labels`, which must harvest the 5x5
    neighbourhood's rows through the SAME widest grid or a population
    that chooses a different width has to throw them away (review
    2026-09-06 — the pure family's whole premise is those rows).
    """
    inherited = spec.axes()
    #: WALK_ORDER and not AXIS_ORDER (W4, 2026-09-07): the regulariser is
    #: still an axis a run may own — it is minimised INSIDE every
    #: candidate now instead of after them, so it is not in the
    #: coordinate order, and `patch_score` splits this tuple.
    filter_auto = tuple(name for name in autoknobs.WALK_ORDER
                        if name in spec.auto)
    refused: dict[str, str] = {}
    if "features" in filter_auto and str(mode) == "rings":
        # the ARM names the features; a held-out vote here would make
        # `rings+offset` a different arm from the one the ledger records
        filter_auto = tuple(a for a in filter_auto if a != "features")
        refused["features"] = "the arm names the feature kind"
    inherited["features"] = feature_kind_of(mode, spec)
    bound = autoknobs.bounding_axes(inherited, filter_auto)
    widest = autoknobs.bounding_of(
        [bound] + [{**inherited, axis: value}
                   for axis in filter_auto
                   for value in autoknobs.CANDIDATES.get(axis, ())])
    return inherited, filter_auto, widest, refused

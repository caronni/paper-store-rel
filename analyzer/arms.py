"""Where to sample it — the registration arms of DESIGN §4.6, and the
delta over `src/holo/receiver/plugins/plane_k.py` that §4.1 asks this module to be.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`.  The unmixing half lives in
:mod:`analyzer.unmix` (one file, one cap) and is re-exported here so
PLAN §1.2's contract reads off one module.

REUSE (DESIGN §4.1), per function:

* `plane_k.field_delta_dots` — CALLED by the `field` arm, whole: it
  evaluates the standing field through `lib/page_map`, with no support
  gate and no refusal, so a tile no evidence reached reads exactly zero,
  which is the pose (design I6/I8).  §4.6's "collapse to committed" is
  then the ANALYZER's own rule, made on the value: a field that reads
  zero over every cell the arm CONSUMES — its halo included, because the
  affine below is fitted over those cells too — renames the row rather
  than paying for a byte-identical duplicate of `committed`.
* `plane_k.choose_offset` — NOT called, for three reasons that are
  design-level, not convenience.  It needs a window-scope `RegionWindow`
  and the lane's FULL rasters, where this module holds a footprint and
  one crop opened once (DESIGN §4.4).  It searches x ONLY, where
  DESIGN §4.6 pre-registers a y arm.  And its objective is
  `fit_window_calibration`'s site-parity held-out split, where DESIGN
  §4.8 requires the analyzer's own SEARCH fold, which no arm's selection
  may see.  Its measured GRID is reused verbatim (`plane_k.shift_grid`'s
  ends and step, +-2 dots by 0.25).
* `plane_k.calibrated_rows` — NOT called: it emits `WindowEvidence` per
  window and runs `apply_region_context` at region scope, which is the
  production row's output shape, not an LLR over a footprint.  Its two
  halves are reached separately, through `analyzer.calibrate`.
* `local_affine.search` / `correlation_ratios` / `state_groups` /
  `unit_coordinates`, and `swim.translation_bound_dots` /
  `swim.resolution_dots` — CALLED by the `affine` and `word` arms.
  `swim.fit_window` itself is NOT called: it needs `swim.window_sites`
  and its own window crop, and it fits all three planes against the
  8-state level table where these arms fit ONE plane against its own
  known bits.
* `plane_field.tile_codes` — CALLED by :func:`_field_uncertainty_dots`,
  to name the grid cells a footprint covers.  The kernel smoother
  (`smooth`, `gaussian_kernel`, `clamp`) is no longer reached from here:
  `smooth_offsets` and its `smooth` arm were retired with the per-lane
  field (A3, 2026-09-12) and `analyzer.field2_kernel` carries the
  smoother `field2` fits with.
* `pilots.decode_color_word` — CALLED by the `word` arm as its BLIND
  verification: the arm believes its hard read only when the 100 sites
  decode to this tile's own counter.

THE DELTA FRAME (DESIGN §4.4; re-ruled with the page field, 2026-09-12).
Every delta in this module is PAGE-frame dots (x, y), and so is every
production delta it consumes: `PlaneField.delta_dots_xy` and
`plane_k.choose_offset`'s sweep both reach the raster through
`lib/page_map`, which carries a page-axis vector into pixels with the
window's own `page_linear` and therefore with its rotation.  A lane's
rot_k is a placement property the MAPPING composes, not something a
consumer applies, so an arm reads a published delta unrotated on a rot-2
owner exactly as on a rot-0 one.  What stays window-local is the swim's
local affine and `refine.color`'s candidate poses, and `page_map`'s own
`local_axes` / `page_axes` convert those.  The per-lane fact this module
DID have to rotate was retired with the receiver's per-lane fitter
(docs/PAGE-FIELD-DESIGN.md §2.2); :func:`to_page_frame` survives as the
algebra, applied to no production field.

PER-CELL DELTAS AND THE 6-TERM AFFINE.  `sample.read_rgb` takes a SCALAR
offset in dots plus an optional per-owner affine override; a per-cell
delta field (the plane field, an `Affine` correction) is not a scalar.
It is EXACTLY a modified affine whenever it is affine in the cell
coordinate — adding ``d(c) = a + Bc`` before the pose is
``M' = M(I + B)``, ``t' = (0.5 + a)M^T + t - 0.5 M'^T`` — which is what
:func:`affine_terms_for_delta` builds, by least squares over the owner's
own cells so a delta that is NOT affine (the plane field is bilinear
between tile centres) is fitted and its residual REPORTED rather than
silently dropped.  MEASURED on the record's own published fields
(review lens 2026-09-13): the approximation displaces a sample by a
median 0.005-0.076 dots and at worst 0.213 (sheet H's Y at halo 48),
all under the 0.25-dot resolution the field itself is published at.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from holo.receiver.format import pilots
from holo.receiver.lib import local_affine, plane_field as plane_field_lib, spectral
from holo.receiver.plugins import color_sites, plane_k, swim

from holo.receiver.plugins import calibrate as calibrate_plugin
from holo.receiver.plugins import color_region_anchor as anchor

from . import calibrate as cal
from . import frame as frame_mod
from . import patch as patch_mod
from . import pure as pure_mod
from . import sample as sample_mod
from .field2_kernel import BOUND_DOTS as FIELD2_BOUND_DOTS
from .types import (Evidence, Folds, Key, KnownFrame, Lane, LaneFootprint,
                    LocalContext, PLANE_OF, PageContext, PseudoLabels, Read,
                    RunInputs)
from .unmix import (LANE_MIX_TILES, MIX_SCOPES, UNMIX_MODES, _sample_tiles,
                    fit_mix, isolated_scores, lane_mix, mix_detail, shim_read,
                    unmix_score)

TILE_CELLS = 64

REGISTER_ARMS: tuple[str, ...] = (
    "committed", "field", "offset", "field+offset", "affine",
    "word", "field2", "field2+offset")

#: The `field2` family, and which field each member reads: the POOLED
#: FURNITURE field, one fit per page-plane over every lane,
#: certificate-free and generation-invariant (RULED 2026-09-03 late).
#: `field2c`, the per-lane CERTIFICATE-anchored fit that came first, was
#: RETIRED 2026-09-12 (A2) — it was the analyzer's last lane-keyed field
#: and the only one whose absence from `controls.FIELD_ARMS` was a
#: withholding hazard.
FIELD2_ARMS: dict[str, str] = {
    "field2": "furniture", "field2+offset": "furniture"}

#: WHICH FIELD EACH REGISTER ARM READS, for the withholding controls to
#: walk (DESIGN §8; PAGE-FIELD-PLAN A6).  TOTAL over `REGISTER_ARMS`,
#: and that is the whole safety of it: a control asks this table what an
#: arm reads, so an arm that is not in it must be an ERROR at
#: registration rather than a silent admission (the check below runs at
#: import).  `certified` = fitted from certificates and not rebuildable
#: without them, so a pass that withholds certificates must refuse the
#: arm; `furniture` = word and dust only, which a withholding pass may
#: keep; `none` = reads no field at all.
#:
#: The production `field` family is `certified` BY CONSTRUCTION, not by
#: inspection: every page field the receiver publishes is solved from
#: certified templates plus furniture and the blind tier is retired
#: (docs/PAGE-FIELD-DESIGN.md §2.5), so the reason is no longer "it may
#: have used certificates" but "it always does".
FIELD_SOURCE: dict[str, str] = {
    "committed": "none", "offset": "none", "affine": "none", "word": "none",
    "field": "certified", "field+offset": "certified",
    **FIELD2_ARMS}

#: What a production `field` arm BECOMES when the standing field reads
#: zero over every cell the arm consumes, or none stands:
#: :func:`_field_delta` returns None and :func:`register` renames the row
#: (`register_arm_effective`) rather than paying for a byte-identical
#: duplicate of `committed` /
#: `offset`.  That collapse is a property of the (page, plane, lane) and
#: the field alone — never of the unmix mode — so ONE evaluation says
#: what every other `field` arm on the same (key, lane) would do, which
#: is the economy `fixedpoint.blind_key` takes on the row it has already
#: computed (DESIGN §4.6; PAGE-FIELD-PLAN finding 3).
FIELD_COLLAPSE: dict[str, str] = {"field": "committed",
                                  "field+offset": "offset"}

#: DESIGN §4.6's blind 2-D grid, separable.  The x half is
#: `plane_k.shift_grid`'s reach verbatim (the measured yask battery's ends
#: and step); the y half is the pre-registered arm, HALF the reach because
#: production searches x only for a measured reason and a y arm ranging as
#: far would mostly be measuring its own freedom.
OFFSET_X_MIN, OFFSET_X_MAX = plane_k.SHIFT_MIN_DOTS, plane_k.SHIFT_MAX_DOTS
OFFSET_Y_MIN, OFFSET_Y_MAX = -1.0, 1.0
OFFSET_STEP_DOTS: float = plane_k.SHIFT_STEP_DOTS

#: The NARROW grid of the `field2+offset` arm (DESIGN §13's field2 lead):
#: the page field has already supplied the centre, so the search only has
#: to cover the LOCAL deviation around it — ±1 dot on x, and the same
#: pre-registered ±1 dot on y the wide arm uses.  A wide search on top of
#: a prior is the prior measured against its own freedom.
NARROW_X_MIN, NARROW_X_MAX = -1.0, 1.0

#: DESIGN §4.3: 32 cells of halo for Y, 16 for C and M — Y's labels are
#: the scarce class and it has to reach further for them.
HALO_CELLS: dict[str, int] = {"C": 16, "M": 16, "Y": 32}

#: How many tiles of a lane-page the PAGE-SCOPE context fit reads
#: (DESIGN §4.7's scope, `analyzer/GAPS-2026-09-03.md` §5).  The same
#: deterministic, target-excluding sample the lane-scope mixing fit takes,
#: at the same default size: the fit is memoised per (lane, page, stream,
#: certificate set), so this is paid once per pass, not once per tile.
PAGE_CTX_TILES: int = LANE_MIX_TILES

#: RULING 2026-09-03 (Germano): pose, page field and toner intensity are
#: LOCAL, so a fitted model takes a NEIGHBOURHOOD.  Radius 2 tiles = the
#: 5x5 block centred on the target, 24 neighbours; the target itself is
#: never in it, so no certificate of the tile being read enters the
#: correction applied to it.
LOCAL_CTX_RADIUS_TILES: int = 2

__all__ = [
    "ArmError", "FIELD2_ARMS", "FIELD_COLLAPSE", "FIELD_SOURCE",
    "HALO_CELLS", "LANE_MIX_TILES", "MIX_SCOPES",
    "LOCAL_CTX_RADIUS_TILES", "PAGE_CTX_TILES", "REGISTER_ARMS",
    "UNMIX_MODES",
    "affine_terms_for_delta",
    "evidence_for", "field_reach_dots", "fit_mix", "isolated_scores",
    "lane_mix", "local_context",
    "mix_detail",
    "page_context", "parse_arm", "register", "shim_read",
    "to_page_frame", "unmix_score", "word_pose", "word_site_rows",
]


class ArmError(RuntimeError):
    """The arm cannot be built as asked."""


def _check_field_source() -> None:
    """`FIELD_SOURCE` is TOTAL over `REGISTER_ARMS`, checked at import.

    The withholding controls decide what to refuse by asking this table
    what an arm reads (DESIGN §8).  A table that merely LISTS the field
    arms fails open — an arm nobody classified is admitted in silence,
    and the reviewer's `prior` arm proved it — so registering an arm
    without classifying it is an error here, at import, where it is one
    line to fix and cannot reach a control.
    """
    missing = tuple(arm for arm in REGISTER_ARMS if arm not in FIELD_SOURCE)
    unknown = tuple(sorted(set(FIELD_SOURCE) - set(REGISTER_ARMS)))
    if missing or unknown:
        raise ArmError(
            "FIELD_SOURCE must classify every register arm and no other: "
            f"unclassified {missing}, not a register arm {unknown}")


_check_field_source()

# ------------------------------------------------------- the delta frame

def to_page_frame(delta_dots_xy: Any, rot_k: int) -> np.ndarray:
    """A WINDOW-LOCAL dot delta, in the PAGE frame.

    A displacement applied through ``pose_linear(window.affine)``
    (whose linear part is ``level_terms[:, :2] @ R`` with
    ``R = pose.rotation_affine(rot_k, shape)[0]``, the window's own
    local frame) equals ``e_yx = R @ d_yx`` applied through
    ``level_terms[:, :2]``, which is what this module samples in; in the
    (x, y) spelling both functions use that is a quarter-turn of the
    pair.  Exact for every `rot_k`, arrays and scalars alike.

    NO PRODUCTION FIELD GOES THROUGH HERE.  Every published delta is a
    page-axis vector already (see the module docstring); this is the
    algebra the window-local searches — the swim's local affine,
    `refine.color`'s candidate poses — need when their answers have to
    be spoken about the page, and it is kept for that work alone.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    flat = delta.reshape(-1, 2)
    k = int(rot_k) % 4
    out = np.empty_like(flat)
    if k == 0:
        out[:] = flat
    elif k == 1:                    # R = [[0, -1], [1, 0]] on (y, x)
        out[:, 0], out[:, 1] = flat[:, 1], -flat[:, 0]
    elif k == 2:                    # R = -I
        out[:] = -flat
    else:                           # R = [[0, 1], [-1, 0]] on (y, x)
        out[:, 0], out[:, 1] = -flat[:, 1], flat[:, 0]
    return out.reshape(delta.shape)


def affine_terms_for_delta(terms: Sequence[float], cells_yx: np.ndarray,
                           delta_cells_yx: np.ndarray,
                           ) -> tuple[tuple[float, ...], float]:
    """6-term affine that adds ``delta`` to the cell BEFORE the pose.

    Exact when the delta is affine in the cell (an `Affine` correction, a
    constant offset); a least-squares fit with a reported maximum
    residual (in CELLS) when it is not (the plane field is bilinear
    between tile centres).  See the module docstring for the algebra.
    """
    matrix = np.asarray(terms, np.float64).reshape(2, 3)
    m = matrix[:, :2]
    t = matrix[:, 2]
    cells = np.asarray(cells_yx, np.float64)
    delta = np.asarray(delta_cells_yx, np.float64)
    design = np.column_stack((np.ones(cells.shape[0]), cells))
    solution, *_ = np.linalg.lstsq(design, delta, rcond=None)
    residual = float(np.max(np.abs(delta - design @ solution))) \
        if cells.shape[0] else 0.0
    a0 = solution[0]                     # (2,) constant part, (y, x)
    b = solution[1:].T                   # (2, 2), d = a0 + B c
    m_new = m + m @ b
    ones = np.array((1.0, 1.0))
    t_new = (0.5 * ones + a0) @ m.T + t - 0.5 * ones @ m_new.T
    out = (float(m_new[0, 0]), float(m_new[0, 1]), float(t_new[0]),
           float(m_new[1, 0]), float(m_new[1, 1]), float(t_new[1]))
    return out, residual


def _override_for_delta(lane: Lane, lfp: LaneFootprint,
                        delta_dots_xy_page: np.ndarray, cell_dots: int,
                        ) -> tuple[dict[int, tuple], float]:
    """Per-owner affines carrying a per-cell PAGE-frame dot delta.

    Fitted over each owner's OBSERVED cells, the halo among them — so
    the halo's deltas move where the target is sampled, which is why
    :func:`_field_delta` collapses on the observed cells and not on the
    target's.  The fit is exact for an affine delta and approximate for
    the bilinear plane field by a measured 0.005-0.076 dots (median) and
    0.213 at worst on the record's own fields, under the 0.25-dot
    resolution the field is published at; the worst residual is
    returned.
    """
    cells = np.asarray(lfp.tile.page_cells_yx, np.float64)
    delta_cells = np.asarray(delta_dots_xy_page, np.float64)[:, ::-1] \
        / float(cell_dots)                      # (x, y) dots -> (y, x) cells
    override: dict[int, tuple] = {}
    worst = 0.0
    for index in np.unique(lfp.owner_index[lfp.observed]).tolist():
        rows = np.flatnonzero(lfp.owner_index == int(index))
        terms = sample_mod._level_terms(lane, lane.placements[int(index)])
        built, residual = affine_terms_for_delta(
            terms, cells[rows], delta_cells[rows])
        override[int(index)] = built
        worst = max(worst, residual)
    return override, worst


# ------------------------------------------------------- registration

def _loss_of(read: Read, mix: spectral.PlaneMix, frame: KnownFrame,
             plane: int, mode: str, folds: Folds,
             lfp: LaneFootprint, crops: Any = None,
             spec: Any = None) -> float | None:
    if read.refusal is not None:
        return None
    # W8 ruling 1: a patch mode searches the grid under `subtract` unless
    # its spec says `search_mode="patch"`, in which case it gets its context.
    objective = patch_mod.objective_mode(mode, spec, grid=True)
    score = unmix_score(objective, plane, mix, read.values_rgb, frame,
                        fit_mask=folds.fit,
                        context=((crops, read, lfp, folds, spec)
                                 if objective in patch_mod.PATCH_MODES
                                 else None))
    return cal.fold_logloss(score, frame, plane, folds,
                            usable=np.asarray(lfp.observed, bool))


def _offset_grid(low: float, high: float, step: float) -> tuple[float, ...]:
    steps = int(round((high - low) / step))
    grid = [round(low + index * step, 6) for index in range(steps + 1)]
    return (0.0,) + tuple(value for value in grid if value != 0.0)


def _search_offset(crops: Any, lfp: LaneFootprint, frame: KnownFrame,
                   mix: spectral.PlaneMix, plane: int, mode: str,
                   folds: Folds, base: tuple[float, float],
                   override: Any, *,
                   x_range: tuple[float, float] | None = None,
                   y_range: tuple[float, float] | None = None,
                   profile: bool = False, spec: Any = None,
                   ) -> tuple[tuple[float, float], dict]:
    """DESIGN §4.6's separable 2-D grid on the SEARCH fold.

    `x_range`/`y_range` default to the arm's own pre-registered reach and
    are narrowed only by `field2+offset`, which searches around a prior.
    `profile` adds the per-candidate held-out losses to the detail — the
    `field2` fit weighs a tile's blind offset by how much its objective
    actually discriminated, which is a property of the whole profile and
    not of the winner.  Both are OFF by default, so every existing arm
    evaluates the same grid and emits the same row it did before.
    """
    low_x, high_x = (OFFSET_X_MIN, OFFSET_X_MAX) if x_range is None \
        else (float(x_range[0]), float(x_range[1]))
    low_y, high_y = (OFFSET_Y_MIN, OFFSET_Y_MAX) if y_range is None \
        else (float(y_range[0]), float(y_range[1]))
    best = (float(base[0]), float(base[1]))
    best_loss: float | None = None
    evaluated = 0
    losses: dict[str, list] = {"x": [], "y": []}
    for axis, name, grid in (
            (0, "x", _offset_grid(low_x, high_x, OFFSET_STEP_DOTS)),
            (1, "y", _offset_grid(low_y, high_y, OFFSET_STEP_DOTS))):
        for value in grid:
            candidate = list(best)
            candidate[axis] = float(base[axis] + value)
            read = sample_mod.read_rgb(
                crops, lfp, offset_dots_xy=(candidate[0], candidate[1]),
                affine_override=override, arm="offset")
            loss = _loss_of(read, mix, frame, plane, mode, folds, lfp,
                            **({"crops": crops, "spec": spec}
                               if mode in patch_mod.PATCH_MODES else {}))
            evaluated += 1
            if profile:
                losses[name].append(None if loss is None else float(loss))
            if loss is None:
                continue
            if best_loss is None or loss < best_loss:
                best_loss = loss
                best = (candidate[0], candidate[1])
    detail = {"offset_evaluations": evaluated,
              "offset_search_logloss": best_loss}
    # E2: under `patch_search_mode="patch"` every candidate pose is a
    # fresh extraction AND a fresh cross-fit, so the count is the cost.
    if patch_mod.objective_mode(mode, spec, grid=True) in patch_mod.PATCH_MODES:
        detail["patch_search_fits"] = evaluated
    if profile:
        detail["offset_profile"] = {name: tuple(values)
                                    for name, values in losses.items()}
    return best, detail


def _field_uncertainty_dots(field: Any, cells_yx: np.ndarray) -> float:
    """The standing field's median uncertainty over the footprint's tiles.

    RECORDED, never gating (design I8): a reader samples where the field
    says, and the uncertainty is what a sparse page says out loud about
    what it does not know.  Per TILE rather than per cell — the grid is
    tile-resolution, so cell weighting would only re-weight by footprint
    shape.
    """
    grid = np.asarray(field.uncertainty_dots, np.float64)
    cells = np.asarray(cells_yx, np.int64)
    if not cells.shape[0]:
        return 0.0
    # Clamped at the page edge, which is `plane_field.evaluate`'s own rule
    # for a cell the grid does not cover.
    tiles = np.clip(cells // TILE_CELLS, 0,
                    np.asarray(grid.shape, np.int64) - 1)
    codes = plane_field_lib.tile_codes(
        tiles * TILE_CELLS, (int(grid.shape[0]), int(grid.shape[1])),
        TILE_CELLS)
    return float(np.median(grid.reshape(-1)[np.unique(codes)]))


def _field_delta(field: Any, lfp: LaneFootprint,
                 target_plane: int | None = None,
                 ) -> tuple[np.ndarray | None, dict]:
    """`plane_k.field_delta_dots`, CALLED, at this footprint's cells.

    A `PlaneField` is keyed by (page, plane) and by nothing else, so it
    applies on EVERY lane of its page: the capture, the level, the scrap
    and the rotation are axes the receiver's evidence pooled over
    (docs/PAGE-FIELD-DESIGN.md §2.2).  What is left to refuse is another
    page, and — cheaply, because a driver can hand one in by mistake —
    another plane.  No rotation: the delta is a PAGE-axis vector at its
    source and this module samples in the page frame (see the module
    docstring).  No support gate either (I6/I8): a tile no evidence
    reached reads exactly zero, which is the pose, and a field that
    reads zero over every cell this arm CONSUMES is an EXPLICIT collapse
    to `committed` rather than a duplicate of it.

    THE COLLAPSE PREDICATE IS `observed`, halo included (F3/F4, review
    2026-09-13).  It used to be `in_tile & observed` — the target's own
    cells — and that made the collapse an approximation rather than the
    identity DESIGN §4.6 claims: :func:`_override_for_delta` fits each
    owner's affine over ALL of that owner's observed cells, so a halo
    cell with a non-zero delta tilts the affine the TARGET is then read
    through (the review lens measured it on a real footprint at halo 48:
    a target reading exactly zero still moves 4,092 of its 4,096 cells,
    by up to 0.0142 dots).
    Exact zero stays exact zero — no near-zero threshold
    — and the row says which cells decided it
    (`field_collapse_over`).  Reachable only at halo >= 34, since a
    narrower footprint cannot pass the next tile centre; the published
    fields on the record have no exactly-zero tile at all, so the
    widening costs the twin reuse nothing that was ever paid.
    """
    if field is None:
        return None, {"field_applied": False, "field_reason": "no_field"}
    if int(field.page) != int(lfp.tile.page):
        return None, {
            "field_applied": False,
            "field_reason": f"field_is_for_page_{int(field.page)}_not_"
                            f"{int(lfp.tile.page)}"}
    if target_plane is not None and int(field.plane) != int(target_plane):
        return None, {
            "field_applied": False,
            "field_reason": f"field_is_for_plane_{int(field.plane)}_not_"
                            f"{int(target_plane)}"}
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    page = np.asarray(plane_k.field_delta_dots(field, cells), np.float64)
    inside = np.asarray(lfp.observed, bool)
    if not np.any(inside):
        return None, {"field_applied": False, "field_reason": "no_observed"}
    stood = {"field_uncertainty_dots": _field_uncertainty_dots(field,
                                                             cells[inside]),
             "field_ordinal": int(field.ordinal)}
    if not np.any(page[inside]):
        return None, {"field_applied": False,
                      "field_reason": "field_reads_zero_here",
                      "field_collapse_over": "observed", **stood}
    median = np.median(page[inside], axis=0)
    return page, {
        "field_applied": True,
        "field_median_dots_xy": (float(median[0]), float(median[1])),
        "field_spread_dots": float(np.max(page[inside], axis=0).max()
                                   - np.min(page[inside], axis=0).min()),
        **stood}


def _field2_delta(page_field2: Any, lfp: LaneFootprint,
                  ) -> tuple[np.ndarray | None, dict]:
    """The analyzer's own page field at these cells — DESIGN §13.

    Already PAGE-frame (see :func:`register`), so no rotation.  A field
    for another page REFUSES and says whose it was, the way
    :func:`_field_delta` does: applying it would move the points silently
    and wrongly.  So does a PER-LANE field met on another lane — but a
    POOLED field (`PageField.lane is None`) is page-scope by
    construction, which is the whole content of the 2026-09-03 ruling,
    so every lane of its page may read it.  No support under the
    footprint is an EXPLICIT collapse to committed, never a duplicate
    row.
    """
    if page_field2 is None:
        return None, {"field2_applied": False, "field2_reason": "no_field"}
    if page_field2.lane is None:
        mine: Any = int(lfp.tile.page)
        theirs: Any = int(page_field2.page)
    else:
        mine = (tuple(lfp.lane), int(lfp.tile.page))
        theirs = (tuple(page_field2.lane), int(page_field2.page))
    if mine != theirs:
        return None, {"field2_applied": False,
                      "field2_reason": f"field2_is_for_{theirs}_not_{mine}"}
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    delta = page_field2.evaluate(cells, require_support=True)
    if delta is None:
        return None, {"field2_applied": False,
                      "field2_reason": "no_support"}
    inside = np.asarray(lfp.tile.in_tile, bool) & np.asarray(lfp.observed,
                                                             bool)
    if not np.any(inside):
        return None, {"field2_applied": False,
                      "field2_reason": "no_observed"}
    median = np.median(np.asarray(delta, np.float64)[inside], axis=0)
    return np.asarray(delta, np.float64), {
        "field2_applied": True,
        "field2_median_dots_xy": (float(median[0]), float(median[1])),
        "field2_support": page_field2.support_at_tile(lfp.tile.ty,
                                                      lfp.tile.tx),
        "field2_degree": int(page_field2.degree),
        "field2_pooled": bool(page_field2.pooled),
        "field2_n_lanes_pooled": len(page_field2.lanes),
        "field2_stream": str(page_field2.stream_id)}


def field_reach_dots(arm: str, lfp: LaneFootprint,
                     target_plane: int | None = None, *,
                     plane_field: Any = None) -> float:
    """How far a STANDING field moves this footprint's points, in dots.

    The term F3 (review 2026-09-13) found missing from the crop bound.
    `sample.open_crops`'s `bound_dots` is "the registration bound the
    arms may move within" and a field IS a registration delta, but
    :func:`evidence_for` built that bound from the offset search and the
    patch window alone — so a field borrowed the APERTURE margin, which
    `open_crops` keeps because a crop sized to the bound alone would
    refuse a read exactly at the bound.  Measured there (c2, 8 px/cell):
    a bare `field` arm refuses past 4.25 dots of constant field and
    `field+offset` past 2.25 with the winner at its +2-dot extreme, and
    from ~0.25 dots below each of those the read is still returned but
    edge-replicated, differing from a generously cut crop by up to 0.11
    of full scale.  The largest vector published on the record is 1.089
    dots (sheet H's Y), so nothing has reached it — this makes the
    margin true by construction rather than by luck.

    Rounded UP to `OFFSET_STEP_DOTS` so the crop memo's cut count does
    not fragment: every arm of one lane reads the same field over the
    same footprint and therefore asks for the same bound, so the
    battery's two cuts become at most three while a field stands
    (`sample.crop_memo_key` carries `bound_dots`, so the identity is
    right by construction; a battery naming `field2` arms as well pays
    one more).  The affine fit's own residual — 0.213 dots at worst on
    the record's fields — is what is left riding the aperture margin.

    The `field2` arms take `field2_kernel.BOUND_DOTS`, field2's clamp on
    its fitted grid and so an upper bound on every vector it can
    evaluate: their field is fitted AFTER the crop is opened, and the
    clamp is the honest ceiling available before it.  The `affine` arm's
    swim translation is already in the bound (`swim.translation_bound_
    dots(row)` IS `cell_dots`, the term that is there); its linear half
    is not.  `local_affine.search` opens the linear terms at
    `LINEAR_BOUND_FRACTION` (0.5) of the translation bound and clips each
    of them there, and `unit_coordinates` runs to +-1, so the two terms
    of one axis add at most ONE more translation bound where they meet at
    the corner: the arm's worst case is 2x `swim.translation_bound_
    dots(row)` — 4.00 dots at c2, 6.00 at c3 (measured 2026-09-13 by
    driving `local_affine.search` to its extreme; the review's "3x" read
    `search_linear`'s own signature, where the caller's bound is the
    translation's, and `search` halves it before it gets there).

    It stays out of the bound all the same, now for a measured reason
    rather than for want of one.  On the F3 fixture a CONSTANT delta of
    that size — strictly worse than the affine, which reaches it at the
    corner alone — still reads at both rungs, with 1.0 px of headroom
    left; it is the aperture's margin it spends to do it.  Nothing has
    ever come close: the review found no such affine in 3 GB of ledger,
    and `read_headroom_px` (`sample`) now publishes the distance every
    read sat from its refusal, so a search that did reach would be read
    off the ledger rather than guessed at.
    """
    if arm in FIELD2_ARMS:
        return float(FIELD2_BOUND_DOTS)
    if arm not in FIELD_COLLAPSE:
        return 0.0
    delta, _detail = _field_delta(plane_field, lfp, target_plane)
    observed = np.asarray(lfp.observed, bool)
    if delta is None or not np.any(observed):
        return 0.0
    reach = float(np.max(np.abs(np.asarray(delta, np.float64)[observed])))
    return float(np.ceil(reach / OFFSET_STEP_DOTS) * OFFSET_STEP_DOTS)


def _unit_coordinates(lfp: LaneFootprint) -> np.ndarray:
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    low = cells.min(axis=0)
    shape = tuple(int(value) for value in (cells.max(axis=0) - low + 1))
    return local_affine.unit_coordinates(cells - low, shape)


def _correlation_score(crops: Any, lfp: LaneFootprint, frame: KnownFrame,
                       mix: spectral.PlaneMix, plane: int, mode: str,
                       rows: np.ndarray, groups: Any, unit: np.ndarray,
                       cell_dots: int, lane: Lane, base: np.ndarray):
    """The swim's objective (`local_affine.correlation_ratios`), per plane."""

    def score(candidates: tuple[local_affine.Affine, ...]) -> np.ndarray:
        out = np.zeros(len(candidates), np.float64)
        for index, affine in enumerate(candidates):
            delta = base + affine.offsets_dots_xy(unit)
            override, _residual = _override_for_delta(
                lane, lfp, delta, cell_dots)
            read = sample_mod.read_rgb(crops, lfp, affine_override=override,
                                       arm="affine")
            if read.refusal is not None:
                continue
            values = unmix_score(mode, plane, mix, read.values_rgb, frame)
            sampled = np.asarray(values, np.float64)[rows][None, :]
            if not np.all(np.isfinite(sampled)):
                continue
            out[index] = float(local_affine.correlation_ratios(
                groups, sampled)[0])
        return out

    return score


def register(arm: str, lane: Lane, crops: Any, lfp: LaneFootprint,
             frame: KnownFrame, target_plane: int, unmix_mode: str,
             folds: Folds, *, mix: spectral.PlaneMix,
             plane_field: Any = None, page_field2: Any = None,
             cell_dots: int | None = None,
             spec: Any = None) -> tuple[Read, dict]:
    """DESIGN §4.6's registration arms over one (lane, footprint).

    Every delta is PAGE-frame dots, production's (`plane_field`, keyed
    by page and plane) and the analyzer's own (`page_field2`,
    :mod:`analyzer.field2`, DESIGN §13) alike: neither is rotated, and
    nothing here calls :func:`to_page_frame`.  The returned dict is
    BLIND diagnostics only.
    """
    if arm not in REGISTER_ARMS:
        raise ArmError(f"unknown registration arm {arm!r}")
    cell_dots = int(crops.cell_dots if cell_dots is None else cell_dots)
    # W8 ruling 1: the swim and the word pose ALWAYS search under `subtract`
    # for a patch mode (their objectives run over fit ∪ search rows); the
    # offset grid follows the spec (`patch_search_mode`).
    objective = patch_mod.objective_mode(
        unmix_mode, spec, grid=arm.endswith("offset"))
    detail: dict[str, Any] = {"register_arm": arm, "field_applied": False,
                              "register_objective_mode": objective}
    override: Any = None
    base_offset = (0.0, 0.0)
    narrow = False

    if arm in FIELD2_ARMS:
        searches = arm.endswith("+offset")
        delta, field2_detail = _field2_delta(page_field2, lfp)
        detail.update(field2_detail)
        detail["field2_anchors"] = FIELD2_ARMS[arm]
        if delta is None:
            arm = "offset" if searches else "committed"
            detail["register_arm_effective"] = arm
        else:
            override, residual = _override_for_delta(
                lane, lfp, delta, cell_dots)
            detail["field2_affine_residual_cells"] = float(residual)
            narrow = searches

    if arm in ("field", "field+offset"):
        delta, field_detail = _field_delta(plane_field, lfp, target_plane)
        detail.update(field_detail)
        if delta is None:
            arm = "committed" if arm == "field" else "offset"
            detail["register_arm_effective"] = arm
        else:
            override, residual = _override_for_delta(
                lane, lfp, delta, cell_dots)
            detail["field_affine_residual_cells"] = float(residual)

    if arm == "word":
        return word_pose(lane, crops, lfp, frame, target_plane,
                         unmix_mode=objective, mix=mix,
                         cell_dots=cell_dots, detail=detail, folds=folds)

    if arm == "affine":
        return _affine_arm(lane, crops, lfp, frame, target_plane,
                           objective, mix, cell_dots, detail, folds)

    if arm in ("offset", "field+offset", "field2+offset"):
        base_offset, search_detail = _search_offset(
            crops, lfp, frame, mix, target_plane, unmix_mode, folds,
            base_offset, override,
            x_range=(NARROW_X_MIN, NARROW_X_MAX) if narrow else None,
            spec=spec)
        detail.update(search_detail)
        detail["offset_grid_dots"] = ((NARROW_X_MIN, NARROW_X_MAX) if narrow
                                      else (OFFSET_X_MIN, OFFSET_X_MAX))

    read = sample_mod.read_rgb(crops, lfp, offset_dots_xy=base_offset,
                               affine_override=override, arm=arm)
    detail["offset_dots_xy"] = (float(base_offset[0]), float(base_offset[1]))
    detail["refusal"] = read.refusal
    return read, detail


def _affine_arm(lane: Lane, crops: Any, lfp: LaneFootprint,
                frame: KnownFrame, plane: int, mode: str,
                mix: spectral.PlaneMix, cell_dots: int,
                detail: dict,
                folds: Folds | None = None) -> tuple[Read, dict]:
    """`local_affine.search` from the committed pose, the swim's objective.

    Its objective is a correlation ratio against the known bits, and the
    known bits are not fold-partitioned by themselves — so this arm would
    fit on the SELECT fold that DESIGN §4.8 reserves for the arm choice,
    and any select-fold win it then scored would be its own search coming
    back.  The objective is therefore restricted to ``fit | search``
    (DESIGN §4.6's "a fold of its own"), and the ledger records which
    cells it saw.
    """
    known = np.asarray(frame.known[:, plane], bool) \
        & np.asarray(lfp.observed, bool)
    if folds is not None:
        known = known & ~np.asarray(folds.select, bool)
    rows = np.flatnonzero(known)
    if rows.size < 2 * spectral.MIN_PER_CLASS:
        return (sample_mod.read_rgb(crops, lfp, arm="affine"),
                {**detail, "refusal": "affine_too_few_known",
                 "register_arm_effective": "committed",
                 "affine_n_known": int(rows.size)})
    groups = local_affine.state_groups(
        np.asarray(frame.bits[rows, plane], np.int64))
    unit = _unit_coordinates(lfp)
    base = np.zeros((int(lfp.tile.page_cells_yx.shape[0]), 2), np.float64)
    score = _correlation_score(crops, lfp, frame, mix, plane, mode, rows,
                               groups, unit, cell_dots, lane, base)
    bound = swim.translation_bound_dots(lane_row_of(crops))
    resolution = swim.resolution_dots(float(crops.pitch_px_level), cell_dots)
    result = local_affine.search(score, local_affine.Affine.zero(), bound,
                                 resolution, int(rows.size))
    delta = base + result.affine.offsets_dots_xy(unit)
    override, residual = _override_for_delta(lane, lfp, delta, cell_dots)
    read = sample_mod.read_rgb(crops, lfp, affine_override=override,
                               arm="affine")
    detail.update({
        "affine_translation_dots_xy": tuple(
            float(value) for value in result.affine.translation),
        "affine_linear_dots": tuple(
            float(value) for value in result.affine.linear.ravel()),
        "affine_correlation": float(result.correlation),
        "affine_evaluations": int(result.n_evaluations),
        "affine_n_known": int(rows.size),
        "affine_residual_cells": float(residual),
        "affine_objective_fold": ("fit|search" if folds is not None
                                  else "known-cells (touches select)"),
        "refusal": read.refusal})
    return read, detail


def lane_row_of(crops: Any) -> Any:
    """The `FormatRow` a `Crops` implies — carried by its lane's inputs.

    `swim.translation_bound_dots(row)` is `cell_dots_of(row)` and nothing
    else, so a `Crops` (which carries `cell_dots`) is enough; this shim
    keeps the production call site literal.
    """

    class _Row:
        pitch_in = 0.0

    row = _Row()
    row.pitch_in = float(crops.cell_dots) / 600.0
    return row


# ------------------------------------------------------------- the word

def word_site_rows(inputs_row: Any, geometry: Any, lfp: LaneFootprint,
                   ) -> np.ndarray:
    """Footprint rows of the target tile's 100 word sites, in SITE order."""
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    width = int(lfp.tile.page_shape_cells_yx[1])
    keys = cells[:, 0] * width + cells[:, 1]
    word = np.asarray(geometry.word_cells_yx, np.int64)
    want = ((int(lfp.tile.ty) * TILE_CELLS + word[:, 0]) * width
            + int(lfp.tile.tx) * TILE_CELLS + word[:, 1])
    position = np.searchsorted(keys, want)
    position = np.clip(position, 0, keys.size - 1)
    return np.where(keys[position] == want, position, -1).astype(np.int64)


def word_pose(lane: Lane, crops: Any, lfp: LaneFootprint,
              frame: KnownFrame, target_plane: int, *,
              unmix_mode: str = "subtract",
              mix: spectral.PlaneMix | None = None,
              cell_dots: int | None = None,
              detail: dict | None = None,
              erasure_ladder: Sequence[int] = (0, 4, 8, 12, 16),
              geometry: Any = None, row: Any = None,
              folds: Folds | None = None,
              ) -> tuple[Read, dict]:
    """DESIGN §4.6's `word` arm — C and M only, BLIND-verified.

    Hard-read the isolated plane at the committed pose, form states
    ``3 * bit`` at the tile's 100 word sites, hand them to
    `pilots.decode_color_word` (erasures allowed for the least confident
    sites), and believe the read ONLY if the word decodes to this tile's
    own counter.  Then fit the tile's per-plane pose from the 120
    furniture sites with `local_affine.search`, scored against those now
    known bits.  If the word does not decode, the arm REFUSES — that
    refusal is the measurement (it separates "the C band is
    misregistered" from "the C band is above the floor").
    """
    detail = dict(detail or {})
    detail["register_arm"] = "word"
    cell_dots = int(crops.cell_dots if cell_dots is None else cell_dots)
    committed = sample_mod.read_rgb(crops, lfp, arm="word")
    if target_plane == PLANE_OF["Y"]:
        return committed, {**detail, "refusal": "word_is_cm_only",
                           "register_arm_effective": "committed"}
    if mix is None or not mix.accepted or committed.refusal is not None:
        return committed, {**detail, "refusal": "word_no_read",
                           "register_arm_effective": "committed"}
    geometry = geometry if geometry is not None else _geometry_of(frame)
    row = row if row is not None else _row_of(frame)
    if geometry is None or row is None:
        return committed, {**detail, "refusal": "word_no_format",
                           "register_arm_effective": "committed"}

    score = unmix_score(unmix_mode, target_plane, mix,
                        committed.values_rgb, frame)
    standard = cal._standardise(np.where(np.isfinite(score), score, 0.0))
    sites = word_site_rows(row, geometry, lfp)
    observed = np.asarray(lfp.observed, bool)
    usable = (sites >= 0) & observed[np.clip(sites, 0, None)]
    detail["word_sites_observed"] = int(np.count_nonzero(usable))
    if int(np.count_nonzero(usable)) < pilots.N_WORD_SITES:
        # a site the lane cannot see is an erasure by construction
        pass
    values = np.zeros(pilots.N_WORD_SITES, np.float64)
    values[usable] = standard[sites[usable]]
    bits = (values > 0.0).astype(np.uint8)
    confidence = np.where(usable, np.abs(values), -1.0)
    counter = row.tile_counter(int(lfp.tile.page), int(lfp.tile.ty),
                               int(lfp.tile.tx))
    order = np.argsort(confidence, kind="stable")
    decoded: int | None = None
    used_erasures = -1
    for n_erased in erasure_ladder:
        n_erased = max(int(n_erased),
                       int(pilots.N_WORD_SITES - np.count_nonzero(usable)))
        erasures = (np.sort(order[:n_erased]).astype(np.int64)
                    if n_erased else None)
        states = (bits * np.uint8(3)).astype(np.uint8)
        decoded = pilots.decode_color_word(states, row.seed, row, erasures)
        if decoded is not None:
            used_erasures = n_erased
            break
    detail["word_decoded_counter"] = decoded
    detail["word_counter"] = int(counter)
    detail["word_erasures"] = int(used_erasures)
    if decoded is None or int(decoded) != int(counter):
        return committed, {**detail, "refusal": "word_did_not_decode",
                           "register_arm_effective": "committed"}

    # the word is now a proven label set: fit the tile's per-plane pose.
    proven_bits = np.asarray(frame.bits[:, target_plane], np.uint8).copy()
    proven_known = np.asarray(frame.known[:, target_plane], bool).copy()
    site_bits = np.asarray(
        pilots.color_word_states(row.seed, (counter,), row)[0], np.uint8) == 3
    good = sites >= 0
    proven_bits[sites[good]] = site_bits[good].astype(np.uint8)
    proven_known[sites[good]] = True
    proven_known &= observed
    if folds is not None:
        # the POSE FIT is a search: it may not see the select fold that
        # DESIGN §4.8 reserves for the arm choice.  The word READ above
        # is the arm's blind verification, not its objective, so it keeps
        # all 100 sites.
        proven_known = proven_known & ~np.asarray(folds.select, bool)
    rows = np.flatnonzero(proven_known)
    detail["word_pose_cells"] = int(rows.size)
    detail["word_objective_fold"] = ("fit|search" if folds is not None
                                     else "known-cells (touches select)")
    if rows.size < 2 * spectral.MIN_PER_CLASS:
        return committed, {**detail, "refusal": "word_too_few_sites",
                           "register_arm_effective": "committed"}
    groups = local_affine.state_groups(
        np.asarray(proven_bits[rows], np.int64))
    unit = _unit_coordinates(lfp)
    base = np.zeros((int(lfp.tile.page_cells_yx.shape[0]), 2), np.float64)
    objective = _correlation_score(crops, lfp, frame, mix, target_plane,
                                   unmix_mode, rows, groups, unit,
                                   cell_dots, lane, base)
    bound = swim.translation_bound_dots(lane_row_of(crops))
    resolution = swim.resolution_dots(float(crops.pitch_px_level), cell_dots)
    result = local_affine.search(objective, local_affine.Affine.zero(),
                                 bound, resolution, int(rows.size))
    delta = base + result.affine.offsets_dots_xy(unit)
    override, residual = _override_for_delta(lane, lfp, delta, cell_dots)
    read = sample_mod.read_rgb(crops, lfp, affine_override=override,
                               arm="word")
    detail.update({
        "word_translation_dots_xy": tuple(
            float(value) for value in result.affine.translation),
        "word_linear_dots": tuple(
            float(value) for value in result.affine.linear.ravel()),
        "word_correlation": float(result.correlation),
        "word_evaluations": int(result.n_evaluations),
        "word_residual_cells": float(residual),
        "refusal": read.refusal})
    return read, detail


def _geometry_of(frame: KnownFrame) -> Any:
    return frame.detail.get("geometry") if frame.detail else None


def _row_of(frame: KnownFrame) -> Any:
    return frame.detail.get("row") if frame.detail else None


# ------------------------------------------- the page-scope context fit

def _ctx_side(llr: np.ndarray, bins: np.ndarray, values: np.ndarray,
              ids: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, ...]:
    return (llr[mask], bins[mask], values[mask], ids[mask])


def _ctx_pool(parts: Sequence[tuple[np.ndarray, ...]]
              ) -> tuple[np.ndarray, ...]:
    """`calibrate._pool`'s shape, over footprints instead of windows."""
    if not parts:
        return (np.zeros(0, np.float64), np.zeros(0, np.int8),
                np.zeros(0, bool), np.zeros(0, np.int64))
    return tuple(np.concatenate([part[index] for part in parts])
                 for index in range(4))


def _page_ctx_labels(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
                     key: Key, halo: int, unmix_mode: str, seed: int,
                     starved_fallback: bool,
                     ) -> tuple[list, list, int]:
    """Read one tile of the page sample and hand back its context labels.

    Deliberately the COMMITTED pose: the correction being fitted is a
    property of the neighbourhood a cell sits in, not of the sub-dot offset
    the target's own arm searched, and paying a 25-read offset search on
    every sampled tile would cost more than the whole rest of the pass.
    The row the fit sees is otherwise the ordinary one — the same crops,
    the same mixing fit, the same PAVA branches, `ctx_mode="none"` so
    nothing is corrected twice.
    """
    page, ty, tx, stream_id = key
    plane = PLANE_OF[str(stream_id)]
    cell_dots = color_sites.cell_dots_of(inputs.row)
    fp = frame_mod.tile_footprint(inputs.row, int(page), int(ty), int(tx),
                                  int(halo), geometry=inputs.geometry)
    folds = cal.split_folds(fp.page_cells_yx, int(seed))
    lfp = sample_mod.lane_footprint(lane, fp)
    if lfp is None or not np.any(lfp.observed):
        return [], [], 0
    try:
        crops = sample_mod.open_crops(lane, lfp, bound_dots=0.0,
                                      cell_dots=cell_dots)
    except sample_mod.SampleError:
        return [], [], 0
    read = sample_mod.read_rgb(crops, lfp, arm="page-ctx")
    if read.refusal is not None:
        return [], [], 0
    # `metadata_known` is REQUIRED and has no default (review 2026-09-03:
    # omitting it raised TypeError, which made every `page`/`local5` fit
    # unreachable).  False here on purpose: no metadata bit is threaded
    # into this sample, so claiming one is known would be a lie about
    # which labels the fit saw.
    frame = frame_mod.known_frame(inputs, certs, fp, key,
                                  metadata_known=False)
    mix, _scope = fit_mix(read.values_rgb, frame,
                          scope_ladder=("footprint",), lane_mix=None,
                          cells_yx=fp.page_cells_yx,
                          usable=np.asarray(lfp.observed, bool))
    if not mix.accepted:
        return [], [], 0
    score = unmix_score(unmix_mode, plane, mix, read.values_rgb, frame,
                        fit_mask=folds.fit)
    # the same branch policy the TARGET's own calibration uses, or the
    # correction would be fitted on differently-priced cells
    llr, detail = cal.calibrate(score, frame, plane, lfp, folds,
                                branches=cal.DEFAULT_BRANCHES,
                                ctx_mode="none",
                                starved_fallback=starved_fallback,
                                stream_id=str(stream_id))
    covered = cal.covered_cells(frame, plane, cal.DEFAULT_BRANCHES, lfp,
                                score, detail)
    cells = np.asarray(fp.page_cells_yx, np.int64)
    bins, _eligible = cal._production_bins(cells, llr)
    bins = np.where(covered, bins, np.int8(-1)).astype(np.int8)
    values = np.asarray(frame.bits[:, plane], bool)
    # PAGE cell ids, not footprint rows: `site_weights` must see the same
    # physical cell as ONE site when two sampled footprints' halos overlap,
    # which is what `physical_cell_ids` does for production's region fit.
    ids = (cells[:, 0] * int(inputs.cells_yx[1]) + cells[:, 1]).astype(
        np.int64)
    labels = (np.asarray(frame.known[:, plane], bool) & covered
              & (bins >= 0))
    fit_side = _ctx_side(llr, bins, values, ids, labels & folds.fit)
    val_side = _ctx_side(llr, bins, values, ids, labels & folds.search)
    return ([fit_side] if fit_side[0].size else [],
            [val_side] if val_side[0].size else [], 1)


def page_context(inputs: RunInputs, certs: Mapping[Key, Any], key: Key,
                 lane: Lane, *, halo_cells: int, unmix_mode: str,
                 seed: int = 0, n_tiles: int = PAGE_CTX_TILES,
                 starved_fallback: bool = cal.STARVED_FALLBACK,
                 ) -> tuple[PageContext | None, dict]:
    """DESIGN §4.7's LANE-PAGE context fit — one per (lane, page, stream).

    W1d recorded the per-footprint fit as a deviation because one footprint
    cannot see the lane-page; this is the scope §4.7 actually asks for, and
    it is `apply_region_context`'s arithmetic: pool the labelled cells of
    many footprints, run `context_decision` ONCE over the pool, and let its
    held-out gate decide adoption for all of them.  The analyzer's own
    folds replace production's site-parity split (fit fold fits, search
    fold validates), so the SELECT fold that chooses arms is untouched.

    The sample is `unmix._sample_tiles`' — deterministic, seeded from the
    lane identity, and with the TARGET TILE EXCLUDED, so a target's own
    certificates never enter the correction applied to it.  The memo key
    carries the sample, so two targets share one fit whenever neither is in
    it, exactly as `lane_mix` does.
    """
    page, ty, tx, stream_id = key
    token = frame_mod._certs_token(inputs, certs)
    tiles = _sample_tiles(inputs, lane, int(page), str(stream_id),
                          int(n_tiles), (int(ty), int(tx)))
    memo = inputs._cache.setdefault("arms_page_context", {})
    cache_key = (lane.lane_id, str(stream_id), token, int(page), tiles,
                 str(unmix_mode), int(halo_cells), int(seed),
                 bool(starved_fallback))
    hit = memo.get(cache_key)
    if hit is not None:
        return hit
    fit_parts: list = []
    val_parts: list = []
    n_read = 0
    for sample_ty, sample_tx in tiles:
        sample_key = (int(page), int(sample_ty), int(sample_tx),
                      str(stream_id))
        fit_side, val_side, read = _page_ctx_labels(
            inputs, certs, lane, sample_key, int(halo_cells),
            str(unmix_mode), int(seed), bool(starved_fallback))
        fit_parts.extend(fit_side)
        val_parts.extend(val_side)
        n_read += read
    fit_pool = _ctx_pool(fit_parts)
    val_pool = _ctx_pool(val_parts)
    offsets, adopted, reason, baseline, candidate = \
        calibrate_plugin.context_decision(fit_pool, val_pool)
    context = PageContext(
        lane=lane.lane_id, page=int(page), stream_id=str(stream_id),
        offsets=tuple(float(value) for value in offsets),
        adopted=bool(adopted), reason=str(reason),
        baseline_logloss=None if baseline is None else float(baseline),
        candidate_logloss=None if candidate is None else float(candidate),
        tiles=tiles, n_tiles_read=int(n_read),
        n_fit_labels=int(fit_pool[0].size),
        n_validation_labels=int(val_pool[0].size))
    detail = {"ctx_page_sample": tiles, "ctx_page_tiles_read": int(n_read),
              "ctx_page_fit_labels": int(fit_pool[0].size),
              "ctx_page_validation_labels": int(val_pool[0].size)}
    memo[cache_key] = (context, detail)
    return context, detail


# --------------------------------------- the neighbourhood context fit

def neighbourhood_tiles(inputs: RunInputs, ty: int, tx: int, radius: int,
                        ) -> tuple[tuple[int, int], ...]:
    """The (2r+1)^2 tile block centred on (ty, tx), target EXCLUDED."""
    tiles_y, tiles_x = inputs.tiles_yx
    out: list[tuple[int, int]] = []
    for dy in range(-int(radius), int(radius) + 1):
        for dx in range(-int(radius), int(radius) + 1):
            if dy == 0 and dx == 0:
                continue
            y, x = int(ty) + dy, int(tx) + dx
            if 0 <= y < int(tiles_y) and 0 <= x < int(tiles_x):
                out.append((y, x))
    return tuple(out)


def local_context(inputs: RunInputs, certs: Mapping[Key, Any], key: Key,
                  lane: Lane, *, halo_cells: int, unmix_mode: str,
                  seed: int = 0, radius_tiles: int = LOCAL_CTX_RADIUS_TILES,
                  starved_fallback: bool = cal.STARVED_FALLBACK,
                  ) -> tuple[LocalContext | None, dict]:
    """The 5x5-tile context fit of the 2026-09-03 ruling.

    Same variable, same solver and same adoption gate as `page_context` —
    the SCOPE is the whole difference, and the ruling is that the scope is
    a neighbourhood because the phenomena the correction stands in for
    (pose, the page field, toner intensity) are local.  The labelled cells
    of the neighbours are pooled, `context_decision` runs ONCE over the
    pool, and the per-bin fit-label counts come back with the offsets
    because `calibrate._apply_local_context` shrinks toward the target
    footprint's own fit in proportion to them.

    The target tile is not in the sample (`neighbourhood_tiles` excludes
    it), so nothing the target itself proves can enter the correction that
    is applied to it.
    """
    page, ty, tx, stream_id = key
    token = frame_mod._certs_token(inputs, certs)
    tiles = neighbourhood_tiles(inputs, int(ty), int(tx), int(radius_tiles))
    memo = inputs._cache.setdefault("arms_local_context", {})
    cache_key = (lane.lane_id, str(stream_id), token, int(page), tiles,
                 str(unmix_mode), int(halo_cells), int(seed),
                 bool(starved_fallback))
    hit = memo.get(cache_key)
    if hit is not None:
        return hit
    fit_parts: list = []
    val_parts: list = []
    n_read = 0
    for sample_ty, sample_tx in tiles:
        sample_key = (int(page), int(sample_ty), int(sample_tx),
                      str(stream_id))
        fit_side, val_side, read = _page_ctx_labels(
            inputs, certs, lane, sample_key, int(halo_cells),
            str(unmix_mode), int(seed), bool(starved_fallback))
        fit_parts.extend(fit_side)
        val_parts.extend(val_side)
        n_read += read
    fit_pool = _ctx_pool(fit_parts)
    val_pool = _ctx_pool(val_parts)
    offsets, adopted, reason, baseline, candidate = \
        calibrate_plugin.context_decision(fit_pool, val_pool)
    bin_labels = np.bincount(
        np.asarray(fit_pool[1], np.int64)[np.asarray(fit_pool[1]) >= 0],
        minlength=calibrate_plugin.N_CONTEXT_BINS,
    )[:calibrate_plugin.N_CONTEXT_BINS]
    context = LocalContext(
        lane=lane.lane_id, page=int(page), stream_id=str(stream_id),
        target_tile_yx=(int(ty), int(tx)), radius_tiles=int(radius_tiles),
        offsets=tuple(float(value) for value in offsets),
        bin_labels=tuple(int(value) for value in bin_labels),
        adopted=bool(adopted), reason=str(reason),
        baseline_logloss=None if baseline is None else float(baseline),
        candidate_logloss=None if candidate is None else float(candidate),
        tiles=tiles, n_tiles_read=int(n_read),
        n_fit_labels=int(fit_pool[0].size),
        n_validation_labels=int(val_pool[0].size))
    detail = {"ctx_local_sample": tiles,
              "ctx_local_tiles_read": int(n_read),
              "ctx_local_fit_labels": int(fit_pool[0].size),
              "ctx_local_validation_labels": int(val_pool[0].size)}
    memo[cache_key] = (context, detail)
    return context, detail


# ------------------------------------------------------- the composition

def parse_arm(arm: str) -> tuple[str, str]:
    """``"subtract+committed"`` -> ``("subtract", "committed")``."""
    if "+" not in arm:
        raise ArmError(f"arm {arm!r} must be '<unmix>+<register>'")
    head, _, tail = arm.partition("+")
    if head not in UNMIX_MODES:
        raise ArmError(f"unknown unmix mode {head!r} in arm {arm!r}")
    if tail not in REGISTER_ARMS:
        raise ArmError(f"unknown registration arm {tail!r} in arm {arm!r}")
    return head, tail


def evidence_for(inputs: RunInputs, certs: Mapping[Key, Any], key: Key,
                 lane: Lane, arm: str, *, halo_cells: int | None = None,
                 folds: Folds | None = None,
                 knobs: Mapping[str, Any] | None = None,
                 crop_memo: dict | None = None) -> Evidence:
    """One (tile-stream, lane, arm) row — the driver's single call.

    footprint -> lane footprint -> crops -> known frame -> mix -> register
    -> unmix -> calibrate -> sequential.  BLIND throughout: `certs` is
    whatever certificate mapping the caller wants used (already stripped
    under `--withhold`), and the metadata bit arrives as a knob.

    `knobs["ctx_mode"]` defaults to `"production"` (RULED 2026-09-03):
    production's own context correction is part of the default arm, not
    an extra — without it the Y plane re-derived 0 of 5 certified tiles.

    `crop_memo` is the caller's per-key crop memo (`sample.open_crops`'s
    `memo`, 2026-09-13).  The cut this arm asks for is decided by knobs
    that are per LANE, so the whole battery resolves to two cuts — three
    while a standing field grows the `field` arms' bound by its own
    reach (:func:`field_reach_dots`, F3) — and a memo hands the second
    arm of a kind the first one's pixels back —
    the same object, not a copy.  Nothing else about the arm changes: the
    memo is read where the crop is opened and nowhere else, and a caller
    that passes none cuts its own crop as before.
    """
    knobs = dict(knobs or {})
    page, ty, tx, stream_id = key
    plane = PLANE_OF[str(stream_id)]
    unmix_mode, register_arm = parse_arm(arm)
    halo = int(halo_cells if halo_cells is not None
               else HALO_CELLS[str(stream_id)])
    cell_dots = color_sites.cell_dots_of(inputs.row)
    fp = frame_mod.tile_footprint(inputs.row, page, ty, tx, halo,
                                  geometry=inputs.geometry)
    if folds is None:
        folds = cal.split_folds(fp.page_cells_yx, int(knobs.get("seed", 0)))
    blind: dict[str, Any] = {"arm": arm, "halo_cells": halo,
                             "unmix_mode": unmix_mode,
                             "register_arm": register_arm,
                             "fold_sizes": folds.sizes}
    # W8 B7: `aperture_cells="auto"` is not a width — the run chooses it
    # inside `patch_score` and records the choice under `auto_choices`, so
    # the CROP is opened at production's own aperture (and keeps its raw
    # pixels, which is what the candidates are re-filtered from).
    aperture_auto = patch_mod.is_auto(knobs.get("aperture_cells"))
    aperture_cells = (float(anchor.APERTURE_CELLS) if aperture_auto else
                      float(knobs.get("aperture_cells",
                                      anchor.APERTURE_CELLS)))
    if aperture_auto and unmix_mode not in patch_mod.PATCH_MODES:
        # A7's choice lives inside `patch_score`; a box arm in the same
        # profile cannot make it, and used to buy the raw crop for
        # nothing and say nothing about it (review 2026-09-06)
        aperture_auto = False
        blind["auto_refused"] = {"tile": "not_a_patch_mode"}
    aperture_kind = str(knobs.get("aperture_kind", "box"))
    if (aperture_cells != float(anchor.APERTURE_CELLS)
            or aperture_kind != "box"):
        blind["aperture_cells"] = aperture_cells
        blind["aperture_kind"] = aperture_kind
    empty = np.zeros(int(inputs.row.payload_cells), np.float64)
    no_observation = np.zeros(int(inputs.row.payload_cells), bool)
    # W8 B4 (ruling 8): the pseudo-label door accepts ONE type.  Anything
    # else — a dict, a tuple, an array — is refused here, before a pixel
    # is read, so no untyped label can ever train a filter or a map.
    pseudo = knobs.get("pseudo_labels")
    if pseudo is not None and not isinstance(pseudo, PseudoLabels):
        blind["refusal"] = "pseudo_labels:not_typed"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)

    lfp = sample_mod.lane_footprint(lane, fp)
    if lfp is None or not np.any(lfp.observed):
        blind["refusal"] = "no_owned_cell"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)
    bound = float(knobs.get("bound_dots",
                            max(abs(OFFSET_X_MIN), abs(OFFSET_X_MAX),
                                float(cell_dots)) + 0.5))
    # F3 (review 2026-09-13): and by what the STANDING field moves the
    # points, which is a registration delta the bound never counted.
    reach = field_reach_dots(register_arm, lfp, plane,
                             plane_field=knobs.get("plane_field"))
    if reach:
        bound += reach
        blind["field_reach_dots"] = reach
    # W8: a patch mode keeps the raw crop (ruling 13) and grows the bound by
    # its half-window so a patch at the search's edge stays inside the crop.
    is_patch = unmix_mode in patch_mod.PATCH_MODES
    spec = patch_mod.spec_from_knobs(knobs) if is_patch else None
    if is_patch:
        # the BOUNDING window: under `patch_window_cells="auto"` the run
        # may choose a wider one, and the crop has to reach it (W8 B7)
        bound += 0.5 * float(spec.bounding_window_cells) * float(cell_dots)
    # W8 B3 (A7): the aperture is a knob.  At the defaults `open_crops`
    # takes production's own code path, so every arm reads what it read
    # before; any other width or kind grows the crop and keeps the raw
    # pixels so the filtered crop can be re-derived from the ledger's
    # record of what was asked.
    non_default_aperture = (aperture_cells != float(anchor.APERTURE_CELLS)
                            or aperture_kind != "box")
    try:
        crops = sample_mod.open_crops(
            lane, lfp, bound_dots=bound, cell_dots=cell_dots,
            keep_raw=is_patch or non_default_aperture or aperture_auto,
            aperture_cells=aperture_cells, aperture_kind=aperture_kind,
            memo=crop_memo)
    except sample_mod.SampleError as error:
        blind["refusal"] = f"crop:{error}"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)

    frame = frame_mod.known_frame(
        inputs, certs, fp, key,
        metadata_known=bool(knobs.get("metadata_known", False)),
        metadata_bit=knobs.get("metadata_bit"))
    frame = _with_format(frame, inputs)
    blind["frame"] = dict(frame.detail)
    # The pseudo labels in FOOTPRINT rows, a LABEL beating a pseudo: a row
    # the frame already knows keeps its known bit.  `frame.known` is never
    # written — the DESIGN §4.5 assertion above stands exactly as it is —
    # and the rows travel beside the frame into the two fits below.
    pseudo_rows: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
    pseudo_detail: dict[str, Any] = {}
    if pseudo is not None:
        rows, bits, weights = patch_mod.pseudo_rows(fp, pseudo)
        keep = ~np.asarray(frame.known[rows, plane], bool)
        pseudo_rows = (rows[keep], bits[keep], weights[keep])
        pseudo_detail = {
            "n_pseudo_labels": int(rows[keep].size),
            "n_pseudo_offered": int(pseudo.size),
            "pseudo_weight": (float(weights[keep].max())
                              if rows[keep].size else None),
            "pseudo_source": str(pseudo.source)}

    committed = sample_mod.read_rgb(crops, lfp, arm="reference")
    memo_mix = knobs.get("lane_mix")
    if memo_mix is None and (unmix_mode == "global"
                             or "lane" in tuple(knobs.get(
                                 "mix_scope_ladder",
                                 ("footprint", "lane")))):
        memo_mix, lane_detail = lane_mix(
            inputs, lane, certs, str(stream_id), page=int(page),
            exclude_tile=(int(ty), int(tx)),
            n_tiles=int(knobs.get("lane_mix_tiles", LANE_MIX_TILES)))
        blind.update(lane_detail)
    if unmix_mode == "global":
        mix, scope = (memo_mix, "lane") if memo_mix is not None else (
            None, "refused")
        if mix is None:
            blind["refusal"] = "global_needs_a_lane_mix"
            return Evidence(key=key, lane=lane.lane_id, arm=arm,
                            llr_sequential=empty, observed=no_observation,
                            blind=blind)
    else:
        mix, scope = fit_mix(
            committed.values_rgb, frame,
            scope_ladder=tuple(knobs.get("mix_scope_ladder",
                                         ("footprint", "lane"))),
            lane_mix=memo_mix, cells_yx=fp.page_cells_yx,
            usable=np.asarray(lfp.observed, bool))
    blind.update(mix_detail(mix, scope))
    if not mix.accepted:
        blind["refusal"] = f"{plane_k.REASON_NO_MIX}:{mix.reason}"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)

    page_field2 = None
    if register_arm in FIELD2_ARMS:
        # Fitted HERE and memoised, for the reason `page_context` gives:
        # the fit reads rasters, and `register` is handed pixels rather
        # than reaching for them.  The import is local because `field2`
        # imports this module for the offset search it shares.
        from . import field2 as field2_mod
        page_field2 = field2_mod.field_for(
            inputs, certs, lane, str(stream_id),
            {**knobs, "halo_cells": halo},
            anchors=FIELD2_ARMS[register_arm], page=int(page))
    read, register_detail = register(
        register_arm, lane, crops, lfp, frame, plane, unmix_mode, folds,
        mix=mix, plane_field=knobs.get("plane_field"),
        page_field2=page_field2, cell_dots=cell_dots, spec=spec)
    blind.update(register_detail)
    if read.refusal is not None:
        blind["refusal"] = f"read:{read.refusal}"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)
    # F3's other half: how far this read sat from the refusal it did not
    # hit.  Recorded, gating nothing — a pass that never refuses can then
    # say how much margin it had rather than only that it had some.
    blind["read_headroom_px"] = sample_mod.read_headroom_px(crops, lfp, read)

    if is_patch:
        # P1g: the 5x5 neighbourhood's own certified cargo as extra
        # training rows, memoised per (lane, tile) — a train-SCOPE knob,
        # off by default (the footprint's own halo is the default scope).
        local_labels = None
        if spec.train_scope == "local5":
            from . import patchlocal as patchlocal_mod
            # the target FOOTPRINT's cells are handed over so the loader
            # can drop them: a halo-48 footprint reaches deep into its
            # neighbours, and a harvested row that is also one of this
            # footprint's search- or select-fold cells would put the arm
            # choice and the lane weights partly in-sample (review
            # 2026-09-06, DESIGN §4.8)
            local_labels, local_detail = patchlocal_mod.local_patch_labels(
                inputs, certs, key, lane, spec, unmix_mode=unmix_mode,
                footprint_cells_yx=fp.page_cells_yx)
            blind.update(local_detail)
        score, patch_detail = patch_mod.patch_score(
            spec, plane, frame, mix, crops, read, lfp, folds,
            mode=unmix_mode, local_labels=local_labels,
            extra_labels=pseudo_rows)
        blind.update(patch_detail)
    else:
        score = unmix_score(unmix_mode, plane, mix, read.values_rgb, frame,
                            fit_mask=folds.fit)
    # the door's record OVER the patch detail: `pseudo_source` says who
    # labelled the fit set from outside (`decoder`), `patch_labels_from`
    # keeps saying `halo+self+bp` when self-training was on as well
    blind.update(pseudo_detail)
    # THE MAP-SIDE DOOR (review 2026-09-06).  A PATCH arm's filter has
    # already absorbed the decoder's rows, so handing the SAME rows to
    # the PAVA map as training pairs fits the map on the filter's output
    # at the cells that trained it — ruling 7 one stage down.  OFF by
    # default for a patch mode; ON for a box arm, where the map is the
    # only place a pseudo label can act.  An explicit knob still wins.
    refit_calibration = bool(knobs.get("refit_calibration", not is_patch))
    if pseudo_rows is not None:
        blind["refit_calibration"] = refit_calibration
    # `branches` is `cal.DEFAULT_BRANCHES` — "pooled", the ONE map
    # `plane_k.calibrated_rows` fits — unless a caller asks for something
    # else; passing the unmix MODE is what re-arms the two-population split
    # of DESIGN §4.7.  RULED 2026-09-03 from the gate in
    # `analyzer/GAPS-2026-09-03.md` §8: pooled costs no certificate on
    # either sheet and buys one on sheet H's C sample.
    ctx_mode = str(knobs.get("ctx_mode", "production"))
    starved_fallback = bool(knobs.get("starved_fallback",
                                      cal.STARVED_FALLBACK))
    page_ctx = None
    local_ctx = None
    if ctx_mode == cal.CTX_LOCAL:
        # same reason as the page fit: the neighbourhood fit reads rasters
        # and `calibrate` reads none.  Memoised per (lane, page, stream,
        # certificate set, neighbourhood).
        local_ctx, local_detail = local_context(
            inputs, certs, key, lane, halo_cells=halo,
            unmix_mode=unmix_mode, seed=int(knobs.get("seed", 0)),
            radius_tiles=int(knobs.get("ctx_local_radius_tiles",
                                       LOCAL_CTX_RADIUS_TILES)),
            starved_fallback=starved_fallback)
        blind.update(local_detail)
    if ctx_mode == cal.CTX_PAGE:
        # fitted here, not in `calibrate`: the fit reads rasters, and
        # `calibrate` reads none.  Memoised per (lane, page, stream,
        # certificate set), so the pass pays for it once.
        page_ctx, page_detail = page_context(
            inputs, certs, key, lane, halo_cells=halo,
            unmix_mode=unmix_mode, seed=int(knobs.get("seed", 0)),
            n_tiles=int(knobs.get("ctx_page_tiles", PAGE_CTX_TILES)),
            starved_fallback=starved_fallback)
        blind.update(page_detail)
    if pure_mod.is_pure(knobs, unmix_mode):
        # W8 B6 (P0, the user's ruling of 2026-09-06): the PURE path.  A
        # discriminant that already separates the classes needs no PAVA,
        # no context and no Platt between it and BP — only its own
        # held-out error rate as a log-odds.  ONE dispatch: the whole
        # calibration stage is replaced and nothing else here changes.
        # The decoder's pseudo rows are not handed on as LABELS (no map
        # to refit — they train the FILTER alone) but they travel as ROWS,
        # so the self price subtracts the cells that trained it (R3).
        llr, cal_detail = pure_mod.pure_llr(
            score, frame, plane, lfp, folds,
            spec=pure_mod.spec_from_knobs(knobs), stream_id=str(stream_id),
            pseudo_rows=(None if pseudo_rows is None else pseudo_rows[0]))
    else:
        llr, cal_detail = cal.calibrate(
            score, frame, plane, lfp, folds,
            branches=str(knobs.get("branches") or cal.DEFAULT_BRANCHES),
            ctx_mode=ctx_mode, page_context=page_ctx,
            local_context=local_ctx, starved_fallback=starved_fallback,
            stream_id=str(stream_id),
            # W8 B2 (C2): the per-state context residual, a knob; B4: the
            # pseudo rows reach the PAVA fit set unless `refit_calibration`
            # is off (then the patch filter alone sees them)
            ctx_state=bool(knobs.get("ctx_state", False)),
            pseudo=(pseudo_rows if refit_calibration else None))
    blind.update(cal_detail)
    sequential, observed = cal.to_sequential(llr, lfp, inputs.row,
                                            inputs.geometry, key)
    blind["n_observed_cargo"] = int(np.count_nonzero(observed))
    return Evidence(key=key, lane=lane.lane_id, arm=arm,
                    llr_sequential=sequential, observed=observed, blind=blind)


def _with_format(frame: KnownFrame, inputs: RunInputs) -> KnownFrame:
    """Carry `row`/`geometry` in the frame's detail for the word arm.

    `KnownFrame` is a frozen value and W1b owns it; the word arm needs the
    format row and site geometry and they are already in `inputs`.  Rather
    than widen the type, they ride in `detail`, which is the frame's own
    blind bookkeeping bag.
    """
    from dataclasses import replace
    return replace(frame, detail={**dict(frame.detail), "row": inputs.row,
                                  "geometry": inputs.geometry})

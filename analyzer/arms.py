"""Where to sample it — the registration arms of DESIGN §4.6, and the
delta over `holo3/plugins/plane_k.py` that §4.1 asks this module to be.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`.  The unmixing half lives in
:mod:`analyzer.unmix` (one file, one cap) and is re-exported here so
PLAN §1.2's contract reads off one module.

REUSE (DESIGN §4.1), per function:

* `plane_k.field_delta_dots` — CALLED by the `field` arm, support gate
  and all: it returns None when the standing field has no support under
  the footprint, which is exactly §4.6's "collapse to committed".
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
  `swim.fit_window` itself is NOT called: it needs `fields.window_sites`
  and its own window crop, and it fits all three planes against the
  8-state level table where these arms fit ONE plane against its own
  known bits.
* `plane_field.smooth` / `gaussian_kernel` — CALLED by
  :func:`smooth_offsets`, with the support normalisation DESIGN §4.6
  requires (`smooth` is zero-padded, so smoothing offsets alone pulls a
  sparse band's edge toward zero — the failure §4.6 names).
* `pilots.decode_color_word` — CALLED by the `word` arm as its BLIND
  verification: the arm believes its hard read only when the 100 sites
  decode to this tile's own counter.

THE DELTA FRAME (DESIGN §4.4, ruled 2026-09-03).  Every delta in this
module is PAGE-frame dots (x, y).  Production's deltas are WINDOW-LOCAL
(`PlaneField.delta_dots_xy` and `plane_k.choose_offset` are both applied
through `anchor.pose_linear(window.affine)`, whose linear part is
``level_terms[:, :2] @ rotation(rot_k)``), so every production delta an
arm consumes goes through :func:`to_page_frame` first, with the
CONTRIBUTING PLACEMENT's own `rot_k`.  579 of sheet I's 3,687 accepted
placements are rot_k 2, where the two frames differ by a sign on both
axes; getting this backwards makes the field arm actively harmful, and a
test on a rot_k-2 placement is mandatory.

PER-CELL DELTAS AND THE 6-TERM AFFINE.  `sample.read_rgb` takes a SCALAR
offset in dots plus an optional per-owner affine override; a per-cell
delta field (the plane field, an `Affine` correction) is not a scalar.
It is EXACTLY a modified affine whenever it is affine in the cell
coordinate — adding ``d(c) = a + Bc`` before the pose is
``M' = M(I + B)``, ``t' = (0.5 + a)M^T + t - 0.5 M'^T`` — which is what
:func:`affine_terms_for_delta` builds, by least squares over the owner's
own cells so a delta that is NOT affine (the plane field is bilinear
between tile centres) is fitted and its residual REPORTED rather than
silently dropped.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from holo3.format import pilots
from holo3.lib import local_affine, plane_field as plane_field_lib, spectral
from holo3.plugins import color_sites, plane_k, swim

from holo3.plugins import calibrate as calibrate_plugin

from . import calibrate as cal
from . import frame as frame_mod
from . import sample as sample_mod
from .types import (Evidence, Folds, Key, KnownFrame, Lane, LaneFootprint,
                    LocalContext, PLANE_OF, PageContext, Read, RunInputs)
from .unmix import (LANE_MIX_TILES, MIX_SCOPES, UNMIX_MODES, _sample_tiles,
                    fit_mix, isolated_scores, lane_mix, mix_detail, shim_read,
                    unmix_score)

TILE_CELLS = 64

REGISTER_ARMS: tuple[str, ...] = (
    "committed", "field", "offset", "field+offset", "affine", "smooth",
    "word", "field2", "field2+offset", "field2c", "field2c+offset")

#: The `field2` family, and which field each member reads.  `field2` is
#: the POOLED FURNITURE field (one fit per page-plane over every lane,
#: certificate-free, generation-invariant — RULED 2026-09-03 late);
#: `field2c` is the per-lane CERTIFICATE-anchored fit that came first.
FIELD2_ARMS: dict[str, str] = {
    "field2": "furniture", "field2+offset": "furniture",
    "field2c": "certified", "field2c+offset": "certified"}

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
    "ArmError", "FIELD2_ARMS", "HALO_CELLS", "LANE_MIX_TILES", "MIX_SCOPES",
    "LOCAL_CTX_RADIUS_TILES", "PAGE_CTX_TILES", "REGISTER_ARMS",
    "UNMIX_MODES",
    "affine_terms_for_delta",
    "evidence_for", "fit_mix", "isolated_scores", "lane_mix", "local_context",
    "mix_detail",
    "page_context", "parse_arm", "register", "shim_read", "smooth_offsets",
    "to_page_frame", "unmix_score", "word_pose", "word_site_rows",
]


class ArmError(RuntimeError):
    """The arm cannot be built as asked."""

# ------------------------------------------------------- the delta frame

def to_page_frame(delta_dots_xy: Any, rot_k: int) -> np.ndarray:
    """A production (window-local) dot delta, in the PAGE frame.

    Production applies a delta through ``pose_linear(window.affine)``,
    whose linear part is ``level_terms[:, :2] @ R`` with
    ``R = pose.rotation_affine(rot_k, shape)[0]``; this module applies it
    through ``level_terms[:, :2]``.  Equal displacement therefore needs
    ``e_yx = R @ d_yx``, and in the (x, y) spelling both functions use
    that is a quarter-turn of the pair.  Exact for every `rot_k`, arrays
    and scalars alike.
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


def _owner_rot_k(lane: Lane, lfp: LaneFootprint) -> dict[int, int]:
    return {int(index): int(lane.placements[int(index)].rot_k)
            for index in np.unique(lfp.owner_index[lfp.observed]).tolist()}


def _override_for_delta(lane: Lane, lfp: LaneFootprint,
                        delta_dots_xy_page: np.ndarray, cell_dots: int,
                        ) -> tuple[dict[int, tuple], float]:
    """Per-owner affines carrying a per-cell PAGE-frame dot delta."""
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
             lfp: LaneFootprint) -> float | None:
    if read.refusal is not None:
        return None
    score = unmix_score(mode, plane, mix, read.values_rgb, frame,
                        fit_mask=folds.fit)
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
                   profile: bool = False,
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
            loss = _loss_of(read, mix, frame, plane, mode, folds, lfp)
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
    if profile:
        detail["offset_profile"] = {name: tuple(values)
                                    for name, values in losses.items()}
    return best, detail


def _field_delta(inputs_or_field: Any, lane: Lane, lfp: LaneFootprint,
                 target_plane: int | None = None,
                 ) -> tuple[np.ndarray | None, dict]:
    """`plane_k.field_delta_dots`, CALLED, then rotated to the page frame.

    A `PlaneField` names its own (capture, level, page, plane) and the
    driver hands one in as a knob; applying another lane's or another
    plane's field would move the points silently and wrongly, so the
    mismatch REFUSES and says which key it was handed.
    """
    field = inputs_or_field
    if field is None:
        return None, {"field_applied": False, "field_reason": "no_field"}
    mine = (str(lane.capture_id), int(lane.level_index),
            int(lfp.tile.page),
            None if target_plane is None else int(target_plane))
    theirs = (str(field.capture_id), int(field.level_index),
              int(field.page),
              None if target_plane is None else int(field.plane))
    if mine != theirs:
        return None, {"field_applied": False,
                      "field_reason": f"field_is_for_{theirs}_not_{mine}"}
    cells = np.asarray(lfp.tile.page_cells_yx, np.int64)
    local = plane_k.field_delta_dots(field, cells)
    if local is None:
        return None, {"field_applied": False, "field_reason": "no_support"}
    local = np.asarray(local, np.float64)
    page = np.zeros_like(local)
    rot = _owner_rot_k(lane, lfp)
    owner = np.asarray(lfp.owner_index, np.int64)
    for index, rot_k in rot.items():
        rows = np.flatnonzero(owner == index)
        page[rows] = to_page_frame(local[rows], rot_k)
    inside = np.asarray(lfp.tile.in_tile, bool) & np.asarray(lfp.observed,
                                                             bool)
    if not np.any(inside):
        return None, {"field_applied": False, "field_reason": "no_observed"}
    median = np.median(page[inside], axis=0)
    return page, {
        "field_applied": True,
        "field_median_dots_xy": (float(median[0]), float(median[1])),
        "field_spread_dots": float(np.max(page[inside], axis=0).max()
                                   - np.min(page[inside], axis=0).min()),
        "field_rot_k": tuple(sorted(set(rot.values())))}


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
             plane_field: Any = None, smooth_field: Any = None,
             page_field2: Any = None,
             cell_dots: int | None = None) -> tuple[Read, dict]:
    """DESIGN §4.6's registration arms over one (lane, footprint).

    Every delta is PAGE-frame dots; a production delta arrives rotated by
    :func:`to_page_frame` before it is used.  The returned dict is BLIND
    diagnostics only.

    `page_field2` is the analyzer's OWN page field (:mod:`analyzer.field2`,
    DESIGN §13) and is already page-frame — it is fitted from this
    module's own blind offsets, which are page-frame by construction —
    so it does NOT go through :func:`to_page_frame`.  Only production's
    deltas do.
    """
    if arm not in REGISTER_ARMS:
        raise ArmError(f"unknown registration arm {arm!r}")
    cell_dots = int(crops.cell_dots if cell_dots is None else cell_dots)
    detail: dict[str, Any] = {"register_arm": arm, "field_applied": False}
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
        delta, field_detail = _field_delta(plane_field, lane, lfp,
                                           target_plane)
        detail.update(field_detail)
        if delta is None:
            arm = "committed" if arm == "field" else "offset"
            detail["register_arm_effective"] = arm
        else:
            override, residual = _override_for_delta(
                lane, lfp, delta, cell_dots)
            detail["field_affine_residual_cells"] = float(residual)

    if arm == "smooth":
        if smooth_field is None:
            return (sample_mod.read_rgb(crops, lfp, arm=arm),
                    {**detail, "refusal": "no_smooth_field",
                     "register_arm_effective": "committed"})
        grid = np.asarray(smooth_field, np.float64)
        value = grid[int(lfp.tile.ty), int(lfp.tile.tx)]
        if not np.all(np.isfinite(value)):
            return (sample_mod.read_rgb(crops, lfp, arm=arm),
                    {**detail, "refusal": "no_smooth_support",
                     "register_arm_effective": "committed"})
        base_offset = (float(value[0]), float(value[1]))
        detail["smooth_offset_dots_xy"] = base_offset

    if arm == "word":
        return word_pose(lane, crops, lfp, frame, target_plane,
                         unmix_mode=unmix_mode, mix=mix,
                         cell_dots=cell_dots, detail=detail, folds=folds)

    if arm == "affine":
        return _affine_arm(lane, crops, lfp, frame, target_plane,
                           unmix_mode, mix, cell_dots, detail, folds)

    if arm in ("offset", "field+offset", "field2+offset", "field2c+offset"):
        base_offset, search_detail = _search_offset(
            crops, lfp, frame, mix, target_plane, unmix_mode, folds,
            base_offset, override,
            x_range=(NARROW_X_MIN, NARROW_X_MAX) if narrow else None)
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
        decoded = pilots.decode_color_word(states, row.seed, erasures)
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
    site_bits = np.asarray(pilots.color_word_states(row.seed, (counter,))[0],
                           np.uint8) == 3
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


# ---------------------------------------------------------- the smoothing

def smooth_offsets(offsets_by_tile: Mapping[tuple[int, int],
                                            tuple[float, float]],
                   weights_by_tile: Mapping[tuple[int, int], float],
                   tiles_yx: tuple[int, int],
                   bandwidth_tiles: float = plane_field_lib.BANDWIDTH_TILES,
                   ) -> tuple[np.ndarray, np.ndarray]:
    """DESIGN §4.6's SUPPORT-NORMALISED smoothing of the offset solutions.

    ``num = smooth(w * offset)``, ``den = smooth(w)``, evaluated only
    where ``den > 0``.  `plane_field.smooth` is zero-padded, so smoothing
    the offsets alone would pull every tile at the edge of a sparse band
    toward zero — the failure DESIGN §4.6 names.  Tiles with no support
    come back NaN, and `register`'s `smooth` arm collapses to committed
    there rather than inventing a delta.
    """
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    weighted = np.zeros((height, width, 2), np.float64)
    weight = np.zeros((height, width), np.float64)
    for (ty, tx), value in offsets_by_tile.items():
        w = float(weights_by_tile.get((ty, tx), 0.0))
        if w <= 0.0 or not np.all(np.isfinite(value)):
            continue
        weighted[int(ty), int(tx)] = np.asarray(value, np.float64) * w
        weight[int(ty), int(tx)] = w
    kernel = plane_field_lib.gaussian_kernel(bandwidth_tiles)
    denominator = plane_field_lib.smooth(weight, kernel)
    out = np.full((height, width, 2), np.nan, np.float64)
    live = denominator > 0.0
    for axis in (0, 1):
        numerator = plane_field_lib.smooth(weighted[..., axis], kernel)
        out[..., axis] = np.where(live, numerator / np.where(
            live, denominator, 1.0), np.nan)
    return out, denominator


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
                 knobs: Mapping[str, Any] | None = None) -> Evidence:
    """One (tile-stream, lane, arm) row — the driver's single call.

    footprint -> lane footprint -> crops -> known frame -> mix -> register
    -> unmix -> calibrate -> sequential.  BLIND throughout: `certs` is
    whatever certificate mapping the caller wants used (already stripped
    under `--withhold`), and the metadata bit arrives as a knob.

    `knobs["ctx_mode"]` defaults to `"production"` (RULED 2026-09-03):
    production's own context correction is part of the default arm, not
    an extra — without it the Y plane re-derived 0 of 5 certified tiles.
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
    empty = np.zeros(int(inputs.row.payload_cells), np.float64)
    no_observation = np.zeros(int(inputs.row.payload_cells), bool)

    lfp = sample_mod.lane_footprint(lane, fp)
    if lfp is None or not np.any(lfp.observed):
        blind["refusal"] = "no_owned_cell"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)
    bound = float(knobs.get("bound_dots",
                            max(abs(OFFSET_X_MIN), abs(OFFSET_X_MAX),
                                float(cell_dots)) + 0.5))
    try:
        crops = sample_mod.open_crops(lane, lfp, bound_dots=bound,
                                      cell_dots=cell_dots)
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
        smooth_field=knobs.get("smooth_field"), page_field2=page_field2,
        cell_dots=cell_dots)
    blind.update(register_detail)
    if read.refusal is not None:
        blind["refusal"] = f"read:{read.refusal}"
        return Evidence(key=key, lane=lane.lane_id, arm=arm,
                        llr_sequential=empty, observed=no_observation,
                        blind=blind)

    score = unmix_score(unmix_mode, plane, mix, read.values_rgb, frame,
                        fit_mask=folds.fit)
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
    llr, cal_detail = cal.calibrate(
        score, frame, plane, lfp, folds,
        branches=str(knobs.get("branches") or cal.DEFAULT_BRANCHES),
        ctx_mode=ctx_mode, page_context=page_ctx, local_context=local_ctx,
        starved_fallback=starved_fallback,
        stream_id=str(stream_id))
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

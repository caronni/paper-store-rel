"""Lanes, ownership, crops and reads — DESIGN §4.2 (per tile), §4.3
(ownership), §4.4 (sampling).

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`.  This module turns a page-cell footprint into
pixels and nothing else; what the pixels MEAN is `arms.py`'s problem.

Three rulings from wave 1 are implemented here rather than assumed:

* **lanes per tile** come from `inputs.finest_covering(..., cover_fraction
  =0.9)`, which resolves DESIGN §4.2's rule per capture INCLUDING its
  largest-coverage fallback ("when no level reaches it, the level with
  the largest non-zero coverage is taken — a tile never has zero lanes
  while any level sees it").  The fallback lived HERE at W1b; W1d moved
  it into `inputs.py` so the census and the reader agree by
  construction, leaving :func:`lanes_for_tile` a typed pass-through and
  :func:`fallback_captures` a caller of the STRICT rule.
* **sampling uses each PLACEMENT's own pitch**, never the lane median:
  `Lane.pitch_px_native` is a median over the lane's placements and they
  spread ±0.6%.  Every crop and every read here divides
  `placement.pitch_px` by the lane's `frame` (DESIGN §4.2's level-pitch
  rule).  The lane median survives only as the crop's aperture, where one
  filter serves the whole footprint.
* **ownership is frozen ONCE per (lane, footprint)** so `n_observed` is
  identical across arms.  The order mirrors production's own owner key
  (`tiles.color_candidates`: held-out loss, then window extent, then
  region index, first wins) — `Placement.quality` IS that held-out log
  loss and LOWER WINS (`data.placement_ordinal` ranks by `-quality` and
  `store._adopts` takes the greater).

WHY THE CROP PRIMITIVES COME FROM `color_region_anchor`.  PLAN's
`calibrate.channel_crops` / `calibrate.sample_channels` DO NOT EXIST; the
per-channel path the production colour lane actually uses is
`anchor.native_crop` -> `anchor.filtered_rgb` -> `anchor.sample_rgb`
(`color_region.py:403-418`, `fields.py:174-181`, `swim.py:382-385`).
`calibrate.window_crop` fuses the three planes to one luma column and is
the K path.  This module calls the colour path.

REFUSALS ARE NEVER FILLS.  A read whose points leave the crop returns a
`Read` with `refusal` set and NaN values; `Crops.fill_rgb` (the crop
median, `calibrate.window_crop`'s convention) exists so that a fill can
be named, and is unreachable while the bounds check stands.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from holo3.lib import geometry as lib_geometry
from holo3.plugins import calibrate
from holo3.plugins import color_region_anchor as anchor

from .inputs import finest_covering
from .types import (Crops, Lane, LaneFootprint, Read, RunInputs,
                    TileFootprint)

#: DESIGN §4.2's ruled cover fraction.
COVER_FRACTION = 0.9


class SampleError(RuntimeError):
    """The pixels cannot be produced as asked."""


# ----------------------------------------------------------------- lanes

def lanes_for_tile(inputs: RunInputs, page: int, ty: int, tx: int, *,
                   cover_fraction: float = COVER_FRACTION,
                   ) -> tuple[Lane, ...]:
    """The `finest-covering` lane set of one tile, WITH the fallback.

    Per capture: the finest level covering at least `cover_fraction` of
    the tile's 64x64 cells; failing that, the level with the largest
    NON-ZERO coverage.  A capture that sees nothing of the tile
    contributes nothing.
    """
    return tuple(inputs.lane(lane_id) for lane_id in finest_covering(
        inputs, page, ty, tx, cover_fraction=cover_fraction, fallback=True))


def fallback_captures(inputs: RunInputs, page: int, ty: int, tx: int, *,
                      cover_fraction: float = COVER_FRACTION,
                      ) -> tuple[str, ...]:
    """Captures whose lane for this tile came from the fallback rule."""
    covered = {capture_id for capture_id, _level in finest_covering(
        inputs, page, ty, tx, cover_fraction=cover_fraction,
        fallback=False)}
    return tuple(sorted(
        lane.capture_id for lane in lanes_for_tile(
            inputs, page, ty, tx, cover_fraction=cover_fraction)
        if lane.capture_id not in covered))


# ------------------------------------------------------------ ownership

def placement_pitch_px_level(lane: Lane, placement: Any) -> float:
    """DESIGN §4.2: the PLACEMENT's own pitch, in the lane's frame."""
    return float(placement.pitch_px) / float(lane.frame)


def placement_page_cells(placement: Any,
                         page_shape_cells_yx: tuple[int, int]) -> np.ndarray:
    extent = placement.window_id[3]
    shape = (int(extent[2]) - int(extent[0]),
             int(extent[3]) - int(extent[1]))
    return calibrate.window_page_cells(placement, shape, page_shape_cells_yx)


#: `(placements tuple, page shape) -> (P, 5) int64` of
#: ``(page, y0, x0, y1, x1)`` page-cell bounds, ``y1 < 0`` for a placement
#: that maps to nothing.  Keyed by `id()` of the tuple with a strong
#: reference kept alongside, so an id can never be reused under us.
_BOUNDS_CACHE: dict[int, tuple[Any, tuple[int, int], np.ndarray]] = {}


def _placement_bounds(lane: Lane, page_shape_cells_yx: tuple[int, int],
                      ) -> np.ndarray:
    """Page-cell bounding box of every placement of `lane`, computed once.

    `lane_footprint` is called once per (lane, tile) and a lane carries
    ~330 placements on sheet I, of which a 96x96 footprint touches a
    handful.  Mapping all of them through `window_page_cells` every time
    cost 0.34 s per (lane, tile) — 300x one read.  The bounds are a pure
    function of the placements and the page shape, so they are computed
    once and used only to SKIP; every surviving placement still goes
    through `placement_page_cells` exactly as before.
    """
    token = id(lane.placements)
    hit = _BOUNDS_CACHE.get(token)
    if (hit is not None and hit[0] is lane.placements
            and hit[1] == tuple(page_shape_cells_yx)):
        return hit[2]
    bounds = np.full((len(lane.placements), 5), -1, np.int64)
    for index, placement in enumerate(lane.placements):
        cells = placement_page_cells(placement, page_shape_cells_yx)
        if not cells.shape[0]:
            continue
        bounds[index] = (int(placement.page),
                         int(cells[:, 0].min()), int(cells[:, 1].min()),
                         int(cells[:, 0].max()), int(cells[:, 1].max()))
    bounds.setflags(write=False)
    _BOUNDS_CACHE[token] = (lane.placements, tuple(page_shape_cells_yx),
                            bounds)
    return bounds


def _owner_order_key(index: int, placement: Any) -> tuple:
    """Production's owner key (`tiles.color_candidates`), first wins.

    `quality` is a held-out log loss — LOWER WINS.  The remaining terms
    only make the order total and reproducible.
    """
    return (float(placement.quality), tuple(placement.window_id[3]),
            int(placement.region_index), int(placement.patch_ordinal),
            str(placement.capture_id), int(placement.level_index), index)


def _level_terms(lane: Lane, placement: Any) -> tuple[float, ...]:
    """The PAGE-cell -> LEVEL-pixel affine of one placement.

    `native_affine` already carries `rot_k` (it maps a PAGE cell, +0.5, to
    a NATIVE pixel); `compose_from_native` rescales it to the level.

    The POINTS this yields are identical to production's colour lane for
    every `rot_k`: `color_region.region_window` builds a LOCAL-cell affine
    as ``level_terms · (rotation · local + translation + page_origin +
    0.5)``, and ``rotated_points`` makes the bracket the page cell, so the
    two compositions agree cell for cell (verified against
    `region_window`, holo3/plugins/color_region.py:580-615).

    Its LINEAR PART does not.  `anchor.pose_linear` of these terms is a
    PAGE-cell 2x2; production's is ``level_terms[:, :2] @ rotation``, a
    WINDOW-LOCAL 2x2.  Every production dot delta — `PlaneField.
    delta_dots_xy`, `plane_k.choose_offset`, `swim` — is therefore in the
    LOCAL frame, and `read_rgb` moves points in the PAGE frame.  They
    agree only at ``rot_k == 0``, and sheet I is NOT all rot_k 0:
    MEASURED 2026-09-03 on the resume-3 run, 579 of 3,687 accepted
    placements have ``rot_k == 2``, where the two frames differ by a sign
    on both axes.  A caller handing a production-derived delta to
    `read_rgb` must rotate it first; W1d owes that conversion (or a
    ruling that the analyzer's arms search the page frame throughout).
    """
    return tuple(lib_geometry.compose_from_native(
        tuple(placement.native_affine), lane.frame))


def lane_footprint(lane: Lane, fp: TileFootprint, *,
                   reference_arm_owner: LaneFootprint | None = None,
                   ) -> LaneFootprint | None:
    """Which of the lane's placements owns each footprint cell, and where.

    Returns None when no accepted placement of this lane touches the
    footprint.  `owner_index` indexes `lane.placements` (-1 = unobserved);
    `points_yx` is in LEVEL pixels and NaN where unobserved.

    `reference_arm_owner` re-uses an ownership already frozen for this
    (lane, footprint) — DESIGN §4.3 wants it frozen once from the
    reference arm so `n_observed` is identical across arms.  The order is
    deterministic, so this is a consistency device, and a mismatch of
    lane or footprint is an error rather than a silent re-freeze.
    """
    cells = fp.page_cells_yx
    n = cells.shape[0]
    width = int(fp.page_shape_cells_yx[1])
    if width <= 0:
        raise SampleError(
            "the footprint carries no page shape; build it with "
            "frame.tile_footprint")
    keys = cells[:, 0] * np.int64(width) + cells[:, 1]

    bounds = _placement_bounds(lane, fp.page_shape_cells_yx)
    fp_y0, fp_x0 = int(cells[:, 0].min()), int(cells[:, 1].min())
    fp_y1, fp_x1 = int(cells[:, 0].max()), int(cells[:, 1].max())

    candidates: list[tuple[tuple, int, np.ndarray]] = []
    for index, placement in enumerate(lane.placements):
        if int(placement.page) != int(fp.page):
            continue
        box = bounds[index]
        if (int(box[3]) < 0 or int(box[0]) != int(fp.page)
                or int(box[3]) < fp_y0 or int(box[1]) > fp_y1
                or int(box[4]) < fp_x0 or int(box[2]) > fp_x1):
            continue                    # cannot touch the footprint
        page_cells = placement_page_cells(placement, fp.page_shape_cells_yx)
        if not page_cells.shape[0]:
            continue
        their = (np.asarray(page_cells[:, 0], np.int64) * np.int64(width)
                 + np.asarray(page_cells[:, 1], np.int64))
        position = np.searchsorted(keys, their)
        position = np.clip(position, 0, n - 1)
        hit = keys[position] == their
        if not np.any(hit):
            continue
        candidates.append((_owner_order_key(index, placement), index,
                           np.unique(position[hit])))
    if not candidates:
        return None

    owner = np.full(n, -1, np.int32)
    for _key, index, rows in sorted(candidates, key=lambda item: item[0]):
        free = rows[owner[rows] < 0]
        owner[free] = index
    observed = owner >= 0

    if reference_arm_owner is not None:
        if (reference_arm_owner.lane != lane.lane_id
                or reference_arm_owner.tile is not fp):
            raise SampleError(
                "reference_arm_owner belongs to another (lane, footprint)")
        owner = np.asarray(reference_arm_owner.owner_index, np.int32)
        observed = np.asarray(reference_arm_owner.observed, np.bool_)

    points = np.full((n, 2), np.nan, np.float64)
    for index in np.unique(owner[observed]).tolist():
        rows = np.flatnonzero(owner == index)
        points[rows] = calibrate.scan_points_yx(
            lane.placements[int(index)].native_affine, lane.frame,
            cells[rows])
    for array in (owner, observed, points):
        array.setflags(write=False)
    return LaneFootprint(lane=lane.lane_id, tile=fp, observed=observed,
                         owner_index=owner, points_yx=points)


# ---------------------------------------------------------------- crops

def _crop_pitch_px(lane: Lane, lfp: LaneFootprint) -> float:
    """The aperture pitch of the crop: the median over its OWNERS.

    Every READ uses its own placement's pitch; the uniform filter is one
    array over the whole crop, so its aperture takes the median of the
    pitches actually in play (the spread is ±0.6%, well under a pixel of
    aperture).
    """
    owners = np.unique(lfp.owner_index[lfp.observed]).tolist()
    if not owners:
        return float(lane.pitch_px_level)
    return float(np.median([placement_pitch_px_level(
        lane, lane.placements[int(index)]) for index in owners]))


def open_crops(lane: Lane, lfp: LaneFootprint, *, bound_dots: float,
               cell_dots: int) -> Crops:
    """The three channels of one (lane, footprint), opened ONCE.

    `bound_dots` is the registration bound the arms may move within; the
    crop grows by ``ceil(bound_dots / cell_dots * pitch_px_level)`` px
    (DESIGN §4.4) PLUS `anchor.points_halo` — the aperture and the
    bilinear kernel both need margin, so a crop sized to the bound alone
    would refuse a read exactly at the bound.

    `cell_dots` is `color_sites.cell_dots_of(row)`; §4.4's own halo
    formula needs it, and `read_rgb` converts offsets with it.
    """
    if lfp.lane != lane.lane_id:
        raise SampleError(f"lane {lane.lane_id} != footprint {lfp.lane}")
    points = np.asarray(lfp.points_yx, np.float64)[lfp.observed]
    if not points.shape[0]:
        raise SampleError("the lane footprint observes no cell")
    pitch = _crop_pitch_px(lane, lfp)
    bound_px = math.ceil(float(bound_dots) / float(cell_dots) * pitch)
    halo = int(bound_px) + int(anchor.points_halo(pitch))
    y0, x0, raw = anchor.native_crop(lane.rasters, points, halo)
    if raw.size == 0:
        raise SampleError(
            f"crop of {lfp.lane} at tile ({lfp.tile.ty}, {lfp.tile.tx}) "
            f"is empty — the points fall outside the raster")
    divisor = anchor.native_divisor((float(np.max(raw)),))
    filtered = anchor.filtered_rgb(raw, pitch, divisor)
    fill = tuple(float(np.median(raw[..., channel])) / divisor
                 for channel in range(3))
    return Crops(lane=lane, footprint=lfp.tile, y0=int(y0), x0=int(x0),
                 filtered_rgb=filtered, fill_rgb=fill,
                 pitch_px_level=pitch, cell_dots=int(cell_dots),
                 bound_dots=float(bound_dots), halo_px=int(halo),
                 divisor=float(divisor))


# ---------------------------------------------------------------- reads

def _terms_for(crops: Crops, index: int,
               affine_override: Any) -> tuple[float, ...]:
    lane = crops.lane
    if affine_override is None:
        return _level_terms(lane, lane.placements[index])
    if isinstance(affine_override, Mapping):
        terms = affine_override.get(index)
        if terms is None:
            return _level_terms(lane, lane.placements[index])
        return tuple(float(value) for value in terms)
    return tuple(float(value) for value in affine_override)


def read_rgb(crops: Crops, lfp: LaneFootprint, *,
             offset_dots_xy: tuple[float, float] = (0.0, 0.0),
             affine_override: Any = None, arm: str = "read") -> Read:
    """Sample the three channels at the footprint's cells.

    `offset_dots_xy` is a registration delta in PRINTED DOTS, (x, y).  It
    is converted the one legal way (PLAN §1.3): divide by `cell_dots` to
    reach cells and push the points through
    `anchor.shifted_points(points, anchor.pose_linear(affine), delta)`,
    where `affine` is the owner placement's PAGE-cell -> level-pixel
    terms.  `affine_override` replaces that affine for the read: a
    6-term sequence for every cell, or a mapping owner index -> 6 terms.

    A point outside the crop REFUSES the read (`Read.refusal` set, values
    NaN).  Never a silent fill.
    """
    if lfp.lane != crops.lane.lane_id:
        raise SampleError(f"crops are {crops.lane.lane_id}, footprint "
                          f"is {lfp.lane}")
    cells = lfp.tile.page_cells_yx
    n = cells.shape[0]
    values = np.full((n, 3), np.nan, np.float64)
    delta_cells = np.asarray(
        ((float(offset_dots_xy[0]) / float(crops.cell_dots),
          float(offset_dots_xy[1]) / float(crops.cell_dots)),), np.float64)
    moved = np.full((n, 2), np.nan, np.float64)
    terms_seen: tuple[float, ...] | None = None
    owners = np.unique(lfp.owner_index[lfp.observed]).tolist()
    if not owners:
        return Read(lane=lfp.lane, arm=arm, values_rgb=values,
                    offset_dots_xy=(float(offset_dots_xy[0]),
                                    float(offset_dots_xy[1])),
                    affine_terms=None, scope="footprint",
                    refusal="no_observed_cell")
    for index in owners:
        rows = np.flatnonzero(lfp.owner_index == index)
        terms = _terms_for(crops, int(index), affine_override)
        terms_seen = terms if terms_seen is None else terms_seen
        if affine_override is None:
            points = np.asarray(lfp.points_yx, np.float64)[rows]
        else:
            points = calibrate.scan_points_yx(terms, 1, cells[rows])
        if delta_cells.any():
            points = anchor.shifted_points(
                points, anchor.pose_linear(terms), delta_cells)
        moved[rows] = points

    local = moved[lfp.observed] - np.asarray(
        (crops.y0, crops.x0), np.float64)
    height, width = crops.shape_yx
    outside = int(np.count_nonzero(
        (local[:, 0] < 0.0) | (local[:, 1] < 0.0)
        | (local[:, 0] > height - 1) | (local[:, 1] > width - 1)))
    if outside:
        return Read(lane=lfp.lane, arm=arm, values_rgb=values,
                    offset_dots_xy=(float(offset_dots_xy[0]),
                                    float(offset_dots_xy[1])),
                    affine_terms=terms_seen, scope="footprint",
                    refusal=f"outside_crop:{outside}")
    values[lfp.observed] = anchor.sample_rgb(
        crops.filtered_rgb, crops.y0, crops.x0, moved[lfp.observed])
    values.setflags(write=False)
    return Read(lane=lfp.lane, arm=arm, values_rgb=values,
                offset_dots_xy=(float(offset_dots_xy[0]),
                                float(offset_dots_xy[1])),
                affine_terms=terms_seen, scope="footprint", refusal=None)


def lane_level_pitches(lane: Lane,
                       lfp: LaneFootprint) -> dict[int, float]:
    """Per-owner level pitch — the column DESIGN §4.2 wants recorded."""
    owners: Sequence[int] = np.unique(
        lfp.owner_index[lfp.observed]).tolist()
    return {int(index): placement_pitch_px_level(
        lane, lane.placements[int(index)]) for index in owners}

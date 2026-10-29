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
  `store_folds._adopts` takes the greater).

WHY THE CROP PRIMITIVES COME FROM `color_region_anchor`.  PLAN's
`calibrate.channel_crops` / `calibrate.sample_channels` DO NOT EXIST; the
per-channel path the production colour lane actually uses is
`anchor.native_crop` -> `anchor.filtered_rgb` -> `anchor.sample_rgb`
(`color_region.py:422-440`, `fields.py:173-180`, `swim.py:241`).
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
from scipy import ndimage

from holo.receiver.lib import geometry as lib_geometry, page_map
from holo.receiver.plugins import calibrate
from holo.receiver.plugins import color_region_anchor as anchor

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
    `region_window`, src/holo/receiver/plugins/color_region.py:602-637).

    Its LINEAR PART is the same matrix production moves by:
    `anchor.pose_linear` of these terms is the PAGE-cell 2x2, and
    production's `RegionWindow.page_linear` IS ``level_terms[:, :2]``
    (`color_region.py:677`), byte for byte this function's linear part.
    What is WINDOW-LOCAL is ``pose_linear(window.affine)`` =
    ``level_terms[:, :2] @ rotation``, and no published delta is spoken
    in it: `PlaneField.delta_dots_xy` and `plane_k.choose_offset`'s sweep
    both reach the raster through `lib/page_map`, whose `raster_points`
    multiplies a PAGE-axis delta in printed dots by that page-axis
    matrix and composes no rotation at all — which is why one dot along
    page +x moves the sampler one dot along page +x at every rot_k
    (design I2).  `read_rgb` moves points the same way through the same
    function.  What is genuinely window-local is the swim's local affine
    and `refine.color`'s candidate poses, and `page_map.local_axes` /
    `page_axes` are the conversion for those.  The delta this module
    once had to rotate was the retired PER-LANE field
    (`arms.to_page_frame`, kept as algebra and applied to no production
    field).
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


#: The aperture kinds :func:`_filtered_rgb` knows (W8 B3, A7).
APERTURE_KINDS: tuple[str, ...] = ("box", "gaussian")
#: A gaussian truncates at 4 sigma; with sigma = FWHM / 2.355 that is
#: 1.7 FWHM, so a gaussian aperture of the same width needs 1.7x the
#: crop margin a box of that width needs.
GAUSSIAN_HALO_FACTOR: float = 1.7


def aperture_halo_px(pitch_px: float, aperture_cells: float,
                     aperture_kind: str) -> int:
    """The crop margin one aperture needs, in level pixels.

    `anchor.points_halo` is the box at `anchor.APERTURE_CELLS`
    (``ceil(0.7 * pitch) + 2``); this is that formula as a function of
    BOTH the width and the kind, and it returns exactly
    `anchor.points_halo(pitch)` at the defaults.
    """
    if aperture_kind not in APERTURE_KINDS:
        raise SampleError(f"aperture kind {aperture_kind!r} is not one of "
                          f"{APERTURE_KINDS}")
    reach = float(aperture_cells) * float(pitch_px)
    if aperture_kind == "gaussian":
        reach *= GAUSSIAN_HALO_FACTOR
    return int(math.ceil(reach)) + 2


def _filtered_rgb(raw: np.ndarray, pitch_px: float, divisor: float,
                  aperture_cells: float, aperture_kind: str) -> np.ndarray:
    """`anchor.filtered_rgb` with the aperture as a parameter (A7).

    `box` IS `anchor.filtered_rgb`'s uniform filter (``size =
    round(aperture_cells * pitch)``, ``mode="nearest"``); `gaussian` is
    the same width read as an FWHM, ``sigma = aperture_cells * pitch /
    2.355``.  The defaults never reach here — `open_crops` calls
    `anchor.filtered_rgb` itself so the production path stays the
    production path, byte for byte.
    """
    if aperture_kind not in APERTURE_KINDS:
        raise SampleError(f"aperture kind {aperture_kind!r} is not one of "
                          f"{APERTURE_KINDS}")
    filtered = np.empty(raw.shape, np.float32)
    for channel in range(3):
        if aperture_kind == "box":
            size = max(1, int(round(float(aperture_cells) * float(pitch_px))))
            ndimage.uniform_filter(raw[..., channel], size=size,
                                   output=filtered[..., channel],
                                   mode="nearest")
        else:
            sigma = float(aperture_cells) * float(pitch_px) / 2.355
            ndimage.gaussian_filter(raw[..., channel].astype(np.float32),
                                    sigma=sigma,
                                    output=filtered[..., channel],
                                    mode="nearest")
    if divisor != 1.0:
        filtered /= np.float32(divisor)
    return filtered


def crop_memo_key(lfp: LaneFootprint, *, bound_dots: float, cell_dots: int,
                  keep_raw: bool, aperture_cells: float,
                  aperture_kind: str) -> tuple:
    """Everything :func:`open_crops` reads to decide the cut.

    The cut is a pure function of the lane, the lane footprint and the
    five cut arguments; the lane footprint is in turn a pure function of
    the lane and the TILE footprint, and the tile footprint of the format
    row, the geometry and ``(page, ty, tx, halo_cells)`` — so those four
    plus the page shape name the footprint, and the lane id names the
    lane.  That leaves the row and the geometry, which no key can carry
    (they are arrays) and no key has to: the memo this keys lives inside
    ONE lane of ONE `fixedpoint.blind_key` call, where one run's row and
    geometry stand still.  A caller that wants a longer-lived memo owes
    the row and geometry in the key itself.
    """
    fp = lfp.tile
    return (lfp.lane, int(fp.page), int(fp.ty), int(fp.tx),
            int(fp.halo_cells), tuple(int(value)
                                      for value in fp.page_shape_cells_yx),
            float(bound_dots), int(cell_dots), bool(keep_raw),
            float(aperture_cells), str(aperture_kind))


class LaneCropMemo:
    """ONE lane's crops at a time — the memo `fixedpoint.blind_key` holds.

    A key's arms run lane by lane, and the crops of the lane before are
    dead the moment that loop moves on, so :meth:`for_lane` drops them.
    That is what keeps the saving free of memory: a worker holds the two
    cuts of ONE lane where it used to hold the one cut of one arm — not
    two cuts per lane of the KEY, which on a ten-capture key would be
    twenty crops (18-31 MB the pair at the sizes the sheet-I corpus cuts
    at level 2, so 180-310 MB a worker and eight times that at `-n 8`).
    The saving is the same either way: the battery's arms for one lane
    are consecutive, and it is across THEM that a cut repeats.
    """

    def __init__(self) -> None:
        self._lane: Any = None
        self._crops: dict[tuple, Crops] = {}

    def for_lane(self, lane_id: Any) -> dict[tuple, Crops]:
        """The memo to hand `open_crops` for this lane, and only this one."""
        if lane_id != self._lane:
            self._crops = {}
            self._lane = lane_id
        return self._crops


def open_crops(lane: Lane, lfp: LaneFootprint, *, bound_dots: float,
               cell_dots: int, keep_raw: bool = False,
               aperture_cells: float = anchor.APERTURE_CELLS,
               aperture_kind: str = "box",
               memo: dict[tuple, Crops] | None = None) -> Crops:
    """The three channels of one (lane, footprint), opened ONCE.

    `bound_dots` is the registration bound the arms may move within; the
    crop grows by ``ceil(bound_dots / cell_dots * pitch_px_level)`` px
    (DESIGN §4.4) PLUS `anchor.points_halo` — the aperture and the
    bilinear kernel both need margin, so a crop sized to the bound alone
    would refuse a read exactly at the bound.  EVERY delta the arm will
    apply belongs in it, the standing field among them
    (`arms.field_reach_dots`, F3 2026-09-13): the aperture margin is not
    a second bound to spend, and a read that eats it comes back
    edge-replicated before it comes back refused.

    `cell_dots` is `color_sites.cell_dots_of(row)`; §4.4's own halo
    formula needs it, and `read_rgb` converts offsets with it.

    `keep_raw` (W8, ruling 13) keeps the unfiltered uint8 crop on the
    `Crops` for the patch family, which resamples the raw pixels at the
    read's pose; every existing arm leaves it off and reads exactly what
    it read before (`filtered_rgb` is computed the same way either way).

    `aperture_cells`/`aperture_kind` (W8 B3, A7) are the sampling
    aperture.  At the defaults this function calls `anchor.filtered_rgb`
    and `anchor.points_halo` — the production path, byte for byte; any
    other width or kind goes through :func:`_filtered_rgb` and grows the
    crop by :func:`aperture_halo_px`, because a wider aperture (and a
    gaussian's 4-sigma tail) needs more margin than the box the crop was
    sized for.

    `memo` (2026-09-13) is a caller-owned dict keyed by
    :func:`crop_memo_key` — :class:`LaneCropMemo` is the one the driver
    holds: a hit returns the SAME `Crops` object rather than cutting a
    byte-identical second one.  It exists because the knobs an arm cuts
    by are per LANE, not per arm — a battery resolves to TWO cuts where
    no field stands, the box arms' and the patch/pure arms' wider
    keep-raw one, and ONE MORE for each distinct reach a field adds
    (`arms.field_reach_dots`: a `field` arm's standing delta, a `field2`
    arm's clamp).  That widening is the CALLER's: `evidence_for` adds
    the reach to `bound_dots` before it builds the key, and this
    function cuts to the bound it is handed and enforces nothing.  Each
    cut is a fresh contiguous copy of the memmap slice plus a float32
    filter of it: 18-40 ms and 8-17 MB per cut on the sheet-I corpus at
    level 2, so the thirteen arms of `DEFAULT_ARMS` + the patch pair cut
    thirteen crops for two distinct ones and the memo takes that (key,
    lane) from 1.70 s to 1.45 s (measured 2026-09-13, no field
    standing).  The object
    handed back is READ-ONLY BY CONVENTION: no reader of `filtered_rgb`
    or `raw_rgb` writes through them (`patchgrid.extract` takes its own
    float copy, `sample_rgb` and `_filtered_rgb` only read), and a reader
    that ever needs to must copy on its own account.  `memo=None` is
    every other caller, unchanged.
    """
    if lfp.lane != lane.lane_id:
        raise SampleError(f"lane {lane.lane_id} != footprint {lfp.lane}")
    token = None if memo is None else crop_memo_key(
        lfp, bound_dots=bound_dots, cell_dots=cell_dots, keep_raw=keep_raw,
        aperture_cells=aperture_cells, aperture_kind=aperture_kind)
    if token is not None:
        held = memo.get(token)
        if held is not None:
            return held
    points = np.asarray(lfp.points_yx, np.float64)[lfp.observed]
    if not points.shape[0]:
        raise SampleError("the lane footprint observes no cell")
    pitch = _crop_pitch_px(lane, lfp)
    default_aperture = (float(aperture_cells) == float(anchor.APERTURE_CELLS)
                        and str(aperture_kind) == "box")
    bound_px = math.ceil(float(bound_dots) / float(cell_dots) * pitch)
    halo = int(bound_px) + (int(anchor.points_halo(pitch)) if default_aperture
                            else aperture_halo_px(pitch, aperture_cells,
                                                  aperture_kind))
    y0, x0, raw = anchor.native_crop(lane.rasters, points, halo)
    if raw.size == 0:
        raise SampleError(
            f"crop of {lfp.lane} at tile ({lfp.tile.ty}, {lfp.tile.tx}) "
            f"is empty — the points fall outside the raster")
    divisor = anchor.native_divisor((float(np.max(raw)),))
    filtered = (anchor.filtered_rgb(raw, pitch, divisor) if default_aperture
                else _filtered_rgb(raw, pitch, divisor, aperture_cells,
                                   aperture_kind))
    fill = tuple(float(np.median(raw[..., channel])) / divisor
                 for channel in range(3))
    crops = Crops(lane=lane, footprint=lfp.tile, y0=int(y0), x0=int(x0),
                  filtered_rgb=filtered, fill_rgb=fill,
                  pitch_px_level=pitch, cell_dots=int(cell_dots),
                  bound_dots=float(bound_dots), halo_px=int(halo),
                  divisor=float(divisor),
                  raw_rgb=raw if keep_raw else None,
                  aperture_cells=float(aperture_cells),
                  aperture_kind=str(aperture_kind))
    if token is not None:
        memo[token] = crops
    return crops


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
    is converted the one legal way (PLAN §1.3, design I7): through
    `page_map.raster_points`, the receiver's own mapping, with
    `anchor.pose_linear(affine)` as the linear part — `affine` being the
    owner placement's PAGE-cell -> level-pixel terms — and `cell_dots`
    as the scale, so dots become cells and cells become pixels exactly
    once and in one place.  `affine_override` replaces that affine for
    the read: a 6-term sequence for every cell, or a mapping owner index
    -> 6 terms.

    A point outside the crop REFUSES the read (`Read.refusal` set, values
    NaN).  Never a silent fill.
    """
    if lfp.lane != crops.lane.lane_id:
        raise SampleError(f"crops are {crops.lane.lane_id}, footprint "
                          f"is {lfp.lane}")
    cells = lfp.tile.page_cells_yx
    n = cells.shape[0]
    values = np.full((n, 3), np.nan, np.float64)
    delta_dots_xy = np.asarray(((float(offset_dots_xy[0]),
                                 float(offset_dots_xy[1])),), np.float64)
    moved = np.full((n, 2), np.nan, np.float64)
    terms_seen: tuple[float, ...] | None = None
    linear_by_owner: dict[int, np.ndarray] = {}
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
        linear = anchor.pose_linear(terms)
        linear.setflags(write=False)
        linear_by_owner[int(index)] = linear
        if affine_override is None:
            points = np.asarray(lfp.points_yx, np.float64)[rows]
        else:
            points = calibrate.scan_points_yx(terms, 1, cells[rows])
        if delta_dots_xy.any():
            points = page_map.raster_points(points, linear, delta_dots_xy,
                                            crops.cell_dots)
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
    moved.setflags(write=False)
    return Read(lane=lfp.lane, arm=arm, values_rgb=values,
                offset_dots_xy=(float(offset_dots_xy[0]),
                                float(offset_dots_xy[1])),
                affine_terms=terms_seen, scope="footprint", refusal=None,
                points_yx=moved, linear_by_owner=linear_by_owner)


def read_headroom_px(crops: Crops, lfp: LaneFootprint,
                     read: Read) -> float | None:
    """How far the worst point of a read sat from the crop's edge, in px.

    :func:`read_rgb`'s own comparison as a NUMBER rather than a verdict:
    the smallest margin any observed point had against the four crop
    edges, so a pass can say how close to `outside_crop` it came
    (F3, review 2026-09-13).  `None` when the read carries no posed
    points — a refused read has none, and the refusal is the number.
    """
    if read.points_yx is None:
        return None
    observed = np.asarray(lfp.observed, bool)
    points = np.asarray(read.points_yx, np.float64)[observed]
    if not points.shape[0]:
        return None
    local = points - np.asarray((crops.y0, crops.x0), np.float64)
    height, width = crops.shape_yx
    return float(min(local[:, 0].min(), local[:, 1].min(),
                     float(height - 1) - local[:, 0].max(),
                     float(width - 1) - local[:, 1].max()))


def refiltered_values(crops: Crops, lfp: LaneFootprint, read: Read, *,
                      aperture_cells: float,
                      aperture_kind: str = "box") -> np.ndarray:
    """Re-read a crop the arm already opened, through another aperture.

    W8 B7 (A7, self-discovered).  Each aperture candidate of
    `autoknobs.choose_aperture` has to be evaluated on ITS OWN filtered
    crop, and a crop is expensive: this re-filters the RAW pixels the
    crop kept (`open_crops(keep_raw=True)`) and re-samples them at the
    READ's own posed points, so nothing but the aperture moves.  Returns
    `(n, 3)` with NaN where the lane observes nothing — the shape and the
    convention of `Read.values_rgb`.

    At the crop's own aperture it returns `read.values_rgb` unchanged
    (the same filter over the same pixels at the same points), and a test
    pins that identity.  The crop's margin was sized for the aperture it
    was opened at, so a WIDER candidate borrows the edge
    (`mode="nearest"`, exactly what the production filter does at the
    crop boundary) rather than reaching for pixels never read.
    """
    if crops.raw_rgb is None:
        raise SampleError("refiltered_values needs crops opened with "
                          "keep_raw=True")
    if read.points_yx is None:
        raise SampleError("refiltered_values needs a read that carries its "
                          "posed points")
    if lfp.lane != crops.lane.lane_id:
        raise SampleError(f"crops are {crops.lane.lane_id}, footprint "
                          f"is {lfp.lane}")
    if (float(aperture_cells) == float(crops.aperture_cells)
            and str(aperture_kind) == str(crops.aperture_kind)):
        return np.asarray(read.values_rgb, np.float64)
    filtered = _filtered_rgb(crops.raw_rgb, float(crops.pitch_px_level),
                             float(crops.divisor), float(aperture_cells),
                             str(aperture_kind))
    observed = np.asarray(lfp.observed, bool)
    points = np.asarray(read.points_yx, np.float64)[observed]
    values = np.full((int(observed.size), 3), np.nan, np.float64)
    values[observed] = anchor.sample_rgb(filtered, crops.y0, crops.x0,
                                         points)
    values.setflags(write=False)
    return values


def lane_level_pitches(lane: Lane,
                       lfp: LaneFootprint) -> dict[int, float]:
    """Per-owner level pitch — the column DESIGN §4.2 wants recorded."""
    owners: Sequence[int] = np.unique(
        lfp.owner_index[lfp.observed]).tolist()
    return {int(index): placement_pitch_px_level(
        lane, lane.placements[int(index)]) for index in owners}

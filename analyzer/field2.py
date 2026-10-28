"""The page field, correctly done — DESIGN §13's `field2` lead.

RULING (Germano, 2026-09-03).  Page-scope CONTEXT and page-scope POSE
fight the physics, because toner interaction and pose are LOCAL.  A
per-plane page FIELD does not: registration is a smooth function of
position with small local deviations, which is exactly what a surface
plus a short-bandwidth residual represents.  This module measures that
surface from the page's own blind evidence and publishes it.

BLIND.  Nothing here may import :mod:`analyzer.truth` or
:mod:`analyzer.oracle`; the fit sees labels (word, dust, certified
cargo of NEIGHBOURS) and nothing else.  Truth appears only in the
oracle columns a caller reads back afterwards.

WHAT IS MEASURED, PER TILE.  The `offset` arm's own blind 2-D search
(`arms._search_offset`, the same function, not a copy of it) on the
plane's own labels, at every covered tile of the page — certified tiles
included, because they carry the most labels and are therefore the best
anchors.  A tile hands back its winning offset, its label count, the
held-out loss gain over the committed pose, and the CURVATURE of the
search profile.

WHY CURVATURE IS THE WEIGHT AND GAIN IS NOT.  The gain over committed is
zero in two very different cases: the pose is already right (an
informative zero, which the field must keep), and the objective is flat
so the winner is noise (uninformative).  The mean-minus-best of the
search profile separates them — a sharp objective has curvature whether
or not its optimum sits at zero.  So the weight is
``n_labels x clip(curvature / CURVATURE_SCALE_NATS, 0, 1)`` and the gain
is REPORTED, per DESIGN §13's ask, rather than trusted.

THE FIT.  A weighted 2-D polynomial of degree <= 3 in page coordinates
(the global tilt and bow; it cannot represent the AltaLink's ~100 mm
yellow sinusoid across a 297 mm page and is not asked to) PLUS a
support-normalised kernel-smoothed residual over the same weights
(``num = smooth(w.r)``, ``den = smooth(w)``, evaluated where ``den >
0``) — `plane_field.smooth` is zero-padded, so smoothing a sparse band
without the normalisation would pull its edge toward zero, the failure
DESIGN §4.6 names for `smooth_offsets`.  The bandwidth is production's
own (2 tiles, ~11 mm), which resolves a 100 mm period comfortably.  The
sum is clamped at production's bound (`plane_field.MAX_DELTA_DOTS`).

POOLED, FROM FURNITURE (RULING, Germano, 2026-09-03 late).  The field is
a property of the PRINTED PAGE, not of a capture or a rung: three
captures of sheet H agreed on it to 0.065 dots.  So the fit that the
arms read is ONE fit per (page, plane), POOLED over every lane of the
page, with the labels taken from FURNITURE ONLY — `known_frame` called
with an EMPTY certificate mapping, so word and dust are the only labels
and no certificate enters anywhere (the mixing fit included).  Two
consequences, and they are the point:

* it is INVARIANT ACROSS CASCADE GENERATIONS — the certificate set moves
  under every generation and the fit does not, so it is computed once
  per process instead of once per lane per generation; and
* it is BLIND BY CONSTRUCTION — no certificate reaches it, so there is
  no withholding hazard to reason about and the DECLARED DEVIATION the
  per-lane fit carried (its one lane-scope mixing fit excluded no tile)
  simply does not arise.

`fit_pooled_page_field` is that fit; `fit_page_field` remains the
per-lane, certificate-anchored one, which the `field2c` arms read.

HONEST UNITS AND PRODUCTION'S FLOOR.  Deltas are printed DOTS in the
PAGE frame (DESIGN §4.4) — the analyzer's own offsets are already page
frame, since `sample.read_rgb` shifts through `level_terms[:, :2]`
without the placement's rotation.  `holo3.plugins.fields` REFUSES to
publish a plane whose median delta is under 0.25 dots (`MIN_DELTA_DOTS`)
because production ADOPTS a published field blindly — the standing fit
speaks first and `plane_k.choose_offset` does not even search.  This
instrument publishes anyway, and records `production_publishable` and
production's own refusal string beside the number: here the field is a
PRIOR for a search that is still scored on held-out labels, not an
adopted pose, so a 0.15-dot field that is real costs nothing when it is
wrong and buys a better search centre when it is right.  The distinction
is what the arm does with it, not what the number is.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import (dataclass, field as dataclass_field,
                         replace as dataclass_replace)
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from holo3.lib import plane_field as plane_field_lib
from holo3.plugins import color_sites, fields as fields_plugin

from . import arms as arms_mod
from . import calibrate as cal
from . import frame as frame_mod
from . import sample as sample_mod
from .types import Key, Lane, PLANE_OF, RunInputs

TILE_CELLS = 64

#: The search-profile curvature (mean loss over the grid minus the best
#: loss, in nats per held-out label) at which a tile's blind offset is
#: given its FULL label weight.  Below it the weight falls off linearly,
#: so a flat objective — a dead band with no discriminating labels — is
#: filled in by its neighbours instead of voting noise into the surface.
#: 0.02 nats is a modest but real separation between the best and a
#: typical grid point; it is a weight scale, not a gate, and no tile is
#: ever dropped by it.
CURVATURE_SCALE_NATS: float = 0.02

#: Degree ladder for the surface: the highest degree with at least
#: `MIN_TILES_PER_TERM` weighted tiles per free coefficient wins.  A
#: cubic in two variables has 10 terms.
MAX_DEGREE: int = 3
MIN_TILES_PER_TERM: float = 8.0

#: Production's own bandwidth and clamp, called not re-chosen.
BANDWIDTH_TILES: float = plane_field_lib.BANDWIDTH_TILES
MAX_DELTA_DOTS: float = plane_field_lib.MAX_DELTA_DOTS

#: How many tiles the LAZY fit inside `arms.evidence_for` samples when a
#: caller asks for a `field2` arm without handing a field in.  The
#: function's own default is every covered tile (DESIGN §13's ask); a
#: battery run that fitted every tile of every lane before reading one
#: target would pay the whole page many times over, so the arm's default
#: is a deterministic subsample and the driver may raise it.
FIT_TILES_DEFAULT: int = 300

#: At most this many fits are memoised at once (each is a few hundred kB
#: of per-tile records plus two tile grids, so this cap is ~10 MB).
#:
#: SIZE IT BY THE LANE COUNT, not by taste.  A fit is keyed per (lane,
#: stream) and `fixedpoint.blind_key` walks EVERY lane that covers a tile
#: for every target, so one generation's working set is
#: `n_lanes x n_streams` — 48 on sheet H (16 lanes x 3), and the eviction
#: below is a queue, not an LRU.  A cap under the working set therefore
#: does not merely lose a little cache: it evicts the entry the next
#: target asks for, and every miss is a WHOLE PAGE FIT (tens of seconds).
#: 96 covers 32 lanes.
MEMO_MAX: int = 96

#: How many tiles the LAZY POOLED fit samples.  Its cost is
#: ``n_lanes x tiles x seconds-per-tile`` and it is paid ONCE per (page,
#: stream) per process — not once per lane per generation, because no
#: certificate is in its memo key — so 150 tiles over sheet H's 22 lanes
#: is ~3,300 reads for a field every lane and every generation then
#: shares.  A driver that wants the full page passes `tiles=None`.
POOLED_FIT_TILES_DEFAULT: int = 150

#: The anchor sets.  `furniture` = word and dust only (certificate-free,
#: generation-invariant, what the `field2` arms read); `certified` = the
#: per-lane fit that also reads the neighbours' certified cargo (what the
#: `field2c` arms read).
ANCHORS_FURNITURE = "furniture"
ANCHORS_CERTIFIED = "certified"
ANCHOR_SETS: tuple[str, ...] = (ANCHORS_FURNITURE, ANCHORS_CERTIFIED)

#: How lanes' per-tile offsets are combined at a tile.
#:
#: WEIGHTED MEDIAN IS THE DEFAULT, and the reason is outliers, not taste.
#: A per-tile winner is the argmin of a noisy objective on a 0.25-dot
#: grid; the record measured the winners scattering with sd 0.28-0.38
#: dots, and a search that latches onto the wrong minimum is off by a
#: whole grid step or more.  Pooling 22 lanes with a MEAN lets one such
#: lane drag the tile; the component-wise weighted median cannot be moved
#: by fewer than half the weight.  The median's own cost — it returns a
#: value ON the grid, so it cannot average the quantisation away — is
#: paid back by the surface and the kernel-smoothed residual, which do
#: that averaging SPATIALLY over the neighbourhood.  `wmean` is kept so
#: the choice stays a measurement (the record reports both).
POOL_WMEDIAN = "wmedian"
POOL_WMEAN = "wmean"
POOL_MODES: tuple[str, ...] = (POOL_WMEDIAN, POOL_WMEAN)

#: THE one empty certificate mapping every furniture-only fit uses.
#:
#: `frame._certs_token` keys on `id(certs)` and keeps only
#: `_MAX_CERT_SETS` mappings alive; handing it a FRESH ``{}`` per tile
#: would mint a token per tile and evict the driver's real certificate
#: memo on every eighth call.  One immutable module-level mapping takes
#: one slot for the life of the process, and its projections are all
#: None, so the slot costs nothing.
NO_CERTS: Mapping = MappingProxyType({})

__all__ = ["ANCHORS_CERTIFIED", "ANCHORS_FURNITURE", "ANCHOR_SETS",
           "BANDWIDTH_TILES", "CURVATURE_SCALE_NATS", "FIT_TILES_DEFAULT",
           "MAX_DEGREE", "NO_CERTS", "POOLED_FIT_TILES_DEFAULT",
           "POOL_MODES", "POOL_WMEAN", "POOL_WMEDIAN", "PageField",
           "TileOffset", "build_field", "column_profile", "covered_tiles",
           "field_for", "field_from_pooled", "fit_page_field",
           "fit_pooled_page_field", "lanes_for_page", "page_covered_tiles",
           "pool_tile", "pooled_records", "sample_tiles", "summary"]


@dataclass(frozen=True)
class TileOffset:
    """One tile's blind per-tile offset — the field's raw evidence."""

    ty: int
    tx: int
    offset_dots_xy: tuple[float, float]
    n_labels: int
    n_discriminating: int
    committed_logloss: float | None
    search_logloss: float | None
    #: Held-out loss GAIN over the committed pose (positive = the search
    #: helped).  Reported, never the weight — see the module docstring.
    gain: float | None
    #: Mean-minus-best of the search profile, in nats per held-out label.
    curvature: float
    weight: float
    refusal: str | None = None
    #: How many LANES this record pools.  1 for a lane's own read; the
    #: number of lanes that reached the tile for a pooled record.
    n_lanes: int = 1


@dataclass(frozen=True)
class PageField:
    """A per-plane page field in PAGE-frame printed dots.

    `delta_dots_xy` and `support` are (tiles_y, tiles_x, 2) and
    (tiles_y, tiles_x); `poly_dots_xy` is the surface alone, so a caller
    can see how much of the field is the low-order part and how much is
    the smoothed residual.

    SCOPE.  `lane` is the owning lane of a PER-LANE fit and is None for a
    POOLED one, which is page-scope by construction and therefore valid
    on every lane of its page; `lanes` is the pooled set (provenance,
    empty for a per-lane fit) and `n_lanes` counts, per tile, how many of
    them reached it.  The two are mutually exclusive by construction:
    there is no way to spell a field that claims one lane AND a pool.

    THE Y COMPONENT IS REPORTED, NOT MEASURED (FIELD2-2026-09-03 §3).
    On sheet H the two 2400 captures agree on the x component to 0.065
    dots and on y to 0.044, but the 4800 capture disagrees on y by 0.185
    — and no measurement in the record has ever claimed a y registration
    field.  Read `delta_dots_xy[..., 0]` as evidence and
    `delta_dots_xy[..., 1]` as a number the fit produced.
    """

    lane: tuple[str, int] | None
    stream_id: str
    page: int
    plane: int
    delta_dots_xy: np.ndarray
    support: np.ndarray
    poly_dots_xy: np.ndarray
    degree: int
    tiles: tuple[TileOffset, ...]
    median_delta_dots: float
    residual_rms_dots: float
    detail: Mapping[str, Any] = dataclass_field(default_factory=dict)
    #: The pooled lane set, empty for a per-lane fit.
    lanes: tuple[tuple[str, int], ...] = ()
    #: Which labels the per-tile offsets were searched on.
    anchors: str = ANCHORS_CERTIFIED
    #: (tiles_y, tiles_x) count of pooled lanes per tile; None per-lane.
    n_lanes: np.ndarray | None = None

    @property
    def pooled(self) -> bool:
        return self.lane is None

    @property
    def tiles_yx(self) -> tuple[int, int]:
        return (int(self.support.shape[0]), int(self.support.shape[1]))

    @property
    def production_publishable(self) -> bool:
        """Would `fields.publishable`'s median leg let this be adopted?

        The OTHER two legs (site count, residual) are production's own
        photometric bookkeeping and have no counterpart here, so only the
        one leg that talks about the field itself is quoted.
        """
        return self.median_delta_dots >= fields_plugin.MIN_DELTA_DOTS

    @property
    def production_refusal(self) -> str:
        if self.production_publishable:
            return ""
        return (f"median {self.median_delta_dots:.2f}d"
                f"<{fields_plugin.MIN_DELTA_DOTS:.2f}d")

    def delta_at_tile(self, ty: int, tx: int) -> np.ndarray:
        return np.asarray(self.delta_dots_xy[int(ty), int(tx)], np.float64)

    def support_at_tile(self, ty: int, tx: int) -> float:
        return float(self.support[int(ty), int(tx)])

    def evaluate(self, cells_yx: np.ndarray, *, require_support: bool = True,
                 ) -> np.ndarray | None:
        """Per-cell PAGE-frame delta at these page cells, or None.

        `plane_field.evaluate`, CALLED — the same bilinear lookup at tile
        centres production samples through, so the two fields are read
        the same way.  `require_support` mirrors
        `plane_k.field_delta_dots`'s rule (every tile under the cells must
        carry support); it is a knob rather than a law because the
        polynomial part is defined everywhere, and whether extrapolating
        it past the evidence is a good idea is a measurement, not an
        assumption.
        """
        cells = np.asarray(cells_yx, np.int64)
        if not cells.shape[0]:
            return np.zeros((0, 2), np.float64)
        if require_support:
            support = np.asarray(self.support, np.float64)
            codes = plane_field_lib.tile_codes(cells, support.shape,
                                               TILE_CELLS)
            if not np.all(support.ravel()[codes] > 0.0):
                return None
        return plane_field_lib.evaluate(np.asarray(self.delta_dots_xy),
                                       cells, TILE_CELLS)


# ------------------------------------------------------------ the tiles

def covered_tiles(inputs: RunInputs, lane: Lane, page: int,
                  ) -> tuple[tuple[int, int], ...]:
    """Every tile this lane sees any cell of, in row-major order."""
    from .inputs import lane_tile_coverage
    counts = lane_tile_coverage(inputs, lane.lane_id, int(page))
    return tuple((int(ty), int(tx))
                 for ty, tx in zip(*np.nonzero(counts > 0)))


def sample_tiles(candidates: Sequence[tuple[int, int]], n_tiles: int,
                 seed: int) -> tuple[tuple[int, int], ...]:
    """A deterministic n-tile subsample, `unmix._sample_tiles`'s draw.

    A hash of (seed, ty, tx) — never `hash`, never a clock (DESIGN §0).
    """
    tiles = [(int(ty), int(tx)) for ty, tx in candidates]
    if not tiles or int(n_tiles) >= len(tiles):
        return tuple(sorted(tiles))
    draw = cal.fold_hash(np.asarray(tiles, np.int64), int(seed))
    order = np.argsort(draw, kind="stable")[:int(n_tiles)]
    return tuple(sorted(tiles[int(index)] for index in order))


def lanes_for_page(inputs: RunInputs, page: int) -> tuple[Lane, ...]:
    """Every lane with an accepted placement on `page`, lane-id order.

    ALL levels of ALL captures — the pooled field's default set, per the
    ruling: a rung is a way of looking at the paper, not a different
    paper, so a level that sees the page has evidence about its field.
    """
    return tuple(sorted(
        (lane for lane in inputs.lanes
         if any(int(placement.page) == int(page)
                for placement in lane.placements)),
        key=lambda lane: (str(lane.lane_id[0]), int(lane.lane_id[1]))))


def page_covered_tiles(inputs: RunInputs, lanes: Sequence[Lane], page: int,
                       ) -> tuple[tuple[int, int], ...]:
    """The UNION of the lanes' covered tiles, in row-major order.

    The pooled fit samples from the union and hands every lane the SAME
    tiles, so that pooling at a tile is over lanes rather than over
    whichever tiles each lane happened to draw.
    """
    union: set[tuple[int, int]] = set()
    for lane in lanes:
        union.update(covered_tiles(inputs, lane, int(page)))
    return tuple(sorted(union))


def _page_of(lane: Lane) -> int:
    pages = sorted({int(placement.page) for placement in lane.placements})
    if not pages:
        raise ValueError(f"lane {lane.lane_id} has no accepted placement")
    return int(pages[0])


# ------------------------------------------------------- the measurement

def _one_tile(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
              stream_id: str, ty: int, tx: int, page: int, *,
              halo: int, unmix_mode: str, seed: int,
              lane_mix: Any) -> TileOffset:
    """The `offset` arm's blind search over ONE tile, scored two ways.

    The target key is this tile's own (page, ty, tx, stream), so
    `frame.known_frame` excludes its certificate from the projections
    exactly as it does for a residue target (DESIGN §4.5): a certified
    tile is read here from its NEIGHBOURS' labels and its own furniture,
    never from its own answer.
    """
    plane = PLANE_OF[str(stream_id)]
    key: Key = (int(page), int(ty), int(tx), str(stream_id))
    empty = TileOffset(ty=int(ty), tx=int(tx), offset_dots_xy=(0.0, 0.0),
                       n_labels=0, n_discriminating=0,
                       committed_logloss=None, search_logloss=None,
                       gain=None, curvature=0.0, weight=0.0)
    cell_dots = color_sites.cell_dots_of(inputs.row)
    fp = frame_mod.tile_footprint(inputs.row, int(page), int(ty), int(tx),
                                  int(halo), geometry=inputs.geometry)
    lfp = sample_mod.lane_footprint(lane, fp)
    if lfp is None or not np.any(lfp.observed):
        return _refused(empty, "no_owned_cell")
    folds = cal.split_folds(fp.page_cells_yx, int(seed))
    bound = max(abs(arms_mod.OFFSET_X_MIN), abs(arms_mod.OFFSET_X_MAX),
                float(cell_dots)) + 0.5
    try:
        crops = sample_mod.open_crops(lane, lfp, bound_dots=bound,
                                      cell_dots=cell_dots)
    except sample_mod.SampleError as error:
        return _refused(empty, f"crop:{error}")
    frame = frame_mod.known_frame(inputs, certs, fp, key,
                                  metadata_known=False)
    mix, _scope = arms_mod.fit_mix(
        sample_mod.read_rgb(crops, lfp, arm="field2-mix").values_rgb, frame,
        scope_ladder=("footprint", "lane") if lane_mix is not None
        else ("footprint",),
        lane_mix=lane_mix, cells_yx=fp.page_cells_yx,
        usable=np.asarray(lfp.observed, bool))
    if not mix.accepted:
        return _refused(empty, f"no_mix:{mix.reason}")

    observed = np.asarray(lfp.observed, bool)
    labels = np.asarray(frame.known[:, plane], bool) & observed
    n_labels = int(np.count_nonzero(labels))

    committed = sample_mod.read_rgb(crops, lfp, arm="field2-committed")
    committed_loss = None
    if committed.refusal is None:
        committed_loss = cal.fold_logloss(
            arms_mod.unmix_score(unmix_mode, plane, mix,
                                 committed.values_rgb, frame,
                                 fit_mask=folds.fit),
            frame, plane, folds, usable=observed)

    offset, detail = arms_mod._search_offset(
        crops, lfp, frame, mix, plane, unmix_mode, folds, (0.0, 0.0), None,
        profile=True)
    search_loss = detail.get("offset_search_logloss")
    # the X profile only: the Y sweep is evaluated AT the winning x, so
    # its losses all sit near the optimum and would flatten a curvature
    # that the ±2-dot x sweep measures honestly.
    profile = [value for value in dict(
        detail.get("offset_profile") or {}).get("x", ())
        if value is not None and np.isfinite(value)]
    curvature = 0.0
    if len(profile) >= 3 and search_loss is not None:
        curvature = float(np.mean(profile) - float(search_loss))
    gain = (None if (committed_loss is None or search_loss is None)
            else float(committed_loss) - float(search_loss))
    sharpness = float(np.clip(curvature / CURVATURE_SCALE_NATS, 0.0, 1.0))
    return TileOffset(
        ty=int(ty), tx=int(tx),
        offset_dots_xy=(float(offset[0]), float(offset[1])),
        n_labels=n_labels, n_discriminating=int(frame.n_discriminating),
        committed_logloss=(None if committed_loss is None
                           else float(committed_loss)),
        search_logloss=(None if search_loss is None else float(search_loss)),
        gain=gain, curvature=curvature,
        weight=float(n_labels) * sharpness,
        refusal=None if search_loss is not None else "search_refused")


def _refused(empty: TileOffset, reason: str) -> TileOffset:
    return dataclass_replace(empty, refusal=str(reason))


# ----------------------------------------------------------- the pooling

def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """The lower weighted median of `values` — a stable, exact draw.

    Sorted by value with `kind="stable"`, so equal values keep their
    input order and the answer does not depend on which thread finished
    first; the first point whose cumulative weight reaches half the total
    wins, and an exact half-way tie takes the mean of the two straddling
    values (the ordinary median convention at even weight).
    """
    order = np.argsort(np.asarray(values, np.float64), kind="stable")
    v = np.asarray(values, np.float64)[order]
    w = np.asarray(weights, np.float64)[order]
    total = float(w.sum())
    if not total > 0.0:
        return float(np.median(v)) if v.size else 0.0
    cumulative = np.cumsum(w)
    index = int(np.searchsorted(cumulative, 0.5 * total, side="left"))
    index = min(index, v.size - 1)
    if abs(float(cumulative[index]) - 0.5 * total) < 1e-12 \
            and index + 1 < v.size:
        return 0.5 * (float(v[index]) + float(v[index + 1]))
    return float(v[index])


def pool_tile(records: Sequence[TileOffset], mode: str = POOL_WMEDIAN,
              ) -> TileOffset | None:
    """One tile's lane records -> ONE pooled record, or None if empty.

    COMPONENT-WISE on x and y: the two axes are separate physical claims
    (x is the measured one, y is reported — see `PageField`), and a joint
    "median point" would be neither lane's answer on either axis.

    The pooled WEIGHT is the SUM of the contributing lanes' weights, i.e.
    the total label evidence standing behind the tile.  That is what the
    surface's least squares and the kernel's support normalisation both
    want: a tile eleven lanes agree on should outvote one that two lanes
    guessed at, and the record keeps `n_lanes` beside it so the reader
    can see which it was.
    """
    live = [item for item in records
            if item.weight > 0.0 and np.all(np.isfinite(item.offset_dots_xy))]
    if not live:
        return None
    if mode not in POOL_MODES:
        raise ValueError(f"unknown pooling mode {mode!r}; {POOL_MODES}")
    offsets = np.asarray([item.offset_dots_xy for item in live],
                         np.float64).reshape(-1, 2)
    weights = np.asarray([item.weight for item in live], np.float64)
    if mode == POOL_WMEAN:
        pooled = tuple(float(np.average(offsets[:, axis], weights=weights))
                       for axis in (0, 1))
    else:
        pooled = tuple(_weighted_median(offsets[:, axis], weights)
                       for axis in (0, 1))
    first = live[0]
    return TileOffset(
        ty=int(first.ty), tx=int(first.tx),
        offset_dots_xy=(float(pooled[0]), float(pooled[1])),
        n_labels=int(sum(item.n_labels for item in live)),
        n_discriminating=int(max(item.n_discriminating for item in live)),
        committed_logloss=None, search_logloss=None,
        gain=(float(np.median([item.gain for item in live
                               if item.gain is not None]))
              if any(item.gain is not None for item in live) else None),
        curvature=float(np.median([item.curvature for item in live])),
        weight=float(weights.sum()), refusal=None, n_lanes=len(live))


# ---------------------------------------------------------- the surface

def _design(tiles_yx: tuple[int, int], ty: np.ndarray, tx: np.ndarray,
            degree: int) -> np.ndarray:
    """Monomials up to total `degree` in normalised page coordinates."""
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    v = 2.0 * np.asarray(ty, np.float64) / max(height - 1, 1) - 1.0
    u = 2.0 * np.asarray(tx, np.float64) / max(width - 1, 1) - 1.0
    columns = [np.ones_like(u)]
    for total in range(1, int(degree) + 1):
        for power_u in range(total, -1, -1):
            columns.append(u ** power_u * v ** (total - power_u))
    return np.stack(columns, axis=1)


def _fit_surface(tiles_yx: tuple[int, int], ty: np.ndarray, tx: np.ndarray,
                 offsets: np.ndarray, weights: np.ndarray,
                 ) -> tuple[np.ndarray, int]:
    """Weighted least squares with a degree ladder; (H, W, 2) surface."""
    live = np.asarray(weights, np.float64) > 0.0
    n_live = int(np.count_nonzero(live))
    degree = int(MAX_DEGREE)
    while degree > 0:
        n_terms = (degree + 1) * (degree + 2) // 2
        if n_live >= MIN_TILES_PER_TERM * n_terms:
            break
        degree -= 1
    grid_y, grid_x = np.meshgrid(np.arange(tiles_yx[0]),
                                 np.arange(tiles_yx[1]), indexing="ij")
    full = _design(tiles_yx, grid_y.ravel(), grid_x.ravel(), degree)
    if n_live == 0:
        return np.zeros((tiles_yx[0], tiles_yx[1], 2), np.float64), degree
    design = _design(tiles_yx, ty[live], tx[live], degree)
    root = np.sqrt(np.asarray(weights, np.float64)[live])[:, None]
    solution, *_ = np.linalg.lstsq(design * root,
                                   np.asarray(offsets, np.float64)[live]
                                   * root, rcond=None)
    surface = (full @ solution).reshape(int(tiles_yx[0]), int(tiles_yx[1]), 2)
    return surface, degree


def _smoothed_residual(tiles_yx: tuple[int, int], ty: np.ndarray,
                       tx: np.ndarray, residual: np.ndarray,
                       weights: np.ndarray, bandwidth_tiles: float,
                       passes: int = plane_field_lib.TWICING_PASSES,
                       ) -> tuple[np.ndarray, np.ndarray]:
    """DESIGN §4.6's support normalisation, over the surface's residual.

    `num = smooth(w.r)`, `den = smooth(w)`; zero where `den` is zero, so
    an unobserved tile keeps the SURFACE rather than being pulled toward
    zero by the zero-padded kernel.

    Then production's TWICING (`plane_field.solve`'s Gauss-Newton step,
    the same `TWICING_PASSES`): a local weighted mean attenuates smooth
    structure — a 2-tile bandwidth damps a 16-tile sinusoid by ~26%, so
    a field fitted without it under-reports the very amplitude the
    AltaLink sinusoid is interesting for — and re-smoothing what the
    first pass left over buys most of it back (measured on the planted
    field: median error 0.152 -> 0.040 dots, and the recovered
    amplitude 0.816 against a planted 0.8).
    """
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    mass = np.zeros((height, width), np.float64)
    binned = np.zeros((height, width, 2), np.float64)
    w = np.asarray(weights, np.float64)
    r = np.asarray(residual, np.float64)
    rows = np.asarray(ty, np.int64)
    columns = np.asarray(tx, np.int64)
    for index in range(w.shape[0]):
        if not (w[index] > 0.0) or not np.all(np.isfinite(r[index])):
            continue
        binned[int(rows[index]), int(columns[index])] += r[index] * w[index]
        mass[int(rows[index]), int(columns[index])] += w[index]
    kernel = plane_field_lib.gaussian_kernel(float(bandwidth_tiles))
    denominator = plane_field_lib.smooth(mass, kernel)
    live = denominator > 0.0
    safe = np.where(live, denominator, 1.0)

    def local_mean(weighted: np.ndarray) -> np.ndarray:
        out = np.zeros((height, width, 2), np.float64)
        for axis in (0, 1):
            out[..., axis] = np.where(
                live, plane_field_lib.smooth(weighted[..., axis], kernel)
                / safe, 0.0)
        return out

    field = local_mean(binned)
    for _ in range(max(0, int(passes))):
        left = np.zeros((height, width, 2), np.float64)
        for index in range(w.shape[0]):
            if not (w[index] > 0.0) or not np.all(np.isfinite(r[index])):
                continue
            row, column = int(rows[index]), int(columns[index])
            left[row, column] += (r[index] - field[row, column]) * w[index]
        field = field + local_mean(left)
    return field, denominator


def build_field(records: Sequence[TileOffset], tiles_yx: tuple[int, int],
                bandwidth_tiles: float = BANDWIDTH_TILES,
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float,
                           int]:
    """Per-tile offsets -> (delta, support, surface, degree, rms, n_used).

    The pure half of the fit: surface + support-normalised smoothed
    residual, clamped at production's bound.  No pixels, no run dir — so
    a planted field can be recovered in a unit test and the arithmetic is
    the same one the paper fit uses.
    """
    used = [item for item in records if item.weight > 0.0
            and np.all(np.isfinite(item.offset_dots_xy))]
    ty = np.asarray([item.ty for item in used], np.float64)
    tx = np.asarray([item.tx for item in used], np.float64)
    offsets = np.asarray([item.offset_dots_xy for item in used],
                         np.float64).reshape(-1, 2)
    weights = np.asarray([item.weight for item in used], np.float64)
    surface, degree = _fit_surface(tiles_yx, ty, tx, offsets, weights)
    if used:
        residual = offsets - surface[ty.astype(np.int64),
                                     tx.astype(np.int64)]
    else:
        residual = np.zeros((0, 2), np.float64)
    smoothed, support = _smoothed_residual(tiles_yx, ty, tx, residual,
                                           weights, bandwidth_tiles)
    delta = plane_field_lib.clamp(surface + smoothed, MAX_DELTA_DOTS)
    rms = 0.0
    if used:
        left = offsets - delta[ty.astype(np.int64), tx.astype(np.int64)]
        rms = float(np.sqrt(np.average((left ** 2).sum(axis=1),
                                       weights=weights)))
    return delta, support, surface, int(degree), rms, len(used)


# ------------------------------------------------------------- the fit

#: key -> (field, a STRONG reference to the run dir the key's `id()` was
#: taken from).  `frame._certs_token` hardened the same hazard the same
#: way: a dead object's id is reused, so a memo that keys on `id(x)`
#: without holding `x` can hand a second run the first run's field.  The
#: held object is one `Path`, not the `RunInputs`, so nothing heavy is
#: pinned.
_MEMO: dict[tuple, tuple[PageField, Any]] = {}
_MEMO_ORDER: list[tuple] = []
_MEMO_LOCK = threading.Lock()
_KEY_LOCKS: dict[tuple, threading.Lock] = {}


def _memo_key(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
              stream_id: str, page: int, tiles: Any, seed: int,
              unmix_mode: str, halo: int, bandwidth_tiles: float) -> tuple:
    if isinstance(tiles, (int, np.integer)) or tiles is None:
        sample: Any = int(tiles) if tiles is not None else None
    else:
        sample = tuple(sorted((int(ty), int(tx)) for ty, tx in tiles))
    # `id(inputs.run_dir)` separates two RunInputs over the SAME run dir
    # (whose certificate tokens both start at 0, being per-RunInputs); the
    # memo holds the run dir so that id cannot be recycled under it.
    return (id(inputs.run_dir), str(inputs.run_dir),
            str(inputs.format_ref), lane.lane_id, str(stream_id), int(page),
            frame_mod._certs_token(inputs, certs), sample,
            int(seed), str(unmix_mode), int(halo), float(bandwidth_tiles))


def fit_page_field(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
                   stream: str, *, tiles: Any = None, seed: int = 0,
                   page: int | None = None, halo_cells: int | None = None,
                   unmix_mode: str = "subtract",
                   bandwidth_tiles: float = BANDWIDTH_TILES,
                   memoise: bool = True) -> PageField:
    """The per-plane page field of one (lane, stream) — DESIGN §13.

    THE CERTIFICATE-ANCHORED, PER-LANE fit — what the `field2c` arms
    read.  The `field2` arms read `fit_pooled_page_field` instead, which
    is one fit per (page, plane) over every lane and takes its labels
    from furniture only.

    `tiles` is None for EVERY covered tile of the page (the default; the
    certified ones are the best anchors and are kept), an int for a
    deterministic subsample of that size, or an explicit iterable of
    (ty, tx).  Memoised per (run dir, format, lane, stream, PAGE,
    certificate token, tile sample, seed, mode, halo, bandwidth) — the
    pass pays once PER GENERATION, because `fixedpoint` hands every
    generation a fresh certificate snapshot and the token moves with it
    (which is right: the field should see the new certificates).
    """
    stream_id = str(stream)
    plane = PLANE_OF[stream_id]
    page = _page_of(lane) if page is None else int(page)
    halo = int(arms_mod.HALO_CELLS[stream_id] if halo_cells is None
               else halo_cells)
    key = _memo_key(inputs, certs, lane, stream_id, page, tiles, seed,
                    unmix_mode, halo, bandwidth_tiles)
    if memoise:
        with _MEMO_LOCK:
            hit = _MEMO.get(key)
            if hit is not None:
                return hit[0]
            lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    else:
        lock = threading.Lock()
    with lock:
        if memoise:
            with _MEMO_LOCK:
                hit = _MEMO.get(key)
            if hit is not None:
                return hit[0]
        built = _fit(inputs, certs, lane, stream_id, plane, page, tiles,
                     seed, halo, unmix_mode, bandwidth_tiles)
        if memoise:
            with _MEMO_LOCK:
                _MEMO[key] = (built, inputs.run_dir)
                _MEMO_ORDER.append(key)
                while len(_MEMO_ORDER) > MEMO_MAX:
                    _MEMO.pop(_MEMO_ORDER.pop(0), None)
                _KEY_LOCKS.pop(key, None)
        return built


def _choose(candidates: Sequence[tuple[int, int]], tiles: Any, seed: int,
            ) -> tuple[tuple[int, int], ...]:
    if tiles is None:
        return tuple(sorted(candidates))
    if isinstance(tiles, (int, np.integer)):
        return sample_tiles(candidates, int(tiles), int(seed))
    wanted = {(int(ty), int(tx)) for ty, tx in tiles}
    return tuple(sorted(wanted & set(candidates)))


def _lane_records(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
                  stream_id: str, page: int,
                  chosen: Sequence[tuple[int, int]], seed: int, halo: int,
                  unmix_mode: str) -> tuple[TileOffset, ...]:
    """One lane's per-tile blind offsets over `chosen`.

    ONE lane-scope mixing fit for the whole page, so a 300-tile fit pays
    for it once instead of 300 times.  DECLARED DEVIATION, and ONLY for
    a CERTIFICATE-ANCHORED fit: a per-target fit excludes the target's
    tile from that 12-tile sample (`arms.lane_mix`'s memo key carries the
    exclusion), and this one excludes nothing — so for the ~0.6% of tiles
    that happen to be in the sample, their own certificate reaches the
    SPECTRAL fit (never the labels: `known_frame` still excludes the
    target key).  The field is a search prior scored on held-out labels,
    not a certificate, and production's `fit_lane_mix` is lane-scope for
    the same reason; recorded rather than hidden.  With
    ``certs = NO_CERTS`` the deviation does not arise at all: there is no
    certificate anywhere in the fit to leak.
    """
    if not chosen:
        return ()
    lane_mix, _detail = arms_mod.lane_mix(
        inputs, lane, certs, stream_id, page=int(page),
        exclude_tile=None, n_tiles=arms_mod.LANE_MIX_TILES)
    return tuple(
        _one_tile(inputs, certs, lane, stream_id, ty, tx, page, halo=halo,
                  unmix_mode=unmix_mode, seed=int(seed), lane_mix=lane_mix)
        for ty, tx in chosen)


def _fit(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
         stream_id: str, plane: int, page: int, tiles: Any, seed: int,
         halo: int, unmix_mode: str, bandwidth_tiles: float) -> PageField:
    chosen = _choose(covered_tiles(inputs, lane, page), tiles, seed)
    records = _lane_records(inputs, certs, lane, stream_id, page, chosen,
                            seed, halo, unmix_mode)

    tiles_yx = (int(inputs.tiles_yx[0]), int(inputs.tiles_yx[1]))
    built = build_field(records, tiles_yx, bandwidth_tiles)
    delta, support, surface, degree, rms, n_used = built
    return PageField(
        lane=lane.lane_id, stream_id=stream_id, page=int(page), plane=plane,
        delta_dots_xy=delta, support=support, poly_dots_xy=surface,
        degree=int(degree), tiles=records,
        median_delta_dots=float(plane_field_lib.median_magnitude_dots(
            delta, support)),
        residual_rms_dots=rms, anchors=ANCHORS_CERTIFIED,
        detail=_detail(records, n_used, degree, support, bandwidth_tiles,
                       unmix_mode, halo, seed))


def _detail(records: Sequence[TileOffset], n_used: int, degree: int,
            support: np.ndarray, bandwidth_tiles: float, unmix_mode: str,
            halo: int, seed: int) -> dict:
    return {
        "n_tiles_read": len(records),
        "n_tiles_weighted": int(n_used),
        "n_tiles_refused": sum(1 for item in records
                               if item.refusal is not None),
        "weight_total": float(sum(item.weight for item in records)),
        "median_n_labels": (float(np.median([item.n_labels
                                             for item in records]))
                            if records else 0.0),
        "median_gain": (float(np.median([item.gain for item in records
                                         if item.gain is not None]))
                        if any(item.gain is not None
                               for item in records) else None),
        "surface_degree": int(degree),
        "bandwidth_tiles": float(bandwidth_tiles),
        "unmix_mode": str(unmix_mode),
        "halo_cells": int(halo),
        "seed": int(seed),
        "support_fraction": float(np.mean(support > 0.0)),
        "curvature_scale_nats": CURVATURE_SCALE_NATS,
        # DESIGN §13 / the module docstring: the number production's
        # writer would refuse on, published beside the field rather
        # than instead of it.
        "production_min_delta_dots": float(fields_plugin.MIN_DELTA_DOTS),
    }


# ------------------------------------------------------- the pooled fit

def _pooled_memo_key(inputs: RunInputs, certs: Mapping[Key, Any],
                     stream_id: str, page: int, anchors: str,
                     lane_ids: Sequence[Any], tiles: Any, seed: int,
                     unmix_mode: str, halo: int, bandwidth_tiles: float,
                     pool: str) -> tuple:
    """The pooled fit's key — WITHOUT a certificate token for furniture.

    A furniture-only fit is a pure function of the paper and the format:
    `known_frame` is called with `NO_CERTS`, so no certificate reaches
    the labels OR the mixing fit, and the field a generation computes is
    bit-identical to the one every other generation would.  Putting the
    certificate token in the key would therefore not protect anything —
    it would only refit the whole page every time the cascade minted a
    tile, which is exactly the cost this fit exists to remove.

    The token STAYS for `certified` anchors, where the fit does read the
    neighbours' certificates and two certificate mappings (a `--withhold`
    control against the full set, DESIGN §8) must never share an entry.

    Everything else in the key is something that changes the arithmetic:
    the run, the format, the page, the stream, the lane SET, the tile
    sample, the seed, the unmix mode, the halo, the bandwidth and the
    pooling rule.
    """
    if isinstance(tiles, (int, np.integer)) or tiles is None:
        sample: Any = int(tiles) if tiles is not None else None
    else:
        sample = tuple(sorted((int(ty), int(tx)) for ty, tx in tiles))
    token = (None if anchors == ANCHORS_FURNITURE
             else frame_mod._certs_token(inputs, certs))
    return ("pooled", id(inputs.run_dir), str(inputs.run_dir),
            str(inputs.format_ref), int(page), str(stream_id), str(anchors),
            tuple(sorted((str(one[0]), int(one[1])) for one in lane_ids)),
            sample, int(seed), str(unmix_mode), int(halo),
            float(bandwidth_tiles), str(pool), token)


def fit_pooled_page_field(inputs: RunInputs, stream: str, page: int, *,
                          lanes: Sequence[Lane] | None = None,
                          anchors: str = ANCHORS_FURNITURE,
                          tiles: Any = None, seed: int = 0,
                          certs: Mapping[Key, Any] | None = None,
                          halo_cells: int | None = None,
                          unmix_mode: str = "subtract",
                          bandwidth_tiles: float = BANDWIDTH_TILES,
                          pool: str = POOL_WMEDIAN, workers: int = 1,
                          memoise: bool = True) -> PageField:
    """ONE per-plane field for a PRINTED PAGE, pooled over its lanes.

    RULING (Germano, 2026-09-03 late).  The per-plane registration field
    is a property of the printed page: it is invariant across rungs and
    across captures of the same sheet (measured on sheet H — three
    captures agreed to 0.065 dots), so there is one field to fit, not one
    per lane per generation.  Fitted from FURNITURE anchors only it is
    also invariant across cascade generations and blind by construction.

    Every lane of the page contributes the per-tile blind offsets
    `fit_page_field` measures, over the SAME tile sample (drawn from the
    union of the lanes' coverage), and they are pooled per tile by
    :func:`pool_tile` before the ONE surface + support-normalised
    residual is fitted with the existing machinery.  Offsets need no
    conversion: they are page-frame by construction (DESIGN §4.4 —
    `sample.read_rgb` shifts through ``level_terms[:, :2]``, without the
    placement's rotation), which is why lanes whose placements differ in
    `rot_k` can be pooled at all.

    `lanes` defaults to every lane with a placement on the page.
    `anchors` is `furniture` (no certificate anywhere) or `certified`
    (the neighbours' certified cargo too, and then `certs` is required).
    `tiles` is None for every covered tile, an int for a deterministic
    subsample, or an explicit iterable.  `workers` threads the per-LANE
    reads; the result does not depend on it (the pooling is order-free
    and the lanes are visited in lane-id order).
    """
    stream_id = str(stream)
    plane = PLANE_OF[stream_id]
    page = int(page)
    if anchors not in ANCHOR_SETS:
        raise ValueError(f"unknown anchor set {anchors!r}; {ANCHOR_SETS}")
    if anchors == ANCHORS_FURNITURE:
        certs = NO_CERTS
    elif certs is None:
        raise ValueError("anchors='certified' needs a certificate mapping")
    pool_lanes = tuple(lanes_for_page(inputs, page) if lanes is None
                       else lanes)
    if not pool_lanes:
        raise ValueError(f"no lane has a placement on page {page}")
    halo = int(arms_mod.HALO_CELLS[stream_id] if halo_cells is None
               else halo_cells)
    key = _pooled_memo_key(inputs, certs, stream_id, page, anchors,
                           [lane.lane_id for lane in pool_lanes], tiles,
                           seed, unmix_mode, halo, bandwidth_tiles, pool)
    if memoise:
        with _MEMO_LOCK:
            hit = _MEMO.get(key)
            if hit is not None:
                return hit[0]
            lock = _KEY_LOCKS.setdefault(key, threading.Lock())
    else:
        lock = threading.Lock()
    with lock:
        if memoise:
            with _MEMO_LOCK:
                hit = _MEMO.get(key)
            if hit is not None:
                return hit[0]
        built = _pooled_fit(inputs, certs, pool_lanes, stream_id, plane,
                            page, anchors, tiles, seed, halo, unmix_mode,
                            bandwidth_tiles, pool, workers)
        if memoise:
            with _MEMO_LOCK:
                _MEMO[key] = (built, inputs.run_dir)
                _MEMO_ORDER.append(key)
                while len(_MEMO_ORDER) > MEMO_MAX:
                    _MEMO.pop(_MEMO_ORDER.pop(0), None)
                _KEY_LOCKS.pop(key, None)
        return built


def pooled_records(inputs: RunInputs, certs: Mapping[Key, Any],
                   pool_lanes: Sequence[Lane], stream_id: str, page: int,
                   tiles: Any, seed: int, halo: int, unmix_mode: str,
                   workers: int = 1,
                   ) -> dict[tuple[int, int], list[TileOffset]]:
    """The pooled fit's RAW evidence: tile -> one record per lane.

    Split out from the fit so a caller can pool the SAME reads two ways
    (the record compares `wmedian` against `wmean`) without paying for
    the reads twice.  The lanes are visited in the order given and the
    per-tile lists are in that order, so a threaded call and a serial one
    build identical lists.
    """
    chosen = _choose(page_covered_tiles(inputs, pool_lanes, page), tiles,
                     seed)
    covered = {lane.lane_id: set(covered_tiles(inputs, lane, int(page)))
               for lane in pool_lanes}

    def read(lane: Lane) -> tuple[TileOffset, ...]:
        mine = tuple(tile for tile in chosen if tile in covered[lane.lane_id])
        return _lane_records(inputs, certs, lane, stream_id, int(page), mine,
                             seed, halo, unmix_mode)

    if int(workers) > 1 and len(pool_lanes) > 1:
        with ThreadPoolExecutor(max_workers=int(workers)) as executor:
            per_lane = list(executor.map(read, pool_lanes))
    else:
        per_lane = [read(lane) for lane in pool_lanes]
    by_tile: dict[tuple[int, int], list[TileOffset]] = {}
    for records in per_lane:
        for item in records:
            by_tile.setdefault((int(item.ty), int(item.tx)), []).append(item)
    return by_tile


def field_from_pooled(by_tile: Mapping[tuple[int, int], Sequence[TileOffset]],
                      inputs: RunInputs, lane_ids: Sequence[Any],
                      stream_id: str, plane: int, page: int, anchors: str,
                      seed: int, halo: int, unmix_mode: str,
                      bandwidth_tiles: float = BANDWIDTH_TILES,
                      pool: str = POOL_WMEDIAN,
                      n_tiles_sampled: int | None = None) -> PageField:
    """Pool `by_tile` and fit the ONE surface + residual over the page."""
    pooled: list[TileOffset] = []
    n_read = 0
    n_refused = 0
    for tile in sorted(by_tile):
        items = list(by_tile[tile])
        n_read += len(items)
        n_refused += sum(1 for item in items if item.refusal is not None)
        one = pool_tile(items, pool)
        if one is not None:
            pooled.append(one)
    records = tuple(pooled)
    tiles_yx = (int(inputs.tiles_yx[0]), int(inputs.tiles_yx[1]))
    delta, support, surface, degree, rms, n_used = build_field(
        records, tiles_yx, bandwidth_tiles)
    n_lanes = np.zeros(tiles_yx, np.int64)
    for item in records:
        n_lanes[int(item.ty), int(item.tx)] = int(item.n_lanes)
    ids = tuple((str(one[0]), int(one[1])) for one in lane_ids)
    detail = _detail(records, n_used, degree, support, bandwidth_tiles,
                     unmix_mode, halo, seed)
    detail.update({
        "pooled": True, "anchors": str(anchors), "pool_mode": str(pool),
        "n_lanes_pooled": len(ids),
        "n_tiles_sampled": int(len(by_tile) if n_tiles_sampled is None
                               else n_tiles_sampled),
        "n_lane_tile_reads": int(n_read),
        "n_lane_tile_refused": int(n_refused),
        "median_n_lanes_per_tile": (
            float(np.median([item.n_lanes for item in records]))
            if records else 0.0),
        "lanes": [[one[0][:12], one[1]] for one in ids],
        "certificate_free": anchors == ANCHORS_FURNITURE,
    })
    return PageField(
        lane=None, stream_id=str(stream_id), page=int(page), plane=int(plane),
        delta_dots_xy=delta, support=support, poly_dots_xy=surface,
        degree=int(degree), tiles=records,
        median_delta_dots=float(plane_field_lib.median_magnitude_dots(
            delta, support)),
        residual_rms_dots=rms, lanes=ids, anchors=str(anchors),
        n_lanes=n_lanes, detail=detail)


def _pooled_fit(inputs: RunInputs, certs: Mapping[Key, Any],
                pool_lanes: Sequence[Lane], stream_id: str, plane: int,
                page: int, anchors: str, tiles: Any, seed: int, halo: int,
                unmix_mode: str, bandwidth_tiles: float, pool: str,
                workers: int) -> PageField:
    by_tile = pooled_records(inputs, certs, pool_lanes, stream_id, page,
                             tiles, seed, halo, unmix_mode, workers)
    return field_from_pooled(
        by_tile, inputs, [lane.lane_id for lane in pool_lanes], stream_id,
        plane, page, anchors, seed, halo, unmix_mode, bandwidth_tiles, pool)


def field_for(inputs: RunInputs, certs: Mapping[Key, Any], lane: Lane,
              stream: str, knobs: Mapping[str, Any], *,
              anchors: str = ANCHORS_FURNITURE,
              page: int | None = None) -> PageField | None:
    """The field a `field2` / `field2c` arm should use, from the knobs.

    `anchors` is the ARM's choice, not a knob: `field2` reads the POOLED
    FURNITURE field (one fit per page-plane, shared by every lane and
    every generation), `field2c` the per-lane certificate-anchored one.

    `knobs["page_field2"]` may be a `PageField` (use it), or the DRIVER's
    own table of pre-fitted fields — keyed by ``(page, stream)`` for the
    pooled form and ``(lane_id, stream)`` for the per-lane one — or
    absent, in which case the field is fitted here and memoised, the way
    `arms.page_context` fits the page context on first use.  A caller
    that wants no fitting passes ``page_field2_fit=False``.
    """
    page = _page_of(lane) if page is None else int(page)
    standing = knobs.get("page_field2")
    if isinstance(standing, PageField):
        return standing
    if isinstance(standing, Mapping):
        # A table is the DRIVER's own; an entry missing from it is a
        # deliberate "not for this one", not an invitation to fit a field
        # behind the driver's back.
        found = standing.get((int(page), str(stream))
                             if anchors == ANCHORS_FURNITURE
                             else (lane.lane_id, str(stream)))
        return found if isinstance(found, PageField) else None
    if not bool(knobs.get("page_field2_fit", True)):
        return None
    if anchors == ANCHORS_CERTIFIED:
        return fit_page_field(
            inputs, certs, lane, str(stream), page=int(page),
            tiles=knobs.get("field2_tiles", FIT_TILES_DEFAULT),
            seed=int(knobs.get("seed", 0)),
            halo_cells=knobs.get("halo_cells"),
            unmix_mode=str(knobs.get("field2_unmix_mode", "subtract")),
            bandwidth_tiles=float(knobs.get("field2_bandwidth_tiles",
                                            BANDWIDTH_TILES)))
    return fit_pooled_page_field(
        inputs, str(stream), int(page), lanes=knobs.get("field2_lanes"),
        anchors=ANCHORS_FURNITURE,
        tiles=knobs.get("field2_pooled_tiles", POOLED_FIT_TILES_DEFAULT),
        seed=int(knobs.get("seed", 0)),
        halo_cells=knobs.get("halo_cells"),
        unmix_mode=str(knobs.get("field2_unmix_mode", "subtract")),
        bandwidth_tiles=float(knobs.get("field2_bandwidth_tiles",
                                        BANDWIDTH_TILES)),
        pool=str(knobs.get("field2_pool", POOL_WMEDIAN)),
        workers=int(knobs.get("field2_fit_workers", 1)))


def summary(field: PageField) -> dict:
    """A flat, JSON-safe digest of a fit (the record's own row)."""
    return {
        "lane": (None if field.lane is None
                 else (field.lane[0][:12], int(field.lane[1]))),
        "pooled": bool(field.pooled), "anchors": str(field.anchors),
        "n_lanes_pooled": len(field.lanes),
        "stream": field.stream_id, "page": int(field.page),
        "median_delta_dots": field.median_delta_dots,
        "residual_rms_dots": field.residual_rms_dots,
        "degree": int(field.degree),
        "production_publishable": bool(field.production_publishable),
        "production_refusal": field.production_refusal,
        **{name: value for name, value in dict(field.detail).items()},
    }


def column_profile(field: PageField, axis: int = 0) -> np.ndarray:
    """Support-weighted mean delta per tile COLUMN, one axis.

    The x-delta as a function of page x — the shape the AltaLink's
    yellow registration sinusoid lives in (e033: 0.83 dot peak, ~100 mm
    period; `measure/yask` §4.2 saw the same object in the yellow signal).
    NaN in a column with no support at all.
    """
    delta = np.asarray(field.delta_dots_xy, np.float64)[..., int(axis)]
    weight = np.asarray(field.support, np.float64)
    mass = weight.sum(axis=0)
    out = np.full(delta.shape[1], np.nan, np.float64)
    live = mass > 0.0
    out[live] = (delta * weight).sum(axis=0)[live] / mass[live]
    return out

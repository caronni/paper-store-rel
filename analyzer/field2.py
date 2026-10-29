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
0``) — `field2_kernel.smooth` is zero-padded, so smoothing a sparse band
without the normalisation would pull its edge toward zero, the failure
DESIGN §4.6 names.  The bandwidth is 2 tiles
(~11 mm), which resolves a 100 mm period comfortably, and the sum is
bounded at `field2_kernel.BOUND_DOTS` — both of them production's
numbers when they were chosen, and field2's own since the A2 ruling in
the last paragraph.

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

`fit_pooled_page_field` is that fit, and since 2026-09-12 (A2,
PAGE-FIELD-PLAN) it is the ONLY one: `fit_page_field`, the per-lane
certificate-anchored fit the retired `field2c` arms read, went with them
— it was the analyzer's last lane-keyed field, and a fit that reads
certificates is one the withholding controls have to refuse.  Its
measurements stand in `FIELD2-2026-09-03.md` §4, in the record's own
form: the pooled furniture field buys ~70-75% of the certificate-
anchored field's oracle gain on Y and slightly MORE on C, with zero
certificates in it — and `field2c` cost a refit per lane per generation
for that remainder, and took 0 first-success on sheet J's complete
residue.

HONEST UNITS.  Deltas are printed DOTS in the PAGE frame (DESIGN §4.4)
— the analyzer's own offsets are already page frame, since
`sample.read_rgb` shifts through `level_terms[:, :2]` without the
placement's rotation.  Every number this module publishes is in those
units, whatever its magnitude: here the field is a PRIOR for a search
that is still scored on held-out labels, not an adopted pose, so a
0.15-dot field that is real costs nothing when it is wrong and buys a
better search centre when it is right.  The distinction is what the arm
does with it, not what the number is.

FIELD2'S RULES ARE ITS OWN (A2, 2026-09-12, PAGE-FIELD-PLAN; DESIGN
§4.6).  Three rules in this module were quotations of the PRODUCTION
estimator, and the receiver's PAGE-FIELD line retired the originals: its
field is one penalised robust solve per printed page, with a prior where
this one has a kernel, and with no publish floor, no support gate and no
clip (`docs/PAGE-FIELD-DESIGN.md` I6, I8).  A quotation of a retired
rule is not a rule, so each was re-decided here.

* The 0.25-dot publish floor is GONE, with the `production_publishable`
  / `production_refusal` / `production_min_delta_dots` reporting that
  quoted it.  A floor the receiver retired is nothing to report against,
  and this instrument never refused on it anyway — it published and
  annotated, which was the paragraph above under its old title.
* The bound STAYS, at the same 2.0 dots, as `field2_kernel.BOUND_DOTS`,
  argued on this fit's own terms: a degree-<=3 surface plus a kernel
  residual has no prior and no fade, and 2 dots is the scale past which
  a page-registration reading is not credible.  It is NOT only the
  extrapolating polynomial that it moves — the per-tile search box
  admits (2, 1), norm 2.236 — so it is REPORTED where it bites, over
  the whole grid and separately under support (`clamped_tiles`,
  `clamped_supported_tiles`), never applied silently.
* `require_support` STAYS as this fit's own coverage refusal — the
  argument is in :meth:`PageField.evaluate`.

The kernel smoother came with them: `gaussian_kernel`, `smooth`, `clamp`
and their constants are `analyzer.field2_kernel` now, adopted verbatim so
the receiver can delete its copies (that module's docstring is the
provenance).  `tile_codes`, `evaluate` and `median_magnitude_dots` stay
imported from `holo.receiver.lib.plane_field`: live receiver code, and
`evaluate` is the one mapping every reader of a field samples through.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import (dataclass, field as dataclass_field,
                         replace as dataclass_replace)
from types import MappingProxyType
from typing import Any, Mapping, NamedTuple, Sequence

import numpy as np

from holo.receiver.lib import plane_field as plane_field_lib
from holo.receiver.plugins import color_sites

from . import arms as arms_mod
from . import calibrate as cal
from . import frame as frame_mod
from . import sample as sample_mod
from .field2_kernel import (BANDWIDTH_TILES, BOUND_DOTS, KERNEL_TRUNCATION,
                            TWICING_PASSES, clamp, gaussian_kernel, smooth)
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

#: The anchor set: word and dust only — certificate-free and
#: generation-invariant, what every `field2` arm reads.  It is the only
#: one since 2026-09-12 (A2), when the per-lane fit that also read the
#: neighbours' certified cargo retired with the `field2c` arms; a field
#: still carries the name, so a fit read back from an archived product
#: says what it was fitted from.
ANCHORS_FURNITURE = "furniture"

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

__all__ = ["ANCHORS_FURNITURE",
           "BANDWIDTH_TILES", "BOUND_DOTS", "CURVATURE_SCALE_NATS",
           "KERNEL_TRUNCATION", "MAX_DEGREE",
           "NO_CERTS", "POOLED_FIT_TILES_DEFAULT", "POOL_MODES",
           "POOL_WMEAN", "POOL_WMEDIAN", "TWICING_PASSES", "PageField",
           "TileOffset", "build_field", "by_tile_from", "column_profile",
           "covered_tiles", "field_for", "field_from_pooled",
           "fit_pooled_page_field", "fitted_pooled_fields", "lanes_for_page",
           "page_covered_tiles", "pool_tile", "pooled_records",
           "records_by_lane", "sample_tiles", "summary"]


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

    BOTH COMPONENTS ARE FITTED, AND y IS THE ONE UNDER TEST (A5,
    2026-09-12; supersedes FIELD2-2026-09-03 §3's "reported, not
    measured").  The y component was called reported because nothing to
    compare it against existed: the record's registration measurements
    were x measurements, this fit's own 4800 lane disagreed with its two
    2400 lanes on y by 0.185 dots where they agreed on x to 0.065, and
    the supervised sheet-I ground truth is x only (`compare.py
    --supervised`; design B3).  A reference exists now.  The receiver
    measures BOTH AXES everywhere since W8 (`measured_xy`) and solves
    them as two independent systems, so its y is the reference and this
    fit's y is the thing under test, through
    `measure/page_field/compare.py`'s `median_abs_dy_dots` per (page,
    plane) — sheet H at the W8 solve reads Y 0.0911 and C 0.1097 dots.
    There is still no SUPERVISED y on any sheet, so a disagreement there
    is a finding about one of the two estimators and names neither as
    wrong; x keeps its own bar (design B3, <= 0.12 dots median) and y
    runs beside it without one.
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
    anchors: str = ANCHORS_FURNITURE
    #: (tiles_y, tiles_x) count of pooled lanes per tile; None per-lane.
    n_lanes: np.ndarray | None = None

    @property
    def pooled(self) -> bool:
        return self.lane is None

    @property
    def tiles_yx(self) -> tuple[int, int]:
        return (int(self.support.shape[0]), int(self.support.shape[1]))

    def delta_at_tile(self, ty: int, tx: int) -> np.ndarray:
        return np.asarray(self.delta_dots_xy[int(ty), int(tx)], np.float64)

    def support_at_tile(self, ty: int, tx: int) -> float:
        return float(self.support[int(ty), int(tx)])

    def evaluate(self, cells_yx: np.ndarray, *, require_support: bool = True,
                 ) -> np.ndarray | None:
        """Per-cell PAGE-frame delta at these page cells, or None.

        `plane_field.evaluate`, CALLED — the same bilinear lookup at tile
        centres production samples through, so the two fields are read
        the same way.

        `require_support` IS FIELD2'S OWN GATE (A2, 2026-09-12).  It used
        to be justified as mirroring `plane_k.field_delta_dots`'s rule,
        and that rule no longer exists: the production field has no
        support gate and no refusal path, because it always exists for a
        colour family and FADES TO THE POSE away from evidence under its
        prior (`docs/PAGE-FIELD-DESIGN.md` I6, I8) — an unmeasured tile
        there reads zero, which is the pose, which is the right answer.
        Nothing pulls THIS fit to the pose.  Outside the furniture's
        coverage all it has is a degree-<=3 polynomial extrapolating, so
        it has no estimate at all there and must say so: this returns
        None, the arm records `field2_reason: no_support` (the spelling
        DESIGN §4.6 quotes) and collapses EXPLICITLY to `committed` —
        never a duplicate row — where the production `field` arm has
        nothing to refuse (AI3).  It stays a keyword rather than a law
        because a caller measuring the extrapolation itself must be
        able to ask for it.
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
    (both fitted; y is the one under test against the receiver's measured
    y — see `PageField`), and a joint
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


def n_terms_of(degree: int) -> int:
    """Free coefficients in a total-degree-`degree` surface, per axis."""
    return (int(degree) + 1) * (int(degree) + 2) // 2


def _fit_surface(tiles_yx: tuple[int, int], ty: np.ndarray, tx: np.ndarray,
                 offsets: np.ndarray, weights: np.ndarray,
                 ) -> tuple[np.ndarray, int]:
    """Weighted least squares with a degree ladder; (H, W, 2) surface.

    THE LADDER IS ON COUNT ALONE and a count is not identifiability
    (review §5.3, 2026-09-13): many observations confined to one tile ROW
    satisfy the six-term rule while the two-dimensional design has rank
    three, and `lstsq` then returns the minimum-norm solution — a number,
    not an exception, and one that says nothing about how the surface
    should extend away from the observed row.  The ladder is UNCHANGED;
    what changed is that `_detail` now reports `design_rank` beside
    `n_terms`, so a fit that is not identified says so.
    """
    live = np.asarray(weights, np.float64) > 0.0
    n_live = int(np.count_nonzero(live))
    degree = int(MAX_DEGREE)
    while degree > 0:
        if n_live >= MIN_TILES_PER_TERM * n_terms_of(degree):
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
                       passes: int = TWICING_PASSES,
                       ) -> tuple[np.ndarray, np.ndarray]:
    """DESIGN §4.6's support normalisation, over the surface's residual.

    `num = smooth(w.r)`, `den = smooth(w)`; zero where `den` is zero, so
    an unobserved tile keeps the SURFACE rather than being pulled toward
    zero by the zero-padded kernel.

    Then TWICING (the Gauss-Newton step `plane_field.solve` took when
    the receiver still smoothed, at the same `TWICING_PASSES`): a local
    weighted mean attenuates smooth
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
    kernel = gaussian_kernel(float(bandwidth_tiles))
    denominator = smooth(mass, kernel)
    live = denominator > 0.0
    safe = np.where(live, denominator, 1.0)

    def local_mean(weighted: np.ndarray) -> np.ndarray:
        out = np.zeros((height, width, 2), np.float64)
        for axis in (0, 1):
            out[..., axis] = np.where(
                live, smooth(weighted[..., axis], kernel) / safe, 0.0)
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


def live_records(records: Sequence[TileOffset]) -> list[TileOffset]:
    """The records the surface is fitted on: a weight, and a finite
    offset.  ONE predicate, so the `design_rank` `_detail` reports is the
    rank of the design `_fit_surface` actually solved."""
    return [item for item in records if item.weight > 0.0
            and np.all(np.isfinite(item.offset_dots_xy))]


def build_field(records: Sequence[TileOffset], tiles_yx: tuple[int, int],
                bandwidth_tiles: float = BANDWIDTH_TILES,
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float,
                           int, int]:
    """-> (delta, support, surface, degree, rms, n_used, n_clamped).

    The pure half of the fit: surface + support-normalised smoothed
    residual, bounded at `BOUND_DOTS`.  No pixels, no run dir — so a
    planted field can be recovered in a unit test and the arithmetic is
    the same one the paper fit uses.

    `n_clamped` is how many tiles of the grid the bound actually moved —
    counted HERE, where the unbounded sum exists, because the producer is
    the only thing that knows.  It is a diagnostic of the surface's
    extrapolation, not a refusal: a page whose bound never bites tells
    the reader the polynomial stayed inside registration's range
    everywhere, and one where it bites over an uncovered band tells them
    which part of the grid to disbelieve.
    """
    used = live_records(records)
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
    unbounded = surface + smoothed
    delta = clamp(unbounded, BOUND_DOTS)
    n_clamped = int(np.count_nonzero(
        np.hypot(unbounded[..., 0], unbounded[..., 1]) > BOUND_DOTS))
    rms = 0.0
    if used:
        left = offsets - delta[ty.astype(np.int64), tx.astype(np.int64)]
        rms = float(np.sqrt(np.average((left ** 2).sum(axis=1),
                                       weights=weights)))
    return (delta, support, surface, int(degree), rms, len(used),
            int(n_clamped))


# ------------------------------------------------------------- the fit

#: key -> (field, a STRONG reference to the run dir the key's `id()` was
#: taken from).  `frame._certs_token` hardened the same hazard the same
#: way: a dead object's id is reused, so a memo that keys on `id(x)`
#: without holding `x` can hand a second run the first run's field.  The
#: held object is one `Path`, not the `RunInputs`, so nothing heavy is
#: pinned.
#: The value is (field, run_dir, pass_token): the field, the object
#: whose id the key carries, and WHICH PASS filled the entry (M2).
_MEMO: dict[tuple, tuple[PageField, Any, Any]] = {}
_MEMO_ORDER: list[tuple] = []
_MEMO_LOCK = threading.Lock()
_KEY_LOCKS: dict[tuple, threading.Lock] = {}

#: Per-lane reads any number of CONCURRENT pooled fits may have in
#: flight at once, together.
#:
#: `fixedpoint` hands every fit the PASS's own worker count (A2's
#: wiring) and one fit can be in flight per (page, stream) — six on a
#: duplex colour sheet — so without a shared bound a run would hold
#: `6 x workers` crops on a machine sized for `workers`.  The pool is
#: created at first use from that same worker count and shared from then
#: on, which is the right shape rather than a smaller per-fit number: a
#: fit that is ALONE still reads at the pass's full width — the case the
#: wiring exists for, one key blocking every other worker on the first
#: `field2` arm — while concurrent fits divide the width instead of
#: multiplying it.  A blocked thread holds no crop, so what this bounds
#: is memory and live CPU, not the thread count; and it cannot move a
#: number, since the pooling is order-free and `executor.map` returns in
#: lane order either way.
_READ_SLOTS: threading.BoundedSemaphore | None = None
_READ_SLOTS_LOCK = threading.Lock()


def read_slots(workers: int) -> threading.BoundedSemaphore:
    """The process-wide pool of in-flight per-lane reads (see above)."""
    global _READ_SLOTS
    with _READ_SLOTS_LOCK:
        if _READ_SLOTS is None:
            _READ_SLOTS = threading.BoundedSemaphore(max(1, int(workers)))
        return _READ_SLOTS


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
    for it once instead of 300 times — and that fit excludes no tile,
    where a per-target fit excludes the target's own (`arms.lane_mix`'s
    memo key carries the exclusion).  Under the certificate-anchored fit
    this module carried until 2026-09-12 that was a DECLARED DEVIATION:
    for the ~0.6% of tiles that fell in the 12-tile sample, their own
    certificate reached the SPECTRAL fit (never the labels —
    `known_frame` always excluded the target key).  Every caller now
    passes ``NO_CERTS``, so the deviation cannot arise: there is no
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


def _detail(records: Sequence[TileOffset], n_used: int, degree: int,
            delta: np.ndarray, support: np.ndarray, bandwidth_tiles: float,
            unmix_mode: str, halo: int, seed: int, n_clamped: int) -> dict:
    # A clamped tile sits exactly at the bound; the ones under support
    # are the ones an arm can read, and the two counts answer different
    # questions (the polynomial ran off the evidence vs. the field the
    # arms sample was bounded).
    at_bound = np.hypot(delta[..., 0], delta[..., 1]) >= (
        BOUND_DOTS * (1.0 - 1e-9))
    clamped_supported = int(np.count_nonzero(at_bound & (support > 0.0)))
    # The rank of the design the ladder's degree actually solved: the
    # count rule can clear `n_terms` on observations that identify far
    # fewer of them (review §5.3), and a min-norm solution hides it.
    used = live_records(records)
    design_rank = 0
    if used:
        design_rank = int(np.linalg.matrix_rank(_design(
            (int(delta.shape[0]), int(delta.shape[1])),
            np.asarray([item.ty for item in used], np.float64),
            np.asarray([item.tx for item in used], np.float64), int(degree))))
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
        "n_terms": n_terms_of(int(degree)),
        "design_rank": design_rank,
        "bandwidth_tiles": float(bandwidth_tiles),
        "unmix_mode": str(unmix_mode),
        "halo_cells": int(halo),
        "seed": int(seed),
        "support_fraction": float(np.mean(support > 0.0)),
        "curvature_scale_nats": CURVATURE_SCALE_NATS,
        # the bound, and where it bit (A2): field2's own rule, so the
        # number it applied travels with the count of tiles it moved.
        "bound_dots": float(BOUND_DOTS),
        "clamped_tiles": int(n_clamped),
        "clamped_supported_tiles": clamped_supported,
    }


# ------------------------------------------------------- the pooled fit

def tile_sample_key(tiles: Any) -> Any:
    """`tiles` as the memo key spells it: None, an int, or a sorted tuple.

    One spelling, so a reader that asks whether a held fit is ITS fit
    (`passfiles.field2_product`) compares the same normalisation the key
    was built with.
    """
    if tiles is None:
        return None
    if isinstance(tiles, (int, np.integer)):
        return int(tiles)
    return tuple(sorted((int(ty), int(tx)) for ty, tx in tiles))


class PooledKey(NamedTuple):
    """The pooled memo's key, spelled (F12, 2026-09-13).

    It was an anonymous tuple, and a reader that wanted the seed a field
    was FITTED under had to index into it.  A `NamedTuple` is still a
    tuple — same hash, same equality, so nothing about the memo moves —
    and `fitted_pooled_fields` can now hand the key back beside the
    field, which is how a product says whose measurement it is
    publishing rather than stamping the current configuration on
    whatever the process cache holds.
    """

    kind: str
    run_dir_id: int
    run_dir: str
    format_ref: str
    page: int
    stream_id: str
    anchors: str
    lane_ids: tuple
    tile_sample: Any
    seed: int
    unmix_mode: str
    halo_cells: int
    bandwidth_tiles: float
    pool: str
    token: Any

    def fit(self) -> dict:
        """The parts that say WHICH FIT this is — the seed and the knobs
        that change the arithmetic, in the product's own spelling.

        SIX of the fifteen fields were compared until 2026-09-13 (M2),
        and the two missing ones were the anchor set and the LANE SET.
        Both change the arithmetic — `anchors` decides what the reads
        are taken over, and a field pooled over four lanes is not the
        field pooled over one — so a held fit could match on the six and
        still be a different measurement.  What stays out is the run,
        the format, the page and the stream: those are not the fit, they
        are WHERE it is, and the caller matched on them before it got
        here (`fitted_pooled_fields` filters by run dir, the product
        keys by page and plane).
        """
        return {"seed": int(self.seed),
                "anchors": str(self.anchors),
                "lane_ids": self.lane_ids,
                "tile_sample": self.tile_sample,
                "unmix_mode": str(self.unmix_mode),
                "halo_cells": int(self.halo_cells),
                "bandwidth_tiles": float(self.bandwidth_tiles),
                "pool": str(self.pool)}


def _pooled_memo_key(inputs: RunInputs, stream_id: str, page: int,
                     anchors: str, lane_ids: Sequence[Any], tiles: Any,
                     seed: int, unmix_mode: str, halo: int,
                     bandwidth_tiles: float, pool: str) -> PooledKey:
    """The pooled fit's key — WITHOUT a certificate token for furniture.

    A furniture-only fit is a pure function of the paper and the format:
    `known_frame` is called with `NO_CERTS`, so no certificate reaches
    the labels OR the mixing fit, and the field a generation computes is
    bit-identical to the one every other generation would.  Putting the
    certificate token in the key would therefore not protect anything —
    it would only refit the whole page every time the cascade minted a
    tile, which is exactly the cost this fit exists to remove.

    The token slot survives, always None, for the anchor set that is
    gone: it kept two certificate mappings (a `--withhold` control
    against the full set, DESIGN §8) out of one entry when a fit could
    read certificates, and it is the one thing in this key that would
    have to come back if one ever does again.

    Everything else in the key is something that changes the arithmetic:
    the run, the format, the page, the stream, the lane SET, the tile
    sample, the seed, the unmix mode, the halo, the bandwidth and the
    pooling rule.
    """
    sample = tile_sample_key(tiles)
    token = None
    return PooledKey(
        "pooled", id(inputs.run_dir), str(inputs.run_dir),
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
                          memoise: bool = True,
                          pass_token: Any = None) -> PageField:
    """ONE per-plane field for a PRINTED PAGE, pooled over its lanes.

    RULING (Germano, 2026-09-03 late).  The per-plane registration field
    is a property of the printed page: it is invariant across rungs and
    across captures of the same sheet (measured on sheet H — three
    captures agreed to 0.065 dots), so there is one field to fit, not one
    per lane per generation.  Fitted from FURNITURE anchors only it is
    also invariant across cascade generations and blind by construction.

    Every lane of the page contributes the per-tile blind offsets
    :func:`_one_tile` measures, over the SAME tile sample (drawn from the
    union of the lanes' coverage), and they are pooled per tile by
    :func:`pool_tile` before the ONE surface + support-normalised
    residual is fitted with the existing machinery.  Offsets need no
    conversion: they are page-frame by construction (DESIGN §4.4 —
    `sample.read_rgb` shifts through ``level_terms[:, :2]``, without the
    placement's rotation), which is why lanes whose placements differ in
    `rot_k` can be pooled at all.

    `lanes` defaults to every lane with a placement on the page.
    `anchors` is `furniture` and nothing else since 2026-09-12 (A2), and
    `certs` is therefore ignored — `NO_CERTS` is what the reads get, so a
    caller that still holds a certificate mapping may pass it and the
    fit stays certificate-free.  `tiles` is None for every covered tile,
    an int for a deterministic subsample, or an explicit iterable.
    `workers` threads the per-LANE reads; the result does not depend on
    it (the pooling is order-free and the lanes are visited in lane-id
    order).

    `pass_token` is WHO FITTED THIS, stamped on the memo entry and not
    on the key (M2, 2026-09-13): the memo outlives a pass, so a later
    pass that finds a held field has to be able to tell "I fitted this"
    from "somebody did".  Off the key because it must not fragment the
    memo — reuse across passes is the point of it — and a hit does NOT
    restamp: the entry keeps the identity of the pass that FILLED it.
    """
    stream_id = str(stream)
    plane = PLANE_OF[stream_id]
    page = int(page)
    if anchors != ANCHORS_FURNITURE:
        raise ValueError(f"unknown anchor set {anchors!r}; "
                         f"{(ANCHORS_FURNITURE,)}")
    certs = NO_CERTS
    pool_lanes = tuple(lanes_for_page(inputs, page) if lanes is None
                       else lanes)
    if not pool_lanes:
        raise ValueError(f"no lane has a placement on page {page}")
    halo = int(arms_mod.HALO_CELLS[stream_id] if halo_cells is None
               else halo_cells)
    key = _pooled_memo_key(inputs, stream_id, page, anchors,
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
                _MEMO[key] = (built, inputs.run_dir, pass_token)
                _MEMO_ORDER.append(key)
                while len(_MEMO_ORDER) > MEMO_MAX:
                    _MEMO.pop(_MEMO_ORDER.pop(0), None)
                _KEY_LOCKS.pop(key, None)
        return built


def records_by_lane(inputs: RunInputs, certs: Mapping[Key, Any],
                    pool_lanes: Sequence[Lane], stream_id: str, page: int,
                    tiles: Any, seed: int, halo: int, unmix_mode: str,
                    workers: int = 1,
                    ) -> dict[Any, tuple[TileOffset, ...]]:
    """The pooled fit's RAW evidence, KEPT BY LANE: lane id -> records.

    One read per (lane, tile) over the SAME tile sample for every lane,
    drawn from the union of their coverage, so that pooling at a tile is
    over lanes rather than over whichever tiles each lane happened to
    draw.  The lanes are visited in the order given and the dict keeps
    that order, so a threaded call and a serial one build identical
    structures.  `workers` threads them, under the process-wide bound
    :func:`read_slots` puts on reads IN FLIGHT across concurrent fits.

    The lane axis SURVIVES here because two readers need it and neither
    may pay for the reads a second time: :func:`pooled_records` folds it
    away for the fit, and the record's lane-to-lane agreement by footing
    (PAGE-FIELD-PLAN A4 — does the pooled furniture fit reproduce the
    cross-footing inversion `lane_gauge` measured?) needs each lane's own
    field, which is this dict one lane at a time through
    :func:`by_tile_from`.
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
        slots = read_slots(workers)

        def guarded(lane: Lane) -> tuple[TileOffset, ...]:
            with slots:                     # the shared bound, see above
                return read(lane)

        with ThreadPoolExecutor(max_workers=int(workers)) as executor:
            per_lane = list(executor.map(guarded, pool_lanes))
    else:
        per_lane = [read(lane) for lane in pool_lanes]
    return {lane.lane_id: tuple(records)
            for lane, records in zip(pool_lanes, per_lane)}


def by_tile_from(per_lane: Mapping[Any, Sequence[TileOffset]],
                 ) -> dict[tuple[int, int], list[TileOffset]]:
    """Lane-keyed records -> tile -> one record per lane, in lane order."""
    by_tile: dict[tuple[int, int], list[TileOffset]] = {}
    for records in per_lane.values():
        for item in records:
            by_tile.setdefault((int(item.ty), int(item.tx)), []).append(item)
    return by_tile


def pooled_records(inputs: RunInputs, certs: Mapping[Key, Any],
                   pool_lanes: Sequence[Lane], stream_id: str, page: int,
                   tiles: Any, seed: int, halo: int, unmix_mode: str,
                   workers: int = 1,
                   ) -> dict[tuple[int, int], list[TileOffset]]:
    """The pooled fit's RAW evidence: tile -> one record per lane.

    Split out from the fit so a caller can pool the SAME reads two ways
    (the record compares `wmedian` against `wmean`) without paying for
    the reads twice.
    """
    return by_tile_from(records_by_lane(
        inputs, certs, pool_lanes, stream_id, page, tiles, seed, halo,
        unmix_mode, workers))


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
    delta, support, surface, degree, rms, n_used, n_clamped = build_field(
        records, tiles_yx, bandwidth_tiles)
    n_lanes = np.zeros(tiles_yx, np.int64)
    for item in records:
        n_lanes[int(item.ty), int(item.tx)] = int(item.n_lanes)
    ids = tuple((str(one[0]), int(one[1])) for one in lane_ids)
    detail = _detail(records, n_used, degree, delta, support,
                     bandwidth_tiles, unmix_mode, halo, seed, n_clamped)
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
    """The field a `field2` arm should use, from the knobs.

    `anchors` is the ARM's choice, not a knob, and every `field2` arm
    makes the same one since 2026-09-12 (A2): the POOLED FURNITURE
    field, one fit per page-plane, shared by every lane and every
    generation.

    `knobs["page_field2"]` may be a `PageField` (use it), or the DRIVER's
    own table of pre-fitted fields keyed by ``(page, stream)``, or
    absent, in which case the field is fitted here and memoised, the way
    `arms.page_context` fits the page context on first use.  A caller
    that wants no fitting passes ``page_field2_fit=False``.

    ``knobs["field2_pass_token"]`` is the pass's own identity, which
    `fixedpoint._knobs_for` puts there and which rides onto the memo
    entry any fit made here fills (M2).
    """
    page = _page_of(lane) if page is None else int(page)
    standing = knobs.get("page_field2")
    if isinstance(standing, PageField):
        return standing
    if isinstance(standing, Mapping):
        # A table is the DRIVER's own; an entry missing from it is a
        # deliberate "not for this one", not an invitation to fit a field
        # behind the driver's back.
        found = standing.get((int(page), str(stream)))
        return found if isinstance(found, PageField) else None
    if not bool(knobs.get("page_field2_fit", True)):
        return None
    return fit_pooled_page_field(
        inputs, str(stream), int(page), lanes=knobs.get("field2_lanes"),
        anchors=anchors,
        tiles=knobs.get("field2_pooled_tiles", POOLED_FIT_TILES_DEFAULT),
        seed=int(knobs.get("seed", 0)),
        halo_cells=knobs.get("halo_cells"),
        unmix_mode=str(knobs.get("field2_unmix_mode", "subtract")),
        bandwidth_tiles=float(knobs.get("field2_bandwidth_tiles",
                                        BANDWIDTH_TILES)),
        pool=str(knobs.get("field2_pool", POOL_WMEDIAN)),
        workers=int(knobs.get("field2_fit_workers", 1)),
        pass_token=knobs.get("field2_pass_token"))


class Fitted(NamedTuple):
    """One memo entry as a reader sees it (M2, 2026-09-13).

    `pass_token` is the identity of the pass that FILLED the entry, not
    of whoever last read it: a reader asks "is this mine" by comparing
    its own token, and a held field that answers no is somebody else's
    measurement however well its knobs match.
    """

    field: PageField
    key: PooledKey
    pass_token: Any


def fitted_pooled_fields(inputs: RunInputs) -> dict[
        tuple[int, int], tuple[Fitted, ...]]:
    """Every pooled field THIS `inputs` fitted, by (page, plane).

    The memo IS the record of a pass's own fits, so reading it back is
    how a run reports its blind cross-check without fitting anything new
    (PAGE-FIELD-PLAN A2, the in-run `field2.json`).  What fills it is
    :func:`fit_pooled_page_field`, which `field_for` calls once per
    (page, stream) when the knobs leave it to fit; a pass whose knobs
    hand in a `PageField` or the DRIVER's own table, or that says
    `page_field2_fit=False`, fills nothing and this is empty — an empty
    result means "no fit was made HERE", never "no field was used".

    THE KEY IS NARROWER THAN THE MEMO'S, SO THE KEY COMES BACK TOO.  A
    memo key carries the knobs that change the arithmetic (seed, lane
    set, unmix mode, bandwidth, pool) as well as the page and stream, so
    more than one entry can stand for one (page, plane) — which no ladder
    spells today, one knob bag per pass, but a library caller can, and
    the sweeps do.  Every one of them is returned, in memo order, as a
    :class:`Fitted` — the field, ITS `PooledKey` (F12, 2026-09-13) and
    the token of the pass that FILLED the entry (M2): the memo outlives
    a pass and an entry a pass never asked for is not that pass's
    measurement, so the caller has to be able to tell them apart rather
    than stamp its own configuration on whatever is held.  The key says
    what the fit WAS, the token says whose it is, and the two answer
    different halves of that: matching knobs with another pass's token
    is exactly the case the key alone could not name.

    The filter is `id(inputs.run_dir)`, which is what the memo key uses:
    two `RunInputs` over the same PATH are two runs, and the memo holds
    a strong reference to the object it keyed on, so the id it compares
    cannot have been recycled.  An entry the queue evicted (`MEMO_MAX`)
    is simply absent — this says what the memo still holds, never what a
    fit would have been.
    """
    want = id(inputs.run_dir)
    with _MEMO_LOCK:
        held = list(_MEMO.items())
    out: dict[tuple[int, int], tuple[Fitted, ...]] = {}
    for key, (field, run_dir, pass_token) in held:
        if id(run_dir) != want:
            continue
        where = (int(field.page), int(field.plane))
        out[where] = out.get(where, ()) + (Fitted(field, key, pass_token),)
    return out


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
        "plane": int(field.plane),
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

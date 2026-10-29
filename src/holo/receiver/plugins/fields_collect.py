"""The `fields.collect` row: one capture's measurements of one page's
per-plane registration.

Subject is the CAPTURE-PAGE.  A page field is a fact about the printed
face and about nothing else (docs/PAGE-FIELD-DESIGN.md §2.2), so the
capture is not an axis of the answer — it is an axis of the EVIDENCE,
and this row is where one capture's evidence is made.  The solve is a
separate row over the page (`plugins/fields.py`).

What this row publishes is RAW (design §2.5, W8 R-C): one row per
(tile, plane), the displacement of that plane's ink against the pose it
was measured through, both axes flagged as measured, a weight and the
template source that paid for it.  NOTHING is subtracted — the gauge is
a constraint on the page's two free fields and each window's own pose
error is a parameter of the solve, so neither belongs here.  Retired
2026-09-08 with the wave that made that true: `common_mode`, its
`gauge_covered` companion and W7's R1 refusal of an ungauged Y row (the
row keeps its information now that the missing quantity is NAMED
instead of subtracted); `certified_whole` and the all-three-plane
intersection that made a certified C wait for M and Y (review F3); and
`pose_work`, the collection ordinal that a fresh placement could not
move (review F4).

The template is chosen PER (TILE, PLANE) — that plane's own certificate
if it has one, its furniture otherwise — and measured by the one
primitive in `plugins/field_tiers.py`.  EVERY offset is in printed DOTS
ALONG THE PAGE AXES: the probe grid is displaced through the window's
PAGE-cell -> pixel 2x2 (`lib/page_map`), so what comes back is a
page-axis measurement by construction, whatever orientation the scrap
was placed at, and a confetti page whose scraps mix all four rotations
pools into one field (I2) with no frame to convert afterwards.

The ORDINAL is the store's evidence revision for this capture-page
(I12), and the revision is BOOKKEEPING: ten certificates between two
admissions of this row buy ONE collection, and that collection
re-measures only the (tile, plane)s whose inputs moved — the rest are
carried under the memo, which is what makes a page certifying in a
hundred batches cost one measurement per tile rather than a hundred.  A
page whose last window has left publishes an EMPTY table under a new
revision: removal is a state transition, not the absence of work
(review F5).

Nothing here mints a certificate, touches a decoder or writes a field.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..data import (Certificate, FieldObservations, JobResult, Placement,
                    PlaneRaster, WindowId)
from ..descriptor import (
    FactKey,
    Job,
    KEY_LANE_POSES,
    KEY_PAGE_CERTS,
    PluginDescriptor,
    RETIRE_PAGE_DONE,
    Subject,
)
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib import page_map, plane_field
from ..lib.geometry import TILE_CELLS
from . import color_region, field_tiers
from . import color_region_anchor as anchor

PLUGIN: str = "fields.collect"
STAGE_COLLECT: str = "collect"
#: The ladder slot the per-lane fitter held.  Collecting is where the
#: work is — a page's worth of correlations against a page's worth of
#: rasters — and it re-prices by its own fire ordinal because a growing
#: certified frontier re-arms it again and again.
COLLECT_COST: int = 180
PRICES: tuple[tuple[str, int], ...] = ((STAGE_COLLECT, COLLECT_COST),)

N_PLANES: int = 3

CollectSubject = tuple[str, int]
Projection = tuple[np.ndarray, np.ndarray]


@dataclass(frozen=True)
class LaneWindows:
    """One decimation level's placed windows on the subject's page.

    `ppc` orders the levels: the same photons read twice never add
    weight, so each tile is measured at the FINEST level that covers it
    (I4) and the coarser levels' windows simply own fewer tiles.
    """

    level_index: int
    ppc: float
    windows: tuple[color_region.RegionWindow, ...]
    window_ids: tuple[WindowId, ...]
    pose_generation: tuple[int, ...]
    planes: tuple[PlaneRaster, ...]


@dataclass
class Rows:
    """The observation table under construction, as growable columns."""

    tile_code: list[int]
    plane: list[int]
    delta_dots_xy: list[np.ndarray]
    measured_xy: list[np.ndarray]
    weight: list[float]
    source: list[int]

    @classmethod
    def empty(cls) -> "Rows":
        return cls([], [], [], [], [], [])

    def add(self, tile_code: int, plane: int,
            measured: field_tiers.Measured, source: int) -> None:
        self.tile_code.append(int(tile_code))
        self.plane.append(int(plane))
        self.delta_dots_xy.append(np.asarray(measured.delta_dots_xy,
                                             np.float64))
        self.measured_xy.append(np.asarray(measured.measured_xy, bool))
        self.weight.append(float(measured.quality))
        self.source.append(int(source))

    def __len__(self) -> int:
        return len(self.tile_code)


def window_crop(window: color_region.RegionWindow, planes: anchor.Planes,
                pitch_px: float,
                divisor: float) -> tuple[int, int, np.ndarray] | None:
    """The window's filtered pixels, once, for all three planes.

    The pitch and the divisor are the CALLER's: `plugins/swim.py` fits a
    tile's covering windows against one another and pools both over
    them, which is that row's business and not this one's.
    """
    y0, x0, raw = anchor.native_crop(
        planes,
        anchor.window_points(window.shape_yx_cells, window.affine),
        anchor.window_halo(pitch_px))
    if raw.size == 0:
        return None
    return y0, x0, anchor.filtered_rgb(raw, pitch_px, divisor)


def owner_crop(window: color_region.RegionWindow,
               planes: anchor.Planes) -> tuple[int, int, np.ndarray] | None:
    """The owning window's filtered pixels, derived from the owner alone.

    I9's premise is that a measurement of this row is a function of ONE
    window's pose, raster and template, so its preprocessing is a
    function of that window too: its own pitch sets the halo and the
    0.7-cell aperture, and its own crop sets the divisor.  Nothing about
    a neighbour reaches it.

    Which half of that mattered, measured 2026-09-12 through
    `collect_job`: the PITCH did — a non-owning window at 4.998 px/cell
    dropped the owner's aperture from 4 px to 3 px and moved its
    measurements by up to 0.67 dots (review R4) — and the DIVISOR moves
    a row by ~1e-7 dots at most, because the NCC is scale-invariant: the
    same page collected as reflectance and as the same raster x255 agrees
    on all 12 rows to 4e-8 dots and 4e-9 of quality, the float32 filter's
    rounding over `weighted_ncc`'s own 1e-9 epsilons.  Only the aperture
    INTEGER can move a row: the halo grows with the pitch too, but it
    always exceeds the aperture's reach from any sampled site, so no
    halo change reaches a sampled value.
    """
    y0, x0, raw = anchor.native_crop(
        planes,
        anchor.window_points(window.shape_yx_cells, window.affine),
        anchor.window_halo(window.pitch_px))
    if raw.size == 0:
        return None
    return y0, x0, anchor.filtered_rgb(
        raw, window.pitch_px, anchor.native_divisor((float(np.max(raw)),)))


def _sampler(crop, points_yx: np.ndarray, page_linear: np.ndarray,
             plane: int, cell_dots: int):
    """Sample one plane at some page cells, displaced in page-axis DOTS.

    The read side's own mapping (`lib/page_map`), so the probe is
    displaced along the PAGE axes exactly as the field it is measuring
    will be applied, and the primitive speaks the one unit.
    """
    y0, x0, filtered = crop

    def sample(offsets_dots_xy: np.ndarray) -> np.ndarray:
        offsets = np.atleast_2d(np.asarray(offsets_dots_xy, np.float64))
        moved = page_map.raster_point_grid(points_yx, page_linear, offsets,
                                           cell_dots)
        values = anchor.sample_plane(filtered, y0, x0,
                                     moved.reshape(-1, 2), plane)
        return values.reshape(offsets.shape[0], points_yx.shape[0])

    return sample


def tile_rows(page_cells_yx: np.ndarray,
              tiles_yx: tuple[int, int]) -> dict[int, np.ndarray]:
    """A window's cell indices, grouped by the page tile they sit in."""
    codes = plane_field.tile_codes(page_cells_yx, tiles_yx, TILE_CELLS)
    return {int(code): np.flatnonzero(codes == code)
            for code in np.unique(codes)}


def assign_tiles(lanes: tuple[LaneWindows, ...],
                 grouped: tuple[tuple[dict[int, np.ndarray], ...], ...],
                 ) -> dict[int, tuple[int, int]]:
    """Which window measures which tile: one observation per (tile, plane).

    The finest level that covers the tile wins, because levels are the
    same photons and never add weight (I4, the multi-scan law applied to
    registration); within one level the window that holds the most of
    that tile wins, because it is the one with the most to correlate.
    """
    owner: dict[int, tuple[int, int]] = {}
    best: dict[int, tuple[float, int]] = {}
    for lane_index, lane in enumerate(lanes):
        for window_index, rows in enumerate(grouped[lane_index]):
            for code, indices in rows.items():
                score = (lane.ppc, int(indices.size))
                if code not in best or score > best[code]:
                    best[code] = score
                    owner[code] = (lane_index, window_index)
    return owner


def tile_template(row: FormatRow, geometry: SiteGeometry, page: int,
                  code: int, plane: int, certificates: dict,
                  memo: dict) -> field_tiers.Template | None:
    """The template one (tile, plane) is measured against, or None.

    That plane's own certificate if it has one — its whole printed tile
    — and its furniture otherwise.  Per (tile, PLANE) and never per
    tile: a CMY8 certificate labels one stream, so a certified C
    correlates 4,096 cells while M and Y are still on ~120 sites each
    (design §2.5, review F3).  A plane with neither reads unknown (I13).
    """
    tile_yx = divmod(int(code), int(row.tiles_yx[1]))
    certified = field_tiers.certified_template(
        row, geometry, page, tile_yx, plane, certificates, memo)
    if certified is not None:
        return certified
    return field_tiers.furniture_template(row, geometry, page, tile_yx,
                                          plane)


def cell_lookup(page_cells_yx: np.ndarray,
                tiles_x: int) -> tuple[np.ndarray, np.ndarray]:
    """A window's page cells, sorted, so a template can find its own.

    A template names PAGE cells and the window names the pixels: this is
    where the two meet.  Built once per window and searched per (tile,
    plane), because a template that reaches past the window's edge — a
    cut scrap, a page boundary — contributes the cells that are there
    and no others.
    """
    cells = np.asarray(page_cells_yx, np.int64)
    keys = cells[:, 0] * (int(tiles_x) * TILE_CELLS) + cells[:, 1]
    order = np.argsort(keys)
    return keys[order], order


def template_at(lookup: tuple[np.ndarray, np.ndarray],
                template: field_tiers.Template,
                tiles_x: int) -> tuple[np.ndarray, np.ndarray]:
    """The window rows a template covers, and the template rows they are.

    Both index arrays, in the template's own order: the caller samples
    at `points[window_rows]` and correlates against `bits[kept]`.
    """
    keys, order = lookup
    cells = np.asarray(template.page_cells_yx, np.int64)
    wanted = cells[:, 0] * (int(tiles_x) * TILE_CELLS) + cells[:, 1]
    position = np.clip(np.searchsorted(keys, wanted), 0,
                       max(keys.size - 1, 0))
    kept = np.flatnonzero(keys.size and keys[position] == wanted)
    return order[position[kept]], kept


def standing_row(standing: FieldObservations | None, code: int, plane: int,
                 wid: WindowId, generation: int,
                 source: int) -> np.ndarray | None:
    """The row of a standing collection this one may copy (I9).

    A measurement is a function of the pose it was taken through and of
    the template it was taken with.  If neither has moved, re-measuring
    would return the same number, so the row is carried over.

    The pose is named by its WINDOW and by that window's generation,
    never by the generation alone: every freshly placed window stands at
    generation 0, so a tile handed from a coarse window to a finer one
    is a pose that moved and a generation test cannot see it (measured
    2026-09-07: a coarse lane's +1.06 dots carried into a collection
    whose owning lane reads -0.95).  The source is per (tile, PLANE),
    which is what makes a tile whose C has just certified re-measure C
    and carry M and Y.
    """
    if standing is None:
        return None
    rows = np.flatnonzero(
        (np.asarray(standing.tile_code, np.int64) == int(code))
        & (np.asarray(standing.plane, np.int64) == int(plane))
        & (np.asarray(standing.source, np.int64) == int(source)))
    if not rows.size:
        return None
    window = int(np.asarray(standing.window, np.int64)[rows[0]])
    if standing.window_ids[window] != wid:
        return None
    if int(np.asarray(standing.window_generation,
                      np.int64)[window]) != int(generation):
        return None
    return rows


@dataclass
class Table:
    """The fact's columns under construction, one window at a time.

    A window's rows carry its index, which is what lets the next
    collection find the pose a row was measured through
    (`standing_row`) and what tells the solve which rows share a
    nuisance translation.
    """

    tile_code: list[np.ndarray]
    plane: list[np.ndarray]
    delta_dots_xy: list[np.ndarray]
    measured_xy: list[np.ndarray]
    weight: list[np.ndarray]
    source: list[np.ndarray]
    window: list[np.ndarray]
    window_ids: list[WindowId]
    window_generation: list[int]

    @classmethod
    def empty(cls) -> "Table":
        return cls([], [], [], [], [], [], [], [], [])

    def add_window(self, wid: WindowId, generation: int,
                   columns: tuple[np.ndarray, ...]) -> None:
        tile_code, plane, delta, measured, weight, source = columns
        if not tile_code.size:
            return
        self.window.append(np.full(tile_code.size, len(self.window_ids),
                                   np.int64))
        self.window_ids.append(wid)
        self.window_generation.append(int(generation))
        self.tile_code.append(tile_code)
        self.plane.append(plane)
        self.delta_dots_xy.append(delta)
        self.measured_xy.append(measured)
        self.weight.append(weight)
        self.source.append(source)


def _column(parts: list[np.ndarray], dtype, width: int = 0) -> np.ndarray:
    return (np.zeros((0, width) if width else (0,), dtype) if not parts
            else np.concatenate(parts).astype(dtype))


def _carried(standing: FieldObservations,
             rows: np.ndarray) -> tuple[np.ndarray, ...]:
    return (np.asarray(standing.tile_code, np.int64)[rows],
            np.asarray(standing.plane, np.int64)[rows],
            np.asarray(standing.delta_dots_xy, np.float64)[rows],
            np.asarray(standing.measured_xy, bool)[rows],
            np.asarray(standing.weight, np.float64)[rows],
            np.asarray(standing.source, np.int64)[rows])


def _made(made: Rows) -> tuple[np.ndarray, ...]:
    return (np.asarray(made.tile_code, np.int64),
            np.asarray(made.plane, np.int64),
            np.stack(made.delta_dots_xy),
            np.stack(made.measured_xy),
            np.asarray(made.weight, np.float64),
            np.asarray(made.source, np.int64))


def restricted(template: field_tiers.Template,
               kept: np.ndarray) -> field_tiers.Template:
    """The part of a template that lies inside one window's cells.

    A cut scrap and a page edge both truncate a template, and what a
    truncated one measures is what the primitive's own site floors then
    decide (design §2.5, the per-class floor on cut scraps).
    """
    return field_tiers.Template(
        page_cells_yx=np.asarray(template.page_cells_yx)[kept],
        bits=np.asarray(template.bits)[kept],
        source=template.source, radius_dots=template.radius_dots,
        weights=(None if template.weights is None
                 else np.asarray(template.weights)[kept]))


def measure_window(row: FormatRow, window: color_region.RegionWindow, crop,
                   lookup: tuple[np.ndarray, np.ndarray],
                   fresh: tuple[tuple[int, int, field_tiers.Template], ...],
                   cell_dots: int) -> Rows:
    """Every (tile, plane) this window owes, through the one primitive."""
    out = Rows.empty()
    points = np.asarray(window.scan_points_yx, np.float64)
    for code, plane, template in fresh:
        window_rows, kept = template_at(lookup, template, row.tiles_yx[1])
        part = restricted(template, kept)
        measured = field_tiers.measure(
            part,
            _sampler(crop, points[window_rows], window.page_linear, plane,
                     cell_dots),
            weights=part.weights)
        if measured is not None:
            out.add(code, plane, measured, template.source)
    return out


def collect_job(row: FormatRow, geometry: SiteGeometry, capture_id: str,
                page: int, lanes: tuple[LaneWindows, ...],
                certificates: dict, standing: FieldObservations | None,
                revision: int) -> JobResult:
    started = time.thread_time()
    cell_dots = color_region.cell_dots_of(row)
    memo: dict[tuple[int, int, int], Projection | None] = {}
    grouped = tuple(
        tuple(tile_rows(window.page_cells_yx, row.tiles_yx)
              for window in lane.windows)
        for lane in lanes)
    owner = assign_tiles(lanes, grouped)
    table = Table.empty()
    for lane_index, lane in enumerate(lanes):
        opened: anchor.Planes | None = None
        for window_index, window in enumerate(lane.windows):
            wid = lane.window_ids[window_index]
            generation = lane.pose_generation[window_index]
            mine = tuple(sorted(code for code, who in owner.items()
                                if who == (lane_index, window_index)))
            parts: list[tuple[np.ndarray, ...]] = []
            fresh: list[tuple[int, int, field_tiers.Template]] = []
            for code in mine:
                for plane in range(N_PLANES):
                    template = tile_template(row, geometry, page, code,
                                             plane, certificates, memo)
                    if template is None:
                        continue
                    kept = standing_row(standing, code, plane, wid,
                                        generation, template.source)
                    if kept is None:
                        fresh.append((code, plane, template))
                    else:
                        parts.append(_carried(standing, kept))
            if fresh:
                if opened is None:
                    opened = (lane.planes[0].open(), lane.planes[1].open(),
                              lane.planes[2].open())
                #: OWNER-LOCAL (R4).  color_region pools a region's pitch
                #: (score bit-exactness, 09-detect-calibrate-k.md:404) and
                #: divisor (one photometric scale, 10-colour-heads.md:414)
                #: over its heads; ONE window's row needs neither.
                crop = owner_crop(window, opened)
                # A window with no crop cannot measure anything, so what
                # it carries stands as it is.
                made = (Rows.empty() if crop is None else measure_window(
                    row, window, crop,
                    cell_lookup(window.page_cells_yx, row.tiles_yx[1]),
                    tuple(fresh), cell_dots))
                if len(made):
                    parts.append(_made(made))
            if parts:
                table.add_window(wid, generation, tuple(
                    np.concatenate([part[index] for part in parts])
                    for index in range(6)))
    fact = FieldObservations(
        capture_id=capture_id, page=int(page),
        tile_code=_column(table.tile_code, np.int64),
        plane=_column(table.plane, np.int64),
        delta_dots_xy=_column(table.delta_dots_xy, np.float64,
                              2).reshape(-1, 2),
        measured_xy=_column(table.measured_xy, bool, 2).reshape(-1, 2),
        weight=_column(table.weight, np.float64),
        source=_column(table.source, np.int64),
        window=_column(table.window, np.int64),
        window_ids=tuple(table.window_ids),
        window_generation=np.asarray(table.window_generation, np.int64),
        revision=int(revision))
    return JobResult((fact,), (), time.thread_time() - started)


def placed_on(store: object, capture_id: str, page: int) -> bool:
    """Has this capture a window on this page at any level?

    Asked on the engine thread for every capture on every certificate,
    so it asks the store for the count and never for the sorted list
    `lane_page_windows` builds.
    """
    capture = store.capture(capture_id)
    if capture is None:
        return False
    return any(store.lane_page_window_count(capture_id, int(level.index),
                                            int(page))
               for level in capture.levels)


def standing_of(store: object, capture_id: str,
                page: int) -> FieldObservations | None:
    return next((fact for fact in store.field_observations(int(page))
                 if fact.capture_id == capture_id), None)


def has_rows(standing: FieldObservations | None) -> bool:
    """Does a standing collection of this capture-page carry measurements?

    Asked beside `placed_on`, and only there: rows standing where no
    window of this capture is any more are work of their own kind —
    publish the emptiness under a new revision, so the page re-solves to
    the pose rather than keeping measurements taken through a window
    that has gone (F5).
    """
    return standing is not None and bool(
        np.asarray(standing.tile_code).size)


def prepare_collect(store: object, subject: Subject,
                    stage: str) -> Job | None:
    capture_id, page = subject
    capture = store.capture(capture_id)
    if capture is None:
        return None
    lanes: list[LaneWindows] = []
    for level in sorted(capture.levels, key=lambda le: (-le.ppc, le.index)):
        wids = store.lane_page_windows(capture_id, int(level.index),
                                       int(page))
        if not wids:
            continue
        lanes.append(LaneWindows(
            level_index=int(level.index), ppc=float(level.ppc),
            windows=tuple(color_region.region_window(store, wid)
                          for wid in wids),
            window_ids=tuple(wids),
            pose_generation=tuple(int(store.pose_generation(wid))
                                  for wid in wids),
            planes=store.rgb_planes((capture_id, int(level.index)))))
    standing = standing_of(store, capture_id, int(page))
    if not lanes and not has_rows(standing):
        return None
    row = store.row
    site_geometry = store.geometry
    certificates = store.certificates()
    revision = store.evidence_revision(capture_id, int(page))

    def job() -> JobResult:
        return collect_job(row, site_geometry, capture_id, int(page),
                           tuple(lanes), certificates, standing, revision)

    return job


def _collect_subjects(store: object,
                      fact: object) -> tuple[Subject, ...]:
    """A page's capture-pages, from a placement or from a certificate.

    K has one plane and no differential (`D_K = 0`, design §2.1), so the
    row is refused at the family and no worker is ever born on it.
    A PLACEMENT names its own capture; a CERTIFICATE names the page, and
    every capture with a placed window there now has more to measure.
    """
    if store.row.family is Family.K:
        return ()
    page = int(fact.page)
    if isinstance(fact, Placement):
        return ((str(fact.capture_id), page),)
    return tuple((capture_id, page) for capture_id in store.captures()
                 if placed_on(store, capture_id, page))


def _collect_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    capture_id, page = subject
    capture = store.capture(capture_id)
    levels = () if capture is None else capture.levels
    return ((KEY_PAGE_CERTS, int(page)),) + tuple(
        (KEY_LANE_POSES, capture_id, int(level.index), int(page))
        for level in levels)


def _collect_eligible(store: object, subject: Subject) -> bool:
    return (placed_on(store, subject[0], subject[1])
            or has_rows(standing_of(store, subject[0], subject[1])))


def _collect_stage(store: object, subject: Subject) -> str | None:
    return STAGE_COLLECT


def _collect_cost(store: object, subject: Subject, stage: str,
                  attempts: int, last_cost: int) -> int:
    """The fire ordinal, floored at one fire.

    A first fire is not free: it is the COLD full-page collection, the
    dearest one this row ever runs (13 of them on a sheet-H resume, one
    per capture), and `COLLECT_COST * 0` would price it under survey's 10
    and jump the whole ladder.
    """
    return COLLECT_COST * attempts if attempts else COLLECT_COST


def _collect_retire(store: object, subject: Subject) -> str | None:
    return RETIRE_PAGE_DONE if store.done_grid(subject[1]).all() else None


COLLECT_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="capture_page",
    born_by=(Placement, Certificate),
    subjects_of=_collect_subjects,
    reads=_collect_reads,
    eligible=_collect_eligible,
    stage=_collect_stage,
    cost=_collect_cost,
    retire=_collect_retire,
    prepare=prepare_collect,
    produces=(FieldObservations,),
    prices=PRICES,
)

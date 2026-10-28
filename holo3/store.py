from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import Callable

import numpy as np

from . import data
from .data import CertKey, DecodeRequest, LaneKey, RegionKey, WindowId
from .descriptor import (
    FactKey,
    KEY_COLOR_POP,
    KEY_COLOR_ROW,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_LANE_POSES,
    KEY_LATTICE_SEED,
    KEY_LIVE_PAGES,
    KEY_PAGE_CERTS,
    KEY_PLACE_STAGE,
    KEY_PLANE_FIELD,
    KEY_POOLED_CTX,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_REGION_CTX,
    KEY_REGION_PITCH,
    KEY_TILE,
    Subject,
)
from .format import identity, metadata
from .format.identity import FormatRow, SiteGeometry
from .plugins import (
    calibrate,
    color_region_head,
    place,
    place_sched,
    refine,
    tiles,
    words,
)


def _adopts(standing: object | None, fact: object,
            ordinal: Callable[[object], tuple]) -> bool:
    return standing is None or ordinal(fact) > ordinal(standing)


def _update_cover(forward: dict, inverse: dict, member: object,
                  new_keys: tuple) -> None:
    old_keys = inverse.get(member, ())
    if new_keys == old_keys:
        return
    for key in old_keys:
        standing = forward.get(key)
        if standing is None:
            continue
        standing.discard(member)
        if not standing:
            del forward[key]
    for key in new_keys:
        forward.setdefault(key, set()).add(member)
    inverse[member] = new_keys


class _Store:

    def __init__(self, request: DecodeRequest,
                 events: list[data.Event]) -> None:
        self._request = request
        self._events = events
        self.row: FormatRow = identity.resolve_format_ref(
            request.format_ref)
        self.geometry: SiteGeometry = identity.build_site_geometry(self.row)
        self.stream_index: dict[str, int] = {
            s.stream_id: i for i, s in enumerate(self.row.streams)}
        bound = (self.row.max_pages if request.max_pages is None
                 else int(request.max_pages))
        self.page_domain: tuple[int, ...] = tuple(range(bound))
        self.reference = words.ReferenceField(self.row)
        self.lookup = calibrate.build_site_lookup(self.geometry)
        self._captures: dict[str, data.Capture] = {}
        self._rasters: tuple[data.PlaneRaster, ...] = ()
        self._planes_by_lane: dict[LaneKey, dict[str, data.PlaneRaster]] = {}
        self._levels: dict[LaneKey, data.Level] = {}
        self._surveys: dict[str, data.CaptureSurvey] = {}
        self._frames: dict[RegionKey, place.RegionFrame] = {}
        self._plan_total: dict[LaneKey, int] = {}
        self._windows: dict[WindowId, data.Window] = {}
        self._ordinal_wid: dict[tuple[str, int, int], WindowId] = {}
        self._place_stages: dict[WindowId,
                                 place_sched.WindowState] = {}
        self._placements: dict[WindowId, data.Placement] = {}
        self._page_cells: dict[WindowId, np.ndarray] = {}
        self._pose_gen: dict[WindowId, int] = {}
        self._lattice_seeds: dict[RegionKey, data.LatticeSeed] = {}
        self._live_pages: set[int] = {0}
        self._lanes_on_page: dict[int, set[LaneKey]] = {}
        self._lane_poses: dict[tuple[str, int, int],
                               dict[WindowId, tuple[float, ...]]] = {}
        self._region_pitch: dict[RegionKey, float] = {}
        self._evidence: dict[WindowId, data.WindowEvidence] = {}
        self._region_ctx: dict[RegionKey, data.RegionCtx] = {}
        self._color_rows: dict[tuple[str, int, int, int],
                               data.ColorEvidenceRow] = {}
        self._color_pops: dict[tuple[str, int, int],
                               data.ColorCtxPopulation] = {}
        self._pop_lanes: dict[tuple[int, str],
                              set[tuple[str, int, int]]] = {}
        self._pooled_ctx: dict[tuple[int, str], data.PooledColorCtx] = {}
        self._plane_fields: dict[tuple[str, int, int, int],
                                 data.PlaneField] = {}
        self._tile_cover_k: dict[tiles.CoverKey, set[WindowId]] = {}
        self._tile_cover_color: dict[tiles.CoverKey,
                                     set[tiles.ColorRowKey]] = {}
        self._window_cover: dict[WindowId, tuple[tiles.CoverKey, ...]] = {}
        self._color_row_cover: dict[tiles.ColorRowKey,
                                    tuple[tiles.CoverKey, ...]] = {}
        self._certificates: dict[CertKey, data.Certificate] = {}
        self._equations: dict[int, int] = {}
        self._attempt_outcomes: dict[tuple[object, ...], str] = {}
        self._account: dict[str, list[float]] = {}
        self._done_grid_cache: dict[int, tuple[int, np.ndarray]] = {}
        self._done_cells_cache: dict[
            RegionKey, tuple[tuple[int, int, int], np.ndarray]] = {}
        self._placements_view: tuple[int, tuple[WindowId, ...]] = (0, ())
        self._windows_view: tuple[int, tuple[WindowId, ...]] = (0, ())
        self._cert_keys_view: tuple[int, tuple[CertKey, ...]] = (0, ())
        self._color_keys_view: tuple[
            int, tuple[tuple[str, int, int, int], ...]] = (0, ())
        self._evidences_view: tuple[int, tuple[WindowId, ...]] = (0, ())
        self._window_reach: dict[WindowId,
                                 tuple[tuple[int, int], ...]] = {}
        self._evidence_reach: dict[WindowId,
                                   tuple[tuple[int, int], ...]] = {}
        self._lane_page_wids: dict[tuple[str, int, int],
                                   set[WindowId]] = {}
        self._color_lane_assembled: dict[tuple[str, int, int],
                                         set[int]] = {}
        self._color_lane_head: dict[tuple[str, int, int],
                                    color_region_head.LaneHead] = {}
        self._color_lane_head_fits: dict[tuple[str, int, int],
                                         int] = {}
        self._pose_stamp: dict[tuple[str, int], tuple[int, int]] = {}

    def capture(self, capture_id: str) -> data.Capture | None:
        return self._captures.get(capture_id)

    def captures(self) -> tuple[str, ...]:
        return tuple(sorted(self._captures))

    def level(self, capture_id: str, level_index: int) -> data.Level:
        return self._levels[(capture_id, level_index)]

    def rasters(self, capture_id: str) -> tuple[data.PlaneRaster, ...]:
        return tuple(raster for raster in self._rasters
                     if raster.capture_id == capture_id)

    def lane_planes(self, lane: LaneKey) -> dict[str, data.PlaneRaster]:
        return self._planes_by_lane[lane]

    def sampling_planes(self,
                        lane: LaneKey) -> tuple[data.PlaneRaster, ...]:
        planes = self.lane_planes(lane)
        if len(planes) == 1:
            return (next(iter(planes.values())),)
        if "y" in planes:
            return (planes["y"],)
        return (planes["r"], planes["g"], planes["b"])

    def rgb_planes(self, lane: LaneKey) -> tuple[data.PlaneRaster,
                                                 data.PlaneRaster,
                                                 data.PlaneRaster]:
        planes = self.lane_planes(lane)
        return (planes["r"], planes["g"], planes["b"])

    def survey(self, capture_id: str) -> data.CaptureSurvey | None:
        return self._surveys.get(capture_id)

    def frame(self, key: RegionKey) -> place.RegionFrame | None:
        return self._frames.get(key)

    def plan_total(self, lane: LaneKey) -> int:
        return self._plan_total.get(lane, 0)

    def window(self, wid: WindowId) -> data.Window | None:
        return self._windows.get(wid)

    def windows(self) -> tuple[WindowId, ...]:
        if self._windows_view[0] != len(self._windows):
            self._windows_view = (len(self._windows),
                                  tuple(sorted(self._windows)))
        return self._windows_view[1]

    def window_by_ordinal(self, capture_id: str, level_index: int,
                          ordinal: int) -> WindowId:
        return self._ordinal_wid[(capture_id, level_index, ordinal)]

    def place_stage(self,
                    wid: WindowId) -> place_sched.WindowState | None:
        return self._place_stages.get(wid)

    def placement(self, wid: WindowId) -> data.Placement | None:
        return self._placements.get(wid)

    def placements(self) -> tuple[WindowId, ...]:
        if self._placements_view[0] != len(self._placements):
            self._placements_view = (len(self._placements),
                                     tuple(sorted(self._placements)))
        return self._placements_view[1]

    def lane_page_windows(self, capture_id: str, level_index: int,
                          page: int) -> tuple[WindowId, ...]:
        wids = self._lane_page_wids.get((capture_id, level_index, page))
        return () if wids is None else tuple(sorted(wids))

    def window_reach(self,
                     wid: WindowId) -> tuple[tuple[int, int], ...] | None:
        return self._window_reach.get(wid)

    def evidence_reach(self,
                       wid: WindowId) -> tuple[tuple[int, int], ...] | None:
        return self._evidence_reach.get(wid)

    def pose_generation(self, wid: WindowId) -> int:
        return self._pose_gen.get(wid, 0)

    def page_cells(self, wid: WindowId) -> np.ndarray | None:
        return self._page_cells.get(wid)

    def lattice_seed(self, key: RegionKey) -> data.LatticeSeed | None:
        return self._lattice_seeds.get(key)

    def live_pages(self) -> frozenset[int]:
        return frozenset(self._live_pages)

    def lanes_on_page(self, page: int) -> frozenset[LaneKey]:
        return frozenset(self._lanes_on_page.get(page, frozenset()))

    def region_pitch(self, key: RegionKey) -> float | None:
        return self._region_pitch.get(key)

    def evidence(self, wid: WindowId) -> data.WindowEvidence | None:
        return self._evidence.get(wid)

    def evidences(self) -> tuple[WindowId, ...]:
        if self._evidences_view[0] != len(self._evidence):
            self._evidences_view = (len(self._evidence),
                                    tuple(sorted(self._evidence)))
        return self._evidences_view[1]

    def region_ctx(self, key: RegionKey) -> data.RegionCtx | None:
        return self._region_ctx.get(key)

    def color_row(self, key: tuple[str, int, int, int],
                  ) -> data.ColorEvidenceRow | None:
        return self._color_rows.get(key)

    def color_row_keys(self) -> tuple[tuple[str, int, int, int], ...]:
        if self._color_keys_view[0] != len(self._color_rows):
            self._color_keys_view = (len(self._color_rows),
                                     tuple(sorted(self._color_rows)))
        return self._color_keys_view[1]

    def color_lane_head(self, lane_page: tuple[str, int, int],
                        ) -> color_region_head.LaneHead | None:
        return self._color_lane_head.get(lane_page)

    def color_lane_head_fits(self,
                             lane_page: tuple[str, int, int]) -> int:
        return self._color_lane_head_fits.get(lane_page, 0)

    def color_lane_debt(self, lane_page: tuple[str, int, int],
                        ) -> tuple[WindowId, ...]:
        assembled = self._color_lane_assembled.get(lane_page, ())
        return tuple(sorted(
            wid for wid in self._lane_page_wids.get(lane_page, ())
            if self._placements[wid].patch_ordinal not in assembled))

    def pooled_ctx_enabled(self) -> bool:
        return bool(self._request.pooled_color_context)

    def lane_rung(self, capture_id: str, level_index: int) -> str:
        return str(self._levels[(capture_id, level_index)].ppc)

    def pooled_ctx_key(self, capture_id: str, level_index: int,
                       page: int) -> tuple[int, str]:
        return (int(page), self.lane_rung(capture_id, level_index))

    def color_ctx_population(
        self, lane_page: tuple[str, int, int],
    ) -> data.ColorCtxPopulation | None:
        return self._color_pops.get(lane_page)

    def pooled_ctx_lanes(
        self, pooled_key: tuple[int, str],
    ) -> tuple[tuple[str, int, int], ...]:
        return tuple(sorted(self._pop_lanes.get(pooled_key, ())))

    def pooled_ctx_captures(self, pooled_key: tuple[int, str]) -> int:
        return len({lane[0] for lane in self._pop_lanes.get(pooled_key, ())})

    def pooled_color_ctx(
        self, pooled_key: tuple[int, str],
    ) -> data.PooledColorCtx | None:
        return self._pooled_ctx.get(pooled_key)

    def plane_fields_enabled(self) -> bool:
        return bool(self._request.plane_fields)

    def plane_field(self, key: tuple[str, int, int, int],
                    ) -> data.PlaneField | None:
        if not self._request.plane_fields:
            return None
        return self._plane_fields.get(key)

    def lane_plane_fields(self, capture_id: str, level_index: int,
                          page: int,
                          ) -> tuple[data.PlaneField | None, ...]:
        return tuple(
            self.plane_field((capture_id, level_index, page, plane))
            for plane in range(3))

    def tile_cover(self, key: tiles.CoverKey,
                   ) -> tuple[tuple[WindowId, ...],
                              tuple[tiles.ColorRowKey, ...]]:
        return (tuple(sorted(self._tile_cover_k.get(key, ()))),
                tuple(sorted(self._tile_cover_color.get(key, ()))))

    def window_cover_tiles(self, wid: WindowId,
                           ) -> tuple[tiles.CoverKey, ...]:
        return self._window_cover.get(wid, ())

    def color_row_cover_tiles(self, key: tiles.ColorRowKey,
                              ) -> tuple[tiles.CoverKey, ...]:
        return self._color_row_cover.get(key, ())

    def level_of_ppc(self, capture_id: str, ppc: Fraction) -> int | None:
        for level in self._captures[capture_id].levels:
            if level.ppc == ppc:
                return level.index
        return None

    def union_rung_ordinal(self, ppc: Fraction) -> int:
        indices = [index for capture_id in self._captures
                   if (index := self.level_of_ppc(capture_id, ppc))
                   is not None]
        return min(indices)

    def cover_lanes(self, page: int, ty: int, tx: int,
                    ppc: Fraction) -> tuple[LaneKey, ...]:
        lanes: list[LaneKey] = []
        for capture_id in sorted(self._captures):
            level_index = self.level_of_ppc(capture_id, ppc)
            if level_index is None:
                continue
            key = (page, ty, tx, capture_id, level_index)
            if key in self._tile_cover_k or key in self._tile_cover_color:
                lanes.append((capture_id, level_index))
        return tuple(lanes)

    def certificate(self, key: CertKey) -> data.Certificate | None:
        return self._certificates.get(key)

    def certificates(self) -> dict[CertKey, data.Certificate]:
        return dict(self._certificates)

    def certificate_keys(self) -> tuple[CertKey, ...]:
        if self._cert_keys_view[0] != len(self._certificates):
            self._cert_keys_view = (len(self._certificates),
                                    tuple(sorted(self._certificates)))
        return self._cert_keys_view[1]

    def has_certificate(self, key: CertKey) -> bool:
        return key in self._certificates

    def n_certificates(self) -> int:
        return len(self._certificates)

    def attempt_outcome(self, key: tuple[object, ...]) -> str | None:
        return self._attempt_outcomes.get(key)

    def worker_version(self, plugin: str, subject: Subject) -> int:
        worker = self._bookmarks.get((plugin, subject))
        return 0 if worker is None else worker.version

    def done_grid(self, page: int) -> np.ndarray:
        n_certs = len(self._certificates)
        cached = self._done_grid_cache.get(page)
        if cached is not None and cached[0] == n_certs:
            return cached[1]
        grid = tiles.done_tile_grid(self.row, self._certificates, page)
        self._done_grid_cache[page] = (n_certs, grid)
        return grid

    def suppressed_codes(self, page: int) -> np.ndarray:
        return np.flatnonzero(self.done_grid(page).ravel()).astype(
            np.int64, copy=False)

    def _region_done_poses(
        self, capture_id: str, region_index: int
    ) -> tuple[tuple[tuple[int, tuple[int, int, int, int],
                           tuple[float, ...]], ...], int]:
        rows = []
        gen_total = 0
        for wid in self.placements():
            if wid[0] != capture_id or wid[2] != region_index:
                continue
            placement = self._placements[wid]
            gen_total += self._pose_gen.get(wid, 0)
            rows.append((placement.page, wid[3],
                         tuple(placement.native_affine)))
        return tuple(rows), gen_total

    def done_cells(self, key: RegionKey) -> np.ndarray | None:
        if not self._certificates:
            return None
        frame = self._frames.get(key)
        if frame is None:
            return None
        counts = self._pose_stamp.get((key[0], key[2]))
        if counts is None:
            return None
        stamp = (counts[0], counts[1], len(self._certificates))
        cached = self._done_cells_cache.get(key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        poses, _gen_total = self._region_done_poses(key[0], key[2])
        grids = {page: self.done_grid(page)
                 for page in sorted({page for page, _e, _a in poses})}
        done = tiles.project_done(poses, grids, frame.origin_native_yx,
                                  frame.pitch_native_px, frame.shape_cells,
                                  frame.support_cells)
        self._done_cells_cache[key] = (stamp, done)
        return done

    def window_extent_done(self, wid: WindowId) -> bool:
        """The pose-free half of the done gate: every supported cell of
        this window's extent already carries a certified tile, projected
        through the region's own committed poses."""
        frame = self._frames.get(wid[:3])
        if frame is None:
            return False
        done = self.done_cells(wid[:3])
        if done is None:
            return False
        return place.done_covers(done, frame.support_cells, wid[3])

    def window_fully_done(self, wid: WindowId) -> bool:
        """True when every tile this window could still contribute
        evidence to is certified in EVERY stream of the coding.

        Such a window can never mint anything again, so no row of it
        needs posing, sampling, refitting or revisiting.  The answer is
        monotone in the certificate frontier because certificates are
        terminal (`_fold_certificate` raises on a conflict and never
        removes one), and `done_grid` is the AND across streams — a tile
        with C and M certified and Y open is NOT done.

        A placed window is judged on its exact tile reach, the derived
        cell maintained beside `page_cells` (window reach) and the
        evidence fit (evidence reach); that reach is a superset of the
        tiles its evidence covers, because the cover is cut from the
        same cells (`tiles.evidence_cover_cells` keeps a payload subset
        of `page_cells_yx`).  An unplaced one is judged pose-free on the
        projection above.  Tiles outside the page grid carry no payload
        and can never certify, so they are ignored — the supported-extent
        law of docs/DONE-GEOMETRY.md §4.6.
        """
        if not self._certificates:
            return False
        placement = self._placements.get(wid)
        if placement is None:
            return self.window_extent_done(wid)
        reach = (self._window_reach.get(wid, ())
                 + self._evidence_reach.get(wid, ()))
        if not reach:
            return False
        grid = self.done_grid(placement.page)
        tiles_y, tiles_x = grid.shape
        on_page = False
        for ty, tx in reach:
            if not (0 <= ty < tiles_y and 0 <= tx < tiles_x):
                continue
            if not grid[ty, tx]:
                return False
            on_page = True
        return on_page

    def _fold(self, fact: object) -> tuple[bool, tuple[FactKey, ...], str]:
        if isinstance(fact, data.Certificate):
            return self._fold_certificate(fact)
        if isinstance(fact, data.Capture):
            return self._fold_capture(fact)
        if isinstance(fact, data.CaptureSurvey):
            return self._fold_survey(fact)
        if isinstance(fact, data.Window):
            return self._fold_window(fact)
        if isinstance(fact, data.Placement):
            return self._fold_placement(fact)
        if isinstance(fact, place_sched.PlaceOutcome):
            return self._fold_place_outcome(fact)
        if isinstance(fact, data.LatticeSeed):
            return self._fold_lattice_seed(fact)
        if isinstance(fact, data.WindowEvidence):
            return self._fold_evidence(fact)
        if isinstance(fact, calibrate.CtxOutcome):
            return self._fold_ctx_outcome(fact)
        if isinstance(fact, refine.RefineOutcome):
            return self._fold_refine_outcome(fact)
        if isinstance(fact, data.AttemptFact):
            return self._fold_attempt(fact)
        if isinstance(fact, data.ColorEvidenceRow):
            return self._fold_color_row(fact)
        if isinstance(fact, color_region_head.ColorLaneFit):
            return self._fold_color_lane_fit(fact)
        if isinstance(fact, data.ColorCtxPopulation):
            return self._fold_color_pop(fact)
        if isinstance(fact, data.PooledColorCtx):
            return self._fold_pooled_ctx(fact)
        if isinstance(fact, data.PlaneField):
            return self._fold_plane_field(fact)
        raise data.IntegrityError(
            f"unknown fact type {type(fact).__name__} reached the fold")

    def _fold_capture(
            self, fact: data.Capture) -> tuple[bool, tuple[FactKey, ...],
                                               str]:
        if fact.capture_id in self._captures:
            return False, (), "other"
        self._captures[fact.capture_id] = fact
        for level in fact.levels:
            self._levels[(fact.capture_id, level.index)] = level
        return True, (), "other"

    def _fold_survey(
            self,
            fact: data.CaptureSurvey) -> tuple[bool, tuple[FactKey, ...],
                                               str]:
        self._surveys[fact.capture_id] = fact
        if fact.pitch_px is None:
            return True, (), "other"
        capture = self._captures[fact.capture_id]
        for level in capture.levels:
            base = 0
            for region in fact.regions:
                frame = place.region_frame(region, level, self.row.pitch_in,
                                           capture.dpi,
                                           capture.platen_backing)
                if frame is None:
                    continue
                key: RegionKey = (fact.capture_id, level.index,
                                  region.region_index)
                self._frames[key] = frame
                plan = place.window_plan(frame, level.index, base)
                base += len(plan)
                for window in plan:
                    self._ingest(window)
            self._plan_total[(fact.capture_id, level.index)] = base
        return True, (), "other"

    def _fold_window(
            self, fact: data.Window) -> tuple[bool, tuple[FactKey, ...],
                                              str]:
        wid = fact.window_id
        if wid in self._windows:
            return False, (), "other"
        self._windows[wid] = fact
        self._ordinal_wid[(fact.capture_id, fact.level_index,
                           fact.ordinal)] = wid
        self._place_stages[wid] = place_sched.WindowState(window=fact)
        return True, (), "other"


    def _fold_place_outcome(
            self,
            fact: place_sched.PlaceOutcome) -> tuple[bool,
                                                     tuple[FactKey, ...],
                                                     str]:
        wid = fact.window_id
        state = self._place_stages.get(wid)
        if state is None:
            return True, (), "other"
        before = (len(state.tried), state.centre_spent, state.rest_spent,
                  state.wide_spent, state.cold_armed, state.cold_live_spent,
                  state.cold_rest_spent, state.dormant_since, state.retired,
                  state.subdivided, state.children)
        result = fact.result
        state.tried |= set(result.tried_now)
        if result.stage_spent == words.STAGE_CENTRE:
            state.centre_spent = True
        elif result.stage_spent == words.STAGE_REST:
            state.rest_spent = True
        if result.wide_spent:
            state.wide_spent = True
            state.cold_armed = True
        if result.cold_spent == place.STAGE_COLD_LIVE:
            state.cold_live_spent = True
        elif result.cold_spent == place.STAGE_COLD_REST:
            state.cold_rest_spent = True
        outcome = result.outcome
        if outcome == "accepted":
            pass
        elif outcome == "insufficient_support":
            state.retired = True
            self._afterlife(state)
        elif outcome == "pose_refused":
            state.dormant_since = self.worker_version("place", wid)
            self._subdivide(state)
        elif outcome == "straddle_audit_refused":
            self._subdivide(state)
            self._place_repush(state)
        else:
            self._place_repush(state)
        after = (len(state.tried), state.centre_spent, state.rest_spent,
                 state.wide_spent, state.cold_armed, state.cold_live_spent,
                 state.cold_rest_spent, state.dormant_since, state.retired,
                 state.subdivided, state.children)
        keys: tuple[FactKey, ...] = (
            ((KEY_PLACE_STAGE, wid),) if after != before else ())
        return True, keys, "other"

    def _fold_placement(
            self, fact: data.Placement) -> tuple[bool, tuple[FactKey, ...],
                                                 str]:
        wid = fact.window_id
        standing = self._placements.get(wid)
        if not _adopts(standing, fact, data.placement_ordinal):
            return False, (), "pose"
        affine_changed = (
            standing is None
            or standing.page != fact.page
            or standing.rot_k != fact.rot_k
            or standing.page_origin_yx != fact.page_origin_yx
            or tuple(standing.native_affine) != tuple(fact.native_affine)
            or standing.pitch_px != fact.pitch_px
            or standing.patch_ordinal != fact.patch_ordinal
            or not np.array_equal(standing.local_cells_yx,
                                  fact.local_cells_yx))
        route_changed = standing is None or standing.route != fact.route
        self._placements[wid] = fact
        stamp_key = (wid[0], wid[2])
        n_poses, gen_total = self._pose_stamp.get(stamp_key, (0, 0))
        self._pose_stamp[stamp_key] = (
            n_poses + (1 if standing is None else 0),
            gen_total + (1 if affine_changed and standing is not None
                         else 0))
        if standing is not None and standing.page != fact.page:
            self._lane_page_wids[(wid[0], wid[1],
                                  standing.page)].discard(wid)
        self._lane_page_wids.setdefault(
            (wid[0], wid[1], fact.page), set()).add(wid)
        keys: list[FactKey] = []
        if affine_changed:
            self._pose_gen[wid] = self._pose_gen.get(wid, -1) + 1
            extent = wid[3]
            shape = (extent[2] - extent[0], extent[3] - extent[1])
            self._page_cells[wid] = calibrate.window_page_cells(
                fact, shape, self.row.cells_yx)
            self._window_reach[wid] = refine.reach_tiles(
                self._page_cells[wid])
            keys.append((KEY_POSE_AFFINE, wid))
        if route_changed:
            keys.append((KEY_POSE_ROUTE, wid))
        state = self._place_stages.get(wid)
        if state is not None and not state.placed:
            state.placed = True
            keys.append((KEY_PLACE_STAGE, wid))
        lane_page = (wid[0], wid[1], fact.page)
        poses = self._lane_poses.setdefault(lane_page, {})
        if poses.get(wid) != tuple(fact.native_affine):
            poses[wid] = tuple(fact.native_affine)
            keys.append((KEY_LANE_POSES,) + lane_page)
        if fact.page not in self._live_pages:
            self._live_pages.add(fact.page)
            keys.append((KEY_LIVE_PAGES,))
        self._lanes_on_page.setdefault(fact.page, set()).add(
            (wid[0], wid[1]))
        key: RegionKey = wid[:3]
        values = [self._placements[owid].pitch_px
                  for owid in self.placements()
                  if owid[:3] == key]
        pitch = calibrate.region_pitch_px(values)
        standing_pitch = self._region_pitch.get(key)
        if standing_pitch is None or pitch != standing_pitch:
            self._region_pitch[key] = pitch
            keys.append((KEY_REGION_PITCH,) + tuple(key))
        return True, tuple(keys), "pose"

    def _fold_lattice_seed(
            self,
            fact: data.LatticeSeed) -> tuple[bool, tuple[FactKey, ...],
                                             str]:
        key: RegionKey = (fact.capture_id, fact.level_index,
                          fact.region_index)
        if not _adopts(self._lattice_seeds.get(key), fact,
                       data.lattice_seed_ordinal):
            return False, (), "other"
        self._lattice_seeds[key] = fact
        return True, ((KEY_LATTICE_SEED,) + tuple(key),), "other"

    def _fold_evidence(
            self,
            fact: data.WindowEvidence) -> tuple[bool, tuple[FactKey, ...],
                                                str]:
        wid = fact.window_id
        standing = self._evidence.get(wid)
        fit_changed = (
            standing is None
            or standing.accepted != fact.accepted
            or standing.refusal_reason != fact.refusal_reason
            or standing.n_search != fact.n_search
            or standing.patch_ordinal != fact.patch_ordinal
            or not np.array_equal(standing.page_cells_yx,
                                  fact.page_cells_yx)
            or not np.array_equal(standing.scores, fact.scores,
                                  equal_nan=True)
            or not np.array_equal(standing.reference_values,
                                  fact.reference_values)
            or not np.array_equal(standing.knots, fact.knots,
                                  equal_nan=True)
            or not np.array_equal(standing.probs, fact.probs,
                                  equal_nan=True)
            or not np.array_equal(standing.marginal_llr, fact.marginal_llr,
                                  equal_nan=True))
        read_changed = (
            standing is None
            or standing.ctx_adopted != fact.ctx_adopted
            or standing.heldout_logloss != fact.heldout_logloss
            or not np.array_equal(standing.printed_llr, fact.printed_llr,
                                  equal_nan=True))
        if not fit_changed and not read_changed:
            return False, (), "other"
        self._evidence[wid] = fact
        keys: list[FactKey] = []
        if fit_changed:
            self._evidence_reach[wid] = refine.reach_tiles(
                fact.page_cells_yx)
            keys.append((KEY_EVIDENCE_FIT, wid))
            covered = (tiles.cover_keys(
                int(fact.page),
                tiles.evidence_cover_cells(self.lookup, fact.page_cells_yx),
                wid[0], wid[1]) if fact.accepted else ())
            _update_cover(self._tile_cover_k, self._window_cover, wid,
                          covered)
        if read_changed:
            keys.append((KEY_EVIDENCE_READ, wid))
        return True, tuple(keys), "other"

    def _fold_ctx_outcome(
            self,
            fact: calibrate.CtxOutcome) -> tuple[bool, tuple[FactKey, ...],
                                                 str]:
        standing = self._region_ctx.get(fact.region_key)
        adopts = _adopts(standing, fact.ctx, data.region_ctx_ordinal)
        held = (standing is not None
                and standing.adopted == fact.ctx.adopted
                and np.array_equal(standing.offsets, fact.ctx.offsets,
                                   equal_nan=True))
        keys: list[FactKey] = []
        if adopts or held:
            for before, after in zip(fact.inputs, fact.outputs):
                if before is after:
                    continue
                changed, evidence_keys, _kind = self._fold_evidence(after)
                if changed:
                    self._births(after)
                    keys.extend(evidence_keys)
        elif standing.adopted:
            for before in fact.inputs:
                row = self._evidence.get(before.window_id)
                if row is None or row.ctx_adopted or not row.accepted:
                    continue
                after = calibrate.apply_standing_context(row, standing)
                changed, evidence_keys, _kind = self._fold_evidence(after)
                if changed:
                    self._births(after)
                    keys.extend(evidence_keys)
        if adopts:
            self._region_ctx[fact.region_key] = fact.ctx
            keys.append((KEY_REGION_CTX,) + tuple(fact.region_key))
            return True, tuple(keys), "other"
        if held:
            return True, tuple(keys), "other"
        return bool(keys), tuple(keys), "other"

    def _fold_refine_outcome(
            self,
            fact: refine.RefineOutcome) -> tuple[bool, tuple[FactKey, ...],
                                                 str]:
        if not fact.revision.adopted:
            return True, (), "other"
        placement = self._placements[fact.window_id]
        revised = refine.revised_placement(placement, fact.revision)
        if fact.revision.candidate_logloss is not None:
            revised = replace(
                revised, quality=float(fact.revision.candidate_logloss))
        changed, keys, _kind = self._fold_placement(revised)
        if changed:
            self._births(revised)
        return True, keys, "pose"

    def _fold_attempt(
            self,
            fact: data.AttemptFact) -> tuple[bool, tuple[FactKey, ...],
                                             str]:
        key = tiles.fact_attempt_key(fact)
        if self._attempt_outcomes.get(key) == fact.outcome:
            return False, (), "other"
        self._attempt_outcomes[key] = fact.outcome
        return True, (), "other"

    def _fold_color_row(
            self,
            fact: data.ColorEvidenceRow) -> tuple[bool, tuple[FactKey, ...],
                                                  str]:
        key = (fact.capture_id, fact.level_index, fact.page,
               fact.patch_ordinal)
        standing = self._color_rows.get(key)
        changed = (standing is None
                   or standing.heldout_logloss != fact.heldout_logloss
                   or not np.array_equal(standing.values, fact.values,
                                         equal_nan=True)
                   or not np.array_equal(standing.page_cells_yx,
                                         fact.page_cells_yx))
        if not changed:
            return False, (), "other"
        self._color_rows[key] = fact
        covered = tiles.cover_keys(
            int(fact.page),
            tiles.color_cover_cells(self.geometry, fact.page_cells_yx),
            fact.capture_id, fact.level_index)
        _update_cover(self._tile_cover_color, self._color_row_cover, key,
                      covered)
        return True, ((KEY_COLOR_ROW,) + key,), "other"

    def _fold_color_pop(
            self,
            fact: data.ColorCtxPopulation) -> tuple[bool,
                                                    tuple[FactKey, ...], str]:
        key = (fact.capture_id, fact.level_index, fact.page)
        standing = self._color_pops.get(key)
        changed = (standing is None
                   or standing.rung != fact.rung
                   or not np.array_equal(standing.keys_pyx, fact.keys_pyx)
                   or not np.array_equal(standing.states, fact.states)
                   or not np.array_equal(standing.kinds, fact.kinds)
                   or not np.array_equal(standing.bins, fact.bins)
                   or not np.array_equal(standing.search, fact.search)
                   or not np.array_equal(standing.scores, fact.scores,
                                         equal_nan=True))
        if not changed:
            return False, (), "other"
        self._color_pops[key] = fact
        self._pop_lanes.setdefault((fact.page, fact.rung), set()).add(key)
        return True, ((KEY_COLOR_POP, fact.page, fact.rung),), "other"

    def _fold_pooled_ctx(
            self,
            fact: data.PooledColorCtx) -> tuple[bool, tuple[FactKey, ...],
                                                str]:
        key = (fact.page, fact.rung)
        if not _adopts(self._pooled_ctx.get(key), fact,
                       data.pooled_ctx_ordinal):
            return False, (), "other"
        self._pooled_ctx[key] = fact
        return True, ((KEY_POOLED_CTX, fact.page, fact.rung),), "other"

    def _fold_plane_field(
            self,
            fact: data.PlaneField) -> tuple[bool, tuple[FactKey, ...], str]:
        key = (fact.capture_id, fact.level_index, fact.page, fact.plane)
        if not _adopts(self._plane_fields.get(key), fact,
                       data.plane_field_ordinal):
            return False, (), "other"
        self._plane_fields[key] = fact
        return True, ((KEY_PLANE_FIELD,) + key,), "other"

    def _fold_color_lane_fit(
            self,
            fact: color_region_head.ColorLaneFit,
            ) -> tuple[bool, tuple[FactKey, ...], str]:
        key = (fact.capture_id, fact.level_index, fact.page)
        self._color_lane_assembled.setdefault(key, set()).update(
            fact.assembled)
        if fact.head_fitted:
            self._color_lane_head_fits[key] = (
                self._color_lane_head_fits.get(key, 0) + 1)
        if fact.head is not None:
            self._color_lane_head[key] = fact.head
        return True, (), "other"

    def _fold_certificate(
            self,
            fact: data.Certificate) -> tuple[bool, tuple[FactKey, ...],
                                             str]:
        key: CertKey = (fact.page, fact.ty, fact.tx, fact.stream_id)
        standing = self._certificates.get(key)
        if standing is not None:
            if np.array_equal(standing.user_bits, fact.user_bits):
                return False, (), "certificate"
            raise data.IntegrityError(
                f"conflicting certificates at {key}: "
                f"{standing.source} vs {fact.source}")
        counter = self.row.tile_counter(fact.page, fact.ty, fact.tx)
        index = (metadata.equation_index(counter,
                                         self.stream_index[fact.stream_id],
                                         len(self.row.streams))
                 if self.row.pooled_fountain else counter)
        bit = int(fact.user_bits[0])
        prev = self._equations.get(index)
        if prev is not None and prev != bit:
            raise data.IntegrityError(
                f"opposite metadata bits at equation index {index} "
                f"(tile {key})")
        self._equations[index] = bit
        self._certificates[key] = fact
        return True, ((KEY_TILE, fact.page, fact.ty, fact.tx,
                       fact.stream_id),
                      (KEY_PAGE_CERTS, fact.page)), "certificate"


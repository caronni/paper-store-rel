from __future__ import annotations

from fractions import Fraction

import numpy as np

from . import data
from .data import CertKey, DecodeRequest, LaneKey, RegionKey, WindowId
from .descriptor import Subject, WorkerBookmark
from .format import identity
from .format.identity import FormatRow, SiteGeometry
from .plugins import (
    calibrate,
    color_region,
    color_region_head,
    place,
    place_sched,
    tiles,
    words,
)
from .store_folds import _Folds, color_row_adopt_by_env


class _Store(_Folds):

    #: The job whose facts are folding now, set by `engine._merge` for
    #: the length of that job's facts and None otherwise; and whether a
    #: fact folded by somebody else bumped its bookmark between the pop
    #: that prepared it and this merge.  Class defaults, so an engine
    #: built by hand (contract tests) and a fact ingested outside any
    #: merge read "no job merging".
    _merging: WorkerBookmark | None = None
    _merging_woken: bool = False

    def __init__(self, request: DecodeRequest,
                 events: list[data.Event]) -> None:
        self._request = request
        self._events = events
        # The colour row's adoption rule, read ONCE (store_folds: a
        # MEASUREMENT hatch; the default is the shipped fold).
        self._color_row_adopt = color_row_adopt_by_env()
        self.row: FormatRow = identity.resolve_format_ref(
            request.format_ref)
        self.geometry: SiteGeometry = identity.build_site_geometry(self.row)
        self.stream_index: dict[str, int] = {
            s.stream_id: i for i, s in enumerate(self.row.streams)}
        bound = (self.row.max_pages if request.max_pages is None
                 else int(request.max_pages))
        # POSSIBLE pages, everywhere -- word admission and cold alike.  The
        # live set is a separate consult (`live_pages`), never a second
        # meaning of this tuple (PAGE-DOMAIN.md §3, edit 1).
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
        # The `{0}` prior is load-bearing, not an initialiser: without it the
        # first cold on a word-failed single sheet is a full-possible REST
        # sweep at the rest floor, and small-support windows never rest-place
        # (PAGE-DOMAIN.md §3, edit 2; contract 07-7 reborn as a prior).
        self._live_pages: set[int] = {0}
        self._lanes_on_page: dict[int, set[LaneKey]] = {}
        self._region_pitch: dict[RegionKey, float] = {}
        # the (halo, aperture) pair the standing pitch samples with at
        # its level: `KEY_REGION_PITCH` moves with THIS, not the float
        self._region_sampling: dict[RegionKey, tuple[int, int]] = {}
        self._evidence: dict[WindowId, data.WindowEvidence] = {}
        self._region_ctx: dict[RegionKey, data.RegionCtx] = {}
        self._color_rows: dict[tuple[str, int, int, int],
                               data.ColorEvidenceRow] = {}
        self._color_pops: dict[tuple[str, int, int],
                               data.ColorCtxPopulation] = {}
        self._pop_lanes: dict[tuple[int, str],
                              set[tuple[str, int, int]]] = {}
        self._pooled_ctx: dict[tuple[int, str], data.PooledColorCtx] = {}
        self._plane_fields: dict[tuple[int, int], data.PlaneField] = {}
        self._field_observations: dict[tuple[str, int],
                                       data.FieldObservations] = {}
        # the evidence revision per (capture, page): one integer
        # advanced by every placement birth, change or removal on that
        # page and by every certificate on it, and by nothing else
        # (I12).  It is the collection's ordinal, so a collection whose
        # inputs really changed is never mistaken for one already done;
        # it is restored on resume rather than recounted, because it
        # counts EVENTS and events do not survive their facts.
        self._evidence_revision: dict[tuple[str, int], int] = {}
        self._tile_cover_k: dict[tiles.CoverKey, set[WindowId]] = {}
        self._tile_cover_color: dict[tiles.CoverKey,
                                     set[tiles.ColorRowKey]] = {}
        self._window_cover: dict[WindowId, tuple[tiles.CoverKey, ...]] = {}
        self._color_row_cover: dict[tiles.ColorRowKey,
                                    tuple[tiles.CoverKey, ...]] = {}
        self._certificates: dict[CertKey, data.Certificate] = {}
        self._equations: dict[int, int] = {}
        self._attempt_outcomes: dict[tuple[object, ...], str] = {}
        # The NARROW attempt ledger, beside the component-keyed one: the
        # newest `(outcome, generation)` per `(page, ty, tx, stream_id,
        # stage, lane)`.  `_attempt_outcomes` stays exactly as it was --
        # `prepare_retry`'s idempotence floor and two `measure/` readers
        # take it as strings -- and this is the cell the KEY_ATTEMPT wake
        # key and the residue rows' `eligible` read.
        self._attempt_latest: dict[tuple[object, ...],
                                   tuple[str, int]] = {}
        # The FOOTINGS that have EVER carried a failed verdict:
        # `(page, ty, tx, stream_id, stage, ppc)`.  The standing verdict
        # above is last-write-wins, so it forgets a failure the next read
        # replaces; the residue rungs' franchise may not
        # (`local_ctx._failed_at`), so this remembers it, and only a
        # certificate takes a stream out of the residue.  It is keyed by
        # footing, not by lane: the residue rows' arming can only
        # enumerate the lanes that cover the tile NOW, so a lane that
        # failed and then left the cover (its window's evidence refused,
        # or re-placed elsewhere) would take a lane-keyed failure with
        # it.  A lane's footing never moves, so this one cannot be lost
        # that way (2026-10-03).  The lane-keyed ledger it replaced was
        # written on every failure and read by nothing in production; it
        # was deleted 2026-10-18 (SCHED-LIFECYCLE-REVIEW D11).
        self._attempt_ever_failed_footing: set[tuple[object, ...]] = set()
        # One counter per (tile, lane): bumped by every evidence or
        # colour-row fold that could change the cut assembled over that
        # tile at that lane.  DERIVED, never snapshotted -- AttemptFact
        # is not snapshotted either, so the ledger starts empty on a
        # resume and no generation is ever compared across runs.
        self._tile_lane_generation: dict[tiles.CoverKey, int] = {}
        # And one per (tile, FOOTING), maintained the same way and for
        # the same reason.  It was SUMMED over the current cover until
        # the 2026-09-21 review measured the sum going DOWN (1 -> 2 -> 0
        # on one capture: a refused re-fit empties the cover, and a
        # lane leaving takes its whole term with it, however often it
        # was bumped on the way out).  A quantity two `eligible`
        # predicates compare with `==` may never come back to a value a
        # standing verdict was stamped with, so the footing counts its
        # own events instead of adding up somebody else's.
        self._union_generation: dict[tuple[int, int, int, Fraction],
                                     int] = {}
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
        #: THE DONE MEMO (2026-10-03): the last answer `window_fully_done`
        #: gave for an UNPLACED window, written by that reader itself --
        #: the one place the answer exists, so the one honest place to
        #: record it.  It is a memo, not a fact: nothing is decided on
        #: it except which windows `_fold_placement` re-judges when an
        #: adopted affine moves in their region, so it stays out of the
        #: fold write map like the done caches above.  The per-region
        #: index holds the windows last judged DONE, which bounds that
        #: re-judging by the suppressed windows of the one region.
        self._window_done_seen: dict[WindowId, bool] = {}
        self._window_done_region: dict[tuple[str, int],
                                       set[WindowId]] = {}

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

    def lane_page_window_count(self, capture_id: str, level_index: int,
                               page: int) -> int:
        return len(self._lane_page_wids.get((capture_id, level_index,
                                             page), ()))

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

    def refine_gate_context(self) -> bool:
        return self._request.refine_gate == data.REFINE_GATE_CONTEXT

    def page_plane_fields(self, page: int,
                          ) -> tuple[data.PlaneField | None, ...]:
        """This printed face's three fields, C, M, Y, missing ones None."""
        return tuple(self._plane_fields.get((int(page), plane))
                     for plane in range(3))

    def field_observations(self,
                           page: int) -> tuple[data.FieldObservations, ...]:
        """Every capture's measurements of this page, capture id order."""
        return tuple(
            self._field_observations[key]
            for key in sorted(self._field_observations)
            if key[1] == int(page))

    def evidence_revision(self, capture_id: str, page: int) -> int:
        """What this capture-page's collection would be measuring (I12)."""
        return self._evidence_revision.get((str(capture_id), int(page)), 0)

    def page_evidence_revision(self, page: int) -> int:
        """The revision the page's standing EVIDENCE was collected at.

        The sum over the page's collections of the revision each was
        made at — monotone, because every term is monotone and a
        collection is adopted only at a higher one.  It is what a solve
        stamps on its fields and what says whether the page owes
        another: a store revision that has moved without a collection
        behind it is a measurement nobody has made yet.
        """
        return sum(int(fact.revision)
                   for fact in self.field_observations(int(page)))

    def field_revision(self, page: int) -> int:
        """The revision the page's standing field was fitted at (I12).

        Zero where no plane has been solved, which is the same answer a
        consumer that has never seen a field records — it owes a refit
        the moment a real one arrives.  ONE reduction, in
        `color_region`, because the job functions are handed the fields
        and never the store and would otherwise carry a second.
        """
        return color_region.field_revision_of(
            self.page_plane_fields(int(page)))

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

    def attempt_verdict(self, page: int, ty: int, tx: int, stream_id: str,
                        stage: str, lane: object,
                        ) -> tuple[str, int] | None:
        """The newest `(outcome, generation)` for one tile-stream cut.

        The tail of the KEY_ATTEMPT key, spelled from a subscriber's own
        subject: `lane` is `(capture_id, level_index)` for a single-lane
        stage and the footing's ppc for a summed one.
        """
        return self._attempt_latest.get(
            (page, ty, tx, stream_id, stage, lane))

    def attempt_ever_failed_at_footing(self, page: int, ty: int, tx: int,
                                       stream_id: str, stage: str,
                                       ppc: Fraction) -> bool:
        """Has any cut of this stage at this FOOTING ever come back failed?

        Cover-independent: whichever lane (or summed set of lanes) at
        `ppc` failed, and whether or not it still covers the tile.
        Monotone; only a certificate takes the stream out of the
        residue.  This is the ONE failure memory the store keeps; the
        standing verdict per lane is `attempt_verdict`.
        """
        return (page, ty, tx, stream_id, stage,
                ppc) in self._attempt_ever_failed_footing

    def tile_lane_generation(self, key: tiles.CoverKey) -> int:
        """How often this tile's cut at this lane could have moved."""
        return self._tile_lane_generation.get(key, 0)

    def union_generation(self, page: int, ty: int, tx: int,
                         ppc: Fraction) -> int:
        """How often this tile's SUMMED cut at this footing could have moved.

        A counter of its own, bumped by `_advance_tile_lanes` once for
        every lane event at this footing, and so monotone by
        construction -- which a sum over the current cover was NOT (see
        `_union_generation`).  Monotone is the whole requirement:
        `tiles.retry`'s union arm compares a standing verdict's stamp
        with `==`, and a quantity that can come back to an old value
        makes a verdict taken on components that no longer exist look
        current.
        """
        return self._union_generation.get((int(page), int(ty), int(tx),
                                           ppc), 0)

    def worker_version(self, plugin: str, subject: Subject) -> int:
        worker = self._bookmarks.get((plugin, subject))
        return 0 if worker is None else worker.version

    def merging_sleep_version(self, subject: Subject) -> int | None:
        """The version `subject` may sleep at, or None: stay awake.

        A SLEEP IS STAMPED AGAINST WHAT THE PASS READ (S7, 2026-10-03).
        `_touch` bumps a bookmark's version even while its job is in
        flight -- the push only marks it pending -- so the bookmark's
        version at merge time already holds every wake that arrived
        during the pass: a neighbour's pose, a page going live.  A
        sleep stamped there swallowed them, and the window never saw
        the anchor it was refused for want of.  So the sleep is granted
        only when nothing woke the merging job's bookmark between its
        pop and this merge; the version returned is the bookmark's NOW,
        which counts the wakes the job's OWN facts folded ahead of this
        one (a lattice seed the pass itself produced) and nothing else.
        Outside a merge, or for a subject that is not the merging job's,
        there is no pass to sleep on: None.  Generic -- no plugin name;
        the one writer of a fact that sleeps is that fact's producer.
        """
        worker = self._merging
        if worker is None or worker.subject != subject \
                or self._merging_woken:
            return None
        return worker.version

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

    #: One pose per posed window -- the LATEST adopted, never the union.
    #: Unioning parent and revision over-claimed +860 done cells on e029
    #: and +588 on Xerox for revisions that sampled no pixel (ruling I3,
    #: 2026-08-23); the residual boundary sliver is UNMEASURED both ways.
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

    def _note_window_done(self, wid: WindowId, done: bool) -> None:
        """Record the done memo for one UNPLACED window (see __init__)."""
        self._window_done_seen[wid] = done
        region = self._window_done_region.setdefault((wid[0], wid[2]),
                                                      set())
        if done:
            region.add(wid)
        else:
            region.discard(wid)

    def reopened_done_windows(self, capture_id: str,
                              region_index: int) -> tuple[WindowId, ...]:
        """The unplaced windows of one region last judged DONE that the
        region's current projection no longer covers, memo updated.

        Called by the placement fold once an adopted affine has moved in
        the region: the pose-free projection runs through the LATEST
        pose of every placed window, so a revision can SHRINK it, and a
        window suppressed on the old geometry has to hear that it is
        open again.  Only windows previously judged done are re-judged
        -- the opposite direction is found at the window's next wake.
        A window that has since PLACED leaves the memo: its own reach
        judges it now, and its place row retires on `placed`.
        """
        suppressed = self._window_done_region.get((capture_id, region_index))
        if not suppressed:
            return ()
        reopened: list[WindowId] = []
        for wid in sorted(suppressed):
            if wid in self._placements:
                suppressed.discard(wid)
                self._window_done_seen.pop(wid, None)
                continue
            if not self.window_extent_done(wid):
                self._note_window_done(wid, False)
                reopened.append(wid)
        return tuple(reopened)

    def window_fully_done(self, wid: WindowId) -> bool:
        """True when every tile this window could still contribute
        evidence to is certified in EVERY stream of the coding.

        Such a window has nothing left to mint while the answer holds,
        so no row of it needs posing, sampling, refitting or revisiting.
        `done_grid` is the AND across streams — a tile with C and M
        certified and Y open is NOT done — and only grows, because
        certificates are terminal (`_fold_certificate` raises on a
        conflict and never removes one).  The answer is monotone in
        that frontier AT FIXED GEOMETRY ONLY.  The unplaced half is NOT
        monotone under a pose revision: its projection runs through the
        LATEST adopted pose of every placed window in the region, and a
        revision can shrink it, turning a done window open again.  That
        is why `place_sched.worker_stage` SUPPRESSES on this verdict
        instead of retiring (56928c45), and why the store keeps the
        done memo and emits `KEY_WINDOW_DONE` from
        `reopened_done_windows` when the projection moves.

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
            done = self.window_extent_done(wid)
            self._note_window_done(wid, done)
            return done
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


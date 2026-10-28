"""The observer-side pane model: derived views, built read-only (L12).

DESIGN §10.3 makes the diag surface "derived views over the commit stream
and orchestrator snapshots". This module is the derivation. It builds its
own :class:`~holo2.solve.tilemap.TileMap` and done projection rather than
borrowing the session's caches, because a private derivation couples the
surface to no session object and owns everything it can damage.

**The store INDEX is the exception, and it stopped being a private
rebuild** (F-17's second residual, 2026-08-17). It used to be one
:meth:`~holo2.solve.tilemap.StoreIndex.build` pass over the store's
sorted keys per render, with a documented retry for "a dict mutated
under the observer while the committer worked". The plane MAINTAINS that
index now — copy-on-write per generation, advanced by each commit's own
delta — so what a reader is handed is a frozen value: it cannot mutate
underneath anybody, the retry has nothing left to catch, and the pass is
work the committer already did. Reading it is not a new coupling either;
the binding this module has held since R2 is the plane itself.

The rest of what this module reads is the frozen session assembly, bound
directly: the derived PLANE (``holo2.solve.SessionPlane``) carries
``captures`` (frozen dataclasses fixed at session open) for the region
lattices and support masks, ``format_row`` for the tile grid and stream
ids, the maintained index, and — since F-02 closed (H4 W6) — three
NARROW TYPED READS in place of the store itself: ``commit_seq`` for the
frame revision, ``close_record()`` for the verdict, and
``attempted_work_keys()`` for the ATTEMPTED chips. The observer used to
be handed the whole ``core.Store`` through a read-only-by-convention
property, which is a wider grant than any of this needs; the reads are
the same information through a typed door. None of it is mutated after
assembly.

No clocks anywhere, on either side (the conventions test is repo-wide and
this module keeps it honestly, not by exemption): a frame's identity is
the store's commit sequence, which is work-counted, so an observed run
and a headless run still read zero clocks between them.

Choices where DESIGN is silent (for adjudication):

1. **Window marks are footing-agnostic.** A capture-cell extent is one
   rectangle of one region regardless of how many footings enumerate a
   window over it (§8.2: footings differ in sampling, not in physical
   cell size). The mark folds every footing's window at that extent into
   one state, so pane A shows the geometry of the capture, not the
   cardinality of the footing ladder.
2. **The window lattice is recomputed here, not read from the plane.**
   The original reason — ``SessionPlane.window_plans`` memoized into the
   plane, so an observer calling it wrote into an object the committer
   owned — expired with W-S wave 1 (generation-stamped views, built
   under their own lock). The choice stands on its own merits: the
   lattice is a pure function of (region lattice, support), so
   recomputing it observer-side costs a pass, couples nothing, and
   produces the same ids (a window IS its footing, region and extent,
   §10.2).
3. **A capture's pages come from its poses' evidence** (the ``StoreIndex``
   rule): a capture that has observed nothing addresses no page, and pane
   A for such a page falls back to the first capture in session order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ...solve import (DoneProjection, StoreIndex, TileMap, WINDOW_CELLS,
                      WINDOW_STEP_CELLS, project_done, window_starts)
from ...solve import TileState, WindowStatus, parse_tile_key, tile_state
from ...solve import window_key
from ...core import ResourceKey

# A capture whose frame exceeds this many native pixels gets no preview
# underlay: the pane says so rather than pulling a multi-gigabyte scan
# through a memory map to draw a thumbnail. Declared, never silent.
UNDERLAY_MAX_PIXELS = 200_000_000
UNDERLAY_TARGET_PX = 900

# Window mark states, in the order pane A paints them.
WINDOW_PENDING = "pending"
WINDOW_POSED = "posed"
WINDOW_RETIRED = "retired"
WINDOW_DONE = "done"


class PaneModelError(RuntimeError):
    """A derived pane view disagreed with the store it was built from."""


@dataclass(frozen=True)
class WindowMark:
    """One capture-cell extent of the window lattice, and what happened."""

    extent_cells: tuple[int, int, int, int]
    state: str
    poses: int = 0


@dataclass(frozen=True)
class RegionMark:
    """One surveyed region: its lattice, its support, its done cells."""

    region_id: ResourceKey
    hue: int
    origin_yx: tuple[int, int]
    pitch_px: float
    support: np.ndarray                     # (cells_y, cells_x) bool
    done: np.ndarray                        # same shape, bool
    windows: tuple[WindowMark, ...] = ()

    @property
    def shape_cells(self) -> tuple[int, int]:
        return (int(self.support.shape[0]), int(self.support.shape[1]))

    @property
    def bbox_px(self) -> tuple[float, float, float, float]:
        """Native-pixel ``(y0, x0, y1, x1)`` covered by the cell lattice."""
        rows, cols = self.shape_cells
        return (float(self.origin_yx[0]), float(self.origin_yx[1]),
                self.origin_yx[0] + rows * self.pitch_px,
                self.origin_yx[1] + cols * self.pitch_px)


@dataclass(frozen=True)
class CaptureMark:
    """One authenticated acquisition as the capture pane draws it."""

    sha256: str
    regions: tuple[RegionMark, ...]
    unschedulable: int = 0

    @property
    def short(self) -> str:
        return self.sha256[:12]


@dataclass(frozen=True)
class TilePlane:
    """One page of the tile map, per stream (DESIGN §5.2 work keys)."""

    page: int
    tiles_yx: tuple[int, int]
    stream_ids: tuple[str, ...]
    states: np.ndarray                      # (n_streams, ty, tx) uint8 ranks
    evidence: np.ndarray                    # (ty, tx) int32 piece counts

    def counts(self) -> dict[str, int]:
        tally = {state.name: 0 for state in TileState}
        for state in TileState:
            tally[state.name] = int(np.count_nonzero(
                self.states == state.value))
        return tally

    def certified_tiles(self) -> int:
        """Work keys whose EVERY stream is certified (the §6 done rule)."""
        every = np.all(self.states == TileState.CERTIFIED.value, axis=0)
        return int(np.count_nonzero(every))


@dataclass(frozen=True)
class PaneModel:
    """One frame's worth of observer facts."""

    revision: int
    page: int
    pages: tuple[int, ...]
    row_id: str
    codec_id: str
    capture: CaptureMark | None
    captures: tuple[str, ...]
    plane: TilePlane | None
    snapshot: dict = field(default_factory=dict)
    close_status: str = "open"
    payload_sha256: str | None = None
    notes: tuple[str, ...] = ()


class PaneSource:
    """Everything the panes read, bound to one live plane (read-only).

    The binding is duck-typed on purpose: the observer is handed whatever
    the receiver already exposes and never asks it for a new field. A
    binding that does not quack is simply not bound, and the panes degrade
    to what the orchestrator snapshot alone can say. Since R2 the object
    that quacks is the session's derived plane, and since F-02 closed
    (H4 W6) the quack is SIX NARROW READS rather than five plus a store:
    captures, printed row, maintained index, commit sequence, close
    record and the ATTEMPTED key set. The session holds only authority.
    """

    def __init__(self, ctx: object) -> None:
        for name in ("captures", "format_row", "index", "commit_seq",
                     "close_record", "attempted_work_keys"):
            if not hasattr(ctx, name):
                raise PaneModelError(
                    f"not a session: no {name!r} (observer stays unbound)")
        self._ctx = ctx
        self._underlay: dict[str, tuple[np.ndarray, int] | None] = {}

    # -- cheap channel -----------------------------------------------------

    @property
    def revision(self) -> int:
        """The frame revision: the store's commit sequence, never a clock."""
        return int(getattr(self._ctx, "commit_seq", 0))

    def catalog(self) -> dict:
        """Cheap facts for the status channel and the index page."""
        row = self._ctx.format_row
        return {
            "revision": self.revision,
            "row_id": str(row.row_id),
            "codec_id": str(row.codec_id),
            "pages": [int(page) for page in row.page_domain],
            "tiles_yx": [int(value) for value in row.tiles_yx],
            "streams": [str(name) for name in row.stream_ids],
            "captures": [capture.source_sha256[:12]
                         for capture in self._ctx.captures],
        }

    def posed_pages(self) -> tuple[int, ...]:
        """Pages some committed pose addresses — the frames worth keeping.

        A run that placed nothing addresses nothing, and would leave the
        operator no picture at exactly the moment a picture matters most;
        so an empty result falls back to the first declared page, whose
        frame then honestly shows an empty tile map (choice, listed).
        """
        domain = tuple(int(page) for page in self._ctx.format_row.page_domain)
        try:
            index = self._index()
        except Exception:                    # observer reads are advisory
            return domain[:1]
        seen = {pose.page for pose in index.poses.values()}
        posed = tuple(page for page in domain if page in seen)
        return posed or domain[:1]

    # -- the frame model ---------------------------------------------------

    def build(self, page: int, capture_short: str | None = None,
              snapshot: dict | None = None) -> PaneModel:
        """Derive one page's model. Expensive by design; called on demand."""
        row = self._ctx.format_row
        index = self._index()
        tiles = TileMap(index, row.stream_ids, row.tiles_yx)
        notes: list[str] = []
        capture = self._capture_mark(index, tiles, page, capture_short, notes)
        plane = self._plane(index, page)
        record = self._close_record()
        return PaneModel(
            revision=self.revision,
            page=int(page),
            pages=tuple(int(value) for value in row.page_domain),
            row_id=str(row.row_id),
            codec_id=str(row.codec_id),
            capture=capture,
            captures=tuple(view.source_sha256[:12]
                           for view in self._ctx.captures),
            plane=plane,
            snapshot=dict(snapshot or {}),
            close_status=("open" if record is None
                          else str(record.status.value)),
            payload_sha256=(None if record is None
                            else record.payload_sha256),
            notes=tuple(notes),
        )

    def _index(self) -> StoreIndex:
        """The plane's maintained index — a frozen value, read as one.

        No rebuild and no retry (see the module docstring): the value is
        immutable per generation, so an observer holding it is reading a
        commit boundary rather than racing one, and which boundary is
        the ordinary declared staleness the whole surface runs on.
        """
        return self._ctx.index()

    def _close_record(self):
        try:
            return self._ctx.close_record()
        except Exception:                    # observer reads are advisory
            return None

    # -- capture pane ------------------------------------------------------

    def _capture_mark(self, index: StoreIndex, tiles: TileMap, page: int,
                      wanted: str | None,
                      notes: list[str]) -> CaptureMark | None:
        views = tuple(self._ctx.captures)
        if not views:
            notes.append("no captures ingested")
            return None
        pages_by_capture = self._pages_by_capture(index)
        chosen = None
        if wanted:
            for view in views:
                if view.source_sha256.startswith(wanted):
                    chosen = view
                    break
        if chosen is None:
            for view in views:
                if page in pages_by_capture.get(view.source_sha256, ()):
                    chosen = view
                    break
        if chosen is None:
            chosen = views[0]
        regions = []
        unschedulable = 0
        for order, region in enumerate(chosen.regions):
            if not region.schedulable:
                unschedulable += 1
                continue
            regions.append(self._region_mark(index, tiles, chosen, region,
                                             order))
        if unschedulable:
            notes.append(f"{unschedulable} region(s) without a pitch vote "
                         "schedule nothing (survey declined)")
        return CaptureMark(
            sha256=chosen.source_sha256,
            regions=tuple(regions),
            unschedulable=unschedulable,
        )

    def _pages_by_capture(self, index: StoreIndex) -> dict[str, tuple[int, ...]]:
        """Which pages each capture's committed poses address (choice 3)."""
        by_capture: dict[str, set[int]] = {}
        region_capture = {view.region_id: view.capture_sha256
                          for capture in self._ctx.captures
                          for view in capture.regions}
        for pose in index.poses.values():
            window = index.windows.get(pose.window_id)
            if window is None:
                continue
            sha = region_capture.get(window.region_id)
            if sha is None:
                continue
            by_capture.setdefault(sha, set()).add(pose.page)
        return {sha: tuple(sorted(pages)) for sha, pages in by_capture.items()}

    def _region_mark(self, index: StoreIndex, tiles: TileMap, capture,
                     region, order: int) -> RegionMark:
        lattice = region.lattice
        support = np.asarray(region.support, bool)
        # The live pose of each posed window, exactly as the scheduler's
        # own projection reads it (tilemap choice 8) — the operator's done
        # band and the gate must not be two different answers.
        pose_ids = index.live_poses_of_region(region.region_id)
        try:
            projection = project_done(
                index, tiles, capture_sha256=capture.source_sha256,
                region_id=region.region_id, lattice=lattice, support=support,
                pose_ids=pose_ids)
        except Exception:
            projection = DoneProjection(capture.source_sha256,
                                        region.region_id,
                                        np.zeros(support.shape, bool))
        return RegionMark(
            region_id=region.region_id,
            hue=order,
            origin_yx=tuple(int(v) for v in lattice.origin_yx),
            pitch_px=float(lattice.pitch_px),
            support=support,
            done=np.asarray(projection.cells, bool),
            windows=self._window_marks(index, capture, region, support,
                                       projection),
        )

    def _window_marks(self, index: StoreIndex, capture, region,
                      support: np.ndarray,
                      projection: DoneProjection) -> tuple[WindowMark, ...]:
        """The §8.2 window lattice of one region, folded over footings."""
        footing_ids = tuple(footing.footing_id for footing in capture.footings)
        rows, cols = support.shape
        marks: list[WindowMark] = []
        for cy0 in window_starts(rows, WINDOW_CELLS, WINDOW_STEP_CELLS):
            cy1 = min(rows, cy0 + WINDOW_CELLS)
            for cx0 in window_starts(cols, WINDOW_CELLS, WINDOW_STEP_CELLS):
                cx1 = min(cols, cx0 + WINDOW_CELLS)
                extent = (cy0, cx0, cy1, cx1)
                if not support[cy0:cy1, cx0:cx1].any():
                    continue
                ids = tuple(window_key(footing_id, region.region_id, extent)
                            for footing_id in footing_ids)
                poses = sum(len(index.poses_by_window.get(wid, ()))
                            for wid in ids)
                records = [index.windows[wid] for wid in ids
                           if wid in index.windows]
                if poses:
                    state = WINDOW_POSED
                elif records and all(record.status is WindowStatus.RETIRED
                                     for record in records):
                    state = WINDOW_RETIRED
                else:
                    state = WINDOW_PENDING
                if projection.covers(extent, support):
                    state = WINDOW_DONE
                marks.append(WindowMark(extent, state, poses))
        return tuple(marks)

    # -- underlay ----------------------------------------------------------

    def underlay(self, capture_short: str
                 ) -> tuple[np.ndarray, int] | None:
        """A decimated grey preview of one capture, derived once and kept.

        Returns ``(grey, stride)`` in native-pixel orientation so the
        renderer can place it; ``None`` means the capture is above
        :data:`UNDERLAY_MAX_PIXELS` (declared refusal, printed in the pane)
        or simply unreadable. A preview is context, never radiometry.
        """
        if capture_short in self._underlay:
            return self._underlay[capture_short]
        preview = None
        for view in self._ctx.captures:
            if not view.source_sha256.startswith(capture_short):
                continue
            preview = self._decimate(view)
            break
        self._underlay[capture_short] = preview
        return preview

    def _decimate(self, view) -> tuple[np.ndarray, int] | None:
        raster = getattr(view, "raster", None)
        shape = tuple(int(value) for value in view.record.shape_px)
        if raster is None or shape[0] * shape[1] > UNDERLAY_MAX_PIXELS:
            return None
        try:
            stride = max(1, int(max(shape) // UNDERLAY_TARGET_PX))
            native = raster.crop_native(0, shape[0], 0, shape[1])
            sliced = np.asarray(native[::stride, ::stride], np.float32)
            if sliced.ndim == 3:
                sliced = sliced.mean(axis=2)
            if sliced.ndim != 2 or not sliced.size:
                return None
            return sliced, stride
        except Exception:                    # a preview is never load-bearing
            return None

    # -- tile plane --------------------------------------------------------

    def _plane(self, index: StoreIndex, page: int) -> TilePlane:
        row = self._ctx.format_row
        tiles_y, tiles_x = (int(v) for v in row.tiles_yx)
        stream_ids = tuple(str(name) for name in row.stream_ids)
        order = {name: position for position, name in enumerate(stream_ids)}
        states = np.zeros((len(stream_ids), tiles_y, tiles_x), np.uint8)
        evidence = np.zeros((tiles_y, tiles_x), np.int32)
        attempted = self._attempted_work_keys()
        for key, record in index.tiles.items():
            try:
                key_page, ty, tx, stream = parse_tile_key(key)
            except Exception:
                continue
            position = order.get(stream)
            if (key_page != page or position is None
                    or not (0 <= ty < tiles_y and 0 <= tx < tiles_x)):
                continue
            states[position, ty, tx] = tile_state(
                record, attempted=key in attempted).value
            evidence[ty, tx] += len(index.evidence_by_tile.get(key, ()))
        return TilePlane(int(page), (tiles_y, tiles_x), stream_ids, states,
                         evidence)

    def _attempted_work_keys(self) -> frozenset[ResourceKey]:
        """Work keys a decoder has run on, off the durable spend ledger.

        Since tile family v4 the ATTEMPTED chip is derived, and the
        payload family owns the counting rule; the PLANE is asked for the
        answer now (F-02's close, H4 W6) rather than for the ledger the
        rule reads — the same call its own tile tally makes, so the chips
        and the tiles row cannot come to disagree. Advisory like every
        other read here: a binding that cannot answer paints ADDRESSED,
        which is honestly what the records alone can say.
        """
        try:
            return self._ctx.attempted_work_keys()
        except Exception:                    # observer reads are advisory
            return frozenset()


__all__ = [
    "CaptureMark", "PaneModel", "PaneModelError", "PaneSource", "RegionMark",
    "TilePlane", "UNDERLAY_MAX_PIXELS", "UNDERLAY_TARGET_PX", "WINDOW_DONE",
    "WINDOW_PENDING", "WINDOW_POSED", "WINDOW_RETIRED", "WindowMark",
]

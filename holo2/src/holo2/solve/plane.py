"""The derived plane: what a session schedules over, and what a worker sees.

R2 split ``engine/runtime.py`` along package lines. This is the half the
engine could not keep: the physical plane and everything derived from it —
the printed row, the authenticated captures, their footings, the surveyed
regions on their pose-free lattices, the window plans, the tile map, the
store index and the §6 done projection. Every one of those is a
``format``, ``capture`` or ``solve`` type, so the object that hands them
out belongs in the package that legitimately knows all three; the engine
relays it to providers and workers as ``core.SolveView`` and never looks
inside (``engine.session.Plane``).

It is therefore also the concrete :class:`~holo2.solve.view.PlaneView`:
what a provider and a worker are handed is exactly this object, granting
reads and only reads. Commit, lifecycle and cache invalidation stay on the
engine's ``SessionContext``, which owns this plane and tells it when its
derived views died.

Choices where DESIGN is silent (for adjudication, carried from the module
this split):

- **A terminal session is opened and nothing else.** Its ``CloseRecord``
  is immutable (§5.5), so re-ingesting captures would be work whose only
  possible outcome is a refused commit. :func:`open_plane` therefore
  reads the store's terminality itself and returns an empty plane.
- **H3/H4: the plane is read-concurrent, not write-concurrent.** Workers
  propose in parallel (§10.1) and every one of them reads this object, so
  two things are pinned here rather than left to luck: the store-derived
  views live in :class:`_DerivedViews`, one generation-stamped object a
  commit REPLACES instead of a reader rebuilding it in place, and a fire
  PINS one generation for its whole run (:meth:`pin_views`, taken where a
  worker's view is born — ``solve.view.as_plane``); and blob READS go
  through one lock, because ``BlobSidecar`` reads through a mapping it
  may replace. Since R1 nothing on the worker side APPENDS — proposals
  stage their bulk values and the commit authority materialises them — so
  the sidecar's one shared file offset is touched on the main thread
  only.

  Before H4 the barrier did this job: reader threads memoised derived
  views into the plane itself, and a ``warm`` shim materialised all of
  them on the main thread before each dispatch round. Under continuous
  admission (H4 W-S) commits interleave with running fires, so that
  memoisation was a data race and one fire could see two generations.
  What a PIN costs is staleness, and staleness is already priced: the §7
  identity re-derivation at admission discards a proposal whose read-set
  moved, so a stale read yields waste, never corruption. Commits stay
  main-thread-only (L11), which is what lets :meth:`invalidate` state
  the other half of the rule — the committing thread's own pin died with
  the views it named.

``_DerivedViews`` itself, and the descriptor budget beside it, live in
``solve/plane_views.py`` since the 1000-line cap named that seam
(2026-08-17). The PIXEL side — the rung frames, the per-rung attachment
gate and the prepared planes — left the same way at H4-LANES stage 2, into
``solve/plane_pixels.py``: a mixin, so every body reads ``self`` exactly
as it did here (that file's docstring states why a helper object could
not).
"""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import numpy as np

from ..capture import (FAMILY_INGEST, KIND_CAPTURE, KIND_REGION,
                       CaptureRecord, FootingSpec, IngestedCapture, Raster,
                       catalog_captures, open_capture, scan_key)
from ..core import (BlobRef, CaptureSha, CloseRecord, CommitEngine, FootingId,
                    Record, ResourceKey, Store, SubjectSpec, WorkId)
from ..format import FormatRowSpec
from .payload import attempted_work_keys, crc_exposure
from .plane_pixels import PlanePixels, _PreparedKey
from .plane_views import _DerivedViews, ensure_fd_headroom, fd_budget
from .plans import RegionView, WindowPlan, region_view
from .pose_fit import PreparedRegion
from .prepared import PixelSource
from .records import TileRecord
from .tilemap import DoneProjection, StoreIndex, TileMap


@dataclass(frozen=True)
class CaptureView:
    """One acquisition and everything derived from it — pixels optional.

    ``raster`` is ``None`` for a capture attached BY RECORD (B9): the
    geometry below it — footings, regions, lattices, support — is durable
    and answers exactly the same, which is what makes a resume without
    the file a full member of the plane rather than a hole in it.
    """

    raster: Raster | None
    record: CaptureRecord
    footings: tuple[FootingSpec, ...]
    regions: tuple[RegionView, ...]

    @property
    def source_sha256(self) -> CaptureSha:
        return self.record.source_sha256


class SessionPlane(PlanePixels):
    """The derived world over one session's durable state (a ``PlaneView``).

    **The capture set GROWS (H4 streaming ingestion).** Captures,
    their regions and their footings used to be constructor-fixed,
    because assembly ran to completion before the plane existed; they are
    now main-thread-mutated maps, admitted by :meth:`attach_captures` as
    the ingest fires' capture records land. The three rules that make
    that safe are the ones already here:

    * every map is replaced, never edited in place, so a reader holding
      the old dict keeps reading a coherent one (the generation
      discipline, one level up: a ``_DerivedViews`` binds the maps it was
      built with);
    * the mutation happens on the COMMITTING thread only (L11), between
      commits, exactly where ``invalidate`` already ran;
    * and the reopen that produces the raster happens OUTSIDE the views
      lock, because it is the one slow thing on this path (a file open
      and a re-authentication) and a starting fire must not block on it.
    """

    def __init__(self, store: Store, engine: CommitEngine,
                 format_row: FormatRowSpec,
                 captures: tuple[CaptureView, ...],
                 scans: Iterable[tuple[Path, float]] = ()) -> None:
        self._store = store
        self._engine = engine
        self._format_row = format_row
        self._captures = captures
        self._regions = {view.region_id: view
                         for capture in captures for view in capture.regions}
        self._footings = {footing.footing_id: footing
                          for capture in captures
                          for footing in capture.footings}
        #: The scans this invocation was DECLARED (H4 streaming
        #: ingestion), in operator order: the plane is the one object
        #: that can resolve a
        #: declaration to an acquisition, because resolving means opening
        #: the file and hashing it. Two memos hang off it — the sha a
        #: scan authenticated as, and the scans whose capture record
        #: stands and whose pixels are therefore attached here.
        self._scans = tuple((Path(path), float(dpi)) for path, dpi in scans)
        self._scan_sha: dict[tuple[Path, float], CaptureSha] = {}
        self._ingested: dict[tuple[Path, float], CaptureSha] = {}
        # Descriptor headroom, sized to what this session can map. The
        # counts GROW with streaming ingestion, so both arrival paths
        # re-budget: :meth:`attach_captures` on what the plane now maps,
        # and :meth:`invalidate` on what the store now holds. Raise-only,
        # so the monotone counts fit exactly and the syscall is bounded
        # by arrivals.
        self._fd_target = 0
        self._rebudget(len(self._captures), len(self._regions))
        # The generation counter, the views built for it, and the lock
        # that swaps the two together. Held only across the (cheap)
        # construction of the next generation's container — never across
        # a build, which is the generation's own lock's job.
        self._views_lock = threading.Lock()
        self._generation = 0
        self._views: _DerivedViews | None = None
        #: The generation THIS thread reads, for as long as it is in one
        #: fire. Absent on a thread that has not pinned, which reads the
        #: current generation per call (the commit thread, between
        #: commits: it is the one that would have invalidated).
        self._pin = threading.local()
        self._blob_lock = threading.Lock()
        # The SESSION-LIFETIME pixel memo (H4 W1a). A prepared region is a
        # function of the capture's pixels and its survey — immutable for
        # the whole session — so it does not belong in a generation's
        # derived views: a commit does not change a prepared plane, and
        # keying it by generation would rebuild it at every one. Built
        # double-checked, read-only once written.
        # The platen backing used to sit beside it, memoised the same way
        # and computed from the raster's borders; since ``CaptureRecord``
        # v3 it is a RECORD (2026-08-17), so there is nothing to memoise
        # and the lock no longer has to be re-entrant.
        self._memo_lock = threading.Lock()
        self._prepared: dict[_PreparedKey, PreparedRegion] = {}
        #: And the NEGATIVE half of it, for the reuse-only door only:
        #: keys whose planes are not on disk, mapped to the capture whose
        #: pixels would supply them. It exists because the M12 gate asks
        #: this question per WINDOW at every refresh, and answering it
        #: costs a SHA-256 over the whole support mask (``prepared``
        #: hashes the mask's own cells into the name) — free once, and a
        #: real per-refresh cost over a region's worth of windows.
        #: Sound because a "no" from that door can only become a "yes"
        #: through an attach, and an attached capture never reaches the
        #: door at all: :meth:`_admit_capture` drops the capture's
        #: entries as its raster lands. Replaced, never mutated, and
        #: written under the memo lock from both sides.
        self._unprepared: dict[_PreparedKey, CaptureSha] = {}
        #: The SUB-NATIVE rungs this session has opened (H4-LANES stage
        #: 1), one read-only mapping each. Session-lifetime like the
        #: prepared planes and for the same reason — a rung is a function
        #: of the authenticated bytes and an exact rational scale, so no
        #: commit can change one — and written under the memo lock, which
        #: is the only place it is touched (:meth:`_footing_source`).
        #: No NEGATIVE half: an absent rung costs one ``stat``, not a
        #: SHA-256 over a support mask, so there is nothing to remember.
        self._footing_rasters: dict[FootingId, PixelSource] = {}

    # -- the physical plane ------------------------------------------------

    @property
    def format_row(self) -> FormatRowSpec:
        return self._format_row

    @property
    def captures(self) -> tuple[CaptureView, ...]:
        return self._captures

    def raster(self, capture_sha256: CaptureSha) -> Raster | None:
        """The authenticated raster, or None when it is not attached (M12)."""
        capture = self._capture(capture_sha256)
        return None if capture is None else capture.raster

    def _capture(self, capture_sha256: CaptureSha) -> CaptureView | None:
        """The plane's view of one acquisition — pixels or no pixels."""
        for capture in self._captures:
            if capture.source_sha256 == capture_sha256:
                return capture
        return None

    def detached_captures(self) -> tuple[CaptureSha, ...]:
        """Captures this session holds BY RECORD only — no pixels attached.

        The honest half of B9, named so recovery can quote it: a resume
        handed fewer files than the store knows carries every durable fact
        of those captures and none of their pixels. Ordinary and correct
        on its own (M12 sleeps the pixel work); the one place it is fatal
        is a crash-cut re-earn that must re-execute a recorded pixel pass,
        and ``engine.replay`` turns exactly this list into the operator's
        remedy.
        """
        return tuple(sorted(capture.source_sha256
                            for capture in self._captures
                            if capture.raster is None))

    # -- streaming ingestion (H4) ------------------------------------------

    def scan_capture(self, path: Path, dpi: float) -> CaptureSha | None:
        """The acquisition a DECLARED scan was ingested as, or None.

        The one question the ingest provider asks (``solve.ingest``), and
        the reason it is asked HERE: "has this scan been ingested?" is a
        question about the store's capture records, but a path and a DPI
        cannot name one — only the file's own SHA-256 can, and learning
        that means opening the file. The plane is where the file gets
        opened (attach-by-reopen), so the plane is where the resolution
        memo lives; everybody else asks it.

        ``None`` means "declared and not yet resolved to a standing
        capture record", which is exactly the frontier the provider
        expands from.
        """
        return self._ingested.get((Path(path), float(dpi)))

    def attach_captures(self, shas: Iterable[CaptureSha]) -> bool:
        """ATTACH-BY-REOPEN: give the plane pixels for captures it holds.

        The committing thread's half of streaming ingestion (point 3 of
        five). An ingest fire proposes a capture record and its regions
        and then DROPS the raster it opened — nothing crosses the wall but
        facts — so when the commit lands, the plane opens its own handle
        to the file the declaration names, admits a ``CaptureView`` for
        it, and the region views, footings and window plans that follow
        enter the maintained maps exactly as a late finer footing's do.

        The same call serves a RESUME: a session whose store already
        holds capture records opens with them CATALOGUED (pixels absent,
        B9), and this walk upgrades the ones whose file the operator
        declared — attach-by-reopen only when the scan is present, so a
        resume with no ``--scan`` keeps every durable fact and simply has
        no pixels, which is M12's case and is unchanged.

        The walk is by DECLARATION ORDER and stops as soon as every asked
        sha is placed, so the ordinary streaming case opens exactly one
        file per arrival: the derivation chain means the capture that
        just landed is the first unresolved scan. A scan opened and not
        matched keeps its sha in the memo, so it is never hashed twice
        for the same question.

        TWO DECLARED PATHS, ONE ACQUISITION — handled, not merely stated
        (2026-08-17): identical bytes drop the second scan's write as an
        L10 no-op, so this walk never runs for it; :meth:`invalidate`
        resolves it off the spend instead (:meth:`_resolve_duplicate_scans`).
        """
        outstanding = set(shas) - {capture.source_sha256
                                   for capture in self._captures
                                   if capture.raster is not None}
        if not outstanding:
            return False
        admitted = False
        for scan in self._scans:
            if not outstanding:
                break
            if scan in self._ingested:
                continue
            raster = None
            sha = self._scan_sha.get(scan)
            if sha is None:
                raster = open_capture(scan[0], scan[1])
                sha = CaptureSha(raster.source_sha256)
                self._scan_sha[scan] = sha
            if sha not in outstanding:
                continue
            if raster is None:
                raster = open_capture(scan[0], scan[1])
            self._admit_capture(sha, raster)
            outstanding.discard(sha)
            self._ingested[scan] = sha
            admitted = True
        if admitted:
            self._rebudget(len(self._captures), len(self._regions))
        return admitted

    def _admit_capture(self, capture_sha256: CaptureSha,
                       raster: Raster) -> None:
        """One capture, into the maintained maps. Committing thread only.

        Built from the DURABLE records in both directions — a capture
        that just arrived is read back through the catalog (the inverse
        ``capture`` owns), and a catalogued one already here keeps its
        view and gains the raster — so what the plane holds after an
        ingest is what a resume would rebuild from the same store, by
        construction rather than by agreement.

        Every map is REPLACED, never edited: a fire pinned to an older
        generation goes on reading the dicts it was built with (the
        class docstring's first rule).
        """
        captures = list(self._captures)
        position = next((index for index, view in enumerate(captures)
                         if view.source_sha256 == capture_sha256), None)
        if position is None:
            (ingested,) = catalog_captures(self._store,
                                           select=capture_sha256)
            view = capture_view(self._format_row,
                                replace(ingested, raster=raster),
                                ingested.record.dpi_true)
            captures.append(view)
        else:
            view = replace(captures[position], raster=raster)
            captures[position] = view
        self._captures = tuple(captures)
        self._regions = {**self._regions,
                         **{region.region_id: region
                            for region in view.regions}}
        self._footings = {**self._footings,
                          **{footing.footing_id: footing
                             for footing in view.footings}}
        # The pixels just arrived, so every "not on disk" this capture's
        # regions collected through the reuse-only door is stale: the
        # build path can make those planes now. Under the memo lock, so
        # the drop cannot lose a concurrent write (and never nested — no
        # preparation reaches this method).
        if any(sha == capture_sha256 for sha in self._unprepared.values()):
            with self._memo_lock:
                self._unprepared = {
                    key: sha for key, sha in self._unprepared.items()
                    if sha != capture_sha256}

    def _resolve_duplicate_scans(self, spent: Iterable[WorkId]) -> None:
        """Off the ATTEMPT, not the write (see ``attach_captures``): an
        ingest-family scan still unresolved after a spend in ``spent``
        can only be a duplicate, so :meth:`_mark_duplicate` opening it
        only confirms a sha already in ``self._captures``.
        """
        for work_id in spent:
            if work_id.family != FAMILY_INGEST:
                continue
            for scan in self._scans:
                if scan_key(scan[0], scan[1]) != work_id.subject:
                    continue
                if scan not in self._ingested:
                    self._mark_duplicate(scan)
                break

    def _mark_duplicate(self, scan: tuple[Path, float]) -> None:
        """Honest, because true: this scan's bytes ARE the sha's
        acquisition — no new ``CaptureView``, one stderr line."""
        sha = self._scan_sha.get(scan)
        if sha is None:
            raster = open_capture(scan[0], scan[1])
            sha = CaptureSha(raster.source_sha256)
            self._scan_sha[scan] = sha
        self._ingested[scan] = sha
        original = next(
            (path for (path, dpi), resolved in self._ingested.items()
             if resolved == sha and (path, dpi) != scan), None)
        sys.stderr.write(
            f"confetti2: declared scan {scan[0]} duplicates "
            f"{original or 'an already-ingested capture'} "
            f"(sha {sha[:12]}…); dropped\n")

    def _rebudget(self, captures: int, regions: int) -> None:
        """Raise the descriptor budget to fit what this session can map."""
        budget = fd_budget(captures, regions)
        if budget > self._fd_target:
            self._fd_target = budget
            ensure_fd_headroom(budget)

    def platen_backing(self, capture_sha256: CaptureSha) -> float | None:
        """The capture's platen backing, READ OFF ITS RECORD.

        The one region-wide SCALAR the placement kernel needs (a median
        over the four 32-px platen borders): every unsupported pixel of
        every region is filled to it, and ``solve.prepared`` hashes it
        into a prepared plane's file name.

        It used to be computed here, once per session, from the raster's
        own borders — which made it durable NOWHERE, so a resume without
        the file could not even name the prepared planes it already had on
        disk (2026-08-17). Its producer knows it: an ingest holds the
        pixels, so ``CaptureRecord`` v3 carries it and this is a record
        read. ONE source of truth — there is no session-computed
        fallback, because a second way of getting this number is a second
        number, and the file names hang off it.

        ``None`` only where the plane holds no such capture at all.
        """
        capture = self._capture(capture_sha256)
        return None if capture is None else capture.record.platen_backing

    # -- the footing ladder's pixels (H4-LANES stage 1) ---------------------
    #
    # ``derived_directory``, ``footing_frame``, ``has_footing_pixels``,
    # ``prepared_region`` and their four helpers live in
    # ``solve/plane_pixels.py`` since stage 2's opener split (the cap named
    # the seam). They are still exactly these methods on exactly this
    # object — ``SessionPlane`` inherits them — and they still read the
    # maps above, which is why the split is a mixin and not a helper.

    def region(self, region_id: ResourceKey) -> RegionView:
        return self._regions[region_id]

    def footing(self, footing_id: FootingId) -> FootingSpec:
        return self._footings[footing_id]

    def has_footing(self, footing_id: FootingId) -> bool:
        return footing_id in self._footings

    def has_region(self, region_id: ResourceKey) -> bool:
        return region_id in self._regions

    def footing_depth(self, footing_id: FootingId) -> int:
        """This rung's index from the COARSEST of its capture's ladder.

        THE LANE TERM's one input (H4-LANES stage 2). Placement prices
        every tier at ``tier + 2*depth`` and payload prices a scan or a
        retry the same way, so both ask the plane rather than each
        deriving a ladder of its own — the plane is the object that holds
        the footings, and a second derivation is a second answer.

        0-based and per CAPTURE, because a ladder is: two captures at the
        same declared dpi have the same ppc values, and one at a
        different dpi does not, so ranking within the capture is what
        makes "coarse" mean the same thing on both. A footing this plane
        does not hold answers 0 — the price of an unknown lane is the
        cheapest one, since a pricing question is not a place to refuse.
        """
        footing = self._footings.get(footing_id)
        if footing is None:
            return 0
        ladder = sorted({spec.ppc for spec in self._footings.values()
                         if spec.capture_sha256 == footing.capture_sha256})
        return ladder.index(footing.ppc)

    def footing_ids(self, selector: str) -> tuple[FootingId, ...]:
        """Footings a recipe entry runs on (§9 ``footing_selector``)."""
        chosen: list[FootingId] = []
        for capture in self._captures:
            if not capture.footings:
                continue
            coarsest = min(footing.ppc for footing in capture.footings)
            for footing in capture.footings:
                if selector == "all":
                    chosen.append(footing.footing_id)
                elif selector == "coarsest" and footing.ppc == coarsest:
                    chosen.append(footing.footing_id)
                elif selector == "finer" and footing.ppc != coarsest:
                    chosen.append(footing.footing_id)
        return tuple(sorted(chosen))

    def window_plans(self, footing_id: FootingId) -> tuple[WindowPlan, ...]:
        """The v1-shaped window lattice of one footing (§8.2), cached."""
        return self._derived().window_plans(footing_id)

    # -- the fact plane ----------------------------------------------------

    def index(self) -> StoreIndex:
        return self._derived().index()

    def tiles(self) -> TileMap:
        return self._derived().tiles()

    def record(self, key: ResourceKey) -> Record | None:
        return self._store.get(key)

    def version(self, key: ResourceKey) -> int:
        """Version as the SCHEDULER holds it — derived collections included.

        Read from the resource table, not the store: a collection key has
        no record, and its version IS its membership count — the cheap
        frontier digest an expensive consult tests before materialising
        anything (M11).
        """
        return self._engine.table.version(key)

    def tile(self, key: ResourceKey) -> TileRecord | None:
        return self.tiles().record(key)

    def open_work_keys(self) -> tuple[ResourceKey, ...]:
        return self.tiles().open_keys()

    def certified_work_keys(self) -> tuple[ResourceKey, ...]:
        return self.tiles().certified_keys()

    def evidence_on(self, key: ResourceKey) -> tuple[ResourceKey, ...]:
        return self.index().evidence_by_tile.get(key, ())

    def poses_of_window(self,
                        window_id: ResourceKey) -> tuple[ResourceKey, ...]:
        return self.index().poses_by_window.get(window_id, ())

    def subjects(self, family: str) -> tuple[SubjectSpec, ...]:
        subjects = self.index().subjects
        return tuple(subjects[subject_id] for subject_id in sorted(subjects)
                     if subjects[subject_id].family == family)

    # Bulk READS are all a proposing worker touches (R1: proposals stage
    # their bulk values and the commit authority materialises them). The
    # sidecar reads through a mapping it may replace, so the read path
    # holds one lock, for a memcpy, never across a commit.

    def read_array(self, ref: BlobRef) -> np.ndarray:
        with self._blob_lock:
            return self._store.read_array(ref)

    def read_blob(self, ref: BlobRef, *, verify: bool = False) -> memoryview:
        with self._blob_lock:
            return self._store.read_blob(ref, verify=verify)

    # -- the done projection (§6) ------------------------------------------

    def done(self, region_id: ResourceKey) -> DoneProjection:
        """The §6 done projection of one region, derived and cached.

        The cache key is the pair of **monotone** counts the projection is
        a function of — committed poses and certified work keys. Both only
        grow (§7 termination), so equal counts mean an equal projection,
        and a commit that touched neither costs no recomputation: the new
        generation inherits the whole map (:meth:`_DerivedViews.done`).
        """
        return self._derived().done(region_id)

    def window_is_done(self, plan: WindowPlan) -> bool:
        """§6 gate: never create, pose, search or wake a done-covered window."""
        view = self._regions[plan.region_id]
        if not view.schedulable:
            return False
        assert view.support is not None
        return self.done(plan.region_id).covers(plan.extent_cells,
                                                view.support)

    # -- generations (H4 W-S) ----------------------------------------------

    def pin_views(self) -> None:
        """Pin this thread to ONE generation of the derived views.

        Taken where a worker's view is born (``solve.view.as_plane``), so
        a fire reads one generation from its first read to its last and
        the engine needs to know nothing about it. Re-pinning is what
        starts the NEXT fire on this thread: a pool thread between fires
        reads nothing, and the commit thread re-pins at every arm and
        every admission (both go through ``read_keys``) on top of the
        drop in :meth:`invalidate`.

        A pin can go stale — that is the point of admitting commits while
        fires run — and staleness is priced where §7 already prices it:
        the identity re-derivation at the wall discards a proposal whose
        read-set moved. Waste, never corruption.
        """
        self._pin.views = self._current_views()

    def _derived(self) -> _DerivedViews:
        """The generation this reader reads: its pin, or the current one."""
        pinned: _DerivedViews | None = getattr(self._pin, "views", None)
        return self._current_views() if pinned is None else pinned

    def _current_views(self) -> _DerivedViews:
        """The current generation's views, built once, on first request."""
        with self._views_lock:
            views = self._views
            if views is None or views.generation != self._generation:
                views = _DerivedViews(self._store, self._format_row,
                                      self._regions, self._footings,
                                      self._generation, views)
                self._views = views
            return views

    # -- what the engine drives --------------------------------------------

    def invalidate(self,
                   changed_keys: Iterable[ResourceKey] | None = None, *,
                   spent: Iterable[WorkId] = ()) -> None:
        """The commit authority committed: the store-derived views died.

        ``changed_keys`` is the commit's own delta
        (``CommitResult.changed_keys``), and passing it is what lets the
        store index be ADVANCED into the next generation instead of
        rebuilt from the store's sorted keys (F-17, ``_DerivedViews``).
        Omitting it is the honest "I do not know what moved" and costs a
        full rebuild at the next touch — which is the answer a caller
        outside the commit path (a test, a repair) should get.

        Everything else is unchanged: a fire already holding the old
        generation keeps reading it, coherently, and is discarded at the
        wall if what it read moved. The committing thread's own pin dies
        here too — commits are main-thread-only (L11), so the one thread
        that reaches this line is never inside a fire.

        SINCE STREAMING INGESTION THIS IS ALSO THE ATTACH POINT: a
        commit carrying a capture record is an ingest fire landing, and
        the plane opens that capture's pixels before the next generation
        is built, so the generation a reader pins already holds the new
        capture's regions, footings and window plans. The reopen is
        deliberately OUTSIDE the lock below — it is a file open, and no
        starting fire should wait on one.

        ``spent`` (2026-08-17) is the commit's spend work ids, off which
        :meth:`_resolve_duplicate_scans` runs (its own docstring: why).
        """
        delta = None if changed_keys is None else tuple(changed_keys)
        if delta is not None:
            arrived = tuple(CaptureSha(key.parts[0]) for key in delta
                            if key.kind == KIND_CAPTURE)
            if arrived:
                self.attach_captures(arrived)
        self._resolve_duplicate_scans(spent)
        changed_keys = delta
        with self._views_lock:
            views = self._views
            advanced = (None if views is None
                        or views.generation != self._generation
                        else views.advance_index(self._store, changed_keys))
            self._generation += 1
            if advanced is not None:
                self._views = _DerivedViews(
                    self._store, self._format_row, self._regions,
                    self._footings, self._generation, views, index=advanced)
            # Otherwise the stale object stays put and the next reader
            # builds off it as ``carried`` — the pre-F-17 path, whole.
        self._pin.views = None
        # Descriptor re-budget on capture/region arrivals only — free for
        # every ordinary commit, and the seam streaming ingestion grew
        # through. Counts come off the advanced index (the STORE's truth,
        # which is the wider of the two: it counts a capture whose pixels
        # this session never attached); raise-only keeps the syscall
        # bounded by arrivals.
        if advanced is not None and changed_keys is not None and any(
                key.kind in (KIND_CAPTURE, KIND_REGION)
                for key in changed_keys):
            self._rebudget(len(advanced.captures), len(advanced.regions))

    # -- observation (L12: derived, never state) ---------------------------
    #
    # THE THREE NARROW READS BELOW ARE F-02's CLOSE (H4 W6, 2026-08-18).
    # They replaced a ``store`` property that handed the observer — and
    # therefore anything holding a plane — the whole ``core.Store``, a
    # grant far wider than ``PlaneView`` declares and read-only only by
    # convention. Each read is one typed value the observer already had a
    # right to (the frame's revision, the close verdict, the ATTEMPTED
    # key set), so the surface is the same information through a door the
    # type system can see. Nothing in ``solve`` needs the property: the
    # plane's own reads go through ``self._store`` as they always did.

    @property
    def commit_seq(self) -> int:
        """The store's commit sequence: the observer's FRAME IDENTITY.

        Work-counted, never a clock (the conventions test is repo-wide),
        and monotone, so a viewer can tell one frame from the next and
        cache on it. It is the store's own counter and not a second one:
        a plane that invented its own could disagree with the state the
        frame was derived from.
        """
        return self._store.commit_seq

    def close_record(self) -> CloseRecord | None:
        """The volume close's verdict, or ``None`` while it is open.

        One durable record read by key. The observer paints the close
        status and the recovered payload's digest off it, which is the
        whole of what it wanted the store for.
        """
        return self._store.close_record()

    def attempted_work_keys(self) -> frozenset[ResourceKey]:
        """Work keys a decoder has run on, off the durable spend ledger.

        Since tile family v4 the ATTEMPTED rank is DERIVED, and the
        counting rule belongs to the payload family (the module function
        of the same name); what the plane knows is where the ledger
        lives. Both readers ask here now — this class's own tile tally
        (:meth:`observer_summary`) and the pane model's chips — so the
        two cannot come to differ about which spends count.
        """
        return attempted_work_keys(self._store.ledger.entries())

    def observer_summary(self) -> dict[str, object]:
        """The three derived views the observer publishes, in one mapping.

        The engine asks once and spreads the answer under these key names
        (``engine.Plane.observer_summary``): what the plane hands back IS
        what the status surface says, so adding a summary is a change
        here and nowhere else. Derived, never state — and derived on the
        MAIN thread: the observer publishes at a commit boundary, and
        that is the thread whose reads are the current generation by
        construction (it holds no pin outside a fire, :meth:`pin_views`).

        The tile tally's ATTEMPTED rank is derived off the SAME ledger
        the exposure count reads (tile family v4): a payload spend that
        burned CRC exposure names its work key, which is the fact the
        deleted state field used to copy.
        """
        return {
            "tiles": self.tiles().counts(self.attempted_work_keys()),
            "crc_exposure": self._crc_exposure(),
            "done_coverage": self._done_coverage(),
        }

    def _crc_exposure(self) -> dict[str, object]:
        """L5's false-accept exposure, COUNTED off the durable ledger.

        One CRC-bearing payload attempt is one ledger exposure since the
        per-route split,
        so the number the review asked for ("how many CRC invocations
        occurred") is arithmetic over spend rows rather than an estimate
        over fires. The counting RULE belongs to the payload family, which
        owns the outcome vocabulary; the plane only knows where the ledger
        lives.
        """
        return crc_exposure(self._store.ledger.entries())

    def _done_coverage(self) -> dict:
        """Per capture, per schedulable region: supported vs done cells."""
        coverage: dict[str, dict] = {}
        for capture in self._captures:
            regions: dict[str, dict] = {}   # keyed by display id
            for view in capture.regions:
                if not view.schedulable:
                    continue
                assert view.support is not None
                projection = self.done(view.region_id)
                supported = int(view.support.sum())
                regions[str(view.region_id)] = {
                    "supported_cells": supported,
                    "done_cells": projection.done_cells,
                    "done_runs": len(projection.runs()),
                }
            coverage[capture.source_sha256[:12]] = regions
        return coverage


def capture_view(format_row: FormatRowSpec, ingested: IngestedCapture,
                 dpi: float) -> CaptureView:
    """Pair one capture with the lattices its regions live on.

    Attached or catalogued: the lattice is a function of the declared dpi
    and the region's own surveyed pitch vote, and both are durable, so
    this arithmetic does not care whether pixels came with them.
    """
    return CaptureView(
        ingested.raster, ingested.record, ingested.footings,
        tuple(region_view(format_row, candidate, dpi)
              for candidate in ingested.candidates))


def open_plane(store: Store, engine: CommitEngine, format_row: FormatRowSpec,
               scans: Iterable[tuple[Path, float]]) -> SessionPlane:
    """CATALOGUE what the store holds, attach what is declared, derive.

    **No file is surveyed here any more (H4 streaming ingestion).**
    Opening a session used to mean ingesting every declared capture
    first — nine platens of
    surveys before the orchestrator's first fire — and ingest is work
    now: the plane opens holding only what the STORE already knows, and
    the declared scans arrive as ingest descriptors
    (``solve.ingest.RealIngestProvider``), each fire's capture record
    attaching through :meth:`SessionPlane.attach_captures`.

    A terminal session is opened and nothing else (choice above): the
    plane is empty, and no capture file is even read.

    What the catalog gives is the point of F-05/D5c: a known capture's
    footings, regions and lattices come back BY RECORD, so a resume that
    was handed no file at all still holds everything its durable evidence
    cites and can carry the decode forward. Pixel work on such a capture
    declines and sleeps on ``attachment_key`` (M12) instead of dying.
    The attach walk that follows is what makes a resume WITH the file
    whole again: it reopens the declared scans whose capture record
    already stands, which is the same act — and the same code — an
    ingest arrival takes mid-run, minus the survey nobody needs twice.

    **The B9 rule still holds and is now structural**: an attached
    capture's fresh survey wins over its durable regions, because the
    only way pixels reach this plane at all is a survey that was
    committed — either by this run's ingest fire or by an earlier run's.
    The two agree by construction (every id is content-derived, so equal
    bytes at an equal declared dpi give equal regions), and F-08 refuses
    loudly if a re-derivation ever disagrees.
    """
    if store.is_terminal():
        return SessionPlane(store, engine, format_row, ())
    catalogued = tuple(
        capture_view(format_row, ingested, ingested.record.dpi_true)
        for ingested in catalog_captures(store))
    plane = SessionPlane(store, engine, format_row, catalogued, scans)
    plane.attach_captures(view.source_sha256 for view in catalogued)
    return plane


__all__ = ["CaptureView", "SessionPlane", "capture_view", "open_plane"]

"""One generation of the plane's derived world, and the budget it maps in.

Two things the plane USES rather than IS, lifted out of ``plane.py`` when
that file reached the 1000-line cap (2026-08-17). The cap is a seam
signal, and the seam it named is the one that module already had a name
for: what :class:`~holo2.solve.plane.SessionPlane` MAINTAINS — the
physical plane, its captures, the maps that grow under streaming
ingestion — against what is DERIVED from one state of the store and dies
with it.

* :class:`_DerivedViews` is that derived world: ONE generation, built
  lazily, REPLACED whole at a commit and PINNED for a fire's whole run.
  It reads the store and the maps the plane hands it, and names no plane
  type at all, which is what lets it sit below the plane rather than
  beside it — the import runs one way, ``plane`` -> ``plane_views``, and
  never back.
* the descriptor budget (:func:`fd_budget`, :func:`ensure_fd_headroom`)
  is arithmetic over the two counts the plane re-budgets on, plus one
  raise-only syscall. It touches no plane state whatever, and lived in
  ``plane.py`` only because that is where the counts are known.

What did NOT move is the argument for either: the generation discipline's
concurrency reasoning and the main-thread-only commit rule stay stated
where they are enforced — the ``plane`` module docstring and
:meth:`~holo2.solve.plane.SessionPlane.invalidate`.
"""
from __future__ import annotations

import resource
import sys
import threading
from typing import Iterable, Mapping

import numpy as np

from ..capture import FootingSpec
from ..core import FootingId, ResourceKey, Store
from ..format import FormatRowSpec
from .plans import RegionView, WindowPlan, window_plans_for
from .tilemap import DoneProjection, StoreIndex, TileMap, project_done

# --- file-descriptor headroom (user ruling 2026-08-17) --------------------
#: The scrap demo died with Errno 24 at macOS's default soft limit of 256,
#: and the arithmetic is the pixel doctrine's own: every live mapping PINS
#: one descriptor (CPython's mmap dup()s it internally), so the budget
#: scales with MAPPED OBJECTS — one raw raster per capture plus three
#: prepared planes per (region, lane) — not with "files open" in the
#: colloquial sense. Single-region sheets hid it; nine platens of ~20
#: scrap regions each did not. The terms are deliberately GENEROUS
#: (resolution lanes multiply the planes per region): a budget wrong by
#: 2x costs nothing — descriptors are cheap kernel objects — while a
#: tight one costs a run at hour N.
#:
#: RAISED at H4-LANES stage 1, because the lanes the generosity was FOR
#: now have a count. The longest ladder the receiver can be handed is a
#: c3 sheet captured at 4800 dpi — ``auto_ppc_levels`` gives 2, 4, 8, 12,
#: 24, so FIVE rungs — and each capture maps its scan plus the four
#: sub-native rasters (5), while each region maps three prepared planes
#: per rung (15) plus the build's own temporaries. The old terms (4 and
#: 16) were both short of that by a hair, which is precisely the shape of
#: failure this budget exists to prevent, so they move to 8 and 32: one
#: doubling of the real worst case each, in the direction the comment
#: above already declared. Raise-only, here and at the syscall.
FD_FIXED = 256        # state dir, diag socket, python/env, pool slack
FD_PER_CAPTURE = 8    # the scan mapping + one per sub-native rung (max 4)
FD_PER_REGION = 32    # 3 planes x 5 rungs, doubled for aperture variants
FD_FLOOR = 1024


def fd_budget(captures: int, regions: int) -> int:
    """The generous mapped-object arithmetic, monotone in both counts."""
    return max(FD_FLOOR, FD_FIXED + FD_PER_CAPTURE * captures
                                  + FD_PER_REGION * regions)


def ensure_fd_headroom(budget: int) -> None:
    """Raise-only soft-limit bump to ``budget``, clamped to the hard limit.

    Never lowers and never fatal: an unprivileged process may raise its
    soft limit up to the hard one, and that is all this does. If the hard
    limit itself sits below the budget, ONE stderr advisory names the
    number the operator must raise (the F-12 closure-advisory precedent:
    stderr, once, the run proceeds — it may still fit if residency stays
    below the budget, and if it does not, the eventual Errno 24 now has
    its explanation on record instead of arriving bare at hour N).
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft >= budget:
        return
    target = budget if hard == resource.RLIM_INFINITY else min(budget, hard)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError):
        target = soft
    if target < budget:
        sys.stderr.write(
            f"confetti2: descriptor budget {budget} exceeds the hard limit "
            f"({hard}); soft limit now {target} — raise the hard limit "
            "(`ulimit -Hn` / `launchctl limit maxfiles`) before "
            "archive-scale sessions\n")


class _DerivedViews:
    """ONE generation of the plane's derived views, shared by every reader.

    A generation is a state of the durable store: the plane bumps it when
    the commit authority commits (:meth:`SessionPlane.invalidate`) and
    hands out a new object, so nothing here is ever mutated into a
    different answer under a reader. What IS lazy is which views have been
    built: each is computed at most once, on first touch, behind this
    generation's own lock — exactly what a serial run computed on first
    touch before H4, and exactly what the barrier's read barrier computed
    once per round.

    THREE of the four views outlive the generation that built them and
    are therefore CARRIED into the next one instead of rebuilt, which is
    what keeps the rebuild cost what it has always been:

    - a window lattice is a function of a footing and the regions of that
      footing's OWN capture (§8.2), and a capture arrives with its whole
      surveyed region set in one batch (``capture.ingest``), so a footing's
      plans are fixed from the moment the footing exists and never die —
      the pre-H4 plane never invalidated them either. Streaming ingestion
      (H4) made the region MAP grow, which does not touch that: a new
      capture's regions can only produce plans for its own new footings,
      which have no carried entry to be wrong;
    - a done projection is a function of the two monotone counts §7
      terminates on, committed poses and certified work keys, so a commit
      that moved neither carries the whole map forward (that cache key is
      the pre-H4 rule, restated as an inheritance instead of a clear);
    - **the store index is ADVANCED by the commit's own delta** (F-17,
      2026-08-17), not rebuilt: :meth:`SessionPlane.invalidate` is told
      what moved and hands the next generation
      ``index.updated(store, changed_keys)``. Measured before: 1,921 full
      rebuilds, 54.5 s, 26.3% of the serial wall, to answer a question
      that had moved by a handful of keys.

      The advance is EAGER — taken on the committing thread, inside the
      serial section, at the moment the delta is known — which is what
      makes a generation's index an exact snapshot of the store AT that
      generation. The from-scratch build was never that: it read the
      CURRENT store whenever a reader first touched it, so a fire that
      touched the index late saw records newer than its own pin. The
      eager delta is therefore strictly tighter than what it replaces,
      and the laziness it gives up was worth ~50 µs.
    """

    def __init__(self, store: Store, format_row: FormatRowSpec,
                 regions: Mapping[ResourceKey, RegionView],
                 footings: Mapping[FootingId, FootingSpec],
                 generation: int,
                 carried: "_DerivedViews | None" = None,
                 index: StoreIndex | None = None) -> None:
        self.generation = generation
        self._store = store
        self._format_row = format_row
        self._regions = regions
        self._footings = footings
        # Re-entrant because the builds nest (``tiles`` builds through
        # ``index``, ``done`` through both) and one generation's lock is
        # the natural granularity: every cache HIT returns before taking
        # it, so only builders ever contend, and a reader pinned to an
        # older generation contends with nobody.
        self._lock = threading.RLock()
        self._index: StoreIndex | None = index
        self._tiles: TileMap | None = None
        self._windows: dict[FootingId, tuple[WindowPlan, ...]] = (
            {} if carried is None else carried.carried_windows())
        self._done: dict[ResourceKey, DoneProjection] = {}
        self._done_generation: tuple[int, int] | None = None
        self._carried_done = (None if carried is None
                              else carried.carried_done())

    # -- the four derived views --------------------------------------------

    def index(self) -> StoreIndex:
        cached = self._index
        if cached is not None:
            return cached
        with self._lock:
            if self._index is None:
                self._index = StoreIndex.build(self._store)
            return self._index

    def tiles(self) -> TileMap:
        cached = self._tiles
        if cached is not None:
            return cached
        with self._lock:
            if self._tiles is None:
                self._tiles = TileMap(self.index(),
                                      self._format_row.stream_ids,
                                      self._format_row.tiles_yx)
            return self._tiles

    def window_plans(self, footing_id: FootingId) -> tuple[WindowPlan, ...]:
        cached = self._windows.get(footing_id)
        if cached is not None:
            return cached
        with self._lock:
            plans = self._windows.get(footing_id)
            if plans is None:
                plans = window_plans_for(self._footings[footing_id],
                                         self._regions.values())
                self._windows[footing_id] = plans
            return plans

    def done(self, region_id: ResourceKey) -> DoneProjection:
        cached = self._done.get(region_id)
        if cached is not None:
            return cached
        with self._lock:
            table = self._done_table()
            projection = table.get(region_id)
            if projection is None:
                projection = self._project(region_id)
                table[region_id] = projection
            return projection

    # -- what the next generation inherits ---------------------------------

    def carried_windows(self) -> dict[FootingId, tuple[WindowPlan, ...]]:
        with self._lock:
            return dict(self._windows)

    def advance_index(self, store: Store,
                      changed_keys: Iterable[ResourceKey] | None
                      ) -> StoreIndex | None:
        """This generation's index, advanced by the commit that ends it.

        ``None`` — no index to carry — in the two honest cases: nobody
        ever asked this generation for one, or the caller did not say
        what moved (``changed_keys is None``), which is a full rebuild
        by declaration rather than by accident. The next generation then
        seeds itself from :meth:`StoreIndex.build`, exactly as a resume
        does.
        """
        if changed_keys is None or self._index is None:
            return None
        return self._index.updated(store, changed_keys)

    def carried_done(self) -> tuple[tuple[int, int],
                                    dict[ResourceKey, DoneProjection]] | None:
        """The done map and the counts it is a function of, or None.

        A generation nobody asked a done projection of passes its OWN
        inheritance along instead of ending the chain: which generations
        happened to be touched is a scheduling accident, and the pre-H4
        cache — one map on the plane, stamped with the counts — did not
        pay for one either.
        """
        with self._lock:
            if self._done_generation is None:
                return self._carried_done
            return self._done_generation, dict(self._done)

    # -- interior ----------------------------------------------------------

    def _done_table(self) -> dict[ResourceKey, DoneProjection]:
        """This generation's done map, inherited from the last one once.

        The caller holds the lock. The counts cannot move inside one
        generation — they are read off this object's own index — so the
        inheritance test runs exactly once, on the first done() call.
        """
        index = self.index()
        counts = (len(index.poses), index.certified)
        if counts != self._done_generation:
            carried = self._carried_done
            self._done = (dict(carried[1]) if carried is not None
                          and carried[0] == counts else {})
            self._done_generation = counts
            self._carried_done = None
        return self._done

    def _project(self, region_id: ResourceKey) -> DoneProjection:
        view = self._regions[region_id]
        if not view.schedulable:
            return DoneProjection(view.capture_sha256, region_id,
                                  np.zeros((1, 1), bool))
        index = self.index()
        assert view.lattice is not None and view.support is not None
        # ONE pose per posed window — the LIVE one (tilemap choice 8,
        # RULING I3). Unioning an extent's poses would let a revision that
        # sampled nothing spend pixels; the shared derivation is the
        # index's.
        pose_ids = index.live_poses_of_region(region_id)
        return project_done(
            index, self.tiles(), capture_sha256=view.capture_sha256,
            region_id=region_id, lattice=view.lattice,
            support=view.support, pose_ids=pose_ids)


__all__ = ["FD_FIXED", "FD_FLOOR", "FD_PER_CAPTURE", "FD_PER_REGION",
           "ensure_fd_headroom", "fd_budget"]

"""The tile map, its derived indexes, and the §6 done-pixel projection.

Everything here is a **derived view over the durable store** (DESIGN §5.2,
§5.6): it holds no authority, is rebuilt from records, and is never
persisted. Two things live here:

* :class:`StoreIndex` — the per-kind indexes the scheduler reads
  (tiles, windows, poses, evidence pieces, regions, captures), seeded by
  one pass over the store's sorted keys and MAINTAINED from each commit's
  own ``changed_keys`` thereafter (:meth:`StoreIndex.updated`).
  Deterministic iteration everywhere it is consumed.
* the **done projection** (§6): per capture, the cell-granular set of
  pixels spent by certificates, derived on demand from certificates plus
  committed poses and never stored.
* :class:`TileState` and :func:`tile_state` — §5.2's four-rank vocabulary,
  which since tile family v4 is a DISPLAY view and lives here for that
  reason (the operator's tiles row, pane B's chips). It is not state: a
  record's absence is UNKNOWN, its presence ADDRESSED, its mint
  CERTIFIED, and ATTEMPTED is the spend ledger's payload CRC exposure on
  the key (``payload.attempted_work_keys``) or a failed baseline
  standing on the record.

Choices where DESIGN is silent (for adjudication):

1. **A pose's page is read off the pose** (R3). It used to be derived by
   scanning the keys of the observation pieces the pose produced —
   ``EvidenceObservation``'s key carries the page, ``PoseRecord`` did
   not — so a pose that observed nothing had no derivable page and the
   index carried a whole ``pages_by_pose`` map to answer the question.
   ``PoseRecord.page`` closed that: one pose is one page (§5.4 — a window
   straddling pages fails its fit and subdivides), the field is validated
   in the session's declared page domain, and the derived map is gone.
2. **Done-ness is per work key, and a tile is done only when EVERY stream
   of the format row is CERTIFIED** — the §2 per-stream terminality rule,
   which for K rows is the one ``main`` stream.
3. **The projection is computed on the certifying pose's own region
   grid.** Survey regions are disjoint connected components of one
   capture, and a window is clipped to its region, so a pose's footprint
   cannot reach another region's cells. Cross-region projection would be
   dead code with a cost.
4. **Audited-cells-only, not the full tile rect** (OR-1 left open by
   DESIGN §6/§15): a capture cell is done iff its centre lands inside a
   CERTIFIED tile under a committed pose *and* the cell is supported. The
   erasure extension stays unimplemented until it is ruled.

5. **The index is MAINTAINED, and the from-scratch builder is the
   oracle** (F-17, measured 2026-08-17). :meth:`StoreIndex.build` was
   re-running at every single commit — 1,921 full rebuilds, 28.4 ms each,
   **54.5 s = 26.3% of a serial decode's wall** — to answer a question
   that had moved by a handful of keys. It now runs exactly twice: at
   session open (the resume seed) and inside the equivalence harness
   (``holo2/measure/index_equivalence.py``), where its answer is the
   ORACLE the maintained index is compared against, commit by commit.
   Three properties make the maintenance safe rather than merely fast:

   * **Copy-on-write per generation.** :meth:`updated` returns a NEW
     frozen index and copies only the buckets the delta touches, sharing
     the rest by reference. Nothing is ever mutated under a reader, which
     is the property ``plane_views._DerivedViews`` rests its whole concurrency
     argument on.
   * **The store never retires a key.** ``Store.apply_committed`` only
     ever assigns, so a delta is inserts and replacements — never a
     removal. A changed key the store cannot answer for is a broken
     invariant and raises :class:`TileMapError` rather than silently
     leaving a stale entry behind.
   * **Order is kept exactly where order is CONSUMED.** The two grouped
     views (:attr:`evidence_by_tile`, :attr:`poses_by_window`) are read
     sets whose ORDER is load-bearing — an attempt identity is a tuple of
     (key, version) pairs in that order (§7), and the consult's stable
     sort breaks ties on it — so a delta inserts into them in sorted
     position. The per-kind DICTS are not order-consumed by anybody: the
     audit is ``tilemap`` (sorts at every exit), ``plane._project`` and
     ``diag.panes.model`` — sets, sums and grid assignment, plus ONE
     ordered construction in each of the last two, which since choice 8
     is :meth:`StoreIndex.live_poses_of_region` and SORTS at its own exit
     (it replaced the ``pose_ids`` tuple those two built by walking
     :attr:`windows`), and which :func:`project_done` sorts again before
     reading a single pose. Since choice 8 BOTH derivations are
     first-write order — :meth:`build` walks ``store.records()`` — so the
     dicts no longer drift at all; the harness still compares the ordered
     surfaces exactly and the dicts by value, which is the stronger bar
     either way. The diag half of that audit is MEASURED, not argued
     (2026-08-17,
     ``docs/MEASUREMENTS.md``): 22 composed pane frames rendered off a
     drifted maintained index and off ``build``'s, byte-identical, on
     boundaries where the drift was confirmed present.

6. **A parsed key is parsed once, and the parse lives in the index.**
   :attr:`evidence_footings` is the §5.4 footing of every evidence key,
   read off the one parse the grouping already performs, and
   :attr:`certified_streams` is the (page, ty, tx) grouping of the tile
   keys — the two derived-immutable facts that were being recovered by
   re-parsing strings on every rebuild (12.4 M ``parse_evidence_key``
   calls per run, 14.9% of main-thread CPU). Both are pure functions of
   an immutable key, so a maintained entry cannot go stale; both are
   carried by the copy-on-write above.

7. **The two work-key partitions are maintained, not re-filtered.**
   ``TileMap.open_keys`` (the eligibility domain the payload frontier
   enumerates) and ``TileMap.certified_keys`` (the close's input, and the
   three ``len(...)`` counters beside it) were each a filter-and-sort
   over the WHOLE tile map per call — 5.9 s profiled on the gen-clean
   serial run, and O(tiles) per read on a sheet where one commit moves
   one key. They are :attr:`open_tiles` / :attr:`certified_tiles` now,
   sorted tuples the delta moves one key between; a certification is one
   removal and one insertion. Their order is consumed (expansion order
   reaches descriptor order; the close materialises in this order), so
   the maintenance inserts in sorted position and the harness compares
   them as tuples.

8. **THE LIVE POSE OF AN EXTENT IS THE LATEST COMMITTED ONE** (W3, the
   user's ruling of 2026-08-23, RULING I3: *"the latest committed pose
   for that extent wins"*). RF1 makes a window carry more than one
   committed pose — a revision is a NEW ``PoseRecord`` at a new key and
   the standing pose is never retracted, marked or deleted — so every
   reader that used to assume "the pose of this window" has to say WHICH
   one it means. The answer is a READ-TIME DERIVATION, never a record and
   never a status: :attr:`live_poses` maps a window key to the last pose
   key COMMITTED for it, maintained by the delta (which arrives in commit
   order) and rebuilt by :meth:`build` from the store's first-write order
   — which is durable, and is why ``core.store.Store._frame`` writes its
   rows unsorted (see that method).

   Two consequences worth stating where the derivation lives. The FIRST
   write wins the position, so a re-write of a standing pose (W5's
   quarantine marking is the only one) does not make it live again. And
   liveness is per WINDOW KEY, which carries the footing and the extent
   — ownership-freeze winners and losers are different windows and each
   keeps its own live pose, exactly as §6 requires.
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

import numpy as np

from .generation import pose_of_evidence
from .geometry import (CellLattice, apply_affine, invert_affine,
                       runs_of_mask, tile_of_cell)
from .records import (KIND_CALIBRATION, KIND_EVIDENCE, KIND_POOL, KIND_POSE,
                      KIND_TILE, KIND_WINDOW,
                      CalibrationRecord, PoseRecord, TileRecord, WindowRecord,
                      parse_evidence_key, parse_tile_key, tile_key)
from ..capture import KIND_CAPTURE, KIND_REGION, CaptureRecord, RegionRecord
from ..core import (CaptureSha, FootingId, KIND_SUBJECT, ResourceKey,
                    SubjectSpec)

#: The kinds :class:`StoreIndex` buckets. A changed key of any other kind
#: — a collection, the close record, a lattice seed — moves nothing here,
#: which is what makes most deltas free. CALIBRATION joined at H5 P1 for
#: exactly one bucket (:attr:`StoreIndex.context_fits` — the ADOPTED
#: pool-scoped fits by pool key); the per-window ``pava-v1`` fits every
#: placement emits are tested and dropped in one isinstance-plus-kind
#: check, so the ordinary delta stays as cheap as it was.
INDEXED_KINDS = frozenset({KIND_TILE, KIND_WINDOW, KIND_POSE, KIND_REGION,
                           KIND_CAPTURE, KIND_SUBJECT, KIND_EVIDENCE,
                           KIND_CALIBRATION})


def _pool_fit_scope(record: object) -> ResourceKey | None:
    """The pool an ADOPTED region fit belongs to, or None for every other
    calibration record (window-scoped marginal fits, refused fits)."""
    if (isinstance(record, CalibrationRecord)
            and record.scope.kind == KIND_POOL and record.heldout.adopted):
        return record.scope
    return None


class TileMapError(RuntimeError):
    """A derived view disagrees with the records it was built from."""


class TileState(Enum):
    """§5.2's four ranks, as the OPERATOR reads them. Derived, never state.

    The ranks are the display order the panes paint in and the tiles row
    prints in; nothing durable carries them, and nothing schedules on
    them (the eligibility domain is :meth:`TileMap.open_keys`, which asks
    the records directly).
    """

    UNKNOWN = 0
    ADDRESSED = 1
    ATTEMPTED = 2
    CERTIFIED = 3


def tile_state(record: TileRecord | None, *, attempted: bool) -> TileState:
    """One work key's display rank (§5.2), derived from what is durable.

    ``attempted`` is the caller's ledger fact — a payload spend row that
    burned CRC exposure on this key. A failed baseline standing on the
    record says the same thing about a footing whose decoder ran, and is
    the half that survives a ledger the caller did not consult.
    """
    if record is None:
        return TileState.UNKNOWN
    if record.certified:
        return TileState.CERTIFIED
    if attempted or record.baselined:
        return TileState.ATTEMPTED
    return TileState.ADDRESSED


@dataclass(frozen=True)
class StoreIndex:
    """Per-kind indexes over one snapshot of the durable store."""

    tiles: dict[ResourceKey, TileRecord] = field(default_factory=dict)
    windows: dict[ResourceKey, WindowRecord] = field(default_factory=dict)
    poses: dict[ResourceKey, PoseRecord] = field(default_factory=dict)
    regions: dict[ResourceKey, RegionRecord] = field(default_factory=dict)
    captures: dict[str, CaptureRecord] = field(default_factory=dict)
    # provider-minted subjects (M3), by subject id
    subjects: dict[str, SubjectSpec] = field(default_factory=dict)
    # tile key -> the evidence keys observing it, sorted
    evidence_by_tile: dict[ResourceKey, tuple[ResourceKey, ...]] = field(
        default_factory=dict)
    # window key -> its committed poses, sorted
    poses_by_window: dict[ResourceKey, tuple[ResourceKey, ...]] = field(
        default_factory=dict)
    #: window key -> the LATEST COMMITTED pose of that extent (choice 8).
    #: The one derived answer to "which pose does this window mean now"
    #: once RF1 may commit a second one. Order is the store's first-write
    #: order, which is commit order live and across a resume alike; every
    #: geometry consumer reads THIS and no consumer scans the collection
    #: to find it (RULING I4's cost clause).
    live_poses: dict[ResourceKey, ResourceKey] = field(default_factory=dict)
    #: How many tile records are CERTIFIED. Counted in the build pass
    #: because the §6 done cache asks for it once per descriptor, once per
    #: fire and once per region — a full scan of the tile map each time,
    #: for a number this pass already walks past.
    certified: int = 0
    #: (page, ty, tx) -> the streams CERTIFIED there (choice 6). The §6
    #: done grid is a projection of exactly this, so it is derived where
    #: the tile keys are already being parsed instead of by rebuilding
    #: ``tiles_y x tiles_x x streams`` keys at every projection.
    certified_streams: dict[tuple[int, int, int], frozenset[str]] = field(
        default_factory=dict)
    #: evidence key -> the footing it was read through (§5.4, choice 6).
    evidence_footings: dict[ResourceKey, FootingId] = field(
        default_factory=dict)
    #: pose -> ITS PIECES, sorted (F2a, ruling J2-3; widened from the
    #: membership-only ``posed_evidence`` at the F2a review, 2026-08-23).
    #: A pose does not index its pieces — the arrow runs the other way
    #: (§5.4) — and TWO readers need the arrow reversed: the placement
    #: scheduler asks at every door whether an extent's LIVE pose has
    #: been sampled through yet (a revision nothing has read is exactly a
    #: pose in :attr:`live_poses` and not a key here), and the re-read
    #: itself needs that pose's cells. Membership answered by walking the
    #: evidence index would be O(pieces) per window per refresh; the
    #: re-read's grouping was O(all pieces) per fire (~25,010 keys x 239
    #: fires on e029). Both are answered here, where the pieces are
    #: already being parsed. Monotone (a piece is never retired), and the
    #: dict is ~one entry per placed window rather than one per piece, so
    #: the copy-on-write is a small dict copy plus one sorted insert —
    #: the shape :attr:`evidence_by_tile` already pays.
    evidence_by_pose: dict[ResourceKey, tuple[ResourceKey, ...]] = field(
        default_factory=dict)
    #: The two work-key partitions the scheduler and the close read, SORTED
    #: (choice 7). A tile write moves at most one key between them, and
    #: both used to be re-filtered and re-sorted out of the whole tile map
    #: at every read — 5.9 s profiled on the gen-clean serial run, and a
    #: cost that grows with the sheet rather than with what moved.
    open_tiles: tuple[ResourceKey, ...] = ()
    certified_tiles: tuple[ResourceKey, ...] = ()
    #: pool key -> the ADOPTED region ctx fits over it, sorted (H5 P1).
    #: Records are frozen, so members only ever arrive; the payload fire
    #: reads this to find the fit it applies at assembly, and its ORDER is
    #: consumed (the keys enter the attempt's read-set), so the delta
    #: inserts in sorted position like the other grouped views.
    context_fits: dict[ResourceKey, tuple[ResourceKey, ...]] = field(
        default_factory=dict)
    #: pool key -> the LATEST-COMMITTED adopted fit over it (F2a review
    #: fix, 2026-08-23). :attr:`context_fits` is sorted, so it cannot
    #: answer "which fit is the current one" — and after a re-read a pool
    #: carries two adopted fits over the SAME search population (the live
    #: generation replaces a window's pieces one for one), which left the
    #: decode's choice between the pre- and post-re-read fit to a content
    #: address. C4 §3.3(5): *"v1's answer is unambiguous — the CURRENT
    #: fit is the one just fitted"*. Derived exactly as :attr:`live_poses`
    #: is, from COMMIT ORDER, and for the same reason: it is the one
    #: thing a sorted walk cannot recover.
    live_context_fits: dict[ResourceKey, ResourceKey] = field(
        default_factory=dict)

    @classmethod
    def build(cls, store) -> "StoreIndex":
        """One deterministic pass over the store, in FIRST-WRITE order.

        THE ORACLE and the resume seed (choice 5) — no longer the commit
        path. Everything :meth:`updated` maintains is derived here from
        the records alone, so the two answers are comparable field by
        field at any commit boundary.

        The pass walks ``store.records()`` rather than ``store.keys()``
        since choice 8: every field built here either sorts at its exit
        (the grouped views, the two partitions) or is a dict whose
        iteration order nothing INSIDE this module consumes, so the two
        orders were interchangeable — except for :attr:`live_poses`,
        which IS the store's write order and cannot be recovered from a
        sorted walk. Since W5, :attr:`windows` gained an EXTERNAL
        consumer of its order too: ``holo2/measure/done_gate_savings.py``
        reads commit-order deciles/tail cuts straight off
        ``index.windows.items()`` (exact, since a window key is written
        EXACTLY ONCE — ``records.py``'s "OUTCOME ONLY" ruling). Nothing
        in this module pins that dependency; a future re-sort of
        ``windows`` before return would silently move that driver's tail
        numbers without failing any test here.
        """
        tiles: dict[ResourceKey, TileRecord] = {}
        windows: dict[ResourceKey, WindowRecord] = {}
        poses: dict[ResourceKey, PoseRecord] = {}
        regions: dict[ResourceKey, RegionRecord] = {}
        captures: dict[str, CaptureRecord] = {}
        subjects: dict[str, SubjectSpec] = {}
        evidence: dict[ResourceKey, list[ResourceKey]] = {}
        footings: dict[ResourceKey, FootingId] = {}
        by_window: dict[ResourceKey, list[ResourceKey]] = {}
        streams: dict[tuple[int, int, int], set[str]] = {}
        fits: dict[ResourceKey, list[ResourceKey]] = {}
        live_fits: dict[ResourceKey, ResourceKey] = {}
        live: dict[ResourceKey, ResourceKey] = {}
        posed: dict[ResourceKey, list[ResourceKey]] = {}
        certified = 0
        for key, record in store.records().items():
            if key.kind == KIND_TILE:
                tiles[key] = record
                if record.certified:
                    certified += 1
                    page, ty, tx, stream = parse_tile_key(key)
                    streams.setdefault((page, ty, tx), set()).add(stream)
            elif key.kind == KIND_WINDOW:
                # The KEY is the id since the identity law: a window
                # record no longer carries a name to disagree with it.
                windows[key] = record
            elif key.kind == KIND_POSE:
                poses[key] = record
                by_window.setdefault(record.window_id, []).append(key)
                # LAST writer wins, and the walk is in write order, so
                # the last assignment is the latest committed pose.
                live[record.window_id] = key
            elif key.kind == KIND_REGION:
                regions[key] = record
            elif key.kind == KIND_CAPTURE:
                captures[record.source_sha256] = record
            elif key.kind == KIND_SUBJECT:
                subjects[record.subject_id] = record
            elif key.kind == KIND_EVIDENCE:
                footing, page, ty, tx, stream, _pose = parse_evidence_key(key)
                footings[key] = FootingId(footing)
                evidence.setdefault(
                    tile_key(page, ty, tx, stream), []).append(key)
                pose_id = pose_of_evidence(key)
                if pose_id is not None:
                    posed.setdefault(pose_id, []).append(key)
            elif key.kind == KIND_CALIBRATION:
                pool = _pool_fit_scope(record)
                if pool is not None:
                    fits.setdefault(pool, []).append(key)
                    # LAST writer wins over a write-order walk — the same
                    # derivation ``live`` makes two branches up, for the
                    # same reason (a sorted walk cannot recover it).
                    live_fits[pool] = key
        return cls(
            tiles=tiles, windows=windows, poses=poses, regions=regions,
            captures=captures, subjects=subjects,
            evidence_by_tile={target: tuple(sorted(keys))
                              for target, keys in evidence.items()},
            poses_by_window={window_id: tuple(sorted(pose_ids))
                             for window_id, pose_ids in by_window.items()},
            live_poses=live,
            certified=certified,
            certified_streams={cell: frozenset(names)
                               for cell, names in streams.items()},
            evidence_footings=footings,
            evidence_by_pose={pose: tuple(sorted(keys))
                              for pose, keys in posed.items()},
            open_tiles=tuple(sorted(key for key, record in tiles.items()
                                    if not record.certified)),
            certified_tiles=tuple(sorted(key for key, record in tiles.items()
                                         if record.certified)),
            context_fits={pool: tuple(sorted(keys))
                          for pool, keys in fits.items()},
            live_context_fits=live_fits)

    def updated(self, store,
                changed_keys: Iterable[ResourceKey]) -> "StoreIndex":
        """This index advanced by one commit's own delta (choice 5).

        Copy-on-write: a bucket is copied only if the delta touches its
        kind, so the ~2 keys an ordinary commit moves cost two small dict
        copies and a sorted insertion instead of a full pass over the
        store's sorted keys. The result is a NEW frozen index — the
        caller's is untouched and stays coherent for anyone still reading
        it — and it is EQUAL to ``build(store)`` at every commit
        boundary, which is what the equivalence harness asserts.

        A delta naming a key the store cannot answer for means the store
        retired something (it does not) or the caller invented a key:
        both are :class:`TileMapError`, never a silently stale entry.
        """
        touched = [
            key for key in changed_keys
            if key.kind in INDEXED_KINDS
            # Calibration is indexed for ONE bucket (H5): the adopted
            # pool fits. Every placement emission writes a window-scoped
            # marginal fit, so the qualification test runs HERE — a delta
            # of non-qualifying calibration keys is the same index, object
            # for object, exactly as an unindexed kind's delta is.
            and (key.kind != KIND_CALIBRATION
                 or _pool_fit_scope(store.get(key)) is not None)]
        if not touched:
            return self
        tiles = self.tiles
        windows = self.windows
        poses = self.poses
        regions = self.regions
        captures = self.captures
        subjects = self.subjects
        evidence_by_tile = self.evidence_by_tile
        poses_by_window = self.poses_by_window
        live_poses = self.live_poses
        certified_streams = self.certified_streams
        evidence_footings = self.evidence_footings
        evidence_by_pose = self.evidence_by_pose
        certified = self.certified
        open_tiles = self.open_tiles
        certified_tiles = self.certified_tiles
        context_fits = self.context_fits
        live_context_fits = self.live_context_fits
        for key in touched:
            kind = key.kind
            if kind == KIND_EVIDENCE:
                # A piece is indexed by its KEY alone (§5.4 puts the
                # footing, the work key and the pose in it), so a
                # re-written piece moves nothing at all.
                if key in evidence_footings:
                    continue
                footing, page, ty, tx, stream, _pose = parse_evidence_key(key)
                if evidence_footings is self.evidence_footings:
                    evidence_footings = dict(evidence_footings)
                evidence_footings[key] = FootingId(footing)
                pose_id = pose_of_evidence(key)
                if pose_id is not None:
                    if evidence_by_pose is self.evidence_by_pose:
                        evidence_by_pose = dict(evidence_by_pose)
                    evidence_by_pose[pose_id] = _with_key(
                        evidence_by_pose.get(pose_id, ()), key)
                target = tile_key(page, ty, tx, stream)
                if evidence_by_tile is self.evidence_by_tile:
                    evidence_by_tile = dict(evidence_by_tile)
                evidence_by_tile[target] = _with_key(
                    evidence_by_tile.get(target, ()), key)
                continue
            record = store.get(key)
            if record is None:
                raise TileMapError(
                    f"{key} is in a commit's changed keys and not in the "
                    "store: the index cannot be maintained across a "
                    "retirement")
            if kind == KIND_CALIBRATION:
                # Frozen records: a member arrives once and never moves.
                # Every placement's per-window fit and every refusal falls
                # through the scope test, so the ordinary delta pays one
                # isinstance and nothing else.
                pool = _pool_fit_scope(record)
                if pool is not None:
                    held = context_fits.get(pool, ())
                    if context_fits is self.context_fits:
                        context_fits = dict(context_fits)
                    context_fits[pool] = _with_key(held, key)
                    if key not in held:
                        # Choice 8: the delta arrives in COMMIT order, so
                        # the newest adopted fit of the pool is the last
                        # FIRST-write through here — the same argument
                        # (and the same "only a first write moves it"
                        # guard) ``live_poses`` makes below, which is
                        # what keeps this equal to ``build``'s
                        # first-write walk.
                        if live_context_fits is self.live_context_fits:
                            live_context_fits = dict(live_context_fits)
                        live_context_fits[pool] = key
                continue
            if kind == KIND_TILE:
                if tiles is self.tiles:
                    tiles = dict(tiles)
                previous = tiles.get(key)
                tiles[key] = record
                was = previous is not None and previous.certified
                if previous is None:
                    # A new work key ENTERS the partition its record names.
                    if record.certified:
                        certified_tiles = _with_key(certified_tiles, key)
                    else:
                        open_tiles = _with_key(open_tiles, key)
                elif record.certified != was:
                    # A certificate landed: the key CROSSES the partition
                    # (the other direction is unreachable — L5 freezes a
                    # certificate — and is maintained anyway, so the
                    # oracle is comparing an invariant, not trusting one).
                    enter, leave = ((_with_key, _without_key)
                                    if record.certified
                                    else (_without_key, _with_key))
                    certified_tiles = enter(certified_tiles, key)
                    open_tiles = leave(open_tiles, key)
                if record.certified != was:
                    page, ty, tx, stream = parse_tile_key(key)
                    if certified_streams is self.certified_streams:
                        certified_streams = dict(certified_streams)
                    certified_streams = _stream_mark(
                        certified_streams, (page, ty, tx), stream,
                        record.certified)
                    certified += 1 if record.certified else -1
            elif kind == KIND_WINDOW:
                if windows is self.windows:
                    windows = dict(windows)
                windows[key] = record
            elif kind == KIND_POSE:
                if poses is self.poses:
                    poses = dict(poses)
                previous = poses.get(key)
                poses[key] = record
                if previous is None:
                    if poses_by_window is self.poses_by_window:
                        poses_by_window = dict(poses_by_window)
                    poses_by_window[record.window_id] = _with_key(
                        poses_by_window.get(record.window_id, ()), key)
                    # Choice 8: the delta arrives in COMMIT order, so the
                    # newest pose of the extent is simply the last one to
                    # come through here. Only a FIRST write moves it — a
                    # re-write (the quarantine marking) leaves the extent's
                    # live pose exactly where it was, which is also what
                    # ``build``'s first-write walk says.
                    if live_poses is self.live_poses:
                        live_poses = dict(live_poses)
                    live_poses[record.window_id] = key
                elif previous.window_id != record.window_id:
                    raise TileMapError(
                        f"{key} was re-written onto window "
                        f"{record.window_id}: a pose's window is in its key")
            elif kind == KIND_REGION:
                if regions is self.regions:
                    regions = dict(regions)
                regions[key] = record
            elif kind == KIND_CAPTURE:
                if captures is self.captures:
                    captures = dict(captures)
                captures[record.source_sha256] = record
            elif kind == KIND_SUBJECT:
                if subjects is self.subjects:
                    subjects = dict(subjects)
                subjects[record.subject_id] = record
        return replace(
            self, tiles=tiles, windows=windows, poses=poses, regions=regions,
            captures=captures, subjects=subjects,
            evidence_by_tile=evidence_by_tile,
            poses_by_window=poses_by_window, live_poses=live_poses,
            certified=certified,
            certified_streams=certified_streams,
            evidence_footings=evidence_footings,
            evidence_by_pose=evidence_by_pose,
            open_tiles=open_tiles, certified_tiles=certified_tiles,
            context_fits=context_fits,
            live_context_fits=live_context_fits)

    def page_of_pose(self, pose_id: ResourceKey) -> int | None:
        """The one page a pose addresses (choice 1); None if unknown."""
        pose = self.poses.get(pose_id)
        return None if pose is None else pose.page

    def live_pose(self, window_id: ResourceKey) -> ResourceKey | None:
        """THE pose of one window right now: the latest committed (choice 8).

        The user's ruling of 2026-08-23 in one lookup — "the latest
        committed pose for that extent wins" — and it is the ONLY spelling
        of it in the tree: a consumer that wants the geometry of a window
        asks here instead of picking one out of :attr:`poses_by_window`,
        which is sorted by key and says nothing about which came last.

        ``None`` where the window has never been posed. Quarantine is NOT
        filtered here: a condemned pose is still the extent's latest
        committed geometry, and the readers that must refuse one already
        ask ``quarantine.is_quarantined`` themselves (the consult, the
        payload read-set, the calibration pool). Answering "None" for a
        condemned pose would hide the marking from the one reader that is
        allowed to see it and silently promote a superseded pose.
        """
        return self.live_poses.get(window_id)

    def live_poses_of_region(self,
                             region_id: ResourceKey) -> tuple[ResourceKey, ...]:
        """One pose per posed window of a region — the §6 projection's input.

        The shared walk :func:`project_done`'s two production callers used
        to make for themselves (``plane_views._project`` and
        ``diag.panes.model``), narrowed by choice 8 from "every committed
        pose of every window here" to "the live pose of each". Sorted, so
        the projection's own ordering argument is unaffected.
        """
        return tuple(sorted(
            pose_id
            for window_id, window in self.windows.items()
            if window.region_id == region_id
            and (pose_id := self.live_poses.get(window_id)) is not None))


def _with_key(group: tuple[ResourceKey, ...],
              key: ResourceKey) -> tuple[ResourceKey, ...]:
    """One grouped view's tuple with ``key`` inserted in SORTED position.

    The grouped views are read sets whose order is consumed (choice 5),
    so a delta may not append: it inserts where the from-scratch builder's
    ``sorted()`` would have put it. Groups are a handful of keys wide, so
    the bisect is cheaper than the sort it replaces by the length of the
    group, not by a constant.
    """
    position = bisect_left(group, key)
    if position < len(group) and group[position] == key:
        return group
    return (*group[:position], key, *group[position:])


def _without_key(group: tuple[ResourceKey, ...],
                 key: ResourceKey) -> tuple[ResourceKey, ...]:
    """The same tuple with ``key`` gone — the partition's other half."""
    position = bisect_left(group, key)
    if position >= len(group) or group[position] != key:
        return group
    return (*group[:position], *group[position + 1:])


def _stream_mark(streams: dict[tuple[int, int, int], frozenset[str]],
                 cell: tuple[int, int, int], stream: str,
                 certified: bool) -> dict[tuple[int, int, int],
                                          frozenset[str]]:
    """Add or drop one stream of one cell, keeping empty cells ABSENT.

    Absent-when-empty is what makes the maintained map compare equal to
    the builder's, which only ever writes a cell it saw a certificate on.
    """
    names = streams.get(cell, frozenset())
    names = (names | {stream}) if certified else (names - {stream})
    if names:
        streams[cell] = names
    else:
        streams.pop(cell, None)
    return streams


class TileMap:
    """The logical authority as the scheduler reads it (§5.2)."""

    def __init__(self, index: StoreIndex, stream_ids: tuple[str, ...],
                 tiles_yx: tuple[int, int]) -> None:
        self._index = index
        self._stream_ids = stream_ids
        self._streams = frozenset(stream_ids)
        self._tiles_yx = tiles_yx

    def record(self, key: ResourceKey) -> TileRecord | None:
        return self._index.tiles.get(key)

    def keys(self) -> tuple[ResourceKey, ...]:
        return tuple(sorted(self._index.tiles))

    def certified_keys(self) -> tuple[ResourceKey, ...]:
        """The close's input frontier — maintained, not re-filtered."""
        return self._index.certified_tiles

    def open_keys(self) -> tuple[ResourceKey, ...]:
        """The eligibility domain: a record exists and is not certified."""
        return self._index.open_tiles

    def counts(self, attempted: Collection[ResourceKey] = ()
               ) -> dict[str, int]:
        """The operator's tally, in display ranks (:func:`tile_state`).

        ``attempted`` is the ledger's set of CRC-exposed work keys; a
        caller with no ledger at hand passes none and the record's own
        failed baselines still answer for the footings that decoded.
        """
        exposed = frozenset(attempted)
        tally = {state.name: 0 for state in TileState}
        for key, record in self._index.tiles.items():
            tally[tile_state(record, attempted=key in exposed).name] += 1
        return tally

    def tile_done(self, page: int, ty: int, tx: int) -> bool:
        """Every stream of this work key certified (choice 2).

        Read off the index's maintained per-cell certificate set rather
        than by rebuilding one tile key per stream: the answer is the
        same set containment, and the keys never have to exist as
        strings for it (choice 6).
        """
        return self._streams <= self._index.certified_streams.get(
            (page, ty, tx), frozenset())

    def done_tile_grid(self, page: int) -> np.ndarray:
        """Boolean ``tiles_yx`` grid of fully-certified tiles on one page.

        Iterates the CERTIFIED cells, not the grid: the projection is
        sparse for most of a decode, and the dense form was building
        ``tiles_y x tiles_x x streams`` resource keys per call (421,615
        ``tile_done`` calls and 3.8 s profiled on the gen-clean serial
        run) to answer a question about a few hundred of them.
        """
        tiles_y, tiles_x = self._tiles_yx
        grid = np.zeros((tiles_y, tiles_x), bool)
        wanted = self._streams
        for (cell_page, ty, tx), names in (
                self._index.certified_streams.items()):
            if (cell_page == page and wanted <= names
                    and 0 <= ty < tiles_y and 0 <= tx < tiles_x):
                grid[ty, tx] = True
        return grid


@dataclass(frozen=True)
class DoneProjection:
    """One region's done cells (§6). Derived on demand, never persisted."""

    capture_sha256: CaptureSha
    region_id: ResourceKey
    cells: np.ndarray

    @property
    def done_cells(self) -> int:
        return int(np.count_nonzero(self.cells))

    def runs(self) -> tuple[tuple[int, int, int], ...]:
        """The cell-granular run representation §6 requires."""
        return runs_of_mask(self.cells)

    def covers(self, extent_cells: tuple[int, int, int, int],
               support: np.ndarray) -> bool:
        """§6 gate: is every SUPPORTED cell of this extent already done?"""
        cy0, cx0, cy1, cx1 = extent_cells
        window_support = support[cy0:cy1, cx0:cx1]
        if not window_support.any():
            return False        # an unsupported window is not "done", it is dead
        return bool(np.all(self.cells[cy0:cy1, cx0:cx1][window_support]))


def project_done(index: StoreIndex, tiles: TileMap, *,
                 capture_sha256: CaptureSha, region_id: ResourceKey,
                 lattice: CellLattice, support: np.ndarray,
                 pose_ids: tuple[ResourceKey, ...]) -> DoneProjection:
    """Project certificates back onto one region's capture cells (§6).

    ``pose_ids`` are ONE pose per posed window of this region — the LIVE
    one (choice 8), which production callers get from
    :meth:`StoreIndex.live_poses_of_region`. Ownership-freeze winners and
    losers are still both here, as §6 requires: they are different
    WINDOWS, each with its own live pose, and any committed observation
    of a certified key spends its pixels.

    WHY LATEST AND NOT THE UNION (W3, the user's ruling of 2026-08-23,
    RULING I3). Before RF1 was turned on an extent had exactly one pose
    and the two readings were the same set. With revisions they are not,
    and the union is the wrong one: measured on the two real sheets (W2,
    ``rf1-e029.md`` / ``rf1-xerox.md``), unioning parent and revision
    added **+860 done cells on e029 and +588 on Xerox** — geometry a
    revision bought without sampling a single pixel, since a revised pose
    carries no evidence at all. Done pixels are a claim about what has
    been SPENT, so a second pose of one extent REPLACES the first rather
    than adding to it, and the union's unbounded over-claim is gone.

    WHAT THAT DOES NOT SAY, stated because the first wording of this
    docstring claimed more than the code delivers (W3 review,
    2026-08-23). The projection maps the window's WHOLE extent through
    whichever pose it is handed, and consults no evidence: with a
    revision live, the cells are projected through geometry that sampled
    nothing. Since a revision's affine differs from its parent's by up to
    the search box (``PHASE_LIMIT_CELLS`` / ``ANGLE_LIMIT_DEG``), a cell
    near a tile boundary can map into a done tile under the revision that
    it missed under the parent, and vice versa — so ``done(revision)`` is
    neither a subset nor a superset of ``done(parent)``. What is bounded
    is the MAGNITUDE: a boundary sliver of the extent, on the order of
    W2's measured ~3 cells per revision, against the union's +860/+588.
    It is UNMEASURED at this pitch, and it bites in both directions —
    ``place_sched`` retires a window ``done_covered`` permanently, so
    coverage that later recedes is not re-offered. W5's done-gate census
    must carry this caveat rather than read the projection as exact.
    """
    done = np.zeros(lattice.shape_cells, bool)
    grids: dict[int, np.ndarray] = {}
    for pose_id in sorted(pose_ids):
        pose = index.poses.get(pose_id)
        if pose is None:
            continue
        page = index.page_of_pose(pose_id)
        if page is None:
            continue            # unknown page: contributes no done pixels
        window = index.windows.get(pose.window_id)
        if window is None or window.region_id != region_id:
            continue
        grid = grids.get(page)
        if grid is None:
            grid = tiles.done_tile_grid(page)
            grids[page] = grid
        if not grid.any():
            continue
        cy0, cx0, cy1, cx1 = window.extent_cells
        centres_y = lattice.centres_y(cy0, cy1)[:, None]
        centres_x = lattice.centres_x(cx0, cx1)[None, :]
        cell_y, cell_x = apply_affine(
            invert_affine(pose.native_affine),
            np.broadcast_to(centres_y, (cy1 - cy0, cx1 - cx0)),
            np.broadcast_to(centres_x, (cy1 - cy0, cx1 - cx0)))
        ty, tx = tile_of_cell(np.floor(cell_y).astype(np.int64),
                              np.floor(cell_x).astype(np.int64))
        inside = ((ty >= 0) & (ty < grid.shape[0])
                  & (tx >= 0) & (tx < grid.shape[1]))
        marked = np.zeros(inside.shape, bool)
        marked[inside] = grid[ty[inside], tx[inside]]
        done[cy0:cy1, cx0:cx1] |= marked & support[cy0:cy1, cx0:cx1]
    return DoneProjection(capture_sha256, region_id, done)


__all__ = [
    "DoneProjection", "StoreIndex", "TileMap", "TileMapError", "TileState",
    "project_done", "tile_state",
]

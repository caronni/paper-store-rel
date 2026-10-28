"""``PlaneView`` — core's fact plane plus the physical plane solve reads.

``core.SolveView`` is deliberately format-blind and pixel-blind: it
grants records, bulk values and frontier queries, and nothing that would
make core know what a printed sheet is. A solve worker needs more — the
format row it is decoding, the surveyed region it sits in, the footing
lane it reads through, the window lattice, and the authenticated raster —
so the extension lives here, in the package that legitimately knows all
four.

R2 made the protocol concrete where it can be: the three structural
stand-ins R1 needed (``FormatRow``, ``RegionSlice``, ``FootingSlice``)
are gone, because their real types now live in packages ``solve``
imports. What remains structural is the view itself: a worker is handed
``holo2.solve.SessionPlane``, but it is typed against this protocol, so a
future plane (a replay harness, a bounded-crop view, a test double) needs
no inheritance to qualify.

Choices where DESIGN is silent (for adjudication):

- **``raster`` hands back the authenticated raster, not a crop.** The
  intended narrowing is bounded crops (``Raster`` already refuses
  unbounded reads and returns copies), but the word-grid sampler decides
  its own crops per hypothesis, and re-cutting that decision is an
  algorithm change R1 explicitly did not make. The view therefore gates
  *availability* — a detached capture answers ``None``, and the worker
  declines on the attachment key (M12) — and leaves the crop policy to
  the sampler until H4 revisits it.

  **H4 W1a is that revisit, and it went the other way**: the answer was
  not a smaller crop per fire but ONE prepared plane per region, built
  once and memory-mapped (:meth:`PlaneView.prepared_region`,
  ``solve/prepared.py``). A fire reads the region's pixels through
  coordinates, so there is no crop policy left to decide — and no
  per-fire materialization to multiply by the pool width, which is the
  measured failure that forced the question (workers 4/8 SIGKILLed).
  ``raster`` stays exactly what it was: the raw authenticated pixels, for
  the paths that legitimately want them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from ..capture import FootingFrame, FootingSpec, Raster
from ..core import CaptureSha, FootingId, ResourceKey, SolveView
from ..format import FormatRowSpec
from .place_model import PlacementConfig
from .plans import RegionView, WindowPlan
from .pose_fit import PreparedRegion
from .records import TileRecord
from .tilemap import StoreIndex


@runtime_checkable
class PlaneView(SolveView, Protocol):
    """What a solve provider or worker may see."""

    @property
    def format_row(self) -> FormatRowSpec: ...

    def index(self) -> StoreIndex:
        """One generation's per-kind indexes, as ONE object.

        Declared because an enumeration over the whole open frontier
        cannot afford to re-enter the view once per key per lookup: the
        payload provider hoists the two maps it reads (F-17), which is a
        pair of dict lookups per key instead of a pair of protocol hops
        through the generation pin. What comes back is READ-ONLY and
        frozen for its generation — a commit publishes a NEW index, it
        never edits this one.
        """

    def tile(self, key: ResourceKey) -> TileRecord | None:
        """The tile-map record at one work key.

        R3 moved this off ``core.SolveView``: a ``TileRecord`` is solve's
        record, so the typed read of one is solve's query.
        """

    def raster(self, capture_sha256: CaptureSha) -> Raster | None:
        """The authenticated raster, or None when it is not attached."""

    def scan_capture(self, path: Path, dpi: float) -> CaptureSha | None:
        """The acquisition a DECLARED scan was ingested as, or None (H4
        streaming ingestion).

        Streaming ingestion's one frontier query. A scan is a
        DECLARATION — a path and an operator DPI — and a capture record
        is named by the SHA-256 of bytes, so only something that has
        opened the file can join the two. The plane has (attach-by-reopen
        is its act), so the ingest provider asks it rather than guessing
        by order or by count.
        """

    def region(self, region_id: ResourceKey) -> RegionView: ...

    def derived_directory(self) -> Path:
        """Where this lineage's DERIVED pixels live (H4-LANES stage 1).

        The ``<state-dir>.prepared`` sibling: prepared planes, and beside
        them the ladder's sub-native footing rasters. It is a plane read
        because a state directory is the plane's to know —
        ``core.SolveView`` withholds the store on purpose — and the
        caller is the ingest provider, which binds a fire that writes
        rungs into it.
        """

    def prepared_region(self, region: RegionView, *,
                        config: PlacementConfig,
                        footing_id: FootingId | None = None,
                        ) -> PreparedRegion | None:
        """One region's prepared plane: filled, filtered, mapped once.

        The pixel surface a placement worker actually reads (W1a). It is
        on the VIEW rather than in the worker because its lifetime is the
        session's and its readers are every fire: building it per fire is
        precisely the failure this replaced.

        ``footing_id`` names the RUNG (H4-LANES stage 1): one region has
        one prepared plane per footing, at that footing's own pitch, from
        that footing's own pixels. ``None`` means the capture's native
        rung, which is what a caller that does not schedule by lane means.

        ``None`` carries ``pose_fit.prepare_region``'s two geometric
        refusals — a bbox off the raster, a region with no support — plus
        "this session has no pixels for it": neither an attached raster
        nor a complete prepared plane in ``<state-dir>.prepared``. Since
        2026-08-17 an absent raster is NOT by itself a refusal, because
        everything a prepared plane's name is a function of became
        durable (``capture.CaptureRecord.platen_backing``).
        """

    def footing(self, footing_id: FootingId) -> FootingSpec: ...

    def footing_frame(self, footing_id: FootingId) -> FootingFrame | None:
        """One rung's PIXEL FRAME, or None for a footing this plane lacks.

        Declared on the view since H4-LANES stage 2, because a placement
        fire needs it: the pose kernel works in the rung's pixels and the
        record it commits is native-frame, so the exact rational scale
        between the two has to reach ``place_shared`` (ruling 2). It is a
        durable derivation — the footing's ppc against its capture's
        finest, plus the capture's recorded shape — so a catalogued
        capture answers it exactly as an attached one does.
        """

    def footing_depth(self, footing_id: FootingId) -> int:
        """The rung's index from the COARSEST of its capture's ladder.

        0-based, so the coarsest lane is 0 and the native lane is the
        last. It is the LANE TERM's input: placement prices every tier at
        ``tier + 2*depth`` and the payload family prices a scan or a
        retry the same way, so both sides ask this one question of the
        one object that holds the ladder (``place_sched``,
        ``payload``). A footing the plane does not hold answers 0 —
        the cheapest lane — because a price is not a place to refuse.
        """

    def has_footing(self, footing_id: FootingId) -> bool:
        """Whether the PLANE holds the footing (F-05/D5c).

        Durable evidence can name footings of captures this run was not
        handed the files for; the payload frontier asks before
        dereferencing, so a partial resume solves what it can instead of
        dying on a ``KeyError`` at expansion.

        Since B9 the answer is "yes" for every capture the STORE knows,
        attached or not (``capture.catalog``): a footing is a durable
        fact, so only a state whose capture record is missing altogether
        can answer no. What an absent raster gates is pixel work, and
        that question is :meth:`raster` returning ``None``.
        """

    def has_region(self, region_id: ResourceKey) -> bool:
        """Whether the plane holds this region's surveyed geometry (B9).

        The composing partner of :meth:`has_footing`, for the other half
        of what durable evidence cites. A provider asks both before
        minting a worker that will dereference them, which is how the
        bare ``KeyError``s that used to cross the worker boundary became
        declines that sleep on ``attachment_key``.
        """

    def has_footing_pixels(self, footing_id: FootingId) -> bool:
        """Can this session dereference this RUNG's pixels? (H4-LANES.)

        :meth:`raster` asked per lane, and the cheap half of the M12
        attachment gate. The native rung is the attached scan; a
        sub-native rung is its derived file, or an attached scan the file
        can be derived from. Costs at most one ``stat``, because the gate
        asks it per window at every refresh.
        """

    def footing_ids(self, selector: str) -> tuple[FootingId, ...]:
        """The footings one recipe selector runs on (§9)."""

    def window_plans(self, footing_id: FootingId) -> tuple[WindowPlan, ...]:
        """The window lattice of one footing (§8.2)."""

    def window_is_done(self, plan: WindowPlan) -> bool:
        """§6 gate: is every supported cell of this extent already spent?"""


@runtime_checkable
class _CarriesDerivedViews(Protocol):
    """A plane that memoises views derived from the durable store.

    Optional on purpose, and asked STRUCTURALLY: :func:`as_plane` is
    handed core's ``SolveView``, which knows nothing about derived views,
    and the narrowing is a statement about wiring rather than a runtime
    branch. A view with no generations to pin — a bounded-crop view, a
    test double built to answer two reads — needs nothing here and is
    unaffected; the one implementation that has them is
    ``solve.plane.SessionPlane``.
    """

    def pin_views(self) -> None:
        """Pin one generation of them for the whole of this fire."""


def pin_views(view: SolveView) -> None:
    """Pin the generation this fire reads, if the view has generations.

    The pin belongs at the seam where a worker's view is BORN, so that
    the engine needs no knowledge of it and the serial, pool and replay
    paths get it identically — they already read through this one
    narrowing. :func:`as_plane` therefore takes it, and a worker whose
    signature is already ``PlaneView`` calls this directly at the top of
    its fire.

    What it buys is the H4 W-S rule: a fire never observes two
    generations of derived state, however many commits land while it
    runs (``SessionPlane.pin_views``).
    """
    if isinstance(view, _CarriesDerivedViews):
        view.pin_views()


def as_plane(view: SolveView) -> PlaneView:
    """Narrow the engine's fact view to the plane solve was composed with.

    The interfaces the engine offers work through are core's, so they type
    their view as ``core.SolveView`` — the widest thing a package that
    knows no printed format can promise. A solve provider (and the volume
    close) needs the physical half, and gets it because the composition
    root builds BOTH halves from one object: ``SessionPlane`` is a
    ``PlaneView``, and it is the only view any of them is ever handed.

    So this is a statement about wiring, not a runtime branch: free at
    call time, and it is what makes the declarations on both sides TRUE
    rather than approximately true (worklist B12 — a provider that
    narrowed this parameter in its own signature did not satisfy
    ``core.Provider`` at all, and ``runtime_checkable`` could never say
    so, because ``isinstance`` reads names and never signatures).

    Since H4 it is also where the fire's generation is PINNED
    (:func:`pin_views`): this call happens once, at the top of a worker's
    ``run`` and its ``read_keys``, which is precisely "one fire, one
    generation".
    """
    pin_views(view)
    return cast(PlaneView, view)


__all__ = ["PlaneView", "as_plane", "pin_views"]

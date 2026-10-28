"""The plane's PIXEL side: rungs, frames, and one region's prepared planes.

H4-LANES stage 2's opener, and a RELOCATION and nothing else. Stage 1 gave
``solve/plane.py`` a footing axis — a frame per rung, a pixel gate per
rung, a prepared plane per (region, rung) — and left the file at 972 lines
against the 1000-line cap, which is a seam signal and never a budget to
squeeze. The seam the cap named is the one stage 1's own commit message
named: everything that answers "where are the pixels of this rung, and
what do they look like once they are filled and filtered" is a different
question from everything the plane's other half answers (which captures
this session holds, which facts stand, which extents are done).

So the pixel half lives here, as a MIXIN rather than as a helper object,
for one reason: the maps it reads (``_captures``, ``_footings``) are
REPLACED by the committing thread as captures attach, so anything holding
a snapshot of them would go quietly stale. Inheriting keeps every body
exactly the one ``SessionPlane`` had, reading ``self`` exactly as before —
the relocation changes no expression, no name and no order.

It sits beside ``plane_views.py``, which took the same cut for the same
reason: ``_DerivedViews`` is the STORE-derived half, this is the
PIXEL-derived half, and ``plane.py`` is the object that owns both and
hands them out as ``core.SolveView``.
"""
from __future__ import annotations

import threading
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING

from ..capture import (FootingFrame, FootingPlan, FootingSpec, footing_plan,
                       footing_raster_for, footing_transform)
from ..core import CaptureSha, FootingId, ResourceKey, Store
from .place_model import PlacementConfig
from .plans import RegionView
from .pose_fit import PreparedRegion
from .prepared import (PixelSource, open_prepared_region, prepared_directory,
                       prepared_region)

if TYPE_CHECKING:                                  # pragma: no cover
    from .plane import CaptureView


#: What names one prepared plane in this session's memos: the region, the
#: RUNG it was prepared at (H4-LANES stage 1) and the aperture in that
#: rung's pixels. The footing joined on the day the reading set stopped
#: being one lane by construction; the aperture was always there, because
#: it is the one thing about placement policy the bytes depend on.
_PreparedKey = tuple[ResourceKey, FootingId | None, int]


class PlanePixels:
    """The pixel half of ``SessionPlane`` (module docstring: why a mixin).

    Every attribute below is the concrete plane's, declared here so the
    reads are visible at the seam rather than discovered by a traceback.
    Nothing in this class constructs any of them.
    """

    _store: Store
    _captures: tuple["CaptureView", ...]
    _footings: dict[FootingId, FootingSpec]
    _memo_lock: threading.Lock
    _prepared: dict[_PreparedKey, PreparedRegion]
    _unprepared: dict[_PreparedKey, CaptureSha]
    _footing_rasters: dict[FootingId, PixelSource]

    def _capture(self, capture_sha256: CaptureSha) -> "CaptureView | None":
        """The plane's view of one acquisition — ``plane.py`` implements it."""
        raise NotImplementedError

    # -- the footing ladder's pixels (H4-LANES stage 1) ---------------------

    def derived_directory(self) -> Path:
        """``<state-dir>.prepared``: where this lineage's DERIVED pixels live.

        One question, asked by everything that writes or reads them — the
        prepared planes below, the footing rasters beside them, and the
        ingest fire that emits the rungs (``solve.ingest`` binds the
        worker with this). It is on the plane because the plane is the
        object that holds a state directory and hands out pixels; a
        provider that computed it from a store would be reaching past
        ``core.SolveView``, which withholds the store on purpose.
        """
        return prepared_directory(self._store.state_dir)

    def footing_frame(self, footing_id: FootingId) -> FootingFrame | None:
        """The pixel frame of one rung, or ``None`` for an unknown footing.

        A frame is a durable derivation: the footing's own ppc against
        the ladder's finest (which IS native — ``auto_ppc_levels`` ends at
        native sampling and never upsamples), plus the capture's recorded
        shape. So a catalogued capture answers this exactly as an
        attached one does, which is what lets the reuse-only door
        pronounce a coarse plane's name with no pixels at all.

        SINCE STAGE 2 IT IS ALSO THE POSE KERNEL'S PARAMETER (ruling 2):
        a pose is fitted on the rung's own pixels at the rung's pitch and
        COMMITTED in the native frame, and this value carries the exact
        rational scale that composition is made of.
        """
        footing = self._footings.get(footing_id)
        if footing is None:
            return None
        capture = self._capture(footing.capture_sha256)
        return None if capture is None else self._frame(capture, footing.ppc)

    def has_footing_pixels(self, footing_id: FootingId) -> bool:
        """Can this session dereference THIS rung's pixels? (M12, per lane.)

        The cheap half of the attachment gate, asked per window at every
        refresh, so it costs at most one ``stat``. The native rung is the
        attached scan, and the answer for it is exactly what
        :meth:`~holo2.solve.plane.SessionPlane.raster` has always said. A
        sub-native rung is a file, and an attached raster is as good as one
        because the rung is derivable from it — which is the same "two
        sources" shape the prepared planes already have.

        A ``False`` here is never a verdict: it is retired by an attach,
        which is the wake ``attachment_key`` already promises.
        """
        footing = self._footings.get(footing_id)
        if footing is None:
            return False
        capture = self._capture(footing.capture_sha256)
        if capture is None:
            return False
        if capture.raster is not None:
            return True
        frame = self._frame(capture, footing.ppc)
        if frame.is_native:
            return False
        return self._footing_plan(capture, footing.ppc).stands()

    def _frame(self, capture: "CaptureView", ppc: Fraction) -> FootingFrame:
        """One capture's rung, as a frame. Native is a member, not a case."""
        native = (capture.footings[-1].ppc if capture.footings else ppc)
        shape = capture.record.shape_px
        return (FootingFrame.native(shape) if ppc >= native
                else FootingFrame.of(ppc, native, shape))

    def _footing_plan(self, capture: "CaptureView",
                      ppc: Fraction) -> FootingPlan:
        """Where a SUB-NATIVE rung of this capture sits, by name only."""
        native = capture.footings[-1].ppc
        return footing_plan(
            capture.source_sha256, footing_transform(ppc, native),
            capture.record.shape_px, capture.record.dtype,
            directory=self.derived_directory())

    def _footing_source(self, capture: "CaptureView",
                        footing_id: FootingId) -> PixelSource | None:
        """The pixels one rung is read through. Memo lock held.

        Native is the authenticated scan itself — no copy, no file, and
        ``None`` when it is not attached. A sub-native rung is opened if
        it stands and DERIVED from the raster if it does not, through the
        one door that owns both halves (``capture.footing_raster_for``),
        so a session whose ``.prepared`` sibling was deleted rebuilds
        what it needs instead of going quietly blind on the coarse lanes.
        """
        footing = self._footings.get(footing_id)
        if footing is None:
            return None
        if self._frame(capture, footing.ppc).is_native:
            return capture.raster
        cached = self._footing_rasters.get(footing_id)
        if cached is not None:
            return cached
        rung = footing_raster_for(
            capture.raster, footing.ppc, capture.footings[-1].ppc,
            capture_sha256=capture.source_sha256,
            shape_px=capture.record.shape_px, dtype=capture.record.dtype,
            directory=self.derived_directory())
        if rung is not None:
            self._footing_rasters[footing_id] = rung
        return rung

    def prepared_region(self, region: RegionView, *,
                        config: PlacementConfig,
                        footing_id: FootingId | None = None,
                        ) -> PreparedRegion | None:
        """One region's filled, filtered, memory-mapped pixels (W1a).

        v1 prepared a region once and looped its windows inside it; holo2
        fires one worker per (window, stage), so the preparation lives
        HERE — session-lifetime, generation-independent, shared by every
        worker — and the pixels themselves live in files under
        ``<state-dir>.prepared``. What a fire gets back is a read-only
        ``np.memmap`` view of exactly the arrays
        ``pose_fit.prepare_region`` would have built (``solve/prepared.py``
        states why that is byte-identical and not merely equivalent), so
        it copies nothing, fills nothing and filters nothing.

        Immutability is the whole coherence story: nothing mutates a
        prepared plane, so no generation, no barrier and no lock stands
        between a reader and it once it exists. ``config`` is the
        PLACEMENT policy — the aperture is a placement decision, not a
        plane one — and it rides into the file's name with everything
        else the bytes depend on.

        TWO SOURCES, ONE NAME (2026-08-17). Everything the name is a
        function of is durable now that the backing rides the capture
        record, so a capture whose pixels are NOT attached still yields
        readable planes when this state's ``<state-dir>.prepared`` sibling
        survived — the crash-cut resume's case, where the derived pixels
        are on disk and only the scans are gone. That door is
        reuse-only (:func:`~holo2.solve.prepared.open_prepared_region`): a
        session with no raster can open what exists and can never build
        what does not.

        ``None`` where ``prepare_region`` refuses — a bbox off the raster
        or a region with no support at all — and, on the reuse-only door,
        where the planes are simply not there.

        ONE REGION, ONE PLANE PER RUNG (H4-LANES stage 1). ``footing_id``
        names the lane the caller will read through; omitting it means
        the capture's NATIVE rung, which is what every caller meant
        before there were lanes and what a caller that does not schedule
        by footing means now. The memo, the refusal memo and the file
        names are all keyed by it, so two rungs of one region are two
        plans that never see each other's bytes.
        """
        if not region.schedulable or region.lattice is None:
            return None
        capture = self._capture(region.capture_sha256)
        if capture is None:
            return None
        lane = footing_id if footing_id is not None else self._native_id(
            capture)
        if lane is not None and lane not in self._footings:
            return None                  # a rung this plane does not hold
        frame = (FootingFrame.native(capture.record.shape_px) if lane is None
                 else self._frame(capture, self._footings[lane].ppc))
        # The aperture in PIXELS is the only thing about placement policy
        # the bytes depend on, so it is the only thing beside the region
        # and its rung that keys them (``prepared`` hashes the same
        # number into the file's name). It is per-rung because a pixel is.
        pitch = frame.pitch_px(float(region.lattice.pitch_px))
        key: _PreparedKey = (region.region_id, lane,
                             max(1, int(round(config.aperture_cells * pitch))))
        cached = self._prepared.get(key)
        if cached is not None:
            return cached
        if key in self._unprepared:
            return None
        with self._memo_lock:
            built = self._prepared.get(key)
            if built is None:
                built = self._prepare(region, capture, lane, frame,
                                      config=config)
                if built is None:
                    if capture.raster is None:
                        self._unprepared = {**self._unprepared,
                                            key: capture.source_sha256}
                    return None
                self._prepared[key] = built
            return built

    def _native_id(self, capture: "CaptureView") -> FootingId | None:
        """The capture's finest footing — its native rung — or None."""
        return (capture.footings[-1].footing_id if capture.footings else None)

    def _prepare(self, region: RegionView, capture: "CaptureView",
                 lane: FootingId | None, frame: FootingFrame, *,
                 config: PlacementConfig) -> PreparedRegion | None:
        """Build from the rung's pixels, or open what an earlier run built."""
        assert region.lattice is not None
        naming = dict(
            config=config, backing=capture.record.platen_backing,
            capture_sha256=region.capture_sha256, frame=frame,
            directory=self.derived_directory())
        pitch = frame.pitch_px(float(region.lattice.pitch_px))
        source = (capture.raster if lane is None
                  else self._footing_source(capture, lane))
        if source is None:
            return open_prepared_region(
                capture.record.shape_px, region.candidate.support, 0,
                pitch, **naming)
        return prepared_region(
            source, region.candidate.support, 0, pitch, **naming)


__all__ = ["PlanePixels"]

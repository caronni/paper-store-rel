"""Pane A (ACQUIRED): the capture/lane geometry model.

Pane A is the one pane that lives in SCAN space.  B, C and D are
page/tile-indexed and therefore frame-free, which is why this is the
natural seam in the live view: everything here is about turning a lane's
pixel geometry into pane pixels, and nothing here knows about pages,
tiles, certificates or the fountain.

Two rules govern the whole module, both of them scars:

- **One frame, capture-native** (RECEIVE-DESIGN v0.47).  A mop-up or
  refinement level reuses its base lane's raster, so it emits THAT lane's
  pixel coordinates, while the underlay belongs to whichever ladder rung
  surveyed last.  Every box is therefore normalized to capture-native
  pixels at ingest — using the exact ratio the receiver publishes on
  ``level.open``/``lane.open`` — and ONE transform projects them.  The
  frame is a property of the geometry, not of whatever surveyed most
  recently.
- **Region ordinals are lane-relative** (v0.48).  ``address.region`` is a
  positional index into the EMITTING lane's survey tuple; an M/R level
  indexes its BASE lane.  A state write is applied only when the region
  lane owns the views currently on screen.

:class:`ScanFrame` is the per-capture display model — the ONE enumeration
of what ``capture.open`` resets, ``capture.resume`` swaps, and the durable
resume seed supplies.  Before it existed the same twelve field names were
spelled out in five places and nothing pinned them to agree.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

import numpy as np

from .presentation import PaneRenderer, RegionView


@dataclass(slots=True)
class ScanFrame:
    """One capture's pane-A display model.

    Stashed on ``capture.resume``, rebuilt blank on ``capture.open``, and
    minted from durable records by the v0.45 resume seed.  Keep the field
    set and :meth:`blank` in step — ``test_scan_frame_is_the_one_resume
    _contract`` pins that the seed builds exactly these names.
    """

    regions: list[RegionView] = field(default_factory=list)
    # CAPTURE-NATIVE px -> pane px.
    transform: tuple[float, float, float] | None = None
    # The lane that OWNS ``regions`` (not merely the last lane to survey):
    # a zero-region survey must never relabel views it did not install.
    lane: str | None = None
    # (y, x, h, w) native px, projected at draw, never frozen to pane.
    active_window: tuple[int, int, int, int] | None = None
    underlay: np.ndarray | None = None
    lane_regions: int = 0
    survey_seen: bool = False
    queue_total: int | None = None
    deferred: int = 0
    # (region, window_id) -> [(y, x, h, w) native px, state]
    planned: dict[tuple[int, int], list] = field(default_factory=dict)
    # Base lane while the current lane is its mop-up / refinement /
    # supplemental level, from the survey.mopup_of / survey.refine_of /
    # survey.uplift_of details.  A supplemental level has the R level's
    # foreign-region-namespace semantics exactly, so it reuses
    # ``refine_base``; ``uplift_arm`` is the one extra fact only it has —
    # the campaign arm this lane FORCES — and pane A prints it, because a
    # lane running a forced arm must never read as an ordinary one.
    mopup_base: str | None = None
    refine_base: str | None = None
    uplift_arm: str | None = None

    @classmethod
    def blank(cls) -> "ScanFrame":
        return cls()


class ScanModel:
    """Pane-A state plus the ingest and projection that maintain it."""

    def __init__(self, panes: PaneRenderer) -> None:
        self._panes = panes
        # The live EventContext, refreshed by the viewer on every
        # event: it carries the emitting lane's id and its exact
        # native_per_view ratio, which are what make a box's frame
        # and a region index interpretable.
        self.context: object | None = None
        # v0.33 parked-for-mop-up chips (§10.3.3/§10.5 as amended):
        # durable pane-A rows that survive their lane's barrier, keyed by
        # the ParkedWindowRecord identity so barrier snapshots retire
        # them.  Value = (native-px box yxhw, plan-level digit).
        self.parked_chips: dict[
            tuple[str, str, int, int],
            tuple[tuple[int, int, int, int], str | None]] = {}
        # capture sha -> retained frame, swapped on capture.resume (§10.5:
        # pane A follows the current raster WITHOUT capture.open's
        # wholesale clearing).
        self.stash: dict[str, ScanFrame] = {}
        # v0.45 durable-record resume seed, consumed on install.
        self.seed: dict[str, ScanFrame] = {}
        self.dirty = True
        self.apply(ScanFrame.blank())

    # -- the resume contract -------------------------------------------
    def capture_frame(self) -> ScanFrame:
        return ScanFrame(**{f.name: getattr(self, f.name)
                            for f in fields(ScanFrame)})

    def apply(self, frame: ScanFrame) -> None:
        for f in fields(ScanFrame):
            setattr(self, f.name, getattr(frame, f.name))

    def stash_capture(self, capture_sha: str | None) -> None:
        if capture_sha:
            self.stash[capture_sha] = self.capture_frame()

    def restore(self, capture_sha: str | None) -> None:
        frame = self.stash.pop(capture_sha or "", None)
        if frame is None:
            frame = self.seed.pop(capture_sha or "", None)
            if frame is not None:
                self.dirty = True
            else:
                # A capture with no retained model starts empty — but the
                # session counters (word/tile state) stand.
                frame = ScanFrame.blank()
        self.apply(frame)

    def seed_from_records(
        self, models: dict[str, ScanFrame], chips: dict
    ) -> None:
        self.seed = models
        for key, chip in chips.items():
            self.parked_chips.setdefault(key, chip)
        if chips:
            self.dirty = True

    # -- native normalization ------------------------------------------
    def native_scale(self) -> float:
        """Native px per view px for the lane that emitted this event.

        Absent the ratio (a legacy event stream, or a harness driving a
        lane directly) the lane IS native and the multiplier is 1.
        """
        ratio = getattr(self.context, "native_per_view", None)
        if (type(ratio) is tuple and len(ratio) == 2
                and type(ratio[0]) is int and type(ratio[1]) is int
                and ratio[1]):
            return ratio[0] / ratio[1]
        return 1.0

    def to_native(self, box: tuple[float, float, float, float],
                  scale: float) -> tuple[int, int, int, int]:
        y, x, h, w = box
        return (round(y * scale), round(x * scale),
                max(1, round(h * scale)), max(1, round(w * scale)))

    # -- ingest ---------------------------------------------------------
    def ingest_survey(self, survey: object,
                      preview: object = None) -> None:
        regions = tuple(getattr(survey, "regions", ()) or ())
        self.planned.clear()
        if not regions:
            # Empty survey (M/R levels carry zero regions and name their
            # base lane): keep the prior underlay so pane A stays on the
            # page.  Nothing else to do — the frame is native, so it does
            # not belong to the outgoing lane and needs no repair.
            return
        self.regions = []
        self.active_window = None
        self.underlay = None
        transform, (y1, x1), views = self._panes.scan_views(regions)
        self.regions = views
        self.lane = getattr(self.context, "lane_id", None)
        scale, y0, x0 = transform
        # The preview's decimation counts LANE pixels, so the underlay is
        # cropped in the frame ``scan_views`` returned, before the lift.
        self.underlay = self._panes.underlay(
            preview, y0, x0, y1, x1, scale)
        # Lift lane px -> native px:  pane = (lane - o) * s
        #                                  = (native - o*m) * (s/m).
        native = self.native_scale()
        self.transform = (scale / native, y0 * native, x0 * native)

    def ingest_planned(self, details: dict[str, object]) -> None:
        try:
            key = (int(details["address.region"]),
                   int(details["address.window"]))
            box = (int(details["address.box_y"]),
                   int(details["address.box_x"]),
                   int(details["address.box_h"]),
                   int(details["address.box_w"]))
        except (KeyError, TypeError, ValueError):
            return
        self.planned[key] = [
            self.to_native(box, self.native_scale()), "pending"]

    def set_planned_state(self, details: dict[str, object],
                          state: str) -> None:
        region = details.get("address.region")
        window = details.get("address.window")
        if type(region) is int and type(window) is int:
            row = self.planned.get((region, window))
            if row is not None:
                row[1] = state

    def drop_region_planned(self, region: object) -> None:
        if type(region) is int:
            self.planned = {key: row for key, row in self.planned.items()
                            if key[0] != region}

    def ingest_active_window(self, window: object, pitch: object,
                             origin: object) -> None:
        """Native px, projected at draw like every other overlay.

        The old pane-space freeze here went stale the moment a later rung
        replaced the frame — thousands of times per mop-up level, since
        ``address.window_progress`` (unlike the M/R ``survey.complete``)
        does carry a snapshot.
        """
        wy, wx = window.origin_yx_px
        hh, ww = window.shape_yx_cells
        self.active_window = self.to_native(
            (float(origin[0]) + float(wy), float(origin[1]) + float(wx),
             hh * float(pitch), ww * float(pitch)),
            self.native_scale())

    # -- regions --------------------------------------------------------
    def region_lane(self) -> str | None:
        """The lane whose region ordinals an address index addresses.

        An M/R level indexes its BASE lane's regions — mop-up places
        against ``place.mopup_survey``'s rebuild of the base lane's
        durable records, and a refined ``address.final`` carries base-lane
        placements — never its own.  The receiver core already treats
        these as a foreign namespace when it re-bases them
        (``ProductionAddress``); pane A was the last consumer that assumed
        they were local.
        """
        return (self.mopup_base or self.refine_base
                or getattr(self.context, "lane_id", None))

    def set_region_state(self, index: object, state: str) -> None:
        # Region ordinals are LANE-RELATIVE: rungs segment independently,
        # so index N of one lane is a different scrap from index N of
        # another.  During an M/R level the views on screen belong to the
        # last ordinary rung while the indices belong to the base lane —
        # applying them would light the wrong scrap (or, out of range, be
        # silently dropped).  Skip rather than guess; a wrong paint is
        # worse than an absent one on the pane that says where the
        # receiver is working.
        if self.region_lane() != self.lane:
            return
        if type(index) is int and 0 <= index < len(self.regions):
            self.regions[index].state = state

    # -- parked chips ---------------------------------------------------
    def resolve_window(self, details: dict[str, object],
                       capture: str) -> None:
        region = int(details.get("address.region", -1) or 0)
        window = int(details.get("address.window", -1) or 0)
        outcome = str(details.get("address.outcome", "") or "")
        row = self.planned.pop((region, window), None)
        if outcome == "parked":
            # Durable mop-up chip: the planned row is already native px,
            # so the chip outlives its lane's frame by construction.
            if row is not None:
                ordinal = getattr(self.context, "level_ordinal", None)
                digit = None if ordinal is None else str(ordinal + 1)
                lane = getattr(self.context, "lane_id", None) or ""
                self.parked_chips[(capture, lane, region, window)] = (
                    row[0], digit)
            return
        if self.mopup_base is not None:
            # A terminal M-level outcome (accepted/refused/insufficient)
            # retires the base lane's chip; the barrier reconciliation
            # catches anything this misses.
            self.parked_chips.pop(
                (capture, self.mopup_base, region, window), None)

    def reconcile_parked(self, state: object) -> None:
        """Retire chips a committed state no longer carries (§10.5).

        Durable ``ParkedWindowRecord`` rows ride ``SessionState.parked``; a
        chip whose identity has left that set was consumed by its M-level
        (or never committed) and is erased.  Chips are never invented
        here: live chips freeze the actually-emitted layout, and committed
        rows enter only through the v0.45 resume seed.
        """
        rows = getattr(state, "parked", None)
        if rows is None:
            return
        try:
            keys = {
                (str(record.capture_id), str(record.lane_id),
                 int(record.region_index), int(record.window_id))
                for record in rows}
        except (AttributeError, TypeError, ValueError):
            return
        stale = [key for key in self.parked_chips if key not in keys]
        for key in stale:
            del self.parked_chips[key]
        if stale:
            self.dirty = True

    # -- projection / draw ----------------------------------------------
    def box_to_pane(
        self,
        box: tuple[int, int, int, int] | None,
        transform: tuple[float, float, float] | None,
    ) -> tuple[int, int, int, int] | None:
        if transform is None or box is None:
            return None
        scale, oy, ox = transform
        y, x, h, w = box
        x0 = round((x - ox) * scale)
        y0 = round((y - oy) * scale)
        return self._panes.clip_box((
            x0, y0,
            x0 + max(2, round(w * scale)), y0 + max(2, round(h * scale))))

    def pane(self, capture: str) -> np.ndarray:
        planned = []
        for row in self.planned.values():
            box = self.box_to_pane(row[0], self.transform)
            if box is not None:
                planned.append((box, row[1]))
        # Parked-for-mop-up chips: native-px boxes through the one frame,
        # exactly like planned windows and the active window.
        parked = []
        for (chip_capture, _lane, _region, _window), (chip_box, digit) in (
                self.parked_chips.items()):
            if chip_capture != capture:
                continue
            box = self.box_to_pane(chip_box, self.transform)
            if box is not None:
                parked.append((box, digit))
        return self._panes.scan(
            self.regions, self.underlay, tuple(planned),
            self.box_to_pane(self.active_window, self.transform),
            parked=tuple(parked))

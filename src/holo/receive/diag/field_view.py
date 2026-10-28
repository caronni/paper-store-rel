"""W5 field-pane viewer state (PLANE-FIELDS.md §6.2): the LiveView-side
companion to :mod:`.field_stats`'s detached CLI observer.

Split out from :mod:`.viewer` to keep the line-cap discipline (CLAUDE.md:
``<=1000 lines/file`` in ``src/holo``) rather than let one growing concern
push the whole module over -- the same reason :mod:`.scan_model`,
:mod:`.rows`, :mod:`.presentation`, :mod:`.seed` and :mod:`.transport`
already exist as ``viewer.py``'s own siblings instead of being inlined
there.

Two products off ONE producer event (see :mod:`.field_stats`'s module
docstring for the shape read off ``production_color.py``): the retained
``payload.plane_fields`` illustration snapshot (feeds the bottom band
raster, via :meth:`FieldPaneState.band`) and that SAME event's
``plane_fields.rms_dots.*``/``.adopted`` Details (feed the one-line
status-row phrase, via :meth:`FieldPaneState.phrase`).

The W5 build read the Details off a payload ``stage.complete`` event,
which the producer never decorates -- so :attr:`FieldPaneState.rms` stayed
empty and the status row's ``F`` fold never rendered on a real dial-ON
run, the same bug class as the one fixed in :mod:`.field_stats` (the class
was fixed there and left standing here; INDEPENDENT-PLANES §6 P1/P5).

NAMING NOTE: a ``Detail`` name is validated lowercase-only
(``holo.receive.types._NAME_RE``), so the plane suffix arrives as
``.c``/``.m``/``.y`` (see :mod:`.field_stats`'s own NAMING NOTE) and the
C/M/Y spelling is restored only in :meth:`FieldPaneState.phrase`'s output.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np

from .presentation import PaneRenderer

_PLANES = ("C", "M", "Y")


def done_tiles(rows: object, page: int | None,
               ) -> "Iterator[tuple[int, int]]":
    """The snapshot's certified-tile rows in BOTH pinned shapes.

    ``[tile_y, tile_x]`` is page-less and applies to every page (the
    original W5 shape, kept because a snapshot written by an older
    producer must still paint); ``[page, tile_y, tile_x]`` names its page
    and is dropped unless it is ``page``'s own -- a band that painted
    another page's certified tiles would report "nothing left to measure"
    exactly where the operator is looking for a blind spot.

    Anything else (a scalar, a 1-element row) is ignored rather than
    guessed at: mis-reading a 3-row as ``(page, tile_y)`` is what the
    length-blind ``row[0], row[1]`` unpack did.
    """
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        if len(row) == 2:
            yield (int(row[0]), int(row[1]))
        elif len(row) >= 3:
            if page is None or int(row[0]) == page:
                yield (int(row[1]), int(row[2]))


@dataclass(slots=True)
class FieldPaneState:
    """One capture-independent field-pane model.

    Tile-space, not scan-space, so -- unlike :class:`~.scan_model.
    ScanFrame` -- there is nothing to stash/restore per capture: one
    instance serves the whole run.  The measurement it holds (deltas,
    rms, adopted planes) is page-independent too; only the certified-tile
    rows name pages, which is why :meth:`band` renders and caches PER
    PAGE while everything above it stays single-valued.
    """

    snapshot: dict[str, object] | None = None
    dirty: bool = False
    revision: int = 0
    rms: dict[str, float] = field(default_factory=dict)
    adopted: str = ""
    #: page -> band raster.  The cache lives HERE, beside the snapshot
    #: that invalidates it, rather than in the view's own pane-raster
    #: dict: the band is the only raster whose content depends on a page
    #: it is not keyed by (its certified-tile rows name pages), and the
    #: view had to grow two blocks of invalidation bookkeeping to say so.
    _rasters: dict[int, np.ndarray] = field(
        default_factory=dict, repr=False)

    def ingest_snapshot(self, snapshot: object) -> None:
        """The illustration product: retained verbatim, and :attr:`dirty`
        so :meth:`band` drops its cached rasters and re-renders on the
        next composed frame.  A malformed snapshot (not a dict, or
        missing ``"planes"``) is ignored."""
        if isinstance(snapshot, dict) and "planes" in snapshot:
            self.snapshot = snapshot
            self.dirty = True
            self.revision += 1

    def ingest_details(self, details: dict[str, object]) -> None:
        """The scalar product of the SAME event: latest value wins per
        plane -- a glance number, not an accumulated statistic
        (:mod:`.field_stats` owns peak/rms history for the CLI epilogue).
        An event with none of these keys is a silent no-op."""
        for plane in _PLANES:
            value = details.get(f"plane_fields.rms_dots.{plane.lower()}")
            if value is not None:
                self.rms[plane] = float(value)
        adopted = details.get("plane_fields.adopted")
        if adopted is not None:
            self.adopted = str(adopted)

    def build_raster(self, panes: PaneRenderer,
                     page: int | None = None) -> np.ndarray:
        """The band raster for the retained snapshot, for one ``page`` (or
        an empty/no-data band if no snapshot has arrived -- callers only
        invoke this once :attr:`snapshot` is not ``None``, matching the
        byte-stability rule: a dial-off run never calls this at all).

        ``page`` selects which certified tiles the band may paint green;
        pass ``None`` (the default) to accept every row whatever page it
        names, which is what a caller with no page context wants."""
        snapshot = self.snapshot or {}
        planes = tuple(snapshot.get("planes") or ())
        done = tuple(done_tiles(snapshot.get("done") or (), page))
        hint = snapshot.get("exaggeration_hint", 1.0)
        raster, _factor = panes.field_band(planes, float(hint), done=done)
        return raster

    def band(self, panes: PaneRenderer, page: int) -> np.ndarray | None:
        """This page's band raster, or ``None`` while no snapshot has
        arrived -- the byte-stability rule (a dial-off run composes
        exactly the four panes it always did, band and all absent).

        Built lazily per composed page and dropped wholesale when a newer
        snapshot lands, so a page nobody looks at is never rendered."""
        if self.snapshot is None:
            return None
        if self.dirty:
            self._rasters.clear()
            self.dirty = False
        raster = self._rasters.get(page)
        if raster is None:
            raster = self._rasters[page] = self.build_raster(panes, page)
        return raster

    def retain(self, pages: "set[int]") -> None:
        """Drop cached bands for pages the view no longer keeps live."""
        if not self._rasters:
            return
        self._rasters = {page: raster
                         for page, raster in self._rasters.items()
                         if page in pages}

    def phrase(self) -> str:
        """The compact ``F ...`` status-row fold, or "" while no rms
        Details have arrived -- rows.py folds this into the format row
        only when non-empty, so the row reads exactly as it did before
        this feature existed."""
        if not self.rms:
            return ""
        parts = " ".join(
            f"{plane}{self.rms[plane]:+.2f}d" for plane in _PLANES
            if plane in self.rms)
        if not parts:
            return ""
        return f"F {parts} [{self.adopted or 'none'}]"


__all__ = ["FieldPaneState", "done_tiles"]

"""Real diag panes for holo2 (DESIGN §10.3, L12 — observer-only).

The v1 receiver's four-pane live viewer, cloned where it fits and
stripped where it does not. What carried, what changed, and why:

* **transport** — the measured e023c pattern: a cheap status channel the
  browser polls, and a composed PNG frame per page it refetches only when
  that page's revision moves (v1 measured: status publish 0.3-0.5 ms vs
  61-118 ms rendered frames). holo2's revision is ``store.commit_seq``,
  which is work-counted, so the status-first doctrine survives the L12
  ban on clocks in every path rather than only in receiver paths.
* **composition** — v1's fixed frame: four equal panes in one horizontal
  row under burned-in headings, bodies rendered as rasters and pasted.
* **palette** — v1's operator primaries-on-white and its two-tone chips,
  green-certified language unchanged.
* **panes** — mapped, not transplanted (see :mod:`.render` for the table):
  A capture space (regions, support, window lattice, committed poses,
  §6 done pixels), B the page's tile map per work key and stream,
  C the worker/queue pane holo2 needs and v1 had no equivalent for,
  D the fountain close per (stream, block).
* **stripped** — lanes, rungs, levels, barriers, parked chips, the
  capture-major driver, the BCH word-site pane, and the filesystem
  publication side-channel. holo2 has footings, workers and commits, and
  its state directory is the store, not a diagnostic scratch directory.

Every entry point here is inert on failure: a pane that cannot be built
returns a frame that says so, and the caller (:mod:`holo2.diag`) swallows
anything that escapes.
"""
from __future__ import annotations

from .model import (CaptureMark, PaneModel, PaneModelError, PaneSource,
                    RegionMark, TilePlane, WindowMark)
from .publish import (DIAG_DIR_SUFFIX, REPORT_NAME, STATUS_NAME, build_report,
                      diag_directory, frame_name, write_artifacts)
from .render import (DEFAULT_PANE_WIDTH, PANE_TITLES, capture_pane,
                     close_pane, frame_size, page_pane, pane_size,
                     render_frame, workers_pane)
from .shell import PAGE, PAGE_BYTES

__all__ = [
    "CaptureMark", "DEFAULT_PANE_WIDTH", "DIAG_DIR_SUFFIX", "PAGE",
    "PAGE_BYTES", "PANE_TITLES", "PaneModel", "PaneModelError", "PaneSource",
    "REPORT_NAME", "RegionMark", "STATUS_NAME", "TilePlane", "WindowMark",
    "build_report", "capture_pane", "close_pane", "diag_directory",
    "frame_name", "frame_size", "page_pane", "pane_size", "render_frame",
    "workers_pane", "write_artifacts",
]

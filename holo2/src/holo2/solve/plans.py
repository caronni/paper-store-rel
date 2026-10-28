"""Region lattices and window plans: the pose-free structure of a capture.

R1 moved :class:`WindowPlan` here from ``engine/runtime.py``; R2 completes
the move by bringing the enumeration that produces the plans, and the
region lattice they are laid out on. All of it is geometry, not
scheduling — a rectangle of capture cells, named before any worker
exists — and leaving it in the engine forced the scheduler to know what a
printed cell measures.

A window is named by what it IS — footing, region, extent — never by the
order it was enumerated in, so two runs, two footings and a resumed
state agree on the name without coordinating. Since the hash-free
identity law those values ARE the name (``records.window_key``); this
module no longer mints one.

Choices where DESIGN is silent (for adjudication, carried from the module
this split):

- **A capture whose survey declined to vote a cell pitch gets no
  windows.** ``RegionCandidate.pitch_in_vote`` is legally ``None`` (the
  survey refuses to invent a lattice); the answer here is to carry the
  region honestly as unschedulable rather than guess a pitch.
- **Every footing of a capture gets the same window extents.** The
  lattice is a property of (capture, region): footings differ in
  sampling, not in physical cell size.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from ..capture import FootingSpec, RegionCandidate, SupportMask, region_key
from ..core import CaptureSha, FootingId, ResourceKey
from ..format import FormatRowSpec, native_cell_pitch_px
from .geometry import (CellLattice, WINDOW_CELLS, WINDOW_STEP_CELLS,
                       window_starts)
from .place_model import PlacementConfig
from .pose_fit import subdivision_child_extents
from .records import window_key


@dataclass(frozen=True)
class WindowPlan:
    """A window as the scheduler names it, before any worker exists."""

    window_id: ResourceKey
    footing_id: FootingId
    region_id: ResourceKey
    capture_sha256: CaptureSha
    extent_cells: tuple[int, int, int, int]
    supported_cells: int


@dataclass(frozen=True)
class RegionView:
    """One surveyed region plus the pose-free lattice windows live on."""

    candidate: RegionCandidate
    lattice: CellLattice | None
    support: np.ndarray | None

    @property
    def region_id(self) -> ResourceKey:
        """The region's key: its capture and its support grid (§10.2)."""
        candidate = self.candidate
        return region_key(
            CaptureSha(candidate.capture_sha256),
            (int(candidate.support.origin_yx[0]),
             int(candidate.support.origin_yx[1])),
            int(candidate.support.step_px),
            (int(candidate.support.extent_px[0]),
             int(candidate.support.extent_px[1])))

    @property
    def capture_sha256(self) -> CaptureSha:
        return self.candidate.capture_sha256

    @property
    def schedulable(self) -> bool:
        return self.lattice is not None and self.support is not None


def sample_support(mask: SupportMask, lattice: CellLattice) -> np.ndarray:
    """Which capture cells of ``lattice`` are supported by ``mask``.

    Cell-centre sampling of the survey's block-constant support grid: a
    cell is supported iff its centre lands in a true survey cell. Cheaper
    and coarser-safe than rasterizing native pixels, and exact at the
    granularity a window is clipped on.
    """
    rows, cols = lattice.shape_cells
    centres_y = lattice.centres_y(0, rows) - mask.origin_yx[0]
    centres_x = lattice.centres_x(0, cols) - mask.origin_yx[1]
    iy = np.floor(centres_y / mask.step_px).astype(np.int64)
    ix = np.floor(centres_x / mask.step_px).astype(np.int64)
    valid_y = (iy >= 0) & (iy < mask.cells.shape[0])
    valid_x = (ix >= 0) & (ix < mask.cells.shape[1])
    support = np.zeros((rows, cols), bool)
    if not valid_y.any() or not valid_x.any():
        return support
    picked = mask.cells[np.ix_(iy[valid_y], ix[valid_x])]
    support[np.ix_(np.flatnonzero(valid_y), np.flatnonzero(valid_x))] = picked
    return support


def region_view(format_row: FormatRowSpec, candidate: RegionCandidate,
                dpi: float) -> RegionView:
    """One surveyed region on its capture-cell lattice, or unschedulable."""
    if candidate.pitch_in_vote is None:
        return RegionView(candidate, None, None)
    # The pitch in PIXELS is a function of the DECLARED dpi and the
    # SURVEYED pitch vote, not of row state — so it is read off the
    # module, not off ``format_row``, which knows neither number.  Both
    # halves are exact rationals since C3 (RULINGS G4, 2026-08-22): the
    # vote is a printed pitch in inches and this multiplies it by the
    # capture's declared dpi, where it used to divide a dot count by a
    # hard-coded 600.
    pitch = native_cell_pitch_px(dpi, candidate.pitch_in_vote)
    lattice = CellLattice.over(candidate.support.origin_yx,
                               candidate.support.extent_px, pitch)
    return RegionView(candidate, lattice,
                      sample_support(candidate.support, lattice))


def window_plans_for(footing: FootingSpec,
                     regions: Iterable[RegionView]) -> tuple[WindowPlan, ...]:
    """v1's flush-shifted window lattice for one footing (§8.2), id-sorted.

    Since the window-alignment ruling this enumeration is
    ``pose_fit.layout_pose_windows``' own — the same size, step and flush
    shift, in the capture-CELL frame the durable window name lives in
    (:func:`~holo2.solve.geometry.window_starts` states the frame
    correspondence and where it is exact). ``min`` on the far corner is
    therefore a no-op for every start but the one on an axis shorter than
    a window; it is kept because it is what makes that case's clip
    explicit.

    The one enumeration rule that is holo2's and not v1's: a window is
    dropped when the region supports NO cell of it, counted exactly on
    the region's own support grid rather than estimated off a ``[::4,
    ::4]`` subsample. v1's 30-site layout estimate is not reproduced
    here — the same floor is applied to the exactly-sampled window by the
    placement worker (``E022_SUPPORT_FLOOR_SITES``,
    ``insufficient_support``), where it judges the cells the pose really
    read instead of a pose-free guess at them.
    """
    plans: list[WindowPlan] = []
    for view in regions:
        if view.capture_sha256 != footing.capture_sha256:
            continue
        if not view.schedulable:
            continue
        assert view.lattice is not None and view.support is not None
        region = view.region_id
        rows, cols = view.lattice.shape_cells
        for cy0 in window_starts(rows, WINDOW_CELLS, WINDOW_STEP_CELLS):
            cy1 = min(rows, cy0 + WINDOW_CELLS)
            for cx0 in window_starts(cols, WINDOW_CELLS, WINDOW_STEP_CELLS):
                cx1 = min(cols, cx0 + WINDOW_CELLS)
                extent = (cy0, cx0, cy1, cx1)
                supported = int(np.count_nonzero(
                    view.support[cy0:cy1, cx0:cx1]))
                if supported == 0:
                    continue
                plans.append(WindowPlan(
                    window_id=window_key(footing.footing_id, region, extent),
                    footing_id=footing.footing_id, region_id=region,
                    capture_sha256=view.capture_sha256,
                    extent_cells=extent, supported_cells=supported))
    return tuple(sorted(plans, key=lambda plan: plan.window_id))


def child_window_plans(plan: WindowPlan, region: RegionView, *, depth: int,
                       config: PlacementConfig) -> tuple[WindowPlan, ...]:
    """One window's E022 corner retries, as ORDINARY plans (W3, PL5).

    Subdivision in the pull model is not a provider minting a different
    kind of thing: it is four more members for the scheduling set, and a
    child is a window like any other — named by ``window_key`` from its
    own extent, on its parent's footing and region, support-counted on
    the same grid ``window_plans_for`` counts on. That is why this lives
    here beside the enumeration rather than in the scheduler: the ONLY
    difference between a child and a laid-out window is which arithmetic
    chose the rectangle.

    ``depth`` is the parent's, and it is the scheduler's in-memory stage
    memory rather than a field of anything durable (the no-lineage
    ruling): a child is admitted at ``depth + 1``, and
    :data:`~holo2.solve.pose_fit.SUBDIVISION_MAX_DEPTH` is what stops it
    subdividing again. An unschedulable region has no lattice to count
    on and yields nothing, exactly as it yields no laid-out windows.

    A child supported by NO cell is dropped, which is
    ``window_plans_for``'s own rule: an unsupported rectangle has no
    pixels to read and nothing to be refused about.
    """
    if not region.schedulable:
        return ()
    assert region.lattice is not None and region.support is not None
    rows, cols = region.lattice.shape_cells
    plans: list[WindowPlan] = []
    for extent in subdivision_child_extents(plan.extent_cells, depth=depth,
                                            config=config):
        cy0, cx0, cy1, cx1 = extent
        if cy0 < 0 or cx0 < 0 or cy1 > rows or cx1 > cols:
            continue          # a corner outside the lattice is not a window
        supported = int(np.count_nonzero(region.support[cy0:cy1, cx0:cx1]))
        if supported == 0:
            continue
        plans.append(WindowPlan(
            window_id=window_key(plan.footing_id, plan.region_id, extent),
            footing_id=plan.footing_id, region_id=plan.region_id,
            capture_sha256=plan.capture_sha256,
            extent_cells=extent, supported_cells=supported))
    return tuple(plans)


__all__ = ["RegionView", "WindowPlan", "child_window_plans", "region_view",
           "sample_support", "window_plans_for"]

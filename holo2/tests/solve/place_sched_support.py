"""Shared scheduling doubles for the place_sched/place_job test split.

Split out of ``test_place_sched.py`` on 2026-08-17 under the cap-as-seam-
signal ruling (1000 lines marks a split-here point, never a budget to
squeeze prose against): ``test_place_sched.py`` pins the pull model's
QUEUE (admission, the flag protocol, pricing and pings) and
``test_place_job.py`` pins the JOB (the ratified distance, the consult,
the floor, and the ladder that drives it). Both need the same admitted-
plane builders and the same sparse/confetti gapped lattice, so those live
here as a plain importable module rather than being duplicated or pytest-
fixture-injected — the same pattern this suite already uses for
``test_placement``'s ``_Plane`` double, just promoted out of a ``test_``
module so a shared name never collides with the repo-wide test-basename
guard.
"""
from __future__ import annotations

from holo2.core import WorkResult
from holo2.solve.place_sched import (LANE_COST_PER_RUNG, TIER_PRICE,
                                     PlacementScheduler)
from holo2.solve.records import PoseRecord, pose_key, window_key
from conftest import FOOTING, REGION
from test_placement import PLAN_A, ROW, _Plane, _plan

AFFINE = (6.0, 0.0, 1.0, 0.0, 6.0, 2.0)

#: ``_Plane``'s ladder is two rungs (ppc 2, then ppc 8) and every plan
#: these fixtures build sits on the FINE one, so every slot they produce
#: carries the lane term of depth 1. It was ``FOOTING_PREMIUM`` (a flat 1)
#: until H4-LANES stage 2 made the term per-rung.
FINE_LANE_TERM = LANE_COST_PER_RUNG * 1


def _scheduler(plane: _Plane, *, entry: int = 0,
               selector: str = "all") -> PlacementScheduler:
    scheduler = PlacementScheduler(ROW)
    scheduler.admit(plane, entry=entry, selector=selector)
    return scheduler


def _priced(tier: str) -> int:
    """What these tests' windows pay for one tier.

    Every plan this module builds sits on ``_Plane``'s FINE lane, which
    is one rung above its coarsest, so every slot carries
    :data:`FINE_LANE_TERM`. Spelling it out at each assertion keeps the
    tier and the lane term separately visible.
    """
    return TIER_PRICE[tier].cost + FINE_LANE_TERM


def _pose(window, page: int = 0) -> PoseRecord:
    return PoseRecord(window_id=window, footing_id=FOOTING, page=page,
                      native_affine=AFFINE)


def _placed(plane_kwargs: dict, window) -> _Plane:
    """A plane in which ``window`` carries one committed pose."""
    pose = _pose(window)
    key = pose_key(window, 0, AFFINE)
    records = dict(plane_kwargs.pop("records", {}))
    records[key] = pose
    return _Plane(records=records, poses={window: (key,)}, **plane_kwargs)


# ------------------------------------------------- a region with a gap in it
#
# A (200, 680) lattice lays FOUR window starts on the row — 0, 160, 320, 480
# — and this fixture gives plans to the first, the third and the fourth. The
# ring is membership by lattice INDEX, so WINDOW_A's only neighbour is the
# start nothing sits on: its ring consult is EMPTY while two windows two and
# three strides away are perfectly visible page-wide. That is the
# sparse/confetti shape the wide tier and R-B exist for, in the smallest
# lattice that can hold it.

GAPPED_CELLS = (200, 680)
FAR_C = window_key(FOOTING, REGION, (0, 320, 200, 520))
FAR_D = window_key(FOOTING, REGION, (0, 480, 200, 680))
PLAN_C = _plan(FAR_C, (0, 320, 200, 520))
PLAN_D = _plan(FAR_D, (0, 480, 200, 680))


def _gapped(*placed) -> _Plane:
    """The gapped region, with ``placed`` windows carrying a pose."""
    poses = {window: (pose_key(window, 0, AFFINE),) for window in placed}
    return _Plane(plans=(PLAN_A, PLAN_C, PLAN_D), shape_cells=GAPPED_CELLS,
                  records={keys[0]: _pose(window)
                           for window, keys in poses.items()},
                  poses=poses)


# ------------------------------------------------------ subdivision children
#
# WINDOW_A is (0, 0, 200, 200), so its corner children are the four
# 100-cell squares below — ``max(min_window_cells, 200 // 2)`` is 100,
# and 100 is above the 70-cell floor, so they tile the parent exactly.
# Shared by three modules since W4 (``test_place_cold`` drives a child
# out to its own cold pair), which is what this module is for.

CHILDREN_A = tuple(window_key(FOOTING, REGION, extent) for extent in (
    (0, 0, 100, 100), (0, 100, 100, 200),
    (100, 0, 200, 100), (100, 100, 200, 200)))


def _refuse(scheduler: PlacementScheduler, window, outcome: str,
            plane: _Plane | None = None) -> None:
    """One whole claim/settle pass that refuses with ``outcome``."""
    plane = plane if plane is not None else _Plane()
    assert scheduler.claim(plane, window) is not None
    scheduler.settle(plane, window, WorkResult(outcome=outcome))

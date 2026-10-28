"""Region lattices and window plans: the pose-free structure of a capture.

R2 split ``engine/runtime.py``; these are the assertions of its test that
are about geometry — the lattice a region's windows live on, the support
sampling that decides which cells count, and the content-derived window
lattice every footing of a capture shares.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo2.capture.ingest import ingest_capture
from holo2.capture.records import FootingSpec
from holo2.capture.survey import RegionCandidate, SupportMask
from holo2.core.commit import CommitEngine
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.format import FormatRowSpec
from holo2.format.close_spec import CloseStreamProfile
from holo2.solve.geometry import CellLattice, WINDOW_CELLS
from holo2.solve.place_model import PlacementConfig
from holo2.solve.plane import open_plane
from holo2.solve.plans import (WindowPlan, child_window_plans, region_view,
                               sample_support, window_plans_for)
from holo2.solve.records import window_key
from conftest import registry

DPI = 600.0

#: The pitch the hand-built region candidates below vote, chosen to be
#: 4 native px at ``DPI`` — which is what the dot count ``4`` meant when
#: the vote was ``c_dots_vote`` on a hard-coded 600-dpi grid (C3,
#: RULINGS G4, 2026-08-22).
PITCH_4PX_AT_600 = Fraction(4, 600)

ROW = FormatRowSpec(
    row_id="c3-test@128x128", codec_id="k-v1", seed=b"holo/v1/test/128x128",
    tiles_yx=(2, 2), pitch_in=Fraction(1, 200),
    streams=(CloseStreamProfile("main", 32),), n_pages=1)


@pytest.fixture
def plane(tmp_path: Path, synthetic_print: Path):
    """The derived plane over one ingested synthetic capture.

    Since streaming ingestion (H4) the survey is WORK and no longer
    runs inside ``open_plane``, so the fixture ingests through the direct
    path — the same derivation the ingest fire proposes, committed
    through the same wall — and the plane attaches the pixels by reopen,
    exactly as the committing thread does mid-run.
    """
    from conftest import make_session

    store = Store.open_or_create(tmp_path / "state",
                                 make_session(), registry(),
                                 fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in)
    yield open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    store.close()


def test_footing_selectors_partition_the_ladder(plane) -> None:
    coarsest = plane.footing_ids("coarsest")
    finer = plane.footing_ids("finer")
    every = plane.footing_ids("all")
    assert len(coarsest) == 1
    assert set(coarsest) | set(finer) == set(every)
    assert not set(coarsest) & set(finer)
    assert plane.footing(coarsest[0]).ppc == Fraction(2)


def test_the_survey_only_votes_pitches_a_format_can_name() -> None:
    """capture's candidate set is always a set of pitches formats name.

    Two halves since C3b (RULINGS H1(b), 2026-08-22).  The BLIND set is
    the registered pitch classes, member for member; a survey handed a
    DECLARED row adds that row's own pitch, which a format spells by
    definition — it came off one.  So the invariant survives the union
    and is now stated as the union: whatever ``candidate_pitches``
    returns, every member is a pitch some identity can carry.

    The two tables cannot be one object: ``capture`` may not import
    ``format`` (the layering DAG), and the questions differ — which
    pitches a BLIND stage will hypothesise, versus which pitches have
    IDENTITIES.  ``solve`` is where they meet (``region_view`` feeds a
    survey vote into ``native_cell_pitch_px`` beside a row), so the
    agreement is pinned here.

    The fork it prevents: a survey that votes a pitch no format spells,
    which would lay a lattice, place windows and spend fires on a sheet
    no row could ever decode — the mirror of the refusal C3b removed
    (RULINGS G4/H1, 2026-08-22).  If the two ever have to differ, this
    test is where the reason gets written down.
    """
    from holo2.capture.survey import CANDIDATE_PITCHES_IN, candidate_pitches
    from holo2.format.lattice import PITCH_CLASSES

    assert set(CANDIDATE_PITCHES_IN) == set(PITCH_CLASSES.values())
    assert list(CANDIDATE_PITCHES_IN) == sorted(CANDIDATE_PITCHES_IN)
    # A declared row at a registered class changes NOTHING — the same
    # tuple object comes back, so no snap can decide differently.
    for pitch in PITCH_CLASSES.values():
        assert candidate_pitches(pitch) is CANDIDATE_PITCHES_IN
    # A declared row at a lawful rational adds exactly itself, in order.
    declared = Fraction(1, 400)
    assert set(candidate_pitches(declared)) == set(
        PITCH_CLASSES.values()) | {declared}
    assert list(candidate_pitches(declared)) == sorted(
        candidate_pitches(declared))


def test_region_lattice_is_pose_free_and_shared_by_footings(plane) -> None:
    view = plane.captures[0].regions[0]
    assert view.schedulable
    assert view.lattice.pitch_px == Fraction(3)
    assert view.lattice.origin_yx == view.candidate.support.origin_yx
    assert view.support.shape == view.lattice.shape_cells


def test_window_plans_are_content_derived_and_deterministic(plane) -> None:
    footing_id = plane.footing_ids("coarsest")[0]
    plans = plane.window_plans(footing_id)
    assert plans
    assert plans == plane.window_plans(footing_id)
    for plan in plans:
        assert plan.window_id == window_key(
            footing_id, plan.region_id, plan.extent_cells)
        assert plan.supported_cells > 0
        cy0, cx0, cy1, cx1 = plan.extent_cells
        assert 0 <= cy0 < cy1 <= WINDOW_CELLS + cy0
        assert 0 <= cx0 < cx1
    assert len({plan.window_id for plan in plans}) == len(plans)


def test_every_footing_gets_the_same_window_extents(plane) -> None:
    """Windows are physical: footings differ in sampling, not cell size."""
    extents = {
        footing_id: {plan.extent_cells
                     for plan in plane.window_plans(footing_id)}
        for footing_id in plane.footing_ids("all")
    }
    assert len(set(map(frozenset, extents.values()))) == 1


def test_window_plans_lay_the_flush_shifted_lattice() -> None:
    """The alignment ruling, at the surface production reads it through.

    A 513x514-cell region (the differential's ``clean`` arm, at pitch 4:
    2052x2056 px) lays out 3x3 windows, EVERY one a full 200x200 —
    starts 0, 160 and 513-200 = 313 on y, 0, 160 and 514-200 = 314 on x.
    The clipped lattice this replaces laid out the same nine starts but
    sized the last ones 193 and 194, so the four corner-most windows
    addressed 193x194 = 37,442 cells instead of 40,000.
    """
    sha = "a" * 64
    step, cells = 4, np.ones((513, 514), bool)
    support = SupportMask((0, 0), step, cells, (513 * step, 514 * step))
    candidate = RegionCandidate(sha, support, PITCH_4PX_AT_600,
                                (0, 0, 2052, 2056), 1.0)
    view = region_view(ROW, candidate, DPI)
    assert view.lattice is not None
    assert view.lattice.shape_cells == (513, 514)   # 2052/4, 2056/4
    plans = window_plans_for(FootingSpec("f", Fraction(1), sha), (view,))
    assert sorted(plan.extent_cells for plan in plans) == [
        (cy0, cx0, cy0 + 200, cx0 + 200)
        for cy0 in (0, 160, 313) for cx0 in (0, 160, 314)]
    assert {plan.supported_cells for plan in plans} == {200 * 200}


def _one_region_view(cells: np.ndarray) -> object:
    """One fully-declared region over a boolean support grid at pitch 4."""
    support = SupportMask((0, 0), 4, cells, (cells.shape[0] * 4,
                                             cells.shape[1] * 4))
    candidate = RegionCandidate("a" * 64, support, PITCH_4PX_AT_600,
                                (0, 0, cells.shape[0] * 4, cells.shape[1] * 4),
                                1.0)
    return region_view(ROW, candidate, DPI)


def test_child_window_plans_are_ordinary_support_counted_windows() -> None:
    """W3 subdivision: a child differs only in which arithmetic chose it.

    Same key function, same footing and region, and its supported cells
    counted on the same grid ``window_plans_for`` counts on — so nothing
    downstream (R5's seed ranking, the pose window's own extent) can tell
    a corner retry from a laid-out window, which is the point.
    """
    view = _one_region_view(np.ones((300, 300), bool))
    plans = window_plans_for(FootingSpec("f", Fraction(1), "a" * 64), (view,))
    parent = next(plan for plan in plans if plan.extent_cells[:2] == (0, 0))
    children = child_window_plans(parent, view, depth=0,
                                  config=PlacementConfig())
    assert [plan.extent_cells for plan in children] == [
        (0, 0, 100, 100), (0, 100, 100, 200),
        (100, 0, 200, 100), (100, 100, 200, 200)]
    for plan in children:
        assert plan.window_id == window_key(parent.footing_id,
                                            parent.region_id,
                                            plan.extent_cells)
        assert plan.footing_id == parent.footing_id
        assert plan.region_id == parent.region_id
        assert plan.capture_sha256 == parent.capture_sha256
        assert plan.supported_cells == 100 * 100


def test_a_child_supported_by_nothing_is_not_a_window() -> None:
    """``window_plans_for``'s own rule, applied to the corner retries.

    An unsupported rectangle has no pixels to read and nothing to be
    refused about. Here the paper ends at column 100, so the parent's
    two right-hand corners never become windows — which is exactly the
    fragment-edge shape subdivision exists for, and the case where a
    window's own fit refuses while its left corners still fit.
    """
    cells = np.ones((300, 300), bool)
    cells[:, 100:] = False
    view = _one_region_view(cells)
    plans = window_plans_for(FootingSpec("f", Fraction(1), "a" * 64), (view,))
    parent = next(plan for plan in plans if plan.extent_cells[:2] == (0, 0))
    children = child_window_plans(parent, view, depth=0,
                                  config=PlacementConfig())
    assert [plan.extent_cells for plan in children] == [
        (0, 0, 100, 100), (100, 0, 200, 100)]
    assert {plan.supported_cells for plan in children} == {100 * 100}


def test_an_unschedulable_region_yields_no_children() -> None:
    """No lattice, no windows — laid out or subdivided, the same answer."""
    support = SupportMask((0, 0), 4, np.ones((300, 300), bool), (1200, 1200))
    candidate = RegionCandidate("a" * 64, support, None, (0, 0, 1200, 1200),
                                1.0)
    view = region_view(ROW, candidate, DPI)
    assert not view.schedulable
    parent = WindowPlan(window_id=window_key("f", view.region_id,
                                             (0, 0, 200, 200)),
                        footing_id="f", region_id=view.region_id,
                        capture_sha256="a" * 64,
                        extent_cells=(0, 0, 200, 200), supported_cells=40_000)
    assert child_window_plans(parent, view, depth=0,
                              config=PlacementConfig()) == ()


def test_sample_support_is_cell_centre_inclusion() -> None:
    cells = np.array([[True, False], [True, True]])
    mask = SupportMask((10, 20), 4, cells, (8, 8))
    lattice = CellLattice((10, 20), Fraction(2), (4, 4))
    support = sample_support(mask, lattice)
    assert support.tolist() == [[True, True, False, False],
                                [True, True, False, False],
                                [True, True, True, True],
                                [True, True, True, True]]


def test_sample_support_is_false_outside_the_mask() -> None:
    mask = SupportMask((100, 100), 4, np.ones((2, 2), bool), (8, 8))
    lattice = CellLattice((0, 0), Fraction(2), (4, 4))
    assert not sample_support(mask, lattice).any()

"""WHICH RUNGS PLACE, as declared policy (H4-LANES stage 1).

``place_shared.working_footing_id`` computed a hard max over ppc and
exited every other footing's windows, permanently. That was tolerated at
H3bis and never ratified, and this wave replaces it with data: a reading
set, declared on the recipe's placement entries, riding
``SessionIdentity`` with them, read once by the scheduler it is composed
into.

Two claims here, and the first is the one stage 1 lives or dies on:

1. **the ``finest`` default reproduces the old arithmetic exactly**, on a
   multi-rung ladder — window for window, and asserted against the max
   over ppc restated here rather than against the function that was
   deleted (a replacement checked against itself proves nothing);
2. **the exit is unchanged** — same string, same windows, same
   ``_exited`` map, because stage 1 is invisible to scheduling.

The gate's own footing generalisation is here too: ``has_footing_pixels``
is now asked per rung, and at the native rung it has to answer exactly
what ``raster`` answered before it existed.

The POLICY half — that the value is recipe data, that it rides the
lineage identity, and that the two spellings of the vocabulary agree
across the package wall — is pinned on the engine's side of that wall
(``tests/engine/test_reading_set_policy.py``), where a test may name both
packages. A solve test may not import ``engine``, and the DAG says so.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo2.capture.ingest import ingest_capture
from holo2.core.commit import CommitEngine
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.solve import PlacementScheduler
from holo2.solve.place_model import PlacementConfig
from holo2.solve.place_sched import EXIT_OUTSIDE_READING_SET
from holo2.solve.place_shared import (READING_ALL, READING_FINEST,
                                      READING_SETS, pixel_work_is_attachable,
                                      reading_set_places)
from holo2.solve.plane import open_plane
from conftest import make_session, registry
from test_placement import COARSE, FOOTING, ROW as FAKE_ROW, _Plane, _plan
from holo2.solve.records import window_key
from holo2.format.registry_rows import format_row
from conftest import REGION

DPI = 600.0
ROW = format_row("c3-k-r0550", (2, 2), 1)


def _finest_of(view, capture_sha256):
    """``working_footing_id``'s arithmetic, restated as the oracle.

    Deliberately a transcription of the DELETED function rather than a
    call to its replacement: what is under test is that the policy's
    default answers what the hard max answered, so the two expressions
    have to be independent.
    """
    best = None
    for footing_id in view.footing_ids("all"):
        footing = view.footing(footing_id)
        if footing.capture_sha256 != capture_sha256:
            continue
        candidate = (footing.ppc, footing_id)
        if best is None or candidate > best:
            best = candidate
    return None if best is None else best[1]


# ------------------------------------------- (1) finest IS the working footing

def test_finest_reproduces_the_working_footing_on_a_multi_rung_ladder(
        ) -> None:
    """The fake plane declares ppc 8 and ppc 2 for one capture."""
    view = _Plane()
    plans = [_plan(window_key(FOOTING, REGION, (0, 0, 200, 200)),
                   (0, 0, 200, 200), footing=FOOTING),
             _plan(window_key(COARSE, REGION, (0, 0, 200, 200)),
                   (0, 0, 200, 200), footing=COARSE)]
    finest = _finest_of(view, plans[0].capture_sha256)
    assert finest == FOOTING, "the fixture's finest rung moved"
    for plan in plans:
        assert reading_set_places(view, plan, READING_FINEST) == (
            plan.footing_id == finest)
        assert reading_set_places(view, plan, READING_ALL), (
            "the cascade places every rung")


def test_finest_is_the_finest_on_a_real_ladder(tmp_path: Path,
                                               synthetic_print: Path) -> None:
    """The same claim over a real capture's real ``auto_ppc_levels``."""
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    try:
        ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in)
        plane = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
        capture = plane.captures[0]
        assert len(capture.footings) >= 2, "the fixture needs a coarse rung"
        finest = _finest_of(plane, capture.source_sha256)
        placed = set()
        for footing in capture.footings:
            for plan in plane.window_plans(footing.footing_id):
                if reading_set_places(plane, plan, READING_FINEST):
                    placed.add(plan.footing_id)
                assert reading_set_places(plane, plan, READING_ALL)
        assert placed == {finest} == {capture.footings[-1].footing_id}
    finally:
        store.close()


def test_an_unknown_reading_set_places_nothing() -> None:
    """A policy nobody implements may not degrade into the widest one."""
    view = _Plane()
    plan = _plan(window_key(FOOTING, REGION, (0, 0, 200, 200)),
                 (0, 0, 200, 200), footing=FOOTING)
    assert not reading_set_places(view, plan, "every-other-tuesday")
    assert READING_SETS == {READING_FINEST, READING_ALL}


def test_the_composition_root_binds_the_recipes_reading_set() -> None:
    """``cli`` is the one package any test may drive, so the binding is
    checkable from here; what it binds FROM is the engine test's claim.

    MOVED PIN (stage 2's default flip): the root binds ``all`` now. That
    it binds it FROM the recipe rather than from a constant is pinned on
    the engine side of the wall, where a test may name a recipe
    (``tests/engine/test_reading_set_policy.py``).
    """
    from holo2.cli import real_source
    assert real_source(ROW).reading_set == READING_ALL


# ------------------------------------------ (2) the exit, rarer and renamed

def test_the_cascade_admits_every_rung_and_the_exit_is_the_declared_one(
) -> None:
    """Stage 2: the default admits, and the exit belongs to a declaration.

    Two MOVED PINS in one, with one cause — the reading set opened. The
    default scheduler no longer exits a coarse window at all, and the
    reason string a ``finest`` run still produces names the POLICY rather
    than a "working footing" the receiver no longer computes.
    """
    plans = (_plan(window_key(COARSE, REGION, (0, 0, 200, 200)),
                   (0, 0, 200, 200), footing=COARSE),)
    cascade = PlacementScheduler(FAKE_ROW)
    assert cascade.reading_set == READING_ALL
    cascade.admit(_Plane(plans=plans), entry=0, selector="coarsest")
    assert set(cascade._slots) and not cascade._exited

    narrow = PlacementScheduler(FAKE_ROW, reading_set=READING_FINEST)
    narrow.admit(_Plane(plans=plans), entry=0, selector="coarsest")
    assert not narrow._slots
    assert set(narrow._exited.values()) == {EXIT_OUTSIDE_READING_SET}


def test_the_lane_terms_ladder_depth_is_the_generators_own(
) -> None:
    """``MAX_LANE_DEPTH`` against ``auto_ppc_levels``, not against memory.

    The cost table's bounds are all stated at that depth
    (``tests/engine/test_cost_vocabulary.py``), and the engine tier of
    the test DAG may not name ``capture`` — so the datum is pinned here,
    where a test may ask the ladder generator directly.
    """
    from fractions import Fraction

    from holo2.capture.scale_space import auto_ppc_levels
    from holo2.solve.place_sched import MAX_LANE_DEPTH

    c2, c3 = Fraction(1, 300), Fraction(1, 200)
    assert len(auto_ppc_levels(4800, c3)) - 1 == MAX_LANE_DEPTH, (
        "c3 at 4800 dpi is the deepest ladder the scanner of record can "
        "produce; its depth is what every lane-term bound is sized for")
    assert all(len(auto_ppc_levels(dpi, pitch_in)) - 1 <= MAX_LANE_DEPTH
               for dpi in (600, 1200, 1600, 2400, 4800)
               for pitch_in in (c2, c3))


# --------------------------------------------------- the gate, per rung (M12)

def test_the_gate_asks_the_plans_own_rung(tmp_path: Path,
                                          synthetic_print: Path) -> None:
    """``has_footing_pixels`` at the native rung IS the old raster test.

    And below it, the rung's own file is what the gate sees — absent
    while the ingest wrote none, present once one has been derived. That
    is the whole generalisation: the question moved from "this capture"
    to "this lane", and at the finest lane the answer did not move.
    """
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    config = PlacementConfig()
    try:
        # Ingest with NO directory: the rungs are not on disk.
        ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in)
        attached = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
        capture = attached.captures[0]
        coarse, native = (capture.footings[0].footing_id,
                          capture.footings[-1].footing_id)
        assert attached.has_footing_pixels(native)
        # An attached raster is as good as a rung file: the rung derives
        # from it, which is the same two-source shape the planes have.
        assert attached.has_footing_pixels(coarse)
        for footing_id in (native, coarse):
            plan = attached.window_plans(footing_id)[0]
            assert pixel_work_is_attachable(attached, plan, config=config)

        # DETACHED: no raster, no rung on disk, no prepared plane -> the
        # coarse lane has nothing to dereference, and says so.
        detached = open_plane(store, engine, ROW, ())
        assert detached.captures[0].raster is None
        assert not detached.has_footing_pixels(native)
        assert not detached.has_footing_pixels(coarse)
        coarse_plan = detached.window_plans(coarse)[0]
        assert not pixel_work_is_attachable(detached, coarse_plan,
                                            config=config)

        # Derive the coarse rung through the attached plane, then a
        # pixel-free session sees it: the file IS the second source.
        assert attached.prepared_region(
            capture.regions[0], config=config, footing_id=coarse) is not None
        revived = open_plane(store, engine, ROW, ())
        assert revived.has_footing_pixels(coarse)
        assert not revived.has_footing_pixels(native), (
            "the native rung is the scan itself; no file stands in for it")
    finally:
        store.close()

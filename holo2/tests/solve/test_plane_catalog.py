"""``open_plane``'s catalog branch: a plane over a capture with no pixels.

B9 (F-05/D5c). Two claims are under test here and they are the whole
ruling: a capture the store knows is a full member of the plane whether
or not this invocation was handed its file, and PIXEL work on a detached
one declines with a wake instead of dying on a lookup.

The third claim — an attached capture's fresh survey WINS over its
durable regions — is checked as an equality, because that is what makes
it free: ingest the file, then re-open with the same file, and the plane
is the ingested one, not a mixture.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo2.capture import attachment_key
from holo2.capture.ingest import ingest_capture
from holo2.core.commit import CommitEngine
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.core.work import (Decline, ExpansionRequest, WorkDescriptor,
                             WorkScope)
from holo2.solve.plane import open_plane
from holo2.solve import PlacementScheduler
from holo2.format.registry_rows import format_row
from conftest import registry

DPI = 600.0

#: A real row (H4 W1b): the retired toy provider took any shape, the word
#: route derives a ``TileFormat`` from the row it is given, so the fixture
#: names a coding that BUILDS.  "The registry" is gone — C2 deleted the
#: last table of names, C4 the last private bridge — so what makes this
#: real now is that the grammar constructs it (RULINGS G1/G5).
ROW = format_row("c3-k-r0550", (2, 2), 1)


@pytest.fixture
def state(tmp_path: Path, synthetic_print: Path):
    """A state directory holding one ingested capture, ready to re-open.

    The ingest is DIRECT since streaming ingestion (H4): a survey is
    scheduled work now, so the fixture commits the capture facts an
    ingest fire would propose. The plane that follows is the ATTACHED
    one — same act, same code, as the mid-run attach-by-reopen — which is
    what makes the catalog comparisons below still compare the two paths
    against each other.
    """
    from conftest import make_session

    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in)
    plane = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    yield store, engine, plane
    store.close()


def _reopen(state, scans=()):
    store, engine, _plane = state
    return open_plane(store, engine, ROW, scans)


def _geometry(plane):
    """Everything a scheduler asks a plane about, as comparable values."""
    return {
        "footings": tuple(sorted(plane.footing_ids("all"))),
        "regions": tuple(sorted(str(view.region_id)
                                for capture in plane.captures
                                for view in capture.regions)),
        "windows": tuple(sorted(
            str(plan.window_id) for footing_id in plane.footing_ids("all")
            for plan in plane.window_plans(footing_id))),
    }


def test_a_capture_with_no_file_is_still_a_member_of_the_plane(state) -> None:
    _store, _engine, ingested = state
    catalogued = _reopen(state)
    assert len(catalogued.captures) == 1
    assert catalogued.captures[0].raster is None
    assert _geometry(catalogued) == _geometry(ingested)


def test_the_catalogued_lattice_is_the_surveyed_one(state) -> None:
    _store, _engine, ingested = state
    catalogued = _reopen(state)
    for before, after in zip(ingested.captures[0].regions,
                             catalogued.captures[0].regions):
        assert after.schedulable == before.schedulable
        assert after.lattice == before.lattice
        np.testing.assert_array_equal(after.support, before.support)


def test_an_attached_capture_is_ingested_not_catalogued(
        state, synthetic_print: Path) -> None:
    """The B9 rule: the fresh survey wins, so the plane holds ONE view."""
    _store, _engine, ingested = state
    reopened = _reopen(state, ((synthetic_print, DPI),))
    assert len(reopened.captures) == 1
    assert reopened.captures[0].raster is not None
    assert _geometry(reopened) == _geometry(ingested)


def test_has_footing_and_has_region_answer_by_record(state) -> None:
    _store, _engine, _plane = state
    catalogued = _reopen(state)
    footing_id = catalogued.footing_ids("coarsest")[0]
    assert catalogued.has_footing(footing_id)
    plan = catalogued.window_plans(footing_id)[0]
    assert catalogued.has_region(plan.region_id)
    assert not catalogued.has_region(plan.window_id)   # not a region key


def test_placement_enters_no_window_of_a_detached_capture(state) -> None:
    """M12's mechanism, reached by the catalog path (B9's boundary repair).

    The decline-and-sleep this used to pin is the pull model's ADMISSION
    now: a capture whose pixels are not attached enters no window into the
    scheduling set, and it is not remembered as an exit either — the next
    refresh asks again, which is what the wake on ``attachment_key`` did.
    """
    _store, _engine, _plane = state
    catalogued = _reopen(state)
    scheduler = PlacementScheduler(ROW)
    scheduler.admit(catalogued, entry=0, selector="all")
    assert catalogued.window_plans(
        catalogued.footing_ids("coarsest")[0]), "the plane still has plans"
    assert scheduler.peek() is None
    assert scheduler.counters()["windows"] == 0


def test_surviving_prepared_planes_are_the_second_pixel_source(state) -> None:
    """2026-08-17: a detached capture whose DERIVED pixels are still there.

    Every placement fire reads the region's prepared plane and never a
    raster (§6.8/W1a), and those files sit beside the state directory, so
    a resume with no ``--scan`` is short of the SCAN, not necessarily of
    the pixels. What used to keep it from saying so was the file's NAME:
    the backing scalar in the digest was computed from the raster's own
    borders and recorded nowhere. It rides ``CaptureRecord`` now.

    So: build the plane on the attached side, re-open catalogued, and the
    same region comes back readable — and its windows enter the scheduling
    set, which is the whole point (a crash-cut resume re-earns its
    recorded placement tail from this).
    """
    from holo2.solve.place_model import PlacementConfig

    _store, _engine, attached = state
    config = PlacementConfig()
    region = attached.captures[0].regions[0]
    built = attached.prepared_region(region, config=config)
    assert built is not None, "the fixture region must prepare at all"

    catalogued = _reopen(state)
    assert catalogued.captures[0].raster is None
    reused = catalogued.prepared_region(
        catalogued.captures[0].regions[0], config=config)
    assert reused is not None, "the surviving planes were not reusable"
    assert reused.backing == built.backing
    assert (reused.y0, reused.x0, reused.aperture_px) == (
        built.y0, built.x0, built.aperture_px)
    assert bytes(np.ascontiguousarray(reused.filtered).data) == bytes(
        np.ascontiguousarray(built.filtered).data)

    scheduler = PlacementScheduler(ROW)
    scheduler.admit(catalogued, entry=0, selector="all")
    assert scheduler.counters()["windows"] > 0
    assert scheduler.peek() is not None


def test_an_attach_retires_the_reuse_doors_no(state, synthetic_print: Path,
                                              tmp_path: Path) -> None:
    """The negative memo is a memo, not a verdict.

    The gate asks per WINDOW at every refresh and the reuse-only door
    costs a SHA-256 over the whole support mask, so a "not on disk" is
    remembered. It has to die the moment the raster lands, or a capture
    attached mid-run would be permanently pixel-less — which is exactly
    the wake ``attachment_key`` promises.
    """
    from holo2.capture import catalog_captures
    from holo2.solve.place_model import PlacementConfig
    from holo2.solve.plane import SessionPlane, capture_view

    store, engine, _plane = state
    config = PlacementConfig()
    # The mid-run shape by construction: the scan is DECLARED and the
    # capture is still catalogued, which is exactly ``open_plane`` before
    # its attach walk.
    detached = SessionPlane(
        store, engine, ROW,
        tuple(capture_view(ROW, ingested, ingested.record.dpi_true)
              for ingested in catalog_captures(store)),
        ((synthetic_print, DPI),))
    region = detached.captures[0].regions[0]
    sha = detached.captures[0].source_sha256
    assert detached.prepared_region(region, config=config) is None
    assert detached._unprepared, "the no was not remembered at all"

    assert detached.attach_captures([sha])
    assert not detached._unprepared, "the no outlived the attach"
    assert detached.prepared_region(
        detached.captures[0].regions[0], config=config) is not None


def test_a_pixel_free_plane_names_its_detached_captures(state) -> None:
    """What recovery quotes when a re-earn cannot proceed."""
    _store, _engine, attached = state
    assert attached.detached_captures() == ()
    catalogued = _reopen(state)
    assert catalogued.detached_captures() == (
        catalogued.captures[0].source_sha256,)


def test_the_same_windows_enter_once_the_file_is_attached(
        state, synthetic_print: Path) -> None:
    """The other half: attaching is what makes the windows enterable."""
    _store, _engine, _plane = state
    attached = _reopen(state, ((synthetic_print, DPI),))
    scheduler = PlacementScheduler(ROW)
    scheduler.admit(attached, entry=0, selector="all")
    assert scheduler.counters()["windows"] > 0
    job = scheduler.peek()
    assert job is not None and job.entry == 0


def test_a_subject_no_plan_names_is_not_claimable(state,
                                                 synthetic_print: Path) -> None:
    """The permanent refusal, in the pull model's own terms.

    A descriptor for a window nobody planned used to be declined; a
    SUBJECT nobody planned is simply not a member of the set, so there is
    nothing to claim and no refusal to render. Same fact, one mechanism
    fewer.
    """
    _store, _engine, _plane = state
    attached = _reopen(state, ((synthetic_print, DPI),))
    scheduler = PlacementScheduler(ROW)
    scheduler.admit(attached, entry=0, selector="all")
    footing_id = attached.footing_ids("coarsest")[0]
    stranger = attached.window_plans(footing_id)[0].region_id
    assert scheduler.claim(attached, stranger) is None

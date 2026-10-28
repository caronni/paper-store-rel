"""ATTACH-BY-REOPEN: how a streamed capture reaches the plane (H4
streaming ingestion).

The committing thread's half of streaming ingestion. An ingest fire drops
the raster it opened — nothing but facts crosses the wall — so when the
capture record lands, the plane opens its own handle to the declared scan
and admits everything derived from it. Four claims, and they are the whole
of point 3 and point 4:

1. a session opens with NO captures of its own: the survey left
   ``open_plane`` when it became work;
2. a capture-record commit ATTACHES — pixels, regions, footings and the
   window plans that follow, into the maps a scheduler reads;
3. the maps are REPLACED, not edited, so a reader holding an older
   generation keeps reading a coherent one;
4. a RESUME with the file present attaches WITHOUT re-ingesting: the
   store already holds the survey, so the plane reopens and stops there.
   Without the file, the capture stays catalogued and pixel work declines
   on ``attachment_key`` (M12, unchanged).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo2.capture.ingest import capture_facts
from holo2.core.commit import CommitBatch, CommitEngine
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.solve.plane import open_plane
from holo2.format.registry_rows import format_row
from conftest import make_session, registry

DPI = 600.0
ROW = format_row("c3-k-r0550", (2, 2), 1)


@pytest.fixture
def store(tmp_path: Path):
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    yield store
    store.close()


def _land(plane, engine: CommitEngine, path: Path, dpi: float = DPI):
    """One ingest fire's proposal, through the wall and into the plane.

    The three steps the orchestrator takes around an ingest fire, with
    the fire itself replaced by its derivation: propose, commit, and tell
    the plane what moved (``SessionContext.apply``'s own two lines).
    """
    facts = capture_facts(path, dpi, ROW.pitch_in)
    result = engine.apply(CommitBatch(writes=facts.writes, blobs=facts.blobs))
    plane.invalidate(result.changed_keys)
    return facts


def test_a_session_opens_with_no_captures_of_its_own(
        store: Store, synthetic_print: Path) -> None:
    """Point 4: ``open_plane`` surveys nothing, however many scans it holds."""
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    plane = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    assert plane.captures == ()
    assert plane.scan_capture(synthetic_print, DPI) is None
    assert store.commit_seq == 0, "opening a session ingested something"


def test_a_capture_record_attaches_its_pixels_and_its_geometry(
        store: Store, synthetic_print: Path) -> None:
    """Point 3: the commit is what admits the capture, end to end."""
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    plane = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    facts = _land(plane, engine, synthetic_print)

    sha = facts.ingested.source_sha256
    assert plane.scan_capture(synthetic_print, DPI) == sha
    assert [capture.source_sha256 for capture in plane.captures] == [sha]
    raster = plane.raster(sha)
    assert raster is not None and raster.source_sha256 == sha
    # The geometry the scheduler reads, all of it derived from records
    # that arrived in this one commit.
    footings = plane.footing_ids("all")
    assert footings and all(plane.has_footing(fid) for fid in footings)
    plans = plane.window_plans(plane.footing_ids("coarsest")[0])
    assert plans and plane.has_region(plans[0].region_id)
    # And the region views are the survey's own, not a re-derivation.
    surveyed = facts.ingested.candidates[0]
    view = plane.region(plans[0].region_id)
    np.testing.assert_array_equal(view.candidate.support.cells,
                                  surveyed.support.cells)


def test_the_maps_are_replaced_so_an_older_reader_stays_coherent(
        store: Store, synthetic_print: Path) -> None:
    """Point 4's memory model: main-thread mutation, COPY-ON-WRITE.

    A generation of the derived views binds the region and footing maps
    it was built with, so what makes a fire pinned to an older generation
    safe is that an arrival never edits those maps — it replaces them.
    Asserted on the objects themselves, because that IS the mechanism: a
    reader holding the old dict must find it exactly as it was.
    """
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    plane = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    regions, footings = plane._regions, plane._footings
    captures = plane.captures
    generation = plane._derived()

    _land(plane, engine, synthetic_print)

    assert regions == {} and footings == {} and captures == ()
    assert plane._regions is not regions and plane._footings is not footings
    # The new generation is a different object, built over the new maps;
    # the committing thread's own pin died with the views it named (L11).
    assert plane._derived() is not generation
    assert plane.footing_ids("all") and plane.captures


def test_a_resume_with_the_file_attaches_without_re_ingesting(
        store: Store, synthetic_print: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Point 4's resume: the survey is durable, so it is not re-run.

    The ingest DOOR is nailed shut for the re-open, which turns "did not
    need to survey again" into "did not". The reopen door stays open —
    that is the act under test.
    """
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    first = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    facts = _land(first, engine, synthetic_print)
    seq = store.commit_seq

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a resume re-surveyed a capture it already holds")

    monkeypatch.setattr("holo2.capture.ingest.capture_facts", refuse)
    resumed = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    sha = facts.ingested.source_sha256
    assert resumed.scan_capture(synthetic_print, DPI) == sha
    assert resumed.raster(sha) is not None
    assert store.commit_seq == seq, "an attach committed something"
    assert [str(plan.window_id)
            for plan in resumed.window_plans(resumed.footing_ids("all")[0])]


def test_a_resume_without_the_file_keeps_the_capture_but_not_its_pixels(
        store: Store, synthetic_print: Path) -> None:
    """M12, unchanged: attach-by-reopen only where the scan is present."""
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    first = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    facts = _land(first, engine, synthetic_print)

    resumed = open_plane(store, engine, ROW, ())
    sha = facts.ingested.source_sha256
    assert [capture.source_sha256 for capture in resumed.captures] == [sha]
    assert resumed.raster(sha) is None
    assert resumed.scan_capture(synthetic_print, DPI) is None
    assert resumed.has_footing(resumed.footing_ids("all")[0])

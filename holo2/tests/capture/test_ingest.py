"""Ingest: one acquisition becomes durable capture facts.

R2 split ``engine/runtime.py``; these are the assertions of its test that
are about this package — what the records say after one capture is
authenticated, surveyed and committed, and how a footing ladder is named.
The lattice and window assertions moved to ``solve``, the lineage ones to
``engine``.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo2.capture.ingest import (footing_id_for, ingest_capture,
                                  platen_backing)
from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, CommitRefusal, Write
from holo2.capture import (CaptureRecord, RegionRecord, SupportMask,
                           capture_key, region_key)
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from conftest import make_region, registry

DPI = 600.0
#: The printed pitch these fixtures are written at: c3, an
#: exact 1/200 in (C3, RULINGS G4 — it was the dot count 3).
PITCH_IN = Fraction(1, 200)


@pytest.fixture
def ingest(tmp_path: Path, synthetic_print: Path):
    """One ingested capture plus the store and engine that hold its facts."""
    from conftest import make_session

    store = Store.open_or_create(tmp_path / "state",
                                 make_session(), registry(),
                                 fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    capture = ingest_capture(engine, synthetic_print, DPI, PITCH_IN)
    yield store, engine, capture
    store.close()


def _key_of(candidate):
    """A region IS its capture and its support grid (the identity law)."""
    return region_key(candidate.capture_sha256, candidate.support.origin_yx,
                      candidate.support.step_px, candidate.support.extent_px)


def test_ingest_writes_the_physical_plane(ingest) -> None:
    store, _engine, capture = ingest
    assert store.get(capture_key(capture.source_sha256)) is not None
    assert capture.candidates, "the survey found no region on a printed page"
    for candidate in capture.candidates:
        record = store.get(_key_of(candidate))
        assert isinstance(record, RegionRecord)
        np.testing.assert_array_equal(
            store.read_array(record.support_mask_ref), candidate.support.cells)


def test_the_region_record_alone_places_its_lattice(ingest) -> None:
    """OR-12, closed: durable state needs no re-survey to KNOW the geometry.

    The support mask plus the three grid fields rebuild the survey's own
    ``SupportMask`` exactly — which is the object the cell lattice is laid
    out over — so a resumed session can place a region from the store.
    """
    store, _engine, capture = ingest
    for candidate in capture.candidates:
        record = store.get(_key_of(candidate))
        assert record.capture_sha256 == capture.source_sha256
        rebuilt = SupportMask(
            origin_yx=record.support_origin_px,
            step_px=record.support_step_px,
            cells=store.read_array(record.support_mask_ref),
            extent_px=record.support_extent_px)
        np.testing.assert_array_equal(rebuilt.cells, candidate.support.cells)
        assert rebuilt.bbox == candidate.support.bbox


def test_footings_are_a_ppc_ascending_ladder(ingest) -> None:
    _store, _engine, capture = ingest
    ppcs = [footing.ppc for footing in capture.footings]
    assert ppcs == sorted(ppcs) and len(set(ppcs)) == len(ppcs)
    assert ppcs[0] == Fraction(2) and ppcs[-1] == Fraction(3)
    for footing in capture.footings:
        assert footing.footing_id == footing_id_for(
            capture.source_sha256, footing.ppc)


def test_re_ingesting_the_same_capture_commits_nothing(ingest,
                                                       synthetic_print) -> None:
    """Capture facts are content-addressed: a second pass is a no-op (L10)."""
    store, engine, _capture = ingest
    seq = store.commit_seq
    ingest_capture(engine, synthetic_print, DPI, PITCH_IN)
    assert store.commit_seq == seq


def test_re_ingesting_at_a_corrected_dpi_is_refused(ingest,
                                                    synthetic_print) -> None:
    """Q2, in its "reject the conflict" form.

    ``source_sha256`` is the identity, but the declared DPI is what names
    every footing (ppc = dpi*c/600) and therefore every evidence key that
    cites one. Silently reinterpreting the old evidence is the option §15
    forbids, so the second interpretation refuses by name.
    """
    store, engine, _capture = ingest
    seq = store.commit_seq
    with pytest.raises(CommitRefusal, match="dpi_true"):
        ingest_capture(engine, synthetic_print, DPI * 2, PITCH_IN)
    assert store.commit_seq == seq, "a refused ingest commits nothing"


def test_the_record_carries_the_raster_s_own_backing(ingest) -> None:
    """The scalar ``solve.prepared`` names its files by is a capture FACT.

    Recorded here because a session without the file cannot compute it —
    and therefore could not name the prepared planes it already has. That
    this transcription is BIT-EQUAL to ``pose_fit``'s carried arithmetic
    is pinned on the ``solve`` side, where the DAG allows both imports
    (``tests/solve/test_pose_fit.py``).
    """
    _store, _engine, capture = ingest
    assert capture.raster is not None
    assert (capture.record.platen_backing
            == platen_backing(capture.raster))
    assert np.isfinite(capture.record.platen_backing)


def test_the_capture_record_mirrors_the_source_id_checks() -> None:
    """The validator also runs on the LOAD path, which is where it matters.

    ``store`` decodes an envelope straight into this constructor, so a
    state carrying a nonfinite ``dpi_true`` or a degenerate shape has to
    refuse at open instead of placing a lattice from it.
    """
    good = dict(source_sha256="ab" * 32, dpi_true=600.0, shape_px=(10, 20),
                dtype="|u1", channels=1, platen_backing=200.0, footings=())
    CaptureRecord(**good)
    CaptureRecord(**{**good, "platen_backing": 0.0})   # a black border is legal
    for bad in ({"source_sha256": "AB" * 32}, {"source_sha256": "ab" * 30},
                {"dpi_true": float("inf")}, {"dpi_true": 0.0},
                {"dtype": "not-a-dtype"}, {"shape_px": (0, 20)},
                {"channels": 2}, {"platen_backing": float("nan")},
                {"platen_backing": float("inf")}):
        with pytest.raises(ValueError):
            CaptureRecord(**{**good, **bad})


def test_region_record_carries_a_declined_pitch_vote(ingest) -> None:
    """The §5.3 widening: the survey may legally decline to vote (L4)."""
    store, engine, capture = ingest
    blob = stage_array(np.zeros(4, np.uint8))
    # On the INGESTED capture: since F-07's relational half a region
    # names the acquisition it was surveyed from, and that record has to
    # be a fact already (it is — the fixture ingested it).
    record = make_region(blob.ref, None, support_origin_px=(8, 8),
                         capture_sha256=capture.record.source_sha256)
    engine.apply(CommitBatch(blobs=(blob,), writes=(
        Write(record.resource_key(), record),)))
    assert b'"pitch_in_vote":null' in store.state_bytes()

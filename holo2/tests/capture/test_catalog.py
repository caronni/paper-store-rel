"""Catalog: the same capture facts, rebuilt from the store without pixels.

B9 (F-05/D5c). The bar is agreement, not approximation — a catalogued
capture must be the ingested one minus its raster, byte-for-byte on the
support mask and value-for-value on everything derived from it, because
that is what makes "an attached capture's fresh survey wins" a free rule
rather than a reconciliation problem.
"""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path

import numpy as np
import pytest

from holo2.capture import (CaptureRecord, RegionRecord, capture_key,
                           catalog_capture, catalog_captures,
                           region_from_record, region_key)
from holo2.capture.ingest import ingest_capture
from holo2.core.blobs import stage_array
from holo2.core.commit import (CommitBatch, CommitEngine, CommitRefusal,
                               Write)
from holo2.core.cache import CACHE_NAME
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from conftest import registry

DPI = 600.0
#: The printed pitch these fixtures are written at: c3, an
#: exact 1/200 in (C3, RULINGS G4 — it was the dot count 3).
PITCH_IN = Fraction(1, 200)


@pytest.fixture
def ingest(tmp_path: Path, synthetic_print: Path):
    from conftest import make_session

    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    capture = ingest_capture(engine, synthetic_print, DPI, PITCH_IN)
    yield store, engine, capture
    store.close()


def test_a_catalogued_capture_is_the_ingested_one_without_its_raster(
        ingest) -> None:
    store, _engine, ingested = ingest
    catalogued = catalog_captures(store)
    assert len(catalogued) == 1
    only = catalogued[0]
    assert only.raster is None
    assert only.record == ingested.record
    assert only.footings == ingested.footings
    assert len(only.candidates) == len(ingested.candidates)
    for rebuilt, surveyed in zip(only.candidates, ingested.candidates):
        # Field by field: a dataclass holding a numpy array has no usable
        # ``==``, and the mask is the field that must be byte-exact.
        np.testing.assert_array_equal(rebuilt.support.cells,
                                      surveyed.support.cells)
        assert (rebuilt.capture_sha256, rebuilt.pitch_in_vote, rebuilt.bbox_px,
                rebuilt.area_mm2, rebuilt.support.origin_yx,
                rebuilt.support.step_px, rebuilt.support.extent_px) == (
            surveyed.capture_sha256, surveyed.pitch_in_vote, surveyed.bbox_px,
            surveyed.area_mm2, surveyed.support.origin_yx,
            surveyed.support.step_px, surveyed.support.extent_px), (
            "the catalog is not a second opinion")


def test_a_footing_names_its_own_capture(ingest) -> None:
    """B9's collapse: the lane answers "whose am I?" off the record."""
    _store, _engine, ingested = ingest
    for footing in ingested.record.footings:
        assert footing.capture_sha256 == ingested.source_sha256


def test_a_footing_of_another_capture_is_refused() -> None:
    with pytest.raises(ValueError, match="lane belongs to ONE"):
        CaptureRecord(source_sha256="ab" * 32, dpi_true=600.0,
                      shape_px=(10, 10), dtype="|u1", channels=1,
                      platen_backing=200.0, footings=(_spec("cd" * 32),))


def _spec(capture_sha256: str):
    from holo2.capture import FootingSpec

    return FootingSpec("cap:2/1", Fraction(2), capture_sha256)


def test_region_from_record_rebuilds_the_survey_geometry(ingest) -> None:
    store, _engine, ingested = ingest
    for candidate in ingested.candidates:
        record = store.get(region_key(
            candidate.capture_sha256, candidate.support.origin_yx,
            candidate.support.step_px, candidate.support.extent_px))
        assert isinstance(record, RegionRecord)
        rebuilt = region_from_record(
            record, store.read_array(record.support_mask_ref), DPI)
        assert rebuilt.bbox_px == candidate.bbox_px
        assert rebuilt.area_mm2 == candidate.area_mm2
        assert rebuilt.pitch_in_vote == candidate.pitch_in_vote


def test_an_attached_capture_is_not_catalogued_beside_itself(ingest) -> None:
    """The fresh survey wins: ingest owns the captures it was handed."""
    store, _engine, ingested = ingest
    assert catalog_captures(store, attached=[ingested.source_sha256]) == ()


def test_a_region_offered_to_the_wrong_capture_is_refused(ingest) -> None:
    _store, _engine, ingested = ingest
    other = CaptureRecord(source_sha256="cd" * 32, dpi_true=600.0,
                          shape_px=(10, 10), dtype="|u1", channels=1,
                          platen_backing=200.0, footings=())
    with pytest.raises(ValueError, match="offered to capture"):
        catalog_capture(other, ingested.candidates)


def test_an_orphan_region_cannot_be_committed_at_all(ingest) -> None:
    """F-07's relational half: the wall is where an orphan is stopped.

    A region names its capture, so a region whose capture nobody
    committed refuses AT THE WALL — the state the catalog used to have
    to defend against is now unreachable through the commit path.
    """
    _store, engine, _ingested = ingest
    blob = stage_array(np.ones((2, 2), bool))
    orphan = RegionRecord(capture_sha256="cd" * 32,
                          support_mask_ref=blob.ref,
                          pitch_in_vote=Fraction(1, 200),
                          support_origin_px=(0, 0),
                          support_step_px=4, support_extent_px=(8, 8))
    with pytest.raises(CommitRefusal, match="no committed record stands at"):
        engine.apply(CommitBatch(
            blobs=(blob,), writes=(Write(orphan.resource_key(), orphan),)))


def test_an_orphan_region_is_refused_not_skipped(ingest, tmp_path: Path) -> None:
    """A region with no capture record is a corrupt state, not a gap (L4).

    The wall (above) is why no run produces one; validation happens at
    the commit wall ONLY — since F-16 rider r1, that is literally the only
    place it happens — so a state that arrives corrupt some other way (a
    hand-edited cache, here) still meets the catalog's own refusal instead
    of being silently skipped.
    """
    store, _engine, ingested = ingest
    store.close()

    def reparent(frame: dict) -> None:
        """Re-parent every region onto a capture nobody ingested.

        Key and record together, so the pair still agrees and the state
        LOADS — an orphan is what the catalog must catch, not a mismatch.
        """
        for entry in frame.get("records", ()):
            if entry[2] != "RegionRecord":
                continue
            entry[3]["capture_sha256"] = "cd" * 32
            interned = entry[0]
            frame["keys"] = [
                [ident, parts if ident != interned
                 else [parts[0], "cd" * 32, *parts[2:]]]
                for ident, parts in frame.get("keys", ())]

    _rewrite_cache(store.state_dir / CACHE_NAME, reparent)
    with Store.open(store.state_dir, registry()) as corrupt:
        with pytest.raises(ValueError, match="holds no record of"):
            catalog_captures(corrupt)


def test_the_catalog_reads_the_declared_dpi_off_the_record(ingest) -> None:
    """The lattice pitch hangs off the capture's dpi, so it must be durable."""
    store, _engine, ingested = ingest
    record = store.get(capture_key(ingested.source_sha256))
    assert isinstance(record, CaptureRecord)
    assert record.dpi_true == DPI
    assert catalog_captures(store)[0].record.dpi_true == DPI


def _rewrite_cache(path: Path, mutate) -> None:
    """Edit a delta-frame cache in place: parse, mutate, re-encode.

    The cache is length-prefixed canonical JSON frames (``core.cache``),
    so hand-editing a state is a frame walk rather than one JSON load —
    the price of never rewriting a 476 MB envelope.
    """
    raw = path.read_bytes()
    frames, offset = [], 0
    while offset < len(raw):
        length = int.from_bytes(raw[offset:offset + 8], "big")
        frames.append(json.loads(raw[offset + 8:offset + 8 + length]))
        offset += 8 + length
    out = bytearray()
    for frame in frames:
        if "pos" in frame:
            mutate(frame)
        payload = json.dumps(frame, sort_keys=True,
                             separators=(",", ":")).encode()
        out += len(payload).to_bytes(8, "big") + payload
    path.write_bytes(bytes(out))

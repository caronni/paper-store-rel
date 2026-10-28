"""The ingest FRONTIER: declared scans, one descriptor at a time (H4
streaming ingestion).

Points 1 and 2 of streaming ingestion, which together are the whole
scheduling design and the reason no gate mechanism was needed:

* the provider closes over the DECLARED scans (session inputs) and
  derives "not yet ingested" against durable capture records, resolved
  through the plane — the only object that can join a declaration to an
  acquisition, because joining means opening the file;
* it mints the HEAD and nothing else, so scan N+1 becomes expandable only
  once scan N's capture record stands. That is what caps the survey's
  ~8x-raster transient at one in flight whatever the pool width, and what
  makes ingest order deterministic in both lanes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo2.capture import (FAMILY_INGEST, OUTCOME_INGESTED, ROUTE_SURVEY,
                          IngestWorker, scan_key)
from holo2.capture.ingest import capture_facts
from holo2.core.commit import CommitBatch, CommitEngine, SpendProposal
from holo2.core.store import Store
from holo2.core.work import Decline, ExpansionRequest, WorkDescriptor
from holo2.core.trace import TraceWriter
from holo2.solve import RealIngestProvider
from holo2.solve.plane import open_plane
from holo2.format.registry_rows import format_row
from conftest import make_session, registry

DPI = 600.0
ROW = format_row("c3-k-r0550", (2, 2), 1)
REQUEST = ExpansionRequest(entry="ingest/all/always")


@pytest.fixture
def second_print(tmp_path: Path) -> Path:
    """A DIFFERENT acquisition: same shape of page, different bytes.

    Two declared scans of identical bytes are one acquisition (L1), so a
    frontier test needs two real ones.
    """
    from PIL import Image

    rng = np.random.default_rng(20260817)
    cells = rng.random((128, 128)) < 0.5
    field = np.kron(cells, np.ones((3, 3), bool))
    page = np.full((600, 600), 235, np.uint8)
    page[100:100 + field.shape[0], 120:120 + field.shape[1]] = np.where(
        field, 30, 235)
    path = tmp_path / "second.png"
    Image.fromarray(page).save(path)
    return path


@pytest.fixture
def duplicate_print(synthetic_print: Path, tmp_path: Path) -> Path:
    """A SECOND declared path, byte-for-byte IDENTICAL to ``synthetic_print``.

    The duplicate-scan fix's own scenario (2026-08-17 ruling): two
    declared scans of the same bytes are one acquisition (L1), so this
    fixture is a second NAME for the first fixture's bytes, not a second
    acquisition.
    """
    import shutil
    path = tmp_path / "duplicate.png"
    shutil.copyfile(synthetic_print, path)
    return path


@pytest.fixture
def triple_session(tmp_path: Path, synthetic_print: Path,
                   duplicate_print: Path, second_print: Path):
    """Three declared scans; the middle one duplicates the first."""
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    scans = ((synthetic_print, DPI), (duplicate_print, DPI),
             (second_print, DPI))
    plane = open_plane(store, engine, ROW, scans)
    yield plane, engine, scans
    store.close()


@pytest.fixture
def session(tmp_path: Path, synthetic_print: Path, second_print: Path):
    """A plane over two declared scans, and the authority behind it."""
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    scans = ((synthetic_print, DPI), (second_print, DPI))
    plane = open_plane(store, engine, ROW, scans)
    yield plane, engine, scans
    store.close()


def _land(plane, engine: CommitEngine, path: Path) -> None:
    """One ingest fire's proposal, through the wall and into the plane."""
    facts = capture_facts(path, DPI, ROW.pitch_in)
    result = engine.apply(CommitBatch(writes=facts.writes, blobs=facts.blobs))
    plane.invalidate(result.changed_keys)


def _land_ingest(plane, engine: CommitEngine, path: Path) -> None:
    """One ingest fire, WITH its spend — the real ``SessionContext.apply``
    shape (``engine/session.py``), needed here because the duplicate-scan
    fix rides off the spend precisely where the write is a no-op (L10)
    and ``_land`` above never builds one.
    """
    facts = capture_facts(path, DPI, ROW.pitch_in)
    work_id = WorkDescriptor(family=FAMILY_INGEST,
                             subject=scan_key(path, DPI),
                             route=ROUTE_SURVEY).work_id
    spend = SpendProposal(work_id, ROUTE_SURVEY, engine.attempt_identity(()),
                          OUTCOME_INGESTED)
    result = engine.apply(CommitBatch(writes=facts.writes, spends=(spend,),
                                      blobs=facts.blobs))
    plane.invalidate(result.changed_keys, spent=(spend.worker_id,))


def _expand(provider: RealIngestProvider, plane) -> tuple[WorkDescriptor, ...]:
    return tuple(provider.expand(plane, REQUEST))


def test_the_head_scan_is_the_only_descriptor(session) -> None:
    plane, _engine, scans = session
    provider = RealIngestProvider(ROW, scans)
    (descriptor,) = _expand(provider, plane)
    assert descriptor.family == FAMILY_INGEST
    assert descriptor.route == ROUTE_SURVEY
    assert descriptor.subject == scan_key(*scans[0])
    # Expansion is total and stateless: asking twice asks the same
    # durable question and gets the same answer.
    assert _expand(provider, plane) == (descriptor,)


def test_scan_two_exists_only_once_scan_one_stands(session) -> None:
    """Point 2's derivation chain, which IS the RAM cap."""
    plane, engine, scans = session
    provider = RealIngestProvider(ROW, scans)
    _land(plane, engine, scans[0][0])
    (descriptor,) = _expand(provider, plane)
    assert descriptor.subject == scan_key(*scans[1])
    _land(plane, engine, scans[1][0])
    assert _expand(provider, plane) == (), "a third attempt was minted"
    assert len(plane.captures) == 2


def test_a_resumed_session_re_ingests_nothing(session, tmp_path: Path,
                                              monkeypatch) -> None:
    """Point 4: the store already answers, so the frontier is empty.

    The derivation alone closes this — the spend ledger is the second
    belt, for a state whose capture record stands under a work id this
    composition never resolved.
    """
    plane, engine, scans = session
    _land(plane, engine, scans[0][0])
    _land(plane, engine, scans[1][0])

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a resume re-surveyed a standing capture")

    monkeypatch.setattr("holo2.capture.ingest.capture_facts", refuse)
    resumed = open_plane(engine.store, engine, ROW, scans)
    provider = RealIngestProvider(ROW, scans)
    assert _expand(provider, resumed) == ()
    assert len(resumed.captures) == 2
    assert all(capture.raster is not None for capture in resumed.captures)


def test_the_worker_is_bound_from_the_declared_list(session) -> None:
    plane, _engine, scans = session
    provider = RealIngestProvider(ROW, scans)
    (descriptor,) = _expand(provider, plane)
    worker = provider.worker(plane, descriptor)
    assert isinstance(worker, IngestWorker)
    assert (worker.path, worker.dpi) == scans[0]
    assert worker.pitch_in == ROW.pitch_in


def test_a_subject_this_session_never_declared_is_declined(session) -> None:
    """A descriptor naming a foreign scan is not this composition's work."""
    plane, _engine, scans = session
    provider = RealIngestProvider(ROW, scans[:1])
    declined = provider.worker(
        plane, WorkDescriptor(family=FAMILY_INGEST,
                              subject=scan_key(*scans[1]),
                              route=ROUTE_SURVEY))
    assert isinstance(declined, Decline)
    assert declined.permanent, "a scan nobody declared cannot become declared"


def test_a_scan_is_named_by_its_declaration(tmp_path: Path,
                                            synthetic_print: Path) -> None:
    """Identity = the scan: the resolved path and the declared DPI.

    Both halves matter and the key says so — a corrected DPI is a
    different acquisition interpretation (Q2), and a relative spelling of
    one path is the same declaration.
    """
    relative = Path(synthetic_print.name)
    assert scan_key(synthetic_print, DPI) != scan_key(synthetic_print, DPI * 2)
    assert scan_key(synthetic_print, DPI) == scan_key(
        synthetic_print.resolve(), DPI)
    assert scan_key(relative, DPI) != scan_key(synthetic_print, DPI)


# -- the duplicate-scan fix (2026-08-17 user ruling) ------------------------
#
# "same sha: drop the effort, never ingest / process, proceed with the
# list of pending ingestions." A mid-list duplicate's ingest fire commits
# a spend but no capture key (an L10 no-op write), so the plane resolves
# it off the SPEND instead (``SessionPlane._resolve_duplicate_scans``).


def test_a_mid_list_duplicate_does_not_stall_the_chain(
        triple_session, capsys: pytest.CaptureFixture) -> None:
    """The stall this fix closes: without it, scan 3 is never even minted.

    Scan 2 duplicates scan 1's bytes. Landing scan 2's ingest fire commits
    only a spend (its capture write is a no-op) — the frontier must still
    advance to scan 3, and scan 2 must resolve to scan 1's acquisition.
    """
    plane, engine, scans = triple_session
    provider = RealIngestProvider(ROW, scans)

    (descriptor,) = _expand(provider, plane)
    assert descriptor.subject == scan_key(*scans[0])
    _land_ingest(plane, engine, scans[0][0])
    sha_a = plane.scan_capture(*scans[0])
    assert sha_a is not None

    (descriptor,) = _expand(provider, plane)
    assert descriptor.subject == scan_key(*scans[1]), (
        "the duplicate was never offered its own ingest attempt")
    capsys.readouterr()
    _land_ingest(plane, engine, scans[1][0])
    out = capsys.readouterr()
    assert out.err.count("\n") == 1, f"expected one warning line, got: {out.err!r}"
    assert str(scans[0][0]) in out.err and str(scans[1][0]) in out.err

    # Resolved via the SAME memo the ordinary path fills — honest,
    # because scan 2's bytes ARE scan 1's acquisition — and no new
    # capture record was minted for it.
    assert plane.scan_capture(*scans[1]) == sha_a
    assert len(plane.captures) == 1

    # The chain proceeds past the duplicate: scan 3 is offered next, not
    # scan 2 again, and its own ingest fire lands a NEW capture record.
    (descriptor,) = _expand(provider, plane)
    assert descriptor.subject == scan_key(*scans[2]), (
        "the derivation chain stalled on the duplicate")
    _land_ingest(plane, engine, scans[2][0])

    assert _expand(provider, plane) == ()
    assert len(plane.captures) == 2, "the duplicate must not add a capture"
    assert plane.scan_capture(*scans[2]) is not None


def test_no_duplicates_emits_no_warning(
        session, capsys: pytest.CaptureFixture) -> None:
    """The control: two genuinely different scans, zero ceremony."""
    plane, engine, scans = session
    capsys.readouterr()
    _land_ingest(plane, engine, scans[0][0])
    _land_ingest(plane, engine, scans[1][0])
    out = capsys.readouterr()
    assert out.err == ""
    assert len(plane.captures) == 2

"""The ingest FIRE: one declared scan, proposed and not committed (H4
streaming ingestion).

Streaming ingestion made reading an acquisition into work. What this file
pins is the half that had to become a worker — derive, propose, hold
nothing — and the three properties the scheduling design rests on:

1. **it commits nothing.** The fire returns writes and staged blobs; the
   store it was fired against is untouched until somebody applies them.
2. **it holds no session state, and reads none.** ``read_keys`` is empty
   and ``run`` never touches the view — pinned by firing it against
   ``None``, which is the only way to state "reads nothing" as a fact
   rather than as a hope.
3. **the empty read-set is the resume mechanism.** An attempt identity
   over no keys is the same value in every run, so the spend row one run
   leaves under a scan's work id is exactly what a later run's spend-once
   test compares against.

What it PROPOSES is the same durable content the direct path commits
(``ingest_capture``), because both compose one derivation — asserted
against a second store rather than by reading the code.
"""
from __future__ import annotations

from fractions import Fraction

from pathlib import Path

import pytest

from holo2.capture import FAMILY_INGEST, OUTCOME_INGESTED, IngestWorker
from holo2.capture.ingest import capture_facts, ingest_capture
from holo2.core.commit import CommitBatch, CommitEngine
from holo2.core.identity import attempt_identity
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.core.work import ProgressSink, check_progress
from conftest import make_session, registry

DPI = 600.0
#: The printed pitch these fixtures are written at: c3, an
#: exact 1/200 in (C3, RULINGS G4 — it was the dot count 3).
PITCH_IN = Fraction(1, 200)


def _engine(tmp_path: Path, name: str) -> CommitEngine:
    store = Store.open_or_create(tmp_path / name, make_session(), registry(),
                                 fsync=False)
    return CommitEngine(store, trace=TraceWriter(store.trace_path))


@pytest.fixture
def fired(tmp_path: Path, synthetic_print: Path):
    """One ingest fire, run to a proposal against an untouched store."""
    engine = _engine(tmp_path, "proposed")
    worker = IngestWorker(synthetic_print, DPI, PITCH_IN)
    progress = ProgressSink(str(FAMILY_INGEST))
    # THE VIEW IS ``None``: a fire that reads no session state can be
    # fired without one, and that is the pin — not a comment.
    result = worker.run(None, (), progress)
    check_progress("ingest", result, progress)
    yield engine, worker, result, progress
    engine.store.close()


def test_the_fire_proposes_and_commits_nothing(fired) -> None:
    engine, _worker, result, _progress = fired
    assert engine.store.commit_seq == 0, "an ingest fire committed by itself"
    assert result.outcome == OUTCOME_INGESTED
    assert result.retire, "one scan is read once; the descriptor is spent"
    assert result.writes and result.blobs, "a surveyed page has regions"
    assert not engine.store.keys()


def test_the_proposal_is_what_the_direct_path_commits(
        fired, tmp_path: Path, synthetic_print: Path) -> None:
    """Two composers of ONE derivation, asserted against each other."""
    engine, _worker, result, _progress = fired
    engine.apply(CommitBatch(writes=result.writes, blobs=result.blobs))

    direct = _engine(tmp_path, "direct")
    ingest_capture(direct, synthetic_print, DPI, PITCH_IN)
    try:
        assert engine.store.keys() == direct.store.keys()
        for key in direct.store.keys():
            assert engine.store.get(key) == direct.store.get(key)
    finally:
        direct.store.close()


def test_the_read_set_is_empty_and_its_identity_is_constant(fired) -> None:
    """Point 2's resume mechanism, as the value the ledger compares.

    An ingest attempt reads no durable fact — its inputs are the declared
    path and DPI — so the identity it spends under is the empty one in
    every run of every lineage. That is what makes "this scan has already
    been read" a durable statement rather than a version race.
    """
    _engine_, worker, _result, _progress = fired
    assert worker.read_keys(None) == ()
    assert attempt_identity((), {}) == attempt_identity((), {"a": 1})


def test_the_fire_reports_bounded_quanta(fired) -> None:
    """§10.3: no leaf runs dark, and no quantum exceeds the bound."""
    _engine_, _worker, _result, progress = fired
    assert progress.count >= 2
    assert progress.units == progress.count, "one unit per boundary"


def test_the_derivation_authenticates_what_it_proposes(
        tmp_path: Path, synthetic_print: Path) -> None:
    """The capture record is about the BYTES, not about the declaration."""
    facts = capture_facts(synthetic_print, DPI, PITCH_IN)
    record = facts.ingested.record
    assert facts.writes[0].record is record
    assert record.dpi_true == DPI
    assert record.source_sha256 == facts.ingested.raster.source_sha256
    assert all(write.record.capture_sha256 == record.source_sha256
               for write in facts.writes[1:])
    assert len(facts.blobs) == len(facts.writes) - 1

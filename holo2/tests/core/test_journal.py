"""The journal: the fold's starting point, its order, and replay from it.

The gate property the trace used to hold, now against the file that
records the ordering: **replaying a recorded ordering over the same
proposals reproduces the durable state**. That is also what makes crash
recovery and the ``--replay`` audit one mechanism (F-24, subsumed by
F-16) — auditing a state directory IS re-folding its journal and
comparing batch ids.

``replay`` itself lives here as this test's straight-line instrument.
Production replay is the orchestrator's — it holds a cursor, re-proposes
and verifies each entry against the recorded ordering
(``engine/replay.py``) — so shipping a second one in the library would
advertise a mechanism nothing uses.

TWO ENTRY SHAPES SINCE H4 W2 (``schema_version`` 7): a commit id, and a
payload-free START MARKER naming one dispatched pass. What the marker
MEANS is the engine's (``tests/engine/test_replay.py``); what is pinned
here is the file: both shapes read back, an unparseable one refuses, and
the tail law is about ORDER and so covers both.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from holo2.core.commit import (CommitBatch, CommitEngine, CommitResult,
                               batch_id)
from holo2.core import WorkId, WorkScope
from holo2.core.journal import (JOURNAL_NAME, Journal, JournalError,
                                ReplayError, commit_count, is_marker,
                                marker_work_id, position_after_commits,
                                read_journal, start_marker)
from holo2.core.store import SCHEMA_VERSION, Store
from conftest import make_session, registry, tile_key
from test_trace import toy_workload


def replay(engine: CommitEngine, ordering: Sequence[str],
           proposals: Mapping[str, CommitBatch]) -> tuple[CommitResult, ...]:
    """Apply ``proposals`` in a recorded ordering (§10.3 replay mode)."""
    results: list[CommitResult] = []
    for position, identifier in enumerate(ordering):
        batch = proposals.get(identifier)
        if batch is None:
            raise ReplayError(
                f"ordering position {position}: no proposal for batch "
                f"{identifier}")
        proposed_id = batch_id(batch)
        if proposed_id != identifier:
            raise ReplayError(
                f"ordering position {position}: proposal identifies as "
                f"{proposed_id}, not {identifier}")
        results.append(engine.apply(batch))
    return tuple(results)


def _record_run(state_dir: Path) -> tuple[bytes, tuple[CommitBatch, ...]]:
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        batches = toy_workload(store)
        for batch in batches:
            engine.apply(batch)
        return store.state_bytes(), batches


def test_replay_of_a_recorded_ordering_reproduces_the_state(
        tmp_path: Path) -> None:
    recorded_dir = tmp_path / "recorded"
    state, batches = _record_run(recorded_dir)
    _header, ordering = read_journal(recorded_dir / JOURNAL_NAME)
    assert len(ordering) == len(batches)

    replay_dir = tmp_path / "replayed"
    with Store.create(replay_dir, make_session(), registry()) as store:
        engine = CommitEngine(store)
        proposals = {batch_id(batch): batch for batch in toy_workload(store)}
        results = replay(engine, ordering, proposals)
        assert [result.batch_id for result in results] == list(ordering)
        assert store.state_bytes() == state
    # The replayed journal IS the recorded one: same starting point, same
    # order. That equality is what "audit = re-fold and compare" means.
    assert ((replay_dir / JOURNAL_NAME).read_bytes()
            == (recorded_dir / JOURNAL_NAME).read_bytes())


def test_replay_refuses_a_missing_proposal(tmp_path: Path) -> None:
    recorded_dir = tmp_path / "recorded"
    _record_run(recorded_dir)
    _header, ordering = read_journal(recorded_dir / JOURNAL_NAME)
    with Store.create(tmp_path / "replayed", make_session(), registry()) as store:
        engine = CommitEngine(store)
        with pytest.raises(ReplayError, match="no proposal"):
            replay(engine, ordering, {})


def test_a_start_marker_round_trips_through_the_file(tmp_path: Path) -> None:
    """The second entry shape: written, read back, and named exactly.

    A ``WorkId`` is a STRUCTURE — family, subject key, route, scope — so
    the marker carries its canonical JSON and not the lossy ``__str__``
    a replay could not resolve back to a worker.
    """
    work_id = WorkId("payload", tile_key(0, 3, 4, "K"), "scan",
                     WorkScope(arm="a1", profile="p2"))
    journal = Journal.create(tmp_path / JOURNAL_NAME, {"magic": "x"},
                             fsync=False)
    journal.append(start_marker(work_id), 0)
    journal.append("a" * 64, 1)
    journal.close()

    _header, ordering = read_journal(tmp_path / JOURNAL_NAME)
    assert [is_marker(entry) for entry in ordering] == [True, False]
    assert marker_work_id(ordering[0]) == work_id
    assert commit_count(ordering) == 1
    assert position_after_commits(ordering, 0) == 0
    assert position_after_commits(ordering, 1) == 2


def test_an_unreadable_marker_refuses_like_a_bad_id(tmp_path: Path) -> None:
    journal = Journal.create(tmp_path / JOURNAL_NAME, {"magic": "x"},
                             fsync=False)
    journal.close()
    with open(tmp_path / JOURNAL_NAME, "ab") as handle:
        handle.write(b'>["payload"]\n')            # a WorkId needs four parts
    with pytest.raises(JournalError, match="unreadable start marker"):
        read_journal(tmp_path / JOURNAL_NAME)


def test_the_tail_law_covers_markers_too(tmp_path: Path) -> None:
    """The record is never rewritten — whatever KIND of entry stands there.

    Both shapes take one append path, because the law is about order.
    """
    marker = start_marker(WorkId("payload", tile_key(0, 3, 4, "K"), "scan"))
    journal = Journal.create(tmp_path / JOURNAL_NAME, {"magic": "x"},
                             fsync=False)
    journal.append(marker, 0)
    journal.append("a" * 64, 1)
    journal.append(marker, 0)            # re-earned: the record stands
    with pytest.raises(JournalError, match="cannot reproduce the recorded"):
        journal.append("b" * 64, 0)      # a commit where a dispatch stands
    assert len(journal) == 2
    journal.close()


def test_the_starting_point_is_line_one_and_the_rest_are_batch_ids(
        tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _record_run(state_dir)
    lines = (state_dir / JOURNAL_NAME).read_bytes().split(b"\n")
    assert lines[-1] == b""                       # newline-terminated
    header = json.loads(lines[0])
    assert header["schema_version"] == SCHEMA_VERSION
    assert header["magic"] == "holo2-journal"
    # The identity is carried BY VALUE, format row id included — core does
    # not name that field, the session record binds it.
    assert header["session"]["format_row_id"] == make_session().format_row_id
    for line in lines[1:-1]:
        assert len(line) == 64 and int(line, 16) >= 0
    # Hundreds of KB a sheet is the target, and this is why: 65 bytes a
    # commit, and nothing else in the file.
    assert len(lines[1]) + 1 == 65


def test_a_torn_journal_tail_is_dropped(tmp_path: Path) -> None:
    """A crash between the write and the fsync: that commit never was."""
    state_dir = tmp_path / "state"
    _record_run(state_dir)
    with open(state_dir / JOURNAL_NAME, "ab") as handle:
        handle.write(b"0123456789abcdef")
    _header, ordering = read_journal(state_dir / JOURNAL_NAME)
    assert len(ordering) == 4
    Store.open(state_dir, registry()).close()


def test_a_line_that_is_not_a_batch_id_refuses(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _record_run(state_dir)
    with open(state_dir / JOURNAL_NAME, "ab") as handle:
        handle.write(b"not a batch id, and not 64 hex digits either!!!!\n")
    with pytest.raises(JournalError, match="is not a batch id"):
        read_journal(state_dir / JOURNAL_NAME)


def test_the_journal_refuses_to_record_anything_but_a_batch_id(
        tmp_path: Path) -> None:
    journal = Journal.create(tmp_path / JOURNAL_NAME, {"magic": "x"},
                             fsync=False)
    with pytest.raises(JournalError, match="not a batch id"):
        journal.append("nope", 0)
    journal.close()


def test_reading_a_directory_that_holds_no_journal_refuses(
        tmp_path: Path) -> None:
    with pytest.raises(JournalError, match="no journal"):
        read_journal(tmp_path / JOURNAL_NAME)


def test_a_divergent_refold_is_refused_never_rewritten(
        tmp_path: Path) -> None:
    """Integrator ruling 2026-08-14: the journal is never rewritten.

    A crashed state reopened with inputs that cannot reproduce the
    recorded tail refuses loudly — naming the position, both batch ids
    and the remedy — instead of silently truncating the authoritative
    history. Truncation is the operator's, explicitly (delete the state
    dir).
    """
    journal = Journal.create(tmp_path / JOURNAL_NAME, {"magic": "x"},
                             fsync=False)
    journal.append("a" * 64, 0)
    journal.append("b" * 64, 1)
    journal.append("a" * 64, 0)          # re-earned: the record stands
    with pytest.raises(JournalError, match="cannot reproduce the recorded"):
        journal.append("c" * 64, 1)
    assert len(journal) == 2, "the recorded history is intact"

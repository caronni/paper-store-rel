"""Diag v0: observer-side only, disposable, state-inert (DESIGN §10.3, L12).

The claims under test are the boundary ones: the provider reads the commit
stream and a bound snapshot and nothing else; an observer that fails does
not raise into the receiver; and the endpoint is opt-in and stoppable.
"""
from __future__ import annotations

import urllib.request

from holo2.diag import status as diag
from holo2.core.commit import CommitResult
from holo2.capture import capture_key
from holo2.engine.snapshot import (CommitLedger, CommitStream, QueueView,
                                   RunSnapshot, WorkCounters, WorkerView)
from holo2.solve import tile_key


def _commit(seq: int, *keys, wakes=()) -> CommitResult:
    return CommitResult(commit_seq=seq, batch_id=f"batch-{seq}",
                        changed_keys=tuple(keys), wakes=tuple(wakes))


def test_one_ledger_counts_every_commit_of_the_session() -> None:
    """One owner, two names: the session total and the run's own subset.

    Ingest commits before a run exists, so those results are PARKED and
    replayed into the run's ledger when it takes over — a second tally on
    this side is what used to make "commits" mean 471 in one pane and 472
    in another.
    """
    provider = diag.StatusProvider()
    provider.note_commit(_commit(1, capture_key("ab" * 32),
                                 wakes=("place:w1",)))       # ingest's
    ledger = CommitLedger()
    provider.adopt_ledger(ledger)                            # the run starts
    ledger.note(_commit(2, tile_key(0, 0, 0, "main"),
                        wakes=("place:w1", "payload:p1")), scheduled=True)
    provider.publish(RunSnapshot(stream=ledger.stream(),
                                 counters=WorkCounters(
                                     commits=ledger.scheduled_commits,
                                     wakes=ledger.scheduled_wakes)))
    status = provider.status()
    stream = status["commit_stream"]
    assert stream["commits"] == 2 and stream["scheduled_commits"] == 1
    assert stream["changed_keys"] == 2
    assert stream["wakes"] == 3 and stream["scheduled_wakes"] == 2
    assert stream["wakes_per_commit"] == 1.5
    assert stream["changed_by_kind"] == {"capture": 1, "tile": 1}
    assert stream["wakes_by_worker"] == {"place:w1": 2, "payload:p1": 1}
    # The pin: the two published numbers are the same tally, not two.
    assert status["session"]["counters"]["commits"] == stream[
        "scheduled_commits"]
    assert status["session"]["counters"]["wakes"] == stream["scheduled_wakes"]


def test_a_published_snapshot_joins_the_status() -> None:
    provider = diag.StatusProvider()
    provider.publish(RunSnapshot(queue=QueueView(depth=3)))
    assert provider.status()["session"]["ready"] == {
        "depth": 3, "by_family": {}}
    assert provider.status()["provisional"] is True


def test_a_snapshot_a_run_could_not_mint_is_text_not_an_exception() -> None:
    """L12: the run reports why there is no instant; it never raises one."""
    provider = diag.StatusProvider()
    provider.publish(error="RuntimeError: viewer exploded")
    status = provider.status()
    assert "session" not in status
    assert status["session_error"] == "RuntimeError: viewer exploded"


def test_asking_for_a_status_asks_the_run_for_the_next_instant() -> None:
    """Push, not pull: a poll is a REQUEST, honoured at the next commit."""
    provider = diag.StatusProvider()
    assert not provider.wants_snapshot()
    provider.status()
    assert provider.wants_snapshot()
    provider.publish(RunSnapshot(recipe="recipe-unit"))
    assert not provider.wants_snapshot()


def test_the_rows_are_the_operator_block_not_a_frame() -> None:
    """One terminal formatter: the fixed six-row block, and nothing else."""
    provider = diag.StatusProvider()
    provider.publish(RunSnapshot(
        queue=QueueView(depth=2, by_family={"place": 1, "payload": 1}),
        workers=WorkerView(total=5, sleeping=2, retired=1, declined=1,
                           declined_pending=0),
        counters=WorkCounters(commits=1, fires=4, wakes=2, useful_fires=1),
        stream=CommitStream(commits=1, wakes=2, changed_keys=1),
        plane={"tiles": {"ADDRESSED": 3, "CERTIFIED": 1}},
        close={"status": "open"}))
    rows = provider.status()["rows"]
    assert len(rows) == 6
    text = "\n".join(rows)
    assert "commits 1" in text and "fires 4" in text
    assert "ready 2[payload:1,place:1]" in text       # sorted, deterministic
    assert "declined 1 (re-offerable 0)" in text
    assert "CERTIFIED 1" in text and "close    open" in text


def test_the_endpoint_serves_the_status_and_stops() -> None:
    provider = diag.StatusProvider()
    provider.publish(RunSnapshot(stream=CommitStream(commits=1)))
    server = diag.serve(0, provider)
    assert server is not None
    try:
        with urllib.request.urlopen(server.url, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "application/json"
            body = response.read()
        assert b'"commits":1' in body
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/nope",
                                   timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:                                   # pragma: no cover
            raise AssertionError("unknown paths must 404")
    finally:
        server.stop()


def test_a_port_that_will_not_bind_is_not_an_error() -> None:
    provider = diag.StatusProvider()
    first = diag.serve(0, provider)
    assert first is not None
    try:
        assert diag.serve(first.port, provider) is None
    finally:
        first.stop()

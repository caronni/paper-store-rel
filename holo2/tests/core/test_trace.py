"""The trace is instrumentation now: sampled digests, and nothing else.

F-16 took the ordering away from it — the journal carries that, one 65-byte
line per commit, fsynced at the commit — so what is left is the L11 honesty
canary: on sampled commits only, what went in and what came out. Off by
default means OFF: an unsampled run writes no file at all.

The ordering property these tests used to hold (replaying a recorded
ordering reproduces the state) lives in ``test_journal.py``, against the
file that now records it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from holo2.core.codec import digest_json, encode_typed_record
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.core.trace import TraceEvent, TraceError, TraceReader, TraceWriter
from conftest import (MintRef, PoseRecord, POSE, RegionRecord, TileRecord,
                      ground_batch, make_pose, make_session,
                      registry, subscribe, tile_key)

_TILE = tile_key(2, 5, 6, "K")


def toy_workload(store: Store) -> tuple[CommitBatch, ...]:
    """Scripted commits — no algorithms, only shapes the store must carry.

    The first commit is the fixture GROUND (capture, region, window): a
    region names its capture and a pose its window (F-07's relational
    half), so a replayable workload has to lay them like a real run.
    """
    bits_ref = store.blobs.put(b"certified payload bits")
    base = ground_batch("window")
    return (
        CommitBatch(
            writes=base.writes, blobs=base.blobs,
            subscriptions=(subscribe("w-tile", _TILE),)),
        CommitBatch(writes=(
            Write(_TILE, TileRecord(
                                    observed_by=("cap:8/1",))),
            Write(POSE, make_pose()))),
        CommitBatch(writes=(Write(_TILE, TileRecord(
            observed_by=("cap:8/1",))),)),                        # no-op commit
        CommitBatch(writes=(Write(_TILE, TileRecord(
            MintRef(POSE, "scan", "fixture-decoder"), bits_ref, 0,
            ("cap:8/1",))),)),
    )


def _record_run(state_dir: Path, *, sample_every: int = 0
                ) -> tuple[bytes, tuple[CommitBatch, ...]]:
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(
            store, trace=TraceWriter(store.trace_path, sample_every=sample_every))
        batches = toy_workload(store)
        for batch in batches:
            engine.apply(batch)
        return store.state_bytes(), batches


def test_sampling_off_writes_no_file_at_all(tmp_path: Path) -> None:
    """The default costs one modulo test per commit and zero bytes."""
    state_dir = tmp_path / "plain"
    _record_run(state_dir)
    assert not (state_dir / "trace.jsonl").exists()
    assert TraceReader(state_dir / "trace.jsonl").samples() == ()


def test_sampling_on_is_deterministic_and_carries_both_digests(
        tmp_path: Path) -> None:
    sampled = tmp_path / "sampled"
    _record_run(sampled, sample_every=2)
    events = TraceReader(sampled / "trace.jsonl").samples()
    assert [event.seq for event in events] == [2, 4]
    for event in events:
        assert event.input_sha256 == event.batch_id

    again = tmp_path / "sampled-again"
    _record_run(again, sample_every=2)
    assert ((sampled / "trace.jsonl").read_bytes()
            == (again / "trace.jsonl").read_bytes())


def test_the_sampled_digest_carries_each_records_type(tmp_path: Path) -> None:
    """The canary digests WHAT was written, class name included.

    The per-write entry used to be ``[key, version, fields]``: two
    different record types at one key with coincidentally equal field
    values digested the same, a blind spot in exactly the honesty canary
    this digest IS (§10.3, L11). The entry carries
    ``encode_typed_record``'s ``{type, value}``, and this pins it — a
    silent return to the untagged shape changes the digest and fails here.
    """
    state_dir = tmp_path / "typed"
    record = TileRecord(observed_by=("cap:8/1",))
    with Store.create(state_dir, make_session(), registry()) as store:
        engine = CommitEngine(
            store, trace=TraceWriter(store.trace_path, sample_every=1))
        engine.apply(CommitBatch(writes=(Write(_TILE, record),)))
    event, = TraceReader(state_dir / "trace.jsonl").samples()
    assert encode_typed_record(record)["type"] == "TileRecord"
    assert event.output_sha256 == digest_json(
        [[_TILE.to_json(), 1, encode_typed_record(record)]])


def test_trace_lines_carry_no_wall_reading(tmp_path: Path) -> None:
    recorded_dir = tmp_path / "recorded"
    _record_run(recorded_dir, sample_every=1)
    text = (recorded_dir / "trace.jsonl").read_text()
    for banned in ("time", "clock", "timestamp", "elapsed"):
        assert banned not in text


def test_the_store_does_not_depend_on_the_trace(tmp_path: Path) -> None:
    """The trace is disposable: deleting it costs observability only."""
    state_dir = tmp_path / "state"
    state, _ = _record_run(state_dir, sample_every=1)
    (state_dir / "trace.jsonl").unlink()
    with Store.open(state_dir, registry()) as reopened:
        assert reopened.state_bytes() == state
        assert TraceReader(reopened.trace_path).samples() == ()


def test_torn_trace_tail_is_dropped(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _record_run(state_dir, sample_every=1)
    path = state_dir / "trace.jsonl"
    with open(path, "ab") as handle:
        handle.write(b'{"seq":5,"batch_id":"abc","input_sha')
    assert len(TraceReader(path).samples()) == 4


def test_trace_event_round_trips() -> None:
    event = TraceEvent(seq=7, batch_id="ab" * 32, input_sha256="cd" * 32,
                       output_sha256="ef" * 32)
    assert TraceEvent.from_json(event.to_json()) == event
    with pytest.raises(TraceError, match="malformed trace event"):
        TraceEvent.from_json({"seq": 7, "batch_id": "ab" * 32})

"""v0.37 re-auth stat-memo pins (PAYLOAD-REWORK-PLAN 3.3, RECEIVE-DESIGN §8).

The per-barrier re-authentication law stands; the detector is stat-based
with cryptographic escalation: a fstat tuple (dev, ino, size, mtime_ns)
identical to the retained ingest-verified tuple skips the byte re-stream,
ANY observable difference escalates to the full re-stream + SHA compare,
and the memo refreshes only after a passing full check.  Threat model on
record: accidental mutation only (PAYLOAD-IMPROVEMENTS 7.2).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from holo.receive import scan
from holo.receive.observer import ReceiverQualificationStatus
from holo.receive.runtime import (
    LaneAlgorithms,
    ReceivePipeline,
    ReceiveRequest,
    run_receive,
)
from holo.receive.scan import open_capture
from holo.receive.types import Stage


def _write_png(path: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, (16, 20), dtype=np.uint8)
    Image.fromarray(pixels, mode="L").save(path)


def _count_streams(monkeypatch) -> list[int]:
    """Wrap the module-level file hasher with a call counter."""
    counter = [0]
    naive = scan._sha256_file

    def counting(path: Path) -> str:
        counter[0] += 1
        return naive(path)

    monkeypatch.setattr(scan, "_sha256_file", counting)
    return counter


def test_stat_memo_hit_skips_the_re_stream(tmp_path, monkeypatch) -> None:
    path = tmp_path / "capture.png"
    _write_png(path, 5_001)
    streams = _count_streams(monkeypatch)

    raster = open_capture(path, 1200.0)
    assert streams[0] == 1  # exactly the one ingest hash

    # Unchanged stat tuple: every retention barrier is a memo hit.
    raster.verify_source_unchanged()
    raster.verify_source_unchanged()
    assert streams[0] == 1


def test_any_stat_delta_escalates_then_refreshes_the_memo(
    tmp_path, monkeypatch,
) -> None:
    path = tmp_path / "capture.png"
    _write_png(path, 5_002)
    streams = _count_streams(monkeypatch)
    raster = open_capture(path, 1200.0)
    assert streams[0] == 1

    # mtime_ns forward, bytes identical: full re-stream, passes, and the
    # refreshed memo makes the next barrier a hit again.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    raster.verify_source_unchanged()
    assert streams[0] == 2
    raster.verify_source_unchanged()
    assert streams[0] == 2


def test_mutation_is_refused_and_the_memo_never_refreshes(
    tmp_path, monkeypatch,
) -> None:
    path = tmp_path / "capture.png"
    _write_png(path, 5_003)
    streams = _count_streams(monkeypatch)
    raster = open_capture(path, 1200.0)

    _write_png(path, 5_004)  # different bytes on the same path
    with pytest.raises(ValueError, match="source changed"):
        raster.verify_source_unchanged()
    assert streams[0] == 2
    # A failing full check must not install a memo for the mutated file.
    with pytest.raises(ValueError, match="source changed"):
        raster.verify_source_unchanged()
    assert streams[0] == 3


def test_missing_source_is_unavailable_at_retention(tmp_path) -> None:
    path = tmp_path / "capture.png"
    _write_png(path, 5_005)
    raster = open_capture(path, 1200.0)
    path.unlink()
    with pytest.raises(ValueError, match="unavailable at retention"):
        raster.verify_source_unchanged()


def test_in_memory_sources_never_re_stream(monkeypatch) -> None:
    streams = _count_streams(monkeypatch)
    raster = open_capture(np.arange(48, dtype=np.uint8).reshape(6, 8), 1200.0)
    raster.verify_source_unchanged()
    assert streams[0] == 0


def test_source_mutation_still_refused_end_to_end(tmp_path) -> None:
    """The runtime's commit-time re-auth still refuses a mid-run mutation.

    Fast-pin port of the orphaned ``_source_mutation_case`` battery shape
    (PAYLOAD-IMPROVEMENTS 8.2): a payload stage rewrites the source file
    between processing and the first retention barrier; the stat delta
    escalates to the full re-stream, the SHA differs, the barrier refuses,
    and no durable state is written.
    """
    import _qualify_runtime_fixtures as fixtures

    image = tmp_path / "mutable.png"
    fixtures._write_image(image, 44_001)
    calls: tuple[list[str], list[str], list[str]] = ([], [], [])
    payload = fixtures._Payload(calls[2])

    class MutatingPayload:
        stage = Stage.PAYLOAD
        policy_id = "qualification/runtime-mutating-payload/v1"

        def process(self, context, survey, address):
            result = payload.process(context, survey, address)
            fixtures._write_image(image, 44_002)
            return result

    pipeline = ReceivePipeline(
        LaneAlgorithms(
            fixtures._Survey(calls[0]),
            fixtures._Address(calls[1]),
            MutatingPayload(),
        ),
        fixtures._Scheduler(),
        fixtures._OpenClose(),
        qualification_status=ReceiverQualificationStatus.QUALIFIED,
    )
    state_path = tmp_path / "mutated.json"
    with pytest.raises(ValueError, match="source changed"):
        run_receive(
            ReceiveRequest(
                fixtures._spec(), (fixtures._capture(image),), state_path),
            pipeline=pipeline)
    assert not state_path.exists()

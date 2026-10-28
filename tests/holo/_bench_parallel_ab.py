"""Tier-0/1 worker-parallelism A/B: state-digest equality + wall.

EXPERIMENT (holo-parallel-tier1).  Standalone (not pytest):

    PYTHONPATH=src <python> tests/holo/_bench_parallel_ab.py [workers...]

Runs the _bench_phased synthetic corpus (roundtrip fixture field + two
re-placed scraps, single page, full --refine drive) once per worker
count (default: 1 and 8), comparing the authoritative durable-state
SHA-256, the recovered payload, and per-stage processor seconds.  The
determinism contract requires byte-identical durable state at every
worker count; a digest mismatch is a defect in the parallel paths.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench_phased as bench_phased
import _roundtrip_fixture as roundtrip
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.session import authoritative_sha256
from holo.receive.types import CaptureInput


def _run_once(workers: int) -> dict:
    os.environ["HOLO_RECEIVE_WORKERS"] = str(workers)
    fixture = roundtrip._build_fixture()
    full = np.array(fixture.raster, copy=True)
    full.setflags(write=False)
    captures = (
        CaptureInput(full, roundtrip._DPI),
        CaptureInput(bench_phased._scrap(fixture, 32, 32, 128),
                     roundtrip._DPI),
        CaptureInput(bench_phased._scrap(fixture, 96, 96, 128),
                     roundtrip._DPI),
    )
    stage_seconds: dict[str, float] = defaultdict(float)
    counters = {"barriers": 0, "colds": 0}

    def observe(event) -> None:
        name = event.name
        if name == "barrier.committed":
            counters["barriers"] += 1
        elif name == "address.cold_open":
            counters["colds"] += 1
        elif name in ("stage.complete", "stage.refused"):
            details = {row.name: row.value for row in event.details}
            seconds = details.get("timing.processor_seconds")
            if isinstance(seconds, (int, float)):
                stage_seconds[event.stage.value] += float(seconds)

    with TemporaryDirectory() as scratch:
        request = ReceiveRequest(
            fixture.spec, captures,
            state_path=Path(scratch) / "ab.json",
            page_hypotheses=(0,),
            run_refine=True)
        start = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            result = run_receive(
                request, pipeline=production_pipeline(request),
                observer=observe)
        wall = time.perf_counter() - start
    return {
        "workers": workers,
        "wall_s": round(wall, 2),
        "verified": result.verified,
        "certificates": len(result.state.certificates),
        "state_sha256": authoritative_sha256(result.state),
        "payload_sha": (
            None if result.payload is None
            else __import__("hashlib").sha256(result.payload).hexdigest()),
        "stage_seconds": {
            name: round(seconds, 2)
            for name, seconds in sorted(stage_seconds.items())},
        **counters,
    }


def main() -> None:
    worker_counts = (
        tuple(int(value) for value in sys.argv[1:]) or (1, 8))
    runs = [_run_once(workers) for workers in worker_counts]
    baseline = runs[0]
    for run in runs[1:]:
        run["state_matches_baseline"] = (
            run["state_sha256"] == baseline["state_sha256"])
        run["payload_matches_baseline"] = (
            run["payload_sha"] == baseline["payload_sha"])
        run["speedup_vs_first"] = round(
            baseline["wall_s"] / run["wall_s"], 2)
    print(json.dumps(runs, indent=1))


if __name__ == "__main__":
    main()

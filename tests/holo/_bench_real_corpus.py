"""Real-corpus A/B runner: phased vs capture-major on chain scraps.

Standalone; run in each worktree:
    PYTHONPATH=src <python> tests/holo/_bench_real_corpus.py <corpus_dir>
Fresh session per run; prints one JSON line with wall, event counts,
close facts, and ground-truth payload comparison.
"""
from __future__ import annotations

import json
import resource
import sys
import time
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

from holo.format.registry import get_format_row
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput


def main() -> None:
    corpus = Path(sys.argv[1])
    prior = json.load(open(corpus / "receive.json"))["state"]
    spec = get_format_row(prior["format_row_id"])
    pages = prior.get("page_hypotheses")
    pages = None if pages is None else tuple(pages)
    truth = (corpus / "payload.bin").read_bytes()
    captures = tuple(
        CaptureInput(str(corpus / name), 4800.0)
        for name in ("scraps-r4800-001.tif", "scraps-r4800-002.tif"))
    counters = {
        "barriers": 0, "colds": 0, "close_checks": 0, "capture_resumes": 0,
        "phase_events": 0, "parked_peak": 0,
    }
    stage_seconds: dict[str, float] = {}

    from _bench_payload_decomp import _Decomposer, _totals
    if "--counterfactual-no-refine" in sys.argv:
        # Bench-only counterfactual (never a production knob): isolate the
        # rework's cost from ruling 10.6's refinement cost.
        from holo.receive import production_color
        from holo.receive.color_refine import ColorForwardRefinement
        production_color.refine_color_address_once = (
            lambda raster, address, generation0, spec, certs:
            ColorForwardRefinement(address, (), ()))
    decomp = _Decomposer()

    def observe(event) -> None:
        decomp.observe(event)
        name = event.name
        if name == "barrier.committed":
            counters["barriers"] += 1
        elif name == "address.cold_open":
            counters["colds"] += 1
        elif name == "close.check":
            counters["close_checks"] += 1
        elif name == "capture.resume":
            counters["capture_resumes"] += 1
        elif name == "session.phase":
            counters["phase_events"] += 1
        if name in ("stage.complete", "stage.refused"):
            details = {row.name: row.value for row in event.details}
            seconds = details.get("timing.processor_seconds")
            lane = str(details.get("lane.id", "?"))
            if isinstance(seconds, (int, float)):
                kind = ("mopup" if lane.startswith("m")
                        else "refine" if lane.startswith("r")
                        else "base")
                key = f"{kind}.{event.stage.value}"
                stage_seconds[key] = stage_seconds.get(key, 0.0) + float(seconds)

    with TemporaryDirectory() as scratch:
        request = ReceiveRequest(
            spec, captures,
            state_path=Path(scratch) / "ab.json",
            page_hypotheses=pages,
            # v0.42: the full phased drive (M + R levels) is flag-gated.
            run_refine=True)
        start = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            result = run_receive(
                request, pipeline=production_pipeline(request),
                observer=observe)
        wall = time.perf_counter() - start
        state = result.state
        counters["parked_peak"] = len(getattr(state, "parked", ()))
    payload = result.payload
    print(json.dumps({
        "wall_s": round(wall, 1),
        "verified": result.verified,
        "payload_matches_gt": payload == truth if payload else False,
        "certificates": len(state.certificates),
        "close_status": state.close.status.value,
        "levels_per_capture": [
            len(row.levels) for row in state.captures],
        "peak_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20),
        "stage_seconds": {
            key: round(value, 1)
            for key, value in sorted(stage_seconds.items())},
        "runtime_residual_s": round(
            wall - sum(stage_seconds.values()), 1),
        **counters,
        "payload_decomposition": _totals(decomp, wall),
    }))


if __name__ == "__main__":
    main()

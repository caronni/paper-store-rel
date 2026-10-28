"""v0.33 A/B bench: phased schedule vs capture-major baseline.

Standalone (not pytest): run in each worktree —
    PYTHONPATH=src env/bin/python tests/holo/_bench_phased.py
Prints one JSON line: wall seconds, barrier/close/cold counts, verified.
Corpus: the roundtrip fixture field — one full-field capture plus two
re-placed scrap captures (parking material), single-page domain.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _roundtrip_fixture as roundtrip
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput


def _scrap(fixture, y0_cells, x0_cells, span_cells):
    spec = fixture.spec
    px = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * px) // 2
    y0 = int(origin_px[0] + y0_cells * px)
    x0 = int(origin_px[1] + x0_cells * px)
    span = span_cells * px
    piece = np.array(fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 4 * 64 * px // 8
    canvas = np.full((span + 2 * margin, span + 2 * margin),
                     float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)
    return canvas


def main() -> None:
    import holo.receive.production_close as production_close
    import holo.receive.production_payload as production_payload

    close_calls = [0]
    real_close = production_close.close_volume

    def counting_close(*args, **kwargs):
        close_calls[0] += 1
        return real_close(*args, **kwargs)

    # Both fountain consult sites: the close gate and the K advisory
    # preclose (one module pre-v0.38, split homes since).
    production_close.close_volume = counting_close
    production_payload.close_volume = counting_close
    fixture = roundtrip._build_fixture()
    full = np.array(fixture.raster, copy=True)
    full.setflags(write=False)
    captures = (
        CaptureInput(full, roundtrip._DPI),
        CaptureInput(_scrap(fixture, 32, 32, 128), roundtrip._DPI),
        CaptureInput(_scrap(fixture, 96, 96, 128), roundtrip._DPI),
    )
    counters = {"barriers": 0, "colds": 0, "close_checks": 0}

    def observe(event) -> None:
        if event.name == "barrier.committed":
            counters["barriers"] += 1
        elif event.name == "address.cold_open":
            counters["colds"] += 1
        elif event.name == "close.check":
            counters["close_checks"] += 1

    with TemporaryDirectory() as scratch:
        request = ReceiveRequest(
            fixture.spec, captures,
            state_path=Path(scratch) / "bench.json",
            page_hypotheses=(0,),
            # v0.42: the full phased drive (M + R levels) is flag-gated.
            run_refine=True)
        start = time.perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ProvisionalReceiverWarning)
            result = run_receive(
                request, pipeline=production_pipeline(request),
                observer=observe)
        wall = time.perf_counter() - start
    print(json.dumps({
        "wall_s": round(wall, 2),
        "verified": result.verified,
        "certificates": len(result.state.certificates),
        "close_volume_calls": close_calls[0],
        **counters,
    }))


if __name__ == "__main__":
    main()

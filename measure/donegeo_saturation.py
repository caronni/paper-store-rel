"""Saturation micro-bench for the done-geometry gate.

Deterministic, unit level, no rasters: it builds a store at the endgame
shape — every tile of the page certified but one, a full grid of placed
windows over it, plus a set of never-placed (parked) windows sitting
inside the certified area — and reports, per gated row, how much
scheduling work the gate turns into an eligible-refusal.

    PYTHONPATH=src:. python measure/donegeo_saturation.py

The two costs it prices are the ones a pop actually pays: the gate
itself (`store.window_fully_done`, both branches) and the prepare it
replaces (`place`'s own ring consult, which walks every committed pose
of the region — until 2026-09-21 the `revisit` row paid that consult a
second time on exactly these parked windows, and its deletion is the
first thing this bench measured the value of).  The calibrate row's
avoided cost is a raster sample and is not priced here — only counted.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from pathlib import Path

from holo.receiver import data, engine
from holo.receiver.plugins import calibrate, place_sched
from holo.receiver.tests import _h3_facts

FORMAT_REF = _h3_facts.FORMAT_REF          # c3-k-r0550@7x7 — 49 tiles
TILE_CELLS = 64
PARKED_EXTENT_CELLS = 40
OPEN_TILE = (6, 6)


def _engine() -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,), format_ref=FORMAT_REF,
        max_pages=1, workers=1, complete=False, no_close=False,
        diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-donegeo-bench-")))
    instance = engine._Engine(request, [])
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.survey())
    return instance


def saturated_store(n_parked: int = 40) -> tuple[engine._Engine, list, list]:
    """One placed window per tile, `n_parked` never-placed windows inside
    the certified area, every tile certified but `OPEN_TILE`."""
    instance = _engine()
    planned = instance.windows()[0]
    frame = instance.frame(planned[:3])
    tiles_y, tiles_x = instance.row.tiles_yx
    placed: list = []
    for ordinal, (ty, tx) in enumerate(
            [(y, x) for y in range(tiles_y) for x in range(tiles_x)]):
        extent = (0, 0, frame.shape_cells[0], frame.shape_cells[1])
        wid = (_h3_facts.CAPTURE_ID, 0, 0, extent) if ordinal == 0 else (
            _h3_facts.CAPTURE_ID, 0, 0,
            (ty, tx, ty + TILE_CELLS, tx + TILE_CELLS))
        if instance.window(wid) is None:
            instance._ingest(_h3_facts.window(wid=wid, ordinal=ordinal))
        instance._ingest(replace(
            _h3_facts.placement(wid=wid),
            page_origin_yx=(ty * TILE_CELLS, tx * TILE_CELLS)))
        instance._ingest(_h3_facts.evidence(
            wid=wid, cells=instance.page_cells(wid)))
        placed.append(wid)
    parked: list = []
    for index in range(n_parked):
        extent = (index, index, index + PARKED_EXTENT_CELLS,
                  index + PARKED_EXTENT_CELLS)
        wid = (_h3_facts.CAPTURE_ID, 0, 0, extent)
        instance._ingest(_h3_facts.window(wid=wid, ordinal=1000 + index))
        parked.append(wid)
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            if (ty, tx) == OPEN_TILE:
                continue
            instance._ingest(_h3_facts.certificate(0, ty, tx))
    return instance, placed, parked


def _time(call: object, repeats: int) -> float:
    call()
    started = time.perf_counter()
    for _ in range(repeats):
        call()
    return (time.perf_counter() - started) / repeats


def report(n_parked: int = 40, repeats: int = 200) -> None:
    instance, placed, parked = saturated_store(n_parked)
    certified = instance.n_certificates()
    done_placed = [wid for wid in placed if instance.window_fully_done(wid)]
    done_parked = [wid for wid in parked if instance.window_fully_done(wid)]
    live_placed = [wid for wid in placed
                   if not instance.window_fully_done(wid)]
    print(f"page {instance.row.tiles_yx} tiles, {certified} certified, "
          f"one open at {OPEN_TILE}")
    print(f"placed windows {len(placed)}: gate fires on {len(done_placed)}, "
          f"{len(live_placed)} stay live")
    print(f"parked windows {len(parked)}: gate fires on {len(done_parked)}")

    placed_gate = _time(
        lambda: instance.window_fully_done(done_placed[0]), repeats)
    parked_gate = _time(
        lambda: instance.window_fully_done(done_parked[0]), repeats)
    consult = _time(
        lambda: place_sched.untried_consult(
            instance, instance.place_stage(done_parked[0]), wide=False),
        repeats)
    print(f"gate cost: placed branch {placed_gate * 1e6:.1f} us, "
          f"pose-free branch {parked_gate * 1e6:.1f} us")
    print(f"prepare cost it replaces (ring consult over "
          f"{len(instance.placements())} poses): {consult * 1e6:.1f} us")

    # counterfactual: what the same pops did before the gate existed
    calibrate_before = sum(1 for wid in placed
                           if instance.placement(wid) is not None)
    calibrate_after = sum(1 for wid in placed
                          if calibrate._window_eligible(instance, wid))
    place_retires = sum(1 for wid in parked
                        if place_sched.place_retire_cause(instance, wid))
    print(f"calibrate pops that fire a job: {calibrate_before} -> "
          f"{calibrate_after} (one raster sample + fit each)")
    print(f"place: {place_retires} of {len(parked)} parked rows retire at "
          f"their next pop")
    saved = len(parked) * (consult - parked_gate)
    print(f"one wake of every parked row: {saved * 1e3:.1f} ms of ring "
          f"consult replaced by {parked_gate * 1e6:.1f} us refusals")


if __name__ == "__main__":
    report()

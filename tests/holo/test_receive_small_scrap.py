"""First-order per-tile contract: a placed scrap certifies every tile it
fully contains.

User design (2026-07-28 18:54): the ~100 word bits plus per-tile furniture
are enough on their own to attempt the payload tile decode — no region- or
window-level label quota may veto a covered tile. Measured on this branch
(2026-07-29): a 24 mm c3 scrap certifies 4/4 contained tiles, a 16 mm scrap
1/1; the 8 mm single-tile scrap fails earlier, at placement (small-scrap
floors are the separate package).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.production import production_pipeline
from holo.receive.session import CaptureStatus
from holo.receive.types import CaptureInput

import _roundtrip_fixture as roundtrip


@pytest.fixture(scope="module")
def fixture():
    return roundtrip._build_fixture()


def _contained_tiles(y0_cells: int, x0_cells: int, span_cells: int,
                     tiles_x: int) -> set[tuple[int, int]]:
    """Tiles fully inside a [y0, y0+span) x [x0, x0+span) cell box."""
    out = set()
    ty0, tx0 = -(-y0_cells // 64), -(-x0_cells // 64)
    ty1 = (y0_cells + span_cells) // 64
    tx1 = (x0_cells + span_cells) // 64
    for ty in range(ty0, ty1):
        for tx in range(tx0, tx1):
            out.add((ty, tx))
    return out


def test_placed_scrap_certifies_every_fully_contained_tile(
    fixture, tmp_path
) -> None:
    spec = fixture.spec
    px_per_cell = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * px_per_cell) // 2

    # A 2x2-tile-SIZED crop, deliberately NOT tile-aligned (offset by a
    # half tile), so it fully contains exactly one tile.
    y0_cells, x0_cells = 32, 32
    span_cells = 128
    y0 = int(origin_px[0] + y0_cells * px_per_cell)
    x0 = int(origin_px[1] + x0_cells * px_per_cell)
    span = span_cells * px_per_cell
    piece = np.array(
        fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 4 * 64 * px_per_cell // 8
    canvas = np.full(
        (span + 2 * margin, span + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)

    request = ReceiveRequest(
        spec,
        (CaptureInput(canvas, roundtrip._DPI),),
        state_path=tmp_path / "scrap.json",
        page_hypotheses=(0,),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        result = run_receive(
            request, pipeline=production_pipeline(request))

    contained = _contained_tiles(
        y0_cells, x0_cells, span_cells, spec.layout.tiles_yx[1])
    assert contained, "test geometry contains no full tile"
    certified = {
        (row.tile_yx[0], row.tile_yx[1])
        for row in result.state.certificates
    }
    missing = contained - certified
    assert not missing, (
        f"fully contained tiles were not certified: {sorted(missing)} "
        f"(certified: {sorted(certified)})")
    # And nothing outside the scrap may certify.
    reachable = _contained_tiles(
        y0_cells - 64, x0_cells - 64, span_cells + 128,
        spec.layout.tiles_yx[1])
    assert certified <= reachable

    # ---- v0.42 R-level leg: drive the SAME open scrap state through the
    # full plan (--refine covers the pending M-levels by the plan-prefix
    # law).  The scrap leaves an uncertified remainder, so the R levels
    # run the REAL K leaf — durable pose/region reconstruction
    # (place_committed) on the derived lane rasters, generation zero,
    # and the certified refinement opportunity — and every level commits.
    refine_request = ReceiveRequest(
        spec,
        (CaptureInput(canvas, roundtrip._DPI),),
        state_path=tmp_path / "scrap.json",
        page_hypotheses=(0,),
        run_mopup=True,
        run_refine=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        refined = run_receive(
            refine_request, pipeline=production_pipeline(refine_request))
    capture = refined.state.captures[0]
    assert len(capture.levels) == len(capture.plan)
    assert capture.status is CaptureStatus.COMPLETE
    r_lanes = [row for row in capture.plan if row.refine_of is not None]
    assert r_lanes and all(
        lane.mopup_of is None for lane in r_lanes)
    # The refinement levels never lose certified truth, and any new
    # certificate stays inside the scrap's reachable tile domain.
    refined_certified = {
        (row.tile_yx[0], row.tile_yx[1])
        for row in refined.state.certificates
    }
    assert certified <= refined_certified <= reachable

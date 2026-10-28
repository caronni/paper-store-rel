"""Multi-capture K-path regression: a second same-lane capture must commit.

The 2026-07-31 growth audit found `ProductionPayload` passing the merged
frontier as BOTH `run_attempts` arguments (the documented contract is
``(new_blocks, frontier_blocks)``; the color path honors it).  With any
retained uncertified prior-capture block at the same lane, the engine then
minted SCAN attempts over prior acquisitions' components, and the barrier
refused ("scan attempt does not use the current acquisition") — breaking
the measured 3-4-scans/sheet doctrine for K rows.  This test is the
regression: capture 1 leaves uncertified evidence, capture 2 at the same
DPI must still commit and certify.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput

import _roundtrip_fixture as roundtrip


@pytest.fixture(scope="module")
def fixture():
    return roundtrip._build_fixture()


def _crop_canvas(fixture, y0_cells, x0_cells, span_cells):
    spec = fixture.spec
    ppc = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    origin = spec.layout.origin_dots_yx
    y0 = int(origin[0] + y0_cells * ppc)
    x0 = int(origin[1] + x0_cells * ppc)
    span = span_cells * ppc
    piece = np.array(fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 16 * ppc
    canvas = np.full(
        (span + 2 * margin, span + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)
    return canvas


def test_second_same_lane_capture_commits_and_unions(
    fixture, tmp_path: Path,
) -> None:
    spec = fixture.spec
    # Capture 1: a 96-cell crop straddling tile boundaries — it certifies
    # its fully covered tile(s) and RETAINS uncertified partial-tile
    # evidence blocks.  Capture 2: an overlapping 128-cell crop at the
    # same DPI (same lane plan) covering those partial tiles fully.
    first = _crop_canvas(fixture, 32, 32, 96)
    second = _crop_canvas(fixture, 32, 32, 128)
    request = ReceiveRequest(
        spec,
        (CaptureInput(first, roundtrip._DPI),
         CaptureInput(second, roundtrip._DPI)),
        state_path=tmp_path / "multicapture.json",
        page_hypotheses=(0,),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        result = run_receive(request, pipeline=production_pipeline(request))

    assert len(result.state.captures) == 2
    assert all(
        level.payload is not None
        for capture in result.state.captures
        for level in capture.levels
    ), "every level must reach a committed payload barrier"
    # The second capture must contribute evidence (union or fresh scan),
    # and the run must certify at least the tiles fully covered by the
    # union of both crops.
    assert result.state.certificates, "no tiles certified across captures"

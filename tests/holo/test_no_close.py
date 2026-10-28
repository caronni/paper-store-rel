"""--no-close: the close layer is never entered (ruling 2026-08-19).

The state x mode table this pins:

  state on disk   | --complete (defer+finalize) | --no-close (defer, never)
  ----------------+-----------------------------+--------------------------
  absent          | one close at end            | OPEN, no CloseRecord
  OPEN            | close at end                | accumulate only
  terminal        | replay/report               | DETACH -> OPEN, ingest

--no-close implies the non-greedy deferral (--complete alongside is
legal and redundant); finalize=False without deferral is incoherent and
refused.  Detach is lossless: a close is a pure derivation from the
certificate set, and the closing run after a detach re-verifies
byte-exactly.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.session import SessionStatus, detach_close
from holo.receive.types import CaptureInput, CloseRecord

import _roundtrip_fixture as roundtrip


@pytest.fixture(scope="module")
def fixture():
    return roundtrip._build_fixture()


def _run(spec, captures, state_path, *, defer, finalize):
    request = ReceiveRequest(
        spec, captures, state_path=state_path,
        page_hypotheses=(0,), defer_fountain_close=defer)
    with warnings.catch_warnings():
        warnings.simplefilter("always", ProvisionalReceiverWarning)
        return run_receive(request, pipeline=production_pipeline(request),
                           finalize_deferred_close=finalize)


def _crop(fixture, y0_cells, x0_cells, span_cells):
    spec = fixture.spec
    px = spec.cell_dots
    oy, ox = spec.layout.origin_dots_yx
    y0, x0 = oy + y0_cells * px, ox + x0_cells * px
    span = span_cells * px
    piece = np.array(fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 64 * px
    canvas = np.full((span + 2 * margin, span + 2 * margin),
                     float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)
    return canvas


def test_no_close_matrix(fixture, tmp_path) -> None:
    spec = fixture.spec
    state_path = tmp_path / "no-close.state"
    full = (CaptureInput(fixture.raster, roundtrip._DPI),)

    # (a) fresh + --no-close: certificates accumulate, the close layer
    # is never entered, no CloseRecord is written.
    res = _run(spec, full, state_path, defer=True, finalize=False)
    assert res.state.status is SessionStatus.OPEN
    assert res.state.close == CloseRecord()
    assert res.payload is None and not res.verified
    assert len(res.state.certificates) == spec.tiles_per_page

    # (b) OPEN resume + --no-close: still accumulation only.
    res = _run(spec, full, state_path, defer=True, finalize=False)
    assert res.state.status is SessionStatus.OPEN
    assert res.state.close == CloseRecord()

    # (c) the close-later promise: a --complete-shaped run closes
    # byte-exact from the accumulated certificates.
    res = _run(spec, full, state_path, defer=True, finalize=True)
    assert res.state.status is SessionStatus.VERIFIED
    assert res.payload == fixture.payload

    # (d) terminal + --no-close with a NEW capture: the close DETACHES,
    # the state reopens, the capture ingests (the e033 sheet-I workflow).
    both = full + (CaptureInput(_crop(fixture, 64, 64, 192),
                                roundtrip._DPI),)
    res = _run(spec, both, state_path, defer=True, finalize=False)
    assert res.state.status is SessionStatus.OPEN
    assert res.state.close == CloseRecord()
    assert len(res.state.captures) == 2

    # (e) the closing run after a detach recomputes the close from ALL
    # certificates and re-verifies byte-exactly.
    res = _run(spec, both, state_path, defer=True, finalize=True)
    assert res.state.status is SessionStatus.VERIFIED
    assert res.payload == fixture.payload


def test_detach_close_unit(fixture, tmp_path) -> None:
    spec = fixture.spec
    res = _run(spec, (CaptureInput(fixture.raster, roundtrip._DPI),),
               tmp_path / "unit.state", defer=True, finalize=True)
    verified = res.state
    assert verified.status is SessionStatus.VERIFIED
    reopened = detach_close(verified)
    assert reopened.status is SessionStatus.OPEN
    assert reopened.close == CloseRecord()
    assert reopened.certificates == verified.certificates
    assert detach_close(reopened) is reopened     # OPEN is a fixed point


def test_no_close_without_deferral_is_incoherent(fixture, tmp_path) -> None:
    request = ReceiveRequest(
        fixture.spec, (CaptureInput(fixture.raster, roundtrip._DPI),),
        state_path=tmp_path / "bad.state",
        page_hypotheses=(0,), defer_fountain_close=False)
    with pytest.raises(ValueError, match="defer"):
        run_receive(request, pipeline=production_pipeline(request),
                    finalize_deferred_close=False)


def test_cli_guards() -> None:
    import sys
    from holo import cli
    # --no-close and --complete together are legal (redundant deferral).
    sys.argv = ["confetti", "decode", "x.tif", "--scan-dpi", "600",
                "--state", "/nonexistent/s", "-o", "o",
                "--no-close", "--complete", "--format", "c3-k-r0550@7x7"]
    with pytest.raises((SystemExit, Exception)) as info:
        cli.main()
    assert "--no-close" not in str(info.value)   # failed later, not on flags
    # discovery mode refuses --no-close.
    sys.argv = ["confetti", "decode", "x.tif", "--scan-dpi", "600",
                "--state", "/nonexistent/s", "-o", "o", "--no-close"]
    with pytest.raises(SystemExit, match="exact-session knob"):
        cli.main()

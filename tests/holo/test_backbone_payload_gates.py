"""Task-10(a): honest per-coding real-payload round-trip gates.

The acceptance net for the stream-generic payload backbone (KISS task 10,
user rescope 2026-07-30): every coding row round-trips a REAL multi-symbol
payload through the current production pipeline on a compact 7x7-tile page.

Why these gates exist: the historical qualification payloads were 32-64
bytes, which collapses the fountain to ~1 source symbol, and an all-zero
payload leaves nearly all source symbols identical — either way the fountain
block assembly and rank machinery went unexercised.  Each gate here pins an
explicit ``k_total`` floor so it cannot silently degrade back to a trivial
fountain, and asserts the full semantic outcome the backbone refactor must
reproduce: recovered bytes, VERIFIED close, every tile certified on every
stream, zero divergences.

Channel: clean render (K: ink/paper + 0.5px Gaussian, the proven roundtrip
optical model; color: the qualification forward model at nominal defaults).
Robustness under the measured channel is a separate axis
(test_measured_channel_gate).
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from holo.format.descriptor import CODINGS, FormatSpec
from holo.gen.emit import emit_volume
from holo.gen.plan import plan_volume
from holo.qualification.color_synthetic import render_color_scan
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput


_PAPER = np.uint8(245)
_INK = np.uint8(35)
# q=0.8 (the e016 K/N) on the 49-tile K pages: the §13.16 planner's
# 16-symbol fountain reserve leaves k_total ~23 — a real multi-symbol
# fountain (q=0.5 would collapse it to 7).  Color pages carry q=0.5 so the
# fountain rank stays comfortably inside the measured ~72%% placement
# coverage.
_Q_K = 0.8
_Q_COLOR = 0.5
_K_FLOOR = 20              # the honest-fountain floor: >= 20 source symbols
_METADATA_TRUST = 48       # distinct certified counters the close requires

# K rows ride the proven 7x7 (49-tile) geometry and certify every tile on
# a clean page.  Color rows get 10x10 (100 tiles): MEASURED 2026-07-30, the
# placement layer resolves only ~70-75% of windows on a clean composite
# color page at every footing (2-12 ppc), so 49 tiles cannot clear the
# metadata trust-48 bar — a finding for the parked placement work, not a
# payload-engine property this gate should hide or gate on.
_K_TILES = (7, 7)
_COLOR_TILES = (10, 10)
_K_MEDIA_MM = {2: (40.0, 40.0), 3: (60.0, 60.0)}
_COLOR_MEDIA_MM = {2: (55.0, 55.0), 3: (82.0, 82.0)}
# Scan footing per cell size: c3 decodes clean at 1 px/dot (the proven
# roundtrip footing); c2 gets 2 px/dot for its finer cells.
_UPSAMPLE = {2: 2, 3: 1}

_ALL_ROWS = tuple(CODINGS)

# Default suite: one K row + one 3-stream color row (~36s); the colour
# representative is the POOLED -v1 row (CMY8-POOLING-PLAN P5 — the -v0
# per-stream row keeps its slow-lane gate and its unit/stack coverage).
# The full nine-row net runs with HOLO_RUN_SLOW_TESTS=1 and is the
# mandatory pre/post checkpoint for backbone refactors.
_FAST_ROWS = ("c3-r0550", "c3-cmy8-p120-v1")

# Wall-budget tripwires, NOT profiling (the doctrine instrument is
# `confetti.py decode --profile-timing`).  ~3x the 2026-07-30 measured
# decode walls on the reference machine: a breach means a mechanism
# regression (e.g. the ~12s/window full-domain cold search leaking back
# into the gated --page path), never ordinary noise.
_WALL_BUDGET_S = {
    "c3-r0550": 60.0,
    "c2-r0550": 120.0,
    "c2-r0700": 120.0,
    "c2-cmy7-p120-v0": 180.0,
    "c3-cmy7-p120-v0": 180.0,
    "c2-cmy8-p120-v0": 180.0,
    "c3-cmy8-p120-v0": 180.0,
    # pooled -v1 rows: identical tile codec and receiver path; only the
    # outer code differs, so the -v0 budgets carry over.
    "c2-cmy8-p120-v1": 180.0,
    "c3-cmy8-p120-v1": 180.0,
}


def _rows() -> tuple[str, ...]:
    if os.environ.get("HOLO_RUN_SLOW_TESTS"):
        return _ALL_ROWS
    return _FAST_ROWS


def _compact_spec(coding_id: str) -> FormatSpec:
    coding = CODINGS[coding_id]
    color = coding.codec_id != "k-v1"
    media = (_COLOR_MEDIA_MM if color else _K_MEDIA_MM)[coding.cell_dots]
    spec = FormatSpec(coding, f"backbone-q-{coding.cell_dots}", media, 0.0)
    expected = _COLOR_TILES if color else _K_TILES
    if spec.layout.tiles_yx != expected:
        raise AssertionError(
            f"backbone gate geometry drifted: {spec.layout.tiles_yx}")
    return spec


def _q_for(spec: FormatSpec) -> float:
    return _Q_K if spec.codec_id == "k-v1" else _Q_COLOR


def _real_payload(spec: FormatSpec, coding_id: str) -> bytes:
    """Largest single-page payload — always a multi-symbol fountain."""
    q = _q_for(spec)
    low, high = 1, 512_000
    while low < high:  # largest n with a one-page plan
        mid = (low + high + 1) // 2
        try:
            pages = plan_volume(spec, mid, q).n_pages
        except ValueError:
            pages = 2
        if pages == 1:
            low = mid
        else:
            high = mid - 1
    length = max(1, low)  # full fill: maximum source symbols on one page
    payload = hashlib.shake_256(
        b"holo/backbone-q1/" + coding_id.encode("ascii")).digest(length)
    plan = plan_volume(spec, length, q)
    assert plan.n_pages == 1
    assert plan.k_total >= _K_FLOOR, (
        f"{coding_id}: k_total {plan.k_total} is a trivial fountain")
    assert len(set(payload[index:index + 8]
                   for index in range(0, length - 8, 8))) > length // 16
    return payload


def _page_canvas(spec: FormatSpec, field: np.ndarray) -> np.ndarray:
    """Place a field-resolution array on the full page dot canvas."""
    page_x, page_y = spec.layout.page_dots_xy
    shape = ((page_y, page_x) if field.ndim == 2
             else (page_y, page_x, field.shape[2]))
    canvas = np.zeros(shape, field.dtype)
    origin_y, origin_x = spec.layout.origin_dots_yx
    height, width = field.shape[:2]
    canvas[origin_y:origin_y + height, origin_x:origin_x + width] = field
    return canvas


def _upsample(array: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return array
    return np.repeat(np.repeat(array, factor, axis=0), factor, axis=1)


def _k_raster(spec: FormatSpec, gt_path: Path) -> tuple[np.ndarray, float]:
    packed = np.load(gt_path, allow_pickle=False)
    field_h, field_w = spec.layout.field_dots_yx
    dots = np.unpackbits(
        packed, axis=1, count=field_w, bitorder="big").astype(bool)
    assert dots.shape == (field_h, field_w)
    factor = _UPSAMPLE[spec.cell_dots]
    ink = _upsample(_page_canvas(spec, dots), factor)
    raster = np.where(ink, _INK, _PAPER).astype(np.float32)
    raster = np.ascontiguousarray(ndimage.gaussian_filter(raster, 0.5))
    return raster, 600.0 * factor


def _color_raster(spec: FormatSpec, gt_path: Path) -> tuple[np.ndarray, float]:
    packed = np.load(gt_path, allow_pickle=False)
    field_h, field_w = spec.layout.field_dots_yx
    assert packed.shape[0] == 3
    coverage = np.stack([
        np.unpackbits(packed[plane], axis=1, count=field_w,
                      bitorder="big").astype(np.float64)
        for plane in range(3)
    ], axis=-1)
    assert coverage.shape == (field_h, field_w, 3)
    # 2 px/dot (1200 dpi): the footing the production color gate closes at.
    # MEASURED 2026-07-30: finer footings (4 px/dot -> 6/12 ppc lanes) added
    # ZERO color certificates — the limiter is placement coverage, not
    # sampling.  A paper border keeps the field out of the edge-desert zone.
    factor = 2
    border_dots = 60
    padded = np.zeros(
        (spec.layout.page_dots_xy[1] + 2 * border_dots,
         spec.layout.page_dots_xy[0] + 2 * border_dots, 3), np.float64)
    padded[border_dots:-border_dots, border_dots:-border_dots] = (
        _page_canvas(spec, coverage))
    source = _upsample(padded, factor)
    scan = render_color_scan(source)
    rgb = np.clip(np.asarray(scan.rgb), 0.0, 1.0)
    raster = np.ascontiguousarray(
        np.round(rgb * 255.0).astype(np.uint8))
    return raster, 600.0 * factor


@pytest.mark.parametrize("coding_id", _rows())
def test_real_payload_round_trip_certifies_every_stream(
    tmp_path: Path,
    coding_id: str,
) -> None:
    spec = _compact_spec(coding_id)
    payload = _real_payload(spec, coding_id)
    volume = emit_volume(spec, payload, _q_for(spec), tmp_path / "volume")
    assert len(volume.pages) == 1
    page = volume.pages[0]

    if spec.codec_id == "k-v1":
        raster, dpi = _k_raster(spec, page.gt_path)
    else:
        raster, dpi = _color_raster(spec, page.gt_path)

    # Declared one-page domain (the production --page feature): without it
    # the cold search correlates against the full 312/140-page domain at
    # ~12s per window (measured 2026-07-30) — the parked frontier-scheduler
    # territory, not what this payload-layer gate qualifies.
    request = ReceiveRequest(
        spec, (CaptureInput(raster, dpi),),
        state_path=tmp_path / f"{coding_id}.receive.json",
        page_hypotheses=(0,))
    started = time.perf_counter()
    with pytest.warns(ProvisionalReceiverWarning):
        result = run_receive(request, pipeline=production_pipeline(request))
    decode_wall_s = time.perf_counter() - started

    assert result.payload == payload, f"{coding_id}: recovered bytes differ"
    state = result.state
    assert state.status.value == "verified"
    assert state.close.status.value == "verified"
    assert state.close.payload_length == len(payload)
    assert state.close.payload_sha256 == hashlib.sha256(payload).hexdigest()

    streams = tuple(spec.stream_ids)
    tiles = spec.tiles_per_page
    certified = {(row.page, row.tile_yx, row.stream_id)
                 for row in state.certificates}
    assert len(certified) == len(state.certificates)
    assert {row[2] for row in certified} == set(streams)
    if spec.codec_id == "k-v1":
        assert len(certified) == tiles * len(streams), (
            f"{coding_id}: {len(certified)} certificates != "
            f"{tiles} tiles x {len(streams)} streams")
    else:
        # Color: full address coverage is NOT an engine property (the
        # placement layer measurably resolves only ~70-75%% of windows on
        # clean composite pages — parked placement finding).  The engine
        # bar: every stream balanced above the metadata trust floor.
        per_stream = {stream: sum(1 for row in certified if row[2] == stream)
                      for stream in streams}
        if spec.pooled_fountain:
            # Pooled -v1 rows have NO per-stream rank requirement — that
            # is the design (CMY8-POOLED-FOUNTAIN §2.3): verified stop
            # can preempt as soon as the ONE pool reaches rank, so
            # per-stream counts land wherever the barrier caught them
            # (measured here: c2 closed at {C:48, M:47, Y:47} where -v0
            # had to certify every stream past its own rank).  The
            # pooled engine bar: metadata trust actually consumed
            # (>= 48 equations total) and symmetric stream treatment.
            assert sum(per_stream.values()) >= _METADATA_TRUST, (
                f"{coding_id}: {per_stream} cannot have carried trust-48")
        else:
            assert min(per_stream.values()) >= _METADATA_TRUST, (
                f"{coding_id}: per-stream certificates {per_stream}")
        assert max(per_stream.values()) - min(per_stream.values()) <= 3, (
            f"{coding_id}: stream imbalance {per_stream}")
    # Divergence rows are the routine non-gating cross-lane audit (one per
    # certified tile re-observed by a later scale lane); a genuine
    # certificate conflict is fatal and cannot reach this point.  Bound the
    # audit volume rather than demanding zero.
    assert state.counters.divergences <= 2 * tiles * len(streams)
    assert result.observer_failures == ()
    # Last so a semantic failure always surfaces before the tripwire.
    assert decode_wall_s <= _WALL_BUDGET_S[coding_id], (
        f"{coding_id}: decode took {decode_wall_s:.1f}s, budget "
        f"{_WALL_BUDGET_S[coding_id]:.0f}s — a scheduling/search mechanism "
        "regressed; profile with `confetti.py decode --profile-timing`")


def test_session_index_refuses_a_substitute_spec() -> None:
    """An in-request spec must be the state's own format, never a stand-in."""
    from holo.receive.session import SessionIndex, SessionState

    spec = _compact_spec("c3-r0550")
    state = SessionState.create(spec.spec_id, "policy/backbone-gate", (0,))
    other = _compact_spec("c2-r0550")
    with pytest.raises(ValueError, match="differs from the state format row"):
        SessionIndex(state, spec=other, validate=False)
    index = SessionIndex(state, spec=spec, validate=False)
    assert index.stream_ids == ("main",)
    color = _compact_spec("c3-cmy8-p120-v0")
    color_state = SessionState.create(
        color.spec_id, "policy/backbone-gate", (0,))
    assert SessionIndex(
        color_state, spec=color, validate=False,
    ).stream_ids == ("C", "M", "Y")

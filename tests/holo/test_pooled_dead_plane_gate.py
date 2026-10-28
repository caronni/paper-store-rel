"""THE dead-plane gate (CMY8-POOLING-PLAN P5 — the change's reason).

Compose-level Y blanking, end to end: a pooled -v1 volume whose Y plane
is erased EVERYWHERE on the rendered page must still close byte-exact
through the real production receiver — the deterministic plane tier
doing its job. The -v0 per-stream negative control on the same blanked
render stays OPEN (slow lane; its close-level twin is always-on in
test_pooled_close). Render/footing/one-page-domain conventions follow
test_backbone_payload_gates.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from holo.format.descriptor import CODINGS, FormatSpec
from holo.gen.emit import emit_volume
from holo.gen.plan import plan_volume
from holo.qualification.color_synthetic import render_color_scan
from holo.receive.observer import ProvisionalReceiverWarning
from holo.receive.production import production_pipeline
from holo.receive.runtime import ReceiveRequest, run_receive
from holo.receive.types import CaptureInput

# The dead-plane dial: with one plane dead only ~2/3 of the symbols can
# exist, and clean-page colour placement resolves ~72% of windows
# (measured, backbone-gate finding), so the surviving C/M certificate
# supply is ~0.72 * 2 per tile.  q=0.35 (the rocksolid class) leaves an
# honest margin below it while staying a real multi-symbol fountain.
_Q = 0.35
_MEDIA_MM = (82.0, 82.0)          # the backbone 10x10 c3 colour geometry
_DEAD_PLANE = 2                   # Y


def _compact_spec(coding_id: str) -> FormatSpec:
    coding = CODINGS[coding_id]
    spec = FormatSpec(coding, "dead-plane-q", _MEDIA_MM, 0.0)
    if spec.layout.tiles_yx != (10, 10):
        raise AssertionError(
            f"dead-plane gate geometry drifted: {spec.layout.tiles_yx}")
    return spec


def _payload(coding_id: str) -> bytes:
    # 20,000 B -> k_meta 26 / k_total 78 on the 100-tile page at q=0.35:
    # a real multi-symbol pool inside the one-page budget (k_total <= 89).
    return hashlib.shake_256(
        b"holo/dead-plane-gate/" + coding_id.encode("ascii")).digest(20_000)


def _y_blanked_raster(spec: FormatSpec,
                      gt_path: Path) -> tuple[np.ndarray, float]:
    """The backbone colour render with the Y plane erased everywhere."""
    packed = np.load(gt_path, allow_pickle=False)
    assert packed.shape[0] == 3
    packed = packed.copy()
    packed[_DEAD_PLANE] = 0                      # the dead plane
    field_h, field_w = spec.layout.field_dots_yx
    coverage = np.stack([
        np.unpackbits(packed[plane], axis=1, count=field_w,
                      bitorder="big").astype(np.float64)
        for plane in range(3)
    ], axis=-1)
    page_x, page_y = spec.layout.page_dots_xy
    origin_y, origin_x = spec.layout.origin_dots_yx
    canvas = np.zeros((page_y, page_x, 3), np.float64)
    canvas[origin_y:origin_y + field_h,
           origin_x:origin_x + field_w] = coverage
    border = 60
    padded = np.zeros(
        (page_y + 2 * border, page_x + 2 * border, 3), np.float64)
    padded[border:-border, border:-border] = canvas
    source = np.repeat(np.repeat(padded, 2, axis=0), 2, axis=1)
    scan = render_color_scan(source)
    rgb = np.clip(np.asarray(scan.rgb), 0.0, 1.0)
    return np.ascontiguousarray(
        np.round(rgb * 255.0).astype(np.uint8)), 1200.0


def _decode(spec: FormatSpec, raster: np.ndarray, dpi: float,
            tmp_path: Path, tag: str):
    request = ReceiveRequest(
        spec, (CaptureInput(raster, dpi),),
        state_path=tmp_path / f"{tag}.receive.json",
        page_hypotheses=(0,))
    with pytest.warns(ProvisionalReceiverWarning):
        return run_receive(request, pipeline=production_pipeline(request))


def test_pooled_volume_survives_a_dead_y_plane(tmp_path: Path) -> None:
    spec = _compact_spec("c3-cmy8-p120-v1")
    payload = _payload("c3-cmy8-p120-v1")
    plan = plan_volume(spec, len(payload), _Q)
    assert plan.n_pages == 1 and plan.k_meta is not None
    assert plan.k_total >= 20                    # honest multi-symbol pool
    volume = emit_volume(spec, payload, _Q, tmp_path / "volume")
    raster, dpi = _y_blanked_raster(spec, volume.pages[0].gt_path)

    result = _decode(spec, raster, dpi, tmp_path, "pooled-dead-y")

    assert result.payload == payload, "dead-Y pooled volume must recover"
    state = result.state
    assert state.status.value == "verified"
    assert state.close.payload_sha256 == hashlib.sha256(payload).hexdigest()
    streams = {row.stream_id for row in state.certificates}
    assert "Y" not in streams, "a dead plane must yield zero Y certificates"
    assert streams == {"C", "M"}


@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the -v0 dead-plane control",
)
def test_v0_control_stays_open_on_the_same_dead_y_render(
    tmp_path: Path,
) -> None:
    """Negative control: the per-stream -v0 row CANNOT survive dead Y at
    any dial — the Y stream is a 100% erasure (design §1)."""
    spec = _compact_spec("c3-cmy8-p120-v0")
    payload = _payload("c3-cmy8-p120-v0")
    volume = emit_volume(spec, payload, _Q, tmp_path / "volume")
    raster, dpi = _y_blanked_raster(spec, volume.pages[0].gt_path)

    result = _decode(spec, raster, dpi, tmp_path, "v0-dead-y")

    assert result.payload is None
    state = result.state
    assert state.status.value == "open"
    assert "Y" not in {row.stream_id for row in state.certificates}

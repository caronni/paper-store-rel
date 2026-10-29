"""THE dead-plane gate (CMY8-POOLING-PLAN P5 — the change's reason).

Gate E re-home: the vehicle is holo3 — the production receiver — driven
on the same Y-blanked render.  The -v0 compose-level control cannot come
along: cmy8 ``-v0`` has no v2 identity at a compact tile matrix, so
holo3 cannot be told what to read; its close-level twin is always-on in
test_pooled_close.

Compose-level Y blanking, end to end: a pooled -v1 volume whose Y plane
is erased EVERYWHERE on the rendered page must still close byte-exact —
the deterministic plane tier doing its job.  Render and footing come
from _colour_gate_render, the one helper the backbone colour gate uses
too, with the dead plane dialled in.

The lane: slow (2026-09-20).  This is a whole render-to-receiver
decode, and the backbone gate's colour page is the default lane's one
of those; the always-on close-level twin in test_pooled_close keeps
the dead-plane law itself in every commit's reach.
"""
from __future__ import annotations

import hashlib
import os
import warnings
from pathlib import Path

import pytest

from holo.format.resolve import resolve_format_ref
from holo.gen.emit import emit_volume
from holo.gen.plan import plan_volume

from _colour_gate_render import colour_raster
from _receive_free import decode_with_holo3

# The dead-plane dial: with one plane dead only ~2/3 of the symbols can
# exist, and clean-page colour placement resolves ~72% of windows
# (measured, backbone-gate finding), so the surviving C/M certificate
# supply is ~0.72 * 2 per tile.  q=0.35 (the rocksolid class) leaves an
# honest margin below it while staying a real multi-symbol fountain.
_Q = 0.35
_FORMAT_REF = "c3-cmy8-r0550@10x10"   # the v2 name of c3-cmy8-p120-v1
_DEAD_PLANE = 2                       # Y


def _payload() -> bytes:
    # 20,000 B -> k_meta 26 / k_total 78 on the 100-tile page at q=0.35:
    # a real multi-symbol pool inside the one-page budget (k_total <= 89).
    return hashlib.shake_256(
        b"holo/dead-plane-gate/" + _FORMAT_REF.encode("ascii")).digest(20_000)


@pytest.mark.skipif(
    os.environ.get("HOLO_RUN_SLOW_TESTS") != "1",
    reason="set HOLO_RUN_SLOW_TESTS=1 for the dead-plane page gate",
)
def test_pooled_volume_survives_a_dead_y_plane(tmp_path: Path) -> None:
    spec = resolve_format_ref(_FORMAT_REF)
    payload = _payload()
    plan = plan_volume(spec, len(payload), _Q)
    assert plan.n_pages == 1 and plan.k_meta is not None
    assert plan.k_total >= 20                    # honest multi-symbol pool
    volume = emit_volume(spec, payload, _Q, tmp_path / "volume")
    raster = colour_raster(spec, volume.pages[0].gt_path,
                           dead_plane=_DEAD_PLANE)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        decode = decode_with_holo3(((raster, 1200.0),), _FORMAT_REF,
                                   tmp_path, "pooled-dead-y")

    assert decode.exit_code == 0, decode.stdout
    assert decode.payload == payload, "dead-Y pooled volume must recover"
    assert decode.status == "verified"
    assert decode.report["run_done"]["payload_sha256"] == hashlib.sha256(
        payload).hexdigest()
    counts = decode.plane_certs
    assert counts.get("Y", 0) == 0, "a dead plane must yield zero Y certs"
    assert counts["C"] > 0 and counts["M"] > 0

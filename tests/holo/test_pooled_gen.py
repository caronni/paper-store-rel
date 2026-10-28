"""P3 pins for pooled -v1 generation (CMY8-POOLING-PLAN).

Planner arithmetic + the dial POLICY (the planner-side half of the P1
predicate/policy split: the dead-plane tier is dial-conditional and
reported, never a refusal — ruling 2026-08-14), the per-stream
metadata-bit compose seam, and the frozen row-seed emission goldens
(PS + packed-GT digests per -v1 row — the format anchors of the pooled
rows).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from holo.core import capacity
from holo.format import metadata
from holo.format.registry import get_format_row
from holo.gen.color_compose import _metadata_bits_for_tile
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes, plan_volume

C3_ROW = "c3-cmy8-p120-v1@2240x1536"
C2_ROW = "c2-cmy8-p120-v1@3328x2304"


def test_pooled_plan_arithmetic_and_dial_policy():
    spec = get_format_row(C3_ROW)
    plan = plan_volume(spec, 50_000, 0.5)
    assert plan.k_meta is not None
    assert plan.k_total == 3 * plan.k_meta
    assert plan.n_symbols_total == plan.n_pages * spec.tiles_per_page * 3
    assert plan.n_repair == plan.n_symbols_total - plan.k_total
    assert plan.symbol_bits == 2087
    # the dial policy is PLANNER POLICY (predicate stays pure — P1):
    # at or below (n-1)/n the plane tier is enforced in sizing and the
    # promise is carried...
    assert plan.plane_tier == "guaranteed"
    assert capacity.pooled_page_capacity_sufficient(
        plan.k_total, spec.tiles_per_page, plan.n_pages, 0.5,
        n_streams=3, enforce_plane_tier=True)
    assert plan_volume(spec, 1_000, 0.66).plane_tier == "guaranteed"
    # ... and above it every legal dial still plans; the tier drops out
    # of sizing and the plan says so out loud (ruling 2026-08-14).
    for q in (0.67, 0.7, 0.9):
        above = plan_volume(spec, 1_000, q)
        assert above.n_pages >= 1
        assert above.plane_tier == "not-at-this-dial (needs q <= 2/3)"
    # -v0 rows keep their dial range and carry no pooled tier
    v0 = get_format_row(C3_ROW.replace("-v1@", "-v0@"))
    assert plan_volume(v0, 1_000, 0.75).plane_tier is None


def test_pooled_capacity_query_fills_to_the_true_dial():
    """Above the ceiling a fixed-page capacity query does not refuse and
    does not quote a ~2/3-fill volume as if it honored the dial: tiers
    1+2 size it to the TRUE dial and the dead-plane tier is reported
    absent (ruling 2026-08-14)."""
    spec = get_format_row(C3_ROW)
    high = plan_volume(spec, max_payload_bytes(spec, 0.9, 5), 0.9)
    assert high.n_pages == 5
    assert high.effective_k_over_n > 2 / 3          # not capped at ~2/3
    assert high.plane_tier == "not-at-this-dial (needs q <= 2/3)"
    limit = max_payload_bytes(spec, 0.5, 1)
    assert limit > 0
    assert plan_volume(spec, limit, 0.5).n_pages == 1
    assert plan_volume(spec, limit + 4_000, 0.5).n_pages == 2


def test_pooled_metadata_bits_are_per_stream_distinct():
    v1 = get_format_row(C3_ROW)
    v0 = get_format_row(C3_ROW.replace("-v1@", "-v0@"))
    word = metadata.encode_metadata(0, 918)
    replicated = _metadata_bits_for_tile(v0, word, 0)
    assert len(set(replicated)) == 1                    # -v0: copies
    assert replicated[0] == metadata.tile_bit(word, 0)  # bit-identical
    pooled = _metadata_bits_for_tile(v1, word, 0)
    bound = metadata.max_equation_index(3)
    assert pooled == tuple(
        metadata.tile_bit(word, metadata.equation_index(0, s, 3),
                          max_index=bound)
        for s in range(3))
    distinct_somewhere = any(
        len(set(_metadata_bits_for_tile(v1, word, counter))) > 1
        for counter in range(16))
    assert distinct_somewhere                           # not copies


# Frozen row-seed emission goldens (format anchors of the pooled rows;
# payload = bytes(i % 251), q = 0.5, page 0). Movement = format fork.
EMIT_GOLDENS = {
    C3_ROW: {
        "payload_bytes": 20_000,
        "k_meta": 26,
        "ps_sha256":
            "d651e84b82d71b6cca375cfa31e5910b285e16eb50563380a1a5d91c4dad61a6",
        "gt_sha256":
            "670994624494b5a2f7dacc10bc79aeb89cf47eab2e884d3ce446263445ed9844",
        "gt_plane_sha256": (
            "f55e70c9e49da8d92f8f9df805f78274f0f2bc0d8f947356a0e719df8d3237e5",
            "aa1289ac4ca9af1c56dee8337b185bc9eae5fdc1569a0672a00bcf576df552e2",
            "54f5aa6c7b86a3aa209aa4a824e0ec4c24e15c20e8c7ec603bf80645ab7732b7",
        ),
    },
    C2_ROW: {
        "payload_bytes": 30_000,
        "k_meta": 39,
        "ps_sha256":
            "857ff63c3bee0c7203149b470313a4b7cce6058f6c30d2cb8671119cf1cc9c2d",
        "gt_sha256":
            "b0027c71f9d44b5926bce457cbcaf31885310f4c302544bfe4e47181e23c6d88",
        "gt_plane_sha256": (
            "abd509b281a62127fcaa7fcd5791b00f2e5da3a20735a3353a08324506588899",
            "a328d575eee0d0d84788a930e61052449f28a8e386007fb880aa80c9a0094361",
            "d6cc5097646126dfc353e7ff04af02584c6ad318bb543a7a2f714310647d00c2",
        ),
    },
}


@pytest.mark.parametrize("row_id", sorted(EMIT_GOLDENS))
def test_pooled_emit_round_trip_smoke_and_frozen_goldens(row_id, tmp_path):
    spec = get_format_row(row_id)
    golden = EMIT_GOLDENS[row_id]
    payload = bytes(i % 251 for i in range(golden["payload_bytes"]))
    vol = emit_volume(spec, payload, 0.5, tmp_path / "vol")
    assert vol.plan.k_meta == golden["k_meta"]
    assert vol.plan.k_total == 3 * golden["k_meta"]
    assert vol.plan.n_pages == 1
    page = vol.pages[0]
    assert page.ps_sha256 == golden["ps_sha256"]
    assert page.gt_sha256 == golden["gt_sha256"]
    assert page.gt_plane_sha256 == golden["gt_plane_sha256"]
    manifest = json.loads((tmp_path / "vol" / "manifest.json").read_text())
    assert manifest["pooled_fountain"] == {
        "pooled": True,
        "k_meta": golden["k_meta"],
        "n_streams": 3,
        "esi": "counter*n_streams + stream_idx",
        "metadata_k_field": "k_meta (k_total = n_streams*k_meta)",
        "plane_tier": "guaranteed",
    }
    assert manifest["volume"]["k_total"] == 3 * golden["k_meta"]
    # GT on disk matches the digest of the canonical packed bytes
    packed = np.load(tmp_path / "vol" / "page000_gt.npy")
    import hashlib
    assert hashlib.sha256(
        packed.tobytes(order="C")).hexdigest() == golden["gt_sha256"]

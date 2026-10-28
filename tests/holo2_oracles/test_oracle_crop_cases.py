"""Pins the PURE logic of ``holo2/measure/crop_cases.py`` (HANDOFF-CROP
Deliverable A) — class sets, clustering + split, the control rim rule,
the manifest schema. No state is opened and no capture is read: the
decodes-and-crops half is the driver's own business (a census, not a
test), exactly as ``test_oracle_tile_differential.py`` pins the
classifier and not the differential.

Lives here and not under ``holo2/tests`` for the same reason the other
oracle modules do: ``crop_cases`` imports ``holo`` at module level (it
reads v1 states), and only ``tests/holo2_oracles/`` may reach v1. The
``sys.path`` preamble is borrowed from ``test_oracle_parity_k.py``
(named fork of that fixture pattern: same three roots plus
``holo2/measure``, so the by-path driver imports as a sibling).

THE FORKS THIS PINS, each silent on the real corpus:

1. **The raw-flip overlap double-counted.** A tile the F1/F2 line turned
   positive that v1 never certified sits in BOTH the raw pre→F2 flip set
   and ``v1_missing`` (measured on the real sheets: 1 e029 / 3 xerox).
   The module's ruling is that ``v1_missing`` wins and ``flipped`` is
   the remainder; a generator using the raw definition would hand
   Deliverable B the same tile twice under two classes, and its census
   arithmetic would disagree with the recorded F2 headers while looking
   plausible.
2. **An off-by-one in the merge gap.** ``--merge-gap-tiles`` counts
   EMPTY tiles between targets (gap 0 = adjacent, so Chebyshev distance
   gap+1 merges). Read as a plain distance bound it turns the xerox
   tx=0 band (consecutive ty, distance 1) into 47 singleton crops —
   deterministic, fully covering, and 47x the decode cost the knob
   exists to avoid.
3. **Transposed bbox order.** The manifest fixes ``cell_bbox``/
   ``px_bbox`` as X-FIRST ``[x0, y0, x1, y1]`` on a page that is TALLER
   than wide in cells (3392 y x 2368 x), read by Deliverable B in
   parallel. A y-first writer crops the wrong region on every
   non-square case and no schema key changes shape.
4. **A control on the rim, or a target as a control.** A both-certified
   tile whose extent straddles the 32-cell rim would measure boundary
   truncation, not crop-vs-full-sheet agreement; a ``flipped`` target is
   both-certified in the final sets and must not double as a stability
   control.
5. **Schema drift.** Deliverable B is coded against HANDOFF-CROP's
   manifest schema key-for-key; an added or dropped key is a contract
   break the generator must refuse itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_ROOT / "src", _ROOT / "holo2" / "src",
              _ROOT / "holo2" / "measure"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import crop_cases                                                # noqa: E402
from crop_cases import (CLASS_NAMES, Cluster, GlobalAffine,      # noqa: E402
                        RecordedDifferential, build_case_entry,
                        cell_bbox_for, cluster_targets, compute_classes,
                        controls_for, crosscheck_headers, px_bbox_for,
                        split_clusters, validate_manifest)


# --------------------------------------------------------------------
# class sets
# --------------------------------------------------------------------


def test_class_sets_disjoint_with_overlap_ruling():
    """Fork 1: the raw pre→F2 flip set overlaps v1_missing; the ruling
    (module docstring) is v1_missing wins and the overlap is REPORTED."""
    v1 = frozenset({(0, 0), (1, 1), (2, 2), (3, 3)})
    pre = frozenset({(0, 0), (1, 1)})
    # (2,2): flipped into the shared set. (4,4): flipped in but v1 never
    # had it -> v1_missing, NOT flipped. (3,3): v1-only. (5,5): neither.
    f2 = frozenset({(0, 0), (1, 1), (2, 2), (4, 4)})
    sets = compute_classes(v1, pre, f2, (6, 6))
    assert sets.flipped == {(2, 2)}
    assert sets.v1_missing == {(4, 4)}
    assert sets.raw_flip_overlap == {(4, 4)}
    assert sets.still_missing_v2 == {(3, 3)}
    assert (5, 5) in sets.neither and len(sets.neither) == 36 - 5
    # disjoint within the sheet, and every target carries exactly one class
    named = [getattr(sets, name) for name in CLASS_NAMES]
    assert sum(len(s) for s in named) == len(sets.targets)
    for tile in sets.targets:
        assert sum(tile in s for s in named) == 1
    assert sets.class_of((4, 4)) == "v1_missing"
    # flipped is a subset of both-certified by construction
    assert sets.flipped <= (v1 & f2)


def test_class_sets_refuse_out_of_domain():
    with pytest.raises(ValueError, match="outside"):
        compute_classes(frozenset({(9, 9)}), frozenset(), frozenset(),
                        (6, 6))


def test_crosscheck_refuses_header_mismatch():
    """The cross-check refuses when the recomputed sets disagree with the
    recorded markdown headers (a stale or foreign record, not a knob)."""
    v1 = frozenset({(0, 0), (1, 1)})
    pre = frozenset({(0, 0)})
    f2 = frozenset({(0, 0), (2, 2)})

    def _record(**headers) -> RecordedDifferential:
        return RecordedDifferential(headers=headers, v1_only=(), h2_only=())

    good_pre = _record(**{"v1 certified": 2, "holo2 certified": 1,
                          "v1 has, holo2 lacks": 1,
                          "holo2 has, v1 lacks": 0})
    good_f2 = _record(**{"v1 certified": 2, "holo2 certified": 2,
                         "v1 has, holo2 lacks": 1,
                         "holo2 has, v1 lacks": 1, "both": 1})
    crosscheck_headers(v1, pre, f2, good_pre, good_f2)
    bad_f2 = _record(**{"v1 certified": 2, "holo2 certified": 3,
                        "v1 has, holo2 lacks": 1,
                        "holo2 has, v1 lacks": 1, "both": 1})
    with pytest.raises(ValueError, match="F2: holo2 certified"):
        crosscheck_headers(v1, pre, f2, good_pre, bad_f2)


# --------------------------------------------------------------------
# clustering + split
# --------------------------------------------------------------------


def test_merge_gap_counts_empty_tiles():
    """Fork 2: gap N means Chebyshev distance N+1 still merges and N+2
    does not."""
    merged = cluster_targets([(0, 0), (3, 0)], merge_gap_tiles=2)
    assert len(merged) == 1 and merged[0].members == ((0, 0), (3, 0))
    apart = cluster_targets([(0, 0), (4, 0)], merge_gap_tiles=2)
    assert len(apart) == 2
    # gap 0 still merges adjacency (distance 1), on both axes at once
    diagonal = cluster_targets([(0, 0), (1, 1)], merge_gap_tiles=0)
    assert len(diagonal) == 1


def test_cluster_and_split_deterministic_full_coverage():
    """A long band splits into segments; every target lands in exactly
    one case; a second run is byte-identical (sorted construction)."""
    band = [(ty, 0) for ty in range(20)]           # 20 tiles = 1280 cells
    extra = [(5, 8), (30, 30)]
    targets = band + extra
    first = split_clusters(cluster_targets(targets, 2), max_span_cells=768)
    second = split_clusters(cluster_targets(targets, 2), max_span_cells=768)
    assert first == second
    got = sorted(t for c in first for t in c.members)
    assert got == sorted(targets)                  # exactly once, no loss
    for cluster in first:
        span_y, span_x = cluster.span_cells_yx
        assert max(span_y, span_x) <= 768
    # the 20-tile band became exactly ceil(1280/768) = 2 segments
    band_segments = [c for c in first if all(tx == 0 for _, tx in c.members)]
    assert len(band_segments) == 2


def test_split_handles_both_axes():
    block = [(ty, tx) for ty in range(0, 26, 2) for tx in range(0, 26, 2)]
    done = split_clusters(cluster_targets(block, 2), max_span_cells=768)
    assert sorted(t for c in done for t in c.members) == sorted(block)
    assert all(max(c.span_cells_yx) <= 768 for c in done)


# --------------------------------------------------------------------
# geometry: bbox order, rotation, the control rim
# --------------------------------------------------------------------


def test_cell_bbox_is_x_first_and_page_clipped():
    """Fork 3: the manifest bboxes are x-first on a taller-than-wide
    page — the numbers below only work unswapped."""
    cluster = Cluster.of([(0, 5)])                 # ty 0, tx 5
    bbox = cell_bbox_for(cluster, halo_cells=240, page_cells_yx=(3392, 2368))
    assert bbox == (5 * 64 - 240, 0, 6 * 64 + 240, 64 + 240)
    # x is clipped by the 2368 axis, y by the 3392 axis
    tall = Cluster.of([(52, 36)])
    assert cell_bbox_for(tall, 240, (3392, 2368)) == (
        36 * 64 - 240, 52 * 64 - 240, 2368, 3392)


def test_px_bbox_aabb_under_rotation_and_pad():
    """The affine handles orientation (the xerox scan is 180°-rotated):
    the crop is the AABB of the transformed rect, padded 32 cells."""
    affine = GlobalAffine(rows=((-16.0, 0.0, 40000.0),
                                (0.0, -16.0, 56000.0)),
                          n_poses=99, residual_median_px=0.0,
                          residual_p99_px=0.0, residual_max_px=0.0)
    assert affine.px_per_cell == pytest.approx(16.0)
    px = px_bbox_for((0, 0, 100, 200), affine, (60000, 42000))
    pad = 32 * 16
    assert px == (40000 - 1600 - pad, 56000 - 3200 - pad,
                  min(42000, 40000 + pad), min(60000, 56000 + pad))
    px0, py0, px1, py1 = px
    assert px0 < px1 and py0 < py1


def test_control_rim_rule_and_target_exclusion():
    """Fork 4: fully-inside-the-shrunk-bbox controls only, and never a
    target tile."""
    bbox = (0, 0, 640, 640)                        # rim-shrunk: 32..608
    both = frozenset({(1, 1), (0, 1), (1, 8), (1, 9), (2, 2)})
    targets = frozenset({(2, 2)})
    controls = controls_for(bbox, both, targets)
    assert (1, 1) in controls                      # 64..128 inside 32..608
    assert (0, 1) not in controls                  # y 0..64 crosses the rim
    assert (1, 8) in controls                      # x 512..576 <= 608
    assert (1, 9) not in controls                  # x 576..640 > 608
    assert (2, 2) not in controls                  # a target, never a control


# --------------------------------------------------------------------
# the manifest schema (Deliverable B's contract)
# --------------------------------------------------------------------


def _synthetic_manifest() -> dict:
    v1 = frozenset({(0, 0), (1, 1), (2, 2)})
    sets = compute_classes(v1, frozenset({(0, 0)}),
                           frozenset({(0, 0), (1, 1), (4, 4)}), (6, 6))
    cluster = Cluster.of(sorted(sets.targets))
    cell_bbox = cell_bbox_for(cluster, 240, (6 * 64, 6 * 64))
    affine = GlobalAffine(rows=((16.0, 0.0, 100.0), (0.0, 16.0, 200.0)),
                          n_poses=9, residual_median_px=0.0,
                          residual_p99_px=0.0, residual_max_px=0.0)
    px_bbox = px_bbox_for(cell_bbox, affine, (9000, 9000))
    ranks = {tile: "certified" if tile in {(1, 1), (4, 4)}
             else "attempted_failed" for tile in sets.targets}
    case = build_case_entry("syn-c01", cluster, cell_bbox, px_bbox, sets,
                            controls_for(cell_bbox, v1, sets.targets),
                            ranks, v1)
    return {
        "sheet": "syn", "capture_path": "/nowhere.tiff",
        "capture_sha256": "00" * 32, "scan_dpi": 4800,
        "format_ref": "L:c2-r0700@3392x2368",
        "tile_convention": crop_cases.TILE_CONVENTION,
        "cell_axes": crop_cases.CELL_AXES,
        "affine_cell_to_px": [list(row) for row in affine.rows],
        "halo_cells": 240,
        "generator": {"tree": "deadbeef", "dirty_sha": ""},
        "cases": [case],
    }


def test_manifest_round_trips_and_schema_is_exact():
    """Fork 5: the schema survives a JSON round-trip and refuses drift
    in either direction."""
    manifest = _synthetic_manifest()
    validate_manifest(manifest)
    rebuilt = json.loads(json.dumps(manifest))
    validate_manifest(rebuilt)
    assert rebuilt == manifest
    case = rebuilt["cases"][0]
    # the classes vocabulary is closed, and full_sheet uses
    # tile_differential's rank names JSON-cased (HANDOFF-CROP's example)
    for target in case["targets"]:
        assert target["classes"][0] in CLASS_NAMES
        assert target["full_sheet"]["v1"] in {"certified", "uncertified"}
    assert set(crop_cases.RANK_JSON.values()) == {
        "never_addressed", "addressed_not_attempted", "attempted_failed",
        "certified"}
    # v1_missing target reads v1-uncertified, h2-certified
    v1_missing = [t for t in case["targets"]
                  if t["classes"] == ["v1_missing"]]
    assert v1_missing and v1_missing[0]["full_sheet"] == {
        "v1": "uncertified", "h2": "certified"}

    extra = json.loads(json.dumps(manifest))
    extra["cases"][0]["note"] = "no"
    with pytest.raises(ValueError, match="syn-c01"):
        validate_manifest(extra)
    missing = json.loads(json.dumps(manifest))
    del missing["capture_sha256"]
    with pytest.raises(ValueError, match="manifest"):
        validate_manifest(missing)
    bad_class = json.loads(json.dumps(manifest))
    bad_class["cases"][0]["targets"][0]["classes"] = ["flippedd"]
    with pytest.raises(ValueError, match="classes"):
        validate_manifest(bad_class)


def test_parse_differential_md_reads_the_record(tmp_path):
    """The parser's contract on a miniature of the real reports: §B/§C
    tile lines are the record, §A headers must agree with them."""
    text = "\n".join([
        "# Tile differential — syn",
        "",
        "## (A) Certificate sets and their differences",
        "",
        "- v1 certified: **3**",
        "- holo2 certified: **2**",
        "- both: **1**",
        "- v1 has, holo2 lacks: **2**",
        "- holo2 has, v1 lacks: **1**",
        "- neither certifies: **0**",
        "- total tiles in domain: **4**",
        "",
        "## (B) v1 has, holo2 lacks (2 tiles)",
        "",
        "### page 0, tile (0, 1) (PAGE-EDGE)",
        "### page 0, tile (1, 0)",
        "",
        "## (C) holo2 has, v1 lacks (1 tiles)",
        "",
        "### page 0, tile (1, 1)",
        "",
        "## (D) Summary by class",
        "### page 0, tile (9, 9)",       # outside B/C: never parsed
        ""])
    path = tmp_path / "differential-syn.md"
    path.write_text(text, encoding="utf-8")
    record = crop_cases.parse_differential_md(path)
    assert record.v1_only == ((0, 1), (1, 0))
    assert record.h2_only == ((1, 1),)
    v1 = frozenset({(0, 0), (0, 1), (1, 0)})
    assert record.h2_set(v1) == {(0, 0), (1, 1)}
    # a header/section disagreement refuses
    path.write_text(text.replace("lacks: **2**", "lacks: **3**"),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="v1 has, holo2 lacks"):
        crop_cases.parse_differential_md(path)

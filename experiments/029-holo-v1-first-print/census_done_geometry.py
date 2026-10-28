#!/usr/bin/env python
"""DONE-GEOMETRY §8 census over the e029 durable state (read-only).

Two views per committed level of the ink-page session:

A. address-space redundancy (ground truth, durable state only): committed
   poses whose oriented page footprint was fully certified at level start —
   their placement + sampling produce was payload-redundant by then;
B. pixel-gate simulation (the DONE-GEOMETRY proposal): the done-pixel mask
   before level i is built ONLY from poses committed at barriers < i
   projected through their own ``native_affine`` onto tiles certified at
   barriers < i (conservative: tile bbox shrunk by QUAD_INSET grid cells
   per side).  A window/pose is "gated" when every supported grid cell of
   its native extent is done — i.e. the pose-free gate would have retired
   it before any route ran.  Planned-window boxes and route costs come from
   the diag events of the final invocation (levels 4-11, the M/R tail);
   earlier invocations' event logs were replaced, so levels 0-3 report the
   durable-pose view only.

Conservatisms (all bias AGAINST gating): tile quads enter the mask as
inset bboxes; window boxes are outset to whole grid cells; support-grid
origins round down.  Nothing here mutates state.

Usage (repo root):
  PYTHONPATH=src env/bin/python \
      experiments/029-holo-v1-first-print/census_done_geometry.py
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_erosion

from holo.receive.session import load_session

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "scratch/e028/holo-c2-r0700-q07-ink-counting"
OUT = Path(__file__).with_name("DONE-GEOMETRY-CENSUS.json")
GRID = 16          # native px per mask cell (= one c2 cell at 4800 dpi)
QUAD_INSET = 1     # grid cells shrunk per side when marking a done tile
TILE = 64


def oriented_shape(pose) -> tuple[int, int]:
    h, w = pose.window_shape_yx_cells
    return (w, h) if pose.rot90 in (1, 3) else (h, w)


def tiles_of(pose) -> set[tuple[int, int]]:
    """Covered tile set of the oriented window footprint (v0.45 convention)."""
    oy, ox = pose.cell_origin_yx
    h, w = oriented_shape(pose)
    return {(ty, tx)
            for ty in range(oy // TILE, (oy + h - 1) // TILE + 1)
            for tx in range(ox // TILE, (ox + w - 1) // TILE + 1)}


def native_bbox(affine, y0, x0, y1, x1):
    """Page-cell rectangle corners through the row-major 2x3 native affine."""
    a, b, c, d, e, f = affine
    ys = [a * cy + b * cx + c for cy, cx in
          ((y0, x0), (y0, x1), (y1, x0), (y1, x1))]
    xs = [d * cy + e * cx + f for cy, cx in
          ((y0, x0), (y0, x1), (y1, x0), (y1, x1))]
    return min(ys), min(xs), max(ys), max(xs)


def main() -> None:
    state = load_session(RUN / "receive.state",
                         defer_fountain_validation=True)
    cap = state.captures[0]
    plan = cap.plan
    lane_index = {lane.lane_id: i for i, lane in enumerate(plan)}
    npv = {lane.lane_id: lane.native_per_view_num / lane.native_per_view_den
           for lane in plan}
    cert_by_id = {c.certificate_id: c for c in state.certificates}

    # Per-level minted addresses, in durable barrier order.
    minted = [
        {(cert_by_id[i].page, *cert_by_id[i].tile_yx)
         for i in (level.payload.certificate_ids if level.payload else ())}
        for level in cap.levels
    ]
    certified_before, seen = [], set()
    for level_minted in minted:
        certified_before.append(frozenset(seen))
        seen |= level_minted

    poses_by_level: dict[int, list] = defaultdict(list)
    for pose in state.poses:
        poses_by_level[lane_index[pose.lane_id]].append(pose)

    # Support masks on the shared native grid, one per ordinary lane.
    gh = -(-cap.shape_yx[0] // GRID)
    gw = -(-cap.shape_yx[1] // GRID)
    support: dict[str, np.ndarray] = {}
    region_origin: dict[str, tuple[int, int]] = {}
    for region in state.regions:
        scale = npv[region.lane_id]
        if abs(region.support_step_px * scale - GRID) > 1e-9:
            raise SystemExit("support step does not project onto the grid")
        grid = np.zeros(region.support_shape_yx, bool)
        flat = grid.reshape(-1)
        for run in region.support_runs:
            flat[run.start:run.start + run.length] = True
        full = np.zeros((gh, gw), bool)
        oy = int(region.origin_yx[0] * scale // GRID)
        ox = int(region.origin_yx[1] * scale // GRID)
        view = full[oy:oy + grid.shape[0], ox:ox + grid.shape[1]]
        view[:] = grid[:view.shape[0], :view.shape[1]]
        support[region.lane_id] = full
        region_origin[region.lane_id] = region.origin_yx

    def build_mask(level: int) -> np.ndarray:
        """Done-pixel mask at level start: barriers < level only.

        Tile bboxes are marked un-inset, then the UNION is eroded by
        QUAD_INSET grid cells (skew guard at the union boundary without
        manufacturing undone seams between adjacent done tiles).
        """
        mask = np.zeros((gh, gw), bool)
        done = certified_before[level]
        for j in range(level):
            for pose in poses_by_level.get(j, []):
                for ty, tx in tiles_of(pose):
                    if (pose.page, ty, tx) not in done:
                        continue
                    y0, x0, y1, x1 = native_bbox(
                        pose.native_affine, ty * TILE, tx * TILE,
                        (ty + 1) * TILE, (tx + 1) * TILE)
                    # Round-to-nearest edges: adjacent done tiles share the
                    # rounded edge (no phantom seams); the union erosion
                    # below supplies the conservative margin.
                    gy0, gx0 = round(y0 / GRID), round(x0 / GRID)
                    gy1, gx1 = round(y1 / GRID), round(x1 / GRID)
                    if gy1 > gy0 and gx1 > gx0:
                        mask[max(gy0, 0):gy1, max(gx0, 0):gx1] = True
        if QUAD_INSET:
            mask = binary_erosion(mask, iterations=QUAD_INSET)
        return mask

    def gated(mask: np.ndarray, base_lane: str, box) -> bool:
        """All supported grid cells of the native box are done."""
        y0, x0, y1, x1 = box
        gy0, gx0 = max(int(y0 // GRID), 0), max(int(x0 // GRID), 0)
        gy1 = min(int(np.ceil(y1 / GRID)), gh)
        gx1 = min(int(np.ceil(x1 / GRID)), gw)
        if gy1 <= gy0 or gx1 <= gx0:
            return False
        window = np.s_[gy0:gy1, gx0:gx1]
        supported = support[base_lane][window]
        return bool(supported.any()) and bool(mask[window][supported].all())

    # Tail-invocation diag events: planned windows, route spend, outcomes.
    windows_by_level: dict[int, dict[tuple, dict]] = defaultdict(dict)
    events_path = RUN / "receive.state.diag/events.jsonl"
    for line in events_path.open():
        event = json.loads(line)
        name, details = event["name"], event["details"]
        lane = event["context"].get("lane_id")
        if lane is None or not name.startswith("address."):
            continue
        level = lane_index[lane]
        key = (details.get("address.region"), details.get("address.window"))
        rows = windows_by_level[level]
        if name == "address.window_planned":
            rows[key] = {"box": (details["address.box_y"],
                                 details["address.box_x"],
                                 details["address.box_h"],
                                 details["address.box_w"]),
                         "word_rest": 0, "cold": 0, "outcome": None}
        elif key in rows:
            row = rows[key]
            if name == "address.word_rest_open":
                row["word_rest"] += 1
            elif name == "address.cold_open":
                row["cold"] += 1
            elif name == "address.window_resolved":
                row["outcome"] = details.get("address.outcome")

    report_rows = []
    for i, lane in enumerate(plan):
        mask = build_mask(i)
        done = certified_before[i]
        kind = "M" if lane.mopup_of else ("R" if lane.refine_of else "L")
        base = lane.base_lane_id

        full = partial = live = pose_gated = 0
        for pose in poses_by_level.get(i, []):
            tiles = tiles_of(pose)
            hit = sum((pose.page, ty, tx) in done for ty, tx in tiles)
            full += hit == len(tiles)
            partial += 0 < hit < len(tiles)
            live += hit == 0
            oy, ox = pose.cell_origin_yx
            h, w = oriented_shape(pose)
            if gated(mask, base,
                     native_bbox(pose.native_affine, oy, ox, oy + h, ox + w)):
                pose_gated += 1

        events = {"windows": 0, "gated": 0, "gated_accepted": 0,
                  "cold": 0, "gated_cold": 0,
                  "word_rest": 0, "gated_word_rest": 0}
        origin = region_origin[base]
        scale = npv[base]
        for row in windows_by_level.get(i, {}).values():
            by, bx, bh, bw = row["box"]
            box = ((origin[0] + by) * scale, (origin[1] + bx) * scale,
                   (origin[0] + by + bh) * scale,
                   (origin[1] + bx + bw) * scale)
            hit = gated(mask, base, box)
            events["windows"] += 1
            events["cold"] += row["cold"]
            events["word_rest"] += row["word_rest"]
            if hit:
                events["gated"] += 1
                events["gated_cold"] += row["cold"]
                events["gated_word_rest"] += row["word_rest"]
                events["gated_accepted"] += row["outcome"] == "accepted"

        report_rows.append({
            "level": i, "lane": lane.lane_id, "kind": kind,
            "certified_before": len(done), "minted": len(minted[i]),
            "attempts": (cap.levels[i].payload.n_attempts
                         if cap.levels[i].payload else 0),
            "poses": len(poses_by_level.get(i, [])),
            "a_fully_done": full, "a_partially_done": partial,
            "a_live": live, "b_poses_gated": pose_gated,
            "events": events,
        })

    totals = {
        "poses": sum(r["poses"] for r in report_rows),
        "a_fully_done": sum(r["a_fully_done"] for r in report_rows),
        "b_poses_gated": sum(r["b_poses_gated"] for r in report_rows),
        "tail_windows": sum(r["events"]["windows"] for r in report_rows),
        "tail_windows_gated": sum(r["events"]["gated"] for r in report_rows),
        "tail_cold": sum(r["events"]["cold"] for r in report_rows),
        "tail_cold_gated": sum(r["events"]["gated_cold"]
                               for r in report_rows),
        "tail_word_rest": sum(r["events"]["word_rest"] for r in report_rows),
        "tail_word_rest_gated": sum(r["events"]["gated_word_rest"]
                                    for r in report_rows),
    }
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    OUT.write_text(json.dumps(
        {"state": str(RUN / "receive.state"),
         "state_sha256": sha256(RUN / "receive.state"),
         "events_sha256": sha256(events_path),
         "grid_px": GRID,
         "quad_inset": QUAD_INSET, "status": state.status.value,
         "levels": report_rows, "totals": totals}, indent=1))

    header = (f"{'lvl':>3} {'lane':21} {'k':1} {'cert<':>5} {'mint':>4} "
              f"{'att':>4} {'poses':>5} {'A:full':>6} {'A:part':>6} "
              f"{'B:gated':>7} {'win':>4} {'winG':>4} {'accG':>4} "
              f"{'cold G/T':>9} {'rest G/T':>9}")
    print(header)
    print("-" * len(header))
    for r in report_rows:
        e = r["events"]
        print(f"{r['level']:>3} {r['lane']:21} {r['kind']} "
              f"{r['certified_before']:>5} {r['minted']:>4} "
              f"{r['attempts']:>4} {r['poses']:>5} {r['a_fully_done']:>6} "
              f"{r['a_partially_done']:>6} {r['b_poses_gated']:>7} "
              f"{e['windows']:>4} {e['gated']:>4} {e['gated_accepted']:>4} "
              f"{e['gated_cold']:>4}/{e['cold']:<4} "
              f"{e['gated_word_rest']:>4}/{e['word_rest']:<4}")
    print(f"\nTOTALS  poses={totals['poses']} "
          f"A:fully-done-at-start={totals['a_fully_done']} "
          f"B:pixel-gated={totals['b_poses_gated']}  |  tail windows "
          f"{totals['tail_windows_gated']}/{totals['tail_windows']} gated, "
          f"colds {totals['tail_cold_gated']}/{totals['tail_cold']}, "
          f"word-rests {totals['tail_word_rest_gated']}/"
          f"{totals['tail_word_rest']} on gated windows")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()

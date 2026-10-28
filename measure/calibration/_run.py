"""E9 (K instance) driver: one ladder lane, five arms, twenty-one tiles.

Per lane the expensive work happens once — derive the lane raster,
re-derive the committed poses (`place.place_committed`, the production
R-level inventory), sample every window (`payload.collect_capture_evidence`)
— and then each arm only refits the marginal head, re-runs the region
context arm, re-freezes ownership, re-materializes the residue blocks and
re-attempts.  The certificate gate is the ordinary one: an attempt that
certifies is taken, an attempt that fails changes nothing, and the
archived state is never written.
"""
from __future__ import annotations

import gc
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import _inputs
from ._arms import ARM_IDS, apply_arm, build_label_pool, context_and_freeze

RESIDUE_STAGES = ("scan", "retry150")


def _rss_gb() -> float:
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1 << 30)             # darwin reports bytes


def _block_stats(block, gt: np.ndarray) -> dict[str, object]:
    observed = block.observed_cells()
    llr = block.cell_tensor().reshape(64, 64)
    ty, tx = block.tile_yx
    truth = gt[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
    decision = (llr > 0).astype(np.uint8)
    wrong = int(np.count_nonzero((decision != truth) & observed))
    n = int(observed.sum())
    return {
        "n_observed": n,
        "n_wrong": wrong,
        "ber": wrong / n if n else float("nan"),
        "mean_abs_llr": float(np.abs(llr[observed]).mean()) if n else 0.0,
    }


def _attempt(block, spec, address, source_sha256, lane_id, gt):
    """The ordinary certificate gate, at both K stages."""
    from holo.receive.evidence import AttemptStage
    from holo.receive.evidence_blocks import tile_attempt_view
    from holo.receive.payload import attempt_k_tile
    from holo.receive.records import printed_cells_from_record

    view = tile_attempt_view((block,))
    out: dict[str, object] = dict(_block_stats(block, gt))
    certified = False
    for stage_name, stage in (("scan", AttemptStage.SCAN),
                              ("retry150", AttemptStage.RETRY150)):
        started = time.process_time()
        record, certificate = attempt_k_tile(
            view.llr_cells_f64, spec, address, stage,
            source_sha256=source_sha256, lane_id=lane_id,
            component_block_ids=view.component_block_ids)
        out[f"{stage_name}_state"] = str(record.state.value)
        out[f"{stage_name}_iters"] = int(record.n_iters)
        out[f"{stage_name}_seconds"] = time.process_time() - started
        out[f"{stage_name}_certified"] = certificate is not None
        if certificate is not None:
            certified = True
            # Zero-wrong audit: a certificate must re-encode to the
            # emitted page, cell for cell.
            printed = np.asarray(
                printed_cells_from_record(certificate, spec)).reshape(64, 64)
            ty, tx = address[1], address[2]
            truth = gt[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
            out[f"{stage_name}_audit_wrong_cells"] = int(
                np.count_nonzero(printed.astype(np.uint8) != truth))
            break
    out["certified"] = certified
    return out


def run_lane(state, spec, truth, residue, lane, capture, *,
             verify_archived: bool) -> dict[str, object]:
    """Everything E9 measures at one ladder lane."""
    from holo.receive.evidence_blocks import blocks_from_frontier
    from holo.receive.payload import collect_capture_evidence
    from holo.receive.payload_model import EvidenceSource
    from holo.receive.place import place_committed

    lane_id = lane.lane_id
    report: dict[str, object] = {"lane_id": lane_id}
    wall = time.time()

    lane_raster = _inputs.open_lane_raster(lane, capture)
    report["raster_shape"] = list(lane_raster.shape)
    report["raster_dpi"] = lane_raster.dpi
    report["decimate_wall_s"] = time.time() - wall

    poses = tuple(row for row in state.poses if row.lane_id == lane_id)
    regions = tuple(row for row in state.regions if row.lane_id == lane_id)
    started = time.time()
    address = place_committed(
        lane_raster.raster, spec, poses=poses, regions=regions)
    report["n_committed_poses"] = len(poses)
    report["n_placements"] = len(address.payload_placements)
    report["place_wall_s"] = time.time() - started

    source = EvidenceSource(capture.source_sha256, lane_id)
    started = time.time()
    baseline = collect_capture_evidence(
        lane_raster.raster, source, address, spec)
    report["n_windows"] = len(baseline.windows)
    report["sample_wall_s"] = time.time() - started
    lane_raster.release()
    gc.collect()

    archived = {row.address: row for row in state.blocks
                if row.lane_id == lane_id}

    pool = build_label_pool(baseline.windows, spec, truth.certified)
    report["n_pool_rows"] = int(pool.site_id.size)
    report["n_pool_labels"] = int((pool.label >= 0).sum())
    report["n_pool_furniture"] = int(pool.furniture.sum())

    arms: dict[str, object] = {}
    for arm in ARM_IDS:
        wall_arm = time.time()
        cpu_arm = time.process_time()
        rows, fits, fit_cpu = apply_arm(baseline.windows, pool, arm)
        frontier, decisions = context_and_freeze(rows, source, spec)
        # No terminal pruning: the certified tiles' blocks are the page-wide
        # BER map (the spatial story, and the check that an arm does not
        # quietly ruin the population the incumbent already closed).  The
        # residue's blocks are identical either way — production prunes
        # AFTER the owner freeze.
        blocks = {row.address: row for row in blocks_from_frontier(frontier)}
        del rows, frontier
        gc.collect()
        tiles: dict[str, object] = {}
        attempt_cpu = 0.0
        for entry in residue:
            block = blocks.get(entry)
            if block is None:
                tiles[str(entry)] = {"n_observed": 0, "certified": False,
                                     "reason": "no_evidence"}
                continue
            row = _attempt(block, spec, entry, capture.source_sha256,
                           lane_id, truth.gt)
            attempt_cpu += float(row.get("scan_seconds", 0.0)) + float(
                row.get("retry150_seconds", 0.0))
            tiles[str(entry)] = row
        exact = None
        if arm == "R" and verify_archived:
            exact = _verify_against_archived(blocks, archived, residue)
        page = {}
        for address, block in blocks.items():
            stats = _block_stats(block, truth.gt)
            page[str(address)] = [stats["n_observed"], stats["n_wrong"]]
        arms[arm] = {
            "fit_cpu_s": fit_cpu,
            "arm_cpu_s": time.process_time() - cpu_arm,
            "arm_wall_s": time.time() - wall_arm,
            "attempt_cpu_s": attempt_cpu,
            "n_certified": sum(
                1 for row in tiles.values() if row.get("certified")),
            "context": [
                {"region_id": row.region_id, "eligible": bool(row.eligible),
                 "adopted": bool(row.adopted), "reason": row.reason,
                 "offsets": [float(value) for value in row.offsets]}
                for row in decisions],
            "windows": [asdict(row) for row in fits],
            "tiles": tiles,
            "page_ber": page,
            "archived_agreement": exact,
        }
        del blocks
        gc.collect()
    report["arms"] = arms
    report["lane_wall_s"] = time.time() - wall
    report["peak_rss_gb"] = _rss_gb()
    return report


def _verify_against_archived(blocks, archived, residue) -> dict[str, object]:
    """Arm R must reproduce the archived evidence bit for bit."""
    same = 0
    total = 0
    missing: list[str] = []
    for entry in residue:
        mine, theirs = blocks.get(entry), archived.get(entry)
        if mine is None or theirs is None:
            missing.append(f"{entry}:{'mine' if mine else '-'}/"
                           f"{'archived' if theirs else '-'}")
            continue
        both = mine.observed_cells() & theirs.observed_cells()
        left = mine.cell_tensor().reshape(64, 64)[both]
        right = theirs.cell_tensor().reshape(64, 64)[both]
        total += int(both.sum())
        same += int(np.count_nonzero(left == right))
    return {"cells_compared": total, "cells_bit_identical": same,
            "missing": missing}


def run(lanes: tuple[str, ...], out_dir: Path, *,
        verify_archived: bool = True) -> dict[str, object]:
    from holo.receive.tiles import k_eff_bits

    started = time.time()
    state = _inputs.load_state()
    spec = _inputs.format_spec()
    capture = state.captures[0]
    truth = _inputs.load_truth(state, spec)
    residue = _inputs.residue_addresses(state, spec)
    plan = {row.lane_id: row for row in capture.plan}
    unknown = [lane for lane in lanes if lane not in plan]
    if unknown:
        raise SystemExit(f"state has no lane(s): {unknown}")

    raw: dict[str, object] = {
        "instrument": "measure/calibration (E9, K instance)",
        "provenance_entry": _inputs.provenance(),
        "spec_id": spec.spec_id,
        "format_row_id": state.format_row_id,
        "receiver_policy_id": state.receiver_policy_id,
        "close_status": str(state.close.status.value),
        "n_certificates": len(state.certificates),
        "tiles_yx": list(spec.layout.tiles_yx),
        "cells_yx": list(spec.layout.cells_yx),
        "n_filler": int(spec.n_filler),
        "k_eff_bits": int(k_eff_bits(spec)),
        "payload_cells_per_tile": int(spec.payload_cells),
        "truth_path": {
            "certified_tiles": truth.n_certified_tiles,
            "cells_checked": truth.n_checked_cells,
            "cells_mismatched": truth.n_mismatched_cells,
        },
        "residue": [list(entry) for entry in residue],
        "lanes": {},
    }
    for lane_id in lanes:
        raw["lanes"][lane_id] = run_lane(          # type: ignore[index]
            state, spec, truth, residue, plan[lane_id], capture,
            verify_archived=verify_archived)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "e9-k-raw.json").write_text(
            json.dumps(raw, indent=1, sort_keys=False))
    raw["total_wall_s"] = time.time() - started
    raw["provenance_exit"] = _inputs.provenance()
    (out_dir / "e9-k-raw.json").write_text(
        json.dumps(raw, indent=1, sort_keys=False))
    return raw


__all__ = ["run", "run_lane"]

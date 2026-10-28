"""Extract the four panels per tile for the dead-vs-GT figure.

READ-ONLY.  Reuses the plane-fields instruments exactly as
``_gt_affine_run.run`` does (same state, same lane, same targets on the
same seed, same restricted-region fit), so the numbers this stage
produces are the ones already recorded in gt-affine-final2.json.

Stage 1 of 2: writes panels.npz + panels.json into
``scratch/plane-fields/gt-affine/``; the renderer
(``plane_fields.render_panels``) never touches a scan or a state.

    cd <repo>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.extract_panels
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

REPO = Path("<repo>")
OUT = REPO / "scratch" / "plane-fields" / "gt-affine"
RESULTS = OUT / "gt-affine-final2.json"

#: The capture rendered.  The primary 2400 dpi Canon scan of sheet I --
#: the one whose restricted region adopted the A1 residual head.
PRIMARY = "269d81217ec48a5e57ae5736baf091f0afe3f66dd15539c0f39dfc6cffdea30c"

#: (tile_y, tile_x, plane_name) -- three dead-band residue tiles that
#: never certified, plus the withheld certified reproduction control.
PANEL_TILES = (
    (14, 9, "Y"),
    (29, 8, "Y"),
    (47, 28, "Y"),
    (24, 20, "Y"),
)
#: the healthy plane on the same pixels, for the companion figure
COMPANION = (14, 9, "C")

PLANE_NAMES = ("C", "M", "Y")
SUB = 8               # pixels per cell in the resampled scanner crop
TILE_CELLS = 64


def affine_from_parameters(params: dict):
    from ._affine_fit import Affine

    tx, ty = params["translation_dots_xy"]
    m = params["m_dots_per_cell"]
    return Affine(float(tx), float(ty),
                  ((float(m[0][0]), float(m[0][1])),
                   (float(m[1][0]), float(m[1][1]))))


def cell_to_scan(cell_yx: np.ndarray, points_yx: np.ndarray) -> np.ndarray:
    """Least-squares (cy, cx, 1) -> (py, px); the map is exactly affine."""
    design = np.column_stack([
        cell_yx[:, 0].astype(np.float64),
        cell_yx[:, 1].astype(np.float64),
        np.ones(cell_yx.shape[0], np.float64)])
    solution, *_ = np.linalg.lstsq(design, points_yx, rcond=None)
    residual = float(np.abs(design @ solution - points_yx).max())
    return solution, residual


def resample_tile_rgb(sampler, raster) -> dict:
    """The tile's own pixels, deskewed onto a 512 x 512 grid.

    The ONLY geometric operation is the committed pose itself: each
    covered cell's 8 x 8 pixel neighbourhood is read at order-1 from the
    NATIVE (unfiltered) RGB crop at the pose's own sampling points.  No
    tone curve, no sharpening, no per-tile stretch.
    """
    from holo.receive.color_sampling import native_crop

    size = TILE_CELLS * SUB
    image = np.zeros((size, size, 3), np.float64)
    filled = np.zeros((TILE_CELLS, TILE_CELLS), np.int16)
    offsets = (np.arange(SUB) + 0.5) / SUB - 0.5
    order = sorted(range(len(sampler.rows)),
                   key=lambda i: -sampler.rows[i].select.size)
    residuals = []
    seams = []
    for rank, index in enumerate(order):
        row = sampler.rows[index]
        solution, residual = cell_to_scan(row.cell_yx, row.points)
        residuals.append(residual)
        want = [tuple(int(v) for v in cell) for cell in row.cell_yx]
        todo = [cell for cell in want if filled[cell] == 0]
        if not todo:
            continue
        seams.append({"window_ordinal": int(row.ordinal),
                      "rank": rank, "cells_filled": len(todo),
                      "affine_residual_px": residual})
        points = []
        for cell in todo:
            mesh_y, mesh_x = np.meshgrid(cell[0] + offsets,
                                         cell[1] + offsets, indexing="ij")
            points.append(np.column_stack([mesh_y.reshape(-1),
                                           mesh_x.reshape(-1)]))
        cell_points = np.concatenate(points)
        design = np.column_stack([
            cell_points[:, 0], cell_points[:, 1],
            np.ones(cell_points.shape[0], np.float64)])
        scan = design @ solution
        y0, x0, raw = native_crop(raster, scan, 4)
        local = scan - np.asarray((y0, x0), np.float64)
        values = np.stack([
            ndimage.map_coordinates(raw[..., channel], local.T, order=1,
                                    mode="nearest", output=np.float64)
            for channel in range(3)], axis=1)
        values = values.reshape(len(todo), SUB, SUB, 3)
        for k, cell in enumerate(todo):
            cy, cx = cell
            image[cy * SUB:(cy + 1) * SUB,
                  cx * SUB:(cx + 1) * SUB, :] = values[k]
            filled[cy, cx] = rank + 1
    return {"image": image, "filled": filled, "seams": seams,
            "pose_residual_px_max": max(residuals) if residuals else None,
            "dtype": str(np.asarray(raster.crop_native(0, 2, 0, 2)).dtype)}


def sampled_grid(sampler, plane: int, affine) -> tuple[np.ndarray, np.ndarray]:
    """The receiver's own per-cell samples, folded onto the 64 x 64 grid."""
    values = sampler.sample(plane, affine)
    total = np.zeros((TILE_CELLS, TILE_CELLS), np.float64)
    count = np.zeros((TILE_CELLS, TILE_CELLS), np.int32)
    np.add.at(total, (sampler.cell_yx[:, 0], sampler.cell_yx[:, 1]), values)
    np.add.at(count, (sampler.cell_yx[:, 0], sampler.cell_yx[:, 1]), 1)
    grid = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    return grid, count


def main() -> int:
    from . import _swim_inputs, _swim_region, _swim_truth
    from ._affine_fit import TileSampler
    from ._gt_affine_run import _fit_for
    from ._swim_inputs import FORMAT_REF, QUAL_STATE
    from ._swim_setup import (
        PAGE,
        LaneRasters,
        build_placements,
        certified_index,
        choose_lane,
        restricted_placements,
        select_controls,
        select_targets,
    )
    from .gt_affine import (
        capture_blocks_at,
        mismatch_map,
        tile_truth_planes,
    )
    from holo.format import pilots
    from holo.format.resolve import resolve_format_ref
    from holo.receive.payload_model import EvidenceSource

    started = time.time()
    results = json.loads(RESULTS.read_text())
    by_tile = {(row["tile_y"], row["tile_x"]): row
               for row in results["targets"] if "error" not in row}

    facts = _swim_inputs.read_facts()
    spec = resolve_format_ref(FORMAT_REF)
    scans = _swim_inputs.verified_scan_paths()
    index = certified_index(facts.certificates)
    targets = select_targets(index, spec.layout.tiles_yx, n_tiles=10,
                             n_clear=3, n_controls=2, seed=20260821)
    lane, coverage = choose_lane(facts, targets, forced=None)
    targets = targets + select_controls(facts, index, lane, targets, count=2,
                                        radius=3, seed=20260821)
    withheld = frozenset(
        (*row.address, row.stream) for row in targets
        if row.role.startswith("reproduction-control"))
    fit_certificates = tuple(
        row for row in facts.certificates
        if (int(row.page), *(int(v) for v in row.tile_yx), row.stream_id)
        not in withheld)
    print(f"state {facts.state_sha256[:12]}... {facts.close_status} "
          f"certs {len(facts.certificates)} lane {lane.lane_id} "
          f"coverage {coverage}")
    print("targets: " + ", ".join(
        f"{row.tile_y},{row.tile_x}/{row.stream}" for row in targets))

    capture = next(row for row in facts.captures
                   if row.source_sha256 == PRIMARY)
    mark = time.time()
    holder = LaneRasters(spec, capture, scans[PRIMARY])
    raster = holder.for_lane(lane)
    placements, _poses = build_placements(facts, spec, capture, lane, raster)
    grouped = restricted_placements(placements, targets, 3)
    source = EvidenceSource(capture.source_sha256, lane.lane_id)
    keep = frozenset(row.address for row in targets)
    by_region = {}
    for region_index, patches in sorted(grouped.items()):
        region_id = (f"{capture.source_sha256}/{lane.lane_id}/"
                     f"region-{region_index}/page-{PAGE}")
        by_region[region_index] = _swim_region.fit_region(
            spec, raster, source, patches, fit_certificates, PAGE, region_id,
            keep_features_for=keep)
    fits = {PRIMARY: by_region}
    print(f"  setup {time.time() - mark:.0f}s; regions " + ", ".join(
        f"{key}:{value.n_windows}w/{value.n_labels}l"
        f"{'*' if value.adopted else ''}"
        for key, value in sorted(by_region.items())))

    payload = (QUAL_STATE.parent / "recovered.bin").read_bytes()
    truth_bits, truth_report = _swim_truth.page_component_bits(
        spec, payload, 0.9, PAGE)
    validation = _swim_truth.validate_against_certificates(
        truth_bits, spec, facts.certificates, sample=24)
    if not validation.get("exact"):
        raise SystemExit(f"truth field REFUSED: {validation}")
    print(f"  truth field exact on {validation['checked']} certified tiles")

    payload_indices = pilots.color_payload_cell_indices(spec.family_seed)
    payload_mask = np.zeros(TILE_CELLS * TILE_CELLS, bool)
    payload_mask[payload_indices] = True
    payload_mask = payload_mask.reshape(TILE_CELLS, TILE_CELLS)

    arrays: dict[str, np.ndarray] = {"payload_mask": payload_mask}
    meta: dict = {
        "capture_sha256": PRIMARY,
        "capture_path": str(scans[PRIMARY]),
        "lane": lane.lane_id,
        "state_sha256": facts.state_sha256,
        "payload_sha256": facts.payload_sha256,
        "format": results["format"],
        "px_per_cell": SUB,
        "truth": truth_report,
        "validation": validation,
        "tiles": [],
    }

    wanted = list(PANEL_TILES) + [COMPANION]
    seen: dict[tuple[int, int], dict] = {}
    for tile_y, tile_x, plane_name in wanted:
        key = (tile_y, tile_x)
        address = (PAGE, tile_y, tile_x)
        plane = PLANE_NAMES.index(plane_name)
        row = by_tile[key]
        tag = f"{tile_y:02d}-{tile_x:02d}"
        found = _fit_for(fits, PRIMARY, address)
        if found is None:
            raise SystemExit(f"tile {address}: no window in the region")
        fit, ordinals = found
        mark = time.time()
        if key not in seen:
            sampler = TileSampler(fit, raster, spec, address, ordinals)
            null = sampler.null_proof(raster)
            crop = resample_tile_rgb(sampler, raster)
            tile_bits = tile_truth_planes(truth_bits, address)
            affines = tuple(
                affine_from_parameters(
                    row["fits"]["by_capture"][PRIMARY][name]["affine_fit"][
                        "parameters"])
                for name in PLANE_NAMES)
            blocks = capture_blocks_at(fit, raster, spec, address, ordinals,
                                       affines)
            blocks0 = capture_blocks_at(fit, raster, spec, address, ordinals,
                                        (None, None, None))
            grids = {}
            counts = {}
            for p in range(3):
                grids[p], counts[p] = sampled_grid(sampler, p, affines[p])
            arrays[f"rgb_{tag}"] = crop["image"].astype(np.float32)
            arrays[f"filled_{tag}"] = crop["filled"]
            arrays[f"gt_{tag}"] = tile_bits.astype(np.uint8)
            for p, name in enumerate(PLANE_NAMES):
                arrays[f"sampled_{tag}_{name}"] = grids[p].astype(np.float32)
                arrays[f"count_{tag}_{name}"] = counts[p]
            seen[key] = {
                "tile_bits": tile_bits, "blocks": blocks, "blocks0": blocks0,
                "crop": crop, "null": null, "affines": affines,
                "windows": len(ordinals),
            }
        cached = seen[key]
        truth_flat = cached["tile_bits"].reshape(-1, 3)[payload_indices][:,
                                                                        plane]
        mis = mismatch_map(cached["blocks"], spec, address, plane,
                           payload_indices, truth_flat)
        mis0 = mismatch_map(cached["blocks0"], spec, address, plane,
                            payload_indices, truth_flat)
        arrays[f"err_{tag}_{plane_name}"] = mis["_grid"].astype(np.uint8)
        arrays[f"valid_{tag}_{plane_name}"] = mis["_valid"]
        arrays[f"err0_{tag}_{plane_name}"] = mis0["_grid"].astype(np.uint8)
        fitted = row["fits"]["by_capture"][PRIMARY]
        entry = {
            "tile_y": tile_y, "tile_x": tile_x, "plane": plane_name,
            "tag": tag,
            "band": row["band"], "role": row["role"],
            "stream_of_record": row["stream"],
            "windows": cached["windows"],
            "null_proof": cached["null"],
            "pose_residual_px_max": cached["crop"]["pose_residual_px_max"],
            "seams": cached["crop"]["seams"],
            "raw_dtype": cached["crop"]["dtype"],
            "capture_ber_at_affine": mis["ber"],
            "capture_ber_at_zero": mis0["ber"],
            "capture_errors_at_affine": mis["errors"],
            "capture_observed": mis["observed"],
            "union_ber_at_affine": row["configurations"]["affine"][
                "union_ber"] if plane_name == row["stream"] else None,
            "union_ber_at_zero": row["configurations"]["zero"][
                "union_ber"] if plane_name == row["stream"] else None,
            "certified_at_affine": bool(
                row["configurations"]["affine"]["verdict"].get("certified")
            ) if plane_name == row["stream"] else None,
            "certified_in_state": plane_name in row["siblings_certified"]
            if "siblings_certified" in row else None,
            "separation": fitted[plane_name]["separation_at_affine"],
            "oracle": fitted[plane_name]["oracle_threshold_at_affine"],
            "ink_fraction": fitted[plane_name]["ink_fraction"],
            "affine_parameters": fitted[plane_name]["affine_fit"][
                "parameters"],
            "affine_parameters_all_planes": {
                name: fitted[name]["affine_fit"]["parameters"]
                for name in PLANE_NAMES},
        }
        meta["tiles"].append(entry)
        print(f"  {tile_y:>2},{tile_x:<2} {plane_name} [{row['band']}/"
              f"{row['role']}] BER {mis0['ber']:.4f} -> {mis['ber']:.4f} "
              f"(capture) d'={entry['separation']['d_prime']:.2f} "
              f"[{time.time() - mark:.0f}s]")

    holder.release()
    del truth_bits
    np.savez_compressed(OUT / "panels.npz", **arrays)
    meta["wall_seconds"] = round(time.time() - started, 1)
    (OUT / "panels.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {OUT / 'panels.npz'} and panels.json "
          f"({meta['wall_seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""CASE GENERATION — crops cut from the archived scans around the gap.

    cd <checkout>
    PYTHONPATH=. env314t/bin/python -m measure.crop_parity.cases \\
        --volume e029 --volume xerox-k

WHAT IT PRODUCES, per volume, under ``scratch/crop-parity/<volume>/``:

* ``cases.json`` — the manifest the harness reads (schema validated on
  write, so a harness coded against it cannot be surprised).
* ``<case_id>-<capture_ordinal>.tiff`` — crops at NATIVE capture pixels
  (no resample, no dtype change), one per capture.
* ``cases-census.md`` — per-class counts with the recorded cross-check
  numbers, the affine fit and its residuals, per-case sizes and controls.

THE PIPELINE. The gap sets come from ``_volumes`` (recomputed from the
two primaries, cross-checked against the recorded parity record); the
targets are the selected classes' addresses; their TILE POSITIONS are
clustered and split; each cluster's cell rectangle gets a halo; the
per-capture affine turns that into a pixel AABB with 32 cells of pad;
and the crop is a windowed read off a read-only memmap.

GROUND TRUTH IS VALIDATED HERE TOO, before any crop is written: the
volume's golden payload is re-encoded through holo1 generation and
checked against every certificate in the archived holo1 state. A
volume whose GT does not validate produces no cases at all.

READ-ONLY on every input: captures are memmapped ``mode='r'``, the holo1
state is slice-parsed (never written), and nothing outside this
worktree's ``scratch/`` is created.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import _census, _geometry, _gt, _paths, _state, _volumes
from ._volumes import Volume

_paths.install_holo1_src()

TILE_CONVENTION = (
    "tile [ty, tx] exactly as the parity record prints them: ty along "
    "the tall cell axis, tx along the wide one; page is 0 on every "
    "declared volume and is carried explicitly in target/control "
    "addresses as [page, ty, tx, stream].")
CELL_AXES = (
    "cell y runs 0..cells_y, cell x runs 0..cells_x; cell_bbox and "
    "px_bbox are x-first half-open [x0, y0, x1, y1]; px x is the capture "
    "column (numpy axis 1) and px y the row (axis 0), so a crop is "
    "capture[py0:py1, px0:px1]; affine_cell_to_px maps px_x = a*cx + "
    "b*cy + c (row 0), px_y = d*cx + e*cy + f (row 1).")

_MANIFEST_KEYS = frozenset({
    "volume", "label", "step", "format_ref", "tile_matrix", "cells_yx",
    "streams", "colour", "classes", "captures", "tile_convention",
    "cell_axes", "halo_cells", "merge_gap_tiles", "max_span_cells",
    "px_pad_cells", "control_rim_cells", "gap_counts", "payload",
    "generator", "cases"})
_CAPTURE_KEYS = frozenset({"ordinal", "capture_id", "path", "dpi",
                           "shape_yx", "channels", "affine_cell_to_px",
                           "affine_fit"})
_CASE_KEYS = frozenset({"case_id", "cell_bbox", "tiles", "crops",
                        "targets", "controls"})
_CROP_KEYS = frozenset({"ordinal", "capture_id", "capture_path",
                        "crop_file", "px_bbox", "shape_yx"})
_TARGET_KEYS = frozenset({"address", "classes", "full_sheet"})
_FULL_SHEET_KEYS = frozenset({"holo1", "holo3"})


def validate_manifest(manifest: dict) -> None:
    """Exact-schema check on our own output — no key may drift."""
    def exact(mapping: dict, keys: frozenset[str], where: str) -> None:
        if set(mapping) != keys:
            raise ValueError(f"{where}: keys {sorted(mapping)} != schema "
                             f"{sorted(keys)}")

    exact(manifest, _MANIFEST_KEYS, "manifest")
    for capture in manifest["captures"]:
        exact(capture, _CAPTURE_KEYS, f"capture {capture.get('ordinal')}")
        rows = capture["affine_cell_to_px"]
        if len(rows) != 2 or any(len(row) != 3 for row in rows):
            raise ValueError("affine_cell_to_px must be 2x3")
    for case in manifest["cases"]:
        exact(case, _CASE_KEYS, f"case {case.get('case_id')}")
        if len(case["cell_bbox"]) != 4:
            raise ValueError(f"{case['case_id']}: cell_bbox must be 4-long")
        for crop in case["crops"]:
            exact(crop, _CROP_KEYS, f"{case['case_id']} crop")
            if len(crop["px_bbox"]) != 4:
                raise ValueError(f"{case['case_id']}: px_bbox must be 4")
        for target in case["targets"]:
            exact(target, _TARGET_KEYS,
                  f"{case['case_id']} target {target.get('address')}")
            exact(target["full_sheet"], _FULL_SHEET_KEYS,
                  f"{case['case_id']} target full_sheet")
            if len(target["address"]) != 4:
                raise ValueError("target address must be "
                                 "[page, ty, tx, stream]")
            unknown = set(target["classes"]) - set(_volumes.CLASS_NAMES)
            if unknown or not target["classes"]:
                raise ValueError(f"bad classes {target['classes']}")
        for control in case["controls"]:
            if len(control) != 4:
                raise ValueError("control must be [page, ty, tx, stream]")


def generator_stamp() -> dict:
    """``{"tree": HEAD, "dirty_sha": sha256(git diff HEAD) or ""}``."""
    def git(*args: str) -> bytes:
        done = subprocess.run(["git", *args], capture_output=True,
                              cwd=str(_paths.WORKTREE))
        return done.stdout if done.returncode == 0 else b""
    head = git("rev-parse", "HEAD").decode().strip()
    diff = git("diff", "HEAD")
    return {"tree": head,
            "dirty_sha": hashlib.sha256(diff).hexdigest() if diff else ""}


@dataclass
class VolumeResult:
    volume: Volume
    manifest: dict
    gaps: _volumes.GapSets
    affines: dict[str, _geometry.GlobalAffine]
    sizes_mb: dict[str, float]
    gt_validated: int
    crosscheck: dict | None
    wall_s: float


def _capture_records(volume: Volume, poses_by_capture: dict[str, list[dict]],
                     cache_dir: Path) -> tuple[list[dict], dict, list]:
    """One record per declared scan: sha (= capture id), shape, affine."""
    import tifffile

    records: list[dict] = []
    affines: dict[str, _geometry.GlobalAffine] = {}
    shapes: list[tuple[int, int]] = []
    for ordinal, (path, dpi) in enumerate(zip(volume.scans, volume.dpi)):
        if not path.is_file():
            raise SystemExit(f"crop_parity: capture absent: {path}")
        capture_id = _state.sha256_file_cached(path, cache_dir)
        poses = poses_by_capture.get(capture_id)
        if not poses:
            raise SystemExit(
                f"crop_parity: {volume.key}: no accepted holo1 pose carries "
                f"capture id {capture_id[:12]}… ({path.name}) — the "
                f"declared scan is not the one the archived state read")
        affine = _geometry.fit_global_affine(poses)
        with tifffile.TiffFile(str(path)) as handle:
            shape = handle.pages[0].shape
        shape_yx = (int(shape[0]), int(shape[1]))
        channels = int(shape[2]) if len(shape) > 2 else 1
        shapes.append(shape_yx)
        affines[capture_id] = affine
        records.append({
            "ordinal": ordinal, "capture_id": capture_id,
            "path": str(path), "dpi": float(dpi),
            "shape_yx": list(shape_yx), "channels": channels,
            "affine_cell_to_px": [list(row) for row in affine.rows],
            "affine_fit": {
                "n_accepted_poses": affine.n_poses,
                "px_per_cell": affine.px_per_cell,
                "residual_median_px": affine.residual_median_px,
                "residual_p99_px": affine.residual_p99_px,
                "residual_max_px": affine.residual_max_px}})
    return records, affines, shapes


def _write_crops(volume: Volume, cases: list[dict],
                 out_dir: Path) -> dict[str, float]:
    """Windowed reads off read-only memmaps, one capture at a time."""
    import tifffile

    sizes: dict[str, float] = {}
    for ordinal, path in enumerate(volume.scans):
        wanted = [(case, crop) for case in cases for crop in case["crops"]
                  if crop["ordinal"] == ordinal]
        if not wanted:
            continue
        plane = tifffile.memmap(str(path), mode="r")
        try:
            for case, crop in wanted:
                px0, py0, px1, py1 = crop["px_bbox"]
                window = np.ascontiguousarray(plane[py0:py1, px0:px1])
                target = out_dir / crop["crop_file"]
                if window.ndim == 3:
                    tifffile.imwrite(str(target), window, photometric="rgb")
                else:
                    tifffile.imwrite(str(target), window,
                                     photometric="minisblack")
                crop["shape_yx"] = [int(window.shape[0]),
                                    int(window.shape[1])]
                sizes[crop["crop_file"]] = window.nbytes / 1e6
                del window
        finally:
            del plane
    return sizes


def generate(volume: Volume, out_root: Path, *, classes: tuple[str, ...],
             merge_gap_tiles: int, max_span_cells: int, halo_cells: int,
             crosscheck: bool, write_crops: bool = True) -> VolumeResult:
    started = time.perf_counter()
    from holo.format.resolve import resolve_format_ref

    spec = resolve_format_ref(volume.format_ref)
    tiles_yx = spec._tiles_yx
    if tuple(tiles_yx) != tuple(volume.tile_matrix):
        raise SystemExit(f"crop_parity: {volume.key}: format says "
                         f"{tiles_yx} tiles, the record says "
                         f"{volume.tile_matrix}")
    cells_yx = (tiles_yx[0] * _geometry.TILE_CELLS,
                tiles_yx[1] * _geometry.TILE_CELLS)

    gaps = _volumes.gap_sets(volume)
    if not volume.holo1_state.is_file():
        raise SystemExit(f"crop_parity: holo1 state absent: "
                         f"{volume.holo1_state}")
    facts = _state.read_state(volume.holo1_state)
    if facts.addresses != gaps.holo1:
        raise SystemExit(
            f"crop_parity: {volume.key}: the archived state's certificate "
            f"set ({len(facts.addresses)}) differs from the recorded "
            f"extract ({len(gaps.holo1)}) — inputs are not the record")

    payload = _gt.load_payload(volume.payload, volume.payload_sha256,
                               volume.payload_bytes)
    truth = _gt.reconstruct(volume.format_ref, payload)
    gt_validated = _gt.validate_against_state(
        truth, facts.certified_bits,
        f"{volume.key} archived holo1 state {volume.holo1_state}")

    checked = None
    if crosscheck:
        checked = _state.crosscheck_with_load_session(
            volume.holo1_state, facts, int(spec.tile_user_bits))

    cache_dir = out_root / "_cache"
    poses_by_capture: dict[str, list[dict]] = {}
    for pose in facts.poses:
        poses_by_capture.setdefault(str(pose["capture_id"]), []).append(pose)
    captures, affines, shapes = _capture_records(
        volume, poses_by_capture, cache_dir)

    targets = gaps.targets(classes)
    target_tiles = frozenset((ty, tx) for _p, ty, tx, _s in targets)
    clusters = _geometry.split_clusters(
        _geometry.cluster_tiles(target_tiles, merge_gap_tiles),
        max_span_cells)
    covered = sorted(tile for cluster in clusters for tile in cluster.members)
    if covered != sorted(target_tiles):
        raise AssertionError("cases do not cover every target tile once")

    by_tile: dict[tuple[int, int], list[tuple]] = {}
    for address in sorted(targets):
        by_tile.setdefault((address[1], address[2]), []).append(address)

    cases: list[dict] = []
    for index, cluster in enumerate(clusters, start=1):
        case_id = f"{volume.key}-c{index:02d}"
        cell_bbox = _geometry.cell_bbox_for(cluster, halo_cells, cells_yx)
        crops = []
        for record in captures:
            affine = affines[record["capture_id"]]
            px_bbox = _geometry.px_bbox_for(
                cell_bbox, affine, tuple(record["shape_yx"]))
            crops.append({
                "ordinal": record["ordinal"],
                "capture_id": record["capture_id"],
                "capture_path": record["path"],
                "crop_file": f"{case_id}-{record['ordinal']}.tiff",
                "px_bbox": list(px_bbox), "shape_yx": [0, 0]})
        entries = []
        for tile in cluster.members:
            for address in by_tile[tile]:
                entries.append({
                    "address": [address[0], address[1], address[2],
                                address[3]],
                    "classes": [gaps.class_of(address)],
                    "full_sheet": {
                        "holo1": ("certified" if address in gaps.holo1
                                  else "uncertified"),
                        "holo3": ("certified" if address in gaps.holo3
                                  else "uncertified")}})
        controls = _geometry.controls_for(cell_bbox, gaps.both, target_tiles)
        cases.append({
            "case_id": case_id, "cell_bbox": list(cell_bbox),
            "tiles": [[ty, tx] for ty, tx in cluster.members],
            "crops": crops, "targets": entries,
            "controls": [[p, ty, tx, s] for p, ty, tx, s in controls]})

    manifest = {
        "volume": volume.key, "label": volume.label, "step": volume.step,
        "format_ref": volume.format_ref,
        "tile_matrix": list(volume.tile_matrix), "cells_yx": list(cells_yx),
        "streams": list(gaps.streams), "colour": volume.colour,
        "classes": list(classes), "captures": captures,
        "tile_convention": TILE_CONVENTION, "cell_axes": CELL_AXES,
        "halo_cells": halo_cells, "merge_gap_tiles": merge_gap_tiles,
        "max_span_cells": max_span_cells,
        "px_pad_cells": _geometry.PX_PAD_CELLS,
        "control_rim_cells": _geometry.CONTROL_RIM_CELLS,
        "gap_counts": {"holo1": len(gaps.holo1), "holo3": len(gaps.holo3),
                       "both": len(gaps.both), "miss": len(gaps.miss),
                       "gain": len(gaps.gain),
                       "neither": len(gaps.neither),
                       "holo3_run": volume.holo3_run,
                       "events": gaps.events_meta},
        "payload": {"path": str(volume.payload),
                    "sha256": volume.payload_sha256,
                    "bytes": volume.payload_bytes,
                    "gt_validated_certificates": gt_validated},
        "generator": generator_stamp(),
        "cases": cases}
    validate_manifest(manifest)

    out_dir = out_root / volume.key
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = _write_crops(volume, cases, out_dir) if write_crops else {}
    validate_manifest(manifest)      # again: _write_crops fills shape_yx
    (out_dir / "cases.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return VolumeResult(volume=volume, manifest=manifest, gaps=gaps,
                        affines=affines, sizes_mb=sizes,
                        gt_validated=gt_validated, crosscheck=checked,
                        wall_s=time.perf_counter() - started)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--volume", action="append", default=[],
                        help="a declared volume key, or 'all' "
                             f"({', '.join(_volumes.VOLUMES_BY_KEY)})")
    parser.add_argument("--classes", default="",
                        help="comma-separated target classes "
                             f"({', '.join(_volumes.CLASS_NAMES)}); "
                             "default miss,gain — 'neither' is where "
                             "toolbox yield lives but is 158-410 "
                             "addresses on the colour volumes")
    parser.add_argument("--merge-gap-tiles", type=int, default=2,
                        help="target tiles whose empty-tile gap is <= this "
                             "merge into one case (default 2)")
    parser.add_argument("--max-span-cells", type=int, default=768,
                        help="a case whose long side exceeds this splits "
                             "(default 768)")
    parser.add_argument("--halo-cells", type=int, default=240,
                        help="context around every cluster on all sides "
                             "(default 240 ~ 1.5 window strides at the "
                             "200-cell window both receivers place with)")
    parser.add_argument("--out-root", type=Path, default=_paths.SCRATCH,
                        help=f"default {_paths.SCRATCH}")
    parser.add_argument("--crosscheck", action="store_true",
                        help="also read the holo1 state through its own "
                             "load_session and compare (small states only)")
    parser.add_argument("--no-crops", action="store_true",
                        help="manifest + census only (census dry run)")
    args = parser.parse_args(argv)

    _paths.refuse_if_absent()
    volumes = _volumes.resolve_volumes(args.volume)
    classes = tuple(name.strip() for name in args.classes.split(",")
                    if name.strip()) or None

    for volume in volumes:
        chosen = classes or volume.default_classes
        print(f"crop_parity: {volume.key} ({', '.join(chosen)}) …",
              file=sys.stderr)
        result = generate(volume, args.out_root, classes=chosen,
                          merge_gap_tiles=args.merge_gap_tiles,
                          max_span_cells=args.max_span_cells,
                          halo_cells=args.halo_cells,
                          crosscheck=args.crosscheck,
                          write_crops=not args.no_crops)
        census = _census.render(result)
        print(census)
        (args.out_root / volume.key / "cases-census.md").write_text(
            census, encoding="utf-8")
        print(f"crop_parity: wrote {args.out_root / volume.key}/cases.json "
              f"+ {sum(len(c['crops']) for c in result.manifest['cases'])} "
              f"crops + cases-census.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

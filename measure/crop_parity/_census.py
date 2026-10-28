"""The case census — rendering, split out of ``cases.py``.

Import-only: it turns a finished ``VolumeResult`` into markdown and knows
nothing else (it cannot decode, read a state or touch the corpus). The
seam is the holo2 harness's ``crop_cases_report.py``, taken up front
rather than at the line cap.
"""
from __future__ import annotations

from typing import Any


def _fmt_address(address: list) -> str:
    page, ty, tx, stream = address
    text = f"({ty}, {tx})"
    if stream != "main":
        text = f"{text}/{stream}"
    if page:
        text = f"p{page} {text}"
    return text


def render(result: Any) -> str:
    volume = result.volume
    manifest = result.manifest
    gaps = result.gaps
    lines: list[str] = []
    lines.append(f"# Crop cases — {volume.key} ({volume.label})")
    lines.append("")
    lines.append(
        f"Format `{volume.format_ref}`, tile matrix "
        f"{volume.tile_matrix[0]}x{volume.tile_matrix[1]}, streams "
        f"{list(gaps.streams)}, "
        f"{len(volume.scans)} capture(s) at {list(volume.dpi)} dpi. "
        f"Generated in {result.wall_s:.1f} s from tree "
        f"`{manifest['generator']['tree'][:12]}`"
        + (" (dirty)" if manifest["generator"]["dirty_sha"] else "") + ".")
    lines.append("")

    lines.append("## The gap (recomputed, cross-checked against the record)")
    lines.append("")
    lines.append(f"holo3 baseline harvest: `{volume.holo3_run}` "
                 f"({gaps.events_meta.get('tile_outcome_rows', 0)} "
                 "TileOutcome rows).")
    lines.append("")
    lines.append("| set | addresses | recorded |")
    lines.append("|---|---:|---:|")
    lines.append(f"| holo1 certified | {len(gaps.holo1)} | — |")
    lines.append(f"| holo3 certified | {len(gaps.holo3)} | — |")
    lines.append(f"| both | {len(gaps.both)} | — |")
    lines.append(f"| **miss** (holo1 only) | {len(gaps.miss)} "
                 f"| {volume.expect_miss} |")
    lines.append(f"| **gain** (holo3 only) | {len(gaps.gain)} "
                 f"| {volume.expect_gain} |")
    lines.append(f"| neither | {len(gaps.neither)} | — |")
    lines.append("")
    lines.append(f"Ground truth: golden payload "
                 f"`{volume.payload_sha256[:12]}…` "
                 f"({volume.payload_bytes} B) re-encoded through holo1 "
                 f"generation, validated against "
                 f"{result.gt_validated}/{len(gaps.holo1)} certificates in "
                 f"the archived holo1 state, zero mismatches.")
    if result.crosscheck is not None:
        check = result.crosscheck
        lines.append("")
        lines.append(
            f"State slice cross-check vs `load_session`: addresses "
            f"identical {check['addresses_identical']}, bits identical "
            f"{check['bits_identical']}, accepted poses identical "
            f"{check['accepted_poses_identical']} "
            f"({check['slice_certificates']} certificates, "
            f"{check['slice_accepted_poses']} poses).")
    lines.append("")

    lines.append("## Captures and the cell→pixel fit")
    lines.append("")
    lines.append("| # | capture id | shape (y, x) | ch | poses | px/cell "
                 "| residual med / p99 / max px |")
    lines.append("|---:|---|---|---:|---:|---:|---|")
    for capture in manifest["captures"]:
        fit = capture["affine_fit"]
        lines.append(
            f"| {capture['ordinal']} | `{capture['capture_id'][:12]}…` "
            f"| {capture['shape_yx'][0]}x{capture['shape_yx'][1]} "
            f"| {capture['channels']} | {fit['n_accepted_poses']} "
            f"| {fit['px_per_cell']:.3f} "
            f"| {fit['residual_median_px']:.1f} / "
            f"{fit['residual_p99_px']:.1f} / "
            f"{fit['residual_max_px']:.1f} |")
    lines.append("")
    lines.append(f"The pixel bbox is padded by {manifest['px_pad_cells']} "
                 "cells' worth of pixels on all sides before clipping, "
                 "which is the margin the max residual has to fit inside.")
    lines.append("")

    lines.append(f"## Cases ({len(manifest['cases'])}) — classes "
                 f"{', '.join(manifest['classes'])}, halo "
                 f"{manifest['halo_cells']} cells, merge-gap "
                 f"{manifest['merge_gap_tiles']} tiles, max span "
                 f"{manifest['max_span_cells']} cells")
    lines.append("")
    lines.append("| case | tiles | targets | controls | cell bbox (x0,y0,"
                 "x1,y1) | crop px (y, x) | MB/crop |")
    lines.append("|---|---:|---:|---:|---|---|---:|")
    for case in manifest["cases"]:
        crop = case["crops"][0]
        size = result.sizes_mb.get(crop["crop_file"])
        px = crop["px_bbox"]
        shape = (f"{crop['shape_yx'][0]}x{crop['shape_yx'][1]}"
                 if crop["shape_yx"][0] else
                 f"{px[3] - px[1]}x{px[2] - px[0]}")
        megabytes = "—" if size is None else f"{size:.1f}"
        lines.append(
            f"| `{case['case_id']}` | {len(case['tiles'])} "
            f"| {len(case['targets'])} | {len(case['controls'])} "
            f"| {tuple(case['cell_bbox'])} | {shape} | {megabytes} |")
    lines.append("")

    per_class: dict[str, int] = {}
    for case in manifest["cases"]:
        for target in case["targets"]:
            for name in target["classes"]:
                per_class[name] = per_class.get(name, 0) + 1
    lines.append("Targets by class: "
                 + (", ".join(f"{name} {count}"
                              for name, count in sorted(per_class.items()))
                    or "none"))
    lines.append("")
    for case in manifest["cases"]:
        addresses = ", ".join(_fmt_address(t["address"]) + f" [{t['classes'][0]}]"
                              for t in case["targets"])
        lines.append(f"- `{case['case_id']}`: {addresses}")
    lines.append("")
    if volume.colour:
        lines.append(
            "**Colour caveat.** A crop changes the context a colour "
            "calibration head pools over, so these cases SCREEN the gap; "
            "they do not settle it. A crop verdict that disagrees with "
            "the full-sheet record on a colour volume is evidence about "
            "the crop, not yet about the receiver.")
        lines.append("")
    return "\n".join(lines)

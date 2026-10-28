#!/usr/bin/env python
"""THE CROP-BATTERY REPORT — rendering, split out of ``crop_harness.py``.

NOT A TEST and not a driver: import-only, the rendering half of the crop
harness (HANDOFF-CROP Deliverable B). ``crop_harness.py`` declares the
paths, runs both receivers and compares against ground truth; this
module turns the finished per-sheet results dict — the SAME dict the
harness writes as ``results.json`` — into markdown, and knows nothing
else. The seam is ``parity_k_report.py``'s, taken up front rather than
at the line cap: this module imports NOTHING from the harness, results
arrive as a plain mapping, and nothing here can decode, read a state or
touch the corpus.

Rendering rules carried from the handoff: wrong certificates render AT
THE TOP, loudly (expected count zero); control flips are REPORTED, never
gated; uplift rows are flagged distinctly; every wall is labelled
executed vs adopted.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

#: The four target classes, in the handoff's order — repeated here (a
#: rendering order, not logic) so this module needs no harness import.
_CLASS_ORDER = ("flipped", "still_missing_v2", "v1_missing", "neither")


def _mark(value: bool | None) -> str:
    """Three-valued, like parity_k_report's: an unavailable side is the
    ABSENCE of a statement, never a fake miss."""
    if value is None:
        return "—"
    return "yes" if value else "no"


def _fmt_tile(tile: Iterable[int]) -> str:
    parts = list(tile)
    if len(parts) == 3 and parts[0] == 0:
        parts = parts[1:]
    return "(" + ", ".join(str(p) for p in parts) + ")"


def _fmt_blocks(blocks: list[Mapping[str, Any]]) -> str:
    if not blocks:
        return "no retained v1 evidence blocks"
    rows = []
    for block in blocks:
        rows.append(f"lane `{block['lane_id']}`: {block['n_observed']} "
                    f"cells observed, |LLR| min={block['min_abs_llr']:.3g} "
                    f"mean={block['mean_abs_llr']:.3g}")
    return "; ".join(rows)


def _fmt_spends(spends: list[Mapping[str, Any]]) -> str:
    if not spends:
        return "no payload spend recorded (never attempted)"
    rows = []
    for spend in spends:
        rows.append(f"{spend['route']}/{spend['footing_or_tag']}: "
                    f"{spend['outcome']} ({spend['attempts']} attempt(s), "
                    f"{spend['exposures']} CRC exposure(s))")
    return "; ".join(rows)


def _fmt_poses(poses: list[Mapping[str, Any]]) -> str:
    if not poses:
        return "no committed holo2 pose's evidence reaches this tile"
    seen: dict[tuple[str, str], Mapping[str, Any]] = {}
    for pose in poses:
        seen[(str(pose["footing_id"]), str(pose["window_id"]))] = pose
    rows = []
    for (footing_id, _window_id), pose in sorted(seen.items()):
        status = str(pose.get("window_status"))
        reason = pose.get("window_retired_reason")
        rows.append(f"footing `{footing_id}`, extent "
                    f"{pose.get('window_extent_cells')} {status}"
                    + (f"({reason})" if reason else ""))
    return "; ".join(rows)


def _run_line(side: str, run: Mapping[str, Any]) -> str:
    status = run["status"]
    sidecar = run.get("sidecar")
    if sidecar is None:
        return f"- **{side}**: {status} — {run['reason']}"
    wall = float(sidecar.get("wall_seconds", 0.0))
    star = "*" if status == "adopted" else ""
    return (f"- **{side}**: {status}, exit {sidecar.get('exit')}, wall "
            f"{wall:.1f} s{star} (decoded {sidecar.get('ran_at', '?')}, "
            f"receiver tree `{str(sidecar.get('receiver_tree', ''))[:12]}`"
            + (", dirty" if sidecar.get("receiver_dirty_sha") else "")
            + ")")


def _wrong_section(wrong: list[Mapping[str, Any]]) -> list[str]:
    lines = ["## WRONG CERTIFICATES (expected: none)", ""]
    if not wrong:
        lines.append("None — every crop-minted certificate on both sides "
                     "matches the re-encoded golden payload.")
        lines.append("")
        return lines
    lines.append(f"**{len(wrong)} WRONG CERTIFICATE(S).** A crop-minted "
                 "certificate whose bits disagree with ground truth is a "
                 "correctness failure of the receiver that minted it, not "
                 "a yield fact — this run exits nonzero.")
    lines.append("")
    for entry in wrong:
        lines.append(f"- case `{entry['case_id']}`, side {entry['side']}, "
                     f"tile {_fmt_tile(entry['tile'])}: "
                     f"{entry['n_bit_mismatch']} bit(s) differ")
    lines.append("")
    return lines


def _class_table(per_class: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        "## Per-class outcomes vs the full-sheet record", "",
        "Counts over TARGET tiles compared this battery (a side is "
        "counted only where its crop decode was available). "
        "`full-sheet` restates the manifest's recorded verdicts for the "
        "same tiles — the expectation, not a bar.", "",
        "| class | targets | crop-v1 cert | full-sheet v1 cert | "
        "crop-h2 cert | full-sheet h2 cert |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in _CLASS_ORDER:
        bucket = per_class.get(name)
        if bucket is None:
            continue
        v1, h2 = bucket["v1"], bucket["h2"]
        lines.append(
            f"| {name} | {bucket['n']} "
            f"| {v1['crop_certified']}/{v1['compared']} "
            f"| {v1['full_sheet_certified']}/{v1['compared']} "
            f"| {h2['crop_certified']}/{h2['compared']} "
            f"| {h2['full_sheet_certified']}/{h2['compared']} |")
    lines.append("")
    return lines


def _uplift_section(uplift: list[Mapping[str, Any]]) -> list[str]:
    lines = ["## UPLIFT rows", ""]
    if not uplift:
        lines.append("None. Absence of uplift is data, not failure.")
        lines.append("")
        return lines
    lines.append("A crop certificate on a target the same receiver "
                 "MISSED at full-sheet scale. Every row is GT-checked; "
                 "`gt_ok` false rows also appear under WRONG "
                 "CERTIFICATES above.")
    lines.append("")
    for entry in uplift:
        lines.append(f"- **{entry['side']}** certifies "
                     f"{_fmt_tile(entry['tile'])} in case "
                     f"`{entry['case_id']}` (classes: "
                     f"{', '.join(entry['classes']) or '—'}; "
                     f"gt_ok: {entry['gt_ok']})")
    lines.append("")
    return lines


def _controls_line(controls: Mapping[str, Mapping[str, Any]]) -> str:
    parts = []
    for side in ("v1", "h2"):
        tally = controls[side]
        if tally["reproduced"] is None:
            parts.append(f"{side}: {tally['n']} controls, side unavailable")
            continue
        text = (f"{side}: {tally['reproduced']}/{tally['n']} reproduced, "
                f"{tally['flipped']} flipped")
        if tally["flipped_tiles"]:
            text += (" (" + ", ".join(_fmt_tile(t)
                                      for t in tally["flipped_tiles"]) + ")")
        parts.append(text)
    return "; ".join(parts)


def _target_lines(row: Mapping[str, Any]) -> list[str]:
    tile = _fmt_tile(row["tile"])
    full = row["full_sheet"]
    crop_v1, crop_h2 = row["crop"]["v1"], row["crop"]["h2"]
    flags = f"  **[{', '.join(row['flags'])}]**" if row["flags"] else ""
    lines = [f"### tile {tile} — {', '.join(row['classes']) or 'control'}"
             f"{flags}", ""]
    lines.append(f"- full sheet: v1 {full.get('v1', '?')}, "
                 f"h2 {full.get('h2', '?')}")
    lines.append(f"- crop v1 certified: {_mark(crop_v1['certified'])}"
                 + ("" if crop_v1["available"]
                    else " (side unavailable)"))
    rank = crop_h2.get("rank")
    lines.append(f"- crop h2 certified: {_mark(crop_h2['certified'])}"
                 + (f" (rank {rank})" if rank is not None else "")
                 + ("" if crop_h2["available"]
                    else " (side unavailable)"))
    if crop_v1.get("blocks") is not None and crop_v1["certified"] is False:
        lines.append(f"- v1 retained evidence: "
                     f"{_fmt_blocks(crop_v1['blocks'])}")
    if crop_h2.get("spends") is not None:
        lines.append(f"- h2 spends: {_fmt_spends(crop_h2['spends'])}")
    if crop_h2.get("poses") is not None:
        lines.append(f"- h2 poses: {_fmt_poses(crop_h2['poses'])}")
    lines.append("")
    return lines


def render_report(results: Mapping[str, Any]) -> str:
    aggregates = results["aggregates"]
    walls = aggregates["walls"]
    gt = results["gt_validation"]
    lines: list[str] = []
    lines.append(f"# Crop battery — {results['sheet']}")
    lines.append("")
    lines.append(f"Manifest `{results['manifest']}`, format "
                 f"`{results['format_ref']}`, generated "
                 f"{results['generated_at']}. Harness tree "
                 f"`{str(results['harness'].get('repo_head', ''))[:12]}` "
                 f"(v1 receiver tree "
                 f"`{str(results['harness'].get('v1_receiver_tree', ''))[:12]}`,"
                 f" h2 receiver tree "
                 f"`{str(results['harness'].get('h2_receiver_tree', ''))[:12]}`).")
    lines.append("")
    validated = ", ".join(f"{sheet}: {count}"
                          for sheet, count in
                          sorted(gt["validated_tiles"].items()))
    lines.append(f"Ground truth: golden payload "
                 f"`{gt['payload_sha256'][:12]}…` re-encoded through "
                 f"src/holo generation; validated against {validated} "
                 f"v1-certified tiles ({gt['rule']}).")
    lines.append("")
    lines.extend(_wrong_section(aggregates["wrong_certificates"]))
    lines.extend(_class_table(aggregates["per_class"]))
    lines.extend(_uplift_section(aggregates["uplift"]))

    lines.append("## Cases")
    lines.append("")
    for case in results["cases"]:
        lines.append(f"## case `{case['case_id']}`")
        lines.append("")
        lines.append(f"Crop `{case['crop_file']}` "
                     f"(sha `{case['crop_sha256'][:12]}…`). "
                     f"GT-checked certificates: "
                     f"v1 {case['checked_certificates']['v1']}, "
                     f"h2 {case['checked_certificates']['h2']}.")
        lines.append("")
        for side in ("v1", "h2"):
            lines.append(_run_line(side, case["runs"][side]))
        lines.append(f"- controls (reported, never gated): "
                     f"{_controls_line(case['controls'])}")
        lines.append("")
        for row in case["tiles"]:
            if row["kind"] == "target":
                lines.extend(_target_lines(row))

    lines.append("## Battery totals")
    lines.append("")
    lines.append(f"- runs executed this invocation: "
                 f"{walls['runs_executed']} "
                 f"({walls['executed_wall_seconds']:.1f} s wall)")
    lines.append(f"- runs adopted from sidecars: {walls['runs_adopted']} "
                 f"({walls['adopted_wall_seconds']:.1f} s recorded wall, "
                 f"marked * above)")
    lines.append(f"- wrong certificates: "
                 f"{len(aggregates['wrong_certificates'])}; uplift rows: "
                 f"{len(aggregates['uplift'])}")
    lines.append("")
    return "\n".join(lines)

"""THE CROP-BATTERY REPORT — rendering, split out of ``harness.py``.

Import-only, the rendering half: results arrive as a plain mapping (the
same dict the harness writes as ``results.json``) and nothing here can
decode, read a state or touch the corpus.

Rendering rules carried from the holo2 harness: wrong certificates
render AT THE TOP, loudly (expected count zero); control flips are
REPORTED, never gated; every wall is labelled executed vs adopted; an
unavailable side is an em dash, never a fake miss.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

_SIDES = ("holo1", "holo3")


def _mark(value: bool | None) -> str:
    return "—" if value is None else ("yes" if value else "no")


def _fmt(address: Iterable[int | str]) -> str:
    page, ty, tx, stream = list(address)
    text = f"({ty}, {tx})"
    if stream != "main":
        text = f"{text}/{stream}"
    return text if not page else f"p{page} {text}"


def _wrong_section(wrong: list[Mapping[str, Any]],
                   bits: Mapping[str, bool]) -> list[str]:
    lines = ["## WRONG CERTIFICATES (expected: none)", ""]
    unaudited = [side for side, ok in sorted(bits.items()) if not ok]
    if not wrong:
        lines.append("None — every crop-minted certificate whose bits "
                     "could be read matches the re-encoded golden "
                     "payload.")
    else:
        lines.append(f"**{len(wrong)} WRONG CERTIFICATE(S).** A crop-minted "
                     "certificate whose bits disagree with ground truth is "
                     "a correctness failure of the receiver that minted it, "
                     "not a yield fact — this run exits nonzero.")
        lines.append("")
        for entry in wrong:
            lines.append(f"- case `{entry['case_id']}`, side "
                         f"{entry['side']}, {_fmt(entry['address'])}: "
                         f"{entry['n_bit_mismatch']} bit(s) differ")
    if unaudited:
        lines.append("")
        lines.append(f"**Not audited on: {', '.join(unaudited)}** — that "
                     "side reported no certificate bits, so its zero is "
                     "an absence of measurement, not a clean result.")
    lines.append("")
    return lines


def _bbox_section(outside: list[Mapping[str, Any]]) -> list[str]:
    lines = ["## Address-frame check", ""]
    if not outside:
        lines.append("Every crop certificate on both sides addresses a "
                     "tile inside its case's cell rectangle: the printed "
                     "address word carries the absolute tile counter, so "
                     "a crop decodes into the FULL-SHEET frame with no "
                     "origin shift applied.")
    else:
        lines.append(f"**{len(outside)} certificate(s) address a tile "
                     "OUTSIDE the case's cell rectangle** — the crop's "
                     "frame does not agree with the full-sheet frame, and "
                     "every verdict below is suspect until that is "
                     "explained.")
        for entry in outside[:20]:
            lines.append(f"- `{entry['case_id']}` {entry['side']}: "
                         f"{_fmt(entry['address'])}")
    lines.append("")
    return lines


def _class_table(per_class: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        "## Per-class outcomes vs the full-sheet record", "",
        "Counts over TARGET addresses compared this battery (a side "
        "counts only where its crop decode was available). "
        "`reproduces` = the crop verdict equals the recorded full-sheet "
        "verdict for that side — the expectation, not a bar.", "",
        "| class | targets | crop holo1 cert | reproduces | "
        "crop holo3 cert | reproduces |",
        "|---|---:|---:|---:|---:|---:|"]
    for name in sorted(per_class):
        bucket = per_class[name]
        repro = bucket["reproduces_full_sheet"]
        lines.append(
            f"| {name} | {bucket['n']} "
            f"| {bucket['holo1_crop_certified']}/"
            f"{bucket['holo1_compared']} "
            f"| {repro['holo1']}/{bucket['holo1_compared']} "
            f"| {bucket['holo3_crop_certified']}/"
            f"{bucket['holo3_compared']} "
            f"| {repro['holo3']}/{bucket['holo3_compared']} |")
    lines.append("")
    return lines


def _controls_line(controls: Mapping[str, Mapping[str, Any]]) -> str:
    parts = []
    for side in _SIDES:
        tally = controls[side]
        if tally["reproduced"] is None:
            parts.append(f"{side}: {tally['n']} controls, side unavailable")
            continue
        text = (f"{side}: {tally['reproduced']}/{tally['n']} reproduced, "
                f"{tally['flipped']} flipped")
        if tally["flipped_addresses"]:
            text += (" (" + ", ".join(_fmt(a) for a in
                                      tally["flipped_addresses"][:12]) + ")")
        parts.append(text)
    return "; ".join(parts)


def _rim_lines(controls: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Control reproduction by depth inside the crop's cell rectangle —
    a crop starves its rim of context, and this is what separates that
    from a receiver fact."""
    bands: set[str] = set()
    for side in _SIDES:
        bands |= set(controls[side].get("by_rim_depth", {}))
    if not bands:
        return []
    order = sorted(bands, key=lambda band: int(band.split("-")[0]))
    lines = ["", "| controls by depth inside the crop (cells) "
             + "".join(f"| {side} reproduced " for side in _SIDES) + "|",
             "|---" + "|---:" * len(_SIDES) + "|"]
    for band in order:
        row = f"| {band} "
        for side in _SIDES:
            tally = controls[side].get("by_rim_depth", {}).get(band)
            row += ("| — " if tally is None else
                    f"| {tally['n'] - tally['flipped']}/{tally['n']} ")
        lines.append(row + "|")
    return lines


def _run_line(side: str, run: Mapping[str, Any]) -> str:
    sidecar = run.get("sidecar")
    if sidecar is None:
        return f"- **{side}**: {run['status']} — {run['reason']}"
    star = "*" if run["status"] == "adopted" else ""
    return (f"- **{side}**: {run['status']}, exit {sidecar.get('exit')}, "
            f"wall {float(sidecar.get('wall_seconds', 0.0)):.1f} s{star} "
            f"(decoded {sidecar.get('ran_at', '?')}, receiver tree "
            f"`{str(sidecar.get('receiver_tree', ''))[:12]}`"
            + (", dirty" if sidecar.get("receiver_dirty_sha") else "") + ")")


def render(results: Mapping[str, Any]) -> str:
    aggregates = results["aggregates"]
    walls = aggregates["walls"]
    lines: list[str] = []
    lines.append(f"# Crop battery — {results['volume']} "
                 f"({results['label']})")
    lines.append("")
    lines.append(
        f"Manifest `{results['manifest']}`, format "
        f"`{results['format_ref']}`, classes "
        f"{', '.join(results['classes'])}, generated "
        f"{results['generated_at']}. holo1 tree "
        f"`{str(results['harness'].get('holo1_tree', ''))[:12]}`, holo3 "
        f"tree `{str(results['harness'].get('holo3_tree', ''))[:12]}`.")
    lines.append("")
    gap = results["gap_counts"]
    lines.append(
        f"Full-sheet record (`{gap['holo3_run']}`): holo1 {gap['holo1']}, "
        f"holo3 {gap['holo3']}, both {gap['both']} — miss {gap['miss']}, "
        f"gain {gap['gain']}, neither {gap['neither']}.")
    lines.append("")
    lines.append(
        f"Ground truth: golden payload "
        f"`{results['gt']['payload_sha256'][:12]}…` re-encoded through "
        f"holo1 generation and validated against "
        f"{results['gt']['validated_certificates']} certificates of the "
        f"archived holo1 state ({results['gt']['rule']}).")
    lines.append("")
    bits = {side: all(case["bits_available"].get(side, True)
                      for case in results["cases"])
            for side in _SIDES} if results["cases"] else {}
    lines.extend(_wrong_section(aggregates["wrong_certificates"], bits))
    lines.extend(_bbox_section(aggregates["out_of_bbox"]))
    lines.extend(_class_table(aggregates["per_class"]))

    agree = aggregates["agreement"]
    lines.append("## Agreement on targets")
    lines.append("")
    lines.append(f"- both sides give the same crop verdict: "
                 f"{agree['agree']}")
    lines.append(f"- the two sides disagree on the crop: "
                 f"{agree['disagree']}")
    lines.append(f"- undetermined (a side unavailable): "
                 f"{agree['undetermined']}")
    lines.append("")

    lines.append("## Cases")
    lines.append("")
    for case in results["cases"]:
        lines.append(f"### case `{case['case_id']}`")
        lines.append("")
        counts = case["n_certificates"]
        lines.append(
            f"Cell bbox {tuple(case['cell_bbox'])}, crop sha "
            f"`{case['crop_sha256'][:12]}…`. Crop certificates: "
            f"holo1 {counts['holo1']}, holo3 {counts['holo3']} "
            f"(GT-checked: holo1 "
            f"{case['checked_certificates']['holo1']}, holo3 "
            f"{case['checked_certificates']['holo3']}).")
        lines.append("")
        for side in _SIDES:
            lines.append(_run_line(side, case["runs"][side]))
        lines.append(f"- controls (reported, never gated): "
                     f"{_controls_line(case['controls'])}")
        lines.extend(_rim_lines(case["controls"]))
        lines.append("")
        lines.append("| target | class | full-sheet holo1 / holo3 "
                     "| crop holo1 | crop holo3 | agree |")
        lines.append("|---|---|---|---|---|---|")
        for row in case["targets"]:
            full = row["full_sheet"]
            lines.append(
                f"| {_fmt(row['address'])} "
                f"| {', '.join(row['classes'])} "
                f"| {full.get('holo1')} / {full.get('holo3')} "
                f"| {_mark(row['crop']['holo1']['certified'])} "
                f"| {_mark(row['crop']['holo3']['certified'])} "
                f"| {_mark(row['agree'])} |")
        lines.append("")

    lines.append("## Battery totals")
    lines.append("")
    executed = walls["executed_wall_seconds"]
    lines.append(f"- runs executed this invocation: "
                 f"{walls['runs_executed']} "
                 f"(holo1 {executed['holo1']:.1f} s, holo3 "
                 f"{executed['holo3']:.1f} s wall)")
    lines.append(f"- runs adopted from sidecars: {walls['runs_adopted']} "
                 f"({walls['adopted_wall_seconds']:.1f} s recorded wall, "
                 f"marked * above)")
    lines.append(f"- wrong certificates: "
                 f"{len(aggregates['wrong_certificates'])}; out-of-bbox "
                 f"certificates: {len(aggregates['out_of_bbox'])}")
    lines.append("")
    if results.get("colour"):
        lines.append(
            "**Colour caveat.** A crop changes the context a colour "
            "calibration head pools over, so this battery SCREENS the "
            "gap rather than settling it: a crop verdict that disagrees "
            "with the full-sheet record here is evidence about the crop "
            "first, and about the receiver only after a full-sheet "
            "confirmation.")
        lines.append("")
    return "\n".join(lines)

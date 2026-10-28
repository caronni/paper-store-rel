"""E8 outputs: the pre-registered bar, ``e8.json``, the figure, the tables.

Kept out of the run driver so the expensive rows are on disk
(``raw.json``) before any reduction can fail on them — the P2 rule.  The
BAR is written before the first capture is opened, which is the only
place a pre-registration can honestly live.
"""
from __future__ import annotations

import json
import resource
import time

import numpy as np
from PIL import Image, ImageDraw

from . import _context_loop, _residue_figures, _swim_inputs
from ._swim_inputs import CAPTURE_DPI, DEAD_BANDS, FORMAT_REF, QUAL_STATE

BG = (255, 255, 255)
INK = (30, 30, 30)
GREY = (120, 120, 120)
GATE = (198, 232, 205)
CONFIG_COLOUR = {
    "a": (110, 130, 200), "b": (205, 95, 55), "c": (150, 150, 150),
    "z": (60, 60, 60), "e1": (90, 150, 90), "e2": (60, 110, 60),
    "f": (190, 160, 60), "g": (140, 90, 170), "h": (80, 165, 175)}

#: The E4 numbers this run has to reproduce at G1 configuration (a)/(b),
#: and the oracle gains the bar is written against (§2.10).
E4_ORACLE_PP = {"dead": -2.427, "control": -2.452}

APPROXIMATIONS = (
    "restricted region: the detector is fitted over the windows within "
    "--fit-radius tiles of a target, exactly as gt_affine, E1 and E4 did",
    "G1 is E4's footing exactly — one refit PER TILE at that tile's "
    "supervised 6-dof affine plus BER polish, bins recut — and is therefore "
    "a CEILING geometry, not a receiver",
    "G2 is production-like: the committed pose plus the field the shipped "
    "TILE_FRAGMENT probe pass builds, applied to EVERY window of the region "
    "through the same offsets_override seam the uF arm uses; ONE refit per "
    "capture serves all eight tiles because the field is tile-blind",
    "G2's field is built from probes alone (no anchors), so it is the "
    "pose-writer instrument's configuration (ii) rather than production's "
    "uF arm in full",
    "G2 changes the SAMPLING only: the detector is still fitted over E1's "
    "restricted region rather than production's whole payload region, "
    "which is what keeps G1 and G2 a one-variable comparison and what "
    "stops G2 from being a production run",
    "the refit seam is keyed by tile address, so it corrects PAYLOAD "
    "windows only; label rows own no tile and stay at the arm's own zero "
    "(the same caveat §2.11 records)",
    "configuration (h) makes the ink map soft, not the CORRECTION: "
    "ContextHead.apply_states takes int8 bins, so interpolating A5's "
    "per-bin offsets between integer bins is a detector change this "
    "instrument is forbidden to make; the expected neighbour count is "
    "rounded to A5's own nine bins instead",
    "configurations (f) and (h) REDEFINE what a Y bin means, so the "
    "incumbent A5 curve is being read at an index it was never fitted on; "
    "bins+head is the faithful arm for those two and bins is reported only "
    "for continuity with E4's table",
    "configuration (g) is a two-pass object: pass one records each "
    "capture's baseline Y decisions, pass two sums them per page cell and "
    "re-decodes; the consensus is therefore built from the SAME captures "
    "it is then used on, which is a receiver-legal but self-referential "
    "combination",
    "the six dead tiles and two controls are OUTCOME-SELECTED (they are "
    "where the residue is) and the controls are n = 2 physical tiles",
    "reference tiles are suppressed by the emission mask, so they can "
    "never mint a certificate; their column is the head's unemitted Y "
    "decision on payload cells at the region fit's own geometry — a "
    "regression control on the DETECTOR, not a decode",
    "rows pool tile x capture through the union, as everywhere in this "
    "campaign; three captures of one physical tile are not independent",
)


def _mean(values):
    rows = [float(v) for v in values
            if v is not None and not isinstance(v, bool) and np.isfinite(v)]
    return float(np.mean(rows)) if rows else None


# --------------------------------------------------------------------------
# the pre-registration
# --------------------------------------------------------------------------
def write_bar(path, geometries, configs, measured, tree_before) -> None:
    """The bar, on disk BEFORE the first capture is opened."""
    if path.is_file():
        return
    path.write_text(json.dumps({
        "schema": "plane-fields-context-loop-bar-v1",
        "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "geometries": list(geometries),
        "configurations": list(configs),
        "tiles": [f"{row.tile_y},{row.tile_x}/{row.role}"
                  for row in measured],
        "oracle_gain_pp_from_e4": E4_ORACLE_PP,
        "clause_1": (
            "a configuration earns a production-change proposal if it "
            "captures >= 50% of the oracle gain at G1 — that is, its dead "
            "mean moves <= -1.21 pp and its control mean <= -1.23 pp "
            "against configuration (a), being 50% of E4's -2.427 / -2.452 "
            "— WITH NO REGRESSION on the certified clean-column references "
            "(reference BER not above configuration (a)'s)"),
        "clause_2": (
            "OR it certifies any dead-band tile at G2, the production-like "
            "geometry, under the ordinary certificate gate (UNION, then "
            "RETRY150) — reported with certificate id, CRC and stage"),
        "verdict_rule": (
            "either clause is a pass; both clauses failing is a measured "
            "negative and is reported as one"),
        "controls": {
            "c": "C,M = GT — E4's method control; must move almost nothing",
            "z": (
                "Y NEIGHBOURHOOD TERM OFF (bins = -1, which A5 treats as "
                "no context and corrects by exactly zero).  DECLARED AFTER "
                "a one-tile, one-capture smoke run showed (h) capturing "
                "~90-100% of the oracle gain: a configuration that merely "
                "BLUNTS a miscalibrated Y term would look the same, and "
                "(z) is the geometry-free way to tell the two apart.  It "
                "is a control, not a candidate — the clauses above are "
                "unchanged, and (z) cannot 'pass' anything"),
        },
        "tree_before": tree_before,
    }, indent=1, sort_keys=True))
    print(f"pre-registered bar written to {path}")


def verdict(summary: dict, geometries) -> dict:
    """The bar, evaluated — mechanically, from the summary alone."""
    out: dict = {"by_configuration": {}, "passed": []}
    for name in _context_loop.CONFIGS:
        if name in ("a", "b", "c", "z"):
            continue
        row: dict = {}
        for arm in ("bins", "bins+head"):
            block = ((summary.get("G1") or {}).get("by_configuration", {})
                     .get(name, {}).get(arm))
            if block is None:
                continue
            # The clause was pre-registered against E4's PINNED oracle
            # gains, so that is what decides it; the run's own (b) span is
            # reported next to it and must agree, because (b) at G1 is E4's
            # (b) and the reproduction check asserts exactly that.
            dead_pp = block.get("dead_delta_pp")
            control_pp = block.get("control_delta_pp")
            regression = block.get("reference_delta_pp")
            row[arm] = {
                "dead_delta_pp": dead_pp,
                "control_delta_pp": control_pp,
                "dead_fraction_of_pinned_oracle": (
                    None if dead_pp is None
                    else dead_pp / E4_ORACLE_PP["dead"]),
                "control_fraction_of_pinned_oracle": (
                    None if control_pp is None
                    else control_pp / E4_ORACLE_PP["control"]),
                "dead_fraction_of_measured_oracle":
                    block.get("dead_oracle_fraction"),
                "control_fraction_of_measured_oracle":
                    block.get("control_oracle_fraction"),
                "reference_delta_pp": regression,
                "clause_1": bool(
                    dead_pp is not None and control_pp is not None
                    and dead_pp <= 0.5 * E4_ORACLE_PP["dead"]
                    and control_pp <= 0.5 * E4_ORACLE_PP["control"]
                    and (regression is None or regression <= 0.0)),
            }
        certificates = []
        for geometry in geometries:
            if geometry != "G2":
                continue
            for arm in ("bins", "bins+head"):
                block = ((summary.get("G2") or {}).get("by_configuration", {})
                         .get(name, {}).get(arm))
                if block is None:
                    continue
                certificates += [{**entry, "arm": arm}
                                 for entry in block.get("certificates", ())
                                 if entry.get("tile") and _is_dead(entry)]
        row["clause_2"] = bool(certificates)
        row["g2_dead_certificates"] = certificates
        row["passed"] = bool(row.get("clause_2") or any(
            value.get("clause_1") for value in row.values()
            if isinstance(value, dict)))
        out["by_configuration"][name] = row
        if row["passed"]:
            out["passed"].append(name)
    out["verdict"] = ("PASS: " + ", ".join(out["passed"])) if out["passed"] \
        else "MEASURED NEGATIVE — no configuration cleared either clause"
    return out


def _is_dead(entry) -> bool:
    from .detector_residue import DEAD_TILES

    return tuple(entry["tile"]) in {tuple(row) for row in DEAD_TILES}


# --------------------------------------------------------------------------
# the figure
# --------------------------------------------------------------------------
def draw_e8(path, union, geometries, *, gate: float, arm: str,
            n_captures: int) -> None:
    """Per tile, per configuration, at both geometries — one panel each."""
    panels = [(geometry, [row for row in union.get(geometry, ())
                          if "error" not in row])
              for geometry in geometries]
    panels = [(geometry, rows) for geometry, rows in panels if rows]
    if not panels:
        return
    font = _residue_figures._font
    names = [name for name in _context_loop.CONFIGS
             if any(name in row["configurations"]
                    for _geometry, rows in panels for row in rows)]
    width = max(1320, 190 + 150 * max(len(rows) for _g, rows in panels),
                110 + 155 * len(names))
    height = 100 + 400 * len(panels)
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    values = [row["configurations"][name]["arms"][arm]["ber"]
              for _geometry, rows in panels for row in rows
              for name in names if name in row["configurations"]]
    top = max([v for v in values if v is not None] + [gate]) * 1.18
    for index, (geometry, rows) in enumerate(panels):
        box = (86, 56 + 400 * index, width - 24, 320 + 400 * index)
        from ._context_loop_run import GEOMETRY_NAMES

        to_y = _residue_figures._axes(
            draw, box, (0.0, top),
            title=(f"E8 {geometry} — {GEOMETRY_NAMES[geometry]} "
                   f"({arm} arm)"),
            ylabel=(f"union cell error, {n_captures} capture"
                    f"{'' if n_captures == 1 else 's'}, against printed "
                    f"truth; the green band is the measured gate "
                    f"{100 * gate:.2f}% and below"))
        draw.rectangle((box[0] + 1, to_y(gate), box[2] - 1, box[3]), fill=GATE)
        draw.line((box[0], to_y(gate), box[2], to_y(gate)),
                  fill=(110, 160, 120))
        step = (box[2] - box[0]) / len(rows)
        span = 0.94 / max(1, len(names))
        for position, row in enumerate(rows):
            centre = box[0] + step * (position + 0.5)
            for order, name in enumerate(names):
                entry = (row["configurations"].get(name) or {}).get(
                    "arms", {}).get(arm)
                if entry is None or entry["ber"] is None:
                    continue
                offset = (order - (len(names) - 1) / 2.0) * span
                x0 = centre + (offset - span * 0.42) * step
                x1 = centre + (offset + span * 0.42) * step
                draw.rectangle((x0, to_y(entry["ber"]), x1, box[3]),
                               fill=CONFIG_COLOUR[name])
                label_y = to_y(entry["ber"]) - 13
                if entry["verdict"].get("certified"):
                    draw.text((x0 - 5, label_y), "CERT", fill=(20, 120, 40),
                              font=font(9))
                    label_y -= 11
                draw.text((x0 - 5, label_y), f"{100 * entry['ber']:.1f}",
                          fill=INK, font=font(9))
            draw.text((centre - 20, box[3] + 8),
                      f"{row['tile_y']},{row['tile_x']}", fill=INK,
                      font=font(13))
            draw.text((centre - 22, box[3] + 25),
                      "dead" if row["role"] == "target" else "control",
                      fill=GREY, font=font(11))
    for order, name in enumerate(names):
        left = 86 + 155 * order
        draw.rectangle((left, height - 44, left + 12, height - 33),
                       fill=CONFIG_COLOUR[name], outline=GREY)
        draw.text((left + 17, height - 45), f"({name})", fill=INK,
                  font=font(11))
        draw.text((left + 17, height - 32),
                  _context_loop.CONFIG_NAMES[name][:22], fill=GREY,
                  font=font(9))
    image.save(path)


# --------------------------------------------------------------------------
# the text tables
# --------------------------------------------------------------------------
def _rate(value, width: int = 7) -> str:
    return " " * width if value is None else f"{100 * value:{width}.2f}"


def _signed(value, width: int = 6) -> str:
    return " " * width if value is None else f"{value:+{width}.2f}"


def _fraction(value, width: int = 6) -> str:
    return " " * width if value is None else f"{100 * value:{width - 1}.0f}%"


def geometry_table(summary: dict, rows: list[dict], geometry: str, *,
                   arm: str) -> str:
    block = summary.get(geometry)
    if block is None:
        return ""
    lines = [
        f"{geometry} — {block['name']}   [{arm} arm]",
        "config                              |   dead  ctrl    gap    "
        "dΔdead  dΔctrl  %oracle-d %oracle-c   refBER  refΔ  cert d/c",
        "-" * 128]
    for name, entry in block["by_configuration"].items():
        row = entry[arm]
        reference = row.get("reference") or {}
        lines.append(
            f"({name:<2}) {_context_loop.CONFIG_NAMES[name]:<31}"
            f"| {_rate(row['dead_mean'], 6)} {_rate(row['control_mean'], 5)}"
            f"  {_signed(row['gap_pp'])}  {_signed(row['dead_delta_pp'])}"
            f"  {_signed(row['control_delta_pp'])}"
            f"   {_fraction(row['dead_oracle_fraction'], 8)}"
            f"  {_fraction(row['control_oracle_fraction'], 8)}"
            f"  {_rate(reference.get('ber'), 7)}"
            f" {_signed(row.get('reference_delta_pp'), 5)}"
            f"   {row['certified_dead']}/{row['certified_control']}")
    lines.append("-" * 128)
    lines.append("per tile (union cell error, %):")
    names = list(block["by_configuration"])
    lines.append("  tile   band     " + "".join(f"{'(' + n + ')':>9}"
                                                for n in names))
    for row in rows:
        if "error" in row:
            continue
        cells = "".join(
            f"{_rate((row['configurations'].get(name) or {}).get('arms', {}).get(arm, {}).get('ber'), 9)}"
            for name in names)
        marks = "".join(
            " C" if ((row['configurations'].get(name) or {})
                     .get('arms', {}).get(arm, {}).get('verdict') or {}
                     ).get('certified') else "  "
            for name in names)
        lines.append(
            f"  {row['tile_y']:>2},{row['tile_x']:<3} "
            f"{'dead' if row['role'] == 'target' else 'control':<8} {cells}"
            f"   {marks}")
    return "\n".join(lines)


def convergence_table(per_capture, geometries) -> str:
    lines = ["iteration convergence (fraction of the lattice's Y bins that "
             "still move):",
             "geometry capture      tile     bins a->e1  bins e1->e2   "
             "ink a->e1   ink e1->e2", "-" * 92]
    for geometry in geometries:
        for sha, capture in sorted(per_capture.items()):
            block = capture["geometries"].get(geometry) or {}
            rows = {}
            if geometry == "G2" and "convergence" in (block.get("region") or {}):
                rows["all"] = block["region"]["convergence"]
            for key, tile in sorted((block.get("tiles") or {}).items()):
                if "convergence" in tile:
                    rows[key] = tile["convergence"]
            for key, row in rows.items():
                lines.append(
                    f"{geometry:<8} {sha[:12]} {key:<9} "
                    f"{100 * row['y_bins_changed_a_to_e1']:9.2f}%  "
                    f"{100 * row['y_bins_changed_e1_to_e2']:10.2f}%  "
                    f"{100 * row['y_ink_changed_a_to_e1']:9.2f}%  "
                    f"{100 * row['y_ink_changed_e1_to_e2']:10.2f}%")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# the writer
# --------------------------------------------------------------------------
def write_outputs(args, facts, spec, lane, coverage, scans, ceiling, measured,
                  references, residue, truth_report, per_capture, union,
                  summary, reproduction, tree_before, started, *,
                  geometries, configs, failures=()) -> int:
    from ._context_loop_run import E4_JSON, GATE_BER, OUT_DIR, SCHEMA
    from .detector_residue import GT_AFFINE

    tree_after = _swim_inputs.tree_state()
    bar = verdict(summary, geometries)
    document = {
        "schema": SCHEMA,
        "state": {"path": str(QUAL_STATE), "sha256": facts.state_sha256,
                  "close": facts.close_status,
                  "payload_sha256": facts.payload_sha256,
                  "certificates": len(facts.certificates)},
        "format": {"ref": FORMAT_REF, "spec_id": spec.spec_id,
                   "tiles_yx": list(spec.layout.tiles_yx),
                   "cell_dots": spec.cell_dots, "dpi": CAPTURE_DPI},
        "lane": {"lane_id": lane.lane_id,
                 "target_coverage_by_capture": list(coverage)},
        "inputs": {
            "scans": {sha: str(path) for sha, path in scans.items()},
            "gt_affine": str(GT_AFFINE),
            "gt_affine_sha256": _swim_inputs.sha256_file(GT_AFFINE),
            "e4": str(E4_JSON),
            "e4_sha256": (_swim_inputs.sha256_file(E4_JSON)
                          if E4_JSON.is_file() else None),
            "recovered_payload": str(QUAL_STATE.parent / "recovered.bin"),
            "recovered_payload_sha256": _swim_inputs.sha256_file(
                QUAL_STATE.parent / "recovered.bin"),
        },
        "geometries": list(geometries),
        "configurations": list(configs),
        "dead_bands": list(DEAD_BANDS),
        "measured_tiles": [
            {"tile_y": row.tile_y, "tile_x": row.tile_x, "stream": row.stream,
             "band": row.band, "role": row.role} for row in measured],
        "reference_tiles": [[ty, tx] for _pg, ty, tx in references],
        "residue_by_column": residue,
        "workers": int(args.workers),
        "approximations": list(APPROXIMATIONS),
        "truth_field": truth_report,
        "e8": {"union": union, "summary": summary,
               "reproduction_of_e4": reproduction, "bar": bar,
               "pass_failures": list(failures)},
        "per_capture": per_capture,
        "tree_before": tree_before,
        "tree_after": tree_after,
        "tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "wall_seconds": round(time.time() - started, 1),
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "e8.json").write_text(
        json.dumps(document, indent=1, sort_keys=True, default=str))
    for arm in ("bins", "bins+head"):
        draw_e8(OUT_DIR / f"e8-ber{'-head' if arm != 'bins' else ''}.png",
                union, geometries, gate=GATE_BER, arm=arm,
                n_captures=len(per_capture))
    tables = "\n\n".join(
        [geometry_table(summary, union.get(geometry, ()), geometry, arm=arm)
         for arm in ("bins", "bins+head") for geometry in geometries
         if summary.get(geometry)]
        + [convergence_table(per_capture, geometries),
           "verdict against the pre-registered bar: " + bar["verdict"]]) + "\n"
    (OUT_DIR / "tables.txt").write_text(tables)
    print("\n" + tables)
    print(f"reproduction of E4 at G1 (a)/(b): {reproduction.get('checked')} "
          f"comparisons, max |gap| {reproduction.get('max_abs_gap')}")
    print(f"\nwrote {OUT_DIR}/e8.json, e8-ber.png, tables.txt "
          f"({document['wall_seconds']:.0f}s, peak RSS "
          f"{document['peak_rss_gb']} GB)")
    return 0


__all__ = ["APPROXIMATIONS", "E4_ORACLE_PP", "convergence_table", "draw_e8",
           "geometry_table", "verdict", "write_bar", "write_outputs"]

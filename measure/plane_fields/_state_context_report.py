"""E3'/E4 outputs: the two JSON files, the E4 figure, the text tables.

Kept out of the run driver so the expensive rows are on disk (``raw.json``)
before any reduction can fail on them — the P2 rule, after forty minutes
of decoding once died inside a summary.
"""
from __future__ import annotations

import json
import resource
import time

import numpy as np
from PIL import Image, ImageDraw

from . import _context_gt, _residue_figures, _state_tables, _swim_inputs
from ._swim_inputs import CAPTURE_DPI, DEAD_BANDS, FORMAT_REF, QUAL_STATE

BG = (255, 255, 255)
INK = (30, 30, 30)
GREY = (120, 120, 120)
GATE = (198, 232, 205)
CONFIG_COLOUR = {"a": (110, 130, 200), "b": (205, 95, 55),
                 "c": (150, 150, 150), "d": (90, 150, 90)}
APPROXIMATIONS = (
    "restricted region: the detector is fitted over the windows within "
    "--fit-radius tiles of a target, exactly as gt_affine and P2 did",
    "the footing is E1's REFIT arm: the whole restricted region is re-fitted "
    "with the target tile sampled at its supervised 6-dof affine + BER "
    "polish, so the registration fit, the QDA/PAVA stack and the A5 context "
    "bins all see the corrected geometry",
    "the geometry under test is SUPERVISED (fitted against the printed "
    "truth): a ceiling, not a receiver",
    "E3' pools (tile x capture) rows as if independent; three captures of "
    "one physical tile are not — n_tiles is carried next to n_rows",
    "E3''s oracle is a per-(C,M)-stratum threshold on the RAW Y channel at "
    "the same geometry, fitted with full knowledge of the Y bits; the "
    "production column is the calibrated head's own hard decision on the "
    "same deduplicated cells",
    "the six dead tiles and two controls are OUTCOME-SELECTED (they are "
    "where the residue is); the certified references are not, and are "
    "carried for that reason",
    "certified reference tiles are SUPPRESSED by the emission mask, so "
    "their production column is the head's unemitted output at the "
    "reference's own fitted affine, on the FROZEN detector (bins cut at "
    "delta = 0) — E3's footing for those tiles, not E1's refit",
    "A3 (per-window photometry) is OVERRIDE-ONLY in production: no lane in "
    "this state ever fitted a window map, so its table is what the u-a3 "
    "supplemental lane WOULD find, never what the archived decode did",
)


def _mean(values):
    rows = [float(v) for v in values
            if v is not None and not isinstance(v, bool) and np.isfinite(v)]
    return float(np.mean(rows)) if rows else None


# --------------------------------------------------------------------------
# the figure
# --------------------------------------------------------------------------
def draw_e4(path, rows: list[dict], *, gate: float, arm: str = "bins",
            n_captures: int = 3) -> None:
    """Per tile, the union Y cell error under configurations a-d."""
    rows = [row for row in rows if "error" not in row]
    if not rows:
        return
    font = _residue_figures._font
    width, height = max(1240, 150 + 138 * len(rows)), 520
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    box = (86, 66, width - 24, height - 108)
    values = [row["configurations"][name]["arms"][arm]["ber"]
              for row in rows for name in _context_gt.CONFIGS]
    top = max([v for v in values if v is not None] + [gate]) * 1.2
    to_y = _residue_figures._axes(
        draw, box, (0.0, top),
        title=("E4: the Y-context circularity — A5's ink map with "
               f"ground-truth columns ({arm} arm)"),
        ylabel=(f"union cell error, {n_captures} capture"
                f"{'' if n_captures == 1 else 's'}, against printed truth; "
                f"the green band is the measured gate "
                f"{100 * gate:.2f}% and below"))
    draw.rectangle((box[0] + 1, to_y(gate), box[2] - 1, box[3]), fill=GATE)
    draw.line((box[0], to_y(gate), box[2], to_y(gate)), fill=(110, 160, 120))
    step = (box[2] - box[0]) / len(rows)
    names = tuple(_context_gt.CONFIGS)
    for position, row in enumerate(rows):
        centre = box[0] + step * (position + 0.5)
        for index, name in enumerate(names):
            entry = row["configurations"][name]["arms"][arm]
            value = entry["ber"]
            if value is None:
                continue
            offset = (index - (len(names) - 1) / 2.0) * 0.21
            x0 = centre + offset * step - 0.095 * step
            x1 = centre + offset * step + 0.095 * step
            draw.rectangle((x0, to_y(value), x1, box[3]),
                           fill=CONFIG_COLOUR[name])
            label_y = to_y(value) - 14
            if entry["verdict"].get("certified"):
                draw.text((x0 - 4, label_y), "CERT", fill=(20, 120, 40),
                          font=font(10))
                label_y -= 12
            draw.text((x0 - 6, label_y), f"{100 * value:.2f}", fill=INK,
                      font=font(10))
        draw.text((centre - 20, box[3] + 8),
                  f"{row['tile_y']},{row['tile_x']}", fill=INK, font=font(13))
        draw.text((centre - 22, box[3] + 25),
                  "dead" if row["role"] == "target" else "control",
                  fill=GREY, font=font(11))
    for index, name in enumerate(names):
        draw.rectangle((box[0] + 300 * index, height - 44,
                        box[0] + 300 * index + 12, height - 33),
                       fill=CONFIG_COLOUR[name], outline=GREY)
        draw.text((box[0] + 300 * index + 18, height - 45),
                  f"({name}) {_context_gt.CONFIG_NAMES[name]}", fill=INK,
                  font=font(11))
    image.save(path)


# --------------------------------------------------------------------------
# the text tables
# --------------------------------------------------------------------------
def _rate(value, width: int = 7) -> str:
    return " " * width if value is None else f"{100 * value:{width}.2f}"


GROUPS = ("dead", "control", "reference")


def e3prime_table(summary: dict) -> str:
    """state x {dead, control, reference}: n_k, a_k, production, oracle."""
    qda = summary.get("qda_reference") or {}
    header = ("state |   n_k       a_k   | "
              + " | ".join(f"{group:^30}" for group in GROUPS))
    lines = [header,
             "      |                   | "
             + " | ".join(f"{'n':>7} {'prod':>7} {'oracle':>7} {'gap':>6}"
                          for _ in GROUPS),
             "-" * len(header)]
    groups = summary["by_group"]
    for state in range(_state_tables.N_STATES):
        name = _state_tables.STATE_LABELS[state]
        entry = qda.get(str(state)) or qda.get(state) or {}
        row = (f" {name}  | {entry.get('n_train', 0):>7d} "
               f"{entry.get('a_k', float('nan')):9.2e} |")
        for group in GROUPS:
            block = groups.get(group)
            if block is None:
                row += f" {'—':^30} |"
                continue
            cell = block["by_state"][state]
            row += (f" {cell['n_cells_total']:>7d} "
                    f"{_rate(cell['production_error'])} "
                    f"{_rate(cell['oracle_error'])} "
                    f"{_rate(cell['gap'], 6)} |")
        lines.append(row)
    lines.append("-" * len(header))
    for group in GROUPS:
        block = groups.get(group)
        if block is None:
            continue
        lines.append(
            f"{group:<10} n_rows {block['n_rows']:>2d} n_tiles "
            f"{block['n_tiles']:>2d}  production "
            f"{100 * block['production_ber']:.2f}%"
            f"  per-stratum oracle {100 * block['oracle_ber']:.2f}%"
            f"  gap {block['gap_pp']:+.2f} pp")
    lines.append(
        "n_k/a_k: the QDA's TRAINING count and covariance shrinkage "
        "a_k = min(1, (D+2)/n_k), D = 3; identical for every arm and every "
        "refit of one capture (a pure function of the ownership split).")
    lines.append(
        "prod: the calibrated head's hard Y decision; oracle: the best "
        "threshold on the raw Y channel fitted PER (C,M) STRATUM with full "
        "knowledge of the Y bits.  gap = prod - oracle, in pp.")
    return "\n".join(lines)


SHORT_CONFIG = {"a": "baseline (provisional)", "b": "Y = GT",
                "c": "C,M = GT (control)", "d": "all three = GT"}


def e4_table(summary: dict, rows: list[dict], *, arm: str = "bins") -> str:
    lines = [f"configuration              | dead    control  gap(pp)  "
             f"closed(pp)  cert d/c   [{arm} arm]", "-" * 92]
    for name, entry in summary["by_configuration"].items():
        block = entry[arm]
        def signed(value, width: int = 6) -> str:
            return " " * width if value is None else f"{value:+{width}.2f}"

        lines.append(
            f"({name}) {SHORT_CONFIG[name]:<23}"
            f"| {_rate(block['dead_mean'], 6)}  {_rate(block['control_mean'], 6)}"
            f"   {signed(block['gap_pp'])}   {signed(block['gap_closed_pp'])}"
            f"      {block['certified_dead']}/{block['certified_control']}")
    lines.append("-" * 92)
    lines.append("per tile (union cell error, %):")
    header = "  tile   band     " + "  ".join(
        f"  ({name})" for name in _context_gt.CONFIGS)
    lines.append(header)
    for row in rows:
        if "error" in row:
            continue
        cells = "  ".join(
            f"{_rate(row['configurations'][name]['arms'][arm]['ber'], 7)}"
            for name in _context_gt.CONFIGS)
        lines.append(
            f"  {row['tile_y']:>2},{row['tile_x']:<3} "
            f"{'dead' if row['role'] == 'target' else 'control':<8} {cells}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# the writer
# --------------------------------------------------------------------------
def write_outputs(args, facts, spec, lane, coverage, scans, ceiling, measured,
                  references, residue, truth_report, per_capture, e4,
                  tree_before, started, *, summaries) -> int:
    from ._state_context_run import E1_REFIT, GATE_BER, OUT_DIR, SCHEMA
    from .detector_residue import GT_AFFINE

    e3prime, e4_summary, reproduction = summaries
    # The QDA reference column of the E3' table: n_k and a_k are pure
    # functions of the ownership split, so they are identical for every
    # arm and every refit of one capture's region — the first capture's
    # first region is the whole story, and the JSON carries all of them.
    reference_qda = None
    for capture in per_capture.values():
        for region in capture["region"].values():
            if "qda" in region:
                reference_qda = {str(row["state"]): row
                                 for row in region["qda"]["states"]}
                break
        if reference_qda:
            break
    e3prime["qda_reference"] = reference_qda or {}

    tree_after = _swim_inputs.tree_state()
    common = {
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
            "gt_affine_tree_before": ceiling.get("tree_before"),
            "e1_refit": str(E1_REFIT),
            "e1_refit_sha256": (_swim_inputs.sha256_file(E1_REFIT)
                                if E1_REFIT.is_file() else None),
            "recovered_payload": str(QUAL_STATE.parent / "recovered.bin"),
            "recovered_payload_sha256": _swim_inputs.sha256_file(
                QUAL_STATE.parent / "recovered.bin"),
        },
        "dead_bands": list(DEAD_BANDS),
        "measured_tiles": [
            {"tile_y": row.tile_y, "tile_x": row.tile_x, "stream": row.stream,
             "band": row.band, "role": row.role} for row in measured],
        "reference_tiles": [[ty, tx] for _pg, ty, tx in references],
        "workers": int(args.workers),
        "approximations": list(APPROXIMATIONS),
        "truth_field": truth_report,
        "tree_before": tree_before,
        "tree_after": tree_after,
        "tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "wall_seconds": round(time.time() - started, 1),
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "e3prime.json").write_text(json.dumps(
        {**common, "residue_by_column": residue,
         "e3prime": e3prime,
         "per_capture": {sha: {"region": capture["region"],
                               "tiles": capture["e3prime"],
                               "references": capture["references"]}
                         for sha, capture in per_capture.items()}},
        indent=1, sort_keys=True, default=str))
    (OUT_DIR / "e4.json").write_text(json.dumps(
        {**common, "e4": {"rows": e4, "summary": e4_summary,
                          "reproduction_of_e1_refit": reproduction},
         "per_capture": {sha: capture["e4"]
                         for sha, capture in per_capture.items()}},
        indent=1, sort_keys=True, default=str))
    draw_e4(OUT_DIR / "e4-ber.png", e4, gate=GATE_BER, arm="bins",
            n_captures=len(per_capture))
    draw_e4(OUT_DIR / "e4-ber-head.png", e4, gate=GATE_BER, arm="bins+head",
            n_captures=len(per_capture))
    tables = (e3prime_table(e3prime) + "\n\n"
              + e4_table(e4_summary, e4, arm="bins") + "\n\n"
              + e4_table(e4_summary, e4, arm="bins+head") + "\n")
    (OUT_DIR / "tables.txt").write_text(tables)
    print("\n" + tables)
    print(f"reproduction of E1's refit arm at configuration (a): "
          f"{reproduction.get('checked')} tiles, max |gap| "
          f"{reproduction.get('max_abs_gap')}")
    print(f"\nwrote {OUT_DIR}/e3prime.json, e4.json, e4-ber.png, tables.txt "
          f"({common['wall_seconds']:.0f}s, peak RSS "
          f"{common['peak_rss_gb']} GB)")
    return 0


__all__ = ["APPROXIMATIONS", "draw_e4", "e3prime_table", "e4_table",
           "write_outputs"]

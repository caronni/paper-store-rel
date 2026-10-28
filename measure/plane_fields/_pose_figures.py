"""The P5 pose-writer figure: the residual, the yield, and the BER (PIL).

matplotlib is not in this env (the house style of ``_figures`` and
``_density_figures``), so everything is drawn with PIL out of the run
JSON -- nothing is recomputed here, and ``--figure-only`` re-cuts the
illustration without re-running a measurement.

Four panels: the per-window plane-common residual the writer would
consume (split by window kind, because only a MIXED window can change a
decode), the certificates each configuration won, the cell-BER change
BINNED BY THE RESIDUAL that produced it -- the panel that carries the
finding, since the damage grows with the correction's own size -- and the
mean BER over the strata that matter.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

GREY = (120, 120, 120)
DARK = (55, 55, 55)
COLOR = {
    "committed": (110, 110, 110),
    "field": (30, 90, 190),
    "field+pose-t": (20, 140, 70),
    "field+pose-affine": (200, 80, 30),
    "field-diff": (150, 110, 200),
    "field-diff+pose-t": (110, 60, 160),
}
SHORT = {"committed": "(i) committed", "field": "(ii) field",
         "field+pose-t": "(iii) +pose t", "field+pose-affine": "(iv) +pose af",
         "field-diff": "(v) diff fld", "field-diff+pose-t": "(vi) diff+pose"}
STRATA = (("all", "all slots"), ("dead_band", "dead band"),
          ("windows_agree", "sites agree"),
          ("residual_above_median", "residual > median"))


def _frame(draw, box, title, unit):
    left, top, right, bottom = box
    draw.text((left, top - 34), title, fill="black")
    draw.text((left, top - 18), unit, fill=GREY)
    draw.rectangle((left, top, right, bottom), outline=(210, 210, 210))
    return left, top, right, bottom


def _legend(draw, x, y, entries, *, step=150):
    for offset, (label, color) in enumerate(entries):
        left = x + offset * step
        draw.rectangle((left, y, left + 11, y + 10), fill=color)
        draw.text((left + 15, y - 1), label, fill=DARK)


def _bars(draw, box, labels, values, colors, *, title, unit, fmt="{:.0f}",
          gap=0.18):
    left, top, right, bottom = _frame(draw, box, title, unit)
    finite = [value for value in values if np.isfinite(value)]
    top_value = max(finite) if finite and max(finite) > 0 else 1.0
    step = (right - left) / max(1, len(values))
    for index, (label, value, color) in enumerate(
            zip(labels, values, colors, strict=True)):
        x0 = left + index * step + step * gap
        x1 = left + (index + 1) * step - step * gap
        height = 0.0 if not np.isfinite(value) else (
            (bottom - top - 18) * max(0.0, value) / top_value)
        draw.rectangle((x0, bottom - height, x1, bottom), fill=color)
        draw.text((x0, bottom - height - 13),
                  fmt.format(value) if np.isfinite(value) else "—", fill=DARK)
        if label:
            draw.text((x0, bottom + 4), label, fill=DARK)


def _grouped(draw, box, groups, names, values, *, title, unit, fmt="{:.1f}"):
    """One cluster of bars per stratum, one bar per configuration."""
    left, top, right, bottom = _frame(draw, box, title, unit)
    flat = [value for row in values for value in row if np.isfinite(value)]
    top_value = max(flat) if flat and max(flat) > 0 else 1.0
    span = (right - left) / max(1, len(groups))
    width = span * 0.82 / max(1, len(names))
    for index, (label, row) in enumerate(zip(groups, values, strict=True)):
        base = left + index * span + span * 0.09
        for offset, (name, value) in enumerate(zip(names, row, strict=True)):
            x0 = base + offset * width
            height = 0.0 if not np.isfinite(value) else (
                (bottom - top - 16) * max(0.0, value) / top_value)
            draw.rectangle((x0, bottom - height, x0 + width - 1, bottom),
                           fill=COLOR.get(name, DARK))
            if offset in (0, len(names) - 1) and np.isfinite(value):
                draw.text((x0 - 4, bottom - height - 13), fmt.format(value),
                          fill=DARK)
        draw.text((base, bottom + 4), label, fill=DARK)
        if index:
            x = left + index * span
            draw.line((x, top, x, bottom), fill=(230, 230, 230))


def _histogram(draw, box, series, *, title, unit, cut=None, top_x=1.0):
    left, top, right, bottom = _frame(draw, box, title, unit)
    bins = 32
    edges = np.linspace(0.0, top_x, bins + 1)
    stacks = [(label, np.histogram(np.clip(values, 0, top_x), bins=edges)[0],
               color) for label, values, color in series]
    total = np.sum([counts for _l, counts, _c in stacks], axis=0)
    peak = max(int(total.max()) if total.size else 1, 1)
    width = (right - left) / bins
    floor = np.zeros(bins)
    for _label, counts, color in stacks:
        for index in range(bins):
            height = (bottom - top - 6) * counts[index] / peak
            base = (bottom - top - 6) * floor[index] / peak
            if height <= 0:
                continue
            draw.rectangle((left + index * width, bottom - base - height,
                            left + (index + 1) * width - 1, bottom - base),
                           fill=color)
        floor = floor + counts
    if cut is not None and 0 <= cut <= top_x:
        x = left + (right - left) * cut / top_x
        draw.line((x, top, x, bottom), fill=(200, 40, 40))
        draw.text((x + 3, top + 4), f"{cut:g} dot adoption cliff",
                  fill=(200, 40, 40))
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        draw.text((left + (right - left) * fraction - 10, bottom + 4),
                  f"{fraction * top_x:.2f}", fill=GREY)


def _delta_by_bin(draw, box, bins, names, values, *, title, unit):
    """Signed cell-BER change per residual bin; up is WORSE."""
    left, top, right, bottom = _frame(draw, box, title, unit)
    zero = bottom - 22
    flat = [abs(value) for row in values for value in row
            if np.isfinite(value)]
    span = max(flat) if flat and max(flat) > 0 else 1.0
    step = (right - left) / max(1, len(bins))
    width = step * 0.8 / max(1, len(names))
    draw.line((left, zero, right, zero), fill=(160, 160, 160))
    for index, (label, row) in enumerate(zip(bins, values, strict=True)):
        base = left + index * step + step * 0.1
        for offset, (name, value) in enumerate(zip(names, row, strict=True)):
            if not np.isfinite(value):
                continue
            x0 = base + offset * width
            height = (zero - top - 14) * value / span
            draw.rectangle(
                (x0, min(zero, zero - height), x0 + width - 1,
                 max(zero, zero - height)), fill=COLOR.get(name, DARK))
        draw.text((base, bottom - 15), label, fill=DARK)
    draw.text((left + 4, top + 2), f"+{span:.2f} pp  (WORSE than baseline)",
              fill=GREY)


def draw(document: dict, path: Path) -> Path:
    footing = document.get("frozen") or {}
    rows = footing.get("per_slot") or []
    table = (footing.get("summary") or {}).get("by_stratum", {})
    # The result JSON is written sorted; restore the ladder's own order.
    order = document["method"]["configurations"]
    present = table.get("all", {}).get("certified", {})
    names = ([name for name in order if name in present]
             + [name for name in present if name not in order])
    baseline = document["pre_registered_bar"]["baseline_configuration"]
    others = [name for name in names if name not in (baseline, "committed")]

    width, height = 1560, 880
    image = Image.new("RGB", (width, height), "white")
    canvas = ImageDraw.Draw(image)
    state = document["state"]
    canvas.text((14, 10),
                "P5 bar -- the POSE WRITER: the per-window plane-common probe "
                "residual fed back to the window pose", fill="black")
    canvas.text((14, 26),
                f"W6 sheet-I state {state['sha256'][:12]}… {state['close']}, "
                f"{state['certificates']} certificates; lane "
                f"{document['lane']['lane_id']}; {document['slots']['open']} "
                f"open (tile, stream) slots over {document['slots']['tiles']} "
                f"tiles; {len(document['captures'])} captures unioned; "
                f"frozen-detector footing", fill=GREY)

    kinds: dict[str, list] = {"label-only": [], "mixed": []}
    for capture in document.get("window_poses", ()):
        for entry in capture.values():
            kinds.setdefault(entry["window_kind"], []).append(
                entry["magnitude_dots"])
    _histogram(
        canvas, (60, 120, 740, 340),
        [("mixed", np.asarray(kinds["mixed"]), (30, 90, 190)),
         ("label-only", np.asarray(kinds["label-only"]), (150, 180, 220))],
        title="1  per-window plane-common residual, all three captures",
        unit="print dots, window LOCAL frame — the correction a writer "
             "would apply", cut=0.25, top_x=1.0)
    _legend(canvas, 64, 356,
            [("mixed windows (can win a slot)", (30, 90, 190)),
             ("label-only windows", (150, 180, 220))], step=230)

    all_row = table.get("all", {})
    _bars(canvas, (830, 120, 1500, 340),
          [SHORT.get(name, name) for name in names],
          [all_row.get("certified", {}).get(name, 0) for name in names],
          [COLOR.get(name, DARK) for name in names],
          title="2  certificates won, all open slots",
          unit=f"of {all_row.get('slots', 0)} slots; baseline = "
               f"{SHORT.get(baseline, baseline)}")

    cuts = [0.0, 0.12, 0.18, 0.24, 0.32, 10.0]
    labels = ["<.12", ".12-.18", ".18-.24", ".24-.32", ">.32"]
    deltas: list[list[float]] = []
    for index in range(len(labels)):
        subset = [
            row for row in rows
            if row.get("window_residual_dots_mean") is not None
            and cuts[index] <= row["window_residual_dots_mean"] < cuts[
                index + 1]]
        entry = []
        for name in others:
            pairs = [
                (row["configurations"][name]["ber"],
                 row["configurations"][baseline]["ber"])
                for row in subset
                if row["configurations"][name].get("ber") is not None
                and row["configurations"][baseline].get("ber") is not None]
            entry.append(float("nan") if not pairs else 100.0 * float(
                np.mean([left - right for left, right in pairs])))
        deltas.append(entry)
    _delta_by_bin(
        canvas, (60, 420, 740, 660), labels, others, deltas,
        title="3  cell-BER change vs the baseline, BINNED BY THE RESIDUAL",
        unit="x: mean plane-common residual of the covering windows (dots); "
             "bars above the line are WORSE than (ii)")
    _legend(canvas, 64, 676,
            [(SHORT.get(name, name), COLOR.get(name, DARK))
             for name in others], step=165)

    _grouped(
        canvas, (830, 420, 1500, 660), [label for _key, label in STRATA],
        names,
        [[(None if table.get(key, {}).get("mean_ber", {}).get(name) is None
           else 100.0 * table[key]["mean_ber"][name]) or float("nan")
          for name in names] for key, _label in STRATA],
        title="4  mean cell BER by stratum and configuration",
        unit="percent; the leftmost and rightmost bar of each cluster are "
             "labelled")
    _legend(canvas, 834, 676,
            [(SHORT.get(name, name), COLOR.get(name, DARK))
             for name in names[:3]], step=165)
    _legend(canvas, 834, 692,
            [(SHORT.get(name, name), COLOR.get(name, DARK))
             for name in names[3:]], step=165)

    verdict_row = footing.get("verdict") or {}
    refit = document.get("refit")
    lines = [
        "PRE-REGISTERED BAR (declared before the run, "
        f"{document['pre_registered_bar']['certificate_increment_slots']} "
        "slots beyond (ii), or a "
        f"{document['pre_registered_bar']['dead_band_mean_ber_reduction_pp']}"
        " pp dead-band BER reduction):",
        "   certificate increment over (ii): " + ", ".join(
            f"{SHORT.get(k, k)} {v:+d}"
            for k, v in verdict_row.get("certificate_increment", {}).items())
        + "     dead-band BER reduction: " + ", ".join(
            f"{SHORT.get(k, k)} " + ("—" if v is None else f"{v:+.2f} pp")
            for k, v in verdict_row.get(
                "dead_band_ber_reduction_pp", {}).items()),
        "   exploratory arms (declared, outside the clause): " + ", ".join(
            f"{SHORT.get(k, k)} {v:+d} slots" for k, v in verdict_row.get(
                "exploratory_certificate_increment", {}).items()),
    ]
    if refit:
        refit_table = refit["summary"]["by_stratum"]["all"]
        lines.append(
            "   E1 REFIT footing (registration, QDA/PAVA and the A5 bins "
            "recut at the corrected geometry): " + ", ".join(
                f"{SHORT.get(name, name)} {value} certs / "
                f"{100 * refit_table['mean_ber'][name]:.2f}% BER"
                for name, value in refit_table["certified"].items()))
    lines.append("")
    lines.append(
        "VERDICT: " + ("PASSED" if verdict_row.get("passed") else
                       "MEASURED NEGATIVE on this sheet — every pose arm "
                       "raises the cell BER, and the damage GROWS with the "
                       "residual it applies (panel 3)."))
    y = 740
    for line in lines:
        canvas.text((60, y), line[:210], fill=DARK if line else GREY)
        y += 16
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


__all__ = ["draw"]

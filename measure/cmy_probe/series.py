"""The bar verdict read per toner (CMY-PROBE-M281 §9): the three named ratios that matter per toner, the cyan
and yellow series, the magenta grid, and a proposed value per toner.

The named ratios (whitened whole-bar ratio at one screen family in one ink density, measure/cmy_probe/
stipples.py; a tuple of densities takes the largest):
  C: the yellow stipple Y213@45 in Y, the cyan's own screen 165@14 in C, magenta dots 165@14 in M;
  M: the yellow stipple Y213@45 in Y, cyan dots 165@14 in C, the magenta's own screen 165@14 in M;
  Y: the dark dots dots160@42 in C or M, the line screen lines196@90 in C or M, the yellow stipple Y213@45
     in Y (043.3c: dark dots and lines in C and M on every off-corner yellow).
Series: per toner, construct and single-axis ladder (axis R, G, B or RG; sheet 1's eleven, sheet 2's cyan G
and yellow B), per swept value the three ratios and the verdict.  Grid: the bars with axis "grid" (sheet 2's
magenta R x B), one table per construct, cell = the three ratios.  Proposal per toner: among the toner's
clean sweep, grid and registry bars, the one with the smallest sum of its three ratios, ties to the one
nearest the registry value (L1 in device RGB); the registry value's own bars (every construct) beside it.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from measure.cmy_probe.bars import AXIS_CHANNELS, ladder_key, swept_value

#: toner -> ((label, densities, family), ...) — the three ratios per toner
KEY_RATIOS: dict[str, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "C": (("yellow", ("Y",), "Y213@45"), ("own", ("C",), "165@14"), ("magenta", ("M",), "165@14")),
    "M": (("yellow", ("Y",), "Y213@45"), ("cyan", ("C",), "165@14"), ("own", ("M",), "165@14")),
    "Y": (("dots", ("C", "M"), "dots160@42"), ("lines", ("C", "M"), "lines196@90"), ("yellow", ("Y",), "Y213@45")),
}


def key_ratios(bar: dict[str, Any]) -> dict[str, float]:
    """{label: ratio} of the bar's toner (empty for a bar without a toner of KEY_RATIOS)."""
    spec = KEY_RATIOS.get(str(bar.get("toner")))
    if not spec:
        return {}
    fam = bar["families"]
    return {lab: max(float(fam[ch][f]) for ch in chans) for lab, chans, f in spec}


def ratio_sum(bar: dict[str, Any]) -> float:
    v = list(key_ratios(bar).values())
    return float(sum(v)) if v and all(np.isfinite(v)) else float("nan")


def _row(bar: dict[str, Any]) -> dict[str, Any]:
    return {"id": bar["id"], "rgb": bar["rgb"], "construct": bar.get("construct"), "kind": bar["kind"],
            "ratios": key_ratios(bar), "sum": ratio_sum(bar), "verdict": bar["verdict"],
            "worst_channel": bar["worst_channel"], "worst_family": bar["worst_family"],
            "worst_ratio": bar["worst_ratio"], "specks_max": bar.get("specks_max"), "specks_density": bar.get("specks_density")}


def series_report(bars: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """toner -> ladder key (with construct) -> rows ordered by swept value."""
    out: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for b in bars:
        if b["kind"] == "sweep" and b.get("axis") in AXIS_CHANNELS and b.get("rgb") and b.get("toner") in KEY_RATIOS:
            out[b["toner"]][ladder_key(b)].append({**_row(b), "value": swept_value(b)})
    return {t: {k: sorted(v, key=lambda r: r["value"]) for k, v in sorted(ls.items())} for t, ls in sorted(out.items())}


def grid_tables(bars: list[dict[str, Any]], toner: str = "M") -> dict[str, dict[str, Any]]:
    """construct -> {"R": [...], "B": [...], "cells": {"R,B": row}} for the toner's axis-"grid" bars."""
    by_c: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in bars:
        if b.get("axis") == "grid" and b.get("toner") == toner and b.get("rgb"):
            by_c[str(b.get("construct"))].append(b)
    out = {}
    for c, bs in sorted(by_c.items()):
        Rs = sorted({int(b["rgb"][0]) for b in bs})
        Bs = sorted({int(b["rgb"][2]) for b in bs})
        out[c] = {"R": Rs, "B": Bs, "G": sorted({int(b["rgb"][1]) for b in bs}),
                  "cells": {f"{int(b['rgb'][0])},{int(b['rgb'][2])}": _row(b) for b in bs}}
    return out


def propose(bars: list[dict[str, Any]], lookup: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
    """toner -> the proposal: the registry value itself when any of its bars is clean (every clean bar's ratios
    sit at noise level, so a minimum over them is a draw among noise — the refuter of 2026-10-11), else the
    clean bar with the smallest ratio sum (ties: nearest the registry value); the per-construct minima and the
    registry value's own bars beside it.  A move of the registry value is the ladders' and the record's call,
    never this function's."""
    out = {}
    for toner in KEY_RATIOS:
        reg = [int(v) for v in lookup.get(toner, [255, 255, 255])]
        cand = [b for b in bars if b.get("toner") == toner and b.get("rgb") and b["kind"] in ("sweep", "registry")]
        if not cand:
            continue

        def key(b: dict[str, Any]) -> tuple[float, int]:
            return ratio_sum(b), sum(abs(int(b["rgb"][j]) - reg[j]) for j in range(3))
        clean = [b for b in cand if b["verdict"] == "clean" and np.isfinite(ratio_sum(b))]
        by_c: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for b in clean:
            by_c[str(b.get("construct"))].append(b)
        reg_clean = [b for b in clean if [int(v) for v in b["rgb"]] == reg]
        out[toner] = {"registry_rgb": reg,
                      "proposal": _row(min(reg_clean or clean, key=key)) if clean else None,
                      "registry_clean": bool(reg_clean),
                      "by_construct": {c: _row(min(bs, key=key)) for c, bs in sorted(by_c.items())},
                      "registry_bars": [_row(b) for b in cand if [int(v) for v in b["rgb"]] == reg]}
    return out


# ---------------------------------------------------------------- text

def _r(v: float) -> str:
    return f"{v:6.0f}" if np.isfinite(v) else "     -"


def series_lines(series: dict[str, dict[str, list[dict[str, Any]]]]) -> list[str]:
    lines = []
    for toner, ls in series.items():
        labs = [lab for lab, _, _ in KEY_RATIOS[toner]]
        for key, rows in ls.items():
            lines.append(f"  {toner} {key}   value: " + " ".join(f"{lab:>7s}" for lab in labs) + "  verdict")
            for r in rows:
                lines.append(f"      {r['value']:3d}:  " + " ".join(f"{_r(r['ratios'][lab]):>7s}" for lab in labs)
                             + f"  {r['verdict']}")
    return lines


def grid_lines(grids: dict[str, dict[str, Any]], toner: str = "M") -> list[str]:
    """One table per construct: rows R, columns B, cell 'yellow/cyan/own'."""
    labs = [lab for lab, _, _ in KEY_RATIOS[toner]]
    lines = []
    for c, g in grids.items():
        lines.append(f"  {toner} grid, {c} (G {g['G']}; cell = {'/'.join(labs)} | foreign specks per mm2; * = clean, s = speckled):")
        lines.append("      R \\ B " + "".join(f"{b:>16d}" for b in g["B"]))
        for R in g["R"]:
            cells = []
            for B in g["B"]:
                row = g["cells"].get(f"{R},{B}")
                if row is None:
                    cells.append(f"{'-':>16s}")
                    continue
                txt = "/".join(f"{row['ratios'][lab]:.0f}" if np.isfinite(row["ratios"][lab]) else "-" for lab in labs)
                sp = row.get("specks_max"); txt += f"|{sp:.0f}" if sp is not None and np.isfinite(sp) else ""
                mark = "*" if row["verdict"] == "clean" else ("s" if row["verdict"] == "speckled" else " ")
                cells.append(f"{txt + mark:>16s}")
            lines.append(f"      {R:5d} " + "".join(cells))
    return lines


def proposal_lines(prop: dict[str, dict[str, Any]]) -> list[str]:
    lines = []
    for toner, p in prop.items():
        labs = [lab for lab, _, _ in KEY_RATIOS[toner]]

        def desc(r: dict[str, Any] | None) -> str:
            if r is None:
                return "none clean"
            return (f"{tuple(r['rgb'])} {r['construct']} " + " ".join(f"{lab} {_r(r['ratios'][lab]).strip()}" for lab in labs)
                    + f" (sum {r['sum']:.0f}, {r['verdict']})")
        lines.append(f"  {toner} proposed {desc(p['proposal'])}")
        for c, r in p["by_construct"].items():
            lines.append(f"      best in {c}: {desc(r)}")
        for r in p["registry_bars"]:
            lines.append(f"      registry {tuple(p['registry_rgb'])} {r['construct']}: " + " ".join(
                f"{lab} {_r(r['ratios'][lab]).strip()}" for lab in labs) + f" -> {r['verdict']} "
                f"(worst {r['worst_family']} in {r['worst_channel']} {r['worst_ratio']:.0f})")
    return lines

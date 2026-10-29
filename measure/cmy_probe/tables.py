"""The readout's CSV tables and table lines (measure/cmy_probe/readout.py): bars, bands, checkerboards, dots.

bands.csv carries both whole-band forms: fam_* (radial median, 043.3c's) and famlocal_* (local median, the
reliable one on a c3 field).  bars.csv carries THE VERDICT's columns (fam_<density>_<family> for the three ink densities C, M, Y and the
five screen families of measure/cmy_probe/stipples.py, worst_channel / worst_family / worst_ratio, verdict)
and the e041 lattice score's columns prefixed legacy_ (legacy_score_<lattice>, legacy_score,
legacy_score_R/G/B, legacy_best_lattice, legacy_verdict), so sheet 1's records stay comparable.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_probe.bands import STATE_NAMES
from measure.cmy_probe.stipples import CHANNELS as DENSITIES
from measure.cmy_probe.stipples import FAMILIES
from measure.e041_scale_readout import LATTICES

FAM_COLS = [(ch, f) for ch in DENSITIES for f in FAMILIES]


def f4(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, float):
        return "" if not np.isfinite(v) else f"{v:.4f}"
    return v


def fmt(v: Any, nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def write_csv(path: Path, head: list[str], rows: list[list[Any]]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows([[f4(v) for v in r] for r in rows])


def fam_head(prefix: str = "fam") -> list[str]:
    return [f"{prefix}_{ch}_{f}" for ch, f in FAM_COLS]


def fam_values(fam: dict[str, dict[str, float]]) -> list[float]:
    return [float(fam[ch][f]) for ch, f in FAM_COLS]


def bars_table(res: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    lats = list(LATTICES)
    head = (["scan", "id", "kind", "toner", "axis", "construct", "r", "g", "b", "x_dots", "y_dots",
             "mean_R", "mean_G", "mean_B", "sd_R", "sd_G", "sd_B"]
            + fam_head() + ["worst_channel", "worst_family", "worst_ratio",
                            "specks_C_per_mm2", "specks_M_per_mm2", "specks_Y_per_mm2", "specks_skew_C", "specks_skew_M",
                            "specks_skew_Y", "specks_density", "specks_max", "verdict"]
            + ["legacy_own", "legacy_lattice_windows"] + [f"legacy_score_{k}" for k in lats]
            + ["legacy_score", "legacy_score_R", "legacy_score_G", "legacy_score_B", "legacy_best_lattice",
               "legacy_verdict", "offband_lpi", "offband_deg", "offband_ratio", "gt_ink_fraction"])
    rows = []
    for r in res:
        for b in r["bars"]:
            rgb = b["rgb"] or [None] * 3
            rows.append([r["name"], b["id"], b["kind"], b["toner"], b["axis"], b["construct"], *rgb,
                         b["x_dots"], b["y_dots"], *b["mean_rgb"], *b["sd_rgb"],
                         *fam_values(b["families"]), b["worst_channel"], b["worst_family"], b["worst_ratio"],
                         *[b["specks"][d]["specks_per_mm2"] for d in ("C", "M", "Y")],
                         *[b["specks"][d]["skew"] for d in ("C", "M", "Y")], b["specks_density"], b["specks_max"],
                         b["verdict"], "".join(b["own"]), b["lattice_windows"],
                         *[b["lattice"].get(k) for k in lats], b["score"], *b["score_rgb"], b["best_lattice"],
                         b["verdict_legacy"], b["offband"]["lpi"], b["offband"]["deg"], b["offband"]["ratio"],
                         b["gt_ink_fraction"]])
    return head, rows


def bands_table(res: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    conf_cols = [f"conf_{t}_{p}" for t in STATE_NAMES for p in STATE_NAMES]
    head = (["scan", "name", "arm", "cell_dots", "n_cells", "n_read", "n_windows", "n_reg_nominal", "n_reg_edge",
             "state_err", "err_C", "err_M", "err_Y", "window_err_max", "M_dy_vs_C_dots", "M_dx_vs_C_dots",
             "Y_dy_vs_C_dots", "Y_dx_vs_C_dots", "Y_minus_C_abs_dots", "lattice_score", "best_lattice", "bytes",
             "full_page_bytes"] + fam_head() + fam_head("famlocal") + ["worst_channel", "worst_family", "worst_ratio"]
            + conf_cols)
    rows = []
    for r in res:
        for b in r["bands"]:
            rows.append([r["name"], b["name"], b["arm"], b["cell_dots"], b["n_cells"], b["n_read"], b["n_windows"],
                         b["n_reg_nominal"], b["n_reg_edge"], b["state_err"], *[b["plane_err"][p] for p in "CMY"],
                         b["window_err_max"], b["M_dy_vs_C_dots"], b["M_dx_vs_C_dots"], b["Y_dy_vs_C_dots"],
                         b["Y_dx_vs_C_dots"], b["Y_minus_C_abs_dots"], b["lattice_score"], b["best_lattice"],
                         b.get("bytes"), b.get("full_page_bytes"), *fam_values(b["families"]),
                         *fam_values(b["families_local"]), b["worst_channel"],
                         b["worst_family"], b["worst_ratio"], *np.asarray(b["confusion"]).ravel().tolist()])
    return head, rows


TONER_COLS = ("ink_fraction", "gain_area_pct", "edge_growth_dots", "ink_fraction_half", "otsu_threshold",
              "ink_fraction_otsu", "edge_um",
              "edge_x_um", "edge_y_um", "dx_dots", "dy_dots", "fund_ratio")


def checkerboards_table(res: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    """One row per (checkerboard, toner of the pair); the pair's relative offset and families on every row."""
    head = (["scan", "id", "pair", "cell_dots", "construct", "x_dots", "y_dots", "toner", *TONER_COLS,
             "solid_R", "solid_G", "solid_B", "rel_dx_dots", "rel_dy_dots", "rel_abs_dots"]
            + fam_head() + ["worst_channel", "worst_family", "worst_ratio"])
    rows = []
    for r in res:
        for c in r["checkerboards"]:
            for t, v in c["toners"].items():
                rows.append([r["name"], c["id"], c["pair"], c["cell_dots"], c["construct"], c["x_dots"], c["y_dots"],
                             t, *[v[k] for k in TONER_COLS], *v["solid_rgb"], c["rel_dx_dots"], c["rel_dy_dots"],
                             c["rel_abs_dots"], *fam_values(c["families"]), c["worst_channel"], c["worst_family"],
                             c["worst_ratio"]])
    return head, rows


def dots_table(res: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    keys = ("id", "toner", "pattern", "x_dots", "y_dots", "n_on", "n_off", "mean_on", "mean_off", "white",
            "contrast", "on_above_mid", "sd_on", "sd_off")
    head = ["scan", *keys, "shift_dy_dots", "shift_dx_dots"]
    return head, [[r["name"], *[d[k] for k in keys], *d["shift_dots"]] for r in res for d in r["dots"]]


def checkerboard_lines(cbs: list[dict[str, Any]]) -> list[str]:
    lines = [f"  {'id':10s} {'pair':4s} c  toner  frac   gain%  e_dots  edge_um   off_dx  off_dy   rel_dx  rel_dy  "
             f"worst family (Y213@45 in Y)"]
    for c in cbs:
        first = True
        for t, v in c["toners"].items():
            rel = (f"{c['rel_dx_dots']:+7.2f} {c['rel_dy_dots']:+7.2f}" if first and np.isfinite(c["rel_abs_dots"])
                   else " " * 15)
            tail = (f"  {c['worst_family']} in {c['worst_channel']} {fmt(c['worst_ratio'], 0)} "
                    f"({fmt(c['families']['Y']['Y213@45'], 0)})" if first else "")
            lines.append(f"  {c['id']:10s} {c['pair']:4s} {c['cell_dots']}  {t:5s} {v['ink_fraction']:.3f} "
                         f"{v['gain_area_pct']:+6.1f} {v['edge_growth_dots']:+6.2f} {v['edge_um']:7.1f}  "
                         f"{v['dx_dots']:+7.2f} {v['dy_dots']:+7.2f}  {rel}{tail}")
            first = False
    return lines

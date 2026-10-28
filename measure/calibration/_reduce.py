"""Reduce the raw E9 record to the report tables.

Nothing here re-measures anything: it reads `e9-k-raw.json` and produces
`e9-k.json`, the arm table over the COMPLETE residue, the spatial split
against the e029 failure geography, the cost table, and the
local-vs-global calibration delta.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# experiments/029-holo-v1-first-print.md, "Failed-tile geography".  The
# groups are the LOG'S OWN split, not a clustering fitted here.
GROUP_COL0 = "extreme column 0"
GROUP_COL36 = "extreme column 36"
GROUP_ROW42 = "interior row-42 band"
GROUP_OTHER = "interior singleton"


def group_of(address) -> str:
    _page, ty, tx = address
    if tx == 0:
        return GROUP_COL0
    if tx == 36:
        return GROUP_COL36
    if ty == 42:
        return GROUP_ROW42
    return GROUP_OTHER


def _ber(row) -> float:
    value = row.get("ber")
    return float("nan") if value is None else float(value)


def _finite(values):
    array = np.asarray(values, np.float64)
    return array[np.isfinite(array)]


def reduce_raw(raw: dict) -> dict:
    arms = ["R", "W", "H1", "H2", "G"]
    residue = [tuple(entry) for entry in raw["residue"]]
    out: dict[str, object] = {
        "instrument": raw["instrument"],
        "subject": {
            "spec_id": raw["spec_id"],
            "format_row_id": raw["format_row_id"],
            "close_status": raw["close_status"],
            "certificates": raw["n_certificates"],
            "tiles_yx": raw["tiles_yx"],
            "residue_tiles": len(residue),
            "k_eff_bits": raw["k_eff_bits"],
            "payload_cells_per_tile": raw["payload_cells_per_tile"],
            "n_filler": raw["n_filler"],
        },
        "production_calibration_granularity": {
            "score_transform": "per WINDOW (median + mean-abs-deviation of "
                               "that window's sampled means) — "
                               "_payload_sampling._scores",
            "marginal_head": "pava-v1 isotonic map, fitted per WINDOW on "
                             "that window's own FORMAT-KNOWN cells, "
                             "SEARCH half of the (131y+17x)&1 parity — "
                             "_payload_sampling._calibrate / "
                             "detect.fit_calibration",
            "marginal_label_population": "BCH word sites only (this row "
                                         "has n_filler = 0); certified "
                                         "payload cells are NEVER labels",
            "context_arm": "ctx-pava-v1, nine ordered additive-logit "
                           "offsets over the 8-neighbour provisional-ink "
                           "count, fitted per REGION over every window of "
                           "that region and adopted only on a strict "
                           "weighted held-out log-loss gain — "
                           "_payload_context.apply_region_context",
            "regions_per_lane_on_this_capture": 1,
            "consequence": "the shipped granularity is PHOTOMETRY per "
                           "window, CALIBRATION per window, CONTEXT "
                           "page-global (one region covers the sheet)",
        },
        "truth_path": raw["truth_path"],
        "provenance_entry": raw["provenance_entry"],
        "provenance_exit": raw.get("provenance_exit"),
        "lanes": {},
        "arms": {
            "R": "incumbent recipe: window-only scope, format-known labels",
            "W": "window-only scope, format-known UNION certified labels",
            "H1": "window + 1 window-extent halo, same labels",
            "H2": "window + 2 window-extent halo, same labels",
            "G": "page-global scope (every window of the lane), same labels",
        },
    }

    for lane_id, lane in raw["lanes"].items():
        table: dict[str, object] = {}
        per_arm: dict[str, dict[str, object]] = {}
        for arm in arms:
            data = lane["arms"][arm]
            bers = np.asarray(
                [_ber(data["tiles"][str(entry)]) for entry in residue])
            base = np.asarray(
                [_ber(lane["arms"]["R"]["tiles"][str(entry)])
                 for entry in residue])
            delta = bers - base
            windows = data["windows"]
            accepted = [row for row in windows if row["accepted"]]
            page = np.asarray([
                [observed, wrong] for observed, wrong
                in data["page_ber"].values()], np.float64)
            page_base = np.asarray([
                [observed, wrong] for observed, wrong
                in lane["arms"]["R"]["page_ber"].values()], np.float64)
            per_arm[arm] = {
                "certificates": data["n_certified"],
                "median_residue_ber_pct": float(
                    100 * np.nanmedian(_finite(bers))),
                "mean_residue_ber_pct": float(100 * _finite(bers).mean()),
                "mean_delta_vs_R_pp": float(100 * _finite(delta).mean()),
                "tiles_better_than_R": int(np.sum(_finite(delta) < 0)),
                "tiles_worse_than_R": int(np.sum(_finite(delta) > 0)),
                "page_cell_ber_pct": float(
                    100 * page[:, 1].sum() / page[:, 0].sum()),
                "page_cell_ber_delta_vs_R_pp": float(
                    100 * (page[:, 1].sum() / page[:, 0].sum()
                           - page_base[:, 1].sum() / page_base[:, 0].sum())),
                "windows_accepted": len(accepted),
                "windows_refused": len(windows) - len(accepted),
                "median_fit_labels": float(np.median(
                    [row["n_search"] for row in accepted])) if accepted else 0,
                "median_halo_windows": float(np.median(
                    [row["n_members"] for row in windows])),
                "nodes_clipped_total": int(sum(
                    row["n_nodes_clipped"] for row in windows)),
                "fit_cpu_s": data["fit_cpu_s"],
                "arm_cpu_s": data["arm_cpu_s"],
                "arm_wall_s": data["arm_wall_s"],
                "attempt_cpu_s": data["attempt_cpu_s"],
                "attempts": 2 * len(residue),
                "cpu_s_per_attempt": data["arm_cpu_s"] / max(
                    2 * len(residue), 1),
                "cpu_s_per_certificate": (
                    data["arm_cpu_s"] / data["n_certified"]
                    if data["n_certified"] else None),
                "context_adopted": [row["adopted"] for row in data["context"]],
                "context_offsets": [row["offsets"] for row in data["context"]],
            }
        for entry in residue:
            key = str(entry)
            row: dict[str, object] = {
                "group": group_of(entry),
                "n_observed": lane["arms"]["R"]["tiles"][key].get(
                    "n_observed", 0),
            }
            best_arm, best = None, float("inf")
            for arm in arms:
                cell = lane["arms"][arm]["tiles"][key]
                value = _ber(cell)
                row[f"ber_{arm}"] = None if value != value else 100 * value
                row[f"certified_{arm}"] = bool(cell.get("certified"))
                row[f"state_{arm}"] = cell.get(
                    "retry150_state", cell.get("scan_state"))
                if value == value and value < best:
                    best_arm, best = arm, value
            row["best_arm"] = best_arm
            row["best_ber_pct"] = None if best == float("inf") else 100 * best
            table[key] = row
        groups: dict[str, object] = {}
        for name in (GROUP_COL0, GROUP_COL36, GROUP_ROW42, GROUP_OTHER):
            members = [entry for entry in residue if group_of(entry) == name]
            groups[name] = {
                "tiles": len(members),
                "mean_ber_R_pct": float(100 * _finite(
                    [_ber(lane["arms"]["R"]["tiles"][str(e)])
                     for e in members]).mean()),
                **{
                    f"mean_delta_{arm}_pp": float(100 * _finite([
                        _ber(lane["arms"][arm]["tiles"][str(e)])
                        - _ber(lane["arms"]["R"]["tiles"][str(e)])
                        for e in members]).mean())
                    for arm in arms if arm != "R"
                },
            }
        t50_w = np.asarray([row["t50"]
                            for row in lane["arms"]["W"]["windows"]])
        t50_g = np.asarray([row["t50"]
                            for row in lane["arms"]["G"]["windows"]])
        t50_r = np.asarray([row["t50"]
                            for row in lane["arms"]["R"]["windows"]])
        centres = np.asarray([row["centre_yx"]
                              for row in lane["arms"]["W"]["windows"]])
        delta_wg = _finite(t50_w - t50_g)
        out["lanes"][lane_id] = {          # type: ignore[index]
            "raster_shape": lane["raster_shape"],
            "raster_dpi": lane["raster_dpi"],
            "windows": lane["n_windows"],
            "placements": lane["n_placements"],
            "pool_rows": lane["n_pool_rows"],
            "pool_labels": lane["n_pool_labels"],
            "pool_furniture_labels": lane["n_pool_furniture"],
            "peak_rss_gb": lane["peak_rss_gb"],
            "lane_wall_s": lane["lane_wall_s"],
            "reproduction_control": lane["arms"]["R"]["archived_agreement"],
            "arm_summary": per_arm,
            "tiles": table,
            "groups": groups,
            "calibration_delta": {
                "t50_local_minus_global": {
                    "mean": float(delta_wg.mean()),
                    "std": float(delta_wg.std(ddof=1)),
                    "min": float(delta_wg.min()),
                    "max": float(delta_wg.max()),
                    "abs_median": float(np.median(np.abs(delta_wg))),
                },
                "t50_production_R": {
                    "mean": float(_finite(t50_r).mean()),
                    "std": float(_finite(t50_r).std(ddof=1)),
                    "min": float(_finite(t50_r).min()),
                    "max": float(_finite(t50_r).max()),
                },
                "t50_global_G": float(np.nanmedian(t50_g)),
                "spearman_delta_vs_row": _spearman(
                    centres[:, 0], t50_w - t50_g),
                "spearman_delta_vs_column": _spearman(
                    centres[:, 1], t50_w - t50_g),
            },
        }
    out["total_wall_s"] = raw.get("total_wall_s")
    return out


def _spearman(x, y) -> float | None:
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    good = np.isfinite(x) & np.isfinite(y)
    if good.sum() < 3:
        return None
    from scipy import stats
    return float(stats.spearmanr(x[good], y[good]).statistic)


def reduce_file(raw_path: Path, out_path: Path) -> dict:
    raw = json.loads(raw_path.read_text())
    report = reduce_raw(raw)
    out_path.write_text(json.dumps(report, indent=1))
    return report


__all__ = ["group_of", "reduce_file", "reduce_raw"]

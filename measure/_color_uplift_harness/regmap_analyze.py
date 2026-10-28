"""PK6/A2 registration-field analysis: the pre-registered plan, verbatim.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.regmap_analyze analyze --capture xerox-c2-cmy7
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.regmap_analyze verdict

Consumes one ``regmap run`` NPZ + its run JSON and produces the
per-capture analysis blob (JSON + markdown + PNG window-median maps).
``verdict`` evaluates the pre-registered A2 build gate across captures.

The plan (stats review, 2026-08-10, implemented verbatim):
residuals against the PRODUCTION fit; M0={1,y} deployed, M1={1,y,x}
refit on window medians, gate on M1; no |r|<=0.5 trim (sensitivity
only); whitening by (bucket x quality-decile x plane x lane) pooled
within-window scale; per-window median + 1.4826*MAD, drop n_w<4;
DerSimonian-Laird tau^2 with Q-profile 99% lower bound; common/diff
split; correlogram + min-separation {0,2,4,8}; placebo lattice
translations + synchronized within-window bootstrap; PRIMARY = one
uncorrected omnibus test (xerox c2-cmy7, last ordinary lane, census
pass, furniture buckets, min-sep 4); deployed-arm DeltaMSE gate with
u-weighting; pre-gates G1 peak-lock, G2 phase, G3 saturation, G4
reach, G5 power.  Everything is development signal; the verdict is a
build/no-build recommendation for the user's ruling, not an adoption.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from . import corpus
from . import regmap_stats as stats
from .regmap import (
    PASS_CENSUS,
    PASS_DENSE,
    PASS_PROD,
    load_regmap,
)

WINDOW_STRIDE_CELLS = 160
MIN_WINDOW_ANCHORS = 4
KAPPA = 8.0
PLACEBO_TRANSLATIONS = 200
BOOTSTRAP_REPS = 999
ANALYZE_SEED = 20260810
MIN_SEPARATIONS = (0, 2, 4, 8)
SATURATION_MARGIN_DOTS = 0.26
PRIMARY_CAPTURE = "xerox-c2-cmy7"
# Half of placement/model.py refine_phase_step_cells (0.0625).
RMS_FLOOR_CELLS = 0.03
COLUMN = {
    "anchors": ["lane", "fit_ordinal", "pass", "plane", "bucket", "page",
                "cell_y", "cell_x", "window_index",
                "off_x_dots", "off_y_dots", "quality"],
    "windows": ["lane", "fit_ordinal", "window_index", "patch_id",
                "region_index", "page", "rot_k",
                "bbox_y0", "bbox_x0", "bbox_y1", "bbox_x1", "n_rows",
                "pitch_px", "angle_deg", "origin_y", "origin_x",
                "phase_y", "phase_x"],
    "fits": ["lane", "fit_ordinal", "pass", "plane", "page",
             "region_index", "intercept_x", "intercept_y",
             "slope_x", "slope_y", "n_anchors", "n_measured"],
}


def _col(table: np.ndarray, name: str, of: str) -> np.ndarray:
    return table[:, COLUMN[of].index(name)]


class CaptureFrame:
    """One capture's regmap arrays joined with its run JSON."""

    def __init__(self, key: str) -> None:
        self.key = key
        work = corpus.work_dir("regmap")
        self.data = load_regmap(work / f"{key}-regmap.npz")
        self.meta = self.data["meta"]
        if self.meta.get("partial"):
            raise SystemExit(f"{key}: regmap NPZ is partial — rerun first")
        run_path = corpus.work_dir("runs") / f"{key}-replay-regmap.json"
        self.run = json.loads(run_path.read_text())
        self.lane_ids = list(self.meta["lane_ids"])
        self.cells_yx = tuple(self.meta["cells_yx"])
        self.cell_dots = float(self.meta["cell_dots"])
        self.anchors = self.data["anchors"]
        self.windows = self.data["windows"]
        self.fits = self.data["fits"]
        rot = np.unique(_col(self.windows, "rot_k", "windows"))
        if rot.size > 1:
            raise SystemExit(
                f"{key}: mixed rot_k across windows {rot.tolist()} — "
                "pooled local-frame offsets are incoherent; abort "
                "(stats review S12)")
        self.rot_k = int(rot[0]) if rot.size else 0
        self.ordinary = [
            name for name in self.lane_ids
            if name[:1] == "l" and name[1:3].isdigit()]
        self.census_lanes = [
            name for name in self.meta["census_lanes"]
            if name in self.lane_ids]

    def lane_index(self, lane_id: str) -> int:
        return self.lane_ids.index(lane_id)

    def production_fit(self, lane: int, plane: int) -> tuple | None:
        rows = self.fits[
            (_col(self.fits, "lane", "fits") == lane)
            & (_col(self.fits, "pass", "fits") == PASS_PROD)
            & (_col(self.fits, "plane", "fits") == plane)]
        if not rows.size:
            return None
        row = rows[0]
        return (row[COLUMN["fits"].index("intercept_x")],
                row[COLUMN["fits"].index("intercept_y")],
                row[COLUMN["fits"].index("slope_x")],
                row[COLUMN["fits"].index("slope_y")])

    def lane_windows(self, lane: int) -> np.ndarray:
        return self.windows[_col(self.windows, "lane", "windows") == lane]

    def window_centers(self, lane: int) -> np.ndarray:
        rows = self.lane_windows(lane)
        return np.stack((
            0.5 * (_col(rows, "bbox_y0", "windows")
                   + _col(rows, "bbox_y1", "windows")),
            0.5 * (_col(rows, "bbox_x0", "windows")
                   + _col(rows, "bbox_x1", "windows")),
        ), axis=1)

    def lane_anchors(self, lane: int, pass_tag: int,
                     furniture_only: bool) -> np.ndarray:
        table = self.anchors
        keep = ((_col(table, "lane", "anchors") == lane)
                & (_col(table, "pass", "anchors") == pass_tag))
        if furniture_only:
            keep &= _col(table, "bucket", "anchors") <= 1
        return table[keep]


def residuals(frame: CaptureFrame, lane: int,
              anchors: np.ndarray) -> np.ndarray:
    """(N, 2) residual dots per component vs the PRODUCTION fit."""
    out = np.full((anchors.shape[0], 2), np.nan)
    y_frac = _col(anchors, "cell_y", "anchors") / frame.cells_yx[0]
    for plane in range(3):
        fit = frame.production_fit(lane, plane)
        rows = _col(anchors, "plane", "anchors") == plane
        if fit is None or not rows.any():
            continue
        ix, iy, sx, sy = fit
        out[rows, 0] = (_col(anchors, "off_x_dots", "anchors")[rows]
                        - (ix + sx * y_frac[rows]))
        out[rows, 1] = (_col(anchors, "off_y_dots", "anchors")[rows]
                        - (iy + sy * y_frac[rows]))
    return out


def recorded_window_of(anchors: np.ndarray) -> np.ndarray:
    """The measuring window, as production attributed it (review B1:
    the windows overlap, so a nearest-centre proxy contradicts the
    recorded identity for ~21% of anchors and attenuates tau)."""
    return _col(anchors, "window_index", "anchors").astype(np.int64)


def nearest_center_attribution(cells: np.ndarray,
                               centers: np.ndarray) -> np.ndarray:
    """Nearest window centre — for TILES only (tiles carry no recorded
    window); anchors always use ``recorded_window_of``."""
    if not centers.size:
        return np.zeros(cells.shape[0], np.int64)
    distance = ((cells[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(distance, axis=1)


def whiten(anchors: np.ndarray, residual: np.ndarray,
           window_of: np.ndarray) -> tuple[np.ndarray, dict]:
    """z-scores via pooled within-window scale per stratum.

    Strata: (plane, bucket, quality tercile) with a (plane,) fallback
    below 30 pooled observations.  The scale is computed from
    within-window CENTERED residuals pooled across windows, so window
    effects cannot inflate it (stats review S2).
    """
    plane = _col(anchors, "plane", "anchors").astype(np.int64)
    bucket = np.minimum(
        _col(anchors, "bucket", "anchors").astype(np.int64), 2)
    quality = _col(anchors, "quality", "anchors")
    centered = np.full(residual.shape, np.nan)
    for window in np.unique(window_of):
        rows = window_of == window
        if rows.sum() >= MIN_WINDOW_ANCHORS:
            centered[rows] = residual[rows] - np.median(
                residual[rows], axis=0)
    tercile = np.zeros(anchors.shape[0], np.int64)
    for p in range(3):
        rows = plane == p
        if rows.sum() >= 30:
            edges = np.quantile(quality[rows], (1 / 3, 2 / 3))
            tercile[rows] = np.searchsorted(edges, quality[rows])
    z = np.full(residual.shape, np.nan)
    scales: dict = {}
    for p in range(3):
        fallback = np.asarray([
            stats.robust_scale(centered[plane == p, comp][
                np.isfinite(centered[plane == p, comp])])
            for comp in range(2)])
        for b in range(3):
            for t in range(3):
                rows = (plane == p) & (bucket == b) & (tercile == t)
                if not rows.any():
                    continue
                for comp in range(2):
                    pool = centered[rows, comp]
                    pool = pool[np.isfinite(pool)]
                    scale = (stats.robust_scale(pool)
                             if pool.size >= 30 else fallback[comp])
                    if not np.isfinite(scale) or scale <= 0:
                        scale = fallback[comp] if fallback[comp] > 0 else 1.0
                    z[rows, comp] = residual[rows, comp] / scale
                    scales[f"p{p}b{b}t{t}c{comp}"] = float(scale)
    return z, scales


def refit_m1(medians: np.ndarray, variances: np.ndarray,
             centers: np.ndarray, cells_yx: tuple) -> np.ndarray:
    """WLS {1, y_frac, x_frac} on window medians -> predictions."""
    keep = np.isfinite(medians) & np.isfinite(variances) & (variances > 0)
    if keep.sum() < 6:
        return np.zeros_like(medians)
    design = np.stack((
        np.ones(keep.sum()),
        centers[keep, 0] / cells_yx[0],
        centers[keep, 1] / cells_yx[1]), axis=1)
    weights = 1.0 / variances[keep]
    wsqrt = np.sqrt(weights)
    coeffs, *_ = np.linalg.lstsq(
        design * wsqrt[:, None], medians[keep] * wsqrt, rcond=None)
    full_design = np.stack((
        np.ones(medians.size),
        centers[:, 0] / cells_yx[0],
        centers[:, 1] / cells_yx[1]), axis=1)
    return full_design @ coeffs


def lane_component_estimates(frame: CaptureFrame, lane: int,
                             pass_tag: int) -> list[dict]:
    """Per (plane, comp): DL tau under M0 and M1, in dots and whitened."""
    anchors = frame.lane_anchors(lane, pass_tag, furniture_only=True)
    if not anchors.shape[0]:
        return []
    centers = frame.window_centers(lane)
    window_of = recorded_window_of(anchors)
    residual = residuals(frame, lane, anchors)
    z, _scales = whiten(anchors, residual, window_of)
    results = []
    for plane in range(3):
        rows = _col(anchors, "plane", "anchors") == plane
        for comp in range(2):
            values = residual[rows, comp]
            zvalues = z[rows, comp]
            keep = np.isfinite(values) & np.isfinite(zvalues)
            summary = stats.window_summaries(
                values[keep], window_of[rows][keep], centers.shape[0],
                MIN_WINDOW_ANCHORS)
            if summary["window_ids"].size < 6:
                continue
            variances = stats.median_variances(summary)
            m0 = stats.dersimonian_laird(summary["medians"], variances)
            kept_centers = centers[summary["window_ids"]]
            m1_prediction = refit_m1(
                summary["medians"], variances, kept_centers,
                frame.cells_yx)
            m1 = stats.dersimonian_laird(
                summary["medians"] - m1_prediction, variances)
            zsummary = stats.window_summaries(
                zvalues[keep], window_of[rows][keep], centers.shape[0],
                MIN_WINDOW_ANCHORS)
            zvariances = stats.median_variances(zsummary)
            zm0 = stats.dersimonian_laird(zsummary["medians"], zvariances)
            results.append({
                "lane": frame.lane_ids[lane],
                "pass": pass_tag,
                "plane": plane,
                "comp": "xy"[comp],
                "windows": int(summary["window_ids"].size),
                "anchors": int(np.sum(summary["counts"])),
                "median_n_w": float(np.median(summary["counts"])),
                "tau_m0_dots": float(np.sqrt(m0["tau2"]))
                if np.isfinite(m0["tau2"]) else None,
                "tau_m1_dots": float(np.sqrt(m1["tau2"]))
                if np.isfinite(m1["tau2"]) else None,
                "sigma_dots": float(np.nanmedian(summary["scales"])),
                "zq_m0": float(zm0["q"]),
                "zdf_m0": int(zm0["df"]),
            })
    return results


def census_diagnostics(frame: CaptureFrame, lane_id: str) -> dict:
    """Plan lines 7-8: common/diff split, correlogram, min-sep curve."""
    lane = frame.lane_index(lane_id)
    pass_tag = (PASS_CENSUS if frame.lane_anchors(
        lane, PASS_CENSUS, True).shape[0] else PASS_DENSE)
    anchors = frame.lane_anchors(lane, pass_tag, furniture_only=True)
    if not anchors.shape[0]:
        return {}
    centers = frame.window_centers(lane)
    window_of = recorded_window_of(anchors)
    residual = residuals(frame, lane, anchors)
    z, _ = whiten(anchors, residual, window_of)
    cells = np.stack((_col(anchors, "cell_y", "anchors"),
                      _col(anchors, "cell_x", "anchors")), axis=1)
    plane_of = _col(anchors, "plane", "anchors").astype(np.int64)

    correlograms = []
    for plane in range(3):
        rows = (plane_of == plane) & np.isfinite(z[:, 0])
        if rows.sum() >= 100:
            correlograms.append({
                "plane": plane,
                "x": stats.correlogram(
                    cells[rows], z[rows, 0], window_of[rows]),
                "y": stats.correlogram(
                    cells[rows], z[rows, 1], window_of[rows])})

    min_sep_curve = []
    for separation in MIN_SEPARATIONS:
        taus = []
        for plane in range(3):
            plane_rows = plane_of == plane
            thin = np.zeros(anchors.shape[0], np.bool_)
            thin[plane_rows] = stats.min_separation_thin(
                cells[plane_rows], window_of[plane_rows], separation,
                ANALYZE_SEED + separation + 17 * plane)
            rows = plane_rows & thin
            for comp in range(2):
                values = residual[rows, comp]
                keep = np.isfinite(values)
                summary = stats.window_summaries(
                    values[keep], window_of[rows][keep],
                    centers.shape[0], MIN_WINDOW_ANCHORS)
                if summary["window_ids"].size < 6:
                    taus.append(None)
                    continue
                variances = stats.median_variances(summary)
                prediction = refit_m1(
                    summary["medians"], variances,
                    centers[summary["window_ids"]], frame.cells_yx)
                result = stats.dersimonian_laird(
                    summary["medians"] - prediction, variances)
                taus.append(float(np.sqrt(result["tau2"]))
                            if np.isfinite(result["tau2"]) else None)
        min_sep_curve.append(
            {"min_separation": separation, "tau_m1_dots": taus})

    # Common/diff split (plan line 7): per-window plane medians ->
    # common = mean over planes, diff = plane - common; DL over windows.
    common_diff: dict = {"common": [], "diff": []}
    for comp in range(2):
        medians = np.full((centers.shape[0], 3), np.nan)
        variances = np.full((centers.shape[0], 3), np.nan)
        for plane in range(3):
            rows = plane_of == plane
            values = residual[rows, comp]
            keep = np.isfinite(values)
            summary = stats.window_summaries(
                values[keep], window_of[rows][keep], centers.shape[0],
                MIN_WINDOW_ANCHORS)
            medians[summary["window_ids"], plane] = summary["medians"]
            variances[summary["window_ids"], plane] = (
                stats.median_variances(summary))
        full = np.isfinite(medians).all(axis=1)
        if full.sum() >= 6:
            common = medians[full].mean(axis=1)
            common_var = variances[full].sum(axis=1) / 9.0
            result = stats.dersimonian_laird(common, common_var)
            common_diff["common"].append({
                "comp": "xy"[comp],
                "windows": int(full.sum()),
                "tau_dots": float(np.sqrt(result["tau2"]))
                if np.isfinite(result["tau2"]) else None})
            for plane in range(3):
                diff = medians[full, plane] - common
                diff_var = (variances[full, plane] * (4.0 / 9.0)
                            + (variances[full].sum(axis=1)
                               - variances[full, plane]) / 9.0)
                result = stats.dersimonian_laird(diff, diff_var)
                lb = stats.q_profile_lower_bound(diff, diff_var)
                common_diff["diff"].append({
                    "comp": "xy"[comp], "plane": plane,
                    "tau_dots": float(np.sqrt(result["tau2"]))
                    if np.isfinite(result["tau2"]) else None,
                    "tau2_lb99_dots2": lb})
    return {"lane": lane_id, "pass": pass_tag,
            "correlograms": correlograms,
            "min_sep_curve": min_sep_curve,
            "common_diff": common_diff}


def power_block(frame: CaptureFrame, lane_id: str,
                diagnostics: dict) -> dict:
    """G5: realized W, n_w, rho_bar, n_eff and the implied tau_min."""
    from scipy import stats as scipy_stats

    lane = frame.lane_index(lane_id)
    rows = [row for row in lane_component_estimates(
        frame, lane, PASS_CENSUS) or lane_component_estimates(
        frame, lane, PASS_DENSE) if row["plane"] == 0]
    if not rows:
        return {}
    w = rows[0]["windows"]
    n_median = rows[0]["median_n_w"]
    sigma = rows[0]["sigma_dots"]
    rho_values = []
    for entry in diagnostics.get("correlograms", []):
        for comp in ("x", "y"):
            rho = entry[comp]["rho"]
            if rho and np.isfinite(rho[0]):
                rho_values.append(rho[0])
    rho_bar = float(np.median(rho_values)) if rho_values else 0.0
    n_eff = n_median / (1.0 + max(0.0, rho_bar) * (n_median - 1.0))
    n_total = w * n_median
    z_alpha = float(scipy_stats.norm.ppf(0.99))
    z_beta = float(scipy_stats.norm.ppf(0.80))
    lambda_min = (z_alpha + z_beta) * np.sqrt(
        2.0 / max(1, w - 1) + 2.0 / max(1, n_total - w))
    tau_min = sigma * np.sqrt(lambda_min / max(n_eff, 1e-9))
    return {"lane": lane_id, "windows": w,
            "median_n_w": n_median, "sigma_dots": sigma,
            "rho_bar_nearest_bin": rho_bar, "n_eff": float(n_eff),
            "tau_min_dots": float(tau_min)}


def pregates(frame: CaptureFrame) -> dict:
    """G1 peak-lock, G3 saturation; per census lane and plane."""
    out: dict = {"g1_peak_lock": [], "g3_saturation": []}
    max_shift_dots = {2.0: 1.5, 3.0: 2.5}.get(frame.cell_dots, 2.5)
    for lane_id in frame.census_lanes:
        lane = frame.lane_index(lane_id)
        anchors = frame.lane_anchors(lane, PASS_CENSUS,
                                     furniture_only=False)
        if not anchors.shape[0]:
            continue
        for plane in range(3):
            rows = _col(anchors, "plane", "anchors") == plane
            if rows.sum() < 50:
                continue
            offs = np.concatenate((
                _col(anchors, "off_x_dots", "anchors")[rows],
                _col(anchors, "off_y_dots", "anchors")[rows]))
            ks = stats.ks_uniform_pvalue(np.mod(offs * 2.0, 1.0))
            out["g1_peak_lock"].append(
                {"lane": lane_id, "plane": plane, **ks})
            magnitude = np.max(np.abs(np.stack((
                _col(anchors, "off_x_dots", "anchors")[rows],
                _col(anchors, "off_y_dots", "anchors")[rows]))), axis=0)
            saturated = float(np.mean(
                magnitude >= max_shift_dots - SATURATION_MARGIN_DOTS))
            out["g3_saturation"].append(
                {"lane": lane_id, "plane": plane,
                 "rate": saturated})
    return out


def phase_gate(frame: CaptureFrame, lane: int) -> list[dict]:
    """G2: window medians regressed on sub-native-pixel origin phase."""
    anchors = frame.lane_anchors(lane, PASS_CENSUS, furniture_only=True)
    if not anchors.shape[0]:
        anchors = frame.lane_anchors(lane, PASS_DENSE, furniture_only=True)
    if not anchors.shape[0]:
        return []
    centers = frame.window_centers(lane)
    window_rows = frame.lane_windows(lane)
    phase = np.stack((
        np.mod(_col(window_rows, "origin_y", "windows"), 1.0),
        np.mod(_col(window_rows, "origin_x", "windows"), 1.0)), axis=1)
    window_of = recorded_window_of(anchors)
    residual = residuals(frame, lane, anchors)
    out = []
    for plane in range(3):
        rows = _col(anchors, "plane", "anchors") == plane
        for comp in range(2):
            values = residual[rows, comp]
            keep = np.isfinite(values)
            summary = stats.window_summaries(
                values[keep], window_of[rows][keep], centers.shape[0],
                MIN_WINDOW_ANCHORS)
            ids = summary["window_ids"]
            if ids.size < 12:
                continue
            medians = summary["medians"]
            design = np.stack((
                np.ones(ids.size),
                np.sin(2 * np.pi * phase[ids, comp ^ 1]),
                np.cos(2 * np.pi * phase[ids, comp ^ 1]),
                np.sin(2 * np.pi * phase[ids, comp]),
                np.cos(2 * np.pi * phase[ids, comp])), axis=1)
            def r_squared(matrix: np.ndarray) -> float:
                coeffs, *_ = np.linalg.lstsq(matrix, medians, rcond=None)
                fitted = matrix @ coeffs
                total = float(np.sum((medians - medians.mean()) ** 2))
                if total <= 0:
                    return float("nan")
                return float(np.sum((fitted - medians.mean()) ** 2)) / total

            observed = r_squared(design)
            rng = np.random.default_rng(ANALYZE_SEED + 7 * plane + comp)
            permuted = np.empty(999, np.float64)
            for rep in range(999):
                order = rng.permutation(ids.size)
                permuted[rep] = r_squared(
                    np.concatenate((design[:, :1], design[order, 1:]),
                                   axis=1))
            p_value = float(
                (1 + np.sum(permuted >= observed)) / (999 + 1))
            out.append({
                "lane": frame.lane_ids[lane], "plane": plane,
                "comp": "xy"[comp],
                "r2_phase": observed,
                "p_permutation": p_value,
                "windows": int(ids.size)})
    return out


def primary_test(frame: CaptureFrame, lane_id: str) -> dict:
    """The one pre-registered test: omnibus on the census pass.

    Bootstrap p is CONSERVATIVE by construction (naive resampling
    inflates the group-median variance ~1.4x while the observed
    medians are raw — review conclusion); the placebo half is the
    self-normalized lattice comparison (review B2).
    """
    lane = frame.lane_index(lane_id)
    pass_tag = (PASS_CENSUS if frame.lane_anchors(
        lane, PASS_CENSUS, True).shape[0] else PASS_DENSE)
    anchors = frame.lane_anchors(lane, pass_tag, furniture_only=True)
    if not anchors.shape[0]:
        return {"error": f"no anchors at {lane_id}"}
    centers = frame.window_centers(lane)
    window_of = recorded_window_of(anchors)
    residual = residuals(frame, lane, anchors)
    z, _ = whiten(anchors, residual, window_of)
    cells = np.stack((_col(anchors, "cell_y", "anchors"),
                      _col(anchors, "cell_x", "anchors")), axis=1)
    plane_frames = []
    for plane in range(3):
        rows = _col(anchors, "plane", "anchors") == plane
        # Review M5: thin per plane — pooled thinning annihilates the
        # cross-plane shared cells the omnibus depends on.
        thin = np.zeros(anchors.shape[0], np.bool_)
        thin[rows] = stats.min_separation_thin(
            cells[rows], window_of[rows], 4, ANALYZE_SEED + plane)
        keep = rows & thin & np.isfinite(z[:, 0]) & np.isfinite(z[:, 1])
        if keep.sum() < 30:
            continue
        z_comps = []
        for comp in range(2):
            values = z[keep, comp]
            summary = stats.window_summaries(
                values, window_of[keep], centers.shape[0],
                MIN_WINDOW_ANCHORS)
            variances = stats.median_variances(summary)
            prediction = refit_m1(
                summary["medians"], variances,
                centers[summary["window_ids"]], frame.cells_yx)
            trend = np.zeros(values.size)
            for row, window in enumerate(summary["window_ids"]):
                trend[window_of[keep] == window] = prediction[row]
            z_comps.append(values - trend)
        plane_frames.append({
            "cells": cells[keep],
            "window_of": window_of[keep],
            "z_by_comp": z_comps})
    if not plane_frames:
        return {"error": f"insufficient anchors at {lane_id}"}
    bootstrap = stats.synchronized_bootstrap_pvalue(
        plane_frames, centers.shape[0], BOOTSTRAP_REPS, ANALYZE_SEED)
    placebo = stats.calibrated_placebo_pvalue(
        plane_frames, WINDOW_STRIDE_CELLS, PLACEBO_TRANSLATIONS,
        40, ANALYZE_SEED)
    return {
        "lane": lane_id, "pass": pass_tag,
        "min_separation": 4,
        "bootstrap": bootstrap,
        "placebo": placebo,
    }


def deployed_view(frame: CaptureFrame, lane_id: str) -> dict:
    """G4 reach + the DeltaMSE gate at the deployed budget.

    Two phases: per (plane, comp) build M1-detrended window medians,
    raw per-window groups, and the calibrated tau^2 lower bound
    (review B3/M6: resampling-calibrated Q threshold + half-split
    design effect); then the plane-differential medians (plane minus
    cross-plane mean, windows where all three planes have data) feed
    gate (iv) through the SAME calibrated threshold — an approximation
    (the diff series has no raw groups of its own), documented here.
    DeltaMSE is computed per component with that component's own
    sigma^2_w (review M4) and summed per plane.
    """
    lane = frame.lane_index(lane_id)
    streams = list(frame.run["stream_ids"])
    if len(streams) not in (1, 3):
        raise SystemExit(f"unexpected stream_ids {streams}")
    tiles_yx = (frame.cells_yx[0] // 64, frame.cells_yx[1] // 64)
    certified: dict = {name: set() for name in streams}
    for row in frame.run["certificates"]:
        certified[row["stream_id"]].add(
            (int(row["tile_yx"][0]), int(row["tile_yx"][1])))
    centers = frame.window_centers(lane)
    if not centers.size:
        return {"error": f"no windows at {lane_id}"}
    tile_centers = np.stack(np.meshgrid(
        np.arange(tiles_yx[0]) * 64 + 32,
        np.arange(tiles_yx[1]) * 64 + 32,
        indexing="ij"), axis=2).reshape(-1, 2).astype(np.float64)
    tile_window = nearest_center_attribution(tile_centers, centers)
    production = frame.lane_anchors(lane, PASS_PROD, furniture_only=False)
    analysis_pass = (PASS_CENSUS if frame.lane_anchors(
        lane, PASS_CENSUS, True).shape[0] else PASS_DENSE)
    census = frame.lane_anchors(lane, analysis_pass, furniture_only=True)
    census_window = recorded_window_of(census)
    census_residual = residuals(frame, lane, census)
    census_cells = np.stack((
        _col(census, "cell_y", "anchors"),
        _col(census, "cell_x", "anchors")), axis=1)

    # Phase 1: per (plane, comp) detrended medians + calibrated LB.
    W = centers.shape[0]
    detrended = np.full((3, 2, W), np.nan)
    sigma2 = np.full((3, 2, W), np.nan)
    medvar = np.full((3, 2, W), np.nan)
    calibrations: list[list[dict]] = [[{}, {}] for _ in range(3)]
    for plane in range(3):
        rows = _col(census, "plane", "anchors") == plane
        for comp in range(2):
            values = census_residual[rows, comp]
            cwin = census_window[rows]
            ccells = census_cells[rows]
            keep = np.isfinite(values)
            values, cwin, ccells = values[keep], cwin[keep], ccells[keep]
            summary = stats.window_summaries(
                values, cwin, W, MIN_WINDOW_ANCHORS)
            if summary["window_ids"].size < 6:
                continue
            variances = stats.median_variances(summary)
            prediction = refit_m1(
                summary["medians"], variances,
                centers[summary["window_ids"]], frame.cells_yx)
            groups, group_cells = [], []
            for row_index, window in enumerate(summary["window_ids"]):
                mask = cwin == window
                groups.append(values[mask] - prediction[row_index])
                group_cells.append(ccells[mask])
            calibrations[plane][comp] = stats.calibrated_tau2_lower_bound(
                groups, group_cells, variances,
                seed=ANALYZE_SEED + 31 * plane + comp)
            detrended[plane, comp, summary["window_ids"]] = (
                summary["medians"] - prediction)
            sigma2[plane, comp, summary["window_ids"]] = (
                summary["scales"] ** 2
                * calibrations[plane][comp]["deff"])
            medvar[plane, comp, summary["window_ids"]] = (
                variances * calibrations[plane][comp]["deff"])

    # Phase 2: per plane, uncertified weights + per-comp DeltaMSE +
    # the diff-mode LB for gate (iv).
    out_planes = []
    for plane in range(3):
        stream = streams[plane] if len(streams) == 3 else streams[0]
        uncertified = np.asarray([
            1.0 if (int(tile[0] // 64), int(tile[1] // 64))
            not in certified[stream] else 0.0
            for tile in tile_centers])
        u_w = np.zeros(W)
        np.add.at(u_w, tile_window, uncertified)
        prod_rows = _col(production, "plane", "anchors") == plane
        n_w = np.bincount(
            _col(production, "window_index", "anchors")[prod_rows]
            .astype(np.int64), minlength=W).astype(np.float64)
        components = []
        medians_x = detrended[plane, 0]
        medians_y = detrended[plane, 1]
        for comp in range(2):
            calibration = calibrations[plane][comp]
            if not calibration:
                continue
            tau2_lb = calibration["tau2_lb"]
            tau2_lb = tau2_lb if np.isfinite(tau2_lb) else 0.0
            gate = stats.delta_mse_gate(
                u_w, n_w, tau2_lb, sigma2[plane, comp], KAPPA)
            # Gate (iv): plane-minus-cross-plane-mean medians through
            # the same calibrated threshold (approximation).
            all_planes = np.isfinite(detrended[:, comp, :]).all(axis=0)
            diff_lb = 0.0
            if all_planes.sum() >= 6:
                diff_medians = (detrended[plane, comp, all_planes]
                                - detrended[:, comp, all_planes]
                                .mean(axis=0))
                others = [q for q in range(3) if q != plane]
                diff_var = (medvar[plane, comp, all_planes] * (4.0 / 9.0)
                            + sum(medvar[q, comp, all_planes]
                                  for q in others) / 9.0)
                diff_bound = stats.q_profile_lower_bound(
                    diff_medians, diff_var,
                    threshold=calibration["threshold"])
                diff_lb = (diff_bound
                           if np.isfinite(diff_bound) else 0.0)
            diff_gate = stats.delta_mse_gate(
                u_w, n_w, diff_lb, sigma2[plane, comp], KAPPA)
            components.append({
                "comp": "xy"[comp],
                "tau2_lb99_dots2": tau2_lb,
                "deff": calibration["deff"],
                "delta_mse": gate["delta_mse"],
                "tau2_diff_lb99_dots2": diff_lb,
                "delta_mse_diff": diff_gate["delta_mse"],
            })
        # Per-axis RMS (conservative vs the vector form by sqrt(2);
        # the 0.03-cell floor is the per-axis half phase step).
        rms = stats.shrunk_correction_rms(
            u_w, n_w, medians_x, medians_y, frame.cell_dots, KAPPA)
        reach = (float(np.sum(u_w[n_w >= KAPPA]) / np.sum(u_w))
                 if np.sum(u_w) > 0 else None)
        out_planes.append({
            "plane": plane, "stream": stream,
            "uncertified_tiles": float(np.sum(u_w)),
            "reach_n8": reach,
            "components": components,
            "delta_mse": float(sum(
                row["delta_mse"] for row in components)),
            "delta_mse_diff": float(sum(
                row["delta_mse_diff"] for row in components)),
            "rms_correction_cells": rms,
            "median_n_production": float(np.median(n_w[n_w > 0]))
            if (n_w > 0).any() else 0.0,
        })
    return {"lane": lane_id, "analysis_pass": analysis_pass,
            "streams": streams, "planes": out_planes}


def heatmap_png(frame: CaptureFrame, lane_id: str, path) -> None:
    """3 planes x 2 comps window-median map, diverging colormap."""
    from PIL import Image

    lane = frame.lane_index(lane_id)
    pass_tag = (PASS_CENSUS if frame.lane_anchors(
        lane, PASS_CENSUS, True).shape[0] else PASS_DENSE)
    anchors = frame.lane_anchors(lane, pass_tag, furniture_only=True)
    if not anchors.shape[0]:
        return
    centers = frame.window_centers(lane)
    window_rows = frame.lane_windows(lane)
    window_of = recorded_window_of(anchors)
    residual = residuals(frame, lane, anchors)
    scale = 16
    height = frame.cells_yx[0] // scale
    width = frame.cells_yx[1] // scale
    panels = []
    limit = 0.3
    for plane in range(3):
        for comp in range(2):
            image = np.full((height, width, 3), 235, np.uint8)
            rows = _col(anchors, "plane", "anchors") == plane
            values = residual[rows, comp]
            keep = np.isfinite(values)
            summary = stats.window_summaries(
                values[keep], window_of[rows][keep], centers.shape[0],
                MIN_WINDOW_ANCHORS)
            for index, window in enumerate(summary["window_ids"]):
                row = window_rows[window]
                y0 = int(row[COLUMN["windows"].index("bbox_y0")]) // scale
                y1 = int(row[COLUMN["windows"].index("bbox_y1")]) // scale
                x0 = int(row[COLUMN["windows"].index("bbox_x0")]) // scale
                x1 = int(row[COLUMN["windows"].index("bbox_x1")]) // scale
                value = float(np.clip(
                    summary["medians"][index] / limit, -1, 1))
                if value >= 0:
                    color = (255, int(255 * (1 - value)),
                             int(255 * (1 - value)))
                else:
                    color = (int(255 * (1 + value)),
                             int(255 * (1 + value)), 255)
                image[y0:y1 + 1, x0:x1 + 1] = color
            panels.append(image)
    grid = np.concatenate([
        np.concatenate(panels[2 * p:2 * p + 2], axis=1)
        for p in range(3)], axis=0)
    Image.fromarray(grid).save(path)


def cmd_analyze(args: argparse.Namespace) -> int:
    frame = CaptureFrame(args.capture)
    work = corpus.work_dir("regmap")
    report: dict = {
        "capture": frame.key,
        "seed": ANALYZE_SEED,
        "rot_k": frame.rot_k,
        "lanes": frame.lane_ids,
        "census_lanes": frame.census_lanes,
        "spy_pass_failures": frame.meta["spy_pass_failures"],
        "pre_gates": pregates(frame),
        "estimates": [],
        "phase_gate": [],
        "primary": None,
        "deployed": None,
    }
    for lane_id in frame.lane_ids:
        lane = frame.lane_index(lane_id)
        for pass_tag in (PASS_PROD, PASS_DENSE, PASS_CENSUS):
            report["estimates"].extend(
                lane_component_estimates(frame, lane, pass_tag))
    if frame.ordinary:
        last = frame.ordinary[-1]
        report["phase_gate"] = phase_gate(
            frame, frame.lane_index(last))
        report["census_diagnostics"] = census_diagnostics(frame, last)
        report["primary"] = primary_test(frame, last)
        report["deployed"] = deployed_view(frame, last)
        report["power"] = power_block(
            frame, last, report["census_diagnostics"])
        for lane_id in dict.fromkeys(
                [frame.ordinary[0], last]):
            heatmap_png(frame, lane_id,
                        work / f"{frame.key}-{lane_id}-medians.png")
    path = work / f"{frame.key}-analysis.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "capture": frame.key,
        "estimates": len(report["estimates"]),
        "primary_p_bootstrap": (report["primary"] or {}).get(
            "bootstrap", {}).get("p"),
        "primary_p_placebo": (report["primary"] or {}).get(
            "placebo", {}).get("p"),
        "out": str(path),
    }))
    return 0


def cmd_verdict(args: argparse.Namespace) -> int:
    work = corpus.work_dir("regmap")
    captures = args.capture or [
        "xerox-c2-cmy7", "xerox-c2-cmy8", "hp-c3-cmy8", "xerox-c3-cmy7"]
    rows = []
    for key in captures:
        path = work / f"{key}-analysis.json"
        if not path.exists():
            rows.append({"capture": key, "status": "missing"})
            continue
        report = json.loads(path.read_text())
        primary = report.get("primary") or {}
        deployed = report.get("deployed") or {}
        planes = deployed.get("planes", [])
        total_mse = sum(row.get("delta_mse") or 0.0 for row in planes)
        total_mse_diff = sum(
            row.get("delta_mse_diff") or 0.0 for row in planes)
        weights = [row.get("uncertified_tiles") or 0.0 for row in planes]
        rms_values = [row.get("rms_correction_cells") for row in planes]
        weighted = [
            (weight, value) for weight, value in zip(weights, rms_values)
            if value is not None and np.isfinite(value) and weight > 0]
        aggregate_rms = (
            float(np.sqrt(
                sum(weight * value ** 2 for weight, value in weighted)
                / sum(weight for weight, _value in weighted)))
            if weighted else None)
        gate = {
            "i_placebo_p": (primary.get("placebo") or {}).get("p"),
            "i_bootstrap_p": (primary.get("bootstrap") or {}).get("p"),
            "ii_delta_mse_total": total_mse,
            "ii_delta_mse_by_plane": [
                row.get("delta_mse") for row in planes],
            "iii_rms_cells_aggregate": aggregate_rms,
            "iii_rms_cells_by_plane": rms_values,
            "iv_delta_mse_diff_total": total_mse_diff,
            "reach_by_plane": [row.get("reach_n8") for row in planes],
        }
        # The plan's ALL-FOUR conjunction, arm-level (review M9).
        passes = (
            (gate["i_placebo_p"] or 1) < 0.01
            and (gate["i_bootstrap_p"] or 1) < 0.01
            and total_mse > 0
            and (aggregate_rms or 0) >= RMS_FLOOR_CELLS
            and total_mse_diff > 0
        )
        rows.append({"capture": key, "status": "analyzed",
                     "gate": gate,
                     "primary_capture": key == PRIMARY_CAPTURE,
                     "passes_all_four": passes})
    print(json.dumps({"verdict_rows": rows,
                      "note": ("the build decision reads the PRIMARY "
                               "capture's row; other captures are "
                               "replications. Pre-gates G1-G5 are "
                               "adjudicated in the write-up and can "
                               "still block a passing row.")}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.regmap_analyze", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--capture", required=True)
    analyze.set_defaults(handler=cmd_analyze)
    verdict = commands.add_parser("verdict")
    verdict.add_argument("--capture", action="append", default=[])
    verdict.set_defaults(handler=cmd_verdict)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

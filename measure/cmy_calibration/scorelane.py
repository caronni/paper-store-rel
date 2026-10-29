"""M1 gate — the cmy receiver's production score lane on e044 sheet B at truth-fitted poses.

What: the colour job (`color_region.region_job`, the A3 pin's route in test_h3_e2e_cmy) run on the real 2400 dpi
capture of e044 sheet B (`c3-cmy-r0850@35x24`) with every window at its TRUTH-FITTED pose, at the score bound
`CMY7_RELATIVE_SCORE_BOUND = 20` and with the bound LIFTED (monkeypatched inside this process, never edited):
  poses    measure/e044_cmy_truth/readout.py's pose fitting (load_page, coarse_seed, read_windows twice with the
           3 x 3 prior, the per-plane poses of every 36-cell window) -> poses.json;
  measure  per receiver level (the capture's ppc ladder 2, 4, 6, 12, decimated by lib/decimate as intake does):
           the production 200-cell windows (lib.geometry.window_starts), each a Placement whose native affine is
           the least-squares fit of C's truth points over the window's cells, composed by
           _h3_fixture_geometry.window_pose (the production composer).  Three arms through color_region's
           `offsets_of` seam: TRUTH (every plane at its own truth point per cell, C's residual from the window
           affine included), REL (the charter's: C at the window pose, M and Y at pose + their offset from C — what
           a converged page field hands the job under the gauge F_C = 0) and POSE (no offsets: all three planes at
           C's window pose, the job before the field exists); the head's three-way gate picks the arm as in
           production.  Regimes: COLD (no certificates: the furniture-only fit), REFIT (the generator's GT tiles
           certified on one tile parity, the other parity read; both folds) and FIRST-FIRE (cold, each window its
           own region, the first colour fire of a decode), each per arm (POSE: cold and first-fire).  Per regime and
           bound the tile cuts are assembled by tiles.color_candidates + assemble_cut (the owner rule) and read
           through tiles.stream_llrs (no sibling) and tiles.attempt_tile (scan, then retry150 on a failed scan);
  report   the RESULTS extract from scorelane.json (--full: every table per level).
Why: on the blur-free c3 sim the score lane's per-cell L-infinity divisor squeezes the true state's W-relative
margin under log 2 where a far state dominates max |score|, so the label demap's signs go wrong on whole states
while the argmax stays right; this asks whether paper evidence (CMY-RECEIVER-PLAN A8, M1) shows it.
How: GT = the emitter's page000_gt.npy; the GT certificates are minted by attempt_tile on a noiseless score-space
cut of each GT tile (every one must certify and re-encode to the GT label bits).  No production code changes.

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -u -m measure.cmy_calibration.scorelane --stage poses
    ... --stage measure [--levels 0 1 2 3] [--workers 4]
    ... --stage report [--full]
Artefacts: scratch2/e044/scorelane/ (poses.json, scorelane.json, tiles.csv).
"""
from __future__ import annotations

import argparse
import json
import resource
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.interpolate import RegularGridInterpolator

from holo.receiver import data
from holo.receiver.format import identity, tile_codec
from holo.receiver.lib import decimate
from holo.receiver.lib import geometry as lib_geometry
from holo.receiver.plugins import color_model, color_region, color_region_head, color_sites, tiles
from holo.receiver.plugins.intake import build_levels
from holo.receiver.tests import _h3_fixture_geometry as fixture_geometry

REPO_MAIN = Path("<repo>")
WORKTREE = Path(__file__).resolve().parents[2]
ART = REPO_MAIN / "scratch2" / "e044" / "scorelane"
SCAN = REPO_MAIN / "scratch2" / "e044" / "captures" / "E044-B-c3-cmy-r0850-hp-scan.tiff"
MANIFEST = WORKTREE / "build" / "p1" / "c3" / "manifest.json"
GT = WORKTREE / "build" / "p1" / "c3" / "page000_gt.npy"
READOUT_SUMMARY = REPO_MAIN / "scratch2" / "e044" / "readout" / "B" / "summary.json"
FORMAT_REF = "1i200-cmy-r0850-p120-v1@35x24"
SCAN_DPI = 2400
CAPTURE_ID = "e044-B-scan"
BOUNDS: dict[str, float] = {"20": 20.0, "lifted": float("inf")}
LEFT_ZONE_MM = 115.0
DOT_MM = 25.4 / 600.0
TILE = tiles.TILE_CELLS
PLANES = ("C", "M", "Y")
STATE_NAMES = ("W", "C", "M", "Y")
ZONES = ("left", "right")
PCTS = (50, 90, 99)
#: The bound is a module global of color_region_head: one bound at a time in this process.
_BOUND_LOCK = threading.Lock()
Rec = dict[str, Any]


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def peak_rss_gb() -> float:
    """ru_maxrss of this process (bytes on darwin)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


# ---------------------------------------------------------------- stage 1: the truth-fitted poses

def stage_poses(art: Path, workers: int) -> Rec:
    """readout.py's pose fitting, verbatim calls: the seed, the orientation, the page white and the two window
    passes (the second on the 3 x 3 prior); per window the per-plane offsets (dy, dx dots, prior included,
    "ok" flags only) over the page affine A (page mm -> scan [col, row])."""
    from measure.cmy_probe.bands import WINDOW_CELLS, window_starts
    from measure.e041_probe_readout import Scan, sub_px_per_dot
    from measure.e044_cmy_truth.readout import (DPI, coarse_seed, load_page, offsets, page_white, prior_field,
                                                read_windows, refine_affine, window_table)
    t0 = time.time()
    page = load_page(MANIFEST, GT)
    scan = Scan(SCAN)
    sub = sub_px_per_dot(scan.dpi, DPI)
    seed = coarse_seed(scan, page)
    rs, cs = window_starts(page["rows"], WINDOW_CELLS), window_starts(page["cols"], WINDOW_CELLS)
    centre = [(rs[len(rs) // 2 + a], cs[len(cs) // 2 + b]) for a in (-1, 0, 1) for b in (-1, 1)]
    peaks = {k: float(np.median([w.get("reg_peak", 0.0) for w in read_windows(
        scan, A, page, page_white(scan, A, page), sub, centre, workers)])) for k, A in seed["candidates"].items()}
    orient = max(peaks, key=peaks.get)
    A = seed["candidates"][orient]
    white = page_white(scan, A, page)
    keys = [(r, c) for r in rs for c in cs]
    wins: list[Rec] = []
    for k in range(2):
        wins = read_windows(scan, A, page, white, sub, keys, workers, None, prior_field(wins, rs, cs) if k else None)
        print(f"poses: window pass {k + 1}: {sum('skipped' in w for w in wins)} skipped, "
              f"{sum(w.get('d_mean') is not None for w in wins)} with all planes ok ({time.time() - t0:.0f} s)")
    _, fin, resid = refine_affine(A, wins)
    offs = offsets(window_table(wins, resid))
    out = {"scan": str(SCAN), "manifest": str(MANIFEST), "gt": str(GT), "orientation": orient, "peaks": peaks,
           "sub": sub, "white_rgb": white, "affine_mm_to_colrow": A, "window_cells": WINDOW_CELLS,
           "rows_starts": rs, "cols_starts": cs, "nonaffine": fin, "offsets_vs_C_dots": offs,
           "windows": [{"r0": w["r0"], "c0": w["c0"], "d": w.get("d", {}), "flags": w.get("flags", {}),
                        "reg_ok": w.get("reg_ok"), "reg_peak": w.get("reg_peak")} for w in wins],
           "seconds": time.time() - t0, "peak_rss_gb": peak_rss_gb()}
    if READOUT_SUMMARY.exists():
        ref = json.loads(READOUT_SUMMARY.read_text())["offsets_dots"]
        out["readout_offsets_vs_C_dots"] = ref
        print("poses: offsets vs C here", json.dumps(jsonable({k: v["median_dy_dx"] for k, v in offs.items()})),
              "readout", json.dumps({k: v["median_dy_dx"] for k, v in ref.items()}))
    (art / "poses.json").write_text(json.dumps(jsonable(out), indent=1))
    print(f"poses: wrote {art / 'poses.json'} ({out['seconds']:.0f} s, peak RSS {out['peak_rss_gb']:.1f} GB)")
    return out


# ---------------------------------------------------------------- the truth field

def plane_offset_field(poses: Rec, plane: str, rows: int, cols: int) -> np.ndarray:
    """(rows, cols, 2) per-cell (dy, dx) plane offset in dots: bilinear between the 36-cell windows' centres
    (clamped at the outermost centres), a window without an "ok" pose for the plane filled from its nearest
    window that has one."""
    rs, cs, wc = poses["rows_starts"], poses["cols_starts"], poses["window_cells"]
    grid = np.full((len(rs), len(cs), 2), np.nan)
    ri, ci = {r: i for i, r in enumerate(rs)}, {c: j for j, c in enumerate(cs)}
    for w in poses["windows"]:
        if plane in w["d"]:
            grid[ri[w["r0"]], ci[w["c0"]]] = w["d"][plane]
    missing = np.isnan(grid[..., 0])
    if missing.all():
        raise SystemExit(f"plane {plane}: no window has an ok pose")
    if missing.any():
        _, (iy, ix) = ndimage.distance_transform_edt(missing, return_indices=True)
        grid = grid[iy, ix]
    ry = np.asarray(rs, float) + wc / 2.0
    cx = np.asarray(cs, float) + wc / 2.0
    interp = RegularGridInterpolator((ry, cx), grid, method="linear")
    out = np.empty((rows, cols, 2))
    yy = np.clip(np.arange(rows) + 0.5, ry[0], ry[-1])
    xx = np.clip(np.arange(cols) + 0.5, cx[0], cx[-1])
    for r0 in range(0, rows, 256):
        Y, X = np.meshgrid(yy[r0:r0 + 256], xx, indexing="ij")
        out[r0:r0 + 256] = interp(np.stack([Y, X], -1))
    return out


def truth_points(poses: Rec, page_origin_dots_yx: tuple[int, int], cell_dots: int, rows: int,
                 cols: int) -> np.ndarray:
    """(3, rows, cols, 2) native scan px (row, col), pixel-index frame, of every cell centre per plane: page dot
    origin + cell_dots * c + centre + the plane's offset, through the page affine.  centre = cell_dots / 2 -
    0.5 / sub is where the readout's own reads sit (its rect pixel k is page dot xd + (k - m) / sub, and
    cell_samples' box centre is k = cell_px * c + cell_px / 2 - 0.5 past the window's plane offset)."""
    A = np.asarray(poses["affine_mm_to_colrow"], float)
    centre = cell_dots / 2.0 - 0.5 / int(poses["sub"])
    oy, ox = page_origin_dots_yx
    base_y = oy + cell_dots * np.arange(rows, dtype=float) + centre
    base_x = ox + cell_dots * np.arange(cols, dtype=float) + centre
    out = np.empty((3, rows, cols, 2))
    for p, plane in enumerate(PLANES):
        d = plane_offset_field(poses, plane, rows, cols)
        x_mm = (base_x[None, :] + d[..., 1]) * DOT_MM
        y_mm = (base_y[:, None] + d[..., 0]) * DOT_MM
        out[p, ..., 1] = A[0, 0] * x_mm + A[0, 1] * y_mm + A[0, 2]
        out[p, ..., 0] = A[1, 0] * x_mm + A[1, 1] * y_mm + A[1, 2]
    return out


# ---------------------------------------------------------------- GT: states and certificates

def gt_states(row: identity.FormatRow, cell_dots: int) -> np.ndarray:
    """(rows, cols) presence ids of the emitter's GT page, one dot per cell sampled at the cell's centre dot."""
    rows, cols = row.cells_yx
    dots = np.unpackbits(np.load(GT, allow_pickle=False), axis=2, count=cols * cell_dots, bitorder="big")
    if dots.shape != (3, rows * cell_dots, cols * cell_dots):
        raise SystemExit(f"GT {dots.shape} vs the row's cells {row.cells_yx} at {cell_dots} dots")
    cells = dots[:, cell_dots // 2::cell_dots, cell_dots // 2::cell_dots]
    return tile_codec.planes_to_states(np.moveaxis(cells, 0, -1))


def gt_tile_cut(row: identity.FormatRow, states: np.ndarray, ty: int, tx: int) -> tiles.TileCut:
    """A noiseless score-space cut of one GT tile (the A3 test's construction at amplitude 10, no noise)."""
    tile = states[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE].ravel()
    loglik = 10.0 * np.eye(len(row.state_ids))[color_region_head.state_columns(row.state_ids, tile)]
    return tiles.TileCut("gt", 0, 0, ty, tx, (loglik[:, 1:] - loglik[:, :1]).astype(np.float32),
                         np.arange(tile_codec.N_CELLS, dtype=np.uint16))


def gt_certificates(row: identity.FormatRow, geometry: identity.SiteGeometry, states: np.ndarray,
                    workers: int) -> dict[tuple[int, int, int, str], data.Certificate]:
    """Every GT tile's two label streams certified by attempt_tile on its noiseless cut; refuses unless every
    stream certifies and the two certificates' projection (format furniture included) IS the GT tile."""
    keys = [(ty, tx) for ty in range(row.tiles_yx[0]) for tx in range(row.tiles_yx[1])]

    def one(key: tuple[int, int]) -> list[tuple[tuple[int, int, int, str], data.Certificate]]:
        cut = gt_tile_cut(row, states, *key)
        out = []
        for fact in row.streams:
            res = tiles.attempt_tile(row, geometry, (cut,), fact.stream_id, tiles.STAGE_SCAN)
            if res.certificate is None:
                raise SystemExit(f"GT tile {key} stream {fact.stream_id}: {res.fact.outcome}")
            out.append(((0, key[0], key[1], fact.stream_id), res.certificate))
        return out
    with ThreadPoolExecutor(workers) as ex:
        certs = dict(kv for part in ex.map(one, keys) for kv in part)
    planes = tile_codec.states_to_planes(states)
    for ty, tx in keys:
        bits, known = color_sites.certified_projection(row, geometry, 0, ty, tx, certs)
        if not known.all() or not np.array_equal(bits, planes[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]):
            raise SystemExit(f"GT tile ({ty}, {tx}): the certificates do not project to the GT")
    return certs


# ---------------------------------------------------------------- the receiver's levels, windows and offsets

class Raster:
    """A PlaneRaster stand-in: `open()` hands back the level's array (region_job reads nothing else)."""

    def __init__(self, array: np.ndarray) -> None:
        self.array = array

    def open(self) -> np.ndarray:
        return self.array


def level_planes(img: np.ndarray, level: data.Level) -> tuple[Raster, Raster, Raster]:
    """R, G, B at one level: the native views, or lib/decimate's area decimation of each native channel (what
    intake writes for a colour family, `derived_planes`)."""
    if level.scale == 1:
        return tuple(Raster(img[..., c]) for c in range(3))  # type: ignore[return-value]
    transform = decimate.AreaPixelTransform(level.scale)
    return tuple(Raster(decimate.area_decimate(img[..., c], transform)) for c in range(3))  # type: ignore[return-value]


def level_windows(row: identity.FormatRow, level: data.Level, truth: np.ndarray, px_per_dot: float,
                  ) -> tuple[tuple[color_region.RegionWindow, ...], Rec]:
    """The production window grid (lib.geometry.window_starts, 200 cells, step 160), each window a Placement at
    the least-squares affine of C's truth points over its cells (page cell + 0.5 -> native px, the native-affine
    convention), composed by the fixture door; the fit's residual (C's non-affine part inside the window)."""
    rows, cols = row.cells_yx
    windows, resid = [], []
    for k, (y0, x0) in enumerate((y, x) for y in lib_geometry.window_starts(rows)
                                 for x in lib_geometry.window_starts(cols)):
        y1, x1 = min(rows, y0 + lib_geometry.WINDOW_CELLS), min(cols, x0 + lib_geometry.WINDOW_CELLS)
        cells = fixture_geometry.grid_cells((y0, x0), (y1 - y0, x1 - x0))
        pts = truth[0, cells[:, 0], cells[:, 1]]
        design = np.column_stack([cells + 0.5, np.ones(len(cells))])
        sol, *_ = np.linalg.lstsq(design, pts, rcond=None)
        native_affine = (float(sol[0, 0]), float(sol[1, 0]), float(sol[2, 0]),
                         float(sol[0, 1]), float(sol[1, 1]), float(sol[2, 1]))
        linear = np.asarray(((native_affine[0], native_affine[1]), (native_affine[3], native_affine[4])))
        res = pts - design @ sol
        resid.append(float(np.sqrt((res ** 2).sum(1).mean())) / px_per_dot)
        wid = (CAPTURE_ID, level.index, k, (y0, x0, y1, x1))
        placement = fixture_geometry.window_placement(
            wid, native_affine, cells - np.asarray((y0, x0)), patch_ordinal=k, page=0,
            pitch_px=float(np.sqrt(abs(np.linalg.det(linear)))), route="truth")
        windows.append(fixture_geometry.window_pose(row, placement, scale=level.scale))
    return tuple(windows), {"windows": len(windows), "c_residual_rms_dots_median": float(np.median(resid)),
                            "c_residual_rms_dots_max": float(np.max(resid))}


def truth_offsets_of(truth: np.ndarray, scale: Fraction, windows: Iterable[color_region.RegionWindow],
                     cell_dots: int) -> Callable[[data.WindowRows], tuple[np.ndarray, ...]]:
    """color_region's `offsets_of` seam: per plane the page-axis dot offset (x, y) that moves each row's pose
    point onto that plane's truth point (raster_points inverts it exactly)."""
    by_ordinal = {w.patch_ordinal: w for w in windows}
    s = float(scale)

    def offsets_of(rows: data.WindowRows) -> tuple[np.ndarray, ...]:
        inv = np.linalg.inv(np.asarray(by_ordinal[rows.patch_ordinal].page_linear, np.float64))
        cells = np.asarray(rows.page_cells_yx, np.int64)
        pose = np.asarray(rows.scan_points_yx, np.float64)
        out = []
        for p in range(3):
            target = (truth[p, cells[:, 0], cells[:, 1]] + 0.5) / s - 0.5
            out.append(np.ascontiguousarray(((target - pose) @ inv.T * cell_dots)[:, ::-1]))
        return tuple(out)
    return offsets_of


def relative_offsets_of(truth: np.ndarray, scale: Fraction, windows: Iterable[color_region.RegionWindow],
                        cell_dots: int) -> Callable[[data.WindowRows], tuple[np.ndarray | None, ...]]:
    """The charter's arm and what a converged page field hands the colour job (gauge F_C = 0): C at the window
    pose, M and Y at pose + (their truth point - C's truth point); C's own non-affine residual inside the window
    stays in all three planes."""
    by_ordinal = {w.patch_ordinal: w for w in windows}
    s = float(scale)

    def offsets_of(rows: data.WindowRows) -> tuple[np.ndarray | None, ...]:
        inv = np.linalg.inv(np.asarray(by_ordinal[rows.patch_ordinal].page_linear, np.float64))
        cells = np.asarray(rows.page_cells_yx, np.int64)
        c_point = truth[0, cells[:, 0], cells[:, 1]]
        return (None,) + tuple(
            np.ascontiguousarray((((truth[p, cells[:, 0], cells[:, 1]] - c_point) / s) @ inv.T * cell_dots)[:, ::-1])
            for p in (1, 2))
    return offsets_of


# ---------------------------------------------------------------- the score lane and its reads

def run_lane(row: identity.FormatRow, geometry: identity.SiteGeometry, windows: tuple[color_region.RegionWindow, ...],
             planes: tuple[Raster, Raster, Raster], certificates: dict, level_index: int,
             offsets_of: Callable | None) -> Rec:
    """One colour-lane fire through the production region_job; its evidence rows and what its head did."""
    t0 = time.thread_time()
    res = color_region.region_job(row, geometry, windows, (), planes, certificates, color_region_head.StackConfig(),
                                  CAPTURE_ID, level_index, offsets_of=offsets_of)
    evidence = [f for f in res.facts if isinstance(f, data.ColorEvidenceRow)]
    (lane_fit,) = [f for f in res.facts if isinstance(f, color_region_head.ColorLaneFit)]
    (event,) = res.events
    head = lane_fit.head
    fit = None if head is None else head.fit
    return {"evidence": evidence, "reason": event.reason, "adopted": bool(event.adopted),
            "corrected_arm": None if head is None else bool(head.corrected),
            "context_head": None if fit is None else fit.context is not None,
            "erased_streams": None if fit is None else list(fit.erased_streams),
            "clipped_label_streams": None if fit is None else list(fit.model.clipped_planes),
            "heldout_loss": None if fit is None else float(fit.heldout_loss),
            "qda_means": None if fit is None else np.concatenate(
                [np.asarray(fit.model.means).ravel()]
                + ([] if fit.context is None else [np.asarray(fit.context.offsets, np.float64).ravel()])),
            "thread_seconds": time.thread_time() - t0}


def with_bound(bound: float, jobs: list[Callable[[], Rec]], workers: int) -> list[Rec]:
    """Run lane jobs with CMY7_RELATIVE_SCORE_BOUND patched to `bound` for the duration (one bound at a time:
    the patch is process-wide), restoring the production value."""
    with _BOUND_LOCK:
        saved = color_region_head.CMY7_RELATIVE_SCORE_BOUND
        color_region_head.CMY7_RELATIVE_SCORE_BOUND = bound
        try:
            with ThreadPoolExecutor(workers) as ex:
                return list(ex.map(lambda job: job(), jobs))
        finally:
            color_region_head.CMY7_RELATIVE_SCORE_BOUND = saved


def assemble_cuts(row: identity.FormatRow, geometry: identity.SiteGeometry, evidence: list[data.ColorEvidenceRow],
                  windows: dict[int, color_region.RegionWindow], level_index: int,
                  tile_keys: Iterable[tuple[int, int]]) -> dict[tuple[int, int], tiles.TileCut]:
    """Per tile the cut the decoder reads: tiles.color_candidates over the rows touching it, assemble_cut's
    owner rule (held-out loss, extent, region) across overlapping windows."""
    arity = tiles.evidence_arity(row)
    touching: dict[int, list[data.ColorEvidenceRow]] = {}
    for crow in evidence:
        cells = np.asarray(crow.page_cells_yx, np.int64)
        for code in np.unique((cells[:, 0] // TILE) * row.tiles_yx[1] + cells[:, 1] // TILE):
            touching.setdefault(int(code), []).append(crow)
    out = {}
    for ty, tx in tile_keys:
        rows = [(windows[c.patch_ordinal].window_id, 0, c) for c in touching.get(ty * row.tiles_yx[1] + tx, [])]
        if not rows:
            continue
        cands, keys = tiles.color_candidates(geometry, arity, 0, ty, tx, rows)
        cut = tiles.assemble_cut(cands, keys, row.cells_yx, CAPTURE_ID, level_index, 0, ty, tx)
        if cut is not None:
            out[(ty, tx)] = cut
    return out


def cut_cells(cut: tiles.TileCut) -> tuple[np.ndarray, np.ndarray]:
    flat = np.asarray(cut.observed_flat, np.int64)
    return cut.ty * TILE + flat // TILE, cut.tx * TILE + flat % TILE


def read_cells(row: identity.FormatRow, ys: np.ndarray, xs: np.ndarray, values: np.ndarray, states: np.ndarray,
               x_mm_of_col: np.ndarray) -> Rec:
    """Per cell: the true state's column, zone, the production stream LLRs' sign errors and exact zeros
    (tiles.stream_llrs, no sibling), the state argmax error and the emitted scores."""
    truth = states[ys, xs]
    col = color_region_head.state_columns(row.state_ids, truth)
    labels = color_model.CMY_COLUMN_LABEL_BITS[col]
    values = np.asarray(values, np.float64)
    out: Rec = {"col": col.astype(np.int8), "left": x_mm_of_col[xs] < LEFT_ZONE_MM, "values": values,
                "y": np.asarray(ys, np.int32), "x": np.asarray(xs, np.int32),
                "argmax_wrong": np.argmax(np.column_stack([np.zeros(len(values)), values]), 1) != col}
    for fact in row.streams:
        llr = tiles.stream_llrs(row, fact, values)
        out[f"{fact.stream_id}_wrong"] = (llr != 0.0) & ((llr > 0.0) != labels[:, fact.label_index])
        out[f"{fact.stream_id}_zero"] = llr == 0.0
        out[f"{fact.stream_id}_positive"] = llr > 0.0
    return out


def attempt_cut(row: identity.FormatRow, geometry: identity.SiteGeometry, cut: tiles.TileCut, stream_id: str,
                gt_cert: data.Certificate) -> str:
    """scan, then retry150 on a failed scan (the retry row's stage): certified / retry_certified / failed /
    below_floor, or WRONG where a certificate's user bits differ from the GT's."""
    res = tiles.attempt_tile(row, geometry, (cut,), stream_id, tiles.STAGE_SCAN)
    tag = "certified"
    if res.fact.outcome == tiles.OUTCOME_FAILED:
        res = tiles.attempt_tile(row, geometry, (cut,), stream_id, tiles.STAGE_RETRY150)
        tag = "retry_certified"
    if res.certificate is None:
        return "below_floor" if res.fact.outcome == tiles.OUTCOME_BELOW_FLOOR else "failed"
    return tag if np.array_equal(res.certificate.user_bits, gt_cert.user_bits) else "WRONG"


def read_cut(row: identity.FormatRow, cut: tiles.TileCut, states: np.ndarray, x_mm_of_col: np.ndarray) -> Rec:
    ys, xs = cut_cells(cut)
    return read_cells(row, ys, xs, cut.values, states, x_mm_of_col)


def read_row(row: identity.FormatRow, geometry: identity.SiteGeometry, crow: data.ColorEvidenceRow,
             states: np.ndarray, x_mm_of_col: np.ndarray) -> Rec:
    """read_cells over one evidence row's cargo cells (a single-window region: no owner rule to apply)."""
    cells = np.asarray(crow.page_cells_yx, np.int64)
    keep = color_sites.cargo_row_indices(geometry, cells)
    return read_cells(row, cells[keep, 0], cells[keep, 1], np.asarray(crow.values)[keep], states, x_mm_of_col)


# ---------------------------------------------------------------- tables

def concat(reads: list[Rec]) -> Rec:
    return {k: np.concatenate([r[k] for r in reads]) for k in reads[0]} if reads else {}


def pct(n: int, d: int) -> float | None:
    return None if d == 0 else 100.0 * n / d


def zone_masks(cells: Rec) -> dict[str, np.ndarray]:
    return {"left": cells["left"], "right": ~cells["left"], "all": np.ones(len(cells["left"]), bool)}


def sign_table(cells: Rec) -> Rec:
    """Per zone x true state (and all): n, hi / lo sign-wrong %, hi / lo exact-zero %, state-argmax-wrong %."""
    out: Rec = {}
    for zone, zm in zone_masks(cells).items():
        out[zone] = {}
        for name, sm in [(n, cells["col"] == s) for s, n in enumerate(STATE_NAMES)] + [("all", np.ones_like(zm))]:
            m = zm & sm
            n = int(m.sum())
            out[zone][name] = {"n": n, **{f"{k}_pct": pct(int(cells[k][m].sum()), n) for k in
                                          ("hi_wrong", "lo_wrong", "hi_zero", "lo_zero", "argmax_wrong")}}
    return out


def sign_changes(a: Rec, b: Rec) -> Rec | str:
    """Per zone x true state: the cells whose hi / lo LLR sign (or zero) differs between two runs over the same
    cells in the same order (refused when the cells are not aligned)."""
    if not a or not b or not (np.array_equal(a["y"], b["y"]) and np.array_equal(a["x"], b["x"])):
        return "unaligned"
    out: Rec = {}
    for zone, zm in zone_masks(a).items():
        out[zone] = {}
        for name, sm in [(n, a["col"] == s) for s, n in enumerate(STATE_NAMES)] + [("all", np.ones_like(zm))]:
            m = zm & sm
            out[zone][name] = {"n": int(m.sum()), **{
                f"{s}_changed": int(((a[f"{s}_positive"] != b[f"{s}_positive"]) | (a[f"{s}_zero"] != b[f"{s}_zero"]))
                                    [m].sum()) for s in ("hi", "lo")}}
    return out


def squeeze(row: identity.FormatRow, cells: Rec) -> Rec:
    """Where the per-cell divisor's flips come from, read off the lifted run's (pre-divisor) scores.  A cell's
    scores divided by d keep their argmax, but as d grows the demap's sign tends to the LINEAR form's
    (hi: sC + sM - sY, lo: sC + sY - sM; the log-sum-exp's first order at 0) — the sim's 6.6e8-over-3e3 regime.
    Per true state: the sign-wrong % of that infinite-squeeze limit (what the bound would do with an unbounded
    divisor), the share of cells where it disagrees with the unbounded sign, and percentiles of
    max |s| / |true margin|, the factor the bound would need over 20 / ln 2 to reach a sign."""
    v = cells["values"]
    col = cells["col"].astype(np.int64)
    labels = color_model.CMY_COLUMN_LABEL_BITS[col]
    lin = {"hi": v[:, 0] + v[:, 1] - v[:, 2], "lo": v[:, 0] + v[:, 2] - v[:, 1]}
    full = np.column_stack([np.zeros(len(v)), v])
    margin = np.abs(np.where(col == 0, -v.max(1), full[np.arange(len(v)), col]))
    ratio = np.abs(v).max(1) / np.maximum(margin, 1e-12)
    out: Rec = {}
    for st, name in enumerate(STATE_NAMES):
        m = col == st
        n = int(m.sum())
        out[name] = {"n": n, **{f"{s}_limit_wrong_pct": pct(int(((lin[s] > 0) != labels[:, i])[m].sum()), n)
                                for i, s in enumerate(("hi", "lo"))},
                     **{f"{s}_limit_disagrees_pct": pct(int(((lin[s] > 0) != cells[f"{s}_positive"])[m].sum()), n)
                        for s in ("hi", "lo")},
                     "max_over_margin": {p: float(np.percentile(ratio[m], p)) for p in PCTS}}
    return out


def magnitudes(cells: Rec, bound: float = 20.0) -> Rec:
    """Per true state: percentiles of max |score| per cell, of the two minor |scores|, of the true state's
    W-relative margin (W: minus the best other score) and of the divisor the bound applies, plus the share of
    cells the bound divides — read off one run's emitted scores (the lifted run's are the pre-divisor ones)."""
    v = cells["values"]
    a = np.abs(v)
    mx = a.max(1)
    minor = np.sort(a, 1)[:, :2].ravel()
    full = np.column_stack([np.zeros(len(v)), v])
    margin = np.where(cells["col"] == 0, -v.max(1), full[np.arange(len(v)), cells["col"]])
    div = np.maximum(1.0, mx / bound)
    out: Rec = {}
    for name, m in [(n, cells["col"] == s) for s, n in enumerate(STATE_NAMES)] + [("all", np.ones(len(v), bool))]:
        mm = np.repeat(m, 2)
        out[name] = {"n": int(m.sum()),
                     "max_abs": {p: float(np.percentile(mx[m], p)) for p in PCTS},
                     "minor_abs": {p: float(np.percentile(minor[mm], p)) for p in PCTS},
                     "true_margin": {p: float(np.percentile(margin[m], 100 - p)) for p in PCTS},
                     "divisor_at_20": {p: float(np.percentile(div[m], p)) for p in PCTS},
                     "divided_pct": pct(int((div[m] > 1.0).sum()), int(m.sum()))}
    return out


def ldpc_table(outcomes: list[Rec]) -> Rec:
    """Per zone and stream: tiles, and the count of each attempt outcome (plus both streams certified)."""
    out: Rec = {}
    for zone in ("left", "right", "all"):
        sel = [o for o in outcomes if zone == "all" or o["zone"] == zone]
        z: Rec = {"tiles": len(sel)}
        for s in ("hi", "lo"):
            z[s] = {tag: sum(o[s] == tag for o in sel) for tag in
                    ("certified", "retry_certified", "failed", "below_floor", "WRONG")}
        z["both_certified"] = sum(o["hi"].endswith("certified") and o["lo"].endswith("certified") for o in sel)
        out[zone] = z
    return out


def lane_meta(rec: Rec) -> Rec:
    return {k: rec[k] for k in ("reason", "adopted", "corrected_arm", "context_head", "erased_streams",
                                "clipped_label_streams", "heldout_loss", "thread_seconds")}


# ---------------------------------------------------------------- stage 2: the measurement

def tiles_inside(row: identity.FormatRow, window: color_region.RegionWindow) -> list[tuple[int, int]]:
    """Tiles a window covers entirely (its extent in page cells)."""
    y0, x0, y1, x1 = window.window_id[3]
    return [(ty, tx) for ty in range(-(-y0 // TILE), y1 // TILE) for tx in range(-(-x0 // TILE), x1 // TILE)
            if ty < row.tiles_yx[0] and tx < row.tiles_yx[1]]


#: The regimes: (name, which windows form a region, fold of GT certificates, the offsets the corrected arm gets).
#: "truth": every plane at its own truth point per cell (C's residual from the window affine included); "rel":
#: C at the window pose, M and Y at pose + (plane - C) — the charter's arm, a converged field's read; "pose": no
#: offsets, so no corrected arm and all three planes at C's window pose — the colour job before the field exists.
REGIMES: tuple[tuple[str, str, int | None, str], ...] = (
    ("cold", "page", None, "truth"), ("refit", "page", 0, "truth"), ("first_fire", "window", None, "truth"),
    ("cold_rel", "page", None, "rel"), ("refit_rel", "page", 0, "rel"), ("first_fire_rel", "window", None, "rel"),
    ("cold_pose", "page", None, "pose"), ("first_fire_pose", "window", None, "pose"))


def measure_level(row: identity.FormatRow, geometry: identity.SiteGeometry, level: data.Level, img: np.ndarray,
                  truth: np.ndarray, states: np.ndarray, certs: dict, x_mm_of_col: np.ndarray, px_per_dot: float,
                  workers: int, tile_rows: list[list[Any]]) -> Rec:
    t0 = time.time()
    cell_dots = color_sites.cell_dots_of(row)
    planes = level_planes(img, level)
    windows, wstats = level_windows(row, level, truth, px_per_dot)
    by_ord = {w.patch_ordinal: w for w in windows}
    arms = {"truth": truth_offsets_of(truth, level.scale, windows, cell_dots),
            "rel": relative_offsets_of(truth, level.scale, windows, cell_dots), "pose": None}
    folds = [{k: v for k, v in certs.items() if (k[1] + k[2]) % 2 == f} for f in (0, 1)]

    def zone(col: float) -> str:
        return "left" if x_mm_of_col[min(int(col), len(x_mm_of_col) - 1)] < LEFT_ZONE_MM else "right"
    tile_zone = {(ty, tx): zone(TILE * tx + TILE / 2) for ty in range(row.tiles_yx[0]) for tx in range(row.tiles_yx[1])}
    all_tiles = sorted(tile_zone)
    print(f"level {level.index} ppc {level.ppc}: {len(windows)} windows, C residual inside a window median "
          f"{wstats['c_residual_rms_dots_median']:.3f} dots ({time.time() - t0:.0f} s)", flush=True)

    def lane(ws: tuple[color_region.RegionWindow, ...], c: dict, arm: str) -> Callable[[], Rec]:
        return lambda: run_lane(row, geometry, ws, planes, c, level.index, arms[arm])

    def regime_jobs(scope: str, fold: int | None, arm: str) -> list[tuple[str, Callable[[], Rec]]]:
        if scope == "window":
            return [(f"w{w.patch_ordinal}", lane((w,), {}, arm)) for w in windows]
        if fold is None:
            return [("page", lane(windows, {}, arm))]
        return [(f"fold{f}", lane(windows, folds[f], arm)) for f in (0, 1)]

    def regime_cuts(scope: str, fold: int | None, recs: list[Rec]) -> list[tuple[Any, tuple[int, int], tiles.TileCut]]:
        if scope == "window":
            items = []
            for w, rec in zip(windows, recs):
                got = assemble_cuts(row, geometry, rec["evidence"], by_ord, level.index, tiles_inside(row, w)) \
                    if rec["evidence"] else {}
                items += [(w.patch_ordinal, k, c) for k, c in got.items() if len(c.observed_flat) == row.payload_cells]
            return items
        if fold is None:
            return [(None, k, c) for k, c in assemble_cuts(row, geometry, recs[0]["evidence"], by_ord, level.index,
                                                           all_tiles).items()]
        items = []
        for f, rec in enumerate(recs):     # fold f certifies the tiles of parity f and reads the other parity
            items += [(None, k, c) for k, c in assemble_cuts(row, geometry, rec["evidence"], by_ord, level.index,
                                                             [k for k in all_tiles if sum(k) % 2 != f]).items()]
        return items

    def attempts(regime: str, bname: str, items: list[tuple[Any, tuple[int, int], tiles.TileCut]]) -> list[Rec]:
        def one(item: tuple[Any, tuple[int, int], tiles.TileCut]) -> Rec:
            tag, (ty, tx), cut = item
            r = read_cut(row, cut, states, x_mm_of_col)
            o = {"key": (ty, tx), "zone": tile_zone[(ty, tx)], "window": tag,
                 **{s: attempt_cut(row, geometry, cut, s, certs[(0, ty, tx, s)]) for s in ("hi", "lo")},
                 "n": len(r["col"]), "hi_wrong": int(r["hi_wrong"].sum()), "lo_wrong": int(r["lo_wrong"].sum())}
            tile_rows.append([level.index, regime, bname, tag, ty, tx, o["zone"], o["n"], o["hi_wrong"],
                              o["lo_wrong"], o["hi"], o["lo"]])
            return o
        with ThreadPoolExecutor(workers) as ex:
            return list(ex.map(one, items))

    out: Rec = {"ppc": str(level.ppc), "scale": str(level.scale), "windows": wstats, "regimes": {}}
    kept: dict[str, dict[str, Rec]] = {}
    means: dict[str, dict[str, list[Any]]] = {}
    for bname, bound in BOUNDS.items():
        t1 = time.time()
        named = [(name, scope, fold, tag, job) for name, scope, fold, arm in REGIMES
                 for tag, job in regime_jobs(scope, fold, arm)]
        recs = with_bound(bound, [job for *_, job in named], workers)
        print(f"  bound {bname}: lanes done ({time.time() - t1:.0f} s, peak RSS {peak_rss_gb():.1f} GB)", flush=True)
        t2 = time.time()
        for name, scope, fold, _arm in REGIMES:
            lanes = [rec for (n, *_), rec in zip(named, recs) if n == name]
            items = regime_cuts(scope, fold, lanes)
            if scope == "window":
                cells = concat([read_row(row, geometry, rec["evidence"][0], states, x_mm_of_col)
                                for rec in lanes if rec["evidence"]])
            else:
                cells = concat([read_cut(row, c, states, x_mm_of_col) for *_, c in items])
            kept.setdefault(bname, {})[name] = cells
            means.setdefault(name, {})[bname] = [x["qda_means"] for x in lanes]
            entry: Rec = {"cells": len(cells.get("col", ())), "signs": sign_table(cells) if cells else None,
                          "magnitudes": magnitudes(cells) if cells else None,
                          "ldpc": ldpc_table(attempts(name, bname, items))}
            if scope == "window":
                fmeta = [lane_meta(x) | {"window": w.window_id[3], "zone": zone((w.window_id[3][1]
                                                                                 + w.window_id[3][3]) / 2)}
                         for w, x in zip(windows, lanes)]
                entry["lanes"] = None
                entry["windows"] = {
                    "refused": sum(not m["adopted"] for m in fmeta),
                    "corrected_arm": sum(bool(m["corrected_arm"]) for m in fmeta),
                    "context_head": sum(bool(m["context_head"]) for m in fmeta),
                    "erased": {k: sum(str(m["erased_streams"]) == k for m in fmeta)
                               for k in sorted({str(m["erased_streams"]) for m in fmeta})},
                    "erased_windows": [m for m in fmeta if m["erased_streams"]],
                    "refusals": [m for m in fmeta if not m["adopted"]]}
            else:
                entry["lanes"] = [lane_meta(x) for x in lanes]
            out["regimes"].setdefault(name, {})[bname] = entry
        print(f"  bound {bname}: reads + attempts done ({time.time() - t2:.0f} s)", flush=True)
    for name, *_ in REGIMES:
        reg = out["regimes"][name]
        reg["sign_changes_20_vs_lifted"] = sign_changes(kept["20"][name], kept["lifted"][name])
        reg["squeeze"] = squeeze(row, kept["lifted"][name]) if kept["lifted"][name] else None
        a, b = (means[name][k] for k in BOUNDS)
        reg["fit_identical_across_bounds"] = all(
            x is not None and y is not None and np.array_equal(x, y) for x, y in zip(a, b))
    out["seconds"] = time.time() - t0
    out["peak_rss_gb"] = peak_rss_gb()
    return out


def stage_measure(art: Path, level_indices: list[int] | None, workers: int) -> Rec:
    from measure.e041_probe_readout import read_rgb
    t0 = time.time()
    if color_region_head.CMY7_RELATIVE_SCORE_BOUND != 20.0:
        raise SystemExit(f"production bound is {color_region_head.CMY7_RELATIVE_SCORE_BOUND}, not 20")
    poses = json.loads((art / "poses.json").read_text())
    row = identity.resolve_format_ref(FORMAT_REF)
    geometry = identity.build_site_geometry(row)
    cell_dots = color_sites.cell_dots_of(row)
    man = json.loads(MANIFEST.read_text())
    if tuple(man["page_cells_yx"]) != row.cells_yx or man["format_id"] != FORMAT_REF:
        raise SystemExit("manifest vs the receiver's row: contract fork")
    origin = tuple(int(v) for v in man["origin_dots_yx"])
    states = gt_states(row, cell_dots)
    certs = gt_certificates(row, geometry, states, workers)
    print(f"GT: {len(certs)} certificates minted from the GT, every tile projects to the GT ({time.time() - t0:.0f} s)",
          flush=True)
    rows, cols = row.cells_yx
    truth = truth_points(poses, origin, cell_dots, rows, cols)
    x_mm_of_col = (origin[1] + cell_dots * np.arange(cols) + cell_dots / 2.0) * DOT_MM
    img = read_rgb(SCAN)
    print(f"scan {img.shape} {img.dtype} ({time.time() - t0:.0f} s, peak RSS {peak_rss_gb():.1f} GB)", flush=True)
    levels = build_levels(SCAN_DPI, row.pitch_in, img.shape[:2])
    tile_rows: list[list[Any]] = []
    doc: Rec = {"format": FORMAT_REF, "scan": str(SCAN), "gt": str(GT), "capture_levels_ppc": [str(lv.ppc) for lv in levels],
                "bounds": {k: str(v) for k, v in BOUNDS.items()}, "left_zone_mm": LEFT_ZONE_MM,
                "poses": {k: poses[k] for k in ("orientation", "nonaffine", "offsets_vs_C_dots")}, "levels": {}}
    for li in (level_indices if level_indices is not None else [lv.index for lv in levels]):
        doc["levels"][str(li)] = measure_level(row, geometry, levels[li], img, truth, states, certs, x_mm_of_col,
                                               float(poses["sub"]), workers, tile_rows)
        (art / "scorelane.json").write_text(json.dumps(jsonable(doc), indent=1))
    doc["seconds"] = time.time() - t0
    doc["peak_rss_gb"] = peak_rss_gb()
    (art / "scorelane.json").write_text(json.dumps(jsonable(doc), indent=1))
    with open(art / "tiles.csv", "w") as fh:
        fh.write("level,regime,bound,window,ty,tx,zone,cells,hi_wrong,lo_wrong,hi,lo\n")
        for r in sorted(tile_rows, key=lambda r: tuple(str(v) for v in r[:6])):
            fh.write(",".join("" if v is None else str(v) for v in r) + "\n")
    print(f"wrote {art / 'scorelane.json'} and tiles.csv ({doc['seconds']:.0f} s, peak RSS {doc['peak_rss_gb']:.1f} GB)")
    return doc


# ---------------------------------------------------------------- stage 3: the report

def fmt(v: Any, d: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{d}f}" if abs(v) < 1e4 else f"{v:.2e}"
    return str(v)


def md_table(head: list[str], rows: list[list[Any]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(fmt(x) for x in r) + " |" for r in rows])


def compact(doc: Rec, levels: list[int] | None = None) -> str:
    """The RESULTS extract: per level and regime (1) the cells whose label sign the bound changes, (2) sign-wrong
    and argmax-wrong % per zone and state at 20 (lifted beside it), (3) the score scale against the bound — these
    three for `levels` (default all) — then for every level (4) the LDPC outcome over the whole page and (5) the
    heads and the erasure verdicts."""
    every = list(doc["levels"].items())
    lv_items = [(k, v) for k, v in every if levels is None or int(k) in levels]
    out = [f"levels (ppc) {[lv['ppc'] for _, lv in lv_items]}; bounds 20 vs lifted (inf); zones left < "
           f"{doc['left_zone_mm']:g} mm / right; wall {fmt(doc.get('seconds'), 0)} s, peak RSS "
           f"{fmt(doc.get('peak_rss_gb'), 1)} GB\n"]
    rows = []
    for _, lv in lv_items:
        for name, reg in lv["regimes"].items():
            ch = reg.get("sign_changes_20_vs_lifted")
            for zone in ZONES:
                rows.append([lv["ppc"], name, zone, reg["20"]["signs"][zone]["all"]["n"]]
                            + [f"{ch[zone][st]['hi_changed']} / {ch[zone][st]['lo_changed']}"
                               if isinstance(ch, dict) else str(ch) for st in STATE_NAMES])
    out += ["(1) cells whose hi / lo LLR sign differs between the bound at 20 and lifted:\n",
            md_table(["ppc", "regime", "zone", "cells", "W", "C", "M", "Y"], rows), ""]
    rows = []
    for _, lv in lv_items:
        for name, reg in lv["regimes"].items():
            for zone in ZONES:
                a20, al = reg["20"]["signs"][zone], reg["lifted"]["signs"][zone]
                rows.append([lv["ppc"], name, zone] + [
                    f"{fmt(a20[st]['hi_wrong_pct'])} / {fmt(a20[st]['lo_wrong_pct'])} / {fmt(a20[st]['argmax_wrong_pct'])}"
                    + ("" if all(abs((a20[st][k] or 0) - (al[st][k] or 0)) < 0.005 for k in
                                 ("hi_wrong_pct", "lo_wrong_pct", "argmax_wrong_pct"))
                       else f" (lifted {fmt(al[st]['hi_wrong_pct'])} / {fmt(al[st]['lo_wrong_pct'])})")
                    for st in STATE_NAMES] + [f"{fmt(a20['all']['hi_zero_pct'])} / {fmt(a20['all']['lo_zero_pct'])}"])
    out += ["(2) % of cells, hi sign wrong / lo sign wrong / state argmax wrong, at 20 (lifted shown where any "
            "differs by >= 0.005 pp); last column exact-zero LLRs hi / lo (an erased stream):\n",
            md_table(["ppc", "regime", "zone", "W", "C", "M", "Y", "zero hi / lo"], rows), ""]
    rows = []
    for _, lv in lv_items:
        for name, reg in lv["regimes"].items():
            m, m20, sq = reg["lifted"]["magnitudes"], reg["20"]["magnitudes"], reg.get("squeeze") or {}
            for st in STATE_NAMES:
                rows.append([lv["ppc"], name, st, m[st]["max_abs"]["50"], m[st]["max_abs"]["99"],
                             m[st]["minor_abs"]["50"], m[st]["true_margin"]["99"], m[st]["divisor_at_20"]["50"],
                             m[st]["divisor_at_20"]["99"], m20[st]["true_margin"]["99"],
                             sq[st]["max_over_margin"]["99"] if st in sq else None,
                             f"{fmt(sq[st]['hi_limit_wrong_pct'])} / {fmt(sq[st]['lo_limit_wrong_pct'])}"
                             if st in sq else None])
    out += ["(3) the scores against the bound (lifted run = pre-divisor): max |s| p50 / p99, minor |s| p50, the true "
            "state's W-relative margin p1 (W: minus the best other), the divisor at 20 p50 / p99, the margin the "
            "bound-20 run EMITS p1, max |s| / |margin| p99, and the infinite-squeeze limit's sign-wrong % hi / lo "
            "(what an unbounded divisor would do; the sim's regime):\n",
            md_table(["ppc", "regime", "state", "max p50", "max p99", "minor p50", "margin p1", "div p50", "div p99",
                      "emitted margin p1", "max/margin p99", "limit wrong hi / lo"], rows), ""]
    rows = []
    for _, lv in every:
        for name, reg in lv["regimes"].items():
            z = {bname: reg[bname]["ldpc"]["all"] for bname in BOUNDS}
            rows.append([lv["ppc"], name, z["20"]["tiles"]] + [
                f"{z[b][s]['certified'] + z[b][s]['retry_certified']} / {z[b][s]['failed']} / {z[b][s]['below_floor']}"
                f" / {z[b][s]['WRONG']}" for b in BOUNDS for s in ("hi", "lo")]
                + [f"{z['20']['both_certified']} / {z['lifted']['both_certified']}"])
    out += ["(4) the whole page's tile attempts through tiles.attempt_tile (scan, retry150 on a failed scan), per "
            "stream certified / failed / below floor / WRONG, at 20 and lifted; tiles with both streams certified "
            "(20 / lifted); the zone split is in --full:\n",
            md_table(["ppc", "regime", "tiles", "hi @20", "lo @20", "hi lifted", "lo lifted", "both 20 / lifted"],
                     rows), ""]
    rows = []
    for _, lv in every:
        for name, reg in lv["regimes"].items():
            for bname in BOUNDS:
                e = reg[bname]
                if e.get("lanes"):
                    rows.append([lv["ppc"], name, bname, "; ".join(
                        f"{x['reason']}, corrected {x['corrected_arm']}, ctx {x['context_head']}, erased "
                        f"{x['erased_streams']}, held-out {fmt(x['heldout_loss'], 4)}" for x in e["lanes"])])
                else:
                    w = e["windows"]
                    at = [(m["window"], m["erased_streams"]) for m in w["erased_windows"]]
                    rows.append([lv["ppc"], name, bname,
                                 f"windows: refused {w['refused']}, corrected {w['corrected_arm']}, ctx "
                                 f"{w['context_head']}, erased {w['erased']}" + (f" at {at}" if at else "")])
    out += ["(5) the lanes' heads (page regimes: one lane, refit: its two folds) and, per first-fire window, the "
            "erasure trigger's verdict (streams 0 = hi, 1 = lo):\n",
            md_table(["ppc", "regime", "bound", "heads"], rows)]
    return "\n".join(out)


def report(doc: Rec) -> str:
    """The RESULTS tables: per level the label-sign table (zone x state, both bounds, each regime), the score
    magnitudes of the lifted run (the pre-divisor scores), the LDPC outcomes and what each lane's head did."""
    out = [f"capture levels (ppc): {doc['capture_levels_ppc']}; bounds {doc['bounds']}; left zone < "
           f"{doc['left_zone_mm']} mm; wall {fmt(doc.get('seconds'), 0)} s, peak RSS {fmt(doc.get('peak_rss_gb'), 1)} GB"]
    for li, lv in doc["levels"].items():
        out.append(f"\n### level {li}: ppc {lv['ppc']} (scale {lv['scale']}), {lv['windows']['windows']} windows, "
                   f"C residual inside a window median {fmt(lv['windows']['c_residual_rms_dots_median'], 3)} / max "
                   f"{fmt(lv['windows']['c_residual_rms_dots_max'], 3)} dots; {fmt(lv['seconds'], 0)} s")
        for regime, by_bound in lv["regimes"].items():
            b20, bl = by_bound["20"], by_bound["lifted"]
            if b20["signs"] is None:
                continue
            rows = []
            for zone in ZONES:
                for st in STATE_NAMES + ("all",):
                    a, b = b20["signs"][zone][st], bl["signs"][zone][st]
                    rows.append([zone, st, a["n"], a["hi_wrong_pct"], a["lo_wrong_pct"], b["hi_wrong_pct"],
                                 b["lo_wrong_pct"], a["hi_zero_pct"], a["lo_zero_pct"], a["argmax_wrong_pct"],
                                 b["argmax_wrong_pct"]])
            ident = by_bound.get("fit_identical_across_bounds")
            ch = by_bound.get("sign_changes_20_vs_lifted")
            if isinstance(ch, dict):
                rows_ch = [[zone, st, ch[zone][st]["n"], ch[zone][st]["hi_changed"], ch[zone][st]["lo_changed"]]
                           for zone in ZONES for st in STATE_NAMES]
                out.append(f"\n{regime}: cells whose label sign differs between the bound at 20 and lifted:\n")
                out.append(md_table(["zone", "state", "n", "hi changed", "lo changed"], rows_ch))
            elif ch is not None:
                out.append(f"\n{regime}: sign changes 20 vs lifted: {ch}")
            sq = by_bound.get("squeeze")
            if sq:
                out.append(f"\n{regime} squeeze (lifted scores): the infinite-squeeze limit's sign-wrong % and its "
                           "disagreement with the unbounded sign (hi / lo), max|s| / |true margin|:\n")
                out.append(md_table(["state", "n", "limit wrong hi / lo", "limit disagrees hi / lo",
                                     "max/margin p50", "p90", "p99"], [
                    [st, sq[st]["n"], f"{fmt(sq[st]['hi_limit_wrong_pct'])} / {fmt(sq[st]['lo_limit_wrong_pct'])}",
                     f"{fmt(sq[st]['hi_limit_disagrees_pct'])} / {fmt(sq[st]['lo_limit_disagrees_pct'])}",
                     *(sq[st]["max_over_margin"][str(p)] for p in PCTS)] for st in STATE_NAMES]))
            out.append(f"\n{regime} (cells {b20['cells']}; QDA and context head identical across bounds: {fmt(ident)}), % of cells:\n")
            out.append(md_table(["zone", "state", "n", "hi wrong @20", "lo wrong @20", "hi wrong lifted",
                                 "lo wrong lifted", "hi zero @20", "lo zero @20", "argmax wrong @20",
                                 "argmax wrong lifted"], rows))
            mrows = []
            for st in STATE_NAMES + ("all",):
                m = bl["magnitudes"][st]
                mrows.append([st, m["n"], *(m["max_abs"][str(p)] if str(p) in m["max_abs"] else m["max_abs"][p]
                                            for p in PCTS),
                              *(m["minor_abs"][str(p)] if str(p) in m["minor_abs"] else m["minor_abs"][p] for p in PCTS),
                              *(m["true_margin"][str(p)] if str(p) in m["true_margin"] else m["true_margin"][p]
                                for p in PCTS),
                              *(m["divisor_at_20"][str(p)] if str(p) in m["divisor_at_20"] else m["divisor_at_20"][p]
                                for p in PCTS), m["divided_pct"],
                              *(b20["magnitudes"][st]["true_margin"][str(p)] for p in PCTS)])
            out.append(f"\n{regime}, lifted run's emitted (= pre-divisor) scores; margin = the true state's W-relative "
                       "score (W: minus the best other), lower percentiles:\n")
            out.append(md_table(["state", "n", "max|s| p50", "p90", "p99", "minor|s| p50", "p90", "p99", "margin p50",
                                 "p10", "p1", "divisor@20 p50", "p90", "p99", "divided %", "emitted margin @20 p50",
                                 "p10", "p1"], mrows))
            lrows = []
            for bname, rec in (("20", b20), ("lifted", bl)):
                for zone in ("left", "right", "all"):
                    z = rec["ldpc"][zone]
                    lrows.append([bname, zone, z["tiles"],
                                  *(f"{z[s]['certified']}+{z[s]['retry_certified']} / {z[s]['failed']} / "
                                    f"{z[s]['below_floor']} / {z[s]['WRONG']}" for s in ("hi", "lo")),
                                  z["both_certified"]])
            out.append(f"\n{regime} LDPC (scan+retry150 certified / failed / below floor / WRONG):\n")
            out.append(md_table(["bound", "zone", "tiles", "hi", "lo", "both certified"], lrows))
            if b20["lanes"] is not None:
                out.append("\nlanes: " + "; ".join(
                    f"{bname}: " + ", ".join(f"reason {x['reason']}, corrected arm {x['corrected_arm']}, context head "
                                             f"{x['context_head']}, erased {x['erased_streams']}, clipped "
                                             f"{x['clipped_label_streams']}, held-out loss {fmt(x['heldout_loss'], 4)}"
                                             for x in rec["lanes"]) for bname, rec in (("20", b20), ("lifted", bl))))
            else:
                for bname, rec in (("20", b20), ("lifted", bl)):
                    w = rec["windows"]
                    out.append(f"\nfirst-fire windows @{bname}: refused {w['refused']}, corrected arm "
                               f"{w['corrected_arm']}, context head {w['context_head']}, erased {w['erased']}"
                               + (f"; erased at {[(m['window'], m['zone'], m['erased_streams']) for m in w['erased_windows']]}"
                                  if w["erased_windows"] else ""))
    return "\n".join(out)


# ---------------------------------------------------------------- driver

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=("poses", "measure", "report"))
    ap.add_argument("--art", type=Path, default=ART)
    ap.add_argument("--workers", type=int, default=4, help="threads (window reads, lanes, LDPC attempts)")
    ap.add_argument("--levels", type=int, nargs="+", default=None,
                    help="measure: receiver level indices; report: levels of tables (1)-(3) (default: all)")
    ap.add_argument("--full", action="store_true", help="report: every table per level (default: the extract)")
    a = ap.parse_args()
    a.art.mkdir(parents=True, exist_ok=True)
    if a.stage == "poses":
        stage_poses(a.art, a.workers)
    elif a.stage == "measure":
        stage_measure(a.art, a.levels, a.workers)
    else:
        doc = json.loads((a.art / "scorelane.json").read_text())
        print(report(doc) if a.full else compact(doc, a.levels))


if __name__ == "__main__":
    main()

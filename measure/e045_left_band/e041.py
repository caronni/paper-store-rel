"""e045 — the left band on the e041 sheets of 2026-10-05/06 (HP M281, fresh toner, Canon 2400 RGB): per-plane window
and sub-window poses on every band kind, the per-slice table on the four-state single-toner bands, the K band U14.

`sheet`, per sheet (S14, S15, S17: the generator's manifest and <tag>-bands.npz beside it; states_<band> = index into
the band's alphabet, planes_<band> = (4, H, W) dot planes C, M, Y, K):
  page   the five fiducials (e041_probe_readout.fit_page on e041_scale_readout.page_frame; residual <= 0.3 mm, scale
         within 1 %) and the page white from the margins (e041_probe_readout.page_white, every band and fiducial
         masked) — no readout summary;
  cmy4   (alphabets cmy4-*: states W, C, M, Y = classes 0..3, the npz planes equal to bands.dot_planes of the
         classes, checked): sheet3's path — the read / win / finex / fine / diff / common / aff arms (cells.py), the
         per-slice rows (sheet3.band_rows: errors, d', levels, neighbour model, offsets, screen families; bare paper
         is NOT measured here, NaN) and the 1 mm profile (sheet3.profile_rows);
  other  (cmy8, cmyk5, dot-mixed): the per-plane poses of every window, twice (the second pass at cells.prior_offsets'
         prior), and of every sub-window, from the band's OWN dot planes (read_windows_planes / refine_subwindows_planes:
         bands.read_window and cells.refine_subwindows with the planes in place of the class grid); peaks and flags are
         written — a screened region's planes are expected weak;
  K      (U14, wk-mask): the K plane's window and sub-window poses as above; cells read at K's pose in all three
         channels (the e041 convention: e041_mixture_readout.sample_per_plane puts R, G, B at K's pose for a K-only
         alphabet) and scored in max(R, G, B) (plane_values); per WIDTH_MM slice at read / win / finex: the W-vs-K error
         of a genie nearest-mean table in RGB (band table, slice table), the best single threshold in max(R, G, B), d',
         the white and ink means and sds, at finex slices.neighbour_model in max(R, G, B) (w0_K / p0_K = white and ink
         with four white neighbours, Wspread_K = a W cell's darkening per K neighbour, W_NS_K / W_WE_K its N - S and
         W - E asymmetry), the K window and sub-window offsets.
  Windows are cells.py's 36 cells square (e041's readout: 31 at c3, 46 at c2; its error is leave-one-out per window).

`summarize`, over the per-sheet directories and the committed e041 extract (results/measurements.json):
  (a) per plane the sub-window y offset ("ok", all-cell fit) minus that plane's median over REF_MM on the same band and
      sub-window row, median per BIN_MM of page x, per sheet over the cmy4 bands, and over the other bands; a STEP at x
      = the median over STEP_SIDE_MM right of x minus the median over STEP_SIDE_MM left, |step| > STEP_MIN_DOTS, at its
      local extremum (+ = the plane lies further down the page right of x);
  (b) the band_screen profile (5 mm bins centred on multiples of 5 mm, max over R/G/B of the median known-lattice score)
      per band: SWITCH-ON = the first bin centre from the band's start whose 212 lpi score exceeds SCREEN_ON[212]
      (165 lpi: SCREEN_ON[165]), RESET = the first bin at or after RESET_FROM_MM back under it, RE-ON = the next bin
      above it; beside them the e041 readout's loo state error per window column (profile_col_state_err_loo);
  (c) zones LEFT [band start, 35) and MID [37, 107) mm per cmy4 band: cell-weighted errors and d' from slices.csv,
      sub-window M - C and Y - C dy medians from subwindows.csv;
      and, from this instrument, the median of the M and Y pose peaks per sub-window column (falls from ~0.7 to ~0.5
      where the band is screened) and where it crosses halfway between its 90th and 10th percentile;
  (d) U14 per slice (kslices.csv) with the K plane's steps;
  every step and crossing is given in page x and in platen x (the scan column at page y PAGE_MID_Y_MM over the fit's
  px per mm); the same steps on the x offsets (axis dx) mark the scanner's common-x jumps (045.4).

    PYTHONPATH=src:. env/bin/python -u -m measure.e045_left_band.e041 sheet \\
        --scan <S15.tiff> --manifest <S15/jobs/S15-ps-reset.manifest.json> --out <dir>/S15 [--bands R5,R8] [--workers 8]
    PYTHONPATH=src:. env/bin/python -m measure.e045_left_band.e041 summarize \\
        --dirs <dir>/S14 <dir>/S15 <dir>/S17 --extract experiments/041-m281-screen-routes/results/measurements.json \\
        --out <dir>
Outputs per sheet: windows.csv, subwindows.csv, slices.csv and profile_1mm.csv (cmy4), kslices.csv (K), summary.json;
summarize: plane_profile.csv, steps.csv, screen_events.csv, peak_profile.csv, zones.csv, report.txt.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from measure.cmy_probe.bands import WINDOW_CELLS, dot_planes, window_starts
from measure.e041_mixture_readout import best_threshold_err, plane_poses, plane_search_px, sample_per_plane
from measure.e041_probe_readout import Scan, fit_page, jsonable, page_white, sample_rect, sub_px_per_dot
from measure.e041_scale_readout import REG_MIN_PEAK, SEARCH_MM, band_arrays, page_frame, rect_dots, register, states_of
from measure.e045_left_band.cells import (HALF_ROWS, PLANES, SUB_CELLS, affine_field, check_reproduction, diff_field,
                                          fine_field, fit_plane_affines, margin_px, paint, paint_X, prior_offsets,
                                          read_windows, refine_subwindows, sample_field, window_centres_dots)
from measure.e045_left_band.sheet3 import band_rows, profile_rows, write_csv
from measure.e045_left_band.slices import neighbour_model, neighbour_states, predict, slice_edges
from measure.e045_left_band.spectra import slice_families

DOT_MM = 25.4 / 600.0
WIDTH_MM = 5.0
BIN_MM = 1.5
REF_MM = (40.0, 100.0)
STEP_SIDE_MM = 4.5
STEP_MIN_DOTS = 0.5
SCREEN_ON = {"212": 50.0, "165": 20.0}
RESET_FROM_MM = 95.0
LEFT_END_MM, MID_MM = 35.0, (37.0, 107.0)
PAGE_MID_Y_MM = 148.5
ALL_PLANES = ("C", "M", "Y", "K")
Rec = dict[str, Any]


def kind_of(b: Rec) -> str:
    a = str(b.get("alphabet"))
    if a.startswith("cmy4"):
        return "cmy4"
    if a == "wk-mask":
        return "K"
    return a


def read_window_planes(scan: Scan, A: np.ndarray, xd: int, yd: int, pl: np.ndarray, cd: int, white: np.ndarray,
                       sub: int) -> Rec:
    """bands.read_window on a window's own (4, n, n) dot planes: the OR-ed registration, per-plane poses, the cells."""
    n_dots = pl.shape[1]
    step = DOT_MM / sub
    s_px, p_px = int(round(SEARCH_MM / step)), plane_search_px(sub)
    m_px = s_px + p_px
    k = np.arange(n_dots * sub + 2 * m_px)
    rect = sample_rect(scan, A, xd * DOT_MM + (k - m_px) * step, yd * DOT_MM + (k - m_px) * step)
    ink = np.kron(pl.max(axis=0).astype(np.float32), np.ones((sub, sub), np.float32))
    oy, ox, peak, edge = register(rect, ink, s_px, p_px)
    reg_ok = bool(peak >= REG_MIN_PEAK)
    if not reg_ok:
        oy = ox = float(m_px)
    poses = plane_poses(rect, pl, oy, ox, white, p_px, sub)
    vals, _ = sample_per_plane(rect, poses, oy, ox, n_dots // cd, cd * sub)
    return {"X": vals, "poses": poses, "reg_ok": reg_ok, "reg_edge": bool(edge), "reg_peak": float(peak)}


def read_windows_planes(scan: Scan, A: np.ndarray, x0d: int, y0d: int, planes: np.ndarray, cd: int, white: np.ndarray,
                        sub: int, workers: int, prior: dict | None = None) -> list[Rec]:
    """cells.read_windows with the band's dot planes: per window r0, c0, X, per plane present d (dy, dx dots, prior
    included), flags, peaks, the OR-ed registration."""
    m = margin_px(sub)
    n = WINDOW_CELLS * cd
    rows, cols = planes.shape[1] // cd, planes.shape[2] // cd

    def one(key: tuple[int, int]) -> Rec:
        r0, c0 = key
        py, px = (prior or {}).get(key, (0.0, 0.0))
        Ak = A.copy()
        Ak[:, 2] += A[:, :2] @ np.array([px, py]) * DOT_MM
        try:
            w = read_window_planes(scan, Ak, x0d + c0 * cd, y0d + r0 * cd,
                                   planes[:, r0 * cd:r0 * cd + n, c0 * cd:c0 * cd + n], cd, white, sub)
        except ValueError as exc:
            return {"r0": r0, "c0": c0, "skipped": str(exc)}
        q = w["poses"]
        return {"r0": r0, "c0": c0, "X": w["X"], "d": {p: (py + (v["oy"] - m) / sub, px + (v["ox"] - m) / sub)
                                                        for p, v in q.items()},
                "flags": {p: v["flag"] for p, v in q.items()}, "peaks": {p: v["peak"] for p, v in q.items()},
                "reg_ok": w["reg_ok"], "reg_peak": w["reg_peak"], "reg_edge": w["reg_edge"]}
    keys = [(r, c) for r in window_starts(rows, WINDOW_CELLS) for c in window_starts(cols, WINDOW_CELLS)]
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, keys))


def refine_subwindows_planes(scan: Scan, A: np.ndarray, x0d: int, y0d: int, planes: np.ndarray, cd: int,
                             white: np.ndarray, sub: int, wins: list[Rec], workers: int) -> list[Rec]:
    """cells.refine_subwindows with the band's dot planes: per SUB_CELLS sub-window the per-plane poses on all of its
    cells (d, flags, peaks) and on each half's HALF_ROWS - 1 rows (d0/flags0, d1/flags1)."""
    m, step, pp = margin_px(sub), DOT_MM / sub, plane_search_px(sub)
    cp = cd * sub
    n_px = SUB_CELLS * cp
    nd = SUB_CELLS * cd

    def one(w: Rec) -> list[Rec]:
        if "skipped" in w or not w.get("d"):
            return []
        base = np.mean([w["d"][p] for p in w["d"]], axis=0)
        by, bx = int(round(base[0] * sub)), int(round(base[1] * sub))
        use = {}
        for half, (ra, rb) in (("0", (0, HALF_ROWS - 1)), ("1", (HALF_ROWS + 1, SUB_CELLS))):
            u = np.zeros((n_px + 2 * m,) * 2, bool)
            u[m + by + ra * cp:m + by + rb * cp, m + bx:m + bx + n_px] = True
            use[half] = u
        res = []
        k = np.arange(n_px + 2 * m)
        for a in range(0, WINDOW_CELLS, SUB_CELLS):
            for b in range(0, WINDOW_CELLS, SUB_CELLS):
                r0, c0 = w["r0"] + a, w["c0"] + b
                pl = planes[:, r0 * cd:r0 * cd + nd, c0 * cd:c0 * cd + nd]
                if pl.shape[1:] != (nd, nd):
                    continue
                rec: Rec = {"r0": r0, "c0": c0}
                try:
                    rect = sample_rect(scan, A, (x0d + c0 * cd) * DOT_MM + (k - m) * step,
                                       (y0d + r0 * cd) * DOT_MM + (k - m) * step)
                    for tag, u in (("", None), ("0", use["0"]), ("1", use["1"])):
                        q = plane_poses(rect, pl, m + base[0] * sub, m + base[1] * sub, white, pp, sub, u)
                        rec["d" + tag] = {p: ((v["oy"] - m) / sub, (v["ox"] - m) / sub) for p, v in q.items()}
                        rec["flags" + tag] = {p: v["flag"] for p, v in q.items()}
                        if not tag:
                            rec["peaks"] = {p: v["peak"] for p, v in q.items()}
                except ValueError:
                    continue
                res.append(rec)
        return res
    with ThreadPoolExecutor(workers) as ex:
        return [s for part in ex.map(one, wins) for s in part]


def as_cmy(recs: list[Rec], plane: str = "K") -> list[Rec]:
    """Records with one plane's d / flags (and half-fits) copied onto C, M and Y (cells.py's plane keys)."""
    out = []
    for r in recs:
        q = dict(r)
        for key in ("d", "flags", "peaks", "d0", "d1", "flags0", "flags1"):
            if key in r and plane in r[key]:
                q[key] = {p: r[key][plane] for p in PLANES}
        out.append(q)
    return out


def k_slice_rows(name: str, b: Rec, cls: np.ndarray, arms: dict[str, np.ndarray], wins: list[Rec], subs: list[Rec],
                 edges: np.ndarray) -> list[Rec]:
    """Per slice and arm: W-vs-K error (band / slice RGB table), best threshold, d' and levels in max(R, G, B); offsets."""
    cd, x0d, y0d = int(b["cell_dots"]), int(b["x_dots"]), int(b["y_dots"])
    col_x = (x0d + (np.arange(cls.shape[1]) + 0.5) * cd) * DOT_MM
    full = np.ones(cls.shape, bool)
    pred_band = {a: predict(X, cls, full) for a, X in arms.items()}
    nb = neighbour_states(cls)
    wx = np.array([window_centres_dots(w, x0d, y0d, cd)[0] * DOT_MM for w in wins])
    sx = np.array([(x0d + (s["c0"] + SUB_CELLS / 2) * cd) * DOT_MM for s in subs])
    rows = []
    for i, (a, c) in enumerate(zip(edges[:-1], edges[1:])):
        mask = np.broadcast_to((col_x >= a) & (col_x < c), cls.shape)
        if not mask.any():
            continue
        r: Rec = {"band": name, "slice": i, "x0_mm": float(a), "x1_mm": float(c), "n_cells": int(mask.sum())}
        for arm, X in arms.items():
            ok = mask & np.isfinite(X).all(-1)
            y = cls[ok]
            r[f"E_band_{arm}"] = 100.0 * float((pred_band[arm][ok] != y).mean())
            r[f"E_slice_{arm}"] = 100.0 * float((predict(X, cls, mask)[ok] != y).mean())
            v = X[ok].max(-1).astype(np.float64)
            wv, kv = v[y == 0], v[y == 1]
            r[f"best_{arm}"] = 100.0 * best_threshold_err(v, y == 1)
            r[f"dp_{arm}"] = float((wv.mean() - kv.mean()) / np.sqrt(0.5 * (wv.var() + kv.var())))
            for tag, u in (("W", wv), ("K", kv)):
                r[f"mu_{tag}_{arm}"], r[f"sd_{tag}_{arm}"] = float(u.mean()), float(u.std())
            if arm == "finex":
                nm = neighbour_model(np.repeat(X.max(-1, keepdims=True), 3, -1), cls, mask, nb).get("C")
                if nm:
                    r.update({"w0_K": nm["w0"], "p0_K": nm["p0"], "dp0_K": nm["dprime0"],
                              "Wspread_K": nm["W_fit"]["spread"]["C"], "W_NS_K": nm["W_fit"]["N_minus_S"]["C"],
                              "W_WE_K": nm["W_fit"]["W_minus_E"]["C"], "Pspread_K": nm["P_fit"]["spread"]["C"]})
        for tag, recs, xs in (("win", wins, wx), ("sub", subs, sx)):
            d = np.array([q["d"]["K"] for q, x in zip(recs, xs) if a <= x < c and q.get("flags", {}).get("K") == "ok"],
                         float).reshape(-1, 2)
            r[f"{tag}_K_dy"] = float(np.median(d[:, 0])) if len(d) else float("nan")
            r[f"{tag}_K_dx"] = float(np.median(d[:, 1])) if len(d) else float("nan")
            r[f"{tag}_K_n"] = len(d)
        rows.append(r)
    return rows


def window_rows(name: str, kind: str, b: Rec, wins: list[Rec], wins1: list[Rec]) -> list[Rec]:
    cd, x0d, y0d = int(b["cell_dots"]), int(b["x_dots"]), int(b["y_dots"])
    out = []
    for w, w1 in zip(wins, wins1):
        if "skipped" in w:
            continue
        cx, cy = window_centres_dots(w, x0d, y0d, cd)
        r: Rec = {"band": name, "kind": kind, "cell_dots": cd, "r0": w["r0"], "c0": w["c0"], "x_mm": cx * DOT_MM,
                  "y_mm": cy * DOT_MM, "reg_ok": w.get("reg_ok"), "reg_peak": w.get("reg_peak"),
                  "reg_ok_pass1": w1.get("reg_ok")}
        for p in ALL_PLANES:
            if p in w["d"]:
                r.update({f"{p}_dy": w["d"][p][0], f"{p}_dx": w["d"][p][1], f"{p}_flag": w["flags"][p],
                          f"{p}_peak": w["peaks"][p], f"{p}_flag_pass1": w1.get("flags", {}).get(p),
                          f"{p}_peak_pass1": w1.get("peaks", {}).get(p)})
        out.append(r)
    return out


def sub_rows(name: str, kind: str, b: Rec, subs: list[Rec], errs: dict[str, np.ndarray], cls: np.ndarray | None) -> list[Rec]:
    cd, x0d, y0d = int(b["cell_dots"]), int(b["x_dots"]), int(b["y_dots"])
    out = []
    for s in subs:
        r: Rec = {"band": name, "kind": kind, "cell_dots": cd, "r0": s["r0"], "c0": s["c0"],
                  "x_mm": (x0d + (s["c0"] + SUB_CELLS / 2) * cd) * DOT_MM,
                  "y_mm": (y0d + (s["r0"] + SUB_CELLS / 2) * cd) * DOT_MM}
        if cls is not None:
            sl = (slice(s["r0"], s["r0"] + SUB_CELLS), slice(s["c0"], s["c0"] + SUB_CELLS))
            for k, pred in errs.items():
                r[f"err_{k}"] = 100.0 * float((pred[sl] != cls[sl]).mean())
        for p in ALL_PLANES:
            if p in s.get("d", {}):
                r.update({f"{p}_dy": s["d"][p][0], f"{p}_dx": s["d"][p][1], f"{p}_flag": s["flags"][p],
                          f"{p}_peak": s.get("peaks", {}).get(p)})
                for h in ("0", "1"):
                    if p in s.get("d" + h, {}):
                        r.update({f"{p}_dy{h}": s["d" + h][p][0], f"{p}_dx{h}": s["d" + h][p][1],
                                  f"{p}_flag{h}": s["flags" + h][p]})
        out.append(r)
    return out


def run_sheet(scan_path: Path, manifest: Path, out: Path, workers: int, sel: list[str] | None) -> Rec:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    man = json.loads(manifest.read_text())
    dpi = float(man["dpi"])
    npz = np.load(manifest.parent / man["bands_npz"]["file"])
    scan = Scan(scan_path)
    sub = sub_px_per_dot(scan.dpi, dpi)
    frame = page_frame(man)
    A, fit = fit_page(scan, frame, 0.3, 0.01)
    rects = [(x * DOT_MM, y * DOT_MM, (x + w) * DOT_MM, (y + h) * DOT_MM)
             for e in [*man["bands"], *man.get("bars", []), *man["fiducials"]] for x, y, w, h in [rect_dots(e, dpi)]]
    white = page_white(scan, A, frame, rects)
    print(f"{man['tag']}: {scan.w} x {scan.h} px, {sub} px/dot; page white {np.round(white, 1).tolist()} "
          f"({time.time() - t0:.0f} s)")
    bands = [b for b in man["bands"] if band_arrays(npz, b, dpi) is not None and (not sel or b["name"] in sel)]
    per: dict[str, Rec] = {}
    for b in bands:
        states, planes = band_arrays(npz, b, dpi)
        kind = kind_of(b)
        x0d, y0d, cd = int(b["x_dots"]), int(b["y_dots"]), int(b["cell_dots"])
        cls = None
        if kind == "cmy4":
            if [s[0] for s in states_of(b)] != ["W", "C", "M", "Y"]:
                raise SystemExit(f"{b['name']}: states {states_of(b)} are not W, C, M, Y")
            cls = states.astype(np.uint8)
            if not np.array_equal(dot_planes(cls, cd), planes):
                raise SystemExit(f"{b['name']}: npz planes differ from the class grid's dot planes")
            wins1 = read_windows(scan, A, x0d, y0d, cls, cd, white, sub, workers)
            wins = read_windows(scan, A, x0d, y0d, cls, cd, white, sub, workers, prior_offsets(wins1))
        else:
            if kind == "K":
                cls = states.astype(np.uint8)
            wins1 = read_windows_planes(scan, A, x0d, y0d, planes, cd, white, sub, workers)
            pri = prior_offsets(as_cmy(wins1) if kind == "K" else wins1)
            wins = read_windows_planes(scan, A, x0d, y0d, planes, cd, white, sub, workers, pri)
        per[b["name"]] = {"band": b, "kind": kind, "cls": cls, "planes": planes, "wins1": wins1, "wins": wins}
        tally = " ".join(f"{p} " + "/".join(str(sum(w.get("flags", {}).get(p) == f for w in wins))
                                            for f in ("ok", "edge", "weak", "collinear")) for p in ALL_PLANES
                         if any(p in w.get("flags", {}) for w in wins))
        print(f"  {b['name']} ({kind}, c{cd}): {len(wins)} windows, ok/edge/weak/collinear pass 2 {tally} "
              f"({time.time() - t0:.0f} s)", flush=True)
    c4 = {k: p for k, p in per.items() if p["kind"] == "cmy4"}
    aff = fit_plane_affines([(p["wins"], int(p["band"]["x_dots"]), int(p["band"]["y_dots"]),
                              int(p["band"]["cell_dots"])) for p in c4.values()]) if c4 else {}
    edges = slice_edges(min(int(b["x_dots"]) for b in bands) * DOT_MM,
                        max(int(b["x_dots"]) + int(b["w_dots"]) for b in bands) * DOT_MM, WIDTH_MM)
    srows, prof, wrows, subrows, krows, repro = [], [], [], [], [], {}
    for name, p in per.items():
        b, cls, kind, wins = p["band"], p["cls"], p["kind"], p["wins"]
        cd, x0d, y0d = int(b["cell_dots"]), int(b["x_dots"]), int(b["y_dots"])
        wrows += window_rows(name, kind, b, wins, p["wins1"])
        if kind == "cmy4":
            pal = b["palette"]
            bb = dict(b, lookup={"C": pal[states_of(b)[1]], "M": pal[states_of(b)[2]]})
            X_read = paint_X(p["wins1"], cls.shape)
            repro[name] = check_reproduction(X_read, sample_field(scan, A, x0d, y0d, cd, sub, paint(p["wins1"], cls.shape)))
            off_win = paint(wins, cls.shape)
            subs = refine_subwindows(scan, A, x0d, y0d, cls, cd, white, sub, wins, workers)
            arms = {"win": sample_field(scan, A, x0d, y0d, cd, sub, off_win),
                    "finex": sample_field(scan, A, x0d, y0d, cd, sub, fine_field(off_win, subs, crossfit=True)),
                    "fine": sample_field(scan, A, x0d, y0d, cd, sub, fine_field(off_win, subs, crossfit=False)),
                    "diff": sample_field(scan, A, x0d, y0d, cd, sub, diff_field(off_win, wins, x0d, y0d, cd)),
                    "common": sample_field(scan, A, x0d, y0d, cd, sub, diff_field(off_win, wins, x0d, y0d, cd, smooth=False)),
                    "aff": sample_field(scan, A, x0d, y0d, cd, sub, affine_field(aff, x0d, y0d, cd, cls.shape))}
            fam = slice_families(scan, A, (x0d, y0d, x0d + cls.shape[1] * cd, y0d + cls.shape[0] * cd), edges, cd, sub,
                                 float(fit["rotation_deg"]))
            srows += band_rows(name, bb, cls, wins, subs, arms, X_read, edges, fam, [[float("nan")] * 3] * (len(edges) - 1))
            prof += profile_rows(name, bb, cls, subs, arms, X_read)
            full = np.ones(cls.shape, bool)
            subrows += sub_rows(name, kind, b, subs, {"read": predict(X_read, cls, full),
                                                      "finex": predict(arms["finex"], cls, full)}, cls)
        else:
            subs = refine_subwindows_planes(scan, A, x0d, y0d, p["planes"], cd, white, sub, wins, workers)
            if kind == "K":
                kw, ks = as_cmy(wins), as_cmy(subs)
                X_read = paint_X(p["wins1"], cls.shape)
                repro[name] = check_reproduction(X_read, sample_field(scan, A, x0d, y0d, cd, sub,
                                                                      paint(as_cmy(p["wins1"]), cls.shape)))
                off_win = paint(kw, cls.shape)
                arms = {"read": X_read, "win": sample_field(scan, A, x0d, y0d, cd, sub, off_win),
                        "finex": sample_field(scan, A, x0d, y0d, cd, sub, fine_field(off_win, ks, crossfit=True))}
                krows += k_slice_rows(name, b, cls, arms, wins, subs, edges)
                full = np.ones(cls.shape, bool)
                subrows += sub_rows(name, kind, b, subs, {a: predict(arms[a], cls, full) for a in ("read", "finex")}, cls)
            else:
                subrows += sub_rows(name, kind, b, subs, {}, None)
        print(f"  {name}: {len(subs)} sub-windows" + (", reproduction mean |d| "
              + " ".join(f"{v:.2f}" for v in repro[name]["mean_abs"]) if name in repro else "")
              + f" ({time.time() - t0:.0f} s)", flush=True)
    for fn, rows in (("windows.csv", wrows), ("subwindows.csv", subrows), ("slices.csv", srows),
                     ("profile_1mm.csv", prof), ("kslices.csv", krows)):
        if rows:
            write_csv(out / fn, rows)
    summ = {"tag": man["tag"], "scan": str(scan_path), "manifest": str(manifest), "fit": fit, "page_white": white.tolist(),
            "bands": {k: {"kind": p["kind"], "cell_dots": int(p["band"]["cell_dots"]), "alphabet": p["band"]["alphabet"],
                          "x_mm": int(p["band"]["x_dots"]) * DOT_MM, "y_mm": int(p["band"]["y_dots"]) * DOT_MM}
                      for k, p in per.items()},
            "page_affines": aff, "reproduction": repro, "edges_mm": edges.tolist(), "seconds": time.time() - t0}
    (out / "summary.json").write_text(json.dumps(jsonable(summ), indent=1))
    print(f"wrote {out} ({time.time() - t0:.0f} s)")
    return summ


def fl(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(open(path))) if path.exists() else []


def plane_profile(rows: list[dict[str, str]], plane: str, x_lo: float = 10.5, x_hi: float = 199.5,
                  axis: str = "dy") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bin centres, the median over bands of the relative dy per BIN_MM, the band count.  Per band: dy relative to the
    plane's REF_MM median per sub-window row r0, the median over rows per sub-window column, linearly interpolated to
    the bin centres within the band's x range (c2 and c3 sub-windows are 1.5 and 2.3 mm wide; a pooled bin median
    would alias bands with different common-mode drift).  plane "M-C" (any pair): the differential dy where both
    planes are "ok"; axis "dx" the same for the x offsets."""
    xc = np.arange(x_lo, x_hi, BIN_MM) + BIN_MM / 2
    per: list[np.ndarray] = []
    pl = plane.split("-")
    for band in sorted({r["band"] for r in rows}):
        rs = [r for r in rows if r["band"] == band and all(r.get(f"{q}_flag") == "ok" for q in pl)]
        if not rs:
            continue
        x = np.array([fl(r["x_mm"]) for r in rs])
        r0 = np.array([int(r["r0"]) for r in rs])
        dy = np.array([fl(r[f"{pl[0]}_{axis}"]) - (fl(r[f"{pl[1]}_{axis}"]) if len(pl) > 1 else 0.0) for r in rs])
        rel = np.full(len(rs), np.nan)
        for rr in set(r0.tolist()):
            sel = r0 == rr
            ref = (x >= REF_MM[0]) & (x < REF_MM[1]) & sel
            if ref.sum() >= 3:
                rel[sel] = dy[sel] - np.median(dy[ref])
        ux = np.unique(x[np.isfinite(rel)])
        if len(ux) < 2:
            continue
        uv = np.array([np.median(rel[(x == u) & np.isfinite(rel)]) for u in ux])
        per.append(np.where((xc >= ux[0]) & (xc <= ux[-1]), np.interp(xc, ux, uv), np.nan))
    if not per:
        return xc, np.full(len(xc), np.nan), np.zeros(len(xc), int)
    P = np.array(per)
    n = np.isfinite(P).sum(0)
    with np.errstate(all="ignore"):
        med = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else np.nan for c in P.T])
    return xc, med, n


def find_steps(x: np.ndarray, v: np.ndarray) -> list[tuple[float, float]]:
    """(x at the boundary, step) where |median right - median left| over STEP_SIDE_MM > STEP_MIN_DOTS, local extrema."""
    k = int(round(STEP_SIDE_MM / BIN_MM))
    edges = x - BIN_MM / 2
    s = np.full(len(x), np.nan)
    for i in range(k, len(x) - k + 1):
        lft, rgt = v[i - k:i], v[i:i + k]
        if np.isfinite(lft).sum() >= 2 and np.isfinite(rgt).sum() >= 2:
            s[i] = np.nanmedian(rgt) - np.nanmedian(lft)
    out = []
    for i in range(len(s)):
        if not np.isfinite(s[i]) or abs(s[i]) <= STEP_MIN_DOTS:
            continue
        nb = s[max(0, i - k):i + k + 1]
        if abs(s[i]) >= np.nanmax(np.abs(nb)):
            out.append((float(edges[i]), float(s[i])))
    return out


def screen_events(prof: dict[str, float], thr: float) -> Rec:
    xs = sorted((float(k), v) for k, v in prof.items())
    on = next((x for x, v in xs if v > thr), float("nan"))
    reset = next((x for x, v in xs if x >= max(RESET_FROM_MM, on) and v <= thr), float("nan"))
    re_on = next((x for x, v in xs if x > reset and v > thr), float("nan")) if np.isfinite(reset) else float("nan")
    return {"first_bin": xs[0][0] if xs else float("nan"), "switch_on": on, "reset": reset, "re_on": re_on}


def peak_crossings(subs: list[dict[str, str]], band: str) -> tuple[np.ndarray, np.ndarray, list[tuple[float, str]]]:
    """Per sub-window column the median of the M and Y pose peaks; where it crosses halfway between its 90th and 10th
    percentile (linear between columns): (x, "down" = toward the screened level, "up" = back)."""
    rs = [r for r in subs if r["band"] == band and r.get("M_peak") and r.get("Y_peak")]
    x = np.array([fl(r["x_mm"]) for r in rs])
    pk = np.array([0.5 * (fl(r["M_peak"]) + fl(r["Y_peak"])) for r in rs])
    ux = np.unique(x)
    v = np.array([np.median(pk[x == u]) for u in ux])
    mid = 0.5 * (np.percentile(v, 90) + np.percentile(v, 10))
    out = []
    for i in range(len(v) - 1):
        if (v[i] - mid) * (v[i + 1] - mid) < 0:
            out.append((float(ux[i] + (mid - v[i]) / (v[i + 1] - v[i]) * (ux[i + 1] - ux[i])),
                        "down" if v[i + 1] < v[i] else "up"))
    return ux, v, out


def zone_rows(sheet: str, slices: list[dict[str, str]], subs: list[dict[str, str]]) -> list[Rec]:
    keys = ["E_band_read", "E_slice_read", "E_slice_win", "E_slice_finex", "E_slice_diff", "E_slice_common",
            "dp_read_C", "dp_read_M", "dp_read_Y", "dp_finex_C", "dp_finex_M", "dp_finex_Y", "mu_W_C", "mu_W_M",
            "mu_W_Y", "mu_P_C", "mu_P_M", "mu_P_Y", "w0_C", "w0_M", "w0_Y", "p0_C", "p0_M", "p0_Y", "Y213_Y"]
    out = []
    for band in dict.fromkeys(r["band"] for r in slices):
        rs = [r for r in slices if r["band"] == band]
        x_lo = min(fl(r["x0_mm"]) for r in rs)
        ss = [s for s in subs if s["band"] == band]
        for z, (a, c) in (("LEFT", (x_lo, LEFT_END_MM)), ("MID", MID_MM)):
            zr = [r for r in rs if a <= 0.5 * (fl(r["x0_mm"]) + fl(r["x1_mm"])) < c]
            w = np.array([fl(r["n_cells"]) for r in zr])
            rec: Rec = {"sheet": sheet, "band": band, "cell_dots": rs[0]["cell_dots"], "C_G": rs[0]["C_G"],
                        "y_mm": fl(rs[0]["y_mm"]), "zone": z, "x0_mm": a, "x1_mm": c, "n_cells": int(w.sum())}
            for k in keys:
                v = np.array([fl(r.get(k)) for r in zr])
                ok = np.isfinite(v)
                rec[k] = float((v[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() else float("nan")
            sz = [s for s in ss if a <= fl(s["x_mm"]) < c]
            for q in ("M", "Y"):
                d = [fl(s[f"{q}_dy"]) - fl(s["C_dy"]) for s in sz if s.get(f"{q}_flag") == "ok" and s.get("C_flag") == "ok"]
                rec[f"sub_{q}C_dy"] = float(np.median(d)) if d else float("nan")
            out.append(rec)
    return out


def summarize(dirs: list[Path], extract: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    ex = json.loads(extract.read_text())
    lines: list[str] = []
    prof_rows, step_rows, ev_rows, zrows, pk_rows = [], [], [], [], []
    for d in dirs:
        summ = json.loads((d / "summary.json").read_text())
        A = np.asarray(summ["fit"]["affine_mm_to_colrow"])

        def platen(x_mm: float, A: np.ndarray = A) -> float:
            return float((A[0, 0] * x_mm + A[0, 1] * PAGE_MID_Y_MM + A[0, 2]) / summ["fit"]["px_per_mm"])
        tag, sheet = summ["tag"], summ["tag"].split("-")[0]
        subs, wins = read_csv(d / "subwindows.csv"), read_csv(d / "windows.csv")
        lines.append(f"\n== {tag}: fit rotation {summ['fit']['rotation_deg']} deg, residual max "
                     f"{max(summ['fit']['residual_mm'].values()):.3f} mm, orientation {summ['fit']['orientation']}")
        groups = {"cmy4-sub": [s for s in subs if s["kind"] == "cmy4"],
                  "other-sub": [s for s in subs if s["kind"] not in ("cmy4", "K")],
                  "other-win": [w for w in wins if w["kind"] not in ("cmy4", "K")],
                  "K-sub": [s for s in subs if s["kind"] == "K"]}
        for src, rows in groups.items():
            if not rows:
                continue
            nb = sorted({r["band"] for r in rows})
            for ax, p in [("dy", q) for q in ALL_PLANES + ("M-C", "Y-C")] + [("dx", q) for q in ALL_PLANES]:
                if not any(all(r.get(f"{q}_flag") == "ok" for q in p.split("-")) for r in rows):
                    continue
                x, v, n = plane_profile(rows, p, axis=ax)
                prof_rows += [{"sheet": sheet, "source": src, "axis": ax, "plane": p, "x_mm": a, "rel": b, "n": c}
                              for a, b, c in zip(x, v, n)]
                st = find_steps(x, v)
                step_rows += [{"sheet": sheet, "source": src, "axis": ax, "plane": p, "x_mm": a, "platen_mm": platen(a),
                               "step_dots": s} for a, s in st]
                lines.append(f"  {src} ({','.join(nb)}) {p} {ax} steps (page x mm [platen mm] dots): "
                             + ", ".join(f"{a:.1f} [{platen(a):.1f}] {s:+.2f}" for a, s in st))
        sl = read_csv(d / "slices.csv")
        if sl:
            zrows += zone_rows(sheet, sl, [s for s in subs if s["kind"] == "cmy4"])
        bs = ex["band_screen"].get(tag, {}).get("bands", {})
        sc = {b["name"]: b for b in ex["scale"].get(tag, {}).get("bands", [])}
        for name, info in summ["bands"].items():
            if info["kind"] not in ("cmy4", "K"):
                ux, v, cr = peak_crossings(subs, name)
                pk_rows += [{"sheet": sheet, "band": name, "x_mm": a, "MY_peak": b} for a, b in zip(ux, v)]
                lines.append(f"  M/Y pose peak {name} ({info['kind']}, {v.min():.2f}..{v.max():.2f}) crosses halfway at: "
                             + ", ".join(f"{a:.1f} {d}" for a, d in cr))
            if info["kind"] in ("cmy4", "K") or name not in bs:
                continue
            ev: Rec = {"sheet": sheet, "band": name, "kind": info["kind"], "x_start_mm": info["x_mm"]}
            for lat, thr in SCREEN_ON.items():
                e = screen_events(bs[name][lat], thr)
                ev.update({f"{lat}_{k}": v for k, v in e.items()})
            if name in sc:
                pc = sc[name]["profile_col_state_err_loo"]
                ev["loo_profile"] = " ".join(f"{q[0]:.0f}:{100 * q[1]:.0f}" for q in pc)
            ev_rows.append(ev)
            lines.append(f"  screen {name} ({info['kind']}, from {info['x_mm']:.1f} mm): 212 lpi on "
                         f"{ev['212_switch_on']:.0f} reset {ev['212_reset']:.0f} re-on {ev['212_re_on']:.0f}; "
                         f"165 lpi on {ev['165_switch_on']:.0f} reset {ev['165_reset']:.0f} re-on {ev['165_re_on']:.0f}")
        ks = read_csv(d / "kslices.csv")
        for r in ks:
            lines.append("  K " + " ".join(f"{k} {fl(r[k]):.2f}" for k in ("x0_mm", "E_band_read", "E_band_finex",
                                                                          "E_slice_finex", "best_finex", "dp_finex",
                                                                          "mu_W_finex", "mu_K_finex", "sd_W_finex",
                                                                          "sd_K_finex", "w0_K", "p0_K", "Wspread_K",
                                                                          "sub_K_dy")))
        if len(ks) > 4:
            e = np.array([fl(r["E_slice_finex"]) for r in ks])
            lines.append("  K Spearman of E_slice_finex with: " + ", ".join(
                f"{k} {spearmanr(e, [fl(r[k]) for r in ks], nan_policy='omit')[0]:+.2f}"
                for k in ("x0_mm", "mu_W_finex", "mu_K_finex", "sd_W_finex", "sd_K_finex", "w0_K", "p0_K", "Wspread_K",
                          "sub_K_dy", "sub_K_dx")))
    for z in zrows:
        lines.append(f"  zone {z['sheet']} {z['band']} c{z['cell_dots']} C_G {z['C_G']} {z['zone']}: read {z['E_band_read']:.2f} "
                     f"win {z['E_slice_win']:.2f} finex {z['E_slice_finex']:.2f}; d' {z['dp_finex_C']:.2f}/"
                     f"{z['dp_finex_M']:.2f}/{z['dp_finex_Y']:.2f}; M-C dy {z['sub_MC_dy']:+.2f} Y-C dy {z['sub_YC_dy']:+.2f}")
    for fn, rows in (("plane_profile.csv", prof_rows), ("steps.csv", step_rows), ("screen_events.csv", ev_rows),
                     ("zones.csv", zrows), ("peak_profile.csv", pk_rows)):
        if rows:
            write_csv(out / fn, rows)
    (out / "report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a1 = sp.add_parser("sheet", help="one e041 sheet: windows, sub-windows, slices")
    a1.add_argument("--scan", required=True, type=Path, help="the sheet's 2400 dpi RGB TIFF")
    a1.add_argument("--manifest", required=True, type=Path, help="the sheet's manifest JSON (bands npz beside it)")
    a1.add_argument("--out", required=True, type=Path, help="output directory")
    a1.add_argument("--bands", default="", help="comma-separated band names (default: every band with arrays)")
    a1.add_argument("--workers", type=int, default=8, help="window-reading threads")
    a2 = sp.add_parser("summarize", help="steps, screen events, zones over sheet directories")
    a2.add_argument("--dirs", required=True, nargs="+", type=Path, help="per-sheet output directories")
    a2.add_argument("--extract", required=True, type=Path, help="experiments/041-m281-screen-routes/results/measurements.json")
    a2.add_argument("--out", required=True, type=Path, help="output directory")
    a = ap.parse_args()
    if a.cmd == "sheet":
        run_sheet(a.scan, a.manifest, a.out, a.workers, [s for s in a.bands.split(",") if s] or None)
    else:
        summarize(a.dirs, a.extract, a.out)


if __name__ == "__main__":
    main()

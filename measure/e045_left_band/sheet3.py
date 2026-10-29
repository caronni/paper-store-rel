"""e045 — the left band per x slice on e043 sheet 3 (E043c): fifteen full-width cmy mask bands at x 12.0-197.9 mm,
one variable per band (cyan G 176/178/184/192, magenta 240/242/238 x 192/194), one print, one day, one x range.

Per band (its manifest rectangle, GT states_c2 / states_c3, the readout's fiducial page affine and page white
from scratch/e043c/readout/summary.json; sheets 1 and 2 of e043 read the same way, a band without its own colour
lookup taking the sheet's):
  1. every 36-cell window read by bands.read_window twice: no prior (as the e043 readout read the bands: the
     `read` arm, its X kept), then with the 3 x 3 neighbourhood prior (cells.prior_offsets: the `win` arm);
  2. one affine per plane over every band's "ok" pass-2 window offsets (the page pose); per window the 2 x 2
     SUB_CELLS sub-windows posed again, all cells and each checkerboard half (cells.refine_subwindows);
  3. the pose arms sampled the same way (cells.sample_field): win, finex (cross-fitted sub-windows), fine (the
     same, in-sample: finex - fine is the in-sample pose's optimism), diff (C local + smoothed differential),
     common (every plane at C's pose), aff (page affine); read = read_window's own X;
  4. per WIDTH_MM slice of page x (slices.py): errors (band table at read = the readout's number; slice table
     at every arm), per-plane separation at every arm, the neighbour model at finex, the window offsets; the
     screen families per slice (spectra.py);
  5. bare paper per slice: the 2.03 mm gaps between the bands (their central 1 mm), and per 1 mm the margins
     left (x 1.5-11.5 mm) and right (198.5-208 mm) of the bands over B3..B14's rows (clear of the fiducials);
  6. a 1 mm profile per band: band-table error at read_window's X, slice-table error at win and fine, and the
     sub-window M - C, Y - C offsets.

    PYTHONPATH=src:. env/bin/python -u -m measure.e045_left_band.sheet3 \\
        --scan <E043-m281-cmy-probe3-a-scan.tiff> --manifest <E043c-m281-cmy-probe3.manifest.json> \\
        --gt <E043c-m281-cmy-probe3-gt.npz> --summary <e043c/readout/summary.json> --out <dir> [--workers 8]
Outputs: slices.csv (one row per band x slice), profile_1mm.csv, windows.csv, subwindows.csv, paper.csv,
summary.json; the condensed table on stdout.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from measure.cmy_probe.bands import state_classes
from measure.e041_probe_readout import Scan, jsonable, sub_px_per_dot
from measure.e045_left_band.cells import (PLANES, SUB_CELLS, affine_field, check_reproduction, diff_field,
                                          fine_field, fit_plane_affines, paint, paint_X, prior_offsets, read_windows,
                                          refine_subwindows, sample_field, window_centres_dots)
from measure.e045_left_band.slices import (error_stats, neighbour_model, neighbour_states, offsets, predict,
                                           separation, slice_edges)
from measure.e045_left_band.spectra import slice_families

DOT_MM = 25.4 / 600.0
WIDTH_MM = 5.0
FINE_MM = 1.0
GAP_INSET = 12                   # printed dots kept clear of each band edge inside a gap (less where the gap is narrower)
Rec = dict[str, Any]


def paper_points(scan: Scan, A: np.ndarray, xs_mm: np.ndarray, ys_mm: np.ndarray) -> np.ndarray:
    """(n, 3) RGB at the points (bilinear)."""
    col = A[0, 0] * xs_mm + A[0, 1] * ys_mm + A[0, 2]
    row = A[1, 0] * xs_mm + A[1, 1] * ys_mm + A[1, 2]
    r0, r1 = int(np.floor(row.min())) - 2, int(np.ceil(row.max())) + 3
    c0, c1 = int(np.floor(col.min())) - 2, int(np.ceil(col.max())) + 3
    win = scan.crop(r0, r1, c0, c1)
    return np.stack([ndimage.map_coordinates(win[..., c], [row - r0, col - c0], order=1) for c in range(3)], -1)


def paper_levels(scan: Scan, A: np.ndarray, bands: list[Rec], edges: np.ndarray) -> Rec:
    """Median paper RGB per slice over the inter-band gaps; per 1 mm over the left and right margins."""
    bs = sorted(bands, key=lambda b: b["y_dots"])
    def inset(a: Rec, b: Rec) -> int:
        return max(2, min(GAP_INSET, (b["y_dots"] - a["y_dots"] - a["h_dots"] - 8) // 2))
    gaps = [(a["y_dots"] + a["h_dots"] + inset(a, b), b["y_dots"] - inset(a, b)) for a, b in zip(bs[:-1], bs[1:])]
    xs = np.arange(edges[0], edges[-1], 2 * DOT_MM)
    vals = []
    for ga, gb in gaps:
        ys = np.arange(ga, gb, 2.0) * DOT_MM
        X, Y = np.meshgrid(xs, ys)
        vals.append((X.ravel(), paper_points(scan, A, X.ravel(), Y.ravel())))
    gx = np.concatenate([v[0] for v in vals])
    gv = np.concatenate([v[1] for v in vals])
    per = [np.median(gv[(gx >= a) & (gx < b)], 0).tolist() for a, b in zip(edges[:-1], edges[1:])]
    rows_y = [b for b in bs if b["name"] not in ("B1", "B2", "B15")]
    y_lo, y_hi = min(b["y_dots"] for b in rows_y) * DOT_MM, max(b["y_dots"] + b["h_dots"] for b in rows_y) * DOT_MM
    margins = {}
    for side, (m0, m1) in (("left", (1.5, 11.5)), ("right", (198.5, 208.0))):
        prof = []
        for a in np.arange(m0, m1, FINE_MM):
            X, Y = np.meshgrid(np.arange(a, a + FINE_MM, 2 * DOT_MM), np.arange(y_lo, y_hi, 0.5))
            prof.append([float(a)] + np.median(paper_points(scan, A, X.ravel(), Y.ravel()), 0).tolist())
        margins[side] = prof
    return {"gaps_dots": gaps, "per_slice": per, "margins_1mm": margins}


def band_rows(name: str, b: Rec, cls: np.ndarray, wins: list[Rec], subs: list[Rec], arms: dict[str, np.ndarray],
              X_read: np.ndarray, edges: np.ndarray, fam: list[Rec], paper: list[list[float]]) -> list[Rec]:
    cd, x0d, y0d = int(b["cell_dots"]), int(b["x_dots"]), int(b["y_dots"])
    cols = cls.shape[1]
    col_x = (x0d + (np.arange(cols) + 0.5) * cd) * DOT_MM
    full = np.ones(cls.shape, bool)
    pred_band = predict(X_read, cls, full)
    nb = neighbour_states(cls)
    wcx = np.array([window_centres_dots(w, x0d, y0d, cd)[0] * DOT_MM for w in wins])
    rows = []
    for i, (a, c) in enumerate(zip(edges[:-1], edges[1:])):
        mask = np.broadcast_to((col_x >= a) & (col_x < c), cls.shape)
        if not mask.any():
            continue
        r: Rec = {"band": name, "cell_dots": cd, "C_G": b["lookup"]["C"][1], "M_RB": f"{b['lookup']['M'][0]}/{b['lookup']['M'][2]}",
                  "y_mm": (y0d + b["h_dots"] / 2) * DOT_MM, "slice": i, "x0_mm": float(a), "x1_mm": float(c)}
        e = error_stats(cls, pred_band, mask)
        r.update({"n_cells": e["n"], "E_band_read": e["err"], **{f"E_band_read_{p}": e[f"err_{p}"] for p in PLANES},
                  "E_band_read_W": e["err_state_W"], "share_W": e["share_W_cells"]})
        for arm, X in {"read": X_read, **arms}.items():
            es = error_stats(cls, predict(X, cls, mask), mask)
            r[f"E_slice_{arm}"] = es["err"]
            for p in PLANES:
                r[f"E_slice_{arm}_{p}"] = es[f"err_{p}"]
            sep = separation(X, cls, mask)
            for p in PLANES:
                s = sep.get(p, {})
                r[f"dp_{arm}_{p}"] = s.get("dprime", float("nan"))
                r[f"best_{arm}_{p}"] = s.get("best_err", float("nan"))
                if arm == "finex":
                    for k in ("mu_W", "sd_W", "mu_P", "sd_P"):
                        r[f"{k}_{p}"] = s.get(k, float("nan"))
        nm = neighbour_model(arms["finex"], cls, mask, nb)
        for p in PLANES:
            m = nm.get(p)
            if not m:
                continue
            r.update({f"w0_{p}": m["w0"], f"p0_{p}": m["p0"], f"dp0_{p}": m["dprime0"],
                      f"Wspread_own_{p}": m["W_fit"]["spread"][p],
                      **{f"W_NS_{q}_in_{p}": m["W_fit"]["N_minus_S"][q] for q in PLANES},
                      **{f"W_WE_{q}_in_{p}": m["W_fit"]["W_minus_E"][q] for q in PLANES},
                      **{f"Wspread_{q}_in_{p}": m["W_fit"]["spread"][q] for q in PLANES if q != p}})
        r.update(offsets(wins, wcx, a, c))
        sd = [s for s in subs if a <= (x0d + (s["c0"] + SUB_CELLS / 2) * cd) * DOT_MM < c]
        for q in ("M", "Y"):
            dd = np.array([np.subtract(s["d"][q], s["d"]["C"]) for s in sd
                           if s["flags"].get(q) == "ok" and s["flags"].get("C") == "ok"], float).reshape(-1, 2)
            r[f"sub_{q}C_dy"] = float(np.median(dd[:, 0])) if len(dd) else float("nan")
            r[f"sub_{q}C_dx"] = float(np.median(dd[:, 1])) if len(dd) else float("nan")
            r[f"sub_{q}C_dy_sd"] = float(dd[:, 0].std()) if len(dd) > 2 else float("nan")
        f = fam[i] if i < len(fam) else {}
        r.update({k: f.get(k, float("nan")) for k in ("Y213_Y", "Y213_C", "s165_max", "s188_max", "noise_max")})
        r.update({f"paper_{ch}": paper[i][j] for j, ch in enumerate("RGB")})
        rows.append(r)
    return rows


def profile_rows(name: str, b: Rec, cls: np.ndarray, subs: list[Rec], arms: dict[str, np.ndarray],
                 X_read: np.ndarray) -> list[Rec]:
    cd, x0d = int(b["cell_dots"]), int(b["x_dots"])
    cols = cls.shape[1]
    col_x = (x0d + (np.arange(cols) + 0.5) * cd) * DOT_MM
    edges = slice_edges(x0d * DOT_MM, (x0d + cols * cd) * DOT_MM, FINE_MM)
    pred_band = predict(X_read, cls, np.ones(cls.shape, bool))
    out = []
    for a, c in zip(edges[:-1], edges[1:]):
        mask = np.broadcast_to((col_x >= a) & (col_x < c), cls.shape)
        if not mask.any():
            continue
        r = {"band": name, "cell_dots": cd, "C_G": b["lookup"]["C"][1], "x0_mm": float(a), "x1_mm": float(c),
             "E_band_read": error_stats(cls, pred_band, mask)["err"],
             **{f"E_slice_{k}": error_stats(cls, predict(arms[k], cls, mask), mask)["err"]
                for k in ("win", "finex", "diff", "common")}}
        sd = [s for s in subs if a <= (x0d + (s["c0"] + SUB_CELLS / 2) * cd) * DOT_MM < c + 0.5]
        for q in ("M", "Y"):
            dd = np.array([np.subtract(s["d"][q], s["d"]["C"]) for s in sd
                           if s["flags"].get(q) == "ok" and s["flags"].get("C") == "ok"], float).reshape(-1, 2)
            r[f"sub_{q}C_dy"] = float(np.median(dd[:, 0])) if len(dd) else float("nan")
            r[f"sub_{q}C_dx"] = float(np.median(dd[:, 1])) if len(dd) else float("nan")
        out.append(r)
    return out


def write_csv(path: Path, rows: list[Rec]) -> None:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


def run(scan_path: Path, manifest: Path, gt: Path, summary: Path, out: Path, workers: int, sel: list[str] | None) -> Rec:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    man, gtz = json.loads(manifest.read_text()), np.load(gt)
    fit = json.loads(summary.read_text())["scans"][0]
    A, white, rot = np.asarray(fit["fit"]["affine_mm_to_colrow"]), np.asarray(fit["page_white"], float), float(fit["fit"]["rotation_deg"])
    scan = Scan(scan_path)
    sub = sub_px_per_dot(scan.dpi, 600.0)
    sheet_lookup = man.get("lookup") if isinstance(man.get("lookup"), dict) and "C" in man.get("lookup", {}) else None
    bands = [b if "lookup" in b else {**b, "lookup": sheet_lookup or {"C": [None, float("nan"), None], "M": [float("nan")] * 3}}
             for b in man["bands"] if not sel or b["name"] in sel]
    print(f"{scan_path.name}: {scan.w} x {scan.h} px, {sub} px/dot; {len(bands)} bands; page white {white.tolist()}; "
          f"load {time.time() - t0:.0f} s")
    per: dict[str, Rec] = {}
    for b in bands:
        cls = state_classes(gtz[b["gt_key"]])
        x0d, y0d, cd = int(b["x_dots"]), int(b["y_dots"]), int(b["cell_dots"])
        wins1 = read_windows(scan, A, x0d, y0d, cls, cd, white, sub, workers)
        wins = read_windows(scan, A, x0d, y0d, cls, cd, white, sub, workers, prior_offsets(wins1))
        per[b["name"]] = {"band": b, "cls": cls, "wins1": wins1, "wins": wins}

        def tally(ws: list[Rec]) -> str:
            return " ".join(f"{pl} " + "/".join(str(sum(w.get("flags", {}).get(pl) == f for w in ws))
                                                for f in ("ok", "edge", "weak")) for pl in PLANES)
        print(f"  {b['name']}: {len(wins)} windows; ok/edge/weak pass 1 {tally(wins1)}; pass 2 {tally(wins)} "
              f"({time.time() - t0:.0f} s)")
    aff = fit_plane_affines([(p["wins"], int(p["band"]["x_dots"]), int(p["band"]["y_dots"]), int(p["band"]["cell_dots"]))
                             for p in per.values()])
    print("page affine per plane (offset dots vs page dots): " + json.dumps(jsonable(aff)))
    edges = slice_edges(min(int(b["x_dots"]) for b in bands) * DOT_MM,
                        max(int(b["x_dots"]) + int(b["w_dots"]) for b in bands) * DOT_MM, WIDTH_MM)
    paper = paper_levels(scan, A, man["bands"], edges)
    rows, prof, wrows, srows, repro = [], [], [], [], {}
    for name, p in per.items():
        b, cls, wins = p["band"], p["cls"], p["wins"]
        cd, x0d, y0d = int(b["cell_dots"]), int(b["x_dots"]), int(b["y_dots"])
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
        fam = slice_families(scan, A, (x0d, y0d, x0d + cls.shape[1] * cd, y0d + cls.shape[0] * cd), edges, cd, sub, rot)
        rows += band_rows(name, b, cls, wins, subs, arms, X_read, edges, fam, paper["per_slice"])
        prof += profile_rows(name, b, cls, subs, arms, X_read)
        full = np.ones(cls.shape, bool)
        pred_read, pred_fx = predict(X_read, cls, full), predict(arms["finex"], cls, full)
        for w, w1 in zip(wins, p["wins1"]):
            if "skipped" in w:
                continue
            cx, cy = window_centres_dots(w, x0d, y0d, cd)
            sl = (slice(w["r0"], w["r0"] + 36), slice(w["c0"], w["c0"] + 36))
            wr = {"band": name, "cell_dots": cd, "C_G": b["lookup"]["C"][1], "r0": w["r0"], "c0": w["c0"],
                  "x_mm": cx * DOT_MM, "y_mm": cy * DOT_MM, "err_read": 100.0 * float((pred_read[sl] != cls[sl]).mean()),
                  "err_finex": 100.0 * float((pred_fx[sl] != cls[sl]).mean()), "reg_ok_pass1": w1.get("reg_ok")}
            for pl in PLANES:
                if pl in w["d"]:
                    wr.update({f"{pl}_dy": w["d"][pl][0], f"{pl}_dx": w["d"][pl][1], f"{pl}_flag": w["flags"][pl],
                               f"{pl}_flag_pass1": w1.get("flags", {}).get(pl)})
            wrows.append(wr)
        for q in subs:
            sl = (slice(q["r0"], q["r0"] + SUB_CELLS), slice(q["c0"], q["c0"] + SUB_CELLS))
            sr = {"band": name, "cell_dots": cd, "C_G": b["lookup"]["C"][1], "r0": q["r0"], "c0": q["c0"],
                  "x_mm": (x0d + (q["c0"] + SUB_CELLS / 2) * cd) * DOT_MM, "y_mm": (y0d + (q["r0"] + SUB_CELLS / 2) * cd) * DOT_MM,
                  "err_finex": 100.0 * float((pred_fx[sl] != cls[sl]).mean()),
                  "err_read": 100.0 * float((pred_read[sl] != cls[sl]).mean())}
            for pl in PLANES:
                if pl in q.get("d", {}):
                    sr.update({f"{pl}_dy": q["d"][pl][0], f"{pl}_dx": q["d"][pl][1], f"{pl}_flag": q["flags"][pl]})
            srows.append(sr)
        print(f"  {name}: arms sampled, {len(subs)} sub-windows, reproduction mean |d| "
              + " ".join(f"{v:.2f}" for v in repro[name]["mean_abs"]) + f" ({time.time() - t0:.0f} s)")
    write_csv(out / "slices.csv", rows)
    write_csv(out / "profile_1mm.csv", prof)
    write_csv(out / "windows.csv", wrows)
    write_csv(out / "subwindows.csv", srows)
    write_csv(out / "paper.csv", [{"side": s, "x_mm": v[0], "R": v[1], "G": v[2], "B": v[3]}
                                  for s, prof_ in paper["margins_1mm"].items() for v in prof_]
              + [{"side": "gaps", "x_mm": float(a), "R": v[0], "G": v[1], "B": v[2]}
                 for a, v in zip(edges[:-1], paper["per_slice"])])
    summ = {"scan": str(scan_path), "manifest": str(manifest), "gt": str(gt), "fit_summary": str(summary),
            "width_mm": WIDTH_MM, "sub_cells": SUB_CELLS, "edges_mm": edges.tolist(), "page_affines": aff,
            "reproduction": repro, "paper_gaps_dots": paper["gaps_dots"], "seconds": time.time() - t0}
    (out / "summary.json").write_text(json.dumps(jsonable(summ), indent=1))
    print_table(rows)
    print(f"wrote {out} ({time.time() - t0:.0f} s)")
    return summ


def print_table(rows: list[Rec]) -> None:
    cols = [("x0_mm", "x", 5, 0), ("E_band_read", "Eread", 6, 2), ("E_slice_win", "Ewin", 6, 2),
            ("E_slice_finex", "Efinx", 6, 2), ("E_slice_fine", "Efine", 6, 2), ("E_slice_diff", "Ediff", 6, 2),
            ("E_slice_common", "Ecomm", 6, 2), ("dp_finex_C", "d'C", 5, 2), ("dp_finex_M", "d'M", 5, 2),
            ("dp_finex_Y", "d'Y", 5, 2), ("mu_W_C", "WR", 6, 1), ("mu_W_M", "WG", 6, 1), ("mu_W_Y", "WB", 6, 1),
            ("paper_R", "pR", 6, 1), ("MC_dy", "MCdy", 6, 2), ("YC_dy", "YCdy", 6, 2), ("MC_dx", "MCdx", 6, 2),
            ("YC_dx", "YCdx", 6, 2), ("flags_not_ok", "nok", 4, 0), ("Y213_Y", "Y213", 5, 0), ("s165_max", "s165", 5, 0)]
    for band in dict.fromkeys(r["band"] for r in rows):
        rs = [r for r in rows if r["band"] == band]
        print(f"\n{band} c{rs[0]['cell_dots']} C G {rs[0]['C_G']} M {rs[0]['M_RB']} (y {rs[0]['y_mm']:.0f} mm)")
        print(" ".join(f"{h:>{w}}" for _, h, w, _ in cols))
        for r in rs:
            print(" ".join(f"{r.get(k, float('nan')):{w}.{d}f}" for k, _, w, d in cols))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", required=True, type=Path, help="sheet 3's 2400 dpi RGB TIFF")
    ap.add_argument("--manifest", required=True, type=Path, help="sheet 3's manifest JSON")
    ap.add_argument("--gt", required=True, type=Path, help="sheet 3's GT npz (states_c2, states_c3)")
    ap.add_argument("--summary", required=True, type=Path, help="sheet 3's readout summary.json (page fit, white)")
    ap.add_argument("--out", required=True, type=Path, help="output directory")
    ap.add_argument("--bands", default="", help="comma-separated band names (default: all)")
    ap.add_argument("--workers", type=int, default=8, help="window-reading threads")
    a = ap.parse_args()
    run(a.scan, a.manifest, a.gt, a.summary, a.out, a.workers, [s for s in a.bands.split(",") if s] or None)


if __name__ == "__main__":
    main()

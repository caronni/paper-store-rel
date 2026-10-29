"""e044 — the first readout of a printed cmy format page, TRUTH-FITTED.  MEASUREMENT ONLY: the emitter's ground
truth is read; nothing here can mint a certificate.

The receiver cannot decode a cmy page yet, so the printed field is measured against page000_gt.npy (planes C, M,
Y, one bit per 600 dpi dot, packed along x; cells solid, tests/holo/_receive_free.py gt_cell_states) with the
e043 band instruments applied to the whole page (a format page carries no fiducials):

1. seed: the ink field's four edges in the 16x block mean of min(R, G, B) (Scan.coarse_min, smoothed along each
   edge), one robust line per edge, the corners -> the page mm -> scan affine, as-is or turned 180 deg (the one
   with the higher OR-ed registration peak over windows at the page centre);
2. every 36-cell window of the page read by measure/cmy_probe/bands.read_window (OR-ed registration within
   0.5 mm, per-plane poses C from R, M from G, Y from B within +-3 dots, per-cell centre-box means at those
   poses), TWICE: the first pass gives each window's plane-mean offset, whose 3 x 3 window median is the second
   pass's prior (the page is non-affine by +-2 dots; where the OR-ed peak falls under its bar, as along the
   field's left edge, bands' fallback is the nominal pose and the planes' +-3 dot search would miss);
3. the per-plane poses ("ok" flags) as correspondences page dot -> scan px, fitted affine with the quadratic rms
   beside it (measure/e040-plane-isolation/fit_planes.py's fit_affine / fit_quadratic_rms, restated: that
   directory is not importable); M - C and Y - C per window in printed dots;
4. one colour table per page (bands.classify_band), bands.band_metrics; the per-tile error map; N_SLICES x- and
   y-slices (error per plane, W -> ink, mean features, offsets, the page's non-affine residual);
5. the screening check, measure/e044_cmy_truth/screening.py (the seam: spectra there, cells here): strips of
   sheet 3's band height across the field, per strip and per ~9.3 mm slice the whitened families per ink
   density, and the strips' averaged power.

    PYTHONPATH=src:. env/bin/python -u -m measure.e044_cmy_truth.readout --scan <tiff> \\
        --manifest <E044-X-manifest.json> --gt <E044-X-page000_gt.npy> --out <dir> [--workers 8]
Outputs: summary.json, confusion.csv, tile_error_map.png, profiles.csv, profiles.png, families.json; the log on
stdout.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from measure.cmy_probe.bands import (PLANES_OF_CLASS, STATE_NAMES, WINDOW_CELLS, band_metrics, classify_band,
                                     read_window, state_classes, window_starts)
from measure.cmy_probe.stipples import _font
from measure.e044_cmy_truth.screening import page_boxes, print_families, screening
from measure.e041_mixture_readout import plane_search_px
from measure.e041_probe_readout import Scan, jsonable, sub_px_per_dot
from measure.e041_scale_readout import SEARCH_MM

DPI = 600.0
DOT_MM = 25.4 / DPI
COARSE = 16                     # block-mean factor of the seed image
EDGE_SMOOTH = 9                 # coarse px averaged along an edge before its threshold crossing
N_SLICES = 20
TILE_CELLS = 64
PLANES = ("C", "M", "Y")
Rec = dict[str, Any]


# ---------------------------------------------------------------- inputs and geometry

def load_page(manifest: Path, gt: Path) -> Rec:
    """Manifest geometry and the GT's per-cell classes (W, C, M, Y = 0..3); refuses a non-solid cell."""
    man = json.loads(manifest.read_text())
    cd = int(man["cell_dots"])
    rows, cols = (int(v) for v in man["page_cells_yx"])
    dots = np.unpackbits(np.load(gt, allow_pickle=False), axis=2, count=cols * cd, bitorder="big")
    if dots.shape != (3, rows * cd, cols * cd):
        raise SystemExit(f"GT {dots.shape} vs manifest cells {rows} x {cols} at {cd} dots — contract fork")
    blk = dots.reshape(3, rows, cd, cols, cd)
    if (blk.min((2, 4)) != blk.max((2, 4))).any():
        raise SystemExit("GT cells are not solid — contract fork")
    st = blk[:, :, 0, :, 0]
    return {"format_id": man["format_id"], "cell_dots": cd, "rows": rows, "cols": cols,
            "cls": state_classes((st[0] | st[1] << 1 | st[2] << 2).astype(np.uint8)),
            "origin_yx": tuple(int(v) for v in man["origin_dots_yx"]), "tiles_yx": tuple(int(v) for v in man["tiles_yx"]),
            "rgb_solid": man["codec"]["renderer"]["rgb_solid"]}


def field_box_dots(page: Rec) -> tuple[int, int, int, int]:
    oy, ox = page["origin_yx"]
    return ox, oy, ox + page["cols"] * page["cell_dots"], oy + page["rows"] * page["cell_dots"]


def to_scan(A: np.ndarray, x_dots: Any, y_dots: Any) -> tuple[Any, Any]:
    """(col, row) scan px of page dots through A (page mm -> [col, row])."""
    x, y = np.asarray(x_dots, float) * DOT_MM, np.asarray(y_dots, float) * DOT_MM
    return A[0, 0] * x + A[0, 1] * y + A[0, 2], A[1, 0] * x + A[1, 1] * y + A[1, 2]


def shifted(A: np.ndarray, dy: float, dx: float) -> np.ndarray:
    """A'(p) = A(p + (dx, dy) dots)."""
    B = A.copy()
    B[:, 2] += A[:, :2] @ np.array([dx, dy]) * DOT_MM
    return B


def fit_affine(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, float, float, np.ndarray]:
    """src (n, 2) -> dst (n, 2): the 2 x 3 affine, its rms, the quadratic fit's rms (fit_planes.py's pair), and
    the affine residuals."""
    d1 = np.column_stack([src, np.ones(len(src))])
    sol, *_ = np.linalg.lstsq(d1, dst, rcond=None)
    res = dst - d1 @ sol
    a, b = src[:, 0], src[:, 1]
    d2 = np.column_stack([a, b, a * b, a * a, b * b, np.ones(len(a))])
    s2, *_ = np.linalg.lstsq(d2, dst, rcond=None)
    return (sol.T, float(np.sqrt((res ** 2).sum(1).mean())), float(np.sqrt(((d2 @ s2 - dst) ** 2).sum(1).mean())),
            res)


def axes(dcdx: float, drdx: float, dcdy: float, drdy: float, nominal: float) -> Rec:
    """Per-axis scale over nominal, the mean axis rotation and the skew (deg, + = axes closer than 90 deg) of a
    linear map given by its partials (scan col / row per page x / y)."""
    return {"scale_x": float(np.hypot(dcdx, drdx) / nominal), "scale_y": float(np.hypot(dcdy, drdy) / nominal),
            "rotation_deg": float(np.degrees(np.arctan2(drdx - dcdy, dcdx + drdy))),
            "skew_deg": float(np.degrees(np.arctan2(drdx + dcdy, 0.5 * (dcdx + drdy))))}


def affine_info(A: np.ndarray, scan: Scan) -> Rec:
    return {"affine_mm_to_colrow": A.tolist(), **axes(A[0, 0], A[1, 0], A[0, 1], A[1, 1], scan.px_per_mm)}


def show(label: str, obj: Any, nd: int = 3) -> None:
    """One log line: the label and the object as JSON, floats rounded to nd decimals."""
    def rnd(v: Any) -> Any:
        return round(v, nd) if isinstance(v, float) else {k: rnd(u) for k, u in v.items()} if isinstance(v, dict) \
            else [rnd(u) for u in v] if isinstance(v, list) else v
    print(label, json.dumps(rnd(jsonable(obj.tolist() if isinstance(obj, np.ndarray) else obj))))


# ---------------------------------------------------------------- seed

def _edge_line(g: np.ndarray, mask: np.ndarray, thr: float, first: bool) -> tuple[float, float]:
    """u = a t + b (coarse px) through the sub-pixel threshold crossing of every line t's first (or last) ink
    pixel, three robust passes."""
    lines = np.flatnonzero(mask.any(1))
    t, u = [], []
    for r in lines[int(0.1 * len(lines)):int(0.9 * len(lines))]:
        idx, p = np.flatnonzero(mask[r]), g[r]
        i, j = (idx[0] - 1, idx[0]) if first else (idx[-1], idx[-1] + 1)
        if i < 0 or j >= len(p) or p[i] == p[j]:
            continue
        t.append(r)
        u.append(i + (p[i] - thr) / (p[i] - p[j]))
    t, u = np.asarray(t, float), np.asarray(u, float)
    keep = np.ones(len(t), bool)
    for _ in range(3):
        a, b = np.polyfit(t[keep], u[keep], 1)
        res = u - (a * t + b)
        keep = np.abs(res) < max(1.0, 3 * 1.4826 * np.median(np.abs(res[keep])))
    return float(a), float(b)


def coarse_seed(scan: Scan, page: Rec) -> Rec:
    """Field edges -> corners -> the two candidate affines (as-is, rot180), page mm -> [col, row]."""
    g = scan.coarse_min(COARSE)
    h, w = g.shape
    paper, field = float(np.percentile(g, 95)), float(np.median(g[h // 3:2 * h // 3, w // 3:2 * w // 3]))
    thr = 0.5 * (paper + field)
    lab, _ = ndimage.label(g < thr)
    mask = ndimage.binary_fill_holes(lab == np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    gy, gx = ndimage.uniform_filter1d(g, EDGE_SMOOTH, axis=0), ndimage.uniform_filter1d(g, EDGE_SMOOTH, axis=1)
    L, R = _edge_line(gy, mask, thr, True), _edge_line(gy, mask, thr, False)          # col = a row + b
    T, B = _edge_line(gx.T, mask.T, thr, True), _edge_line(gx.T, mask.T, thr, False)  # row = a col + b

    def meet(v: tuple[float, float], hz: tuple[float, float]) -> tuple[float, float]:
        row = (hz[0] * v[1] + hz[1]) / (1 - hz[0] * v[0])
        return v[0] * row + v[1], row
    S = np.array([meet(L, T), meet(R, T), meet(R, B), meet(L, B)]) * COARSE + 0.5 * (COARSE - 1)  # TL TR BR BL
    x0, y0, x1, y1 = field_box_dots(page)
    src = np.column_stack([np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float) * DOT_MM, np.ones(4)])
    cands = {name: np.linalg.lstsq(src, np.roll(S, -k, axis=0), rcond=None)[0].T for name, k in (("as-is", 0), ("rot180", 2))}
    print(f"seed: paper {paper:.1f}, field {field:.1f}, threshold {thr:.1f}; corners (col, row) "
          + " ".join(f"({c:.0f}, {r:.0f})" for c, r in S))
    return {"paper": paper, "field": field, "threshold": thr, "corners_colrow": S.tolist(), "candidates": cands}


def page_white(scan: Scan, A: np.ndarray, page: Rec) -> np.ndarray:
    """Median RGB of the paper ring 1-3 mm outside the field."""
    x0, y0, x1, y1 = field_box_dots(page)
    d1, d3 = 1.0 / DOT_MM, 3.0 / DOT_MM
    X, Y = np.meshgrid(np.arange(x0 - d3, x1 + d3, 8.0), np.arange(y0 - d3, y1 + d3, 8.0))
    ring = ~((X > x0 - d1) & (X < x1 + d1) & (Y > y0 - d1) & (Y < y1 + d1))
    c, r = (np.round(v).astype(int) for v in to_scan(A, X[ring], Y[ring]))
    ok = (r >= 0) & (r < scan.h) & (c >= 0) & (c < scan.w)
    return np.median(scan.img[r[ok], c[ok], :3].astype(np.float32) * scan.scale255, axis=0)


# ---------------------------------------------------------------- windows

def read_windows(scan: Scan, A: np.ndarray, page: Rec, white: np.ndarray, sub: int, keys: list[tuple[int, int]],
                 workers: int, X: np.ndarray | None = None, prior: dict | None = None) -> list[Rec]:
    """bands.read_window per key (r0, c0) at the window's prior offset (dots); per window the plane offsets "d"
    (dots, prior included, "ok" poses only), their mean "d_mean" when all three are ok, flags and the OR-ed state."""
    cd, (oy, ox), m = page["cell_dots"], page["origin_yx"], int(round(SEARCH_MM / (DOT_MM / sub))) + plane_search_px(sub)

    def one(key: tuple[int, int]) -> Rec:
        r0, c0 = key
        py, px = (prior or {}).get(key, (0.0, 0.0))
        win = page["cls"][r0:r0 + WINDOW_CELLS, c0:c0 + WINDOW_CELLS]
        try:
            w = read_window(scan, shifted(A, py, px), ox + c0 * cd, oy + r0 * cd, win, cd, DPI, white, sub)
        except ValueError as exc:
            return {"r0": r0, "c0": c0, "skipped": str(exc)}
        d = {pl: (py + (q["oy"] - m) / sub, px + (q["ox"] - m) / sub) for pl, q in w["poses"].items() if q["flag"] == "ok"}
        return {"r0": r0, "c0": c0, "yd": oy + r0 * cd, "xd": ox + c0 * cd, "X": w["X"], "reg_ok": w["reg_ok"],
                "reg_edge": w["reg_edge"], "reg_peak": w["reg_peak"], "d": d,
                "flags": {pl: q["flag"] for pl, q in w["poses"].items()},
                "d_mean": tuple(np.mean([d[pl] for pl in PLANES], 0)) if all(pl in d for pl in PLANES) else None}
    out = []
    with ThreadPoolExecutor(workers) as ex:
        for w in ex.map(one, keys):
            vals = w.pop("X", None)
            if X is not None and vals is not None:
                X[w["r0"]:w["r0"] + WINDOW_CELLS, w["c0"]:w["c0"] + WINDOW_CELLS] = vals
            out.append(w)
    return out


def refine_affine(A: np.ndarray, wins: list[Rec]) -> tuple[np.ndarray, Rec, dict]:
    """Compose the affine fit of the plane-mean offsets (page dots) into A: true(p) = A(p + delta(p)); the
    per-window residual (dots, dy dx) is the page's non-affine part."""
    ok = [w for w in wins if w.get("d_mean") is not None]
    p = np.array([(w["xd"], w["yd"]) for w in ok], float)
    d = np.array([w["d_mean"][::-1] for w in ok], float)                           # (dx, dy)
    D, rms, qrms, res = fit_affine(p, d)
    T = np.eye(3)
    T[:2, :2], T[:2, 2] = np.eye(2) + D[:, :2], D[:, 2] * DOT_MM
    return ((np.vstack([A, [0, 0, 1]]) @ T)[:2],
            {"windows": len(ok), "offset_median_dx_dy_dots": np.median(d, 0).tolist(), "residual_rms_dots": rms,
             "residual_quadratic_rms_dots": qrms},
            {(w["r0"], w["c0"]): (float(r[1]), float(r[0])) for w, r in zip(ok, res)})


def prior_field(wins: list[Rec], rs: list[int], cs: list[int]) -> dict:
    """Per window the median plane-mean offset over its 3 x 3 window neighbourhood (5 x 5 where that is empty,
    else zero)."""
    D = np.full((2, len(rs) + 4, len(cs) + 4), np.nan)
    ri, ci = {r: i for i, r in enumerate(rs)}, {c: j for j, c in enumerate(cs)}
    for w in wins:
        if w.get("d_mean") is not None:
            D[:, ri[w["r0"]] + 2, ci[w["c0"]] + 2] = w["d_mean"]
    n, m = len(rs), len(cs)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)            # all-NaN neighbourhoods
        med = {k: np.nanmedian(np.stack([D[:, 2 + a:2 + a + n, 2 + b:2 + b + m] for a in range(-k, k + 1)
                                         for b in range(-k, k + 1)]), 0) for k in (1, 2)}
    P = np.nan_to_num(np.where(np.isnan(med[1]), med[2], med[1]))
    return {(r, c): (float(P[0, i, j]), float(P[1, i, j])) for i, r in enumerate(rs) for j, c in enumerate(cs)}


def plane_geometry(A: np.ndarray, wins: list[Rec], sub: int) -> Rec:
    """Per plane the affine page dot (y, x) -> scan px (row, col) from the "ok" window poses; flag counts."""
    out: Rec = {}
    for pl in PLANES:
        src = np.array([(w["yd"], w["xd"]) for w in wins if pl in w.get("d", {})], float)
        dd = np.array([w["d"][pl] for w in wins if pl in w.get("d", {})], float)
        c, r = to_scan(A, src[:, 1] + dd[:, 1], src[:, 0] + dd[:, 0])
        aff, rms, qrms, _ = fit_affine(src, np.column_stack([r, c]))
        flags = dict(Counter(w.get("flags", {}).get(pl, "absent") for w in wins))
        out[pl] = {"windows_ok": len(src), "flags": flags, "affine_dots_yx_to_px_rowcol": aff.tolist(),
                   **axes(aff[1, 1], aff[0, 1], aff[1, 0], aff[0, 0], sub), "affine_rms_px": rms, "quadratic_rms_px": qrms}
    return out


def window_table(wins: list[Rec], resid: dict) -> dict[str, np.ndarray]:
    """Per window: centre cell (r, c), M - C, Y - C and the non-affine residual (dy, dx dots; NaN when absent)."""
    nan2 = (np.nan, np.nan)

    def diff(w: Rec, pl: str) -> tuple[float, float]:
        d = w.get("d", {})
        return tuple(np.subtract(d[pl], d["C"])) if pl in d and "C" in d else nan2
    ws = [w for w in wins if "skipped" not in w]
    return {"rc": np.array([(w["r0"] + WINDOW_CELLS / 2, w["c0"] + WINDOW_CELLS / 2) for w in ws]),
            "MC": np.array([diff(w, "M") for w in ws]), "YC": np.array([diff(w, "Y") for w in ws]),
            "res": np.array([resid.get((w["r0"], w["c0"]), nan2) for w in ws])}


def offsets(wt: dict[str, np.ndarray]) -> Rec:
    out = {}
    for k in ("MC", "YC"):
        d = wt[k][np.isfinite(wt[k]).all(1)]
        out[k] = {"windows": len(d), "median_dy_dx": np.median(d, 0).tolist(), "p10_dy_dx": np.percentile(d, 10, 0).tolist(),
                  "p90_dy_dx": np.percentile(d, 90, 0).tolist(), "abs_median": float(np.median(np.hypot(*d.T)))}
    return out


# ---------------------------------------------------------------- cells

def colour_table(X: np.ndarray, cls: np.ndarray, white: np.ndarray) -> Rec:
    ok = np.isfinite(X).all(-1)
    out = {}
    for s, nm in enumerate(STATE_NAMES):
        v = X[ok & (cls == s)].astype(np.float64)
        mu = v.mean(0)
        out[nm] = {"n": int(len(v)), "mean_rgb": mu.tolist(), "sd_rgb": v.std(0).tolist(),
                   "density_rgb": (-np.log10(np.maximum(mu, 1.0) / np.maximum(white, 1.0))).tolist()}
    return out


PROFILE_HEAD = ["axis", "slice", "cell_from", "cell_to", "mm_from", "mm_to", "n_read", "cell_err_pct", "C_err_pct",
                "M_err_pct", "Y_err_pct", "W_to_ink_pct", "mean_R", "mean_G", "mean_B", "MC_dy_dots", "MC_dx_dots",
                "YC_dy_dots", "YC_dx_dots", "nonaffine_dy_dots", "nonaffine_dx_dots", "windows"]


def slice_rows(axis: str, page: Rec, pred: np.ndarray, X: np.ndarray, wt: dict[str, np.ndarray]) -> list[list[Any]]:
    """profiles.csv rows along `axis` (x = cell columns, y = cell rows): cells and windows (by centre) per slice."""
    k = 1 if axis == "x" else 0
    size, o, cd = page["cols"] if k else page["rows"], page["origin_yx"][k], page["cell_dots"]
    edges = np.round(np.linspace(0, size, N_SLICES + 1)).astype(int)
    rows = []
    for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        sl = (slice(None), slice(a, b)) if axis == "x" else (slice(a, b), slice(None))
        c, p, x = page["cls"][sl], pred[sl], X[sl]
        ok = p >= 0
        y, q = c[ok], p[ok]
        pe = [100 * float((PLANES_OF_CLASS[y][:, j] != PLANES_OF_CLASS[q][:, j]).mean()) for j in range(3)]
        sel = (wt["rc"][:, k] >= a) & (wt["rc"][:, k] < b)
        meds = [float(np.nanmedian(wt[t][sel, j])) if np.isfinite(wt[t][sel, j]).any() else float("nan")
                for t in ("MC", "YC", "res") for j in (0, 1)]
        rows.append([axis, i, int(a), int(b), (o + a * cd) * DOT_MM, (o + b * cd) * DOT_MM, int(ok.sum()),
                     100 * float((y != q).mean()), *pe, 100 * float((q[y == 0] != 0).mean()),
                     *np.nanmean(x[ok], 0).tolist(), *meds, int(sel.sum())])
    return rows


def tile_map(cls: np.ndarray, pred: np.ndarray, tiles_yx: tuple[int, int], path: Path, title: str) -> Rec:
    ty, tx = tiles_yx
    e = np.where(pred >= 0, (cls != pred).astype(np.float64), np.nan)
    err = 100 * np.nanmean(e.reshape(ty, TILE_CELLS, tx, TILE_CELLS), axis=(1, 3))
    vmax, s = float(np.nanmax(err)), 12
    g = np.where(np.isfinite(err), 255 * (1 - np.clip(err / max(vmax, 1e-9), 0, 1)), 128).astype(np.uint8)
    im = Image.new("L", (tx * s + 20, ty * s + 40), 255)
    im.paste(Image.fromarray(np.kron(g, np.ones((s, s), np.uint8))), (10, 10))
    ImageDraw.Draw(im).text((10, ty * s + 16), f"{title}: tile cell error, white 0 % .. black {vmax:.2f} % (linear); "
                                               f"median {np.nanmedian(err):.2f} %", fill=0, font=_font(12))
    im.save(path)
    order = np.argsort(-np.nan_to_num(err), axis=None)[:8]
    return {"tile_err_pct_median": float(np.nanmedian(err)), "tile_err_pct_p90": float(np.nanpercentile(err, 90)),
            "tile_err_pct_max": vmax, "tile_err_pct_min": float(np.nanmin(err)),
            "worst_tiles_ty_tx_pct": [[int(i // tx), int(i % tx), float(err.flat[i])] for i in order],
            "tile_err_pct": np.round(err, 3).tolist()}


def profiles_png(rows: list[list[Any]], path: Path, title: str) -> None:
    """Two panels (x, y): cell error (black) and the C, M, Y plane errors per slice, page mm along the axis."""
    W, H, L, T, B = 560, 300, 50, 30, 30
    im = Image.new("RGB", (2 * W, H + 10), "white")
    d, f = ImageDraw.Draw(im), _font(11)
    for k, ax in enumerate(("x", "y")):
        rs = [r for r in rows if r[0] == ax]
        x0, x1, ymax = rs[0][4], rs[-1][5], 1.1 * max(r[c] for r in rs for c in (7, 8, 9, 10))

        def px(x: float, y: float) -> tuple[float, float]:
            return k * W + L + (x - x0) / (x1 - x0) * (W - L - 20), T + (1 - y / ymax) * (H - T - B)
        d.rectangle([px(x0, ymax), px(x1, 0)], outline=(150, 150, 150))
        for c, rgb in ((7, (0, 0, 0)), (8, (0, 160, 220)), (9, (220, 0, 160)), (10, (200, 160, 0))):
            d.line([px(0.5 * (r[4] + r[5]), r[c]) for r in rs], fill=rgb, width=2)
        d.text((k * W + L, 8), f"{title} {ax}: cell error (black), C, M, Y plane error, % vs page mm", fill="black", font=f)
        for v in np.linspace(0, ymax, 5):
            d.text((k * W + 4, px(x0, v)[1] - 6), f"{v:.1f}", fill="black", font=f)
        for v in np.linspace(x0, x1, 6):
            d.text((px(v, 0)[0] - 10, H - B + 6), f"{v:.0f}", fill="black", font=f)
    im.save(path)


# ---------------------------------------------------------------- drivers

def run(scan_path: Path, manifest: Path, gt: Path, out: Path, workers: int) -> Rec:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    page = load_page(manifest, gt)
    cls, cd = page["cls"], page["cell_dots"]
    print(f"{page['format_id']}: {page['rows']} x {page['cols']} cells at {cd} dots, origin (y, x) {page['origin_yx']} "
          f"dots, tiles {page['tiles_yx']}; states "
          + " ".join(f"{n} {int((cls == s).sum())}" for s, n in enumerate(STATE_NAMES)))
    scan = Scan(scan_path)
    sub = sub_px_per_dot(scan.dpi, DPI)
    seed = coarse_seed(scan, page)
    rs, cs = window_starts(page["rows"], WINDOW_CELLS), window_starts(page["cols"], WINDOW_CELLS)
    centre = [(rs[len(rs) // 2 + a], cs[len(cs) // 2 + b]) for a in (-1, 0, 1) for b in (-1, 1)]
    peaks = {k: float(np.median([w.get("reg_peak", 0.0) for w in read_windows(scan, A, page, page_white(scan, A, page),
                                                                              sub, centre, workers)]))
             for k, A in seed["candidates"].items()}
    orient = max(peaks, key=peaks.get)
    A = seed["candidates"][orient]
    white = page_white(scan, A, page)
    show(f"orientation {orient}; median OR-ed peak at the centre", peaks)
    show("page white RGB", white)
    keys = [(r, c) for r in rs for c in cs]
    X = np.full((page["rows"], page["cols"], 3), np.nan, np.float32)
    passes, wins = [], []
    for k in range(2):
        t1 = time.time()
        wins = read_windows(scan, A, page, white, sub, keys, workers, X, prior_field(wins, rs, cs) if k else None)
        passes.append({"pass": k + 1, "seconds": time.time() - t1, "skipped": sum("skipped" in w for w in wins),
                       "or_below_bar": sum(not w.get("reg_ok", True) for w in wins),
                       "or_on_edge": sum(bool(w.get("reg_edge")) for w in wins),
                       "all_planes_ok": sum(w.get("d_mean") is not None for w in wins),
                       "cell_err_pct": 100 * band_metrics(cls, classify_band(X, cls))["state_err"]})
        show("window pass", passes[-1], 1)
    A_fin, fin, resid = refine_affine(A, wins)
    page_geo, planes = affine_info(A_fin, scan), plane_geometry(A, wins, sub)
    wt = window_table(wins, resid)
    offs = offsets(wt)
    show("page affine (mm -> col, row)", page_geo, 5)
    show("page non-affine residual (dots)", fin)
    for pl, g in planes.items():
        show(f"plane {pl}", g, 4)
    show("offsets vs C (dots)", offs)
    pred = classify_band(X, cls)
    met = band_metrics(cls, pred)
    conf = np.array(met["confusion"])
    table = colour_table(X, cls, white)
    wcont = {"W_to_pct": {STATE_NAMES[j]: 100 * conf[0, j] / conf[0].sum() for j in (1, 2, 3)},
             "share_of_errors_on_W_cells_pct": 100 * (conf[0].sum() - conf[0, 0]) / max(conf.sum() - np.trace(conf), 1)}
    print(f"cell error {100 * met['state_err']:.3f} % over {met['n_read']} of {met['n_cells']} cells; per plane "
          + " ".join(f"{p} {100 * v:.3f} %" for p, v in met["plane_err"].items()) + "; per state "
          + " ".join(f"{s} {100 * v:.2f} %" for s, v in met["per_state_err"].items() if v is not None))
    show(f"confusion (rows true W C M Y, columns decided) {met['confusion']}; W contamination", wcont)
    for s, v in table.items():
        show(f"colour table {s}", v)
    tiles = tile_map(cls, pred, page["tiles_yx"], out / "tile_error_map.png", out.name)
    show("tiles", {k: v for k, v in tiles.items() if k != "tile_err_pct"})
    prows = slice_rows("x", page, pred, X, wt) + slice_rows("y", page, pred, X, wt)
    with open(out / "profiles.csv", "w", newline="") as fh:
        csv.writer(fh).writerows([PROFILE_HEAD] + [[round(v, 4) if isinstance(v, float) else v for v in r] for r in prows])
    profiles_png(prows, out / "profiles.png", out.name)
    for ax in ("x", "y"):
        for j in (7, 8, 9, 10, 11, 15, 16, 17, 18, 19, 20):
            nm = PROFILE_HEAD[j]
            print(f"{ax} profile {nm}: " + " ".join(f"{r[j]:.2f}" for r in prows if r[0] == ax))
    with open(out / "confusion.csv", "w", newline="") as fh:
        csv.writer(fh).writerows([["true\\decided", *STATE_NAMES, *(f"{s}_row_pct" for s in STATE_NAMES)]] + [
            [nm, *conf[s].tolist(), *(round(100 * v / conf[s].sum(), 4) for v in conf[s])] for s, nm in enumerate(STATE_NAMES)])
    del X
    print("screening:")
    fam = screening(scan, A_fin, page_boxes(field_box_dots(page)), cd * sub, page_geo["rotation_deg"], sub)
    (out / "families.json").write_text(json.dumps(jsonable(fam), indent=1))
    print_families(fam)
    summary = {"scan": str(scan_path), "manifest": str(manifest), "gt": str(gt), "format_id": page["format_id"],
               "cells_yx": [page["rows"], page["cols"]], "cell_dots": cd, "origin_dots_yx": list(page["origin_yx"]),
               "tiles_yx": list(page["tiles_yx"]), "rgb_solid": page["rgb_solid"], "px_per_dot": sub,
               "seed": {k: v for k, v in seed.items() if k != "candidates"}, "orientation": orient,
               "orientation_peaks": peaks, "window_passes": passes, "nonaffine": fin,
               "page_affine": page_geo, "page_white_rgb": white.tolist(), "planes": planes, "offsets_dots": offs, **met,
               "colour_table": table, "W_contamination": wcont, "tiles": tiles,
               "families": {k: fam[k] for k in ("summary_local", "mean_power_whole", "mean_power_whole_by_angle",
                                                "Y213_in_Y_slice_median_over_boxes", "slice_x_mm")},
               "seconds": time.time() - t0}
    (out / "summary.json").write_text(json.dumps(jsonable(summary), indent=1))
    print(f"wrote {out}: summary.json confusion.csv tile_error_map.png profiles.csv profiles.png families.json "
          f"({time.time() - t0:.0f} s)")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", required=True, type=Path, help="2400 dpi RGB TIFF of the printed page")
    ap.add_argument("--manifest", required=True, type=Path, help="the emitter's manifest JSON")
    ap.add_argument("--gt", required=True, type=Path, help="the emitter's page000_gt.npy")
    ap.add_argument("--out", required=True, type=Path, help="output directory")
    ap.add_argument("--workers", type=int, default=8, help="window-reading threads")
    a = ap.parse_args()
    run(a.scan, a.manifest, a.gt, a.out, a.workers)

if __name__ == "__main__":
    main()

"""analyze_ores.py — score a scanned ORES-1 sheet and emit the
resolution-unlock verdict.

Runs AFTER the office print + a home/known-scanner scan. Registers on the four
chiral corner marks, samples every field, and for each REQUESTED-grid field
compares its raw BER to its own 600-equivalent CONTROL on the same sheet:

  UNLOCKED  requested-grid field decodes within ~1.5x of its 600 control
  COLLAPSED requested-grid BER >= COLLAPSE_BER (~the PS-path alias floor)
  MARGINAL  in between

The 600 controls are a genuine 600 grid and must always decode; if they do
not, the scan/registration is bad and the verdict is withheld.

Pre-registered decision rule (frozen here BEFORE any office scan exists):
  CONTROL_MAX   = 0.06   a 600 control above this ⇒ scan/registration suspect
  UNLOCK_FACTOR = 1.5    grid BER <= UNLOCK_FACTOR * control BER ⇒ UNLOCKED
  COLLAPSE_BER  = 0.20   grid BER >= this ⇒ COLLAPSED (alias floor is ~0.24-0.26)
Gratings report Michelson contrast of the on/off bands (fundamental strength);
a real finer grid keeps contrast > CONTRAST_MIN = 0.15 at the requested pitch.

Usage: analyze_ores.py <scan.png> [--grid 1200|2400] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

Image.MAX_IMAGE_PIXELS = None

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "experiments" / "002-calibration-page"))
import gen_calpage  # noqa: E402

BUILD = _HERE / "build"
CONTROL_MAX = 0.06
UNLOCK_FACTOR = 1.5
UNLOCK_FLOOR = 0.03    # a grid field this clean is UNLOCKED regardless of control
COLLAPSE_BER = 0.20
CONTRAST_MIN = 0.15
GEOM_HONORED_FRAC = 0.75   # device_dpi >= this * requested_dpi => grid was actually imaged finer
MIN_PX_PER_CELL = 2.5      # below this the SCAN cannot resolve the cell (verdict withheld)


def _otsu(x: np.ndarray) -> float:
    """Otsu threshold on a flat array. Robust to any ink fraction, unlike a
    median (which collapses to a mode value for a clean bimodal ~50% field)."""
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-9:
        return (lo + hi) / 2.0
    hist, edges = np.histogram(x, bins=256, range=(lo, hi))
    p = hist.astype(np.float64) / hist.sum()
    centers = (edges[:-1] + edges[1:]) / 2.0
    w0 = np.cumsum(p); w1 = 1.0 - w0
    mu = float(np.sum(p * centers))
    mu0 = np.cumsum(p * centers)
    m0 = mu0 / np.clip(w0, 1e-12, None)
    m1 = (mu - mu0) / np.clip(w1, 1e-12, None)
    var_b = w0 * w1 * (m0 - m1) ** 2
    return float(centers[int(np.argmax(var_b))])


def load_grey(path: str) -> np.ndarray:
    """Ink-is-large float array in [0,1] (1 = full ink)."""
    a = np.asarray(Image.open(path).convert("L")).astype(np.float64)
    return 1.0 - a / 255.0


def _by_quadrant(pts: np.ndarray) -> dict:
    """Assign points to page corners by x±y extremes. NOTE: resolves TL/TR/BR/BL
    for a near-UPRIGHT scan only — it does NOT read the chiral satellite counts,
    so a 180deg/mirrored scan is silently mis-assigned (GT then mismatches ->
    ~50% -> SUSPECT). Scan upright; M1 upgrade = route through cal_core.register
    (brute-forces the 8 orientations from satellite counts)."""
    return {"TL": pts[np.argmin(pts[:, 0] + pts[:, 1])],
            "BR": pts[np.argmax(pts[:, 0] + pts[:, 1])],
            "TR": pts[np.argmax(pts[:, 0] - pts[:, 1])],
            "BL": pts[np.argmin(pts[:, 0] - pts[:, 1])]}


def register(grey: np.ndarray, manifest: dict) -> np.ndarray:
    """Affine (dots -> px) 2x3 [[a,b,tx],[c,d,ty]] from the 4 corner crosses.

    The corner marks are the only ISOLATED, low-fill (cross ~6-9% ink),
    ~123-dot-square connected components; the dense PN/grating fields are one
    huge ~50%-fill component each. Label components, keep the mark-shaped ones,
    take their centroids by quadrant, least-squares fit the affine. Robust for
    near-upright scans of our own sheets (verdict is coarse, not sub-dot)."""
    from scipy.ndimage import label, find_objects, center_of_mass

    corners = [f for f in manifest["fields"] if f["kind"] == "corner_mark"]
    pw, ph = manifest["page_w_dots"], manifest["page_h_dots"]
    ink = grey > (0.5 * grey.max())
    ys, xs = np.where(ink)
    scale = (((xs.max() - xs.min()) / pw) + ((ys.max() - ys.min()) / ph)) / 2.0
    side = 123 * scale

    lab, n = label(ink)
    slices = find_objects(lab)
    cand = []  # (centroid_x, centroid_y)
    for i, sl in enumerate(slices, start=1):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        comp = lab[sl] == i
        fill = comp.mean()
        # mark-shaped: roughly `side` square, cross-sparse fill, not a field
        if (0.6 * side < h < 1.6 * side and 0.6 * side < w < 1.6 * side
                and 0.02 < fill < 0.22):
            cy, cx = center_of_mass(comp)
            cand.append((sl[1].start + cx, sl[0].start + cy))
    if len(cand) < 4:
        raise RuntimeError(f"found {len(cand)} corner-mark candidates (need 4)")
    cand = np.array(cand, float)
    # if >4 candidates, keep the 4 nearest the ink-bbox corners
    if len(cand) > 4:
        bbox = _by_quadrant(np.array([[xs.min(), ys.min()], [xs.max(), ys.max()],
                                      [xs.max(), ys.min()], [xs.min(), ys.max()]]))
        chosen = []
        for k in ("TL", "TR", "BR", "BL"):
            d = np.hypot(cand[:, 0] - bbox[k][0], cand[:, 1] - bbox[k][1])
            chosen.append(cand[int(np.argmin(d))])
        cand = np.array(chosen)

    det = _by_quadrant(cand)
    man = _by_quadrant(np.array([[c["cx_dots"], c["cy_dots"]] for c in corners], float))
    S = np.array([man[k] for k in ("TL", "TR", "BR", "BL")])
    D = np.array([det[k] for k in ("TL", "TR", "BR", "BL")])
    A = np.hstack([S, np.ones((len(S), 1))])           # [cx cy 1]
    coef_x, *_ = np.linalg.lstsq(A, D[:, 0], rcond=None)
    coef_y, *_ = np.linalg.lstsq(A, D[:, 1], rcond=None)
    return np.array([coef_x, coef_y])                  # rows map [cx,cy,1]->px


def _sample_grid(grey: np.ndarray, coef: np.ndarray, cx: np.ndarray,
                 cy: np.ndarray) -> np.ndarray:
    """Bilinear-sample `grey` at dot-space points (cx, cy) mapped through the
    affine. Bilinear (not nearest+round) avoids half-integer rounding jitter
    that corrupts 2-3 px cells."""
    px = coef[0, 0] * cx + coef[0, 1] * cy + coef[0, 2]
    py = coef[1, 0] * cx + coef[1, 1] * cy + coef[1, 2]
    return map_coordinates(grey, [py.ravel(), px.ravel()], order=1,
                           mode="nearest").reshape(cx.shape)


def cell_means(grey: np.ndarray, coef: np.ndarray, f: dict) -> np.ndarray:
    """Per-cell mean: bilinear-sample every DOT centre, then block-mean the
    cp x cp dots of each cell. The block-mean washes out the single
    cell-boundary dot whose bilinear tap blends into the neighbour, so even
    2-3 px cells recover cleanly after Otsu."""
    n, cp = f["n_cells"], f["cell_px"]
    D = n * cp
    ii, jj = np.mgrid[0:D, 0:D].astype(np.float64)
    # sample AT the dot coordinate (the affine maps dot->its pixel); adding a
    # half-dot "centre" offset lands on pixel boundaries and 50/50-blurs.
    dots = _sample_grid(grey, coef, f["x_dots"] + jj, f["y_dots"] + ii)
    return dots.reshape(n, cp, n, cp).mean(axis=(1, 3))


def score_pn(grey, coef, f) -> dict:
    n = f["n_cells"]
    means = cell_means(grey, coef, f)
    hard = (means > _otsu(means)).astype(np.uint8)
    gt = np.load(BUILD / f["gt_file"])[:n, :n]
    ber = float(np.mean(hard != gt))
    ber = min(ber, 1.0 - ber)  # polarity-agnostic
    null = float(np.mean(hard != np.roll(gt, 3, axis=0)))
    return {"ber": ber, "null": min(null, 1 - null), "n_cells": n * n}


def score_grating(grey, coef, f) -> dict:
    """Modulation depth of the bar pattern on the RAW pixel crop (no dot
    resampling — bilinear at half-dot centres would wash out the 1-on-1-off
    Nyquist pattern). Percentile-based so it is robust to scanner blur/noise:
    a resolved finer grid keeps depth high; a closed/aliased one collapses."""
    corners_dot = np.array([[f["x_dots"], f["y_dots"]],
                            [f["x_dots"] + f["w_dots"], f["y_dots"]],
                            [f["x_dots"], f["y_dots"] + f["h_dots"]],
                            [f["x_dots"] + f["w_dots"], f["y_dots"] + f["h_dots"]]], float)
    px = coef[0, 0] * corners_dot[:, 0] + coef[0, 1] * corners_dot[:, 1] + coef[0, 2]
    py = coef[1, 0] * corners_dot[:, 0] + coef[1, 1] * corners_dot[:, 1] + coef[1, 2]
    r0, r1 = int(py.min()), int(py.max()); c0, c1 = int(px.min()), int(px.max())
    r0 = max(0, r0); c0 = max(0, c0)
    crop = grey[r0:r1, c0:c1]
    if crop.size == 0:
        return {"contrast": 0.0}
    axis = 0 if f["horizontal"] else 1        # bars vary DOWN rows (H) / across cols (V)
    prof = crop.mean(axis=1 - axis)
    hi = float(np.percentile(prof, 90)); lo = float(np.percentile(prof, 10))
    return {"contrast": abs((hi - lo) / (hi + lo + 1e-9))}


def affine_scale(coef: np.ndarray) -> float:
    """Scan pixels per grid-dot from the fitted affine (mean of the two axis
    gains). This is the ABSOLUTE-scale signal the BER-only verdict was blind
    to: it tells us how big a grid-dot printed, not just whether cells decode."""
    sx = float(np.hypot(coef[0, 0], coef[0, 1]))
    sy = float(np.hypot(coef[1, 0], coef[1, 1]))
    return (sx + sy) / 2.0


def verdict_pn(grid_ber: float, ctrl_ber: float, cell_dots: int,
               px_per_dot: float, device_dpi: float | None,
               requested_dpi: int) -> str:
    """Verdict for one requested-grid field. The ORDER matters: geometry
    (was the grid actually imaged finer?) is checked BEFORE the BER, because a
    field that printed at a COARSER device grid decodes fine — it is just
    physically bigger, i.e. SCALED-not-denser, NOT an unlock (measured on the
    AltaLink: PCL *tR ignored, imaged at 600 -> 1200 content 2x oversize)."""
    if ctrl_ber > CONTROL_MAX:
        return "SUSPECT(control failed)"
    # (1) absolute-scale gate: did the printer actually image at the requested grid?
    if device_dpi is not None and device_dpi < GEOM_HONORED_FRAC * requested_dpi:
        return f"SCALED@~{int(round(device_dpi))}dpi(no density gain)"
    # (2) scan-adequacy gate: can THIS scan resolve the requested-grid cell?
    if px_per_dot * cell_dots < MIN_PX_PER_CELL:
        return f"INDETERMINATE(scan {px_per_dot * cell_dots:.1f}px/cell)"
    # (3) BER, now trustworthy as a density statement
    if grid_ber >= COLLAPSE_BER:
        return "COLLAPSED"
    if grid_ber <= max(UNLOCK_FACTOR * ctrl_ber, UNLOCK_FLOOR):
        return "UNLOCKED"
    return "MARGINAL"


def analyze(scan_path: str, grid: int, scan_dpi: float | None = None) -> dict:
    man = json.loads((BUILD / "ores_manifest.json").read_text())["manifests"][str(grid)]
    grey = load_grey(scan_path)
    coef = register(grey, man)
    by = {f["name"]: f for f in man["fields"]}

    px_per_dot = affine_scale(coef)
    # inferred device (marking) resolution: a grid-dot occupies 1/device_dpi
    # inch, seen as px_per_dot px at scan_dpi -> device_dpi = scan_dpi/px_per_dot.
    device_dpi = (scan_dpi / px_per_dot) if scan_dpi else None
    geom = {"px_per_grid_dot": round(px_per_dot, 3),
            "scan_dpi": scan_dpi,
            "device_dpi_inferred": round(device_dpi, 1) if device_dpi else None,
            "grid_honored": (device_dpi >= GEOM_HONORED_FRAC * grid) if device_dpi else None}

    pn = {}
    for name in ("pn_c3_grid", "pn_c3_600", "pn_c2_grid", "pn_c2_600"):
        pn[name] = score_pn(grey, coef, by[name])
    gr = {}
    for f in man["fields"]:
        if f["kind"] == "grating":
            gr[f["name"]] = {**score_grating(grey, coef, f), "grid": f["grid"]}

    out = {"scan": scan_path, "requested_dpi": grid, "geometry": geom,
           "pn": pn, "gratings": gr,
           "verdicts": {
               "c3": verdict_pn(pn["pn_c3_grid"]["ber"], pn["pn_c3_600"]["ber"],
                                by["pn_c3_grid"]["cell_px"], px_per_dot, device_dpi, grid),
               "c2": verdict_pn(pn["pn_c2_grid"]["ber"], pn["pn_c2_600"]["ber"],
                                by["pn_c2_grid"]["cell_px"], px_per_dot, device_dpi, grid),
           }}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="score a scanned ORES-1 sheet")
    ap.add_argument("scan")
    ap.add_argument("--grid", type=int, default=1200, choices=(1200, 2400))
    ap.add_argument("--scan-dpi", type=float, default=None,
                    help="the KNOWN scanner resolution (e.g. 4800 for the Canon, "
                         "1200 for the home flatbed). Required to verify the grid "
                         "was actually imaged finer vs merely scaled up.")
    ap.add_argument("--json")
    a = ap.parse_args()
    r = analyze(a.scan, a.grid, a.scan_dpi)
    print(f"ORES-1  {a.scan}  requested grid {a.grid}")
    g = r["geometry"]
    if g["device_dpi_inferred"] is not None:
        flag = "grid IMAGED FINER" if g["grid_honored"] else "SCALED UP (not denser)"
        print(f"  geometry: {g['px_per_grid_dot']}px/grid-dot @ scan {int(a.scan_dpi)}dpi "
              f"-> device ~{g['device_dpi_inferred']}dpi  [{flag}]")
    else:
        print("  geometry: --scan-dpi NOT given -> cannot tell a real unlock from a "
              "scaled-up print (a decoded field may be scaled-not-denser); verdicts BER-only")
    for k in ("pn_c3_grid", "pn_c3_600", "pn_c2_grid", "pn_c2_600"):
        v = r["pn"][k]
        print(f"  {k:12s} BER {v['ber']*100:6.2f}%  null {v['null']*100:5.1f}%  ({v['n_cells']} cells)")
    print(f"  VERDICT  c3@{a.grid}: {r['verdicts']['c3']}   "
          f"c2@{a.grid}: {r['verdicts']['c2']}")
    g1 = [v['contrast'] for k, v in r["gratings"].items() if k.startswith("g1_grid")]
    print(f"  1-on-1-off @{a.grid} contrast (H,V): "
          f"{', '.join(f'{c:.3f}' for c in g1)}  (finer-grid alive if > {CONTRAST_MIN})")
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1))
        print(f"  -> {a.json}")


if __name__ == "__main__":
    main()

"""e041 — where across the page does the engine screen? A per-band screen profile along x.

For a sheet built of full-width bands (S14 and later), cut each band into columns of 256 scan px (2.7 mm
at 2400 dpi, step 128 px; at --scan-dpi D every px size scales by D / 2400 — window N, step, the band-edge
insets of 24 / 8 px — so the window stays 2.7 mm, and the lattice frequency in cycles per px is lpi / D; at
2400 the output is byte-identical to the instrument before the dpi axis) and, in windows stacked down the
band, score the engine's known screen lattices
by their peak over the ring median at the known frequency AND angle (a cell grid cannot produce these
peaks): 165 lpi at +-14 deg, 188 lpi at +-71/+-19 deg, 212 lpi at +-45 deg, each in R, G and B. The score
of a column is the median over its windows. A pixel-shuffled copy of every 8th window gives the noise
floor. Bands are read from the manifest; the page is placed by the five fiducials.

    PYTHONPATH=src:. env/bin/python -m measure.e041_band_screen \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S14/captures/S14-canon-2400rgb.tiff \
        --manifest <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S14/jobs/S14-ps-scale.manifest.json --out build/e041/band-screen
    (add --scan-dpi 4800 for a 4800 dpi scan)

Outputs: <tag>-columns.csv (band, x_mm, per lattice and channel the column score, mean R/G/B),
<tag>-heat-<lattice>.png (bands down, x across; bright = screened) and a printed profile per band.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from measure.e041_probe_readout import Scan, fit_page

Image.MAX_IMAGE_PIXELS = None
DPI = 2400.0                            # the default scan dpi; the px sizes below are at DPI
N = 256
STEP = 128
INSET_ROW_PX, INSET_COL_PX = 24, 8      # band-edge insets of the window grid
LATTICES = {"165": (165.0, (14, -14, 166, -166)),
            "188": (188.0, (71, -71, 19, -19, 109, -109, 161, -161)),
            "212": (212.0, (45, -45, 135, -135))}
DOT_MM = 25.4 / 600


def spectrum(w: np.ndarray, win: np.ndarray) -> np.ndarray:
    p = w.astype(np.float64)
    p -= p.mean()
    return np.abs(np.fft.fftshift(np.fft.fft2(p * win))) ** 2


def lattice_score(S: np.ndarray, lpi: float, angles: tuple[int, ...], geo: tuple, dpi: float = DPI) -> float:
    fy, fx, R, binw = geo
    f = lpi / dpi
    ring = np.abs(R - f) < 1.5 * binw
    med = float(np.median(S[ring])) + 1e-12
    pk = 0.0
    for a in angles:
        ty, tx = f * np.sin(np.radians(a)), f * np.cos(np.radians(a))
        m = (np.abs(fy - ty) <= 1.1 * binw) & (np.abs(fx - tx) <= 1.1 * binw)
        pk = max(pk, float(S[m].max()))
    return pk / med


def scaled_px(px_at_2400: int, dpi: float) -> int:
    """A px size given at 2400 dpi, at the scan's dpi (the same mm)."""
    return int(round(px_at_2400 * dpi / DPI))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--scan-dpi", type=float, default=DPI, help="the scan's resolution (2400 or 4800)")
    args = ap.parse_args()
    dpi = args.scan_dpi
    n_px, step_px = scaled_px(N, dpi), scaled_px(STEP, dpi)
    in_r, in_c = scaled_px(INSET_ROW_PX, dpi), scaled_px(INSET_COL_PX, dpi)
    man = json.load(open(args.manifest))
    tag = args.tag or man.get("tag", "sheet")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fid_man = {"fiducials": [{"id": f["id"], "x_mm": f["x_mm"], "y_mm": f["y_mm"], "w_mm": f["w_mm"],
                              "h_mm": f["h_mm"]} for f in man["fiducials"]]}
    # the path alone at the default: the experiments/041 verifiers' in-memory Scan stand-ins take only that
    scan = Scan(Path(args.scan)) if dpi == DPI else Scan(Path(args.scan), dpi)
    A, info = fit_page(scan, fid_man, 0.3, 0.01)
    img = scan.img
    win = np.outer(np.hanning(n_px), np.hanning(n_px))
    fr = np.fft.fftshift(np.fft.fftfreq(n_px))
    fy, fx = np.meshgrid(fr, fr, indexing="ij")
    geo = (fy, fx, np.hypot(fy, fx), 1.0 / n_px)
    rng = np.random.default_rng(0)
    rows, floor = [], []
    bands = sorted((b for b in man["bands"] if b.get("alphabet")), key=lambda b: b["y_dots"])
    first_col: dict[str, int] = {}
    for b in bands:
        x0, y0, w, h = b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]
        # band rectangle in scan px through the affine (axis-aligned to within the fitted rotation)
        c0, r0 = A @ np.array([x0 * DOT_MM, y0 * DOT_MM, 1.0])
        c1, r1 = A @ np.array([(x0 + w) * DOT_MM, (y0 + h) * DOT_MM, 1.0])
        lo_r, hi_r = int(min(r0, r1)) + in_r, int(max(r0, r1)) - in_r
        lo_c, hi_c = int(min(c0, c1)) + in_c, int(max(c0, c1)) - in_c
        ys = list(range(lo_r, hi_r - n_px, n_px // 2))
        first_col[b["name"]] = lo_c
        for k, cx in enumerate(range(lo_c, hi_c - n_px, step_px)):
            scores = {f"{lat}_{ch}": [] for lat in LATTICES for ch in "RGB"}
            means = []
            for j, cy in enumerate(ys):
                blk = img[cy:cy + n_px, cx:cx + n_px]
                means.append(blk.reshape(-1, 3).mean(0))
                for ci, ch in enumerate("RGB"):
                    S = spectrum(blk[:, :, ci], win)
                    for lat, (lpi, angs) in LATTICES.items():
                        scores[f"{lat}_{ch}"].append(lattice_score(S, lpi, angs, geo, dpi))
                if (k + j) % 8 == 0:
                    g = blk[:, :, 1].ravel().copy()
                    rng.shuffle(g)
                    S = spectrum(g.reshape(n_px, n_px), win)
                    floor.append(max(lattice_score(S, lpi, angs, geo, dpi)
                                     for lpi, angs in LATTICES.values()))
            xmm = float(np.linalg.solve(A[:, :2], np.array([cx + n_px / 2, (lo_r + hi_r) / 2]) - A[:, 2])[0])
            m = np.mean(means, axis=0)
            row = {"band": b["name"], "alphabet": b["alphabet"], "matching": b.get("matching"),
                   "x_mm": round(xmm, 2), "mean_R": round(float(m[0]), 1), "mean_G": round(float(m[1]), 1),
                   "mean_B": round(float(m[2]), 1)}
            row |= {k2: round(float(np.median(v)), 1) for k2, v in scores.items()}
            rows.append(row)
        print(f"  {b['name']} done", flush=True)
    fl = np.array(floor)
    print(f"{tag}: {len(rows)} columns over {len(bands)} bands; shuffled floor median {np.median(fl):.1f} "
          f"p98 {np.quantile(fl, .98):.1f}")
    keys = list(rows[0].keys())
    with open(out / f"{tag}-columns.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        wr.writerows(rows)
    names = [b["name"] for b in bands]
    for lat in LATTICES:
        best = {nm: [max(r[f"{lat}_R"], r[f"{lat}_G"], r[f"{lat}_B"]) for r in rows if r["band"] == nm]
                for nm in names}
        # a band that starts right of the leftmost one (S15's R5) is padded on the left by its offset in
        # columns, so the heat map's x is the page's; equal starts (S14) pad nothing
        lo = min(first_col.values())
        pad = {nm: (first_col[nm] - lo) // step_px for nm in names}
        ncol = min(pad[nm] + len(v) for nm, v in best.items())
        M = np.array([([1.0] * pad[nm] + v)[:ncol] for nm, v in best.items()])
        v = np.clip(np.log10(M) / np.log10(max(M.max(), 10)), 0, 1)
        Image.fromarray((v * 255).astype(np.uint8)).resize((ncol * 6, len(names) * 40),
                                                           Image.NEAREST).save(out / f"{tag}-heat-{lat}.png")
    xs = sorted({round(r["x_mm"] / 5) * 5 for r in rows})
    for lat in LATTICES:
        print(f"\n== lattice {lat} lpi, column score (max over R/G/B, median of windows), 5 mm bins")
        print("  band   " + " ".join(f"{x:4.0f}" for x in xs))
        for nm in names:
            cells = []
            for x in xs:
                v = [max(r[f"{lat}_R"], r[f"{lat}_G"], r[f"{lat}_B"]) for r in rows
                     if r["band"] == nm and round(r["x_mm"] / 5) * 5 == x]
                cells.append(f"{np.median(v):4.0f}" if v else "   -")
            print(f"  {nm:6s} " + " ".join(cells))
    print(json.dumps({"fit": {k: info[k] for k in ("residual_mm", "rotation_deg", "orientation")}}))


if __name__ == "__main__":
    main()

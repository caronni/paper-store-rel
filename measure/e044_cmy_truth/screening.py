"""e044 — the screening check of a printed cmy format page: is anything re-screened?  (split from readout.py
along its seam: the cell readout there, the spectra here.)

The e043 stipple instrument (measure/cmy_probe/stipples.py) applied to boxes of one size: per box and per
~SLICE_MM slice of it the locally whitened families per ink density (C = 255 - R, M = 255 - G, Y = 255 - B;
stipples.power + peak_local, the band form of families_local), the cell lattice's harmonics excluded at the page
rotation (checkerboards.lattice_exclude).  On a format page the boxes are strips of sheet 3's band height
(STRIP_DOTS, inset STRIP_INSET_Y) across the field (inset STRIP_INSET_X), so a strip reads like one of sheet 3's
whole bands and a slice like one of its 9.3 mm slices (noise 10-25, stipples.py).  Beside them the boxes' power
spectra AVERAGED and read the same way — whole, per family angle, and per slice column: a weak component that
every single box carries under its noise shows there (the averaged noise floor is lower than 10-25: read it off
the families that are not expected, e.g. dots160@42 / lines196@90).

The control (this module's CLI): sheet 3's named bands (its manifest, its readout's page fit and scan path)
through the same function — the averaged form's reference at the probe's own fit.

    PYTHONPATH=src:. env/bin/python -u -m measure.e044_cmy_truth.screening \\
        --summary <e043c readout/summary.json> --manifest <E043c manifest.json> --bands B1,B9,B11,B14 --out <dir>
Output: <out>/families-<bands>.json; the log on stdout.  readout.py calls page_boxes / screening / print_families.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_probe.checkerboards import lattice_exclude
from measure.cmy_probe.stipples import CHANNELS, FAMILIES, _grid, peak_local, power
from measure.e041_probe_readout import Scan, jsonable, sub_px_per_dot

DOT_MM = 25.4 / 600.0
STRIP_DOTS, STRIP_INSET_Y, STRIP_INSET_X, SLICE_MM = 336, 8, 24, 9.3     # sheet 3's band height, insets, slices
Box = tuple[float, float, float, float]


def page_boxes(field: tuple[int, int, int, int]) -> list[Box]:
    """Strips of STRIP_DOTS spread evenly down the field (x0, y0, x1, y1 page dots), inset."""
    x0, y0, x1, y1 = field
    ys = np.round(np.linspace(y0, y1 - STRIP_DOTS, (y1 - y0) // STRIP_DOTS)).astype(int)
    return [(x0 + STRIP_INSET_X, y + STRIP_INSET_Y, x1 - STRIP_INSET_X, y + STRIP_DOTS - STRIP_INSET_Y) for y in ys]


def screening(scan: Scan, A: np.ndarray, boxes: list[Box], period: int, rot_deg: float, sub: int) -> dict[str, Any]:
    """boxes (x0, y0, x1, y1 page dots, one width and height; A page mm -> [col, row]): per box and per slice the
    locally whitened families per ink density; the boxes' mean power read the same way, whole (per family angle
    too) and per slice column."""
    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
        P = A @ np.vstack([np.array([x0, x1, x0, x1]) * DOT_MM, np.array([y0, y0, y1, y1]) * DOT_MM, np.ones(4)])
        return (int(round(P[1].min())), int(round(P[0].min())), int(round(P[1].max())),     # corners sorted:
                int(round(P[0].max())))                                                      # a turned page too
    x0, y0, x1, y1 = boxes[0]
    n_sl = int(round((x1 - x0) * DOT_MM / SLICE_MM))
    xe0 = np.linspace(x0, x1, n_sl + 1)
    r0, c0, r1, c1 = box(*boxes[0])
    hs, ws, sw = r1 - r0, c1 - c0, int(round((x1 - x0) / n_sl * sub))
    small = ((rot_deg + 45) % 90) - 45
    ex, ex_s = lattice_exclude((hs, ws), period, rot_deg=small), lattice_exclude((hs, sw), period, rot_deg=small)
    (R, ang, _), (Rs, angs, _) = _grid(hs, ws), _grid(hs, sw)

    def fam(P: np.ndarray, r: np.ndarray, a: np.ndarray, e: np.ndarray) -> dict[str, float]:
        return {f: peak_local(P, r, a, *FAMILIES[f], dpi=scan.dpi, exclude=e) for f in FAMILIES}

    def crop(q0: int, s0: int, w: int) -> np.ndarray:
        return scan.img[q0:q0 + hs, s0:s0 + w, :3].astype(np.float64) * scan.scale255
    acc, acc_s, out = np.zeros((3, hs, ws)), np.zeros((n_sl, 3, hs, sw)), []
    for bx0, by0, bx1, by1 in boxes:
        patch, loc = crop(*box(bx0, by0, bx1, by1)[:2], ws), {}
        for k, ch in enumerate(CHANNELS):
            acc[k] += (P := power(255.0 - patch[..., k]))
            loc[ch] = fam(P, R, ang, ex)
        sl, xe = [], np.linspace(bx0, bx1, n_sl + 1)
        for i in range(n_sl):
            sp = crop(*box(xe[i], by0, xe[i + 1], by1)[:2], sw)
            sl.append({})
            for k, ch in enumerate(CHANNELS):
                acc_s[i, k] += (P := power(255.0 - sp[..., k]))
                sl[i][ch] = fam(P, Rs, angs, ex_s)
        out.append({"y_mm": float((by0 + by1) / 2 * DOT_MM), "local": loc, "slices": sl})
        print(f"  box y {out[-1]['y_mm']:6.1f} mm: Y213@45 in Y {loc['Y']['Y213@45']:6.1f} (C {loc['C']['Y213@45']:5.1f},"
              f" M {loc['M']['Y213@45']:5.1f}); 165@14 max {max(loc[c]['165@14'] for c in CHANNELS):5.1f}; 188 max "
              f"{max(loc[c]['188@71/19'] for c in CHANNELS):5.1f}; per slice Y213 in Y "
              + " ".join(f"{s['Y']['Y213@45']:.0f}" for s in sl))
    n = len(boxes)
    by_angle = {ch: {f"{f}:{a:g}": peak_local(acc[k] / n, R, ang, FAMILIES[f][0], (a,), dpi=scan.dpi, exclude=ex)
                     for f in FAMILIES for a in FAMILIES[f][1]} for k, ch in enumerate(CHANNELS)}

    def stats(v: list[float]) -> dict[str, float]:
        return {"median": float(np.nanmedian(v)), "max": float(np.nanmax(v))}
    return {"boxes_dots": [list(map(float, b)) for b in boxes], "box_shape_px": [hs, ws], "slice_shape_px": [hs, sw],
            "slice_x_mm": [[float(a * DOT_MM), float(b * DOT_MM)] for a, b in zip(xe0[:-1], xe0[1:])],
            "lattice_period_px": period, "rotation_deg_used": small,
            "summary_local": {ch: {f: {"box": stats([b["local"][ch][f] for b in out]),
                                       "slice": stats([q[ch][f] for b in out for q in b["slices"]])} for f in FAMILIES}
                              for ch in CHANNELS},
            "mean_power_whole": {ch: fam(acc[k] / n, R, ang, ex) for k, ch in enumerate(CHANNELS)},
            "mean_power_whole_by_angle": by_angle,
            "mean_power_slice_columns": [{ch: fam(acc_s[i, k] / n, Rs, angs, ex_s) for k, ch in enumerate(CHANNELS)}
                                         for i in range(n_sl)],
            "Y213_in_Y_slice_median_over_boxes": [float(np.nanmedian([b["slices"][i]["Y"]["Y213@45"] for b in out]))
                                                  for i in range(n_sl)], "boxes": out}


def print_families(fam: dict[str, Any]) -> None:
    for ch in CHANNELS:
        print(f"mean power over {len(fam['boxes'])} boxes, {ch}: "
              + "  ".join(f"{f} {v:.1f}" for f, v in fam["mean_power_whole"][ch].items())
              + "   by angle " + " ".join(f"{k} {v:.1f}" for k, v in fam["mean_power_whole_by_angle"][ch].items()))
        print(f"  boxes / slices (median/max) {ch}: " + "  ".join(
            f"{f} {s['box']['median']:.0f}/{s['box']['max']:.0f} | {s['slice']['median']:.0f}/{s['slice']['max']:.0f}"
            for f, s in fam["summary_local"][ch].items()))
    for f in ("165@14", "188@71/19", "Y213@45"):
        print(f"mean power per slice column, {f} in C/M/Y: " + " ".join(
            "/".join(f"{c[ch][f]:.0f}" for ch in CHANNELS) for c in fam["mean_power_slice_columns"]))
    print("Y213@45 in Y per slice (median over boxes): "
          + " ".join(f"{v:.0f}" for v in fam["Y213_in_Y_slice_median_over_boxes"]))


def control(summary: Path, manifest: Path, bands: list[str], out: Path) -> dict[str, Any]:
    """Sheet 3's named bands (inset as page strips are) through screening() at the probe's own page fit."""
    s, man = json.loads(summary.read_text())["scans"][0], json.loads(manifest.read_text())
    sel = [b for b in man["bands"] if b["name"] in bands]
    if {b["name"] for b in sel} != set(bands) or len({int(b.get("cell_dots", 2)) for b in sel}) != 1:
        raise SystemExit(f"bands {bands}: not all in the manifest, or of mixed cell pitch")
    scan = Scan(Path(s["scan"]))
    sub = sub_px_per_dot(scan.dpi, 600.0)
    boxes = [(b["x_dots"] + STRIP_INSET_X, b["y_dots"] + STRIP_INSET_Y, b["x_dots"] + b["w_dots"] - STRIP_INSET_X,
              b["y_dots"] + b["h_dots"] - STRIP_INSET_Y) for b in sel]
    print(f"control: {s['scan']} bands {bands} (lookups {[b.get('lookup') for b in sel]})")
    fam = screening(scan, np.asarray(s["fit"]["affine_mm_to_colrow"]), boxes, int(sel[0].get("cell_dots", 2)) * sub,
                    float(s["fit"]["rotation_deg"]), sub)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"families-{'-'.join(bands)}.json").write_text(json.dumps(jsonable({"bands": bands, **fam}), indent=1))
    print_families(fam)
    return fam


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", required=True, type=Path, help="sheet 3's readout summary.json (scan path, page fit)")
    ap.add_argument("--manifest", required=True, type=Path, help="sheet 3's manifest JSON")
    ap.add_argument("--bands", required=True, help="comma-separated band names of one cell pitch")
    ap.add_argument("--out", required=True, type=Path, help="output directory")
    a = ap.parse_args()
    control(a.summary, a.manifest, a.bands.split(","), a.out)


if __name__ == "__main__":
    main()

"""e045 — page or platen: per-plane y offsets and the common-x jumps of an e044 format page on any capture,
whatever way round it lay on the glass (045.4).

Per capture: the field's corners (e044_cmy_truth.readout.coarse_seed), the orientation by the centre windows'
OR-ed registration peak (as-is vs turned 180 deg, readout.run's rule), ROWS rows of 36-cell windows spread down
the page read twice (readout.read_windows, the second pass at readout.prior_field's prior).  Per window and
plane the offset (dy, dx printed dots) against the corner affine; reported per window column (median over the
rows): each plane's dy against its own 40-100 mm level, M - C and Y - C dy, and the drops of the plane-mean dx
between neighbouring windows larger than DROP_DOTS against the page's median step — the common-x jumps, with
their page x and the scan column of page x 0 so that page and platen positions can be compared between
captures.

    PYTHONPATH=src:. env/bin/python -m measure.e045_left_band.platen \\
        --manifest <E044-X-manifest.json> --gt <E044-X-page000_gt.npy> --scan <capture.tiff> [--scan <capture-2.tiff>] \\
        [--out <dir>]
Writes, per capture, <out>/<capture stem>-platen.csv (window column x, per-plane dy, M - C, Y - C) and
<out>/<capture stem>-platen.json (orientation, peaks, page-x-0 column, jumps); prints both.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_probe.bands import WINDOW_CELLS
from measure.e041_probe_readout import Scan, jsonable, sub_px_per_dot
from measure.e044_cmy_truth.readout import (DOT_MM, coarse_seed, load_page, page_white, prior_field, read_windows,
                                            window_starts)

ROWS = (0.2, 0.35, 0.5, 0.65, 0.8)
DROP_DOTS = 0.3
Rec = dict[str, Any]


def one_capture(scan_path: Path, page: Rec, workers: int) -> tuple[Rec, list[Rec]]:
    scan = Scan(scan_path)
    sub = sub_px_per_dot(scan.dpi, 600.0)
    seed = coarse_seed(scan, page)
    rs, cs = window_starts(page["rows"], WINDOW_CELLS), window_starts(page["cols"], WINDOW_CELLS)
    centre = [(rs[len(rs) // 2 + a], cs[len(cs) // 2 + b]) for a in (-1, 0, 1) for b in (-1, 1)]
    peaks = {k: float(np.median([w.get("reg_peak", 0.0) for w in
                                 read_windows(scan, A, page, page_white(scan, A, page), sub, centre, workers)]))
             for k, A in seed["candidates"].items()}
    orient = max(peaks, key=peaks.get)
    A = seed["candidates"][orient]
    white = page_white(scan, A, page)
    pick = [rs[int(f * (len(rs) - 1))] for f in ROWS]
    keys = [(r, c) for r in pick for c in cs]
    w1 = read_windows(scan, A, page, white, sub, keys, workers)
    w2 = read_windows(scan, A, page, white, sub, keys, workers, None, prior_field(w1, pick, cs))
    cd, ox = page["cell_dots"], page["origin_yx"][1]
    per: dict[float, dict[str, list[float]]] = {}
    for w in w2:
        if not all(pl in w.get("d", {}) for pl in "CMY"):
            continue
        x = round((ox + (w["c0"] + WINDOW_CELLS / 2) * cd) * DOT_MM, 2)
        acc = per.setdefault(x, {k: [] for k in ("C", "M", "Y", "MC", "YC", "dx", "row")})
        for pl in "CMY":
            acc[pl].append(w["d"][pl][0])
        acc["MC"].append(w["d"]["M"][0] - w["d"]["C"][0])
        acc["YC"].append(w["d"]["Y"][0] - w["d"]["C"][0])
        acc["dx"].append(float(np.mean([w["d"][pl][1] for pl in "CMY"])))
        acc["row"].append(w["r0"])
    xs = sorted(per)
    ref = {pl: {r: np.median([v for x in xs if 40 <= x < 100 for v, rr in zip(per[x][pl], per[x]["row"]) if rr == r])
                for r in pick} for pl in "CMY"}
    rows = []
    for x in xs:
        a = per[x]
        rec = {"x_mm": x, **{f"{pl}_dy": float(np.median([v - ref[pl][r] for v, r in zip(a[pl], a["row"])])) for pl in "CMY"},
               "MC_dy": float(np.median(a["MC"])), "YC_dy": float(np.median(a["YC"])), "dx_mean": float(np.median(a["dx"]))}
        rows.append(rec)
    dd = np.diff([r["dx_mean"] for r in rows])
    base = float(np.median(dd))
    jumps = [(round(0.5 * (rows[i]["x_mm"] + rows[i + 1]["x_mm"]), 2), round(float(v - base), 3))
             for i, v in enumerate(dd) if v - base < -DROP_DOTS]
    info = {"scan": str(scan_path), "orientation": orient, "orientation_peaks": peaks,
            "page_x0_scan_col": float((A @ np.array([0.0, 150.0, 1.0]))[0]), "px_per_mm": scan.px_per_mm,
            "median_dx_step_dots": base, "common_dx_jumps_page_x_mm": jumps}
    del scan
    return info, rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, type=Path, help="the e044 page manifest")
    ap.add_argument("--gt", required=True, type=Path, help="the e044 page000_gt.npy")
    ap.add_argument("--scan", required=True, type=Path, action="append", help="a capture (repeatable)")
    ap.add_argument("--out", type=Path, default=None, help="output directory (default: print only)")
    ap.add_argument("--workers", type=int, default=10, help="window-reading threads")
    a = ap.parse_args()
    page = load_page(a.manifest, a.gt)
    for s in a.scan:
        info, rows = one_capture(s, page, a.workers)
        print(json.dumps(jsonable(info)))
        for r in rows:
            if r["x_mm"] < 52 or 98 < r["x_mm"] < 128:
                print("  " + " ".join(f"{k} {v:7.2f}" for k, v in r.items()))
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / f"{s.stem}-platen.json").write_text(json.dumps(jsonable(info), indent=1))
            with open(a.out / f"{s.stem}-platen.csv", "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows([{k: round(v, 4) for k, v in r.items()} for r in rows])


if __name__ == "__main__":
    main()

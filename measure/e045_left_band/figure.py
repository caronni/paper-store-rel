"""e045 — the left band in one figure (PIL; no matplotlib in the venv): page x on one axis, two panels.

Top: each plane's y offset (printed dots, + = down the page) against its own 40-100 mm level on the same sub-window
row, median over every band per BIN_MM of x (subwindows.csv, "ok" planes) — where a plane steps.  Bottom: the c2
cell error per 1 mm pooled over the c2 bands (profile_1mm.csv), at the readout's poses (`read`, band colour table)
and at the cross-fitted sub-window poses (`finex`, slice table).  Lines are direct-labelled (the plane colours are
identity, not the only cue).  Dashed: the per-plane steps of 045.3 (C 33.5 / 109, Y 114.5 mm); short ticks under the
error panel: the scanner's common-x seams on this placement (page x SEAM0_MM + k SEAM_MM, 045.4 — platen-fixed).

    PYTHONPATH=src:. env/bin/python -m measure.e045_left_band.figure --dir <sheet3 out> --png <path>
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from measure.cmy_probe.stipples import _font

BIN_MM = 1.5
SEAM0_MM, SEAM_MM = 17.5, 18.2     # sheet 3's placement (045.4)
INK = {"C": (0, 160, 220), "M": (220, 0, 160), "Y": (180, 140, 0)}
W, H, L, R, T, GAP = 1500, 780, 70, 30, 40, 70


def plane_profiles(subs: list[dict[str, str]]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    bins = np.arange(12.0, 198.0, BIN_MM)
    acc = {p: [[] for _ in bins] for p in "CMY"}
    for b in sorted({r["band"] for r in subs}):
        rs = [r for r in subs if r["band"] == b and all(r.get(f"{p}_flag") == "ok" for p in "CMY")]
        x = np.array([float(r["x_mm"]) for r in rs])
        rows = np.array([int(r["r0"]) for r in rs])
        for p in "CMY":
            dy = np.array([float(r[f"{p}_dy"]) for r in rs])
            ref = {rr: np.median(dy[(rows == rr) & (x >= 40) & (x < 100)]) for rr in set(rows.tolist())}
            rel = dy - np.array([ref[rr] for rr in rows])
            for i, a in enumerate(bins):
                acc[p][i] += rel[(x >= a) & (x < a + BIN_MM)].tolist()
    return bins + BIN_MM / 2, {p: np.array([np.median(v) if v else np.nan for v in acc[p]]) for p in "CMY"}


def error_profiles(prof: list[dict[str, str]]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    c2 = [r for r in prof if r["cell_dots"] == "2"]
    xs = sorted({round(float(r["x0_mm"]), 2) for r in c2})
    out = {}
    for k in ("E_band_read", "E_slice_finex"):
        out[k] = np.array([np.mean([float(r[k]) for r in c2 if round(float(r["x0_mm"]), 2) == x]) for x in xs])
    return np.array(xs) + 0.5, out


def draw(dirpath: Path, png: Path) -> None:
    subs = list(csv.DictReader(open(dirpath / "subwindows.csv")))
    prof = list(csv.DictReader(open(dirpath / "profile_1mm.csv")))
    xp, dy = plane_profiles(subs)
    xe, err = error_profiles(prof)
    im = Image.new("RGB", (W, H), "white")
    d, f, fb = ImageDraw.Draw(im), _font(14), _font(16)
    x0, x1 = 10.0, 200.0
    ph = (H - T - GAP - 40) // 2
    panels = [(T, -3.0, 1.5, "plane y offset vs its own 40-100 mm level (dots; median over 15 bands)"),
              (T + ph + GAP, 0.0, 14.0, "c2 cell error per 1 mm (%; mean over 8 c2 bands)")]

    def X(v: float) -> float:
        return L + (v - x0) / (x1 - x0) * (W - L - R)
    for top, lo, hi, title in panels:
        def Y(v: float, top=top, lo=lo, hi=hi) -> float:
            return top + (1 - (v - lo) / (hi - lo)) * ph
        d.text((L, top - 26), title, fill=(20, 20, 20), font=fb)
        d.rectangle([X(x0), Y(hi), X(x1), Y(lo)], outline=(170, 170, 170))
        for v in np.arange(np.ceil(lo), hi + 1e-9, 1.0 if hi - lo < 6 else 2.0):
            d.line([X(x0), Y(v), X(x1), Y(v)], fill=(235, 235, 235))
            d.text((8, Y(v) - 8), f"{v:g}", fill=(90, 90, 90), font=f)
        for e in (33.5, 109.0, 114.5):
            for yy in np.arange(top, top + ph, 8):
                d.line([X(e), yy, X(e), yy + 4], fill=(150, 150, 150))
        if lo < 0 < hi:
            d.line([X(x0), Y(0), X(x1), Y(0)], fill=(120, 120, 120))
    top, lo, hi, _ = panels[0]
    Y0 = lambda v: top + (1 - (v - lo) / (hi - lo)) * ph  # noqa: E731
    for p in "CMY":
        pts = [(X(a), Y0(v)) for a, v in zip(xp, dy[p]) if np.isfinite(v)]
        d.line(pts, fill=INK[p], width=2)
        d.text((pts[-1][0] - 60, pts[-1][1] - 22 if p != "M" else pts[-1][1] + 6), {"C": "cyan", "M": "magenta", "Y": "yellow"}[p],
               fill=(20, 20, 20), font=f)
    top, lo, hi, _ = panels[1]
    Y1 = lambda v: top + (1 - (v - lo) / (hi - lo)) * ph  # noqa: E731
    for k, col, lab in (("E_band_read", (160, 160, 160), "readout poses"), ("E_slice_finex", (20, 20, 20), "local poses")):
        pts = [(X(a), Y1(min(v, hi))) for a, v in zip(xe, err[k])]
        d.line(pts, fill=col, width=2)
        d.text((X(150), Y1(12.5 if k == "E_band_read" else 11.0)), lab, fill=col if k != "E_band_read" else (110, 110, 110), font=f)
    top, lo, hi, _ = panels[1]
    for k in range(11):
        sx = SEAM0_MM + k * SEAM_MM
        if x0 < sx < x1:
            d.line([X(sx), top + ph - 10, X(sx), top + ph], fill=(60, 60, 60), width=2)
    d.text((X(150), top + ph - 30), "ticks: scanner seams", fill=(90, 90, 90), font=f)
    for v in range(20, 201, 20):
        d.text((X(v) - 10, H - 30), f"{v}", fill=(90, 90, 90), font=f)
    d.text((X(x1) - 80, H - 16), "page x (mm)", fill=(90, 90, 90), font=f)
    for e, lab, dy_ in ((33.5, "C step", 4), (109.0, "C step", 4), (114.5, "Y step", 22)):
        d.text((X(e) + 4, T + dy_), lab, fill=(90, 90, 90), font=f)
    im.save(png)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, type=Path, help="sheet3.py's output directory")
    ap.add_argument("--png", required=True, type=Path, help="the figure to write")
    a = ap.parse_args()
    draw(a.dir, a.png)


if __name__ == "__main__":
    main()

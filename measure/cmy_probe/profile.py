"""The x-profile of a band's lattice score: is the band screened (or contone mush) across SOME of its x extent?

The M281's screener is a per-column-region switch (boundary near x = 107 mm) that turns on after a
content-dependent distance (e041 §041.5i), so one in-band score over the whole band can average a screened
stretch away.  Per band: the band's interior (the margin of readout.band_lattice) cut into n_slices equal
x-slices (~9.3 mm each at 20 on the A4 band); per slice the same lattice_score (all three channels) as
band_lattice, the mean window cell error of the windows whose centre falls in the slice (bands.py's per
window-column profile; a window centre outside the interior counts in the nearest slice), and the mean RGB.

Outputs (readout.run): bands_profile.csv, bands_profile.svg (hand-written: no matplotlib in env/), and per
band profile_max_score / profile_max_slice_x_mm / profile_scores in summary.json.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_probe.bands import WINDOW_CELLS
from measure.cmy_probe.bars import BAR_MARGIN_PX, bar_box_mm
from measure.e041_probe_readout import SCAN_DPI_NOMINAL, Scan, sample_rect
from measure.e041_scale_readout import UNSCREENED_MAX, lattice_score

N_SLICES = 20
REGION_BOUNDARY_MM = 107.0                  # the M281's column-region switch (e041 §041.5i)


def window_centres_mm(band: dict[str, Any], dpi: float, err_by_col: dict[str, float]) -> list[tuple[float, float]]:
    """(x centre in page mm, mean window cell error) per window column of the band."""
    dot_mm = 25.4 / dpi
    cd, bx = int(band.get("cell_dots", 2)), int(band["x_dots"])
    return [((bx + (int(c0) + 0.5 * WINDOW_CELLS) * cd) * dot_mm, e) for c0, e in err_by_col.items()]


def band_lattice_profile(scan: Scan, A: np.ndarray, band: dict[str, Any], dpi: float, n_slices: int = N_SLICES,
                         err_by_col: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Per x-slice of the band's interior: index, x0_mm / x1_mm (page mm), lattice score over all three channels,
    best lattice, windows, mean window cell error (fraction; NaN without windows) and mean RGB."""
    margin_mm = BAR_MARGIN_PX * scan.dpi / SCAN_DPI_NOMINAL / scan.px_per_mm
    x0, y0, x1, y1 = bar_box_mm(band, dpi, margin_mm)
    edges = np.linspace(x0, x1, n_slices + 1)
    width_mm = (x1 - x0) / n_slices
    errs: list[list[float]] = [[] for _ in range(n_slices)]
    for xc, e in window_centres_mm(band, dpi, err_by_col or {}):
        k = int(np.clip(np.floor((xc - x0) / width_mm), 0, n_slices - 1))
        if np.isfinite(e):
            errs[k].append(e)
    step = 25.4 / dpi
    out = []
    for i in range(n_slices):
        box = (float(edges[i]), y0, float(edges[i + 1]), y1)
        lat = lattice_score(scan, A, box, (0, 1, 2))
        try:
            px = sample_rect(scan, A, np.arange(box[0], box[2], step), np.arange(y0, y1, step), order=0)
            rgb = px.reshape(-1, 3).mean(0).tolist()
        except ValueError:                                  # outside the scan
            rgb = [float("nan")] * 3
        out.append({"slice": i, "x0_mm": box[0], "x1_mm": box[2], "score": lat["score"],
                    "best_lattice": lat["best_lattice"], "windows": lat["windows"],
                    "cell_err": float(np.mean(errs[i])) if errs[i] else float("nan"), "mean_rgb": rgb})
    return out


def profile_summary(prof: list[dict[str, Any]]) -> dict[str, Any]:
    """profile_scores, the max and the x centre (page mm) of the slice carrying it."""
    scores = [float(s["score"]) for s in prof]
    fin = [i for i, v in enumerate(scores) if np.isfinite(v)]
    if not fin:
        return {"profile_scores": scores, "profile_max_score": float("nan"), "profile_max_slice_x_mm": float("nan")}
    k = max(fin, key=lambda i: scores[i])
    return {"profile_scores": scores, "profile_max_score": scores[k],
            "profile_max_slice_x_mm": 0.5 * (prof[k]["x0_mm"] + prof[k]["x1_mm"])}


def profile_table(res: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    head = ["scan", "band", "arm", "slice", "x0_mm", "x1_mm", "score", "best_lattice", "windows", "cell_err_pct",
            "mean_R", "mean_G", "mean_B"]
    rows = []
    for r in res:
        for b in r["bands"]:
            for s in b["profile"]:
                rows.append([r["name"], b["name"], b["arm"], s["slice"], s["x0_mm"], s["x1_mm"], s["score"],
                             s["best_lattice"], s["windows"], 100 * s["cell_err"], *s["mean_rgb"]])
    return head, rows


def profile_lines(bands: list[dict[str, Any]]) -> list[str]:
    """One row of rounded slice scores per band with the max and its x."""
    lines = []
    for b in bands:
        row = " ".join(f"{v:4.0f}" if np.isfinite(v) else "   -" for v in b["profile_scores"])
        lines.append(f"  {b['name']:4s} {str(b['arm']):6s} {row}   max {b['profile_max_score']:.1f} "
                     f"at x {b['profile_max_slice_x_mm']:.1f} mm")
    return lines


COLOURS = ("#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#7f7f7f")


def write_svg(path: Path, bands: list[dict[str, Any]], title: str) -> None:
    """x in page mm, the slice lattice scores per band (one polyline per band, labelled by arm), the verdict bar
    (18) and the region boundary (107 mm, dashed); log y when any score exceeds 100."""
    W, H, L, R, T, B = 900, 480, 70, 150, 40, 50
    pts = [(0.5 * (s["x0_mm"] + s["x1_mm"]), float(s["score"])) for b in bands for s in b["profile"]
           if np.isfinite(float(s["score"]))]
    xs = [p[0] for p in pts] + [REGION_BOUNDARY_MM]
    xmin, xmax = (min(xs), max(xs)) if pts else (0.0, 210.0)
    ys = [p[1] for p in pts] + [UNSCREENED_MAX]
    logy = max(ys) > 100
    f = (lambda v: np.log10(max(v, 0.1))) if logy else (lambda v: v)
    ylo = min(f(v) for v in ys) if logy else 0.0
    yhi = max(f(v) for v in ys) * (1.05 if not logy else 1.0) + (0.1 if logy else 0.0)
    if yhi <= ylo:
        yhi = ylo + 1.0

    def px(x: float, y: float) -> tuple[float, float]:
        return (L + (x - xmin) / max(xmax - xmin, 1e-9) * (W - L - R),
                H - B - (f(y) - ylo) / (yhi - ylo) * (H - T - B))
    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif" font-size="12">',
          f'<rect width="{W}" height="{H}" fill="white"/>',
          f'<text x="{L}" y="20">{title} — in-band lattice score per x-slice{" (log y)" if logy else ""}</text>',
          f'<rect x="{L}" y="{T}" width="{W - L - R}" height="{H - T - B}" fill="none" stroke="black"/>']
    for t in np.linspace(xmin, xmax, 6):
        x, _ = px(float(t), UNSCREENED_MAX)
        el.append(f'<text x="{x:.1f}" y="{H - B + 16}" text-anchor="middle">{t:.0f}</text>')
    yt = [10 ** e for e in range(int(np.floor(ylo)), int(np.ceil(yhi)) + 1)] if logy else list(np.linspace(0, yhi, 6))
    for t in yt:
        _, y = px(xmin, float(t))
        if T - 1 <= y <= H - B + 1:
            el.append(f'<text x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{t:g}</text>')
    el.append(f'<text x="{(W - R + L) / 2}" y="{H - 12}" text-anchor="middle">x (page mm)</text>')
    el.append(f'<text x="16" y="{(H - B + T) / 2}" transform="rotate(-90 16 {(H - B + T) / 2})" '
              f'text-anchor="middle">lattice score</text>')
    xa, y18 = px(xmin, UNSCREENED_MAX)
    xb, _ = px(xmax, UNSCREENED_MAX)
    el.append(f'<line x1="{xa:.1f}" y1="{y18:.1f}" x2="{xb:.1f}" y2="{y18:.1f}" stroke="grey"/>')
    el.append(f'<text x="{xb + 4:.1f}" y="{y18 + 4:.1f}" fill="grey">{UNSCREENED_MAX:g}</text>')
    xr, _ = px(REGION_BOUNDARY_MM, UNSCREENED_MAX)
    el.append(f'<line x1="{xr:.1f}" y1="{T}" x2="{xr:.1f}" y2="{H - B}" stroke="black" stroke-dasharray="6,4"/>')
    for j, b in enumerate(bands):
        col = COLOURS[j % len(COLOURS)]
        pp = [px(0.5 * (s["x0_mm"] + s["x1_mm"]), float(s["score"])) for s in b["profile"]
              if np.isfinite(float(s["score"]))]
        el.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.5" points="'
                  + " ".join(f"{x:.1f},{y:.1f}" for x, y in pp) + '"/>')
        el.append(f'<text x="{W - R + 10}" y="{T + 16 + 18 * j}" fill="{col}">{b["name"]} {b["arm"]}</text>')
    el.append("</svg>")
    path.write_text("\n".join(el) + "\n")

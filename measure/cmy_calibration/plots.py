"""R11 — minimal PNG charts drawn with PIL (matplotlib is not installed in env/).

What: a categorical/numeric line chart with optional 95 % interval bars per point, and a grid of small heat maps
(confusion matrices).  Why: the report's figures fig01-fig11 must exist as PNGs in the artefact directory.
How: PIL ImageDraw with the default bitmap font; every chart is deterministic for the same inputs.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PALETTE = ((31, 119, 180), (214, 39, 40), (44, 160, 44), (148, 103, 189), (255, 127, 14), (140, 86, 75),
           (227, 119, 194), (127, 127, 127), (188, 189, 34), (23, 190, 207))


def _font() -> Any:
    return ImageFont.load_default()


def line_chart(path: Path, title: str, xlabels: Sequence[str], series: list[dict[str, Any]], ylabel: str,
               ylim: tuple[float, float] | None = None, size: tuple[int, int] = (900, 520)) -> None:
    """series: [{'label', 'y': [...], 'lo': [...] | None, 'hi': [...] | None}] over the categorical x."""
    W, H = size
    L, R, T, B = 70, 200, 40, 70
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    f = _font()
    vals = [v for s in series for k in ("y", "lo", "hi") for v in (s.get(k) or []) if v is not None
            and math.isfinite(v)]
    lo_, hi_ = ylim if ylim else ((min(vals), max(vals)) if vals else (0.0, 1.0))
    if hi_ - lo_ < 1e-12:
        lo_, hi_ = lo_ - 0.5, hi_ + 0.5
    pad = 0.05 * (hi_ - lo_)
    lo_, hi_ = lo_ - pad, hi_ + pad
    nx = max(1, len(xlabels))

    def X(i: int, j: int = 0) -> float:
        return L + (i + 0.5) * (W - L - R) / nx + (j - len(series) / 2) * 3

    def Y(v: float) -> float:
        return T + (hi_ - v) / (hi_ - lo_) * (H - T - B)
    d.rectangle([L, T, W - R, H - B], outline=(0, 0, 0))
    d.text((L, 10), title, fill=(0, 0, 0), font=f)
    d.text((5, T - 15), ylabel, fill=(0, 0, 0), font=f)
    for k in range(6):
        v = lo_ + k * (hi_ - lo_) / 5
        d.line([L - 4, Y(v), L, Y(v)], fill=(0, 0, 0))
        d.text((5, Y(v) - 5), f"{v:.4g}", fill=(0, 0, 0), font=f)
    for i, lab in enumerate(xlabels):
        d.text((X(i) - 20, H - B + 6 + (i % 3) * 12), str(lab)[:14], fill=(0, 0, 0), font=f)
    for j, s in enumerate(series):
        c = PALETTE[j % len(PALETTE)]
        pts = [(X(i, j), Y(v)) for i, v in enumerate(s["y"]) if v is not None and math.isfinite(v)]
        if len(pts) > 1:
            d.line(pts, fill=c, width=2)
        for i, v in enumerate(s["y"]):
            if v is None or not math.isfinite(v):
                continue
            d.ellipse([X(i, j) - 3, Y(v) - 3, X(i, j) + 3, Y(v) + 3], fill=c)
            lo, hi = (s.get("lo") or [None] * nx)[i], (s.get("hi") or [None] * nx)[i]
            if lo is not None and hi is not None and math.isfinite(lo) and math.isfinite(hi):
                d.line([X(i, j), Y(lo), X(i, j), Y(hi)], fill=c)
        d.rectangle([W - R + 10, T + 16 * j, W - R + 20, T + 16 * j + 10], fill=c)
        d.text((W - R + 25, T + 16 * j), str(s["label"])[:28], fill=(0, 0, 0), font=f)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def heatmaps(path: Path, title: str, mats: list[tuple[str, np.ndarray]], labels: Sequence[str],
             cell_px: int = 46) -> None:
    """Row-normalised matrices side by side, value printed per cell."""
    n = len(mats)
    k = len(labels)
    W = 20 + n * (k * cell_px + 60)
    H = 60 + k * cell_px + 30
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f = _font()
    d.text((10, 8), title, fill=(0, 0, 0), font=f)
    for m, (name, M) in enumerate(mats):
        M = np.asarray(M, np.float64)
        P = M / np.maximum(M.sum(1, keepdims=True), 1)
        x0 = 30 + m * (k * cell_px + 60)
        d.text((x0, 28), name[:40], fill=(0, 0, 0), font=f)
        for i in range(k):
            d.text((x0 - 14, 50 + i * cell_px + cell_px // 2 - 5), labels[i], fill=(0, 0, 0), font=f)
            for j in range(k):
                v = float(P[i, j])
                g = int(255 * (1 - min(1.0, v ** 0.3)))
                d.rectangle([x0 + j * cell_px, 50 + i * cell_px, x0 + (j + 1) * cell_px - 1,
                             50 + (i + 1) * cell_px - 1], fill=(g, g, 255))
                d.text((x0 + j * cell_px + 3, 50 + i * cell_px + cell_px // 2 - 5), f"{100 * v:.2f}",
                       fill=(0, 0, 0) if g > 120 else (255, 255, 255), font=f)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def map_curves(path: Path, title: str, curves: list[tuple[str, np.ndarray, np.ndarray]],
               size: tuple[int, int] = (900, 520)) -> None:
    """Score -> probability step curves (PAVA maps) on a shared numeric axis."""
    W, H = size
    L, R, T, B = 60, 220, 40, 50
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    f = _font()
    xs = np.concatenate([c[1] for c in curves]) if curves else np.array([-1.0, 1.0])
    x_lo, x_hi = float(np.percentile(xs, 1)), float(np.percentile(xs, 99))
    if x_hi - x_lo < 1e-9:
        x_lo, x_hi = x_lo - 1, x_hi + 1
    d.rectangle([L, T, W - R, H - B], outline=(0, 0, 0))
    d.text((L, 10), title, fill=(0, 0, 0), font=f)
    for k in range(5):
        v = x_lo + k * (x_hi - x_lo) / 4
        d.text((L + k * (W - L - R) / 4 - 10, H - B + 5), f"{v:.3g}", fill=(0, 0, 0), font=f)
    for j, (name, sx, p) in enumerate(curves):
        c = PALETTE[j % len(PALETTE)]
        grid = np.linspace(x_lo, x_hi, 400)
        pv = np.interp(grid, sx, p)
        pts = [(L + (g - x_lo) / (x_hi - x_lo) * (W - L - R), T + (1 - q) * (H - T - B)) for g, q in zip(grid, pv)]
        d.line(pts, fill=c, width=2)
        d.rectangle([W - R + 10, T + 16 * j, W - R + 20, T + 16 * j + 10], fill=c)
        d.text((W - R + 25, T + 16 * j), name[:30], fill=(0, 0, 0), font=f)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)

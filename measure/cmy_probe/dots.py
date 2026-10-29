"""The dot-level set of sheet 2 (CMY-PROBE-M281 §9 item 4): the mask path's smallest marks, a record.

A manifest entry {id, toner, pattern, x_dots, y_dots, w_dots, h_dots} with its 0/1 dot pattern in the GT npz
under its id (pattern names: single8, quad8, vlines1, hlines1, vlines2).  Per patch: every printed dot's
centre through the page affine to its nearest scan px, the toner's ink density there (C 255 - R, M 255 - G,
Y 255 - B); the patch placed by the affine and then refined by a whole-px shift within +-SEARCH_DOTS dots
that maximises mean(on) - mean(off) (a toner plane sits up to ~2 dots off the K fiducials on this engine);
reported: the shift, the mean density at the GT's on-dots and off-dots, the page white's density, the
DEPTH of the on-dots and of the off-dots against the sheet's solid of that toner, (on - white) / (solid -
white) — the number that says how much of a full cell an isolated mark lays down (the refuter of 2026-10-11:
the contrast below is ~1 for any mark whose off-dots read as paper, however faint the mark) — the contrast
(on - off) / (on - white) — 1 when the off-dots read as paper, 0 when the marks fill in — and the fraction
of on-dots above the midpoint (on + off) / 2.  A zoom PNG per toner: its five patterns side
by side, the top-left ZOOM_DOTS dots at 8x scan px.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from measure.cmy_probe.stipples import _font
from measure.e041_probe_readout import Scan, sample_rect

TONER_CHANNEL = {"C": 0, "M": 1, "Y": 2}
SEARCH_DOTS = 3
ZOOM = 8
ZOOM_DOTS = 24


def dot_centres_px(A: np.ndarray, d: dict[str, Any], dpi: float) -> tuple[np.ndarray, np.ndarray]:
    """(row, col) float scan px of every printed dot centre of the patch, (h, w) arrays."""
    dot_mm = 25.4 / dpi
    X, Y = np.meshgrid((int(d["x_dots"]) + np.arange(int(d["w_dots"])) + 0.5) * dot_mm,
                       (int(d["y_dots"]) + np.arange(int(d["h_dots"])) + 0.5) * dot_mm)
    return A[1, 0] * X + A[1, 1] * Y + A[1, 2], A[0, 0] * X + A[0, 1] * Y + A[0, 2]


def read_dots(scan: Scan, A: np.ndarray, d: dict[str, Any], gt: Any, dpi: float, white: np.ndarray,
              solid_rgb: np.ndarray | None = None) -> dict[str, Any]:
    pat = np.asarray(gt[d["id"]]).astype(bool)
    if pat.shape != (int(d["h_dots"]), int(d["w_dots"])):
        raise SystemExit(f"dots {d['id']}: GT {pat.shape} vs manifest {d['h_dots']} x {d['w_dots']} — contract fork")
    ch = TONER_CHANNEL[d["toner"]]
    rows, cols = dot_centres_px(A, d, dpi)
    s = int(round(SEARCH_DOTS * scan.dpi / dpi))
    r0, r1 = int(np.floor(rows.min())) - s - 1, int(np.ceil(rows.max())) + s + 2
    c0, c1 = int(np.floor(cols.min())) - s - 1, int(np.ceil(cols.max())) + s + 2
    win = 255.0 - scan.crop(r0, r1, c0, c1, ch)
    ri, ci = np.round(rows).astype(np.int64) - r0, np.round(cols).astype(np.int64) - c0
    best = (-np.inf, 0, 0)
    for dy in range(-s, s + 1):
        for dx in range(-s, s + 1):
            v = win[ri + dy, ci + dx]
            gap = float(v[pat].mean() - v[~pat].mean())
            if gap > best[0]:
                best = (gap, dy, dx)
    _, dy, dx = best
    v = win[ri + dy, ci + dx]
    on, off = float(v[pat].mean()), float(v[~pat].mean())
    w = 255.0 - float(white[ch])
    mid = 0.5 * (on + off)
    solid = 255.0 - float(solid_rgb[ch]) if solid_rgb is not None else float("nan")
    return {"id": d["id"], "toner": d["toner"], "pattern": d["pattern"], "x_dots": int(d["x_dots"]),
            "y_dots": int(d["y_dots"]), "n_on": int(pat.sum()), "n_off": int((~pat).sum()),
            "shift_px": [dy, dx], "shift_dots": [dy * dpi / scan.dpi, dx * dpi / scan.dpi],
            "mean_on": on, "mean_off": off, "white": w, "solid": solid,
            "contrast": (on - off) / (on - w) if on - w > 1e-6 else float("nan"),
            "depth_on": (on - w) / (solid - w) if np.isfinite(solid) and solid - w > 1e-6 else float("nan"),
            "depth_off": (off - w) / (solid - w) if np.isfinite(solid) and solid - w > 1e-6 else float("nan"),
            "on_above_mid": float((v[pat] > mid).mean()), "sd_on": float(v[pat].std()), "sd_off": float(v[~pat].std())}


def zoom(scan: Scan, A: np.ndarray, d: dict[str, Any], dpi: float, rec: dict[str, Any]) -> Image.Image:
    """The patch's top-left ZOOM_DOTS dots, page-aligned at scan px, shifted by the refinement, at 8x."""
    sub = scan.dpi / dpi
    dot_mm = 25.4 / dpi
    n = int(round(ZOOM_DOTS * sub))
    oy, ox = rec["shift_dots"]
    xs = (int(d["x_dots"]) + ox + (np.arange(n) + 0.5) / sub) * dot_mm
    ys = (int(d["y_dots"]) + oy + (np.arange(n) + 0.5) / sub) * dot_mm
    try:
        img = sample_rect(scan, A, xs, ys, order=0)
    except ValueError:
        img = np.full((n, n, 3), 255.0, np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((n * ZOOM, n * ZOOM), Image.NEAREST)


def read_all(scan: Scan, A: np.ndarray, entries: list[dict[str, Any]], gt: Any, dpi: float, white: np.ndarray,
             png_dir: Path | None, solids: dict[str, np.ndarray] | None = None) -> list[dict[str, Any]]:
    recs = []
    tiles: dict[str, list[tuple[Image.Image, dict[str, Any]]]] = {}
    for d in entries:
        r = read_dots(scan, A, d, gt, dpi, white, (solids or {}).get(d["toner"]))
        recs.append(r)
        print(f"  dots {d['id']} {d['toner']} {d['pattern']:8s}: on {r['mean_on']:.1f} off {r['mean_off']:.1f} white "
              f"{r['white']:.1f} solid {r['solid']:.1f} depth on {r['depth_on']:.3f} off {r['depth_off']:.3f} "
              f"contrast {r['contrast']:.3f} on>mid {r['on_above_mid']:.3f} shift {r['shift_dots']}")
        if png_dir is not None:
            tiles.setdefault(d["toner"], []).append((zoom(scan, A, d, dpi, r), r))
    font = _font(16)
    for t, ts in tiles.items():
        side = ts[0][0].width
        sheet = Image.new("RGB", (len(ts) * (side + 16) + 16, side + 60), "white")
        dr = ImageDraw.Draw(sheet)
        for k, (im, r) in enumerate(ts):
            x = 16 + k * (side + 16)
            sheet.paste(im, (x, 44))
            dr.text((x, 4), f"{t} {r['pattern']}: depth of the on-dots {r['depth_on']:.2f} of the solid, off {r['depth_off']:.2f}; "
                            f"contrast {r['contrast']:.2f}, on>mid {r['on_above_mid']:.2f}", fill="black", font=font)
            dr.text((x, 24), f"on {r['mean_on']:.0f} off {r['mean_off']:.0f} white {r['white']:.0f} (density)",
                    fill="grey", font=font)
        sheet.save(png_dir / f"dots-{t}.png")
    return recs

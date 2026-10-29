"""e041 S14/S17 — synthetic 2400 or 4800 dpi scans of a page-scale probe, for e041_scale_readout's smoke test.

Writes a small manifest + bands npz to the S14 contract plus S17's layout axis (tag "S14-synth", page 2400 x
2500 dots: the five fiducials at S14's offsets from the page corners; three full-width noise bands — cmyk5
c3 under toner black, cmy4 c2 detail split into four abutting tile images, cmy8-engine c3; three LAYOUT bands
in S17's schema — "layout_catalogue" per band, "layouts_<band>" in the npz, drawn by S17's rule (states =
rng.choice, then u = rng.random, layout = floor(u x the state's candidate count)):
  L1 c3 cmy8 dot-mixed: two-toner X (one layout), CMY stripes orientation x phase (6 layouts);
  L2 c3 cmy7 dot-mixed: two-toner oriented bands (5:4) orientation x phase (4 layouts);
  L3 c2 cmy7 dot-mixed: two-toner column / row pairs x which toner leads (4 layouts);
and two strips of solid bars: the single toners, both magentas, the overlaps, two cyan candidates and a
toner-black K bar, once in strip A and once in strip B) and paints a page:
data bands from the npz's DOT-LEVEL planes (each plane's dots in that toner's colour, overlaps multiply
reflectances: e041_mixture_synth's model), bars in their own device RGB (so the readout must read them back
at that RGB), fiducials black.  The 600 dpi raster is mapped through a pose at --scan-dpi (scan dpi / 600 px
per dot: 4 at 2400, 8 at 4800) by paint_scan (shift, scale, rotation, optional 180 deg turn, Gaussian blur,
seeded noise), in row strips straight into one uint8 image (no float copy of the page; the noise of strip i
from default_rng([seed, i])).  --plane-offset PLANE DY DX (repeatable, scan px at --scan-dpi) displaces that
data plane's ink (page-aligned; the bars are device RGB and stay in place).  Images over 4 GB are written as
BigTIFF (tifffile).

    PYTHONPATH=src:. env/bin/python -m measure.e041_scale_synth --out /tmp/x --name s14 \\
        --blur-px 3 --noise-sd 8 --rot180 --shift-mm 1.2 -0.7 --rot-deg 0.2 --scale 1.003
    (--manifest M paints the generator's own manifest + <tag>-bands.npz beside it, at its page size; the
    whole-page float painter this replaced peaked at 34 GB for an A4 page at 2400 dpi.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import tifffile
from scipy import ndimage

from measure.e041_mixture_synth import (ENGINE_RGB, M_CORNER, M_SOLID, SINGLE_RGB, TONER_RGB, plane_offsets,
                                        state_planes)
from measure.e041_scale_readout import WINDOW_CELLS, rect_dots

DPI = 600
PAGE_DOTS = (2400, 2500)
PLANES = ("C", "M", "Y", "K")
CMY4 = ["W", "C", "M", "Y"]
CMYK5 = ["W", "C", "M", "Y", "K"]
CMY8 = ["W", "C", "M", "Y", "CM", "CY", "MY", "CMY"]
# (name, section, matching, alphabet, M rgb, cell_dots, method, neutral, height dots, tile images)
SYNTH_BANDS: list[tuple[str, str, str, list[str], tuple[int, int, int], int, str, str, int, int]] = [
    ("A3", "A", "default", CMYK5, M_SOLID, 3, "smooth", "toner", 372, 1),
    ("B3", "B", "off", CMY4, M_SOLID, 2, "detail", "process", 276, 4),
    ("A2", "A", "default", CMY8, M_CORNER, 3, "smooth", "process", 282, 1),
]
BAR_H_DOTS = 93                            # two strips (A matching default, B off) of solid bars
BARS: list[tuple[str, tuple[int, int, int], str]] = [
    ("C", (0, 255, 255), "process"), ("M-solid", M_SOLID, "process"), ("M-corner", M_CORNER, "process"),
    ("Y", (255, 255, 0), "process"), ("CM", (0, 0, 255), "process"), ("CY", (0, 255, 0), "process"),
    ("MY", (255, 0, 0), "process"), ("CMY", (0, 0, 0), "process"),
    ("cyan-0,240,255", (0, 240, 255), "process"),
    ("cyan-16,255,255", (16, 255, 255), "process"), ("K", (0, 0, 0), "toner"),
]
CMY7 = ["W", "C", "M", "Y", "CM", "CY", "MY"]
DOT_COLOUR = {"C": "C-solid", "M": "M-solid", "Y": "Y"}
DOT_PLANE = {"C-solid": 0, "M-solid": 1, "Y": 2}
LAYOUT_PALETTE = {"W": [255, 255, 255], "C": [0, 208, 255], "M": [240, 0, 192], "Y": [255, 255, 0]}
# (name, alphabet, states, cell_dots, two-toner family, CMY family, height dots)
SYNTH_LAYOUT_BANDS: list[tuple[str, str, list[str], int, str, str, int]] = [
    ("L1", "cmy8-dotmix-stripes", CMY8, 3, "x", "stripes-orient-phase", 186),
    ("L2", "cmy7-dotmix-bands", CMY7, 3, "bands-orient-phase", "", 186),
    ("L3", "cmy7-c2-pairs", CMY7, 2, "pairs-col-row", "", 184),
]


# ---------------------------------------------------------------- S17 layout geometry (the generator side)

def grid(cd: int, f: Callable[[int, int], str]) -> list[list[str]]:
    return [[f(r, c) for c in range(cd)] for r in range(cd)]


def entry(lid: str, orient: str | None, phase: int | None, g: list[list[str]]) -> dict[str, Any]:
    return {"id": lid, "orientation": orient, "phase": phase, "grid": g}


def stripes3(o: str, ph: int) -> dict[str, Any]:
    """CMY stripes: "-" toner (C, M, Y)[((r + c) + phase) mod 3]; "+" (C, M, Y)[((c - r) mod 3 + phase)
    mod 3]."""
    def f(r: int, c: int) -> str:
        return DOT_COLOUR["CMY"[((r + c) + ph) % 3 if o == "-" else ((c - r) % 3 + ph) % 3]]
    return entry(f"stripes{o}{ph}", o, ph, grid(3, f))


def x3(a: str, b: str) -> dict[str, Any]:
    """Two-toner X: A on (r + c) even (5 dots), B on odd."""
    return entry("X", None, None, grid(3, lambda r, c: DOT_COLOUR[a if (r + c) % 2 == 0 else b]))


def bands3(a: str, b: str, o: str, ph: int) -> dict[str, Any]:
    """Two-toner oriented band (5:4): "+" A on d = c - r in {0, 1} (phase 0) / {-1, 0} (phase 1); "-" A on
    a = r + c in {2, 3} / {1, 2}; B on the other four dots (one of them 4-isolated)."""
    def f(r: int, c: int) -> str:
        on = (c - r in ((0, 1), (-1, 0))[ph]) if o == "+" else (r + c in ((2, 3), (1, 2))[ph])
        return DOT_COLOUR[a if on else b]
    return entry(f"band{o}{ph}", o, ph, grid(3, f))


def pairs2(a: str, b: str, kind: str, ph: int) -> dict[str, Any]:
    """c2 two-toner pairs: column ("+": A on column `phase`) or row ("-": A on row `phase`)."""
    def f(r: int, c: int) -> str:
        return DOT_COLOUR[a if (c if kind == "col" else r) == ph else b]
    return entry(f"{kind}{ph}", "+" if kind == "col" else "-", ph, grid(2, f))


def layout_catalogue(states: list[str], cd: int, two: str, cmy: str) -> dict[str, list[dict[str, Any]]]:
    cat: dict[str, list[dict[str, Any]]] = {}
    for s in states:
        if len(s) == 1:
            cat[s] = [entry(s, None, None, grid(cd, lambda r, c: "W" if s == "W" else DOT_COLOUR[s]))]
        elif len(s) == 2:
            a, b = s[0], s[1]
            cat[s] = ([x3(a, b)] if two == "x" else
                      [bands3(a, b, o, ph) for o in "+-" for ph in (0, 1)] if two == "bands-orient-phase" else
                      [pairs2(a, b, k, ph) for k in ("col", "row") for ph in (0, 1)])
        else:
            cat[s] = ([stripes3(o, ph) for o in "+-" for ph in (0, 1, 2)] if cmy == "stripes-orient-phase"
                      else [stripes3("-", 0)])
    return cat


def catalogue_planes(cat: dict[str, list[dict[str, Any]]], states: list[str], st: np.ndarray, lt: np.ndarray,
                     cd: int) -> np.ndarray:
    """(4, rows x cd, cols x cd) ink per dot from each cell's catalogue grid."""
    nmax = max(len(v) for v in cat.values())
    lut = np.zeros((len(states), nmax, 4, cd, cd), np.uint8)
    for si, s in enumerate(states):
        for j, e in enumerate(cat[s]):
            for r in range(cd):
                for c in range(cd):
                    if e["grid"][r][c] != "W":
                        lut[si, j, DOT_PLANE[e["grid"][r][c]], r, c] = 1
    R, C = st.shape
    return lut[st, lt].transpose(2, 0, 3, 1, 4).reshape(4, R * cd, C * cd)


def fiducials(W: int, H: int) -> list[dict[str, Any]]:
    """S11/S12/S14's five, at the same offsets from the page corners (F1/F3 at W - 259, F2/F3 at H - 260)."""
    pos = [("F0", 189, 189, 71), ("F1", W - 259, 189, 71), ("F2", 189, H - 260, 71),
           ("F3", W - 259, H - 260, 71), ("F4", 189, 283, 142)]
    return [{"id": i, "x_dots": x, "y_dots": y, "w_dots": 71, "h_dots": h,
             "x_mm": x * 25.4 / DPI, "y_mm": y * 25.4 / DPI, "w_mm": 71 * 25.4 / DPI, "h_mm": h * 25.4 / DPI,
             "rgb": [0, 0, 0]} for i, x, y, h in pos]


def band_planes(states: np.ndarray, alphabet: list[str], cd: int, neutral: str) -> np.ndarray:
    lut = np.stack([state_planes(s, cd, "", neutral) for s in alphabet])          # (S, 4, cd, cd)
    blk = lut[states]                                                             # (r, c, 4, cd, cd)
    r, c = states.shape
    return blk.transpose(2, 0, 3, 1, 4).reshape(4, r * cd, c * cd)


def build(seed0: int = 51000) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    W, H = PAGE_DOTS
    x0, width = 283, W - 2 * 283
    y = 283
    bands, windows, arrays = [], [], {}
    for k, (name, sec, match, alpha, m_rgb, cd, method, neutral, h, n_tiles) in enumerate(SYNTH_BANDS):
        w = (width // (cd * n_tiles)) * cd * n_tiles
        seed = seed0 + k
        states = np.random.default_rng(seed).choice(len(alpha), size=(h // cd) * (w // cd))
        states = states.astype(np.uint8).reshape(h // cd, w // cd)
        arrays[f"states_{k}"] = states
        arrays[f"planes_{k}"] = band_planes(states, alpha, cd, neutral)
        tw = w // n_tiles
        images = [{"x_dots": x0 + i * tw, "y_dots": y, "w_dots": tw, "h_dots": h} for i in range(n_tiles)]
        pal = {s: list(m_rgb if s == "M" else SINGLE_RGB.get(s, ENGINE_RGB.get(s, (0, 0, 0)))) for s in alpha}
        b = {"band": k, "name": name, "section": sec, "matching": match, "alphabet": alpha, "palette": pal,
             "cell_dots": cd, "x_dots": x0, "y_dots": y, "w_dots": w, "h_dots": h, "method": method,
             "neutral": neutral, "images": images, "seed": seed,
             "states_sha256": hashlib.sha256(states.tobytes()).hexdigest()}
        bands.append(b)
        n = WINDOW_CELLS[cd] * cd
        for r in range(h // n):
            for c in range(w // n):
                wx, wy = x0 + c * n, y + r * n
                windows.append({"id": f"{name}-r{r}c{c}", "band": k, "x_dots": wx, "y_dots": wy,
                                "x_mm": wx * 25.4 / DPI, "y_mm": wy * 25.4 / DPI, "cells": WINDOW_CELLS[cd],
                                "cell_dots": cd, "alphabet": alpha, "palette": pal, "method": method,
                                "neutral": neutral, "matching": match, "section": sec,
                                "tile": (c * n + n // 2) // tw if n_tiles > 1 else None})
        y += h + 24
    for k2, (name, family, alpha, cd, two, cmy, h) in enumerate(SYNTH_LAYOUT_BANDS):
        k = len(bands)
        w = (width // cd) * cd
        seed = seed0 + 100 + k2
        rng = np.random.default_rng(seed)
        states = rng.choice(len(alpha), size=(h // cd, w // cd)).astype(np.uint8)
        cat = layout_catalogue(alpha, cd, two, cmy)
        ncand = np.array([len(cat[s]) for s in alpha])
        u = rng.random(states.shape)
        layouts = np.floor(u * ncand[states]).astype(np.uint8)
        arrays[f"states_{k}"], arrays[f"layouts_{k}"] = states, layouts
        arrays[f"planes_{k}"] = catalogue_planes(cat, alpha, states, layouts, cd)
        bands.append({"band": k, "name": name, "section": "A", "matching": "default", "alphabet": family,
                      "states": alpha, "palette": dict(LAYOUT_PALETTE), "cell_dots": cd, "x_dots": x0,
                      "y_dots": y, "w_dots": w, "h_dots": h, "method": "smooth", "neutral": "process",
                      "images": [{"x_dots": x0, "y_dots": y, "w_dots": w, "h_dots": h}], "seed": seed,
                      "layout_catalogue": cat,
                      "states_sha256": hashlib.sha256(states.tobytes()).hexdigest()})
        n = WINDOW_CELLS[cd] * cd
        for r in range(h // n):
            for c in range(w // n):
                wx, wy = x0 + c * n, y + r * n
                windows.append({"id": f"{name}-r{r}c{c}", "band": k, "x_dots": wx, "y_dots": wy,
                                "x_mm": wx * 25.4 / DPI, "y_mm": wy * 25.4 / DPI, "cells": WINDOW_CELLS[cd],
                                "cell_dots": cd, "alphabet": family, "method": "smooth",
                                "neutral": "process", "matching": "default", "section": "A", "tile": None})
        y += h + 24
    bars = []
    for sec, match in (("A", "default"), ("B", "off")):
        bx = x0
        for i, (colour, rgb, neutral) in enumerate(BARS):
            bars.append({"id": f"{sec}-bar{i:02d}", "x_dots": bx, "y_dots": y, "w_dots": 93,
                         "h_dots": BAR_H_DOTS, "rgb": list(rgb), "colour": colour, "section": sec,
                         "matching": match, "neutral": neutral})
            bx += 93 + 24
        bands.append({"band": len(bands), "name": f"{sec}-strip", "section": sec, "matching": match,
                      "alphabet": [], "palette": {}, "cell_dots": 1, "x_dots": x0, "y_dots": y,
                      "w_dots": bx - 24 - x0, "h_dots": BAR_H_DOTS, "method": "smooth", "neutral": "process",
                      "images": [], "seed": None})
        y += BAR_H_DOTS + 24
    if y - 24 > H - 260 - 24:
        raise SystemExit("synthetic layout overruns the bottom fiducials")
    man = {"tag": "S14-synth", "dpi": DPI, "page_dots": [W, H], "bytes": 0, "sha256": "",
           "fiducials": fiducials(W, H), "bands": bands, "bars": bars, "windows": windows,
           "notes": ["synthetic, e041_scale_synth",
                     "layout bands: rng = default_rng(seed); states = rng.choice(len(alphabet), "
                     "size=(rows, cols)); "
                     "u = rng.random((rows, cols)); layout = floor(u * n_candidates(state)) (0 where n = 1)"],
           "novelty": []}
    return man, arrays


def page_planes(man: dict[str, Any], npz: Any) -> tuple[np.ndarray, np.ndarray]:
    """(base RGB uint8: fiducials and device-RGB bars, (4, H, W) uint8 data-band ink per plane)."""
    dpi = float(man["dpi"])
    if "page_dots" in man:
        pd = man["page_dots"]
        W, H = (int(v) for v in ([pd["w"], pd["h"]] if isinstance(pd, dict) else pd))
    else:
        W, H = (int(round(v * dpi / 25.4)) for v in man["page_mm"])
    base = np.full((H, W, 3), 255, np.uint8)
    for f in man["fiducials"]:
        x, y, w, h = rect_dots(f, dpi)
        base[y:y + h, x:x + w] = f.get("rgb", [0, 0, 0])
    for bar in man.get("bars", []):
        x, y, w, h = rect_dots(bar, dpi)
        base[y:y + h, x:x + w] = bar["rgb"]
    planes = np.zeros((4, H, W), np.uint8)
    for b in man["bands"]:
        key = next((k for k in (b.get("band"), b.get("name"))
                    if k is not None and f"planes_{k}" in npz), None)
        if key is not None:
            x, y, w, h = rect_dots(b, dpi)
            planes[:, y:y + h, x:x + w] = np.asarray(npz[f"planes_{key}"], np.uint8)
    return base, planes


def page_raster(man: dict[str, Any], npz: Any, toner: dict[str, tuple[int, int, int]]) -> np.ndarray:
    """The 600 dpi page as uint8 RGB (fiducials, bars, data planes multiplied as reflectances): the S15/S16
    verifiers' in-memory dry runs repeat it 4 x 4; paint_scan paints from page_planes instead."""
    dpi = float(man["dpi"])
    if "page_dots" in man:
        pd = man["page_dots"]
        W, H = (int(v) for v in ([pd["w"], pd["h"]] if isinstance(pd, dict) else pd))
    else:
        W, H = (int(round(v * dpi / 25.4)) for v in man["page_mm"])
    refl = np.ones((H, W, 3), np.float32)
    for f in man["fiducials"]:
        x, y, w, h = rect_dots(f, dpi)
        refl[y:y + h, x:x + w] = np.array(f.get("rgb", [0, 0, 0]), np.float32) / 255
    tr = np.array([toner[p] for p in PLANES], np.float32) / 255.0                  # (4, 3)
    for b in man["bands"]:
        key = next((k for k in (b.get("band"), b.get("name"))
                    if k is not None and f"planes_{k}" in npz), None)
        if key is None:
            continue
        x, y, w, h = rect_dots(b, dpi)
        planes = np.asarray(npz[f"planes_{key}"])
        sq = np.ones((h, w, 3), np.float32)
        for k in range(4):
            sq *= 1.0 - planes[k][..., None].astype(np.float32) * (1.0 - tr[k])
        refl[y:y + h, x:x + w] = sq
    for bar in man.get("bars", []):
        x, y, w, h = rect_dots(bar, dpi)
        refl[y:y + h, x:x + w] = np.array(bar["rgb"], np.float32) / 255.0
    return np.clip(np.round(refl * 255.0), 0, 255).astype(np.uint8)


def dot_index(U: np.ndarray, V: np.ndarray, o: np.ndarray, Wd: int,
              Hd: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(xd, yd, inside): the page dot under each canvas pixel; U, V = Rinv @ pixel centre, o = Rinv @
    offset."""
    xd = np.floor(U - o[0]).astype(np.int64)
    yd = np.floor(V - o[1]).astype(np.int64)
    return xd, yd, (xd >= 0) & (xd < Wd) & (yd >= 0) & (yd < Hd)


def paint_scan(base: np.ndarray, planes: np.ndarray, toner: dict[str, tuple[int, int, int]],
               offsets_px: dict[str, tuple[float, float]], *, scan_dpi: float, rot180: bool,
               shift_mm: tuple[float, float], scale: float, rot_deg: float, pad_mm: float, blur_px: float,
               noise_sd: float, white: float, seed: int, strip_rows: int = 256) -> np.ndarray:
    """base (H, W, 3) uint8 = everything that is not data-plane ink (fiducials, bars); planes (4, H, W) 0/1.
    e041_probe_synth.paint's pose at scan_dpi (page dot (x, y) -> canvas = s R sub (x, y) + pad + shift, the
    inverse per pixel centre, nearest dot), each plane through the pose plus its own (dy, dx) scan-px offset
    (page-aligned: the sign flips with rot180) as e041_mixture_synth.paint_offset_planes, layers multiplying
    as reflectances; then Gaussian blur (blur_px, scan px; a halo of 4 sigma per strip) and seeded noise, row
    strip by row strip into one uint8 image."""
    Hd, Wd = base.shape[:2]
    if rot180:
        base, planes = base[::-1, ::-1], planes[:, ::-1, ::-1]
    sub = scan_dpi / DPI
    pad = int(round(pad_mm * scan_dpi / 25.4))
    Hs, Ws = int(Hd * sub) + 2 * pad, int(Wd * sub) + 2 * pad
    th = np.radians(rot_deg)
    Ri = np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]]) / (scale * sub)
    off = np.array([pad + shift_mm[0] * scan_dpi / 25.4, pad + shift_mm[1] * scan_dpi / 25.4])
    sgn = -1.0 if rot180 else 1.0
    layers = []
    for k, pl in enumerate(PLANES):
        if planes[k].any():
            dy, dx = offsets_px.get(pl, (0.0, 0.0))
            o = off + sgn * np.array([dx, dy])
            layers.append((planes[k], Ri @ o, 1.0 - np.array(toner[pl], np.float32) / 255.0))
    base_o = Ri @ off
    halo = int(math.ceil(4 * blur_px)) + 1 if blur_px > 0 else 0
    out = np.empty((Hs, Ws, 3), np.uint8)
    cols = np.arange(Ws) + 0.5
    for i, r0 in enumerate(range(0, Hs, strip_rows)):
        r1 = min(r0 + strip_rows, Hs)
        a0, a1 = max(0, r0 - halo), min(Hs, r1 + halo)
        C, R = np.meshgrid(cols, np.arange(a0, a1) + 0.5)
        U = Ri[0, 0] * C + Ri[0, 1] * R
        V = Ri[1, 0] * C + Ri[1, 1] * R
        del C, R
        xd, yd, ok = dot_index(U, V, base_o, Wd, Hd)
        refl = np.ones(U.shape + (3,), np.float32)
        refl[ok] = base[yd[ok], xd[ok]].astype(np.float32) / 255.0
        for pk, o, absorb in layers:
            xd, yd, ok = dot_index(U, V, o, Wd, Hd)
            cov = np.zeros(U.shape, np.float32)
            cov[ok] = pk[yd[ok], xd[ok]]
            refl *= 1.0 - cov[..., None] * absorb
        del U, V, xd, yd, ok
        refl *= white
        if blur_px > 0:
            for c in range(3):
                refl[..., c] = ndimage.gaussian_filter(refl[..., c], blur_px, mode="nearest")
        blk = refl[r0 - a0:r0 - a0 + (r1 - r0)]
        if noise_sd > 0:
            blk = blk + np.random.default_rng([seed, i]).standard_normal(blk.shape, np.float32) * noise_sd
        out[r0:r1] = np.clip(np.round(blk), 0, 255).astype(np.uint8)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rot180", action="store_true")
    ap.add_argument("--shift-mm", type=float, nargs=2, default=(0.0, 0.0))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--rot-deg", type=float, default=0.0)
    ap.add_argument("--pad-mm", type=float, default=8.0)
    ap.add_argument("--blur-px", type=float, default=0.0)
    ap.add_argument("--noise-sd", type=float, default=0.0)
    ap.add_argument("--white", type=float, default=255.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--toner-rgb", type=int, nargs=12, default=None, metavar="V",
                    help="C, M, Y, K toner colours as 12 integers (default a printed-looking set)")
    ap.add_argument("--manifest", default=None, help="paint this S14 manifest (+ its bands npz) instead")
    ap.add_argument("--plane-offset", nargs=3, action="append", metavar=("PLANE", "DY_PX", "DX_PX"),
                    help="displace one data plane's ink by (dy, dx) scan px, page-aligned (repeatable)")
    ap.add_argument("--scan-dpi", type=float, default=2400.0,
                    help="scan resolution (scan dpi / 600 px per dot)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    toner = dict(TONER_RGB)
    if args.toner_rgb:
        toner = {p: tuple(args.toner_rgb[3 * k:3 * k + 3]) for k, p in enumerate(PLANES)}
    if args.manifest:
        man = json.loads(Path(args.manifest).read_text())
        npz: Any = np.load(Path(args.manifest).parent / f"{man['tag']}-bands.npz")
    else:
        man, npz = build()
        (out / "S14-synth.manifest.json").write_text(json.dumps(man, indent=1))
        np.savez_compressed(out / "S14-synth-bands.npz", **npz)
    pose: dict[str, Any] = {"rot180": args.rot180, "shift_mm": tuple(args.shift_mm), "scale": args.scale,
                            "rot_deg": args.rot_deg, "pad_mm": args.pad_mm, "blur_px": args.blur_px,
                            "noise_sd": args.noise_sd, "white": args.white, "seed": args.seed}
    img = paint_scan(*page_planes(man, npz), toner, plane_offsets(args.plane_offset), scan_dpi=args.scan_dpi,
                     **pose)
    path = out / f"{args.name}.tiff"
    tifffile.imwrite(path, img, photometric="rgb", bigtiff=img.nbytes > 2 ** 32 - 2 ** 26,
                     resolution=(args.scan_dpi, args.scan_dpi), resolutionunit="INCH")
    print(f"wrote {path} {img.shape[1]} x {img.shape[0]} px at {args.scan_dpi:.0f} dpi")


if __name__ == "__main__":
    main()

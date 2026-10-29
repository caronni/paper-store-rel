"""E043b — the synthetic self-check's sheet-2 case: a stand-in sheet-2 manifest (CMY-PROBE-M281 §9's schema)
rendered at 2400 dpi with planted checkerboard and dot-level truth, read by the readout, recovery asserted.

The stand-in (build_manifest2): A4 at 600 dpi, the five fiducials of synth.py, two cell bands (c2 seed 43
`states_c2`, c3 seed 45 `states_c3`), the bars of §9 item 1 (cyan G 176..190 step 2 and the magenta R x B
grid (axis "grid") and the yellow four, each in mask-a85 and I-2; the registry triples as I-8 and I-ref; four
white, two scrambled, one screened), the twelve checkerboards (W/C, W/M, W/Y, C/M, C/Y, M/Y at c2 and c3,
480 x 240 dots, two rows of six) and the fifteen dot patches (C, M, Y x single8, quad8, vlines1, hlines1,
vlines2; 96 x 96 dots) with their GT patterns.  Not the emitter's layout: the schema's.

Planted, painted analytically per scan px in page-dot coordinates (synth.paint_scan's overlay hook):
checkerboard cells grown by GAIN_DOTS on every edge per toner (square growth: a point is inked when its own
cell is the toner's or it lies within GAIN_DOTS of an edge to one; the diagonal corners overlap), pair[1]'s
pattern shifted by OFFSET_DOTS (c2: (+0.8, 0), c3: (0, -0.8)) against pair[0]'s, overlapping toners
multiplied as transmittances; the yellow stipple (213 lpi +-45 deg, STIPPLE_AMP of the blue channel) on one
checkerboard (W/C c3: at c2 the stipple IS the pattern's fundamental and is masked by construction); dot
patches painted dot by dot from their GT.  Bars, bands, blur and noise as synth.py.

Asserted (besides synth.check's bars, bands, floor and registry rows): per checkerboard and toner the
ink fraction (mean coverage) within FRACTION_TOL of the planted area (0.5 + 2u - 2u^2, u = GAIN_DOTS / cell_dots), the
relative offset of a coloured pair within OFFSET_TOL dots per axis of the planted one, a finite edge width;
the planted board's Y213@45 ratio in Y above STIPPLE_MIN and every other board's judgeable families (all
channels) below NOISE_MAX; every band's whole-band families (local median) below NOISE_MAX; every dot
patch's contrast above DOT_CONTRAST_MIN.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy.special import erf

from measure.cmy_probe.stipples import FAMILIES
from measure.cmy_probe.synth import (FIDUCIALS_MM, PAGE_DOTS_XY, PAPER, SCAN_DPI, TONER_SCAN, check, mm_dots,
                                     page_raster, paint_scan, plant)

TAG2 = "E043b-m281-cmy-probe2-synth"
LOOKUP2 = {"W": [255, 255, 255], "C": [0, 184, 255], "M": [240, 0, 192], "Y": [255, 255, 0]}
X0 = 283
PAIRS = (("W", "C"), ("W", "M"), ("W", "Y"), ("C", "M"), ("C", "Y"), ("M", "Y"))
DOT_PATTERNS = ("single8", "quad8", "vlines1", "hlines1", "vlines2")
GAIN_DOTS = 0.3
OFFSET_DOTS = {2: (0.8, 0.0), 3: (0.0, -0.8)}
STIPPLE_BOARD = "CB-WC-c3"
STIPPLE_AMP = 0.05
PRE_BLUR_PX = 1.0          # the checkerboards are rendered band-limited (an optical blur before sampling)
FRACTION_TOL = 0.02
OFFSET_TOL = 0.2
STIPPLE_MIN = 50.0
NOISE_MAX = 25.0
DOT_CONTRAST_MIN = 0.5


# ---------------------------------------------------------------- the stand-in manifest

def dot_pattern(name: str, n: int = 96) -> np.ndarray:
    p = np.zeros((n, n), np.uint8)
    if name == "single8":
        p[2::8, 2::8] = 1
    elif name == "quad8":
        for dy in (0, 1):
            for dx in (0, 1):
                p[2 + dy::8, 2 + dx::8] = 1
    elif name == "vlines1":
        p[:, ::2] = 1
    elif name == "hlines1":
        p[::2, :] = 1
    elif name == "vlines2":
        p[:, (np.arange(n) // 2) % 2 == 0] = 1
    else:
        raise ValueError(name)
    return p


def _bars2() -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for c in ("mask-a85", "I-2"):
        bars += [{"kind": "sweep", "toner": "C", "axis": "G", "rgb": [0, g, 255], "construct": c} for g in range(176, 191, 2)]
        bars += [{"kind": "sweep", "toner": "M", "axis": "grid", "rgb": [r, 0, b], "construct": c}
                 for r in (236, 238, 240, 242) for b in range(188, 199, 2)]
        bars += [{"kind": "sweep", "toner": "Y", "axis": "B", "rgb": [255, 255, b], "construct": c} for b in (0, 8, 16, 24)]
    bars += [{"kind": "registry", "toner": t, "axis": None, "rgb": list(LOOKUP2[t]), "construct": c}
             for t in "CMY" for c in ("I-8", "I-ref")]
    bars += [{"kind": "white", "toner": None, "axis": None, "rgb": [255, 255, 255], "construct": "none"} for _ in range(4)]
    bars += [{"kind": "scrambled", "toner": t, "axis": None, "rgb": list(LOOKUP2[t]), "construct": "mask-a85"}
             for t in ("C", "M")]
    bars += [{"kind": "screened", "toner": "C", "axis": None, "rgb": [128, 232, 255], "construct": "I-8"}]
    return bars


def build_manifest2(seed_cells: int = 43, seed_c3: int = 45, seed_layout: int = 44) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    gt: dict[str, np.ndarray] = {}
    ids = np.array([0, 1, 2, 4], np.uint8)
    gt["states_c2"] = ids[np.random.default_rng(seed_cells).integers(0, 4, size=(216, 2196))]
    gt["states_c3"] = ids[np.random.default_rng(seed_c3).integers(0, 4, size=(144, 1464))]
    bands = [{"name": "B1", "arm": "mask-a85", "x_dots": X0, "y_dots": 283, "w_dots": 4392, "h_dots": 432,
              "cell_dots": 2, "rows": 216, "cols": 2196, "gt_key": "states_c2"},
             {"name": "B2", "arm": "mask-a85", "x_dots": X0, "y_dots": 739, "w_dots": 4392, "h_dots": 432,
              "cell_dots": 3, "rows": 144, "cols": 1464, "gt_key": "states_c3"}]
    cbs = []
    for row, cd in enumerate((2, 3)):
        for k, pair in enumerate(PAIRS):
            cbs.append({"id": f"CB-{pair[0]}{pair[1]}-c{cd}", "pair": list(pair), "cell_dots": cd, "construct": "mask-a85",
                        "x_dots": X0 + k * 732, "y_dots": 1219 + row * 264, "w_dots": 480, "h_dots": 240})
    bars = _bars2()
    y0 = 1771
    order = np.random.default_rng(seed_layout).permutation(len(bars))
    for slot, i in enumerate(order):
        b = bars[int(i)]
        b.update(id=f"P{int(i):03d}", x_dots=X0 + (slot % 20) * 221, y_dots=y0 + (slot // 20) * 72, w_dots=192, h_dots=48,
                 gt_key=None)
        if b["kind"] == "scrambled":
            b["gt_key"] = f"scrambled_{b['id']}"
            gt[b["gt_key"]] = np.random.default_rng([seed_layout, int(i)]).integers(0, 2, (48, 192), dtype=np.uint8)
    ydots = y0 + (len(bars) // 20 + 1) * 72 + 24
    dots = []
    for k, (t, pat) in enumerate((t, p) for t in "CMY" for p in DOT_PATTERNS):
        did = f"D-{t}-{pat}"
        dots.append({"id": did, "toner": t, "pattern": pat, "x_dots": X0 + k * 288, "y_dots": ydots,
                     "w_dots": 96, "h_dots": 96})
        gt[did] = dot_pattern(pat)
    fids = [{"id": f, "x_mm": x, "y_mm": y, "w_mm": w, "h_mm": h, "x_dots": mm_dots(x), "y_dots": mm_dots(y),
             "w_dots": mm_dots(w), "h_dots": mm_dots(h)} for f, x, y, w, h in FIDUCIALS_MM]
    man = {"tag": TAG2, "dpi": 600, "page_dots_xy": list(PAGE_DOTS_XY), "seed_cells": seed_cells,
           "seed_layout": seed_layout, "lookup": LOOKUP2, "fiducials": fids, "bands": bands, "bars": bars,
           "checkerboards": cbs, "dots": dots,
           "job": {"file": "synthetic (measure/cmy_probe/synth_sheet2.py)", "sha256": "", "bytes": 0}}
    return man, gt


# ---------------------------------------------------------------- the planted overlay

def planted_fraction(cell_dots: int, gain_dots: float = GAIN_DOTS) -> float:
    u = gain_dots / cell_dots
    return 0.5 + 2 * u - 2 * u * u


def toner_offset(cb: dict[str, Any], toner: str) -> tuple[float, float]:
    return OFFSET_DOTS[int(cb["cell_dots"])] if (cb["pair"][1] == toner and cb["pair"][0] != "W") else (0.0, 0.0)


def _boxes(u: np.ndarray, cd: int, g: float, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """(sum, alternating sum) over cells k of the Gaussian-blurred 1-D hole indicator [k cd + g, (k + 1) cd - g]."""
    k0 = np.floor(u / cd)
    s2 = sigma * np.sqrt(2.0)
    S = np.zeros_like(u)
    Alt = np.zeros_like(u)
    for dk in range(-2, 3):
        k = k0 + dk
        b = 0.5 * (erf((u - k * cd - g) / s2) - erf((u - (k + 1) * cd + g) / s2))
        S += b
        Alt += np.where(k % 2 == 0, b, -b)
    return S, Alt


def blurred_checker(u: np.ndarray, v: np.ndarray, cd: int, parity: int, g: float, sigma: float) -> np.ndarray:
    """Coverage of a toner on the cells of `parity` ((i + j) % 2, i row from v, j column from u), its squares
    grown by g dots, blurred by a Gaussian of sigma dots — exact: the white holes are separable boxes, and the
    parity sum splits into products of 1-D sums: white = (Sx Sy - (-1)^parity Ax Ay) / 2."""
    Sx, Ax = _boxes(u, cd, g, sigma)
    Sy, Ay = _boxes(v, cd, g, sigma)
    return 1.0 - 0.5 * (Sx * Sy - (1 - 2 * parity) * Ax * Ay)


def blurred_rect(x: np.ndarray, a: float, b: float, sigma: float) -> np.ndarray:
    s2 = sigma * np.sqrt(2.0)
    return 0.5 * (erf((x - a) / s2) - erf((x - b) / s2))


def make_overlay(man: dict[str, Any], gt: Any):
    """The overlay painting checkerboards and dot patches in continuous page-dot coordinates."""
    paper = np.array(PAPER, np.float32)
    trans = {t: np.array(TONER_SCAN[t], np.float32) / paper for t in TONER_SCAN}
    f = FAMILIES["Y213@45"][0] / 600.0
    kst = [(2 * np.pi * f * math.cos(math.radians(a)), 2 * np.pi * f * math.sin(math.radians(a))) for a in (45.0, -45.0)]

    sigma = PRE_BLUR_PX * float(man["dpi"]) / SCAN_DPI          # in printed dots

    def overlay(X: np.ndarray, Y: np.ndarray, val: np.ndarray) -> None:
        ylo, yhi = float(Y.min()), float(Y.max())
        for cb in man["checkerboards"]:
            x0, y0, w, h, cd = (int(cb[k]) for k in ("x_dots", "y_dots", "w_dots", "h_dots", "cell_dots"))
            if yhi < y0 or ylo >= y0 + h:
                continue
            pad = 4 * sigma
            m = (X >= x0 - pad) & (X < x0 + w + pad) & (Y >= y0 - pad) & (Y < y0 + h + pad)
            if not m.any():
                continue
            xs, ys = X[m].astype(np.float64), Y[m].astype(np.float64)
            colour = np.ones((len(xs), 3), np.float32) * paper
            for par, t in enumerate(cb["pair"]):
                if t == "W":
                    continue
                ox, oy = toner_offset(cb, t)
                u, v = xs - x0 - ox, ys - y0 - oy
                cov = blurred_checker(u, v, cd, par, GAIN_DOTS, sigma)
                cov *= blurred_rect(xs, x0, x0 + w, sigma) * blurred_rect(ys, y0, y0 + h, sigma)
                colour *= (1.0 - cov[:, None] * (1.0 - trans[t][None, :])).astype(np.float32)
            if cb["id"] == STIPPLE_BOARD:
                s = 0.5 + 0.25 * sum(np.cos(kx * xs + ky * ys) for kx, ky in kst)
                colour[:, 2] *= (1.0 - STIPPLE_AMP * s).astype(np.float32)
            val[m] = colour
        for d in man["dots"]:
            x0, y0, w, h = (int(d[k]) for k in ("x_dots", "y_dots", "w_dots", "h_dots"))
            if yhi < y0 or ylo >= y0 + h:
                continue
            m = (X >= x0) & (X < x0 + w) & (Y >= y0) & (Y < y0 + h)
            if not m.any():
                continue
            pat = np.asarray(gt[d["id"]], bool)
            on = pat[np.floor(Y[m] - y0).astype(np.int64), np.floor(X[m] - x0).astype(np.int64)]
            colour = np.ones((len(on), 3), np.float32) * paper
            colour[on] = TONER_SCAN[d["toner"]]
            val[m] = colour
    return overlay


# ---------------------------------------------------------------- the checks

def check_sheet2(summary: dict[str, Any]) -> tuple[list[str], bool]:
    r = summary["scans"][0]
    lines = [f"{'board':10s} {'toner':5s} {'frac planted':>12s} {'read':>6s} {'edge um':>8s}  "
             f"{'rel planted':>14s} {'rel read':>14s}  {'Y213 in Y':>9s} {'worst other':>12s}  ok"]
    ok_all = True
    for c in r["checkerboards"]:
        cd = c["cell_dots"]
        fam = c["families"]
        y213 = fam["Y"]["Y213@45"]
        if c["id"] == STIPPLE_BOARD:
            fam_ok = np.isfinite(y213) and y213 > STIPPLE_MIN
            other = max((v for ch, fs in fam.items() for f, v in fs.items()
                         if np.isfinite(v) and f != "Y213@45"), default=float("nan"))
        else:
            other = c["worst_ratio"]
            fam_ok = not (other >= NOISE_MAX)
        pair = c["pair"].split("/")
        planted_rel = OFFSET_DOTS[cd] if pair[0] != "W" else None
        for k, (t, v) in enumerate(c["toners"].items()):
            pf = planted_fraction(cd)
            ok = abs(v["ink_fraction"] - pf) <= FRACTION_TOL and np.isfinite(v["edge_um"]) and v["edge_um"] > 0
            rel_txt = ""
            if k == 0 and planted_rel is not None:
                rel_ok = (abs(c["rel_dx_dots"] - planted_rel[0]) <= OFFSET_TOL
                          and abs(c["rel_dy_dots"] - planted_rel[1]) <= OFFSET_TOL)
                ok &= rel_ok
                rel_txt = (f"({planted_rel[0]:+.2f},{planted_rel[1]:+.2f}) "
                           f"({c['rel_dx_dots']:+.2f},{c['rel_dy_dots']:+.2f})")
            if k == 0:
                ok &= bool(fam_ok)
            ok_all &= bool(ok)
            ftxt = (f"{y213:9.1f} {other:12.1f}" if k == 0 else " " * 22)
            lines.append(f"{c['id']:10s} {t:5s} {pf:12.3f} {v['ink_fraction']:6.3f} {v['edge_um']:8.1f}  "
                         f"{rel_txt:>29s}  {ftxt}  {'ok' if ok else 'FAIL'}")
    for b in r["bands"]:
        ok = bool(b["worst_ratio"] < NOISE_MAX)
        ok_all &= ok
        lines.append(f"band {b['name']} c{b['cell_dots']} whole-band families (local) worst {b['worst_family']} in "
                     f"{b['worst_channel']} {b['worst_ratio']:.1f} < {NOISE_MAX:g} (radial Y213@45 in Y "
                     f"{b['families']['Y']['Y213@45']:.1f}, a record): {'ok' if ok else 'FAIL'}")
    for d in r["dots"]:
        ok = d["contrast"] > DOT_CONTRAST_MIN
        ok_all &= bool(ok)
        lines.append(f"dots {d['id']:14s} contrast {d['contrast']:.3f} (> {DOT_CONTRAST_MIN}) on>mid "
                     f"{d['on_above_mid']:.3f} shift {d['shift_dots']}  {'ok' if ok else 'FAIL'}")
    return lines, bool(ok_all)


def main_sheet2(out: Path, seed: int, remove_scan: bool) -> int:
    from measure.cmy_probe.readout import run as run_readout
    man, gt = build_manifest2()
    man_path, gt_path = out / f"{TAG2}.manifest.json", out / f"{TAG2}-gt.npz"
    man_path.write_text(json.dumps(man, indent=1))
    np.savez_compressed(gt_path, **gt)
    p = plant(man, seed)
    for b in man["bars"]:          # the bars at the registry value carry the checkerboards' solids, unplanted
        if b.get("toner") in TONER_SCAN and b.get("rgb") == LOOKUP2[b["toner"]]:
            p.colour[b["id"]] = TONER_SCAN[b["toner"]]
            p.screen.pop(b["id"], None)
            p.crosstalk.pop(b["id"], None)
    base, screen = page_raster(man, gt, p)
    img = paint_scan(base, screen, seed, overlay=make_overlay(man, gt))
    del base, screen
    scan_path = out / f"{TAG2}-synth-{seed}.tiff"
    Image.fromarray(img).save(scan_path, dpi=(SCAN_DPI, SCAN_DPI))
    print(f"wrote {scan_path} {img.shape[1]} x {img.shape[0]} px")
    del img
    try:
        summary = run_readout([scan_path], man_path, gt_path, out / "readout", float(SCAN_DPI))
    finally:
        if remove_scan:
            scan_path.unlink(missing_ok=True)
    l1, ok1 = check(summary, p)
    l2, ok2 = check_sheet2(summary)
    print("\nSELF-CHECK sheet 2 (planted vs read)\n" + "\n".join(l1 + l2)
          + f"\nSELF-CHECK {'PASSED' if ok1 and ok2 else 'FAILED'}")
    return 0 if ok1 and ok2 else 1
